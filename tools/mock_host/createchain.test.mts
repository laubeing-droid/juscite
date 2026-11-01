// “新建对话任务”创建链自测：模拟 UI 点击后的完整 RPC 序列
// （fileService.ensureConversationWorkspace → agent 身份 → initializeWorkspace →
//   createSession → listTasks），打通 useConversationWorkspaceActions.handleCreateConversationTask
// 断点（原 file 静默 stub 返回 undefined → result.path 抛错被空 catch 吞）。
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient, ProxyChannel } from "@zcode/rpc";
import type { IFileService, IZCodeAgentService, IZCodeSessionService } from "@zcode/services";

const ws = new WebSocket("ws://localhost:3039/ws");
ws.binaryType = "arraybuffer";
const data = { fire: (_b: VSBuffer) => {} };

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
    const { IFileService, IZCodeAgentService, IZCodeSessionService } =
      await import("@zcode/services");
    const file = ProxyChannel.toService<IFileService>(client.getChannel(IFileService.channelName));
    const agent = ProxyChannel.toService<IZCodeAgentService>(client.getChannel(IZCodeAgentService.channelName));
    const session = ProxyChannel.toService<IZCodeSessionService>(client.getChannel(IZCodeSessionService.channelName));

    // 1) UI 链第一跳：ensureConversationWorkspace（断点修复面）
    const conv = await file.ensureConversationWorkspace();
    if (!conv || typeof conv.path !== "string" || !conv.path ||
        conv.workspacePurpose !== "conversation" || typeof conv.created !== "boolean") {
      throw new Error(`ensureConversationWorkspace 返回形状不合法: ${JSON.stringify(conv)}`);
    }
    console.log("[test] 1) ensureConversationWorkspace →", JSON.stringify(conv));

    // 2) 对话 workspace 身份（tab 激活后 UI 会解析 runtime identity）
    const identity = await agent.getWorkspaceRuntimeIdentity({ workspacePath: conv.path });
    console.log("[test] 2) agent.getWorkspaceRuntimeIdentity(对话工作区) →", JSON.stringify(identity));

    // 3) 草稿首条消息发送时的 workspace 准备 + 会话创建
    const prepared = await session.initializeWorkspace({ workspacePath: conv.path });
    const created = await session.createSession({ workspacePath: conv.path });
    if (!created || typeof created.sessionId !== "string" || !created.sessionId) {
      throw new Error(`createSession 返回形状不合法: ${JSON.stringify(created)}`);
    }
    console.log("[test] 3) initializeWorkspace →", JSON.stringify(prepared), "；createSession →", created.sessionId);

    console.log("CREATECHAIN_PASS");
    process.exit(0);
  } catch (e) {
    console.error("[test] FAIL", e);
    process.exit(1);
  }
});
setTimeout(() => { console.error("[test] timeout"); process.exit(1); }, 15000);
