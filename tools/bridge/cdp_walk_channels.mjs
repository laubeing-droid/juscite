// Unknown channel 清零走查（施工单-02 任务三④，方法承 M4 取证文档 CDP 走查）。
// 前置：vite dev :5173（代理 :3030 桥）+ 调试 Chrome :9223 独立 profile（勿动用户浏览器）。
// 流程：reload → 收启动 console → 逐个点导航面（自动化/法律工作台/插件市场/任务/连接使用）
//       → 法律工作台内逐 tab → 二次 reload → 汇总 Unknown channel/报错清单。
// 用法: node cdp_walk_channels.mjs [outJson 路径]；stdout 打摘要，JSON 落盘供证据归档。
import WebSocket from "ws";
import http from "node:http";
import fs from "node:fs";

const CDP = "http://127.0.0.1:9223";
const OUT = process.argv[2];
function getJson(path) {
  return new Promise((res, rej) => {
    http.get(CDP + path, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => res(JSON.parse(d))); }).on("error", rej);
  });
}
const list = await getJson("/json/list");
const target = list.find((t) => t.type === "page" && (t.url || "").includes("5173")) ?? list.find((t) => t.type === "page");
if (!target) { console.log("NO_PAGE"); process.exit(1); }
const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 128 * 1024 * 1024 });
await new Promise((r) => ws.on("open", r));
let mid = 0;
const pending = new Map();
const entries = []; // {at, kind, text}
function send(method, params = {}) {
  return new Promise((res, rej) => { const id = ++mid; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
}
ws.on("message", (raw) => {
  const m = JSON.parse(raw.toString());
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); return; }
  if (m.method === "Runtime.consoleAPICalled") {
    const text = (m.params.args ?? []).map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 500);
    entries.push({ at: Date.now(), kind: `console.${m.params.type}`, text });
  } else if (m.method === "Runtime.exceptionThrown") {
    entries.push({ at: Date.now(), kind: "exception", text: String(m.params.exceptionDetails?.exception?.description ?? m.params.exceptionDetails?.text ?? "").slice(0, 500) });
  } else if (m.method === "Log.entryAdded") {
    entries.push({ at: Date.now(), kind: `log.${m.params.entry?.level}`, text: String(m.params.entry?.text ?? "").slice(0, 500) });
  }
});
await send("Runtime.enable");
await send("Page.enable");
await send("Log.enable");
async function evalJs(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) return "EXC: " + String(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text).slice(0, 300);
  return r.result?.value;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const CLICK_HELPER = `
window.__clickByText = function (t) {
  const els = [...document.querySelectorAll('button,[role=button],[role=tab],a,[class*=item],[class*=Item],[class*=nav] *')];
  const el = els.find((e) => (e.textContent || '').trim() === t && e.offsetParent !== null);
  if (!el) return 'NOT_FOUND:' + t;
  el.click();
  return 'CLICKED:' + t;
};
'helper-ready'`;
const TOP_NAVS = ["自动化", "法律工作台", "插件市场", "任务", "连接使用"];
const steps = [];
const mark = (s) => { steps.push({ at: Date.now(), step: s }); console.log("[walk] " + s); };

mark("reload#1");
await evalJs("location.reload(); 'ok'");
await sleep(9000);
await evalJs(CLICK_HELPER);
for (const nav of TOP_NAVS) {
  mark("click " + nav);
  mark(await evalJs(`window.__clickByText(${JSON.stringify(nav)})`));
  await sleep(1600);
  if (nav === "法律工作台") {
    // 八法律面等子 tab：点击后枚举新出现的短文本按钮逐个点
    const kids = await evalJs("JSON.stringify([...new Set([...document.querySelectorAll('button,[role=tab]')].map(e=>(e.textContent||'').trim()).filter(t=>t&&t.length<=6&&t!==\"法律工作台\"))].slice(0,20))");
    let kidList = [];
    try { kidList = JSON.parse(kids ?? "[]"); } catch { /* 解析失败按空 */ }
    for (const k of kidList) {
      mark("click 子tab " + k);
      await evalJs(`window.__clickByText(${JSON.stringify(k)})`);
      await sleep(1300);
    }
  }
}
mark("reload#2");
await evalJs("location.reload(); 'ok'");
await sleep(9000);

const unknownChannels = [...new Set(entries.map((e) => e.text).join("\n").match(/Unknown channel[: ]*"?([\w-]+)"?/g) ?? [])]
  .map((s) => s.replace(/Unknown channel[: ]*"?([\w-]+)"?/, "$1"));
const errors = entries.filter((e) => e.kind.includes("error") || e.kind === "exception" || /unknown channel|event not found|timeout|fail/i.test(e.text));
const summary = {
  at: new Date().toISOString(),
  pageUrl: target.url,
  totalConsoleEntries: entries.length,
  errorEntries: errors.length,
  unknownChannels,
  steps,
};
console.log("---- 摘要 ----");
console.log(JSON.stringify({ ...summary, steps: undefined }, null, 2));
console.log("---- 报错/异常条目（" + errors.length + "）----");
for (const e of errors.slice(-80)) console.log(`[${e.kind}] ${e.text.slice(0, 220)}`);
if (OUT) {
  fs.mkdirSync(OUT.slice(0, OUT.lastIndexOf("\\")) ? OUT.slice(0, OUT.lastIndexOf("\\")) : ".", { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify({ ...summary, entries, errors }, null, 2));
  console.log("EVIDENCE_JSON " + OUT);
}
ws.close();
process.exit(unknownChannels.length ? 2 : 0); // 退出码：0=无 Unknown channel，2=有
