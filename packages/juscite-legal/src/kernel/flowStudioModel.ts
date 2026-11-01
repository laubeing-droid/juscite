// 【功能 #35 尾巴②】Flow Studio/运行看板面板投影（RE-35 §2 D/E/G 面的 UI 消费纯函数）。
// 只做投影与文案映射，零 React 零 DOM；状态闭集 fail-closed（未知态灰态具名，不猜不隐藏）。
// 文案全部自写（表达隔离）。

export const FLOW_RUN_STATES = ["QUEUED", "RUNNING", "WAITING", "SUSPENDED", "SUCCEEDED", "FAILED", "CANCELLED"] as const;
export type FlowRunStatus = (typeof FLOW_RUN_STATES)[number];

export type BadgeTone = "ok" | "warn" | "err" | "info" | "idle";
export interface BadgeView { label: string; tone: BadgeTone; unknown?: boolean }

export const FLOW_RUN_STATUS_BADGE: Record<FlowRunStatus, BadgeView> = {
  QUEUED: { label: "排队中", tone: "idle" },
  RUNNING: { label: "运行中", tone: "info" },
  WAITING: { label: "待审（关卡）", tone: "warn" },
  SUSPENDED: { label: "已挂起", tone: "idle" },
  SUCCEEDED: { label: "已完成", tone: "ok" },
  FAILED: { label: "失败", tone: "err" },
  CANCELLED: { label: "已取消", tone: "idle" },
};

/** 未知态=灰态具名标注（fail-closed：不把没见过的状态渲染成已知态）。 */
export function runBadgeOf(status: string): BadgeView {
  const b = (FLOW_RUN_STATES as readonly string[]).includes(status)
    ? FLOW_RUN_STATUS_BADGE[status as FlowRunStatus]
    : undefined;
  return b ?? { label: `未知态（${status}）`, tone: "idle", unknown: true };
}

export const FLOW_DEF_SOURCES = ["local", "builtin"] as const;
export type FlowDefSource = (typeof FLOW_DEF_SOURCES)[number];
export const FLOW_DEF_STATUS_BADGE: Record<string, BadgeView> = {
  draft: { label: "草稿", tone: "idle" },
  published: { label: "已发布", tone: "ok" },
  builtin: { label: "内置（只读）", tone: "info" },
};

export function defBadgeOf(source: string, status: string): BadgeView {
  if (!(FLOW_DEF_SOURCES as readonly string[]).includes(source))
    return { label: `未知来源（${source}/${status}）`, tone: "idle", unknown: true };
  const key = source === "builtin" ? "builtin" : status;
  return FLOW_DEF_STATUS_BADGE[key] ?? { label: `未知状态（${source}/${status}）`, tone: "idle", unknown: true };
}

/** 内置流程恒只读（双来源 E2：编辑请另存草稿）。 */
export function defReadonlyOf(source: string): boolean {
  return source === "builtin";
}

export function eventLevelBadge(level: string): BadgeView {
  if (level === "error") return { label: "错误", tone: "err" };
  if (level === "warn") return { label: "警告", tone: "warn" };
  if (level === "info" || !level) return { label: "信息", tone: "idle" };
  return { label: `未知级（${level}）`, tone: "idle", unknown: true };
}

export interface RunFaceLike {
  run?: {
    status?: string; errorCode?: { code?: string } | null; error?: { code?: string; message?: string } | null;
    dryRun?: boolean; waiting?: { kind?: string; nodeId?: string; gateNodeId?: string } | null;
  } | null;
  events?: Array<{ kind?: string; level?: string }> | null;
  aiRuns?: unknown[] | null;
  artifacts?: Array<{ payloadDigest?: string }> | null;
  chain?: { verified?: boolean; reason?: string } | null;
}

export interface RunFaceSummary {
  status: BadgeView;
  chainOk: boolean;
  chainNote: string;
  heartbeats: number;
  aiRunCount: number;
  artifactCount: number;
  errorCode: string | null;
  waitingGate: boolean;
  gateNodeId: string | null;
  dryRun: boolean;
}

export function summarizeRunFace(face: RunFaceLike): RunFaceSummary {
  const events = face.events ?? [];
  const waiting = face.run?.waiting ?? null;
  const errCode = face.run?.error?.code ?? face.run?.errorCode?.code ?? null;
  return {
    status: runBadgeOf(face.run?.status ?? ""),
    chainOk: face.chain?.verified === true,
    chainNote: face.chain?.verified === true ? "事件链校验通过" : `事件链未通过：${face.chain?.reason ?? "未校验"}`,
    heartbeats: events.filter((e) => e.kind === "heartbeat").length,
    aiRunCount: face.aiRuns?.length ?? 0,
    artifactCount: face.artifacts?.length ?? 0,
    errorCode: errCode,
    waitingGate: waiting?.kind === "gate",
    gateNodeId: waiting?.gateNodeId ?? null,
    dryRun: face.run?.dryRun === true,
  };
}

/**
 * 关卡乐观锁冲突回显（律见 R2 口径）：错误文本里的「当前 vN」解析出服务端当前版本，
 * 供面板回显提示人工刷新后重下决定——绝不自动重放旧决定。
 */
export function conflictCurrentVersionOf(errText: string): number | null {
  const m = /当前 v(\d+)/.exec(errText ?? "");
  return m ? Number(m[1]) : null;
}

export interface AiRunRowLike {
  modelCode?: string | null; promptVersion?: string | null;
  riskLevel?: string | null; riskScore?: number | null; findingsCount?: number | null;
  findings?: Array<{ clause?: string | null; level?: string | null; description?: string | null; advice?: string | null }> | null;
}

export interface AiRunRowView {
  modelPinned: string; // G1 钉定：模型+提示词版本
  riskLine: string; // G2 三件套（严格数值才收，未上报=如实标注）
  findingsCount: number;
  findingsQuad: Array<{ clause: string; level: string; description: string; advice: string }>; // G3 四元组（缺项如实空串）
}

export function aiRunRowView(row: AiRunRowLike): AiRunRowView {
  const findings = Array.isArray(row.findings) ? row.findings : [];
  return {
    modelPinned: `${row.modelCode ?? "unknown"} · 提示词 ${row.promptVersion ?? "unknown"}`,
    riskLine: `级别 ${row.riskLevel ?? "未上报"} / 分值 ${
      typeof row.riskScore === "number" ? String(row.riskScore) : "未上报（非严格数值不收）"
    } / 发现 ${typeof row.findingsCount === "number" ? String(row.findingsCount) : findings.length} 条`,
    findingsCount: typeof row.findingsCount === "number" ? row.findingsCount : findings.length,
    findingsQuad: findings.map((f) => ({
      clause: f?.clause ?? "", level: f?.level ?? "", description: f?.description ?? "", advice: f?.advice ?? "",
    })),
  };
}

export interface FlowDefLike {
  nodes?: Array<{ type?: string }> | null;
  groups?: Array<{ nodeIds?: string[] }> | null;
}

export interface DefCensus {
  byType: Array<{ type: string; count: number }>;
  total: number;
  groupsNote: string; // B9：分组仅展示，执行序只由依赖决定
}

export function defNodeCensus(def: FlowDefLike): DefCensus {
  const nodes = def.nodes ?? [];
  const counts = new Map<string, number>();
  for (const n of nodes) {
    const t = typeof n?.type === "string" && n.type ? n.type : "未知型";
    counts.set(t, (counts.get(t) ?? 0) + 1);
  }
  return {
    byType: [...counts.entries()].map(([type, count]) => ({ type, count })).sort((a, b) => b.count - a.count),
    total: nodes.length,
    groupsNote: (def.groups?.length ?? 0) > 0
      ? `${def.groups!.length} 个分组（仅界面展示，不参与执行顺序）`
      : "无分组（分组仅界面展示，不参与执行顺序）",
  };
}

/** 草稿不可直接发起（须试跑语义或先发布）——面板按钮态据此切换。 */
export function canStartDefinition(source: string, status: string): { start: boolean; testRunOnly: boolean; note: string } {
  if (defReadonlyOf(source)) return { start: true, testRunOnly: false, note: "内置流程只读，可直接发起" };
  if (status === "published") return { start: true, testRunOnly: false, note: "已发布定义可直接发起" };
  return { start: true, testRunOnly: true, note: "草稿定义只可试跑（testRun），发布后才可正式发起" };
}
