// 【步骤4·#3 看板日历面】月历网格/期限预警阶梯/案件下一节点 纯函数（RE-3 §3.4-6 + 对拍行 84/91）。
// 日期纪律（§3.6）：一律本地日历日 ISO 字符串比较；差值用归零到日的 Date 只作差值，无时区隐式转换。

export interface BoardMonthCell {
  date: string | null; // YYYY-MM-DD；null=补位空格
  inMonth: boolean;
}

/** 整月网格：周一起、固定 42 格（对拍行 28）；非当月格仍带日期（淡显由 UI 决定）。 */
export function boardMonthCells(year: number, month: number): BoardMonthCell[] {
  const first = new Date(year, month - 1, 1);
  const lead = (first.getDay() + 6) % 7; // 周一=0
  const cells: BoardMonthCell[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(year, month - 1, 1 - lead + i);
    cells.push({
      date: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`,
      inMonth: d.getMonth() === month - 1,
    });
  }
  return cells;
}

/** 本地日历日差值（to - from，天）；入参须 YYYY-MM-DD 真日历日（格式或日历日非法返回 null，不猜——
 *  2026-02-30 这类假日按 Date 翻转会伪装成 3 月 2 日，须回读年月日剔除）。 */
export function boardDayDiff(fromDate: string, toDate: string): number | null {
  const p = (s: string) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return null;
    const y = Number(m[1]);
    const mo = Number(m[2]);
    const d = Number(m[3]);
    const t = new Date(y, mo - 1, d);
    return t.getFullYear() === y && t.getMonth() === mo - 1 && t.getDate() === d ? t.getTime() : null;
  };
  const a = p(fromDate);
  const b = p(toDate);
  if (a === null || b === null) return null;
  return Math.round((b - a) / 86_400_000);
}

export function boardTodayStr(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

// 提醒档位文案单源（§3.4-6：与 #17 期限引擎偏移并集同源，不另造常量表——#17 接入方从这里取）
export const BOARD_DEADLINE_TIERS = ["T-3", "T-1", "T-0", "T+1"] as const;

export interface BoardLadderBucket {
  key: "overdue" | "d3" | "d7" | "d30";
  count: number;
  items: Array<{ id: string; title: string; dueDate: string; daysLeft: number }>;
}

/**
 * 期限预警阶梯（对拍行 91；LL schedule-view 阶梯卡等量）：未完期限按剩余天数四桶——
 * <0 已逾期 / 0..3 / 4..7 / 8..30；窗「未来 30 天」（更远不计入）。
 * 未完期限源=未完成待办 dueDate + kind=deadline 日程（随 #17 期限引擎接入后由规则产物供给）。
 */
export function boardDeadlineLadder(
  items: ReadonlyArray<{ id: string; title: string; dueDate: string }>,
  todayStr: string,
): BoardLadderBucket[] {
  const buckets: BoardLadderBucket[] = [
    { key: "overdue", count: 0, items: [] },
    { key: "d3", count: 0, items: [] },
    { key: "d7", count: 0, items: [] },
    { key: "d30", count: 0, items: [] },
  ];
  for (const it of items) {
    const left = boardDayDiff(todayStr, it.dueDate);
    if (left === null || left > 30) continue; // 非法日期不猜；30 天外不进阶梯窗
    const idx = left < 0 ? 0 : left <= 3 ? 1 : left <= 7 ? 2 : 3;
    const bucket = buckets[idx];
    if (!bucket) continue;
    bucket.count += 1;
    bucket.items.push({ ...it, daysLeft: left });
  }
  for (const b of buckets) b.items.sort((x, y) => x.dueDate.localeCompare(y.dueDate) || x.id.localeCompare(y.id));
  return buckets;
}

// 月历色点阈值（对拍行 28；实跑 CB-B12：≤7 红/≤30 琥珀/31+ 按 kind 蓝/紫/绿/灰）
export type BoardDotColor = "red" | "amber" | "blue" | "purple" | "green" | "gray";

/** 色点色：距今天数≤7 红、≤30 琥珀，其余按 kind（hearing 蓝/todo 紫/schedule 绿/其余灰）；daysLeft 未知按 kind。 */
export function boardCellDotColor(daysLeft: number | null, kind: string): BoardDotColor {
  if (daysLeft !== null && daysLeft <= 7) return "red";
  if (daysLeft !== null && daysLeft <= 30) return "amber";
  if (kind === "hearing") return "blue";
  if (kind === "todo") return "purple";
  if (kind === "schedule") return "green";
  return "gray";
}

export interface BoardNextNode {
  date: string;
  title: string;
  daysAway: number;
}

/**
 * 案件下一节点（对拍行 84：看板卡显示下一节点）。数据源=该案绑定的日程 + 时间线阶段节点行
 * （经 boardShapeTimelineRows 整编：#4 翻牌输入源，行政登记行/孪生行已在整编层剔除），
 * 取最早一个今天及以后的；无未来节点返回 null（板面显「暂无排期节点」）。
 */
export function boardNextCaseNode(
  events: ReadonlyArray<{ id: string; date: string; title: string; caseId: string | null }>,
  caseId: string,
  todayStr: string,
): BoardNextNode | null {
  let best: (BoardNextNode & { id: string }) | null = null;
  for (const ev of events) {
    if (!ev || ev.caseId !== caseId) continue;
    const daysAway = boardDayDiff(todayStr, ev.date);
    if (daysAway === null || daysAway < 0) continue; // 过往节点不占「下一节点」
    // 日期升序，同日取 id 序最小（确定性）
    if (!best || ev.date < best.date || (ev.date === best.date && ev.id < best.id)) {
      best = { id: ev.id, date: ev.date, title: ev.title, daysAway };
    }
  }
  if (!best) return null;
  return { date: best.date, title: best.title, daysAway: best.daysAway };
}

// ── 【#4 翻牌行整编】时间线行进看板前的两道确定性整编（纯函数，合成自测 E14 对拍）──
// 背景 defect（2026-10-28 走查 W12 实证）：#4 翻牌把时间线 dated 行并入看板后——
//   ①「建案」等行政登记行（映射 kind=schedule、日期=动作发生当日）恒压过未来里程碑，
//     当日建案的案件卡永远显「建案（今天）」而非真实下一阶段节点；
//   ②案绑 hearing/deadline 日程写入时桥侧自动生成「开庭排期/期限登记」孪生时间线行，
//     与日程行同案同日不同 id——日历双份同事实、下一节点同日 tie 时通用名「开庭排期」
//     压过用户所取的日程标题（boardNextCaseNode 同日取 id 序最小，cev: < evt: 恒先）。
// 两道整编（对拍行 27 sourceKey 去重语义 + 对拍行 84 节点=阶段里程碑语义）：
//   孪生让位：时间线行 caseId@date 与案绑日程行相碰→丢弃时间线行（日程行=用户标题权威）；
//   阶段过滤：stageNodeOnly=true 时再丢弃 kind=schedule 的行政登记行（建案/任务登记/材料登记
//   等——它们不是阶段节点，案件卡无未来节点时回「暂无排期节点」，RE-3 件4 口径）。
export function boardShapeTimelineRows<T extends { id: string; date: string; caseId: string | null; kind: string }>(
  rows: ReadonlyArray<T>,
  boardEvents: ReadonlyArray<{ caseId: string | null; date: string }>,
  stageNodeOnly: boolean,
): Array<T> {
  const twinKeys = new Set(
    boardEvents.filter((e) => e.caseId).map((e) => `${e.caseId}@${e.date}`),
  );
  return rows.filter((t) => {
    if (twinKeys.has(`${t.caseId}@${t.date}`)) return false; // 孪生行让位日程行
    if (stageNodeOnly && t.kind === "schedule") return false; // 行政登记行不作阶段节点
    return true;
  });
}
