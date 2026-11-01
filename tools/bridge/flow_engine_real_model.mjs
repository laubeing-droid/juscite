#!/usr/bin/env node
// 【功能 #35 尾巴①】Flow 引擎真模型 agent 执行实跑（RE-35 §2 D 系 RunActor 打真模型轮，oc28 活）。
// 口径：引擎与 trust 库全在临时目录（零 %APPDATA% 写入、零监听端口、进程内直调）；agent 节点经
// runtime-port 域面（adapter 组合根）打 oc28(:43127) 公开 HTTP 真模型轮——只读/对话，绝不重启不杀
// （模型轮问题全合成，非真实案件）。activity 节点走合成执行器（材料面无模型依赖）。
// 覆盖：D1 启动上限（真轮在飞时拒新运行）/D2 恢复门拒绝（真轮产物 run 上验 attestation+catalog 两门）/
// D3 事件链 HMAC 校验/D4 checkpoint（WAITING 恢复不重跑已完成真轮节点）/D5 fail-fast（真模型拒不
// 出 JSON→OUTPUT_REJECTED）/D6 心跳（真轮耗时段可见）/D7 产物链（真轮产出 payloadDigest）/B4 有界
// 修复（诊断回喂第二轮）/G1 AI-run 一等记录（真 modelCode+promptVersion 钉定，含 map worker 路径）/
// 真轮自证（产出回对 oc28 会话转录）。
// 前置：oc28 :43127 在监听（缺=如实退 1，不自行拉起服务）；模型 env FLOW_REAL_MODEL_PROVIDER/
// FLOW_REAL_MODEL_ID 可覆盖（缺省 deepseek-byok/deepseek-chat）。
// 末行 FLOW_REALMODEL_PASS / FLOW_REALMODEL_FAIL；exit 0/1。
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const MODEL = {
  providerId: process.env.FLOW_REAL_MODEL_PROVIDER ?? "deepseek-byok",
  modelId: process.env.FLOW_REAL_MODEL_ID ?? "deepseek-chat",
};
const WORKSPACE_DIR = "D:\\mock\\lvyin-demo"; // 真模型轮会话绑定目录（conversation.probe 同款合成目录）

let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[flow-realmodel] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[flow-realmodel] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }
const assert = (n, cond, msg, detail) => (cond ? ok(n, msg) : fail(n, msg, typeof detail === "string" ? detail : JSON.stringify(detail)));
const HEX64 = /^[0-9a-f]{64}$/;

const { FLOW_ENGINE_DDL } = await import("./flow_engine_service.mjs");
const { createFlowGate } = await import("./flow_gate_service.mjs");
const {
  createFlowEngine, createCapabilityRegistry, registerBuiltinLineCapabilities,
  createRealModelAgentExecutor, createDryRunExecutors, AGENT_PROMPT_VERSION,
} = await import("../../packages/juscite-flow/src/index.mjs");
const { composeExecutors } = await import("../../packages/juscite-flow/src/fact-verification.mjs"); // 执行器合成件（service 同源）
const { createOpenCodeRuntime } = await import("../../packages/juscite-runtime-adapters/opencode/src/opencodeAdapter.mjs");

const GATE_DDL = `
    CREATE TABLE IF NOT EXISTS flow_nodes (
      id TEXT PRIMARY KEY, instance_code TEXT NOT NULL, node_code TEXT NOT NULL,
      node_type TEXT NOT NULL DEFAULT 'gate',
      status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','SUPERSEDED','SKIPPED')),
      assignee_user TEXT, lock_version INTEGER NOT NULL DEFAULT 1,
      payload_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS flow_node_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT NOT NULL,
      event_type TEXT NOT NULL CHECK (event_type IN ('created','process','transfer','force_transfer')),
      action TEXT, actor_user TEXT NOT NULL, target_user TEXT, reason TEXT,
      from_version INTEGER NOT NULL, to_version INTEGER NOT NULL, created_at TEXT NOT NULL)`;

const SCRATCH = mkdtempSync(join(tmpdir(), "juscite-flow-realmodel-"));
const db = new DatabaseSync(join(SCRATCH, "flow.db"));
db.exec("PRAGMA foreign_keys = ON");
db.exec(FLOW_ENGINE_DDL);
db.exec(GATE_DDL);
const gate = createFlowGate(db);

// runtime-port 域面（adapter 组合根）+ 会话创建计数（RM11 证第二轮真跑）+ 出站文本记录（RM9 证 D9 条款下发）
const rawRuntime = createOpenCodeRuntime();
const createdSessions = [];
const sentTexts = new Map();
const runtime = {
  createSession: async (spec) => { createdSessions.push(spec.sessionId); return rawRuntime.createSession(spec); },
  send: async (sid, msg) => { sentTexts.set(sid, msg.text); return rawRuntime.send(sid, msg); },
  pullTranscript: (sid) => rawRuntime.pullTranscript(sid),
  health: () => rawRuntime.health(),
};

let receiptSeq = 0;
const engine = createFlowEngine({
  db, gate,
  capabilities: (() => { const c = createCapabilityRegistry(); registerBuiltinLineCapabilities(c); return c; })(),
  executors: composeExecutors(
    createRealModelAgentExecutor({ runtime, model: MODEL, workspacePath: WORKSPACE_DIR, turnTimeoutMs: 240000 }),
    createDryRunExecutors(),
  ),
  citeVerify: ({ citations }) => ({
    mode: "synthetic",
    receiptId: `syn_receipt_${(++receiptSeq).toString(36)}`,
    citationCount: Array.isArray(citations) ? citations.length : 0,
  }),
  config: { maxRuns: 50, maxActiveRuns: 1, heartbeatIntervalMs: 400, heartbeatCoalesceMs: 300 }, // D1 单活动位 + D6 短心跳
  dataRoot: SCRATCH,
  trustKeyPath: join(SCRATCH, "trust", "attestation.key"),
});

const MAT_TEXT = "合成借条材料（非真实案件）：2026年3月1日，张三（出借人）向李四（借款人）出借人民币 120,000 元；"
  + "2026年4月1日，张三再向李四出借人民币 80,000 元。两笔借款均约定 2026 年 12 月 31 日前归还。";

const R1_DEF = {
  formatVersion: 2, id: "flow.realmodel.r1", version: 1, title: "真模型主链（合成材料）",
  inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] },
  nodes: [
    { id: "act.materials", type: "activity", title: "材料进来（合成）", dependsOn: [], capability: "line.intake.materials", input: { lineId: { kind: "input", path: "lineId" } } },
    {
      id: "agt.extract", type: "agent", title: "借款提取（真模型）", dependsOn: ["act.materials"],
      instruction: "从【节点输入】的合成借条材料文本中提取每笔借款，输出 loans 数组（按发生顺序），每项含 lender（出借人）、borrower（借款人）、amountCents（该笔金额换算为整数分，1 元=100 分）。",
      inputs: [{ name: "材料文本", kind: "literal", value: MAT_TEXT }],
      outputSchema: { type: "object", properties: { loans: { type: "array", items: { type: "object" } } }, required: ["loans"] },
      outputSubmissionAttempts: 2,
    },
    { id: "gate.review", type: "gate", title: "提取复核（人审关卡）", dependsOn: ["agt.extract"], gateKind: "process", request: { 事项: "合成借条提取结果复核（合成人审位）" } },
    {
      id: "agt.sum", type: "agent", title: "合计（真模型）", dependsOn: ["gate.review"],
      instruction: "对【节点输入】的 loans 数组：totalAmountCents=各项 amountCents 之和（整数分），count=笔数，borrower=借款人姓名。",
      inputs: [{ name: "loans", kind: "node-output", nodeId: "agt.extract", path: "loans" }],
      outputSchema: { type: "object", properties: { totalAmountCents: { type: "integer" }, count: { type: "integer" }, borrower: { type: "string" } }, required: ["totalAmountCents", "count"] },
      outputSubmissionAttempts: 2,
    },
  ],
  output: [{ nodeId: "agt.sum", type: "flow.realmodel.sum", citations: ["flow.realmodel.r1"] }],
};

try {
  // ── RM0 oc28 活性（不重启不杀；缺监听=如实 FAIL）──
  const health = await runtime.health();
  assert(0, health.ok, "oc28(:43127) 经 runtime-port health 探活（只读，不重启不杀）", health.detail ?? "");

  // ── RM1 主链：activity(合成)→agent(真模型轮)→gate→WAITING ──
  const t0 = Date.now();
  const r1 = await engine.startRun({ definition: R1_DEF, input: { lineId: "line.synthetic.realmodel" }, actor: "合成律师·真模型", ref: "realmodel-r1" });
  assert(1, r1.status === "WAITING" && r1.gateNodeId, `主链真模型轮后停人审关卡（首轮真实模型提取，耗时 ${((Date.now() - t0) / 1000).toFixed(1)}s）`, r1);
  if (r1.status !== "WAITING") throw new Error(`主链未达 WAITING（${r1.status}: ${r1.message ?? ""}）——后续断言无从谈起，早退`);

  // ── RM2 D3 事件链 HMAC 校验（真轮事件入链可验）──
  const faceW = engine.getRunFace(r1.runId);
  assert(2, faceW.chain.verified === true && faceW.chain.length >= 5, `D3 事件链 HMAC 校验通过（${faceW.chain.length} 事件）`, faceW.chain);

  // ── RM3 G1 AI-run 一等记录：真 modelCode 钉定 ──
  const aiW = faceW.aiRuns.filter((r) => r.nodeId === "agt.extract");
  assert(3, aiW.length === 1 && aiW[0].modelCode === `${MODEL.providerId}/${MODEL.modelId}` && aiW[0].modelCode !== "synthetic-model"
    && aiW[0].promptVersion === AGENT_PROMPT_VERSION,
    "G1 agent 节点 AI-run 落行：真 modelCode+promptVersion 钉定", aiW.map((r) => [r.nodeId, r.modelCode, r.promptVersion]));

  // ── RM4 D6 心跳：真轮耗时窗内心跳事件可见 ──
  const beats = faceW.events.filter((e) => e.kind === "heartbeat");
  assert(4, beats.length >= 2, `D6 心跳事件 ${beats.length} 条（400ms 档，真轮节点间可见）`, beats.length);

  // ── RM5 D1 启动上限：WAITING 占用唯一活动位时拒新运行 ──
  let d1err = null;
  try { await engine.startRun({ definition: R1_DEF, input: { lineId: "line.synthetic.realmodel.2" } }); } catch (e) { d1err = e; }
  assert(5, d1err?.message?.includes("活动流程运行数量已达上限"), "D1 活动运行占满即拒新运行（真轮 run 在飞）", String(d1err?.message ?? d1err));

  // ── RM6 过闸恢复：agent2 真模型轮消费 agent1 产出（node-output 数据流）──
  const gv = gate.getNode(r1.gateNodeId);
  gate.process(r1.gateNodeId, { actor: "合成复核位", action: "approve", comment: "合成材料人审模拟（非真实决定）", expectedVersion: gv.node.lockVersion });
  const r1r = await engine.resumeRun(r1.runId, { actor: "合成复核位" });
  const face1 = engine.getRunFace(r1.runId);
  const extractOut = JSON.parse(db.prepare("SELECT context_json FROM flow_runs WHERE id = ?").get(r1.runId).context_json)["agt.extract"]?.output;
  const loans = extractOut?.loans ?? [];
  const sumRow = face1.run.status === "SUCCEEDED" ? face1 : null;
  const sumAi = face1.aiRuns.filter((r) => r.nodeId === "agt.sum");
  const sumOut = JSON.parse(db.prepare("SELECT context_json FROM flow_runs WHERE id = ?").get(r1.runId).context_json)["agt.sum"]?.output;
  const loansSum = loans.reduce((a, l) => a + (Number(l.amountCents) || 0), 0);
  assert(6, r1r.status === "SUCCEEDED" && sumAi.length === 1 && sumAi[0].modelCode === `${MODEL.providerId}/${MODEL.modelId}`
    && sumOut?.totalAmountCents === loansSum && sumOut?.count === loans.length,
    "过闸恢复后第二轮真模型完成，且产出与上游真轮产出数据闭合（totalAmountCents=loans 之和）",
    { status: r1r.status, loans: loans.map((l) => l.amountCents), total: sumOut?.totalAmountCents, count: sumOut?.count, expect: loansSum });

  // ── RM7 D4 checkpoint：恢复不重跑已完成真轮节点 ──
  const started1 = face1.events.filter((e) => e.kind === "node.started" && e.nodeId === "agt.extract");
  const resumed = face1.events.filter((e) => e.kind === "run.resumed");
  assert(7, started1.length === 1 && resumed.length === 1 && face1.aiRuns.filter((r) => r.nodeId === "agt.extract").length === 1,
    "D4 checkpoint：WAITING 恢复后已完成真轮节点不重跑（node.started=1、AI-run=1）",
    { started: started1.length, aiRows: face1.aiRuns.filter((r) => r.nodeId === "agt.extract").length });

  // ── RM8 D7 产物链：真轮产物 payloadDigest+引用回执 ──
  assert(8, face1.artifacts.length === 1 && HEX64.test(face1.artifacts[0].payloadDigest) && Boolean(face1.artifacts[0].citeReceipt?.receiptId),
    "D7 产物链：真轮产物带 payloadDigest(64hex)+citeReceipt", face1.artifacts.map((a) => [a.type, a.payloadDigest?.slice(0, 12)]));

  // ── RM9 真轮自证：产出回对 oc28 会话转录；D9 防护条款随出站提示词下发（发送面记录——
  //    oc28 listMessages 不回显 user 文本，转录面无从断言，如实改走发送侧记录）──
  const extractSids = createdSessions.filter((s) => s.includes("agt.extract"));
  let transcriptHit = false;
  const sentPrompt = extractSids.length ? (sentTexts.get(extractSids[0]) ?? "") : "";
  const guardSent = sentPrompt.includes("数据与指令边界") && sentPrompt.includes("合成借条材料");
  if (extractSids.length) {
    const entries = await runtime.pullTranscript(extractSids[0]);
    transcriptHit = entries.some((e) => e.role === "assistant" && /loans/.test(e.text ?? ""));
  }
  assert(9, transcriptHit && guardSent, "真轮自证：assistant 回复含产出 JSON（loans）且出站提示词携带 D9 注入防护条款", { sid: extractSids[0] ?? null, guardSent, promptChars: sentPrompt.length });

  // ── RM10 map 真模型轮：逐项并发+G1 map 路径 AI-run 落行 ──
  const MAP_DEF = {
    formatVersion: 2, id: "flow.realmodel.map", version: 1, title: "真模型 map 逐项（合成材料）",
    inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] },
    nodes: [{
      id: "map.convert", type: "map", title: "逐笔换算（真模型）", dependsOn: [],
      items: { kind: "literal", value: [
        { doc: "材料一（合成）", amountYuan: 120000 },
        { doc: "材料二（合成）", amountYuan: 80000 },
      ] },
      maxConcurrency: 2,
      worker: {
        type: "agent",
        instruction: "把输入 item 的 amountYuan（元）换算为整数分，输出 {amountCents, doc}（doc 原样回填）。",
        inputs: [{ name: "item", kind: "item" }],
        outputSchema: { type: "object", properties: { amountCents: { type: "integer" }, doc: { type: "string" } }, required: ["amountCents", "doc"] },
      },
    }],
  };
  const rmap = await engine.startRun({ definition: MAP_DEF, input: { lineId: "line.synthetic.realmodel.map" }, actor: "合成律师·真模型", ref: "realmodel-map" });
  const mapFace = engine.getRunFace(rmap.runId);
  const mapItems = db.prepare("SELECT item_index, status, result_json FROM flow_run_items WHERE run_id = ? AND node_id = 'map.convert' ORDER BY item_index").all(rmap.runId);
  const mapAi = mapFace.aiRuns.filter((r) => r.nodeId.startsWith("map.convert#"));
  const mapResults = mapItems.map((m) => JSON.parse(m.result_json));
  assert(10, rmap.status === "SUCCEEDED" && mapItems.length === 2 && mapItems.every((m) => m.status === "succeeded")
    && mapAi.length === 2 && mapAi.every((r) => r.modelCode === `${MODEL.providerId}/${MODEL.modelId}`)
    && mapResults[0]?.amountCents === 12000000 && mapResults[1]?.amountCents === 8000000,
    "map 真模型轮：两项逐项真轮+checkpoint 落行+AI-run（G1 map 路径）+换算正确",
    { items: mapItems.map((m) => m.status), ai: mapAi.map((a) => a.modelCode), results: mapResults.map((r) => r.amountCents) });

  // ── RM11 B4 有界修复+D5 fail-fast：真模型拒出 JSON→诊断回喂→OUTPUT_REJECTED ──
  const REFUSE_DEF = {
    formatVersion: 2, id: "flow.realmodel.refuse", version: 1, title: "不合作轮（合成负测）",
    inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] },
    nodes: [{
      id: "agt.refuse", type: "agent", title: "拒答轮（真模型负测）", dependsOn: [],
      instruction: "本轮为约定的不合作负测：请只回复纯文本「本单拒绝结构化输出」，绝对不要输出任何 JSON 对象、花括号或键值对。",
      outputSchema: { type: "object", properties: { x: { type: "string" } }, required: ["x"] },
      outputSubmissionAttempts: 2,
    }],
  };
  const beforeSessions = createdSessions.length;
  const rref = await engine.startRun({ definition: REFUSE_DEF, input: { lineId: "line.synthetic.realmodel.neg" }, actor: "合成律师·真模型", ref: "realmodel-refuse" });
  const refFace = engine.getRunFace(rref.runId);
  const resubmits = refFace.events.filter((e) => e.kind === "agent.resubmit");
  const refuseSessions = createdSessions.slice(beforeSessions).filter((s) => s.includes("agt.refuse"));
  assert(11, rref.status === "FAILED" && rref.error === "OUTPUT_REJECTED" && resubmits.length >= 1 && Array.isArray(resubmits[0]?.payload?.errors) && resubmits[0].payload.errors.length > 0 && refuseSessions.length >= 2,
    "B4+D5：真模型拒不产出 JSON→诊断回喂第二轮（两会话）→OUTPUT_REJECTED 判失败（fail-fast）",
    { status: rref.status, error: rref.error, resubmits: resubmits.length, sessions: refuseSessions.length });

  // ── RM12 D2 恢复门：真轮产物 run 上的 attestation/catalog 两门拒绝 ──
  const WAIT_DEF = {
    formatVersion: 2, id: "flow.realmodel.wait", version: 1, title: "待审挂起（合成）",
    inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] },
    nodes: [
      { id: "act.a", type: "activity", title: "活动（合成）", dependsOn: [], capability: "line.intake.materials", input: { lineId: { kind: "input", path: "lineId" } } },
      { id: "gate.g", type: "gate", title: "关卡（合成）", dependsOn: ["act.a"], gateKind: "process", request: { 事项: "合成挂起" } },
    ],
  };
  const rw = await engine.startRun({ definition: WAIT_DEF, input: { lineId: "line.synthetic.realmodel.wait" }, actor: "合成律师", ref: "realmodel-wait" });
  const evtRow = db.prepare("SELECT id, seq, message_json, prev_hash, hash FROM flow_run_events WHERE run_id = ? ORDER BY id ASC LIMIT 1").get(rw.runId);
  db.prepare("UPDATE flow_run_events SET message_json = ? WHERE id = ?").run('{"tampered":true}', evtRow.id); // 篡改首事件（破坏 HMAC 链）
  let rec1 = null;
  try { rec1 = await engine.recoverPendingRuns(); } catch (e) { rec1 = { error: String(e?.message ?? e) }; }
  const refused1 = (rec1?.refused ?? []).find((r) => r.runId === rw.runId);
  assert(12, refused1?.gate === "attestation", "D2 门② attestation：事件链被篡改的 run 拒自动恢复（真轮同库同门）", rec1?.refused ?? rec1);

  db.prepare("UPDATE flow_run_events SET message_json = ? WHERE id = ?").run(evtRow.message_json, evtRow.id); // 还原链
  const rec2 = await engine.recoverPendingRuns();
  const refused2 = (rec2?.refused ?? []).find((r) => r.runId === rw.runId);
  assert(13, refused2?.gate === "catalog", "D2 门③ catalog：内联定义 run 的静态目录比对失败拒自动恢复", rec2?.refused ?? rec2);

  // ── 收尾：oc28 全程未动（health 仍活）──
  const healthAfter = await runtime.health();
  assert(14, healthAfter.ok, "oc28 全程只读对话未动（收尾探活仍活）", healthAfter.detail ?? "");
} catch (e) {
  fail("UNCAUGHT", String(e?.stack ?? e));
} finally {
  try { db.close(); } catch { /* 已关 */ }
  try { rmSync(SCRATCH, { recursive: true, force: true }); } catch { /* Windows 句柄延迟，残留临时目录无害 */ }
}
if (failed > 0) { console.error("FLOW_REALMODEL_FAIL"); process.exit(1); }
console.log("FLOW_REALMODEL_PASS");
