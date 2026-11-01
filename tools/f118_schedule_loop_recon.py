"""F118 schedule-loop reconciliation against the live harness entry (W1-U07).

对账对象：harness 分支 w1-u07（基于 v8-e05-opencode-target@1de352e5 的 F118
施工分支）的 public_entry --schedule-json 封闭径——与产品桥（legal_entry →
子进程 public_entry）完全同一条链。全部合成材料：临时状态根、合成
matter/procedure event/schedule/reminder 字符串；harness 检出零字节改动
（只运行其代码，git 只读命令核对分支）。

实跑覆盖（PENDING_OWNER_F118_accept）：
  schedule_event → 既有程序期限链（save_procedure_event 锚＋record_deadline_result
  链行投影）→ 提醒（channel=desktop 落账）→ 系统通知（f118_scheduler 载荷＋
  送达报告）→ 节点倒计时 urgent 回读 → 三分类不混同 → 撤销/停用语义 →
  桥 fail-closed 负向。

用法：
  python -X utf8 tools/f118_schedule_loop_recon.py [--harness-root <path>] [--json]

退出码：0 = RECON_OK；1 = RECON_FAIL；3 = RECON_BLOCKED。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import legal_entry  # noqa: E402
import f118_scheduler  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo\.local\worktrees\w1-u07")
EXPECT_BRANCH = "w1-u07"
EXPECT_BASE = "1de352e5"

MATTER = "m-f118-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
AS_OF = "2026-10-15"
AS_AT = "2026-10-15T01:00:00Z"


def key(request_id):
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


class Recon:
    def __init__(self, harness_root: Path):
        self.harness_root = harness_root
        self.checks: list[dict] = []

    def step(self, name, ok, **facts):
        entry = {"check": name, "status": "PASS" if ok else "FAIL", **facts}
        self.checks.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        if not ok:
            raise AssertionError(name)

    def expect_error(self, name, call, code_part, error=HarnessCommandError):
        try:
            call()
        except error as exc:
            self.step(name, code_part in str(exc), code=str(exc))
            return
        raise AssertionError(name + ": no typed error raised")

    def call(self, config, method, args):
        return legal_entry.call(method, args, config)

    def run(self) -> int:
        temporary = tempfile.TemporaryDirectory()
        state_root = Path(temporary.name) / "state"
        state_root.mkdir(parents=True)
        registration = Path(temporary.name) / "service-local.json"
        registration.write_text(json.dumps(
            {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
            encoding="utf-8")
        for path in (str(self.harness_root / "src"),
                     str(self.harness_root / "tools/workflow-tools")):
            sys.path.insert(0, path)
        from legal_harness.state.matter_store import MatterStore
        MatterStore(state_root).create_matter(MATTER, "cas://profile-f118-recon")

        config = {
            "harness_public_entry":
                str(self.harness_root / "tools/workflow-tools/harness/public_entry.py"),
            "harness_target": "opencode",
            "harness_state_root": str(state_root),
            "harness_service_registration": str(registration),
            "harness_timeout": 90,
        }
        listing_query = {"query": {"asOf": AS_OF, "asAt": AS_AT}}

        # 0. 分支核对（git 只读）。
        branch = subprocess.check_output(
            ["git", "-C", str(self.harness_root), "rev-parse", "--abbrev-ref", "HEAD"],
            text=True).strip()
        base = subprocess.check_output(
            ["git", "-C", str(self.harness_root), "rev-parse",
             f"{EXPECT_BRANCH}~1" if False else "HEAD~1"], text=True).strip() \
            if False else subprocess.check_output(
            ["git", "-C", str(self.harness_root), "merge-base", "HEAD",
             "v8-e05-opencode-target"], text=True).strip()
        self.step("harness_branch", branch == EXPECT_BRANCH, branch=branch)
        self.step("harness_base", base.startswith(EXPECT_BASE), base=base)

        # 1. 既有程序期限链照实：procedure event 与 IFC-1 摄入
        #    （save_procedure_event 属 W08 产品接线义务、record_deadline_result
        #    是 harness 内部 JC 摄入面，均不在本单产品桥 F118 白名单——照实经
        #    HarnessUnits 种子入账，与 JC adapter 同径；链行语义照实不重造）。
        from legal_harness.business.units import HarnessUnits
        units = HarnessUnits(MatterStore(state_root))
        units.save_procedure_event(
            "recon-lawyer", SCOPE, key("pe-1"),
            {"id": "pe-court-recon", "revision": 1, "matterId": MATTER,
             "kind": "court_event"})
        units.record_deadline_result(
            "jc-recon", SCOPE, key("rd-1"),
            deadline={"id": "dl-chain-recon", "revision": 1,
                      "eventId": "pe-court-recon", "eventRevision": 1,
                      "dueDate": "2026-10-17", "dateOrigin": "calculated",
                      "rule": "上诉期（合成）"},
            derived_tasks=[
                {"id": "task-chain-recon", "revision": 1,
                 "deadlineId": "dl-chain-recon", "deadlineRevision": 1,
                 "eventId": "pe-court-recon", "eventRevision": 1,
                 "state": "proposed", "dueDate": "2026-10-16"}],
            reminders=[
                {"id": "rem-chain-recon", "revision": 1,
                 "taskId": "task-chain-recon", "taskRevision": 1,
                 "scheduledAt": "2026-10-15T00:20:00Z", "channel": "desktop",
                 "state": "pending"}])
        chain_listing = self.call(config, "harness.schedule_list",
                                  {"scope": SCOPE, **listing_query})
        chain_group = chain_listing["groups"]["program_deadline"]
        self.step("chain_row_projects_as_program_deadline",
                  [i["id"] for i in chain_group] == ["dl-chain-recon"]
                  and chain_group[0]["origin"] == "chain"
                  and chain_group[0]["daysRemaining"] == 2
                  and chain_group[0]["urgent"],
                  origin=chain_group[0]["origin"],
                  daysRemaining=chain_group[0]["daysRemaining"])

        # 2. schedule_event 三分类（程序期限锚链／合同义务／实务提醒）。
        saved_program = self.call(config, "harness.schedule_event", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-1"),
            "event": {"id": "sched-prog-recon",
                      "classification": "program_deadline",
                      "title": "开庭日前准备（合成）", "dueDate": "2026-10-18",
                      "eventRef": {"eventId": "pe-court-recon",
                                   "eventRevision": 1}},
            "reminders": [{"id": "rem-prog-recon",
                           "scheduledAt": "2026-10-16T00:00:00Z",
                           "channel": "desktop"}]})
        self.call(config, "harness.schedule_event", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-2"),
            "event": {"id": "sched-contract-recon",
                      "classification": "contract_obligation",
                      "title": "合同尾款支付义务（合成）", "dueDate": "2026-11-01"},
            "reminders": []})
        self.call(config, "harness.schedule_event", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-3"),
            "event": {"id": "sched-practical-recon",
                      "classification": "practical_reminder",
                      "title": "庭前会议提醒（合成）", "dueDate": "2026-10-16"},
            "reminders": [{"id": "rem-practical-recon",
                           "scheduledAt": "2026-10-15T00:30:00Z",
                           "channel": "desktop"},
                          {"id": "rem-practical-future",
                           "scheduledAt": "2099-01-01T00:00:00Z",
                           "channel": "desktop"}]})
        self.step("schedule_event_saved",
                  saved_program["classification"] == "program_deadline"
                  and saved_program["revision"] == 1
                  and [r["id"] for r in saved_program["reminderRefs"]]
                  == ["rem-prog-recon"])

        listing = self.call(config, "harness.schedule_list",
                            {"scope": SCOPE, **listing_query})
        groups = listing["groups"]
        # 3. 三分类不混同（可回读、分开判定）。
        self.step("three_groups_separate",
                  [i["id"] for i in groups["program_deadline"]]
                  == ["dl-chain-recon", "sched-prog-recon"]
                  and [i["id"] for i in groups["contract_obligation"]]
                  == ["sched-contract-recon"]
                  and [i["id"] for i in groups["practical_reminder"]]
                  == ["sched-practical-recon"],
                  counts=listing["counts"])
        program_sched = next(i for i in groups["program_deadline"]
                             if i["id"] == "sched-prog-recon")
        self.step("program_anchor_real",
                  program_sched["anchor"] == {"eventId": "pe-court-recon",
                                              "eventRevision": 1})
        self.step("non_program_anchor_none",
                  groups["contract_obligation"][0]["anchor"] is None
                  and groups["practical_reminder"][0]["anchor"] is None)

        # 4. 节点倒计时 urgent 回读（整数日差＋窗口）。
        self.step("countdown_urgent",
                  program_sched["daysRemaining"] == 3 and program_sched["urgent"]
                  and not program_sched["overdue"]
                  and groups["practical_reminder"][0]["daysRemaining"] == 1)

        # 5. 提醒→系统通知→送达报告闭环（f118_scheduler 产品半边实跑）。
        fired: list[str] = []

        def notifier(payload):
            fired.append(payload["reminderId"])
            # 通知内容只含账面字段（title/dueDate/classification＋倒计时）。
            assert set(payload) == {"reminderId", "taskId", "deadlineId",
                                    "classification", "title", "body",
                                    "dueDate", "daysRemaining", "urgent",
                                    "channel"}, payload
            assert "合成" in (payload["title"] or "")
            return f"os-notification:{payload['reminderId']}"

        round_result = f118_scheduler.dispatch_and_report(
            config, matter_id=MATTER, notifier=notifier,
            now_iso=AS_AT, as_of=AS_OF, request_seq=1)
        due_ids = sorted(f["reminderId"] for f in round_result["fired"])
        self.step("notifications_fired_for_all_due_desktop",
                  due_ids == ["rem-chain-recon", "rem-practical-recon"]
                  and round_result["refused"] == []
                  and sorted(fired) == due_ids,
                  fired=due_ids)
        after = self.call(config, "harness.schedule_list",
                          {"scope": SCOPE, **listing_query})
        self.step("delivery_reported_in_ledger",
                  after["dueDesktopReminders"] == []
                  and after["counts"]["dueDesktopReminders"] == 0)
        practical = after["groups"]["practical_reminder"][0]
        rem_states = {r["id"]: r["state"] for r in practical["reminders"]}
        self.step("reminder_states_readable",
                  rem_states == {"rem-practical-recon": "sent",
                                 "rem-practical-future": "pending"},
                  states=rem_states)

        # 6. 撤销/停用语义实跑。
        cancelled = self.call(config, "harness.schedule_cancel", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("sc-1"),
            "cancel": {"scheduleId": "sched-practical-recon",
                       "reason": "对账撤销（合成）"}})
        self.step("cancel_cascades",
                  cancelled["state"] == "cancelled"
                  and cancelled["cancelledReminders"]
                  == ["rem-practical-future"])
        final = self.call(config, "harness.schedule_list",
                          {"scope": SCOPE, **listing_query})
        final_practical = [i for i in final["cancelled"]
                           if i["id"] == "sched-practical-recon"]
        # 已送达提醒保留 sent 史（送达史不抹），只有待发项转 cancelled。
        self.step("cancelled_readable_not_in_groups",
                  [i["id"] for i in final["groups"]["practical_reminder"]] == []
                  and len(final_practical) == 1
                  and final_practical[0]["state"] == "cancelled"
                  and {r["id"]: r["state"]
                       for r in final_practical[0]["reminders"]}
                  == {"rem-practical-recon": "sent",
                      "rem-practical-future": "cancelled"})
        # 撤销后待发提醒不再派发。
        self.step("cancelled_not_dispatched",
                  f118_scheduler.due_notifications(
                      config, matter_id=MATTER, now_iso=AS_AT, as_of=AS_OF)
                  == [])
        # 已撤销 id 不可复活（不暗自前移）。
        self.expect_error("used_id_not_resurrected", lambda: self.call(
            config, "harness.schedule_event", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-dead"),
                "event": {"id": "sched-practical-recon",
                          "classification": "practical_reminder",
                          "title": "复活尝试（合成）", "dueDate": "2026-10-20"},
                "reminders": []}), "schedule_id_conflict")
        self.expect_error("double_cancel_refused", lambda: self.call(
            config, "harness.schedule_cancel", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("sc-2"),
                "cancel": {"scheduleId": "sched-practical-recon"}}),
            "schedule_already_cancelled")
        # 链行不归 schedule_cancel 管辖。
        self.expect_error("chain_row_not_cancellable", lambda: self.call(
            config, "harness.schedule_cancel", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("sc-3"),
                "cancel": {"scheduleId": "dl-chain-recon"}}),
            "schedule_cancel_not_schedule_row")

        # 7. 锚规则负向（fail-closed）。
        self.expect_error("program_without_anchor_refused", lambda: self.call(
            config, "harness.schedule_event", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-x1"),
                "event": {"id": "sched-x1", "classification": "program_deadline",
                          "title": "无锚（合成）", "dueDate": "2026-10-20"},
                "reminders": []}), "schedule_anchor_required")
        self.expect_error("practical_with_anchor_refused", lambda: self.call(
            config, "harness.schedule_event", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-x2"),
                "event": {"id": "sched-x2",
                          "classification": "practical_reminder",
                          "title": "带锚（合成）", "dueDate": "2026-10-20",
                          "eventRef": {"eventId": "pe-court-recon",
                                       "eventRevision": 1}},
                "reminders": []}), "schedule_anchor_forbidden")

        # 8. 桥 fail-closed 负向（未配置＝NOT_CONNECTED；未知方法拒绝）。
        self.expect_error("bridge_unconfigured_not_connected", lambda: self.call(
            {}, "harness.schedule_list", {"scope": SCOPE}),
            "harness_public_entry_not_configured", error=NotConnected)
        self.expect_error("unknown_method_refused", lambda: self.call(
            config, "harness.schedule_delete", {"scope": SCOPE}),
            "method_not_connected", error=NotConnected)

        temporary.cleanup()
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--harness-root", type=Path, default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--json", action="store_true",
                        help="append a machine-readable summary block")
    args = parser.parse_args()
    if not (args.harness_root / "tools/workflow-tools/harness/public_entry.py").exists():
        print("RECON_BLOCKED: harness root missing public_entry:", args.harness_root)
        return 3
    recon = Recon(args.harness_root)
    try:
        code = recon.run()
    except (AssertionError, HarnessCommandError, NotConnected) as error:
        print("RECON_FAIL:", error)
        if args.json:
            print(json.dumps({"summary": "RECON_FAIL", "checks": recon.checks},
                             ensure_ascii=False, indent=1))
        return 1
    print(f"RECON_OK, {len(recon.checks)} checks all PASS")
    if args.json:
        print(json.dumps({"summary": "RECON_OK", "checks": recon.checks,
                          "matter": MATTER, "asOf": AS_OF,
                          "today": date.today().isoformat()},
                         ensure_ascii=False, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
