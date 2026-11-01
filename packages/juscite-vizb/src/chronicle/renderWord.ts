// 大事记 Word 交付版渲染（契约二：脚本算几何——版面常量定死；契约三：一字不改底稿）。
// 格式=WordprocessingML 2003 单文件 XML（零依赖、字节级确定）；A4 竖版，页边距与五列宽为常量。
// 字体=我方自选可分发字族（Noto Sans CJK SC / Arial），中西文分族声明在每个 run；
// 出处列用尾注号去重（同出处共用同一注号），表后列尾注表。

import { xmlEscape, wordXmlProlog } from "../shared/xml.ts";
import { deriveEvidenceStatus, type FactBase } from "./factbase.ts";
import { DATE_PRECISION_LABEL } from "./tables.ts";
import { sortedFacts } from "./guards.ts";

// ── 版面常量（twips；A4 竖版 11906×16838）──
export const WORD_PAGE = { w: 11906, h: 16838 } as const;
export const WORD_MARGIN = { top: 1440, right: 1440, bottom: 1440, left: 1440 } as const;
export const WORD_BODY_W = WORD_PAGE.w - WORD_MARGIN.left - WORD_MARGIN.right; // 9026
/** 五列定死：日期/事项/主要内容/证据状态/出处（我方自定列序，合计=版心宽，误差为零）。 */
export const WORD_COLS = [1300, 1560, 4566, 800, 800] as const;
export const WORD_FONT = { ascii: "Arial", eastAsia: "Noto Sans CJK SC" } as const;
const HEADERS = ["日期", "事项", "主要内容", "证据状态", "出处"] as const;

function run(text: string, opts: { bold?: boolean; sizeHalfPt?: number } = {}): string {
  const rPr = `<w:rPr><w:rFonts w:ascii="${WORD_FONT.ascii}" w:hAnsi="${WORD_FONT.ascii}" w:eastAsia="${WORD_FONT.eastAsia}"/>`
    + (opts.bold ? "<w:b/>" : "") + `<w:sz w:val="${opts.sizeHalfPt ?? 18}"/><w:szCs w:val="${opts.sizeHalfPt ?? 18}"/></w:rPr>`;
  return `<w:r>${rPr}<w:t xml:space="preserve">${xmlEscape(text)}</w:t></w:r>`;
}
function para(runs: string, opts: { align?: "left" | "center"; spacing?: number } = {}): string {
  const pPr = `<w:pPr>${opts.align === "center" ? '<w:jc w:val="center"/>' : ""}`
    + `<w:spacing w:before="${opts.spacing ?? 0}" w:after="${opts.spacing ?? 40}" w:line="240" w:lineRule="auto"/></w:pPr>`;
  return `<w:p>${pPr}${runs}</w:p>`;
}
function cell(w: number, children: string): string {
  return `<w:tc><w:tcPr><w:tcW w:w="${w}" w:type="dxa"/></w:tcPr>${children}</w:tc>`;
}

/** 出处尾注号去重：同出处串共用同一注号。 */
export function buildEndnotes(fb: FactBase): Map<string, number> {
  const m = new Map<string, number>();
  for (const f of sortedFacts(fb)) {
    const ref = `${f.volume}《${fb.docs.find((d) => d.docId === f.sourceDoc)?.label ?? f.sourceDoc}》${f.locator}`;
    if (!m.has(ref)) m.set(ref, m.size + 1);
  }
  return m;
}
export function sourceRefOf(fb: FactBase, f: FactBase["facts"][number]): string {
  return `${f.volume}《${fb.docs.find((d) => d.docId === f.sourceDoc)?.label ?? f.sourceDoc}》${f.locator}`;
}

/** 渲染（纯函数）。输入须已过守卫；本函数不再判断、不改一字。 */
export function renderWord(fb: FactBase): string {
  const notes = buildEndnotes(fb);
  const facts = sortedFacts(fb);
  const rows: string[] = [];
  // 表头
  rows.push("<w:tr>" + HEADERS.map((h, i) => cell(WORD_COLS[i]!, para(run(h, { bold: true })))).join("") + "</w:tr>");
  for (const f of facts) {
    const dateCell = f.datePrecision === "day" ? f.dateStr : f.datePrecision === "span" ? f.dateStr : `${f.dateStr}（${DATE_PRECISION_LABEL[f.datePrecision]}）`;
    const status = deriveEvidenceStatus(f);
    const noteNo = notes.get(sourceRefOf(fb, f))!;
    rows.push("<w:tr>"
      + cell(WORD_COLS[0]!, para(run(dateCell)))
      + cell(WORD_COLS[1]!, para(run(`${f.verb}·${f.title}`)))
      + cell(WORD_COLS[2]!, para(run(f.content)))
      + cell(WORD_COLS[3]!, para(run(status)))
      + cell(WORD_COLS[4]!, para(run(`注${noteNo}`)))
      + "</w:tr>");
  }
  const grid = `<w:tblGrid>${WORD_COLS.map((w) => `<w:gridCol w:w="${w}"/>`).join("")}</w:tblGrid>`;
  const tbl = `<w:tbl><w:tblPr><w:tblW w:w="${WORD_BODY_W}" w:type="dxa"/>`
    + '<w:tblBorders><w:top w:val="single" w:sz="4"/><w:left w:val="single" w:sz="4"/><w:bottom w:val="single" w:sz="4"/><w:right w:val="single" w:sz="4"/><w:insideH w:val="single" w:sz="4"/><w:insideV w:val="single" w:sz="4"/></w:tblBorders>'
    + "</w:tblPr>" + grid + rows.join("") + "</w:tbl>";
  const endnoteParas = [...notes.entries()].map(([ref, no]) => para(run(`注${no}＝${ref}`))).join("");
  const uncertainty = fb.uncertainty.length
    ? para(run("不确定清单（无书证事实，机械生成）", { bold: true })) + fb.uncertainty.map((u) => para(run(u))).join("")
    : "";
  return wordXmlProlog()
    + `<w:wordDocument xmlns:w="http://schemas.microsoft.com/office/word/2003/wordml" xml:space="preserve">`
    + "<w:body>"
    + para(run(`${fb.caseTitle}·大事记表`, { bold: true, sizeHalfPt: 28 }), { align: "center" })
    + tbl
    + para(run("出处尾注（同出处共用注号）", { bold: true }), { spacing: 120 })
    + endnoteParas
    + uncertainty
    + `<w:sectPr><w:pgSz w:w="${WORD_PAGE.w}" w:h="${WORD_PAGE.h}"/>`
    + `<w:pgMar w:top="${WORD_MARGIN.top}" w:right="${WORD_MARGIN.right}" w:bottom="${WORD_MARGIN.bottom}" w:left="${WORD_MARGIN.left}" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>`
    + "</w:body></w:wordDocument>";
}
