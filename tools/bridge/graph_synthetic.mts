// 功能 #19 轻量知识图谱合成用例（步骤4·RE-19 验收口径，全部合成材料）：
//   ①exists:false 正常态（对拍 #6）②规则建图预览：当事人=MatterLite 表+证据=materials 登记，
//   预览不落库（对拍 #1/#2）③确认建图写入回执真实计数（对拍 #36/#37）
//   ④写路径 fail-closed 八连负测：悬空边/关键无来源/2 月 30 日/HTML/URL/config 白名单外键/
//   节点超限/未知顶层字段（对拍 #30/#31/#32/#38）⑤乐观锁冲突+刷新再存（对拍 #26）
//   ⑥锁定守卫与级联删除（对拍 #19）⑦杀桥重启图不丢（RE-19 保存落桥同库）
//   ⑧清空图乐观锁+清空后回空态（对拍 #27）⑨布局确定性/方向/环图（对拍 #12/#13）
//   ⑩文件名净化（对拍 #29）⑪来源读取与缺失显式报错（对拍 #22）。
// 自管隔离桥实例（BRIDGE_TEST_PORT，默认 3065，独立 bridge-{port}.db），不碰 :3030/:43127。
// 末行 GRAPH_SYNTH_PASS / GRAPH_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import {
  layoutGraph, sanitizeGraphFilename, removeNodeCascade, lockedFieldGuard,
  type GNode, type GEdge,
} from "../../packages/juscite-legal/src/kernel/caseGraphModel.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3065);
const WORKSPACE = join(REPO_ROOT, ".local", `graph-scratch-${Date.now()}`);
const MATERIALS = join(WORKSPACE, "materials");
mkdirSync(MATERIALS, { recursive: true });
const NODE = process.execPath;
const results: Array<{ name: string; ok: boolean }> = [];
function check(name: string, ok: boolean, detail: string) {
  results.push({ name, ok });
  console.log(`[graph-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ── 合成材料（证据登记来源）+ 合成当事人（直接落 MatterLite 表，桥侧迁移先建表）──
writeFileSync(join(MATERIALS, "合成-借款合同.txt"), "甲方：张三\n乙方：李四\n利息：年利率百分之十二。\n", "utf-8");
writeFileSync(join(MATERIALS, "合成-转账凭证.md"), "# 转账凭证\n2026-03-01 张三向李四转账 20 万元。\n", "utf-8");

let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, ".local", `graph-synth-bridge-${PORT}.log`), "a");
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
async function waitProbe(timeoutMs: number) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) { if (await probe()) return true; await sleep(500); }
  return false;
}
async function killBridge(reason: string) {
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

// ---- RPC 客户端（重启后重建）----
let call: <T>(m: string, a?: unknown) => Promise<T> = async () => { throw new Error("未连接"); };
function connect(): Promise<void> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws`);
    ws.binaryType = "arraybuffer";
    const data = { fire: (_b: VSBuffer) => {} };
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

async function preflightClearPort() {
  // 上轮崩溃残留的同端口桥会让本轮探到旧代码旧库——开工先清场（核验命令行后才动手）
  if (!(await probe())) return;
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const pids = new Set<number>();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === PORT) pids.add(Number(m[2]));
  }
  for (const pid of pids) {
    const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
      { encoding: "utf-8", timeout: 20000 });
    if (String(q.stdout ?? "").includes("bridge_host.mjs")) {
      spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
      console.log(`[graph-synth] 清场：杀掉残留桥 pid=${pid}`);
    }
  }
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline && (await probe())) await sleep(500);
}

// ---- 主流程 ----
await preflightClearPort();
bridgePid = spawnBridge();
if (!(await waitProbe(40000))) { console.log("GRAPH_SYNTH_FAIL"); console.error("桥 40s 不可探"); process.exit(1); }
await connect();

type GetResult =
  | { exists: false; caseId: string }
  | { exists: true; caseId: string; revision: number; graph: { title: string; nodes: GNode[]; edges: GEdge[]; config: { direction: "TB" | "LR"; edgeLabels: boolean }; layout: { positions: Record<string, { x: number; y: number }> } }; updatedAt: number };

const get = () => call<GetResult>("caseGraphGet", { workspacePath: WORKSPACE, caseId: "default" });
const save = (baseRevision: number, graph: unknown) =>
  call<{ revision: number; nodeCount: number; edgeCount: number }>("caseGraphSave", { workspacePath: WORKSPACE, caseId: "default", baseRevision, graph });

// 种子 MatterLite 当事人（直落同库 case_board_cases——迁移 0005 由桥启动时建好）
let partiesSeeded = false;
try {
  const db = new DatabaseSync(dbPath());
  db.prepare("DELETE FROM case_board_cases WHERE id = 'mat_seed19'").run();
  db.prepare(`INSERT INTO case_board_cases (id, name, cause, case_no, court, court_type, claim_amount_cents,
      plaintiffs_json, defendants_json, judges_json, workflow_status, workflow_locked, overrides_json, sort_order, updated_at)
      VALUES (?, ?, '', '', '', '法院', 0, ?, ?, '[]', NULL, 0, '{}', NULL, ?)`)
    .run("mat_seed19", "合成-借款纠纷案", JSON.stringify(["张三"]), JSON.stringify(["李四", "王五"]),
      new Date().toISOString());
  db.close();
  partiesSeeded = true;
} catch (e) {
  console.log(`[graph-synth] MatterLite 种子失败（当事人路将诚实降级）：${String((e as Error).message).slice(0, 80)}`);
}

// ── ① exists:false 正常态 ──
const g0 = await get();
check("初读不存在=exists:false 正常态", g0.exists === false && g0.caseId === "default", JSON.stringify(g0).slice(0, 60));

// ── ② 建图预览（不落库）──
const pv = await call<{ available: boolean; partiesCount: number; materialsCount: number; note: string;
  proposal: { schemaVersion: number; title: string; nodes: GNode[]; edges: GEdge[] } }>("caseGraphBuildPreview",
  { workspacePath: WORKSPACE, caseId: "default", caseName: "合成借款纠纷" });
const pvKinds = pv.proposal.nodes.map((n) => n.kind);
check("预览含当事人与证据", pv.available && pvKinds.filter((k) => k === "party").length === (partiesSeeded ? 3 : 0)
  && pvKinds.filter((k) => k === "evidence").length === 2,
  `parties=${pv.partiesCount} materials=${pv.materialsCount} kinds=${pvKinds.join("/")}`);
check("预览带诚实说明", typeof pv.note === "string" && pv.note.length > 0, pv.note.slice(0, 40));
check("证据节点自带材料来源", pv.proposal.nodes.filter((n) => n.kind === "evidence")
  .every((n) => n.sourceRefs.length === 1 && !!n.sourceRefs[0].filename), "sourceRefs 绑文件名");
const gAfterPreview = await get();
check("预览不落库（未确认不写入）", gAfterPreview.exists === false, "仍 exists:false");

// ── ③ 确认建图：写入回执=真实结果（对拍 #36/#37）──
const saved1 = await save(0, pv.proposal);
check("确认后写入 revision 1", saved1.revision === 1 && saved1.nodeCount === pv.proposal.nodes.length,
  `rev=${saved1.revision} nodes=${saved1.nodeCount} edges=${saved1.edgeCount}`);
const g1 = await get();
check("回读一致", g1.exists && g1.revision === 1 && g1.graph.nodes.length === pv.proposal.nodes.length
  && g1.graph.config.direction === "TB", `title=${g1.exists ? g1.graph.title : "?"}`);

// ── ④ 写路径 fail-closed 八连负测 ──
const good = g1.exists ? g1.graph : null;
if (!good) { console.log("GRAPH_SYNTH_FAIL"); process.exit(1); }
const deepClone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));
async function expectReject(name: string, graph: unknown) {
  let rejected = false, msg = "";
  try { await save(1, graph); } catch (e) { rejected = true; msg = String((e as Error)?.message ?? e); }
  check(name, rejected, msg.slice(0, 70));
}
{
  const t = deepClone(good);
  t.edges.push({ id: "bad-dangling", source: t.nodes[0].id, target: "ghost", kind: "prove", status: "uncertain", sourceRefs: [], provenance: "user", lockedFields: [] });
  await expectReject("悬空边拒绝", t);
}
{
  const t = deepClone(good);
  t.nodes[0].status = "confirmed";
  t.nodes[0].importance = "critical";
  t.nodes[0].sourceRefs = [];
  await expectReject("关键+已证实无来源拒绝", t);
}
{
  const t = deepClone(good);
  t.nodes[0].date = "2026-02-30";
  await expectReject("2 月 30 日拒绝（ISO fail-closed）", t);
}
{
  const t = deepClone(good);
  t.nodes[0].label = "<img src=x onerror=alert(1)>张三";
  await expectReject("HTML 标签注入拒绝", t);
}
{
  const t = deepClone(good);
  t.nodes[0].detail = "详情见 https://example.com/evidence";
  await expectReject("http URL 拒绝", t);
}
{
  const t = deepClone(good);
  (t.config as Record<string, unknown>)["minimap"] = true;
  await expectReject("config 白名单外键拒绝", t);
}
{
  const t = deepClone(good);
  const extra = Array.from({ length: 101 - t.nodes.length }, (_, i) => ({
    id: `bulk-${i}`, kind: "event", label: `合成节点${i}`, status: "uncertain", sourceRefs: [], provenance: "user", lockedFields: [],
  }));
  t.nodes.push(...(extra as GNode[]));
  await expectReject("节点超 100 上限拒绝", t);
}
{
  const t = deepClone(good) as Record<string, unknown>;
  t["evilExtra"] = { a: 1 };
  await expectReject("未知顶层字段拒绝", t);
}

// ── ⑤ 乐观锁 ──
let conflictMsg = "";
try { await save(0, good); } catch (e) { conflictMsg = String((e as Error)?.message ?? e); }
check("过期 baseRevision 冲突报错", conflictMsg.includes("修订冲突"), conflictMsg.slice(0, 60));
{
  const t = deepClone(good);
  t.title = "合成借款纠纷·关系图（第二版）";
  const saved2 = await save(1, t);
  check("最新 baseRevision 保存成功 revision 2", saved2.revision === 2, `rev=${saved2.revision}`);
}

// ── ⑥ 锁定守卫与级联删除（模型层直测，对拍 #19）──
{
  const nA: GNode = { id: "a", kind: "party", label: "甲", status: "uncertain", sourceRefs: [], provenance: "user", lockedFields: [] };
  const nB: GNode = { id: "b", kind: "party", label: "乙", status: "uncertain", sourceRefs: [], provenance: "user", lockedFields: ["status"] };
  const nC: GNode = { id: "c", kind: "evidence", label: "凭证", status: "uncertain", sourceRefs: [], provenance: "user", lockedFields: [] };
  const eAB: GEdge = { id: "e1", source: "a", target: "b", kind: "contract", status: "uncertain", sourceRefs: [], provenance: "user", lockedFields: ["status"] };
  const eAC: GEdge = { id: "e2", source: "a", target: "c", kind: "prove", status: "uncertain", sourceRefs: [], provenance: "user", lockedFields: [] };
  const graph = { nodes: [nA, nB, nC], edges: [eAB, eAC] };
  let aiBlocked = false, aiMsg = "";
  try { removeNodeCascade(graph, "a", "ai"); } catch (e) { aiBlocked = true; aiMsg = String((e as Error).message); }
  check("自动改动删锁定相连节点整拒", aiBlocked && aiMsg.includes("锁定"), aiMsg.slice(0, 50));
  const userCut = removeNodeCascade(graph, "a", "user");
  check("人工删除连带删边+无关保留", userCut.nodes.length === 2 && userCut.edges.length === 0,
    `nodes=${userCut.nodes.map((n) => n.id).join("/")} edges=${userCut.edges.length}`);
  let guardBlocked = false;
  try { lockedFieldGuard(nB, { status: "confirmed" }, "ai"); } catch { guardBlocked = true; }
  check("自动改动触碰锁定字段拒绝", guardBlocked, "lockedFields=[status]");
  let guardUserOk = true;
  try { lockedFieldGuard(nB, { status: "confirmed" }, "user"); } catch { guardUserOk = false; }
  check("人工编辑无视锁定直改", guardUserOk, "user 路径放行");
}

// ── ⑦ 杀桥重启图不丢 ──
await killBridge("重启持久窗");
bridgePid = spawnBridge();
if (!(await waitProbe(40000))) { console.log("GRAPH_SYNTH_FAIL"); console.error("重启后桥 40s 不可探"); process.exit(1); }
await connect();
const g2 = await get();
check("杀桥重启图完整（revision/节点/标题）", g2.exists && g2.revision === 2
  && g2.graph.title === "合成借款纠纷·关系图（第二版）" && g2.graph.nodes.length === good.nodes.length,
  `rev=${g2.exists ? g2.revision : "?"} title=${g2.exists ? g2.graph.title : "?"}`);

// ── ⑧ 清空图：乐观锁+清空后回空态 ──
let clearConflict = "";
try { await call("caseGraphClear", { workspacePath: WORKSPACE, caseId: "default", baseRevision: 0 }); }
catch (e) { clearConflict = String((e as Error)?.message ?? e); }
check("清空图乐观锁冲突", clearConflict.includes("修订冲突"), clearConflict.slice(0, 50));
await call("caseGraphClear", { workspacePath: WORKSPACE, caseId: "default", baseRevision: 2 });
const g3 = await get();
check("清空后回 exists:false", g3.exists === false, "空态可重建");

// ── ⑨ 布局确定性/方向/环图 ──
{
  const ns = [{ id: "a", label: "甲" }, { id: "b", label: "乙" }, { id: "c", label: "丙" }];
  const es = [{ source: "a", target: "b" }, { source: "b", target: "c" }];
  const l1 = layoutGraph(ns, es, "TB");
  const l2 = layoutGraph(ns, es, "TB");
  const same = JSON.stringify(l1) === JSON.stringify(l2);
  const a = l1.positions.a, b = l1.positions.b, c = l1.positions.c;
  const tbOk = a.y === 32 && b.y === 32 + 84 + 72 && c.y === 32 + 2 * (84 + 72)
    && b.x === 32 && a.x === 32; // 同层单列：x=pad
  check("TB 分层坐标确定性（层距 72/垫 32/同输入同输出）", same && tbOk,
    `a=(${a.x},${a.y}) b=(${b.x},${b.y}) c=(${c.x},${c.y})`);
  const lr = layoutGraph(ns, es, "LR");
  check("LR 方向换轴", lr.positions.b.x === 32 + 220 + 72 && lr.positions.b.y === 32,
    `b=(${lr.positions.b.x},${lr.positions.b.y})`);
  const cyc = layoutGraph(ns, [{ source: "a", target: "b" }, { source: "b", target: "c" }, { source: "c", target: "a" }], "TB");
  check("环图不死循环、全部有位", Object.keys(cyc.positions).length === 3,
    Object.entries(cyc.positions).map(([k, v]) => `${k}@${v.x},${v.y}`).join(" "));
}

// ── ⑩ 文件名净化 ──
{
  const s1 = sanitizeGraphFilename('借/贷:合*同?"<>|纠纷.md');
  const s2 = sanitizeGraphFilename("...尾点...");
  const s3 = sanitizeGraphFilename("///");
  check("文件名净化（非法字符并档/首尾点/全下划线回退）",
    s1 === "借_贷_合_同_纠纷.md" && s2 === "尾点" && s3 === "关系图",
    `s1=${s1} s2=${s2} s3=${s3}`);
}

// ── ⑪ 来源读取与缺失显式报错 ──
{
  const src = await call<{ name: string; text: string; truncated: boolean }>("caseGraphReadSource",
    { workspacePath: WORKSPACE, filename: "合成-借款合同.txt" });
  check("来源回读材料正文", src.name === "合成-借款合同.txt" && src.text.includes("年利率百分之十二"),
    `len=${src.text.length}`);
  let missingRejected = false;
  try { await call("caseGraphReadSource", { workspacePath: WORKSPACE, filename: "不存在-材料.txt" }); }
  catch { missingRejected = true; }
  check("缺失来源显式报错", missingRejected, "fail-closed");
}

// 清场：杀自己的桥实例 + 刮刮乐工作区
await killBridge("自测收场");
rmSync(WORKSPACE, { recursive: true, force: true });

const failed = results.filter((r) => !r.ok);
console.log(failed.length ? "GRAPH_SYNTH_FAIL" : "GRAPH_SYNTH_PASS");
process.exit(failed.length ? 1 : 0);
