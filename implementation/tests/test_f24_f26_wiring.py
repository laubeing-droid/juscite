# -*- coding: utf-8 -*-
"""W3-U03 / F24+F26 acceptance: run ledger owner + tool governance wiring.

06 F24「durable run 事件表（幂等键+事件溯源+乐观锁+SSE cursor）」acceptance
「所选核心Session与Harness业务run/goal各唯一owner；Host只有投影/游标/批准
恢复元数据，同键重放异内容拒绝，不另造业务终局」＋06 F26「工具治理（读写
分区双闸/执行档位/白名单+skill 黑名单）」acceptance「未广告/未授权工具不
能调用；读写区、执行权限、黑白名单后端强制」：

* legal_entry 新增 HARNESS_RUN_LEDGER_METHODS（四方法，--runledger-json 信
  封）与 HARNESS_TOOL_GOVERNANCE_METHODS（三方法，--toolgov-json 信封），
  与既有方法组互斥、组外方法结构性不在；宿主自造终局方法（run_host_finalize
  形态）绝不入组——Host 不另造业务终局；
* fail-closed：未配置桥＝NOT_CONNECTED（exit 3 具名），账面 typed 码
  （run_event_key_conflict / tool_governance_deny_by_default_required 等）
  经 HarnessCommandError 原样上浮，绝不空响应冒成功；
* Host 侧 run_cursor_store（f24-runhost/1）：只存 session 引用/游标/批准
  恢复元数据三类；goal 内容键与业务终局键任何层级禁入（fail-closed）；
  游标单调（回退拒不采纳）；批准按 (runId,decision,decisionRef) 幂等去重
  （宿主不产生第二业务账）；模块公开面无终局写入 API（AST 断言）。

全部合成材料；真 public_entry 全链与活服务负测对账在
tools/PENDING_OWNER_f24_f26_owner_permission_recon.py（desktop=产品桥
SQLite 子进程全链／selfhost=PgMatterStore 直连 lh-pg-e08）。
"""
from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import HarnessCommandError, NotConnected  # noqa: E402
from run_cursor_store import (  # noqa: E402
    GOAL_CONTENT_KEYS,
    TERMINAL_FORBIDDEN_KEYS,
    RunCursorStore,
    RunCursorStoreError,
)

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
RUN_LEDGER_METHODS = (
    "harness.run_event_append", "harness.run_events_read",
    "harness.run_projection_read", "harness.run_list",
)
TOOL_GOVERNANCE_METHODS = (
    "harness.tool_governance_register", "harness.tool_governance_read",
    "harness.tool_governance_decide",
)


def fake_entry_output(surface, result):
    return json.dumps({"surface": surface, "method": "synthetic",
                       "result": result})


def patch_execute(testcase, *, stdout="", returncode=0, calls=None):
    def _fake(argv, env, timeout):
        if calls is not None:
            calls.append({"argv": argv, "env": env})
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
    patcher.start()
    testcase.addCleanup(patcher.stop)


class F24F26BridgeTests(unittest.TestCase):
    """legal_entry 两组七方法：白名单、信封、fail-closed。"""

    def test_method_groups_frozen_and_disjoint(self) -> None:
        self.assertEqual(legal_entry.HARNESS_RUN_LEDGER_METHODS,
                         frozenset(RUN_LEDGER_METHODS))
        self.assertEqual(legal_entry.HARNESS_TOOL_GOVERNANCE_METHODS,
                         frozenset(TOOL_GOVERNANCE_METHODS))
        # 宿主自造终局/第二账方法结构性不在组（Host 只有投影/游标/批准
        # 恢复元数据——终局唯一来源是 owner 链 terminal_results）。
        self.assertNotIn("harness.run_host_finalize",
                         legal_entry.HARNESS_RUN_LEDGER_METHODS)
        self.assertNotIn("harness.run_terminal_mint",
                         legal_entry.HARNESS_RUN_LEDGER_METHODS)
        self.assertNotIn("harness.run_second_ledger_write",
                         legal_entry.HARNESS_RUN_LEDGER_METHODS)
        # 与既有 harness 方法组两两互斥（同方法不得双信封路由）。
        groups = [
            legal_entry.HARNESS_GOAL_METHODS,
            legal_entry.HARNESS_STRATEGY_METHODS,
            legal_entry.HARNESS_VOI_METHODS,
            legal_entry.HARNESS_SCHEDULE_METHODS,
            legal_entry.HARNESS_MATERIAL_METHODS,
            legal_entry.HARNESS_BATCH_REVIEW_METHODS,
            legal_entry.HARNESS_FORMAL_PROPOSAL_METHODS,
            legal_entry.HARNESS_PATH_EVIDENCE_METHODS,
            legal_entry.HARNESS_TABULAR_METHODS,
            legal_entry.HARNESS_REVIEW_OPS_METHODS,
            legal_entry.HARNESS_EVIDENCE_ATTEMPT_METHODS,
            legal_entry.HARNESS_CASH_METHODS,
            legal_entry.HARNESS_RUN_LEDGER_METHODS,
            legal_entry.HARNESS_TOOL_GOVERNANCE_METHODS,
        ]
        seen: set = set()
        for group in groups:
            self.assertFalse(group & seen,
                             f"group overlap: {sorted(group & seen)}")
            seen |= group
        # E07 goal 账（T16）仍然冻结在原组——owner 唯一的 goal 侧权威不动。
        self.assertIn("harness.save_goal", legal_entry.HARNESS_GOAL_METHODS)

    def test_run_ledger_methods_ride_runledger_envelope(self) -> None:
        for method in RUN_LEDGER_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout, _c=captured):
                    _c.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--runledger-json") + 1]
                        ).read_text(encoding="utf-8")),
                        "env": dict(env)})
                    return SimpleNamespace(
                        stdout=fake_entry_output("runledger",
                                                 {"ok": True}),
                        returncode=0)
                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                args = {"scope": {"kind": "matter", "matterId": "m-f24"}}
                if method == "harness.run_event_append":
                    args["event"] = {"runId": "run-x", "eventKey": "k1",
                                     "eventCode": "run.progress",
                                     "payload": {}, "expectedHeadSeq": None,
                                     "terminalReceiptRef": None}
                legal_entry.call(method, args, dict(CONFIG))
                self.assertEqual(len(captured), 1)
                ride = captured[0]
                self.assertIn("--runledger-json", ride["argv"])
                self.assertEqual(
                    ride["envelope"],
                    {"method": method, "params": args})
                # 状态根经 LH_LEGAL_STATE_ROOT 环境通道进入子进程。
                self.assertEqual(ride["env"].get("LH_LEGAL_STATE_ROOT"),
                                 "X:/synth/state-root")

    def test_governance_methods_ride_toolgov_envelope(self) -> None:
        for method in TOOL_GOVERNANCE_METHODS:
            with self.subTest(method=method):
                captured: list[dict] = []

                def _capture(argv, env, timeout, _c=captured):
                    _c.append({
                        "argv": list(argv),
                        "envelope": json.loads(Path(
                            argv[argv.index("--toolgov-json") + 1]
                        ).read_text(encoding="utf-8"))})
                    return SimpleNamespace(
                        stdout=fake_entry_output("toolgov",
                                                 {"verdict": "deny"}),
                        returncode=0)
                patcher = unittest.mock.patch.object(legal_entry, "_execute",
                                                     _capture)
                patcher.start()
                self.addCleanup(patcher.stop)
                args = {"scope": {"kind": "matter", "matterId": "m-f26"},
                        "governance_id": "gov-x"}
                legal_entry.call(method, args, dict(CONFIG))
                self.assertEqual(len(captured), 1)
                ride = captured[0]
                self.assertIn("--toolgov-json", ride["argv"])
                self.assertEqual(
                    ride["envelope"], {"method": method, "params": args})

    def test_unconfigured_bridge_fails_closed(self) -> None:
        for method in ("harness.run_list", "harness.tool_governance_decide"):
            with self.subTest(method=method):
                with tempfile.TemporaryDirectory() as tmp:
                    request = Path(tmp) / "request.json"
                    config = Path(tmp) / "config.json"
                    request.write_text(json.dumps(
                        {"method": method, "args": {"scope": {
                            "kind": "matter", "matterId": "m-f24"}}},
                        ensure_ascii=False), encoding="utf-8")
                    config.write_text("{}", encoding="utf-8")
                    import subprocess
                    proc = subprocess.run(
                        [sys.executable, "-X", "utf8",
                         str(ROOT / "python" / "legal_entry.py"),
                         "--request-json", str(request),
                         "--config", str(config)],
                        capture_output=True, text=True, encoding="utf-8",
                        timeout=120)
                self.assertEqual(proc.returncode, 3)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload.get("status"), "NOT_CONNECTED")
                self.assertIn("harness_public_entry_not_configured",
                              str(payload.get("code", "")))

    def test_ledger_typed_error_surfaces(self) -> None:
        # 账面 typed 码（同键重放异内容拒）经信封原样上浮，不洗白。
        calls: list[dict] = []
        patch_execute(self,
                      stdout=json.dumps({"status": "FAIL",
                                         "error": "run_event_key_conflict:k1"}),
                      returncode=1, calls=calls)
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call(
                "harness.run_event_append",
                {"scope": {"kind": "matter", "matterId": "m-f24"},
                 "event": {"runId": "run-x", "eventKey": "k1",
                           "eventCode": "run.progress", "payload": {},
                           "expectedHeadSeq": None,
                           "terminalReceiptRef": None}},
                dict(CONFIG))
        self.assertIn("run_event_key_conflict", str(caught.exception))
        # 伪结果（surface 不符）拒不采纳。
        patch_execute(self,
                      stdout=fake_entry_output("voi", {"ok": True}),
                      returncode=0)
        with self.assertRaises(HarnessCommandError):
            legal_entry.call("harness.run_list",
                             {"scope": {"kind": "matter",
                                        "matterId": "m-f24"}},
                             dict(CONFIG))


class RunCursorStoreTests(unittest.TestCase):
    """Host 侧存储：三类元数据、禁入键、游标单调、批准幂等、零终局 API。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = RunCursorStore(Path(self.tmp.name) / "run-host.json")

    def test_cursor_monotonic_and_replay(self) -> None:
        first = self.store.update_cursor("run-x", 3, "2026-10-18T00:00:00Z")
        self.assertIsNone(first["previous"])
        self.assertEqual(self.store.read_cursor("run-x"), 3)
        replay = self.store.update_cursor("run-x", 3, "2026-10-18T00:00:01Z")
        self.assertEqual(replay["previous"], 3)
        advance = self.store.update_cursor("run-x", 7,
                                           "2026-10-18T00:00:02Z")
        self.assertEqual(advance["previous"], 3)
        self.assertEqual(self.store.read_cursor("run-x"), 7)
        with self.assertRaises(RunCursorStoreError) as caught:
            self.store.update_cursor("run-x", 5, "2026-10-18T00:00:03Z")
        self.assertIn("run_host_cursor_regressed", str(caught.exception))

    def test_approval_idempotent_dedup(self) -> None:
        first = self.store.record_approval("run-x", "approved",
                                           "rcpt-1", "2026-10-18T00:00:00Z")
        self.assertFalse(first["replayed"])
        replay = self.store.record_approval("run-x", "approved",
                                            "rcpt-1",
                                            "2026-10-18T00:00:00Z")
        self.assertTrue(replay["replayed"])
        self.assertEqual(replay["approvalCount"], first["approvalCount"])
        self.store.record_approval("run-x", "resumed", "rcpt-2",
                                   "2026-10-18T00:00:05Z")
        self.assertEqual(self.store.load()["approvals"],
                         [{"runId": "run-x", "decision": "approved",
                           "decisionRef": "rcpt-1",
                           "decidedAt": "2026-10-18T00:00:00Z"},
                          {"runId": "run-x", "decision": "resumed",
                           "decisionRef": "rcpt-2",
                           "decidedAt": "2026-10-18T00:00:05Z"}])
        with self.assertRaises(RunCursorStoreError) as caught:
            self.store.record_approval("run-x", "finalized", "rcpt-3",
                                       "2026-10-18T00:00:06Z")
        self.assertIn("run_host_approval_invalid", str(caught.exception))

    def test_session_ref_replay(self) -> None:
        first = self.store.record_session_ref("m-f24", "ses_synth_1")
        self.assertFalse(first["replayed"])
        replay = self.store.record_session_ref("m-f24", "ses_synth_1")
        self.assertTrue(replay["replayed"])
        changed = self.store.record_session_ref("m-f24", "ses_synth_2")
        self.assertEqual(changed["previous"], "ses_synth_1")

    def test_goal_content_and_terminal_fields_structurally_refused(self) -> None:
        self.assertIn("confirmedScope", GOAL_CONTENT_KEYS)
        self.assertIn("terminalResult", TERMINAL_FORBIDDEN_KEYS)
        # 载荷任何层级带 goal 内容/终局字段＝具名拒（写盘前 fail-closed）。
        bad_cursor = {
            "schema": "f24-runhost/1", "sessionRefs": {},
            "runCursors": {"run-x": {"headSeq": 1, "updatedAt": "t",
                                     "terminalResult": {"verdict": "win"}}},
            "approvals": []}
        with self.assertRaises(RunCursorStoreError) as caught:
            self.store.save(bad_cursor)
        self.assertIn("run_host_terminal_field_forbidden", str(caught.exception))
        bad_approval = {
            "schema": "f24-runhost/1", "sessionRefs": {},
            "runCursors": {},
            "approvals": [{"runId": "run-x", "decision": "approved",
                           "decisionRef": "r", "decidedAt": "t",
                           "confirmedScope": "宿主自拟范围＝第二 goal 账"}]}
        with self.assertRaises(RunCursorStoreError) as caught_goal:
            self.store.save(bad_approval)
        self.assertIn("run_host_goal_content_forbidden", str(caught_goal.exception))
        # 落盘态（经由合法 API 的）回读不含任何禁入键。
        self.store.record_session_ref("m-f24", "ses_synth_1")
        self.store.update_cursor("run-x", 1, "t")
        self.store.record_approval("run-x", "approved", "rcpt-1", "t")
        state = self.store.load()
        self.assertEqual(state["schema"], "f24-runhost/1")

    def test_store_shape_closed_and_module_has_no_terminal_api(self) -> None:
        with self.assertRaises(RunCursorStoreError) as caught:
            self.store.save({"schema": "f24-runhost/1", "sessionRefs": {},
                             "runCursors": {}, "approvals": [],
                             "businessLedger": {}})
        self.assertIn("run_host_store_fields_not_closed", str(caught.exception))
        # AST 断言：模块公开函数面＝封闭三类，没有任何终局写入 API。
        source = (ROOT / "python" / "run_cursor_store.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        top_functions: set = set()
        methods: set = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                top_functions.add(node.name)
            if isinstance(node, ast.ClassDef) and node.name == "RunCursorStore":
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef,
                                         ast.AsyncFunctionDef)):
                        methods.add(item.name)
        self.assertEqual(top_functions, {"_guard_metadata"})
        self.assertEqual(
            methods,
            {"__init__", "load", "save", "record_session_ref",
             "update_cursor", "read_cursor", "record_approval"})
        for forbidden in ("finalize", "terminal_write", "mint", "set_status"):
            self.assertFalse(
                any(forbidden in name for name in methods | top_functions),
                f"host store must not expose a {forbidden} API")


if __name__ == "__main__":
    unittest.main()
