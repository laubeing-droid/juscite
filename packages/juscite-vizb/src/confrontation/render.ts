// 庭审对抗图渲染（图是表的渲染、表是唯一信息源；#19 深化·对抗视图交付形态）。
// 三栏对抗 SVG（A4 横版）＋17 列分析表（SpreadsheetML 2003）；全链确定性纯函数。
// 版面/走线/红块/图表一致/字段出口判据在 artifactGuards.ts 读产物核验，不查生成函数返回值。
// 几何要点：行组高=max(左栈,右栈,中轴需高)；中轴卡高=行组高；空段留位（每侧恒两卡位）但图上不立空框。

import { excelXmlProlog, ssCell, ssStyle, SS_NS, xmlEscape } from "../shared/xml.ts";
import { cardLayoutIn, columnXs, GEO, segIntersectsRect, wrapLines, type Rect } from "./geometry.ts";
import { decisiveOf, scatteredMode } from "./guards.ts";
import { isAbsentSegment, isPresentSegment, type ConfrontationSemantic, type Element, type Slot } from "./semantic.ts";
import { BURDEN_LABEL, BURDEN_OF, CLAIM_TYPES, DEFENSE_CATEGORY_LABEL, MATURITY_LABEL, stripUnverifiedMarker, type ClaimType, type DefenseCategory } from "./tables.ts";

export const DEEP_RED = "#8a1f1f"; // 深红唯一值（我方自选；数色块不数出现次数）
const INK = "#1f2937";
const MUTED = "#64748b";
const CARD_BG = "#ffffff";
const CARD_BORDER = "#94a3b8";
const LEFT_ACCENT = "#1d4ed8";  // 请求方侧
const RIGHT_ACCENT = "#b45309"; // 抗辩方侧（琥珀；非红系强调）
/** 图面封闭色板（版面判据：产物任何 fill 必须落在封闭色板内；深红在板内唯一）。 */
export const FIGURE_PALETTE: ReadonlySet<string> = new Set([
  DEEP_RED, "#ffffff", "#eef2f7", "#f8fafc", "#fcfcfd", INK, MUTED, CARD_BORDER,
  LEFT_ACCENT, RIGHT_ACCENT, "#cbd5e1", "#e2e8f0",
]);
const FONT_STACK = "'Noto Sans CJK SC','Source Han Sans SC','Microsoft YaHei',sans-serif"; // SVG 保留完整字族栈（光栅化前才换单一字族并日志报出）
const INTERNAL_NOTE = "内部推演件·不对法院出示·可含我方薄弱点与待补证";
const SLOT_RESERVE_MIN = 120; // 空段留位最小高（每侧恒两卡位；不画框）

// ══ 走线封闭模式（汇聚式封闭集，我方自拟 M1–M4；任何走线不得穿过非端点卡片与边标签）══
export type WireMode = "M1-direct" | "M2-elbow" | "M3-switchback" | "M4-arc";
export const WIRE_MODES: ReadonlySet<string> = new Set(["M1-direct", "M2-elbow", "M3-switchback", "M4-arc"]);

export interface Obstacle extends Rect { id: string; label?: string }
export interface WireSpec {
  mode: WireMode;
  fromId: string; toId: string;
  points: Array<[number, number]>; // 底层折线（圆弧倒角前；data-poly 同源进产物供自证）
  label: string; labelRect: Rect; labelId: string;
}

const SEG_PAD = 2;

function clearOf(pts: Array<[number, number]>, obstacles: Obstacle[], skipIds: Set<string>): boolean {
  for (let i = 0; i + 1 < pts.length; i++) {
    const [ax, ay] = pts[i]!;
    const [bx, by] = pts[i + 1]!;
    for (const o of obstacles) {
      if (skipIds.has(o.id)) continue;
      if (segIntersectsRect(ax, ay, bx, by, o, SEG_PAD)) return false;
    }
  }
  return true;
}

/** 走线选型：M1→M2(左道)→M2(右道)→M3→M4 依序取第一个全量避障通过者（确定性；模式封闭）。 */
export function routeWire(from: Rect, fromId: string, to: Rect, toId: string, obstacles: Obstacle[], label: string, labelId: string, laneOrdinal = 0): WireSpec {
  const skip = new Set([fromId, toId, labelId]);
  const x1 = from.x + from.w, y1 = from.y + from.h / 2; // 起卡右缘中点
  const x2 = to.x, y2 = to.y + to.h / 2;               // 终卡左缘中点
  const { channels } = columnXs();
  // 行界净空道：上道在抬头带内（lane 逐线错开，避开彼此边标签）；下道压在行间距中央
  const rowTop = Math.min(from.y, to.y);
  const rowBottom = Math.max(from.y + from.h, to.y + to.h);
  const laneUp = rowTop - 44 - laneOrdinal * 16;
  const laneDown = rowBottom + 24;
  const labelAbove = (cx: number, cy: number): Rect => ({ x: cx - 85, y: cy - 62, w: 170, h: 40 });
  const mk = (mode: WireMode, ptsRaw: Array<[number, number]>, labelRect: Rect): WireSpec => {
    const pts = ptsRaw.filter((p, i) => i === 0 || Math.abs(p[0] - ptsRaw[i - 1]![0]) > 0.5 || Math.abs(p[1] - ptsRaw[i - 1]![1]) > 0.5); // 去零长段
    return { mode, fromId, toId, points: pts, label, labelRect, labelId };
  };
  // M1 直连（仅当共线且全段避障）
  if (Math.abs(y1 - y2) < 0.5) {
    const pts: Array<[number, number]> = [[x1, y1], [x2, y2]];
    if (clearOf(pts, obstacles, skip)) return mk("M1-direct", pts, labelAbove((x1 + x2) / 2, y1));
  }
  // M2 单拐（拐点取通道中心：纵向段不擦卡缘）
  const c1 = channels[0]! + GEO.channelW / 2;
  const c2 = channels[1]! + GEO.channelW / 2;
  for (const xm of [c1, c2]) {
    const pts: Array<[number, number]> = [[x1, y1], [xm, y1], [xm, y2], [x2, y2]];
    if (clearOf(pts, obstacles, skip)) return mk("M2-elbow", pts, labelAbove(xm, (y1 + y2) / 2));
  }
  // M3 通道折返（双侧通道中心借行界净空道横穿：起卡右缘→左道纵向让位→净空道横穿→右道纵向对位→短横入终卡；
  // 末段横向入卡，不沿终卡边缘纵向擦行）
  for (const yc of [laneUp, laneDown]) {
    const pts: Array<[number, number]> = [[x1, y1], [c1, y1], [c1, yc], [c2, yc], [c2, y2], [x2, y2]];
    if (clearOf(pts, obstacles, skip)) return mk("M3-switchback", pts, labelAbove((x1 + x2) / 2, yc));
  }
  // M4 拱弧（二次曲线自整行上方跨越，采样折线自证；不避障即抛=fail-closed 拒绝出图）
  const cyTop = rowTop - 60 - laneOrdinal * 16;
  const arcPts: Array<[number, number]> = [];
  for (let t = 0; t <= 20; t++) {
    const u = t / 20;
    arcPts.push([(1 - u) * (1 - u) * x1 + 2 * (1 - u) * u * ((x1 + x2) / 2) + u * u * x2,
      (1 - u) * (1 - u) * y1 + 2 * (1 - u) * u * cyTop + u * u * y2]);
  }
  if (clearOf(arcPts, obstacles, skip)) return mk("M4-arc", arcPts, labelAbove((x1 + x2) / 2, cyTop + 44));
  throw new Error(`走线「${label}」四模式（M1–M4 封闭集）均无法避障，拒绝出图——请检查卡群密度或拆分板块`);
}

/** 全量走线×全量障碍自证（穿非端点卡片/压任何边标签即报；出图前必跑）。 */
export function wiresSelfCheck(wires: WireSpec[], obstacles: Obstacle[]): string[] {
  const errs: string[] = [];
  for (const w of wires) {
    const skip = new Set([w.fromId, w.toId, w.labelId]);
    for (let i = 0; i + 1 < w.points.length; i++) {
      const [ax, ay] = w.points[i]!;
      const [bx, by] = w.points[i + 1]!;
      for (const o of obstacles) {
        if (skip.has(o.id)) continue;
        if (segIntersectsRect(ax, ay, bx, by, o, SEG_PAD)) errs.push(`走线「${w.label}」第 ${i + 1} 段穿过${o.label ? `边标签「${o.label}」` : `非端点卡片 ${o.id}`}`);
      }
    }
  }
  return [...new Set(errs)];
}

// ══ 图渲染 ══
type CardKind = "center" | "claim" | "counter" | "response" | "second";
export interface CardBox { rect: Rect; el: Element; kind: CardKind; side: "center" | "left" | "right"; title: string; bodyLines: string[] }

export interface FigureModel {
  svg: string;
  rows: Array<{ elNo: string; rowH: number; centerH: number; leftStackH: number; rightStackH: number; leftSlots: number; rightSlots: number }>;
  cards: CardBox[];
  wires: WireSpec[];
  obstacles: Obstacle[];
  conclusion: { text: string; deepRed: boolean };
}

function slotBodyLines(s: Slot, title: string): string[] {
  if (!isPresentSegment(s)) return [];
  return [...wrapLines(s.text, GEO.fontBody, GEO.colW - 2 * GEO.cardPadX), `来源：${s.src}［${s.srcKind}］`];
}

/** 图模型（几何反解+走线自证；渲染与产物守卫同源复算）。 */
export function buildFigureModel(sem: ConfrontationSemantic): FigureModel {
  const { cols } = columnXs();
  const contentTop = GEO.marginTop + GEO.headerH;
  const contentBottom = GEO.pageH - GEO.marginBottom - GEO.conclusionH;
  const rows: FigureModel["rows"] = [];
  const cards: CardBox[] = [];
  let y = contentTop;
  for (const el of sem.elements) {
    const claimBody = slotBodyLines(el.claim, "主张");
    const counterBody = slotBodyLines(el.counter, "反制");
    const responseBody = slotBodyLines(el.response, "回应");
    const secondBody = slotBodyLines(el.second, "再回应");
    const claimH = cardLayoutIn(claimBody, 0).height;
    const counterH = counterBody.length ? cardLayoutIn(counterBody, 0).height : SLOT_RESERVE_MIN;
    const responseH = responseBody.length ? cardLayoutIn(responseBody, 0).height : SLOT_RESERVE_MIN;
    const secondH = secondBody.length ? cardLayoutIn(secondBody, 0).height : SLOT_RESERVE_MIN;
    const leftStackH = claimH + GEO.slotGap + counterH;   // 空段留位：每侧恒两卡位
    const rightStackH = responseH + GEO.slotGap + secondH;
    const centerTitle = `${el.no} ${el.issue}`;
    const centerBody = [
      ...wrapLines(`责任：${BURDEN_LABEL[el.burden]}`, GEO.fontBody, GEO.colW - 2 * GEO.cardPadX),
      ...wrapLines(`法信:${confLabel(el.lawConfidence)} 证信:${confLabel(el.evidenceConfidence)}`, GEO.fontBody, GEO.colW - 2 * GEO.cardPadX),
      ...wrapLines(`依据:${el.source}`, GEO.fontBody, GEO.colW - 2 * GEO.cardPadX),
      ...(decisiveOf(el) ? ["决定性要件（三判据同中）"] : []),
    ];
    const centerNeed = cardLayoutIn(centerBody, 0).height;
    const rowH = Math.max(leftStackH, rightStackH, centerNeed); // 行组高=三栈最大
    const centerRect: Rect = { x: cols[1]!, y, w: GEO.colW, h: rowH }; // 中轴卡高=行组高
    const claimRect: Rect = { x: cols[0]!, y, w: GEO.colW, h: claimH };
    const counterRect: Rect = { x: cols[0]!, y: y + claimH + GEO.slotGap, w: GEO.colW, h: counterH };
    const responseRect: Rect = { x: cols[2]!, y, w: GEO.colW, h: responseH };
    const secondRect: Rect = { x: cols[2]!, y: y + responseH + GEO.slotGap, w: GEO.colW, h: secondH };
    rows.push({ elNo: el.no, rowH, centerH: rowH, leftStackH, rightStackH, leftSlots: 2, rightSlots: 2 });
    cards.push({ rect: centerRect, el, kind: "center", side: "center", title: centerTitle, bodyLines: centerBody });
    cards.push({ rect: claimRect, el, kind: "claim", side: "left", title: "主张", bodyLines: claimBody });
    if (counterBody.length) cards.push({ rect: counterRect, el, kind: "counter", side: "left", title: "反制", bodyLines: counterBody });
    if (responseBody.length) cards.push({ rect: responseRect, el, kind: "response", side: "right", title: "回应", bodyLines: responseBody });
    if (secondBody.length) cards.push({ rect: secondRect, el, kind: "second", side: "right", title: "再回应", bodyLines: secondBody });
    y += rowH + GEO.gapY;
  }
  if (y - GEO.gapY > contentBottom) throw new Error(`行组超出 A4 页界（须拆板块；内容底=${Math.round(y - GEO.gapY)} 页底=${contentBottom}）`);
  const { scattered, decisiveCount } = scatteredMode(sem);
  const conclusionText = scattered
    ? `共 ${decisiveCount} 处决定性要件同中三判据——分散态：全图不作强调，判定如实全进分析表（代码不替律师挑前两个）`
    : decisiveCount > 0
      ? `决定性要件 ${sem.elements.filter((e) => decisiveOf(e)).map((e) => e.no).join("、")}（三判据同中；证明前景与排序由律师回填）`
      : "本板块无决定性要件（三判据未同时命中）";
  // 走线：卡片全量入障碍；走线定型后再把边标签入障碍做全量自证（标签自身避开所属走线）
  const obstacles: Obstacle[] = cards.map((c) => ({ x: c.rect.x, y: c.rect.y, w: c.rect.w, h: c.rect.h, id: `${c.kind}@${c.el.no}` }));
  const wires: WireSpec[] = [];
  const find = (no: string, kind: CardKind) => cards.find((c) => c.el.no === no && c.kind === kind);
  for (const el of sem.elements) {
    const claim = find(el.no, "claim");
    const response = find(el.no, "response");
    const counter = find(el.no, "counter");
    const second = find(el.no, "second");
    let lane = 0; // 同一要件的走线逐线错道（确定性）
    const mk = (from: CardBox, to: CardBox, label: string) => {
      const w = routeWire(from.rect, `${from.kind}@${el.no}`, to.rect, `${to.kind}@${el.no}`,
        [...obstacles, ...wires.map((x) => ({ ...x.labelRect, id: x.labelId, label: x.label }))], label, `label:${label}`, lane++);
      return w;
    };
    // 两轮对抗各一条走线：第一轮 主张→回应；第二轮 反制→再回应（位置已表关系，不添冗余线）
    if (claim && response) wires.push(mk(claim, response, `主张→回应 ${el.no}`));
    if (counter && second) wires.push(mk(counter, second, `反制→再回应 ${el.no}`));
  }
  const allObstacles: Obstacle[] = [...obstacles, ...wires.map((w) => ({ ...w.labelRect, id: w.labelId, label: w.label }))];
  const errs = wiresSelfCheck(wires, allObstacles);
  if (errs.length) throw new Error(`走线自证失败，拒绝出图：${errs[0]}`);
  const conclusion = { text: conclusionText, deepRed: !scattered && decisiveCount > 0 };
  return { svg: emitSvg(sem, rows, cards, wires, conclusion), rows, cards, wires, obstacles: allObstacles, conclusion };
}

function confLabel(c: string): string {
  return c === "high" ? "高" : c === "mid" ? "中" : "低";
}

function pathD(points: Array<[number, number]>): string {
  // 多拐点走线圆弧倒角：拐点前后各退 chamferR 以 Q 衔接；底层折线原样进 data-poly 供产物自证
  const R = GEO.chamferR;
  if (points.length < 3) return `M ${points[0]![0]} ${points[0]![1]} L ${points[points.length - 1]![0]} ${points[points.length - 1]![1]}`;
  let d = `M ${points[0]![0]} ${points[0]![1]}`;
  for (let i = 1; i + 1 < points.length; i++) {
    const [px, py] = points[i - 1]!;
    const [cx, cy] = points[i]!;
    const [nx, ny] = points[i + 1]!;
    const inLen = Math.hypot(cx - px, cy - py);
    const outLen = Math.hypot(nx - cx, ny - cy);
    const r = Math.min(R, inLen / 2, outLen / 2);
    d += ` L ${cx - (cx - px) / (inLen || 1) * r} ${cy - (cy - py) / (inLen || 1) * r}`
      + ` Q ${cx} ${cy} ${cx + (nx - cx) / (outLen || 1) * r} ${cy + (ny - cy) / (outLen || 1) * r}`;
  }
  const last = points[points.length - 1]!;
  return d + ` L ${last[0]} ${last[1]}`;
}

function emitSvg(sem: ConfrontationSemantic, rows: FigureModel["rows"], cards: CardBox[], wires: WireSpec[], conclusion: { text: string; deepRed: boolean }): string {
  const { cols, channels } = columnXs();
  const contentTop = GEO.marginTop + GEO.headerH;
  const contentBottom = GEO.pageH - GEO.marginBottom - GEO.conclusionH;
  const p: string[] = [];
  const { scattered } = scatteredMode(sem);
  p.push(`<rect x="0" y="0" width="${GEO.pageW}" height="${GEO.pageH}" fill="#ffffff"/>`);
  p.push(`<rect class="header-band" x="${GEO.marginX}" y="${GEO.marginTop}" width="${GEO.pageW - 2 * GEO.marginX}" height="${GEO.headerH}" fill="#eef2f7"/>`);
  p.push(`<text class="meta" x="${GEO.marginX + 30}" y="${GEO.marginTop + 92}" font-size="52" font-weight="700" fill="${INK}" font-family="${FONT_STACK}">${xmlEscape(`${sem.caseTitle}·庭审对抗图`)}</text>`);
  p.push(`<text class="meta" x="${GEO.marginX + 30}" y="${GEO.marginTop + 142}" font-size="${GEO.fontMeta}" fill="${MUTED}" font-family="${FONT_STACK}">${xmlEscape(`成熟度：${MATURITY_LABEL[sem.maturity]}｜${INTERNAL_NOTE}`)}</text>`);
  for (const cx of channels) {
    p.push(`<line class="channel-dash" x1="${cx + GEO.channelW / 2}" y1="${contentTop}" x2="${cx + GEO.channelW / 2}" y2="${contentBottom}" stroke="#cbd5e1" stroke-width="4" stroke-dasharray="24 18"/>`);
  }
  cols.forEach((x, i) => p.push(`<rect class="col-bg" data-col="${i}" x="${x}" y="${contentTop}" width="${GEO.colW}" height="${contentBottom - contentTop}" fill="${i === 1 ? "#f8fafc" : "#fcfcfd"}"/>`));
  // 空段留位（每侧恒两卡位；不可见=不立空框，机器可验）。
  // data-el 承要件编号（语义 JSON 自由字符串）——属性值一律 xmlEscape（施工单-10 单元三）。
  for (const r of rows) {
    for (const [x, tag] of [[cols[0]!, "left"], [cols[2]!, "right"]] as Array<[number, string]>) {
      p.push(`<rect class="slot-reserve" data-el="${xmlEscape(r.elNo)}" data-side="${tag}" x="${x}" y="0" width="${GEO.colW}" height="0" fill="none" stroke="none"/>`);
    }
  }
  for (const c of cards) {
    const decisive = c.kind === "center" && decisiveOf(c.el) && !scattered;
    const accent = c.side === "left" ? LEFT_ACCENT : c.side === "right" ? RIGHT_ACCENT : CARD_BORDER;
    const layout = cardLayoutIn(c.bodyLines, c.rect.h); // 卡高与基线同一函数（中轴拉伸后正文纵向居中）
    p.push(`<rect class="card ${c.kind}" data-el="${xmlEscape(c.el.no)}" data-kind="${c.kind}" x="${c.rect.x}" y="${c.rect.y}" width="${c.rect.w}" height="${Math.round(c.rect.h)}" rx="24" fill="${CARD_BG}" stroke="${accent}" stroke-width="6"/>`);
    const titleFill = decisive ? "#ffffff" : c.side === "center" ? INK : accent;
    if (decisive) p.push(`<rect class="deepred" data-el="${xmlEscape(c.el.no)}" x="${c.rect.x}" y="${c.rect.y}" width="${c.rect.w}" height="${GEO.titleH + GEO.cardPadTop}" rx="24" fill="${DEEP_RED}"/>`);
    p.push(`<text class="card-title" x="${c.rect.x + GEO.cardPadX}" y="${c.rect.y + layout.titleBaseline}" font-size="${GEO.fontTitle}" font-weight="700" fill="${titleFill}" font-family="${FONT_STACK}">${xmlEscape(c.title)}</text>`);
    c.bodyLines.forEach((ln, i) => {
      p.push(`<text class="card-body" x="${c.rect.x + GEO.cardPadX}" y="${c.rect.y + layout.baselines[i]!}" font-size="${GEO.fontBody}" fill="${INK}" font-family="${FONT_STACK}">${xmlEscape(ln)}</text>`);
    });
  }
  for (const w of wires) {
    const [tipX, tipY] = w.points[w.points.length - 1]!;
    const [preX] = w.points[w.points.length - 2] ?? w.points[0]!;
    const dir = tipX >= preX ? 1 : -1;
    p.push(`<path class="wire" data-mode="${w.mode}" data-from="${xmlEscape(w.fromId)}" data-to="${xmlEscape(w.toId)}" d="${pathD(w.points)}" data-poly="${w.points.map((pt) => `${pt[0]},${pt[1]}`).join(" ")}" fill="none" stroke="${MUTED}" stroke-width="5"/>`);
    p.push(`<polygon class="arrow" points="${tipX},${tipY} ${tipX - dir * GEO.arrowW},${tipY - GEO.arrowH / 2} ${tipX - dir * GEO.arrowW},${tipY + GEO.arrowH / 2}" fill="${MUTED}"/>`);
    p.push(`<rect class="wire-label-box" x="${w.labelRect.x}" y="${w.labelRect.y}" width="${w.labelRect.w}" height="${w.labelRect.h}" fill="#ffffff" fill-opacity="0.85" stroke="none"/>`);
    p.push(`<text class="wire-label" x="${w.labelRect.x + w.labelRect.w / 2}" y="${w.labelRect.y + 28}" font-size="${GEO.fontMeta}" fill="${MUTED}" text-anchor="middle" font-family="${FONT_STACK}">${xmlEscape(w.label)}</text>`);
  }
  p.push(`<rect class="conclusion${conclusion.deepRed ? " deepred" : ""}" x="${GEO.marginX}" y="${GEO.pageH - GEO.marginBottom - GEO.conclusionH + 20}" width="${GEO.pageW - 2 * GEO.marginX}" height="${GEO.conclusionH - 40}" rx="16" fill="${conclusion.deepRed ? DEEP_RED : "#e2e8f0"}"/>`);
  p.push(`<text class="conclusion-text" x="${GEO.marginX + 30}" y="${GEO.pageH - GEO.marginBottom - GEO.conclusionH + 20 + (GEO.conclusionH - 40) / 2 + 14}" font-size="${GEO.fontBody}" fill="${conclusion.deepRed ? "#ffffff" : INK}" font-family="${FONT_STACK}">${xmlEscape(conclusion.text)}</text>`);
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${GEO.pageW} ${GEO.pageH}" width="${GEO.pageW / 10}mm" height="${GEO.pageH / 10}mm" font-family="${FONT_STACK}"><desc>juscite-vizb 庭审对抗图·确定性渲染（图是表的渲染；不对法院出示）</desc>${p.join("")}</svg>`;
}

/** 图渲染（对外纯函数）。 */
export function renderConfrontationSvg(sem: ConfrontationSemantic): string {
  return buildFigureModel(sem).svg;
}

// ══ 17 列分析表（表是唯一信息源）══
export const ANALYSIS_COLUMNS = [
  "板块", "编号", "要件/事项", "主张（照录）", "主张来源", "回应（照录）", "回应来源",
  "反制（照录）", "反制来源", "再回应（照录）", "再回应来源", "举证责任", "三问路径",
  "法律置信", "证据置信", "决定性（规则算）", "待办/律师留白",
] as const;
const COL_W17 = [52, 70, 150, 260, 130, 260, 130, 260, 130, 260, 130, 90, 220, 60, 60, 150, 150] as const;

function slotCell(s: Slot): string {
  if (s == null) return "";
  if (isAbsentSegment(s)) return `（${s.reason}）`;
  return s.text;
}
function slotSrc(s: Slot): string {
  return isPresentSegment(s) ? `${s.src}［${s.srcKind}］` : "";
}

export function renderConfrontationTable(sem: ConfrontationSemantic): string {
  const { scattered, decisiveCount } = scatteredMode(sem);
  const rows: string[][] = [];
  const push = (cells: Record<number, string>) => {
    const full = new Array<string>(ANALYSIS_COLUMNS.length).fill("");
    for (const [k, v] of Object.entries(cells)) full[Number(k)] = v;
    rows.push(full);
  };
  push({ 0: "程序审查", 1: "P-1", 2: "管辖", 3: sem.procedure.jurisdiction });
  push({ 0: "程序审查", 1: "P-2", 2: "主体", 3: sem.procedure.standing });
  push({ 0: "程序审查", 1: "P-3", 2: "重复起诉", 3: sem.procedure.repeatedSuit });
  for (const c of sem.claims) {
    const amount = c.claimedCents == null ? "数额未定（不核算）" : `${(c.claimedCents / 100).toFixed(2)} 元`;
    push({ 0: "诉请", 1: c.no, 2: `${CLAIM_TYPES[c.type as ClaimType]?.label ?? c.type}｜${c.summary.text}｜主张 ${amount}`, 4: slotSrc(c.summary) });
    for (const it of c.items) push({ 0: "诉请明细", 1: `${c.no}-明细`, 2: it.label, 3: `${(it.cents / 100).toFixed(2)} 元（依据：${it.basis}）` });
    const reqEntries = Object.entries(c.required).map(([k, val]) => `${k}＝${val}`).join("；");
    if (reqEntries) push({ 0: "诉请要素", 1: `${c.no}-要素`, 2: reqEntries });
    for (const ad of c.adjustments) push({ 0: "诉请调整项", 1: `${c.no}-调整`, 2: ad.label, 3: `${(ad.cents / 100).toFixed(2)} 元（依据：${ad.basis}）` });
  }
  for (const d of sem.defenses) {
    const stripped = stripUnverifiedMarker(String(d.category)).trim() as DefenseCategory;
    const unverified = String(d.category).includes("【待核验】") ? "（待核验：材料未明示，照录原话标记）" : "";
    push({
      0: "抗辩", 1: d.no, 2: `${DEFENSE_CATEGORY_LABEL[stripped] ?? String(d.category)}${unverified}`,
      3: isPresentSegment(d.text) ? d.text.text : "", 4: slotSrc(d.text),
      11: `${BURDEN_LABEL[BURDEN_OF[stripped] ?? "defendant"]}（归类机械决定）`,
      12: (Array.isArray(d.threeQuestions) ? d.threeQuestions : []).map((q, i) => `问${i + 1}：${q}`).join("；"),
    });
  }
  for (const e of sem.elements) {
    push({
      0: "要件推演", 1: e.no, 2: e.issue,
      3: slotCell(e.claim), 4: slotSrc(e.claim),
      5: slotCell(e.response), 6: slotSrc(e.response),
      7: slotCell(e.counter), 8: slotSrc(e.counter),
      9: slotCell(e.second), 10: slotSrc(e.second),
      11: BURDEN_LABEL[e.burden],
      13: confLabel(e.lawConfidence), 14: confLabel(e.evidenceConfidence),
      15: decisiveOf(e) ? (scattered ? "决定性（分散态，不作视觉强调）" : "决定性") : "—",
    });
  }
  push({ 0: "材料成熟度", 1: "M", 2: MATURITY_LABEL[sem.maturity], 3: `决定性共 ${decisiveCount} 处${scattered ? "（分散态：全图不强调）" : ""}` });
  sem.toComplete.forEach((t, i) => push({ 0: "待补", 1: `T-${i + 1}`, 2: t }));
  push({ 0: "律师留白", 1: "L-1", 2: "证明前景", 16: "（律师回填；模型留空）" });
  push({ 0: "律师留白", 1: "L-2", 2: "决定性要件排序", 16: "（律师回填；模型留空）" });
  push({ 0: "律师留白", 1: "L-3", 2: "法院另定性风险", 16: "（律师回填；模型留空）" });

  const table = `<Table ss:ExpandedColumnCount="${ANALYSIS_COLUMNS.length}" ss:ExpandedRowCount="${rows.length + 2}">`
    + COL_W17.map((w) => `<Column ss:Width="${w}"/>`).join("")
    + `<Row>${ssCell(`${xmlEscape(sem.caseTitle)}·庭审对抗分析表（内部推演件·不对法院出示；对抗图=本表的渲染）`, { styleId: "title" })}${new Array(ANALYSIS_COLUMNS.length - 1).fill("<Cell/>").join("")}</Row>`
    + `<Row>${ANALYSIS_COLUMNS.map((c) => ssCell(c, { styleId: "hdr" })).join("")}</Row>`
    + rows.map((r) => `<Row>${r.map((c, i) => ssCell(c, { styleId: r[15] === "决定性" && i === 15 ? "decisive" : i === 0 ? "sec" : "plain" })).join("")}</Row>`).join("")
    + `</Table>`;
  return excelXmlProlog()
    + `<Workbook ${SS_NS}>`
    + "<Styles>"
    + ssStyle("Default")
    + ssStyle("title", { bold: true })
    + ssStyle("hdr", { bold: true, color: "#FFFFFFFF", bg: "#FF374151", align: "Center" })
    + ssStyle("sec", { bg: "#FFE2E8F0" })
    + ssStyle("decisive", { bold: true, color: `#FF${DEEP_RED.slice(1).toUpperCase()}`, bg: "#FFF6ECEC" }) // 与图同一深红值（去 #FF 前缀对拍；图表一致判据）
    + ssStyle("plain")
    + "</Styles>"
    + `<Worksheet ss:Name="对抗分析表">${table}</Worksheet>`
    + "</Workbook>";
}
