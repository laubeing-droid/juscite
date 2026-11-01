#!/usr/bin/env node
// 【桥·增强三式·式三】CLI shim 解析器合成自测（ci_gate fast 随行步）。
// 唯一依据=律台-桥增强三式规格.md §式三 验收断言①-④（全部合成材料）：
//   ① 合成 .cmd fixture（含 %~dp0\node.exe 干扰项与 js 目标）→解析出正确 js
//      入口且以 node 直跑（不经 cmd.exe）；
//   ② 含换行/引号/& 的长合成提示词经该路送达子进程字节无损（argv 往返比对）；
//   ③ 解析失败→具名报错且零 shell 回落（无 cmd.exe 兜底径）；
//   ④ 杀停止→无残留孙进程（taskkill /T 树杀）。
// 补充：PATH 发现扩展名序（.exe 先于 .cmd）、环境剥离（桥凭据不外泄+PATH 补
// npm 全局目录）、--version 探活兜底（规格 UNKNOWN-2）、%dp0% 变量形态包装
// 解析（⑨，真 codex.cmd 实掘形态）。纯 Node 零新依赖、零端口占用；单命令
// exit 0/1，末行 CLI_SHIM_SYNTH_PASS 可判。
// 用法：node tools/bridge/cli_shim_synthetic.mjs
import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { CliShimError, buildChildEnv, probeCliVersion, resolveCliCommand, spawnCli, stopTree } from "./cli_shim.mjs";

let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[clishim-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[clishim-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const scratch = mkdtempSync(join(tmpdir(), "juscite-clishim-"));
const binDir = join(scratch, "bin");
const pkgBin = join(binDir, "node_modules", "synth-tool", "bin");
mkdirSync(pkgBin, { recursive: true });

// ── fixtures：npm 风格 .cmd 包装（含 node.exe 干扰项）+ js 目标 ──
const targetJs = join(pkgBin, "tool.js");
writeFileSync(targetJs, `#!/usr/bin/env node
import { writeFileSync } from "node:fs";
const [outFile, payload] = process.argv.slice(2);
if (outFile === "--version-probe") { console.log("synth-tool 0.9.9"); process.exit(0); }
if (outFile === "--version") { console.log("synth-tool 0.9.9"); process.exit(0); }
writeFileSync(outFile, JSON.stringify({
  argv: process.argv.slice(2),
  node: process.argv[0],
  script: process.argv[1],
  leaked: Object.keys(process.env).filter((k) => /^(BRIDGE_OC28_|JUSBENCH_AGENT_|ELECTRON_RUN_AS_NODE)/.test(k)),
  pathHasNpmGlobal: String(process.env.PATH ?? "").toLowerCase().split(";").includes(String(process.env.APPDATA ?? "").toLowerCase() + "\\\\npm"),
}));
console.log("TOOL_DONE");
`);
writeFileSync(join(binDir, "synthtool.cmd"), `@ECHO off
IF EXIST "%~dp0\\node.exe" (
  SET "_prog=%~dp0\\node.exe"
) ELSE (
  SET "_prog=node"
)
"%_prog%"  "%~dp0\\node_modules\\synth-tool\\bin\\tool.js" %*
`);
// %dp0% 变量形态包装（hermes npm 布局真 codex.cmd 同构，2026-10-30 真模型轮
// 实掘形态：SET dp0=%~dp0 后引 "%dp0%\目标"——上轮解析器只认 %~dp0 内联形态）。
writeFileSync(join(binDir, "synthtooldp0.cmd"), `@ECHO off
GOTO start
:find_dp0
SET dp0=%~dp0
EXIT /b
:start
SETLOCAL
CALL :find_dp0
IF EXIST "%dp0%\\node.exe" (
  SET "_prog=%dp0%\\node.exe"
) ELSE (
  SET "_prog=node"
)
"%_prog%"  "%dp0%\\node_modules\\synth-tool\\bin\\tool.js" %*
`);
// 只有解释器/二级包装引用的坏包装（③ 解析失败两形态）+ 目标缺失形态。
writeFileSync(join(binDir, "onlyinterpreter.cmd"), `@ECHO off
"%~dp0\\node.exe" "%~dp0\\inner.cmd" %*
`);
writeFileSync(join(binDir, "nodp0.cmd"), "@ECHO off\r\necho no references here\r\n");
writeFileSync(join(binDir, "missingtarget.cmd"), `@ECHO off
"%_prog%"  "%~dp0\\node_modules\\synth-tool\\bin\\gone.js" %*
`);
// PATH 发现序 fixtures：同名 .exe（占位文本，不执行）+.cmd 并存 → .exe 先中。
const orderDir = join(scratch, "order");
mkdirSync(orderDir, { recursive: true });
writeFileSync(join(orderDir, "ordercli.exe"), "placeholder-not-executed");
writeFileSync(join(orderDir, "ordercli.cmd"), `@ECHO off\r\n"%_prog%" "%~dp0\\tool.js" %*\r\n`);
// ④ 树杀 fixtures：runner 直跑→孙进程心跳。
const heartbeat = join(scratch, "grandchild-heartbeat.txt");
writeFileSync(join(scratch, "grandchild.js"), `import { writeFileSync } from "node:fs";
const f = process.argv[2];
setInterval(() => writeFileSync(f, process.pid + " " + Date.now()), 300);
`);
writeFileSync(join(scratch, "runner.js"), `import { spawn } from "node:child_process";
const g = spawn(process.execPath, [process.argv[2], process.argv[3]], { stdio: "ignore" });
g.on("exit", () => process.exit(0));
setInterval(() => {}, 1e9);
`);

function readJson(file) { return JSON.parse(readFileSync(file, "utf-8")); }
async function waitFile(file, ms) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    try { statSync(file); return true; } catch { await sleep(150); }
  }
  return false;
}
async function pidAlive(pid) {
  const { spawnSync } = await import("node:child_process");
  const r = spawnSync("tasklist", ["/FI", `PID eq ${pid}`, "/FO", "CSV", "/NH"], { encoding: "utf-8", timeout: 15000 });
  return String(r.stdout ?? "").includes(String(pid));
}

try {
  // ① shim 解析：node.exe 干扰项剔除，js 入口命中，node 直跑（origin=shim-node，
  //    command 绝非 .cmd/.exe 包装本身）。
  let resolved;
  try {
    resolved = resolveCliCommand("synthtool", { explicitPath: join(binDir, "synthtool.cmd") });
    if (resolved.origin === "shim-node" && resolved.targetPath === targetJs
      && !/\.cmd$/i.test(resolved.command) && resolved.argsPrefix.length === 1) {
      ok(1, `.cmd shim 解析出 js 入口并以 node 直跑（target=${resolved.targetPath}，剔除干扰 ${resolved.droppedInterpreter.length} 项）`);
    } else fail(1, "shim 解析形态不符", JSON.stringify(resolved));
  } catch (e) { fail(1, "解析抛错", String(e?.message ?? e)); }

  // ② 长合成提示词字节无损：换行/单双引号/反引号/&/^/|/%/!/<>/长串，经
  //    spawnCli argv 数组往返比对。
  const nasty = [
    "第一行：甲 & 乙 ^ 丙 | 丁 < 戊 > 己 %己% !庚!",
    'quote " inside \' and `backtick` — line1\nline2\ttab — 中文引号“”‘’',
    "x".repeat(8192) + "\n&tail",
  ];
  const outFile = join(scratch, "case2-out.json");
  const child2 = spawnCli(resolved, [outFile, ...nasty], { cwd: scratch });
  let toolDone = false;
  child2.stdout.on("data", (d) => { if (String(d).includes("TOOL_DONE")) toolDone = true; });
  const done2 = await Promise.race([
    (async () => { while (!toolDone) await sleep(100); return true; })(),
    new Promise((r) => setTimeout(() => r(false), 30000)),
  ]);
  if (done2 && await waitFile(outFile, 5000)) {
    const got = readJson(outFile);
    const eq = JSON.stringify(got.argv.slice(1)) === JSON.stringify(nasty);
    eq ? ok(2, `长合成提示词 argv 字节无损往返（${nasty[2].length + nasty[0].length + nasty[1].length}+ 字符含换行/引号/&）`)
      : fail(2, "argv 往返不等", `got=${JSON.stringify(got.argv).slice(0, 200)}`);
  } else fail(2, "子进程未落盘/超时", `done=${done2}`);

  // ③ 解析失败 fail-closed 具名 + 零 shell 回落：三种坏包装各得具名码；
  //    spawnCli 拒绝字符串参数（禁止拼串过 shell 的机械形态）。
  const badCases = [
    [join(binDir, "onlyinterpreter.cmd"), "cli_shim_unparseable"],
    [join(binDir, "nodp0.cmd"), "cli_shim_unparseable"],
    [join(binDir, "missingtarget.cmd"), "cli_shim_target_missing"],
  ];
  let badAll = true;
  for (const [p, wantCode] of badCases) {
    try {
      resolveCliCommand("x", { explicitPath: p });
      fail(3, `坏包装未拒: ${p}`, "resolve 未抛错"); badAll = false;
    } catch (e) {
      if (e instanceof CliShimError && e.code === wantCode && e.detail?.wrapperPath === p) continue;
      fail(3, `坏包装错误码不符: ${p}`, `${e?.code ?? e?.message} detail=${JSON.stringify(e?.detail)?.slice(0, 120)}`); badAll = false;
    }
  }
  try { spawnCli(resolved, "不是数组"); fail(3, "字符串参数未拒", "spawnCli 接受了字符串"); badAll = false; } catch (e) {
    if (!(e instanceof CliShimError && e.code === "cli_shim_args_must_be_array")) { fail(3, "字符串参数错误码不符", String(e?.code)); badAll = false; }
  }
  if (badAll) ok(3, "解析失败三类具名报错（含包装路径）+字符串参数拒绝＝零 cmd.exe 兜底");

  // ④ 树杀无残留孙进程：runner(直子)→grandchild(孙)心跳，stopTree 后孙进程消失。
  const child4 = spawnCli(
    { origin: "node-script", command: process.execPath, argsPrefix: [join(scratch, "runner.js")], wrapperPath: null, targetPath: join(scratch, "runner.js") },
    [join(scratch, "grandchild.js"), heartbeat],
    { cwd: scratch },
  );
  if (await waitFile(heartbeat, 15000)) {
    const grandPid = Number(readFileSync(heartbeat, "utf-8").split(" ")[0]);
    await sleep(800); // 孙进程持续心跳中
    const killed = stopTree(child4.pid);
    let gone = false;
    for (let i = 0; i < 40 && !gone; i++) { await sleep(250); gone = !(await pidAlive(grandPid)); }
    killed && gone ? ok(4, `树杀无残留孙进程（直子 ${child4.pid}→孙 ${grandPid} 均终止）`)
      : fail(4, "孙进程残留", `killed=${killed} grandPid=${grandPid} alive=${await pidAlive(grandPid)}`);
  } else fail(4, "孙进程心跳未起", heartbeat);

  // ⑤ PATH 发现序：同名 .exe 先于 .cmd（占位 .exe 命中=direct，未误入 cmd 包装）。
  const orderEnv = { ...process.env, PATH: [orderDir, process.env.PATH ?? process.env.Path].join(";") };
  try {
    const found = resolveCliCommand("ordercli", { env: orderEnv });
    found.origin === "direct" && found.command === join(orderDir, "ordercli.exe")
      ? ok(5, "PATH 发现按 .exe→.cmd 序命中（.exe 先中，未落 cmd 包装）")
      : fail(5, "发现序不符", JSON.stringify({ origin: found.origin, command: found.command }));
  } catch (e) { fail(5, "PATH 发现抛错", String(e?.message ?? e)); }

  // ⑥ 环境剥离：桥/runtime 凭据零外泄 + PATH 重建补 npm 全局目录。
  const stripParent = { ...process.env, BRIDGE_OC28_PASSWORD: "synth-secret", JUSBENCH_AGENT_TOKEN: "synth-token", ELECTRON_RUN_AS_NODE: "1" };
  const env = buildChildEnv(stripParent);
  const stripped = env.BRIDGE_OC28_PASSWORD === undefined && env.JUSBENCH_AGENT_TOKEN === undefined && env.ELECTRON_RUN_AS_NODE === undefined;
  const npmGlobal = join(process.env.APPDATA ?? "", "npm");
  const pathHas = String(env.PATH ?? "").toLowerCase().split(";").includes(npmGlobal.toLowerCase());
  stripped && pathHas ? ok(6, `环境剥离（3 变量不外泄）+PATH 补 npm 全局目录（${npmGlobal}）`)
    : fail(6, "环境剥离/PATH 不符", `stripped=${stripped} pathHas=${pathHas}`);
  const outFile6 = join(scratch, "case6-out.json");
  const child6 = spawnCli(resolved, [outFile6, "x"], { cwd: scratch });
  await new Promise((r) => child6.on("exit", r));
  if (await waitFile(outFile6, 5000)) {
    const leak = readJson(outFile6).leaked;
    (Array.isArray(leak) && leak.length === 0) ? ok(7, "子进程实测零凭据键继承（BRIDGE_OC28_*/JUSBENCH_AGENT_*/ELECTRON_RUN_AS_NODE）")
      : fail(7, "子进程环境外泄", JSON.stringify(leak));
  } else fail(7, "子进程未落盘", outFile6);

  // ⑧ --version 探活（UNKNOWN-2 兜底：CLI 参数面漂移不硬编，探测优先）。
  const probe = probeCliVersion(resolved);
  probe.ok && probe.stdout.includes("synth-tool 0.9.9")
    ? ok(8, `--version 探活通（stdout="${probe.stdout}"）`)
    : fail(8, "探活失败", JSON.stringify(probe));

  // ⑨ %dp0% 变量形态包装解析（真 codex.cmd 实掘形态，同构 ①）：SET dp0=%~dp0
  //    +引 "%dp0%\目标"→js 入口命中、node.exe 干扰剔除、node 直跑。
  try {
    const r9 = resolveCliCommand("synthtooldp0", { explicitPath: join(binDir, "synthtooldp0.cmd") });
    r9.origin === "shim-node" && r9.targetPath === targetJs && r9.droppedInterpreter.length === 1
      ? ok(9, `%dp0% 变量形态 shim 解析出 js 入口并以 node 直跑（target=${r9.targetPath}）`)
      : fail(9, "%dp0% 形态解析不符", JSON.stringify(r9));
  } catch (e) { fail(9, "%dp0% 形态解析抛错", String(e?.message ?? e)); }
} catch (e) {
  fail("fatal", String(e?.message ?? e));
} finally {
  try { rmSync(scratch, { recursive: true, force: true }); } catch { /* 尽力而为 */ }
}

console.log(`[clishim-synth] ── ${passed} OK / ${failed} FAIL ──`);
if (failed > 0) { console.error("CLI_SHIM_SYNTH_FAIL"); process.exit(1); }
console.log("CLI_SHIM_SYNTH_PASS");
