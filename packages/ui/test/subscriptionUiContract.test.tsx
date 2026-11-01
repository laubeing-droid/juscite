// 【#43 订阅型推理引擎】UI 消费面合同测试（RE-43 §2.2 对拍 10-12 + §3.5 面行为合同，2026-10-30）。
// A 段=kernel 纯合同（等级集/钳制双端标签/隐藏/pending 零推断/粘性钉住/会话内变更协议/三分支/
// 用量条）；B 段=组件渲染面（jsdom+testing-library；桥信封 fetch 全 mock，零真网络零真引擎）。
// 对拍锚点：10 粘性+钉住+每面板独立；11 隐藏规则+Ultra→Max+wire 亲告零推断；12 会话内 reasoning
// 单键提交+session.model 整组一帧+--global 具名拒。
// @vitest-environment jsdom
import { cleanup, render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
// 注意：本测经相对路径直引 @juscite/legal 源文件（非裸包名）——vitest 对裸包名
// （node_modules 符号链）加载会外置依赖，组件内 react 与 react-dom 各绑一份实例，
// useState 全数崩（2026-10-30 实测：裸包名 14 败/相对路径全过）；相对源载入=单实例。
import {
  REASONING_LEVELS,
  USAGE_MANAGE_URL,
  fallbackReasonCopy,
  isReasoningLevel,
  loginBranchCopy,
  loginBranchOf,
  modelCommitOf,
  modelPinnedDotOf,
  reasoningClampOf,
  reasoningCommitOf,
  reasoningMenuLevels,
  reasoningPendingOf,
  reasoningPillLabelOf,
  reasoningPillVisibleOf,
  rejectNonSessionScope,
  stickyModelSelection,
  usageHintOf,
  type SubscriptionStatus,
} from "../../juscite-legal/src/kernel/subscriptionUiModel.js";
import {
  LoginResultView,
  ModelPill,
  ReasoningPill,
  SubscriptionPanel,
  UsageHintBar,
} from "../../juscite-legal/src/panels/SubscriptionPanel.js";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ── A 段：kernel 纯合同 ──

describe("RE-43 §2.2#5 等级集与守卫", () => {
  it("等级全集八档、次序钉定（none→ultra），isReasoningLevel 拒非法值", () => {
    expect([...REASONING_LEVELS]).toEqual([
      "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra",
    ]);
    expect(isReasoningLevel("ultra")).toBe(true);
    expect(isReasoningLevel("mega")).toBe(false);
    expect(isReasoningLevel("")).toBe(false);
    expect(isReasoningLevel(null)).toBe(false);
  });

  it("reasoningMenuLevels 供菜单渲染且与全集一一对应", () => {
    const menu = reasoningMenuLevels();
    expect(menu.map((m) => m.value)).toEqual([...REASONING_LEVELS]);
    expect(menu.every((m) => m.label.length > 0)).toBe(true);
  });
});

describe("RE-43 §2.2#5 对拍 11：钳制判定与双端标签（wire 亲告零推断）", () => {
  it("ultra+亲告 max → 双端钳制；标签显「Ultra→Max」", () => {
    expect(reasoningClampOf("ultra", "max")).toEqual({ picked: "ultra", wire: "max" });
    expect(reasoningPillLabelOf("ultra", "max")).toBe("Ultra→Max");
  });

  it("wire 未上报/空/非法/与 picked 相同 → 一律无钳制（绝不从 picked 推断 wire）", () => {
    expect(reasoningClampOf("ultra", null)).toBeNull();
    expect(reasoningClampOf("ultra", undefined)).toBeNull();
    expect(reasoningClampOf("ultra", "")).toBeNull();
    expect(reasoningClampOf("ultra", "totally-unknown")).toBeNull();
    expect(reasoningClampOf("max", "max")).toBeNull();
    expect(reasoningPillLabelOf("high", null)).not.toContain("→");
  });

  it("picked 非法等级 → 标签空串（不冒充）", () => {
    expect(reasoningPillLabelOf("", null)).toBe("");
    expect(reasoningPillLabelOf("weird", null)).toBe("");
  });
});

describe("RE-43 §2.2#4 对拍 11：pill 隐藏规则", () => {
  it("模型声明无推理控制（显式 false）→ 整 pill 隐藏；unknown（null）不隐藏", () => {
    expect(reasoningPillVisibleOf({ supportsReasoning: false, hasMenuContent: true })).toBe(false);
    expect(reasoningPillVisibleOf({ supportsReasoning: null, hasMenuContent: true })).toBe(true);
    expect(reasoningPillVisibleOf({ supportsReasoning: undefined, hasMenuContent: true })).toBe(true);
  });

  it("无菜单内容 → 隐藏（即使模型未声明否定）", () => {
    expect(reasoningPillVisibleOf({ supportsReasoning: true, hasMenuContent: false })).toBe(false);
  });
});

describe("RE-43 §2.2#7 对拍 11：pending 不猜测原则", () => {
  it("会话未上报自身档位（null/空/非法）→ pending；上报合法档 → 非 pending", () => {
    expect(reasoningPendingOf(null)).toBe(true);
    expect(reasoningPendingOf("")).toBe(true);
    expect(reasoningPendingOf("nope")).toBe(true);
    expect(reasoningPendingOf("high")).toBe(false);
  });
});

describe("RE-43 §2.2#2 对拍 10：钉住圆点（防遗忘手选）与粘性", () => {
  it("钉住圆点=主面板+草稿面（无运行会话）+手选覆盖+模型非空，缺一不可", () => {
    expect(modelPinnedDotOf({ surface: "primary", hasRuntime: false, source: "manual", model: "m1" })).toBe(true);
    expect(modelPinnedDotOf({ surface: "tile", hasRuntime: false, source: "manual", model: "m1" })).toBe(false);
    expect(modelPinnedDotOf({ surface: "primary", hasRuntime: true, source: "manual", model: "m1" })).toBe(false);
    expect(modelPinnedDotOf({ surface: "primary", hasRuntime: false, source: "default", model: "m1" })).toBe(false);
    expect(modelPinnedDotOf({ surface: "primary", hasRuntime: false, source: "manual", model: "  " })).toBe(false);
  });

  it("手选粘性：列表刷新/新对话沿用手选，不回默认；默认跟随引擎列表首项；空列表维持原值", () => {
    expect(stickyModelSelection({ model: "m2", source: "manual" }, ["m1", "m3"])).toBe("m2");
    expect(stickyModelSelection({ model: "", source: "default" }, ["m1", "m3"])).toBe("m1");
    expect(stickyModelSelection({ model: "m2", source: "default" }, [])).toBe("m2");
  });
});

describe("RE-43 §2.2#6 对拍 12：会话内变更协议形状", () => {
  it("档位切换=会话级 reasoning 单键提交；非法档具名拒", () => {
    expect(reasoningCommitOf("low")).toEqual({ scope: "session", key: "reasoning", value: "low" });
    expect(() => reasoningCommitOf("mega")).toThrow("subscription_reasoning_level_invalid");
  });

  it("模型选择=整组（model/provider/reasoning）一帧提交；reasoning 非法落 null；空模型具名拒", () => {
    expect(modelCommitOf({ model: "m1", provider: "chatgpt-sub", reasoning: "high" })).toEqual({
      scope: "session", model: "m1", provider: "chatgpt-sub", reasoning: "high",
    });
    expect(modelCommitOf({ model: "m1", provider: "chatgpt-sub", reasoning: "weird" }).reasoning).toBeNull();
    expect(() => modelCommitOf({ model: " ", provider: "p", reasoning: null })).toThrow("subscription_model_empty");
  });

  it("--global 具名拒（会话级变更协议只收 session scope）", () => {
    expect(() => rejectNonSessionScope("global")).toThrow("subscription_scope_rejected:global");
    expect(() => rejectNonSessionScope("session")).not.toThrow();
  });
});

describe("RE-43 §3.5 登录回调三分支（成功/拒绝/超时）", () => {
  it("typed siwc_* 码→三分支：无码=成功；窗过期与换令牌不可达=超时；校验族/服务器拒/换号=拒绝", () => {
    expect(loginBranchOf(null)).toBe("success");
    expect(loginBranchOf(undefined)).toBe("success");
    expect(loginBranchOf("")).toBe("success");
    expect(loginBranchOf("siwc_login_window_expired")).toBe("timeout");
    expect(loginBranchOf("siwc_exchange_unreachable:http_503")).toBe("timeout");
    expect(loginBranchOf("siwc_state_mismatch")).toBe("rejected");
    expect(loginBranchOf("siwc_exchange_rejected:access_denied")).toBe("rejected");
    expect(loginBranchOf("siwc_client_account_switch_rejected")).toBe("rejected");
    expect(loginBranchOf("siwc_id_token_nonce_mismatch")).toBe("rejected");
    expect(loginBranchOf("siwc_token_exchange_incomplete")).toBe("rejected");
  });

  it("三分支文案：成功含未开套餐子提示；拒绝/超时回显具名码", () => {
    expect(loginBranchCopy("success").title).toBe("登录成功");
    expect(loginBranchCopy("success", null, false).detail).toContain("未开通套餐用量");
    expect(loginBranchCopy("success", null, true).detail).not.toContain("未开通套餐用量");
    expect(loginBranchCopy("rejected", "siwc_state_mismatch").detail).toContain("siwc_state_mismatch");
    expect(loginBranchCopy("timeout", "siwc_login_window_expired").detail).toContain("siwc_login_window_expired");
  });
});

describe("RE-43 §3.5/§2.3 用量提示条数据源（不静默降级）", () => {
  it("用量上限码→专属条（原因码权威）；其余具名回落→回落条（须带回落标记）；无回落不显示", () => {
    expect(usageHintOf({ fallbackUsed: true, fallbackReason: "subscription_usage_limit" }))
      .toEqual({ show: true, kind: "usage_limit", reasonCode: "subscription_usage_limit" });
    // 用量上限码=引擎映射后的权威信号，单独出现即点亮（引擎回执恒带回落标记，此为宽容路径）
    expect(usageHintOf({ fallbackUsed: false, fallbackReason: "subscription_usage_limit" }))
      .toEqual({ show: true, kind: "usage_limit", reasonCode: "subscription_usage_limit" });
    expect(usageHintOf({ fallbackUsed: true, fallbackReason: "siwc_needs_relogin" }))
      .toEqual({ show: true, kind: "fallback", reasonCode: "siwc_needs_relogin" });
    expect(usageHintOf({ fallbackUsed: false, fallbackReason: "siwc_needs_relogin" }).show).toBe(false);
    expect(usageHintOf({ fallbackUsed: true, fallbackReason: null }).show).toBe(false);
    expect(usageHintOf(null).show).toBe(false);
    expect(usageHintOf({}).show).toBe(false);
  });

  it("具名原因文案：三查/用量/终态族映射，未知码原样透传不猜", () => {
    expect(fallbackReasonCopy("siwc_not_logged_in")).toBe("订阅未登录");
    expect(fallbackReasonCopy("siwc_needs_relogin")).toBe("订阅需重新登录");
    expect(fallbackReasonCopy("siwc_plan_usage_absent")).toBe("账号未开通套餐用量");
    expect(fallbackReasonCopy("subscription_usage_limit")).toBe("订阅用量已达上限");
    expect(fallbackReasonCopy("siwc_terminal_invalidated:invalid_grant")).toContain("需重新登录");
    expect(fallbackReasonCopy("siwc_weird_code")).toBe("订阅暂不可用（siwc_weird_code）");
    expect(fallbackReasonCopy(null)).toBe("");
  });
});

// ── B 段：组件渲染面（桥信封 fetch 全 mock）──

function statusFixture(overrides: Partial<SubscriptionStatus> = {}): SubscriptionStatus {
  return {
    engine: "siwc/1",
    hostId: "urn:uuid:00000000-0000-0000-0000-000000000001",
    accounts: [{
      sub: "sub-1", email: "lawyer@example.com", needsLogin: false,
      planUsage: true, defaultModel: "m-a", models: ["m-a", "m-b"],
    }],
    activeSub: "sub-1",
    available: true,
    unavailableReason: null,
    ...overrides,
  };
}

function envelopeOk(result: unknown) {
  return { status: "OWNER_RESPONSE", result };
}
function envelopeErr(code: string) {
  return { status: "NOT_CONNECTED", code };
}
function mockFetchQueue(responses: unknown[]) {
  const queue = [...responses];
  const f = vi.fn(async () => ({
    ok: true,
    json: async () => queue.length ? queue.shift() : envelopeErr("subscription_mock_queue_empty"),
  }));
  vi.stubGlobal("fetch", f);
  return f;
}

describe("SubscriptionPanel 来源卡片（RE-43 §3.5①）", () => {
  it("可用态：引擎徽章=订阅可用，账号信息/默认模型首项上屏", async () => {
    mockFetchQueue([envelopeOk(statusFixture())]);
    render(<SubscriptionPanel />);
    await waitFor(() => expect(screen.getByTestId("subscription-engine-badge").dataset.state).toBe("available"));
    expect(screen.getByTestId("subscription-accounts").textContent).toContain("lawyer@example.com");
    expect(screen.getByTestId("subscription-accounts").textContent).toContain("已登录");
    expect(screen.getByTestId("subscription-accounts").textContent).toContain("套餐用量已开通");
    expect(screen.getByTestId("subscription-models-list").textContent).toContain("默认 m-a");
  });

  it("不可用态：具名原因上屏（三查码不静默）；模型菜单走具名回落不伪造目录", async () => {
    mockFetchQueue([envelopeOk(statusFixture({
      available: false, activeSub: null, unavailableReason: "siwc_not_logged_in",
      accounts: [{ sub: "sub-1", email: null, needsLogin: true, planUsage: false, defaultModel: null, models: [] }],
    }))]);
    render(<SubscriptionPanel />);
    await waitFor(() => expect(screen.getByTestId("subscription-engine-badge").dataset.state).toBe("unavailable"));
    expect(screen.getByTestId("subscription-unavailable-reason").textContent).toContain("订阅未登录");
    fireEvent.click(screen.getByTestId("subscription-model-pill"));
    expect(screen.getByTestId("subscription-model-menu-fallback").textContent).toContain("未登录或不可用");
    expect(screen.queryByTestId("subscription-model-menu")).toBeNull();
  });

  it("发起登录：login_begin 回授权 URL → 新窗打开，面板提示回到此处刷新（面板零端口推断）", async () => {
    const f = mockFetchQueue([
      envelopeOk(statusFixture()),
      envelopeOk({ authorizationUrl: "https://auth.example/authorize?state=s1", state: "s1", expiresIn: 600 }),
    ]);
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<SubscriptionPanel />);
    await waitFor(() => expect(screen.getByTestId("subscription-engine-badge").dataset.state).toBe("available"));
    fireEvent.click(screen.getByTestId("subscription-login"));
    await waitFor(() => expect(open).toHaveBeenCalledWith("https://auth.example/authorize?state=s1", "_blank", "noopener"));
    expect(f).toHaveBeenCalledWith("/api/subscription/login_begin", expect.objectContaining({ method: "POST" }));
    await waitFor(() => expect(screen.getByTestId("subscription-flash").textContent).toContain("刷新"));
  });

  it("退出撤销按钮在无活跃账号时禁用（fail-closed 不空转）", async () => {
    mockFetchQueue([envelopeOk(statusFixture({ activeSub: null }))]);
    render(<SubscriptionPanel />);
    await waitFor(() => expect((screen.getByTestId("subscription-logout") as HTMLButtonElement).disabled).toBe(true));
  });
});

describe("ModelPill/ReasoningPill 组件合同（对拍 10-11）", () => {
  it("live 菜单：展开列出引擎模型；选择回调整组一帧", () => {
    const onSelect = vi.fn();
    render(<ModelPill models={["m-a", "m-b"]} model="m-a" source="default" provider="chatgpt-sub" liveMenu onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("subscription-model-pill"));
    expect(screen.getAllByRole("option").length).toBe(2);
    fireEvent.click(screen.getByTestId("subscription-model-item-m-b"));
    expect(onSelect).toHaveBeenCalledWith("m-b");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("钉住圆点：手选+草稿面显示；默认来源不显示", () => {
    const { rerender, container } = render(
      <ModelPill models={["m1"]} model="m1" source="manual" provider="p" liveMenu onSelect={() => {}} />,
    );
    expect(screen.getByTestId("subscription-model-pinned-dot")).toBeTruthy();
    rerender(<ModelPill models={["m1"]} model="m1" source="default" provider="p" liveMenu onSelect={() => {}} />);
    expect(container.querySelector('[data-testid="subscription-model-pinned-dot"]')).toBeNull();
  });

  it("推理 pill：显式 supportsReasoning=false → 整 pill 不渲染", () => {
    render(<ReasoningPill supportsReasoning={false} picked="high" wire={null} onSelect={() => {}} />);
    expect(screen.queryByTestId("subscription-reasoning-pill")).toBeNull();
  });

  it("推理 pill：未上报档位=pending 等待态（不拿默认档冒充）；上报后显短标签", () => {
    const { rerender } = render(<ReasoningPill supportsReasoning={null} picked="" wire={null} onSelect={() => {}} />);
    expect(screen.getByTestId("subscription-reasoning-pill").dataset.pending).toBe("true");
    expect(screen.queryByTestId("subscription-reasoning-label")).toBeNull();
    rerender(<ReasoningPill supportsReasoning={null} picked="ultra" wire="max" onSelect={() => {}} />);
    expect(screen.getByTestId("subscription-reasoning-pill").dataset.pending).toBe("false");
    expect(screen.getByTestId("subscription-reasoning-label").textContent).toBe("Ultra→Max");
    expect(screen.getByTestId("subscription-reasoning-pill").dataset.clamped).toBe("true");
  });

  it("推理 pill 菜单：选档回调会话级单键；无钳制时 label 单端且 clamped=false", () => {
    const onSelect = vi.fn();
    const { rerender } = render(<ReasoningPill supportsReasoning={null} picked="high" wire={null} onSelect={onSelect} />);
    expect(screen.getByTestId("subscription-reasoning-label").textContent).not.toContain("→");
    expect(screen.getByTestId("subscription-reasoning-pill").dataset.clamped).toBe("false");
    fireEvent.click(screen.getByTestId("subscription-reasoning-pill"));
    fireEvent.click(screen.getByTestId("subscription-reasoning-item-ultra"));
    expect(onSelect).toHaveBeenCalledWith("ultra");
    rerender(<ReasoningPill supportsReasoning={null} picked="ultra" wire={null} onSelect={onSelect} />);
    // wire 未亲告：即使 picked=ultra 也不自造「Ultra→Max」（零推断）
    expect(screen.getByTestId("subscription-reasoning-label").textContent).toBe("Ultra");
  });

  it("每面板独立：两实例各持各的模型与钉住态，互不串写", () => {
    render(
      <div>
        <ModelPill models={["m-a", "m-b"]} model="m-a" source="manual" provider="p" surface="primary" liveMenu onSelect={() => {}} />
        <ModelPill models={["m-a", "m-b"]} model="m-b" source="default" provider="p" surface="tile" hasRuntime liveMenu onSelect={() => {}} />
      </div>,
    );
    const pills = screen.getAllByTestId("subscription-model-pill");
    expect(pills[0]!.textContent).toContain("m-a");
    expect(pills[1]!.textContent).toContain("m-b");
    expect(screen.getAllByTestId("subscription-model-pill")[0]!.querySelector('[data-testid="subscription-model-pinned-dot"]')).toBeTruthy();
    expect(screen.getAllByTestId("subscription-model-pill")[1]!.querySelector('[data-testid="subscription-model-pinned-dot"]')).toBeNull();
  });
});

describe("面板内粘性对齐与用量条集成（对拍 10/§2.3）", () => {
  it("手选后列表刷新：粘性保留手选模型不回默认；选择即落 manual 来源", async () => {
    mockFetchQueue([
      envelopeOk(statusFixture()),
      envelopeOk(statusFixture({
        accounts: [{ sub: "sub-1", email: "lawyer@example.com", needsLogin: false, planUsage: true, defaultModel: "m-c", models: ["m-c"] }],
      })),
    ]);
    render(<SubscriptionPanel />);
    await waitFor(() => expect(screen.getByTestId("subscription-model-pill").textContent).toContain("m-a"));
    fireEvent.click(screen.getByTestId("subscription-model-pill"));
    fireEvent.click(screen.getByTestId("subscription-model-item-m-b"));
    expect(screen.getByTestId("subscription-model-pill").dataset.source).toBe("manual");
    expect(screen.getByTestId("subscription-model-pill").textContent).toContain("m-b");
    // 列表刷新（引擎换列表 m-c）：手选粘性保留 m-b 不回默认
    fireEvent.click(screen.getByTestId("subscription-refresh"));
    await waitFor(() => expect(screen.getByTestId("subscription-models-list").textContent).toContain("默认 m-c"));
    expect(screen.getByTestId("subscription-model-pill").textContent).toContain("m-b");
    expect(screen.getByTestId("subscription-model-pill").dataset.source).toBe("manual");
  });

  it("对话试驾回执 fallbackReason=用量上限 → 面板内点亮专属条+管理用量外链", async () => {
    mockFetchQueue([
      envelopeOk(statusFixture()),
      envelopeOk({
        backend: "api-key:fallback", fallbackUsed: true, fallbackReason: "subscription_usage_limit",
        replyText: "（回落轮合成回复）", requestId: "req-1",
      }),
    ]);
    render(<SubscriptionPanel />);
    await waitFor(() => expect(screen.getByTestId("subscription-engine-badge").dataset.state).toBe("available"));
    fireEvent.change(screen.getByTestId("subscription-probe-input"), { target: { value: "合成试驾" } });
    fireEvent.click(screen.getByTestId("subscription-probe-send"));
    await waitFor(() => expect(screen.getByTestId("subscription-usage-bar").dataset.kind).toBe("usage_limit"));
    const link = screen.getByTestId("subscription-usage-manage");
    expect(link.getAttribute("href")).toBe(USAGE_MANAGE_URL);
    expect(screen.getByTestId("subscription-probe-receipt").textContent).toContain("api-key:fallback");
  });

  it("对话试驾回执无回落 → 不出提示条；来源=订阅 backend", async () => {
    mockFetchQueue([
      envelopeOk(statusFixture()),
      envelopeOk({ backend: "chatgpt-sub:sub-1", fallbackUsed: false, fallbackReason: null, replyText: "合成回复", requestId: "req-2" }),
    ]);
    render(<SubscriptionPanel />);
    await waitFor(() => expect(screen.getByTestId("subscription-engine-badge").dataset.state).toBe("available"));
    fireEvent.change(screen.getByTestId("subscription-probe-input"), { target: { value: "合成试驾二" } });
    fireEvent.click(screen.getByTestId("subscription-probe-send"));
    await waitFor(() => expect(screen.getByTestId("subscription-probe-receipt").textContent).toContain("chatgpt-sub:sub-1"));
    expect(screen.queryByTestId("subscription-usage-bar")).toBeNull();
  });
});

describe("LoginResultView/UsageHintBar 独立渲染合同（RE-43 §3.5②③）", () => {
  it("三分支视图：data-branch 钉定+标题自写", () => {
    const { rerender } = render(<LoginResultView branch="success" planUsage />);
    expect(screen.getByTestId("subscription-login-result").dataset.branch).toBe("success");
    expect(screen.getByTestId("subscription-login-result-title").textContent).toBe("登录成功");
    rerender(<LoginResultView branch="rejected" code="siwc_state_mismatch" />);
    expect(screen.getByTestId("subscription-login-result").dataset.branch).toBe("rejected");
    expect(screen.getByTestId("subscription-login-result-title").textContent).toBe("登录被拒绝");
    rerender(<LoginResultView branch="timeout" code="siwc_login_window_expired" />);
    expect(screen.getByTestId("subscription-login-result").dataset.branch).toBe("timeout");
    expect(screen.getByTestId("subscription-login-result-title").textContent).toBe("登录未完成");
  });

  it("用量条独立渲染：null 回执不渲染；回落条带具名原因与切回指引", () => {
    const { container } = render(<UsageHintBar receipt={null} />);
    expect(container.querySelector('[data-testid="subscription-usage-bar"]')).toBeNull();
    render(<UsageHintBar receipt={{ fallbackUsed: true, fallbackReason: "siwc_needs_relogin" }} />);
    expect(screen.getByTestId("subscription-usage-bar").dataset.kind).toBe("fallback");
    expect(screen.getByTestId("subscription-usage-bar").textContent).toContain("订阅需重新登录");
    expect(screen.getByTestId("subscription-usage-bar").textContent).toContain("不自动切回");
  });
});
