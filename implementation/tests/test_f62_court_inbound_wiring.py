"""F62 法院来件 OCR 入库链产品面接线测试（W3-U14）。

全部合成材料：ocr/harness 桥 seam 注入（不真起 OCR worker 与 harness 进程，
单测零网络零仓依赖）；真 OCR 基线链与真 harness MatterStore 的全链对账在
tools/PENDING_OWNER_f62_court_inbound_recon.py（GPU fail-closed 钉定解释器
真跑）。fail-closed 纪律：未配置状态根＝NOT_CONNECTED，绝不空响应冒成功。
"""

from __future__ import annotations

import ast
import base64
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
import court_inbound  # noqa: E402

MATTER = "m-f62"
SMS_TEXT = ("【合成市第一人民法院】您有（2026）京01民初91001号案件文书送达，"
            "请及时登录律引查收并确认入库。")
CONFIG = {"court_inbound_state_root": "X:/synth/state"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_corpus(tmp: Path) -> Path:
    corpus = tmp / "att-corpus"
    (corpus / "docs").mkdir(parents=True)
    payload = b"synthetic court attachment pdf bytes"
    (corpus / "docs" / "att_0001.pdf").write_bytes(payload)
    manifest = {"schema": "juscite-f38-f44-attachments/1", "synthetic": True,
                "documents": [{"doc_id": "att_0001",
                               "page_files": [{"page": 1,
                                               "png": "pages/att_0001/p0001.png"}]}]}
    (corpus / "corpus_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return corpus


def _sms_args(corpus: Path, sms_id: str = "sms-0001", text: str = SMS_TEXT,
              sent_at: str = "2026-10-17T09:00:00+08:00") -> dict:
    return {"matter_id": MATTER,
            "sms": {"sms_id": sms_id, "sender": "合成市第一人民法院",
                    "sent_at": sent_at, "text": text, "corpus_root":
                    str(corpus),
                    "attachments": [{"doc_id": "att_0001",
                                     "path": "docs/att_0001.pdf"}]}}


OCR_LINES = [
    {"page": 1, "lines": [
        {"text": "合成附件材料（全合成测试材料）", "conf": 0.97},
        {"text": "案号：（2026）京01民初91001号", "conf": 0.95},
        {"text": "联系电话：13700002222", "conf": 0.93},
    ]},
]


def _fake_ocr(lines_by_call: list | None = None):
    """F41 桥 seam：register/run 幂等形状＋doc_version 合成 OCR 行。"""
    calls: list[tuple] = []

    def call(method, args):
        calls.append((method, json.loads(json.dumps(args))))
        if method == "ocr.batch_register":
            return {"batch_id": "f41-synthetic0001", "corpus_sha256":
                    "cafe" * 16, "counters": {"docs_pending": 1}}
        if method == "ocr.batch_run":
            return {"status": "COMPLETED", "pending_after": []}
        if method == "ocr.batch_doc_version":
            return {"batch_id": args["batch_id"], "doc_id": args["doc_id"],
                    "version": 1, "is_current": True,
                    "doc": {"doc_id": args["doc_id"], "error_pages": 0,
                            "engine": {"engine": "paddleocr",
                                       "device": "gpu:0"}},
                    "pages": (lines_by_call or [OCR_LINES]).pop(0)
                    if lines_by_call else OCR_LINES}
        raise AssertionError("unexpected " + method)
    call.calls = calls
    return call


def _fake_harness():
    calls: list[tuple] = []

    def call(method, args):
        calls.append((method, json.loads(json.dumps(args))))
        assert method == "harness.register_material"
        material = args["material"]
        content = base64.b64decode(material["bytesB64"])
        return {"ref": {"owner": "harness", "kind": "material",
                        "id": material["id"], "version": "1",
                        "matterId": args["scope"]["matterId"]},
                "revision": 1, "sha256": _sha(content),
                "casRef": "cas://" + _sha(content)}
    call.calls = calls
    return call


class F62ProductFaceTests(unittest.TestCase):
    """court_inbound 产品面全链（合成桥）：登记→跑批→候选→人审→入库。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="juscite-f62-test-")
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.corpus = _make_corpus(Path(self.tmp.name))
        self.config = dict(CONFIG, court_inbound_state_root=str(self.state))

    # --------------------------------------------- 桥面：冻结组＋fail-closed
    def test_method_group_frozen(self) -> None:
        self.assertEqual(
            legal_entry.COURT_INBOUND_METHODS,
            frozenset({
                "court_inbound.sms_receive", "court_inbound.inbound_run",
                "court_inbound.candidate_review", "court_inbound.intake",
                "court_inbound.read", "court_inbound.list"}))

    def test_unconfigured_and_unknown_fail_closed(self) -> None:
        with self.assertRaisesRegex(NotConnected,
                                    "f62_state_root_not_configured"):
            legal_entry.call("court_inbound.sms_receive",
                             {"matter_id": MATTER}, {})
        with self.assertRaisesRegex(NotConnected, "method_not_connected"):
            legal_entry.call("court_inbound.explode",
                             {"matter_id": MATTER}, self.config)
        with self.assertRaisesRegex(NotConnected,
                                    "court_inbound_params_invalid"):
            legal_entry.call("court_inbound.list", ["not-a-dict"],
                             self.config)
        with self.assertRaisesRegex(court_inbound.CourtInboundError,
                                    "f62_matter_id_invalid"):
            legal_entry.call("court_inbound.list",
                             {"matter_id": "../escape"}, self.config)

    def test_import_closure_deterministic(self) -> None:
        # AST 纪律（同 W2b-U04 先例）：确定性白名单闭集，零网络零模型。
        tree = ast.parse(
            (ROOT / "python" / "court_inbound.py").read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertLessEqual(
            imports,
            {"__future__", "base64", "hashlib", "json", "os", "re",
             "datetime", "pathlib", "bridge_errors", "legal_entry"},
            f"court_inbound 导入闭集越界：{sorted(imports)}")

    # ------------------------------------------------------------- 短信登记
    def test_sms_receive_idempotency_three_flavors(self) -> None:
        args = _sms_args(self.corpus)
        first = legal_entry.call("court_inbound.sms_receive", args,
                                 self.config)
        self.assertFalse(first["duplicate"])
        self.assertEqual(first["parsed"]["court"], "合成市第一人民法院")
        self.assertEqual(first["parsed"]["case_numbers"],
                         ["（2026）京01民初91001号"])
        self.assertTrue(first["attachments"][0]["sha256"])
        # 同 id 同内容→重放，不重记账
        replay = legal_entry.call("court_inbound.sms_receive", args,
                                  self.config)
        self.assertTrue(replay["duplicate"])
        self.assertEqual(replay["sms_id"], first["sms_id"])
        # 同内容异 id（网关重发）→去重回既有账
        resent = legal_entry.call(
            "court_inbound.sms_receive",
            _sms_args(self.corpus, sms_id="sms-retry-9"), self.config)
        self.assertTrue(resent["duplicate"])
        self.assertEqual(resent["sms_id"], first["sms_id"])
        self.assertEqual(resent["deduped_from"], "sms-retry-9")
        # 同 id 异内容→具名拒
        with self.assertRaisesRegex(court_inbound.CourtInboundError,
                                    "f62_sms_id_content_conflict"):
            legal_entry.call(
                "court_inbound.sms_receive",
                _sms_args(self.corpus, text=SMS_TEXT + "（改）"), self.config)
        records = list(self.state.glob("f62-inbound/*/sms-*.json"))
        self.assertEqual(len(records), 1)

    # ------------------------------------------------------------- 入件跑批
    def _received(self) -> dict:
        return legal_entry.call("court_inbound.sms_receive",
                                _sms_args(self.corpus), self.config)

    def test_inbound_run_extracts_candidates_and_replays(self) -> None:
        self._received()
        ocr = _fake_ocr()
        # 桥径 fail-closed：状态根已配但 ocr/harness 域未配→NOT_CONNECTED
        with self.assertRaisesRegex(NotConnected,
                                    "anonymizer_p09_p10_not_configured"):
            legal_entry.call("court_inbound.inbound_run",
                             {"matter_id": MATTER, "sms_id": "sms-0001"},
                             self.config)
        run = court_inbound.court_inbound_call(
            "court_inbound.inbound_run",
            {"matter_id": MATTER, "sms_id": "sms-0001"}, self.config,
            ocr_call=ocr)
        self.assertFalse(run["duplicate"])
        self.assertEqual([c["value"] for c in run["candidates"]],
                         ["（2026）京01民初91001号"])
        cand = run["candidates"][0]
        self.assertEqual(cand["page"], 1)
        self.assertEqual(cand["line_index"], 1)
        self.assertEqual(cand["type"], "case_number")
        self.assertTrue(cand["candidate_id"].startswith("cand-"))
        digest = run["candidates_sha256"]
        # 重跑：同批同指纹→重放
        rerun = court_inbound.court_inbound_call(
            "court_inbound.inbound_run",
            {"matter_id": MATTER, "sms_id": "sms-0001"}, self.config,
            ocr_call=ocr)
        self.assertTrue(rerun["duplicate"])
        self.assertEqual(rerun["candidates_sha256"], digest)
        # OCR 行漂移→指纹冲突具名拒
        drifting = _fake_ocr(lines_by_call=[
            [dict(OCR_LINES[0], lines=OCR_LINES[0]["lines"] +
                  [{"text": "案号：（2026）京01民初99999号", "conf": 0.9}])],
            [dict(OCR_LINES[0])]])
        with self.assertRaisesRegex(court_inbound.CourtInboundError,
                                    "f62_run_digest_conflict"):
            court_inbound.court_inbound_call(
                "court_inbound.inbound_run",
                {"matter_id": MATTER, "sms_id": "sms-0001"}, self.config,
                ocr_call=drifting)

    def test_inbound_run_attachment_tamper_refused(self) -> None:
        self._received()
        pdf = self.corpus / "docs" / "att_0001.pdf"
        original = pdf.read_bytes()
        pdf.write_bytes(original + b"tampered")
        with self.assertRaisesRegex(court_inbound.CourtInboundError,
                                    "f62_attachment_changed"):
            court_inbound.court_inbound_call(
                "court_inbound.inbound_run",
                {"matter_id": MATTER, "sms_id": "sms-0001"}, self.config,
                ocr_call=_fake_ocr())
        pdf.write_bytes(original)

    # ------------------------------------------------------------- 人审确认
    def _run(self) -> dict:
        self._received()
        return court_inbound.court_inbound_call(
            "court_inbound.inbound_run",
            {"matter_id": MATTER, "sms_id": "sms-0001"}, self.config,
            ocr_call=_fake_ocr())

    def test_candidate_review_guards_and_conflict(self) -> None:
        run = self._run()
        cid = run["candidates"][0]["candidate_id"]
        with self.assertRaisesRegex(court_inbound.CourtInboundError,
                                    "f62_candidate_unknown"):
            court_inbound.court_inbound_call(
                "court_inbound.candidate_review",
                {"matter_id": MATTER, "sms_id": "sms-0001",
                 "reviewer": "律师甲",
                 "decisions": [{"candidate_id": "cand-nope",
                                "decision": "confirmed"}]}, self.config)
        with self.assertRaisesRegex(court_inbound.CourtInboundError,
                                    "f62_review_decision_invalid"):
            court_inbound.court_inbound_call(
                "court_inbound.candidate_review",
                {"matter_id": MATTER, "sms_id": "sms-0001",
                 "reviewer": "律师甲",
                 "decisions": [{"candidate_id": cid,
                                "decision": "maybe"}]}, self.config)
        review = court_inbound.court_inbound_call(
            "court_inbound.candidate_review",
            {"matter_id": MATTER, "sms_id": "sms-0001", "reviewer": "律师甲",
             "decisions": [{"candidate_id": cid,
                            "decision": "confirmed"}]}, self.config)
        self.assertEqual(review["counts"]["confirmed"], 1)
        self.assertEqual(review["counts"]["unreviewed"], 0)
        # 同候选同决定＝幂等重放
        again = court_inbound.court_inbound_call(
            "court_inbound.candidate_review",
            {"matter_id": MATTER, "sms_id": "sms-0001", "reviewer": "律师甲",
             "decisions": [{"candidate_id": cid,
                            "decision": "confirmed"}]}, self.config)
        self.assertEqual(len(again["reviews"]), 1)
        # 翻案＝具名拒不静默改
        with self.assertRaisesRegex(court_inbound.CourtInboundError,
                                    "f62_candidate_review_conflict"):
            court_inbound.court_inbound_call(
                "court_inbound.candidate_review",
                {"matter_id": MATTER, "sms_id": "sms-0001",
                 "reviewer": "律师甲",
                 "decisions": [{"candidate_id": cid,
                                "decision": "rejected"}]}, self.config)

    # ------------------------------------------------------------- 入库
    def test_intake_guards_then_register_deterministic(self) -> None:
        self._received()                      # 链不齐（未跑批未人审）
        with self.assertRaisesRegex(court_inbound.CourtInboundError,
                                    "f62_intake_chain_incomplete"):
            court_inbound.court_inbound_call(
                "court_inbound.intake",
                {"matter_id": MATTER, "sms_id": "sms-0001"}, self.config)
        run = self._run()
        cid = run["candidates"][0]["candidate_id"]
        harness = _fake_harness()
        court_inbound.court_inbound_call(
            "court_inbound.candidate_review",
            {"matter_id": MATTER, "sms_id": "sms-0001", "reviewer": "律师甲",
             "decisions": [{"candidate_id": cid,
                            "decision": "rejected"}]}, self.config)
        with self.assertRaisesRegex(court_inbound.CourtInboundError,
                                    "f62_intake_no_confirmed_candidate"):
            court_inbound.court_inbound_call(
                "court_inbound.intake",
                {"matter_id": MATTER, "sms_id": "sms-0001"}, self.config,
                ocr_call=_fake_ocr(), harness_call=harness)
        # 改判不允许——直接换新短信（异内容=异 sent_at）走全链 happy path；
        # 双候选制造"部分人审"负向后再补审
        legal_entry.call(
            "court_inbound.sms_receive",
            _sms_args(self.corpus, sms_id="sms-0002",
                      sent_at="2026-10-17T10:00:00+08:00"), self.config)
        two_cand = [[{"page": 1, "lines": [
            {"text": "案号：（2026）京01民初91001号", "conf": 0.95},
            {"text": "案号：（2026）京01民初91002号", "conf": 0.94}]}]]
        court_inbound.court_inbound_call(
            "court_inbound.inbound_run",
            {"matter_id": MATTER, "sms_id": "sms-0002"}, self.config,
            ocr_call=_fake_ocr(lines_by_call=two_cand))
        run2 = court_inbound.court_inbound_call(
            "court_inbound.read",
            {"matter_id": MATTER, "sms_id": "sms-0002"}, self.config)
        self.assertEqual(len(run2["run"]["candidates"]), 2)
        cid2 = run2["run"]["candidates"][0]["candidate_id"]
        court_inbound.court_inbound_call(
            "court_inbound.candidate_review",
            {"matter_id": MATTER, "sms_id": "sms-0002", "reviewer": "律师甲",
             "decisions": [{"candidate_id": cid2,
                            "decision": "confirmed"}]}, self.config)
        harness = _fake_harness()
        with self.assertRaisesRegex(court_inbound.CourtInboundError,
                                    "f62_intake_unreviewed_candidates"):
            court_inbound.court_inbound_call(
                "court_inbound.intake",
                {"matter_id": MATTER, "sms_id": "sms-0002"}, self.config,
                ocr_call=_fake_ocr(), harness_call=harness)
        cid2b = run2["run"]["candidates"][1]["candidate_id"]
        court_inbound.court_inbound_call(
            "court_inbound.candidate_review",
            {"matter_id": MATTER, "sms_id": "sms-0002", "reviewer": "律师甲",
             "decisions": [{"candidate_id": cid2b,
                            "decision": "confirmed"}]}, self.config)
        first = court_inbound.court_inbound_call(
            "court_inbound.intake",
            {"matter_id": MATTER, "sms_id": "sms-0002"}, self.config,
            ocr_call=_fake_ocr(), harness_call=harness)
        self.assertFalse(first["replayed"])
        self.assertEqual(len(harness.calls), 1)
        method, payload = harness.calls[0]
        self.assertEqual(method, "harness.register_material")
        self.assertEqual(payload["material"]["kind"], "scan")
        self.assertEqual(payload["material"]["id"],
                         f"f62-{MATTER}-sms-0002")
        self.assertEqual(payload["key"]["requestId"],
                         first["request_id"])
        self.assertTrue(payload["key"]["requestId"].startswith(
            f"f62-intake-{MATTER}-sms-0002-"))
        material_text = base64.b64decode(
            payload["material"]["bytesB64"]).decode("utf-8")
        self.assertIn("（2026）京01民初91001号", material_text)
        self.assertIn("confirmed by 律师甲", material_text)
        self.assertIn("送达事实不由上传日自动补", material_text)
        # 幂等重放：再入库不再打桥、同回执
        second = court_inbound.court_inbound_call(
            "court_inbound.intake",
            {"matter_id": MATTER, "sms_id": "sms-0002"}, self.config,
            ocr_call=_fake_ocr(), harness_call=harness)
        self.assertTrue(second["replayed"])
        self.assertEqual(len(harness.calls), 1)
        self.assertEqual(second["material_sha256"], first["material_sha256"])
        # 漂移（入库账被篡改）＝具名拒不静默重登
        intake_path = (self.state / "f62-inbound" / MATTER /
                       "intake-sms-0002.json")
        record = json.loads(intake_path.read_text(encoding="utf-8"))
        record["intake_bytes_sha256"] = "0" * 64
        intake_path.write_text(json.dumps(record, ensure_ascii=False),
                               encoding="utf-8")
        with self.assertRaisesRegex(court_inbound.CourtInboundError,
                                    "f62_intake_drift"):
            court_inbound.court_inbound_call(
                "court_inbound.intake",
                {"matter_id": MATTER, "sms_id": "sms-0002"}, self.config,
                ocr_call=_fake_ocr(), harness_call=harness)

    def test_read_and_list_projections(self) -> None:
        self._received()
        court_inbound.court_inbound_call(
            "court_inbound.inbound_run",
            {"matter_id": MATTER, "sms_id": "sms-0001"}, self.config,
            ocr_call=_fake_ocr())
        projection = legal_entry.call(
            "court_inbound.read",
            {"matter_id": MATTER, "sms_id": "sms-0001"}, self.config)
        self.assertIsNone(projection["intake"])
        self.assertIsNotNone(projection["run"]["batch_id"])
        listing = legal_entry.call("court_inbound.list",
                                   {"matter_id": MATTER}, self.config)
        self.assertEqual(len(listing["items"]), 1)
        self.assertIsNone(listing["items"][0]["intake_material_id"])


if __name__ == "__main__":
    unittest.main()
