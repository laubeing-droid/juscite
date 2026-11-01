// 【步骤4·#3 看板日历面】提前提醒引擎纯函数（RE-3-案件看板.md §3.4-5；等量 LawX reminders.js 实跑 X1/X2 口径）。
// 60s 扫描节奏由宿主 hook 提供，本模块只做确定性窗口计算（UI 侧纯函数，桥不预做——车道决策 2026-10-27）：
//   触发窗=[开火时刻-提前量, 开火时刻+60s 宽限]；开火 24h 外不开火；错过窗口（>开火+60s）不补发；
//   fired 键集进程内去重（键含开火时刻——改期/改提前量=新键=新提醒，LL 确定性主键同语义）。
// 日期纪律（§3.6）：date(YYYY-MM-DD)+HH:MM 分量构造本地 Date，无时区隐式转换。
// 通知面：title 固定、body=标题 · 开始时间（对拍行 85；isSupported 检查+异常静默在宿主 notify 实现）。
import { suppressedByUnseal } from "./boardPreservation.js";

export const BOARD_SCAN_INTERVAL_MS = 60_000; // 对拍行 85：60s 扫
export const BOARD_FIRE_GRACE_MS = 60_000; // 开火后 60s 宽限
export const BOARD_24H_WINDOW_MS = 24 * 60 * 60_000; // 开火 24h 外不开火
export const BOARD_DEFAULT_LEAD_MINUTES = 30; // 提前量默认 30min（可按条覆盖）

export interface BoardReminderEvent {
  id: string;
  date: string; // YYYY-MM-DD
  title: string;
  startAt: string | null; // HH:MM；null=date-only 行（按 dayFireTime 归一）
  remind: boolean;
  remindMinutes: number;
}

export interface BoardReminderTodo {
  id: string;
  caseId: string | null;
  title: string;
  done: boolean;
  dueDate: string | null; // YYYY-MM-DD；date-only，按 dayFireTime 归一
}

export interface BoardReminderFire {
  key: string;
  source: "evt" | "todo";
  sourceId: string;
  title: string; // 固定标题（宿主传入）
  body: string; // 标题 · 开始时间
}

export interface BoardReminderScan {
  fire: BoardReminderFire[];
  firedKeys: Set<string>;
}

/** date(YYYY-MM-DD) + HH:MM → 本地时刻毫秒；格式非法返回 null（不猜）。 */
export function boardFireMomentMs(date: string, timeOfDay: string): number | null {
  const d = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  const t = /^(\d{2}):(\d{2})$/.exec(timeOfDay);
  if (!d || !t) return null;
  return new Date(Number(d[1]), Number(d[2]) - 1, Number(d[3]), Number(t[1]), Number(t[2])).getTime();
}

export function boardFireKey(source: "evt" | "todo", id: string, fireMs: number): string {
  return `${source}:${id}@${fireMs}`;
}

/** body 的开始时间标签：MM-DD HH:MM（本地日历日语义，不做时区换算）。 */
export function boardFireLabel(date: string, timeOfDay: string): string {
  return `${date.slice(5, 10)} ${timeOfDay}`;
}

/**
 * 扫描一轮（纯函数）：返回本轮应开火的提醒与新 fired 键集。
 * events 取 remind=1 行（开火时刻=startAt ?? dayFireTime）；todos 取未完成且有 dueDate 行（开火=dayFireTime）。
 *提前量：逐条 remindMinutes；非法值回落默认 30（LX 非法回退同语义）。
 */
export function scanBoardReminders(params: {
  events: readonly BoardReminderEvent[];
  todos: readonly BoardReminderTodo[];
  nowMs: number;
  firedKeys: ReadonlySet<string>;
  dayFireTime: string;
  fixedTitle: string;
}): BoardReminderScan {
  const { events, todos, nowMs, firedKeys, dayFireTime, fixedTitle } = params;
  const nextFired = new Set(firedKeys);
  const fire: BoardReminderFire[] = [];
  const consider = (
    key: string, source: "evt" | "todo", sourceId: string, title: string,
    startLabel: string, fireMs: number, leadMinutes: number,
  ): void => {
    if (firedKeys.has(key)) return; // 二次扫描去重（X1 实跑口径）
    const lead = (Number.isInteger(leadMinutes) && leadMinutes >= 0 ? leadMinutes : BOARD_DEFAULT_LEAD_MINUTES) * 60_000;
    if (fireMs - nowMs > BOARD_24H_WINDOW_MS) return; // 24h 外不开火
    if (nowMs < fireMs - lead) return; // 未进提前窗
    if (nowMs > fireMs + BOARD_FIRE_GRACE_MS) return; // 错过窗口不补发
    nextFired.add(key);
    fire.push({ key, source, sourceId, title: fixedTitle, body: `${title} · ${startLabel}` });
  };
  for (const ev of events) {
    if (!ev || !ev.remind) continue;
    const timeOfDay = ev.startAt ?? dayFireTime;
    const fireMs = boardFireMomentMs(ev.date, timeOfDay);
    if (fireMs === null) continue;
    consider(boardFireKey("evt", ev.id, fireMs), "evt", ev.id, ev.title,
      boardFireLabel(ev.date, timeOfDay), fireMs, ev.remindMinutes);
  }
  for (const td of todos) {
    if (!td || td.done || !td.dueDate) continue;
    const fireMs = boardFireMomentMs(td.dueDate, dayFireTime);
    if (fireMs === null) continue;
    consider(boardFireKey("todo", td.id, fireMs), "todo", td.id, td.title,
      boardFireLabel(td.dueDate, dayFireTime), fireMs, BOARD_DEFAULT_LEAD_MINUTES);
  }
  return { fire, firedKeys: nextFired };
}

// ── 【#4 时间线节点→提醒】对拍 34（CB E1）补齐（2026-10-28）：时间线开庭/还款期/保全三族
// 节点喂同一提醒引擎（同源同覆盖：软删行已在 caseEvent* 读面 deleted=0 过滤，覆盖后值即行现值）。
//   开庭类（开庭/二审开庭）→当日提醒；还款期→expires_at 优先、类型名含「还款/分期」回落 date；
//   保全→expires_at 到期提醒（无 expires_at 不猜年限——期限推算属抽取线，fail-closed）；
//   后置解封（解封行日期≥保全行日期）压制保全提醒（CB E1「解封后自动取消续封提醒」/
//   CB-B11 同语义，suppressedByUnseal 单源；数据行不动，只在提醒输入层剔除）；
//   与案绑日程同案同日的孪生行让位（防同事实双通知，boardShapeTimelineRows 同规）。
// 标题=「案名 · 类型」（案名缺失退类型，文案自写）；开火时刻=startAt ?? dayFireTime（date-only
// 归一口径不变）；提前量默认 30min；24h 窗/去重/不补发由 scanBoardReminders 统一裁定。
export interface TimelineReminderEvent {
  eventId: string;
  matterId: string;
  eventType: string;
  date: string | null;
  expiresAt: string | null;
}

export function boardTimelineReminderInputs(params: {
  caseEvents: readonly TimelineReminderEvent[];
  boardEvents: ReadonlyArray<{ caseId: string | null; date: string }>;
  caseNameOf: (matterId: string) => string | null;
}): BoardReminderEvent[] {
  const { caseEvents, boardEvents, caseNameOf } = params;
  const twinKeys = new Set(boardEvents.filter((e) => e.caseId).map((e) => `${e.caseId}@${e.date}`));
  const suppressed = suppressedByUnseal(
    caseEvents.filter((c) => c.eventType === "保全").map((p) => ({ id: p.eventId, startDate: p.date })),
    caseEvents.filter((c) => c.eventType === "解封").map((u) => ({ id: u.eventId, date: u.date ?? "" })),
  );
  const out: BoardReminderEvent[] = [];
  for (const c of caseEvents) {
    if (!c || suppressed.has(c.eventId)) continue; // 解封后自动取消续封提醒
    let due: string | null = null;
    if (c.eventType === "开庭" || c.eventType === "二审开庭") due = c.date;
    else if (c.eventType === "还款期") due = c.expiresAt ?? (/还款|分期/.test(c.eventType) ? c.date : null);
    else if (c.eventType === "保全") due = c.expiresAt;
    else continue; // 非提醒三族不进（E1 口径）
    if (!due || !/^\d{4}-\d{2}-\d{2}$/.test(due)) continue; // 无日期不提醒（B13 同铁律，不造日历日）
    if (twinKeys.has(`${c.matterId}@${due}`)) continue; // 孪生行让位案绑日程（防双通知）
    const name = caseNameOf(c.matterId);
    out.push({
      id: `cev:${c.eventId}`,
      date: due,
      title: name ? `${name} · ${c.eventType}` : c.eventType,
      startAt: null,
      remind: true,
      remindMinutes: BOARD_DEFAULT_LEAD_MINUTES,
    });
  }
  return out;
}
