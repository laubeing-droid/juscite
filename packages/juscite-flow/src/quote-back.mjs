// @juscite/flow · tabular-review 逐字引文回验共享 validator（RE-12 对照源增补节 T40-T42；
// 施工单-10-P0防注入与引文回验 单元四 R2）。来源=claude-for-legal skills/tabular-review 机制吸收
// （仓锚 4a6c651889c9，Apache-2.0；表达隔离——三规则转写与全部文案自写，零逐字化用官方句段）：
//   规则一（T40）：每个抽取值必须随附出处逐字引文+位置锚——一致性判据=归一空白后子串匹配
//     （值须可在其引文中逐字复现），容错中文全半角标点（宽窄互认）；转述/拼接引文过不了该判据。
//   规则二（T41）：无引文之值=按编造处理——显式 fabricated 旗标，结果集与输入逐条对应零静默丢弃；
//     程序派生值/否定性主张由消费面适配器显式单列（uncited/derived），不入编造桶（RE-12 分母边界）。
//   规则三（T42）：已作答但证据对不上 > 如实未答——severityRank 全序 pass(0)<unclear(1)<mismatch(2)<fabricated(3)。
// 消费面：#33 cross-verification（分析层主张面）/#34 fact-verification（直接主张 fact 面）同包 import；
// #32 尽调台账经桥 I/O 层 tools/bridge/diligence_service.mjs import（juscite-legal kernel 零跨包依赖不碰）。
// 回验=报告旗标面（呈现给复核者），不承担发布硬门——引用存在性闭环（各面既有 cite-verify 族）与本件分立。
// 纯函数、零 IO、零模型；同输入字节级同输出。
// engine.mjs 不在本分支（S12 缺口）。回验只需要这个错误类型，不装配整套流程引擎。
class FlowEngineError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "FlowEngineError";
    this.code = code;
  }
}

export const QUOTE_BACK_VERDICTS = ["pass", "mismatch", "fabricated"];
// 严重度全序（RE-12 规则三）：已答错（mismatch）与已答无据（fabricated）均压过如实未答（unclear）；
// unclear 非 validator 判定值——它是消费面既有「待核/不足」态，入序供消费面统一排序（severityRank 可查）。
export const QUOTE_BACK_SEVERITY = Object.freeze({ pass: 0, unclear: 1, mismatch: 2, fabricated: 3 });

export function severityRank(kind) {
  const v = QUOTE_BACK_SEVERITY[kind];
  if (v === undefined) throw new FlowEngineError("VALIDATION", `未知回验严重度档：${kind}（合法=${Object.keys(QUOTE_BACK_SEVERITY).join("/")}）`);
  return v;
}

// 中文标点→ASCII 折算表（全半角互认面；值/引文两侧同折，宽窄差不再改判）
const PUNCT_FOLD = new Map([
  ["，", ","], ["、", ","], ["。", "."], ["；", ";"], ["：", ":"],
  ["（", "("], ["）", ")"], ["！", "!"], ["？", "?"],
  ["《", "<"], ["》", ">"], ["【", "["], ["】", "]"], ["〔", "["], ["〕", "]"],
  ["「", "\""], ["」", "\""], ["『", "\""], ["』", "\""], ["“", "\""], ["”", "\""], ["‘", "'"], ["’", "'"],
  ["－", "-"], ["～", "~"], ["　", ""],
]);

// 归一：全角 ASCII（U+FF01-FF5E）折半角 + 中文标点折算 + 剔除全部空白（含全角空格/不换行空格）
export function normalizeQuoteText(text) {
  let s = String(text ?? "");
  let out = "";
  for (const ch of s) {
    const code = ch.codePointAt(0);
    let c = ch;
    if (PUNCT_FOLD.has(ch)) c = PUNCT_FOLD.get(ch);
    else if (code >= 0xff01 && code <= 0xff5e) c = String.fromCharCode(code - 0xfee0); // ！-～ → !-~
    if (/\s/u.test(c)) continue; // 空白（含 \u3000 已被折为 ""，此处兜底 ASCII 空白族）
    out += c;
  }
  return out;
}

// 单值回验：{value, quote} → {verdict, severity, reason}
//   quote 缺/空 → fabricated（规则二：无引文之值=按编造处理，显式旗标不静默）
//   归一后 value ⊄ quote → mismatch（规则三：已作答但引文不支持该值——伪造证据链）
//   否则 → pass
export function checkQuoteBack({ value, quote } = {}) {
  if (typeof value !== "string" || value.length < 1) {
    throw new FlowEngineError("VALIDATION", "回验值必须是非空字符串（空值由消费面适配器先剔除，不入回验分母）");
  }
  if (quote === null || quote === undefined || normalizeQuoteText(quote) === "") {
    return { verdict: "fabricated", severity: QUOTE_BACK_SEVERITY.fabricated, reason: "值未携带逐字引文——按编造处理（显式旗标，不静默丢弃）" };
  }
  const nv = normalizeQuoteText(value);
  const nq = normalizeQuoteText(quote);
  if (nv === "") {
    return { verdict: "mismatch", severity: QUOTE_BACK_SEVERITY.mismatch, reason: "归一后值为空，不能按已核验放行" };
  }
  if (nq.includes(nv)) {
    return { verdict: "pass", severity: QUOTE_BACK_SEVERITY.pass, reason: "值在其逐字引文中复现（归一空白后子串匹配，全半角标点互认）" };
  }
  return { verdict: "mismatch", severity: QUOTE_BACK_SEVERITY.mismatch, reason: "引文不支持该值（归一后值非引文子串）——已作答但证据链对不上" };
}

// 批量回验：entries=[{value, quote, ...上下文}] → 逐条判定一一对应（规则二零丢弃）。
// 上下文字段原样随行（claimId/rowNo/field 等），消费面直接落报告。
export function verifyQuoteBack(entries) {
  if (!Array.isArray(entries)) throw new FlowEngineError("VALIDATION", "回验输入必须是数组 [{value, quote, ...}]");
  const results = [];
  const counts = { pass: 0, mismatch: 0, fabricated: 0 };
  for (const e of entries) {
    const verdict = checkQuoteBack({ value: e?.value, quote: e?.quote });
    counts[verdict.verdict] += 1;
    const { value: _v, quote: _q, ...context } = e ?? {};
    results.push({ ...context, value: e?.value, verdict: verdict.verdict, severity: verdict.severity, reason: verdict.reason });
  }
  return {
    mode: "deterministic",
    total: results.length,
    counts,
    results,
    note: "逐字引文回验（tabular-review）：无引文=编造旗标；已答且引文不符>如实未答（severity 全序 pass<unclear<mismatch<fabricated）",
  };
}
