// #43 订阅型推理引擎·UI 消费面纯模型（RE-43 §2.2 对话框 pill 行为合同 + §3.5 面行为合同，
// 2026-10-30）。Hermes 桌面版（MIT）行为合同对拍收口：等级集/钳制双端标签/隐藏规则/pending
// 零推断/手选粘性钉住——机制等量、零复制零文案进入（RE-43 §5 吸收清单第 4 行）；
// 对拍 10-12（粘性+钉住+每面板独立／隐藏+钳制显示+wire 亲告零推断／会话内变更协议形状）。
// 本文件零 React 零 fetch：桥端点形状与渲染面在 panels/SubscriptionPanel.tsx。

// ── 推理档位（等级全集；RE-43 §2.2#5 canonical set。ultra=产品内部档：
// OpenAI 兼容线钳到 max 发送、Codex 线原样发——实际下发 wire 档由会话亲告，客户端零推断）──
export const REASONING_LEVELS = [
  "none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra",
] as const;
export type ReasoningLevel = (typeof REASONING_LEVELS)[number];

export function isReasoningLevel(v: unknown): v is ReasoningLevel {
  return typeof v === "string" && (REASONING_LEVELS as readonly string[]).includes(v);
}

// pill 短标签（空间受限档；自写：中文档位词，max/ultra 保留协议档名词形——钳制双端标签
// 钉定显示形「Ultra→Max」按 RE-43 §2.2#5）。
const SHORT_LABELS: Record<ReasoningLevel, string> = {
  none: "关", minimal: "微", low: "低", medium: "中", high: "高",
  xhigh: "超高", max: "Max", ultra: "Ultra",
};

// 推理档菜单全量项（menu 内容；选择=会话级 reasoning 变更，见 reasoningCommitOf）。
export function reasoningMenuLevels(): ReadonlyArray<{ value: ReasoningLevel; label: string }> {
  return REASONING_LEVELS.map((v) => ({ value: v, label: SHORT_LABELS[v] }));
}

// ── 钳制判定（对拍 11）：wire=会话亲告下发档（session.info.reasoning_effort_wire 等价面），
// 空/未上报/与 picked 相同/非法 → 无钳制（null）；亲告与 picked 不同且双方都合法 → 双端。
// 客户端零推断：wire 永远取亲告值，绝不从 picked 猜。
export function reasoningClampOf(
  picked: string,
  wire: string | null | undefined,
): { picked: ReasoningLevel; wire: ReasoningLevel } | null {
  if (!isReasoningLevel(picked) || !isReasoningLevel(wire) || wire === picked) return null;
  return { picked, wire };
}

// pill 标签：有钳制 → 「Ultra→Max」双端（ultra 永不以自身面目冒充 wire 档）；无 → 单端短标签。
export function reasoningPillLabelOf(picked: string, wire?: string | null): string {
  const clamp = reasoningClampOf(picked, wire);
  if (clamp) return `${SHORT_LABELS[clamp.picked]}→${SHORT_LABELS[clamp.wire]}`;
  return isReasoningLevel(picked) ? SHORT_LABELS[picked] : "";
}

// pill 可见性（对拍 11）：模型声明无推理控制（supportsReasoning===false，只认显式否定——
// unknown=null 不隐藏）或无菜单内容 → 整 pill 隐藏。
export function reasoningPillVisibleOf(input: {
  supportsReasoning?: boolean | null;
  hasMenuContent: boolean;
}): boolean {
  if (input.supportsReasoning === false) return false;
  return input.hasMenuContent;
}

// pending（对拍 11/§2.2#7 不猜测原则）：会话未上报自身档位前=pending 等待态；
// 绝不拿默认档位冒充当前档。
export function reasoningPendingOf(reported: string | null | undefined): boolean {
  return !isReasoningLevel(reported);
}

// ── 模型 pill（对拍 10）──

// 钉住圆点（#62055 修复形态：手选粘性静默烧钱的防御）：仅主面板草稿面（无运行会话）+
// 手选覆盖+模型非空时显示。瓦片/运行中会话不显（其页脚自报模型）。
export function modelPinnedDotOf(input: {
  surface: "primary" | "tile";
  hasRuntime: boolean;
  source: "manual" | "default";
  model: string;
}): boolean {
  return input.surface === "primary"
    && !input.hasRuntime
    && input.source === "manual"
    && input.model.trim() !== "";
}

// 粘性：手选钉住——列表刷新/新对话沿用手选，不回默认；默认（source!=="manual"）跟随
// 引擎列表首项（引擎 #11：默认模型=列表首项），列表空则维持原值不猜。
export function stickyModelSelection(
  prev: { model: string; source: "manual" | "default" },
  nextList: readonly string[],
): string {
  if (prev.source === "manual" && prev.model.trim() !== "") return prev.model;
  return nextList.length > 0 ? nextList[0]! : prev.model;
}

// ── 会话内变更协议形状（对拍 12；RE-43 §2.2#6 同构）：档位切换=会话级 reasoning 单键提交；
// 模型选择=整组（model/provider/reasoning）一帧提交。--global 共享网关不收=具名拒。──
export interface ReasoningCommit {
  scope: "session";
  key: "reasoning";
  value: ReasoningLevel;
}
export interface ModelCommit {
  scope: "session";
  model: string;
  provider: string;
  reasoning: ReasoningLevel | null;
}

export function reasoningCommitOf(level: string): ReasoningCommit {
  if (!isReasoningLevel(level)) throw new Error("subscription_reasoning_level_invalid");
  return { scope: "session", key: "reasoning", value: level };
}

export function modelCommitOf(input: {
  model: string; provider: string; reasoning: string | null;
}): ModelCommit {
  if (!input.model.trim()) throw new Error("subscription_model_empty");
  return {
    scope: "session",
    model: input.model,
    provider: input.provider,
    reasoning: input.reasoning && isReasoningLevel(input.reasoning) ? input.reasoning : null,
  };
}

// scope 守卫：非 session（如 global）=具名拒（协议词不照抄，码自写）。
export function rejectNonSessionScope(scope: string): void {
  if (scope !== "session") throw new Error("subscription_scope_rejected:" + scope);
}

// ── 登录回调三分支（RE-43 §3.5；ask 钉定：成功/拒绝/超时）──
export type LoginBranch = "success" | "rejected" | "timeout";

// typed siwc_* 码 → 三分支：窗过期/换令牌不可达=超时；无码=成功；其余（state 对账/
// 服务器拒/同 client 换号/id_token 校验族/换令牌不完整）=拒绝。
export function loginBranchOf(code: string | null | undefined): LoginBranch {
  if (!code) return "success";
  if (code === "siwc_login_window_expired") return "timeout";
  if (code.startsWith("siwc_exchange_unreachable")) return "timeout";
  return "rejected";
}

// 三分支页文案（自写；成功分支含未开套餐子提示——scope 缺套餐用量位）。
export function loginBranchCopy(
  branch: LoginBranch,
  code?: string | null,
  planUsage?: boolean | null,
): { title: string; detail: string } {
  if (branch === "success") {
    return {
      title: "登录成功",
      detail: planUsage === false
        ? "订阅账号已连接本机，但该账号未开通套餐用量（scope 缺用量位）：对话轮将自动回落 API Key。"
        : "订阅账号已连接本机。可在下方查看账号与模型列表。",
    };
  }
  if (branch === "timeout") {
    return {
      title: "登录未完成",
      detail: "授权等待超时或网络不可达，本次登录未生效。请重新发起登录。"
        + (code ? `（code: ${code}）` : ""),
    };
  }
  return {
    title: "登录被拒绝",
    detail: "授权服务器或安全校验未通过，本机未保存任何令牌。请重新发起登录。"
      + (code ? `（code: ${code}）` : ""),
  };
}

// ── 用量提示条（RE-43 §3.5：用量上限提示条+「管理用量」外链，不静默降级；§2.3 回落具名）──
// 管理用量入口（律台 lib/chatgpt.js:18 同一事实 URL，MIT 注明；文案自写）。
export const USAGE_MANAGE_URL = "https://chatgpt.com/settings/usage";

export interface UsageHint {
  show: boolean;
  kind: "usage_limit" | "fallback" | null;
  reasonCode: string | null;
}

// 数据源=对话轮回执（engine chat receipt：fallbackUsed/fallbackReason）。用量上限=专属条
// （带管理用量外链）；其余具名回落原因=回落提示条；无回落=不显示。
export function usageHintOf(
  receipt: { fallbackUsed?: boolean | null; fallbackReason?: string | null } | null | undefined,
): UsageHint {
  const reason = receipt?.fallbackReason ?? null;
  if (reason === "subscription_usage_limit") {
    return { show: true, kind: "usage_limit", reasonCode: reason };
  }
  if (receipt?.fallbackUsed && reason) {
    return { show: true, kind: "fallback", reasonCode: reason };
  }
  return { show: false, kind: null, reasonCode: null };
}

// 具名回落原因→用户提示（自写；覆盖引擎三查/终态/用量/轮次失败族，未知码原样透传不猜）。
export function fallbackReasonCopy(code: string | null | undefined): string {
  if (!code) return "";
  const named: Record<string, string> = {
    siwc_not_logged_in: "订阅未登录",
    siwc_needs_relogin: "订阅需重新登录",
    siwc_plan_usage_absent: "账号未开通套餐用量",
    subscription_usage_limit: "订阅用量已达上限",
    siwc_relogin_required: "订阅需重新登录",
  };
  if (named[code]) return named[code]!;
  if (code.startsWith("siwc_terminal_invalidated")) return "订阅登录已失效，需重新登录";
  return "订阅暂不可用（" + code + "）";
}

// ── 桥端点形状（引擎投影只读面；panels 层 fetch 用）──
export interface SubscriptionAccount {
  sub: string;
  email: string | null;
  needsLogin: boolean;
  planUsage: boolean;
  defaultModel: string | null;
  models: string[];
}
export interface SubscriptionStatus {
  engine: string;
  hostId: string | null;
  accounts: SubscriptionAccount[];
  activeSub: string | null;
  available: boolean;
  unavailableReason: string | null;
}
export interface ChatReceipt {
  backend?: string;
  fallbackUsed?: boolean;
  fallbackReason?: string | null;
  replyText?: string | null;
  requestId?: string | null;
  reasoningEffortWire?: string | null; // 会话亲告 wire 档挂点（engine v1 回执未带=null→无钳制显示，不推断）
}
