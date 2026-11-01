// 功能 #28 桌宠 · 自绘精灵与逐帧清单（RE-28 §3.1 动画清单）。
// 表达隔离：素材全部程序化自绘（不复制任何竞品雪碧图/视频资产）；
// 播放机制=manifest 逐帧 durationMs 驱动（对拍 29），格 192×208、表 8 行。
// 帧时长设计与宏 clip 同和（thinking 2420 / working 1840 / awaitApproval 2540 /
// celebrate 1720 / sad 2400 / curious 2880 / explain 1940），回环恰落在 clip 边界。

export const PET_SPRITE_CELL_WIDTH = 192;
export const PET_SPRITE_CELL_HEIGHT = 208;

export type SpriteAnimationName =
  | "idle"
  | "thinking"
  | "working"
  | "approval"
  | "celebrate"
  | "sad"
  | "curious"
  | "explain";

export interface SpriteFrame {
  index: number;
  durationMs: number;
}

export interface SpriteManifestEntry {
  name: SpriteAnimationName;
  row: number;
  frames: SpriteFrame[];
  loop: boolean;
}

export interface SpriteManifest {
  cellWidth: number;
  cellHeight: number;
  animations: SpriteManifestEntry[];
}

function frames(count: number, durations: number[]): SpriteFrame[] {
  const list: SpriteFrame[] = [];
  for (let i = 0; i < count; i += 1) {
    list.push({ index: i, durationMs: durations[i % durations.length]! });
  }
  return list;
}

/** 行序=动画清单序（§3.1：8 动画钉死；移动复用 explain 帧位）。 */
export const PET_SPRITE_MANIFEST: SpriteManifest = {
  cellWidth: PET_SPRITE_CELL_WIDTH,
  cellHeight: PET_SPRITE_CELL_HEIGHT,
  animations: [
    { name: "idle", row: 0, frames: frames(4, [420, 420, 420, 420]), loop: true },
    // clip 2420 = 400+400+410+400+400+410
    { name: "thinking", row: 1, frames: frames(6, [400, 400, 410, 400, 400, 410]), loop: true },
    // clip 1840 = 300+310+300+310+310+310
    { name: "working", row: 2, frames: frames(6, [300, 310, 300, 310, 310, 310]), loop: true },
    // clip 2540 = 630+640+630+640
    { name: "approval", row: 3, frames: frames(4, [630, 640, 630, 640]), loop: true },
    // once 1720 = 280+280+290+280+290+300
    { name: "celebrate", row: 4, frames: frames(6, [280, 280, 290, 280, 290, 300]), loop: false },
    // clip 2400 = 600×4
    { name: "sad", row: 5, frames: frames(4, [600, 600, 600, 600]), loop: true },
    // once 2880 = 470+480+470+480+490+490
    { name: "curious", row: 6, frames: frames(6, [470, 480, 470, 480, 490, 490]), loop: false },
    // clip 1940 = 320+320+330+320+330+320（移动/回家复用本行）
    { name: "explain", row: 7, frames: frames(6, [320, 320, 330, 320, 330, 320]), loop: true },
  ],
};

export function spriteManifestEntry(name: SpriteAnimationName): SpriteManifestEntry {
  const entry = PET_SPRITE_MANIFEST.animations.find((a) => a.name === name);
  if (!entry) throw new Error(`pet sprite manifest missing animation: ${name}`);
  return entry;
}

// ── 程序化绘制（自绘团子：耳·身·脸·道具按帧相位变化）────────────────────────

interface PaintContext {
  ctx: CanvasRenderingContext2D;
  frameIndex: number;
  frameCount: number;
}

function phase(frameIndex: number, frameCount: number): number {
  return frameCount <= 1 ? 0 : (Math.PI * 2 * frameIndex) / frameCount;
}

function drawBody(p: PaintContext, opts: { squash: number; tilt: number; offsetX: number; offsetY: number }): void {
  const { ctx } = p;
  const cx = PET_SPRITE_CELL_WIDTH / 2 + opts.offsetX;
  const by = PET_SPRITE_CELL_HEIGHT - 30 + opts.offsetY; // 身底基线
  const bodyRx = 56 * (1 + opts.squash * 0.18);
  const bodyRy = 52 * (1 - opts.squash * 0.22);
  ctx.save();
  ctx.translate(cx, by);
  ctx.rotate(opts.tilt);
  // 身体
  ctx.fillStyle = "#e8b96b";
  ctx.beginPath();
  ctx.ellipse(0, -bodyRy, bodyRx, bodyRy, 0, 0, Math.PI * 2);
  ctx.fill();
  // 耳朵（sad 时下垂）
  ctx.fillStyle = "#d9a752";
  const earDroop = p.frameIndex >= 0 && opts.squash > 0.6 ? 10 : 0;
  ctx.beginPath();
  ctx.ellipse(-bodyRx * 0.55, -bodyRy * 1.55 + earDroop, 14, 18, -0.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(bodyRx * 0.55, -bodyRy * 1.55 + earDroop, 14, 18, 0.3, 0, Math.PI * 2);
  ctx.fill();
  // 内耳
  ctx.fillStyle = "#f4d9a8";
  ctx.beginPath();
  ctx.ellipse(-bodyRx * 0.55, -bodyRy * 1.5 + earDroop, 7, 10, -0.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(bodyRx * 0.55, -bodyRy * 1.5 + earDroop, 7, 10, 0.3, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawFace(p: PaintContext, mood: "calm" | "happy" | "sad" | "curious" | "focus"): void {
  const { ctx } = p;
  const cx = PET_SPRITE_CELL_WIDTH / 2;
  const by = PET_SPRITE_CELL_HEIGHT - 30;
  const eyeY = by - 66;
  ctx.fillStyle = "#3a2a14";
  const blink = mood === "calm" && p.frameIndex === p.frameCount - 1;
  for (const ex of [cx - 20, cx + 20]) {
    ctx.beginPath();
    if (blink || mood === "happy") {
      ctx.lineWidth = 3;
      ctx.strokeStyle = "#3a2a14";
      ctx.arc(ex, eyeY, 5, Math.PI, 0);
      ctx.stroke();
    } else if (mood === "sad") {
      ctx.lineWidth = 3;
      ctx.strokeStyle = "#3a2a14";
      ctx.arc(ex, eyeY + 3, 5, Math.PI * 1.15, Math.PI * 1.85);
      ctx.stroke();
    } else {
      ctx.ellipse(ex, eyeY, 4, 5.5, 0, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  // 嘴
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = "#3a2a14";
  ctx.beginPath();
  if (mood === "happy") ctx.arc(cx, eyeY + 14, 7, 0.15 * Math.PI, 0.85 * Math.PI);
  else if (mood === "sad") ctx.arc(cx, eyeY + 22, 7, 1.15 * Math.PI, 1.85 * Math.PI);
  else if (mood === "curious") ctx.arc(cx + 3, eyeY + 13, 4, 0, Math.PI);
  else ctx.arc(cx, eyeY + 13, 4, 0.1 * Math.PI, 0.9 * Math.PI);
  ctx.stroke();
  // 腮红
  ctx.fillStyle = "rgba(224, 122, 95, 0.55)";
  ctx.beginPath();
  ctx.ellipse(cx - 32, eyeY + 12, 6, 4, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(cx + 32, eyeY + 12, 6, 4, 0, 0, Math.PI * 2);
  ctx.fill();
}

function drawProp(p: PaintContext, name: SpriteAnimationName): void {
  const { ctx } = p;
  const cx = PET_SPRITE_CELL_WIDTH / 2;
  const wobble = Math.sin(phase(p.frameIndex, p.frameCount)) * 4;
  ctx.save();
  ctx.lineWidth = 3;
  switch (name) {
    case "thinking": {
      // 头顶思考泡：三点随帧浮现
      ctx.fillStyle = "rgba(255,255,255,0.92)";
      const shown = 1 + (p.frameIndex % 3);
      const baseY = 52;
      for (let i = 0; i < shown; i += 1) {
        const r = 4 + i * 3;
        ctx.beginPath();
        ctx.arc(cx + 26 + i * 11, baseY - i * 9, r, 0, Math.PI * 2);
        ctx.fill();
      }
      break;
    }
    case "working": {
      // 手边小扳手左右敲击
      ctx.strokeStyle = "#8a8f98";
      ctx.translate(cx + 52, 118 + wobble);
      ctx.rotate(-0.6 + wobble * 0.04);
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(0, -34);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(0, -40, 8, 0.4, Math.PI * 1.6);
      ctx.stroke();
      break;
    }
    case "approval": {
      // 头顶"!"气泡
      ctx.fillStyle = "rgba(255,255,255,0.94)";
      ctx.beginPath();
      ctx.roundRect(cx - 16, 30, 32, 40, 8);
      ctx.fill();
      ctx.fillStyle = "#b45309";
      ctx.font = "bold 30px 'Segoe UI', sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("!", cx, 61);
      break;
    }
    case "celebrate": {
      // 彩带碎屑（每帧不同相位）
      const colors = ["#e05a4e", "#3f7fce", "#3fa34d", "#e0a23f"];
      for (let i = 0; i < 10; i += 1) {
        const a = phase(i, 10) + phase(p.frameIndex, p.frameCount);
        const x = cx + Math.cos(a) * (58 + (i % 3) * 10);
        const y = 70 + Math.sin(a * 1.7) * 34;
        ctx.fillStyle = colors[i % colors.length]!;
        ctx.fillRect(x, y, 5, 9);
      }
      break;
    }
    case "sad": {
      // 头顶雨云一滴
      ctx.fillStyle = "rgba(120, 130, 145, 0.8)";
      ctx.beginPath();
      ctx.ellipse(cx + 34, 44, 20, 12, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#5b8ecb";
      const dropY = 60 + ((p.frameIndex * 9) % 40);
      ctx.beginPath();
      ctx.ellipse(cx + 34, dropY, 3, 6, 0, 0, Math.PI * 2);
      ctx.fill();
      break;
    }
    case "curious": {
      // 头顶"?"随帧摆动
      ctx.fillStyle = "rgba(255,255,255,0.94)";
      ctx.beginPath();
      ctx.roundRect(cx + 18, 26, 30, 38, 8);
      ctx.fill();
      ctx.fillStyle = "#3f6fce";
      ctx.font = "bold 28px 'Segoe UI', sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("?", cx + 33, 55 + wobble * 0.6);
      break;
    }
    case "explain": {
      // 身侧话线（移动/讲解复用帧位）
      ctx.strokeStyle = "rgba(255,255,255,0.85)";
      for (let i = 0; i < 3; i += 1) {
        ctx.beginPath();
        ctx.moveTo(cx + 62, 84 + i * 12);
        ctx.lineTo(cx + 62 + 14 - i * 4, 84 + i * 12);
        ctx.stroke();
      }
      break;
    }
    case "idle":
    default:
      break;
  }
  ctx.restore();
}

/** 画第 frameIndex 帧到目标 2D 上下文的 (dx,dy) 处（格 192×208）。 */
export function paintSpriteFrame(
  ctx: CanvasRenderingContext2D,
  name: SpriteAnimationName,
  frameIndex: number,
  dx: number,
  dy: number,
  flip: boolean,
): void {
  const entry = spriteManifestEntry(name);
  const count = entry.frames.length;
  const index = ((frameIndex % count) + count) % count;
  ctx.save();
  ctx.translate(dx + PET_SPRITE_CELL_WIDTH / 2, dy);
  if (flip) ctx.scale(-1, 1);
  ctx.translate(-PET_SPRITE_CELL_WIDTH / 2, 0);
  const paint: PaintContext = { ctx, frameIndex: index, frameCount: count };
  const mood: Record<SpriteAnimationName, "calm" | "happy" | "sad" | "curious" | "focus"> = {
    idle: "calm",
    thinking: "focus",
    working: "focus",
    approval: "curious",
    celebrate: "happy",
    sad: "sad",
    curious: "curious",
    explain: "calm",
  };
  const squash = name === "idle" ? Math.abs(Math.sin(phase(index, count))) * 0.12 : 0;
  const tilt = name === "sad" ? 0.1 : name === "curious" ? 0.14 * Math.sin(phase(index, count)) : 0;
  drawBody(paint, { squash, tilt, offsetX: 0, offsetY: 0 });
  drawFace(paint, mood[name]);
  drawProp(paint, name);
  ctx.restore();
}
