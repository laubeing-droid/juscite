"""W2a-U16 / F41 OCR 批量工程桥面测试：冻结方法组、fail-closed 配置面、
批量生命周期（登记/跑批/取消/续跑/重抽/验签/密钥不外漏）经桥同进程闭环
（anonymizer 仓 w2a-u16 分支 ocr_batch_service 公开面）。

真引擎跑批由 tools/PENDING_OWNER_f41_batch_recon.py 承担；此处确定性组用
引擎测试缝（monkeypatch _spawn_batch_worker——产品路径恒走钉定解释器
F40 worker 子进程，缝只属测试），真引擎组单件单页（解释器不在机上=skip
如实）。全部材料合成。
"""
import hashlib
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))


def _resolve_anonymizer_src():
    env = os.environ.get("JUSCITE_ANONYMIZER_SRC")
    if env:
        return Path(env)
    # juscite worktree …/1.法律工作区/jusbench工作区/juscite/.local/…/w2a-u16
    # → 同波 anonymizer worktree …/1.法律工作区/legal-cn-anonymizer工作区/
    #   legal-cn-anonymizer/.local/worktrees/w4-u32/src（F40 recon 同式；
    #   W4-U32 同波钉定迁移 w2a-u16→w4-u32——链超集含 F41 全部面，
    #   且与 conftest 同波钉一致，消跨波缓存漂移）
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "jusbench工作区":
            guess = (parent.parent / "legal-cn-anonymizer工作区"
                     / "legal-cn-anonymizer" / ".local" / "worktrees"
                     / "w4-u32" / "src")
            if (guess / "legal_anonymizer" / "application"
                    / "ocr_batch_service.py").is_file():
                return guess
            break
    return None


_ANONYMIZER_SRC = _resolve_anonymizer_src()
if _ANONYMIZER_SRC is not None:
    sys.path.insert(0, str(_ANONYMIZER_SRC))
try:
    from legal_anonymizer.application import ocr_batch_service as _obs
except ImportError:
    # 全套跑时字母序更早的桥测试（如 W2a-U15 的 attachment 面文件）可能已把
    # 其他波次检出缓存进 sys.modules；逐出后按本文件的钉定路径重导入（保持
    # 本桥面测试对 w2a-u16 面封闭，W2a-U15 同式——主仓合并结果全套暴露的
    # 跨波缓存漂移，缺此段则 legal_entry 桥内延迟 import 踩他波缓存面）。
    import importlib
    _obs = None
    if _ANONYMIZER_SRC is not None:
        for _mod in [m for m in sys.modules if m == "legal_anonymizer"
                     or m.startswith("legal_anonymizer.")]:
            del sys.modules[_mod]
        try:
            _obs = importlib.import_module(
                "legal_anonymizer.application.ocr_batch_service")
        except ImportError:                            # pragma: no cover
            _obs = None

from legal_entry import call, NotConnected, OCR_BATCH_METHODS

_INTERP = Path(os.environ.get(
    "JUSCITE_F40_BASELINE_INTERPRETER",
    r"C:\Users\being\AppData\Local\pdf2md-venv\Scripts\python.exe"))
_INTERP_AVAILABLE = _INTERP.is_file()
_DOCS = {"wdoc_a": 2, "wdoc_b": 2, "wdoc_c": 1}


def _page_png(doc_id: str, page: int) -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("L", (992, 1403), 255)
    d = ImageDraw.Draw(img)
    d.text((100, 100 + page * 40), f"SYN-{doc_id}-p{page}", fill=20)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _write_corpus(root: Path) -> Path:
    corpus = root / "corpus"
    docs_meta = []
    for doc_id, n in _DOCS.items():
        (corpus / "pages" / doc_id).mkdir(parents=True)
        page_files = []
        for i in range(1, n + 1):
            payload = _page_png(doc_id, i)
            rel = f"pages/{doc_id}/p{i:04d}.png"
            (corpus / rel).write_bytes(payload)
            page_files.append({
                "page": i, "kind": "TEXT", "png": rel,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
                "expected_signal": "read_ok",    # 金标字段：必须结构性无视
            })
        docs_meta.append({"doc_id": doc_id, "doc_code": "SJ-F41W",
                          "page_count": n, "pdf": f"docs/{doc_id}.pdf",
                          "pdf_bytes": 1, "pdf_sha256": "0" * 64,
                          "page_files": page_files})
    (corpus / "corpus_manifest.json").write_text(
        json.dumps({"schema": "juscite-e12-corpus/1", "seed": 11,
                    "pages": 5, "documents": docs_meta},
                   ensure_ascii=False), encoding="utf-8")
    return corpus


def _fake_worker(interp, pages, workdir):
    result_pages = [{"page": p["page"],
                     "lines": [{"text": "synthetic-bridge",
                                "bbox": [10.0, 20.0, 300.0, 44.0],
                                "conf": 0.98}],
                     "error": None} for p in pages]
    return {"schema": "juscite-f40-baseline-worker/1", "ok": True,
            "engine": {"engine": "fake-test", "device": "gpu:0"},
            "pages": result_pages}, 4242


def _pin_and_refresh():
    """钉面并刷新本模块的 _obs 引用：引擎测试缝（monkeypatch _obs.
    _spawn_batch_worker）必须打在桥运行时实际命中的那个模块对象上。"""
    global _obs
    m = _pin_face()
    if m is not None:
        _obs = m


def _pin_face():
    """运行时钉定本波面（w2a-u16）。全套单进程内多波桥测试共存（U15
    attachment 面与 U16 batch 面基于 anonymizer 平行分支、互不含对方
    模块）；本文件测试类 setUpClass 重钉，保证桥内延迟 import 恒命中
    本波面（W2a-U16 合并时补）。"""
    sys.path.insert(0, str(_ANONYMIZER_SRC))  # 本波面提到 path 最前（他波后插入者会压前）
    if _ANONYMIZER_SRC is None:
        return None
    import importlib
    for m in [m for m in sys.modules if m == "legal_anonymizer"
              or m.startswith("legal_anonymizer.")]:
        del sys.modules[m]
    return importlib.import_module(
        "legal_anonymizer.application.ocr_batch_service")


class F41BridgeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pin_and_refresh()
    def test_frozen_method_group(self):
        self.assertEqual(OCR_BATCH_METHODS, frozenset({
            "ocr.batch_register", "ocr.batch_run", "ocr.batch_cancel",
            "ocr.batch_status", "ocr.batch_events", "ocr.batch_pending",
            "ocr.batch_redraw", "ocr.batch_report",
            "ocr.batch_verify_reports", "ocr.batch_doc_version",
            "ocr.batch_secret_exposure"}))

    def test_unknown_ocr_method_stays_not_connected(self):
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected:ocr.explode"):
            call("ocr.explode", {}, {"anonymizer_contract": "p09/p10"})

    def test_fail_closed_config_triangle(self):
        with self.assertRaisesRegex(NotConnected,
                                    "anonymizer_p09_p10_not_configured"):
            call("ocr.batch_status", {"batch_id": "f41-x"}, {})
        with self.assertRaisesRegex(NotConnected,
                                    "ocr_ports_state_root_not_configured"):
            call("ocr.batch_status", {"batch_id": "f41-x"},
                 {"anonymizer_contract": "p09/p10"})
        with self.assertRaisesRegex(
                NotConnected, "ocr_baseline_interpreter_not_configured"):
            call("ocr.batch_register",
                 {"corpus_root": "C:/nowhere"},
                 {"anonymizer_contract": "p09/p10",
                  "ocr_ports_state_root": "C:/nowhere-state"})

    def test_params_validation(self):
        cfg = {"anonymizer_contract": "p09/p10",
               "ocr_ports_state_root": "C:/nowhere-state",
               "ocr_baseline_interpreter": "C:/nowhere-python.exe"}
        with self.assertRaisesRegex(NotConnected,
                                    "ocr_batch_id_required"):
            call("ocr.batch_status", {}, cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "ocr_batch_corpus_root_required"):
            call("ocr.batch_register", {}, cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "ocr_batch_doc_id_required"):
            call("ocr.batch_redraw", {"batch_id": "f41-x"}, cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "ocr_batch_after_seq_invalid"):
            call("ocr.batch_events",
                 {"batch_id": "f41-x", "after_seq": -1}, cfg)


@unittest.skipIf(_obs is None,
                 "anonymizer w2a-u16 源不可得（JUSCITE_ANONYMIZER_SRC 未配且"
                 " 同波 worktree 不在盘）")
class F41BridgeLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pin_and_refresh()
    """经桥全生命周期（引擎测试缝）：进度事件/取消/续跑/重抽/验签。"""

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="f41-bridge-"))
        self.corpus = _write_corpus(self._tmp)
        self.config = {
            "anonymizer_contract": "p09/p10",
            "ocr_ports_state_root": str(self._tmp / "state"),
            "ocr_baseline_interpreter": sys.executable,
        }
        self._real_spawn = _obs._spawn_batch_worker
        _obs._spawn_batch_worker = _fake_worker

    def tearDown(self):
        _obs._spawn_batch_worker = self._real_spawn
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_register_reports_limits_and_whitelist(self):
        reg = call("ocr.batch_register",
                   {"corpus_root": str(self.corpus), "min_doc_gap_s": 0.1},
                   self.config)
        self.assertTrue(reg["batch_id"].startswith("f41-"))
        self.assertEqual(reg["limits"]["max_concurrency"], 1)
        self.assertEqual(reg["counters"]["docs_pending"], 3)
        self.assertEqual(call("ocr.batch_pending",
                              {"batch_id": reg["batch_id"]},
                              self.config)["pending"], list(_DOCS))
        batch_raw = (Path(self.config["ocr_ports_state_root"])
                     / "f41-batch" / reg["batch_id"]
                     / "batch.json").read_text(encoding="utf-8")
        self.assertNotIn("expected_signal", batch_raw)

    def test_run_events_progress_and_reconcile(self):
        reg = call("ocr.batch_register", {"corpus_root": str(self.corpus)},
                   self.config)
        out = call("ocr.batch_run", {"batch_id": reg["batch_id"]},
                   self.config)
        self.assertEqual(out["status"], "COMPLETED")
        events = call("ocr.batch_events", {"batch_id": reg["batch_id"]},
                      self.config)
        seqs = [e["seq"] for e in events["events"]]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
        done = [e["counters"]["docs_done"] for e in events["events"]]
        self.assertEqual(done, sorted(done))
        status = call("ocr.batch_status", {"batch_id": reg["batch_id"]},
                      self.config)
        self.assertEqual(status["counters"]["docs_done"], 3)

    def test_cancel_resume_redraw_and_signatures(self):
        reg = call("ocr.batch_register", {"corpus_root": str(self.corpus)},
                   self.config)
        holder = {}
        th = threading.Thread(target=lambda: holder.__setitem__(
            "run", call("ocr.batch_run", {"batch_id": reg["batch_id"]},
                        self.config)))
        th.start()
        deadline = time.time() + 30
        while time.time() < deadline:
            evs = call("ocr.batch_events", {"batch_id": reg["batch_id"]},
                       self.config)["events"]
            if any(e["type"] == "doc_completed" for e in evs):
                call("ocr.batch_cancel", {"batch_id": reg["batch_id"]},
                     self.config)
                break
            time.sleep(0.01)
        th.join()
        self.assertEqual(holder["run"]["status"], "CANCELLED")
        resume = call("ocr.batch_run", {"batch_id": reg["batch_id"]},
                      self.config)
        self.assertEqual(resume["status"], "COMPLETED")
        redraw = call("ocr.batch_redraw",
                      {"batch_id": reg["batch_id"], "doc_id": "wdoc_b"},
                      self.config)
        self.assertEqual(redraw["version"], 2)
        old = call("ocr.batch_doc_version",
                   {"batch_id": reg["batch_id"], "doc_id": "wdoc_b",
                    "version": 1}, self.config)
        self.assertFalse(old["is_current"])
        verify = call("ocr.batch_verify_reports",
                      {"batch_id": reg["batch_id"]}, self.config)
        self.assertTrue(verify["all_valid"])
        rows = {r["report_seq"]: r for r in verify["reports"]}
        self.assertTrue(rows[1]["expired"] and rows[1]["valid"])
        exposure = call("ocr.batch_secret_exposure",
                        {"batch_id": reg["batch_id"]}, self.config)
        self.assertFalse(exposure["exposed"])

    def test_typed_error_surfaces_as_code(self):
        reg = call("ocr.batch_register", {"corpus_root": str(self.corpus)},
                   self.config)
        with self.assertRaisesRegex(NotConnected,
                                    "ocr_batch_cancel_not_running"):
            call("ocr.batch_cancel", {"batch_id": reg["batch_id"]},
                 self.config)


@unittest.skipUnless(_INTERP_AVAILABLE and _obs is not None,
                     "钉定解释器不在机上（真引擎组如实 skip）")
class F41BridgeRealEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pin_and_refresh()
    def test_real_engine_register_and_single_doc_run(self):
        tmp = Path(tempfile.mkdtemp(prefix="f41-bridge-real-"))
        corpus = tmp / "corpus"
        (corpus / "pages" / "doc_0001").mkdir(parents=True)
        payload = _page_png("doc_0001", 1)
        rel = "pages/doc_0001/p0001.png"
        (corpus / rel).write_bytes(payload)
        (corpus / "corpus_manifest.json").write_text(json.dumps({
            "schema": "juscite-e12-corpus/1", "seed": 11, "pages": 1,
            "documents": [{"doc_id": "doc_0001", "doc_code": "SJ-F41W",
                           "page_count": 1, "pdf": "docs/doc_0001.pdf",
                           "pdf_bytes": 1, "pdf_sha256": "0" * 64,
                           "page_files": [{"page": 1, "kind": "TEXT",
                                           "png": rel, "sha256": hashlib.sha256(
                                               payload).hexdigest(),
                                           "bytes": len(payload)}]}]},
            ensure_ascii=False), encoding="utf-8")
        config = {"anonymizer_contract": "p09/p10",
                  "ocr_ports_state_root": str(tmp / "state"),
                  "ocr_baseline_interpreter": str(_INTERP)}
        try:
            reg = call("ocr.batch_register",
                       {"corpus_root": str(corpus)}, config)
            out = call("ocr.batch_run", {"batch_id": reg["batch_id"]}, config)
            self.assertEqual(out["status"], "COMPLETED")
            doc = call("ocr.batch_doc_version",
                       {"batch_id": reg["batch_id"], "doc_id": "doc_0001"},
                       config)
            self.assertEqual((doc["doc"]["engine"] or {}).get("engine"),
                             "paddleocr")
            self.assertEqual(doc["doc"]["pages_ok"], 1)
            self.assertTrue(call("ocr.batch_verify_reports",
                                 {"batch_id": reg["batch_id"]},
                                 config)["all_valid"])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
