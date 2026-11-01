// 功能 #22 定时任务合成用例（施工单-03 任务二验收口径，全部合成材料）：
//   ①合成定时任务到点真跑出产物（会话任务上屏+运行历史 succeeded）；
//   ②杀桥重启后任务表完整、到点继续跑（recurring 每分钟）；
//   ③错过的触发有如实记录（misfire → skipped run，不静默吞）。
// 自管隔离桥实例（BRIDGE_TEST_PORT，默认 3062，独立 bridge-{port}.db），不碰 :3030/:43127。
// 前置：oc28 :43127 已运行（真回合出产物）。末行 AUTOMATION_SYNTH_PASS / AUTOMATION_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { openSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3062);
const WORKSPACE = "D:\\mock\\lvyin-demo";
const NODE = process.execPath;
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok });
  console.log(`[auto-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, `.local`, `auto-synth-bridge-${PORT}.log`), "a");
function dbPath() { return join(process.env.APPDATA ?? "", "Juscite", "bridge", `bridge-${PORT}.db`); }
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
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${bridgePid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  const line = String(r.stdout ?? "").trim();
  if (!line.includes("bridge_host.mjs")) {
    throw new Error(`拒绝杀进程 pid=${bridgePid}（${reason}）：命令行不含 bridge_host.mjs，宁停不误杀`);
  }
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probe())) await sleep(500);
}
/** 杀桥前等非认领态：running=1 时硬杀会让重启后等 CLAIM_STALE（10min）才回收，测试超时假阴。 */
async function waitNotClaimed(automationId, timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const a = (await call("listAllAutomations")).find((x) => x.automationId === automationId);
    if (!a || a.dispatchStatus !== "claimed") return true;
    await sleep(3000);
  }
  return false;
}

// ---- RPC 客户端（每次重启桥后重连）----
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

try {
  // ── P1 创建与列表 ──
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error(`隔离桥 :${PORT} 40s 不可探`);
  await connect();
  const created = await call("createAutomation", {
    title: "合成定时试跑·一次性",
    cronExpr: "* * * * *",
    relativeDelayMinutes: 1,
    prompt: "自动化合成试跑：请用一句话回复「定时产物已生成」。",
    workspacePath: WORKSPACE,
    recurring: false,
  });
  const oneShotOk = Boolean(created?.automationId) && created.enabled === true
    && Math.abs((created.nextRunAt ?? 0) - Date.now() - 60_000) < 20_000;
  check("P1 一次性任务创建（next_run_at≈+60s）", oneShotOk,
    `id=${created?.automationId} nextRunIn=${created ? Math.round((created.nextRunAt - Date.now()) / 1000) : "?"}s`);
  const list1 = await call("listAllAutomations");
  check("P1 列表可见且 active", Array.isArray(list1) && list1.some((a) => a.automationId === created.automationId && a.lifecycleStatus === "active"),
    `count=${list1?.length}`);

  // ── P2 到点真跑出产物 ──
  let dispatchedRun = null;
  const p2Deadline = Date.now() + 200_000;
  while (Date.now() < p2Deadline && !dispatchedRun) {
    const runs = await call("listAutomationRuns", { automationId: created.automationId, workspacePath: WORKSPACE });
    dispatchedRun = (runs ?? []).find((r) => r.dispatchStatus === "dispatched" || r.outcome === "succeeded" || r.outcome === "failed") ?? null;
    if (!dispatchedRun) await sleep(5000);
  }
  check("P2 到点触发出 run（dispatched 带 sessionId）", Boolean(dispatchedRun?.sessionId),
    `runId=${dispatchedRun?.runId ?? "无"} sid=${dispatchedRun?.sessionId ?? "无"}`);
  let outcome = dispatchedRun?.outcome ?? null;
  const p2bDeadline = Date.now() + 240_000;
  while (Date.now() < p2bDeadline && outcome !== "succeeded" && outcome !== "failed") {
    await sleep(5000);
    const runs = await call("listAutomationRuns", { automationId: created.automationId, workspacePath: WORKSPACE });
    outcome = (runs ?? []).find((r) => r.runId === dispatchedRun?.runId)?.outcome ?? null;
  }
  check("P2 运行终态 succeeded（真回合产物）", outcome === "succeeded", `outcome=${outcome}`);
  const afterRun = (await call("listAllAutomations")).find((a) => a.automationId === created.automationId);
  check("P2 产物任务以定时任务名登记侧栏", afterRun?.runCount >= 1 && afterRun?.lastRunAt > 0,
    `runCount=${afterRun?.runCount} title=${afterRun?.title}`);

  // ── P3 重启存活：recurring 每分钟，重启后到点继续跑 ──
  const recurring = await call("createAutomation", {
    title: "合成定时试跑·每分钟",
    cronExpr: "*/1 * * * *",
    prompt: "每分钟合成试跑：回复「心跳正常」。",
    workspacePath: WORKSPACE,
    recurring: true,
  });
  let recurringRuns = 0;
  const p3Deadline = Date.now() + 200_000;
  while (Date.now() < p3Deadline && recurringRuns < 1) {
    const a = (await call("listAllAutomations")).find((x) => x.automationId === recurring.automationId);
    recurringRuns = a?.runCount ?? 0;
    if (recurringRuns < 1) await sleep(5000);
  }
  check("P3 recurring 首轮到点运行", recurringRuns >= 1, `runCount=${recurringRuns}`);

  await waitNotClaimed(recurring.automationId);
  await killBridge("P3 重启实测");
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error("P3 重启桥 40s 不可探");
  await connect();
  const afterRestart = (await call("listAllAutomations")).find((x) => x.automationId === recurring.automationId);
  check("P3 重启后任务表完整", Boolean(afterRestart) && afterRestart.runCount >= 1
    && afterRestart.lifecycleStatus === "active" && afterRestart.enabled === true,
    `runCount=${afterRestart?.runCount} lifecycle=${afterRestart?.lifecycleStatus}`);
  const restartAt = Date.now();
  let postRestartRun = null;
  const p3bDeadline = Date.now() + 200_000;
  while (Date.now() < p3bDeadline && !postRestartRun) {
    const runs = await call("listAutomationRuns", { automationId: recurring.automationId, workspacePath: WORKSPACE });
    postRestartRun = (runs ?? []).find((r) => r.trigger === "schedule"
      && r.dispatchStatus === "dispatched" && (r.updatedAt ?? 0) > restartAt) ?? null;
    if (!postRestartRun) await sleep(5000);
  }
  check("P3 重启后到点继续跑（新 scheduled run）", Boolean(postRestartRun), `runId=${postRestartRun?.runId ?? "无"}`);

  // ── P4 错过触发如实记录（misfire → skipped）──
  await waitNotClaimed(recurring.automationId);
  await killBridge("P4 misfire 实测");
  {
    const db = new DatabaseSync(dbPath());
    const stale = Date.now() - 10 * 60_000;
    db.prepare(`UPDATE automations SET enabled = 1, running = 0, claimed_at = NULL, retry_at = NULL,
      next_run_at = ? WHERE automation_id = ?`).run(stale, recurring.automationId);
    db.close();
  }
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error("P4 重启桥 40s 不可探");
  await connect();
  let skippedRun = null;
  const p4Deadline = Date.now() + 90_000;
  while (Date.now() < p4Deadline && !skippedRun) {
    const runs = await call("listAutomationRuns", { automationId: recurring.automationId, workspacePath: WORKSPACE });
    skippedRun = (runs ?? []).find((r) => r.dispatchStatus === "skipped") ?? null;
    if (!skippedRun) await sleep(5000);
  }
  const afterSkip = (await call("listAllAutomations")).find((x) => x.automationId === recurring.automationId);
  check("P4 错过触发记 skipped run（不静默吞）", Boolean(skippedRun) && String(skippedRun.error ?? "").includes("computer_asleep"),
    `runId=${skippedRun?.runId ?? "无"} reason=${skippedRun?.error ?? "无"}`);
  check("P4 skipped 后调度前推（next_run_at 恢复未来）", (afterSkip?.nextRunAt ?? 0) > Date.now(),
    `nextRunIn=${afterSkip ? Math.round((afterSkip.nextRunAt - Date.now()) / 1000) : "?"}s`);

  // ── P5 清理（自管测试数据不留库）──
  await call("deleteAutomation", { automationId: created.automationId, workspacePath: WORKSPACE });
  await call("deleteAutomation", { automationId: recurring.automationId, workspacePath: WORKSPACE });
  const left = (await call("listAllAutomations")).filter((a) =>
    a.automationId === created.automationId || a.automationId === recurring.automationId);
  check("P5 清理（deleteAutomation 生效）", left.length === 0, `left=${left.length}`);
} catch (e) {
  check("用例执行", false, e?.message ?? String(e));
} finally {
  try { await call("dispose"); } catch { /* 断连即可 */ }
}

const pass = results.every((r) => r.ok);
console.log(pass ? "AUTOMATION_SYNTH_PASS" : "AUTOMATION_SYNTH_FAIL");
process.exit(pass ? 0 : 1);
