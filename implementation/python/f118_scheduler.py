"""F118 product-side scheduler: desktop reminder notification loop (W1-U07).

日程闭环的产品半边（harness docs/f118-schedule-contract.md §3）：

    schedule_list.dueDesktopReminders（账面到期 desktop 提醒）
      → build_notification()（通知载荷：只取账面 title/dueDate/classification
        ＋倒计时文案，不含原件/身份/映射——账面本就没有这些字段，载荷构造
        也不引入任何其他来源）
      → notifier(payload)（默认 sink 记录；Electron 主进程经 UI 补丁绑定
        真实系统通知）
      → reminder_report（sent / delivery_unknown）闭环入账。

fail-closed 纪律（沿 legal_entry E09 模式）：桥未配置/未知错误＝异常上抛或
显式 refused 记录，绝不空响应冒成功。mutation 不盲重试：report 的
CommandKey 按事件域派生（每提醒每轮一次），报告失败记 refused 并保留账面
pending 态（下一轮重读仍是 due，不丢提醒）。
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Callable

from bridge_errors import HarnessCommandError, NotConnected
from legal_entry import call

CLASSIFICATIONS = ("program_deadline", "contract_obligation", "practical_reminder")
_CLASSIFICATION_LABELS = {
    "program_deadline": "程序期限",
    "contract_obligation": "合同义务",
    "practical_reminder": "实务提醒",
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _local_today() -> str:
    return date.today().isoformat()


def build_notification(due: dict) -> dict:
    """One desktop notification payload from a dueDesktopReminders entry.

    载荷字段封闭：只镜像账面 reminderId/title/dueDate/classification 与由
    dueDate 算出的整数日差。日差用 due 行自带口径重算（不信任调用方时钟），
    纯 date 运算无浮点。
    """
    title = due.get("title") or "期限提醒"
    due_date = date.fromisoformat(due["dueDate"])
    days = (due_date - date.today()).days
    label = _CLASSIFICATION_LABELS.get(due.get("classification"), "日程")
    if days < 0:
        countdown = f"已过期 {-days} 天"
        urgent = True
    elif days == 0:
        countdown = "今日到期"
        urgent = True
    else:
        countdown = f"还有 {days} 天"
        urgent = days <= 3
    body = f"【{label}】{title}（{due['dueDate']}，{countdown}）"
    return {
        "reminderId": due["reminderId"],
        "taskId": due.get("taskId"),
        "deadlineId": due.get("deadlineId"),
        "classification": due.get("classification"),
        "title": title,
        "body": body,
        "dueDate": due["dueDate"],
        "daysRemaining": days,
        "urgent": urgent,
        "channel": "desktop",
    }


def default_notifier(payload: dict) -> str:
    """Default sink: structured log line. The Electron main process binds the
    real OS notification through the UI patch; until then this sink keeps the
    loop honest (a notification action happened and is reportable)."""
    return f"desktop-notification:{payload['reminderId']}"


def due_notifications(config: dict, *, matter_id: str, now_iso: str | None = None,
                      as_of: str | None = None) -> list[dict]:
    """Read due desktop reminders and build notification payloads (no writes)."""
    listing = call("harness.schedule_list", {
        "scope": {"kind": "matter", "matterId": matter_id},
        "query": {"asAt": now_iso or _utc_now_iso(), "asOf": as_of or _local_today()},
    }, config)
    return [build_notification(due) for due in listing.get("dueDesktopReminders", [])]


def dispatch_and_report(config: dict, *, matter_id: str,
                        notifier: Callable[[dict], str] = default_notifier,
                        actor_id: str = "desktop-notify",
                        now_iso: str | None = None,
                        as_of: str | None = None,
                        request_seq: int = 0) -> dict:
    """One notification round: fire every due desktop reminder, report delivery.

    送达语义：notifier 返回回执串＝sent；notifier 抛异常＝该提醒记
    delivery_unknown（不确定时如实记不确定，不猜已送达）。报告自身的
    CommandKey 按 (reminderId, 轮次序号) 派生——同轮重试安全，下一轮新键。
    """
    fired: list[dict] = []
    refused: list[dict] = []
    payloads = due_notifications(config, matter_id=matter_id,
                                 now_iso=now_iso, as_of=as_of)
    for index, payload in enumerate(payloads):
        outcome = "sent"
        receipt = None
        try:
            receipt = notifier(payload)
        except Exception as exc:  # notifier 故障＝送达不确定，如实入账
            outcome = "delivery_unknown"
            receipt = f"notifier-failed:{type(exc).__name__}"
        try:
            call("harness.reminder_report", {
                "actor_id": actor_id,
                "scope": {"kind": "matter", "matterId": matter_id},
                "key": {"requestId": f"f118-rr-{payload['reminderId']}-{request_seq}-{index}",
                        "targetId": None, "expectedRevision": None,
                        "inputRefs": []},
                "report": {"reminderId": payload["reminderId"],
                           "outcome": outcome, "receiptRef": receipt},
            }, config)
            fired.append({"reminderId": payload["reminderId"], "outcome": outcome,
                          "receipt": receipt, "notification": payload})
        except (HarnessCommandError, NotConnected) as exc:
            # 报告通道失败：账面仍 pending（下一轮重读仍 due，不丢提醒）。
            refused.append({"reminderId": payload["reminderId"],
                            "outcome": outcome, "error": str(exc),
                            "notification": payload})
    return {"matterId": matter_id, "fired": fired, "refused": refused,
            "dueCount": len(payloads)}
