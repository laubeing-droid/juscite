// 一次性走查驱动：功能 #4 案件时间线 UI 真形态走查（CDP 9223 独立调试 Chrome + vite 5173 + 桥 :3030）。
// 断言：面板渲染/建案自动节点/业务动作徽标/软删+还原 chips/空态虚线框（全隐藏态）+还原 chips 空态常渲染/
// 真模型抽取回合（oc28 链，确认制对话框经 CDP javascriptDialogOpening 自动接受）/节点渲染+编辑覆盖+↺ 恢复/
// 看板案件卡下一节点翻牌时间线源；截图落 evidence 目录。种子全部合成，收尾清场。
// 用法: node tools/bridge/timeline_walk.mjs <截图输出目录>
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import http from "node:http";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const CDP = process.env.CDP_PORT ? "http://127.0.0.1:" + process.env.CDP_PORT : "http://127.0.0.1:9223";
const OUT = process.argv[2] ?? "evidence/timeline-walk";
const MAT_DIR = "D:\\mock\\lvyin-demo\\materials";
const MY_FILES = ["时间线走查-起诉状.txt", "时间线走查-调解书.txt"];
mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`[timeline-walk] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const NL = String.fromCharCode(10);
function getJson(path) {
  return new Promise((res, rej) => {
    http.get(CDP + path, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => res(JSON.parse(d))); }).on("error", rej);
  });
}

// ── CDP 连接 ──
const list = await getJson("/json/list");
const tabs = list.filter((t) => t.type === "page" && (t.url || "").includes("localhost:5173"));
if (!tabs.length) { console.log("NO_5173_TAB"); process.exit(1); }
let target = null;
// 多页签（并行工位遗留）择优：挑已 boot 完成、有可点按钮的健康页签；找不到则退回首个页签
// （由主流程 gotoBoard 轮询兜底，不在此硬退）。
for (const t of tabs) {
  try {
    const probe = new WebSocket(t.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 });
    const st = await new Promise((res, rej) => {
      probe.on("message", (raw) => { const m = JSON.parse(raw.toString()); if (m.id === 1) res(m.result); });
      probe.on("open", () => probe.send(JSON.stringify({ id: 1, method: "Runtime.evaluate", params: { expression: `JSON.stringify({boot:!!document.querySelector('.zcode-boot-loading'), btn:document.querySelectorAll('button').length})`, returnByValue: true } })));
      probe.on("error", rej);
      setTimeout(() => rej(new Error("probe timeout")), 10000);
    });
    probe.close();
    const v = JSON.parse(st?.result?.value ?? "{}");
    if (!v.boot && v.btn > 0) { target = t; break; }
  } catch { /* 探测失败试下一个 */ }
}
target = target ?? tabs[0];
let ws = null;
let mid = 0; const pending = new Map();
async function connect() {
  const fresh = (await getJson("/json/list")).filter((t) => t.type === "page" && (t.url || "").includes("localhost:5173"));
  if (!fresh.length) throw new Error("5173 tab gone");
  // 重连时同样择优（健康页签优先，找不到退回原 target）
  const cur = fresh.find((t) => t.id === target.id) ?? fresh[fresh.length - 1];
  ws = new WebSocket(cur.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 });
  ws.on("message", (raw) => {
    const m = JSON.parse(raw.toString());
    if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); }
    // 窗口 confirm 走 CDP javascriptDialogOpening 自动接受（抽取确认制对话框）
    if (m.method === "Page.javascriptDialogOpening") {
      ws.send(JSON.stringify({ id: ++mid, method: "Page.handleJavaScriptDialog", params: { accept: true } }));
    }
  });
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
  await evalJs(`(() => { const el = document.querySelector('${sel}'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, ""); el.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  await send("Input.insertText", { text });
  return true;
}

// ── 桥 RPC 客户端（种子/清场用，与板面同 :3030；board_synthetic 同款握手）──
let rpcWs = null;
async function rpcConnect() {
  rpcWs = new WebSocket("ws://127.0.0.1:3030/ws");
  rpcWs.binaryType = "arraybuffer";
  const data = { fire: (_b) => {} };
  rpcWs.on("message", (buf) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
  await new Promise((r, j) => { rpcWs.on("open", r); rpcWs.on("error", j); });
  const isocket = {
    onData: (l) => { data.fire = l; return { dispose: () => {} }; },
    onClose: () => ({ dispose: () => {} }),
    onEnd: () => ({ dispose: () => {} }),
    write: (b) => rpcWs.send(b.buffer),
    end: () => rpcWs.close(), drain: async () => {}, dispose: () => rpcWs.close(),
  };
  const ch = new ChannelClient(new SocketProtocol(isocket)).getChannel("zcode-agent");
  await ch.call("helloConversationV4", []);
  return ch;
}
async function rpcCall(ch, m, a) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try { return await ch.call(m, a === undefined ? [] : [a]); }
    catch (e) {
      if (attempt === 1) throw e;
      // :3030 可能被并行工位门禁短暂重启——探活后重连重试一次
      for (let i = 0; i < 20; i++) {
        const ok = await fetch("http://127.0.0.1:3030/api/server-info", { signal: AbortSignal.timeout(2500) }).then((r) => r.ok).catch(() => false);
        if (ok) break;
        await sleep(800);
      }
      try { rpcWs?.close(); } catch { /* 已断 */ }
      ch = await rpcConnect();
    }
  }
}

await connect();
await send("Page.enable");
await send("Runtime.enable");
await evalJs("1").catch(async () => { await connect(); });
await send("Page.bringToFront", {}).catch(() => {});
await send("Emulation.setFocusEmulationEnabled", { enabled: true }).catch(() => {});
await sleep(1500);

// reload 后轮询进板（boot 完成前侧栏按钮不存在）
async function gotoBoard(maxMs = 30000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    const ok = await evalJs(`(() => {
      if (document.querySelector('[data-testid=timeline-panel]')) return 'ONBOARD';
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

// ── 种子（合成材料）：桥 RPC 建案+案绑开庭排期（+3 天，看板下一节点确定性来源）+合成材料落盘 ──
let ch = await rpcConnect();
let matter = await rpcCall(ch, "matterCreate", { name: "合成案·时间线走查" });
check("S1 建案落桥（含建案自动节点）", Boolean(matter?.id), JSON.stringify(matter)?.slice(0, 80));
const d = new Date(); d.setDate(d.getDate() + 3);
const hearingDate = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
await rpcCall(ch, "matterEventAdd", { date: hearingDate, title: "合成排期·证据交换庭", kind: "hearing", location: "合成区法院第2法庭", caseId: matter.id });
const emptyCase = await rpcCall(ch, "matterCreate", { name: "合成案·空态走查" });
check("S2 空态案落桥", Boolean(emptyCase?.id), JSON.stringify(emptyCase)?.slice(0, 60));
for (const f of MY_FILES) {
  rmSync(join(MAT_DIR, f), { force: true });
}
writeFileSync(join(MAT_DIR, MY_FILES[0]), [
  "民事起诉状（合成材料，仅供时间线走查）",
  "原告：合成甲公司。被告：合成乙贸易行。",
  "2025年3月4日，原告与被告签订《合成设备买卖合同》，约定总价款人民币 18 万元。",
  "2025年5月9日，原告依约交付设备。",
  "2025年8月11日，原告向被告发出书面催告，要求十日内付清货款。",
  "2025年11月20日，原告向合成区人民法院提起诉讼。",
].join("\n"), "utf-8");
writeFileSync(join(MAT_DIR, MY_FILES[1]), [
  "民事调解书（合成材料，仅供时间线走查）",
  "2026年1月8日，经合成区人民法院主持调解，双方达成调解协议：被告分两期支付货款，",
  "第一期 10 万元于2026年2月10日前付清，第二期 8 万元于2026年4月10日前付清。",
].join("\n"), "utf-8");

// 种子落桥后强制 reload：页签可能挂载着上一轮的陈旧案件列表/面板状态（重跑场景），必须重挂载
await send("Page.reload", {}).catch(() => {});
await sleep(6000);

try {
  for (const type of ["keyDown", "keyUp"]) {
    await send("Input.dispatchKeyEvent", { type, key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  }
  await sleep(800);
  // 先直接导航（健康页签不轻举 reload——boot 可能因多页签/dev WS 竞态挂起）；
  // 进板后若时间轴面板缺失（旧 bundle），才 reload 一次重试。
  let nav = await gotoBoard(45000);
  if (nav === true && (await evalJs(`!!document.querySelector('[data-testid=timeline-panel]')`)) !== true) {
    await send("Page.reload", {}).catch(() => {});
    await sleep(6000);
    nav = await gotoBoard(45000);
  }
  check("W1 进入法律工作台（时间轴面板可见）", nav === true, String(nav));
  if (nav !== true) {
    const snap = await evalJs(`document.body?.innerText?.slice(0, 400) ?? "NO_BODY"`).catch(() => "EVAL_ERR");
    console.log(`[timeline-walk] 页面快照（诊断）: ${String(snap).replace(/\n/g, " | ").slice(0, 300)}`);
  }
  await sleep(1500);
  await evalJs(`(() => { const el = document.querySelector('[data-testid=timeline-panel]'); if (el) el.scrollIntoView({ block: "start" }); return !!el; })()`).catch(() => {});
  await sleep(400);
  check("W2 办案时间轴面板渲染", (await evalJs(`!!document.querySelector('[data-testid=timeline-panel]')`)) === true);

  // W3 建案自动节点上屏+auto 徽标（显式选中走查案——列表按 updated 倒序，后建的空态案会排第一）
  const selText = await evalJs(`(() => { const s = document.querySelector('[data-testid=timeline-case-select]'); const opt = [...s.options].find(o => o.textContent.includes('时间线走查')); if (opt) { s.value = opt.value; s.dispatchEvent(new Event('change', { bubbles: true })); } return s?.selectedOptions[0]?.textContent ?? null; })()`);
  await sleep(1200);
  check("W3 案件选择器选中走查案", Boolean(selText) && selText.includes("时间线走查"), String(selText));
  const autoNode = await evalJs(`(() => { const n = [...document.querySelectorAll('[data-testid=timeline-node]')]; return n.map(e => e.textContent).find(t => t.includes('建案')) ?? null; })()`);
  check("W3b 建案自动节点上屏（含服务端短句备注）",
    Boolean(autoNode) && autoNode.includes("建案") && autoNode.includes("新建案件"), String(autoNode).slice(0, 100));
  await shot("timeline-walk-1-rail.png");

  // W4 编辑模式：auto 行只有隐藏×（无编辑铅笔）；隐藏→还原 chips→还原
  const ensureEditOn = async () => {
    const on = await evalJs(`document.querySelector('[data-testid=timeline-edit-toggle]')?.getAttribute('aria-pressed') === 'true'`);
    if (!on) { await clickAt(q("[data-testid=timeline-edit-toggle]")); await sleep(500); }
  };
  await ensureEditOn();
  const autoRow = await evalJs(`(() => {
    const n = [...document.querySelectorAll('[data-testid=timeline-node]')].find(e => e.textContent.includes('建案'));
    return n ? {
      del: n.querySelector('[data-testid^=timeline-node-del-]')?.dataset.testid ?? null,
      badge: n.textContent.includes('业务动作生成'),
      noEditBtn: !n.querySelector('[aria-label="编辑节点"]'),
    } : null;
  })()`);
  check("W4 auto 行隐藏钮在行内+业务动作生成徽标+编辑铅笔缺席",
    Boolean(autoRow?.del) && autoRow.badge === true && autoRow.noEditBtn === true, JSON.stringify(autoRow));
  if (autoRow?.del && await clickAt(`document.querySelector('[data-testid=${autoRow.del}]')`)) {
    await sleep(1000);
    const chip = await evalJs(`(() => { const c = document.querySelector('[data-testid=timeline-restore-chips]'); return c ? c.textContent : null; })()`);
    check("W4b 软删后还原 chips 出现（只删显示不删库）", Boolean(chip) && chip.includes("建案"), String(chip).slice(0, 80));
    const chipBtn = await evalJs(`document.querySelector('[data-testid=timeline-restore-chips] button')?.dataset.testid ?? null`);
    if (chipBtn) {
      await clickAt(`document.querySelector('[data-testid=${chipBtn}]')`);
      await sleep(1000);
      const back = await evalJs(`(() => [...document.querySelectorAll('[data-testid=timeline-node]')].some(e => e.textContent.includes('建案')))()`);
      check("W4c 点 chip 还原回 rail", back === true, `back=${String(back)}`);
    }
  }
  await shot("timeline-walk-2-edit.png");

  // W5 空态两态（D5a）：切到空态案→确保编辑模式开→全隐藏→虚线框+还原 chips 同屏渲染
  await evalJs(`(() => { const s = document.querySelector('[data-testid=timeline-case-select]'); const opt = [...s.options].find(o => o.textContent.includes('空态走查')); if (opt) { s.value = opt.value; s.dispatchEvent(new Event('change', { bubbles: true })); } return s?.selectedOptions[0]?.textContent ?? null; })()`);
  await sleep(1200);
  await ensureEditOn(); // W5 状态机显式保证开
  await clickAt(`[...document.querySelectorAll('[data-testid=timeline-node]')][0]?.querySelector('[data-testid^=timeline-node-del-]')`);
  await sleep(1000);
  const emptyBox = await evalJs(`document.querySelector('[data-testid=timeline-empty]')?.textContent ?? null`);
  const chipsInEmpty = await evalJs(`(() => { const c = document.querySelector('[data-testid=timeline-restore-chips]'); return c ? c.textContent : null; })()`);
  check("W5 空态虚线框（双通道语义文案）", Boolean(emptyBox) && emptyBox.includes("还没有时间轴节点") && emptyBox.includes("自动生成"), String(emptyBox).slice(0, 80));
  check("W5b 空态下还原 chips 照常渲染（D5a）", Boolean(chipsInEmpty) && chipsInEmpty.includes("建案"), String(chipsInEmpty).slice(0, 60));
  // 还原回去
  const chip2 = await evalJs(`document.querySelector('[data-testid=timeline-restore-chips] button')?.dataset.testid ?? null`);
  if (chip2) { await clickAt(`document.querySelector('[data-testid=${chip2}]')`); await sleep(800); }
  await shot("timeline-walk-3-empty.png");

  // W6 回走查案→真模型抽取回合（oc28 链）：确认对话框自动接受→生成中→节点渲染
  // ⚠ 并行工位的清场型合成自测可能整库抹案（matter_synthetic/board_synthetic 清场段）——
  // 先守卫核对，被抹则重播种子（新案 id 重选）再继续，避免与邻道竞态误判自身失败。
  {
    const list1 = await rpcCall(ch, "matterList", {});
    if (!list1?.cases?.some((c) => c.id === matter.id)) {
      console.log("[timeline-walk] 走查案被并行清场抹除——重播种子（合成）");
      const re1 = await rpcCall(ch, "matterCreate", { name: "合成案·时间线走查" });
      matter.id = re1.id;
      await rpcCall(ch, "matterEventAdd", { date: hearingDate, title: "合成排期·证据交换庭", kind: "hearing", location: "合成区法院第2法庭", caseId: matter.id });
    }
  }
  await evalJs(`(() => { const s = document.querySelector('[data-testid=timeline-case-select]'); const opt = [...s.options].find(o => o.textContent.includes('时间线走查')); if (opt) { s.value = opt.value; s.dispatchEvent(new Event('change', { bubbles: true })); } return true; })()`);
  await sleep(1500);
  if (!(await clickAt(q("[data-testid=timeline-extract-btn]")))) throw new Error("抽取按钮点不到");
  // confirm 对话框由 javascriptDialogOpening 自动接受；轮询抽取完成（真模型回合，≤200s）
  let extracted = null;
  for (let i = 0; i < 50; i++) {
    await sleep(4000);
    extracted = await evalJs(`(() => ({
      info: document.querySelector('[data-testid=timeline-extract-info]')?.textContent ?? null,
      err: document.querySelector('[data-testid=timeline-extract-error]')?.textContent ?? null,
      nodes: document.querySelectorAll('[data-testid=timeline-node]').length,
    }))()`);
    if ((extracted?.info && extracted.nodes > 0) || extracted?.err) break;
  }
  check("W6 真模型抽取回合完成（新增计数回显+节点上屏）",
    Boolean(extracted?.info) && extracted.nodes > 0 && !extracted.err,
    JSON.stringify(extracted).slice(0, 140));
  const badge = await evalJs(`(() => document.querySelector('[data-testid=timeline-node-status]')?.textContent ?? null)()`);
  check("W6b 状态徽章六档渲染", Boolean(badge), String(badge));
  const refs = await evalJs(`(() => document.querySelector('[data-testid=timeline-node-refs]')?.textContent ?? null)()`);
  check("W6c 来源计数渲染（N 项材料依据/未绑定材料）",
    Boolean(refs) && (refs.includes("材料依据") || refs.includes("未绑定材料")), String(refs));
  await evalJs(`(() => { const el = document.querySelector('[data-testid=timeline-panel]'); if (el) el.scrollIntoView({ block: "start" }); return !!el; })()`);
  await sleep(500);
  await shot("timeline-walk-4-extract.png");

  // W7 编辑流真身：编辑模式→首个可编辑行改备注→保存→↺ 恢复到抽取原值
  await ensureEditOn();
  const editBtn = await evalJs(`(() => { const n = [...document.querySelectorAll('[data-testid=timeline-node]')].find(e => e.querySelector('[aria-label=编辑节点]')); return n ? n.getAttribute('data-testid') : null; })()`);
  check("W7 可编辑行（非 auto）在 rail", Boolean(editBtn), String(editBtn));
  if (editBtn) {
    await clickAt(`document.querySelector('[data-testid=${editBtn}] [aria-label=编辑节点]')`);
    await sleep(600);
    const beforeNote = await evalJs(`document.querySelector('[data-testid=timeline-edit-note]')?.value ?? null`);
    await typeInto("[data-testid=timeline-edit-note]", "走查覆盖备注（合成）");
    await clickAt(q("[data-testid=timeline-edit-save]"));
    await sleep(1200);
    const afterNote = await evalJs(`(() => document.querySelector('[data-testid=timeline-node-note]')?.textContent ?? null)()`);
    check("W7b 覆盖保存生效（备注=覆盖值）", afterNote === "走查覆盖备注（合成）", String(afterNote));
    // ↺ 恢复：点选该行展开详情（等待重渲染）→覆盖字段恢复钮
    await evalJs(`(() => {
      const n = [...document.querySelectorAll('[data-testid=timeline-node]')].find(e => e.textContent.includes('走查覆盖备注'));
      n?.querySelector('[data-testid=timeline-node-main]')?.click();
      return !!n;
    })()`);
    await sleep(1000);
    const restoreId = await evalJs(`(() => {
      const n = [...document.querySelectorAll('[data-testid=timeline-node]')].find(e => e.textContent.includes('走查覆盖备注'));
      return n?.querySelector('[data-testid=timeline-node-restore-note]')?.dataset.testid ?? null;
    })()`);
    check("W7c 已覆盖字段↺ 钮在详情面（备注字段）", Boolean(restoreId), String(restoreId));
    if (restoreId) {
      await clickAt(`document.querySelector('[data-testid=${restoreId}]')`);
      await sleep(1000);
      const restored = await evalJs(`(() => document.querySelector('[data-testid=timeline-node-note]')?.textContent ?? null)()`);
      check("W7d ↺ 恢复到抽取原值", restored === beforeNote && restored !== "走查覆盖备注（合成）", `${String(beforeNote).slice(0, 30)} -> ${String(restored).slice(0, 30)}`);
    }
  }
  await shot("timeline-walk-5-editflow.png");

  // W8 看板翻牌（对拍 84；2026-10-28 行整编语义对齐——原断言「空态案显建案今天」是翻牌实现
  // 副产物，与 RE-3 节点=里程碑语义相悖（建案恒为当日，永远压过未来节点，board_walk W12 实证），
  // 随 boardShapeTimelineRows 整编改为：主案下一节点=案绑开庭里程碑（孪生「开庭排期」行让位
  // 日程行标题）；空态案无阶段节点行→显「暂无排期节点」（RE-3 件4 口径），行政行不外溢。
  const boardNav = await gotoBoard(20000);
  check("W8 看板案件卡滚动就位", boardNav === true, String(boardNav));
  await evalJs(`(() => { const el = document.querySelector('[data-testid=board-cases]'); if (el) el.scrollIntoView({ block: "center" }); return !!el; })()`);
  await sleep(600);
  const nodeOf = (name) => evalJs(`(() => {
    const cards = [...document.querySelectorAll('[data-testid=board-case-card]')];
    const el = cards.find(e => e.textContent.includes('${name}'));
    return el ? el.querySelector('[data-testid=board-case-node]')?.textContent ?? null : null;
  })()`);
  const mainNode = await nodeOf("合成案·时间线走查");
  check("W8b 下一节点=案绑开庭里程碑（+3 天证据交换庭；孪生开庭排期行让位日程标题）",
    Boolean(mainNode) && mainNode.includes("合成排期·证据交换庭") && mainNode.includes("3 天后")
      && !mainNode.includes("开庭排期") && !mainNode.includes("建案"), String(mainNode));
  const emptyNode = await nodeOf("合成案·空态走查");
  check("W8c 空态案无阶段节点行→「暂无排期节点」（建案行政行不作节点）",
    Boolean(emptyNode) && emptyNode.includes("暂无排期节点") && !emptyNode.includes("建案"), String(emptyNode));
  await shot("timeline-walk-6-board-node.png");
} catch (e) {
  check("走查执行", false, e?.message ?? String(e));
} finally {
  // ── 清场（合成数据不留库；材料只删自建的）──
  try {
    ch = ch ?? await rpcConnect();
    if (matter?.id) await rpcCall(ch, "matterDelete", { id: matter.id });
    if (emptyCase?.id) await rpcCall(ch, "matterDelete", { id: emptyCase.id });
    for (const f of MY_FILES) rmSync(join(MAT_DIR, f), { force: true });
    const left = await rpcCall(ch, "matterList", {});
    console.log(`[timeline-walk] 清场后案件数=${left?.cases?.length ?? "?"}`);
  } catch (e) {
    console.log(`[timeline-walk] 清场异常（如实留痕）: ${e?.message ?? e}`);
  }
  try { rpcWs?.close(); } catch { /* 已断 */ }
}
const okAll = results.every((r) => r.ok);
console.log(okAll ? "TIMELINE_WALK_PASS" : "TIMELINE_WALK_FAIL");
process.exit(okAll ? 0 : 1);
