"""F137 定时 Agent 任务接线测试（W5-U12）：legal_entry f137.* 方法组＋产品
侧调度层（时区/授权/失败/停止/幂等/未知）。

全部合成材料：临时状态根＋合成任务字符串＋确定性合成时钟（显式 now 注
入）；单测零网络（runner 一律注入合成回执；真实 opencode 适配器的负向
只打死地址 http://127.0.0.1:1）。17 卡验收向量逐字「v2才启用具体定时任
务，时区/授权/失败/停止/幂等实际验证；不同于v1持续任务故障恢复」逐面
落断言。
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import legal_entry  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
import f137_scheduled_tasks as f137  # noqa: E402
from f137_scheduled_tasks import (  # noqa: E402
    FIRE_FIELDS,
    RUNNER_RECEIPT_FIELDS,
    SCHEMA,
    F137TaskStore,
    ScheduledTaskError,
    iso_utc,
    next_occurrence,
)

AUTH_OK = {"grantId": "grant-1", "authorizedBy": "lawyer-a",
           "authorizedAt": "2026-10-20T00:00:00Z",
           "permissions": {"agent.session.prompt": True}}
DAILY_SH = {"kind": "daily", "tz": "Asia/Shanghai", "at": "09:00"}
CREATED_AT = "2026-10-20T00:30:00Z"


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


class RunnerSpy:
    """合成 runner：记账 fireKey，返回 transport 引用回执（零内容）。"""

    def __init__(self, fail_times: int = 0):
        self.calls: list[str] = []
        self.fail_times = fail_times

    def __call__(self, task_view, fire_key, scheduled_utc):
        self.calls.append(fire_key)
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("synthetic-launch-boom")
        return {"sessionId": "ses_synth_%d" % len(self.calls),
                "messageId": "msg_synth_%d" % len(self.calls),
                "receiptRef": "rcpt:" + fire_key}


def make_store(directory, name="store.json", gate=True) -> F137TaskStore:
    return F137TaskStore(Path(directory) / name, v2_enabled=gate)


def make_task(store: F137TaskStore, task_id="t1", schedule=None) -> dict:
    return store.create_task(
        task_id=task_id, title="合成定时任务",
        schedule=schedule or DAILY_SH,
        action={"kind": "agent.session.prompt", "prompt": "合成指令"},
        authorization=dict(AUTH_OK, grantId="grant-" + task_id),
        now=CREATED_AT, created_by="ui")


class Vectors(unittest.TestCase):
    """确定性合成时钟钉定：时区/夏令时/月末边界。"""

    def test_daily_shanghai_next_day_wall(self) -> None:
        self.assertEqual(iso_utc(next_occurrence(DAILY_SH, utc(
            "2026-01-15T02:00:00Z"))), "2026-01-16T01:00:00Z")

    def test_month_end_last_day_non_leap(self) -> None:
        last = {"kind": "monthly", "tz": "Asia/Shanghai", "at": "09:00",
                "day": "last"}
        for after, expect in [
                ("2026-01-15T02:00:00Z", "2026-01-31T01:00:00Z"),
                ("2026-02-01T00:00:00Z", "2026-02-28T01:00:00Z"),
                ("2026-03-01T00:00:00Z", "2026-03-31T01:00:00Z"),
                ("2026-04-01T00:00:00Z", "2026-04-30T01:00:00Z")]:
            self.assertEqual(
                iso_utc(next_occurrence(last, utc(after))), expect,
                "month-end vector %s" % after)

    def test_monthly_day31_skips_short_months(self) -> None:
        day31 = {"kind": "monthly", "tz": "UTC", "at": "00:00", "day": 31}
        self.assertEqual(iso_utc(next_occurrence(day31, utc(
            "2026-04-01T00:00:00Z"))), "2026-05-31T00:00:00Z")
        self.assertEqual(iso_utc(next_occurrence(day31, utc(
            "2026-02-01T00:00:00Z"))), "2026-03-31T00:00:00Z")

    def test_dst_spring_forward_nonexistent_wall_clamps(self) -> None:
        # 2026-03-08 02:30 在 America/New_York 不存在（02:00→03:00）：
        # clamp 到跳变后即时（墙钟显示 03:30 EDT）＝07:30Z。
        ny = {"kind": "daily", "tz": "America/New_York", "at": "02:30"}
        clamp = next_occurrence(ny, utc("2026-03-07T08:00:00Z"))
        self.assertEqual(iso_utc(clamp), "2026-03-08T07:30:00Z")
        # 之后回到正常偏移（EDT＝UTC-4）。
        self.assertEqual(iso_utc(next_occurrence(ny, clamp)),
                         "2026-03-09T06:30:00Z")

    def test_dst_fall_back_ambiguous_wall_takes_first_fold0(self) -> None:
        # 2026-11-01 01:30 在 America/New_York 出现两次：fold=0 取首现
        # （EDT）＝05:30Z，而非重置后的 06:30Z。
        ny = {"kind": "daily", "tz": "America/New_York", "at": "01:30"}
        self.assertEqual(iso_utc(next_occurrence(ny, utc(
            "2026-10-31T12:00:00Z"))), "2026-11-01T05:30:00Z")

    def test_schedule_guards_named(self) -> None:
        for schedule, code in [
                ({"kind": "hourly", "tz": "UTC", "at": "09:00"},
                 "schedule_kind_unknown"),
                ({"kind": "daily", "tz": "Mars/Olympus", "at": "09:00"},
                 "schedule_timezone_unknown"),
                ({"kind": "daily", "tz": "UTC", "at": "24:00"},
                 "schedule_at_invalid"),
                ({"kind": "weekly", "tz": "UTC", "at": "09:00",
                  "weekday": 7}, "schedule_weekday_invalid"),
                ({"kind": "monthly", "tz": "UTC", "at": "09:00",
                  "day": 32}, "schedule_day_invalid"),
                ({"kind": "daily", "tz": "UTC", "at": "09:00",
                  "extra": 1}, "schedule_field_unknown")]:
            with self.assertRaises(ScheduledTaskError) as caught:
                next_occurrence(schedule, utc(CREATED_AT))
            self.assertIn(code, str(caught.exception), schedule)


class StageGate(unittest.TestCase):
    """「v2才启用具体定时任务」：门关的店零任务可建。"""

    def test_gate_closed_refuses_creation_and_persists_zero_tasks(
            self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp, gate=False)
            with self.assertRaises(ScheduledTaskError) as caught:
                make_task(store)
            self.assertIn("scheduled_tasks_stage_gate_v2_required",
                          str(caught.exception))
            self.assertEqual(store.task_list(), [])
            state = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertIs(state["stageGate"]["v2"], False)

    def test_gate_open_store_records_and_operates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            task = make_task(store)
            self.assertEqual(task["state"], "enabled")
            state = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertIs(state["stageGate"]["v2"], True)

    def test_bridge_face_gate_literal_true_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for bad in (None, False, "true", 1):
                config = {"f137_state_root": str(tmp)}
                if bad is not None:
                    config["f137_v2_scheduled_tasks"] = bad
                with self.assertRaises(NotConnected) as caught:
                    legal_entry.call("f137.task_list", {}, config)
                self.assertIn("f137_stage_gate_v2_required",
                              str(caught.exception))
            config = {"f137_v2_scheduled_tasks": True,
                      "f137_state_root": str(tmp)}
            self.assertEqual(legal_entry.call("f137.task_list", {}, config),
                             {"tasks": []})


class Authorization(unittest.TestCase):
    """「授权＝每任务显式授权建立」：deny-closed 矩阵＋grant 一次性绑定。"""

    def test_missing_authorization_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            with self.assertRaises(ScheduledTaskError) as caught:
                store.create_task(
                    task_id="t1", title="x", schedule=DAILY_SH,
                    action={"kind": "agent.session.prompt", "prompt": "p"},
                    authorization=None, now=CREATED_AT, created_by="ui")
            self.assertIn("task_authorization_required",
                          str(caught.exception))
            self.assertEqual(store.task_list(), [])

    def test_permission_not_literal_true_refused(self) -> None:
        for permissions, code in (
                ({}, "authorization_permissions_required"),
                ({"agent.session.prompt": False},
                 "authorization_permission_not_granted"),
                ({"agent.session.prompt": "true"},
                 "authorization_permission_not_granted"),
                ({"other.tool": True},
                 "authorization_permission_not_granted")):
            with tempfile.TemporaryDirectory() as tmp:
                store = make_store(tmp)
                with self.assertRaises(ScheduledTaskError) as caught:
                    store.create_task(
                        task_id="t1", title="x", schedule=DAILY_SH,
                        action={"kind": "agent.session.prompt",
                                "prompt": "p"},
                        authorization={"grantId": "g",
                                       "authorizedBy": "lawyer-a",
                                       "authorizedAt": CREATED_AT,
                                       "permissions": permissions},
                        now=CREATED_AT, created_by="ui")
                self.assertIn(code, str(caught.exception), permissions)
                self.assertEqual(store.task_list(), [])

    def test_grant_reused_across_tasks_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            store.create_task(
                task_id="t1", title="x", schedule=DAILY_SH,
                action={"kind": "agent.session.prompt", "prompt": "p"},
                authorization=AUTH_OK, now=CREATED_AT, created_by="ui")
            with self.assertRaises(ScheduledTaskError) as caught:
                store.create_task(
                    task_id="t2", title="y", schedule=DAILY_SH,
                    action={"kind": "agent.session.prompt", "prompt": "p"},
                    authorization=AUTH_OK, now=CREATED_AT, created_by="ui")
            self.assertIn("authorization_grant_reused",
                          str(caught.exception))

    def test_authorization_subject_and_grant_id_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            for authorization, code in [
                    ({"grantId": "", "authorizedBy": "a",
                      "authorizedAt": CREATED_AT,
                      "permissions": dict(AUTH_OK["permissions"])},
                     "authorization_grant_id_required"),
                    ({"grantId": "g", "authorizedBy": "",
                      "authorizedAt": CREATED_AT,
                      "permissions": dict(AUTH_OK["permissions"])},
                     "authorization_subject_required")]:
                with self.assertRaises(ScheduledTaskError) as caught:
                    store.create_task(
                        task_id="t1", title="x", schedule=DAILY_SH,
                        action={"kind": "agent.session.prompt",
                                "prompt": "p"},
                        authorization=authorization, now=CREATED_AT,
                        created_by="ui")
                self.assertIn(code, str(caught.exception))

    def test_goal_content_keys_structurally_forbidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            authorization = dict(AUTH_OK)
            authorization["permissions"] = {
                "agent.session.prompt": True, "confirmedScope": {"x": 1}}
            with self.assertRaises(ScheduledTaskError) as caught:
                store.create_task(
                    task_id="t1", title="x", schedule=DAILY_SH,
                    action={"kind": "agent.session.prompt", "prompt": "p"},
                    authorization=authorization, now=CREATED_AT,
                    created_by="ui")
            self.assertIn("task_payload_goal_content_forbidden",
                          str(caught.exception))


class Fire(unittest.TestCase):
    """「失败/停止/幂等实际验证」：fireKey 幂等回执、missed 补跑、取消、
    失败挂起、崩溃未知。"""

    def test_round_fires_once_and_replay_never_double_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            runner = RunnerSpy()
            empty = store.run_due_round(runner=runner, now=CREATED_AT)
            self.assertEqual(empty["fired"], [])
            first = store.run_due_round(runner=runner,
                                        now="2026-10-20T01:30:00Z")
            self.assertEqual([f["fireKey"] for f in first["fired"]],
                             ["t1@2026-10-20T01:00:00Z"])
            self.assertEqual(len(runner.calls), 1)
            replay = store.run_due_round(runner=runner,
                                         now="2026-10-20T01:30:00Z")
            self.assertEqual(replay["fired"], [])
            self.assertEqual(len(runner.calls), 1)
            record = store.fire_record("t1@2026-10-20T01:00:00Z")
            self.assertEqual(record["state"], "enqueued")
            self.assertEqual(record["receiptRef"],
                             "rcpt:t1@2026-10-20T01:00:00Z")

    def test_reopen_replay_still_never_double_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            runner = RunnerSpy()
            store.run_due_round(runner=runner, now="2026-10-20T01:30:00Z")
            reopened = F137TaskStore(store.path, v2_enabled=True)
            again = reopened.run_due_round(runner=runner,
                                           now="2026-10-20T01:30:00Z")
            self.assertEqual(again["fired"], [])
            self.assertEqual(len(runner.calls), 1)

    def test_missed_recorded_latest_once_no_stale_burst(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            runner = RunnerSpy()
            store.run_due_round(runner=runner, now="2026-10-20T01:30:00Z")
            catchup = store.run_due_round(runner=runner,
                                          now="2026-10-23T01:30:00Z")
            self.assertEqual(len(catchup["missed"]), 2)
            self.assertEqual([f["fireKey"] for f in catchup["fired"]],
                             ["t1@2026-10-23T01:00:00Z"])
            self.assertEqual(len(runner.calls), 2)
            missed_keys = {m["fireKey"] for m in catchup["missed"]}
            self.assertEqual(missed_keys, {
                "t1@2026-10-21T01:00:00Z", "t1@2026-10-22T01:00:00Z"})

    def test_cancel_stops_named_and_never_fires_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            runner = RunnerSpy()
            store.run_due_round(runner=runner, now="2026-10-20T01:30:00Z")
            stops: list[tuple] = []

            def stop_runner(session_id, fire_key):
                stops.append((session_id, fire_key))
                return "interrupted:" + fire_key

            receipt = store.cancel_task(task_id="t1",
                                        now="2026-10-20T02:00:00Z",
                                        actor_id="lawyer-a",
                                        reason_ref="doc-cancel-7",
                                        stop_runner=stop_runner)
            self.assertEqual(receipt["state"], "cancelled")
            self.assertEqual(receipt["cancelledBy"], "lawyer-a")
            self.assertEqual(receipt["cancelReasonRef"], "doc-cancel-7")
            self.assertEqual(stops,
                             [("ses_synth_1", "t1@2026-10-20T01:00:00Z")])
            self.assertEqual(receipt["stoppedInFlight"][0]["stopOutcome"],
                             "interrupt_requested")
            state = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertEqual(state["grants"]["grant-t1"]["state"], "sealed")
            after = store.run_due_round(runner=runner,
                                        now="2026-10-24T01:30:00Z")
            self.assertEqual(after["fired"], [])
            self.assertEqual(len(runner.calls), 1)
            with self.assertRaises(ScheduledTaskError) as caught:
                store.cancel_task(task_id="t1", now="2026-10-24T02:00:00Z",
                                  actor_id="lawyer-a")
            self.assertIn("task_already_cancelled", str(caught.exception))
            with self.assertRaises(ScheduledTaskError) as caught:
                store.cancel_task(task_id="absent",
                                  now="2026-10-24T02:00:00Z",
                                  actor_id="lawyer-a")
            self.assertIn("task_unknown", str(caught.exception))

    def test_cancel_needs_stop_runner_when_in_flight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            store.run_due_round(runner=RunnerSpy(),
                                now="2026-10-20T01:30:00Z")
            with self.assertRaises(ScheduledTaskError) as caught:
                store.cancel_task(task_id="t1", now="2026-10-20T02:00:00Z",
                                  actor_id="lawyer-a")
            self.assertIn("f137_stop_runner_not_configured",
                          str(caught.exception))
            # 先验后动：拒后任务仍在账且未取消。
            self.assertEqual(store.task_view("t1")["state"], "enabled")

    def test_stop_runner_failure_recorded_not_masked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            store.run_due_round(runner=RunnerSpy(),
                                now="2026-10-20T01:30:00Z")

            def bad_stop(session_id, fire_key):
                raise RuntimeError("interrupt-refused")

            receipt = store.cancel_task(task_id="t1",
                                        now="2026-10-20T02:00:00Z",
                                        actor_id="lawyer-a",
                                        stop_runner=bad_stop)
            self.assertEqual(receipt["stoppedInFlight"][0]["stopOutcome"],
                             "interrupt_failed:RuntimeError")
            self.assertEqual(receipt["state"], "cancelled")

    def test_launch_failure_receipt_and_suspension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            runner = RunnerSpy(fail_times=3)
            first = store.run_due_round(runner=runner,
                                        now="2026-10-20T01:30:00Z")
            self.assertEqual(first["fired"][0]["state"], "launch_failed")
            self.assertEqual(first["fired"][0]["errorClass"], "RuntimeError")
            self.assertEqual(store.task_view("t1")["consecutiveFailures"], 1)
            second = store.run_due_round(runner=runner,
                                         now="2026-10-21T01:30:00Z")
            self.assertEqual(second["fired"][0]["state"], "launch_failed")
            third = store.run_due_round(runner=runner,
                                        now="2026-10-22T01:30:00Z")
            self.assertEqual(third["suspended"],
                             [{"taskId": "t1",
                               "fireKey": "t1@2026-10-22T01:00:00Z"}])
            self.assertEqual(store.task_view("t1")["state"],
                             "failure_suspended")
            quiet = store.run_due_round(runner=runner,
                                        now="2026-10-23T01:30:00Z")
            self.assertEqual(quiet["fired"], [])
            self.assertEqual(len(runner.calls), 3)

    def test_unsuspend_named_and_guarded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            runner = RunnerSpy(fail_times=3)
            store.run_due_round(runner=runner, now="2026-10-20T01:30:00Z")
            with self.assertRaises(ScheduledTaskError) as caught:
                store.task_unsuspend(task_id="t1", now="2026-10-20T02:00:00Z",
                                     actor_id="lawyer-a")
            self.assertIn("task_not_suspended", str(caught.exception))
            store.run_due_round(runner=runner, now="2026-10-21T01:30:00Z")
            store.run_due_round(runner=runner, now="2026-10-22T01:30:00Z")
            self.assertEqual(store.task_view("t1")["state"],
                             "failure_suspended")
            resumed = store.task_unsuspend(task_id="t1",
                                           now="2026-10-23T00:00:00Z",
                                           actor_id="lawyer-b")
            self.assertEqual(resumed["state"], "enabled")
            self.assertEqual(resumed["unsuspendedBy"], "lawyer-b")
            # 恢复后下一到期照常发起（成功回执清零失败计数）。
            store.run_due_round(runner=runner, now="2026-10-24T01:30:00Z")
            self.assertEqual(store.task_view("t1")["consecutiveFailures"], 0)

    def test_crash_unknown_blocks_until_explicit_reconcile(self) -> None:
        class Crash(BaseException):
            pass

        def crashing(task_view, fire_key, scheduled_utc):
            raise Crash()

        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            with self.assertRaises(Crash):
                store.run_due_round(runner=crashing,
                                    now="2026-10-20T01:30:00Z")
            # 重开存储＝崩溃后进程：firing 标记已落盘、终态未写。
            reopened = F137TaskStore(store.path, v2_enabled=True)
            self.assertEqual(reopened.fire_record(
                "t1@2026-10-20T01:00:00Z")["state"], "firing")
            runner = RunnerSpy()
            blocked = reopened.run_due_round(runner=runner,
                                             now="2026-10-21T01:30:00Z")
            self.assertEqual(blocked["unknown"], [{
                "fireKey": "t1@2026-10-20T01:00:00Z",
                "state": "firing",
                "code": "occurrence_outcome_unknown"}])
            self.assertEqual(blocked["fired"], [])
            self.assertEqual(len(runner.calls), 0)
            for kwargs, code in [
                    ({"task_id": "t1", "fire_key": "wrong",
                      "resolution": "unknown_acknowledged"},
                     "reconcile_target_unknown"),
                    ({"task_id": "t1",
                      "fire_key": "t1@2026-10-20T01:00:00Z",
                      "resolution": "retry_now"},
                     "reconcile_resolution_unknown")]:
                with self.assertRaises(ScheduledTaskError) as caught:
                    reopened.reconcile_unknown(now="2026-10-21T08:00:00Z",
                                               actor_id="lawyer-a", **kwargs)
                self.assertIn(code, str(caught.exception))
            acknowledged = reopened.reconcile_unknown(
                task_id="t1", fire_key="t1@2026-10-20T01:00:00Z",
                resolution="unknown_acknowledged",
                now="2026-10-21T08:00:00Z", actor_id="lawyer-a")
            self.assertEqual(acknowledged["state"], "unknown_acknowledged")
            resumed = reopened.run_due_round(runner=runner,
                                             now="2026-10-21T09:00:00Z")
            self.assertEqual([f["fireKey"] for f in resumed["fired"]],
                             ["t1@2026-10-21T01:00:00Z"])

    def test_runner_missing_refuses_before_any_state_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            with self.assertRaises(ScheduledTaskError) as caught:
                store.run_due_round(runner=None, now="2026-10-20T01:30:00Z")
            self.assertIn("f137_runner_not_configured",
                          str(caught.exception))
            state = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertEqual(state["fires"], {})
            self.assertIsNone(state["tasks"]["t1"]["cursorUtc"])

    def test_receipt_fields_closed_and_zero_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            store.run_due_round(runner=RunnerSpy(),
                                now="2026-10-20T01:30:00Z")
            record = store.fire_record("t1@2026-10-20T01:00:00Z")
            self.assertTrue(set(record) <= set(FIRE_FIELDS))
            self.assertEqual(record["state"], "enqueued")
            # 回执零 agent 输出内容字段（结果/回复/文本结构性不落地）。
            self.assertFalse({"result", "output", "response", "text"}
                             & set(record))

    def test_receipt_shape_invalid_goes_unknown_not_fake_success(
            self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)

            def bad_receipt(task_view, fire_key, scheduled_utc):
                return {"receiptRef": "r", "result": "满纸内容"}

            with self.assertRaises(ScheduledTaskError) as caught:
                store.run_due_round(runner=bad_receipt,
                                    now="2026-10-20T01:30:00Z")
            self.assertIn("runner_receipt_field_unknown",
                          str(caught.exception))
            self.assertEqual(store.fire_record(
                "t1@2026-10-20T01:00:00Z")["state"], "firing")

    def test_dead_address_adapter_fails_named_without_egress(self) -> None:
        """真实 opencode 适配器负向：死地址＝transport_failure 具名回执
        （零出站被行使；127.0.0.1:1 连接即拒）。"""
        from opencode_http import Client
        with tempfile.TemporaryDirectory() as tmp:
            store = make_store(tmp)
            make_task(store)
            client = Client("http://127.0.0.1:1",
                            headers={"Authorization":
                                     "Basic c3ludGg6c3ludGg="},
                            timeout=2)
            runner = f137.opencode_session_prompt_runner(
                client, workspace_dir=str(tmp))
            report = store.run_due_round(runner=runner,
                                         now="2026-10-20T01:30:00Z")
            self.assertEqual(report["fired"][0]["state"], "launch_failed")
            self.assertEqual(report["fired"][0]["errorClass"],
                             "TransportError")


class BridgeFace(unittest.TestCase):
    """legal_entry f137.* 公开面：分组冻结＋分派＋typed 具名拒。"""

    def test_method_group_frozen_and_separated(self) -> None:
        self.assertEqual(legal_entry.SCHEDULED_TASK_METHODS, frozenset({
            "f137.task_create", "f137.task_read", "f137.task_list",
            "f137.task_cancel", "f137.task_unsuspend",
            "f137.run_due_round", "f137.reconcile_unknown"}))
        forbidden = ("goal", "reminder", "terminal", "resume", "recover",
                     "replay", "send", "submit", "harness.")
        for method in legal_entry.SCHEDULED_TASK_METHODS:
            for token in forbidden:
                self.assertNotIn(token, method, method)
        # 已 VERIFIED 面零动：F118 调度组＋F24 run/goal owner 组原样。
        self.assertEqual(legal_entry.HARNESS_SCHEDULE_METHODS, frozenset({
            "harness.schedule_event", "harness.schedule_list",
            "harness.schedule_cancel", "harness.reminder_report"}))
        self.assertIn("harness.run_event_append",
                      legal_entry.HARNESS_RUN_LEDGER_METHODS)

    def test_bridge_create_round_cancel_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = {"f137_v2_scheduled_tasks": True,
                      "f137_state_root": str(tmp)}
            created = legal_entry.call("f137.task_create", {
                "taskId": "t1", "title": "合成定时任务",
                "schedule": DAILY_SH,
                "action": {"kind": "agent.session.prompt",
                           "prompt": "合成指令"},
                "authorization": AUTH_OK,
                "now": CREATED_AT, "createdBy": "ui"}, config)
            self.assertEqual(created["id"], "t1")
            calls: list[str] = []

            def runner(task_view, fire_key, scheduled_utc):
                calls.append(fire_key)
                return {"sessionId": "ses_b", "messageId": "msg_b",
                        "receiptRef": "rcpt:" + fire_key}

            bridged = dict(config)
            bridged["f137_runner"] = runner
            report = legal_entry.call("f137.run_due_round",
                                      {"now": "2026-10-20T01:30:00Z"},
                                      bridged)
            self.assertEqual(len(report["fired"]), 1)
            stops: list[str] = []

            def stop(session_id, fire_key):
                stops.append(fire_key)
                return "interrupted"

            bridged_stop = dict(config)
            bridged_stop["f137_stop_runner"] = stop
            receipt = legal_entry.call("f137.task_cancel", {
                "taskId": "t1", "now": "2026-10-20T02:00:00Z",
                "actorId": "lawyer-a", "reasonRef": "doc-7"}, bridged_stop)
            self.assertEqual(receipt["state"], "cancelled")
            self.assertEqual(stops, ["t1@2026-10-20T01:00:00Z"])
            view = legal_entry.call("f137.task_read",
                                    {"taskId": "t1", "now": CREATED_AT},
                                    config)
            self.assertEqual(view["state"], "cancelled")
            # 重复建同 id 任务＝具名拒（幂等面守卫）。
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call("f137.task_create", {
                    "taskId": "t1", "title": "x", "schedule": DAILY_SH,
                    "action": {"kind": "agent.session.prompt",
                               "prompt": "p"},
                    "authorization": AUTH_OK, "now": CREATED_AT,
                    "createdBy": "ui"}, config)
            self.assertIn("f137_refused:task_id_exists",
                          str(caught.exception))

    def test_bridge_named_refusals_are_typed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = {"f137_v2_scheduled_tasks": True,
                      "f137_state_root": str(tmp)}
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call("f137.task_read",
                                 {"taskId": "absent",
                                  "now": CREATED_AT}, config)
            self.assertIn("f137_refused:task_unknown", str(caught.exception))
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call("f137.run_due_round",
                                 {"now": CREATED_AT}, config)
            self.assertIn("f137_refused:f137_runner_not_configured",
                          str(caught.exception))
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call("f137.run_due_round", {}, config)
            self.assertIn("f137_refused:now_required",
                          str(caught.exception))
            with self.assertRaises(NotConnected) as caught:
                legal_entry.call("f137.task_read",
                                 {"taskId": "x", "now": CREATED_AT},
                                 {"f137_v2_scheduled_tasks": True})
            self.assertIn("f137_refused:f137_state_root_not_configured",
                          str(caught.exception))


class Structure(unittest.TestCase):
    """结构性守卫：AST 钉死（不创第二 Agent loop／零现在时时钟／适配器
    白名单）。"""

    MODULE = ROOT / "python" / "f137_scheduled_tasks.py"

    def _tree(self):
        return ast.parse(self.MODULE.read_text(encoding="utf-8"))

    def test_import_closure_closed(self) -> None:
        # opencode_http＝钉定 core 客户端（create/prompt/interrupt 白名单
        # 另测钉死；零第二 Agent loop）。
        allowed = {"__future__", "calendar", "json", "os", "re", "datetime",
                   "pathlib", "zoneinfo", "run_cursor_store",
                   "opencode_http"}
        found = set()
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0]
                             for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module.split(".")[0])
        self.assertTrue(found <= allowed, sorted(found - allowed))

    def test_no_wall_clock_reads(self) -> None:
        """零 datetime.now()/time.time()/浮点纪元（确定性合成时钟纪律）。"""
        for node in ast.walk(self._tree()):
            if isinstance(node, ast.Call) and isinstance(node.func,
                                                         ast.Attribute):
                self.assertNotIn(node.func.attr,
                                 ("now", "time", "time_ns", "monotonic"),
                                 "wall-clock read forbidden")
            if isinstance(node, ast.Attribute) and node.attr in (
                    "fromtimestamp", "utcfromtimestamp"):
                self.fail("float epoch API forbidden")

    @staticmethod
    def _client_calls(function) -> list:
        return [node.func.attr for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "client"]

    def _inner_function(self, factory_name: str, inner_name: str):
        factory = next(node for node in ast.walk(self._tree())
                       if isinstance(node, ast.FunctionDef)
                       and node.name == factory_name)
        return next(node for node in ast.walk(factory)
                    if isinstance(node, ast.FunctionDef)
                    and node.name == inner_name)

    def test_prompt_runner_uses_only_create_and_prompt(self) -> None:
        """不创第二 Agent loop：适配器 client 交互仅 create+prompt 各一次，
        零流消费零事件订阅（session.text/SSE/delta/inbox 零出现）。"""
        inner = self._inner_function("opencode_session_prompt_runner", "run")
        self.assertEqual(self._client_calls(inner), ["create", "prompt"])
        source = self.MODULE.read_text(encoding="utf-8")
        for token in ("session.text", "/api/event", "text.delta",
                      "/inbox", "while True"):
            self.assertNotIn(token, source, token)

    def test_stop_runner_uses_only_interrupt(self) -> None:
        inner = self._inner_function("opencode_session_stop_runner", "stop")
        self.assertEqual(self._client_calls(inner), ["interrupt"])

    def test_store_schema_and_runner_receipt_fields_documented(self) -> None:
        self.assertEqual(SCHEMA, "f137-schedtasks/1")
        self.assertEqual(RUNNER_RECEIPT_FIELDS,
                         {"sessionId", "messageId", "receiptRef"})


if __name__ == "__main__":
    unittest.main()
