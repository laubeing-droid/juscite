// 【表格导出公式注入防御】CSV 导出共享 sanitizer（施工单-10 单元一，2026-11-01）。
// 机制来源=竞品情报《2026-11-01 官方开源与兄弟逆向波》A 报告 §④ 条 6/7（Excel 公式注入同威胁
// 异表面；机制学习，零文本搬运，文案自写）。集中一处、禁各导出面散写：
//   - 单元格值（用户/文档来源字符串）去除前导空白后以 `= + - @ \t \r` 任一开头 → CSV 前置 `'`；
//   - 我方自产纯数字金额（含负数/千分位，如 -1200.00 / +300 / 1,200.50）不拦——不是注入向量；
//   - 全角 ＝＋－＠、零宽字符（U+200B/U+200C 等）与换行后的新起始符同样视为注入（表格软件会折叠或另起一行）；
//   - xlsx/SpreadsheetML 侧的防御是「强制 cell type=string，不经公式/数值推断」，不在此文件
//     （见 @juscite/vizb shared/xml.ts ssCell：字符串格恒 ss:Type="String"，公式通道仅对
//     数值格开放；桥 Python 侧 excel_export.py inlineStr 恒字符串格）。
// 纯函数、零 IO。

/** CSV 公式注入起始符闭集（OWASP CSV Injection 口径收口：= + - @ 及制表/回车先行形）。 */
export const CSV_FORMULA_LEAD_CHARS: ReadonlySet<string> = new Set(["=", "+", "-", "@", "\t", "\r"]);

/** 我方自产纯数字金额豁免形：符号后跟数字，其余仅数字/小数点/千分位（十进制串口径，金额不落浮点）。 */
const OWN_NUMERIC_AMOUNT_RE = /^[-+]\d[\d.,]*$/u;

/** 零宽/不可见字符：夹在起始符前可绕过「看首字符」。 */
const CSV_INVISIBLE_RE = /[\u200B\u200C\u200D\u2060\uFEFF\u00AD]/g;

/** 全角公式起始符折成半角再进闭集（＝＋－＠）。 */
const FULLWIDTH_FORMULA_LEAD: Readonly<Record<string, string>> = {
  "\uFF1D": "=",
  "\uFF0B": "+",
  "\uFF0D": "-",
  "\uFF20": "@",
};

function lineIsFormulaLead(line: string): boolean {
  const visible = line.replace(CSV_INVISIBLE_RE, "").replace(/^[\s\uFEFF]+/u, "");
  const ch = FULLWIDTH_FORMULA_LEAD[visible[0] ?? ""] ?? visible[0] ?? "";
  return ch !== "" && CSV_FORMULA_LEAD_CHARS.has(ch);
}

/** 去前导空白/零宽后，任一行首字符落入注入起始符闭集（含全角折半角、换行注入）。 */
export function isCsvFormulaLead(value: string): boolean {
  const raw = String(value ?? "").replace(CSV_INVISIBLE_RE, "");
  return raw.split(/\r\n|\n|\r/u).some((line) => lineIsFormulaLead(line));
}

/**
 * CSV 导出格防御：命中注入起始形 → 前置 `'`（Excel 惯用转义；读回首字符即 `'`）；
 * 纯数字金额与其余值原样返回（除前置 `'` 外零改写——交付值逐字保留是台账口径）。
 * 全部 CSV 导出路径（盘上落盘与 HTTP 下载直出）统一经此函数后再走 RFC4180 引号化。
 */
export function csvFormulaGuard(value: string): string {
  const v = String(value ?? "");
  if (!isCsvFormulaLead(v)) return v;
  if (OWN_NUMERIC_AMOUNT_RE.test(v.replace(/^[\s\uFEFF]+/u, ""))) return v;
  return "'" + v;
}
