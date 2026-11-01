// 功能 #28 桌宠 · 主渲染层运行事件转发钩子（RE-28 §3.2 驱动流 1）。
// 事实源=sessions-index（与任务通知同一权威）：phase 边沿 → PetRunEventPayload → 桌宠。
// 八态投影在桌宠主进程侧完成，这里只转发边沿（running/pending/terminal/idle + 会话标题），
// 不造事实：sessions-index 没有的细分（thinking/工具名）不下发。

import { useEffect, useRef } from "react";
import type { IPlatformService } from "@zcode/shared";
import type { SessionSummary } from "@zcode/shared/zcode-protocol-v4";
import { useServices } from "@/hooks/useServices.js";
import {
  acquireSessionsIndex,
  releaseSessionsIndex,
  type SessionsIndexScope,
} from "@/v4/sessionsIndexRegistry.js";

export interface PetRunStatusForwarderParams {
  workspacePath: string;
  workspaceIdentity?: string;
  endpointKey?: string | null;
  rpcReady: boolean;
  platform: Pick<IPlatformService, "reportPetRunEvent"> | null | undefined;
}

interface DerivedRunState {
  kind: "running" | "pending" | "idle";
  title: string | null;
}

function isRunningPhase(phase: string): boolean {
  return phase === "running" || phase === "prewarming";
}

function isTerminalPhase(phase: string): boolean {
  return phase === "completedSuccess" || phase === "completedInterrupted" || phase === "error";
}

function mostRecentSession(sessions: readonly SessionSummary[]): SessionSummary | null {
  let best: SessionSummary | null = null;
  for (const session of sessions) {
    if (!best || session.lastActivityAt > best.lastActivityAt) best = session;
  }
  return best;
}

/** 从快照推导当前投影态：pending > running > idle（优先级即用户注意力序）。 */
function deriveRunState(sessions: readonly SessionSummary[]): DerivedRunState {
  let running: SessionSummary | null = null;
  for (const session of sessions) {
    const pending = session.pendingInteractionSummary;
    if (pending && pending.permissionCount + pending.userInputCount > 0) {
      return { kind: "pending", title: session.title };
    }
    if (isRunningPhase(session.phase) && !session.sessionEnded) {
      if (!running || session.lastActivityAt > running.lastActivityAt) running = session;
    }
  }
  if (running) return { kind: "running", title: running.title };
  return { kind: "idle", title: null };
}

export function usePetRunStatusForwarder(params: PetRunStatusForwarderParams): void {
  const { zcodeAgentService } = useServices();
  const { workspacePath, workspaceIdentity, endpointKey, rpcReady, platform } = params;
  const workspaceKey = workspaceIdentity?.trim() || workspacePath;
  const previousBySessionIdRef = useRef<Map<string, SessionSummary> | null>(null);
  const lastSentRef = useRef<string>("");

  useEffect(() => {
    if (!rpcReady || !platform?.reportPetRunEvent) {
      previousBySessionIdRef.current = null;
      return;
    }
    const report = platform.reportPetRunEvent.bind(platform);
    const registryScope: SessionsIndexScope = {
      workspaceKey,
      workspacePath,
      ...(workspaceIdentity ? { workspaceIdentity } : {}),
      ...(endpointKey ? { endpointKey } : {}),
    };
    const store = acquireSessionsIndex(registryScope, zcodeAgentService);

    const syncState = () => {
      const status = store.getStatus();
      const sessions = store.getSessions();
      const previous = previousBySessionIdRef.current;

      // 终态边沿：上一帧 running/prewarming → 本帧 completedSuccess/completedInterrupted/error。
      if (status === "live" && previous) {
        for (const session of sessions) {
          if (!isTerminalPhase(session.phase)) continue;
          const prev = previous.get(session.sessionId);
          if (!prev || !isRunningPhase(prev.phase)) continue;
          const outcome =
            session.phase === "completedSuccess"
              ? "completed"
              : session.phase === "error"
                ? "error"
                : "interrupted";
          report({ kind: "terminal", outcome, sessionTitle: session.title });
          lastSentRef.current = `terminal:${outcome}`;
        }
      }

      const derived = deriveRunState(sessions);
      const signature =
        derived.kind === "idle" ? "idle" : `${derived.kind}:${derived.title ?? ""}`;
      if (status === "live" && signature !== lastSentRef.current) {
        lastSentRef.current = signature;
        if (derived.kind === "idle") {
          // 无运行/无阻塞：仅在之前是 running/pending 时回 idle（避免首帧噪音）。
          if (previous && [...previous.values()].some((s) => isRunningPhase(s.phase))) {
            report({ kind: "idle" });
          }
        } else {
          report({ kind: derived.kind, sessionTitle: derived.title ?? undefined });
        }
      }

      if (status === "live") {
        previousBySessionIdRef.current = new Map(sessions.map((s) => [s.sessionId, s]));
      }
    };

    const unsubscribe = store.subscribe(syncState);
    syncState();
    return () => {
      unsubscribe();
      releaseSessionsIndex(registryScope, store);
    };
  }, [endpointKey, platform, rpcReady, workspaceIdentity, workspaceKey, workspacePath, zcodeAgentService]);
}
