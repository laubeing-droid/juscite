// 庭审对抗图语义 JSON（契约一：模型唯一自由产出=封闭 schema；我方字段名自定，不照抄源仓示例）。
// 判断带三标（法律置信/证据置信/来源；立场方向由三栏结构承担）；
// 三处结论留空等律师填：证明前景/决定性排序/另定性风险（模型填即拒）；
// 四段攻防正文=文书原文照录（子序列核验），每段必须标实际来源文件。

import { stripPunct, isSubsequence } from "../chronicle/textcheck.ts";
import {
  ABSENCE_REASONS, CLAIM_TYPES, CONFIDENCE_LEVELS, DEFENSE_CATEGORIES, MATURITY_LEVELS,
  SEGMENT_SOURCE_KINDS, stripUnverifiedMarker, type AbsenceReason, type ClaimType,
  type Confidence, type DefenseCategory, type MaturityLevel, type SegmentSourceKind,
} from "./tables.ts";

export const CONFRONTATION_SCHEMA = "juscite.vizb.confrontation@1" as const;

/** 照录段：正文+实际来源（文件名）+文书类型；正文须为该来源文本的去标点子序列。 */
export interface Segment {
  text: string;
  src: string;                 // 实际来源文件名（须在 sources 内；不得套默认文书名）
  srcKind: SegmentSourceKind;
}
/** 空段：留位不立框；归因严格二分（无书面记载≠未获取）。 */
export interface AbsentSegment {
  absent: true;
  reason: AbsenceReason;
}

export type Slot = Segment | AbsentSegment | null;

/** 金额明细项（整型分；主张额构成明细，代码做算术——J 组）。 */
export interface AmountItem { label: string; cents: number; basis: string }
/** 显式调整项（差额必须有依据；无依据的差额即错）。 */
export interface AmountAdjustment { label: string; cents: number; basis: string }

export interface Claim {
  no: string;                  // 编号（图与表一一对应）
  type: ClaimType;
  summary: Segment;            // 诉请要旨（照录）
  claimedCents: number | null; // 主张总额（整型分）；null=取不出确定数额（不核算，如实标）
  items: AmountItem[];         // 构成明细（代码对平）
  adjustments: AmountAdjustment[];
  /** 按类型的必填字段（CLAIM_TYPES[type].required 缺一即错）。 */
  required: Record<string, string>;
}

export interface Defense {
  no: string;
  category: DefenseCategory | string; // 允许带【待核验】标记，剥后必须命中封闭表
  text: Segment;
  /** 三问路径（K 组：逐问非空）。 */
  threeQuestions: [string, string, string];
  /** 人标举证责任（与归类机械决定不一致即错）。 */
  burden?: "claimant" | "defendant";
}

export interface Element {
  no: string;                  // 板块-序（图表对应键）
  issue: string;               // 要件/争点
  claim: Segment;              // 主张（左·下）
  counter: Slot;               // 反制（左·上；null=不设位）
  response: Slot;              // 回应（右·下）
  second: Slot;                // 再回应（右·上）
  burden: "claimant" | "defendant";
  /** 判断三标（可推=要件拆解等须带三标）。 */
  lawConfidence: Confidence;
  evidenceConfidence: Confidence;
  source: string;
  /** 决定性三判据输入（规则算不由人标）：有争议×客观证明责任在请求方×证据未达证明标准。 */
  disputed: boolean;
  evidenceStandardMet: boolean;
  /** 从属性：随主债同进退的从属要件不算决定性；另有独立抗辩指向时须单列=true。 */
  subordinateTo?: string;
  independentlyTargeted?: boolean;
  /** 三处结论留空（模型填即拒，律师回填）： */
  prospect?: undefined;
  decisiveRanking?: undefined;
  recharacterizationRisk?: undefined;
}

export interface ConfrontationSemantic {
  schema: typeof CONFRONTATION_SCHEMA;
  caseTitle: string;
  /** 不对法院出示：内部推演件（产品文案随交付面携带此限制）。 */
  internalOnly: true;
  maturity: MaturityLevel;
  /** 程序站三项分列字段审查（数关键词会漏）：管辖/主体/重复起诉。 */
  procedure: { jurisdiction: string; standing: string; repeatedSuit: string };
  claims: Claim[];
  defenses: Defense[];
  elements: Element[];
  /** 待补清单（材料薄只降精确度不降结构；证据置信低须列明待补）。 */
  toComplete: string[];
  /** 照录原文源文件（正文子序列判定的源）。 */
  sources: Array<{ name: string; text: string }>;
}

type Reject = { path: string; msg: string };
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

export function isAbsentSegment(v: unknown): v is AbsentSegment {
  return isObj(v) && v.absent === true;
}
export function isPresentSegment(v: unknown): v is Segment {
  return isObj(v) && typeof v.text === "string" && typeof v.src === "string";
}

/** 封闭校验（未知字段拒绝/枚举封闭/结构完备）。 */
export function validateSemantic(input: unknown): Reject[] {
  const out: Reject[] = [];
  if (!isObj(input)) return [{ path: "$", msg: "语义 JSON 须为对象" }];
  if (input.schema !== CONFRONTATION_SCHEMA) out.push({ path: "$.schema", msg: `schema 须为 ${CONFRONTATION_SCHEMA}` });
  const TOP = new Set(["schema", "caseTitle", "internalOnly", "maturity", "procedure", "claims", "defenses", "elements", "toComplete", "sources"]);
  for (const k of Object.keys(input)) if (!TOP.has(k)) out.push({ path: `$.${k}`, msg: "未知顶层字段（schema 封闭）" });
  if (typeof input.caseTitle !== "string" || !input.caseTitle.trim()) out.push({ path: "$.caseTitle", msg: "案件名不能为空" });
  if (input.internalOnly !== true) out.push({ path: "$.internalOnly", msg: "对抗图为内部推演件，internalOnly 必须为 true（不对法院出示）" });
  if (!MATURITY_LEVELS.includes(input.maturity as MaturityLevel)) out.push({ path: "$.maturity", msg: "成熟度须在 L0–L3 封闭枚举内" });
  const proc = input.procedure;
  if (!isObj(proc)) out.push({ path: "$.procedure", msg: "procedure 须为对象" });
  else {
    const P = new Set(["jurisdiction", "standing", "repeatedSuit"]);
    for (const k of Object.keys(proc)) if (!P.has(k)) out.push({ path: `$.procedure.${k}`, msg: "未知字段" });
    for (const k of P) if (typeof proc[k] !== "string" || !(proc[k] as string).trim()) out.push({ path: `$.procedure.${k}`, msg: "程序站分列字段不能为空（分列审查，不数关键词）" });
  }
  const checkSlot = (v: unknown, path: string) => {
    if (v == null) return;
    if (isAbsentSegment(v)) {
      if (!ABSENCE_REASONS.includes(v.reason as AbsenceReason)) out.push({ path: `${path}.reason`, msg: `空段归因须二分（${ABSENCE_REASONS.join("/")}）` });
      return;
    }
    if (isPresentSegment(v)) {
      if (!SEGMENT_SOURCE_KINDS.includes(v.srcKind as SegmentSourceKind)) out.push({ path: `${path}.srcKind`, msg: "来源类型不在封闭表" });
      return;
    }
    out.push({ path, msg: "段须为 {text,src,srcKind} 或 {absent,reason} 或 null" });
  };
  if (!Array.isArray(input.claims)) out.push({ path: "$.claims", msg: "claims 须为数组" });
  else input.claims.forEach((c, i) => {
    const p = `$.claims[${i}]`;
    if (!isObj(c)) { out.push({ path: p, msg: "诉请须为对象" }); return; }
    const C = new Set(["no", "type", "summary", "claimedCents", "items", "adjustments", "required"]);
    for (const k of Object.keys(c)) if (!C.has(k)) out.push({ path: `${p}.${k}`, msg: "未知字段" });
    if (!CLAIM_TYPES[c.type as ClaimType]) out.push({ path: `${p}.type`, msg: `诉请类型不在封闭表（表外拒绝；律师确认后补表）` });
    checkSlot(c.summary, `${p}.summary`);
    if (isPresentSegment(c.summary) && c.summary.absent) out.push({ path: `${p}.summary`, msg: "诉请要旨不可为空段" });
    if (c.claimedCents !== null && (!Number.isInteger(c.claimedCents) || (c.claimedCents as number) < 0)) out.push({ path: `${p}.claimedCents`, msg: "主张额须为非负整型分或 null" });
    for (const arr of ["items", "adjustments"] as const) {
      if (!Array.isArray(c[arr])) { out.push({ path: `${p}.${arr}`, msg: `${arr} 须为数组` }); continue; }
      c[arr].forEach((it, j) => {
        if (!isObj(it) || typeof it.label !== "string" || !Number.isInteger(it.cents) || typeof it.basis !== "string" || !it.basis) {
          out.push({ path: `${p}.${arr}[${j}]`, msg: "金额项须 {label,cents,basis}（整型分＋注明依据）" });
        }
      });
    }
    if (!isObj(c.required)) out.push({ path: `${p}.required`, msg: "required 须为对象" });
  });
  if (!Array.isArray(input.defenses)) out.push({ path: "$.defenses", msg: "defenses 须为数组" });
  else input.defenses.forEach((d, i) => {
    const p = `$.defenses[${i}]`;
    if (!isObj(d)) { out.push({ path: p, msg: "抗辩须为对象" }); return; }
    const D = new Set(["no", "category", "text", "threeQuestions", "burden"]);
    for (const k of Object.keys(d)) if (!D.has(k)) out.push({ path: `${p}.${k}`, msg: "未知字段" });
    if (typeof d.category !== "string" || !DEFENSE_CATEGORIES.includes(stripUnverifiedMarker(d.category).trim() as DefenseCategory)) {
      out.push({ path: `${p}.category`, msg: `抗辩归类不在四分法封闭表（${DEFENSE_CATEGORIES.join("/")}；【待核验】标记不豁免）` });
    }
    checkSlot(d.text, `${p}.text`);
    if (!Array.isArray(d.threeQuestions) || d.threeQuestions.length !== 3 || d.threeQuestions.some((q) => typeof q !== "string" || !q.trim())) {
      out.push({ path: `${p}.threeQuestions`, msg: "三问路径缺一即错（逐问非空）" });
    }
  });
  if (!Array.isArray(input.elements)) out.push({ path: "$.elements", msg: "elements 须为数组" });
  else input.elements.forEach((e, i) => {
    const p = `$.elements[${i}]`;
    if (!isObj(e)) { out.push({ path: p, msg: "要件行须为对象" }); return; }
    const E = new Set(["no", "issue", "claim", "counter", "response", "second", "burden",
      "lawConfidence", "evidenceConfidence", "source", "disputed", "evidenceStandardMet",
      "subordinateTo", "independentlyTargeted", "prospect", "decisiveRanking", "recharacterizationRisk"]);
    for (const k of Object.keys(e)) if (!E.has(k)) out.push({ path: `${p}.${k}`, msg: "未知字段" });
    for (const k of ["prospect", "decisiveRanking", "recharacterizationRisk"] as const) {
      if (e[k] !== undefined) out.push({ path: `${p}.${k}`, msg: "证明前景/决定性排序/另定性风险由律师回填，模型填即拒" });
    }
    if (!CONFIDENCE_LEVELS.includes(e.lawConfidence as Confidence)) out.push({ path: `${p}.lawConfidence`, msg: "法律置信不在三档封闭枚举" });
    if (!CONFIDENCE_LEVELS.includes(e.evidenceConfidence as Confidence)) out.push({ path: `${p}.evidenceConfidence`, msg: "证据置信不在三档封闭枚举" });
    if (typeof e.source !== "string" || !e.source.trim()) out.push({ path: `${p}.source`, msg: "判断须带来源标（三标之一）" });
    if (typeof e.disputed !== "boolean" || typeof e.evidenceStandardMet !== "boolean") out.push({ path: `${p}.disputed`, msg: "决定性三判据输入须为布尔" });
    checkSlot(e.claim, `${p}.claim`);
    checkSlot(e.counter, `${p}.counter`);
    checkSlot(e.response, `${p}.response`);
    checkSlot(e.second, `${p}.second`);
  });
  if (!Array.isArray(input.toComplete) || input.toComplete.some((s) => typeof s !== "string")) out.push({ path: "$.toComplete", msg: "toComplete 须为字符串数组" });
  if (!Array.isArray(input.sources)) out.push({ path: "$.sources", msg: "sources 须为数组" });
  else input.sources.forEach((s, i) => {
    if (!isObj(s) || typeof s.name !== "string" || typeof s.text !== "string") out.push({ path: `$.sources[${i}]`, msg: "来源须 {name,text}" });
  });
  return out;
}

/** 照录判定（契约三）：四段攻防正文须为其标名来源文本的去标点子序列；来源必须实际存在。 */
export function segmentVerbatimViolations(sem: ConfrontationSemantic): Reject[] {
  const out: Reject[] = [];
  const srcMap = new Map(sem.sources.map((s) => [s.name, stripPunct(s.text)]));
  const check = (slot: unknown, path: string, fallbackSrc?: string) => {
    if (!isPresentSegment(slot)) return;
    const srcName = fallbackSrc ?? slot.src;
    const hay = srcMap.get(srcName);
    if (hay === undefined) { out.push({ path: `${path}.src`, msg: `来源「${srcName}」不存在——每段必须标实际来源，不得套用默认文书名` }); return; }
    if (!isSubsequence(stripPunct(slot.text), hay)) out.push({ path: `${path}.text`, msg: `${path} 正文非来源「${srcName}」文本子序列（四段攻防照录，模型只摆位置不生成主张）` });
  };
  for (const c of sem.claims) check(c.summary, `claim ${c.no}`);
  for (const d of sem.defenses) check(d.text, `defense ${d.no}`);
  for (const e of sem.elements) {
    check(e.claim, `element ${e.no} claim`);
    check(e.counter, `element ${e.no} counter`);
    check(e.response, `element ${e.no} response`);
    check(e.second, `element ${e.no} second`);
  }
  return out;
}
