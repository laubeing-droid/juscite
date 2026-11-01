// 大事记机器读底稿（契约一：模型唯一自由产出=封闭 schema 的语义 JSON）。
// schema 封闭：additionalProperties=false 语义=未知顶层/行级字段一律拒绝；
// 事实编号顺序分配、一旦分配不再变动、删行不回收；
// 争点字段底稿生成时恒空、由律师在 Excel 母表回填；
// 模型不填判断字段（证据状态由有无证据编号机械决定，见 guards E 组）。
// 底稿=既有事件账本（case_events）的投影视视图：确认事件按本 schema 投影而来，本模块只认 schema 不认库。

import { DATE_PRECISIONS, type DatePrecision } from "./tables.ts";

export const FACTBASE_SCHEMA = "juscite.vizb.chronicle.factbase@1" as const;

/** 材料册（卷）：同一证据编号不得跨册；册内文档为照录原文的源。 */
export interface SourceDoc {
  docId: string;      // 如 "卷一-借款合同"
  label: string;      // 展示名
  volume: string;     // 所属册（卷一/卷二…）
  /** 原文全量（底稿自包含：照录子序列判定就地可跑，不需要回读文件）。 */
  text: string;
}

/** 事实行：一法律动作一条事实；字段全枚举，封闭。 */
export interface FactRow {
  factNo: number;            // 顺序分配，只增不回收
  dateStr: string;           // 写法与精度档正则相符（tables.ts）
  datePrecision: DatePrecision;
  verb: string;              // 封闭动词表
  title: string;             // ≤15 字；不含定性词；书名号配对
  content: string;           // 主要内容：源文本去标点子序列，全量不省略（省略只归律师，且在母表内做）
  sourceDoc: string;         // docId，须存在
  locator: string;           // 页/段定位，形如 p3¶2 或 p3
  evidenceNo: string | null; // null=无书证
  volume: string;            // 证据所在册
  subjects: string[];        // 主体照录，不归并
  dispute: null;             // 恒空：争点由律师母表回填，模型禁填
  arithmeticNote: string | null; // 材料矛盾报告：照原样列出，不修正（算术自校是证据不是判据）
  /** 模型禁填字段（填即拒）：evidenceStatus 由守卫机械决定。 */
  evidenceStatus?: undefined;
}

export interface FactBase {
  schema: typeof FACTBASE_SCHEMA;
  caseTitle: string;
  docs: SourceDoc[];
  facts: FactRow[];
  /** 不确定清单：无书证事实自动进入（E 组联动）。 */
  uncertainty: string[];
}

type Reject = { path: string; msg: string };

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** 封闭校验（未知字段拒绝/类型全查/枚举封闭）。返回违例清单；空=通过。 */
export function validateFactBase(input: unknown): Reject[] {
  const out: Reject[] = [];
  if (!isObj(input)) return [{ path: "$", msg: "底稿必须是对象" }];
  if (input.schema !== FACTBASE_SCHEMA) out.push({ path: "$.schema", msg: `schema 须为 ${FACTBASE_SCHEMA}` });
  const TOP = new Set(["schema", "caseTitle", "docs", "facts", "uncertainty"]);
  for (const k of Object.keys(input)) if (!TOP.has(k)) out.push({ path: `$.${k}`, msg: "未知顶层字段（schema 封闭）" });
  if (typeof input.caseTitle !== "string" || !input.caseTitle.trim()) out.push({ path: "$.caseTitle", msg: "案件名不能为空" });
  if (!Array.isArray(input.docs)) { out.push({ path: "$.docs", msg: "docs 须为数组" }); }
  else {
    const DOC = new Set(["docId", "label", "volume", "text"]);
    const seen = new Set<string>();
    input.docs.forEach((d, i) => {
      if (!isObj(d)) { out.push({ path: `$.docs[${i}]`, msg: "文档须为对象" }); return; }
      for (const k of Object.keys(d)) if (!DOC.has(k)) out.push({ path: `$.docs[${i}].${k}`, msg: "未知文档字段" });
      if (typeof d.docId !== "string" || !d.docId) out.push({ path: `$.docs[${i}].docId`, msg: "docId 不能为空" });
      else if (seen.has(d.docId)) out.push({ path: `$.docs[${i}].docId`, msg: "docId 重复" });
      else seen.add(d.docId);
      if (typeof d.label !== "string" || !d.label) out.push({ path: `$.docs[${i}].label`, msg: "label 不能为空" });
      if (typeof d.volume !== "string" || !d.volume) out.push({ path: `$.docs[${i}].volume`, msg: "volume 不能为空" });
      if (typeof d.text !== "string") out.push({ path: `$.docs[${i}].text`, msg: "text 须为字符串" });
    });
  }
  if (!Array.isArray(input.facts)) { out.push({ path: "$.facts", msg: "facts 须为数组" }); }
  else {
    const FACT = new Set(["factNo", "dateStr", "datePrecision", "verb", "title", "content",
      "sourceDoc", "locator", "evidenceNo", "volume", "subjects", "dispute", "arithmeticNote", "evidenceStatus"]);
    let prevNo = 0;
    input.facts.forEach((f, i) => {
      const p = `$.facts[${i}]`;
      if (!isObj(f)) { out.push({ path: p, msg: "事实行须为对象" }); return; }
      for (const k of Object.keys(f)) if (!FACT.has(k)) out.push({ path: `${p}.${k}`, msg: "未知事实字段（schema 封闭）" });
      if (!Number.isInteger(f.factNo) || (f.factNo as number) <= prevNo) out.push({ path: `${p}.factNo`, msg: `事实编号须顺序分配且不回收（期望 >${prevNo}）` });
      else prevNo = f.factNo as number;
      if (typeof f.dateStr !== "string") out.push({ path: `${p}.dateStr`, msg: "dateStr 须为字符串" });
      if (!DATE_PRECISIONS.includes(f.datePrecision as DatePrecision)) out.push({ path: `${p}.datePrecision`, msg: "datePrecision 不在四档封闭枚举内" });
      if (typeof f.verb !== "string" || !f.verb) out.push({ path: `${p}.verb`, msg: "verb 不能为空" });
      if (typeof f.title !== "string" || !f.title) out.push({ path: `${p}.title`, msg: "title 不能为空" });
      if (typeof f.content !== "string" || !f.content) out.push({ path: `${p}.content`, msg: "content 不能为空" });
      if (typeof f.sourceDoc !== "string") out.push({ path: `${p}.sourceDoc`, msg: "sourceDoc 须为字符串" });
      if (typeof f.locator !== "string") out.push({ path: `${p}.locator`, msg: "locator 须为字符串" });
      if (f.evidenceNo !== null && typeof f.evidenceNo !== "string") out.push({ path: `${p}.evidenceNo`, msg: "evidenceNo 须为字符串或 null" });
      if (typeof f.volume !== "string") out.push({ path: `${p}.volume`, msg: "volume 须为字符串" });
      if (!Array.isArray(f.subjects) || f.subjects.some((s) => typeof s !== "string" || !s)) out.push({ path: `${p}.subjects`, msg: "subjects 须为非空字符串数组" });
      if (f.dispute !== null && f.dispute !== undefined) out.push({ path: `${p}.dispute`, msg: "争点字段模型禁填（恒空，律师母表回填）" });
      if (f.arithmeticNote !== null && typeof f.arithmeticNote !== "string") out.push({ path: `${p}.arithmeticNote`, msg: "arithmeticNote 须为字符串或 null" });
      if (f.evidenceStatus !== undefined) out.push({ path: `${p}.evidenceStatus`, msg: "证据状态由守卫机械决定，模型禁填" });
    });
  }
  if (!Array.isArray(input.uncertainty) || input.uncertainty.some((s) => typeof s !== "string")) {
    out.push({ path: "$.uncertainty", msg: "uncertainty 须为字符串数组" });
  }
  return out;
}

/** 证据状态机械决定（E 组）：有证据编号=有书证；无=仅当事人陈述。 */
export function deriveEvidenceStatus(f: Pick<FactRow, "evidenceNo">): "有书证" | "仅当事人陈述" {
  return f.evidenceNo != null && f.evidenceNo !== "" ? "有书证" : "仅当事人陈述";
}
