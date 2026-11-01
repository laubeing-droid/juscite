"""F48 产品侧接线测试（W2b-U12）：<edits> 流式协议＋卡片状态机＋DB/书签
双持久化（edits.* 方法组）。

全部合成材料（合成 DOCX 由 tools/e12_corpus_gen.py --docx 现场生成，seed
钉定；或本测试自建最小 DOCX 字节）。分三层：

1. 协议层（parse_stream）：分块不可见（同字节任意切块同卡集）、实体解码、
   未知标签前向兼容警告、截断具名拒（未闭合尾卡绝不产出）、坏形/根非法/
   重复卡号/嵌套文本具名拒、卡片字段校验闭集。
2. 引擎层（apply_card_to_tree/scan/reconcile，经 edits_call 全链）：
   唯一 quote 定位（零/多命中具名拒）、真修订 OOXML 形（replace＝w:del
   [delText 原文]＋w:ins [新文] 两个独立元素＝office-js#5188 规避；insert
   只 ins；delete 只 del）、书签包裹、现行文本语义（delText 不算现行）、
   既有修订 id 越位分配、他部件字节保真、原子写、同输入字节确定性、
   状态机守卫、宿主动过后对账以实际文档为准（host_accepted/host_removed）。
3. 桥层（legal_entry）：EDITS_METHODS 冻结组、未配置状态根 fail-closed
   NOT_CONNECTED（exit 3 类）、未知方法 method_not_connected。
"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
import edits_protocol as ep  # noqa: E402

W = ep.W

# --------------------------------------------------------------------------
# 合成 DOCX 夹具（最小但多部件：正文/表/页眉/脚注；全合成虚构文本）
# --------------------------------------------------------------------------

MIN_PARAGRAPHS = [
    "第一条 合成甲方向合成乙方供应合成设备，货款总额人民币480,000.00元。",
    "第二条 合成乙方应在验收合格后三十日内付清全部款项，逾期按日计付违约金。",
    "第三条 因本合同发生的争议，由合同签订地有管辖权的人民法院管辖。",
    "第四条 本合同一式两份，双方各执一份，自签字或盖章之日起生效。",
]


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_min_docx() -> bytes:
    """多部件最小 DOCX（正文含跨 run 段落＋表格＋脚注引用＋页眉脚）。"""
    def para(text, split=None, footnote=False):
        pieces = []
        previous = 0
        for offset in sorted(set(split or [])) + [len(text)]:
            pieces.append(text[previous:offset])
            previous = offset
        runs = "".join(
            f"<w:r><w:t>{_xml_escape(p)}</w:t></w:r>"
            for p in pieces if p)
        foot = ('<w:r><w:rPr><w:rStyle w:val="a4"/></w:rPr>'
                '<w:footnoteReference w:id="1"/></w:r>') if footnote else ""
        return f"<w:p>{runs}{foot}</w:p>"

    body = [para(MIN_PARAGRAPHS[0], [10, 26]),
            para(MIN_PARAGRAPHS[1], [8, 30]),
            para(MIN_PARAGRAPHS[2]),
            para(MIN_PARAGRAPHS[3], footnote=True)]
    body.append(
        "<w:tbl><w:tblGrid><w:gridCol w:w=\"2800\"/><w:gridCol w:w=\"2800\"/>"
        "</w:tblGrid><w:tr>"
        '<w:tc><w:tcPr><w:tcW w:w="2800" w:type="dxa"/></w:tcPr>'
        "<w:p><w:r><w:t>款项名称</w:t></w:r></w:p></w:tc>"
        '<w:tc><w:tcPr><w:tcW w:w="2800" w:type="dxa"/></w:tcPr>'
        "<w:p><w:r><w:t>96,000.00</w:t></w:r></w:p></w:tc>"
        "</w:tr></w:tbl>")
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<w:document xmlns:w="' + ep.W_NS
                + '" xmlns:r="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships"><w:body>'
                + "".join(body)
                + '<w:sectPr><w:headerReference w:type="default" r:id="rId3"/>'
                '<w:footerReference w:type="default" r:id="rId4"/>'
                '<w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
                + "</w:body></w:document>")
    header = ('<?xml version="1.0" encoding="UTF-8"?>'
              '<w:hdr xmlns:w="' + ep.W_NS + '"><w:p><w:r><w:t>合成页眉</w:t>'
              "</w:r></w:p></w:hdr>")
    footer = ('<?xml version="1.0" encoding="UTF-8"?>'
              '<w:ftr xmlns:w="' + ep.W_NS + '"><w:p><w:r><w:t>合成页脚</w:t>'
              "</w:r></w:p></w:ftr>")
    footnotes = ('<?xml version="1.0" encoding="UTF-8"?>'
                 '<w:footnotes xmlns:w="' + ep.W_NS + '">'
                 '<w:footnote w:type="separator" w:id="-1"><w:p/></w:footnote>'
                 '<w:footnote w:type="continuationSeparator" w:id="0"><w:p/>'
                 "</w:footnote>"
                 '<w:footnote w:id="1"><w:p><w:r><w:t>合成脚注文本</w:t></w:r>'
                 "</w:p></w:footnote></w:footnotes>")
    styles = ('<?xml version="1.0" encoding="UTF-8"?>'
              '<w:styles xmlns:w="' + ep.W_NS + '">'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
              '<w:name w:val="Normal"/></w:style></w:styles>')
    parts = [
        ("[Content_Types].xml",
         '<?xml version="1.0" encoding="UTF-8"?>'
         '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
         'content-types"><Default Extension="rels" ContentType="application/'
         'vnd.openxmlformats-package.relationships+xml"/>'
         '<Default Extension="xml" ContentType="application/xml"/>'
         '<Override PartName="/word/document.xml" ContentType="application/'
         'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"'
         '/><Override PartName="/word/styles.xml" ContentType="application/'
         'vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
         '<Override PartName="/word/footnotes.xml" ContentType="application/'
         'vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>'
         '<Override PartName="/word/header1.xml" ContentType="application/'
         'vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
         '<Override PartName="/word/footer1.xml" ContentType="application/'
         'vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
         "</Types>"),
        ("_rels/.rels",
         '<?xml version="1.0" encoding="UTF-8"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
         '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
         'openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
         ' Target="word/document.xml"/></Relationships>'),
        ("word/document.xml", document),
        ("word/styles.xml", styles),
        ("word/footnotes.xml", footnotes),
        ("word/header1.xml", header),
        ("word/footer1.xml", footer),
        ("word/_rels/document.xml.rels",
         '<?xml version="1.0" encoding="UTF-8"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
         '2006/relationships">'
         '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
         'officeDocument/2006/relationships/styles" Target="styles.xml"/>'
         '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/'
         'officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/>'
         '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/'
         'officeDocument/2006/relationships/header" Target="header1.xml"/>'
         '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/'
         'officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
         "</Relationships>"),
    ]
    import io
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in parts:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, payload.encode("utf-8"))
    return buffer.getvalue()


def edits_stream(*cards: str) -> str:
    return "<edits>" + "".join(cards) + "</edits>"


def edit_card(card_id: str, op: str, old: str, new: str = "",
              reason: str = "合成理由") -> str:
    new_xml = f"<new>{_xml_escape(new)}</new>" if op != "delete" else ""
    return (f'<edit id="{card_id}" op="{op}">'
            f"<old>{_xml_escape(old)}</old>{new_xml}"
            f"<reason>{_xml_escape(reason)}</reason></edit>")


class F48Fixture:
    """每测试一个临时状态根＋登记好的最小合成 DOCX。"""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="juscite-f48-test-")
        self.root = Path(self.tmp.name)
        self.config = {"edits_state_root": str(self.root)}
        self.docx = build_min_docx()
        self.call("edits.register", {"document_id": "d1",
                                     "bytesB64": base64.b64encode(
                                         self.docx).decode("ascii")})

    def call(self, method, args):
        return ep.edits_call(method, args, self.config)

    def feed(self, stream: str, stream_id: str = "s1", chunk: int = 7):
        self.call("edits.stream_open", {"document_id": "d1",
                                        "stream_id": stream_id})
        for i in range(0, len(stream), chunk):
            self.call("edits.stream_push",
                      {"document_id": "d1", "stream_id": stream_id,
                       "chunk": stream[i:i + chunk]})
        return self.call("edits.stream_close",
                         {"document_id": "d1", "stream_id": stream_id})

    def working(self) -> Path:
        return self.root / "edits-protocol" / "d1" / "working.docx"

    def close(self):
        self.tmp.cleanup()


# --------------------------------------------------------------------------
# 1. 协议层
# --------------------------------------------------------------------------

class ProtocolParserTests(unittest.TestCase):

    STREAM = edits_stream(
        edit_card("c1", "replace", "旧句一", "新句一"),
        edit_card("c2", "insert", "锚点二", "插入二"),
        edit_card("c3", "delete", "删除三"),
    )

    def test_chunking_invisible(self):
        """同字节任意切块（1 字符/7/整段）解析结果相同——流式分块语义不可见。"""
        baseline = None
        for size in (1, 7, 40, len(self.STREAM)):
            chunks = [self.STREAM[i:i + size]
                      for i in range(0, len(self.STREAM), size)]
            parsed = ep.parse_stream(chunks, final=True)
            self.assertIsNone(parsed["protocol_error"])
            snapshot = json.dumps(parsed["cards"], ensure_ascii=False,
                                  sort_keys=True)
            if baseline is None:
                baseline = snapshot
            self.assertEqual(snapshot, baseline)

    def test_entity_decoding(self):
        stream = edits_stream(
            '<edit id="e1" op="replace"><old>甲&amp;乙&lt;丙</old>'
            "<new>新&amp;文</new></edit>")
        parsed = ep.parse_stream([stream], final=True)
        self.assertEqual(parsed["cards"][0]["quote"], "甲&乙<丙")
        self.assertEqual(parsed["cards"][0]["new_text"], "新&文")

    def test_unknown_tag_forward_compatible(self):
        stream = edits_stream(
            '<edit id="u1" op="replace"><old>旧</old><new>新</new>'
            "<occurrence>1</occurrence></edit>")
        parsed = ep.parse_stream([stream], final=True)
        self.assertIsNone(parsed["protocol_error"])
        self.assertEqual(len(parsed["cards"]), 1)
        self.assertTrue(any("occurrence" in w
                            for w in parsed["warnings"]))

    def test_truncated_stream_named_refusal(self):
        """截断（未闭合尾卡）：完整前卡照常产出，尾卡绝不产出＋具名拒。"""
        stream = self.STREAM[:-12]     # 掐断最后 </edit></edits> 尾部
        parsed = ep.parse_stream([stream], final=True)
        self.assertEqual(parsed["protocol_error"]["code"], "f48_stream_truncated")
        card_ids = [card["card_id"] for card in parsed["cards"]]
        self.assertEqual(card_ids, ["c1", "c2"])   # c3 未闭合不产出

    def test_intermediate_push_is_incomplete_not_error(self):
        stream = self.STREAM[:60]
        parsed = ep.parse_stream([stream], final=False)
        self.assertIsNone(parsed["protocol_error"])
        self.assertFalse(parsed["closed"])

    def test_malformed_named_refusal(self):
        parsed = ep.parse_stream(["<edits><edit id=op=></edit></edits>"],
                                 final=True)
        self.assertEqual(parsed["protocol_error"]["code"],
                         "f48_protocol_malformed")

    def test_root_invalid(self):
        for payload in ("<wrongs><edit/></wrongs>",
                        "<edits></edits><junk/>",
                        ""):
            parsed = ep.parse_stream([payload], final=True)
            self.assertIsNotNone(parsed["protocol_error"])
            self.assertEqual(parsed["cards"], [])

    def test_duplicate_card_id(self):
        stream = edits_stream(edit_card("d1", "delete", "甲"),
                              edit_card("d1", "delete", "乙"))
        parsed = ep.parse_stream([stream], final=True)
        self.assertEqual(parsed["protocol_error"]["code"],
                         "f48_protocol_duplicate_card_id")

    def test_card_validation_closed_set(self):
        cases = [
            ('<edit op="replace"><old>甲</old><new>乙</new></edit>',
             "f48_protocol_card_id_invalid"),
            ('<edit id="x1" op="swap"><old>甲</old><new>乙</new></edit>',
             "f48_protocol_edit_invalid:op"),
            ('<edit id="x1" op="replace"><old></old><new>乙</new></edit>',
             "f48_protocol_edit_invalid:old_required"),
            ('<edit id="x1" op="insert"><old>甲</old><new></new></edit>',
             "f48_protocol_edit_invalid:new_required"),
            ('<edit id="x1" op="delete"><old>甲</old><new>乙</new></edit>',
             "f48_protocol_edit_invalid:delete_with_new"),
            ('<edit id="x1" op="replace"><old><b>甲</b></old>'
             "<new>乙</new></edit>", "f48_protocol_nested_invalid"),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload[:40]):
                parsed = ep.parse_stream([edits_stream(payload)], final=True)
                self.assertEqual(parsed["protocol_error"]["code"], expected)


# --------------------------------------------------------------------------
# 2. 引擎层（经 edits_call 全链：唯一 quote 定位／真修订／双持久化对账）
# --------------------------------------------------------------------------

class EngineApplyTests(unittest.TestCase):

    def setUp(self):
        self.fx = F48Fixture()
        self.addCleanup(self.fx.close)

    def apply_stream(self, cards_xml, accept, reject=None, chunk=7):
        closed = self.fx.feed(edits_stream(*cards_xml))
        self.assertIsNone(closed["protocol_error"])
        self.fx.call("edits.locate", {"document_id": "d1",
                                      "stream_id": "s1"})
        return self.fx.call("edits.apply", {
            "document_id": "d1", "stream_id": "s1", "card_ids": accept,
            "reject_card_ids": reject or [],
            "revision_author": "lvyin-edits",
            "revision_date": "2026-10-17T00:00:00Z"})

    def scan(self):
        return ep.scan_document(ep.load_docx_parts(self.fx.working()))

    def current_text(self):
        parts = ep.load_docx_parts(self.fx.working())
        root, _, _ = ep._parse_document_xml(parts["word/document.xml"])
        text, _ = ep.build_text_index(root)
        return text

    def test_replace_lands_split_revision_pair(self):
        """#5188 规避核心断言：replace＝w:del（delText 逐字原文）＋w:ins
        （新文）两个**独立**修订元素，非单一合并 op。"""
        old = MIN_PARAGRAPHS[0]
        new = "第一条（修订） 合成货款总额人民币560,000.00元。"
        result = self.apply_stream(
            [edit_card("c1", "replace", old, new)], ["c1"])
        self.assertTrue(result["cards"][0]["applied"])
        scan = self.scan()
        dels = [rev for rev in scan["revisions"] if rev["kind"] == "del"]
        ins = [rev for rev in scan["revisions"] if rev["kind"] == "ins"]
        self.assertEqual(len(dels), 1)
        self.assertEqual(len(ins), 1)
        self.assertEqual(dels[0]["text"], old)      # 删除侧证据=delText 原文
        self.assertEqual(ins[0]["text"], new)
        # 现行文本语义：旧句不在现行文本（只在 delText），新句在
        self.assertNotIn(old, self.current_text())
        self.assertIn(new, self.current_text())

    def test_insert_and_delete_single_revision_elements(self):
        anchor = MIN_PARAGRAPHS[1]
        self.apply_stream([
            edit_card("i1", "insert", anchor, "（插入句）"),
            edit_card("d1", "delete", MIN_PARAGRAPHS[2]),
        ], ["i1", "d1"])
        scan = self.scan()
        kinds = [(rev["kind"], rev["text"]) for rev in scan["revisions"]]
        self.assertIn(("ins", "（插入句）"), kinds)
        self.assertIn(("del", MIN_PARAGRAPHS[2]), kinds)
        self.assertEqual(len(scan["revisions"]), 2)
        self.assertIn("（插入句）", self.current_text())
        self.assertNotIn(MIN_PARAGRAPHS[2], self.current_text())

    def test_bookmark_wraps_revision_region(self):
        self.apply_stream([edit_card("c1", "replace", MIN_PARAGRAPHS[0],
                                     "新句。")], ["c1"])
        scan = self.scan()
        self.assertIn("JF48_c1", scan["bookmarks"])
        self.assertEqual(scan["bookmarks"]["JF48_c1"]["text"], "新句。")

    def test_unique_quote_localization(self):
        """零命中/多命中具名拒，卡片落 locate_failed，不碰文档。"""
        before = self.fx.working().read_bytes()
        closed = self.fx.feed(edits_stream(
            edit_card("nf", "replace", "文档中不存在的句子。", "新"),
            edit_card("nu", "replace", "合成", "新")))
        self.fx.call("edits.locate", {"document_id": "d1",
                                      "stream_id": "s1"})
        cards = self.fx.call("edits.cards", {"document_id": "d1"})["cards"]
        by_id = {card["card_id"]: card for card in cards}
        self.assertEqual(by_id["nf"]["state"], "locate_failed")
        self.assertEqual(by_id["nf"]["state_reason"], "quote_not_found")
        # “合成”出现多次（每段都有）→ 多命中具名拒
        self.assertEqual(by_id["nu"]["state"], "locate_failed")
        self.assertEqual(by_id["nu"]["state_reason"], "quote_not_unique")
        self.assertEqual(self.fx.working().read_bytes(), before)

    def test_state_machine_guards(self):
        closed = self.fx.feed(edits_stream(
            edit_card("c1", "replace", MIN_PARAGRAPHS[0], "新句。")))
        # 未 locate 直接 apply → 具名拒
        with self.assertRaises(ep.EditsError) as ctx:
            self.fx.call("edits.apply", {
                "document_id": "d1", "stream_id": "s1", "card_ids": ["c1"],
                "revision_author": "lvyin-edits", "revision_date":
                    "2026-10-17T00:00:00Z"})
        self.assertIn("f48_card_state_invalid", str(ctx.exception))
        self.fx.call("edits.locate", {"document_id": "d1",
                                      "stream_id": "s1"})
        # 重复 locate → 具名拒（已转移）
        with self.assertRaises(ep.EditsError) as ctx:
            self.fx.call("edits.locate", {"document_id": "d1",
                                          "stream_id": "s1"})
        self.assertIn("f48_card_state_invalid", str(ctx.exception))
        self.fx.call("edits.apply", {
            "document_id": "d1", "stream_id": "s1", "card_ids": ["c1"],
            "revision_author": "lvyin-edits", "revision_date": "2026-10-17T00:00:00Z"})
        # 已 applied 再 apply → 具名拒
        with self.assertRaises(ep.EditsError) as ctx:
            self.fx.call("edits.apply", {
                "document_id": "d1", "stream_id": "s1", "card_ids": ["c1"],
                "revision_author": "lvyin-edits", "revision_date":
                    "2026-10-17T00:00:00Z"})
        self.assertIn("f48_card_state_invalid", str(ctx.exception))

    def test_reject_leaves_document_untouched(self):
        before = self.fx.working().read_bytes()
        self.apply_stream([edit_card("r1", "replace", MIN_PARAGRAPHS[0],
                                     "不应出现")],
                          accept=[], reject=["r1"])
        self.assertEqual(self.fx.working().read_bytes(), before)
        cards = self.fx.call("edits.cards", {"document_id": "d1"})["cards"]
        self.assertEqual(cards[0]["state"], "rejected")
        self.assertEqual(cards[0]["state_reason"], "human_rejected")
        scan = self.scan()
        self.assertEqual(scan["revisions"], [])
        self.assertNotIn("JF48_r1", scan["bookmarks"])

    def test_table_cell_quote_localizes(self):
        result = self.apply_stream(
            [edit_card("t1", "delete", "96,000.00")], ["t1"])
        self.assertTrue(result["cards"][0]["applied"])
        self.assertNotIn("96,000.00", self.current_text())
        self.assertIn("96,000.00",
                      [rev["text"] for rev in self.scan()["revisions"]
                       if rev["kind"] == "del"][0])

    def test_other_parts_byte_identical_and_deterministic(self):
        original_parts = ep.load_docx_parts_from_bytes(self.fx.docx)
        self.apply_stream([
            edit_card("c1", "replace", MIN_PARAGRAPHS[0], "新句。"),
            edit_card("d1", "delete", MIN_PARAGRAPHS[1]),
        ], ["c1", "d1"])
        after = ep.load_docx_parts(self.fx.working())
        for name, payload in original_parts.items():
            if name != "word/document.xml":
                self.assertEqual(after[name], payload,
                                 f"部件被意外改动: {name}")
        # 同输入两跑字节级同输出（确定性）
        other = F48Fixture()
        self.addCleanup(other.close)
        other.feed(edits_stream(edit_card("c1", "replace", MIN_PARAGRAPHS[0],
                                          "新句。"),
                                edit_card("d1", "delete",
                                          MIN_PARAGRAPHS[1])), chunk=13)
        other.call("edits.locate", {"document_id": "d1",
                                    "stream_id": "s1"})
        other.call("edits.apply", {
            "document_id": "d1", "stream_id": "s1", "card_ids": ["c1", "d1"],
            "revision_author": "lvyin-edits",
            "revision_date": "2026-10-17T00:00:00Z"})
        self.assertEqual(self.fx.working().read_bytes(),
                         other.working().read_bytes())

    def test_registration_discipline(self):
        # 同 id 同字节＝幂等重读；异字节＝具名拒（原件钉定不覆盖）
        again = self.fx.call("edits.register", {
            "document_id": "d1",
            "bytesB64": base64.b64encode(self.fx.docx).decode("ascii")})
        self.assertFalse(again["registered"])
        with self.assertRaises(ep.EditsError) as ctx:
            self.fx.call("edits.register", {
                "document_id": "d1",
                "bytesB64": base64.b64encode(b"not-a-docx").decode("ascii")})
        self.assertEqual(str(ctx.exception), "f48_document_bytes_mismatch")

    def test_read_document_returns_actual_file(self):
        self.apply_stream([edit_card("c1", "replace", MIN_PARAGRAPHS[0],
                                     "新句。")], ["c1"])
        result = self.fx.call("edits.read_document", {"document_id": "d1"})
        import hashlib
        raw = base64.b64decode(result["bytesB64"])
        self.assertEqual(raw, self.fx.working().read_bytes())
        self.assertEqual(result["sha256"],
                         hashlib.sha256(raw).hexdigest())

    def test_reconcile_document_authoritative(self):
        """宿主动过实际文档后重载对账：host_accepted/host_removed 以
        实际文档为准改写 DB，事件留痕。"""
        self.apply_stream([
            edit_card("a1", "replace", MIN_PARAGRAPHS[0], "接受后新句。"),
            edit_card("k1", "insert", MIN_PARAGRAPHS[1], "（存活插入）"),
            edit_card("g1", "delete", MIN_PARAGRAPHS[2]),
        ], ["a1", "k1", "g1"])
        # ---- 宿主模拟（外部直接改文件字节：接受 a1 修订；整体移除 g1）
        parts = ep.load_docx_parts(self.fx.working())
        root, decls, dns = ep._parse_document_xml(parts["word/document.xml"])

        def region(name):
            for bm in root.iter(W + "bookmarkStart"):
                if bm.get(W + "name") == name:
                    for p in root.iter(W + "p"):
                        if any(el is bm for el in p.iter()):
                            return p

        container = region("JF48_a1")
        children = list(container)
        seen = False
        for el in children:
            if el.tag == W + "bookmarkStart" \
                    and el.get(W + "name") == "JF48_a1":
                seen = True
                continue
            if el.tag == W + "bookmarkEnd":
                break
            if not seen:
                continue
            if el.tag == W + "ins":
                index = list(container).index(el)
                for run in list(el):
                    container.insert(index, run)
                    index += 1
                container.remove(el)
            elif el.tag == W + "del":
                container.remove(el)
        container = region("JF48_g1")
        children = list(container)
        seen = False
        for el in children:
            if el.tag == W + "bookmarkStart" \
                    and el.get(W + "name") == "JF48_g1":
                seen = True
                container.remove(el)
                continue
            if el.tag == W + "bookmarkEnd" and seen:
                container.remove(el)
                break
            if not seen:
                continue
            if el.tag in (W + "ins", W + "del"):
                container.remove(el)
        parts["word/document.xml"] = ep._serialize_document_xml(
            root, decls, dns)
        ep.write_docx_atomic(self.fx.working(), parts)
        # ---- 重载对账（fresh call 重读盘上文件）
        report = self.fx.call("edits.reconcile", {"document_id": "d1"})
        by_id = {card["card_id"]: card for card in report["cards"]}
        self.assertEqual(by_id["a1"]["db_state_after"], "host_accepted")
        self.assertTrue(by_id["a1"]["document"]["bookmark_present"])
        self.assertEqual(by_id["k1"]["db_state_after"], "applied")
        self.assertEqual(by_id["k1"]["resolution"], "intact")
        self.assertEqual(by_id["g1"]["db_state_after"], "host_removed")
        self.assertFalse(by_id["g1"]["document"]["bookmark_present"])
        self.assertEqual(report["authoritative"], "document")
        # DB 侧复扫（双持久化对账落账）
        cards = self.fx.call("edits.cards", {"document_id": "d1"})["cards"]
        states = {card["card_id"]: card["state"] for card in cards}
        self.assertEqual(states, {"a1": "host_accepted", "k1": "applied",
                                  "g1": "host_removed"})

    def test_existing_revisions_ids_not_reused(self):
        """既有他作者修订：新修订 id 越位分配、既有修订原样保留。"""
        docx = build_min_docx()
        # 在第一段前插入前手修订（w:ins id=900 / w:del id=901）
        import io
        buffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(docx)) as zin, \
                zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                payload = zin.read(info.filename)
                if info.filename == "word/document.xml":
                    text = payload.decode("utf-8")
                    text = text.replace(
                        "<w:body>",
                        '<w:body><w:ins w:id="900" w:author="prior-author"'
                        ' w:date="2026-09-01T00:00:00Z"><w:r><w:t>'
                        "前手插入句</w:t></w:r></w:ins>"
                        '<w:del w:id="901" w:author="prior-author"'
                        ' w:date="2026-09-02T00:00:00Z"><w:r><w:delText>'
                        "前手删除句</w:delText></w:r></w:del>")
                    payload = text.encode("utf-8")
                info.date_time = (1980, 1, 1, 0, 0, 0)
                zout.writestr(info, payload)
        prior_docx = buffer.getvalue()
        with tempfile.TemporaryDirectory(prefix="juscite-f48-prior-") as tmp:
            config = {"edits_state_root": tmp}
            ep.edits_call("edits.register", {
                "document_id": "d2",
                "bytesB64": base64.b64encode(prior_docx).decode("ascii")},
                config)
            ep.edits_call("edits.stream_open", {"document_id": "d2",
                                                "stream_id": "s1"}, config)
            ep.edits_call("edits.stream_push", {
                "document_id": "d2", "stream_id": "s1",
                "chunk": edits_stream(edit_card("c1", "replace",
                                                MIN_PARAGRAPHS[0], "新句。"))},
                config)
            ep.edits_call("edits.stream_close", {"document_id": "d2",
                                                 "stream_id": "s1"}, config)
            ep.edits_call("edits.locate", {"document_id": "d2",
                                           "stream_id": "s1"}, config)
            result = ep.edits_call("edits.apply", {
                "document_id": "d2", "stream_id": "s1", "card_ids": ["c1"],
                "revision_author": "lvyin-edits",
                "revision_date": "2026-10-17T00:00:00Z"}, config)
            ids = result["cards"][0]["revision_ids"]
            self.assertTrue(all(int(value) > 901 for value in ids))
            working = Path(tmp) / "edits-protocol" / "d2" / "working.docx"
            scan = ep.scan_document(ep.load_docx_parts(working))
            prior = [rev for rev in scan["revisions"]
                     if rev["author"] == "prior-author"]
            self.assertEqual(len(prior), 2)
            self.assertEqual({rev["id"] for rev in prior}, {"900", "901"})

    def test_apply_params_validation(self):
        self.fx.feed(edits_stream(edit_card("c1", "replace",
                                            MIN_PARAGRAPHS[0], "新")))
        self.fx.call("edits.locate", {"document_id": "d1",
                                      "stream_id": "s1"})
        for bad in ({"revision_author": "", "revision_date":
                     "2026-10-17T00:00:00Z"},
                    {"revision_author": "a", "revision_date": "2026-10-17"},
                    {"revision_author": "a", "revision_date": None}):
            with self.subTest(bad=bad):
                with self.assertRaises(ep.EditsError) as ctx:
                    self.fx.call("edits.apply", {
                        "document_id": "d1", "stream_id": "s1",
                        "card_ids": ["c1"], **bad})
                self.assertIn("f48_revision_params_invalid",
                              str(ctx.exception))

    def test_stream_session_discipline(self):
        # 首次 open 成功；同 id 重复 open＝具名拒
        self.fx.call("edits.stream_open", {"document_id": "d1",
                                           "stream_id": "s1"})
        with self.assertRaises(ep.EditsError) as ctx:
            self.fx.call("edits.stream_open", {"document_id": "d1",
                                               "stream_id": "s1"})
        self.assertEqual(str(ctx.exception), "f48_stream_exists")
        with self.assertRaises(ep.EditsError) as ctx:
            self.fx.call("edits.stream_push", {"document_id": "d1",
                                               "stream_id": "nope",
                                               "chunk": "x"})
        self.assertEqual(str(ctx.exception), "f48_stream_not_found")
        # 关闭后不可再推
        self.fx.call("edits.stream_push", {"document_id": "d1",
                                           "stream_id": "s1",
                                           "chunk": "</edits>"})
        self.fx.call("edits.stream_close", {"document_id": "d1",
                                            "stream_id": "s1"})
        with self.assertRaises(ep.EditsError) as ctx:
            self.fx.call("edits.stream_push", {"document_id": "d1",
                                               "stream_id": "s1",
                                               "chunk": "x"})
        self.assertEqual(str(ctx.exception), "f48_stream_closed")
        # 未关闭的流不可 locate
        self.fx.call("edits.stream_open", {"document_id": "d1",
                                           "stream_id": "s2"})
        self.fx.call("edits.stream_push", {"document_id": "d1",
                                           "stream_id": "s2",
                                           "chunk": "<edits>"})
        with self.assertRaises(ep.EditsError) as ctx:
            self.fx.call("edits.locate", {"document_id": "d1",
                                          "stream_id": "s2"})
        self.assertIn("f48_stream_not_closed", str(ctx.exception))

    def test_failed_stream_never_yields_cards(self):
        """坏流（截断 close）：卡片账零行（失败面不污染），locate 具名拒。"""
        stream = edits_stream(edit_card("z1", "replace",
                                        MIN_PARAGRAPHS[0], "新"))
        self.fx.call("edits.stream_open", {"document_id": "d1",
                                           "stream_id": "sz"})
        self.fx.call("edits.stream_push", {"document_id": "d1",
                                           "stream_id": "sz",
                                           "chunk": stream[:-8]})
        closed = self.fx.call("edits.stream_close",
                              {"document_id": "d1", "stream_id": "sz"})
        self.assertEqual(closed["protocol_error"]["code"],
                         "f48_stream_truncated")
        cards = self.fx.call("edits.cards", {"document_id": "d1"})["cards"]
        self.assertEqual(cards, [])
        with self.assertRaises(ep.EditsError) as ctx:
            self.fx.call("edits.locate", {"document_id": "d1",
                                          "stream_id": "sz"})
        self.assertIn("f48_stream_invalid", str(ctx.exception))


# --------------------------------------------------------------------------
# 3. 桥层（legal_entry 冻结方法组＋fail-closed）
# --------------------------------------------------------------------------

class BridgeWiringTests(unittest.TestCase):

    CONFIG = {"edits_state_root": "X:/synth/edits-state-root"}

    def test_method_group_frozen(self):
        self.assertEqual(legal_entry.EDITS_METHODS, ep.EDITS_METHODS)
        for bogus in ("edits.bake", "edits.force_apply", "edits.set_state",
                      "edits.stream_reopen"):
            self.assertNotIn(bogus, legal_entry.EDITS_METHODS)

    def test_dispatch_reaches_module_surface(self):
        """桥路由：edits.cards 经 legal_entry.call 到模块面（参数原样）。"""
        with tempfile.TemporaryDirectory(prefix="juscite-f48-bridge-") as tmp:
            fx = F48Fixture.__new__(F48Fixture)
            fx.tmp = None
            fx.root = Path(tmp)
            fx.config = {"edits_state_root": str(tmp)}
            fx.docx = build_min_docx()
            fx.call("edits.register", {"document_id": "d1", "bytesB64":
                                       base64.b64encode(
                                           fx.docx).decode("ascii")})
            result = legal_entry.call("edits.cards", {"document_id": "d1"},
                                      self.CONFIG.__class__({
                                          "edits_state_root": str(tmp)}))
            self.assertEqual(result["cards"], [])

    def test_not_configured_fails_closed(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("edits.cards", {"document_id": "d1"}, {})
        self.assertIn("f48_state_root_missing", str(ctx.exception))

    def test_unknown_method_refused(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("edits.bake", {"document_id": "d1"},
                             self.CONFIG)
        self.assertIn("method_not_connected", str(ctx.exception))

    def test_typed_error_crosses_as_not_connected(self):
        with self.assertRaises(NotConnected) as ctx:
            legal_entry.call("edits.cards", {"document_id": "missing-doc"},
                             self.CONFIG)
        self.assertIn("edits_failed:f48_document_not_registered",
                      str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
