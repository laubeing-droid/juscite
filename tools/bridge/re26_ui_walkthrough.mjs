// 【步骤4·#26 LAN 团队同步】UI 真形态走查（RE-26 验收：GUI 在调试 Chrome 独立实例验证）。
// vite 独立实例（5173；被并行工位占用时降级 5178 并如实注记）+ 隔离桥（BRIDGE_PORT=3086 独立库，
// 不碰 :3030）+ 调试 Chrome 9223 独立 tab + CDP trusted 输入。
// 链路：A1 侧栏「团队」恒显→A2 引导双卡→A4 空表单禁用→A5 建团进看板（B1 顶栏/角色徽章）→
// B6/B7/B9 种子案件投影→B4 立即同步（单机 0 在场=info）→E1/E2 配对码展示/换新码作废→E3 成员列表→
// E6 退出确认口径（dialog 拒绝→接受回引导页）。成员端接力视图（B10-B12）需双成员在库，协议级已由
// team_synthetic 双实例 68 断言覆盖；本走查为单实例 GUI 面（诚实边界）。
// 并行工位须知：他们改 packages/ui 文件会触发本 vite 实例全量 reload——所有交互带重试+quiescence 等待。
import WebSocket from "ws";
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
process.chdir(REPO_ROOT);
const CDP = "http://127.0.0.1:9223";
const BRIDGE_PORT = 3086;
const CFG_PATH = join(homedir(), "AppData", "Roaming", "Juscite", "config", "mock", "setting.json");
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`[re26-walk] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function probe(port) {
  try {
    const r = await fetch(`http://127.0.0.1:${port}/api/server-info`, { signal: AbortSignal.timeout(2500) });
    return r.ok;
  } catch { return false; }
}
// 团队身份落在共享配置文件（F13 等量：settings.json 单文件，隔离只分库不分配置）——
// 开工清残留 team 键（崩溃残留会让她桥重启自启团队网）；收尾 process.on("exit") 再清。
function cleanTeamConfig() {
  try {
    const j = JSON.parse(readFileSync(CFG_PATH, "utf-8"));
    if ("team" in j) { delete j.team; writeFileSync(CFG_PATH, JSON.stringify(j, null, 2), "utf-8"); return true; }
  } catch { /* 无配置文件=未配置 */ }
  return false;
}
console.log("[re26-walk] 开工清残留 team 配置键:", cleanTeamConfig());

// ── 杀旧 3086 桥→拉起隔离桥 ──
{
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === BRIDGE_PORT) spawnSync("taskkill", ["/PID", String(m[2]), "/F", "/T"], { timeout: 15000 });
  }
}
await sleep(800);
const bridgeLog = openSync(join(REPO_ROOT, ".local", `re26-walk-bridge-${BRIDGE_PORT}.log`), "a");
const bridge = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")], {
  cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(BRIDGE_PORT) },
  stdio: ["ignore", bridgeLog, bridgeLog], detached: true,
});
bridge.unref();
{
  // 2026-10-30 旧账五件：冷启实测（25 会话恢复+onboarding+automation+learning 依次起）可超 40s，放至 120s。
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline && !(await probe(BRIDGE_PORT))) await sleep(500);
}
if (!(await probe(BRIDGE_PORT))) { console.log("RE26_UI_FAIL"); console.error("桥 120s 不可探"); process.exit(1); }

// ── 种子合成案件（直插隔离库：1 案+未来开庭+已发生时间线；复跑幂等）──
{
  const { DatabaseSync } = await import("node:sqlite");
  const dbp = join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${BRIDGE_PORT}.db`);
  const db = new DatabaseSync(dbp);
  db.exec("DELETE FROM case_board_cases");
  db.prepare("DELETE FROM case_board_events WHERE id = ?").run("evt_walk1");
  db.prepare("DELETE FROM case_events WHERE event_id = ?").run("ce_walk1");
  db.exec("DELETE FROM team_snapshots; DELETE FROM team_state; DELETE FROM team_edits;");
  const now = new Date().toISOString();
  db.prepare(`INSERT INTO case_board_cases (id, name, cause, case_no, court, court_type, claim_amount_cents,
      plaintiffs_json, defendants_json, judges_json, workflow_status, workflow_locked, overrides_json, sort_order, updated_at)
    VALUES ('mat_walk1', '走查·买卖合同纠纷', '买卖合同纠纷', '(2026)合0101号', '合成市人民法院', '法院', 88000000,
      '["合成原告公司"]', '["合成被告公司"]', '[]', '审理中', 0, '{}', NULL, ?)`).run(now);
  const t = new Date();
  // 2026-10-30 旧账五件：原 plus 用 Math.min(day+d,28) 截断——10-27/28 跑出 10-28 恰为未来/当日侥幸过，
  // 10-29 起 10-28 成过去日→产品正确剔出未来窗→W5b ⏰/W5c 日期条必败（回传验收 fail 真因）。
  // 改真日历算术（月/年自然进位），语义回归「+20 天未来开庭/-10 天已发生建案」。
  const plus = (d) => {
    const nd = new Date(t.getFullYear(), t.getMonth(), t.getDate() + d);
    return `${nd.getFullYear()}-${String(nd.getMonth() + 1).padStart(2, "0")}-${String(nd.getDate()).padStart(2, "0")}`;
  };
  db.prepare(`INSERT INTO case_board_events (id, date, title, note, created_at, case_id, kind, location, start_at, end_at, trip, remind, remind_minutes)
    VALUES ('evt_walk1', ?, '开庭（合成）', NULL, ?, 'mat_walk1', 'hearing', '', NULL, NULL, NULL, 0, 30)`).run(plus(20), now);
  db.prepare(`INSERT INTO case_events (event_id, matter_id, event_type, date, date_label, note, expires_at, status,
      importance, phase, side, origin, source_refs_json, payload_json, provenance, locked_fields_json, orig_json, deleted, created_at, updated_at)
    VALUES ('ce_walk1', 'mat_walk1', '建案', ?, NULL, '新建案件：走查·买卖合同纠纷', NULL, 'confirmed',
      'normal', NULL, NULL, 'auto', '[]', NULL, 'system', '[]', NULL, 0, ?, ?)`).run(plus(-10), now, now);
  db.close();
}

// ── vite 独立实例（5173 优先，占用则 5178）──
let VITE_PORT = 5173;
try {
  const r = await fetch(`http://localhost:${VITE_PORT}/`, { signal: AbortSignal.timeout(1500) });
  if (r.ok) { VITE_PORT = 5178; console.log(`[re26-walk] 5173 被占（并行工位），降级 ${VITE_PORT}（如实注记）`); }
} catch { /* 5173 空闲 */ }
const APP = `http://localhost:${VITE_PORT}/`;
const viteLog = openSync(join(REPO_ROOT, ".local", `re26-walk-vite-${VITE_PORT}.log`), "a");
// 2026-10-30 旧账五件：基座升至 3.16.2 后 vite 对 localhost 只绑 [::1]（实测 netstat 仅 [::1]:port LISTENING，
// 127.0.0.1 探活恒 000）——显式 --host 127.0.0.1 钉定 IPv4 绑定，探活/Chrome 导航同栈确定性；
// 冷优化器首启（dep scan+bundle）实测可超 120s，等待窗放至 300s（热缓存常态数十秒内）。
const vite = spawn(process.execPath, [join(REPO_ROOT, "packages", "web", "node_modules", "vite", "bin", "vite.js"), "--port", String(VITE_PORT), "--strictPort", "--host", "127.0.0.1"],
  { cwd: join(REPO_ROOT, "packages", "web"), env: { ...process.env, BRIDGE_PORT: String(BRIDGE_PORT) }, stdio: ["ignore", viteLog, viteLog], detached: true });
vite.unref();
{
  let up = false;
  const deadline = Date.now() + 300000;
  while (Date.now() < deadline && !up) {
    try { const r = await fetch(APP, { signal: AbortSignal.timeout(2500) }); up = r.ok; } catch { /* 未起 */ }
    if (!up) { process.stdout.write("."); await sleep(1000); }
  }
  console.log("");
  if (!up) { console.log("RE26_UI_FAIL"); console.error("vite 300s 不可探"); process.exit(1); }
}
console.log("[re26-walk] vite up:", APP, "bridge:", BRIDGE_PORT);
const OUT = join("evidence", "步骤4-LAN团队同步-RE26-20261027", "ui-walkthrough");
mkdirSync(OUT, { recursive: true });

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
console.log("[re26-walk] tab:", tab.id, tab.url);
const ws = new WebSocket(tab.webSocketDebuggerUrl, { maxPayload: 128 * 1024 * 1024 });
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
let mid = 0; const pending = new Map();
let dialogAccept = true;
let lastDialog = "";
ws.on("message", (raw) => {
  const m = JSON.parse(raw.toString());
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); }
  if (m.method === "Page.javascriptDialogOpening") {
    console.log("[re26-walk] dialog:", (m.params.message ?? "").slice(0, 80));
    lastDialog = m.params.message ?? "";
    send("Page.handleJavaScriptDialog", { accept: dialogAccept }).catch(() => {});
  }
});
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++mid; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
await send("Runtime.enable"); await send("Page.enable"); await send("Page.bringToFront", {});
async function evalJs(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error("EXC: " + (r.exceptionDetails.exception?.description ?? r.exceptionDetails.text).slice(0, 300));
  return r.result?.value;
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(r.data, "base64"));
  console.log("[re26-walk] shot", name);
}
const q = (sel) => `document.querySelector('${sel}')`;
// 点击走 DOM el.click()（CDP trusted 鼠标事件与并行工位引发的 vite reload 竞态易脱靶——
// 同步探测直连实证 el.click() 稳定；dialog/表单语义不受影响，如实注记）。
async function tclickRetry(expr, tries = 5) {
  for (let i = 0; i < tries; i++) {
    const ok = await evalJs(`(() => { const el = (${expr}); if (!el) return false; el.scrollIntoView({ block: "center" }); el.click(); return true; })()`).catch(() => false);
    if (ok) return;
    await sleep(600);
  }
  throw new Error("MISS " + expr.slice(0, 90));
}
async function ttype(expr, text) {
  // CDP trusted 输入优先；值未落（reload 竞态）用 React native setter 兜底+整轮重试
  for (let attempt = 0; attempt < 3; attempt++) {
    try { await tclickRetry(expr); await send("Input.insertText", { text }); } catch { /* 走兜底 */ }
    const v = await evalJs(`(${expr})?.value`).catch(() => undefined);
    if (v === text) return;
    await evalJs(`(() => { const el = (${expr}); if (!el) return false;
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      setter.call(el, ${JSON.stringify(text)});
      el.dispatchEvent(new Event("input", { bubbles: true }));
      return el.value === ${JSON.stringify(text)}; })()`).catch(() => false);
    const v2 = await evalJs(`(${expr})?.value`).catch(() => undefined);
    if (v2 === text) return;
    await sleep(900);
  }
  throw new Error("TTYPE-FAIL " + expr.slice(0, 90));
}
async function reloadPage() {
  await send("Page.navigate", { url: APP });
  for (let i = 0; i < 60; i++) {
    await sleep(1500);
    if (await evalJs(`!!${q('[data-testid="sidebar-primary-navigation"]')}`).catch(() => false)) break;
  }
  await waitStable();
  await sleep(600);
}
async function clickAndWait(clickExpr, testid, rounds = 4, waitMs = 22000) {
  for (let r = 0; r < rounds; r++) {
    try { await tclickRetry(clickExpr); } catch { /* 元素瞬时缺失，重试 */ }
    if (await waitTestid(testid, waitMs)) return true;
    console.log(`[re26-walk] clickAndWait ${testid} 第 ${r + 1} 轮未就位，重载页面重试`);
    await reloadPage();
  }
  return false;
}
const waitTestid = async (testid, timeoutMs = 30000) => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await evalJs(`!!${q(`[data-testid="${testid}"]`)}`).catch(() => false)) return true;
    await sleep(500);
  }
  return false;
};
// quiescence：设窗口标记并等它存活（存活=期间无全量 reload；并行工位写文件风暴的护城河）
async function waitStable(maxMs = 60000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    await evalJs("window.__re26mark = 1").catch(() => {});
    await sleep(1500);
    if (await evalJs("window.__re26mark === 1").catch(() => false)) return true;
  }
  return false;
}

await send("Page.navigate", { url: APP });
{
  // 2026-10-30 旧账五件：基座 3.16.2 后首访冷变换全应用模块图实测可超 90s（CDP 复盘：reload 后 20s 内
  // 装配完成、sidebar 团队/冲突预检/安全审计全在——非 UI 断链，纯冷变换时长），窗放至 300s。
  let up = false;
  for (let i = 0; i < 200; i++) {
    await sleep(1500);
    up = await evalJs(`!!${q('[data-testid="sidebar-primary-navigation"]')}`).catch(() => false);
    if (up) break;
  }
  if (!up) { console.log("RE26_UI_FAIL"); console.error("app 300s 未装配"); process.exit(1); }
}
await waitStable();
await sleep(800);

// W1 (A1) 侧栏「团队」入口恒显（带 reload 抖动重试）
{
  let w1ok = false, w1text = "";
  for (let i = 0; i < 20 && !w1ok; i++) {
    w1text = (await evalJs(`${q('[data-testid="team-sidebar-open"]')}?.textContent?.trim() ?? ''`).catch(() => "")) ?? "";
    w1ok = w1text === "团队";
    if (!w1ok) { await waitStable(20000); }
  }
  check("W1-A1 侧栏团队入口恒显", w1ok, "text=" + JSON.stringify(w1text));
}
// W2 (A1/A2) 入口→引导页双卡
check("W2-A2 引导页挂载", await clickAndWait(q('[data-testid="team-sidebar-open"]'), "team-panel-guide")
  && await evalJs(`!!${q('[data-testid="team-guide-create"]')} && !!${q('[data-testid="team-guide-join"]')}`));
await waitStable();
await shot("s1-guide.png");
// W2b (A3) 姓名预填：源=产品称呼槽 localStorage juscite.board.displayName（看板问候行同源
// CaseBoardPanel）+设置层称呼字段次优（现无）。空源=空串可输入不崩；有源=两卡姓名即预填（竞品
// A3=进入引导页即预填设置里用户称呼；预填后清键复位，W3/W4 仍在空源路径）。
{
  await evalJs(`(() => { try { window.localStorage.removeItem("juscite.board.displayName"); } catch {} return true; })()`);
  await send("Page.navigate", { url: APP });
  await waitStable(); await sleep(600);
  check("W2b-prep 引导页重挂载", await clickAndWait(q('[data-testid="team-sidebar-open"]'), "team-panel-guide")
    && await evalJs(`!!${q('[data-testid="team-guide-create"]')}`));
  const who0 = await evalJs(`(() => document.querySelector('[data-testid="team-guide-create"]')?.querySelectorAll("input")[1]?.value ?? "MISS")()`);
  check("W2b-A3a 空源不预填可输入", who0 === "", "init=" + JSON.stringify(who0));
  await evalJs(`(() => { try { window.localStorage.setItem("juscite.board.displayName", "走查预填称呼"); } catch {} return true; })()`);
  await send("Page.navigate", { url: APP });
  await waitStable(); await sleep(600);
  check("W2b-prep2 引导页重挂载", await clickAndWait(q('[data-testid="team-sidebar-open"]'), "team-panel-guide")
    && await evalJs(`!!${q('[data-testid="team-guide-create"]')}`));
  const who1 = await evalJs(`(() => document.querySelector('[data-testid="team-guide-create"]')?.querySelectorAll("input")[1]?.value ?? "MISS")()`);
  check("W2b-A3b 有源即预填", who1 === "走查预填称呼", "init=" + JSON.stringify(who1));
  await evalJs(`(() => { try { window.localStorage.removeItem("juscite.board.displayName"); } catch {} return true; })()`);
  await send("Page.navigate", { url: APP });
  await waitStable(); await sleep(600);
  check("W2b-prep3 复位回引导页", await clickAndWait(q('[data-testid="team-sidebar-open"]'), "team-panel-guide")
    && await evalJs(`!!${q('[data-testid="team-guide-create"]')}`));
}
// W3 (A4) 空表单禁用；填团队名缺姓名仍禁用
{
  const createDisabledEmpty = await evalJs(`${q('[data-testid="team-create-btn"]')}?.disabled ?? null`);
  await ttype(`${q('[data-testid="team-guide-create"] input')}`, "走查小队");
  const createDisabledHalf = await evalJs(`${q('[data-testid="team-create-btn"]')}?.disabled ?? null`);
  const filled = (await evalJs(`[...document.querySelectorAll('[data-testid="team-guide-create"] input')].map((i) => i.value)`)) ?? [];
  check("W3-A4 空表单/缺姓名禁用创建", createDisabledEmpty === true && createDisabledHalf === true,
    "empty=" + createDisabledEmpty + " half=" + createDisabledHalf + " values=" + JSON.stringify(filled));
}
// W4 (A5/B1) 填姓名→创建→进看板
await ttype(`(() => ${q('[data-testid="team-guide-create"]')}?.querySelectorAll("input")[1] ?? null)()`, "走查队长");
check("W4-A5 建团进看板", await clickAndWait(q('[data-testid="team-create-btn"]'), "team-panel-board"));
check("W4b-B1 顶栏团队名/成员数/团队长徽章",
  (await evalJs(`${q('[data-testid="team-board-name"]')}?.textContent?.trim() ?? ''`)) === "走查小队"
  && (((await evalJs(`${q('[data-testid="team-panel-board"]')}?.textContent ?? ''`)) ?? "").includes("1 名成员"))
  && ((await evalJs(`${q('[data-testid="team-role-badge"]')}?.textContent?.trim() ?? ''`)) === "团队长"));
await waitStable();
await shot("s2-board-leader.png");
// W5 (B6/B7/B9) 种子案件投影
{
  const ok = await waitTestid("team-case-card", 20000);
  const board = (await evalJs(`${q('[data-testid="team-panel-board"]')}?.textContent ?? ''`)) ?? "";
  check("W5-B6 成员组+我的徽章", ok && board.includes("走查队长") && board.includes("（我）") && board.includes("1 个案件"),
    "ok=" + ok + " board[0..500]=" + board.slice(0, 500));
  check("W5b-B7/B9 案件卡投影字段", board.includes("走查·买卖合同纠纷") && board.includes("审理中")
    && board.includes("(2026)合0101号") && board.includes("合成原告公司 对 合成被告公司")
    && board.includes("¥880,000") && board.includes("最新进展：") && board.includes("⏰"),
    "missing=" + ["走查·买卖合同纠纷", "审理中", "(2026)合0101号", "合成原告公司 对 合成被告公司", "¥880,000", "最新进展：", "⏰"]
      .filter((k) => !board.includes(k)).join("|"));
  check("W5c-B5 关键日期条", board.includes("近期关键日期") && board.includes("开庭（合成）"),
    "bar=" + board.includes("近期关键日期") + " hearing=" + board.includes("开庭（合成）"));
}
await shot("s3-board-case.png");
// W5d (B12) 平铺视图案件卡可见所有者徽章（含(我)）
{
  await tclickRetry(q('[data-testid="team-sort-latest"]'));
  const ok = await waitTestid("team-flat-grid", 15000) && await waitTestid("team-case-owner", 15000);
  const owner = (await evalJs(`[...document.querySelectorAll('[data-testid="team-case-owner"]')].map((e) => e.textContent.trim())`)) ?? [];
  check("W5d-B12 平铺所有者徽章含(我)", ok && owner.length >= 1 && owner.every((t) => t.includes("走查队长（我）")), JSON.stringify(owner));
  await shot("s3b-flat-owner.png");
  await tclickRetry(q('[data-testid="team-sort-member"]')); // 切回按成员
}
// W5e (C5) 详情页基本信息「最近动态」行（更新于+日期）
{
  await tclickRetry(q('[data-testid="team-case-card"] button:not([disabled])'));
  const ok = await waitTestid("team-case-detail", 15000);
  const detail = (await evalJs(`${q('[data-testid="team-detail-info"]')}?.textContent ?? ''`)) ?? "";
  check("W5e-C5 详情最近动态行（更新于+日期）", ok && detail.includes("最近动态") && /更新于\s*\d{4}-\d{2}-\d{2}/.test(detail),
    "has=" + detail.includes("最近动态") + " match=" + /更新于\s*\d{4}-\d{2}-\d{2}/.test(detail) + " text=" + detail.slice(0, 220));
  await shot("s3c-detail-activity.png");
  await tclickRetry(q('[data-testid="team-detail-back"]'));
  await waitTestid("team-panel-board", 15000);
}

// W6 (B4) 立即同步：单机 0 在场=info toast
await tclickRetry(q('[data-testid="team-sync-btn"]'));
{
  let seen = false;
  for (let i = 0; i < 30 && !seen; i++) {
    seen = await evalJs(`(${q('[data-testid="team-toast"]')}?.textContent ?? '').includes("没有同步到任何队友")`).catch(() => false);
    await sleep(400);
  }
  check("W6-B4 立即同步 0 在场 info", seen);
}
// W7 (B3/E1/E2) 管理区：配对码 6 位→换新码变化
await tclickRetry(q('[data-testid="team-manage-toggle"]'));
check("W7-B3 管理区展开", await waitTestid("team-manage", 10000));
await waitStable();
await tclickRetry(q('[data-testid="team-pairing-refresh"]'));
{
  let code1 = "";
  for (let i = 0; i < 20 && !code1; i++) {
    code1 = (await evalJs(`${q('[data-testid="team-pairing-code"]')}?.textContent?.trim() ?? ''`).catch(() => "")) ?? "";
    if (!code1) await sleep(400);
  }
  check("W7b-E1 配对码大号展示 6 位", /^\d{6}$/.test(code1), "code1=" + code1);
  await tclickRetry(q('[data-testid="team-pairing-rotate"]'));
  await sleep(900);
  const code2 = (await evalJs(`${q('[data-testid="team-pairing-code"]')}?.textContent?.trim() ?? ''`).catch(() => "")) ?? "";
  check("W7c-E2 换新码作废旧码", /^\d{6}$/.test(code2) && code2 !== code1, "code2=" + code2);
  await shot("s4-manage-pairing.png");
}
// W8 (E3/E6) 成员列表含我+退出确认两段（拒绝→接受）
{
  const membersText = (await evalJs(`${q('[data-testid="team-members"]')}?.textContent ?? ''`)) ?? "";
  check("W8-E3 成员列表含我", membersText.includes("走查队长（我）"));
  dialogAccept = false;
  await tclickRetry(q('[data-testid="team-leave-btn"]'));
  await sleep(900);
  check("W8b-E6 退出确认 dialog（团队长=解散口径）", lastDialog.includes("解散团队"), lastDialog.slice(0, 40));
  check("W8c-E6 拒绝后仍在看板", await evalJs(`!!${q('[data-testid="team-panel-board"]')}`));
  dialogAccept = true;
  check("W8d-E6 确认解散回引导页", await clickAndWait(q('[data-testid="team-leave-btn"]'), "team-panel-guide", 3, 20000));
  await shot("s5-after-leave.png");
}

// ── 收尾：清共享配置 team 键 + 杀自管进程（正常/异常路径都走） ──
process.on("exit", () => {
  cleanTeamConfig();
  try { spawnSync("taskkill", ["/PID", String(bridge.pid), "/F", "/T"], { timeout: 15000 }); } catch { /* 尽力 */ }
  try { spawnSync("taskkill", ["/PID", String(vite.pid), "/F", "/T"], { timeout: 15000 }); } catch { /* 尽力 */ }
});
const passed = results.filter((r) => r.ok).length;
const failed = results.length - passed;
for (const r of results.filter((x) => !x.ok)) console.log(`[re26-walk] FAIL → ${r.name} ${r.detail ?? ""}`);
console.log(`[re26-walk] PASS=${passed} FAIL=${failed}`);
console.log(failed === 0 ? "RE26_UI_PASS" : "RE26_UI_FAIL");
process.exit(failed === 0 ? 0 : 1);
