// 【步骤4·#3 看板日历面】桥面日程扩展+agent 可读查询+提醒引擎纯函数 合成用例（全部合成材料）：
//   P1-P7 走自管隔离桥实例（:3065 独立库，BRIDGE_BOARD_DAY_FIRE_TIME=08:30 证「09:00 桥常量可配」）：
//     ①日程新字段 CRUD round-trip（kind/地点/起止默认 10:00-11:00/关联案件/出行项/提醒开关+提前分钟）；
//     ②负测（kind 白名单/HH:MM/结束<=开始/负提前量/浮点/未知关联案件/空标题/假日历日/limit 越界）；
//     ③matterEventList 返回 dayFireTime（可配实测）；④matterScheduleQuery 窗口/案件过滤/排序/limit/只读；
//     ⑤matterTaskQuery done/案件过滤/排序（done ASC、due ASC、NULL 沉底）；⑥案件删→日程解绑+待办级联；
//     ⑦杀桥重启新列字段全等+迁移账本不重放。
//   E1-E9 纯函数（不经桥，直 import UI 侧模块）：
//     提醒引擎（等量 LX reminders.js 实跑 X1/X2 口径：提前窗内开火/未到跳/24h 外跳/错过 +2min 不补发/
//     宽限 30s 内开火/fired 去重/date-only 09:00 归一/已完成待办跳/remind=0 跳/逐条提前量/title 固定+
//     body=标题 · 开始时间/改期=新键）；月历 42 格周一起；阶梯四桶；案件下一节点。
//   E14-E18 整编/状态机/案件列表面（件5/补齐件2/补齐件3）；E20 r9 补齐件4（行24 开庭 session 去重并
//   显示路径/行66 最近期限风险徽章）。
// 末行 BOARD_SYNTH_PASS / BOARD_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { openSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import {
  BOARD_FIRE_GRACE_MS, BOARD_24H_WINDOW_MS, boardFireKey, boardFireMomentMs,
  scanBoardReminders,
} from "../../packages/juscite-legal/src/panels/boardReminder.ts";
import {
  boardCellDotColor, boardDeadlineLadder, boardMonthCells, boardNextCaseNode, boardShapeTimelineRows,
  boardTodayStr,
} from "../../packages/juscite-legal/src/panels/boardCalendar.ts";
import {
  BOARD_STATUS_NAMES, boardDisplayStatus, boardSignalsFromRows, boardSortCasesByBucket,
  boardStatusBucket, inferBoardWorkflowStatus,
} from "../../packages/juscite-legal/src/panels/boardStatus.ts";
import { MATTER_STATUS_DEFS } from "./matter_service.mjs";
import {
  briefingLevel, buildImportantReminders, boardDeleteConfirmCopy, importantCountdown,
} from "../../packages/juscite-legal/src/panels/boardImportant.ts";
import {
  cnDateString, cnNumber, boardDedupTimelineHearings, dedupHearingsBySession, durationMonths,
  extractPreservationClauses, hearingSessionKeyOf, suppressedByUnseal,
} from "../../packages/juscite-legal/src/panels/boardPreservation.ts";
import {
  boardApplyDragOrder, boardCaseGate, boardDeadlineRiskOf, boardDragOrderSeq, boardFilingDateOf,
  boardFocusItem, boardHearingDisplayTitle, boardNextHearingDateOf, boardRecentGroups,
  boardSortCasesByKey, boardStatusWeight, boardYuan, filterCasesByDomain, isCriminalCase,
} from "../../packages/juscite-legal/src/panels/boardCaseList.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3065);
const NODE = process.execPath;
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok });
  console.log(`[board-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function dbPath() { return join(process.env.APPDATA ?? "", "Juscite", "bridge", `bridge-${PORT}.db`); }
function openDb() { return new DatabaseSync(dbPath()); }

let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, ".local", `board-synth-bridge-${PORT}.log`), "a");
function spawnBridge() {
  const env = { ...process.env, BRIDGE_PORT: String(PORT), BRIDGE_BOARD_DAY_FIRE_TIME: "08:30" };
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
async function clearStaleBridge() {
  for (const pid of findListenerPids(PORT)) {
    const line = await commandLineOf(pid);
    if (!line.includes("bridge_host.mjs")) {
      throw new Error(`:${PORT} 被非桥进程占用（pid=${pid}），不接触`);
    }
    console.log(`[board-synth] 清残留桥 pid=${pid}`);
    spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
  }
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probe())) await sleep(500);
}
async function callExpectError(name, params) {
  try { await call(name, params); return { threw: false, message: "" }; }
  catch (e) { return { threw: true, message: String(e?.message ?? e) }; }
}

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
  for (const suffix of ["", "-wal", "-shm"]) {
    try { unlinkSync(dbPath() + suffix); } catch { /* 不存在即可 */ }
  }
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error(`隔离桥 :${PORT} 40s 不可探`);
  await connect();

  // ── P1 日程新字段 CRUD round-trip ──
  const c1 = await call("matterCreate", { name: "合成案件·看板联动" });
  const ev1 = await call("matterEventAdd", {
    date: "2026-11-02", title: "合成日程·开庭", kind: "hearing", location: "合成区法院第3法庭",
    startAt: "09:00", endAt: "11:00", caseId: c1.id, trip: "乘地铁2号线 8:00 出发",
    remind: true, remindMinutes: 45, note: "带证据原件",
  });
  check("P1 全字段 round-trip",
    ev1.kind === "hearing" && ev1.location === "合成区法院第3法庭" && ev1.startAt === "09:00" && ev1.endAt === "11:00"
      && ev1.caseId === c1.id && ev1.trip === "乘地铁2号线 8:00 出发" && ev1.remind === true && ev1.remindMinutes === 45,
    JSON.stringify(ev1));
  const ev2 = await call("matterEventAdd", { date: "2026-11-03", title: "合成日程·默认面" });
  check("P1 默认面（kind=schedule/date-only 无时刻/提醒关/提前量默认30）",
    ev2.kind === "schedule" && ev2.startAt === null && ev2.endAt === null && ev2.remind === false
      && ev2.remindMinutes === 30 && ev2.caseId === null && ev2.trip === "" && ev2.location === "",
    JSON.stringify(ev2));
  const ev3 = await call("matterEventAdd", { date: "2026-11-05", title: "合成日程·带时刻", startAt: "14:00", endAt: "16:00" });
  check("P1 带时刻 round-trip", ev3.startAt === "14:00" && ev3.endAt === "16:00",
    `${ev3.startAt}-${ev3.endAt}`);
  const ev4 = await call("matterEventAdd", { date: "2026-11-06", title: "合成日程·期限类", kind: "deadline", remind: true });

  // ── P2 负测（fail-closed 显式报错）──
  const neg = async (name, params, frag) => {
    const r = await callExpectError("matterEventAdd", params);
    check(name, r.threw && r.message.includes(frag), r.message.slice(0, 50));
  };
  await neg("P2 kind 白名单外拒绝", { date: "2026-11-02", title: "x", kind: "party" }, "日程分类");
  await neg("P2 坏时刻拒绝", { date: "2026-11-02", title: "x", startAt: "9:00" }, "HH:MM");
  await neg("P2 结束<=开始拒绝", { date: "2026-11-02", title: "x", startAt: "11:00", endAt: "10:00" }, "结束时刻");
  await neg("P2 负提前量拒绝", { date: "2026-11-02", title: "x", remind: true, remindMinutes: -3 }, "非负整数");
  await neg("P2 浮点提前量拒绝", { date: "2026-11-02", title: "x", remindMinutes: 1.5 }, "非负整数");
  await neg("P2 未知关联案件拒绝", { date: "2026-11-02", title: "x", caseId: "mat_nope" }, "关联案件不存在");
  await neg("P2 空标题拒绝", { date: "2026-11-02", title: "  " }, "标题");
  await neg("P2 假日历日拒绝", { date: "2026-02-30", title: "x" }, "YYYY-MM-DD");
  const upd = await callExpectError("matterEventUpdate", { id: ev1.id, endAt: "08:00" }); // ev1 起止 09:00-11:00
  check("P2 更新与库中现值合并校验（结束<=开始）", upd.threw && upd.message.includes("结束时刻"), upd.message.slice(0, 50));
  const upd2 = await call("matterEventUpdate", { id: ev2.id, endAt: "09:00" }); // date-only 行单给 endAt 合法
  check("P2b date-only 行单给 endAt 合法（桥存诚实值）", upd2.endAt === "09:00" && upd2.startAt === null,
    `${upd2.startAt}-${upd2.endAt}`);
  const updNon = await callExpectError("matterEventUpdate", { id: ev2.id, foo: 1 });
  check("P2 无可更新字段拒绝", updNon.threw && updNon.message.includes("无可更新字段"), updNon.message.slice(0, 40));

  // ── P3 matterEventList 带 dayFireTime（桥常量可配：本实例 BRIDGE_BOARD_DAY_FIRE_TIME=08:30）──
  const list1 = await call("matterEventList");
  check("P3 dayFireTime 可配生效（env 覆盖 09:00→08:30）", list1?.dayFireTime === "08:30",
    `dayFireTime=${list1?.dayFireTime}`);
  check("P3 列表排序（日期升序；同日有时刻按 start_at）",
    list1.events.length === 4
      && list1.events.map((e) => e.id).join(",") === [ev1.id, ev2.id, ev3.id, ev4.id].join(",")
      && list1.events[0].startAt === "09:00" && list1.events[1].startAt === null,
    list1.events.map((e) => `${e.date}${e.startAt ?? "-"}`).join("/"));

  // ── P4 matterScheduleQuery（agent 可读日程面，对拍行 86）──
  const q1 = await call("matterScheduleQuery", { from: "2026-11-02", to: "2026-11-03" });
  check("P4 日期窗口过滤", q1.events.length === 2 && q1.events.every((e) => e.date >= "2026-11-02" && e.date <= "2026-11-03"),
    `rows=${q1.events.length}`);
  const q1b = await call("matterScheduleQuery", { kind: undefined });
  const q2 = await call("matterScheduleQuery", { caseId: c1.id });
  check("P4 案件过滤", q2.events.length === 1 && q2.events[0].caseId === c1.id, `rows=${q2.events.length}`);
  const q3 = await call("matterScheduleQuery", { limit: 2 });
  check("P4 limit 截断+升序", q3.events.length === 2 && q3.events[0].date <= q3.events[1].date,
    q3.events.map((e) => e.date).join(","));
  const q4 = await call("matterScheduleQuery", {});
  check("P4 全量缺省 limit=20", q4.events.length === 4, `rows=${q4.events.length}`);
  void q1b;
  for (const bad of [0, 51, 1.5, "x"]) {
    const r = await callExpectError("matterScheduleQuery", { limit: bad });
    check(`P4 非法 limit=${JSON.stringify(bad)} 拒绝（1..50）`, r.threw && r.message.includes("1..50"), r.message.slice(0, 40));
  }
  const r4 = await callExpectError("matterScheduleQuery", { from: "11月2日" });
  check("P4 非法 from 日期拒绝", r4.threw && r4.message.includes("YYYY-MM-DD"), r4.message.slice(0, 40));
  const q5 = await call("matterScheduleQuery", { caseId: "mat_nope" });
  check("P4 未知案件=空集（读面过滤语义，不伪造错误）", Array.isArray(q5.events) && q5.events.length === 0, "empty");

  // ── P5 matterTaskQuery（agent 可读任务面）──
  const t1 = await call("matterTodoAdd", { caseId: c1.id, title: "合成待办·甲", dueDate: "2026-11-01" });
  const t2 = await call("matterTodoAdd", { caseId: c1.id, title: "合成待办·乙", dueDate: "2026-10-28" });
  const t3 = await call("matterTodoAdd", { caseId: c1.id, title: "合成待办·无期限" });
  await call("matterTodoSetDone", { id: t1.id, done: true });
  const tq1 = await call("matterTaskQuery", { done: false });
  check("P5 done=false 过滤（已完成不出现）", tq1.tasks.length === 2 && tq1.tasks.every((x) => !x.done),
    `rows=${tq1.tasks.length}`);
  check("P5 排序 done ASC + due ASC（未完成先，期限早者先，NULL 沉底）",
    tq1.tasks[0].id === t2.id && tq1.tasks[1].id === t3.id, tq1.tasks.map((x) => x.title).join("/"));
  const tq2 = await call("matterTaskQuery", { caseId: "mat_nope", limit: 5 });
  check("P5 未知案件=空集+limit 生效", tq2.tasks.length === 0, "empty");
  const tq3 = await call("matterTaskQuery", { done: true });
  check("P5 done=true 过滤", tq3.tasks.length === 1 && tq3.tasks[0].id === t1.id, `rows=${tq3.tasks.length}`);

  // ── P6 案件删除→日程解绑+待办级联 ──
  const c2 = await call("matterCreate", { name: "合成案件·将删除" });
  await call("matterEventAdd", { date: "2026-11-06", title: "合成日程·随案解绑", caseId: c2.id });
  await call("matterTodoAdd", { caseId: c2.id, title: "合成待办·随案删" });
  await call("matterDelete", { id: c2.id });
  const list2 = await call("matterEventList");
  const tq4 = await call("matterTaskQuery", {});
  const freed = list2.events.find((e) => e.title === "合成日程·随案解绑");
  check("P6 案件删→日程 case_id 置空（防悬空引用）", Boolean(freed) && freed.caseId === null, `caseId=${freed?.caseId}`);
  check("P6 案件删→待办级联清", tq4.tasks.every((x) => x.caseId !== c2.id), "cascaded");

  // ── P7 杀桥重启：新列字段全等+迁移账本不重放 ──
  const migBefore = (() => { const db = openDb(); const n = db.prepare("SELECT COUNT(*) AS n FROM schema_migration").get().n; db.close(); return n; })();
  await killBridge("P7 重启实测");
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error("P7 重启桥 40s 不可探");
  await connect();
  const listR = await call("matterEventList");
  const re1 = listR.events.find((e) => e.id === ev1.id);
  check("P7 重启后新列字段全等",
    re1.kind === "hearing" && re1.location === "合成区法院第3法庭" && re1.startAt === "09:00" && re1.endAt === "11:00"
      && re1.caseId === c1.id && re1.trip === "乘地铁2号线 8:00 出发" && re1.remind === true && re1.remindMinutes === 45,
    JSON.stringify(re1));
  check("P7 重启后 dayFireTime 配置仍在", listR.dayFireTime === "08:30", `${listR.dayFireTime}`);
  {
    const db = openDb();
    const migAfter = db.prepare("SELECT COUNT(*) AS n FROM schema_migration").get().n;
    const cols = db.prepare("PRAGMA table_info(case_board_events)").all().map((r) => r.name);
    db.close();
    check("P7 迁移账本不重放+0007 新列在库",
      migAfter === migBefore
        && ["case_id", "kind", "location", "start_at", "end_at", "trip", "remind", "remind_minutes"]
          .every((c) => cols.includes(c)),
      `mig=${migAfter}/${migBefore} cols=${cols.join(",")}`);
  }

  // ── P8 清场（自管测试数据不留库）──
  await call("matterDelete", { id: c1.id });
  for (const e of listR.events) await call("matterEventDelete", { id: e.id });
  const finC = await call("matterList");
  const finE = await call("matterEventList");
  check("P8 清场归零", finC.cases.length === 0 && finE.events.length === 0,
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

// ════════ 纯函数段（不经桥）：提醒引擎 X1/X2 等量 + 月历/阶梯/节点 ════════
try {
  const T0 = boardFireMomentMs("2026-11-02", "09:00");
  if (T0 === null) throw new Error("boardFireMomentMs 基准时刻解析失败");
  const baseEvents = (over) => [{
    id: "e1", date: "2026-11-02", title: "合成开庭", startAt: "09:00",
    remind: true, remindMinutes: 30, ...over,
  }];
  const emptyTodos = [];

  // E1 提前窗内开火（start-30min 恰好进窗）
  const r1 = scanBoardReminders({ events: baseEvents({}), todos: emptyTodos, nowMs: T0 - 30 * 60_000, firedKeys: new Set(), dayFireTime: "09:00", fixedTitle: "Juscite 提醒" });
  check("E1 提前窗起点开火（start-30min）", r1.fire.length === 1 && r1.fire[0].sourceId === "e1", `n=${r1.fire.length}`);

  // E2 提前窗前不触发（自定义提前 5min 未到跳——X1 口径）
  const r2 = scanBoardReminders({ events: baseEvents({ remindMinutes: 5 }), todos: emptyTodos, nowMs: T0 - 30 * 60_000, firedKeys: new Set(), dayFireTime: "09:00", fixedTitle: "Juscite 提醒" });
  check("E2 提前量 5min 未到窗不触发", r2.fire.length === 0, `n=${r2.fire.length}`);

  // E3 24h 外不开火（提前量 30h 大于 24h 窗仍不开）
  const r3 = scanBoardReminders({ events: baseEvents({ remindMinutes: 1800 }), todos: emptyTodos, nowMs: T0 - 29 * 3600_000, firedKeys: new Set(), dayFireTime: "09:00", fixedTitle: "Juscite 提醒" });
  check("E3 开火 24h 外不开火（大提前量同拦）", r3.fire.length === 0, `n=${r3.fire.length}`);
  const r3b = scanBoardReminders({ events: baseEvents({ date: "2026-11-04", startAt: null }), todos: emptyTodos, nowMs: T0, firedKeys: new Set(), dayFireTime: "09:00", fixedTitle: "Juscite 提醒" });
  check("E3b date-only 且距开火 >24h 不开火", r3b.fire.length === 0, `n=${r3b.fire.length}`);

  // E4 错过窗口（+2min）不补发；宽限内（+30s）仍开火（X1 口径）
  const r4 = scanBoardReminders({ events: baseEvents({}), todos: emptyTodos, nowMs: T0 + 2 * 60_000, firedKeys: new Set(), dayFireTime: "09:00", fixedTitle: "Juscite 提醒" });
  check("E4 错过 +2min 不补发", r4.fire.length === 0, `n=${r4.fire.length}`);
  const r4b = scanBoardReminders({ events: baseEvents({}), todos: emptyTodos, nowMs: T0 + 30_000, firedKeys: new Set(), dayFireTime: "09:00", fixedTitle: "Juscite 提醒" });
  check("E4b 宽限 30s 内开火（60s 宽限）", r4b.fire.length === 1, `n=${r4b.fire.length}`);
  if (BOARD_FIRE_GRACE_MS !== 60_000 || BOARD_24H_WINDOW_MS !== 86_400_000) {
    throw new Error("引擎窗口常量偏离 LX 口径");
  }

  // E5 fired 集合二次扫描去重（X1 口径）
  const r5a = scanBoardReminders({ events: baseEvents({}), todos: emptyTodos, nowMs: T0 - 60_000, firedKeys: new Set(), dayFireTime: "09:00", fixedTitle: "Juscite 提醒" });
  const r5b = scanBoardReminders({ events: baseEvents({}), todos: emptyTodos, nowMs: T0 - 30_000, firedKeys: r5a.firedKeys, dayFireTime: "09:00", fixedTitle: "Juscite 提醒" });
  check("E5 首扫开火+二扫去重", r5a.fire.length === 1 && r5b.fire.length === 0,
    `a=${r5a.fire.length} b=${r5b.fire.length}`);

  // E6 date-only 行按 dayFireTime 归一（桥常量可配：08:30 实测进窗判定）
  const r6 = scanBoardReminders({ events: baseEvents({ startAt: null }), todos: emptyTodos, nowMs: boardFireMomentMs("2026-11-02", "08:05"), firedKeys: new Set(), dayFireTime: "08:30", fixedTitle: "Juscite 提醒" });
  check("E6 date-only 按 dayFireTime=08:30 归一进窗", r6.fire.length === 1, `n=${r6.fire.length}`);

  // E7 待办：未完成+dueDate 开火；已完成跳；无日期跳
  const todos = [
    { id: "t1", caseId: "c1", title: "合成待办·到期", done: false, dueDate: "2026-11-02" },
    { id: "t2", caseId: "c1", title: "合成待办·已完", done: true, dueDate: "2026-11-02" },
    { id: "t3", caseId: "c1", title: "合成待办·无期", done: false, dueDate: null },
  ];
  const r7 = scanBoardReminders({ events: [], todos, nowMs: boardFireMomentMs("2026-11-02", "08:30"), firedKeys: new Set(), dayFireTime: "08:30", fixedTitle: "Juscite 提醒" });
  check("E7 待办仅未完成+有日期开火（09:00 归一，此处 08:30 配置）",
    r7.fire.length === 1 && r7.fire[0].source === "todo" && r7.fire[0].sourceId === "t1",
    JSON.stringify(r7.fire));

  // E8 remind=0 日程永不触发；通知形状=title 固定 + body=标题 · 开始时间（对拍行 85）
  const r8 = scanBoardReminders({ events: baseEvents({ remind: false }), todos: emptyTodos, nowMs: T0, firedKeys: new Set(), dayFireTime: "09:00", fixedTitle: "Juscite 提醒" });
  check("E8 remind=0 不触发", r8.fire.length === 0, `n=${r8.fire.length}`);
  check("E8 通知形状（title 固定+body=标题 · 开始时间）",
    r5a.fire[0].title === "Juscite 提醒" && r5a.fire[0].body === "合成开庭 · 11-02 09:00",
    `${r5a.fire[0].title} | ${r5a.fire[0].body}`);

  // E9 改期=新键=新提醒（去重键含开火时刻）
  const moved = scanBoardReminders({ events: baseEvents({ date: "2026-11-03" }), todos: emptyTodos, nowMs: boardFireMomentMs("2026-11-03", "08:30"), firedKeys: r5a.firedKeys, dayFireTime: "09:00", fixedTitle: "Juscite 提醒" });
  check("E9 改期后新键开火（旧键不拦截）", moved.fire.length === 1
    && moved.fire[0].key !== [...r5a.firedKeys][0], `n=${moved.fire.length}`);
  check("E9 键形状含开火时刻", boardFireKey("evt", "e1", 1) === "evt:e1@1", boardFireKey("evt", "e1", 1));

  // E10 月历 42 格周一起（对拍行 28）：2026-11-01 是周日→首格 10-26 周一
  const cells = boardMonthCells(2026, 11);
  check("E10 月历 42 格+周一起（2026-11-01 周日→下标 6）",
    cells.length === 42 && cells[0].date === "2026-10-26" && !cells[0].inMonth
      && cells[6].date === "2026-11-01" && cells[6].inMonth,
    `first=${cells[0].date} n=${cells.length}`);

  // E11 期限阶梯四桶（对拍行 91：<0 已逾期/0..3/4..7/8..30；30 天外不进窗）
  const ladder = boardDeadlineLadder([
    { id: "a", title: "逾期项", dueDate: "2026-10-25" },
    { id: "b", title: "3日内", dueDate: "2026-10-28" },
    { id: "c", title: "7日内", dueDate: "2026-11-01" },
    { id: "d", title: "30日内", dueDate: "2026-11-20" },
    { id: "e", title: "窗外", dueDate: "2026-12-20" },
  ], "2026-10-27");
  check("E11 阶梯四桶计数（逾期1/3日1/7日1/30日1/窗外不计）",
    JSON.stringify(ladder.map((b) => b.count)) === JSON.stringify([1, 1, 1, 1])
      && ladder[0].items[0].daysLeft === -2 && ladder[3].items[0].daysLeft === 24,
    JSON.stringify(ladder.map((b) => b.count)));

  // E12 案件下一节点：最早未来绑定节点；过往不占位；未绑定不出现
  const nodes = boardNextCaseNode([
    { id: "n1", date: "2026-10-20", title: "过往开庭", caseId: "cA" },
    { id: "n2", date: "2026-11-10", title: "举证期限截止", caseId: "cA" },
    { id: "n3", date: "2026-11-05", title: "证据质证", caseId: "cA" },
    { id: "n4", date: "2026-11-01", title: "别案节点", caseId: "cB" },
  ], "cA", "2026-10-27");
  check("E12 下一节点=最早未来绑定（11-05 证据质证，9 天后）",
    nodes !== null && nodes.date === "2026-11-05" && nodes.title === "证据质证" && nodes.daysAway === 9,
    JSON.stringify(nodes));
  check("E12b 无未来节点返回 null", boardNextCaseNode([
    { id: "n1", date: "2026-10-20", title: "过往", caseId: "cA" },
  ], "cA", "2026-10-27") === null, "null");

  check("E13 today 格式（本地日历日 YYYY-MM-DD）", /^\d{4}-\d{2}-\d{2}$/.test(boardTodayStr()), boardTodayStr());

  // E14 时间线行整编（#4 翻牌 defect 回归针：2026-10-28 走查 W12 实证建案/孪生行污染）
  //   案 cA：建案(今天,行政)+任务登记(+2,行政)+开庭排期(+9,孪生)+保全(+15,真节点)；
  //   日程行：e9(+9 证据质证,案绑)=孪生原体。
  const tlRows = [
    { id: "cev:a1", date: "2026-10-27", title: "建案", caseId: "cA", kind: "schedule" },
    { id: "cev:a2", date: "2026-10-29", title: "任务登记", caseId: "cA", kind: "schedule" },
    { id: "cev:a3", date: "2026-11-05", title: "开庭排期", caseId: "cA", kind: "hearing" },
    { id: "cev:a4", date: "2026-11-11", title: "保全", caseId: "cA", kind: "deadline" },
    { id: "cev:x1", date: "2026-11-01", title: "别案建案", caseId: "cB", kind: "schedule" },
  ];
  const boardEvts = [{ id: "evt:z9", date: "2026-11-05", title: "证据质证", caseId: "cA" }];
  // E14a 阶段节点视图：行政行(schedule)全剔+孪生让位→节点=保全(+15)；非孪生 hearing/deadline 留
  const stageSrc = boardShapeTimelineRows(tlRows, boardEvts, true);
  check("E14a 阶段视图剔行政行+孪生让位",
    JSON.stringify(stageSrc.map((r) => r.id)) === JSON.stringify(["cev:a4"]),
    JSON.stringify(stageSrc.map((r) => r.id)));
  const nodeShaped = boardNextCaseNode([...boardEvts, ...stageSrc], "cA", "2026-10-27");
  check("E14b 整编后下一节点=真里程碑（日程行 +9 证据质证，非建案今天）",
    nodeShaped !== null && nodeShaped.title === "证据质证" && nodeShaped.date === "2026-11-05" && nodeShaped.daysAway === 9,
    JSON.stringify(nodeShaped));
  check("E14c 未整编对照（defect 复现）：建案(今天)恒压过里程碑",
    boardNextCaseNode([...boardEvts, ...tlRows.filter((r) => r.caseId === "cA")], "cA", "2026-10-27")?.title === "建案",
    "defect shape");
  // E14d 日历视图：孪生让位但行政事实行保留（建案/别案行留，孪生开庭排期剔）
  const calSrc = boardShapeTimelineRows(tlRows, boardEvts, false);
  check("E14d 日历视图剔孪生留行政事实行",
    JSON.stringify(calSrc.map((r) => r.id)) === JSON.stringify(["cev:a1", "cev:a2", "cev:a4", "cev:x1"]),
    JSON.stringify(calSrc.map((r) => r.id)));

  // ══ E15-E17（状态机面补齐件：对拍行 40-44 纯函数针）══
  // E15a 单源对拍：UI 枚举与桥校验枚举同串同序（对拍行 40 单源）
  check("E15a 11 档枚举与桥单源同串同序",
    JSON.stringify(BOARD_STATUS_NAMES) === JSON.stringify(MATTER_STATUS_DEFS) && BOARD_STATUS_NAMES.length === 11,
    `${BOARD_STATUS_NAMES.length}档`);
  // E15b 推断优先级链全路径（对拍行 41；CB-B5 同链同序）
  const chainCases: Array<[Parameters<typeof inferBoardWorkflowStatus>[0], string]> = [
    [{ execution: true, judgment: true }, "执行中"],
    [{ retrial: true, secondInstance: true }, "再审中"],
    [{ secondInstance: true, mediation: true }, "二审中"],
    [{ mediation: true, judgment: true }, "已调解"], // 调解压过判决
    [{ judgment: true, acceptance: true }, "上诉期"],
    [{ hearingDates: ["2026-10-20"], acceptance: true }, "审理中"], // 已开庭
    [{ hearingDates: ["2026-10-27"], today: "2026-10-27" }, "审理中"], // 开庭=今日
    [{ hearingDates: ["2026-11-30"] }, "接案"], // 未来开庭不=已开
    [{ courtSessionRecord: true }, "审理中"],
    [{ acceptance: true, complaint: true }, "待开庭"],
    [{ complaint: true, arbitrationOnly: true }, "立案中"],
    [{ arbitrationOnly: true }, "仲裁中"],
    [{ engagement: true }, "接案"],
    [{}, "接案"], // 默认
  ];
  const chainBad = chainCases.filter(([sig, want]) => inferBoardWorkflowStatus(sig, "2026-10-27") !== want);
  check("E15b 推断链 14 针全中（含调解压判决/开庭今日边界/默认接案）", chainBad.length === 0,
    JSON.stringify(chainBad.map(([, w]) => w)));
  check("E15c 链永不自动已结案（全线索齐射仍=执行中）",
    inferBoardWorkflowStatus({ execution: true, retrial: true, secondInstance: true, mediation: true,
      judgment: true, hearingDates: ["2026-01-01"], courtSessionRecord: true, acceptance: true,
      complaint: true, arbitrationOnly: true, engagement: true }, "2026-10-27") === "执行中",
    "no-closed");
  // E15d 时间线/案绑日程行→线索映射
  const m1 = inferBoardWorkflowStatus(boardSignalsFromRows([
    { type: "还款期", date: "2026-12-01" }, { type: "执行立案" }]), "2026-10-27");
  const m2 = inferBoardWorkflowStatus(boardSignalsFromRows([{ type: "开庭", date: "2026-10-01" }]), "2026-10-27");
  const m3 = inferBoardWorkflowStatus(boardSignalsFromRows([{ type: "正式立案" }]), "2026-10-27");
  const m4 = inferBoardWorkflowStatus(boardSignalsFromRows([{ type: "申请立案" }, { type: "保全" }]), "2026-10-27");
  check("E15d 行映射：执行立案→执行中/开庭已过→审理中/正式立案→待开庭/申请立案+保全→立案中",
    m1 === "执行中" && m2 === "审理中" && m3 === "待开庭" && m4 === "立案中",
    `${m1}/${m2}/${m3}/${m4}`);
  // E16 locked 展示三态（对拍行 42；§3.3 公式）
  check("E16 locked=1 用户值压倒（即使=接案）",
    boardDisplayStatus({ locked: true, userValue: "接案", userHistory: null, inferred: "审理中" }) === "接案",
    "locked-wins");
  check("E16 locked=0 推断非接案优先",
    boardDisplayStatus({ locked: false, userValue: null, userHistory: "待开庭", inferred: "二审中" }) === "二审中",
    "infer-first");
  check("E16 locked=0 推断接案→历史兜底位（null 落推断）",
    boardDisplayStatus({ locked: false, userValue: null, userHistory: null, inferred: "接案" }) === "接案"
      && boardDisplayStatus({ locked: false, userValue: null, userHistory: "待开庭", inferred: "接案" }) === "待开庭",
    "history-fallback");
  // E17 默认排序桶（对拍行 44；CB-B6：在办<已调解<已结案，桶内 updated 倒序）
  const sorted = boardSortCasesByBucket([
    { id: "a", workflowStatus: "已结案", updatedAt: "2026-10-01T10:00:00Z" },
    { id: "b", workflowStatus: null, updatedAt: "2026-10-03T10:00:00Z" },
    { id: "c", workflowStatus: "已调解", updatedAt: "2026-10-05T10:00:00Z" },
    { id: "d", workflowStatus: "审理中", updatedAt: "2026-10-02T10:00:00Z" },
    { id: "e", workflowStatus: null, updatedAt: "2026-10-04T10:00:00Z" },
  ]);
  check("E17 桶序+桶内 updated 倒序+已结案沉底",
    JSON.stringify(sorted.map((x) => x.id)) === JSON.stringify(["e", "b", "d", "c", "a"]),
    JSON.stringify(sorted.map((x) => x.id)));
  check("E17b 桶值（已结案=2/已调解=1/其余=0）",
    boardStatusBucket("已结案") === 2 && boardStatusBucket("已调解") === 1 && boardStatusBucket("执行中") === 0
      && boardStatusBucket(null) === 0, "buckets");

  // ══ F 段（补齐件：保全面/重要位/简报/色点/删除文案）══
  // F1 保全抽取：四类资产+中文数字+日期窗+动作归一（CB-B7/B8 口径）
  const p1 = extractPreservationClauses("冻结被申请人银行账户一年。", "2026-10-27");
  check("F1 银行账户一年→续冻 12 个月（起=基准日）",
    p1.length === 1 && p1[0].label === "银行账户" && p1[0].action === "续冻"
      && p1[0].startDate === "2026-10-27" && p1[0].expiresAt === "2027-10-27",
    JSON.stringify(p1[0]));
  const p2 = extractPreservationClauses("查封其名下车辆，期限二年。", "2026-10-27");
  check("F1b 车辆二年→续封 24 个月", p2[0]?.label === "车辆" && p2[0]?.action === "续封"
    && p2[0]?.expiresAt === "2028-10-27", JSON.stringify(p2[0]));
  const p3 = extractPreservationClauses("冻结被执行人持有的股权三年。", "2026-10-27");
  check("F1c 股权三年（中文数字）→续冻 36 个月", p3[0]?.label === "股权" && p3[0]?.expiresAt === "2029-10-27",
    JSON.stringify(p3[0]));
  const p4 = extractPreservationClauses("查封不动产三年。", "2026-10-27");
  check("F1d 不动产三年→续封 36 个月", p4[0]?.label === "不动产" && p4[0]?.expiresAt === "2029-10-27",
    JSON.stringify(p4[0]));
  const p5 = extractPreservationClauses("冻结银行存款，自2026年1月5日至2026年7月5日止。", "2026-10-27");
  check("F1e 日期窗（自X至Y）→至日为到期", p5[0]?.startDate === "2026-01-05" && p5[0]?.expiresAt === "2026-07-05",
    JSON.stringify(p5[0]));
  const p6 = extractPreservationClauses("双方握手言和，气氛融洽。", "2026-10-27");
  check("F1f 负样本（无冻结/查封/扣押词）不产出", p6.length === 0, `n=${p6.length}`);
  const p7 = extractPreservationClauses("扣押涉案仓储设备。", "2026-10-27");
  check("F1g 其他目标→原文 label+不猜到期（UNKNOWN）", p7.length === 1 && p7[0].label === "原文"
    && p7[0].expiresAt === null && p7[0].action === "续封", JSON.stringify(p7[0]));
  const p8 = extractPreservationClauses("冻结账户至2026年2月30日。", "2026-10-27");
  check("F1h 假日历日（2 月 30 日）→null 不猜", p8.length === 1 && p8[0].expiresAt === null, JSON.stringify(p8[0]));
  check("F1i 工具面：cnNumber 二=2 十五=15 / durationMonths 一年半=18",
    cnNumber("二") === 2 && cnNumber("十五") === 15 && durationMonths("一年半") === 18,
    `${cnNumber("二")}/${cnNumber("十五")}/${durationMonths("一年半")}`);
  check("F1j cnDateString 真日历日校验", cnDateString("2026", "2", "30") === null && cnDateString("二零二六", "一", "五") === "2026-01-05",
    `${cnDateString("2026", "2", "30")}/${cnDateString("二零二六", "一", "五")}`);

  // F2 解封压制（CB-B11：解封≥保全开始→压制；否则保留；无开始日保留）
  const sup = suppressedByUnseal(
    [{ id: "pv1", startDate: "2026-11-01" }, { id: "pv2", startDate: "2026-12-01" }, { id: "pv3", startDate: null }],
    [{ id: "u1", date: "2026-11-01" }],
  );
  check("F2 解封=开始日→压制 pv1；解封<开始→留 pv2；无开始日→留 pv3",
    sup.has("pv1") && !sup.has("pv2") && !sup.has("pv3"), JSON.stringify([...sup]));

  // F3 session 四键去重+最新文档权威（CB-B10）
  const deduped = dedupHearingsBySession([
    { id: "h1", title: "第一次开庭", docRank: 1 },
    { id: "h2", title: "第一次开庭（补充）", docRank: 3 },
    { id: "h3", title: "第二次开庭", docRank: 2 },
    { id: "h4", title: "庭前询问", docRank: 1 },
    { id: "h5", title: "证据交换笔录", docRank: 9 },
  ]);
  check("F3 同键留最新文档（h2 压 h1）+异键并存+未命中透传",
    deduped.length === 4 && deduped.some((x) => x.id === "h2") && !deduped.some((x) => x.id === "h1")
      && deduped.some((x) => x.id === "h3") && deduped.some((x) => x.id === "h4") && deduped.some((x) => x.id === "h5"),
    JSON.stringify(deduped.map((x) => x.id)));
  check("F3b 键表：听证=pretrial 第二次=second 第一次=first",
    hearingSessionKeyOf("庭前听证") === "pretrial" && hearingSessionKeyOf("第二次开庭") === "second"
      && hearingSessionKeyOf("开庭传票") === "first" && hearingSessionKeyOf("缴费通知") === null,
    "keys");

  // F4 重要位窗口（CB-B9）：hearing≤365 未过期；保全≤60；非保全期限不进；todo/manual 逾期进
  const imp = buildImportantReminders([
    { id: "a", kind: "hearing", title: "开庭窗内", date: "2027-10-26" },
    { id: "b", kind: "hearing", title: "开庭窗外", date: "2027-11-01" },
    { id: "c", kind: "hearing", title: "开庭已过", date: "2026-10-20" },
    { id: "d", kind: "deadline", title: "保全续封", date: "2026-12-20", isPreservation: true },
    { id: "e", kind: "deadline", title: "保全过期", date: "2026-10-25", isPreservation: true },
    { id: "f", kind: "deadline", title: "非保全期限", date: "2026-11-15" },
    { id: "g", kind: "todo", title: "逾期待办", date: "2026-10-25" },
    { id: "h", kind: "manual", title: "独立日程", date: "2027-09-01" },
  ], "2026-10-27");
  const impIds = imp.map((x) => x.id);
  check("F4 窗口口径（开庭窗内留/窗外丢/已过丢；保全窗内留/过期丢；非保全期限不进；todo/manual 进；normal 段天数升序 h309<a364）",
    JSON.stringify(impIds) === JSON.stringify(["g", "d", "h", "a"]), JSON.stringify(impIds));

  // F5 排序链+urgency+色调
  const imp2 = buildImportantReminders([
    { id: "x1", kind: "manual", title: "逾期独立", date: "2026-10-25" },
    { id: "x2", kind: "hearing", title: "紧急开庭", date: "2026-11-01" },
    { id: "x3", kind: "todo", title: "普通待办", date: "2027-08-01" },
    { id: "x4", kind: "todo", title: "紧急待办", date: "2026-12-01" },
  ], "2026-10-27");
  check("F5 排序：逾期→紧急(天数升序)→普通；hearing 5 天=urgent 红调",
    JSON.stringify(imp2.map((x) => x.id)) === JSON.stringify(["x1", "x2", "x4", "x3"])
      && imp2[1]?.urgency === "urgent" && imp2[1]?.tone === "red"
      && imp2[2]?.tone === "amber" && imp2[3]?.tone === "gray",
    JSON.stringify(imp2.map((x) => [x.id, x.urgency, x.tone])));
  check("F5b 倒计时三态（今天/N 天/逾期 N 天）",
    importantCountdown(0) === "今天" && importantCountdown(3) === "3 天" && importantCountdown(-2) === "逾期 2 天",
    `${importantCountdown(0)}/${importantCountdown(3)}/${importantCountdown(-2)}`);

  // F6 截 12 条
  const many: Array<{ id: string; kind: "todo"; title: string; date: string }> = [];
  for (let i = 0; i < 14; i++) many.push({ id: `m${i}`, kind: "todo", title: `待办${i}`, date: "2026-10-25" });
  check("F6 重要位截 12 条", buildImportantReminders(many, "2026-10-27").length === 12,
    `n=${buildImportantReminders(many, "2026-10-27").length}`);

  // F7 简报五级（红→橙提醒→材料→更新→平静）
  const bi = buildImportantReminders([{ id: "q1", kind: "todo", title: "逾期", date: "2026-10-25" }], "2026-10-27");
  const lv1 = briefingLevel({ important: bi });
  const lv2 = briefingLevel({ important: buildImportantReminders([{ id: "q2", kind: "hearing", title: "紧急", date: "2026-11-01" }], "2026-10-27") });
  const lv3 = briefingLevel({ important: [], materialFailures: 2 });
  const lv4 = briefingLevel({ important: [], cases: [{ id: "c1", updatedAt: new Date(Date.now() - 3600_000).toISOString() }] });
  const lv5 = briefingLevel({ important: [], cases: [{ id: "c1", updatedAt: new Date(Date.now() - 7 * 24 * 3600_000).toISOString() }] });
  check("F7 简报五级（红逾期/橙紧急/橙材料/平更新/平静）",
    lv1.level === "red" && lv1.anchor === "important"
      && lv2.level === "amber" && lv2.anchor === "calendar"
      && lv3.level === "amber" && lv3.anchor === "cases"
      && lv4.level === "normal" && lv4.anchor === "cases"
      && lv5.level === "normal" && lv5.anchor === "calendar",
    `${lv1.level}/${lv2.level}/${lv3.level}/${lv4.level}/${lv5.level}`);

  // F8 月历色点阈值（CB-B12）
  check("F8 色点（≤7 红/≤30 琥珀/31+ kind 蓝紫绿灰）",
    boardCellDotColor(3, "hearing") === "red" && boardCellDotColor(20, "hearing") === "amber"
      && boardCellDotColor(40, "hearing") === "blue" && boardCellDotColor(40, "todo") === "purple"
      && boardCellDotColor(40, "schedule") === "green" && boardCellDotColor(40, "deadline") === "gray"
      && boardCellDotColor(null, "schedule") === "green",
    "dots");

  // F9 删除确认文案两分支（对拍行 32）
  check("F9 删除文案区分（AI 派生=仅隐藏 vs 手工=不可恢复）",
    boardDeleteConfirmCopy(true, "开庭").includes("仅隐藏") && !boardDeleteConfirmCopy(true, "开庭").includes("不可恢复")
      && boardDeleteConfirmCopy(false, "开庭").includes("不可恢复"),
    boardDeleteConfirmCopy(false, "开庭"));

  // ══ E18 段（补齐件3：案件列表面纯函数——对拍行 45/46/49/52/61-64/65/67/70/71）══
  // E18a 刑事启发式（对拍行 61；CB-B4 同构：宁漏勿误+排除词压倒词表）
  check("E18a 刑事启发式（刑案号/案由含罪/词表命中→刑事；排除词不误吞；默认非刑事；案号「刑」压倒排除词）",
    isCriminalCase({ name: "借款纠纷", cause: "民间借贷", caseNo: "(2026)合0203刑初15号" }) === true
      && isCriminalCase({ name: "张三盗窃案", cause: "盗窃罪", caseNo: "" }) === true
      && isCriminalCase({ name: "指控被告人张三犯罪一案", cause: "", caseNo: "(2026)合0203民初15号" }) === true
      && isCriminalCase({ name: "公安局侦查行为赔偿案", cause: "行政赔偿", caseNo: "(2026)合0203行初15号" }) === false
      && isCriminalCase({ name: "张三与某检察院国家赔偿案", cause: "", caseNo: "" }) === false
      && isCriminalCase({ name: "借款合同纠纷", cause: "民间借贷", caseNo: "(2026)合0203民初15号" }) === false
      && isCriminalCase({ name: "公安局侦查行为赔偿案", cause: "", caseNo: "(2026)合0203刑初1号" }) === true,
    "heuristic");

  // E18b 域 tabs（行62/63/65：诉讼=全部/刑事=启发式/执行=状态过滤）
  const domCases = [
    { id: "d1", name: "借款纠纷", criminal: false, status: "审理中" },
    { id: "d2", name: "盗窃案", criminal: true, status: "接案" },
    { id: "d3", name: "执行纠纷", criminal: false, status: "执行中" },
  ];
  const law = (c: (typeof domCases)[number]) => c.criminal;
  const st = (c: (typeof domCases)[number]) => c.status;
  check("E18b 域过滤（诉讼全显/刑事只刑事/执行只执行中）",
    filterCasesByDomain(domCases, "civil", law, st).length === 3
      && JSON.stringify(filterCasesByDomain(domCases, "criminal", law, st).map((c) => c.id)) === JSON.stringify(["d2"])
      && JSON.stringify(filterCasesByDomain(domCases, "execution", law, st).map((c) => c.id)) === JSON.stringify(["d3"]),
    "tabs");

  // E18c 案件集口径（行64：日历集排已结案；提醒集排已结案+已调解）
  check("E18c 案件集 gate（结案双排/调解只排提醒面/在办全过）",
    boardCaseGate("已结案", "calendar") === false && boardCaseGate("已结案", "reminder") === false
      && boardCaseGate("已调解", "calendar") === true && boardCaseGate("已调解", "reminder") === false
      && boardCaseGate("审理中", "reminder") === true && boardCaseGate(null, "calendar") === true,
    "gate");

  // E18d 四排序键（行46：null 沉底两方向一致+同值 updated 兜底）
  const sortCases = [
    { id: "s1", updatedAt: "2026-10-01T00:00:00Z" }, // 金额 null
    { id: "s2", updatedAt: "2026-10-02T00:00:00Z" }, // 金额 0
    { id: "s3", updatedAt: "2026-10-03T00:00:00Z" }, // 金额 9900
    { id: "s4", updatedAt: "2026-10-04T00:00:00Z" }, // 金额 9900（同值→updated 倒序兜底）
  ];
  const centsOf = (c: (typeof sortCases)[number]): number | null => (c.id === "s1" ? null : c.id === "s2" ? 0 : 9900);
  check("E18d 四排序键（金额升/降 null 恒沉底；同值 updated 倒序兜底；状态=档位权重）",
    JSON.stringify(boardSortCasesByKey(sortCases, "status", "asc", () => null).map((c) => c.id)) === JSON.stringify(["s4", "s3", "s2", "s1"])
      && JSON.stringify(boardSortCasesByKey(sortCases, "amount", "asc", centsOf).map((c) => c.id)) === JSON.stringify(["s2", "s4", "s3", "s1"])
      && JSON.stringify(boardSortCasesByKey(sortCases, "amount", "desc", centsOf).map((c) => c.id)) === JSON.stringify(["s4", "s3", "s2", "s1"])
      && boardStatusWeight("接案") === 0 && boardStatusWeight("执行中") === 9 && boardStatusWeight("无关值") === null,
    JSON.stringify(boardSortCasesByKey(sortCases, "amount", "desc", centsOf).map((c) => c.id)));

  // E18e 排序键数据源（立案时间=正式立案>建案/接案；最近开庭=未来最早，过往忽略）
  const keyRows = [
    { caseId: "k1", type: "建案", date: "2026-01-05", hearing: false },
    { caseId: "k1", type: "正式立案", date: "2026-02-01", hearing: false },
    { caseId: "k2", type: "建案", date: "2026-03-01", hearing: false },
    { caseId: "k1", type: "开庭", date: "2026-10-01", hearing: true },
    { caseId: "k1", type: "开庭", date: "2026-11-11", hearing: true },
    { caseId: "k2", type: "开庭", date: "2026-01-01", hearing: true },
  ];
  check("E18e 排序键数据源（正式立案压建案/无立案行=null/未来最近开庭/纯过往=null）",
    boardFilingDateOf(keyRows, "k1") === "2026-02-01" && boardFilingDateOf(keyRows, "k2") === "2026-03-01"
      && boardFilingDateOf(keyRows, "kX") === null
      && boardNextHearingDateOf(keyRows, "k1", "2026-10-27") === "2026-11-11"
      && boardNextHearingDateOf(keyRows, "k2", "2026-10-27") === null,
    "keyrows");

  // E18f 拖拽序（行45：展示序已结案尾分区+无序新案 updated 倒序追加尾；拖放增量只含变更行）
  const dragCases = [
    { id: "g1", updatedAt: "2026-10-03T00:00:00Z" }, // 无序 新案（updated 最新）
    { id: "g2", updatedAt: "2026-10-01T00:00:00Z", sortOrder: 1 }, // 有序
    { id: "g3", updatedAt: "2026-10-04T00:00:00Z" }, // 无序
    { id: "g4", updatedAt: "2026-10-05T00:00:00Z", sortOrder: 0, closed: true }, // 已结案
  ];
  const seq = boardDragOrderSeq(dragCases, (c) => c.closed === true, (c) => (typeof (c as { sortOrder?: number }).sortOrder === "number" ? (c as { sortOrder: number }).sortOrder : null));
  check("E18f 拖拽展示序（有序在前/无序 updated 倒序追加尾/已结案强制尾分区）",
    JSON.stringify(seq.map((c) => c.id)) === JSON.stringify(["g2", "g3", "g1", "g4"]),
    JSON.stringify(seq.map((c) => c.id)));
  const dragPatch = boardApplyDragOrder([{ id: "A" }, { id: "B" }, { id: "C" }], "C", "A");
  check("E18f2 拖放落位（C 前插到 A→全序重编号 0..n-1，后续行随移；同位拖放=空增量）",
    JSON.stringify(dragPatch) === JSON.stringify([{ id: "C", sortOrder: 0 }, { id: "A", sortOrder: 1 }, { id: "B", sortOrder: 2 }])
      && boardApplyDragOrder([{ id: "A" }, { id: "B" }], "A", "A").length === 0,
    JSON.stringify(dragPatch));

  // E18g 近期日程分组（行70：30 天窗/按日分组升序/tone ≤3 红 ≤7 琥珀/前 3 天+余数/开庭标题补全）
  const rg = boardRecentGroups([
    { date: "2026-10-28", kind: "hearing", title: "证据交换", ref: "r1" },
    { date: "2026-10-29", kind: "deadline", title: "举证期限", ref: "r2" },
    { date: "2026-11-01", kind: "schedule", title: "当事人约谈", ref: "r3" },
    { date: "2026-11-16", kind: "manual", title: "窗内末天", ref: "r4" },
    { date: "2026-12-06", kind: "hearing", title: "窗外", ref: "r5" },
    { date: "2026-10-26", kind: "hearing", title: "昨日已过", ref: "r6" },
  ], "2026-10-27");
  check("E18g 近期日程分组（窗 30 天/升序前 3 天+extraDays/过去不进/tone 三档/hearing 补「开庭 · 」前缀）",
    rg.groups.length === 3 && rg.extraDays === 1
      && rg.groups[0]?.date === "2026-10-28" && rg.groups[0]?.tone === "urgent" && rg.groups[0]?.countdown === "1 天后"
      && rg.groups[1]?.tone === "urgent" && rg.groups[2]?.tone === "soon"
      && rg.groups[0]?.items[0]?.title === "开庭 · 证据交换",
    JSON.stringify({ n: rg.groups.length, extra: rg.extraDays, t0: rg.groups[0]?.items[0]?.title }));
  check("E18g2 开庭标题补全边界（开庭/庭审/询问 开头不重复补；非 hearing 不动）",
    boardHearingDisplayTitle("hearing", "庭审准备") === "庭审准备"
      && boardHearingDisplayTitle("hearing", "询问笔录核对") === "询问笔录核对"
      && boardHearingDisplayTitle("hearing", "第二次质证") === "开庭 · 第二次质证"
      && boardHearingDisplayTitle("schedule", "约谈") === "约谈",
    "prefix");

  // E18h 今日焦点（行71：逾期即焦点（最近一条）/≤3 红/未来 30 天无→null/案件名案号富化）
  const f1 = boardFocusItem({
    deadlines: [{ id: "fd1", title: "上诉期限", date: "2026-10-25", caseId: "fc1" }],
    events: [{ id: "fe1", title: "质证", date: "2026-11-05", kind: "hearing" }],
    todayStr: "2026-10-27",
    caseInfoOf: () => ({ name: "合成案", caseNo: "(2026)合0203民初1号" }),
  });
  const f2 = boardFocusItem({
    deadlines: [{ id: "fd2", title: "远期", date: "2026-12-31" }],
    events: [{ id: "fe2", title: "远期庭", date: "2027-01-05", kind: "hearing" }],
    todayStr: "2026-10-27",
  });
  check("E18h 今日焦点（逾期最近一条优先+红色+逾期 N 天+案件富化；全 30 天外=null 空态）",
    f1 !== null && f1.title === "上诉期限" && f1.daysLeft === -2 && f1.tone === "red"
      && f1.countdown === "逾期 2 天" && f1.caseName === "合成案" && f1.caseNo === "(2026)合0203民初1号"
      && f2 === null,
    JSON.stringify(f1));

  // E18i 金额格式化（§3.6 整型分，整数运算禁浮点）
  check("E18i 金额（整分→元两位小数；null/非法→占位 -）",
    boardYuan(123456) === "¥1234.56" && boardYuan(0) === "¥0.00" && boardYuan(5) === "¥0.05"
      && boardYuan(null) === "-" && boardYuan(1.5 as unknown as number) === "-",
    `${boardYuan(123456)}/${boardYuan(0)}/${boardYuan(null)}`);

  // ══ E20 段（r9 二次补齐件4：对拍行 24/66 纯函数针——行24 开庭 session 去重并显示路径/
  // 行66 最近期限风险徽章）══
  // E20a 行24：同案同 session 键开庭族行坍缩保留 updatedAt 最新（最新文档权威）；
  //   二审开庭自成一族不与一审互吞；非 hearing/未绑案/键外行不去重。
  const dedupRows = [
    { id: "h1", caseId: "k1", kind: "hearing", title: "开庭", updatedAt: "2026-10-01T00:00:00Z" },
    { id: "h2", caseId: "k1", kind: "hearing", title: "开庭", updatedAt: "2026-10-05T00:00:00Z" },
    { id: "h3", caseId: "k1", kind: "hearing", title: "二审开庭", updatedAt: "2026-10-02T00:00:00Z" },
    { id: "h4", caseId: "k1", kind: "hearing", title: "二审开庭", updatedAt: "2026-10-09T00:00:00Z" },
    { id: "h5", caseId: "k2", kind: "hearing", title: "开庭排期", updatedAt: "2026-10-03T00:00:00Z" },
    { id: "h6", caseId: "k1", kind: "schedule", title: "调解", updatedAt: "2026-10-04T00:00:00Z" },
    { id: "h7", caseId: null, kind: "hearing", title: "开庭", updatedAt: "2026-10-06T00:00:00Z" },
  ];
  const dedupKept = boardDedupTimelineHearings(dedupRows).map((r) => r.id);
  check("E20a 行24 时间线开庭去重（同键保最新文档/二审开庭自成一族/非 hearing 与未绑案不去重）",
    JSON.stringify(dedupKept) === JSON.stringify(["h2", "h4", "h5", "h6", "h7"]),
    JSON.stringify(dedupKept));
  check("E20b 行24 时间戳同值 tie→id 序小（确定性；单独键行原样保留）",
    JSON.stringify(boardDedupTimelineHearings([
      { id: "t2", caseId: "k9", kind: "hearing", title: "开庭", updatedAt: "2026-10-01T00:00:00Z" },
      { id: "t1", caseId: "k9", kind: "hearing", title: "开庭", updatedAt: "2026-10-01T00:00:00Z" },
      { id: "t3", caseId: "k9", kind: "hearing", title: "第三次开庭", updatedAt: "2026-10-01T00:00:00Z" },
    ]).map((r) => r.id)) === JSON.stringify(["t1", "t3"]),
    "tie");

  // E20c 行66：最近期限风险徽章（该案最近一条已逾期=最贴近今天；未来项不冒红；他案隔离）
  const riskRows = [
    { caseId: "k1", title: "续封申请截止", dueDate: "2026-10-17" }, // 逾期 10 天
    { caseId: "k1", title: "上诉期限", dueDate: "2026-10-26" }, // 逾期 1 天（最近→中选）
    { caseId: "k1", title: "举证期限", dueDate: "2026-11-30" }, // 未来不冒红
    { caseId: "k2", title: "未来项", dueDate: "2026-11-01" },
  ];
  const riskK1 = boardDeadlineRiskOf(riskRows, "k1", "2026-10-27");
  check("E20c 行66 期限风险徽章（只收已逾期/取最近一条/他案隔离/无逾期=null）",
    riskK1 !== null && riskK1.title === "上诉期限" && riskK1.daysLeft === -1 && riskK1.date === "2026-10-26"
      && boardDeadlineRiskOf(riskRows, "k2", "2026-10-27") === null
      && boardDeadlineRiskOf(riskRows, "kX", "2026-10-27") === null,
    JSON.stringify(riskK1));
  check("E20d 行66 非法日期不猜（坏日期行跳过；空集=null）",
    boardDeadlineRiskOf([
      { caseId: "k1", title: "坏日期", dueDate: "2026-02-30" },
      { caseId: "k1", title: "怪格式", dueDate: "2026/10/01" },
    ], "k1", "2026-10-27") === null
      && boardDeadlineRiskOf([], "k1", "2026-10-27") === null,
    "baddate");
} catch (e) {
  check("纯函数段", false, e?.message ?? String(e));
}

const pass = results.every((r) => r.ok);
console.log(pass ? "BOARD_SYNTH_PASS" : "BOARD_SYNTH_FAIL");
process.exit(pass ? 0 : 1);
