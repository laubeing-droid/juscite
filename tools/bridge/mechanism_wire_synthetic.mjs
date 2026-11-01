#!/usr/bin/env node
// 【施工单-06】桥内机制件接线自测（ci_gate fast 随行步）。
// 真子进程径：自拉 bridge_host.mjs 独立实例（随机空闲口+BRIDGE_OC28_SSE=0 隔离 oc28），
// 断言 /api/server-info 携 taskshell/flowgate 能力标记（旧桥缺标记=旧换新判据，同 kb 标记惯例），
// 直开桥库文件断言 0014/0015 迁移三表在物；收场杀自家实例（杀前核验命令行含 bridge_host.mjs，
// 同 ci_gate 纪律）并清掉自己的 bridge-<port>.db* 与 artifacts 目录。
// 纯 Node 零依赖；单命令 exit 0/1，末行 MECHWIRE_SYNTH_PASS 可判。
// 用法：node tools/bridge/mechanism_wire_synthetic.mjs
import { spawn, spawnSync } from "node:child_process";
import { rmSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { mkdtempSync } from "node:fs";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url)); // tools/bridge/ → 仓库根
const scratch = mkdtempSync(join(tmpdir(), "juscite-mechwire-"));
let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[mechwire-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[mechwire-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }

function pickFreePort() {
  for (let p = 30400 + Math.floor(Math.random() * 2000); ; p += 1) {
    const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Test-NetConnection -ComputerName 127.0.0.1 -Port ${p} -InformationLevel Quiet -WarningAction SilentlyContinue)`],
      { encoding: "utf-8", timeout: 20000 });
    if (String(r.stdout ?? "").trim() !== "True") return p;
  }
}
function commandLineLooksLikeBridge(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  return String(r.stdout ?? "").includes("bridge_host.mjs");
}
const storeDir = join(homedir(), "AppData", "Roaming", "Juscite", "bridge");
function cleanupBridgeFiles(port) {
  for (const suffix of [".db", ".db-wal", ".db-shm"]) {
    try { rmSync(join(storeDir, `bridge-${port}${suffix}`), { force: true }); } catch { /* 尽力而为 */ }
  }
}
async function killOwnBridge(pid, port) {
  if (!commandLineLooksLikeBridge(pid)) throw new Error(`pid=${pid} 命令行不含 bridge_host.mjs，宁停不误杀`);
  spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
    if (!new RegExp(`\\sTCP\\s+\\S*:${port}\\s+\\S+\\s+LISTENING`).test(String(r.stdout ?? ""))) break;
    await new Promise((res) => setTimeout(res, 500));
  }
  cleanupBridgeFiles(port);
}
async function probeServerInfo(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/server-info`, { signal: AbortSignal.timeout(2500) });
      if (r.ok) return JSON.parse(await r.text());
    } catch { /* 未起，重试 */ }
    await new Promise((res) => setTimeout(res, 500));
  }
  return null;
}

const port = pickFreePort();
const env = { ...process.env, BRIDGE_PORT: String(port), BRIDGE_OC28_SSE: "0" };
const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
  { cwd: REPO_ROOT, env, stdio: "ignore", detached: true });
try {
  // 用例 1：桥起+能力标记在物
  const info = await probeServerInfo(port, 60000);
  if (!info) { fail(1, `:${port} 60s 不可探`); throw new Error("桥未起，后续用例跳过"); }
  if (info.taskshell === 1 && info.flowgate === 1 && info.store === "sqlite")
    ok(1, "server-info 携 taskshell/flowgate 标记");
  else fail(1, "能力标记缺失", JSON.stringify({ taskshell: info.taskshell, flowgate: info.flowgate }));

  // 用例 2：迁移在物——async_tasks/flow_nodes/flow_node_events 三表可查
  const db = new DatabaseSync(join(storeDir, `bridge-${port}.db`), { readOnly: true });
  const tables = new Set(db.prepare(
    "SELECT name FROM sqlite_master WHERE type='table'").all().map((r) => r.name));
  if (tables.has("async_tasks") && tables.has("flow_nodes") && tables.has("flow_node_events"))
    ok(2, "0014/0015 迁移三表在物");
  else fail(2, "迁移表缺失", JSON.stringify([...tables]));
  db.close();
} catch (e) {
  fail("fatal", e.message);
} finally {
  try { await killOwnBridge(child.pid, port); } catch (e) { fail("cleanup", `收场异常: ${e.message}`); }
  try { rmSync(scratch, { recursive: true, force: true }); } catch { /* 尽力而为 */ }
}

console.log(`[mechwire-synth] ── ${passed} OK / ${failed} FAIL ──`);
if (failed > 0) { console.error("MECHWIRE_SYNTH_FAIL"); process.exit(1); }
console.log("MECHWIRE_SYNTH_PASS");
