// 光栅化字体契约（B 轨规格 §2.2 字体坑契约+A9 工程坑位，机制照收·选族自写）：
//  - SVG 交付件保留完整字族栈（规范字体名照写）；
//  - PNG 光栅化前把副本的全部 font-family 换成单一确实安装的字族，替换必须在日志报出
//    （字体回退是静默的——换单族后要么全渲染要么全缺字，静默回退就此可见）；
//  - 换族只发生在光栅化副本上，交付面 SVG 一字不动。
// 渲染器（环境面：字族文件探测注册+Skia 解码+PNG 编码）在桥面 tools/bridge/vizb_raster.mjs；
// 本文件只放纯函数：换族+日志、读产物守卫（改坏可证伪）。

/** 光栅化单族注册名（桥面把已安装的 CJK 字族文件注册到此名——注册即「确实安装」的可证形态）。 */
export const RASTER_FONT_FAMILY = "Juscite Raster CJK";

export interface RasterSwap {
  svg: string;   // 换族后的光栅化副本（非交付件）
  logs: string[]; // 字族替换日志（每遇到一个不同的栈报一次）
}

/** 光栅化副本换单一族：替换全部 font-family 属性值；每个不同的原栈在日志报出一次。 */
export function swapFontStackForRaster(svg: string, family: string): RasterSwap {
  const logs: string[] = [];
  const seen = new Set<string>();
  const out = svg.replace(/font-family="([^"]*)"/g, (_m: string, stack: string) => {
    if (!seen.has(stack)) {
      seen.add(stack);
      logs.push(`[vizb-raster] 光栅化前换单一族：${stack} → ${family}（SVG 交付件仍写规范字族栈；静默回退就此可见）`);
    }
    return `font-family="${family}"`;
  });
  if (!seen.size) logs.push(`[vizb-raster] 副本未检出 font-family 属性，无处证单族——拒绝盲光栅化（family=${family}）`);
  return { svg: out, logs };
}

export interface RasterArtifactViolation { code: string; msg: string }

/**
 * 光栅化副本字族守卫（读产物字符串，不查生成函数返回值）：换族后全图必须恰好单族且等于目标族。
 * 多族栈残留 / 异族 / 无 font-family 可证——任一即报（守卫可证伪：拿未换族的交付 SVG 来跑必报）。
 */
export function guardRasterFontSwapped(svgForRaster: string, family: string): RasterArtifactViolation[] {
  const v: RasterArtifactViolation[] = [];
  const fams = [...svgForRaster.matchAll(/font-family="([^"]*)"/g)].map((m) => m[1]!);
  if (!fams.length) return [{ code: "RA-no-font-family", msg: "光栅化副本无 font-family 属性，无法证明单族" }];
  for (const f of fams) {
    if (f.includes(",") || f.includes("'")) v.push({ code: "RA-multi-family", msg: `光栅化副本仍含多族栈：${f}` });
    else if (f !== family) v.push({ code: "RA-family-mismatch", msg: `光栅化副本字族不符：${f} ≠ ${family}` });
  }
  return v;
}
