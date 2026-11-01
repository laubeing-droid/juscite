"""F117/F124 产品侧接线测试（W3-U08）：任务/待办＋散件文档方法组。

全部合成材料。legal_entry 新增 HARNESS_TASK_METHODS 五方法（--tasks-json
信封）与 HARNESS_LOOSE_DOC_METHODS 六方法（--loosedocs-json 信封），走同
一封闭 public_entry provider dispatch（subprocess seam 注入，单测零仓依
赖；真 public_entry 全链＋PG 直连对账在
tools/PENDING_OWNER_f117_f124_todo_loose_recon.py）。fail-closed：未配置
桥＝NOT_CONNECTED，绝不空响应冒成功。

合同要点（harness docs/f117-f124-todo-loose-contract.md）：建议不是任务
——采用才落 derived_tasks 既有账（不造第二任务账）；完成必带终局 owner
（_REF_OWNERS 闭集）与结果绑定；散件三账 matter-less（零案号合法的结
构面）；归案＝同一事务（F113 锚点＋F08 材料链 revision 1＋散件冻结），
归案后版本演进唯一走 F08/F114。桥只路由不解释——真值校验全部在 harness
面。
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
SCOPE = {"kind": "matter", "matterId": "m-f117f124"}
TASK_METHODS = (
    "tasks.suggest", "tasks.proposal_decide", "tasks.proposal_list",
    "tasks.list", "tasks.decide",
)
LOOSE_METHODS = (
    "harness.loose_register", "harness.loose_add_revision",
    "harness.loose_record_review", "harness.loose_read",
    "harness.loose_list", "harness.loose_file",
)


def fake_entry_output(result, surface="tasks"):
    return json.dumps({"surface": surface, "method": "synthetic",
                       "result": result})


def command_key(request_id: str) -> dict:
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


class F117F124BridgeTests(unittest.TestCase):
    """legal_entry 两组方法：白名单、tasks/loosedocs 信封、fail-closed。"""

    def test_method_group_membership(self) -> None:
        self.assertEqual(legal_entry.HARNESS_TASK_METHODS,
                         frozenset(TASK_METHODS))
        self.assertEqual(legal_entry.HARNESS_LOOSE_DOC_METHODS,
                         frozenset(LOOSE_METHODS))
        # 伪方法（第二任务账直写/绕过采用落账/散件状态直改/第二归案通道）
        # 不在冻结组。
        for forged in ("tasks.insert", "tasks.complete",
                       "tasks.proposal_adopt", "harness.loose_attach",
                       "harness.loose_set_state", "harness.loose_import"):
            self.assertNotIn(forged, legal_entry.HARNESS_TASK_METHODS)
            self.assertNotIn(forged, legal_entry.HARNESS_LOOSE_DOC_METHODS)

    def test_task_methods_ride_tasks_envelope(self) -> None:
        args_by_method = {
            "tasks.suggest": {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": command_key("ts-1"),
                "proposal": {"proposalId": "prop-1", "title": "起草催告函",
                             "originKind": "path_candidate",
                             "originRef": {"owner": "harness",
                                           "kind": "path_candidate",
                                           "id": "cand-1", "version": "1",
                                           "matterId": "m-f117f124"}}},
            "tasks.proposal_decide": {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": command_key("tp-1"),
                "decision": {"proposalId": "prop-1", "action": "adopt",
                             "reasonRef": {"owner": "host",
                                           "kind": "decision-receipt",
                                           "id": "r1", "version": "1"},
                             "receiptRef": {"owner": "host",
                                            "kind": "decision-receipt",
                                            "id": "rc1", "version": "1"}}},
            "tasks.proposal_list": {"scope": SCOPE},
            "tasks.list": {"scope": SCOPE, "cursor": None},
            "tasks.decide": {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": command_key("td-1"),
                "task_ref": {"id": "task-prop-1"},
                "decision": {"action": "complete",
                             "reasonRef": {"owner": "host",
                                           "kind": "decision-receipt",
                                           "id": "r2", "version": "1"},
                             "receiptRef": {"owner": "host",
                                            "kind": "decision-receipt",
                                            "id": "rc2", "version": "1"},
                             "finalOwner": "harness",
                             "resultRefs": [{"owner": "harness",
                                             "kind": "path_candidate",
                                             "id": "cand-1", "version": "1",
                                             "matterId": "m-f117f124"}]}},
        }
        for method in TASK_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--tasks-json") + 1]
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
                self.assertIn("--tasks-json", argv)
                for other in ("--materials-json", "--goal-json",
                              "--schedule-json", "--reviewbatch-json",
                              "--caseanchor-json", "--caseperm-json",
                              "--loosedocs-json"):
                    self.assertNotIn(other, argv)
                self.assertIn("opencode", argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)
                self.assertEqual(envelope["params"], args_by_method[method])

    def test_loose_methods_ride_loosedocs_envelope(self) -> None:
        args_by_method = {
            "harness.loose_register": {
                "key": command_key("lr-1"),
                "doc": {"looseId": "loose-1", "title": "散件（合成）",
                        "bytesB64": "6ZmQ5rG9", "source": "upload"}},
            "harness.loose_add_revision": {
                "key": command_key("lv-1"),
                "revision": {"looseId": "loose-1", "bytesB64": "6ZmQ5rG9",
                             "source": "assistant_edit",
                             "baseRevision": 1}},
            "harness.loose_record_review": {
                "key": command_key("lrv-1"),
                "review": {"looseId": "loose-1", "reviewId": "lrev-1",
                           "revision": 1, "reviewKind": "citation_check",
                           "review": {"citations": 1}}},
            "harness.loose_read": {"loose_id": "loose-1"},
            "harness.loose_list": {"state": None},
            "harness.loose_file": {
                "actor_id": "lawyer-1", "scope": SCOPE,
                "key": command_key("lf-1"),
                "filing": {"looseId": "loose-1", "materialId": "mat-1",
                           "materialKind": "digital_text"}},
        }
        for method in LOOSE_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout):
                    captured.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--loosedocs-json") + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_entry_output({"ok": True},
                                                 surface="loosedocs"),
                        returncode=0)

                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                result = legal_entry.call(method, args_by_method[method],
                                          CONFIG)
                self.assertEqual(result, {"ok": True})
                argv = captured[0]["argv"]
                self.assertIn("--loosedocs-json", argv)
                for other in ("--tasks-json", "--materials-json",
                              "--goal-json", "--caseanchor-json",
                              "--caseperm-json"):
                    self.assertNotIn(other, argv)
                envelope = captured[0]["envelope"]
                self.assertEqual(envelope["method"], method)
                self.assertEqual(envelope["params"], args_by_method[method])

    def test_surface_mismatch_refused(self) -> None:
        # 信封面各立：tasks 面的调用拿不到 loosedocs 面（surface 闭集）。
        patcher = unittest.mock.patch.object(
            legal_entry, "_execute",
            lambda argv, env, timeout: SimpleNamespace(
                stdout=fake_entry_output({"ok": True}, surface="loosedocs"),
                returncode=0))
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(HarnessCommandError):
            legal_entry.call("tasks.list", {"scope": SCOPE}, CONFIG)

    def test_typed_codes_surface_through_bridge(self) -> None:
        # 合同面具名拒（origin 不回账/无绑定完成/终局后再决定/散件已归案）
        # 经桥透传（harness 面码原样上浮，桥不吞不改）。
        for method, code in (
            ("tasks.suggest",
             "task_origin_ref_not_found:path_candidate:nope"),
            ("tasks.decide", "task_final_owner_invalid"),
            ("tasks.decide", "task_state_terminal"),
            ("harness.loose_add_revision", "loose_already_filed"),
            ("harness.loose_file", "loose_already_filed"),
            ("harness.loose_add_revision",
             "loose_source_not_writable:user_accept"),
        ):
            with self.subTest(code=code):
                surface = "tasks" if method.startswith("tasks.") \
                    else "loosedocs"
                patcher = unittest.mock.patch.object(
                    legal_entry, "_execute",
                    lambda argv, env, timeout, code=code, surface=surface:
                    SimpleNamespace(
                        stdout=json.dumps({"surface": surface,
                                           "error": code}),
                        returncode=1))
                patcher.start()
                self.addCleanup(patcher.stop)
                args: dict = {"scope": SCOPE}
                if method == "tasks.decide":
                    args = {"scope": SCOPE, "task_ref": {"id": "t-1"},
                            "key": command_key("neg-1"),
                            "decision": {"action": "complete"}}
                elif method == "tasks.suggest":
                    args = {"scope": SCOPE, "key": command_key("neg-2"),
                            "proposal": {"proposalId": "p", "title": "x",
                                         "originKind": "path_candidate",
                                         "originRef": {}}}
                elif method.startswith("harness.loose"):
                    args = {"key": command_key("neg-3"),
                            "revision": {"looseId": "loose-1",
                                         "bytesB64": "6ZmQ"},
                            "filing": {"looseId": "loose-1",
                                       "materialId": "m",
                                       "materialKind": "digital_text"}}
                with self.assertRaisesRegex(HarnessCommandError,
                                            code.split(":")[0]):
                    legal_entry.call(method, args, CONFIG)

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
            legal_entry.call("tasks.suggest", {"scope": SCOPE}, {})
        with self.assertRaisesRegex(NotConnected,
                                    "harness_target_not_configured"):
            legal_entry.call("harness.loose_read", {"loose_id": "l-1"},
                             {"harness_public_entry": "X:/synth/entry.py"})
        with self.assertRaisesRegex(NotConnected, "method_not_connected"):
            legal_entry.call("tasks.create", {"scope": SCOPE}, CONFIG)
        with self.assertRaisesRegex(NotConnected, "method_not_connected"):
            legal_entry.call("harness.loose_import", {}, CONFIG)
        with self.assertRaisesRegex(NotConnected, "harness_params_invalid"):
            legal_entry.call("tasks.list", ["not-a-dict"], CONFIG)
        with self.assertRaisesRegex(NotConnected, "harness_params_invalid"):
            legal_entry.call("harness.loose_file", "not-a-dict", CONFIG)
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
            legal_entry.call("tasks.list", {"scope": SCOPE}, CONFIG)
        with self.assertRaisesRegex(HarnessCommandError,
                                    "harness_entry_protocol_invalid"):
            legal_entry.call("harness.loose_read", {"loose_id": "l-1"},
                             CONFIG)


if __name__ == "__main__":
    unittest.main()
