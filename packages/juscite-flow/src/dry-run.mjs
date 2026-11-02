// @juscite/flow · 合成执行器（dry-run 面完成定义②：六阶段全合成材料走通，零真模型零 oc28 零外呼）。
// agent+activity 双节点执行同一执行器合同（ctx 进、{output, aiMeta?} 出）——真模型执行接线挂后续集成单，
// 本件只承载引擎机制面（编排/预算/心跳/检查点/产物链/AI-run 记录），产出全部标注 synthetic。
import { AGENT_PROMPT_VERSION } from "./dsl.mjs";
import { parseLineManifest, validateLineManifest, lineManifestToDefinition, buildDecisionSheet } from "./line-manifest.mjs";

const SYN_NOTE = "合成材料产出（dry-run），非真实案件数据";
const CENTS = (yuan) => Math.round(yuan * 100); // 金额一律整型分（工作区工程约束）

// 按能力 id 出合成阶段产物（与办案线交接物契约对形：文件清单/证据包/勾稽表/计算书/文书族/期限表）
const ACTIVITY_OUTPUTS = {
  "line.intake.materials": (input) => ({
    handoff: "材料",
    files: [
      { name: "借条（合成）.pdf", pages: 1, sha256: "syn_" + "0".repeat(24), pageAnchor: "p1" },
      { name: "转账凭证（合成）.png", pages: 1, sha256: "syn_" + "1".repeat(24), pageAnchor: "p1" },
    ],
    parse: { chunks: 6, ocr: "本地 OCR 未启用（合成面不触发）" },
    note: SYN_NOTE,
  }),
  "line.evidence.fix": (input) => ({
    handoff: "证据",
    evidence: [
      { id: "EV-001", kind: "借条", hash: "syn_e1", pageAnchor: "p1" },
      { id: "EV-002", kind: "转账记录", hash: "syn_e2", pageAnchor: "p1" },
    ],
    note: SYN_NOTE,
  }),
  "line.facts.reconcile": (input) => ({
    handoff: "事实",
    reconcileRows: [
      { row: 1, 出借: CENTS(130000), 证据: "EV-001", 还款冲抵: [{ 期次: 1, 金额分: CENTS(20000) }], anchor: "EV-001:p1" },
    ],
    unknowns: [],
    note: SYN_NOTE,
  }),
  "line.compute.ninecalc": (input) => ({
    handoff: "计算",
    modules: ["calc.interest", "calc.court_fee", "calc.calendar_account", "calc.calendar_due_date"],
    principalCents: CENTS(130000),
    interestNote: "过渡档九计算器承担基础算面；域级规则（四倍上限/分段/复利）=JC 完整档挂起位，不出数（台账:69）",
    ruleVersion: "九计算器冻结方法族（JC registry 调用时解析）",
    unknowns: ["2020-08-20 前后分段利率档=UNKNOWN（合成面不外推）"],
    note: SYN_NOTE,
  }),
  "line.drafting.assemble": (input) => ({
    handoff: "文书",
    documents: ["起诉状-民间借贷（合成）", "还款冲抵清单（合成）", "证据清单-民间借贷（合成）"],
    citations: ["EV-001:p1", "EV-002:p1"],
    note: SYN_NOTE,
  }),
  "line.deadlines.calendar": (input) => ({
    handoff: "期限",
    deadlines: [
      { rule: "诉讼时效", basis: "calc.calendar_account/calc.calendar_due_date（合成）", startDay: "2024-01-01", dueDay: "2026-01-01" },
      { rule: "保证期间", basis: "同上（合成）", startDay: "2024-01-01", dueDay: "2024-07-01" },
    ],
    note: SYN_NOTE,
  }),
};

export function createDryRunExecutors({ onAgentOutput } = {}) {
  return {
    async activity(ctx) {
      const factory = ACTIVITY_OUTPUTS[ctx.capability?.id];
      const output = factory ? factory(ctx.input) : { handoff: ctx.nodeId, synthetic: true, note: SYN_NOTE };
      return output;
    },
    async agent(ctx) {
      const stageHandoff = ctx.input?.stage === "facts" ? "事实" : ctx.input?.stage === "drafting" ? "文书" : "出稿";
      const output = {
        handoff: stageHandoff,
        summary: `合成 agent 产出（节点 ${ctx.nodeId}，提交第 ${ctx.attempt} 次）`,
        conclusions: [{ text: "合成结论：按方法组步骤执行（非真实模型）", anchor: "EV-001:p1" }],
        citations: ["EV-001:p1"],
        unknowns: ["LPR 数据包未覆盖时点=UNKNOWN（拒绝外推）"],
        disputes: ["利息起算日之争=争点（合成）"],
        note: SYN_NOTE,
      };
      const aiMeta = {
        modelCode: "synthetic-model",
        promptVersion: ctx.systemPromptVersion ?? AGENT_PROMPT_VERSION,
        riskLevel: "low",
        riskScore: 0.2,
        findingsCount: 1,
        findings: [{ clause: "借条条款（合成）", level: "提示", description: "合成发现：利率表述待核", advice: "合成建议：按方法组核对分段" }],
      };
      onAgentOutput?.({ ctx, output, aiMeta });
      return { output, aiMeta };
    },
  };
}

// 线单六阶段 dry-run：解析→装配→编译→合成执行（闸门走真 flow_gate 机制件，合成复核位过闸）
export async function dryRunLineManifest({ engine, manifestMd, input }) {
  const parsed = parseLineManifest(manifestMd);
  const diag = [...parsed.diagnostics];
  const shapeOk = validateLineManifest(parsed.meta, parsed.format, diag);
  if (!shapeOk) return { ok: false, stage: "validate", diagnostics: diag };
  const assembled = lineManifestToDefinition(parsed.meta);
  if (!assembled.ok) return { ok: false, stage: "assemble", diagnostics: assembled.diagnostics };
  const result = await engine.startRun({
    definition: assembled.definition,
    input: { lineId: parsed.meta.id, ...(input ?? {}) },
    actor: "合成律师·dryrun",
    ref: `line-dryrun:${parsed.meta.id}`,
    dryRun: true,
  });
  if (result.status !== "SUCCEEDED") {
    return { ok: false, stage: "run", runId: result.runId, status: result.status, error: result.error, diagnostics: diag };
  }
  const face = engine.getRunFace(result.runId);
  const stageOutputs = {};
  for (const a of face.artifacts) {
    const stage = a.nodeId?.startsWith("stage.") ? a.nodeId.slice(6) : null;
    if (stage) stageOutputs[stage] = a.payload;
  }
  return {
    ok: true,
    lineId: parsed.meta.id,
    runId: result.runId,
    definition: assembled.definition,
    stages: Object.keys(stageOutputs),
    stageOutputs,
    decisionSheet: buildDecisionSheet(stageOutputs),
    artifacts: face.artifacts,
    aiRuns: face.aiRuns,
    chain: face.chain,
    diagnostics: diag,
  };
}
