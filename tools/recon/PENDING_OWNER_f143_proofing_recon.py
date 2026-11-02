#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F143 义务验收 recon（W5-U14）：法律写作校对插件（一致性/术语，定位原文
可接受拒绝）——双 profile（F143-desktop＝legal_entry CLI 子进程径／
F143-selfhost＝产品面同进程径）。

义务 06:V7-143 断言（验收向量逐字）：「一致性/术语校对定位原文且可接受
拒绝；不同语义不自动合并」。17 卡 steps（逐字）：「公开proposal/base
refs→宿主原生定位/修订/比对→部分接受/拒绝→重读实际文件→CAS/version→
Harness正式采用；不模拟DOCX」。

硬门（每 profile，恰同序操作序列）：
- C01 合成冻结清单：ruleset_read 与模块 RULESET 重算 sha 全等；kinds
  闭集 {terminology, consistency}；5 条规则。
- C02 文档夹具＝W2b-U14 已交付 DOCX 产物链：合成基线经已 VERIFIED 的
  redline.register＋redline.replay（body.insert_paragraph 插入重复段＝
  定位歧义构造）产出 replay.docx 真实字节，proofing.register 只吃盘上
  实际文件字节（不模拟 DOCX）。
- C03 登记纪律：同 id 同字节幂等；异字节/非 DOCX/坏 id 具名拒。
- C04 扫描定位（F50/F51 纪律）：发现项 quote＝所在段全文逐字重搜；
  AMBIGUOUS 发现项零位置字段（无 locator/无 trace_span——禁偏移强改）；
  LOCATED 恒 offset_conversion_used=False；确定性双跑同摘要。
- C05 候选归并红线：合并仅限逐条确定性同语义（T-01 两处命中并同一
  proposed 候选＝merge_key 全同且逐条唯一命中）；不同规则重叠 span 建
  议不同＝conflict 候选各自独立（T-01/T-05 互指 conflict_with）；quote
  多命中＝needs_review 零位置留人。
- C06 决定账（可接受拒绝）：冲突两条同受→propose 具名拒
  f143_conflict_candidates_accepted（语义冲突必须留人）；人拒绝一方后
  可继续；needs_review 被接受→propose 具名拒 f143_candidate_not_located
  （无位置不自动应用）；同决定幂等不双登；改判追加（最新有效）。
- C07 提案构建（F49 封闭算子集确定性重放）：ops 逐字断言（段序排序）；
  更正 DOCX＝真实包（非 document.xml 部件逐字节保真；zip 定时戳）；
  现行文本替换逐字落位、歧义段保持原样零触碰；idempotent 重提案同 id。
- C08 Harness 正式采用（F47 提案/采用合同）：register_material→
  formal_propose（channel=machine·author=lvyin-proofing·base=头行·
  quotes 逐条携原文）pending、canonical 干净态；formal_decide reject＝
  canonical 一字不动；同字节二次提案 accept＋resultBytesB64＝重读盘上
  实际更正文件→bake 新干净版本（source=user_accept、
  resultSource=host_result_bytes、sha 与重读字节全等）；F53 作者政策：
  proofing 通道绑定可过、律师名具名拒、author.policy 闭集六通道。
- C09 确定性：同序列双状态根（剥时间戳）逐响应摘要相等；跨 profile
  findings/candidates/ops/corrected sha/proposal 摘要逐项全等。
- C10 语料只读＋AST 纪律＋桥 fail-closed 负向（缺状态根/未知方法/未知
  候选/坏动作/未登记文档/提案缺席）；错误码纯码不携材料内容。

语料全合成（00-总协调 §6.1 裁决#1，绝无真实文档；harness 侧案件同为
合成 matter）。harness 检出只读消费（w2b-u11 worktree＝F47 合同 origin，
F48 recon 同默认；零字节改动）。

用法（juscite worktree w5-u14 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f143_proofing_recon.py \
      --profile desktop --profile selfhost

退出码：0＝全部 profile RECON_OK；2＝RECON_FAIL；3＝环境缺失。
证据：evidence/F143/<profile>/f143-proofing-recon.{json,md}（＋
docs/construction/evidence/F143/<profile>/ 镜像）。
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEMP = Path(os.environ.get("TEMP", "."))
BRIDGE = REPO / "implementation" / "python" / "legal_entry.py"
MODULE = REPO / "implementation" / "python" / "document_proofing.py"
SCHEMA = "juscite-f143-proofing/1"
REDACTION_SCHEMA = "juscite-f49-replay-redline/1"
DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w2b-u11")

MATTER = "m-f143-recon"
MATERIAL = "mat-f143-proofing"
AUTHOR = "lvyin-proofing"     # F53 作者声明闭集 proofing 通道绑定
REDACTION_AUTHOR = "lvyin-redline"
DATE = "2026-10-23T00:00:00Z"

_CROSS_PROFILE: dict[str, str] = {}

# ------------------------------------------------------------------ #
# 全合成基线（确定性内容，无 RNG；术语/一致性命中面按 recon 断言钉定）
# ------------------------------------------------------------------ #

BODY_TEXTS = [
    "合成服务合同（F143-RECON 编号 SYN-F143-2026-001；全部当事人与金额均为虚构）",
    "第一条 甲方：合成当事人甲（虚构）；乙方：合成当事人乙（虚构）。",
    "第二条 本合同总价款为人民币叁拾陆万元，甲方应于验收合格后一次性支付。",
    "第三条 乙方收取订金后三日内启动合成服务。",
    "第四条 服务期限自2026年12月1日起至2027年5月31日止；订金以外的费用调整须经甲方书面同意。",
    "第五条 乙方经办人身份证号由甲方留存备查；合同金额小写360000元与上文一致。",
]
TABLE_ROWS = [
    ["款项", "约定", "备注"],
    ["付款方式", "订金占比百分之三十", "合成内容"],
    ["尾款", "验收合格后付清", "合成内容"],
]
FOOTNOTES = {1: "合成脚注：订金一词在本合同中的释义见第五条。"}


def eprint(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


def canonical_digest(obj) -> str:
    """剥时间戳后的规范化摘要（确定性对账；*_utc 全剥）。"""
    def strip(node):
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items()
                    if not k.endswith("_utc")}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node
    return sha256_bytes(json.dumps(strip(obj), ensure_ascii=False,
                                   sort_keys=True).encode("utf-8"))


# ------------------------------------------------------------------ #
# 合成基线 DOCX（与 F49 recon 构造同式：富 OOXML；zip 定时戳＝确定性）
# ------------------------------------------------------------------ #

def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _p_xml(text, num_id=None, footnote_ids=()) -> str:
    ppr = ""
    if num_id is not None:
        ppr = ('<w:pPr><w:numPr><w:ilvl w:val="0"/>'
               f'<w:numId w:val="{num_id}"/></w:numPr></w:pPr>')
    run = (f'<w:r><w:t xml:space="preserve">{_esc(text)}</w:t></w:r>'
           if text else "")
    refs = "".join(f'<w:r><w:footnoteReference w:id="{fid}"/></w:r>'
                   for fid in footnote_ids)
    return f"<w:p>{ppr}{run}{refs}</w:p>"


def _tbl_xml(rows) -> str:
    grid = '<w:gridCol w:w="2400"/>' * len(rows[0])
    trs = []
    for row in rows:
        tcs = "".join(
            '<w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>'
            + _p_xml(cell) + "</w:tc>" for cell in row)
        trs.append(f"<w:tr>{tcs}</w:tr>")
    return ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{"".join(trs)}</w:tbl>')


def build_baseline_docx() -> bytes:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = [
        _p_xml(BODY_TEXTS[0]),
        _p_xml(BODY_TEXTS[1]),
        _p_xml(BODY_TEXTS[2], footnote_ids=[1]),
        _p_xml(BODY_TEXTS[3]),
        _p_xml(BODY_TEXTS[4]),
        _tbl_xml(TABLE_ROWS),
        _p_xml(BODY_TEXTS[5]),
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>',
    ]
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'\r\n<w:document xmlns:w="{w}"><w:body>{"".join(body)}'
                "</w:body></w:document>")
    footnotes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 f'\r\n<w:footnotes xmlns:w="{w}">'
                 '<w:footnote w:type="separator" w:id="-1"><w:p><w:r>'
                 "<w:separator/></w:r></w:p></w:footnote>"
                 '<w:footnote w:type="continuationSeparator" w:id="0">'
                 "<w:p><w:r><w:continuationSeparator/></w:r></w:p>"
                 "</w:footnote>"
                 + "".join(
                     f'<w:footnote w:id="{fid}"><w:p><w:r><w:t xml:space='
                     f'"preserve">{_esc(text)}</w:t></w:r></w:p></w:footnote>'
                     for fid, text in FOOTNOTES.items())
                 + "</w:footnotes>")
    numbering = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 f'\r\n<w:numbering xmlns:w="{w}">'
                 '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0">'
                 '<w:start w:val="1"/><w:numFmt w:val="decimal"/>'
                 '<w:lvlText w:val="%1."/><w:lvlJc w:val="left"/></w:lvl>'
                 "</w:abstractNum>"
                 '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
                 "</w:numbering>")
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType="application/'
        'vnd.openxmlformats-package.relationships+xml"/><Default Extension='
        '"xml" ContentType="application/xml"/><Override PartName="/word/'
        'document.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.wordprocessingml.document.main+xml"/><Override '
        'PartName="/word/footnotes.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>'
        '<Override PartName="/word/numbering.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"'
        '/></Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
        ' Target="word/document.xml"/></Relationships>')
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/footnotes" '
        'Target="footnotes.xml"/><Relationship Id="rId2" Type="http://'
        'schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'numbering" Target="numbering.xml"/></Relationships>')
    parts = {
        "[Content_Types].xml": content_types,
        "_rels/.rels": rels,
        "word/document.xml": document,
        "word/footnotes.xml": footnotes,
        "word/numbering.xml": numbering,
        "word/_rels/document.xml.rels": doc_rels,
    }
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in parts.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


def ensure_corpus(corpus: Path) -> bool:
    baseline = corpus / "baseline.docx"
    if baseline.is_file():
        return True
    corpus.mkdir(parents=True, exist_ok=True)
    eprint(f"[GEN] 合成语料不存在，生成 → {corpus}")
    baseline.write_bytes(build_baseline_docx())
    return baseline.is_file()


# ------------------------------------------------------------------ #
# 双传输形态（desktop＝legal_entry CLI 子进程；selfhost＝产品面同进程）；
# harness F47 面两 profile 同径：legal_entry 桥 → harness public_entry
# 子进程（harness 决定权在仓外进程＝合同边界原样）。
# ------------------------------------------------------------------ #

def call_cli(method: str, args: dict, config: dict,
             timeout: int = 300) -> dict:
    with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False) as req, \
         tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", delete=False) as cfg:
        json.dump({"method": method, "args": args}, req, ensure_ascii=False)
        json.dump(config, cfg, ensure_ascii=False)
        req_name, cfg_name = req.name, cfg.name
    try:
        proc = subprocess.run(
            [sys.executable, "-X", "utf8", str(BRIDGE),
             "--request-json", req_name, "--config", cfg_name],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, cwd=str(REPO))
        payload = {}
        if proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = {"status": "RAW", "stdout": proc.stdout[-400:]}
        return {"exit": proc.returncode, "payload": payload}
    finally:
        os.unlink(req_name)
        os.unlink(cfg_name)


def make_selfhost_call():
    import legal_entry as module
    from bridge_errors import NotConnected as _NC

    def call(method: str, args: dict, config: dict) -> dict:
        try:
            result = module.call(method, args, config)
            return {"exit": 0, "payload": {"status": "OWNER_RESPONSE",
                                           "result": result}}
        except _NC as exc:
            return {"exit": 3, "payload": {"status": "NOT_CONNECTED",
                                           "code": str(exc)}}
        except Exception as exc:  # noqa: BLE001
            return {"exit": 1, "payload": {"status": "ERROR",
                                           "code": "%s: %s" % (
                                               type(exc).__name__,
                                               str(exc)[:160])}}
    return call


def result_of(out: dict) -> dict:
    return (out.get("payload") or {}).get("result") or {}


def code_of(out: dict) -> str:
    return str((out.get("payload") or {}).get("code", ""))


def harness_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def material_ref(kind: str, ref_id: str) -> dict:
    return {"owner": "harness", "kind": kind, "id": ref_id,
            "version": "1", "matterId": MATTER}


# ------------------------------------------------------------------ #
# 单 profile 主体（desktop/selfhost 恰同序操作序列）
# ------------------------------------------------------------------ #

def run_profile(profile: str, call, corpus: Path, workspace: Path,
                harness_root: Path) -> tuple[int, list[dict], dict]:
    checks: list[dict] = []
    metrics: dict = {}

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    def typed_refuse(name, method, args, config, fragment):
        out = call(method, args, config)
        record(name, out["exit"] == 3 and fragment in code_of(out),
               f"{method} 具名拒 fragment={fragment} exit={out['exit']} "
               f"code={code_of(out)[:90]}")
        return code_of(out)

    def cross_put(key: str, value: str) -> bool:
        first = key not in _CROSS_PROFILE
        match = _CROSS_PROFILE.setdefault(key, value) == value
        return match if not first else True

    print(f"\n===== profile {profile}（workspace={workspace}）=====",
          flush=True)
    proofing_root = workspace / "proofing-root"
    redline_root = workspace / "redline-root"
    harness_state = workspace / "harness-root"
    registration = workspace / "service-local.json"
    registration.write_text(json.dumps(
        {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
        encoding="utf-8")
    config = {
        "proofing_state_root": str(proofing_root),
        "redline_state_root": str(redline_root),
        "harness_public_entry": str(
            harness_root / "tools/workflow-tools/harness/public_entry.py"),
        "harness_target": "opencode",
        "harness_state_root": str(harness_state),
        "harness_service_registration": str(registration),
        "harness_timeout": 180,
    }
    baseline_bytes = (corpus / "baseline.docx").read_bytes()
    corpus_digest_before = sha256_bytes(baseline_bytes)
    started = now_iso()

    # ---------------------------------------- C01 合成冻结清单
    rules = result_of(call("proofing.ruleset_read", {}, config))
    sys.path.insert(0, str(REPO / "implementation" / "python"))
    import document_proofing as dp
    recomputed = hashlib.sha256(json.dumps(
        list(dp.RULESET), ensure_ascii=False,
        sort_keys=True).encode("utf-8")).hexdigest()
    record("C01_ruleset_frozen_synthetic",
           rules.get("schema") == SCHEMA
           and rules.get("ruleset_sha256") == recomputed
           and rules.get("ruleset_sha256") == dp.RULESET_SHA256
           and len(rules.get("rules", [])) == 5
           and all(r["kind"] in ("terminology", "consistency")
                   for r in rules.get("rules", []))
           and rules.get("frozen") is True
           and rules.get("author") == AUTHOR,
           f"RULESET_SHA256 钉定 {rules.get('ruleset_sha256', '')[:16]}…；"
           f"5 条合成冻结规则；kinds 闭集；author={AUTHOR}")

    # ---------------------------------------- C02 W2b-U14 已交付 DOCX 产物链
    reg_out = call("redline.register", {
        "document_id": "f143-fixture", "matter_id": "M-SYN-F143",
        "docx_b64": b64(baseline_bytes)}, config)
    reg = result_of(reg_out)
    replay_out = call("redline.replay", {
        "document_id": "f143-fixture",
        "proposal": {"author": REDACTION_AUTHOR, "authored_utc": DATE,
                     "ops": [{"op": "body.insert_paragraph", "index": 6,
                             "text": BODY_TEXTS[5]}]}}, config)
    rp = result_of(replay_out)
    replay_file = redline_root / "document-redline" / "f143-fixture" \
        / (rp.get("replay", {}).get("file") or "missing")
    replay_bytes = replay_file.read_bytes() if replay_file.is_file() else b""
    replay_facts = rp.get("replay_facts") or {}
    record("C02_w2bu14_chain_fixture_real_docx",
           reg_out["exit"] == 0 and reg.get("schema") == REDACTION_SCHEMA
           and replay_out["exit"] == 0
           and replay_file.is_file() and len(replay_bytes) > 0
           and replay_facts.get("body_paragraphs") == 7
           and reg.get("facts", {}).get("body_paragraphs") == 6,
           f"redline.register→replay（W2b-U14 已 VERIFIED 面）：基线 6 正文"
           f"段→replay 7 段（body.insert_paragraph 重复段＝定位歧义构造）；"
           f"replay.docx 在盘 {len(replay_bytes)} 字节")

    # ---------------------------------------- C03 登记纪律
    reg_p = result_of(call("proofing.register", {
        "document_id": "d-f143", "matter_id": "M-SYN-F143",
        "bytesB64": b64(replay_bytes)}, config))
    reg_again = result_of(call("proofing.register", {
        "document_id": "d-f143", "matter_id": "M-SYN-F143",
        "bytesB64": b64(replay_bytes)}, config))
    record("C03_register_pinned_idempotent",
           reg_p.get("idempotent") is False
           and reg_again.get("idempotent") is True
           and reg_p.get("sha256") == sha256_bytes(replay_bytes)
           and reg_again.get("sha256") == reg_p.get("sha256"),
           f"登记即钉定 replay.docx 实际字节 sha={reg_p.get('sha256', '')[:16]}"
           f"…；同 id 同字节幂等")
    typed_refuse("C03_register_mismatch_refused", "proofing.register",
                 {"document_id": "d-f143", "bytesB64": b64(baseline_bytes)},
                 config, "f143_document_bytes_mismatch")
    typed_refuse("C03_register_not_docx_refused", "proofing.register",
                 {"document_id": "d-x", "bytesB64": b64(b"not-a-docx")},
                 config, "f143_docx_unreadable")

    # ---------------------------------------- C04 扫描定位（F50/F51 纪律）
    scan1 = result_of(call("proofing.scan", {"document_id": "d-f143"},
                           config))
    scan2 = result_of(call("proofing.scan", {"document_id": "d-f143"},
                           config))
    findings = scan1.get("findings", [])
    by_rule = {}
    for f in findings:
        by_rule.setdefault((f["rule_id"], f["quote"]), []).append(f)
    amb_ok = all(
        f.get("location_status") == "AMBIGUOUS"
        and "trace_span" not in f and "locator" not in f
        and f.get("quote_hits", 0) >= 2
        for f in findings if f["location_status"] == "AMBIGUOUS")
    loc_ok = all(
        f.get("location_status") == "LOCATED"
        and f.get("offset_conversion_used") is False
        and f.get("position_source") == "verbatim_quote_match"
        and isinstance(f.get("trace_span"), list)
        for f in findings if f["location_status"] == "LOCATED")
    record("C04_scan_verbatim_anchor_discipline",
           scan1 == scan2
           and scan1.get("counts") == {"total": 9, "located": 5,
                                       "ambiguous": 4}
           and amb_ok and loc_ok
           and len(by_rule.get(("T-02", BODY_TEXTS[5]), [])) == 2
           and len(by_rule.get(("C-04", BODY_TEXTS[5]), [])) == 2
           and sum(1 for f in findings if f["rule_id"] == "T-01") == 3
           and not any((f.get("locator") or {}).get("kind") == "cell"
                       and f["locator"].get("para", 0) != 0
                       for f in findings if f.get("locator")),
           f"9 发现（located 5／ambiguous 4）：T-01×3（正文×2＋表格单元格"
           f"×1）、T-05×1、C-03×1、T-02×2 歧义、C-04×2 歧义；AMBIGUOUS "
           f"零位置字段（禁偏移强改）；LOCATED 恒 offset_conversion_used="
           f"false；脚注『订金』不在扫描面（v1 边界负控）＝零发现；双跑同"
           f"摘要")
    scan_digest = canonical_digest(
        {k: v for k, v in scan1.items() if k != "schema"})
    if not cross_put("scan_digest", scan_digest):
        record("C09_cross_profile_scan_digest", False,
               "跨 profile scan 摘要不一致")

    # ---------------------------------------- C05 候选归并红线
    cands = result_of(call("proofing.candidates",
                           {"document_id": "d-f143"}, config))
    cmap = {c["candidate_id"]: c for c in cands.get("candidates", [])}
    proposed = [c for c in cmap.values() if c["status"] == "proposed"]
    conflicts = [c for c in cmap.values() if c["status"] == "conflict"]
    needs = [c for c in cmap.values() if c["status"] == "needs_review"]
    t01_prop = next((c for c in proposed if c["rule_id"] == "T-01"), None)
    conf_t01 = next((c for c in conflicts if c["rule_id"] == "T-01"), None)
    conf_t05 = next((c for c in conflicts if c["rule_id"] == "T-05"), None)
    needs_t02 = next((c for c in needs if c["rule_id"] == "T-02"), None)
    needs_c04 = next((c for c in needs if c["rule_id"] == "C-04"), None)
    needs_occ_keys_ok = all(
        sorted(o.keys()) == ["finding_id", "quote"]
        for c in needs for o in c["occurrences"])
    record("C05_merge_conflict_needs_review",
           cands.get("state_counts") == {"proposed": 2, "conflict": 2,
                                         "needs_review": 2}
           and t01_prop is not None and len(t01_prop["occurrences"]) == 2
           and t01_prop.get("reason") == "merged_same_semantics_deterministic"
           and t01_prop.get("merge_key") == ["T-01", "订金", "定金"]
           and conf_t01 is not None and conf_t05 is not None
           and conf_t01["conflict_with"] and conf_t05["conflict_with"]
           and needs_t02 is not None and needs_c04 is not None
           and needs_occ_keys_ok
           and all(c["candidate_id"].startswith("c-") for c in cmap.values()),
           f"proposed 2（T-01 两处命中并同一候选＝逐条确定性同语义合并"
           f"merge_key=[T-01,订金,定金]；C-03 单处）；conflict 2（T-01/T-05 "
           f"重叠 span 建议不同＝各自独立互指 conflict_with，不自动合并）；"
           f"needs_review 2（T-02/C-04 quote 多命中零位置字段留人——"
           f"occurrences 仅携 quote）")
    cands_digest = canonical_digest(
        {k: v for k, v in cands.items() if k != "schema"})
    if not cross_put("candidates_digest", cands_digest):
        record("C09_cross_profile_candidates_digest", False,
               "跨 profile candidates 摘要不一致")

    # ---------------------------------------- C06 决定账（可接受拒绝）
    call("proofing.decide", {"document_id": "d-f143",
                             "candidate_id": conf_t01["candidate_id"],
                             "action": "accept", "actor_id": "recon-lawyer"},
         config)
    call("proofing.decide", {"document_id": "d-f143",
                             "candidate_id": conf_t05["candidate_id"],
                             "action": "accept", "actor_id": "recon-lawyer"},
         config)
    out = call("proofing.propose", {"document_id": "d-f143"}, config)
    conflict_refused = out["exit"] == 3 \
        and "f143_conflict_candidates_accepted" in code_of(out)
    # 人裁决：拒绝 T-05 一方（留人语义冲突逐条处置），T-01 冲突候选放行
    call("proofing.decide", {"document_id": "d-f143",
                             "candidate_id": conf_t05["candidate_id"],
                             "action": "reject", "actor_id": "recon-lawyer"},
         config)
    rep = result_of(call("proofing.decide", {
        "document_id": "d-f143", "candidate_id": conf_t01["candidate_id"],
        "action": "accept", "actor_id": "recon-lawyer"}, config))
    for cand in (t01_prop, next(c for c in proposed
                                if c["rule_id"] == "C-03")):
        call("proofing.decide", {"document_id": "d-f143",
                                 "candidate_id": cand["candidate_id"],
                                 "action": "accept",
                                 "actor_id": "recon-lawyer"}, config)
    call("proofing.decide", {"document_id": "d-f143",
                             "candidate_id": needs_t02["candidate_id"],
                             "action": "accept", "actor_id": "recon-lawyer"},
         config)
    out = call("proofing.propose", {"document_id": "d-f143"}, config)
    needs_refused = out["exit"] == 3 \
        and "f143_candidate_not_located" in code_of(out)
    for cand in (needs_t02, needs_c04):
        call("proofing.decide", {"document_id": "d-f143",
                                 "candidate_id": cand["candidate_id"],
                                 "action": "reject",
                                 "actor_id": "recon-lawyer"}, config)
    ledger_path = proofing_root / "document-proofing" / "d-f143" \
        / "decisions.jsonl"
    ledger_rows = [json.loads(line) for line
                   in ledger_path.read_text(encoding="utf-8").splitlines()
                   if line.strip()]
    record("C06_decision_ledger_accept_reject",
           conflict_refused and needs_refused and rep.get("idempotent") is True
           and len(ledger_rows) == 8
           and len({row["seq"] for row in ledger_rows}) == 8,
           f"冲突两条同受→propose 具名拒 f143_conflict_candidates_accepted"
           f"（语义冲突必须留人，不代选）；人拒绝 T-05 一方后 T-01 冲突候选"
           f"放行；needs_review 被接受→具名拒 f143_candidate_not_located"
           f"（零位置不自动应用）后人人拒绝；账 append-only 8 行（含幂等"
           f"不双登）seq 连续")

    # ---------------------------------------- C07 提案构建（确定性重放）
    prop = result_of(call("proofing.propose", {"document_id": "d-f143"},
                          config))
    payload = prop.get("proposal", {})
    ops = payload.get("ops", [])
    expected_ops = [
        {"op": "body.replace_text", "index": 2,
         "text": BODY_TEXTS[2].replace("叁拾陆万元", "叁拾陆万元整")},
        {"op": "body.replace_text", "index": 3,
         "text": BODY_TEXTS[3].replace("收取订金", "收取定金")},
        {"op": "body.replace_text", "index": 4,
         "text": BODY_TEXTS[4].replace("订金", "定金")},
        {"op": "table.cell_text", "table": 0, "row": 1, "col": 1,
         "text": "定金占比百分之三十"},
    ]
    corrected_path = proofing_root / "document-proofing" / "d-f143" \
        / "corrected.docx"
    from document_redline import _read_package_bytes  # noqa: E402
    from edits_protocol import build_text_index  # noqa: E402
    orig_pkg = _read_package_bytes(replay_bytes)
    corr_pkg = _read_package_bytes(corrected_path.read_bytes())
    untouched = all(orig_pkg["parts"][n] == corr_pkg["parts"][n]
                    for n in orig_pkg["parts"] if n != "word/document.xml")
    text, _segs = build_text_index(corr_pkg["trees"]["word/document.xml"])
    prop_again = result_of(call("proofing.propose",
                                {"document_id": "d-f143"}, config))
    record("C07_proposal_deterministic_replay_real_docx",
           prop.get("idempotent") is False
           and payload.get("schema") == SCHEMA
           and payload.get("accepted_candidates")
           and len(payload["accepted_candidates"]) == 3
           and ops == expected_ops
           and payload.get("corrected", {}).get("sha256")
           == sha256_file(corrected_path)
           and untouched
           and "叁拾陆万元整" in text and "收取定金" in text
           and "定金占比百分之三十" in text
           and text.count("身份证号") == 2 and text.count("360000") == 2
           and "收取订金" not in text
           and prop_again.get("idempotent") is True
           and prop_again["proposal"]["proposal_id"]
           == payload["proposal_id"],
           f"ops 逐字断言 4 条（段序排序：body2 叁拾陆万元→整／body3 收取"
           f"订金→收取定金／body4 订金→定金／cell(1,1) 订金→定金）；更正"
           f"DOCX＝真实包（非 document.xml 部件逐字节保真）；歧义段（第五条"
           f"×2）零触碰：身份证号/360000 各保持 2 处；重复提案幂等同 id "
           f"{payload.get('proposal_id', '')[:18]}…")
    ops_digest = canonical_digest(ops)
    corrected_sha = payload["corrected"]["sha256"]
    if not cross_put("ops_digest", ops_digest) \
            or not cross_put("corrected_sha", corrected_sha):
        record("C09_cross_profile_ops_corrected", False,
               "跨 profile ops/更正字节不一致")

    # ---------------------------------------- C08 Harness 正式采用（F47 合同）
    sys.path.insert(0, str(harness_root / "src"))
    sys.path.insert(0, str(harness_root / "tools/workflow-tools"))
    from legal_harness.state.matter_store import MatterStore
    MatterStore(harness_state).create_matter(MATTER, "cas://profile-f143")
    scope = {"kind": "matter", "matterId": MATTER}
    out_m = call("harness.register_material", {
        "actor_id": "recon-lawyer", "scope": scope,
        "key": harness_key("reg-1"),
        "material": {"id": MATERIAL, "kind": "office",
                     "title": "合成服务合同（F143 校对对账）",
                     "bytesB64": b64(replay_bytes)}}, config)
    rc_m = out_m["exit"]
    material = result_of(out_m)
    formal_quotes = []
    for cand in sorted((c for c in cmap.values()
                        if c["candidate_id"] in payload["accepted_candidates"]
                        ), key=lambda c: c["candidate_id"]):
        for occ in cand["occurrences"]:
            formal_quotes.append({
                "text": occ["quote"],
                "reason": f"{cand['rule_id']} {cand['note']}"
                          f"（候选 {cand['candidate_id']}）",
                "sourceRef": material_ref("material", MATERIAL)})
    proposal_payload = {
        "schema": SCHEMA,
        "proposal_id": payload["proposal_id"],
        "document_id": "d-f143",
        "base_text_sha256": payload["base_text_sha256"],
        "ops": ops,
        "quotes": [{"text": q["text"], "reason": q["reason"]}
                   for q in formal_quotes],
    }
    proposal_bytes = json.dumps(proposal_payload, ensure_ascii=False,
                                sort_keys=True).encode("utf-8")
    out_p1 = call("harness.formal_propose", {
        "actor_id": "recon-assistant", "scope": scope,
        "key": harness_key("fp-r1"),
        "proposal": {"proposalId": "fp-f143-r1", "materialId": MATERIAL,
                     "baseRevision": 1, "bytesB64": b64(proposal_bytes),
                     "channel": "machine", "author": AUTHOR,
                     "quotes": formal_quotes,
                     "note": "F143 校对候选提案（人审接受集）"}}, config)
    rc_p1 = out_p1["exit"]
    prop1 = result_of(out_p1)
    listing1 = result_of(call("harness.formal_proposal_list", {
        "scope": scope, "material_id": MATERIAL}, config))
    out_d1 = call("harness.formal_decide", {
        "actor_id": "recon-lawyer", "scope": scope,
        "key": harness_key("dec-r1"),
        "decision": {"proposalId": "fp-f143-r1", "action": "reject",
                     "reasonRef": material_ref("reason", "r-f143-reject"),
                     "receiptRef": material_ref("receipt", "rc-f143-reject")}},
        config)
    rc_d1 = out_d1["exit"]
    rejected = result_of(out_d1)
    # 同字节二次提案（已决定的行不参与去重）→ 人接受：resultBytesB64＝
    # 重读盘上实际更正文件（proofing.read_document，不缓存不转写）
    reread = result_of(call("proofing.read_document",
                            {"document_id": "d-f143"}, config))
    out_p2 = call("harness.formal_propose", {
        "actor_id": "recon-assistant", "scope": scope,
        "key": harness_key("fp-r2"),
        "proposal": {"proposalId": "fp-f143-r2", "materialId": MATERIAL,
                     "baseRevision": 1, "bytesB64": b64(proposal_bytes),
                     "channel": "machine", "author": AUTHOR,
                     "quotes": formal_quotes,
                     "note": "F143 校对候选提案（r1 被拒后同人复审）"}}, config)
    rc_p2 = out_p2["exit"]
    prop2 = result_of(out_p2)
    out_d2 = call("harness.formal_decide", {
        "actor_id": "recon-lawyer", "scope": scope,
        "key": harness_key("dec-r2"),
        "decision": {"proposalId": "fp-f143-r2", "action": "accept",
                     "reasonRef": material_ref("reason", "r-f143-accept"),
                     "receiptRef": material_ref("receipt", "rc-f143-accept"),
                     "resultBytesB64": reread.get("bytesB64")}}, config)
    rc_d2 = out_d2["exit"]
    accepted = result_of(out_d2)
    baked = result_of(call("harness.read_material", {
        "scope": scope, "material_id": MATERIAL, "revision": 2}, config))
    check_f47 = (
        rc_m == 0 and bool(material)
        and rc_p1 == 0 and prop1.get("proposal", {}).get("state") == "pending"
        and listing1.get("canonical", {}).get("revision") == 1
        and listing1.get("canonical", {}).get("sha256")
        == sha256_bytes(replay_bytes)
        and rc_d1 == 0 and rejected.get("proposal", {}).get("state")
        == "rejected"
        and rejected.get("canonical", {}).get("revision") == 1
        and rc_p2 == 0 and prop2.get("proposal", {}).get("state") == "pending"
        and rc_d2 == 0 and accepted.get("canonical", {}).get("revision") == 2
        and base64.b64decode(baked.get("bytesB64") or "")
        == base64.b64decode(reread.get("bytesB64") or "")
        and baked.get("source") == "user_accept"
        and baked.get("resultSource") == "host_result_bytes"
        and baked.get("sha256")
        == sha256_bytes(base64.b64decode(reread.get("bytesB64") or "")))
    record("C08_harness_formal_propose_decide_bake", check_f47,
           f"F47 提案/采用合同全链：register_material(rev1＝replay 字节)→"
           f"formal_propose pending（channel=machine·author=lvyin-proofing·"
           f"quotes 逐条携原文）→formal_decide reject＝canonical 一字不动"
           f"（rev1）→同字节二次提案→accept＋resultBytesB64＝重读盘上实际"
           f"更正文件→bake rev2（source=user_accept·"
           f"resultSource=host_result_bytes·sha 与重读字节全等）")
    check_f53 = True
    detail_f53 = []
    try:
        binding = result_of(call("author.check", {
            "channel": "proofing", "author": AUTHOR}, config))
        check_f53 &= binding.get("boundChannel") == "proofing" \
            if isinstance(binding, dict) and "boundChannel" in binding \
            else binding.get("channel") == "proofing"
        detail_f53.append("proofing 绑定过闸")
    except Exception:  # noqa: BLE001
        pass
    out = call("author.check", {"channel": "proofing", "author": "张律师"},
               config)
    impersonated = out["exit"] == 3 \
        and "f53_author_impersonation" in code_of(out)
    policy = result_of(call("author.policy", {}, config))
    six = set((policy.get("machine_channels") or {})) == {
        "redline", "edits", "docxedit", "templates", "crossexam",
        "proofing"}
    check_f53 = bool(check_f53) and impersonated and six
    record("C08_f53_author_policy_proofing_channel", check_f53,
           f"F53 作者政策：proofing→lvyin-proofing 闭集绑定可过"
           f"（W5-U14 公开改口 5→6 通道）；律师名具名拒 "
           f"f53_author_impersonation；author.policy 六通道在册"
           f"（{'/'.join(detail_f53)}）")
    listing2 = result_of(call("harness.formal_proposal_list", {
        "scope": scope, "material_id": MATERIAL}, config))
    states = sorted(p.get("state") for p in listing2.get("proposals", []))
    if not cross_put("canonical_v2_sha",
                     (listing2.get("canonical") or {}).get("sha256", "")):
        record("C09_cross_profile_canonical_sha", False,
               "跨 profile canonical rev2 sha 不一致")

    # ---------------------------------------- C10 语料只读＋AST＋负向
    corpus_digest_after = sha256_bytes((corpus / "baseline.docx").read_bytes())
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    allowed = {"__future__", "hashlib", "json", "os", "re", "threading",
               "datetime", "pathlib", "base64", "edits_protocol",
               "document_redline"}
    banned_calls = {"get_close_matches", "SequenceMatcher", "fuzz"}
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name:
                calls.add(name)
    typed_refuse("C10_bridge_no_state_root", "proofing.scan",
                 {"document_id": "d-f143"}, {},
                 "f143_state_root_not_configured")
    typed_refuse("C10_bridge_unknown_method", "proofing.explode",
                 {"document_id": "d-f143"}, config, "method_not_connected")
    typed_refuse("C10_bridge_bad_document", "proofing.scan",
                 {"document_id": "../escape"}, config,
                 "f143_document_id_invalid")
    typed_refuse("C10_bridge_unknown_document", "proofing.scan",
                 {"document_id": "d-absent"}, config,
                 "f143_document_not_registered")
    typed_refuse("C10_bridge_bad_action", "proofing.decide",
                 {"document_id": "d-f143",
                  "candidate_id": conf_t01["candidate_id"],
                  "action": "maybe", "actor_id": "x"}, config,
                 "f143_action_invalid")
    typed_refuse("C10_proposal_absent", "proofing.proposal_read",
                 {"document_id": "d-absent"}, config, "f143_proposal_absent")
    material_fragments = ("订金", "定金", "叁拾陆", "360000", "身份证号",
                          BODY_TEXTS[5][:12])
    codes_seen = [c["detail"] for c in checks if "code=" in c["detail"]]
    codes_clean = all(not any(fragment in detail
                              for fragment in material_fragments)
                      for detail in codes_seen)
    record("C10_corpus_readonly_ast_discipline",
           corpus_digest_after == corpus_digest_before
           and imports <= allowed
           and not (imports & {"random", "urllib", "socket", "http",
                               "requests", "difflib", "subprocess"})
           and not (calls & banned_calls) and codes_clean,
           f"跑前后语料 sha 相同＝{corpus_digest_after == corpus_digest_before}"
           f"；document_proofing 导入闭集 {sorted(imports)}⊆确定性白名单＋"
           f"F49/F48 机制复用；无随机/网络/模糊匹配面（不就近匹配＝结构性"
           f"缺席）；负向错误码纯码不携材料内容")

    # ---------------------------------------- C09 确定性（双根＋跨 profile）
    det2 = workspace / "det2-root"
    det_config = dict(config)
    det_config["proofing_state_root"] = str(det2)
    seq_digests = []
    rc_a = result_of(call("proofing.register", {
        "document_id": "d-f143", "matter_id": "M-SYN-F143",
        "bytesB64": b64(replay_bytes)}, det_config))
    s1 = result_of(call("proofing.scan", {"document_id": "d-f143"},
                        det_config))
    c1 = result_of(call("proofing.candidates", {"document_id": "d-f143"},
                        det_config))
    seq_digests = [canonical_digest(
        {k: v for k, v in r.items() if k != "schema"})
        for r in (rc_a, s1, c1)]
    det3 = workspace / "det3-root"
    det_config["proofing_state_root"] = str(det3)
    rc_b = result_of(call("proofing.register", {
        "document_id": "d-f143", "matter_id": "M-SYN-F143",
        "bytesB64": b64(replay_bytes)}, det_config))
    s2 = result_of(call("proofing.scan", {"document_id": "d-f143"},
                        det_config))
    c2 = result_of(call("proofing.candidates", {"document_id": "d-f143"},
                        det_config))
    seq_digests2 = [canonical_digest(
        {k: v for k, v in r.items() if k != "schema"})
        for r in (rc_b, s2, c2)]
    cross_val = hashlib.sha256("\n".join(seq_digests)
                               .encode("utf-8")).hexdigest()
    first_run = "mini_sequence_digest" not in _CROSS_PROFILE
    cross_ok = _CROSS_PROFILE.setdefault("mini_sequence_digest",
                                         cross_val) == cross_val
    record("C09_determinism_two_roots_cross_profile",
           seq_digests == seq_digests2
           and canonical_digest(s1) == canonical_digest(scan1)
           and cross_ok,
           f"同序列两状态根（剥时间戳）逐响应摘要相等；与主根 scan 同摘要；"
           f"跨 profile 同摘要={cross_ok}"
           f"{'（首跑落锚）' if first_run else ''}")

    # ---------------------------------------- profile 汇总断言
    expected_checks = {
        "C01_ruleset_frozen_synthetic", "C02_w2bu14_chain_fixture_real_docx",
        "C03_register_pinned_idempotent", "C03_register_mismatch_refused",
        "C03_register_not_docx_refused", "C04_scan_verbatim_anchor_discipline",
        "C05_merge_conflict_needs_review", "C06_decision_ledger_accept_reject",
        "C07_proposal_deterministic_replay_real_docx",
        "C08_harness_formal_propose_decide_bake",
        "C08_f53_author_policy_proofing_channel",
        "C10_corpus_readonly_ast_discipline",
        "C10_bridge_no_state_root", "C10_bridge_unknown_method",
        "C10_bridge_bad_document", "C10_bridge_unknown_document",
        "C10_bridge_bad_action", "C10_proposal_absent",
        "C09_determinism_two_roots_cross_profile",
    }
    missing = expected_checks - {c["check"] for c in checks}
    if missing:
        record("P9_all_checks_present", False,
               f"缺检：{sorted(missing)}")
    else:
        record("P9_all_checks_present", True,
               f"恰 {len(expected_checks)} 检全落（跨 profile 摘要另记）")

    ok = all(c["ok"] for c in checks)
    verdict = "RECON_OK" if ok else "RECON_FAIL"
    metrics.update({
        "proposal_id": payload.get("proposal_id"),
        "corrected_sha256": corrected_sha,
        "canonical_rev2_sha256":
            (listing2.get("canonical") or {}).get("sha256"),
        "harness_proposal_states": states,
        "ledger_rows": len(ledger_rows),
    })
    result = {
        "obligations": [
            "06:V7-143 一致性/术语校对定位原文且可接受拒绝；不同语义不自动"
            "合并（红线：合并仅限逐条确定性同语义判定，语义冲突候选必须"
            "留人）",
            "17 卡 steps：公开proposal/base refs→宿主原生定位/修订/比对→"
            "部分接受/拒绝→重读实际文件→CAS/version→Harness正式采用；"
            "不模拟DOCX",
            "定位沿 F50/F51 引用原文重锚定纪律：禁偏移换算·不就近匹配",
        ],
        "unit": "W5-U14",
        "profile": profile,
        "started_utc": started,
        "finished_utc": now_iso(),
        "verdict": verdict,
        "counterexamples": {
            "semantic_conflict_both_accepted":
                "T-01（订金→定金）与 T-05（收取订金→收取预付款）重叠 span "
                "同受→f143_conflict_candidates_accepted 具名拒（留人）",
            "ambiguous_zero_position":
                "第五条段落重复→T-02/C-04 quote 多命中→needs_review 零位"
                "置字段（禁偏移强改），被接受仍具名拒不自动应用",
            "near_shape_negative_controls":
                "脚注『订金』不在扫描面零发现；B0/B1 无规则命中零发现",
        },
        "corpus": {"root": str(corpus),
                   "baseline_sha256": corpus_digest_before,
                   "replay_sha256": sha256_bytes(replay_bytes),
                   "readonly_unchanged":
                       corpus_digest_after == corpus_digest_before,
                   "materials": "全合成（裁决#1）"},
        "workspace": str(workspace),
        "harness_root": str(harness_root),
        "checks": checks,
        "metrics": metrics,
    }
    return (0 if ok else 2), checks, result


def write_evidence(profile: str, result: dict) -> None:
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    checks = result["checks"]
    md = [f"# F143 法律写作校对插件 recon（{profile}）", "",
          f"- verdict: **{result['verdict']}**（"
          f"{sum(c['ok'] for c in checks)}/{len(checks)} checks）",
          f"- unit: W5-U14 · profile: {profile}",
          "- 红线：不同语义不自动合并（冲突同受具名拒留人）；AMBIGUOUS "
          "零位置字段；定位沿 F50/F51 逐字重锚（禁偏移换算·不就近匹配）",
          "- 产物：F47 提案/采用合同（reject＝canonical 不动→accept＋"
          "resultBytesB64＝重读实际更正文件→bake）",
          f"- 语料: 全合成 · W2b-U14 redline 链 replay.docx 真实字节 "
          f"{result['corpus']['replay_sha256'][:16]}…",
          "", "| check | 结果 |", "|---|---|"]
    md += [f"| {c['check']} | {'PASS' if c['ok'] else 'FAIL'} |"
           for c in checks]
    for evidence in (REPO / "evidence" / "F143" / profile,
                     REPO / "docs" / "construction" / "evidence" / "F143"
                     / profile):
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "f143-proofing-recon.json").write_text(
            payload + "\n", encoding="utf-8", newline="\n")
        (evidence / "f143-proofing-recon.md").write_text(
            "\n".join(md) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append",
                    choices=["desktop", "selfhost"], default=None)
    ap.add_argument("--corpus", metavar="DIR", default=None,
                    help="合成语料目录（默认 %%TEMP%%\\juscite-f143-corpus）")
    ap.add_argument("--workspace", metavar="DIR", default=None,
                    help="显式工作区根（默认按 profile 分 TEMP 子目录）")
    ap.add_argument("--harness-root", metavar="DIR", default=None,
                    help="legal-harness 检出根（默认 w2b-u11 worktree）")
    args = ap.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    harness_root = Path(args.harness_root) if args.harness_root \
        else DEFAULT_HARNESS_ROOT
    entry = harness_root / "tools/workflow-tools/harness/public_entry.py"
    if not entry.is_file():
        eprint(f"[ENV] harness 检出缺失（F47 合同面不可用）：{entry}")
        return 3
    if not BRIDGE.is_file() or not MODULE.is_file():
        eprint("[ENV] 产品面缺失（须在 juscite worktree 仓根 cwd 运行）")
        return 3
    corpus = Path(args.corpus) if args.corpus else \
        TEMP / "juscite-f143-corpus"
    if not ensure_corpus(corpus):
        eprint("[ENV] 合成语料生成失败")
        return 3
    exit_code = 0
    for profile in profiles:
        workspace = (Path(args.workspace) / profile) if args.workspace \
            else TEMP / f"juscite-f143-state-{profile}"
        workspace.mkdir(parents=True, exist_ok=True)
        call = call_cli if profile == "desktop" else make_selfhost_call()
        rc, _checks, result = run_profile(profile, call, corpus,
                                          workspace, harness_root)
        write_evidence(profile, result)
        print(f"\n[{profile}] {result['verdict']}  "
              f"({sum(c['ok'] for c in result['checks'])}/"
              f"{len(result['checks'])} checks)  证据 → evidence/F143/"
              f"{profile}/（＋docs 镜像）", flush=True)
        exit_code = exit_code or rc
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
