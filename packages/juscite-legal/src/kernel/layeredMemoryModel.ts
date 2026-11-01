// 功能 #36 分层记忆纯模型（RE-36-分层记忆.md 实现规格 §3）。
// 桥/合成自测单一来源（沿 learningModel/caseGraphModel 先例）：四层两作用域映射/
// 条目规范（来源+时间戳）/分类树回写合并（F2 等量：去重合并·新节点追加·计数+last_updated·
// 空库直接创建 F4）/代表方确认回写五要素（F12：去重+次数+日期+类别并入+尺度计票）/
// 置信门三分支（F8 唯一命中直采+告知可改 / F9 多命中弹窗置顶·并列取最近 / 无历史按无记忆 F18）
// 与 inputs 显式传入优先（F11：被覆盖字段不进 questions、整组全被覆盖则整批不发）/
// 偏好规则类别匹配（F14：类型文件>通用文件·多命中只取第一个·缺失静默 F15）/
// 注入按层装配（§3：项目约定优先于个人偏好）/researched 沉淀复用（F5：研究一次同类不再研究；
// F6：研究未做不沉淀不改标记）/路径安全（记忆域白名单）。
// 全部正则+状态机零模型（工作区铁律）；文案全部自写（表达隔离：等量≠抄文案）；
// 零 node 依赖（介质无关，浏览器可打包）。

// ── 四层两作用域（§3 数据模型）──
export type MemoryLayer = "preference" | "correction" | "convention" | "resource";
export type MemoryScope = "user" | "project";

export const MEMORY_LAYERS: readonly MemoryLayer[] = ["preference", "correction", "convention", "resource"];

export const LAYER_LABELS: Record<MemoryLayer, string> = {
  preference: "个人偏好",
  correction: "操作纠正",
  convention: "项目约定",
  resource: "资源指引",
};

export const SCOPE_LABELS: Record<MemoryScope, string> = {
  user: "用户级（跨案跟随律师）",
  project: "项目级（随项目隔离）",
};

// §3 有意偏离：偏好按用户级作用域跨案跟随（D2 文档口径），不随单只业务流。
export function scopeOfLayer(layer: MemoryLayer): MemoryScope {
  return layer === "convention" || layer === "resource" ? "project" : "user";
}

// ── 条目规范（§3：条目带来源与时间戳）──
export interface MemoryEntry {
  id: string;
  layer: MemoryLayer;
  content: string;
  source: "explicit" | "auto"; // explicit=显式纠正；auto=模式沉淀（重复选择/偏好自动累积）
  origin?: string;             // 来源业务动作/线程标识
  createdAt: number;
  updatedAt: number;
}

let idSeed = 0;
export function newMemoryId(prefix: string, now: number): string {
  idSeed = (idSeed + 1) % 1296;
  return `${prefix}_${now.toString(36)}${idSeed.toString(36).padStart(2, "0")}`;
}

// ── 操作纠正记录（显式纠正写入；同类去重累加，不覆盖既有做法描述）──
export interface CorrectionRecord {
  id: string;
  scene: string;   // 场景关键词（去重键组成）
  wrong: string;   // 被纠正的做法
  right: string;   // 应采用的做法
  source: "explicit";
  origin?: string;
  count: number;   // 同类纠正累计次数
  createdAt: number;
  updatedAt: number;
}

export interface CorrectionsFile {
  _meta: { description: string; last_updated: string };
  records: CorrectionRecord[];
}

export function emptyCorrectionsFile(now: number): CorrectionsFile {
  return {
    _meta: { description: "操作纠正记录：用户指出并纠正过的做法，由纠正动作写入（可查看可清除）", last_updated: isoDateOf(now) },
    records: [],
  };
}

export function normalizeCorrectionsFile(raw: unknown, now: number): CorrectionsFile {
  const base = emptyCorrectionsFile(now);
  if (!raw || typeof raw !== "object") return base;
  const records = (raw as CorrectionsFile).records;
  if (!Array.isArray(records)) return base;
  return { _meta: base._meta, records: records.filter((r) => r && typeof r === "object" && typeof r.right === "string") };
}

// 去重键=场景+旧做法+新做法（trim 后全等）：同类再犯只累加次数与时间戳，不重复建行。
export function mergeCorrection(
  file: CorrectionsFile,
  incoming: { scene: string; wrong: string; right: string; origin?: string },
  now: number,
): { file: CorrectionsFile; id: string; merged: "updated" | "appended" } {
  const scene = String(incoming.scene ?? "").trim();
  const wrong = String(incoming.wrong ?? "").trim();
  const right = String(incoming.right ?? "").trim();
  if (!right) throw new Error("纠正后的做法不能为空");
  const key = (r: CorrectionRecord) => `${r.scene}\u0000${r.wrong}\u0000${r.right}`;
  const target = file.records.find((r) => key(r) === `${scene}\u0000${wrong}\u0000${right}`);
  if (target) {
    const updated: CorrectionRecord = { ...target, count: target.count + 1, updatedAt: now };
    const out: CorrectionsFile = {
      ...file,
      records: file.records.map((r) => (r === target ? updated : r)),
      _meta: { ...file._meta, last_updated: isoDateOf(now) },
    };
    return { file: out, id: updated.id, merged: "updated" };
  }
  const id = newMemoryId("cor", now);
  const out: CorrectionsFile = {
    ...file,
    records: [...file.records, { id, scene, wrong, right, source: "explicit", origin: incoming.origin, count: 1, createdAt: now, updatedAt: now }],
    _meta: { ...file._meta, last_updated: isoDateOf(now) },
  };
  return { file: out, id, merged: "appended" };
}

// 注入面渲染：turnText 命中场景关键词的记录优先，其余按时间截尾；无命中返回全部（截尾）。
export function renderCorrectionLines(records: CorrectionRecord[], turnText: string, cap = 6): string[] {
  const q = String(turnText ?? "");
  const hit = records.filter((r) => r.scene && q.includes(r.scene));
  const rest = records.filter((r) => !hit.includes(r));
  const ordered = [...hit, ...rest].sort((a, b) => b.updatedAt - a.updatedAt);
  return ordered.slice(0, cap).map((r) => `- 场景「${r.scene || "通用"}」：${r.wrong ? `不要${r.wrong}；` : ""}改按：${r.right}${r.count > 1 ? `（已纠正 ${r.count} 次）` : ""}`);
}

// ── 分类树（F2/F3/F4；deal_type 六选一全域钉定，transaction-structure 口径等量自写）──
export type TaxonomyTreeKey = "contract_category" | "deal_type" | "industry_sector";
export const TAXONOMY_TREE_KEYS: readonly TaxonomyTreeKey[] = ["contract_category", "deal_type", "industry_sector"];
export const DEAL_TYPE_ENUM = ["动产", "不动产", "服务行为", "禁止行为", "权利", "其他"] as const;

export interface TaxonomyNode {
  name: string;
  researched?: boolean;
  children?: TaxonomyNode[];
}

export interface TaxonomyFile {
  _meta: { description: string; total_classified: number; last_updated: string };
  trees: Record<TaxonomyTreeKey, TaxonomyNode[]>;
}

export function emptyTaxonomyFile(now: number): TaxonomyFile {
  return {
    _meta: { description: "项目分类知识树：首次为空库，由分类动作在每次业务后自动回写维护（无需手工编辑）", total_classified: 0, last_updated: isoDateOf(now) },
    trees: { contract_category: [], deal_type: [], industry_sector: [] },
  };
}

export function normalizeTaxonomyFile(raw: unknown, now: number): TaxonomyFile {
  const base = emptyTaxonomyFile(now);
  if (!raw || typeof raw !== "object") return base;
  const src = raw as TaxonomyFile;
  const out = base;
  // 落盘 meta 计数与日期随读回保留（F2 计数跨回合累计；缺失/非法回落空库 meta）
  const total = Number((src._meta as unknown as { total_classified?: unknown })?.total_classified);
  if (Number.isFinite(total) && total >= 0) out._meta.total_classified = Math.floor(total);
  if (typeof src._meta?.last_updated === "string" && src._meta.last_updated) out._meta.last_updated = src._meta.last_updated;
  if (typeof src._meta?.description === "string" && src._meta.description) out._meta.description = src._meta.description;
  const trees = src.trees;
  if (!trees || typeof trees !== "object") return out;
  for (const k of TAXONOMY_TREE_KEYS) {
    const v = (trees as Record<string, unknown>)[k];
    if (Array.isArray(v)) out.trees[k] = v.filter((n) => n && typeof n === "object" && typeof n.name === "string");
  }
  return out;
}

function findChild(nodes: TaxonomyNode[], name: string): TaxonomyNode | undefined {
  return nodes.find((n) => n.name === name);
}

// 深拷贝（回写合并不改调用方入参；节点形状浅，直接递归足够）。
function cloneNodes(nodes: TaxonomyNode[]): TaxonomyNode[] {
  return nodes.map((n) => ({ ...n, ...(n.children ? { children: cloneNodes(n.children) } : {}) }));
}

// F2 回写合并：已有节点只更新文件级 _meta（total+1/last_updated），新节点沿路径追加；
// 空库直接创建（F4）。deal_type 根节点必须在六选一内（域外拒绝，确定性枚举）。
export function mergeTaxonomy(
  file: TaxonomyFile,
  treeKey: TaxonomyTreeKey,
  path: string[],
  now: number,
): { file: TaxonomyFile; appended: string[] } {
  const names = path.map((s) => String(s ?? "").trim()).filter(Boolean);
  if (!names.length) throw new Error("分类路径为空");
  if (treeKey === "deal_type" && !DEAL_TYPE_ENUM.includes(names[0] as (typeof DEAL_TYPE_ENUM)[number])) {
    throw new Error(`deal_type 根节点须为六选一（${DEAL_TYPE_ENUM.join("/")}），收到：${names[0]}`);
  }
  const trees: TaxonomyFile["trees"] = { ...file.trees, [treeKey]: cloneNodes(file.trees[treeKey]) };
  let level = trees[treeKey];
  const appended: string[] = [];
  for (const name of names) {
    let node = findChild(level, name);
    if (!node) {
      node = { name };
      level.push(node);
      appended.push(name);
    }
    if (!node.children) node.children = [];
    level = node.children;
  }
  return {
    file: {
      trees,
      _meta: { ...file._meta, total_classified: file._meta.total_classified + 1, last_updated: isoDateOf(now) },
    },
    appended,
  };
}

// F5：研究完成后给叶节点打 researched 标记（叶=树上既有节点按名 DFS 首个命中；
// 节点不存在=错误，不虚设节点——未分类过的叶无从谈起沉淀）。
export function markResearched(
  file: TaxonomyFile,
  treeKey: TaxonomyTreeKey,
  path: string[],
): TaxonomyFile {
  const names = path.map((s) => String(s ?? "").trim()).filter(Boolean);
  if (names.length !== 1) throw new Error("沉淀叶须为单节点名");
  const trees: TaxonomyFile["trees"] = { ...file.trees, [treeKey]: cloneNodes(file.trees[treeKey]) };
  const hit = dfsFind(trees[treeKey], names[0]);
  if (!hit) throw new Error(`分类路径不存在：${names[0]}`);
  hit.researched = true;
  return { ...file, trees };
}

function dfsFind(nodes: TaxonomyNode[], name: string): TaxonomyNode | undefined {
  for (const n of nodes) {
    if (n.name === name) return n;
    if (n.children?.length) {
      const sub = dfsFind(n.children, name);
      if (sub) return sub;
    }
  }
  return undefined;
}

// 树上按名查节点（DFS 首个命中；读侧复用判断与写侧 markResearched 同一定位语义）。
export function findTaxonomyNode(file: TaxonomyFile, treeKey: TaxonomyTreeKey, name: string): TaxonomyNode | undefined {
  return dfsFind(file.trees[treeKey], String(name ?? "").trim());
}

// ── 代表方确认史（F7/F12/F13）──
export interface RepresentativeRow {
  name: string;                  // 主体全称（去重键）
  role: string;                  // 常代表阵营
  categories: string[];          // 涉及合同类别（并入去重）
  selectCount: number;           // 选择次数
  lastSelectedAt: string;        // 最近选择日期（ISO date）
  scaleVotes: Record<string, number>; // 审查尺度计票
}

export interface RepresentativesFile {
  _meta: { description: string; last_updated: string };
  rows: RepresentativeRow[];
}

export function emptyRepresentativesFile(now: number): RepresentativesFile {
  return {
    _meta: { description: "代表方确认史：由确认动作自动回写维护（无需手工编辑）", last_updated: isoDateOf(now) },
    rows: [],
  };
}

export function normalizeRepresentativesFile(raw: unknown, now: number): RepresentativesFile {
  const base = emptyRepresentativesFile(now);
  if (!raw || typeof raw !== "object") return base;
  const rows = (raw as RepresentativesFile).rows;
  if (!Array.isArray(rows)) return base;
  return { _meta: base._meta, rows: rows.filter((r) => r && typeof r === "object" && typeof r.name === "string") };
}

// F12 五要素回写：按主体全称去重、选择次数+1、更新最近选择日期、合同类别并入去重、
// 审查尺度计票累加；新主体追加一行。F13：只回写调用方确认的主体（未确认项不进本函数）；
// 自定义名称同样入账（名称不做枚举校验）。
export function mergeRepresentative(
  file: RepresentativesFile,
  incoming: { name: string; role?: string; category?: string; scale?: string; date?: string },
  now: number,
): { file: RepresentativesFile; merged: "updated" | "appended" } {
  const name = String(incoming.name ?? "").trim();
  if (!name) throw new Error("主体全称不能为空");
  const date = incoming.date ?? isoDateOf(now);
  const rows = file.rows.map((r) => ({ ...r, categories: [...r.categories], scaleVotes: { ...r.scaleVotes } }));
  const target = rows.find((r) => r.name === name);
  if (target) {
    target.selectCount += 1;
    if (date > target.lastSelectedAt) target.lastSelectedAt = date;
    if (incoming.role) target.role = incoming.role;
    if (incoming.category && !target.categories.includes(incoming.category)) target.categories.push(incoming.category);
    if (incoming.scale) target.scaleVotes[incoming.scale] = (target.scaleVotes[incoming.scale] ?? 0) + 1;
    const out: RepresentativesFile = { rows, _meta: { ...file._meta, last_updated: isoDateOf(now) } };
    return { file: out, merged: "updated" };
  }
  const row: RepresentativeRow = {
    name,
    role: incoming.role ?? "",
    categories: incoming.category ? [incoming.category] : [],
    selectCount: 1,
    lastSelectedAt: date,
    scaleVotes: incoming.scale ? { [incoming.scale]: 1 } : {},
  };
  const out: RepresentativesFile = { rows: [...rows, row], _meta: { ...file._meta, last_updated: isoDateOf(now) } };
  return { file: out, merged: "appended" };
}

// ── 置信门（F8/F9/F10/F11/F18）──
export interface GateCandidate {
  name: string;
  role?: string;
  selectCount: number;
  lastSelectedAt: string;
  scaleVotes?: Record<string, number>;
}

export interface GateInputs {
  partyName?: string; // inputs 显式传入（F11：优先于历史记忆、不提示历史）
  scale?: string;
}

export interface GateQuestion {
  key: "party" | "scale";
  pinnedDefault?: string; // 记忆默认置顶（无命中/无记录=无默认，F18）
}

export interface GateResult {
  mode: "direct" | "ask"; // ask=有题待确认；direct=整批无题
  adopted: { name?: string; role?: string; scale?: string };
  notice: string;   // F10：凡因记忆跳过必一句话告知采用了什么+如何改；inputs 传入不提示历史=空
  questions: GateQuestion[]; // 被覆盖字段不进数组（F11）；整组全被覆盖=空数组（整批不发）
}

// 压倒性多数阈值（自定判定：竞品真值表行 :83-86 只载"单一或压倒性多数跳过"，数值未拆出）：
// 顶票占比 ≥0.75 且顶票 ≥2 视为压倒性；只有一种尺度=单一。其余按拉锯处理（弹窗置顶默认）。
export const SCALE_DOMINANT_SHARE = 0.75;
export const SCALE_DOMINANT_MIN_VOTES = 2;

export function resolveConfidenceGate(candidates: GateCandidate[], inputs?: GateInputs): GateResult {
  const inParty = String(inputs?.partyName ?? "").trim();
  const inScale = String(inputs?.scale ?? "").trim();
  const adopted: GateResult["adopted"] = {};
  let notice = "";
  const questions: GateQuestion[] = [];

  // 主体侧：inputs 传入优先且不提示历史（F11/F13：inputs 场景不产 notice）
  if (!inParty) {
    if (candidates.length === 1) {
      // F8：唯一命中=高置信直采，与选择次数无关；F10 一句话告知+可改
      const only = candidates[0];
      adopted.name = only.name;
      adopted.role = only.role || undefined;
      notice = `已按历史记录直接采用代表方「${only.name}」${only.role ? `（${only.role}）` : ""}，如需更换直接说明即可。`;
    } else if (candidates.length >= 2) {
      // F9：多命中弹窗置顶，默认=选择次数最高，并列取最近日期
      const sorted = [...candidates].sort((a, b) =>
        b.selectCount - a.selectCount || (a.lastSelectedAt < b.lastSelectedAt ? 1 : a.lastSelectedAt > b.lastSelectedAt ? -1 : a.name < b.name ? -1 : 1));
      questions.push({ key: "party", pinnedDefault: sorted[0].name });
    } else {
      // F18：无历史/空表/无命中=按无记忆正常走弹窗（题照出，无默认）
      questions.push({ key: "party" });
    }
  } else {
    adopted.name = inParty;
  }

  // 尺度侧：计票池=参与本门的历史行（唯一命中/多命中的并集；无历史=无票）
  if (!inScale) {
    const votes: Record<string, number> = {};
    for (const c of candidates) {
      for (const [k, v] of Object.entries(c.scaleVotes ?? {})) {
        if (typeof v === "number" && v > 0) votes[k] = (votes[k] ?? 0) + v;
      }
    }
    const keys = Object.keys(votes);
    if (keys.length > 0) {
      const sortedKeys = keys.sort((a, b) => votes[b] - votes[a] || (a < b ? -1 : 1));
      const top = sortedKeys[0];
      const total = keys.reduce((s, k) => s + votes[k], 0);
      const dominant = keys.length === 1 || (votes[top] >= SCALE_DOMINANT_MIN_VOTES && votes[top] / total >= SCALE_DOMINANT_SHARE);
      if (!dominant) questions.push({ key: "scale", pinnedDefault: top }); // F9 拉锯→题照出+默认置顶
      else adopted.scale = top; // F8 单一/压倒性→跳过
    } else {
      questions.push({ key: "scale" }); // 无尺度记录→照出（无默认，F18 同族）
    }
  } else {
    adopted.scale = inScale;
  }

  return { mode: questions.length > 0 ? "ask" : "direct", adopted, notice, questions };
}

// ── 偏好规则文件（F14/F15/F16）──
export interface PreferenceRuleFile {
  fileName: string;
  typeKey: string | null; // null=通用文件
  body: string;
}

export const PREFERENCE_COMMON_FILE = "preferences.md";
export const PREFERENCE_TYPE_PREFIX = "preferences-";

export function typeKeyOfPreferenceFileName(fileName: string): string | null {
  if (fileName === PREFERENCE_COMMON_FILE) return null;
  if (fileName.startsWith(PREFERENCE_TYPE_PREFIX) && fileName.endsWith(".md")) {
    const key = fileName.slice(PREFERENCE_TYPE_PREFIX.length, -3);
    if (key) return key;
  }
  return null;
}

// F14：类别关键词命中类型文件；类型文件优先于通用文件；多关键词命中只取第一个（数组序）。
export function matchPreferenceFiles(
  files: PreferenceRuleFile[],
  category: string,
): { typeFile: PreferenceRuleFile | null; commonFile: PreferenceRuleFile | null } {
  const cat = String(category ?? "");
  const typeFile = files.map((f) => (f.typeKey && cat.includes(f.typeKey) ? f : null)).find(Boolean) ?? null;
  const commonFile = files.find((f) => f.typeKey === null) ?? null;
  return { typeFile, commonFile };
}

// ── 注入装配（§3：对话上下文按层装配，项目约定优先于个人偏好；空段静默跳过 F15）──
export interface InjectionSection {
  key: string;        // 文件相对路径或纠正段标识（对账 id）
  layer: MemoryLayer;
  body: string;
}

export const INJECTION_BUDGET_CHARS = 2400;

export function assembleInjection(sections: InjectionSection[], opts?: { budgetChars?: number }): { block: string; usedKeys: string[] } {
  const budget = opts?.budgetChars ?? INJECTION_BUDGET_CHARS;
  const order: Record<MemoryLayer, number> = { convention: 0, preference: 1, correction: 2, resource: 3 };
  const usable = sections
    .filter((s) => s.body && s.body.trim())
    .sort((a, b) => order[a.layer] - order[b.layer] || (a.key < b.key ? -1 : 1));
  const lines: string[] = [];
  const usedKeys: string[] = [];
  let used = 0;
  for (const s of usable) {
    const chunk = `【${LAYER_LABELS[s.layer]}】\n${s.body.trim()}`;
    if (used + chunk.length > budget) break;
    used += chunk.length;
    lines.push(chunk);
    usedKeys.push(s.key);
  }
  if (!lines.length) return { block: "", usedKeys: [] };
  const block = "【分层记忆】以下是本项目与该律师此前的稳定约定与习惯，回答时自然遵循，不要逐条复述：\n" + lines.join("\n\n");
  return { block, usedKeys };
}

// ── researched 沉淀复用（F5/F6）──
export interface ResearchDecision {
  reuse: boolean;        // researched 且沉淀文件可读 → 直接复用不再研究（F5）
  needResearch: boolean; // 需要研究（未标记或沉淀文件缺失）
  sediment: string | null;
}

export function researchReuseDecision(researched: boolean, sediment: string | null): ResearchDecision {
  if (researched && sediment !== null && sediment.trim()) return { reuse: true, needResearch: false, sediment };
  return { reuse: false, needResearch: true, sediment };
}

// F6：研究未做（内容为空）→ 不沉淀文件、不改标记（由运行时在写入入口拦截）。
export function canSedimentResearch(content: string): boolean {
  return Boolean(String(content ?? "").trim());
}

// ── 路径安全（记忆域白名单；确定性段校验，零 node 依赖）──
// 允许段：中英文/数字/点/下划线/连字符；拒绝空段、点段、盘符、绝对前缀。
const SEGMENT_RE = /^[^\\/]+$/;

export type MemoryFileKind = "handwritten" | "auto";

// 解析相对路径→规范化段；非法= null（越界/逃逸拒绝）。
export function normalizeMemoryRelPath(rel: string): string[] | null {
  const raw = String(rel ?? "").replace(/\\/g, "/");
  if (!raw || raw.startsWith("/") || /^[a-zA-Z]:/.test(raw)) return null;
  const segs = raw.split("/");
  for (const s of segs) {
    if (!SEGMENT_RE.test(s) || s === "." || s === "..") return null;
  }
  return segs;
}

// 记忆域文件白名单（F1 文件族 + F17 边界）：
// handwritten=可直接编辑（偏好 md 族/项目约定/资源指引，F16）；auto=只经回写 API 变更（F17）。
export function resolveMemoryFileKind(segs: string[]): { kind: MemoryFileKind; scope: MemoryScope; layer: MemoryLayer | null } | null {
  if (segs.length === 2 && segs[0] === "user") {
    const f = segs[1];
    if (typeKeyOfPreferenceFileName(f) !== null || f === PREFERENCE_COMMON_FILE) {
      return { kind: "handwritten", scope: "user", layer: "preference" };
    }
    if (f === "corrections.json") return { kind: "auto", scope: "user", layer: "correction" };
    return null;
  }
  if (segs.length === 3 && segs[0] === "projects") {
    const f = segs[2];
    if (f === "conventions.md") return { kind: "handwritten", scope: "project", layer: "convention" };
    if (f === "resources.md") return { kind: "handwritten", scope: "project", layer: "resource" };
    return null;
  }
  if (segs.length === 4 && segs[0] === "projects" && segs[2] === "auto") {
    const f = segs[3];
    if (f === "taxonomy.json") return { kind: "auto", scope: "project", layer: "convention" };
    if (f === "representatives.json") return { kind: "auto", scope: "project", layer: "preference" };
    return null;
  }
  if (segs.length === 5 && segs[0] === "projects" && segs[2] === "auto" && segs[3] === "research" && segs[4].endsWith(".md")) {
    return { kind: "auto", scope: "project", layer: "convention" };
  }
  return null;
}

// 项目 id 段校验（MatterLite mat_* 或等长安全段；路径逃逸拒绝）。
export function isValidProjectId(projectId: string): boolean {
  const s = String(projectId ?? "");
  return s.length > 0 && s.length <= 64 && SEGMENT_RE.test(s) && s !== "." && s !== ".." && !/^[a-zA-Z]:/.test(s);
}

// ── 时间工具 ──
export function isoDateOf(nowMs: number): string {
  return new Date(nowMs).toISOString().slice(0, 10);
}
