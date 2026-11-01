// 一次性走查驱动：功能 #3 案件看板 UI 真形态走查（CDP 9223 独立调试 Chrome + vite 5173）。
// 断言板面渲染/两态空态/对话框 CRUD 真输入/kind 徽章/出行行；截图落 evidence 目录。
// 用法: node tools/bridge/board_walk.mjs <截图输出目录>
import WebSocket from "ws";
import http from "node:http";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const CDP = process.env.CDP_PORT ? "http://127.0.0.1:" + process.env.CDP_PORT : "http://127.0.0.1:9223";
const OUT = process.argv[2] ?? "evidence/board-walk";
mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`[board-walk] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const NL = String.fromCharCode(10);
function getJson(path) {
  return new Promise((res, rej) => {
    http.get(CDP + path, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => res(JSON.parse(d))); }).on("error", rej);
  });
}

const list = await getJson("/json/list");
const target = list.find((t) => t.type === "page" && (t.url || "").includes("localhost:5173"));
if (!target) { console.log("NO_5173_TAB"); process.exit(1); }
let ws = null;
let mid = 0; const pending = new Map();
async function connect() {
  const fresh = (await getJson("/json/list")).find((t) => t.type === "page" && (t.url || "").includes("localhost:5173"));
  if (!fresh) throw new Error("5173 tab gone");
  ws = new WebSocket(fresh.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 });
  ws.on("message", (raw) => { const m = JSON.parse(raw.toString()); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
  await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); setTimeout(() => j(new Error("ws open timeout")), 8000); });
}
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++mid; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
async function evalJs(expr) {
  for (let i = 0; i < 3; i++) {
    try {
      const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
      if (r.exceptionDetails) throw new Error("EXC: " + (r.exceptionDetails.exception?.description ?? r.exceptionDetails.text));
      return r.result?.value;
    } catch (e) {
      if (i === 2) throw e;
      await sleep(800); await connect();
    }
  }
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(r.data, "base64"));
}
async function clickAt(el) {
  const rect = await evalJs(`(() => { const el = ${el}; if (!el) return null; el.scrollIntoView({ block: "center" }); const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  if (!rect) return false;
  for (const type of ["mousePressed", "mouseReleased"]) {
    await send("Input.dispatchMouseEvent", { type, x: rect.x, y: rect.y, button: "left", clickCount: 1 });
  }
  return true;
}
const q = (sel) => `document.querySelector('${sel}')`;
async function typeInto(sel, text) {
  if (!(await clickAt(q(sel)))) return false;
  await evalJs(`(() => { const el = document.querySelector('${sel}'); const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ""); el.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  await send("Input.insertText", { text });
  return true;
}

await connect();
await send("Page.enable");
await send("Runtime.enable");
await evalJs("1").catch(async () => { await connect(); });
await send("Page.bringToFront", {}).catch(() => {});
await send("Emulation.setFocusEmulationEnabled", { enabled: true }).catch(() => {});
await sleep(1500);

// reload 后轮询进板（boot 完成前侧栏按钮不存在——一次性 nav 会静默空过）
async function gotoBoard(maxMs = 30000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    const ok = await evalJs(`(() => {
      if (document.querySelector('[data-testid=board-panel]')) return 'ONBOARD';
      const els = [...document.querySelectorAll('button')].filter(e => e.offsetParent !== null);
      const el = els.find(e => (e.textContent ?? '').trim() === '法律工作台');
      if (el) { el.click(); return 'CLICKED'; }
      return document.querySelector('.zcode-boot-loading') ? 'BOOTING' : 'NOENTRY';
    })()`).catch(() => 'EVAL_ERR');
    if (ok === 'ONBOARD') return true;
    await sleep(900);
  }
  return false;
}

// W1 关闭可能的浮层（命令面板），再点侧栏「法律工作台」入口（可见元素精确匹配）
for (const type of ["keyDown", "keyUp"]) {
  await send("Input.dispatchKeyEvent", { type, key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
}
await sleep(800);
const nav = await gotoBoard();
check("W1 进入法律工作台", nav === true, String(nav));
await sleep(1500);
await evalJs(`(() => { const el = document.querySelector('[data-testid=board-panel]'); if (el) el.scrollIntoView({ block: "start" }); return !!el; })()`).catch(() => {});
await sleep(400);
check("W2 看板面板渲染", (await evalJs(`!!document.querySelector('[data-testid=board-panel]')`)) === true);

// W3 空态两态（对拍行 82）：空库轮=两态之一可见；有日程轮=两态皆不可见
const emptyNever = await evalJs(`document.querySelector('[data-testid=board-empty-never]')?.textContent ?? null`);
const emptyEnded = await evalJs(`document.querySelector('[data-testid=board-empty-ended]')?.textContent ?? null`);
const upcomingCount = await evalJs(`document.querySelectorAll('[data-testid=board-upcoming-list] > button').length`);
check("W3 两态空态与数据态一致",
  upcomingCount === 0 ? (emptyNever === null) !== (emptyEnded === null) : (emptyNever === null && emptyEnded === null),
  `never=${JSON.stringify(emptyNever)} ended=${JSON.stringify(emptyEnded)} upcoming=${upcomingCount}`);

// 行29 默认折叠：初入板先展开整月格（默认态本身由 W17 专项清键验证；此处展开=显式偏好落 0）
const needExpand = await evalJs(`!document.querySelector('[data-testid=board-cal-grid]') && !!document.querySelector('[data-testid=board-calendar-collapse]')`);
if (needExpand) { await clickAt(q("[data-testid=board-calendar-collapse]")); await sleep(700); }

// W4 月历 42 格 + 今日格
const cellCount = await evalJs(`document.querySelectorAll('[data-testid=board-cal-grid] > button').length`);
check("W4 月历 42 格", cellCount === 42, `n=${cellCount}`);
check("W4b 今日格存在", (await evalJs(`!!document.querySelector('[data-testid=board-cell-today]')`)) === true);

// W5 新建日程：点新建 → 对话框默认 10:00-11:00 → 真输入标题/地点/出行 → 保存
if (!(await clickAt(q("[data-testid=board-btn-new]")))) throw new Error("新建按钮点不到");
await sleep(700);
const defStart = await evalJs(`document.querySelector('[data-testid=board-dlg-start]')?.value ?? null`);
const defEnd = await evalJs(`document.querySelector('[data-testid=board-dlg-end]')?.value ?? null`);
check("W5 对话框起止默认 10:00/11:00", defStart === "10:00" && defEnd === "11:00", `${defStart}-${defEnd}`);
await typeInto("[data-testid=board-dlg-title]", "合成庭审·借款纠纷第一次开庭");
await typeInto("[data-testid=board-dlg-location]", "合成区人民法院第三法庭");
await typeInto("[data-testid=board-dlg-trip]", "8:00 地铁2号线出发");
// 选「庭审」kind
await clickAt(q("[data-testid=board-dlg-kind-hearing]"));
await sleep(300);
await clickAt(q("[data-testid=board-dlg-save]"));
await sleep(1200);
check("W5b 保存后对话框关闭+今日格出现日程", (await evalJs(`!document.querySelector('[data-testid=board-dialog]')`)) === true
  && (await evalJs(`document.querySelector('[data-testid=board-cell-today] [data-testid=board-cell-count]')?.textContent ?? null`)) !== null,
  "dialog closed + badge");

// W6 当日面板行：kind 庭审徽章+地点+出行行
const dayItem = await evalJs(`(() => {
  const el = document.querySelector('[data-testid=board-day-item]');
  return el ? el.textContent : null;
})()`);
check("W6 当日行含 庭审/地点/出行",
  Boolean(dayItem) && dayItem.includes("庭审") && dayItem.includes("合成区人民法院第三法庭") && dayItem.includes("8:00 地铁2号线出发"),
  String(dayItem).slice(0, 120));
await shot("board-walk-1-crud.png");

// W7 空标题负测：保存被行内拒绝
await clickAt(q("[data-testid=board-btn-new]"));
await sleep(600);
await clickAt(q("[data-testid=board-dlg-save]"));
await sleep(500);
const err = await evalJs(`document.querySelector('[data-testid=board-dlg-error]')?.textContent ?? null`);
check("W7 空标题行内报错", Boolean(err) && err.includes("事项名"), String(err));
await clickAt(q("[data-testid=board-dlg-cancel]"));
await sleep(400);

// W9 提醒引擎真开火：经桥 RPC 播一条 70 秒后开始、提前 1 分钟的提醒日程 →
//    挂载即扫（未进窗）→ 60s 周扫进窗 → 出行与提醒卡 engineNote 现真身（通知已弹或未授权如实分流）。
//    种子=合成数据；走查完删除。
{
  const seeded = await seedRemindEvent();
  check("W9 种子提醒日程落桥", Boolean(seeded?.id), JSON.stringify(seeded)?.slice(0, 80));
  // 刷新页面让面板重新挂载（挂载即扫一轮）
  await send("Page.reload", {});
  await gotoBoard();
  await sleep(1500);
  const row = await evalJs(`[...document.querySelectorAll('[data-testid=board-remind-row]')].map(e => e.textContent).find(t => t.includes('合成提醒·进窗即弹')) ?? null`);
  check("W9b 种子提醒行现真身（下一提醒+提前 1 分钟）",
    Boolean(row) && row.includes("下一提醒") && row.includes("提前 1 分钟"), String(row).slice(0, 110));
  await shot("board-walk-3-trip-remind.png");
  // 等进窗（种子 start=now+70s，提前 1min → 窗口 now+10s..now+130s；60s 周扫在 now+60s 附近命中）
  let note = null;
  for (let i = 0; i < 14; i++) {
    await sleep(8000);
    note = await evalJs(`document.querySelector('[data-testid=board-engine-note]')?.textContent ?? null`);
    if (note) break;
  }
  check("W9c 引擎进窗开火（通知已弹或未授权如实分流）",
    Boolean(note) && (note.includes("弹出") || note.includes("未授权")), String(note));
  // W10 开关面：对种子行关提醒→该行消失（未来行集不再含它）
  const toggleSel = `[...document.querySelectorAll('[data-testid=board-remind-row]')].find(e => e.textContent.includes('合成提醒·进窗即弹'))?.querySelector('[data-testid^=board-remind-toggle-]')`;
  const toggleId = await evalJs(`[...document.querySelectorAll('[data-testid=board-remind-row]')].find(e => e.textContent.includes('合成提醒·进窗即弹'))?.querySelector('[data-testid^=board-remind-toggle-]')?.dataset.testid ?? null`);
  check("W10 种子行开关按钮在行内", Boolean(toggleId), String(toggleId));
  if (toggleId && await clickAt(toggleSel)) {
    await sleep(1500);
    const still = await evalJs(`[...document.querySelectorAll('[data-testid=board-remind-row]')].some(e => e.textContent.includes('合成提醒·进窗即弹'))`);
    check("W10b 关闭提醒后种子行消失", still === false, `still=${String(still)}`);
  }
  if (seeded?.id) await cleanupEvent(seeded.id);
  await evalJs("location.reload()");
  await sleep(3000);
}

// W11 期限预警阶梯+#17 联动脚注：播演示集 → 四桶计数 [1,1,1,1]（-2/+2/+6/+20 各一，+40 窗外）
function seedRun(args) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const r = spawnSync(process.execPath, ["--import", "tsx", join("tools", "bridge", "board_seed.mts"), ...args],
      { cwd: process.cwd(), encoding: "utf-8", timeout: 90000 });
    try { return JSON.parse(String(r.stdout ?? "").trim().split(NL).pop().trim() ?? "{}"); }
    catch (e) {
      if (attempt === 1) return { err: String(e?.message ?? e).slice(0, 200), stderr: String(r.stderr ?? "").slice(-200) };
      // :3030 可能被并行工位门禁短暂重启——探活后重试一次
      spawnSync(process.execPath, ["-e", "fetch('http://127.0.0.1:3030/api/server-info').then(() => process.exit(0)).catch(() => process.exit(1))"], { timeout: 20000 });
    }
  }
}
const demo = seedRun(["demo"]);
check("W11 演示集落桥", Boolean(demo.caseId), JSON.stringify(demo).slice(0, 120));
await send("Page.reload", {});
await gotoBoard();
await sleep(1500);
const buckets = await evalJs(`(() => JSON.stringify(["overdue","d3","d7","d30"].map(k => document.querySelector('[data-testid=board-ladder-' + k + ']')?.querySelector('span')?.textContent ?? null)))()`);
check("W11b 阶梯四桶计数 [1,1,1,1]（四桶各一；+40 天窗外项不进窗）",
  buckets === JSON.stringify(["1", "1", "1", "1"]), String(buckets));
const footnote = await evalJs(`document.querySelector('[data-testid=board-ladder-footnote]')?.textContent ?? null`);
check("W11c 档位脚注（T-3/T-1/T-0/T+1+#17 联动措辞）",
  Boolean(footnote) && footnote.includes("T-3 / T-1 / T-0 / T+1") && footnote.includes("期限引擎") && footnote.includes("节假日顺延"),
  String(footnote));

// W12 案件卡下一节点（对拍行 84）
const node = await evalJs(`(() => {
  const cards = [...document.querySelectorAll('[data-testid=board-case-card]')];
  const el = cards.find(e => e.textContent.includes('合成案件·阶梯演示'));
  return el ? el.querySelector('[data-testid=board-case-node]')?.textContent ?? null : null;
})()`);
check("W12 案件卡显示下一节点（9 天后 证据质证）",
  Boolean(node) && node.includes("下一节点") && node.includes("证据质证") && node.includes("9 天后"), String(node));

// W12b-f 状态机面（行40-44 E2E：title 双态/下拉 11 档/手设两写/结案 toast/恢复自动推断）
const demoCard = () => `[...document.querySelectorAll('[data-testid=board-case-card]')].find(e => e.textContent.includes('合成案件·阶梯演示'))`;
const chipOf = (prop) => `${demoCard()}?.querySelector('[data-testid=board-case-status]')?.${prop} ?? null`;
const chipTitle0 = await evalJs(chipOf("title"));
check("W12b chip title 双态（未手设=自动推断位）", chipTitle0 === "自动推断·点击手工选择", String(chipTitle0));
await clickAt(`${demoCard()}?.querySelector('[data-testid=board-case-status]')`);
await sleep(500);
const menuN = await evalJs(`${demoCard()}?.querySelectorAll('[data-testid^=board-status-opt-]').length ?? 0`);
check("W12c 下拉现真身含 11 档", menuN === 11, `n=${String(menuN)}`);
await clickAt(`${demoCard()}?.querySelector('[data-testid=board-status-opt-已结案]')`);
await sleep(1400);
const chipText1 = await evalJs(chipOf("textContent"));
const chipTitle1 = await evalJs(chipOf("title"));
const toast1 = await evalJs(`document.querySelector('[data-testid=board-case-toast]')?.textContent ?? null`);
check("W12d 手设已结案=chip 值+title 手工位+结案 toast（行43）",
  chipText1 === "已结案" && chipTitle1 === "手工设置·点击修改" && Boolean(toast1),
  `${String(chipText1)}/${String(chipTitle1)}/${String(toast1)}`);
await clickAt(`${demoCard()}?.querySelector('[data-testid=board-case-status]')`);
await sleep(400);
const hasAuto = await evalJs(`!!${demoCard()}?.querySelector('[data-testid=board-status-auto]')`);
check("W12e locked 时「恢复自动推断」入口现（行42）", hasAuto === true, String(hasAuto));
await clickAt(`${demoCard()}?.querySelector('[data-testid=board-status-auto]')`);
await sleep(1400);
const chipText2 = await evalJs(chipOf("textContent"));
const chipTitle2 = await evalJs(chipOf("title"));
check("W12f 恢复自动=推断默认接案+title 回自动位",
  chipText2 === "接案" && chipTitle2 === "自动推断·点击手工选择", `${String(chipText2)}/${String(chipTitle2)}`);
await evalJs(`(() => { const el = document.querySelector('[data-testid=board-ladder]'); if (el) el.scrollIntoView({ block: 'center' }); return !!el; })()`);
await sleep(600);
await shot("board-walk-5-ladder-cases.png");

// W13 演示集清场（合成数据不留库）
const undone = seedRun(["undemo", demo.caseId, (demo.eventIds ?? []).join(",")]);
check("W13 演示集清场", Boolean(demo.caseId) && undone.cleaned === demo.caseId, JSON.stringify(undone));
await send("Page.reload", {});
await sleep(2500);
for (const type of ["keyDown", "keyUp"]) {
  await send("Input.dispatchKeyEvent", { type, key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
}
const renav = await gotoBoard(30000);
check("W13b 清场后重载回板（重挂竞态显性化）", renav === true, String(renav));
await sleep(1200);

// W14 补齐件：问候+简报+重要提醒卡（行1-7/12-17）
const greeting = await evalJs(`document.querySelector('[data-testid=board-greeting-card]')?.textContent ?? null`);
check("W14 问候卡（五档问候+在办计数）", Boolean(greeting) && greeting.includes("在办") && /好，/.test(greeting), String(greeting).slice(0, 60));
check("W14d 无名回退称谓「律师」（行1：单机无名恒走回退位）", Boolean(greeting) && greeting.includes("律师"), String(greeting).slice(0, 40));
const briefing = await evalJs(`document.querySelector('[data-testid=board-briefing]')?.textContent ?? null`);
check("W14b 简报行现真身", Boolean(briefing) && briefing.length > 4, String(briefing));
const impRows = await evalJs(`document.querySelectorAll('[data-testid=board-important-list] button').length`);
check("W14c 重要提醒卡条目≥1（今日开庭=urgent 留）", impRows >= 1, `rows=${impRows}`);
await shot("board-walk-6-skeleton.png");

// W15 卡宽切换持久（行 3）
const ariaBefore = await evalJs(`document.querySelector('[data-testid=board-card-width]')?.getAttribute('aria-label') ?? null`);
await clickAt(q("[data-testid=board-card-width]"));
await sleep(500);
const ariaAfter = await evalJs(`document.querySelector('[data-testid=board-card-width]')?.getAttribute('aria-label') ?? null`);
check("W15 卡宽切换 aria 双态", Boolean(ariaBefore) && ariaAfter !== ariaBefore, `${ariaBefore} -> ${ariaAfter}`);
await clickAt(q("[data-testid=board-card-width]"));
await sleep(400);

// W16 月历色点（行 28）
const dots = await evalJs(`(() => { const el = document.querySelector('[data-testid=board-cell-today] [data-testid=board-cell-dots]'); return el ? el.querySelectorAll('span').length : -1; })()`);
check("W16 今日格色点≥1", dots >= 1, `dots=${dots}`);

// W17 默认折叠（行 29：CB 默认折叠——清 per-device 键后重载验默认态；显式偏好仍胜默认）
await evalJs(`try { localStorage.removeItem('juscite.board.calendarCollapsed'); } catch {}`);
await send("Page.reload", {});
await gotoBoard(30000);
await sleep(1500);
const defCollapsed = await evalJs(`(() => ({ s: !!document.querySelector('[data-testid=board-collapsed-summary]'), g: !!document.querySelector('[data-testid=board-cal-grid]') }))()`);
check("W17 默认折叠（键缺省=摘要态非整月格）", defCollapsed?.s === true && defCollapsed?.g === false, JSON.stringify(defCollapsed));
const summary = await evalJs(`document.querySelector('[data-testid=board-collapsed-summary]')?.textContent ?? null`);
check("W17b 摘要行渲染（近 30 天逾期+未来）", Boolean(summary) && (summary.includes("今天") || summary.includes("逾期") || summary.includes("天后")), String(summary).slice(0, 80));
await clickAt(q("[data-testid=board-calendar-collapse]"));
await sleep(600);
check("W17c 展开回整月网格（持久化显式 0）", (await evalJs(`!!document.querySelector('[data-testid=board-cal-grid]')`)) === true, "grid back");

// W18 案内待办卡（行 35）：添加→打钩→已完成区→撤销
const caseOpt = await evalJs(`document.querySelector('[data-testid=board-case-select]')?.value ?? null`);
check("W18 待办卡已选案件", Boolean(caseOpt), String(caseOpt));
if (caseOpt) {
  if (!(await typeInto("[data-testid=board-todo-input]", "合成待办·走查样本"))) throw new Error("待办输入框点不到");
  await clickAt(q("[data-testid=board-todo-add]"));
  await sleep(1200);
  check("W18b 待办添加入列表", (await evalJs(`[...document.querySelectorAll('[data-testid=board-todo-item]')].some(e => e.textContent.includes('合成待办·走查样本'))`)) === true, "added");
  const cb = await evalJs(`[...document.querySelectorAll('[data-testid=board-todo-item]')].find(e => e.textContent.includes('合成待办·走查样本'))?.querySelector('input[type=checkbox]') ? 'ok' : null`);
  if (cb === "ok") {
    const sel = `[...document.querySelectorAll('[data-testid=board-todo-item]')].find(e => e.textContent.includes('合成待办·走查样本')).querySelector('input[type=checkbox]')`;
    await clickAt(sel);
    await sleep(1200);
    check("W18c 打钩进已完成区", (await evalJs(`!!document.querySelector('[data-testid=board-todo-done-zone]')`)) === true, "done zone");
    await clickAt(q("[data-testid=board-todo-done-zone] button"));
    await sleep(500);
    const undoSel = `[...document.querySelectorAll('[data-testid=board-todo-undo-]')]`;
    const undoBtn = await evalJs(`(() => { const b = [...document.querySelectorAll('button')].find(x => x.dataset.testid?.startsWith('board-todo-undo-')); if (!b) return null; b.click(); return 'clicked'; })()`);
    await sleep(1200);
    check("W18d 撤销回未完成", undoBtn === "clicked" && (await evalJs(`[...document.querySelectorAll('[data-testid=board-todo-item]')].some(e => e.textContent.includes('合成待办·走查样本'))`)) === true, "back open");
  }
}

// W18e-g 待办汇总卡（行38：跨案聚合+计数+打钩乐观移除）
const aggRow = await evalJs(`[...document.querySelectorAll('[data-testid^=board-agg-todo-]')].map(e => e.textContent).find(t => t.includes('合成待办·走查样本')) ?? null`);
check("W18e 待办汇总卡含跨案样本行（行38）", Boolean(aggRow), String(aggRow).slice(0, 60));
const aggCount = await evalJs(`document.querySelector('[data-testid=board-todo-agg-count]')?.textContent ?? null`);
check("W18f 汇总计数现真身（N 条未完成）", Boolean(aggCount) && /\d+ 条未完成/.test(aggCount), String(aggCount));
if (aggRow) {
  // 按行 id 断言（共享库有历史轮次同名残留——按标题匹配会数错对象，2026-10-28 W18g 首跑实证）
  const aggId = await evalJs(`[...document.querySelectorAll('[data-testid^=board-agg-todo-]')].find(e => e.textContent.includes('合成待办·走查样本'))?.dataset.testid ?? null`);
  const aggSel = `[...document.querySelectorAll('[data-testid^=board-agg-todo-]')].find(e => e.textContent.includes('合成待办·走查样本'))?.querySelector('input[type=checkbox]')`;
  await clickAt(aggSel);
  await sleep(1500);
  const gone = await evalJs(`!document.querySelector('[data-testid=${JSON.stringify(aggId)}]')`);
  check("W18g 汇总卡打钩乐观移除（按行 id）", Boolean(aggId) && gone === true, `id=${String(aggId)} gone=${String(gone)}`);
}
// W18h 历史样本清扫（跨轮残留同名待办；board_seed cleantodos 模式）
const cleanR = seedRun(["cleantodos"]);
check("W18h 历史样本待办清扫", Number(cleanR?.cleaned ?? 0) >= 1, JSON.stringify(cleanR));

// W21 三开关面+筛选工具栏（行2/47/48）
const sw = await evalJs(`(() => ({
  f: !!document.querySelector('[data-testid=board-switch-filterToolbar]'),
  a: !!document.querySelector('[data-testid=board-switch-boardAssistant]'),
  t: document.querySelector('[data-testid=board-switch-ticktick]')?.disabled ?? null,
}))()`);
check("W21 三开关渲染（滴答=禁用位不伪造）", sw?.f === true && sw?.a === true && sw?.t === true, JSON.stringify(sw));
await evalJs(`try { localStorage.removeItem('juscite.board.switch.filterToolbar'); } catch {}`);
await send("Page.reload", {});
await gotoBoard(30000);
await sleep(1500);
const tb0 = await evalJs(`!!document.querySelector('[data-testid=board-filter-toolbar]')`);
check("W21b 筛选工具栏默认关（开关关=面不渲染）", tb0 === false, `tb=${String(tb0)}`);
await clickAt(q("[data-testid=board-switch-filterToolbar]"));
await sleep(800);
const tb1 = await evalJs(`(() => ({ t: !!document.querySelector('[data-testid=board-filter-toolbar]'), c: document.querySelectorAll('[data-testid^=board-filter-status-]').length, court: !!document.querySelector('[data-testid=board-filter-court]'), party: !!document.querySelector('[data-testid=board-filter-party]') }))()`);
check("W21c 开关开=工具栏现真身（11 状态 chips+法院下拉+当事人搜索）",
  tb1?.t === true && tb1?.c === 11 && tb1?.court === true && tb1?.party === true, JSON.stringify(tb1));
const cntBefore = await evalJs(`document.querySelector('[data-testid=board-cases] h3 + span')?.textContent ?? null`);
await clickAt(q("[data-testid=board-filter-status-已结案]"));
await sleep(800);
const filtered = await evalJs(`(() => ({ cnt: document.querySelector('[data-testid=board-cases] h3 + span')?.textContent ?? null, clear: !!document.querySelector('[data-testid=board-filter-clear]') }))()`);
check("W21d 状态筛选真过滤+清空钮现（行47）",
  Boolean(cntBefore) && filtered?.cnt !== cntBefore && filtered?.clear === true, `${String(cntBefore)}->${String(filtered?.cnt)}`);
await clickAt(q("[data-testid=board-filter-clear]"));
await sleep(600);
const restored = await evalJs(`document.querySelector('[data-testid=board-cases] h3 + span')?.textContent ?? null`);
await clickAt(q("[data-testid=board-switch-filterToolbar]"));
await sleep(600);
const tb2 = await evalJs(`!!document.querySelector('[data-testid=board-filter-toolbar]')`);
check("W21e 清空恢复计数+开关关回工具栏隐", restored === cntBefore && tb2 === false, `${String(restored)}/${String(tb2)}`);

// W19 截图整体面
await shot("board-walk-2-panel.png");
const okAll = results.every((r) => r.ok);
console.log(okAll ? "BOARD_WALK_PASS" : "BOARD_WALK_FAIL");
process.exit(okAll ? 0 : 1);

// ── 种子/清理：经 board_seed.mts 子进程（--import tsx，同 lane 合成自测手法）──
function seedRemindEvent() {
  const start = new Date(Date.now() + 70_000);
  const hh = String(start.getHours()).padStart(2, "0");
  const mm = String(start.getMinutes()).padStart(2, "0");
  const date = `${start.getFullYear()}-${String(start.getMonth() + 1).padStart(2, "0")}-${String(start.getDate()).padStart(2, "0")}`;
  const once = () => {
    const r = spawnSync(process.execPath, ["--import", "tsx", join("tools", "bridge", "board_seed.mts"),
      "add", date, `${hh}:${mm}`, "合成提醒·进窗即弹", "1"],
      { cwd: process.cwd(), encoding: "utf-8", timeout: 60000 });
    try { return JSON.parse(String(r.stdout ?? "").trim().split(NL).pop().trim() ?? "{}"); }
    catch (e) { return { id: null, err: String(e?.message ?? e).slice(0, 200) }; }
  };
  const first = once();
  // :3030 被并行工位短暂竞态时种子 spawn 可能空输出——探活后重试一次（与 seedRun 同款）
  if (first?.id) return first;
  spawnSync(process.execPath, ["-e", "fetch('http://127.0.0.1:3030/api/server-info').then(() => process.exit(0)).catch(() => process.exit(1))"], { timeout: 20000 });
  return once();
}
function cleanupEvent(id) {
  spawnSync(process.execPath, ["--import", "tsx", join("tools", "bridge", "board_seed.mts"), "del", id],
    { cwd: process.cwd(), encoding: "utf-8", timeout: 60000 });
}
