#!/usr/bin/env node
// WPS sideload CLI（方案 §五 S4）：版本门槛检查 → publish.xml 注入/移除（幂等）→ 回读核对。
//   安装：node cli/wps-sideload.mjs --port 3128 [--jsaddons-dir <dir>（默认真实 %APPDATA%\kingsoft\wps\jsaddons）]
//   移除：node cli/wps-sideload.mjs --remove [--jsaddons-dir <dir>]
// 输出末行 WPS_SIDELOAD_OK / WPS_SIDELOAD_FAIL / WPS_SIDELOAD_REMOVE_CLEAN / WPS_SIDELOAD_REMOVE_DIRTY。
// 注入 url 指向双适配页 /taskpane/（方案 §五 S4 的 /wps/ 示形与实形差异见证据文件——双适配单页同源伺服）。
import { versionAtLeast, detectWpsVersion, injectWpsAddon, removeWpsAddon, wpsAddonState } from "../src/wps-install.mjs";
import { join } from "node:path";

const args = process.argv.slice(2);
function flagOf(name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
}
const remove = args.includes("--remove");
const port = Number(flagOf("--port") ?? 0);
const jsaddonsDir = flagOf("--jsaddons-dir") ?? join(process.env.APPDATA ?? ".", "kingsoft", "wps", "jsaddons");

if (!remove && (!Number.isInteger(port) || port < 1 || port > 65535)) {
  console.error("用法: node cli/wps-sideload.mjs --port <桥端口> [--remove] [--jsaddons-dir <dir>]");
  process.exit(2);
}

if (remove) {
  const r = removeWpsAddon({ jsaddonsDir });
  const verify = wpsAddonState(jsaddonsDir);
  console.log(`removed=${r.removed} fileDeleted=${r.fileDeleted} entries=${r.entries ?? verify.total}`);
  const clean = !verify.mine;
  console.log(clean ? "WPS_SIDELOAD_REMOVE_CLEAN" : "WPS_SIDELOAD_REMOVE_DIRTY");
  process.exit(clean ? 0 : 1);
}

const version = detectWpsVersion();
console.log(`wpsVersion=${version ?? "未检出"} 门槛=${"6.13.0"}`);
if (!versionAtLeast(version)) {
  console.log("WPS_SIDELOAD_FAIL");
  console.error("WPS 版本未达门槛（fail-closed，不猜）");
  process.exit(1);
}
const url = `http://127.0.0.1:${port}/taskpane/`;
const r = injectWpsAddon({ jsaddonsDir, url });
const verify = wpsAddonState(jsaddonsDir);
console.log(`changed=${r.changed} created=${r.created} entries=${verify.total} foreignPreserved=${r.foreignPreserved}`);
const ok = verify.mine && verify.url === url && r.foreignPreserved;
console.log(ok ? "WPS_SIDELOAD_OK" : "WPS_SIDELOAD_FAIL");
process.exit(ok ? 0 : 1);
