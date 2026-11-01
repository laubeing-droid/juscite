// #43 订阅型推理引擎·UI 消费面（RE-43 §3.5 面行为合同落码，2026-10-30）。
// 四件：①模型与连接来源卡片（登录/账号信息/模型列表/用量入口/退出撤销/测试连接）；
// ②登录回调三分支页（成功[含未开套餐子提示]/拒绝/超时——授权浏览器窗口由桥 /auth/callback
// 渲染同合同页，应用内经状态刷新判定落同款三分支视图）；③用量提示条（用量上限专属条+
// 「管理用量」外链/具名回落提示条，数据源=对话轮回执 fallbackReason，不静默降级）；
// ④对话框模型 pill/推理强度 pill（RE-43 §2.2 对拍 10-12 收口：粘性+钉住+每面板独立／
// 隐藏规则+Ultra→Max 双端标签+wire 亲告零推断／会话内变更协议形状——合同函数在
// kernel/subscriptionUiModel.ts，本组件消费之）。对话试驾盒=chat 面消费挂点（回执点亮提示条）。
// 数据经 /api/subscription/* 桥端点族（subscription_service.mjs）；fail-closed 具名报错。
// 文案全部自写（表达隔离）；纯 HTML 元素+lucide 图标（LawBookPanel 同款，不直改上游面板）。
import { useCallback, useEffect, useMemo, useState } from "react";
// 刻意零 lucide-react：vitest 面内 lucide 与 react-dom 各绑一份 react 实例（useContext null）
// ——面板图内零第三方 react 消费者后，react 实例单一（2026-10-30 实测注记）。
import {
  USAGE_MANAGE_URL, fallbackReasonCopy, loginBranchCopy, modelPinnedDotOf,
  modelCommitOf, reasoningCommitOf, reasoningMenuLevels, reasoningPendingOf,
  reasoningPillLabelOf, reasoningPillVisibleOf, stickyModelSelection,
  usageHintOf, rejectNonSessionScope,
  type ChatReceipt, type LoginBranch, type ReasoningLevel, type SubscriptionStatus,
} from "../kernel/subscriptionUiModel.js";

type Envelope<T> = { status: "OWNER_RESPONSE"; result: T } | { status: "NOT_CONNECTED"; code: string };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api/subscription/${path}`, { cache: "no-store", ...init });
  const j = (await r.json().catch(() => ({}))) as Partial<Envelope<T>> | null;
  if (j && j.status === "OWNER_RESPONSE" && j.result !== undefined) return j.result;
  const code = j && "code" in j && typeof j.code === "string" ? j.code : `subscription_bridge_http_${r.status}`;
  throw new Error(code);
}

// ── 登录回调三分支视图（RE-43 §3.5；branch/code 为已知结局时渲染对应分支——
// 授权浏览器窗口的整页由桥渲染同合同 HTML，应用内视图供状态判定与后续嵌入）──
export function LoginResultView(props: { branch: LoginBranch; code?: string | null; planUsage?: boolean | null }) {
  const copy = loginBranchCopy(props.branch, props.code, props.planUsage);
  return (
    <div
      data-testid="subscription-login-result"
      data-branch={props.branch}
      className="rounded-lg border border-border/60 p-3"
    >
      <div
        data-testid="subscription-login-result-title"
        className={
          props.branch === "success"
            ? "text-ui-sm font-semibold text-[#177a44]"
            : props.branch === "timeout"
              ? "text-ui-sm font-semibold text-[#8a6d1d]"
              : "text-ui-sm font-semibold text-[#b23c36]"
        }
      >
        {copy.title}
      </div>
      <div className="mt-1 text-ui-caption text-foreground-subtle">{copy.detail}</div>
    </div>
  );
}

// ── 用量提示条（不静默降级：用量上限=专属条+管理用量外链；其余=具名回落条）──
export function UsageHintBar(props: { receipt: ChatReceipt | null }) {
  const hint = usageHintOf(props.receipt);
  if (!hint.show) return null;
  if (hint.kind === "usage_limit") {
    return (
      <div
        data-testid="subscription-usage-bar"
        data-kind="usage_limit"
        className="flex items-center gap-2 rounded-lg border border-[#c9971d55] bg-[#c9971d1a] px-3 py-2 text-ui-sm"
      >
        <span className="text-foreground">订阅用量已达上限：本轮已自动回落 API Key，对话未中断。</span>
        <a
          data-testid="subscription-usage-manage"
          href={USAGE_MANAGE_URL}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-[#8a6d1d] underline"
        >
          管理用量
        </a>
      </div>
    );
  }
  return (
    <div
      data-testid="subscription-usage-bar"
      data-kind="fallback"
      className="flex items-center gap-2 rounded-lg border border-border/60 bg-foreground/5 px-3 py-2 text-ui-sm"
    >
      <span className="text-foreground">
        已回落 API Key（{fallbackReasonCopy(hint.reasonCode)}）。订阅恢复后不自动切回：如需回到订阅来源，请在此手动选择。
      </span>
    </div>
  );
}

// ── 对话框模型 pill（对拍 10：live 菜单优先/无 live 菜单具名回落；手选粘性+钉住圆点；
// 每面板独立=实例自治状态，父层按面板各持一份）──
export function ModelPill(props: {
  models: readonly string[];
  model: string;
  source: "manual" | "default";
  provider: string;
  surface?: "primary" | "tile";
  hasRuntime?: boolean;
  liveMenu?: boolean;          // 引擎模型列表在位=live 菜单；缺=具名回落
  fallbackHint?: string | null; // 无 live 菜单时的具名原因（未登录/不可用）
  onSelect: (model: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const pinned = modelPinnedDotOf({
    surface: props.surface ?? "primary",
    hasRuntime: props.hasRuntime ?? false,
    source: props.source,
    model: props.model,
  });
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        data-testid="subscription-model-pill"
        data-source={props.source}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-ui-sm text-foreground-subtle hover:bg-foreground/5"
      >
        <span data-testid="subscription-model-pill-label" className="max-w-40 truncate">
          {props.model || "选择模型"}
        </span>
        {pinned ? (
          <span
            data-testid="subscription-model-pinned-dot"
            role="img"
            aria-label="已手动选定模型：新建对话将沿用"
            className="size-1 shrink-0 rounded-full bg-[#1d7fd0]"
          />
        ) : null}
      </button>
      {open ? (
        props.liveMenu && props.models.length > 0 ? (
          <ul
            data-testid="subscription-model-menu"
            role="listbox"
            className="absolute bottom-full z-10 mb-1 max-h-56 w-56 overflow-auto rounded-md border border-border bg-header py-1 shadow-md"
          >
            {props.models.map((m) => (
              <li key={m}>
                <button
                  type="button"
                  role="option"
                  aria-selected={m === props.model}
                  data-testid={`subscription-model-item-${m}`}
                  onClick={() => {
                    props.onSelect(m);
                    setOpen(false);
                  }}
                  className={`block w-full px-3 py-1.5 text-left text-ui-sm hover:bg-foreground/5 ${m === props.model ? "font-medium text-foreground" : "text-foreground-subtle"}`}
                >
                  {m}
                  {m === props.model ? "（当前）" : ""}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          // 无 live 菜单（引擎未登录/不可用）→ 具名回落占位，不伪造目录（fail-closed）
          <div
            data-testid="subscription-model-menu-fallback"
            className="absolute bottom-full z-10 mb-1 w-56 rounded-md border border-border bg-header p-3 text-ui-caption text-foreground-subtle shadow-md"
          >
            {props.fallbackHint ?? "订阅引擎暂不可用，无可选模型。"}
          </div>
        )
      ) : null}
    </span>
  );
}

// ── 推理强度 pill（对拍 11：supportsReasoning===false 或无菜单内容 → 整 pill 隐藏；
// 会话未上报档位 → pending 等待态，不拿默认值冒充；亲告 wire≠picked → 「Ultra→Max」双端）──
export function ReasoningPill(props: {
  supportsReasoning?: boolean | null;
  picked: string;
  wire?: string | null; // 会话亲告下发档；null=未上报
  onSelect: (level: ReasoningLevel) => void;
}) {
  const [open, setOpen] = useState(false);
  if (!reasoningPillVisibleOf({ supportsReasoning: props.supportsReasoning, hasMenuContent: true })) {
    return null;
  }
  const pending = reasoningPendingOf(props.picked);
  const label = reasoningPillLabelOf(props.picked, props.wire);
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        data-testid="subscription-reasoning-pill"
        data-pending={pending ? "true" : "false"}
        data-clamped={reasoningPillLabelOf(props.picked, props.wire).includes("→") ? "true" : "false"}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-ui-sm text-foreground-subtle hover:bg-foreground/5"
      >
        {pending ? (
          <span
            data-testid="subscription-reasoning-pending"
            aria-label="推理档位待会话上报"
            className="inline-block size-3 animate-spin rounded-full border border-current border-t-transparent"
          />
        ) : (
          <span data-testid="subscription-reasoning-label">{label}</span>
        )}
      </button>
      {open ? (
        <ul
          data-testid="subscription-reasoning-menu"
          role="listbox"
          className="absolute bottom-full z-10 mb-1 max-h-56 w-40 overflow-auto rounded-md border border-border bg-header py-1 shadow-md"
        >
          {reasoningMenuLevels().map((lv) => (
            <li key={lv.value}>
              <button
                type="button"
                role="option"
                aria-selected={lv.value === props.picked}
                data-testid={`subscription-reasoning-item-${lv.value}`}
                onClick={() => {
                  props.onSelect(lv.value);
                  setOpen(false);
                }}
                className={`block w-full px-3 py-1.5 text-left text-ui-sm hover:bg-foreground/5 ${lv.value === props.picked ? "font-medium text-foreground" : "text-foreground-subtle"}`}
              >
                {lv.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </span>
  );
}

// ── 主面板：来源卡片+登录动线+模型列表+pills+对话试驾（消费挂点）──
export function SubscriptionPanel() {
  const [status, setStatus] = useState<SubscriptionStatus | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  // pills 面板级状态（每面板独立：本组件实例=一个面板；瓦片/并排面板各挂各的实例）
  const [model, setModel] = useState("");
  const [modelSource, setModelSource] = useState<"manual" | "default">("default");
  const [pickedLevel, setPickedLevel] = useState<string | null>(null); // null=会话未上报 → pending
  const [wireLevel, setWireLevel] = useState<string | null>(null); // 亲告下发档挂点（回执带出，零推断）
  const [probeInput, setProbeInput] = useState("");
  const [receipt, setReceipt] = useState<ChatReceipt | null>(null);
  const [probeBusy, setProbeBusy] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const s = await api<SubscriptionStatus>("status");
      setStatus(s);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  // 引擎列表到达时按粘性合同对齐当前模型（手选钉住不回默认；默认=首项）
  useEffect(() => {
    const models = status?.accounts.find((a) => !a.needsLogin)?.models ?? [];
    setModel((prev) => stickyModelSelection({ model: prev, source: modelSource }, models));
  }, [status, modelSource]);

  const active = useMemo(
    () => status?.accounts.find((a) => a.sub === status?.activeSub) ?? null,
    [status],
  );

  const beginLogin = useCallback(async () => {
    setFlash(null);
    try {
      const out = await api<{ authorizationUrl: string }>("login_begin", { method: "POST" });
      window.open(out.authorizationUrl, "_blank", "noopener");
      setFlash("已在浏览器打开授权页：完成授权后回到此处点「刷新」查看结果（回调分支页显示在浏览器窗口）。");
    } catch (e) {
      setFlash("发起登录失败：" + (e instanceof Error ? e.message : String(e)));
    }
  }, []);

  const testConnection = useCallback(async () => {
    setFlash(null);
    try {
      const out = await api<{ models: string[]; cached: boolean }>("models?refresh=1");
      setFlash(`测试连接通过：引擎模型列表可拉取（${out.models.length} 个模型，缓存已刷新）。`);
      void refresh();
    } catch (e) {
      setFlash("测试连接未通过：" + (e instanceof Error ? e.message : String(e)));
    }
  }, [refresh]);

  const logout = useCallback(async () => {
    if (!status?.activeSub) return;
    setFlash(null);
    try {
      const out = await api<{ revoked: boolean; attempts: number }>("logout", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sub: status.activeSub }),
      });
      setFlash(`已退出并撤销授权（撤销请求 ${out.attempts} 次尝试，服务器确认=${out.revoked ? "是" : "否——凭证已清，账号标记需重登"}）。`);
      setModel("");
      setModelSource("default");
      setPickedLevel(null);
      setWireLevel(null);
      void refresh();
    } catch (e) {
      setFlash("退出失败：" + (e instanceof Error ? e.message : String(e)));
    }
  }, [status, refresh]);

  const selectModel = useCallback((m: string) => {
    // 整组一帧提交（对拍 12：session.model=整组选择）；scope 守卫演示面=本组件恒 session。
    rejectNonSessionScope("session");
    const commit = modelCommitOf({ model: m, provider: "chatgpt-sub", reasoning: pickedLevel });
    setModel(commit.model);
    setModelSource("manual"); // 手选钉住（粘性：新建对话沿用）
  }, [pickedLevel]);

  const selectLevel = useCallback((lv: ReasoningLevel) => {
    // 会话级 reasoning 单键提交（对拍 12）
    rejectNonSessionScope("session");
    const commit = reasoningCommitOf(lv);
    setPickedLevel(commit.value);
  }, []);

  const sendProbe = useCallback(async () => {
    if (!probeInput.trim() || probeBusy) return;
    setProbeBusy(true);
    setReceipt(null);
    try {
      const out = await api<ChatReceipt>("chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          input: probeInput,
          ...(model ? { model } : {}),
          ...(pickedLevel && pickedLevel !== "none" ? { reasoning: pickedLevel } : {}),
        }),
      });
      setReceipt(out);
      if (out.reasoningEffortWire) setWireLevel(out.reasoningEffortWire); // 亲告才采纳，零推断
    } catch (e) {
      // 引擎具名拒（未配回落且订阅不可用等）原样上浮，不伪答不伪造回执
      setFlash("对话轮未完成：" + (e instanceof Error ? e.message : String(e)));
    } finally {
      setProbeBusy(false);
    }
  }, [probeInput, probeBusy, model, pickedLevel]);

  return (
    <div className="space-y-4" data-testid="subscription-panel">
      {/* 来源卡片（RE-43 §3.5：登录/账号信息/模型列表/用量入口/退出撤销/测试连接） */}
      <div className="rounded-lg border border-border/60 p-3" data-testid="subscription-source-card">
        <div className="flex items-center gap-2">
          <span aria-hidden className="text-ui-sm">🔑</span>
          <span className="text-ui-sm font-medium text-foreground">订阅引擎（OpenAI 订阅族 · SIWC）</span>
          <span
            data-testid="subscription-engine-badge"
            data-state={status ? (status.available ? "available" : "unavailable") : "unknown"}
            className={`ml-auto inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${
              status?.available
                ? "bg-[#1d9e571a] text-[#177a44]"
                : "bg-[#787f8a1a] text-[#6d737c]"
            }`}
          >
            {status ? (status.available ? "订阅可用" : "订阅不可用") : "状态未知"}
          </span>
        </div>
        {!status?.available && status ? (
          <p className="mt-1 text-ui-caption text-foreground-subtle" data-testid="subscription-unavailable-reason">
            具名原因：{fallbackReasonCopy(status.unavailableReason)}（{status.unavailableReason}）
          </p>
        ) : null}
        {loadError ? (
          <p className="mt-1 text-ui-caption text-[#b23c36]">桥连接失败：{loadError}（请确认桥在本机运行）</p>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            data-testid="subscription-login"
            onClick={() => void beginLogin()}
            className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-ui-sm text-foreground hover:bg-foreground/5"
          >
            ⚡ {status?.accounts.length ? "重新登录" : "登录"}
          </button>
          <button
            type="button"
            data-testid="subscription-test-connection"
            onClick={() => void testConnection()}
            className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-ui-sm text-foreground hover:bg-foreground/5"
          >
            ⟳ 测试连接
          </button>
          <button
            type="button"
            data-testid="subscription-logout"
            disabled={!status?.activeSub}
            onClick={() => void logout()}
            className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-ui-sm text-foreground hover:bg-foreground/5 disabled:opacity-50"
          >
            ⎋ 退出并撤销授权
          </button>
          <button
            type="button"
            data-testid="subscription-refresh"
            onClick={() => void refresh()}
            className="ml-auto rounded-md border border-border/60 px-2 py-1 text-ui-sm text-foreground-subtle hover:bg-foreground/5"
          >
            {loading ? "读取中…" : "刷新"}
          </button>
        </div>

        {/* 账号信息（引擎投影：email/套餐用量位/需重登标记；hostId 不上屏=机器标识非账号信息） */}
        <ul className="mt-3 space-y-1" data-testid="subscription-accounts">
          {(status?.accounts ?? []).map((a) => (
            <li key={a.sub} className="text-ui-sm text-foreground-subtle">
              {a.email ?? "（邮箱未提供）"} ·
              {a.needsLogin ? " 需重新登录" : " 已登录"} ·
              套餐用量{a.planUsage ? "已开通" : "未开通"}
              {a.sub === status?.activeSub ? " · 当前账号" : ""}
            </li>
          ))}
          {!status?.accounts.length ? (
            <li className="text-ui-caption text-foreground-subtle">尚未登录订阅账号（登录后模型列表与对话轮在此出现）。</li>
          ) : null}
        </ul>

        {/* 模型列表（引擎 #11：可见性过滤后默认模型=首项） */}
        {active?.models.length ? (
          <div className="mt-2 text-ui-caption text-foreground-subtle" data-testid="subscription-models-list">
            模型 {active.models.length} 个 · 默认 {active.defaultModel ?? "—"}（首项）
          </div>
        ) : null}
        {flash ? (
          <p className="mt-2 text-ui-caption text-foreground-subtle" data-testid="subscription-flash">{flash}</p>
        ) : null}
      </div>

      {/* 对话框 pills（对拍 10-12 消费面；每面板独立=本实例自治） */}
      <div className="rounded-lg border border-border/60 p-3" data-testid="subscription-pills">
        <div className="text-ui-sm font-medium text-foreground">对话来源与推理档位</div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <ModelPill
            models={active?.models ?? []}
            model={model}
            source={modelSource}
            provider="chatgpt-sub"
            surface="primary"
            hasRuntime={false}
            liveMenu={Boolean(active?.models.length)}
            fallbackHint={
              status?.available
                ? "账号已登录但模型列表为空：点「测试连接」强刷列表。"
                : "订阅引擎未登录或不可用：先在上方登录，或改用 API Key 来源。"
            }
            onSelect={selectModel}
          />
          <ReasoningPill
            supportsReasoning={null} // 引擎模型列表未携推理声明：只认显式 false，unknown 不隐藏（合同原文）
            picked={pickedLevel ?? ""}
            wire={wireLevel}
            onSelect={selectLevel}
          />
          <span className="text-ui-caption text-foreground-subtle">
            手选模型新建对话沿用（钉住圆点提示）；推理档以会话上报为准（未上报前显示等待态）。
          </span>
        </div>
      </div>

      {/* 对话试驾（chat 面消费挂点：回执点亮用量/回落提示条；未配回落且订阅不可用=引擎具名拒不伪答） */}
      <div className="rounded-lg border border-border/60 p-3" data-testid="subscription-probe">
        <div className="text-ui-sm font-medium text-foreground">对话轮试驾</div>
        <div className="mt-2 flex items-center gap-2">
          <input
            data-testid="subscription-probe-input"
            value={probeInput}
            onChange={(e) => setProbeInput(e.target.value)}
            placeholder="输入一句合成试驾内容（走订阅引擎；不可用时按回落语义具名）"
            className="min-w-0 flex-1 rounded-md border border-border/60 bg-transparent px-2 py-1 text-ui-sm text-foreground"
          />
          <button
            type="button"
            data-testid="subscription-probe-send"
            disabled={probeBusy || !probeInput.trim()}
            onClick={() => void sendProbe()}
            className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2 py-1 text-ui-sm text-foreground hover:bg-foreground/5 disabled:opacity-50"
          >
            ➤ {probeBusy ? "发送中…" : "发送"}
          </button>
        </div>
        {receipt ? (
          <div className="mt-2 space-y-2">
            <UsageHintBar receipt={receipt} />
            <p className="text-ui-caption text-foreground-subtle" data-testid="subscription-probe-receipt">
              来源 {receipt.backend ?? "—"}
              {receipt.requestId ? ` · 请求 ID ${receipt.requestId}` : ""}
              {receipt.fallbackReason ? ` · 回落原因 ${receipt.fallbackReason}` : ""}
            </p>
            {receipt.replyText ? (
              <p className="whitespace-pre-wrap text-ui-sm text-foreground" data-testid="subscription-probe-reply">{receipt.replyText}</p>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
