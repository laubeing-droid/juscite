# -*- coding: utf-8 -*-
"""W3-U26 / E24 acceptance: 外部动作与程序提醒分离不变量（回归面）。

07:E24「外部动作与程序提醒分离」——本模块钉组级与模块级结构性事实（不是
运行时约定）：①外部动作四通道方法组（submission/calendar/collection/
court_inbound）不含 schedule/reminder/send/submit 派发形态，提醒面
（harness.schedule_*）不含外发形态，f118_scheduler 模块导入闭集零网络；
②通知载荷键闭集＋桌面通道；③到期桌面派发队列只收 desktop 通道（email/im
外部发送不在本面＝另授权，harness reminder_report docstring 同边界）；④
程序期限锚只认法院程序事件（schedule_anchor_required/not_found/forbidden
——送达事实不由上传日补的日程级形态）；⑤提醒只能显式声明（reminders=[]
→ 零自动提醒行——F118 待裁不启用实务自动提醒）。

全合成材料；harness 侧 W3 施工链头 w3-u20（基 w3-u12@7c9ccc16，master
929d0802 零动）经 HarnessUnits 直连同封闭注册（深版双 profile 对账＝
tools/PENDING_OWNER_e24_external_actions_recon.py）。
"""
import ast
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "python"))
import legal_entry  # noqa: E402

HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w3-u20")

SCOPE = {"kind": "matter", "matterId": "m-e24-wiring"}

EXPECTED_GROUPS = {
    "SUBMISSION_PACKAGE_METHODS": legal_entry.SUBMISSION_PACKAGE_METHODS,
    "CALENDAR_SYNC_METHODS": legal_entry.CALENDAR_SYNC_METHODS,
    "WECHAT_COLLECTION_METHODS": legal_entry.WECHAT_COLLECTION_METHODS,
    "COURT_INBOUND_METHODS": legal_entry.COURT_INBOUND_METHODS,
}
FORBIDDEN_TOKENS = ("schedule", "reminder", "send", "submit", "dispatch")


def key(request_id):
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


class E24SeparationGroupTests(unittest.TestCase):
    """组级与模块级分离事实（结构性，两 profile 共用同一模块）。"""

    def test_channel_groups_contain_no_reminder_or_egress_forms(self):
        for name, group in EXPECTED_GROUPS.items():
            with self.subTest(group=name):
                self.assertTrue(group)
                for method in group:
                    for token in FORBIDDEN_TOKENS:
                        self.assertNotIn(token, method,
                                         f"{name}:{method}:{token}")

    def test_schedule_group_has_no_external_egress_form(self):
        self.assertEqual(
            legal_entry.HARNESS_SCHEDULE_METHODS,
            frozenset({"harness.schedule_event", "harness.schedule_list",
                       "harness.schedule_cancel", "harness.reminder_report"}))
        self.assertEqual(
            legal_entry.DEADLINE_PRESET_METHODS,
            frozenset({"calc.deadline_presets",
                       "calc.deadline_preset_evaluate"}))

    def test_scheduler_module_import_closure_zero_network(self):
        source = (HERE / "python" / "f118_scheduler.py").read_text(
            encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        self.assertLessEqual(
            imports,
            {"__future__", "datetime", "typing", "bridge_errors",
             "legal_entry"})

    def test_notification_payload_closed_and_desktop_channel(self):
        from f118_scheduler import build_notification, default_notifier
        due = {"reminderId": "rem-wire-1", "taskId": "t-1",
               "deadlineId": "sched-1", "classification": "practical_reminder",
               "title": "庭前会议提醒（合成）", "dueDate": "2099-01-01",
               "scheduledAt": "2098-12-25T00:00:00Z", "channel": "desktop",
               "state": "pending"}
        payload = build_notification(due)
        self.assertEqual(
            set(payload),
            {"reminderId", "taskId", "deadlineId", "classification", "title",
             "body", "dueDate", "daysRemaining", "urgent", "channel"})
        self.assertEqual(payload["channel"], "desktop")
        self.assertIsInstance(payload["daysRemaining"], int)
        expected_days = (date.fromisoformat("2099-01-01") - date.today()).days
        self.assertEqual(payload["daysRemaining"], expected_days)
        # 缺省 sink 只产回执串（结构化日志面），绝不外发。
        receipt = default_notifier(payload)
        self.assertEqual(receipt, "desktop-notification:rem-wire-1")


@unittest.skipUnless(
    (HARNESS_ROOT / "src" / "legal_harness").is_dir(),
    "harness w3-u20 worktree unavailable")
class E24ReminderQueueSeparationTests(unittest.TestCase):
    """到期桌面派发队列只收 desktop；锚规则；提醒只能显式声明。"""

    @classmethod
    def setUpClass(cls):
        for path in (str(HARNESS_ROOT / "src"),
                     str(HARNESS_ROOT / "tools/workflow-tools")):
            if path not in sys.path:
                sys.path.insert(0, path)
        from legal_harness.business.units import HarnessUnits
        from legal_harness.state.matter_store import MatterStore
        cls._tmp = tempfile.TemporaryDirectory(prefix="juscite-e24-wire-")
        cls.store = MatterStore(Path(cls._tmp.name) / "state")
        cls.store.create_matter(SCOPE["matterId"], "cas://e24-wiring")
        cls.units = HarnessUnits(cls.store)
        cls.units.save_procedure_event(
            "wire-lawyer", SCOPE, key("pe-1"),
            {"id": "pe-e24-court", "revision": 1,
             "matterId": SCOPE["matterId"], "kind": "court_event"})
        cls.units.schedule_event(
            "wire-lawyer", SCOPE, key("se-1"),
            {"id": "sched-wire-prog", "classification": "program_deadline",
             "title": "开庭日前准备（合成）", "dueDate": "2099-01-01",
             "eventRef": {"eventId": "pe-e24-court", "eventRevision": 1}},
            [{"id": "rem-wire-prog", "scheduledAt": "2098-12-01T00:00:00Z",
              "channel": "desktop"}])
        # 实务提醒：reminders=[] → 零提醒行（不自动启用实务自动提醒）。
        cls.units.schedule_event(
            "wire-lawyer", SCOPE, key("se-2"),
            {"id": "sched-wire-practical",
             "classification": "practical_reminder",
             "title": "庭前实务提醒（合成·无自动提醒）",
             "dueDate": "2099-01-01"},
            [])
        cls.units.schedule_event(
            "wire-lawyer", SCOPE, key("se-3"),
            {"id": "sched-wire-contract",
             "classification": "contract_obligation",
             "title": "合同尾款义务（合成）", "dueDate": "2099-02-01"},
            [{"id": "rem-wire-email", "scheduledAt": "2098-12-01T00:00:00Z",
              "channel": "email"},
             {"id": "rem-wire-im", "scheduledAt": "2098-12-01T00:00:00Z",
              "channel": "im"}])

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _listing(self):
        return self.units.schedule_list(
            SCOPE, {"asOf": "2098-12-15", "asAt": "2098-12-15T01:00:00Z"})

    def test_groups_separate_and_anchor_rules_hold(self):
        listing = self._listing()
        groups = listing["groups"]
        program = next(i for i in groups["program_deadline"]
                       if i["id"] == "sched-wire-prog")
        practical = groups["practical_reminder"]
        contract = next(i for i in groups["contract_obligation"]
                        if i["id"] == "sched-wire-contract")
        self.assertEqual(program["anchor"],
                         {"eventId": "pe-e24-court", "eventRevision": 1})
        self.assertTrue(all(i["anchor"] is None for i in practical))
        self.assertIsNone(contract["anchor"])

    def test_due_queue_desktop_only_and_no_auto_practical_reminders(self):
        listing = self._listing()
        due_ids = sorted(r["reminderId"]
                         for r in listing["dueDesktopReminders"])
        self.assertEqual(due_ids, ["rem-wire-prog"])
        self.assertTrue(all(r["channel"] == "desktop"
                            for r in listing["dueDesktopReminders"]))
        # email/im 提醒在账保持 pending（外部发送不在本面＝另授权），
        # 永不入到期派发队列。
        import contextlib
        with contextlib.closing(self.store._connect()) as connection:
            rows = connection.execute(
                "SELECT reminder_id, channel, state FROM reminders"
                " WHERE matter_id=?", (SCOPE["matterId"],)).fetchall()
        states = {row["reminder_id"]: (row["channel"], row["state"])
                  for row in rows}
        self.assertEqual(states["rem-wire-email"], ("email", "pending"))
        self.assertEqual(states["rem-wire-im"], ("im", "pending"))
        self.assertNotIn("rem-wire-practical", states)  # 零自动提醒行

    def test_anchor_refusals(self):
        from legal_harness.business.units import UnitsError
        cases = [
            ("schedule_anchor_required:program_deadline",
             {"id": "sched-wire-noa", "classification": "program_deadline",
              "title": "无锚（合成）", "dueDate": "2099-03-01"}, []),
            ("schedule_anchor_not_found:pe-nope",
             {"id": "sched-wire-bog", "classification": "program_deadline",
              "title": "伪造锚（合成）", "dueDate": "2099-03-01",
              "eventRef": {"eventId": "pe-nope", "eventRevision": 1}}, []),
            ("schedule_anchor_forbidden:practical_reminder",
             {"id": "sched-wire-pa", "classification": "practical_reminder",
              "title": "冒锚（合成）", "dueDate": "2099-03-01",
              "eventRef": {"eventId": "pe-e24-court", "eventRevision": 1}},
             []),
        ]
        for expected, event, reminders in cases:
            with self.subTest(code=expected):
                with self.assertRaises(UnitsError) as ctx:
                    self.units.schedule_event(
                        "wire-lawyer", SCOPE, key("neg-" + event["id"]),
                        event, reminders)
                self.assertIn(expected, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
