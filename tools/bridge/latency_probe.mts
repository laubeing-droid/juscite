// 首字延迟对比探针（任务二验收②）：向桥发一句合成消息，记录 sendText ack → 首个文本增量
// row.delta 的毫秒值。桥首字来源由 BRIDGE_OC28_SSE 决定（1=SSE 唤醒对账，0=纯 700ms 轮询），
// A/B 各起一个隔离实例（BRIDGE_PORT + BRIDGE_WS_URL 指向对应端口）即可复现对比。
// 用法（仓库根）：node --import tsx tools/bridge/latency_probe.mts <label>
// 末行输出 LATENCY_JSON {"label","ackToFirstDeltaMs","totalMs","replyLen"}。
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { randomUUID } from "node:crypto";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const WS_URL = process.env.BRIDGE_WS_URL ?? "ws://127.0.0.1:3030/ws";
const WORKSPACE = "D:\\mock\\lvyin-demo";
type Delta = { op: string; row?: { rowId?: number; kind?: string; state?: string }; append?: string; path?: string };
type Frame = { frame?: { payload?: { kind?: string; deltas?: Delta[] } }; payload?: { kind?: string; deltas?: Delta[] } };

function connect(): Promise<{ call: (m: string, a?: unknown) => Promise<never>; frames: Frame[]; close: () => void }> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(WS_URL);
    ws.binaryType = "arraybuffer";
    const frames: Frame[] = [];
    const data = { fire: (_b: VSBuffer) => {} };
    ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
    ws.on("error", (e: unknown) => reject(e));
    ws.on("open", () => {
      const isocket = {
        onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
        onClose: () => ({ dispose: () => {} }),
        onEnd: () => ({ dispose: () => {} }),
        write: (b: VSBuffer) => ws.send(b.buffer),
        end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
      };
      const client = new ChannelClient(new SocketProtocol(isocket as never));
      const ch = client.getChannel("zcode-agent");
      const call = (m: string, a?: unknown) => ch.call<never>(m, a === undefined ? [] : [a]);
      ch.listen<never>("onDynamicConversationFrame", { workspacePath: WORKSPACE })((f: { topic: string }) => {
        if (f.topic.startsWith("conversation/")) frames.push(f as Frame);
      });
      resolve({ call, frames, close: () => { try { ws.close(); } catch { /* 已断 */ } } });
    });
  });
}

const label = process.argv[2] ?? "run";
const { call, frames, close } = await connect();
await call("helloConversationV4");
const sessionId = "ses_lat_" + randomUUID().slice(0, 6);
await call("subscribeConversationV4", { topic: `conversation/${sessionId}`, workspacePath: WORKSPACE, historyFirst: true });
await call("sendConversationCommandV4", { workspacePath: WORKSPACE, envelope: {
  commandId: "cmd_create_" + randomUUID(), clientId: "latency-probe", sessionId: null,
  type: "createSession", payload: { sessionId, workspaceId: WORKSPACE }, issuedAt: Date.now(),
} });
await call("sendConversationCommandV4", { workspacePath: WORKSPACE, envelope: {
  commandId: "cmd_lat_" + randomUUID().slice(0, 8), clientId: "latency-probe", sessionId, type: "sendText",
  payload: { text: "首字延迟对比探针（合成材料），请用一两句话介绍民事诉讼时效。" }, issuedAt: Date.now() },
});
const ackAt = Date.now(); // sendText 返回（ack accepted）即计时零点
let firstDeltaMs: number | null = null;
let completeText = "";
const deadline = Date.now() + 120000;
while (Date.now() < deadline) {
  await sleep(60);
  const deltas = frames.flatMap((f) => f.frame?.payload?.deltas ?? f.payload?.deltas ?? []);
  const textDelta = deltas.find((d) => d.op === "row.delta" && d.path === "text" && (d.append ?? "").length > 0);
  if (textDelta && firstDeltaMs === null) firstDeltaMs = Date.now() - ackAt;
  const done = deltas.find((d) => d.op === "row.upserted" && d.row?.state === "complete");
  if (done) { completeText = (done as never as { row?: { text?: string } }).row?.text ?? ""; break; }
}
console.log(`[latency] label=${label} ackToFirstDeltaMs=${firstDeltaMs} replyLen=${completeText.length}`);
console.log("LATENCY_JSON " + JSON.stringify({ label, ackToFirstDeltaMs: firstDeltaMs, totalMs: Date.now() - ackAt, replyLen: completeText.length }));
close();
setTimeout(() => process.exit(firstDeltaMs === null ? 1 : 0), 150); // 等 WS close 收尾再退，避免悬挂句柄报错
