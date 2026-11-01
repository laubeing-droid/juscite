#!/usr/bin/env node
// 【功能 #34 事实核验·全量面】合成对拍（RE-34-事实核验.md §4 对拍清单 39 行逐项验收；ci_gate fast mech 随行步）。
// 全合成材料：库=临时目录 node:sqlite（FLOW_ENGINE_DDL 单源导入），trust key=临时目录，零 %APPDATA% 触碰，
// 零端口（进程内直调服务面，:3030/:43127 不接触），零真模型零 oc28（agent 执行=事实核验合成执行器）。
// 对齐物=Andoo workflow-v2 document-fact-verification（RE-34 规格 r11 终修稿）；本 harness 只验我方行为面，
// 竞品行为面以规格 §2/§4 行号为据（锚定纪律：符号名主锚）。编号 1-39 与 §4 对拍行一一对应。
// 纯 Node 零依赖；单命令 exit 0/1，末行 FACTVERIF_SYNTH_PASS 可判。
// 用法：node tools/bridge/fact_verification_synthetic.mjs
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url)); // tools/bridge/ → 仓库根（m1-u01）
let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[factverif-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[factverif-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }
const assert = (n, cond, msg, detail) => (cond ? ok(n, msg) : fail(n, msg, typeof detail === "string" ? detail : JSON.stringify(detail)));
const tryCode = (fn) => { try { const r = fn(); return r instanceof Promise ? r.then(() => null, (e) => e) : null; } catch (e) { return e; } };
const HEX64 = /^[0-9a-f]{64}$/;

const { FLOW_ENGINE_DDL, createFlowEngineService } = await import("./flow_engine_service.mjs");
const { createFlowGate } = await import("./flow_gate_service.mjs");
const fv = await import("../../packages/juscite-flow/src/fact-verification.mjs");
const { createFlowEngine, AGENT_PROMPT_VERSION, AGENT_INSTRUCTION_GUARD, createCapabilityRegistry, registerBuiltinLineCapabilities } =
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

const SCRATCH = mkdtempSync(join(tmpdir(), "juscite-factverif-synth-"));
function freshDb(file) {
  const db = new DatabaseSync(file);
  db.exec("PRAGMA foreign_keys = ON");
  db.exec(FLOW_ENGINE_DDL);
  db.exec(GATE_DDL);
  return db;
}
function freshService({ config } = {}) {
  const dir = mkdtempSync(join(tmpdir(), "juscite-factverif-svc-"));
  const db = freshDb(join(dir, "flow.db"));
  const gate = createFlowGate(db);
  const svc = createFlowEngineService({ db, gate, trustDir: dir, config });
  return { db, gate, svc, dir };
}
// 直连引擎（tamper/重提场景用；执行器可注入）
function directEngine({ db, gate, dir, executors, config } = {}) {
  const capabilities = createCapabilityRegistry();
  registerBuiltinLineCapabilities(capabilities);
  fv.registerFactVerificationCapabilities(capabilities);
  return createFlowEngine({
    db, gate, capabilities, executors, config,
    citeVerify: ({ citations }) => ({ mode: "synthetic", receiptId: "syn_" + citations.length, citationCount: citations.length }),
    dataRoot: dir, trustKeyPath: join(dir, "trust", "attestation.key"),
  });
}

const GOOD_INPUT = { document: { path: "知识产权权属与许可说明（合成）.docx", name: "知识产权权属与许可说明（合成）.docx" }, scope: "专利与商标的登记与许可事项" };

async function main() {
  const def = fv.buildFactVerificationDefinition();
  const nodesById = new Map(def.nodes.map((n) => [n.id, n]));
  const capRisk = new Map(fv.FACT_VERIFICATION_CAPABILITIES.map((c) => [c.id, c]));
  const { svc, db, dir } = freshService({});
  const dry = await svc.flowFactVerifyDryRun({ input: GOOD_INPUT });
  const face = dry.ok ? svc.flowRunGet({ id: dry.runId }) : null;
  const events = face?.events ?? [];
  const outputs = dry.ok ? JSON.parse(db.prepare("SELECT context_json FROM flow_runs WHERE id = ?").get(dry.runId).context_json) : {};

  // ── 对拍 1：入口=文件操作菜单「验证事实」（行为 1；我方=桥 RPC 面 flowFactVerifyDryRun + 工作树接线在案）──
  const bridgeHost = readFileSync(join(REPO_ROOT, "tools", "bridge", "bridge_host.mjs"), "utf8");
  assert(1, typeof svc.flowFactVerifyDryRun === "function" && bridgeHost.includes("flowFactVerifyDryRun"),
    "入口接线在案：服务方法 flowFactVerifyDryRun + bridge_host 转发行（工作树接线与 #35/#43 同批待共享索引收口）",
    ["method", typeof svc.flowFactVerifyDryRun, bridgeHost.includes("flowFactVerifyDryRun")]);

  // ── 对拍 2：Word 目标文档+表格类禁入明文（行为 2）──
  const eXlsx = tryCode(() => fv.validateFactVerificationInput({ document: { path: "对账单（合成）.xlsx" } }));
  const eCsv = tryCode(() => fv.validateFactVerificationInput({ document: { path: "流水（合成）.csv" } }));
  const docxOk = fv.validateFactVerificationInput({ document: { path: "说明（合成）.docx" } });
  const eXlsxRun = await tryCode(() => svc.flowFactVerifyDryRun({ input: { document: { path: "对账单（合成）.xlsx" } } }));
  assert(2, eXlsx?.message?.includes("表格类") && eCsv && docxOk.ok && eXlsxRun?.message?.includes("表格类"),
    "表格类发起即报错（xlsx/csv 拒、docx 收、dry-run 入口同拒）", [eXlsx?.message, eXlsxRun?.code]);

  // ── 对拍 3：path 必填/scope≤2000/附加属性拒绝（行为 3）──
  const noPath = tryCode(() => fv.validateFactVerificationInput({ document: {} }));
  const longPath = tryCode(() => fv.validateFactVerificationInput({ document: { path: "a".repeat(4097) + ".docx" } }));
  const longName = tryCode(() => fv.validateFactVerificationInput({ document: { path: "a.docx", name: "x".repeat(201) } }));
  const longScope = tryCode(() => fv.validateFactVerificationInput({ document: { path: "a.docx" }, scope: "x".repeat(2001) }));
  const extraKey = tryCode(() => fv.validateFactVerificationInput({ document: { path: "a.docx" }, extra: 1 }));
  const boundsOk = fv.validateFactVerificationInput({ document: { path: "a".repeat(4090) + ".docx", name: "x".repeat(200) }, scope: "x".repeat(2000) });
  assert(3, noPath && longPath && longName && longScope && extraKey && boundsOk.ok,
    "输入 schema 同形：path 必填 1-4096/name≤200/scope≤2000/顶层附加属性拒（边界值恰过）",
    [noPath?.message, longPath?.message, extraKey?.message, boundsOk.ok]);

  // ── 对拍 4：预算四限 100/256/4MB/3h（行为 4）──
  const budgetEq = JSON.stringify(def.budget) === JSON.stringify({ maxMapItems: 100, maxAgentExecutions: 256, maxInputBytesPerNode: 4194304, maxRunDurationMs: 10800000 });
  const { db: bDb, dir: bDir } = { db: freshDb(join(SCRATCH, "budget.db")), dir: SCRATCH };
  const bEng = directEngine({ db: bDb, gate: createFlowGate(bDb), dir: bDir, executors: fv.composeExecutors(fv.createFactVerificationExecutors(), { activity: async () => ({}), agent: async () => ({}) }) });
  const bigInput = { document: { path: "a.docx" }, pad: "x".repeat(4194304 + 1024) };
  const budgetHit = await tryCode(() => bEng.startRun({ definition: def, input: bigInput }));
  assert(4, budgetEq && budgetHit?.code === "BUDGET_INPUT",
    "预算闸同值四限（100/256/4MB/3h 声明在案；4MB 输入超限实测拒 BUDGET_INPUT）", [JSON.stringify(def.budget), budgetHit?.code]);

  // ── 对拍 5：结构 agent 同职责+level 规则（行为 5/7）──
  const st = nodesById.get("identify_structure");
  assert(5, st.type === "agent" && st.thinkingLevel === "low" && st.outputVerify === "document.structure" && st.outputSubmissionAttempts === 5
    && st.instruction.includes("自行判断哪些句子是标题") && st.instruction.includes("「一、」类=2，「（一）」类=3，「1．」类=4") && st.tools.length === 1,
    "同职责 agent 节点：自判标题+level 规则入 instruction（low/structure 校验/重提 5）", [st.type, st.thinkingLevel, st.outputVerify]);

  // ── 对拍 6：分页读三段协议+from/until 抽读（行为 6）──
  const matOut = outputs.materialize_structure?.output;
  assert(6, st.instruction.includes("先不带参读第一页") && st.instruction.includes("偏移续读") && st.instruction.includes("from/until")
    && matOut?.pagedRead?.pages?.length >= 2 && matOut.pagedRead.sampled?.[0]?.from === "[dp_0010]",
    "同分页读协议：instruction 三段协议+物化产物带 pagedRead 轨迹（首页→偏移续读→from/until 抽读）", JSON.stringify(matOut?.pagedRead ?? null));

  // ── 对拍 7：ranges 拆段/排他 endAnchor/锚点原样（行为 8-9；空态=scope 空单段全文）──
  const scopeRun = await svc.flowFactVerifyDryRun({ input: { document: GOOD_INPUT.document } }); // scope 缺省→空态
  const noScopeOutputs = scopeRun.ok ? JSON.parse(db.prepare("SELECT context_json FROM flow_runs WHERE id = ?").get(scopeRun.runId).context_json) : {};
  const withScope = outputs.identify_structure?.output?.ranges ?? [];
  const noScope = noScopeOutputs.identify_structure?.output?.ranges ?? [];
  assert(7, withScope.length === 2 && withScope.every((r) => r.startAnchor !== r.endAnchor && r.nodes[0].kind === "heading")
    && withScope[0].startAnchor === "[dp_0010]" && withScope[0].endAnchor === "[dp_0020]" // 标题型 endAnchor=下一同级标题（排他）
    && noScope.length === 1 && noScope[0].startAnchor === "[dp_0001]" && noScope[0].nodes.length === 2,
    "ranges 语义同形：有范围=两章节各一段（排他 endAnchor=下一标题）；无范围=单段覆盖全文（两章节都交）",
    JSON.stringify([withScope.map((r) => [r.startAnchor, r.endAnchor]), noScope.map((r) => r.startAnchor)]));

  // ── 对拍 8：输出 schema 50 段×5000 节点+严格封闭（行为 10）──
  const rangesSchema = st.outputSchema.properties.ranges;
  const nodesSchema = rangesSchema.items.properties.nodes;
  const manyRanges = Array.from({ length: 51 }, (_, i) => ({ startAnchor: "[dp_0010]", endAnchor: "[dp_0020]", nodes: [{ kind: "heading", anchor: "[dp_001" + i + "]", level: 2 }] }));
  const overRanges = fv.validateStructureRanges(manyRanges);
  const badLevel = fv.validateStructureRanges([{ startAnchor: "[dp_0010]", endAnchor: "[dp_0020]", nodes: [{ kind: "heading", anchor: "[dp_0010]", level: 7 }] }]);
  const sameAnchor = fv.validateStructureRanges([{ startAnchor: "[dp_0010]", endAnchor: "[dp_0010]", nodes: [{ kind: "heading", anchor: "[dp_0010]", level: 2 }] }]);
  assert(8, rangesSchema.maxItems === 50 && nodesSchema.maxItems === 5000 && nodesSchema.items.properties.anchor.maxLength === 128
    && st.outputSchema.additionalProperties === false && overRanges.length > 0 && badLevel.length > 0 && sameAnchor.length > 0,
    "同 schema 约束：50 段×5000 节点/anchor≤128/level 1-6/封闭声明+语义校验器（51 段/level 7/空区间均拒）",
    [rangesSchema.maxItems, nodesSchema.maxItems, overRanges.length, badLevel.length, sameAnchor.length]);

  // ── 对拍 9：final_output 诊断重提×5（行为 11/15）──
  const rDb = freshDb(join(SCRATCH, "resubmit.db"));
  const captured = [];
  const capturePair = { agent: async (ctx) => { captured.push([ctx.nodeId, ctx.attempt, ctx.instruction.includes(AGENT_INSTRUCTION_GUARD)]); return null; } };
  const rEng = directEngine({
    db: rDb, gate: createFlowGate(rDb), dir: SCRATCH,
    executors: fv.composeExecutors(capturePair, fv.createFactVerificationExecutors({ failFirstSubmitOf: ["identify_structure"] }), {
      activity: async () => ({}), agent: async () => ({ output: {} }),
    }),
  });
  const rRun = await rEng.startRun({ definition: def, input: GOOD_INPUT });
  const rFace = rEng.getRunFace(rRun.runId);
  const resubmitEvents = rFace.events.filter((e) => e.kind === "agent.resubmit");
  const stAttempts = captured.filter((c) => c[0] === "identify_structure").map((c) => c[1]);
  assert(9, rRun.status === "SUCCEEDED" && JSON.stringify(stAttempts) === "[1,2]" && resubmitEvents.length >= 1 && resubmitEvents[0].payload.errors.length >= 1,
    "同失败重提协议：坏产出按诊断（错因清单）重提后成功；上限 5 声明在案", [rRun.status, JSON.stringify(stAttempts), resubmitEvents.length]);

  // ── 对拍 10：结构物化 write+幂等写（行为 12）──
  const mCap = capRisk.get("docver.structure.materialize");
  assert(10, mCap.risk === "write" && mCap.idempotency === "idempotent-write" && mCap.approval === "implicit"
    && nodesById.get("materialize_structure").capability === "docver.structure.materialize",
    "同能力语义：结构物化 write/idempotent-write（隐式审批=C2 当且仅当）", JSON.stringify([mCap.risk, mCap.idempotency, mCap.approval]));

  // ── 对拍 11：业务识别「只分类不查证不读底稿不改范围」（行为 13）──
  const ib = nodesById.get("identify_businesses");
  const ibOut = outputs.identify_businesses?.output;
  assert(11, ib.instruction.includes("只做分类，不查证，不读底稿，也不改范围") && ib.instruction.includes("范围已冻结")
    && ib.runtimeBindings.bindings[0].name === "structure" && ib.runtimeBindings.bindings[0].value.nodeId === "materialize_structure"
    && ibOut.businesses.length === 2 && ibOut.classificationOnly === true,
    "同职责分离纪律：只分类四条款+结构树经 runtimeBindings（structure←materialize）", ib.instruction.slice(0, 40));

  // ── 对拍 12：项目文件树准备（行为 14）──
  assert(12, capRisk.get("docver.project-file-tree.prepare").risk === "read" && nodesById.get("prepare_project_file_tree").capability === "docver.project-file-tree.prepare"
    && (outputs.prepare_project_file_tree?.output?.tree ?? []).length >= 5,
    "同前置步骤：file-tree.prepare（read）+树产物在案", String((outputs.prepare_project_file_tree?.output?.tree ?? []).length));

  // ── 对拍 13：冻结/排除带理由+空数组+子树收拢+共用目录（行为 15-16；无用户确认环节）──
  const noReason = fv.validateBusinessScopes({ businessScopes: [{ businessId: "b", scopeNodeIds: ["n1"] }], excludedScopes: [{ nodeIds: ["n2"], reason: "r" }] });
  const emptyWithReason = fv.validateBusinessScopes({ businessScopes: [{ businessId: "b", scopeNodeIds: [], reason: "未找到合适底稿，待补充" }], excludedScopes: [{ nodeIds: ["n2"], reason: "r" }] });
  const collapsedIds = fv.collapseSubtreeScopes(["proj.docs.patents", "proj.docs.patents.archive", "proj.docs.shared"]);
  const fz = outputs.freeze_business_scopes?.output;
  const patentScope = (fz?.businessScopes ?? []).find((s) => s.businessId === "biz.patent");
  const trademarkScope = (fz?.businessScopes ?? []).find((s) => s.businessId === "biz.trademark");
  assert(13, noReason.length > 0 && emptyWithReason.length === 0 && JSON.stringify(collapsedIds) === JSON.stringify(["proj.docs.patents", "proj.docs.shared"])
    && !patentScope.scopeNodeIds.includes("proj.docs.patents.archive") && patentScope.reason && (fz.excludedScopes ?? [])[0].reason
    && trademarkScope.scopeNodeIds.includes("proj.docs.shared") && patentScope.scopeNodeIds.includes("proj.docs.shared") && fz.frozen === true,
    "同冻结模型：理由必填/空数组带理由合法/父子收拢为父/两业务共用目录/无用户确认环节（机械冻结）",
    JSON.stringify([noReason.length, emptyWithReason.length, collapsedIds, patentScope?.scopeNodeIds]));

  // ── 对拍 14：主张识别 map×2+表格行可拆不可并（行为 19）──
  const ic = nodesById.get("identify_claims");
  const claimJobs = outputs.prepare_claim_units?.output?.jobs ?? [];
  const row2Job = claimJobs.find((j) => j.unit.kind === "table_row" && j.unit.rowIndex === 2);
  const claimsOut = outputs.identify_claims?.output ?? [];
  const allClaims = claimsOut.flatMap((o) => o.claims ?? []);
  const row2Claims = allClaims.filter((c) => c.unitAnchor === "[/body/tbl[0]:2]");
  const mergedRowClaim = allClaims.some((c) => c.unitKind === "table_row" && /\|\)|；.*行/.test(c.text) === false && c.unitAnchor.includes("|"));
  assert(14, ic.type === "map" && ic.maxConcurrency === 2 && ic.items.nodeId === "prepare_claim_units" && ic.items.path === "jobs"
    && row2Job && row2Claims.length === 2 && allClaims.length === 9 && !mergedRowClaim
    && allClaims.every((c) => /^\[(dp_\d+|\/body\/tbl\[0\]:\d+)\]$/.test(c.unitAnchor)),
    "同拆条纪律：map×2 items←claim_units.jobs；行 2 拆两条（clm.003/004）、9 条主张每条单一单元锚（无跨行合并）",
    JSON.stringify({ row2: row2Claims.map((c) => c.claimId), total: allClaims.length }));

  // ── 对拍 15：匹配限冻结底稿+派生不输入+检索分母五字段（行为 21）──
  const mc = nodesById.get("match_claim_evidence");
  const mcInstruction = mc.worker.instruction;
  const matchOut = outputs.match_claim_evidence?.output ?? [];
  const patentMatch = matchOut.find((m) => m.businessId === "biz.patent");
  const zeroHitClaim = fv.SYNTH_CLAIMS["biz.patent"].find((c) => c.claimId === "clm.005");
  const cov005 = dry.aggregate?.coverage?.perClaim?.["clm.005"];
  assert(15, mc.maxConcurrency === 2 && mc.dependsOn.includes("prepare_claim_match_jobs")
    && mcInstruction.includes("已冻结底稿") && mcInstruction.includes("派生主张")
    && patentMatch && ["searchedSourceIds", "readSourceIds", "unreadableSourceIds", "searchQueries", "searchExhausted"].every((k) => k in patentMatch)
    && patentMatch.searchedSourceIds.length === 3 && patentMatch.searchExhausted === true
    && dry.aggregate.totals.zeroHit.includes("clm.005") && cov005 && cov005.searchedSourceIds.length === 3 && cov005.searchExhausted === true,
    "同边界+分母申报落库：五字段在匹配输出；零命中 clm.005 带分母（已搜 3/穷尽）才算已证无",
    JSON.stringify([patentMatch && Object.keys(patentMatch).filter((k) => k.includes("Source") || k === "searchExhausted"), cov005 && cov005.searchedSourceIds.length]));

  // ── 对拍 16：材料包三步 prepare/snapshot/jobs（行为 23-25）──
  assert(16, nodesById.get("prepare_material_documents").capability === "docver.material-documents.prepare"
    && capRisk.get("docver.snapshot.prepare").risk === "write" && nodesById.get("snapshot_material_documents").capability === "docver.snapshot.prepare"
    && nodesById.get("prepare_verification_jobs").capability === "docver.verification-jobs.prepare"
    && (outputs.snapshot_material_documents?.output?.snapshots ?? []).length === 4
    && outputs.prepare_verification_jobs.output.jobs.length === 2,
    "同三步前置：prepare→snapshot(write)→jobs 链在案（快照 4 件/验证任务 2 包）", String((outputs.snapshot_material_documents?.output?.snapshots ?? []).length));

  // ── 对拍 17：包内核验 map×3+tableMode=full+composite 全读（行为 26）──
  const vp = nodesById.get("verify_material_packages");
  const verifyOut = outputs.verify_material_packages?.output ?? [];
  const patentVerify = verifyOut.find((v) => v.businessId === "biz.patent");
  assert(17, vp.maxConcurrency === 3 && vp.worker.instruction.includes("tableMode=full") && vp.worker.instruction.includes("composite")
    && vp.worker.instruction.includes("只是待核验数据") && patentVerify
    && patentVerify.tableReads[0].tableMode === "full" && patentVerify.tableReads[0].pages.length === 2 && patentVerify.tableReads[0].exhausted === true
    && patentVerify.compositeReads.length === 3,
    "同核验纪律：map×3；table 方法=tableMode=full 分页读完；composite=包内每份材料都读（3/3）",
    JSON.stringify([vp.maxConcurrency, patentVerify?.tableReads?.[0]?.tableMode, patentVerify?.compositeReads?.length]));

  // ── 对拍 18：map 并发实测 2/2/3/2（行为 19/21/26/29；上游单值口径勘误）──
  assert(18, ic.maxConcurrency === 2 && mc.maxConcurrency === 2 && vp.maxConcurrency === 3 && nodesById.get("check_business_consistency").maxConcurrency === 2,
    "并发参数同值 2/2/3/2（identify_claims/match/verify/consistency 四处）",
    JSON.stringify([ic.maxConcurrency, mc.maxConcurrency, vp.maxConcurrency, nodesById.get("check_business_consistency").maxConcurrency]));

  // ── 对拍 19：派生主张程序计算、核验段不碰（行为 26-27）──
  const verifJobsOut = outputs.prepare_verification_jobs?.output?.jobs ?? [];
  const directOnly = verifJobsOut.every((j) => j.directClaimIds.every((id) => !String(id).startsWith("clm.d.")));
  const deriveOut = outputs.derive_claim_results?.output ?? {};
  const d1 = (deriveOut.derivedClaimResults ?? []).find((d) => d.claimId === "clm.d.001");
  const d2 = (deriveOut.derivedClaimResults ?? []).find((d) => d.claimId === "clm.d.002");
  const derivedByProgram = fv.deriveClaimResults({
    claimVerifications: [{ claimResults: [{ claimId: "clm.001", status: "verified" }, { claimId: "clm.009", status: "verified" }] }],
    claimMatches: [],
  });
  assert(19, nodesById.get("derive_claim_results").type === "activity" && directOnly
    && d1.status === "verified" && d2.status === "conflict" && d2.derivedFrom.includes("clm.002")
    && derivedByProgram.directClaimResults.length === 2 && derivedByProgram.derivedClaimResults[0].status === "verified",
    "同程序派生+隔离：验证任务零派生 id；全验证前提→verified/含冲突前提→conflict；derive=activity 非.agent",
    JSON.stringify([d1?.status, d2?.status, directOnly]));

  // ── 对拍 20：一致性六条款（行为 29）──
  const cc = nodesById.get("check_business_consistency");
  const ccOut = outputs.check_business_consistency?.output ?? [];
  const trademarkRel = ccOut.find((c) => c.businessId === "biz.trademark");
  const oneClaimId = fv.validateConsistencyRelations([{ ruleFamily: "value", claimIds: ["clm.001"], status: "consistent", message: "m" }]);
  const badFamily = fv.validateConsistencyRelations([{ ruleFamily: "tone", claimIds: ["clm.001", "clm.002"], status: "consistent", message: "m" }]);
  const badStatus = fv.validateConsistencyRelations([{ ruleFamily: "value", claimIds: ["clm.001", "clm.002"], status: "maybe", message: "m" }]);
  const emptyOk = fv.validateConsistencyRelations([]);
  const dupPremise = fv.validateConsistencyRelations([{ ruleFamily: "value", claimIds: ["clm.001", "clm.d.001"], status: "consistent", message: "m" }], [{ claimId: "clm.d.001", derivedFrom: ["clm.001", "clm.009"] }]);
  const relations = (ccOut.flatMap((c) => c.relations ?? []) ?? []);
  assert(20, !("tools" in cc.worker) && oneClaimId.length > 0 && badFamily.length > 0 && badStatus.length > 0 && emptyOk.length === 0 && dupPremise.length > 0
    && relations.length === 2 && relations.every((r) => fv.CONSISTENCY_RULE_FAMILIES.includes(r.ruleFamily) && fv.CONSISTENCY_STATUSES.includes(r.status))
    && trademarkRel.relations.length === 0,
    "同六条款：worker 无工具/≥2 claimId/四枚举×2/空 relations 合法/不重复 derived 与 premise（validator 负例全拒）",
    JSON.stringify([oneClaimId.length, badFamily.length, badStatus.length, dupPremise.length, relations.length]));

  // ── 对拍 21：五路聚合（行为 30）──
  const aggNode = nodesById.get("aggregate_fact_verification");
  const aggRefs = Object.values(aggNode.input).map((r) => r.nodeId).sort();
  assert(21, JSON.stringify(aggRefs) === JSON.stringify(["check_business_consistency", "derive_claim_results", "identify_businesses", "prepare_claim_match_jobs", "prepare_verification_jobs"])
    && dry.aggregate && ["businesses", "claimJobs", "claimResults", "consistency", "verificationJobs"].every((k) => k in dry.aggregate),
    "同聚合输入面：恰五路引用（businesses/claimJobs/claimResults/consistency/verificationJobs）+聚合产物五节俱在",
    JSON.stringify(aggRefs));

  // ── 对拍 22：cite.verify 全文引用校验（行为 31）──
  const badMarkReceipt = fv.verifyFactCitations(
    { claimResults: { direct: [{ claimId: "x", citations: ["[[document:src.patent.cert||page:9||quote:不存在页]]"] }] } },
    fv.SYNTH_SNAPSHOTS,
  );
  const goodMarkReceipt = fv.verifyFactCitations(
    { claimResults: { direct: [{ claimId: "x", citations: ["[[document:src.patent.cert||page:1||quote:专利号 ZL202310000001.0]]", "[[document:src.trademark.reg||sheet:注册登记表||cell:B2||quote:第 45 类]]"] }] } },
    fv.SYNTH_SNAPSHOTS,
  );
  const citeNodeOut = outputs.verify_fact_citations?.output;
  assert(22, nodesById.get("verify_fact_citations").capability === "docver.cite-verify"
    && goodMarkReceipt.ok && goodMarkReceipt.verifiedCount === 2
    && badMarkReceipt.ok === false && badMarkReceipt.failures[0].reason.includes("页码越界")
    && citeNodeOut.mode === "deterministic" && citeNodeOut.citationCount === 7 && citeNodeOut.verifiedCount === 7,
    "同后端引用核验：确定性校验（页码越界/文本不逐字→失败列名）；dry-run 7/7 引用全过（含表格变体 cell:B2）",
    JSON.stringify([goodMarkReceipt.verifiedCount, badMarkReceipt.failures[0].reason, citeNodeOut.citationCount]));

  // ── RE-12 对照源增补节 T40-T42 #34 接线回执：直接主张 fact↔引文支持性回验（cite-verify 回执携 quoteBack）──
  const qb34 = citeNodeOut.quoteBack;
  assert("22b", Boolean(qb34) && qb34.total === 7 && qb34.counts.pass === 2 && qb34.counts.mismatch === 5 && qb34.counts.fabricated === 0
    && qb34.counts.uncited === 2 && qb34.uncited?.map((u) => u.claimId).join(",") === "clm.005,clm.006"
    && qb34.derivedOutOfScope?.length === 0 && qb34.noValue?.length === 0
    && qb34.results?.find((r) => r.verdict === "pass")?.claimId === "clm.001"
    && qb34.results?.filter((r) => r.verdict === "pass").map((r) => r.claimId).join(",") === "clm.001,clm.008",
    "tabular-review 接线：已作答 7 主张入分母（逐字复现 2 pass=clm.001/clm.008；转述式事实句 5 mismatch=机制立场：改写即不可逐字核）+零命中待核验 clm.005/006 显式 uncited 单列（如实未答族不落编造桶）",
    JSON.stringify(qb34?.counts));
  const qb34neg = fv.verifyFactQuoteBack([
    { claimId: "neg.fab", status: "verified", conclusion: { fact: "无中生有的结论句" }, citations: [] },
    { claimId: "neg.pending", status: "pending", conclusion: { fact: "零命中待核验句" }, citations: [] },
    { claimId: "clm.d.neg", derivedByProgram: true, conclusion: { fact: "程序归并结论" }, citations: [] },
  ]);
  assert("22c", qb34neg.counts.fabricated === 1 && qb34neg.results?.[0]?.verdict === "fabricated"
    && qb34neg.counts.uncited === 1 && qb34neg.derivedOutOfScope?.[0] === "clm.d.neg",
    "回验适配器负例三派：已作答（verified）零引文→fabricated 编造旗标（RE-12 规则二）；待核验（pending）零引文→uncited 如实未答族；派生主张→显式出分母",
    JSON.stringify(qb34neg.counts));

  // ── 对拍 23：publish type=document-fact-verification v1+citeReceipt（行为 32；与 #33 异名异型）──
  const env = outputs.publish_fact_verification?.output;
  const envelopeKeys = Object.keys(env ?? {});
  assert(23, env.type === "document-fact-verification" && env.version === 1 && env.citeReceipt.ok
    && env.type !== fv.CROSS_VERIFICATION_ARTIFACT_TYPE
    && ["artifactId", "runId", "nodeId", "projectId", "sessionId", "type", "version", "renderer", "payloadDigest", "byteLength", "createdAt"].every((k) => envelopeKeys.includes(k)),
    "同 artifact 类型（与 #33 隔离）：type=document-fact-verification v1+信封前 11 字段同族+citeReceipt 随发",
    JSON.stringify([env.type, env.version, envelopeKeys.length]));

  // ── 对拍 24：attestation 信任锚（行为 33；接线差异如实标注）──
  const trustKeyPath = join(dir, "trust", "attestation.key");
  const keyHex = existsSync(trustKeyPath) ? readFileSync(trustKeyPath, "utf8").trim() : "";
  const journalText = db.prepare("SELECT group_concat(message_json, '|') AS t, group_concat(hash, '|') AS h FROM flow_run_events WHERE run_id = ?").get(dry.runId);
  assert(24, dry.chain.verified === true && dry.chain.length >= 40 && keyHex.length === 64
    && !(journalText.t + journalText.h).includes(keyHex) && HEX64.test(env.payloadDigest),
    "产物完整性锚机制对齐：run 事件链 HMAC 全验（" + dry.chain.length + " 事件）+密钥不入日志+payloadDigest 64hex；接线差异=我方引擎级链（竞品 publish→attestation 接线 UNKNOWN 如实标注）",
    JSON.stringify(dry.chain));

  // ── 对拍 25：（mike 对照）tabular 引文无后端核验=半个坑 → 我方 citations 必过闭环（有意差异）──
  const tDb = freshDb(join(SCRATCH, "tamper.db"));
  const tEng = directEngine({
    db: tDb, gate: createFlowGate(tDb), dir: SCRATCH,
    executors: fv.composeExecutors(fv.createFactVerificationExecutors({ tamperQuoteIn: "src.patent.cert" }), { activity: async () => ({}), agent: async () => null }),
  });
  const tRun = await tEng.startRun({ definition: def, input: GOOD_INPUT });
  const tArtifacts = tDb.prepare("SELECT COUNT(*) AS c FROM flow_artifacts WHERE run_id = ?").get(tRun.runId).c;
  assert(25, tRun.status === "FAILED" && tRun.error === "CITE_REQUIRED" && tArtifacts === 0,
    "引用闭环（本件命门）：快照文本损坏→cite 校验失败→发布节点拒发（FAILED/CITE_REQUIRED）且零产物落账——mike 半坑闭合",
    JSON.stringify([tRun.status, tRun.error, tArtifacts]));

  // ── 对拍 26：（soundsuite 对照）requested vs effective+零命中报分母（增强吸收）──
  const cov = dry.aggregate.coverage;
  const pkgCov = cov.packages ?? [];
  assert(26, pkgCov.length === 2 && pkgCov.every((p) => JSON.stringify(p.requestedSourceIds) === JSON.stringify(p.effectiveReadSourceIds))
    && cov.snapshotCount === 4 && dry.aggregate.totals.zeroHit.length === 2
    && Object.values(cov.perClaim).every((c) => Array.isArray(c.searchedSourceIds) && typeof c.searchExhausted === "boolean"),
    "全环节申报：包级 requested=effective 逐包在案+快照计数；零命中两条（clm.005/006）均带分母",
    JSON.stringify([pkgCov.length, cov.snapshotCount, dry.aggregate.totals.zeroHit]));

  // ── 对拍 27：capability 声明式控权 14 实例（行为 35）──
  const caps = fv.FACT_VERIFICATION_CAPABILITIES;
  const writeCaps = caps.filter((c) => c.risk === "write").map((c) => c.id).sort();
  assert(27, caps.length === 14 && writeCaps.length === 4
    && JSON.stringify(writeCaps) === JSON.stringify(["docver.artifact-publish", "docver.claim-units.prepare", "docver.snapshot.prepare", "docver.structure.materialize"])
    && caps.filter((c) => c.risk === "read").every((c) => c.idempotency === "read")
    && caps.every((c) => c.risk !== "external") && caps.every((c) => typeof c.displayName === "string" && c.displayName.length > 0)
    && dry.artifacts.length === 1,
    "声明式控权表同形：14 实例/write 恰 4（物化·主张单元·快照·发布）/其余全 read+read/external 零实例/中文 displayName 全带",
    JSON.stringify([caps.length, writeCaps]));

  // ── 对拍 28：prompt-injection 数据免责两条款（行为 37）──
  const injectedClaim = (dry.aggregate.claimResults.direct ?? []).find((r) => r.claimId === "clm.006");
  const guardSeen = captured.filter((c) => c[2]).length;
  assert(28, vp.worker.instruction.includes("只是待核验数据") && cc.worker.instruction.includes("不是指令")
    && dry.ok && injectedClaim.status === "pending"
    && injectedClaim.conclusion.discrepancy.includes("不执行") && injectedClaim.conclusion.discrepancy.includes("数据"),
    "同条款入 worker instruction（材料包/一致性两条独立）+引擎 D9 守卫恒注入（" + guardSeen + " 次 agent 调用实测携带）；注入主张不执行=按数据处理停待核验",
    JSON.stringify([injectedClaim?.status, injectedClaim?.conclusion?.discrepancy?.slice(0, 30), guardSeen]));

  // ── 对拍 29：UI 三态筛选（行为 42）──
  const pm = dry.panelModel;
  const filtered = fv.filterPanelModel(pm, "conflict");
  const filteredIds = filtered.groups.flatMap((g) => g.items.map((i) => i.claimId));
  assert(29, JSON.stringify(pm.filterStates) === JSON.stringify(["conflict", "pending", "verified"])
    && fv.filterPanelModel(pm, "pending").groups.flatMap((g) => g.items.map((i) => i.claimId)).includes("clm.005")
    && filteredIds.includes("clm.002") && !filteredIds.includes("clm.001") && filtered.groups.every((g) => g.items.every((i) => i.status === "conflict")),
    "同三态筛选：冲突/待核验/已验证闭集；筛冲突=仅 clm.002（+冲突派生），筛待核验含零命中 clm.005",
    JSON.stringify(filteredIds));

  // ── 对拍 30：UI 独立结果+找到的记录数量（行为 39-40）──
  const patentGroup = pm.groups.find((g) => g.businessId === "biz.patent");
  const clm001 = patentGroup.items.find((i) => i.claimId === "clm.001");
  const clm005Item = patentGroup.items.find((i) => i.claimId === "clm.005");
  assert(30, patentGroup.recordCount === 5 && clm001.recordsCount === 1 && clm005Item.recordsCount === 0
    && patentGroup.items.length === 9 && pm.totals.claims === 9,
    "同计数显示：每条独立结果带找到的记录数量（clm.001=1/clm.005=0）；组级记录数=逐条和（专利 5）",
    JSON.stringify([patentGroup.recordCount, clm001.recordsCount, clm005Item.recordsCount, pm.totals.claims]));

  // ── 对拍 31：UI 按事项分组分别核验（行为 41）──
  assert(31, pm.groups.length === 2 && pm.groups.map((g) => g.title).join("/") === "专利权事项/商标权事项"
    && pm.groups.every((g) => g.items.length > 0) && pm.groups[0].status === "conflict" && pm.groups[1].status === "verified",
    "同分组维度：按事项（专利权/商标权）分别核验；组态=最劣主张态（专利=冲突/商标=已验证）",
    JSON.stringify(pm.groups.map((g) => [g.businessId, g.items.length, g.status])));

  // ── 对拍 32：UI 结果三段+「定位原文」回跳（行为 43-44；§3.1 引文格式条）──
  const clm002 = patentGroup.items.find((i) => i.claimId === "clm.002");
  const clm007 = pm.groups.find((g) => g.businessId === "biz.trademark").items.find((i) => i.claimId === "clm.007");
  assert(32, clm001.fact && clm001.discrepancy && clm001.support
    && clm002.locate && clm002.locate.documentId === "src.patent.cert" && clm002.locate.page === 2 && clm002.locate.anchorKind === "page"
    && clm007.locate.sheet === "注册登记表" && clm007.locate.cell === "B2" && clm007.locate.anchorKind === "sheet-cell"
    && fv.parseCitationMark("[[document:x||page:1||quote:q]]").page === 1,
    "同三段结构（提取的事实/核查差异/材料支持）+定位原文：页锚 page=2 可跳；表格变体落 sheet!cell（page+bbox 渲染层挂 #6 定位层衔接）",
    JSON.stringify([clm002.locate, clm007.locate]));

  // ── 对拍 33：主张匹配任务备料 activity（行为 20）──
  assert(33, capRisk.get("docver.claim-match-jobs.prepare").risk === "read" && capRisk.get("docver.claim-match-jobs.prepare").idempotency === "read"
    && nodesById.get("prepare_claim_match_jobs").type === "activity"
    && mc.items.nodeId === "prepare_claim_match_jobs" && aggNode.input.claimJobs.nodeId === "prepare_claim_match_jobs",
    "同备料步骤：claim-match-jobs.prepare（read）输出被 match.items 与聚合 claimJobs 两条引用", "");

  // ── 对拍 34：材料包规划 activity（行为 22）──
  assert(34, capRisk.get("docver.material-packages.plan").risk === "read" && nodesById.get("plan_material_packages").type === "activity"
    && (outputs.plan_material_packages?.output?.packages ?? []).length === 2,
    "同规划步骤：material-packages.plan（read）两包在案", "");

  // ── 对拍 35：一致性任务备料 activity（行为 28）──
  assert(35, capRisk.get("docver.consistency-jobs.prepare").risk === "read" && nodesById.get("prepare_consistency_jobs").type === "activity"
    && cc.items.nodeId === "prepare_consistency_jobs" && (outputs.prepare_consistency_jobs?.output?.jobs ?? []).length === 2,
    "同备料步骤：consistency-jobs.prepare（read）两业务任务在案", "");

  // ── 对拍 36：全 agent/map-worker systemPromptVersion 钉定（行为 34）──
  const agentFaces = [...def.nodes.filter((n) => n.type === "agent"), ...def.nodes.filter((n) => n.type === "map").map((n) => n.worker)];
  assert(36, agentFaces.length === 7 && agentFaces.every((n) => n.systemPromptVersion === AGENT_PROMPT_VERSION)
    && (rFace.aiRuns ?? []).every((a) => a.promptVersion === AGENT_PROMPT_VERSION),
    "同钉定机制：3 agent+4 map-worker 全部钉 " + AGENT_PROMPT_VERSION + "；AI-run 记录版本同钉", String(agentFaces.length));

  // ── 对拍 37：职责分离三节点三纪律分立（行为 36）──
  assert(37, st.instruction.includes("自行判断哪些句子是标题") && st.instruction.includes("冻结核验范围")
    && ib.instruction.includes("只做分类") && ib.instruction.includes("不改范围")
    && (ic.worker.instruction.includes("不得") && mc.worker.instruction.includes("不得新增、删除或改写主张") && vp.worker.instruction.includes("不得核验程序生成的派生主张")),
    "同三纪律分立入各自 instruction：结构（自判标题+冻结范围）/业务（只分类不改范围）/主张链（不增删改+不越冻结+不碰派生）", "");

  // ── 对拍 38：「拆条逐个核对」叙事定位（行为 38；文案自写）──
  assert(38, pm.narrative.includes("逐条") && pm.narrative.includes("不笼统回答") && pm.narrative.includes("拆开"),
    "同拆条叙事（结果面板文案自写）：逐条拆开/不笼统回答整份文件", pm.narrative.slice(0, 30));

  // ── 对拍 39：主张单元备料 activity（行为 18，write 类）──
  const cuCap = capRisk.get("docver.claim-units.prepare");
  assert(39, cuCap.risk === "write" && cuCap.idempotency === "idempotent-write" && cuCap.approval === "implicit"
    && nodesById.get("prepare_claim_units").type === "activity" && claimJobs.length === 8,
    "同备料步骤（write 类，与结构物化/快照/发布同族）：claim-units.prepare write/idempotent-write；单元 8 job（行单元去重）",
    JSON.stringify([cuCap.risk, cuCap.idempotency, claimJobs.length]));

  // ── 收尾 ──
  console.log(`[factverif-synth] ── ${passed} OK / ${failed} FAIL ──`);
  try { rmSync(SCRATCH, { recursive: true, force: true }); } catch { /* Windows 句柄延迟，残留临时目录无害 */ }
  try { rmSync(dir, { recursive: true, force: true }); } catch { /* 同上 */ }
  if (failed > 0) { console.error("FACTVERIF_SYNTH_FAIL"); process.exit(1); }
  console.log("FACTVERIF_SYNTH_PASS");
}
main().catch((e) => { console.error("[factverif-synth] UNCAUGHT", e); process.exit(1); });
