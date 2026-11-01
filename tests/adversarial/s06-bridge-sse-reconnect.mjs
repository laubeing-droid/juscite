#!/usr/bin/env node
// S06 合成材料：SSE 断线期间到达的消息，重连后的增量补齐不得丢失。
// 服务端只在带 Last-Event-ID 时重放断线窗；不带则故意不补，用来卡住缺补齐的客户端。
import http from "node:http";

const queued = [
  { id: "1", type: "session.text.delta", created: 1, data: { sessionID: "synth-sse", text: "SYN-A" } },
  { id: "2", type: "session.text.delta", created: 2, data: { sessionID: "synth-sse", text: "SYN-B" } },
  { id: "3", type: "session.text.ended", created: 3, data: { sessionID: "synth-sse", text: "SYN-C" } },
];

const server = http.createServer((req, res) => {
  if (!req.url.startsWith("/api/event")) {
    res.writeHead(404);
    res.end();
    return;
  }
  res.writeHead(200, {
    "content-type": "text/event-stream",
    "cache-control": "no-cache",
    connection: "keep-alive",
  });
  const last = req.headers["last-event-id"];
  const start = last ? queued.findIndex((ev) => ev.id === String(last)) + 1 : 0;
  const batch = last ? queued.slice(Math.max(start, 0)) : queued.slice(0, 1);
  for (const ev of batch) res.write(`data: ${JSON.stringify(ev)}\n\n`);
  req.on("close", () => {});
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const { port } = server.address();
process.env.BRIDGE_OC28_URL = `http://127.0.0.1:${port}`;
process.env.BRIDGE_OC28_PASSWORD = "synthetic-not-a-secret";

const { openEventStream } = await import("../../packages/juscite-runtime-adapters/opencode/src/opencodeAdapter.mjs");

const seen = [];
let stream;
const done = new Promise((resolve) => {
  stream = openEventStream({
    onEvent: (evt) => {
      if (evt?.id) seen.push(String(evt.id));
      if (seen.length === 1) stream.drop();
      if (seen.includes("2") && seen.includes("3")) resolve("caught-up");
    },
  });
});

let outcome = "timeout";
try {
  outcome = await Promise.race([
    done,
    new Promise((resolve) => setTimeout(() => resolve("timeout"), 4000)),
  ]);
} finally {
  try { stream?.close(); } catch { /* already closed */ }
  await new Promise((resolve) => server.close(resolve));
}

const unique = [...new Set(seen)];
const ok = outcome === "caught-up" && unique.includes("1") && unique.includes("2") && unique.includes("3");
if (!ok) {
  console.error(`[S06] FAIL catch-up outcome=${outcome} seen=${unique.join(",")}`);
  console.log("RESULT fail");
  process.exit(1);
}
console.log(`[S06] OK reconnect delivered ${unique.join(",")}`);
console.log("RESULT pass");
