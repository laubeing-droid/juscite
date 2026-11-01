"""F141 评论权限合同＋F142 审批流产品侧接线测试（W5-U13）。

全部合成材料。legal_entry 新增三冻结组：HARNESS_COLLABDOC_METHODS 五方
法（P04 save_case_note/start_review_round 零改动复用＋F141 评论三方法）
走 --collabdoc-json 封闭信封；HARNESS_APPROVAL_METHODS 七方法走
--approval-json；HARNESS_FORMAL_LIFECYCLE_METHODS 两方法（P02
prepare_formal/commit_formal）走既有 --prepare-formal-json/
--commit-formal-json 服务信封（请求原样透传——字段闭集合同在 harness
ApplicationService）。subprocess seam 注入，单测零仓依赖；真 public_entry
全链＋PG 直连对账在 tools/PENDING_OWNER_f141_f142_collab_lifecycle_
recon.py。fail-closed：未配置桥＝NOT_CONNECTED（具名），绝不空响应冒成
功；非 JSON stdout（未类型化 FinalizationError traceback）＝
harness_entry_protocol_invalid，绝不假成功。

合同要点（harness docs/f141-f142-collab-lifecycle-contract.md）：
「评论/分享按对象权限及版本，撤销立失效，不越权原件」＝harness 侧 F04
活体 read 门＋版本逐字绑定；「正式文档生命周期/审批采用后实记；v1已有
文件终局不得等v2」＝决定唯一入账通道是显式 decide（免登录审批页只读不
扩权），审批零门控既有 commit_formal 终局路径。桥只路由不解释。
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
SCOPE = {"kind": "matter", "matterId": "m-f141"}
COLLABDOC_METHODS = (
    "harness.start_review_round", "harness.save_case_note",
    "harness.collab_doc_comment_save", "harness.collab_doc_comment_read",
    "harness.collab_doc_comment_shared_read",
)
APPROVAL_METHODS = (
    "harness.formal_approval_open", "harness.formal_approval_page_issue",
    "harness.formal_approval_page_view", "harness.formal_approval_decide",
    "harness.formal_approval_page_revoke", "harness.formal_approval_read",
    "harness.formal_approval_list",
)
FORMAL_LIFECYCLE_METHODS = (
    "harness.prepare_formal", "harness.commit_formal",
)


def command_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def fake_envelope_output(surface: str, result):
    return json.dumps({"surface": surface, "method": "synthetic",
                       "result": result})


class F141F142CollabLifecycleWiringTests(unittest.TestCase):
    """legal_entry 三冻结组：白名单、信封分派、fail-closed。"""

    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_COLLABDOC_METHODS,
                         frozenset(COLLABDOC_METHODS))
        self.assertEqual(legal_entry.HARNESS_APPROVAL_METHODS,
                         frozenset(APPROVAL_METHODS))
        self.assertEqual(legal_entry.HARNESS_FORMAL_LIFECYCLE_METHODS,
                         frozenset(FORMAL_LIFECYCLE_METHODS))
        # 伪方法（绕活体权限求值直放行/免登录页扩权写路径/审批代决/审批
        # 门控既有终局）不在冻结组。
        for forged in ("harness.collab_doc_comment_force_allow",
                       "harness.collab_doc_comment_write",
                       "harness.formal_approval_auto_decide",
                       "harness.formal_approval_decide_on_view",
                       "harness.formal_commit_require_approval",
                       "harness.formal_commit_with_approval"):
            self.assertNotIn(forged, legal_entry.HARNESS_COLLABDOC_METHODS)
            self.assertNotIn(forged, legal_entry.HARNESS_APPROVAL_METHODS)
            self.assertNotIn(
                forged, legal_entry.HARNESS_FORMAL_LIFECYCLE_METHODS)
        # 与 F04/F05 管理组两两不交（方法组闭集纪律）。
        for group in (legal_entry.HARNESS_COLLABDOC_METHODS,
                      legal_entry.HARNESS_APPROVAL_METHODS,
                      legal_entry.HARNESS_FORMAL_LIFECYCLE_METHODS):
            self.assertEqual(
                group & legal_entry.HARNESS_CASE_PERMISSION_METHODS,
                frozenset())
            self.assertEqual(
                group & legal_entry.HARNESS_COLLAB_METHODS, frozenset())

    def test_collabdoc_methods_ride_envelope(self) -> None:
        args_by_method = {
            "harness.start_review_round": {
                "actor_id": "admin-1", "scope": SCOPE,
                "key": command_key("rr-1"),
                "material_refs": [{"owner": "harness", "kind": "material",
                                   "id": "doc-1", "version": "1"}],
                "purpose": "核对批注"},
            "harness.save_case_note": {
                "actor_id": "admin-1", "scope": SCOPE,
                "key": command_key("sn-1"),
                "review_round_ref": {"id": "round-1"},
                "note_ref": {"owner": "harness", "kind": "case-note",
                             "id": "note-1"},
                "source_locations": []},
            "harness.collab_doc_comment_save": {
                "actor_id": "member-1", "scope": SCOPE,
                "key": command_key("cs-1"),
                "comment": {"commentId": "cm-1", "materialId": "doc-1",
                            "revision": 1, "body": "请核对第二段"}},
            "harness.collab_doc_comment_read": {
                "actor_id": "member-1", "scope": SCOPE,
                "material_id": "doc-1", "revision": 1},
            "harness.collab_doc_comment_shared_read": {
                "token": "lhshk-x", "material_id": "doc-1",
                "revision": 1},
        }
        for method in COLLABDOC_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--collabdoc-json") + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_envelope_output("collabdoc",
                                                    {"ok": True}),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, args_by_method[method],
                                          CONFIG)
                self.assertEqual(result, {"ok": True})
                argv = captured[0]["argv"]
                self.assertIn("--collabdoc-json", argv)
                for other in ("--collab-json", "--caseperm-json",
                              "--materials-json", "--approval-json",
                              "--prepare-formal-json",
                              "--commit-formal-json"):
                    self.assertNotIn(other, argv)
                self.assertIn("opencode", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)
                self.assertEqual(envelope["params"], args_by_method[method])

    def test_approval_methods_ride_envelope(self) -> None:
        args_by_method = {
            "harness.formal_approval_open": {
                "actor_id": "admin-1", "scope": SCOPE,
                "key": command_key("ao-1"),
                "request": {"approvalId": "appr-1", "runId": "run-1"}},
            "harness.formal_approval_page_issue": {
                "actor_id": "admin-1", "scope": SCOPE,
                "key": command_key("pg-1"),
                "page": {"pageId": "page-1", "approvalId": "appr-1"}},
            "harness.formal_approval_page_view": {"token": "lhapg-x"},
            "harness.formal_approval_decide": {
                "actor_id": "approver-1", "scope": SCOPE,
                "key": command_key("dc-1"),
                "decision": {"approvalId": "appr-1",
                             "decision": "approved",
                             "decisionRef": "receipt:dc-001"}},
            "harness.formal_approval_page_revoke": {
                "actor_id": "admin-1", "key": command_key("rv-1"),
                "revoke": {"pageId": "page-1"}},
            "harness.formal_approval_read": {
                "actor_id": "admin-1", "scope": SCOPE,
                "approval_id": "appr-1"},
            "harness.formal_approval_list": {
                "actor_id": "admin-1", "scope": SCOPE},
        }
        for method in APPROVAL_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--approval-json") + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_envelope_output("approval",
                                                    {"ok": True}),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, args_by_method[method],
                                          CONFIG)
                self.assertEqual(result, {"ok": True})
                argv = captured[0]["argv"]
                self.assertIn("--approval-json", argv)
                self.assertNotIn("--collabdoc-json", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)
                self.assertEqual(envelope["params"], args_by_method[method])

    def test_formal_lifecycle_rides_p02_service_envelopes(self) -> None:
        """P02 既有服务信封：请求原样透传（无 method/params 包装——字段
        闭集合同在 harness ApplicationService）；响应无 surface 包装，
        status 透传返回。"""
        cases = (
            ("harness.prepare_formal", "--prepare-formal-json", {
                "schema_version": "1.0", "run_id": "run-1",
                "document_type": "complaint",
                "output_name": "synth.docx", "fills_ref": "cas://" + "a" * 64,
                "qc_receipt_refs": ["qc://r1"],
                "forbidden_values": ["张三"]},
             {"status": "NEEDS_FINAL_CHECK", "run_id": "run-1"}),
            ("harness.commit_formal", "--commit-formal-json", {
                "schema_version": "1.0", "run_id": "run-1",
                "forbidden_values": ["张三"]},
             {"status": "PASS", "run_id": "run-1"}),
        )
        for method, flag, request, expected in cases:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "request": json.loads(Path(
                            argv[argv.index(flag) + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=json.dumps(expected, ensure_ascii=False),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, request, CONFIG)
                self.assertEqual(result, expected)
                self.assertIn(flag, captured[0]["argv"])
                self.assertEqual(captured[0]["request"], request)

    def test_state_root_env_propagation(self) -> None:
        seen: list[dict] = []

        def _capture(argv, env, timeout):
            seen.append(dict(env))
            return SimpleNamespace(
                stdout=fake_envelope_output("collabdoc", {"ok": True}),
                returncode=0)

        patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                             _capture)
        patcher.start()
        self.addCleanup(patcher.stop)
        legal_entry.call("harness.collab_doc_comment_read",
                         {"actor_id": "u", "scope": SCOPE,
                          "material_id": "doc-1", "revision": 1}, CONFIG)
        self.assertEqual(seen[0]["LH_LEGAL_STATE_ROOT"],
                         CONFIG["harness_state_root"])

    def test_typed_codes_surface_through_bridge(self) -> None:
        # F141/F142 acceptance 具名拒经桥透传（harness 面码原样上浮，桥
        # 不吞不改）。
        for method, surface, code in (
            ("harness.collab_doc_comment_shared_read", "collabdoc",
             "f141_share_revision_not_granted:2:1"),
            ("harness.collab_doc_comment_shared_read", "collabdoc",
             "f141_share_object_mismatch:doc-other"),
            ("harness.collab_doc_comment_shared_read", "collabdoc",
             "f05_share_token_revoked:member_revoked"),
            ("harness.collab_doc_comment_save", "collabdoc",
             "f141_comment_conflict:cm-1"),
            ("harness.collab_doc_comment_save", "collabdoc",
             "case_permission_denied:read:membership"),
            ("harness.formal_approval_page_view", "approval",
             "f142_page_revoked:manual"),
            ("harness.formal_approval_decide", "approval",
             "f142_approval_already_decided:appr-1:1"),
            ("harness.formal_approval_decide", "approval",
             "case_permission_denied:manage:default"),
            ("harness.formal_approval_open", "approval",
             "f142_preparation_cas_missing:ffffffffffffffff"),
        ):
            with self.subTest(code=code):
                patcher = unittest.mock.patch.object(
                    legal_entry, "_execute",
                    lambda argv, env, timeout, s=surface, c=code:
                        SimpleNamespace(
                            stdout=json.dumps({"surface": s, "error": c}),
                            returncode=1))
                patcher.start()
                self.addCleanup(patcher.stop)
                with self.assertRaises(HarnessCommandError) as caught:
                    legal_entry.call(
                        method, {"token": "lhshk-x"}, CONFIG)
                self.assertIn(code, str(caught.exception))

    def test_fail_closed(self) -> None:
        # 未配置桥＝具名 NOT_CONNECTED（绝不空响应冒成功）。
        for method in ("harness.collab_doc_comment_read",
                       "harness.formal_approval_decide",
                       "harness.prepare_formal"):
            with self.subTest(method=method):
                with self.assertRaises(NotConnected) as caught:
                    legal_entry.call(method, {"token": "x"}, {})
                self.assertIn("harness_public_entry_not_configured",
                              str(caught.exception))
        # 未配置 target＝具名 NOT_CONNECTED。
        partial = {"harness_public_entry": CONFIG["harness_public_entry"]}
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("harness.formal_approval_list",
                             {"actor_id": "u", "scope": SCOPE}, partial)
        self.assertIn("harness_target_not_configured",
                      str(caught.exception))
        # 未知方法（白名单外）＝method_not_connected。
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("harness.formal_approval_force_decide",
                             {"approvalId": "x"}, CONFIG)
        self.assertIn("method_not_connected", str(caught.exception))
        # 非 dict args＝harness_params_invalid。
        for method in ("harness.collab_doc_comment_read",
                       "harness.formal_approval_decide",
                       "harness.prepare_formal"):
            with self.subTest(method=method):
                with self.assertRaises(NotConnected) as caught:
                    legal_entry.call(method, ["not", "a", "dict"], CONFIG)
                self.assertIn("harness_params_invalid",
                              str(caught.exception))
        # 非 JSON stdout（未类型化 traceback）＝协议失效，绝不假成功。
        for surface_flag in ("--collabdoc-json", "--approval-json",
                             "--prepare-formal-json"):
            with self.subTest(flag=surface_flag):
                method = ("harness.collab_doc_comment_read"
                          if surface_flag == "--collabdoc-json"
                          else ("harness.formal_approval_list"
                                if surface_flag == "--approval-json"
                                else "harness.prepare_formal"))
                patcher = unittest.mock.patch.object(
                    legal_entry, "_execute",
                    lambda argv, env, timeout: SimpleNamespace(
                        stdout="Traceback (most recent call last):",
                        returncode=1))
                patcher.start()
                self.addCleanup(patcher.stop)
                with self.assertRaises(HarnessCommandError) as caught:
                    legal_entry.call(method, {"schema_version": "1.0"},
                                     CONFIG)
                self.assertIn("harness_entry_protocol_invalid",
                              str(caught.exception))
        # P02 FAIL 信封（exit 1）＝错误码上浮。
        patcher = unittest.mock.patch.object(
            legal_entry, "_execute",
            lambda argv, env, timeout: SimpleNamespace(
                stdout=json.dumps({"status": "FAIL",
                                   "error": "formal_commit_fields_not_closed"}),
                returncode=1))
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call("harness.commit_formal",
                             {"schema_version": "1.0"}, CONFIG)
        self.assertIn("formal_commit_fields_not_closed",
                      str(caught.exception))


if __name__ == "__main__":
    unittest.main()
