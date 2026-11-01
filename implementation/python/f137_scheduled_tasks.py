"""F137 定时 Agent 任务：产品侧定时自动化调度层（W5-U12）。

义务 06 V7-137「定时自动化 agent 任务」v2，owner=product，
UI_HOST_OR_NEW_PRODUCT；17 卡验收向量逐字：「v2才启用具体定时任务，时区/
授权/失败/停止/幂等实际验证；不同于v1持续任务故障恢复」；17 卡施工次序
「优先保原生能力→仅选型必要差异→新增产品合同/权限/持久化→原生UI触发→
真实回读；不创第二Agent loop」。

与两个已 VERIFIED 面的分工（不混同语义、不重复逻辑）：

- F23 server-owned run（已 VERIFIED）：服务端执行 fiber 的断线续播/stop
  独立终态——那是 v1 持续任务故障恢复。本单是**其上的定时调度层**：只在
  到期时刻发起新的一次 agent 会话入队（复用同一 core loop：opencode
  create+prompt 各一次，F23 面管完成记账），不恢复、不续播任何已中断的
  服务端 run；本店只存 transport 引用（F24 宿主纪律：投影/回执元数据，
  零业务终局字段，也零完成记录 API——迟到完成归 core 账，本店不覆写）。
- F118 期限提醒（W1-U07/W4-U50 已 VERIFIED）：harness 日程账面的提醒
  派发环（三分类锚/倒计时/TTL）。本单调度面为通用扩展：任务定义/时区
  计算/授权/回执全部产品侧自持，不读 harness 日程、不生成提醒、不重复
  F118 的三分类锚语义。

确定性纪律（工作区：时效与日历确定性解析，禁浮点时间运算）：

- 调度数学全程显式注入 now（aware datetime，统一归一 UTC）；模块零
  datetime.now()/time.time()/浮点纪元；时区用 stdlib zoneinfo（PEP 615；
  Windows 部署需 tzdata 数据包，缺区＝schedule_timezone_unknown 具名拒
  fail-closed）。夏令时/月末边界全部可复现合成时钟钉定：
  - 歧义墙钟（秋拨重复时刻）＝fold=0 首现（ambiguous_wall_first_fold0）；
  - 不存在墙钟（春拨跳过时刻）＝夹到跳变后即时，墙钟显示晚于名义时刻
    （nonexistent_wall_clamp）；
  - 月末＝calendar.monthrange 确定性（day="last"）；day=N 超出当月＝整月
    跳过（cron 语义，monthly_day_overflow_skips_month）。

授权纪律（沿 F24/F26 run/goal owner 唯一已 VERIFIED 面）：每任务显式授权
与任务同命令一次性建立——authorization{grantId, authorizedBy,
authorizedAt, permissions}；缺块/缺 subject/权限非 literal True 一律具名
拒（deny-closed 同 F26 denyByDefault literal-True 纪律）；grantId 与任务
终身绑定、已用即耗尽（authorization_grant_reused）；任务取消＝授权一并
封存（grants[grantId].state=sealed）。

幂等/停止/失败/未知纪律：

- fireKey = taskId + "@" + 预定时刻 UTC ISO（同一预定时刻全局唯一）；终
  态回执在账的预定时刻零重发（幂等回执，不双跑；跨进程重开存储同样成
  立）；
- 发起原子序＝先落 firing 标记（单次原子 save），终态回执写入时才推进
  cursor：进程崩在中间＝标记在、终态无、cursor 未过——该任务后续派发
  fail-closed 阻塞（occurrence_outcome_unknown），唯一出路显式
  reconcile_unknown（人核后放行，不自动重发）——区别于 F23 的服务端自
  动断线续播；
- 停机窗口错过的预定时刻＝逐条记 missed（零静默丢弃），补跑策略
  catch_up_latest_once：每轮每任务至多发起最近一个错过的时刻一次，更早
  的只记 missed 不补——停机后不自动爆发陈旧法律作业；
- 取消即停具名：task_cancelled 回执（cancelledAt/cancelledBy/
  cancelReasonRef）；在途已入队会话可经 stop runner 走 core interrupt
  （F23 stop 端点，stopOutcome 记 interrupt_requested/interrupt_failed:
  <类名>）；取消后新预定时刻永不派发；迟到完成归 core 账（本店零完成记
  录 API，不覆写任何终态）；
- runner 异常＝launch_failed 回执（错误类名具名，不静默吞）；连续发起失
  败达 maxConsecutiveFailures（默认 3）＝任务 failure_suspended，显式
  task_unsuspend（人动作）才恢复——zero task_resume 形态，避免与 F23/E07
  resume_goal 唤醒通道撞名。

宿主存储纪律（run_cursor_store f24-runhost 同款）：状态文件 schema
f137-schedtasks/1，原子写（tmp+os.replace）；goal 内容键/业务终局键结构
性禁入（复用 run_cursor_store 同款清单）；回执字段闭集，只存 transport
引用（sessionId/messageId/receiptRef），零 agent 输出内容；任务定义（含
提示文本）＝产品自动化配置，是任务本体。
"""
from __future__ import annotations

import calendar
import json
import os
import re
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from run_cursor_store import GOAL_CONTENT_KEYS, TERMINAL_FORBIDDEN_KEYS

SCHEMA = "f137-schedtasks/1"
STORE_FILENAME = "f137-scheduled-tasks.json"

# 预定粒度只有墙钟 HH:MM（每日/每周/每月），天然无秒级风暴。
SCHEDULE_KINDS = ("daily", "weekly", "monthly")
ACTION_KINDS = ("agent.session.prompt",)
ACTION_FIELDS = frozenset({"kind", "prompt", "cwd"})
SCHEDULE_FIELDS = frozenset({"kind", "tz", "at", "weekday", "day"})
AUTHORIZATION_FIELDS = frozenset(
    {"grantId", "authorizedBy", "authorizedAt", "permissions"})
REQUIRED_PERMISSION = "agent.session.prompt"
_AT_RE = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])$")

TERMINAL_FIRE_STATES = ("enqueued", "launch_failed")
ALL_FIRE_STATES = ("firing", "missed", *TERMINAL_FIRE_STATES,
                   "unknown_acknowledged")
# 回执字段闭集：零 agent 输出内容（结果/回复/文本一律不落地）。
FIRE_FIELDS = frozenset({
    "fireKey", "taskId", "scheduledUtc", "state", "startedAt", "finishedAt",
    "recordedAt", "sessionId", "messageId", "receiptRef", "errorClass",
    "errorText", "stopRequestedAt", "stopOutcome", "stopReceipt",
    "acknowledgedAt", "acknowledgedBy",
})
RUNNER_RECEIPT_FIELDS = frozenset({"sessionId", "messageId", "receiptRef"})
TASK_STATES = ("enabled", "cancelled", "failure_suspended")

_ENUMLIMIT_OCCURRENCES = 10000
_ENUMLIMIT_MONTHS = 49
_ERROR_TEXT_LIMIT = 200


class ScheduledTaskError(ValueError):
    """F137 具名拒；str(...) 即机器可读错误码。"""


# ---------------------------------------------------------------- 时钟入参

def parse_now(value, *, field: str = "now") -> datetime:
    """显式注入的确定性时钟：ISO Z 字符串或 aware datetime（归一 UTC）。"""
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ScheduledTaskError(field + "_timestamp_invalid") from None
    else:
        raise ScheduledTaskError(field + "_timestamp_invalid")
    if moment.tzinfo is None or moment.utcoffset() is None \
            or moment.utcoffset() != timedelta(0):
        raise ScheduledTaskError(field + "_must_be_aware_utc")
    return moment.astimezone(UTC)


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z")


# ---------------------------------------------------------------- 调度数学

_ZONE_CACHE: dict = {}


def _zone(name):
    zone = _ZONE_CACHE.get(name)
    if zone is None:
        try:
            zone = ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, KeyError, OSError):
            raise ScheduledTaskError(
                "schedule_timezone_unknown:" + str(name)) from None
        _ZONE_CACHE[name] = zone
    return zone


def _parse_wall(at) -> time:
    match = _AT_RE.match(at if isinstance(at, str) else "")
    if not match:
        raise ScheduledTaskError("schedule_at_invalid")
    return time(int(match.group(1)), int(match.group(2)))


def validate_schedule(schedule) -> dict:
    if not isinstance(schedule, dict):
        raise ScheduledTaskError("schedule_invalid")
    unknown = set(schedule) - set(SCHEDULE_FIELDS)
    if unknown:
        raise ScheduledTaskError(
            "schedule_field_unknown:" + sorted(unknown)[0])
    kind = schedule.get("kind")
    if kind not in SCHEDULE_KINDS:
        raise ScheduledTaskError("schedule_kind_unknown")
    _parse_wall(schedule.get("at"))
    _zone(schedule.get("tz"))
    if kind == "weekly":
        weekday = schedule.get("weekday")
        if not isinstance(weekday, int) or isinstance(weekday, bool) \
                or not 0 <= weekday <= 6:
            raise ScheduledTaskError("schedule_weekday_invalid")
    if kind == "monthly":
        day = schedule.get("day")
        if day == "last":
            pass
        elif isinstance(day, int) and not isinstance(day, bool) \
                and 1 <= day <= 31:
            pass
        else:
            raise ScheduledTaskError("schedule_day_invalid")
    return dict(schedule)


def _wall_on(date_value, wall: time, tz: ZoneInfo) -> datetime:
    """某日墙钟时刻 → UTC 即刻（fold=0）。

    - 歧义（秋拨重复）：fold=0 取首现——round-trip 墙钟相等，正常返回。
    - 不存在（春拨跳过）：fold=0 挂偏移得到的即刻落在跳变之后，round-trip
      墙钟晚于名义时刻——clamp 策略原样采用该即刻（墙钟显示跳变后时刻）。
    """
    naive = datetime.combine(date_value, wall)
    attached = naive.replace(tzinfo=tz)  # fold=0
    return attached.astimezone(UTC)


def next_occurrence(schedule, after_utc) -> datetime:
    """严格晚于 after_utc 的下一次预定时刻（确定性合成时钟数学）。"""
    schedule = validate_schedule(schedule)
    moment = parse_now(after_utc)
    tz = _zone(schedule["tz"])
    wall = _parse_wall(schedule["at"])
    kind = schedule["kind"]
    cursor = moment.astimezone(tz).date()

    if kind == "monthly":
        year, month = cursor.year, cursor.month
        wanted = schedule["day"]
        for _ in range(_ENUMLIMIT_MONTHS):
            last = calendar.monthrange(year, month)[1]
            if wanted == "last":
                candidate = last
            elif wanted <= last:
                candidate = wanted
            else:
                candidate = None  # monthly_day_overflow_skips_month
            if candidate is not None:
                date_value = datetime(year, month, candidate).date()
                instant = _wall_on(date_value, wall, tz)
                if instant > moment:
                    return instant
            month += 1
            if month == 13:
                year, month = year + 1, 1
        raise ScheduledTaskError("schedule_enumeration_overflow")

    for step in range(_ENUMLIMIT_OCCURRENCES):
        date_value = cursor + timedelta(days=step)
        if kind == "weekly" and date_value.weekday() != schedule["weekday"]:
            continue
        instant = _wall_on(date_value, wall, tz)
        if instant > moment:
            return instant
    raise ScheduledTaskError("schedule_enumeration_overflow")


def _fire_key(task_id: str, moment: datetime) -> str:
    return task_id + "@" + iso_utc(moment)


# ---------------------------------------------------------------- 存储

def _guard_payload(node, *, where: str) -> None:
    """goal 内容键/业务终局键任何层级禁入（run_cursor_store 同款清单）。"""

    def _walk(item) -> None:
        if isinstance(item, dict):
            for key, value in item.items():
                if key in GOAL_CONTENT_KEYS:
                    raise ScheduledTaskError(
                        where + "_goal_content_forbidden:" + key)
                if key in TERMINAL_FORBIDDEN_KEYS:
                    raise ScheduledTaskError(
                        where + "_terminal_field_forbidden:" + key)
                _walk(value)
        elif isinstance(item, list):
            for value in item:
                _walk(value)

    _walk(node)


class F137TaskStore:
    """产品侧定时任务店（调度定义＋授权账＋发起回执；零业务事实）。"""

    def __init__(self, path, *, v2_enabled: bool):
        self.path = Path(path)
        self.v2_enabled = bool(v2_enabled)
        self._state = None
        self._load()

    # -- 原子持久化 -----------------------------------------------------

    def _load(self) -> None:
        if self.path.exists():
            self._state = json.loads(self.path.read_text(encoding="utf-8"))
            if self._state.get("schema") != SCHEMA:
                raise ScheduledTaskError("f137_store_schema_unknown")
            return
        self._state = {
            "schema": SCHEMA,
            # 门状态建店时定格：门关的店不因后续内存参数翻转。
            "stageGate": {"v2": self.v2_enabled},
            "tasks": {},
            "grants": {},
            "fires": {},
        }
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(self._state, handle, ensure_ascii=False, indent=1,
                      sort_keys=True)
        os.replace(tmp, self.path)

    # -- 建店门（v2 才启用具体定时任务） ---------------------------------

    def _gate_open(self) -> None:
        if not (self.v2_enabled
                and self._state["stageGate"].get("v2") is True):
            raise ScheduledTaskError("scheduled_tasks_stage_gate_v2_required")

    # -- ① 任务建立（含每任务显式授权） ----------------------------------

    def create_task(self, *, task_id, title, schedule, action,
                    authorization, now, created_by) -> dict:
        self._gate_open()
        moment = parse_now(now)
        if not isinstance(task_id, str) or not task_id.strip():
            raise ScheduledTaskError("task_id_invalid")
        if task_id in self._state["tasks"]:
            raise ScheduledTaskError("task_id_exists")
        if not isinstance(title, str) or not title.strip():
            raise ScheduledTaskError("task_title_required")
        if not isinstance(created_by, str) or not created_by.strip():
            raise ScheduledTaskError("task_creator_required")
        clean_schedule = validate_schedule(schedule)
        clean_action = self._validate_action(action)
        clean_authorization = self._validate_authorization(authorization,
                                                           moment)
        # grant 一次性绑定：同一 grantId 已绑定任何任务＝具名拒（授权不可
        # 复用；新任务须新的显式授权）。
        if clean_authorization["grantId"] in self._state["grants"]:
            raise ScheduledTaskError("authorization_grant_reused")
        task = {
            "id": task_id,
            "title": title,
            "state": "enabled",
            "schedule": clean_schedule,
            "action": clean_action,
            "authorization": clean_authorization,
            "createdBy": created_by,
            "createdAt": iso_utc(moment),
            "cursorUtc": None,
            "consecutiveFailures": 0,
        }
        _guard_payload(task, where="task_payload")
        self._state["tasks"][task_id] = task
        self._state["grants"][clean_authorization["grantId"]] = {
            "grantId": clean_authorization["grantId"],
            "taskId": task_id,
            "authorizedBy": clean_authorization["authorizedBy"],
            "authorizedAt": clean_authorization["authorizedAt"],
            "state": "bound",
        }
        self._save()
        return self.task_view(task_id)

    @staticmethod
    def _validate_action(action) -> dict:
        if not isinstance(action, dict):
            raise ScheduledTaskError("action_invalid")
        unknown = set(action) - set(ACTION_FIELDS)
        if unknown:
            raise ScheduledTaskError(
                "action_field_unknown:" + sorted(unknown)[0])
        if action.get("kind") not in ACTION_KINDS:
            raise ScheduledTaskError("action_kind_unknown")
        if not isinstance(action.get("prompt"), str) \
                or not action["prompt"].strip():
            raise ScheduledTaskError("action_prompt_required")
        cwd = action.get("cwd")
        if cwd is not None and (not isinstance(cwd, str) or not cwd.strip()):
            raise ScheduledTaskError("action_cwd_invalid")
        clean = {"kind": action["kind"], "prompt": action["prompt"]}
        if cwd is not None:
            clean["cwd"] = cwd
        return clean

    @staticmethod
    def _validate_authorization(authorization, moment: datetime) -> dict:
        if not isinstance(authorization, dict):
            raise ScheduledTaskError("task_authorization_required")
        unknown = set(authorization) - set(AUTHORIZATION_FIELDS)
        if unknown:
            raise ScheduledTaskError(
                "authorization_field_unknown:" + sorted(unknown)[0])
        grant_id = authorization.get("grantId")
        if not isinstance(grant_id, str) or not grant_id.strip():
            raise ScheduledTaskError("authorization_grant_id_required")
        authorized_by = authorization.get("authorizedBy")
        if not isinstance(authorized_by, str) or not authorized_by.strip():
            raise ScheduledTaskError("authorization_subject_required")
        authorized_at = parse_now(
            authorization.get("authorizedAt", moment), field="authorizedAt")
        permissions = authorization.get("permissions")
        if not isinstance(permissions, dict) or not permissions:
            raise ScheduledTaskError("authorization_permissions_required")
        # deny-closed：仅 literal True 授予；缺失/False/字符串 "true" 全拒。
        if permissions.get(REQUIRED_PERMISSION) is not True:
            raise ScheduledTaskError("authorization_permission_not_granted")
        return {
            "grantId": grant_id,
            "authorizedBy": authorized_by,
            "authorizedAt": iso_utc(authorized_at),
            "permissions": dict(permissions),
        }

    # -- ② 读面 ----------------------------------------------------------

    def task_view(self, task_id) -> dict:
        task = self._state["tasks"].get(task_id)
        if task is None:
            raise ScheduledTaskError("task_unknown:" + str(task_id))
        return json.loads(json.dumps(task, ensure_ascii=False))

    def task_list(self) -> list:
        return [self.task_view(task_id)
                for task_id in sorted(self._state["tasks"])]

    def fire_record(self, fire_key) -> dict | None:
        record = self._state["fires"].get(fire_key)
        return json.loads(json.dumps(record, ensure_ascii=False)) \
            if record is not None else None

    # -- ③ 到期轮（幂等发起；missed/failure 纪律） ------------------------

    def run_due_round(self, *, runner, now,
                      max_consecutive_failures: int = 3) -> dict:
        self._gate_open()
        if not callable(runner):
            # 先拒后动：任何状态改变之前具名拒（零标记零游标推进）。
            raise ScheduledTaskError("f137_runner_not_configured")
        if not isinstance(max_consecutive_failures, int) \
                or isinstance(max_consecutive_failures, bool) \
                or max_consecutive_failures < 1:
            raise ScheduledTaskError("failure_policy_invalid")
        moment = parse_now(now)
        report = {"fired": [], "already": [], "missed": [], "unknown": [],
                  "suspended": []}
        for task_id in sorted(self._state["tasks"]):
            task = self._state["tasks"][task_id]
            if task["state"] != "enabled":
                continue
            cursor = (parse_now(task["cursorUtc"])
                      if task["cursorUtc"] else parse_now(task["createdAt"]))
            due = self._occurrences_between(task, cursor, moment)
            if not due:
                continue
            # fail-closed 先检：任一在窗预定时刻仍处 firing（无终态）＝上次
            # 发起未知——本任务本轮零动作（不补 missed、不发起新时刻）。
            blocked = [occ for occ in due
                       if (self._state["fires"].get(_fire_key(
                           task_id, occ)) or {}).get("state") == "firing"]
            if blocked:
                for occ in blocked:
                    report["unknown"].append({
                        "fireKey": _fire_key(task_id, occ),
                        "state": "firing",
                        "code": "occurrence_outcome_unknown"})
                continue
            for earlier in due[:-1]:
                self._record_missed(task, earlier, moment, report)
            target = due[-1]
            self._fire(task, target, runner, moment,
                       max_consecutive_failures, report)
        self._save()
        return report

    def _occurrences_between(self, task, cursor: datetime,
                             moment: datetime) -> list:
        found = []
        probe = cursor
        for _ in range(_ENUMLIMIT_OCCURRENCES):
            occurrence = next_occurrence(task["schedule"], probe)
            if occurrence > moment:
                break
            found.append(occurrence)
            probe = occurrence
        else:
            raise ScheduledTaskError("schedule_enumeration_overflow")
        return found

    def _record_missed(self, task, occurrence: datetime,
                       moment: datetime, report: dict) -> None:
        fire_key = _fire_key(task["id"], occurrence)
        if self._state["fires"].get(fire_key) is None:
            self._state["fires"][fire_key] = {
                "fireKey": fire_key,
                "taskId": task["id"],
                "scheduledUtc": iso_utc(occurrence),
                "state": "missed",
                "recordedAt": iso_utc(moment),
            }
            report["missed"].append({"fireKey": fire_key,
                                     "scheduledUtc":
                                         iso_utc(occurrence)})

    def _fire(self, task, occurrence: datetime, runner, moment: datetime,
              max_consecutive_failures: int, report: dict) -> None:
        fire_key = _fire_key(task["id"], occurrence)
        record = self._state["fires"].get(fire_key)
        if record is not None:
            if record["state"] in TERMINAL_FIRE_STATES \
                    or record["state"] == "unknown_acknowledged":
                # 幂等回执：同一预定时刻零重发；处置完该时刻（cursor 越过）。
                task["cursorUtc"] = record["scheduledUtc"]
                self._save()
                report["already"].append({
                    "fireKey": fire_key,
                    "state": record["state"],
                    "receiptRef": record.get("receiptRef"),
                })
                return
            # firing 且无终态＝上次发起结果未知（进程崩在中间）——
            # fail-closed 阻塞，不自动重发，不推进。
            report["unknown"].append({"fireKey": fire_key,
                                      "state": record["state"],
                                      "code": "occurrence_outcome_unknown"})
            return
        # 原子序：先落 firing 标记（单次 save），终态写入时才推进 cursor。
        record = {
            "fireKey": fire_key,
            "taskId": task["id"],
            "scheduledUtc": iso_utc(occurrence),
            "state": "firing",
            "startedAt": iso_utc(moment),
        }
        self._state["fires"][fire_key] = record
        self._save()
        try:
            receipt = runner(self._task_handoff(task), fire_key, occurrence)
        except Exception as exc:  # 发起失败＝具名回执，不静默吞
            self._finish_failure(task, record, exc, moment,
                                 max_consecutive_failures, report)
            return
        # BaseException（KeyboardInterrupt/SystemExit 等）原样上抛＝
        # 模拟进程死亡：firing 标记已落盘、终态未写＝unknown 面。
        self._finish_enqueued(task, record, receipt, moment, report)

    @staticmethod
    def _task_handoff(task: dict) -> dict:
        return {
            "taskId": task["id"],
            "title": task["title"],
            "schedule": dict(task["schedule"]),
            "action": dict(task["action"]),
            "grantId": task["authorization"]["grantId"],
        }

    def _finish_enqueued(self, task, record, receipt, moment: datetime,
                         report: dict) -> None:
        if not isinstance(receipt, dict):
            raise ScheduledTaskError("runner_receipt_shape_invalid")
        unknown = set(receipt) - set(RUNNER_RECEIPT_FIELDS)
        if unknown:
            raise ScheduledTaskError(
                "runner_receipt_field_unknown:" + sorted(unknown)[0])
        receipt_ref = receipt.get("receiptRef")
        if not isinstance(receipt_ref, str) or not receipt_ref.strip():
            raise ScheduledTaskError("runner_receipt_ref_required")
        record.update({
            "state": "enqueued",
            "finishedAt": iso_utc(moment),
            "receiptRef": receipt_ref,
            "sessionId": receipt.get("sessionId"),
            "messageId": receipt.get("messageId"),
        })
        task["consecutiveFailures"] = 0
        task["cursorUtc"] = record["scheduledUtc"]
        self._save()
        report["fired"].append({
            "fireKey": record["fireKey"],
            "scheduledUtc": record["scheduledUtc"],
            "receiptRef": receipt_ref,
            "sessionId": record.get("sessionId"),
        })

    def _finish_failure(self, task, record, exc: Exception,
                        moment: datetime, max_consecutive_failures: int,
                        report: dict) -> None:
        record.update({
            "state": "launch_failed",
            "finishedAt": iso_utc(moment),
            "errorClass": type(exc).__name__,
            "errorText": str(exc)[:_ERROR_TEXT_LIMIT],
        })
        task["consecutiveFailures"] = \
            int(task.get("consecutiveFailures") or 0) + 1
        task["cursorUtc"] = record["scheduledUtc"]
        suspended = task["consecutiveFailures"] >= max_consecutive_failures
        if suspended:
            task["state"] = "failure_suspended"
            task["suspendedAt"] = iso_utc(moment)
        self._save()
        if suspended:
            report["suspended"].append({"taskId": task["id"],
                                        "fireKey": record["fireKey"]})
        else:
            report["fired"].append({"fireKey": record["fireKey"],
                                    "state": "launch_failed",
                                    "errorClass": record["errorClass"]})

    # -- ④ 未知发起的人核放行（区别于 F23 自动续播） ----------------------

    def reconcile_unknown(self, *, task_id, fire_key, resolution, now,
                          actor_id) -> dict:
        self._gate_open()
        moment = parse_now(now)
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ScheduledTaskError("reconcile_actor_required")
        record = self._state["fires"].get(fire_key)
        if record is None or record.get("taskId") != task_id:
            raise ScheduledTaskError("reconcile_target_unknown")
        if record["state"] != "firing":
            raise ScheduledTaskError(
                "reconcile_state_not_unknown:" + record["state"])
        if resolution != "unknown_acknowledged":
            raise ScheduledTaskError("reconcile_resolution_unknown")
        record.update({
            "state": "unknown_acknowledged",
            "acknowledgedAt": iso_utc(moment),
            "acknowledgedBy": actor_id,
        })
        self._save()
        return json.loads(json.dumps(record, ensure_ascii=False))

    # -- ⑤ 取消即停具名／失败挂起恢复 -------------------------------------

    def cancel_task(self, *, task_id, now, actor_id, reason_ref=None,
                    stop_runner=None) -> dict:
        self._gate_open()
        moment = parse_now(now)
        task = self._state["tasks"].get(task_id)
        if task is None:
            raise ScheduledTaskError("task_unknown:" + str(task_id))
        if task["state"] == "cancelled":
            raise ScheduledTaskError("task_already_cancelled")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ScheduledTaskError("cancel_actor_required")
        # 先验后动：需要停在途会话而 stop runner 未配置＝零改动具名拒。
        in_flight = self._find_in_flight(task)
        if in_flight and stop_runner is None:
            raise ScheduledTaskError("f137_stop_runner_not_configured")
        if in_flight and not callable(stop_runner):
            raise ScheduledTaskError("f137_stop_runner_invalid")
        receipt = {
            "taskId": task_id,
            "state": "cancelled",
            "cancelledAt": iso_utc(moment),
            "cancelledBy": actor_id,
            "cancelReasonRef": reason_ref,
        }
        task["state"] = "cancelled"
        task["cancelledAt"] = receipt["cancelledAt"]
        task["cancelledBy"] = actor_id
        task["cancelReasonRef"] = reason_ref
        # 授权随任务封存（一次性授予，不复用）。
        grant = self._state["grants"].get(task["authorization"]["grantId"])
        if grant is not None:
            grant["state"] = "sealed"
        # 在途已入队会话：显式 stop runner 才碰 core interrupt（F23 端点）；
        # 单个失败如实记 interrupt_failed，不冒成功也不阻断取消本身。
        receipt["stoppedInFlight"] = self._stop_in_flight(
            task, in_flight, moment, stop_runner)
        self._save()
        return receipt

    def _find_in_flight(self, task) -> list:
        return [
            record for record in self._state["fires"].values()
            if record.get("taskId") == task["id"]
            and record.get("state") == "enqueued"
            and record.get("sessionId")
            and not record.get("stopRequestedAt")
        ]

    def _stop_in_flight(self, task, in_flight, moment: datetime,
                        stop_runner) -> list:
        stopped = []
        for record in in_flight:
            try:
                stop_receipt = stop_runner(record["sessionId"],
                                           record["fireKey"])
                record["stopOutcome"] = "interrupt_requested"
                record["stopReceipt"] = (stop_receipt
                                         if isinstance(stop_receipt, str)
                                         else "interrupted")
            except Exception as exc:
                record["stopOutcome"] = (
                    "interrupt_failed:" + type(exc).__name__)
            record["stopRequestedAt"] = iso_utc(moment)
            stopped.append({"fireKey": record["fireKey"],
                            "sessionId": record["sessionId"],
                            "stopOutcome": record["stopOutcome"]})
        return stopped

    def task_unsuspend(self, *, task_id, now, actor_id) -> dict:
        self._gate_open()
        moment = parse_now(now)
        task = self._state["tasks"].get(task_id)
        if task is None:
            raise ScheduledTaskError("task_unknown:" + str(task_id))
        if task["state"] == "cancelled":
            raise ScheduledTaskError("task_already_cancelled")
        if task["state"] != "failure_suspended":
            raise ScheduledTaskError("task_not_suspended")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ScheduledTaskError("unsuspend_actor_required")
        task["state"] = "enabled"
        task["consecutiveFailures"] = 0
        task["unsuspendedAt"] = iso_utc(moment)
        task["unsuspendedBy"] = actor_id
        self._save()
        return self.task_view(task_id)


# ------------------------------------------------- 生产 runner 适配器
# 唯一落点：opencode create+prompt 各一次（复用同一 core loop，F23 面管
# 完成记账）；stop 适配器＝core interrupt 端点。零流消费零事件订阅零轮询
# ——不创第二 Agent loop 的结构性落点（recon AST 钉死白名单）。

def opencode_session_prompt_runner(client, *, workspace_dir):
    """Fire one occurrence = create session (once) + prompt (once)."""

    def run(task_view, fire_key, scheduled_utc) -> dict:
        payload = {"directory": workspace_dir}
        created = client.create(payload)
        data = created.get("data", created) if isinstance(created, dict) \
            else {}
        session_id = data.get("id") if isinstance(data, dict) else None
        if not isinstance(session_id, str) or not session_id:
            raise ScheduledTaskError("runner_session_ref_missing")
        message_id = "msg_f137_" + re.sub(r"[^A-Za-z0-9_.-]", "_",
                                          task_view["taskId"] + "_" + fire_key)
        client.prompt(session_id, {
            "id": message_id,
            "text": "[定时任务 %s｜预定 %s]\n%s" % (
                task_view["taskId"], iso_utc(scheduled_utc),
                task_view["action"]["prompt"]),
        })
        return {"sessionId": session_id, "messageId": message_id,
                "receiptRef": "opencode:" + session_id + ":" + message_id}

    return run


def opencode_session_stop_runner(client):
    """Cancel-in-flight adapter: core interrupt endpoint (F23 stop)."""

    def stop(session_id, fire_key) -> str:
        client.interrupt(session_id)
        return "interrupted:" + fire_key

    return stop


# ---------------------------------------------------------------- 公开入口

def f137_call(method: str, args: dict, config: dict):
    """legal_entry SCHEDULED_TASK_METHODS 分派面（同进程公开入口）。

    config 键：f137_state_root（状态根目录，必填）；f137_runner /
    f137_stop_runner（注入 callable，测试与宿主直配用）；f137_opencode
    {url, headers?, timeout?, workspaceDir}（未注入时构造真实适配器）；
    v2 闸门由 legal_entry literal-True 键先行把关（本函数不重复）。
    """
    state_root = config.get("f137_state_root")
    if not isinstance(state_root, str) or not state_root.strip():
        raise ScheduledTaskError("f137_state_root_not_configured")
    if not isinstance(args, dict):
        raise ScheduledTaskError("f137_params_invalid")
    store = F137TaskStore(Path(state_root) / STORE_FILENAME,
                          v2_enabled=True)

    def need(key: str):
        value = args.get(key)
        if value is None:
            raise ScheduledTaskError(key + "_required")
        return value

    if method == "f137.task_create":
        return store.create_task(
            task_id=need("taskId"), title=need("title"),
            schedule=need("schedule"), action=need("action"),
            authorization=need("authorization"), now=need("now"),
            created_by=need("createdBy"))
    if method == "f137.task_read":
        return store.task_view(need("taskId"))
    if method == "f137.task_list":
        return {"tasks": store.task_list()}
    if method == "f137.task_cancel":
        return store.cancel_task(
            task_id=need("taskId"), now=need("now"),
            actor_id=need("actorId"), reason_ref=args.get("reasonRef"),
            stop_runner=_resolve_adapter(config, "f137_stop_runner",
                                         opencode_session_stop_runner))
    if method == "f137.task_unsuspend":
        return store.task_unsuspend(
            task_id=need("taskId"), now=need("now"),
            actor_id=need("actorId"))
    if method == "f137.run_due_round":
        return store.run_due_round(
            runner=_resolve_adapter(config, "f137_runner",
                                    opencode_session_prompt_runner),
            now=need("now"),
            max_consecutive_failures=args.get("maxConsecutiveFailures", 3))
    if method == "f137.reconcile_unknown":
        return store.reconcile_unknown(
            task_id=need("taskId"), fire_key=need("fireKey"),
            resolution=need("resolution"), now=need("now"),
            actor_id=need("actorId"))
    raise ScheduledTaskError("f137_method_unknown:" + str(method))


def _resolve_adapter(config: dict, key: str, factory):
    """注入 callable 优先；否则 f137_opencode 构造真实适配器；否则 None。"""
    injected = config.get(key)
    if injected is not None:
        return injected
    opencode_cfg = config.get("f137_opencode")
    if isinstance(opencode_cfg, dict) and opencode_cfg.get("url"):
        from opencode_http import Client
        client = Client(opencode_cfg["url"],
                        headers=opencode_cfg.get("headers") or {},
                        timeout=opencode_cfg.get("timeout", 30))
        if factory is opencode_session_stop_runner:
            return opencode_session_stop_runner(client)
        return opencode_session_prompt_runner(
            client, workspace_dir=opencode_cfg.get("workspaceDir")
            or str(Path.cwd()))
    return None
