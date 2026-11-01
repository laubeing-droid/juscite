"""F114 产品侧接线测试（W2a-U06）：版本来源合同 P04 方法组。

全部合成材料。legal_entry 的 HARNESS_MATERIAL_METHODS 组扩入 P04 三方法
（propose_materials/decide_materials/withdraw_material），与 F08 四方法同
走 --materials-json 封闭信封（subprocess seam 注入，单测零仓依赖；真
public_entry 全链实跑对账在 tools/PENDING_OWNER_f114_version_sources_recon.py）。
fail-closed：未配置桥＝NOT_CONNECTED，绝不空响应冒成功。

合同要点（harness docs/f114-version-source-contract.md）：五 source 枚举＝
真版本来源不互换伪装；user_accept/reject 只出自 decide_materials 真实决定；
文件字节可回读。桥只路由不解释——来源真值校验全部在 harness 公开面。
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
SCOPE = {"kind": "matter", "matterId": "m-f114"}
DOC_B64 = base64.b64encode(
    "委托代理合同（F114 合成材料）。\n".encode("utf-8")).decode("ascii")


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


def command_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def material_ref(version: str) -> dict:
    return {"owner": "harness", "kind": "material", "id": "mat-f114",
            "version": version, "matterId": "m-f114"}


def decision(action: str, suffix: str) -> dict:
    return {
        "action": action,
        "reasonRef": {"owner": "harness", "kind": "reason",
                      "id": f"r-f114-{suffix}", "version": "1",
                      "matterId": "m-f114"},
        "receiptRef": {"owner": "harness", "kind": "receipt",
                       "id": f"rc-f114-{suffix}", "version": "1",
                       "matterId": "m-f114"},
    }


class F114P04BridgeTests(unittest.TestCase):
    """legal_entry P04 三方法：白名单、materials 信封、fail-closed。"""

    def test_p04_methods_whitelisted_use_materials_envelope(self) -> None:
        cases = (
            ("harness.propose_materials",
             {"actor_id": "lawyer-1", "scope": SCOPE,
              "key": command_key("pm-1"),
              "bundle_ref": {"owner": "harness", "kind": "sanitized-bundle",
                             "id": "b-1", "version": "1"},
              "manifest_ref": {"owner": "harness", "kind": "source-manifest",
                               "id": "sm-1", "version": "1"}}),
            ("harness.decide_materials",
             {"actor_id": "lawyer-1", "scope": SCOPE,
              "key": command_key("dm-1"),
              "material_refs": [material_ref("2")],
              "decision": decision("accept", "w")}),
            ("harness.withdraw_material",
             {"actor_id": "lawyer-1", "scope": SCOPE,
              "key": command_key("wm-1"),
              "material_ref": material_ref("3"),
              "decision": decision("withdraw", "w")}),
        )
        for method, params in cases:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--materials-json") + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_entry_output("materials",
                                                 {"receipt": "synthetic"}),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, params, CONFIG)
                self.assertEqual(result, {"receipt": "synthetic"})
                argv = captured[0]["argv"]
                self.assertIn("--materials-json", argv)
                self.assertNotIn("--goal-json", argv)
                self.assertNotIn("--schedule-json", argv)
                self.assertIn("opencode", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)
                self.assertEqual(envelope["params"], params)

    def test_f08_methods_still_ride_same_envelope(self) -> None:
        calls: list[dict] = []
        patch_execute(self, stdout=fake_entry_output("materials", {}),
                      calls=calls)
        legal_entry.call("harness.read_material",
                         {"scope": SCOPE, "material_id": "mat-f114"}, CONFIG)
        self.assertIn("--materials-json", calls[0]["argv"])

    def test_version_source_disguise_surfaces_typed_code(self) -> None:
        # 伪装负向经桥透传：harness 面 material_source_not_writable 原样
        # 上浮（桥不吞不改，typed code 冒 HarnessCommandError）。
        patch_execute(self, stdout=json.dumps({
            "surface": "materials",
            "error": "material_source_not_writable:user_accept"}),
            returncode=1)
        with self.assertRaisesRegex(HarnessCommandError,
                                    "material_source_not_writable"):
            legal_entry.call("harness.add_material_revision", {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": command_key("ar-1"),
                "revision": {"materialId": "mat-f114", "bytesB64": DOC_B64,
                             "source": "user_accept"}}, CONFIG)

    def test_unconfigured_and_unknown_fail_closed(self) -> None:
        with self.assertRaisesRegex(NotConnected,
                                    "harness_public_entry_not_configured"):
            legal_entry.call("harness.decide_materials",
                             {"scope": SCOPE}, {})
        with self.assertRaisesRegex(NotConnected, "method_not_connected"):
            legal_entry.call("harness.material_set_source",
                             {"scope": SCOPE}, CONFIG)
        with self.assertRaisesRegex(NotConnected, "harness_params_invalid"):
            legal_entry.call("harness.propose_materials", ["not-a-dict"],
                             CONFIG)

    def test_method_group_membership(self) -> None:
        # P04 三方法与 F08 四方法同组同信封；改来源的伪方法不入组。
        self.assertEqual(
            legal_entry.HARNESS_MATERIAL_METHODS,
            frozenset({
                "harness.register_material",
                "harness.add_material_revision",
                "harness.read_material", "harness.list_materials",
                "harness.propose_materials", "harness.decide_materials",
                "harness.withdraw_material",
            }))


if __name__ == "__main__":
    unittest.main()
