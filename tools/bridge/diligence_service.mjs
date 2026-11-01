// 【功能 #32 整理与尽调】桥面服务（RE-32 §2 行为 1-16 + 2026-10-31 增补 S1-S3；施工波三轮-20261031）。
// 内核=packages/juscite-legal/src/kernel/diligence*.ts（出树自有包五内核，相对路径消费同 juscite-legal kernel 先例）；
// 本文件只做 I/O 接线（库/文件/HTTP/异步壳），机制与文案全在内核层自写。
// 分面：
//   A 任务看板（行为 1-5）：三分组模板建板/确认门状态机/子任务两级编辑/Flow 绑定契约（引擎归 RE-35 不调）/成果版本；
//   B 台账（行为 6-10）：字段模板三态一源（S1-S3）/批量提取（规则优先双路，LLM 路注入制缺省不编造）/
//     依据指针回溯（page+seq+bbox+source+ocrVersion 四元组口径）/在线编辑共用同一校验器/CSV 导出；
//   C 清单（行为 11-12）：分类归档+重命名+建索引/缺失核对+补充清单；
//   D 历史沿革（行为 13-16）：材料汇集=用户提交+项目内检索（§5：不做外部数据代采，对拍 12 按此口径）/
//     时间轴章节/风险评估与待核查/Word 导出（markdownToLegalDocx 零依赖装配，文案自写）。
// 异步：批量提取挂 r11 通用异步任务壳（taskshell register("diligence-extract")；入队即回、轮询取件、
// 产物走壳白名单 result_ref）。本地鉴权挂点同材料面（local-auth.token 存在即强制）。
// 审计：RE-30 §3.5 映射表无「尽调域」动作行，不增竞品没有的审计类别（同 #36 先例，记档不接线）。
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { markdownToLegalDocx } from "./draft_docx.mjs";
import { readJsonBody, extractPdfTextLayer } from "./material_service.mjs";
import {
  BOARD_GROUPS, BOARD_PRESET, isBoardGroup, boardProjection, transitionTask, confirmTask,
  addSubtask, removeSubtask, retitleSubtask, markSubtask, bindFlow, saveTaskResult, getTaskResult,
  TASK_STATUSES,
} from "../../packages/juscite-legal/src/kernel/diligenceBoardModel.ts";
import {
  validateFieldSchema, normalizeFieldSchema, renderExtractionPrompt, validateRowValues,
  exportSchemaJson, importSchemaJson, schemaFieldNames,
} from "../../packages/juscite-legal/src/kernel/diligenceSchemaModel.ts";
import {
  extractLedgerRows, ledgerToCsv, traceOf, editCell,
} from "../../packages/juscite-legal/src/kernel/diligenceLedgerModel.ts";
import {
  DEFAULT_CHECKLIST_TEMPLATE, organizePlan, checkMissing,
} from "../../packages/juscite-legal/src/kernel/diligenceListModel.ts";
import {
  CHRONICLE_KINDS, isChronicleKind, searchInProject, extractTimelineEvents,
  buildChronicleChapter, buildRiskAndTodo, chronicleWordMarkdown,
} from "../../packages/juscite-legal/src/kernel/diligenceChronicleModel.ts";
import { verifyQuoteBack } from "../../packages/juscite-flow/src/quote-back.mjs";

const CSV_BOM = "\uFEFF"; // Excel 打开中文 CSV 的兼容前置（自定口径；RFC4180 之外的加分项，不破坏解析器）

function randomId(prefix) {
  return `${prefix}_${createHash("sha256").update(`${Math.random()}${Date.now()}${process.pid}`).digest("hex").slice(0, 12)}`;
}

// ══════════ DDL（迁移 0024_diligence 单源；bridge_store 与合成自测共用同一份）══════════
export const DILIGENCE_DDL = `
  CREATE TABLE IF NOT EXISTS diligence_tasks (
    workspace_key TEXT NOT NULL,
    task_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    group_name TEXT NOT NULL CHECK (group_name IN ('计划与清单','资料收集与台账','专项核查')),
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','in_progress','pending_confirmation','done')),
    subtasks_json TEXT NOT NULL DEFAULT '[]',
    flow_ref_json TEXT,
    confirmed_by TEXT,
    confirmed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, task_id)
  );
  CREATE INDEX IF NOT EXISTS idx_diligence_tasks_case ON diligence_tasks (workspace_key, case_id, group_name);
  CREATE TABLE IF NOT EXISTS diligence_task_results (
    workspace_key TEXT NOT NULL,
    task_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    saved_by TEXT NOT NULL,
    saved_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, task_id, version)
  );
  CREATE TABLE IF NOT EXISTS diligence_field_schemas (
    workspace_key TEXT NOT NULL,
    schema_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    name TEXT NOT NULL,
    fields_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, schema_id)
  );
  CREATE TABLE IF NOT EXISTS diligence_ledgers (
    workspace_key TEXT NOT NULL,
    ledger_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    schema_id TEXT NOT NULL DEFAULT '',
    schema_name TEXT NOT NULL DEFAULT '',
    fields_json TEXT NOT NULL DEFAULT '[]',
    rows_json TEXT NOT NULL DEFAULT '[]',
    stats_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, ledger_id)
  );
  CREATE TABLE IF NOT EXISTS diligence_checklists (
    workspace_key TEXT NOT NULL,
    list_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    template_json TEXT NOT NULL DEFAULT '{}',
    plan_json TEXT,
    missing_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, list_id)
  );
  CREATE TABLE IF NOT EXISTS diligence_chronicles (
    workspace_key TEXT NOT NULL,
    chronicle_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    docs_json TEXT NOT NULL DEFAULT '[]',
    events_json TEXT NOT NULL DEFAULT '[]',
    chapter_md TEXT,
    risks_json TEXT,
    todo_md TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_key, chronicle_id)
  );
`;

// ══════════ DAO（对 db 句柄的存取；含对 #6 材料表 case_materials/case_material_chunks 的只读消费）══════════
export function createDiligenceDao(db) {
  return {
    upsertTask: (r) => db.prepare(`
      INSERT INTO diligence_tasks (workspace_key, task_id, case_id, group_name, title, status, subtasks_json,
        flow_ref_json, confirmed_by, confirmed_at, created_at, updated_at)
      VALUES (@workspace_key, @task_id, @case_id, @group_name, @title, @status, @subtasks_json,
        @flow_ref_json, @confirmed_by, @confirmed_at, @created_at, @updated_at)
      ON CONFLICT(workspace_key, task_id) DO UPDATE SET
        group_name=@group_name, title=@title, status=@status, subtasks_json=@subtasks_json,
        flow_ref_json=@flow_ref_json, confirmed_by=@confirmed_by, confirmed_at=@confirmed_at, updated_at=@updated_at`)
      .run(r),
    getTask: (ws, id) => {
      const r = db.prepare("SELECT * FROM diligence_tasks WHERE workspace_key = ? AND task_id = ?").get(ws, id);
      if (!r) return null;
      return {
        taskId: r.task_id, caseId: r.case_id, group: r.group_name, title: r.title, status: r.status,
        subtasks: JSON.parse(r.subtasks_json || "[]"), flowRef: r.flow_ref_json ? JSON.parse(r.flow_ref_json) : null,
        confirmedBy: r.confirmed_by ?? null, confirmedAt: r.confirmed_at ?? null,
        createdAt: r.created_at, updatedAt: r.updated_at,
      };
    },
    listTasksByCase: (ws, caseId) =>
      db.prepare("SELECT task_id FROM diligence_tasks WHERE workspace_key = ? AND case_id = ? ORDER BY created_at, task_id")
        .all(ws, caseId).map((r) => r.task_id),
    putResult: (ws, taskId, v) => db.prepare(`
      INSERT INTO diligence_task_results (workspace_key, task_id, version, content, saved_by, saved_at)
      VALUES (?, ?, ?, ?, ?, ?)`).run(ws, taskId, v.version, v.content, v.savedBy, v.savedAt),
    listResults: (ws, taskId) =>
      db.prepare("SELECT version, saved_by, saved_at FROM diligence_task_results WHERE workspace_key = ? AND task_id = ? ORDER BY version")
        .all(ws, taskId).map((r) => ({ version: r.version, savedBy: r.saved_by, savedAt: r.saved_at })),
    getResult: (ws, taskId, version) => {
      const r = db.prepare("SELECT content, saved_by, saved_at FROM diligence_task_results WHERE workspace_key = ? AND task_id = ? AND version = ?")
        .get(ws, taskId, version);
      return r ? { version, content: r.content, savedBy: r.saved_by, savedAt: r.saved_at } : null;
    },
    putSchema: (r) => db.prepare(`
      INSERT INTO diligence_field_schemas (workspace_key, schema_id, case_id, name, fields_json, created_at, updated_at)
      VALUES (@workspace_key, @schema_id, @case_id, @name, @fields_json, @created_at, @updated_at)
      ON CONFLICT(workspace_key, schema_id) DO UPDATE SET name=@name, fields_json=@fields_json, updated_at=@updated_at`)
      .run(r),
    getSchema: (ws, id) => {
      const r = db.prepare("SELECT * FROM diligence_field_schemas WHERE workspace_key = ? AND schema_id = ?").get(ws, id);
      if (!r) return null;
      return { schemaId: r.schema_id, caseId: r.case_id, name: r.name, fields: JSON.parse(r.fields_json || "[]"), createdAt: r.created_at, updatedAt: r.updated_at };
    },
    listSchemasByCase: (ws, caseId) =>
      db.prepare("SELECT schema_id FROM diligence_field_schemas WHERE workspace_key = ? AND case_id = ? ORDER BY created_at")
        .all(ws, caseId).map((r) => r.schema_id),
    putLedger: (r) => db.prepare(`
      INSERT INTO diligence_ledgers (workspace_key, ledger_id, case_id, schema_id, schema_name, fields_json,
        rows_json, stats_json, status, created_at, updated_at)
      VALUES (@workspace_key, @ledger_id, @case_id, @schema_id, @schema_name, @fields_json,
        @rows_json, @stats_json, @status, @created_at, @updated_at)
      ON CONFLICT(workspace_key, ledger_id) DO UPDATE SET
        rows_json=@rows_json, stats_json=@stats_json, status=@status, updated_at=@updated_at`)
      .run(r),
    getLedgerRow: (ws, id) => db.prepare("SELECT * FROM diligence_ledgers WHERE workspace_key = ? AND ledger_id = ?").get(ws, id) ?? null,
    listLedgersByCase: (ws, caseId) =>
      db.prepare("SELECT ledger_id FROM diligence_ledgers WHERE workspace_key = ? AND case_id = ? ORDER BY created_at")
        .all(ws, caseId).map((r) => r.ledger_id),
    putChecklist: (r) => db.prepare(`
      INSERT INTO diligence_checklists (workspace_key, list_id, case_id, template_json, plan_json, missing_json, created_at, updated_at)
      VALUES (@workspace_key, @list_id, @case_id, @template_json, @plan_json, @missing_json, @created_at, @updated_at)
      ON CONFLICT(workspace_key, list_id) DO UPDATE SET plan_json=@plan_json, missing_json=@missing_json, updated_at=@updated_at`)
      .run(r),
    getChecklist: (ws, id) => {
      const r = db.prepare("SELECT * FROM diligence_checklists WHERE workspace_key = ? AND list_id = ?").get(ws, id);
      if (!r) return null;
      return {
        listId: r.list_id, caseId: r.case_id, template: JSON.parse(r.template_json || "{}"),
        plan: r.plan_json ? JSON.parse(r.plan_json) : null, missing: r.missing_json ? JSON.parse(r.missing_json) : null,
        createdAt: r.created_at, updatedAt: r.updated_at,
      };
    },
    listChecklistsByCase: (ws, caseId) =>
      db.prepare("SELECT list_id FROM diligence_checklists WHERE workspace_key = ? AND case_id = ? ORDER BY created_at")
        .all(ws, caseId).map((r) => r.list_id),
    putChronicle: (r) => db.prepare(`
      INSERT INTO diligence_chronicles (workspace_key, chronicle_id, case_id, title, docs_json, events_json,
        chapter_md, risks_json, todo_md, created_at, updated_at)
      VALUES (@workspace_key, @chronicle_id, @case_id, @title, @docs_json, @events_json,
        @chapter_md, @risks_json, @todo_md, @created_at, @updated_at)
      ON CONFLICT(workspace_key, chronicle_id) DO UPDATE SET
        docs_json=@docs_json, events_json=@events_json, chapter_md=@chapter_md, risks_json=@risks_json,
        todo_md=@todo_md, updated_at=@updated_at`)
      .run(r),
    getChronicle: (ws, id) => {
      const r = db.prepare("SELECT * FROM diligence_chronicles WHERE workspace_key = ? AND chronicle_id = ?").get(ws, id);
      if (!r) return null;
      return {
        chronicleId: r.chronicle_id, caseId: r.case_id, title: r.title,
        docs: JSON.parse(r.docs_json || "[]"), events: JSON.parse(r.events_json || "[]"),
        chapterMd: r.chapter_md ?? null, risks: r.risks_json ? JSON.parse(r.risks_json) : null, todoMd: r.todo_md ?? null,
        createdAt: r.created_at, updatedAt: r.updated_at,
      };
    },
    listChroniclesByCase: (ws, caseId) =>
      db.prepare("SELECT chronicle_id FROM diligence_chronicles WHERE workspace_key = ? AND case_id = ? ORDER BY created_at")
        .all(ws, caseId).map((r) => r.chronicle_id),
    // ── #6 材料面只读消费（台账/沿革的底稿来源；不写材料表）──
    materialsByCaseLite: (ws, caseId) =>
      db.prepare("SELECT material_id, title, filename, version, mime_type, document_subtype, tags_json, status, stored_path FROM case_materials WHERE workspace_key = ? AND case_id = ? ORDER BY added_at")
        .all(ws, caseId),
    materialChunks: (ws, materialId) =>
      db.prepare("SELECT chunk_id, seq, title, text FROM case_material_chunks WHERE workspace_key = ? AND material_id = ? ORDER BY seq")
        .all(ws, materialId),
  };
}

// ══════════ 服务 ══════════
// deps：dao（createDiligenceDao 产物）、caseExists、workspaceKey、authFilePath（本地鉴权挂点，可空）、
//       taskShell（r11 通用异步任务壳，可空=降级同步跑并如实标注）、llmExtract（LLM 路注入，缺省 null=不编造）、
//       now、log
export function createDiligenceService({ dao, caseExists, workspaceKey, authFilePath, taskShell = null, llmExtract = null, now, log }) {
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

  function requireTask(id) {
    const t = dao.getTask(workspaceKey, id);
    if (!t) { const e = new Error("任务不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
    return t;
  }
  function requireLedger(id) {
    const row = dao.getLedgerRow(workspaceKey, id);
    if (!row) { const e = new Error("台账不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
    return row;
  }
  function ledgerOf(id) {
    const r = requireLedger(id);
    return {
      ledgerId: r.ledger_id, caseId: r.case_id, schemaId: r.schema_id, schemaName: r.schema_name,
      fields: JSON.parse(r.fields_json || "[]"), rows: JSON.parse(r.rows_json || "[]"),
      stats: JSON.parse(r.stats_json || "{}"), status: r.status, createdAt: r.created_at, updatedAt: r.updated_at,
    };
  }
  function persistLedger(ledger) {
    dao.putLedger({
      workspace_key: workspaceKey, ledger_id: ledger.ledgerId, case_id: ledger.caseId,
      schema_id: ledger.schemaId ?? "", schema_name: ledger.schemaName, fields_json: JSON.stringify(ledger.fields),
      rows_json: JSON.stringify(ledger.rows), stats_json: JSON.stringify(ledger.stats ?? {}),
      status: ledger.status ?? "open", created_at: ledger.createdAt ?? iso(), updated_at: ledger.updatedAt ?? iso(),
    });
  }

  // ── 底稿→text_blocks（复用 #6 管线口径：PDF 文本层重放取页/序块；其余以 #6 持久分块代位，page=null 如实）──
  function blocksOfMaterial(row) {
    if (row.stored_path && existsSync(row.stored_path) && String(row.mime_type ?? "").includes("pdf")) {
      try {
        const { blocks } = extractPdfTextLayer(readFileSync(row.stored_path));
        if (Array.isArray(blocks) && blocks.length > 0) return blocks;
      } catch { /* 损坏原件落到分块代位，不编造坐标 */ }
    }
    return dao.materialChunks(workspaceKey, row.material_id).map((c) => ({
      page: null, seq: c.seq, bbox: null, text: String(c.text ?? ""),
      source: "chunk", ocrVersion: null,
    }));
  }

  function latestMaterialRows(caseId) {
    const rows = dao.materialsByCaseLite(workspaceKey, caseId);
    const latest = new Map();
    for (const r of rows) {
      const cur = latest.get(r.title);
      if (!cur || r.version > cur.version) latest.set(r.title, r);
    }
    return [...latest.values()];
  }

  function sourceDocs(caseId, materialIds) {
    requireCase(caseId);
    const latest = latestMaterialRows(caseId);
    const byId = new Map(latest.map((r) => [r.material_id, r]));
    const chosen = Array.isArray(materialIds) && materialIds.length > 0
      ? materialIds.map((mid) => {
          const row = byId.get(String(mid));
          if (!row) { const e = new Error(`材料不在该案件最新版清单中：${mid}`); e.http = 400; e.code = "MATERIAL_NOT_FOUND"; throw e; }
          return row;
        })
      : latest;
    return chosen.map((row) => ({
      docId: row.material_id,
      docTitle: row.title,
      material: row,
      blocks: blocksOfMaterial(row),
    }));
  }

  // ── tabular-review 逐字引文回验（RE-12 对照源增补节 T40-T42；施工单-10 单元四 #32 接线）──
  // 台账格值↔依据指针 quote：值非空的格必带 evidence（无引文=编造旗标）；引文不复现该值=mismatch
  // （人工改动后值不再复现于原提取引文=如实落 mismatch，note 已注「依据仍指原提取位置」）；空值格=如实未提取不入分母。
  function ledgerQuoteBack(rows, fields) {
    const entries = [];
    for (const row of rows ?? []) {
      for (const f of fields ?? []) {
        const cell = row?.cells?.[f.name];
        if (!cell || cell.value === null || cell.value === undefined || String(cell.value) === "") continue;
        entries.push({
          rowNo: row.rowNo, docId: row.docId, field: f.name, origin: cell.origin,
          value: String(cell.value), quote: typeof cell.evidence?.quote === "string" ? cell.evidence.quote : null,
        });
      }
    }
    const report = verifyQuoteBack(entries);
    return {
      mode: report.mode, checked: report.total, counts: report.counts,
      entries: report.results.map((r) => ({ rowNo: r.rowNo, field: r.field, origin: r.origin, verdict: r.verdict })),
      note: "逐字引文回验（tabular-review）：值非空的格必带依据引文；无引文=编造旗标；引文不复现该值=mismatch——提取时计算、人工编辑后重算",
    };
  }

  // ── 批量提取执行体（taskshell runner 与同步降级共用；逐件提取=逐件协作式取消检查点）──
  function runExtraction({ caseId, schemaId, materialIds, ledgerId, checkpoint }) {
    const schema = dao.getSchema(workspaceKey, schemaId);
    if (!schema) { const e = new Error("字段模板不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
    const docs = sourceDocs(caseId, materialIds);
    const cp = typeof checkpoint === "function" ? checkpoint : () => {};
    const llmFill = llmExtract
      ? (field, doc) => llmExtract(field, { docId: doc.docId, docTitle: doc.docTitle, blocks: doc.blocks })
      : null;
    const rows = [];
    const stats = { docs: docs.length, cellsFilled: 0, cellsRule: 0, cellsLlm: 0, cellsEmpty: 0, rejected: [] };
    docs.forEach((doc) => {
      cp(); // 壳契约：逐件处理前响应取消
      const one = extractLedgerRows({ name: schema.name, fields: schema.fields }, [doc], { llmFill });
      // 行号台账内全局唯一：逐件单独提取时内核每件从 1 起编，入账时重编（否则 rowNo 撞号——
      // trace 按 rowNo 只达首行、editCell(rowNo) 会改到所有撞号行；本单引文回验接线实测暴露，随接线修复）
      for (const r of one.rows) rows.push({ ...r, rowNo: rows.length + 1 });
      stats.cellsFilled += one.stats.cellsFilled;
      stats.cellsRule += one.stats.cellsRule;
      stats.cellsLlm += one.stats.cellsLlm;
      stats.cellsEmpty += one.stats.cellsEmpty;
      stats.rejected.push(...one.stats.rejected);
    });
    const at = iso();
    const normFields = normalizeFieldSchema({ name: schema.name, fields: schema.fields }).fields;
    const ledger = {
      ledgerId: ledgerId ?? randomId("dlg"),
      caseId, schemaId: schema.schemaId, schemaName: schema.name,
      fields: normFields,
      rows,
      stats: { ...stats, mode: llmFill ? "rule+llm" : "rule-only", quoteBack: ledgerQuoteBack(rows, normFields) },
      status: "open", createdAt: at, updatedAt: at,
    };
    persistLedger(ledger);
    return { ledger, csv: ledgerToCsv(ledger) };
  }

  // r11 壳接线：批量提取=长任务（入队即回；产物文件走壳白名单目录）
  if (taskShell && typeof taskShell.register === "function") {
    taskShell.register("diligence-extract", async ({ payload, artifactDir, checkpoint }) => {
      const { ledger, csv } = runExtraction({ ...payload, checkpoint });
      if (artifactDir) {
        const { writeFileSync } = await import("node:fs");
        const { join } = await import("node:path");
        writeFileSync(join(artifactDir, "diligence-ledger.csv"), CSV_BOM + csv, "utf-8");
        writeFileSync(join(artifactDir, "diligence-ledger.json"), JSON.stringify(ledger, null, 2), "utf-8");
      }
      return { fileName: "diligence-ledger.csv", ledgerId: ledger.ledgerId };
    });
  }

  function createTask({ caseId, group, title, subtasks, fromPreset }) {
    requireCase(caseId);
    const at = iso();
    if (fromPreset) {
      const preset = (BOARD_PRESET[group] ?? []).find((p) => p.title === fromPreset);
      if (!preset) { const e = new Error(`预设任务不存在：${fromPreset}`); e.http = 400; e.code = "PRESET_NOT_FOUND"; throw e; }
      const taskId = randomId("dlt");
      dao.upsertTask({
        workspace_key: workspaceKey, task_id: taskId, case_id: caseId, group_name: group, title: preset.title,
        status: "pending", subtasks_json: JSON.stringify((preset.subtasks ?? []).map((t, i) => ({ subId: `sub${i + 1}`, title: t, done: false }))),
        flow_ref_json: null, confirmed_by: null, confirmed_at: null, created_at: at, updated_at: at,
      });
      return dao.getTask(workspaceKey, taskId);
    }
    const g = String(group ?? "");
    if (!isBoardGroup(g)) { const e = new Error(`看板分组必须是三分组之一：${BOARD_GROUPS.join("/")}`); e.http = 400; e.code = "BAD_GROUP"; throw e; }
    const t = String(title ?? "").trim();
    if (!t || t.length > 120) { const e = new Error("任务标题不能为空且不超过 120 字"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
    const subs = Array.isArray(subtasks) ? subtasks.map((s, i) => ({ subId: `sub${i + 1}`, title: String(s ?? "").trim(), done: false })).filter((s) => s.title) : [];
    const taskId = randomId("dlt");
    dao.upsertTask({
      workspace_key: workspaceKey, task_id: taskId, case_id: caseId, group_name: g, title: t,
      status: "pending", subtasks_json: JSON.stringify(subs), flow_ref_json: null,
      confirmed_by: null, confirmed_at: null, created_at: at, updated_at: at,
    });
    return dao.getTask(workspaceKey, taskId);
  }

  function taskAction(taskId, body) {
    const action = String(body?.action ?? "");
    const at = iso();
    let task = requireTask(taskId);
    const put = (t) => {
      dao.upsertTask({
        workspace_key: workspaceKey, task_id: t.taskId, case_id: t.caseId, group_name: t.group, title: t.title,
        status: t.status, subtasks_json: JSON.stringify(t.subtasks), flow_ref_json: t.flowRef ? JSON.stringify(t.flowRef) : null,
        confirmed_by: t.confirmedBy, confirmed_at: t.confirmedAt, created_at: t.createdAt, updated_at: t.updatedAt,
      });
      return dao.getTask(workspaceKey, taskId);
    };
    switch (action) {
      case "start":
      case "submit-confirmation":
      case "return": {
        const to = action === "start" ? "in_progress" : action === "submit-confirmation" ? "pending_confirmation" : "in_progress";
        if (action === "return" && task.status !== "pending_confirmation")
          throw new Error(`仅「待确认」状态可退回（当前：${task.status}）`);
        return put(transitionTask(task, to, at));
      }
      case "confirm":
        return put(confirmTask(task, String(body?.by ?? ""), at));
      case "add-subtask":
        return put(addSubtask(task, String(body?.subId ?? `sub${task.subtasks.length + 1}`), String(body?.title ?? "")));
      case "remove-subtask":
        return put(removeSubtask(task, String(body?.subId ?? "")));
      case "retitle-subtask":
        return put(retitleSubtask(task, String(body?.subId ?? ""), String(body?.title ?? "")));
      case "mark-subtask":
        return put(markSubtask(task, String(body?.subId ?? ""), Boolean(body?.done)));
      case "bind-flow":
        return put(bindFlow(task, body?.flowRef ?? null));
      case "retitle": {
        const t = String(body?.title ?? "").trim();
        if (!t || t.length > 120) throw new Error("任务标题不能为空且不超过 120 字");
        return put({ ...task, title: t, updatedAt: at });
      }
      default:
        throw new Error(`未知任务动作：${action || "(空)"}`);
    }
  }

  function saveSchema({ caseId, name, fields }) {
    requireCase(caseId);
    const def = { name: String(name ?? ""), fields: Array.isArray(fields) ? fields : [] };
    const check = validateFieldSchema(def);
    if (!check.ok) { const e = new Error(`字段模板不合法（${check.code}）：${check.message}`); e.http = 400; e.code = "SCHEMA_INVALID"; throw e; }
    const norm = normalizeFieldSchema(def);
    const at = iso();
    const schemaId = randomId("dschema");
    dao.putSchema({
      workspace_key: workspaceKey, schema_id: schemaId, case_id: caseId, name: norm.name,
      fields_json: JSON.stringify(norm.fields), created_at: at, updated_at: at,
    });
    return dao.getSchema(workspaceKey, schemaId);
  }

  function chronicleCollect(chronicleId, body) {
    const chronicle = dao.getChronicle(workspaceKey, chronicleId);
    if (!chronicle) { const e = new Error("沿革档案不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
    requireCase(chronicle.caseId);
    const refs = Array.isArray(body?.refs) ? body.refs : [];
    const latest = new Map(latestMaterialRows(chronicle.caseId).map((r) => [r.material_id, r]));
    const docs = [...chronicle.docs];
    for (const ref of refs) {
      const row = latest.get(String(ref?.docId ?? ""));
      if (!row) { const e = new Error(`材料不在该案件最新版清单中：${ref?.docId}`); e.http = 400; e.code = "MATERIAL_NOT_FOUND"; throw e; }
      const kind = isChronicleKind(String(ref?.kind ?? "")) ? String(ref.kind) : "其他";
      if (docs.some((d) => d.docId === row.material_id)) continue;
      docs.push({ docId: row.material_id, docTitle: row.title, kind, channel: "user", blocks: blocksOfMaterial(row) });
    }
    const searchKinds = Array.isArray(body?.searchKinds) ? body.searchKinds.filter(isChronicleKind) : [];
    if (searchKinds.length > 0) {
      const pool = [...latest.values()].map((row) => ({ docId: row.material_id, docTitle: row.title, blocks: blocksOfMaterial(row) }));
      for (const hit of searchInProject(pool, searchKinds)) {
        if (docs.some((d) => d.docId === hit.docId)) continue;
        docs.push({ docId: hit.docId, docTitle: hit.docTitle, kind: hit.kind, channel: "search" });
      }
    }
    // 检索通道命中的材料补挂块（汇集面统一带块，章节提取即取即用）
    const withBlocks = docs.map((d) => {
      if (Array.isArray(d.blocks) && d.blocks.length > 0) return d;
      const row = latest.get(d.docId);
      return row ? { ...d, blocks: blocksOfMaterial(row) } : d;
    });
    dao.putChronicle({
      workspace_key: workspaceKey, chronicle_id: chronicleId, case_id: chronicle.caseId, title: chronicle.title,
      docs_json: JSON.stringify(withBlocks), events_json: JSON.stringify(chronicle.events),
      chapter_md: chronicle.chapterMd, risks_json: chronicle.risks ? JSON.stringify(chronicle.risks) : null,
      todo_md: chronicle.todoMd, created_at: chronicle.createdAt, updated_at: iso(),
    });
    return { chronicleId, docs: withBlocks.map(({ docId, docTitle, kind, channel }) => ({ docId, docTitle, kind, channel })) };
  }

  // ── HTTP 面（/api/diligence/*；鉴权同材料面）──
  async function httpHandler(req, res, url) {
    const path = url.pathname;
    if (!path.startsWith("/api/diligence/")) return false;
    const send = (code, obj, headers = {}) => {
      if (res.headersSent) { res.end(); return; }
      res.writeHead(code, { "content-type": "application/json; charset=utf-8", ...headers });
      res.end(typeof obj === "string" ? obj : JSON.stringify(obj));
    };
    try {
      if (!localAuthOk(req)) { send(401, { error: { code: "UNAUTHORIZED", message: "缺少有效的本地访问凭据" } }); return true; }
      const m = req.method ?? "GET";
      const body = m === "POST" || m === "PATCH" ? await readJsonBody(req) : {};
      const seg = path.slice("/api/diligence/".length).split("/").filter(Boolean);

      // ── A 任务看板（行为 1-5）──
      if (seg[0] === "overview" && m === "GET") {
        const caseId = url.searchParams.get("caseId") ?? "";
        requireCase(caseId);
        const tasks = dao.listTasksByCase(workspaceKey, caseId).map((id) => dao.getTask(workspaceKey, id));
        send(200, { groups: BOARD_GROUPS, preset: BOARD_PRESET, board: boardProjection(tasks) });
        return true;
      }
      if (seg[0] === "tasks" && seg.length === 1 && m === "POST") { send(200, createTask(body)); return true; }
      if (seg[0] === "tasks" && seg.length === 1 && m === "GET") {
        const caseId = url.searchParams.get("caseId") ?? "";
        requireCase(caseId);
        const tasks = dao.listTasksByCase(workspaceKey, caseId).map((id) => dao.getTask(workspaceKey, id));
        send(200, { tasks, board: boardProjection(tasks) });
        return true;
      }
      if (seg[0] === "tasks" && seg.length === 2 && m === "PATCH") { send(200, taskAction(seg[1], body)); return true; }
      if (seg[0] === "tasks" && seg.length === 2 && m === "GET") { send(200, requireTask(seg[1])); return true; }
      if (seg[0] === "tasks" && seg[2] === "results" && seg.length === 3 && m === "POST") {
        const task = requireTask(seg[1]);
        const versions = dao.listResults(workspaceKey, task.taskId).map((meta) => dao.getResult(workspaceKey, task.taskId, meta.version));
        const saved = saveTaskResult(versions, String(body?.content ?? ""), String(body?.by ?? ""), iso());
        dao.putResult(workspaceKey, task.taskId, saved);
        noop(`task ${task.taskId} result v${saved.version} saved`);
        send(200, saved);
        return true;
      }
      if (seg[0] === "tasks" && seg[2] === "results" && seg.length === 3 && m === "GET") {
        const task = requireTask(seg[1]);
        send(200, { versions: dao.listResults(workspaceKey, task.taskId) });
        return true;
      }
      if (seg[0] === "tasks" && seg[2] === "results" && seg.length === 4 && m === "GET") {
        const task = requireTask(seg[1]);
        const hit = dao.getResult(workspaceKey, task.taskId, Number(seg[3]));
        if (!hit) { const e = new Error(`版本不存在：v${seg[3]}`); e.http = 404; e.code = "NOT_FOUND"; throw e; }
        send(200, hit); // 点版本号切换查看（行为 5）
        return true;
      }

      // ── B 字段模板（三态一源 S1-S3）──
      if (seg[0] === "schemas" && seg.length === 1 && m === "POST") { send(200, saveSchema(body)); return true; }
      if (seg[0] === "schemas" && seg.length === 1 && m === "GET") {
        const caseId = url.searchParams.get("caseId") ?? "";
        requireCase(caseId);
        send(200, { schemas: dao.listSchemasByCase(workspaceKey, caseId).map((id) => dao.getSchema(workspaceKey, id)) });
        return true;
      }
      if (seg[0] === "schemas" && seg[2] === "export" && m === "GET") {
        const schema = dao.getSchema(workspaceKey, seg[1]);
        if (!schema) { const e = new Error("字段模板不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
        send(200, { schemaId: schema.schemaId, json: exportSchemaJson({ name: schema.name, fields: schema.fields }) });
        return true;
      }
      if (seg[0] === "schemas" && seg[2] === "import" && m === "POST") {
        const caseId = String(body?.caseId ?? "");
        requireCase(caseId);
        const imp = importSchemaJson(String(body?.json ?? ""));
        if (!imp.ok) { const e = new Error(`导入被拒（${imp.code}）：${imp.message}`); e.http = 400; e.code = "IMPORT_REJECTED"; throw e; }
        const at = iso();
        const schemaId = randomId("dschema");
        dao.putSchema({
          workspace_key: workspaceKey, schema_id: schemaId, case_id: caseId, name: imp.schema.name,
          fields_json: JSON.stringify(imp.schema.fields), created_at: at, updated_at: at,
        });
        send(200, { schemaId, schema: dao.getSchema(workspaceKey, schemaId) });
        return true;
      }
      if (seg[0] === "schemas" && seg[2] === "prompt" && m === "GET") {
        const schema = dao.getSchema(workspaceKey, seg[1]);
        if (!schema) { const e = new Error("字段模板不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
        send(200, { prompt: renderExtractionPrompt({ name: schema.name, fields: schema.fields }), fields: schemaFieldNames({ name: schema.name, fields: schema.fields }) });
        return true;
      }

      // ── B 批量提取（taskshell 异步；无壳降级同步并如实标注）──
      if (seg[0] === "extract" && seg.length === 1 && m === "POST") {
        const caseId = String(body?.caseId ?? "");
        const schemaId = String(body?.schemaId ?? "");
        requireCase(caseId);
        if (!dao.getSchema(workspaceKey, schemaId)) { const e = new Error("字段模板不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
        const materialIds = Array.isArray(body?.materialIds) ? body.materialIds.map(String) : [];
        if (materialIds.length === 0) { const e = new Error("请选择至少一件底稿材料（批量提取面向多件格式相近底稿）"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
        if (taskShell) {
          const t = taskShell.create("diligence-extract", { caseId, schemaId, materialIds }, { ref: caseId });
          send(200, { mode: "async", task: t });
          return true;
        }
        const { ledger } = runExtraction({ caseId, schemaId, materialIds });
        send(200, { mode: "sync-degraded", ledger });
        return true;
      }
      if (seg[0] === "extract" && seg.length === 2 && m === "GET") {
        if (!taskShell) { const e = new Error("本桥未接异步任务壳（降级同步模式无任务可查）"); e.http = 409; e.code = "NO_SHELL"; throw e; }
        send(200, taskShell.get(seg[1]));
        return true;
      }

      // ── B 台账（查看/编辑/回溯/CSV）──
      if (seg[0] === "ledgers" && seg.length === 1 && m === "GET") {
        const caseId = url.searchParams.get("caseId") ?? "";
        requireCase(caseId);
        send(200, { ledgers: dao.listLedgersByCase(workspaceKey, caseId).map((id) => { const l = ledgerOf(id); return { ledgerId: l.ledgerId, schemaName: l.schemaName, rows: l.rows.length, status: l.status, updatedAt: l.updatedAt }; }) });
        return true;
      }
      if (seg[0] === "ledgers" && seg.length === 2 && m === "GET") { send(200, ledgerOf(seg[1])); return true; }
      if (seg[0] === "ledgers" && seg[2] === "cells" && m === "PATCH") {
        const ledger = ledgerOf(seg[1]);
        const out = editCell(ledger, Number(body?.rowNo), String(body?.field ?? ""), String(body?.value ?? ""), String(body?.by ?? ""), iso());
        // 逐字引文回验随编辑重算（RE-12 T40-T42 #32 接线）：人工改动后值与原提取引文的关系即时回呈现
        const editedLedger = { ...out.ledger, schemaId: ledger.schemaId, createdAt: ledger.createdAt };
        const stats = { ...editedLedger.stats, quoteBack: ledgerQuoteBack(editedLedger.rows, editedLedger.fields) };
        persistLedger({ ...editedLedger, stats });
        send(200, { ledgerId: seg[1], rowNo: Number(body?.rowNo), field: String(body?.field ?? ""), origin: out.origin, quoteBack: stats.quoteBack });
        return true;
      }
      if (seg[0] === "ledgers" && seg[2] === "trace" && m === "GET") {
        const ledger = ledgerOf(seg[1]);
        const rowNo = Number(url.searchParams.get("rowNo"));
        const field = String(url.searchParams.get("field") ?? "");
        send(200, traceOf(ledger, rowNo, field)); // 行为 8：回溯跳转载荷（四元组口径）
        return true;
      }
      if (seg[0] === "ledgers" && seg[2] === "csv" && m === "GET") {
        const ledger = ledgerOf(seg[1]);
        send(200, CSV_BOM + ledgerToCsv(ledger), {
          "content-type": "text/csv; charset=utf-8",
          "content-disposition": `attachment; filename="${seg[1]}.csv"`,
        });
        return true;
      }

      // ── C 清单（行为 11-12）──
      if (seg[0] === "checklists" && seg.length === 1 && m === "POST") {
        const caseId = String(body?.caseId ?? "");
        requireCase(caseId);
        let template = DEFAULT_CHECKLIST_TEMPLATE;
        if (Array.isArray(body?.items) && body.items.length > 0) {
          template = {
            templateId: randomId("dlist"),
            name: String(body?.name ?? "自定义尽调资料清单").slice(0, 60),
            items: body.items.map((it, i) => ({
              itemId: String(it?.itemId ?? `x${i + 1}`), category: String(it?.category ?? "未分组").slice(0, 30),
              name: String(it?.name ?? "").trim(), required: Boolean(it?.required),
              ...(it?.hint ? { hint: String(it.hint).slice(0, 80) } : {}),
            })).filter((it) => it.name),
          };
          if (template.items.length === 0) { const e = new Error("自定义清单至少含一个事项"); e.http = 400; e.code = "BAD_REQUEST"; throw e; }
        }
        const at = iso();
        const listId = randomId("dlist");
        dao.putChecklist({
          workspace_key: workspaceKey, list_id: listId, case_id: caseId, template_json: JSON.stringify(template),
          plan_json: null, missing_json: null, created_at: at, updated_at: at,
        });
        send(200, dao.getChecklist(workspaceKey, listId));
        return true;
      }
      if (seg[0] === "checklists" && seg.length === 1 && m === "GET") {
        const caseId = url.searchParams.get("caseId") ?? "";
        requireCase(caseId);
        send(200, { checklists: dao.listChecklistsByCase(workspaceKey, caseId).map((id) => dao.getChecklist(workspaceKey, id)) });
        return true;
      }
      if (seg[0] === "checklists" && seg[2] === "organize" && m === "POST") {
        const list = dao.getChecklist(workspaceKey, seg[1]);
        if (!list) { const e = new Error("清单不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
        const materials = latestMaterialRows(list.caseId).map((r) => ({
          materialId: r.material_id, title: r.title, documentSubtype: r.document_subtype ?? "",
          tags: (() => { try { return JSON.parse(r.tags_json || "[]"); } catch { return []; } })(),
        }));
        const plan = organizePlan(list.template, materials);
        dao.putChecklist({
          workspace_key: workspaceKey, list_id: list.listId, case_id: list.caseId, template_json: JSON.stringify(list.template),
          plan_json: JSON.stringify(plan), missing_json: list.missing ? JSON.stringify(list.missing) : null,
          created_at: list.createdAt, updated_at: iso(),
        });
        send(200, plan);
        return true;
      }
      if (seg[0] === "checklists" && seg[2] === "missing" && m === "POST") {
        const list = dao.getChecklist(workspaceKey, seg[1]);
        if (!list) { const e = new Error("清单不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
        const materials = latestMaterialRows(list.caseId).map((r) => ({
          materialId: r.material_id, title: r.title, documentSubtype: r.document_subtype ?? "", tags: [],
        }));
        const plan = list.plan ?? organizePlan(list.template, materials);
        const claims = Array.isArray(body?.claims) ? body.claims.map((c) => ({ itemId: String(c?.itemId ?? ""), materialId: String(c?.materialId ?? "") })) : [];
        const outcome = checkMissing({ template: list.template, assignments: plan.assignments, claims, materials });
        dao.putChecklist({
          workspace_key: workspaceKey, list_id: list.listId, case_id: list.caseId, template_json: JSON.stringify(list.template),
          plan_json: JSON.stringify(plan), missing_json: JSON.stringify(outcome), created_at: list.createdAt, updated_at: iso(),
        });
        send(200, outcome);
        return true;
      }

      // ── D 历史沿革（行为 13-16）──
      if (seg[0] === "chronicles" && seg.length === 1 && m === "POST") {
        const caseId = String(body?.caseId ?? "");
        requireCase(caseId);
        const at = iso();
        const chronicleId = randomId("dchr");
        dao.putChronicle({
          workspace_key: workspaceKey, chronicle_id: chronicleId, case_id: caseId,
          title: String(body?.title ?? "历史沿革核查").slice(0, 80),
          docs_json: "[]", events_json: "[]", chapter_md: null, risks_json: null, todo_md: null,
          created_at: at, updated_at: at,
        });
        send(200, dao.getChronicle(workspaceKey, chronicleId));
        return true;
      }
      if (seg[0] === "chronicles" && seg.length === 1 && m === "GET") {
        const caseId = url.searchParams.get("caseId") ?? "";
        requireCase(caseId);
        send(200, { chronicles: dao.listChroniclesByCase(workspaceKey, caseId).map((id) => { const c = dao.getChronicle(workspaceKey, id); return { chronicleId: c.chronicleId, title: c.title, docs: c.docs.length, hasChapter: Boolean(c.chapterMd), updatedAt: c.updatedAt }; }) });
        return true;
      }
      if (seg[0] === "chronicles" && seg.length === 2 && m === "GET") {
        const c = dao.getChronicle(workspaceKey, seg[1]);
        if (!c) { const e = new Error("沿革档案不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
        send(200, c);
        return true;
      }
      if (seg[0] === "chronicles" && seg[2] === "collect" && m === "POST") { send(200, chronicleCollect(seg[1], body)); return true; }
      if (seg[0] === "chronicles" && seg[2] === "chapter" && m === "POST") {
        const chronicle = dao.getChronicle(workspaceKey, seg[1]);
        if (!chronicle) { const e = new Error("沿革档案不存在"); e.http = 404; e.code = "NOT_FOUND"; throw e; }
        const { events, undated } = extractTimelineEvents(chronicle.docs);
        const chapterMd = buildChronicleChapter(chronicle.title, chronicle.docs, events, undated);
        const { risks, todoMd } = buildRiskAndTodo(chronicle.docs, events, undated);
        dao.putChronicle({
          workspace_key: workspaceKey, chronicle_id: chronicle.chronicleId, case_id: chronicle.caseId, title: chronicle.title,
          docs_json: JSON.stringify(chronicle.docs), events_json: JSON.stringify(events),
          chapter_md: chapterMd, risks_json: JSON.stringify(risks), todo_md: todoMd,
          created_at: chronicle.createdAt, updated_at: iso(),
        });
        send(200, { chronicleId: chronicle.chronicleId, events: events.length, undated, risks: risks.length, chapterMd, todoMd });
        return true;
      }
      if (seg[0] === "chronicles" && seg[2] === "word" && m === "GET") {
        const chronicle = dao.getChronicle(workspaceKey, seg[1]);
        if (!chronicle || !chronicle.chapterMd) { const e = new Error("沿革章节未生成，请先执行章节生成"); e.http = 409; e.code = "CHAPTER_NOT_READY"; throw e; }
        const md = chronicleWordMarkdown(chronicle.chapterMd, chronicle.todoMd ?? "");
        const docx = markdownToLegalDocx(md);
        if (res.headersSent) { res.end(); return true; }
        res.writeHead(200, {
          "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          "content-disposition": `attachment; filename="${chronicle.chronicleId}.docx"`,
        });
        res.end(docx);
        return true;
      }

      send(404, { error: { code: "NOT_FOUND", message: `未知的尽调路由：${m} ${path}` } });
      return true;
    } catch (e) {
      send(e?.http ?? 500, { error: { code: e?.code ?? "DILIGENCE_ERROR", message: String(e?.message ?? e) } });
      return true;
    }
  }

  return {
    httpHandler,
    // 供探针/后续 UI 面直调的稳定面（不走 HTTP 也能跑全链）
    createTask, taskAction, saveSchema, runExtraction, sourceDocs,
    overviewOf: (caseId) => {
      const tasks = dao.listTasksByCase(workspaceKey, caseId).map((id) => dao.getTask(workspaceKey, id));
      return { groups: BOARD_GROUPS, preset: BOARD_PRESET, board: boardProjection(tasks) };
    },
  };
}
