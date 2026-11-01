// 【步骤4·#3 状态机面】11 档工作流状态 UI 单源（RE-3-案件看板.md §3.2/§3.3；对拍行 40-44）。
// 色表/枚举权重同表单源（展示色自绘=表达隔离；枚举值域与桥 matter_service.MATTER_STATUS_DEFS
// 同串同序，board_synthetic E15 单源对拍——UI 侧无桥依赖，桥侧校验器不动）。
// 推断优先级链（CB-B5 同链同序）/locked 展示公式（§3.3）/默认排序桶（CB-B6）全纯函数，探针可对拍。
// 确定性纪律（§3.6）：开庭日期比较=本地日历日 ISO 字符串差值，非法日期不猜（忽略该线索）。
import { boardDayDiff } from "./boardCalendar.js";

export interface BoardStatusDef {
  name: string;
  weight: number; // 枚举序（状态排序键用；与默认排序桶无关——桶见 boardStatusBucket）
  chip: string;   // 自绘色板（Tailwind；表外值由 UI 兜底中性色）
}

export const BOARD_STATUS_DEFS: readonly BoardStatusDef[] = [
  { name: "接案", weight: 0, chip: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
  { name: "立案中", weight: 1, chip: "bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300" },
  { name: "仲裁中", weight: 2, chip: "bg-cyan-100 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-300" },
  { name: "待开庭", weight: 3, chip: "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300" },
  { name: "审理中", weight: 4, chip: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300" },
  { name: "已调解", weight: 5, chip: "bg-teal-100 text-teal-700 dark:bg-teal-950 dark:text-teal-300" },
  { name: "上诉期", weight: 6, chip: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  { name: "二审中", weight: 7, chip: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300" },
  { name: "再审中", weight: 8, chip: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300" },
  { name: "执行中", weight: 9, chip: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300" },
  { name: "已结案", weight: 10, chip: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
];

export const BOARD_STATUS_NAMES: readonly string[] = BOARD_STATUS_DEFS.map((d) => d.name);

export function boardStatusChip(name: string | null | undefined): string {
  return BOARD_STATUS_DEFS.find((d) => d.name === name)?.chip ?? "bg-header text-foreground-subtle";
}

// 排序桶（§3.3）：在办(0)<已调解(1)<已结案(2)
export function boardStatusBucket(name: string | null | undefined): 0 | 1 | 2 {
  if (name === "已结案") return 2;
  if (name === "已调解") return 1;
  return 0;
}

// ── 推断优先级链（对拍行 41；CB-B5 同链同序：从最末端程序往回命中即返）──
export interface BoardStatusSignals {
  execution?: boolean;          // 执行类材料/执行立案
  retrial?: boolean;            // 再审类材料
  secondInstance?: boolean;     // 上诉状/二审节点
  mediation?: boolean;          // 调解书/调解（压过判决书）
  judgment?: boolean;           // 判决书/判决
  hearingDates?: string[];      // 开庭节点日期（≤today=已开）
  courtSessionRecord?: boolean; // 庭审笔录
  acceptance?: boolean;         // 受理/应诉/传票/开庭通知/正式立案
  complaint?: boolean;          // 起诉状/保全申请/申请立案
  arbitrationOnly?: boolean;    // 纯仲裁材料
  engagement?: boolean;         // 委托合同（与默认同档接案）
}

export function inferBoardWorkflowStatus(s: BoardStatusSignals, today: string): string {
  if (s.execution) return "执行中";
  if (s.retrial) return "再审中";
  if (s.secondInstance) return "二审中";
  if (s.mediation) return "已调解"; // 压过判决书（CB 口径）
  if (s.judgment) return "上诉期";
  const opened = (s.hearingDates ?? []).some((d) => {
    const diff = boardDayDiff(today, d);
    return diff !== null && diff <= 0;
  });
  if (opened || s.courtSessionRecord) return "审理中";
  if (s.acceptance) return "待开庭";
  if (s.complaint) return "立案中";
  if (s.arbitrationOnly) return "仲裁中";
  return "接案"; // 委托合同与默认同档；永不自动已结案（closed 只能用户手设）
}

// 时间线/案绑日程行 → 推断线索映射（#4 抽取 CB 14 类型+案绑开庭；口径自写）：
// 执行立案→execution；上诉/二审开庭/二审判决→secondInstance；调解→mediation；判决→judgment；
// 开庭→hearing 日期线索；正式立案→acceptance（受理族）；申请立案/保全→complaint（起诉状/保全申请族）；
// 还款期/解封/开发票/接案/建案等行政与义务行不产生阶段线索。
export function boardSignalsFromRows(
  rows: ReadonlyArray<{ type: string; date?: string | null }>,
): BoardStatusSignals {
  const sig: BoardStatusSignals = {};
  const hearings: string[] = [];
  for (const r of rows) {
    if (!r) continue;
    switch (r.type) {
      case "执行立案": sig.execution = true; break;
      case "上诉": case "二审开庭": case "二审判决": sig.secondInstance = true; break;
      case "调解": sig.mediation = true; break;
      case "判决": sig.judgment = true; break;
      case "开庭": if (r.date) hearings.push(r.date); break;
      case "正式立案": sig.acceptance = true; break;
      case "申请立案": case "保全": sig.complaint = true; break;
      default: break;
    }
  }
  if (hearings.length) sig.hearingDates = hearings;
  return sig;
}

// 展示状态公式（§3.3）：locked?用户值:(推断非接案?推断:(用户历史值||推断))。
// userHistory=无线索时的历史兜底位（单机无 LLM 历史值恒传 null——参数位与 CB 三态语义对齐保留）。
export function boardDisplayStatus(params: {
  locked: boolean;
  userValue: string | null;
  userHistory: string | null;
  inferred: string;
}): string {
  const { locked, userValue, userHistory, inferred } = params;
  if (locked) return userValue ?? inferred;
  return inferred !== "接案" ? inferred : (userHistory ?? inferred);
}

// 默认排序（对拍行 44；CB-B6）：稳定桶 在办(0)<已调解(1)<已结案(2)，桶内 updated_at 倒序；
// 已结案永远尾分区（即使用户在别处前置——本面暂无拖拽序，桶序即默认序）。
export function boardSortCasesByBucket<T extends { workflowStatus?: string | null; updatedAt?: string }>(
  cases: readonly T[],
): T[] {
  return [...cases].sort(
    (a, b) =>
      boardStatusBucket(a.workflowStatus) - boardStatusBucket(b.workflowStatus)
      || (b.updatedAt ?? "").localeCompare(a.updatedAt ?? ""),
  );
}
