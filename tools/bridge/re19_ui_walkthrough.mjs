// 功能 #19 轻量知识图谱 UI 真形态走查（对拍 #16 控制条验收·复审补口）：
//   复审实证缺口=画布左下控制条「放大/缩小/适合窗口」对真实指针点击无响应
//   （根因 CaseGraphPanel.tsx onBackgroundPointerDown 无条件 setPointerCapture 吞 click）；
//   修复=pointerdown 对 button 目标放行（一行）。本走查用 CDP trusted 输入复验：
//   ①三按钮真指针点击缩放读数必变 ②滚轮缩放回归 ③背景拖拽平移回归（放行不得伤平移）。
// 环境：隔离桥 3076（独立库）+ vite 5187 + 调试 Chrome 9223 独立 tab；全合成材料；不碰 :3030/:43127。
// 末行 RE19_UI_PASS / RE19_UI_FAIL。
import WebSocket from "ws";
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import http from "node:http";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
process.chdir(REPO_ROOT);
const CDP = process.env.CDP_PORT ? "http://127.0.0.1:" + process.env.CDP_PORT : "http://127.0.0.1:9223";
const BRIDGE_PORT = 3076;
const VITE_PORT = 5187;
const APP = `http://localhost:${VITE_PORT}/`;
const OUT = join("evidence", "步骤4-轻量知识图谱-RE19-20261028", "ui-walkthrough");
mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`[re19-walk] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 隔离桥（3076，独立库；onboarding 直置 completed 免向导遮挡）──
const DB = join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${BRIDGE_PORT}.db`);
const bridgeLog = openSync(join(REPO_ROOT, ".local", `re19-walk-bridge-${BRIDGE_PORT}.log`), "a");
function spawnBridge() {
  const env = { ...process.env, BRIDGE_PORT: String(BRIDGE_PORT) };
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
async function clearPortLeftovers() {
  if (!(await probe())) return;
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const pids = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === BRIDGE_PORT) pids.add(m[2]);
  }
  for (const pid of pids) {
    const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`], { encoding: "utf-8", timeout: 20000 });
    if (String(q.stdout ?? "").includes("bridge_host.mjs")) {
      spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
      console.log("[re19-walk] 清场：杀掉残留桥 pid=" + pid);
    }
  }
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline && (await probe())) await sleep(400);
}
await clearPortLeftovers();
for (const suffix of ["", "-wal", "-shm"]) { try { rmSync(DB + suffix, { force: true }); } catch { /* 留给下轮 */ } }
{ // 清理同端口陈年 vite（命令行含 vite.js 才动手；上一实例会让 --strictPort 起不来或吃到旧码）
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) !== VITE_PORT) continue;
    const pid = m[2];
    const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`], { encoding: "utf-8", timeout: 20000 });
    if (String(q.stdout ?? "").includes("vite.js")) {
      spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
      console.log("[re19-walk] 清场：杀掉残留 vite pid=" + pid);
    }
  }
}
let bridgePid = spawnBridge();
{
  const deadline = Date.now() + 40000;
  while (Date.now() < deadline && !(await probe())) await sleep(500);
  try {
    const db = new DatabaseSync(DB);
    db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.status','completed') ON CONFLICT(key) DO UPDATE SET value='completed'").run();
    db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.guideStatus','skipped') ON CONFLICT(key) DO UPDATE SET value='skipped'").run();
    const back = db.prepare("SELECT key,value FROM app_meta WHERE key LIKE 'onboarding%'").all();
    db.close();
    console.log("[re19-walk] onboarding 预置读回：", JSON.stringify(back));
    if (!back.some((r) => r.key === "onboarding.status" && r.value === "completed")) throw new Error("读回非 completed");
  } catch (e) { console.log("[re19-walk] onboarding 预置失败：", String(e).slice(0, 120)); }
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  const d2 = Date.now() + 15000;
  while (d2 > Date.now() && (await probe())) await sleep(400);
  bridgePid = spawnBridge();
  const d3 = Date.now() + 40000;
  while (d3 > Date.now() && !(await probe())) await sleep(500);
}
if (!(await probe())) { console.log("RE19_UI_FAIL"); console.error("桥 40s 不可探"); process.exit(1); }

// ── vite 独立实例（5187，代理指向 3076）──
const viteLog = openSync(join(REPO_ROOT, ".local", `re19-walk-vite-${VITE_PORT}.log`), "a");
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
if (!(await viteUp())) { console.log("RE19_UI_FAIL"); console.error("vite 120s 不可探"); process.exit(1); }
console.log("[re19-walk] vite up:", APP, "bridge:", BRIDGE_PORT);

// ── CDP 接调试 Chrome 9223 ──
function getJson(p) {
  return new Promise((res, rej) => {
    http.get(CDP + p, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => { try { res(JSON.parse(d)); } catch (e) { rej(e); } }); }).on("error", rej);
  });
}
// 先清同 URL 旧 tab（僵尸 tab 的渲染器已死，CDP 命令永不应答=卡死根因），恒开新 tab
{
  const stale = (await getJson("/json/list")).filter((t) => t.type === "page" && (t.url || "").startsWith(APP));
  for (const t of stale) { try { await fetch(CDP + "/json/close/" + t.id); } catch { /* 已关 */ } }
}
const tab = await (await fetch(CDP + "/json/new?" + encodeURIComponent(APP), { method: "PUT" })).json();
console.log("[re19-walk] tab:", tab.id, tab.url);
const ws = new WebSocket(tab.webSocketDebuggerUrl, { maxPayload: 128 * 1024 * 1024 });
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
let mid = 0; const pending = new Map();
ws.on("message", (raw) => { const m = JSON.parse(raw.toString()); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++mid; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
await send("Runtime.enable"); await send("Page.enable"); await send("Page.bringToFront", {});
try {
  const { windowId, bounds } = await send("Browser.getWindowForTarget");
  await send("Browser.setWindowBounds", { windowId, bounds: { ...bounds, windowState: "normal", width: 1500, height: 900 } });
} catch { /* 无 Browser 域权限时按原窗口继续 */ }
async function evalJs(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error("EXC: " + (r.exceptionDetails.exception?.description ?? r.exceptionDetails.text).slice(0, 500));
  return r.result?.value;
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(r.data, "base64"));
  console.log("[re19-walk] shot", name);
}
// 真实指针点击（Input.dispatchMouseEvent=trusted，走 pointerdown→mouseup→click 全链）
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
const STAGE = `[document.querySelector('[data-testid="case-graph-canvas"] div[style*="transform"]')]`;
async function readView() {
  const t = await evalJs(`${STAGE}[0]?.style.transform ?? ""`);
  const tr = /translate\(([-\d.]+)px,\s*([-\d.]+)px\)\s*scale\(([\d.]+)\)/.exec(String(t));
  return tr ? { x: Number(tr[1]), y: Number(tr[2]), scale: Number(tr[3]) } : null;
}

await send("Page.navigate", { url: APP });
{ // 等 app 装配
  let up = false;
  for (let i = 0; i < 60; i++) {
    await sleep(1500);
    up = await evalJs(`!!document.querySelector('[data-testid="sidebar-primary-navigation"]')`).catch(() => false);
    if (up) break;
  }
  console.log("[re19-walk] app shell up:", up);
}

// ① 侧栏入口 → 工作台 → #19 面板空态
await tclick(`document.querySelector('[data-testid="legal-workbench-sidebar-open"]')`);
{
  let mounted = false;
  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    mounted = await evalJs(`!!document.querySelector('[data-testid="case-graph"]')`).catch(() => false);
    if (mounted) break;
  }
  check("侧栏进工作台，#19 面板挂载", mounted === true, String(mounted));
}
await sleep(1200);
{
  // 首启向导是强制完成型模态（fixed inset-0 z-[200]）会吞掉全部 trusted 指针——在场即环境未净，fail-fast 不出假数据
  const wizard = await evalJs(`!!document.querySelector('[data-testid="first-run-wizard"]')`).catch(() => "EXC");
  check("首启向导不在场（环境净化守卫）", wizard === false, String(wizard));
}
const emptyEntry = await evalJs(`!!document.querySelector('[data-testid="case-graph-build"]') && !!document.querySelector('[data-testid="case-graph-new"]')`);
check("空态两入口（从案件数据建图/手工新建空图）", emptyEntry === true, String(emptyEntry));
await shot("s0-empty-entry.png");

// ② 手工新建空图 → 添加一个节点（stage/transform 出现，控制条在位）
await tclick(`document.querySelector('[data-testid="case-graph-new"]')`);
{
  let toolbar = false;
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    toolbar = await evalJs(`!!document.querySelector('[data-testid="case-graph-toolbar"]')`).catch(() => false);
    if (toolbar) break;
  }
  check("手工新建空图出工具条", toolbar === true, String(toolbar));
}
await ttype(`document.querySelector('[data-testid="case-graph-add-node-label"]')`, "甲公司");
await tclick(`document.querySelector('[data-testid="case-graph-add-node"]')`);
{
  let node = false;
  for (let i = 0; i < 20; i++) {
    await sleep(500);
    node = await evalJs(`!!document.querySelector('[data-testid="case-graph-node"]')`).catch(() => false);
    if (node) break;
  }
  check("节点卡渲染（stage transform 在位）", node === true, String(node));
}
await sleep(800);
const v0 = await readView();
check("初始 fitView 读数（scale≤1.25）", Boolean(v0) && v0.scale <= 1.251, v0 ? `scale=${v0.scale} x=${v0.x} y=${v0.y}` : "无");
await shot("s1-canvas-node.png");

// ③ 对拍 #16 验收：真指针点「放大」→ 读数必变（×1.2，钳 1.8）
await tclick(`document.querySelector('[aria-label="放大"]')`);
await sleep(500);
const v1 = await readView();
check("真指针点「放大」读数变化（对拍#16）", Boolean(v1) && Math.abs(v1.scale - Math.min(1.8, v0.scale * 1.2)) < 0.01,
  v1 ? `${v0.scale}→${v1.scale}` : "无");
await shot("s2-zoom-in.png");

// ④ 真指针点「适合窗口」→ 回 fit（≤1.25 且小于放大后读数）
await tclick(`document.querySelector('[aria-label="适合窗口"]')`);
await sleep(500);
const v2 = await readView();
check("真指针点「适合窗口」回 fit（对拍#16）", Boolean(v2) && v2.scale <= 1.251 && v2.scale < v1.scale,
  v2 ? `${v1.scale}→${v2.scale}` : "无");
await shot("s3-fit.png");

// ⑤ 真指针点「缩小」→ ÷1.2（钳 0.25）
await tclick(`document.querySelector('[aria-label="缩小"]')`);
await sleep(500);
const v3 = await readView();
check("真指针点「缩小」读数变化（对拍#16）", Boolean(v3) && Math.abs(v3.scale - Math.max(0.25, v2.scale / 1.2)) < 0.01,
  v3 ? `${v2.scale}→${v3.scale}` : "无");
await shot("s4-zoom-out.png");

// ⑥ 滚轮缩放回归（wheel 路径不受修复影响）
{
  const rect = await evalJs(`(() => { const r = document.querySelector('[data-testid="case-graph-canvas"]').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  await send("Input.dispatchMouseEvent", { type: "mouseWheel", x: rect.x, y: rect.y, deltaX: 0, deltaY: -120 });
  await sleep(500);
  const v4 = await readView();
  check("滚轮缩放回归（×1.1）", Boolean(v4) && Math.abs(v4.scale - Math.min(1.8, v3.scale * 1.1)) < 0.011,
    v4 ? `${v3.scale}→${v4.scale}` : "无");
}

// ⑦ 背景拖拽平移回归（修复对 button 放行不得伤平移）
{
  const rect = await evalJs(`(() => { const r = document.querySelector('[data-testid="case-graph-canvas"]').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; })()`);
  const px = rect.x + rect.w - 60, py = rect.y + rect.h - 60; // 右下角空白（避节点/控制条）
  const before = await readView();
  // Chrome 156 CDP 实测：mouseMoved 不带显式 button 字段会被整单丢弃（diag 实证 pointermove 零送达）；
  // 带 button:"left" 后 pointerdown→capture→move→up 全链正常，translate 精确随指针。
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x: px, y: py, button: "left", clickCount: 1, buttons: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: px + 60, y: py + 40, button: "left", buttons: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: px + 120, y: py + 80, button: "left", buttons: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: px + 120, y: py + 80, button: "left", clickCount: 1, buttons: 1 });
  await sleep(500);
  const after = await readView();
  check("背景拖拽平移回归（translate 随指针）", Boolean(before) && Boolean(after)
    && Math.abs(after.x - before.x - 120) <= 2 && Math.abs(after.y - before.y - 80) <= 2,
    after && before ? `dx=${(after.x - before.x).toFixed(1)} dy=${(after.y - before.y).toFixed(1)}` : "无");
}

// 收场：杀自家 vite/桥（杀前核验命令行），tab 留给调试实例
async function killOwn(pid, tag) {
  const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`], { encoding: "utf-8", timeout: 20000 });
  const line = String(q.stdout ?? "").trim();
  if (!line.includes(tag)) { console.log(`[re19-walk] 拒杀 pid=${pid}（不含 ${tag}）`); return; }
  spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
}
try { await killOwn(vite.pid, "vite.js"); } catch { /* 已停 */ }
try { await killOwn(bridgePid, "bridge_host.mjs"); } catch { /* 已停 */ }

const total = results.filter((r) => !r.ok).length;
console.log(`[re19-walk] checks=${results.length} fail=${total}`);
console.log(total === 0 ? "RE19_UI_PASS" : "RE19_UI_FAIL");
process.exit(total === 0 ? 0 : 1);
