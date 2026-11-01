// 可视化 B 轨共享：XML 转义与 Word/Excel 单文件 XML 组装件（净室自写）。
// 交付面选型：Word 交付版=WordprocessingML 2003 单文件 XML、Excel 母表=SpreadsheetML 2003
// 单文件 XML——两者均为纯文本 XML、零依赖、字节级确定（同一输入两次渲染逐字节一致，契约二）。
// 工程坑位照收（A9 机制等量，修法自写）：
//  - 颜色一律显式八位 ARGB（SpreadsheetML ss:Color="#FF......"），不留六位隐式 alpha；
//  - 空白敏感单元格写 xml:space="preserve"，文本节点紧跟前段不落孤立空白节点；
//  - 公式不指望阅读器重算：公式串与缓存值同写（LibreOffice 不重算 Excel 的坑）。

/** XML 属性/文本转义（五实体+控制字符丢弃，输出确定）。 */
export function xmlEscape(s: string): string {
  let out = "";
  for (const ch of s) {
    if (ch === "&") out += "&amp;";
    else if (ch === "<") out += "&lt;";
    else if (ch === ">") out += "&gt;";
    else if (ch === '"') out += "&quot;";
    else if (ch === "'") out += "&apos;";
    else if (ch.codePointAt(0)! < 0x20) continue; // 控制字符不进 XML
    else out += ch;
  }
  return out;
}

/** WordprocessingML 2003 文档头（mso-application 指令使 Word/WPS 直接识别）。 */
export function wordXmlProlog(): string {
  return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    + '<?mso-application progid="Word.Document"?>\n';
}

/** SpreadsheetML 2003 工作簿头。 */
export function excelXmlProlog(): string {
  return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    + '<?mso-application progid="Excel.Sheet"?>\n';
}

export const SS_NS = 'xmlns="urn:schemas-microsoft-com:office:spreadsheet"'
  + ' xmlns:o="urn:schemas-microsoft-com:office:office"'
  + ' xmlns:x="urn:schemas-microsoft-com:office:excel"'
  + ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"';

/** SpreadsheetML 单元格：值类型 text|number，可选公式（缓存值同写）。
 * 公式注入防御（施工单-10 单元一）：字符串格恒 ss:Type="String"（不经公式/数值推断），
 * 公式通道仅对数值格开放——字符串格禁携 ss:Formula（携之=把不可信文本送进可执行通道，
 * fail-fast 具名拒）。我方自产公式（如序号列 ROW()-2）全部走数值格，零既有影响。 */
export function ssCell(
  value: string | number | null,
  opts: { formula?: string; styleId?: string; type?: "String" | "Number" } = {},
): string {
  const type = opts.type ?? (typeof value === "number" ? "Number" : "String");
  const attrs = [opts.styleId ? ` ss:StyleID="${opts.styleId}"` : ""].join("");
  if (value === null || value === undefined) return `<Cell${attrs}/>`;
  if (opts.formula && !(type === "Number" && typeof value === "number" && Number.isFinite(value))) {
    throw new Error(`ssCell 公式通道仅数值格开放（type=${type}、值非有限数；字符串格禁携 ss:Formula）`);
  }
  const f = opts.formula ? ` ss:Formula="${xmlEscape(opts.formula)}"` : "";
  if (type === "Number" && typeof value === "number" && Number.isFinite(value)) {
    return `<Cell${attrs}${f}><Data ss:Type="Number">${value}</Data></Cell>`;
  }
  return `<Cell${attrs}><Data ss:Type="String" xml:space="preserve">${xmlEscape(String(value))}</Data></Cell>`;
}

/** SpreadsheetML 样式：Header/g(分组色块)/Decisive(深红)/Plain 四用，颜色全部八位 ARGB。 */
export function ssStyle(id: string, o: { bold?: boolean; color?: string; bg?: string; align?: "Left" | "Center" } = {}): string {
  const font = `<Font ss:FontName="${o.bold ? "Noto Sans CJK SC" : "Noto Sans CJK SC"}" x:Family="Swiss" ss:Size="10"${o.bold ? ' ss:Bold="1"' : ""}${o.color ? ` ss:Color="${o.color}"` : ""}/>`;
  const interior = o.bg ? `<Interior ss:Color="${o.bg}" ss:Pattern="Solid"/>` : "";
  const align = `<Alignment ss:Vertical="Center"${o.align === "Center" ? ' ss:Horizontal="Center"' : ""} ss:WrapText="1"/>`;
  return `<Style ss:ID="${id}">${font}${align}${interior}</Style>`;
}
