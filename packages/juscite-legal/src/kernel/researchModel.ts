// 【步骤4·#16 调研报告】调研纯模型（RE-16-调研报告.md 实现规格 §3）。
// 桥/UI/合成自测单一来源（沿 caseGraphModel/caseTimelineModel 先例）：即时规划/规划提取评分器/
// 三桶切分/阶段号提取/报告完整性/证据门/工具剔除/配额错误识别/裸话题防误触发/导出预处理/
// 编辑落账/导出命名/提示词装配，全部正则+状态机零模型（工作区铁律）。
// 文案全部自写（表达隔离）；阈值为规格钉死口径：报告完整性 trim≥300 字符+5 组节名命中≥4、
// 证据门去空白≥160、续跑上限 5、评分器权重 +20/+4/+2/-5/-12、编号分隔两判定器字符集分立
// （UI 提取器含冒号不含全角点，工作流发布判定含全角点不含冒号，B12）。

// ── 数据模型（§3 数据模型，字段与竞品同构；持久化介质=桥内轻量表，字段同构）──
export type ResearchStatus = "running" | "done" | "error";
export type StepIconKind = "search" | "case" | "doc" | "statute" | "summary" | "web" | "general" | "error";

export interface ResearchStep {
  id: string;
  tool: string;
  icon: StepIconKind;
  status: "pending" | "running" | "done" | "error";
  input: string;
  output?: string;
  detail?: string;
  meta?: Record<string, unknown>;
}

export interface ResearchUpdate {
  id: string;
  text: string;
  createdAt: number;
  completed?: boolean;
}

export interface ResearchRecord {
  id: string;                              // `research-<Date.now()>`
  query: string;                           // 课题原文（trim 后）
  timestamp: string;                       // zh-CN 本地时间串（展示用）
  updatedAt: number;                       // 计时基准
  status: ResearchStatus;
  planning?: string;                       // 规划文本（初始=即时规划，后被模型规划替换）
  reasoning: string;                       // 规划期 reasoning 原文
  steps: ResearchStep[];
  updates: ResearchUpdate[];               // 阶段播报（已剥掉规划与报告）
  summary: string;                         // 最终报告 markdown（可被编辑覆盖）
  editedSummary?: string;
  reportRevision?: number;                 // 编辑时间戳，驱动重渲染
  blocks: unknown[];                       // 原始块快照（对账用）
  threadId?: string;
  turnId?: string;
  error?: string;
}

// ── 常量单源（规格实测钉死阈值）──
export const REPORT_MIN_CHARS = 300;      // 报告完整性：trim 后 ≥300 字符（B24）
export const REPORT_SECTION_TOTAL = 5;    // 五节结构
export const REPORT_MIN_SECTIONS = 4;     // 命中 ≥4/5 节名才算完整（B24）
export const EVIDENCE_MIN_CHARS = 160;    // 证据门：载荷去空白 ≥160（B22）
export const MAX_REPORT_CONTINUATIONS = 5; // 有界续跑上限（B24）
export const INSTANT_PLAN_ITEMS = 5;      // 即时规划 5 条（B08）
export const TITLE_MAX_CHARS = 60;        // 内部会话标题取课题前 60 字（B09）
export const EXPORT_NAME_QUERY_CHARS = 30; // 导出默认名取课题前 30 字（B39）
export const RESEARCH_NAME_PREFIX = "调研报告"; // 导出默认名前缀（文案自写，B39 等量规则）

// 报告五节结构（自家报告骨架；完整性节名族按此定制，对拍 25）
export const REPORT_SECTIONS = ["结论与建议", "法律依据与效力", "相关案例", "分析与风险", "来源与核验"] as const;

// 五组节名正则族（判定器锚点；自家节名的同义词族，阈值同构）
export const REPORT_SECTION_RES: ReadonlyArray<RegExp> = [
  /结论|建议|综述意见/u,
  /法律依据|法条|法规|条文|依据/u,
  /相关案例|案例|判例|裁判/u,
  /分析|风险|评析/u,
  /来源|参考|引用|核验/u,
];

// 首选源枚举（B50/对拍 52：三选一，枚举值等量；真实库对接随数据工程解挂，§5 边界 1）
export const PRIMARY_LEGAL_SOURCES = [
  { id: "pkulaw", label: "北大法宝" },
  { id: "yuandian", label: "元典" },
  { id: "wk", label: "威科先行" },
] as const;

// ── 中文数字（阶段号提取 B14：中文数字表一~二十、数字 1-99）──
const CN_DIGIT: Readonly<Record<string, number>> = {
  零: 0, 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9,
};
export function cnNumberToArabic(s: string): number | null {
  const t = String(s ?? "").trim();
  if (!t) return null;
  if (/^\d{1,3}$/.test(t)) return Number(t);
  // 纯中文数字（一~九十九）
  if (![...t].every((c) => c in CN_DIGIT || c === "十")) return null;
  if (t === "十") return 10;
  const shiIdx = t.indexOf("十");
  if (shiIdx < 0) {
    // 一~九
    return t.length === 1 ? (CN_DIGIT[t] ?? null) : null;
  }
  const tens = shiIdx === 0 ? 1 : (shiIdx > 0 ? CN_DIGIT[t[shiIdx - 1] ?? ""] : undefined);
  const onesPart = t.slice(shiIdx + 1);
  const ones = onesPart ? (CN_DIGIT[onesPart] ?? 0) : 0;
  if (tens === undefined || ones === undefined) return null;
  return tens * 10 + (ones ?? 0);
}

// ── 阶段号提取（B14：模型自写阶段号优先于顺序号）──
// 形态：「阶段四」「第5阶段」「第 12 阶段」「步骤三」
export function extractStageNo(text: string): number | null {
  const t = String(text ?? "").slice(0, 200);
  const m = t.match(/(?:第\s*([一二两三四五六七八九十百零\d]{1,4})\s*个?\s*阶段)|(?:阶段\s*([一二两三四五六七八九十百零\d]{1,4}))|(?:第\s*([一二两三四五六七八九十百零\d]{1,4})\s*个?\s*步骤)|(?:步骤\s*([一二两三四五六七八九十百零\d]{1,4}))/u);
  const raw = m?.[1] ?? m?.[2] ?? m?.[3] ?? m?.[4];
  if (!raw) return null;
  const n = cnNumberToArabic(raw);
  if (n === null || n < 1 || n > 99) return null; // 规格口径：数字 1-99
  return n;
}

// ── 即时规划（B08：启动当下就渲染"调研规划"卡，5 条编号计划、主题词内插；条目文案自写）──
export function instantPlan(query: string): string {
  const q = String(query ?? "").trim() || "该课题";
  const items = [
    `界定「${q}」的核心法律问题与争议焦点，明确调研范围`,
    `检索与「${q}」相关的现行法律法规、司法解释及条文效力`,
    `收集「${q}」领域的典型案例，提炼裁判要旨`,
    `梳理实务处理口径与主要风险点，搭建分析框架`,
    `综合以上材料，按五节结构完成调研报告并核对来源`,
  ];
  return `调研规划：\n${items.map((s, i) => `${i + 1}. ${s}`).join("\n")}`;
}

// ── 编号分隔两判定器（B12：字符集分立，两口径各自对拍）──
// UI 提取器口径：含冒号（半/全角）、不含全角点．
const UI_PLAN_SEP = "[.)、：:]";
// 工作流发布判定口径：含全角点．、不含冒号
const LOOP_PLAN_SEP = "[.)、．]";
const NUM_HEAD = String.raw`(?:\d{1,3}|[一二两三四五六七八九十]{1,3})`;

function makeNumberedRe(sep: string): RegExp {
  return new RegExp(String.raw`^\s*(?:#{1,6}\s*|[-*]\s+)?(?:\*\*)?(` + NUM_HEAD + String.raw`)\s*` + sep + "\s*", "u");
}
// 行首编号剥除（两口径各自实例）
const UI_NUMBERED_RE = makeNumberedRe(UI_PLAN_SEP);
const LOOP_NUMBERED_RE = makeNumberedRe(LOOP_PLAN_SEP);

export function stripUiNumberPrefix(line: string): string {
  return line.replace(UI_NUMBERED_RE, "");
}
export function isUiNumberedItem(line: string): boolean {
  return UI_NUMBERED_RE.test(line);
}
// 工作流发布判定（B22 前置）：按 loop 口径，标题+编号项≥3 即"规划已发布"
export function isPlanPublished(text: string): boolean {
  const lines = String(text ?? "").split("\n");
  let items = 0;
  let hasTitle = false;
  for (const line of lines) {
    if (/(调研规划|研究规划|检索规划|调研计划|工作规划)/u.test(line)) hasTitle = true;
    if (LOOP_NUMBERED_RE.test(line)) items++;
  }
  return hasTitle && items >= 3;
}

// ── 规划提取评分器（B12：显式标题+20、每项+4、动作词每项+2、剔除项每项-5、元语境-12）──
const PLAN_ACTION_RE = /(检索|查找|搜集|收集|梳理|分析|比较|比对|核查|核验|总结|归纳|整理|输出|撰写|调研|研究|评估|查阅|定位|提炼)/u;
// 剔除项：复述系统要求/执行日志前缀（让我/接下来/先检查…）；探针实证：裸执行日志行
// （非编号行）终结当前编号候选组（切分语义，非组内剔除）；编号条目自身带执行日志前缀才被剔除。
const PLAN_DROP_PREFIX_RE = /^(让我|让我来|接下来|先检查|先看|先来|我需要|我将|我要|我先|现在开始|开始执行|正在执行|执行：|好，|好的，)/u;
const PLAN_SYSTEM_ECHO_RE = /(系统提示|系统要求|作为.*(助手|模型)|你的任务|你需要|必须遵守)/u;
// 元语境（自我说明/客套话）
const PLAN_META_RE = /^(好的|明白|收到|当然|没问题|以下是|这是|关于|根据您|根据你|我理解)/u;
const PLAN_TITLE_RE = /(调研规划|研究规划|检索规划|调研计划|工作规划|研究思路|调研思路)/u;

export interface PlanCandidate {
  score: number;
  title: string | null;
  items: string[];
  removed: number;
}
export interface PlanExtraction {
  plan: string | null;
  candidates: PlanCandidate[];
}

// 提取一段文本中的编号规划（UI 口径）。候选组按"裸执行日志行终结"切分：
// 顺序扫描，非编号行若命中执行日志/元语境前缀→终结当前候选组（组内已收项保留）；
// 无编号列表时三级降级：编号→要点列表（- * 开头）→按句切分（。！？边界，≥3 句才成）。
export function extractPlan(text: string): PlanExtraction {
  const src = String(text ?? "");
  const lines = src.split("\n");
  const candidates: PlanCandidate[] = [];
  let cur: { items: string[]; removed: number; title: string | null } | null = null;
  const flush = () => {
    if (!cur) return;
    if (cur.items.length) {
      let score = 0;
      if (cur.title) score += 20;
      score += cur.items.length * 4;
      score -= cur.removed * 5;
      candidates.push({ score, title: cur.title, items: [...cur.items], removed: cur.removed });
    }
    cur = null;
  };
  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line.trim()) continue;
    if (UI_NUMBERED_RE.test(line)) {
      const body = stripUiNumberPrefix(line).trim();
      if (!body) continue;
      if (!cur) cur = { items: [], removed: 0, title: null };
      // 编号条目自身带执行日志前缀/复述系统要求→剔除并计 -5
      if (PLAN_DROP_PREFIX_RE.test(body) || PLAN_SYSTEM_ECHO_RE.test(body)) { cur.removed++; continue; }
      cur.items.push(body);
      continue;
    }
    // 非编号行：标题行挂到当前候选组；裸执行日志行/元语境行终结当前组
    if (PLAN_TITLE_RE.test(line) && line.trim().length <= 30) {
      flush();
      cur = { items: [], removed: 0, title: line.trim() };
      continue;
    }
    if (PLAN_DROP_PREFIX_RE.test(line.trim()) || PLAN_META_RE.test(line.trim())) flush();
  }
  flush();
  // 动作词每项 +2（计分口径；资格判定=显式标题+编号项≥3）
  for (const c of candidates) {
    const actionItems = c.items.filter((s) => PLAN_ACTION_RE.test(s)).length;
    c.score += actionItems * 2;
  }
  // 元语境惩罚：候选组上下文里有元语境行 → -12（记在组上）
  if (PLAN_META_RE.test(src.slice(0, 400))) {
    for (const c of candidates) c.score -= 12;
  }
  // 资格：显式标题 + 编号项 ≥3（规格实测钉死口径）；取分最高组
  const qualified = candidates.filter((c) => c.title && c.items.length >= 3);
  qualified.sort((a, b) => b.score - a.score);
  const best = qualified[0];
  if (best) {
    return { plan: `${best.title}\n${best.items.map((s, i) => `${i + 1}. ${s}`).join("\n")}`, candidates };
  }
  // 降级②：要点列表（无编号列表时的要点行）
  const bullets = lines.map((l) => l.trim()).filter((l) => /^[-*]\s+\S/u.test(l)).map((l) => l.replace(/^[-*]\s+/u, ""));
  if (bullets.length >= 3) {
    return { plan: bullets.slice(0, 8).map((s, i) => `${i + 1}. ${s}`).join("\n"), candidates };
  }
  // 降级③：按句切分（≥3 句且总长有限才成，防把报告误当规划）
  const sentences = src.split(/(?<=[。！？])/u).map((s) => s.trim()).filter((s) => s.length >= 8 && s.length <= 80);
  if (sentences.length >= 3 && sentences.length <= 8 && !isReportShaped(src)) {
    return { plan: sentences.slice(0, 6).map((s, i) => `${i + 1}. ${s}`).join("\n"), candidates };
  }
  return { plan: null, candidates };
}
function isReportShaped(text: string): boolean {
  return reportSectionHits(text) >= 4;
}

// ── 报告完整性（B24：trim 后 ≥300 字符 且 5 组节名命中 ≥4；trim 口径仅去 \r 与首尾空白）──
export function trimLoose(text: string): string {
  return String(text ?? "").replace(/\r/g, "").trim();
}
export function reportSectionHits(text: string): number {
  const t = trimLoose(text).slice(0, 6000);
  if (!t) return 0;
  return REPORT_SECTION_RES.filter((re) => re.test(t)).length;
}
export function isReportComplete(text: string): boolean {
  return trimLoose(text).length >= REPORT_MIN_CHARS && reportSectionHits(text) >= REPORT_MIN_SECTIONS;
}

// ── 三桶切分（B17：从混合流里按标题剥离规划/阶段播报/报告；跳过规划/阶段标题，从报告标题起）──
const PLAN_HEADING_RE = /^\s*#{0,6}\s*(?:\*\*)?\s*(?:\d{0,3}[.、．:：]?\s*)(调研规划|研究规划|检索规划|调研计划|工作规划)(?:[:：]|\s|$).*$/u;
const STAGE_HEADING_RE = /^\s*#{0,6}\s*(?:\*\*)?\s*(?:阶段|第\s*[一二两三四五六七八九十百零\d]{1,4}\s*个?\s*阶段|步骤|第\s*[一二两三四五六七八九十百零\d]{1,4}\s*个?\s*步骤).{0,60}$/u;
// 报告起点标题族：非规划/阶段的语义标题里，命中报告节名族即视为报告开始
const REPORT_START_RE = /^\s*#{1,6}\s*(?:\*\*)?\s*(.{0,40})$/u;

export interface StreamSplit {
  planning: string | null;   // 规划桶（模型规划；null=未提取到）
  updates: ResearchUpdate[]; // 阶段播报桶（每条带模型阶段号优先的序号）
  summary: string;           // 报告桶（""=未出现）
  now: number;
}

export function splitResearchStream(full: string, now = Date.now()): StreamSplit {
  const lines = String(full ?? "").replace(/\r/g, "").split("\n");
  const planningLines: string[] = [];
  const stageBlocks: Array<{ heading: string; body: string[] }> = [];
  let reportLines: string[] | null = null;
  let curStage: { heading: string; body: string[] } | null = null;
  for (const line of lines) {
    if (reportLines) { reportLines.push(line); continue; }
    if (PLAN_HEADING_RE.test(line)) {
      curStage = null;
      planningLines.push(line);
      continue;
    }
    if (STAGE_HEADING_RE.test(line)) {
      curStage = { heading: line.trim(), body: [] };
      stageBlocks.push(curStage);
      continue;
    }
    const h = line.match(REPORT_START_RE);
    if (h && reportSectionHits(line) >= 1 && /报告|结论|综述|摘要|依据|案例|分析|风险|来源/u.test(line)) {
      // 报告起点：从此行起全部归报告桶
      reportLines = [line];
      curStage = null;
      continue;
    }
    if (curStage) curStage.body.push(line);
    else planningLines.push(line);
  }
  const updates: ResearchUpdate[] = stageBlocks.map((b, i) => {
    const text = [b.heading, ...b.body].join("\n").trim();
    return { id: `upd-${now}-${i}`, text, createdAt: now + i, completed: true };
  });
  return {
    planning: planningLines.join("\n").trim() || null,
    updates,
    summary: reportLines ? reportLines.join("\n").trim() : "",
    now,
  };
}

// ── 证据门（B22/B51；主库特征按自家轻量期来源定制：本地法规库/案例库，对拍 22/31）──
// 规则：mcp_search 类"发现"不计证据；链接装饰类（link_enhance/引证核验等）不计；
// 法规证据=工具名或载荷命中主源特征 且 载荷去空白≥160 且 非错误；
// 案例证据另需案例工具名或案号特征（\d{4}…第N号）；两者齐=synthesisReady。
const EVIDENCE_DISCOVERY_TOOL_RE = /mcp_search|工具发现|检索发现/u;
const LINK_DECOR_TOOL_RE = /link[_-]?enhance|引证核验|链接装饰|citation[_-]?verify/u;
const REGULATION_SOURCE_RE = /(法规|法条|法規|法典|条文|statute|law|法规库|lccc)/iu; // law 词干=自家 laws_search 工具命名约定
const CASE_TOOL_RE = /(案例|判例|case|裁判)/iu; // case 词干=自家 case_search 工具命名约定
const CASE_NO_RE = /\d{2,4}[^0-9，。;；\n\r]{0,12}\d{1,6}\s*号/u; // 案号特征（如 （2023）合01民终1234号）
export interface EvidenceToolInput {
  name: string;
  payloadText: string;
  isError?: boolean;
}
export interface EvidenceGateResult {
  regulationReady: boolean;
  caseReady: boolean;
  synthesisReady: boolean;
}
export function evidenceGate(tools: ReadonlyArray<EvidenceToolInput>): EvidenceGateResult {
  let regulationReady = false;
  let caseReady = false;
  for (const t of tools) {
    if (!t || t.isError) continue;
    if (EVIDENCE_DISCOVERY_TOOL_RE.test(t.name)) continue;   // 发现不计证据
    if (LINK_DECOR_TOOL_RE.test(t.name)) continue;           // 装饰类不计
    const compact = String(t.payloadText ?? "").replace(/\s/g, "");
    const nameHit = REGULATION_SOURCE_RE.test(t.name);
    const payloadHit = REGULATION_SOURCE_RE.test(String(t.payloadText ?? "").slice(0, 400));
    if ((nameHit || payloadHit) && compact.length >= EVIDENCE_MIN_CHARS) regulationReady = true;
    const caseHit = CASE_TOOL_RE.test(t.name) || CASE_NO_RE.test(String(t.payloadText ?? "").slice(0, 2000));
    if (caseHit && compact.length >= EVIDENCE_MIN_CHARS) caseReady = true;
  }
  return { regulationReady, caseReady, synthesisReady: regulationReady && caseReady };
}

// ── 工具目录剔除（B23：任一主库可用法规证据就绪后，装饰性扩张工具从目录剔除）──
const CULL_TOOL_RE = /web[_-]?search|web[_-]?fetch|外部法规|法规直检|link[_-]?enhance|引证核验|链接装饰|citation[_-]?verify|网页检索|网页抓取/iu;
export function cullToolCatalog(names: ReadonlyArray<string>, regulationReady: boolean): string[] {
  if (!regulationReady) return [...names];
  return names.filter((n) => !CULL_TOOL_RE.test(n));
}

// ── 冗余检索判定（workflow 侧 :129-138 等量：同参数重复检索不再放行）──
export function isRedundantSearch(history: ReadonlyArray<string>, tool: string, input: string): boolean {
  const key = `${tool}::${String(input ?? "").trim()}`;
  return history.some((h) => h === key);
}

// ── 配额/鉴权确定性错误识别（B26：命中即切 web 兜底不再重试该库；403/forbidden 明确不判）──
export function isQuotaAuthError(message: string): boolean {
  const m = String(message ?? "");
  if (!m) return false;
  if (/403|forbidden/i.test(m)) return false; // 明确不判（规格口径）
  if (/90001/.test(m)) return true;
  if (/remaining points/i.test(m)) return true;
  if (/(?:^|[^0-9])401(?:[^0-9]|$)/.test(m)) return true;
  if (/invalid\s+(api\s+)?key/i.test(m)) return true;
  if (/(额度|余额|积分)(不足|已用尽|耗尽|已耗尽)/u.test(m)) return true;
  if (/(quota|balance|credit)[\w\s]{0,24}(exhausted|insufficient|depleted)/i.test(m)) return true;
  if (/insufficient\s+(quota|balance|credit|funds)/i.test(m)) return true;
  if (/depleted/i.test(m)) return true;
  return false;
}

// ── 裸话题防误触发（B29：4-48 字+≥1 汉字+无豁免标点与换行+不命中指令动词词表+不命中三排除链；
//     中文逗号不在豁免集——"婚姻家庭，财产分割"仍判裸话题）──
const BARE_EXEMPT_RE = /[?？!！。；;：:]|\n/u;
const BARE_VERB_RE = /(请|帮我|帮忙|麻烦|劳驾|检索|搜索|查询|查找|查一下|查查|搜一搜|分析|研究|调研|起草|撰写|写一?份|写个|生成|总结|翻译|审查|审核|对比|比对|核查|核验|列出|罗列|梳理|给出|提供|输出|看看|看下|了解|说明|解释|介绍|评估|整理)/u;
const BARE_FILE_RE = /(word|docx|pdf|excel|ppt|表格|文档|文件|报告|合同|起诉状|答辩状)/iu;
// 三排除链：续聊/低信号抱怨/上下文指代
const BARE_CONTINUE_RE = /^(继续|接着|然后|还有|另外|补充一下?|再|那)/u;
const BARE_COMPLAIN_RE = /(不对|错了|不对劲|重新|重来|不行|不好|没用|听不懂|答非所问|太差|胡说|again|wrong|bad)/iu;
const BARE_CONTEXT_REF_RE = /(它|他|她|这个|那个|上面|刚才|之前|以上|此处|这篇|那段|上面说的|刚才说)/u;
export function isBareResearchTopic(text: string): boolean {
  const t = String(text ?? "").trim();
  if (!t) return false;
  const n = [...t].length;
  if (n < 4 || n > 48) return false;
  if (!/[\u4e00-\u9fff]/u.test(t)) return false;
  if (BARE_EXEMPT_RE.test(t)) return false;
  if (BARE_VERB_RE.test(t)) return false;
  if (BARE_FILE_RE.test(t)) return false;
  if (BARE_CONTINUE_RE.test(t)) return false;
  if (BARE_COMPLAIN_RE.test(t)) return false;
  if (BARE_CONTEXT_REF_RE.test(t)) return false;
  return true;
}

// ── 导出预处理（B42：框图围栏化/`|||` 转列表/从首个非规划阶段 H1 截取/连续空行折叠）──
const BOX_LINE_RE = /^[^a-zA-Z0-9\u4e00-\u9fff]*[┌┐└┘├┤┬┴┼─│═║╔╗╚╝╠╣╦╩╬+|=~\-_][^a-zA-Z0-9\u4e00-\u9fff]*$/u;
function isBoxLine(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  // 制表符 ≥2 即框线行（行内可含字母数字——表格中列有内容）；再兜 ASCII 分隔行
  const boxChars = (t.match(/[┌┐└┘├┤┬┴┼─│═║╔╗╚╝╠╣╦╩╬]/gu) ?? []).length;
  if (boxChars >= 2) return true;
  const hits = (t.match(/[+\-=|]/g) ?? []).length;
  return hits >= 6 && /^[+\-=|\s:]+$/u.test(t);
}
export function preprocessReportMarkdown(text: string): string {
  let src = String(text ?? "").replace(/\r/g, "");
  // ③截取：从首个非规划/阶段 H1 起（其前内容=规划/阶段播报残留，不入导出）
  const lines = src.split("\n");
  let startIdx = 0;
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i] ?? "";
    if (/^#\s+\S/u.test(ln) && !PLAN_HEADING_RE.test(ln) && !STAGE_HEADING_RE.test(ln)) {
      startIdx = i;
      break;
    }
  }
  src = lines.slice(startIdx).join("\n");
  // ①框图围栏化：连续框线行整块包 ```text 围栏
  const out: string[] = [];
  let boxBuf: string[] = [];
  const flushBox = () => {
    if (!boxBuf.length) return;
    if (boxBuf.length >= 2) {
      out.push("```text", ...boxBuf, "```");
    } else {
      if (boxBuf[0] !== undefined) out.push(boxBuf[0]);
    }
    boxBuf = [];
  };
  for (const line of src.split("\n")) {
    if (isBoxLine(line)) boxBuf.push(line);
    else { flushBox(); out.push(line); }
  }
  flushBox();
  src = out.join("\n");
  // ②`|||`/`||` → 换行+两空格缩进列表（原文段内前导空格保留）
  src = src.split("\n").map((line) => {
    if (!/\|\|\|?/u.test(line)) return line;
    const parts = line.split(/\|\|\|?/u).map((p) => p.replace(/\s+$/u, "")).filter((p) => p.trim());
    if (parts.length <= 1) return line;
    return parts.map((p) => `\n  - ${p}`).join("");
  }).join("\n");
  // ④4+ 连续空行折叠为 2 行（折叠超量空行；折叠目标 2 行为自研裁量，规格只钉"4+ 折叠"）
  src = src.replace(/\n{5,}/gu, "\n\n\n");
  return src.trim();
}

// ── 编辑落账（B43：保存后 summary=editedSummary=新文、reportRevision=编辑时间戳）──
export function applyReportEdit<T extends { summary: string; editedSummary?: string; reportRevision?: number; updatedAt: number }>(
  record: T, newText: string, now = Date.now(),
): T {
  const text = String(newText ?? "");
  return { ...record, summary: text, editedSummary: text, reportRevision: now, updatedAt: now };
}

// ── 导出命名（B39/B41：前缀+课题前 30 字；非法文件名字符→_；强制后缀）──
export function exportFileName(query: string, ext: ".docx" | ".md", now?: number): string {
  void now;
  const stem = `${RESEARCH_NAME_PREFIX}_${String(query ?? "").trim().slice(0, EXPORT_NAME_QUERY_CHARS)}`
    .replace(/[\\/:*?"<>|\u0000-\u001f]/gu, "_")
    .replace(/[\s.]+$/gu, "") || RESEARCH_NAME_PREFIX;
  return stem.toLowerCase().endsWith(ext) ? stem : stem + ext;
}

// ── 展示时间戳（B07：本地化字符串）──
export function localizedTimestamp(now = new Date()): string {
  try {
    return now.toLocaleString("zh-CN", { hour12: false });
  } catch {
    return now.toISOString();
  }
}

// ── 记录工厂（B07：id=时间戳串 `research-<Date.now()>`；初始 planning=即时规划 B08）──
export function newResearchRecord(query: string, now = Date.now()): ResearchRecord {
  const q = String(query ?? "").trim();
  return {
    id: `research-${now}`,
    query: q,
    timestamp: localizedTimestamp(new Date(now)),
    updatedAt: now,
    status: "running",
    planning: instantPlan(q),
    reasoning: "",
    steps: [],
    updates: [],
    summary: "",
    blocks: [],
  };
}

// ── 记录归一（持久化读回容错：坏数据回退安全默认，不抛）──
export function normalizeRecord(raw: unknown): ResearchRecord | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Partial<ResearchRecord>;
  if (typeof r.id !== "string" || !r.id) return null;
  const status: ResearchStatus = r.status === "done" || r.status === "error" ? r.status : "running";
  return {
    id: r.id,
    query: typeof r.query === "string" ? r.query : "",
    timestamp: typeof r.timestamp === "string" ? r.timestamp : localizedTimestamp(),
    updatedAt: typeof r.updatedAt === "number" ? r.updatedAt : Date.now(),
    status,
    planning: typeof r.planning === "string" ? r.planning : undefined,
    reasoning: typeof r.reasoning === "string" ? r.reasoning : "",
    steps: Array.isArray(r.steps) ? (r.steps as ResearchStep[]) : [],
    updates: Array.isArray(r.updates) ? (r.updates as ResearchUpdate[]) : [],
    summary: typeof r.summary === "string" ? r.summary : "",
    editedSummary: typeof r.editedSummary === "string" ? r.editedSummary : undefined,
    reportRevision: typeof r.reportRevision === "number" ? r.reportRevision : undefined,
    blocks: Array.isArray(r.blocks) ? r.blocks : [],
    threadId: typeof r.threadId === "string" ? r.threadId : undefined,
    turnId: typeof r.turnId === "string" ? r.turnId : undefined,
    error: typeof r.error === "string" ? r.error : undefined,
  };
}

// ── 内部会话标题（B09：功能名+课题前 60 字）──
export const RESEARCH_THREAD_PREFIX = "调研报告";
export function isResearchThreadTitle(title: string): boolean {
  return typeof title === "string" && title.startsWith(RESEARCH_THREAD_PREFIX);
}
export function researchThreadTitle(query: string): string {
  const q = String(query ?? "").trim().slice(0, TITLE_MAX_CHARS);
  return `${RESEARCH_THREAD_PREFIX} · ${q}`;
}

// ── 思考球状态映射（B18：composing/searching/working/solving；规划期=solving）──
export type OrbState = "composing" | "searching" | "working" | "solving";
export function orbStateOf(text: string, phase: "planning" | "running" = "running"): OrbState {
  if (phase === "planning") return "solving";
  const t = String(text ?? "");
  if (/总结|综述|成文|撰写|归纳/u.test(t)) return "composing";
  if (/搜索|检索|查询|案例|法规|法条/u.test(t)) return "searching";
  return "working";
}

// ── 工具步骤图标八类（B15：搜索/案例/文献/法规/总结/web/通用/错误）──
export function stepIconKind(tool: string, summary?: string): StepIconKind {
  const s = `${tool ?? ""} ${summary ?? ""}`;
  if (/失败|错误|error|failed/iu.test(s)) return "error";
  if (/总结|综述|归纳|summary/iu.test(s)) return "summary";
  if (/案例|判例|裁判|case/iu.test(s)) return "case";
  if (/法规|法条|statute|law/iu.test(s)) return "statute";
  if (/文献|文档|文书|document|paper/iu.test(s)) return "doc";
  if (/web|网页|浏览器|browser|http/iu.test(s)) return "web";
  if (/search|搜索|检索|query/iu.test(s)) return "search";
  return "general";
}

// ── 实时状态条时长格式（B16：s/m/h）──
export function durationFormat(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h`;
}

// ── 发送提示词（B11：固定模板五要素，课题内插；文案全自写，无网页替代条）──
export function buildResearchPrompt(query: string): string {
  const q = String(query ?? "").trim();
  return [
    "你是法律调研助手。请围绕文末课题完成一次多来源调研，并在本轮直接交付全部成果。",
    "",
    "【交付要求】",
    "1. 全部使用中文，并在本轮内直接给出最终调研报告，不要以「后续再继续」之类的话收尾。",
    "2. 可以先在内部拟定检索与写作计划，也可以用简短的阶段播报同步进度，但计划与播报都不能替代最终报告；不要等全部检索完成才开始组织报告，拿到材料就边整理边成文。",
    "3. 使用哪些检索工具与资料来源由你自主决定；现有来源足以支撑课题时不要继续扩张检索面，优先用好主来源（所内法规库与案例库）。",
    "4. 某一来源检索失败或内容无法核验时，就此停手、改用其他已获得的材料继续完成；确实无法核验的内容如实标注「未经核验」，不要因此中断整份报告。",
    "5. 最终报告按五节组织（结论与建议 / 法律依据与效力 / 相关案例 / 分析与风险 / 来源与核验）；保留材料中的真实链接，没有链接的依据按「库名＋法规名/文件名＋条文序号或案号」标注出处；一律不得猜测或编造依据。",
    "",
    "【课题】",
    q,
  ].join("\n");
}

// ── 首选源指令（B50：三源枚举；覆盖记忆偏好；确定性错误切备源；双败走 web 并标注）──
export function primarySourceDirective(sourceId: string): string | null {
  const src = PRIMARY_LEGAL_SOURCES.find((s) => s.id === sourceId);
  if (!src) return null;
  return [
    `【首选来源】本次调研优先使用「${src.label}」作为主检索来源，该偏好优先于既往记忆中的来源习惯。`,
    `若「${src.label}」返回鉴权失败、配额用尽等确定性错误，立即改用其余备源或本地知识库，不要反复重试。`,
    "若各权威库均不可用，改用网页检索获取原文，并在报告「来源与核验」一节如实标注「经 web 检索，未经权威数据库核实」，不得放弃检索。",
  ].join("\n");
}

// ── 阶段指令（B25 每步注入 / B24 续跑指令）──
export function buildStageDirective(opts: { hasPlan: boolean; continuation: boolean }): string {
  const parts: string[] = [];
  if (opts.continuation) {
    parts.push("上一轮回复尚未形成完整的调研报告。请基于已获得的材料直接补完，并输出完整报告。");
  }
  if (opts.hasPlan) {
    parts.push("检索与写作规划已形成，不要重新规划，按既有规划推进。");
  }
  parts.push("现有来源足以支撑时不要扩张检索面；直接输出完整调研报告（五节结构：结论与建议 / 法律依据与效力 / 相关案例 / 分析与风险 / 来源与核验）。");
  parts.push("来源不足或工具失败时，在报告中如实标注局限并继续完成，不得终止交付、不得吞掉报告。");
  return parts.join("\n");
}

// ── 法规库兜底检索（B31 轻量期=本地法规库索引直检；官方法规 API 直检随数据工程解挂）──
// 三策略：标题精确/标题模糊/正文模糊；候选排序=现行有效→标题命中→法源位阶→多策略重合；
// 只认带可定位出处（文件名/条号）的条目；库不可用=fail-closed 话术，不升级浏览器自动化。
export const LAW_LEVEL_ORDER: Readonly<Record<string, number>> = {
  宪法: 0, 法律: 1, 行政法规: 2, 部门规章: 3, 地方性法规: 4, 司法解释: 5,
  军事法规: 6, 经济特区法规: 7, 国际条约: 8, 规范性文件: 9,
};
export interface LawIndexEntry {
  id?: string; name?: string; level?: string; filename?: string;
  publish?: string; valid_from?: string; valid_to?: string; subtitle?: string;
  tags?: unknown; content?: string;
}
export interface LawHit {
  id: string; name: string; level: string; filename: string;
  validity: "现行" | "已废止" | "时效不明";
  matched: string[]; // 命中策略（title_exact/title_partial/fulltext）
}
export interface LawLookupResult {
  ok: boolean;
  hits: LawHit[];
  notice?: string; // fail-closed 话术
}
// 时效标签：valid_to=2099-12-31 或缺省→现行；=1970-01-01 墓碑→已废止；过真实日界→按日判
export function validityOf(entry: LawIndexEntry, today = new Date()): "现行" | "已废止" | "时效不明" {
  const from = entry.valid_from ? Date.parse(entry.valid_from) : NaN;
  const to = entry.valid_to ? Date.parse(entry.valid_to) : NaN;
  if (entry.valid_to === "1970-01-01") return "已废止";
  if (!entry.valid_from && !entry.valid_to) return "时效不明";
  const t = today.getTime();
  if (!Number.isNaN(from) && t < from) return "已废止";
  if (entry.valid_to && entry.valid_to !== "2099-12-31") {
    if (Number.isNaN(to)) return "时效不明";
    if (t > to) return "已废止";
  }
  return "现行";
}
export function lookupLawsLibrary(entries: ReadonlyArray<LawIndexEntry>, query: string, today = new Date()): LawLookupResult {
  const q = String(query ?? "").trim();
  if (!q) return { ok: false, hits: [], notice: "未执行法规检索：检索词为空。" };
  const scored: Array<{ e: LawIndexEntry; matched: string[] }> = [];
  const nameOf = (e: LawIndexEntry) => String(e.name ?? "");
  for (const e of entries) {
    const matched: string[] = [];
    const name = nameOf(e);
    if (name && name === q) matched.push("title_exact");
    else if (name && name.includes(q)) matched.push("title_partial");
    const body = String(e.content ?? "").slice(0, 200000);
    if (!matched.length && body && body.includes(q)) matched.push("fulltext");
    if (!matched.length && Array.isArray(e.tags) && e.tags.some((t) => String(t).includes(q))) matched.push("title_partial");
    if (matched.length) scored.push({ e, matched });
  }
  scored.sort((a, b) => {
    const va = validityOf(a.e, today) === "现行" ? 0 : 1;
    const vb = validityOf(b.e, today) === "现行" ? 0 : 1;
    if (va !== vb) return va - vb;
    const ma = a.matched.includes("title_exact") ? 0 : a.matched.includes("title_partial") ? 1 : 2;
    const mb = b.matched.includes("title_exact") ? 0 : b.matched.includes("title_partial") ? 1 : 2;
    if (ma !== mb) return ma - mb;
    const la = LAW_LEVEL_ORDER[String(a.e.level ?? "")] ?? 99;
    const lb = LAW_LEVEL_ORDER[String(b.e.level ?? "")] ?? 99;
    if (la !== lb) return la - lb;
    return b.matched.length - a.matched.length;
  });
  return {
    ok: true,
    hits: scored.slice(0, 10).map(({ e, matched }) => ({
      id: String(e.id ?? e.filename ?? nameOf(e)),
      name: nameOf(e),
      level: String(e.level ?? ""),
      filename: String(e.filename ?? ""),
      validity: validityOf(e, today),
      matched,
    })),
  };
}
// fail-closed 话术（B31：失败引导，不升级浏览器自动化；文案自写）
export const LAW_LOOKUP_UNAVAILABLE =
  "本地法规库当前不可用，法规直检兜底就此停止。请改用已配置的其他来源继续调研，或先安装并启用本地法规库；不要转向浏览器自动化抓取。";

// ── 工具步骤构造（B15：八类图标映射已就位，此处补步骤构造与错误步文案；B28 同源：
//     步骤/目录只追加进信息面，永不落 error——目录漂移不判失败的轻量形态）──
export const STEP_ERROR_TEXT = "调用失败，将尝试其他方法继续调研。"; // B15 错误步骤文案（自写等量）
export function toResearchStep(spec: {
  id: string; name: string; input?: string; output?: string; error?: string;
  status?: ResearchStep["status"];
}): ResearchStep {
  const failed = Boolean(spec.error);
  return {
    id: spec.id,
    tool: spec.name,
    icon: failed ? "error" : stepIconKind(spec.name, spec.output ?? spec.input),
    status: spec.status ?? (failed ? "error" : "done"),
    input: spec.input ?? "",
    output: spec.output,
    detail: failed ? (spec.error ?? STEP_ERROR_TEXT) : undefined,
    meta: undefined,
  };
}
// oc28 assistant 消息里 tool-call part 的提取（形状族到达即点亮；当前模型实测无此类 part 时恒空，不伪造）
export interface ToolCallPartLike {
  type?: unknown; name?: unknown; toolName?: unknown; function?: { name?: unknown } | null;
  input?: unknown; arguments?: unknown; output?: unknown; error?: unknown;
}
export function extractToolCalls(parts: ReadonlyArray<ToolCallPartLike>): Array<{ name: string; input: string; output: string; error?: string }> {
  const out: Array<{ name: string; input: string; output: string; error?: string }> = [];
  for (const p of parts ?? []) {
    const isCall = p && (p.type === "tool-call" || p.type === "tool_use" || typeof p.toolName === "string" || (p.type === "tool-call" && typeof (p.function as { name?: unknown } | null)?.name === "string"));
    if (!isCall) continue;
    const name = String(p.name ?? p.toolName ?? (p.function as { name?: unknown } | null)?.name ?? "").trim();
    if (!name) continue;
    const rawInput = p.input ?? p.arguments;
    const input = typeof rawInput === "string" ? rawInput : rawInput ? JSON.stringify(rawInput) : "";
    const rawOut = p.output;
    const output = typeof rawOut === "string" ? rawOut : rawOut ? JSON.stringify(rawOut) : "";
    out.push({ name, input, output, error: typeof p.error === "string" ? p.error : undefined });
  }
  return out;
}

// ── 证据门/配额切换/三类续跑：回合链活接线用的指令装配与判定器（B22/B23/B26/B30）──
// B22 证据未齐：强制取证指令（自家检索工具名族，对拍 22）
// B23 法规证据就绪：剔除装饰类指令（对拍 23）
export function buildEvidenceDirective(gate: { regulationReady: boolean; caseReady: boolean; synthesisReady: boolean }, hasPlan: boolean): string {
  if (gate.synthesisReady) {
    // B51 轻量期同构（对拍 53）：法规+案例证据齐→综合跳收敛思考面（省一轮逐项展开/再检索）。
    // 真实 per-request reasoningEffort 开关无通道：oc28 模型会话创建即绑定、prompt 体不可带
    // （runtime adapter createSession 实测注记；原 oc28client.mjs:39-43，r12 波2.5 迁 packages/juscite-runtime-adapters/opencode），随 oc28 面解挂后可换真开关。
    return "法规与案例证据均已齐备：请直接整理既有材料输出最终完整报告，不再发起新的检索，也不必重复展开已完成的逐项分析。";
  }
  if (gate.regulationReady) {
    return "法规证据已就绪：不要再使用网页检索、网页抓取或链接装饰类工具，优先基于已有法规与案例材料综合成文。";
  }
  if (hasPlan) {
    return "检索证据尚未齐备（法规与案例两类）。请先调用检索工具取证——法规类（如 laws_search）与案例类（如 case_search）各至少一次，取得足量载荷后再综合，不要直接给出结论。";
  }
  return "";
}
// B26 配额/鉴权确定性错误：立即切 web 兜底、不再重试该类来源（对拍 27）
export function buildQuotaFallbackDirective(): string {
  return "权威来源出现鉴权或配额类确定性错误，已停止重试该类来源：请改用网页检索获取原文继续调研，并在报告「来源与核验」一节如实标注「经 web 检索，未经权威数据库核实」，不得放弃检索。";
}
// B30「宣布要调工具没调」识别（文本宣布但本跳无工具事件）
export const ANNOUNCE_TOOL_RE = /(将调用|接下来调用|先调用|准备调用|马上调用|需要调用)[^。\n]{0,24}(工具|检索|搜索)/u;
// B30 三类续跑分类（各 ≤2；reasoning_only=纯思考无正文；no_tool=规划已发且证据未齐但零工具；
// announce_no_call=宣布调用却没调）。bridge 链按类计数收口，防同一形态无限续跑。
export type ContinuationKind = "none" | "reasoning_only" | "no_tool" | "announce_no_call";
export function classifyContinuation(prev: { text: string; reasoning: string; toolCount: number }, cur: {
  text: string; reasoning: string; toolCount: number; gate: { synthesisReady: boolean }; hasPlan: boolean;
}): ContinuationKind {
  const textGrew = cur.text.length > prev.text.length;
  const reasoningGrew = cur.reasoning.length > prev.reasoning.length;
  const newTools = cur.toolCount > prev.toolCount;
  if (textGrew && newTools === false && ANNOUNCE_TOOL_RE.test(cur.text.slice(prev.text.length))) return "announce_no_call";
  if (!textGrew && reasoningGrew) return "reasoning_only";
  if (!newTools && cur.hasPlan && !cur.gate.synthesisReady) return "no_tool";
  return "none";
}

// ── 记录派生装配（桥侧轮询投影单源：rows → 派生字段；UI 直接渲染桥面结果）──
export interface ThreadRowLike {
  kind: string;
  state?: string;
  text?: string;
  reasoning?: string;
}
export interface DerivedResearch {
  planning: string | null;
  updates: ResearchUpdate[];
  summary: string;
  reasoning: string;
}
export function deriveFromRows(rows: ReadonlyArray<ThreadRowLike>, now = Date.now()): DerivedResearch {
  const assistantText = rows
    .filter((r) => r.kind === "assistantText")
    .map((r) => String(r.text ?? ""))
    .join("\n\n")
    .trim();
  const reasoning = rows
    .filter((r) => r.kind === "assistantText")
    .map((r) => String(r.reasoning ?? ""))
    .filter(Boolean)
    .join("\n\n");
  // 优先从正文切分（三桶）；正文无规划时从 reasoning 提取（B12 reasoning 与正文双通道）
  const split = splitResearchStream(assistantText, now);
  let planning = split.planning;
  if (!planning && reasoning) {
    const fromReasoning = extractPlan(reasoning);
    planning = fromReasoning.plan;
  }
  return { planning, updates: split.updates, summary: split.summary, reasoning };
}
