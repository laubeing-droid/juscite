// 【#21 安全层】工具安全设置面板＋审计「工具决策」tab 合同测试（RE-21 增补 §3.1/§2.6/§3.3；
// 施工波二轮 2026-10-30）。Node 环境零 DOM——面板纯模型合同（与 materialAttachments 先例同法）：
// 设置读取宽容面/默认关维持/yolo 档不暴露只留设置键（2026-10-30 用户裁决）/浅合并整对象写回/
// 策略三分目录闭集/审计行守卫与回退链/原因码闭集十枚对齐桥面/ui-kit Switch 端口 fail-fast。
import { describe, expect, it } from "vitest";
import {
  EFFECT_META,
  MODE_LABELS,
  POLICY_TIERS,
  REASON_CODE_LABELS,
  TOOL_DECISIONS_UNAVAILABLE_TEXT,
  UI_EXPOSED_MODES,
  auditRowsForTab,
  effectMetaOf,
  isModeExposed,
  mergeToolSecurityPatch,
  modeDisplayLine,
  readPermissionMode,
  readShellEnabled,
  readToolSecurityRaw,
  reasonCodeLabel,
  selectEffectiveToolDecision,
  toToolDecisionRows,
  toolRowsForTab,
  userDecisionLabel,
  type ToolDecisionRow,
} from "@juscite/legal/panels/toolSecurityModel";
import { Switch } from "@juscite/legal/ui-kit";
import type { AuditRow } from "@juscite/legal/panels/toolSecurityModel";

// 桥侧原因码闭集十枚（tools/bridge/tool_policy.mjs:25-29 REASON_CODES 硬编码对账）
const BRIDGE_REASON_CODES = [
  "read_only", "no_workspace", "writes_files", "external_call",
  "shell_disabled", "permission_not_declared", "destructive",
  "cross_matter", "source_not_enabled", "unknown_tool",
] as const;

const row = (over: Partial<ToolDecisionRow>): ToolDecisionRow => ({
  id: "ta-1", conversationId: "ses-a", runId: null, toolName: "bash",
  effect: "deny", code: "shell_disabled", reason: "命令执行开关未打开",
  policyVersion: 1, userDecision: null, argsSummary: "{}", createdAt: "2026-10-30T10:00:00.000Z",
  ...over,
});

describe("toolSecurityModel 设置读取", () => {
  it("readShellEnabled 缺省=关（默认关维持，2026-10-30 主控裁定）", () => {
    expect(readShellEnabled(undefined)).toBe(false);
    expect(readShellEnabled(null)).toBe(false);
    expect(readShellEnabled({})).toBe(false);
  });

  it("readShellEnabled 只认布尔真值：true 过，1/'yes'/'true' 一律按关（桥侧同款）", () => {
    expect(readShellEnabled({ toolSecurity: { shellEnabled: true } })).toBe(true);
    expect(readShellEnabled({ toolSecurity: { shellEnabled: 1 } })).toBe(false);
    expect(readShellEnabled({ toolSecurity: { shellEnabled: "yes" } })).toBe(false);
    expect(readShellEnabled({ toolSecurity: { shellEnabled: "true" } })).toBe(false);
  });

  it("readToolSecurityRaw 非对象（数组/标量）一律按空对象", () => {
    expect(readToolSecurityRaw({ toolSecurity: [] })).toEqual({});
    expect(readToolSecurityRaw({ toolSecurity: "smart" })).toEqual({});
    expect(readToolSecurityRaw({})).toEqual({});
  });

  it("readPermissionMode 缺省/非法=smart；三档闭集逐值 round-trip", () => {
    expect(readPermissionMode(undefined)).toBe("smart");
    expect(readPermissionMode({})).toBe("smart");
    expect(readPermissionMode({ toolSecurity: { permissionMode: "yolo-not-a-mode" } })).toBe("smart");
    expect(readPermissionMode({ toolSecurity: { permissionMode: "smart" } })).toBe("smart");
    expect(readPermissionMode({ toolSecurity: { permissionMode: "always_ask" } })).toBe("always_ask");
    expect(readPermissionMode({ toolSecurity: { permissionMode: "yolo" } })).toBe("yolo");
    expect(Object.keys(MODE_LABELS).sort()).toEqual(["always_ask", "smart", "yolo"]);
  });

  it("yolo 档不暴露只留设置键（2026-10-30 用户裁决）：界面只出智能档", () => {
    expect(UI_EXPOSED_MODES).toEqual(["smart"]);
    expect(isModeExposed("smart")).toBe(true);
    expect(isModeExposed("yolo")).toBe(false);
    expect(isModeExposed("always_ask")).toBe(false);
  });

  it("档位展示行：默认档给行为说明；非暴露档注明仅设置键 toolSecurity.permissionMode", () => {
    expect(modeDisplayLine("smart")).toContain("智能档");
    expect(modeDisplayLine("always_ask")).toContain("toolSecurity.permissionMode");
    expect(modeDisplayLine("yolo")).toContain("toolSecurity.permissionMode");
    expect(modeDisplayLine("yolo")).not.toContain("界面不提供切换"); // yolo/逐条批措辞区分（裁决只点名 yolo）
  });

  it("mergeToolSecurityPatch 整对象写回：保留 permissionMode 等既有键，只覆写 shellEnabled", () => {
    const raw = { permissionMode: "yolo", shellEnabled: false, futureKey: 1 };
    expect(mergeToolSecurityPatch(raw, { shellEnabled: true })).toEqual({
      permissionMode: "yolo", shellEnabled: true, futureKey: 1,
    });
    expect(mergeToolSecurityPatch(undefined, { shellEnabled: false })).toEqual({ shellEnabled: false });
    expect(mergeToolSecurityPatch("bad", { shellEnabled: true })).toEqual({ shellEnabled: true });
    expect(mergeToolSecurityPatch(raw, {})).toEqual(raw); // 无 patch=原样回写
  });
});

describe("POLICY_TIERS 策略展示目录", () => {
  it("恰三分：effect 闭集=allow/ask/deny，title 非空互异，条目全非空", () => {
    expect(POLICY_TIERS.map((t) => t.effect).sort()).toEqual(["allow", "ask", "deny"]);
    const titles = POLICY_TIERS.map((t) => t.title);
    expect(new Set(titles).size).toBe(3);
    for (const t of POLICY_TIERS) {
      expect(t.title.length).toBeGreaterThan(0);
      expect(t.description.length).toBeGreaterThan(0);
      expect(t.items.length).toBeGreaterThan(0);
      for (const item of t.items) expect(item.length).toBeGreaterThan(0);
    }
  });

  it("判序覆盖面：拒绝档≥3（删除/跨事项/开关关/未声明族），确认档≥3，放行档=只读白名单", () => {
    const byEffect = new Map(POLICY_TIERS.map((t) => [t.effect, t] as const));
    expect(byEffect.get("deny")!.items.length).toBeGreaterThanOrEqual(3);
    expect(byEffect.get("ask")!.items.length).toBeGreaterThanOrEqual(3);
    expect(byEffect.get("allow")!.items.length).toBeGreaterThanOrEqual(1);
  });
});

describe("工具决策行守卫与回退链", () => {
  it("toToolDecisionRows 非数组=[]；完整行按桥 camel 同形映射", () => {
    expect(toToolDecisionRows("nope")).toEqual([]);
    expect(toToolDecisionRows(null)).toEqual([]);
    const src = {
      id: "ta-x", conversationId: "ses-a", runId: "run-1", toolName: "bash",
      effect: "deny", code: "shell_disabled", reason: "r", policyVersion: 1,
      userDecision: null, argsSummary: "{}", createdAt: "2026-10-30T10:00:00.000Z",
    };
    expect(toToolDecisionRows([src])).toEqual([src]);
  });

  it("缺字段兜底：非法 policyVersion=0、非法 userDecision=null、缺 id 行滤除", () => {
    const rows = toToolDecisionRows([
      { id: "ta-2", policyVersion: "NaN-ish", userDecision: "hmm", runId: "", toolName: 42 },
      { toolName: "no-id" },
    ]);
    expect(rows.length).toBe(1);
    expect(rows[0]).toMatchObject({ id: "ta-2", policyVersion: 0, userDecision: null, runId: null, toolName: "42" });
  });

  it("selectEffectiveToolDecision 回退链=find ?? 首行 ?? null（RE-30 对拍 54 同构）", () => {
    const rows = [row({ id: "a" }), row({ id: "b" })];
    expect(selectEffectiveToolDecision(rows, "b")!.id).toBe("b");
    expect(selectEffectiveToolDecision(rows, null)!.id).toBe("a");
    expect(selectEffectiveToolDecision(rows, "ghost")!.id).toBe("a");
    expect(selectEffectiveToolDecision([], null)).toBeNull();
  });
});

describe("审计中心 tab 过滤", () => {
  const auditRow = { id: "a-1", ts: null, actor: null, action: "x", target: null, detail: null, prev_hash: null, hash: "h" } as AuditRow;
  const toolRows = [row({ id: "ta-1" })];

  it("toolRowsForTab 只在 tools tab 出示", () => {
    expect(toolRowsForTab("tools", toolRows)).toEqual(toolRows);
    expect(toolRowsForTab("all", toolRows)).toEqual([]);
    expect(toolRowsForTab("privacy", toolRows)).toEqual([]);
    expect(toolRowsForTab("ops", toolRows)).toEqual([]);
  });

  it("auditRowsForTab 在 tools tab 不出示（专表专视图）；其余 tab 原样", () => {
    const list = [auditRow];
    expect(auditRowsForTab("tools", list)).toEqual([]);
    expect(auditRowsForTab("all", list)).toEqual(list);
    expect(auditRowsForTab("privacy", list)).toEqual(list);
  });

  it("不可用提示文案非空（查询降级如实，不伪装空账）", () => {
    expect(TOOL_DECISIONS_UNAVAILABLE_TEXT.length).toBeGreaterThan(0);
  });
});

describe("码表与徽章", () => {
  it("REASON_CODE_LABELS 与桥侧原因码闭集十枚一一对应", () => {
    expect(Object.keys(REASON_CODE_LABELS).sort()).toEqual([...BRIDGE_REASON_CODES].sort());
    expect(reasonCodeLabel("shell_disabled")).toBe("命令开关未开");
    expect(reasonCodeLabel("never_heard_of")).toBe("never_heard_of"); // 未知码原样回显不猜
  });

  it("决定三态徽章闭集+未知 effect 回退（label=原值/未知）", () => {
    expect(Object.keys(EFFECT_META).sort()).toEqual(["allow", "ask", "deny"]);
    expect(effectMetaOf("deny").label).toBe("已拒绝");
    expect(effectMetaOf("weird").label).toBe("weird");
    expect(effectMetaOf("").label).toBe("未知");
  });

  it("userDecisionLabel 四态：always/allow/deny/未询问", () => {
    expect(userDecisionLabel("always")).toBe("总是允许");
    expect(userDecisionLabel("allow")).toBe("本次允许");
    expect(userDecisionLabel("deny")).toBe("拒绝");
    expect(userDecisionLabel(null)).toBe("未询问");
    expect(userDecisionLabel(undefined)).toBe("未询问");
  });
});

describe("ui-kit Switch 端口", () => {
  it("Switch 已入 kit 出口；未注册（Node 测试环境无宿主）调用 fail-fast 抛错不静默降级", () => {
    expect(typeof Switch).toBe("function");
    expect(() => Switch({ checked: true })).toThrowError(/未注册/);
  });
});
