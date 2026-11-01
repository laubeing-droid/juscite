#!/usr/bin/env node
// 功能 #28 桌宠 · 合成自测（RE-28 §3/§4 行为面的纯逻辑闭环）。
// 全合成材料：内存对象+临时目录，零 %APPDATA% 触碰，零竞品资产，零 GUI 拉起。
// 覆盖：几何单源公式（对拍 24/33）/ PetConfig 持久化与 PetStatus 推导（§3.1）/
// 协议校验+准入串行与严格抢占+安全回家（对拍 8/9/10/11，A13-A16）/ 工具合同两态文本+
// 20s 超时降级+卡片回执（对拍 13/15，A20-A23）/ 八态投影与 A28 六词落点+终态收口（对拍
// 16/32）/ 气泡 seed 稳定轮选（对拍 18）/ 抛射物理全套参数（对拍 21，B21）/ 自绘素材
// manifest 逐帧清单与宏数值同和（对拍 7/29）。
// 运行：node --import tsx tools/bridge/pet_synthetic.mts（tsx 装载 desktop 包 TS 源）。
// 单命令 exit 0/1，末行 PET_SYNTH_PASS 可判。
import { mkdtempSync, existsSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dir = mkdtempSync(join(tmpdir(), "juscite-pet-synth-"));
let passed = 0;
let failed = 0;
function ok(n, msg) {
  passed += 1;
  console.log(`[pet-synth] ${n}: OK ${msg}`);
}
function fail(n, msg, detail) {
  failed += 1;
  console.error(`[pet-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`);
}
function eq(n, actual, expected, label) {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  if (a === b) ok(n, label);
  else fail(n, label, `expected=${b} actual=${a}`);
}

const { PET_BASE_WIDTH, PET_WINDOW_PAD_X, PET_WINDOW_MIN_WIDTH, petWindowLogicalSize, petBodyRect, clampSizePercent } =
  await import("../../packages/juscite-desktop-pet/src/main/desktop/pet/geometry.ts");
const { PET_MOTION_LABELS, PET_MACRO_CATALOG, petToolActivityLabel } = await import(
  "../../packages/juscite-desktop-pet/src/main/desktop/pet/motions.ts"
);
const { createPetStore, sanitizePetConfig } = await import(
  "../../packages/juscite-desktop-pet/src/main/desktop/pet/store.ts"
);
const {
  PetAdmissionController,
  validateSequenceInput,
  compileMacroSequence,
} = await import("../../packages/juscite-desktop-pet/src/main/desktop/pet/admission.ts");
const { createPetTool, PET_HOST_TIMEOUT_MS } = await import(
  "../../packages/juscite-desktop-pet/src/main/desktop/pet/tool.ts"
);
const { PetRunProjection, PET_SUCCESS_MOTION_MS, PET_TERMINAL_BUBBLE_MS } = await import(
  "../../packages/juscite-desktop-pet/src/main/desktop/pet/projection.ts"
);
const {
  PET_SPRITE_MANIFEST,
  spriteManifestEntry,
} = await import("../../packages/juscite-desktop-pet/src/renderer/src/pet/sprites.ts");
const {
  estimateThrowVelocity,
  stepFlight,
  isThrowable,
  applySoftSpeedLimit,
  THROW_SOFT_SPEED_LIMIT_PX_S,
  THROW_MIN_SPEED_PX_S,
  FLIGHT_MAX_DT_MS,
  FLIGHT_RESTITUTION,
} = await import("../../packages/juscite-desktop-pet/src/renderer/src/pet/physics.ts");
const { bubbleTitle, pickStable, seedNumber, disconnectedBubble, terminalBubble } = await import(
  "../../packages/juscite-desktop-pet/src/renderer/src/pet/bubble.ts"
);

// ── 1. 几何单源（对拍 24/33；B2/B3/B27 公式形状）────────────────────────────
{
  const size100 = petWindowLogicalSize(100);
  // 宽 = max(220×1.0+32, 420) = 420；高 = 220×16/9 + 82
  eq(1, size100.width, 420, "窗口宽 100%=max(220+32,420)=420");
  const expectH = (PET_BASE_WIDTH * 16) / 9 / 1 + (72 + 10);
  eq(2, Math.abs(size100.height - expectH) < 1e-9, true, "窗口高 100%=本体高+82");
  const size50 = petWindowLogicalSize(50);
  eq(3, size50.width, 420, "窗口宽 50%=min 侧仍 420（最小宽门）");
  const size200 = petWindowLogicalSize(200);
  eq(4, size200.width, 440 + PET_WINDOW_PAD_X, "窗口宽 200%=440+32=472（左向扩展出口）");
  eq(5, clampSizePercent(173), 175, "大小钳位到 5 的倍数");
  eq(6, clampSizePercent(30), 50, "大小下界 50");
  eq(7, clampSizePercent(500), 200, "大小上界 200");
  const body = petBodyRect({ width: 472, height: size200.height }, 200);
  eq(8, body.x, 472 - 440, "本体命中箱右下锚定 x（透明留白在左）");
  eq(9, PET_WINDOW_MIN_WIDTH, 420, "常量单源：最小宽 420");
}

// ── 2. PetConfig 持久化 + PetStatus 推导（§3.1）────────────────────────────
{
  const file = join(dir, "desktop", "pet.json");
  const events = [];
  const store = createPetStore({ file, events: { onChange: (s) => events.push(s) } });
  const initial = store.getStatus();
  eq(10, initial.config, { enabled: true, alwaysOnTop: true, rememberPosition: true, sizePercent: 100, throwEnabled: false, activeSkin: "default" }, "默认配置=全开/100%/抛射关（对拍 2/21）");
  eq(11, initial.visible, true, "visible≡enabled（B6）");
  eq(12, existsSync(file), false, "文件缺失=默认不报错不落盘（A8 语义，惰性写）");
  store.update({ sizePercent: 150, enabled: false });
  const reread = createPetStore({ file, events: { onChange: () => {} } });
  eq(13, reread.getConfig(), { enabled: false, alwaysOnTop: true, rememberPosition: true, sizePercent: 150, throwEnabled: false, activeSkin: "default" }, "落盘回读一致");
  const raw = JSON.parse(readFileSync(file, "utf-8"));
  eq(14, sanitizePetConfig({ ...raw, junk: 1, sizePercent: 999 }).sizePercent, 200, "越界字段钳位+多余键丢弃");
  eq(15, initial.geometry.body.x, initial.geometry.window.width - 220, "几何载荷含本体命中箱（B23 共用一份）");
}

// ── 3. 协议校验（A13；对拍 8）──────────────────────────────────────────────
{
  const good = validateSequenceInput({ requestId: "REQ-1", priority: 10, steps: [{ kind: "playAction", animation: "thinking", playback: { kind: "loopForDuration", durationMs: 3000, clipMs: 2420 }, completionBehavior: "restoreIdle", timeoutMs: 60000 }] });
  eq(16, good.ok, true, "合法序列通过");
  eq(17, validateSequenceInput({ requestId: "x", priority: 10, steps: [1] }).ok, false, "requestId 小写开头被拒");
  eq(18, validateSequenceInput({ requestId: "REQ-2", priority: 101, steps: [{ kind: "moveByPath", path: [{ kind: "home" }], timeoutMs: 100 }] }).ok, false, "priority>100 被拒");
  eq(19, validateSequenceInput({ requestId: "REQ-3", priority: 10, steps: [] }).ok, false, "空 steps 被拒");
  eq(20, validateSequenceInput({ requestId: "REQ-4", priority: 10, steps: Array.from({ length: 17 }, () => ({ kind: "moveByPath", path: [{ kind: "home" }], timeoutMs: 100 })) }).ok, false, "steps>16 被拒");
  eq(21, validateSequenceInput({ requestId: "REQ-5", priority: 10, steps: [{ kind: "playAction", animation: "idle", playback: { kind: "once", durationMs: 100 }, completionBehavior: "restoreIdle", timeoutMs: 100 }] }).ok, false, "idle 动画不对外接单");
  eq(22, validateSequenceInput({ requestId: "REQ-6", priority: 10, steps: [{ kind: "playAction", animation: "sad", playback: { kind: "once", durationMs: 60001 }, completionBehavior: "restoreIdle", timeoutMs: 100 }] }).ok, false, "时长>60s 被拒");
  eq(23, validateSequenceInput({ requestId: "REQ-7", priority: 10, steps: [{ kind: "playAction", animation: "sad", playback: { kind: "once", durationMs: 100 }, completionBehavior: "loopForever", timeoutMs: 100 }] }).ok, false, "playAction 缺 restoreIdle 被拒");
  eq(24, validateSequenceInput({ requestId: "REQ-8", priority: 10, steps: [{ kind: "moveByPath", path: [{ kind: "away" }], timeoutMs: 100 }] }).ok, false, "moveByPath 仅允许 home");
}

// ── 4. 准入：串行/BUSY/严格抢占/安全回家（A15/A16；对拍 9/10/11）────────────
{
  // 手控时钟：schedule 收集回调，测试逐个放行。
  const scheduled = [];
  const schedule = (fn, ms) => {
    const entry = { fn, ms, cancelled: false };
    scheduled.push(entry);
    return () => {
      entry.cancelled = true;
    };
  };
  const flushTimers = () => {
    for (const e of scheduled.splice(0)) if (!e.cancelled) e.fn();
  };
  let stepResolver = null;
  let interrupted = 0;
  let available = true;
  const executor = {
    isAvailable: () => available,
    interruptCurrent: () => {
      interrupted += 1;
    },
    runStep: (step, ctx) =>
      new Promise((resolve) => {
        stepResolver = { resolve, ctx, step };
      }),
  };
  const admission = new PetAdmissionController({ executor, schedule });
  const r1 = admission.execute({ requestId: "A-1", priority: 10, steps: [{ kind: "playAction", animation: "thinking", playback: { kind: "loopForDuration", durationMs: 3000, clipMs: 2420 }, completionBehavior: "restoreIdle", timeoutMs: 60000 }] });
  eq(25, admission.isRunning, true, "无在跑即接（串行）");
  const r2 = admission.execute({ requestId: "A-2", priority: 10, steps: [{ kind: "moveByPath", path: [{ kind: "home" }], timeoutMs: 15000 }] });
  const r3 = admission.execute({ requestId: "A-3", priority: 50, steps: [{ kind: "moveByPath", path: [{ kind: "home" }], timeoutMs: 15000 }] });
  eq(26, (await r2).code, "PET_BUSY", "同优先级=BUSY（严格更高门）");
  eq(27, interrupted, 1, "更高优先级先打断当前步（fire-and-forget）");
  // 旧步被中断收口 → 旧序列 interrupted 回填 → 新序列开跑。
  stepResolver.resolve({ kind: "interrupted" });
  eq(28, (await r1).status, "interrupted", "旧序列收口=interrupted");
  eq(29, (await r1).reasonCode, "admission.preemptedByHigherPriorityPlan", "抢占 reasonCode 固定");
  eq(30, admission.isRunning, true, "抢占后新序列自动开跑");
  stepResolver.resolve({ kind: "completed" });
  eq(31, await r3, { status: "completed", completedSteps: 1 }, "新序列完成 completedSteps=1");
  // 步失败 → 自动安全回家（moveByPath home 15s）→ failed。
  available = false;
  const r4 = admission.execute({ requestId: "A-4", priority: 10, steps: [{ kind: "playAction", animation: "working", playback: { kind: "loopForDuration", durationMs: 3000, clipMs: 1840 }, completionBehavior: "restoreIdle", timeoutMs: 60000 }] });
  eq(32, (await r4).code, "PET_UNAVAILABLE", "渲染面不在=UNAVAILABLE");
  available = true;
  const r5 = admission.execute({ requestId: "A-5", priority: 10, steps: [{ kind: "playAction", animation: "working", playback: { kind: "loopForDuration", durationMs: 3000, clipMs: 1840 }, completionBehavior: "restoreIdle", timeoutMs: 60000 }] });
  stepResolver.resolve({ kind: "failed" });
  await new Promise((r) => setTimeout(r, 0)); // 排空微任务链：失败收口→安全回家步发起
  eq(33, stepResolver.step.kind, "moveByPath", "步失败→自动安全回家步");
  eq(34, stepResolver.step.timeoutMs, 15000, "安全回家超时=15s");
  stepResolver.resolve({ kind: "completed" });
  eq(35, (await r5).code, "PET_STEP_FAILED", "安全回家后返回 STEP_FAILED");
  // 步守卫超时：timeoutMs+1000。
  const r6 = admission.execute({ requestId: "A-6", priority: 10, steps: [{ kind: "playAction", animation: "explain", playback: { kind: "loopForDuration", durationMs: 3000, clipMs: 1940 }, completionBehavior: "restoreIdle", timeoutMs: 500 }] });
  eq(36, scheduled.some((e) => e.ms === 1500), true, "步守卫=timeoutMs+1000");
  flushTimers();
  await new Promise((r) => setTimeout(r, 0)); // 排空：守卫超时收口→安全回家步发起
  flushTimers(); // 安全回家守卫（16s 档）同步放行
  eq(37, (await r6).code, "PET_STEP_FAILED", "守卫超时收口为步失败");
}

// ── 5. AI 工具合同（A20-A23；对拍 13/15）──────────────────────────────────
{
  const seqQueue = [];
  const tool = createPetTool({
    executeSequence: (params) => {
      seqQueue.push(params);
      return new Promise(() => {});
    },
    schedule: (fn, ms) => {
      if (ms === PET_HOST_TIMEOUT_MS) fn(); // 立即触发=模拟 20s 超时
      return () => {};
    },
  });
  const invalid = await tool.execute({ macro: "dance" });
  eq(38, invalid.details.code, "VALIDATION_FAILED", "入参非法=VALIDATION_FAILED");
  eq(39, invalid.isError, false, "入参非法不抛错（isError=false）");
  const timeout = await tool.execute({ macro: "celebrate" });
  eq(40, timeout.details.code, "PET_UNAVAILABLE", "20s 超时降级 UNAVAILABLE");
  eq(41, timeout.text.includes("未完成"), true, "结果文本两态：未完成句");
  eq(42, timeout.details.card, { card: "pet", macro: "celebrate", status: "failed" }, "回执卡片形状");
  const macro = compileMacroSequence("thinking");
  eq(43, macro.priority, 10, "thinking 宏优先级 10");
  eq(44, macro.steps[0].playback, { kind: "loopForDuration", durationMs: 3000, clipMs: 2420 }, "thinking 宏时长/clip");
  const home = compileMacroSequence("returnHome");
  eq(45, home.steps[0].kind, "moveByPath", "returnHome=moveByPath([home])");
  eq(46, home.priority, 40, "returnHome 优先级 40");
  const done = createPetTool({
    executeSequence: async () => ({ status: "completed", completedSteps: 1 }),
    schedule: () => () => {},
  });
  const okResult = await done.execute({ macro: "curious" });
  eq(47, okResult.text, "桌宠动作完成：curious", "结果文本两态：完成句");
}

// ── 6. 八态投影 + A28 六词落点 + 终态收口（对拍 16/32）──────────────────────
{
  const motionsSeen = [];
  const bubblesSeen = [];
  const storeLike = {
    setMotion: (m) => motionsSeen.push(m),
    setBubble: (b) => bubblesSeen.push(b),
  };
  const timers = [];
  const projection = new PetRunProjection({
    store: storeLike,
    isBridgeAlive: () => bridgeAlive,
    schedule: (fn, ms) => {
      const entry = { fn, cancelled: false };
      timers.push(entry);
      return () => {
        entry.cancelled = true;
      };
    },
  });
  let bridgeAlive = true;
  projection.reportRunEvent({ kind: "running", sessionTitle: "借贷纠纷答辩" });
  eq(48, motionsSeen.at(-1), "working", "running→working 投影");
  eq(49, bubblesSeen.at(-1).body, "正在处理「借贷纠纷答辩」", "运行气泡带会话标题（B18 任务层）");
  projection.reportRunEvent({ kind: "pending" });
  eq(50, motionsSeen.at(-1), "awaitApproval", "pending→awaitApproval");
  projection.reportRunEvent({ kind: "terminal", outcome: "completed" });
  eq(51, motionsSeen.at(-1), "success", "终态 completed→success（celebrate）");
  eq(52, bubblesSeen.at(-1).ttlMs, PET_TERMINAL_BUBBLE_MS, "终态气泡 3s（B17）");
  timers.at(-1).fn();
  eq(53, motionsSeen.at(-1), "idle", "celebrate 收口回 idle");
  projection.reportRunEvent({ kind: "terminal", outcome: "error" });
  eq(54, motionsSeen.at(-1), "failed", "终态 error→failed（sad）");
  timers.at(-1).fn();
  projection.reportRunEvent({ kind: "terminal", outcome: "interrupted" });
  eq(55, motionsSeen.at(-1), "idle", "cancelled 动画直回 idle（自研补落点）");
  eq(56, bubblesSeen.at(-1).body, PET_MOTION_LABELS.cancelled, "取消气泡=运行已取消");
  bridgeAlive = false;
  projection.pollBridge();
  eq(57, motionsSeen.at(-1), "disconnected", "桥断=桌面端未连接态");
  bridgeAlive = true;
  projection.pollBridge();
  eq(58, motionsSeen.at(-1), "idle", "重连自动恢复");
  // A28 六词全落点（词表逐词）。
  const words = Object.values(PET_MOTION_LABELS);
  for (const word of ["待命中", "等待授权确认或提问", "刚完成一次运行", "运行已取消", "需要查看错误", "桌面端未连接"]) {
    if (!words.includes(word)) fail(59, `A28 词表缺词：${word}`);
  }
  ok(59, "A28 六词全落点+thinking/working 细分（八态超集）");
  eq(60, petToolActivityLabel("web_search"), "工具执行中（检索）", "工具活动分类词（B19 语义）");
  // 宏播放期运行投影不覆盖。
  projection.setSequenceActive(true);
  const mark = motionsSeen.length;
  projection.reportRunEvent({ kind: "running", sessionTitle: "x" });
  eq(61, motionsSeen.length, mark, "宏播放期运行投影不覆盖（准入优先）");
  projection.setSequenceActive(false);
}

// ── 7. 宏目录与素材 manifest（对拍 7/29）──────────────────────────────────
{
  const expect = {
    thinking: [3000, 2420, 10],
    working: [3000, 1840, 10],
    awaitApproval: [5000, 2540, 30],
    celebrate: [1720, null, 20],
    sad: [3000, 2400, 20],
    curious: [2880, null, 20],
    explain: [3000, 1940, 20],
    returnHome: [15000, null, 40],
  };
  let allOk = true;
  for (const [id, [duration, clip, priority]] of Object.entries(expect)) {
    const spec = PET_MACRO_CATALOG[id];
    if (spec.playback.durationMs !== duration || spec.priority !== priority) allOk = false;
    if (clip !== null && spec.playback.clipMs !== clip) allOk = false;
    if (clip === null && spec.playback.kind !== "once" && id !== "returnHome") allOk = false;
  }
  eq(62, allOk, true, "8 宏时长/clip/优先级逐格对齐（对拍 7）");
  eq(63, PET_SPRITE_MANIFEST.animations.length, 8, "manifest 恰 8 动画（8 行）");
  eq(64, PET_SPRITE_MANIFEST.cellWidth, 192, "格宽 192");
  eq(65, PET_SPRITE_MANIFEST.cellHeight, 208, "格高 208");
  // 帧时长设计与宏 clip 同和（回环恰落 clip 边界）。
  const clipOf = { thinking: 2420, working: 1840, approval: 2540, celebrate: 1720, sad: 2400, curious: 2880, explain: 1940 };
  let sumsOk = true;
  for (const [name, clip] of Object.entries(clipOf)) {
    const entry = spriteManifestEntry(name);
    const sum = entry.frames.reduce((acc, f) => acc + f.durationMs, 0);
    if (sum !== clip) sumsOk = false;
  }
  eq(66, sumsOk, true, "逐帧清单与宏 clip 同和（对拍 29 清单驱动）");
}

// ── 8. 抛射物理（B21 全套参数；对拍 21）────────────────────────────────────
{
  const now = 10_000;
  const samples = [
    { t: now - 150, x: 0, y: 0 },
    { t: now - 100, x: 60, y: -30 },
    { t: now - 50, x: 140, y: -80 },
    { t: now, x: 240, y: -150 },
  ];
  const v = estimateThrowVelocity(samples, now);
  eq(67, v.vx > 1500 && v.vy < -1000, true, "150ms 窗口端点估速成立");
  eq(68, isThrowable(v), true, "≥500px/s 可甩");
  eq(69, isThrowable({ vx: 100, vy: 0 }), false, "<500px/s 不甩");
  const capped = applySoftSpeedLimit({ vx: 6000, vy: 0 });
  eq(70, capped.vx < 6000 && capped.vx > THROW_SOFT_SPEED_LIMIT_PX_S, true, "指数软限速不硬截断");
  // 飞行：重力+地面反弹+静止。
  const bounds = { left: 0, right: 800, top: 0, bottom: 500 };
  let state = { x: 100, y: 0, vx: 600, vy: 0, lastImpactSpeed: 0, grounded: false };
  for (let i = 0; i < 2000 && !(state.grounded && state.vx === 0 && state.vy === 0); i += 1) {
    state = stepFlight(state, FLIGHT_MAX_DT_MS, bounds, { ceilingBounce: true });
  }
  eq(71, state.grounded && state.vx === 0 && state.vy === 0, true, "摩擦+静止阈值收敛落地静止");
  eq(72, state.x >= bounds.left && state.x <= bounds.right, true, "墙反弹不出台");
  // dt 钳位。
  const big = stepFlight({ x: 0, y: 0, vx: 0, vy: 0, lastImpactSpeed: 0, grounded: false }, 500, bounds, { ceilingBounce: true });
  eq(73, Math.abs(big.y - (FLIGHT_MAX_DT_MS / 1000) ** 2 * 3000) < 1e-9, true, "dt≤50ms 防穿墙");
  // 天花板反弹可关。
  const ceilOn = stepFlight({ x: 400, y: -10, vx: 0, vy: -100, lastImpactSpeed: 0, grounded: false }, 16, bounds, { ceilingBounce: true });
  eq(74, ceilOn.vy > 0, true, "天花板反弹（开）");
  const ceilOff = stepFlight({ x: 400, y: -10, vx: 0, vy: -100, lastImpactSpeed: 0, grounded: false }, 16, bounds, { ceilingBounce: false });
  eq(75, ceilOff.vy === 0, true, "天花板可关（贴住）");
  eq(76, FLIGHT_RESTITUTION > 0 && FLIGHT_RESTITUTION < 1, true, "restitution 随代码钉死");
}

// ── 9. 气泡词库 seed 稳定轮选（对拍 18）────────────────────────────────────
{
  const seed = seedNumber("session-abc");
  eq(77, pickStable(["甲", "乙", "丙"], seed), pickStable(["甲", "乙", "丙"], seed), "同 seed 恒选同句");
  eq(78, bubbleTitle("zh-CN", null), "新会话", "标题兜底：新会话");
  eq(79, bubbleTitle("en-US", "  "), "New session", "标题兜底（英）+空白串trim");
  eq(80, bubbleTitle("zh-CN", "借贷案"), "借贷案", "标题取会话 title");
  eq(81, disconnectedBubble("zh-CN").body.includes("桌面端未连接"), true, "断连气泡词（A28 落点）");
  eq(82, terminalBubble("zh-CN", seed, "completed").tone, "success", "成功气泡 tone");
  eq(83, terminalBubble("zh-CN", seed, "interrupted").body.includes("取消"), true, "取消气泡词");
}

// ── 10. 宏→准入接线（compileMacroSequence 直入 admission）──────────────────
{
  const executor = {
    isAvailable: () => true,
    interruptCurrent: () => {},
    runStep: async () => ({ kind: "completed" }),
  };
  const admission = new PetAdmissionController({ executor });
  const result = await admission.execute(compileMacroSequence("explain"));
  eq(84, result.status, "completed", "宏序列经准入全链执行完成");
}

if (failed > 0) {
  console.error(`[pet-synth] 汇总 ${passed} 过 / ${failed} 败`);
  console.error("PET_SYNTH_FAIL");
  rmSync(dir, { recursive: true, force: true });
  process.exit(1);
}
console.log(`[pet-synth] 汇总 ${passed} 过 / 0 败`);
console.log("PET_SYNTH_PASS");
rmSync(dir, { recursive: true, force: true });
process.exit(0);
