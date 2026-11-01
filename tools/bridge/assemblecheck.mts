// 官方装配器跑桥帧：真实 accept() 每帧，故障码直出
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { TopicWireFrameAssembler } from "@zcode/shared/zcode-protocol-v4";
import * as proto from "@zcode/shared/zcode-protocol-v4";
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
  type Wire = Record<string, unknown> & { kind?: string; logicalFrameOrdinal?: number; subscriptionId?: string; topic?: string };
  const wires: Wire[] = [];
  const ev = ch.listen<never>("onDynamicConversationFrame", { workspacePath: "D:\mock\lvyin-demo" });
  ev((f: never) => { wires.push(f as never); });
  const sid = "ses_ac_" + randomUUID().slice(0, 6);
  await call("subscribeConversationV4", { topic: `conversation/${sid}`, connectionId: "ac", clientMode: "desktop-continuous" });
  await call("sendConversationCommandV4", { workspacePath: "D:\mock\lvyin-demo", envelope: { commandId: "cmd_ac", clientId: "ac", sessionId: sid, type: "sendText", payload: { text: "装配测试（合成）" }, issuedAt: Date.now() } });
  await new Promise((r) => setTimeout(r, 20000));
  console.log("[ac] wires:", wires.length);
  const asm = new TopicWireFrameAssembler((proto as never as { conversationTopicFrameSchema: { safeParse: (x: unknown) => unknown } }).conversationTopicFrameSchema, {});
  for (const w of wires) {
    try {
      const events = asm.accept(w as never, Date.now());
      for (const e of events as Array<Record<string, unknown>>) {
        console.log("[ac] ord=" + w.logicalFrameOrdinal, JSON.stringify(e).slice(0, 220));
      }
    } catch (err) {
      console.log("[ac] ord=" + w.logicalFrameOrdinal, "THROW=" + String((err as Error).message).slice(0, 150));
    }
  }
  process.exit(0);
});
setTimeout(() => { console.error("AC_TIMEOUT"); process.exit(1); }, 30000);
