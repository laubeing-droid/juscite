// 功能 #23 对话分支画布合成用例（施工单-03 任务三验收口径，全部合成材料）：
//   ①分支创建→切换→回退重生成 E2E 过（forkAssistant 建 child 带 forkNotice；child 独立对话；
//     editUserQuery rewind 裁剪重生成）；②分支数据随桥持久化（杀桥重启后 fork 链路行完整、
//     会话可用、无旧分支复活）；③守卫负测（非稳定目标/非最新行显式拒绝）。
// 自管隔离桥实例（BRIDGE_TEST_PORT，默认 3063，独立 bridge-{port}.db），不碰 :3030/:43127。
// 前置：oc28 :43127 已运行（真回合出产物）。末行 BRANCH_SYNTH_PASS / BRANCH_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { openSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3063);
const WORKSPACE = "D:\\mock\\lvyin-demo";
const NODE = process.execPath;
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok });
  console.log(`[branch-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const dbPath = () => join(process.env.APPDATA ?? "", "Juscite", "bridge", `bridge-${PORT}.db`);
function rows(sid) {
  const db = new DatabaseSync(dbPath(), { readOnly: true });
  const out = db.prepare("SELECT row_seq, kind, state, text, row_json FROM session_rows WHERE workspace_key = ? AND session_id = ? ORDER BY row_seq").all(WORKSPACE, sid);
  db.close();
  return out;
}

let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, `.local`, `branch-synth-bridge-${PORT}.log`), "a");
function spawnBridge() {
  const env = { ...process.env, BRIDGE_PORT: String(PORT) };
  const child = spawn(NODE, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: ["ignore", bridgeLog, bridgeLog], detached: true });
  child.unref();
  return child.pid;
}
async function probe() {
  try {
    const r = await fetch(`http://127.0.0.1:${PORT}/api/server-info`, { signal: AbortSignal.timeout(2500) });
    return r.ok && JSON.parse(await r.text()).store === "sqlite";
  } catch { return false; }
}
async function waitProbe(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) { if (await probe()) return true; await sleep(500); }
  return false;
}
async function killBridge(reason) {
  // 监听 pid 才是桥本体（spawn 直返 pid 可能是已退出的中间壳，tsx 链下监听在孙进程）
  const pids = findListenerPids();
  if (pids.length === 0) return;
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pids[0]}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  const line = String(r.stdout ?? "").trim();
  if (!line.includes("bridge_host.mjs")) {
    throw new Error(`拒绝杀进程 pid=${pids[0]}（${reason}）：命令行不含 bridge_host.mjs，宁停不误杀`);
  }
  spawnSync("taskkill", ["/PID", String(pids[0]), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probe())) await sleep(500);
}
function findListenerPids() {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const pids = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === PORT) pids.add(Number(m[2]));
  }
  return [...pids];
}

let ch = null;
async function connect() {
  const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws`);
  ws.binaryType = "arraybuffer";
  const data = { fire: (_b) => {} };
  ws.on("message", (buf) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
  await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
  const isocket = {
    onData: (l) => { data.fire = l; return { dispose: () => {} }; },
    onClose: () => ({ dispose: () => {} }),
    onEnd: () => ({ dispose: () => {} }),
    write: (b) => ws.send(b.buffer),
    end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
  };
  ch = new ChannelClient(new SocketProtocol(isocket)).getChannel("zcode-agent");
  await ch.call("helloConversationV4", []);
}
const call = (m, a) => ch.call(m, a === undefined ? [] : [a]);
const cmd = (envelope, extra = {}) => call("sendConversationCommandV4", { workspacePath: WORKSPACE, ...extra, envelope });

/** 等某会话出现 state=complete 的 assistant 行（真回合收口），返回全部行。 */
async function waitComplete(sid, timeoutMs = 200_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const rs = rows(sid);
    if (rs.some((r) => r.kind === "assistantText" && r.state === "complete")) return rs;
    await sleep(2000);
  }
  return rows(sid);
}

try {
  // ── P1 母会话一轮真回合：canEdit/canFork/entityId 入口面 ──
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error(`隔离桥 :${PORT} 40s 不可探`);
  await connect();
  const sid = "ses_brpar_" + randomUUID().slice(0, 6);
  await cmd({ commandId: "cmd_c_" + randomUUID().slice(0, 6), clientId: "branch-synth", sessionId: sid, type: "createSession", payload: { sessionId: sid, workspaceId: WORKSPACE }, issuedAt: Date.now() });
  await cmd({ commandId: "cmd_s_" + randomUUID().slice(0, 6), clientId: "branch-synth", sessionId: sid, type: "sendText", payload: { text: "分支合成测试：请用一句话回复「母轮完成」。" }, issuedAt: Date.now() });
  const p1rows = await waitComplete(sid);
  const asstJson = JSON.parse(p1rows.find((r) => r.kind === "assistantText" && r.state === "complete")?.row_json ?? "{}");
  const userJson = JSON.parse(p1rows.find((r) => r.kind === "userInput")?.row_json ?? "{}");
  check("P1 母轮完成且行带入口面（entityId+canFork/canEdit）",
    Boolean(asstJson.entityId) && asstJson.actions?.canFork === true && Boolean(userJson.entityId) && userJson.actions?.canEdit === true,
    `asst.ent=${asstJson.entityId ?? "无"} canFork=${asstJson.actions?.canFork} user.canEdit=${userJson.actions?.canEdit}`);

  // ── P2 分支创建：forkAssistant → child 会话 + forkNotice/forkCreated 链路行 ──
  const forkAck = await cmd({ commandId: "cmd_f_" + randomUUID().slice(0, 6), clientId: "branch-synth", sessionId: sid, baseRevision: 1, baseLogEpoch: "bridge-conv-x", type: "forkAssistant", payload: { target: { rowId: asstJson.rowId, entityId: asstJson.entityId } }, issuedAt: Date.now() });
  const childId = forkAck?.result?.type === "forkAssistant" ? forkAck.result.sessionId : null;
  check("P2 forkAssistant accepted 带 child sessionId", forkAck?.status === "accepted" && typeof childId === "string" && childId.length > 0,
    `status=${forkAck?.status} child=${childId ?? "无"}`);
  const childRows1 = childId ? rows(childId) : [];
  let notice = null;
  for (const r of childRows1) {
    const j = JSON.parse(r.row_json);
    if (j.kind === "timelineMarker" && j.marker?.type === "forkNotice") notice = j;
  }
  check("P2 child 首部 forkNotice 指回父行", Boolean(notice) && notice.marker.parentSessionId === sid && notice.marker.parentRowId === asstJson.rowId,
    `notice=${notice ? JSON.stringify(notice.marker) : "无"}`);
  const parentRows2 = rows(sid);
  let created = null;
  for (const r of parentRows2) {
    const j = JSON.parse(r.row_json);
    if (j.kind === "timelineMarker" && j.marker?.type === "forkCreated" && j.marker.childSessionId === childId) created = j;
  }
  check("P2 父会话 forkCreated 登记 child", Boolean(created), `created=${created ? created.marker.childSessionId : "无"}`);

  // ── P3 切换到分支独立对话（child sendText → 独立回合产物）──
  await cmd({ commandId: "cmd_bc_" + randomUUID().slice(0, 6), clientId: "branch-synth", sessionId: childId, type: "sendText", payload: { text: "分支内合成提问：请回复「分支轮完成」。" }, issuedAt: Date.now() });
  const childRows3 = await waitComplete(childId);
  const childUser = childRows3.find((r) => r.kind === "userInput");
  const childAsst = childRows3.find((r) => r.kind === "assistantText" && r.state === "complete");
  check("P3 分支内独立对话成立（child 有自己的 user+assistant 轮）",
    Boolean(childUser) && Boolean(childAsst) && !childUser.text.includes("母轮"),
    `child.user="${(childUser?.text ?? "").slice(0, 18)}" asst="${(childAsst?.text ?? "").slice(0, 24)}"`);

  // ── P4 回退重生成：editUserQuery rewind 裁剪 + 新答 ──
  const newCommandId = "cmd_e_" + randomUUID().slice(0, 6);
  const editAck = await cmd({ commandId: newCommandId, clientId: "branch-synth", sessionId: sid, baseRevision: 1, baseLogEpoch: "bridge-conv-x", type: "editUserQuery", payload: { target: { rowId: userJson.rowId, entityId: userJson.entityId }, newText: "编辑后的合成问法：请回复「已按新问法重答」。", workspaceMode: "preserve" }, issuedAt: Date.now() });
  check("P4 editUserQuery accepted disposition=rewind",
    editAck?.status === "accepted" && editAck?.result?.type === "editUserQuery" && editAck?.result?.disposition === "rewind",
    `status=${editAck?.status} result=${JSON.stringify(editAck?.result ?? null)}`);
  const p4rows = await waitComplete(sid);
  const p4user = p4rows.find((r) => r.kind === "userInput");
  const p4asst = p4rows.filter((r) => r.kind === "assistantText" && r.state === "complete");
  const p4userJson = JSON.parse(p4user?.row_json ?? "{}");
  check("P4 裁剪生效：旧 assistant 行已移除、user 行换成新文本（sourceCommandId=edit 命令）",
    p4asst.length === 1 && p4userJson.text.includes("已按新问法重答") && p4userJson.sourceCommandId === newCommandId,
    `completeAsst=${p4asst.length} user="${(p4userJson.text ?? "").slice(0, 18)}" srcCmd=${p4userJson.sourceCommandId === newCommandId}`);

  // ── P5 守卫负测：非稳定 fork 目标 / 非最新 edit 目标显式拒绝 ──
  const badFork = await cmd({ commandId: "cmd_bf_" + randomUUID().slice(0, 6), clientId: "branch-synth", sessionId: sid, type: "forkAssistant", payload: { target: { rowId: asstJson.rowId, entityId: "ent_stale" } }, issuedAt: Date.now() });
  const badEdit = await cmd({ commandId: "cmd_be_" + randomUUID().slice(0, 6), clientId: "branch-synth", sessionId: sid, type: "editUserQuery", payload: { target: { rowId: 9999, entityId: "ent_x" }, newText: "不应生效" }, issuedAt: Date.now() });
  check("P5 负测显式拒绝（stale fork / 非 latest edit）",
    badFork?.status === "rejected" && badFork?.reasonCode === "guard.forkTargetNotStable"
    && badEdit?.status === "rejected" && badEdit?.reasonCode === "guard.editTargetNotLatest",
    `fork=${badFork?.status}/${badFork?.reasonCode} edit=${badEdit?.status}/${badEdit?.reasonCode}`);

  // ── P6 重启持久化：杀桥重启后 fork 链路完整、会话可用、无旧分支复活 ──
  // 注：父会话 forkCreated marker 已随 P4 rewind 正确消失（分支点行被裁，marker 随行集裁剪，
  // rows.ts「出现在 parent（可选展示）」）；分支 LINK 的持久凭据=child 首部 forkNotice。
  await killBridge("P6 重启实测");
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error("P6 重启桥 40s 不可探");
  await connect();
  const p6child = rows(childId);
  const p6parent = rows(sid);
  const p6notice = p6child.some((r) => { const j = JSON.parse(r.row_json); return j.kind === "timelineMarker" && j.marker?.type === "forkNotice"; });
  const p6noResurrect = p6parent.filter((r) => r.kind === "assistantText" && r.state === "complete").length === 1
    && JSON.parse(p6parent.find((r) => r.kind === "userInput")?.row_json ?? "{}").text.includes("已按新问法重答");
  const p6markerGone = !p6parent.some((r) => { const j = JSON.parse(r.row_json); return j.marker?.type === "forkCreated"; });
  check("P6 重启后分支链路持久（child forkNotice 存活+裁剪态不复活+rewound marker 不复活）",
    p6notice && p6noResurrect && p6markerGone,
    `notice=${p6notice} noResurrect=${p6noResurrect} rewoundMarkerGone=${p6markerGone} parentRows=${p6parent.length}`);
  await cmd({ commandId: "cmd_p6_" + randomUUID().slice(0, 6), clientId: "branch-synth", sessionId: childId, type: "sendText", payload: { text: "重启后的分支提问：请回复「分支仍可用」。" }, issuedAt: Date.now() });
  const p6childAfter = await waitComplete(childId);
  check("P6 重启后分支会话继续可用（真回合完成）",
    p6childAfter.some((r) => r.kind === "assistantText" && r.state === "complete"),
    `childRows=${p6childAfter.length}`);
} catch (e) {
  check("用例执行", false, e?.message ?? String(e));
} finally {
  // 清场：自管实例不留孤儿（监听 pid 核验命令行后才杀，宁停不误杀）
  try {
    for (const pid of findListenerPids()) {
      const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
        `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
        { encoding: "utf-8", timeout: 20000 });
      if (String(r.stdout ?? "").includes("bridge_host.mjs")) {
        spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
        console.log(`[branch-synth] 清场：隔离桥 ${pid} 已停`);
      }
    }
  } catch { /* 已死则忽略 */ }
}

const pass = results.every((r) => r.ok);
console.log(pass ? "BRANCH_SYNTH_PASS" : "BRANCH_SYNTH_FAIL");
process.exit(pass ? 0 : 1);
