// WPS jsaddons 通道（方案 §五 S4）：在 %APPDATA%\kingsoft\wps\jsaddons\publish.xml 注入
// <jspluginonline name="juscite-wps-plugin" type="wps" url=... enable="true" install="null"/>。
// 确定性解析（正则状态机，LegalTech 约束①——零大模型猜测）；幂等：同名条目=原位更新，异名条目全保留；
// 移除：只删自家条目，发布文件若为本单元所建且变空则整文件删除（回到注入前原样）。
// 版本门槛：AutoClaw 参照 6.13.0（B 报告 §2.3），本机实测 12.1.0.29680 达标。
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { readdirSync } from "node:fs";

export const WPS_PLUGIN_NAME = "juscite-wps-plugin";
export const WPS_MIN_VERSION = [6, 13, 0];
const PUBLISH_XML = "publish.xml";

export function publishXmlPath(jsaddonsDir) {
  return join(jsaddonsDir, PUBLISH_XML);
}

// 版本比较：主.次.修 的整数序；无法解析=不达标（fail-closed，不猜）
export function versionAtLeast(present, min = WPS_MIN_VERSION) {
  const parts = String(present ?? "").split(/[.,]/).map((x) => Number(x));
  if (parts.some((x) => !Number.isInteger(x)) || parts.length < 3) return false;
  for (let i = 0; i < 3; i++) {
    if ((parts[i] ?? 0) > (min[i] ?? 0)) return true;
    if ((parts[i] ?? 0) < (min[i] ?? 0)) return false;
  }
  return true;
}

// 从 %LOCALAPPDATA%\Kingsoft/WPS Office/<版本目录>/office6/wps.exe 的目录名取版本（确定性，无注册表依赖）
export function detectWpsVersion(localAppData = process.env.LOCALAPPDATA) {
  const root = join(localAppData ?? "", "Kingsoft", "WPS Office");
  if (!existsSync(root)) return null;
  const dirs = readdirSync(root, { withFileTypes: true })
    .filter((e) => e.isDirectory() && /^\d+(\.\d+)*$/.test(e.name))
    .map((e) => e.name)
    .sort((a, b) => cmpVersionStrings(b, a)); // 新版本优先
  return dirs[0] ?? null;
}
function cmpVersionStrings(a, b) {
  const pa = a.split(".").map(Number);
  const pb = b.split(".").map(Number);
  const n = Math.max(pa.length, pb.length); // 全段比较（含 build 段），缺段按 0
  for (let i = 0; i < n; i++) {
    if ((pa[i] ?? 0) !== (pb[i] ?? 0)) return (pa[i] ?? 0) - (pb[i] ?? 0);
  }
  return 0;
}

const entryRe = (name) => new RegExp(`\\s*<jspluginonline\\s+[^>]*name="${escapeReg(name)}"[^>]*/>`, "g");
function escapeReg(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function entryXml(url) {
  return `  <jspluginonline name="${WPS_PLUGIN_NAME}" type="wps" url="${url}" enable="true" install="null"/>`;
}

// 返回 {changed, created, entries, foreignPreserved}；幂等=先剥自家旧条目（含历史重复）再插一条最新，
// 他名条目（如竞品/用户已有项）逐字保留
export function injectWpsAddon({ jsaddonsDir, url }) {
  const file = publishXmlPath(jsaddonsDir);
  const existed = existsSync(file);
  const text0 = existed ? readFileSync(file, "utf-8") : "";
  const mineBefore = (text0.match(entryRe(WPS_PLUGIN_NAME)) ?? []).length;
  const foreign = countEntries(text0) - mineBefore;
  let text = text0.replace(entryRe(WPS_PLUGIN_NAME), "").replace(/\n[ \t]*\n/g, "\n");
  const mine = entryXml(url);
  if (!/<jsplugins\b[^>]*>/.test(text)) {
    text = `<?xml version="1.0" encoding="utf-8"?>\n<jsplugins>\n${mine}\n</jsplugins>\n`;
  } else {
    text = text.replace(/<\/jsplugins>/, `${mine}\n</jsplugins>`);
  }
  writeFileSync(file, text, "utf-8");
  return { changed: true, created: !existed, entries: countEntries(text), foreignPreserved: countEntries(text) === foreign + 1 };
}

function countEntries(text) {
  return (text.match(/<jspluginonline\b/g) ?? []).length;
}

// 移除自家条目；文件若为本单元建且条目清零 → 删文件；否则保留他名条目
export function removeWpsAddon({ jsaddonsDir }) {
  const file = publishXmlPath(jsaddonsDir);
  if (!existsSync(file)) return { removed: false, fileDeleted: false, entries: 0 };
  const before = readFileSync(file, "utf-8");
  const after = before.replace(entryRe(WPS_PLUGIN_NAME), "").replace(/\n\s*\n/g, "\n");
  const hasMine = countEntries(before) > countEntries(after);
  if (!hasMine) {
    const zeroResidue = !entryRe(WPS_PLUGIN_NAME).test(before);
    return { removed: false, fileDeleted: false, entries: countEntries(before), zeroResidue };
  }
  if (countEntries(after) === 0) {
    rmSync(file, { force: true });
    return { removed: true, fileDeleted: true, entries: 0, zeroResidue: true };
  }
  writeFileSync(file, after, "utf-8");
  return { removed: true, fileDeleted: false, entries: countEntries(after), zeroResidue: !entryRe(WPS_PLUGIN_NAME).test(after) };
}

// 只读探测：自家条目现状（安装态核对用）
export function wpsAddonState(jsaddonsDir) {
  const file = publishXmlPath(jsaddonsDir);
  if (!existsSync(file)) return { fileExists: false, mine: false, url: null, total: 0 };
  const text = readFileSync(file, "utf-8");
  const m = entryRe(WPS_PLUGIN_NAME).exec(text);
  const url = m ? /url="([^"]*)"/.exec(m[0])?.[1] ?? null : null;
  return { fileExists: true, mine: !!m, url, total: countEntries(text) };
}
