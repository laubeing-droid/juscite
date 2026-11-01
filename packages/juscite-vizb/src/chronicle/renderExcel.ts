// 大事记 Excel 母表渲染（SpreadsheetML 2003 单文件 XML；零依赖、字节级确定）。
// 工程坑照收（A9）：公式串与缓存值同写（阅读器不重算也能看对）；空白敏感单元格
// xml:space="preserve"；颜色八位 ARGB。母表=全量底稿＋律师回填列（争点/备注交付时恒空）。

import { excelXmlProlog, ssCell, ssStyle, SS_NS, xmlEscape } from "../shared/xml.ts";
import { deriveEvidenceStatus, type FactBase } from "./factbase.ts";
import { sortedFacts } from "./guards.ts";
import { sourceRefOf } from "./renderWord.ts";

export const MASTER_COLUMNS = [
  "序号", "日期", "精度", "事项", "主要内容（全量）", "主体", "证据编号", "证据状态", "出处",
  "矛盾报告", "争点（律师回填）", "备注（律师回填）",
] as const;
const COL_W = [45, 78, 52, 110, 340, 90, 60, 78, 150, 140, 130, 130] as const;
const PRECISION_CELL: Record<string, string> = { day: "确切日", month: "仅至月", year: "仅至年", span: "区间" };

/** 渲染（纯函数；输入须已过守卫）。序号列公式=ROW()-2，缓存值=事实号直写。 */
export function renderExcel(fb: FactBase): string {
  const facts = sortedFacts(fb);
  const titleRow = `<Row>${ssCell(`${xmlEscape(fb.caseTitle)}·大事记母表（争点/备注两列由律师回填；序号列含公式=ROW()-2，缓存值已直写）`, { styleId: "title" })}${MASTER_COLUMNS.slice(1).map(() => "<Cell/>").join("")}</Row>`;
  const headerRow = "<Row>" + MASTER_COLUMNS.map((c) => ssCell(c, { styleId: "hdr" })).join("") + "</Row>";
  const dataRows = facts.map((f) => "<Row>"
    + ssCell(f.factNo, { type: "Number", formula: "ROW()-2", styleId: "num" })
    + ssCell(f.dateStr)
    + ssCell(PRECISION_CELL[f.datePrecision] ?? f.datePrecision)
    + ssCell(`${f.verb}·${f.title}`)
    + ssCell(f.content)
    + ssCell(f.subjects.join("、"))
    + ssCell(f.evidenceNo ?? "")
    + ssCell(deriveEvidenceStatus(f))
    + ssCell(sourceRefOf(fb, f))
    + ssCell(f.arithmeticNote ?? "")
    + ssCell("")
    + ssCell("")
    + "</Row>").join("");
  const table = `<Table ss:ExpandedColumnCount="${MASTER_COLUMNS.length}" ss:ExpandedRowCount="${facts.length + 2}">`
    + COL_W.map((w) => `<Column ss:Width="${w}"/>`).join("")
    + titleRow + headerRow + dataRows
    + "</Table>";
  return excelXmlProlog()
    + `<Workbook ${SS_NS}>`
    + "<Styles>"
    + ssStyle("Default")
    + ssStyle("title", { bold: true })
    + ssStyle("hdr", { bold: true, color: "#FFFFFFFF", bg: "#FF374151" })
    + ssStyle("num", { align: "Center" })
    + "</Styles>"
    + `<Worksheet ss:Name="大事记母表">${table}</Worksheet>`
    + "</Workbook>";
}
