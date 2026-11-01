#!/usr/bin/env node
// Word sideload CLI（方案 §五 S3）：manifest 落地 %LOCALAPPDATA%\Juscite\OfficePlugin\word\ →
// reg add HKCU\Software\Microsoft\Office\16.0\Wef\Developer /v <Id> （/reg:64 与 /reg:32 各一次）→ 回读校验。
// 卸载（--remove）：两视图 reg delete + manifest 目录删除，回读确认零残留。
// ⚠ 本机实测状态：本机 Word=2007（Office.Application.12，无 WEF/Office.js 子系统）——本 CLI 在本机
// 属"写好未跑"（S3 阻塞，见证据文件）；首次真实使用前必须先核验目标机存在 16.0 WEF 能力。
// 用法：node cli/sideload-word.mjs --port 3128 [--remove]
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = fileURLToPath(new URL("..", import.meta.url)); // packages/juscite-office-bridge/

const ADDIN_ID = "7f4a2c91-6d3b-4e58-9a10-52b6c8d9e3a1"; // 与 manifests/word-manifest.template.xml 的 <Id> 同源
const WEF_KEY = "HKCU\\Software\\Microsoft\\Office\\16.0\\Wef\\Developer";

const args = process.argv.slice(2);
function flagOf(name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
}
const port = Number(flagOf("--port") ?? 0);
const remove = args.includes("--remove");
if (!remove && (!Number.isInteger(port) || port < 1 || port > 65535)) {
  console.error("用法: node cli/sideload-word.mjs --port <桥端口> [--remove]");
  process.exit(2);
}

function reg(args2) {
  const r = spawnSync("reg", args2, { encoding: "utf-8", timeout: 20000 });
  return { code: r.status, out: String(r.stdout ?? ""), err: String(r.stderr ?? "") };
}

function wefValueName() { return `{${ADDIN_ID.toUpperCase()}}`; }

if (remove) {
  let cleaned = true;
  for (const view of ["64", "32"]) {
    const q = reg(["query", WEF_KEY, "/reg:" + view]);
    if (!q.out.toUpperCase().includes(ADDIN_ID.toUpperCase())) continue;
    const d = reg(["delete", WEF_KEY, "/v", wefValueName(), "/f", "/reg:" + view]);
    if (d.code !== 0) { cleaned = false; console.error(`reg delete /reg:${view} 失败: ${d.err}`); }
  }
  const verify64 = reg(["query", WEF_KEY, "/reg:64"]).out;
  const verify32 = reg(["query", WEF_KEY, "/reg:32"]).out;
  const residue = [verify64, verify32].some((o) => o.toUpperCase().includes(ADDIN_ID.toUpperCase()));
  rmSync(join(process.env.LOCALAPPDATA ?? ".", "Juscite", "OfficePlugin", "word"), { recursive: true, force: true });
  console.log(residue || !cleaned ? "WORD_SIDELOAD_REMOVE_DIRTY" : "WORD_SIDELOAD_REMOVE_CLEAN");
  process.exit(residue || !cleaned ? 1 : 0);
}

// ── 安装 ──
const manifestDir = join(process.env.LOCALAPPDATA ?? ".", "Juscite", "OfficePlugin", "word");
mkdirSync(manifestDir, { recursive: true });
const template = readFileSync(join(PKG_ROOT, "manifests", "word-manifest.template.xml"), "utf-8");
const manifestPath = join(manifestDir, "manifest.xml");
writeFileSync(manifestPath, template.replaceAll("{{PORT}}", String(port)), "utf-8");

let ok = true;
for (const view of ["64", "32"]) {
  const a = reg(["add", WEF_KEY, "/v", wefValueName(), "/t", "REG_SZ", "/d", manifestPath, "/f", "/reg:" + view]);
  if (a.code !== 0) { ok = false; console.error(`reg add /reg:${view} 失败: ${a.err}`); }
}
for (const view of ["64", "32"]) {
  const q = reg(["query", WEF_KEY, "/v", wefValueName(), "/reg:" + view]);
  if (!q.out.includes(manifestPath)) { ok = false; console.error(`回读校验失败 /reg:${view}`); }
}
console.log(`manifest=${manifestPath}`);
console.log(ok ? "WORD_SIDELOAD_OK" : "WORD_SIDELOAD_FAIL");
process.exit(ok ? 0 : 1);
