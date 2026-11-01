"""F05 协作面产品侧接线测试（W4-U31）：org 邀请/直授/分享 token/弃权档案。

全部合成材料。legal_entry 新增 HARNESS_COLLAB_METHODS 十一方法组，走
--collab-json 封闭信封（subprocess seam 注入，单测零仓依赖；真
public_entry 全链＋PG 直连对账在 tools/PENDING_OWNER_f05_collaboration_
recon.py）。fail-closed：未配置桥＝NOT_CONNECTED（具名），绝不空响应冒
成功。

合同要点（harness docs/f05-collab-surface-contract.md）：「邀请/直授/撤
权按角色落真实权限」＝harness 侧 F04 求值 roster 回落；「旧分享 token
失效且无越权文档」＝成员撤权同事务级联 token revoked＋解析按当下活体权
限求值。桥只路由不解释——求值真值校验全部在 harness 面；本面零出站通
道（无邮件投递/通知方法）。
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
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E401,F401

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
SCOPE = {"kind": "matter", "matterId": "m-f05"}
COLLAB_METHODS = (
    "harness.collab_invite_create", "harness.collab_invite_accept",
    "harness.collab_invite_revoke", "harness.collab_grant_direct",
    "harness.collab_member_revoke", "harness.collab_member_read",
    "harness.collab_share_token_issue", "harness.collab_share_token_resolve",
    "harness.collab_share_token_revoke",
    "harness.collab_upgrade_waiver_record",
    "harness.collab_upgrade_waiver_read",
)


def fake_entry_output(result):
    return json.dumps({"surface": "collab", "method": "synthetic",
                       "result": result})


def command_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


class F05CollabBridgeTests(unittest.TestCase):
    """legal_entry 十一方法：白名单、collab 信封、fail-closed。"""

    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_COLLAB_METHODS,
                         frozenset(COLLAB_METHODS))
        # 伪方法（绕开活体权限求值直放行/直造第二权限通道）不在冻结组。
        for forged in ("harness.collab_member_grant",
                       "harness.collab_token_force_allow",
                       "harness.collab_permission_decide",
                       "harness.collab_send_invite_email"):
            self.assertNotIn(forged, legal_entry.HARNESS_COLLAB_METHODS)
        # 与 F04 管理组两两不交（方法组闭集纪律）。
        self.assertEqual(
            legal_entry.HARNESS_COLLAB_METHODS
            & legal_entry.HARNESS_CASE_PERMISSION_METHODS, frozenset())

    def test_all_methods_ride_collab_envelope(self) -> None:
        args_by_method = {
            "harness.collab_invite_create": {
                "actor_id": "admin-1", "key": command_key("inv-1"),
                "invite": {"inviteId": "inv-1", "orgId": "org-1",
                           "email": "hire@synth.example",
                           "roles": ["paralegal"]}},
            "harness.collab_invite_accept": {
                "actor_id": "hire", "key": command_key("ia-1"),
                "accept": {"inviteToken": "lhinv-x", "userId": "hire"}},
            "harness.collab_invite_revoke": {
                "actor_id": "admin-1", "key": command_key("ir-1"),
                "revoke": {"inviteId": "inv-1"}},
            "harness.collab_grant_direct": {
                "actor_id": "admin-1", "key": command_key("gd-1"),
                "grant": {"orgId": "org-1", "userId": "u1",
                          "email": "u1@synth.example",
                          "roles": ["paralegal"]}},
            "harness.collab_member_revoke": {
                "actor_id": "admin-1", "key": command_key("mr-1"),
                "revoke": {"orgId": "org-1", "userId": "u1"}},
            "harness.collab_member_read": {"org_id": "org-1"},
            "harness.collab_share_token_issue": {
                "actor_id": "admin-1", "scope": SCOPE,
                "key": command_key("ti-1"),
                "token": {"tokenId": "tok-1",
                          "materialId": "mat-f05-doc", "action": "read",
                          "granteeUserId": "u1"}},
            "harness.collab_share_token_resolve": {"token": "lhshk-x"},
            "harness.collab_share_token_revoke": {
                "actor_id": "admin-1", "key": command_key("tr-1"),
                "revoke": {"tokenId": "tok-1"}},
            "harness.collab_upgrade_waiver_record": {
                "actor_id": "admin-1", "key": command_key("wa-1"),
                "waiver": {"waiverId": "waiv-1", "orgId": "org-1",
                           "fromSemantics": "legacy_share_raw_access",
                           "toSemantics": "rbac_live_permission",
                           "changes": ["legacy_share_links_invalidated"],
                           "acknowledgedBy": "org-admin"}},
            "harness.collab_upgrade_waiver_read": {"waiver_id": "waiv-1"},
        }
        for method in COLLAB_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--collab-json") + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_entry_output({"ok": True}),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, args_by_method[method],
                                          CONFIG)
                self.assertEqual(result, {"ok": True})
                argv = captured[0]["argv"]
                self.assertIn("--collab-json", argv)
                for other in ("--caseperm-json", "--materials-json",
                              "--goal-json", "--dashboard-json",
                              "--casedomain-json"):
                    self.assertNotIn(other, argv)
                self.assertIn("opencode", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)
                self.assertEqual(envelope["params"], args_by_method[method])

    def test_typed_codes_surface_through_bridge(self) -> None:
        # F05 acceptance 具名拒经桥透传（harness 面码原样上浮，桥不吞不改）。
        for method, code in (
            ("harness.collab_share_token_resolve",
             "f05_share_token_revoked:member_revoked"),
            ("harness.collab_share_token_resolve",
             "f05_share_token_permission_denied:read:rule"),
            ("harness.collab_invite_accept", "f05_invite_token_revoked:x"),
            ("harness.collab_member_revoke",
             "f05_member_not_active:org-1:u1"),
            ("harness.collab_upgrade_waiver_record",
             "f05_waiver_changes_invalid"),
        ):
            with self.subTest(code=code):
                patcher = unittest.mock.patch.object(
                    legal_entry, "_execute",
                    lambda argv, env, timeout: SimpleNamespace(
                        stdout=json.dumps({"surface": "collab",
                                           "error": code}),
                        returncode=1))
                patcher.start()
                self.addCleanup(patcher.stop)
                kwargs = {"token": "lhshk-x"} \
                    if method.endswith("resolve") else {}
                with self.assertRaisesRegex(HarnessCommandError,
                                            code.split(":")[0]):
                    legal_entry.call(method, kwargs, CONFIG)

    def test_unconfigured_and_unknown_fail_closed(self) -> None:
        calls: list = []
        patcher = unittest.mock.patch.object(
            legal_entry, "_execute",
            lambda argv, env, timeout: calls.append(argv)
            or SimpleNamespace(stdout=fake_entry_output({}), returncode=0))
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaisesRegex(NotConnected,
                                    "harness_public_entry_not_configured"):
            legal_entry.call("harness.collab_member_read",
                             {"org_id": "org-1"}, {})
        with self.assertRaisesRegex(NotConnected,
                                    "harness_target_not_configured"):
            legal_entry.call("harness.collab_member_read",
                             {"org_id": "org-1"},
                             {"harness_public_entry": "X:/synth/e.py"})
        with self.assertRaisesRegex(NotConnected, "method_not_connected"):
            legal_entry.call("harness.collab_send_invite_email",
                             {"org_id": "org-1"}, CONFIG)
        with self.assertRaisesRegex(NotConnected, "harness_params_invalid"):
            legal_entry.call("harness.collab_member_read",
                             ["not-a-dict"], CONFIG)
        self.assertEqual(calls, [])

    def test_no_outbound_channel_in_group(self) -> None:
        """本面零出站通道（E24 分离不变量同纪律）：任何 email/notify/
        send/smtp 形态方法结构性不在组。"""
        for method in legal_entry.HARNESS_COLLAB_METHODS:
            lowered = method.lower()
            for forbidden in ("email", "notify", "send", "smtp", "push"):
                if forbidden == "send":
                    # collab_send_* 已被上测钉死不在组；组内成员名不含。
                    self.assertNotIn("send", lowered)
                else:
                    self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
