// 【步骤4·#3 案件看板·补齐件3】案件列表面纯函数（RE-3-案件看板.md 对拍行 45/46/49/52/61-64/65/67/70/71）。
// 文案全部自写（表达隔离）；日期纪律（§3.6）：本地日历日 ISO 字符串比较，非法不猜（null 落沉底位）。
import { boardDayDiff } from "./boardCalendar.js";
import { BOARD_STATUS_DEFS } from "./boardStatus.js";

// ── 域分类（对拍行 61；CB-B4 同构策略，词表自写）：纯前端启发式，宁漏勿误 ──
// 命中链：案号含「刑」→刑事；案由含「罪」→刑事；排除词（检察院/公安局/侦查）压倒词表命中——
// 防交通/行政/国家赔偿类表述误吞；再刑事专属词表命中→刑事；默认非刑事（漏判不误判）。
const CRIMINAL_WORDS = ["刑事", "犯罪", "被告人", "犯罪嫌疑人", "羁押", "逮捕", "起诉书", "缓刑", "刑罚"];
const CRIMINAL_EXCLUDE = ["检察院", "公安局", "侦查"];

export function isCriminalCase(c: { name: string; cause?: string; caseNo?: string }): boolean {
  const caseNo = c.caseNo ?? "";
  const cause = c.cause ?? "";
  if (caseNo.includes("刑")) return true; // 案号程序字 authoritative
  if (cause.includes("罪")) return true; // 案由含罪名
  const hay = `${c.name ?? ""} ${cause}`;
  if (CRIMINAL_EXCLUDE.some((w) => hay.includes(w))) return false; // 排除词压倒词表
  return CRIMINAL_WORDS.some((w) => hay.includes(w));
}

// 域 tabs（对拍行 62/63/65/67）：诉讼=全部；刑事=启发式过滤；执行=状态过滤（显示态，locked 感知）。
export type BoardDomainTab = "civil" | "criminal" | "execution";
export const BOARD_DOMAIN_TABS: ReadonlyArray<{ key: BoardDomainTab; label: string }> = [
  { key: "civil", label: "诉讼" },
  { key: "criminal", label: "刑事" },
  { key: "execution", label: "执行" },
];

export function filterCasesByDomain<T>(
  cases: readonly T[],
  tab: BoardDomainTab,
  law: (c: T) => boolean,
  statusOf: (c: T) => string | null,
): T[] {
  if (tab === "civil") return [...cases];
  if (tab === "criminal") return cases.filter(law);
  return cases.filter((c) => statusOf(c) === "执行中");
}

// ── 案件集口径（对拍行 64；CB：提醒集「非已结案非已调解」/日历集「非已结案」）──
// 只作用于案绑行（案绑日程/时间线抽取行）；独立日程与待办不属于案件集，不过此门。
export function boardCaseGate(displayStatus: string | null | undefined, view: "calendar" | "reminder"): boolean {
  if (displayStatus === "已结案") return false;
  if (view === "reminder" && displayStatus === "已调解") return false;
  return true;
}

// ── 拖拽序（对拍行 45/51；CB-B6 尾分区纪律）──
// 展示序=已结案永远尾分区；非结案段=有 sort_order 升序在前，无序（含新案）按 updated 倒序追加尾。
export function boardDragOrderSeq<T extends { id: string; updatedAt?: string }>(
  cases: readonly T[],
  closedOf: (c: T) => boolean,
  sortOrderOf: (c: T) => number | null,
): T[] {
  const rank = (a: T, b: T): number => {
    const sa = sortOrderOf(a);
    const sb = sortOrderOf(b);
    if (sa !== null && sb !== null && sa !== sb) return sa - sb;
    if (sa !== null !== (sb !== null)) return sa !== null ? -1 : 1; // 有序在前，无序（新案）追加尾
    return (b.updatedAt ?? "").localeCompare(a.updatedAt ?? "");
  };
  const open = cases.filter((c) => !closedOf(c)).sort(rank);
  const closed = cases.filter((c) => closedOf(c)).sort(rank);
  return [...open, ...closed];
}

// 拖放落位：把 dragged 移到 target 位（前插），全序重编号 0..n-1，只回变更行的写路径增量。
export function boardApplyDragOrder<T extends { id: string }>(
  seq: readonly T[],
  draggedId: string,
  targetId: string,
): Array<{ id: string; sortOrder: number }> {
  const ids = seq.map((c) => c.id);
  const from = ids.indexOf(draggedId);
  const to = ids.indexOf(targetId);
  if (from < 0 || to < 0 || from === to) return [];
  const before = [...ids];
  ids.splice(from, 1);
  ids.splice(ids.indexOf(targetId), 0, draggedId);
  const out: Array<{ id: string; sortOrder: number }> = [];
  ids.forEach((id, i) => {
    if (before[i] !== id) out.push({ id, sortOrder: i });
  });
  return out;
}

// ── 四排序键（对拍行 46；CB：状态/诉讼金额/立案时间/最近开庭日，null 沉底，同值 updated 兜底）──
export type BoardSortKey = "status" | "amount" | "filedAt" | "nextHearing";
export const BOARD_SORT_KEYS: ReadonlyArray<{ key: BoardSortKey | "default"; label: string }> = [
  { key: "default", label: "默认桶序" },
  { key: "status", label: "状态" },
  { key: "amount", label: "诉讼金额" },
  { key: "filedAt", label: "立案时间" },
  { key: "nextHearing", label: "最近开庭日" },
];

function statusWeight(name: string | null): number | null {
  const i = BOARD_STATUS_DEFS.findIndex((d) => d.name === name);
  return i >= 0 ? i : null;
}

export function boardSortCasesByKey<T extends { updatedAt?: string }>(
  cases: readonly T[],
  key: BoardSortKey,
  dir: "asc" | "desc",
  valueOf: (c: T) => string | number | null, // 状态=档位名；金额=整型分；日期=YYYY-MM-DD
): T[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...cases].sort((a, b) => {
    const va = valueOf(a);
    const vb = valueOf(b);
    if (va === null && vb === null) return (b.updatedAt ?? "").localeCompare(a.updatedAt ?? "");
    if (va === null) return 1; // null 沉底（两方向一致）
    if (vb === null) return -1;
    const cmp = typeof va === "number" && typeof vb === "number"
      ? va - vb
      : String(va).localeCompare(String(vb), "zh");
    if (cmp !== 0) return sign * cmp;
    return (b.updatedAt ?? "").localeCompare(a.updatedAt ?? "");
  });
}

export { statusWeight as boardStatusWeight };

// ── 排序键数据源（确定性，纯函数）──
// 立案时间=时间线「正式立案」行最早日期，无则「建案/接案」行最早日期，再无=null（沉底）。
export function boardFilingDateOf(
  rows: ReadonlyArray<{ caseId: string | null; type: string; date: string | null }>,
  caseId: string,
): string | null {
  let formal: string | null = null;
  let created: string | null = null;
  for (const r of rows) {
    if (!r || r.caseId !== caseId || !r.date || !/^\d{4}-\d{2}-\d{2}$/.test(r.date)) continue;
    if (r.type === "正式立案") {
      if (formal === null || r.date < formal) formal = r.date;
    } else if (r.type === "建案" || r.type === "接案") {
      if (created === null || r.date < created) created = r.date;
    }
  }
  return formal ?? created;
}

// 最近开庭日=未来最近开庭（案绑 kind=hearing 日程 + 时间线开庭行）；无未来开庭=null（沉底）。
export function boardNextHearingDateOf(
  rows: ReadonlyArray<{ caseId: string | null; date: string; hearing?: boolean }>,
  caseId: string,
  todayStr: string,
): string | null {
  let best: string | null = null;
  for (const r of rows) {
    if (!r || r.caseId !== caseId || !r.hearing) continue;
    const left = boardDayDiff(todayStr, r.date);
    if (left === null || left < 0) continue;
    if (best === null || r.date < best) best = r.date;
  }
  return best;
}

// ── 近期日程按日分组（对拍行 70；LL：30 天窗/按日分组/前 3 条/tone 三档/倒计时）──
export type BoardTone = "urgent" | "soon" | "normal";
export interface BoardRecentItem {
  ref: string;
  kind: string;
  title: string; // 开庭标题已补全（boardHearingDisplayTitle）
  startAt: string | null;
  caseName: string | null;
}
export interface BoardRecentGroup {
  date: string;
  daysLeft: number;
  tone: BoardTone;
  countdown: string; // 自写三态：逾期 N 天 / 今天 / N 天后（窗内恒 ≥0）
  items: BoardRecentItem[];
}

// 开庭标题补全（对拍行 70）：非「开庭|庭审|询问」开头的 hearing 标题自动补「开庭 · 」前缀。
export function boardHearingDisplayTitle(kind: string, title: string): string {
  if (kind !== "hearing") return title;
  const t = title.trim();
  return /^(开庭|庭审|询问)/.test(t) ? t : `开庭 · ${t}`;
}

export function boardRecentGroups(
  entries: ReadonlyArray<{ date: string; kind: string; title: string; ref: string; startAt?: string | null; caseName?: string | null }>,
  todayStr: string,
  opts?: { windowDays?: number; maxGroups?: number },
): { groups: BoardRecentGroup[]; extraDays: number } {
  const windowDays = opts?.windowDays ?? 30;
  const maxGroups = opts?.maxGroups ?? 3;
  const byDate = new Map<string, BoardRecentItem[]>();
  for (const e of entries) {
    const left = boardDayDiff(todayStr, e.date);
    if (left === null || left < 0 || left > windowDays) continue;
    const arr = byDate.get(e.date) ?? [];
    arr.push({ ref: e.ref, kind: e.kind, title: boardHearingDisplayTitle(e.kind, e.title), startAt: e.startAt ?? null, caseName: e.caseName ?? null });
    byDate.set(e.date, arr);
  }
  const all = [...byDate.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([date, items]) => {
      const daysLeft = boardDayDiff(todayStr, date) ?? 0;
      const tone: BoardTone = daysLeft <= 3 ? "urgent" : daysLeft <= 7 ? "soon" : "normal";
      return { date, daysLeft, tone, countdown: daysLeft === 0 ? "今天" : `${daysLeft} 天后`, items };
    });
  return { groups: all.slice(0, maxGroups), extraDays: Math.max(0, all.length - maxGroups) };
}

// ── 今日焦点（对拍行 71；LL：全案最近一条期限/日程，≤3 天红点否则琥珀，逾期优先）──
export interface BoardFocusItem {
  title: string;
  date: string;
  timeLabel: string | null; // HH:MM 或 null=全天
  daysLeft: number; // 负=已逾期
  tone: "red" | "amber";
  countdown: string; // 自写：逾期 N 天 / 今天到期 / N 天
  caseId: string | null;
  caseName: string | null;
  caseNo: string | null;
}

export function boardFocusItem(params: {
  deadlines: ReadonlyArray<{ id: string; title: string; date: string; caseId?: string | null }>;
  events: ReadonlyArray<{ id: string; title: string; date: string; kind?: string; startAt?: string | null; caseId?: string | null }>;
  todayStr: string;
  caseInfoOf?: (caseId: string) => { name: string | null; caseNo: string | null } | null;
}): BoardFocusItem | null {
  const { deadlines, events, todayStr, caseInfoOf } = params;
  type Cand = { title: string; date: string; timeLabel: string | null; daysLeft: number; caseId: string | null };
  const cands: Cand[] = [];
  for (const d of deadlines) {
    const left = boardDayDiff(todayStr, d.date);
    if (left === null) continue;
    cands.push({ title: d.title, date: d.date, timeLabel: null, daysLeft: left, caseId: d.caseId ?? null });
  }
  for (const e of events) {
    const left = boardDayDiff(todayStr, e.date);
    if (left === null) continue;
    cands.push({ title: boardHearingDisplayTitle(e.kind ?? "schedule", e.title), date: e.date, timeLabel: e.startAt ?? null, daysLeft: left, caseId: e.caseId ?? null });
  }
  if (!cands.length) return null;
  // 最紧急=距今日历日最近（逾期项同参——最近一条已逾期期限即焦点）；30 天外不进焦点（空态绿✓语义）
  const inWindow = cands.filter((c) => c.daysLeft <= 30);
  if (!inWindow.length) return null;
  const pick = inWindow.reduce((a, b) => {
    const da = Math.abs(a.daysLeft);
    const db = Math.abs(b.daysLeft);
    if (db !== da) return db < da ? b : a;
    if (b.date !== a.date) return b.date < a.date ? b : a;
    return (b.timeLabel ?? "99:99") < (a.timeLabel ?? "99:99") ? b : a;
  });
  const info = pick.caseId ? caseInfoOf?.(pick.caseId) ?? null : null;
  return {
    title: pick.title,
    date: pick.date,
    timeLabel: pick.timeLabel,
    daysLeft: pick.daysLeft,
    tone: pick.daysLeft <= 3 ? "red" : "amber",
    countdown: pick.daysLeft < 0 ? `逾期 ${-pick.daysLeft} 天` : pick.daysLeft === 0 ? "今天到期" : `${pick.daysLeft} 天`,
    caseId: pick.caseId,
    caseName: info?.name ?? null,
    caseNo: info?.caseNo ?? null,
  };
}

// ── 金额格式化（§3.6：整型分，整数运算禁浮点）──
export function boardYuan(cents: number | null | undefined): string {
  if (cents === null || cents === undefined || !Number.isInteger(cents)) return "-";
  const y = Math.floor(cents / 100);
  const f = cents % 100;
  return `¥${y}.${String(f).padStart(2, "0")}`;
}

// ── 最近期限风险徽章（对拍行 66；LL 列表行红字「逾期 N 天·期限名」GUI 实证口径）──
// 只取该案最近一条已逾期未完期限（最贴近今天的逾期=逾期天数最小者）；无逾期不显（未来项
// 不冒红，红色纪律=只用于逾期与法定期限）。非法日期不猜（null 跳过）。
export interface BoardDeadlineRisk {
  title: string;
  date: string;
  daysLeft: number; // 负=已逾期天数
}

export function boardDeadlineRiskOf(
  items: ReadonlyArray<{ caseId?: string | null; title: string; dueDate: string }>,
  caseId: string,
  todayStr: string,
): BoardDeadlineRisk | null {
  let best: BoardDeadlineRisk | null = null;
  for (const it of items) {
    if (!it || it.caseId !== caseId) continue;
    const left = boardDayDiff(todayStr, it.dueDate);
    if (left === null || left >= 0) continue; // 只收已逾期
    if (best === null || left > best.daysLeft) best = { title: it.title, date: it.dueDate, daysLeft: left };
  }
  return best;
}
