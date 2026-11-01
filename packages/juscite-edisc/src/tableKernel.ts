// 【功能 #42 电子数据取证】表格/行面内核（RE-42 §2.B/§2.H2/§2.H3，纯模型零 I/O）。
// 行寻址三件套（sourceId, tableName, 行区间）+ 源 fileHash = 可复核引用（B4）；
// 行号从 1 起（B2，两端最小值 1，默认区间 1..50）；金额一律字符串+整数分双轨，禁浮点
// （H2，工作区工程约束 2——十进制字符串→BigInt 分，全程不落 Number 浮点）。
// 表格行列对应关系在解析层保持（H3：补位空单元格，不破坏版面逻辑）。
// 依赖注入式：xlsx 的 zip 解包由调用方（桥）完成传入 entries——本包不依赖桥内 parseZip，
// 保持自有包自包含（出树纪律：桥单向引包，包不回引桥）。

export interface TableRow {
  rowNo: number;
  cells: string[];
}
export interface SheetTable {
  name: string;
  rows: TableRow[];
}
export interface RowRef {
  kind: "rows";
  sourceId: string;
  tableName: string;
  rowStart: number;
  rowEnd: number;
}

export const DEFAULT_ROW_START = 1;
export const DEFAULT_ROW_END = 50;
export const MAX_ROW_SPAN = 500; // 单次行读取上限（防整表倾倒；搜索另有 limit 口径）
/** 整表解析字节上限。超过则拒绝展开，避免把超大 Buffer 扫成单元格。 */
export const TABULAR_PARSE_MAX_BYTES = 150 * 1024 * 1024;

function byteLengthOf(input: string | Uint8Array): number {
  if (typeof input !== "string" && input instanceof Uint8Array) return input.byteLength;
  return new TextEncoder().encode(String(input ?? "")).byteLength;
}

function rejectOversizedTable(bytes: number): void {
  if (bytes > TABULAR_PARSE_MAX_BYTES) {
    const error = new Error(`表格 ${bytes} 字节超过解析上限 ${TABULAR_PARSE_MAX_BYTES}，拒绝展开`);
    (error as Error & { code: string }).code = "PAYLOAD_TOO_LARGE";
    throw error;
  }
}
export const SEARCH_LIMIT_MAX = 200;
export const SEARCH_LIMIT_DEFAULT = 50;

/** 行引用校验：行号从 1 起、区间合法（B2/B4） */
export function normalizeRowRef(ref: Partial<RowRef> | null | undefined): RowRef | null {
  if (!ref || ref.kind !== "rows") return null;
  const rowStart = Math.floor(Number(ref.rowStart ?? DEFAULT_ROW_START));
  const rowEnd = Math.floor(Number(ref.rowEnd ?? DEFAULT_ROW_END));
  if (!Number.isFinite(rowStart) || !Number.isFinite(rowEnd)) return null;
  if (rowStart < 1 || rowEnd < rowStart) return null;
  if (rowEnd - rowStart + 1 > MAX_ROW_SPAN) return null;
  if (!ref.sourceId || !ref.tableName) return null;
  return { kind: "rows", sourceId: String(ref.sourceId), tableName: String(ref.tableName), rowStart, rowEnd };
}

/** 金额双轨（H2）：原文串 + 整数分。仅接受确定性十进制形态（千分逗号可选、两位以内小数），
 *  超两位小数/非数值形态返回 null（不硬猜）。万元口径由调用方语境判断，本函数不做倍率。 */
export function amountDualTrack(raw: string): { text: string; cents: number | null } | null {
  const s = String(raw ?? "").trim();
  if (!s) return null;
  const m = /^(?:[￥¥]\s*)?([+-]?[\d,，]+(?:\.\d{1,2})?)\s*(?:元)?$/.exec(s);
  if (!m || !/\d/.test(m[1])) return null;
  const neg = m[1].startsWith("-");
  const digits = m[1].replace(/^[+-]/, "").replace(/[,，]/g, "");
  const [ip, fp = ""] = digits.split(".");
  if (!/^\d+$/.test(ip) || (fp !== "" && !/^\d{1,2}$/.test(fp))) return null;
  let cents = BigInt(ip) * 100n + BigInt((fp + "00").slice(0, 2));
  if (neg) cents = -cents;
  if (cents > 9007199254740991n || cents < -9007199254740991n) return { text: s, cents: null }; // 超安全整数：原文保留、分数不落
  return { text: s, cents: Number(cents) };
}

/** 行可读串（B3 搜索索引文本）：单元格以“ | ”连接（与 #6 表格行口径一致） */
export function rowText(row: TableRow): string {
  return row.cells.join(" | ");
}

// ── CSV 解析（RFC4180 式状态机：引号/引号内逗号/引号内换行/双引号转义；行列对应保持）──
export function parseCsvTable(text: string | Uint8Array, name = "csv"): SheetTable[] {
  rejectOversizedTable(byteLengthOf(typeof text === "string" || text == null ? String(text ?? "") : text));
  const s = typeof text === "string" || text == null
    ? String(text ?? "")
    : new TextDecoder("utf-8", { fatal: false }).decode(text);
  const rows: TableRow[] = [];
  let cells: string[] = [];
  let cur = "";
  let inQuotes = false;
  let cellOpen = false; // 本字段是否已开始（引号只认字段首引号）
  const pushCell = () => { cells.push(cur); cur = ""; cellOpen = false; };
  const pushRow = () => {
    pushCell();
    if (cells.some((c) => c.trim() !== "")) rows.push({ rowNo: rows.length + 1, cells });
    cells = [];
  };
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (inQuotes) {
      if (c === '"') {
        if (s[i + 1] === '"') { cur += '"'; i++; }
        else inQuotes = false;
      } else cur += c;
      continue;
    }
    if (c === '"' && !cellOpen) { inQuotes = true; continue; }
    if (c === ",") { pushCell(); continue; }
    if (c === "\r") continue;
    if (c === "\n") { pushRow(); continue; }
    cur += c;
    cellOpen = true;
  }
  if (cur !== "" || cells.length || inQuotes) pushRow();
  return [{ name, rows }];
}

// ── XML 实体解码（xlsx 单元格文本）──
function decodeXmlEntities(x: string): string {
  return x
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'")
    .replace(/&#x([0-9a-fA-F]+);/g, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d)))
    .replace(/&amp;/g, "&");
}

function colIndexOf(addr: string): number {
  const m = /^([A-Z]+)(\d+)$/.exec(addr);
  if (!m) return -1;
  let col = 0;
  for (const ch of m[1]) col = col * 26 + (ch.charCodeAt(0) - 64);
  return col - 1;
}

/** xlsx 解析（entries=zip 解包件，来自调用方 parseZip；SheetML 子集：sharedStrings/inlineStr/数字/布尔）。
 *  数字单元格的 <v> 原文串直读——金额不落浮点（H2）。行号取 r 属性，缺行以空行占位保持行号对位。 */
export function parseXlsxTables(entries: Map<string, Buffer>): { sheets: SheetTable[]; notes: string[] } {
  let total = 0;
  for (const buf of entries.values()) total += buf?.byteLength ?? 0;
  rejectOversizedTable(total);
  const notes: string[] = [];
  const get = (p: string) => entries.get(p) ?? entries.get("/" + p) ?? null;
  // 共享串表：一个 <si> 内多个 <t>（rich run）串接
  const shared: string[] = [];
  const sst = get("xl/sharedStrings.xml");
  if (sst) {
    const xml = sst.toString("utf8");
    for (const si of xml.split(/<\/si>/)) {
      let text = "";
      for (const t of si.matchAll(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g)) text += decodeXmlEntities(t[1]);
      if (text || si.includes("<t")) shared.push(text);
    }
    if (!shared.length) notes.push("sharedStrings 存在但未解析出条目");
  }
  // 工作表名与目标：workbook.xml 声明序 + rels 映射
  const wb = get("xl/workbook.xml");
  if (!wb) throw new Error("xlsx 缺少 xl/workbook.xml");
  const relsXml = (get("xl/_rels/workbook.xml.rels") ?? Buffer.alloc(0)).toString("utf8");
  const relTarget = new Map<string, string>();
  for (const r of relsXml.matchAll(/<Relationship\b[^>]*>/g)) {
    const tag = r[0];
    const id = /Id="([^"]+)"/.exec(tag)?.[1];
    const target = /Target="([^"]+)"/.exec(tag)?.[1];
    if (id && target) relTarget.set(id, target.replace(/^\/?xl\//, "").replace(/^\//, ""));
  }
  const sheets: SheetTable[] = [];
  const wbXml = wb.toString("utf8");
  for (const s of wbXml.matchAll(/<sheet\b[^>]*>/g)) {
    const tag = s[0];
    const name = /name="([^"]*)"/.exec(tag)?.[1] ?? `sheet${sheets.length + 1}`;
    const rid = /r:id="([^"]+)"/.exec(tag)?.[1] ?? "";
    const target = relTarget.get(rid);
    if (!target) { notes.push(`工作表 ${name} 缺少关系映射`); continue; }
    const sheetXml = get(`xl/${target}`);
    if (!sheetXml) { notes.push(`工作表 ${name} 的 ${target} 不在包内`); continue; }
    sheets.push(parseSheetXml(name, sheetXml.toString("utf8"), shared));
  }
  if (!sheets.length) throw new Error("xlsx 未解析出任何工作表");
  return { sheets, notes };
}

function parseSheetXml(name: string, xml: string, shared: string[]): SheetTable {
  const rows: TableRow[] = [];
  const maxRowNo = (() => {
    let max = 0;
    for (const r of xml.matchAll(/<row\b[^>]*\br="(\d+)"/g)) max = Math.max(max, Number(r[1]));
    return max;
  })();
  const byRow = new Map<number, TableRow>();
  for (const rm of xml.matchAll(/<row\b[^>]*\br="(\d+)"[^>]*>([\s\S]*?)<\/row>|<row\b[^>]*\br="(\d+)"[^>]*\/>/g)) {
    const rowNo = Number(rm[1] ?? rm[3]);
    const body = rm[2] ?? "";
    const cells: string[] = [];
    for (const cm of body.matchAll(/<c\b([^>]*)>([\s\S]*?)<\/c>|<c\b([^>]*)\/>/g)) {
      const attrs = cm[1] ?? cm[3] ?? "";
      const inner = cm[2] ?? "";
      const addr = /r="([A-Z]+\d+)"/.exec(attrs)?.[1] ?? "";
      const col = colIndexOf(addr);
      const type = /t="([^"]+)"/.exec(attrs)?.[1] ?? "";
      let value = "";
      if (type === "s") {
        const v = /<v>([\s\S]*?)<\/v>/.exec(inner)?.[1] ?? "";
        const i = Number(v);
        value = Number.isInteger(i) && i >= 0 && i < shared.length ? shared[i] : "";
      } else if (type === "inlineStr") {
        value = [...inner.matchAll(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g)].map((t) => decodeXmlEntities(t[1])).join("");
      } else if (type === "b") {
        value = /<v>\s*1\s*<\/v>/.test(inner) ? "TRUE" : "FALSE";
      } else if (type === "str") {
        value = decodeXmlEntities(/<v>([\s\S]*?)<\/v>/.exec(inner)?.[1] ?? "");
      } else {
        value = /<v>([\s\S]*?)<\/v>/.exec(inner)?.[1] ?? ""; // 数字等：原文串直读
      }
      const slot = col >= 0 ? col : cells.length;
      while (cells.length < slot) cells.push(""); // 列对位补空（H3 版面保持）
      cells[slot] = value;
    }
    byRow.set(rowNo, { rowNo, cells });
  }
  for (let no = 1; no <= Math.max(maxRowNo, byRow.size); no++) {
    rows.push(byRow.get(no) ?? { rowNo: no, cells: [] }); // 缺行占位保持行号
  }
  return { name, rows };
}

/** 源画像（B1）：表清单与行数（xlsx/csv 类源按表组织） */
export function profileOfTables(sheets: SheetTable[]): { tables: { name: string; rowCount: number }[] } {
  return { tables: sheets.map((s) => ({ name: s.name, rowCount: s.rows.length })) };
}

/** 行切片（B2）：区间内行（含边界），行号越界的行不出（调用方按存在性报告） */
export function sliceRows(sheets: SheetTable[], tableName: string, rowStart: number, rowEnd: number): TableRow[] | null {
  const sheet = sheets.find((s) => s.name === tableName);
  if (!sheet) return null;
  return sheet.rows.filter((r) => r.rowNo >= rowStart && r.rowNo <= rowEnd);
}
