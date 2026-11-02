#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F55+F58 义务验收 recon（W4-U37）：独立文档对比（双栏/三窗格+变更清单）
＋红线/对比产物导出 PDF——双 profile（desktop/selfhost）四实例一跑。

义务 06:F55 断言：「两份实际文件本地对比与变更清单对应，PDF/DOCX范围有
明确支持」；06:F58 断言：「真实红线/对比PDF可阅读打印并保变更范围；失败
不交空PDF」（preserved：F58 随 F55 立项，故同单）。17 卡两卡 target=
新产品 document-adapter（F54 conversion.*/F49 redline.* 同族落点）＋
Harness 正式材料，entries P02/P04。

硬门（每 profile，真桥 CLI 子进程径）：
- C01 DOCX↔DOCX 对比：确定性差量＋变更清单（替换/插入/表行/脚注增）＋
  对应三不变式回执＋范围显式声明（supported_modes/docx_docx 闭集）。
- C02 变更清单逐项对应＝工具侧独立复核：第二实现（recon 自带 difflib
  对齐）重算 kinds 序列与变更数逐项相等；清单侧文本⊆实际登记文件分段；
  覆盖回放（消费左/右档序列==分段序列）。
- C03 PDF↔PDF 对比：逐页文本行差量＋页/行定位＋无文本层如实计数。
- C04 范围门负向：docx↔pdf 跨类具名拒；txt 未支持具名拒；仅编号差
  （可见段零差量）具名拒不假「无变化」；同档对比零变更诚实回执。
- C05 双留存＋append-only：登记字节钉定、同 id 异字节拒、对比目录追加
  不改、list 与盘上一一对应（无孤儿）。
- C06 确定性：同输入两状态根 payload_digest 相等；跨 profile 同摘要锚。
- C07 F58 红线导出：真 U14 链（redline.register/replay/compare）→
  redline.redline b64 面取件 → LibreOffice headless 真渲染 → PDF 页数
  ≥1＋文本行≥1（可阅读打印）＋保变更范围（run 级 PDF 文本层实测
  checked==matched）＋report 回读/list。
- C08 F58 对比产物导出：自 F55 comparison.json 确定性生成报告 DOCX→
  渲染→逐变更项 before/after 双侧核对全中。
- C09 失败不交空 PDF：坏 XML 渲染失败 typed 拒＋零文本不可读 typed 拒
  ＋失败零残留（导出目录无半成品）。
- C10 桥 fail-closed 负向（两方法组未知方法/缺状态根/坏 id/缺文件）＋
  错误码纯码不携材料内容。
- C11 语料只读锚（跑前后同摘要）。

语料全合成（reportlab＋自建 OOXML；00-总协调 §6.1 裁决#1，绝无真实文档）。
LibreOffice UserInstallation 隔离于状态根（绝不写 %APPDATA%）。

用法（juscite worktree w4-u37 仓根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f55_f58_compare_pdf_recon.py \
      --profile desktop --profile selfhost

退出码：0＝全部 profile RECON_OK；2＝RECON_FAIL；3＝环境缺失。
证据：docs/construction/evidence/F55/<profile>/ 与 F58/<profile>/ JSON＋MD。
"""
from __future__ import annotations

import argparse
import base64
import difflib
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

REPO = Path(__file__).resolve().parents[2]
TEMP = Path(os.environ.get("TEMP", "."))
BRIDGE = REPO / "implementation" / "python" / "legal_entry.py"
SCHEMA_F55 = "juscite-f55-document-compare/1"
SCHEMA_F58 = "juscite-f58-document-export/1"
DEFAULT_SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"

# 跨 profile 确定性锚（同字节同摘要；run 内共享）
_CROSS_PROFILE_DIGESTS: dict[str, str] = {}

_W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


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
# 全合成语料（自建 OOXML＋reportlab；确定性内容，无 RNG 依赖）
# --------------------------------------------------------------------------

def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _p(text: str, num_id=None, footnote_ids=()) -> str:
    ppr = ""
    if num_id is not None:
        ppr = ('<w:pPr><w:numPr><w:ilvl w:val="0"/>'
               f'<w:numId w:val="{num_id}"/></w:numPr></w:pPr>')
    run = (f'<w:r><w:t xml:space="preserve">{_esc(text)}</w:t></w:r>'
           if text else "")
    refs = "".join(f'<w:r><w:footnoteReference w:id="{fid}"/></w:r>'
                   for fid in footnote_ids)
    return f"<w:p>{ppr}{run}{refs}</w:p>"


def _tbl(rows) -> str:
    grid = '<w:gridCol w:w="2400"/>' * len(rows[0])
    trs = "".join(
        "<w:tr>" + "".join(
            '<w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>'
            + _p(cell) + "</w:tc>" for cell in row) + "</w:tr>"
        for row in rows)
    return ('<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid>{trs}</w:tbl>')


def build_docx(body_parts, numbering=False, footnotes=None) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        f'<w:document xmlns:w="{_W_URI}"><w:body>'
        + "".join(body_parts)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
          "</w:body></w:document>")
    parts = {"word/document.xml": document}
    ct_overrides = ['<Override PartName="/word/document.xml" '
                    'ContentType="application/vnd.openxmlformats-'
                    'officedocument.wordprocessingml.document.main+xml"/>']
    rels_entries = []
    if numbering:
        parts["word/numbering.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
            f'<w:numbering xmlns:w="{_W_URI}">'
            '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0">'
            '<w:start w:val="1"/><w:numFmt w:val="decimal"/>'
            '<w:lvlText w:val="%1."/><w:lvlJc w:val="left"/></w:lvl>'
            "</w:abstractNum>"
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
            "</w:numbering>")
        ct_overrides.append('<Override PartName="/word/numbering.xml" '
                            'ContentType="application/vnd.'
                            'openxmlformats-officedocument.'
                            'wordprocessingml.numbering+xml"/>')
        rels_entries.append(
            '<Relationship Id="rId2" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/'
            'numbering" Target="numbering.xml"/>')
    if footnotes:
        parts["word/footnotes.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
            f'<w:footnotes xmlns:w="{_W_URI}">'
            '<w:footnote w:type="separator" w:id="-1"><w:p><w:r>'
            '<w:separator/></w:r></w:p></w:footnote>'
            '<w:footnote w:type="continuationSeparator" w:id="0"><w:p>'
            '<w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
            + "".join(
                f'<w:footnote w:id="{fid}"><w:p><w:r><w:t xml:space='
                f'"preserve">{_esc(text)}</w:t></w:r></w:p></w:footnote>'
                for fid, text in footnotes.items())
            + "</w:footnotes>")
        ct_overrides.append('<Override PartName="/word/footnotes.xml" '
                            'ContentType="application/vnd.'
                            'openxmlformats-officedocument.'
                            'wordprocessingml.footnotes+xml"/>')
        rels_entries.append(
            '<Relationship Id="rId3" Type="http://schemas.'
            'openxmlformats.org/officeDocument/2006/relationships/'
            'footnotes" Target="footnotes.xml"/>')
    parts["[Content_Types].xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types"><Default Extension="rels" ContentType='
        '"application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        + "".join(ct_overrides) + "</Types>")
    parts["_rels/.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/'
        'officeDocument" Target="word/document.xml"/></Relationships>')
    parts["word/_rels/document.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
        '2006/relationships">' + "".join(rels_entries) + "</Relationships>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in parts.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, text.encode("utf-8"))
    return buf.getvalue()


BODY_V1 = [
    _p("合成测试卷宗：原告张三与被告李四买卖合同纠纷（全部当事人、案号与金额均为合成虚构材料）"),
    _p("第一条 合同价款：人民币36,000.00元整"),
    _p("付款安排：分三期支付"),
    _p("第三条 争议解决"),
    _tbl([["期次", "应付日期", "本金（元）"],
          ["1", "2026-02-05", "12,000.00"],
          ["2", "2026-03-05", "12,000.00"]]),
    _p("本卷全部内容为合成测试材料，不代表任何真实案件。"),
]
BODY_V2 = [
    BODY_V1[0],
    _p("第一条 合同价款：人民币38,500.00元整（含税费）"),
    BODY_V1[2],
    _p("第二条之一 质量保证期：自验收合格之日起二十四个月。"),
    BODY_V1[3],
    _tbl([["期次", "应付日期", "本金（元）"],
          ["1", "2026-02-05", "12,500.00"],
          ["2", "2026-03-05", "12,000.00"]]),
    BODY_V1[5],
]

# F49 语料（W2b-U14 夹具同构——红线源走真 U14 链；脚注 1 在正文带引用，
# 无引用脚注 LibreOffice 渲染不呈现＝保范围核对如实拒，W4-U37 实测钉定）
F49_BODY = [
    _p("合成测试卷宗：原告张三与被告李四买卖合同纠纷（全部当事人、案号与金额均为合成虚构材料）"),
    _p("第一条 合同价款：人民币36,000.00元整", footnote_ids=[1]),
    _p("付款安排：分三期支付"),
    _p("第二条 交付与验收"),
    _tbl([["期次", "应付日期", "本金（元）"],
          ["1", "2026-02-05", "12,000.00"],
          ["2", "2026-03-05", "12,000.00"]]),
    _p("付款安排：逾期付款违约金按日万分之五计"),
    _p("第三条 争议解决"),
    _p("本卷全部内容为合成测试材料，不代表任何真实案件。"),
]
F49_PROPOSAL = {
    "author": "lvyin-redline",
    "authored_utc": "2026-10-20T00:00:00Z",
    "ops": [
        {"op": "body.replace_text", "index": 1,
         "text": "第一条 合同价款：人民币38,500.00元整（含税费）"},
        {"op": "body.insert_paragraph", "index": 3,
         "text": "第二条之一 质量保证期：自验收合格之日起二十四个月。"},
        {"op": "table.cell_text", "table": 0, "row": 2, "col": 2,
         "text": "12,500.00"},
        {"op": "footnote.replace_text", "id": 1,
         "text": "合成脚注一：三期付款日期均为合成示例日期（修订版）。"},
    ],
}


def build_pdf(lines_per_page: list) -> bytes:
    import io as _io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buf = _io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    for page_lines in lines_per_page:
        c.setFont("STSong-Light", 12)
        for i, line in enumerate(page_lines):
            c.drawString(72, A4[1] - 100 - i * 24, line)
        c.showPage()
    c.save()
    return buf.getvalue()


PDF_V1 = build_pdf([
    ["合成测试对比档 F55-RECON（全部内容为合成虚构材料）",
     "第一条 合同价款：人民币36,000.00元整",
     "付款安排：分三期支付",
     "第三条 争议解决"],
    ["第二页：交付与验收条款为合成示例文本。",
     "本卷全部内容为合成测试材料，不代表任何真实案件。"],
])
PDF_V2 = build_pdf([
    ["合成测试对比档 F55-RECON（全部内容为合成虚构材料）",
     "第一条 合同价款：人民币38,500.00元整（含税费）",
     "付款安排：分三期支付",
     "第三条 争议解决"],
    ["第二页：交付与验收条款为合成示例文本（修订版）。",
     "本卷全部内容为合成测试材料，不代表任何真实案件。"],
])

CORPUS_FILES = ("docx_v1.docx", "docx_v2.docx", "pdf_v1.pdf", "pdf_v2.pdf",
                "f49_baseline.docx")


def ensure_corpus(corpus: Path) -> bool:
    if all((corpus / n).is_file() for n in CORPUS_FILES):
        return True
    corpus.mkdir(parents=True, exist_ok=True)
    eprint(f"[GEN] 合成语料不存在，生成 → {corpus}")
    (corpus / "docx_v1.docx").write_bytes(
        build_docx(BODY_V1, numbering=True,
                   footnotes={1: "合成脚注一：三期付款日期均为合成示例日期。"}))
    (corpus / "docx_v2.docx").write_bytes(
        build_docx(BODY_V2, numbering=True,
                   footnotes={1: "合成脚注一：三期付款日期均为合成示例日期。",
                              2: "合成脚注二：争议解决条文为合成示例文本（修订版）。"}))
    (corpus / "pdf_v1.pdf").write_bytes(PDF_V1)
    (corpus / "pdf_v2.pdf").write_bytes(PDF_V2)
    (corpus / "f49_baseline.docx").write_bytes(
        build_docx(F49_BODY, numbering=True,
                   footnotes={1: "合成脚注一：三期付款日期均为合成示例日期。"}))
    return all((corpus / n).is_file() for n in CORPUS_FILES)


def corpus_identity_digest(corpus: Path) -> str:
    parts = [sha256_file(corpus / n) for n in CORPUS_FILES]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 真桥 CLI 子进程径（与产品桌面/服务调用完全同形）
# --------------------------------------------------------------------------

def bridge_call(config: dict, method: str, args: dict,
                timeout: int = 900) -> tuple[int, dict]:
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
# 工具侧独立第二实现（变更清单对应独立复核；不 import 产品面对齐代码）
# --------------------------------------------------------------------------

def _expected_kinds(left_texts: list, right_texts: list) -> list:
    pairs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, left_texts, right_texts, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        for k in range(max(i2 - i1, j2 - j1)):
            a = i1 + k if k < i2 - i1 else None
            b = j1 + k if k < j2 - j1 else None
            pairs.append((a, b))
    return [("insert" if a is None else "delete" if b is None
             else "replace") for a, b in pairs]


def _docx_segment_texts(docx_path: Path) -> list:
    """独立分段抽取（第二实现：zipfile＋ET，含表格行/脚注）。"""
    import xml.etree.ElementTree as ET
    _W = "{%s}" % _W_URI
    _MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
    with zipfile.ZipFile(docx_path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
        fn_root = (ET.fromstring(zf.read("word/footnotes.xml"))
                   if "word/footnotes.xml" in zf.namelist() else None)
    parent = {c: p for p in root.iter() for c in p}

    def all_t(node):
        out = []
        for el in node.iter(_W + "t"):
            p, fb = el, False
            while p in parent:
                p = parent[p]
                if p.tag == _MC + "Fallback":
                    fb = True
                    break
            if not fb:
                out.append(el.text or "")
        return out

    texts = []
    body = root.find(_W + "body")
    for child in body:
        if child.tag == _MC + "Fallback":
            continue
        if child.tag == _W + "p":
            texts.append("".join(all_t(child)))
        elif child.tag == _W + "tbl":
            for tr in child.findall(_W + "tr"):
                texts.append(" | ".join(
                    "".join(all_t(tc)).strip()
                    for tc in tr.findall(_W + "tc")))
    if fn_root is not None:
        entries = []
        for fn in fn_root.findall(_W + "footnote"):
            if fn.get(_W + "type") in ("separator", "continuationSeparator"):
                continue
            entries.append((int(fn.get(_W + "id") or 0), "\n".join(
                "".join(all_t(p)) for p in fn.findall(_W + "p")).strip()))
        for _fid, text in sorted(entries):
            texts.append(text)
    return texts


def _pdf_segment_texts(pdf_path: Path) -> list:
    sys.path.insert(0, str(REPO / "implementation" / "python"))
    from pdf_conversion import pdf_facts
    facts = pdf_facts(pdf_path)
    return [line["text"] for page in facts["pages"]
            for line in page["lines"]]


# --------------------------------------------------------------------------
# 单 profile recon
# --------------------------------------------------------------------------

def run_profile(profile: str, args, corpus: Path, soffice: str) -> int:
    evidence_f55 = REPO / "docs" / "construction" / "evidence" / "F55" \
        / profile
    evidence_f58 = REPO / "docs" / "construction" / "evidence" / "F58" \
        / profile
    state = Path(args.state) if args.state else \
        TEMP / f"juscite-f55-f58-state-{profile}"
    if state.exists() and any(state.iterdir()):
        eprint(f"[{profile}] 状态根非空，另起子目录：{state}")
        state = state / f"run-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    cmp_state = state / "cmp"
    exp_state = state / "exp"
    red_state = state / "red"
    cfg_cmp = {"doccompare_state_root": str(cmp_state)}
    cfg_red = {"redline_state_root": str(red_state)}
    cfg_exp = {"docexport_state_root": str(exp_state),
               "libreoffice_soffice": soffice,
               "redline_state_root": str(red_state),
               "doccompare_state_root": str(cmp_state)}
    digest_before = corpus_identity_digest(corpus)
    started = now_iso()
    checks: list[dict] = []
    metrics: dict = {}

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    print(f"\n===== profile {profile}（state={state}）=====", flush=True)

    # ------------------------------------------------ C01 DOCX↔DOCX 对比＋范围声明
    rc_a, res_a = bridge_call(cfg_cmp, "doccompare.compare", {
        "document_id": "docx-pair", "matter_id": "M-SYN-F55",
        "left_path": str(corpus / "docx_v1.docx"),
        "right_path": str(corpus / "docx_v2.docx")})
    view_a = res_a.get("result", {})
    changes = view_a.get("changes", {})
    range_ok = (view_a.get("range", {}).get("declared") is True
                and view_a.get("range", {}).get("mode") == "docx_docx"
                and view_a.get("range", {}).get("supported_modes")
                == ["docx_docx", "pdf_pdf"]
                and view_a.get("schema") == SCHEMA_F55)
    corr = view_a.get("correspondence", {})
    record("C01_docx_compare_range_declared_and_changes",
           rc_a == 0 and range_ok
           and changes.get("count", 0) >= 4
           and set(changes.get("by_kind", {})) >= {"replace", "insert"}
           and set(changes.get("by_category", {})) >= {"paragraph",
                                                       "table_row"}
           and corr == {"bijection": True, "coverage": True, "sides": True},
           f"exit{rc_a} mode={view_a.get('mode')} range 声明齐（supported="
           f"{view_a.get('range', {}).get('supported_modes')}）变更 "
           f"{changes.get('count')}（by_kind={changes.get('by_kind')}·"
           f"by_category={changes.get('by_category')}）对应三不变式回执全真")

    # ------------------------------------------------ C02 变更清单逐项对应（独立复核）
    rc_rep, res_rep = bridge_call(cfg_cmp, "doccompare.report", {
        "comparison_id": view_a.get("comparison_id")})
    rep = res_rep.get("result", {})
    items = rep.get("change_items", [])
    left_texts = _docx_segment_texts(corpus / "docx_v1.docx")
    right_texts = _docx_segment_texts(corpus / "docx_v2.docx")
    expect_kinds = _expected_kinds(left_texts, right_texts)
    got_kinds = [c["kind"] for c in items]
    left_set = set(left_texts)
    right_set = set(right_texts)
    sides_ok = all(
        (c["before_text"] in left_set or c["before_text"] == "")
        and (c["after_text"] in right_set or c["after_text"] == "")
        for c in items)
    coverage_ok = (len(items) == len(expect_kinds)
                   and sides_ok)
    kinds_match = got_kinds == expect_kinds
    bijection_ok = all(re.fullmatch(r"c\d{3}", c["id"])
                       and re.fullmatch(r"r\d{4}", c["row_id"])
                       for c in items) and len(
        {c["id"] for c in items}) == len(items)
    record("C02_change_list_correspondence_independent_recheck",
           rc_rep == 0 and rep.get("schema") == SCHEMA_F55
           and kinds_match and coverage_ok and bijection_ok,
           f"第二实现重算 kinds 序列逐项相等={kinds_match}（{got_kinds}）；"
           f"变更数==重算数 {len(items)}=={len(expect_kinds)}；清单侧文本"
           f"⊆实际登记文件分段={sides_ok}；id/row_id 双射形={bijection_ok}")

    # ------------------------------------------------ C03 PDF↔PDF 对比
    rc_p, res_p = bridge_call(cfg_cmp, "doccompare.compare", {
        "document_id": "pdf-pair",
        "left_path": str(corpus / "pdf_v1.pdf"),
        "right_path": str(corpus / "pdf_v2.pdf")})
    view_p = res_p.get("result", {})
    rc_pr, res_pr = bridge_call(cfg_cmp, "doccompare.report", {
        "comparison_id": view_p.get("comparison_id")})
    rep_p = res_pr.get("result", {})
    pdf_items = rep_p.get("change_items", [])
    loc_ok = all(
        isinstance(c.get("left_location") or c.get("right_location"), dict)
        for c in pdf_items)
    pages_meta = view_p.get("pdf_pages_without_text", {})
    pdf_text_joined = "->".join(
        c["before_text"] + "=>" + c["after_text"] for c in pdf_items)
    record("C03_pdf_pair_compare_locations",
           rc_p == 0 and view_p.get("mode") == "pdf_pdf"
           and view_p.get("range", {}).get("mode") == "pdf_pdf"
           and rep_p.get("changes", {}).get("count") == 2
           and loc_ok
           and "36,000.00" in pdf_text_joined
           and "38,500.00" in pdf_text_joined
           and "（修订版）" in pdf_text_joined
           and pages_meta == {"left": 0, "right": 0},
           f"exit{rc_p} pdf_pdf 变更 {rep_p.get('changes', {}).get('count')}"
           f"（页/行定位齐={loc_ok}·无文本层页如实 {pages_meta}）两处替换"
           f"双侧文本全中")

    # ------------------------------------------------ C04 范围门负向
    rc_mix, res_mix = bridge_call(cfg_cmp, "doccompare.compare", {
        "document_id": "mix-1",
        "left_path": str(corpus / "docx_v1.docx"),
        "right_path": str(corpus / "pdf_v1.pdf")})
    txt = corpus / "notes.txt"
    txt.write_bytes("纯文本不在支持矩阵".encode("utf-8"))
    rc_txt, res_txt = bridge_call(cfg_cmp, "doccompare.compare", {
        "document_id": "mix-2", "left_path": str(txt),
        "right_path": str(txt)})
    num_only_a = build_docx([_p("第一条 合同价款", 1), _p("第二条 交付")])
    num_only_b = build_docx([_p("第一条 合同价款"), _p("第二条 交付")])
    rc_num, res_num = bridge_call(cfg_cmp, "doccompare.compare", {
        "document_id": "num-1",
        "left_b64": base64.b64encode(num_only_a).decode(),
        "right_b64": base64.b64encode(num_only_b).decode()})
    rc_same, res_same = bridge_call(cfg_cmp, "doccompare.compare", {
        "document_id": "same-1",
        "left_path": str(corpus / "docx_v1.docx"),
        "right_path": str(corpus / "docx_v1.docx")})
    same_changes = res_same.get("result", {}).get("changes", {})
    record("C04_range_gate_negatives_and_honest_zero",
           rc_mix == 3 and "f55_mode_unsupported:docx_pdf"
           in str(res_mix.get("code"))
           and rc_txt == 3 and "f55_mode_unsupported:unknown_unknown"
           in str(res_txt.get("code"))
           and rc_num == 3 and "f55_difference_outside_segment_model:"
           "numbering_marks" in str(res_num.get("code"))
           and rc_same == 0 and same_changes.get("count") == 0
           and view_a.get("payload_digest"),
           f"docx↔pdf exit{rc_mix} 具名拒；txt exit{rc_txt} 具名拒；"
           f"仅编号差 exit{rc_num} 具名拒（不假无变化）；同档对比 exit"
           f"{rc_same} 零变更诚实回执（count=0）")

    # ------------------------------------------------ C05 双留存＋append-only
    doc_dir = cmp_state / "document-compare" / "docx-pair"
    left_bin = doc_dir / "left.bin"
    right_bin = doc_dir / "right.bin"
    first_cmp_json = doc_dir / "comparisons" / "0001-compare" \
        / "comparison.json"
    first_sha = sha256_file(first_cmp_json) if first_cmp_json.is_file() \
        else ""
    rc_a2, res_a2 = bridge_call(cfg_cmp, "doccompare.compare", {
        "document_id": "docx-pair",
        "left_path": str(corpus / "docx_v1.docx"),
        "right_path": str(corpus / "docx_v2.docx")})
    view_a2 = res_a2.get("result", {})
    rc_list, res_list = bridge_call(cfg_cmp, "doccompare.list", {
        "document_id": "docx-pair"})
    listing = res_list.get("result", {}).get("comparisons", [])
    on_disk = sorted(p.parent.name for p in
                     (doc_dir / "comparisons").glob("*/comparison.json")) \
        if (doc_dir / "comparisons").is_dir() else []
    rc_mm, res_mm = bridge_call(cfg_cmp, "doccompare.compare", {
        "document_id": "docx-pair",
        "left_path": str(corpus / "docx_v2.docx"),
        "right_path": str(corpus / "docx_v2.docx")})
    record("C05_dual_retention_append_only_pinned",
           rc_a == 0
           and sha256_file(left_bin)
           == sha256_file(corpus / "docx_v1.docx")
           and sha256_file(right_bin)
           == sha256_file(corpus / "docx_v2.docx")
           and rc_a2 == 0 and view_a2.get("comparison_id")
           == "docx-pair:0002-compare"
           and sha256_file(first_cmp_json) == first_sha
           and [c["comparison_id"] for c in listing]
           == ["docx-pair:0001-compare", "docx-pair:0002-compare"]
           and on_disk == ["0001-compare", "0002-compare"]
           and rc_mm == 3 and "f55_left_bytes_mismatch"
           in str(res_mm.get("code")),
           f"left/right.bin sha==源；再对比出新序号 {view_a2.get('comparison_id')}"
           f"（0001 清单字节不动）；list 与盘上一一对应（无孤儿）；同 id 异"
           f"左档 exit{rc_mm} 具名拒")

    # ------------------------------------------------ C06 确定性（payload_digest）
    det_state = state / "cmp2"
    cfg_det = {"doccompare_state_root": str(det_state)}
    rc_d, res_d = bridge_call(cfg_det, "doccompare.compare", {
        "document_id": "docx-pair",
        "left_path": str(corpus / "docx_v1.docx"),
        "right_path": str(corpus / "docx_v2.docx")})
    digest_d = res_d.get("result", {}).get("payload_digest")
    cross = _CROSS_PROFILE_DIGESTS.setdefault("docx", digest_d)
    record("C06_deterministic_payload_digest",
           rc_d == 0 and digest_d
           and digest_d == view_a.get("payload_digest")
           and cross == digest_d,
           f"同输入两状态根 payload_digest 相等（{str(digest_d)[:16]}…）；"
           f"跨 profile 锚一致={cross == digest_d}")

    # ------------------------------------------------ C07 F58 红线导出（真 U14 链）
    rc_r1, res_r1 = bridge_call(cfg_red, "redline.register", {
        "document_id": "f49-doc",
        "docx_b64": base64.b64encode(
            (corpus / "f49_baseline.docx").read_bytes()).decode()})
    rc_r2, res_r2 = bridge_call(cfg_red, "redline.replay", {
        "document_id": "f49-doc", "proposal": F49_PROPOSAL})
    rc_r3, res_r3 = bridge_call(cfg_red, "redline.compare", {
        "document_id": "f49-doc",
        "proposal_id": res_r2.get("result", {}).get("proposal_id")})
    redline_id = res_r3.get("result", {}).get("redline_id")
    rev_count = res_r3.get("result", {}).get("revisions", {}).get("count")
    rc_e, res_e = bridge_call(cfg_exp, "docexport.pdf", {
        "source": "redline", "redline_id": redline_id})
    exp = res_e.get("result", {})
    pdf_meta = exp.get("pdf", {})
    scope = exp.get("change_scope", {})
    rc_rb, res_rb = bridge_call(cfg_red, "redline.redline", {
        "redline_id": redline_id})
    u14_sha = res_rb.get("result", {}).get("sha256")
    rc_rep58, res_rep58 = bridge_call(cfg_exp, "docexport.report", {
        "export_id": exp.get("export_id")})
    rc_lst58, res_lst58 = bridge_call(cfg_exp, "docexport.list", {})
    exports_listed = res_lst58.get("result", {}).get("exports", [])
    record("C07_f58_redline_pdf_real_render_scope_preserved",
           rc_r1 == 0 and rc_r2 == 0 and rc_r3 == 0 and rev_count >= 3
           and rc_e == 0
           and exp.get("schema") == SCHEMA_F58
           and pdf_meta.get("page_count", 0) >= 1
           and pdf_meta.get("total_lines", 0) >= 1
           and scope.get("checked", 0) > 0
           and scope.get("checked") == scope.get("matched")
           and scope.get("granularity")
           == "revision_run_normalized_containment"
           and exp.get("source", {}).get("sha256") == u14_sha
           and exp.get("engine", {}).get("name") == "libreoffice"
           and "soffice" in str(exp.get("engine", {}).get("binary"))
           and rc_rep58 == 0
           and res_rep58.get("result", {}).get("pdf", {}).get("sha256")
           == pdf_meta.get("sha256")
           and [e.get("export_id") for e in exports_listed]
           == [exp.get("export_id")],
           f"真 U14 链（revisions={rev_count}）→ redline.redline b64 取件"
           f"sha 一致 → LibreOffice（{exp.get('engine', {}).get('version')}）"
           f"真渲染 PDF {pdf_meta.get('page_count')} 页 "
           f"{pdf_meta.get('total_lines')} 行（可阅读打印）→ 保变更范围 "
           f"run 级 checked==matched=={scope.get('checked')}；report 回读/"
           f"list 一致")

    # ------------------------------------------------ C08 F58 对比产物导出
    rc_e2, res_e2 = bridge_call(cfg_exp, "docexport.pdf", {
        "source": "compare_report",
        "comparison_id": view_a.get("comparison_id")})
    exp2 = res_e2.get("result", {})
    scope2 = exp2.get("change_scope", {})
    record("C08_f58_compare_report_pdf_export",
           rc_e2 == 0 and exp2.get("source", {}).get("kind")
           == "compare_report"
           and scope2.get("checked", 0) >= 4
           and scope2.get("checked") == scope2.get("matched")
           and scope2.get("granularity")
           == "change_item_side_normalized_containment"
           and exp2.get("pdf", {}).get("page_count", 0) >= 1
           and exp2.get("pdf", {}).get("total_lines", 0) >= 1,
           f"对比报告自 F55 变更清单确定性生成→渲染 PDF "
           f"{exp2.get('pdf', {}).get('page_count')} 页；逐变更项 before/"
           f"after 双侧核对 checked==matched=={scope2.get('checked')}")

    # ------------------------------------------------ C09 失败不交空 PDF
    exports_root = exp_state / "document-export" / "exports"
    exports_before = sorted(p.name for p in exports_root.iterdir()) \
        if exports_root.is_dir() else []
    bad_buf = io.BytesIO()
    with zipfile.ZipFile(bad_buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        z.writestr("word/document.xml", "<w:document><w:body><w:p>x")
    rc_bad, res_bad = bridge_call(cfg_exp, "docexport.pdf", {
        "source": "docx",
        "docx_b64": base64.b64encode(bad_buf.getvalue()).decode()})
    empty_docx = build_docx([_p("")])
    rc_empty, res_empty = bridge_call(cfg_exp, "docexport.pdf", {
        "source": "docx",
        "docx_b64": base64.b64encode(empty_docx).decode()})
    exports_after = sorted(p.name for p in exports_root.iterdir()) \
        if exports_root.is_dir() else []
    record("C09_failure_no_empty_pdf_no_leftover",
           rc_bad == 3 and "f58_render_failed" in str(res_bad.get("code"))
           and rc_empty == 3
           and ("f58_unreadable_pdf" in str(res_empty.get("code"))
                or "f58_empty_pdf" in str(res_empty.get("code")))
           and exports_after == exports_before,
           f"坏 XML exit{rc_bad}={res_bad.get('code')}；零文本 exit"
           f"{rc_empty}={res_empty.get('code')}；失败零残留（导出目录"
           f"{len(exports_after)} 项不变）＝失败不交空 PDF")

    # ------------------------------------------------ C10 桥 fail-closed 负向
    rc_ns, res_ns = bridge_call({"libreoffice_soffice": soffice},
                                "doccompare.compare",
                                {"document_id": "x", "left_path": "x",
                                 "right_path": "x"})
    rc_ns2, res_ns2 = bridge_call({}, "docexport.pdf",
                                  {"source": "redline",
                                   "redline_id": "x:0001-compare"})
    rc_um, res_um = bridge_call(cfg_cmp, "doccompare.explode", {})
    rc_um2, res_um2 = bridge_call(cfg_exp, "docexport.explode", {})
    rc_nf, res_nf = bridge_call(cfg_cmp, "doccompare.report",
                                {"comparison_id": "docx-pair:9999-compare"})
    rc_mf, res_mf = bridge_call(cfg_cmp, "doccompare.compare", {
        "document_id": "mf-1", "left_path": str(corpus / "missing.docx"),
        "right_path": str(corpus / "docx_v1.docx")})
    code_shape = re.compile(r"^[\w:.;-]+$")
    codes = [str(res_ns.get("code")), str(res_ns2.get("code")),
             str(res_um.get("code")), str(res_um2.get("code")),
             str(res_nf.get("code")), str(res_mf.get("code"))]
    record("C10_bridge_fail_closed_negatives",
           rc_ns == 3 and "f55_state_root_not_configured"
           in str(res_ns.get("code"))
           and rc_ns2 == 3 and "f58_state_root_not_configured"
           in str(res_ns2.get("code"))
           and rc_um == 3 and "method_not_connected:doccompare.explode"
           in str(res_um.get("code"))
           and rc_um2 == 3 and "method_not_connected:docexport.explode"
           in str(res_um2.get("code"))
           and rc_nf == 3 and "f55_comparison_not_found"
           in str(res_nf.get("code"))
           and rc_mf == 3 and "f55_left_not_found" in str(res_mf.get("code"))
           and all(code_shape.match(c) for c in codes),
           f"两方法组未知方法/缺状态根/坏 id/缺文件六路全 exit3 具名拒；"
           f"错误码纯码不携材料内容")
    metrics["negative_codes"] = codes

    # ------------------------------------------------ C11 语料只读锚
    digest_after = corpus_identity_digest(corpus)
    record("C11_corpus_anchor_readonly",
           digest_after == digest_before,
           f"跑前后 sha256(identity) 相同＝{digest_after == digest_before}"
           f"（{digest_before[:16]}…）")

    ok = all(c["ok"] for c in checks)
    verdict = "RECON_OK" if ok else "RECON_FAIL"
    result = {
        "obligation": "06:F55 独立文档对比（两份实际文件本地对比与变更清单"
                      "对应，PDF/DOCX范围有明确支持）＋06:F58 红线/对比产物"
                      "导出 PDF（真实红线/对比PDF可阅读打印并保变更范围；"
                      "失败不交空PDF）",
        "unit": "W4-U37",
        "profile": profile,
        "started_utc": started,
        "finished_utc": now_iso(),
        "verdict": verdict,
        "corpus": {"root": str(corpus),
                   "identity_digest": digest_before,
                   "readonly_unchanged": digest_after == digest_before,
                   "materials": "全合成（reportlab＋自建 OOXML；裁决#1）"},
        "state_root": str(state),
        "f55": {"mode_docx": view_a.get("mode"),
                "changes": changes,
                "payload_digest": view_a.get("payload_digest"),
                "outside_model_declared":
                    view_a.get("range", {}).get("outside_model")},
        "f58": {"engine": exp.get("engine"),
                "redline_pdf": {k: pdf_meta.get(k) for k in
                                ("page_count", "total_lines", "sha256")},
                "scope_checked": scope.get("checked"),
                "scope_matched": scope.get("matched"),
                "scope_granularity": scope.get("granularity")},
        "checks": checks,
        "metrics": metrics,
    }
    result_json = json.dumps(result, ensure_ascii=False, indent=2)
    for ev_dir in (evidence_f55, evidence_f58):
        ev_dir.mkdir(parents=True, exist_ok=True)
        (ev_dir / "f55-f58-compare-pdf-recon-result.json").write_text(
            result_json, encoding="utf-8", newline="\n")
        md = [f"# F55+F58 对比与 PDF 导出 recon（{profile}）", "",
              f"- verdict: **{verdict}**（{sum(c['ok'] for c in checks)}/"
              f"{len(checks)} checks）",
              f"- unit: W4-U37 · profile: {profile}",
              f"- F55: mode={view_a.get('mode')} 变更 {changes.get('count')}"
              f" payload_digest={str(view_a.get('payload_digest'))[:16]}…",
              f"- F58: LibreOffice "
              f"{exp.get('engine', {}).get('version')} 真渲染；保变更范围 "
              f"run 级 checked==matched=={scope.get('checked')}",
              f"- 语料: 全合成 · 只读锚 {digest_before[:16]}…",
              f"- state: `{state}`", "", "| check | 结果 |", "|---|---|"]
        md += [f"| {c['check']} | {'PASS' if c['ok'] else 'FAIL'} |"
               for c in checks]
        (ev_dir / "f55-f58-compare-pdf-recon.md").write_text(
            "\n".join(md) + "\n", encoding="utf-8", newline="\n")
    print(f"\n[{profile}] {verdict}  ({sum(c['ok'] for c in checks)}/"
          f"{len(checks)} checks)  证据 → {evidence_f55}", flush=True)
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append",
                    choices=["desktop", "selfhost"], default=None)
    ap.add_argument("--corpus", metavar="DIR", default=None,
                    help="合成语料目录（默认 %%TEMP%%\\juscite-f55-f58-corpus）")
    ap.add_argument("--state", metavar="DIR", default=None,
                    help="显式状态根（默认按 profile 分 TEMP 子目录）")
    ap.add_argument("--soffice", metavar="PATH", default=None,
                    help="soffice 可执行路径（默认 C:\\Program Files\\"
                         "LibreOffice\\program\\soffice.exe 或环境变量 "
                         "JUSCITE_LIBREOFFICE）")
    args = ap.parse_args()
    profiles = args.profile or ["desktop"]
    soffice = args.soffice or os.environ.get("JUSCITE_LIBREOFFICE") \
        or DEFAULT_SOFFICE
    if not Path(soffice).is_file():
        eprint(f"[ENV] soffice 不存在：{soffice}（LibreOffice 未装？"
               "F58 渲染硬门不可过，不假 RECON_OK）")
        return 3
    corpus = Path(args.corpus) if args.corpus else \
        TEMP / "juscite-f55-f58-corpus"
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
