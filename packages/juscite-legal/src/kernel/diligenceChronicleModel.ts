// 【功能 #32 整理与尽调】历史沿革核查内核（RE-32 §2 行为 13-16 / §5 边界）。
// 行为 13＝材料汇集：用户提交+项目内检索双通道（我方不做外部数据代采——§5：外部源接入待自家
// LCCC/legal-cn-cases 路线就绪；对拍 12 按此口径判非严格等量）；
// 行为 14＝按时间轴生成历史沿革章节正文（日期确定性解析；解析不了=待核，不猜）；
// 行为 15＝同步输出风险评估与待核查事项清单（规则面：缺件/日期未解析/沿革断层）；
// 行为 16＝一键导出 Word 的装配稿（markdown；docx 装配在桥侧复用 draft_docx 零依赖装配器）。
// 纯函数、零 IO；文案自写。

import type { TextBlock } from "./diligenceLedgerModel.js";

export const CHRONICLE_KINDS = ["工商登记档案", "验资报告", "股权转让协议", "公司章程", "董监高任免文件", "其他"] as const;
export type ChronicleKind = (typeof CHRONICLE_KINDS)[number];

export function isChronicleKind(k: string): k is ChronicleKind {
  return (CHRONICLE_KINDS as readonly string[]).includes(k);
}

// 各类材料的项目内检索关键词（自定；确定性子串匹配）
export const KIND_KEYWORDS: Record<ChronicleKind, string[]> = {
  工商登记档案: ["工商", "登记", "营业执照", "年报", "变更"],
  验资报告: ["验资"],
  股权转让协议: ["股权转让", "股转"],
  公司章程: ["章程"],
  董监高任免文件: ["任免", "聘任", "解聘", "选举", "董事", "监事"],
  其他: [],
};

export interface ChronicleDoc {
  docId: string;
  docTitle: string;
  kind: ChronicleKind | "未定类";
  channel: "user" | "search";
  blocks: TextBlock[];
}

export interface ChronicleEvent {
  dateIso: string | null; // 解析不出真实日期= null（待核，不猜）
  dateRaw: string;
  text: string;
  docId: string;
  docTitle: string;
  page: number | null;
  seq: number;
}

export interface RiskNote {
  level: "risk" | "todo";
  title: string;
  detail: string;
}

// ── 行为 13 通道二：项目内检索（对已登记材料的块文本按类目关键词扫描）──
export function searchInProject(
  docs: Array<{ docId: string; docTitle: string; blocks: TextBlock[] }>,
  kinds: ChronicleKind[],
): Array<{ docId: string; docTitle: string; kind: ChronicleKind; hitKeywords: string[] }> {
  const out: Array<{ docId: string; docTitle: string; kind: ChronicleKind; hitKeywords: string[] }> = [];
  for (const d of docs) {
    const hay = `${d.docTitle}\n${d.blocks.map((b) => b.text ?? "").join("\n")}`;
    for (const kind of kinds) {
      const hits = KIND_KEYWORDS[kind].filter((k) => hay.includes(k));
      if (hits.length > 0 && !out.some((o) => o.docId === d.docId && o.kind === kind)) {
        out.push({ docId: d.docId, docTitle: d.docTitle, kind, hitKeywords: hits.slice(0, 4) });
      }
    }
  }
  return out;
}

// ── 日期确定性解析（三种写法；解析失败=待核 null）──
const DATE_PATTERNS: Array<{ re: RegExp; build: (m: RegExpMatchArray) => string | null }> = [
  { re: /(\d{4})年(\d{1,2})月(\d{1,2})日/u, build: (m) => isoOf(+m[1]!, +m[2]!, +m[3]!) },
  { re: /(\d{4})-(\d{1,2})-(\d{1,2})/u, build: (m) => isoOf(+m[1]!, +m[2]!, +m[3]!) },
  { re: /(\d{4})\.(\d{1,2})\.(\d{1,2})/u, build: (m) => isoOf(+m[1]!, +m[2]!, +m[3]!) },
];

function isoOf(y: number, mo: number, d: number): string | null {
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || y < 1900 || y > 2199) return null;
  const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (d > days[mo - 1]!) return null;
  return `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

export function parseDateAt(text: string): { dateIso: string | null; dateRaw: string } | null {
  for (const p of DATE_PATTERNS) {
    const m = String(text ?? "").match(p.re);
    if (m) return { dateIso: p.build(m), dateRaw: m[0] };
  }
  return null;
}

// ── 行为 14 前置：从汇集材料提取时间轴事件（每块取首个日期；无日期块不入轴）──
export function extractTimelineEvents(docs: ChronicleDoc[]): { events: ChronicleEvent[]; undated: number } {
  const events: ChronicleEvent[] = [];
  let undated = 0;
  for (const d of docs) {
    for (const b of d.blocks) {
      const lines = String(b.text ?? "").split(/\r?\n/);
      for (const line of lines) {
        const s = line.trim();
        if (!s) continue;
        const hit = parseDateAt(s);
        if (!hit) { undated += 1; continue; }
        events.push({
          dateIso: hit.dateIso, dateRaw: hit.dateRaw,
          text: s.slice(0, 160), docId: d.docId, docTitle: d.docTitle, page: b.page, seq: b.seq,
        });
      }
    }
  }
  events.sort((a, b) => {
    if (a.dateIso && b.dateIso) return a.dateIso < b.dateIso ? -1 : a.dateIso > b.dateIso ? 1 : 0;
    if (a.dateIso) return -1;
    if (b.dateIso) return 1;
    return 0;
  });
  return { events, undated };
}

// ── 行为 14：历史沿革章节正文（按年分组时间轴；叙事模板自写）──
export function buildChronicleChapter(caseTitle: string, docs: ChronicleDoc[], events: ChronicleEvent[], undated: number): string {
  const lines: string[] = ["# 历史沿革核查报告（草稿）", "", `项目：${caseTitle}`, ""];
  const byYear = new Map<string, ChronicleEvent[]>();
  for (const e of events) {
    const y = e.dateIso ? e.dateIso.slice(0, 4) : "待核";
    const list = byYear.get(y) ?? [];
    list.push(e);
    byYear.set(y, list);
  }
  const years = [...byYear.keys()].sort();
  if (years.length === 0) {
    lines.push("汇集材料中未解析出可定位日期的事件，沿革时间轴暂空——请先补材料或人工提供关键日期。");
  }
  lines.push("## 一、沿革时间轴");
  for (const y of years) {
    lines.push("", `### ${y} 年`);
    for (const e of byYear.get(y)!) {
      const anchor = `〔${e.docTitle}${e.page !== null ? ` 第${e.page}页` : ` 块${e.seq}`}〕`;
      lines.push(`- ${e.dateIso ?? `（日期待核：${e.dateRaw}）`}　${e.text} ${anchor}`);
    }
  }
  const kindCount = new Map<string, number>();
  for (const d of docs) kindCount.set(d.kind, (kindCount.get(d.kind) ?? 0) + 1);
  lines.push("", "## 二、汇集材料清单", "");
  for (const d of docs) {
    const via = d.channel === "user" ? "用户提交" : "项目内检索";
    lines.push(`- 〔${d.kind}〕${d.docTitle}（${via}）`);
  }
  if (undated > 0) lines.push("", `另有 ${undated} 行含材料文本未解析出日期，未纳入时间轴（见待核查清单）。`);
  lines.push("");
  return lines.join("\n");
}

// ── 行为 15：风险评估+待核查事项清单（规则面，全自写）──
export function buildRiskAndTodo(docs: ChronicleDoc[], events: ChronicleEvent[], undated: number): { risks: RiskNote[]; todoMd: string } {
  const risks: RiskNote[] = [];
  const kindsPresent = new Set(docs.map((d) => d.kind));
  for (const kind of ["工商登记档案", "验资报告", "股权转让协议", "公司章程", "董监高任免文件"] as const) {
    if (!kindsPresent.has(kind)) {
      risks.push({ level: "risk", title: `缺「${kind}」类材料`, detail: "历史沿革核查的关键类材料尚未汇集，请先按清单索取。" });
    }
  }
  const undatedEvents = events.filter((e) => e.dateIso === null);
  if (undatedEvents.length > 0) {
    risks.push({ level: "todo", title: `${undatedEvents.length} 条事件日期未能解析`, detail: "原文日期写法非标准三式（YYYY年M月D日／YYYY-M-D／YYYY.M.D）或非真实日期，需人工定档。" });
  }
  if (undated > 0) {
    risks.push({ level: "todo", title: `${undated} 行材料文本无日期`, detail: "未纳入时间轴，如涉关键节点请人工补录日期。" });
  }
  const dated = events.filter((e) => e.dateIso !== null);
  for (let i = 1; i < dated.length; i++) {
    const gap = (Date.parse(dated[i]!.dateIso!) - Date.parse(dated[i - 1]!.dateIso!)) / 86400000;
    if (gap > 365 * 3) {
      risks.push({ level: "todo", title: `沿革疑似断层：${dated[i - 1]!.dateIso} 至 ${dated[i]!.dateIso} 间隔约 ${Math.round(gap / 365)} 年`, detail: "间隔超过三年，请确认期间是否确无沿革事件或材料缺漏。" });
      break; // 只报最长一处，避免刷屏（全量清点留给人工）
    }
  }
  if (events.length === 0) {
    risks.push({ level: "risk", title: "时间轴为空", detail: "无任何可定位日期的事件，沿革正文无法成稿。" });
  }
  const lines = [
    "# 风险评估与待核查事项清单",
    "",
    `- 风险提示 ${risks.filter((r) => r.level === "risk").length} 项；待核查 ${risks.filter((r) => r.level === "todo").length} 项。`,
    "",
  ];
  risks.forEach((r, i) => {
    lines.push(`${i + 1}. 〔${r.level === "risk" ? "风险" : "待核"}〕${r.title}——${r.detail}`);
  });
  if (risks.length === 0) lines.push("本轮汇集材料未见规则面风险项；规则面之外的专业判断仍归律师复核。");
  return { risks, todoMd: lines.join("\n") + "\n" };
}

// ── 行为 16：Word 装配稿（章节正文+风险清单+材料清单合一；docx 化在桥侧）──
export function chronicleWordMarkdown(chapterMd: string, riskTodoMd: string): string {
  return [chapterMd.trimEnd(), "", "---", "", riskTodoMd.trimEnd(), ""].join("\n");
}
