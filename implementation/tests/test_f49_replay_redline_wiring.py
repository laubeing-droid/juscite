"""W2b-U14 / F49 wiring: 干净基版与提案 replay 对比产真修订红线
（redline.* 桥方法组 → document_redline 产品面 document-adapter）。

义务 06:F49 / 17 卡断言：「干净基版与提案replay对比产真修订；表格/脚注/
编号有内容回读」；06:F49「compareDocuments 差量，非会话内打标」「提案
replay 与渲染解耦，更稳」。

- 语料全合成（本文件自建富 OOXML 基线：正文/表格/脚注/编号，全部合成
  合同文本；00-总协调 §6.1 裁决#1，绝无真实文档）。
- 真修订断言：w:ins/w:del（delText 口径）/段标记/trPr/w:pPrChange 都是
  产物红线 DOCX 里的真 OOXML 修订标记（不模拟）。
- 对账双不变式：accept_all(红线)==replay 事实、reject_all(红线)==基线
  事实（正文/表格/脚注/编号四类）；内容回读自红线文档本身。
"""
import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from legal_entry import call, NotConnected  # noqa: E402

_W_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = "{%s}" % _W_URI
_MC_URI = "http://schemas.openxmlformats.org/markup-compatibility/2006"

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


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _p_xml(text: str, num_id=None, footnote_ids=()) -> str:
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
    """全合成富基线：正文 7 段（2 段编号）＋3×3 表＋2 脚注＋双编号定义。"""
    import io
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
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        f'<w:document xmlns:w="{_W_URI}"><w:body>{"".join(body)}'
        "</w:body></w:document>")
    footnotes = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        f'<w:footnotes xmlns:w="{_W_URI}">'
        '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/>'
        "</w:r></w:p></w:footnote>"
        '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r>'
        "<w:continuationSeparator/></w:r></w:p></w:footnote>"
        + "".join(
            f'<w:footnote w:id="{fid}"><w:p><w:r><w:t xml:space='
            f'"preserve">{_esc(text)}</w:t></w:r></w:p></w:footnote>'
            for fid, text in FOOTNOTES.items())
        + "</w:footnotes>")
    numbering = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        f'<w:numbering xmlns:w="{_W_URI}">'
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


def _config(state_root) -> dict:
    return {"redline_state_root": str(state_root)}


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class F49FixtureTests(unittest.TestCase):
    """基线夹具自证：干净态、四类事实齐全。"""

    def test_fixture_is_clean_rich_document(self):
        from document_redline import (_read_package_bytes, extract_facts,
                                      _gate_tree_clean)
        pkg = _read_package_bytes(build_rich_baseline_docx())
        _gate_tree_clean(pkg["trees"]["word/document.xml"], "")
        _gate_tree_clean(pkg["trees"]["word/footnotes.xml"], "footnotes.")
        facts = extract_facts(pkg["trees"]["word/document.xml"],
                              pkg["trees"]["word/footnotes.xml"],
                              pkg["trees"]["word/numbering.xml"])
        self.assertEqual(len(facts["body"]), 7)
        self.assertEqual(len(facts["tables"]), 1)
        self.assertEqual(facts["tables"][0], TABLE_ROWS)
        self.assertEqual(facts["footnotes"],
                         {str(k): v for k, v in FOOTNOTES.items()})
        self.assertEqual([n["num_id"] if n else None
                          for n in facts["numbering"]],
                         [None, None, "1", None, "1", None, None])
        self.assertEqual(facts["numbering"][2]["num_fmt"], "decimal")


class F49RegisterTests(unittest.TestCase):
    """干净基版闸：钉定/幂等/字节异拒/既有修订拒/模型外构件拒。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="f49-reg-"))
        self.src = self.tmp / "base.docx"
        self.src.write_bytes(build_rich_baseline_docx())

    def test_register_pins_baseline_and_facts(self):
        view = call("redline.register",
                    {"document_id": "doc-a", "docx_path": str(self.src),
                     "matter_id": "M-SYN"}, _config(self.tmp))
        self.assertEqual(view["schema"], "juscite-f49-replay-redline/1")
        self.assertEqual(view["model"], "supported_constructs_gated")
        self.assertEqual(view["baseline"]["sha256"], _sha(self.src))
        self.assertEqual(view["facts"]["body_paragraphs"], 7)
        self.assertEqual(view["facts"]["tables"], 1)
        self.assertEqual(view["facts"]["footnotes"], 2)
        self.assertEqual(view["facts"]["numbered_paragraphs"], 2)
        # 幂等复用：同字节再注册
        again = call("redline.register",
                     {"document_id": "doc-a", "docx_path": str(self.src)},
                     _config(self.tmp))
        self.assertEqual(again["baseline"]["sha256"],
                         view["baseline"]["sha256"])

    def test_register_refuses_different_bytes_same_id(self):
        call("redline.register",
             {"document_id": "doc-b", "docx_path": str(self.src)},
             _config(self.tmp))
        other = self.tmp / "other.docx"
        other.write_bytes(build_rich_baseline_docx() + b"\0")
        with self.assertRaises(NotConnected) as ctx:
            call("redline.register",
                 {"document_id": "doc-b", "docx_path": str(other)},
                 _config(self.tmp))
        self.assertIn("f49_baseline_bytes_mismatch", str(ctx.exception))

    def test_register_refuses_existing_revisions(self):
        import io
        rich = build_rich_baseline_docx()
        with zipfile.ZipFile(io.BytesIO(rich)) as zf:
            replaced = {}
            for name in zf.namelist():
                data = zf.read(name)
                if name == "word/document.xml":
                    data = data.replace(
                        b"<w:body>", b"<w:body><w:p><w:ins w:id=\"9\" "
                        b"w:author=\"x\" w:date=\"2026-01-01T00:00:00Z\">"
                        b"<w:r><w:t>already</w:t></w:r></w:ins></w:p>",
                        1)
                replaced[name] = data
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, data in replaced.items():
                zout.writestr(name, data)
        src = self.tmp / "revised.docx"
        src.write_bytes(buf.getvalue())
        with self.assertRaises(NotConnected) as ctx:
            call("redline.register",
                 {"document_id": "doc-rev", "docx_path": str(src)},
                 _config(self.tmp))
        self.assertIn("f49_baseline_has_existing_revisions",
                      str(ctx.exception))

    def test_register_refuses_unsupported_construct(self):
        import io
        rich = build_rich_baseline_docx()
        with zipfile.ZipFile(io.BytesIO(rich)) as zf:
            replaced = {name: zf.read(name) for name in zf.namelist()}
        replaced["word/document.xml"] = replaced["word/document.xml"].replace(
            b"</w:body>",
            b'<w:p><w:r><mc:AlternateContent xmlns:mc='
            b'"http://schemas.openxmlformats.org/markup-compatibility/2006">'
            b"<mc:Choice/></mc:AlternateContent></w:r></w:p></w:body>", 1)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
            for name, data in replaced.items():
                zout.writestr(name, data)
        src = self.tmp / "textbox.docx"
        src.write_bytes(buf.getvalue())
        with self.assertRaises(NotConnected) as ctx:
            call("redline.register",
                 {"document_id": "doc-tb", "docx_path": str(src)},
                 _config(self.tmp))
        self.assertIn("f49_baseline_unsupported_construct", str(ctx.exception))


class F49ReplayRedlineTests(unittest.TestCase):
    """提案 replay（渲染解耦）＋compareDocuments 差量产真修订红线。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="f49-main-"))
        cls.cfg = _config(cls.tmp)
        cls.src = cls.tmp / "base.docx"
        cls.src.write_bytes(build_rich_baseline_docx())
        call("redline.register",
             {"document_id": "doc-main", "docx_path": str(cls.src)},
             cls.cfg)
        cls.replay = call("redline.replay",
                          {"document_id": "doc-main",
                           "proposal": PROPOSAL_MAIN}, cls.cfg)
        cls.cmp = call("redline.compare",
                       {"document_id": "doc-main",
                        "proposal_id": cls.replay["proposal_id"]}, cls.cfg)
        cls.redline_path = (cls.tmp / "document-redline" / "doc-main"
                            / cls.cmp["redline"]["file"])

    def _doc_dir(self):
        return self.tmp / "document-redline" / "doc-main"

    def test_replay_is_decoupled_deterministic_artifact(self):
        self.assertEqual(self.replay["ops_applied"], 6)
        self.assertEqual(self.replay["author"], "lvyin-redline")
        replay_file = self._doc_dir() / self.replay["replay"]["file"]
        self.assertTrue(replay_file.is_file())
        # 同提案再重放 → 新序号 append-only，但字节级相同（确定性）
        second = call("redline.replay",
                      {"document_id": "doc-main",
                       "proposal": PROPOSAL_MAIN}, self.cfg)
        self.assertNotEqual(second["proposal_id"],
                            self.replay["proposal_id"])
        second_file = self._doc_dir() / second["replay"]["file"]
        self.assertEqual(_sha(second_file), _sha(replay_file))
        # replay 事实与基线事实确有分叉（提案产生了变更）
        self.assertNotEqual(self.replay["replay_facts"]["facts_digest"],
                            self.replay["baseline_facts"]["facts_digest"])

    def test_redline_carries_true_ooxml_revision_markup(self):
        raw = self.redline_path.read_bytes()
        doc_part = zipfile.ZipFile(self.redline_path).read(
            "word/document.xml").decode("utf-8")
        fn_part = zipfile.ZipFile(self.redline_path).read(
            "word/footnotes.xml").decode("utf-8")
        self.assertIn("<w:ins ", doc_part)        # 内联插入
        self.assertIn("<w:del ", doc_part)        # 内联删除
        self.assertIn("<w:delText", doc_part)     # 删除文本口径
        self.assertIn("<w:pPrChange", doc_part)   # 编号属性变更
        self.assertIn("<w:delText", fn_part)      # 脚注修订
        # 修订作者＝提案声明（不伪装律师；F53 前置）
        self.assertIn('w:author="lvyin-redline"', doc_part)
        self.assertIn('w:date="2026-10-16T00:00:00Z"', doc_part)

    def test_reconciliation_dual_invariants_hold(self):
        rec = self.cmp["reconciliation"]
        self.assertTrue(rec["accept_all_equals_replay"])
        self.assertTrue(rec["reject_all_equals_baseline"])
        self.assertTrue(rec["readback_content_complete"])
        # 独立复核（不经面内声明）：直接从三份盘上文件用面对外可调函数重算
        import copy as copy_mod
        from document_redline import (_read_package, _accept_all, _reject_all,
                                      extract_facts)
        base_pkg = _read_package(self._doc_dir() / "baseline.docx")
        replay_pkg = _read_package(self._doc_dir()
                                   / self.replay["replay"]["file"])
        red_pkg = _read_package(self.redline_path)
        numbering = red_pkg["trees"].get("word/numbering.xml")

        def settled(accept):
            tree = copy_mod.deepcopy(
                red_pkg["trees"]["word/document.xml"])
            fn = copy_mod.deepcopy(
                red_pkg["trees"]["word/footnotes.xml"])
            if accept:
                _accept_all(tree)
                _accept_all(fn)
            else:
                _reject_all(tree)
                _reject_all(fn)
            return extract_facts(tree, fn, numbering)

        replay_facts = extract_facts(
            replay_pkg["trees"]["word/document.xml"],
            replay_pkg["trees"]["word/footnotes.xml"],
            replay_pkg["trees"].get("word/numbering.xml"))
        base_facts = extract_facts(
            base_pkg["trees"]["word/document.xml"],
            base_pkg["trees"]["word/footnotes.xml"],
            base_pkg["trees"].get("word/numbering.xml"))
        self.assertEqual(settled(True), replay_facts)
        self.assertEqual(settled(False), base_facts)

    def test_readback_covers_body_table_footnote_numbering(self):
        revs = self.cmp["revisions"]
        by_cat = revs["by_category"]
        for cat in ("body", "table", "footnote", "numbering"):
            self.assertGreaterEqual(by_cat.get(cat, 0), 1, cat)
        kinds = {r["kind"] for r in revs["items"]}
        self.assertIn("paragraph_insert", kinds)
        self.assertIn("paragraph_delete", kinds)
        self.assertIn("text_replace", kinds)
        self.assertIn("paragraph_property_change", kinds)
        for rev in revs["items"]:                     # 内容回读本体
            if rev["kind"] == "paragraph_property_change":
                self.assertEqual(rev["old_num_id"], "1")
                self.assertEqual(rev["new_num_id"], "2")
            elif rev["kind"] in ("paragraph_insert", "paragraph_delete"):
                key = "inserted_text" if "insert" in rev["kind"] \
                    else "deleted_text"
                self.assertTrue(rev[key])
            elif rev["kind"] == "text_replace":
                self.assertTrue(rev["inserted_text"] or rev["deleted_text"])
        foot = [r for r in revs["items"] if r["category"] == "footnote"]
        self.assertEqual(foot[0]["footnote_id"], "2")
        self.assertIn("修订版", foot[0]["inserted_text"])
        self.assertEqual(foot[0]["after_text"],
                         PROPOSAL_MAIN["ops"][4]["text"])
        self.assertEqual(foot[0]["before_text"], FOOTNOTES[2])
        self.assertTrue(foot[0]["deleted_text"])   # 旧字真删（delText 口径）

    def test_table_cell_change_readable_back(self):
        cell = [r for r in self.cmp["revisions"]["items"]
                if r["kind"] == "text_replace" and "table" in r]
        self.assertTrue(cell)
        target = [r for r in cell if r.get("table") == 0 and r.get("row") == 2
                  and r.get("col") == 2]
        self.assertTrue(target)
        # 双侧全文自红线标记回读（keep＋del / keep＋ins）
        self.assertEqual(target[0]["before_text"], "12,000.00")
        self.assertEqual(target[0]["after_text"], "12,500.00")
        self.assertTrue(target[0]["deleted_text"])
        self.assertTrue(target[0]["inserted_text"])

    def test_row_insert_delete_readback(self):
        replay = call("redline.replay",
                      {"document_id": "doc-main",
                       "proposal": PROPOSAL_ROWS}, self.cfg)
        cmp2 = call("redline.compare",
                    {"document_id": "doc-main",
                     "proposal_id": replay["proposal_id"]}, self.cfg)
        kinds = {r["kind"]: r for r in cmp2["revisions"]["items"]}
        self.assertIn("row_insert", kinds)
        self.assertIn("row_delete", kinds)
        self.assertEqual(kinds["row_delete"]["cells"], TABLE_ROWS[1])
        self.assertEqual(kinds["row_insert"]["cells"],
                         ["3", "2026-04-05", "12,000.00"])
        self.assertTrue(cmp2["reconciliation"]["accept_all_equals_replay"])
        self.assertTrue(cmp2["reconciliation"]["reject_all_equals_baseline"])

    def test_append_only_and_listing_no_orphans(self):
        first_sha = _sha(self.redline_path)
        replay = call("redline.replay",
                      {"document_id": "doc-main",
                       "proposal": PROPOSAL_ROWS}, self.cfg)
        cmp3 = call("redline.compare",
                    {"document_id": "doc-main",
                     "proposal_id": replay["proposal_id"]}, self.cfg)
        self.assertEqual(_sha(self.redline_path), first_sha)  # 旧红线不动
        listing = call("redline.list", {"document_id": "doc-main"},
                       self.cfg)
        self.assertEqual(len(listing["proposals"]), 2)   # 本类 setUpClass＋本测
        self.assertEqual(len(listing["redlines"]), 2)
        on_disk = sorted(p.parent.name for p in
                         (self._doc_dir() / "redlines").glob(
                             "*/redline.json"))
        listed = sorted(r["redline_id"].split(":")[1]
                        for r in listing["redlines"])
        self.assertEqual(on_disk, listed)
        self.assertEqual(cmp3["redline_id"].split(":")[1], "0002-compare")

    def test_report_and_b64_roundtrip_consumable(self):
        got = call("redline.report",
                   {"redline_id": self.cmp["redline_id"]}, self.cfg)
        self.assertEqual(got["redline"]["sha256"],
                         self.cmp["redline"]["sha256"])
        self.assertEqual(got["consumers"],
                         ["W2b-U16-wps-host", "E13-docx-closeout"])
        import base64
        blob = call("redline.redline",
                    {"redline_id": self.cmp["redline_id"]}, self.cfg)
        self.assertEqual(base64.b64decode(blob["docx_b64"]),
                         self.redline_path.read_bytes())
        self.assertEqual(blob["revision_count"],
                         self.cmp["revisions"]["count"])

    def test_determinism_byte_stable_across_documents(self):
        other = self.tmp / "doc-main2.docx"
        other.write_bytes(self.src.read_bytes())
        call("redline.register",
             {"document_id": "doc-main2", "docx_path": str(other)},
             self.cfg)
        replay = call("redline.replay",
                      {"document_id": "doc-main2",
                       "proposal": PROPOSAL_MAIN}, self.cfg)
        cmp4 = call("redline.compare",
                    {"document_id": "doc-main2",
                     "proposal_id": replay["proposal_id"]}, self.cfg)
        other_path = (self.tmp / "document-redline" / "doc-main2"
                      / cmp4["redline"]["file"])
        self.assertEqual(_sha(other_path), _sha(self.redline_path))
        self.assertEqual(cmp4["redline"]["content_digest"],
                         self.cmp["redline"]["content_digest"])


class F49FailClosedTests(unittest.TestCase):
    """桥 fail-closed：未配置/未知方法/坏 id/坏提案/未注册/未找到。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="f49-neg-"))
        self.cfg = _config(self.tmp)
        self.src = self.tmp / "base.docx"
        self.src.write_bytes(build_rich_baseline_docx())
        call("redline.register",
             {"document_id": "doc-n", "docx_path": str(self.src)}, self.cfg)

    def test_missing_state_root(self):
        with self.assertRaises(NotConnected) as ctx:
            call("redline.list", {"document_id": "doc-n"}, {})
        self.assertIn("redline_failed:f49_state_root_not_configured",
                      str(ctx.exception))

    def test_unknown_method_not_connected(self):
        with self.assertRaises(NotConnected) as ctx:
            call("redline.explode", {}, self.cfg)
        self.assertIn("method_not_connected:redline.explode",
                      str(ctx.exception))

    def test_bad_document_id(self):
        with self.assertRaises(NotConnected) as ctx:
            call("redline.register",
                 {"document_id": "../escape", "docx_path": str(self.src)},
                 self.cfg)
        self.assertIn("f49_document_id_invalid", str(ctx.exception))

    def test_unknown_op_refused(self):
        with self.assertRaises(NotConnected) as ctx:
            call("redline.replay",
                 {"document_id": "doc-n", "proposal": {
                     "author": "lvyin-redline", "authored_utc": "2026-10-16T00:00:00Z",
                     "ops": [{"op": "body.explode"}]}}, self.cfg)
        self.assertIn("f49_proposal_op_unknown", str(ctx.exception))

    def test_op_target_missing(self):
        with self.assertRaises(NotConnected) as ctx:
            call("redline.replay",
                 {"document_id": "doc-n", "proposal": {
                     "author": "lvyin-redline", "authored_utc": "2026-10-16T00:00:00Z",
                     "ops": [{"op": "body.replace_text", "index": 99,
                              "text": "x"}]}}, self.cfg)
        self.assertIn("f49_op_target_missing", str(ctx.exception))

    def test_numbering_unknown_refused(self):
        with self.assertRaises(NotConnected) as ctx:
            call("redline.replay",
                 {"document_id": "doc-n", "proposal": {
                     "author": "lvyin-redline", "authored_utc": "2026-10-16T00:00:00Z",
                     "ops": [{"op": "para.numbering_set", "index": 0,
                              "num_id": 9}]}}, self.cfg)
        self.assertIn("f49_op_numbering_unknown", str(ctx.exception))

    def test_no_change_proposal_refused(self):
        with self.assertRaises(NotConnected) as ctx:
            call("redline.replay",
                 {"document_id": "doc-n", "proposal": {
                     "author": "lvyin-redline", "authored_utc": "2026-10-16T00:00:00Z",
                     "ops": [{"op": "body.replace_text", "index": 0,
                              "text": BODY_TEXTS[0]}]}}, self.cfg)
        self.assertIn("f49_proposal_no_change", str(ctx.exception))

    def test_unregistered_document_and_missing_replay(self):
        with self.assertRaises(NotConnected) as ctx:
            call("redline.replay",
                 {"document_id": "doc-none", "proposal": PROPOSAL_MAIN},
                 self.cfg)
        self.assertIn("f49_document_not_registered", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            call("redline.compare",
                 {"document_id": "doc-n",
                  "proposal_id": "doc-n:9999-replay"}, self.cfg)
        self.assertIn("f49_replay_not_found", str(ctx.exception))
        with self.assertRaises(NotConnected) as ctx:
            call("redline.report",
                 {"redline_id": "doc-n:9999-compare"}, self.cfg)
        self.assertIn("f49_redline_not_found", str(ctx.exception))

    def test_error_codes_never_carry_material_content(self):
        import re
        probes = []
        for method, args in (
                ("redline.replay", {"document_id": "doc-n",
                                    "proposal": {"ops": []}}),
                ("redline.replay", {"document_id": "doc-n",
                                    "proposal": {"author": "a",
                                                 "authored_utc": "bad",
                                                 "ops": [{"op":
                                                          "body.replace_text",
                                                          "index": 0,
                                                          "text": "x"}]}}),
                ("redline.compare", {"document_id": "doc-n",
                                     "proposal_id": "bad"})):
            try:
                call(method, args, self.cfg)
                probes.append("UNEXPECTED_SUCCESS")
            except NotConnected as exc:
                probes.append(str(exc))
        for code in probes:
            self.assertTrue(re.match(r"^[\w:.;-]+$", code), code)
            for material in ("张三", "李四", "36,000", "合成"):
                self.assertNotIn(material, code)


if __name__ == "__main__":
    unittest.main()
