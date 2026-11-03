// 功能 #35 Flow 工作流：装配入口留在本文件，本轮不接线。
// 内核 @juscite/flow 已在盘（packages/juscite-flow，自有 package.json）。
// index.mjs、engine.mjs、dsl.mjs，以及 capabilities / line-manifest / dry-run，都在；
// materialize 会把该包拷进桥随包。本文件不 import 它们。
// 本轮运行时消费不走本函数：
//   bridge_host 只 createFlowGate（flow_gate_service.mjs），不调用 createFlowEngineService，
//   也不把 flow 引擎 RPC 挂上桥；
//   尽调 diligence_service 静态 import quote-back.mjs。
// 本文件导出 FLOW_ENGINE_DDL（字符串，不依赖内核）和 createFlowEngineService。
// createFlowEngineService 在入口故意 fail-closed，直到另一次接线决定：
// 抛 ERR_MODULE_NOT_FOUND，消息含「拒绝装配」（R3 S13 锁定）。不要拆 throw，
// 不要从 bridge_host 调用本函数。
// 抛出文案里的「不在本分支」是被锁住的历史信号，不是当前文件清单。
import { createHash } from "node:crypto";
import { join } from "node:path";

export const STUDIO_BUNDLE_FORMAT = "juscite-workflow-studio"; // 自写格式名（E3 导入导出对应物，不建内置商店）
export const STUDIO_BUNDLE_VERSION = 1;

// DDL 单源（迁移 0022_flow_engine 与 flow_engine_synthetic 共用同一份——material/edisc 同法）。
// 事件日志=只追加事件流（journal）+HMAC 链（attestation）；map 逐项 checkpoint 表；AI-run 一等记录表。
export const FLOW_ENGINE_DDL = `
    CREATE TABLE IF NOT EXISTS flow_definitions (
      id TEXT PRIMARY KEY,
      kind TEXT NOT NULL DEFAULT 'local' CHECK (kind IN ('local','builtin')),
      status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','builtin')),
      version INTEGER NOT NULL DEFAULT 1,
      title TEXT NOT NULL,
      definition_json TEXT NOT NULL,
      definition_hash TEXT NOT NULL,
      layout_json TEXT,
      published_hash TEXT,
      author TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS flow_runs (
      id TEXT PRIMARY KEY,
      definition_id TEXT NOT NULL,
      definition_hash TEXT NOT NULL,
      definition_json TEXT NOT NULL DEFAULT '{}',
      status TEXT NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('QUEUED','RUNNING','WAITING','SUSPENDED','SUCCEEDED','FAILED','CANCELLED')),
      input_json TEXT NOT NULL DEFAULT '{}',
      ref TEXT,
      actor TEXT,
      dry_run INTEGER NOT NULL DEFAULT 0,
      budget_json TEXT,
      deadline_at TEXT,
      context_json TEXT NOT NULL DEFAULT '{}',
      waiting_json TEXT,
      pause_requested INTEGER NOT NULL DEFAULT 0,
      error_code TEXT,
      error_message TEXT,
      created_at TEXT NOT NULL,
      finished_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_flow_runs_status ON flow_runs (status);
    CREATE INDEX IF NOT EXISTS idx_flow_runs_ref ON flow_runs (ref);
    CREATE TABLE IF NOT EXISTS flow_run_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL,
      seq INTEGER NOT NULL,
      kind TEXT NOT NULL,
      node_id TEXT,
      level TEXT NOT NULL DEFAULT 'info',
      message_json TEXT NOT NULL DEFAULT '{}',
      prev_hash TEXT NOT NULL DEFAULT '',
      hash TEXT NOT NULL,
      created_at TEXT NOT NULL,
      FOREIGN KEY (run_id) REFERENCES flow_runs(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_flow_run_events_run ON flow_run_events (run_id, id);
    CREATE TABLE IF NOT EXISTS flow_run_items (
      run_id TEXT NOT NULL,
      node_id TEXT NOT NULL,
      item_index INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','succeeded','suspended','failed')),
      result_json TEXT NOT NULL DEFAULT '{}',
      updated_at TEXT NOT NULL,
      PRIMARY KEY (run_id, node_id, item_index),
      FOREIGN KEY (run_id) REFERENCES flow_runs(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS flow_capabilities (
      id TEXT PRIMARY KEY,
      display_name TEXT,
      risk TEXT NOT NULL CHECK (risk IN ('read','write','external')),
      idempotency TEXT NOT NULL CHECK (idempotency IN ('read','idempotent-write','non-idempotent')),
      approval TEXT,
      input_schema_json TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS flow_ai_runs (
      id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL,
      node_id TEXT NOT NULL,
      model_code TEXT NOT NULL,
      prompt_version TEXT NOT NULL,
      risk_level TEXT,
      risk_score REAL,
      findings_count INTEGER,
      findings_json TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL,
      FOREIGN KEY (run_id) REFERENCES flow_runs(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_flow_ai_runs_run ON flow_ai_runs (run_id, id);
    CREATE TABLE IF NOT EXISTS flow_artifacts (
      id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL,
      node_id TEXT NOT NULL,
      type TEXT NOT NULL,
      version INTEGER NOT NULL DEFAULT 1,
      payload_json TEXT NOT NULL,
      payload_digest TEXT NOT NULL,
      cite_receipt_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL,
      FOREIGN KEY (run_id) REFERENCES flow_runs(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_flow_artifacts_run ON flow_artifacts (run_id, id);
`;

// 内置只读流程（E2 双来源的 builtin 半边；compile 不过=启动即崩 fail-closed）
const BUILTIN_FLOW_DEFINITION = {
  formatVersion: 2,
  id: "builtin.six-stage-line",
  version: 1,
  title: "通用办案线六阶段骨架（内置只读）",
  description: "内置只读样例：六阶段顺序链。编辑请另存草稿（双来源：builtin 恒只读）。",
  inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] },
  nodes: [
    { id: "stage.intake", type: "activity", title: "材料进来", dependsOn: [], capability: "line.intake.materials", input: { lineId: { kind: "input", path: "lineId" } } },
    { id: "stage.evidence", type: "activity", title: "证据固定", dependsOn: ["stage.intake"], capability: "line.evidence.fix", input: { lineId: { kind: "input", path: "lineId" } } },
    { id: "stage.facts", type: "activity", title: "事实整理", dependsOn: ["stage.evidence"], capability: "line.facts.reconcile", input: { lineId: { kind: "input", path: "lineId" } } },
    { id: "stage.compute", type: "activity", title: "计算", dependsOn: ["stage.facts"], capability: "line.compute.ninecalc", input: { lineId: { kind: "input", path: "lineId" } } },
    { id: "stage.drafting", type: "activity", title: "文书", dependsOn: ["stage.compute"], capability: "line.drafting.assemble", input: { lineId: { kind: "input", path: "lineId" } } },
    { id: "stage.deadlines", type: "activity", title: "程序期限", dependsOn: ["stage.drafting"], capability: "line.deadlines.calendar", input: { lineId: { kind: "input", path: "lineId" } } },
  ],
  groups: [{ id: "g.head", title: "材料→证据", nodeIds: ["stage.intake", "stage.evidence"] }],
  output: [
    { nodeId: "stage.drafting", type: "line.stage.drafting", citations: ["builtin.six-stage-line"] },
  ],
};

const nowIso = () => new Date().toISOString();
const defHashOf = (def) => createHash("sha256").update(JSON.stringify(def)).digest("hex");

export function createFlowEngineService({
  db, gate, trustDir = null, config = {}, studioEnabled = () => true, loadPersistedCapabilities = true,
  agentExecutor = null, // 【#35 尾巴①】真模型 agent 执行器（runtime-port 域面注入；null=全合成旧状）
} = {}) {
  void db; void gate; void trustDir; void config; void studioEnabled; void loadPersistedCapabilities; void agentExecutor;
  // 内核在盘。这里仍拒绝装配：接线决定未做。勿删这条 throw；bridge_host 不得调用本函数。
  // code 与文案保持不动（S13：ERR_MODULE_NOT_FOUND，消息含「拒绝装配」）。
  const missing = new Error("Flow 引擎入口缺失：packages/juscite-flow/src/index.mjs、engine.mjs、dsl.mjs 不在本分支，拒绝装配");
  missing.code = "ERR_MODULE_NOT_FOUND";
  throw missing;
  if (!db || !gate) throw new Error("flow_engine_service 需要 db 与 flow gate 机制件");
  const capabilities = createCapabilityRegistry();
  const builtinIds = registerBuiltinLineCapabilities(capabilities);
  // 【#34 事实核验】能力面追加注册（14 实例；write 类恰 4——见 fact-verification.mjs 控权表）
  registerFactVerificationCapabilities(capabilities);

  // 自定义能力持久化（重启后注册面不丢——builtin 零实例约定只约束内置面）
  if (loadPersistedCapabilities) {
    for (const row of db.prepare("SELECT * FROM flow_capabilities").all()) {
      try { capabilities.register({ id: row.id, displayName: row.display_name ?? undefined, risk: row.risk, idempotency: row.idempotency, approval: row.approval ?? undefined, inputSchema: row.input_schema_json ? JSON.parse(row.input_schema_json) : undefined }); } catch { /* 注册面行损坏不阻断启动；detail 面经 flowCapList 可见缺项 */ }
    }
  }

  // 内置只读流程种子（幂等：已存在不覆盖——用户不可写 builtin，种子也不自改）
  const compiled = compileDefinition(BUILTIN_FLOW_DEFINITION);
  if (!compiled.ok) throw new FlowEngineError("VALIDATION", `内置流程定义编译不过（${compiled.diagnostics[0]?.path}: ${compiled.diagnostics[0]?.message}）`);
  const ts = nowIso();
  db.prepare(`INSERT INTO flow_definitions (id, kind, status, version, title, definition_json, definition_hash, layout_json, published_hash, author, created_at, updated_at)
              VALUES (?, 'builtin', 'builtin', 1, ?, ?, ?, NULL, NULL, 'system', ?, ?)
              ON CONFLICT(id) DO NOTHING`)
    .run(BUILTIN_FLOW_DEFINITION.id, BUILTIN_FLOW_DEFINITION.title, JSON.stringify(BUILTIN_FLOW_DEFINITION), defHashOf(BUILTIN_FLOW_DEFINITION), ts, ts);

  // 合成引用核验钩子（D7 先校验后发布）：v1 桥内无真引用回执生产者，回执显式 mode=synthetic——
  // 真核验接线（#14 引证核验服务）挂后续集成单，不伪造 verified:true。
  let receiptSeq = 0;
  const citeVerify = ({ citations }) => ({
    mode: "synthetic",
    receiptId: `syn_receipt_${(++receiptSeq).toString(36)}`,
    citationCount: Array.isArray(citations) ? citations.length : 0,
  });

  const engine = createFlowEngine({
    db, gate, capabilities,
    // 【#34 事实核验】执行器合成：事实核验领域执行器在前（未知面返回 null），办案线合成执行器兜底
    // 【#35 尾巴①】真模型执行器（agentExecutor）排最前：agent 节点打真模型轮；dry-run 让位（执行器内
    // ctx.dryRun=true 返回 null）保证 flowLineDryRun/flowFactVerifyDryRun 等合成面语义不变。
    executors: agentExecutor
      ? composeExecutors(agentExecutor, createFactVerificationExecutors(), createDryRunExecutors())
      : composeExecutors(createFactVerificationExecutors(), createDryRunExecutors()),
    citeVerify,
    config,
    dataRoot: trustDir, // D2④：trust 路径越出数据根=拒绝装载
    trustKeyPath: trustDir ? join(trustDir, "trust", "attestation.key") : null,
  });

  // ── Studio 持久化面（E1 草稿模型/E2 双来源/E3 操作族/E4 布局分离）──
  function metaOf(row) {
    return { id: row.id, source: row.kind, status: row.status, version: row.version, title: row.title, updatedAt: row.updated_at, ...(row.published_hash ? { publishedHash: row.published_hash } : {}) };
  }
  const getDefRow = (id) => db.prepare("SELECT * FROM flow_definitions WHERE id = ?").get(id);
  function assertStudioOpen() {
    if (!studioEnabled()) throw new FlowEngineError("VALIDATION", "Flow Studio 面已停用（enableStudio=false）——Studio 面不可达");
  }
  function assertNotBuiltin(row) {
    if (row.kind === "builtin") throw new FlowEngineError("VALIDATION", `内置流程只读（${row.id}）——编辑请另存草稿`);
  }
  function upsertDraft({ id, title, definition, layout = null, author = "律师" }) {
    assertStudioOpen();
    const c = compileDefinition(definition);
    if (!c.ok) throw new FlowEngineError("VALIDATION", `定义编译不过（${c.diagnostics.length} 条诊断，首条 ${c.diagnostics[0]?.path}: ${c.diagnostics[0]?.message}）`, { diagnostics: c.diagnostics });
    const now = nowIso();
    if (id) {
      const row = getDefRow(id);
      if (!row) throw new FlowEngineError("NOT_FOUND", `草稿不存在 ${id}`);
      assertNotBuiltin(row);
      const version = row.version + 1;
      db.prepare("UPDATE flow_definitions SET status='draft', version=?, title=?, definition_json=?, definition_hash=?, layout_json=?, author=?, updated_at=? WHERE id=?")
        .run(version, definition.title ?? row.title, JSON.stringify(definition), defHashOf(definition), layout === null ? row.layout_json : JSON.stringify(layout), author, now, id);
      return metaOf(getDefRow(id));
    }
    const newId = "flow.draft." + Math.random().toString(36).slice(2, 10);
    db.prepare(`INSERT INTO flow_definitions (id, kind, status, version, title, definition_json, definition_hash, layout_json, author, created_at, updated_at)
                VALUES (?, 'local', 'draft', 1, ?, ?, ?, ?, ?, ?, ?)`)
      .run(newId, definition.title ?? "未命名流程", JSON.stringify(definition), defHashOf(definition), layout ? JSON.stringify(layout) : null, author, now, now);
    return metaOf(getDefRow(newId));
  }
  function publishDraft({ id }) {
    assertStudioOpen();
    const row = getDefRow(id);
    if (!row) throw new FlowEngineError("NOT_FOUND", `定义不存在 ${id}`);
    assertNotBuiltin(row);
    const def = JSON.parse(row.definition_json);
    const c = compileDefinition(def);
    if (!c.ok) throw new FlowEngineError("VALIDATION", `发布前编译不过（B11 前置）：${c.diagnostics[0]?.path}: ${c.diagnostics[0]?.message}`, { diagnostics: c.diagnostics });
    const hash = defHashOf(def); // 64 位 hex（E1）
    db.prepare("UPDATE flow_definitions SET status='published', version=version+1, published_hash=?, updated_at=? WHERE id=?").run(hash, nowIso(), id);
    return { ...metaOf(getDefRow(id)), publishedHash: hash };
  }
  function listDefs() {
    return db.prepare("SELECT * FROM flow_definitions ORDER BY updated_at DESC").all().map(metaOf);
  }
  function getDefFace({ id }) {
    const row = getDefRow(id);
    if (!row) throw new FlowEngineError("NOT_FOUND", `定义不存在 ${id}`);
    return { meta: metaOf(row), definition: JSON.parse(row.definition_json), layout: row.layout_json ? JSON.parse(row.layout_json) : null };
  }
  function putLayout({ id, layout }) {
    assertStudioOpen();
    const row = getDefRow(id);
    if (!row) throw new FlowEngineError("NOT_FOUND", `定义不存在 ${id}`);
    assertNotBuiltin(row);
    db.prepare("UPDATE flow_definitions SET layout_json=?, updated_at=? WHERE id=?").run(JSON.stringify(layout ?? null), nowIso(), id); // E4：布局与定义分离持久化
    const after = getDefRow(id);
    return { id, layoutChanged: true, definitionHash: after.definition_hash };
  }
  function importBundle({ bundle, overwrite = false }) {
    assertStudioOpen();
    if (!bundle || bundle.format !== STUDIO_BUNDLE_FORMAT || bundle.version !== STUDIO_BUNDLE_VERSION)
      throw new FlowEngineError("VALIDATION", `导入包格式必须是 ${STUDIO_BUNDLE_FORMAT} v${STUDIO_BUNDLE_VERSION}`);
    const c = bundle.definition ? compileDefinition(bundle.definition) : { ok: false };
    if (!c.ok) throw new FlowEngineError("VALIDATION", "导入包内定义编译不过");
    const defId = bundle.definition.id; // 草稿行键=定义 id（导出/导入往返 id 稳定，overwrite 契约才有意义）
    const existing = defId ? getDefRow(defId) : null;
    if (existing) {
      assertNotBuiltin(existing);
      if (!overwrite) throw new FlowEngineError("STATE", `定义已存在 ${existing.id}——overwrite=true 才覆盖`);
      db.prepare("DELETE FROM flow_definitions WHERE id=?").run(existing.id);
    }
    const now = nowIso();
    db.prepare(`INSERT INTO flow_definitions (id, kind, status, version, title, definition_json, definition_hash, layout_json, author, created_at, updated_at)
                VALUES (?, 'local', 'draft', 1, ?, ?, ?, ?, '导入', ?, ?)`)
      .run(defId || ("flow.draft." + Math.random().toString(36).slice(2, 10)), bundle.definition.title ?? "导入流程",
        JSON.stringify(bundle.definition), defHashOf(bundle.definition), bundle.layout ? JSON.stringify(bundle.layout) : null, now, now);
    return { imported: getDefRow(defId).id, overwrite: Boolean(overwrite && existing) };
  }
  function exportBundle({ id }) {
    const { definition, layout } = getDefFace({ id });
    return { format: STUDIO_BUNDLE_FORMAT, version: STUDIO_BUNDLE_VERSION, definition, layout };
  }

  // ── 桥 RPC 面 ──
  return {
    engine,
    capabilities,
    builtinCapabilityIds: builtinIds,
    // 编译（保存/发布前置的诊断面，B11）
    flowDefCompile: async ({ definition } = {}) => {
      const c = compileDefinition(definition);
      return { ok: c.ok, diagnostics: c.diagnostics };
    },
    flowDraftSave: (p) => upsertDraft(p ?? {}),
    flowDraftPublish: (p) => publishDraft(p ?? {}),
    flowDefList: async () => ({ rows: listDefs() }),
    flowDefGet: (p) => getDefFace(p ?? {}),
    flowLayoutPut: (p) => putLayout(p ?? {}),
    flowBundleImport: (p) => importBundle(p ?? {}),
    flowBundleExport: (p) => exportBundle(p ?? {}),
    flowRunStart: (p = {}) => engine.startRun({
      definitionId: p.definitionId, definition: p.definition, input: p.input ?? {},
      actor: p.actor ?? "律师", ref: p.ref ?? null, testRun: p.testRun === true,
    }),
    flowRunGet: (p = {}) => engine.getRunFace(p.id),
    flowRunList: (p = {}) => ({ rows: engine.listRuns(p) }),
    flowRunResume: (p = {}) => engine.resumeRun(p?.id, { actor: p?.actor ?? "律师" }),
    flowRunPause: (p = {}) => ({ ok: engine.pauseRun(p?.id) }),
    flowRunCancel: (p = {}) => ({ ok: engine.cancelRun(p?.id, { reason: p?.reason ?? null }) }),
    flowRecoverPending: () => engine.recoverPendingRuns(),
    flowCapRegister: ({ id, displayName, risk, idempotency, approval, inputSchema } = {}) => {
      const cap = capabilities.register({ id, displayName, risk, idempotency, approval, inputSchema });
      db.prepare(`INSERT INTO flow_capabilities (id, display_name, risk, idempotency, approval, input_schema_json, created_at)
                  VALUES (?, ?, ?, ?, ?, ?, ?)
                  ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name, risk=excluded.risk,
                    idempotency=excluded.idempotency, approval=excluded.approval, input_schema_json=excluded.input_schema_json`)
        .run(cap.id, cap.displayName ?? null, cap.risk, cap.idempotency, cap.approval, cap.inputSchema ? JSON.stringify(cap.inputSchema) : null, nowIso());
      return { id: cap.id, risk: cap.risk, idempotency: cap.idempotency, approval: cap.approval };
    },
    flowCapList: async () => ({ rows: capabilities.descriptors() }),
    flowLineParse: ({ manifestMd } = {}) => {
      const parsed = parseLineManifest(manifestMd ?? "");
      const diag = [...parsed.diagnostics];
      const shapeOk = validateLineManifest(parsed.meta, parsed.format, diag);
      let definition = null;
      if (shapeOk) {
        const assembled = lineManifestToDefinition(parsed.meta);
        diag.push(...assembled.diagnostics);
        definition = assembled.ok ? assembled.definition : null;
        if (definition) {
          const c = compileDefinition(definition);
          if (!c.ok) { definition = null; diag.push(...c.diagnostics); }
        }
      }
      return { ok: shapeOk && definition !== null, meta: parsed.meta, body: parsed.body, diagnostics: diag, definition };
    },
    flowLineDryRun: ({ manifestMd, input } = {}) => dryRunLineManifest({ engine, manifestMd: manifestMd ?? "", input }),
    // 【#34 事实核验】dry-run 全链（入口合同校验→五组流水线合成执行→面板投影；真模型接线挂后续集成单）
    flowFactVerifyDryRun: ({ input } = {}) => dryRunFactVerification({ engine, input }),
    flowAiRunList: ({ runId } = {}) => engine.aiRunFace({ runId }),
    flowDecisionSheetOf: (stageOutputs) => buildDecisionSheet(stageOutputs),
  };
}
