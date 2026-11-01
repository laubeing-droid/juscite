#!/usr/bin/env node
// 【桥·增强三式·式三】Windows .cmd 包装防转义坑（2026-10-30 施工）。
// 唯一依据=竞品情报/2026-10-29-规格波/律台-桥增强三式规格.md §式三：
// Windows npm 全局安装的命令是 .cmd 包装脚本，长提示词经 cmd.exe 无法可靠
// 转义（换行/引号/& 等）——绕开 cmd.exe，解析包装脚本后用 node 直跑目标。
// 机制等量吸收律台 lib/cli.js:88-120（MIT，lawdesk 0.4.2，行为级对齐零复制）。
//
// 消费面（RE-43 Codex 交接路前置件；当前桥链路已免疫——桥进程=execPath 直跑，
// desktopHostProcess.ts:195-208）：本文件只做 发现/解析/分派/环境/收尾 五件事，
// 不 spawn 任何真实 CLI（调用方拿 resolveCliCommand 的结果自行派生）。
//
// 纪律：
//  - 参数一律 argv 数组传子进程，禁止拼字符串过 shell（spawnCli 强制 shell:false
//    + 数组参数；对齐规格 §式三 我方规格 3）。
//  - 解析失败 fail-closed 具名报错（cli_shim_*，含包装路径与原因），绝不回落
//    cmd.exe 兜底（规格 §式三 我方规格 4）。
//  - 环境剥离：子进程不继承桥/产品服务的凭据与会话注入变量；PATH 重建补齐
//    npm 全局目录（规格 §式三 我方规格 5，同构律台 §机制 5）。
// 纯 Node 零依赖。自测=tools/bridge/cli_shim_synthetic.mjs（ci_gate fast 随行步）。
import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { basename, dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const CLI_SHIM_VERSION = "1";

// 宿主注入变量剥离表：桥自注入的 runtime 凭据（BRIDGE_OC28_*）与产品服务
// 凭据（JUSBENCH_AGENT_*）绝不外泄给第三方 CLI 子进程；ELECTRON_RUN_AS_NODE
// 是宿主 Electron 标记，带进子进程会让经 electron 路径的 node 直跑变形。
const STRIP_ENV_EXACT = new Set([
  "BRIDGE_OC28_URL", "BRIDGE_OC28_PASSWORD", "BRIDGE_OC28_SSE",
  "JUSBENCH_AGENT_TOKEN", "JUSBENCH_AGENT_USERNAME",
  "JUSBENCH_AGENT_PASSWORD", "ELECTRON_RUN_AS_NODE",
]);
const STRIP_ENV_PREFIXES = ["BRIDGE_OC28_", "JUSBENCH_AGENT_"];

// Windows 可执行扩展序（规格 §式三 我方规格 1：按 .exe/.cmd/.bat/.com 序试）。
const WIN_EXE_EXTS = [".exe", ".cmd", ".bat", ".com"];
// shim 包装里可直跑的 node 脚本入口（优先级降序）与二级包装（剔除）。
const JS_ENTRY_EXTS = [".js", ".mjs", ".cjs"];
const SECONDARY_WRAPPER_EXTS = new Set([".cmd", ".bat", ".ps1"]);

export class CliShimError extends Error {
  constructor(code, detail) {
    super(code + (detail ? ": " + JSON.stringify(detail) : ""));
    this.name = "CliShimError";
    this.code = code;
    this.detail = detail ?? null;
  }
}

const IS_WIN = process.platform === "win32";
const hasExt = (name) => /\.[a-z0-9]+$/i.test(name);

// ── 1. 路径发现：显式配置优先 → PATH 探测 ──────────────────────────────
function searchPath(name, env) {
  const pathVar = (env ?? process.env).PATH ?? (IS_WIN ? process.env.Path : undefined) ?? "";
  for (const dir of pathVar.split(IS_WIN ? ";" : ":")) {
    if (!dir) continue;
    const candidates = hasExt(name) ? [name] : WIN_EXE_EXTS.map((e) => name + e);
    for (const cand of candidates) {
      const full = join(dir, cand);
      if (existsSync(full)) return full;
    }
  }
  return null;
}

export function findCliExecutable(name, { explicitPath, env } = {}) {
  if (explicitPath) {
    if (!isAbsolute(explicitPath)) {
      throw new CliShimError("cli_shim_explicit_path_must_be_absolute", { explicitPath });
    }
    if (!existsSync(explicitPath)) {
      throw new CliShimError("cli_shim_explicit_path_missing", { explicitPath });
    }
    return explicitPath;
  }
  const found = searchPath(name, env);
  if (!found) throw new CliShimError("cli_shim_not_found_on_path", { name });
  return found;
}

// ── 2. shim 解析：从 .cmd/.bat 包装文本提取 dp0 相对目标引用 ─────────────
// 同构律台 §机制 2：正则取引号内 dp0 相对目标；剔 node.exe 解释器自身与
// .cmd/.bat/.ps1 二级包装；优先 .js/.mjs/.cjs 入口，退而取首个目标。
// 真实垫片两形态（2026-10-30 真模型轮实掘）：内联 "%~dp0\目标"（npm 经典）
// 与变量 "%dp0%\目标"（hermes npm 布局真 codex.cmd 实测形态——上轮解析器
// 只认前者，真 codex.cmd fail-closed 在案，本轮补齐）。
const DP0_TARGET_RE = /"%(?:~dp0|dp0%)[\\/]([^"]+)"/gi;

export function parseCmdShim(wrapperPath) {
  const wrapperDir = dirname(wrapperPath);
  let text;
  try {
    text = readFileSync(wrapperPath, "utf-8");
  } catch (e) {
    throw new CliShimError("cli_shim_wrapper_unreadable", { wrapperPath, reason: String(e?.message ?? e) });
  }
  const targets = [];
  DP0_TARGET_RE.lastIndex = 0;
  let m;
  while ((m = DP0_TARGET_RE.exec(text)) !== null) targets.push(m[1]);
  const extOfSegment = (t) => { const e = t.match(/\.([a-z0-9]+)$/i); return e ? "." + e[1].toLowerCase() : ""; };
  const droppedInterpreter = targets.filter((t) => /(^|[\\/])node\.exe$/i.test(t));
  const droppedSecondary = targets.filter((t) => SECONDARY_WRAPPER_EXTS.has(extOfSegment(t)));
  const real = targets.filter((t) => !droppedInterpreter.includes(t) && !droppedSecondary.includes(t));
  const pick = real.find((t) => JS_ENTRY_EXTS.includes(extOfSegment(t))) ?? real[0];
  if (!pick) {
    throw new CliShimError("cli_shim_unparseable", {
      wrapperPath,
      reason: "包装内无可直跑目标（仅解释器/二级包装引用或零 %~dp0 引用）",
      targets,
    });
  }
  const targetPath = resolve(wrapperDir, pick);
  if (!existsSync(targetPath)) {
    throw new CliShimError("cli_shim_target_missing", { wrapperPath, targetPath });
  }
  return { targetPath, droppedInterpreter, droppedSecondary, allTargets: targets };
}

// ── 3. 分派：.exe 直跑；否则 node <目标脚本> 直跑（绝不经 cmd.exe） ──────
// node 解释器优先序：包装同目录 node.exe → 当前 process.execPath（仅当其本身
// 就是 node）→ PATH 上的 node（Windows spawn 数组参数可命中 PATH 里的 .exe）。
export function resolveNodeExecutable(preferDir) {
  const sameDirNode = preferDir ? join(preferDir, "node.exe") : null;
  if (sameDirNode && existsSync(sameDirNode)) return sameDirNode;
  if (/^node(\.exe)?$/i.test(basename(process.execPath))) return process.execPath;
  return "node";
}

function extOf(p) {
  const m = p.match(/\.([a-z0-9]+)$/i);
  return m ? "." + m[1].toLowerCase() : "";
}

export function resolveCliCommand(name, { explicitPath, env } = {}) {
  const executable = findCliExecutable(name, { explicitPath, env });
  const ext = extOf(executable);
  if (ext === ".cmd" || ext === ".bat") {
    const { targetPath, droppedInterpreter, droppedSecondary } = parseCmdShim(executable);
    const targetExt = extOf(targetPath);
    if (targetExt === ".exe") {
      return { origin: "shim-exe", command: targetPath, argsPrefix: [], wrapperPath: executable, targetPath };
    }
    const nodeRun = resolveNodeExecutable(dirname(executable));
    return {
      origin: "shim-node",
      command: nodeRun,
      argsPrefix: [targetPath],
      wrapperPath: executable,
      targetPath,
      droppedInterpreter,
      droppedSecondary,
    };
  }
  if (JS_ENTRY_EXTS.includes(ext)) {
    return { origin: "node-script", command: resolveNodeExecutable(null), argsPrefix: [executable], wrapperPath: null, targetPath: executable };
  }
  if (ext === ".exe" || ext === ".com" || !IS_WIN) {
    return { origin: "direct", command: executable, argsPrefix: [], wrapperPath: null, targetPath: executable };
  }
  throw new CliShimError("cli_shim_unsupported_executable_kind", { executable, ext });
}

// ── 4. 派生：唯一合法 spawn 口（argv 数组 + shell:false + 剥离后环境） ───
export function buildChildEnv(parentEnv = process.env) {
  const env = {};
  for (const [k, v] of Object.entries(parentEnv)) {
    if (STRIP_ENV_EXACT.has(k)) continue;
    if (STRIP_ENV_PREFIXES.some((p) => k.startsWith(p))) continue;
    env[k] = v;
  }
  const sep = IS_WIN ? ";" : ":";
  const npmGlobal = process.env.APPDATA ? join(process.env.APPDATA, "npm") : null;
  const pathKey = Object.keys(env).find((k) => k.toLowerCase() === "path") ?? "PATH";
  const parts = String(env[pathKey] ?? "").split(sep).filter(Boolean);
  if (npmGlobal && !parts.some((p) => p.toLowerCase() === npmGlobal.toLowerCase())) parts.push(npmGlobal);
  env[pathKey] = parts.join(sep);
  return env;
}

export function spawnCli(resolved, args, { cwd, onChild } = {}) {
  if (!Array.isArray(args)) {
    throw new CliShimError("cli_shim_args_must_be_array", { got: typeof args });
  }
  const child = spawn(resolved.command, [...resolved.argsPrefix, ...args], {
    cwd,
    shell: false, // 纪律点：禁拼字符串过 shell（规格 §式三 我方规格 3）
    env: buildChildEnv(),
    windowsHide: true,
  });
  if (onChild) onChild(child);
  return child;
}

// ── 5. 收尾：Windows 杀进程树（taskkill /T /F；杀直接子进程杀不掉孙进程） ──
export function stopTree(pid) {
  if (!Number.isInteger(pid) || pid <= 0) {
    throw new CliShimError("cli_shim_stop_pid_invalid", { pid });
  }
  if (IS_WIN) {
    const r = spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { timeout: 15000 });
    return r.status === 0;
  }
  try { process.kill(pid, "SIGTERM"); return true; } catch { return false; }
}

// └ CLI 直跑探活口（UNKNOWN-2 兜底：codex 路参数漂移不硬编，--version 探测）。
export function probeCliVersion(resolved, timeoutMs = 20000) {
  const r = spawnSync(resolved.command, [...resolved.argsPrefix, "--version"], {
    timeout: timeoutMs, encoding: "utf-8", shell: false, env: buildChildEnv(), windowsHide: true,
  });
  return { ok: r.status === 0, status: r.status, stdout: String(r.stdout ?? "").trim(), stderr: String(r.stderr ?? "").trim() };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  // 极简 CLI 面：node cli_shim.mjs resolve <name|--path=...>（诊断用；解析失败 exit 2 具名）。
  const arg = process.argv[3];
  try {
    const resolved = resolveCliCommand(process.argv[2], arg?.startsWith("--path=") ? { explicitPath: arg.slice("--path=".length) } : {});
    console.log(JSON.stringify(resolved, null, 2));
  } catch (e) {
    if (e instanceof CliShimError) { console.error(e.message); process.exit(2); }
    throw e;
  }
}
