// 功能 #28 桌宠 · 几何常量单源（RE-28 §3.3「DPI/几何唯一出口」）。
// 教训对齐 dsh issue #308（B2/B27）：窗口几何常量若在宿主与渲染层两处各写一份，
// 缩放必打架。本文件是桌宠宽高公式的唯一出处；渲染层不自带常量，
// 一律经 pet://status 载荷从主进程取（见 store.ts 广播的 geometry 字段）。
// 数值语义（对拍 24）：基准宽 220 / 左右留白 32 / 顶 72 + 底 10 = 82 / 最小宽 420 /
// 画布比 9:16 / 大小 50..200 步进 5 默认 100。

export const PET_BASE_WIDTH = 220;
export const PET_WINDOW_PAD_X = 32;
export const PET_WINDOW_TOP_PAD = 72;
export const PET_WINDOW_BOTTOM_PAD = 10;
export const PET_WINDOW_MIN_WIDTH = 420;
export const PET_BUILTIN_ASPECT = 9 / 16; // 宽:高 = 9:16（v1 单皮肤，无 codex 图集画布）
export const PET_SIZE_MIN_PERCENT = 50;
export const PET_SIZE_MAX_PERCENT = 200;
export const PET_SIZE_DEFAULT_PERCENT = 100;
export const PET_SIZE_STEP = 5;

export interface PetSize {
  width: number;
  height: number;
}

/** 大小百分比钳位到 50..200 内的 5 的倍数（滑条步进同源）。 */
export function clampSizePercent(value: number): number {
  if (!Number.isFinite(value)) return PET_SIZE_DEFAULT_PERCENT;
  const stepped = Math.round(value / PET_SIZE_STEP) * PET_SIZE_STEP;
  return Math.min(PET_SIZE_MAX_PERCENT, Math.max(PET_SIZE_MIN_PERCENT, stepped));
}

/** 宠物本体宽（像素）= 基准宽 × size%。 */
export function petBodyWidth(sizePercent: number): number {
  return (PET_BASE_WIDTH * clampSizePercent(sizePercent)) / 100;
}

/** 宠物本体高（像素）= 本体宽 ÷ 画布比。 */
export function petBodyHeight(sizePercent: number): number {
  return petBodyWidth(sizePercent) / PET_BUILTIN_ASPECT;
}

/** 窗口宽 = max(本体宽 + 左右留白, 最小宽)——加宽只向左扩透明区（对拍 24）。 */
export function petWindowWidth(sizePercent: number): number {
  return Math.max(petBodyWidth(sizePercent) + PET_WINDOW_PAD_X, PET_WINDOW_MIN_WIDTH);
}

/** 窗口高 = 本体高 + 顶 72 + 底 10（透明留白，宠物锚右下）。 */
export function petWindowHeight(sizePercent: number): number {
  return petBodyHeight(sizePercent) + PET_WINDOW_TOP_PAD + PET_WINDOW_BOTTOM_PAD;
}

/** 窗口逻辑尺寸（创建/setSize 唯一公式，对齐 B27 公式形状）。 */
export function petWindowLogicalSize(sizePercent: number): PetSize {
  return {
    width: petWindowWidth(sizePercent),
    height: petWindowHeight(sizePercent),
  };
}

export interface PetRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * 宠物本体命中箱（窗口内坐标）：透明留白可出屏、本体不出屏（B23）——
 * 命中箱=右下角锚定的本体矩形，非整窗。
 */
export function petBodyRect(windowSize: PetSize, sizePercent: number): PetRect {
  const width = petBodyWidth(sizePercent);
  const height = petBodyHeight(sizePercent);
  return {
    x: windowSize.width - width,
    y: windowSize.height - height,
    width,
    height,
  };
}
