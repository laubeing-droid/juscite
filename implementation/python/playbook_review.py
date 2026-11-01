# -*- coding: utf-8 -*-
"""F90 规则集/Playbook 审查（W4-U45；06:F90 F90-desktop/F90-selfhost 双实例）。

06:F90 assertion「按固定 playbook 逐条风险/依据/偏差核；候选规则不直接
做事实」＋17 卡（owner=manuals+product+jc；entries P04/P01；target＝JC
compiler_core/client.py 公开 owner 扩展及真实规则包；UI 仅调用/展示，
本面不建 UI）。

分工红线：固定 playbook 审查程序与真实规则包的唯一权威在 JC
（compiler_core.playbook_review，playbook-review/1；权威期待只从
W2b-U19 冻结规则包导入，官方 locator+retrieved 随包携带；独立 checker
compiler_core.playbook_checker 不同算路复核，不同意不盖章）。本面是
产品桥＋候选账，不造第二审查权威：

* playbook.registry / playbook.review＝P01 JCClient 同一钉定公开面只读
  转录（回执逐字转录：逐条 risk/basis/deviation 三元行钉规则版本
  locator＋retrieved；NOT_CHECKED 行留存 unknown；封章＝checker 同意，
  不同意＝JC typed 拒原样上浮，绝不代签）；
* 候选账＝E15 path_candidates 窄字段闭集同构：review 回执的 candidates
  块自动入候选账（窄投影＋回执溯源），候选行携任何 verdict 形字段具名
  拒（playbook_candidate_field_not_closed）；候选→事实链唯一通道＝
  playbook.adopt 显式 decide（adopt|reject 必带 decisionRef；同内容
  幂等重放、异决定 conflict 具名拒）；采纳本身不产生任何判定——采纳
  规则要携带判定仍须经一次封章 playbook.review（回执 note 具名申明）；
* playbook.deviations_record＝P04 leg：封章回执的偏差行（value/basis）
  与 NOT_CHECKED 行（REVIEW_REQUIRED）经 harness.record_deviation 落
  harness 偏差账（observation_ref 钉 jc 回执 ref＋行号；deterministic
  requestId＝重放安全）；零偏差回执如实 recorded=[] 不造偏差。

金额/费率全程 integer minor＋十进制定点文本（float 一律 JC 侧具名拒，
桥不转手不兜底）；缺 jc/harness/playbook 状态根配置＝NOT_CONNECTED
（exit 3）；JC typed 拒＝JC_FAILURE 携码（exit 4）；harness 账面错＝
HarnessCommandError（exit 1）。无时钟入账（同输入同回执字节）。

全部材料为工程合成样本；oc28/%APPDATA% 零触碰；不 push。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from bridge_errors import HarnessCommandError, NotConnected

PROCEDURE_VERSION = "playbook-review/1"

# 候选账窄字段闭集（E15 同构）：候选行只许这些字段，一字不扩。
CANDIDATE_LEDGER_FIELDS = ("candidate_id", "playbook_id", "playbook_version",
                           "entry_id", "claim", "status", "candidate_reason",
                           "receipt_digest", "review_ref")
# 会把判定偷渡上候选的形状字段——先于一般闭集检查具名拒。
VERDICT_SHAPED_FIELDS = ("risk", "basis", "deviation", "deviations",
                         "certified", "verdict", "check", "claimed_source")
DECISIONS = ("adopt", "reject")
DECISION_FIELDS = ("candidate_id", "decision", "decision_ref")


def _state_root(config: dict) -> Path:
    root = config.get("playbook_state_root")
    if not root:
        raise NotConnected("playbook_state_root_not_configured")
    return Path(root)


def _candidates_path(root: Path) -> Path:
    return root / "playbook" / "candidates.jsonl"


def _reviews_dir(root: Path) -> Path:
    return root / "playbook" / "reviews"


def _load_candidates(root: Path) -> list:
    path = _candidates_path(root)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _append_ledger(root: Path, row: dict) -> None:
    path = _candidates_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _store_review(root: Path, review: dict) -> None:
    digest = review["review_digest"]
    path = _reviews_dir(root) / (digest + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        stored = json.loads(path.read_text(encoding="utf-8"))
        if stored == review:
            return  # 同内容幂等（append-only 纪律：绝不重写）
        raise NotConnected("playbook_review_digest_conflict:" + digest)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(review, ensure_ascii=False, sort_keys=True, indent=1),
                   encoding="utf-8")
    os.replace(tmp, path)  # 原子提交：中断不留半写状态


def _load_review(root: Path, review_id: str) -> dict:
    path = _reviews_dir(root) / (review_id + ".json")
    if not path.is_file():
        raise NotConnected("playbook_review_not_found:" + review_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise NotConnected("playbook_state_unreadable:"
                           + type(exc).__name__) from None


def _candidate_id(playbook_id: str, playbook_version: str,
                  entry_id: str, receipt_digest: str) -> str:
    canonical = json.dumps(
        {"playbookId": playbook_id, "playbookVersion": playbook_version,
         "entryId": entry_id, "receiptDigest": receipt_digest},
        sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "cand-" + hashlib.sha256(canonical).hexdigest()[:24]


def _review_digest(receipt: dict) -> str:
    canonical = json.dumps(receipt, sort_keys=True, ensure_ascii=False,
                           default=str).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


# ---------------------------------------------------------------------- #
# 方法面
# ---------------------------------------------------------------------- #


def registry(args: dict, config: dict) -> dict:
    """playbook.registry＝固定审查程序冻结文档（P01 只读转录）。"""
    from legal_entry import _jc, _jc_client

    client = _jc_client(config)
    doc = _jc(client.playbook_review_registry)
    if doc.get("registry_version") != PROCEDURE_VERSION:
        raise NotConnected("playbook_procedure_version_drift:"
                           + str(doc.get("registry_version")))
    return doc


def review(args: dict, config: dict) -> dict:
    """playbook.review＝一次封章审查（P01 转录＋候选自动入账）。

    回执（逐条 risk/basis/deviation＋locator 钉定＋NOT_CHECKED 留存＋
    inputDigest/input result refs 配对）逐字转录；candidates 块按窄投影
    自动记入候选账（同回执幂等）。JC checker 不同意＝typed 拒上浮，
    绝不产出未封章回执。
    """
    from legal_entry import _jc, _jc_client

    root = _state_root(config)
    playbook_id = args.get("playbook_id") or args.get("playbookId")
    playbook_version = args.get("playbook_version") or args.get("playbookVersion")
    entries = args.get("entries")
    if not isinstance(playbook_id, str) or not playbook_id.strip():
        raise NotConnected("playbook_id_required")
    if not isinstance(playbook_version, str) or not playbook_version.strip():
        raise NotConnected("playbook_version_required")
    if not isinstance(entries, list) or not entries:
        raise NotConnected("playbook_entries_required")
    matter_id = str(args.get("matter_id") or args.get("matterId") or "unscoped")
    client = _jc_client(config)
    receipt = _jc(lambda: client.review_playbook({
        "matterId": matter_id,
        "playbookId": playbook_id,
        "playbookVersion": playbook_version,
        "entries": entries,
    }))
    review_ref = receipt.get("playbookReviewRef") or {}
    if review_ref.get("owner") != "jc" or not review_ref.get("digest"):
        raise NotConnected("playbook_review_ref_missing")
    digest = _review_digest(receipt)
    stored = {
        "review_digest": digest,
        "playbook_id": playbook_id,
        "playbook_version": playbook_version,
        "matter_id": matter_id,
        "input_digest": receipt.get("inputDigest"),
        "sealed": receipt.get("sealed") is True,
        "review_ref": review_ref,
        "counts": receipt.get("counts"),
        "receipt": receipt,
    }
    if stored["sealed"] is not True:
        raise NotConnected("playbook_receipt_unsealed")  # 桥不收未封章回执
    _store_review(root, stored)

    recorded = []
    for candidate in receipt.get("candidates") or []:
        recorded.append(_record_candidate(root, candidate, playbook_id,
                                          playbook_version, digest, review_ref))
    return {"receipt": receipt,
            "reviewDigest": digest,
            "reviewId": digest,
            "reviewRef": review_ref,
            "candidateLedger": {"recorded": recorded,
                                "ledger": "juscite-f90-candidates/1"}}


def _record_candidate(root: Path, candidate: dict, playbook_id: str,
                      playbook_version: str, receipt_digest: str,
                      review_ref: dict) -> dict:
    """候选行入账（窄字段闭集；verdict 形字段先具名拒——E15 同构）。"""
    for field in VERDICT_SHAPED_FIELDS:
        if field in candidate:
            raise NotConnected("playbook_candidate_field_not_closed:" + field)
    entry_id = candidate.get("entryId")
    claim = candidate.get("claim")
    if not isinstance(entry_id, str) or not entry_id.strip():
        raise NotConnected("playbook_candidate_entry_id_required")
    if not isinstance(claim, str) or not claim.strip():
        raise NotConnected("playbook_candidate_claim_required")
    cid = _candidate_id(playbook_id, playbook_version, entry_id, receipt_digest)
    existing = {row.get("candidate_id") for row in _load_candidates(root)}
    if cid in existing:
        return {"candidateId": cid, "entryId": entry_id, "recorded": False}
    row = {
        "candidate_id": cid,
        "playbook_id": playbook_id,
        "playbook_version": playbook_version,
        "entry_id": entry_id,
        "claim": claim,
        "status": "candidate",
        "receipt_digest": receipt_digest,
        "review_ref": {"owner": review_ref.get("owner"),
                       "kind": review_ref.get("kind"),
                       "id": review_ref.get("id"),
                       "digest": review_ref.get("digest")},
    }
    reason = candidate.get("candidateReason")
    if reason is not None:
        row["candidate_reason"] = reason
    if set(row) - set(CANDIDATE_LEDGER_FIELDS):
        raise NotConnected("playbook_candidate_field_not_closed")
    _append_ledger(root, row)
    return {"candidateId": cid, "entryId": entry_id, "recorded": True}


def candidates(args: dict, config: dict) -> dict:
    """playbook.candidates＝候选账只读投影（决定折叠末条）。"""
    root = _state_root(config)
    rows = [row for row in _load_candidates(root)
            if row.get("record") != "decision"]
    decisions = {}
    for row in _load_candidates(root):
        if row.get("record") == "decision":
            decisions[row["candidate_id"]] = row
    projection = []
    for row in rows:
        cid = row["candidate_id"]
        decision = decisions.get(cid)
        view = {
            "candidateId": cid,
            "playbookId": row["playbook_id"],
            "playbookVersion": row["playbook_version"],
            "entryId": row["entry_id"],
            "claim": row["claim"],
            "status": "candidate",
            "receiptDigest": row["receipt_digest"],
            "reviewRef": row.get("review_ref"),
        }
        if row.get("candidate_reason") is not None:
            view["candidateReason"] = row["candidate_reason"]
        if decision is not None:
            view["status"] = ("adopted" if decision["decision"] == "adopt"
                              else "rejected")
            view["decisionRef"] = decision.get("decision_ref")
            view["note"] = decision.get("note")
        projection.append(view)
    counts = {
        "total": len(projection),
        "pending": sum(1 for v in projection if v["status"] == "candidate"),
        "adopted": sum(1 for v in projection if v["status"] == "adopted"),
        "rejected": sum(1 for v in projection if v["status"] == "rejected"),
    }
    return {"schema": "juscite-f90-candidates/1",
            "candidates": projection, "counts": counts}


def adopt(args: dict, config: dict) -> dict:
    """playbook.adopt＝候选→工作集唯一通道（显式 decide，E15 同构）。

    adopt|reject 必带 decisionRef（无引用不签决定）；同内容幂等重放；
    已决定候选异决定＝conflict 具名拒。采纳本身零判定语义——采纳规则
    携带 risk/basis/deviation 仍须经一次封章 playbook.review（note 具名）。
    """
    root = _state_root(config)
    cid = args.get("candidate_id") or args.get("candidateId")
    decision = args.get("decision")
    decision_ref = args.get("decision_ref") or args.get("decisionRef")
    if cid is None:
        raise NotConnected("playbook_decision_field_missing:candidate_id")
    if decision is None:
        raise NotConnected("playbook_decision_field_missing:decision")
    if decision not in DECISIONS:
        raise NotConnected("playbook_decision_invalid:" + str(decision))
    if not isinstance(decision_ref, (str, dict)) or not decision_ref:
        raise NotConnected("playbook_decision_ref_required")
    rows = _load_candidates(root)
    target = None
    for row in rows:
        if row.get("candidate_id") == cid and row.get("record") != "decision":
            target = row
    if target is None:
        raise NotConnected("playbook_candidate_not_found:" + str(cid))
    prior = None
    for row in rows:
        if row.get("record") == "decision" and row.get("candidate_id") == cid:
            prior = row
    if prior is not None:
        if (prior.get("decision") == decision
                and prior.get("decision_ref") == decision_ref):
            return _decision_receipt(cid, decision, prior.get("digest"),
                                     replay=True)
        raise NotConnected("playbook_decision_conflict:" + str(cid))
    canonical = json.dumps(
        {"candidateId": cid, "decision": decision,
         "decisionRef": decision_ref},
        sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    _append_ledger(root, {
        "record": "decision",
        "candidate_id": cid,
        "decision": decision,
        "decision_ref": decision_ref,
        "digest": digest,
        "note": ("adopted_rule_not_a_verdict: verdicts come solely from a "
                 "sealed playbook.review (locator-bound, checker-sealed)"),
    })
    return _decision_receipt(cid, decision, digest, replay=False)


def _decision_receipt(cid: str, decision: str, digest: str, replay: bool) -> dict:
    return {"candidateId": cid, "decision": decision,
            "decisionDigest": digest, "replay": replay,
            "note": ("adopted_rule_not_a_verdict: verdicts come solely from "
                     "a sealed playbook.review") if decision == "adopt" else
                    ("candidate_rejected: stays out of the working playbook "
                     "set; never a fact")}


def deviations_record(args: dict, config: dict) -> dict:
    """playbook.deviations_record＝P04 leg（harness.record_deviation）。

    封章回执的偏差行（value/basis）与 NOT_CHECKED 行（REVIEW_REQUIRED）
    逐行落 harness 偏差账；observation_ref 钉 jc 回执 ref＋行 entryId；
    deterministic requestId＝同回执重放安全（CommandKey 幂等）。零偏差
    回执如实 recorded=[]，绝不造偏差。
    """
    root = _state_root(config)
    review_id = args.get("review_id") or args.get("reviewId")
    if not isinstance(review_id, str) or not review_id.strip():
        raise NotConnected("playbook_review_id_required")
    stored = _load_review(root, review_id)
    receipt = stored["receipt"]
    review_ref = stored["review_ref"]
    matter_id = stored.get("matter_id") or "unscoped"
    digest = stored["review_digest"]
    rows_to_record = []
    for row in receipt.get("reviews") or []:
        if row.get("deviations"):
            rows_to_record.append(
                (row["entryId"], "deviation",
                 [d.get("kind") for d in row["deviations"]],
                 row.get("risk", {}).get("level")))
        elif row.get("verdictSource") == "not_checked":
            rows_to_record.append(
                (row["entryId"], "not_checked", ["REVIEW_REQUIRED"],
                 row.get("risk", {}).get("level")))
    recorded = []
    for index, (entry_id, kind, deviation_kinds, risk_level) in \
            enumerate(rows_to_record):
        observation_ref = {
            "owner": review_ref.get("owner"),
            "kind": "playbook-review",
            "id": review_ref.get("id"),
            "version": "1",
            "matterId": matter_id,
            "digest": review_ref.get("digest"),
            "row": entry_id,
            "reviewDigest": digest,
        }
        # requestId 全程 ≤24 字符且索引在前（harness deviationId 取
        # requestId[:24]，索引被截断＝多行偏差撞同一 dev id、冲突丢弃）。
        request_id = f"pbook-{index:02d}-{digest[:16]}"
        result = legal_entry_call(
            "harness.record_deviation",
            {"actor_id": "lvyin-playbook-bridge",
             "scope": {"kind": "matter", "matterId": matter_id},
             "key": {"requestId": request_id, "targetId": None,
                     "expectedRevision": None, "inputRefs": []},
             "observation_ref": observation_ref},
            config)
        deviation_ref = (result or {}).get("ref") or {}
        recorded.append({"entryId": entry_id, "kind": kind,
                         "deviationKinds": deviation_kinds,
                         "riskLevel": risk_level,
                         "deviationRef": deviation_ref})
    return {"schema": "juscite-f90-deviations/1",
            "reviewId": digest,
            "recorded": recorded,
            "counts": {"recorded": len(recorded)}}


def legal_entry_call(method: str, args: dict, config: dict) -> dict:
    """经 legal_entry 冻结方法组走 harness provider dispatch（P04 面）。

    独立间接层（产品面不 import legal_entry 顶层符号以避免循环导入；
    测试以本模块属性替换做 seam）。
    """
    import legal_entry
    return legal_entry.call(method, args, config)


def playbook_call(method: str, args: dict, config: dict) -> dict:
    """playbook.* 冻结方法组调度（legal_entry.call 分派进入口）。"""
    if not isinstance(args, dict):
        raise NotConnected("playbook_params_invalid")
    handlers = {
        "playbook.registry": registry,
        "playbook.review": review,
        "playbook.candidates": candidates,
        "playbook.adopt": adopt,
        "playbook.deviations_record": deviations_record,
    }
    if method not in handlers:
        raise NotConnected("playbook_method_unknown:" + method)
    return handlers[method](args, config)
