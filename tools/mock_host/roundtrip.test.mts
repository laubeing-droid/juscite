// mock Host 往返自测：ChannelClient → setting.get / zcodeAgent.listSessions（合成数据）
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient, ProxyChannel } from "@zcode/rpc";
import type { ISettingService } from "@zcode/services";
import type { IZCodeAgentService } from "@zcode/services";

const ws = new WebSocket("ws://localhost:3039/ws");
ws.binaryType = "arraybuffer";
const data = { fire: (_b: VSBuffer) => {} };

ws.on("open", () => console.log("[test] ws open"));
ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
ws.on("error", (e: unknown) => { console.error("[test] ws error", e); process.exit(1); });

const isocket = {
  onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
  onClose: (_l: () => void) => ({ dispose: () => {} }),
  onEnd: (_l: () => void) => ({ dispose: () => {} }),
  write: (b: VSBuffer) => ws.send(b.buffer),
  end: () => ws.close(),
  drain: async () => {},
  dispose: () => ws.close(),
};

ws.on("open", async () => {
  try {
    const protocol = new SocketProtocol(isocket as never);
    const client = new ChannelClient(protocol);
    // channel 名在运行时从 descriptor 常量拿（与 mock 端注册同源）
    const { ISettingService, IZCodeAgentService } = await import("@zcode/services");
    const setting = ProxyChannel.toService<ISettingService>(client.getChannel(ISettingService.channelName));
    const agent = ProxyChannel.toService<IZCodeAgentService>(client.getChannel(IZCodeAgentService.channelName));
    const s = await setting.get();
    const sessions = await agent.listSessions({} as never);
    console.log("[test] setting.get →", JSON.stringify(s).slice(0, 120));
    console.log("[test] listSessions →", sessions.length, "条：", sessions.map((x) => x.title).join(" | "));
    console.log("ROUNDTRIP_PASS");
    process.exit(0);
  } catch (e) {
    console.error("[test] FAIL", e);
    process.exit(1);
  }
});
setTimeout(() => { console.error("[test] timeout"); process.exit(1); }, 15000);
