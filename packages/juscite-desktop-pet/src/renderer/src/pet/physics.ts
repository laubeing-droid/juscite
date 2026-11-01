// 功能 #28 桌宠 · 抛射物理纯函数（RE-28 §3.3；对拍 21，B21 参数全套随代码钉死）。
// 松手估速=最近 150ms 窗口、端点均速×0.5+分段峰值×0.5、末段加速增益 ≤+60%
// （8000px/s² 给满）、指数软限速 3600、<500px/s 不甩；飞行=重力积分（dt≤50ms）、
// 左右墙/天花板（可关）反弹 restitution、落地 Q 弹（力度=积分前撞击速度）、
// 地面摩擦、静止阈值。无 DOM 依赖，合成自测直跑。

export const THROW_ESTIMATE_WINDOW_MS = 150;
export const THROW_ENDPOINT_WEIGHT = 0.5;
export const THROW_PEAK_WEIGHT = 0.5;
export const THROW_ACCEL_PX_S2 = 8_000;
export const THROW_ACCEL_GAIN_MAX = 0.6;
export const THROW_SOFT_SPEED_LIMIT_PX_S = 3_600;
export const THROW_MIN_SPEED_PX_S = 500;
export const FLIGHT_MAX_DT_MS = 50;
export const FLIGHT_GRAVITY_PX_S2 = 3_000;
/** 墙/地反弹恢复系数；天花板反弹可关（ceilingBounce=false 则贴住）。 */
export const FLIGHT_RESTITUTION = 0.5;
export const GROUND_FRICTION_PER_S = 3.5;
export const REST_SPEED_THRESHOLD_PX_S = 40;

export interface VelocitySample {
  t: number;
  x: number;
  y: number;
}

export interface VelocityVector {
  vx: number;
  vy: number;
}

/** 松手估速：取最近 windowMs 样本；端点均速×0.5 + 分段峰值×0.5；末段加速增益（≤+60%）。 */
export function estimateThrowVelocity(
  samples: VelocitySample[],
  nowMs: number,
  windowMs: number = THROW_ESTIMATE_WINDOW_MS,
): VelocityVector {
  const recent = samples.filter((s) => nowMs - s.t <= windowMs);
  if (recent.length < 2) return { vx: 0, vy: 0 };
  const first = recent[0]!;
  const last = recent[recent.length - 1]!;
  const dt = (last.t - first.t) / 1000;
  if (dt <= 0) return { vx: 0, vy: 0 };
  const endpoint = { vx: (last.x - first.x) / dt, vy: (last.y - first.y) / dt };
  // 分段峰值：相邻样本段速度的最大模长。
  let peak = 0;
  let peakVx = 0;
  let peakVy = 0;
  for (let i = 1; i < recent.length; i += 1) {
    const a = recent[i - 1]!;
    const b = recent[i]!;
    const segDt = (b.t - a.t) / 1000;
    if (segDt <= 0) continue;
    const vx = (b.x - a.x) / segDt;
    const vy = (b.y - a.y) / segDt;
    const speed = Math.hypot(vx, vy);
    if (speed > peak) {
      peak = speed;
      peakVx = vx;
      peakVy = vy;
    }
  }
  // 末段加速增益：速度方向与末段同向、随末段加速度线性给满（≤+60%）。
  const tailFirst = recent[Math.max(0, recent.length - 3)]!;
  const tailDt = (last.t - tailFirst.t) / 1000;
  const endSpeed = Math.hypot(endpoint.vx, endpoint.vy);
  let gain = 0;
  if (tailDt > 0) {
    const tailVx = (last.x - tailFirst.x) / tailDt;
    const tailVy = (last.y - tailFirst.y) / tailDt;
    const tailSpeed = Math.hypot(tailVx, tailVy);
    if (tailSpeed > 0 && endSpeed > 0) {
      const accel = (endSpeed - tailSpeed) / tailDt;
      const aligned =
        (tailVx * endpoint.vx + tailVy * endpoint.vy) / (tailSpeed * endSpeed || 1) > 0;
      gain = aligned ? Math.min(THROW_ACCEL_GAIN_MAX, Math.max(0, accel / THROW_ACCEL_PX_S2)) : 0;
    }
  }
  const blended = {
    vx: endpoint.vx * THROW_ENDPOINT_WEIGHT + peakVx * THROW_PEAK_WEIGHT,
    vy: endpoint.vy * THROW_ENDPOINT_WEIGHT + peakVy * THROW_PEAK_WEIGHT,
  };
  const boosted = { vx: blended.vx * (1 + gain), vy: blended.vy * (1 + gain) };
  return applySoftSpeedLimit(boosted);
}

/** 指数软限速：超 3600 px/s 的部分按 exp 衰减，不硬截断。 */
export function applySoftSpeedLimit(v: VelocityVector): VelocityVector {
  const speed = Math.hypot(v.vx, v.vy);
  if (speed <= THROW_SOFT_SPEED_LIMIT_PX_S || speed === 0) return v;
  const overshoot = speed - THROW_SOFT_SPEED_LIMIT_PX_S;
  const damped = THROW_SOFT_SPEED_LIMIT_PX_S + overshoot * Math.exp(-overshoot / THROW_SOFT_SPEED_LIMIT_PX_S);
  const scale = damped / speed;
  return { vx: v.vx * scale, vy: v.vy * scale };
}

export interface FlightState {
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** 落地 Q 弹用的最近撞击速度（积分前）。 */
  lastImpactSpeed: number;
  grounded: boolean;
}

/** 飞行舞台=本体可动范围（调用方已把本体宽高从 right/bottom 预留掉）。 */
export interface FlightBounds {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export interface FlightOptions {
  ceilingBounce: boolean;
}

/** 一帧积分：重力、边界反弹（左右墙/天花板可关/地面）、地面摩擦、静止阈值。 */
export function stepFlight(
  state: FlightState,
  dtMs: number,
  bounds: FlightBounds,
  options: FlightOptions,
): FlightState {
  const dt = Math.min(dtMs, FLIGHT_MAX_DT_MS) / 1000;
  const vyPre = state.vy + FLIGHT_GRAVITY_PX_S2 * dt;
  const impactSpeed = Math.hypot(state.vx, vyPre);
  let { x, y, vx } = state;
  let vy = vyPre;
  x += vx * dt;
  y += vy * dt;
  // 左右墙反弹
  if (x < bounds.left) {
    x = bounds.left;
    vx = Math.abs(vx) * FLIGHT_RESTITUTION;
  } else if (x > bounds.right) {
    x = bounds.right;
    vx = -Math.abs(vx) * FLIGHT_RESTITUTION;
  }
  // 天花板反弹（可关：关=贴住不下穿也不弹）
  if (y < bounds.top) {
    y = bounds.top;
    if (options.ceilingBounce) vy = Math.abs(vy) * FLIGHT_RESTITUTION;
    else vy = 0;
  }
  // 地面
  let grounded = false;
  if (y >= bounds.bottom) {
    y = bounds.bottom;
    grounded = true;
    // 落地 Q 弹：反弹力度=积分前撞击速度的竖直分量。
    vy = Math.abs(vyPre) > FLIGHT_GRAVITY_PX_S2 * dt ? -Math.abs(vyPre) * FLIGHT_RESTITUTION * 0.6 : 0;
    if (Math.abs(vy) < REST_SPEED_THRESHOLD_PX_S) vy = 0;
    // 地面摩擦
    vx = vx * Math.exp(-GROUND_FRICTION_PER_S * dt);
    if (Math.abs(vx) < REST_SPEED_THRESHOLD_PX_S) vx = 0;
  }
  const speed = Math.hypot(vx, vy);
  if (grounded && speed === 0) {
    return { x, y, vx: 0, vy: 0, lastImpactSpeed: impactSpeed, grounded: true };
  }
  return { x, y, vx, vy, lastImpactSpeed: impactSpeed, grounded };
}

/** 抛射判定：<500px/s 不甩（对拍 21）。 */
export function isThrowable(v: VelocityVector): boolean {
  return Math.hypot(v.vx, v.vy) >= THROW_MIN_SPEED_PX_S;
}
