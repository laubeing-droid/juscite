// 最小 CDP 客户端：律引 UI 动态取证（调试 Chrome 9223）
// 用法: node cdp_probe.mjs <mode> [arg]
//   eval <js> | keys <text> | console <secs> | shot | wslist [secs]
import WebSocket from "ws";
import http from "node:http";
import fs from "node:fs";

const CDP = process.env.CDP_PORT ? "http://127.0.0.1:" + process.env.CDP_PORT : "http://127.0.0.1:9223";
const mode = process.argv[2];
const arg = process.argv[3];

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
  if (r.exceptionDetails) return "EXC: " + JSON.stringify(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text).slice(0, 800);
  return r.result?.value;
}

if (mode === "eval") {
  console.log(String(await evalJs(arg)));
} else if (mode === "keys") {
  await send("Input.insertText", { text: arg });
  console.log("KEYS_OK");
} else if (mode === "console") {
  await new Promise((r) => setTimeout(r, Number(arg) * 1000));
  const logs = events.filter((e) => e.method === "Runtime.consoleAPICalled" || e.method === "Runtime.exceptionThrown")
    .map((e) => e.method === "Runtime.consoleAPICalled"
      ? `[${e.params.type}] ` + (e.params.args ?? []).map((a) => a.value ?? a.description ?? "").join(" ").slice(0, 400)
      : "[EXC] " + JSON.stringify(e.params.exceptionDetails?.exception?.description ?? e.params.exceptionDetails?.text).slice(0, 400));
  console.log(logs.length ? logs.join("\n") : "NO_CONSOLE_EVENTS");
} else if (mode === "shot") {
  const r = await send("Page.captureScreenshot", { format: "png" });
  const p = process.env.TEMP + "\\cdp_shot.png";
  fs.writeFileSync(p, Buffer.from(r.data, "base64"));
  console.log("SHOT_OK", p);
} else if (mode === "wslist") {
  await send("Network.enable");
  await new Promise((r) => setTimeout(r, Number(arg ?? 3) * 1000));
  const created = events.filter((e) => e.method === "Network.webSocketCreated").map((e) => e.params.url);
  console.log("WS_CREATED(" + created.length + "):");
  console.log(created.join("\n") || "NONE");
}
ws.close();
process.exit(0);
