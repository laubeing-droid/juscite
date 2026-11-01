"""F04/F92 产品侧接线测试（W3-U07）：案件权限方法组。

全部合成材料。legal_entry 新增 HARNESS_CASE_PERMISSION_METHODS 四方法组，
走 --caseperm-json 封闭信封（subprocess seam 注入，单测零仓依赖；真
public_entry 全链＋PG 直连对账在
tools/PENDING_OWNER_f04_f92_permission_recon.py）。fail-closed：未配置
桥＝NOT_CONNECTED（exit 3 具名），绝不空响应冒成功。

合同要点（harness docs/f04-f92-case-permission-contract.md）：优先级语义
按 f9-permission-precedence.md（T18 已 VERIFIED）账本落点——role→org→user
段序末条胜出＋org veto 只压 deny 永不放行＋规则段 deny 短路 veto＋受管案
无匹配 fail-closed；撤权立即生效（四类门逐操作同事务读账）；review 可见
不自动得文档读权。桥只路由不解释——求值真值校验全部在 harness 面。
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
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E401

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
SCOPE = {"kind": "matter", "matterId": "m-f04"}
CASEPERM_METHODS = (
    "harness.case_member_declare", "harness.case_permission_rule",
    "harness.case_permission_veto", "harness.case_permission_read",
)


def fake_entry_output(result):
    return json.dumps({"surface": "caseperm", "method": "synthetic",
                       "result": result})


def command_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


class F04F92BridgeTests(unittest.TestCase):
    """legal_entry 四方法：白名单、caseperm 信封、fail-closed。"""

    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_CASE_PERMISSION_METHODS,
                         frozenset(CASEPERM_METHODS))
        # 伪方法（绕开管理门直改账/直改生效判定）不在冻结组。
        for forged in ("harness.case_permission_set",
                       "harness.case_permission_grant",
                       "harness.case_permission_decide",
                       "harness.case_permission_require"):
            self.assertNotIn(forged,
                             legal_entry.HARNESS_CASE_PERMISSION_METHODS)
        # 四类门不注册独立方法：读/写/事件流/导出在各既有公开面内验权
        # （不建第二执行通道）。
        for gate in ("harness.case_permission_check",
                     "harness.case_gate_read"):
            self.assertNotIn(gate,
                             legal_entry.HARNESS_CASE_PERMISSION_METHODS)

    def test_all_methods_ride_caseperm_envelope(self) -> None:
        args_by_method = {
            "harness.case_member_declare": {
                "actor_id": "admin-1", "scope": SCOPE,
                "key": command_key("mb-1"),
                "members": [{"userId": "u1", "orgId": "org-1",
                             "roles": ["paralegal"]}]},
            "harness.case_permission_rule": {
                "actor_id": "admin-1", "scope": SCOPE,
                "key": command_key("rl-1"),
                "rules": [{"principalKind": "user", "principalId": "u1",
                           "action": "read", "effect": "allow"}]},
            "harness.case_permission_veto": {
                "actor_id": "admin-1", "scope": SCOPE,
                "key": command_key("vt-1"),
                "vetoes": [{"orgId": "org-2", "action": "export",
                            "status": "ACTIVE"}]},
            "harness.case_permission_read": {
                "scope": SCOPE, "actor_id": "u1"},
        }
        for method in CASEPERM_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--caseperm-json") + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_entry_output({"managed": True}),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, args_by_method[method],
                                          CONFIG)
                self.assertEqual(result, {"managed": True})
                argv = captured[0]["argv"]
                self.assertIn("--caseperm-json", argv)
                for other in ("--materials-json", "--goal-json",
                              "--schedule-json", "--reviewbatch-json",
                              "--runledger-json", "--toolgov-json",
                              "--caseanchor-json"):
                    self.assertNotIn(other, argv)
                self.assertIn("opencode", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)
                self.assertEqual(envelope["params"], args_by_method[method])

    def test_typed_codes_surface_through_bridge(self) -> None:
        # 合同面具名拒（优先级归因段/匿名拒/武装后无 manage/veto 状态机）
        # 经桥透传（harness 面码原样上浮，桥不吞不改）。
        for method, code in (
            ("harness.case_permission_rule",
             "case_permission_denied:manage:default"),
            ("harness.case_member_declare",
             "case_permission_denied:manage:membership"),
            ("harness.case_permission_veto",
             "case_veto_not_active:org-2:read"),
            ("harness.case_permission_read",
             "case_permission_actor_required"),
        ):
            with self.subTest(code=code):
                patcher = unittest.mock.patch.object(
                    legal_entry, "_execute",
                    lambda argv, env, timeout: SimpleNamespace(
                        stdout=json.dumps({"surface": "caseperm",
                                           "error": code}),
                        returncode=1))
                patcher.start()
                self.addCleanup(patcher.stop)
                with self.assertRaisesRegex(HarnessCommandError,
                                            code.split(":")[0]):
                    legal_entry.call(method, {"scope": SCOPE}, CONFIG)

    def test_unconfigured_and_unknown_fail_closed(self) -> None:
        calls: list[dict] = []
        patcher = unittest.mock.patch.object(
            legal_entry, "_execute",
            lambda argv, env, timeout: calls.append(argv)
            or SimpleNamespace(stdout=fake_entry_output({}), returncode=0))
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaisesRegex(NotConnected,
                                    "harness_public_entry_not_configured"):
            legal_entry.call("harness.case_member_declare",
                             {"scope": SCOPE}, {})
        with self.assertRaisesRegex(NotConnected,
                                    "harness_target_not_configured"):
            legal_entry.call("harness.case_member_declare",
                             {"scope": SCOPE},
                             {"harness_public_entry": "X:/synth/entry.py"})
        with self.assertRaisesRegex(NotConnected, "method_not_connected"):
            legal_entry.call("harness.case_permission_set",
                             {"scope": SCOPE}, CONFIG)
        with self.assertRaisesRegex(NotConnected, "harness_params_invalid"):
            legal_entry.call("harness.case_permission_read",
                             ["not-a-dict"], CONFIG)
        self.assertEqual(calls, [])

    def test_protocol_invalid_never_surfaces_stderr(self) -> None:
        patcher = unittest.mock.patch.object(
            legal_entry, "_execute",
            lambda argv, env, timeout: SimpleNamespace(stdout="not-json",
                                                       returncode=1))
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaisesRegex(HarnessCommandError,
                                    "harness_entry_protocol_invalid"):
            legal_entry.call("harness.case_permission_read",
                             {"scope": SCOPE}, CONFIG)


if __name__ == "__main__":
    unittest.main()
