// 【施工波三轮·#35 尾巴②】Flow Studio/运行看板面板投影合同测试（RE-35 §2 D/E/G 面 UI 消费纯函数）。
// Node 环境零 DOM：状态闭集/未知态 fail-closed 灰具名/运行面摘要计数/关卡冲突回显解析（R2 不自动重放）/
// AI-run 行视图（G1 钉定+G2 严格数值+G3 四元组缺项如实）/定义节点普查（B9 分组仅展示）/发起门槛（草稿只可试跑）。
import { describe, expect, it } from "vitest";
import {
  FLOW_RUN_STATES, FLOW_DEF_SOURCES, runBadgeOf, defBadgeOf, defReadonlyOf, eventLevelBadge,
  summarizeRunFace, conflictCurrentVersionOf, aiRunRowView, defNodeCensus, canStartDefinition,
} from "../src/kernel/flowStudioModel.ts";

describe("flowStudioModel 状态闭集与徽章", () => {
  it("运行七态闭集全覆盖，逐态可取徽章", () => {
    expect(FLOW_RUN_STATES).toEqual(["QUEUED", "RUNNING", "WAITING", "SUSPENDED", "SUCCEEDED", "FAILED", "CANCELLED"]);
    for (const s of FLOW_RUN_STATES) {
      const b = runBadgeOf(s);
      expect(b.unknown).toBeFalsy();
      expect(b.label.length).toBeGreaterThan(0);
    }
  });
  it("未知运行态=灰态具名（fail-closed，不冒充已知态）", () => {
    const b = runBadgeOf("EXPLODED");
    expect(b.unknown).toBe(true);
    expect(b.tone).toBe("idle");
    expect(b.label).toContain("EXPLODED");
  });
  it("定义双来源：builtin 恒只读徽章；draft/published 各得其所；未知来源灰态", () => {
    expect(FLOW_DEF_SOURCES).toEqual(["local", "builtin"]);
    expect(defBadgeOf("builtin", "builtin").label).toContain("只读");
    expect(defReadonlyOf("builtin")).toBe(true);
    expect(defReadonlyOf("local")).toBe(false);
    expect(defBadgeOf("local", "draft").tone).toBe("idle");
    expect(defBadgeOf("local", "published").tone).toBe("ok");
    expect(defBadgeOf("ghost", "draft").unknown).toBe(true);
  });
  it("事件级三态+未知级灰具名", () => {
    expect(eventLevelBadge("error").tone).toBe("err");
    expect(eventLevelBadge("warn").tone).toBe("warn");
    expect(eventLevelBadge("info").tone).toBe("idle");
    expect(eventLevelBadge("").tone).toBe("idle");
    expect(eventLevelBadge("fatal").unknown).toBe(true);
  });
});

describe("flowStudioModel 运行面摘要", () => {
  const face = {
    run: { status: "WAITING", error: null, dryRun: false, waiting: { kind: "gate", nodeId: "gate.review", gateNodeId: "fgn_x" } },
    events: [{ kind: "run.created" }, { kind: "heartbeat" }, { kind: "heartbeat" }, { kind: "node.started", level: "info" }, { kind: "run.failed", level: "error" }],
    aiRuns: [{ id: "a" }, { id: "b" }],
    artifacts: [{ payloadDigest: "0".repeat(64) }],
    chain: { verified: true },
  };
  it("摘要计数：心跳/AI-run/产物/待审关卡齐全", () => {
    const s = summarizeRunFace(face);
    expect(s.status.label).toContain("待审");
    expect(s.chainOk).toBe(true);
    expect(s.heartbeats).toBe(2);
    expect(s.aiRunCount).toBe(2);
    expect(s.artifactCount).toBe(1);
    expect(s.waitingGate).toBe(true);
    expect(s.gateNodeId).toBe("fgn_x");
  });
  it("失败面：错误码透出；链未过给原因不猜", () => {
    const s = summarizeRunFace({
      run: { status: "FAILED", error: { code: "OUTPUT_REJECTED", message: "x" }, waiting: null },
      events: [], aiRuns: [], artifacts: [],
      chain: { verified: false, reason: "事件链在 seq=2 处断裂" },
    });
    expect(s.errorCode).toBe("OUTPUT_REJECTED");
    expect(s.chainOk).toBe(false);
    expect(s.chainNote).toContain("seq=2");
    expect(s.waitingGate).toBe(false);
  });
  it("空面（G4 口径）：零值如实，不抛不造", () => {
    const s = summarizeRunFace({});
    expect(s.aiRunCount).toBe(0);
    expect(s.status.unknown).toBe(true);
    expect(s.chainNote).toContain("未校验");
  });
});

describe("flowStudioModel 关卡冲突回显（R2：不自动重放人审决定）", () => {
  it("「当前 vN」解析出服务端当前版本", () => {
    expect(conflictCurrentVersionOf("版本已推进：你看到的是 v1，当前 v3，请刷新后重新决定")).toBe(3);
  });
  it("无版本号文本=不可解析（null，面板只显示原文）", () => {
    expect(conflictCurrentVersionOf("节点不存在 fgn_x")).toBeNull();
    expect(conflictCurrentVersionOf("")).toBeNull();
  });
});

describe("flowStudioModel AI-run 行视图（G1/G2/G3）", () => {
  it("G1 钉定模型+提示词版本；G2 严格数值才收；G3 四元组缺项如实空串", () => {
    const v = aiRunRowView({
      modelCode: "deepseek-byok/deepseek-chat", promptVersion: "workflow-agent-core-v1",
      riskLevel: "低", riskScore: 0.2, findingsCount: 1,
      findings: [{ clause: "还款期限", level: "低", description: "期限表述待核", advice: "按分段核对" }],
    });
    expect(v.modelPinned).toContain("deepseek-byok/deepseek-chat");
    expect(v.modelPinned).toContain("workflow-agent-core-v1");
    expect(v.riskLine).toContain("0.2");
    expect(v.findingsQuad[0]).toEqual({ clause: "还款期限", level: "低", description: "期限表述待核", advice: "按分段核对" });
  });
  it("未上报=如实标注「未上报」，字符串分值不收（严格数值）", () => {
    const v = aiRunRowView({ modelCode: "m", promptVersion: "p", riskScore: "0.2" as unknown as number, findings: null });
    expect(v.riskLine).toContain("未上报");
    expect(v.findingsCount).toBe(0);
    expect(v.findingsQuad).toEqual([]);
  });
});

describe("flowStudioModel 定义普查与发起门槛", () => {
  const def = {
    nodes: [
      { type: "activity" }, { type: "agent" }, { type: "agent" }, { type: "gate" }, { type: "map" }, { type: "activity" },
    ],
    groups: [{ nodeIds: ["a", "b"] }],
  };
  it("节点普查按型计数，分组注记=仅展示不参与执行（B9）", () => {
    const c = defNodeCensus(def);
    expect(c.total).toBe(6);
    expect(c.byType).toContainEqual({ type: "agent", count: 2 });
    expect(c.byType).toContainEqual({ type: "activity", count: 2 });
    expect(c.byType).toContainEqual({ type: "gate", count: 1 });
    expect(c.groupsNote).toContain("仅界面展示");
  });
  it("空定义零值不抛；未知型节点具名计数", () => {
    expect(defNodeCensus({}).total).toBe(0);
    expect(defNodeCensus({ nodes: [{ type: "weird" }] }).byType[0].type).toBe("weird");
    expect(defNodeCensus({ nodes: [{}] }).byType[0].type).toBe("未知型");
  });
  it("发起门槛：builtin/已发布可发起，草稿只可试跑", () => {
    expect(canStartDefinition("builtin", "builtin").testRunOnly).toBe(false);
    expect(canStartDefinition("local", "published").testRunOnly).toBe(false);
    const d = canStartDefinition("local", "draft");
    expect(d.testRunOnly).toBe(true);
    expect(d.note).toContain("试跑");
  });
});
