"""W2a-U02 / E12 wiring: 全量材料解析版本桥面（5000 页级清单、未读失败
低置信分母、跨页表阅读序、页号 bbox 版本、人改不覆、局部恢复）。

同进程闭环打 anonymizer material_parse_service 公开面（anonymizer 仓
w2a-u02 分支）。语料全合成（00-总协调 §6.1 裁决#1）：空白页/字节级重复页/
渲染表格页。桥面纪律与 P09/P10 基线一致：未配置 fail-closed；错误码永不
携带材料内容；语料只读（页字节 sha 复验）；分母信号闭集分别计数，不凭
文件存在已读；人改版本重扫不覆；process 重入不重不漏。
"""
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from legal_entry import call, NotConnected


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _white(w=992, h=1403) -> bytes:
    from PIL import Image
    return _png(Image.new("L", (w, h), 255))


def _table_page_png() -> bytes:
    """reportlab STSong → PDF → pypdfium2 栅格化：两行五列还款计划行。"""
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


class E12MaterialParseWiringTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp(prefix="juscite-e12-wiring-"))
        white = _white()
        table = _table_page_png()
        # 纯白页＋表格原件＋表格字节级复刻（复刻在源页之后，同语料契约）
        self.corpus = _write_corpus(self.tmp, [white, table, table])
        self.config = _config(self.tmp / "state")
        reg = call("material.parse_register",
                   {"corpus_root": str(self.corpus)}, self.config)
        self.batch_id = reg["batch_id"]
        self.assertEqual(reg["registered_pages"], 3)
        self.assertEqual(reg["documents"], 1)

    def test_register_is_idempotent_and_ignores_gold_fields(self):
        again = call("material.parse_register",
                     {"corpus_root": str(self.corpus)}, self.config)
        self.assertEqual(again["batch_id"], self.batch_id)
        batch_raw = (self.tmp / "state" / "material-parse" / self.batch_id
                     / "batch.json").read_text(encoding="utf-8")
        self.assertNotIn("expected_signal", batch_raw)
        self.assertNotIn("page_no_gold", batch_raw)
        self.assertNotIn('"tables"', batch_raw)

    def test_process_resume_and_closed_denominator(self):
        first = call("material.parse_process",
                     {"batch_id": self.batch_id,
                      "pages": [{"doc_id": "doc_0001", "page": 1}]},
                     self.config)
        self.assertEqual(first["processed"], 1)
        pending = call("material.parse_pending", {"batch_id": self.batch_id},
                       self.config)["pending"]
        self.assertEqual(len(pending), 2)          # 不凭文件存在已读
        second = call("material.parse_process", {"batch_id": self.batch_id},
                      self.config)
        self.assertEqual(second["processed"], 2)
        self.assertEqual(second["skipped_existing"], 1)   # 不重
        report = call("material.parse_report", {"batch_id": self.batch_id},
                      self.config)
        self.assertEqual(report["registered_pages"], 3)
        self.assertEqual(report["completed"] + report["pending"], 3)
        self.assertEqual(report["pending"], 0)     # 不漏
        self.assertEqual(report["corrupt_records"], 0)
        self.assertEqual(set(report["signals"]), {
            "READ_OK", "LOW_CONFIDENCE", "EMPTY_RECOGNITION",
            "UNREAD_FAILED", "BLANK", "DUPLICATE"})
        self.assertEqual(report["signals"]["BLANK"], 1)
        self.assertEqual(report["signals"]["DUPLICATE"], 1)

    def test_blank_and_duplicate_page_records(self):
        call("material.parse_process", {"batch_id": self.batch_id},
             self.config)
        blank = call("material.parse_page",
                     {"batch_id": self.batch_id, "doc_id": "doc_0001",
                      "page": 1}, self.config)
        self.assertEqual(blank["signal"], "BLANK")
        dup = call("material.parse_page",
                   {"batch_id": self.batch_id, "doc_id": "doc_0001",
                    "page": 3}, self.config)
        self.assertEqual(dup["signal"], "DUPLICATE")
        self.assertEqual(dup["duplicate_of"], {"doc_id": "doc_0001", "page": 2})

    def test_cross_page_table_reading_order_and_page_no_bbox(self):
        call("material.parse_process", {"batch_id": self.batch_id},
             self.config)
        page2 = call("material.parse_page",
                     {"batch_id": self.batch_id, "doc_id": "doc_0001",
                      "page": 2}, self.config)
        self.assertEqual(page2["signal"], "READ_OK")
        tables = call("material.parse_tables",
                      {"batch_id": self.batch_id, "doc_id": "doc_0001"},
                      self.config)
        self.assertEqual(len(tables["groups"]), 1)
        group = tables["groups"][0]
        self.assertEqual(group["columns"], 5)
        self.assertEqual(len(group["rows"]), 2)
        first = [c["text"] if c else None for c in group["rows"][0]["cells"]]
        self.assertEqual(first, ["1", "2026-02-05", "100.00", "20.00",
                                 "120.00"])
        order = [(r["page"], r["page_row_index"]) for r in group["rows"]]
        self.assertEqual(order, [(2, 0), (2, 1)])   # 阅读序=(页,页内行)

    def test_human_edit_survives_rescan(self):
        # 人改不覆：人工修订页号 → 重抽 → human 版本仍是当前版本
        call("material.parse_process", {"batch_id": self.batch_id},
             self.config)
        edit = call("material.parse_human_edit",
                    {"batch_id": self.batch_id, "doc_id": "doc_0001",
                     "page": 1, "page_no_text": "- 1 -"}, self.config)
        self.assertEqual(edit["source"], "human")
        rescan = call("material.parse_reparse",
                      {"batch_id": self.batch_id, "doc_id": "doc_0001",
                       "page": 1}, self.config)
        self.assertEqual(rescan["human_versions_kept"], 1)
        self.assertEqual(rescan["page_no_current_version"],
                         edit["version"])
        rec = call("material.parse_page",
                   {"batch_id": self.batch_id, "doc_id": "doc_0001",
                    "page": 1}, self.config)
        human = [v for v in rec["page_no"]["versions"]
                 if v["source"] == "human"]
        self.assertEqual(len(human), 1)
        self.assertEqual(human[0]["text"], "- 1 -")
        self.assertEqual(rec["page_no"]["current_version"], edit["version"])

    def test_page_no_bbox_versioned_with_bounds(self):
        call("material.parse_process", {"batch_id": self.batch_id},
             self.config)
        rec = call("material.parse_page",
                   {"batch_id": self.batch_id, "doc_id": "doc_0001",
                    "page": 2}, self.config)
        if rec["page_no"]["versions"]:             # 页号可提取时必带版本+bbox
            version = rec["page_no"]["versions"][0]
            self.assertEqual(version["version"], 1)
            self.assertEqual(version["source"], "engine")
            x0, y0, x1, y1 = version["bbox"]
            self.assertTrue(0 <= x0 < x1 <= rec["geom"]["w"])
            self.assertTrue(0 <= y0 < y1 <= rec["geom"]["h"])
        else:
            # 页号不可提取（覆印/零行）：诚实空版本链，绝不伪造
            self.assertEqual(rec["page_no"]["current_version"], None)

    def test_fail_closed_config_and_args(self):
        bad_configs = ({}, {"anonymizer_contract": "p09/p10"},
                       {"anonymizer_contract": "other"})
        for bad in bad_configs:
            with self.assertRaisesRegex(
                    NotConnected,
                    "anonymizer_p09_p10_not_configured|"
                    "material_parse_state_root_not_configured"):
                call("material.parse_report", {"batch_id": "mp-x"}, bad)
        with self.assertRaisesRegex(NotConnected,
                                    "material_parse_failed:"
                                    "parse_batch_not_registered"):
            call("material.parse_report", {"batch_id": "mp-none"},
                 self.config)
        with self.assertRaisesRegex(NotConnected,
                                    "material_parse_batch_id_required"):
            call("material.parse_report", {}, self.config)
        with self.assertRaisesRegex(NotConnected,
                                    "material_parse_corpus_root_required"):
            call("material.parse_register", {}, self.config)
        with self.assertRaisesRegex(
                NotConnected, "material_parse_params_invalid"):
            call("material.parse_report", "not-a-dict", self.config)

    def test_mutated_original_refused_not_reparsed(self):
        # 语料只读红线：页字节在登记后被改写 → UNREAD_FAILED，绝不解析
        target = self.corpus / "pages" / "doc_0001" / "p0001.png"
        target.write_bytes(_white(800, 600))
        out = call("material.parse_process", {"batch_id": self.batch_id},
                   self.config)
        self.assertEqual(out["signals"]["UNREAD_FAILED"], 1)
        rec = call("material.parse_page",
                   {"batch_id": self.batch_id, "doc_id": "doc_0001",
                    "page": 1}, self.config)
        self.assertEqual(rec["signal_detail"], "page_bytes_mismatch")

    def test_unknown_parse_method_stays_not_connected(self):
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected:"
                                    "material.parse_explode"):
            call("material.parse_explode", {}, self.config)


if __name__ == "__main__":
    unittest.main()
