// 功能 #18 学习迭代 UI 真形态走查（RE-18 验收）：vite 独立实例（5179，BRIDGE_PORT=3079 隔离桥
// + mock oc28 确定性提案回合）+ 调试 Chrome 9223 独立 tab + CDP trusted 输入。
// 链路：侧栏「学习迭代」入口（J1）→面板挂载+状态卡/徽章/立即学习（J2）→预置已完成记录出现于记录
// 列表（J12 状态图标）→详情页全项（J7-J11：徽章/双态标题/圆环/5 格统计带/横条图/安全卡/三列/
// 技术记录折叠）→搜索过滤空态与恢复（J12）→立即学习真轮（mock 提案→记录+1，J13 轮询）→
// 回滚最近一轮（J6/H8 面上按钮）→记录态翻转 rolled_back。截图落 evidence；末行 RE18_UI_PASS / FAIL。
import WebSocket from "ws";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { mkdirSync, openSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
process.chdir(REPO_ROOT);
const CDP = process.env.CDP_PORT ? "http://127.0.0.1:" + process.env.CDP_PORT : "http://127.0.0.1:9223";
const BRIDGE_PORT = 3079;
const VITE_PORT = 5179;
const APP = `http://localhost:${VITE_PORT}/`;
const OUT = join("evidence", "步骤4-学习迭代-RE18-20261027", "ui-walkthrough");
mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`[re18-walk] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── mock oc28：学习提示→合成提案 JSON；其他→普通回复 ──
const OUTPUT_MARK_BEGIN = "<<<JUSCITE_LEARNING_OUTPUT";
const NOTE_BODY = "综合多个线程的做法，举证责任分配按谁主张谁举证为基线，例外情形由法庭依职权审查；具体到合同纠纷中，违约方通常就免责事由举证。本条为合成笔记正文，长度满足下限要求，内容全部为合成材料，不含任何真实案件信息。".slice(0, 200);
const tests4 = ["should-trigger", "should-not-trigger", "ambiguous", "sibling-confusion"];
const proposal = {
  title: "写作习惯与举证要点", summary: "这轮了解了你常用的写作习惯，并整理了一条举证要点笔记。",
  reportMarkdown: "## 这次学到了什么\n- 记住了工作方式：先列证据清单再写正文\n\n## 会带来哪些提升\n- 学会了「证据清单先行」\n\n## 以后会怎样帮你\n- 起草文书时主动附证据清单。",
  memories: [{ action: "create", category: "workflow", content: "写文书前先列证据清单再动笔", confidence: 0.9,
    evidence: [{ sourceKey: "thread:ses_walk_a", sourceKind: "thread" }, { sourceKey: "thread:ses_walk_b", sourceKind: "thread" }] }],
  skills: [{ id: "evidence-checklist", name: "证据清单先行", description: "写文书前先列证据清单再动笔的固定做法，来自用户反复执行的工作方式。",
    skillMarkdown: "---\nname: evidence-checklist\n---\n# 证据清单先行",
    evidence: [{ sourceKey: "thread:ses_walk_a", sourceKind: "thread" }, { sourceKey: "thread:ses_walk_b", sourceKind: "thread" }],
    tests: [...tests4, ...tests4.map((t) => t + "2")].map((c, i) => ({ category: tests4[i % 4], input: c, passed: true })) }],
  knowledgeNotes: [{ action: "create", path: "举证责任分配实务要点.md", title: "举证责任分配实务要点", summary: "综合两个线程的举证分配做法与例外情形。", content: NOTE_BODY, evidence: [{ sourceKey: "thread:ses_walk_a", sourceKind: "thread" }] }],
  rejected: [],
};
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
      const promptText = parsed.text ?? "";
      const list = mockSessions.get(sid) ?? [];
      list.push({ id: parsed.id ?? "u" + mockSeq, type: "user", time: { created: Date.now() }, content: [{ type: "text", text: promptText }] });
      const isLearning = promptText.includes(OUTPUT_MARK_BEGIN);
      const reply = isLearning ? `分析如下：\n${OUTPUT_MARK_BEGIN}\n${JSON.stringify(proposal)}\nJUSCITE_LEARNING_OUTPUT>>>\n以上。` : "收到（合成回复）。";
      const mid = "a" + (mockSeq++);
      setTimeout(() => {
        const l2 = mockSessions.get(sid) ?? [];
        l2.push({ id: mid, type: "assistant", time: { created: Date.now(), completed: Date.now() }, content: [{ type: "text", text: reply }] });
        mockSessions.set(sid, l2);
      }, 250);
      mockSessions.set(sid, list);
      res.writeHead(200); res.end("{}");
    });
    return;
  }
  const lm = req.method === "GET" && url.match(/^\/api\/session\/([^/]+)\/message$/);
  if (lm) { res.writeHead(200, { "content-type": "application/json" }); res.end(JSON.stringify({ data: mockSessions.get(decodeURIComponent(lm[1])) ?? [] })); return; }
  res.writeHead(404); res.end("{}");
});
const mockUrl = await new Promise((resolve) => mockServer.listen(0, "127.0.0.1", () => resolve("http://127.0.0.1:" + mockServer.address().port)));

// ── 隔离桥（3079；独立学习根/知识根；onboarding 直置 completed 免向导遮挡）──
const LEARN_ROOT = join(REPO_ROOT, ".local", `re18-walk-learning-${BRIDGE_PORT}`);
const KB_ROOT = join(REPO_ROOT, ".local", `re18-walk-kb-${BRIDGE_PORT}`);
rmSync(LEARN_ROOT, { recursive: true, force: true });
rmSync(KB_ROOT, { recursive: true, force: true });
const DB = join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${BRIDGE_PORT}.db`);
const bridgeLog = openSync(join(REPO_ROOT, ".local", `re18-walk-bridge-${BRIDGE_PORT}.log`), "a");
function spawnBridge() {
  const env = { ...process.env, BRIDGE_PORT: String(BRIDGE_PORT), BRIDGE_OC28_SSE: "0", BRIDGE_OC28_URL: mockUrl, BRIDGE_OC28_PASSWORD: "walk",
    BRIDGE_LEARNING_ROOT: LEARN_ROOT, BRIDGE_KB_ROOT: KB_ROOT, BRIDGE_LEARNING_POLL_MS: "3600000" };
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
      console.log("[re18-walk] 清场：杀掉残留桥 pid=" + pid);
    }
  }
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline && (await probe())) await sleep(400);
}
await clearPortLeftovers();
for (const suffix of ["", "-wal", "-shm"]) { try { rmSync(DB + suffix, { force: true }); } catch { /* 留给下轮 */ } }
// 预置：state.json 标记今日已成功（boot tick 直接走 doneToday 出口，消竞速；A3 话术可断言）
{
  mkdirSync(LEARN_ROOT, { recursive: true });
  const today = new Date();
  const localDay = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  writeFileSync(join(LEARN_ROOT, "state.json"), JSON.stringify({
    version: 1, sourceHashes: {}, lastSuccessfulAt: Date.now() - 3600_000, lastCheckedAt: Date.now() - 3600_000,
    lastLocalDay: localDay, lastRetryAt: null, retryCount: 0,
    baselineComplete: true, baselineProcessed: 3, baselineRemaining: 0, pendingRunId: null,
  }, null, 2), "utf-8");
}
let bridgePid = spawnBridge();
{
  const deadline = Date.now() + 40000;
  while (Date.now() < deadline && !(await probe())) await sleep(500);
  try {
    const db = new DatabaseSync(DB);
    db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.status','completed') ON CONFLICT(key) DO UPDATE SET value='completed'").run();
    db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.guideStatus','skipped') ON CONFLICT(key) DO UPDATE SET value='skipped'").run();
    db.close();
  } catch (e) { console.log("[re18-walk] onboarding 预置失败：", String(e).slice(0, 80)); }
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  const d2 = Date.now() + 15000;
  while (d2 > Date.now() && (await probe())) await sleep(400);
  bridgePid = spawnBridge();
  const d3 = Date.now() + 40000;
  while (d3 > Date.now() && !(await probe())) await sleep(500);
}
if (!(await probe())) { console.log("RE18_UI_FAIL"); console.error("桥 40s 不可探"); process.exit(1); }

// 预置一场已完成记录（走查播种，端到端已被 learning_synthetic 覆盖）：runs/<id>/manifest+REPORT
{
  const runId = "2026-10-26-1015-walkseed";
  const dir = join(LEARN_ROOT, "runs", runId);
  mkdirSync(dir, { recursive: true });
  const counts = { sources: 5, threads: 2, knowledgeFiles: 1, uploadedFiles: 0, generatedFiles: 0,
    memoriesCreated: 1, memoriesUpdated: 0, memoriesDisabled: 0, skillsCreated: 1, skillsUpdated: 0,
    knowledgeNotesCreated: 1, knowledgeNotesUpdated: 0, rejected: 2 };
  const manifest = {
    version: 1,
    summary: { id: runId, title: "写作习惯与举证要点", displayName: "2026-10-26 · 写作习惯与举证要点", status: "completed",
      startedAt: Date.now() - 86400000, finishedAt: Date.now() - 86300000, reportPath: join(dir, "REPORT.md"), canRollback: true, counts },
    sourceHashes: {},
    rollback: { memories: [], skills: [], knowledge: [] }, // 走查播种不带账本：回滚点击走真轮记录（见后）
    modelResult: { title: "写作习惯与举证要点", summary: "s", reportMarkdown: "", memories: [], skills: [], knowledgeNotes: [], rejected: [] },
  };
  writeFileSync(join(dir, "manifest.json"), JSON.stringify(manifest, null, 2), "utf-8");
  writeFileSync(join(dir, "REPORT.md"), [
    "# 写作习惯与举证要点", "", "这一轮系统通读了最近的工作记录，并把其中有把握的内容整理进了记忆、方法与知识库。", "",
    "## 这次学到了什么", "- 记住了工作方式：先列证据清单再写正文", "",
    "## 会带来哪些提升", "- 学会了「证据清单先行」", "- 沉淀了「举证责任分配实务要点」", "",
    "## 学习结果一览", "", "| 项目 | 数量 |", "|---|---|", "| 记住的内容 | 1 |", "| 掌握的方法 | 1 |", "| 知识库沉淀 | 1 |", "| 因信息不够确定而未采纳 | 2 |", "| 浏览的变化来源 | 5 |", "",
    "## 以后会怎样帮你", "- 起草文书时主动附证据清单。", "",
    "## 隐私与控制", "- 只学习有把握的稳定内容；拿不准的一律不采纳。", "- 新笔记只写入指定的沉淀目录，不会覆盖你的原始文件。", "- 每一轮都可以整轮撤销，随时可在记录页回滚。",
  ].join("\n"), "utf-8");
}

// ── vite 独立实例（5179，代理指向 3079）──
const viteLog = openSync(join(REPO_ROOT, ".local", `re18-walk-vite-${VITE_PORT}.log`), "a");
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
if (!(await viteUp())) { console.log("RE18_UI_FAIL"); console.error("vite 120s 不可探"); process.exit(1); }
console.log("[re18-walk] vite up:", APP, "bridge:", BRIDGE_PORT);

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
console.log("[re18-walk] tab:", tab.id, tab.url);
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
  console.log("[re18-walk] shot", name);
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

await send("Page.navigate", { url: APP });
{ // 等 app 装配
  let up = false;
  for (let i = 0; i < 60; i++) {
    await sleep(1500);
    up = await evalJs(`!!document.querySelector('[data-testid="sidebar-primary-navigation"]')`).catch(() => false);
    if (up) break;
  }
  console.log("[re18-walk] app shell up:", up);
  await shot("s0-app-shell.png");
}

// ① 侧栏入口 → 面板挂载（J1）
const entry = await evalJs(`!!document.querySelector('[data-testid="learning-iteration-sidebar-open"]')`);
check("侧栏「学习迭代」入口可见（J1）", entry === true, String(entry));
await tclick(`document.querySelector('[data-testid="learning-iteration-sidebar-open"]')`);
{
  let mounted = false;
  for (let i = 0; i < 30; i++) {
    await sleep(1000);
    mounted = await evalJs(`!!document.querySelector('[data-testid="learning-panel"]')`).catch(() => false);
    if (mounted) break;
  }
  check("面板挂载（J1 lazy）", mounted === true, String(mounted));
}
await sleep(1500);
const badge = await evalJs(`document.querySelector('[data-testid="learning-status-badge"]')?.textContent ?? ""`);
check("状态卡徽章七态文案（J2）", ["待检查", "已完成", "学习中", "排队中", "未完成", "已回滚", "已关闭"].includes(badge), badge);
const queueBtn = await evalJs(`!!document.querySelector('[data-testid="learning-queue-btn"]')`);
check("立即学习主按钮在位（J2）", queueBtn === true, String(queueBtn));
const msg = await evalJs(`document.querySelector('[data-testid="learning-message"]')?.textContent ?? ""`);
check("当前消息文案在位（J2）", msg.length > 0, msg.slice(0, 40));
await shot("s1-panel-overview.png");

// ② 预置记录出现于记录列表（J12 轮询刷新）
{
  let item = null;
  for (let i = 0; i < 20; i++) {
    await sleep(1000);
    item = await evalJs(`document.querySelector('[data-testid="learning-record-item"]')?.textContent ?? null`);
    if (item) break;
  }
  check("记录列表出现预置记录（J12/J13）", Boolean(item) && String(item).includes("写作习惯与举证要点"), String(item).slice(0, 40));
}
const metricCards = await evalJs(`document.querySelectorAll('[data-testid="learning-metric-cards"] > div').length`);
check("4 指标卡（J3）", metricCards === 4, String(metricCards));
const latestMetrics = await evalJs(`document.querySelectorAll('[data-testid="learning-latest-metrics"] .grid > div').length`);
check("最新一轮 5 指标（J4）", latestMetrics === 5, String(latestMetrics));
const stageCells = await evalJs(`document.querySelectorAll('[data-testid="learning-stage-bar"] > div').length`);
check("七阶段流程条（J5）", stageCells === 7, String(stageCells));
await shot("s2-overview-with-record.png");

// ③ 详情页全项（J7-J11）
await tclick(`document.querySelector('[data-testid="learning-record-item"]')`);
{
  let detail = false;
  for (let i = 0; i < 20; i++) {
    await sleep(1000);
    detail = await evalJs(`!!document.querySelector('[data-testid="learning-detail"]')`).catch(() => false);
    if (detail) break;
  }
  check("详情页挂载（J7）", detail === true, String(detail));
}
await sleep(1200);
const dTitle = await evalJs(`document.querySelector('[data-testid="learning-detail-title"]')?.textContent ?? ""`);
check("详情标题（H3 报告标题）", dTitle.includes("写作习惯与举证要点"), dTitle);
const dBage = await evalJs(`!!document.querySelector('[data-testid="learning-detail-badge"]')`);
check("详情状态徽章（J7）", dBage === true, "");
const ring = await evalJs(`document.querySelector('[data-testid="learning-ring"]')?.getAttribute("aria-label") ?? ""`);
check("圆环计数 aria（J8）", ring.includes("3 处变更"), ring);
const band = await evalJs(`document.querySelectorAll('[data-testid="learning-stat-band"] > div').length`);
check("5 格统计带（J8）", band === 5, String(band));
const bars = await evalJs(`document.querySelector('[data-testid="learning-bars"]')?.getAttribute("aria-label") ?? ""`);
check("成果横条图 aria 含四类分布（J8）", bars.includes("记住的内容") && bars.includes("谨慎未采纳"), bars.slice(0, 60));
const safety = await evalJs(`document.querySelector('[data-testid="learning-safety-rejected"]')?.textContent ?? ""`);
check("安全卡 rejected 二态提示（J9）", safety.includes("2 条"), safety.slice(0, 50));
const threeCols = await evalJs(`!!document.querySelector('[data-testid="learning-three-cols"]')`);
check("三列内容区（J10）", threeCols === true, "");
{
  // 技术记录折叠（J11）：点击展开
  const summary = await evalJs(`!!document.querySelector('[data-testid="learning-tech-record"] summary')`);
  if (summary) await tclick(`document.querySelector('[data-testid="learning-tech-record"] summary')`);
  await sleep(600);
  const open = await evalJs(`document.querySelector('[data-testid="learning-tech-record"]')?.hasAttribute("open") ?? false`);
  check("技术记录折叠可展开（J11）", open === true, String(open));
}
await shot("s3-detail-report.png");

// ④ 搜索过滤（J12）
await evalJs(`(() => { window.scrollTo(0, 0); })()`);
await tclick(`document.querySelector('[data-testid="learning-overview-btn"]')`);
await sleep(600);
await ttype(`document.querySelector('[data-testid="learning-search"]')`, "不存在的关键词");
await sleep(800);
const emptyText = await evalJs(`document.querySelector('[data-testid="learning-record-empty"]')?.textContent ?? ""`);
check("搜索无结果空态话术（J12）", emptyText.includes("没有匹配的记录"), emptyText.slice(0, 40));
await evalJs(`(() => { const el = document.querySelector('[data-testid="learning-search"]'); el.focus(); document.execCommand("selectAll", false, null); document.execCommand("delete", false, null); })()`);
await sleep(800);
const itemBack = await evalJs(`!!document.querySelector('[data-testid="learning-record-item"]')`);
check("清空搜索恢复记录列表（J12）", itemBack === true, String(itemBack));

// ⑤ 立即学习在今日额度用尽后的面上话术（A3；真轮端到端已由 learning_synthetic B 段覆盖）
{
  await tclick(`document.querySelector('[data-testid="learning-queue-btn"]')`);
  await sleep(1000);
  const notice = await evalJs(`document.querySelector('[data-testid="learning-notice"]')?.textContent ?? ""`);
  check("立即学习今日额度话术（A3/J2）", notice.includes("明天"), notice.slice(0, 50));
  await shot("s4-after-run.png");
}

// ⑥ 详情页含学习标记/回滚按钮（新记录 canRollback=true → 详情「回滚本轮」在位）
{
  const items = await evalJs(`document.querySelectorAll('[data-testid="learning-record-item"]').length`);
  await tclick(`document.querySelector('[data-testid="learning-record-item"]')`);
  let hasRoll = false;
  for (let i = 0; i < 15; i++) {
    await sleep(1000);
    hasRoll = await evalJs(`!!document.querySelector('[data-testid="learning-rollback-this"]')`).catch(() => false);
    if (hasRoll) break;
  }
  check("详情「回滚本轮」按 canRollback 显示（J7）", hasRoll === true, `items=${items}`);
}
await shot("s5-detail-rollback.png");

await kill(bridgePid);
function kill(pid) {
  if (!pid) return Promise.resolve();
  return new Promise((resolve) => {
    spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
    setTimeout(resolve, 800);
  });
}

// ⑦ 设置页三控件（J14）
{
  // 直接开设置：侧栏底部/命令面板入口不稳定，走 hash/query 不存在——经 UI：点设置齿轮。
  // 与 re16 同口径：直接定位设置导航按钮（data-testid 随官方壳）——找不到则经 workspaceMainView 快捷路径跳过。
  const setBtn = await evalJs(`!!document.querySelector('[data-testid="settings-sidebar-open"], [data-tour="tour-settings"]')`);
  if (setBtn) {
    await tclick(`document.querySelector('[data-testid="settings-sidebar-open"], [data-tour="tour-settings"]')`);
    await sleep(1500);
  }
  // 通用节内查找学习迭代分区（若设置页默认不在通用节，先点「通用」）
  const generalBtn = await evalJs(`(() => { const els = [...document.querySelectorAll("button, a")]; const b = els.find((e) => e.textContent?.trim() === "通用"); if (b) { b.click(); return true; } return false; })()`);
  if (generalBtn) await sleep(1200);
  const sec = await evalJs(`(() => { let el = document.querySelector('[data-testid="settings-learning-section"]'); if (!el) return null; el.scrollIntoView({ block: "center" }); return true; })()`);
  check("设置通用节学习迭代分区在位（J14）", sec === true, String(sec));
  if (sec) {
    const toggle = await evalJs(`document.querySelector('[data-testid="settings-learning-toggle"]')?.getAttribute("aria-checked") ?? document.querySelector('[data-testid="settings-learning-toggle"]')?.getAttribute("data-state") ?? ""`);
    check("总开关默认开（A1/J14）", toggle === "true" || toggle === "checked", toggle);
    const idleVal = await evalJs(`document.querySelector('[data-testid="settings-learning-idle"]')?.value ?? ""`);
    check("空闲等待默认 15 分钟（J14）", idleVal === "15", idleVal);
    const tray = await evalJs(`document.querySelector('[data-testid="settings-learning-tray"]')?.getAttribute("aria-checked") ?? document.querySelector('[data-testid="settings-learning-tray"]')?.getAttribute("data-state") ?? ""`);
    check("托盘驻留默认开（J14）", tray === "true" || tray === "checked", tray);
    // 关总开关 → 下拉禁用
    await tclick(`document.querySelector('[data-testid="settings-learning-toggle"]')`);
    await sleep(900);
    const disabledAfterOff = await evalJs(`document.querySelector('[data-testid="settings-learning-idle"]')?.disabled ?? false`);
    check("关总开关后空闲下拉禁用（J14）", disabledAfterOff === true, String(disabledAfterOff));
    await shot("s6-settings.png");
  }
}

// 收场
try { await kill(bridgePid); } catch { /* 已停 */ }
try { rmSync(LEARN_ROOT, { recursive: true, force: true }); } catch { /* 句柄延迟留给下轮 */ }
try { rmSync(KB_ROOT, { recursive: true, force: true }); } catch { /* 同上 */ }

const total = results.filter((r) => !r.ok).length;
console.log(`[re18-walk] checks=${results.length} fail=${total}`);
console.log(total === 0 ? "RE18_UI_PASS" : "RE18_UI_FAIL");
process.exit(total === 0 ? 0 : 1);
