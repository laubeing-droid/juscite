// 【步骤4·#5 冲突查重】冲突检索纯模型（RE-5-冲突查重.md 实现规格 §3.2）。
// 桥/UI/合成自测单一来源（同 caseGraphModel/caseTimelineModel 先例）：归一化/探针/四级匹配/
// 严重度矩阵/去重键/检索条件构造/指纹载荷/命中方式分组，全部纯函数零依赖零模型。
// 文案（角色/严重度标签、命中 reason 句式、自动结论备注）全部自写——表达隔离：语义对齐≠抄句子。
// ⚠ 过渡态：检索候选主体挂在桥内轻量案件表族（迁移 0012_conflict_check 注），MatterStore
// 解挂后随案件族翻牌真源、本模型的输入形状不变。

// ── 值域 ──
export const CONCLUSIONS = ["PENDING", "SAME_SUBJECT", "DIFFERENT", "NEED_INFO"] as const;
export type ConflictConclusion = (typeof CONCLUSIONS)[number];

export const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "BLOCKING"] as const;
export type ConflictSeverity = (typeof SEVERITIES)[number];

export const SEVERITY_RANK: Record<ConflictSeverity, number> = { LOW: 0, MEDIUM: 1, HIGH: 2, BLOCKING: 3 };

// 当事人角色七值（登记面；预检输入只开放前三，见 INPUT_ROLES）
export const ROLES = ["CLIENT", "OPPOSING_PARTY", "THIRD_PARTY", "CO_LITIGANT", "AGENT", "WITNESS", "OTHER"] as const;
export type PartyRole = (typeof ROLES)[number];
// 预检输入角色三选（B1：拟委托方/对方/第三人）
export const INPUT_ROLES: readonly PartyRole[] = ["CLIENT", "OPPOSING_PARTY", "THIRD_PARTY"];

// 命中两条腿（E1）：历史案件当事人 / 在办收案
export const HIT_TYPES = ["HISTORICAL_PARTY", "IN_PROGRESS_INTAKE"] as const;
export type ConflictHitType = (typeof HIT_TYPES)[number];

// ── 标签（自写；服务端 reason 用 ROLE_LABEL，命中卡徽章用 HIT_ROLE_LABEL——两张面各持一套，
//    与竞品「服务端六种+兜底 / 预检页七种」双面分工同构，文案词自定）──
export const ROLE_LABEL: Record<PartyRole, string> = {
  CLIENT: "委托方", OPPOSING_PARTY: "对方", THIRD_PARTY: "第三人",
  CO_LITIGANT: "共同诉讼人", AGENT: "代理人", WITNESS: "证人", OTHER: "当事人",
};
export const HIT_ROLE_LABEL: Record<PartyRole, string> = {
  CLIENT: "委托方", OPPOSING_PARTY: "对方当事人", THIRD_PARTY: "第三人",
  CO_LITIGANT: "共同诉讼人", AGENT: "代理人", WITNESS: "证人", OTHER: "其他",
};
export const SEVERITY_LABEL: Record<ConflictSeverity, string> = {
  BLOCKING: "重点规避", HIGH: "高风险", MEDIUM: "需核实", LOW: "一般提示",
};
export const SEVERITY_SHORT: Record<ConflictSeverity, string> = {
  BLOCKING: "阻塞", HIGH: "高", MEDIUM: "中", LOW: "低",
};
// 严重度卡片色键（UI 侧映射 Tailwind；值单源在此）
export const SEVERITY_TONE: Record<ConflictSeverity, string> = {
  BLOCKING: "red", HIGH: "orange", MEDIUM: "amber", LOW: "gray",
};

// 命中方式三分（E5 预检/弹窗面）：名称相同 / 名称相似 / 证件一致
export type MatchKind = "name_exact" | "name_similar" | "id_number";
export function matchKindOf(hit: { matchedField: string; matchLevel: string | null }): MatchKind {
  return hit.matchedField === "idNumber" ? "id_number"
    : hit.matchLevel === "EXACT" ? "name_exact" : "name_similar";
}
export const MATCH_KIND_LABEL: Record<MatchKind, string> = {
  name_exact: "名称相同", name_similar: "名称相似", id_number: "证件一致",
};

// ── 自写文案单源（自动结论/关键报错句——自动结论识别按常量全等比对，见 F9 等量注）──
export const AUTO_NOTE_FORMAL = "系统自动标记：登记记录未命中冲突，暂可承接。";
export const AUTO_NOTE_REVIEW = "系统复核检索未命中，仍需结合业务实际自行判断。";
export const AUTO_NOTE_PREFIX = "系统自动标记："; // F12 概览行自动标注按前缀识别

// ── 名称归一化（C6 保守变换：全角→半角、去空白、去括号段、迭代剥组织后缀、ASCII 小写；
//    不做繁简转换、不剥裸地域前缀、不剥分公司/分店——分支机构是独立主体）──
const ORG_SUFFIXES = ["股份有限公司", "有限责任公司", "有限公司", "合伙企业", "集团公司", "公司", "集团"]; // 长前短后
const BRACKET_PAIRS: Array<[string, string]> = [["（", "）"], ["(", ")"]];

export function fullToHalf(s: string): string {
  let out = "";
  for (const ch of s) {
    const code = ch.codePointAt(0) ?? 0;
    if (code === 0x3000) out += " ";
    else if (code >= 0xff01 && code <= 0xff5e) out += String.fromCodePoint(code - 0xfee0);
    else out += ch;
  }
  return out;
}

function stripBracketSegments(s: string): string {
  let out = s;
  for (const [open, close] of BRACKET_PAIRS) {
    // 逐对删除成对括号段（含内容）；未闭合的孤立括号不剥（保守）
    let prev: string;
    do {
      prev = out;
      const i = out.indexOf(open);
      if (i >= 0) {
        const j = out.indexOf(close, i + open.length);
        if (j >= 0) out = out.slice(0, i) + out.slice(j + close.length);
      }
    } while (out !== prev);
  }
  return out;
}

export function normalizeOrgName(s: string): string {
  let out = fullToHalf(String(s ?? "")).replace(/\s+/g, "");
  out = stripBracketSegments(out);
  // 迭代剥组织后缀（长前短后）；尾巴是分公司/分店时停手（独立主体）
  let changed = true;
  while (changed) {
    changed = false;
    for (const suffix of ORG_SUFFIXES) {
      if (out.length > suffix.length && out.endsWith(suffix)) {
        const head = out.slice(0, out.length - suffix.length);
        if (head.endsWith("分")) continue; // 分公司/分店不剥
        out = head;
        changed = true;
        break;
      }
    }
  }
  return out.toLowerCase();
}

// 去地域前缀核：33 项省/直辖市/自治区/特别行政区前缀（无台湾）；长前优先匹配
export const REGION_PREFIXES: readonly string[] = [
  "北京", "天津", "上海", "重庆",
  "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东",
  "河南", "湖北", "湖南", "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海",
  "广西", "内蒙古", "西藏", "宁夏", "新疆",
  "香港", "澳门",
];

function stripRegionPrefix(norm: string): string {
  for (const p of [...REGION_PREFIXES].sort((a, b) => b.length - a.length)) {
    if (norm.startsWith(p)) return norm.slice(p.length);
  }
  return norm;
}

// 探针集（C5）：原名 / 归一核 / 去地域核，各 ≥3 字（按码点计）才收，去重保序
export function buildNameProbes(rawName: string): string[] {
  const probes: string[] = [];
  const push = (s: string) => {
    const t = s.trim();
    if ([...t].length >= 3 && !probes.includes(t)) probes.push(t);
  };
  push(String(rawName ?? ""));
  const norm = normalizeOrgName(rawName);
  if (norm !== probes[0]) push(norm);
  const noRegion = stripRegionPrefix(norm);
  if (noRegion !== norm) push(noRegion);
  return probes;
}

// 证件号归一（B4）：trim + 大写（小写 x、小写统一社会信用代码归一）
export function normalizeIdNumber(s: string): string {
  return String(s ?? "").trim().toUpperCase();
}

// 证件变体集（C4）：原文（trim）与大写归一去重——命中=任一变体相等
export function idVariants(raw: string): string[] {
  const t = String(raw ?? "").trim();
  const u = normalizeIdNumber(t);
  return u && u !== t ? [t, u] : t ? [t] : [];
}

// ── 四级双向匹配分级（C5）：EXACT＞NORMALIZED_EQUAL＞CONTAINS（原文互含）＞NORMALIZED_CONTAINS＞null ──
export type NameMatchLevel = "EXACT" | "NORMALIZED_EQUAL" | "CONTAINS" | "NORMALIZED_CONTAINS";
export interface NameMatch { level: NameMatchLevel; ratio: number }

export function nameMatchLevel(query: string, stored: string): NameMatch | null {
  const q = String(query ?? "").trim();
  const s = String(stored ?? "").trim();
  if (!q || !s) return null;
  if (q === s) return { level: "EXACT", ratio: 1 };
  const nq = normalizeOrgName(q);
  const ns = normalizeOrgName(s);
  if (nq && nq === ns) return { level: "NORMALIZED_EQUAL", ratio: 1 };
  const short = [...q].length <= [...s].length ? q : s;
  const long = short === q ? s : q;
  if (long.includes(short)) {
    const ratio = [...long].length ? [...short].length / [...long].length : 1;
    return { level: "CONTAINS", ratio };
  }
  if (nq && ns && (ns.includes(nq) || nq.includes(ns))) {
    const nShort = nq.length <= ns.length ? nq : ns;
    const nLong = nShort === nq ? ns : nq;
    return { level: "NORMALIZED_CONTAINS", ratio: nLong.length ? nShort.length / nLong.length : 1 };
  }
  return null;
}

// ── 严重度（D1-D7）──
// 矩阵：拟委托×历史对手=HIGH；拟代理对手×历史委托=BLOCKING；对手×对手=LOW；委托×委托=LOW；
// 任一侧第三人=MEDIUM；其余组合=MEDIUM 兜底。
export function pickSeverity(queryRole: PartyRole, storedRole: PartyRole): ConflictSeverity {
  if (queryRole === "THIRD_PARTY" || storedRole === "THIRD_PARTY") return "MEDIUM";
  if (queryRole === "CLIENT" && storedRole === "OPPOSING_PARTY") return "HIGH";
  if (queryRole === "OPPOSING_PARTY" && storedRole === "CLIENT") return "BLOCKING";
  if (queryRole === "OPPOSING_PARTY" && storedRole === "OPPOSING_PARTY") return "LOW";
  if (queryRole === "CLIENT" && storedRole === "CLIENT") return "LOW";
  return "MEDIUM";
}
// 证件一致 → 升 1 级，BLOCKING 封顶（D5）
export function bumpForIdMatch(sev: ConflictSeverity): ConflictSeverity {
  return SEVERITIES[Math.min(SEVERITY_RANK[sev] + 1, SEVERITY_RANK.BLOCKING)] ?? sev;
}
// 归一化命中 → 降 1 级，LOW 地板（D6）
export function downgradeForNormalized(sev: ConflictSeverity): ConflictSeverity {
  return SEVERITIES[Math.max(SEVERITY_RANK[sev] - 1, SEVERITY_RANK.LOW)] ?? sev;
}

// 名称命中严重度：EXACT 走矩阵；NORMALIZED_EQUAL 矩阵降 1（地板 LOW）；原文互含/归一互含恒 LOW
//（D7：互含不按矩阵染色；归一化分级先于互含——nameMatchLevel 的级序已保证）
export function severityOfNameHit(level: NameMatchLevel, queryRole: PartyRole, storedRole: PartyRole): ConflictSeverity {
  if (level === "EXACT") return pickSeverity(queryRole, storedRole);
  if (level === "NORMALIZED_EQUAL") return downgradeForNormalized(pickSeverity(queryRole, storedRole));
  return "LOW";
}

// ── 命中草稿 ──
export interface HitDraft {
  hitType: ConflictHitType;
  targetType: "matter" | "intake";
  targetId: string;
  matchedName: string;
  matchedField: "name" | "idNumber";
  matchedValue: string;
  matchedRatio: number;
  matchLevel: NameMatchLevel | null;
  severity: ConflictSeverity;
  reason: string;
  storedRole: PartyRole;
  storedStanding: string | null;
}

// reason 句式（自写；语义结构对齐：命中方式 + 归一/相似标注 + 登记身份）
export function reasonOfHit(hit: Pick<HitDraft, "matchedField" | "matchLevel" | "matchedRatio" | "storedRole">): string {
  const roleText = `该记录登记身份：${ROLE_LABEL[hit.storedRole]}`;
  if (hit.matchedField === "idNumber") return `证件号与登记记录一致；${roleText}。`;
  switch (hit.matchLevel) {
    case "EXACT":
      return `名称完全一致；${roleText}。`;
    case "NORMALIZED_EQUAL":
      return `名称经规范化（全半角/括号/组织后缀）后一致，请人工核对是否同一主体；${roleText}。`;
    case "CONTAINS":
      return hit.matchedRatio < 1
        ? `名称部分相符（相似度 ${Math.round(hit.matchedRatio * 100)}%）；${roleText}。`
        : `名称部分相符；${roleText}。`;
    case "NORMALIZED_CONTAINS":
      return `名称规范化后部分相符，请人工核对；${roleText}。`;
    default:
      return `与登记记录相符；${roleText}。`;
  }
}

// 去重键（D8）=[targetId, matchedField, matchedValue, matchedName]：同键只留最高严重度
export function hitDedupeKey(h: Pick<HitDraft, "targetId" | "matchedField" | "matchedValue" | "matchedName">): string {
  return [h.targetId, h.matchedField, h.matchedValue, h.matchedName].join("\u0000");
}
export function dedupeHits(hits: HitDraft[]): HitDraft[] {
  const byKey = new Map<string, HitDraft>();
  for (const h of hits) {
    const key = hitDedupeKey(h);
    const prev = byKey.get(key);
    if (!prev || SEVERITY_RANK[h.severity] > SEVERITY_RANK[prev.severity]) byKey.set(key, h);
  }
  return [...byKey.values()];
}
// 输出按严重度降序（稳定：同严重度保持插入序）
export function sortHitsDesc(hits: HitDraft[]): HitDraft[] {
  return [...hits].sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity]);
}

// ── 检索条件构造（§3.2 buildConflictQueries）：委托方缺 Party 行则补；
//    [role,name,idNumber] 去重；带证件的同名同角色查询消并。──
export interface ConflictQuery { role: PartyRole; name: string; idNumber: string }
export interface PartyLike { role: PartyRole; name: string; idNumber?: string | null }
export interface ClientLike { name: string; idNumber?: string | null }

export function buildConflictQueries(client: ClientLike | null, parties: PartyLike[]): ConflictQuery[] {
  const queries: Array<{ role: PartyRole; name: string; idNumber: string }> = [];
  // 委托方缺 Party 行则补（用客户档案补一条委托方查询）
  const hasClientParty = client
    ? parties.some((p) => p.role === "CLIENT" && p.name.trim() === client.name.trim())
    : false;
  if (client && !hasClientParty) {
    queries.push({ role: "CLIENT", name: client.name.trim(), idNumber: normalizeIdNumber(client.idNumber ?? "") });
  }
  for (const p of parties) {
    const name = String(p.name ?? "").trim();
    if (!name) continue;
    queries.push({ role: p.role, name, idNumber: normalizeIdNumber(p.idNumber ?? "") });
  }
  // 同名同角色消并：组内任一带证件则以带证件者为准
  const byRoleName = new Map<string, ConflictQuery>();
  const order: string[] = [];
  for (const q of queries) {
    const key = `${q.role}\u0000${q.name}`;
    const prev = byRoleName.get(key);
    if (!prev) { byRoleName.set(key, q); order.push(key); }
    else if (!prev.idNumber && q.idNumber) byRoleName.set(key, { ...q });
  }
  return order.map((k) => byRoleName.get(k) as ConflictQuery);
}

// 预检入参行规范化（B2/B3/B4）：角色可省默认对方；名称≤120、证件≤50；空行剔除；
// 名称与证件至少一项（逐行判定，全空行直接过滤，剩余为空=拦截）。
export interface PrecheckRowInput { role?: string; name?: string; idNumber?: string }
export interface NormalizeQueriesResult { queries: ConflictQuery[]; error: string | null }

export function normalizePrecheckQueries(rows: unknown): NormalizeQueriesResult {
  if (!Array.isArray(rows)) return { queries: [], error: "检索主体须为数组" };
  const queries: ConflictQuery[] = [];
  for (const row of rows as PrecheckRowInput[]) {
    const name = String(row?.name ?? "").trim();
    const idNumber = normalizeIdNumber(String(row?.idNumber ?? ""));
    if (!name && !idNumber) continue; // 空行自动过滤（B7）
    if ([...name].length > 120) return { queries: [], error: "名称不能超过 120 字" };
    if (idNumber.length > 50) return { queries: [], error: "证件号不能超过 50 字符" };
    const role = (String(row?.role ?? "").trim() || "OPPOSING_PARTY") as PartyRole; // B3 预检缺省=对方
    if (!ROLES.includes(role)) return { queries: [], error: `当事人角色不在值域内（实收 ${JSON.stringify(row?.role ?? null)}）` };
    queries.push({ role, name, idNumber });
  }
  if (!queries.length) return { queries: [], error: "请至少填写一个主体的名称或证件号" };
  return { queries, error: null };
}

// 正式检索入参角色必填（B3：不默认当对方）
export function normalizeFormalQueries(rows: unknown): NormalizeQueriesResult {
  if (!Array.isArray(rows)) return { queries: [], error: "检索主体须为数组" };
  const queries: ConflictQuery[] = [];
  for (const row of rows as PrecheckRowInput[]) {
    const name = String(row?.name ?? "").trim();
    const idNumber = normalizeIdNumber(String(row?.idNumber ?? ""));
    if (!name && !idNumber) continue;
    const role = String(row?.role ?? "").trim() as PartyRole;
    if (!ROLES.includes(role)) return { queries: [], error: "正式检索必须包含当事人身份（缺 role）" };
    queries.push({ role, name, idNumber });
  }
  if (!queries.length) return { queries: [], error: "检索主体为空" };
  return { queries, error: null };
}

// ── 指纹（B8/F6）：载荷=固定键序的 JSON 串；哈希在桥侧做（模型层零 node 依赖，UI 可安全引入）。
//    正式（收案）侧字段集={queries,category,serviceScope,firstProcedureType,ourStanding,businessType}；
//    案件复核侧={queries,category,serviceScope,procedures,scopes}。
//    过渡态：MatterLite 无 category/serviceScope 等列，案件指纹取 {queries,cause,courtType}
//    （案由≈类别、法院类型≈程序面——主体集变化必经 queries，改案由/法院类型同样触发失效），
//    收案实体接入后换正式字段集。键序由 fingerprintPayload 固定（ASCII 排序），跨重启稳定。──
export type FingerprintFields = Record<string, unknown>;
export function fingerprintPayload(fields: FingerprintFields): string {
  const keys = Object.keys(fields).sort();
  const parts = keys.map((k) => `${JSON.stringify(k)}:${JSON.stringify(fields[k] ?? null)}`);
  return `{${parts.join(",")}}`;
}
export const FORMAL_FINGERPRINT_FIELDS = ["queries", "category", "serviceScope", "firstProcedureType", "ourStanding", "businessType"] as const;
export const MATTER_REVIEW_FINGERPRINT_FIELDS = ["queries", "category", "serviceScope", "procedures", "scopes"] as const;

// 当场重跑命中集比对（G2/H4）：键集合差异——返回新增键（旧集中没有的）
export function newHitKeys(previous: Array<Pick<HitDraft, "targetId" | "matchedField" | "matchedValue" | "matchedName">>,
  current: Array<Pick<HitDraft, "targetId" | "matchedField" | "matchedValue" | "matchedName">>): string[] {
  const prevKeys = new Set(previous.map(hitDedupeKey));
  return current.map(hitDedupeKey).filter((k) => !prevKeys.has(k));
}

// 命中是否含高风险/阻塞（F5：有 HIGH/BLOCKING 时 DIFFERENT 必填备注）
export function hasHighOrBlocking(hits: Array<Pick<HitDraft, "severity">>): boolean {
  return hits.some((h) => SEVERITY_RANK[h.severity] >= SEVERITY_RANK.HIGH);
}

// ── H5 写路径硬门禁判定核（对拍 32；三段闸次序=无记录∨指纹漂移＞最新结论未过＞当场重跑新增命中）──
// 桥侧 assertReviewCurrent 按本判定核抛错（报错文案在桥面自写），写路径模块接入时同位调用。
export type ReviewGateOutcome = "ok" | "STALE" | "NOT_PASSED" | "NEW_HITS";
export function reviewGateOutcome(input: {
  hasRecord: boolean;          // 案件是否有复核检索记录
  fingerprintCurrent: boolean; // 最新记录指纹与当前主体状态是否一致
  conclusion: string | null;   // 最新记录结论（无记录为 null）
  newHitCount: number;         // 当场重跑新增命中数
}): ReviewGateOutcome {
  if (!input.hasRecord || !input.fingerprintCurrent) return "STALE";
  if (input.conclusion !== "DIFFERENT") return "NOT_PASSED";
  if (input.newHitCount > 0) return "NEW_HITS";
  return "ok";
}

// ══ 【对拍 r9 补齐件】实体无关核（B1/E5/F10/G2/G4/F7）：判定核先行落位+合成覆盖，
// 收案/审批实体（#2）接入时同位接线不重写（沿 reviewGateOutcome 先例）。报错文案一律接线侧自写。══

// B1 审批侧第三套角色标签（conflictPartyRoleLabel 等量位）：七种；与预检页 HIT_ROLE_LABEL
//（OPPOSING_PARTY=对方当事人）、服务端 reason 面 ROLE_LABEL（OTHER 兜底=当事人）分面各持一套——
// 审批侧差异=OPPOSING_PARTY 显「对方」、OTHER 显「其他」。
export const APPROVAL_ROLE_LABEL: Record<PartyRole, string> = {
  CLIENT: "委托方", OPPOSING_PARTY: "对方", THIRD_PARTY: "第三人",
  CO_LITIGANT: "共同诉讼人", AGENT: "代理人", WITNESS: "证人", OTHER: "其他",
};

// E5 审批侧命中方式四分（预检/弹窗面 matchKindOf 三分之外的第二口径）：
// 证件列→证件一致；名称列缺级或字段异常→其他历史匹配；EXACT 且比率为 1→名称相同；其余名称命中→名称相似。
export type ApprovalMatchKind = "name_exact" | "name_similar" | "id_number" | "other";
export function matchKindOfApproval(hit: {
  matchedField: string; matchLevel: string | null;
  matchedName: string; matchedValue: string; matchedRatio: number | null;
}): ApprovalMatchKind {
  if (hit.matchedField === "idNumber") return "id_number";
  if (hit.matchedField !== "name" || !String(hit.matchedName ?? "").trim() || !String(hit.matchedValue ?? "").trim()) return "other";
  return hit.matchLevel === "EXACT" && (hit.matchedRatio === null || hit.matchedRatio === 1) ? "name_exact" : "name_similar";
}
export const APPROVAL_MATCH_KIND_LABEL: Record<ApprovalMatchKind, string> = {
  name_exact: "名称相同", name_similar: "名称相似", id_number: "证件一致", other: "其他历史匹配",
};

// F10 覆盖比对核：当前收案权威重派条件 vs 存档检索条件，role+trim(name)+trim(idNumber) 键逐条比对。
// ok=当前条件全部在档；incomplete=存档档无可比对条件（早期记录/坏载荷→「检索资料不完整」支）；
// missing=已变更缺失条件清单（自写格式：角色·名称（证件尾号 xxxx））。
export interface CoverageOutcome { ok: boolean; incomplete: boolean; missing: string[] }
export function conflictQueryCoverage(
  currentQueries: ReadonlyArray<ConflictQuery>,
  storedQueries: ReadonlyArray<{ role: string; name: string; idNumber?: string | null }>,
): CoverageOutcome {
  const key = (q: { role: string; name: string; idNumber?: string | null }) =>
    JSON.stringify([q.role, String(q.name ?? "").trim(), String(q.idNumber ?? "").trim()]);
  const stored = new Set(storedQueries.map(key));
  const missing = currentQueries
    .filter((q) => !stored.has(key(q)))
    .map((q) => `${ROLE_LABEL[q.role] ?? q.role}·${String(q.name).trim()}${q.idNumber ? `（证件尾号 ${q.idNumber.slice(-4)}）` : ""}`);
  return {
    ok: currentQueries.length > 0 && missing.length === 0,
    incomplete: currentQueries.length > 0 && storedQueries.length === 0,
    missing,
  };
}

// G2 送审闸判定核（五查次序）：①无检索记录→②指纹失效→③结论未承接（requireConclusion 时）→
// ④有命中无备注（requireConclusion 时）→⑤当场重跑新增/变化命中。送审闸 requireConclusion=false、
// 转案事务闸传 true（同竞品 assertFreshIntakeCheck 形参）；报错文案接线侧自写。
export type IntakeSubmitGateOutcome =
  | "ok" | "NO_CHECK" | "STALE" | "NOT_DIFFERENT" | "NOTE_REQUIRED" | "NEW_HITS";
export function intakeSubmitGateOutcome(input: {
  hasCheck: boolean;
  fingerprintCurrent: boolean;
  requireConclusion: boolean;
  conclusion: string | null;
  hasHits: boolean;
  noteNonEmpty: boolean;
  changedHitCount: number;
}): IntakeSubmitGateOutcome {
  if (!input.hasCheck) return "NO_CHECK";
  if (!input.fingerprintCurrent) return "STALE";
  if (input.requireConclusion && input.conclusion !== "DIFFERENT") return "NOT_DIFFERENT";
  if (input.requireConclusion && input.hasHits && !input.noteNonEmpty) return "NOTE_REQUIRED";
  if (input.changedHitCount > 0) return "NEW_HITS";
  return "ok";
}

// G2 当场重跑严格比对（键+严重度+reason 三元签名）：返回当前命中中旧集没有对应签名的数量。
// 案件复核 H4 的键级比对走 newHitKeys（已验收面不动）；送审/转案闸用本严格口径。
export type RerunHitSig = Pick<HitDraft, "targetId" | "matchedField" | "matchedValue" | "matchedName" | "severity" | "reason">;
export function rerunChangedCount(
  previous: ReadonlyArray<RerunHitSig>,
  current: ReadonlyArray<RerunHitSig>,
): number {
  const sig = (h: RerunHitSig) => `${hitDedupeKey(h)}\u0000${h.severity}\u0000${h.reason ?? ""}`;
  const prior = new Set(previous.map(sig));
  return current.filter((h) => !prior.has(sig(h))).length;
}

// F7 送审冻结（conclude 侧闸）：收案处于待审批态时不可改结论，须先撤回再改。
export function intakeFrozenForConclusion(intakeState: string | null): boolean {
  return intakeState === "PENDING_CONFIRMATION";
}

// G4 转案内容闸判定核（八条次序）：①无当事人→②无检索→③条件不齐（F10 覆盖比对不过）→
// ④结论 PENDING→⑤NEED_INFO→⑥SAME_SUBJECT→⑦结论异常兜底（非四态）→⑧高风险/阻塞命中无备注。
export type IntakeConvertGateOutcome =
  | "ok" | "NO_PARTIES" | "NO_CHECK" | "COVERAGE_MISSING" | "PENDING" | "NEED_INFO" | "SAME_SUBJECT" | "ABNORMAL" | "NOTE_REQUIRED";
export function intakeConvertGateOutcome(input: {
  queryCount: number;           // 当前权威重派条件数（0=未登记当事人）
  hasCheck: boolean;            // 是否存在收案正式检索记录
  coverage: CoverageOutcome;    // F10 覆盖比对产物
  conclusion: string | null;    // 最新检索结论
  hasHighOrBlocking: boolean;
  noteNonEmpty: boolean;
}): IntakeConvertGateOutcome {
  if (input.queryCount === 0) return "NO_PARTIES";
  if (!input.hasCheck) return "NO_CHECK";
  if (!input.coverage.ok) return "COVERAGE_MISSING";
  if (input.conclusion === "PENDING") return "PENDING";
  if (input.conclusion === "NEED_INFO") return "NEED_INFO";
  if (input.conclusion === "SAME_SUBJECT") return "SAME_SUBJECT";
  if (input.conclusion !== "DIFFERENT") return "ABNORMAL";
  if (input.hasHighOrBlocking && !input.noteNonEmpty) return "NOTE_REQUIRED";
  return "ok";
}
