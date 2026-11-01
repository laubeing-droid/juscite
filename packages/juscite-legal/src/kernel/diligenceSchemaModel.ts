// 【功能 #32 整理与尽调】台账字段模板内核·三态一源（RE-32 §3 + 2026-10-31 增补节「字段 schema 三态一源」）。
// 机制等量转写自 contextgem JsonObjectConcept.structure 的单源思想（Apache-2.0，机制吸收、表达自写）：
// 同一份结构定义（列名+类型+枚举+描述）同时驱动三处——
//   ①抽取指令渲染 renderExtractionPrompt（字段结构序列化进指令）；
//   ②抽取返回值动态校验 validateRowValues（按定义逐字段生成校验，类型/枚举不符即拒）；
//   ③输出结构终验（同②——人工编辑、导入值与抽取产物共用同一校验器，见 diligenceLedgerModel）。
// 结构可序列化为 JSON 存盘（exportSchemaJson/importSchemaJson 往返不变）＝「字段 schema 用户可配」的载体
// （行为 6/7 验收口径）；枚举/布尔做精确匹配（防「1/True/1.0」型宽松等值混入台账）。
// 不吸收：Document/Aspect/Concept 对象树主干（工作区「扁平 JSON/SQLite，不上图谱模型」约束）。
// 纯函数、零 IO；命名约束为我方自定（增补节：其侧禁下划线前缀，我方侧命名约束随复核轮定——本版即按
// 「非空、不以数字开头、不含空白」收口，宽松于其侧，留复核轮再裁）。

export type FieldType = "text" | "number" | "date" | "enum" | "boolean";

export const FIELD_TYPES: readonly FieldType[] = ["text", "number", "date", "enum", "boolean"];

export interface FieldDef {
  /** 列名（字段键；台账与 CSV 表头同用此名） */
  name: string;
  type: FieldType;
  /** type=enum 时必填：枚举可选值（≥2 项、不重复） */
  enumValues?: string[];
  /** 字段说明：抽取指令与人工补录提示共用同一份 */
  description?: string;
}

export interface FieldSchema {
  schemaId?: string | null;
  name: string;
  fields: FieldDef[];
}

export interface SchemaViolation {
  field: string;
  code: "FIELD_UNKNOWN" | "TYPE_MISMATCH" | "ENUM_OUT_OF_RANGE" | "BOOL_NOT_EXACT" | "NOT_A_DATE";
  message: string;
}

export interface SchemaCheck {
  ok: boolean;
  violations: SchemaViolation[];
}

const NAME_RE = /^[^\s\d][^\s]*$/u; // 非空、首字符非数字非空白、全程无空白
const NAME_MAX = 40;
const DESC_MAX = 200;
const ENUM_MAX = 32;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

// ── 定义面校验（结构本身合法才允许入库/渲染）──
export function validateFieldSchema(def: FieldSchema): { ok: boolean; code?: string; message?: string } {
  if (!def || typeof def !== "object") return { ok: false, code: "SCHEMA_INVALID", message: "字段模板不是合法对象" };
  const name = String(def.name ?? "").trim();
  if (!name) return { ok: false, code: "NAME_EMPTY", message: "字段模板名称不能为空" };
  if (name.length > NAME_MAX) return { ok: false, code: "NAME_TOO_LONG", message: `字段模板名称超过 ${NAME_MAX} 字` };
  if (!Array.isArray(def.fields) || def.fields.length === 0)
    return { ok: false, code: "FIELDS_EMPTY", message: "字段列表不能为空" };
  const seen = new Set<string>();
  for (const f of def.fields) {
    const fname = String(f?.name ?? "").trim();
    if (!fname) return { ok: false, code: "FIELD_NAME_EMPTY", message: "存在空列名" };
    if (fname.length > NAME_MAX) return { ok: false, code: "FIELD_NAME_TOO_LONG", message: `列名超过 ${NAME_MAX} 字：${fname}` };
    if (!NAME_RE.test(fname)) return { ok: false, code: "FIELD_NAME_INVALID", message: `列名含空白或以数字开头：${fname}` };
    if (seen.has(fname)) return { ok: false, code: "FIELD_NAME_DUP", message: `列名重复：${fname}` };
    seen.add(fname);
    if (!FIELD_TYPES.includes(f.type)) return { ok: false, code: "FIELD_TYPE_UNKNOWN", message: `未知字段类型：${String(f.type)}（${fname}）` };
    if (f.type === "enum") {
      const vals = f.enumValues;
      if (!Array.isArray(vals) || vals.length < 2)
        return { ok: false, code: "ENUM_MISSING", message: `枚举字段至少给出 2 个可选值（${fname}）` };
      if (vals.length > ENUM_MAX) return { ok: false, code: "ENUM_TOO_MANY", message: `枚举可选值超过 ${ENUM_MAX} 个（${fname}）` };
      const vseen = new Set<string>();
      for (const v of vals) {
        const s = String(v ?? "");
        if (!s || s.length > NAME_MAX) return { ok: false, code: "ENUM_VALUE_INVALID", message: `枚举值非法（${fname}）：${s}` };
        if (vseen.has(s)) return { ok: false, code: "ENUM_VALUE_DUP", message: `枚举值重复（${fname}）：${s}` };
        vseen.add(s);
      }
    }
    const desc = String(f.description ?? "");
    if (desc.length > DESC_MAX) return { ok: false, code: "DESC_TOO_LONG", message: `字段说明超过 ${DESC_MAX} 字（${fname}）` };
  }
  return { ok: true };
}

/** 规范化：裁空白、非枚举字段丢弃 enumValues（三态一源的单一规范形，渲染/校验/存盘共用） */
export function normalizeFieldSchema(def: FieldSchema): FieldSchema {
  return {
    schemaId: def.schemaId ?? null,
    name: String(def.name ?? "").trim(),
    fields: def.fields.map((f) => ({
      name: String(f.name ?? "").trim(),
      type: f.type,
      ...(f.type === "enum" ? { enumValues: (f.enumValues ?? []).map((v) => String(v)) } : {}),
      ...(f.description ? { description: String(f.description) } : {}),
    })),
  };
}

/** 单源字段键序（S1 的结构基准：渲染与校验两侧都从这份规范化定义出发） */
export function schemaFieldNames(def: FieldSchema): string[] {
  return normalizeFieldSchema(def).fields.map((f) => f.name);
}

// ── ① 抽取指令渲染：同一份结构定义序列化进指令（文案自写）──
export function renderExtractionPrompt(def: FieldSchema): string {
  const norm = normalizeFieldSchema(def);
  const typeLabel: Record<FieldType, string> = {
    text: "文本", number: "数值", date: "日期（格式 YYYY-MM-DD）", enum: "枚举", boolean: "布尔（仅 true/false）",
  };
  const lines = [
    `请从给定底稿文本中逐字段提取下表所列信息（模板「${norm.name}」，共 ${norm.fields.length} 个字段）。`,
    "输出要求：",
  ];
  for (const f of norm.fields) {
    const range = f.type === "enum" ? `，只允许取值：${(f.enumValues ?? []).join(" / ")}` : "";
    const desc = f.description ? `。字段说明：${f.description}` : "";
    lines.push(`- ${f.name}：类型=${typeLabel[f.type]}${range}${desc}`);
  }
  lines.push("- 底稿中查不到的字段留空，不要编造；每个取值须能指回底稿原文位置。");
  return lines.join("\n");
}

// ── 值级精确校验（②抽取返回值校验与③输出终验共用同一实现）──
function isPlainNumberString(s: string): boolean {
  return /^-?\d+(\.\d+)?$/u.test(s.trim());
}

function isRealDate(iso: string): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return false;
  const y = Number(m[1]), mo = Number(m[2]), d = Number(m[3]);
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return false;
  const leap = (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return d <= days[mo - 1]!;
}

export function checkFieldValue(field: FieldDef, value: unknown): SchemaViolation | null {
  const t = field.type;
  if (t === "text") {
    if (typeof value !== "string") return { field: field.name, code: "TYPE_MISMATCH", message: `${field.name} 应为文本` };
    return null;
  }
  if (t === "number") {
    if (typeof value === "boolean") return { field: field.name, code: "TYPE_MISMATCH", message: `${field.name} 应为数值，不接受布尔值` };
    if (typeof value === "number" && Number.isFinite(value)) return null;
    if (typeof value === "string" && isPlainNumberString(value)) return null;
    return { field: field.name, code: "TYPE_MISMATCH", message: `${field.name} 应为数值（数值列给了非数值内容）` };
  }
  if (t === "date") {
    if (typeof value !== "string" || !DATE_RE.test(value.trim()) || !isRealDate(value.trim()))
      return { field: field.name, code: "NOT_A_DATE", message: `${field.name} 应为 YYYY-MM-DD 真实日期` };
    return null;
  }
  if (t === "enum") {
    // 精确匹配：恒等比较，防 1/"1"/1.0 型宽松等值混入（增补节机制点）
    const hit = (field.enumValues ?? []).some((v) => v === value);
    if (!hit) return { field: field.name, code: "ENUM_OUT_OF_RANGE", message: `${field.name} 取值不在枚举范围内` };
    return null;
  }
  // boolean：只认恒等 true/false
  if (value === true || value === false) return null;
  return { field: field.name, code: "BOOL_NOT_EXACT", message: `${field.name} 仅接受 true/false（不接受 1/"true" 等替身）` };
}

/** ②逐字段校验一行取值。未知字段键=violation；缺字段仅在 requireComplete 时计违例。 */
export function validateRowValues(def: FieldSchema, row: Record<string, unknown>, opts: { requireComplete?: boolean } = {}): SchemaCheck {
  const norm = normalizeFieldSchema(def);
  const violations: SchemaViolation[] = [];
  const known = new Map(norm.fields.map((f) => [f.name, f]));
  for (const key of Object.keys(row ?? {})) {
    if (!known.has(key)) { violations.push({ field: key, code: "FIELD_UNKNOWN", message: `未知字段：${key}` }); continue; }
    const v = row[key];
    if (v === null || v === undefined || v === "") continue; // 空值=未提取，不冒类型错
    const bad = checkFieldValue(known.get(key)!, v);
    if (bad) violations.push(bad);
  }
  if (opts.requireComplete) {
    for (const f of norm.fields) {
      const v = row?.[f.name];
      if (v === null || v === undefined || v === "") violations.push({ field: f.name, code: "TYPE_MISMATCH", message: `${f.name} 未填写` });
    }
  }
  return { ok: violations.length === 0, violations };
}

// ── ③ 结构可序列化：导出/导入 JSON 往返不变（S3；行为 6/7「用户可配」载体）──
export function exportSchemaJson(def: FieldSchema): string {
  const norm = normalizeFieldSchema(def);
  return JSON.stringify({ name: norm.name, fields: norm.fields }, null, 2);
}

const IMPORT_KEYS = new Set(["name", "fields", "schemaId"]);

export function importSchemaJson(text: string): { ok: boolean; schema?: FieldSchema; code?: string; message?: string } {
  let parsed: unknown;
  try { parsed = JSON.parse(String(text ?? "")); } catch { return { ok: false, code: "JSON_PARSE", message: "不是合法 JSON" }; }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return { ok: false, code: "JSON_SHAPE", message: "顶层应为对象" };
  for (const k of Object.keys(parsed as object)) {
    if (!IMPORT_KEYS.has(k)) return { ok: false, code: "JSON_KEY_UNKNOWN", message: `未知顶层键：${k}（fail-closed 拒收）` };
  }
  const def = parsed as FieldSchema;
  const check = validateFieldSchema(def);
  if (!check.ok) return { ok: false, code: check.code, message: check.message };
  return { ok: true, schema: normalizeFieldSchema(def) };
}
