// 桥重启不丢案探针（ci_gate.mjs persist 子步骤的 RPC 客户端，手法照抄 conversation.e2e.mts 已验证路径）。
// phase1：桥上新建会话发一句合成消息→等 assistant complete→冷订阅取权威快照（rows+seq）→落状态 JSON。
// phase2：按状态 JSON 冷订阅同一会话→重启后的快照逐行对拍（行数/kind/state/text/seq 全等）。
// 用法（仓库根）：
//   node --import tsx tools/bridge/persist_probe.mts phase1 <state.json>
//   node --import tsx tools/bridge/persist_probe.mts phase2 <state.json>
// 桥地址经 BRIDGE_WS_URL（默认 ws://127.0.0.1:3030/ws）。合成材料；末行 PERSIST_PASS / PERSIST_FAIL。
import WebSocket from "ws";
import { readFileSync, writeFileSync } from "node:fs";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { randomUUID } from "node:crypto";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const WS_URL = process.env.BRIDGE_WS_URL ?? "ws://127.0.0.1:3030/ws";
const WORKSPACE = "D:\\mock\\lvyin-demo";
type Row = { rowId?: number; kind?: string; text?: string; state?: string; sourceCommandId?: string };
type Delta = { op: string; row?: Row; append?: string };
type Snapshot = { seq?: number; rows?: { window: Row[] }; control?: { phase: string } };
type Frame = {
  deliveryKind?: string;
  frame?: { payload?: { kind?: string; snapshot?: Snapshot; deltas?: Delta[] } };
  payload?: { kind?: string; snapshot?: Snapshot; deltas?: Delta[] };
};
const deltasOf = (f: Frame): Delta[] => f.frame?.payload?.deltas ?? f.payload?.deltas ?? [];
const snapshotOf = (f: Frame): Snapshot | undefined => f.frame?.payload?.snapshot ?? f.payload?.snapshot;

function connect(): Promise<{ call: (m: string, a?: unknown) => Promise<never>; frames: Frame[] }> {
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
        onClose: (_l: () => void) => ({ dispose: () => {} }),
        onEnd: (_l: () => void) => ({ dispose: () => {} }),
        write: (b: VSBuffer) => ws.send(b.buffer),
        end: () => ws.close(),
        drain: async () => {},
        dispose: () => ws.close(),
      };
      const client = new ChannelClient(new SocketProtocol(isocket as never));
      const ch = client.getChannel("zcode-agent");
      const call = (m: string, a?: unknown) => ch.call<never>(m, a === undefined ? [] : [a]);
      ch.listen<never>("onDynamicConversationFrame", { workspacePath: WORKSPACE })((f: { topic: string }) => {
        if (f.topic.startsWith("conversation/")) frames.push(f as Frame);
      });
      resolve({ call, frames });
    });
  });
}
// 冷订阅：新 subscriptionId，等 deliveryKind=initial 的权威快照
async function coldSnapshot(call: (m: string, a?: unknown) => Promise<never>, frames: Frame[], sessionId: string): Promise<Snapshot> {
  const before = frames.length;
  await call("subscribeConversationV4", { topic: `conversation/${sessionId}`, workspacePath: WORKSPACE, historyFirst: true });
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    await sleep(200);
    const f = frames.slice(before).find((x) => x.deliveryKind === "initial" && snapshotOf(x));
    if (f) return snapshotOf(f) as Snapshot;
  }
  throw new Error(`cold_subscribe_no_initial_snapshot(${sessionId})`);
}
function normalize(snap: Snapshot) {
  return {
    seq: snap.seq ?? null,
    rows: (snap.rows?.window ?? []).map((r) => ({
      rowId: r.rowId ?? null, kind: r.kind ?? null, state: r.state ?? null,
      text: r.text ?? "", sourceCommandId: r.sourceCommandId ?? null,
    })),
  };
}

async function phase1(stateFile: string) {
  const sessionId = "ses_persist_" + randomUUID().slice(0, 6);
  const { call, frames } = await connect();
  await call("helloConversationV4");
  await call("subscribeConversationV4", { topic: `conversation/${sessionId}`, workspacePath: WORKSPACE, historyFirst: true });
  await call("sendConversationCommandV4", { workspacePath: WORKSPACE, envelope: {
    commandId: "cmd_create_" + randomUUID(), clientId: "persist-probe", sessionId: null,
    type: "createSession", payload: { sessionId, workspaceId: WORKSPACE }, issuedAt: Date.now(),
  } });
  const commandId = "cmd_persist_" + randomUUID().slice(0, 8);
  await call("sendConversationCommandV4", { workspacePath: WORKSPACE, envelope: {
    commandId, clientId: "persist-probe", sessionId, type: "sendText",
    payload: { text: "桥重启持久化门禁探针（合成材料），请只回复：持久化探针完成。" }, issuedAt: Date.now(),
  } });
  // 等 assistant 行 complete（单轮，上限 150s）
  const deadline = Date.now() + 150000;
  let reply = "";
  while (Date.now() < deadline) {
    await sleep(500);
    const deltas = frames.flatMap(deltasOf);
    for (const d of deltas) {
      if (d.op === "row.delta") reply += d.append ?? "";
      if (d.op === "row.upserted" && d.row?.state === "complete") reply = d.row.text ?? reply;
    }
    if (reply && deltas.some((d) => d.op === "row.upserted" && d.row?.state === "complete")) break;
  }
  if (!reply) throw new Error("phase1_no_assistant_complete_in_150s");
  const state = { sessionId, marker: "JUSCITE-PERSIST-GATE", ...normalize(await coldSnapshot(call, frames, sessionId)) };
  writeFileSync(stateFile, JSON.stringify(state, null, 2));
  console.log(`[persist-probe] phase1 sessionId=${state.sessionId} rows=${state.rows.length} seq=${state.seq}`);
  console.log(`[persist-probe] reply=${reply.slice(0, 80)}`);
  console.log("PERSIST_PHASE1_OK");
  process.exit(0);
}

async function phase2(stateFile: string) {
  const prev = JSON.parse(readFileSync(stateFile, "utf-8"));
  const { call, frames } = await connect();
  await call("helloConversationV4");
  const now = normalize(await coldSnapshot(call, frames, prev.sessionId));
  const problems: string[] = [];
  if (now.seq !== prev.seq) problems.push(`seq: 前=${prev.seq} 后=${now.seq}`);
  if (now.rows.length !== prev.rows.length) problems.push(`行数: 前=${prev.rows.length} 后=${now.rows.length}`);
  for (let i = 0; i < Math.min(now.rows.length, prev.rows.length); i++) {
    if (JSON.stringify(now.rows[i]) !== JSON.stringify(prev.rows[i])) {
      problems.push(`行[${i}]: 前=${JSON.stringify(prev.rows[i]).slice(0, 160)} 后=${JSON.stringify(now.rows[i]).slice(0, 160)}`);
    }
  }
  if (problems.length) {
    console.log(`[persist-probe] 会话 ${prev.sessionId} 重启后不一致:`);
    for (const p of problems) console.log(`[persist-probe]   ✗ ${p}`);
    console.log("PERSIST_FAIL");
    process.exit(1);
  }
  console.log(`[persist-probe] 会话 ${prev.sessionId} 重启后 ${now.rows.length} 行与 seq=${now.seq} 完整一致`);
  console.log("PERSIST_PASS");
  process.exit(0);
}

// crash：createSession→sendText→ack 后立刻退出（不等回复）。ci_gate 随后杀桥制造"receipt 已落/
// 行未完成"崩溃窗（F1③）。文本也存档供 replay 原样重放。
async function crash(stateFile: string) {
  const sessionId = "ses_persist_" + randomUUID().slice(0, 6);
  const commandId = "cmd_crash_" + randomUUID().slice(0, 8);
  const text = "桥崩溃窗持久化门禁探针（合成材料），请只回复：崩溃窗探针完成。";
  const { call } = await connect();
  await call("helloConversationV4");
  await call("subscribeConversationV4", { topic: `conversation/${sessionId}`, workspacePath: WORKSPACE, historyFirst: true });
  await call("sendConversationCommandV4", { workspacePath: WORKSPACE, envelope: {
    commandId: "cmd_create_" + randomUUID(), clientId: "persist-probe", sessionId: null,
    type: "createSession", payload: { sessionId, workspaceId: WORKSPACE }, issuedAt: Date.now(),
  } });
  const ack = await call("sendConversationCommandV4", { workspacePath: WORKSPACE, envelope: {
    commandId, clientId: "persist-probe", sessionId, type: "sendText", payload: { text }, issuedAt: Date.now(),
  } });
  writeFileSync(stateFile, JSON.stringify({ sessionId, commandId, text, ackStatus: (ack as never as { status?: string })?.status ?? null, marker: "JUSCITE-PERSIST-CRASH" }));
  console.log(`[persist-probe] crash sessionId=${sessionId} commandId=${commandId} ack=${(ack as never as { status?: string })?.status}`);
  console.log("PERSIST_CRASH_OK");
  process.exit(0);
}

// replay：重启后订阅崩溃会话→断言无 running 相位（F3）→重放同 sendText envelope→
// 断言行出现（complete）或显式错误（failed），且终态无 running（F1③）。
async function replay(stateFile: string) {
  const st = JSON.parse(readFileSync(stateFile, "utf-8"));
  const { call, frames } = await connect();
  await call("helloConversationV4");
  const snap0 = await coldSnapshot(call, frames, st.sessionId);
  const rows0 = snap0.rows?.window ?? [];
  const phase0 = snap0.control?.phase;
  console.log(`[persist-probe] 重启快照: phase=${phase0} rows=${rows0.length}`);
  if (phase0 === "running") {
    console.log("[persist-probe]   ✗ 恢复快照存在 running 相位（F3 违例：mid-turn 僵尸会话）");
    console.log("PERSIST_REPLAY_FAIL");
    process.exit(1);
  }
  // 重放同 envelope（UI 重连不重发 create，故只重放 sendText）
  await call("sendConversationCommandV4", { workspacePath: WORKSPACE, envelope: {
    commandId: st.commandId, clientId: "persist-probe", sessionId: st.sessionId,
    type: "sendText", payload: { text: st.text }, issuedAt: Date.now(),
  } });
  const deadline = Date.now() + 90000;
  let lastPhase = phase0;
  let terminal: { state: string; text: string } | null = null;
  while (Date.now() < deadline) {
    await sleep(2000);
    const snap = await coldSnapshot(call, frames, st.sessionId);
    lastPhase = snap.control?.phase ?? lastPhase;
    const asst = (snap.rows?.window ?? []).filter((r) => r.kind === "assistantText");
    const done = asst.find((r) => r.state === "complete" && (r.text ?? "").length > 0);
    const failed = asst.find((r) => r.state === "failed");
    if (done) { terminal = { state: "complete", text: (done.text ?? "").slice(0, 60) }; break; }
    if (failed && lastPhase !== "running") { terminal = { state: "failed", text: (failed.text ?? "").slice(0, 60) }; break; }
  }
  if (!terminal) {
    console.log(`[persist-probe]   ✗ 重放后 90s 内无终态行（最后 phase=${lastPhase}）`);
    console.log("PERSIST_REPLAY_FAIL");
    process.exit(1);
  }
  if (lastPhase === "running") {
    console.log("[persist-probe]   ✗ 终态行已出但会话相位仍 running（F3 违例）");
    console.log("PERSIST_REPLAY_FAIL");
    process.exit(1);
  }
  console.log(`[persist-probe] 重放结果: 行=${terminal.state} phase=${lastPhase} text="${terminal.text}"`);
  console.log("PERSIST_REPLAY_OK");
  process.exit(0);
}

const [, , phase, stateFile] = process.argv;
const PHASES: Record<string, (f: string) => Promise<void>> = { phase1, phase2, crash, replay };
if (!stateFile || !PHASES[phase]) {
  console.error("用法: node --import tsx tools/bridge/persist_probe.mts <phase1|phase2|crash|replay> <state.json>");
  process.exit(2);
}
PHASES[phase](stateFile).catch((e) => { console.error("PERSIST_PROBE_ERROR", e); process.exit(1); });
setTimeout(() => { console.error("PERSIST_PROBE_TIMEOUT"); process.exit(1); }, 240000);
