// 功能 #28 桌宠 · 宏目录与状态词表（RE-28 §3.1 表 / §3.2 八态投影）。
import type { PetMotion } from "@zcode/shared";

// 8 宏同名同语义同参数对齐竞品行为面（对拍 7），数值逐格照规格表钉死；
// 词表为自写措辞（表达隔离）：八态=A28 六词全落点 + thinking/working 细分（对拍 32）。

/** 恰 8 个动画（idle 仅内部待机，不在宏目录）。 */
export const PET_ANIMATIONS = [
  "idle",
  "thinking",
  "working",
  "approval",
  "celebrate",
  "sad",
  "curious",
  "explain",
] as const;
export type PetAnimation = (typeof PET_ANIMATIONS)[number];

/** 恰 8 个宏（A12：thinking/working/awaitApproval/celebrate/sad/curious/explain/returnHome）。 */
export const PET_MACRO_IDS = [
  "thinking",
  "working",
  "awaitApproval",
  "celebrate",
  "sad",
  "curious",
  "explain",
  "returnHome",
] as const;
export type PetMacroId = (typeof PET_MACRO_IDS)[number];

export type PetPlayback =
  | { kind: "once"; durationMs: number }
  | { kind: "loopForDuration"; durationMs: number; clipMs: number };

export interface PetMacroSpec {
  id: PetMacroId;
  animation: PetAnimation;
  playback: PetPlayback;
  priority: number;
  /** loop 宏=可被打断且回 idle（interruptible→idle）；once 宏=播完收步（finishStep→idle）。 */
  interruptible: boolean;
}

function loop(
  id: PetMacroId,
  animation: PetAnimation,
  durationMs: number,
  clipMs: number,
  priority: number,
): PetMacroSpec {
  return {
    id,
    animation,
    playback: { kind: "loopForDuration", durationMs, clipMs },
    priority,
    interruptible: true,
  };
}

function once(id: PetMacroId, animation: PetAnimation, durationMs: number, priority: number): PetMacroSpec {
  return {
    id,
    animation,
    playback: { kind: "once", durationMs },
    priority,
    interruptible: false,
  };
}

// 时长/clip/优先级（对拍 7，规格 §3.1 表逐行）：
// thinking 3000/2420/p10、working 3000/1840/p10、awaitApproval 5000/2540/p30、
// celebrate once 1720/p20、sad 3000/2400/p20、curious once 2880/p20、explain 3000/1940/p20、
// returnHome=moveByPath([home]) timeout 15000/p40。
export const PET_MACRO_CATALOG: Record<PetMacroId, PetMacroSpec> = {
  thinking: loop("thinking", "thinking", 3000, 2420, 10),
  working: loop("working", "working", 3000, 1840, 10),
  awaitApproval: loop("awaitApproval", "approval", 5000, 2540, 30),
  celebrate: once("celebrate", "celebrate", 1720, 20),
  sad: loop("sad", "sad", 3000, 2400, 20),
  curious: once("curious", "curious", 2880, 20),
  explain: loop("explain", "explain", 3000, 1940, 20),
  returnHome: {
    id: "returnHome",
    animation: "explain", // 移动复用 explain 帧位（§3.1 动画清单注）
    playback: { kind: "loopForDuration", durationMs: 15000, clipMs: 15000 },
    priority: 40,
    interruptible: true,
  },
};

// ── 八态投影（§3.2 驱动流 1）─────────────────────────────────────────────

export const PET_MOTIONS = [
  "idle",
  "thinking",
  "working",
  "awaitApproval",
  "success",
  "cancelled",
  "failed",
  "disconnected",
] as const;
export type { PetMotion };

/** 状态词（A28 六词全落点 + thinking/working 自写细分；对拍 32）。 */
export const PET_MOTION_LABELS: Record<PetMotion, string> = {
  idle: "待命中",
  thinking: "模型推理中",
  working: "工具执行中",
  awaitApproval: "等待授权确认或提问",
  success: "刚完成一次运行",
  cancelled: "运行已取消",
  failed: "需要查看错误",
  disconnected: "桌面端未连接",
};

/** 投影态 → 动画映射（success 撞一次 celebrate 后回 idle 由渲染层收口）。 */
export const PET_MOTION_ANIMATION: Record<PetMotion, PetAnimation> = {
  idle: "idle",
  thinking: "thinking",
  working: "working",
  awaitApproval: "approval",
  success: "celebrate",
  cancelled: "idle",
  failed: "sad",
  disconnected: "idle",
};

/** 工具活动分类文案（B19 语义，自写词表；正则分类=检索/写入/执行/检验）。 */
const PET_TOOL_KIND_PATTERNS: Array<{ kind: string; pattern: RegExp }> = [
  { kind: "检索", pattern: /search|grep|find|list|glob|read|fetch|query/i },
  { kind: "写入", pattern: /write|edit|patch|apply|create|save|insert|update/i },
  { kind: "执行", pattern: /bash|shell|exec|run|command|terminal/i },
  { kind: "检验", pattern: /test|check|verify|lint|validate|review/i },
];

export function petToolActivityLabel(toolName: string): string {
  for (const { kind, pattern } of PET_TOOL_KIND_PATTERNS) {
    if (pattern.test(toolName)) return `工具执行中（${kind}）`;
  }
  return PET_MOTION_LABELS.working;
}
