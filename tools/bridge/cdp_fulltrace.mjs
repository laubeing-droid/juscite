// 全链追踪：预注入 ws 接收钩子 → 刷新 → 打字 → 点击 → 抓 UI v4 日志 + 下行帧 + 页面态
import WebSocket from "ws";
import http from "node:http";
import fs from "node:fs";

const CDP = "http://127.0.0.1:9223";

function getJson(path) {
  return new Promise((res, rej) => {
    http.get(CDP + path, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => res(JSON.parse(d))); }).on("error", rej);
  });
}
const list = await getJson("/json/list");
let target = list.find((t) => t.type === "page" && (t.url || "").includes("5173")) ?? list.find((t) => t.type === "page");
if (!target) { console.log("NO_PAGE"); process.exit(1); }
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
async function evalJs(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  return r.exceptionDetails ? "EXC:" + String(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text).slice(0, 300) : r.result?.value;
}

const hook = `
window.__rxlog = [];
(function(){
  const OrigWS = window.WebSocket;
  const Wrapped = function(url, protos){ const ws = protos ? new OrigWS(url, protos) : new OrigWS(url);
    ws.addEventListener('message', (ev) => { try {
      let s = '';
      if (typeof ev.data === 'string') s = ev.data;
      else if (ev.data instanceof ArrayBuffer) { const a = new Uint8Array(ev.data); for (let i=0;i<Math.min(a.length,4000);i++) s += String.fromCharCode(a[i]); }
      if (s && (s.includes('conversation') || s.includes('snapshot') || s.includes('delta') || s.includes('frame'))) {
        window.__rxlog.push(Date.now() + ' RX ' + s.replace(/[^\\x20-\\x7e]/g, '.').slice(0, 2500));
      }
    } catch(e){} });
    return ws; };
  Wrapped.prototype = OrigWS.prototype;
  window.WebSocket = Wrapped;
})();
`;
await send("Page.addScriptToEvaluateOnNewDocument", { source: hook });
await send("Page.navigate", { url: "http://localhost:5173/" });
await new Promise((r) => setTimeout(r, 9000));
console.log("HOOK_FRAMES:", await evalJs("window.__rxlog ? window.__rxlog.length : -1"));

await evalJs("(() => { const ed = document.querySelector('[contenteditable=true]'); if (!ed) return 'NO_EDITOR'; ed.focus(); document.execCommand('selectAll'); document.execCommand('delete'); return 'OK'; })()");
await send("Input.insertText", { text: "诉讼时效期间一般几年" });
await new Promise((r) => setTimeout(r, 1200));
console.log("CLICK:", await evalJs("(() => { const b = [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim() === '发送'); if (!b) return 'NO_BTN'; b.click(); return 'CLICKED d=' + b.disabled; })()"));
await new Promise((r) => setTimeout(r, 30000));

const v4logs = events.filter((e) => e.method === "Runtime.consoleAPICalled")
  .map((e) => (e.params.args ?? []).map((a) => a.value ?? a.description ?? "").join(" "))
  .filter((t) => /v4|conv|frame|订阅|投影|recovery|silent|subscription/.test(t));
console.log("===UI_V4_LOGS===");
console.log(v4logs.length ? v4logs.join("\n").slice(0, 3500) : "NONE");
console.log("===RX_COUNT===", await evalJs("window.__rxlog ? window.__rxlog.length : -1"));
const rx = await evalJs("(window.__rxlog ?? []).slice(0, 8).join('\n----\n')");
console.log("===RX_FRAMES===");
console.log(String(rx).slice(0, 6000));
console.log("===BODY===", String(await evalJs("document.body.innerText.replace(/\\s+/g,' ').slice(0,400)")));
ws.close();
process.exit(0);
