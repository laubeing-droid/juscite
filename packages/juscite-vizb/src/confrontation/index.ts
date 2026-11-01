// 庭审对抗图 #19 深化·组合入口：语义 JSON（封闭 schema）→ 数据守卫（J/K/P/M/D/四段收口/照录）
// → 图+表渲染 → 产物守卫（版面/走线/红块/图表一致/字段出口）。任何一条不成立拒绝出图，禁止降级硬填。
// 全链纯函数：同输入两跑逐字节一致。零 JC 依赖（金额对平=纯脚本整型分算术；判断=带三标的模型语义输出）。

import { validateSemantic, type ConfrontationSemantic } from "./semantic.ts";
import { guardConfrontation, type CViolation } from "./guards.ts";
import { guardFigureAndTable, type FigureViolation } from "./artifactGuards.ts";
import { renderConfrontationSvg, renderConfrontationTable } from "./render.ts";

export * from "./tables.ts";
export * from "./semantic.ts";
export { guardConfrontation, decisiveOf, scatteredMode } from "./guards.ts";
export type { CViolation } from "./guards.ts";
export { checkClaimArithmetic, claimRequiredMissing } from "./arithmetic.ts";
export { renderConfrontationSvg, renderConfrontationTable, buildFigureModel, routeWire, wiresSelfCheck, WIRE_MODES, DEEP_RED, ANALYSIS_COLUMNS } from "./render.ts";
export type { WireSpec, WireMode, Obstacle, CardBox, FigureModel } from "./render.ts";
export { guardFigureAndTable, confrontationDeterminism } from "./artifactGuards.ts";
export type { FigureViolation } from "./artifactGuards.ts";
export { cardLayoutIn, cardLayout, columnXs, GEO, segIntersectsRect, wrapLines, textWidth } from "./geometry.ts";
export { RASTER_FONT_FAMILY, swapFontStackForRaster, guardRasterFontSwapped } from "../shared/raster.ts"; // 光栅化字体契约（对抗图 SVG→PNG 共用）
export type { RasterSwap, RasterArtifactViolation } from "../shared/raster.ts";

export interface ConfrontationComposeResult {
  ok: boolean;
  schemaViolations: ReturnType<typeof validateSemantic>;
  guardViolations: CViolation[];
  figureViolations: FigureViolation[];
  artifacts: { svg: string; analysisTableXml: string } | null;
  refusal: string | null;
}

export function composeConfrontation(input: unknown): ConfrontationComposeResult {
  const schemaViolations = validateSemantic(input);
  if (schemaViolations.length) {
    return { ok: false, schemaViolations, guardViolations: [], figureViolations: [], artifacts: null,
      refusal: `语义 JSON 不合封闭 schema（${schemaViolations.length} 处），拒绝出图：${schemaViolations[0]!.path} ${schemaViolations[0]!.msg}` };
  }
  const sem = input as ConfrontationSemantic;
  const guardViolations = guardConfrontation(sem);
  if (guardViolations.length) {
    return { ok: false, schemaViolations: [], guardViolations, figureViolations: [], artifacts: null,
      refusal: `判据守卫不成立（${guardViolations.length} 条），拒绝出图：[${guardViolations[0]!.group}/${guardViolations[0]!.code}] ${guardViolations[0]!.msg}` };
  }
  let svg: string;
  try {
    svg = renderConfrontationSvg(sem); // 内部先全量走线自证，穿卡即抛（fail-fast 拒绝出图）
  } catch (e) {
    return { ok: false, schemaViolations: [], guardViolations: [], figureViolations: [], artifacts: null,
      refusal: `渲染层拒绝出图：${e instanceof Error ? e.message : String(e)}` };
  }
  const analysisTableXml = renderConfrontationTable(sem);
  const figureViolations = guardFigureAndTable(sem, svg, analysisTableXml);
  if (figureViolations.length) {
    return { ok: false, schemaViolations: [], guardViolations: [], figureViolations, artifacts: null,
      refusal: `产物自检不成立（${figureViolations.length} 条），拒绝出图：[${figureViolations[0]!.group}/${figureViolations[0]!.code}] ${figureViolations[0]!.msg}` };
  }
  return { ok: true, schemaViolations: [], guardViolations: [], figureViolations: [], refusal: null,
    artifacts: { svg, analysisTableXml } };
}
