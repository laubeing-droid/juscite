"""W2a-U03 / F40 OCR 级联四端口桥面测试：冻结方法组、fail-closed 配置面、
端口具名报告与基础线登记/拒跑经桥同进程闭环（anonymizer 仓 w2a-u03 分支
ocr_ports_service 公开面）。

真引擎跑批（页块/表格金标）由 tools/PENDING_OWNER_f40_ocr_ports_recon.py
承担；此处引擎无关面为主，仅端口报告用真实钉定解释器（不在机上=skip 如实）。
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))

_SRC = os.environ.get("JUSCITE_ANONYMIZER_SRC")
if _SRC:
    sys.path.insert(0, _SRC)
try:
    from legal_anonymizer.application import ocr_ports_service as _ops
except ImportError:                                    # pragma: no cover
    _ops = None

from legal_entry import call, NotConnected, OCR_PORTS_METHODS

_INTERP = Path(os.environ.get(
    "JUSCITE_F40_BASELINE_INTERPRETER",
    r"C:\Users\being\AppData\Local\pdf2md-venv\Scripts\python.exe"))
_INTERP_AVAILABLE = _INTERP.is_file()


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _white(w: int = 992, h: int = 1403) -> bytes:
    from PIL import Image

    return _png(Image.new("L", (w, h), 255))


def _write_corpus(root: Path) -> Path:
    corpus = root / "corpus"
    (corpus / "pages" / "doc_0001").mkdir(parents=True)
    payload = _white()
    rel = "pages/doc_0001/p0001.png"
    (corpus / rel).write_bytes(payload)
    manifest = {"schema": "juscite-e12-corpus/1", "seed": 3, "pages": 1,
                "documents": [{
                    "doc_id": "doc_0001", "doc_code": "SJ-F40", "page_count": 1,
                    "pdf": "docs/doc_0001.pdf", "pdf_bytes": 1,
                    "pdf_sha256": "0" * 64, "tables": [],
                    "page_files": [{
                        "page": 1, "kind": "TEXT", "png": rel,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "bytes": len(payload),
                        "expected_signal": "read_ok",   # 金标字段：必须无视
                    }]}]}
    (corpus / "corpus_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return corpus


class F40BridgeContractTests(unittest.TestCase):
    def test_frozen_method_group(self):
        self.assertEqual(OCR_PORTS_METHODS, frozenset({
            "ocr.ports", "ocr.baseline_register", "ocr.baseline_run",
            "ocr.baseline_pending", "ocr.baseline_report",
            "ocr.baseline_tables", "ocr.baseline_page"}))

    def test_unknown_ocr_method_stays_not_connected(self):
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected:ocr.explode"):
            call("ocr.explode", {}, {"anonymizer_contract": "p09/p10"})

    def test_fail_closed_config(self):
        for config in ({}, {"anonymizer_contract": "p09/p10"}):
            with self.assertRaisesRegex(
                    NotConnected,
                    "anonymizer_p09_p10_not_configured|"
                    "ocr_ports_state_root_not_configured"):
                call("ocr.baseline_report", {"run_id": "f40-x"}, config)
        with self.assertRaisesRegex(NotConnected,
                                    "ocr_baseline_interpreter_not_configured"):
            call("ocr.baseline_register", {"corpus_root": "."},
                 {"anonymizer_contract": "p09/p10",
                  "ocr_ports_state_root": "x"})
        with self.assertRaisesRegex(NotConnected,
                                    "ocr_ports_run_id_required"):
            call("ocr.baseline_report", {},
                 {"anonymizer_contract": "p09/p10",
                  "ocr_ports_state_root": "x",
                  "ocr_baseline_interpreter": str(sys.executable)})
        with self.assertRaisesRegex(NotConnected,
                                    "ocr_ports_params_invalid"):
            call("ocr.ports", "not-a-dict",
                 {"anonymizer_contract": "p09/p10"})


@unittest.skipIf(_ops is None,
                 "anonymizer ocr_ports_service 不可导入（JUSCITE_ANONYMIZER_SRC "
                 "未指向 w2a-u03 树），dispatch 面跳过不伪造")
class F40BridgeDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="juscite-f40-wiring-"))
        self.corpus = _write_corpus(self.tmp)
        self.config = {"anonymizer_contract": "p09/p10",
                       "ocr_ports_state_root": str(self.tmp / "state"),
                       "ocr_baseline_interpreter": str(sys.executable)}

    def test_register_and_gold_blindness_via_bridge(self):
        reg = call("ocr.baseline_register",
                   {"corpus_root": str(self.corpus)}, self.config)
        self.assertTrue(reg["run_id"].startswith("f40-"))
        self.assertEqual(reg["registered_pages"], 1)
        raw = (self.tmp / "state" / "f40-baseline" / reg["run_id"]
               / "run.json").read_text(encoding="utf-8")
        self.assertNotIn("expected_signal", raw)
        pending = call("ocr.baseline_pending", {"run_id": reg["run_id"]},
                       self.config)["pending"]
        self.assertEqual(len(pending), 1)

    def test_mutated_original_refused_via_bridge(self):
        # 语料只读红线经桥面：登记后改写页字节 → 拒跑（fail-closed），无引擎
        reg = call("ocr.baseline_register",
                   {"corpus_root": str(self.corpus)}, self.config)
        (self.corpus / "pages" / "doc_0001" / "p0001.png").write_bytes(
            _white(800, 600))
        out = call("ocr.baseline_run", {"run_id": reg["run_id"]}, self.config)
        self.assertEqual(out["processed"], 0)
        self.assertEqual(out["failed"], 1)
        rec = call("ocr.baseline_page",
                   {"run_id": reg["run_id"], "doc_id": "doc_0001",
                    "page": 1}, self.config)
        self.assertEqual(rec["error"], "page_bytes_mismatch")
        self.assertIsNone(rec["lines"])

    def test_service_error_surfaces_typed_code(self):
        with self.assertRaisesRegex(NotConnected,
                                    "ocr_ports_failed:ocr_run_not_registered"):
            call("ocr.baseline_report", {"run_id": "f40-none"},
                 self.config)


@unittest.skipUnless(_ops is not None and _INTERP_AVAILABLE,
                     "钉定解释器或 anonymizer w2a-u03 面不在机上，真探针跳过")
class F40BridgePortsReportRealTests(unittest.TestCase):
    def test_ports_report_via_bridge_named_and_honest(self):
        report = call("ocr.ports", {"interpreter": str(_INTERP)},
                      {"anonymizer_contract": "p09/p10"})
        self.assertEqual([p["port_id"] for p in report["ports"]],
                         ["paddleocr-baseline", "mineru", "paddle-vl",
                          "pp-ocrv6", "minicpm-v"])
        self.assertEqual(report["ports"][0]["install_status"], "INSTALLED")
        for port in report["ports"][1:]:
            self.assertEqual(port["install_status"], "NOT_INSTALLED")
        self.assertEqual(report["cascade_effective"], ["paddleocr-baseline"])


@unittest.skipIf(_ops is None,
                 "anonymizer ocr_ports_service 不可导入（JUSCITE_ANONYMIZER_SRC "
                 "未指向源树），dispatch 面跳过不伪造")
class F39IsolationPassThroughTests(unittest.TestCase):
    """W2a-U18：args["isolation"] 经桥透传至 ops.baseline_run；未传=None
    ＝既有调用面不变（闭集校验在 anonymizer 服务侧 typed fail-closed）。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="juscite-f39-wiring-"))
        self.config = {"anonymizer_contract": "p09/p10",
                       "ocr_ports_state_root": str(self.tmp / "state"),
                       "ocr_baseline_interpreter": str(sys.executable)}

    def test_isolation_forwarded_and_default_none(self):
        # 全套跑时字母序更早的测试可能已 del sys.modules 重导出其他实例——
        # 打桩必须打在 legal_entry 调用时实际可见的 sys.modules 条目上
        # （文件顶层 _ops 绑定于收集期，二者可不同一）。
        import importlib
        import sys
        mod = sys.modules.get(
            "legal_anonymizer.application.ocr_ports_service")
        if mod is None:
            mod = importlib.import_module(
                "legal_anonymizer.application.ocr_ports_service")
        seen = {}

        def _spy(state_root, run_id, pages=None, interpreter=None,
                 isolation=None):
            seen["isolation"] = isolation
            return {"run_id": run_id, "sent_pages": 0, "processed": 0,
                    "skipped_existing": 0, "failed": 0,
                    "worker_token_face": None}

        real = mod.baseline_run
        mod.baseline_run = _spy
        try:
            call("ocr.baseline_run",
                 {"run_id": "f40-x", "isolation": "restricted_token"},
                 self.config)
            self.assertEqual(seen["isolation"], "restricted_token")
            call("ocr.baseline_run", {"run_id": "f40-x"}, self.config)
            self.assertIsNone(seen["isolation"])
        finally:
            mod.baseline_run = real


if __name__ == "__main__":
    unittest.main()
