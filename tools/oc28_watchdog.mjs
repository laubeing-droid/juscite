#!/usr/bin/env node
// oc28 守护脚本（施工波三轮 20261031 · 桥健③）。
// 根因结论（证据链见 docs/evidence/施工波三轮-20261031/oc28-一日两死根因.md）：
//   2026-10-30 两死均=宿主机电源事件（①10-29 22:58 用户计划关机=Event 1074/6006；
//   ②10-30 17:23:53 异常关机=Event 6008，17:58:37 重启），oc28 自身日志零 ERROR、
//   死前签名（location services evicted+watcher stopped）与幸存实例完全一致=良性闲置驱逐。
//   用户态脚本无法防断电，只能「探活→自动重拉」缩短不可用窗。
// 授权边界（开工提示词·oc28 自愈授权）：只拉不杀；:43127 探活无监听才重拉；
//   拉起后 service.json 覆盖 service-local.json。绝不 taskkill 任何进程。
// 用法：
//   node tools/oc28_watchdog.mjs                # 一次探活：活着=exit 0 不动；死了=重拉+等就绪
//   node tools/oc28_watchdog.mjs --watch 30     # 常驻循环：每 30s 探活（Ctrl-C 退出）
//   node tools/oc28_watchdog.mjs --selftest     # 隔离自测：临时 XDG+隔离端口 43990 拉一个
//                                              # 一次性实例验证「探活→拉起→就绪→覆盖」全链，
//                                              # 自测实例结束（只终止本脚本拉起的 PID，先验其
//                                              # 命令行含 --port 43990 才动手）；常驻 :43127 零触碰。
// 开机自启登记（需用户裁决，不代登）：
//   schtasks /Create /TN "Juscite oc28 watchdog" /SC ONSTART /RU <用户名> /TR "node /D:\...\tools\oc28_watchdog.mjs --watch 60"
import { spawn, spawnSync, execSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, openSync, readFileSync, rmSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import net from "node:net";

const OC28_EXE = "D:\\Codex\\1.法律工作区\\jusbench工作区\\oc28\\packages\\desktop\\resources\\opencode-cli.exe";
const PORT = Number(process.env.OC28_WATCHDOG_PORT || 43127);
const JUSCITE = join(homedir(), "AppData", "Roaming", "Juscite");
const LOGDIR = join(JUSCITE, "logs");
const STATE_DIR = join(JUSCITE, "state", "opencode");

function log(line) { console.log(`[oc28-watchdog ${new Date().toISOString()}] ${line}`); }

function xdgEnv(root) {
  return {
    XDG_STATE_HOME: join(root, "state"),
    XDG_CONFIG_HOME: join(root, "config"),
    XDG_DATA_HOME: join(root, "data"),
    XDG_CACHE_HOME: join(root, "data", "cache"),
    OPENCODE_DISABLE_MODELS_FETCH: "1",
  };
}

/** TCP 探活：端口有无监听（不碰 HTTP 凭据，只判「有人听」）。 */
function portListening(port) {
  return new Promise((resolve) => {
    const s = net.connect({ port, host: "127.0.0.1", timeout: 1500 });
    s.on("connect", () => { s.destroy(); resolve(true); });
    s.on("error", () => resolve(false));
    s.on("timeout", () => { s.destroy(); resolve(false); });
  });
}

/** 拉起（只拉不杀）：detached spawn，stdout/err 落既有命名法的 relaunch 日志（UTC 戳）。 */
function relaunch({ port = PORT, xdgRoot = JUSCITE, logNamePrefix = "oc28-serve-relaunch" } = {}) {
  mkdirSync(LOGDIR, { recursive: true });
  const now = new Date();
  const stamp = now.toISOString().slice(0, 19).replaceAll(":", "-").replace("T", "-");
  const logPath = join(LOGDIR, `${logNamePrefix}-${stamp}.log`);
  const out = openSync(logPath, "a");
  const err = openSync(logPath, "a");
  const child = spawn(OC28_EXE, ["serve", "--service", "--hostname", "127.0.0.1", "--port", String(port)], {
    detached: true,
    stdio: ["ignore", out, err],
    env: { ...process.env, ...xdgEnv(xdgRoot) },
  });
  child.unref();
  log(`已拉起 pid=${child.pid} port=${port} 日志=${logPath}`);
  return { pid: child.pid, logPath };
}

/** 等 service.json 出现/刷新且其 url 端口=目标（就绪凭据面），随后 service.json→service-local.json。 */
async function waitRegistration({ timeoutMs = 30_000, port = PORT, xdgRoot = JUSCITE, apply = true } = {}) {
  const serviceJson = join(xdgRoot, "state", "opencode", "service.json");
  const serviceLocal = join(xdgRoot, "state", "opencode", "service-local.json");
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (existsSync(serviceJson)) {
      try {
        const reg = JSON.parse(readFileSync(serviceJson, "utf-8"));
        if (reg?.url && reg.url.includes(`:${port}`)) {
          if (apply) copyFileSync(serviceJson, serviceLocal); // 授权口径：拉起后 service.json 覆盖 service-local.json
          log(`就绪 url=${reg.url}（service.json→service-local.json ${apply ? "已覆盖" : "未覆盖(自测)"}）`);
          return reg;
        }
      } catch { /* 注册文件写一半=再等下一轮 */ }
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`service.json ${timeoutMs}ms 内未就绪（port=${port}）`);
}

async function ensureAlive({ port = PORT, xdgRoot = JUSCITE } = {}) {
  if (await portListening(port)) { log(`:${port} 在听——无需动作（只探不杀）`); return { wasAlive: true }; }
  log(`:${port} 无监听——按自愈授权重拉（只拉不杀）`);
  const { pid } = relaunch({ port, xdgRoot });
  const reg = await waitRegistration({ port, xdgRoot });
  if (!(await portListening(port))) throw new Error("拉起后端口仍无监听");
  return { wasAlive: false, pid, reg };
}

/** 自测：隔离 XDG 根+隔离端口拉一次性实例，验「拉起→就绪→覆盖→探活」全链后只收自己拉的那个 PID。 */
async function selftest() {
  const port = 43990;
  const tmp = join(tmpdir(), `oc28-watchdog-selftest-${Date.now()}`);
  mkdirSync(join(tmp, "state"), { recursive: true });
  log(`自测开始：隔离端口 :${port}，隔离 XDG 根 ${tmp}（常驻 :43127 零触碰）`);
  if (await portListening(port)) throw new Error(`:${port} 已被占用，自测端口冲突`);
  const { pid } = relaunch({ port, xdgRoot: tmp, logNamePrefix: "oc28-watchdog-selftest" });
  const reg = await waitRegistration({ port, xdgRoot: tmp, apply: false });
  const ok = (await portListening(port)) && reg.url.includes(`:${port}`);
  log(`自测探活=${ok ? "PASS" : "FAIL"}（url=${reg.url}）`);
  // 收尾：只终止本脚本拉起的 PID，且动手前先验其命令行确含 --port 43990（防误伤）
  try {
    const cmd = String(execSync(
      `powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}').CommandLine"`,
      { encoding: "utf-8" })).trim();
    if (cmd.includes("opencode-cli.exe") && cmd.includes(`--port ${port}`)) {
      spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"]);
      log(`自测实例 pid=${pid} 已收（命令行核验含 --port ${port} 后才动手；常驻 :43127 未触碰）`);
    } else {
      log(`自测实例 pid=${pid} 命令行核验不符（${cmd.slice(0, 120)}）——不动手，留待人工收`);
      return 2;
    }
  } catch (e) {
    log(`自测实例收尾异常（pid=${pid} 可能已自退）：${e?.message ?? e}`);
  }
  try { rmSync(tmp, { recursive: true, force: true }); } catch { /* 临时目录残留无害 */ }
  return ok ? 0 : 1;
}

async function main() {
  const args = process.argv.slice(2);
  if (args.includes("--selftest")) process.exit(await selftest());
  const watchIdx = args.indexOf("--watch");
  if (watchIdx >= 0) {
    const interval = Math.max(5, Number(args[watchIdx + 1] || 60));
    log(`常驻模式：每 ${interval}s 探活 :${PORT}（只拉不杀；Ctrl-C 退出）`);
    for (;;) {
      try { await ensureAlive({}); } catch (e) { log(`本轮失败：${e?.message ?? e}（下轮重试）`); }
      await new Promise((r) => setTimeout(r, interval * 1000));
    }
  }
  try {
    const r = await ensureAlive({});
    process.exit(0);
  } catch (e) {
    log(`失败：${e?.message ?? e}`);
    process.exit(1);
  }
}

main().catch((e) => { log(`致命：${e?.message ?? e}`); process.exit(1); });
