"""W2a-U07 / F86 wiring: 前后端阅读序同源规范面（reading.document /
reading.hits 桥方法组 → reading_order 规范文档）。

同源断言：规范阅读序文档只读 material.parse_* 解析产物（同一来源），
表格行序与 material.parse_tables 组装阅读序逐行一致；前端阅读面（patch
013）消费同一文档不再自行推导。高亮三类＝page_segment/table/ocr（引用
命中属 E14/W2b 不在本面）。静默失败预防针：命中解析不到=typed error，
批次未处理完拒出文档。语料全合成（00-总协调 §6.1 裁决#1）。
"""
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from legal_entry import call, NotConnected  # noqa: E402
from reading_order import (  # noqa: E402
    ReadingOrderError, document as face_document, hits as face_hits,
    order_hash)


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _white(w=992, h=1403) -> bytes:
    from PIL import Image
    return _png(Image.new("L", (w, h), 255))


def _table_page_png(page_no: int) -> bytes:
    """reportlab STSong → PDF → pypdfium2 栅格化：两行五列还款表＋页脚页号。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas as rl_canvas
    import pypdfium2 as pdfium

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setFont("STSong-Light", 18)
    rows = [("1", "2026-02-05", "100.00", "20.00", "120.00"),
            ("2", "2026-03-05", "100.00", "18.00", "118.00")]
    for ri, row in enumerate(rows):
        for ci, text in enumerate(row):
            c.drawString(80 + ci * 105, A4[1] - 200 - ri * 60, text)
    c.setFont("STSong-Light", 14)
    c.drawCentredString(A4[0] / 2, 40, f"- {page_no} -")   # 页脚页号
    c.showPage()
    c.save()
    buf.seek(0)
    pdf = pdfium.PdfDocument(buf)
    image = pdf[0].render(scale=992 / A4[0]).to_pil().convert("L")
    pdf.close()
    return _png(image)


def _write_corpus(root: Path, pages: list[bytes]) -> Path:
    corpus = root / "corpus"
    (corpus / "pages" / "doc_0001").mkdir(parents=True)
    page_files = []
    for i, payload in enumerate(pages):
        rel = f"pages/doc_0001/p{i + 1:04d}.png"
        (corpus / rel).write_bytes(payload)
        page_files.append({
            "page": i + 1, "kind": "TEXT", "png": rel,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "expected_signal": "read_ok",       # 金标字段：桥/服务必须无视
        })
    manifest = {"schema": "juscite-e12-corpus/1", "seed": 7,
                "pages": len(pages),
                "documents": [{
                    "doc_id": "doc_0001", "doc_code": "SJ-0001",
                    "page_count": len(pages), "pdf": "docs/doc_0001.pdf",
                    "pdf_bytes": 1, "pdf_sha256": "0" * 64,
                    "tables": [], "page_files": page_files}]}
    (corpus / "corpus_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return corpus


def _config(state_root):
    return {"anonymizer_contract": "p09/p10",
            "material_parse_state_root": str(state_root)}


class F86ReadingOrderWiringTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from PIL import Image
        self.tmp = Path(tempfile.mkdtemp(prefix="juscite-f86-wiring-"))
        white = _white()
        table = _table_page_png(2)
        # 纯白页＋表格页（带页脚页号）＋表格字节级复刻（复刻在源页之后）
        self.corpus = _write_corpus(self.tmp, [white, table, table])
        self.state = self.tmp / "state"
        self.config = _config(self.state)
        reg = call("material.parse_register",
                   {"corpus_root": str(self.corpus)}, self.config)
        self.batch_id = reg["batch_id"]
        call("material.parse_process", {"batch_id": self.batch_id},
             self.config)

    def _document(self):
        return call("reading.document", {"batch_id": self.batch_id},
                    self.config)

    def test_canonical_order_and_kinds(self):
        doc = self._document()
        self.assertEqual(doc["schema"], "juscite-f86-reading-order/1")
        self.assertEqual(doc["source_face"], "material.parse_*")
        self.assertEqual(doc["docs"], ["doc_0001"])
        kinds = [i["kind"] for i in doc["items"]]
        # 页2：seg → row0 → row1 → ocr（页内序：段/表行(页内行序)/页脚OCR）
        self.assertEqual(
            kinds,
            ["page_segment",                       # p1 纯白
             "page_segment", "table_row", "table_row", "ocr_hit",  # p2
             "page_segment"])                      # p3 复刻
        self.assertEqual([i["order_index"] for i in doc["items"]],
                         list(range(len(doc["items"]))))
        seg3 = doc["items"][5]
        self.assertEqual(seg3["signal"], "DUPLICATE")
        self.assertEqual(seg3["duplicate_of"], {"doc_id": "doc_0001",
                                                "page": 2})
        self.assertEqual(doc["counts"]["page_segments"], 3)
        self.assertEqual(doc["counts"]["table_rows"], 2)
        self.assertEqual(doc["counts"]["ocr_hits"], 1)

    def test_same_source_table_rows_match_parse_tables(self):
        # 同源硬断言：规范文档表格行序 == material.parse_tables 组装阅读序
        doc = self._document()
        assembled = call("material.parse_tables",
                         {"batch_id": self.batch_id, "doc_id": "doc_0001"},
                         self.config)
        gold = [(g["group_index"], r["page"], r["page_row_index"])
                for g in assembled["groups"] for r in g["rows"]]
        got = [(i["group"], i["page"], i["row"]) for i in doc["items"]
               if i["kind"] == "table_row"]
        self.assertEqual(got, gold)
        # 单元格文本/bbox 逐格同源
        rows_gold = [r for g in assembled["groups"] for r in g["rows"]]
        rows_doc = [i for i in doc["items"] if i["kind"] == "table_row"]
        for rg, rd in zip(rows_gold, rows_doc):
            texts_gold = [c["text"] if c else None for c in rg["cells"]]
            texts_doc = [c["text"] if c else None for c in rd["cells"]]
            self.assertEqual(texts_doc, texts_gold)
            bboxes = [c["bbox"] for c in rd["cells"] if c]
            for x0, y0, x1, y1 in bboxes:
                self.assertTrue(0 <= x0 < x1 and 0 <= y0 < y1)

    def test_deterministic_order_hash(self):
        first = self._document()
        second = face_document(self.state, self.batch_id)
        self.assertEqual(first["order_hash"], second["order_hash"])
        self.assertEqual(
            first["order_hash"],
            order_hash([i["id"] for i in second["items"]]))

    def test_hits_three_kinds(self):
        doc = self._document()
        # ① 页段命中
        seg = call("reading.hits",
                   {"batch_id": self.batch_id, "kind": "page_segment",
                    "selector": {"doc_id": "doc_0001", "page": 1}},
                   self.config)
        self.assertEqual(seg["kind"], "page_segment")
        self.assertEqual(seg["hits"][0]["signal"], "BLANK")
        # ② 表格命中（组）＋组内行
        table = call("reading.hits",
                     {"batch_id": self.batch_id, "kind": "table",
                      "selector": {"doc_id": "doc_0001", "group": 0}},
                     self.config)
        self.assertEqual(len(table["hits"]), 2)
        row = call("reading.hits",
                   {"batch_id": self.batch_id, "kind": "table",
                    "selector": {"doc_id": "doc_0001", "group": 0,
                                 "row": 1}},
                   self.config)
        self.assertEqual(len(row["hits"]), 1)
        self.assertEqual(row["hits"][0]["row"], 1)
        self.assertTrue(any(c for c in row["hits"][0]["cells"]))
        # ③ 扫描 OCR 命中（页号）：文本/bbox/置信与规范文档同源
        ocr = call("reading.hits",
                   {"batch_id": self.batch_id, "kind": "ocr",
                    "selector": {"doc_id": "doc_0001", "page": 2}},
                   self.config)
        self.assertEqual(ocr["kind"], "ocr")
        hit = ocr["hits"][0]
        self.assertEqual(hit["source"], "engine")
        # OCR 原样文本（空格可能被吞）；归一化后必是页号 2
        self.assertEqual(hit["text"].replace(" ", ""), "-2-")
        gold = next(i for i in doc["items"] if i["id"] == "ocr:doc_0001:2")
        self.assertEqual(hit["bbox"], gold["bbox"])
        x0, y0, x1, y1 = hit["bbox"]
        seg2 = next(i for i in doc["items"]
                    if i["id"] == "seg:doc_0001:2")
        self.assertTrue(0 <= x0 < x1 <= seg2["geom"]["w"])
        self.assertTrue(0 <= y0 < y1 <= seg2["geom"]["h"])

    def test_ocr_hit_tracks_human_current_version(self):
        # 人改页号 → ocr 命中切到 human 当前版本（人改不覆同源投影）
        call("material.parse_human_edit",
             {"batch_id": self.batch_id, "doc_id": "doc_0001", "page": 2,
              "page_no_text": "- 2 -"}, self.config)
        ocr = call("reading.hits",
                   {"batch_id": self.batch_id, "kind": "ocr",
                    "selector": {"doc_id": "doc_0001", "page": 2}},
                   self.config)
        self.assertEqual(ocr["hits"][0]["source"], "human")
        doc = self._document()
        gold = next(i for i in doc["items"] if i["id"] == "ocr:doc_0001:2")
        self.assertEqual(gold["source"], "human")

    def test_fail_loud_not_silent(self):
        # 静默失败预防针：解析不到=typed error，绝不返回空命中
        cases = [
            ("page_segment", {"doc_id": "doc_0001", "page": 99},
             "reading_order_failed:f86_selector_not_found:page_segment"),
            ("table", {"doc_id": "doc_0001", "group": 9},
             "reading_order_failed:f86_selector_not_found:table"),
            ("table", {"doc_id": "doc_0001", "group": 0, "row": 9},
             "reading_order_failed:f86_selector_not_found:table_row"),
            ("ocr", {"doc_id": "doc_0001", "page": 1},   # 纯白页无页号
             "reading_order_failed:f86_selector_not_found:ocr_hit"),
            ("ocr", {"doc_id": "doc_0001", "page": 3},   # 复刻页短路无 OCR
             "reading_order_failed:f86_selector_not_found:ocr_hit"),
            ("citation", {"doc_id": "doc_0001"},
             "reading_order_failed:f86_kind_invalid"),
            ("table", {"doc_id": "doc_0001"},
             "reading_order_failed:f86_selector_invalid:group"),
        ]
        for kind, selector, code in cases:
            with self.assertRaisesRegex(NotConnected, code):
                call("reading.hits",
                     {"batch_id": self.batch_id, "kind": kind,
                      "selector": selector}, self.config)
        # 不经桥直调规范面：typed error 原样（码不携内容）
        with self.assertRaisesRegex(ReadingOrderError,
                                    "f86_selector_not_found"):
            face_hits(self.state, self.batch_id, "table",
                      {"doc_id": "doc_0001", "group": 9})

    def test_incomplete_batch_refuses_document(self):
        import tempfile
        other = Path(tempfile.mkdtemp(prefix="juscite-f86-pending-"))
        # 两张不同页（页号不同→字节不同，非复刻）；只处理第 1 页
        corpus = _write_corpus(other, [_table_page_png(1), _table_page_png(2)])
        config = _config(other / "state")
        reg = call("material.parse_register",
                   {"corpus_root": str(corpus)}, config)
        call("material.parse_process",
             {"batch_id": reg["batch_id"],
              "pages": [{"doc_id": "doc_0001", "page": 1}]}, config)
        with self.assertRaisesRegex(
                ReadingOrderError, "f86_batch_incomplete"):
            face_document(other / "state", reg["batch_id"])
        with self.assertRaisesRegex(
                NotConnected, "reading_order_failed:f86_batch_incomplete"):
            call("reading.document", {"batch_id": reg["batch_id"]}, config)

    def test_bridge_fail_closed(self):
        for bad in ({}, {"anonymizer_contract": "p09/p10"},
                    {"anonymizer_contract": "other"}):
            with self.assertRaisesRegex(NotConnected, "reading_order_failed:"
                                        "f86_state_root_not_configured|"
                                        "anonymizer_p09_p10_not_configured"):
                call("reading.document", {"batch_id": "mp-x"}, bad)
        with self.assertRaisesRegex(NotConnected,
                                    "reading_order_failed:"
                                    "f86_batch_id_required"):
            call("reading.document", {}, self.config)
        with self.assertRaisesRegex(
                NotConnected, "method_not_connected:reading.explode"):
            call("reading.explode", {"batch_id": self.batch_id},
                 self.config)
        with self.assertRaisesRegex(NotConnected,
                                    "reading_order_params_invalid"):
            call("reading.document", "not-a-dict", self.config)
        with self.assertRaisesRegex(
                NotConnected,
                "reading_order_failed:f86_parse_face:"
                "parse_batch_not_registered"):
            call("reading.document", {"batch_id": "mp-none"}, self.config)


if __name__ == "__main__":
    unittest.main()
