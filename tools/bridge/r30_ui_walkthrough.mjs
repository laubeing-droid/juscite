// R30 UI 真形态走查（RE-30 验收）：vite 独立实例（5176，BRIDGE_PORT=3077 隔离桥）+
// 调试 Chrome 9223 独立 tab + CDP trusted 输入。链路：侧栏底部入口存在→点击开审计中心→
// 徽章绿态（链验真）→摘要四卡→挂载自动选中隐私行+详情→切 tab 清选自动回退首行（对拍 54）→
// 规则目录 14 类展开/收起→遮罩点击关+×关→设置安全节导流卡（关设置+开审计，对拍 2）→
// 桥杀掉后错误路径：徽章停留灰态不转红+列表红字（对拍 5 错误出口）→重启后重开可见新行（对拍 57）。
// 用法：node --import tsx tools/bridge/r30_ui_walkthrough.mjs；末行 R30_UI_PASS / R30_UI_FAIL。
import WebSocket from "ws";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { join } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { rmSync } from "node:fs";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const NODE = process.execPath;
const CDP = process.env.CDP_PORT ?? "http://127.0.0.1:9223";
const PORT = Number(process.env.R30_BRIDGE_PORT ?? 3077);
const WEB_PORT = 5176;
const APP = process.env.R30_APP_URL ?? `http://localhost:${WEB_PORT}/`;
const OUT = path.join(REPO_ROOT, "evidence", "步骤4-安全审计中心-RE30-20261027", "ui-walkthrough");
fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const dbPath = path.join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${PORT}.db`);

function killPortBridge(port) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue).OwningProcess`],
    { encoding: "utf-8", timeout: 20000 });
  const pid = Number(String(r.stdout ?? "").trim().split(/\s+/)[0]);
  if (!pid) return;
  const cl = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  if (String(cl.stdout ?? "").includes("bridge_host.mjs")) {
    spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
    console.log(`[walk] 清理端口 ${port} 残留桥 pid=${pid}`);
  }
}
function spawnBridge() {
  const log = fs.openSync(path.join(REPO_ROOT, ".local", `re30-walk-bridge-${PORT}.log`), "a");
  const child = spawn(NODE, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(PORT) }, stdio: ["ignore", log, log], detached: true });
  child.unref();
  return child.pid;
}
function spawnVite() {
  const log = fs.openSync(path.join(REPO_ROOT, ".local", `re30-walk-vite-${WEB_PORT}.log`), "a");
  const child = spawn("pnpm", ["--filter", "@zcode/web", "exec", "vite", "--port", String(WEB_PORT), "--strictPort"],
    { cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(PORT) }, stdio: ["ignore", log, log], detached: true, shell: true });
  child.unref();
  return child.pid;
}
async function probeHttp(url, timeoutMs = 2500) {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    return r.ok;
  } catch { return false; }
}
async function waitHttp(url, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) { if (await probeHttp(url)) return true; await sleep(600); }
  throw new Error("等待超时: " + label);
}
const PRIVACY_DETAIL = JSON.stringify({
  kind: "privacy-redaction", requestId: "sum-walk-1", scenario: "summary", provider: "deepseek",
  model: "deepseek-chat", policyVersion: "juscite-redaction-v1", status: "success",
  originalChars: 900, outboundChars: 840, totalMatches: 6,
  counts: { person_name: 4, id_card: 2 }, toolCalls: 0,
  payloadDigest: "b".repeat(64),
});
let ch = null;
async function rpcConnect(port) {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/ws`);
  ws.binaryType = "arraybuffer";
  const data = { fire: () => {} };
  ws.on("message", (buf) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
  await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
  const isocket = {
    onData: (l) => { data.fire = l; return { dispose: () => {} }; },
    onClose: () => ({ dispose: () => {} }),
    onEnd: () => ({ dispose: () => {} }),
    write: (b) => ws.send(b.buffer),
    end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
  };
  ch = new ChannelClient(new SocketProtocol(isocket)).getChannel("zcode-agent");
  await ch.call("helloConversationV4", []);
}
const call = (m, a) => ch.call(m, a === undefined ? [] : [a]);

// ── 起隔离桥+vite（净库起步：删旧库→完成 onboarding（向导不挡道）→经渲染层同款通道种 3 行）──
killPortBridge(PORT);
for (const suffix of ["", "-wal", "-shm"]) { try { rmSync(dbPath + suffix, { force: true }); } catch { /* 净 */ } }
let bridgePid = spawnBridge();
await waitHttp(`http://127.0.0.1:${PORT}/api/server-info`, 40000, "隔离桥");
await rpcConnect(PORT);
await call("onboardingComplete", { demo: false, startGuide: false }); // 向导不挡道（RE-29 域）
await call("auditAppend", { actor: "隐私网关", action: "privacy.redaction", target: "unbound", detail: JSON.parse(PRIVACY_DETAIL) });
await call("auditAppend", { actor: "律师", action: "case.create", target: "mat_walk1", detail: "合成：走查对拍案" });
await call("auditAppend", { actor: "律师", action: "task.add", target: "cbt_walk1", detail: "合成：整理证据清单" });
let vitePid = spawnVite();
await waitHttp(`http://localhost:${WEB_PORT}/`, 90000, "vite 独立实例");

// ── CDP 连调试 Chrome（9223 独立实例，trusted 输入）──
function getJson(p) {
  return new Promise((res, rej) => {
    http.get(CDP + p, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => res(JSON.parse(d))); }).on("error", rej);
  });
}
const tabs = await getJson("/json/list");
let tab = tabs.find((t) => t.type === "page" && (t.url || "").startsWith(APP));
if (!tab) {
  const r = await fetch(CDP + "/json/new?" + encodeURIComponent(APP), { method: "PUT" });
  tab = await r.json();
}
console.log("[walk] tab:", tab.id, tab.url);
const ws = new WebSocket(tab.webSocketDebuggerUrl, { maxPayload: 128 * 1024 * 1024 });
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
let mid = 0; const pending = new Map();
ws.on("message", (raw) => { const m = JSON.parse(raw.toString()); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++mid; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
// 侧栏挂点需要桌面级宽度：把窗口抬到 1500×900（真窗口尺寸，trusted 坐标不漂移）
try {
  const { windowId, bounds } = await send("Browser.getWindowForTarget");
  await send("Browser.setWindowBounds", { windowId, bounds: { ...bounds, windowState: "normal", width: 1500, height: 900 } });
} catch { /* 无 Browser 域权限时按原窗口继续 */ }

await send("Runtime.enable"); await send("Page.enable");
await send("Page.navigate", { url: APP });
await send("Page.bringToFront", {});
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
    await sleep(700);
  }
  throw new Error("waitFor 超时: " + (label ?? expr));
}
const results = [];
const check = (name, ok, detail) => { results.push({ name, ok }); console.log(`[walk] ${name}: ${ok ? "OK" : "FAIL"} ${detail ?? ""}`); };

try {
  // ── S1 主界面+侧栏底部入口（对拍 1：盾+主/副文案+title）──
  await waitFor(`document.querySelector('[data-testid="audit-sidebar-entry"]')`, 90000, "侧栏审计入口");
  const entry = await evalJs(`(() => { const el = document.querySelector('[data-testid="audit-sidebar-entry"]'); return { text: el.innerText.replace(/\\n/g, "|"), title: el.getAttribute("title"), belowFooter: (() => { const f = document.querySelector('[data-testid="task-settings-button"]'); return !f || el.getBoundingClientRect().top > f.getBoundingClientRect().top; })() }; })()`);
  check("S1 侧栏底部入口（盾+双行+title+账户区之下）",
    entry.text.includes("安全审计") && entry.text.includes("脱敏与操作留痕") && entry.title && entry.belowFooter,
    JSON.stringify(entry));
  await shot("s1-sidebar-entry.png");

  // ── S2 点击开审计中心：dialog/aria-modal/aria-label + 徽章绿态（对拍 3/5/6）──
  await tclick(`document.querySelector('[data-testid="audit-sidebar-entry"]')`);
  await waitFor(`document.querySelector('[data-testid="audit-center"]')`, 15000, "审计中心打开");
  const dlg = await evalJs(`(() => { const el = document.querySelector('[data-testid="audit-center"]'); return { role: el.getAttribute("role"), modal: el.getAttribute("aria-modal"), label: el.getAttribute("aria-label") }; })()`);
  check("S2 dialog/aria-modal/aria-label", dlg.role === "dialog" && dlg.modal === "true" && dlg.label === "安全审计中心", JSON.stringify(dlg));
  await waitFor(`document.querySelector('[data-testid="audit-chain-badge"]')?.dataset.state === "ok"`, 10000, "徽章绿态");
  const badgeOk = await evalJs(`document.querySelector('[data-testid="audit-chain-badge"]').innerText.trim()`);
  check("S2 链徽章绿态（校验通过）", badgeOk.includes("链校验通过"), `badge=${badgeOk}`);
  await shot("s2-panel-badge-ok.png");

  // ── S3 摘要四卡（对拍 8/9）──
  const cards = await evalJs(`({
    total: document.querySelector('[data-testid="audit-card-total"]')?.innerText,
    privacy: document.querySelector('[data-testid="audit-card-privacy"]')?.innerText,
    hits: document.querySelector('[data-testid="audit-card-hits"]')?.innerText,
    policy: document.querySelector('[data-testid="audit-card-policy"]')?.innerText,
  })`);
  check("S3 四卡：总数3/脱敏1/命中6/版本+14类",
    cards.total.includes("3") && cards.total.includes("200")
    && cards.privacy.includes("1")
    && cards.hits.includes("6")
    && cards.policy.includes("juscite-redaction-v1") && cards.policy.includes("14 类规则"),
    JSON.stringify(cards));

  // ── S4 挂载自动选中隐私行+详情（对拍 53）──
  const autoSel = await evalJs(`(() => {
    const sel = document.querySelector('[data-testid="audit-list"] .bg-selected');
    const kind = sel?.dataset.rowKind;
    const detail = document.querySelector('[data-testid="audit-detail-privacy"]');
    return { kind, hasPrivacyDetail: !!detail, detailFull: detail?.innerText ?? "" };
  })()`);
  check("S4 自动选中首条隐私行+出站脱敏详情", autoSel.kind === "privacy" && autoSel.hasPrivacyDetail
    && autoSel.detailFull.includes("案件摘要") && autoSel.detailFull.includes("已完成")
    && autoSel.detailFull.includes("处理字符") && autoSel.detailFull.includes("安全摘要")
    && autoSel.detailFull.includes("4× 姓名") && autoSel.detailFull.includes("未命中") === false,
    JSON.stringify(autoSel).slice(0, 300));
  await shot("s4-privacy-detail.png");

  // ── S5 三 tab 实时计数+切换清选自动回退（对拍 10/54）──
  const tabTexts = await evalJs(`[...document.querySelectorAll('[role="tab"]')].map((t) => t.innerText.trim())`);
  check("S5a 三 tab 计数", tabTexts.length === 3 && tabTexts[0] === "全部 3" && tabTexts[1] === "出站脱敏 1" && tabTexts[2] === "本地操作 2",
    JSON.stringify(tabTexts));
  await tclick(`document.querySelector('[data-testid="audit-tab-ops"]')`);
  await sleep(600);
  const opsView = await evalJs(`(() => {
    const rows = document.querySelectorAll('[data-testid="audit-list"] [data-row-kind="ops"]').length;
    const sel = document.querySelector('[data-testid="audit-list"] .bg-selected');
    const detail = document.querySelector('[data-testid="audit-detail-ops"]');
    const placeholder = document.querySelector('[data-testid="audit-detail-placeholder"]');
    return { rows, selKind: sel?.dataset.rowKind, hasOpsDetail: !!detail, hasPlaceholder: !!placeholder,
      detailFull: detail?.innerText ?? "" };
  })()`);
  // 回退首行=rowid 倒序过滤集第一行=最新的 task.add 行（非占位即等量语义成立）
  check("S5b 切本地操作 tab：清选后详情自动回退过滤集首行非占位", opsView.rows === 2 && opsView.selKind === "ops"
    && opsView.hasOpsDetail && !opsView.hasPlaceholder && opsView.detailFull.includes("task.add")
    && opsView.detailFull.includes("合成：整理证据清单"),
    JSON.stringify(opsView).slice(0, 240));
  await shot("s5-ops-tab-fallback.png");

  // ── S6 规则目录展开 14 类/收起（对拍 11）──
  await tclick(`document.querySelector('[data-testid="audit-rules-toggle"]')`);
  await sleep(400);
  const ruleCount = await evalJs(`document.querySelectorAll('[data-testid="audit-rules-list"] li').length`);
  await tclick(`document.querySelector('[data-testid="audit-rules-toggle"]')`);
  await sleep(300);
  const ruleGone = await evalJs(`!document.querySelector('[data-testid="audit-rules-list"]')`);
  check("S6 规则目录 14 类展开/收起", ruleCount === 14 && ruleGone, `count=${ruleCount} gone=${ruleGone}`);

  // ── S7 打开期间新写入不实时出现；重开可见（对拍 57）──
  const preCount = await evalJs(`document.querySelectorAll('[data-testid="audit-list"] [data-row-kind]').length`);
  await call("auditAppend", { actor: "律师", action: "client.create", target: "cli_walk1", detail: "合成：走查期间新客户" });
  await sleep(2000);
  const postCount = await evalJs(`document.querySelectorAll('[data-testid="audit-list"] [data-row-kind]').length`);
  check("S7a 打开期间新写入不可见（无推送/轮询）", preCount === 2 && postCount === 2, `pre=${preCount} post=${postCount}`);

  // ── S8 × 关闭 + 遮罩点击关闭（对拍 3）──
  await tclick(`document.querySelector('[data-testid="audit-close"]')`);
  await sleep(500);
  const closedByX = !(await evalJs(`!!document.querySelector('[data-testid="audit-center"]')`));
  await tclick(`document.querySelector('[data-testid="audit-sidebar-entry"]')`);
  await waitFor(`document.querySelector('[data-testid="audit-center"]')`, 10000, "重开");
  await sleep(700);
  const reOpened = await evalJs(`document.querySelectorAll('[data-testid="audit-list"] [data-row-kind]').length`);
  check("S7b 重开=全新拉取（新行可见+徽章绿）", reOpened === 4
    && (await evalJs(`document.querySelector('[data-testid="audit-chain-badge"]')?.dataset.state`)) === "ok",
    `rows=${reOpened}`);
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x: 6, y: 400, button: "left", clickCount: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: 6, y: 400, button: "left", clickCount: 1 });
  await sleep(500);
  const closedByMask = !(await evalJs(`!!document.querySelector('[data-testid="audit-center"]')`));
  check("S8 ×关+遮罩点关", closedByX && closedByMask, `x=${closedByX} mask=${closedByMask}`);

  // ── S9 设置安全节导流卡：关设置+开审计（对拍 2）──
  await tclick(`document.querySelector('[data-testid="task-settings-button"]')`);
  await waitFor(`document.querySelector('[data-testid="settings-page"]')`, 20000, "设置页打开");
  await tclick(`document.querySelector('[data-settings-section-nav="stealth"]')`);
  await waitFor(`document.querySelector('[data-testid="settings-security-audit-open"]')`, 15000, "审计导流卡");
  await shot("s9-settings-card.png");
  await tclick(`document.querySelector('[data-testid="settings-security-audit-open"]')`);
  await waitFor(`document.querySelector('[data-testid="audit-center"]')`, 10000, "导流卡开审计");
  const settingsClosed = !(await evalJs(`!!document.querySelector('[data-testid="settings-page"]')`));
  check("S9 导流卡=关设置+开审计", settingsClosed, `settingsClosed=${settingsClosed}`);
  await tclick(`document.querySelector('[data-testid="audit-close"]')`);
  await sleep(400);

  // ── S10 错误路径（对拍 5 关键等量）：桥杀掉→重开面板→audit.list 不落定→徽章必须停留灰态不转红 ──
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  await sleep(1200);
  await tclick(`document.querySelector('[data-testid="audit-sidebar-entry"]')`);
  await sleep(2500);
  // 事实采集：桥死后通道行为（reject→红字态 / 挂起重连→加载态），两者徽章都必须停留 checking
  const errState = await evalJs(`(() => ({
    open: !!document.querySelector('[data-testid="audit-center"]'),
    badge: document.querySelector('[data-testid="audit-chain-badge"]')?.dataset.state,
    badgeText: document.querySelector('[data-testid="audit-chain-badge"]')?.innerText.trim(),
    err: document.querySelector('[data-testid="audit-error"]')?.innerText.slice(0, 60) ?? null,
    loading: document.querySelector('[data-testid="audit-loading"]')?.innerText ?? null,
  }))()`);
  console.log("[walk] S10 桥死后面板实态:", JSON.stringify(errState));
  const settled = await evalJs(`(async () => {
    const deadline = Date.now() + 25000;
    while (Date.now() < deadline) {
      const b = document.querySelector('[data-testid="audit-chain-badge"]')?.dataset.state;
      if (b === "bad") return "badge-bad";
      const err = document.querySelector('[data-testid="audit-error"]');
      if (err) return "error-line:" + err.innerText.slice(0, 50);
      await new Promise((r) => setTimeout(r, 800));
    }
    return "still-checking-after-25s";
  })()`);
  check("S10 读取失败：徽章停留灰态不转红", errState.open && errState.badge === "checking"
    && errState.badgeText.includes("链校验中") && settled !== "badge-bad",
    `settled=${settled} errLine=${errState.err ?? "无"}`);
  await shot("s10-error-badge-gray.png");

  // ── S11 桥重启→刷新页面（取新连接）→重开面板恢复（链验真+数据在）──
  bridgePid = spawnBridge();
  await waitHttp(`http://127.0.0.1:${PORT}/api/server-info`, 40000, "桥重启");
  await send("Page.navigate", { url: APP }); // 断线重连时序归应用层，不归本单强证——刷新取全新连接
  await sleep(2500);
  await waitFor(`document.querySelector('[data-testid="audit-sidebar-entry"]')`, 90000, "刷新后主界面");
  await tclick(`document.querySelector('[data-testid="audit-sidebar-entry"]')`);
  await waitFor(`document.querySelector('[data-testid="audit-chain-badge"]')?.dataset.state === "ok"`, 20000, "重启后徽章绿");
  const afterRestart = await evalJs(`document.querySelectorAll('[data-testid="audit-list"] [data-row-kind]').length`);
  check("S11 桥重启后重开：链验真+4 行在", afterRestart === 4, `rows=${afterRestart}`);
  await shot("s11-after-restart.png");
} catch (e) {
  console.error("[walk] 主链失败:", String(e?.message ?? e).slice(0, 400));
  await shot("sX-failure.png").catch(() => {});
  results.push({ name: "主链", ok: false });
}
const failed = results.filter((r) => !r.ok);
console.log(failed.length ? "R30_UI_FAIL" : "R30_UI_PASS");
process.exit(failed.length ? 1 : 0);
