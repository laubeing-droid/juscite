// 对抗图产物守卫（版面 M/R/T/L＋图表一致＋字段出口；全部读 svg/table 产物字符串核验）。
// 判据盯真正画进去的那份数据：几何量从产物 data-* 属性解析回读，与反解函数复算值比对。

import { cardLayoutIn, columnXs, GEO } from "./geometry.ts";
import { decisiveOf, scatteredMode } from "./guards.ts";
import { DEEP_RED, FIGURE_PALETTE, renderConfrontationSvg, renderConfrontationTable, wiresSelfCheck, type Obstacle, type WireSpec } from "./render.ts";
import type { ConfrontationSemantic } from "./semantic.ts";
import { CLAIM_TYPES, DEFENSE_CATEGORY_LABEL, MATURITY_LABEL, stripUnverifiedMarker, type ClaimType, type DefenseCategory } from "./tables.ts";

export interface FigureViolation { group: "VC-版面" | "VC-图表一致" | "VC-字段出口"; code: string; msg: string }

function decode(s: string): string {
  return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&amp;/g, "&");
}

/** 产物几何守卫＋红块计数＋直角引号＋图表一致＋字段出口。 */
export function guardFigureAndTable(sem: ConfrontationSemantic, svg: string, tableXml: string): FigureViolation[] {
  const v: FigureViolation[] = [];
  const { cols, channels } = columnXs();
  // ── 三栏等宽、恰好三栏、通道等宽、总宽零误差（读产物 col-bg）──
  const colBg = [...svg.matchAll(/<rect class="col-bg" data-col="(\d)" x="([\d.]+)"[^>]*width="(\d+)"[^>]*\/>/g)];
  if (colBg.length !== 3) v.push({ group: "VC-版面", code: "L-cols", msg: `产物三栏数=${colBg.length}（恰好三栏）` });
  const widths = colBg.map((m) => Number(m[3]));
  if (new Set(widths).size > 1) v.push({ group: "VC-版面", code: "L-col-width", msg: `三栏不等宽：${widths.join(",")}` });
  if (colBg.some((m) => Number(m[3]) !== GEO.colW)) v.push({ group: "VC-版面", code: "L-col-sum", msg: `栏宽 ${widths[0]} ≠ 反解 ${GEO.colW}（三栏+两通道+页边=总宽须零误差）` });
  const xs = colBg.map((m) => Number(m[2]));
  if (xs.some((x, i) => x !== cols[i])) v.push({ group: "VC-版面", code: "L-col-x", msg: "栏 x 坐标与反解不符" });
  // ── 行组高=max 三栈、中轴卡高=行组高（读产物 card 高与 data-el 分组）──
  const cards = [...svg.matchAll(/<rect class="card (\w+)" data-el="([^"]+)" data-kind="(\w+)" x="([\d.]+)" y="([\d.]+)" width="(\d+)" height="(\d+)"[^>]*\/>/g)]
    .map((m) => ({ kind: m[1]!, elNo: m[2]!, x: Number(m[4]), y: Number(m[5]), w: Number(m[6]), h: Number(m[7]) }));
  for (const el of sem.elements) {
    const mine = cards.filter((c) => c.elNo === el.no);
    const center = mine.find((c) => c.kind === "center");
    const left = mine.filter((c) => c.kind === "claim" || c.kind === "counter");
    const right = mine.filter((c) => c.kind === "response" || c.kind === "second");
    if (!center) { v.push({ group: "VC-版面", code: "L-center-missing", msg: `要件 ${el.no} 缺中轴卡` }); continue; }
    const leftH = left.reduce((a, c) => a + c.h + GEO.slotGap, 0);
    const rightH = right.reduce((a, c) => a + c.h + GEO.slotGap, 0);
    if (center.h < Math.max(leftH, rightH) - GEO.slotGap - 1) {
      v.push({ group: "VC-版面", code: "L-row-height", msg: `要件 ${el.no} 中轴卡高 ${center.h} < 侧栈需高 ${Math.round(Math.max(leftH, rightH) - GEO.slotGap)}（行组高=max(左栈,右栈,中轴需高)）` });
    }
    // 四段收口·几何面：每侧恒两卡位（留位由布局保证），下位卡无而上位卡有=几何拒绝
    if (!left.some((c) => c.kind === "claim") && left.some((c) => c.kind === "counter")) {
      v.push({ group: "VC-版面", code: "L-slot-order-left", msg: `要件 ${el.no} 左侧无主张卡却有反制卡（几何层拦截）` });
    }
    if (!right.some((c) => c.kind === "response") && right.some((c) => c.kind === "second")) {
      v.push({ group: "VC-版面", code: "L-slot-order-right", msg: `要件 ${el.no} 右侧无回应卡却有再回应卡（几何层拦截）` });
    }
    // 卡底留白≥卡顶留白（另量绝对值，不靠居中吸收）
    const layout = cardLayoutIn([], center.h);
    const bottomPad = center.h - layout.bodyTop;
    if (bottomPad < GEO.cardPadTop) v.push({ group: "VC-版面", code: "L-pad", msg: `要件 ${el.no} 中轴卡底留白 ${Math.round(bottomPad)} < 卡顶留白 ${GEO.cardPadTop}` });
  }
  // ── 走线全量自证（读产物 data-poly 复演；穿非端点卡片/压边标签即拒）──
  const obstacles: Obstacle[] = cards.map((c) => ({ x: c.x, y: c.y, w: c.w, h: c.h, id: `${c.kind}@${c.elNo}` }));
  const wireEls = [...svg.matchAll(/<path class="wire" data-mode="([\w-]+)" data-from="([^"]+)" data-to="([^"]+)"[^>]*data-poly="([^"]+)"[^>]*\/>/g)];
  const labels = [...svg.matchAll(/<text class="wire-label"[^>]*>([\s\S]*?)<\/text>/g)].map((m, i) => decode(m[1]!));
  const labelBoxes = [...svg.matchAll(/<rect class="wire-label-box" x="([\d.-]+)" y="([\d.-]+)" width="([\d.]+)" height="([\d.]+)"/g)];
  labelBoxes.forEach((m, i) => obstacles.push({ x: Number(m[1]), y: Number(m[2]), w: Number(m[3]), h: Number(m[4]), id: `label:${labels[i] ?? i}`, label: labels[i] }));
  const wires: WireSpec[] = wireEls.map((m, i) => ({
    mode: m[1]! as WireSpec["mode"], fromId: m[2]!, toId: m[3]!,
    points: m[4]!.split(" ").map((pt) => pt.split(",").map(Number) as [number, number]),
    label: labels[i] ?? m[2]!, labelRect: { x: 0, y: 0, w: 0, h: 0 }, labelId: `label:${labels[i] ?? i}`,
  }));
  for (const w of wires) {
    if (!["M1-direct", "M2-elbow", "M3-switchback", "M4-arc"].includes(w.mode)) {
      v.push({ group: "VC-版面", code: "L-wire-mode", msg: `走线模式「${w.mode}」不在封闭集 M1–M4` });
    }
  }
  for (const err of wiresSelfCheck(wires, obstacles)) v.push({ group: "VC-版面", code: "L-wire-cross", msg: err });
  // ── 深红唯一值＋数色块（不数出现次数）；分散态全图无深红；结论条写明共几处 ──
  const deepRedBlocks = [...svg.matchAll(/<(rect|path|polygon)[^>]*fill="#8a1f1f"[^>]*>/g)].length;
  const { scattered, decisiveCount } = scatteredMode(sem);
  if (scattered) {
    if (deepRedBlocks !== 0) v.push({ group: "VC-版面", code: "L-scattered-red", msg: `分散态（${decisiveCount} 处决定性）全图不得出现深红，实测 ${deepRedBlocks} 块（代码不得替律师挑前两个）` });
    if (!svg.includes(`共 ${decisiveCount} 处决定性要件`)) v.push({ group: "VC-版面", code: "L-scattered-count", msg: "分散态结论条须写明共几处决定性" });
  } else if (decisiveCount > 0) {
    if (deepRedBlocks > 3) v.push({ group: "VC-版面", code: "L-red-blocks", msg: `深红色块 ${deepRedBlocks} 个＞3（至多两处强调＋一条结论条）` });
    if (deepRedBlocks < decisiveCount) v.push({ group: "VC-版面", code: "L-red-missing", msg: `决定性 ${decisiveCount} 处但深红强调块仅 ${deepRedBlocks}（判定如实上图）` });
  } else if (deepRedBlocks > 0) {
    v.push({ group: "VC-版面", code: "L-red-spurious", msg: `无决定性要件但出现 ${deepRedBlocks} 个深红块` });
  }
  const fills = [...svg.matchAll(/fill="(#[0-9a-fA-F]{6})"/g)].map((m) => m[1]!.toLowerCase());
  const offPalette = [...new Set(fills.filter((c) => !FIGURE_PALETTE.has(c)))];
  if (offPalette.length) v.push({ group: "VC-版面", code: "L-palette", msg: `图面出现封闭色板外的颜色：${offPalette.join(",")}（色板封闭；深红在板内唯一）` });
  const deepRedFamily = fills.filter((c) => c !== DEEP_RED && colorNear(c, DEEP_RED));
  if (deepRedFamily.length) v.push({ group: "VC-版面", code: "L-red-unique", msg: `深红须唯一值，检出近似深红 ${[...new Set(deepRedFamily)].join(",")}` });
  // ── 图上不出现直角引号 ──
  const texts = [...svg.matchAll(/<text[^>]*>([\s\S]*?)<\/text>/g)].map((m) => decode(m[1]!));
  if (texts.some((t) => /[「」『』]/.test(t))) v.push({ group: "VC-版面", code: "L-corner-quotes", msg: "图上出现直角引号「」『』" });
  // ── 内部件声明随图 ──
  if (!svg.includes("不对法院出示")) v.push({ group: "VC-版面", code: "L-internal-note", msg: "图面缺「不对法院出示」限制声明（对抗图=内部推演件）" });
  // ── 图表一致：编号一一对应＋同色值 ──
  const figNos = cards.filter((c) => c.kind === "center").map((c) => c.elNo);
  const tableRows = [...tableXml.matchAll(/<Row>([\s\S]*?)<\/Row>/g)].map((m) => [...m[1]!.matchAll(/<Data[^>]*>([\s\S]*?)<\/Data>/g)].map((d) => decode(d[1]!)));
  const elemRows = tableRows.filter((r) => r[0] === "要件推演");
  const tableNos = elemRows.map((r) => r[1] ?? "");
  if (figNos.length !== tableNos.length || figNos.some((n, i) => n !== tableNos[i])) {
    v.push({ group: "VC-图表一致", code: "I-numbering", msg: `图与表要件编号不一一对应（图 ${figNos.join(",")} vs 表 ${tableNos.join(",")}）` });
  }
  const decisiveInTable = elemRows.filter((r) => (r[15] ?? "").startsWith("决定性")).length;
  const decisiveInFig = sem.elements.filter((e) => decisiveOf(e)).length;
  if (decisiveInTable !== decisiveInFig) v.push({ group: "VC-图表一致", code: "I-decisive", msg: `表内决定性行 ${decisiveInTable} ≠ 规则算出 ${decisiveInFig}` });
  if (decisiveInFig > 0 && !tableXml.toUpperCase().includes(DEEP_RED.slice(1).toUpperCase())) {
    v.push({ group: "VC-图表一致", code: "I-color", msg: "表内决定性行须与图用同一深红色值" });
  }
  // ── 字段出口全覆盖（填进语义 JSON 的字段在图或表找不到即报——防律师白填）──
  for (const [field, found] of fieldExits(sem, tableXml, svg)) {
    if (!found) v.push({ group: "VC-字段出口", code: "E-exit", msg: `字段「${field}」在图与表均无出口（防白填）` });
  }
  return v;
}

function colorNear(a: string, b: string): boolean {
  const d = (x: string, i: number) => parseInt(x.slice(1 + i * 2, 3 + i * 2), 16);
  const dist = Math.hypot(d(a, 0) - d(b, 0), d(a, 1) - d(b, 1), d(a, 2) - d(b, 2));
  return dist < 40; // 近深红（防色值漂移致静默算 0 的教训：近似也算深红族）
}

/** 字段出口映射（每个非空字段 → 表列或图面；机制：全覆盖检查，防白填）。 */
function fieldExits(sem: ConfrontationSemantic, tableXml: string, svg: string): Array<[string, boolean]> {
  const out: Array<[string, boolean]> = [];
  const inTable = (s: string) => s.length > 0 && tableXml.includes(escapeFor(s));
  const inFig = (s: string) => s.length > 0 && svg.includes(escapeFor(s));
  const either = (field: string, s: string) => out.push([field, inTable(s) || inFig(s)]);
  either("procedure.jurisdiction", sem.procedure.jurisdiction);
  either("procedure.standing", sem.procedure.standing);
  either("procedure.repeatedSuit", sem.procedure.repeatedSuit);
  either("maturity", MATURITY_LABEL[sem.maturity]);
  for (const c of sem.claims) {
    either(`claim ${c.no}.type`, CLAIM_TYPES[c.type as ClaimType]?.label ?? c.type);
    if (c.summary) either(`claim ${c.no}.summary`, c.summary.text);
    either(`claim ${c.no}.claimedCents`, c.claimedCents == null ? "数额未定" : (c.claimedCents / 100).toFixed(2));
    for (const it of c.items) { either(`claim ${c.no}.item ${it.label}`, it.label); either(`claim ${c.no}.item ${it.label} basis`, it.basis); }
    for (const ad of c.adjustments) either(`claim ${c.no}.adjustment ${ad.label}`, ad.label);
    for (const [k, val] of Object.entries(c.required)) either(`claim ${c.no}.required.${k}`, String(val));
  }
  for (const d of sem.defenses) {
    either(`defense ${d.no}.category`, DEFENSE_CATEGORY_LABEL[stripUnverifiedMarker(String(d.category)).trim() as DefenseCategory] ?? String(d.category));
    if (d.text) either(`defense ${d.no}.text`, d.text.text);
    (Array.isArray(d.threeQuestions) ? d.threeQuestions : []).forEach((q, i) => either(`defense ${d.no}.q${i + 1}`, q));
  }
  for (const e of sem.elements) {
    either(`element ${e.no}.issue`, e.issue);
    either(`element ${e.no}.source`, e.source);
    for (const [k, s] of [["claim", e.claim], ["response", e.response], ["counter", e.counter], ["second", e.second]] as const) {
      if (s && typeof s === "object" && "text" in s && s.text) either(`element ${e.no}.${k}`, s.text);
    }
  }
  sem.toComplete.forEach((t, i) => either(`toComplete[${i}]`, t));
  return out;
}
function escapeFor(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");
}

/** 确定性对拍（C15 用）：同语义 JSON 两跑图+表逐字节一致。 */
export function confrontationDeterminism(sem: ConfrontationSemantic): { same: boolean } {
  const a1 = renderConfrontationSvg(sem); const a2 = renderConfrontationSvg(sem);
  const b1 = renderConfrontationTable(sem); const b2 = renderConfrontationTable(sem);
  return { same: a1 === a2 && b1 === b2 };
}
