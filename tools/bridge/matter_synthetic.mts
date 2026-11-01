// 【步骤4·案件族底座】MatterLite 桥内轻量案件表合成用例（全部合成材料）：
//   ①案件/待办/日程三面 CRUD round-trip 与强校验负测（金额整型分/日期 YYYY-MM-DD/状态 11 档白名单）；
//   ②状态两写同语句（手设=值+locked=1；恢复自动=NULL+locked=0，DB 直读核验）；
//   ③覆盖层 merge 语义+服务端校验 fail-closed+整体清除（原字段不被覆盖）；
//   ④杀桥重启数据不丢+迁移账本不重放；⑤案件删除级联清案内待办（FK CASCADE）。
// 自管隔离桥实例（BRIDGE_TEST_PORT，默认 3064，独立 bridge-{port}.db），不碰 :3030/:43127。
// 末行 MATTER_SYNTH_PASS / MATTER_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { openSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3064);
const NODE = process.execPath;
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok });
  console.log(`[matter-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function dbPath() { return join(process.env.APPDATA ?? "", "Juscite", "bridge", `bridge-${PORT}.db`); }
function openDb() { return new DatabaseSync(dbPath()); }

let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, ".local", `matter-synth-bridge-${PORT}.log`), "a");
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
async function commandLineOf(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  return String(r.stdout ?? "").trim();
}
function findListenerPids(port) {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const pids = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === port) pids.add(Number(m[2]));
  }
  return [...pids];
}
async function killBridge(reason) {
  const line = await commandLineOf(bridgePid);
  if (!line.includes("bridge_host.mjs")) {
    throw new Error(`拒绝杀进程 pid=${bridgePid}（${reason}）：命令行不含 bridge_host.mjs，宁停不误杀`);
  }
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probe())) await sleep(500);
}
// 开跑前清占端口的残留桥（上一轮崩溃可能泄漏实例——probe 连旧实例=拿旧代码/旧库跑，结果全不可信）。
// 只杀命令行含 bridge_host.mjs 的进程；被非桥占用则显式失败，宁停不误杀。
async function clearStaleBridge() {
  for (const pid of findListenerPids(PORT)) {
    const line = await commandLineOf(pid);
    if (!line.includes("bridge_host.mjs")) {
      throw new Error(`:${PORT} 被非桥进程占用（pid=${pid}），不接触`);
    }
    console.log(`[matter-synth] 清残留桥 pid=${pid}`);
    spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
  }
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probe())) await sleep(500);
}
// 期望 RPC 报错的负测：错误消息收全（fail-closed=显式报错，非静默吞）
async function callExpectError(name, params) {
  try { await call(name, params); return { threw: false, message: "" }; }
  catch (e) { return { threw: true, message: String(e?.message ?? e) }; }
}

// ---- RPC 客户端（重启桥后重连）----
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
  await clearStaleBridge();
  // 清自家隔离库（上一轮崩溃可能留脏数据；clearStaleBridge 已确保无进程占用）
  for (const suffix of ["", "-wal", "-shm"]) {
    try { unlinkSync(dbPath() + suffix); } catch { /* 不存在即可 */ }
  }
  // ── P1 案件创建+列表 round-trip（含仲裁委口径）──
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error(`隔离桥 :${PORT} 40s 不可探`);
  await connect();
  const c1 = await call("matterCreate", {
    name: "合成案件·借款合同纠纷",
    cause: "民间借贷",
    caseNo: "(2026)合0203民初9999号",
    court: "合成市合成区人民法院",
    courtType: "法院",
    claimAmountCents: 1234567,
    plaintiffs: ["合成甲"],
    defendants: ["合成乙", "合成丙"],
    judges: ["合成审判员"],
  });
  check("P1 案件创建（id 返回+字段 round-trip）",
    Boolean(c1?.id) && c1.name === "合成案件·借款合同纠纷" && c1.claimAmountCents === 1234567
      && JSON.stringify(c1.defendants) === JSON.stringify(["合成乙", "合成丙"])
      && c1.courtType === "法院" && c1.workflowStatus === null && c1.workflowLocked === false
      && JSON.stringify(c1.overrides) === "{}",
    `id=${c1?.id ?? "无"} cents=${c1?.claimAmountCents}`);
  const arb = await call("matterCreate", { name: "合成案件·劳动仲裁", courtType: "仲裁委", cause: "劳动争议" });
  check("P1 仲裁委案件（court_type 收『仲裁委』）", arb?.courtType === "仲裁委", `id=${arb?.id ?? "无"}`);
  const list1 = await call("matterList");
  check("P1 列表可见两案", Array.isArray(list1?.cases) && list1.cases.length === 2, `count=${list1?.cases?.length}`);

  // ── P2 创建负测（强校验 fail-closed 显式报错）──
  const e2a = await callExpectError("matterCreate", { name: "  " });
  check("P2 空案件名显式拒绝", e2a.threw && e2a.message.includes("案件名"), e2a.message.slice(0, 40));
  const e2b = await callExpectError("matterCreate", { name: "合成", courtType: "高院" });
  check("P2 非法法院类型拒绝", e2b.threw && e2b.message.includes("法院类型"), e2b.message.slice(0, 40));
  const e2c = await callExpectError("matterCreate", { name: "合成", claimAmountCents: 1.5 });
  check("P2 浮点金额拒绝（整型分纪律）", e2c.threw && e2c.message.includes("整型分"), e2c.message.slice(0, 40));
  const e2d = await callExpectError("matterCreate", { name: "合成", claimAmountCents: -5 });
  check("P2 负金额拒绝", e2d.threw, e2d.message.slice(0, 40));
  const e2e = await callExpectError("matterCreate", { name: "合成", judges: "不是数组" });
  check("P2 非数组当事人拒绝", e2e.threw && e2e.message.includes("judges"), e2e.message.slice(0, 40));

  // ── P3 状态两写同语句（手设→值+locked=1；恢复自动→NULL+locked=0）──
  const s1 = await call("matterUpdate", { id: c1.id, workflowStatus: "执行中" });
  check("P3 手设状态=值+locked", s1.workflowStatus === "执行中" && s1.workflowLocked === true,
    `status=${s1?.workflowStatus} locked=${s1?.workflowLocked}`);
  const s2 = await call("matterUpdate", { id: c1.id, workflowStatus: "已结案" });
  check("P3 换值仍 locked（两写同语句可持续翻转）", s2.workflowStatus === "已结案" && s2.workflowLocked === true,
    `status=${s2?.workflowStatus}`);
  const s3 = await call("matterUpdate", { id: c1.id, workflowStatus: null });
  check("P3 恢复自动=NULL+unlocked（协议面）", s3.workflowStatus === null && s3.workflowLocked === false,
    `status=${s3?.workflowStatus} locked=${s3?.workflowLocked}`);
  {
    const db = openDb();
    const row = db.prepare("SELECT workflow_status, workflow_locked FROM case_board_cases WHERE id = ?").get(c1.id);
    db.close();
    check("P3 恢复自动=NULL+unlocked（DB 直读核验同语句落位）", row?.workflow_status === null && row?.workflow_locked === 0,
      `db_status=${JSON.stringify(row?.workflow_status)} db_locked=${row?.workflow_locked}`);
  }
  const e3 = await callExpectError("matterUpdate", { id: c1.id, workflowStatus: "霸王档" });
  check("P3 11 档白名单外拒绝", e3.threw && e3.message.includes("接案"), e3.message.slice(0, 40));

  // ── P4 拖拽序 sortOrder ──
  const o1 = await call("matterUpdate", { id: c1.id, sortOrder: 3 });
  check("P4 拖拽序持久化", o1.sortOrder === 3, `sortOrder=${o1?.sortOrder}`);
  const o2 = await call("matterUpdate", { id: c1.id, sortOrder: null });
  check("P4 拖拽序清空（null 合法）", o2.sortOrder === null, `sortOrder=${o2?.sortOrder}`);
  const e4 = await callExpectError("matterUpdate", { id: c1.id, sortOrder: 1.5 });
  check("P4 浮点拖拽序拒绝", e4.threw, e4.message.slice(0, 40));

  // ── P5 覆盖层（merge 语义+校验 fail-closed+原字段不动+整体清除）──
  const v1 = await call("matterSetOverride", { id: c1.id, sourceKey: "timeline:hearing:doc-1",
    patch: { date: "2026-11-05", title: "开庭（改期）" } });
  check("P5 覆盖写入命中 sourceKey", v1?.overrides?.calendar_events?.["timeline:hearing:doc-1"]?.date === "2026-11-05"
    && v1.overrides.calendar_events["timeline:hearing:doc-1"].title === "开庭（改期）",
    JSON.stringify(v1?.overrides));
  check("P5 覆盖不动案件原字段（对拍行 89）", v1.name === "合成案件·借款合同纠纷" && v1.caseNo === "(2026)合0203民初9999号",
    `name=${v1?.name}`);
  await call("matterSetOverride", { id: c1.id, sourceKey: "timeline:preserve:bank-1", patch: { date: "2026-11-01", title: "续封（合成）" } });
  const v2 = await call("matterSetOverride", { id: c1.id, sourceKey: "timeline:hearing:doc-1", patch: { title: "开庭（再次改期）" } });
  const h5 = v2?.overrides?.calendar_events?.["timeline:hearing:doc-1"];
  check("P5 同键增量合并保留旧字段+他键并存",
    h5?.date === "2026-11-05" && h5?.title === "开庭（再次改期）"
      && Boolean(v2.overrides.calendar_events["timeline:preserve:bank-1"]),
    JSON.stringify(v2?.overrides));
  const e5a = await callExpectError("matterSetOverride", { id: c1.id, sourceKey: "  ", patch: { title: "x" } });
  check("P5 空 sourceKey 拒绝", e5a.threw && e5a.message.includes("sourceKey"), e5a.message.slice(0, 40));
  const e5b = await callExpectError("matterSetOverride", { id: c1.id, sourceKey: "k", patch: { date: "2026/11/05" } });
  check("P5 非法日期格式拒绝（服务端校验）", e5b.threw && e5b.message.includes("YYYY-MM-DD"), e5b.message.slice(0, 40));
  const e5c = await callExpectError("matterSetOverride", { id: c1.id, sourceKey: "k", patch: { title: "" } });
  check("P5 非隐藏空标题拒绝", e5c.threw && e5c.message.includes("标题"), e5c.message.slice(0, 40));
  const e5d = await callExpectError("matterSetOverride", { id: c1.id, sourceKey: "k", patch: { foo: 1 } });
  check("P5 白名单外覆盖字段拒绝", e5d.threw && e5d.message.includes("白名单"), e5d.message.slice(0, 40));
  const e5e = await callExpectError("matterSetOverride", { id: "mat_notexist", sourceKey: "k", patch: { title: "x" } });
  check("P5 不存在案件显式拒绝", e5e.threw && e5e.message.includes("不存在"), e5e.message.slice(0, 40));
  const v3 = await call("matterClearOverrides", { id: c1.id });
  check("P5 覆盖层整体清除（回空层）", JSON.stringify(v3?.overrides) === "{}", JSON.stringify(v3?.overrides));

  // ── P6 案内待办（打钩不删行/撤销清 done_at/校验负测）──
  const t1 = await call("matterTodoAdd", { caseId: c1.id, title: "合成待办·交证据", dueDate: "2026-11-01" });
  check("P6 待办创建带日期", t1?.title === "合成待办·交证据" && t1.dueDate === "2026-11-01" && t1.done === false,
    `id=${t1?.id} due=${t1?.dueDate}`);
  const t2 = await call("matterTodoAdd", { caseId: c1.id, title: "合成待办·无日期" });
  check("P6 无日期待办 dueDate=null", t2?.dueDate === null, `id=${t2?.id}`);
  const d1 = await call("matterTodoSetDone", { id: t1.id, done: true });
  const listT1 = await call("matterTodoList", { caseId: c1.id });
  check("P6 打钩翻位不删行+done_at 落位",
    d1.done === true && typeof d1.doneAt === "string" && listT1.todos.length === 2,
    `done=${d1?.done} doneAt=${d1?.doneAt ?? "无"} rows=${listT1.todos.length}`);
  const d2 = await call("matterTodoSetDone", { id: t1.id, done: false });
  check("P6 撤销清 done_at（行保留）", d2.done === false && d2.doneAt === null,
    `done=${d2?.done} doneAt=${JSON.stringify(d2?.doneAt)}`);
  const e6a = await callExpectError("matterTodoAdd", { caseId: "mat_notexist", title: "x" });
  check("P6 挂不存在案件显式拒绝", e6a.threw && e6a.message.includes("不存在"), e6a.message.slice(0, 40));
  const e6b = await callExpectError("matterTodoAdd", { caseId: c1.id, title: "" });
  check("P6 空待办标题拒绝", e6b.threw && e6b.message.includes("标题"), e6b.message.slice(0, 40));
  const e6c = await callExpectError("matterTodoAdd", { caseId: c1.id, title: "x", dueDate: "明天" });
  check("P6 坏待办日期拒绝", e6c.threw && e6c.message.includes("YYYY-MM-DD"), e6c.message.slice(0, 40));
  await call("matterTodoDelete", { id: t2.id });
  const listT2 = await call("matterTodoList", {});
  check("P6 待办删除生效", listT2.todos.length === 1, `rows=${listT2.todos.length}`);

  // ── P7 独立日程（date 升序/校验负测/更新）──
  const ev1 = await call("matterEventAdd", { date: "2026-11-02", title: "合成日程·立案缴费", note: "合成备注" });
  const ev2 = await call("matterEventAdd", { date: "2026-10-28", title: "合成日程·会见" });
  const listE = await call("matterEventList");
  check("P7 日程创建+date 升序列出",
    listE?.events?.length === 2 && listE.events[0].date === "2026-10-28" && listE.events[1].date === "2026-11-02",
    `dates=${listE?.events?.map((x) => x.date).join(",")}`);
  check("P7 note 落位", ev1?.note === "合成备注" && ev2?.note === null, `note=${ev1?.note}/${JSON.stringify(ev2?.note)}`);
  const e7a = await callExpectError("matterEventAdd", { date: "2026-11-02", title: "  " });
  check("P7 空日程标题拒绝（标题必填空拒）", e7a.threw && e7a.message.includes("标题"), e7a.message.slice(0, 40));
  const e7b = await callExpectError("matterEventAdd", { date: "2026-13-40", title: "x" });
  check("P7 假日历日拒绝（13 月 40 日）", e7b.threw && e7b.message.includes("YYYY-MM-DD"), e7b.message.slice(0, 40));
  const ev3 = await call("matterEventUpdate", { id: ev1.id, date: "2026-11-03", title: "合成日程·缴费（改期）" });
  check("P7 日程更新 round-trip", ev3?.date === "2026-11-03" && ev3.title === "合成日程·缴费（改期）",
    `date=${ev3?.date}`);
  await call("matterEventDelete", { id: ev1.id });
  const listE2 = await call("matterEventList");
  check("P7 日程删除生效", listE2.events.length === 1, `rows=${listE2.events.length}`);

  // ── P8 案件删除级联清案内待办（FK CASCADE）──
  const c2 = await call("matterCreate", { name: "合成案件·将删除" });
  await call("matterTodoAdd", { caseId: c2.id, title: "合成待办·随案删" });
  await call("matterDelete", { id: c2.id });
  const listT3 = await call("matterTodoList", {});
  const listC3 = await call("matterList");
  check("P8 案件删除+待办级联清", listT3.todos.every((t) => t.caseId !== c2.id) && listC3.cases.length === 2,
    `todoRows=${listT3.todos.length} caseRows=${listC3.cases.length}`);
  const e8 = await callExpectError("matterDelete", { id: "mat_notexist" });
  check("P8 删不存在案件显式拒绝", e8.threw && e8.message.includes("不存在"), e8.message.slice(0, 40));

  // ── P9 杀桥重启：数据不丢+迁移账本不重放 ──
  const migCountBefore = (() => { const db = openDb(); const n = db.prepare("SELECT COUNT(*) AS n FROM schema_migration").get().n; db.close(); return n; })();
  await killBridge("P9 重启实测");
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error("P9 重启桥 40s 不可探");
  await connect();
  const listR = await call("matterList");
  const rc1 = listR.cases.find((x) => x.id === c1.id);
  check("P9 重启后案件行完整（字段全等）",
    rc1?.name === "合成案件·借款合同纠纷" && rc1.courtType === "法院" && rc1.claimAmountCents === 1234567
      && JSON.stringify(rc1.defendants) === JSON.stringify(["合成乙", "合成丙"])
      && rc1.workflowStatus === null && rc1.workflowLocked === false,
    `cases=${listR.cases.length}`);
  const rv = await call("matterSetOverride", { id: c1.id, sourceKey: "timeline:hearing:doc-1",
    patch: { date: "2026-11-05", title: "开庭（改期）" } });
  check("P9 重启后覆盖层可写（三表迁移完好）",
    rv?.overrides?.calendar_events?.["timeline:hearing:doc-1"]?.date === "2026-11-05", "override 写回 OK");
  const listR3 = await call("matterTodoList", {});
  check("P9 重启后待办仍在", listR3.todos.length === 1 && listR3.todos[0].title === "合成待办·交证据",
    `rows=${listR3.todos.length}`);
  const listR4 = await call("matterEventList");
  check("P9 重启后日程仍在", listR4.events.length === 1 && listR4.events[0].title === "合成日程·会见",
    `rows=${listR4.events.length}`);
  {
    const db = openDb();
    const migCountAfter = db.prepare("SELECT COUNT(*) AS n FROM schema_migration").get().n;
    const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'case_board%' ORDER BY name").all().map((r) => r.name);
    db.close();
    check("P9 迁移账本不重放+三表在库",
      migCountAfter === migCountBefore
        && JSON.stringify(tables) === JSON.stringify(["case_board_cases", "case_board_events", "case_board_todos"]),
      `mig=${migCountAfter}/${migCountBefore} tables=${tables.join(",")}`);
  }

  // ── P10 清场（自管测试数据不留库）──
  await call("matterClearOverrides", { id: c1.id });
  await call("matterDelete", { id: c1.id });
  await call("matterDelete", { id: arb.id });
  await call("matterEventDelete", { id: ev2.id });
  const finC = await call("matterList");
  const finE = await call("matterEventList");
  check("P10 清场（案件/日程归零）", finC.cases.length === 0 && finE.events.length === 0,
    `cases=${finC.cases.length} events=${finE.events.length}`);
} catch (e) {
  check("用例执行", false, e?.message ?? String(e));
} finally {
  try { await call("dispose"); } catch { /* 断连即可 */ }
  if (bridgePid) {
    try {
      if ((await commandLineOf(bridgePid)).includes("bridge_host.mjs")) {
        spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
      }
    } catch { /* 已死则忽略 */ }
  }
}

const pass = results.every((r) => r.ok);
console.log(pass ? "MATTER_SYNTH_PASS" : "MATTER_SYNTH_FAIL");
process.exit(pass ? 0 : 1);
