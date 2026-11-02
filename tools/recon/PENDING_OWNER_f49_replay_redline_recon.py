#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F49 义务验收 recon（W2b-U14）：干净基版与提案 replay 对比产真修订
红线——双 profile（desktop/selfhost）两实例，真桥 CLI 子进程径。

义务 06:F49 / 17 卡断言：「干净基版与提案replay对比产真修订；表格/
脚注/编号有内容回读」；06:F49「compareDocuments 差量，非会话内打标」
「提案 replay 与渲染解耦，更稳」。产物红线 DOCX 供 W2b-U16 WPS 宿主
验证与 E13 两宿主正式 DOCX 闭环收口消费。

硬门（每 profile）：
- C01 干净基版钉定：register 双留存（baseline.docx sha 钉定）＋四类
  事实＋同字节幂等＋同 id 异字节具名拒不改盘。
- C02 干净基版闸：既有修订标记（w:ins）具名拒；模型外构件（文本框
  AlternateContent——LibreOffice Writer PDF 导入结构）具名拒。
- C03 提案 replay（渲染解耦）：封闭算子集重放成独立在盘工件；确定性
  两跑字节级相同；与基线事实确有分叉。
- C04 compareDocuments 差量产真修订：红线 docx 含 w:ins/w:del/w:delText/
  w:pPrChange 真 OOXML 修订标记；作者/日期＝提案声明透传（不伪装律师）；
  对账双不变式（accept_all==replay、reject_all==baseline）面内成立。
- C05 独立对账复核：本工具自带第二实现（非面内代码）对盘上红线做
  accept/reject 变换后与 baseline/replay 四类事实逐一相等。
- C06 内容回读：修订清单自产物红线 DOCX 解析；正文/表格/脚注/编号四类
  齐全且每条携内容（增删段文本/双侧全文/行格内容/新旧 numId）。
- C07 行级修订与 append-only：第二提案（行删＋行插）row_delete/row_
  insert 携格内容回读；旧红线/旧 replay 字节不动；list 与盘一一对应
  （无孤儿）。
- C08 F54 管线衔接：conversion.rebuild 候选（平铺 OOXML）→ redline.
  register 可入修订线（editable_text/route=revision_line）；LibreOffice
  转换候选（文本框结构）→ 干净基版闸具名拒（引擎 READY 时验，未装
  如实记 skipped_env）。
- C09 消费契约与确定性：redline.report 回读==清单；redline.redline
  b64 取件==盘上字节；consumers=[W2b-U16, E13]；跨 profile 同基线同
  提案 content_digest 相等。
- C10 桥 fail-closed 负向：缺状态根/未知方法/坏 id/坏提案/未注册/
  未找到——错误码纯码不携材料内容。
- C11 语料只读锚（跑前后同摘要）。

语料全合成（本工具自建富 OOXML 基线＋reportlab PDF；00-总协调 §6.1
裁决#1，绝无真实文档）。状态根 TEMP 子目录（绝不写 %APPDATA%）。

用法（juscite worktree w2b-u14 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f49_replay_redline_recon.py \
      --profile desktop --profile selfhost

退出码：0＝全部 profile RECON_OK；2＝RECON_FAIL；3＝环境缺失。
证据：docs/construction/evidence/F49/<profile>/ JSON＋MD。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

REPO = Path(__file__).resolve().parents[2]
TEMP = Path(os.environ.get("TEMP", "."))
BRIDGE = REPO / "implementation" / "python" / "legal_entry.py"
SCHEMA = "juscite-f49-replay-redline/1"
DEFAULT_SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# 跨 profile 确定性锚（同基线同提案 → 同 content_digest）
_CROSS_PROFILE_DIGEST: dict[str, str] = {}

BODY_TEXTS = [
    "合成测试卷宗：原告张三与被告李四买卖合同纠纷（全部当事人、案号与金额均为合成虚构材料）",
    "第一条 合同价款：人民币36,000.00元整",
    "付款安排：分三期支付",
    "第二条 交付与验收",
    "付款安排：逾期付款违约金按日万分之五计",
    "第三条 争议解决",
    "本卷全部内容为合成测试材料，不代表任何真实案件。",
]
TABLE_ROWS = [
    ["期次", "应付日期", "本金（元）"],
    ["1", "2026-02-05", "12,000.00"],
    ["2", "2026-03-05", "12,000.00"],
]
FOOTNOTES = {
    1: "合成脚注一：三期付款日期均为合成示例日期。",
    2: "合成脚注二：争议解决条款为合成示例文本。",
}
PROPOSAL_MAIN = {
    "author": "lvyin-redline",
    "authored_utc": "2026-10-16T00:00:00Z",
    "ops": [
        {"op": "body.replace_text", "index": 1,
         "text": "第一条 合同价款：人民币38,500.00元整（含税费）"},
        {"op": "body.insert_paragraph", "index": 3,
         "text": "第二条之一 质量保证期：自验收合格之日起二十四个月。"},
        {"op": "body.delete_paragraph", "index": 7},
        {"op": "table.cell_text", "table": 0, "row": 2, "col": 2,
         "text": "12,500.00"},
        {"op": "footnote.replace_text", "id": 2,
         "text": "合成脚注二：争议解决条文为合成示例文本（修订版）。"},
        {"op": "para.numbering_set", "index": 2, "num_id": 2},
    ],
}
PROPOSAL_ROWS = {
    "author": "lvyin-redline",
    "authored_utc": "2026-10-16T00:00:00Z",
    "ops": [
        {"op": "table.delete_row", "table": 0, "row": 1},
        {"op": "table.insert_row", "table": 0, "row": 2,
         "cells": ["3", "2026-04-05", "12,000.00"]},
    ],
}


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


# --------------------------------------------------------------------------
# 全合成富基线语料（正文/表格/脚注/编号；确定性 zip 时间戳）
# --------------------------------------------------------------------------

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


def build_rich_baseline_docx() -> bytes:
    body = [
        _p_xml(BODY_TEXTS[0]),
        _p_xml(BODY_TEXTS[1], footnote_ids=[1]),
        _p_xml(BODY_TEXTS[2], num_id=1),
        _p_xml(BODY_TEXTS[3]),
        _tbl_xml(TABLE_ROWS),
        _p_xml(BODY_TEXTS[4], num_id=1),
        _p_xml(BODY_TEXTS[5], footnote_ids=[2]),
        _p_xml(BODY_TEXTS[6]),
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>',
    ]
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'\r\n<w:document xmlns:w="{w}"><w:body>{"".join(body)}'
                "</w:body></w:document>")
    footnotes = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 f'\r\n<w:footnotes xmlns:w="{w}">'
                 '<w:footnote w:type="separator" w:id="-1"><w:p><w:r>'
                 "<w:separator/></w:r></w:p></w:footnote>"
                 '<w:footnote w:type="continuationSeparator" w:id="0"><w:p>'
                 "<w:r><w:continuationSeparator/></w:r></w:p></w:footnote>"
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
                 '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0">'
                 '<w:start w:val="1"/><w:numFmt w:val="lowerLetter"/>'
                 '<w:lvlText w:val="(%1)"/><w:lvlJc w:val="left"/></w:lvl>'
                 "</w:abstractNum>"
                 '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
                 '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
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
        'vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml'
        '"/></Types>')
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
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in parts.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


def _rewrite_docx(source: bytes, part_name: str, transform) -> bytes:
    with zipfile.ZipFile(io.BytesIO(source)) as zf:
        replaced = {n: zf.read(n) for n in zf.namelist()}
    replaced[part_name] = transform(replaced[part_name])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in replaced.items():
            zf.writestr(name, data)
    return buf.getvalue()


def build_poisoned_revisions_docx() -> bytes:
    """基线夹具注入既有 w:ins（非干净态）。"""
    return _rewrite_docx(
        build_rich_baseline_docx(), "word/document.xml",
        lambda d: d.replace(
            b"<w:body>",
            b'<w:body><w:p><w:ins w:id="9" w:author="x" '
            b'w:date="2026-01-01T00:00:00Z"><w:r><w:t>already</w:t></w:r>'
            b"</w:ins></w:p>", 1))


def build_textbox_docx() -> bytes:
    """基线夹具注入 mc:AlternateContent（LibreOffice 文本框结构形态）。"""
    return _rewrite_docx(
        build_rich_baseline_docx(), "word/document.xml",
        lambda d: d.replace(
            b"</w:body>",
            b'<w:p><w:r><mc:AlternateContent xmlns:mc="http://schemas.'
            b'openxmlformats.org/markup-compatibility/2006"><mc:Choice/>'
            b"</mc:AlternateContent></w:r></w:p></w:body>", 1))


def build_linkage_pdf() -> bytes:
    """F54 管线衔接用合成 PDF（reportlab；1 页 3 行）。"""
    import io as _io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas as rl_canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buf = _io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setFont("STSong-Light", 12)
    c.drawString(72, A4[1] - 100, "合成管线衔接卷 F49-LINK")
    c.drawString(72, A4[1] - 130, "原告张三与被告李四合成合同纠纷（全部合成）")
    c.drawString(72, A4[1] - 160, "价款人民币21,000.00元，分两期支付。")
    c.showPage()
    c.save()
    return buf.getvalue()


def ensure_corpus(corpus: Path) -> bool:
    names = ("base.docx", "poisoned.docx", "textbox.docx", "link.pdf")
    if all((corpus / n).is_file() for n in names):
        return True
    corpus.mkdir(parents=True, exist_ok=True)
    eprint(f"[GEN] 合成语料不存在，生成 → {corpus}")
    (corpus / "base.docx").write_bytes(build_rich_baseline_docx())
    (corpus / "poisoned.docx").write_bytes(build_poisoned_revisions_docx())
    (corpus / "textbox.docx").write_bytes(build_textbox_docx())
    (corpus / "link.pdf").write_bytes(build_linkage_pdf())
    return all((corpus / n).is_file() for n in names)


def corpus_identity_digest(corpus: Path) -> str:
    parts = [sha256_file(corpus / n)
             for n in ("base.docx", "poisoned.docx", "textbox.docx",
                       "link.pdf")]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 独立对账复核器（第二实现：不复用产品面代码）
# --------------------------------------------------------------------------

def _independent_parse(docx_path: Path):
    zf = zipfile.ZipFile(docx_path)
    names = zf.namelist()
    doc = ET.fromstring(zf.read("word/document.xml"))
    fn = ET.fromstring(zf.read("word/footnotes.xml")) \
        if "word/footnotes.xml" in names else None
    numbering = ET.fromstring(zf.read("word/numbering.xml")) \
        if "word/numbering.xml" in names else None
    numap = {}
    if numbering is not None:
        abstract = {}
        for an in numbering.findall(_W + "abstractNum"):
            abstract[an.get(_W + "abstractNumId")] = True
        for num in numbering.findall(_W + "num"):
            numap[num.get(_W + "numId")] = num.find(
                _W + "abstractNumId").get(_W + "val")
    return doc, fn, numap


def _independent_text(node) -> str:
    out = []
    for el in node.iter():
        if el.tag in (_W + "t", _W + "delText"):
            out.append(el.text or "")
    return "".join(out)


def _independent_facts(doc, fn) -> dict:
    body = [c for c in doc.find(_W + "body") if c.tag == _W + "p"]
    body_texts = [_independent_text(p) for p in body]
    numbering = []
    for p in body:
        ppr = p.find(_W + "pPr")
        numpr = ppr.find(_W + "numPr") if ppr is not None else None
        nid = numpr.find(_W + "numId") if numpr is not None else None
        numbering.append(nid.get(_W + "val") if nid is not None else None)
    tables = []
    for tbl in [c for c in doc.find(_W + "body") if c.tag == _W + "tbl"]:
        rows = []
        for tr in [c for c in tbl if c.tag == _W + "tr"]:
            rows.append([_independent_text(tc).strip()
                         for tc in [c for c in tr if c.tag == _W + "tc"]])
        tables.append(rows)
    footnotes = {}
    if fn is not None:
        for note in fn.findall(_W + "footnote"):
            if note.get(_W + "type") in ("separator",
                                         "continuationSeparator"):
                continue
            footnotes[note.get(_W + "id")] = _independent_text(note).strip()
    return {"body": body_texts, "numbering": numbering, "tables": tables,
            "footnotes": footnotes}


def _independent_parent(root, target):
    for par in root.iter():
        if target in list(par):
            return par
    return None


def _independent_settle(root, accept: bool):
    """独立 accept/reject：accept=删 del 内容/解 ins/去标记；reject=删
    ins/解 del（delText 保留由文本抽取器计）。"""
    for p in list(root.iter(_W + "p")):
        ppr = p.find(_W + "pPr")
        rpr = ppr.find(_W + "rPr") if ppr is not None else None
        if rpr is None:
            continue
        gone = rpr.find(_W + "del" if accept else _W + "ins")
        if gone is not None:
            parent = _independent_parent(root, p)
            if parent is not None:
                parent.remove(p)
    for tr in list(root.iter(_W + "tr")):
        trpr = tr.find(_W + "trPr")
        if trpr is None:
            continue
        gone = trpr.find(_W + "del" if accept else _W + "ins")
        if gone is not None:
            parent = _independent_parent(root, tr)
            if parent is not None:
                parent.remove(tr)
    for el in list(root.iter()):
        if el.tag not in (_W + "ins", _W + "del"):
            continue
        keep = (el.tag == _W + "ins") if accept else (el.tag == _W + "del")
        parent = _independent_parent(root, el)
        if parent is None:
            continue
        if keep:
            idx = list(parent).index(el)
            for child in list(el):
                parent.insert(idx, child)
                idx += 1
        parent.remove(el)
    for change in list(root.iter(_W + "pPrChange")):
        ppr = _independent_parent(root, change)
        if ppr is None:
            continue
        if accept:
            ppr.remove(change)
        else:
            ppr.clear()
            for child in list(change):
                ppr.append(child)


def independent_dual_invariant(redline_path: Path, baseline_path: Path,
                               replay_path: Path) -> dict:
    """第二实现复核：accept_all(红线)==replay 事实 且 reject_all==基线。"""
    r_doc, r_fn, _ = _independent_parse(redline_path)
    results = {}
    for accept, other in ((True, replay_path), (False, baseline_path)):
        import copy as copy_mod
        doc = copy_mod.deepcopy(r_doc)
        fn = copy_mod.deepcopy(r_fn) if r_fn is not None else None
        _independent_settle(doc, accept)
        if fn is not None:
            _independent_settle(fn, accept)
        other_doc, other_fn, _ = _independent_parse(other)
        results["accept" if accept else "reject"] = (
            _independent_facts(doc, fn)
            == _independent_facts(other_doc, other_fn))
    return results


# --------------------------------------------------------------------------
# 真桥 CLI 子进程径（与产品桌面/服务调用完全同形）
# --------------------------------------------------------------------------

def bridge_call(config: dict, method: str, args: dict,
                timeout: int = 300) -> tuple:
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
            errors="replace", timeout=timeout)
        payload = {}
        if proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = {"raw": proc.stdout[-400:]}
        return proc.returncode, payload
    finally:
        os.unlink(req_name)
        os.unlink(cfg_name)


# --------------------------------------------------------------------------
# profile 主流程
# --------------------------------------------------------------------------

def run_profile(profile: str, args, corpus: Path, soffice: str) -> int:
    evidence_dir = REPO / "docs" / "construction" / "evidence" / "F49" \
        / profile
    state = Path(args.state) if args.state else \
        TEMP / f"juscite-f49-state-{profile}"
    if state.exists() and any(state.iterdir()):
        eprint(f"[{profile}] 状态根非空，另起子目录：{state}")
        state = state / f"run-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    config = {"redline_state_root": str(state)}
    conv_state = state / "f54-side"
    conv_config = {"conversion_state_root": str(conv_state),
                   "libreoffice_soffice": soffice}
    digest_before = corpus_identity_digest(corpus)
    started = now_iso()
    checks: list[dict] = []
    metrics: dict = {}

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    print(f"\n===== profile {profile}（state={state}）=====", flush=True)

    # ------------------------------------------------ C01 干净基版钉定
    rc_reg, res_reg = bridge_call(config, "redline.register", {
        "document_id": "doc-main", "docx_path": str(corpus / "base.docx"),
        "matter_id": "M-SYN-F49"})
    reg = res_reg.get("result", {})
    doc_dir = state / "document-redline" / "doc-main"
    baseline_file = doc_dir / "baseline.docx"
    rc_again, res_again = bridge_call(config, "redline.register", {
        "document_id": "doc-main", "docx_path": str(corpus / "base.docx")})
    rc_mismatch, res_mismatch = bridge_call(config, "redline.register", {
        "document_id": "doc-main",
        "docx_path": str(corpus / "poisoned.docx")})
    pinned_ok = (
        rc_reg == 0 and reg.get("schema") == SCHEMA
        and reg.get("model") == "supported_constructs_gated"
        and baseline_file.is_file()
        and sha256_file(baseline_file) == sha256_file(corpus / "base.docx")
        and reg.get("baseline", {}).get("sha256")
        == sha256_file(corpus / "base.docx")
        and reg.get("facts", {}).get("body_paragraphs") == 7
        and reg.get("facts", {}).get("tables") == 1
        and reg.get("facts", {}).get("footnotes") == 2
        and reg.get("facts", {}).get("numbered_paragraphs") == 2
        and rc_again == 0
        and res_again.get("result", {}).get("baseline", {}).get("sha256")
        == reg["baseline"]["sha256"])
    record("C01_clean_baseline_pinned",
           pinned_ok
           and rc_mismatch == 3
           and "f49_baseline_bytes_mismatch"
           in str(res_mismatch.get("code"))
           and sha256_file(baseline_file)
           == sha256_file(corpus / "base.docx"),
           f"baseline.docx sha==源（{reg.get('facts', {}).get('body_paragraphs')}"
           f"段/{reg.get('facts', {}).get('tables')}表/"
           f"{reg.get('facts', {}).get('footnotes')}脚注/"
           f"{reg.get('facts', {}).get('numbered_paragraphs')}编号段）；"
           f"同字节幂等；同 id 异字节 exit{rc_mismatch}="
           f"{res_mismatch.get('code')} 且盘上基线不动")

    # ------------------------------------------------ C02 干净基版闸
    rc_rev, res_rev = bridge_call(config, "redline.register", {
        "document_id": "doc-poisoned",
        "docx_path": str(corpus / "poisoned.docx")})
    rc_tb, res_tb = bridge_call(config, "redline.register", {
        "document_id": "doc-textbox",
        "docx_path": str(corpus / "textbox.docx")})
    record("C02_clean_gate_negatives",
           rc_rev == 3 and "f49_baseline_has_existing_revisions"
           in str(res_rev.get("code"))
           and rc_tb == 3 and "f49_baseline_unsupported_construct"
           in str(res_tb.get("code"))
           and not (state / "document-redline" / "doc-poisoned"
                    / "baseline.docx").exists()
           and not (state / "document-redline" / "doc-textbox"
                    / "baseline.docx").exists(),
           f"既有修订标记 exit{rc_rev}={res_rev.get('code')}；模型外构件"
           f"（文本框结构）exit{rc_tb}={res_tb.get('code')}；拒后零残留")

    # ------------------------------------------------ C03 提案 replay（渲染解耦）
    rc_rp1, res_rp1 = bridge_call(config, "redline.replay", {
        "document_id": "doc-main", "proposal": PROPOSAL_MAIN})
    rp1 = res_rp1.get("result", {})
    rc_rp2, res_rp2 = bridge_call(config, "redline.replay", {
        "document_id": "doc-main", "proposal": PROPOSAL_MAIN})
    rp2 = res_rp2.get("result", {})
    replay1 = doc_dir / rp1.get("replay", {}).get("file", "?")
    replay2 = doc_dir / rp2.get("replay", {}).get("file", "?")
    record("C03_replay_decoupled_deterministic",
           rc_rp1 == 0 and rc_rp2 == 0
           and rp1.get("ops_applied") == 6
           and rp1.get("author") == "lvyin-redline"
           and replay1.is_file() and replay2.is_file()
           and rp1.get("proposal_id") != rp2.get("proposal_id")
           and sha256_file(replay1) == sha256_file(replay2)
           and rp1.get("replay_facts", {}).get("facts_digest")
           != rp1.get("baseline_facts", {}).get("facts_digest")
           and sha256_file(replay1) != sha256_file(baseline_file),
           f"两跑 replay 字节级相同（sha={str(rp1.get('replay', {}).get('sha256'))[:16]}"
           "…）；独立在盘工件；事实分叉（提案产生变更）；append-only 新序号 "
           f"{rp1.get('proposal_id')}→{rp2.get('proposal_id')}")

    # ------------------------------------------------ C04 compareDocuments 真修订
    rc_cmp, res_cmp = bridge_call(config, "redline.compare", {
        "document_id": "doc-main", "proposal_id": rp1["proposal_id"]})
    cmp_view = res_cmp.get("result", {})
    redline_file = doc_dir / cmp_view.get("redline", {}).get("file", "?")
    doc_part = fn_part = ""
    if redline_file.is_file():
        with zipfile.ZipFile(redline_file) as zf:
            doc_part = zf.read("word/document.xml").decode("utf-8")
            fn_part = zf.read("word/footnotes.xml").decode("utf-8")
    markup_ok = (
        rc_cmp == 0 and cmp_view.get("schema") == SCHEMA
        and "<w:ins " in doc_part and "<w:del " in doc_part
        and "<w:delText" in doc_part and "<w:pPrChange" in doc_part
        and "<w:delText" in fn_part
        and 'w:author="lvyin-redline"' in doc_part
        and 'w:date="2026-10-16T00:00:00Z"' in doc_part)
    rec = cmp_view.get("reconciliation", {})
    record("C04_compare_documents_true_revisions",
           markup_ok
           and rec.get("accept_all_equals_replay") is True
           and rec.get("reject_all_equals_baseline") is True
           and rec.get("readback_content_complete") is True,
           f"红线 docx 携真 OOXML 修订标记（w:ins/w:del/delText/pPrChange/"
           f"脚注 delText）；作者日期＝提案声明透传；面内对账双不变式成立；"
           f"redline={str(cmp_view.get('redline', {}).get('sha256'))[:16]}…")

    # ------------------------------------------------ C05 独立对账复核
    indep = independent_dual_invariant(redline_file, baseline_file,
                                       replay1) \
        if redline_file.is_file() else {"accept": False, "reject": False}
    record("C05_independent_dual_invariant_recheck",
           indep.get("accept") is True and indep.get("reject") is True,
           "第二实现（不复用产品面代码）独立变换复核：accept_all(红线)=="
           f"replay 四类事实={indep.get('accept')}；reject_all==基线="
           f"{indep.get('reject')}（正文/表格/脚注/编号）")

    # ------------------------------------------------ C06 内容回读（四类齐全）
    revs = cmp_view.get("revisions", {})
    by_cat = revs.get("by_category", {})
    items = revs.get("items", [])
    numbering_rev = [r for r in items
                     if r.get("kind") == "paragraph_property_change"]
    foot_rev = [r for r in items if r.get("category") == "footnote"]
    cell_rev = [r for r in items if r.get("kind") == "text_replace"
                and "table" in r]
    body_ins = [r for r in items if r.get("kind") == "paragraph_insert"]
    body_del = [r for r in items if r.get("kind") == "paragraph_delete"]
    cell_target = [r for r in cell_rev if r.get("table") == 0
                   and r.get("row") == 2 and r.get("col") == 2]
    record("C06_readback_all_categories_with_content",
           all(by_cat.get(c, 0) >= 1 for c in
               ("body", "table", "footnote", "numbering"))
           and body_ins and body_ins[0].get("after_text")
           and body_del and body_del[0].get("before_text")
           and cell_target
           and cell_target[0].get("before_text") == "12,000.00"
           and cell_target[0].get("after_text") == "12,500.00"
           and foot_rev
           and foot_rev[0].get("before_text") == FOOTNOTES[2]
           and "修订版" in foot_rev[0].get("after_text", "")
           and numbering_rev
           and numbering_rev[0].get("old_num_id") == "1"
           and numbering_rev[0].get("new_num_id") == "2",
           f"四类齐全 body={by_cat.get('body')}/table={by_cat.get('table')}/"
           f"footnote={by_cat.get('footnote')}/numbering="
           f"{by_cat.get('numbering')}；表格格双侧全文 12,000.00→12,500.00；"
           "脚注双侧全文回读；编号 numId 1→2 可回读")
    metrics["revisions_by_category"] = by_cat
    metrics["revision_count"] = revs.get("count")

    # ------------------------------------------------ C07 行级修订＋append-only
    first_redline_sha = sha256_file(redline_file) if redline_file.is_file() \
        else ""
    first_replay_sha = sha256_file(replay1) if replay1.is_file() else ""
    rc_rp3, res_rp3 = bridge_call(config, "redline.replay", {
        "document_id": "doc-main", "proposal": PROPOSAL_ROWS})
    rp3 = res_rp3.get("result", {})
    rc_cmp2, res_cmp2 = bridge_call(config, "redline.compare", {
        "document_id": "doc-main", "proposal_id": rp3.get("proposal_id")})
    cmp2 = res_cmp2.get("result", {})
    kinds = {r.get("kind"): r for r in cmp2.get("revisions", {}).get(
        "items", [])}
    rc_list, res_list = bridge_call(config, "redline.list",
                                    {"document_id": "doc-main"})
    listing = res_list.get("result", {})
    on_disk = sorted(p.parent.name for p in
                     (doc_dir / "redlines").glob("*/redline.json"))
    listed = sorted(r["redline_id"].split(":")[1]
                    for r in listing.get("redlines", []))
    record("C07_row_revisions_and_append_only",
           rc_rp3 == 0 and rc_cmp2 == 0
           and "row_delete" in kinds and "row_insert" in kinds
           and kinds.get("row_delete", {}).get("cells") == TABLE_ROWS[1]
           and kinds.get("row_insert", {}).get("cells")
           == ["3", "2026-04-05", "12,000.00"]
           and cmp2.get("reconciliation", {}).get(
               "accept_all_equals_replay") is True
           and sha256_file(redline_file) == first_redline_sha
           and sha256_file(replay1) == first_replay_sha
           and rc_list == 0 and on_disk == listed
           and len(listing.get("redlines", [])) == 2,
           f"行删/行插携格内容回读（{kinds.get('row_delete', {}).get('cells')}"
           f" 删/{kinds.get('row_insert', {}).get('cells')} 插）；旧红线/"
           "旧 replay 字节不动；list 与盘一一对应（0001/0002，无孤儿）")

    # ------------------------------------------------ C08 F54 管线衔接
    rc_rb, res_rb = bridge_call(conv_config, "conversion.rebuild", {
        "document_id": "link-src", "pdf_path": str(corpus / "link.pdf")})
    rebuild_view = res_rb.get("result", {})
    rc_cand, res_cand = bridge_call(conv_config, "conversion.candidate", {
        "candidate_id": rebuild_view.get("candidate_id")})
    cand_b64 = res_cand.get("result", {}).get("docx_b64")
    rc_link_reg, res_link_reg = bridge_call(config, "redline.register", {
        "document_id": "doc-f54link", "docx_b64": cand_b64})
    link_reg = res_link_reg.get("result", {})
    rc_eng, res_eng = bridge_call(conv_config, "conversion.engine", {})
    engine = res_eng.get("result", {})
    lo_refused = None
    if engine.get("status") == "READY":
        rc_lo, res_lo = bridge_call(conv_config, "conversion.convert", {
            "document_id": "link-lo", "pdf_path": str(corpus / "link.pdf")},
            timeout=600)
        lo_view = res_lo.get("result", {})
        rc_lo_cand, res_lo_cand = bridge_call(
            conv_config, "conversion.candidate",
            {"candidate_id": lo_view.get("candidate_id")})
        rc_lo_reg, res_lo_reg = bridge_call(config, "redline.register", {
            "document_id": "doc-f54lo",
            "docx_b64": res_lo_cand.get("result", {}).get("docx_b64")})
        lo_refused = (rc_lo == 0
                      and rc_lo_reg == 3
                      and "f49_baseline_unsupported_construct"
                      in str(res_lo_reg.get("code")))
    link_ok = (
        rc_rb == 0 and rebuild_view.get("redline", {}).get("route")
        == "revision_line" and cand_b64
        and rc_link_reg == 0 and link_reg.get("schema") == SCHEMA
        and link_reg.get("facts", {}).get("body_paragraphs", 0) > 0)
    record("C08_f54_pipeline_linkage",
           link_ok and (lo_refused in (True, None)),
           f"conversion.rebuild 候选（平铺 OOXML，route=revision_line）b64 "
           f"取件→redline.register 可入修订线（{link_reg.get('facts', {}).get('body_paragraphs')}段"
           f"）；LibreOffice 候选（文本框结构）＝"
           + ("干净基版闸具名拒（f49_baseline_unsupported_construct）"
              if lo_refused is True else
              ("引擎未装如实 skipped_env" if lo_refused is None
               else "未如预期拒（FAIL）")))
    metrics["f54_linkage"] = {"rebuild_route": rebuild_view.get(
        "redline", {}).get("route"),
        "libreoffice_refused": lo_refused,
        "engine": engine.get("status")}

    # ------------------------------------------------ C09 消费契约＋确定性
    rc_rep, res_rep = bridge_call(config, "redline.report", {
        "redline_id": cmp_view.get("redline_id")})
    rep = res_rep.get("result", {})
    rc_b64, res_b64 = bridge_call(config, "redline.redline", {
        "redline_id": cmp_view.get("redline_id")})
    blob = res_b64.get("result", {})
    b64_ok = blob.get("docx_b64") and redline_file.is_file() and \
        base64.b64decode(blob["docx_b64"]) == redline_file.read_bytes()
    digest = cmp_view.get("redline", {}).get("content_digest")
    cross = _CROSS_PROFILE_DIGEST.setdefault("main", digest)
    valid_zip = False
    if redline_file.is_file():
        try:
            with zipfile.ZipFile(redline_file) as zf:
                valid_zip = zf.testzip() is None and "word/document.xml" \
                    in zf.namelist()
        except zipfile.BadZipFile:
            valid_zip = False
    record("C09_consumer_contract_and_determinism",
           rc_rep == 0 and rep.get("redline", {}).get("sha256")
           == cmp_view.get("redline", {}).get("sha256")
           and rep.get("consumers") == ["W2b-U16-wps-host",
                                        "E13-docx-closeout"]
           and rc_b64 == 0 and b64_ok
           and blob.get("revision_count") == revs.get("count")
           and valid_zip
           and digest and cross == digest,
           f"report 回读==清单；b64 取件==盘上字节；consumers="
           f"{rep.get('consumers')}（U16 WPS 宿主验证/E13 收口）；zip 合法；"
           f"跨 profile 同基线同提案 content_digest 相等"
           f"（{str(digest)[:16]}…）")

    # ------------------------------------------------ C10 桥 fail-closed 负向
    rc_nc, res_nc = bridge_call({}, "redline.list", {"document_id": "x"})
    rc_unknown, res_unknown = bridge_call(config, "redline.explode", {})
    rc_badid, res_badid = bridge_call(config, "redline.register", {
        "document_id": "../escape",
        "docx_path": str(corpus / "base.docx")})
    rc_badprop, res_badprop = bridge_call(config, "redline.replay", {
        "document_id": "doc-main", "proposal": {
            "author": "a", "authored_utc": "2026-10-16T00:00:00Z",
            "ops": [{"op": "body.explode"}]}})
    rc_unreg, res_unreg = bridge_call(config, "redline.replay", {
        "document_id": "doc-none", "proposal": PROPOSAL_MAIN})
    rc_notfound, res_notfound = bridge_call(config, "redline.report", {
        "redline_id": "doc-main:9999-compare"})
    code_shape = re.compile(r"^[\w:.;-]+$")
    codes = [str(res_nc.get("code")), str(res_unknown.get("code")),
             str(res_badid.get("code")), str(res_badprop.get("code")),
             str(res_unreg.get("code")), str(res_notfound.get("code"))]
    record("C10_bridge_fail_closed_negatives",
           rc_nc == 3 and "redline_failed:f49_state_root_not_configured"
           in str(res_nc.get("code"))
           and rc_unknown == 3
           and "method_not_connected:redline.explode"
           in str(res_unknown.get("code"))
           and rc_badid == 3 and "f49_document_id_invalid"
           in str(res_badid.get("code"))
           and rc_badprop == 3 and "f49_proposal_op_unknown"
           in str(res_badprop.get("code"))
           and rc_unreg == 3 and "f49_document_not_registered"
           in str(res_unreg.get("code"))
           and rc_notfound == 3 and "f49_redline_not_found"
           in str(res_notfound.get("code"))
           and all(code_shape.match(c) for c in codes),
           f"缺状态根 exit{rc_nc}；未知方法 exit{rc_unknown}；坏 id "
           f"exit{rc_badid}；坏算子 exit{rc_badprop}；未注册 exit{rc_unreg}；"
           f"未找到 exit{rc_notfound}；错误码纯码不携材料内容")
    metrics["negative_codes"] = codes

    # ------------------------------------------------ C11 语料只读锚
    digest_after = corpus_identity_digest(corpus)
    record("C11_corpus_anchor_readonly",
           digest_after == digest_before,
           f"跑前后 sha256(identity) 相同＝{digest_after == digest_before} "
           f"（{digest_after[:16]}…）")

    ok = all(c["ok"] for c in checks)
    verdict = "RECON_OK" if ok else "RECON_FAIL"
    result = {
        "obligation": "06:F49/17卡 干净基版与提案replay对比产真修订"
                      "（compareDocuments 差量，非会话内打标）；表格/脚注/"
                      "编号有内容回读；产物红线 DOCX 供 W2b-U16 WPS 宿主"
                      "验证与 E13 收口消费",
        "unit": "W2b-U14",
        "profile": profile,
        "started_utc": started,
        "finished_utc": now_iso(),
        "verdict": verdict,
        "corpus": {"root": str(corpus),
                   "identity_digest": digest_before,
                   "readonly_unchanged": digest_after == digest_before,
                   "materials": "全合成（自建富 OOXML＋reportlab；裁决#1）"},
        "state_root": str(state),
        "redline_sha256": cmp_view.get("redline", {}).get("sha256"),
        "redline_content_digest": cmp_view.get("redline", {}).get(
            "content_digest"),
        "revisions": metrics.get("revisions_by_category"),
        "revision_count": metrics.get("revision_count"),
        "f54_linkage": metrics.get("f54_linkage"),
        "checks": checks,
        "metrics": metrics,
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_json = evidence_dir / "f49-replay-redline-recon-result.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8", newline="\n")
    md = [f"# F49 replay 红线 recon（{profile}）",
          "",
          f"- verdict: **{verdict}**（{sum(c['ok'] for c in checks)}/"
          f"{len(checks)} checks）",
          f"- unit: W2b-U14 · profile: {profile}",
          f"- 红线产物: redline.docx sha256="
          f"{str(cmp_view.get('redline', {}).get('sha256'))[:16]}…"
          f"（content_digest="
          f"{str(cmp_view.get('redline', {}).get('content_digest'))[:16]}…，"
          "字节级确定）",
          f"- 修订分布: {metrics.get('revisions_by_category')}"
          f"（共 {metrics.get('revision_count')} 条，四类内容全回读）",
          f"- F54 管线衔接: {metrics.get('f54_linkage')}",
          f"- 语料: 全合成 · 只读锚 {digest_before[:16]}…",
          f"- state: `{state}`",
          "",
          "| check | 结果 |", "|---|---|"]
    md += [f"| {c['check']} | {'PASS' if c['ok'] else 'FAIL'} |"
           for c in checks]
    (evidence_dir / "f49-replay-redline-recon.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8", newline="\n")
    print(f"\n[{profile}] {verdict}  ({sum(c['ok'] for c in checks)}/"
          f"{len(checks)} checks)  证据 → {out_json}", flush=True)
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append",
                    choices=["desktop", "selfhost"], default=None)
    ap.add_argument("--corpus", metavar="DIR", default=None,
                    help="合成语料目录（默认 %%TEMP%%\\juscite-f49-corpus）")
    ap.add_argument("--state", metavar="DIR", default=None,
                    help="显式状态根（默认按 profile 分 TEMP 子目录）")
    ap.add_argument("--soffice", metavar="PATH", default=None,
                    help="soffice 可执行路径（默认 C:\\Program Files\\"
                         "LibreOffice\\program\\soffice.exe 或环境变量 "
                         "JUSCITE_LIBREOFFICE；未装时 C08 LibreOffice 段"
                         "如实 skipped_env）")
    args = ap.parse_args()
    profiles = args.profile or ["desktop"]
    soffice = args.soffice or os.environ.get("JUSCITE_LIBREOFFICE") \
        or DEFAULT_SOFFICE
    corpus = Path(args.corpus) if args.corpus else \
        TEMP / "juscite-f49-corpus"
    if not ensure_corpus(corpus):
        eprint("[ENV] 合成语料生成失败")
        return 3
    if args.state is not None and len(profiles) > 1:
        eprint("[ENV] 多 profile 共用显式状态根会互相污染，拒绝")
        return 3
    exit_code = 0
    for profile in profiles:
        rc = run_profile(profile, args, corpus, soffice)
        exit_code = exit_code or rc
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
