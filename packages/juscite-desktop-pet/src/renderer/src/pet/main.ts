// 功能 #28 桌宠 · 渲染层入口（RE-28 §3.3 渲染层；pet.html 专用）。
// requestAnimationFrame 帧步进器读 manifest 逐帧 durationMs（对拍 29）；
// 状态→动画映射；命中箱=本体矩形（B23/B22）；拖拽=pointer 事件+弹簧+moving-* 方向翻转
// （对拍 20）；抛射默认关、开=physics 全套（对拍 21）；单击本体=唤出主窗口（对拍 19）；
// 资产异常可见提示绝不开透明空窗（B15）。

import {
  PET_SPRITE_MANIFEST,
  paintSpriteFrame,
  spriteManifestEntry,
  type SpriteAnimationName,
} from "./sprites.js";
import {
  estimateThrowVelocity,
  isThrowable,
  stepFlight,
  type FlightState,
  type VelocitySample,
} from "./physics.js";
import type { PetStatusPayload } from "@zcode/shared";

interface PetHostBridge {
  ready(): void;
  onStatus(handler: (status: PetStatusPayload) => void): () => void;
  onWorkAreas(handler: (areas: Array<{ x: number; y: number; width: number; height: number }>) => void): () => void;
  onStep(handler: (envelope: PetStepEnvelope) => void): () => void;
  onInterrupt(handler: () => void): () => void;
  ackStep(id: string, outcome: { kind: "completed" | "interrupted" | "failed" | "unavailable" }): void;
  setHover(hovering: boolean): void;
  click(): void;
  move(x: number, y: number): void;
  reportAssetError(message: string): void;
  getWorkAreas(): Promise<Array<{ x: number; y: number; width: number; height: number }>>;
  getBounds(): Promise<{ x: number; y: number; width: number; height: number }>;
  requestClamp(): void;
}

interface PetStepEnvelope {
  id: string;
  step:
    | {
        kind: "playAction";
        animation: SpriteAnimationName;
        playback: { kind: "once" | "loopForDuration"; durationMs: number; clipMs?: number };
      }
    | { kind: "moveByPath"; path: Array<{ kind: string }>; timeoutMs: number };
}

declare global {
  interface Window {
    petHost: PetHostBridge;
  }
}

const host = window.petHost;
const canvas = document.getElementById("pet-canvas") as HTMLCanvasElement;
const ctx = canvas.getContext("2d");
const bubbleEl = document.getElementById("pet-bubble") as HTMLDivElement;
const errorEl = document.getElementById("pet-error") as HTMLDivElement;
if (!ctx) throw new Error("pet canvas 2d context unavailable");

const MARGIN = 24;

let status: PetStatusPayload | null = null;
let workAreas: Array<{ x: number; y: number; width: number; height: number }> = [];
// 动画播放器
let currentAnim: SpriteAnimationName = "idle";
let frameIndex = 0;
let frameAccumMs = 0;
let stepPlayback: { until: number; done: boolean; id: string; kind: "playAction" } | null = null;
let homeGlide: { targetX: number; targetY: number; id: string; deadline: number } | null = null;
let stepInterrupted = false;
// 拖拽/抛射
let dragging = false;
let dragOffset = { x: 0, y: 0 }; // 指针相对窗口的抓取偏移
let windowStart = { x: 0, y: 0 };
let springPos = { x: 0, y: 0 };
let springTarget = { x: 0, y: 0 };
let velocitySamples: VelocitySample[] = [];
let flip = false;
let flight: FlightState | null = null;
let flightBounds: { left: number; right: number; top: number; bottom: number } | null = null;
let hoverBody = false;
let lastDragClient = { x: 0, y: 0 };

function bodyRect(): { x: number; y: number; width: number; height: number } {
  const geometry = status?.geometry;
  if (!geometry) return { x: 0, y: 0, width: 0, height: 0 };
  return geometry.body;
}

function resizeCanvas(): void {
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(window.innerWidth * dpr);
  canvas.height = Math.round(window.innerHeight * dpr);
  ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
}

const MOTION_TO_ANIMATION: Record<string, SpriteAnimationName> = {
  idle: "idle",
  thinking: "thinking",
  working: "working",
  awaitApproval: "approval",
  success: "celebrate",
  cancelled: "idle",
  failed: "sad",
  disconnected: "idle",
};

let lastMotion: string | null = null;

function applyStatus(next: PetStatusPayload): void {
  status = next;
  resizeCanvas();
  renderBubble(next);
  if (lastMotion !== next.motion) {
    lastMotion = next.motion;
    if (!stepPlayback && !homeGlide) {
      currentAnim = MOTION_TO_ANIMATION[next.motion] ?? "idle";
      frameIndex = 0;
      frameAccumMs = 0;
    }
  }
}

function renderBubble(next: PetStatusPayload): void {
  const bubble = next.bubble;
  if (!bubble) {
    bubbleEl.style.display = "none";
    return;
  }
  bubbleEl.textContent = `${bubble.title} · ${bubble.body}`;
  bubbleEl.dataset.tone = bubble.tone;
  bubbleEl.style.display = "block";
  // 气泡挂在宠物上方靠右（窗口右上透明区）。
  bubbleEl.style.right = "12px";
  bubbleEl.style.top = "10px";
  if (bubble.ttlMs > 0) {
    const id = bubble.id;
    window.setTimeout(() => {
      if (status?.bubble?.id === id) bubbleEl.style.display = "none";
    }, bubble.ttlMs);
  }
}

function showFatal(message: string): void {
  // B15：可见提示，绝不开透明空窗。
  errorEl.textContent = `桌宠素材加载失败：${message}`;
  errorEl.style.display = "block";
  host.reportAssetError(message);
}

function playStep(envelope: PetStepEnvelope): void {
  const step = envelope.step;
  if (step.kind === "playAction") {
    currentAnim = step.animation;
    frameIndex = 0;
    frameAccumMs = 0;
    stepInterrupted = false;
    stepPlayback = { until: performance.now() + step.playback.durationMs, done: false, id: envelope.id, kind: "playAction" };
    return;
  }
  // moveByPath：仅允许 home（主进程已校验）； Glide 回默认位（主屏右下角）。
  const geometry = status?.geometry.window;
  const area = workAreas[0];
  if (!geometry || !area) {
    host.ackStep(envelope.id, { kind: "completed" });
    return;
  }
  const targetX = area.x + area.width - geometry.width - MARGIN;
  const targetY = area.y + area.height - geometry.height - MARGIN;
  stepInterrupted = false;
  currentAnim = "explain"; // 移动复用 explain 帧位
  homeGlide = { targetX, targetY, id: envelope.id, deadline: performance.now() + step.timeoutMs };
  void host.getBounds().then((bounds) => {
    if (!homeGlide) return;
    springPos = { x: bounds.x, y: bounds.y };
    springTarget = { x: targetX, y: targetY };
  });
}

function pointerInBody(e: PointerEvent): boolean {
  const body = bodyRect();
  return e.clientX >= body.x && e.clientX <= body.x + body.width && e.clientY >= body.y && e.clientY <= body.y + body.height;
}

canvas.addEventListener("pointermove", (e) => {
  const hovering = pointerInBody(e);
  if (hovering !== hoverBody) {
    hoverBody = hovering;
    host.setHover(hovering);
    canvas.style.cursor = hovering ? "grab" : "default";
  }
  if (!dragging) return;
  velocitySamples.push({ t: performance.now(), x: e.clientX, y: e.clientY });
  if (velocitySamples.length > 32) velocitySamples.shift();
  lastDragClient = { x: e.clientX, y: e.clientY };
  springTarget = {
    x: windowStart.x + (e.clientX - dragOffset.x),
    y: windowStart.y + (e.clientY - dragOffset.y),
  };
  const dx = e.clientX - dragOffset.x - (springPos.x - windowStart.x);
  if (Math.abs(dx) > 2) flip = dx < 0; // moving-left/right 方向翻转
});

canvas.addEventListener("pointerdown", (e) => {
  if (e.button !== 0 || !pointerInBody(e)) return;
  if (flight) return; // 飞行中抓取由 device 流兜底（Electron forward 已把事件送进来）
  void host.getBounds().then((bounds) => {
    dragging = true;
    windowStart = { x: bounds.x, y: bounds.y };
    springPos = { x: bounds.x, y: bounds.y };
    springTarget = { x: bounds.x, y: bounds.y };
    dragOffset = { x: e.clientX, y: e.clientY };
    velocitySamples = [{ t: performance.now(), x: e.clientX, y: e.clientY }];
    canvas.setPointerCapture(e.pointerId);
    canvas.style.cursor = "grabbing";
    void host.getWorkAreas().then((areas) => {
      workAreas = areas; // 抓取时刷新工作区（B23 热插拔即生效）
    });
  });
});

canvas.addEventListener("pointerup", (e) => {
  if (!dragging) return;
  dragging = false;
  canvas.style.cursor = "grab";
  velocitySamples.push({ t: performance.now(), x: e.clientX, y: e.clientY });
  const velocity = estimateThrowVelocity(velocitySamples, performance.now());
  velocitySamples = [];
  const moved = Math.hypot(lastDragClient.x - dragOffset.x, lastDragClient.y - dragOffset.y);
  if (moved < 5) {
    // 单击命中=聚焦主窗口（对拍 19）。
    host.click();
    return;
  }
  if (status?.config.throwEnabled && isThrowable(velocity)) {
    startFlight(velocity);
  }
});

function startFlight(velocity: { vx: number; vy: number }): void {
  const geometry = status?.geometry;
  if (!geometry) return;
  const body = geometry.body;
  const stage = pickStageForBody();
  if (!stage) return;
  flightBounds = {
    left: stage.x - body.x,
    right: stage.x + stage.width - body.width - body.x,
    top: stage.y - body.y,
    bottom: stage.y + stage.height - body.height - body.y,
  };
  flight = {
    x: springPos.x,
    y: springPos.y,
    vx: velocity.vx,
    vy: velocity.vy,
    lastImpactSpeed: 0,
    grounded: false,
  };
}

function pickStageForBody(): { x: number; y: number; width: number; height: number } | null {
  // 跨屏选本体中心所在工作区（B23）；近似取当前窗口中心。
  if (workAreas.length === 0) return null;
  const cx = springPos.x + (status?.geometry.window.width ?? 0) / 2;
  const cy = springPos.y + (status?.geometry.window.height ?? 0) / 2;
  for (const area of workAreas) {
    if (cx >= area.x && cx <= area.x + area.width && cy >= area.y && cy <= area.y + area.height) return area;
  }
  return workAreas[0]!;
}

// ── 主循环 ────────────────────────────────────────────────────────────────

let lastFrameTs = performance.now();

function tick(ts: number): void {
  const dtMs = Math.min(ts - lastFrameTs, 100);
  lastFrameTs = ts;
  try {
    advanceAnimation(dtMs, ts);
    advanceDragSpring();
    advanceFlight(dtMs);
    draw();
  } catch (error) {
    showFatal(error instanceof Error ? error.message : String(error));
  }
  window.requestAnimationFrame(tick);
}

function advanceAnimation(dtMs: number, ts: number): void {
  // 宏步播放收口
  if (stepPlayback && !stepPlayback.done) {
    if (ts >= stepPlayback.until) {
      stepPlayback.done = true;
      host.ackStep(stepPlayback.id, { kind: stepInterrupted ? "interrupted" : "completed" });
      stepPlayback = null;
      currentAnim = MOTION_TO_ANIMATION[status?.motion ?? "idle"] ?? "idle";
      frameIndex = 0;
      frameAccumMs = 0;
    }
  }
  if (homeGlide) {
    const speed = 480; // px/s
    const dx = homeGlide.targetX - springPos.x;
    const dy = homeGlide.targetY - springPos.y;
    const dist = Math.hypot(dx, dy);
    if (dist < 2 || ts >= homeGlide.deadline || stepInterrupted) {
      const id = homeGlide.id;
      homeGlide = null;
      host.ackStep(id, { kind: stepInterrupted ? "interrupted" : "completed" });
      currentAnim = MOTION_TO_ANIMATION[status?.motion ?? "idle"] ?? "idle";
    } else {
      const stepPx = Math.min(dist, (speed * dtMs) / 1000);
      springPos = { x: springPos.x + (dx / dist) * stepPx, y: springPos.y + (dy / dist) * stepPx };
      springTarget = { ...springPos };
      flip = dx < 0;
      host.move(Math.round(springPos.x), Math.round(springPos.y));
    }
  }
  // 逐帧步进（manifest durationMs 驱动）
  const entry = spriteManifestEntry(currentAnim);
  frameAccumMs += dtMs;
  while (frameAccumMs >= entry.frames[frameIndex]!.durationMs) {
    frameAccumMs -= entry.frames[frameIndex]!.durationMs;
    if (entry.loop) {
      frameIndex = (frameIndex + 1) % entry.frames.length;
    } else if (frameIndex < entry.frames.length - 1) {
      frameIndex += 1;
    } else {
      // once 动画停在末帧；无宏步在播则回状态映射动画（success→celebrate 播完收口）。
      frameAccumMs = 0;
      if (!stepPlayback && !homeGlide) {
        currentAnim = MOTION_TO_ANIMATION[status?.motion ?? "idle"] ?? "idle";
        frameIndex = 0;
      }
      break;
    }
  }
}

function advanceDragSpring(): void {
  if (!dragging) return;
  // 弹簧跟随（B20 拖拽弹簧语义）。
  const k = 0.35;
  springPos = {
    x: springPos.x + (springTarget.x - springPos.x) * k,
    y: springPos.y + (springTarget.y - springPos.y) * k,
  };
  host.move(Math.round(springPos.x), Math.round(springPos.y));
}

function advanceFlight(dtMs: number): void {
  if (!flight || !flightBounds) return;
  const next = stepFlight(flight, dtMs, flightBounds, { ceilingBounce: true });
  flight = next;
  host.move(Math.round(next.x), Math.round(next.y));
  if (next.grounded && next.vx === 0 && next.vy === 0) {
    flight = null;
    flightBounds = null;
    host.requestClamp(); // 静止后夹回工作区（B23）
    host.move(Math.round(next.x), Math.round(next.y));
  }
}

function draw(): void {
  ctx!.clearRect(0, 0, window.innerWidth, window.innerHeight);
  if (!status) return;
  const body = status.geometry.body;
  const drawSize = PET_SPRITE_MANIFEST.cellHeight / PET_SPRITE_MANIFEST.cellWidth;
  const width = body.width;
  const height = width * drawSize;
  const dx = body.x + (body.width - width) / 2;
  const dy = body.y + body.height - height;
  paintSpriteFrame(ctx!, currentAnim, frameIndex, dx, dy, flip);
}

// ── 启动 ─────────────────────────────────────────────────────────────────

try {
  host.onStatus(applyStatus);
  host.onWorkAreas((areas) => {
    workAreas = areas;
  });
  host.onStep(playStep);
  host.onInterrupt(() => {
    stepInterrupted = true;
    if (stepPlayback && !stepPlayback.done) {
      const id = stepPlayback.id;
      stepPlayback = null;
      host.ackStep(id, { kind: "interrupted" });
      currentAnim = MOTION_TO_ANIMATION[status?.motion ?? "idle"] ?? "idle";
      frameIndex = 0;
      frameAccumMs = 0;
    }
    if (homeGlide) {
      const gid = homeGlide.id;
      homeGlide = null;
      host.ackStep(gid, { kind: "interrupted" });
      currentAnim = MOTION_TO_ANIMATION[status?.motion ?? "idle"] ?? "idle";
    }
  });
  window.addEventListener("resize", resizeCanvas);
  // 状态→动画映射（success once 播完回 idle 由 advanceAnimation 收口）。
  void host.getWorkAreas().then((areas) => {
    workAreas = areas;
    host.ready();
  });
  window.requestAnimationFrame(tick);
} catch (error) {
  showFatal(error instanceof Error ? error.message : String(error));
}
