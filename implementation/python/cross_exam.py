# -*- coding: utf-8 -*-
"""F120 质证意见生成（W4-U51）——产品侧公开面。

义务 06:F120（v1.5；owner=product+harness；17 卡 P04,P01）：「质证意见
绑定证据和反方观点，律师可编辑终审；空证据不编质证」。证据→质证→报
告主链的中段（技能包形态）。生成＝**确定性装配**（绑定校验＋引用过
闸＋文书组装），不是模型自由生成——逐条主张必须绑证据 ref（harness
证据目录账在案证据）＋反方观点 ref（case_issues 真实争点行）；无 ref
的主张不生成（crossexam_claim_ref_required 结构断言）；空证据（目录
零行）不编质证（crossexam_empty_evidence 具名拒）＝acceptance 结构断
言。意见中的法条引用**过 F87 抽取闸**（extraction.register→
extraction.gate 同一路径；闸拒＝整单具名拒不静默丢主张）。律师编辑终
审＝harness 提案/人审合同（register_material→formal_propose
[channel=machine]→formal_decide accept/reject 必带真实决定引用）；作
者＝F53 作者策略闭集 lvyin-cross-exam（author 声明透传，不伪装律师）。

单一条流：

  输入主张集（逐条绑 evidence_id＋counter_issue_id）
    ├─ 空证据（evidence_list 零行）＝拒（不编质证）
    ├─ 逐主张绑定解析（证据在账；反方观点由 harness 账本解析校验）
    ├─ 引用检测（W2a-U14 parse_citations 确定性解析）→过闸主张
    │   extraction.register→extraction.gate（CITATION_VERIFIED 才放行）
    ├─ 意见 docx 纯 Python 生成（确定性；独立检查器四门）
    ├─ harness.register_material（意见文书入材料链，revision 1）
    ├─ F53 author.check（crossexam→lvyin-cross-exam；闭集外拒）
    ├─ harness.formal_propose（channel=machine；quotes=主张定位集）
    └─ harness.cross_exam_draft_record（账本半边：claims＋gateRef 落账）
  律师终审：crossexam.decide → harness.formal_decide
    （accept 带 resultBytesB64=律师编辑后字节 → canonical source=
    user_accept；reject=人说不）＋F53 三方投影可回读。

纪律（全部与既有面同基线）：确定性（零模型/零网络/零随机/零时钟入产
物）；fail-closed（typed error crossexam_*，错误码不携材料内容）；边
界如实——本面不做编辑器 UI（律师编辑=经 decide 的 resultBytesB64 回
流）；策略建议=position 闭集四性投影，不冒法律结论。
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import threading
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA = "juscite-f120-cross-exam/1"
STATE_SUBDIR = "cross-exam"

# 作者声明闭集通道（F53 author_policy；crossexam 为本单新增绑定）。
CROSSEXAM_CHANNEL = "crossexam"
CROSSEXAM_AUTHOR = "lvyin-cross-exam"

# 质证四性（position 闭集；与 harness 账本同集）。
POSITIONS = ("authenticity", "legality", "relevance", "proof_value")
POSITION_LABELS = {
    "authenticity": "真实性", "legality": "合法性",
    "relevance": "关联性", "proof_value": "证明力",
}

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_MATTER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_CLAIM_TEXT_MAX = 2000
_ZIP_HEAD_CHARS = 120

_LOCK = threading.Lock()

W_NS = _W_NS


class CrossExamError(ValueError):
    """Typed F120 face failure; str() is a code, never material content."""

    error_code = "crossexam_invalid"


def _fail(code: str) -> CrossExamError:
    return CrossExamError(code)


def _q(tag: str) -> str:
    return f"{{{_W_NS}}}{tag}"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def content_digest(docx_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        parts = [f"{info.filename}:{_sha256(zf.read(info.filename))}"
                 for info in zf.infolist()]
    return _sha256("\n".join(sorted(parts)).encode("utf-8"))


def _bridge_call(method: str, args: dict, config: dict) -> dict:
    """harness/闸公开面 seam（默认＝legal_entry.call 冻结方法组）。"""
    import legal_entry
    return legal_entry.call(method, args, config)


def _state_root(config: dict) -> Path:
    root = config.get("cross_exam_state_root")
    if not root:
        raise _fail("crossexam_state_root_not_configured")
    return Path(root)


def _atomic_write(path: Path, payload: bytes) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


def _next_output_dir(root: Path) -> Path:
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    seq = 1
    for entry in sorted(outputs.iterdir()):
        if entry.is_dir() and entry.name.isdigit():
            seq = max(seq, int(entry.name) + 1)
    out_dir = outputs / f"{seq:04d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _find_output(root: Path, request_id: str) -> Path | None:
    outputs = root / "outputs"
    if not outputs.is_dir():
        return None
    for entry in sorted(outputs.iterdir(), reverse=True):
        manifest = entry / "output.json"
        if not manifest.is_file():
            continue
        try:
            record = json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if record.get("request_id") == request_id:
            return entry
    return None


# ---------------------------------------------------------------------------
# 意见 docx 生成（纵向；纯 xml.etree；zip 时间戳钉定）
# ---------------------------------------------------------------------------


def _el(parent, tag: str, text: str | None = None, **attrs) -> ET.Element:
    node = ET.SubElement(parent, _q(tag)) if parent is not None \
        else ET.Element(_q(tag))
    for key, value in attrs.items():
        node.set(_q(key), value)
    if text is not None:
        node.text = text
    return node


def opinion_document_xml(title: str, matter_line: str,
                         sections: list[dict]) -> bytes:
    """意见文书 document.xml（sections 逐条＝绑定制主张；确定性）。"""
    document = ET.Element(_q("document"))
    body = _el(document, "body")

    def paragraph(text: str, bold: bool = False, center: bool = False,
                  size: int | None = None) -> None:
        p = _el(body, "p")
        p_pr = _el(p, "pPr")
        if center:
            _el(p_pr, "jc", val="center")
        run = _el(p, "r")
        r_pr = _el(run, "rPr")
        if bold:
            _el(r_pr, "b")
        if size:
            _el(r_pr, "sz", val=str(size))
        _el(run, "t", text)

    paragraph(title, bold=True, center=True, size=32)
    paragraph(matter_line)
    for order, section in enumerate(sections, 1):
        paragraph(f"{order}. {section['heading']}", bold=True)
        for line in section["lines"]:
            paragraph(line)
    sect = _el(body, "sectPr")
    _el(sect, "pgSz", w="11906", h="16838")
    _el(sect, "pgMar", top="1440", right="1440", bottom="1440", left="1440",
        header="0", footer="0", gutter="0")
    ET.register_namespace("w", _W_NS)
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' \
        + ET.tostring(document, encoding="utf-8", xml_declaration=False)


_FIXED_PARTS = {
    "[Content_Types].xml":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType="application/'
        '/vnd.openxmlformats-package.relationships+xml"/><Default '
        'Extension="xml" ContentType="application/xml"/><Override '
        'PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>",
    "_rels/.rels":
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/></Relationships>',
}


def package_docx(document_xml: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in sorted(_FIXED_PARTS):
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, _FIXED_PARTS[name].encode("utf-8"))
        info = zipfile.ZipInfo("word/document.xml", date_time=_ZIP_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        dst.writestr(info, document_xml)
    return out.getvalue()


# ---------------------------------------------------------------------------
# 独立检查器（python-docx/lxml 不同算路；四门）
# ---------------------------------------------------------------------------

_MARK_TAGS = {"ins", "del", "delText", "commentReference"}


def opinion_check(docx_bytes: bytes, expect: dict) -> dict:
    """四门：可打开/干净/绑定投影/确定性（两跑 digest 相等由调用方复）。"""
    try:
        import docx as pydocx
    except ImportError:
        raise _fail("crossexam_checker_unavailable") from None
    try:
        doc = pydocx.Document(io.BytesIO(docx_bytes))
    except Exception:
        raise _fail("crossexam_docx_unreadable") from None
    import lxml.etree as lxml_etree
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        names = set(zf.namelist())
        root = lxml_etree.fromstring(zf.read("word/document.xml"))
    failures = []
    texts = [p.text or "" for p in doc.paragraphs]
    if not texts or expect["title"] != texts[0]:
        failures.append("title")
    for want in expect["lines"]:
        if want not in texts:
            failures.append("projection:" + want[:24])
    marks = [el for el in root.iter()
             if (el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str)
                 and "}" in el.tag else el.tag) in _MARK_TAGS]
    if marks or any(n.startswith("word/comments") for n in names):
        failures.append("clean")
    if failures:
        raise _fail("crossexam_gate_failed:" + ",".join(failures[:6]))
    return {"checks": 4, "checker": "python-docx+lxml", "failures": []}


# ---------------------------------------------------------------------------
# 生成（绑定校验→引用过闸→文书→材料链→提案→账本）
# ---------------------------------------------------------------------------


def _validate_claim_inputs(raw_claims) -> list[dict]:
    if not isinstance(raw_claims, list) or not raw_claims:
        # 空主张输入＝没有可绑定内容，不编质证（结构断言）。
        raise _fail("crossexam_claims_empty")
    if len(raw_claims) > 200:
        raise _fail("crossexam_claims_too_many")
    prepared = []
    for offset, item in enumerate(raw_claims):
        if not isinstance(item, dict):
            raise _fail("crossexam_claim_invalid:%d" % offset)
        claim_id = item.get("claim_id")
        evidence_id = item.get("evidence_id")
        counter_issue_id = item.get("counter_issue_id")
        # 无 ref 的主张不生成（结构断言——质证必须绑证据＋反方观点）。
        if not isinstance(claim_id, str) or not _ID_RE.fullmatch(claim_id):
            raise _fail("crossexam_claim_id_invalid:%d" % offset)
        if not isinstance(evidence_id, str) or not evidence_id:
            raise _fail("crossexam_claim_ref_required:%s:evidence"
                        % claim_id)
        if not isinstance(counter_issue_id, str) or not counter_issue_id:
            raise _fail("crossexam_claim_ref_required:%s:counter" % claim_id)
        position = item.get("position")
        if position not in POSITIONS:
            raise _fail("crossexam_position_invalid:" + str(claim_id))
        text = item.get("text")
        if not isinstance(text, str) or not text.strip() \
                or len(text) > _CLAIM_TEXT_MAX:
            raise _fail("crossexam_claim_text_invalid:" + claim_id)
        prepared.append({
            "claimId": claim_id, "evidenceId": evidence_id,
            "counterIssueId": counter_issue_id, "position": position,
            "text": text,
        })
    ids = [c["claimId"] for c in prepared]
    if len(set(ids)) != len(ids):
        raise _fail("crossexam_claim_id_duplicate")
    return prepared


def generate(config: dict, args: dict) -> dict:
    """生成质证意见（绑定制；引用过 F87 闸；入材料链＋提案＋账本）。"""
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.fullmatch(matter_id):
        raise _fail("crossexam_matter_id_invalid")
    opinion_id = args.get("opinion_id")
    if not isinstance(opinion_id, str) or not _ID_RE.fullmatch(opinion_id):
        raise _fail("crossexam_opinion_id_invalid")
    request_id = args.get("request_id")
    if not isinstance(request_id, str) or not _ID_RE.fullmatch(request_id):
        raise _fail("crossexam_request_id_invalid")
    actor_id = args.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        raise _fail("crossexam_actor_required")
    as_of = args.get("as_of")
    if as_of is not None and (not isinstance(as_of, str)
                              or not re.fullmatch(r"\d{8}", as_of)):
        raise _fail("crossexam_as_of_invalid")
    scope = {"kind": "matter", "matterId": matter_id}

    with _LOCK:
        matter_root = _state_root(config) / STATE_SUBDIR / matter_id
        replay = _find_output(matter_root, request_id)
        if replay is not None:
            record = json.loads(
                (replay / "output.json").read_text(encoding="utf-8"))
            return {key: record[key] for key in
                    ("op", "request_id", "opinion_id", "material_id",
                     "proposal_id", "claims_recorded")}

        # 1) 空证据不编质证（目录零行＝具名拒，绝不产空意见）。
        listing = _bridge_call("harness.evidence_list", {"scope": scope},
                               config)
        evidence_rows = listing.get("items") or []
        if not evidence_rows:
            raise _fail("crossexam_empty_evidence_no_fabrication")

        # 2) 逐主张绑定校验＋证据解析（在账证据；无 ref 不生成）。
        claims = _validate_claim_inputs(args.get("claims"))
        evidence_head = {}
        for claim in claims:
            evidence_id = claim["evidenceId"]
            if evidence_id in evidence_head:
                continue
            try:
                evidence_head[evidence_id] = _bridge_call(
                    "harness.evidence_read",
                    {"scope": scope, "evidence_id": evidence_id}, config)
            except Exception as exc:
                code = str(exc)
                raise _fail("crossexam_evidence_unresolved:"
                            + code.split(":", 1)[0][:40]) from None

        # 3) 引用检测（确定性解析）→ 过闸主张强制 F87 闸。
        from citation_verifier import parse_citations
        gate_batch_id = "f120-" + opinion_id
        citing, plain = [], []
        for claim in claims:
            if parse_citations(claim["text"]):
                citing.append(claim)
            else:
                plain.append(claim)
        gate_refs: dict[str, dict] = {}
        if citing:
            if not as_of:
                # 引用主张必须给 as_of（效力时点 fail-closed，不猜）。
                raise _fail("crossexam_gate_as_of_required")
            _bridge_call("extraction.register", {
                "batch_id": gate_batch_id,
                "candidates": [
                    {"text": claim["text"],
                     "provenance": {"source": "cross_exam_claim",
                                    "opinion": opinion_id,
                                    "claim": claim["claimId"]}}
                    for claim in citing]}, config)
            gate_result = _bridge_call("extraction.gate", {
                "batch_id": gate_batch_id, "as_of": as_of}, config)
            gate_seq = gate_result.get("run_seq")
            by_candidate = {row["candidate_id"]: row
                            for row in gate_result.get("results") or []}
            for offset, claim in enumerate(citing, 1):
                candidate_id = "cand_%04d" % offset
                row = by_candidate.get(candidate_id)
                if row is None or row.get("gate_status") \
                        != "CITATION_VERIFIED":
                    # 闸拒＝整单具名拒（不静默丢主张、不降级收录）。
                    reasons = ",".join(sorted({
                        r.get("reason") or "UNKNOWN"
                        for r in (row or {}).get("rejection_reasons") or []}))
                    raise _fail("crossexam_gate_rejected:%s:%s"
                                % (claim["claimId"], reasons))
                gate_refs[claim["claimId"]] = {
                    "gateBatchId": gate_batch_id, "gateRunSeq": gate_seq,
                    "candidateId": candidate_id,
                    "gateStatus": "CITATION_VERIFIED"}

        # 4) 意见 docx 生成（确定性＋两跑同字节＋四门检查器）。
        sections = []
        ledger_claims = []
        for claim in claims:
            evidence = evidence_head[claim["evidenceId"]]
            heading = (f"质证意见（{POSITION_LABELS[claim['position']]}）"
                       f"——{evidence['evidenceNo']}")
            lines = [
                f"针对证据：{evidence['evidenceNo']}"
                f"（{evidence['name']}）",
                f"反方观点：issue {claim['counterIssueId']}（在案争点）",
                f"质证意见：{claim['text']}",
                "引用核验：" + ("已经 F87 抽取闸引用级核验"
                               if claim["claimId"] in gate_refs
                               else "本条不含法条引用"),
            ]
            sections.append({"heading": heading, "lines": lines})
            ledger_claims.append({
                "claimId": claim["claimId"],
                "evidenceRef": {"id": claim["evidenceId"],
                                "revision": evidence["revision"]},
                "counterRef": {"id": claim["counterIssueId"],
                               "revision": 1},
                "position": claim["position"], "text": claim["text"],
                "citesLaw": claim["claimId"] in gate_refs,
                "gateRef": gate_refs.get(claim["claimId"]),
            })
        title = f"质证意见（{opinion_id}）"
        matter_line = f"案件：{matter_id}"
        first = package_docx(opinion_document_xml(title, matter_line,
                                                  sections))
        second = package_docx(opinion_document_xml(title, matter_line,
                                                   sections))
        if content_digest(first) != content_digest(second):
            raise _fail("crossexam_determinism_violation")
        expect_lines = []
        for order, section in enumerate(sections, 1):
            # 文档内标题带序号前缀（opinion_document_xml 同构）；投影期望
            # 与文档同形（检查器独立解析路径逐行对账）。
            expect_lines.append(f"{order}. {section['heading']}")
            expect_lines.extend(section["lines"])
        gate = opinion_check(first, {"title": title, "lines": expect_lines})

        # 5) 材料链＋F53 作者闸＋提案＋账本（半边落账）。
        material = _bridge_call("harness.register_material", {
            "actor_id": actor_id, "scope": scope,
            "key": {"requestId": f"{request_id}:material", "targetId": None,
                    "expectedRevision": None, "inputRefs": []},
            "material": {"id": f"mat-cx-{opinion_id}", "kind": "office",
                         "title": title,
                         "bytesB64": base64.b64encode(first)
                         .decode("ascii")}}, config)
        from author_policy import check_revision_author
        binding = check_revision_author(CROSSEXAM_CHANNEL, CROSSEXAM_AUTHOR)
        proposal = _bridge_call("harness.formal_propose", {
            "actor_id": actor_id, "scope": scope,
            "key": {"requestId": f"{request_id}:proposal", "targetId": None,
                    "expectedRevision": None, "inputRefs": []},
            "proposal": {
                "proposalId": f"fp-cx-{opinion_id}",
                "materialId": material["ref"]["id"],
                "baseRevision": material["revision"],
                "bytesB64": base64.b64encode(first).decode("ascii"),
                "channel": "machine", "author": binding["author"],
                "quotes": [
                    {"text": claim["text"][:_ZIP_HEAD_CHARS],
                     "reason": f"质证主张绑定（{claim['position']}）",
                     "sourceRef": {"owner": "harness", "kind": "evidence",
                                   "id": claim["evidenceId"],
                                   "version": str(evidence_head[
                                       claim["evidenceId"]]["revision"]),
                                   "matterId": matter_id}}
                    for claim in claims],
                "note": None}}, config)
        draft_record = _bridge_call("harness.cross_exam_draft_record", {
            "actor_id": actor_id, "scope": scope,
            "key": {"requestId": f"{request_id}:draft", "targetId": None,
                    "expectedRevision": None, "inputRefs": []},
            "draft": {
                "opinionId": opinion_id, "claims": ledger_claims,
                "materialRef": {"materialId": material["ref"]["id"],
                                "revision": material["revision"]}}}, config)

        out_dir = _next_output_dir(matter_root)
        _atomic_write(out_dir / "opinion.docx", first)
        record = {
            "schema": SCHEMA, "op": "crossexam.generate",
            "request_id": request_id, "matter_id": matter_id,
            "opinion_id": opinion_id,
            "material_id": material["ref"]["id"],
            "material_revision": material["revision"],
            "proposal_id": proposal["proposal"]["proposalId"],
            "claims_recorded": draft_record.get("claimCount"),
            "docx_sha256": _sha256(first),
            "content_digest": content_digest(first),
            "author": binding["author"], "gate": gate,
            "outputs_dir": str(out_dir),
        }
        _atomic_write(out_dir / "output.json",
                      json.dumps(record, ensure_ascii=False,
                                 indent=1).encode("utf-8"))
        return {key: record[key] for key in
                ("op", "request_id", "opinion_id", "material_id",
                 "proposal_id", "claims_recorded")}


def decide(config: dict, args: dict) -> dict:
    """律师终审（透传 harness.formal_decide；accept 必带编辑后字节，
    reject＝人说不；决定引用必带——空决定面 harness 具名拒）。"""
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.fullmatch(matter_id):
        raise _fail("crossexam_matter_id_invalid")
    request_id = args.get("request_id")
    if not isinstance(request_id, str) or not _ID_RE.fullmatch(request_id):
        raise _fail("crossexam_request_id_invalid")
    actor_id = args.get("actor_id")
    if not isinstance(actor_id, str) or not actor_id:
        raise _fail("crossexam_actor_required")
    proposal_id = args.get("proposal_id")
    if not isinstance(proposal_id, str) or not _ID_RE.fullmatch(proposal_id):
        raise _fail("crossexam_proposal_id_invalid")
    material_id = args.get("material_id")
    if not isinstance(material_id, str) or not material_id:
        raise _fail("crossexam_material_id_required")
    action = args.get("action")
    if action not in ("accept", "reject"):
        raise _fail("crossexam_action_invalid")
    # FORMAL_DECIDE_FIELDS 闭集（proposalId/action/reasonRef/receiptRef/
    # resultBytesB64）——materialId 只作调用方核对面，不进决定载荷。
    payload = {
        "proposalId": proposal_id,
        "action": action,
        "reasonRef": args.get("reason_ref"),
        "receiptRef": args.get("receipt_ref"),
    }
    if payload["reasonRef"] is None or payload["receiptRef"] is None:
        # 律师决定必带真实决定引用（F53 投影面同规则；harness 同拒）。
        raise _fail("crossexam_decision_ref_required")
    if action == "accept":
        result_b64 = args.get("result_bytes_b64")
        if not isinstance(result_b64, str) or not result_b64:
            # accept＝律师编辑终审回流（edited bytes）——空字节＝未审。
            raise _fail("crossexam_result_bytes_required")
        payload["resultBytesB64"] = result_b64
    return _bridge_call("harness.formal_decide", {
        "actor_id": actor_id,
        "scope": {"kind": "matter", "matterId": matter_id},
        "key": {"requestId": request_id, "targetId": None,
                "expectedRevision": None, "inputRefs": []},
        "decision": payload}, config)


def read(config: dict, args: dict) -> dict:
    """回读：账本 draft＋F53 三方投影（决定引用↔author↔channel）。"""
    matter_id = args.get("matter_id")
    if not isinstance(matter_id, str) or not _MATTER_RE.fullmatch(matter_id):
        raise _fail("crossexam_matter_id_invalid")
    opinion_id = args.get("opinion_id")
    if not isinstance(opinion_id, str) or not _ID_RE.fullmatch(opinion_id):
        raise _fail("crossexam_opinion_id_invalid")
    scope = {"kind": "matter", "matterId": matter_id}
    draft = _bridge_call("harness.cross_exam_read",
                         {"scope": scope, "opinion_id": opinion_id}, config)
    material_id = draft["materialRef"]["materialId"]
    from author_policy import decision_projection
    listing = _bridge_call("harness.formal_proposal_list",
                           {"scope": scope, "material_id": material_id},
                           config)
    projection = decision_projection(listing, matter_id, material_id)
    return {"op": "crossexam.read", "matter_id": matter_id,
            "opinion_id": opinion_id, "draft": draft,
            "author_decision_projection": projection}


def cross_exam_call(method: str, args: dict, config: dict) -> dict:
    """legal_entry 冻结方法组分发（crossexam.*）。未列方法绝不落到这里。"""
    if method == "crossexam.generate":
        return generate(config, args)
    if method == "crossexam.decide":
        return decide(config, args)
    if method == "crossexam.read":
        return read(config, args)
    raise CrossExamError("crossexam_method_unknown:" + method)
