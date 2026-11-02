#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F54 义务验收 recon（W2b-U17）：PDF→docx 转换候选与保真检查（LibreOffice
优先）——双 profile（desktop/selfhost）两实例。

义务 06:F54 断言：「保存原PDF和转换候选；纯文本重建明确损失，实际版面/
表/页眉脚对照，不称自动保真；LibreOffice优先转换；结构保真实际对照，
未保真标损失」。§6.1 裁决#5：LibreOffice 已装（C:\\Program Files\\LibreOffice，
B2b 就绪）。转换候选入 U14 红线管线（candidate.json＝W2b-U14 消费契约）。

硬门（每 profile，真桥 CLI 子进程径）：
- C01 引擎：LibreOffice READY＋版本＋确定性 CLI 面（writer_pdf_import→
  MS Word 2007 XML，soffice.com 阻塞二进制）；未配置如实 NOT_INSTALLED。
- C02 双留存：original.pdf 落盘 sha==源；候选在盘；同 id 异字节=fail-closed
  且原件不动。
- C03 保真实测五维一致：文本/几何/分页保真＋表格/页眉页脚 loss 已标（引擎
  实测行为）；auto_fidelity_claimed 恒 false（不称自动保真本体）。
- C04 扫描页诚实：无文本层→no_text_layer＋needs_ocr＋不可编辑，不假成功。
- C05 纯文本重建：闭集损失显式标注＋文本/分页保真。
- C06 append-only：再转换出新序号，旧候选/原件不动。
- C07 确定性：同字节两文档 content_digest 相等（部件级；zip mtime 不参与）；
  跨 profile 同字节同摘要。
- C08 U14 红线管线消费契约：清单字段齐＋双 sha 与盘上字节复核＋report 回读
  ＋candidate b64 取件。
- C09 桥 fail-closed 负向（缺状态根/未知方法/坏 id/缺 soffice/未找到）＋
  错误码不携材料内容。
- C10 语料只读锚（跑前后同摘要）。
- C11 管线可枚举：conversion.list 与盘上候选一一对应（无孤儿）。

语料全合成（reportlab；00-总协调 §6.1 裁决#1，绝无真实文档）。reportlab
PDF 内嵌生成时间戳→跨次运行字节自然不同（如实记录），跑内锚与同跑确定性
不受影响。

用法（juscite worktree w2b-u17 仓根 cwd）：
  python -X utf8 tools/PENDING_OWNER_f54_pdf_conversion_recon.py \
      --profile desktop --profile selfhost

退出码：0＝全部 profile RECON_OK；2＝RECON_FAIL；3＝环境缺失。
证据：docs/construction/evidence/F54/<profile>/ JSON＋MD。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMP = Path(os.environ.get("TEMP", "."))
BRIDGE = REPO / "implementation" / "python" / "legal_entry.py"
SCHEMA = "juscite-f54-pdf-conversion/1"
DEFAULT_SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"

# 跨 profile 确定性锚（同字节同摘要；run 内共享）
_CROSS_PROFILE_DIGESTS: dict[str, str] = {}


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
# 全合成语料（reportlab；确定性内容，无 RNG 依赖）
# --------------------------------------------------------------------------

def _font(c):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    c.setFont("STSong-Light", 12)


def _doc_a() -> bytes:
    """2 页：页眉/页脚页码/正文/3×3 表格（金标网格）。"""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import Table, TableStyle

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    for page in (1, 2):
        _font(c)
        c.setFont("STSong-Light", 9)
        c.drawString(72, A4[1] - 40, "合成测试卷宗 F54-RECON-A")
        c.drawCentredString(A4[0] / 2, 30, f"- {page} -")
        c.setFont("STSong-Light", 12)
        c.drawString(72, A4[1] - 130,
                     f"第{page}页正文：本卷全部当事人、案号与金额均为合成"
                     f"虚构材料，价款人民币36,000.00元分三期支付。")
        if page == 1:
            tbl = Table([["期次", "应付日期", "本金（元）"],
                         ["1", "2026-02-05", "12,000.00"],
                         ["2", "2026-03-05", "12,000.00"]],
                        colWidths=[50, 95, 90])
            tbl.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.6, "black"),
                ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                ("FONTSIZE", (0, 0), (-1, -1), 10)]))
            tbl.wrapOn(c, 400, 200)
            tbl.drawOn(c, 72, A4[1] - 400)
        c.showPage()
    c.save()
    return buf.getvalue()


def _doc_b() -> bytes:
    """纯图像扫描页（无文本层）。"""
    import io
    from PIL import Image as PILImage, ImageDraw
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    img = PILImage.new("L", (992, 1403), 255)
    draw = ImageDraw.Draw(img)
    for i in range(18):
        draw.line([(80, 120 + i * 64), (900, 120 + i * 64)], fill=0, width=3)
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.drawImage(ImageReader(img), 0, 0, A4[0], A4[1])
    c.showPage()
    c.save()
    return buf.getvalue()


def _doc_c() -> bytes:
    """3 页纯文本＋每页相同页眉＋页码页脚。"""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as rl_canvas

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    for page in (1, 2, 3):
        _font(c)
        c.setFont("STSong-Light", 9)
        c.drawString(72, A4[1] - 40, "合成测试卷宗 F54-RECON-C")
        c.drawCentredString(A4[0] / 2, 30, f"- {page} -")
        c.setFont("STSong-Light", 12)
        for i in range(10):
            c.drawString(72, A4[1] - 130 - i * 26,
                         f"第{page}页第{i + 1}行：合成正文段落，当事人与"
                         f"金额均为虚构，本行用于文本保真对照。")
        c.showPage()
    c.save()
    return buf.getvalue()


GOLD_TABLE_A = {"cells": [["期次", "应付日期", "本金（元）"],
                          ["1", "2026-02-05", "12,000.00"],
                          ["2", "2026-03-05", "12,000.00"]]}


def ensure_corpus(corpus: Path) -> bool:
    if all((corpus / n).is_file() for n in
           ("doc_a.pdf", "doc_b.pdf", "doc_c.pdf")):
        return True
    corpus.mkdir(parents=True, exist_ok=True)
    eprint(f"[GEN] 合成语料不存在，生成 → {corpus}")
    (corpus / "doc_a.pdf").write_bytes(_doc_a())
    (corpus / "doc_b.pdf").write_bytes(_doc_b())
    (corpus / "doc_c.pdf").write_bytes(_doc_c())
    return all((corpus / n).is_file() for n in
               ("doc_a.pdf", "doc_b.pdf", "doc_c.pdf"))


def corpus_identity_digest(corpus: Path) -> str:
    parts = [sha256_file(corpus / n) for n in
             ("doc_a.pdf", "doc_b.pdf", "doc_c.pdf")]
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


def run_profile(profile: str, args, corpus: Path, soffice: str) -> int:
    evidence_dir = REPO / "docs" / "construction" / "evidence" / "F54" \
        / profile
    state = Path(args.state) if args.state else \
        TEMP / f"juscite-f54-state-{profile}"
    if state.exists() and any(state.iterdir()):
        eprint(f"[{profile}] 状态根非空，另起子目录：{state}")
        state = state / f"run-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    config = {"conversion_state_root": str(state),
              "libreoffice_soffice": soffice}
    digest_before = corpus_identity_digest(corpus)
    started = now_iso()
    checks: list[dict] = []
    metrics: dict = {}

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    print(f"\n===== profile {profile}（state={state}）=====", flush=True)

    # ------------------------------------------------ C01 引擎（LibreOffice 优先）
    rc, probe = bridge_call(config, "conversion.engine", {})
    eng = probe.get("result", {})
    rc_nc, probe_nc = bridge_call({}, "conversion.engine", {})
    eng_nc = probe_nc.get("result", {})
    record("C01_engine_libreoffice_first",
           rc == 0 and eng.get("installed") is True
           and eng.get("status") == "READY"
           and bool(eng.get("version"))
           and eng.get("infilter") == "writer_pdf_import"
           and eng.get("export_filter") == "MS Word 2007 XML"
           and Path(eng.get("binary", "")).name.startswith("soffice")
           and rc_nc == 0 and eng_nc.get("installed") is False
           and eng_nc.get("status") == "NOT_INSTALLED",
           f"engine={eng.get('engine')} priority={eng.get('priority')} "
           f"version={eng.get('version')} binary="
           f"{Path(eng.get('binary', '?')).name}（阻塞控制台二进制）；"
           f"未配置如实={eng_nc.get('status')}")
    metrics["engine"] = {k: eng.get(k) for k in
                         ("status", "version", "infilter", "export_filter")}

    # ------------------------------------------------ C02 双留存＋原件钉定
    rc_a, res_a = bridge_call(config, "conversion.convert", {
        "document_id": "doc-a", "matter_id": "M-SYN-001",
        "pdf_path": str(corpus / "doc_a.pdf"),
        "gold_tables": [GOLD_TABLE_A]})
    view_a = res_a.get("result", {})
    doc_dir = state / "pdf-conversion" / "doc-a"
    original = doc_dir / "original.pdf"
    cand_docx = doc_dir / view_a.get("candidate_docx", {}).get(
        "file", "candidates/0001-libreoffice/candidate.docx")
    retained_ok = (rc_a == 0 and original.is_file()
                   and sha256_file(original)
                   == sha256_file(corpus / "doc_a.pdf")
                   and cand_docx.is_file())
    # 同 id 异字节 → fail-closed，且原件不动
    rc_mismatch, res_mismatch = bridge_call(config, "conversion.convert", {
        "document_id": "doc-a", "pdf_path": str(corpus / "doc_b.pdf")})
    original_after = sha256_file(original) if original.is_file() else ""
    record("C02_dual_retention_original_pinned",
           retained_ok
           and rc_mismatch == 3
           and res_mismatch.get("status") == "NOT_CONNECTED"
           and "f54_original_bytes_mismatch"
           in str(res_mismatch.get("code"))
           and original_after == sha256_file(corpus / "doc_a.pdf"),
           f"original.pdf sha==源 sha；候选 docx 在盘；同 id 异字节 "
           f"exit{rc_mismatch}={res_mismatch.get('code')}；负向后原件不动")

    # ------------------------------------------------ C03 保真实测五维（不称自动保真）
    fid = view_a.get("fidelity", {})
    dims = {k: v.get("status") for k, v in
            fid.get("dimensions", {}).items()}
    text_dim = fid.get("dimensions", {}).get("text_content", {})
    tbl_dim = fid.get("dimensions", {}).get("tables", {})
    hf_dim = fid.get("dimensions", {}).get("headers_footers", {})
    record("C03_fidelity_measured_five_dimensions",
           view_a.get("schema") == SCHEMA
           and fid.get("auto_fidelity_claimed") is False
           and fid.get("comparison") == "measured_structural"
           and dims.get("text_content") == "preserved"
           and text_dim.get("missing_lines") == 0
           and text_dim.get("pdf_lines", 0) > 0
           and dims.get("page_geometry") == "preserved"
           and dims.get("page_flow") == "preserved"
           and fid.get("dimensions", {}).get("page_flow", {}).get(
               "docx_explicit_pages") == 2
           and dims.get("tables") == "loss"
           and "table_structure" in fid.get("losses", [])
           and tbl_dim.get("docx_tables") == []
           and dims.get("headers_footers") == "loss"
           and "header_footer_structure" in fid.get("losses", [])
           and hf_dim.get("content_survives_as_body_text") is True
           and any("- 1 -" == e for e in hf_dim.get("pdf_edge_lines", [])),
           f"五维实测：文本 preserved（{text_dim.get('pdf_lines')} 行 "
           f"missing={text_dim.get('missing_lines')}）/几何 preserved/"
           f"分页 preserved（breaks+1=2）/表格 loss（引擎不重建 w:tbl，"
           f"金标 3×3 对照 docx_tables=0）/页眉页脚 loss（部件 0，内容以"
           f"正文存活）；auto_fidelity_claimed=false；losses="
           f"{fid.get('losses')}")
    metrics["fidelity_dimensions"] = dims
    metrics["losses"] = fid.get("losses")

    # ------------------------------------------------ C04 扫描页诚实（不假成功）
    rc_b, res_b = bridge_call(config, "conversion.convert", {
        "document_id": "doc-b", "pdf_path": str(corpus / "doc_b.pdf")})
    view_b = res_b.get("result", {})
    b_docx = state / "pdf-conversion" / "doc-b" / view_b.get(
        "candidate_docx", {}).get("file", "?")
    image_carried = False
    if b_docx.is_file():
        with zipfile.ZipFile(b_docx) as zf:
            image_carried = any(n.startswith("word/media/")
                                for n in zf.namelist())
    b_dims = view_b.get("fidelity", {}).get("dimensions", {})
    record("C04_scanned_page_honest_no_text_layer",
           rc_b == 0
           and b_dims.get("text_content", {}).get("status")
           == "no_text_layer"
           and view_b.get("redline", {}).get("editable_text") is False
           and view_b.get("redline", {}).get("route") == "needs_ocr"
           and "text_content" not in view_b.get("fidelity", {}).get(
               "losses", [])
           and image_carried,
           f"图像页转换 exit0（图像携入 word/media）但文本层无→"
           f"no_text_layer＋route=needs_ocr＋不可编辑；不标文本损失"
           f"（无文本可丢，如实口径）")

    # ------------------------------------------------ C05 纯文本重建明确损失
    rc_r, res_r = bridge_call(config, "conversion.rebuild",
                              {"document_id": "doc-a"})
    view_r = res_r.get("result", {})
    r_fid = view_r.get("fidelity", {})
    r_losses = set(r_fid.get("losses", []))
    rebuild_closed = {"table_structure", "header_footer_structure",
                      "graphics_images", "fonts_styling",
                      "precise_positioning"}
    record("C05_text_rebuild_explicit_losses",
           rc_r == 0 and view_r.get("kind") == "text_rebuild"
           and rebuild_closed.issubset(r_losses)
           and "pure_text_rebuild_explicit_losses"
           in str(r_fid.get("rebuild_annotation", ""))
           and r_fid.get("dimensions", {}).get("text_content", {}
                                               ).get("status")
           == "preserved"
           and r_fid.get("dimensions", {}).get("page_flow", {}
                                               ).get("status")
           == "preserved",
           f"重建（从留存原件，无源路径）：闭集损失 "
           f"{sorted(rebuild_closed)} 全显式；文本/分页保真；"
           f"losses={sorted(r_losses)}")

    # ------------------------------------------------ C06 append-only＋不覆写
    first_json = doc_dir / "candidates" / "0001-libreoffice" \
        / "candidate.json"
    first_json_sha = sha256_file(first_json) if first_json.is_file() else ""
    first_docx_sha = sha256_file(cand_docx) if cand_docx.is_file() else ""
    rc_a2, res_a2 = bridge_call(config, "conversion.convert", {
        "document_id": "doc-a", "pdf_path": str(corpus / "doc_a.pdf")})
    view_a2 = res_a2.get("result", {})
    rc_list, res_list = bridge_call(config, "conversion.list",
                                    {"document_id": "doc-a"})
    listing = res_list.get("result", {}).get("candidates", [])
    record("C06_append_only_no_overwrite",
           rc_a2 == 0 and view_a2.get("candidate_id")
           == "doc-a:0003-libreoffice"
           and sha256_file(first_json) == first_json_sha
           and sha256_file(cand_docx) == first_docx_sha
           and sha256_file(original) == sha256_file(corpus / "doc_a.pdf")
           and [c["kind"] for c in listing]
           == ["libreoffice", "text_rebuild", "libreoffice"],
           f"再转换出新序号 {view_a2.get('candidate_id')}；旧候选"
           f" json/docx 字节不动；原件不动；list 序="
           f"{[c['candidate_id'] for c in listing]}")

    # ------------------------------------------------ C07 确定性（部件级摘要）
    rc_c1, res_c1 = bridge_call(config, "conversion.convert", {
        "document_id": "doc-c1", "pdf_path": str(corpus / "doc_c.pdf")})
    rc_c2, res_c2 = bridge_call(config, "conversion.convert", {
        "document_id": "doc-c2", "pdf_path": str(corpus / "doc_c.pdf")})
    d1 = res_c1.get("result", {}).get("candidate_docx", {})
    d2 = res_c2.get("result", {}).get("candidate_docx", {})
    same_digest = d1.get("content_digest") and \
        d1.get("content_digest") == d2.get("content_digest")
    cross = _CROSS_PROFILE_DIGESTS.setdefault("doc_c",
                                              d1.get("content_digest"))
    cross_ok = cross == d1.get("content_digest")
    record("C07_deterministic_content_digest",
           rc_c1 == 0 and rc_c2 == 0 and same_digest and cross_ok,
           f"同字节两文档 content_digest 相等（部件级 sha，zip mtime 不"
           f"参与）={same_digest}（{str(d1.get('content_digest'))[:16]}…）；"
           f"跨 profile 同摘要={cross_ok}")

    # ------------------------------------- C08 U14 红线管线消费契约＋取件
    rc_rep, res_rep = bridge_call(config, "conversion.report", {
        "candidate_id": view_a.get("candidate_id")})
    rep = res_rep.get("result", {})
    rc_bytes, res_bytes = bridge_call(config, "conversion.candidate", {
        "candidate_id": view_r.get("candidate_id")})
    got = res_bytes.get("result", {})
    r_docx = doc_dir / view_r.get("candidate_docx", {}).get("file", "?")
    b64_ok = got.get("docx_b64") and r_docx.is_file() and \
        base64.b64decode(got["docx_b64"]) == r_docx.read_bytes()
    manifest_path = doc_dir / "candidates" / "0001-libreoffice" \
        / "candidate.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) \
        if manifest_path.is_file() else {}
    record("C08_redline_pipeline_contract_consumable",
           rc_rep == 0 and rep.get("schema") == SCHEMA
           and rep.get("redline", {}).get("pipeline") == "w2b-u14"
           and rep.get("redline", {}).get("consumable_schema") == SCHEMA
           and rep.get("redline", {}).get("editable_text") is True
           and rep.get("redline", {}).get("route") == "revision_line"
           and manifest.get("original", {}).get("sha256")
           == sha256_file(original)
           and manifest.get("candidate_docx", {}).get("sha256")
           == sha256_file(cand_docx)
           and rc_bytes == 0 and b64_ok
           and rep.get("candidate_id") == view_a.get("candidate_id"),
           "candidate.json 双 sha 与盘上字节复核一致；redline 块"
           "（pipeline=w2b-u14/schema/editable_text/route/manifest 名）齐；"
           "report 回读==清单；candidate b64 取件==盘上字节")

    # ------------------------------------------------ C09 桥 fail-closed 负向
    rc_nc, res_nc = bridge_call({"libreoffice_soffice": soffice},
                                "conversion.convert",
                                {"document_id": "x", "pdf_path": "x"})
    rc_unknown, res_unknown = bridge_call(config, "conversion.explode", {})
    rc_badid, res_badid = bridge_call(config, "conversion.convert", {
        "document_id": "../escape", "pdf_path": str(corpus / "doc_a.pdf")})
    rc_nosrc, res_nosrc = bridge_call(config, "conversion.convert", {
        "document_id": "doc-ok", "pdf_path": str(corpus / "missing.pdf")})
    rc_notfound, res_notfound = bridge_call(config, "conversion.report", {
        "candidate_id": "doc-a:9999-libreoffice"})
    code_shape = re.compile(r"^[\w:.;-]+$")
    codes = [str(res_nc.get("code")), str(res_unknown.get("code")),
             str(res_badid.get("code")), str(res_nosrc.get("code")),
             str(res_notfound.get("code"))]
    record("C09_bridge_fail_closed_negatives",
           rc_nc == 3 and "f54_state_root_not_configured"
           in str(res_nc.get("code"))
           and rc_unknown == 3 and "method_not_connected:conversion.explode"
           in str(res_unknown.get("code"))
           and rc_badid == 3 and "f54_document_id_invalid"
           in str(res_badid.get("code"))
           and rc_nosrc == 3 and "f54_pdf_not_found"
           in str(res_nosrc.get("code"))
           and rc_notfound == 3 and "f54_candidate_not_found"
           in str(res_notfound.get("code"))
           and all(code_shape.match(c) for c in codes),
           f"缺状态根 exit{rc_nc}；未知方法 exit{rc_unknown}；坏 id "
           f"exit{rc_badid}；源缺失 exit{rc_nosrc}；候选未找到 "
           f"exit{rc_notfound}；错误码纯码不携材料内容")
    metrics["negative_codes"] = codes

    # ------------------------------------------------ C10 语料只读锚
    digest_after = corpus_identity_digest(corpus)
    record("C10_corpus_anchor_readonly",
           digest_after == digest_before,
           f"跑前后 sha256(identity) 相同＝{digest_after == digest_before} "
           f"（{digest_after[:16]}…）")

    # ------------------------------------------------ C11 管线可枚举（无孤儿）
    on_disk = sorted(p.parent.name for p in
                     (doc_dir / "candidates").glob("*/candidate.json"))
    listed = sorted(c["candidate_id"].split(":")[1] for c in listing)
    consumable = all(
        c.get("schema") == SCHEMA and c.get("candidate_docx", {}).get(
            "sha256") and c.get("original", {}).get("sha256")
        and isinstance(c.get("fidelity", {}).get("losses"), list)
        and c.get("redline", {}).get("route") in ("revision_line",
                                                  "needs_ocr")
        for c in (view_a, view_r, view_a2))
    record("C11_pipeline_enumerable_no_orphans",
           on_disk == listed and consumable,
           f"conversion.list 与盘上候选目录一一对应（{on_disk}）；"
           f"全部清单字段可消费（schema/双 sha/losses/route）={consumable}")

    ok = all(c["ok"] for c in checks)
    verdict = "RECON_OK" if ok else "RECON_FAIL"
    result = {
        "obligation": "06:F54 PDF→docx 转换进红线管线（LibreOffice 优先）："
                      "保存原PDF和转换候选；纯文本重建明确损失，实际版面/"
                      "表/页眉脚对照，不称自动保真；结构保真实际对照，"
                      "未保真标损失",
        "unit": "W2b-U17",
        "profile": profile,
        "started_utc": started,
        "finished_utc": now_iso(),
        "verdict": verdict,
        "corpus": {"root": str(corpus),
                   "identity_digest": digest_before,
                   "readonly_unchanged": digest_after == digest_before,
                   "materials": "全合成（reportlab；裁决#1）"},
        "state_root": str(state),
        "engine": metrics.get("engine"),
        "fidelity_dimensions": metrics.get("fidelity_dimensions"),
        "losses": metrics.get("losses"),
        "checks": checks,
        "metrics": metrics,
    }
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out_json = evidence_dir / "f54-pdf-conversion-recon-result.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8", newline="\n")
    md = [f"# F54 PDF→docx 转换候选与保真检查 recon（{profile}）",
          "",
          f"- verdict: **{verdict}**（{sum(c['ok'] for c in checks)}/"
          f"{len(checks)} checks）",
          f"- unit: W2b-U17 · profile: {profile}",
          f"- engine: LibreOffice {metrics.get('engine', {}).get('version')}"
          "（writer_pdf_import → MS Word 2007 XML，soffice.com 阻塞二进制）",
          f"- 保真实测维度: {metrics.get('fidelity_dimensions')}",
          f"- 已标损失: {metrics.get('losses')}（auto_fidelity_claimed="
          "false——结构保真实际对照，未保真标损失，不称自动保真）",
          f"- 语料: 全合成 · 只读锚 {digest_before[:16]}…",
          f"- state: `{state}`",
          "",
          "| check | 结果 |", "|---|---|"]
    md += [f"| {c['check']} | {'PASS' if c['ok'] else 'FAIL'} |"
           for c in checks]
    (evidence_dir / "f54-pdf-conversion-recon.md").write_text(
        "\n".join(md) + "\n", encoding="utf-8", newline="\n")
    print(f"\n[{profile}] {verdict}  ({sum(c['ok'] for c in checks)}/"
          f"{len(checks)} checks)  证据 → {out_json}", flush=True)
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", action="append",
                    choices=["desktop", "selfhost"], default=None)
    ap.add_argument("--corpus", metavar="DIR", default=None,
                    help="合成语料目录（默认 %%TEMP%%\\juscite-f54-corpus）")
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
               "§6.1 裁决#5 称已装）")
        return 3
    corpus = Path(args.corpus) if args.corpus else \
        TEMP / "juscite-f54-corpus"
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
