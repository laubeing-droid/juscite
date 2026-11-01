"""F118 产品侧接线测试（W1-U07）：legal_entry F118 方法组＋调度器通知闭环。

全部合成材料：subprocess seam 注入（不真起 harness 进程，单测零网络零仓依赖）；
真 harness public_entry 的实跑对账在 tools/f118_schedule_loop_recon.py（合成
状态根+合成 matter，git 只读）。fail-closed 纪律：未配置桥＝NOT_CONNECTED，
绝不空响应冒成功。
"""

from __future__ import annotations

import importlib
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
import f118_scheduler  # noqa: E402

CONFIG = {
    "harness_public_entry": "X:/synth/harness/public_entry.py",
    "harness_target": "opencode",
    "harness_state_root": "X:/synth/state-root",
    "harness_python": sys.executable,
}
SCOPE_ARGS = {"scope": {"kind": "matter", "matterId": "m-f118"},
              "query": {"asOf": "2026-10-15", "asAt": "2026-10-15T01:00:00Z"}}


def fake_entry_output(surface, result):
    return json.dumps({"surface": surface, "method": "synthetic", "result": result})


def patch_execute(testcase, *, stdout="", returncode=0, calls=None, error=None):
    def _fake(argv, env, timeout):
        if calls is not None:
            calls.append({"argv": argv, "env": env})
        if error is not None:
            raise error
        class _Proc:
            pass
        proc = _Proc()
        proc.stdout, proc.returncode = stdout, returncode
        return proc
    testcase.patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
    testcase.patcher.start()
    testcase.addCleanup(testcase.patcher.stop)


class F118BridgeTests(unittest.TestCase):
    """legal_entry F118 方法组：白名单分发、fail-closed、信封分离。"""

    def test_schedule_methods_whitelisted_and_use_schedule_envelope(self) -> None:
        calls: list[dict] = []
        envelopes: list[dict] = []

        def _capture(argv, env, timeout):
            calls.append({"argv": argv, "env": env})
            envelopes.append(json.loads(
                Path(argv[argv.index("--schedule-json") + 1]).read_text(encoding="utf-8")))
            return SimpleNamespace(stdout=fake_entry_output("schedule", {"items": []}),
                                   returncode=0)

        patcher = unittest.mock.patch.object(legal_entry, "_execute", _capture)
        patcher.start(); self.addCleanup(patcher.stop)
        result = legal_entry.call("harness.schedule_list", SCOPE_ARGS, CONFIG)
        self.assertEqual(result, {"items": []})
        argv = calls[0]["argv"]
        self.assertIn("--schedule-json", argv)
        self.assertNotIn("--goal-json", argv)
        self.assertIn("--target", argv)
        self.assertIn("opencode", argv)
        self.assertEqual(envelopes[0]["method"], "harness.schedule_list")
        self.assertEqual(envelopes[0]["params"], SCOPE_ARGS)
        env = calls[0]["env"]
        self.assertEqual(env.get("LH_LEGAL_STATE_ROOT"), "X:/synth/state-root")

    def test_goal_methods_still_use_goal_envelope(self) -> None:
        calls: list[dict] = []
        patch_execute(self, stdout=fake_entry_output("goal", {"goal": {}}), calls=calls)
        legal_entry.call("harness.list_goals", {"scope": SCOPE_ARGS["scope"]}, CONFIG)
        self.assertIn("--goal-json", calls[0]["argv"])
        self.assertNotIn("--schedule-json", calls[0]["argv"])

    def test_unconfigured_bridge_fails_closed_not_connected(self) -> None:
        for missing in ("harness_public_entry", "harness_target"):
            config = dict(CONFIG)
            del config[missing]
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call("harness.schedule_event",
                                 {"scope": SCOPE_ARGS["scope"]}, config)
            self.assertIn(f"{missing}_not_configured", str(caught.exception))

    def test_unknown_method_fails_closed(self) -> None:
        with self.assertRaises(NotConnected) as caught:
            legal_entry.call("harness.schedule_delete", {}, CONFIG)
        self.assertIn("method_not_connected", str(caught.exception))

    def test_wrong_surface_and_ledger_error_fail_closed(self) -> None:
        # surface 不匹配（如误走 goal 信封）＝协议拒绝，不冒成功。
        patch_execute(self, stdout=fake_entry_output("goal", {"items": []}))
        with self.assertRaises(HarnessCommandError):
            legal_entry.call("harness.schedule_list", SCOPE_ARGS, CONFIG)
        # ledger 打回（UnitsError code）＝HARNESS_FAIL 语义。
        patch_execute(self, stdout=json.dumps(
            {"status": "FAIL", "error": "schedule_anchor_not_found:pe-x:1"}),
            returncode=1)
        with self.assertRaises(HarnessCommandError) as caught:
            legal_entry.call("harness.schedule_event", {}, CONFIG)
        self.assertIn("schedule_anchor_not_found", str(caught.exception))

    def test_cli_envelope_owner_response(self) -> None:
        # CLI 端到端信封：schedule 结果照 OWNER_RESPONSE 出（与 goal 同款）。
        calls: list[dict] = []
        envelopes: list[dict] = []

        def _capture(argv, env, timeout):
            calls.append({"argv": argv})
            envelopes.append(json.loads(
                Path(argv[argv.index("--schedule-json") + 1]).read_text(encoding="utf-8")))
            return SimpleNamespace(stdout=fake_entry_output("schedule", {"ref": {"id": "s1"}}),
                                   returncode=0)

        patcher = unittest.mock.patch.object(legal_entry, "_execute", _capture)
        patcher.start(); self.addCleanup(patcher.stop)
        result = legal_entry.call("harness.schedule_cancel",
                                  {"scope": SCOPE_ARGS["scope"]}, CONFIG)
        self.assertEqual(result["ref"]["id"], "s1")
        self.assertEqual(envelopes[0]["method"], "harness.schedule_cancel")


class SchedulerTests(unittest.TestCase):
    """f118_scheduler：通知载荷封闭、送达语义、报告闭环与拒绝路径。"""

    DUE = {
        "reminderId": "rem-1", "taskId": "sched-1-task", "taskStates": ["accepted"],
        "deadlineId": "sched-1", "classification": "program_deadline",
        "title": "上诉期届满（合成）", "dueDate": "2026-10-18",
        "scheduledAt": "2026-10-15T00:30:00Z", "channel": "desktop", "state": "pending",
    }

    def listing(self, due=(DUE,)):
        return fake_entry_output("schedule", {
            "asOf": "2026-10-15", "asAt": "2026-10-15T01:00:00Z",
            "dueDesktopReminders": list(due), "counts": {"dueDesktopReminders": len(due)},
        })

    def test_notification_payload_closed_and_countdown_labels(self) -> None:
        import datetime as dt

        class _FakeDate:
            @staticmethod
            def today():
                return dt.date(2026, 10, 15)

            fromisoformat = staticmethod(dt.date.fromisoformat)

        real_date = f118_scheduler.date
        f118_scheduler.date = _FakeDate
        self.addCleanup(setattr, f118_scheduler, "date", real_date)
        payload = f118_scheduler.build_notification(self.DUE)
        # 字段封闭：只有账面镜像＋日差＋文案。
        self.assertEqual(set(payload), {
            "reminderId", "taskId", "deadlineId", "classification", "title",
            "body", "dueDate", "daysRemaining", "urgent", "channel"})
        self.assertEqual(payload["daysRemaining"], 3)
        self.assertTrue(payload["urgent"])
        self.assertIn("程序期限", payload["body"])
        self.assertIn("还有 3 天", payload["body"])
        overdue = f118_scheduler.build_notification(
            self.DUE | {"dueDate": "2026-10-13"})
        self.assertEqual(overdue["daysRemaining"], -2)
        self.assertTrue(overdue["urgent"])
        self.assertIn("已过期 2 天", overdue["body"])
        today = f118_scheduler.build_notification(self.DUE | {"dueDate": "2026-10-15"})
        self.assertIn("今日到期", today["body"])

    def test_dispatch_and_report_closes_the_loop(self) -> None:
        calls: list[dict] = []
        outputs = [self.listing(), fake_entry_output("schedule", {"state": "sent"})]
        def _fake(argv, env, timeout):
            calls.append({"method": json.loads(
                Path(argv[argv.index("--schedule-json") + 1]).read_text(encoding="utf-8"))["method"],
                "params": json.loads(
                Path(argv[argv.index("--schedule-json") + 1]).read_text(encoding="utf-8"))["params"]})
            class _Proc: pass
            proc = _Proc(); proc.returncode = 0
            proc.stdout = outputs[len(calls) - 1]
            return proc
        patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
        patcher.start(); self.addCleanup(patcher.stop)
        receipts: list[str] = []
        round_result = f118_scheduler.dispatch_and_report(
            CONFIG, matter_id="m-f118",
            notifier=lambda p: receipts.append(f"os-notification:{p['reminderId']}") or f"os-notification:{p['reminderId']}",
            now_iso="2026-10-15T01:00:00Z", as_of="2026-10-15")
        self.assertEqual(round_result["dueCount"], 1)
        self.assertEqual(len(round_result["fired"]), 1)
        self.assertEqual(round_result["fired"][0]["outcome"], "sent")
        self.assertEqual(round_result["refused"], [])
        self.assertEqual(receipts, ["os-notification:rem-1"])
        # 第二次调用＝reminder_report，outcome sent，receiptRef 绑系统通知回执。
        self.assertEqual(calls[0]["method"], "harness.schedule_list")
        self.assertEqual(calls[1]["method"], "harness.reminder_report")
        report = calls[1]["params"]
        self.assertEqual(report["report"]["reminderId"], "rem-1")
        self.assertEqual(report["report"]["outcome"], "sent")
        self.assertEqual(report["report"]["receiptRef"], "os-notification:rem-1")
        self.assertTrue(report["key"]["requestId"].startswith("f118-rr-rem-1-"))

    def test_notifier_failure_reports_delivery_unknown(self) -> None:
        outputs = [self.listing(), fake_entry_output("schedule", {"state": "delivery_unknown"})]
        counter = []
        def _fake(argv, env, timeout):
            counter.append(1)
            class _Proc: pass
            proc = _Proc(); proc.returncode = 0
            proc.stdout = outputs[len(counter) - 1]
            return proc
        patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
        patcher.start(); self.addCleanup(patcher.stop)
        def broken_notifier(payload):
            raise RuntimeError("synthetic electron failure")
        result = f118_scheduler.dispatch_and_report(
            CONFIG, matter_id="m-f118", notifier=broken_notifier,
            now_iso="2026-10-15T01:00:00Z", as_of="2026-10-15")
        self.assertEqual(result["fired"][0]["outcome"], "delivery_unknown")
        self.assertIn("notifier-failed", result["fired"][0]["receipt"])

    def test_report_channel_failure_leaves_pending_and_records_refused(self) -> None:
        outputs = [self.listing(),
                   json.dumps({"status": "FAIL", "error": "reminder_already_reported:rem-1"})]
        counter = []
        def _fake(argv, env, timeout):
            counter.append(1)
            class _Proc: pass
            proc = _Proc(); proc.returncode = 1 if len(counter) == 2 else 0
            proc.stdout = outputs[len(counter) - 1]
            return proc
        patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
        patcher.start(); self.addCleanup(patcher.stop)
        result = f118_scheduler.dispatch_and_report(
            CONFIG, matter_id="m-f118",
            notifier=lambda p: "os-ok",
            now_iso="2026-10-15T01:00:00Z", as_of="2026-10-15")
        self.assertEqual(result["fired"], [])
        self.assertEqual(len(result["refused"]), 1)
        self.assertEqual(result["refused"][0]["reminderId"], "rem-1")
        self.assertIn("reminder_already_reported", result["refused"][0]["error"])

    def test_no_due_reminders_is_clean_noop(self) -> None:
        outputs = [self.listing(due=())]
        counter = []
        def _fake(argv, env, timeout):
            counter.append(1)
            class _Proc: pass
            proc = _Proc(); proc.returncode = 0
            proc.stdout = outputs[len(counter) - 1]
            return proc
        patcher = unittest.mock.patch.object(legal_entry, "_execute", _fake)
        patcher.start(); self.addCleanup(patcher.stop)
        result = f118_scheduler.dispatch_and_report(
            CONFIG, matter_id="m-f118",
            now_iso="2026-10-15T01:00:00Z", as_of="2026-10-15")
        self.assertEqual(result, {"matterId": "m-f118", "fired": [], "refused": [],
                                  "dueCount": 0})
        self.assertEqual(len(counter), 1)  # 只读不写

    def test_unconfigured_bridge_raises_not_connected(self) -> None:
        with self.assertRaises(NotConnected):
            f118_scheduler.due_notifications({}, matter_id="m-f118")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
