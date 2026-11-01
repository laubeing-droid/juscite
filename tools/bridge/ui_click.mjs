// 一次性走查辅助：CDP 真实输入（Input.dispatchMouseEvent=trusted）+ 元素坐标查找。
// 用法: node ui_click.mjs <selector-js> [selector-js-2 ...]  每个参数点一次；selector 在页面里 eval 返回元素。
import WebSocket from "ws";
import http from "node:http";

const CDP = process.env.CDP_PORT ? "http://127.0.0.1:" + process.env.CDP_PORT : "http://127.0.0.1:9223";
const exprs = process.argv.slice(3);
const mode = process.argv[2];
function getJson(path) {
  return new Promise((res, rej) => {
    http.get(CDP + path, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => res(JSON.parse(d))); }).on("error", rej);
  });
}
const list = await getJson("/json/list");
const target = list.find((t) => t.type === "page" && (t.url || "").includes("5173")) ?? list.find((t) => t.type === "page");
const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 128 * 1024 * 1024 });
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
let mid = 0; const pending = new Map();
ws.on("message", (raw) => { const m = JSON.parse(raw.toString()); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++mid; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const evalJs = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error("EXC: " + (r.exceptionDetails.exception?.description ?? r.exceptionDetails.text));
  return r.result?.value;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

if (mode === "click") {
  for (const expr of exprs) {
    const rect = await evalJs(`(() => { const el = ${expr}; if (!el) return null; el.scrollIntoView({block: "center"}); const r = el.getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; })()`);
    if (!rect) { console.log("MISS " + expr.slice(0, 60)); continue; }
    for (const type of ["mousePressed", "mouseReleased"]) {
      await send("Input.dispatchMouseEvent", { type, x: rect.x, y: rect.y, button: "left", clickCount: 1 });
    }
    console.log("CLICKED at", JSON.stringify(rect));
    await sleep(900);
  }
} else if (mode === "type") {
  // type <selector-js> <text>: 聚焦后用 Input.insertText
  const sel = exprs[0]; const text = exprs[1] ?? "";
  const rect = await evalJs(`(() => { const el = ${sel}; if (!el) return null; el.focus(); const r = el.getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; })()`);
  if (!rect) { console.log("MISS target"); process.exit(1); }
  await send("Input.dispatchMouseEvent", { type: "mousePressed", x: rect.x, y: rect.y, button: "left", clickCount: 1 });
  await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: rect.x, y: rect.y, button: "left", clickCount: 1 });
  await evalJs(`(() => { const el = ${sel}; const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ""); el.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  await send("Input.insertText", { text });
  console.log("TYPED", JSON.stringify(text.slice(0, 30)));
} else if (mode === "eval") {
  console.log(JSON.stringify(await evalJs(exprs[0])));
}
ws.close();
process.exit(0);
