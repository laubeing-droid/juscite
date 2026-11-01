#!/usr/bin/env node
// 功能 #13 法条手册 UI 真形态走查（RE-13 完成定义「落地」的渲染面验证）：vite 独立实例（5179，
// BRIDGE_PORT=3079 隔离桥独立库）+ 共享调试 Chrome 9223 独立 tab + CDP trusted 输入。
// 链路：侧栏「法律工作台」→法条手册面板挂载→目录树/分组切换→开法（条号加粗/目录 sheet/关于 sheet）
// →搜索已废法（效力横幅）→篇内过滤（命中高亮）→整法收藏→书签页→偏好面→法条包面。
// 真实内置包（base）；合成输入；收场只杀自家进程+清自家库文件。末行 RE13_UI_PASS / RE13_UI_FAIL。
import WebSocket from "ws";
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
process.chdir(REPO_ROOT);
const CDP = "http://127.0.0.1:9223";
const BRIDGE_PORT = 3079;
const VITE_PORT = 5179;
const APP = `http://localhost:${VITE_PORT}/`;
const OUT = join("evidence", "步骤4-法条手册-RE13-20261028", "ui-walkthrough");
mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, cond, detail = "") {
  results.push({ name, ok: Boolean(cond) });
  console.log(`[re13-walk] ${name}: ${cond ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 隔离桥（3079；独立库；onboarding 直置 completed 免向导遮挡）──
const DB = join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${BRIDGE_PORT}.db`);
const bridgeLog = openSync(join(REPO_ROOT, ".local", `re13-walk-bridge-${BRIDGE_PORT}.log`), "a");
function spawnBridge() {
  const env = { ...process.env, BRIDGE_PORT: String(BRIDGE_PORT), BRIDGE_OC28_SSE: "0", BRIDGE_OC28_PASSWORD: "walk" };
  const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: ["ignore", bridgeLog, bridgeLog], detached: true });
  child.unref();
  return child.pid;
}
async function probe() {
  try {
    const r = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/api/server-info`, { signal: AbortSignal.timeout(2500) });
    return r.ok && JSON.parse(await r.text()).store === "sqlite";
  } catch { return false; }
}
async function killOnPort(port, marker) {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const pids = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === port) pids.add(Number(m[2]));
  }
  for (const pid of pids) {
    const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
      { encoding: "utf-8", timeout: 20000 });
    if (String(q.stdout ?? "").includes(marker)) {
      spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
      const deadline = Date.now() + 20000;
      while (Date.now() < deadline) {
        const r2 = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
        if (!new RegExp(`\\sTCP\\s+\\S*:${port}\\s+\\S+\\s+LISTENING`).test(String(r2.stdout ?? ""))) break;
        await sleep(500);
      }
    } else {
      console.log(`[re13-walk] :${port} 的 pid=${pid} 命令行不含 ${marker}，不动（宁停不误杀）`);
    }
  }
}

// 先占位写 onboarding 跳过标记（库文件由桥首启建表；先建空库再让桥迁移）
try {
  const { DatabaseSync } = await import("node:sqlite");
  const db = new DatabaseSync(DB);
  db.prepare("CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT DEFAULT (datetime('now')))").run();
  db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.status','completed') ON CONFLICT(key) DO UPDATE SET value='completed'").run();
  db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.guideStatus','skipped') ON CONFLICT(key) DO UPDATE SET value='skipped'").run();
  db.close();
} catch (e) { console.log("[re13-walk] onboarding 预置失败：", String(e).slice(0, 80)); }
await killOnPort(BRIDGE_PORT, "bridge_host.mjs");
spawnBridge();
{
  let up = false;
  for (let i = 0; i < 80 && !up; i++) { up = await probe(); if (!up) await sleep(500); }
  if (!up) { console.log("RE13_UI_FAIL"); console.error("桥 40s 不可探"); process.exit(1); }
  console.log("[re13-walk] bridge up:", BRIDGE_PORT, JSON.stringify(await (await fetch(`http://127.0.0.1:${BRIDGE_PORT}/api/server-info`)).json()).slice(0, 120));
}

// ── vite 独立实例（5179，代理指向 3079）──
const viteLog = openSync(join(REPO_ROOT, ".local", `re13-walk-vite-${VITE_PORT}.log`), "a");
const vite = spawn(process.execPath, [join(REPO_ROOT, "packages", "web", "node_modules", "vite", "bin", "vite.js"), "--port", String(VITE_PORT), "--strictPort"],
  { cwd: join(REPO_ROOT, "packages", "web"), env: { ...process.env, BRIDGE_PORT: String(BRIDGE_PORT) }, stdio: ["ignore", viteLog, viteLog], detached: true });
vite.unref();
async function viteUp() {
  try { const r = await fetch(APP, { signal: AbortSignal.timeout(2500) }); return r.ok; } catch { return false; }
}
{
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline && !(await viteUp())) { process.stdout.write("."); await sleep(1000); }
  console.log("");
}
if (!(await viteUp())) { console.log("RE13_UI_FAIL"); console.error("vite 120s 不可探"); process.exit(1); }
console.log("[re13-walk] vite up:", APP, "bridge:", BRIDGE_PORT);

// ── CDP 接共享调试 Chrome 9223 ──
function getJson(p) {
  return new Promise((res, rej) => {
    import("node:http").then((http) => {
      http.default.get(CDP + p, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => { try { res(JSON.parse(d)); } catch (e) { rej(e); } }); }).on("error", rej);
    });
  });
}
const tabs = await getJson("/json/list");
let tab = tabs.find((t) => t.type === "page" && (t.url || "").startsWith(APP));
if (!tab) {
  const r = await fetch(CDP + "/json/new?" + encodeURIComponent(APP), { method: "PUT" });
  tab = await r.json();
}
console.log("[re13-walk] tab:", tab.id, tab.url);
const ws = new WebSocket(tab.webSocketDebuggerUrl, { maxPayload: 128 * 1024 * 1024 });
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
let mid = 0; const pending = new Map();
ws.on("message", (raw) => { const m = JSON.parse(raw.toString()); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++mid; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
await send("Runtime.enable"); await send("Page.enable"); await send("Page.bringToFront", {});
async function evalJs(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error("EXC: " + (r.exceptionDetails.exception?.description ?? r.exceptionDetails.text).slice(0, 400));
  return r.result?.value;
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(r.data, "base64"));
  console.log("[re13-walk] shot", name);
}
async function tclick(expr) {
  const rect = await evalJs(`(() => { const el = (${expr}); if (!el) return null; el.scrollIntoView({ block: "center" }); const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  if (!rect) throw new Error("MISS " + expr.slice(0, 80));
  for (const type of ["mousePressed", "mouseReleased"]) {
    await send("Input.dispatchMouseEvent", { type, x: rect.x, y: rect.y, button: "left", clickCount: 1 });
  }
}
async function ttype(expr, text) {
  await tclick(expr);
  await send("Input.insertText", { text });
}
async function tenter(expr) {
  await tclick(expr);
  for (const type of ["rawKeyDown", "keyUp"]) {
    await send("Input.dispatchKeyEvent", { type, key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13, text: "\r" });
  }
}
const waitFor = async (expr, timeoutMs = 20000) => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await evalJs(expr).catch(() => false)) return true;
    await sleep(600);
  }
  return false;
};

try {
  // ⓪ 冷 vite 首次按需变换可达 30s+（re5/re16 同款经验）：显式导航+等应用壳
  await send("Page.navigate", { url: APP });
  let shellUp = false;
  for (let i = 0; i < 60; i++) {
    await sleep(1500);
    shellUp = await evalJs(`!!document.querySelector('[data-testid="sidebar-primary-navigation"]')`).catch(() => false);
    if (shellUp) break;
  }
  check("应用壳就绪", shellUp);
  await evalJs(`localStorage.removeItem("lawbook.prefs.v1")`); // 前轮偏好持久化会污染步进器初值断言（共享 Chrome profile）
  // ① 侧栏入口 → 法律工作台 → 法条手册面板挂载（分类 ready）
  await tclick(`document.querySelector('[data-testid="legal-workbench-sidebar-open"]')`);
  const mounted = await waitFor(`!!document.querySelector('[data-testid="lawbook-panel"] [data-testid="lawbook-search-input"]')`, 60000);
  check("法条手册面板挂载", mounted);
  const catCount = await evalJs(`document.querySelectorAll('[data-testid="lawbook-cat-item"]').length`);
  check("目录树部门分组渲染（cat≥8）", catCount >= 8, String(catCount));
  await shot("s1-panel.png");

  // ② 分组切换：法律阶位（11 档序表）
  await tclick(`document.querySelector('[data-testid="lawbook-group-level"]')`);
  await sleep(300);
  const levelTxt = await evalJs(`document.querySelector('[data-testid="lawbook-panel"]')?.textContent?.includes("司法解释")`);
  check("阶位分组渲染（含司法解释档）", levelTxt === true);
  await tclick(`document.querySelector('[data-testid="lawbook-group-dept"]')`);

  // ③ 开第一部法：点宪法组 → 法行 → 正文（条号加粗）
  await tclick(`document.querySelectorAll('[data-testid="lawbook-cat-item"]')[0]`);
  const lawRow = await waitFor(`!!document.querySelector('[data-testid="lawbook-law-item"]')`, 15000);
  check("组内法行展开", lawRow);
  await tclick(`document.querySelectorAll('[data-testid="lawbook-law-item"]')[0]`);
  const contentUp = await waitFor(`!!document.querySelector('[data-testid="lawbook-content-title"]')`, 30000);
  check("中栏正文标题渲染", contentUp, await evalJs(`document.querySelector('[data-testid="lawbook-content-title"]')?.textContent ?? ""`));
  const boldArticle = await evalJs(`!!document.querySelector('[data-testid="lawbook-content-body"] strong')`);
  check("条号加粗（B3）", boldArticle);
  await shot("s2-content.png");

  // ④ 目录 sheet（B4）+ 点击锚点关闭
  await tclick(`document.querySelector('[data-testid="lawbook-toc-btn"]')`);
  const sheetUp = await waitFor(`!!document.querySelector('[data-testid="lawbook-toc-sheet"]')`, 8000);
  check("目录 sheet 打开（B4）", sheetUp);
  await tclick(`document.querySelector('[data-testid="lawbook-toc-sheet"] [data-testid="lawbook-toc-item"]')`);
  const sheetGone = await waitFor(`!document.querySelector('[data-testid="lawbook-toc-sheet"]')`, 8000);
  check("目录项点击关 sheet（等量交互）", sheetGone);

  // ⑤ 关于 sheet（B5 信息块）
  await tclick(`document.querySelector('[data-testid="lawbook-about-btn"]')`);
  const aboutUp = await waitFor(`!!document.querySelector('[data-testid="lawbook-about-sheet"]')`, 8000);
  check("关于 sheet 打开（B5）", aboutUp);
  await tclick(`document.querySelector('[data-testid="lawbook-dialog-close"]')`);
  await sleep(300);

  // ⑥ 搜索已废法：效力横幅（B2）+ ver>1 公布日
  await ttype(`document.querySelector('[data-testid="lawbook-search-input"]')`, "合同法");
  await tclick(`document.querySelector('[data-testid="lawbook-search-go"]')`);
  const searched = await waitFor(`!!document.querySelector('[data-testid="lawbook-search-results"] [data-testid="lawbook-law-item"]')`, 20000);
  check("搜索结果渲染（C1）", searched);
  // 点名为「合同法」的那一行（行内含 ⚠/公布日期等杂串，用 includes 匹配；「民法典 合同编」不含「合同法」串不误中）
  await tclick(`(() => { const rows = [...document.querySelectorAll('[data-testid="lawbook-search-results"] [data-testid="lawbook-law-item"]')]; const el = rows.find((r) => (r.textContent ?? "").includes("合同法")); return el ?? null; })()`);
  const banner = await waitFor(`!!document.querySelector('[data-testid="lawbook-banner-repealed"]')`, 30000);
  check("已废法效力横幅（B2 灰⚠）", banner);
  await shot("s3-repealed-banner.png");

  // ⑦ 篇内过滤：命中段 + 高亮（B6）
  await ttype(`document.querySelector('[data-testid="lawbook-filter-input"]')`, "合同");
  await tenter(`document.querySelector('[data-testid="lawbook-filter-input"]')`);
  const hits = await waitFor(`!!document.querySelector('[data-testid="lawbook-filter-hits"] mark')`, 20000);
  check("篇内过滤命中高亮（B6）", hits);
  await shot("s4-filter-hits.png");

  // ⑧ 整法收藏（B9 心形）→ 书签页（D3）
  await tclick(`document.querySelector('[data-testid="lawbook-heart"]')`);
  await sleep(800);
  await tclick(`document.querySelector('[data-testid="lawbook-bookmarks"]')`);
  const bmView = await waitFor(`!!document.querySelector('[data-testid="lawbook-bookmarks"]')`, 8000);
  check("书签子页切换", bmView);
  // 新建夹（经输入+按钮）
  await ttype(`document.querySelector('[data-testid="lawbook-bm-new-name"]')`, "走查夹");
  await tclick(`document.querySelector('[data-testid="lawbook-bm-new-go"]')`);
  const folderRow = await waitFor(`!!document.querySelector('[data-testid="lawbook-bm-folder"]')`, 10000);
  check("书签夹新建（D2）", folderRow);
  await shot("s5-bookmarks.png");

  // ⑨ 偏好面（G1 步进器）
  await tclick(`document.querySelector('[data-testid="lawbook-settings-btn"]')`);
  const setSheet = await waitFor(`!!document.querySelector('[data-testid="lawbook-settings-sheet"]')`, 8000);
  check("阅读偏好面打开（G1）", setSheet);
  const before = await evalJs(`document.querySelector('[data-testid="lawbook-pref-font"]')?.textContent`);
  await tclick(`document.querySelector('[data-testid="lawbook-pref-font-inc"]')`);
  await sleep(200);
  const after = await evalJs(`document.querySelector('[data-testid="lawbook-pref-font"]')?.textContent`);
  check("字号步进器（步进+1，值域内到界停走）", Number(after) === Number(before) + 1, `${before}→${after}`);
  await tclick(`document.querySelector('[data-testid="lawbook-dialog-close"]')`);
  await sleep(300);

  // ⑩ 法条包面（E 线：base 包正常态）
  await tclick(`document.querySelector('[data-testid="lawbook-packs-btn"]')`);
  const packRow = await waitFor(`document.querySelector('[data-testid="lawbook-pack-row"]')?.textContent?.includes("正常")`, 8000);
  check("法条包面（base 正常+法条计数）", packRow === true, await evalJs(`document.querySelector('[data-testid="lawbook-pack-row"]')?.textContent ?? ""`));
  await shot("s6-packs.png");
} catch (e) {
  check("走查异常", false, String(e).slice(0, 300));
  try { await shot("z-crash.png"); } catch { /* ignore */ }
} finally {
  const pass = results.every((r) => r.ok);
  console.log(`[re13-walk] ${results.filter((r) => r.ok).length}/${results.length} checks`);
  // ── 收场：只杀自家进程 + 清自家库 ──
  try { await fetch(CDP + "/json/close/" + tab.id); } catch { /* ignore */ }
  await killOnPort(VITE_PORT, "vite.js");
  await killOnPort(BRIDGE_PORT, "bridge_host.mjs");
  for (const suffix of [".db", ".db-wal", ".db-shm"]) {
    try { rmSync(join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${BRIDGE_PORT}${suffix}`), { force: true }); } catch { /* ignore */ }
  }
  console.log(pass ? "RE13_UI_PASS" : "RE13_UI_FAIL");
  process.exit(pass ? 0 : 1);
}
