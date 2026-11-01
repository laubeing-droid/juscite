// 【施工波二轮·可视化B轨收尾】SVG→PNG 光栅化桥面配套（环境面；纯函数面在 @juscite/vizb shared/raster.ts）。
// 机制（B 轨规格 §2.2 字体坑契约+A9）：字体回退是静默的——PNG 光栅化前把副本换单一确实安装的
// 字族并日志报出；SVG 交付件仍写规范字族栈。
// 工程姿态（A9「cairo 缺失只跳过导出不拖垮全部交付」同款）：渲染器/字族缺位=跳过 PNG 导出并
// 显式报因，SVG 交付件不受影响；@napi-rs/canvas 系 pdfjs-dist 随附 native（桌面打包态被原生包
// 瘦身策略剔除——packages/desktop/scripts/desktop-native-package-policy.mjs——打包态即走跳过分支）。
// 渲染链全确定性：同一 SVG+同一字族文件两跑 PNG 逐字节一致（无时间戳入流）。
import { existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { guardRasterFontSwapped, RASTER_FONT_FAMILY, swapFontStackForRaster } from "../../packages/juscite-vizb/src/shared/raster.ts";

// 已安装 CJK 字族文件候选（按序取首个在盘者注册到 RASTER_FONT_FAMILY——注册即「确实安装」的可证形态）
const FONT_FILE_CANDIDATES = (() => {
  const win = process.env.windir ?? "C:\\Windows";
  return [
    join(homedir(), "AppData", "Local", "Microsoft", "Windows", "Fonts", "msyh.ttc"),
    join(win, "Fonts", "msyh.ttc"),
    join(win, "Fonts", "simhei.ttf"),
    join(win, "Fonts", "simsun.ttc"),
    join(win, "Fonts", "simkai.ttf"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
  ];
})();

let fontEnsured = null; // 模块级单次注册缓存 { family, sourcePath } | { missing: reason }
function ensureRasterFont(canvas) {
  if (fontEnsured) return fontEnsured;
  for (const p of FONT_FILE_CANDIDATES) {
    if (!existsSync(p)) continue;
    try {
      canvas.GlobalFonts.registerFromPath(p, RASTER_FONT_FAMILY);
      fontEnsured = { family: RASTER_FONT_FAMILY, sourcePath: p };
      return fontEnsured;
    } catch { /* 该文件注册失败试下一候选 */ }
  }
  fontEnsured = { missing: `未找到可注册的已安装 CJK 字族文件（候选 ${FONT_FILE_CANDIDATES.length} 个均不在盘或注册失败）` };
  return fontEnsured;
}

/**
 * SVG → PNG：换单一族（日志报出）→ 字族守卫（读副本字符串）→ Skia 解码绘制 → 非空白守卫 → PNG。
 * 返回 { ok:true, png, width, height, logs } 或 { ok:false, skipped:true, reason }（渲染面缺位跳过，
 * 不拖垮 SVG 交付）；字族守卫/非空白守卫不成立=硬错（可见失败，fail-fast 不静默）。
 */
export async function rasterizeSvgToPng(svg) {
  let canvas;
  try {
    canvas = await import("@napi-rs/canvas");
  } catch {
    return { ok: false, skipped: true, reason: "光栅化渲染器不可用（@napi-rs/canvas 未安装/被打包瘦身剔除）——跳过 PNG 导出，SVG 交付件不受影响" };
  }
  const font = ensureRasterFont(canvas);
  if (font.missing) return { ok: false, skipped: true, reason: font.missing };
  const swap = swapFontStackForRaster(svg, font.family);
  const violations = guardRasterFontSwapped(swap.svg, font.family);
  if (violations.length) throw new Error(`光栅化副本字族守卫不成立：[${violations[0].code}] ${violations[0].msg}`);
  const image = await canvas.loadImage(Buffer.from(swap.svg, "utf8"));
  const c = canvas.createCanvas(image.width, image.height);
  const ctx = c.getContext("2d");
  ctx.drawImage(image, 0, 0);
  // 非空白守卫：全图几乎无深色像素=文本未落版（缺字形/空图），拒绝交付近白 PNG（静默失败可见化）
  const d = ctx.getImageData(0, 0, c.width, c.height).data;
  let dark = 0;
  for (let i = 0; i < d.length; i += 4) if (d[i] < 128 && d[i + 1] < 128 && d[i + 2] < 128) dark++;
  if (dark < Math.max(64, Math.floor((c.width * c.height) / 2000))) {
    throw new Error(`光栅化产物近空白（深色像素 ${dark}/${c.width}x${c.height}）——字族未生效或图源为空，拒绝交付 PNG`);
  }
  const png = c.toBuffer("image/png");
  const logs = [`[vizb-raster] 字族源文件=${font.sourcePath}（注册名 ${font.family}）`, ...swap.logs];
  return { ok: true, png, width: c.width, height: c.height, dark, logs };
}
