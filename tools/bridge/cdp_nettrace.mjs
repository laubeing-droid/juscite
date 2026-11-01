// 长驻网络观测 v2：reload→点击→找下行帧中的 conversation 帧
import WebSocket from "ws";
import http from "node:http";

const CDP = "http://127.0.0.1:9223";
function getJson(path) {
  return new Promise((res, rej) => {
    http.get(CDP + path, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => res(JSON.parse(d))); }).on("error", rej);
  });
}
const atobDecode = (b64) => Buffer.from(b64, "base64").toString("utf8");
const list = await getJson("/json/list");
const target = list.find((t) => t.type === "page" && (t.url ?? "").includes("5173")) ?? list.find((t) => t.type === "page");
const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 128 * 1024 * 1024 });
await new Promise((r) => ws.on("open", r));
let mid = 0;
const pending = new Map();
const events = [];
function send(method, params = {}) {
  return new Promise((res, rej) => { const id = ++mid; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
}
ws.on("message", (raw) => {
  const m = JSON.parse(raw.toString());
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); }
  else if (m.method) events.push(m);
});
await send("Runtime.enable");
await send("Page.enable");
await send("Network.enable");
async function evalJs(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  return r.exceptionDetails ? "EXC:" + String(r.exceptionDetails.exception?.description ?? "").slice(0, 200) : r.result?.value;
}

await send("Page.navigate", { url: "http://localhost:5173/" });
await new Promise((r) => setTimeout(r, 9000));
await evalJs("(() => { const ed = document.querySelector('[contenteditable=true]'); if (!ed) return 'NO_EDITOR'; ed.focus(); document.execCommand('selectAll'); document.execCommand('delete'); return 'OK'; })()");
await send("Input.insertText", { text: "诉讼时效一般几年" });
await new Promise((r) => setTimeout(r, 1000));
console.log("CLICK:", await evalJs("(() => { const b = [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim() === '发送'); if (!b) return 'NO_BTN'; b.click(); return 'CLICKED d=' + b.disabled; })()"));
await new Promise((r) => setTimeout(r, 22000));

const recvFrames = events.filter((e) => e.method === "Network.webSocketFrameReceived")
  .map((e) => String(e.params.response?.payloadData ?? ""));
console.log("TOTAL_RECV:", recvFrames.length);
const conv = recvFrames.filter((t) => { try { return atobDecode(t).includes("ses_bridge"); } catch { return false; } });
console.log("CONV_FRAMES:", conv.length);
for (const c of conv.slice(0, 4)) console.log("CONV>>>", c.replace(/[^\x20-\x7e]/g, ".").slice(0, 700));
ws.close();
process.exit(0);
