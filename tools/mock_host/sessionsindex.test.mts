// 侧栏 sessions-index 帧面自测：模拟 UI 订阅序列
// helloConversationV4 → initializeConversationV4 → onDynamicSessionsIndexFrame(workspace)
// → subscribeSessionsIndexV4(ACK) → 收 initial snapshot 帧；帧用 shared 真 zod schema 验。
// 另验 zcode-task 左表行（fetchTaskListMembershipSets 三分区读取面）。
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient, ProxyChannel } from "@zcode/rpc";
import type { IZCodeAgentService, IZCodeTaskService } from "@zcode/services";
import {
  helloMessageSchema,
  sessionsIndexTopicWireCandidateSchema,
  sessionsIndexTopicFrameSchema,
} from "@zcode/shared/zcode-protocol-v4";

const WORKSPACE = { workspacePath: "D:\\mock\\lvyin-demo" };

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
    const { IZCodeAgentService, IZCodeTaskService } = await import("@zcode/services");
    const agent = ProxyChannel.toService<IZCodeAgentService>(client.getChannel(IZCodeAgentService.channelName));
    const task = ProxyChannel.toService<IZCodeTaskService>(client.getChannel(IZCodeTaskService.channelName));

    // 0) 左表：zcode-task 三分区行
    const [active, pinned, archived, pinnedIds, deleted] = await Promise.all([
      task.listTasks(WORKSPACE),
      task.listPinnedTasks(WORKSPACE),
      task.listArchivedTasks(WORKSPACE),
      task.listPinnedTaskIds(),
      task.listDeletedTaskIds(WORKSPACE),
    ]);
    if (!Array.isArray(active) || active.length !== 3) {
      throw new Error(`listTasks 应返回 3 条合成行，实际 ${JSON.stringify(active)}`);
    }
    console.log("[test] 0) zcode-task 左表 →", active.length, "条：", active.map((t) => t.title).join(" | "));
    console.log("      pinned=", pinned.length, "archived=", archived.length, "pinnedIds=", pinnedIds.length, "deleted=", deleted.length);

    // 1) v4 握手（hello 用真 schema 严验）
    const hello = helloMessageSchema.parse(await agent.helloConversationV4());
    await agent.initializeConversationV4({
      kind: "clientHello", protocolVersion: 3, clientId: "test-client-1",
      clientKind: "desktop", appVersion: "unknown", capabilities: { workspaceHookReviewUi: true },
    });
    console.log("[test] 1) hello 握手 OK: connectionId=", hello.connectionId, "mode=", hello.clientMode);

    // 2) 先挂动态事件监听（UI 的 onFrame 先于 subscribe）
    const frames: unknown[] = [];
    const evt = (agent as unknown as {
      onDynamicSessionsIndexFrame: (arg: unknown) => (l: (f: unknown) => void) => { dispose(): void };
    }).onDynamicSessionsIndexFrame(WORKSPACE);
    const sub = evt((f) => frames.push(f));

    // 3) 订阅拿 ACK
    const result = await agent.subscribeSessionsIndexV4({
      ...WORKSPACE,
      runtimePolicy: "existing-only",
      visibility: "foreground",
    } as never);
    if (!result?.ack?.subscriptionId || result.ack.mode !== "snapshot") {
      throw new Error(`subscribeSessionsIndexV4 ACK 不合法: ${JSON.stringify(result)}`);
    }
    console.log("[test] 3) subscribe ACK →", JSON.stringify(result.ack));

    // 4) 等 initial snapshot 帧（宿主 setTimeout(0) 发出）
    const deadline = Date.now() + 5000;
    while (frames.length === 0 && Date.now() < deadline) await new Promise((r) => setTimeout(r, 50));
    if (frames.length === 0) throw new Error("5s 内未收到 sessions-index 帧");
    sub.dispose();

    const wire = sessionsIndexTopicWireCandidateSchema.parse(frames[0]);
    if (wire.kind !== "complete") throw new Error(`帧应为 complete，实际 ${String(wire.kind)}`);
    const inner = sessionsIndexTopicFrameSchema.parse(wire.frame);
    if (inner.payload.kind !== "snapshot") throw new Error(`内帧应为 snapshot，实际 ${inner.payload.kind}`);
    if (inner.topic !== `sessions-index/${WORKSPACE.workspacePath}`) {
      throw new Error(`topic 不符: ${inner.topic}`);
    }
    const titles = inner.payload.snapshot.sessions.map((s) => s.title);
    if (titles.length !== 3) throw new Error(`snapshot 应含 3 条合成会话，实际 ${titles.length}`);
    console.log("[test] 4) 帧过 zod 严验（wire candidate + inner frame）→", inner.topic, "sessions=", titles.length, "条：");
    for (const s of inner.payload.snapshot.sessions) {
      console.log(`      - ${s.sessionId} [${s.phase}] ${s.title}`);
    }

    console.log("SESSIONSINDEX_PASS");
    process.exit(0);
  } catch (e) {
    console.error("[test] FAIL", e);
    process.exit(1);
  }
});
setTimeout(() => { console.error("[test] timeout"); process.exit(1); }, 15000);
