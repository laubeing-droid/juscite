// 功能 #16 调研报告 UI 真形态走查（RE-16 验收）：vite 独立实例（5177，BRIDGE_PORT=3077 隔离桥
// + mock oc28 确定性回合）+ 调试 Chrome 9223 独立 tab + CDP trusted 输入。
// 链路：侧栏「调研报告」入口→面板挂载/空态/法规库提示条（B06）→输入课题→即时规划卡秒上屏（B07/B08）
// →mock 两跳：模型规划替换+阶段播报×2（B08/B14）→五节报告定格 done（B24/B32）→三钮出现
// →导出 MD 通知（B41）→编辑对话框保存 revision（B43）→第二课题发起+手动停止（B04/B37）→
// 历史两条/删除/清空确认（B44/B45）。截图落 evidence 目录；末行 RE16_UI_PASS / RE16_UI_FAIL。
import WebSocket from "ws";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
process.chdir(REPO_ROOT);
const CDP = process.env.CDP_PORT ? "http://127.0.0.1:" + process.env.CDP_PORT : "http://127.0.0.1:9223";
const BRIDGE_PORT = 3077;
const VITE_PORT = 5177;
const APP = `http://localhost:${VITE_PORT}/`;
const OUT = join("evidence", "步骤4-调研报告-RE16-20261027", "ui-walkthrough");
mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`[re16-walk] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── mock oc28（确定性两跳：首跳=规划+阶段一；续跳=阶段二+五节完整报告）──
const FULL_REPORT = [
  "## 阶段二",
  "检索完成，进入综合整理。",
  "",
  "## 结论与建议",
  "综合全部分析，本案请求权基础成立，建议以合同违约作为主要主张，并同时准备不当得利的备位主张，以应对合同效力被否定的风险；同时在庭前补强履约与催告证据，降低举证不能的风险。",
  "## 法律依据与效力",
  "（一）《合成民法典》第二百零九条，现行有效，效力层级为法律；（二）《合成司法解释》第一条，现行有效。",
  "## 相关案例",
  "（2023）合01民终1234号：同类案件支持违约主张；（2022）合01民初5678号：备位主张获支持。",
  "## 分析与风险",
  "主要风险在于证据链是否完整；次要风险在于诉讼时效起算点的认定分歧，建议提前准备中断证据。",
  "## 来源与核验",
  "以上法条与案例均来自所内合成法规库与合成案例库，核验状态为现行有效。",
].join("\n");
const HOP1_TEXT = [
  "## 调研规划",
  "1. 检索股东出资纠纷相关法律法规（模型规划版）",
  "2. 收集典型裁判案例",
  "3. 按五节结构成文并核对来源",
  "",
  "## 阶段一",
  "已梳理课题焦点，开始法规与案例检索。",
].join("\n");
const mockSessions = new Map();
let mockSeq = 0;
const mockServer = createServer((req, res) => {
  const url = req.url ?? "";
  if (req.method === "POST" && url === "/api/session") { res.writeHead(200); res.end("{}"); return; }
  const pm = req.method === "POST" && url.match(/^\/api\/session\/([^/]+)\/prompt$/);
  if (pm) {
    let body = "";
    req.on("data", (c) => (body += String(c)));
    req.on("end", () => {
      const sid = decodeURIComponent(pm[1]);
      const parsed = JSON.parse(body || "{}");
      const list = mockSessions.get(sid) ?? [];
      list.push({ id: parsed.id ?? "u" + mockSeq, type: "user", time: { created: Date.now() }, content: [{ type: "text", text: parsed.text ?? "" }] });
      const isContinuation = (parsed.text ?? "").includes("尚未形成完整");
      const text = isContinuation ? FULL_REPORT : HOP1_TEXT;
      const mid = "a" + mockSeq++;
      const withTools = !isContinuation; // 闭包捕获（setTimeout 内不可见外部块变量 isContinuation）
      setTimeout(() => {
        const l2 = mockSessions.get(sid) ?? [];
        const content = [{ type: "text", text }];
        if (withTools) {
          // 首跳带 tool-call parts（B15）：工具步骤面数据源
          content.push({ type: "tool-call", name: "laws_search", input: "股东出资 法规检索", output: "《合成民法典》" + "第二百零九条 现行有效。".repeat(9) });
          content.push({ type: "tool-call", name: "case_search", input: "股东出资 案例检索", output: "（2023）合01民终1234号 支持违约主张。" });
        }
        l2.push({ id: mid, type: "assistant", time: { created: Date.now(), completed: Date.now() }, content });
        mockSessions.set(sid, l2);
      }, 300);
      mockSessions.set(sid, list);
      res.writeHead(200); res.end("{}");
    });
    return;
  }
  const lm = req.method === "GET" && url.match(/^\/api\/session\/([^/]+)\/message$/);
  if (lm) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ data: mockSessions.get(decodeURIComponent(lm[1])) ?? [] }));
    return;
  }
  res.writeHead(404); res.end("{}");
});
const mockUrl = await new Promise((resolve) => {
  mockServer.listen(0, "127.0.0.1", () => resolve("http://127.0.0.1:" + mockServer.address().port));
});

// ── 隔离桥（3077；独立库；onboarding 直置 completed 免向导遮挡）──
const DB = join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${BRIDGE_PORT}.db`);
const bridgeLog = openSync(join(REPO_ROOT, ".local", `re16-walk-bridge-${BRIDGE_PORT}.log`), "a");
function spawnBridge() {
  const env = { ...process.env, BRIDGE_PORT: String(BRIDGE_PORT), BRIDGE_OC28_SSE: "0", BRIDGE_OC28_URL: mockUrl, BRIDGE_OC28_PASSWORD: "walk" };
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
// 端口清场（kb_synthetic preflight 同款）：残留桥的 mock oc28 已随旧进程失效，必须换新
async function clearPortLeftovers() {
  if (!(await probe())) return;
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const pids = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === BRIDGE_PORT) pids.add(Number(m[2]));
  }
  for (const pid of pids) {
    const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
      { encoding: "utf-8", timeout: 20000 });
    if (String(q.stdout ?? "").includes("bridge_host.mjs")) {
      spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
      console.log("[re16-walk] 清场：杀掉残留桥 pid=" + pid);
    }
  }
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline && (await probe())) await sleep(400);
}
await clearPortLeftovers();
for (const suffix of ["", "-wal", "-shm"]) { try { rmSync(DB + suffix, { force: true }); } catch (e) { console.log("[re16-walk] 删库失败（将续用旧库）:", String(e).slice(0, 60)); } }
let bridgePid = spawnBridge();
{
  const deadline = Date.now() + 40000;
  while (Date.now() < deadline && !(await probe())) await sleep(500);
  // 首建库后置 onboarding=completed（免首启向导遮挡本走查面），再重启桥生效
  try {
    const db = new DatabaseSync(DB);
    db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.status','completed') ON CONFLICT(key) DO UPDATE SET value='completed'").run();
    db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.guideStatus','skipped') ON CONFLICT(key) DO UPDATE SET value='skipped'").run();
    db.close();
  } catch (e) { console.log("[re16-walk] onboarding 预置失败（可能键名不同）：", String(e).slice(0, 80)); }
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  const d2 = Date.now() + 15000;
  while (Date.now() < d2 && (await probe())) await sleep(400);
  bridgePid = spawnBridge();
  const d3 = Date.now() + 40000;
  while (Date.now() < d3 && !(await probe())) await sleep(500);
}
if (!(await probe())) { console.log("RE16_UI_FAIL"); console.error("桥 40s 不可探"); process.exit(1); }

// ── vite 独立实例（5177，代理指向 3077）──
const viteLog = openSync(join(REPO_ROOT, ".local", `re16-walk-vite-${VITE_PORT}.log`), "a");
const vite = spawn(process.execPath, [join(REPO_ROOT, "packages", "web", "node_modules", "vite", "bin", "vite.js"), "--port", String(VITE_PORT), "--strictPort"],
  { cwd: join(REPO_ROOT, "packages", "web"), env: { ...process.env, BRIDGE_PORT: String(BRIDGE_PORT) }, stdio: ["ignore", viteLog, viteLog], detached: true });
vite.unref();
async function viteUp() {
  try {
    const r = await fetch(APP, { signal: AbortSignal.timeout(2500) });
    return r.ok;
  } catch { return false; }
}
{
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline && !(await viteUp())) { process.stdout.write("."); await sleep(1000); }
  console.log("");
}
if (!(await viteUp())) { console.log("RE16_UI_FAIL"); console.error("vite 60s 不可探"); process.exit(1); }
console.log("[re16-walk] vite up:", APP, "bridge:", BRIDGE_PORT);

// ── CDP 接调试 Chrome 9223 ──
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
console.log("[re16-walk] tab:", tab.id, tab.url);
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
  console.log("[re16-walk] shot", name);
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
// window.confirm 自动接受（B45 清空确认）
send("Page.enable");
ws.on("message", (raw) => {
  const m = JSON.parse(raw.toString());
  if (m.method === "Page.javascriptDialogOpening") {
    console.log("[re16-walk] dialog:", m.params.message?.slice(0, 60));
    send("Page.handleJavaScriptDialog", { accept: true }).catch(() => {});
  }
});

await send("Page.navigate", { url: APP });
{ // 等 app 装配（冷 vite 首次模块变换可达 30s+），轮询侧栏导航出现
  let up = false;
  for (let i = 0; i < 60; i++) {
    await sleep(1500);
    up = await evalJs(`!!document.querySelector('[data-testid="sidebar-primary-navigation"]')`).catch(() => false);
    if (up) break;
  }
  console.log("[re16-walk] app shell up:", up);
  await shot("s0-app-shell.png");
}

// ① 侧栏入口 → 面板挂载（B01）
const entry = await evalJs(`!!document.querySelector('[data-testid="research-report-sidebar-open"]')`);
check("侧栏「调研报告」入口可见（B01）", entry === true, String(entry));
await tclick(`document.querySelector('[data-testid="research-report-sidebar-open"]')`);
await sleep(1500);
const mounted = await evalJs(`!!document.querySelector('[data-testid="research-panel"]')`);
check("面板挂载（B01 lazy）", mounted === true, String(mounted));
const empty = await evalJs(`document.querySelector('[data-testid="research-empty"]')?.textContent?.slice(0,40) ?? ""`);
check("空态两行文案（B05）", empty.includes("结构化调研") && empty.includes("自动保存在左侧"), empty);
const hint = await evalJs(`!!document.querySelector('[data-testid="research-laws-hint"]')`);
check("法规库提示条（B06 不阻断）", hint === true, String(hint));
await shot("s1-panel-empty.png");

// ② 输入课题 → 即时规划秒上屏（B07/B08）
const q1 = "请调研股东出资纠纷相关的法律规定与典型案例";
await ttype(`document.querySelector('[data-testid="research-input"]')`, q1);
await tclick(`document.querySelector('[data-testid="research-run"]')`);
await sleep(1200);
const instant = await evalJs(`document.querySelector('[data-testid="research-planning-card"]')?.textContent?.slice(0,80) ?? ""`);
check("即时规划卡秒上屏（B08）", instant.includes("调研规划") && instant.includes("1."), instant);
const liveTool = await evalJs(`document.querySelector('[data-testid="research-live-tool"]')?.textContent ?? ""`);
check("吸顶条当前执行工具名/等待文案（B16）", liveTool.includes("当前执行：") || liveTool.includes("等待下一条结果"), liveTool.slice(0, 40));
const badgeRunning = await evalJs(`document.querySelector('[data-testid="research-status-badge"]')?.textContent ?? ""`);
check("课题徽章 running（B07）", badgeRunning.includes("调研中"), badgeRunning);
await shot("s2-instant-plan.png");

// ③ mock 两跳收口：模型规划替换+阶段×2+五节报告 done（B08/B14/B24/B32）
let doneBody = "";
for (let i = 0; i < 40; i++) {
  await sleep(1000);
  doneBody = await evalJs(`document.querySelector('[data-testid="research-summary-body"]')?.textContent ?? ""`);
  if (doneBody.includes("结论与建议")) break;
}
let badgeTxt = "";
for (let i = 0; i < 30; i++) {
  await sleep(1000);
  badgeTxt = await evalJs(`document.querySelector('[data-testid="research-status-badge"]')?.textContent ?? ""`);
  if (badgeTxt.includes("已完成")) break;
}
check("五节报告流式定格（B17/B24）", doneBody.includes("结论与建议") && doneBody.includes("来源与核验"), doneBody.slice(0, 40));
const planReplaced = await evalJs(`document.querySelector('[data-testid="research-planning-card"]')?.textContent ?? ""`);
check("模型规划替换即时规划（B08）", planReplaced.includes("模型规划版"), "");
const stageBadges = await evalJs(`[...document.querySelectorAll('[data-testid="research-stage-badge"]')].map((e) => e.textContent)`);
check("阶段播报两条+模型阶段号优先（B14）", stageBadges.length === 2 && stageBadges[0] === "阶段1" && stageBadges[1] === "阶段2", stageBadges.join(","));
const badgeDone = await evalJs(`document.querySelector('[data-testid="research-status-badge"]')?.textContent ?? ""`);
check("完成徽章 done（B32）", badgeTxt.includes("已完成"), badgeTxt);
const threeBtns = await evalJs(`["research-edit","research-export-word","research-export-md"].map((t) => !!document.querySelector('[data-testid="' + t + '"]'))`);
check("完成三钮出现（B32）", threeBtns.every(Boolean), threeBtns.join(","));
const historyCount = await evalJs(`document.querySelectorAll('[data-testid="research-history-item"]').length`);
check("历史侧栏条目（B44）", historyCount === 1, String(historyCount));
const stepItems = await evalJs(`[...document.querySelectorAll('[data-testid="research-step-item"]')].map((e) => e.textContent?.slice(0, 24))`);
check("工具步骤卡两条（B15 八类图标接线）", stepItems.length === 2 && stepItems[0].includes("laws_search") && stepItems[1].includes("case_search"), stepItems.join(" | "));
await shot("s3-report-done.png");

// ④ 导出 MD 通知（B41）
await tclick(`document.querySelector('[data-testid="research-export-md"]')`);
await sleep(1500);
const notice = await evalJs(`document.querySelector('[data-testid="research-notice"]')?.textContent ?? ""`);
check("MD 导出成功通知（B41）", notice.includes("已导出") && notice.includes(".md"), notice);
await shot("s4-export-md.png");

// ⑤ 编辑对话框：模式切换+保存 revision（B43）
await tclick(`document.querySelector('[data-testid="research-edit"]')`);
await sleep(800);
const dialogOpen = await evalJs(`!!document.querySelector('[data-testid="research-editor-dialog"]')`);
check("编辑对话框打开（B43）", dialogOpen === true, String(dialogOpen));
await tclick(`document.querySelector('[data-testid="research-editor-mode"]')`); // 切到源码
await sleep(300);
await tclick(`document.querySelector('[data-testid="research-editor-dialog"] textarea')`);
await sleep(200);
await send("Input.dispatchKeyEvent", { type: "keyDown", code: "End", windowsVirtualKeyCode: 35 });
await send("Input.dispatchKeyEvent", { type: "keyUp", code: "End", windowsVirtualKeyCode: 35 });
await send("Input.insertText", { text: "\n\n补记：本报告经人工复核修订。" });
await sleep(200);
await send("Input.dispatchKeyEvent", { type: "keyDown", key: "s", code: "KeyS", modifiers: 2, windowsVirtualKeyCode: 83 }); // Ctrl+S
await send("Input.dispatchKeyEvent", { type: "keyUp", key: "s", code: "KeyS", modifiers: 2, windowsVirtualKeyCode: 83 });
await sleep(1500);
const noticeTxt = await evalJs(`document.querySelector('[data-testid="research-notice"]')?.textContent ?? ""`);
const dialogClosed = await evalJs(`!document.querySelector('[data-testid="research-editor-dialog"]')`);
console.log("[re16-walk] after save: notice=", noticeTxt.slice(0, 50), " dialogClosed=", dialogClosed);
const bodyEdited = await evalJs(`document.querySelector('[data-testid="research-summary-body"]')?.textContent?.includes("人工复核修订")`);
check("Ctrl+S 保存+revision 重渲染（B43）", dialogClosed === true && bodyEdited === true, `closed=${dialogClosed} edited=${bodyEdited}`);
await shot("s5-edited.png");

// ⑥ 第二课题发起+手动停止（B04/B37）
{
  const q2 = "请研究停止语义的走查测试课题";
  const okSet = await evalJs(`(() => { const el = document.querySelector('[data-testid="research-input"]'); if (!el) return false; const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set; set.call(el, ${JSON.stringify(q2)}); el.dispatchEvent(new Event("input", { bubbles: true })); return true; })()`);
  console.log("[re16-walk] q2 set:", okSet);
}
await tclick(`document.querySelector('[data-testid="research-run"]')`);
await sleep(1200);
const stopBtn = await evalJs(`!!document.querySelector('[data-testid="research-stop"]')`);
const inputDisabled = await evalJs(`document.querySelector('[data-testid="research-input"]')?.disabled`);
check("running 时输入禁用+停止钮（B04）", stopBtn === true && inputDisabled === true, `stop=${stopBtn} disabled=${inputDisabled}`);
await tclick(`document.querySelector('[data-testid="research-stop"]')`);
await sleep(1200);
const errBar = await evalJs(`document.querySelector('[data-testid="research-error-bar"]')?.textContent ?? ""`);
check("手动停止落停止文案（B37）", errBar.includes("已停止"), errBar.slice(0, 40));
await shot("s6-stopped.png");

// ⑦ 历史两条 → 删除一条 → 清空确认（B44/B45）
let itemCount = await evalJs(`document.querySelectorAll('[data-testid="research-history-item"]').length`);
check("历史两条（B44）", itemCount === 2, String(itemCount));
{ // hover 条目激活 group-hover 删除钮（hidden 无盒子不可点），再 trusted 点击
  const rectH = await evalJs(`(() => { const el = [...document.querySelectorAll('[data-testid="research-history-item"]')][1]; if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: rectH.x, y: rectH.y });
  await sleep(300);
}
await tclick(`[...document.querySelectorAll('[data-testid="research-history-item"]')][1]?.querySelector('[data-testid="research-item-delete"]')`);
await sleep(800);
itemCount = await evalJs(`document.querySelectorAll('[data-testid="research-history-item"]').length`);
check("删除条目（B44）", itemCount === 1, String(itemCount));
const clearBtn = await evalJs(`!!document.querySelector('[data-testid="research-clear"]')`);
check("有记录才显清空钮（B44）", clearBtn === true, String(clearBtn));
await tclick(`document.querySelector('[data-testid="research-clear"]')`);
await sleep(1000);
itemCount = await evalJs(`document.querySelectorAll('[data-testid="research-history-item"]').length`);
check("清空确认后清空（B45）", itemCount === 0, String(itemCount));
await shot("s7-cleared.png");

// 清场：杀桥+杀 vite+关 tab
spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
try { process.kill(-vite.pid); } catch { try { vite.kill(); } catch { /* 已退 */ } }
try { await fetch(CDP + "/json/close/" + tab.id); } catch { /* tab 可能已关 */ }
mockServer.close();

async function cleanupAll() {
  try { if (bridgePid) await killBridgeVerified(); } catch { /* 已死则忽略 */ }
  try { process.kill(-vite.pid); } catch { try { vite.kill(); } catch { /* 已退 */ } }
  mockServer.close();
}
async function killBridgeVerified() {
  const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${bridgePid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  if (!String(q.stdout ?? "").includes("bridge_host.mjs")) throw new Error("拒绝杀 pid=" + bridgePid + "：不是桥");
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
}
const failed = results.filter((r) => !r.ok);
console.log(`[re16-walk] ── ${results.length - failed.length}/${results.length} PASS ──`);
if (failed.length) {
  console.log("RE16_UI_FAIL");
  for (const f of failed) console.error("  FAIL:", f.name);
  process.exit(1);
} else {
  console.log("RE16_UI_PASS");
}
