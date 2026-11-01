// R/W/X/简表四组交付面守卫（契约三：渲染层一字不许动底稿；判据盯「真正画进去的那份数据」——
// 全部从产物字符串解析回读比对，不查生成函数返回值；绕开函数直接改渲染数据/产物，判据照样报）。

import { deriveEvidenceStatus, type FactBase, type FactRow } from "./factbase.ts";
import { sortedFacts } from "./guards.ts";
import { BRIEF_BANNED_MARKERS, BRIEF_CONTENT_CHARS, BRIEF_MARGIN, BRIEF_MAX_LINES, BRIEF_PAGE, renderBrief } from "./renderBrief.ts";
import { MASTER_COLUMNS } from "./renderExcel.ts";
import { WORD_BODY_W, WORD_COLS, buildEndnotes, sourceRefOf } from "./renderWord.ts";
import { clipForBrief, stripPunct } from "./textcheck.ts";

export interface ArtifactViolation { group: "VB-R" | "VB-W" | "VB-X" | "VB-简表"; code: string; msg: string }

/** 文本宽度估算（确定性常量：全角=字号，半角=0.55×字号）——版心越界扫产物用。 */
export function measureText(text: string, fontSize: number): number {
  let w = 0;
  for (const ch of text) {
    const c = ch.codePointAt(0)!;
    const fullWidth = (c >= 0x2e80 && c <= 0x9fff) || (c >= 0x3000 && c <= 0x303f) || (c >= 0xf900 && c <= 0xfaff) || (c >= 0xff00 && c <= 0xff60) || (c >= 0xffe0 && c <= 0xffe6);
    w += fullWidth ? fontSize : fontSize * 0.55;
  }
  return w;
}

function decode(s: string): string {
  return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, "&");
}

// ── Word 产物解析回读 ──
export function parseWordRows(xml: string): string[][] {
  const rows: string[][] = [];
  for (const tr of xml.match(/<w:tr>[\s\S]*?<\/w:tr>/g) ?? []) {
    const cells: string[] = [];
    for (const tc of tr.match(/<w:tc>[\s\S]*?<\/w:tc>/g) ?? []) {
      cells.push((tc.match(/<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/g) ?? []).map((t) => decode(t.replace(/<\/?w:t(?:\s[^>]*)?>/g, ""))).join(""));
    }
    rows.push(cells);
  }
  return rows;
}

/** R+W：Word 交付版守卫（渲染零改动＋版面/字族/尾注自检）。 */
export function guardWordArtifact(fb: FactBase, xml: string): ArtifactViolation[] {
  const v: ArtifactViolation[] = [];
  const rows = parseWordRows(xml);
  const facts = sortedFacts(fb);
  if (rows.length !== facts.length + 1) v.push({ group: "VB-R", code: "R-row-count", msg: `Word 行数 ${rows.length - 1} ≠ 底稿事实数 ${facts.length}（渲染层零改动：条数逐项比对）` });
  const notes = buildEndnotes(fb);
  facts.forEach((f: FactRow, i) => {
    const r = rows[i + 1];
    if (!r) return;
    const expectDate = f.datePrecision === "day" || f.datePrecision === "span"
      ? f.dateStr
      : `${f.dateStr}（${f.datePrecision === "month" ? "仅至月" : "仅至年"}）`;
    if (r[0] !== expectDate) v.push({ group: "VB-R", code: "R-date", msg: `事实 ${f.factNo} 日期画成「${r[0]}」（底稿「${expectDate}」）：渲染层一字不许动底稿` });
    if (r[1] !== `${f.verb}·${f.title}`) v.push({ group: "VB-R", code: "R-item", msg: `事实 ${f.factNo} 事项画成「${r[1]}」（底稿「${f.verb}·${f.title}」）：渲染层一字不许动底稿` });
    if (stripPunct(r[2] ?? "") !== stripPunct(f.content)) v.push({ group: "VB-R", code: "R-content", msg: `事实 ${f.factNo} 主要内容被改动（去标点后逐字比对不等）` });
    if (r[3] !== deriveEvidenceStatus(f)) v.push({ group: "VB-R", code: "R-evidence", msg: `事实 ${f.factNo} 证据状态画成「${r[3]}」（机械值「${deriveEvidenceStatus(f)}」）` });
    if (r[4] !== `注${notes.get(sourceRefOf(fb, f))}`) v.push({ group: "VB-W", code: "W-endnote", msg: `事实 ${f.factNo} 注号与出处尾注表不一致` });
  });
  const grid = (xml.match(/<w:gridCol w:w="(\d+)"\/>/g) ?? []).map((g) => Number(g.replace(/\D/g, "")));
  if (grid.length !== WORD_COLS.length || grid.reduce((a, b) => a + b, 0) !== WORD_BODY_W) {
    v.push({ group: "VB-W", code: "W-grid", msg: `Word 列栅 ${grid.join("+")} ≠ 定死五列 ${WORD_COLS.join("+")}=${WORD_BODY_W}` });
  }
  const runsTotal = (xml.match(/<w:r>/g) ?? []).length;
  const runsWithFont = (xml.match(/<w:rFonts w:ascii="[^"]+" w:hAnsi="[^"]+" w:eastAsia="[^"]+"\/>/g) ?? []).length;
  if (runsWithFont !== runsTotal) v.push({ group: "VB-W", code: "W-font-family", msg: `中西文分族不全：${runsTotal} 个 run 中 ${runsWithFont} 个带 ascii+eastAsia 字族` });
  const endnoteLines = xml.match(/注\d+＝[^<]+/g) ?? [];
  const expectNotes = [...notes.entries()].map(([ref, no]) => `注${no}＝${ref}`);
  if (endnoteLines.length !== expectNotes.length || expectNotes.some((e, i) => e !== endnoteLines[i])) {
    v.push({ group: "VB-W", code: "W-endnote-dedupe", msg: "尾注表与去重映射不一致（同出处须共用注号）" });
  }
  return v;
}

// ── Excel 产物解析回读 ──
export function parseExcelRows(xml: string): { cells: string[][]; formulas: Array<{ formula: string; cached: string; row: number }> } {
  const rows: string[][] = [];
  const formulas: Array<{ formula: string; cached: string; row: number }> = [];
  let ri = 0;
  for (const rowXml of xml.match(/<Row>[\s\S]*?<\/Row>/g) ?? []) {
    ri += 1;
    const cells: string[] = [];
    for (const c of rowXml.match(/<Cell[\s\S]*?<\/Cell>|<Cell\/>/g) ?? []) {
      const f = /ss:Formula="([^"]+)"/.exec(c)?.[1];
      const val = /<Data[^>]*>([\s\S]*?)<\/Data>/.exec(c)?.[1] ?? "";
      cells.push(decode(val));
      if (f) formulas.push({ formula: f, cached: decode(val), row: ri });
    }
    rows.push(cells);
  }
  return { cells: rows, formulas };
}

/** R+X：Excel 母表守卫（渲染零改动＋列结构/序号公式缓存/律师列恒空）。 */
export function guardExcelArtifact(fb: FactBase, xml: string): ArtifactViolation[] {
  const v: ArtifactViolation[] = [];
  const { cells, formulas } = parseExcelRows(xml);
  const facts = sortedFacts(fb);
  const header = cells[1] ?? [];
  if (header.length !== MASTER_COLUMNS.length || header.some((h, i) => h !== MASTER_COLUMNS[i])) {
    v.push({ group: "VB-X", code: "X-columns", msg: `母表列头不符（期望 ${MASTER_COLUMNS.join("|")}）` });
  }
  const dataRows = cells.slice(2);
  if (dataRows.length !== facts.length) v.push({ group: "VB-X", code: "X-row-count", msg: `母表数据行 ${dataRows.length} ≠ 事实数 ${facts.length}` });
  facts.forEach((f, i) => {
    const r = dataRows[i];
    if (!r) return;
    if (r[4] !== f.content) v.push({ group: "VB-R", code: "R-content-master", msg: `事实 ${f.factNo} 母表主要内容被改动（母表存全文，省略只归律师）` });
    if (r[1] !== f.dateStr) v.push({ group: "VB-R", code: "R-date-master", msg: `事实 ${f.factNo} 母表日期被改动` });
    if (r[10] !== "" || r[11] !== "") v.push({ group: "VB-X", code: "X-lawyer-columns", msg: `事实 ${f.factNo} 律师回填列交付时须为空（争点/备注由律师在母表内完成）` });
  });
  if (formulas.length !== facts.length) v.push({ group: "VB-X", code: "X-formula-count", msg: `序号公式 ${formulas.length} 条 ≠ 事实数 ${facts.length}` });
  formulas.forEach((f, i) => {
    const fact = facts[i];
    if (!fact) return;
    if (f.formula !== "ROW()-2") v.push({ group: "VB-X", code: "X-formula", msg: `第 ${f.row} 行序号公式「${f.formula}」≠ ROW()-2` });
    if (f.cached !== String(fact.factNo)) v.push({ group: "VB-X", code: "X-cached", msg: `第 ${f.row} 行序号缓存值「${f.cached}」≠ 事实号 ${fact.factNo}` });
  });
  return v;
}

// ── 简表产物解析回读 ──
export interface BriefTextNode { cls: string; x: number; y: number; fontSize: number; text: string; anchor?: string }
export function parseBriefTexts(svg: string): BriefTextNode[] {
  const out: BriefTextNode[] = [];
  for (const m of svg.matchAll(/<text class="([^"]*)" x="(-?[\d.]+)" y="(-?[\d.]+)"(?: font-size="(\d+)")?([^>]*)>([\s\S]*?)<\/text>/g)) {
    const anchor = /text-anchor="(\w+)"/.exec(m[5] ?? "")?.[1];
    out.push({ cls: m[1]!, x: Number(m[2]), y: Number(m[3]), fontSize: Number(m[4] ?? 34), text: decode(m[6]!), anchor });
  }
  return out;
}

/** 简表自检（读产物：版心越界/序号单调/红只用于分组色块/页码/无内部痕迹；内容行按渲染序 zip 比对＋前缀·句读·句号断言）。 */
export function guardBriefArtifacts(fb: FactBase, pages: string[]): ArtifactViolation[] {
  const v: ArtifactViolation[] = [];
  const facts = sortedFacts(fb);
  // 期望内容行（同输入重放裁剪——确定性；断言施加于期望本身，产物与期望逐行比对）
  const expectedLinesByFact = new Map<number, string[]>();
  for (const f of facts) {
    const clip = clipForBrief(f.content, BRIEF_CONTENT_CHARS, BRIEF_MAX_LINES);
    expectedLinesByFact.set(f.factNo, clip.lines);
    if (!clip.isPrefix) v.push({ group: "VB-简表", code: "S-not-prefix", msg: `事实 ${f.factNo} 画进简表的内容不是原文前缀（渲染层改字即断言失败）` });
    if (!clip.stopsAtBoundary) v.push({ group: "VB-简表", code: "S-half-sentence", msg: `事实 ${f.factNo} 裁剪未停在句读上（只验前缀不够——截九个字也是前缀却是半句话）` });
  }
  const expectedAll: Array<{ factNo: number; line: string }> = [];
  for (const vol of [...new Set(facts.map((f) => f.volume))]) {
    for (const f of facts.filter((x) => x.volume === vol)) {
      for (const line of expectedLinesByFact.get(f.factNo) ?? []) expectedAll.push({ factNo: f.factNo, line });
    }
  }
  const right = BRIEF_PAGE.w - BRIEF_MARGIN.right;
  let pageNo = 0;
  const seenNos: number[] = [];
  const productLines: string[] = [];
  for (const svg of pages) {
    pageNo += 1;
    const texts = parseBriefTexts(svg);
    for (const t of texts) {
      const w = measureText(t.text, t.fontSize);
      const left = t.anchor === "end" ? t.x - w : t.x; // 右锚文本按左端量
      if (left < BRIEF_MARGIN.left || left + w > right + 0.5) v.push({ group: "VB-简表", code: "S-overflow", msg: `第 ${pageNo} 页文字越出版心（左=${Math.round(left)} 宽=${Math.round(w)} 版心右界=${right}）：「${t.text.slice(0, 12)}…」` });
      if (t.y < BRIEF_MARGIN.top || t.y > BRIEF_PAGE.h - BRIEF_MARGIN.bottom) v.push({ group: "VB-简表", code: "S-overflow-y", msg: `第 ${pageNo} 页文字纵向越界（y=${t.y}）：「${t.text.slice(0, 12)}…」` });
      if (t.cls !== "content" && BRIEF_BANNED_MARKERS.some((m) => t.text.includes(m))) {
        v.push({ group: "VB-简表", code: "S-internal-marks", msg: `呈报简表出现内部痕迹标注「${t.text}」（此类标注只允许留在 Word/Excel）` });
      }
      if (t.cls === "content") productLines.push(t.text);
      if (t.cls === "no") seenNos.push(Number(t.text));
    }
    if (!texts.some((t) => t.text === `第 ${pageNo} 页`)) v.push({ group: "VB-简表", code: "S-page-no", msg: `第 ${pageNo} 页缺页码` });
    const redFills = [...svg.matchAll(/fill="(#[0-9a-fA-F]{6})"/g)].map((m) => m[1]!.toLowerCase()).filter((c) => isRed(c));
    const groupRectReds = [...svg.matchAll(/<rect class="group"[^>]*fill="(#[0-9a-fA-F]{6})"/g)].map((m) => m[1]!.toLowerCase());
    if (redFills.length !== groupRectReds.length) v.push({ group: "VB-简表", code: "S-red-only-group", msg: `第 ${pageNo} 页红色出现 ${redFills.length} 处但分组色块仅 ${groupRectReds.length} 处（红只用于分组色块）` });
  }
  for (let i = 1; i < seenNos.length; i++) if (seenNos[i]! <= seenNos[i - 1]!) v.push({ group: "VB-简表", code: "S-no-order", msg: `简表序号非单调递增（${seenNos.join(",")}）` });
  if (seenNos.length !== facts.length) v.push({ group: "VB-简表", code: "S-no-count", msg: `简表序号 ${seenNos.length} 个 ≠ 事实数 ${facts.length}` });
  // 产物内容行与期望逐行比对（防渲染层改行/加行/漏行）
  if (productLines.length !== expectedAll.length) v.push({ group: "VB-简表", code: "S-line-count", msg: `简表内容行 ${productLines.length} ≠ 期望 ${expectedAll.length}` });
  for (let i = 0; i < Math.min(productLines.length, expectedAll.length); i++) {
    if (productLines[i] !== expectedAll[i]!.line) {
      v.push({ group: "VB-简表", code: "S-line-tampered", msg: `简表第 ${i + 1} 内容行与裁剪期望不符（产物「${productLines[i]}」）` });
      break;
    }
  }
  // 末行句号收尾（读产物）
  let cursor = 0;
  for (const f of facts) {
    const lines = expectedLinesByFact.get(f.factNo) ?? [];
    cursor += lines.length;
    const paintedLast = productLines[cursor - 1];
    if (paintedLast !== undefined && !/[。！？；]$/.test(paintedLast)) {
      v.push({ group: "VB-简表", code: "S-sentence-end", msg: `事实 ${f.factNo} 简表末行未句读收尾：「${paintedLast.slice(-8)}」` });
    }
  }
  return v;
}

function isRed(hex: string): boolean {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return r > 140 && r > g * 1.8 && r > b * 1.8;
}

/** 确定性对拍（C15 用）：同输入两跑简表渲染逐字节一致。 */
export function briefDeterminism(fb: FactBase): { same: boolean; first: string; second: string } {
  const first = renderBrief(fb).join("");
  const second = renderBrief(fb).join("");
  return { same: first === second, first, second };
}
