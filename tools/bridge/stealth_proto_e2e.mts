// UI-3 隐身协议层 E2E：经桥 setting 开隐身 → sendText 收失败行 → 关隐身 → sendText 恢复真回复。
// 路径与 M2 conversation.e2e.mts 同源（hello→subscribe→sendText→帧流断言）。
import { randomUUID } from "node:crypto";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";

const ws = new WebSocket("ws://localhost:3030/ws");
ws.binaryType = "arraybuffer";
const data = { fire: () => {} };
ws.on("message", (buf) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
ws.on("error", (e) => { console.error("WS_ERR", e); process.exit(1); });
const isocket = {
  onData: (l) => { data.fire = l; return { dispose: () => {} }; },
  onClose: () => ({ dispose: () => {} }),
  onEnd: () => ({ dispose: () => {} }),
  write: (b) => ws.send(b.buffer),
  end: () => ws.close(),
  drain: async () => {},
  dispose: () => ws.close(),
};

ws.on("open", async () => {
  try {
    const protocol = new SocketProtocol(isocket);
    const client = new ChannelClient(protocol);
    const agent = client.getChannel("zcode-agent");
    const setting = client.getChannel("setting");
    const call = (ch, m, a) => ch.call(m, a === undefined ? [] : [a]);

    const frames = [];
    const convEvent = agent.listen("onDynamicConversationFrame", { workspacePath: "D:\mock\lvyin-demo" });
    convEvent((f) => frames.push(f));

    const hello = await call(agent, "helloConversationV4");
    console.log("[stealth-e2e] hello protocolVersion:", hello.protocolVersion);

    const deltasOf = (f) => f.frame?.payload?.deltas ?? f.payload?.deltas ?? [];
    const runTurn = async (label, text) => {
      const sessionId = "ses_stealth_" + randomUUID().slice(0, 6);
      frames.length = 0;
      const sub = await call(agent, "subscribeConversationV4", { topic: "conversation/" + sessionId, connectionId: "stealth-e2e", clientMode: "desktop-continuous" });
      await new Promise((r) => setTimeout(r, 200));
      const ack = await call(agent, "sendConversationCommandV4", {
        workspacePath: "D:\mock\lvyin-demo",
        envelope: {
          commandId: "cmd_" + randomUUID().slice(0, 8), clientId: "stealth-e2e", sessionId,
          type: "sendText", payload: { text }, issuedAt: Date.now(),
        },
      });
      console.log("[" + label + "] ack:", ack.status, "sub:", sub.ack.subscriptionId);
      const deadline = Date.now() + 150000;
      let failedRow = null, completeRow = null;
      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 800));
        for (const f of frames) for (const d of deltasOf(f)) {
          if (d.op === "row.appended" && d.row?.state === "failed") failedRow = d.row;
          if (d.op === "row.upserted" && d.row?.state === "complete") completeRow = d.row;
        }
        if (failedRow) break;
        if (completeRow) break;
      }
      return { failedRow, completeRow };
    };

    // 阶段1：开隐身（经桥 setting，与 UI 开关同字段同文件）→ sendText → 期待失败行
    await call(setting, "update", { stealthMode: { enabled: true } });
    const on = await call(setting, "get");
    console.log("[stealth-e2e] stealth enabled:", on.stealthMode?.enabled);
    const r1 = await runTurn("blocked", "隐身协议E2E阻断消息（合成）：请回答 1+1=？");
    const blockedOk = !!r1.failedRow && (r1.failedRow.text || "").includes("隐身模式已开启：出站通道全断") && !r1.completeRow;
    console.log("[blocked] failedRow:", JSON.stringify(r1.failedRow && { state: r1.failedRow.state, model: r1.failedRow.model, text: (r1.failedRow.text || "").slice(0, 60) }));
    console.log("[blocked] completeRow:", r1.completeRow ? "PRESENT(BAD)" : "absent(good)");

    // 阶段2：关隐身 → sendText → 期待真回复
    await call(setting, "update", { stealthMode: { enabled: false } });
    const off = await call(setting, "get");
    console.log("[stealth-e2e] stealth enabled:", off.stealthMode?.enabled);
    const r2 = await runTurn("restored", "隐身协议E2E恢复消息（合成）：请只回答民事诉讼一般时效几年");
    const restoredOk = !!r2.completeRow && (r2.completeRow.text || "").length > 5 && !r2.failedRow;
    console.log("[restored] completeRow text:", (r2.completeRow?.text || "").slice(0, 80));
    console.log("[restored] failedRow:", r2.failedRow ? "PRESENT(BAD)" : "absent(good)");

    console.log(blockedOk && restoredOk ? "UI3_STEALTH_PROTO_PASS" : "UI3_STEALTH_PROTO_FAIL");
    process.exit(blockedOk && restoredOk ? 0 : 1);
  } catch (e) {
    console.error("E2E_ERROR", e);
    process.exit(1);
  }
});
