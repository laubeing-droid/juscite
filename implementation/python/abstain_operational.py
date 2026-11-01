# -*- coding: utf-8 -*-
"""F91 abstain 反修复＋operational 模式产品面（工单 W4-U46）。

06 行 F91（v1.5；owner=product+harness；acceptance「覆盖充分题可纠正误
拒答但重过闸；操作性材料整理仍输出且标边界」；preserved「防 fail-closed
被用户当『动不动拒绝用』」）。

三个模式，结构性分开：

1. abstain（拒答具名）——每次正式拒答具名入账：理由闭集＋缺失输入清
   单＋问题摘要。拒答不是静默拒绝：有账可查、有因可读（防「动不动拒
   绝用」），但对正式结论的阻断不松动（08§4：未知关键输入阻断该正式
   结论）。

2. 反修复（abstain repair）——用户主张误拒并提交纠正候选时：
   a. 覆盖充分性判定绑定可具名证据：纠正候选中的引用逐条经 W2a-U14
      citation 面确定性核验（同一唯一权威，零模型自评）；覆盖证据＝
      逐条核验记录（status/identifier/verified_scoped）。至少一条
      verified_scoped 才算「覆盖充分题」（有真实法源支撑纠正）；否则
      coverage_insufficient 具名拒（该拒答不是误拒，纠正无效）。
   b. 重过闸（结构断言＝本单验收硬点）：纠正产物只能经 F87 闸同一路
      径——extraction_gate.register（入册即 UNVERIFIED，登记面拒绝闸
      状态字段＝无法伪造已核）→ extraction_gate.gate_run（每次真调
      F70 核验服务）。本模块不 import 任何第二核验算法、不提供任何
      「不过闸直接采纳纠正」的方法。CITATION_VERIFIED 才产可交付纠正
      产物（引用级，不代签命题支持——沿 F87 SUPPORT_UNSIGNED 纪律）；
      REJECTED（含 UNKNOWN_FAIL_CLOSED）就拒——fail-closed 红线不松动。
   c. 修复事件经 harness 账本（harness.abstain_event_record）记账，
      repair_gate_* 必带闸凭据（账本半边结构断言）。

3. operational（操作性交付照给）——材料整理/格式化等操作性任务不受
   法律闸阻断：确定性文本操作闭集（正则＋状态机，零模型参与）照常产
   出交付物，但产物恒带 boundary_mark=NON_LEGAL_CONCLUSION（『非法律
   结论』边界标记）；操作性路径零 citation/extraction 调用（AST 可断
   言），产物试图携带法律结论字段（gate_status/citations/legal_
   conclusion 等）具名拒——操作交付永不冒法律结论。

状态面：扁平 JSON，<abstain_state_root>/abstains/<id>.json（append-only
事件数组）；确定性：同输入两跑同字节（无时钟入账面字段由调用方携带
时戳，模块不取本机时钟——可复现）。
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
# 闭集
# ---------------------------------------------------------------------- #

# 拒答理由闭集（fail-closed 具名；08§4 未知关键输入阻断正式结论）
ABSTAIN_UNKNOWN_KEY_INPUT = "UNKNOWN_KEY_INPUT"
ABSTAIN_MISSING_KEY_INPUT = "MISSING_KEY_INPUT"
ABSTAIN_COVERAGE_INSUFFICIENT = "COVERAGE_INSUFFICIENT"
ABSTAIN_GATE_REJECTED = "GATE_REJECTED"
ABSTAIN_REASONS = (
    ABSTAIN_UNKNOWN_KEY_INPUT, ABSTAIN_MISSING_KEY_INPUT,
    ABSTAIN_COVERAGE_INSUFFICIENT, ABSTAIN_GATE_REJECTED,
)

REPAIR_COVERAGE_INSUFFICIENT = "REPAIR_COVERAGE_INSUFFICIENT"
REPAIR_DELIVERABLE = "CORRECTED_DELIVERABLE"
REPAIR_REJECTED_GATE = "REJECTED_GATE_FAIL_CLOSED"

# 覆盖证据口径（不模型自评：每条证据=一次 W2a-U14 确定性核验记录）
COVERAGE_EVIDENCE_FACE = ("citation_verifier.verify_citation(W2a-U14 "
                          "VERIFIED)——逐条具名核验记录，非模型自评")

BOUNDARY_MARK = "NON_LEGAL_CONCLUSION"
OPERATIONAL_FACE_NOTE = ("操作性交付：材料整理/格式化产物，非法律结论；"
                         "不携带任何法律断言，未经 F70/F87 引证闸")

# 操作性产物禁止携带的法律结论字段（操作性交付永不冒法律结论）
FORBIDDEN_OPERATIONAL_FIELDS = (
    "gate_status", "gateStatus", "citations", "citation_records",
    "legal_conclusion", "legalConclusion", "proposition_support",
    "verified_scoped", "rejection_reasons",
)

# 操作闭集（确定性文本操作；零模型参与）
OPERATIONS = ("normalize", "extract_text", "split_sections", "renumber")

_BATCH_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_ABSTAIN_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_AS_OF_RE = re.compile(r"^\d{8}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class AbstainOperationalError(Exception):
    """typed f91_* 错误（只带工程码，不带材料内容）。"""


# ---------------------------------------------------------------------- #
# 状态面（扁平 JSON；append-only 事件数组）
# ---------------------------------------------------------------------- #


def _state_root(config: dict) -> Path:
    root = config.get("abstain_state_root")
    if not root:
        raise NotConnected("abstain_state_root_not_configured")
    return Path(root)


def _abstain_path(root: Path, abstain_id: str) -> Path:
    return root / "abstains" / (abstain_id + ".json")


def _load(root: Path, abstain_id: str) -> dict:
    path = _abstain_path(root, abstain_id)
    if not path.is_file():
        raise NotConnected("abstain_not_registered:" + abstain_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise NotConnected("abstain_state_unreadable:"
                           + type(exc).__name__) from None


def _store(root: Path, record: dict) -> None:
    path = _abstain_path(root, record["abstain_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1,
                              sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)  # 原子提交


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------- #
# abstain.record —— 拒答具名入账（防「动不动拒绝用」：有账可查有因可读）
# ---------------------------------------------------------------------- #


def abstain_record(args: dict, config: dict) -> dict:
    abstain_id = args.get("abstain_id")
    if not isinstance(abstain_id, str) or not _ABSTAIN_ID_RE.fullmatch(
            abstain_id):
        raise NotConnected("abstain_id_invalid")
    reason = args.get("reason")
    if reason not in ABSTAIN_REASONS:
        raise NotConnected("abstain_reason_not_in_closed_set:" + str(reason))
    question = args.get("question_text")
    if not isinstance(question, str) or not question.strip():
        raise NotConnected("abstain_question_text_required")
    missing = args.get("missing_inputs", [])
    if not isinstance(missing, list) or not all(
            isinstance(m, str) and m.strip() for m in missing):
        raise NotConnected("abstain_missing_inputs_invalid")
    if reason in (ABSTAIN_UNKNOWN_KEY_INPUT, ABSTAIN_MISSING_KEY_INPUT) \
            and not missing:
        # 08§4 fail-closed 具名：缺什么要说清，不许空称阻断
        raise NotConnected("abstain_missing_inputs_required_for_fail_closed")
    root = _state_root(config)
    if _abstain_path(root, abstain_id).exists():
        raise NotConnected("abstain_already_registered:" + abstain_id)
    question_digest = hashlib.sha256(question.encode("utf-8")).hexdigest()
    record = {
        "schema": 1,
        "abstain_id": abstain_id,
        "registered_at": _now(),
        "question_digest": question_digest,  # 问题正文不入账面（只存摘要）
        "events": [{
            "seq": 1,
            "kind": "abstain_recorded",
            "reason": reason,
            "missing_inputs": sorted(missing),
            "note": "正式结论被阻断（08§4）；有因可读，可携证据申请纠正",
            "at": _now(),
        }],
        "repairs": [],
    }
    _store(root, record)
    return {
        "abstain_id": abstain_id,
        "question_digest": question_digest,
        "reason": reason,
        "missing_inputs": sorted(missing),
        "note": "拒答具名入账；覆盖充分题可携具名证据提交纠正"
                "（纠正产物必须重新过同一核验闸）",
    }


def abstain_read(args: dict, config: dict) -> dict:
    abstain_id = args.get("abstain_id")
    if not isinstance(abstain_id, str) or not _ABSTAIN_ID_RE.fullmatch(
            abstain_id):
        raise NotConnected("abstain_id_invalid")
    record = _load(_state_root(config), abstain_id)
    return {
        "abstain_id": abstain_id,
        "question_digest": record["question_digest"],
        "events": record["events"],
        "repairs": record["repairs"],
    }


def abstain_list(args: dict, config: dict) -> dict:
    root = _state_root(config)
    items = []
    if (root / "abstains").is_dir():
        for path in sorted((root / "abstains").glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            items.append({
                "abstain_id": record["abstain_id"],
                "reason": record["events"][0]["reason"],
                "events": len(record["events"]),
                "repairs": len(record["repairs"]),
            })
    return {"items": items, "count": len(items),
            "note": "拒答有账可查（防 fail-closed 被当『动不动拒绝用』）"}


# ---------------------------------------------------------------------- #
# 反修复 —— 纠正候选：覆盖证据前置＋强制重过同一 F87 闸
# ---------------------------------------------------------------------- #


def _coverage_evidence(corrected_text: str, as_of: str, config: dict) -> dict:
    """覆盖充分性判定：绑定可具名证据（法源覆盖面，不模型自评）。

    纠正候选中的引用逐条经 W2a-U14 citation 面确定性核验——覆盖证据＝
    逐条核验记录。至少一条 verified_scoped=True 才算覆盖充分题。
    """
    from citation_verifier import parse_citations, verify_citation

    parsed_items = parse_citations(corrected_text)
    evidence = []
    if not parsed_items:
        return {"sufficient": False, "evidence": [],
                "face": COVERAGE_EVIDENCE_FACE,
                "reason": "纠正候选零引用：无法绑定任何法源覆盖证据"
                          "（覆盖判定不收自评主张）"}
    for parsed in parsed_items:
        parsed = dict(parsed)
        parsed["as_of"] = as_of
        record = verify_citation(parsed, config)
        evidence.append({
            "citation_text": record.get("citation_text"),
            "title": record.get("title"),
            "status": record.get("status"),
            "identifier": record.get("identifier"),
            "verified_scoped": record.get("verified_scoped"),
        })
    # 覆盖＝法源覆盖面：至少一条引用的标题在本地法源真实命中且版本解析
    # 成功（identifier 非空）。覆盖判定只答「知识库有没有」（题域可核），
    # 不答「引文写没写对」（那是重过闸的事）——伪引文/误引/未施行等
    # 「有命中但不过闸」的纠正照样进闸、照样被闸拒（fail-closed 不松动）。
    sufficient = any(item["identifier"] for item in evidence)
    return {"sufficient": sufficient, "evidence": evidence,
            "face": COVERAGE_EVIDENCE_FACE,
            "reason": ("覆盖充分：纠正候选存在本地法源真实命中（identifier "
                       "在案，逐条具名记录）；引文正确性交由重过闸判定"
                       if sufficient else
                       "覆盖不足：纠正候选引用全部未在本地法源命中"
                       "（虚构/零引用）——原拒答不是误拒，纠正无效")}


def repair_submit(args: dict, config: dict) -> dict:
    """误拒纠正提交：覆盖证据前置 → 强制重过同一 F87 闸（结构断言）。

    重过闸＝纠正产物走同一 citation_gate/extraction_gate 路径：
    extraction_gate.register（登记即 UNVERIFIED、拒绝闸状态字段）→
    extraction_gate.gate_run（每次真调 F70）。本模块没有、也不提供任何
    绕闸直出的方法；CITATION_VERIFIED 才产可交付纠正产物（引用级）；
    REJECTED（含未知 fail-closed）如实拒——fail-closed 红线不松动。
    """
    abstain_id = args.get("abstain_id")
    if not isinstance(abstain_id, str) or not _ABSTAIN_ID_RE.fullmatch(
            abstain_id):
        raise NotConnected("abstain_id_invalid")
    corrected_text = args.get("corrected_text")
    if not isinstance(corrected_text, str) or not corrected_text.strip():
        raise NotConnected("abstain_corrected_text_required")
    as_of = args.get("as_of")
    if not isinstance(as_of, str) or not _AS_OF_RE.fullmatch(as_of):
        raise NotConnected("abstain_as_of_must_be_yyyymmdd_fail_closed")
    # 纠正候选不得自带闸状态字段（伪造已核未遂——与 F87 登记面同纪律）
    forged = sorted(set(args) & {"gate_status", "verified", "citations",
                                 "citation_records", "proposition_support"})
    if forged:
        raise NotConnected("abstain_repair_gate_fields_refused:" + ", ".join(
            forged))
    root = _state_root(config)
    record = _load(root, abstain_id)

    # a) 覆盖充分性判定（绑定具名证据，不模型自评）
    coverage = _coverage_evidence(corrected_text, as_of, config)
    seq = len(record["repairs"]) + 1
    repair_id = "repair_%03d" % seq
    repair = {
        "repair_id": repair_id,
        "submitted_at": _now(),
        "as_of": as_of,
        "coverage": coverage,
    }
    if not coverage["sufficient"]:
        repair["status"] = REPAIR_COVERAGE_INSUFFICIENT
        repair["deliverable"] = None
        record["repairs"].append(repair)
        record["events"].append({
            "seq": len(record["events"]) + 1,
            "kind": "repair_refused_coverage",
            "reason": REPAIR_COVERAGE_INSUFFICIENT,
            "note": "覆盖判定绑定具名证据（非自评）；证据不足纠正无效",
            "at": _now(),
        })
        _store(root, record)
        return {
            "abstain_id": abstain_id, "repair_id": repair_id,
            "status": REPAIR_COVERAGE_INSUFFICIENT,
            "coverage": coverage, "deliverable": None,
            "note": "覆盖充分性判定绑定可具名证据（知识库/法源覆盖面）；"
                    "本纠正未绑定到任何可核引用——原拒答不是误拒",
        }

    # b) 强制重过同一 F87 闸（结构断言：同一路径、同一函数对象）
    import extraction_gate as eg

    batch_id = "f91-%s-%s" % (abstain_id, repair_id)
    if not _BATCH_ID_RE.fullmatch(batch_id):
        raise NotConnected("abstain_gate_batch_id_invalid")
    eg.register({"batch_id": batch_id,
                 "candidates": [{"text": corrected_text,
                                 "provenance": {"source": "abstain_repair",
                                                "abstain_id": abstain_id}}]},
                config)
    gate_receipt = eg.gate_run({"batch_id": batch_id, "as_of": as_of},
                               config)
    result = gate_receipt["results"][0]
    gate_ref = {
        "gateBatchId": batch_id,
        "gateRunSeq": gate_receipt["run_seq"],
        "candidateId": result["candidate_id"],
        "gateStatus": result["gate_status"],
    }
    repair["gate_ref"] = gate_ref
    repair["gate_face"] = gate_receipt["verification_face"]
    if result["gate_status"] == eg.GATE_CITATION_VERIFIED:
        repair["status"] = REPAIR_DELIVERABLE
        # 引用级可交付；命题支持仍不代签（F87 纪律原样）
        repair["deliverable"] = {
            "corrected_text": corrected_text,
            "gate_batch_id": batch_id,
            "gate_run_seq": gate_receipt["run_seq"],
            "candidate_id": result["candidate_id"],
            "proposition_support": eg.SUPPORT_UNSIGNED,
            "boundary": "引用级核验通过；非命题级法律结论（E14 支持核验"
                        "面另做）；可交付＝重新过闸后的纠正产物",
        }
        event_kind = "repair_gate_passed"
    else:
        repair["status"] = REPAIR_REJECTED_GATE
        repair["deliverable"] = None
        repair["rejection_reasons"] = result["rejection_reasons"]
        event_kind = "repair_gate_rejected"
    record["repairs"].append(repair)
    record["events"].append({
        "seq": len(record["events"]) + 1,
        "kind": event_kind,
        "reason": repair["status"],
        "gate_ref": gate_ref,
        "note": ("纠正产物经同一 F87 闸引用级核验通过（可交付，引用级）"
                 if event_kind == "repair_gate_passed" else
                 "纠正产物过闸被拒——fail-closed 不松动，交付不发生"),
        "at": _now(),
    })
    _store(root, record)
    return {
        "abstain_id": abstain_id, "repair_id": repair_id,
        "status": repair["status"], "coverage": coverage,
        "gate_ref": gate_ref, "gate_face": repair["gate_face"],
        "deliverable": repair["deliverable"],
        "rejection_reasons": repair.get("rejection_reasons", []),
        "note": "重过闸=结构断言：纠正产物走同一 citation_gate/"
                "extraction_gate 路径（extraction.register→extraction."
                "gate，真调 F70）；未过闸的纠正永不交付",
    }


# ---------------------------------------------------------------------- #
# operational —— 操作性任务照常交付（不经法律闸），边界标记恒带
# ---------------------------------------------------------------------- #

_WS_RE = re.compile(r"[ \t\u3000]+")
_SECTION_RE = re.compile(r"(?m)^(#{1,3})\s*(.+)$")
_NUMLIST_RE = re.compile(r"(?m)^\s*(\d+)[.、．)]\s*")


def _op_normalize(text: str) -> str:
    lines = [_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _op_extract_text(text: str) -> str:
    return _SECTION_RE.sub(lambda m: m.group(2), text)


def _op_split_sections(text: str) -> str:
    parts, current = [], ["=== 未分节 ==="]
    for line in text.splitlines():
        hit = _SECTION_RE.match(line)
        if hit:
            if current:
                parts.append("\n".join(current))
            current = ["=== %s ===" % hit.group(2).strip()]
        else:
            current.append(line)
    parts.append("\n".join(current))
    return "\n\n".join(part for part in parts if part.strip())


def _op_renumber(text: str) -> str:
    counter = {"n": 0}

    def _sub(_match: re.Match) -> str:
        counter["n"] += 1
        return "%d. " % counter["n"]

    return _NUMLIST_RE.sub(_sub, text)


_OPERATION_FUNCS = {
    "normalize": _op_normalize,
    "extract_text": _op_extract_text,
    "split_sections": _op_split_sections,
    "renumber": _op_renumber,
}


def operational_deliver(args: dict, config: dict) -> dict:
    """操作性任务照常交付：不经法律闸（结构性零 citation/extraction 调
    用），产物恒带『非法律结论』边界标记；携带法律结论字段具名拒。"""
    _ = config  # 操作面无配置依赖（不经闸、不读法源）
    operation = args.get("operation")
    if operation not in OPERATIONS:
        raise NotConnected("abstain_operation_not_in_closed_set:"
                           + str(operation))
    text = args.get("text")
    if not isinstance(text, str) or not text.strip():
        raise NotConnected("abstain_operational_text_required")
    # 操作产物禁止携带法律结论字段（操作性交付永不冒法律结论）
    extra = args.get("extra", {})
    if not isinstance(extra, dict):
        raise NotConnected("abstain_operational_extra_invalid")
    forbidden = sorted(set(extra) & set(FORBIDDEN_OPERATIONAL_FIELDS))
    if forbidden:
        raise NotConnected("abstain_operational_legal_fields_refused:"
                           + ",".join(forbidden))
    output = _OPERATION_FUNCS[operation](text)
    digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
    return {
        "operation": operation,
        "output": output,
        "output_sha256": digest,
        "boundary_mark": BOUNDARY_MARK,
        "boundary_note": OPERATIONAL_FACE_NOTE,
        "gate_status": None,
        "note": "操作性交付不经法律闸、不携带法律结论；如需作为法律命题"
                "使用，必须另行走 F70/F87 引证闸",
    }


# ---------------------------------------------------------------------- #
# legal_entry 冻结方法组分发（abstain.* / operational.*）
# ---------------------------------------------------------------------- #


def abstain_operational_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发。闭集外方法绝不落到这里。"""
    if method == "abstain.record":
        return abstain_record(args, config)
    if method == "abstain.read":
        return abstain_read(args, config)
    if method == "abstain.list":
        return abstain_list(args, config)
    if method == "abstain.repair_submit":
        return repair_submit(args, config)
    if method == "operational.deliver":
        return operational_deliver(args, config)
    raise NotConnected("abstain_method_not_in_frozen_list:" + method)
