"""F62 法院来件 OCR 入库链产品面（W3-U14）。

06:F62「法院短信→附件提取→OCR→AI 阅读→律师确认入库」／acceptance「法院
来件附件 OCR 及送达候选人审入库；重复短信幂等」（17 卡：既有 command_tx
和 MatterStore/CAS 承接入库，事务幂等/版本；新场景字段在同 owner 扩不新
库）。本面＝链的产品半边编排，只复用既有权威面、不建第二引擎：

    短信登记（确定性解析＋附件 sha 钉定）
      → 入件跑批（复用 ocr.batch_*＝F41 公开面；引擎权威=F40 worker 钉
        定解释器 GPU fail-closed·模型 sha256 钉定·绝不运行时下载）
      → 阅读候选提取（正则确定性解析——LegalTech 约束 1：案号/文书分块
        严禁大模型模糊猜测；候选＝候选，人审确认前绝不入正式账＝E24
        纪律「送达事实不由上传日补」）
      → 律师逐候选确认/否决（append-only，翻案具名拒不静默改）
      → 入库（harness.register_material，F08 MatterStore/CAS；CommandKey
        按 (matter, sms_id, 内容 sha) 派生——重复短信全链幂等：短信账
        不重记、OCR 批不重跑（F41 登记 sha 幂等）、材料不重登（harness
        同 key 重放原回执））。

边界如实：06 卡链中的「AI 阅读」步在 v1 落为确定性结构化阅读（候选提
取）——模型辅助阅读不在 F62 acceptance 文本与本单验收命令内（模型轮次
纪律沿 §2.1 暂停账），如实挂边界不冒充；期限计算/程序提醒属 E21/F118/
E24 面零触（本面不产日程不发送外部动作）；原件字节不出 OCR 状态根域
（入库材料＝OCR 文本衍生物＋溯源，附件 PDF 原字节不入 harness CAS）；
E17 取证账零触（法院来件非律师取证）。

fail-closed 纪律（同 docx_edit/ocr_batch 先例）：状态根未配置＝
NOT_CONNECTED；业务级 typed 拒＝CourtInboundError（f62_* 码）；
HarnessCommandError 原样上浮。str() 只装错误码，材料内容永不进错误码。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

#: 入库材料种类闭集（harness MATERIAL_KINDS 子集，本面恒 scan）。
MATERIAL_KIND = "scan"

#: 送达候选类型闭集（确定性提取面）。v1＝案号候选——附件 OCR 行与短信
#: 文本内可确定性解析的法院案号；扩类型须同 owner 扩闭集不散落。
CANDIDATE_TYPES = ("case_number",)

#: 人审决定闭集。
REVIEW_DECISIONS = ("confirmed", "rejected")

_SMS_ID_RE = re.compile(r"\A[A-Za-z0-9._-]{1,80}\Z")
_MATTER_ID_RE = re.compile(r"\A[A-Za-z0-9._-]{1,80}\Z")
#: 案号确定性解析：全/半角括号年＋机关标识＋序号＋「号」。捕获整段匹配。
_CASE_NO_RE = re.compile(r"[（(]\s*20\d{2}\s*[）)][^号\s，。；、]{1,30}?号")

#: 入库派生文本的页行呈现上限（防护性外边界：单 SMS 附件数×页数×行数
#: 天然有界，此处只防病态输入撑爆派生材料）。
_MAX_ATTACHMENTS_PER_SMS = 20
_MAX_LINES_PER_DOC = 2000


class CourtInboundError(ValueError):
    """Typed F62 face failure; str() is a code, never material content."""


def _fail(code: str) -> CourtInboundError:
    return CourtInboundError(code)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(_canonical(obj))
    os.replace(tmp, path)                       # 原子落盘，不留半态


def _read_json(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _fail("f62_state_corrupt:" + path.name) from None


def _state_dir(config: dict, matter_id: str) -> Path:
    root = config.get("court_inbound_state_root")
    if not root:
        from bridge_errors import NotConnected
        raise NotConnected("f62_state_root_not_configured")
    if not isinstance(matter_id, str) or not _MATTER_ID_RE.match(matter_id):
        raise _fail("f62_matter_id_invalid")
    return Path(root) / "f62-inbound" / matter_id


def _require_sms_id(sms_id) -> str:
    if not isinstance(sms_id, str) or not _SMS_ID_RE.match(sms_id):
        raise _fail("f62_sms_id_invalid")
    return sms_id


def _bridge_call(config: dict):
    """缺省径＝legal_entry 封闭桥（ocr.*→anonymizer 公开面；
    harness.*→public_entry 子进程）。测试/recon 可注入 seam。"""
    import legal_entry

    def call(method: str, args: dict):
        return legal_entry.call(method, args, config)
    return call


# --------------------------------------------------------------- 短信登记
def _parse_sms_text(text: str) -> dict:
    """短信文本确定性解析（正则，无模型）：案号候选＋发件法院去壳。"""
    case_numbers = []
    for match in _CASE_NO_RE.finditer(text):
        value = match.group(0)
        norm = value.replace("(", "（").replace(")", "）").replace(" ", "")
        if norm not in case_numbers:
            case_numbers.append(norm)
    court = None
    shell = re.match(r"\A【([^】]{2,30})】", text or "")
    if shell:
        court = shell.group(1)
    return {"case_numbers": case_numbers, "court": court}


def sms_receive(state_root: Path, config: dict, args: dict,
                harness_call=None) -> dict:
    """登记一条法院来件短信（幂等=双层：短信 ID＋内容指纹）。

    同 id 同内容→重放（duplicate=true，不重记账）；同 id 异内容→
    f62_sms_id_content_conflict 具名拒（重号不同体＝事故或伪造，不静默
    并账）；同内容异 id（网关重发常换号）→去重回既有短信账
    （duplicate=true＋deduped_from），全链下游仍一条账。内容指纹不含
    sms_id 本身（sender+sent_at+text+清单 sha+附件钉定）。附件 sha256
    当场钉定，跑批前复验（变更=拒跑）。
    """
    del harness_call  # 纯登记无桥依赖；参数为 seam 对齐保留
    sms = args.get("sms")
    if not isinstance(sms, dict):
        raise _fail("f62_sms_payload_invalid")
    sms_id = _require_sms_id(sms.get("sms_id"))
    text = sms.get("text")
    sender = sms.get("sender")
    sent_at = sms.get("sent_at")
    if not isinstance(text, str) or not text.strip():
        raise _fail("f62_sms_text_invalid")
    if not isinstance(sender, str) or not sender.strip():
        raise _fail("f62_sms_sender_invalid")
    if not isinstance(sent_at, str) or not sent_at.strip():
        raise _fail("f62_sms_sent_at_invalid")
    raw_atts = sms.get("attachments")
    if not isinstance(raw_atts, list) or not raw_atts \
            or len(raw_atts) > _MAX_ATTACHMENTS_PER_SMS:
        raise _fail("f62_sms_attachments_invalid")
    corpus_root = sms.get("corpus_root")
    if not isinstance(corpus_root, str) or not corpus_root.strip():
        raise _fail("f62_corpus_root_invalid")
    corpus = Path(corpus_root)
    if not (corpus / "corpus_manifest.json").is_file():
        raise _fail("f62_corpus_manifest_missing")

    attachments = []
    for att in raw_atts:
        if not isinstance(att, dict):
            raise _fail("f62_sms_attachments_invalid")
        doc_id, rel = att.get("doc_id"), att.get("path")
        if not isinstance(doc_id, str) or not _SMS_ID_RE.match(doc_id):
            raise _fail("f62_attachment_doc_id_invalid")
        if not isinstance(rel, str) or not rel.strip():
            raise _fail("f62_attachment_path_invalid")
        resolved = (corpus.resolve() / rel).resolve()
        if not resolved.is_file() or corpus.resolve() not in resolved.parents:
            raise _fail("f62_attachment_missing:" + doc_id)
        data = resolved.read_bytes()
        attachments.append({"doc_id": doc_id, "path": rel,
                            "sha256": _sha256_bytes(data),
                            "bytes": len(data)})

    content_sha = _sha256_bytes(_canonical({
        "sender": sender, "sent_at": sent_at, "text": text,
        "corpus_root_sha": _sha256_bytes(
            (corpus / "corpus_manifest.json").read_bytes()),
        "attachments": attachments}))
    matter_dir = state_root

    def _replay(record: dict, deduped_from: str | None = None) -> dict:
        out = {k: record[k] for k in (
            "sms_id", "matter_id", "parsed", "attachments",
            "content_sha256", "received_at")}
        out["duplicate"] = True
        if deduped_from is not None:
            out["deduped_from"] = deduped_from
        return out

    record_path = matter_dir / f"sms-{sms_id}.json"
    existing = _read_json(record_path)
    if existing is not None:
        if existing.get("content_sha256") != content_sha:
            raise _fail("f62_sms_id_content_conflict")
        return _replay(existing)
    for path in sorted(matter_dir.glob("sms-*.json")):
        other = _read_json(path)
        if other and other.get("content_sha256") == content_sha:
            return _replay(other, deduped_from=sms_id)

    parsed = _parse_sms_text(text)
    record = {"sms_id": sms_id, "matter_id": args.get("matter_id"),
              "sender": sender, "sent_at": sent_at, "text_sha256":
              _sha256_bytes(text.encode("utf-8")),
              "corpus_root": str(corpus), "parsed": parsed,
              "attachments": attachments, "content_sha256": content_sha,
              "received_at": _now_iso()}
    _write_json(record_path, record)
    return dict(record, duplicate=False)


# --------------------------------------------------------------- 入件跑批
def _extract_candidates(doc_id: str, pages: list) -> list:
    """OCR 行→送达候选（正则确定性；候选带逐行溯源）。"""
    candidates, seen = [], set()
    for page in pages:
        page_no = page.get("page")
        for idx, line in enumerate(page.get("lines") or []):
            text = line.get("text") or ""
            conf = line.get("conf")
            for match in _CASE_NO_RE.finditer(text):
                value = match.group(0).replace(
                    "(", "（").replace(")", "）").replace(" ", "")
                key = (doc_id, page_no, idx, value)
                if key in seen:
                    continue
                seen.add(key)
                cid = "cand-" + _sha256_bytes(_canonical(
                    {"doc_id": doc_id, "page": page_no, "line": idx,
                     "type": "case_number", "value": value}))[:12]
                candidates.append({
                    "candidate_id": cid, "type": "case_number",
                    "value": value, "doc_id": doc_id, "page": page_no,
                    "line_index": idx, "conf": conf,
                    "source_text_sha256": _sha256_bytes(
                        text.encode("utf-8"))})
    return candidates


def inbound_run(state_root: Path, config: dict, args: dict,
                ocr_call=None) -> dict:
    """入件跑批：附件钉定复验→F41 登记真跑（幂等）→OCR 行→候选提取。

    幂等：同语料同批（F41 batch_id=清单 sha 派生）＋候选指纹一致→重放
    （duplicate=true）；候选指纹漂移→f62_run_digest_conflict（OCR 不确
    定性响亮暴露，不静默换账）。
    """
    if ocr_call is None:
        ocr_call = _bridge_call(config)
    matter_dir = state_root
    sms_id = _require_sms_id(args.get("sms_id"))
    sms = _read_json(matter_dir / f"sms-{sms_id}.json")
    if sms is None:
        raise _fail("f62_sms_not_received")
    corpus = Path(sms["corpus_root"])

    # 附件钉定复验（登记后变更=拒跑，原件只读红线）
    for att in sms["attachments"]:
        path = corpus / att["path"]
        if not path.is_file():
            raise _fail("f62_attachment_missing:" + att["doc_id"])
        if _sha256_bytes(path.read_bytes()) != att["sha256"]:
            raise _fail("f62_attachment_changed:" + att["doc_id"])

    registered = ocr_call("ocr.batch_register",
                          {"corpus_root": str(corpus), "min_doc_gap_s": 0.0})
    batch_id = registered["batch_id"]
    # F41 单运行器纪律：COMPLETED 批次拒绝重跑——登记幂等回执携带分母计数，
    # pending>0 才跑批（重复短信→同批登记幂等→零 pending→不重跑）。
    pending = (registered.get("counters") or {}).get("docs_pending")
    if pending is None or pending > 0:
        run_state = ocr_call("ocr.batch_run", {"batch_id": batch_id})
        if run_state.get("status") != "COMPLETED":
            raise _fail("f62_ocr_batch_incomplete:"
                        + str(run_state.get("status")))

    candidates, page_summaries, engine = [], [], None
    for att in sms["attachments"]:
        rec = ocr_call("ocr.batch_doc_version",
                       {"batch_id": batch_id, "doc_id": att["doc_id"]})
        doc = rec.get("doc") or {}
        engine = doc.get("engine") or engine
        pages = rec.get("pages") or []          # 页行记录在返回顶层（F41 面）
        if sum(len(p.get("lines") or []) for p in pages) > _MAX_LINES_PER_DOC:
            raise _fail("f62_doc_lines_overrun:" + att["doc_id"])
        extracted = _extract_candidates(att["doc_id"], pages)
        candidates.extend(extracted)
        page_summaries.append({
            "doc_id": att["doc_id"], "pages": len(pages),
            "lines": sum(len(p.get("lines") or []) for p in pages),
            "candidates": len(extracted),
            "error_pages": doc.get("error_pages")})
    candidates_sha = _sha256_bytes(_canonical(candidates))

    run_path = matter_dir / f"run-{sms_id}.json"
    existing = _read_json(run_path)
    if existing is not None:
        if existing.get("candidates_sha256") != candidates_sha:
            raise _fail("f62_run_digest_conflict")
        return {"sms_id": sms_id, "batch_id": existing["batch_id"],
                "engine": existing["engine"], "candidates":
                existing["candidates"], "candidates_sha256": candidates_sha,
                "pages": existing["pages"], "duplicate": True}
    run = {"sms_id": sms_id, "batch_id": batch_id, "engine": engine,
           "corpus_sha256": registered.get("corpus_sha256"),
           "candidates": candidates, "candidates_sha256": candidates_sha,
           "pages": page_summaries, "ran_at": _now_iso()}
    _write_json(run_path, run)
    return dict(run, duplicate=False)


# --------------------------------------------------------------- 人审确认
def candidate_review(state_root: Path, config: dict, args: dict) -> dict:
    """律师逐候选确认/否决（append-only；同候选翻案具名拒不静默改）。"""
    del config  # 纯状态根操作；参数为 seam 对齐保留
    matter_dir = state_root
    sms_id = _require_sms_id(args.get("sms_id"))
    run = _read_json(matter_dir / f"run-{sms_id}.json")
    if run is None:
        raise _fail("f62_run_not_found")
    reviewer = args.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise _fail("f62_reviewer_invalid")
    decisions = args.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise _fail("f62_review_decisions_invalid")
    known = {c["candidate_id"]: c for c in run["candidates"]}

    log_path = matter_dir / f"review-{sms_id}.json"
    log = _read_json(log_path) or {"sms_id": sms_id, "reviews": []}
    reviewed = {r["candidate_id"]: r for r in log["reviews"]}
    for decision in decisions:
        if not isinstance(decision, dict):
            raise _fail("f62_review_decisions_invalid")
        cid = decision.get("candidate_id")
        verdict = decision.get("decision")
        if cid not in known:
            raise _fail("f62_candidate_unknown")
        if verdict not in REVIEW_DECISIONS:
            raise _fail("f62_review_decision_invalid")
        prior = reviewed.get(cid)
        if prior is not None:
            if prior["decision"] == verdict:
                continue                      # 同候选同决定＝幂等重放
            raise _fail("f62_candidate_review_conflict")
        row = {"candidate_id": cid, "decision": verdict,
               "reviewer": reviewer, "reviewed_at": _now_iso(),
               "candidate_sha256": _sha256_bytes(_canonical(known[cid]))}
        log["reviews"].append(row)
        reviewed[cid] = row
    log["updated_at"] = _now_iso()
    _write_json(log_path, log)
    counts = {"confirmed": 0, "rejected": 0}
    for row in log["reviews"]:
        counts[row["decision"]] += 1
    counts["unreviewed"] = len(known) - len(log["reviews"])
    return {"sms_id": sms_id, "reviews": log["reviews"], "counts": counts}


# --------------------------------------------------------------- 入库
def _compile_intake_bytes(sms: dict, run: dict, reviews: list,
                          ocr_lines_by_doc: dict) -> bytes:
    """入库派生文本（确定性编译：同输入同字节）。附件 PDF 原字节不入
    harness CAS——入库材料＝OCR 文本衍生物＋逐行溯源＋人审账。"""
    out = ["法院来件入库材料（律引 F62 链·全合成测试材料）",
           f"matter: {sms['matter_id']}",
           f"sms_id: {sms['sms_id']}  sender: {sms['sender']}"
           f"  sent_at: {sms['sent_at']}",
           f"sms_content_sha256: {sms['content_sha256']}",
           f"ocr_batch: {run['batch_id']}  corpus_sha256:"
           f" {run.get('corpus_sha256')}",
           "",
           "== 附件 OCR 文本 =="]
    for att in sms["attachments"]:
        out.append(f"-- {att['doc_id']}（{att['path']}"
                   f" sha256={att['sha256'][:16]}…）")
        for page in ocr_lines_by_doc.get(att["doc_id"]) or []:
            out.append(f"  [p{page['page']}]")
            for idx, line in enumerate(page.get("lines") or []):
                out.append(f"  {idx:03d} conf={line.get('conf')}"
                           f" {line.get('text')}")
    out += ["", "== 送达候选（人审账）=="]
    review_by_id = {r["candidate_id"]: r for r in reviews}
    for cand in run["candidates"]:
        row = review_by_id.get(cand["candidate_id"])
        out.append(f"- {cand['candidate_id']} type={cand['type']}"
                   f" value={cand['value']} doc={cand['doc_id']}"
                   f" p{cand['page']}l{cand['line_index']}"
                   f" => {row['decision']} by {row['reviewer']}"
                   f" at {row['reviewed_at']}")
    out += ["", "== 边界 ==",
            "候选经律师人审确认；送达事实不由上传日自动补（E24）。"
            "本材料为 OCR 文本衍生物，附件原件字节不出 OCR 状态根域。"]
    return "\n".join(out).encode("utf-8")


def intake(state_root: Path, config: dict, args: dict,
           ocr_call=None, harness_call=None) -> dict:
    """律师确认后入库：harness.register_material（F08 MatterStore/CAS）。

    幂等键=CommandKey.requestId=f62-intake-<matter>-<sms>-<内容sha16>：
    同内容重入库→harness 同 key 重放原回执（材料不重登）；产品侧已有
    入库账→readback 校验后重放。全拒→f62_intake_no_confirmed_candidate
    （无候选确认＝律师认定非本案件来件，不入库）；有候选未审→
    f62_intake_unreviewed_candidates（人审不齐不入账）。
    """
    if ocr_call is None or harness_call is None:
        bridge = _bridge_call(config)
        ocr_call = ocr_call or bridge
        harness_call = harness_call or bridge
    matter_dir = state_root
    sms_id = _require_sms_id(args.get("sms_id"))
    sms = _read_json(matter_dir / f"sms-{sms_id}.json")
    run = _read_json(matter_dir / f"run-{sms_id}.json")
    review_log = _read_json(matter_dir / f"review-{sms_id}.json")
    if sms is None or run is None or review_log is None:
        raise _fail("f62_intake_chain_incomplete")
    known_ids = {c["candidate_id"] for c in run["candidates"]}
    reviewed_ids = {r["candidate_id"] for r in review_log["reviews"]}
    if known_ids - reviewed_ids:
        raise _fail("f62_intake_unreviewed_candidates")
    confirmed = [r for r in review_log["reviews"]
                 if r["decision"] == "confirmed"]
    if not confirmed:
        raise _fail("f62_intake_no_confirmed_candidate")

    ocr_lines_by_doc = {}
    for att in sms["attachments"]:
        rec = ocr_call("ocr.batch_doc_version",
                       {"batch_id": run["batch_id"],
                        "doc_id": att["doc_id"]})
        ocr_lines_by_doc[att["doc_id"]] = rec["pages"]
    content = _compile_intake_bytes(sms, run, review_log["reviews"],
                                    ocr_lines_by_doc)
    content_sha = _sha256_bytes(content)

    matter_id = sms["matter_id"]
    material_id = f"f62-{matter_id}-{sms_id}"
    request_id = f"f62-intake-{matter_id}-{sms_id}-{content_sha[:16]}"
    title = f"法院来件（{sms['parsed'].get('court') or sms['sender']}）{sms_id}"
    note = json.dumps({"f62": True, "batch_id": run["batch_id"],
                       "corpus_sha256": run.get("corpus_sha256"),
                       "candidates_sha256": run["candidates_sha256"],
                       "sms_content_sha256": sms["content_sha256"],
                       "intake_bytes_sha256": content_sha,
                       "confirmed": len(confirmed),
                       "rejected": len(review_log["reviews"])
                       - len(confirmed)},
                      ensure_ascii=False, sort_keys=True)
    intake_path = matter_dir / f"intake-{sms_id}.json"
    # 产品侧幂等在前：已有入库账→指纹一致重放（不重打桥）；不一致＝漂移
    # 具名拒。指纹不一致绝不先打桥（防止同 material_id 异内容二次登记）。
    existing = _read_json(intake_path)
    if existing is not None:
        if existing.get("intake_bytes_sha256") != content_sha:
            raise _fail("f62_intake_drift")
        return dict(existing, replayed=True)
    receipt = harness_call("harness.register_material", {
        "actor_id": args.get("actor_id") or "lvyin-court-inbound",
        "scope": {"kind": "matter", "matterId": matter_id},
        "key": {"requestId": request_id, "targetId": None,
                "expectedRevision": None, "inputRefs": []},
        "material": {"id": material_id, "kind": MATERIAL_KIND,
                     "title": title, "bytesB64":
                     base64.b64encode(content).decode("ascii"),
                     "note": note}})
    record = {"sms_id": sms_id, "matter_id": matter_id,
              "material_ref": receipt.get("ref"), "revision":
              receipt.get("revision"), "material_sha256":
              receipt.get("sha256"), "casRef": receipt.get("casRef"),
              "request_id": request_id, "intake_bytes_sha256": content_sha,
              "material_id": material_id, "intake_at": _now_iso()}
    _write_json(intake_path, record)
    return dict(record, replayed=False)


# --------------------------------------------------------------- 只读面
def read_inbound(state_root: Path, config: dict, args: dict) -> dict:
    del config
    matter_dir = state_root
    sms_id = _require_sms_id(args.get("sms_id"))
    projection = {"sms_id": sms_id}
    for key, prefix in (("sms", "sms"), ("run", "run"),
                        ("review", "review"), ("intake", "intake")):
        projection[key] = _read_json(
            matter_dir / f"{prefix}-{sms_id}.json")
    return projection


def list_inbound(state_root: Path, config: dict, args: dict) -> dict:
    del config
    prefix = "sms-"
    items = []
    for path in sorted(state_root.glob(prefix + "*.json")):
        sms_id = path.name[len(prefix):-len(".json")]
        record = _read_json(path) or {}
        intake_row = _read_json(state_root / f"intake-{sms_id}.json")
        items.append({"sms_id": sms_id,
                      "received_at": record.get("received_at"),
                      "court": (record.get("parsed") or {}).get("court"),
                      "intake_material_id":
                      (intake_row or {}).get("material_id")})
    return {"matter_id": args.get("matter_id"), "items": items}


_DISPATCH = {
    "court_inbound.sms_receive": sms_receive,
    "court_inbound.inbound_run": inbound_run,
    "court_inbound.candidate_review": candidate_review,
    "court_inbound.intake": intake,
    "court_inbound.read": read_inbound,
    "court_inbound.list": list_inbound,
}


def court_inbound_call(method: str, args: dict, config: dict, *,
                       ocr_call=None, harness_call=None) -> dict:
    """legal_entry court_inbound.* 唯一分发（fail-closed 同基线）。

    配置级缺状态根＝NOT_CONNECTED（同全桥纪律）；业务级 typed 拒＝
    CourtInboundError（f62_* 码）。入参形状在分发层统一把关。"""
    state_root = config.get("court_inbound_state_root")
    if not state_root:
        from bridge_errors import NotConnected
        raise NotConnected("f62_state_root_not_configured")
    if not isinstance(args, dict):
        raise NotConnected("court_inbound_params_invalid")
    handler = _DISPATCH.get(method)
    if handler is None:
        raise _fail("f62_method_unknown")
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_ID_RE.match(matter_id):
        raise _fail("f62_matter_id_invalid")
    matter_dir = _state_dir(config, matter_id)
    if method == "court_inbound.sms_receive":
        return handler(matter_dir, config, args,
                       harness_call=harness_call)
    if method == "court_inbound.inbound_run":
        return handler(matter_dir, config, args, ocr_call=ocr_call)
    if method == "court_inbound.intake":
        return handler(matter_dir, config, args, ocr_call=ocr_call,
                       harness_call=harness_call)
    return handler(matter_dir, config, args)
