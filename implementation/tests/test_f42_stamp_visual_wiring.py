"""W4-U35 / F42 印章/PS 疑似视觉检测桥面测试：冻结方法组、fail-closed
配置面、登记/探针跑/原图只读回读/结论词闭集经桥同进程闭环（anonymizer
仓 w4-u21 分支 stamp_visual_service 公开面，W4-U21 交付）。

真引擎跑批由 tools/PENDING_OWNER_f42_seal_detection_recon.py 承担；此处
确定性组用引擎测试缝（monkeypatch svs._spawn_worker——产品路径恒走钉定
解释器下 worker 子进程，GPU fail-closed/模型 sha256 钉定在 worker 内强制，
缝只属测试），真引擎组单页（解释器不在机上=skip 如实）。全部材料合成。
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


def _resolve_anonymizer_src():
    env = os.environ.get("JUSCITE_ANONYMIZER_SRC")
    if env:
        return Path(env)
    # juscite worktree …/1.法律工作区/jusbench工作区/juscite/.local/…
    # → 同波 anonymizer worktree …/1.法律工作区/legal-cn-anonymizer工作区/
    #   legal-cn-anonymizer/.local/worktrees/w4-u21/src（F41 recon 同式）
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "jusbench工作区":
            guess = (parent.parent / "legal-cn-anonymizer工作区"
                     / "legal-cn-anonymizer" / ".local" / "worktrees"
                     / "w4-u21" / "src")
            if (guess / "legal_anonymizer" / "application"
                    / "stamp_visual_service.py").is_file():
                return guess
            break
    return None


_ANONYMIZER_SRC = _resolve_anonymizer_src()
if _ANONYMIZER_SRC is not None:
    sys.path.insert(0, str(_ANONYMIZER_SRC))
try:
    from legal_anonymizer.application import stamp_visual_service as _svs
except ImportError:
    # 全套跑时字母序更早的桥测试可能已把其他波次检出缓存进 sys.modules；
    # 逐出后按本文件的钉定路径重导入（F41 同式——保持本桥面测试对 w4-u21
    # 面封闭，缺此段则 legal_entry 桥内延迟 import 踩他波缓存面）。
    import importlib
    _svs = None
    if _ANONYMIZER_SRC is not None:
        for _mod in [m for m in sys.modules if m == "legal_anonymizer"
                     or m.startswith("legal_anonymizer.")]:
            del sys.modules[_mod]
        try:
            _svs = importlib.import_module(
                "legal_anonymizer.application.stamp_visual_service")
        except ImportError:                            # pragma: no cover
            _svs = None

from legal_entry import call, NotConnected, STAMP_METHODS

_INTERP = Path(os.environ.get(
    "JUSCITE_F40_BASELINE_INTERPRETER",
    r"C:\Users\being\AppData\Local\pdf2md-venv\Scripts\python.exe"))
_INTERP_AVAILABLE = _INTERP.is_file()
PAGE_W, PAGE_H = 1240, 1754
RED = (185, 30, 35)
GOLD = {"kind": "seal", "cx": 920, "cy": 330, "box": [770, 180, 1070, 480]}


def _seal_png() -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (PAGE_W, PAGE_H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for line in range(6):
        d.text((90, 120 + line * 42), f"SYN-line{line:02d}",
               fill=(25, 25, 25))
    d.ellipse([770, 180, 1070, 480], outline=RED, width=10)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _clean_png() -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (PAGE_W, PAGE_H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((90, 120), "SYN-clean-page", fill=(25, 25, 25))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _write_corpus(root: Path) -> Path:
    """两页合成语料：p1 章页（金标盒）＋p2 净页。金标字段（gold_boxes）
    入清单但服务面白名单结构性不读。"""
    corpus = root / "corpus"
    docs = []
    for doc_id, page_files in (
            ("doc_a", [(_seal_png(), GOLD)]),
            ("doc_b", [(_clean_png(), None)])):
        (corpus / "pages" / doc_id).mkdir(parents=True)
        pfs = []
        for i, (payload, gold) in enumerate(page_files, start=1):
            rel = f"pages/{doc_id}/p{i:04d}.png"
            (corpus / rel).write_bytes(payload)
            pf = {"page": i, "kind": "TEXT", "png": rel,
                  "sha256": hashlib.sha256(payload).hexdigest(),
                  "bytes": len(payload)}
            if gold:
                pf["gold_boxes"] = [gold]     # 金标：结构性不入账
            pfs.append(pf)
        docs.append({"doc_id": doc_id, "doc_code": "SJ-F42W",
                     "page_count": len(pfs), "page_files": pfs})
    (corpus / "corpus_manifest.json").write_text(
        json.dumps({"schema": "juscite-f42-stamp-gold/1", "seed": 7,
                    "documents": docs}, ensure_ascii=False),
        encoding="utf-8")
    return corpus


def _fake_worker_payload(pages, suspected_pages: set):
    out = []
    for p in pages:
        if (p.get("doc_id"), int(p["page"])) in suspected_pages:
            out.append({
                "page": int(p["page"]), "geom": {"w": PAGE_W, "h": PAGE_H},
                "verdict": "suspected",
                "regions": [{"bbox": [770, 180, 1070, 480], "area_px": 9000,
                             "fill_ratio": 0.1, "circularity": 0.95,
                             "hole_fraction": 0.8, "red_intensity": 0.83,
                             "aspect": 1.0, "conf": 0.9,
                             "text_hints": [{"text": "SYN-SEAL",
                                             "bbox": [900.0, 320.0, 940.0,
                                                      342.0],
                                             "conf": 0.91}]}],
                "error": None})
        else:
            out.append({"page": int(p["page"]),
                        "geom": {"w": PAGE_W, "h": PAGE_H},
                        "verdict": "not_detected", "regions": [],
                        "error": None})
    return {"schema": "juscite-f42-stamp-worker/1", "ok": True,
            "engine": {"engine": "fake-test", "device": "gpu:0",
                       "worker_pid": 4242},
            "pages": out}


def _pin_face():
    """运行时钉定本波面（w4-u21）。全套单进程内多波桥测试共存；本文件
    测试类 setUpClass 重钉，保证桥内延迟 import 恒命中本波面（F41 同式）。"""
    sys.path.insert(0, str(_ANONYMIZER_SRC))
    if _ANONYMIZER_SRC is None:
        return None
    import importlib
    for m in [m for m in sys.modules if m == "legal_anonymizer"
              or m.startswith("legal_anonymizer.")]:
        del sys.modules[m]
    return importlib.import_module(
        "legal_anonymizer.application.stamp_visual_service")


def _pin_and_refresh():
    global _svs
    m = _pin_face()
    if m is not None:
        _svs = m


class F42BridgeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pin_and_refresh()

    def test_frozen_method_group(self):
        self.assertEqual(STAMP_METHODS, frozenset({
            "stamp.register", "stamp.run", "stamp.pending", "stamp.report",
            "stamp.page", "stamp.original", "stamp.limitation",
            "stamp.conclusion_scan"}))

    def test_unknown_stamp_method_stays_not_connected(self):
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected:stamp.explode"):
            call("stamp.explode", {}, {"anonymizer_contract": "p09/p10"})

    def test_fail_closed_config_triangle(self):
        with self.assertRaisesRegex(NotConnected,
                                    "anonymizer_p09_p10_not_configured"):
            call("stamp.report", {"run_id": "f42-x"}, {})
        with self.assertRaisesRegex(NotConnected,
                                    "stamp_state_root_not_configured"):
            call("stamp.report", {"run_id": "f42-x"},
                 {"anonymizer_contract": "p09/p10"})
        with self.assertRaisesRegex(NotConnected,
                                    "stamp_interpreter_not_configured"):
            call("stamp.register", {"corpus_root": "C:/nowhere"},
                 {"anonymizer_contract": "p09/p10",
                  "ocr_ports_state_root": "C:/nowhere-state"})

    def test_params_validation(self):
        cfg = {"anonymizer_contract": "p09/p10",
               "ocr_ports_state_root": "C:/nowhere-state",
               "ocr_baseline_interpreter": "C:/nowhere-python.exe"}
        with self.assertRaisesRegex(NotConnected, "stamp_run_id_required"):
            call("stamp.report", {}, cfg)
        with self.assertRaisesRegex(NotConnected,
                                    "stamp_corpus_root_required"):
            call("stamp.register", {}, cfg)
        with self.assertRaisesRegex(NotConnected, "stamp_doc_id_required"):
            call("stamp.page", {"run_id": "f42-x", "page": 1}, cfg)
        for bad in (0, True, "1", 1.0):
            with self.assertRaisesRegex(NotConnected, "stamp_page_invalid"):
                call("stamp.page", {"run_id": "f42-x", "doc_id": "doc_a",
                                    "page": bad}, cfg)


@unittest.skipIf(_svs is None,
                 "anonymizer w4-u21 源不可得（JUSCITE_ANONYMIZER_SRC 未配且"
                 " 同波 worktree 不在盘）")
class F42BridgeLifecycleTests(unittest.TestCase):
    """经桥全生命周期（引擎测试缝）：登记白名单/跑批/原图回读/结论闭集。"""

    @classmethod
    def setUpClass(cls):
        _pin_and_refresh()

    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="f42-bridge-"))
        self.corpus = _write_corpus(self._tmp)
        self.interp = self._tmp / "interp" / "python.exe"
        self.interp.parent.mkdir(parents=True, exist_ok=True)
        self.interp.write_bytes(b"# synthetic interpreter stub\n")
        self.config = {
            "anonymizer_contract": "p09/p10",
            "ocr_ports_state_root": str(self._tmp / "state"),
            "ocr_baseline_interpreter": str(self.interp),
        }
        self._suspected: set = set()
        self._real_spawn = _svs._spawn_worker
        _svs._spawn_worker = self._fake_spawn
        self.addCleanup(self._restore_spawn)
        self.addCleanup(self._cleanup_tmp)

    def _restore_spawn(self):
        _svs._spawn_worker = self._real_spawn

    def _cleanup_tmp(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _fake_spawn(self, rdir, interp, pages):
        return _fake_worker_payload(pages, self._suspected)

    def _register(self):
        return call("stamp.register", {"corpus_root": str(self.corpus)},
                    self.config)

    def _run(self, suspected_pages: set) -> dict:
        self._suspected = suspected_pages
        reg = self._register()
        return call("stamp.run", {"run_id": reg["run_id"]}, self.config)

    # ------------------------------------------------------------ 登记面
    def test_register_pins_interpreter_whitelist_idempotent(self):
        reg = self._register()
        self.assertTrue(reg["run_id"].startswith("f42-"))
        self.assertEqual(reg["registered_pages"], 2)
        self.assertEqual(reg["verdicts_closed_set"],
                         ["suspected", "not_detected"])
        run_raw = (Path(self.config["ocr_ports_state_root"]) / "f42-stamp"
                   / reg["run_id"] / "run.json").read_text(encoding="utf-8")
        self.assertNotIn("gold_boxes", run_raw)       # 金标结构性不入账
        self.assertNotIn("cx", run_raw)
        self.assertIn("interpreter_pin", run_raw)
        again = self._register()
        self.assertEqual(again["run_id"], reg["run_id"])   # 幂等回读

    def test_pending_lists_unrun_pages(self):
        reg = self._register()
        pend = call("stamp.pending", {"run_id": reg["run_id"]}, self.config)
        self.assertEqual(pend["pending"],
                         [{"doc_id": "doc_a", "page": 1},
                          {"doc_id": "doc_b", "page": 1}])

    # ------------------------------------------------------------ 跑批面
    def test_run_report_verdicts_and_page_limitation(self):
        out = self._run({("doc_a", 1)})
        self.assertEqual(out["processed"], 2)
        self.assertEqual(out["failed"], 0)
        run_id = self._register()["run_id"]
        report = call("stamp.report", {"run_id": run_id}, self.config)
        self.assertEqual(report["completed"], 2)
        self.assertEqual(report["verdict_counts"],
                         {"suspected": 1, "not_detected": 1})
        self.assertEqual(report["error_pages"], 0)
        rec = call("stamp.page",
                   {"run_id": run_id, "doc_id": "doc_a", "page": 1},
                   self.config)
        self.assertEqual(rec["verdict"], "suspected")
        self.assertEqual(rec["regions"][0]["conf"], 0.9)
        self.assertEqual(rec["limitation"]["not_a"], "expert_opinion")
        self.assertTrue(rec["limitation"]["models"])
        self.assertEqual(rec["engine"]["regions"], 1)

    def test_verdict_outside_closed_set_rejected(self):
        real_spawn = _svs._spawn_worker

        def bad_spawn(rdir, interp, pages):
            payload = _fake_worker_payload(pages, set())
            for rec in payload["pages"]:
                rec["verdict"] = "authentic_genuine"   # 闭集外伪造形态
            return payload

        _svs._spawn_worker = bad_spawn
        try:
            out = self._run(set())
        finally:
            _svs._spawn_worker = real_spawn
        self.assertEqual(out["failed"], 2)
        run_id = self._register()["run_id"]
        rec = call("stamp.page",
                   {"run_id": run_id, "doc_id": "doc_b", "page": 1},
                   self.config)
        self.assertEqual(rec["error"], "worker_verdict_not_in_closed_set")
        self.assertIsNone(rec["verdict"])   # 失败不假成功：verdict 恒空

    def test_interpreter_drift_rejected(self):
        self._register()
        run_id = self._register()["run_id"]
        self.interp.write_bytes(b"# changed stub\n")
        with self.assertRaisesRegex(NotConnected, "stamp_interpreter_changed"):
            call("stamp.run", {"run_id": run_id}, self.config)

    # ---------------------------------------------------------- 原图回读
    def test_original_readback_mapping_no_bytes(self):
        self._run({("doc_a", 1)})
        run_id = self._register()["run_id"]
        out = call("stamp.original",
                   {"run_id": run_id, "doc_id": "doc_a", "page": 1},
                   self.config)
        self.assertTrue(out["sha_match"])
        self.assertTrue(out["read_only"])
        self.assertFalse(out["bytes_returned"])       # 字节恒不出域
        self.assertEqual(out["region_bboxes"], [[770, 180, 1070, 480]])
        for forbidden in ("payload", "png_bytes", "bytes_b64", "data"):
            self.assertNotIn(forbidden, out)

    def test_original_tamper_rejected(self):
        self._run(set())
        run_id = self._register()["run_id"]
        victim = self.corpus / "pages/doc_b/p0001.png"
        payload = victim.read_bytes()
        victim.write_bytes(payload[:-1] + bytes([payload[-1] ^ 0x5A]))
        try:
            with self.assertRaisesRegex(NotConnected,
                                        "stamp_original_bytes_mismatch"):
                call("stamp.original",
                     {"run_id": run_id, "doc_id": "doc_b", "page": 1},
                     self.config)
        finally:
            victim.write_bytes(payload)
        # 越界页：typed 拒（不在 run 的页没有可回读对象）
        with self.assertRaisesRegex(NotConnected, "stamp_page_not_in_run"):
            call("stamp.original",
                 {"run_id": run_id, "doc_id": "doc_z", "page": 9},
                 self.config)

    def test_error_page_fail_closed_chain(self):
        """低置信/失败不假成功（E11 语义）：登记后改写页字节→拒跑记错误码
        →错误页 verdict 恒 None→原图回读 typed 拒。"""
        run_id = self._register()["run_id"]
        victim = self.corpus / "pages/doc_b/p0001.png"
        payload = victim.read_bytes()
        victim.write_bytes(b"F42-SYNTHETIC-FAULT-INJECTION")
        try:
            out = call("stamp.run", {"run_id": run_id}, self.config)
        finally:
            victim.write_bytes(payload)
        self.assertEqual(out["failed"], 1)
        self.assertEqual(out["processed"], 1)   # 他页不阻断（真跑经缝）
        rec = call("stamp.page",
                   {"run_id": run_id, "doc_id": "doc_b", "page": 1},
                   self.config)
        self.assertEqual(rec["error"], "page_bytes_mismatch")
        self.assertIsNone(rec["verdict"])
        report = call("stamp.report", {"run_id": run_id}, self.config)
        self.assertEqual(report["error_pages"], 1)
        self.assertEqual(report["error_codes"], {"page_bytes_mismatch": 1})
        with self.assertRaisesRegex(NotConnected,
                                    "stamp_original_page_not_completed"):
            call("stamp.original",
                 {"run_id": run_id, "doc_id": "doc_b", "page": 1},
                 self.config)

    # -------------------------------------------------------- 结论闭集面
    def test_limitation_static_face_and_scan_clean(self):
        face = call("stamp.limitation", {}, self.config)
        self.assertEqual(face["verdicts_closed_set"],
                         ["suspected", "not_detected"])
        self.assertEqual(face["limitation"]["not_a"], "expert_opinion")
        self.assertGreaterEqual(len(face["limitation"]["boundary"]), 3)
        self._run({("doc_a", 1)})
        run_id = self._register()["run_id"]
        scan = call("stamp.conclusion_scan", {"run_id": run_id},
                    self.config)
        self.assertEqual(scan["records_scanned"], 3)   # run.json＋2 页
        self.assertEqual(scan["verdict_values"],
                         {"suspected": 1, "not_detected": 1})
        self.assertEqual(scan["forbidden_hits"], [])

    def test_scan_catches_planted_morphology(self):
        self._run({("doc_a", 1)})
        run_id = self._register()["run_id"]
        victim = (Path(self.config["ocr_ports_state_root"]) / "f42-stamp"
                  / run_id / "pages/doc_b/p0001.json")
        doc = json.loads(victim.read_text(encoding="utf-8"))
        doc["鉴定结论"] = "synthetic-plant"
        victim.write_text(json.dumps(doc, ensure_ascii=False),
                          encoding="utf-8")
        try:
            with self.assertRaisesRegex(
                    NotConnected, "stamp_conclusion_morphology_detected"):
                call("stamp.conclusion_scan", {"run_id": run_id},
                     self.config)
        finally:
            victim.unlink()
        scan = call("stamp.conclusion_scan", {"run_id": run_id},
                    self.config)
        self.assertEqual(scan["forbidden_hits"], [])


@unittest.skipUnless(_INTERP_AVAILABLE and _svs is not None,
                     "钉定解释器不在机上（真引擎组如实 skip）")
class F42BridgeRealEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pin_and_refresh()

    def test_real_engine_single_seal_page(self):
        tmp = Path(tempfile.mkdtemp(prefix="f42-bridge-real-"))
        try:
            corpus = tmp / "corpus"
            (corpus / "pages/doc_a").mkdir(parents=True)
            payload = _seal_png()
            rel = "pages/doc_a/p0001.png"
            (corpus / rel).write_bytes(payload)
            (corpus / "corpus_manifest.json").write_text(
                json.dumps({"schema": "juscite-f42-stamp-gold/1", "seed": 7,
                            "documents": [{"doc_id": "doc_a",
                                           "doc_code": "SJ-F42W",
                                           "page_count": 1,
                                           "page_files": [{
                                               "page": 1, "kind": "TEXT",
                                               "png": rel,
                                               "sha256": hashlib.sha256(
                                                   payload).hexdigest(),
                                               "bytes": len(payload)}]}]},
                           ensure_ascii=False), encoding="utf-8")
            config = {"anonymizer_contract": "p09/p10",
                      "ocr_ports_state_root": str(tmp / "state"),
                      "ocr_baseline_interpreter": str(_INTERP)}
            reg = call("stamp.register", {"corpus_root": str(corpus)},
                       config)
            out = call("stamp.run", {"run_id": reg["run_id"]}, config)
            self.assertEqual(out["failed"], 0, msg=str(out))
            rec = call("stamp.page",
                       {"run_id": reg["run_id"], "doc_id": "doc_a",
                        "page": 1}, config)
            self.assertEqual(rec["verdict"], "suspected", msg=str(rec))
            bx = rec["regions"][0]["bbox"]
            self.assertTrue(bx[0] <= GOLD["cx"] <= bx[2]
                            and bx[1] <= GOLD["cy"] <= bx[3], msg=str(bx))
            eng = rec["engine"]
            self.assertEqual(eng["device"], "gpu:0")
            self.assertTrue(eng["cuda_compiled"])
            self.assertGreaterEqual(len(eng["model_cache"]["files"]), 10)
            orig = call("stamp.original",
                        {"run_id": reg["run_id"], "doc_id": "doc_a",
                         "page": 1}, config)
            self.assertTrue(orig["sha_match"])
            self.assertFalse(orig["bytes_returned"])
            scan = call("stamp.conclusion_scan", {"run_id": reg["run_id"]},
                        config)
            self.assertEqual(scan["forbidden_hits"], [])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
