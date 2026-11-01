// R30 补充探针：audit:list reject 路径实测（对拍 5 错误出口——catch 仅置错误信息、不触 chainOk、
// 徽章停留灰态不转红+列表区红字）。方法：CDP 打开已运行的 vite:5176 页 → 从 DOM fiber 上溯
// ServiceProvider 读 services accessor → 现场把 zcodeAgentService.auditList 换成 reject 的
// Promise（运行时猴补丁，不改任何代码文件）→ 关面板重开触发全新 auditList → 读徽章态+错误行。
// 用法：node tools/bridge/re30_reject_probe.mjs（需 vite 5176 与 CDP 9223 在跑）。
import WebSocket from "ws";
import http from "node:http";

const CDP = process.env.CDP_PORT ?? "http://127.0.0.1:9223";
const APP = process.env.R30_APP_URL ?? "http://localhost:5176/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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
  await sleep(1500);
}
const ws = new WebSocket(tab.webSocketDebuggerUrl, { maxPayload: 64 * 1024 * 1024 });
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
let mid = 0; const pending = new Map();
ws.on("message", (raw) => {
  const m = JSON.parse(raw.toString());
  if (m.id && pending.has(m.id)) {
    const p = pending.get(m.id); pending.delete(m.id);
    m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
  }
});
const send = (method, params = {}) => new Promise((res, rej) => {
  const id = ++mid; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params }));
});
async function evalJs(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error("EXC: " + (r.exceptionDetails.exception?.description ?? r.exceptionDetails.text).slice(0, 600));
  return r.result?.value;
}
await send("Runtime.enable"); await send("Page.enable");
await send("Page.bringToFront", {});

async function waitFor(expr, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await evalJs(`!!(${expr})`)) return true;
    await sleep(500);
  }
  throw new Error("waitFor 超时: " + (label ?? expr));
}

await waitFor(`document.querySelector('[data-testid="audit-sidebar-entry"]')`, 90000, "侧栏审计入口");

// 1) 打开面板（干净态先看一眼绿徽章）
async function click(selector) {
  const rect = await evalJs(`(() => { const el = document.querySelector('${selector}'); if (!el) return null; el.scrollIntoView({ block: "center" }); const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  if (!rect) throw new Error("MISS " + selector);
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x: rect.x, y: rect.y, button: "left", clickCount: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: rect.x, y: rect.y, button: "left", clickCount: 1 });
  await sleep(800);
}
await click('[data-testid="audit-sidebar-entry"]');
await waitFor(`document.querySelector('[data-testid="audit-center"]')`, 15000, "面板打开");
await waitFor(`document.querySelector('[data-testid="audit-chain-badge"]')?.dataset.state === "ok"`, 10000, "绿徽章（先证干净态链验真）");

// 2) 从 fiber 上溯找 ServiceProvider，猴补 auditList 为 reject
const patched = await evalJs(`(() => {
  const el = document.querySelector('[data-testid="audit-center"]');
  const fk = Object.keys(el).find((k) => k.startsWith("__reactFiber$"));
  if (!fk) return { ok: false, why: "no fiber key" };
  let f = el[fk];
  for (let i = 0; i < 200 && f; i++, f = f.return) {
    const v = f.pendingProps?.value;
    if (v && typeof v === "object" && v.zcodeAgentService) {
      const svc = v.zcodeAgentService;
      const before = typeof svc.auditList;
      const rejector = { auditList: () => Promise.reject(new Error("E2E-forced-reject-对拍5")) };
      let setErr = null;
      try { v.zcodeAgentService = rejector; } catch (e) { setErr = String(e); }
      const readBack = v.zcodeAgentService === rejector;
      return { ok: true, before, after: typeof svc.auditList, readBack, setErr };
    }
  }
  return { ok: false, why: "provider not found" };
})()`);
console.log("[probe] patch:", JSON.stringify(patched));
if (!patched.ok) process.exit(2);

// 3) 关面板重开 → 新挂载必发 auditList → reject
await click('[data-testid="audit-close"]');
await click('[data-testid="audit-sidebar-entry"]');
await waitFor(`document.querySelector('[data-testid="audit-center"]')`, 10000, "重开");
await sleep(1500);

const state = await evalJs(`(() => ({
  badge: document.querySelector('[data-testid="audit-chain-badge"]')?.dataset.state,
  badgeText: document.querySelector('[data-testid="audit-chain-badge"]')?.innerText.trim(),
  err: document.querySelector('[data-testid="audit-error"]')?.innerText ?? null,
  errColor: document.querySelector('[data-testid="audit-error"]') ? getComputedStyle(document.querySelector('[data-testid="audit-error"]')).color : null,
  detail: document.querySelector('[data-testid="audit-detail"]')?.innerText.slice(0, 80) ?? null,
}))()`);
console.log("[probe] reject 后面板实态:", JSON.stringify(state, null, 2));

const ok = state.badge === "checking" && (state.badgeText ?? "").includes("链校验中")
  && (state.err ?? "").includes("E2E-forced-reject-对拍5");
console.log(ok ? "R30_REJECT_PROBE_PASS" : "R30_REJECT_PROBE_FAIL");

// 截图留证
const shot = await send("Page.captureScreenshot", { format: "png" });
const fs = await import("node:fs");
fs.writeFileSync(".local/re30-reject-probe.png", Buffer.from(shot.data, "base64"));

// 4) 恢复现场：刷新页面清猴补丁
await send("Page.navigate", { url: APP });
process.exit(ok ? 0 : 1);
