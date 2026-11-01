// 功能 #28 桌宠 · 序列准入（RE-28 §3.1 协议 + §3.2 准入；行为等量 A13-A16，命名自有）。
// 串行准入：无在跑即接；有在跑时新优先级必须严格更高，≤=PET_BUSY；更高=先打断当前步
// （fire-and-forget）等旧序列收口（interrupted 结果回填）再开跑。任一步 failed→自动
// returnHome 等价步再返回失败（安全回家）。协议校验失败一律返回 VALIDATION_FAILED，不抛错。
// 本文件不 import electron：执行器（渲染窗口桥）注入，纯逻辑可合成自测。

import { randomUUID } from "node:crypto";
import { PET_ANIMATIONS, PET_MACRO_CATALOG, type PetAnimation, type PetPlayback } from "./motions.js";

// ── 协议类型 ─────────────────────────────────────────────────────────────

export const PET_REQUEST_ID_PATTERN = /^[A-Z0-9][\w-]{0,127}$/i;
export const PET_MAX_STEP_DURATION_MS = 60_000;
export const PET_MAX_STEPS = 16;
export const PET_PRIORITY_MIN = 0;
export const PET_PRIORITY_MAX = 100;
/** 单步守卫超时=步 timeoutMs+1000（A17 线协议语义的进程内等量）。 */
export const PET_STEP_GUARD_SLACK_MS = 1_000;
/** 安全回家步超时（returnHome 15s）。 */
export const PET_SAFE_HOME_TIMEOUT_MS = 15_000;

export type PetFailureCode =
  | "PET_BUSY"
  | "PET_PROTOCOL_ERROR"
  | "PET_STEP_FAILED"
  | "PET_UNAVAILABLE"
  | "VALIDATION_FAILED";

export type PetStepAction =
  | {
      kind: "playAction";
      animation: PetAnimation;
      playback: PetPlayback;
      /** playAction 必带 completionBehavior=restoreIdle（A13）。 */
      completionBehavior: "restoreIdle";
      timeoutMs: number;
    }
  | {
      kind: "moveByPath";
      /** 仅允许 [{kind:'home'}] 形态（A13）。 */
      path: Array<{ kind: "home" }>;
      timeoutMs: number;
    };

export interface PetSequenceParams {
  requestId: string;
  priority: number;
  steps: PetStepAction[];
}

export type PetSequenceResult =
  | { status: "completed"; completedSteps: number }
  | { status: "interrupted"; reasonCode: "admission.preemptedByHigherPriorityPlan"; completedSteps: number }
  | { status: "failed"; code: PetFailureCode; completedSteps: number };

export type PetStepOutcome =
  | { kind: "completed" }
  | { kind: "interrupted" }
  | { kind: "failed" }
  /** 渲染面不在（窗口销毁/代际切换）→ PET_UNAVAILABLE。 */
  | { kind: "unavailable" };

export interface PetStepExecutor {
  /** 播一步；Promise resolve=步收口。实现方自行按动画时长收口。 */
  runStep(step: PetStepAction, context: { requestId: string; stepId: string; index: number }): Promise<PetStepOutcome>;
  /** 打断当前步（渲染侧中断当前动画）；无在跑步为空操作。fire-and-forget。 */
  interruptCurrent(): void;
  /** 渲染面是否可用（pet 窗口存活且回执过 ready）。 */
  isAvailable(): boolean;
}

// ── 协议校验（A13）────────────────────────────────────────────────────────

export type PetValidation =
  | { ok: true; params: PetSequenceParams }
  | { ok: false; reason: string };

function isFiniteInt(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function validatePlayback(playback: unknown): PetPlayback | null {
  if (typeof playback !== "object" || playback === null) return null;
  const p = playback as Record<string, unknown>;
  if (p.kind === "once") {
    const duration = p.durationMs;
    return isFiniteInt(duration) && duration > 0 && duration <= PET_MAX_STEP_DURATION_MS
      ? { kind: "once", durationMs: duration }
      : null;
  }
  if (p.kind === "loopForDuration") {
    const duration = p.durationMs;
    const clip = p.clipMs;
    return isFiniteInt(duration) &&
      duration > 0 &&
      duration <= PET_MAX_STEP_DURATION_MS &&
      isFiniteInt(clip) &&
      clip > 0
      ? { kind: "loopForDuration", durationMs: duration, clipMs: clip }
      : null;
  }
  return null;
}

function validateStep(raw: unknown): PetStepAction | null {
  if (typeof raw !== "object" || raw === null) return null;
  const s = raw as Record<string, unknown>;
  if (s.kind === "playAction") {
    const animation = s.animation;
    // idle 仅内部待机，不对外接单（A13）。
    if (typeof animation !== "string" || !(PET_ANIMATIONS as readonly string[]).includes(animation) || animation === "idle") {
      return null;
    }
    const playback = validatePlayback(s.playback);
    if (!playback) return null;
    if (s.completionBehavior !== "restoreIdle") return null;
    if (!isFiniteInt(s.timeoutMs) || (s.timeoutMs as number) <= 0 || (s.timeoutMs as number) > PET_MAX_STEP_DURATION_MS) {
      return null;
    }
    return {
      kind: "playAction",
      animation: animation as PetAnimation,
      playback,
      completionBehavior: "restoreIdle",
      timeoutMs: s.timeoutMs as number,
    };
  }
  if (s.kind === "moveByPath") {
    const path = s.path;
    if (!Array.isArray(path) || path.length < 1 || path.length > 1) return null;
    const node = path[0];
    if (typeof node !== "object" || node === null || (node as Record<string, unknown>).kind !== "home") {
      return null;
    }
    if (!isFiniteInt(s.timeoutMs) || (s.timeoutMs as number) <= 0 || (s.timeoutMs as number) > PET_MAX_STEP_DURATION_MS) {
      return null;
    }
    return { kind: "moveByPath", path: [{ kind: "home" }], timeoutMs: s.timeoutMs as number };
  }
  return null;
}

export function validateSequenceInput(raw: unknown): PetValidation {
  if (typeof raw !== "object" || raw === null) return { ok: false, reason: "params must be an object" };
  const p = raw as Record<string, unknown>;
  if (typeof p.requestId !== "string" || !PET_REQUEST_ID_PATTERN.test(p.requestId)) {
    return { ok: false, reason: "requestId mismatch" };
  }
  if (!isFiniteInt(p.priority) || (p.priority as number) < PET_PRIORITY_MIN || (p.priority as number) > PET_PRIORITY_MAX) {
    return { ok: false, reason: "priority must be integer 0..100" };
  }
  if (!Array.isArray(p.steps) || p.steps.length < 1 || p.steps.length > PET_MAX_STEPS) {
    return { ok: false, reason: "steps must be 1..16" };
  }
  const steps: PetStepAction[] = [];
  for (const step of p.steps) {
    const parsed = validateStep(step);
    if (!parsed) return { ok: false, reason: "invalid step" };
    steps.push(parsed);
  }
  return { ok: true, params: { requestId: p.requestId as string, priority: p.priority as number, steps } };
}

/** 宏 → 序列（§3.1 宏表；tool.ts 消费）。 */
export function compileMacroSequence(macro: keyof typeof PET_MACRO_CATALOG): PetSequenceParams {
  const spec = PET_MACRO_CATALOG[macro];
  const step: PetStepAction =
    macro === "returnHome"
      ? { kind: "moveByPath", path: [{ kind: "home" }], timeoutMs: PET_SAFE_HOME_TIMEOUT_MS }
      : {
          kind: "playAction",
          animation: spec.animation,
          playback: spec.playback,
          completionBehavior: "restoreIdle",
          timeoutMs: PET_MAX_STEP_DURATION_MS,
        };
  return {
    requestId: `MACRO-${macro.toUpperCase()}-${Date.now().toString(36).toUpperCase()}`,
    priority: spec.priority,
    steps: [step],
  };
}

// ── 准入控制器（A15/A16）──────────────────────────────────────────────────

interface RunningEntry {
  params: PetSequenceParams;
  resolve: (result: PetSequenceResult) => void;
  completedSteps: number;
  preempted: boolean;
  settled: boolean;
}

export interface PetAdmissionOptions {
  executor: PetStepExecutor;
  /** 可注入时钟（合成自测用）；默认 setTimeout。 */
  schedule?: (fn: () => void, ms: number) => () => void;
}

export class PetAdmissionController {
  private current: RunningEntry | null = null;
  private readonly pending: RunningEntry[] = [];
  private readonly executor: PetStepExecutor;
  private readonly schedule: (fn: () => void, ms: number) => () => void;

  constructor(options: PetAdmissionOptions) {
    this.executor = options.executor;
    this.schedule =
      options.schedule ??
      ((fn, ms) => {
        const t = setTimeout(fn, ms);
        return () => clearTimeout(t);
      });
  }

  get isRunning(): boolean {
    return this.current !== null;
  }

  get pendingCount(): number {
    return this.pending.length;
  }

  /** 入口：校验失败返回 VALIDATION_FAILED（不抛错，A20 语义）；忙返回 PET_BUSY（A15）。 */
  execute(rawInput: unknown): Promise<PetSequenceResult> {
    const validation = validateSequenceInput(rawInput);
    if (!validation.ok) {
      return Promise.resolve({ status: "failed", code: "VALIDATION_FAILED", completedSteps: 0 });
    }
    const params = validation.params;
    return new Promise<PetSequenceResult>((resolve) => {
      const entry: RunningEntry = { params, resolve, completedSteps: 0, preempted: false, settled: false };
      if (this.current === null) {
        this.start(entry);
        return;
      }
      if (params.priority <= this.current.params.priority) {
        resolve({ status: "failed", code: "PET_BUSY", completedSteps: 0 });
        return;
      }
      // 严格更高：先打断当前步（fire-and-forget），排队等旧序列收口后开跑。
      this.executor.interruptCurrent();
      this.insertPending(entry);
    });
  }

  private insertPending(entry: RunningEntry): void {
    // 高优先级在前；同级按到达序（稳定）。
    const index = this.pending.findIndex((e) => entry.params.priority > e.params.priority);
    if (index < 0) this.pending.push(entry);
    else this.pending.splice(index, 0, entry);
  }

  private start(entry: RunningEntry): void {
    this.current = entry;
    if (!this.executor.isAvailable()) {
      this.settle(entry, { status: "failed", code: "PET_UNAVAILABLE", completedSteps: 0 });
      return;
    }
    void this.runSteps(entry);
  }

  private async runSteps(entry: RunningEntry): Promise<void> {
    const { params } = entry;
    for (let index = 0; index < params.steps.length; index += 1) {
      if (entry.settled) return;
      const step = params.steps[index]!;
      const stepId = `step_${randomUUID()}`;
      const outcome = await this.runStepGuarded(step, { requestId: params.requestId, stepId, index });
      if (entry.settled) return;
      if (outcome.kind === "completed") {
        entry.completedSteps = index + 1;
        continue;
      }
      if (outcome.kind === "interrupted") {
        this.settle(entry, {
          status: "interrupted",
          reasonCode: "admission.preemptedByHigherPriorityPlan",
          completedSteps: entry.completedSteps,
        });
        return;
      }
      if (outcome.kind === "unavailable") {
        this.settle(entry, { status: "failed", code: "PET_UNAVAILABLE", completedSteps: entry.completedSteps });
        return;
      }
      // 步失败 → 自动安全回家（moveByPath home 15s），再返回失败（A16）。
      await this.runStepGuarded(
        { kind: "moveByPath", path: [{ kind: "home" }], timeoutMs: PET_SAFE_HOME_TIMEOUT_MS },
        { requestId: params.requestId, stepId: `step_${randomUUID()}`, index: -1 },
      );
      this.settle(entry, { status: "failed", code: "PET_STEP_FAILED", completedSteps: entry.completedSteps });
      return;
    }
    this.settle(entry, { status: "completed", completedSteps: entry.completedSteps });
  }

  /** 步执行 + 主进程侧守卫超时（timeoutMs+1000；渲染面失联不挂死准入）。 */
  private runStepGuarded(
    step: PetStepAction,
    context: { requestId: string; stepId: string; index: number },
  ): Promise<PetStepOutcome> {
    return new Promise<PetStepOutcome>((resolve) => {
      let done = false;
      const finish = (outcome: PetStepOutcome) => {
        if (done) return;
        done = true;
        cancelGuard();
        resolve(outcome);
      };
      const cancelGuard = this.schedule(() => finish({ kind: "failed" }), step.timeoutMs + PET_STEP_GUARD_SLACK_MS);
      this.executor
        .runStep(step, context)
        .then(finish)
        .catch(() => finish({ kind: "failed" }));
    });
  }

  private settle(entry: RunningEntry, result: PetSequenceResult): void {
    if (entry.settled) return;
    entry.settled = true;
    if (this.current === entry) this.current = null;
    entry.resolve(result);
    const next = this.pending.shift();
    if (next) this.start(next);
  }
}
