// 【#35 尾巴②】Flow Studio 面板件合成自测（施工波三轮；全合成材料，逐条可复跑）：
// 面板侧投影（@juscite/legal flowStudioModel 纯函数，进程内直调）
// → 真桥 flow* RPC 全链（隔离端口自管桥实例，默认 :3090 可 BRIDGE_FLOW_PANEL_PORT 覆盖；
//   不碰 :3030/:43127，杀前核验命令行含 bridge_host.mjs）。覆盖面板按钮主链路中除浏览器 DOM 外每一环：
//   S1 投影闭集与 fail-closed     S2 隔离桥拉起
//   S3 定义列表含内置只读         S4 内置详情六活动节点
//   S5 编译诊断面（B11）          S6 草稿→发布（publishedHash 64hex，E1）
//   S7 布局分离持久化（E4）       S8 导出/导入往返+覆盖契约（E3）
//   S9 内置只读拒写               S10 内置发起运行→产物链+链校验（D3/D7）
//   S11 运行列表                  S12 闸门运行 WAITING 持久化（B7）
//   S13 乐观锁冲突回显（R2 不自动重放）S14 正确版本过闸恢复→SUCCEEDED
//   S15 AI-run 空面（G4 如实空）  S16 能力描述符不含 inputSchema（C4）
//   S17 暂停/取消状态机
// 末行 FLOWPANEL_SYNTH_PASS / FLOWPANEL_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { openSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import {
  runBadgeOf, defBadgeOf, conflictCurrentVersionOf, aiRunRowView, defNodeCensus, canStartDefinition,
} from "../../packages/juscite-legal/src/kernel/flowStudioModel.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_FLOW_PANEL_PORT ?? 3090);
const NODE = process.execPath;
const results: Array<{ name: string; ok: boolean }> = [];
function check(name: string, ok: boolean, detail: string) {
  results.push({ name, ok });
  console.log(`[flowpanel-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const HEX64 = /^[0-9a-f]{64}$/;

// ══ S1 面板投影纯函数 ══
{
  const unk = runBadgeOf("EXPLODED");
  check("S1a 未知运行态灰态具名（fail-closed）", unk.unknown === true && unk.tone === "idle" && unk.label.includes("EXPLODED"), unk.label);
  check("S1b 内置只读徽章+只读位", defBadgeOf("builtin", "builtin").label.includes("只读"), defBadgeOf("builtin", "builtin").label);
  check("S1c 关卡冲突回显解析「当前 vN」", conflictCurrentVersionOf("版本已推进：你看到的是 v1，当前 v3，请刷新后重新决定") === 3, "v3");
  const airun = aiRunRowView({ modelCode: "m", promptVersion: "p", riskScore: "0.2" as unknown as number, findings: null });
  check("S1d AI-run 行视图：字符串分值不收（严格数值）", airun.riskLine.includes("未上报") && airun.findingsCount === 0, airun.riskLine);
  const census = defNodeCensus({ nodes: [{ type: "gate" }, { type: "gate" }], groups: [{ nodeIds: ["a", "b"] }] });
  check("S1e 定义普查分组注记=仅展示", census.byType[0]!.count === 2 && census.groupsNote.includes("仅界面展示"), census.groupsNote);
  check("S1f 草稿发起门槛=只可试跑", canStartDefinition("local", "draft").testRunOnly === true, "draft→testRun");
}

// ══ 真桥接线（隔离端口自管桥实例；不碰 :3030/:43127）══
let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, ".local", `flow-panel-synth-bridge-${PORT}.log`), "a");
function probe(): Promise<boolean> {
  return (async () => {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/api/server-info`, { signal: AbortSignal.timeout(2500) });
      return r.ok;
    } catch { return false; }
  })();
}
let call: <T>(m: string, a?: unknown) => Promise<T> = async () => { throw new Error("未连接"); };
function connect(): Promise<void> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws`);
    ws.binaryType = "arraybuffer";
    const data: { fire: (b: VSBuffer) => void } = { fire: () => {} };
    ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
    ws.on("open", () => {
      const isocket = {
        onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
        onClose: () => ({ dispose: () => {} }),
        onEnd: () => ({ dispose: () => {} }),
        write: (b: VSBuffer) => ws.send(b.buffer),
        end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
      };
      const ch = new ChannelClient(new SocketProtocol(isocket as never)).getChannel("zcode-agent");
      call = async <T,>(m: string, a?: unknown) => ch.call<T>(m, a === undefined ? [] : [a]);
      call("helloConversationV4").then(() => resolve()).catch(reject);
    });
    ws.on("error", reject);
  });
}

// 定义 id 每跑唯一（隔离桥 per-port 库跨跑持久——幂等可复跑，不留同名冲突）
const DRAFT_ID = "flow.panel.draft." + Date.now().toString(36);
const DRAFT_DEF = {
  formatVersion: 2, id: DRAFT_ID, version: 1, title: "面板合成草稿（合成材料）",
  inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] },
  nodes: [
    { id: "s1", type: "activity", title: "材料（合成）", dependsOn: [], capability: "line.intake.materials", input: { lineId: { kind: "input", path: "lineId" } } },
    { id: "g1", type: "gate", title: "复核（合成）", dependsOn: ["s1"], gateKind: "process", request: { 事项: "面板合成复核" } },
  ],
};
const GATE_RUN_DEF = {
  formatVersion: 2, id: "flow.panel.gaterun", version: 1, title: "面板闸门运行（合成材料）",
  inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] },
  nodes: [
    { id: "act", type: "activity", title: "活动（合成）", dependsOn: [], capability: "line.intake.materials", input: { lineId: { kind: "input", path: "lineId" } } },
    { id: "gate", type: "gate", title: "关卡（合成）", dependsOn: ["act"], gateKind: "process", request: { 事项: "面板合成关卡" } },
  ],
};

try {
  const pre = await probe();
  if (pre) throw new Error(`端口 :${PORT} 已被占用（拒绝复用来历不明的桥实例；请改 BRIDGE_FLOW_PANEL_PORT）`);
  const env = { ...process.env, BRIDGE_PORT: String(PORT) };
  const child = spawn(NODE, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: ["ignore", bridgeLog, bridgeLog], detached: true });
  child.unref();
  bridgePid = child.pid!;
  let up = false;
  const deadline = Date.now() + 40000;
  while (Date.now() < deadline) { if (await probe()) { up = true; break; } await sleep(500); }
  check("S2 隔离桥拉起（:" + PORT + "）", up, `pid=${bridgePid}`);
  if (!up) throw new Error("隔离桥未在超时内就绪");
  await connect();

  // S3/S4 定义列表+内置详情
  const defList = await call<{ rows: Array<{ id: string; source: string; status: string; title: string }> }>("flowDefList");
  const builtin = defList.rows.find((r) => r.id === "builtin.six-stage-line");
  check("S3 定义列表含内置流程（双来源 builtin 半边）", Boolean(builtin) && builtin!.source === "builtin" && builtin!.status === "builtin",
    `${defList.rows.length} 行`);
  const defGet = await call<{ meta: { id: string; source: string; status: string }; definition: { nodes: Array<{ type: string }> } }>("flowDefGet", { id: "builtin.six-stage-line" });
  check("S4 内置详情：六活动节点只读面", defGet.meta.source === "builtin" && defGet.definition.nodes.length === 6 && defGet.definition.nodes.every((n) => n.type === "activity"),
    `${defGet.definition.nodes.length} 节点`);

  // S5 编译诊断面（B11）
  const badCompile = await call<{ ok: boolean; diagnostics: Array<{ path: string }> }>("flowDefCompile", { definition: { ...DRAFT_DEF, extraKey: 1 } });
  const goodCompile = await call<{ ok: boolean }>("flowDefCompile", { definition: DRAFT_DEF });
  check("S5 编译诊断：附加属性拒+合法定义过", badCompile.ok === false && badCompile.diagnostics.some((d) => d.path === "extraKey") && goodCompile.ok === true,
    `diagnostics=${badCompile.diagnostics.length}`);

  // S6 草稿→发布（E1 publishedHash）
  const saved = await call<{ id: string; status: string; version: number }>("flowDraftSave", { definition: DRAFT_DEF });
  const published = await call<{ status: string; publishedHash?: string }>("flowDraftPublish", { id: saved.id });
  check("S6 草稿保存→发布：publishedHash 64hex（E1）", saved.status === "draft" && saved.version === 1 && published.status === "published" && HEX64.test(published.publishedHash ?? ""),
    `hash=${(published.publishedHash ?? "").slice(0, 12)}…`);

  // S7 布局分离（E4）
  const layout = await call<{ layoutChanged: boolean }>("flowLayoutPut", { id: saved.id, layout: { nodes: { s1: { position: { x: 10, y: 20 } } }, viewport: { x: 0, y: 0, zoom: 1 } } });
  check("S7 布局与定义分离持久化（E4）", layout.layoutChanged === true, "layoutChanged");

  // S8 导出/导入往返（E3；行键=定义 id 只在导入路径成立——草稿保存行键为随机 id，首次导入才落 flow.panel.draft1）
  const bundle = await call<{ format: string; definition: { id: string }; layout: unknown }>("flowBundleExport", { id: saved.id });
  const imp1 = await call<{ imported: string; overwrite: boolean }>("flowBundleImport", { bundle });
  let noOverwrite: unknown = null;
  try { await call("flowBundleImport", { bundle }); } catch (e) { noOverwrite = e; }
  check("S8a 同名再导入不覆盖=拒（STATE）", imp1.imported === DRAFT_ID && imp1.overwrite === false
    && noOverwrite !== null && String((noOverwrite as Error).message).includes("overwrite"),
    String((noOverwrite as Error)?.message ?? "").slice(0, 50));
  const imported = await call<{ imported: string; overwrite: boolean }>("flowBundleImport", { bundle, overwrite: true });
  check("S8b 覆盖导入往返成立（E3）", imported.imported === DRAFT_ID && imported.overwrite === true, imported.imported);

  // S9 内置只读拒写
  let builtinWrite: unknown = null;
  try { await call("flowDraftSave", { id: "builtin.six-stage-line", definition: DRAFT_DEF }); } catch (e) { builtinWrite = e; }
  check("S9 内置流程只读拒写（E2）", builtinWrite !== null && String((builtinWrite as Error).message).includes("只读"),
    String((builtinWrite as Error)?.message ?? "").slice(0, 40));

  // S10 内置发起运行→产物链+链校验（D3/D7）
  const runRes = await call<{ runId: string; status: string }>("flowRunStart", { definitionId: "builtin.six-stage-line", input: { lineId: "line.panel.synth" } });
  const runFace = await call<{ run: { status: string }; chain: { verified: boolean; length: number }; artifacts: Array<{ payloadDigest: string; citeReceipt: { receiptId?: string } }>; aiRuns: unknown[] }>("flowRunGet", { id: runRes.runId });
  check("S10 内置运行：SUCCEEDED+链校验+产物 digest（D3/D7）",
    runRes.status === "SUCCEEDED" && runFace.run.status === "SUCCEEDED" && runFace.chain.verified === true
    && runFace.artifacts.length === 1 && HEX64.test(runFace.artifacts[0]!.payloadDigest) && Boolean(runFace.artifacts[0]!.citeReceipt.receiptId),
    `chain=${runFace.chain.length} artifacts=${runFace.artifacts.length}`);

  // S11 运行列表
  const runList = await call<{ rows: Array<{ id: string; status: string }> }>("flowRunList", { limit: 10 });
  check("S11 运行列表含刚完成的运行", runList.rows.some((r) => r.id === runRes.runId && r.status === "SUCCEEDED"), `${runList.rows.length} 行`);

  // S12 闸门运行 WAITING 持久化（B7）
  const gateRun = await call<{ runId: string; status: string; gateNodeId: string }>("flowRunStart", { definition: GATE_RUN_DEF, input: { lineId: "line.panel.gate" } });
  const gateFaceRun = await call<{ run: { status: string; waiting: { kind: string; gateNodeId: string } | null } }>("flowRunGet", { id: gateRun.runId });
  const gateNode = await call<{ node: { id: string; status: string; lockVersion: number } }>("flowGateGetNode", { id: gateRun.gateNodeId });
  check("S12 闸门运行 WAITING 持久化+关卡 PENDING（B7）",
    gateRun.status === "WAITING" && gateFaceRun.run.status === "WAITING" && gateFaceRun.run.waiting?.kind === "gate"
    && gateNode.node.status === "PENDING" && gateNode.node.lockVersion === 1,
    `gate=${gateRun.gateNodeId} v${gateNode.node.lockVersion}`);

  // S13 乐观锁冲突回显（R2：冲突回 currentVersion，不自动重放）
  let conflict: unknown = null;
  try { await call("flowGateProcess", { id: gateRun.gateNodeId, actor: "面板合成人", action: "approve", expectedVersion: 0 }); } catch (e) { conflict = e; }
  const conflictText = String((conflict as Error)?.message ?? "");
  check("S13 旧版本决定=CONFLICT 拒（回显当前 v1，不自动重放）",
    conflict !== null && conflictText.includes("当前 v1") && conflictCurrentVersionOf(conflictText) === 1,
    conflictText.slice(0, 44));

  // S14 正确版本过闸恢复→SUCCEEDED
  await call("flowGateProcess", { id: gateRun.gateNodeId, actor: "面板合成人", action: "approve", comment: "面板合成批准（非真实决定）", expectedVersion: 1 });
  const resumed = await call<{ status: string }>("flowRunResume", { id: gateRun.runId, actor: "面板合成人" });
  check("S14 正确版本批准→恢复→SUCCEEDED", resumed.status === "SUCCEEDED", resumed.status);

  // S15 AI-run 空面（G4：记录缺失=如实空，不伪造）
  const aiFace = await call<{ status: string; rows: unknown[] }>("flowAiRunList", { runId: runRes.runId });
  check("S15 AI-run 面空态如实（纯确定性运行零记录）", aiFace.status === "OK" && aiFace.rows.length === 0, `rows=${aiFace.rows.length}`);

  // S16 能力描述符不含 inputSchema（C4）
  const caps = await call<{ rows: Array<{ id: string; risk: string; idempotency: string; inputSchema?: unknown }> }>("flowCapList");
  const intake = caps.rows.find((c) => c.id === "line.intake.materials");
  check("S16 能力描述符不含 inputSchema（C4 分层）", Boolean(intake) && caps.rows.every((c) => !("inputSchema" in c)),
    `${caps.rows.length} 项`);

  // S17 暂停/取消状态机
  const pRun = await call<{ runId: string; status: string; gateNodeId: string }>("flowRunStart", { definition: GATE_RUN_DEF, input: { lineId: "line.panel.pc" }, testRun: false });
  const paused = await call<{ ok: boolean }>("flowRunPause", { id: pRun.runId });
  const cancelled = await call<{ ok: boolean }>("flowRunCancel", { id: pRun.runId, reason: "面板合成取消" });
  const pFace = await call<{ run: { status: string } }>("flowRunGet", { id: pRun.runId });
  check("S17 WAITING 可下暂停标记→取消终态", paused.ok === true && cancelled.ok === true && pFace.run.status === "CANCELLED", pFace.run.status);
} catch (e) {
  check("BRIDGE 接线", false, String(e instanceof Error ? e.message : e));
} finally {
  if (bridgePid) {
    const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Get-CimInstance Win32_Process -Filter "ProcessId=${bridgePid}").CommandLine`],
      { encoding: "utf-8", timeout: 20000 });
    if (String(q.stdout ?? "").includes("bridge_host.mjs")) {
      spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
      console.log(`[flowpanel-synth] 测试桥已关闭 pid=${bridgePid}`);
    } else {
      console.log(`[flowpanel-synth] 拒绝杀 pid=${bridgePid}（命令行不含 bridge_host.mjs）——如实留运行`);
    }
  }
}
const failedCount = results.filter((r) => !r.ok).length;
if (failedCount > 0) { console.error("FLOWPANEL_SYNTH_FAIL"); process.exit(1); }
console.log("FLOWPANEL_SYNTH_PASS");
