// 【功能 #42 电子数据取证】UI 视图模型（RE-42 §3.3 五分区展示逻辑纯函数层）。
// 数据面=/api/edisc/* 桥端点族（tools/bridge/edisc_service.mjs）；本文件零 I/O 零 React，
// 徽章映射/分组/可读差异/律师闸判定收敛于此，便于 UI 合同测试（vitest ediscPanelModel）。
// 文案全部自写（表达隔离）；档位/标记值域=桥闭集（reviewKernel FLAG_LEVELS/FLAG_TAGS/PROOF_STRENGTHS）。

export type EdiscParseStatus = "pending" | "parsing" | "done" | "failed";
export type EdiscOcrStatus = "not_required" | "required";
export type EdiscSourceKind = "chat" | "statement" | "table" | "generic";
export type EdiscFlagLevel = "ok" | "doubt" | "insufficient";

// §3.3 五分区（面板内页签；顺序=施工动线：进场→行面→归类→页卡→审查）
export const EDISC_SECTIONS = [
  { key: "sources", label: "源列表" },
  { key: "rows", label: "行浏览" },
  { key: "board", label: "归类看板" },
  { key: "pages", label: "页卡阅读" },
  { key: "review", label: "审查工作台" },
] as const;
export type EdiscSectionKey = (typeof EDISC_SECTIONS)[number]["key"];

export const EDISC_KIND_LABELS: Record<EdiscSourceKind, string> = {
  chat: "聊天记录",
  statement: "转账流水",
  table: "业务表格",
  generic: "通用文件",
};

// A4 三态底座徽章（哈希态并入解析徽章文案；展示词自写）
export const EDISC_PARSE_BADGE: Record<EdiscParseStatus, { label: string; cls: string }> = {
  pending: { label: "待解析", cls: "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300" },
  parsing: { label: "解析中", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  done: { label: "已解析", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  failed: { label: "解析失败", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
};
export const EDISC_OCR_BADGE: Record<EdiscOcrStatus, { label: string; cls: string }> = {
  not_required: { label: "无需 OCR", cls: "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300" },
  required: { label: "需 OCR（本版未启用）", cls: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300" },
};

// F3 三档色标（✅ 明显充分 / ✅+⚠️ 存疑保留=默认档 / ❌ 明显不足）
export const EDISC_LEVEL_BADGE: Record<EdiscFlagLevel, { label: string; cls: string }> = {
  ok: { label: "明显充分", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  doubt: { label: "存疑保留", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  insufficient: { label: "明显不足", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
};

// ── B4 行地址三件套（sourceId+tableName+行区间；展示串供清单/引用处复用）──
export interface EdiscRowRef {
  kind: "rows";
  sourceId: string;
  tableName: string;
  rowStart: number;
  rowEnd: number;
}
export function rowRefOf(sourceId: string, tableName: string, rowNo: number): EdiscRowRef {
  return { kind: "rows", sourceId, tableName, rowStart: rowNo, rowEnd: rowNo };
}
export function formatRowAddress(ref: EdiscRowRef): string {
  const span = ref.rowStart === ref.rowEnd ? `第 ${ref.rowStart} 行` : `第 ${ref.rowStart}-${ref.rowEnd} 行`;
  return `${ref.tableName} ${span}（源 ${ref.sourceId}）`;
}

// ── C2 归类看板：按 category 分组（保持首现顺序，便于看板稳定渲染）──
export function groupClassificationsByCategory<T extends { category: string }>(items: T[]): Array<{ category: string; items: T[] }> {
  const order: string[] = [];
  const map = new Map<string, T[]>();
  for (const it of items) {
    if (!map.has(it.category)) { map.set(it.category, []); order.push(it.category); }
    map.get(it.category)!.push(it);
  }
  return order.map((category) => ({ category, items: map.get(category)! }));
}

// ── E3 批注按页分组（页码升序；同页保持返回序）──
export function groupAnnotationsByPage<T extends { pageNumber: number }>(items: T[]): Array<{ page: number; items: T[] }> {
  const pages = [...new Set(items.map((a) => a.pageNumber))].sort((a, b) => a - b);
  return pages.map((page) => ({ page, items: items.filter((a) => a.pageNumber === page) }));
}

// ── D2/G6 校验可读差异（逐行展示；空问题=通过行 + 回跳统计行）──
export interface EdiscVerifyResult {
  ok: boolean;
  checked: number;
  problems: Array<{ ref: string; issue: string }>;
  backjumpChecked: number;
  backjumpMismatched: number;
  candidates: number;
}
export function summarizeVerify(v: EdiscVerifyResult): string[] {
  const lines: string[] = [];
  if (v.ok) {
    lines.push(`校验通过：${v.candidates} 个清单项、${v.checked} 处锚一一对应，未发现缺漏。`);
  } else {
    lines.push(`校验未通过：共 ${v.problems.length} 处问题，须回归类/清单修正后重新校验。`);
    for (const p of v.problems) lines.push(`· ${p.ref}：${p.issue}`);
  }
  lines.push(`回跳核验：${v.backjumpMismatched}/${v.backjumpChecked} 处引用与原文不一致。`);
  return lines;
}

// ── F10 律师闸：报告导出前，全部存疑/不足标注须律师逐项过目（无豁免通道）──
export function canExportReviewReport(input: { flagCount: number; lawyerConfirmed: boolean }): { ok: boolean; reason: string } {
  if (input.flagCount > 0 && !input.lawyerConfirmed) {
    return { ok: false, reason: `存在 ${input.flagCount} 条审查标注，须经执业律师逐项过目并勾选确认后，方可作为行动依据导出。` };
  }
  return { ok: true, reason: "" };
}

// ═══ 对拍收尾面（施工波三轮 20261031；值域镜像桥闭集，文案自写）═══

// ── F1 待证事实：四类排除纪律（随登记面提示）──
export const EDISC_FACT_EXCLUSIONS = [
  "各方均无争议的事实",
  "已由生效裁判文书确认的事实",
  "纯法律适用问题",
  "公知事实",
] as const;

// ── F2 形式六要素（顺序=登记表单列序；缺项提示先补齐再实质审查）──
export const EDISC_FORMAL_ELEMENTS = ["名称", "形成时间", "出具方", "原件或复印件", "证明目的", "对应待证事实"] as const;
export type EdiscFormalElement = (typeof EDISC_FORMAL_ELEMENTS)[number];
export function missingFormalElements(elements: Partial<Record<EdiscFormalElement, string>> = {}): EdiscFormalElement[] {
  return EDISC_FORMAL_ELEMENTS.filter((k) => !String(elements?.[k] ?? "").trim());
}

// ── F4 三性表单（属性三件+结论闭集；结论色标=绿/琥珀/红可辨）──
export const EDISC_TRIPLE_ATTRIBUTES = ["真实性", "合法性", "关联性"] as const;
export const EDISC_ATTR_CONCLUSIONS = ["符合", "存疑", "不符合"] as const;
export type EdiscAttrConclusion = (typeof EDISC_ATTR_CONCLUSIONS)[number];
export const EDISC_ATTR_BADGE: Record<EdiscAttrConclusion, { label: string; cls: string }> = {
  符合: { label: "符合", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  存疑: { label: "存疑", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  不符合: { label: "不符合", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
};

// ── F6 四类缺口（类目闭集；行格式与报告第五节同形）──
export const EDISC_GAP_KINDS = ["完全缺口", "证明力不足", "证据链断裂", "形式瑕疵"] as const;
export type EdiscGapKind = (typeof EDISC_GAP_KINDS)[number];
export interface EdiscGapEntry {
  kind: EdiscGapKind; factText: string; suggestion: string;
  sourceChannel: string; difficulty: string; deadlineNote: string;
}
export function formatGapEntry(g: EdiscGapEntry): string {
  const seg = [
    `对应待证事实：${g.factText || "（未指定）"}`,
    `建议补充：${g.suggestion}`,
    `取得渠道：${g.sourceChannel || "待定"}`,
    `收集难度：${g.difficulty || "未评估"}`,
  ];
  if (g.deadlineNote) seg.push(`期限警示：${g.deadlineNote}`);
  return `【${g.kind}】${seg.join("｜")}`;
}

// ── G5 长任务状态徽章（四态色标：运行琥珀/暂停灰/完成绿/取消红灰）──
export type EdiscTaskStatus = "running" | "paused" | "done" | "canceled";
export const EDISC_TASK_STATUS_BADGE: Record<EdiscTaskStatus, { label: string; cls: string }> = {
  running: { label: "运行中", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  paused: { label: "已暂停（断点保留）", cls: "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300" },
  done: { label: "已完成", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  canceled: { label: "已取消", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
};
/** 任务进度行（检查点/成功/失败/待处理可读计数）。 */
export function summarizeTaskProgress(s: {
  status: EdiscTaskStatus; total: number; done: number; failed: number; pending: number; checkpoint: number;
}): string {
  return `检查点 ${s.checkpoint}/${s.total}｜成功 ${s.done}｜失败 ${s.failed}｜待处理 ${s.pending}`;
}
