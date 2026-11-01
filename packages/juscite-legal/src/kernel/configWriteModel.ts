// 结构化配置写入防御内核（施工单-10 单元二·YAML/JSON 配置面；机制等量自研，文案全部自写）。
// 唯一职责：把「用户/模型来源字符串」写成结构化配置（YAML frontmatter）时的注入防御——
//   ① 用户来源值一律显式双引号化（safe dump 引号化）：值永远是单行纯标量，
//      冒号/换行/锚点(&a *a)/标签(!!python)/引号/反斜杠/控制字符全部只可能是数据，不可能是结构；
//   ② 键名禁来自用户原文：键必须来自调用方闭集字面量，本内核再以键语法闸兜底
//      （字母数字下划线连字符，另拒 JS 原型面危险键 __proto__/constructor/prototype），重复键即拒；
//   ③ 写入前 round-trip 校验：自产文本用本内核严格读回，结构键集合与期望闭集零变化、
//      值逐字段回读相等，任一不符=typed 拒（fail-closed，坏配置不落盘）。
// 零依赖零 IO 纯函数（桥侧 learning_runtime 只做装配，内核单源——learningModel 同法）。
// 引号化实现取 JSON 字符串字面量：它是 YAML 1.2 双引号标量的合法子集（\" \\ \n \r \t \uXXXX），
// 标准解析器（yaml 包/gray-matter）读回即纯标量字符串。

export class ConfigWriteError extends Error {
  /** typed 失败码（cfgwrite_*）；message 只有错误码，绝不携带配置内容。 */
  readonly code: string;
  constructor(code: string) {
    super(code);
    this.code = code;
  }
}

/** 键语法闸：键只能由调用方闭集字面量提供（字母/数字/下划线/连字符，首字符字母或下划线）。 */
export const FRONTMATTER_KEY_RE = /^[A-Za-z_][A-Za-z0-9_-]*$/;

// JS 原型面危险键（赋值/展开通道的已知旁路）——结构上直接拒，不进任何配置文件。
const PROTOTYPE_KEYS = new Set(["__proto__", "constructor", "prototype"]);

/** 用户来源字符串 → 单行双引号 YAML 标量（=JSON 字符串字面量；round-trip 无损）。 */
export function yamlQuoteScalar(value: unknown): string {
  if (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean") {
    throw new ConfigWriteError("cfgwrite_field_invalid");
  }
  return JSON.stringify(value);
}

export interface FrontmatterField {
  key: string;
  value: string;
}

function checkKey(key: string): string {
  if (typeof key !== "string" || !FRONTMATTER_KEY_RE.test(key) || PROTOTYPE_KEYS.has(key)) {
    throw new ConfigWriteError("cfgwrite_key_invalid");
  }
  return key;
}

/**
 * 构造带围栏的 frontmatter 块：`---\nkey: "value"\n---`。
 * 键过语法闸（重复即拒）；值一律双引号化。返回文本尚未经 round-trip 校验——
 * 落盘请用 writeFrontmatterChecked（单一入口，校验后才可写）。
 */
export function buildFrontmatterBlock(fields: readonly FrontmatterField[]): string {
  if (!Array.isArray(fields) || fields.length === 0) throw new ConfigWriteError("cfgwrite_field_invalid");
  const seen = new Set<string>();
  const lines: string[] = [];
  for (const field of fields) {
    const key = checkKey(field?.key);
    if (seen.has(key)) throw new ConfigWriteError("cfgwrite_duplicate_key");
    seen.add(key);
    lines.push(`${key}: ${yamlQuoteScalar(field.value)}`);
  }
  return `---\n${lines.join("\n")}\n---`;
}

/**
 * 严格读回（只认本内核产出的形态）：围栏 + 每行 `key: "双引号标量"`。
 * 任何偏离（裸值/未闭合围栏/重复键/非法转义/多余行）都返回 null——
 * 解析器面越窄，写入面被结构注入后越读不回来（round-trip 校验才能兜住）。
 */
export function readFrontmatterScalars(text: string): Record<string, string> | null {
  if (typeof text !== "string") return null;
  const normalized = text.replace(/^\uFEFF/u, "").replace(/\r\n/g, "\n");
  if (!normalized.startsWith("---\n")) return null;
  const lines = normalized.split("\n");
  const close = lines.indexOf("---", 1);
  if (close < 0) return null;
  const out: Record<string, string> = {};
  for (let index = 1; index < close; index += 1) {
    const match = /^([A-Za-z_][A-Za-z0-9_-]*): "((?:[^"\\]|\\.)*)"$/u.exec(lines[index] ?? "");
    if (!match || PROTOTYPE_KEYS.has(match[1] ?? "")) return null;
    const key = match[1]!;
    if (key in out) return null;
    try {
      out[key] = JSON.parse(`"${match[2] ?? ""}"`) as string;
    } catch {
      return null;
    }
  }
  return out;
}

/**
 * 写入前 round-trip 校验（fail-closed 单一入口）：
 * 构造 → 严格读回 → 结构键集合与 expectedKeys 零变化（多键/少键/换键都拒）+ 值逐字段相等。
 * 通过才返回可落盘文本；任一不符抛 ConfigWriteError（cfgwrite_* 码），调用方不得写盘。
 */
export function writeFrontmatterChecked(
  fields: readonly FrontmatterField[],
  expectedKeys: readonly string[],
): string {
  if (!Array.isArray(expectedKeys) || expectedKeys.length === 0) {
    throw new ConfigWriteError("cfgwrite_field_invalid");
  }
  for (const key of expectedKeys) checkKey(key);
  const text = buildFrontmatterBlock(fields);
  const parsed = readFrontmatterScalars(text);
  if (parsed === null) throw new ConfigWriteError("cfgwrite_roundtrip_shape");
  const actualKeys = Object.keys(parsed).sort().join(",");
  const wantedKeys = [...expectedKeys].sort().join(",");
  if (actualKeys !== wantedKeys) throw new ConfigWriteError("cfgwrite_roundtrip_mismatch");
  for (const field of fields) {
    if (parsed[field.key] !== field.value) throw new ConfigWriteError("cfgwrite_roundtrip_mismatch");
  }
  return text;
}

/**
 * 独立校验既有文本（回执/复核面）：结构键集合必须恰等于 expectedKeys 且全部读回为纯标量。
 * 返回读回的键值；形态不符=cfgwrite_roundtrip_shape，键集合漂移=cfgwrite_roundtrip_mismatch。
 */
export function roundTripCheckFrontmatter(text: string, expectedKeys: readonly string[]): Record<string, string> {
  const parsed = readFrontmatterScalars(text);
  if (parsed === null) throw new ConfigWriteError("cfgwrite_roundtrip_shape");
  const actualKeys = Object.keys(parsed).sort().join(",");
  const wantedKeys = [...expectedKeys].sort().join(",");
  if (actualKeys !== wantedKeys) throw new ConfigWriteError("cfgwrite_roundtrip_mismatch");
  return parsed;
}
