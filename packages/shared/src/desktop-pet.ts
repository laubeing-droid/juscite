// 功能 #28 桌宠 · 跨进程载荷契约（RE-28 §3.1 数据模型 / §3.2 驱动流）。
// 主进程 pet 模块（packages/desktop/src/main/desktop/pet）持有权威实现；
// 本文件只定契约形状：preload / 设置面 / 主渲染层转发钩子按此类型对话，不 import 桌面内部件。

/** 八态投影（A28 六词全落点 + thinking/working 细分；词表在桌面 motions.ts）。 */
export type PetMotion =
  | "idle"
  | "thinking"
  | "working"
  | "awaitApproval"
  | "success"
  | "cancelled"
  | "failed"
  | "disconnected";

/** 桌宠持久配置（落盘 %APPDATA%\Juscite\desktop\pet.json，随壳 store 机制）。 */
export interface PetConfig {
  /** 关闭=销毁窗口，重启不自动拉起（B28）。 */
  enabled: boolean;
  alwaysOnTop: boolean;
  rememberPosition: boolean;
  /** 50..200，步进 5，默认 100。 */
  sizePercent: number;
  /** 抛射默认关（dsh issue #930 语义）。 */
  throwEnabled: boolean;
  /** v1 单皮肤，键位留。 */
  activeSkin: string;
}

export type PetConfigPatch = Partial<PetConfig>;

export interface PetBubbleState {
  id: string;
  title: string;
  body: string;
  tone: "info" | "success" | "warn" | "error";
  /** 渲染层按 ttl 自动消失；0=常驻（跟随状态，状态翻走即清）。 */
  ttlMs: number;
}

export interface PetRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PetSize {
  width: number;
  height: number;
}

export interface PetGeometryPayload {
  window: PetSize;
  /** 本体命中箱（窗口内坐标，右下锚定）——命中区按本体非整窗（B23）。 */
  body: PetRect;
}

/** PetStatus：config 全字段 + 派生 visible + 运行态 motion/气泡 + 几何（变更即广播）。 */
export interface PetStatusPayload {
  config: PetConfig;
  /** 可见性≡持久开关（dsh B6 历史字段语义）。 */
  visible: boolean;
  motion: PetMotion;
  bubble: PetBubbleState | null;
  geometry: PetGeometryPayload;
  /** 桌宠窗口当前是否存活（主进程广播/读取时按实况覆写）；缺失=未知。
   *  对拍 28：重建再败销毁后=false，设置页据此给可见提示。 */
  windowAlive?: boolean;
}

/** 主渲染层 → 桌宠运行事件（sessions-index 事实的边沿投影，驱动流 1）。 */
export interface PetRunEventPayload {
  kind: "running" | "terminal" | "pending" | "idle";
  /** kind=terminal 时有效（sessions-index lastOutcome）。 */
  outcome?: "completed" | "error" | "interrupted";
  /** 气泡标题候选（会话 title）。 */
  sessionTitle?: string;
}
