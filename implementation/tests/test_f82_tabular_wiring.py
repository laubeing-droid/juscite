"""F82 产品侧接线测试（W2b-U05）：Tabular 窄版闭环核心方法组。

全部合成材料。legal_entry 新增 HARNESS_TABULAR_METHODS 五方法（复用
--reviewbatch-json 信封）＋TABULAR_METHODS 四方法（产品面 tabular_review），
桥与产品面经 subprocess seam 注入单测（零仓依赖；真全链实跑对账在
tools/PENDING_OWNER_f82_tabular_core_recon.py）。fail-closed：未配置桥＝
NOT_CONNECTED（exit 3 具名），绝不空响应冒成功。

合同要点（harness docs/f82-tabular-core-contract.md＋产品面模块头）：
列三元组（列名/金标/值）投影；支持戳只记已过闸结论（UNVERIFIED 拒盖章
＝先核验服务再接抽取的接线点纪律）；出处钉页文本 sha256；失效理由闭集
权威在 harness；tabular.audit 材料侧 sha＋引用在页内、法规侧同面复验。
"""

from __future__ import annotations

import json
import sys
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
import tabular_review  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E401

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
    "codices_face_sha256": "a" * 64,
    "tabular_corpus_root": "X:/synth/corpus",
}
SCOPE = {"kind": "matter", "matterId": "m-f82"}
H82_METHODS = (
    "harness.review_columns_define", "harness.review_columns_read",
    "harness.review_support_record", "harness.review_support_invalidate",
    "harness.review_support_read",
)
TABULAR_METHODS = (
    "tabular.read", "tabular.support_stamp", "tabular.invalidate",
    "tabular.audit",
)


def fake_entry_output(result):
    return json.dumps({"surface": "reviewbatch", "method": "synthetic",
                       "result": result})


def patch_execute(testcase, *, stdout="", returncode=0, calls=None):
    def _fake(argv, env, timeout):
        if calls is not None:
            calls.append({"argv": argv, "env": env})
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
    patcher.start()
    testcase.addCleanup(patcher.stop)


def command_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def synth_stamp_view(gate_status: str = "CITATION_VERIFIED") -> dict:
    """U02 extraction.candidate 回读形态（全合成）。"""
    return {
        "candidate_id": "cand_0001",
        "text": "依据《中华人民共和国个人信息保护法》第一条：“…”",
        "provenance": {"source": "material_extraction", "doc": "synth_doc",
                       "page": 3, "textSha256": "b" * 64},
        "gate_status": gate_status,
        "proposition_support": "PENDING_GATE",
        "rejection_reasons": [],
        "gate_history": [{
            "run_seq": 1, "as_of": "20261016",
            "citations": [{"citation_text": "《中华人民共和国个人信息保护"
                                            "法》第一条", "status": "现行",
                           "code": None, "verified_scoped": True,
                           "quote_in_article": True}],
            "gate_status": gate_status,
        }],
    }


class F82BridgeTests(unittest.TestCase):
    """legal_entry 双方法组：白名单、信封、fail-closed。"""

    def test_harness_tabular_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_TABULAR_METHODS,
                         frozenset(H82_METHODS))
        for forged in ("harness.review_support_verify",
                       "harness.review_support_mark_verified",
                       "harness.review_columns_patch_gold"):
            self.assertNotIn(forged, legal_entry.HARNESS_TABULAR_METHODS)

    def test_tabular_group_membership(self) -> None:
        self.assertEqual(legal_entry.TABULAR_METHODS,
                         frozenset(TABULAR_METHODS))
        for forged in ("tabular.mark_supported", "tabular.verify",
                       "tabular.sign_off"):
            self.assertNotIn(forged, legal_entry.TABULAR_METHODS)

    def test_harness_methods_ride_reviewbatch_envelope(self) -> None:
        for method in H82_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--reviewbatch-json") + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_entry_output({"receipt": "synthetic"}),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, {
                    "actor_id": "lawyer-1", "scope": SCOPE,
                    "key": command_key("r-1"), "batch_id": "brt-synth"},
                    CONFIG)
                self.assertEqual(result, {"receipt": "synthetic"})
                argv = captured[0]["argv"]
                self.assertIn("--reviewbatch-json", argv)
                self.assertEqual(captured[0]["envelope"]["method"], method)

    def test_unconfigured_and_unknown_fail_closed(self) -> None:
        for method in H82_METHODS[:1] + TABULAR_METHODS[:1]:
            with self.subTest(method=method):
                with self.assertRaises(NotConnected):
                    legal_entry.call(method, {"scope": SCOPE}, {})
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("tabular.support_verify", {}, CONFIG)
        self.assertIn("method_not_connected:tabular.support_verify",
                      str(caught.exception))


class SupportStampTests(unittest.TestCase):
    """tabular.support_stamp：E14 接线点纪律（先核验再盖章）。"""

    def setUp(self) -> None:
        stamp_args = {
            "extraction_batch_id": "exb-synth", "candidate_id": "cand_0001",
            "review_batch_id": "brt-synth", "row_id": "row-1",
            "cell_id": "amount", "actor_id": "worker-1", "scope": SCOPE,
            "key": command_key("st-1"),
        }
        self.stamp_args = stamp_args
        recorded: list[dict] = []

        def _harness(method, args, config):
            recorded.append({"method": method, "args": args})
            return {"seq": 1, "cellGeneration": 1}

        patcher = unittest.mock.patch.object(tabular_review, "_harness_call",
                                             _harness)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.recorded = recorded

    def _patch_candidate(self, view, error=None):
        import extraction_gate

        def _read(args, config):
            if error is not None:
                raise error
            return view
        patcher = unittest.mock.patch.object(extraction_gate,
                                             "candidate_read", _read)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_stamp_records_gate_verdict_with_face_chain(self) -> None:
        self._patch_candidate(synth_stamp_view())
        result = tabular_review.tabular_call("tabular.support_stamp",
                                             self.stamp_args, CONFIG)
        self.assertEqual(result["cellGeneration"], 1)
        call = self.recorded[0]
        self.assertEqual(call["method"], "harness.review_support_record")
        entry = call["args"]["entry"]
        self.assertEqual(entry["gate"]["via"], "extraction.gate(W2b-U02)")
        self.assertEqual(entry["gate"]["gateStatus"], "CITATION_VERIFIED")
        self.assertEqual(entry["gate"]["faceSha256"], "a" * 64)
        self.assertEqual(entry["gate"]["asOf"], "20261016")
        self.assertEqual(entry["citations"][0]["citationText"],
                         "《中华人民共和国个人信息保护法》第一条")
        self.assertEqual(entry["provenance"]["textSha256"], "b" * 64)

    def test_unverified_candidate_refused(self) -> None:
        self._patch_candidate(synth_stamp_view("UNVERIFIED"))
        with self.assertRaises(NotConnected) as caught:
            tabular_review.tabular_call("tabular.support_stamp",
                                        self.stamp_args, CONFIG)
        self.assertIn("tabular_stamp_requires_gated_candidate",
                      str(caught.exception))
        self.assertEqual(self.recorded, [])

    def test_missing_page_sha_refused(self) -> None:
        view = synth_stamp_view()
        view["provenance"] = {"source": "material_extraction",
                              "doc": "synth_doc", "page": 3}
        self._patch_candidate(view)
        with self.assertRaises(NotConnected) as caught:
            tabular_review.tabular_call("tabular.support_stamp",
                                        self.stamp_args, CONFIG)
        self.assertIn("tabular_stamp_requires_page_sha256",
                      str(caught.exception))

    def test_missing_face_pin_refused(self) -> None:
        config = dict(CONFIG)
        config.pop("codices_face_sha256")
        with self.assertRaises(NotConnected) as caught:
            tabular_review.tabular_call("tabular.support_stamp",
                                        self.stamp_args, config)
        self.assertIn("tabular_stamp_face_pin_required",
                      str(caught.exception))

    def test_extra_fields_refused(self) -> None:
        args = dict(self.stamp_args, gate_status="CITATION_VERIFIED")
        with self.assertRaises(NotConnected) as caught:
            tabular_review.tabular_call("tabular.support_stamp", args,
                                        CONFIG)
        self.assertIn("tabular_stamp_args_invalid", str(caught.exception))


class GoldMatchTests(unittest.TestCase):
    """列三元组投影的 goldMatch 确定性对照（Decimal 纪律）。"""

    def test_number_match_with_units_and_thousands(self) -> None:
        self.assertTrue(tabular_review._gold_match(
            {"kind": "number", "expect": "123456.78"},
            "合同金额 123,456.78 元")["goldMatch"])
        self.assertFalse(tabular_review._gold_match(
            {"kind": "number", "expect": "999.00"}, "123,456.78 元")[
                "goldMatch"])

    def test_typed_golds(self) -> None:
        self.assertTrue(tabular_review._gold_match(
            {"kind": "text", "expect": "三十日"}, "三十日")["goldMatch"])
        self.assertTrue(tabular_review._gold_match(
            {"kind": "enum", "expect": ["有", "无"]}, "有")["goldMatch"])
        self.assertFalse(tabular_review._gold_match(
            {"kind": "enum", "expect": ["有", "无"]}, "部分")["goldMatch"])
        self.assertTrue(tabular_review._gold_match(
            {"kind": "boolean", "expect": True}, True)["goldMatch"])
        self.assertTrue(tabular_review._gold_match(
            {"kind": "date", "expect": "2026-10-16"}, " 2026-10-16 ")[
                "goldMatch"])

    def test_not_comparable_and_unparseable(self) -> None:
        self.assertIsNone(tabular_review._gold_match(
            {"kind": "none"}, "任意")["goldMatch"])
        self.assertIsNone(tabular_review._gold_match(
            {"kind": "number"}, "42")["goldMatch"])
        self.assertFalse(tabular_review._gold_match(
            {"kind": "number", "expect": "42.00"}, "无数字文本")[
                "goldMatch"])
        self.assertFalse(tabular_review._gold_match(
            {"kind": "text", "expect": "x"}, None)["goldMatch"])


class ReadProjectionTests(unittest.TestCase):
    """tabular.read：列三元组投影（列名/金标/值＋支持状态）。"""

    def test_read_joins_contract_values_support(self) -> None:
        def _harness(method, args, config):
            if method == "harness.review_columns_read":
                return {"defined": True, "columns": [
                    {"id": "amount", "name": "合同金额",
                     "format": "decimal-string", "version": "1",
                     "gold": {"kind": "number", "expect": "123456.78"}}]}
            if method == "harness.review_batch_read":
                if args.get("row_id"):
                    return {"status": "active", "row": {
                        "id": args["row_id"], "state": "done", "cells": {
                            "amount": {"value": "123,456.78 元",
                                       "generation": 1,
                                       "source": "machine"}}}}
                return {"status": "active", "rows": [
                    {"id": "row-1", "state": "done"}]}
            return {"counts": {"SUPPORTED_CITATION_LEVEL": 1},
                    "projections": [
                        {"rowId": "row-1", "cellId": "amount",
                         "supportStatus": "SUPPORTED_CITATION_LEVEL"}]}
        patcher = unittest.mock.patch.object(tabular_review, "_harness_call",
                                             _harness)
        patcher.start()
        self.addCleanup(patcher.stop)
        result = tabular_review.tabular_call(
            "tabular.read", {"review_batch_id": "brt-synth",
                             "scope": SCOPE}, CONFIG)
        triple = result["rows"][0]["cells"][0]
        self.assertEqual(triple["columnName"], "合同金额")
        self.assertEqual(triple["gold"], {"kind": "number",
                                          "expect": "123456.78"})
        self.assertEqual(triple["value"], "123,456.78 元")
        self.assertEqual(triple["cellSource"], "machine")
        self.assertEqual(triple["supportStatus"],
                         "SUPPORTED_CITATION_LEVEL")
        self.assertTrue(triple["goldMatch"])


class InvalidateTests(unittest.TestCase):
    """tabular.invalidate：薄透传＋理由闭集。"""

    def test_invalidate_passthrough(self) -> None:
        recorded: list[dict] = []

        def _harness(method, args, config):
            recorded.append({"method": method, "args": args})
            return {"reason": args["reason"]}
        patcher = unittest.mock.patch.object(tabular_review, "_harness_call",
                                             _harness)
        patcher.start()
        self.addCleanup(patcher.stop)
        result = tabular_review.tabular_call("tabular.invalidate", {
            "review_batch_id": "brt-synth", "row_id": "row-1",
            "cell_id": "amount", "reason": "source_version_stale",
            "detail": "页字节变化", "actor_id": "auditor-1",
            "scope": SCOPE, "key": command_key("inv-1")}, CONFIG)
        self.assertEqual(result["reason"], "source_version_stale")
        self.assertEqual(recorded[0]["method"],
                         "harness.review_support_invalidate")

    def test_invalidate_reason_closed(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            tabular_review.tabular_call("tabular.invalidate", {
                "review_batch_id": "brt-synth", "row_id": "row-1",
                "cell_id": "amount", "reason": "lawyer_changed_mind",
                "actor_id": "a", "scope": SCOPE,
                "key": command_key("inv-x")}, CONFIG)
        self.assertIn("tabular_invalidate_reason_invalid",
                      str(caught.exception))


class AuditTests(unittest.TestCase):
    """tabular.audit：溯源两端（材料侧 sha＋页内；法规侧同面复验）。"""

    def setUp(self) -> None:
        import tempfile
        self.temporary = tempfile.TemporaryDirectory(prefix="f82-audit-")
        self.addCleanup(self.temporary.cleanup)
        corpus = Path(self.temporary.name)
        page_dir = corpus / "synth_doc"
        page_dir.mkdir(parents=True)
        self.page_text = "第三条 付款约定：合同总价 123,456.78 元。依据" \
                         "《中华人民共和国个人信息保护法》第一条：“…”。"
        (page_dir / "page-3.txt").write_text(self.page_text, encoding="utf-8")
        self.config = dict(CONFIG)
        self.config["tabular_corpus_root"] = str(corpus)
        self.page_sha = tabular_review.hashlib.sha256(
            self.page_text.encode("utf-8")).hexdigest()
        self.support_read = {
            "entries": {"row-1:amount": [{
                "seq": 1, "entryKind": "support",
                "record": {
                    "entryKind": "support",
                    "cellGeneration": 1,
                    "gate": {"via": "extraction.gate(W2b-U02)",
                             "face": "f", "faceSha256": "a" * 64,
                             "asOf": "20261016", "runSeq": 1,
                             "extractionBatchId": "exb-synth",
                             "candidateId": "cand_0001",
                             "gateStatus": "CITATION_VERIFIED",
                             "rejectionReasons": []},
                    "citations": [{
                        "citationText": "《中华人民共和国个人信息保护法》"
                                       "第一条", "status": "现行",
                        "quoteInArticle": True}],
                    "provenance": {
                        "source": "material_extraction", "doc": "synth_doc",
                        "page": 3, "textSha256": self.page_sha},
                }}]},
        }
        view = synth_stamp_view()

        def _harness(method, args, config):
            assert method == "harness.review_support_read"
            return self.support_read
        patcher = unittest.mock.patch.object(tabular_review, "_harness_call",
                                             _harness)
        patcher.start()
        self.addCleanup(patcher.stop)
        import extraction_gate
        patcher2 = unittest.mock.patch.object(
            extraction_gate, "candidate_read",
            lambda args, config: view)
        patcher2.start()
        self.addCleanup(patcher2.stop)
        # 法规侧复验同面 mock（真法源复验在 recon 全链跑）。
        import citation_verifier
        patcher3 = unittest.mock.patch.object(
            citation_verifier, "parse_citations",
            lambda text: [{"citation_text": "《中华人民共和国个人信息保护"
                                           "法》第一条", "title": "合成"}])
        patcher3.start()
        self.addCleanup(patcher3.stop)
        replay_record = {"citation_text": "《中华人民共和国个人信息保护法》"
                                         "第一条", "status": "现行",
                         "verified_scoped": True,
                         "support": {"quote_in_article": True}}
        patcher4 = unittest.mock.patch.object(
            citation_verifier, "verify_citation",
            lambda parsed, config: replay_record)
        patcher4.start()
        self.addCleanup(patcher4.stop)

    def test_audit_ok(self) -> None:
        result = tabular_review.tabular_call(
            "tabular.audit", {"review_batch_id": "brt-synth",
                              "scope": SCOPE}, self.config)
        self.assertEqual(result["auditStatus"], "AUDIT_OK")
        self.assertEqual(result["sourceTraced"], "1/1")
        self.assertEqual(result["statuteConsistent"], "1/1")
        finding = result["findings"][0]
        self.assertTrue(finding["sourceShaOk"])
        self.assertTrue(finding["citations"][0]["inSourceText"])
        self.assertTrue(finding["statuteReplay"]["consistent"])

    def test_audit_detects_source_drift(self) -> None:
        (Path(self.config["tabular_corpus_root"]) / "synth_doc"
         / "page-3.txt").write_text("页面被改写后的内容", encoding="utf-8")
        result = tabular_review.tabular_call(
            "tabular.audit", {"review_batch_id": "brt-synth",
                              "scope": SCOPE}, self.config)
        self.assertEqual(result["auditStatus"], "AUDIT_FAIL")
        self.assertFalse(result["findings"][0]["sourceShaOk"])
        self.assertFalse(result["findings"][0]["citations"][0]
                         ["inSourceText"])

    def test_audit_requires_corpus_config(self) -> None:
        config = dict(self.config)
        config.pop("tabular_corpus_root")
        with self.assertRaises(NotConnected) as caught:
            tabular_review.tabular_call(
                "tabular.audit", {"review_batch_id": "brt-synth",
                                  "scope": SCOPE}, config)
        self.assertIn("tabular_corpus_root_not_configured",
                      str(caught.exception))


class LateCodePassThroughTests(unittest.TestCase):
    """harness 面码经桥透传（迟到/冲突码不吞不改）。"""

    def test_typed_codes_surface_through_bridge(self) -> None:
        for code in ("review_columns_conflict:brt-synth",
                     "columns_not_frozen:brt-synth:extra=:missing=cited",
                     "review_invalidation_no_support:amount"):
            with self.subTest(code=code):
                patch_execute(self, stdout=json.dumps({
                    "surface": "reviewbatch", "error": code}), returncode=1)
                with self.assertRaisesRegex(HarnessCommandError,
                                            code.split(":")[0]):
                    legal_entry.call("harness.review_columns_define", {
                        "actor_id": "lawyer-1", "scope": SCOPE,
                        "key": command_key("rc-1"), "batch_id": "brt-synth",
                        "columns": []}, CONFIG)


if __name__ == "__main__":
    unittest.main()
