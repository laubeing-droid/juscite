// 【功能 #42 电子数据取证】桥面服务（RE-42 §2.A-H/§3.2 状态机落码；施工波-20261030）。
// 内核=packages/juscite-edisc（@juscite/edisc，出树自有包：锚/行面/审查纯模型）；
// 本文件只做 I/O 接线（库/文件/HTTP），相对路径消费同 juscite-legal kernel 先例。
// 三类首做（H1 微信记录=PDF 文本层→页/坐标锚+对话段结构化；H2 流水=xlsx/csv 行面；
// H3 表格=xlsx/csv 行面）；治理红线：原件只读（G1，登记后任何路径不回写原件）、
// 归类/批注/更正全部虚拟覆盖层（C1/E3）、元数据更正默认干跑+确认落库+留痕（G2/G3）、
// 无破坏性删除入口（G4）、进场预处理记录可查（G7，preprocess 落源记录）。
// 金额纪律（H2）：行内金额字符串+整数分双轨（内核 amountDualTrack，禁浮点）。
// 人机分工（yuanli chat-recording-evidence 行为参照，NC-SA 零吸收）：工具只定位/锚定/聚合/校验，
// 定档与确认归人——候选一律 suggested，预置审查档一律 doubt 待律师过目。
// 本地工件落 %APPDATA%\Juscite\bridge\cases\<case>\edisc\（红线②：只碰 Juscite 域）。
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { basename, isAbsolute, join } from "node:path";
import { parseZip } from "./skills_service.mjs";
import { MAX_UPLOAD_BYTES, safeFilename, readJsonBody } from "./material_service.mjs";
import {
  extractAnchoredPdfBlocks, parseChatSegments, anchorInvariantOk, PDF_COORD_SYSTEM,
} from "../../packages/juscite-edisc/src/anchorKernel.ts";
import {
  parseCsvTable, parseXlsxTables, profileOfTables, normalizeRowRef, amountDualTrack, rowText,
  DEFAULT_ROW_START, DEFAULT_ROW_END, SEARCH_LIMIT_DEFAULT, SEARCH_LIMIT_MAX,
} from "../../packages/juscite-edisc/src/tableKernel.ts";
import {
  presetReviewFlag, aggregateCandidates, verifyCandidates, buildReviewReport,
  checkFormalElements, normalizeTripleFindings, formatGapLine, ruleSourceLabel, SOURCE_LABEL_DISCIPLINE,
  FACT_EXCLUSIONS, FACT_EXCLUSION_NOTE, FORMAL_ELEMENTS, TRIPLE_ATTRIBUTES, ATTR_CONCLUSIONS,
  GAP_KINDS, RULE_SOURCE_ORIGINS, VERIFY_REQUIRED_MARK,
  FLAG_LEVELS, FLAG_TAGS, PROOF_STRENGTHS,
} from "../../packages/juscite-edisc/src/reviewKernel.ts";
import {
  startOrganize, nextPendingIndex, recordOutcome, applyControl, taskSummary,
  TASK_STATUSES, TASK_CONTROLS,
} from "../../packages/juscite-edisc/src/taskKernel.ts";

const CHAT_TABLE = "聊天记录"; // 聊天段统一入行面（虚拟表名我方自定）：B1/B2/B3 与流水/表格同模
const ANNOTATION_TYPES = new Set(["highlight", "note", "mark"]);
const ANNOTATION_COLOR_DEFAULT = "#FFC24D"; // 默认高亮色自选（不袭对照源缺省值）
const ROW_EXTS = new Set([".xlsx", ".csv"]);

function sha256hex(buf) { return createHash("sha256").update(buf).digest("hex"); }
function randomId(prefix) {
  return `${prefix}_${createHash("sha256").update(`${Math.random()}${Date.now()}${process.pid}`).digest("hex").slice(0, 12)}`;
}
function digestOf(lines) { return sha256hex(Buffer.from(lines.join("\n"), "utf8")); }

// ══════════ DDL（迁移 0020_edisc 单源；bridge_store 与合成自测共用同一份）══════════
export const EDISC_DDL = `
  CREATE TABLE IF NOT EXISTS edisc_sources (
    workspace_key TEXT NOT NULL,
    source_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('chat','statement','table','generic')),
    filename TEXT NOT NULL DEFAULT '',
    origin_path TEXT NOT NULL DEFAULT '',
    stored_path TEXT NOT NULL DEFAULT '',
    file_hash TEXT NOT NULL DEFAULT '',
    format TEXT NOT NULL DEFAULT '',
    byte_size INTEGER NOT NULL DEFAULT 0,
    page_count INTEGER,
    block_count INTEGER,
    tables_json TEXT NOT NULL DEFAULT '[]',
    parse_status TEXT NOT NULL DEFAULT 'pending' CHECK (parse_status IN ('pending','parsing','done','failed')),
    ocr_status TEXT NOT NULL DEFAULT 'not_required' CHECK (ocr_status IN ('not_required','required','hooked')),
    error_code TEXT,
    error_message TEXT,
    preprocess_json TEXT NOT NULL DEFAULT '{}',
    registered_at TEXT NOT NULL,
    registered_by TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (workspace_key, source_id)
  );
  CREATE INDEX IF NOT EXISTS idx_edisc_sources_case ON edisc_sources (workspace_key, case_id, registered_at);
  CREATE TABLE IF NOT EXISTS edisc_blocks (
    workspace_key TEXT NOT NULL,
    source_id TEXT NOT NULL,
    block_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    bbox_json TEXT NOT NULL DEFAULT '[]',
    coord_system TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    engine TEXT NOT NULL DEFAULT 'text_layer',
    ocr_version TEXT,
    file_hash TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (workspace_key, source_id, block_id)
  );
  CREATE INDEX IF NOT EXISTS idx_edisc_blocks_page ON edisc_blocks (workspace_key, source_id, page, seq);
  CREATE TABLE IF NOT EXISTS edisc_rows (
    workspace_key TEXT NOT NULL,
    source_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    row_no INTEGER NOT NULL,
    cells_json TEXT NOT NULL DEFAULT '[]',
    text TEXT NOT NULL DEFAULT '',
    block_id TEXT,
    file_hash TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (workspace_key, source_id, table_name, row_no)
  );
  CREATE TABLE IF NOT EXISTS edisc_chat_messages (
    workspace_key TEXT NOT NULL,
    source_id TEXT NOT NULL,
    msg_index INTEGER NOT NULL,
    sender TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    content TEXT NOT NULL,
    header_block_id TEXT,
    content_block_ids_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (workspace_key, source_id, msg_index)
  );
  CREATE TABLE IF NOT EXISTS edisc_classifications (
    workspace_key TEXT NOT NULL,
    class_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    refs_json TEXT NOT NULL DEFAULT '[]',
    category TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, class_id)
  );
  CREATE INDEX IF NOT EXISTS idx_edisc_class_case ON edisc_classifications (workspace_key, case_id, category);
  CREATE TABLE IF NOT EXISTS edisc_fix_candidates (
    workspace_key TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    class_ids_json TEXT NOT NULL DEFAULT '[]',
    category TEXT NOT NULL DEFAULT '',
    source_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    anchors_json TEXT NOT NULL DEFAULT '[]',
    suggestion_level TEXT NOT NULL DEFAULT 'suggested',
    status TEXT NOT NULL DEFAULT 'suggested' CHECK (status IN ('suggested','confirmed')),
    confirmed_by TEXT,
    confirmed_at TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, candidate_id)
  );
  CREATE TABLE IF NOT EXISTS edisc_review_flags (
    workspace_key TEXT NOT NULL,
    flag_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    target_label TEXT NOT NULL DEFAULT '',
    target_ref_json TEXT NOT NULL DEFAULT '{}',
    kind TEXT NOT NULL DEFAULT 'generic',
    level TEXT NOT NULL CHECK (level IN ('ok','doubt','insufficient')),
    proof_strength TEXT NOT NULL DEFAULT '',
    issues_json TEXT NOT NULL DEFAULT '[]',
    supports_json TEXT NOT NULL DEFAULT '[]',
    weakens_json TEXT NOT NULL DEFAULT '[]',
    lawyer_action TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, flag_id)
  );
  CREATE TABLE IF NOT EXISTS edisc_annotations (
    workspace_key TEXT NOT NULL,
    annotation_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    rects_json TEXT NOT NULL DEFAULT '[]',
    annotation_type TEXT NOT NULL DEFAULT 'highlight',
    color TEXT NOT NULL DEFAULT '#FFC24D',
    text_content TEXT NOT NULL DEFAULT '',
    comment TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, annotation_id)
  );
  CREATE TABLE IF NOT EXISTS edisc_refine_audit (
    workspace_key TEXT NOT NULL,
    audit_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    target_ref TEXT NOT NULL,
    op TEXT NOT NULL,
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    by TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, audit_id)
  );
`;

// ══════════ DDL（迁移 0023_edisc_review 单源：对拍收尾五表——施工波三轮 20261031）══════════
// F1 待证事实 / F2 候选形式六要素 / F4 三性评估 / F6 四类缺口 / G5 长任务生命周期。
// 独立迁移号：0020 已应用库不重放，新表走 0023（bridge_store 与合成自测共用本单源）。
export const EDISC_REVIEW_DDL = `
  CREATE TABLE IF NOT EXISTS edisc_facts (
    workspace_key TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    text TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, fact_id)
  );
  CREATE INDEX IF NOT EXISTS idx_edisc_facts_case ON edisc_facts (workspace_key, case_id, created_at);
  CREATE TABLE IF NOT EXISTS edisc_candidate_formal (
    workspace_key TEXT NOT NULL,
    case_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    elements_json TEXT NOT NULL DEFAULT '{}',
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, candidate_id)
  );
  CREATE TABLE IF NOT EXISTS edisc_triple_reviews (
    workspace_key TEXT NOT NULL,
    review_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    source_id TEXT,
    target_label TEXT NOT NULL DEFAULT '',
    findings_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, review_id)
  );
  CREATE INDEX IF NOT EXISTS idx_edisc_triple_case ON edisc_triple_reviews (workspace_key, case_id, created_at);
  CREATE TABLE IF NOT EXISTS edisc_gaps (
    workspace_key TEXT NOT NULL,
    gap_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('完全缺口','证明力不足','证据链断裂','形式瑕疵')),
    fact_text TEXT NOT NULL DEFAULT '',
    suggestion TEXT NOT NULL,
    source_channel TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL DEFAULT '',
    deadline_note TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, gap_id)
  );
  CREATE INDEX IF NOT EXISTS idx_edisc_gaps_case ON edisc_gaps (workspace_key, case_id, created_at);
  CREATE TABLE IF NOT EXISTS edisc_tasks (
    workspace_key TEXT NOT NULL,
    task_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running','paused','done','canceled')),
    items_json TEXT NOT NULL DEFAULT '[]',
    checkpoint INTEGER NOT NULL DEFAULT 0,
    page_cards_only INTEGER NOT NULL DEFAULT 0,
    stop_on_error INTEGER NOT NULL DEFAULT 0,
    tick_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, task_id)
  );
  CREATE INDEX IF NOT EXISTS idx_edisc_tasks_case ON edisc_tasks (workspace_key, case_id, created_at);
`;

export function createEdiscDao(db) {
  return {
    insertSource: (r) => db.prepare(`
      INSERT INTO edisc_sources (workspace_key, source_id, case_id, kind, filename, origin_path, stored_path,
        file_hash, format, byte_size, page_count, block_count, tables_json, parse_status, ocr_status,
        error_code, error_message, preprocess_json, registered_at, registered_by)
      VALUES (@workspace_key, @source_id, @case_id, @kind, @filename, @origin_path, @stored_path,
        @file_hash, @format, @byte_size, @page_count, @block_count, @tables_json, @parse_status, @ocr_status,
        @error_code, @error_message, @preprocess_json, @registered_at, @registered_by)`).run(r),
    updateSource: (id, cols) => {
      const keys = Object.keys(cols).filter((k) =>
        ["file_hash", "stored_path", "page_count", "block_count", "tables_json", "parse_status", "ocr_status", "error_code", "error_message", "preprocess_json", "byte_size", "format"].includes(k));
      if (!keys.length) return;
      const { workspace_key: ws, ...rest } = cols;
      db.prepare(`UPDATE edisc_sources SET ${keys.map((k) => `${k} = @${k}`).join(", ")} WHERE workspace_key = @ws AND source_id = @id`)
        .run({ ...rest, ws, id });
    },
    getSource: (ws, id) => db.prepare("SELECT * FROM edisc_sources WHERE workspace_key = ? AND source_id = ?").get(ws, id) ?? null,
    getSourceByHash: (ws, caseId, hash, kind) =>
      db.prepare("SELECT * FROM edisc_sources WHERE workspace_key = ? AND case_id = ? AND file_hash = ? AND kind = ? AND file_hash != ''")
        .get(ws, caseId, hash, kind) ?? null,
    listSourcesByCase: (ws, caseId) =>
      db.prepare("SELECT * FROM edisc_sources WHERE workspace_key = ? AND case_id = ? ORDER BY registered_at, source_id").all(ws, caseId),
    replaceBlocks: (ws, sourceId, blocks) => {
      const del = db.prepare("DELETE FROM edisc_blocks WHERE workspace_key = ? AND source_id = ?");
      const ins = db.prepare(`
        INSERT INTO edisc_blocks (workspace_key, source_id, block_id, page, seq, bbox_json, coord_system, text, engine, ocr_version, file_hash)
        VALUES (@workspace_key, @source_id, @block_id, @page, @seq, @bbox_json, @coord_system, @text, @engine, @ocr_version, @file_hash)`);
      db.exec("BEGIN IMMEDIATE");
      try {
        del.run(ws, sourceId);
        for (const b of blocks) ins.run({
          workspace_key: ws, source_id: sourceId, block_id: b.blockId, page: b.page, seq: b.seq,
          bbox_json: JSON.stringify(b.bbox), coord_system: b.coordSystem, text: b.text,
          engine: b.engine, ocr_version: b.ocrVersion, file_hash: b.fileHash,
        });
        db.exec("COMMIT");
      } catch (e) { try { db.exec("ROLLBACK"); } catch { /* ignore */ } throw e; }
    },
    listBlocks: (ws, sourceId, page = null) =>
      db.prepare(page === null
        ? "SELECT * FROM edisc_blocks WHERE workspace_key = ? AND source_id = ? ORDER BY page, seq"
        : "SELECT * FROM edisc_blocks WHERE workspace_key = ? AND source_id = ? AND page = ? ORDER BY seq").all(ws, sourceId, page),
    getBlock: (ws, sourceId, page, seq) =>
      db.prepare("SELECT * FROM edisc_blocks WHERE workspace_key = ? AND source_id = ? AND page = ? AND seq = ?").get(ws, sourceId, page, seq) ?? null,
    replaceRows: (ws, sourceId, tableName, rows) => {
      const del = db.prepare("DELETE FROM edisc_rows WHERE workspace_key = ? AND source_id = ? AND table_name = ?");
      const ins = db.prepare(`
        INSERT INTO edisc_rows (workspace_key, source_id, table_name, row_no, cells_json, text, block_id, file_hash)
        VALUES (@workspace_key, @source_id, @table_name, @row_no, @cells_json, @text, @block_id, @file_hash)`);
      db.exec("BEGIN IMMEDIATE");
      try {
        del.run(ws, sourceId, tableName);
        for (const r of rows) ins.run({
          workspace_key: ws, source_id: sourceId, table_name: tableName, row_no: r.rowNo,
          cells_json: JSON.stringify(r.cells), text: r.text ?? rowText(r), block_id: r.blockId ?? null,
          file_hash: r.fileHash ?? "",
        });
        db.exec("COMMIT");
      } catch (e) { try { db.exec("ROLLBACK"); } catch { /* ignore */ } throw e; }
    },
    getRows: (ws, sourceId, tableName, rowStart, rowEnd) =>
      db.prepare(`SELECT * FROM edisc_rows WHERE workspace_key = ? AND source_id = ? AND table_name = ? AND row_no BETWEEN ? AND ? ORDER BY row_no`)
        .all(ws, sourceId, tableName, rowStart, rowEnd),
    countRows: (ws, sourceId, tableName) =>
      db.prepare("SELECT COUNT(*) AS n, MIN(row_no) AS lo, MAX(row_no) AS hi FROM edisc_rows WHERE workspace_key = ? AND source_id = ? AND table_name = ?")
        .get(ws, sourceId, tableName),
    getRow: (ws, sourceId, tableName, rowNo) =>
      db.prepare("SELECT * FROM edisc_rows WHERE workspace_key = ? AND source_id = ? AND table_name = ? AND row_no = ?").get(ws, sourceId, tableName, rowNo) ?? null,
    searchRows: (ws, sourceIds, q, limit) => {
      const ph = sourceIds.map(() => "?").join(",");
      return db.prepare(`
        SELECT r.*, s.case_id AS case_id, s.filename AS source_filename
        FROM edisc_rows r JOIN edisc_sources s ON s.workspace_key = r.workspace_key AND s.source_id = r.source_id
        WHERE r.workspace_key = ? AND r.source_id IN (${ph}) AND r.text LIKE ? ESCAPE '\\'
        ORDER BY r.source_id, r.table_name, r.row_no LIMIT ?`).all(ws, ...sourceIds, `%${q.replace(/[\\%_]/g, "\\$&")}%`, limit);
    },
    replaceChatMessages: (ws, sourceId, messages) => {
      const del = db.prepare("DELETE FROM edisc_chat_messages WHERE workspace_key = ? AND source_id = ?");
      const ins = db.prepare(`
        INSERT INTO edisc_chat_messages (workspace_key, source_id, msg_index, sender, sent_at, content, header_block_id, content_block_ids_json)
        VALUES (@workspace_key, @source_id, @msg_index, @sender, @sent_at, @content, @header_block_id, @content_block_ids_json)`);
      db.exec("BEGIN IMMEDIATE");
      try {
        del.run(ws, sourceId);
        for (const msg of messages) ins.run({
          workspace_key: ws, source_id: sourceId, msg_index: msg.msgIndex, sender: msg.sender,
          sent_at: msg.sentAt, content: msg.content, header_block_id: msg.headerBlockId,
          content_block_ids_json: JSON.stringify(msg.contentBlockIds),
        });
        db.exec("COMMIT");
      } catch (e) { try { db.exec("ROLLBACK"); } catch { /* ignore */ } throw e; }
    },
    listChatMessages: (ws, sourceId) =>
      db.prepare("SELECT * FROM edisc_chat_messages WHERE workspace_key = ? AND source_id = ? ORDER BY msg_index").all(ws, sourceId),
    insertClassification: (r) => db.prepare(`
      INSERT INTO edisc_classifications (workspace_key, class_id, case_id, source_id, refs_json, category, reason, created_by, created_at)
      VALUES (@workspace_key, @class_id, @case_id, @source_id, @refs_json, @category, @reason, @created_by, @created_at)`).run(r),
    listClassifications: (ws, caseId, sourceId = null) =>
      db.prepare(sourceId === null
        ? "SELECT * FROM edisc_classifications WHERE workspace_key = ? AND case_id = ? ORDER BY created_at, class_id"
        : "SELECT * FROM edisc_classifications WHERE workspace_key = ? AND case_id = ? AND source_id = ? ORDER BY created_at, class_id")
        .all(ws, caseId, ...(sourceId === null ? [] : [sourceId])),
    insertCandidate: (r) => db.prepare(`
      INSERT INTO edisc_fix_candidates (workspace_key, candidate_id, case_id, class_ids_json, category, source_id,
        title, purpose, anchors_json, suggestion_level, status, confirmed_by, confirmed_at, created_at)
      VALUES (@workspace_key, @candidate_id, @case_id, @class_ids_json, @category, @source_id,
        @title, @purpose, @anchors_json, @suggestion_level, @status, @confirmed_by, @confirmed_at, @created_at)`).run(r),
    listCandidates: (ws, caseId) =>
      db.prepare("SELECT * FROM edisc_fix_candidates WHERE workspace_key = ? AND case_id = ? ORDER BY created_at, candidate_id").all(ws, caseId),
    getCandidate: (ws, id) => db.prepare("SELECT * FROM edisc_fix_candidates WHERE workspace_key = ? AND candidate_id = ?").get(ws, id) ?? null,
    updateCandidate: (ws, id, cols) => {
      const keys = Object.keys(cols).filter((k) => ["title", "purpose", "status", "confirmed_by", "confirmed_at"].includes(k));
      if (!keys.length) return;
      db.prepare(`UPDATE edisc_fix_candidates SET ${keys.map((k) => `${k} = @${k}`).join(", ")} WHERE workspace_key = @ws AND candidate_id = @id`)
        .run({ ...cols, ws, id });
    },
    insertFlag: (r) => db.prepare(`
      INSERT INTO edisc_review_flags (workspace_key, flag_id, case_id, target_label, target_ref_json, kind, level,
        proof_strength, issues_json, supports_json, weakens_json, lawyer_action, tags_json, created_by, created_at)
      VALUES (@workspace_key, @flag_id, @case_id, @target_label, @target_ref_json, @kind, @level,
        @proof_strength, @issues_json, @supports_json, @weakens_json, @lawyer_action, @tags_json, @created_by, @created_at)`).run(r),
    listFlags: (ws, caseId) =>
      db.prepare("SELECT * FROM edisc_review_flags WHERE workspace_key = ? AND case_id = ? ORDER BY created_at, flag_id").all(ws, caseId),
    insertAnnotation: (r) => db.prepare(`
      INSERT INTO edisc_annotations (workspace_key, annotation_id, case_id, source_id, page_number, rects_json,
        annotation_type, color, text_content, comment, created_by, created_at)
      VALUES (@workspace_key, @annotation_id, @case_id, @source_id, @page_number, @rects_json,
        @annotation_type, @color, @text_content, @comment, @created_by, @created_at)`).run(r),
    listAnnotations: (ws, caseId, sourceId = null, page = null) => {
      const conds = ["workspace_key = ?", "case_id = ?"];
      const args = [ws, caseId];
      if (sourceId !== null) { conds.push("source_id = ?"); args.push(sourceId); }
      if (page !== null) { conds.push("page_number = ?"); args.push(page); }
      return db.prepare(`SELECT * FROM edisc_annotations WHERE ${conds.join(" AND ")} ORDER BY page_number, created_at`).all(...args);
    },
    insertRefineAudit: (r) => db.prepare(`
      INSERT INTO edisc_refine_audit (workspace_key, audit_id, case_id, target_ref, op, before_json, after_json, reason, by, at)
      VALUES (@workspace_key, @audit_id, @case_id, @target_ref, @op, @before_json, @after_json, @reason, @by, @at)`).run(r),
    listRefineAudit: (ws, caseId) =>
      db.prepare("SELECT * FROM edisc_refine_audit WHERE workspace_key = ? AND case_id = ? ORDER BY at, audit_id").all(ws, caseId),
    // ── 迁移 0023_edisc_review 五表（对拍收尾：F1/F2/F4/F6/G5）──
    insertFact: (r) => db.prepare(`
      INSERT INTO edisc_facts (workspace_key, fact_id, case_id, text, note, created_by, created_at)
      VALUES (@workspace_key, @fact_id, @case_id, @text, @note, @created_by, @created_at)`).run(r),
    listFacts: (ws, caseId) =>
      db.prepare("SELECT * FROM edisc_facts WHERE workspace_key = ? AND case_id = ? ORDER BY created_at, fact_id").all(ws, caseId),
    upsertFormal: (r) => db.prepare(`
      INSERT INTO edisc_candidate_formal (workspace_key, case_id, candidate_id, elements_json, updated_by, updated_at)
      VALUES (@workspace_key, @case_id, @candidate_id, @elements_json, @updated_by, @updated_at)
      ON CONFLICT (workspace_key, candidate_id) DO UPDATE SET
        elements_json = excluded.elements_json, updated_by = excluded.updated_by, updated_at = excluded.updated_at`).run(r),
    listFormalByCase: (ws, caseId) =>
      db.prepare("SELECT * FROM edisc_candidate_formal WHERE workspace_key = ? AND case_id = ?").all(ws, caseId),
    insertTriple: (r) => db.prepare(`
      INSERT INTO edisc_triple_reviews (workspace_key, review_id, case_id, source_id, target_label, findings_json, created_by, created_at)
      VALUES (@workspace_key, @review_id, @case_id, @source_id, @target_label, @findings_json, @created_by, @created_at)`).run(r),
    listTriples: (ws, caseId) =>
      db.prepare("SELECT * FROM edisc_triple_reviews WHERE workspace_key = ? AND case_id = ? ORDER BY created_at, review_id").all(ws, caseId),
    insertGap: (r) => db.prepare(`
      INSERT INTO edisc_gaps (workspace_key, gap_id, case_id, kind, fact_text, suggestion, source_channel, difficulty, deadline_note, created_by, created_at)
      VALUES (@workspace_key, @gap_id, @case_id, @kind, @fact_text, @suggestion, @source_channel, @difficulty, @deadline_note, @created_by, @created_at)`).run(r),
    listGaps: (ws, caseId) =>
      db.prepare("SELECT * FROM edisc_gaps WHERE workspace_key = ? AND case_id = ? ORDER BY created_at, gap_id").all(ws, caseId),
    insertTask: (r) => db.prepare(`
      INSERT INTO edisc_tasks (workspace_key, task_id, case_id, status, items_json, checkpoint, page_cards_only, stop_on_error, tick_ms, created_at, updated_at)
      VALUES (@workspace_key, @task_id, @case_id, @status, @items_json, @checkpoint, @page_cards_only, @stop_on_error, @tick_ms, @created_at, @updated_at)`).run(r),
    updateTask: (ws, id, cols) => {
      const keys = Object.keys(cols).filter((k) => ["status", "items_json", "checkpoint", "updated_at"].includes(k));
      if (!keys.length) return;
      db.prepare(`UPDATE edisc_tasks SET ${keys.map((k) => `${k} = @${k}`).join(", ")} WHERE workspace_key = @ws AND task_id = @id`)
        .run({ ...cols, ws, id });
    },
    getTask: (ws, id) => db.prepare("SELECT * FROM edisc_tasks WHERE workspace_key = ? AND task_id = ?").get(ws, id) ?? null,
    listTasksByCase: (ws, caseId) =>
      db.prepare("SELECT * FROM edisc_tasks WHERE workspace_key = ? AND case_id = ? ORDER BY created_at DESC, task_id").all(ws, caseId),
  };
}

// ══════════ 服务（I/O 接线 + HTTP 面 /api/edisc/*）══════════
export function createEdiscService({ dao, caseExists, root, workspaceKey, authFilePath, now, log, auditWrite }) {
  const iso = () => (typeof now === "function" ? now() : new Date().toISOString());
  const noop = typeof log === "function" ? log : () => {};

  function localAuthOk(req) {
    try {
      if (!authFilePath || !existsSync(authFilePath)) return true;
      const token = readFileSync(authFilePath, "utf-8").trim();
      if (!token) return true;
      return req.headers["x-juscite-token"] === token;
    } catch { return false; }
  }

  function requireCase(caseId) {
    if (!caseId || typeof caseId !== "string") { const e = new Error("caseId 不能为空"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    if (!caseExists(caseId)) { const e = new Error(`案件不存在：${caseId}`); e.http = 404; e.code = "CASE_NOT_FOUND"; throw e; }
  }
  function requireSource(id) {
    const row = dao.getSource(workspaceKey, id);
    if (!row) { const e = new Error("电子数据源不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
    return row;
  }

  function sourceProto(row) {
    let preprocess = {};
    try { preprocess = JSON.parse(row.preprocess_json || "{}"); } catch { preprocess = {}; }
    let tables = [];
    try { tables = JSON.parse(row.tables_json || "[]"); } catch { tables = []; }
    return {
      id: row.source_id, caseId: row.case_id, kind: row.kind, filename: row.filename,
      originPath: row.origin_path, fileHash: row.file_hash, format: row.format, byteSize: row.byte_size,
      pageCount: row.page_count ?? null, blockCount: row.block_count ?? null, tables,
      parseStatus: row.parse_status, ocrStatus: row.ocr_status,   // A4 三态底座：hash/parse/ocr
      error: row.error_code ? { code: row.error_code, message: row.error_message ?? "" } : null,
      preprocess,                                                    // G7 进场预处理记录可查
      registeredAt: row.registered_at, registeredBy: row.registered_by,
    };
  }

  // ── A2 单源登记（默认 computeHash=true+parse=true；与 A1 粗扫两档）──
  // bytes 缺省（scan 粗扫态）= 只落元数据不拷贝不解析；入册态=拷贝原件到 Juscite 域（G1 原件只读）。
  function registerSource({ caseId, kind = "generic", filename, bytes, originPath = "", computeHash = true, parse = true, registeredBy = "律师" }) {
    requireCase(caseId);
    if (!["chat", "statement", "table", "generic"].includes(kind)) {
      const e = new Error(`未知的电子数据类型：${kind}`); e.http = 400; e.code = "BAD_REQUEST"; throw e;
    }
    const buf = bytes ?? Buffer.alloc(0);
    if (buf.length > MAX_UPLOAD_BYTES) { const e = new Error("文件超过 100MB 上限"); e.http = 413; e.code = "PAYLOAD_TOO_LARGE"; throw e; }
    const fname = safeFilename(filename || "电子数据源");
    const ext = fname.includes(".") ? fname.slice(fname.lastIndexOf(".")).toLowerCase() : "";
    const hash = computeHash && buf.length ? sha256hex(buf) : "";
    if (hash) {
      const dup = dao.getSourceByHash(workspaceKey, caseId, hash, kind);
      if (dup) return { ...sourceProto(dup), deduplicated: true };
    }
    const id = randomId("esrc");
    const ts = iso();
    let storedPath = "";
    if (buf.length) {
      const dir = join(root, caseId, "edisc", "files");
      mkdirSync(dir, { recursive: true });
      storedPath = join(dir, `${id}_${fname}`);
      writeFileSync(storedPath, buf); // 原件落 Juscite 域；此后任何路径不回写（G1）
    }
    dao.insertSource({
      workspace_key: workspaceKey, source_id: id, case_id: caseId, kind,
      filename: fname, origin_path: originPath || "", stored_path: storedPath,
      file_hash: hash, format: ext, byte_size: buf.length, page_count: null, block_count: null,
      tables_json: "[]", parse_status: "pending", ocr_status: "not_required",
      error_code: null, error_message: null, preprocess_json: "{}",
      registered_at: ts, registered_by: registeredBy,
    });
    if (!parse || !buf.length) {
      auditWrite("edisc.source.register", id, { kind, filename: fname, hashed: Boolean(hash), parse: false });
      return sourceProto(dao.getSource(workspaceKey, id));
    }
    dao.updateSource(id, { workspace_key: workspaceKey, parse_status: "parsing" });
    let out;
    try {
      out = parseSource({ id, caseId, kind, fname, ext, buf, hash, registeredBy });
    } catch (e) {
      dao.updateSource(id, {
        workspace_key: workspaceKey, parse_status: "failed",
        error_code: e?.code ?? "PARSE_FAILED", error_message: e?.message ?? String(e),
      });
      auditWrite("edisc.source.register", id, { kind, filename: fname, hashed: Boolean(hash), parse: "failed", code: e?.code ?? "PARSE_FAILED" });
      return sourceProto(dao.getSource(workspaceKey, id));
    }
    auditWrite("edisc.source.register", id, { kind, filename: fname, hashed: Boolean(hash), parse: out.parseStatus, blocks: out.blockCount ?? 0 });
    return sourceProto(dao.getSource(workspaceKey, id));
  }

  // ── 解析分派（RE-42 §3.2：进场→解析/OCR→块锚/行索引落库；G5 pageCardsOnly=只产页卡/块锚）──
  function parseSource({ id, caseId, kind, fname, ext, buf, hash, registeredBy: _by, pageCardsOnly = false }) {
    const preprocess = { warnings: [], coordSystem: null };
    if (kind === "chat" && ext === ".pdf") {
      const { blocks, pageCount } = extractAnchoredPdfBlocks(buf, hash);   // E1 四元组锚
      if (!blocks.length) {
        const e = new Error("未检出可定位的文本层（扫描件/图片需 OCR，本版未启用本地 OCR）");
        e.code = "NEEDS_OCR";
        dao.updateSource(id, { workspace_key: workspaceKey, ocr_status: "required" });
        throw e;
      }
      dao.replaceBlocks(workspaceKey, id, blocks);
      if (pageCardsOnly) {
        // G5 纯页卡档：只落页卡/块锚，跳过对话段结构化与行面；重跑旧源时清掉既有行面（档位如实）
        dao.replaceChatMessages(workspaceKey, id, []);
        dao.replaceRows(workspaceKey, id, CHAT_TABLE, []);
        preprocess.coordSystem = PDF_COORD_SYSTEM;
        preprocess.pageCardsOnly = true;
        dao.updateSource(id, {
          workspace_key: workspaceKey, parse_status: "done", page_count: pageCount, block_count: blocks.length,
          tables_json: "[]", preprocess_json: JSON.stringify(preprocess),
        });
        return { parseStatus: "done", blockCount: blocks.length };
      }
      const { messages, unstructuredBlockIds } = parseChatSegments(blocks); // H1 对话要素结构化
      dao.replaceChatMessages(workspaceKey, id, messages);
      const rows = messages.map((msg, i) => ({
        rowNo: i + 1, cells: [msg.sentAt, msg.sender, msg.content],
        text: rowText({ cells: [msg.sentAt, msg.sender, msg.content] }), blockId: msg.anchorBlockId, fileHash: hash,
      }));
      dao.replaceRows(workspaceKey, id, CHAT_TABLE, rows);                 // 聊天段入行面（统一寻址）
      preprocess.coordSystem = PDF_COORD_SYSTEM;
      preprocess.unstructuredBlockLines = unstructuredBlockIds.length;
      preprocess.chatMessages = messages.length;
      if (unstructuredBlockIds.length) preprocess.warnings.push(`${unstructuredBlockIds.length} 行未能结构化为对话段，已按原文块保留`);
      dao.updateSource(id, {
        workspace_key: workspaceKey, parse_status: "done", page_count: pageCount, block_count: blocks.length,
        tables_json: JSON.stringify([{ name: CHAT_TABLE, rowCount: rows.length }]), preprocess_json: JSON.stringify(preprocess),
      });
      return { parseStatus: "done", blockCount: blocks.length };
    }
    if ((kind === "statement" || kind === "table") && ROW_EXTS.has(ext)) {
      let sheets;
      if (ext === ".csv") {
        const text = new TextDecoder("utf-8", { fatal: false }).decode(buf); // CSV：编码直读（BOM 容忍）
        preprocess.encoding = "utf-8";
        sheets = parseCsvTable(text, fname.replace(/\.csv$/i, ""));
      } else {
        let entries;
        try { entries = parseZip(buf); } catch (e) { e.code = "DAMAGED"; throw e; }
        try {
          const r = parseXlsxTables(entries);
          sheets = r.sheets;
          preprocess.sheetNotes = r.notes;
        } catch (e) { e.code = "DAMAGED"; throw e; }
      }
      for (const sheet of sheets) {
        const rows = sheet.rows.map((r) => ({ ...r, fileHash: hash }));
        dao.replaceRows(workspaceKey, id, sheet.name, rows);
      }
      const tables = profileOfTables(sheets).tables;                       // B1 表清单（金额双轨在读取面按行现算）
      dao.updateSource(id, {
        workspace_key: workspaceKey, parse_status: "done",
        tables_json: JSON.stringify(tables), preprocess_json: JSON.stringify(preprocess), block_count: 0,
      });
      return { parseStatus: "done", blockCount: 0 };
    }
    if (kind === "chat") {
      const e = new Error("聊天记录首版支持带文本层的 PDF 导出件；截图/图片需 OCR，本版未启用本地 OCR，请改用可复制文字的导出 PDF");
      e.code = "NEEDS_OCR";
      dao.updateSource(id, { workspace_key: workspaceKey, ocr_status: "required" });
      throw e;
    }
    if (ext === ".pdf") {
      const { blocks, pageCount } = extractAnchoredPdfBlocks(buf, hash);   // 通用进场：页卡+块锚路径
      dao.replaceBlocks(workspaceKey, id, blocks);
      preprocess.coordSystem = PDF_COORD_SYSTEM;
      if (kind === "statement") preprocess.warnings.push("PDF 流水的行面暂不提供，本版以页卡+块锚登记（行面后补）");
      dao.updateSource(id, {
        workspace_key: workspaceKey, parse_status: "done", page_count: pageCount, block_count: blocks.length,
        preprocess_json: JSON.stringify(preprocess),
      });
      return { parseStatus: "done", blockCount: blocks.length };
    }
    const e = new Error(`该类型与格式的组合暂不支持解析（${kind} / ${ext || "无扩展名"}）：流水与表格请用 xlsx/csv，聊天记录请用带文本层的 PDF`);
    e.code = "UNSUPPORTED_FORMAT";
    throw e;
  }

  // ── A1 目录扫描（默认不哈希不解析=粗扫档；逐件失败隔离）──
  function scanDirectory({ caseId, rootPath, computeHash = false }) {
    requireCase(caseId);
    if (!rootPath || !isAbsolute(rootPath)) { const e = new Error("rootPath 必须是绝对路径"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    let entries;
    try {
      const st = statSync(rootPath);
      if (!st.isDirectory()) { const e2 = new Error("rootPath 不是目录"); e2.http = 400; e2.code = "BAD_REQUEST"; throw e2; }
      entries = readdirSync(rootPath, { withFileTypes: true }).filter((d) => d.isFile());
    } catch (e2) {
      if (e2?.http) throw e2;
      const e = new Error("目录不存在或不可读"); e.http = 404; e.code = "NOT_FOUND"; throw e;
    }
    const items = [];
    for (const f of entries) {
      const name = f.name;
      const ext = name.includes(".") ? name.slice(name.lastIndexOf(".")).toLowerCase() : "";
      const allowed = [".pdf", ".xlsx", ".csv", ".png", ".jpg", ".jpeg"];
      if (!allowed.includes(ext)) continue;
      let bytes = Buffer.alloc(0);
      try {
        const p = join(rootPath, name);
        const st = statSync(p);
        if (st.size > MAX_UPLOAD_BYTES) { items.push({ filename: name, status: "skipped", reason: "超过 100MB 上限" }); continue; }
        bytes = computeHash ? readFileSync(p) : Buffer.alloc(0);
        if (!computeHash) {
          // 粗扫档：只登记路径元数据（byteSize 记实际值，内容不读不入域）
          const id = randomId("esrc");
          const kind = ext === ".pdf" ? "chat" : ext === ".xlsx" || ext === ".csv" ? "table" : "chat";
          dao.insertSource({
            workspace_key: workspaceKey, source_id: id, case_id: caseId, kind,
            filename: safeFilename(name), origin_path: p, stored_path: "",
            file_hash: "", format: ext, byte_size: st.size, page_count: null, block_count: null,
            tables_json: "[]", parse_status: "pending",
            ocr_status: ext === ".png" || ext === ".jpg" || ext === ".jpeg" ? "required" : "not_required",
            error_code: null, error_message: null, preprocess_json: "{}",
            registered_at: iso(), registered_by: "律师",
          });
          items.push({ sourceId: id, filename: name, status: "registered", hashed: false });
          continue;
        }
        const proto = registerSource({
          caseId, kind: ext === ".pdf" ? "chat" : "table", filename: name, bytes, originPath: join(rootPath, name),
          computeHash: true, parse: true,
        });
        items.push({ sourceId: proto.id, filename: name, status: proto.parseStatus, hashed: true, error: proto.error });
      } catch (e) {
        items.push({ filename: name, status: "failed", error: { code: e?.code ?? "SCAN_FAILED", message: e?.message ?? String(e) } });
      }
    }
    auditWrite("edisc.source.scan", caseId, { rootPath: basename(rootPath), count: items.length, hashed: Boolean(computeHash) });
    return { items, summary: { ok: items.filter((x) => x.status === "registered" || x.status === "done").length, failed: items.filter((x) => x.status === "failed").length } };
  }

  const listSources = (caseId) => {
    requireCase(caseId);
    return { items: dao.listSourcesByCase(workspaceKey, caseId).map(sourceProto) };
  };

  const getSourceDetail = (id) => sourceProto(requireSource(id));

  // ── B1 源画像（表清单/页与块统计）──
  function sourceProfile(id) {
    const row = requireSource(id);
    const tables = JSON.parse(row.tables_json || "[]");
    return {
      id: row.source_id, kind: row.kind, format: row.format,
      fileHash: row.file_hash,
      tables,                                     // xlsx/csv：表清单+行数
      pages: row.page_count ?? null,              // pdf：页数/块数/坐标系
      blocks: row.block_count ?? null,
      coordSystem: row.kind === "chat" || row.format === ".pdf" ? PDF_COORD_SYSTEM : null,
      chatMessages: row.kind === "chat" ? dao.listChatMessages(workspaceKey, id).length : null,
    };
  }

  // ── B2 行读取（默认 1..50，行号从 1 起；区间即引用地址）──
  function readRows(id, tableName, rowStart = DEFAULT_ROW_START, rowEnd = DEFAULT_ROW_END) {
    const row = requireSource(id);
    if (row.parse_status !== "done") {
      const e = new Error(`源未完成解析（当前 ${row.parse_status}${row.error_code ? `：${row.error_message}` : ""}），无行面可读`);
      e.http = 409; e.code = "NOT_PARSED"; throw e;
    }
    const ref = normalizeRowRef({ kind: "rows", sourceId: id, tableName, rowStart, rowEnd });
    if (!ref) { const e = new Error("行区间不合法（行号从 1 起，单次至多 500 行）"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const rows = dao.getRows(workspaceKey, id, ref.tableName, ref.rowStart, ref.rowEnd);
    return {
      sourceId: id, tableName: ref.tableName, rowStart: ref.rowStart, rowEnd: ref.rowEnd,
      fileHash: row.file_hash,                                            // B4 三件套+源哈希=可复核引用
      rows: rows.map((r) => ({
        rowNo: r.row_no, cells: JSON.parse(r.cells_json || "[]"), text: r.text,
        blockId: r.block_id ?? null,                                      // 聊天行回链页/坐标锚
        amounts: JSON.parse(r.cells_json || "[]").map((c, i) => ({ col: i, ...amountDualTrack(c) }))
          .filter((a) => a.cents !== undefined || /^[￥¥]/.test(String(a.text))),
      })),
    };
  }

  // ── B3 行搜索（limit≤200 默认 50；可按案件/源收窄；命中=定位线索）──
  function searchRows({ caseId, sourceId, q, limit = SEARCH_LIMIT_DEFAULT }) {
    requireCase(caseId);
    const query = String(q ?? "").trim();
    if (!query) return { hits: [], mode: "empty" };
    const lim = Math.max(1, Math.min(SEARCH_LIMIT_MAX, Math.floor(Number(limit) || SEARCH_LIMIT_DEFAULT)));
    const sourceIds = sourceId
      ? [requireSource(sourceId).source_id]
      : dao.listSourcesByCase(workspaceKey, caseId).filter((s) => s.parse_status === "done").map((s) => s.source_id);
    if (!sourceIds.length) return { hits: [], mode: "no-parsed-source" };
    const hits = dao.searchRows(workspaceKey, sourceIds, query, lim).map((h) => ({
      sourceId: h.source_id, sourceFilename: h.source_filename, tableName: h.table_name,
      rowNo: h.row_no, text: h.text, blockId: h.block_id ?? null,
      ref: { kind: "rows", sourceId: h.source_id, tableName: h.table_name, rowStart: h.row_no, rowEnd: h.row_no },
    }));
    return {
      hits, mode: "like",
      limit: lim,
      note: "检索命中仅为定位线索，不构成取证结论；作为取证引用前，请经页卡或行读取面覆盖阅读命中区域。", // E5 两段纪律（自写）
    };
  }

  // ── C1 行级虚拟归类（覆盖层，不写回源文件；C3 操作者留名）──
  function classifyRows({ caseId, refs, category, reason = "", createdBy = "律师" }) {
    requireCase(caseId);
    const cat = String(category ?? "").trim();
    if (!cat) { const e = new Error("category 不能为空"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    if (!Array.isArray(refs) || !refs.length) { const e = new Error("refs 不能为空"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const norm = [];
    for (const r of refs) {
      const ref = normalizeRowRef(r);
      if (!ref) { const e = new Error(`行引用不合法：${JSON.stringify(r)}`); e.http = 400; e.code = "BAD_REF"; throw e; }
      const src = requireSource(ref.sourceId);
      if (src.case_id !== caseId) { const e = new Error(`源 ${ref.sourceId} 不属于案件 ${caseId}`); e.http = 400; e.code = "BAD_REF"; throw e; }
      if (!src.file_hash) { const e = new Error(`源 ${ref.sourceId} 尚未入册哈希（粗扫态），先完成登记解析再归类`); e.http = 409; e.code = "NOT_HASHED"; throw e; }
      const count = dao.countRows(workspaceKey, ref.sourceId, ref.tableName).n;
      if (ref.rowEnd > count) { const e = new Error(`${ref.tableName} 共 ${count} 行，引用越界（第 ${ref.rowEnd} 行不存在）`); e.http = 400; e.code = "BAD_REF"; throw e; }
      norm.push(ref);
    }
    const id = randomId("ecls");
    dao.insertClassification({
      workspace_key: workspaceKey, class_id: id, case_id: caseId,
      source_id: norm[0].sourceId, refs_json: JSON.stringify(norm), category: cat,
      reason: String(reason ?? ""), created_by: createdBy, created_at: iso(),
    });
    auditWrite("edisc.classify", id, { caseId, category: cat, refs: norm.length, by: createdBy });
    return classificationProto(dao.listClassifications(workspaceKey, caseId).find((c) => c.class_id === id));
  }

  function classificationProto(row) {
    return {
      id: row.class_id, caseId: row.case_id, sourceId: row.source_id,
      refs: JSON.parse(row.refs_json || "[]"), category: row.category, reason: row.reason,
      createdBy: row.created_by, createdAt: row.created_at,
    };
  }
  const listClassifications = (caseId, sourceId = null) => {
    requireCase(caseId);
    return { items: dao.listClassifications(workspaceKey, caseId, sourceId ?? null).map(classificationProto) };
  };

  // ── D1 候选证据清单（只聚合已人工归类行；建议档不自动入正式目录）──
  function generateFixList({ caseId, category = null }) {
    requireCase(caseId);
    const classes = dao.listClassifications(workspaceKey, caseId)
      .filter((c) => (category ? c.category === category : true));
    if (!classes.length) { const e = new Error("该案件尚无归类行，先归类再生成候选清单"); e.http = 409; e.code = "NO_CLASSIFICATION"; throw e; }
    const srcNames = new Map(dao.listSourcesByCase(workspaceKey, caseId).map((s) => [s.source_id, s.filename]));
    // 归类可跨源引用（refs 各自带 sourceId），而库行 source_id 只记首引源——聚合前按 ref 自身源
    // 拆分，防「甲源的候选挂乙源的行锚」（校验会以行不存在可读报错，20261031 UI 探针实测抓到）。
    const drafts = aggregateCandidates(classes.flatMap((c) => {
      const bySrc = new Map();
      for (const r of JSON.parse(c.refs_json || "[]")) {
        const sid = r.sourceId ?? c.source_id;
        if (!bySrc.has(sid)) bySrc.set(sid, []);
        bySrc.get(sid).push(r);
      }
      return [...bySrc.entries()].map(([sid, refs]) => ({
        classId: c.class_id, sourceId: sid, sourceName: srcNames.get(sid) ?? sid,
        category: c.category, refs,
      }));
    }));
    const existing = new Set(dao.listCandidates(workspaceKey, caseId)
      .map((c) => `${c.category}\u0000${c.source_id}\u0000${c.anchors_json}`));
    const created = [];
    for (const d of drafts) {
      const anchors = d.anchors.map((a) => {
        const rows = dao.getRows(workspaceKey, a.sourceId, a.rows.tableName, a.rows.rowStart, a.rows.rowEnd);
        return { ...a, digest: digestOf(rows.map((r) => r.text)) };   // 回跳快照：落款时行文摘要
      });
      const anchorsJson = JSON.stringify(anchors);
      const key = `${d.category}\u0000${d.sourceId}\u0000${anchorsJson}`;
      if (existing.has(key)) continue;
      const id = randomId("efx");
      dao.insertCandidate({
        workspace_key: workspaceKey, candidate_id: id, case_id: caseId,
        class_ids_json: JSON.stringify(d.classIds), category: d.category, source_id: d.sourceId,
        title: d.title, purpose: "", anchors_json: anchorsJson,
        suggestion_level: "suggested", status: "suggested", confirmed_by: null, confirmed_at: null, created_at: iso(),
      });
      created.push(id);
    }
    auditWrite("edisc.fixlist.generate", caseId, { created: created.length, category: category ?? null });
    return { created: created.map((id) => candidateProto(dao.getCandidate(workspaceKey, id))), suggestionNote: "候选清单由已人工归类的行生成，属建议；未经律师确认不得进入正式证据目录。" };
  }

  function candidateProto(row, formalMap = null) {
    const formalRow = formalMap ? formalMap.get(row.candidate_id) : null;
    let formal = null;
    if (formalRow) {
      let elements = {};
      try { elements = JSON.parse(formalRow.elements_json || "{}"); } catch { elements = {}; }
      formal = { elements, check: checkFormalElements(elements), updatedBy: formalRow.updated_by, updatedAt: formalRow.updated_at };
    }
    return {
      id: row.candidate_id, caseId: row.case_id, category: row.category, sourceId: row.source_id,
      classIds: JSON.parse(row.class_ids_json || "[]"), title: row.title, purpose: row.purpose,
      anchors: JSON.parse(row.anchors_json || "[]"), suggestionLevel: row.suggestion_level,
      status: row.status, confirmedBy: row.confirmed_by, confirmedAt: row.confirmed_at, createdAt: row.created_at,
      formal,                                                               // F2 形式六要素（未登记=null）
    };
  }
  const listFixLists = (caseId) => {
    requireCase(caseId);
    const formalMap = new Map(dao.listFormalByCase(workspaceKey, caseId).map((r) => [r.candidate_id, r]));
    return { items: dao.listCandidates(workspaceKey, caseId).map((c) => candidateProto(c, formalMap)) };
  };

  // ── D2/G6 校验（清单项↔源行/页锚一一对应 + 回跳摘要一致；失败可读返回）──
  function verifyFixList(caseId) {
    requireCase(caseId);
    const candidates = dao.listCandidates(workspaceKey, caseId);
    const resolve = {
      sourceHash: (sourceId) => {
        const s = dao.getSource(workspaceKey, sourceId);
        return s ? { fileHash: s.file_hash } : null;
      },
      rowExists: (sourceId, tableName, rowNo) => {
        const r = dao.getRow(workspaceKey, sourceId, tableName, rowNo);
        return r ? { fileHash: r.file_hash } : null;
      },
      blockExists: (sourceId, page, seq) => {
        const b = dao.getBlock(workspaceKey, sourceId, page, seq);
        return b ? { fileHash: b.file_hash } : null;
      },
    };
    const base = verifyCandidates(
      candidates.map((c) => ({ candidateId: c.candidate_id, title: c.title, anchors: JSON.parse(c.anchors_json || "[]"), status: c.status })),
      resolve,
      () => null,
      [],
    );
    // 回跳核验：锚处现行行文摘要 vs 落款摘要
    const problems = [...base.problems];
    let backjumpChecked = 0;
    let backjumpMismatched = 0;
    for (const c of candidates) {
      for (const a of JSON.parse(c.anchors_json || "[]")) {
        if (a.kind !== "rows" || !a.rows) continue;
        backjumpChecked += 1;
        const rows = dao.getRows(workspaceKey, a.sourceId, a.rows.tableName, a.rows.rowStart, a.rows.rowEnd);
        const nowDigest = digestOf(rows.map((r) => r.text));
        if (nowDigest !== a.digest) {
          backjumpMismatched += 1;
          problems.push({ ref: a.label, issue: "引用回跳原文与清单落款时不一致（源行已变动或锚失效）" });
        }
      }
    }
    return {
      ok: problems.length === 0, checked: base.checked, problems,
      backjumpChecked, backjumpMismatched,
      candidates: candidates.length,
    };
  }

  // ── D3 建议-确认分权（人工确认才入正式；律师留名必填）──
  function confirmCandidate(id, { confirmedBy }) {
    const row = requireCandidate(id);
    const by = String(confirmedBy ?? "").trim();
    if (!by) { const e = new Error("确认必须留名（confirmedBy）"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    if (row.status === "confirmed") return { ...candidateProto(dao.getCandidate(workspaceKey, id)), alreadyConfirmed: true };
    dao.updateCandidate(workspaceKey, id, { status: "confirmed", confirmed_by: by, confirmed_at: iso() });
    insertRefineAudit(row.case_id, `candidate:${id}`, "confirm", { title: row.title }, { title: row.title, status: "confirmed" }, "律师确认候选", by);
    auditWrite("edisc.fixlist.confirm", id, { caseId: row.case_id, by });
    return candidateProto(dao.getCandidate(workspaceKey, id));
  }
  function requireCandidate(id) {
    const row = dao.getCandidate(workspaceKey, id);
    if (!row) { const e = new Error("候选不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
    return row;
  }

  // ── G2/G3 元数据更正（默认干跑预览；confirmed=true 落库+精化留痕）──
  function updateCandidateMetadata(id, { title, purpose, reason = "", confirmed = false, by = "律师" }) {
    const row = requireCandidate(id);
    const before = { title: row.title, purpose: row.purpose };
    const after = {
      title: typeof title === "string" && title.trim() ? title.trim() : before.title,
      purpose: typeof purpose === "string" ? purpose.trim() : before.purpose,
    };
    if (after.title === before.title && after.purpose === before.purpose) {
      const e = new Error("没有任何待更正字段"); e.http = 400; e.code = "BAD_REQUEST"; throw e;
    }
    const preview = {
      candidateId: id, dryRun: !confirmed, before, after, reason,
      refinePreview: { targetRef: `candidate:${id}`, op: "metadata", by },
    };
    if (!confirmed) return { ...preview, note: "默认干跑：以上为预览，传 confirmed=true 才落库并记精化留痕。" };
    dao.updateCandidate(workspaceKey, id, { title: after.title, purpose: after.purpose });
    insertRefineAudit(row.case_id, `candidate:${id}`, "metadata", before, after, reason, by);
    auditWrite("edisc.metadata.refine", id, { fields: Object.keys(after).filter((k) => after[k] !== before[k]), by });
    return { ...preview, applied: true };
  }
  function insertRefineAudit(caseId, targetRef, op, before, after, reason, by) {
    dao.insertRefineAudit({
      workspace_key: workspaceKey, audit_id: randomId("eaud"), case_id: caseId,
      target_ref: targetRef, op, before_json: JSON.stringify(before), after_json: JSON.stringify(after),
      reason: String(reason ?? ""), by: String(by ?? ""), at: iso(),
    });
  }
  const listRefineAudit = (caseId) => {
    requireCase(caseId);
    return { items: dao.listRefineAudit(workspaceKey, caseId).map((r) => ({
      id: r.audit_id, caseId: r.case_id, targetRef: r.target_ref, op: r.op,
      before: JSON.parse(r.before_json || "{}"), after: JSON.parse(r.after_json || "{}"),
      reason: r.reason, by: r.by, at: r.at,
    })) };
  };

  // ── F1 待证事实登记（审查先行件；提炼自诉求与争点归人，四类排除纪律随登记面输出）──
  function registerFact({ caseId, text, note = "", createdBy = "律师" }) {
    requireCase(caseId);
    const t = String(text ?? "").trim();
    if (!t) { const e = new Error("待证事实不能为空"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const id = randomId("efact");
    dao.insertFact({
      workspace_key: workspaceKey, fact_id: id, case_id: caseId,
      text: t, note: String(note ?? ""), created_by: createdBy, created_at: iso(),
    });
    auditWrite("edisc.fact.register", id, { caseId, by: createdBy });
    return factProto(dao.listFacts(workspaceKey, caseId).find((f) => f.fact_id === id));
  }
  const factProto = (r) => ({
    id: r.fact_id, caseId: r.case_id, text: r.text, note: r.note,
    createdBy: r.created_by, createdAt: r.created_at,
  });
  const listFacts = (caseId) => {
    requireCase(caseId);
    return {
      items: dao.listFacts(workspaceKey, caseId).map(factProto),
      exclusionNote: FACT_EXCLUSION_NOTE,                                   // 四类排除纪律随读回下发
    };
  };

  // ── F2 形式六要素（逐候选登记；缺项给"先补齐再实质审查"可读提示，不拦确认——档位归律师）──
  function saveFormalElements(candidateId, { elements, by = "律师" }) {
    const row = requireCandidate(candidateId);
    const clean = {};
    for (const k of FORMAL_ELEMENTS) clean[k] = String(elements?.[k] ?? "").trim();
    const check = checkFormalElements(clean);
    dao.upsertFormal({
      workspace_key: workspaceKey, case_id: row.case_id, candidate_id: candidateId,
      elements_json: JSON.stringify(clean), updated_by: by, updated_at: iso(),
    });
    insertRefineAudit(row.case_id, `candidate:${candidateId}`, "formal-elements",
      { formal: "未登记" }, { formal: check.note }, "形式六要素登记", by);
    auditWrite("edisc.formal.save", candidateId, { caseId: row.case_id, complete: check.complete, by });
    return { candidateId, elements: clean, check };
  }

  // ── F4 三性评估表单（真实性/合法性/关联性逐项结论+理由；结论闭集校验）──
  function saveTripleReview({ caseId, sourceId = null, targetLabel, findings, createdBy = "律师" }) {
    requireCase(caseId);
    if (sourceId) {
      const src = requireSource(sourceId);
      if (src.case_id !== caseId) { const e = new Error("源不属于该案件"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    }
    const label = String(targetLabel ?? "").trim();
    if (!label) { const e = new Error("评估对象不能为空（targetLabel）"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const norm = normalizeTripleFindings(findings);
    if (!norm.ok) { const e = new Error(norm.error); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const id = randomId("etri");
    dao.insertTriple({
      workspace_key: workspaceKey, review_id: id, case_id: caseId, source_id: sourceId,
      target_label: label, findings_json: JSON.stringify(norm.findings),
      created_by: createdBy, created_at: iso(),
    });
    auditWrite("edisc.triple.save", id, { caseId, attrs: norm.findings.map((f) => f.attr).join("/"), by: createdBy });
    return tripleProto(dao.listTriples(workspaceKey, caseId).find((t) => t.review_id === id));
  }
  const tripleProto = (r) => ({
    id: r.review_id, caseId: r.case_id, sourceId: r.source_id ?? null, targetLabel: r.target_label,
    findings: JSON.parse(r.findings_json || "[]"), createdBy: r.created_by, createdAt: r.created_at,
  });
  const listTripleReviews = (caseId) => {
    requireCase(caseId);
    return { items: dao.listTriples(workspaceKey, caseId).map(tripleProto) };
  };

  // ── F6 四类缺口结构化（类目闭集；每缺口必须给补充建议，期限警示可选）──
  function registerGap({ caseId, kind, factText = "", suggestion, sourceChannel = "", difficulty = "", deadlineNote = "", createdBy = "律师" }) {
    requireCase(caseId);
    if (!GAP_KINDS.includes(kind)) {
      const e = new Error(`缺口类目必须是 ${GAP_KINDS.join("/")}（收到：${kind ?? "空"}）`);
      e.http = 400; e.code = "BAD_REQUEST"; throw e;
    }
    const sug = String(suggestion ?? "").trim();
    if (!sug) { const e = new Error("缺口登记必须给补充建议（拟取得什么证据）"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const id = randomId("egap");
    dao.insertGap({
      workspace_key: workspaceKey, gap_id: id, case_id: caseId, kind,
      fact_text: String(factText ?? ""), suggestion: sug,
      source_channel: String(sourceChannel ?? ""), difficulty: String(difficulty ?? ""),
      deadline_note: String(deadlineNote ?? ""), created_by: createdBy, created_at: iso(),
    });
    auditWrite("edisc.gap.register", id, { caseId, kind, by: createdBy });
    return gapProto(dao.listGaps(workspaceKey, caseId).find((g) => g.gap_id === id));
  }
  const gapProto = (r) => ({
    id: r.gap_id, caseId: r.case_id, kind: r.kind, factText: r.fact_text, suggestion: r.suggestion,
    sourceChannel: r.source_channel, difficulty: r.difficulty, deadlineNote: r.deadline_note,
    createdBy: r.created_by, createdAt: r.created_at,
  });
  const listGaps = (caseId) => {
    requireCase(caseId);
    return { items: dao.listGaps(workspaceKey, caseId).map(gapProto) };
  };

  // ── G5 长任务生命周期（批量整理=逐件解析在册源；检查点=每件落库后推进；启动即返回执）──
  // tickMs=逐件处理间隔（默认 0 尽速；测试/演示传正值以便运行中注入暂停/取消）。
  const taskTickTimers = new Map(); // taskId → Timeout（控制面改库后由 tick 自行停摆，不强清定时器）
  function taskFromRow(row) {
    return {
      taskId: row.task_id, caseId: row.case_id, status: row.status,
      items: JSON.parse(row.items_json || "[]"), checkpoint: row.checkpoint,
      pageCardsOnly: Boolean(row.page_cards_only), stopOnError: Boolean(row.stop_on_error),
      createdAt: row.created_at, updatedAt: row.updated_at,
    };
  }
  function taskProto(row) {
    const t = taskFromRow(row);
    return {
      id: t.taskId, caseId: t.caseId, status: t.status, checkpoint: t.checkpoint,
      pageCardsOnly: t.pageCardsOnly, stopOnError: t.stopOnError,
      createdAt: t.createdAt, updatedAt: t.updatedAt,
      summary: taskSummary(t),
      items: t.items.map((i) => ({ sourceId: i.sourceId, label: i.label, state: i.state, attempts: i.attempts, error: i.error ?? null })),
    };
  }
  function persistTask(t, tickMs = 0) {
    const existing = dao.getTask(workspaceKey, t.taskId);
    const cols = {
      status: t.status, items_json: JSON.stringify(t.items), checkpoint: t.checkpoint, updated_at: t.updatedAt,
    };
    if (existing) dao.updateTask(workspaceKey, t.taskId, cols);
    else dao.insertTask({
      workspace_key: workspaceKey, task_id: t.taskId, case_id: t.caseId,
      status: t.status, items_json: cols.items_json, checkpoint: t.checkpoint,
      page_cards_only: t.pageCardsOnly ? 1 : 0, stop_on_error: t.stopOnError ? 1 : 0,
      tick_ms: Math.max(0, Math.floor(Number(tickMs) || 0)), created_at: t.createdAt, updated_at: t.updatedAt,
    });
  }
  function organizeOne(item, pageCardsOnly) {
    const src = dao.getSource(workspaceKey, item.sourceId);
    if (!src) { const e = new Error(`源 ${item.sourceId} 不存在（可能已移出）`); e.code = "SOURCE_MISSING"; throw e; }
    if (!src.stored_path) { const e = new Error("粗扫态无内容副本：先重新入册登记（带文件内容）再整理"); e.code = "NO_STORED_BYTES"; throw e; }
    const buf = readFileSync(src.stored_path);                              // G1：只读原件域内副本
    const hash = src.file_hash || sha256hex(buf);
    dao.updateSource(src.source_id, { workspace_key: workspaceKey, parse_status: "parsing" });
    try {
      parseSource({
        id: src.source_id, caseId: src.case_id, kind: src.kind, fname: src.filename,
        ext: src.format, buf, hash, pageCardsOnly,
      });
    } catch (err) {
      dao.updateSource(src.source_id, {
        workspace_key: workspaceKey, parse_status: "failed",
        error_code: err?.code ?? "PARSE_FAILED", error_message: err?.message ?? String(err),
      });
      throw err;
    }
  }
  function taskTick(taskId) {
    let row = dao.getTask(workspaceKey, taskId);
    if (!row || row.status !== "running") { taskTickTimers.delete(taskId); return; }
    const t0 = taskFromRow(row);
    const idx = nextPendingIndex(t0);
    if (idx === null) {
      const done = { ...t0, status: "done", updatedAt: iso() };
      persistTask(done, row.tick_ms);
      auditWrite("edisc.task.done", taskId, { caseId: t0.caseId, summary: taskSummary(done) });
      taskTickTimers.delete(taskId);
      return;
    }
    const item = t0.items[idx];
    let t1;
    try {
      organizeOne(item, t0.pageCardsOnly);
      t1 = recordOutcome(t0, item.sourceId, "ok", "", iso());
    } catch (err) {
      t1 = recordOutcome(t0, item.sourceId, "failed", String(err?.message ?? err), iso());
    }
    persistTask(t1, row.tick_ms);
    if (t1.status === "running") {
      taskTickTimers.set(taskId, setTimeout(() => taskTick(taskId), Math.max(0, row.tick_ms || 0)));
    } else if (t1.status === "paused") {
      auditWrite("edisc.task.halt", taskId, { caseId: t1.caseId, reason: "stopOnError：失败即停，断点保留待恢复", failed: item.label });
      taskTickTimers.delete(taskId);
    }
  }
  function startOrganizeTask({ caseId, sourceIds = null, pageCardsOnly = false, stopOnError = false, tickMs = 0, resume = false }) {
    requireCase(caseId);
    if (resume) {
      const paused = dao.listTasksByCase(workspaceKey, caseId).find((r) => r.status === "paused");
      if (paused) return controlOrganizeTask(paused.task_id, "resume");
    }
    let work;
    if (Array.isArray(sourceIds) && sourceIds.length) {
      work = sourceIds.map((sid) => {
        const s = requireSource(String(sid));
        if (s.case_id !== caseId) { const e = new Error(`源 ${sid} 不属于案件 ${caseId}`); e.http = 400; e.code = "BAD_REF"; throw e; }
        return { sourceId: s.source_id, label: s.filename };
      });
    } else {
      work = dao.listSourcesByCase(workspaceKey, caseId)
        .filter((s) => s.parse_status !== "done" && s.stored_path)
        .map((s) => ({ sourceId: s.source_id, label: s.filename }));
    }
    const ts = iso();
    let task;
    try {
      task = startOrganize({ taskId: randomId("etask"), caseId, createdAt: ts }, work, { pageCardsOnly, stopOnError });
    } catch (e) { e.http = 409; e.code = "NO_WORK"; throw e; }
    persistTask(task, tickMs);
    auditWrite("edisc.task.start", task.taskId, { caseId, total: work.length, pageCardsOnly, stopOnError, resume: Boolean(resume && work) });
    taskTickTimers.set(task.taskId, setTimeout(() => taskTick(task.taskId), Math.max(0, Math.floor(Number(tickMs) || 0))));
    return taskProto(dao.getTask(workspaceKey, task.taskId));               // 后台启动即返：检查点回执
  }
  function controlOrganizeTask(taskId, control) {
    if (!TASK_CONTROLS.includes(control)) { const e = new Error(`未知控制动作 ${control}`); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const row = dao.getTask(workspaceKey, taskId);
    if (!row) { const e = new Error("任务不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
    const r = applyControl(taskFromRow(row), control, iso());
    if (!r.ok) { const e = new Error(r.error); e.http = 409; e.code = "BAD_CONTROL"; throw e; }
    persistTask(r.task, row.tick_ms);
    auditWrite(`edisc.task.${control.replace("-", ".")}`, taskId, { caseId: r.task.caseId, status: r.task.status });
    if (r.task.status === "running" && !taskTickTimers.has(taskId)) {
      taskTickTimers.set(taskId, setTimeout(() => taskTick(taskId), Math.max(0, row.tick_ms || 0)));
    }
    return taskProto(dao.getTask(workspaceKey, taskId));
  }
  const getOrganizeTask = (taskId) => {
    const row = dao.getTask(workspaceKey, taskId);
    if (!row) { const e = new Error("任务不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
    return taskProto(row);
  };
  const listOrganizeTasks = (caseId) => {
    requireCase(caseId);
    return { items: dao.listTasksByCase(workspaceKey, caseId).map(taskProto) };
  };

  // ── E2 锚回跳（引用→原文位置；行/块两态）──
  function resolveAnchor(q) {
    if (q?.kind === "rows") {
      const ref = normalizeRowRef(q);
      if (!ref) { const e = new Error("行引用不合法"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
      const src = requireSource(ref.sourceId);
      const rows = dao.getRows(workspaceKey, ref.sourceId, ref.tableName, ref.rowStart, ref.rowEnd);
      return {
        kind: "rows", sourceId: ref.sourceId, tableName: ref.tableName, rowStart: ref.rowStart, rowEnd: ref.rowEnd,
        fileHash: src.file_hash,
        invariantOk: rows.length > 0 && rows.every((r) => anchorInvariantOk(src.file_hash, { fileHash: r.file_hash })),
        rows: rows.map((r) => ({ rowNo: r.row_no, cells: JSON.parse(r.cells_json || "[]"), text: r.text, blockId: r.block_id ?? null })),
      };
    }
    if (q?.kind === "block") {
      const page = Math.floor(Number(q.page));
      const seq = Math.floor(Number(q.seq));
      if (!Number.isInteger(page) || !Number.isInteger(seq) || !q.sourceId) {
        const e = new Error("块引用需 sourceId/page/seq"); e.http = 400; e.code = "BAD_REQUEST"; throw e;
      }
      const src = requireSource(q.sourceId);
      const b = dao.getBlock(workspaceKey, q.sourceId, page, seq);
      if (!b) { const e = new Error(`页 ${page} 块序 ${seq} 不存在`); e.http = 404; e.code = "NOT_FOUND"; throw e; }
      return {
        kind: "block", sourceId: q.sourceId, page: b.page, seq: b.seq,
        bbox: JSON.parse(b.bbox_json || "[]"), coordSystem: b.coord_system,
        text: b.text, engine: b.engine, ocrVersion: b.ocr_version, fileHash: b.file_hash,
        invariantOk: anchorInvariantOk(src.file_hash, { fileHash: b.file_hash }),
      };
    }
    const e = new Error("kind 必须是 rows 或 block"); e.http = 400; e.code = "BAD_REQUEST"; throw e;
  }

  // ── E4 页卡阅读面（整页块序+文本，覆盖阅读载体；不抽样）──
  function pageCards(id, page) {
    const src = requireSource(id);
    const pageNo = Math.max(1, Math.floor(Number(page) || 1));
    const blocks = dao.listBlocks(workspaceKey, id, pageNo);
    if (src.format === ".pdf" && !blocks.length && (src.page_count ?? 0) > 0 && pageNo > src.page_count) {
      const e = new Error(`页 ${pageNo} 超出源页数 ${src.page_count}`); e.http = 404; e.code = "NOT_FOUND"; throw e;
    }
    return {
      sourceId: id, page: pageNo, fileHash: src.file_hash, coordSystem: PDF_COORD_SYSTEM,
      fullText: blocks.map((b) => b.text).join("\n"),
      blocks: blocks.map((b) => ({ seq: b.seq, bbox: JSON.parse(b.bbox_json || "[]"), text: b.text, blockId: b.block_id })),
      note: "页卡为分析载体：引用前须整页覆盖阅读，不得以抽样代替。",
    };
  }
  const listPages = (id) => {
    const src = requireSource(id);
    const blocks = dao.listBlocks(workspaceKey, id, null);
    const byPage = new Map();
    for (const b of blocks) byPage.set(b.page, (byPage.get(b.page) ?? 0) + 1);
    return { sourceId: id, pageCount: src.page_count ?? null, blocksPerPage: [...byPage.entries()].map(([p, n]) => ({ page: p, blocks: n })) };
  };

  // ── E3 坐标批注（虚拟覆盖层，挂页/坐标，不篡改原件）──
  function createAnnotation({ caseId, sourceId, pageNumber, rects, type = "highlight", color = ANNOTATION_COLOR_DEFAULT, textContent = "", comment = "", createdBy = "律师" }) {
    requireCase(caseId);
    const src = requireSource(sourceId);
    if (src.case_id !== caseId) { const e = new Error("源不属于该案件"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const page = Math.floor(Number(pageNumber));
    if (!Number.isInteger(page) || page < 1) { const e = new Error("pageNumber 必须是 >=1 的整数"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    if (!Array.isArray(rects) || !rects.length || !rects.every((r) => Array.isArray(r) && r.length === 4 && r.every((n) => Number.isFinite(n)))) {
      const e = new Error("rects 必须是非空矩形数组 [x0,y0,x1,y1]（单位与锚坐标系一致）"); e.http = 400; e.code = "BAD_REQUEST"; throw e;
    }
    if (!ANNOTATION_TYPES.has(type)) { const e = new Error(`批注类型必须是 ${[...ANNOTATION_TYPES].join("/")}`); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const id = randomId("eann");
    dao.insertAnnotation({
      workspace_key: workspaceKey, annotation_id: id, case_id: caseId, source_id: sourceId,
      page_number: page, rects_json: JSON.stringify(rects), annotation_type: type,
      color: /^#[0-9a-fA-F]{6}$/.test(color) ? color : ANNOTATION_COLOR_DEFAULT,
      text_content: String(textContent ?? ""), comment: String(comment ?? ""),
      created_by: createdBy, created_at: iso(),
    });
    auditWrite("edisc.annotation.create", id, { caseId, sourceId, page, type });
    return annotationProto(dao.listAnnotations(workspaceKey, caseId).find((a) => a.annotation_id === id));
  }
  const annotationProto = (r) => ({
    id: r.annotation_id, caseId: r.case_id, sourceId: r.source_id, pageNumber: r.page_number,
    rects: JSON.parse(r.rects_json || "[]"), type: r.annotation_type, color: r.color,
    textContent: r.text_content, comment: r.comment, createdBy: r.created_by, createdAt: r.created_at,
  });
  const listAnnotations = (caseId, sourceId = null, page = null) => {
    requireCase(caseId);
    return { items: dao.listAnnotations(workspaceKey, caseId, sourceId ?? null, page === null ? null : Math.floor(Number(page))).map(annotationProto) };
  };

  // ── F3/F5/F11 审查标注（预置档+可覆写；档位/标记闭集校验）──
  function createReviewFlag({ caseId, sourceId = null, targetLabel, kind = "generic", notarized = false, level, proofStrength, issues, supports, weakens, lawyerAction, tags, createdBy = "律师" }) {
    requireCase(caseId);
    if (sourceId) {
      const src = requireSource(sourceId);
      if (src.case_id !== caseId) { const e = new Error("源不属于该案件"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    }
    const preset = presetReviewFlag(kind, { notarized });
    const lv = level === undefined ? preset.level : level;
    if (!FLAG_LEVELS.includes(lv)) { const e = new Error(`档位必须是 ${FLAG_LEVELS.join("/")}`); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const ps = proofStrength === undefined ? preset.proofStrength : proofStrength;
    if (ps !== "" && !PROOF_STRENGTHS.includes(ps)) { const e = new Error(`证明力必须是 ${PROOF_STRENGTHS.join("/")}`); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const tagList = tags === undefined ? preset.tags : tags;
    if (!Array.isArray(tagList) || tagList.some((t) => !FLAG_TAGS.includes(t))) {
      const e = new Error(`标记必须取自 ${FLAG_TAGS.join("/")}`); e.http = 400; e.code = "BAD_REQUEST"; throw e;
    }
    const id = randomId("eflag");
    dao.insertFlag({
      workspace_key: workspaceKey, flag_id: id, case_id: caseId,
      target_label: String(targetLabel ?? "").trim(), target_ref_json: JSON.stringify(sourceId ? { sourceId } : {}),
      kind, level: lv, proof_strength: ps,
      issues_json: JSON.stringify(issues === undefined ? preset.issues : issues),
      supports_json: JSON.stringify(supports === undefined ? preset.supports : supports),
      weakens_json: JSON.stringify(weakens === undefined ? preset.weakens : weakens),
      lawyer_action: lawyerAction === undefined ? preset.lawyerAction : lawyerAction,
      tags_json: JSON.stringify(tagList), created_by: createdBy, created_at: iso(),
    });
    auditWrite("edisc.flag.create", id, { caseId, kind, level: lv, by: createdBy });
    return flagProto(dao.listFlags(workspaceKey, caseId).find((f) => f.flag_id === id));
  }
  const flagProto = (r) => ({
    id: r.flag_id, caseId: r.case_id, targetLabel: r.target_label, targetRef: JSON.parse(r.target_ref_json || "{}"),
    kind: r.kind, level: r.level, proofStrength: r.proof_strength,
    issues: JSON.parse(r.issues_json || "[]"), supports: JSON.parse(r.supports_json || "[]"),
    weakens: JSON.parse(r.weakens_json || "[]"), lawyerAction: r.lawyer_action,
    tags: JSON.parse(r.tags_json || "[]"), createdBy: r.created_by, createdAt: r.created_at,
  });
  const listReviewFlags = (caseId) => {
    requireCase(caseId);
    return { items: dao.listFlags(workspaceKey, caseId).map(flagProto) };
  };

  // ── F12 审查报告（七节；律师闸与引用核实双轮随报告输出；F1/F2/F4/F6/F9/F14 随收尾面并入）──
  function reviewReport(caseId) {
    requireCase(caseId);
    const verify = verifyFixList(caseId);
    const formalMap = new Map(dao.listFormalByCase(workspaceKey, caseId).map((r) => [r.candidate_id, r]));
    const candidates = dao.listCandidates(workspaceKey, caseId).map((c) => candidateProto(c, formalMap));
    const flags = dao.listFlags(workspaceKey, caseId).map(flagProto);
    const categories = [...new Set(dao.listClassifications(workspaceKey, caseId).map((c) => c.category))];
    const facts = dao.listFacts(workspaceKey, caseId).map((f) => f.text);
    const triples = dao.listTriples(workspaceKey, caseId).map((r) => ({
      targetLabel: r.target_label, findings: JSON.parse(r.findings_json || "[]"),
    }));
    const gaps = dao.listGaps(workspaceKey, caseId).map(gapProto);
    const report = buildReviewReport({
      caseId, categories, facts,
      candidates: candidates.map((c) => ({
        title: c.title, status: c.status, confirmedBy: c.confirmedBy, anchors: c.anchors,
        formal: c.formal ? c.formal.check : undefined,
      })),
      flags: flags.map((f) => ({ targetLabel: f.targetLabel || f.id, kind: f.kind, level: f.level, issues: f.issues, lawyerAction: f.lawyerAction, tags: f.tags })),
      triples, gaps, verify,
    });
    return { caseId, report, verify };
  }

  // ── HTTP 面（/api/edisc/*；本地鉴权挂点同材料面）──
  async function httpHandler(req, res, url) {
    const path = url.pathname;
    if (!path.startsWith("/api/edisc/")) return false;
    const send = (code, obj) => {
      if (res.headersSent) { res.end(); return; }
      res.writeHead(code, { "content-type": "application/json; charset=utf-8" });
      res.end(JSON.stringify(obj));
    };
    try {
      if (!localAuthOk(req)) { send(401, { error: { code: "UNAUTHORIZED", message: "缺少有效的本地访问凭据" } }); return true; }
      const m = req.method ?? "GET";
      if (path === "/api/edisc/sources" && m === "POST") {
        const body = await readJsonBody(req);
        if (!body.dataBase64) { send(400, { error: { code: "BAD_REQUEST", message: "缺少文件内容 dataBase64" } }); return true; }
        send(200, registerSource({
          caseId: String(body.caseId ?? ""), kind: body.kind ?? "generic", filename: body.filename,
          bytes: Buffer.from(String(body.dataBase64), "base64"),
          computeHash: body.computeHash === undefined ? true : Boolean(body.computeHash),   // A2 默认哈希
          parse: body.parse === undefined ? true : Boolean(body.parse),                     // A2 默认解析
          registeredBy: body.registeredBy,
        }));
        return true;
      }
      if (path === "/api/edisc/scan" && m === "POST") {
        const body = await readJsonBody(req);
        send(200, scanDirectory({
          caseId: String(body.caseId ?? ""), rootPath: String(body.rootPath ?? ""),
          computeHash: body.computeHash === undefined ? false : Boolean(body.computeHash),  // A1 默认不哈希
        }));
        return true;
      }
      if (path === "/api/edisc/sources" && m === "GET") { send(200, listSources(url.searchParams.get("caseId") ?? "")); return true; }
      const mProf = path.match(/^\/api\/edisc\/sources\/([^/]+)\/profile$/);
      if (mProf && m === "GET") { send(200, sourceProfile(decodeURIComponent(mProf[1]))); return true; }
      const mRows = path.match(/^\/api\/edisc\/sources\/([^/]+)\/rows$/);
      if (mRows && m === "GET") {
        send(200, readRows(
          decodeURIComponent(mRows[1]),
          url.searchParams.get("table") ?? CHAT_TABLE,
          Number(url.searchParams.get("rowStart") ?? DEFAULT_ROW_START),
          Number(url.searchParams.get("rowEnd") ?? DEFAULT_ROW_END),
        ));
        return true;
      }
      const mPages = path.match(/^\/api\/edisc\/sources\/([^/]+)\/pages$/);
      if (mPages && m === "GET") { send(200, pageCards(decodeURIComponent(mPages[1]), Number(url.searchParams.get("page") ?? 1))); return true; }
      const mSrc = path.match(/^\/api\/edisc\/sources\/([^/]+)$/);
      if (mSrc && m === "GET") { send(200, getSourceDetail(decodeURIComponent(mSrc[1]))); return true; }
      if (path === "/api/edisc/search" && m === "GET") {
        send(200, searchRows({
          caseId: url.searchParams.get("caseId") ?? "",
          sourceId: url.searchParams.get("sourceId") ?? null,
          q: url.searchParams.get("q") ?? "",
          limit: Number(url.searchParams.get("limit") ?? SEARCH_LIMIT_DEFAULT),
        }));
        return true;
      }
      if (path === "/api/edisc/classifications" && m === "POST") {
        const body = await readJsonBody(req);
        send(200, classifyRows({ caseId: String(body.caseId ?? ""), refs: body.refs, category: body.category, reason: body.reason, createdBy: body.createdBy }));
        return true;
      }
      if (path === "/api/edisc/classifications" && m === "GET") {
        send(200, listClassifications(url.searchParams.get("caseId") ?? "", url.searchParams.get("sourceId")));
        return true;
      }
      if (path === "/api/edisc/fix-lists" && m === "POST") {
        const body = await readJsonBody(req);
        send(200, generateFixList({ caseId: String(body.caseId ?? ""), category: body.category ?? null }));
        return true;
      }
      if (path === "/api/edisc/fix-lists" && m === "GET") { send(200, listFixLists(url.searchParams.get("caseId") ?? "")); return true; }
      if (path === "/api/edisc/fix-lists/verify" && m === "POST") {
        const body = await readJsonBody(req);
        send(200, verifyFixList(String(body.caseId ?? "")));
        return true;
      }
      const mConfirm = path.match(/^\/api\/edisc\/fix-lists\/([^/]+)\/confirm$/);
      if (mConfirm && m === "POST") {
        const body = await readJsonBody(req);
        send(200, confirmCandidate(decodeURIComponent(mConfirm[1]), { confirmedBy: body.confirmedBy }));
        return true;
      }
      const mMeta = path.match(/^\/api\/edisc\/fix-lists\/([^/]+)\/metadata$/);
      if (mMeta && m === "POST") {
        const body = await readJsonBody(req);
        send(200, updateCandidateMetadata(decodeURIComponent(mMeta[1]), {
          title: body.title, purpose: body.purpose, reason: body.reason,
          confirmed: Boolean(body.confirmed), by: body.by,
        }));
        return true;
      }
      if (path === "/api/edisc/anchors/resolve" && m === "POST") {
        const body = await readJsonBody(req);
        send(200, resolveAnchor(body));
        return true;
      }
      if (path === "/api/edisc/annotations" && m === "POST") {
        const body = await readJsonBody(req);
        send(200, createAnnotation(body));
        return true;
      }
      if (path === "/api/edisc/annotations" && m === "GET") {
        send(200, listAnnotations(
          url.searchParams.get("caseId") ?? "",
          url.searchParams.get("sourceId"),
          url.searchParams.get("page") === null ? null : Number(url.searchParams.get("page")),
        ));
        return true;
      }
      if (path === "/api/edisc/review-flags" && m === "POST") {
        const body = await readJsonBody(req);
        send(200, createReviewFlag(body));
        return true;
      }
      if (path === "/api/edisc/review-flags" && m === "GET") { send(200, listReviewFlags(url.searchParams.get("caseId") ?? "")); return true; }
      if (path === "/api/edisc/facts" && m === "POST") {
        const body = await readJsonBody(req);
        send(200, registerFact(body));
        return true;
      }
      if (path === "/api/edisc/facts" && m === "GET") { send(200, listFacts(url.searchParams.get("caseId") ?? "")); return true; }
      const mFormal = path.match(/^\/api\/edisc\/fix-lists\/([^/]+)\/elements$/);
      if (mFormal && m === "POST") {
        const body = await readJsonBody(req);
        send(200, saveFormalElements(decodeURIComponent(mFormal[1]), { elements: body.elements, by: body.by }));
        return true;
      }
      if (path === "/api/edisc/triple-reviews" && m === "POST") {
        const body = await readJsonBody(req);
        send(200, saveTripleReview(body));
        return true;
      }
      if (path === "/api/edisc/triple-reviews" && m === "GET") { send(200, listTripleReviews(url.searchParams.get("caseId") ?? "")); return true; }
      if (path === "/api/edisc/gaps" && m === "POST") {
        const body = await readJsonBody(req);
        send(200, registerGap(body));
        return true;
      }
      if (path === "/api/edisc/gaps" && m === "GET") { send(200, listGaps(url.searchParams.get("caseId") ?? "")); return true; }
      if (path === "/api/edisc/tasks" && m === "POST") {
        const body = await readJsonBody(req);
        send(200, startOrganizeTask({
          caseId: String(body.caseId ?? ""), sourceIds: Array.isArray(body.sourceIds) ? body.sourceIds : null,
          pageCardsOnly: Boolean(body.pageCardsOnly), stopOnError: Boolean(body.stopOnError),
          tickMs: Number(body.tickMs ?? 0), resume: Boolean(body.resume),
        }));
        return true;
      }
      if (path === "/api/edisc/tasks" && m === "GET") { send(200, listOrganizeTasks(url.searchParams.get("caseId") ?? "")); return true; }
      const mTaskCtl = path.match(/^\/api\/edisc\/tasks\/([^/]+)\/(pause|resume|cancel|recover-failed)$/);
      if (mTaskCtl && m === "POST") {
        send(200, controlOrganizeTask(decodeURIComponent(mTaskCtl[1]), mTaskCtl[2]));
        return true;
      }
      const mTask = path.match(/^\/api\/edisc\/tasks\/([^/]+)$/);
      if (mTask && m === "GET") { send(200, getOrganizeTask(decodeURIComponent(mTask[1]))); return true; }
      if (path === "/api/edisc/review-report" && m === "GET") { send(200, reviewReport(url.searchParams.get("caseId") ?? "")); return true; }
      if (path === "/api/edisc/refinements" && m === "GET") { send(200, listRefineAudit(url.searchParams.get("caseId") ?? "")); return true; }
      send(404, { error: { code: "NOT_FOUND", message: `电子数据面未知路由：${m} ${path}` } });
      return true;
    } catch (e) {
      send(e?.http ?? 500, { error: { code: e?.code ?? "INTERNAL", message: e?.message ?? String(e) } });
      return true;
    }
  }

  return {
    registerSource, scanDirectory, listSources, getSourceDetail, sourceProfile, readRows, searchRows,
    classifyRows, listClassifications, generateFixList, listFixLists, verifyFixList, confirmCandidate,
    updateCandidateMetadata, listRefineAudit, resolveAnchor, pageCards, listPages,
    createAnnotation, listAnnotations, createReviewFlag, listReviewFlags, reviewReport, httpHandler,
    registerFact, listFacts, saveFormalElements, saveTripleReview, listTripleReviews,
    registerGap, listGaps, startOrganizeTask, controlOrganizeTask, getOrganizeTask, listOrganizeTasks,
  };
}
