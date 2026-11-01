// 帧合法性诊断：收桥全部帧，逐帧过 UI 同款 schema，打印首个 fail 字段
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { conversationTopicWireCandidateSchema } from "@zcode/shared/zcode-protocol-v4";
import { randomUUID } from "node:crypto";

const ws = new WebSocket("ws://localhost:3030/ws");
ws.binaryType = "arraybuffer";
const data = { fire: (_b: VSBuffer) => {} };
ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
const isocket = {
  onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
  onClose: (_l: () => void) => ({ dispose: () => {} }),
  onEnd: (_l: () => void) => ({ dispose: () => {} }),
  write: (b: VSBuffer) => ws.send(b.buffer),
  end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
};
ws.on("open", async () => {
  const protocol = new SocketProtocol(isocket as never);
  const client = new ChannelClient(protocol);
  const ch = client.getChannel("zcode-agent");
  const call = <T>(m: string, a?: unknown) => ch.call<T>(m, a === undefined ? [] : [a]);
  await call("helloConversationV4");
  type Delta = { op: string; row?: { kind?: string; rowId?: number; turnId?: string; text?: string; state?: string; model?: string }; append?: string; rowId2?: number; path?: string };
  type Frame = { wireVersion?: number; kind?: string; logicalFrameOrdinal?: number; topic?: string; subscriptionId?: string; frame?: { payload?: { kind?: string; snapshot?: unknown; deltas?: Delta[] }; fromSeq?: number; toSeq?: number } };
  const frames: Frame[] = [];
  const ev = ch.listen<never>("onDynamicConversationFrame", { workspacePath: "D:\mock\lvyin-demo" });
  ev((f: never) => { frames.push(f as never); });
  const sid = "ses_fc_" + randomUUID().slice(0, 6);
  await call("subscribeConversationV4", { topic: `conversation/${sid}`, connectionId: "fc", clientMode: "desktop-continuous" });
  await call("sendConversationCommandV4", { workspacePath: "D:\mock\lvyin-demo", envelope: { commandId: "cmd_fc", clientId: "fc", sessionId: sid, type: "sendText", payload: { text: "测试帧（合成）" }, issuedAt: Date.now() } });
  await new Promise((r) => setTimeout(r, 20000));
  console.log("[fc] 收帧数:", frames.length);
  for (const f of frames) {
    const r = (conversationTopicWireCandidateSchema as { safeParse: (x: unknown) => { success: boolean; error?: { issues: Array<{ path: (string|number)[]; message: string }> } } }).safeParse(f);
    if (!r.success) {
      console.log("[fc] FRAME FAIL kind=" + (f.frame?.payload?.kind ?? "?") + " ordinal=" + f.logicalFrameOrdinal);
      for (const i of r.error!.issues.slice(0, 4)) console.log("   ", i.path.join("."), "|", i.message.slice(0, 90));
    } else {
      console.log("[fc] ok kind=" + (f.frame?.payload?.kind ?? "?") + " ordinal=" + f.logicalFrameOrdinal);
    }
  }
  process.exit(0);
});
setTimeout(() => { console.error("FC_TIMEOUT"); process.exit(1); }, 30000);
