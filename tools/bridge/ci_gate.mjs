#!/usr/bin/env node
// Juscite 桥 CI 门禁（施工单-02 任务四 · 第 1 轮）。
// 子模式：
//   fast    = node --check 全部桥 .mjs 源 + UI 合同测试（vitest，sessionsIndexStore+agentV4ConnectionTransports+materialAttachments，期望 76 项）
//             + 桥 e2e（conversation.e2e.mts，期望 22 项全 OK 且末行 E2E_PASS）
//             + 许可骨架三态自测（license_synthetic.mjs，17 用例含桥接线两例，末行 LICENSE_SYNTH_PASS；F78/F79·RE-B3）
//             + 桥内机制件合成自测（施工单-06：taskshell/flow_gate/mechanism_wire 三案 + 桥·增强三式·式三 cli_shim，末行 *_SYNTH_PASS）
//             + 轻量知识图谱合成自测（graph_synthetic.mts，末行 GRAPH_SYNTH_PASS；#19·RE-19）
//             + 可视化面板桥接线合成自测（施工波二轮·可视化B轨 UI 件：vizb_panel_synthetic.mts，
//               面板投影→五工具真桥 RPC，隔离端口 :3093，末行 VIZB_PANEL_SYNTH_PASS）
//             + 监控白名单与宿主降级合成自测（逆向吸收波二·条 2/条 3：monitoring_synthetic.mjs，
//               声明式监控契约+消费面接线+host.use('db'/'user') 两态，隔离端口 :3090 段，
//               末行 MONITORING_SYNTH_PASS）
//             + 品牌二轮门禁（r12 波2 · D5：全品牌正则用户可见字符串零命中 + locale overlay 覆盖断言，
//               豁免表 contracts/brand-exemptions.md；扫描面含 packages/web/src，并含成对标签静态文本）
//   brand   = 只跑品牌二轮门禁（stepBrand）。不拉 vitest/e2e/桥进程。
//   persist = fast + 桥重启不丢案实测（发一句合成消息→杀桥进程→重启→历史会话行完整一致）。
//             默认对 :3030（破坏性：会杀掉在跑的桥再用注册凭据拉起）；--port N 改在门禁自管的独立实例上自测，不碰 :3030。
//   full    = fast + persist（persist 已含 fast，等价 persist，不重跑两遍）。
//   package = 打包门禁（步骤5 打包单③；RE-B3 §5 放行条件④）。
//             绿口径：仅 Windows NSIS（electron-builder --win --x64 nsis）
//             + 随包桥探针 bridge_bundle_synthetic。Linux 构建或任何 Linux 产物
//             都不得称作 package 门禁绿；本模式须在 Windows 上跑，Linux 上构建成功 ≠ package PASS。
//             步骤：nodecheck（桥 .mjs 语法面）→ license（放行条件④随行）→ 桌面构建
//             （build-metadata → production build(tsup+vite) → electron-builder --win --x64 nsis）
//             → 产物断言（exe/blockmap/latest.yml 存在+新鲜 + app-update.yml 携自家更新源桩
//             + 随包桥探针 bridge_bundle_synthetic：resources/bridge 物化要件与 ELECTRON_RUN_AS_NODE spawn）。
//             vitest/e2e/persist 不随（打包门禁不依赖在跑开发桥与 oc28；回归面由 fast/full 覆盖）。
//   upgrade = 上游升级门禁（r12 波5 · 设计 §五，①→⑤顺序）：
//             ①豁免 patch apply --check（复跑波4 verify-apply-check：9 patch 必须干净打在上游基线树）
//             ②合同面类型快照 diff（重生成 contracts/type-snapshot.json 到临时目录与在库版 diff，
//               被消费 @zcode/* 符号声明形变/增删即爆红——§八原则1 协议真源漂移编译期暴露）
//             ③adapter 行数纪律（全部 adapter ≤ 桥代码 10%，口径=contracts/adapter-budget.md，超限爆红）
//             ④品牌正则全量检查（=fast 的 brand 步，此处按 §五顺序显式占位）
//             ⑤fast 全量（nodecheck/vitest/e2e/license/mech/support/graph/citation；brand 已在④跑不重跑）。
// 用法（内部自行 chdir 仓库根，任意目录可调；推荐工作区根）：
//   node juscite/.local/worktrees/m1-u01/tools/bridge/ci_gate.mjs fast
//   node juscite/.local/worktrees/m1-u01/tools/bridge/ci_gate.mjs persist --port 3055
//   node juscite/.local/worktrees/m1-u01/tools/bridge/ci_gate.mjs upgrade
// 安全：桥 :3030 先探活复用，死了才经 loadCredentials 读注册文件拉起（口令运行时解码传递，不硬编码不入日志）；
//       oc28(:43127) 是用户进程绝不动；杀桥前必须核验 PID 命令行含 bridge_host.mjs，否则拒绝动手。
// 纯 Node，不新增依赖。单命令 exit 0/1 可判（施工单-02 任务四验收口径）。
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, openSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url)); // tools/bridge/ → 仓库根（m1-u01）
process.chdir(REPO_ROOT);
const NODE = process.execPath;
const BRIDGE_DIR = join(REPO_ROOT, "tools", "bridge");
const DESKTOP_DIR = join(REPO_ROOT, "packages", "desktop");
const DESKTOP_DIST = join(DESKTOP_DIR, "dist");
const UPDATE_FEED_STUB = "https://updates.juscite.invalid/"; // 打包单②：自家更新源占位桩
const E2E_CHECKS = 23; // conversation.e2e.mts 的 checks 项数（22 基线 + 任务二 sseDropRecovery）
const VITEST_TESTS = 150; // sessionsIndexStore(基线) + agentV4ConnectionTransports(基线) + materialAttachments(#6 RE-6 对拍面 14+4 项：r8 缺项补齐新增目录拖拽白名单 4 项) + ediscPanelModel(#42 RE-42 §3.3 面板合同 13+6 项：五分区/徽章闭集/行地址/分组/校验可读差异/律师闸+施工波三轮对拍收尾 6 项：F1 四类排除/F2 六要素闭集与缺项/F4 三性闭集/F6 四类缺口行/G5 任务徽章与进度) + toolSecurityPanel(#21 安全层设置面板+审计工具决策 tab 合同 19 项：默认关/yolo 不暴露只留设置键/浅合并写回/策略三分/行守卫/回退链/码表闭集/ui-kit Switch fail-fast) + subscriptionUiContract(#43 RE-43 §2.2 对拍 10-12+§3.5 面合同 32 项：等级集/钳制双端标签/隐藏/pending 零推断/粘性钉住/每面板独立/会话内变更协议/三分支/用量条/组件渲染面)
const VITEST_LEGAL_TESTS = 96; // vizbPanelContract（施工波二轮·可视化B轨 UI 件：大事记投影 10+摄入载荷 2+对抗摘要 2+下载名净化 1）+ skillActivationModel（施工波三轮·#7 全量面：触发通道/分值/预算/上限/双语义/supplemental/注入格式 17）+ deliveryChainModel（施工波三轮·#7 全量面：路径提取/双层过滤/版本族去重/D4 两层短路 15）+ flowStudioModel（施工波三轮·#35 尾巴②：运行七态闭集/未知态灰具名/双来源只读/运行面摘要/关卡冲突回显/AI-run G1-G3 视图/定义普查与发起门槛 14）+ configWriteModel（施工单-10 单元二·结构化写入防御：safe-quote 纯标量 yaml 对拍/键闭集闸含原型键拒/round-trip 键集合零变化 27）+ tabularExportGuard（施工单-10 单元一·CSV 公式注入防御：闭集判定/20 payload 读回首字符 '/金额豁免/干净值零改写/列名同防 8），独立 vitest 配置独立期望

const mode = process.argv[2];
if (!["fast", "persist", "full", "package", "upgrade", "brand"].includes(mode)) {
  console.error("用法: node tools/bridge/ci_gate.mjs <fast|persist|full|package|upgrade|brand> [--port N]");
  process.exit(2);
}
let persistPort = 3030;
const rest = process.argv.slice(3);
for (let i = 0; i < rest.length; i++) {
  if (rest[i] === "--port") { persistPort = Number(rest[i + 1]); i++; }
}
if (!Number.isInteger(persistPort) || persistPort < 1 || persistPort > 65535) {
  console.error(`[ci-gate] 非法端口: ${rest[rest.indexOf("--port") + 1]}`);
  process.exit(2);
}
const stamp = new Date().toISOString().replace(/[:T]/g, "-").slice(0, 19);
const LOGDIR = join(REPO_ROOT, ".local", "ci-gate-logs", `${mode}-${stamp}`);
mkdirSync(LOGDIR, { recursive: true });
log(`日志目录 ${LOGDIR}`);

function log(msg) { console.log(`[ci-gate:${mode}] ${msg}`); }
const stripAnsi = (s) => s.replace(/\x1b\[[0-9;]*m/g, "");

// ── 子进程执行：stdout/stderr 落日志文件，返回文本供断言 ──
function runChild(stepName, args, { timeoutMs = 120000, env, cwd = REPO_ROOT } = {}) {
  const outFile = join(LOGDIR, `${stepName}.log`);
  const fd = openSync(outFile, "a");
  log(`▶ ${stepName}: node ${args.join(" ")} （日志 ${outFile}）`);
  const r = spawnSync(NODE, args, {
    cwd,
    encoding: "buffer",
    maxBuffer: 64 * 1024 * 1024,
    timeout: timeoutMs,
    env: env ?? process.env,
    stdio: ["ignore", fd, fd], // 输出全量落日志文件，stdout/stderr 管道不占内存
  });
  let out = "";
  try { out = readFileSync(outFile, "utf-8"); } catch { /* 文件缺失按空处理 */ }
  return { status: r.status, error: r.error?.message ?? "", out, outFile };
}
function childTail(stepName, n = 3000) {
  try { return readFileSync(join(LOGDIR, `${stepName}.log`), "utf-8").slice(-n); } catch { return "(无日志)"; }
}

// ── 桥生命周期：探活复用；死了才经 loadCredentials 拉起；oc28 绝不动 ──
function httpProbe(port, path = "/api/server-info", timeoutMs = 2500) {
  return fetch(`http://127.0.0.1:${port}${path}`, { signal: AbortSignal.timeout(timeoutMs) })
    .then((r) => r.ok)
    .catch(() => false);
}
function findListenerPid(port) {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const pids = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === port) pids.add(Number(m[2]));
  }
  return [...pids];
}
// 杀桥前核验：目标 PID 命令行必须含 bridge_host.mjs（防误杀 oc28/无关进程）
function commandLineLooksLikeBridge(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  const line = String(r.stdout ?? "").trim();
  return line.includes("bridge_host.mjs");
}
function bridgeChildEnv() {
  // 不注入凭据：子桥进程自己的 loadCredentials 每请求重读注册文件（oc28 重启换口令也自愈）；
  // 若操作者显式设了 BRIDGE_OC28_* 环境变量则原样透传（固定凭据直连语义不变）。
  return { ...process.env };
}
function spawnBridgeProcess(port, tag) {
  const env = bridgeChildEnv();
  env.BRIDGE_PORT = String(port);
  const fd = openSync(join(LOGDIR, `bridge-${tag}.log`), "a");
  const child = spawn(NODE, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")], {
    cwd: REPO_ROOT, env, stdio: ["ignore", fd, fd], detached: true,
  });
  child.unref();
  log(`桥已拉起 pid=${child.pid} port=${port}（凭据经子进程 loadCredentials 读注册文件，不入日志）`);
  return child.pid;
}
async function waitProbe(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await httpProbe(port)) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}
// 持久化能力探测：/api/server-info 带 store:"sqlite" 才算新桥（RE-B1 §5 升级代偿）
async function isPersistCapable(port) {
  try {
    const r = await fetch(`http://127.0.0.1:${port}/api/server-info`, { signal: AbortSignal.timeout(2500) });
    return r.ok && JSON.parse(await r.text()).store === "sqlite";
  } catch { return false; }
}
// 复用的桥若是无持久化旧代码：先杀换新（升级代偿），否则 phase1 的数据随旧桥内存蒸发
async function upgradeBridgeIfNeeded(port, pidInfo) {
  if (await isPersistCapable(port)) return pidInfo;
  log(`:${port} 在跑桥无持久化能力（store 标记缺失）→ 杀换新桥再测（升级代偿）`);
  await killBridge(pidInfo.pid, "持久化能力升级");
  const pid = spawnBridgeProcess(port, "upgrade");
  if (!(await waitProbe(port, 40000))) throw new Error(`桥 :${port} 升级后 40s 不可探`);
  return { pid, owned: true };
}
async function killBridge(pid, reason) {
  if (!commandLineLooksLikeBridge(pid)) {
    throw new Error(`拒绝杀进程 pid=${pid}（${reason}）：命令行不含 bridge_host.mjs，不是桥，宁停不误杀`);
  }
  log(`杀桥 pid=${pid}（${reason}）`);
  spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && findListenerPid(persistPort).length > 0) {
    await new Promise((r) => setTimeout(r, 500));
  }
}
async function ensureBridge(port) {
  if (await httpProbe(port)) {
    const pids = findListenerPid(port);
    log(`:3030 探活复用 → :${port} 活着（pid=${pids.join(",") || "?"}），不重启`);
    return { pid: pids[0], owned: false };
  }
  if (port !== 3030 && findListenerPid(port).length > 0) {
    throw new Error(`:${port} 被非桥进程占用且 /api/server-info 不应答，不接触`);
  }
  const pid = spawnBridgeProcess(port, `ensure-${port}`);
  if (!(await waitProbe(port, 40000))) throw new Error(`桥 :${port} 拉起后 40s 不可探（见 bridge-ensure 日志）`);
  return { pid, owned: true };
}

// ── 步骤 1：node --check 全部桥 .mjs 源（排除 .bak 与 node_modules）──
function stepNodecheck() {
  const files = readdirSync(BRIDGE_DIR)
    .filter((f) => f.endsWith(".mjs") && !f.includes(".bak"))
    .sort();
  const bad = [];
  for (const f of files) {
    const r = spawnSync(NODE, ["--check", join("tools", "bridge", f)], { cwd: REPO_ROOT, encoding: "utf-8", timeout: 30000 });
    if (r.status !== 0) { bad.push(f); log(`  ✗ ${f}\n${String(r.stderr ?? "")}`); }
    else log(`  ✓ node --check ${f}`);
  }
  if (bad.length) return { ok: false, msg: `node --check 失败 ${bad.length}/${files.length}: ${bad.join(",")}` };
  return { ok: true, msg: `node --check ${files.length}/${files.length} 通过` };
}

// ── 步骤 2：UI 合同测试（vitest 五文件，期望数见 VITEST_TESTS）──
function stepVitest() {
  const args = [
    join("node_modules", "vitest", "vitest.mjs"), "run",
    "--config", join("packages", "ui", "vitest.config.ts"),
    // --dir 钉测试发现根：.local 下并行泳道临时校验树（verify-head-*）路径含同名子串，
    // 会被 vitest 位置参数按子串过滤扫入成坏文件（2026-10-28 实测 FAIL 根因，根修）。
    "--dir", join("packages", "ui"),
    // --maxWorkers 1：共享工位并发施工期池 worker 并发冷吊起可挤爆 vitest 内置 60s 启动窗
    // （2026-10-31 fast 首轮实测：五文件 112/112 全过后 subscriptionUiContract 吊起超窗报
    // [vitest-pool-runner] Timeout waiting for worker to respond；vitest 4.1.4 该窗硬编码
    // 不可配），串行吊起消同轮内争（99ec5acd 探针窗放宽同款环境征候，断言面零改动）。
    "--maxWorkers", "1",
    join("packages", "ui", "test", "sessionsIndexStore.test.ts"),
    join("packages", "ui", "test", "agentV4ConnectionTransports.test.ts"),
    join("packages", "ui", "test", "materialAttachments.test.ts"),
    join("packages", "ui", "test", "ediscPanelModel.test.ts"),
    join("packages", "ui", "test", "toolSecurityPanel.test.ts"),
    join("packages", "ui", "test", "subscriptionUiContract.test.tsx"),
  ];
  // 串行吊起后单步窗 300s→600s；仅环境停顿具名特征单次重试，断言失败/计数不符不重试不冒 PASS。
  let r = runChild("vitest", args, { timeoutMs: 600000 });
  if (r.status !== 0 && /\[vitest-pool(-runner)?\]|Timeout waiting for worker to respond/.test(stripAnsi(r.out) + String(r.error ?? ""))) {
    log("  ↻ vitest 池 worker 吊起超窗（共享工位环境停顿特征命中），重试一次");
    r = runChild("vitest", args, { timeoutMs: 600000 });
  }
  if (r.status !== 0) return { ok: false, msg: `vitest exit=${r.status}（期望 0）`, tail: childTail("vitest") };
  // 重试输出 append 进同一 vitest.log（runChild 固定 "a" 开档），判读只认末次尝试的汇总：
  // 2026-11-01 fast 首轮实测——首跑 subscriptionUiContract 吊起超窗 118/150+1 error 触发重试，
  // 重试 150/150 全绿 exit=0，但旧取首匹配 parse 到首跑陈旧 118 误报"通过数 118 ≠ 期望 150"；
  // 改取末次匹配即判重试当轮，两跑证据仍全量留在日志。
  const text = stripAnsi(r.out);
  const m = [...text.matchAll(/Tests\s+(\d+)\s+passed/g)].pop();
  const passed = m ? Number(m[1]) : NaN;
  const failed = [...text.matchAll(/Tests\s.*?(\d+)\s+failed/g)].pop();
  if (Number(failed?.[1] ?? 0) > 0) return { ok: false, msg: `vitest 有失败项`, tail: childTail("vitest") };
  if (passed !== VITEST_TESTS) {
    return { ok: false, msg: `vitest 通过数 ${passed} ≠ 期望 ${VITEST_TESTS}（若为有意增改，请同步本门禁期望值后复跑）`, tail: childTail("vitest") };
  }
  return { ok: true, msg: `vitest UI 合同测试 ${passed}/${VITEST_TESTS} 通过（6 文件）` };
}

// ── 步骤 2b（施工波二轮·可视化B轨 UI 件）：@juscite/legal 面板投影合同测试（独立配置独立期望，
// 不与 ui 包合同面混扫——面板族代码全在自有包，测试不进上游 ui 树）──
function stepVitestLegal() {
  const r = runChild("vitest-legal", [
    join("node_modules", "vitest", "vitest.mjs"), "run",
    "--config", join("packages", "juscite-legal", "vitest.config.ts"),
    "--dir", join("packages", "juscite-legal"),
    join("packages", "juscite-legal", "test", "vizbPanelContract.test.ts"),
    join("packages", "juscite-legal", "test", "skillActivationModel.test.ts"),
    join("packages", "juscite-legal", "test", "deliveryChainModel.test.ts"),
    join("packages", "juscite-legal", "test", "flowStudioModel.test.ts"),
    join("packages", "juscite-legal", "test", "configWriteModel.test.ts"),
    join("packages", "juscite-legal", "test", "tabularExportGuard.test.ts"),
  ], { timeoutMs: 300000 });
  if (r.status !== 0) return { ok: false, msg: `vitest-legal exit=${r.status}（期望 0）`, tail: childTail("vitest-legal") };
  const text = stripAnsi(r.out);
  const m = text.match(/Tests\s+(\d+)\s+passed/);
  const passed = m ? Number(m[1]) : NaN;
  const failed = /Tests\s.*?(\d+)\s+failed/.exec(text);
  if (Number(failed?.[1] ?? 0) > 0) return { ok: false, msg: `vitest-legal 有失败项`, tail: childTail("vitest-legal") };
  if (passed !== VITEST_LEGAL_TESTS) {
    return { ok: false, msg: `vitest-legal 通过数 ${passed} ≠ 期望 ${VITEST_LEGAL_TESTS}（若为有意增改，请同步本门禁期望值后复跑）`, tail: childTail("vitest-legal") };
  }
  return { ok: true, msg: `vitest @juscite/legal 面板合同测试 ${passed}/${VITEST_LEGAL_TESTS} 通过（6 文件）` };
}

// ── 步骤 3：桥 e2e（期望 22 项全 OK + 末行 E2E_PASS）──
async function stepE2E() {
  await ensureBridge(3030); // e2e 写死 ws://localhost:3030/ws
  const r = runChild("e2e", ["--import", "tsx", join("tools", "bridge", "conversation.e2e.mts")], { timeoutMs: 560000 });
  if (r.status !== 0) return { ok: false, msg: `e2e exit=${r.status}（期望 0）`, tail: childTail("e2e") };
  const text = stripAnsi(r.out);
  if (!text.includes("E2E_PASS")) return { ok: false, msg: "e2e 输出无 E2E_PASS 末行", tail: childTail("e2e") };
  const okCount = (text.match(/^\[e2e\] \w+: OK$/gm) ?? []).length;
  if (okCount !== E2E_CHECKS) {
    return { ok: false, msg: `e2e OK 项 ${okCount} ≠ 期望 ${E2E_CHECKS}`, tail: childTail("e2e") };
  }
  return { ok: true, msg: `桥 e2e ${okCount}/${E2E_CHECKS} 项 OK，末行 E2E_PASS` };
}

// ── 步骤 4（persist/full）：桥重启不丢案实测 + 崩溃窗实测 ──
// 常规窗：phase1 发合成消息→杀桥→重启→phase2 逐行对拍（历史一致）。
// 崩溃窗（F1③/F3）：crash 相 sendText ack 后即退（行未完成）→杀桥→重启→replay 相断言
//   ①恢复快照无 running 相位 ②重放同 envelope 后行出现（complete）或显式错误（failed）。
async function stepPersist() {
  const probeEnvBase = process.env; // persist 探针只走桥 WS，不需要 oc28 凭据
  const wsUrl = `ws://127.0.0.1:${persistPort}/ws`;
  const stateFile = join(LOGDIR, "persist-state.json");
  const crashState = join(LOGDIR, "persist-crash-state.json");
  const probeArgs = ["--import", "tsx", join("tools", "bridge", "persist_probe.mts")];

  log(`persist 目标 :${persistPort}${persistPort === 3030 ? "（破坏性实测：会杀掉在跑桥并重启）" : "（独立实例自测，不碰 :3030）"}`);
  let first = await ensureBridge(persistPort);
  first = await upgradeBridgeIfNeeded(persistPort, first); // 旧桥先升级，phase1 数据才落得了库
  let bridgePid = first.pid;
  const cleanup = async () => {
    // 任何出口都收场：独立实例不留孤儿（哪怕中途 FAIL）
    if (persistPort !== 3030) { try { await killBridge(bridgePid, "独立实例清场"); } catch { /* 已死则忽略 */ } }
  };
  try {
    return await runPersistPhases({ first, stateFile, crashState, probeArgs, probeEnvBase, wsUrl, setPid: (p) => { bridgePid = p; }, cleanup });
  } finally {
    await cleanup();
  }
}

async function runPersistPhases({ first, stateFile, crashState, probeArgs, probeEnvBase, wsUrl, setPid }) {
  let bridgePid = first.pid;

  // phase1：发合成消息，落状态
  const r1 = runChild("persist-phase1", [...probeArgs, "phase1", stateFile],
    { timeoutMs: 220000, env: { ...probeEnvBase, BRIDGE_WS_URL: wsUrl } });
  if (r1.status !== 0 || !existsSync(stateFile) || !readFileSync(stateFile, "utf-8").includes("sessionId")) {
    return { ok: false, msg: `persist phase1 失败 exit=${r1.status}`, tail: childTail("persist-phase1") };
  }
  const st = JSON.parse(readFileSync(stateFile, "utf-8"));
  log(`phase1 会话 ${st.sessionId} 已收 ${st.rows.length} 行（seq=${st.seq}）`);

  // 杀桥（自己的实例直接杀；复用的 :3030 先核验命令行再杀）→ 重启 → phase2 对拍
  await killBridge(bridgePid, first.owned ? "门禁自拉实例" : "persist 实测");
  bridgePid = spawnBridgeProcess(persistPort, "persist-restart");
  setPid(bridgePid);
  if (!(await waitProbe(persistPort, 40000))) {
    return { ok: false, msg: "persist 重启桥 40s 不可探", tail: childTail("bridge-persist-restart") };
  }
  const r2 = runChild("persist-phase2", [...probeArgs, "phase2", stateFile],
    { timeoutMs: 90000, env: { ...probeEnvBase, BRIDGE_WS_URL: wsUrl } });
  const pass2 = r2.status === 0 && stripAnsi(r2.out).includes("PERSIST_PASS");
  if (!pass2) {
    return { ok: false, msg: "persist FAIL：重启后历史会话行与重启前不一致", tail: childTail("persist-phase2") };
  }
  log(`phase2 PASS：会话 ${st.sessionId} 重启后 ${st.rows.length} 行完整一致（seq=${st.seq}）`);

  // 崩溃窗：sendText ack 后立刻杀桥 → 重启 → 重放同 envelope 必须行出现或显式错误，且无 running 相位
  const r3 = runChild("persist-crash", [...probeArgs, "crash", crashState],
    { timeoutMs: 60000, env: { ...probeEnvBase, BRIDGE_WS_URL: wsUrl } });
  if (r3.status !== 0 || !existsSync(crashState)) {
    return { ok: false, msg: `persist crash 相失败 exit=${r3.status}`, tail: childTail("persist-crash") };
  }
  const cs = JSON.parse(readFileSync(crashState, "utf-8"));
  log(`crash 相：会话 ${cs.sessionId} sendText ack=${cs.ackStatus} 后杀桥（行未等完成）`);
  await killBridge(bridgePid, "崩溃窗实测");
  bridgePid = spawnBridgeProcess(persistPort, "persist-crash-restart");
  setPid(bridgePid);
  if (!(await waitProbe(persistPort, 40000))) {
    return { ok: false, msg: "persist 崩溃窗重启桥 40s 不可探", tail: childTail("bridge-persist-crash-restart") };
  }
  const r4 = runChild("persist-replay", [...probeArgs, "replay", crashState],
    { timeoutMs: 150000, env: { ...probeEnvBase, BRIDGE_WS_URL: wsUrl } });
  const pass4 = r4.status === 0 && stripAnsi(r4.out).includes("PERSIST_REPLAY_OK");
  if (!pass4) {
    return { ok: false, msg: "persist 崩溃窗 FAIL：重放后无终态行或存在 running 相位", tail: childTail("persist-replay") };
  }
  return { ok: true, msg: `persist PASS：会话 ${st.sessionId} 重启后行完整一致；崩溃窗会话 ${cs.sessionId} 重放后行出现/显式错误且无 running 相位` };
}

// ── 步骤 4：许可骨架三态自测（F78/F79·RE-B3：无文件/有效/损坏→形态判定，含桥接线两例+复核轮收紧用例）──
function stepLicense() {
  const r = runChild("license-synth", [join("tools", "bridge", "license_synthetic.mjs")], { timeoutMs: 300000 });
  if (r.status !== 0) return { ok: false, msg: `license-synth exit=${r.status}（期望 0）`, tail: childTail("license-synth") };
  const text = stripAnsi(r.out);
  if (!text.includes("LICENSE_SYNTH_PASS")) return { ok: false, msg: "license-synth 输出无 LICENSE_SYNTH_PASS 末行", tail: childTail("license-synth") };
  const okCount = (text.match(/^\[license-synth\] \d+: OK/gm) ?? []).length;
  return { ok: true, msg: `许可骨架三态自测 ${okCount}/17 用例 OK，末行 LICENSE_SYNTH_PASS` };
}

// ── 步骤（fast）：桥内机制件合成自测（施工单-06：任务壳+gate 节点+真桥接线）──
function stepMechanisms() {
  const cases = [
    ["taskshell-synth", "taskshell_synthetic.mjs", "TASKSHELL_SYNTH_PASS"],
    ["flowgate-synth", "flow_gate_synthetic.mjs", "FLOWGATE_SYNTH_PASS"],
    ["mechwire-synth", "mechanism_wire_synthetic.mjs", "MECHWIRE_SYNTH_PASS"],
    ["clishim-synth", "cli_shim_synthetic.mjs", "CLI_SHIM_SYNTH_PASS"],
    ["flowengine-synth", "flow_engine_synthetic.mjs", "FLOWENGINE_SYNTH_PASS"],
    ["factverif-synth", "fact_verification_synthetic.mjs", "FACTVERIF_SYNTH_PASS"],
    ["crossverif-synth", "cross_verification_synthetic.mjs", "CROSSVERIF_SYNTH_PASS"],
    ["configwrite-synth", "config_write_synthetic.mjs", "CONFIGWRITE_SYNTH_PASS"],
  ];
  for (const [label, file, passMark] of cases) {
    const r = runChild(label, [join("tools", "bridge", file)], { timeoutMs: 300000 });
    if (r.status !== 0) return { ok: false, msg: `${file} exit=${r.status}（期望 0）`, tail: childTail(label) };
    const text = stripAnsi(r.out);
    if (!text.includes(passMark)) return { ok: false, msg: `${file} 输出无 ${passMark} 末行`, tail: childTail(label) };
    const okCount = text.split(String.fromCharCode(10)).filter((l) => l.startsWith("[" + label + "] ") && l.includes(": OK")).length;
    log(`  ✓ ${file} ${okCount} 用例 OK`);
  }
  return { ok: true, msg: "桥内机制件合成自测 8/8 PASS（TASKSHELL/FLOWGATE/MECHWIRE/CLISHIM/FLOWENGINE/FACTVERIF/CROSSVERIF/CONFIGWRITE——桥·增强三式·式三随行+#34 事实核验+#33 成套勾稽对拍+施工单-10 单元二结构化写入防御）" };
}

// ── 步骤（fast）：功能 #19 轻量知识图谱合成自测（RE-19 §3：exists:false 正常态/预览不落库/
// 写入回执真实计数/写路径 fail-closed 八连负测/乐观锁/锁定守卫+级联删除/杀桥重启不丢/清空回空态/
// 布局确定性/文件名净化/来源读取，末行 GRAPH_SYNTH_PASS）──
function stepGraph() {
  // --import tsx：经 @zcode/rpc 直调桥 RPC + 复用工作区 TS 模型（graph_synthetic 自管 :3065 隔离实例，不碰 :3030）
  const r = runChild("graph-synth", ["--import", "tsx", join("tools", "bridge", "graph_synthetic.mts")], { timeoutMs: 300000 });
  if (r.status !== 0) return { ok: false, msg: `graph-synth exit=${r.status}（期望 0）`, tail: childTail("graph-synth") };
  const text = stripAnsi(r.out);
  if (!text.includes("GRAPH_SYNTH_PASS")) return { ok: false, msg: "graph-synth 输出无 GRAPH_SYNTH_PASS 末行", tail: childTail("graph-synth") };
  const okCount = text.split(String.fromCharCode(10)).filter((l) => l.startsWith("[graph-synth] ") && l.includes(": OK")).length;
  return { ok: true, msg: `轻量知识图谱合成自测 ${okCount} 用例 OK，末行 GRAPH_SYNTH_PASS` };
}

// ── 步骤（fast）：功能 #14 引证核验合成自测（RE-14 §3.5：引擎针组+桥端四针+F4 落账）──
function stepCitation() {
  const r = runChild("citation-synth", [join("tools", "bridge", "citation_verify_synthetic.mjs")], { timeoutMs: 420000 });
  if (r.status !== 0) return { ok: false, msg: `citation-synth exit=${r.status}（期望 0）`, tail: childTail("citation-synth") };
  const text = stripAnsi(r.out);
  if (!text.includes("CITATION_VERIFY_SYNTH_PASS")) return { ok: false, msg: "citation-synth 输出无 CITATION_VERIFY_SYNTH_PASS 末行", tail: childTail("citation-synth") };
  const okCount = (text.match(/^\[citation-synth\] \d+: OK/gm) ?? []).length;
  return { ok: true, msg: `引证核验合成自测 ${okCount} 用例 OK，末行 CITATION_VERIFY_SYNTH_PASS（含引擎针组 CITATION_ENGINE_PROBE）` };
}

// ── 步骤（fast）：功能 #31 支持通道合成自测（RE-31 对拍：C27/§3.5/E31-E38/B15-B24/A6/A10/A12+桥接线）──
function stepSupport() {
  // --import tsx：经 @zcode/rpc 直调桥 RPC（persist_probe.mts 同款装载），纯 node 装不下工作区 TS 源
  const r = runChild("re31-synth", ["--import", "tsx", join("tools", "bridge", "re31_support_synthetic.mjs")], { timeoutMs: 300000 });
  if (r.status !== 0) return { ok: false, msg: `re31-synth exit=${r.status}（期望 0）`, tail: childTail("re31-synth") };
  const text = stripAnsi(r.out);
  if (!text.includes("RE31_SUPPORT_SYNTH_PASS")) return { ok: false, msg: "re31-synth 输出无 RE31_SUPPORT_SYNTH_PASS 末行", tail: childTail("re31-synth") };
  const okCount = (text.match(/^\[re31-synth\] \d+: OK/gm) ?? []).length;
  return { ok: true, msg: `支持通道合成自测 ${okCount} 用例 OK，末行 RE31_SUPPORT_SYNTH_PASS` };
}

// ── 步骤（package）：桌面构建 + 产物断言（步骤5 打包单①③）──
// 链路：build-metadata（版本/commit 落盘，About 可追溯）→ production build（tsup+vite，先清 out）
//       → electron-builder --win --x64（nsis 目标，electron-builder.config.js）。
// 口径：package 绿只认本步的 Windows NSIS 产物 + bridge_bundle_synthetic。
//       Linux 构建/产物即使成功，也不是 package 门禁绿（package 须在 Windows 上跑）。
// 产物新鲜闸：断言 exe/blockmap mtime 晚于构建起点，防旧产物冒充本轮构建。
function freshExeOf(distDir, notBeforeMs) {
  const out = [];
  for (const f of readdirSync(distDir)) {
    if (!f.toLowerCase().endsWith(".exe") || f.includes("__uninstaller")) continue;
    const full = join(distDir, f);
    if (statSync(full).isFile() && statSync(full).mtimeMs > notBeforeMs) out.push({ full, size: statSync(full).size, mtimeMs: statSync(full).mtimeMs });
  }
  return out;
}

async function stepDesktopBuild() {
  const buildStartMs = Date.now();
  const r0 = runChild("desktop-build-meta", [join("scripts", "build-metadata.mjs")],
    { cwd: DESKTOP_DIR, timeoutMs: 120000 });
  if (r0.status !== 0) return { ok: false, msg: `build-meta exit=${r0.status}（期望 0）`, tail: childTail("desktop-build-meta") };
  const buildMetaTail = stripAnsi(r0.out).trim().split(String.fromCharCode(10)).filter(Boolean).pop() ?? "";
  log(`build-meta ok（${buildMetaTail}）`);

  const r1 = runChild("desktop-build", [join("scripts", "run-production-build.mjs")],
    // 900s→3600s：tsup 与 vite 并行（run-production-build.mjs Promise.all），共享工位负载尖峰时
    // 整段慢 6-50 倍——2026-10-31 package 首轮实测：tsup 各段 79-103s（健康态 2-18s，见
    // ci-gate-logs/package-2026-10-30-*），vite 8337 模块转完后仍在渲染/产物段，15 分钟窗到点被
    // 误杀，日志零错误断在 transforming 后（无 crash 输出=外部杀，非构建自败）。同本文件 vitest
    // 300s→600s、electron-builder 30min→120min 的在案放宽类；本窗仍小于 electron-builder 窗，
    // 步骤级预算次序不变。
    { cwd: DESKTOP_DIR, timeoutMs: 3600000 });
  if (r1.status !== 0) return { ok: false, msg: `desktop production build exit=${r1.status}（期望 0；tsup/vite 输出见日志）`, tail: childTail("desktop-build", 4000) };

  const r2 = runChild("desktop-package", [
    join("node_modules", "electron-builder", "cli.js"),
    "--win", "--x64", "--config", "electron-builder.config.js",
  // r12 波4 实测（package 门禁四轮在案）：electron zip 冷缓存下载 ~15 分钟+pnpm 收集 ~10 分钟+
  // NSIS 压缩 ~5 分钟，30 分钟预算在热缓存机上也会于 NSIS 阶段误杀（exit=null），放宽到 60 分钟。
  // 施工波二轮实测（2026-10-31）：树增 @juscite/flow+edisc+vizb+legal 新面板后 60 分钟再度不够
  //（outer 3600000 同限炸 run），放宽到 120 分钟；outer 门禁超时须恒大于此值。
  ], { cwd: DESKTOP_DIR, timeoutMs: 7200000 });
  if (r2.status !== 0) return { ok: false, msg: `electron-builder exit=${r2.status}（期望 0；输出见日志）`, tail: childTail("desktop-package", 4000) };

  if (!existsSync(DESKTOP_DIST)) return { ok: false, msg: `产物目录缺失：${DESKTOP_DIST}` };
  const exes = freshExeOf(DESKTOP_DIST, buildStartMs);
  if (exes.length !== 1) {
    return { ok: false, msg: `新鲜 exe 应恰 1 个，实得 ${exes.length}（${exes.map((x) => x.full).join(", ") || "无"}）` };
  }
  const exe = exes[0];
  const blockmap = `${exe.full}.blockmap`;
  const latest = join(DESKTOP_DIST, "latest.yml");
  const unpackedYml = join(DESKTOP_DIST, "win-unpacked", "resources", "app-update.yml");
  const unpackedAsar = join(DESKTOP_DIST, "win-unpacked", "resources", "app.asar");
  for (const [label, p] of [["blockmap", blockmap], ["latest.yml", latest], ["win-unpacked app.asar", unpackedAsar], ["win-unpacked app-update.yml", unpackedYml]]) {
    if (!existsSync(p)) return { ok: false, msg: `产物缺失 ${label}: ${p}` };
    if (label !== "win-unpacked app-update.yml" && statSync(p).mtimeMs <= buildStartMs) {
      return { ok: false, msg: `${label} 非本轮构建产物（mtime 早于构建起点）: ${p}` };
    }
  }
  const ymlText = readFileSync(unpackedYml, "utf-8");
  if (!ymlText.includes("updates.juscite.invalid")) {
    return { ok: false, msg: `随包 app-update.yml 未携自家更新源桩（期望含 ${UPDATE_FEED_STUB}）：${unpackedYml}` };
  }
  // 桥随包断言（步骤5·桥随包单，销项 78b34899 记档边界）：win-unpacked resources/bridge
  // 物化要件在物 + 打包径 spawn 探针——ELECTRON_RUN_AS_NODE + 包内 tsx，与
  // desktopHostProcess.ts 打包分支同款参数，桥面 /api/server-info 应答即随包真可跑。
  const unpackedDir = join(DESKTOP_DIST, "win-unpacked");
  const unpackedExe = readdirSync(unpackedDir).find(
    (f) => f.toLowerCase().endsWith(".exe") && !f.toLowerCase().startsWith("uninstall"),
  );
  if (!unpackedExe) return { ok: false, msg: `win-unpacked 桌面 exe 缺失：${unpackedDir}` };
  // 探针预算不动：bridge_bundle_synthetic 里 #15 仍是字面量 90000。
  // 计时前对同一 Preview.exe 做一轮 ELECTRON_RUN_AS_NODE 预热（上限 130s，探到即停），
  // 再收场才开 #15。冷带约 98–120s，热路径约 55s。本步窗要装下 #14 + 预热 + #15
  //（各含探针过冲与最多 20s 收场，再加两段 2s 落静）≈ 400s；300s 会在预热收场前误杀。
  // 放到 480s。杀掉的是整段 synth，不是把探针放宽。
  const r3 = runChild("bridge-bundle-synth", [join("tools", "bridge", "bridge_bundle_synthetic.mjs")], {
    timeoutMs: 480000,
    env: {
      ...process.env,
      BRIDGE_BUNDLE_DIR: join(unpackedDir, "resources", "bridge"),
      BRIDGE_BUNDLE_ELECTRON_EXE: join(unpackedDir, unpackedExe),
    },
  });
  if (r3.status !== 0) {
    return { ok: false, msg: "随包桥探针 FAIL（bridge_bundle_synthetic：物化要件/spawn 未过；输出见日志）", tail: childTail("bridge-bundle-synth", 4000) };
  }
  log("随包桥探针 BRIDGE_BUNDLE_SYNTH_PASS（resources/bridge 物化要件 + ELECTRON_RUN_AS_NODE spawn 应答 server-info）");
  const mb = (exe.size / 1024 / 1024).toFixed(1);
  log(`产物 ${exe.full}（${exe.size} B ≈ ${mb} MB）+ blockmap + latest.yml；随包 app-update.yml 已携 ${UPDATE_FEED_STUB}`);
  return {
    ok: true,
    msg: `桌面构建 nsis exit 0，产物 ${exe.full}（${mb} MB）；blockmap/latest.yml 在；app-update.yml 携自家更新源桩；随包桥探针 PASS`,
    artifact: exe.full,
  };
}

// ── 步骤（fast）：品牌二轮门禁（r12 波2 · D5，设计 §二/§五④）──
// 全品牌正则 = 旧品牌 律引|Lvyin + 上游品牌 ZCode|Z.ai|智谱|GLM|ChatGLM|BigModel（大小写敏感：
// 小写 zcode/z.ai 属代码标识符与 wire 域名命名空间，不属用户可见文案）。
// 只扫用户可见字符串：剥离注释/模块路径/模板插值后匹配引号字面量，并匹配成对 HTML/JSX
// 标签的静态文本（<title>/<span> 等；去掉 {…} 表达式，跳过 script/style）。locale 基座（已还原上游）
// 不走字面量零命中，走 overlay 覆盖完备性断言；豁免逐项在 contracts/brand-exemptions.md（机读表为 ```json 围栏）。
const BRAND_RE_SOURCE = "ZCode|Z\\.ai|智谱|GLM|ChatGLM|BigModel|律引|Lvyin";
const BRAND_SCAN_ROOTS = ["packages/ui/src", "packages/desktop/src", "packages/web/src"];
const BRAND_SCAN_FILES = ["packages/web/index.html", "packages/desktop/build/installer.nsh"];
const BRAND_SCAN_EXTS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".json", ".html", ".nsh"]);
const BRAND_MODULE_SPECIFIER_RE = /^[\w@./~-]+\.(js|jsx|ts|tsx|mjs|cjs|json|css|scss|svg|png|jpe?g|gif|webp|woff2?|md)$/i;

function listBrandFiles(dir, out) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith(".") || entry.name.includes(".bak") || entry.name === "node_modules") continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) listBrandFiles(full, out);
    else if (BRAND_SCAN_EXTS.has(entry.name.slice(entry.name.lastIndexOf(".")))) out.push(full);
  }
  return out;
}

// 逐行引号跨度提取（错位只限单行、不跨行级联）：块注释先整体抹除（保行号）；
// 行内引号态机扫 "…"/'…'/`…`，模板 ${…} 插值跳过；' 起引需前导为代码标点/关键字（防英文撇号误判）。
function extractBrandLiterals(text) {
  const BS = String.fromCharCode(92);
  const SQ = String.fromCharCode(39);
  const blanked = text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "));
  const literals = [];
  blanked.split(/\r?\n/).forEach((line, idx) => {
    let q = null;
    let start = -1;
    let prevSignificant = "";
    let tplVal = ""; // 模板字面量的去插值累积（${…} 记一个空格占位）
    let i = 0;
    while (i < line.length) {
      const c = line[i];
      if (q === null) {
        if (c === "/" && line[i + 1] === "/") break; // 行注释
        if (c === '"' || c === "`") { q = c; start = i; tplVal = ""; i++; continue; }
        if (c === SQ) {
          const prevCode = /[(\[{:;,=+*&|!?<>~^+\-]/.test(prevSignificant) || /(return|typeof|case|in|of|default|throws?)$/i.test(prevSignificant);
          if (prevCode) { q = c; start = i; }
          i++;
          continue;
        }
        if (!/\s/.test(c)) prevSignificant = c;
        i++;
        continue;
      }
      if (c === BS) { tplVal += line.slice(i, i + 2); i += 2; continue; }
      if (q === "`" && c === "$" && line[i + 1] === "{") {
        let depth = 1;
        i += 2;
        while (i < line.length && depth > 0) {
          const d = line[i];
          if (d === "{") { depth++; i++; continue; }
          if (d === "}") { depth--; i++; continue; }
          if (d === '"' || d === SQ || d === "`") {
            const q2 = d;
            i++;
            while (i < line.length && line[i] !== q2) { i += line[i] === BS ? 2 : 1; }
            i++;
            continue;
          }
          i++;
        }
        tplVal += " ";
        continue;
      }
      if (c === q) {
        literals.push({ value: q === "`" ? tplVal : line.slice(start + 1, i), line: idx + 1 });
        q = null;
        prevSignificant = c;
        i++;
        continue;
      }
      tplVal += c;
      i++;
    }
  });
  return literals;
}

// 成对标签的静态文本（引号字面量扫不到的 <title>…</title> / <span>品牌</span>）。
// 块注释与 HTML 注释、script/style 正文先抹掉（保行号）；标签属性与正文都不跨 `<`/`>`，
// 因此比较运算和嵌套标签不会被当成一整段文案。JSX `{…}` 表达式抹成空格后再匹配品牌正则。
function stripBrandJsxExpressions(value) {
  let out = "";
  let i = 0;
  while (i < value.length) {
    if (value[i] !== "{") { out += value[i]; i++; continue; }
    let depth = 1;
    i++;
    while (i < value.length && depth > 0) {
      if (value[i] === "{") depth++;
      else if (value[i] === "}") depth--;
      i++;
    }
    out += " ";
  }
  return out;
}

function extractBrandMarkupTextNodes(text) {
  const blanked = text
    .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/<!--[\s\S]*?-->/g, (m) => m.replace(/[^\n]/g, " "))
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, (m) => m.replace(/[^\n]/g, " "))
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, (m) => m.replace(/[^\n]/g, " "));
  const nodes = [];
  const re = /<([A-Za-z][\w:.-]*)\b[^<>]*>([^<>]*)<\/\1>/g;
  let m;
  while ((m = re.exec(blanked)) !== null) {
    const value = stripBrandJsxExpressions(m[2]).replace(/\s+/g, " ").trim();
    if (!value) continue;
    const contentAt = m.index + m[0].indexOf(">") + 1;
    nodes.push({ value, line: blanked.slice(0, contentAt).split(/\r?\n/).length });
  }
  return nodes;
}

// locale 基座词条解析（扁平 Record，键行冒号后换行的续行值合并；与波2 生成器同法）。
function parseBrandLocaleEntries(text) {
  const BS = String.fromCharCode(92);
  const entryRe = new RegExp('^ {2}"((?:[^"' + BS + '"]|' + BS + '.)+)":(.*)$');
  const entries = new Map();
  let wrapKey = null;
  let wrapParts = [];
  for (const line of text.split(/\r?\n/)) {
    if (wrapKey !== null) {
      wrapParts.push(line.trim());
      if (/,\s*$/.test(line)) { entries.set(wrapKey, wrapParts.join(" ").replace(/,\s*$/, "")); wrapKey = null; wrapParts = []; }
      continue;
    }
    const m = line.match(entryRe);
    if (!m) continue;
    if (m[2].trim() === "") { wrapKey = m[1]; wrapParts = []; continue; }
    entries.set(m[1], m[2].trim().replace(/,\s*$/, ""));
  }
  return entries;
}

function parseBrandOverlayKeys(text, blockName) {
  const BS = String.fromCharCode(92);
  const start = text.indexOf(`const ${blockName}: Record<string, string> = {`);
  if (start < 0) throw new Error(`jusciteOverlay.ts 缺 ${blockName} 块`);
  const end = text.indexOf(String.fromCharCode(10) + "};", start);
  if (end < 0) throw new Error(`jusciteOverlay.ts ${blockName} 块未闭合`);
  const body = text.slice(start, end);
  const keyRe = new RegExp('^ {2}"((?:[^"' + BS + '"]|' + BS + '.)+)":', "gm");
  const keys = new Set();
  let m;
  while ((m = keyRe.exec(body)) !== null) keys.add(m[1]);
  return keys;
}

function stepBrand() {
  const exemptionsPath = join(REPO_ROOT, "contracts", "brand-exemptions.md");
  if (!existsSync(exemptionsPath)) return { ok: false, msg: "缺 contracts/brand-exemptions.md（品牌豁免表是门禁硬依赖）" };
  const fence = readFileSync(exemptionsPath, "utf-8").match(/```json\s*\n([\s\S]*?)```/);
  if (!fence) return { ok: false, msg: "brand-exemptions.md 缺 ```json 机读豁免表" };
  let waivers;
  try { waivers = JSON.parse(fence[1]).waivers; } catch (e) { return { ok: false, msg: `豁免表 JSON 解析失败: ${e.message}` }; }

  const relFiles = [];
  for (const root of BRAND_SCAN_ROOTS) {
    const abs = join(REPO_ROOT, ...root.split("/"));
    if (existsSync(abs)) for (const f of listBrandFiles(abs, [])) {
      const rel = f.slice(REPO_ROOT.length).replaceAll("\\", "/").replace(/^\//, "");
      if (!rel.includes("/i18n/locales/")) relFiles.push(rel); // locale 基座走覆盖断言，不进字面量扫描
    }
  }
  for (const f of BRAND_SCAN_FILES) if (existsSync(join(REPO_ROOT, ...f.split("/")))) relFiles.push(f);

  const brandRe = new RegExp(BRAND_RE_SOURCE, "g");
  const rawHits = [];
  for (const rel of relFiles) {
    let text = readFileSync(join(REPO_ROOT, ...rel.split("/")), "utf-8");
    if (rel.endsWith(".nsh")) text = text.split(/\r?\n/).filter((l) => !/^\s*[;#]/.test(l)).join(String.fromCharCode(10));
    if (rel.endsWith(".html")) text = text.replace(/<!--[\s\S]*?-->/g, " ");
    const seen = new Set();
    for (const lit of [...extractBrandLiterals(text), ...extractBrandMarkupTextNodes(text)]) {
      brandRe.lastIndex = 0;
      if (!brandRe.test(lit.value)) continue;
      if (BRAND_MODULE_SPECIFIER_RE.test(lit.value.trim())) continue; // 模块路径=标识符命名空间
      const value = lit.value.slice(0, 120);
      const key = `${lit.line}\0${value}`;
      if (seen.has(key)) continue;
      seen.add(key);
      rawHits.push({ rel, line: lit.line, value });
    }
  }

  let waived = 0;
  const unwaived = [];
  for (const hit of rawHits) {
    const w = waivers.find((x) => "packages/" + x.file === hit.rel && hit.value.includes(x.literal));
    if (w) { waived++; continue; }
    unwaived.push(hit);
  }

  const overlayText = readFileSync(join(REPO_ROOT, "packages", "ui", "src", "i18n", "jusciteOverlay.ts"), "utf-8");
  const overlayKeys = { en: parseBrandOverlayKeys(overlayText, "overlayEnUS"), zh: parseBrandOverlayKeys(overlayText, "overlayZhCN") };
  const coverage = {};
  for (const [locale, file, block] of [["en", "en-US", "overlayEnUS"], ["zh", "zh-CN", "overlayZhCN"]]) {
    let brandKeys = 0;
    let missing = [];
    for (const [key, rawVal] of parseBrandLocaleEntries(readFileSync(join(REPO_ROOT, "packages", "ui", "src", "i18n", "locales", `${file}.ts`), "utf-8"))) {
      brandRe.lastIndex = 0;
      if (!brandRe.test(rawVal)) continue;
      brandKeys++;
      if (!overlayKeys[locale].has(key)) missing.push(key);
    }
    coverage[locale] = { brandKeys, missing };
    if (missing.length) {
      return { ok: false, msg: `品牌检查 FAIL：locale ${file} 品牌词条 ${brandKeys} 键中 ${missing.length} 键无 overlay 覆盖（首3: ${missing.slice(0, 3).join(", ")}）` };
    }
  }

  if (unwaived.length) {
    const head = unwaived.slice(0, 5).map((h) => `${h.rel}:${h.line} "${h.value}"`).join(" | ");
    return { ok: false, msg: `品牌检查 FAIL：豁免外命中 ${unwaived.length} 处（正则 ${BRAND_RE_SOURCE}；前5: ${head}）——补扫 contracts/brand-exemptions.md` };
  }
  return {
    ok: true,
    msg: `品牌二轮检查 ${relFiles.length} 文件字面量与标签文本零漏（豁免 ${waived} 项逐条在案）；locale 基座品牌键 overlay 覆盖 en ${coverage.en.brandKeys}/${coverage.en.brandKeys}、zh ${coverage.zh.brandKeys}/${coverage.zh.brandKeys}`,
  };
}

// ── 步骤（upgrade①，设计 §五①）：豁免集 patch 干净适用检查（波4 verify-apply-check 直挂）──
// 语义：contracts/exemptions/*.patch 每个都必须能干净打在上游基线树（3c5b2276=3.16.2 原树，
// 可 env JUSCITE_EXEMPT_BASE 覆盖）；上游前进后此步红=豁免族上游形变，重裁豁免再过。
function stepApplyCheck() {
  const r = runChild("apply-check", [join("contracts", "exemptions", "verify-apply-check.mjs")], { timeoutMs: 300000 });
  if (r.status !== 0) return { ok: false, msg: `apply-check exit=${r.status}（期望 0）`, tail: childTail("apply-check") };
  const text = stripAnsi(r.out);
  const passLine = text.split(String.fromCharCode(10)).filter((l) => l.startsWith("APPLY_CHECK_PASS")).pop();
  if (!passLine) return { ok: false, msg: "apply-check 输出无 APPLY_CHECK_PASS 末行", tail: childTail("apply-check") };
  return { ok: true, msg: passLine };
}

// ── 步骤（upgrade②，设计 §五②/§八原则1）：合同面类型快照 diff ──
// 重生成 type-snapshot.json 到门禁日志临时目录，与在库 contracts/type-snapshot.json 逐符号对比
// （decl 文件/hash/text）。added/removed/changed 任一即红——上游协议动了我们消费的合同面，先红再裁。
function stepTypeSnapshot() {
  const baseP = join(REPO_ROOT, "contracts", "type-snapshot.json");
  if (!existsSync(baseP)) return { ok: false, msg: "缺 contracts/type-snapshot.json——先 node scripts/gen-ref-graph.mjs 生成并入库基线" };
  const genDir = join(LOGDIR, "type-snapshot-gen");
  const r = runChild("type-snapshot-gen", [join("scripts", "gen-ref-graph.mjs"), "--out-dir", genDir], { timeoutMs: 300000 });
  if (r.status !== 0) return { ok: false, msg: `gen-ref-graph exit=${r.status}（期望 0）`, tail: childTail("type-snapshot-gen") };
  const freshP = join(genDir, "type-snapshot.json");
  if (!existsSync(freshP)) return { ok: false, msg: "重生成未产出 type-snapshot.json", tail: childTail("type-snapshot-gen") };
  let base, fresh;
  try {
    base = JSON.parse(readFileSync(baseP, "utf-8")).symbols;
    fresh = JSON.parse(readFileSync(freshP, "utf-8")).symbols;
  } catch (e) {
    return { ok: false, msg: `快照 JSON 解析失败: ${e.message}` };
  }
  const modules = [...new Set([...Object.keys(base), ...Object.keys(fresh)])].sort();
  const added = [];
  const removed = [];
  const changed = [];
  let total = 0;
  for (const m of modules) {
    const b = base[m] ?? {};
    const f = fresh[m] ?? {};
    for (const s of Object.keys(f)) {
      total++;
      if (!(s in b)) added.push(`${m}:${s}`);
      else if (b[s].hash !== f[s].hash) changed.push(`${m}:${s}`);
    }
    for (const s of Object.keys(b)) if (!(s in f)) removed.push(`${m}:${s}`);
  }
  const drift = added.length + removed.length + changed.length;
  if (drift) {
    const head = [
      ...changed.slice(0, 5).map((x) => `变 ${x}`),
      ...added.slice(0, 5).map((x) => `增 ${x}`),
      ...removed.slice(0, 5).map((x) => `减 ${x}`),
    ].join(" | ");
    return { ok: false, msg: `合同面漂移 ${drift} 处（变 ${changed.length}/增 ${added.length}/减 ${removed.length}；首15: ${head}）——对齐上游真源后如属有意变更，重生成入库快照再复跑` };
  }
  return { ok: true, msg: `合同面类型快照 diff 零漂移（${total} 符号逐一对齐，声明原文 hash 一致）` };
}

// ── 步骤（upgrade③，设计 §五③/§一 L1b）：adapter 行数纪律 ──
// 口径=contracts/adapter-budget.md：桥=tools/bridge 顶层 .mjs+.mts（排 .bak/_tmp_，不含子目录）；
// adapter=packages/juscite-runtime-adapters 递归 .mjs+.ts（排 node_modules）；L1a port 类型件不计入。
// 全部 adapter 合计 ≤ 桥代码 10%（对标 dsh 模型层 ~3%），超限爆红。
const ADAPTER_BUDGET_RATIO_MAX = 10;
function countLinesIn(dir, exts, out) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name.startsWith(".")) continue;
    const full = join(dir, e.name);
    if (e.isDirectory()) countLinesIn(full, exts, out);
    else if (exts.some((x) => e.name.endsWith(x))) {
      out.files++;
      out.lines += readFileSync(full, "utf-8").split(/\r?\n/).length;
    }
  }
  return out;
}
function stepAdapterBudget() {
  const bridgeFiles = readdirSync(BRIDGE_DIR)
    .filter((f) => (f.endsWith(".mjs") || f.endsWith(".mts")) && !f.includes(".bak") && !f.startsWith("_tmp_"));
  let bridgeLines = 0;
  for (const f of bridgeFiles) bridgeLines += readFileSync(join(BRIDGE_DIR, f), "utf-8").split(/\r?\n/).length;
  const adapters = join(REPO_ROOT, "packages", "juscite-runtime-adapters");
  if (!existsSync(adapters)) return { ok: false, msg: "缺 packages/juscite-runtime-adapters（L1b adapter 树）" };
  const a = countLinesIn(adapters, [".mjs", ".ts"], { files: 0, lines: 0 });
  if (bridgeLines <= 0) return { ok: false, msg: "桥代码行数为 0，口径异常" };
  const ratio = (a.lines * 100) / bridgeLines;
  const msg = `adapter 行数纪律：adapter ${a.files} 文件 ${a.lines} 行 / 桥 ${bridgeFiles.length} 文件 ${bridgeLines} 行 = ${ratio.toFixed(2)}%（上限 ≤${ADAPTER_BUDGET_RATIO_MAX}%）`;
  if (ratio > ADAPTER_BUDGET_RATIO_MAX) return { ok: false, msg: `${msg} —— 超限爆红：换底座胶水膨胀，回砍 adapter 或走 port 扩面` };
  return { ok: true, msg };
}

// ── 步骤（fast·施工波二轮·可视化B轨 UI 件）：可视化面板桥接线合成自测（面板投影纯函数
// 进程内直调 → 五工具真桥 RPC，vizb_panel_synthetic.mts 自管隔离桥 :3093 不碰 :3030/:43127，
// 杀前核验命令行含 bridge_host.mjs，末行 VIZB_PANEL_SYNTH_PASS）──
function stepVizbPanel() {
  const r = runChild("vizb-panel-synth", ["--import", "tsx", join("tools", "bridge", "vizb_panel_synthetic.mts")], { timeoutMs: 300000 });
  if (r.status !== 0) return { ok: false, msg: `vizb-panel-synth exit=${r.status}（期望 0）`, tail: childTail("vizb-panel-synth") };
  const text = stripAnsi(r.out);
  if (!text.includes("VIZB_PANEL_SYNTH_PASS")) return { ok: false, msg: "vizb-panel-synth 输出无 VIZB_PANEL_SYNTH_PASS 末行", tail: childTail("vizb-panel-synth") };
  const okCount = text.split(String.fromCharCode(10)).filter((l) => l.startsWith("[vizb-panel-synth] ") && l.includes(": OK")).length;
  return { ok: true, msg: `可视化面板桥接线合成自测 ${okCount} 用例 OK，末行 VIZB_PANEL_SYNTH_PASS` };
}

// ── 步骤（fast/full·施工单-10 单元一）：表格导出公式注入防御合成自测（tabular_export_synthetic.mjs
// 进程内直驱零端口：#32 尽调台账 CSV 内核+HTTP 下载直出×合成负例 20 读回首字符 '/SpreadsheetML
// 大事记母表+对抗分析表强制 string 零载荷入公式/ssCell 公式通道封锁 fail-fast，末行 TABULAR_EXPORT_SYNTH_PASS）──
function stepTabularExport() {
  const r = runChild("tabular-export-synth", ["--import", "tsx", join("tools", "bridge", "tabular_export_synthetic.mjs")], { timeoutMs: 300000 });
  if (r.status !== 0) return { ok: false, msg: `tabular-export-synth exit=${r.status}（期望 0）`, tail: childTail("tabular-export-synth") };
  const text = stripAnsi(r.out);
  if (!text.includes("TABULAR_EXPORT_SYNTH_PASS")) return { ok: false, msg: "tabular-export-synth 输出无 TABULAR_EXPORT_SYNTH_PASS 末行", tail: childTail("tabular-export-synth") };
  const okCount = text.split(String.fromCharCode(10)).filter((l) => l.includes(" OK  ")).length;
  return { ok: true, msg: `表格导出公式注入防御合成自测 ${okCount} 用例 OK，末行 TABULAR_EXPORT_SYNTH_PASS（CSV 前置 '/SpreadsheetML 强制 string/公式通道封锁）` };
}

// ── 步骤（fast/full·逆向吸收波二·条 2/条 3）：声明式监控白名单+宿主桥降级合成自测
// （monitoring_synthetic.mjs：vizb 模板契约面 A/B + 页内执法双实现同矩阵 C + 消费面接线 D
// + 宿主桥 host.use('db'/'user') 两态 E；隔离端口 :3090 段先探活避让，oc28/:3030 不碰，
// 末行 MONITORING_SYNTH_PASS）──
function stepMonitoring() {
  const r = runChild("monitoring-synth", ["--import", "tsx", join("tools", "bridge", "monitoring_synthetic.mjs")], { timeoutMs: 300000 });
  if (r.status !== 0) return { ok: false, msg: `monitoring-synth exit=${r.status}（期望 0）`, tail: childTail("monitoring-synth") };
  const text = stripAnsi(r.out);
  if (!text.includes("MONITORING_SYNTH_PASS")) return { ok: false, msg: "monitoring-synth 输出无 MONITORING_SYNTH_PASS 末行", tail: childTail("monitoring-synth") };
  const okCount = text.split(String.fromCharCode(10)).filter((l) => l.startsWith("[monitoring-synth] ") && l.includes(": OK")).length;
  return { ok: true, msg: `监控白名单与宿主降级合成自测 ${okCount} 用例 OK，末行 MONITORING_SYNTH_PASS（白名单/三值/错误枚举闭集+host.use 两态/降级零报错/假身全合成）` };
}

// ── 主流程 ──
async function main() {
  let steps;
  if (mode === "brand") {
    steps = [["brand", stepBrand]];
  } else if (mode === "package") {
    // 放行条件④（RE-B3 §5）：license 步骤随行进打包门禁；桌面构建=步骤5 打包单①③。
    // 绿只认 Windows NSIS + bridge_bundle_synthetic；Linux ≠ package 绿。
    steps = [["nodecheck", stepNodecheck], ["license", stepLicense], ["desktop-build", stepDesktopBuild]];
  } else if (mode === "upgrade") {
    // 设计 §五 ①→⑤：豁免 apply --check → 合同面类型快照 diff → adapter 行数纪律 → 品牌正则 → fast 全量
    // （brand 属 fast 步骤之一，按 §五顺序置于④位，⑤尾段不重跑）。
    steps = [["apply-check", stepApplyCheck], ["type-snapshot", stepTypeSnapshot], ["adapter-budget", stepAdapterBudget], ["brand", stepBrand], ["nodecheck", stepNodecheck], ["vitest", stepVitest], ["vitestlegal", stepVitestLegal], ["e2e", stepE2E], ["license", stepLicense], ["mech", stepMechanisms], ["support", stepSupport], ["graph", stepGraph], ["vizbpanel", stepVizbPanel], ["tabularexport", stepTabularExport], ["monitoring", stepMonitoring], ["citation", stepCitation]];
  } else {
    steps = [["nodecheck", stepNodecheck], ["vitest", stepVitest], ["vitestlegal", stepVitestLegal], ["e2e", stepE2E], ["license", stepLicense], ["mech", stepMechanisms], ["support", stepSupport], ["graph", stepGraph], ["vizbpanel", stepVizbPanel], ["tabularexport", stepTabularExport], ["monitoring", stepMonitoring], ["citation", stepCitation], ["brand", stepBrand]];
    if (mode === "persist" || mode === "full") steps.push(["persist", stepPersist]);
  }
  const results = [];
  for (let i = 0; i < steps.length; i++) {
    const [name, fn] = steps[i];
    log(`── 步骤 ${i + 1}/${steps.length} ${name} ──`);
    let r;
    try { r = await fn(); } catch (e) { r = { ok: false, msg: `${name} 异常: ${e.message}` }; }
    results.push([name, r]);
    log(`${r.ok ? "✓" : "✗"} ${name}: ${r.msg}`);
    if (!r.ok) {
      if (r.tail) log(`── ${name} 日志尾部 ──\n${r.tail}`);
      log(`FAIL exit=1（${results.map(([n, x]) => `${n}=${x.ok ? "ok" : "FAIL"}`).join(", ")}）`);
      process.exit(1);
    }
  }
  const summary = results.map(([n, x]) => `${n}: ${x.msg}`).join(" | ");
  const artifact = results.find(([, x]) => x.artifact)?.[1].artifact;
  log(`PASS exit=0 —— ${summary}`);
  if (artifact) log(`PASS exit=0 产物路径 ${artifact}`);
  process.exit(0);
}
main();
