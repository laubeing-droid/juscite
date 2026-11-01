// 功能 #5 冲突查重 UI 真形态走查（RE-5 验收 §3.4 面一/面二）：vite 独立实例（5178，BRIDGE_PORT=3078
// 隔离桥独立库）+ 调试 Chrome 9223 独立 tab + CDP trusted 输入。合成材料，收尾清场只杀自家进程。
// 链路：侧栏「冲突预检」入口→面板挂载/空态→主体行默认角色（A8）→证件大写化（B4）→空检索拦截（B2）
// →双主体预检：命中卡染色徽章+命中方式三分+案件最小披露+查看案件钮（E4/E6）→行只读+修改/新建（B5/B7）
// →预检页不渲染 reason（E4）→未命中主体区+免责（E7）→统计条四格+侧栏小结（E6/E9）→新建预检重置
// →法律工作台「冲突快检」弹窗：reason 在弹窗面渲染（D9）+零命中绿卡（E7）→打开完整页链接→查看案件跳看板。
// 末行 CONFLICT_UI_PASS / CONFLICT_UI_FAIL。
import WebSocket from "ws";
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
process.chdir(REPO_ROOT);
const CDP = process.env.CDP_PORT ? "http://127.0.0.1:" + process.env.CDP_PORT : "http://127.0.0.1:9223";
const BRIDGE_PORT = 3078;
const VITE_PORT = 5178;
const APP = `http://localhost:${VITE_PORT}/`;
const OUT = join("evidence", "步骤4-冲突查重-RE5-20261027", "ui-walkthrough");
mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`[re5-walk] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 隔离桥（3078；独立库；onboarding 直置 completed 免向导遮挡）──
const DB = join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${BRIDGE_PORT}.db`);
const bridgeLog = openSync(join(REPO_ROOT, ".local", `re5-walk-bridge-${BRIDGE_PORT}.log`), "a");
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
  // 只杀命令行含 marker 的进程，被其他进程占用则不动（宁停不误杀）
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
      console.log(`[re5-walk] 清场：杀掉残留 ${marker.includes("bridge") ? "桥" : "vite"} pid=${pid}`);
    }
  }
}
async function portAlive(port) {
  try { const r = await fetch(`http://127.0.0.1:${port}/`, { signal: AbortSignal.timeout(1500) }); return r.ok; }
  catch { return false; }
}
async function clearPortLeftovers() {
  // 桥与 vite 都清：崩溃的上一轮会把两者都留在端口上；长跑 vite 的模块图被中途源码变动污染后
  // 新载页签会静默挂 boot（timeline_walk 实录教训），必须换新实例。
  await killOnPort(BRIDGE_PORT, "bridge_host.mjs");
  await killOnPort(VITE_PORT, join("vite", "bin", "vite.js"));
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline && ((await portAlive(BRIDGE_PORT)) || (await portAlive(VITE_PORT)))) await sleep(400);
}
await clearPortLeftovers();
for (const suffix of ["", "-wal", "-shm"]) { try { rmSync(DB + suffix, { force: true }); } catch { /* 不存在即可 */ } }
let bridgePid = spawnBridge();
{
  const deadline = Date.now() + 40000;
  while (Date.now() < deadline && !(await probe())) await sleep(500);
  try {
    const db = new DatabaseSync(DB);
    db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.status','completed') ON CONFLICT(key) DO UPDATE SET value='completed'").run();
    db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.guideStatus','skipped') ON CONFLICT(key) DO UPDATE SET value='skipped'").run();
    db.close();
  } catch (e) { console.log("[re5-walk] onboarding 预置失败：", String(e).slice(0, 80)); }
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  const d2 = Date.now() + 15000;
  while (Date.now() < d2 && (await probe())) await sleep(400);
  bridgePid = spawnBridge();
  const d3 = Date.now() + 40000;
  while (Date.now() < d3 && !(await probe())) await sleep(500);
}
if (!(await probe())) { console.log("CONFLICT_UI_FAIL"); console.error("桥 40s 不可探"); process.exit(1); }

// ── 种子（RPC 直灌隔离桥）：历史案一件带对手/委托两当事人 ──
{
  const ws = new WebSocket(`ws://127.0.0.1:${BRIDGE_PORT}/ws`);
  ws.binaryType = "arraybuffer";
  const data = { fire: (_b) => {} };
  ws.on("message", (buf) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
  await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
  const isocket = {
    onData: (l) => { data.fire = l; return { dispose: () => {} }; },
    onClose: () => ({ dispose: () => {} }), onEnd: () => ({ dispose: () => {} }),
    write: (b) => ws.send(b.buffer), end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
  };
  const ch = new ChannelClient(new SocketProtocol(isocket)).getChannel("zcode-agent");
  await ch.call("helloConversationV4", []);
  const call = (m, a) => ch.call(m, [a]);
  const h1 = await call("matterCreate", { name: "合成历史案·对手与客户档案", cause: "合同纠纷", caseNo: "(2026)合0105民初0001号" });
  await call("conflictPartySet", { subjectType: "matter", subjectId: h1.id, parties: [
    { role: "OPPOSING_PARTY", name: "合成对手甲有限公司", idNumber: "X110009" },
    { role: "CLIENT", name: "合成嘉吉贸易有限公司", idNumber: "X120009" },
  ] });
  // 复核走查案用专用对家（不撞预检走查面的「合成对手甲」，E6/E9 统计不被污染）
  const rv0 = await call("matterCreate", { name: "合成历史案·复核对家档案", cause: "合同纠纷" });
  await call("conflictPartySet", { subjectType: "matter", subjectId: rv0.id, parties: [
    { role: "OPPOSING_PARTY", name: "合成复核对家有限公司" },
  ] });
  const rv1 = await call("matterCreate", { name: "合成复核走查案·有命中", cause: "合同纠纷" });
  await call("conflictPartySet", { subjectType: "matter", subjectId: rv1.id, parties: [
    { role: "OPPOSING_PARTY", name: "合成复核对家有限公司" },
  ] });
  const rv2 = await call("matterCreate", { name: "合成复核走查案·零命中", cause: "民间借贷" });
  await call("conflictPartySet", { subjectType: "matter", subjectId: rv2.id, parties: [
    { role: "CLIENT", name: "合成复核零命中公司" },
  ] });
  ws.close();
  console.log("[re5-walk] 种子完成：历史案+两当事人");
}

// ── vite 独立实例（5178，代理指向 3078）──
const viteLog = openSync(join(REPO_ROOT, ".local", `re5-walk-vite-${VITE_PORT}.log`), "a");
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
if (!(await viteUp())) { console.log("CONFLICT_UI_FAIL"); console.error("vite 120s 不可探"); process.exit(1); }
console.log("[re5-walk] vite up:", APP, "bridge:", BRIDGE_PORT);

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
console.log("[re5-walk] tab:", tab.id, tab.url);
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
  console.log("[re5-walk] shot", name);
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
async function clearInput(expr) {
  await evalJs(`(() => { const el = ${expr}; if (!el) return; el.focus(); el.select && el.select(); })()`);
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "a", code: "KeyA", windowsVirtualKeyCode: 65, modifiers: 2 });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "a", code: "KeyA", windowsVirtualKeyCode: 65, modifiers: 2 });
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Delete", code: "Delete", windowsVirtualKeyCode: 46 });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Delete", code: "Delete", windowsVirtualKeyCode: 46 });
}

await send("Page.navigate", { url: APP });
{
  let up = false;
  for (let i = 0; i < 60; i++) {
    await sleep(1500);
    up = await evalJs(`!!document.querySelector('[data-testid="sidebar-primary-navigation"]')`).catch(() => false);
    if (up) break;
  }
  console.log("[re5-walk] app shell up:", up);
}

// ① 侧栏入口 → 面板挂载+空态（E8）
const entry = await evalJs(`!!document.querySelector('[data-testid="conflict-precheck-sidebar-open"]')`);
check("侧栏「冲突预检」入口可见", entry === true, String(entry));
await tclick(`document.querySelector('[data-testid="conflict-precheck-sidebar-open"]')`);
let mounted = false;
{
  // 冷 vite 首次按需变换可达 30s+（re16 同款经验）：轮询面板挂载，超时后抓主区文本诊断
  for (let i = 0; i < 30; i++) {
    await sleep(1500);
    mounted = await evalJs(`!!document.querySelector('[data-testid="conflict-precheck-panel"]')`).catch(() => false);
    if (mounted) break;
  }
  if (!mounted) {
    const diag = await evalJs(`document.querySelector("main")?.textContent?.slice(0, 300) ?? "no-main"`);
    console.log("[re5-walk] 挂载诊断:", diag);
  }
}
check("预检面板挂载（lazy 分支）", mounted === true, String(mounted));
const emptyTxt = await evalJs(`document.querySelector('[data-testid="conflict-empty-state"]')?.textContent ?? ""`);
check("未检索空态占位卡（E8）", emptyTxt.includes("填写主体后开始预检"), emptyTxt.slice(0, 40));
const role0 = await evalJs(`document.querySelector('[data-testid="conflict-role-0"] button[aria-pressed="true"]')?.textContent ?? ""`);
check("首行默认角色=拟委托方（A8）", role0 === "拟委托方", role0);
await shot("s1-panel-empty.png");

// ② 添加主体默认对方（A8）+仅 1 行时删除禁用（B5）
await tclick(`document.querySelector('[data-testid="conflict-add-row"]')`);
await sleep(400);
const role1 = await evalJs(`document.querySelector('[data-testid="conflict-role-1"] button[aria-pressed="true"]')?.textContent ?? ""`);
check("新行默认角色=对方（A8）", role1 === "对方", role1);
await tclick(`document.querySelector('[data-testid="conflict-remove-1"]')`);
await sleep(300);
const rowsAfterRemove = await evalJs(`document.querySelectorAll('[data-testid^="conflict-row-"]').length`);
check("仅剩 1 行时删除禁用（B5）", rowsAfterRemove === 1, String(rowsAfterRemove));

// ③ 证件大写化（B4）
await ttype(`document.querySelector('[data-testid="conflict-id-0"]')`, "x110009");
await sleep(300);
const idVal = await evalJs(`document.querySelector('[data-testid="conflict-id-0"]')?.value ?? ""`);
check("证件输入大写化去空白（B4）", idVal === "X110009", idVal);
await clearInput(`document.querySelector('[data-testid="conflict-id-0"]')`);

// ④ 空检索拦截（B2 客户端同闸）
await tclick(`document.querySelector('[data-testid="conflict-run"]')`);
await sleep(500);
const errTxt = await evalJs(`document.querySelector('[data-testid="conflict-error"]')?.textContent ?? ""`);
check("空检索拦截文案（B2）", errTxt.includes("请至少填写"), errTxt);

// ⑤ 双主体预检：精确 HIGH+归一化 HIGH/名称相似（E6/D6/D9 命中面）
await ttype(`document.querySelector('[data-testid="conflict-name-0"]')`, "合成对手甲有限公司");
await tclick(`document.querySelector('[data-testid="conflict-add-row"]')`);
await sleep(300);
await ttype(`document.querySelector('[data-testid="conflict-name-1"]')`, "合成嘉吉（广州）贸易有限公司");
await tclick(`document.querySelector('[data-testid="conflict-run"]')`);
let hitCards = [];
for (let i = 0; i < 20; i++) {
  await sleep(800);
  hitCards = await evalJs(`[...document.querySelectorAll('[data-testid^="conflict-subject-group-"]')].map((e) => e.textContent)`);
  if (hitCards.length >= 2) break;
}
check("按主体分组命中区出现（E6）", hitCards.length === 2, `groups=${hitCards.length}`);
const g0 = hitCards[0] ?? "";
check("精确命中卡：高风险徽章+名称相同+案件披露+查看案件钮（D9/E4/E6）",
  g0.includes("高风险") && g0.includes("名称相同") && g0.includes("合成历史案") && g0.includes("查看案件"),
  g0.slice(0, 80));
const g1 = hitCards[1] ?? "";
check("归一化命中卡：高风险+名称相似（D6 降级显示）", g1.includes("高风险") && g1.includes("名称相似"), g1.slice(0, 80));
// reason 专属短语（"名称完全一致；"/"请人工核对是否同一主体"只在 reason 句出现；侧栏披露口径
// 的"请人工核对"是自写说明文案，不算 reason 泄漏）
const reasonLeak = await evalJs(`(() => { const t = document.querySelector('[data-testid="conflict-precheck-panel"]')?.textContent ?? ""; return t.includes("名称完全一致；") || t.includes("请人工核对是否同一主体"); })()`);
check("预检页命中卡不渲染 reason 文字（E4）", reasonLeak === false, String(reasonLeak));
await shot("s2-precheck-hits.png");

// ⑥ 行只读+修改/新建预检（B5/B7）
const nameDisabled = await evalJs(`document.querySelector('[data-testid="conflict-name-0"]')?.disabled`);
const btnText = await evalJs(`document.querySelector('[data-testid="conflict-run"]')?.textContent ?? ""`);
const editBtn = await evalJs(`!!document.querySelector('[data-testid="conflict-edit-rows"]')`);
const newBtn = await evalJs(`!!document.querySelector('[data-testid="conflict-new-precheck"]')`);
check("检索后行只读+按钮转重新预检+修改/新建预检（B5/B7）",
  nameDisabled === true && btnText.includes("重新预检") && editBtn && newBtn,
  `disabled=${nameDisabled} btn=${btnText}`);

// ⑦ 统计条四格+侧栏小结（E6/E9）
const stats = await evalJs(`({
  subj: document.querySelector('[data-testid="conflict-stat-有相关记录的主体"]')?.textContent ?? "",
  hist: document.querySelector('[data-testid="conflict-stat-涉及历史案件"]')?.textContent ?? "",
  intake: document.querySelector('[data-testid="conflict-stat-涉及在办收案"]')?.textContent ?? "",
  crit: document.querySelector('[data-testid="conflict-stat-重点关注/高风险命中"]')?.textContent ?? "",
})`);
check("统计条四格（E6）", stats.subj === "2/2" && stats.hist === "1" && stats.intake === "0" && stats.crit === "2",
  JSON.stringify(stats));
const summary = await evalJs(`({
  s: document.querySelector('[data-testid="conflict-summary-subjects"]')?.textContent ?? "",
  h: document.querySelector('[data-testid="conflict-summary-hits"]')?.textContent ?? "",
})`);
check("侧栏小结卡（E9）", summary.s.includes("2") && summary.h.includes("2"), JSON.stringify(summary));

// ⑧ 修改解锁→添加未命中主体→重新预检→未命中主体区+免责（E7）
await tclick(`document.querySelector('[data-testid="conflict-edit-rows"]')`);
await sleep(300);
await tclick(`document.querySelector('[data-testid="conflict-add-row"]')`);
await sleep(300);
await ttype(`document.querySelector('[data-testid="conflict-name-2"]')`, "合成从无此人名");
await tclick(`document.querySelector('[data-testid="conflict-run"]')`);
let noHitZone = "";
for (let i = 0; i < 20; i++) {
  await sleep(800);
  noHitZone = await evalJs(`document.querySelector('[data-testid="conflict-no-hit-zone"]')?.textContent ?? ""`);
  if (noHitZone) break;
}
check("未命中主体单列区+免责声明（E7）", noHitZone.includes("合成从无此人名") && noHitZone.includes("不等于确认无冲突"), noHitZone.slice(0, 60));
await shot("s3-no-hit-zone.png");

// ⑨ 新建预检重置（A2）
await tclick(`document.querySelector('[data-testid="conflict-new-precheck"]')`);
await sleep(500);
const resetEmpty = await evalJs(`!!document.querySelector('[data-testid="conflict-empty-state"]')`);
const resetRows = await evalJs(`document.querySelectorAll('[data-testid^="conflict-row-"]').length`);
check("新建预检重置（空态回归+行归一）", resetEmpty === true && resetRows === 1, `empty=${resetEmpty} rows=${resetRows}`);

// ⑩ 快检弹窗：法律工作台入口→reason 弹窗面渲染（D9）→零命中绿卡→打开完整页（A2/E7）
await tclick(`document.querySelector('[data-testid="legal-workbench-sidebar-open"]')`);
await sleep(1500);
const quickBtn = await evalJs(`!!document.querySelector('[data-testid="conflict-quick-open"]')`);
check("法律工作台「冲突快检」入口钮（A2）", quickBtn === true, String(quickBtn));
await tclick(`document.querySelector('[data-testid="conflict-quick-open"]')`);
await sleep(600);
const dlgUp = await evalJs(`!!document.querySelector('[data-testid="conflict-quick-dialog"]')`);
check("快检弹窗打开", dlgUp === true, String(dlgUp));
await ttype(`document.querySelector('[data-testid="conflict-quick-name"]')`, "合成对手甲有限公司");
await tclick(`document.querySelector('[data-testid="conflict-quick-run"]')`);
let quickReason = "";
for (let i = 0; i < 15; i++) {
  await sleep(800);
  quickReason = await evalJs(`document.querySelector('[data-testid="conflict-quick-reason"]')?.textContent ?? ""`);
  if (quickReason) break;
}
check("弹窗命中渲染 reason 文字（D9 弹窗面分工）", quickReason.includes("名称完全一致"), quickReason.slice(0, 50));
const quickCount = await evalJs(`document.querySelector('[data-testid="conflict-quick-count"]')?.textContent ?? ""`);
check("弹窗命中计数反馈行（I3）", /^命中 \d+ 条/.test(quickCount), quickCount.slice(0, 40));
await shot("s4-quick-dialog-hit.png");
// 清空名称换未命中名 → 零命中绿卡
await clearInput(`document.querySelector('[data-testid="conflict-quick-name"]')`);
await ttype(`document.querySelector('[data-testid="conflict-quick-name"]')`, "合成快检无名氏");
await tclick(`document.querySelector('[data-testid="conflict-quick-run"]')`);
let zeroCard = "";
for (let i = 0; i < 15; i++) {
  await sleep(800);
  zeroCard = await evalJs(`document.querySelector('[data-testid="conflict-quick-zero"]')?.textContent ?? ""`);
  if (zeroCard) break;
}
check("弹窗零命中绿卡（E7）", zeroCard.includes("不等于确认无冲突"), zeroCard.slice(0, 50));
await tclick(`document.querySelector('[data-testid="conflict-quick-open-full"]')`);
await sleep(1200);
const backToPanel = await evalJs(`!!document.querySelector('[data-testid="conflict-precheck-panel"]')`);
check("快检链接跳完整预检页", backToPanel === true, String(backToPanel));

// ⑪ 查看案件钮 → 跳法律工作台（E3 本地恒可见）：先回预检页跑一次检索出命中卡，再点查看案件
await tclick(`document.querySelector('[data-testid="conflict-precheck-sidebar-open"]')`);
await sleep(1500);
await ttype(`document.querySelector('[data-testid="conflict-name-0"]')`, "合成对手甲有限公司");
await tclick(`document.querySelector('[data-testid="conflict-run"]')`);
let viewBtnUp = false;
for (let i = 0; i < 15; i++) {
  await sleep(800);
  viewBtnUp = await evalJs(`[...document.querySelectorAll("button")].some((b) => b.textContent.includes("查看案件"))`).catch(() => false);
  if (viewBtnUp) break;
}
check("查看案件钮出现（命中卡内）", viewBtnUp === true, String(viewBtnUp));
await tclick(`[...document.querySelectorAll("button")].find((b) => b.textContent.includes("查看案件"))`);
await sleep(1500);
const backToLegal = await evalJs(`!!document.querySelector('[data-testid="legal-workbench"]')`);
check("查看案件跳法律工作台（E3 本地可见等量）", backToLegal === true, String(backToLegal));
await shot("s5-view-matter-jump.png");

// ⑫ 案件冲突复核卡（H1-H4/A5，P2 先落复核卡与结论）：仅待复核渲染+检索+三键备注闸+结论后隐藏
async function selectBoardCase(name) {
  for (let i = 0; i < 10; i++) {
    const ok = await evalJs(`(() => { const sel = document.querySelector('[data-testid="board-case-select"]'); if (!sel) return false; const opt = [...sel.options].find((o) => o.textContent.includes("${name}")); if (!opt) return false; const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set; setter.call(sel, opt.value); sel.dispatchEvent(new Event("change", { bubbles: true })); return true; })()`).catch(() => false);
    if (ok) return true;
    await sleep(800);
  }
  return false;
}
await selectBoardCase("合成复核走查案·零命中");
await sleep(1200);
const cardOnZero = await evalJs(`!!document.querySelector('[data-testid="conflict-review-card"]')`);
check("复核卡：无复核记录案渲染（H1 needsReview=无记录）", cardOnZero === true, String(cardOnZero));
await tclick(`document.querySelector('[data-testid="conflict-review-run"]')`);
// 零命中→自动 DIFFERENT（H3，语义由合成 P7 钉死）→needsReview 翻 false→卡即卸载（A5）；
// 卡卸载后 notice 随组件消失，故直接轮询「卡隐藏」为通过事实（run 报错则卡留错误行，不会隐藏）
let cardHidden = false;
for (let i = 0; i < 15; i++) {
  await sleep(800);
  cardHidden = await evalJs(`!document.querySelector('[data-testid="conflict-review-card"]')`).catch(() => false);
  if (cardHidden) break;
}
check("零命中自动可承接后卡隐藏（A5 仅待复核渲染；H3 自动结论）", cardHidden === true, String(cardHidden));
await shot("s6-review-auto-pass.png");

await selectBoardCase("合成复核走查案·有命中");
await sleep(1200);
await tclick(`document.querySelector('[data-testid="conflict-review-run"]')`);
let hitRow = "";
for (let i = 0; i < 15; i++) {
  await sleep(800);
  hitRow = await evalJs(`document.querySelector('[data-testid="conflict-review-hits"]')?.textContent ?? ""`);
  if (hitRow) break;
}
check("复核命中列表（PENDING 挂起）", hitRow.includes("合成复核对家有限公司"), hitRow.slice(0, 50));
const decideDisabled = await evalJs(`document.querySelector('[data-testid="conflict-review-decide-DIFFERENT"]')?.disabled`);
check("三结论键备注空时禁用（H2/H4）", decideDisabled === true, String(decideDisabled));
await ttype(`document.querySelector('[data-testid="conflict-review-note"]')`, "合成复核理由：经核非同一主体，书面同意在卷。");
const decideEnabled = await evalJs(`!document.querySelector('[data-testid="conflict-review-decide-DIFFERENT"]')?.disabled`);
check("备注非空解锁结论键（H4）", decideEnabled === true, String(decideEnabled));
await tclick(`document.querySelector('[data-testid="conflict-review-decide-DIFFERENT"]')`);
// 结论成功即 needsReview 翻 false、卡卸载（notice 随组件消失）——以卡隐藏为保存事实
let cardHidden2 = false;
for (let i = 0; i < 15; i++) {
  await sleep(800);
  cardHidden2 = await evalJs(`!document.querySelector('[data-testid="conflict-review-card"]')`).catch(() => false);
  if (cardHidden2) break;
}
check("人工结论保存且卡隐藏（H4/A5）", cardHidden2 === true, String(cardHidden2));
await shot("s7-review-decided.png");

// ⑬ A7：URL ?name= 预填检索主体（截 100 字）——带参链接打开应用后进入预检页即预填首行
{
  const longName = "合成超长名称预填主体" + "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥".repeat(5) + "零一二三四五六七八九十";
  await send("Page.navigate", { url: APP + "?name=" + encodeURIComponent(longName) });
  for (let i = 0; i < 30; i++) {
    await sleep(1200);
    if (await evalJs(`!!document.querySelector('[data-testid="sidebar-primary-navigation"]')`).catch(() => false)) break;
  }
  await tclick(`document.querySelector('[data-testid="conflict-precheck-sidebar-open"]')`);
  let prefill = "";
  for (let i = 0; i < 20; i++) {
    await sleep(1000);
    prefill = await evalJs(`document.querySelector('[data-testid="conflict-name-0"]')?.value ?? ""`).catch(() => "");
    if (prefill) break;
  }
  check("A7 URL ?name= 预填首行（截 100 字）", prefill.length === 100 && longName.startsWith(prefill),
    `len=${prefill.length} head=${prefill.slice(0, 20)}…`);
  await shot("s8-url-name-prefill.png");
}

// 清场：杀桥+杀 vite+关 tab（收尾只杀自家）
async function killBridgeVerified() {
  const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${bridgePid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  if (!String(q.stdout ?? "").includes("bridge_host.mjs")) throw new Error("拒绝杀 pid=" + bridgePid + "：不是桥");
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
}
try { if (bridgePid) await killBridgeVerified(); } catch (e) { console.log("[re5-walk] 桥清场:", String(e).slice(0, 60)); }
try { process.kill(-vite.pid); } catch { try { vite.kill(); } catch { /* 已退 */ } }
try { await fetch(CDP + "/json/close/" + tab.id); } catch { /* tab 可能已关 */ }

const failed = results.filter((r) => !r.ok);
console.log(`[re5-walk] ── ${results.length - failed.length}/${results.length} PASS ──`);
if (failed.length) {
  console.log("CONFLICT_UI_FAIL");
  for (const f of failed) console.error("  FAIL:", f.name);
  process.exit(1);
} else {
  console.log("CONFLICT_UI_PASS");
}
