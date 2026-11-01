// 大事记 #4 深化·组合入口（四契约的施工面）：
//   语义 JSON（封闭 schema，模型唯一自由产出）→ 判据守卫（A/B/C/D/E，任何一条不成立拒绝出表）
//   → 四件同源交付（Word 交付版/Excel 母表/A4 呈报简表/机器读底稿）＋交付面自检（R/W/X/简表）。
// 底稿=既有事件账本（case_events 确认事件）的投影视图：投影在桥面做，本包只认 schema。
// 全链纯函数零依赖：同输入两次组合逐字节一致（契约二确定性）。

import { deriveEvidenceStatus, validateFactBase, FACTBASE_SCHEMA, type FactBase } from "./factbase.ts";
import { guardChronicle, sortedFacts, type Violation } from "./guards.ts";
import { guardBriefArtifacts, guardExcelArtifact, guardWordArtifact, type ArtifactViolation } from "./parseBack.ts";
import { renderBrief } from "./renderBrief.ts";
import { renderExcel } from "./renderExcel.ts";
import { renderWord } from "./renderWord.ts";
import { reconcileIntake, type IntakeManifestDoc, type IntakePage, type IntakeSkip } from "./intake.ts";

export * from "./tables.ts";
export * from "./factbase.ts";
export * from "./textcheck.ts";
export * from "./intake.ts";
export { guardChronicle, sortedFacts } from "./guards.ts";
export type { Violation } from "./guards.ts";
export { guardWordArtifact, guardExcelArtifact, guardBriefArtifacts, parseWordRows, parseExcelRows, parseBriefTexts } from "./parseBack.ts";
export type { ArtifactViolation } from "./parseBack.ts";
export { renderWord, WORD_PAGE, WORD_MARGIN, WORD_BODY_W, WORD_COLS, WORD_FONT, buildEndnotes, sourceRefOf } from "./renderWord.ts";
export { renderExcel, MASTER_COLUMNS } from "./renderExcel.ts";
export { renderBrief, BRIEF_PAGE, BRIEF_MARGIN, BRIEF_FONT, BRIEF_COLS, BRIEF_CONTENT_CHARS, BRIEF_MAX_LINES, BRIEF_GROUP_RED, BRIEF_BANNED_MARKERS } from "./renderBrief.ts";
export { RASTER_FONT_FAMILY, swapFontStackForRaster, guardRasterFontSwapped } from "../shared/raster.ts"; // 光栅化字体契约（简表 SVG→PNG 共用）
export type { RasterSwap, RasterArtifactViolation } from "../shared/raster.ts";

export interface ChronicleComposeResult {
  ok: boolean;
  schemaViolations: ReturnType<typeof validateFactBase>;
  guardViolations: Violation[];
  artifactViolations: ArtifactViolation[];
  artifacts: { wordXml: string; excelXml: string; briefSvgPages: string[]; factBaseJson: string } | null;
  refusal: string | null; // 拒绝出表的理由（守卫或自检不成立）
}

/** 规范化 JSON（键序稳定，字节级确定）。 */
export function canonicalJson(v: unknown): string {
  const walk = (x: unknown): unknown => {
    if (Array.isArray(x)) return x.map(walk);
    if (x !== null && typeof x === "object") {
      return Object.fromEntries(Object.keys(x as Record<string, unknown>).sort().map((k) => [k, walk((x as Record<string, unknown>)[k])]));
    }
    return x;
  };
  return JSON.stringify(walk(v), null, 2);
}

/**
 * 组合入口：schema 校验→守卫→渲染→交付自检。任何一步不成立即拒绝出表（禁止降级硬填），
 * 返回 ok=false＋具名违例；不产任何交付物。
 */
export function composeChronicle(input: unknown): ChronicleComposeResult {
  const schemaViolations = validateFactBase(input);
  if (schemaViolations.length) {
    return { ok: false, schemaViolations, guardViolations: [], artifactViolations: [], artifacts: null,
      refusal: `底稿不合封闭 schema（${schemaViolations.length} 处），拒绝出表：${schemaViolations[0]!.path} ${schemaViolations[0]!.msg}` };
  }
  const fb = input as FactBase;
  // 不确定清单联动（E 组）：无书证事实未列则补齐（机械生成，模型不判断）
  for (const f of fb.facts) {
    if (deriveEvidenceStatus(f) === "仅当事人陈述" && !fb.uncertainty.some((u) => u.includes(`事实 ${f.factNo}`))) {
      fb.uncertainty.push(`事实 ${f.factNo}（${f.verb}·${f.title}）：无书证，仅当事人陈述`);
    }
  }
  const guardViolations = guardChronicle(fb);
  if (guardViolations.length) {
    return { ok: false, schemaViolations: [], guardViolations, artifactViolations: [], artifacts: null,
      refusal: `判据守卫不成立（${guardViolations.length} 条），拒绝出表：[${guardViolations[0]!.group}/${guardViolations[0]!.code}] ${guardViolations[0]!.msg}` };
  }
  const wordXml = renderWord(fb);
  const excelXml = renderExcel(fb);
  const briefSvgPages = renderBrief(fb);
  const factBaseJson = canonicalJson({ ...fb, schema: FACTBASE_SCHEMA });
  const artifactViolations = [
    ...guardWordArtifact(fb, wordXml),
    ...guardExcelArtifact(fb, excelXml),
    ...guardBriefArtifacts(fb, briefSvgPages),
  ];
  if (artifactViolations.length) {
    return { ok: false, schemaViolations: [], guardViolations: [], artifactViolations, artifacts: null,
      refusal: `交付面自检不成立（${artifactViolations.length} 条），拒绝出表：[${artifactViolations[0]!.group}/${artifactViolations[0]!.code}] ${artifactViolations[0]!.msg}` };
  }
  return { ok: true, schemaViolations: [], guardViolations: [], artifactViolations: [], refusal: null,
    artifacts: { wordXml, excelXml, briefSvgPages, factBaseJson } };
}

/** 摄入对账直通（I 组；#4/#19 共用前置）。 */
export function chronicleIntake(pages: IntakePage[], skips: IntakeSkip[], manifest: IntakeManifestDoc[]) {
  return reconcileIntake(pages, skips, manifest);
}
