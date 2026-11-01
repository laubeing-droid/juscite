// 【步骤4·#3 案件看板·补齐件】重要提醒位+今日简报 纯函数（RE-3 §2.3 行 12-17/§2.2 行 7 简报五级/§3.4-2）。
// 等量 CB homeReminderEngine 口径（实跑 CB-B9 旁证），文案全自写：
//   重要位案件源=开庭（hearing ≤365d 且未过期）+保全类期限（isPreservation ≤60d 且未过期）；
//   非保全类期限不进重要位（只进日历，CB includeNonPreservationDeadlines=false 口径）；
//   +带日期待办（todo）+独立日程（manual）合并后截 12 条；
//   urgency=负→逾期 / hearing≤30 / 其他≤90→紧急 / 否则普通；
//   排序=逾期→紧急→普通→天数升序→开庭先；色调=逾期或紧急≤7 红/其余紧急琥珀/普通灰；
//   倒计时三态=今天 / N 天 / 逾期 N 天。
// 日期纪律（§3.6）：本地日历日字符串+boardDayDiff 归零差值，无时区隐式转换。
import { boardDayDiff } from "./boardCalendar.js";

export const HEARING_WINDOW_DAYS = 365;
export const PRESERVATION_WINDOW_DAYS = 60;
export const URGENT_HEARING_DAYS = 30;
export const URGENT_OTHER_DAYS = 90;
export const RED_TONE_DAYS = 7;
export const IMPORTANT_MAX = 12;

export type ImportantKind = "hearing" | "deadline" | "todo" | "manual";

export interface ImportantInput {
  id: string;
  kind: ImportantKind; // CB 事件四分类：开庭/期限（内分保全与非保全）/带日期待办/独立日程
  title: string;
  date: string; // YYYY-MM-DD
  isPreservation?: boolean; // 保全类期限标记（#4/#6 保全抽取接入后置真）
}

export interface ImportantItem {
  id: string;
  kind: ImportantKind;
  title: string;
  date: string;
  isPreservation: boolean; // 保全型（五型图标之盾警型取用）
  daysLeft: number;
  urgency: "overdue" | "urgent" | "normal";
  countdown: string; // 自写三态词：今天 / N 天 / 逾期 N 天
  tone: "red" | "amber" | "gray";
}

/** 倒计时三态文案（实跑 CB-B2 等量，措辞自写）。 */
export function importantCountdown(daysLeft: number): string {
  if (daysLeft === 0) return "今天";
  if (daysLeft > 0) return `${daysLeft} 天`;
  return `逾期 ${-daysLeft} 天`;
}

/**
 * 重要位构建：窗口过滤（开庭 ≤365d 未过期；保全 ≤60d 未过期；非保全期限不进）+
 * todo/manual 全量（含逾期）→ 排序（逾期→紧急→普通→天数升序→开庭先）→ 截 12。
 */
export function buildImportantReminders(items: readonly ImportantInput[], todayStr: string): ImportantItem[] {
  const out: ImportantItem[] = [];
  for (const it of items) {
    const daysLeft = boardDayDiff(todayStr, it.date);
    if (daysLeft === null) continue; // 非法日期不猜（§3.6）
    if (it.kind === "hearing") {
      if (daysLeft < 0 || daysLeft > HEARING_WINDOW_DAYS) continue; // 过期开庭丢/超窗丢
    } else if (it.kind === "deadline" && it.isPreservation) {
      if (daysLeft < 0 || daysLeft > PRESERVATION_WINDOW_DAYS) continue; // 保全 60d 窗且未过期
    } else if (it.kind === "deadline") {
      continue; // 非保全期限不进重要位（只进日历）
    }
    const urgency: ImportantItem["urgency"] =
      daysLeft < 0 ? "overdue"
        : (it.kind === "hearing" ? daysLeft <= URGENT_HEARING_DAYS : daysLeft <= URGENT_OTHER_DAYS) ? "urgent"
          : "normal";
    out.push({
      id: it.id, kind: it.kind, title: it.title, date: it.date,
      isPreservation: Boolean(it.isPreservation), daysLeft, urgency,
      countdown: importantCountdown(daysLeft),
      tone: urgency === "overdue" || (urgency === "urgent" && daysLeft <= RED_TONE_DAYS) ? "red"
        : urgency === "urgent" ? "amber" : "gray",
    });
  }
  const order: Record<ImportantItem["urgency"], number> = { overdue: 0, urgent: 1, normal: 2 };
  out.sort((a, b) =>
    order[a.urgency] - order[b.urgency]
    || a.daysLeft - b.daysLeft
    || (a.kind === "hearing" ? -1 : 0) - (b.kind === "hearing" ? -1 : 0)
    || a.id.localeCompare(b.id));
  return out.slice(0, IMPORTANT_MAX);
}

export interface BriefingCaseLite {
  id: string;
  updatedAt: string; // ISO 或可比较时间串
}

export interface BriefingLevel {
  level: "red" | "amber" | "normal";
  text: string; // 自写行动句
  anchor: "important" | "calendar" | "cases"; // 面板内滚动锚
}

/**
 * 今日简报五级（§2.2 行 7；§3.5 本版做静态简报段）：
 * 红提醒>0→红（查看提醒）；橙提醒>0→橙（扫一眼日程）；
 * 材料抽取失败级=橙——随 #6 抽取态计数接入（本函数预留 materialFailures 入参，接入前恒 0）；
 * 48h 内案件更新→平（看更新）；默认→平（平静句）。点击跳对应锚。
 */
export function briefingLevel(params: {
  important: readonly ImportantItem[];
  cases?: readonly BriefingCaseLite[];
  nowMs?: number;
  materialFailures?: number;
}): BriefingLevel {
  const { important, cases = [], nowMs = Date.now(), materialFailures = 0 } = params;
  if (important.some((i) => i.urgency === "overdue")) {
    return { level: "red", text: "有逾期事项，点此查看提醒", anchor: "important" };
  }
  if (important.some((i) => i.urgency === "urgent")) {
    return { level: "amber", text: "近期有紧急日程，扫一眼日历", anchor: "calendar" };
  }
  if (materialFailures > 0) {
    return { level: "amber", text: `有 ${materialFailures} 份材料抽取失败，点此查看`, anchor: "cases" };
  }
  const H48 = 48 * 3600_000;
  const recent = cases.some((c) => {
    const t = Date.parse(c.updatedAt);
    return Number.isFinite(t) && nowMs - t <= H48 && nowMs - t >= -60_000; // 时钟小回拨容忍
  });
  if (recent) {
    return { level: "normal", text: "近两天案件有更新，点此回看", anchor: "cases" };
  }
  return { level: "normal", text: "暂无待急事项，从日历安排下一步", anchor: "calendar" };
}

/**
 * 日程删除确认文案（对拍行 32：AI 派生 vs 手工记录两类区分）。
 * AI 派生=来自 #4/#6 材料识别的派生日程（删除仅隐藏、不删原始识别数据——覆盖层纪律）；
 * 手工=用户自建日程（真删）。本表现无 AI 派生行（原值不在本表），派生分支供 #4/#6 接入后启用。
 */
export function boardDeleteConfirmCopy(isAiDerived: boolean, title: string): string {
  return isAiDerived
    ? `日程「${title}」来自材料识别：删除仅隐藏这条日程，不改动原始识别数据；之后可在覆盖层里恢复。`
    : `删除日程「${title}」？该日程为手工记录，删除后不可恢复。`;
}
