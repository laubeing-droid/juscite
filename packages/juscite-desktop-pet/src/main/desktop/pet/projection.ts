// 功能 #28 桌宠 · 运行状态投影（RE-28 §3.2 驱动流 1；八态超集，A28 六词全落点）。
// 事实源=壳转发（sessions-index 边沿）+ 桥进程存活轮询。纯逻辑：store/schedule 注入，
// 不 import electron，合成自测直跑。投影态=基态（idle/thinking/working/awaitApproval/
// disconnected）+ 终态动画窗（success→celebrate 1720ms 回基态；failed→sad 3000ms 回基态；
// cancelled→气泡"运行已取消"+动画直回 idle）。

import type { PetBubbleState, PetMotion, PetRunEventPayload } from "@zcode/shared";
import { PET_MOTION_LABELS } from "./motions.js";

/** 终态动画/气泡收口时长：celebrate once 1720ms；sad loop 3000ms；气泡 3s（B17）。 */
export const PET_SUCCESS_MOTION_MS = 1_720;
export const PET_SAD_MOTION_MS = 3_000;
export const PET_TERMINAL_BUBBLE_MS = 3_000;

export interface PetProjectionStore {
  setMotion(motion: PetMotion): void;
  setBubble(bubble: PetBubbleState | null): void;
}

export interface PetProjectionDeps {
  store: PetProjectionStore;
  /** 桥进程存活（desktopHostProcess.isBridgeAlive）——桌面端未连接态的事实源。 */
  isBridgeAlive: () => boolean;
  /** 可注入时钟（合成自测用）；默认 setTimeout。 */
  schedule?: (fn: () => void, ms: number) => () => void;
}

export class PetRunProjection {
  private baseMotion: PetMotion = "idle";
  private runBubbleBody: string | null = null;
  private sequenceActive = false;
  private motionTimer: (() => void) | null = null;
  private readonly store: PetProjectionStore;
  private readonly isBridgeAlive: () => boolean;
  private readonly schedule: (fn: () => void, ms: number) => () => void;

  constructor(deps: PetProjectionDeps) {
    this.store = deps.store;
    this.isBridgeAlive = deps.isBridgeAlive;
    this.schedule =
      deps.schedule ??
      ((fn, ms) => {
        const t = setTimeout(fn, ms);
        return () => clearTimeout(t);
      });
  }

  get currentBaseMotion(): PetMotion {
    return this.baseMotion;
  }

  /** 宏序列播放期占位（准入优先，运行投影不覆盖；收口回基态）。 */
  setSequenceActive(active: boolean): void {
    this.sequenceActive = active;
    if (!active) this.projectBaseMotion();
  }

  get isSequenceActive(): boolean {
    return this.sequenceActive;
  }

  private applyMotion(
    motion: PetMotion,
    bubbleBody: string | null,
    bubbleTtl: number,
    tone: PetBubbleState["tone"],
  ): void {
    this.store.setMotion(motion);
    if (bubbleBody === null) {
      this.store.setBubble(null);
      return;
    }
    this.store.setBubble({
      id: `${motion}:${bubbleBody}`,
      title: "Juscite 桌宠",
      body: bubbleBody,
      tone,
      ttlMs: bubbleTtl,
    });
  }

  projectBaseMotion(): void {
    if (this.sequenceActive) return;
    if (!this.isBridgeAlive()) {
      this.baseMotion = "disconnected";
      this.applyMotion("disconnected", PET_MOTION_LABELS.disconnected, 0, "warn");
      return;
    }
    this.applyMotion(this.baseMotion, this.runBubbleBody, 0, "info");
  }

  private backToBaseAfter(ms: number): void {
    if (this.motionTimer) this.motionTimer();
    const cancel = this.schedule(() => {
      this.motionTimer = null;
      this.baseMotion = "idle";
      this.projectBaseMotion();
    }, ms);
    this.motionTimer = cancel;
  }

  /** 桥存活轮询入口（周期调用；断连=桌面端未连接，重连自动恢复）。 */
  pollBridge(): void {
    if (this.sequenceActive) return;
    const disconnected = !this.isBridgeAlive();
    if (disconnected && this.baseMotion !== "disconnected") {
      this.baseMotion = "disconnected";
      this.projectBaseMotion();
    } else if (!disconnected && this.baseMotion === "disconnected") {
      this.baseMotion = "idle";
      this.projectBaseMotion();
    }
  }

  reportRunEvent(event: PetRunEventPayload): void {
    if (this.sequenceActive) return; // 宏序列播放中不被运行投影覆盖（准入优先）
    switch (event.kind) {
      case "running": {
        this.baseMotion = "working";
        this.runBubbleBody = event.sessionTitle
          ? `正在处理「${event.sessionTitle}」`
          : PET_MOTION_LABELS.working;
        this.applyMotion("working", this.runBubbleBody, 0, "info");
        break;
      }
      case "pending": {
        this.baseMotion = "awaitApproval";
        this.runBubbleBody = PET_MOTION_LABELS.awaitApproval;
        this.applyMotion("awaitApproval", this.runBubbleBody, 0, "warn");
        break;
      }
      case "terminal": {
        this.runBubbleBody = null;
        if (event.outcome === "completed") {
          this.applyMotion("success", PET_MOTION_LABELS.success, PET_TERMINAL_BUBBLE_MS, "success");
          this.backToBaseAfter(PET_SUCCESS_MOTION_MS);
        } else if (event.outcome === "error") {
          this.applyMotion("failed", PET_MOTION_LABELS.failed, PET_TERMINAL_BUBBLE_MS, "error");
          this.backToBaseAfter(PET_SAD_MOTION_MS);
        } else {
          // cancelled：气泡"运行已取消"+动画回 idle（§3.2 自研补落点）。
          this.baseMotion = "idle";
          this.applyMotion("idle", PET_MOTION_LABELS.cancelled, PET_TERMINAL_BUBBLE_MS, "info");
        }
        break;
      }
      case "idle": {
        this.baseMotion = "idle";
        this.runBubbleBody = null;
        this.projectBaseMotion();
        break;
      }
    }
  }
}
