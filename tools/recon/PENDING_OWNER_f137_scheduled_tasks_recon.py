# -*- coding: utf-8 -*-
r"""F137 定时 Agent 任务 验收对账（W5-U12）。

F137（06 V7-137 行 v2，owner=product，UI_HOST_OR_NEW_PRODUCT，desktop/
selfhost 双实例；17 卡验收向量逐字）：「v2才启用具体定时任务，时区/授权/
失败/停止/幂等实际验证；不同于v1持续任务故障恢复」。本单落点＝产品侧
f137_scheduled_tasks 调度层（新增产品合同/权限/持久化，17 卡施工次序第
三段）＋legal_entry f137.* 冻结组公开面；任务执行只经既有 core loop
（opencode create+prompt 各一次入队，完成记账归 F23 server-owned run 面
——v1 持续任务故障恢复已 VERIFIED 在账，本单是其上的定时调度层，不混同
语义：本面零断线续播零自动重发，崩溃未知 fail-closed 等人核）；F118 期
限提醒先行已 VERIFIED（W1-U07/W4-U50）——本面为通用扩展：不读 harness
日程、不生成提醒、不重复三分类锚逻辑。

验收向量逐面（全部确定性合成时钟注入，禁浮点时间运算）：
- v2 闸门：门关的店零任务可建；桥面 config 键必须 literal True
  （False/真值字符串/缺失全拒）。
- 时区/夏令时/月末：zoneinfo 确定性数学钉定——Asia/Shanghai 日任务墙
  钟；America/New_York 春拨不存在墙钟 clamp（2026-03-08 02:30→07:30Z＝
  墙钟 03:30 EDT）、秋拨歧义墙钟 fold=0 首现（2026-11-01 01:30→05:30Z
  EDT 非重置 06:30Z）；月末 day="last" 2026 四月向量（01-31/02-28/03-31/
  04-30）＋day=31 跳短月。
- 授权：每任务显式授权块同命令建立（沿 F24/F26 owner 唯一已 VERIFIED
  面）——缺块/缺 subject/权限非 literal True 具名拒；grantId 一次性绑定
  复用拒；取消封存；goal 内容键结构性禁入（run_cursor_store 同款清单）。
- 失败：runner 异常＝launch_failed 具名回执；连续 3 失败＝failure_
  suspended 零静默重试；task_unsuspend 人动作恢复。
- 停止：取消即停具名（cancelledAt/cancelledBy/cancelReasonRef）；在途已
  入队会话经 stop runner 走 core interrupt（F23 stop 端点），stop 失败
  如实记不冒成功；取消后零新派发；迟到完成归 core 账（本店零完成记录
  API）。
- 幂等：fireKey=任务@预定时刻；同刻重放零 runner 调用（跨进程重开同样
  成立）；停机窗口 missed 逐条入账、补跑 catch_up_latest_once（只发最近
  一个，不爆发陈旧作业）。
- 崩溃未知：firing 标记落盘后进程死＝occurrence_outcome_unknown 阻塞，
  唯一出路显式 reconcile_unknown（区别于 F23 自动续播的语义分离）。

红线遵守：全程合成材料（临时状态根＋合成任务字符串＋注入时钟）；真实
适配器负向只打死地址 http://127.0.0.1:1（零出站被行使）；%APPDATA%\
JusBench 与 %APPDATA%\Juscite 前后快照相等零触碰；oc28 钉定 commit 只读
（工作树前后 porcelain 相等＝本单零触碰，既有 patch 增量原样保留）；
harness 零依赖零改动（owner=product）；台账零改动（F137 两行登记随账
房）；不 push。

用法（juscite worktree w5-u12 根 cwd；--profile 缺省＝双 profile）：
  python -X utf8 tools/recon/PENDING_OWNER_f137_scheduled_tasks_recon.py \
      --profile desktop --profile selfhost

退出码：0 = RECON_OK；1 = RECON_FAIL。
两腿分工（F06 同款：desktop/selfhost 共用宿主面——产品合同无库后端依赖
——分状态根分证据；链内 S8/S9 另经 F137TaskStore 直连径互证）：desktop
/selfhost 全链＝legal_entry 桥面（config 注入合成 runner，生产同链）。
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "python"))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import legal_entry  # noqa: E402
from bridge_errors import NotConnected  # noqa: E402
import f137_scheduled_tasks as f137  # noqa: E402
from f137_scheduled_tasks import (  # noqa: E402
    F137TaskStore,
    FIRE_FIELDS,
    ScheduledTaskError,
    iso_utc,
    next_occurrence,
)

LEDGER = REPO_ROOT / "docs" / "construction" / "acceptance-ledger.csv"
OC28 = Path(r"D:\Codex\1.法律工作区\jusbench工作区\oc28")
OC28_PIN = "026b106bc5d41b679ffc413264229c340871e4d3"
APPDATA = Path(os.environ.get("APPDATA", ""))
JUSBENCH_V6 = APPDATA / "JusBench"
JUSCITE_ROOT = APPDATA / "Juscite"

AUTH_OK = {"grantId": "grant-1", "authorizedBy": "lawyer-a",
           "authorizedAt": "2026-10-20T00:00:00Z",
           "permissions": {"agent.session.prompt": True}}
DAILY_SH = {"kind": "daily", "tz": "Asia/Shanghai", "at": "09:00"}
CREATED_AT = "2026-10-20T00:30:00Z"

# E24 通道四方法组冻结钉值（W4-U50 recon 同键同值；分离面回归）。
CHANNEL_GROUPS = {
    "SUBMISSION_PACKAGE_METHODS": {
        "submission.checklist_define", "submission.checklist_read",
        "submission.package_build", "submission.package_confirm",
        "submission.package_read", "submission.package_list"},
    "CALENDAR_SYNC_METHODS": {
        "calendar.sync_event", "calendar.pull_external",
        "calendar.resolve_conflict", "calendar.sync_read",
        "calendar.sync_list"},
    "WECHAT_COLLECTION_METHODS": {
        "collection.authorize", "collection.batch",
        "collection.batch_read"},
    "COURT_INBOUND_METHODS": {
        "court_inbound.sms_receive", "court_inbound.inbound_run",
        "court_inbound.candidate_review", "court_inbound.intake",
        "court_inbound.read", "court_inbound.list"},
}
HARNESS_SCHEDULE_PIN = {"harness.schedule_event", "harness.schedule_list",
                        "harness.schedule_cancel", "harness.reminder_report"}
SCHEDULER_IMPORT_CLOSURE = {"__future__", "datetime", "typing",
                            "bridge_errors", "legal_entry"}
F137_IMPORT_CLOSURE = {"__future__", "calendar", "json", "os", "re",
                       "datetime", "pathlib", "zoneinfo",
                       "run_cursor_store", "opencode_http"}
AGENT_LOOP_TOKENS = ("session.text", "/api/event", "text.delta",
                     "/inbox", "while True")


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def module_imports(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


def module_functions(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name: node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)}


def snapshot_root(root: Path) -> str:
    """只读快照（相对路径＋大小清单摘要；不读内容）。"""
    if not root.exists():
        return "missing"
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            path = Path(dirpath) / name
            try:
                stat = path.stat()
                rel = str(path.relative_to(root))
            except OSError:
                continue
            digest.update(rel.encode("utf-8"))
            digest.update(str(stat.st_size).encode("ascii"))
    return digest.hexdigest()[:16]


class RunnerSpy:
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


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, ok: bool, detail: str) -> bool:
        self.items.append({"id": check_id,
                           "status": "PASS" if ok else "FAIL",
                           "detail": detail})
        print("[%s] %s — %s" % ("PASS" if ok else "FAIL", check_id, detail),
              flush=True)
        return ok

    @property
    def all_passed(self) -> bool:
        return all(item["status"] == "PASS" for item in self.items)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.items if item["status"] == "PASS")


class TaskFace:
    """统一操作面：全部经 legal_entry 桥面（生产同链）；同店另开直连径
    store 互证（S8/S9）。"""


    def __init__(self, checks: Checks, state_root: Path):
        self.checks = checks
        self.state_root = state_root
        self.config = {"f137_v2_scheduled_tasks": True,
                       "f137_state_root": str(state_root)}

    def store(self, gate: bool, root: Path | None = None) -> F137TaskStore:
        return F137TaskStore((root or self.state_root)
                             / "f137-scheduled-tasks.json",
                             v2_enabled=gate)

    def call(self, method: str, args: dict, extra: dict | None = None):
        config = dict(self.config)
        if extra:
            config.update(extra)
        return legal_entry.call(method, args, config)

    def create(self, task_id="t1", schedule=None, authorization=None):
        # authorization 透传不兜底（None＝真缺块探针，不得被默认值吞掉）。
        return self.call("f137.task_create", {
            "taskId": task_id, "title": "合成定时任务",
            "schedule": schedule or DAILY_SH,
            "action": {"kind": "agent.session.prompt",
                       "prompt": "合成指令"},
            "authorization": authorization,
            "now": CREATED_AT, "createdBy": "ui"})

    def round(self, now, runner, max_failures=None):
        return self.call("f137.run_due_round",
                         {"now": now,
                          **({"maxConsecutiveFailures": max_failures}
                             if max_failures else {})},
                         {"f137_runner": runner})

    def cancel(self, task_id, now, actor_id, reason_ref=None, stop=None):
        return self.call("f137.task_cancel", {
            "taskId": task_id, "now": now, "actorId": actor_id,
            **({"reasonRef": reason_ref} if reason_ref else {})},
            {"f137_stop_runner": stop} if stop else None)

    def view(self, task_id):
        return self.call("f137.task_read",
                         {"taskId": task_id, "now": CREATED_AT})

    def raw_state(self) -> dict:
        return json.loads((self.state_root / "f137-scheduled-tasks.json")
                          .read_text(encoding="utf-8"))


def pins(checks: Checks, rows: dict, oc28_porcelain_baseline: str) -> None:
    """S0 前提在账＋oc28 钉定＋方法组冻结。"""
    prereq = {key: rows.get(key, {}).get("status")
              for key in ("E03", "E05", "E07", "E23", "E24")}
    f23 = (rows.get("F23-desktop", {}).get("status"),
           rows.get("F23-selfhost", {}).get("status"))
    f118 = (rows.get("F118-desktop", {}).get("status"),
            rows.get("F118-selfhost", {}).get("status"),
            rows.get("F118-v1.5", {}).get("status"))
    f137_rows = (rows.get("F137-desktop", {}).get("status"),
                 rows.get("F137-selfhost", {}).get("status"))
    checks.add(
        "U12-PIN-0",
        all(value == "VERIFIED" for value in prereq.values())
        and f23 == ("VERIFIED", "VERIFIED")
        and f118 == ("VERIFIED", "VERIFIED", "VERIFIED")
        and f137_rows == ("NOT_RUN", "NOT_RUN"),
        "前提在账（acceptance-ledger.csv 亲读）：F137 工单 prereq E03/E05/"
        "E07/E23/E24 全 VERIFIED；F23 server-owned 持续任务双实例 VERIFIED"
        "（v1 持续任务故障恢复面在账——本单是其上的定时调度层，不混同语"
        "义）；F118 提醒先行 desktop/selfhost/v1.5 全 VERIFIED（本面不重"
        "复其逻辑）；F137 两行待本单＝%s" % (f137_rows,))

    head = subprocess.check_output(
        ["git", "-C", str(OC28), "rev-parse", "HEAD"], text=True).strip()
    porcelain_now = subprocess.run(
        ["git", "-C", str(OC28), "status", "--porcelain"],
        capture_output=True, text=True).stdout
    checks.add("U12-PIN-1",
               head == OC28_PIN
               and porcelain_now == oc28_porcelain_baseline,
               "oc28 钉定只读零触碰：HEAD=%s…==pin 026b106；工作树前后 "
               "porcelain 逐字节相等（本单零改动；既有 001-011 patch 增量"
               "原样保留未提交，%d 行）" % (head[:12],
                                          len(oc28_porcelain_baseline.
                                              splitlines())))

    checks.add(
        "U12-PIN-2",
        legal_entry.SCHEDULED_TASK_METHODS == frozenset({
            "f137.task_create", "f137.task_read", "f137.task_list",
            "f137.task_cancel", "f137.task_unsuspend",
            "f137.run_due_round", "f137.reconcile_unknown"})
        and legal_entry.HARNESS_SCHEDULE_METHODS
        == frozenset(HARNESS_SCHEDULE_PIN)
        and all(getattr(legal_entry, name) == frozenset(want)
                for name, want in CHANNEL_GROUPS.items()),
        "方法组冻结：legal_entry f137.* 七方法组＝本单新增（零 run/goal/"
        "reminder/terminal/resume 形态，不撞 F23/E07 resume_goal 唤醒通"
        "道）＋已 VERIFIED 面零动（F118 调度组＋E24 通道四方法组逐字相"
        "等）")


def structure(checks: Checks) -> None:
    """结构性守卫：AST 钉死（不创第二 Agent loop／零现在时时钟）。"""
    module = (REPO_ROOT / "implementation" / "python"
              / "f137_scheduled_tasks.py")
    imports = module_imports(module)
    functions = module_functions(module)
    prompt_factory = functions["opencode_session_prompt_runner"]
    prompt_run = next(node for node in ast.walk(prompt_factory)
                      if isinstance(node, ast.FunctionDef)
                      and node.name == "run")
    stop_factory = functions["opencode_session_stop_runner"]
    stop_run = next(node for node in ast.walk(stop_factory)
                    if isinstance(node, ast.FunctionDef)
                    and node.name == "stop")

    def client_calls(function):
        return [node.func.attr for node in ast.walk(function)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "client"]

    source = module.read_text(encoding="utf-8")
    wall_clock_free = all(
        not (isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr in ("now", "time", "time_ns", "monotonic"))
        for node in ast.walk(ast.parse(source)))
    checks.add(
        "U12-STRUCT-0",
        imports <= F137_IMPORT_CLOSURE
        and client_calls(prompt_run) == ["create", "prompt"]
        and client_calls(stop_run) == ["interrupt"]
        and not any(token in source for token in AGENT_LOOP_TOKENS)
        and wall_clock_free,
        "不创第二 Agent loop（结构性）：模块 import 闭集在册（%d 项含钉定 "
        "opencode_http 客户端）；适配器 client 交互仅 create+prompt 各一"
        "次／stop 仅 interrupt（零流消费零事件订阅零轮询，完成记账归 F23 "
        "面）；零 Agent-loop 形态 token；零 datetime.now()/time.time()/浮"
        "点纪元（确定性合成时钟纪律）" % len(imports))

    scheduler = (REPO_ROOT / "implementation" / "python"
                 / "f118_scheduler.py")
    checks.add(
        "U12-STRUCT-1",
        module_imports(scheduler) <= SCHEDULER_IMPORT_CLOSURE,
        "F118 提醒派发环零漂移旁证：f118_scheduler AST 导入闭集仍零网络"
        "（已 VERIFIED 面零改动；本面不读 harness 日程不生成提醒）")


def timezone_vectors(checks: Checks) -> None:
    """时区/夏令时/月末确定性合成时钟钉定。"""
    vectors = [
        ("daily Asia/Shanghai 09:00 次日墙钟",
         DAILY_SH, "2026-01-15T02:00:00Z", "2026-01-16T01:00:00Z"),
        ("monthly day=last 1月",
         {"kind": "monthly", "tz": "Asia/Shanghai", "at": "09:00",
          "day": "last"}, "2026-01-15T02:00:00Z", "2026-01-31T01:00:00Z"),
        ("monthly day=last 2月（2026 非闰）",
         {"kind": "monthly", "tz": "Asia/Shanghai", "at": "09:00",
          "day": "last"}, "2026-02-01T00:00:00Z", "2026-02-28T01:00:00Z"),
        ("monthly day=last 3月",
         {"kind": "monthly", "tz": "Asia/Shanghai", "at": "09:00",
          "day": "last"}, "2026-03-01T00:00:00Z", "2026-03-31T01:00:00Z"),
        ("monthly day=last 4月",
         {"kind": "monthly", "tz": "Asia/Shanghai", "at": "09:00",
          "day": "last"}, "2026-04-01T00:00:00Z", "2026-04-30T01:00:00Z"),
        ("monthly day=31 跳短月（4月→5月）",
         {"kind": "monthly", "tz": "UTC", "at": "00:00", "day": 31},
         "2026-04-01T00:00:00Z", "2026-05-31T00:00:00Z"),
        ("春拨不存在墙钟 clamp（2026-03-08 02:30 NY＝墙钟 03:30 EDT）",
         {"kind": "daily", "tz": "America/New_York", "at": "02:30"},
         "2026-03-07T08:00:00Z", "2026-03-08T07:30:00Z"),
        ("春拨后回正常偏移（03-09 02:30 EDT＝06:30Z）",
         {"kind": "daily", "tz": "America/New_York", "at": "02:30"},
         "2026-03-08T07:30:00Z", "2026-03-09T06:30:00Z"),
        ("秋拨歧义墙钟 fold=0 首现（2026-11-01 01:30 EDT＝05:30Z 非 06:30Z）",
         {"kind": "daily", "tz": "America/New_York", "at": "01:30"},
         "2026-10-31T12:00:00Z", "2026-11-01T05:30:00Z"),
    ]
    failures = []
    for name, schedule, after, expect in vectors:
        got = iso_utc(next_occurrence(schedule, utc(after)))
        if got != expect:
            failures.append("%s: got %s expect %s" % (name, got, expect))
    checks.add(
        "U12-TZ-0", not failures,
        "时区/夏令时/月末确定性数学 %d 向量全钉定（显式合成时钟注入；禁浮"
        "点时间运算）：日/周/月墙钟＋day=last 月末四月份向量（01-31/02-28/"
        "03-31/04-30）＋day=31 跳短月＋春拨 clamp/秋拨 fold=0；named 策略"
        "＝ambiguous_wall_first_fold0／nonexistent_wall_clamp／"
        "monthly_day_overflow_skips_month%s"
        % (len(vectors), "；" if not failures else "；失败：" +
           "；".join(failures)))

    guard_failures = []
    for schedule, code in [
            ({"kind": "hourly", "tz": "UTC", "at": "09:00"},
             "schedule_kind_unknown"),
            ({"kind": "daily", "tz": "Mars/Olympus", "at": "09:00"},
             "schedule_timezone_unknown"),
            ({"kind": "daily", "tz": "UTC", "at": "24:00"},
             "schedule_at_invalid"),
            ({"kind": "weekly", "tz": "UTC", "at": "09:00", "weekday": 7},
             "schedule_weekday_invalid"),
            ({"kind": "monthly", "tz": "UTC", "at": "09:00", "day": 32},
             "schedule_day_invalid")]:
        try:
            next_occurrence(schedule, utc(CREATED_AT))
            guard_failures.append("no refusal for %s" % (schedule,))
        except ScheduledTaskError as exc:
            if code not in str(exc):
                guard_failures.append("%s: got %s" % (code, exc))
    checks.add("U12-TZ-1", not guard_failures,
               "时区/时刻/星期/日域守卫具名拒全过（schedule_timezone_"
               "unknown fail-closed——Windows 部署需 tzdata 数据包，缺区拒"
               "不猜）%s" % ("；".join(guard_failures) or ""))


def chain(checks: Checks, face: TaskFace) -> None:
    """S1-S9 全链（legal_entry 桥面＋直连径互证）。"""
    state_root = face.state_root

    # S1 v2 闸门（门关探针用独立状态根，不污染主店） ------------------------
    closed = face.store(gate=False, root=state_root / "gate-closed-probe")
    try:
        closed.create_task(task_id="early", title="x", schedule=DAILY_SH,
                           action={"kind": "agent.session.prompt",
                                   "prompt": "p"},
                           authorization=AUTH_OK, now=CREATED_AT,
                           created_by="ui")
        refused = False
    except ScheduledTaskError as exc:
        refused = "scheduled_tasks_stage_gate_v2_required" in str(exc)
    closed_state = json.loads(closed.path.read_text(encoding="utf-8"))
    checks.add("S1-GATE-0", refused
               and closed_state["tasks"] == {}
               and closed_state["stageGate"]["v2"] is False,
               "「v2才启用具体定时任务」：门关的店建任务＝"
               "scheduled_tasks_stage_gate_v2_required 具名拒且零任务落盘"
               "（门状态建店定格，不因内存参数翻转）")
    gate_refused = False
    for bad in (None, False, "true", 1):
        config = {"f137_state_root": str(state_root / "gate-probe")}
        if bad is not None:
            config["f137_v2_scheduled_tasks"] = bad
        try:
            legal_entry.call("f137.task_list", {}, config)
            gate_refused = False
            break
        except NotConnected as exc:
            gate_refused = "f137_stage_gate_v2_required" in str(exc)
    checks.add("S1-GATE-1", gate_refused,
               "桥面 v2 闸门 deny-closed：config 键缺失/False/真值字符串/"
               "非 bool 一律 f137_stage_gate_v2_required 拒（literal True "
               "才启用，F26 denyByDefault 同款纪律）")

    # S2 授权 ---------------------------------------------------------------
    auth_failures = []
    try:
        face.create("t-noauth", authorization=None)
        auth_failures.append("missing authorization not refused")
    except (ScheduledTaskError, NotConnected) as exc:
        # 桥面 need() 先拒＝authorization_required；店面直驱＝
        # task_authorization_required（同语义两层面具名）。
        if "authorization_required" not in str(exc):
            auth_failures.append("missing: %s" % exc)
    for permissions, label in (({}, "空 permissions"),
                               ({"agent.session.prompt": False}, "False"),
                               ({"agent.session.prompt": "true"}, "字符串"),
                               ({"other.tool": True}, "未授工具")):
        try:
            face.create(
                "t-badperm",
                authorization={"grantId": "g-bad",
                               "authorizedBy": "lawyer-a",
                               "authorizedAt": CREATED_AT,
                               "permissions": permissions})
            auth_failures.append("%s not refused" % label)
        except (ScheduledTaskError, NotConnected) as exc:
            if "authorization_permission_not_granted" not in str(exc) and (
                    "authorization_permissions_required" not in str(exc)):
                auth_failures.append("%s: %s" % (label, exc))
    face.create("t-a", authorization=AUTH_OK)
    try:
        face.create("t-b", authorization=AUTH_OK)
        auth_failures.append("grant reuse not refused")
    except (ScheduledTaskError, NotConnected) as exc:
        if "authorization_grant_reused" not in str(exc):
            auth_failures.append("reuse: %s" % exc)
    try:
        face.create("t-goalkey", authorization=dict(
            AUTH_OK, grantId="g-goal",
            permissions={"agent.session.prompt": True,
                         "confirmedScope": {"x": 1}}))
        auth_failures.append("goal-content key not refused")
    except (ScheduledTaskError, NotConnected) as exc:
        if "task_payload_goal_content_forbidden" not in str(exc):
            auth_failures.append("goal key: %s" % exc)
    created = face.view("t-a")
    checks.add("S2-AUTH-0", not auth_failures
               and created["state"] == "enabled",
               "授权＝每任务显式授权建立（F24/F26 owner 唯一面同纪律）：缺"
               "块＝task_authorization_required（店面）/authorization_"
               "required（桥面 need 先拒）；permissions 非 literal True 四"
               "形态（空/False/真值字符串/未授工具）全拒；grantId 一次性绑"
               "定复用＝authorization_grant_reused；goal 内容键结构性禁入"
               "（run_cursor_store 同款清单）＝task_payload_goal_content_"
               "forbidden；合法授权任务 enabled 在账；事实=%s"
               % (json.dumps(auth_failures, ensure_ascii=False),))

    # S4 幂等发起 -----------------------------------------------------------
    runner = RunnerSpy()
    empty = face.round(CREATED_AT, runner)
    first = face.round("2026-10-20T01:30:00Z", runner)
    fire_key = "t-a@2026-10-20T01:00:00Z"
    replay = face.round("2026-10-20T01:30:00Z", runner)
    record = face.raw_state()["fires"][fire_key]
    checks.add(
        "S4-FIRE-0",
        empty["fired"] == []
        and [f["fireKey"] for f in first["fired"]] == [fire_key]
        and len(runner.calls) == 1
        and replay["fired"] == [] and len(runner.calls) == 1
        and record["state"] == "enqueued"
        and record["receiptRef"] == "rcpt:" + fire_key,
        "幂等回执不双跑：到期轮恰发起一次（fireKey=%s，runner 恰 1 调用）；"
        "同刻重放零新调用零新回执（同任务重放不双跑）；回执只存 transport "
        "引用（receiptRef/sessionId/messageId）" % fire_key)

    calls_before_reopen = len(runner.calls)
    reopened = face.store(gate=True)
    again = reopened.run_due_round(runner=runner, now=utc(
        "2026-10-20T01:30:00Z"))
    checks.add("S4-FIRE-1", again["fired"] == []
               and len(runner.calls) == calls_before_reopen,
               "跨进程幂等：重开存储（新 store 实例重读盘）重放同轮＝零新"
               "发起（持久化回执面，非内存态）")

    next_day = face.round("2026-10-21T01:30:00Z", runner)
    checks.add("S4-FIRE-2",
               [f["fireKey"] for f in next_day["fired"]]
               == ["t-a@2026-10-21T01:00:00Z"] and len(runner.calls) == 2,
               "次日新预定时刻＝新 fireKey 正常发起（fireKey=任务@预定时刻"
               "全局唯一；每日任务跨日推进）")

    # S5 停机补跑 -----------------------------------------------------------
    face.create("t-miss", authorization={
        "grantId": "g-miss", "authorizedBy": "lawyer-a",
        "authorizedAt": CREATED_AT,
        "permissions": dict(AUTH_OK["permissions"])})
    face.round("2026-10-20T01:30:00Z", runner)  # t-miss 首日
    calls_mark = len(runner.calls)
    catchup = face.round("2026-10-23T01:30:00Z", runner)
    miss_missed = sorted(m["fireKey"] for m in catchup["missed"]
                         if m["fireKey"].startswith("t-miss@"))
    miss_fired = [f["fireKey"] for f in catchup["fired"]
                  if f["fireKey"].startswith("t-miss@")]
    checks.add(
        "S5-MISS-0",
        miss_missed == ["t-miss@2026-10-21T01:00:00Z",
                        "t-miss@2026-10-22T01:00:00Z"]
        and miss_fired == ["t-miss@2026-10-23T01:00:00Z"]
        and len(runner.calls) == calls_mark + 2,
        "停机窗口（多任务店各任务独立结账）：错过的预定时刻逐条记 missed"
        "（零静默丢弃）；补跑 catch_up_latest_once——每任务至多发起最近"
        "一个错过的时刻一次（t-miss 补 10-23 一次；t-a 同轮补自己的 10-23"
        "＝恰 2 次调用，互不挤占不爆发陈旧作业）；t-miss facts=%s；全轮 "
        "fired=%s"
        % (json.dumps({"missed": miss_missed, "fired": miss_fired}),
           json.dumps(sorted(f["fireKey"] for f in catchup["fired"]))))

    # S6 取消即停 -----------------------------------------------------------
    stops: list[tuple] = []

    def stop_runner(session_id, fire_key):
        stops.append((session_id, fire_key))
        return "interrupted:" + fire_key

    receipt = face.cancel("t-miss", "2026-10-23T02:00:00Z", "lawyer-a",
                          reason_ref="doc-cancel-7", stop=stop_runner)
    after_cancel = face.round("2026-10-24T01:30:00Z", runner)
    miss_after = [f["fireKey"] for f in after_cancel["fired"]
                  if f["fireKey"].startswith("t-miss@")]
    double_cancel_named = ""
    try:
        face.cancel("t-miss", "2026-10-24T02:00:00Z", "lawyer-a")
    except (ScheduledTaskError, NotConnected) as exc:
        double_cancel_named = str(exc)
    stopped_keys = {entry["fireKey"]
                    for entry in receipt["stoppedInFlight"]}
    checks.add(
        "S6-STOP-0",
        receipt["state"] == "cancelled"
        and receipt["cancelledBy"] == "lawyer-a"
        and receipt["cancelReasonRef"] == "doc-cancel-7"
        and stopped_keys == {"t-miss@2026-10-20T01:00:00Z",
                             "t-miss@2026-10-23T01:00:00Z"}
        and all(entry["stopOutcome"] == "interrupt_requested"
                for entry in receipt["stoppedInFlight"])
        and len(stops) == len(receipt["stoppedInFlight"]) == 2
        and miss_after == []
        and "task_already_cancelled" in double_cancel_named
        and face.raw_state()["grants"]["g-miss"]["state"] == "sealed",
        "取消即停具名：task_cancelled 回执（cancelledAt/cancelledBy/"
        "cancelReasonRef=doc-cancel-7）；在途已入队未停会话逐个经 stop "
        "runner 走 core interrupt（F23 stop 端点，10-20 首发＋10-23 补跑"
        "共 2 个全部具名 interrupt_requested）；取消后零新派发（t-miss 在"
        " 10-24 轮零 fireKey；其余任务不受牵连）；重复取消＝"
        "task_already_cancelled 具名拒；授权随任务封存（grants.state="
        "sealed）；facts=%s"
        % json.dumps({"stops": stops,
                      "stoppedInFlight": receipt.get("stoppedInFlight"),
                      "missAfterCancel": miss_after,
                      "doubleCancel": double_cancel_named[:80]},
                     ensure_ascii=False))

    no_stop_named = ""
    try:
        face.cancel("t-a", "2026-10-20T02:00:00Z", "lawyer-a")
    except (ScheduledTaskError, NotConnected) as exc:
        no_stop_named = str(exc)
    still_enabled = face.view("t-a")["state"] == "enabled"
    checks.add("S6-STOP-1",
               "f137_stop_runner_not_configured" in no_stop_named
               and still_enabled,
               "先验后动：在途会话需停而 stop runner 未配置＝具名拒且任务"
               "零改动（取消本身不被半途落盘）")

    def bad_stop(session_id, fire_key):
        raise RuntimeError("interrupt-refused")

    bad_receipt = face.cancel("t-a", "2026-10-20T03:00:00Z", "lawyer-a",
                              stop=bad_stop)
    checks.add("S6-STOP-2", bad_receipt["state"] == "cancelled"
               and bad_receipt["stoppedInFlight"][0]["stopOutcome"]
               == "interrupt_failed:RuntimeError",
               "stop 通道失败如实记 interrupt_failed:<类名>（不冒成功也不"
               "阻断取消本身——任务级取消照常成立，零新派发）")

    # S7 失败挂起 -----------------------------------------------------------
    face.create("t-fail", authorization={
        "grantId": "g-fail", "authorizedBy": "lawyer-a",
        "authorizedAt": CREATED_AT,
        "permissions": dict(AUTH_OK["permissions"])})
    bad_runner = RunnerSpy(fail_times=3)
    r1 = face.round("2026-10-20T01:30:00Z", bad_runner)
    r2 = face.round("2026-10-21T01:30:00Z", bad_runner)
    r3 = face.round("2026-10-22T01:30:00Z", bad_runner)
    quiet = face.round("2026-10-23T01:30:00Z", bad_runner)
    fail_view = face.view("t-fail")
    resumed = face.call("f137.task_unsuspend",
                        {"taskId": "t-fail", "now": "2026-10-23T06:00:00Z",
                         "actorId": "lawyer-b"})
    checks.add(
        "S7-FAIL-0",
        all(r["fired"] and r["fired"][0].get("state") == "launch_failed"
            and r["fired"][0].get("errorClass") == "RuntimeError"
            for r in (r1, r2))
        and r3["suspended"] == [{"taskId": "t-fail",
                                 "fireKey": "t-fail@2026-10-22T01:00:00Z"}]
        and quiet["fired"] == [] and len(bad_runner.calls) == 3
        and fail_view["state"] == "failure_suspended"
        and resumed["state"] == "enabled"
        and resumed["unsuspendedBy"] == "lawyer-b",
        "失败面：runner 异常＝launch_failed 具名回执（错误类名入账，零静"
        "默吞）；连续 3 失败＝failure_suspended 零自动重试（挂起轮零调"
        "用）；恢复＝task_unsuspend 人动作具名（zero task_resume 形态，不"
        "撞 F23/E07 resume_goal 唤醒通道）")

    # S8 崩溃未知（区别于 F23 自动续播；直连径互证） -------------------------
    class Crash(BaseException):
        pass

    def crashing(task_view, fire_key, scheduled_utc):
        raise Crash()

    face.create("t-crash", authorization={
        "grantId": "g-crash", "authorizedBy": "lawyer-a",
        "authorizedAt": CREATED_AT,
        "permissions": dict(AUTH_OK["permissions"])})
    crash_propagated = False
    try:
        face.round("2026-10-20T01:30:00Z", crashing)
    except BaseException:
        crash_propagated = True
    after_crash = face.store(gate=True)  # 直连径重开＝崩溃后新进程
    marker_at_reopen = after_crash.fire_record(
        "t-crash@2026-10-20T01:00:00Z")["state"]
    runner2 = RunnerSpy()
    blocked = after_crash.run_due_round(runner=runner2,
                                        now=utc("2026-10-21T01:30:00Z"))
    calls_at_block = len(runner2.calls)
    reconcile_refusals = []
    for kwargs, code in (
            ({"task_id": "t-crash", "fire_key": "wrong",
              "resolution": "unknown_acknowledged"},
             "reconcile_target_unknown"),
            ({"task_id": "t-crash",
              "fire_key": "t-crash@2026-10-20T01:00:00Z",
              "resolution": "retry_now"},
             "reconcile_resolution_unknown")):
        try:
            after_crash.reconcile_unknown(now=utc("2026-10-21T08:00:00Z"),
                                          actor_id="lawyer-a", **kwargs)
        except ScheduledTaskError as exc:
            reconcile_refusals.append(code in str(exc))
    acknowledged = after_crash.reconcile_unknown(
        task_id="t-crash", fire_key="t-crash@2026-10-20T01:00:00Z",
        resolution="unknown_acknowledged", now=utc("2026-10-21T08:00:00Z"),
        actor_id="lawyer-a")
    resumed_round = after_crash.run_due_round(
        runner=runner2, now=utc("2026-10-21T09:00:00Z"))
    s8_facts = {
        "crashPropagated": crash_propagated,
        "markerAtReopen": marker_at_reopen,
        "blockedUnknown": blocked["unknown"],
        "blockedFired": blocked["fired"],
        "runner2CallsAtBlock": calls_at_block,
        "refusals": reconcile_refusals,
        "acknowledged": acknowledged.get("state"),
        "resumedFired": [f["fireKey"] for f in resumed_round["fired"]],
    }
    checks.add(
        "S8-UNKNOWN-0",
        crash_propagated
        and marker_at_reopen == "firing"
        and blocked["unknown"] == [{
            "fireKey": "t-crash@2026-10-20T01:00:00Z",
            "state": "firing",
            "code": "occurrence_outcome_unknown"}]
        and blocked["fired"] == [] and calls_at_block == 0
        and all(reconcile_refusals)
        and acknowledged["state"] == "unknown_acknowledged"
        and [f["fireKey"] for f in resumed_round["fired"]]
        == ["t-crash@2026-10-21T01:00:00Z"],
        "崩溃未知（≠F23 v1 自动续播的语义分离；直连径互证）：firing 标记"
        "落盘后进程死＝重启轮 occurrence_outcome_unknown fail-closed 阻塞"
        "（零自动重发零断线续播）；错 target/错 resolution 具名拒；显式 "
        "reconcile_unknown（人核）后任务恢复推进——迟到完成归 core 账（本"
        "店零完成记录 API）；facts=%s"
        % json.dumps(s8_facts, ensure_ascii=False))

    # S9 回执面卫生＋先拒后动 ------------------------------------------------
    raw = face.raw_state()
    fire_ok = all(set(record) <= set(FIRE_FIELDS)
                  and not ({"result", "output", "response", "text"}
                           & set(record))
                  for record in raw["fires"].values())
    store_text = (state_root / "f137-scheduled-tasks.json").read_text(
        encoding="utf-8")
    banned = ("confirmedScope", "hardConstraints", "preferences",
              "unitTiming", "sourceDecisionRef", "terminalResult",
              "finalVerdict", "businessOutcome")
    checks.add("S9-HYG-0", fire_ok
               and not any(key in store_text for key in banned),
               "宿主存储纪律（f24-runhost 同款）：回执字段闭集且零 agent 输"
               "出内容键（result/output/response/text 零出现）；全店字节扫"
               "描零 goal 内容键/业务终局键；任务定义（含提示文本）＝产品"
               "自动化配置是任务本体")

    before_refuse = face.raw_state()
    refuse_named = ""
    try:
        face.round("2026-10-25T01:30:00Z", None)
    except (ScheduledTaskError, NotConnected) as exc:
        refuse_named = str(exc)
    after_refuse = face.raw_state()
    checks.add("S9-HYG-1",
               "f137_runner_not_configured" in refuse_named
               and after_refuse["fires"] == before_refuse["fires"]
               and after_refuse["tasks"] == before_refuse["tasks"],
               "先拒后动：runner 未配置＝f137_runner_not_configured 具名拒"
               "且零状态改变（零标记零游标推进，回执账逐字节不动）")


def dead_address(checks: Checks, root: Path) -> None:
    """真实 opencode 适配器负向（独立状态根）：死地址＝launch_failed 具名
    回执，零出站被行使。"""
    from opencode_http import Client
    store = F137TaskStore(root / "f137-scheduled-tasks.json",
                          v2_enabled=True)
    store.create_task(
        task_id="t-dead", title="死地址探针", schedule=DAILY_SH,
        action={"kind": "agent.session.prompt", "prompt": "合成指令"},
        authorization={"grantId": "g-dead", "authorizedBy": "lawyer-a",
                       "authorizedAt": CREATED_AT,
                       "permissions": dict(AUTH_OK["permissions"])},
        now=CREATED_AT, created_by="recon")
    client = Client("http://127.0.0.1:1",
                    headers={"Authorization": "Basic c3ludGg6c3ludGg="},
                    timeout=2)
    runner = f137.opencode_session_prompt_runner(client,
                                                 workspace_dir=str(root))
    report = store.run_due_round(runner=runner, now=utc(
        "2026-10-20T01:30:00Z"))
    record = store.fire_record("t-dead@2026-10-20T01:00:00Z")
    checks.add(
        "S9-ADAPT-0",
        bool(report["fired"])
        and report["fired"][0]["state"] == "launch_failed"
        and report["fired"][0]["errorClass"] == "TransportError"
        and record["state"] == "launch_failed"
        and record["errorClass"] == "TransportError",
        "真实适配器（opencode_http.Client，钉定 v2.0.28 接线）负向：死地"
        "址 http://127.0.0.1:1＝TransportError→launch_failed 具名回执（零"
        "出站被行使——连接即拒；适配器是真实 HTTP 链非 stub）")


def run_profile(profile: str, workspace: Path, rows: dict,
                oc28_porcelain_baseline: str) -> tuple:
    checks = Checks()
    print("\n===== profile: %s =====" % profile, flush=True)
    state_root = workspace / profile / "state"
    state_root.mkdir(parents=True)

    baseline_v6 = snapshot_root(JUSBENCH_V6)
    baseline_juscite = snapshot_root(JUSCITE_ROOT)

    pins(checks, rows, oc28_porcelain_baseline)
    structure(checks)
    timezone_vectors(checks)
    face = TaskFace(checks, state_root)
    chain(checks, face)
    dead_address(checks, workspace / profile / "dead-root")

    after_v6 = snapshot_root(JUSBENCH_V6)
    after_juscite = snapshot_root(JUSCITE_ROOT)
    checks.add("U12-HYG-2",
               baseline_v6 == after_v6 and baseline_juscite == after_juscite,
               "%%APPDATA%% 零触碰：JusBench（v6 遗留）与 Juscite 产品根前"
               "后快照相等（%s==%s／%s==%s；本单状态根全在临时目录）"
               % (baseline_v6, after_v6, baseline_juscite, after_juscite))

    verdict = "RECON_OK" if checks.all_passed else "RECON_FAILED"
    meta = {
        "state_root": str(state_root),
        "checks_passed": checks.passed_count,
        "checks_total": len(checks.items),
    }
    return checks, meta, verdict


def ledger_rows() -> dict:
    with open(LEDGER, encoding="utf-8-sig", newline="") as handle:
        return {row["obligation_id"]: row
                for row in csv.DictReader(handle)}


def write_evidence(profile: str, checks: Checks, meta: dict,
                   verdict: str) -> None:
    payload = {
        "unit": "W5-U12", "feature": "F137", "profile": profile,
        "verdict": verdict,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                      time.gmtime()),
        "command": ("python -X utf8 "
                    "tools/recon/PENDING_OWNER_f137_scheduled_tasks_recon.py "
                    "--profile " + profile),
        "cwd": str(REPO_ROOT),
        "subject": ("juscite 分支 w5-u12（worktree 根 cwd；证据生成于收口 "
                    "commit 前工作树＝分支最终内容，W4-U44 先例）"),
        "summary": meta,
        "checks": checks.items,
        "note": ("17 卡验收向量逐字「v2才启用具体定时任务，时区/授权/失败/"
                 "停止/幂等实际验证；不同于v1持续任务故障恢复」逐面落断"
                 "言；F23=其上调度层的 v1 持续任务故障恢复面（已 VERIFIED，"
                 "零混同）；F118 提醒先行已 VERIFIED（本面不重复其逻辑）；"
                 "全程合成材料＋确定性合成时钟（禁浮点时间运算）；真实适配"
                 "器负向只打死地址；%APPDATA% 零触碰；oc28 只读（porcelain"
                 " 前后相等）；harness 零依赖零改动；台账零改动（F137 两行"
                 "登记随账房）"),
    }
    for base in (REPO_ROOT / "evidence" / "F137" / profile,
                 REPO_ROOT / "docs" / "construction" / "evidence" / "F137"
                 / profile):
        base.mkdir(parents=True, exist_ok=True)
        (base / "f137-scheduled-tasks-recon.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8", newline="\n")
        lines = ["# F137 定时 Agent 任务 recon — %s（W5-U12）" % profile,
                 "",
                 "verdict: **%s**（%d/%d）" % (verdict, checks.passed_count,
                                              len(checks.items)),
                 "",
                 "command: `%s`" % payload["command"],
                 "",
                 "| 检 | 结果 | 要点 |", "|---|---|---|"]
        for item in checks.items:
            lines.append("| %s | %s | %s |" % (
                item["id"], item["status"],
                item["detail"].replace("|", "\\|")))
        lines += ["", payload["note"], ""]
        (base / "f137-scheduled-tasks-recon.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F137 定时 Agent 任务 验收对账（W5-U12）")
    parser.add_argument("--profile", action="append",
                        choices=["desktop", "selfhost"], default=[],
                        help="缺省＝双 profile")
    args = parser.parse_args(argv)
    profiles = args.profile or ["desktop", "selfhost"]

    rows = ledger_rows()
    oc28_porcelain_baseline = subprocess.run(
        ["git", "-C", str(OC28), "status", "--porcelain"],
        capture_output=True, text=True).stdout
    workspace = Path(tempfile.mkdtemp(prefix="w5u12-f137-sched-"))
    print("workspace: %s" % workspace, flush=True)
    all_ok = True
    for profile in profiles:
        checks, meta, verdict = run_profile(profile, workspace, rows,
                                            oc28_porcelain_baseline)
        all_ok = all_ok and checks.all_passed
        print("%s[%s] %d/%d" % (verdict, profile, checks.passed_count,
                                len(checks.items)), flush=True)
        write_evidence(profile, checks, meta, verdict)
    print("\n%s" % ("RECON_OK" if all_ok else "RECON_FAILED"), flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
