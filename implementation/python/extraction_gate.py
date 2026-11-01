# -*- coding: utf-8 -*-
"""F87 引文核验接抽取路径强制闸（工单 W2b-U02）。

顺序纪律（07 E14：引文/支持服务→抽取接线→UI 闭环；06 F87：独立核验
服务先实现，再接抽取）：本模块是**闸**，不是第二核验器。版本/效力/时点/
取文/引文支持判定全部复用 W2a-U14 已 VERIFIED 的 citation_verifier
（citation.{parse,verify,verify_document}；其版本面经 W2a-U13
statute.citation_gate，法源消费经 E22 冻结面 lccc_consumer v1.1）——
本模块零新增核验算法，只做闸政策映射与记账。

强制闸（非聊天装饰）的结构保证：
  - 抽取路径候选（格候选）经 extraction.register 入册即具名 UNVERIFIED；
  - 登记面拒绝携带任何闸状态字段的候选（gate_status/verified*/citation
    记录）——抽取方无法伪造已核状态，没有旁路；
  - gate_status 只能经 extraction.gate 转移，而 gate 每次都真调核验服务
    （未钉定面/缺 as_of 即响亮拒绝，绝不静默放行）；
  - 三态闭集 {UNVERIFIED, CITATION_VERIFIED, REJECTED}；REJECTED 理由
    闭集具名（伪引文/旧版本/误引/虚构/未知 fail-closed/无引用）。

记账纪律（06 行 F87 acceptance）：
  - quote 存在不等于命题支持：候选最好结局也只是 CITATION_VERIFIED
    （引用级），proposition_support 恒不代签——具名
    UNSIGNED_QUOTE_EXISTENCE_IS_NOT_PROPOSITION_SUPPORT；命题支持判定
    属 E14 后续支持核验面，本闸绝不产出命题级 PASS 字段；
  - 伪引文/旧版本拒绝：候选任一引用 虚构/误引/已废止/已修订/失效/替代/
    未知 → 候选 REJECTED，理由逐引用具名（fail-closed，不猜）；
  - 格候选不伪已核：未过闸候选恒 UNVERIFIED 具名，绝不缺席或伪 VERIFIED；
  - 无批次级 PASS 笼统结论：candidates 只回逐候选状态＋计数。

状态面：扁平 JSON（工作区约束 4），落 <state_root>/batches/<batch_id>.json；
闸记录 append-only（重闸不删旧记录，历史可回读）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from bridge_errors import NotConnected

# ---------------------------------------------------------------------- #
# 闸状态闭集与理由闭集
# ---------------------------------------------------------------------- #

GATE_UNVERIFIED = "UNVERIFIED"
GATE_CITATION_VERIFIED = "CITATION_VERIFIED"
GATE_REJECTED = "REJECTED"
GATE_STATUSES = (GATE_UNVERIFIED, GATE_CITATION_VERIFIED, GATE_REJECTED)

# 命题支持恒不代签（quote 存在不等于命题支持）
SUPPORT_PENDING_GATE = "PENDING_GATE"
SUPPORT_UNSIGNED = "UNSIGNED_QUOTE_EXISTENCE_IS_NOT_PROPOSITION_SUPPORT"
SUPPORT_NOT_APPLICABLE = "NOT_APPLICABLE_GATE_REJECTED"

# REJECTED 理由闭集（映射自 F70 单条核验状态；fail-closed 兜底在末位）
REJECT_NO_CITATION = "NO_CITATION_PARSED"
REJECT_FABRICATED_TITLE = "FABRICATED_TITLE_LOCAL_MISS"
REJECT_FABRICATED_QUOTE = "FABRICATED_QUOTE_NOT_IN_REAL_TEXT"
REJECT_MISATTRIBUTED_QUOTE = "MISATTRIBUTED_QUOTE_OTHER_ARTICLE"
REJECT_ARTICLE_ABSENT = "ARTICLE_NOT_IN_REAL_TEXT"
REJECT_OLD_ABOLISHED = "OLD_VERSION_ABOLISHED"
REJECT_OLD_AMENDED = "OLD_VERSION_AMENDED"
REJECT_OLD_EXPIRED = "OLD_VERSION_EXPIRED"
REJECT_OLD_SUPERSEDED = "OLD_VERSION_SUPERSEDED"
REJECT_UNKNOWN_FAIL_CLOSED = "UNKNOWN_FAIL_CLOSED"
REJECTION_REASONS = (
    REJECT_NO_CITATION, REJECT_FABRICATED_TITLE, REJECT_FABRICATED_QUOTE,
    REJECT_MISATTRIBUTED_QUOTE, REJECT_ARTICLE_ABSENT, REJECT_OLD_ABOLISHED,
    REJECT_OLD_AMENDED, REJECT_OLD_EXPIRED, REJECT_OLD_SUPERSEDED,
    REJECT_UNKNOWN_FAIL_CLOSED,
)

# F70 状态 → 闸理由（确定性映射；F70 已 VERIFIED，本表不重判任何事实）
_STATUS_TO_REASON = {
    "虚构": REJECT_FABRICATED_TITLE,
    "已废止": REJECT_OLD_ABOLISHED,
    "已修订": REJECT_OLD_AMENDED,
    "失效": REJECT_OLD_EXPIRED,
    "替代": REJECT_OLD_SUPERSEDED,
}
_CODE_TO_REASON = {
    "QUOTE_NOT_IN_REAL_TEXT": REJECT_FABRICATED_QUOTE,
    "QUOTE_MISATTRIBUTED": REJECT_MISATTRIBUTED_QUOTE,
    "ARTICLE_NOT_IN_REAL_TEXT": REJECT_ARTICLE_ABSENT,
}

GATE_FACE = ("citation.verify(W2a-U14 VERIFIED)→statute.citation_gate"
             "(W2a-U13)→lccc_consumer(E22 freeze v1.1)")

# 登记面拒绝的闸状态字段（抽取方不可伪造已核——无旁路）
FORBIDDEN_REGISTER_FIELDS = (
    "gate_status", "verified", "verified_scoped", "citation_verified",
    "citation_records", "gate_records", "proposition_support",
    "rejection_reasons",
)

_BATCH_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_AS_OF_RE = re.compile(r"^\d{8}$")


# ---------------------------------------------------------------------- #
# 状态面（扁平 JSON；单进程纪律，E14 租约/generation 属后续工单）
# ---------------------------------------------------------------------- #


def _state_root(config: dict) -> Path:
    root = config.get("extraction_gate_state_root")
    if not root:
        raise NotConnected("extraction_gate_state_root_not_configured")
    return Path(root)


def _batch_path(root: Path, batch_id: str) -> Path:
    return root / "batches" / (batch_id + ".json")


def _load_batch(root: Path, batch_id: str) -> dict:
    path = _batch_path(root, batch_id)
    if not path.is_file():
        raise NotConnected("extraction_batch_not_registered:" + batch_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise NotConnected("extraction_state_unreadable:"
                           + type(exc).__name__) from None


def _store_batch(root: Path, batch: dict) -> None:
    path = _batch_path(root, batch["batch_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(batch, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, path)  # 原子提交：中断不留半写状态


def _candidate_view(candidate: dict) -> dict:
    """候选回读投影：闸状态恒在场（未核状态具名，绝不缺席）。"""
    view = {
        "candidate_id": candidate["candidate_id"],
        "text": candidate["text"],
        "provenance": candidate.get("provenance"),
        "gate_status": candidate.get("gate_status", GATE_UNVERIFIED),
        "proposition_support": candidate.get("proposition_support",
                                             SUPPORT_PENDING_GATE),
        "rejection_reasons": candidate.get("rejection_reasons", []),
    }
    if candidate.get("gate_history"):
        view["gate_history"] = candidate["gate_history"]
    return view


# ---------------------------------------------------------------------- #
# 面钉定（漂移即响亮失败——闸绝不跑在未钉定的法源面上）
# ---------------------------------------------------------------------- #


def _face_sha256(config: dict) -> str:
    """闸运行前置：法源面 sha256 钉定复验（config.codices_face_sha256）。

    缺钉定配置＝拒绝开闸（强制闸纪律：先核验服务[钉定面]再接抽取，
    不跑裸面）；在盘 sha 与钉定不符＝响亮失败，绝不静默放行。
    """
    pinned = config.get("codices_face_sha256")
    if not isinstance(pinned, str) or not re.fullmatch(
            r"[0-9a-f]{64}", pinned):
        raise NotConnected("extraction_gate_face_sha_pin_required")
    import_path = config.get("codices_import_path")
    if not import_path:
        raise NotConnected("codices_import_path_not_configured")
    face_file = os.path.join(import_path, "lccc_consumer.py")
    if not os.path.isfile(face_file):
        raise NotConnected("lccc_consumer_not_in_import_path:"
                           + str(import_path))
    digest = hashlib.sha256(
        Path(face_file).read_bytes()).hexdigest()
    if digest != pinned:
        raise NotConnected("codices_face_sha256_drift:" + digest)
    return digest


# ---------------------------------------------------------------------- #
# extraction.register —— 抽取路径入册（具名 UNVERIFIED，无旁路）
# ---------------------------------------------------------------------- #


def register(args: dict, config: dict) -> dict:
    batch_id = args.get("batch_id")
    if not isinstance(batch_id, str) or not _BATCH_ID_RE.fullmatch(batch_id):
        raise NotConnected("extraction_batch_id_invalid")
    candidates = args.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise NotConnected("extraction_candidates_required")
    prepared = []
    for offset, item in enumerate(candidates):
        if not isinstance(item, dict):
            raise NotConnected("extraction_candidate_must_be_object:%d"
                               % offset)
        # 强制闸核心：抽取方携带的任何闸状态字段＝伪造未遂，响亮拒绝
        forged = sorted(set(item) & set(FORBIDDEN_REGISTER_FIELDS))
        if forged:
            raise NotConnected(
                "extraction_register_gate_fields_refused:"
                + ",".join(forged))
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise NotConnected("extraction_candidate_text_required:%d"
                               % offset)
        provenance = item.get("provenance")
        if provenance is not None and not isinstance(provenance, dict):
            raise NotConnected("extraction_candidate_provenance_invalid:%d"
                               % offset)
        prepared.append({
            "candidate_id": "cand_%04d" % (offset + 1),
            "text": text,
            "provenance": provenance,
            "gate_status": GATE_UNVERIFIED,
            "proposition_support": SUPPORT_PENDING_GATE,
            "rejection_reasons": [],
            "gate_history": [],
        })
    root = _state_root(config)
    if _batch_path(root, batch_id).exists():
        raise NotConnected("extraction_batch_already_registered:" + batch_id)
    batch = {
        "schema": 1,
        "batch_id": batch_id,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "candidates": prepared,
    }
    _store_batch(root, batch)
    return {
        "batch_id": batch_id,
        "registered": len(prepared),
        "gate_status_by_candidate": {
            c["candidate_id"]: c["gate_status"] for c in prepared},
        "note": "登记即具名 UNVERIFIED；已核状态只能经 extraction.gate"
                "（真调核验服务）转移，登记面无闸状态字段可传",
    }


# ---------------------------------------------------------------------- #
# extraction.gate —— 强制闸执行（每次真调 W2a-U14 核验服务）
# ---------------------------------------------------------------------- #


def _reject_reason(citation_record: dict) -> str:
    """F70 单条记录 → 闸理由（确定性映射；映射不到＝fail-closed 未知）。"""
    status = citation_record.get("status")
    if status == "误引":
        return _CODE_TO_REASON.get(citation_record.get("code"),
                                   REJECT_UNKNOWN_FAIL_CLOSED)
    reason = _STATUS_TO_REASON.get(status)
    if reason:
        return reason
    # 现行但未过范围核（结构性不可能：F70 现行必 verified_scoped；防漂移）
    if status == "现行" and citation_record.get("verified_scoped") is True:
        return ""  # 由调用方按通过处理
    return REJECT_UNKNOWN_FAIL_CLOSED


def gate_run(args: dict, config: dict) -> dict:
    batch_id = args.get("batch_id")
    if not isinstance(batch_id, str) or not _BATCH_ID_RE.fullmatch(batch_id):
        raise NotConnected("extraction_batch_id_invalid")
    as_of = args.get("as_of")
    if as_of is None:
        raise NotConnected("extraction_gate_as_of_required_fail_closed")
    if not isinstance(as_of, str) or not _AS_OF_RE.fullmatch(as_of):
        raise NotConnected("extraction_gate_as_of_must_be_yyyymmdd")
    face_sha = _face_sha256(config)  # 钉定复验前置：漂移即响亮失败

    # 核验服务唯一权威：版本/效力/时点/取文/引文支持全在 W2a-U14 面
    # （md 扫描缓存在面模块进程级共享——一次闸跑多引用不重复冷扫）
    from citation_verifier import parse_citations, verify_citation

    root = _state_root(config)
    batch = _load_batch(root, batch_id)
    run_seq = len(batch.get("gate_runs", [])) + 1
    run_results = []
    for candidate in batch["candidates"]:
        parsed_items = parse_citations(candidate["text"])
        citation_records = []
        reasons: list = []
        if not parsed_items:
            reasons.append({
                "reason": REJECT_NO_CITATION,
                "citation_text": None,
                "status": None,
                "verifier_code": None,
            })
        else:
            for parsed in parsed_items:
                parsed = dict(parsed)
                parsed["as_of"] = as_of
                record = verify_citation(parsed, config)
                citation_records.append({
                    key: record.get(key) for key in (
                        "citation_text", "status", "decision", "code",
                        "verified_scoped", "identifier")
                })
                support = record.get("support") or {}
                citation_records[-1]["quote_in_article"] = support.get(
                    "quote_in_article")
                reason = _reject_reason(record)
                if reason:
                    reasons.append({
                        "reason": reason,
                        "citation_text": record.get("citation_text"),
                        "status": record.get("status"),
                        "verifier_code": record.get("code"),
                    })
        history_entry = {
            "run_seq": run_seq,
            "as_of": as_of,
            "citations": citation_records,
        }
        if reasons:
            gate_status = GATE_REJECTED
            candidate["rejection_reasons"] = reasons
            candidate["proposition_support"] = SUPPORT_NOT_APPLICABLE
            history_entry["rejection_reasons"] = reasons
        else:
            gate_status = GATE_CITATION_VERIFIED
            candidate["rejection_reasons"] = []
            # quote 存在不等于命题支持：最好结局也不代签命题支持
            candidate["proposition_support"] = SUPPORT_UNSIGNED
        candidate["gate_status"] = gate_status
        history_entry["gate_status"] = gate_status
        candidate["gate_history"].append(history_entry)
        run_results.append({
            "candidate_id": candidate["candidate_id"],
            "gate_status": gate_status,
            "rejection_reasons": reasons,
        })
    batch.setdefault("gate_runs", []).append({
        "run_seq": run_seq,
        "as_of": as_of,
        "gated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "face_sha256": face_sha,
        "verification_face": GATE_FACE,
        "results": run_results,
    })
    _store_batch(root, batch)
    counts: dict = {}
    for item in run_results:
        counts[item["gate_status"]] = counts.get(item["gate_status"], 0) + 1
    return {
        "batch_id": batch_id,
        "run_seq": run_seq,
        "as_of": as_of,
        "face_sha256": face_sha,
        "verification_face": GATE_FACE,
        "results": run_results,
        "by_gate_status": counts,
        "note": "引用级闸结论；quote 存在不等于命题支持——"
                "proposition_support 恒不代签（E14 支持核验面另做）",
    }


# ---------------------------------------------------------------------- #
# 回读面（逐候选状态；无批次级 PASS 笼统结论）
# ---------------------------------------------------------------------- #


def candidates_read(args: dict, config: dict) -> dict:
    batch_id = args.get("batch_id")
    if not isinstance(batch_id, str) or not _BATCH_ID_RE.fullmatch(batch_id):
        raise NotConnected("extraction_batch_id_invalid")
    batch = _load_batch(_state_root(config), batch_id)
    views = [_candidate_view(c) for c in batch["candidates"]]
    counts: dict = {}
    for view in views:
        counts[view["gate_status"]] = counts.get(view["gate_status"], 0) + 1
    return {
        "batch_id": batch_id,
        "candidates": views,
        "by_gate_status": counts,
        "gate_runs": len(batch.get("gate_runs", [])),
        "accounting": "per_candidate_scoped",
        "note": "逐候选状态记账——无批次级 PASS 笼统结论；未过闸候选"
                "恒 UNVERIFIED 具名",
    }


def candidate_read(args: dict, config: dict) -> dict:
    batch_id = args.get("batch_id")
    if not isinstance(batch_id, str) or not _BATCH_ID_RE.fullmatch(batch_id):
        raise NotConnected("extraction_batch_id_invalid")
    candidate_id = args.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise NotConnected("extraction_candidate_id_required")
    batch = _load_batch(_state_root(config), batch_id)
    for candidate in batch["candidates"]:
        if candidate["candidate_id"] == candidate_id:
            return _candidate_view(candidate)
    raise NotConnected("extraction_candidate_not_found:" + candidate_id)


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（extraction.*）
# ---------------------------------------------------------------------- #


def extraction_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发（extraction.*）。未列方法绝不落到这里。"""
    if method == "extraction.register":
        return register(args, config)
    if method == "extraction.gate":
        return gate_run(args, config)
    if method == "extraction.candidates":
        return candidates_read(args, config)
    if method == "extraction.candidate":
        return candidate_read(args, config)
    raise NotConnected("extraction_method_not_in_frozen_list:" + method)
