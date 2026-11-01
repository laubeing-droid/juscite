#!/usr/bin/env node
// 【功能 #33 成套文件勾稽·全量面】合成对拍（RE-33-成套文件勾稽.md §4 对拍清单 1-19+OpenSign 增补节 20-25 逐项验收；
// ci_gate fast mech 随行步）。全合成材料：库=临时目录 node:sqlite（FLOW_ENGINE_DDL 单源导入），零 %APPDATA% 触碰，
// 零端口（进程内直调服务面，:3030/:43127 不接触），零真模型零 oc28（agent 执行=成套勾稽合成执行器）。
// 对齐物=Andoo workflow-v2 document-cross-verification（RE-33 规格 r11 终修稿+2026-10-31 OpenSign 增补节）；
// 本 harness 只验我方行为面，竞品行为面以规格 §2/§4 行号为据（符号名主锚）。编号 1-25 与 §4 对拍行一一对应。
// 纯 Node 零依赖；单命令 exit 0/1，末行 CROSSVERIF_SYNTH_PASS 可判。
// 用法：node tools/bridge/cross_verification_synthetic.mjs
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import { createHash } from "node:crypto";
const createHashSync = (v) => createHash("sha256").update(JSON.stringify(v)).digest("hex");

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url)); // tools/bridge/ → 仓库根（m1-u01）
let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[crossverif-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[crossverif-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }
const assert = (n, cond, msg, detail) => (cond ? ok(n, msg) : fail(n, msg, typeof detail === "string" ? detail : JSON.stringify(detail)));
const tryCode = (fn) => { try { const r = fn(); return r instanceof Promise ? r.then(() => null, (e) => e) : null; } catch (e) { return e; } };
const HEX64 = /^[0-9a-f]{64}$/;

const { FLOW_ENGINE_DDL, createFlowEngineService } = await import("./flow_engine_service.mjs");
const { createFlowGate } = await import("./flow_gate_service.mjs");
const cv = await import("../../packages/juscite-flow/src/cross-verification.mjs");
const { createFlowEngine, estimateRunDurationMs, AGENT_PROMPT_VERSION, createCapabilityRegistry, registerBuiltinLineCapabilities } =
  await import("../../packages/juscite-flow/src/index.mjs");

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

const SCRATCH = mkdtempSync(join(tmpdir(), "juscite-crossverif-synth-"));
function freshDb(file) {
  const db = new DatabaseSync(file);
  db.exec("PRAGMA foreign_keys = ON");
  db.exec(FLOW_ENGINE_DDL);
  db.exec(GATE_DDL);
  return db;
}
function freshService() {
  const dir = mkdtempSync(join(tmpdir(), "juscite-crossverif-svc-"));
  const db = freshDb(join(dir, "flow.db"));
  const gate = createFlowGate(db);
  const svc = createFlowEngineService({ db, gate, trustDir: dir });
  return { db, gate, svc, dir };
}
// 直连引擎（tamper/重提场景用；执行器可注入）
function directEngine({ db, gate, dir, executors }) {
  const capabilities = createCapabilityRegistry();
  registerBuiltinLineCapabilities(capabilities);
  cv.registerCrossVerificationCapabilities(capabilities);
  return createFlowEngine({
    db, gate, capabilities, executors,
    citeVerify: ({ citations }) => ({ mode: "synthetic", receiptId: "syn_" + citations.length, citationCount: citations.length }),
    dataRoot: dir, trustKeyPath: join(dir, "trust", "attestation.key"),
  });
}
const outputsOf = (db, runId) => JSON.parse(db.prepare("SELECT context_json FROM flow_runs WHERE id = ?").get(runId).context_json);

const GOOD_INPUT = { documents: cv.SYNTH_DOCUMENTS.map((d) => ({ path: d.path, name: d.name })) }; // 主链件带 name（path 必填 name 可选合同的两形态之一；对拍 1 另测无 name 形态）

async function main() {
  const def = cv.buildCrossVerificationDefinition();
  const nodesById = new Map(def.nodes.map((n) => [n.id, n]));
  const capRisk = new Map(cv.CROSS_VERIFICATION_CAPABILITIES.map((c) => [c.id, c]));
  const { svc, db } = freshService();
  const dry = await svc.flowCrossVerifyDryRun({ input: GOOD_INPUT });
  const face = dry.ok ? svc.flowRunGet({ id: dry.runId }) : null;
  const outputs = dry.ok ? outputsOf(db, dry.runId) : {};

  // ── 对拍 1：成套文件 2-20 份进场建快照，snapshotId 贯穿引用（行为 1）──
  const bridgeHost = readFileSync(join(REPO_ROOT, "tools", "bridge", "bridge_host.mjs"), "utf8");
  const oneDoc = tryCode(() => cv.validateCrossVerificationInput({ documents: [{ path: "a.pdf" }] }));
  const twentyOne = tryCode(() => cv.validateCrossVerificationInput({ documents: Array.from({ length: 21 }, (_, i) => ({ path: `f${i}.pdf` })) }));
  const badPath = tryCode(() => cv.validateCrossVerificationInput({ documents: [{ path: "" }, { path: "b.pdf" }] }));
  const longPath = tryCode(() => cv.validateCrossVerificationInput({ documents: [{ path: "x".repeat(4097) }, { path: "b.pdf" }] }));
  const longName = tryCode(() => cv.validateCrossVerificationInput({ documents: [{ path: "a.pdf", name: "n".repeat(201) }, { path: "b.pdf" }] }));
  const extraKey = tryCode(() => cv.validateCrossVerificationInput({ documents: [{ path: "a.pdf" }, { path: "b.pdf" }], scope: "x" }));
  const twoOk = cv.validateCrossVerificationInput({ documents: [{ path: "a.pdf" }, { path: "b.pdf" }] });
  const snap = outputs.prepare_documents?.output ?? {};
  const snapOk = dry.ok && snap.snapshotId?.startsWith("snap.") && snap.documents?.length === 4
    && snap.documents.every((d) => d.documentId && d.anchors?.length >= 2);
  const aggregateOut = outputs.aggregate_result?.output ?? {};
  const citationsAll = (aggregateOut.comparisons ?? []).flatMap((c) => c.documentResults ?? []).flatMap((r) => r.citations ?? []);
  assert(1, typeof svc.flowCrossVerifyDryRun === "function" && bridgeHost.includes("flowCrossVerifyDryRun") && snapOk
    && aggregateOut.snapshotId === snap.snapshotId && citationsAll.every((c) => c.snapshotId === snap.snapshotId)
    && oneDoc && twentyOne && badPath && longPath && longName && extraKey && twoOk.ok,
    "进场合同同形：2-20 份/path 1-4096/name≤200/附加属性拒；快照冻结（4 份 documentId+锚集）且 snapshotId 贯穿聚合与全部引用；入口=服务面 flowCrossVerifyDryRun+bridge_host 转发行（工作树接线与 #35/#43 同批待共享索引收口）",
    [dry.ok, snap.snapshotId, aggregateOut.snapshotId, oneDoc?.message, twentyOne?.message, extraKey?.message]);

  // ── 对拍 2：逐文档识别模块+主张，并发 2，主体名单排除（行为 2）──
  const az = nodesById.get("analyze_documents");
  const analysesOut = outputs.analyze_documents?.output ?? [];
  const firstAnalysis = Array.isArray(analysesOut) ? analysesOut[0] : analysesOut?.modules ? analysesOut : null;
  const excludedSubjects = Array.isArray(analysesOut) ? (analysesOut.flatMap((a) => a?.excludedSubjects ?? []) ?? []) : [];
  assert(2, az.type === "map" && az.maxConcurrency === 2 && az.worker.type === "agent"
    && az.worker.instruction.includes("机会/风险/事实/判断/金额/期限/条件/结论") && az.worker.instruction.includes("不算模块或主张")
    && Array.isArray(analysesOut) && analysesOut.length === 4
    && firstAnalysis.modules.every((m) => m.localModuleId && m.name && Array.isArray(m.claims))
    && excludedSubjects.length >= 3 && String(analysesOut.flatMap((a) => a?.excludedBackground ?? []).join("")).includes("注入性文字"),
    "逐文档 map 并发 2+八类别归类+主体名单/封面目录排除（公司名单进 excludedSubjects；注入段进 excludedBackground 不产主张）",
    [az.maxConcurrency, Array.isArray(analysesOut) ? analysesOut.length : "not-array", excludedSubjects.length]);

  // ── 对拍 3：结构覆盖门 valid/diagnostics+引用回绑+stats（行为 3）──
  const shapeErr = tryCode(() => cv.validateCoverageStructure({ analyses: {}, documents: [], snapshotId: 1 }));
  const orphan = cv.validateCoverageStructure({ analyses: [{ documentId: "doc.nope", modules: [] }], documents: [{ documentId: "doc.a" }], snapshotId: "snap.x" });
  const missing = cv.validateCoverageStructure({ analyses: [{ documentId: "doc.a", modules: "x" }], documents: [{ documentId: "doc.a" }], snapshotId: "snap.x" });
  const unanalyzed = cv.validateCoverageStructure({ analyses: [{ documentId: "doc.a", modules: [] }], documents: [{ documentId: "doc.a" }, { documentId: "doc.b" }], snapshotId: "snap.x" });
  const overflow = cv.validateCoverageStructure({ analyses: [{ documentId: "doc.a", modules: [] }, { documentId: "doc.a", modules: [] }], documents: [{ documentId: "doc.a" }], snapshotId: "snap.x" });
  const covOut = outputs.validate_coverage?.output ?? {};
  const rebound = (covOut.analyses ?? []).flatMap((a) => a.modules ?? []).flatMap((m) => m.claims ?? []).flatMap((c) => c.citations ?? []);
  assert(3, shapeErr?.message?.includes("coverage input 格式无效")
    && orphan.diagnostics.some((d) => d.kind === "orphan_analysis") && missing.diagnostics.some((d) => d.kind === "missing_modules")
    && unanalyzed.diagnostics.some((d) => d.kind === "document_unanalyzed") && overflow.diagnostics.some((d) => d.kind === "analysis_overflow")
    && covOut.valid === true && covOut.diagnostics.length === 0
    && covOut.stats.documentCount === 4 && covOut.stats.analysisCount === 4 && covOut.stats.moduleCount === 4 && covOut.stats.claimCount === 12
    && rebound.every((c) => c.snapshotId && c.documentId && "anchor" in c),
    "覆盖门四类逐位对齐诊断（orphan/missing_modules/unanalyzed/overflow）+形状校验抛错+valid=诊断空+stats 四计+引用回绑三元组",
    [JSON.stringify(orphan.diagnostics), JSON.stringify(covOut.stats)]);

  // ── RE-12 对照源增补节 T40-T42 #33 接线回执：分析层主张逐字引文回验（覆盖校验节点输出携 quoteBack）──
  const qb33 = covOut.quoteBack;
  assert("3b", Boolean(qb33) && qb33.total === 11 && qb33.counts.pass === 1 && qb33.counts.mismatch === 10
    && qb33.counts.fabricated === 0 && qb33.counts.uncited === 1
    && qb33.uncited?.[0]?.localClaimId === "sha.clm.003"
    && qb33.results?.find((r) => r.verdict === "pass")?.localClaimId === "sha.clm.001",
    "tabular-review 接线：带引用主张 11 入分母（逐字复现 1 pass=sha.clm.001；转述型主张句 10 mismatch=机制立场：改写即不可逐字核）+零引用否定性主张 sha.clm.003 显式 uncited 单列",
    JSON.stringify(qb33?.counts));
  const qb33neg = cv.verifyCrossQuoteBack([
    { modules: [{ claims: [{ localClaimId: "n1", text: "正面主张却零引文", citations: [] }] }] },
    { modules: [{ claims: [{ localClaimId: "n2", text: "改写过的主张句", citations: [{ quote: "原文是完全另一句" }] }] }] },
  ]);
  assert("3c", qb33neg.counts.uncited === 1 && qb33neg.counts.mismatch === 1 && qb33neg.results?.[0]?.verdict === "mismatch",
    "回验适配器负例：零引文正面主张→uncited 显式单列（不静默不冒通过）；引文不含主张文本→mismatch",
    JSON.stringify(qb33neg.counts));

  // ── 对拍 4：覆盖不过→一次有界修复（行为 15）──
  const gapDb = freshDb(join(SCRATCH, "gap.db"));
  const gapEngine = directEngine({ db: gapDb, gate: createFlowGate(gapDb), dir: SCRATCH, executors: cv.createCrossVerificationExecutors({ coverageGapOnce: true }) });
  const gapRun = await gapEngine.startRun({ definition: def, input: GOOD_INPUT, dryRun: true });
  const gapOutputs = outputsOf(gapDb, gapRun.runId);
  const gapCov = gapOutputs.validate_coverage?.output ?? {};
  const gapUnify = gapOutputs.unify_business_tree?.output ?? {};
  const gapAgg = gapOutputs.aggregate_result?.output ?? {};
  assert(4, gapRun.status === "SUCCEEDED" && gapCov.valid === false && gapCov.diagnostics.some((d) => d.kind === "document_unanalyzed")
    && gapUnify.boundedRepair?.applied === true && gapUnify.boundedRepair?.once === true && Array.isArray(gapUnify.repairedAnalyses)
    && gapUnify.repairedAnalyses.length === 4 && gapAgg.summary?.total === 8,
    "覆盖门诊断在场→unify 按诊断做一次有界修复（boundedRepair.applied/once，补齐 4 份分析）→主链照常走通（8 主张不缺）",
    [gapRun.status, gapCov.valid, JSON.stringify(gapUnify.boundedRepair), gapAgg.summary?.total]);

  // ── 对拍 5：统一两层业务树+ID 映射+无证据不新增（行为 4）──
  const unify = nodesById.get("unify_business_tree");
  const unifyOut = outputs.unify_business_tree?.output ?? {};
  const noEvidence = cv.validateUnifiedTree({ modules: [{ moduleId: "m.x", name: "x", members: [], claims: [{ claimId: "c.ghost", businessClaim: "无中生有", derivedFromLocal: ["ghost.local"] }] }] }, []);
  const treeOk = cv.validateUnifiedTree(unifyOut, covOut.analyses);
  const mapOk = Object.entries(unifyOut.idMapping ?? {}).filter(([k, v]) => k.startsWith("ts.") && String(v).startsWith("uclm."));
  assert(5, unify.type === "agent" && unify.retry && unify.retry.maxAttempts === 3 && unify.retry.backoffMs === 1000
    && unifyOut.modules?.length === 4 && unifyOut.modules.every((m) => "moduleId" in m && "name" in m && "members" in m && "claims" in m)
    && treeOk.length === 0 && noEvidence.length > 0 && mapOk.length >= 3
    && unify.outputSchema.properties.modules.items.required.includes("moduleId"),
    "统一两层树（模块→主张）+local→统一 ID 映射（ts.*→uclm.*）+无原文证据新增拒（derivedFromLocal 不可溯诊断）+retry 3 次×1s 声明",
    [unifyOut.modules?.length, treeOk, noEvidence.length]);

  // ── 对拍 6：有界批次 ≤100 批/≤256 次执行+budget 边界（行为 5,18）──
  const batchOut = outputs.build_comparison_batches?.output ?? {};
  const overBatches = tryCode(() => cv.buildComparisonBatchPlan(Array.from({ length: 900 }, (_, i) => ({ moduleId: "m" + i, claims: [{ claimId: "c" + i }] })), { maxBatches: 100, maxAgentExecutions: 900 })); // 900 主张→113 批>100
  const overExecs = tryCode(() => cv.buildComparisonBatchPlan([{ moduleId: "m", claims: Array.from({ length: 9 }, (_, i) => ({ claimId: "c" + i })) }], { maxBatches: 100, maxAgentExecutions: 8 }));
  const budgetEq = def.budget.maxDocuments === 20 && def.budget.maxMapItems === 100 && def.budget.maxAgentExecutions === 256 && def.budget.maxInputBytesPerNode === 4194304
    && def.budget.runDurationPolicy.kind === "input-files" && def.budget.runDurationPolicy.baseMs === 1200000 && def.budget.runDurationPolicy.perItemMs === 300000
    && def.budget.runDurationPolicy.perMiBMs === 120000 && def.budget.runDurationPolicy.minMs === 1800000 && def.budget.runDurationPolicy.maxMs === 10800000;
  const est4 = estimateRunDurationMs(def.budget.runDurationPolicy, [{ sizeMiB: 2 }, { sizeMiB: 2 }, { sizeMiB: 2 }, { sizeMiB: 2 }]);
  const estCeil = estimateRunDurationMs(def.budget.runDurationPolicy, Array.from({ length: 40 }, () => ({ sizeMiB: 100 })));
  const bigInput = { documents: Array.from({ length: 21 }, (_, i) => ({ path: `f${i}.pdf` })) };
  const bDb = freshDb(join(SCRATCH, "b.db"));
  const budgetDocs = await tryCode(() => directEngine({ db: bDb, gate: createFlowGate(bDb), dir: SCRATCH, executors: cv.createCrossVerificationExecutors() }).startRun({ definition: def, input: bigInput, dryRun: true }));
  assert(6, batchOut.stats?.batchCount === 1 && batchOut.stats?.plannedAgentExecutions === 8 && batchOut.batches?.length === 1
    && overBatches?.code === "BUDGET_BATCHES" && overExecs?.code === "BUDGET_EXECUTIONS" && budgetEq
    && est4 === 3360000 && estCeil === 10800000 && budgetDocs?.code === "BUDGET_DOCS",
    "批次硬上限（100 批/256 执行；超限抛错）+budget 域值六面照录（20/100/256/4MiB/policy 五参）+时长估算实算（4×2MiB=1.2M+1.2M+0.96M=3.36M；40×100MiB 夹顶 10.8M）+21 份实测 BUDGET_DOCS 拒",
    [JSON.stringify(batchOut.stats), est4, estCeil, budgetDocs?.code]);

  // ── 对拍 7：分批比对并发 4：conclusion+逐文档 presence/summary/citations 仅直接支撑（行为 6,20）──
  const cb = nodesById.get("compare_businesses");
  const cmpOut = outputs.compare_businesses?.output ?? [];
  const cmpItems = (Array.isArray(cmpOut) ? cmpOut : []).flatMap((o) => o?.comparisons ?? []);
  const itemOk = cv.validateComparisonItems(cmpItems, snap.documents) ;
  const presentCited = cmpItems.flatMap((it) => it.documentResults ?? []).filter((r) => r.presence === "present");
  assert(7, cb.type === "map" && cb.maxConcurrency === 4 && cb.worker.type === "agent"
    && cb.worker.instruction.includes("present（明文提及）") && cb.worker.instruction.includes("快照冻结锚，非活文档位置")
    && cmpItems.length === 8 && itemOk.length === 0 && presentCited.length >= 2
    && presentCited.every((r) => r.citations.length >= 1 && r.citations.every((c) => /^[A-Za-z0-9_-]{1,128}$/.test(c.anchor))),
    "分批比对 map 并发 4+presence 三枚举+引用只收直接支撑（present 必带快照冻结锚 [A-Za-z0-9_-]{1,128}）+语义校验零诊断",
    [cb.maxConcurrency, cmpItems.length, itemOk]);

  // ── 对拍 8：单文档 present→unmentioned 特判；未提及 citations 空（行为 12,13）──
  const uclm005 = (aggregateOut.comparisons ?? []).find((c) => c.claimId === "uclm.005");
  const notMentioned = (aggregateOut.comparisons ?? []).flatMap((c) => c.documentResults ?? []).filter((r) => r.presence !== "present");
  const missingDocCorrected = cv.aggregateComparisons({
    comparisons: [{ claimId: "t.1", businessClaim: "试件", status: "consistent", conclusion: "", documentResults: [{ documentId: "doc.a", presence: "present", summary: "s", citations: [{ snapshotId: "snap", documentId: "doc.a", anchor: "a1" }] }] }],
    modules: [], documents: [{ documentId: "doc.a" }, { documentId: "doc.b" }], snapshotId: "snap",
  });
  assert(8, uclm005?.status === "unmentioned" && uclm005.documentResults.filter((r) => r.presence === "present").length === 1
    && uclm005.documentResults.filter((r) => r.presence !== "present").every((r) => r.citations.length === 0 && r.summary.includes("未提及"))
    && notMentioned.every((r) => r.citations.length === 0)
    && missingDocCorrected.comparisons[0].documentResults.length === 2
    && missingDocCorrected.comparisons[0].documentResults[1].presence === "not_mentioned" && missingDocCorrected.comparisons[0].documentResults[1].citations.length === 0,
    "恰一份 present→固定 unmentioned（不再判一致/差异）；未提及文档 summary 明示+citations 强制空；漏报文档聚合层补 not_mentioned",
    [uclm005?.status, notMentioned.length]);

  // ── 对拍 9：聚合层 presence 确定性校正+一致/差异/证据不足三态（行为 7）──
  const uclm003 = (aggregateOut.comparisons ?? []).find((c) => c.claimId === "uclm.003");
  const uclm002 = (aggregateOut.comparisons ?? []).find((c) => c.claimId === "uclm.002");
  assert(9, aggregateOut.summary && aggregateOut.summary.consistent === 2 && aggregateOut.summary.difference === 2
    && aggregateOut.summary.insufficient === 1 && aggregateOut.summary.unmentioned === 3 && aggregateOut.summary.total === 8
    && uclm003?.status === "difference" && uclm003.documentResults.filter((r) => r.presence === "present").map((r) => r.summary).join("｜").includes("12 月 15 日")
    && uclm003.documentResults.filter((r) => r.presence === "present").map((r) => r.summary).join("｜").includes("11 月 30 日")
    && uclm002?.status === "insufficient",
    "聚合三态四枚举齐（一致 2/差异 2/证据不足 1/未提及 3=8）；交割日差异双侧（12-15 对 11-30）；证据不足=present≥2 但证据面不足保留",
    [JSON.stringify(aggregateOut.summary), uclm003?.status, uclm002?.status]);

  // ── 对拍 10：双道引用校验：节点校验出 receipt+发布时复核四字段全等（行为 8）──
  const receipt = outputs.verify_citations?.output ?? {};
  const pubOut = outputs.publish_result?.output ?? {};
  const recomputed = cv.verifyCrossCitations({ runId: receipt.runId, payload: aggregateOut, snapshot: { snapshotId: snap.snapshotId, documents: snap.documents } });
  const mismatchCount = tryCode(() => cv.reverifyCiteReceipt({ payload: aggregateOut, citeReceipt: { ...receipt, citationCount: receipt.citationCount + 1 }, snapshot: { snapshotId: snap.snapshotId, documents: snap.documents } }));
  const mismatchDigest = tryCode(() => cv.reverifyCiteReceipt({ payload: aggregateOut, citeReceipt: { ...receipt, payloadDigest: "0".repeat(64) }, snapshot: { snapshotId: snap.snapshotId, documents: snap.documents } }));
  const badAnchor = cv.validCitation({ snapshotId: "s", documentId: "d", anchor: "非法 锚!" });
  assert(10, receipt.ok === true && HEX64.test(receipt.receiptId ?? "") && receipt.runId === dry.runId && receipt.citationCount === citationsAll.length
    && recomputed.receiptId === receipt.receiptId && pubOut.citeReceipt?.receiptId === receipt.receiptId
    && mismatchCount?.code === "CITE_RECEIPT_MISMATCH" && mismatchDigest?.code === "CITE_RECEIPT_MISMATCH" && badAnchor === false,
    "第一道节点校验出四字段回执（receiptId=sha256(runId+payloadDigest+引用规范化串) hex64）+第二道发布时重算四字段全等复核（篡改 citationCount/payloadDigest 均抛）+引用合法判据（anchor 字符集）",
    [receipt.citationCount, receipt.runId === dry.runId, mismatchCount?.code, badAnchor]);

  // ── 对拍 11：产物 11 字段完整性锚+32MB 上限+幂等重发布（行为 9）──
  const envelopeKeys = ["artifactId", "runId", "nodeId", "projectId", "sessionId", "type", "version", "renderer", "payloadDigest", "byteLength", "createdAt"];
  const envelopeOk = envelopeKeys.every((k) => k in pubOut) && pubOut.type === "document-cross-verification" && pubOut.version === 2
    && /^[0-9a-f]{32}$/.test(pubOut.artifactId) && pubOut.byteLength === Buffer.byteLength(JSON.stringify(aggregateOut), "utf8");
  const expectedId = createHash("sha256").update(`${dry.runId}+publish_result+document-cross-verification+2`).digest("hex").slice(0, 32);
  const bigPayload = { pad: "x".repeat(33554432 + 1024) };
  const tooLarge = tryCode(() => cv.buildCrossArtifactEnvelope({ runId: "r.big", nodeId: "n", payload: bigPayload, citeReceipt: { ok: true } }));
  const store = cv.createCrossArtifactStore(join(SCRATCH, "store"));
  const receiptFor = (runId, payload) => ({ runId, payloadDigest: createHashSync(payload), citationCount: 0, receiptId: "r".repeat(64), ok: true });
  const envA = cv.buildCrossArtifactEnvelope({ runId: "run.dup", nodeId: "publish_result", payload: { v: 1 }, citeReceipt: receiptFor("run.dup", { v: 1 }) });
  const replay = store.persist(envA);
  const replay2 = store.persist(envA);
  const envB = cv.buildCrossArtifactEnvelope({ runId: "run.dup", nodeId: "publish_result", payload: { v: 2 }, citeReceipt: receiptFor("run.dup", { v: 2 }) });
  const conflict = tryCode(() => store.persist(envB));
  const receiptMismatch = tryCode(() => store.persist(cv.buildCrossArtifactEnvelope({ runId: "run.x", nodeId: "n", payload: { v: 1 }, citeReceipt: { runId: "run.OTHER", payloadDigest: "z", ok: true } })));
  const persistedFiles = existsSync(join(SCRATCH, "store", envA.artifactId, "payload.json")) && existsSync(join(SCRATCH, "store", envA.artifactId, "manifest.json"));
  const defOutputSchemaOk = def.outputSchema.required.length === 11 && def.outputSchema.additionalProperties === false;
  assert(11, envelopeOk && pubOut.artifactId === expectedId && tooLarge?.code === "PAYLOAD_TOO_LARGE"
    && replay.idempotentReplay !== true && replay2.idempotentReplay === true && conflict?.code === "IDEMPOTENCY_CONFLICT"
    && receiptMismatch?.code === "RECEIPT_MISMATCH" && persistedFiles && defOutputSchemaOk
    && pubOut.payloadDigest === createHashSync(aggregateOut),
    "信封 11 字段恰（type=document-cross-verification/version=2/outputSchema 11 required+additionalProperties:false）+artifactId=sha256(runId+nodeId+type+version) 前 32 hex 实证+32MB 上限抛+幂等（同键同 payload 重放/异 payload 幂等键冲突/store 层 receipt 不符拒）+payload.json+manifest.json 落盘",
    [pubOut.artifactId, expectedId, tooLarge?.code, conflict?.code, receiptMismatch?.code, persistedFiles]);

  // ── 对拍 12：输出 schema 失败重试（unify 3 次×1s）（行为 16）──
  const rDb = freshDb(join(SCRATCH, "resubmit.db"));
  const captured = [];
  const capturePair = { agent: async (ctx) => { captured.push([ctx.nodeId, ctx.attempt]); return null; } };
  const { composeExecutors } = await import("../../packages/juscite-flow/src/fact-verification.mjs");
  const rEng = directEngine({
    db: rDb, gate: createFlowGate(rDb), dir: SCRATCH,
    executors: composeExecutors(capturePair, cv.createCrossVerificationExecutors({ failFirstSubmitOf: ["unify_business_tree"] }), { activity: async () => ({}), agent: async () => ({ output: {} }) }),
  });
  const rRun = await rEng.startRun({ definition: def, input: GOOD_INPUT, dryRun: true });
  const rFace = rEng.getRunFace(rRun.runId);
  const resubmitEvents = rFace.events.filter((e) => e.kind === "agent.resubmit");
  const unifyAttempts = captured.filter((c) => c[0] === "unify_business_tree").map((c) => c[1]);
  const azWorker = nodesById.get("analyze_documents").worker.outputSubmissionAttempts === 3;
  const cmpWorker = nodesById.get("compare_businesses").worker.outputSubmissionAttempts === 3;
  assert(12, rRun.status === "SUCCEEDED" && JSON.stringify(unifyAttempts) === "[1,2]" && resubmitEvents.length >= 1
    && nodesById.get("unify_business_tree").outputSubmissionAttempts === 3 && azWorker && cmpWorker,
    "agent 坏产出按诊断重提（unify attempt[1,2]+agent.resubmit 事件）；提交上限 3 声明在案（unify/analyze worker/compare worker 三面）",
    [rRun.status, JSON.stringify(unifyAttempts), resubmitEvents.length]);

  // ── 对拍 13：分页读协议不整份进 prompt（行为 19）──
  const unifyInstr = unify.instruction;
  assert(13, unifyInstr.includes("describe") && unifyInstr.includes("分页读") && unifyInstr.includes("不把整份资源塞进提示词"),
    "长资源分页读协议入 instruction（先 describe 再分页读完+明令不整份塞提示词）", unifyInstr.slice(0, 60));

  // ── 对拍 14：groups 三组进度承载（行为 10）──
  const groups = def.groups;
  const grouped = new Set(groups.flatMap((g) => g.nodeIds));
  const eventOrder = (face?.events ?? []).filter((e) => e.kind === "node.succeeded").map((e) => e.nodeId ?? e.payload?.nodeId).filter(Boolean);
  const idxOf = (id) => eventOrder.indexOf(id);
  assert(14, groups.length === 3
    && JSON.stringify(groups.find((g) => g.id === "identify_business")?.nodeIds) === JSON.stringify(["analyze_documents", "validate_coverage"])
    && JSON.stringify(groups.find((g) => g.id === "cross_compare")?.nodeIds) === JSON.stringify(["build_comparison_batches", "compare_businesses"])
    && JSON.stringify(groups.find((g) => g.id === "publish_verification")?.nodeIds) === JSON.stringify(["aggregate_result", "verify_citations", "publish_result"])
    && !grouped.has("prepare_documents") && !grouped.has("unify_business_tree")
    && idxOf("prepare_documents") < idxOf("analyze_documents") && idxOf("validate_coverage") < idxOf("unify_business_tree")
    && idxOf("compare_businesses") < idxOf("aggregate_result") && idxOf("verify_citations") < idxOf("publish_result"),
    "groups 三组恰 7 节点入组（组名/组员逐一同形）+prepare_documents/unify_business_tree 不入组+执行序由 dependsOn 决定（B9 groups 仅展示）",
    [JSON.stringify(groups.map((g) => [g.id, g.nodeIds])), JSON.stringify(eventOrder)]);

  // ── 对拍 15：agent 工具六动作发起：start 即回 runId+禁轮询（行为 11）──
  const tracker = cv.createCrossVerificationRunTracker();
  const started = tracker.start({ documents: GOOD_INPUT.documents, runId: "run.synth.001" });
  const badProto = tryCode(() => tracker.start({ documents: GOOD_INPUT.documents, runId: "__proto__" }));
  const badSpace = tryCode(() => tracker.start({ documents: GOOD_INPUT.documents, runId: "run x" }));
  const badLong = tryCode(() => tracker.start({ documents: GOOD_INPUT.documents, runId: "r".repeat(129) }));
  assert(15, started.runId === "run.synth.001" && started.started === true
    && started.message.includes("请勿在本轮内轮询") && started.message.includes("明确查询") && started.snapshotId?.startsWith("snap.")
    && typeof tracker.start === "function" && typeof tracker.status === "function" && typeof tracker.pause === "function"
    && typeof tracker.resume === "function" && typeof tracker.retry === "function" && typeof tracker.cancel === "function"
    && badProto && badSpace && badLong,
    "start 提交即回 runId 回执（文案自写：勿轮询+用户明确查询才查进度）+六动作齐+runId=SafeId（原型污染名/空格/超 128 均拒）",
    [started.runId, badProto?.message?.slice(0, 30), badSpace?.message?.slice(0, 30)]);

  // ── 对拍 16：生命周期控制边界：retry 恢复/只控本工具 run/主 agent 专用（行为 21）──
  const subagent = tryCode(() => tracker.start({ documents: GOOD_INPUT.documents, runId: "run.sub", via: "subagent" }));
  const notMine = tracker.status("run.other.tool");
  const notMinePause = tracker.pause("run.other.tool");
  const notMineRetry = tracker.retry("run.other.tool");
  tracker.mark("run.synth.001", "failed");
  const retried = tracker.retry("run.synth.001");
  const reRetry = tryCode(() => tracker.retry("run.synth.001")); // 已 running，非失败拒 retry
  tracker.mark("run.synth.001", "failed"); tracker.retry("run.synth.001"); tracker.cancel("run.synth.001");
  const afterCancel = tryCode(() => tracker.pause("run.synth.001"));
  assert(16, subagent?.code === "SUBAGENT_DENIED" && notMine.found === false && notMinePause.found === false && notMineRetry.found === false
    && retried.status === "running" && retried.message.includes("不重新 start") && reRetry?.code === "INVALID_TRANSITION" && afterCancel?.code === "INVALID_TRANSITION",
    "子代理拒发（SUBAGENT_DENIED）+外来 runId 六动作=不存在（只控本工具 run）+retry 仅失败态恢复（不重新 start/不重传）+canceled 后 pause 拒（非法迁移）",
    [subagent?.code, notMine.found, retried.status, reRetry?.code, afterCancel?.code]);

  // ── 对拍 17：status 无命中=任务不存在回执（行为 14）──
  const missStatus = tracker.status("run.nope");
  const hitStatus = tracker.status("run.synth.001");
  assert(17, missStatus.found === false && missStatus.message.includes("交叉核验任务不存在") && hitStatus.found === true && hitStatus.status === "canceled"
    && tracker.listRuns().length === 1,
    "status 查询无命中→「交叉核验任务不存在」具名回执；命中→状态可读（查询态独立于 start 即返语义）",
    [missStatus.message, hitStatus.status]);

  // ── 对拍 18：发布链硬失败面（32MB/类型注册/receipt 不匹配/幂等冲突）（行为 17）──
  const tDb = freshDb(join(SCRATCH, "tamper.db"));
  const tEng = directEngine({ db: tDb, gate: createFlowGate(tDb), dir: SCRATCH, executors: cv.createCrossVerificationExecutors({ tamperAnchorIn: "SHA" }) });
  const tRun = await tEng.startRun({ definition: def, input: GOOD_INPUT, dryRun: true });
  const tFace = tEng.getRunFace(tRun.runId);
  const failEvents = (tFace.events ?? []).filter((e) => e.kind === "run.failed" || e.kind === "node.failed");
  const isolatedType = (await import("../../packages/juscite-flow/src/fact-verification.mjs")).FACT_VERIFICATION_ARTIFACT_TYPE !== cv.CROSS_VERIFICATION_ARTIFACT_TYPE;
  assert(18, tRun.status === "FAILED" && tRun.error === "CITE_REQUIRED" && tFace.artifacts.length === 0 && failEvents.length >= 1
    && tooLarge?.code === "PAYLOAD_TOO_LARGE" && receiptMismatch?.code === "RECEIPT_MISMATCH" && conflict?.code === "IDEMPOTENCY_CONFLICT" && isolatedType,
    "发布链硬失败面四件+类型隔离：锚集损坏→FAILED CITE_REQUIRED 零产物（引用闭环）；payload 超 32MB 抛；store 层 receipt 不符抛；同键异 payload 幂等键冲突抛；type 与 #34 异名异型不互串",
    [tRun.status, tRun.error, tFace.artifacts.length, failEvents.length]);

  // ── 对拍 19：加载态细节/隐藏交互（行为 22,23）——部分实证；形态 UNKNOWN 挂起 ──
  const progTracker = cv.createCrossVerificationRunTracker();
  progTracker.start({ documents: GOOD_INPUT.documents, runId: "run.prog" });
  progTracker.advance("run.prog", { stage: "comparing", done: 5, total: 8 });
  const progStatus = progTracker.status("run.prog");
  assert(19, started.message.includes("进度") && progStatus.progress.stage === "comparing" && progStatus.progress.done === 5
    && dry.panelModel && dry.report,
    "进度承载=状态查询面数据结构在案（advance→status 读回 stage/done）+start 回执文案明示进度获取方式；卡片形态/进度粒度/终态呈现/隐藏交互=UNKNOWN（动态实跑未做，规格 §5 Gaps② 挂起如实）",
    [progStatus.progress.stage, dry.panelModel ? "panel" : null]);

  // ── 对拍 20（OS-1 完成判定门）：应核清单非空且逐位完成才置完成态 ──
  const completeOk = cv.completionGate({ coverageValid: true, comparisons: aggregateOut.comparisons, publishedReceipt: receipt });
  const emptyList = cv.completionGate({ coverageValid: true, comparisons: [], publishedReceipt: receipt });
  const partial = cv.completionGate({ coverageValid: true, comparisons: [...aggregateOut.comparisons, { claimId: "x", status: null }], publishedReceipt: receipt });
  const noReceipt = cv.completionGate({ coverageValid: true, comparisons: aggregateOut.comparisons, publishedReceipt: null });
  const noCoverage = cv.completionGate({ coverageValid: false, comparisons: aggregateOut.comparisons, publishedReceipt: receipt });
  assert(20, completeOk.complete === true && emptyList.complete === false && partial.complete === false && noReceipt.complete === false && noCoverage.complete === false
    && emptyList.reason.includes("空") && partial.reason.includes("部分完成"),
    "完成判定门（计数比对驱动状态位）：应核 8 项逐位完成+覆盖门 valid+发布回执→翻转；空清单/部分完成/缺回执/覆盖门不过均不翻转",
    [completeOk.complete, emptyList.reason, partial.reason]);

  // ── 对拍 21（OS-2 顺序门控）：前序未完成拒后序并具名回执（分发面未立项，纯函数承载）──
  const seq = ["签署方甲", "签署方乙", "归档方"];
  const gateB = cv.sequentialGate({ sequence: seq, completed: ["签署方甲"] }, "签署方乙");
  const gateC = cv.sequentialGate({ sequence: seq, completed: ["签署方甲"] }, "归档方");
  const gateA = cv.sequentialGate({ sequence: seq, completed: [] }, "签署方甲");
  const gateDone = cv.sequentialGate({ sequence: seq, completed: ["签署方甲", "签署方乙"] }, "归档方");
  assert(21, gateA.allowed === true && gateB.allowed === true && gateC.allowed === false && gateC.reason.includes("签署方乙") && gateDone.allowed === true,
    "顺序门控纯函数：按名单序扫描前序完成态，未齐拒动并具名回执（卡位=前序未完成者）；分发/多签收场景立项时接入（规格增补节：未立项标注）",
    [gateC.reason]);

  // ── 对拍 22（OS-3 产物自证链）：报告页脚 artifactId+payloadDigest+生成时间+离线验哈希 ──
  const report = dry.report ?? "";
  const offlineDigest = createHashSync(aggregateOut);
  const panelDiffRow = (dry.panelModel.modules ?? []).flatMap((m) => m.rows).find((r) => r.status === "difference" && r.sideA?.locate && r.sideB?.locate);
  assert(22, report.includes("artifactId=" + pubOut.artifactId) && report.includes("payloadDigest=" + pubOut.payloadDigest)
    && report.includes("生成时间=") && offlineDigest === pubOut.payloadDigest
    && panelDiffRow && panelDiffRow.sideA.locate.anchor && panelDiffRow.sideB.locate.anchor
    && (dry.panelModel.modules ?? []).every((m) => m.moduleId && Array.isArray(m.rows)),
    "人可读报告页脚带 artifactId+payloadDigest+生成时间（离线重算 sha256(payload)=payloadDigest 实证）+差异行双侧原文定位（documentId@anchor）+对照表按统一树两层分组",
    [report.includes("payloadDigest="), offlineDigest === pubOut.payloadDigest, !!panelDiffRow]);

  // ── 对拍 23（OS-4 名单 ACL·挂起）：v1 无公开读路径（负测=零外发/零公开面构造）──
  const domainSrc = readFileSync(join(REPO_ROOT, "packages", "juscite-flow", "src", "cross-verification.mjs"), "utf8");
  const noHttpFace = !/https?:\/\//.test(domainSrc) && !/fetch\(/.test(domainSrc) && !/listen\(/.test(domainSrc);
  assert(23, noHttpFace,
    "受控分发未立项（规格增补节挂起如实）：v1 无外发面负测通过——领域件零 http(s) URL 构造/零 fetch/零监听；断言 OS-4（名单变动即重算+无公开读路径 403/404 负测）立项时生效", []);

  // ── 对拍 24（OS-5 短期预签名 URL·挂起）：零预签名/直链构造 ──
  const noPresign = !/presign|X-Goog|X-Amz|SignedUrl/i.test(domainSrc);
  assert(24, noPresign,
    "受控分发未立项（同上挂起）：v1 零预签名 URL/直链构造面；断言 OS-5（读取走短时效签名 URL ≤15 分钟、过期即拒、无签名参数直链拒）立项时生效", []);

  // ── 对拍 25（OS-6 反面两条不吸收）：append-only 无覆盖路径+外发链接面负测 ──
  const evBefore = progTracker.events.length;
  const snapshotBefore = JSON.stringify(progTracker.events);
  progTracker.advance("run.prog", { stage: "done" }); // 同一 run 多次动作
  progTracker.advance("run.prog", { stage: "done2" });
  const evGrewOnly = progTracker.events.length === evBefore + 2 && JSON.parse(snapshotBefore).every((e, i) => JSON.stringify(progTracker.events[i]) === JSON.stringify(e));
  const storeEvents = store.events.map((e) => e.kind);
  const noOverwritePath = !domainSrc.includes("existingIndex") && domainSrc.includes("events.push");
  const replayKept = replay2.idempotentReplay === true && JSON.stringify(store.get(envA.artifactId).manifest) === JSON.stringify(store.get(envA.artifactId).manifest);
  assert(25, evGrewOnly && noOverwritePath && storeEvents.filter((k) => k === "artifact.persist").length === 1 && storeEvents.includes("artifact.replay") && replayKept && noHttpFace,
    "反面不吸收实证：事件/审计记录=追加写入（同人同 run 多次动作只增不改既有条目）+store 重发布=幂等重放新事件（既有产物零改写）+源码无「按人索引覆盖」式更新路径+外发链接面=v1 无（将来受控分发一律签名票据+短时效）",
    [evGrewOnly, storeEvents]);

  // ── 收尾 ──
  console.log(`[crossverif-synth] 汇总：${passed} OK / ${failed} FAIL`);
  if (failed > 0) { console.error("CROSSVERIF_SYNTH_FAIL"); process.exit(1); }
  console.log("CROSSVERIF_SYNTH_PASS");
  process.exit(0);
}

main().catch((e) => { console.error("[crossverif-synth] FATAL", e); console.error("CROSSVERIF_SYNTH_FAIL"); process.exit(1); })
  .finally(() => { /* SCRATCH 显式清一次便于并行单；Windows 句柄迟释放不视失败 */ try { rmSync(SCRATCH, { recursive: true, force: true }); } catch { /* ignore */ } });
