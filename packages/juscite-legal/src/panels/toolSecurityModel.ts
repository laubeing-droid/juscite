// 【#21 安全层】工具安全设置面板＋审计中心「工具决策」tab 纯模型
// （RE-21 增补 §3.1「三档模式进设置」/§2.6 判序/§3.3 审计行；与 RE-30 面板纯模型
// securityAuditModel 同构：确定性函数+查表，禁模型猜；文案全部自写）。
// 依据（ ask 2026-10-30）：设置面板=toolSecurity.shellEnabled 开关（默认关维持，
// 2026-10-30 主控裁定）+Allow/Ask/Deny 策略展示；**yolo 档不暴露只留设置键**（用户裁决）。
// 判序语义与桥侧 tools/bridge/tool_policy.mjs 一一对应（引证 tool_policy.mjs:80-176）；
// 审计行与 tools/bridge/tool_audit_service.mjs listToolAudits 返回形同构（十一字段 camel）。

import type { AuditRow, AuditTab } from "./securityAuditModel.js";

// auditRowsForTab 签名面暴露 AuditRow——类型随 API 一并出（审计中心行类型单一真源=securityAuditModel）
export type { AuditRow };

// ── 设置读取（设置文件为 Juscite additive 字段，运行时宽容、类型层断言桥接）──

export type ToolSecuritySettingRaw = {
  shellEnabled?: unknown;
  permissionMode?: unknown;
};

/** 读原始 toolSecurity 对象（非对象一律按空——写入端整对象写回防冲键，见 mergeToolSecurityPatch）。 */
export function readToolSecurityRaw(setting: unknown): ToolSecuritySettingRaw {
  const ts = (setting as { toolSecurity?: unknown } | null | undefined)?.toolSecurity;
  return ts && typeof ts === "object" && !Array.isArray(ts) ? (ts as ToolSecuritySettingRaw) : {};
}

/** shell 开关（默认关维持——2026-10-30 主控裁定）：非布尔真值一律按关（桥侧 bridge_host.mjs:3544 同款）。 */
export function readShellEnabled(setting: unknown): boolean {
  return readToolSecurityRaw(setting).shellEnabled === true;
}

/** 三档闭集与展示名（桥侧 tool_policy.mjs:22 PERMISSION_MODES 同闭集）。 */
export const MODE_LABELS = {
  always_ask: "逐条批",
  smart: "智能档（默认）",
  yolo: "全放行",
} as const;
export type PermissionMode = keyof typeof MODE_LABELS;
const MODES: ReadonlySet<string> = new Set(Object.keys(MODE_LABELS));

/** permissionMode 读取：不在三档闭集内一律按 smart（桥侧 toolSecuritySetting 同款宽容，bridge_host.mjs:3545）。 */
export function readPermissionMode(setting: unknown): PermissionMode {
  const m = readToolSecurityRaw(setting).permissionMode;
  return typeof m === "string" && MODES.has(m) ? (m as PermissionMode) : "smart";
}

/** 界面暴露的档位：只智能档——yolo 档不暴露只留设置键；逐条批档同样不走界面切换
 * （2026-10-30 用户裁决：yolo 档不暴露只留设置键；界面不给任何档位切换面）。 */
export const UI_EXPOSED_MODES: readonly PermissionMode[] = ["smart"];

export function isModeExposed(mode: PermissionMode): boolean {
  return UI_EXPOSED_MODES.includes(mode);
}

/** 档位展示行：默认档给行为说明；非暴露档如实注明「仅设置键 toolSecurity.permissionMode」。 */
export function modeDisplayLine(mode: PermissionMode): string {
  if (mode === "smart") return "智能档（默认）：只读查看直接放行，其余动作逐项把关。";
  if (mode === "always_ask") {
    return "逐条批档：每次工具调用都先确认（仅设置键 toolSecurity.permissionMode，界面不提供切换）。";
  }
  return "全放行档：除绝对拒绝外放行（仅设置键 toolSecurity.permissionMode；界面不提供，谨慎使用）。";
}

/**
 * 浅合并桥语义（tools/bridge/team_sync_model.mjs:240 mergeSettingKeepTeam 整段覆盖）下的
 * 安全写法：toolSecurity 整对象写回，防冲掉 permissionMode 等既有键。
 * 入参=已解包的 toolSecurity 对象（readToolSecurityRaw(s) 的产出），非整个 setting。
 */
export function mergeToolSecurityPatch(
  rawToolSecurity: unknown,
  patch: { shellEnabled?: boolean },
): Record<string, unknown> {
  const raw =
    rawToolSecurity && typeof rawToolSecurity === "object" && !Array.isArray(rawToolSecurity)
      ? (rawToolSecurity as Record<string, unknown>)
      : {};
  return patch.shellEnabled === undefined ? { ...raw } : { ...raw, shellEnabled: patch.shellEnabled };
}

// ── Allow/Ask/Deny 策略展示目录（判序语义与 tool_policy.mjs:89-175 一致；文案自写）──

export type PolicyTier = {
  effect: "allow" | "ask" | "deny";
  title: string;
  description: string;
  items: string[];
};

export const POLICY_TIERS: PolicyTier[] = [
  {
    effect: "deny",
    title: "一律拒绝",
    description: "不可逆或越界的动作：任何档位、任何技能声明都不放行。",
    items: [
      "删除类工具——删除不可逆，技能声明了也不行",
      "跨事项检索——目标不是当前会话事项即拒，当事人数据按事项隔离",
      "命令执行开关未打开时的 shell 类调用（默认关）",
      "技能清单未声明所需权限的调用——开一次功能不等于送给所有技能",
      "未启用的外部数据源",
    ],
  },
  {
    effect: "ask",
    title: "逐条确认",
    description: "会动到你的机器、或把内容带出本机的动作：每次都先问你。",
    items: [
      "命令执行——开关已开且技能已声明：命令在你的机器上全权运行，逐条确认，仍受宿主命令闸把关",
      "写入工作区文件——确认目标与内容",
      "外部数据源查询——检索词会发送给外部",
      "未分类的新工具——不因没人分类而自动放行",
    ],
  },
  {
    effect: "allow",
    title: "直接放行",
    description: "只读查看类：不改动文件、不向外出网。",
    items: ["只读工具白名单——案件、材料、法条、时间线等查看面（智能档直放）"],
  },
];

// ── 工具决策审计行（tool_audits 十一字段，桥侧 listToolAudits 同形 camelCase）──

export type ToolDecisionRow = {
  id: string;
  conversationId: string;
  runId: string | null;
  toolName: string;
  effect: string;
  code: string;
  reason: string;
  policyVersion: number;
  userDecision: string | null;
  argsSummary: string;
  createdAt: string;
};

/** 决定三态展示（绿/灰/红胶囊；与 RE-30 面板色板一致，文案自写）。 */
export const EFFECT_META: Record<string, { label: string; cls: string }> = {
  allow: { label: "放行", cls: "bg-[#1d9e571a] text-[#177a44]" },
  ask: { label: "待确认", cls: "bg-[#787f8a1a] text-[#6d737c]" },
  deny: { label: "已拒绝", cls: "bg-[#d0453e1a] text-[#b23c36]" },
};

export function effectMetaOf(effect: string): { label: string; cls: string } {
  return EFFECT_META[effect] ?? { label: effect || "未知", cls: "bg-foreground/8 text-foreground-subtle" };
}

/** 原因码闭集十个→短标（与桥 tool_policy.mjs:25-29 REASON_CODES 一一对应；未知码原样回显）。 */
export const REASON_CODE_LABELS: Record<string, string> = {
  destructive: "删除类拒绝",
  cross_matter: "跨事项拒绝",
  shell_disabled: "命令开关未开",
  permission_not_declared: "权限未声明",
  no_workspace: "无工作区",
  source_not_enabled: "数据源未启用",
  writes_files: "写文件确认",
  external_call: "出网确认",
  read_only: "只读放行",
  unknown_tool: "未分类工具",
};

export function reasonCodeLabel(code: string): string {
  return REASON_CODE_LABELS[code] ?? code;
}

/** 用户决定短标（allow/always/deny/NULL——tool_audits.user_decision 值域）。 */
export function userDecisionLabel(d: string | null | undefined): string {
  if (d === "always") return "总是允许";
  if (d === "allow") return "本次允许";
  if (d === "deny") return "拒绝";
  return "未询问";
}

/** 桥返回行 → 面板行守卫：非数组→[]；逐行兜底缺字段（决策行不因桥端形状漂移崩面板）。 */
export function toToolDecisionRows(value: unknown): ToolDecisionRow[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((r): r is Record<string, unknown> => Boolean(r && typeof r === "object"))
    .map((r) => ({
      id: String(r.id ?? ""),
      conversationId: String(r.conversationId ?? ""),
      runId: typeof r.runId === "string" && r.runId ? r.runId : null,
      toolName: String(r.toolName ?? ""),
      effect: String(r.effect ?? ""),
      code: String(r.code ?? ""),
      reason: String(r.reason ?? ""),
      policyVersion: typeof r.policyVersion === "number" && Number.isFinite(r.policyVersion) ? r.policyVersion : 0,
      userDecision:
        r.userDecision === "allow" || r.userDecision === "always" || r.userDecision === "deny"
          ? r.userDecision
          : null,
      argsSummary: String(r.argsSummary ?? ""),
      createdAt: String(r.createdAt ?? ""),
    }))
    .filter((r) => r.id !== "");
}

/** 详情有效行回退链（RE-30 §3.7 关键等量同款）：find ?? 首行 ?? null。 */
export function selectEffectiveToolDecision(
  filtered: ToolDecisionRow[],
  selectedId: string | null,
): ToolDecisionRow | null {
  return filtered.find((r) => r.id === selectedId) ?? filtered[0] ?? null;
}

// ── 审计中心 tab 面（RE-30 三 tab 语义不变；tools=工具决策专表独立视图）──

export type SecurityAuditTab = AuditTab | "tools";

/** 工具决策行只在 tools tab 出示（全部/出站脱敏/本地操作三 tab 维持 audit_log 语义）。 */
export function toolRowsForTab(tab: SecurityAuditTab, toolRows: ToolDecisionRow[]): ToolDecisionRow[] {
  return tab === "tools" ? toolRows : [];
}

/** audit_log 行在 tools tab 不出示（专表专视图，互不混排）。 */
export function auditRowsForTab(tab: SecurityAuditTab, rows: AuditRow[]): AuditRow[] {
  return tab === "tools" ? [] : rows;
}

/** 工具决策不可用提示（桥无本方法/查询失败——如实降级不伪装空账）。 */
export const TOOL_DECISIONS_UNAVAILABLE_TEXT = "工具决策查询不可用：桥暂未提供查询通道。";

/** 工具决策空账引导文案（tab 有数据通道、库里还没有行）。 */
export const TOOL_DECISIONS_EMPTY_TEXT =
  "还没有工具决策留痕。技能运行中的每次放行/确认/拒绝都会记入这里；被拒的调用也入账——事件复盘要看的正是它们。";
