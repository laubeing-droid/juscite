"""F08/F09 产品侧接线测试（W2a-U05）：材料真源桥＋覆盖层桥。

全部合成材料。F08 面：legal_entry 四方法组经 --materials-json 封闭信封分发
（subprocess seam 注入，单测零仓依赖；真 public_entry 实跑对账在
tools/PENDING_OWNER_f08_f09_store_recon.py）。F09 面：material.overlay_* 同
进程进 anonymizer overlay_service（原件与身份映射不出 anonymizer——桥响应
剥离 originalPath，只回摘要绑定与 revision 链）。fail-closed：未配置桥＝
NOT_CONNECTED，绝不空响应冒成功。
"""

from __future__ import annotations

import base64
import json
import sys
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E402

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
SCOPE = {"kind": "matter", "matterId": "m-f08"}
DOC_B64 = base64.b64encode("委托代理合同（F08 合成材料）。\n".encode("utf-8")).decode("ascii")


def fake_entry_output(surface, result):
    return json.dumps({"surface": surface, "method": "synthetic", "result": result})


def patch_execute(testcase, *, stdout="", returncode=0, calls=None):
    def _fake(argv, env, timeout):
        if calls is not None:
            calls.append({"argv": argv, "env": env})
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
    patcher.start()
    testcase.addCleanup(patcher.stop)


class F08BridgeTests(unittest.TestCase):
    """legal_entry F08 方法组：白名单分发、信封分离、fail-closed。"""

    def test_four_methods_whitelisted_use_materials_envelope(self) -> None:
        for method, extra in (
            ("harness.register_material",
             {"actor_id": "lawyer-1", "scope": SCOPE,
              "key": {"requestId": "rm-1", "targetId": None,
                      "expectedRevision": None, "inputRefs": []},
              "material": {"id": "mat-1", "kind": "digital_text",
                           "title": "合成", "bytesB64": DOC_B64}}),
            ("harness.add_material_revision",
             {"actor_id": "lawyer-1", "scope": SCOPE,
              "key": {"requestId": "ar-1", "targetId": None,
                      "expectedRevision": None, "inputRefs": []},
              "revision": {"materialId": "mat-1", "bytesB64": DOC_B64}}),
            ("harness.read_material",
             {"scope": SCOPE, "material_id": "mat-1"}),
            ("harness.list_materials", {"scope": SCOPE}),
        ):
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv), "env": dict(env),
                        "envelope": json.loads(Path(
                            argv[argv.index("--materials-json") + 1]).read_text(
                                encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_entry_output("materials", {"revision": 1}),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, extra, CONFIG)
                self.assertEqual(result, {"revision": 1})
                argv = captured[0]["argv"]
                self.assertIn("--materials-json", argv)
                self.assertNotIn("--goal-json", argv)
                self.assertNotIn("--schedule-json", argv)
                self.assertIn("opencode", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)
                self.assertEqual(envelope["params"], extra)
                self.assertEqual(captured[0]["env"].get("LH_LEGAL_STATE_ROOT"),
                                 "X:/synth/state-root")

    def test_materials_never_ride_goal_or_schedule_envelope(self) -> None:
        calls: list[dict] = []
        patch_execute(self, stdout=fake_entry_output("goal", {}),
                      calls=calls)
        legal_entry.call("harness.list_goals", {"scope": SCOPE}, CONFIG)
        self.assertIn("--goal-json", calls[0]["argv"])
        self.assertNotIn("--materials-json", calls[0]["argv"])

    def test_ledger_error_surfaces_typed_code(self) -> None:
        patch_execute(self, stdout=json.dumps(
            {"surface": "materials", "error": "material_not_found:mat-x"}),
            returncode=1)
        with self.assertRaisesRegex(HarnessCommandError,
                                    "material_not_found"):
            legal_entry.call("harness.read_material",
                             {"scope": SCOPE, "material_id": "mat-x"}, CONFIG)

    def test_unconfigured_and_unknown_fail_closed(self) -> None:
        with self.assertRaisesRegex(NotConnected,
                                    "harness_public_entry_not_configured"):
            legal_entry.call("harness.list_materials", {"scope": SCOPE}, {})
        with self.assertRaisesRegex(NotConnected,
                                    "method_not_connected"):
            legal_entry.call("harness.material_delete", {"scope": SCOPE}, CONFIG)
        with self.assertRaisesRegex(NotConnected, "harness_params_invalid"):
            legal_entry.call("harness.read_material", ["not-a-dict"], CONFIG)


SYN_ORIGINAL = (
    "委托代理合同（合成材料）。\n"
    "委托人：周测敏（测试用合成身份，身份证11010119900307867X）。\n"
    "代理费123,456.78元，2026年10月15日签订于北京市海淀区。\n"
)


class F09OverlayBridgeTests(unittest.TestCase):
    """material.overlay_* 同进程面：真 anonymizer overlay_service＋合成件。"""

    def setUp(self) -> None:
        import tempfile

        from legal_anonymizer.config import Config
        from legal_anonymizer.pipeline import deidentify

        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        original = self.root / "originals" / "contract.txt"
        original.parent.mkdir(parents=True)
        original.write_text(SYN_ORIGINAL, encoding="utf-8")
        self.original = original
        self.sanitized = deidentify(
            SYN_ORIGINAL, Config(use_llm=False, critic=False,
                                 policy="balanced", locale="zh")).text
        self.config = {"anonymizer_contract": "p09/p10",
                       "overlay_state_root": str(self.root / "overlay-state")}

    def test_register_apply_read_chain(self) -> None:
        registered = legal_entry.call("material.overlay_register", {
            "matterId": "m-f09", "documentId": "doc-1",
            "original_path": str(self.original),
            "sanitized_text": self.sanitized}, self.config)
        self.assertEqual(registered["revision"], 1)
        self.assertEqual(registered["origin"], "pipeline")
        self.assertNotIn("originalPath", registered)
        start = self.sanitized.index("周测敏")
        second = legal_entry.call("material.overlay_apply", {
            "matterId": "m-f09", "documentId": "doc-1",
            "user_overrides": [
                {"op": "redact_span", "start": start,
                 "end": start + len("周测敏"), "replacement": "PERSON_1"}]},
            self.config)
        self.assertEqual(second["revision"], 2)
        self.assertEqual(second["baseRevision"], 1)
        old = legal_entry.call("material.overlay_read", {
            "matterId": "m-f09", "documentId": "doc-1", "revision": 1},
            self.config)
        new = legal_entry.call("material.overlay_read", {
            "matterId": "m-f09", "documentId": "doc-1", "revision": 2},
            self.config)
        self.assertEqual(old["text"], self.sanitized)
        self.assertIn("PERSON_1", new["text"])
        self.assertNotIn("originalPath", new["record"])
        listing = legal_entry.call("material.overlay_list", {
            "matterId": "m-f09", "documentId": "doc-1"}, self.config)
        self.assertEqual(listing["currentRevision"], 2)
        self.assertEqual([r["revision"] for r in listing["revisions"]], [1, 2])

    def test_failures_surface_type_only_never_material(self) -> None:
        legal_entry.call("material.overlay_register", {
            "matterId": "m-f09", "documentId": "doc-1",
            "original_path": str(self.original),
            "sanitized_text": self.sanitized}, self.config)
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("material.overlay_apply", {
                "matterId": "m-f09", "documentId": "doc-1",
                "user_overrides": [
                    {"op": "replace_text", "find": "委托人",
                     "replace": "委托人13700009999"}]}, self.config)
        self.assertIn("overlay_introduces_catchable_pii", str(caught.exception))
        self.assertNotIn("13700009999", str(caught.exception))
        # original mutated → typed code, original content never echoed
        self.original.write_text(SYN_ORIGINAL + "\n（被改）", encoding="utf-8")
        with self.assertRaisesRegex(NotConnected, "overlay_original_mutated"):
            legal_entry.call("material.overlay_apply", {
                "matterId": "m-f09", "documentId": "doc-1",
                "user_overrides": [
                    {"op": "replace_text", "find": "委托人",
                     "replace": "委托方"}]}, self.config)

    def test_unconfigured_fail_closed(self) -> None:
        for bad in ({}, {"anonymizer_contract": "p09/p10"},
                    {"anonymizer_contract": None,
                     "overlay_state_root": "X:/synth"}):
            with self.assertRaises(NotConnected):
                legal_entry.call("material.overlay_list", {
                    "matterId": "m-f09", "documentId": "doc-1"}, bad)

    def test_missing_document_fields_refused(self) -> None:
        with self.assertRaisesRegex(NotConnected, "overlay_document_required"):
            legal_entry.call("material.overlay_list", {}, self.config)


if __name__ == "__main__":
    unittest.main()
