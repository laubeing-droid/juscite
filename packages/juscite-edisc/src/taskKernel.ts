// 【功能 #42 电子数据取证】长任务生命周期内核（RE-42 §2.G G5，纯模型零 I/O）。
// 机制位=取证批量整理任务：后台启动即返检查点（逐件处理、每件落库后推进 checkpoint）、
// 暂停/取消、断点续传（resume 自检查点继续）、失败件恢复（recover-failed 把失败件重排回队）、
// 纯页卡档（pageCardsOnly：只产页卡/块锚，跳过对话段等行面结构化）。
// 状态迁移与推进规则收敛于此纯函数层（服务层只做持久化与逐件 I/O）；文案自写。
export const TASK_STATUSES = ["running", "paused", "done", "canceled"] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];
export type TaskItemState = "pending" | "ok" | "failed";
export const TASK_CONTROLS = ["pause", "resume", "cancel", "recover-failed"] as const;
export type TaskControl = (typeof TASK_CONTROLS)[number];

export interface TaskItem {
  sourceId: string;
  label: string;
  state: TaskItemState;
  attempts: number; // 处理尝试次数（失败恢复重跑会累加）
  error?: string;   // 最近一次失败的可读原因
}

export interface OrganizeTask {
  taskId: string;
  caseId: string;
  status: TaskStatus;
  items: TaskItem[];
  /** 检查点=已完成处理的件数（ok+failed；断点续传自此继续） */
  checkpoint: number;
  pageCardsOnly: boolean;
  stopOnError: boolean;
  createdAt: string;
  updatedAt: string;
}

/** 起任务：全部件 pending、检查点 0、状态 running（后台启动即返——服务层起完即回执）。 */
export function startOrganize(
  base: { taskId: string; caseId: string; createdAt: string },
  items: { sourceId: string; label: string }[],
  opts: { pageCardsOnly?: boolean; stopOnError?: boolean } = {},
): OrganizeTask {
  if (!Array.isArray(items) || items.length === 0) throw new Error("任务工作清单为空：没有可整理的待处理源");
  return {
    ...base,
    status: "running",
    items: items.map((i) => ({ sourceId: String(i.sourceId), label: String(i.label ?? i.sourceId), state: "pending" as const, attempts: 0 })),
    checkpoint: 0,
    pageCardsOnly: Boolean(opts.pageCardsOnly),
    stopOnError: Boolean(opts.stopOnError),
    createdAt: base.createdAt,
    updatedAt: base.createdAt,
  };
}

/** 下一待处理件下标；全部处理完返回 null（服务层据此落 done）。 */
export function nextPendingIndex(t: OrganizeTask): number | null {
  const idx = t.items.findIndex((i) => i.state === "pending");
  return idx === -1 ? null : idx;
}

/** 单件结果入账：推进检查点；stopOnError 出错即停（落 paused 等人工介入，断点保留）。 */
export function recordOutcome(t: OrganizeTask, sourceId: string, outcome: "ok" | "failed", error = "", now = ""): OrganizeTask {
  const idx = t.items.findIndex((i) => i.sourceId === sourceId && i.state === "pending");
  if (idx === -1) return t; // 非当前待处理件（并发/重复回执）：幂等忽略
  const items = t.items.map((i, k) => k === idx
    ? { ...i, state: outcome, attempts: i.attempts + 1, error: outcome === "failed" ? error : undefined }
    : i);
  const checkpoint = items.filter((i) => i.state !== "pending").length;
  const halt = outcome === "failed" && t.stopOnError && t.status === "running";
  return { ...t, items, checkpoint, status: halt ? "paused" : t.status, updatedAt: now || t.updatedAt };
}

/** 控制面：暂停/恢复/取消/失败件重跑。迁移合法才收；非法给可读错误（服务层转 409）。 */
export function applyControl(
  t: OrganizeTask,
  control: TaskControl,
  now = "",
): { ok: true; task: OrganizeTask } | { ok: false; error: string } {
  const stamp = now || t.updatedAt;
  if (control === "pause") {
    if (t.status !== "running") return { ok: false, error: `仅在运行中的任务可暂停（当前 ${t.status}）` };
    return { ok: true, task: { ...t, status: "paused", updatedAt: stamp } };
  }
  if (control === "resume") {
    if (t.status !== "paused") return { ok: false, error: `仅在已暂停的任务可恢复续传（当前 ${t.status}）` };
    const finished = nextPendingIndex({ ...t, status: "running" }) === null;
    return { ok: true, task: { ...t, status: finished ? "done" : "running", updatedAt: stamp } };
  }
  if (control === "cancel") {
    if (t.status !== "running" && t.status !== "paused") return { ok: false, error: `已结束的任务不可取消（当前 ${t.status}）` };
    return { ok: true, task: { ...t, status: "canceled", updatedAt: stamp } };
  }
  // recover-failed：失败件重排回队（attempts 保留，供重跑次数核对）
  const failed = t.items.filter((i) => i.state === "failed");
  if (!failed.length) return { ok: false, error: "没有失败件可恢复重跑" };
  if (t.status === "running") return { ok: false, error: "任务运行中不可恢复失败件（先暂停或等其结束）" };
  const items = t.items.map((i) => (i.state === "failed" ? { ...i, state: "pending" as const } : i));
  const checkpoint = items.filter((i) => i.state !== "pending").length;
  return { ok: true, task: { ...t, items, checkpoint, status: "running", updatedAt: stamp } };
}

/** 任务摘要（检查点/进度/失败数——启动即返的可回执形状）。 */
export function taskSummary(t: OrganizeTask): {
  status: TaskStatus; total: number; done: number; failed: number; pending: number;
  checkpoint: number; pageCardsOnly: boolean; stopOnError: boolean;
} {
  return {
    status: t.status,
    total: t.items.length,
    done: t.items.filter((i) => i.state === "ok").length,
    failed: t.items.filter((i) => i.state === "failed").length,
    pending: t.items.filter((i) => i.state === "pending").length,
    checkpoint: t.checkpoint,
    pageCardsOnly: t.pageCardsOnly,
    stopOnError: t.stopOnError,
  };
}
