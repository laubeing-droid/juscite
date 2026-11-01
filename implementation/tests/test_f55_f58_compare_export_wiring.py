"""W4-U37 / F55+F58 wiring: 独立文档对比与红线/对比产物导出 PDF
（doccompare.* → document_compare；docexport.* → document_export，
document-adapter 家族，legal_entry 桥同进程径）。

义务 06:F55 断言：「两份实际文件本地对比与变更清单对应，PDF/DOCX范围
有明确支持」；06:F58 断言：「真实红线/对比PDF可阅读打印并保变更范围；
失败不交空PDF」。

- 语料全合成（本文件自建 DOCX/PDF，全部合成合同文本；00-总协调 §6.1
  裁决#1，绝无真实文档）。
- F55：确定性差量（difflib 对齐，F49 _align 复用）＋变更清单对应三不变
  式（双射/覆盖/双侧）＋支持矩阵显式声明（docx_docx/pdf_pdf 闭集）＋
  模型外差量守卫（编号/删除侧标记零可见差量时具名拒不假无变化）。
- F58：LibreOffice headless 真渲染（未装环境整类诚实跳过——F54 先例）；
  红线源消费 U14 redline.redline b64 面；保变更范围＝run 级 PDF 文本层
  实测；失败不交空 PDF（typed 拒＋半成品清除）。
"""
import base64
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from legal_entry import call, NotConnected, DOCCOMPARE_METHODS, \
    DOC_EXPORT_METHODS  # noqa: E402

_W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DEFAULT_SOFFICE = r"C:\Program Files\LibreOffice\program\soffice.exe"
SOFFICE = os.environ.get("JUSCITE_LIBREOFFICE", DEFAULT_SOFFICE)
HAVE_SOFFICE = Path(SOFFICE).is_file()


# --------------------------------------------------------------------------
# 合成语料（DOCX 富文档／编号差异档／PDF）
# --------------------------------------------------------------------------

def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _p(text: str, num_id=None) -> str:
    ppr = ""
    if num_id is not None:
        ppr = ('<w:pPr><w:numPr><w:ilvl w:val="0"/>'
               f'<w:numId w:val="{num_id}"/></w:numPr></w:pPr>')
    run = (f'<w:r><w:t xml:space="preserve">{_esc(text)}</w:t></w:r>'
           if text else "")
    return f"<w:p>{ppr}{run}</w:p>"


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
    """合成 DOCX：正文＋表格＋（可选）双编号定义＋（可选）脚注。"""
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        f'<w:document xmlns:w="{_W_URI}"><w:body>'
        + "".join(body_parts)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
          "</w:body></w:document>")
    parts = {}
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
    parts["word/document.xml"] = document
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
        '2006/relationships">' + "".join(rels_entries)
        + "</Relationships>")
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

DOCX_V1 = build_docx(BODY_V1, numbering=True,
                     footnotes={1: "合成脚注一：三期付款日期均为合成示例日期。"})
DOCX_V2 = build_docx(BODY_V2, numbering=True,
                     footnotes={1: "合成脚注一：三期付款日期均为合成示例日期。",
                                2: "合成脚注二：争议解决条文为合成示例文本（修订版）。"})


def build_pdf(lines_per_page: list) -> bytes:
    """合成 PDF（reportlab，确定性内容；内嵌时间戳如实不主张字节确定）。"""
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

# F49 语料复用（红线源走真 U14 面）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_f49_replay_redline_wiring import (  # noqa: E402
    build_rich_baseline_docx as _f49_baseline, PROPOSAL_MAIN as _F49_PROPOSAL)

RICH_BASELINE = _f49_baseline()


def _cmp_config(state) -> dict:
    return {"doccompare_state_root": str(state)}


def _exp_config(state, red_state=None, cmp_state=None) -> dict:
    cfg = {"docexport_state_root": str(state),
           "libreoffice_soffice": SOFFICE}
    if red_state is not None:
        cfg["redline_state_root"] = str(red_state)
    if cmp_state is not None:
        cfg["doccompare_state_root"] = str(cmp_state)
    return cfg


class F55FixtureTests(unittest.TestCase):
    """夹具自证：两档差异面清晰（正文替换/插入/表格行/脚注增）。"""

    def test_fixture_docx_pair_differs_on_four_axes(self):
        from document_compare import docx_segments
        import tempfile
        td = Path(tempfile.mkdtemp())
        a = td / "a.docx"
        b = td / "b.docx"
        a.write_bytes(DOCX_V1)
        b.write_bytes(DOCX_V2)
        la = docx_segments(a)
        lb = docx_segments(b)
        # V1：5 正文段＋3 表行＋1 脚注＝9 段
        self.assertEqual(len(la["segments"]), 9)
        self.assertEqual(len(lb["segments"]), 11)     # V2：6 段＋3 行＋2 脚注
        ta = [s["text"] for s in la["segments"]]
        tb = [s["text"] for s in lb["segments"]]
        self.assertNotEqual(ta, tb)
        self.assertIn("第一条 合同价款：人民币36,000.00元整", ta)
        self.assertIn("第一条 合同价款：人民币38,500.00元整（含税费）", tb)
        self.assertTrue(any(s["category"] == "table_row"
                            for s in la["segments"]))

    def test_method_groups_closed(self):
        self.assertEqual(DOCCOMPARE_METHODS, frozenset({
            "doccompare.compare", "doccompare.report", "doccompare.list"}))
        self.assertEqual(DOC_EXPORT_METHODS, frozenset({
            "docexport.pdf", "docexport.report", "docexport.list"}))


class F55CompareTests(unittest.TestCase):
    """doccompare.compare：差量＋变更清单对应＋支持矩阵＋确定性。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        td = Path(self._tmp.name)
        self.a = td / "v1.docx"
        self.b = td / "v2.docx"
        self.a.write_bytes(DOCX_V1)
        self.b.write_bytes(DOCX_V2)
        self.state = td / "state"
        self.cfg = _cmp_config(self.state)

    def tearDown(self):
        self._tmp.cleanup()

    def test_docx_compare_change_list_correspondence(self):
        view = call("doccompare.compare",
                    {"document_id": "pair-1",
                     "left_path": str(self.a), "right_path": str(self.b)},
                    self.cfg)
        self.assertEqual(view["mode"], "docx_docx")
        self.assertTrue(view["range"]["declared"])
        self.assertEqual(view["range"]["supported_modes"],
                         ["docx_docx", "pdf_pdf"])
        self.assertEqual(view["correspondence"],
                         {"bijection": True, "coverage": True,
                          "sides": True})
        changes = view["changes"]
        self.assertGreaterEqual(changes["count"], 4)   # 替换/插入/表行/脚注
        rep = call("doccompare.report",
                   {"comparison_id": view["comparison_id"]}, self.cfg)
        items = rep["change_items"]
        # 双射：变更项 id 连续且与窗格行一一回指
        self.assertEqual([c["id"] for c in items],
                         [f"c{i + 1:03d}" for i in range(len(items))])
        self.assertTrue(all(c["row_id"].startswith("r") for c in items))
        kinds = {c["kind"] for c in items}
        self.assertIn("replace", kinds)
        self.assertIn("insert", kinds)
        # 覆盖：消费左/右档的行文本序列==实际登记分段（重建口径）
        before = [c["before_text"] for c in items if c["before_text"]]
        self.assertTrue(any("36,000.00" in b for b in before))
        after = [c["after_text"] for c in items if c["after_text"]]
        self.assertTrue(any("38,500.00" in a for a in after))

    def test_identical_pair_zero_changes_and_cross_profile_digest(self):
        v1 = call("doccompare.compare",
                  {"document_id": "same-1", "left_b64": base64.b64encode(
                      DOCX_V1).decode(),
                   "right_b64": base64.b64encode(DOCX_V1).decode()},
                  self.cfg)
        v2 = call("doccompare.compare",
                  {"document_id": "same-2", "left_b64": base64.b64encode(
                      DOCX_V1).decode(),
                   "right_b64": base64.b64encode(DOCX_V1).decode()},
                  self.cfg)
        self.assertEqual(v1["changes"]["count"], 0)
        self.assertEqual(v1["payload_digest"], v2["payload_digest"])

    def test_pdf_pair_compare(self):
        import tempfile
        td = Path(tempfile.mkdtemp())
        pa, pb = td / "v1.pdf", td / "v2.pdf"
        pa.write_bytes(PDF_V1)
        pb.write_bytes(PDF_V2)
        view = call("doccompare.compare",
                    {"document_id": "pdf-1", "left_path": str(pa),
                     "right_path": str(pb)}, self.cfg)
        self.assertEqual(view["mode"], "pdf_pdf")
        self.assertEqual(view["changes"]["by_category"], {"pdf_line": 2})
        items = view["change_items"] if "change_items" in view else \
            call("doccompare.report",
                 {"comparison_id": view["comparison_id"]},
                 self.cfg)["change_items"]
        texts = [c["before_text"] + "->" + c["after_text"] for c in items]
        self.assertTrue(any("36,000.00" in t and "38,500.00" in t
                            for t in texts))
        self.assertTrue(any("（修订版）" in t for t in texts))

    def test_mode_gate_unsupported_pairs(self):
        import tempfile
        td = Path(tempfile.mkdtemp())
        pdf = td / "a.pdf"
        pdf.write_bytes(PDF_V1)
        with self.assertRaises(NotConnected) as ctx:
            call("doccompare.compare",
                 {"document_id": "mix-1", "left_path": str(self.a),
                  "right_path": str(pdf)}, self.cfg)
        self.assertIn("f55_mode_unsupported:docx_pdf", str(ctx.exception))
        txt = td / "a.txt"
        txt.write_bytes("纯文本不属于支持矩阵".encode("utf-8"))
        with self.assertRaises(NotConnected) as ctx2:
            call("doccompare.compare",
                 {"document_id": "mix-2", "left_path": str(txt),
                  "right_path": str(txt)}, self.cfg)
        self.assertIn("f55_mode_unsupported", str(ctx2.exception))

    def test_outside_model_guard_numbering_only_difference(self):
        """仅编号标记差（可见文本零差量）＝具名拒，不假「无变化」。"""
        with_num = build_docx([_p("第一条 合同价款", 1), _p("第二条 交付")])
        no_num = build_docx([_p("第一条 合同价款"), _p("第二条 交付")])
        with self.assertRaises(NotConnected) as ctx:
            call("doccompare.compare",
                 {"document_id": "num-1",
                  "left_b64": base64.b64encode(with_num).decode(),
                  "right_b64": base64.b64encode(no_num).decode()},
                 self.cfg)
        self.assertIn("f55_difference_outside_segment_model:numbering_marks",
                      str(ctx.exception))

    def test_register_pinned_mismatch_negative(self):
        call("doccompare.compare",
             {"document_id": "pin-1", "left_path": str(self.a),
              "right_path": str(self.b)}, self.cfg)
        import tempfile
        td = Path(tempfile.mkdtemp())
        other = td / "other.docx"
        other.write_bytes(DOCX_V2)
        with self.assertRaises(NotConnected) as ctx:
            call("doccompare.compare",
                 {"document_id": "pin-1", "left_path": str(other),
                  "right_path": str(self.b)}, self.cfg)
        self.assertIn("f55_left_bytes_mismatch", str(ctx.exception))

    def test_determinism_payload_digest_two_state_roots(self):
        with tempfile.TemporaryDirectory() as td2:
            cfg2 = _cmp_config(Path(td2) / "state2")
            v1 = call("doccompare.compare",
                      {"document_id": "det-1", "left_path": str(self.a),
                       "right_path": str(self.b)}, self.cfg)
            v2 = call("doccompare.compare",
                      {"document_id": "det-1", "left_path": str(self.a),
                       "right_path": str(self.b)}, cfg2)
            self.assertEqual(v1["payload_digest"], v2["payload_digest"])

    def test_list_and_negatives(self):
        view = call("doccompare.compare",
                    {"document_id": "list-1", "left_path": str(self.a),
                     "right_path": str(self.b)}, self.cfg)
        listing = call("doccompare.list", {"document_id": "list-1"},
                       self.cfg)
        self.assertEqual([c["comparison_id"] for c in listing["comparisons"]],
                         [view["comparison_id"]])
        with self.assertRaises(NotConnected) as ctx:
            call("doccompare.report",
                 {"comparison_id": "list-1:9999-compare"}, self.cfg)
        self.assertIn("f55_comparison_not_found", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx2:
            call("doccompare.compare", {"document_id": "list-1"}, self.cfg)
        self.assertIn("f55_left_required", str(ctx2.exception))
        with self.assertRaises(NotConnected) as ctx3:
            call("doccompare.compare", {}, {})
        self.assertIn("f55_state_root_not_configured", str(ctx3.exception))
        with self.assertRaises(NotConnected) as ctx4:
            call("doccompare.explode", {}, self.cfg)
        self.assertIn("method_not_connected:doccompare.explode",
                      str(ctx4.exception))


@unittest.skipUnless(HAVE_SOFFICE, "LibreOffice 未安装——渲染类整组诚实跳过"
                     "（F54 先例；§6.1 裁决#5 本机已装时应为真）")
class F58ExportTests(unittest.TestCase):
    """docexport.pdf：真渲染＋保变更范围＋失败不交空 PDF。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        td = Path(self._tmp.name)
        self.red_state = td / "red"
        self.exp_state = td / "exp"
        self.cmp_state = td / "cmp"
        red_cfg = {"redline_state_root": str(self.red_state)}
        r1 = call("redline.register",
                  {"document_id": "doc1",
                   "docx_b64": base64.b64encode(RICH_BASELINE).decode()},
                  red_cfg)
        r2 = call("redline.replay",
                  {"document_id": "doc1", "proposal": _F49_PROPOSAL},
                  red_cfg)
        r3 = call("redline.compare",
                  {"document_id": "doc1", "proposal_id": r2["proposal_id"]},
                  red_cfg)
        self.redline_id = r3["redline_id"]
        self.assertGreaterEqual(r3["revisions"]["count"], 5)

    def tearDown(self):
        self._tmp.cleanup()

    def test_redline_pdf_export_scope_preserved(self):
        cfg = _exp_config(self.exp_state, red_state=self.red_state)
        out = call("docexport.pdf",
                   {"source": "redline", "redline_id": self.redline_id}, cfg)
        self.assertEqual(out["schema"], "juscite-f58-document-export/1")
        self.assertGreaterEqual(out["pdf"]["page_count"], 1)
        self.assertGreaterEqual(out["pdf"]["total_lines"], 1)
        self.assertEqual(out["engine"]["name"], "libreoffice")
        scope = out["change_scope"]
        self.assertGreater(scope["checked"], 0)
        self.assertEqual(scope["checked"], scope["matched"])
        self.assertEqual(scope["granularity"],
                         "revision_run_normalized_containment")
        # 源字节钉定：source sha == U14 面回执 sha
        red_view = call("redline.redline",
                        {"redline_id": self.redline_id},
                        {"redline_state_root": str(self.red_state)})
        self.assertEqual(out["source"]["sha256"], red_view["sha256"])
        # report 回读＋list 可枚举
        rep = call("docexport.report", {"export_id": out["export_id"]}, cfg)
        self.assertEqual(rep["pdf"]["sha256"], out["pdf"]["sha256"])
        lst = call("docexport.list", {}, cfg)
        self.assertEqual([e["export_id"] for e in lst["exports"]],
                         [out["export_id"]])

    def test_compare_report_pdf_export(self):
        td = Path(self._tmp.name)
        a, b = td / "v1.docx", td / "v2.docx"
        a.write_bytes(DOCX_V1)
        b.write_bytes(DOCX_V2)
        view = call("doccompare.compare",
                    {"document_id": "exp-1", "left_path": str(a),
                     "right_path": str(b)}, _cmp_config(self.cmp_state))
        cfg = _exp_config(self.exp_state, cmp_state=self.cmp_state)
        out = call("docexport.pdf",
                   {"source": "compare_report",
                    "comparison_id": view["comparison_id"]}, cfg)
        self.assertEqual(out["source"]["kind"], "compare_report")
        scope = out["change_scope"]
        self.assertGreaterEqual(scope["checked"], 4)
        self.assertEqual(scope["checked"], scope["matched"])
        self.assertEqual(scope["granularity"],
                         "change_item_side_normalized_containment")

    def test_failure_leaves_no_artifact(self):
        """失败不交空 PDF：坏源渲染失败/空文档不可读——typed 拒＋目录清除。"""
        cfg = _exp_config(self.exp_state, red_state=self.red_state)
        # 合法 zip 但 document.xml 坏 XML → LibreOffice 渲染失败（实测
        # rc=1 无产物；纯垃圾字节会被 Writer 按文本导入——诚实容错不算
        # 渲染失败，故用坏 XML 打真失败路径）
        bad_buf = io.BytesIO()
        with zipfile.ZipFile(bad_buf, "w") as z:
            z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
            z.writestr("word/document.xml",
                       "<w:document><w:body><w:p>unclosed")
        with self.assertRaises(NotConnected) as ctx:
            call("docexport.pdf",
                 {"source": "docx",
                  "docx_b64": base64.b64encode(
                      bad_buf.getvalue()).decode()}, cfg)
        self.assertIn("f58_render_failed", str(ctx.exception))
        # 合法 docx 但零文本（单空段）→ 可阅读硬门拒
        empty_docx = build_docx([_p("")])
        with self.assertRaises(NotConnected) as ctx2:
            call("docexport.pdf",
                 {"source": "docx",
                  "docx_b64": base64.b64encode(empty_docx).decode()}, cfg)
        self.assertTrue("f58_unreadable_pdf" in str(ctx2.exception)
                        or "f58_empty_pdf" in str(ctx2.exception))
        exports = self.exp_state / "document-export" / "exports"
        if exports.is_dir():
            self.assertEqual(list(exports.iterdir()), [])
        with self.assertRaises(NotConnected) as ctx3:
            call("docexport.pdf",
                 {"source": "redline", "redline_id": "doc1:9999-compare"},
                 _exp_config(self.exp_state))   # 无 redline_state_root
        self.assertIn("f58_redline_state_root_not_configured",
                      str(ctx3.exception))

    def test_scope_loss_typed_rejection(self):
        """篡改源红线删除全部修订 run→无文本侧可核；改用查无对比源负向。"""
        cfg = _exp_config(self.exp_state, cmp_state=self.cmp_state)
        with self.assertRaises(NotConnected) as ctx:
            call("docexport.pdf",
                 {"source": "compare_report",
                  "comparison_id": "ghost:0001-compare"}, cfg)
        self.assertIn("f58_compare_source:f55_comparison_not_found",
                      str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx2:
            call("docexport.pdf", {"source": "carrier_pigeon"}, cfg)
        self.assertIn("f58_source_unsupported", str(ctx2.exception))


if __name__ == "__main__":
    unittest.main()
