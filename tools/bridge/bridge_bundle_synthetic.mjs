#!/usr/bin/env node
// 桥随包物化自测（步骤5·桥随包单）：验证 materialize-bridge-bundle.mjs 产出的自足目录
// 能独立拉起桥——不依赖仓库布局（销项 78b34899 记档的「无仓库布局机器桥 spawn fail-closed」边界）。
//
// 三段：
//   A. 物化树要件断言（桥入口/tsx 装载器/@zcode 闭包/esbuild 平台二进制/services 源/juscite-flow quote-back/内置文集）。
//   B. 随包 spawn 径（system node + 包内 tsx，cwd=包内 tools/bridge）：/api/server-info 应答
//      store=sqlite + taskshell/flowgate/kb 能力代 + license 字段——与 dev 桥同面。
//   C. 打包径（BRIDGE_BUNDLE_ELECTRON_EXE 设置时，ci_gate package 传入 win-unpacked 桌面 exe）：
//      ELECTRON_RUN_AS_NODE=1 + 包内 tsx——desktopHostProcess.ts 打包分支的同款 spawn 参数。
// 全合成材料：许可走 BRIDGE_LICENSE_FILE 临时文件，oc28 走 BRIDGE_OC28_SSE=0 隔离；
// 杀前核验命令行含 bridge_host.mjs（宁停不误杀，同 ci_gate/license_synthetic 纪律）；
// #14 收场须端口已释放且自家 pid 已退出，短落静后才开 #15（不放宽 90s 探针，不扩杀）；
// 收场自清自家 %APPDATA%\Juscite\bridge\bridge-<port>.db*（只碰 Juscite 域）。
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url)); // tools/bridge/ → 仓库根
const BUNDLE_DIR = resolve(REPO_ROOT, process.env["BRIDGE_BUNDLE_DIR"] ?? "packages/desktop/bridge-bundle");
const PLATFORM_KEY = `${process.platform}-${process.arch}`;

let passed = 0, failed = 0;
function ok(n, label) { passed += 1; console.log(`ok ${n} - ${label}`); }
function fail(n, label, why) { failed += 1; console.log(`not ok ${n} - ${label} :: ${why}`); }
function assert(cond, n, label, why) { cond ? ok(n, label) : fail(n, label, why); return cond; }

// ── A. 物化树要件 ──
function bundleEssentials() {
  return [
    ["桥入口", join(BUNDLE_DIR, "tools", "bridge", "bridge_host.mjs")],
    ["桥面服务件", join(BUNDLE_DIR, "tools", "bridge", "bridge_store.mjs")],
    ["tsx 装载器", join(BUNDLE_DIR, "node_modules", "tsx", "dist", "cli.mjs")],
    ["esbuild 平台二进制", join(BUNDLE_DIR, "node_modules", "@esbuild", PLATFORM_KEY)],
    ["@zcode/services 包", join(BUNDLE_DIR, "node_modules", "@zcode", "services", "package.json")],
    ["@zcode/rpc 包", join(BUNDLE_DIR, "node_modules", "@zcode", "rpc", "package.json")],
    ["ws", join(BUNDLE_DIR, "node_modules", "ws", "package.json")],
    ["zod", join(BUNDLE_DIR, "node_modules", "zod", "package.json")],
    ["services TS 源", join(BUNDLE_DIR, "packages", "services", "src", "index.ts")],
    ["services 包清单（#src 子路径导入）", join(BUNDLE_DIR, "packages", "services", "package.json")],
    ["flow 原文回引（diligence_service 静态 import）", join(BUNDLE_DIR, "packages", "juscite-flow", "src", "quote-back.mjs")],
    ["内置文集（B61）", join(BUNDLE_DIR, "knowledge-base")],
    ["时间线技能规范包（timeline_skill 真源）", join(BUNDLE_DIR, "implementation", "skill-presets", "timeline-generation", "skill.json")],
  ];
}

// ── 随包 spawn 径共通件 ──
function pickFreePort() {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const used = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING/g)) used.add(Number(m[1]));
  let p = 34500 + (process.pid % 400);
  while (p < 34900) {
    if (!used.has(p)) return p;
    p += 1;
  }
  throw new Error("无空闲测试口");
}

function commandLineLooksLikeBridge(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
  { encoding: "utf-8", timeout: 20000 });
  return String(r.stdout ?? "").includes("bridge_host.mjs");
}

function portListening(port) {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  return new RegExp(`\\sTCP\\s+\\S*:${port}\\s+\\S+\\s+LISTENING`).test(String(r.stdout ?? ""));
}

/** tasklist CSV 的 PID 列（第 2 字段）。去掉 NUL，避免 UTF-16 管道被当成「已退出」。 */
function tasklistShowsPid(stdout, pid) {
  const text = String(stdout ?? "").replace(/\0/g, "");
  const id = String(Number(pid));
  if (!/^\d+$/.test(id)) return false;
  for (const line of text.split(/\r?\n/)) {
    const fields = [...line.matchAll(/"([^"]*)"/g)].map((m) => m[1]);
    if (fields[1] === id) return true;
  }
  return false;
}

/** 只查询自家 pid。口径同 cli_shim_synthetic.pidAlive（看 stdout，无匹配即不在）。
 *  spawn 失败或超时无法确认 → 不当成已退出。不扩杀。 */
function ownPidGone(pid) {
  const id = Number(pid);
  if (!Number.isInteger(id) || id <= 0) return false;
  const r = spawnSync("tasklist", ["/FI", `PID eq ${id}`, "/FO", "CSV", "/NH"], {
    encoding: "utf-8", timeout: 15000, windowsHide: true,
  });
  if (r.error || r.status == null) return false;
  if (tasklistShowsPid(r.stdout, id)) return false;
  // 出现了别的 pid 行：不能把「不是这一行」当成自家已退出。
  if (/"[^"]*","\d+"/.test(String(r.stdout ?? "").replace(/\0/g, ""))) return false;
  return true;
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
  // 端口不再 LISTENING 不够：自家进程还在时同口复用会踩着未释放的 bridge-<port>.db。
  // 只等、只核这一棵 pid；超时仍不净就抛，不二次扩杀。
  const deadline = Date.now() + 20000;
  let released = false;
  while (Date.now() < deadline) {
    if (!portListening(port) && ownPidGone(pid)) { released = true; break; }
    await new Promise((res) => setTimeout(res, 500));
  }
  if (!released) {
    if (portListening(port)) throw new Error(`:${port} 杀后仍 LISTENING`);
    if (!ownPidGone(pid)) throw new Error(`pid=${pid} 杀后仍在`);
  }
  cleanupBridgeFiles(port);
}

/** #14 → #15：收场未净、端口仍听、或自家 pid 仍在，都不许开 ELECTRON spawn。 */
function electronHandoffBlockReason(s) {
  if (!s || !s.teardownClean) {
    const detail = s && s.teardownError ? `：${s.teardownError}` : "";
    return `前序收场未净${detail}`;
  }
  if (s.portListening) return `前序 :${s.port} 仍 LISTENING`;
  if (s.pidAlive) return `前序 pid=${s.pid} 仍在`;
  return "";
}

// 落静在 90s 探针之外。重跑9：#14 后立刻拉 ELECTRON 冷启动贴着 90s（约 89.5s）。
const ELECTRON_HANDOFF_SETTLE_MS = 2000;

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

// 探活失败时把子进程 stderr 尾打进失败行（stdio 不继承父进程；只留有界尾，避免管道塞满卡住子进程）。
const STDERR_TAIL_KEEP = 4000;
function collectStderrTail(child) {
  let buf = "";
  const stream = child.stderr;
  if (!stream) return () => "";
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    buf += chunk;
    if (buf.length > STDERR_TAIL_KEEP) buf = buf.slice(-STDERR_TAIL_KEEP);
  });
  return () => buf;
}

function formatStderrTail(raw) {
  const lines = String(raw ?? "").trim().split(/\r?\n/).slice(-12).join("\n");
  if (!lines) return "";
  return lines.length > 800 ? lines.slice(-800) : lines;
}

function formatProbeFailure(port, elapsedMs, exitCode, stderrRaw) {
  const code = exitCode == null ? "null" : String(exitCode);
  const head = `:${port} 90s 不可探（随包 spawn 失败 elapsed_ms=${elapsedMs} exitCode=${code}）`;
  const tail = formatStderrTail(stderrRaw);
  return tail ? `${head}\n--- child stderr tail ---\n${tail}` : head;
}

/** spawnArgs/env 由调用方决定（B=system node，C=Electron-as-node），其余纪律共用。 */
async function spawnBundleBridge(n, label, electronExe) {
  const port = pickFreePort();
  const isElectronRun = Boolean(electronExe);
  const tsxCli = join(BUNDLE_DIR, "node_modules", "tsx", "dist", "cli.mjs");
  const entry = join(BUNDLE_DIR, "tools", "bridge", "bridge_host.mjs");
  const bridgeDir = join(BUNDLE_DIR, "tools", "bridge");
  const env = {
    ...process.env,
    BRIDGE_PORT: String(port),
    BRIDGE_OC28_SSE: "0",
    BRIDGE_LICENSE_FILE: licenseFile,
    ...(isElectronRun ? { ELECTRON_RUN_AS_NODE: "1" } : {}),
  };
  // windowsHide 对齐 desktopHostProcess.ts 打包分支。
  const startedAt = Date.now();
  const child = spawn(electronExe ?? process.execPath, [tsxCli, entry], {
    cwd: bridgeDir, env, stdio: ["ignore", "ignore", "pipe"], windowsHide: true,
  });
  const stderrTail = collectStderrTail(child);
  let teardownError = null;
  try {
    const info = await probeServerInfo(port, 90000);
    if (!info) {
      fail(n, label, formatProbeFailure(port, Date.now() - startedAt, child.exitCode, stderrTail()));
    } else {
      const problems = [];
      if (info.store !== "sqlite") problems.push(`store=${info.store} 期望 sqlite`);
      if (info.taskshell !== 1) problems.push("taskshell 能力代缺失");
      if (info.flowgate !== 1) problems.push("flowgate 能力代缺失");
      if (info.kb !== 1) problems.push("kb 能力代缺失");
      if (!info.license) problems.push("license 字段缺失");
      if (!Array.isArray(info.workspaces) || info.workspaces.length === 0) problems.push("workspaces 缺失");
      if (problems.length > 0) fail(n, label, problems.join("; "));
      else ok(n, label);
    }
  } finally {
    try { await killOwnBridge(child.pid, port); }
    catch (e) {
      teardownError = e instanceof Error ? e.message : String(e);
      fail(n, label, `收场异常: ${teardownError}`);
    }
  }
  return { port, pid: child.pid, teardownClean: teardownError == null, teardownError };
}

function handoffSnapshot(prev) {
  if (!prev || !prev.teardownClean) return prev ?? { teardownClean: false };
  return {
    ...prev,
    portListening: portListening(prev.port),
    pidAlive: !ownPidGone(prev.pid),
  };
}

// ── 跑 ──
let n = 0;
for (const [label, path] of bundleEssentials()) {
  n += 1;
  assert(existsSync(path), n, `要件·${label}`, path);
}

const scratch = mkdtempSync(join(tmpdir(), "bridge-bundle-synth-"));
const licenseFile = join(scratch, "license.json");
writeFileSync(licenseFile, JSON.stringify({
  schema: "juscite-license/1", licenseId: "bundle-synth", issuedAt: new Date().toISOString(), modules: {},
}), "utf-8");

n += 1;
const systemSpawn = await spawnBundleBridge(n, "随包 spawn（system node + 包内 tsx）", null);

const electronExe = process.env["BRIDGE_BUNDLE_ELECTRON_EXE"];
const electronLabel = "打包 spawn（ELECTRON_RUN_AS_NODE + 包内 tsx）";
if (electronExe) {
  n += 1;
  if (!existsSync(electronExe)) {
    fail(n, "打包 spawn（ELECTRON_RUN_AS_NODE）", `BRIDGE_BUNDLE_ELECTRON_EXE 不在物：${electronExe}`);
  } else {
    const block = electronHandoffBlockReason(handoffSnapshot(systemSpawn));
    if (block) {
      fail(n, electronLabel, `拒绝开打包 spawn（${block}）`);
    } else {
      await new Promise((res) => setTimeout(res, ELECTRON_HANDOFF_SETTLE_MS));
      const afterSettle = electronHandoffBlockReason(handoffSnapshot(systemSpawn));
      if (afterSettle) fail(n, electronLabel, `落静后仍不净，拒绝开打包 spawn（${afterSettle}）`);
      else await spawnBundleBridge(n, electronLabel, electronExe);
    }
  }
} else {
  console.log(`skip - 打包 spawn（未设 BRIDGE_BUNDLE_ELECTRON_EXE；ci_gate package 会传 win-unpacked 桌面 exe）`);
}

rmSync(scratch, { recursive: true, force: true });
console.log(`BRIDGE_BUNDLE_SYNTH: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  console.error("BRIDGE_BUNDLE_SYNTH_FAIL");
  process.exit(1);
}
console.log("BRIDGE_BUNDLE_SYNTH_PASS");
