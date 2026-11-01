// 【功能 #32 整理与尽调】任务看板内核（RE-32 §2 行为 1-5 / §3 任务模型；tasks.txt 对齐面）。
// 看板三分组（计划与清单／资料收集与台账／专项核查）由任务模板驱动；任务→子任务两级可编辑；
// 状态机含确认门（需律师确认的结果保留「待确认」，确认后才可置「已完成」）；
// 任务可绑定法律尽调 Flow（契约-only：引擎本体归 RE-35，本件只存绑定关系，不调引擎）；
// 成果按版本保存、点版本号切换查看（版本不可变，只追加）。
// 纯函数、零 IO；文案全部自写（不袭对齐物文档措辞）。

export const BOARD_GROUPS = ["计划与清单", "资料收集与台账", "专项核查"] as const;
export type BoardGroup = (typeof BOARD_GROUPS)[number];

export type TaskStatus = "pending" | "in_progress" | "pending_confirmation" | "done";

export const TASK_STATUSES: readonly TaskStatus[] = ["pending", "in_progress", "pending_confirmation", "done"];

/** 状态机迁移表（确认门：done 只能从 pending_confirmation 经 confirmTask 进入） */
const TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  pending: ["in_progress"],
  in_progress: ["pending_confirmation", "pending"],
  pending_confirmation: ["in_progress"], // done 不走通用迁移，只能走 confirmTask（带确认人）
  done: [], // 终态：不改回（重开=另立任务，历史版本全保）
};

export interface Subtask {
  subId: string;
  title: string;
  done: boolean;
}

/** Flow 绑定契约（引擎与 DSL 归 RE-35；此处只验形状存关系） */
export interface FlowRef {
  flowId: string;
  flowName?: string;
}

export const FLOW_SCOPE_NOTE = "流程引擎本体归 RE-35：本任务只保存绑定契约（flowId/名称），执行与产物由流程侧另行承载。";

export interface BoardTask {
  taskId: string;
  caseId: string;
  group: BoardGroup;
  title: string;
  status: TaskStatus;
  subtasks: Subtask[];
  flowRef: FlowRef | null;
  confirmedBy: string | null;
  confirmedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface TaskResultVersion {
  version: number;
  content: string;
  savedBy: string;
  savedAt: string;
}

// ── 行为 1/3：任务模板（尽调流程预设三分组；文案自写）──
export interface TaskTemplateItem {
  title: string;
  subtasks?: string[];
}

export const BOARD_PRESET: Record<BoardGroup, TaskTemplateItem[]> = {
  计划与清单: [
    { title: "明确尽调目的、范围与核查重点", subtasks: ["梳理委托方关注事项", "圈定核查范围与时间窗"] },
    { title: "编制尽调资料清单并向目标公司发出", subtasks: ["按清单体系列明待收材料", "登记发出与催收进度"] },
    { title: "约定材料交接与保密安排" },
  ],
  资料收集与台账: [
    { title: "接收、登记并分类归档底稿材料", subtasks: ["按清单类目归档", "生成重命名与索引方案"] },
    { title: "建立尽调资料台账", subtasks: ["配置台账字段模板", "批量提取底稿关键字段", "逐项核对台账与原文"] },
    { title: "跟进缺失材料的补充与替换" },
  ],
  专项核查: [
    {
      title: "主体资格与工商沿革核查",
      subtasks: ["设立与工商沿革梳理", "实缴出资情况核查", "历史关联主体排查", "工商公示信息与年报外部核对"],
    },
    { title: "历史沿革核查", subtasks: ["汇集章程/股转/验资/任免材料", "按时间轴整理沿革章节", "同步产出风险评估与待核查清单"] },
    { title: "重大合同与债权债务核查" },
    { title: "涉诉、行政处罚与合规核查" },
  ],
};

export function isBoardGroup(g: string): g is BoardGroup {
  return (BOARD_GROUPS as readonly string[]).includes(g);
}

// ── 行为 2：状态机与确认门 ──
export function transitionTask(task: BoardTask, to: TaskStatus, at: string): BoardTask {
  if (!TASK_STATUSES.includes(to)) throw new Error(`未知任务状态：${to}`);
  if (to === "done") throw new Error("完成任务须经确认门：先转「待确认」，由确认人执行确认后置已完成");
  if (task.status === "done") throw new Error("任务已完成，状态不再变更（如需重做请另立任务）");
  if (!(TRANSITIONS[task.status] ?? []).includes(to)) throw new Error(`非法状态迁移：${task.status} → ${to}`);
  return { ...task, status: to, updatedAt: at };
}

/** 确认门动作：pending_confirmation → done，确认人必填（行为 2「确认后才点完成任务」） */
export function confirmTask(task: BoardTask, by: string, at: string): BoardTask {
  const who = String(by ?? "").trim();
  if (!who) throw new Error("确认人不能为空：完成任务须留律师确认记录");
  if (task.status !== "pending_confirmation") throw new Error(`仅「待确认」状态可执行确认（当前：${task.status}）`);
  return { ...task, status: "done", confirmedBy: who, confirmedAt: at, updatedAt: at };
}

// ── 行为 3：子任务两级可编辑（按项目情况添加/调整）──
export function addSubtask(task: BoardTask, subId: string, title: string): BoardTask {
  const sid = String(subId ?? "").trim();
  if (!sid) throw new Error("子任务标识不能为空");
  const t = String(title ?? "").trim();
  if (!t) throw new Error("子任务标题不能为空");
  if (t.length > 80) throw new Error("子任务标题超过 80 字");
  if (task.subtasks.some((s) => s.subId === sid)) throw new Error(`子任务标识重复：${sid}`);
  if (task.subtasks.some((s) => s.title === t)) throw new Error(`子任务已存在：${t}`);
  return { ...task, subtasks: [...task.subtasks, { subId: sid, title: t, done: false }], updatedAt: task.updatedAt };
}

export function removeSubtask(task: BoardTask, subId: string): BoardTask {
  if (!task.subtasks.some((s) => s.subId === subId)) throw new Error(`子任务不存在：${subId}`);
  return { ...task, subtasks: task.subtasks.filter((s) => s.subId !== subId) };
}

export function retitleSubtask(task: BoardTask, subId: string, title: string): BoardTask {
  const t = String(title ?? "").trim();
  if (!t) throw new Error("子任务标题不能为空");
  const hit = task.subtasks.find((s) => s.subId === subId);
  if (!hit) throw new Error(`子任务不存在：${subId}`);
  return { ...task, subtasks: task.subtasks.map((s) => (s.subId === subId ? { ...s, title: t } : s)) };
}

/** 子任务逐项推进（勾完成/取消勾） */
export function markSubtask(task: BoardTask, subId: string, done: boolean): BoardTask {
  const hit = task.subtasks.find((s) => s.subId === subId);
  if (!hit) throw new Error(`子任务不存在：${subId}`);
  return { ...task, subtasks: task.subtasks.map((s) => (s.subId === subId ? { ...s, done: Boolean(done) } : s)) };
}

// ── 行为 4：任务绑定尽调 Flow（契约-only）──
export function bindFlow(task: BoardTask, ref: FlowRef | null): BoardTask {
  if (ref === null || ref === undefined) return { ...task, flowRef: null };
  const flowId = String((ref as FlowRef).flowId ?? "").trim();
  if (!flowId) throw new Error("flowId 不能为空");
  if (flowId.length > 80) throw new Error("flowId 超过 80 字符");
  const flowName = ref.flowName === undefined ? undefined : String(ref.flowName).slice(0, 120);
  return { ...task, flowRef: flowName === undefined ? { flowId } : { flowId, flowName } };
}

// ── 行为 1：看板投影（三分组）──
export interface BoardProjection {
  groups: Array<{ group: BoardGroup; tasks: BoardTask[] }>;
  counts: Record<string, number>;
}

export function boardProjection(tasks: BoardTask[]): BoardProjection {
  const groups = BOARD_GROUPS.map((group) => ({ group, tasks: tasks.filter((t) => t.group === group) }));
  const counts: Record<string, number> = {};
  for (const g of groups) counts[g.group] = g.tasks.length;
  return { groups, counts };
}

// ── 行为 5：成果版本（只追加不可变；点版本号切换查看）──
export function saveTaskResult(versions: TaskResultVersion[], content: string, by: string, at: string): TaskResultVersion {
  const body = String(content ?? "");
  if (!body.trim()) throw new Error("成果内容不能为空");
  const who = String(by ?? "").trim();
  if (!who) throw new Error("保存人不能为空");
  const version = versions.reduce((m, v) => Math.max(m, v.version), 0) + 1;
  return { version, content: body, savedBy: who, savedAt: at };
}

export function getTaskResult(versions: TaskResultVersion[], version: number): TaskResultVersion {
  const hit = versions.find((v) => v.version === version);
  if (!hit) throw new Error(`版本不存在：v${version}`);
  return hit;
}
