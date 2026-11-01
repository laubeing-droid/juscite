// 对抗图几何反解（契约二：一切版面量由脚本从物理页尺寸反解得出；几何算法实现自写）。
// 版面不变量（版面 M/R/T/L 组的机验面）：
//   三栏等宽、恰好三栏、通道等宽、三栏+两通道+页边=总宽（误差为零，构造即整除）；
//   行组高=max(左栈,右栈,中轴需高)，中轴卡高=行组高；卡高与卡内每行基线出自同一函数；
//   抬头带与中缝虚线由同一反解确定；箭头绝对尺寸；多拐点走线带圆弧倒角。
// 单位=0.1mm；A4 横版 2970×2100。

export const GEO = {
  pageW: 2970, pageH: 2100,
  marginX: 150, marginTop: 120, marginBottom: 120,
  headerH: 170,           // 抬头带（案件名+成熟度+内部件声明）
  conclusionH: 110,       // 结论条（分散态写明共几处决定性）
  channelW: 135,          // 两道纵向通道
  colW: 800,              // 三栏等宽：3*800+2*135=2670=2970-2*150（构造即零误差）
  cardPadX: 40, cardPadTop: 36, cardPadBottom: 52, // 卡底留白≥卡顶留白（另量绝对值，不靠居中吸收）
  titleH: 64, titleGap: 18,
  lineH: 52, fontTitle: 34, fontBody: 30, fontMeta: 26,
  gapY: 56,               // 行间距
  slotGap: 28,            // 同侧两卡间距
  arrowW: 96, arrowH: 44, // 箭头绝对尺寸
  chamferR: 60,           // 多拐点走线圆弧倒角半径
} as const;

/** 三栏+两通道+页边=总宽（零误差断言数据源；守卫复算同式）。 */
export function columnXs(): { cols: [number, number, number]; channels: [number, number] } {
  const avail = GEO.pageW - 2 * GEO.marginX; // 2670
  const colW = Math.floor((avail - 2 * GEO.channelW) / 3); // 800
  if (colW * 3 + 2 * GEO.channelW !== avail) throw new Error("几何反解自相矛盾：三栏+通道+页边≠总宽");
  return {
    cols: [GEO.marginX, GEO.marginX + colW + GEO.channelW, GEO.marginX + 2 * (colW + GEO.channelW)],
    channels: [GEO.marginX + colW, GEO.marginX + 2 * colW + GEO.channelW],
  };
}

/** 文本行数：全角=字号宽、半角=0.55×（确定性估算，与守卫同函数）。 */
export function textWidth(text: string, fontSize: number): number {
  let w = 0;
  for (const ch of text) {
    const c = ch.codePointAt(0)!;
    const fullWidth = (c >= 0x2e80 && c <= 0x9fff) || (c >= 0x3000 && c <= 0x303f) || (c >= 0xf900 && c <= 0xfaff) || (c >= 0xff00 && c <= 0xff60) || (c >= 0xffe0 && c <= 0xffe6);
    w += fullWidth ? fontSize : fontSize * 0.55;
  }
  return w;
}

/** 折行（确定性：满列宽即折，不悬挂）。 */
export function wrapLines(text: string, fontSize: number, widthAvailable: number): string[] {
  const chars = [...text];
  const perLine = Math.max(1, Math.floor(widthAvailable / fontSize));
  const lines: string[] = [];
  for (let i = 0; i < chars.length; i += perLine) lines.push(chars.slice(i, i + perLine).join(""));
  return lines.length ? lines : [""];
}

/**
 * 卡片排版反解（卡高与卡内每行基线出自同一函数——改一处两边一起动）。
 * 返回自然高度（不拉伸）与逐行基线（相对卡顶）。
 */
export function cardLayout(bodyLines: string[], o: { title: string } ): { height: number; baselines: number[]; titleBaseline: number; bodyTop: number; bodyBottom: number } {
  const titleBaseline = GEO.cardPadTop + GEO.titleH * 0.72; // 标题贴卡顶（同一常量供守卫复算）
  const bodyTop = GEO.cardPadTop + GEO.titleH + GEO.titleGap;
  const baselines = bodyLines.map((_, i) => bodyTop + GEO.lineH * (i + 0.78));
  const bodyBottom = bodyTop + GEO.lineH * bodyLines.length;
  const height = bodyBottom + GEO.cardPadBottom;
  return { height, baselines, titleBaseline, bodyTop, bodyBottom };
}

export interface Rect { x: number; y: number; w: number; h: number }

/** 在给定卡高内排版（卡高与基线同一函数）：targetH≤0=自然高；拉伸时标题仍贴卡顶、正文纵向居中。 */
export function cardLayoutIn(bodyLines: string[], targetH: number): { height: number; baselines: number[]; titleBaseline: number; bodyTop: number; bodyBottom: number; shift: number } {
  const nat = cardLayout(bodyLines, { title: "" });
  if (targetH <= nat.height) return { ...nat, shift: 0 };
  const shift = (targetH - nat.height) / 2; // 正文整块下移居中；标题基线不动（贴卡顶一致性）
  return { ...nat, baselines: nat.baselines.map((b) => b + shift), height: targetH, shift };
}

/** 段（线段）×矩形 相交判定（Liang–Barsky 裁剪思想的自写实现：走线穿卡自证用）。 */
export function segIntersectsRect(x1: number, y1: number, x2: number, y2: number, r: Rect, pad = 0): boolean {
  const rx1 = r.x - pad, ry1 = r.y - pad, rx2 = r.x + r.w + pad, ry2 = r.y + r.h + pad;
  let t0 = 0, t1 = 1;
  const dx = x2 - x1, dy = y2 - y1;
  const clips: Array<[number, number]> = [[-dx, x1 - rx1], [dx, rx2 - x1], [-dy, y1 - ry1], [dy, ry2 - y1]];
  for (const [p, q] of clips) {
    if (p === 0) { if (q < 0) return false; continue; }
    const t = q / p;
    if (p < 0) { if (t > t1) return false; if (t > t0) t0 = t; }
    else { if (t < t0) return false; if (t < t1) t1 = t; }
  }
  return true; // [t0,t1]∩(0,1) 非空 ⇒ 线段进入矩形
}
