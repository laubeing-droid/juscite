"""W2b-U17 / F54 wiring: PDF→docx 转换候选与保真检查（conversion.* 桥方法
组 → pdf_conversion 产品面 document-adapter）。

义务 06:F54 断言：「保存原PDF和转换候选；纯文本重建明确损失，实际版面/
表/页眉脚对照，不称自动保真；LibreOffice优先转换；结构保真实际对照，
未保真标损失」。

- 对照器/重建/双留存：纯单测（无 soffice，手造 docx 字节与 PDF 事实）。
- 桥面真转换：真 LibreOffice（soffice.com 阻塞二进制，writer_pdf_import
  → MS Word 2007 XML）——未安装/不可执行整类跳过（如实 NOT_INSTALLED，
  绝不假绿）。语料全合成（reportlab，00-总协调 §6.1 裁决#1）。
- 实测口径（本机 LibreOffice 26.8.1.1）：Writer PDF 导入保留文本/页面
  尺寸/显式分页，表格结构与页眉页脚部件不重建（内容以正文存活）——
  断言只钉「实测一致性」（维度状态与实测计数自洽、未保真标 loss、
  auto_fidelity_claimed 恒 false），绝不宣称自动保真。
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from legal_entry import call, NotConnected  # noqa: E402
from pdf_conversion import (  # noqa: E402
    ConversionError, REBUILD_LOSSES, SCHEMA, _docx_parse, docx_content_digest,
    fidelity_report, pdf_facts, write_text_rebuild_docx)

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_W_URI = _W[1:-1]


def _fixture_pdf(pages_spec=None) -> bytes:
    """全合成 PDF：页眉(顶部 40pt)/正文(自顶部 130pt 起)/表格/页脚(y=30)。
    几何与边带口径（10%）留足间隔，边带分类无歧义。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import Table, TableStyle

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)

    def _chrome(page_no):
        c.setFont("STSong-Light", 9)
        c.drawString(72, A4[1] - 40, "合成卷宗 F54-TEST")
        c.drawCentredString(A4[0] / 2, 30, f"- {page_no} -")

    for page_no in range(1, 3):
        _chrome(page_no)
        c.setFont("STSong-Light", 12)
        c.drawString(72, A4[1] - 130,
                     f"第{page_no}页正文：原告张三与被告李四合同纠纷，"
                     f"约定价款人民币12,000.00元，利率约定不超过4倍LPR。")
        if page_no == 1:
            tbl = Table([["期次", "应付日期", "本金（元）"],
                         ["1", "2026-02-05", "4,000.00"],
                         ["2", "2026-03-05", "4,000.00"]],
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


def _scan_pdf() -> bytes:
    """全合成扫描页（纯图像无文本层）。"""
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


def _write_docx(parts: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in parts.items():
            zf.writestr(name, text)
    return buf.getvalue()


def _doc_xml(paragraph_texts, page_breaks=0, w_tw=11906, h_tw=16838,
             tables_xml="", dup_fallback=False):
    """手造 document.xml。dup_fallback=True 模拟 LibreOffice Writer PDF
    导入的 mc:Choice/mc:Fallback 成对复制结构。"""
    body = []
    breaks = ['<w:r><w:br w:type="page"/></w:r>'] * page_breaks
    seq = list(paragraph_texts)
    for i, text in enumerate(seq):
        run = f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>'
        if dup_fallback:
            run = ('<w:r><mc:AlternateContent><mc:Choice Requires="wps">'
                   '<w:drawing><w:txbxContent><w:p>' + run +
                   '</w:p></w:txbxContent></w:drawing></mc:Choice>'
                   '<mc:Fallback><w:pict><v:textbox><w:txbxContent><w:p>'
                   + run + '</w:p></w:txbxContent></v:textbox></w:pict>'
                   '</mc:Fallback></mc:AlternateContent></w:r>')
        body.append("<w:p>" + run + "</w:p>")
        if i < len(breaks):
            body.append("<w:p>" + breaks[i] + "</w:p>")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main" xmlns:mc="http://schemas.'
        'openxmlformats.org/markup-compatibility/2006" xmlns:v="urn:'
        'schemas-microsoft-com:vml"><w:body>' + "".join(body) + tables_xml +
        f'<w:sectPr><w:pgSz w:w="{w_tw}" w:h="{h_tw}"/></w:sectPr>'
        '</w:body></w:document>')


def _facts(pages_lines, sizes=None):
    """手造 pdf facts：[[{text,zone},...], ...]。"""
    return {"pages": [
        {"index": i + 1,
         "width_pt": (sizes or [(595.3, 841.9)] * len(pages_lines))[i][0],
         "height_pt": (sizes or [(595.3, 841.9)] * len(pages_lines))[i][1],
         "lines": lines}
        for i, lines in enumerate(pages_lines)]}


class FidelityComparatorTests(unittest.TestCase):
    """五维对照器判定逻辑（纯单测，手造事实）。"""

    def test_all_dimensions_preserved(self):
        facts = _facts([[{"text": "正文一", "zone": "body"},
                         {"text": "页眉行", "zone": "header"},
                         {"text": "- 1 -", "zone": "footer"}]])
        parsed = {"page_sizes_pt": [(595, 842)], "page_breaks": 0,
                  "pages_text": [["正文一", "页眉行", "- 1 -"]],
                  "tables": [], "header_footer_parts": [
                      {"part": "header1.xml", "kind": "header",
                       "texts": ["页眉行"]},
                      {"part": "footer1.xml", "kind": "footer",
                       "texts": ["- 1 -"]}]}
        rep = fidelity_report(facts, parsed)
        dims = {k: v["status"] for k, v in rep["dimensions"].items()}
        self.assertEqual(dims["text_content"], "preserved")
        self.assertEqual(dims["page_geometry"], "preserved")
        self.assertEqual(dims["page_flow"], "preserved")
        self.assertEqual(dims["headers_footers"], "preserved")
        self.assertEqual(rep["losses"], [])
        self.assertFalse(rep["auto_fidelity_claimed"])
        self.assertTrue(rep["dimensions_all_preserved"])

    def test_text_partial_and_geometry_loss(self):
        facts = _facts([[{"text": "行一", "zone": "body"},
                         {"text": "行二", "zone": "body"}]])
        parsed = {"page_sizes_pt": [(500, 700)], "page_breaks": 0,
                  "pages_text": [["行一"]], "tables": [],
                  "header_footer_parts": []}
        rep = fidelity_report(facts, parsed)
        dims = rep["dimensions"]
        self.assertEqual(dims["text_content"]["status"], "partial_loss")
        self.assertEqual(dims["text_content"]["missing_lines"], 1)
        self.assertEqual(dims["page_geometry"]["status"], "loss")
        self.assertIn("text_content", rep["losses"])
        self.assertIn("page_geometry", rep["losses"])

    def test_gold_table_hard_compare_marks_loss(self):
        facts = _facts([[{"text": "期次", "zone": "body"}]])
        gold = [{"rows": 2, "cols": 2, "cells": [["期次", "日期"],
                                                 ["1", "2026-01-01"]]}]
        parsed = {"page_sizes_pt": [(595, 842)], "page_breaks": 0,
                  "pages_text": [["期次"]], "tables": [],  # docx 无表
                  "header_footer_parts": []}
        rep = fidelity_report(facts, parsed, gold)
        self.assertEqual(rep["dimensions"]["tables"]["status"], "loss")
        self.assertIn("table_structure", rep["losses"])
        # docx 真有同网格表 → preserved
        parsed_ok = dict(parsed, tables=[{"rows": 2, "cols": 2,
                                          "cells": gold[0]["cells"]}])
        rep2 = fidelity_report(facts, parsed_ok, gold)
        self.assertEqual(rep2["dimensions"]["tables"]["status"], "preserved")

    def test_header_footer_loss_marked_with_content_survival(self):
        facts = _facts([[{"text": "页眉行", "zone": "header"},
                         {"text": "正文", "zone": "body"}]])
        parsed = {"page_sizes_pt": [(595, 842)], "page_breaks": 0,
                  "pages_text": [["页眉行", "正文"]], "tables": [],
                  "header_footer_parts": []}
        rep = fidelity_report(facts, parsed)
        dim = rep["dimensions"]["headers_footers"]
        self.assertEqual(dim["status"], "loss")
        self.assertTrue(dim["content_survives_as_body_text"])
        self.assertIn("header_footer_structure", rep["losses"])

    def test_no_text_layer_status(self):
        facts = _facts([[]])
        parsed = {"page_sizes_pt": [(595, 842)], "page_breaks": 0,
                  "pages_text": [[]], "tables": [], "header_footer_parts": []}
        rep = fidelity_report(facts, parsed)
        self.assertEqual(rep["dimensions"]["text_content"]["status"],
                         "no_text_layer")


class DocxParseTests(unittest.TestCase):
    """docx 事实抽取：Choice/Fallback 去重＋分页切页。"""

    def test_fallback_dedupe_and_page_split(self):
        xml = _doc_xml(["第一页行", "第二页行"], page_breaks=1,
                       dup_fallback=True)
        docx = _write_docx({"word/document.xml": xml})
        fd, name = tempfile.mkstemp(suffix=".docx")
        os.close(fd)
        path = Path(name)
        path.write_bytes(docx)
        try:
            parsed = _docx_parse(path)
        finally:
            path.unlink()
        self.assertEqual(parsed["pages_text"], [["第一页行"], ["第二页行"]])
        self.assertEqual(parsed["page_breaks"], 1)
        self.assertEqual(parsed["page_sizes_pt"], [(595, 842)])

    def test_tables_and_header_parts(self):
        tbl = ('<w:tbl><w:tr><w:tc><w:p><w:r><w:t>a</w:t></w:r></w:p>'
               '</w:tc><w:tc><w:p><w:r><w:t>b</w:t></w:r></w:p></w:tc>'
               '</w:tr></w:tbl>')
        xml = _doc_xml(["x"], tables_xml=tbl)
        docx = _write_docx({"word/document.xml": xml,
                            "word/header1.xml":
                                '<w:hdr xmlns:w="' + _W_URI + '"><w:p><w:r>'
                                '<w:t>页眉文本</w:t></w:r></w:p></w:hdr>'})
        fd, name = tempfile.mkstemp(suffix=".docx")
        os.close(fd)
        path = Path(name)
        path.write_bytes(docx)
        try:
            parsed = _docx_parse(path)
        finally:
            path.unlink()
        self.assertEqual(parsed["tables"],
                         [{"rows": 1, "cols": 2, "cells": [["a", "b"]]}])
        self.assertEqual(parsed["header_footer_parts"][0]["texts"],
                         ["页眉文本"])


class PdfFactsAndRebuildTests(unittest.TestCase):
    """PDF 事实抽取（真 pdfium）＋纯文本重建。"""

    def test_pdf_facts_zones(self):
        fd, name = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        path = Path(name)
        path.write_bytes(_fixture_pdf())
        try:
            facts = pdf_facts(path)
        finally:
            path.unlink()
        self.assertEqual(facts["page_count"], 2)
        zones = {(line["text"], line["zone"])
                 for page in facts["pages"] for line in page["lines"]}
        self.assertIn(("合成卷宗 F54-TEST", "header"), zones)
        self.assertIn(("- 1 -", "footer"), zones)
        self.assertIn(("- 2 -", "footer"), zones)
        self.assertTrue(any(zone == "body" and text.startswith("第1页正文")
                            for text, zone in zones))
        self.assertTrue(any(text == "期次" for text, _ in zones))

    def test_text_rebuild_docx_explicit_losses(self):
        work = Path(tempfile.mkdtemp(prefix="f54-rebuild-"))
        src = work / "src.pdf"
        src.write_bytes(_fixture_pdf())
        facts = pdf_facts(src)
        out = work / "rebuild.docx"
        written = write_text_rebuild_docx(out, facts)
        self.assertEqual(written["pages"], 2)
        self.assertTrue(out.is_file())
        parsed = _docx_parse(out)
        rep = fidelity_report(facts, parsed)
        # 重建自对照：文本/分页应保真（服务层再把 REBUILD_LOSSES 并入标注）
        self.assertEqual(rep["dimensions"]["text_content"]["status"],
                         "preserved")
        self.assertEqual(rep["dimensions"]["page_flow"]["status"], "preserved")
        # 重建 docx 可再解析（合法 zip＋xml），内容摘要稳定
        self.assertEqual(docx_content_digest(out), docx_content_digest(out))

    def test_text_with_percent_sign_roundtrip(self):
        work = Path(tempfile.mkdtemp(prefix="f54-pct-"))
        src = work / "src.pdf"
        buf = io.BytesIO()
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas as rl_canvas
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        c = rl_canvas.Canvas(buf, pagesize=A4)
        c.setFont("STSong-Light", 12)
        c.drawString(72, A4[1] - 130, "手续费率100%封顶，另计5%税费")
        c.showPage()
        c.save()
        src.write_bytes(buf.getvalue())
        facts = pdf_facts(src)
        out = work / "rebuild.docx"
        write_text_rebuild_docx(out, facts)
        parsed = _docx_parse(out)
        flat = [t for page in parsed["pages_text"] for t in page]
        self.assertIn("手续费率100%封顶，另计5%税费", flat)


class DualRetentionTests(unittest.TestCase):
    """双留存：原件钉定不覆盖（同 id 字节异=fail-closed）。"""

    def test_original_pinned(self):
        from pdf_conversion import _register_document
        work = Path(tempfile.mkdtemp(prefix="f54-retain-"))
        src = work / "a.pdf"
        src.write_bytes(_fixture_pdf())
        doc_dir, manifest = _register_document(work, "doc-ret", None, src)
        original = doc_dir / "original.pdf"
        first_sha = hashlib.sha256(original.read_bytes()).hexdigest()
        # 幂等复用：同字节再注册
        _, again = _register_document(work, "doc-ret", None, src)
        self.assertEqual(again["original"]["sha256"],
                         manifest["original"]["sha256"])
        # 字节异 → fail-closed，且盘上原件不动
        src.write_bytes(_scan_pdf())
        with self.assertRaises(ConversionError) as ctx:
            _register_document(work, "doc-ret", None, src)
        self.assertIn("f54_original_bytes_mismatch", str(ctx.exception))
        self.assertEqual(
            hashlib.sha256(original.read_bytes()).hexdigest(), first_sha)


def _soffice_config(state_root):
    path = os.environ.get(
        "JUSCITE_LIBREOFFICE",
        r"C:\Program Files\LibreOffice\program\soffice.exe")
    return {"conversion_state_root": str(state_root),
            "libreoffice_soffice": path}


class F54ConversionBridgeTests(unittest.TestCase):
    """桥面真转换（真 LibreOffice；未装=整类跳过，不假绿）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="f54-bridge-"))
        cls.cfg = _soffice_config(cls.tmp)
        from pdf_conversion import engine_report
        cls.engine = engine_report(cls.cfg)
        if not cls.engine.get("installed"):
            raise unittest.SkipTest(
                "libreoffice not available: " + str(cls.engine.get("status")))

    def test_convert_fidelity_measured_dual_retention(self):
        src = self.tmp / "in.pdf"
        fixture_bytes = _fixture_pdf()
        src.write_bytes(fixture_bytes)
        view = call("conversion.convert",
                    {"document_id": "doc-f54", "pdf_path": str(src),
                     "matter_id": "M-SYN", "gold_tables": [
                        {"cells": [["期次", "应付日期", "本金（元）"],
                                   ["1", "2026-02-05", "4,000.00"],
                                   ["2", "2026-03-05", "4,000.00"]]}]},
                    self.cfg)
        self.assertEqual(view["schema"], SCHEMA)
        self.assertEqual(view["kind"], "libreoffice")
        self.assertEqual(view["engine"]["version"],
                         self.engine["version"])
        self.assertFalse(view["engine"].get("binary", "").find("\\") >= 0,
                         "engine.binary 只回文件名不带绝对路径")
        fid = view["fidelity"]
        self.assertFalse(fid["auto_fidelity_claimed"])   # 不称自动保真
        dims = fid["dimensions"]
        # 实测一致性：对照结论与引擎实测行为自洽（本机 26.8.1.1：文本/
        # 几何/分页保真；表格结构与页眉页脚部件不重建→如实 loss）
        self.assertEqual(dims["text_content"]["status"], "preserved")
        self.assertEqual(dims["page_geometry"]["status"], "preserved")
        self.assertEqual(dims["page_flow"]["status"], "preserved")
        self.assertIn("table_structure", fid["losses"])
        self.assertIn("header_footer_structure", fid["losses"])
        self.assertEqual(dims["tables"]["status"], "loss")
        self.assertEqual(dims["headers_footers"]["status"], "loss")
        # 双留存：原件落位且 sha 钉定；候选 docx 在盘
        doc_dir = self.tmp / "pdf-conversion" / "doc-f54"
        original = doc_dir / "original.pdf"
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(),
                         hashlib.sha256(fixture_bytes).hexdigest())
        self.assertTrue((doc_dir / view["candidate_docx"]["file"]).is_file())
        # U14 红线管线消费契约
        self.assertEqual(view["redline"]["pipeline"], "w2b-u14")
        self.assertTrue(view["redline"]["editable_text"])
        self.assertEqual(view["redline"]["route"], "revision_line")

    def test_scanned_pdf_honest_no_text_layer(self):
        src = self.tmp / "scan.pdf"
        src.write_bytes(_scan_pdf())
        view = call("conversion.convert",
                    {"document_id": "doc-scan", "pdf_path": str(src)},
                    self.cfg)
        dims = view["fidelity"]["dimensions"]
        self.assertEqual(dims["text_content"]["status"], "no_text_layer")
        self.assertFalse(view["redline"]["editable_text"])
        self.assertEqual(view["redline"]["route"], "needs_ocr")
        self.assertNotIn("text_content", view["fidelity"]["losses"])

    def test_rebuild_explicit_losses_and_append_only(self):
        src = self.tmp / "in2.pdf"
        src.write_bytes(_fixture_pdf())
        call("conversion.convert",
             {"document_id": "doc-rb", "pdf_path": str(src)}, self.cfg)
        view = call("conversion.rebuild", {"document_id": "doc-rb"},
                    self.cfg)
        self.assertEqual(view["kind"], "text_rebuild")
        losses = set(view["fidelity"]["losses"])
        for loss in REBUILD_LOSSES:                     # 闭集全显式
            self.assertIn(loss, losses)
        self.assertIn("pure_text_rebuild_explicit_losses",
                      view["fidelity"]["rebuild_annotation"])
        listing = call("conversion.list", {"document_id": "doc-rb"},
                       self.cfg)
        kinds = [c["kind"] for c in listing["candidates"]]
        self.assertEqual(kinds, ["libreoffice", "text_rebuild"])  # append-only
        # 再转换 → 新候选，原件不动
        before = hashlib.sha256(
            (self.tmp / "pdf-conversion" / "doc-rb" / "original.pdf")
            .read_bytes()).hexdigest()
        call("conversion.convert",
             {"document_id": "doc-rb", "pdf_path": str(src)}, self.cfg)
        listing2 = call("conversion.list", {"document_id": "doc-rb"},
                        self.cfg)
        self.assertEqual(len(listing2["candidates"]), 3)
        after = hashlib.sha256(
            (self.tmp / "pdf-conversion" / "doc-rb" / "original.pdf")
            .read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_report_and_candidate_bytes_roundtrip(self):
        import base64
        src = self.tmp / "in3.pdf"
        src.write_bytes(_fixture_pdf())
        view = call("conversion.convert",
                    {"document_id": "doc-rt", "pdf_path": str(src)},
                    self.cfg)
        rep = call("conversion.report",
                   {"candidate_id": view["candidate_id"]}, self.cfg)
        self.assertEqual(rep["candidate_id"], view["candidate_id"])
        got = call("conversion.candidate",
                   {"candidate_id": view["candidate_id"]}, self.cfg)
        on_disk = self.tmp / "pdf-conversion" / "doc-rt" / view[
            "candidate_docx"]["file"]
        self.assertEqual(base64.b64decode(got["docx_b64"]),
                         on_disk.read_bytes())
        # 内容摘要可复现（同字节另一文档 → 同 content_digest）
        src2 = self.tmp / "in3-copy.pdf"
        src2.write_bytes(src.read_bytes())
        view2 = call("conversion.convert",
                     {"document_id": "doc-rt2", "pdf_path": str(src2)},
                     self.cfg)
        self.assertEqual(view2["candidate_docx"]["content_digest"],
                         view["candidate_docx"]["content_digest"])

    def test_bridge_fail_closed(self):
        src = self.tmp / "in4.pdf"
        src.write_bytes(_fixture_pdf())
        with self.assertRaises(NotConnected) as ctx:
            call("conversion.convert", {"document_id": "bad id!",
                                       "pdf_path": str(src)}, self.cfg)
        self.assertIn("f54_document_id_invalid", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            call("conversion.convert",
                 {"document_id": "doc-ok", "pdf_path": str(src)},
                 {"conversion_state_root": str(self.tmp)})
        self.assertIn("f54_soffice_not_configured", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            call("conversion.convert", {"document_id": "doc-ok"},
                 self.cfg)
        self.assertIn("f54_pdf_path_required", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            call("conversion.report",
                 {"candidate_id": "doc-ok:9999-libreoffice"}, self.cfg)
        self.assertIn("f54_candidate_not_found", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            call("conversion.explode", {}, self.cfg)
        self.assertIn("method_not_connected:conversion.explode",
                      str(ctx.exception))
        # 状态根缺失：engine 探针仍可用（如实报告），其余 fail-closed
        probe = call("conversion.engine", {}, {})
        self.assertIn(probe.get("status"), ("NOT_INSTALLED", "READY"))
        with self.assertRaises(NotConnected) as ctx:
            call("conversion.list", {"document_id": "doc-ok"}, {})
        self.assertIn("f54_state_root_not_configured", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
