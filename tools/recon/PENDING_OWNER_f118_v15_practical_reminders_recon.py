"""F118-v1.5 实务提醒扩卡实施对账（W4-U50；裁决 #20 唯一扩范围裁决）。

裁决 #20（00-总协调.md:239，2026-10-15）：F118 v1.5 范围含实务提醒。本工具
对 F118-v1.5 实例（tools/acceptance/registry.py COMPOSITE_SEGMENTS["F118"]
扩卡注册，宿主 F118-desktop/selfhost=W1-U07 已 VERIFIED 的程序期限链 v1 段
不动）做全链真跑对账。沿 W3-U26 分离不变量不放松：

  ①实务锚禁用：程序期限锚只认本案 procedure_events 真实行（伪造锚
    schedule_anchor_not_found 拒）；contract_obligation/practical_reminder
    eventRef 一律 schedule_anchor_forbidden 拒——合同义务/实务提醒不混同
    程序 deadline。
  ②提醒只能显式 schedule_event 声明：零隐式自动生成（无 reminders 的
    实务日程 reminders 表零行）。
  ③派发轮仅桌面通知：email/im 提醒账面 pending 永不入 dueDesktopReminders
    队列（外部发送另授权，F61 授权账语义）；提醒环零外发（f118_scheduler
    AST 导入闭集零网络＋desktop 全程死地址注册文件 http://127.0.0.1:1
    全链走通＝无任何 HTTP 出站路径被行使）。
  ④E24 分离收口面回归不破：通道四方法组零 schedule/reminder/send/submit
    形态＋E24 面零新增自动提醒方法（calendar.auto_remind/practical.
    auto_remind method_not_connected）。

新实例断言（工单原文「实务提醒声明/倒计时 urgent/撤销/TTL 全链真实回读＋
合成材料＋通知环零外发」）：TTL=提醒时刻窗与终态语义（harness F118 合同
docs/f118-schedule-contract.md 既有语义，本单零新引擎）——scheduledAt 未到
＝pending 不入派发队列；到期桌面提醒派发一次经 reminder_report 终态 sent 后
永不重发；报告通道失败＝账面仍 pending 下一轮重读仍 due（无静默丢弃、无隐式
过期）；撤销级联后 cancelled 永不再派发；email/im 永久 pending 等显式授权。

对账对象＝harness 钉定 W3 施工链头 w3-u20@b9dce088（本单 harness 零改动，
与 E24 recon 同钉；w3-u20 是 W4 各 harness 分支的祖先，树净亲验）。全程
合成材料（临时状态根＋合成 matter/日程字符串），%APPDATA%/oc28 零触碰。

用法（worktree 根 cwd）：
  python -X utf8 tools/recon/PENDING_OWNER_f118_v15_practical_reminders_recon.py \
      --profile desktop --profile selfhost

退出码：0 = RECON_OK；1 = RECON_FAIL；3 = RECON_BLOCKED。
"""
from __future__ import annotations

import argparse
import ast
import csv
import json
import subprocess
import sys
import tempfile
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))

import legal_entry  # noqa: E402
import f118_scheduler  # noqa: E402
from legal_entry import HarnessCommandError, NotConnected  # noqa: E402

DEFAULT_HARNESS_ROOT = Path(
    r"D:\Codex\1.法律工作区\legal-harness工作区\legal-harness-repo"
    r"\.local\worktrees\w3-u20")

MATTER = "m-f118-v15-recon"
SCOPE = {"kind": "matter", "matterId": MATTER}
AS_OF = "2026-10-20"
AS_AT = "2026-10-20T01:00:00Z"

# lh-pg-e08 容器（E08 拓扑；selfhost 腿 PgMatterStore 直连，同 E24 recon）。
DEFAULT_PG_DSN = "postgresql://lh_app:e08-synth-only@127.0.0.1:55432/legal_harness"

# 钉定（与 tools/recon/PENDING_OWNER_e24_external_actions_recon.py 同键同值）：
# harness＝W3 施工链头 w3-u20（基 w3-u12@7c9ccc16，master 零动）——本单
# harness 零改动，F118 合同面在该链头即已完整（docs/f118-schedule-contract.md）。
EXPECT_BRANCH = "w3-u20"
EXPECT_HEAD = "b9dce088"
HARNESS_BASE_W3_U12 = "7c9ccc16"
HARNESS_MASTER_PIN = "929d0802"

# 方法组冻结（E24 分离不变量的组级面，逐字同 E24 recon 钉值）。
SUBMISSION_METHODS = frozenset({
    "submission.checklist_define", "submission.checklist_read",
    "submission.package_build", "submission.package_confirm",
    "submission.package_read", "submission.package_list"})
CALENDAR_SYNC_METHODS = frozenset({
    "calendar.sync_event", "calendar.pull_external",
    "calendar.resolve_conflict", "calendar.sync_read", "calendar.sync_list"})
WECHAT_COLLECTION_METHODS = frozenset({
    "collection.authorize", "collection.batch", "collection.batch_read"})
COURT_INBOUND_METHODS = frozenset({
    "court_inbound.sms_receive", "court_inbound.inbound_run",
    "court_inbound.candidate_review", "court_inbound.intake",
    "court_inbound.read", "court_inbound.list"})
HARNESS_SCHEDULE_METHODS = frozenset({
    "harness.schedule_event", "harness.schedule_list",
    "harness.schedule_cancel", "harness.reminder_report"})
DEADLINE_PRESET_GROUP = frozenset({
    "calc.deadline_presets", "calc.deadline_preset_evaluate"})
SCHEDULER_IMPORT_CLOSURE = {
    "__future__", "datetime", "typing", "bridge_errors", "legal_entry"}
PAYLOAD_KEYS = {"reminderId", "taskId", "deadlineId", "classification",
                "title", "body", "dueDate", "daysRemaining", "urgent",
                "channel"}

# 合成日程（全合成字符串，无任何真实案号/身份）。
PROG_ID = "sched-v15-prog"
PRAC_A = "sched-v15-prac-a"      # asOf+1 → urgent（默认窗 3）
PRAC_B = "sched-v15-prac-b"      # asOf+4 → 非 urgent；提醒 2099 未来时刻
PRAC_C = "sched-v15-prac-c"      # asOf-1 → 过期 urgent；首轮报告通道失败
PRAC_EMPTY = "sched-v15-prac-empty"  # 无 reminders＝零提醒行（零隐式生成）
CONTRACT_ID = "sched-v15-contract"   # email/im 提醒＝永久 pending 不入队
CHAIN_DL = "dl-v15-chain"            # IFC-1 链行（origin=chain，不可撤）
REM_A = "rem-v15-prac-a"
REM_B = "rem-v15-prac-b"
REM_C = "rem-v15-prac-c"
REM_PROG = "rem-v15-prog"
REM_EMAIL = "rem-v15-email"
REM_IM = "rem-v15-im"
PE_COURT = "pe-v15-court"


def key(request_id):
    return {"requestId": request_id, "targetId": None,
            "expectedRevision": None, "inputRefs": []}


def module_imports(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def api_states(listing: dict) -> dict:
    """提醒状态全量真实回读（schedule_list API：groups＋cancelled 逐行）。"""
    states = {}
    for group in listing["groups"].values():
        for item in group:
            for r in item.get("reminders", []):
                states[r["id"]] = r["state"]
    for item in listing.get("cancelled", []):
        for r in item.get("reminders", []):
            states[r["id"]] = r["state"]
    return states


class Recon:
    def __init__(self, harness_root: Path, profile: str):
        self.harness_root = harness_root
        self.profile = profile
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

    # ------------------------------------------------------------------
    # S0 钉定卫生＋扩卡在账＋E24 分离组冻结。
    # ------------------------------------------------------------------
    def pins_and_card(self, registry):
        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(self.harness_root), *args],
                text=True).strip()

        branch = git("rev-parse", "--abbrev-ref", "HEAD")
        head = git("rev-parse", "HEAD")
        base = git("merge-base", "HEAD", "w3-u12")
        master = git("rev-parse", "master")
        self.step("c00_harness_pinned_w3_chain_head",
                  branch == EXPECT_BRANCH and head.startswith(EXPECT_HEAD),
                  branch=branch, head=head[:12])
        self.step("c00_harness_base_contains_w3_u12_delivery",
                  base.startswith(HARNESS_BASE_W3_U12), base=base[:12])
        self.step("c00_harness_master_untouched",
                  master.startswith(HARNESS_MASTER_PIN), master=master[:12])
        dirty = git("status", "--porcelain")
        self.step("c00_harness_worktree_clean", dirty == "", dirty=dirty[:200])

        # 扩卡在账：registry 表条目＋台账 F118-v1.5 行（断言=registry 逐字生成）。
        self.step("card_registry_segment_entry",
                  "F118" in registry.COMPOSITE_SEGMENTS
                  and registry.COMPOSITE_SEGMENTS["F118"][0][0] == "v1.5"
                  and registry.ADJUDICATED_SEGMENT_OK == {"F118"},
                  segments=sorted(registry.COMPOSITE_SEGMENTS))
        rows06, rows07, _denom = registry.load_inputs()
        expected = registry.build_ledger(rows06, rows07)
        inst = next(i for i in expected
                    if i["obligation_id"] == "F118-v1.5")
        with open(REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv",
                  encoding="utf-8-sig", newline="") as f:
            ledger = list(csv.DictReader(f))
        rows = {r["obligation_id"]: r for r in ledger}
        card = rows.get("F118-v1.5")
        self.step("card_ledger_row_registered",
                  card is not None
                  and card["phase"] == "B4"
                  and card["profile"] == "desktop;selfhost"
                  and card["assertion"] == inst["assertion"],
                  phase=card["phase"] if card else None,
                  assertion=inst["assertion"][:60])
        self.step("card_host_instances_verified_v1_segment",
                  rows.get("F118-desktop", {}).get("status") == "VERIFIED"
                  and rows.get("F118-selfhost", {}).get("status") == "VERIFIED",
                  desktop=rows.get("F118-desktop", {}).get("status"),
                  selfhost=rows.get("F118-selfhost", {}).get("status"))

        # ④E24 分离面回归：通道四方法组零 schedule/reminder/send/submit 形态
        # ＋f118_scheduler AST 导入闭集零网络（结构性，非运行时约定）。
        channel_groups = {
            "SUBMISSION_PACKAGE_METHODS": (
                SUBMISSION_METHODS, legal_entry.SUBMISSION_PACKAGE_METHODS),
            "CALENDAR_SYNC_METHODS": (
                CALENDAR_SYNC_METHODS, legal_entry.CALENDAR_SYNC_METHODS),
            "WECHAT_COLLECTION_METHODS": (
                WECHAT_COLLECTION_METHODS, legal_entry.WECHAT_COLLECTION_METHODS),
            "COURT_INBOUND_METHODS": (
                COURT_INBOUND_METHODS, legal_entry.COURT_INBOUND_METHODS),
        }
        frozen_ok = all(want == got for want, got in channel_groups.values())
        forbidden = ("schedule", "reminder", "send", "submit", "dispatch")
        channel_clean = all(
            not any(tok in m for tok in forbidden)
            for want, _ in channel_groups.values() for m in want)
        imports = module_imports(
            REPO_ROOT / "implementation" / "python" / "f118_scheduler.py")
        scheduler_clean = imports <= SCHEDULER_IMPORT_CLOSURE
        self.step("c00_separation_method_groups_frozen",
                  frozen_ok and channel_clean
                  and legal_entry.HARNESS_SCHEDULE_METHODS
                  == HARNESS_SCHEDULE_METHODS
                  and legal_entry.DEADLINE_PRESET_METHODS == DEADLINE_PRESET_GROUP
                  and scheduler_clean,
                  frozen=frozen_ok, channel_clean=channel_clean,
                  scheduler_imports=sorted(imports))

    # ------------------------------------------------------------------
    # S1-S6 实务提醒全链（call_harness: 合同四方法；round_fn: f118_scheduler
    # 派发轮；query: 状态根直查 SQL）。
    # ------------------------------------------------------------------
    def practical_chain(self, call_harness, round_fn, query,
                        refuse_report_for=None):
        listing_query = {"query": {"asOf": AS_OF, "asAt": AS_AT}}

        # S1 声明：三分类显式 schedule_event（含无提醒实务日程）。
        call_harness("harness.schedule_event", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-prog"),
            "event": {"id": PROG_ID, "classification": "program_deadline",
                      "title": "开庭日前准备（F118-v1.5 合成）",
                      "dueDate": "2026-10-23",
                      "eventRef": {"eventId": PE_COURT, "eventRevision": 1}},
            "reminders": [{"id": REM_PROG,
                           "scheduledAt": "2026-10-19T00:00:00Z",
                           "channel": "desktop"}]})
        call_harness("harness.schedule_event", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-a"),
            "event": {"id": PRAC_A, "classification": "practical_reminder",
                      "title": "当事人庭前联系（合成）", "dueDate": "2026-10-21",
                      "note": "实务提醒不混同程序 deadline（合成注）"},
            "reminders": [{"id": REM_A, "scheduledAt": "2026-10-19T00:30:00Z",
                           "channel": "desktop"}]})
        call_harness("harness.schedule_event", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-b"),
            "event": {"id": PRAC_B, "classification": "practical_reminder",
                      "title": "阅卷预约提醒（合成）", "dueDate": "2026-10-24"},
            "reminders": [{"id": REM_B, "scheduledAt": "2099-01-01T00:00:00Z",
                           "channel": "desktop"}]})
        call_harness("harness.schedule_event", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-c"),
            "event": {"id": PRAC_C, "classification": "practical_reminder",
                      "title": "缴费票据归档提醒（合成）", "dueDate": "2026-10-19"},
            "reminders": [{"id": REM_C, "scheduledAt": "2026-10-19T00:40:00Z",
                           "channel": "desktop"}]})
        call_harness("harness.schedule_event", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-empty"),
            "event": {"id": PRAC_EMPTY, "classification": "practical_reminder",
                      "title": "无提醒实务日程（合成）", "dueDate": "2026-10-22"},
            "reminders": []})
        call_harness("harness.schedule_event", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-ct"),
            "event": {"id": CONTRACT_ID, "classification": "contract_obligation",
                      "title": "合同尾款义务（合成）", "dueDate": "2026-11-01"},
            "reminders": [{"id": REM_EMAIL, "scheduledAt": "2026-10-19T00:00:00Z",
                           "channel": "email"},
                          {"id": REM_IM, "scheduledAt": "2026-10-19T00:00:00Z",
                           "channel": "im"}]})
        # ②零隐式自动生成：无 reminders 的实务日程在 reminders 表零行
        # （COUNT(DISTINCT)：reminders 逐 revision 追加，按 id 去重计数）。
        empty_rows = query(
            "SELECT COUNT(DISTINCT reminder_id) AS n FROM reminders"
            " WHERE matter_id=? AND task_id=?", (MATTER, PRAC_EMPTY + "-task"))[0]["n"]
        declared = query(
            "SELECT COUNT(DISTINCT reminder_id) AS n FROM reminders"
            " WHERE matter_id=?", (MATTER,))[0]["n"]
        self.step("s1_declared_only_zero_implicit",
                  empty_rows == 0 and declared == 6,
                  distinct_reminder_rows=declared, empty_task_rows=empty_rows,
                  note="6=显式声明（prog/prac-a/prac-b/prac-c desktop×4＋email＋im）")

        # S1 锚规则负向（①实务锚禁用＋程序期限锚只认真实程序事件行）。
        self.expect_error("s1_practical_anchor_forbidden", lambda: call_harness(
            "harness.schedule_event", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-x1"),
                "event": {"id": "sched-v15-x1",
                          "classification": "practical_reminder",
                          "title": "带锚实务（合成）", "dueDate": "2026-10-25",
                          "eventRef": {"eventId": PE_COURT,
                                       "eventRevision": 1}},
                "reminders": []}), "schedule_anchor_forbidden:practical_reminder")
        self.expect_error("s1_contract_anchor_forbidden", lambda: call_harness(
            "harness.schedule_event", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-x2"),
                "event": {"id": "sched-v15-x2",
                          "classification": "contract_obligation",
                          "title": "带锚合同（合成）", "dueDate": "2026-11-02",
                          "eventRef": {"eventId": PE_COURT,
                                       "eventRevision": 1}},
                "reminders": []}), "schedule_anchor_forbidden:contract_obligation")
        self.expect_error("s1_program_anchor_required", lambda: call_harness(
            "harness.schedule_event", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-x3"),
                "event": {"id": "sched-v15-x3",
                          "classification": "program_deadline",
                          "title": "无锚程序期限（合成）",
                          "dueDate": "2026-10-26"},
                "reminders": []}), "schedule_anchor_required:program_deadline")
        self.expect_error("s1_forged_anchor_not_found", lambda: call_harness(
            "harness.schedule_event", {
                "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("se-x4"),
                "event": {"id": "sched-v15-x4",
                          "classification": "program_deadline",
                          "title": "伪造锚（合成）", "dueDate": "2026-10-26",
                          "eventRef": {"eventId": "pe-forged-v15",
                                       "eventRevision": 1}},
                "reminders": []}), "schedule_anchor_not_found:pe-forged-v15:1")

        # S2 倒计时 urgent（整数日差，三组分开，锚可回读）。
        listing = call_harness("harness.schedule_list",
                               {"scope": SCOPE, **listing_query})
        groups = listing["groups"]
        prac_ids = [i["id"] for i in groups["practical_reminder"]]
        prog = next(i for i in groups["program_deadline"] if i["id"] == PROG_ID)
        prac_a = next(i for i in groups["practical_reminder"] if i["id"] == PRAC_A)
        prac_b = next(i for i in groups["practical_reminder"] if i["id"] == PRAC_B)
        prac_c = next(i for i in groups["practical_reminder"] if i["id"] == PRAC_C)
        contract = next(i for i in groups["contract_obligation"]
                        if i["id"] == CONTRACT_ID)
        chain = next(i for i in groups["program_deadline"]
                     if i["id"] == CHAIN_DL)
        self.step("s2_groups_separate_anchor_rules",
                  sorted(prac_ids) == sorted([PRAC_A, PRAC_B, PRAC_C,
                                              PRAC_EMPTY])
                  and prog["anchor"] == {"eventId": PE_COURT,
                                         "eventRevision": 1}
                  and chain["origin"] == "chain"
                  and chain["anchor"] == {"eventId": PE_COURT,
                                          "eventRevision": 1}
                  and all(i["anchor"] is None
                          for i in groups["practical_reminder"])
                  and contract["anchor"] is None,
                  practical=prac_ids)
        self.step("s2_countdown_urgent_matrix",
                  prac_a["daysRemaining"] == 1 and prac_a["urgent"]
                  and not prac_a["overdue"]
                  and prac_b["daysRemaining"] == 4 and not prac_b["urgent"]
                  and prac_c["daysRemaining"] == -1 and prac_c["urgent"]
                  and prac_c["overdue"]
                  and prog["daysRemaining"] == 3 and prog["urgent"],
                  matrix={"prac_a": [prac_a["daysRemaining"], prac_a["urgent"]],
                          "prac_b": [prac_b["daysRemaining"], prac_b["urgent"]],
                          "prac_c": [prac_c["daysRemaining"], prac_c["urgent"]],
                          "prog": [prog["daysRemaining"], prog["urgent"]]})
        narrow = call_harness("harness.schedule_list", {
            "scope": SCOPE,
            "query": {"asOf": AS_OF, "asAt": AS_AT, "urgentWithinDays": 0}})
        n_a = next(i for i in narrow["groups"]["practical_reminder"]
                   if i["id"] == PRAC_A)
        n_c = next(i for i in narrow["groups"]["practical_reminder"]
                   if i["id"] == PRAC_C)
        self.step("s2_urgent_window_parameter",
                  n_a["urgent"] is False and n_c["urgent"] is True,
                  prac_a_urgent_at_window0=n_a["urgent"],
                  prac_c_urgent_at_window0=n_c["urgent"],
                  note="urgentWithinDays=0：+1 日不 urgent，过期恒 urgent（含过期）")

        # S3 时刻窗/TTL：email/im 永不入 desktop 派发队列；未来时刻不入队。
        due_ids = sorted(r["reminderId"]
                         for r in listing["dueDesktopReminders"])
        self.step("s3_desktop_only_email_im_never_queued",
                  due_ids == [REM_A, REM_C, REM_PROG]
                  and all(r["channel"] == "desktop"
                          for r in listing["dueDesktopReminders"]),
                  due=due_ids,
                  note="REM_B 未来 2099 不入队；REM_EMAIL/REM_IM 永久 pending")

        # S3/S5 派发轮 1（rem-v15-prac-c 报告通道注入失败→refused 保 pending）。
        result1 = round_fn(request_seq=1,
                           refuse_report_for=refuse_report_for)
        fired1 = sorted(f["reminderId"] for f in result1["fired"])
        refused1 = sorted(f["reminderId"] for f in result1["refused"])
        payloads = {f["reminderId"]: f["notification"]
                    for f in result1["fired"]}
        payloads.update({f["reminderId"]: f["notification"]
                         for f in result1["refused"]})
        self.step("s5_round1_desktop_payload_closed_set",
                  fired1 == [REM_A, REM_PROG]
                  and refused1 == [REM_C]
                  and all(f["outcome"] == "sent"
                          for f in result1["refused"])
                  and all(set(p) == PAYLOAD_KEYS for p in payloads.values())
                  and payloads[REM_A]["classification"] == "practical_reminder"
                  and payloads[REM_A]["channel"] == "desktop"
                  and "【实务提醒】" in payloads[REM_A]["body"]
                  and "【程序期限】" in payloads[REM_PROG]["body"]
                  and payloads[REM_C]["classification"] == "practical_reminder"
                  and payloads[REM_C]["urgent"] is True,
                  fired=fired1, refused=refused1,
                  payload_keys=sorted(payloads[REM_A]),
                  note="通知已发但报告通道失败＝refused 携 sent 结果与原载荷")
        after1 = call_harness("harness.schedule_list",
                              {"scope": SCOPE, **listing_query})
        due1 = sorted(r["reminderId"] for r in after1["dueDesktopReminders"])
        states1 = api_states(after1)
        self.step("s3_sent_terminal_and_report_failure_keeps_pending",
                  due1 == [REM_C]
                  and states1[REM_A] == "sent" and states1[REM_PROG] == "sent"
                  and states1[REM_C] == "pending"
                  and states1[REM_EMAIL] == "pending"
                  and states1[REM_IM] == "pending"
                  and states1[REM_B] == "pending",
                  due_after_round1=due1,
                  note="报告通道失败＝账面仍 pending（不丢提醒·无隐式过期）")

        # S3 派发轮 2：被拒提醒仍 due 重派（下一轮新 CommandKey）；sent 永不重发。
        result2 = round_fn(request_seq=2)
        fired2 = sorted(f["reminderId"] for f in result2["fired"])
        after2 = call_harness("harness.schedule_list",
                              {"scope": SCOPE, **listing_query})
        self.step("s3_round2_requeues_only_refused_sent_never_refires",
                  fired2 == [REM_C] and result2["refused"] == []
                  and after2["dueDesktopReminders"] == []
                  and after2["counts"]["dueDesktopReminders"] == 0,
                  fired=fired2)
        # S3 派发轮 3：队列终态出口——空轮（一次性消费，无重发环）。
        result3 = round_fn(request_seq=3)
        self.step("s3_round3_queue_exit_final",
                  result3["fired"] == [] and result3["refused"] == []
                  and result3["dueCount"] == 0,
                  dueCount=result3["dueCount"])

        # S4 撤销级联（待发提醒转 cancelled；sent 史保留）。
        cancelled = call_harness("harness.schedule_cancel", {
            "actor_id": "recon-lawyer", "scope": SCOPE, "key": key("sc-b"),
            "cancel": {"scheduleId": PRAC_B, "reason": "对账撤销（合成）"}})
        self.step("s4_cancel_cascades",
                  cancelled["state"] == "cancelled"
                  and cancelled["cancelledReminders"] == [REM_B],
                  cancelledReminders=cancelled["cancelledReminders"])
        final = call_harness("harness.schedule_list",
                             {"scope": SCOPE, **listing_query})
        cancelled_row = next(i for i in final["cancelled"]
                             if i["id"] == PRAC_B)
        prac_final_ids = [i["id"] for i in final["groups"]["practical_reminder"]]
        states_f = api_states(final)
        self.step("s4_cancelled_readable_sent_history_kept",
                  sorted(prac_final_ids) == sorted([PRAC_A, PRAC_C, PRAC_EMPTY])
                  and cancelled_row["state"] == "cancelled"
                  and {r["id"]: r["state"]
                       for r in cancelled_row["reminders"]} == {REM_B: "cancelled"}
                  and states_f[REM_A] == "sent",
                  practical=prac_final_ids)
        # 撤销后待发提醒不再派发（派发队列空＝cancelled 永不入队）。
        self.step("s4_cancelled_never_dispatched",
                  final["dueDesktopReminders"] == []
                  and final["counts"]["dueDesktopReminders"] == 0,
                  due=sorted(r["reminderId"]
                             for r in final["dueDesktopReminders"]))

        # S4 撤销守卫负向（不暗自前移：已用 id 不复活；链行不归本面管辖）。
        self.expect_error("s4_used_id_not_resurrected", lambda: call_harness(
            "harness.schedule_event", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("se-dead"),
                "event": {"id": PRAC_B, "classification": "practical_reminder",
                          "title": "复活尝试（合成）", "dueDate": "2026-10-27"},
                "reminders": []}), "schedule_id_conflict")
        self.expect_error("s4_double_cancel_refused", lambda: call_harness(
            "harness.schedule_cancel", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("sc-b2"),
                "cancel": {"scheduleId": PRAC_B}}),
            "schedule_already_cancelled")
        self.expect_error("s4_chain_row_not_cancellable", lambda: call_harness(
            "harness.schedule_cancel", {
                "actor_id": "recon-lawyer", "scope": SCOPE,
                "key": key("sc-chain"),
                "cancel": {"scheduleId": CHAIN_DL}}),
            "schedule_cancel_not_schedule_row")


def run_desktop(recon: Recon, harness_root: Path) -> int:
    """desktop＝产品桥子进程全链（SQLite 临时状态根；生产同链）。"""
    temporary = tempfile.TemporaryDirectory(prefix="juscite-f118v15-desktop-")
    tmp = Path(temporary.name)
    state_root = tmp / "state"
    state_root.mkdir(parents=True)
    # 死地址注册文件：全链若存在任何 HTTP 出站路径被行使即响亮失败
    # ＝通知环零外发的运行时证明（与 AST 闭集互为双证）。
    registration = tmp / "service-local.json"
    registration.write_text(json.dumps(
        {"url": "http://127.0.0.1:1", "password": "synthetic-recon"}),
        encoding="utf-8")
    for path in (str(harness_root / "src"),
                 str(harness_root / "tools/workflow-tools")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.state.matter_store import MatterStore
    from legal_harness.business.units import HarnessUnits
    store = MatterStore(state_root)
    store.create_matter(MATTER, "cas://profile-f118-v15")
    # 程序事件与 IFC-1 链行种子（save_procedure_event/record_deadline_result
    # 属 W08/JC 摄入面，不在产品桥 F118 白名单——W1-U07/E24 recon 同先例）。
    units = HarnessUnits(store)
    units.save_procedure_event(
        "recon-lawyer", SCOPE, key("pe-1"),
        {"id": PE_COURT, "revision": 1, "matterId": MATTER,
         "kind": "court_event"})
    units.record_deadline_result(
        "jc-recon", SCOPE, key("rd-1"),
        deadline={"id": CHAIN_DL, "revision": 1,
                  "eventId": PE_COURT, "eventRevision": 1,
                  "dueDate": "2026-10-23", "dateOrigin": "calculated",
                  "rule": "上诉期（合成）"},
        derived_tasks=[{"id": CHAIN_DL + "-task", "revision": 1,
                        "deadlineId": CHAIN_DL, "deadlineRevision": 1,
                        "eventId": PE_COURT, "eventRevision": 1,
                        "state": "proposed", "dueDate": "2026-10-22"}],
        reminders=[])
    config = {
        "harness_public_entry":
            str(harness_root / "tools/workflow-tools/harness/public_entry.py"),
        "harness_target": "opencode",
        "harness_state_root": str(state_root),
        "harness_service_registration": str(registration),
        "harness_timeout": 120,
    }
    recon.step("s5_dead_registration_no_http_egress_path",
               json.loads(registration.read_text(encoding="utf-8"))["url"]
               == "http://127.0.0.1:1",
               registration="http://127.0.0.1:1",
               note="全链走通＝零 HTTP 出站被行使（桥=子进程 state 根直连）")

    def call_harness(method, call_args):
        return legal_entry.call(method, call_args, config)

    def round_fn(request_seq, refuse_report_for=None):
        real_call = f118_scheduler.call

        def wrapped(method, args, cfg=None):
            if (refuse_report_for is not None
                    and method == "harness.reminder_report"
                    and args["report"]["reminderId"] == refuse_report_for):
                raise HarnessCommandError(
                    f"recon-injected-report-failure:{refuse_report_for}")
            return real_call(method, args, cfg or config)

        f118_scheduler.call = wrapped
        try:
            return f118_scheduler.dispatch_and_report(
                config, matter_id=MATTER,
                notifier=lambda payload:
                    f"os-notification:{payload['reminderId']}",
                now_iso=AS_AT, as_of=AS_OF, request_seq=request_seq)
        finally:
            f118_scheduler.call = real_call

    def query(sql, params):
        import contextlib
        import sqlite3
        with contextlib.closing(store._connect()) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(r) for r in connection.execute(sql, params).fetchall()]

    print("[profile desktop] product bridge subprocess (SQLite state root)",
          flush=True)
    recon.practical_chain(call_harness, round_fn, query,
                          refuse_report_for=REM_C)

    # 桥负向：未配置 fail-closed／未知方法拒／E24 面零新增自动提醒方法。
    try:
        legal_entry.call("harness.schedule_list", {"scope": SCOPE}, {})
        raise AssertionError("bridge_not_configured_expected")
    except NotConnected as exc:
        recon.step("s6_bridge_unconfigured_not_connected",
                   "harness_public_entry_not_configured" in str(exc))
    for method in ("harness.schedule_detonate", "calendar.auto_remind",
                   "practical.auto_remind"):
        try:
            legal_entry.call(method, {"scope": SCOPE}, config)
            raise AssertionError(f"unknown_method_expected:{method}")
        except NotConnected as exc:
            recon.step(f"s6_unknown_method_refused_{method.replace('.', '_')}",
                       "method_not_connected" in str(exc), method=method)
    return 0


def run_selfhost(recon: Recon, harness_root: Path, dsn: str) -> int:
    """selfhost＝PgMatterStore 直连 lh-pg-e08（resolve_provider_method 同一
    封闭注册；E24 recon selfhost 腿同径）。"""
    for path in (str(harness_root / "src"),
                 str(harness_root / "tools/workflow-tools"),
                 str(harness_root), str(harness_root / "tests")):
        if path not in sys.path:
            sys.path.insert(0, path)
    from legal_harness.business.provider_registry import (
        resolve_provider_method, MethodNotWhitelisted,
    )
    from legal_harness.business.units import HarnessUnits, UnitsError
    from legal_harness.state.pg_store import PgMatterStore

    temporary = tempfile.TemporaryDirectory(prefix="juscite-f118v15-selfhost-")
    store = PgMatterStore(
        Path(temporary.name) / "state", dsn=dsn,
        schema="f118v15_" + _uuid.uuid4().hex[:12])
    units = HarnessUnits(store)
    bound = {name: resolve_provider_method(name, units)
             for name in HARNESS_SCHEDULE_METHODS}
    store.create_matter(MATTER, "cas://profile-f118-v15")
    units.save_procedure_event(
        "recon-lawyer", SCOPE, key("pe-1"),
        {"id": PE_COURT, "revision": 1, "matterId": MATTER,
         "kind": "court_event"})
    units.record_deadline_result(
        "jc-recon", SCOPE, key("rd-1"),
        deadline={"id": CHAIN_DL, "revision": 1,
                  "eventId": PE_COURT, "eventRevision": 1,
                  "dueDate": "2026-10-23", "dateOrigin": "calculated",
                  "rule": "上诉期（合成）"},
        derived_tasks=[{"id": CHAIN_DL + "-task", "revision": 1,
                        "deadlineId": CHAIN_DL, "deadlineRevision": 1,
                        "eventId": PE_COURT, "eventRevision": 1,
                        "state": "proposed", "dueDate": "2026-10-22"}],
        reminders=[])

    def call_harness(method, call_args):
        target = bound.get(method)
        if target is None:
            raise MethodNotWhitelisted(method)
        try:
            return target(**call_args)
        except UnitsError as exc:  # 直连径错误规范化为桥错误型（同 desktop 语义）
            raise HarnessCommandError(str(exc)) from exc

    def round_fn(request_seq, refuse_report_for=None):
        def injected(method, args, cfg=None):
            if (refuse_report_for is not None
                    and method == "harness.reminder_report"
                    and args["report"]["reminderId"] == refuse_report_for):
                raise HarnessCommandError(
                    f"recon-injected-report-failure:{refuse_report_for}")
            target = bound.get(method)
            if target is None:
                raise NotConnected("method_not_connected:" + method)
            try:
                return target(**args)
            except UnitsError as exc:  # 同上：规范化为桥错误型
                raise HarnessCommandError(str(exc)) from exc

        original = f118_scheduler.call
        f118_scheduler.call = injected
        try:
            return f118_scheduler.dispatch_and_report(
                {"_selfhost_direct": True},
                matter_id=MATTER,
                notifier=lambda payload:
                    f"os-notification:{payload['reminderId']}",
                now_iso=AS_AT, as_of=AS_OF, request_seq=request_seq)
        finally:
            f118_scheduler.call = original

    def query(sql, params):
        import contextlib
        with contextlib.closing(store._connect()) as connection:
            return [dict(r) for r in connection.execute(sql, params).fetchall()]

    try:
        print("[profile selfhost] PgMatterStore direct (lh-pg-e08)", flush=True)
        recon.practical_chain(call_harness, round_fn, query,
                              refuse_report_for=REM_C)
        # 封闭注册负向（selfhost 同语义）：封闭注册外方法无法解析。
        try:
            resolve_provider_method("harness.schedule_detonate", units)
            raise AssertionError("closed_registry_expected_refusal")
        except MethodNotWhitelisted as exc:
            recon.step("s6_selfhost_closed_registry",
                       "not_whitelisted" in str(exc).replace("-", "_")
                       or "whitelist" in str(exc).lower(),
                       code=str(exc))
    finally:
        store.destroy()
    return 0


def write_evidence(recon: Recon, started: datetime) -> None:
    finished = datetime.now(timezone.utc)
    doc = {
        "unit": "W4-U50",
        "instance": "F118-v1.5",
        "profile": recon.profile,
        "verdict": "RECON_OK",
        "counts": {"pass": sum(1 for c in recon.checks
                               if c["status"] == "PASS"),
                   "total": len(recon.checks)},
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "harness_pin": {"branch": EXPECT_BRANCH, "head": EXPECT_HEAD,
                        "base_w3_u12": HARNESS_BASE_W3_U12,
                        "master": HARNESS_MASTER_PIN},
        "checks": recon.checks,
    }
    for base in (REPO_ROOT / "evidence" / "F118" / recon.profile,
                 REPO_ROOT / "docs" / "construction" / "evidence" / "F118"
                 / recon.profile):
        base.mkdir(parents=True, exist_ok=True)
        (base / "f118-v15-practical-recon.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8", newline="\n")
        lines = ["# F118-v1.5 实务提醒 recon（W4-U50·%s）" % recon.profile,
                 "",
                 "命令：`python -X utf8 "
                 "tools/recon/PENDING_OWNER_f118_v15_practical_reminders_recon.py"
                 " --profile %s`（worktree 根 cwd）" % recon.profile,
                 "",
                 "verdict=**RECON_OK**，%d/%d 检 PASS（harness 钉 %s@%s，"
                 "树净，本单 harness 零改动）。"
                 % (doc["counts"]["pass"], doc["counts"]["total"],
                    EXPECT_BRANCH, EXPECT_HEAD),
                 "",
                 "| 检查 | 结果 |",
                 "|---|---|"]
        for c in recon.checks:
            lines.append("| %s | %s |" % (c["check"], c["status"]))
        lines += ["", "全部合成材料；%APPDATA%\\JusBench／oc28 零触碰；不 push。",
                  ""]
        (base / "f118-v15-practical-recon.md").write_text(
            "\n".join(lines), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"],
                        help="可重复；缺省＝双 profile 全跑")
    parser.add_argument("--harness-root", type=Path,
                        default=DEFAULT_HARNESS_ROOT)
    parser.add_argument("--pg-dsn", default=DEFAULT_PG_DSN)
    args = parser.parse_args()
    profiles = args.profile or ["desktop", "selfhost"]
    if not (args.harness_root
            / "tools/workflow-tools/harness/public_entry.py").exists():
        print("RECON_BLOCKED: harness root missing public_entry:",
              args.harness_root)
        return 3
    sys.path.insert(0, str(REPO_ROOT / "tools" / "acceptance"))
    import registry

    overall_fail = False
    for profile in profiles:
        recon = Recon(args.harness_root, profile)
        started = datetime.now(timezone.utc)
        try:
            recon.pins_and_card(registry)
            if profile == "desktop":
                run_desktop(recon, args.harness_root)
            else:
                run_selfhost(recon, args.harness_root, args.pg_dsn)
        except (AssertionError, HarnessCommandError, NotConnected) as error:
            print("RECON_FAIL[%s]:" % profile, error)
            overall_fail = True
            doc = {"unit": "W4-U50", "profile": profile,
                   "verdict": "RECON_FAIL", "error": str(error),
                   "checks": recon.checks}
            base = REPO_ROOT / "evidence" / "F118" / profile
            base.mkdir(parents=True, exist_ok=True)
            (base / "f118-v15-practical-recon.json").write_text(
                json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8", newline="\n")
            continue
        write_evidence(recon, started)
        print("RECON_OK[%s], %d checks all PASS"
              % (profile, len(recon.checks)), flush=True)
    return 1 if overall_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
