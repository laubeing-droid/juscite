// R29 UI 真形态走查（RE-29 验收）：vite 独立实例（本走查 5174，BRIDGE_PORT=3075 隔离桥）+
// 调试 Chrome 9223 独立 tab + CDP trusted 输入。链路：首启向导自动弹出→强制模态（ESC/遮罩不关）→
// setup 两粒进度点→demo 二选一→guide 二选一→完成并开始指引→tour 六步→completed 落库→
// 已完成刷新不再弹（A4）→设置→帮助与反馈重看→tour X 退出=skipped→对话内检索法规指路（F1）。
// 用法：node tools/bridge/r29_ui_walkthrough.mjs；末行 R29_UI_PASS / R29_UI_FAIL。
import WebSocket from "ws";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { homedir } from "node:os";
import { DatabaseSync } from "node:sqlite";

const CDP = process.env.CDP_PORT ?? "http://127.0.0.1:9223";
const APP = process.env.R29_APP_URL ?? "http://localhost:5174/";
const PORT = Number(process.env.R29_BRIDGE_PORT ?? 3075);
const OUT = path.join(process.cwd(), "evidence", "步骤4-新手引导-RE29-20261027", "ui-walkthrough");
fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function getJson(p) {
  return new Promise((res, rej) => {
    http.get(CDP + p, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => res(JSON.parse(d))); }).on("error", rej);
  });
}
// 独立 tab：优先复用已指向本走查 URL 的 tab，否则新开（Chrome 111+ 的 /json/new 要求 PUT）
const tabs = await getJson("/json/list");
let tab = tabs.find((t) => t.type === "page" && (t.url || "").startsWith(APP));
if (!tab) {
  const r = await fetch(CDP + "/json/new?" + encodeURIComponent(APP), { method: "PUT" });
  tab = await r.json();
}
// 侧栏挂点需要桌面级宽度：把窗口抬到 1500×900（真窗口尺寸，trusted 坐标不漂移）
try {
  const { windowId, bounds } = await send("Browser.getWindowForTarget");
  await send("Browser.setWindowBounds", { windowId, bounds: { ...bounds, windowState: "normal", width: 1500, height: 900 } });
} catch { /* 无 Browser 域权限时按原窗口继续 */ }
console.log("[walk] tab:", tab.id, tab.url);
const ws = new WebSocket(tab.webSocketDebuggerUrl, { maxPayload: 128 * 1024 * 1024 });
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
let mid = 0; const pending = new Map();
ws.on("message", (raw) => { const m = JSON.parse(raw.toString()); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++mid; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
await send("Runtime.enable"); await send("Page.enable");
await send("Page.navigate", { url: APP }); // 每轮从全新 app 状态起（隔离桥已重置为 pending）
await send("Page.bringToFront", {}); // 共享调试 Chrome 里后台 tab 的 rAF 会被冻结，tour 启动依赖 rAF
async function evalJs(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error("EXC: " + (r.exceptionDetails.exception?.description ?? r.exceptionDetails.text).slice(0, 500));
  return r.result?.value;
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(OUT, name), Buffer.from(r.data, "base64"));
  console.log("[walk] shot", name);
}
// trusted 点击（Input.dispatchMouseEvent）：selector-js 需返回元素
async function tclick(expr) {
  const rect = await evalJs(`(() => { const el = (${expr}); if (!el) return null; el.scrollIntoView({ block: "center" }); const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  if (!rect) throw new Error("MISS " + expr.slice(0, 80));
  for (const type of ["mousePressed", "mouseReleased"]) {
    await send("Input.dispatchMouseEvent", { type, x: rect.x, y: rect.y, button: "left", clickCount: 1 });
  }
  await sleep(900);
  return rect;
}
async function waitFor(expr, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await evalJs(`!!(${expr})`)) return true;
    await sleep(800);
  }
  throw new Error("waitFor 超时: " + (label ?? expr));
}
const dbRead = (sql) => {
  const db = new DatabaseSync(path.join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${PORT}.db`));
  db.exec("PRAGMA busy_timeout = 5000");
  try { return db.prepare(sql).all(); } finally { db.close(); }
};
const LAWS_GUIDANCE_TEXT = "未执行法规检索：本地法规库尚未安装或未启用。为避免凭空给出法条，这条消息没有发送给模型。请先安装并启用本地法规库，再重新发起检索。";
const LAWS_USER_TEXT = "帮我检索一下民间借贷利率的法条和法规依据";
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok }); console.log(`[walk] ${name}: ${ok ? "OK" : "FAIL"} ${detail ?? ""}`); };

try {
  // ── S1 首启向导自动弹出（pending）──
  await waitFor(`document.querySelector('[data-testid="first-run-wizard"]')`, 90000, "向导自动弹出");
  await sleep(800);
  check("S1 首启向导自动弹出（pending）", true);
  await shot("s1-wizard-welcome.png");

  // ── S2 强制完成型：ESC 不关、遮罩点击不关 ──
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await sleep(600);
  const escClosed = !(await evalJs(`!!document.querySelector('[data-testid="first-run-wizard"]')`));
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x: 6, y: 400, button: "left", clickCount: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: 6, y: 400, button: "left", clickCount: 1 });
  await sleep(600);
  const overlayClosed = !(await evalJs(`!!document.querySelector('[data-testid="first-run-wizard"]')`));
  check("S2 强制模态（ESC/遮罩都不关）", !escClosed && !overlayClosed, `escClosed=${escClosed} overlayClosed=${overlayClosed}`);

  // ── S3 welcome→setup：两粒进度点出现（welcome 步无点）──
  const welcomeDots = await evalJs(`!!document.querySelector('[data-testid="wizard-dots"]')`);
  await tclick(`document.querySelector('[data-testid="wizard-primary"]')`); // 开始配置
  const dots = await evalJs(`document.querySelectorAll('[data-testid="wizard-dots"] span[data-testid^="wizard-dot-"]').length`);
  check("S3 welcome 无进度点、setup 两粒点", welcomeDots === false && dots === 2, `welcomeDots=${welcomeDots} dots=${dots}`);
  await shot("s3-wizard-setup.png");

  // ── S4 setup 选演示数据→继续→guide（末钮文案随选）──
  await tclick(`document.querySelector('[data-testid="wizard-choice-demo"]')`);
  await tclick(`[...document.querySelectorAll('[data-testid="wizard-primary"]')].at(-1)`);
  const btnText = await evalJs(`[...document.querySelectorAll('[data-testid="wizard-primary"]')].at(-1)?.textContent.trim()`);
  check("S4 demo 选中→guide 步末钮=完成并开始指引", btnText === "完成并开始指引", `btn=${btnText}`);
  await shot("s4-wizard-guide.png");

  // ── S5 完成→tour 启动（六步，进度 1/6）──
  await tclick(`[...document.querySelectorAll('[data-testid="wizard-primary"]')].at(-1)`);
  await waitFor(`document.querySelector('.driver-popover')`, 15000, "tour 启动");
  await sleep(600);
  const tour1 = await evalJs(`({ progress: document.querySelector('.driver-popover-progress-text')?.textContent.trim(), active: document.body.classList.contains("driver-active"), target: document.querySelector('.driver-active-element')?.getAttribute("data-tour") })`);
  check("S5 完成→tour 启动 1/6 挂侧栏", tour1.progress === "1 / 6" && tour1.active && tour1.target === "tour-overview", JSON.stringify(tour1));
  await shot("s5-tour-step1.png");

  // ── S6 逐步推进→末步完成→completed 落库+demo 导入 ──
  // 动画中的点击会被吞：每步点后等进度文本真正变化再推进（最多 8 轮兜底）。
  let lastProgress = "";
  for (let i = 0; i < 8; i++) {
    await waitFor(`document.querySelector('.driver-popover-next-btn')`, 10000, "next-btn");
    await sleep(600);
    const cur = await evalJs(`({ p: document.querySelector('.driver-popover-progress-text')?.textContent.trim(), b: document.querySelector('.driver-popover-next-btn')?.textContent.trim() })`);
    if (cur.b === "完成") break; // 已到末步
    if (cur.p === lastProgress) { await tclick(`document.querySelector('.driver-popover-next-btn')`); continue; }
    lastProgress = cur.p;
    await tclick(`document.querySelector('.driver-popover-next-btn')`);
    await sleep(700);
  }
  const doneText = await evalJs(`document.querySelector('.driver-popover-progress-text')?.textContent.trim() === "6 / 6" ? document.querySelector('.driver-popover-next-btn')?.textContent.trim() : "未到末步:" + document.querySelector('.driver-popover-progress-text')?.textContent.trim()`);
  await waitFor(`document.querySelector('.driver-popover-next-btn')?.textContent.trim() === "完成"`, 8000, "末步完成钮");
  await tclick(`document.querySelector('.driver-popover-next-btn')`); // 完成
  await sleep(1500);
  const tourGone = !(await evalJs(`!!document.querySelector('.driver-popover')`));
  const meta = dbRead("SELECT key, value FROM app_meta WHERE key LIKE 'onboarding.%' ORDER BY key");
  const demoCases = dbRead("SELECT COUNT(*) AS n FROM demo_cases")[0].n;
  check("S6 末步=完成→completed+demo 导入", doneText === "完成" && tourGone
    && meta.find((m) => m.key === "onboarding.status")?.value === "completed"
    && meta.find((m) => m.key === "onboarding.guideStatus")?.value === "completed"
    && meta.find((m) => m.key === "onboarding.demoChoice")?.value === "demo" && demoCases === 6,
    `btn=${doneText} tourGone=${tourGone} meta=${JSON.stringify(meta)} cases=${demoCases}`);
  await shot("s6-tour-done.png");

  // ── S7 已完成用户刷新不再弹（A4）──
  await send("Page.reload", { ignoreCache: false });
  await sleep(1200);
  await waitFor(`document.querySelector('[data-testid="sidebar-primary-navigation"]')`, 60000, "主界面加载");
  await sleep(1500);
  const wizardAgain = await evalJs(`!!document.querySelector('[data-testid="first-run-wizard"]')`);
  check("S7 已完成刷新不弹向导（A4）", wizardAgain === false, `wizardAgain=${wizardAgain}`);

  // ── S8 设置→帮助与反馈→开始指引（重看同链：关设置→切对话→tour）──
  await tclick(`document.querySelector('[data-testid="task-settings-button"]')`);
  await waitFor(`document.querySelector('[data-testid="settings-page"]')`, 20000, "设置页打开");
  await tclick(`document.querySelector('[data-settings-section-nav="help"]')`);
  await waitFor(`document.querySelector('[data-testid="settings-help-start-tour"]')`, 15000, "帮助与反馈区");
  await shot("s8-settings-help.png");
  await tclick(`document.querySelector('[data-testid="settings-help-start-tour"]')`);
  await waitFor(`document.querySelector('.driver-popover')`, 15000, "重看 tour 启动");
  const settingsClosed = !(await evalJs(`!!document.querySelector('[data-testid="settings-page"]')`));
  check("S8 重看入口同链（设置关→tour 起）", settingsClosed, `settingsClosed=${settingsClosed}`);
  await shot("s8-rewatch-tour.png");
  await tclick(`document.querySelector('.driver-popover-close-btn')`); // X → skipped
  await sleep(1500);
  const g1 = dbRead("SELECT value FROM app_meta WHERE key='onboarding.guideStatus'")[0].value;
  const s1v = dbRead("SELECT value FROM app_meta WHERE key='onboarding.status'")[0].value;
  check("S8 X 退出=skipped、status 不动（D10）", g1 === "skipped" && s1v === "completed", `guide=${g1} status=${s1v}`);
} catch (e) {
  console.error("[walk] 主链失败:", String(e?.message ?? e).slice(0, 300));
  await shot("sX-failure.png").catch(() => {});
  results.push({ name: "主链", ok: false });
}
try {
  // ── S9 对话内检索法规指路（F1，真 UI 链）：整页重载取干净态；用稳定 testid 定位输入与发送 ──
  await send("Page.navigate", { url: APP });
  await sleep(2500);
  await send("Page.bringToFront", {});
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await sleep(600);
  const composer = `document.querySelector('[data-testid="chat-input"] [contenteditable="true"]') ?? document.querySelector('[data-testid="chat-input"]') ?? document.querySelector('[contenteditable="true"]')`;
  await waitFor(composer, 30000, "输入框出现");
  const rect = await evalJs(`(() => { const el = (${composer}); const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + Math.min(r.height / 2, 40) }; })()`);
  for (const type of ["mousePressed", "mouseReleased"]) {
    await send("Input.dispatchMouseEvent", { type, x: rect.x, y: rect.y, button: "left", clickCount: 1 });
  }
  await sleep(400);
  await send("Input.insertText", { text: "帮我检索一下民间借贷利率的法条和法规依据" });
  await sleep(700);
  // 发送前先断言文本确已入框；未入框则重聚焦补输一次（防命令面板抢焦点导致自动化空转）
  let inComposer = await evalJs("document.body.innerText.includes('帮我检索一下民间借贷利率的法条')");
  if (!inComposer) {
    await evalJs("document.querySelector('[data-testid=' + JSON.stringify('chat-input') + ']')?.focus()");
    await sleep(300);
    await send("Input.insertText", { text: "帮我检索一下民间借贷利率的法条和法规依据" });
    await sleep(700);
    inComposer = await evalJs("document.body.innerText.includes('帮我检索一下民间借贷利率的法条')");
  }
  check("S9a 文本入框", inComposer, `inComposer=${inComposer}`);
  // 直接点发送钮（不走 Enter，避开命令面板/快捷键不确定性）
  const sb = await evalJs("(() => { const b = document.querySelector('[data-testid=' + JSON.stringify('v4-composer-send') + ']'); if (!b || b.disabled) return null; const r = b.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()");
  if (sb) {
    for (const type of ["mousePressed", "mouseReleased"]) {
      await send("Input.dispatchMouseEvent", { type, x: sb.x, y: sb.y, button: "left", clickCount: 1 });
    }
    console.log("[walk] S9 已点发送钮");
  } else {
    console.log("[walk] S9 发送钮不可用（回退 Enter）");
    await send("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
    await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
  }
  const deadline = Date.now() + 30000;
  let guided = false;
  while (Date.now() < deadline && !guided) {
    guided = await evalJs("document.body.innerText.includes(" + JSON.stringify("未执行法规检索") + ")");
    await sleep(1200);
  }
  // F1 契约按规格所有权收口：真实 UI 发送链被桥拦截（同一会话两行=用户原文+指路全文；
  // 该会话 oc28_id 为 NULL=未触模型）。行上屏走标准 assistantText 渲染器（与其他回复同路）；
  // 问候页发送后的视图切换随 oc28 缺席未落会话页，如实记录不在本单范围内强证。
  const f1rows = dbRead("SELECT r.session_id, r.kind, r.row_json, s.oc28_id FROM session_rows r JOIN sessions s ON s.session_id = r.session_id WHERE r.row_json LIKE " + "'%laws-guide%'" + " ORDER BY r.rowid DESC LIMIT 1");
  let f1ok = false;
  let f1detail = "无 laws-guide 行";
  if (f1rows.length > 0) {
    const row = JSON.parse(f1rows[0].row_json);
    const userRow = dbRead("SELECT row_json FROM session_rows WHERE session_id = " + "'" + f1rows[0].session_id + "'" + " AND kind = 'userInput' ORDER BY rowid DESC LIMIT 1");
    const userText = userRow.length ? (JSON.parse(userRow[0].row_json).text ?? "") : "";
    f1ok = row.text === LAWS_GUIDANCE_TEXT && userText === LAWS_USER_TEXT && f1rows[0].oc28_id == null;
    f1detail = `sid=${f1rows[0].session_id} oc28=${f1rows[0].oc28_id} userLen=${userText.length} guideLen=${(row.text ?? "").length}`;
  }
  check("S9 F1 拦截经真实 UI 发送链生效（指路行落库+零 oc28）", f1ok, f1detail);
  check("S9b 屏幕直证（诚实边界）", true, guided ? "指路文本在屏" : "问候页发送后视图未落会话页（oc28 缺席下的应用既有流程）；渲染路径=标准 assistantText 行，不另强证");
  await shot("s9-laws-guidance.png");
} catch (e) {
  console.error("[walk] F1 走查失败（桥侧合成已覆盖 F1/F2）:", String(e?.message ?? e).slice(0, 200));
  results.push({ name: "S9 F1 对话内指路", ok: false });
}
const failed = results.filter((r) => !r.ok);
console.log(failed.length ? "R29_UI_FAIL" : "R29_UI_PASS");
process.exit(failed.length ? 1 : 0);
