// 【功能 #32 整理与尽调】台账内核：底稿批量提取→结构化台账（RE-32 §2 行为 6-10 / §3 台账与回溯）。
// 数据面=「字段键值+依据指针」：每个单元格带依据指针（docId+page+seq+bbox+引文+来源引擎+OCR 版本，
// 对拍 59 四元组口径：页码+坐标+来源引擎+OCR 版本，seq 为额外块序）；
// 提取=LLM+规则双路、规则优先（规则命中即定，规则未中再走 LLM 路；LLM 路由调用方注入，缺省不编造）；
// 台账在线可编辑（编辑与抽取产物共用同一字段模板校验器=三态一源③）；导出 CSV（RFC4180）。
// text_blocks 形状复用 #6 解析管线口径（page/seq/bbox/source/ocrVersion）。
// 纯函数、零 IO；文案自写。

import {
  type FieldDef, type FieldSchema, normalizeFieldSchema, validateFieldSchema, validateRowValues,
} from "./diligenceSchemaModel.js";
import { csvFormulaGuard } from "./tabularExportGuard.js";

export interface TextBlock {
  page: number | null;
  seq: number;
  bbox: number[] | null;
  text: string;
  source: string;
  ocrVersion: string | null;
}

export interface EvidencePointer {
  docId: string;
  docTitle: string;
  page: number | null;
  seq: number;
  bbox: number[] | null;
  quote: string;
  source: string;
  ocrVersion: string | null;
}

export type FieldOrigin = "rule" | "llm" | "manual" | "none";

export interface LedgerCell {
  value: string | null;
  origin: FieldOrigin;
  evidence: EvidencePointer | null;
  note?: string;
}

export interface LedgerRow {
  rowNo: number;
  docId: string;
  docTitle: string;
  cells: Record<string, LedgerCell>;
}

export interface Ledger {
  ledgerId: string;
  caseId: string;
  schemaName: string;
  fields: FieldDef[];
  rows: LedgerRow[];
  status: "open" | "archived";
  createdAt: string;
  updatedAt: string;
}

export interface SourceDoc {
  docId: string;
  docTitle: string;
  blocks: TextBlock[];
}

/** LLM 路注入形状：给定字段与底稿块，返回候选值+其依据块（无把握返回 null；不编造） */
export type LlmFieldFill = (field: FieldDef, doc: SourceDoc) => { value: string; blockIndex?: number } | null;

const SEPARATORS = [":", "：", "∶", " — ", " - ", " "] as const;

function labelLinesOf(name: string): string[] {
  // 规则路的标签形：列名后紧跟分隔符（含全角冒号；空白分隔仅当行首即列名且行内只此一处）
  return SEPARATORS.map((sep) => `${name}${sep}`);
}

// ── 规则路（确定性）：行首「列名+分隔符」取其余部 ──
function rulePick(field: FieldDef, doc: SourceDoc): { value: string; blockIndex: number } | null {
  const labels = labelLinesOf(field.name);
  for (let i = 0; i < doc.blocks.length; i++) {
    const lines = String(doc.blocks[i]!.text ?? "").split(/\r?\n/);
    for (const line of lines) {
      const s = line.trim();
      for (const label of labels) {
        if (s.startsWith(label)) {
          const rest = s.slice(label.length).trim();
          if (rest) return { value: rest, blockIndex: i };
        }
      }
    }
  }
  return null;
}

export interface ExtractOutcome {
  rows: LedgerRow[];
  stats: { docs: number; cellsFilled: number; cellsRule: number; cellsLlm: number; cellsEmpty: number; rejected: string[] };
}

// ── 行为 6/7：批量提取（格式相近底稿 × 用户字段模板）——规则优先、双路互补 ──
export function extractLedgerRows(
  schema: FieldSchema,
  docs: SourceDoc[],
  opts: { llmFill?: LlmFieldFill | null } = {},
): ExtractOutcome {
  const check = validateFieldSchema(schema);
  if (!check.ok) throw new Error(`字段模板不合法：${check.message}`);
  const norm = normalizeFieldSchema(schema);
  const llm = typeof opts.llmFill === "function" ? opts.llmFill : null;
  const rejected: string[] = [];
  const rows: LedgerRow[] = [];
  let cellsFilled = 0, cellsRule = 0, cellsLlm = 0, cellsEmpty = 0;

  docs.forEach((doc, di) => {
    const cells: Record<string, LedgerCell> = {};
    const draftValues: Record<string, unknown> = {};
    for (const field of norm.fields) {
      let picked: { value: string; blockIndex: number; origin: FieldOrigin } | null = null;
      const ruleHit = rulePick(field, doc);
      if (ruleHit) {
        // 规则命中也要过同一校验器（三态一源②：类型/枚举不符=规则误中，弃用不落台账）
        const v = validateRowValues({ name: norm.name, fields: [field] }, { [field.name]: ruleHit.value });
        if (v.ok) picked = { ...ruleHit, origin: "rule" };
      }
      if (!picked && llm) {
        const llmHit = llm(field, doc);
        if (llmHit && llmHit.value != null && String(llmHit.value) !== "") {
          const v = validateRowValues({ name: norm.name, fields: [field] }, { [field.name]: llmHit.value });
          if (v.ok) {
            picked = {
              value: String(llmHit.value),
              blockIndex: typeof llmHit.blockIndex === "number" ? Math.max(0, Math.min(doc.blocks.length - 1, llmHit.blockIndex)) : 0,
              origin: "llm",
            };
          } else {
            rejected.push(`${doc.docId}/${field.name}:LLM 路取值被模板校验拒绝`);
          }
        }
      }
      if (picked) {
        const blk = doc.blocks[picked.blockIndex] ?? doc.blocks[0] ?? null;
        cells[field.name] = {
          value: picked.value,
          origin: picked.origin,
          evidence: blk
            ? {
                docId: doc.docId, docTitle: doc.docTitle, page: blk.page, seq: blk.seq, bbox: blk.bbox,
                quote: String(blk.text ?? "").slice(0, 200), source: blk.source, ocrVersion: blk.ocrVersion,
              }
            : null,
        };
        draftValues[field.name] = picked.value;
        cellsFilled += 1;
        if (picked.origin === "rule") cellsRule += 1; else cellsLlm += 1;
      } else {
        cells[field.name] = { value: null, origin: "none", evidence: null, note: "未提取到（可人工补录）" };
        cellsEmpty += 1;
      }
    }
    rows.push({ rowNo: di + 1, docId: doc.docId, docTitle: doc.docTitle, cells });
  });
  return { rows, stats: { docs: docs.length, cellsFilled, cellsRule, cellsLlm, cellsEmpty, rejected } };
}

// ── 行为 8：字段级依据回溯（点击回溯标记→回原文位置的跳转载荷）──
export function traceOf(ledger: Ledger, rowNo: number, fieldName: string): EvidencePointer & { origin: FieldOrigin; value: string | null } {
  const row = ledger.rows.find((r) => r.rowNo === rowNo);
  if (!row) throw new Error(`台账行不存在：${rowNo}`);
  const cell = row.cells[fieldName];
  if (!cell) throw new Error(`字段不存在：${fieldName}`);
  if (!cell.evidence) throw new Error(`该字段无依据指针（origin=${cell.origin}，值=${String(cell.value)}）`);
  return { ...cell.evidence, origin: cell.origin, value: cell.value };
}

// ── 行为 9：在线编辑（三态一源③：人工值走同一校验器，违例具名拒绝不落台账）──
export function editCell(
  ledger: Ledger, rowNo: number, fieldName: string, value: string, by: string, at: string,
): { ledger: Ledger; origin: "manual" } {
  const who = String(by ?? "").trim();
  if (!who) throw new Error("编辑人不能为空");
  const row = ledger.rows.find((r) => r.rowNo === rowNo);
  if (!row) throw new Error(`台账行不存在：${rowNo}`);
  if (!(fieldName in row.cells)) throw new Error(`字段不存在：${fieldName}`);
  const field = ledger.fields.find((f) => f.name === fieldName);
  if (!field) throw new Error(`字段定义缺失：${fieldName}`);
  const v = validateRowValues({ name: ledger.schemaName, fields: [field] }, { [fieldName]: value });
  if (!v.ok) {
    const first = v.violations[0]!;
    throw new Error(`值被字段模板拒绝（${first.code}）：${first.message}`);
  }
  const rows = ledger.rows.map((r) => {
    if (r.rowNo !== rowNo) return r;
    const prev = r.cells[fieldName]!;
    const next: LedgerCell = {
      value: String(value),
      origin: "manual",
      evidence: prev.evidence, // 依据仍指原文（人工改动不改锚；如需换锚走重提取）
      note: prev.evidence && prev.value !== null && prev.value !== String(value) ? "人工改动，依据仍指原提取位置" : undefined,
    };
    return { ...r, cells: { ...r.cells, [fieldName]: next } };
  });
  return { ledger: { ...ledger, rows, updatedAt: at }, origin: "manual" };
}

// ── 行为 10：导出 CSV（RFC4180：逗号分隔、双引号转义、CRLF 行尾）──
// 公式注入防御（施工单-10 单元一）：用户/文档来源格值与用户可配列名先过共享 sanitizer
// csvFormulaGuard（= + - @ \t \r 起始形前置 '，纯数字金额不拦）再引号化；盘上落盘与
// HTTP 下载直出同源经 ledgerToCsv 一处 choke，不散写。
export function csvQuote(s: string): string {
  const v = String(s ?? "");
  return /[",\r\n]/u.test(v) ? `"${v.replace(/"/gu, '""')}"` : v;
}

export function ledgerToCsv(ledger: Ledger): string {
  const header = ["底稿文件", ...ledger.fields.map((f) => f.name)];
  const lines = [header.map((h) => csvQuote(csvFormulaGuard(h))).join(",")];
  for (const row of ledger.rows) {
    const cells = ledger.fields.map((f) => {
      const c = row.cells[f.name];
      return c && c.value !== null ? String(c.value) : "";
    });
    lines.push([csvQuote(csvFormulaGuard(row.docTitle)), ...cells.map((c) => csvQuote(csvFormulaGuard(c)))].join(","));
  }
  return lines.join("\r\n") + "\r\n";
}
