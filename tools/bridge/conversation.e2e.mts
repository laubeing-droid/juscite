// M2 桥对话流 e2e：hello→subscribe→sendText→收帧→真模型回复完整。
// 波1 §六.A 协议对齐自测段：hello capabilities 白名单 / 新可选键容忍 / runtimeInitialization
// 产出 / sessions-index lastOutcome + reconcile（findings.md §六.A 六条，合成数据）。
// 期望末行 E2E_PASS（exit 0）。可独立执行（桥需已在 :3030 运行）。
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { randomUUID } from "node:crypto";
import {
  conversationTopicWireCandidateSchema, sessionsIndexTopicWireCandidateSchema,
  commandsQueryResultSchema, TopicWireFrameAssembler, conversationTopicFrameSchema,
} from "@zcode/shared/zcode-protocol-v4";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const ws = new WebSocket("ws://localhost:3030/ws");
ws.binaryType = "arraybuffer";
const data = { fire: (_b: VSBuffer) => {} };
ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
ws.on("error", (e: unknown) => { console.error("WS_ERR", e); process.exit(1); });

const isocket = {
  onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
  onClose: (_l: () => void) => ({ dispose: () => {} }),
  onEnd: (_l: () => void) => ({ dispose: () => {} }),
  write: (b: VSBuffer) => ws.send(b.buffer),
  end: () => ws.close(),
  drain: async () => {},
  dispose: () => ws.close(),
};

// §六.A#3：host capabilities 只允许声明 hostCapabilitiesSchema（aac4755 transport.ts:23）认识的键
const KNOWN_HOST_CAP_KEYS = new Set([
  "nativeDialogs", "localTerminal", "binaryFrames", "compression",
  "workspaceHookReview", "independentPlanState", "workflowRunDeltas",
]);

ws.on("open", async () => {
  try {
    const protocol = new SocketProtocol(isocket as never);
    const client = new ChannelClient(protocol);
    const ch = client.getChannel("zcode-agent");
    const call = <T>(m: string, a?: unknown) => ch.call<T>(m, a === undefined ? [] : [a]); // wire 上 args 是数组（fromService 端 .apply(handler, args)）

    const checks: Record<string, boolean> = {};

    // ── §六.A#3：hello capabilities 只声明已支持键 ──
    const hello = await call<{ protocolVersion: number; capabilities: Record<string, unknown> }>("helloConversationV4");
    console.log("[e2e] hello protocolVersion:", hello.protocolVersion);
    const capKeys = Object.keys(hello.capabilities ?? {});
    checks.capDeclaredOnly = capKeys.length > 0 && capKeys.every((k) => KNOWN_HOST_CAP_KEYS.has(k));
    console.log("[e2e] host capabilities keys:", capKeys.join(","), checks.capDeclaredOnly ? "OK(declared-only)" : "FAIL(unknown key)");

    // 帧监听（原生 channel.listen：动态事件带 arg）
    type Row = { rowId?: number; kind?: string; text?: string; state?: string; sourceCommandId?: string };
    type Delta = { op: string; row?: Row; append?: string; rowId?: number; path?: string };
    type Snapshot = { runtimeInitialization?: { status: string; attemptId: string }; seq?: number; rows?: { window: Row[] }; control?: { phase: string } };
    type Frame = { subscriptionId?: string; deliveryKind?: string; frame?: { fromSeq?: number; toSeq?: number; payload?: { kind?: string; snapshot?: Snapshot; deltas?: Delta[] } }; payload?: { kind?: string; snapshot?: Snapshot; deltas?: Delta[] } };
    type SidxSnapshot = { sessions?: Array<{ sessionId: string; phase?: string; lastOutcome?: string }> };
    type SidxFrame = { subscriptionId?: string; deliveryKind?: string; frame?: { fromSeq?: number; toSeq?: number; payload?: { kind?: string; snapshot?: SidxSnapshot; deltas?: Array<{ op: string; session?: { sessionId: string } }> } }; payload?: { kind?: string; snapshot?: SidxSnapshot } };
    const sessionId = "ses_e2e_" + randomUUID().slice(0, 6);
    const frames: Frame[] = [];
    const convEvent = ch.listen<never>("onDynamicConversationFrame", { workspacePath: "D:\\mock\\lvyin-demo" });
    convEvent((f: { topic: string }) => { if (f.topic === `conversation/${sessionId}`) frames.push(f as Frame); });
    const sidxFrames: SidxFrame[] = [];
    const sidxEvent = ch.listen<never>("onDynamicSessionsIndexFrame", { workspacePath: "D:\\mock\\lvyin-demo" });
    sidxEvent((f) => { sidxFrames.push(f); });

    // ── §六.A#2：subscribe 带新可选键（historyFirst/additionalDirectories）+ 未知未来键 → 不拒帧 ──
    const sub = await call<{ ack: { subscriptionId: string } }>("subscribeConversationV4", {
      topic: `conversation/${sessionId}`, connectionId: "e2e-conn", clientMode: "desktop-continuous",
      historyFirst: true, additionalDirectories: ["D:\\mock\\extra-dir"],
      e2eUnknownFutureKey: { nested: true },
    });
    checks.subscribeTolerant = !!sub.ack.subscriptionId;
    console.log("[e2e] subscribed(new-keys):", sub.ack.subscriptionId, checks.subscribeTolerant ? "OK" : "FAIL");
    await sleep(300);
    const snapFrame = frames.find((f) => (f.frame?.payload?.kind ?? f.payload?.kind) === "snapshot");
    console.log("[e2e] initial snapshot frame:", snapFrame ? "RECEIVED" : "none(yet)");
    // ── §六.A#1：snapshot 顶层产出 runtimeInitialization（桥态恒 ready+attemptId） ──
    const snap = snapFrame?.frame?.payload?.snapshot ?? snapFrame?.payload?.snapshot;
    checks.runtimeInit = snap?.runtimeInitialization?.status === "ready" && !!snap?.runtimeInitialization?.attemptId;
    console.log("[e2e] snapshot.runtimeInitialization:", JSON.stringify(snap?.runtimeInitialization), checks.runtimeInit ? "OK" : "FAIL");

    // ── §六.A#2：resync 带 retryInitialization（不匹配 attempt→剥键照常）+ 未知键 → 不拒帧 ──
    const framesBefore = frames.length;
    const rs = await call<{ ack: { subscriptionId: string } }>("resyncConversationV4", {
      subscriptionId: sub.ack.subscriptionId, retryInitialization: "stale-attempt-id",
      forceSnapshot: true, e2eUnknownKey: 1,
    });
    await sleep(300);
    checks.resyncTolerant = !!rs.ack.subscriptionId && frames.length > framesBefore;
    console.log("[e2e] resync(new-keys) ack:", rs.ack.subscriptionId, "frames:", framesBefore, "->", frames.length, checks.resyncTolerant ? "OK" : "FAIL");

    // ── §六.A#6：sessions-index lastOutcome + reconcile 兜底（snapshot 缺席≠删除） ──
    const ssub = await call<{ ack: { subscriptionId: string } }>("subscribeSessionsIndexV4", {
      workspacePath: "D:\\mock\\lvyin-demo", historyFirst: true, e2eUnknownKey: "x",
    });
    checks.sidxSubscribe = !!ssub.ack.subscriptionId;
    await sleep(300);
    const sidxSnap = sidxFrames.find((f) => (f.frame?.payload?.kind ?? f.payload?.kind) === "snapshot");
    const sessions = sidxSnap?.frame?.payload?.snapshot?.sessions ?? sidxSnap?.payload?.snapshot?.sessions;
    const completed = sessions?.find((s) => s.sessionId === "ses_mock_0001");
    const running = sessions?.find((s) => s.sessionId === "ses_mock_0002");
    checks.lastOutcome = completed?.lastOutcome === "completed" && running !== undefined && running.lastOutcome === undefined;
    console.log("[e2e] sessions-index lastOutcome:", JSON.stringify({ completed: completed?.lastOutcome, runningAbsent: running?.lastOutcome === undefined }), checks.lastOutcome ? "OK" : "FAIL");
    const rec = await call<{ sessions: Array<{ sessionId: string; exists: boolean; deleted?: boolean; lastOutcome?: string }> }>("reconcileSessionsIndexV4", {
      workspaceId: "D:\\mock\\lvyin-demo", sessionIds: ["ses_mock_0001", "ses_not_persisted"],
    });
    const r0 = rec.sessions?.find((s) => s.sessionId === "ses_mock_0001");
    const r1 = rec.sessions?.find((s) => s.sessionId === "ses_not_persisted");
    checks.reconcile = r0?.exists === true && r0?.lastOutcome === "completed" && r1?.exists === false && r1?.deleted === false;
    console.log("[e2e] reconcile:", JSON.stringify(rec.sessions), checks.reconcile ? "OK" : "FAIL");

    // M4：预热会话必须有 live 摘要，但首发前不能伪造项目目录任务。
    const workspacePath = "D:\\mock\\lvyin-demo";
    const createEnvelope = { commandId: "cmd_create_" + randomUUID(), clientId: "e2e-client", sessionId: null,
      type: "createSession", payload: { sessionId, workspaceId: workspacePath }, issuedAt: Date.now() };
    const created = await call<{ result: { sessionId: string } }>("sendConversationCommandV4", {
      workspacePath, projectId: "lvyin-demo", envelope: createEnvelope,
    });
    const replayed = await call("sendConversationCommandV4", { workspacePath, projectId: "lvyin-demo", envelope: createEnvelope });
    checks.createReplay = created.result.sessionId === sessionId && JSON.stringify(created) === JSON.stringify(replayed);
    const project = client.getChannel("project");
    type Tree = { tasks: Array<{ taskId: string; workspacePath: string; projectId: string | null }> };
    const beforeSend = await project.call<Tree>("readTree", []);
    checks.draftHidden = !beforeSend.tasks.some((task) => task.taskId === sessionId);
    const commandId = "cmd_e2e_" + randomUUID().slice(0, 8);

    // ── §六.A#4（ready 放行）：门禁在桥态 ready 时不拦 sendText，走真模型往返 ──
    const ack = await call<{ status: string }>("sendConversationCommandV4", {
      workspacePath: "D:\\mock\\lvyin-demo",
      envelope: {
        commandId,
        clientId: "e2e-client",
        sessionId,
        type: "sendText",
        payload: { text: "合成端到端测试，请只回复：合成测试第一轮完成。" },
        issuedAt: Date.now(),
      },
    });
    checks.commandAccepted = ack.status === "accepted";
    console.log("[e2e] command ack:", ack.status, checks.commandAccepted ? "OK" : "FAIL");
    const afterSend = await project.call<Tree>("readTree", []);
    checks.taskMaterialized = afterSend.tasks.some((task) => task.taskId === sessionId && task.workspacePath === workspacePath && task.projectId === "lvyin-demo");
    const queried = commandsQueryResultSchema.parse(await call("queryConversationCommandsV4", {
      workspacePath, commands: [{ sessionId, commandId }, { sessionId, commandId: "never-accepted" }],
    }));
    checks.receiptQuery = queried.results[0]?.result !== "unknown" && queried.results[1]?.result === "unknown";
    const groups = client.getChannel("task-groups");
    const taskRef = { hostId: "local", workspacePath, taskId: sessionId };
    await groups.call("admit", [{ tasks: [taskRef], placement: { task: taskRef, groupId: null, creationId: commandId } }]);
    const groupState = await groups.call<{ order: Array<{ type: string; key: string }> }>("read", []);
    checks.groupAdmission = groupState.order.some((node) => node.type === "task" && node.key === JSON.stringify([workspacePath, sessionId]));

    // 收帧直到 assistant complete 或超时
    const deadline = Date.now() + 150000;
    let reply = "";
    let consumed = 0;
    while (Date.now() < deadline) {
      await sleep(1000);
      for (const f of frames.slice(consumed)) {
        for (const d of f.frame?.payload?.deltas ?? f.payload?.deltas ?? []) {
          if (d.op === "row.delta") reply += d.append ?? "";
          if (d.op === "row.upserted" && d.row?.state === "complete") reply = d.row.text ?? reply;
        }
      }
      consumed = frames.length;
      const done = frames.some((f) => (f.frame?.payload?.deltas ?? f.payload?.deltas ?? []).some((d) => d.op === "row.upserted" && d.row?.state === "complete"));
      if (done && reply) break;
    }
    console.log("[e2e] reply:", reply.slice(0, 160));
    checks.acceptedProjection = frames.some((f) => f.frame?.payload?.deltas?.some((d) => d.row?.sourceCommandId === commandId));
    checks.liveIndex = sidxFrames.some((f) => f.subscriptionId === ssub.ack.subscriptionId && f.frame?.payload?.deltas?.some((d) => d.session?.sessionId === sessionId));

    // 同一会话第二轮不能重复第一轮文本。
    const secondStart = frames.length;
    const secondCommandId = "cmd_second_" + randomUUID();
    await call("sendConversationCommandV4", { workspacePath, envelope: {
      commandId: secondCommandId, clientId: "e2e-client", sessionId, type: "sendText",
      payload: { text: "第二轮合成测试，请只回复：合成测试第二轮完成。不要重复上一轮文字。" }, issuedAt: Date.now(),
    } });
    let secondReply = "";
    const secondDeadline = Date.now() + 150000;
    while (Date.now() < secondDeadline) {
      await sleep(500);
      const completedRow = frames.slice(secondStart).flatMap((f) => f.frame?.payload?.deltas ?? [])
        .find((d) => d.op === "row.upserted" && d.row?.state === "complete");
      if (completedRow) { secondReply = completedRow.row?.text ?? ""; break; }
    }
    checks.separateTurns = secondReply.includes("第二轮") && !secondReply.includes(reply);
    console.log("[e2e] second reply:", secondReply.slice(0, 160));

    const beforeRecovery = frames.length;
    await call("resyncConversationV4", { workspacePath, subscriptionId: sub.ack.subscriptionId, forceSnapshot: true });
    await sleep(300);
    const recovered = frames.slice(beforeRecovery).find((f) => f.deliveryKind === "recovery");
    const recoveredSnapshot = recovered?.frame?.payload?.snapshot;
    const rows = recoveredSnapshot?.rows?.window ?? [];
    // 功能#27 起：每轮含 turnHeader 边界行（分享预检的 product turn 权威），两轮=6 行
    // （2×(turnHeader+userInput+assistantText)）。
    checks.recoveryRows = rows.length === 6 && rows.filter((r) => r.kind === "turnHeader").length === 2
      && rows.filter((r) => r.kind === "assistantText").every((r) => r.state === "complete")
      && rows.some((r) => r.text === reply) && rows.some((r) => r.text === secondReply)
      && recoveredSnapshot?.seq === recovered?.frame?.toSeq && recoveredSnapshot?.control?.phase === "completedSuccess";
    const coldStart = frames.length;
    const cold = await call<{ ack: { subscriptionId: string } }>("subscribeConversationV4", { topic: `conversation/${sessionId}`, workspacePath });
    await sleep(300);
    const coldFrames = frames.slice(coldStart);
    checks.coldSnapshot = coldFrames.length === 1 && coldFrames[0]?.subscriptionId === cold.ack.subscriptionId
      && coldFrames[0]?.deliveryKind === "initial" && coldFrames[0]?.frame?.payload?.snapshot?.rows?.window.length === 6;

    const indexRecoveryStart = sidxFrames.length;
    await call("resyncSessionsIndexV4", { workspacePath, subscriptionId: ssub.ack.subscriptionId, forceSnapshot: true });
    await sleep(300);
    checks.indexRecovery = sidxFrames.slice(indexRecoveryStart).some((f) => f.subscriptionId === ssub.ack.subscriptionId
      && f.deliveryKind === "recovery" && f.frame?.payload?.snapshot?.sessions?.some((s) => s.sessionId === sessionId && s.lastOutcome === "completed"));
    await call("unsubscribeSessionsIndexV4", { workspacePath, subscriptionId: ssub.ack.subscriptionId });
    const indexStop = sidxFrames.filter((f) => f.subscriptionId === ssub.ack.subscriptionId).length;
    await call("sendConversationCommandV4", { workspacePath, envelope: { ...createEnvelope, commandId: "cmd_other_" + randomUUID(), payload: { workspaceId: workspacePath } } });
    await sleep(300);
    checks.indexUnsubscribe = sidxFrames.filter((f) => f.subscriptionId === ssub.ack.subscriptionId).length === indexStop;

    // ── 任务二：SSE 断线重连不丢增量——第三轮发出后立即注入桥侧 SSE 断线（自动重连），
    // turn 必须仍收敛到完整回复（回落轮询/重连对账兜底），文本不截断不串轮（RE-B2 §5 对拍 6）。
    const thirdCommandId = "cmd_third_" + randomUUID();
    await call("sendConversationCommandV4", { workspacePath, envelope: {
      commandId: thirdCommandId, clientId: "e2e-client", sessionId, type: "sendText",
      payload: { text: "SSE 断线重连合成测试，请只回复：SSE第三轮完成。" }, issuedAt: Date.now(),
    } });
    await fetch("http://localhost:3030/api/dev/sse-drop").then((r) => r.json()).catch(() => null);
    let thirdReply = "";
    const thirdStart = frames.length;
    const thirdDeadline = Date.now() + 150000;
    while (Date.now() < thirdDeadline) {
      await sleep(500);
      const completedRow = frames.slice(thirdStart).flatMap((f) => f.frame?.payload?.deltas ?? [])
        .find((d) => d.op === "row.upserted" && d.row?.state === "complete");
      if (completedRow) { thirdReply = completedRow.row?.text ?? ""; break; }
    }
    checks.sseDropRecovery = thirdReply.includes("第三轮") && !thirdReply.includes("第二轮") && !thirdReply.includes("第一轮");
    console.log("[e2e] third reply (after sse drop):", thirdReply.slice(0, 120));

    checks.frameSchemas = frames.every((f) => conversationTopicWireCandidateSchema.safeParse(f).success)
      && sidxFrames.every((f) => sessionsIndexTopicWireCandidateSchema.safeParse(f).success);
    const assembler = new TopicWireFrameAssembler(conversationTopicFrameSchema);
    checks.assembly = frames.every((f) => {
      const wire = conversationTopicWireCandidateSchema.parse(f);
      return assembler.accept(wire, Date.now()).every((event) => event.kind !== "fault");
    });
    for (const [name, passed] of Object.entries(checks)) console.log(`[e2e] ${name}: ${passed ? "OK" : "FAIL"}`);
    const failed = Object.entries(checks).filter(([, v]) => !v).map(([k]) => k);
    if (failed.length) console.log("[e2e] FAILED CHECKS:", failed.join(","));
    const pass = reply.length > 5 && failed.length === 0;
    console.log(pass ? "E2E_PASS" : "E2E_FAIL");
    process.exit(pass ? 0 : 1);
  } catch (e) {
    console.error("E2E_ERROR", e);
    process.exit(1);
  }
});
setTimeout(() => { console.error("E2E_TIMEOUT"); process.exit(1); }, 480000); // 三轮模型回合 + 注入等待
