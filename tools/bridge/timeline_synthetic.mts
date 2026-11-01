// 【步骤4·#4 案件时间线】件1 合成用例（全部合成材料）——CaseEvent 数据模型+读取契约+auto 通道：
//   P 段走自管隔离桥实例（:3066 独立库）：
//     P0 迁移 0010 在库（表+索引+账本）；P1 建案挂点（建案事件同事务）；P2 唯一写入口 round-trip
//     （origin=auto/provenance=system/date 缺省=今日）；P3 日程挂点（开庭排期/期限登记同事务；
//     独立日程与无关联案件不产事件）；P4 待办挂点（任务登记，date=due）；P5 feed 口径（date DESC
//     LIMIT 50）；P6 full 口径（C3 确定性排序：同日次序表/99 垫底/无日期沉底）；P7 viewer 客户侧
//     白名单过滤（查询层执行）；P8 负测（未知案件/空类型/白名单外/坏日期）；P9 案件删级联清事件；
//     P10 杀桥重启字段全等+迁移账本不重放；P11 清场归零。
//   E 段纯函数（直 import 模型）：C3 排序全路径（12 值次序表/解封·还款期·白名单外=99 同段垫底/
//     无日期沉底/同段 createdAt+eventId 稳定）；D6 行键缺值空串；C4 去重保留首现；C7 开庭三态；
//     B18 日期精度三级兜底；值域计数（CB 14/auto 21/FACT 11/次序表 12）。
// 末行 TIMELINE_SYNTH_PASS / TIMELINE_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import {
  AUTO_EVENT_TYPES, CB_EVENT_TYPES, FACT_EVENT_TYPES, BUSINESS_ORDER,
  applyCaseEventEdit, assembleExtractionPrompt, dedupByKeyKeepFirst, displayDateOf, docHintOf, eventOrderOf,
  hearingStatusText, parseExtractionOutput, planCaseEventMerge, postprocessExtracted,
  restoreCaseEventField, rowKeyOf, sortCaseEventsFull,
  buildCaseTimelineReportLines, CASE_REPORT_DATE_FALLBACK, CASE_REPORT_EMPTY_TEXT, CASE_REPORT_EVENT_FALLBACK,
  type CaseEventProto, type ExtractedRow,
} from "../../packages/juscite-legal/src/kernel/caseTimelineModel.ts";
import { BOARD_DEFAULT_LEAD_MINUTES, boardTimelineReminderInputs } from "../../packages/juscite-legal/src/panels/boardReminder.ts";
import { TIMELINE_SKILL_MD, TIMELINE_SKILL_META } from "./timeline_skill.mjs";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3066);
const NODE = process.execPath;
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok });
  console.log(`[tl-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function dbPath() { return join(process.env.APPDATA ?? "", "Juscite", "bridge", `bridge-${PORT}.db`); }
function openDb() { return new DatabaseSync(dbPath()); }

let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, ".local", `timeline-synth-bridge-${PORT}.log`), "a");
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
async function clearStaleBridge() {
  for (const pid of findListenerPids(PORT)) {
    const line = await commandLineOf(pid);
    if (!line.includes("bridge_host.mjs")) {
      throw new Error(`:${PORT} 被非桥进程占用（pid=${pid}），不接触`);
    }
    console.log(`[tl-synth] 清残留桥 pid=${pid}`);
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
const today = (() => { const n = new Date(); return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`; })();

try {
  await clearStaleBridge();
  for (const suffix of ["", "-wal", "-shm"]) {
    try { unlinkSync(dbPath() + suffix); } catch { /* 不存在即可 */ }
  }
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error(`隔离桥 :${PORT} 40s 不可探`);
  await connect();

  // ── P0 迁移在库 ──
  {
    const db = openDb();
    const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map((r) => r.name);
    const indexes = db.prepare("SELECT name FROM sqlite_master WHERE type='index'").all().map((r) => r.name);
    const migs = db.prepare("SELECT id FROM schema_migration WHERE id='0010_case_event'").all();
    const cols = db.prepare("PRAGMA table_info(case_events)").all().map((r) => r.name);
    db.close();
    check("P0 迁移 0010 在库（表+账本+索引+列全集）",
      tables.includes("case_events") && migs.length === 1
        && indexes.includes("idx_case_events_matter_date")
        && ["event_id", "matter_id", "event_type", "date", "date_label", "note", "expires_at", "status",
          "importance", "phase", "side", "origin", "source_refs_json", "payload_json", "provenance",
          "locked_fields_json", "orig_json", "deleted", "created_at", "updated_at"].every((c) => cols.includes(c)),
      `cols=${cols.length}`);
  }

  // ── P1 建案挂点（同事务）──
  const c1 = await call("matterCreate", { name: "合成案·时间线甲" });
  const p1full = await call("caseEventList", { matterId: c1.id, mode: "full" });
  const p1ev = p1full.events[0];
  check("P1 建案动作自动写时间线事件（建案/origin=auto/provenance=system/date=今日）",
    p1full.events.length === 1 && p1ev.eventType === "建案" && p1ev.origin === "auto"
      && p1ev.provenance === "system" && p1ev.status === "confirmed" && p1ev.date === today
      && p1ev.note === "新建案件「合成案·时间线甲」" && p1ev.matterId === c1.id && !p1ev.deleted,
    JSON.stringify(p1ev));
  check("P1b full 口径 C3 升序返回（单行）+viewer/mode 回显", p1full.viewer === "internal" && p1full.mode === "full", p1full.viewer);

  // ── P2 唯一写入口 round-trip ──
  const e1 = await call("caseEventRecord", { matterId: c1.id, eventType: "开庭", note: "第一次开庭·合成区法院第3法庭", date: "2026-11-02" });
  check("P2 唯一写入口 round-trip（CB 白名单值+显式日期）",
    e1.eventType === "开庭" && e1.date === "2026-11-02" && e1.note === "第一次开庭·合成区法院第3法庭"
      && e1.origin === "auto" && e1.provenance === "system" && e1.eventId.startsWith("ce_"),
    JSON.stringify(e1));
  const e2 = await call("caseEventRecord", { matterId: c1.id, eventType: "材料登记", note: "上传起诉状（合成）" });
  check("P2b date 缺省=动作发生当日（LL F3 等量）", e2.date === today && e2.eventType === "材料登记", e2.date);
  const e3 = await call("caseEventRecord", { matterId: c1.id, eventType: "还款期", date: "2026-12-01", note: "第一期付款日（计划）" });
  // P2c 富字段（对拍 47 补齐：保全登记等经唯一写入口自带 expires_at/payload/refs/六档 status 能力；
  // 对拍增补 63：payload.confidence 随桥 round-trip，字符串数字收为数值）
  const e5 = await call("caseEventRecord", {
    matterId: c1.id, eventType: "保全", date: "2026-10-27", expiresAt: "2027-10-27",
    status: "disputed", importance: "critical", phase: "争议解决", side: "我方",
    note: "冻结银行账户（标的资金，期限一年）",
    payload: { subjects: ["合成甲公司"], amount_text: "18 万元", dispute_note: "被告主张已部分还款", confidence: "0.85" },
    sourceRefs: [{ filename: "保全裁定书（合成）.txt", locator: "第2页", quote: "冻结被申请人银行存款一年。" }],
  });
  check("P2c 富字段 round-trip（保全登记：expires_at/六档 status/关键档/阶段/立场/payload/来源四元组/置信度 0.85）",
    e5.eventType === "保全" && e5.expiresAt === "2027-10-27" && e5.status === "disputed" && e5.importance === "critical"
      && e5.phase === "争议解决" && e5.side === "我方" && e5.payload?.amount_text === "18 万元"
      && e5.payload?.confidence === 0.85
      && e5.sourceRefs[0]?.filename === "保全裁定书（合成）.txt" && e5.sourceRefs[0]?.locator === "第2页",
    JSON.stringify(e5));
  const e5b = await callExpectError("caseEventRecord", { matterId: c1.id, eventType: "保全", expiresAt: "明年十月" });
  check("P2c 坏到期日拒绝", e5b.threw && e5b.message.includes("到期日"), e5b.message.slice(0, 40));
  // P2d 对拍增补 63：confidence 非数值丢弃不造值（其余 payload 键照常保留；独立案即建即删不动后续计数）
  const c0 = await call("matterCreate", { name: "合成案·置信度负检" });
  const e6 = await call("caseEventRecord", { matterId: c0.id, eventType: "接案", date: "2026-11-01", payload: { confidence: "高", subjects: ["合成乙"] } });
  check("P2d confidence 非数值丢弃（payload 保留 subjects）",
    e6.payload != null && !("confidence" in e6.payload) && JSON.stringify(e6.payload.subjects) === '["合成乙"]', JSON.stringify(e6.payload));
  await call("matterDelete", { id: c0.id });

  // ── P3 日程挂点 ──
  await call("matterEventAdd", { date: "2026-11-02", title: "合成开庭日程", kind: "hearing", location: "合成区法院第3法庭", caseId: c1.id });
  await call("matterEventAdd", { date: "2026-11-20", title: "举证期限", kind: "deadline", caseId: c1.id });
  await call("matterEventAdd", { date: "2026-11-21", title: "独立日程（不绑案）", kind: "hearing" });
  await call("matterEventAdd", { date: "2026-11-22", title: "普通日程（绑案）", kind: "schedule", caseId: c1.id });
  {
    const full = await call("caseEventList", { matterId: c1.id, mode: "full" });
    const types = full.events.map((e: CaseEventProto) => e.eventType);
    check("P3 日程挂点：开庭/期限写事件；普通日程与无关联案件不写",
      types.filter((t) => t === "开庭排期").length === 1 && types.filter((t) => t === "期限登记").length === 1
        && full.events.length === 3 + 4 // 建案+开庭+材料登记+还款期+保全(P2c) + 开庭排期+期限登记
      , JSON.stringify(types));
    const hearing = full.events.find((e: CaseEventProto) => e.eventType === "开庭排期");
    check("P3b 开庭排期事件标题语义（服务端短句+地点+日程日期）",
      hearing?.note === "排期开庭：合成开庭日程（合成区法院第3法庭）" && hearing?.date === "2026-11-02",
      hearing?.note ?? "none");
  }

  // ── P4 待办挂点 ──
  await call("matterTodoAdd", { caseId: c1.id, title: "合成待办·质证准备", dueDate: "2026-11-15" });
  {
    const full = await call("caseEventList", { matterId: c1.id, mode: "full" });
    const task = full.events.find((e: CaseEventProto) => e.eventType === "任务登记");
    check("P4 待办挂点（任务登记/date=dueDate）",
      !!task && task.note === "新增任务：合成待办·质证准备" && task.date === "2026-11-15", JSON.stringify(task));
    const all = await call("caseEventAllList", {});
    check("P4b caseEventAllList 跨案只读源（含 e1；看板下一节点/阶梯/日历翻牌用）",
      all.events.some((e: CaseEventProto) => e.eventId === e1.eventId), `rows=${all.events.length}`);
  }

  // ── P5 feed 口径（date DESC LIMIT 50）──
  for (let i = 0; i < 55; i++) {
    await call("caseEventRecord", { matterId: c1.id, eventType: "材料登记", note: `合成材料事件 ${i}`, date: i % 2 ? "2026-10-01" : "2026-09-01" });
  }
  {
    const feed = await call("caseEventList", { matterId: c1.id, mode: "feed" });
    check("P5 feed LIMIT 50", feed.events.length === 50, `rows=${feed.events.length}`);
    const dates = feed.events.map((e: CaseEventProto) => e.date ?? "");
    const sortedDesc = [...dates].every((d, i) => i === 0 || dates[i - 1] >= d);
    check("P5b feed 倒序（date DESC）+首条为最新日期", sortedDesc && dates[0] >= dates[dates.length - 1], `${dates[0]}..${dates[dates.length - 1]}`);
    check("P5c feed mode 回显", feed.mode === "feed", feed.mode);
  }

  // ── P6 full 口径 C3 排序（同日次序表/99 垫底/无日期沉底）──
  const c2 = await call("matterCreate", { name: "合成案·时间线乙" });
  await call("caseEventRecord", { matterId: c2.id, eventType: "开庭", date: "2026-11-02", note: "同日开庭" });
  await call("caseEventRecord", { matterId: c2.id, eventType: "接案", date: "2026-11-02", note: "同日接案" });
  await call("caseEventRecord", { matterId: c2.id, eventType: "还款期", date: "2026-11-02", note: "同日还款期（99 段）" });
  await call("caseEventRecord", { matterId: c2.id, eventType: "申请立案", date: "2026-11-02", note: "同日申请立案" });
  await call("caseEventRecord", { matterId: c2.id, eventType: "实收登记", note: "无日期事件（沉底）" });
  {
    const full = await call("caseEventList", { matterId: c2.id, mode: "full" });
    const order = full.events.map((e: CaseEventProto) => e.eventType).join(",");
    // 建案/实收登记 date 缺省=动作当日（LL F3 等量）→ 同日 99 段按 createdAt 先于 11-02 组；
    // 「无日期沉底」路径仅抽取通道可产（date 缺失），断言见纯函数段 E1。
    check("P6 full C3：日期升序分组 → 同日按次序表（接案→申请立案→开庭）→99 垫底（还款期）",
      order === "建案,实收登记,接案,申请立案,开庭,还款期", order);
  }

  // ── P7 viewer 客户侧白名单（查询层过滤）──
  {
    const cust = await call("caseEventList", { matterId: c1.id, viewer: "customer", mode: "full" });
    const bad = cust.events.filter((e: CaseEventProto) => !(FACT_EVENT_TYPES as readonly string[]).includes(e.eventType));
    check("P7 customer full 只见 FACT 白名单（材料/任务登记等被查询层滤除）",
      cust.events.length > 0 && bad.length === 0, `rows=${cust.events.length} bad=${bad.length}`);
    const custFeed = await call("caseEventList", { matterId: c1.id, viewer: "customer", mode: "feed" });
    const badFeed = custFeed.events.filter((e: CaseEventProto) => !(FACT_EVENT_TYPES as readonly string[]).includes(e.eventType));
    check("P7b customer feed 同规（SQL IN 过滤）", badFeed.length === 0 && custFeed.events.length > 0, `rows=${custFeed.events.length}`);
    const unk = await call("caseEventList", { matterId: c1.id, viewer: " mystery ", mode: "full" });
    const badUnk = unk.events.filter((e: CaseEventProto) => !(FACT_EVENT_TYPES as readonly string[]).includes(e.eventType));
    check("P7c 未知 viewer 一律按最严（fail-closed）", badUnk.length === 0, `viewer=${unk.viewer}`);
  }

  // ── P8 负测 ──
  const n1 = await callExpectError("caseEventRecord", { matterId: "mat_nope", eventType: "开庭" });
  check("P8 未知案件拒绝", n1.threw && n1.message.includes("案件不存在"), n1.message.slice(0, 40));
  const n2 = await callExpectError("caseEventRecord", { matterId: c1.id, eventType: "  " });
  check("P8b 空事件类型拒绝", n2.threw && n2.message.includes("不能为空"), n2.message.slice(0, 40));
  const n3 = await callExpectError("caseEventRecord", { matterId: c1.id, eventType: "团建聚餐" });
  check("P8c 值域外拒绝（自由文本不走唯一写入口）", n3.threw && n3.message.includes("值域"), n3.message.slice(0, 40));
  const n4 = await callExpectError("caseEventRecord", { matterId: c1.id, eventType: "开庭", date: "2026-02-30" });
  check("P8d 假日历日拒绝", n4.threw && n4.message.includes("YYYY-MM-DD"), n4.message.slice(0, 40));
  const n5 = await callExpectError("caseEventList", { matterId: "" });
  check("P8e 空 matterId 拒绝", n5.threw && n5.message.includes("matterId"), n5.message.slice(0, 40));
  const n6 = await call("caseEventList", { matterId: "mat_nope", mode: "full" });
  check("P8f 未知案件读=空集（读面过滤语义，不伪造错误）", n6.events.length === 0, "empty");

  // ── P9 案件删级联 ──
  const c3 = await call("matterCreate", { name: "合成案·将删除" });
  await call("caseEventRecord", { matterId: c3.id, eventType: "接案", date: "2026-11-01" });
  await call("matterDelete", { id: c3.id });
  {
    const db = openDb();
    const left = db.prepare("SELECT COUNT(*) AS n FROM case_events WHERE matter_id = ?").get(c3.id).n;
    db.close();
    check("P9 案件删→时间线事件 FK 级联清", left === 0, `left=${left}`);
  }

  // ── P10 杀桥重启：字段全等+账本不重放 ──
  const migBefore = (() => { const db = openDb(); const n = db.prepare("SELECT COUNT(*) AS n FROM schema_migration").get().n; db.close(); return n; })();
  await killBridge("P10 重启实测");
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error("P10 重启桥 40s 不可探");
  await connect();
  {
    const full = await call("caseEventList", { matterId: c1.id, mode: "full" });
    const re = full.events.find((e: CaseEventProto) => e.eventId === e1.eventId);
    check("P10 重启后事件字段全等",
      re?.eventType === "开庭" && re?.date === "2026-11-02" && re?.note === "第一次开庭·合成区法院第3法庭"
        && re?.origin === "auto" && re?.provenance === "system",
      JSON.stringify(re));
    const db = openDb();
    const migAfter = db.prepare("SELECT COUNT(*) AS n FROM schema_migration").get().n;
    db.close();
    check("P10b 迁移账本不重放", migAfter === migBefore, `${migAfter}/${migBefore}`);
  }

  // ── P12 编辑流（对拍 30-32/D4-D5）：auto 行不可编辑字段值、可软删+还原 ──
  {
    const c4 = await call("matterCreate", { name: "合成案·编辑流" });
    const ev = await call("caseEventRecord", { matterId: c4.id, eventType: "接案", date: "2026-11-01", note: "原备注" });
    const rej = await callExpectError("caseEventEdit", { matterId: c4.id, eventId: ev.eventId, note: "改备注" });
    check("P12 auto 行编辑字段值拒绝（事实由业务动作定义）",
      rej.threw && rej.message.includes("不可编辑字段值"), rej.message.slice(0, 40));
    const hid = await call("caseEventSoftDelete", { matterId: c4.id, eventId: ev.eventId });
    check("P12b auto 行可软删隐藏（deleted=1）", hid.deleted === true, `deleted=${hid.deleted}`);
    const fullAfterHide = await call("caseEventList", { matterId: c4.id, mode: "full" });
    check("P12c 软删行不进 full 口径（只删显示不删库）",
      !fullAfterHide.events.some((e: CaseEventProto) => e.eventId === ev.eventId), `rows=${fullAfterHide.events.length}`);
    const delList = await call("caseEventDeletedList", { matterId: c4.id });
    check("P12d 还原 chips 源=deletedList（含软删行）", delList.events.length === 1 && delList.events[0].eventId === ev.eventId,
      `rows=${delList.events.length}`);
    const res = await call("caseEventRestore", { matterId: c4.id, eventId: ev.eventId });
    check("P12e 还原回 full 口径", res.deleted === false, `deleted=${res.deleted}`);
    const noLock = await callExpectError("caseEventEditRestore", { matterId: c4.id, eventId: ev.eventId, field: "note" });
    check("P12f 未覆盖字段恢复拒绝", noLock.threw && noLock.message.includes("被覆盖"), noLock.message.slice(0, 40));
    await call("matterDelete", { id: c4.id });
  }

  // ── P13 抽取通道空语料负路径（不调模型，确定性）──
  const tmpMat = join(REPO_ROOT, ".local", "timeline-synth-materials-" + PORT);
  {
    mkdirSync(join(tmpMat, "materials"), { recursive: true });
    const c5 = await call("matterCreate", { name: "合成案·抽取" });
    const e1 = await callExpectError("caseEventExtract", { matterId: c5.id, workspacePath: tmpMat });
    check("P13 空语料显式报错（停在空态不调模型）", e1.threw && e1.message.includes("语料为空"), e1.message.slice(0, 50));
    writeFileSync(join(tmpMat, "materials", "扫描件.docx"), "docx", "utf-8");
    const e2 = await callExpectError("caseEventExtract", { matterId: c5.id, workspacePath: tmpMat });
    check("P13b 仅非文本材料→报错含警告（语料不完整出警告口径）",
      e2.threw && e2.message.includes("非文本材料"), e2.message.slice(0, 80));
    writeFileSync(join(tmpMat, "materials", "空材料.txt"), "  ", "utf-8");
    const e3 = await callExpectError("caseEventExtract", { matterId: c5.id, workspacePath: tmpMat });
    check("P13c 空文本材料→正文为空警告", e3.threw && e3.message.includes("正文为空"), e3.message.slice(0, 80));
    // 忽略材料排除语义：仅剩的一份有效文本被忽略→仍空语料（用户排除不算缺口）
    writeFileSync(join(tmpMat, "materials", "起诉状（合成）.txt"), "合成起诉状正文。", "utf-8");
    const e4 = await callExpectError("caseEventExtract", { matterId: c5.id, workspacePath: tmpMat, ignoredMaterials: ["起诉状（合成）.txt"] });
    check("P13d 忽略材料不进语料（排除后空语料照报）", e4.threw && e4.message.includes("语料为空"), e4.message.slice(0, 60));
    await call("matterDelete", { id: c5.id });
    rmSync(tmpMat, { recursive: true, force: true });
  }

  // ── P14 工作汇报「办案时间轴」节导出（对拍 35 = CB C12 补齐）：服务端库内现值重算
  //      （full 口径=覆盖应用+软删滤+C3 排序）+零依赖 docx 装配（zip 头 PK）+文件名=案名-工作汇报 ──
  {
    const rep = await call("caseEventReportExport", { matterId: c1.id });
    const magic = Buffer.from(rep.docxBase64, "base64").subarray(0, 2).toString("latin1");
    const repNeg = await callExpectError("caseEventReportExport", { matterId: "mat_不存在" });
    check("P14 汇报导出（docx zip 头 PK+文件名=案名-工作汇报.docx）+未知案件显式拒",
      magic === "PK" && rep.fileName === "合成案·时间线甲-工作汇报.docx"
        && repNeg.threw && repNeg.message.includes("案件不存在"),
      `${rep.fileName} magic=${magic}`);
  }

  // ── P11 清场 ──
  await call("matterDelete", { id: c1.id });
  await call("matterDelete", { id: c2.id });
  const finC = await call("matterList");
  {
    const db = openDb();
    const left = db.prepare("SELECT COUNT(*) AS n FROM case_events").get().n;
    db.close();
    check("P11 清场归零（案件+事件）", finC.cases.length === 0 && left === 0, `cases=${finC.cases.length} events=${left}`);
  }
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

// ════════ 纯函数段（不经桥）：C3 排序/行键/去重/开庭三态/日期兜底/值域计数 ════════
try {
  const row = (eventId: string, eventType: string, date: string | null, createdAt: string) =>
    ({ eventId, eventType, date, createdAt });
  // E1 同日次序表 12 值 + 99 垫底（解封/还款期/白名单外同段）+ 无日期沉底
  const sorted = sortCaseEventsFull([
    row("f", "调解", "2026-01-01", "t1"),
    row("a", "接案", "2026-01-01", "t1"),
    row("z", "自定义事件", "2026-01-01", "t0"),
    row("b", "解封", "2026-01-01", "t1"),
    row("c", "申请立案", "2026-01-01", "t1"),
    row("d", "正式立案", "2026-01-01", "t1"),
    row("e", "还款期", "2026-01-01", "t1"),
    row("g", "判决", "2026-01-01", "t1"),
    row("h", "上诉", "2026-01-01", "t1"),
    row("i", "二审开庭", "2026-01-01", "t1"),
    row("j", "二审判决", "2026-01-01", "t1"),
    row("k", "执行立案", "2026-01-01", "t1"),
    row("l", "开发票", "2026-01-01", "t1"),
    row("m", "保全", "2026-01-01", "t1"),
    row("n", "开庭", "2026-01-01", "t1"),
    row("x", "开庭", "2026-02-01", "t1"),
    row("y", "接案", null, "t1"),
  ]);
  const got = sorted.map((r) => r.eventId).join(",");
  // 99 段内按 createdAt（z=t0 先于 b/e=t1）再 eventId 稳定；无日期 y 沉底
  check("E1 C3 全路径（日期升序→同日 12 值次序→99 同段按 createdAt→eventId→无日期沉底）",
    got === "a,c,d,m,n,f,g,h,i,j,k,l,z,b,e,x,y", got);
  check("E1b 次序值：接案=0/开发票=11/解封=99/还款期=99/白名单外=99",
    eventOrderOf("接案") === 0 && eventOrderOf("开发票") === 11
      && eventOrderOf("解封") === 99 && eventOrderOf("还款期") === 99 && eventOrderOf("自定义") === 99,
    `${eventOrderOf("接案")}/${eventOrderOf("解封")}`);

  // E2 行键（D6）：raw 值计算、缺值空串占位
  check("E2 rowKey=eventType|date（缺值空串）",
    rowKeyOf("开庭", "2026-11-02") === "开庭|2026-11-02" && rowKeyOf("接案", null) === "接案|" && rowKeyOf(null, null) === "|",
    rowKeyOf("接案", null));

  // E3 去重（C4）：date|event_type 保留首现
  const deduped = dedupByKeyKeepFirst(
    [{ id: 1 }, { id: 2 }, { id: 3 }] as Array<{ id: number }>,
    (_it) => "k",
  );
  void deduped;
  const items = [
    { d: "2026-01-01", t: "开庭", n: 1 },
    { d: "2026-01-01", t: "开庭", n: 2 },
    { d: "2026-01-01", t: "调解", n: 3 },
    { d: "2026-01-02", t: "开庭", n: 4 },
  ];
  const kept = dedupByKeyKeepFirst(items, (it) => `${it.d}|${it.t}`);
  check("E3 去重保留首现（date|event_type）", kept.length === 3 && kept[0].n === 1 && kept[2].n === 4,
    JSON.stringify(kept.map((k) => k.n)));

  // E4 开庭三态归一（C7）
  check("E4 开庭三态（将于/今日/已于+非法日期 null）",
    hearingStatusText("2026-11-02", "2026-10-27") === "将于 2026-11-02 开庭"
      && hearingStatusText("2026-10-27", "2026-10-27") === "今日开庭"
      && hearingStatusText("2026-10-20", "2026-10-27") === "已于 2026-10-20 开庭"
      && hearingStatusText(null, "2026-10-27") === null
      && hearingStatusText("11月2日", "2026-10-27") === null,
    `${hearingStatusText("2026-11-02", "2026-10-27")}/${hearingStatusText("2026-10-27", "2026-10-27")}`);

  // E5 日期精度三级（B18）
  check("E5 日期兜底三级（exact/range/unknown）",
    displayDateOf({ date: "2026-11-02", dateLabel: null }).precision === "exact"
      && displayDateOf({ date: null, dateLabel: "2026 年 11 月上旬" }).text === "2026 年 11 月上旬（日期待核对）"
      && displayDateOf({ date: "11月2日", dateLabel: null }).precision === "unknown"
      && displayDateOf({ date: null, dateLabel: null }).text === "日期待核对",
    "precision");

  // E6 值域计数（对拍 7/49/50 基数）
  check("E6 值域：CB 14/auto 21/FACT 11/次序表 12",
    CB_EVENT_TYPES.length === 14 && AUTO_EVENT_TYPES.length === 21 && FACT_EVENT_TYPES.length === 11
      && Object.keys(BUSINESS_ORDER).length === 12,
    `${CB_EVENT_TYPES.length}/${AUTO_EVENT_TYPES.length}/${FACT_EVENT_TYPES.length}/${Object.keys(BUSINESS_ORDER).length}`);
  check("E6b FACT ⊆ auto 枚举（客户白名单全部可由 auto 通道产出）",
    (FACT_EVENT_TYPES as readonly string[]).every((t) => (AUTO_EVENT_TYPES as readonly string[]).includes(t)),
    "subset");

  // ══ 件2 纯函数段 ══
  // E7 解析（B17/B22）：围栏容错/纯数组/不可解析抛错/非数组兜底空
  const fenced = "```json\n[{\"event_type\":\"开庭\"}]\n```";
  check("E7 围栏 JSON 解析", JSON.stringify(parseExtractionOutput(fenced)) === '[{"event_type":"开庭"}]', fenced.slice(0, 20));
  check("E7b 纯数组直解析", (parseExtractionOutput("[]").length === 0), "[]");
  let threw7 = false;
  try { parseExtractionOutput("模型说：抱歉我不能输出"); } catch { threw7 = true; }
  check("E7c 不可解析抛错（失败态+重试）", threw7, "threw");
  check("E7d 非数组 JSON 兜底空（B22）", JSON.stringify(parseExtractionOutput('{"a":1}')) === "[]" && JSON.stringify(parseExtractionOutput("null")) === "[]", "empty");

  // E8 后处理：双缺项过滤/坏日期沉原文/专项警告/去重/白名单外兜底
  const pp = postprocessExtracted([
    { event_type: "开庭", date: "2026-11-02", note: "" }, // 开庭缺 note → 警告
    { event_type: "开庭", date: "2026-11-02", note: "同键重复（应去重）" },
    { event_type: "", date: "" }, // 双缺项 → 丢
    { event_type: "接案", date: "2026 年 3 月" }, // 坏日期 → date_label 保留原文
    { event_type: "执行立案", note: "（2025）京01民初1号" }, // 审判案号 → 警告
    { event_type: "还款期", date: "2026-12-01", expires_at: "12月1日", payload: { amount_text: 12345, subjects: ["甲公司", ""] } },
    { event_type: "某次沟通", status: "怪值", source_refs: [{ filename: "a.txt", quote: "x".repeat(400) }, { filename: "" }, "junk"] },
  ]);
  check("E8 双缺项过滤+开庭去重+坏日期沉原文",
    pp.rows.length === 5 && pp.rows.filter((r) => r.eventType === "开庭").length === 1
      && pp.rows.find((r) => r.eventType === "接案")?.dateLabel === "2026 年 3 月"
      && pp.rows.find((r) => r.eventType === "接案")?.date === null,
    JSON.stringify(pp.rows.map((r) => r.eventType)));
  check("E8b 专项警告（开庭缺详情/执行立案未见执行案号）",
    pp.warnings.some((w) => w.includes("开庭节点缺庭审详情"))
      && pp.warnings.some((w) => w.includes("执行立案") && w.includes("执行案号")),
    JSON.stringify(pp.warnings));
  const repay = pp.rows.find((r) => r.eventType === "还款期");
  check("E8c amount_text 非字符串丢（禁浮点）+坏 expires_at 置空+subjects 净化",
    repay?.expiresAt === null && repay?.payload != null && !("amount_text" in repay.payload)
      && JSON.stringify(repay.payload.subjects) === '["甲公司"]',
    JSON.stringify(repay?.payload));
  const freeRow = pp.rows.find((r) => r.eventType === "某次沟通");
  check("E8d 白名单外自由文本兜底+status 归一 confirmed+source_refs 净化（quote 截 300/丢无名/丢非对象）",
    !!freeRow && freeRow.status === "confirmed" && freeRow.sourceRefs.length === 1
      && (freeRow.sourceRefs[0].quote?.length ?? 0) === 300,
    JSON.stringify(freeRow?.sourceRefs));

  // E9 定向 hint 11 分支（8 加节点+3 不加+空默认；对拍 8 同构）
  check("E9 hint 映射（起诉状→申请立案/调解书→还款期细则/解封→置空到期/裁定书·答辩状·执行通知书不加节点/空默认）",
    docHintOf("民事起诉状（合成）.txt").hint.includes("申请立案")
      && docHintOf("调解书.txt").hint.includes("还款期")
      && docHintOf("解封裁定.txt").hint.includes("置空")
      && docHintOf("保全裁定.txt").hint.includes("expires_at")
      && docHintOf("传票.txt").hint.includes("禁止写当事人")
      && docHintOf("执行通知书.txt").addNodes === false
      && docHintOf("答辩状.txt").addNodes === false
      && docHintOf("行政裁定书.txt").addNodes === false
      && docHintOf("会议纪要.txt").addNodes === true && docHintOf("会议纪要.txt").hint === "",
    "hints");

  // E10 编辑流纯函数（D2/D3）：orig 快照/重复编辑不覆盖快照/↺ 恢复回 ai
  const llmRow: CaseEventProto = {
    eventId: "ce_x", matterId: "m1", eventType: "开庭", date: "2026-11-02",
    dateLabel: null, note: "原始备注", expiresAt: null, status: "confirmed", importance: "normal",
    phase: null, side: null, origin: "llm_extract", sourceRefs: [], payload: null,
    provenance: "ai", lockedFields: [], orig: null, deleted: false,
    createdAt: "t0", updatedAt: "t0",
  };
  const edit1 = applyCaseEventEdit(llmRow, { date: "2026-11-05", note: "改" }, "t1");
  check("E10 编辑写覆盖（orig 快照原值+locked+provenance=user）",
    edit1.cols.orig_json === '{"date":"2026-11-02","note":"原始备注"}'
      && edit1.cols.locked_fields_json === '["date","note"]'
      && edit1.cols.provenance === "user" && edit1.cols.date === "2026-11-05",
    JSON.stringify(edit1.cols));
  const editedRow: CaseEventProto = { ...llmRow, date: "2026-11-05", note: "改", provenance: "user",
    lockedFields: ["date", "note"], orig: { date: "2026-11-02", note: "原始备注" } };
  const edit2 = applyCaseEventEdit(editedRow, { note: "再改" }, "t2");
  check("E10b 重复编辑不覆盖快照（↺ 永远回抽取原值）",
    edit2.cols.orig_json === '{"date":"2026-11-02","note":"原始备注"}', String(edit2.cols.orig_json));
  const res1 = restoreCaseEventField(editedRow, "note", "t3");
  check("E10c ↺ 恢复单字段（note 回原值+note 锁清+date 锁仍在+provenance 不动）",
    res1.cols.note === "原始备注" && res1.cols.locked_fields_json === '["date"]' && !("provenance" in res1.cols),
    JSON.stringify(res1.cols));
  const resAll = restoreCaseEventField({ ...editedRow, lockedFields: ["date"] }, "date", "t4");
  check("E10d 锁全清且 llm_extract 来源→provenance 回 ai",
    resAll.cols.locked_fields_json === "[]" && resAll.cols.provenance === "ai", JSON.stringify(resAll.cols));
  let threw10 = false;
  try { applyCaseEventEdit({ ...llmRow, origin: "auto" }, { note: "x" }, "t"); } catch { threw10 = true; }
  check("E10e auto 行编辑拒绝（桥面同规）", threw10, "threw");

  // E11 重抽 COALESCE 合并（D7）：命中更新未锁字段/锁字段保现值/旧键保留/新键插入/user·auto 不碰
  const existing: CaseEventProto[] = [
    { ...llmRow, eventId: "ce_1", eventType: "开庭", date: "2026-11-02", note: "旧备注" },
    { ...llmRow, eventId: "ce_2", eventType: "调解", date: "2026-10-01", note: "将被保留（新语料没有）" },
    { ...llmRow, eventId: "ce_3", eventType: "判决", date: "2026-12-01", note: "锁定备注", lockedFields: ["note"], orig: { note: "原判备注" } },
    { ...llmRow, eventId: "ce_4", eventType: "材料登记", date: "2026-10-27", origin: "auto", provenance: "system" },
  ];
  const inc = (eventType: string, date: string | null, note: string | null, expiresAt: string | null = null): ExtractedRow => ({
    eventType, date, dateLabel: null, note, expiresAt, status: "confirmed",
    importance: "normal", phase: null, side: null, sourceRefs: [], payload: null,
  });
  const plan = planCaseEventMerge(existing, [
    inc("开庭", "2026-11-02", "新备注"),
    inc("还款期", "2026-12-20", null, "2026-12-20"),
    inc("二审开庭", "2027-01-05", null),
  ], "t9");
  check("E11 合并：命中更新未锁字段（ce_1 note 更新）/新键插入 2 条/旧键保留 2 条（ce_2 无新语料+ce_3 锁字段——都防子集抹除）",
    plan.updates.length === 1 && plan.updates[0].eventId === "ce_1" && plan.updates[0].cols.note === "新备注"
      && plan.inserts.length === 2 && plan.keptCount === 2,
    JSON.stringify({ u: plan.updates.length, i: plan.inserts.length, k: plan.keptCount }));
  check("E11b COALESCE：锁字段（ce_3 note）不更新；auto 行（ce_4）不入合并键",
    !plan.updates.some((u) => u.eventId === "ce_3") && !plan.inserts.some((i) => i.eventType === "材料登记"),
    "locked-untouched");

  // E12 技能包合同（RE-4 §3 技能类附加；真源=skill-presets/timeline-generation，桥运行时读取）
  const tr = TIMELINE_SKILL_META.triggers ?? {};
  check("E12 触发族（/时间线 命令+pattern 族+四类 fileTypes+无工具+priority 0）",
    JSON.stringify(tr.commands) === '["/时间线"]'
      && tr.promptPatterns?.[0] === "时间线|时间轴|大事记|案件经过|事件梳理"
      && JSON.stringify(tr.fileTypes) === '[".pdf",".docx",".txt",".md"]'
      && Array.isArray(TIMELINE_SKILL_META.allowedTools) && TIMELINE_SKILL_META.allowedTools.length === 0
      && TIMELINE_SKILL_META.priority === 0,
    JSON.stringify(tr));
  const checks10 = (TIMELINE_SKILL_MD.match(/^[0-9]+\. ☐/gm) ?? []).length;
  check("E12b SKILL.md 章节合同（三格式/法律声明五点/八字段表/六场景/十项自检/操作五步）",
    TIMELINE_SKILL_MD.includes("时间线表格") && TIMELINE_SKILL_MD.includes("mermaid") && TIMELINE_SKILL_MD.includes("结构化事件清单")
      && TIMELINE_SKILL_MD.includes("法律声明") && (TIMELINE_SKILL_MD.match(/^¥?[0-9]+\. /gm) ?? []).length >= 5
      && TIMELINE_SKILL_MD.includes("涉及金额") && TIMELINE_SKILL_MD.includes("场景重点")
      && checks10 === 10 && TIMELINE_SKILL_MD.includes("操作五步"),
    `selfChecks=${checks10}`);
  // E12c 英文线证明地图合同（对拍 23：三分类/证言文书冲突/空白期旁证/多流分离/三节输出/.docx 交付）
  check("E12c 证明地图节（有利·不利·中立三分类/证言只作佐证弹劾/空白期须连续性旁证/多请求抗辩不混流/主表四列+空白期+聚类要日期三节+下一步建议/.docx）",
    TIMELINE_SKILL_MD.includes("证明地图") && TIMELINE_SKILL_MD.includes("有利／不利／中立")
      && TIMELINE_SKILL_MD.includes("佐证或弹劾") && TIMELINE_SKILL_MD.includes("连续性旁证")
      && TIMELINE_SKILL_MD.includes("不混流") && TIMELINE_SKILL_MD.includes("Strategic Assessment")
      && TIMELINE_SKILL_MD.includes("空白期分析节") && TIMELINE_SKILL_MD.includes("聚类要日期节")
      && TIMELINE_SKILL_MD.includes("下一步建议") && TIMELINE_SKILL_MD.includes(".docx"),
    "proof-map");

  // ══ r8 缺项补齐（对拍增补 63·对照源二和讼）：逐条双引用+置信度 ══
  // E8e 增补 63 警告面：缺（材料名+页码/段落）双引用与缺置信度逐行透出（只警告不阻断不编造——
  // 有材料名无页码也算缺双引用；payload 全空被净化回 null 一样算缺置信度）
  const pp63 = postprocessExtracted([
    { event_type: "开庭", date: "2026-11-02", note: "无出处无置信度" },
    { event_type: "接案", date: "2026-11-01", source_refs: [{ filename: "委托合同（合成）.txt" }], payload: { confidence: 1.7 } },
    { event_type: "调解", date: "2026-11-03", source_refs: [{ filename: "调解书（合成）.txt", locator: "第1页" }], payload: { confidence: "0.65" } },
    { event_type: "判决", date: "2026-11-04", source_refs: [{ filename: "判决书（合成）.txt", locator: "第2页" }], payload: { confidence: "高" } },
  ]);
  check("E8e 增补 63 警告：缺双引用 2 行（无出处/有名无页码）+缺置信度 2 行（无 payload/非数值被丢）",
    pp63.warnings.filter((w) => w.includes("双引用")).length === 2
      && pp63.warnings.filter((w) => w.includes("缺置信度")).length === 2
      && pp63.warnings.some((w) => w.includes("开庭 2026-11-02")),
    JSON.stringify(pp63.warnings));
  const r63a = pp63.rows.find((r) => r.eventType === "接案");
  const r63b = pp63.rows.find((r) => r.eventType === "调解");
  const r63c = pp63.rows.find((r) => r.eventType === "判决");
  check("E8f confidence 净化：1.7 钳到 1/字符串 0.65 收数值/非数值「高」丢弃（payload 全空→null 不造值）",
    r63a?.payload?.confidence === 1 && r63b?.payload?.confidence === 0.65 && r63c?.payload === null,
    `${r63a?.payload?.confidence}/${r63b?.payload?.confidence}/${JSON.stringify(r63c?.payload)}`);
  // E12d 抽取 prompt 出处与置信度合同（单源在 assembleExtractionPrompt）
  const prompt63 = assembleExtractionPrompt([{ name: "甲（合成）.txt", text: "正文（合成）", hint: "", addNodes: true }], "2026-10-28");
  check("E12d prompt 出处与置信度纪律（逐条文件+页码/段落双引用/查不到出处不输出/不猜页码/confidence 0-1 必给）",
    prompt63.includes("出处与置信度纪律") && prompt63.includes("页码或段落定位")
      && prompt63.includes("不要输出") && prompt63.includes("不要猜页码") && prompt63.includes("confidence"),
    "prompt63");
  // E12e SKILL.md 增补 63 合同（逐条双引用+置信度自评/缺出处标注待补不编造/结构化清单含 confidence 落点）
  check("E12e SKILL 增补 63 合同（双引用缺一不可/查不到出处不输出不猜页码/置信度 0-1 自评拿不准给低值/清单字段含 confidence）",
    TIMELINE_SKILL_MD.includes("双引用") && TIMELINE_SKILL_MD.includes("不猜页码")
      && TIMELINE_SKILL_MD.includes("置信度") && TIMELINE_SKILL_MD.includes("0-1")
      && TIMELINE_SKILL_MD.includes("拿不准给低值") && TIMELINE_SKILL_MD.includes("confidence"),
    "skill63");

  // ══ 补齐件（2026-10-28 对拍 34/35）纯函数段 ══
  // E13 工作汇报行（C12 等量，文案自写）：齐全/无日期兜底/无事件兜底/备注空省略/空表整句
  const rp = buildCaseTimelineReportLines([
    { eventType: "开庭", date: "2026-11-02", note: "第一次开庭·合成区法院第3法庭" },
    { eventType: "接案", date: null, note: null },
    { eventType: "  ", date: "2026-01-03", note: "  " },
  ]);
  check("E13 汇报行（齐全/无日期兜底/无事件兜底/空白备注省略）",
    rp.empty === false && rp.lines.length === 3
      && rp.lines[0].dateText === "2026-11-02" && rp.lines[0].eventText === "开庭"
      && rp.lines[0].noteText === "第一次开庭·合成区法院第3法庭"
      && rp.lines[1].dateText === CASE_REPORT_DATE_FALLBACK
      && rp.lines[2].eventText === CASE_REPORT_EVENT_FALLBACK && rp.lines[2].noteText === null,
    JSON.stringify(rp.lines));
  const rpEmpty = buildCaseTimelineReportLines([]);
  check("E13b 空表=空态句（不渲染行；坏日期串落兜底不造日历日）",
    rpEmpty.empty === true && rpEmpty.lines.length === 0 && CASE_REPORT_EMPTY_TEXT.length > 0
      && buildCaseTimelineReportLines([{ eventType: "开庭", date: "11月2日", note: null }]).lines[0].dateText === CASE_REPORT_DATE_FALLBACK,
    CASE_REPORT_EMPTY_TEXT);

  // E16 时间线节点→提醒输入（对拍 34/CB E1 补齐）：三族进/解封压制/孪生让位/无到期不猜/案名入题
  const ceRow = (eventId: string, matterId: string, eventType: string, date: string | null, expiresAt: string | null = null) =>
    ({ eventId, matterId, eventType, date, expiresAt });
  const tlOut = boardTimelineReminderInputs({
    caseEvents: [
      ceRow("ce_1", "m1", "开庭", "2026-11-02"),
      ceRow("ce_2", "m1", "还款期", "2026-12-01", "2026-12-10"),
      ceRow("ce_3", "m2", "还款期", "2026-12-01", null),
      ceRow("ce_4", "m2", "保全", "2026-10-27", "2027-10-27"),
      ceRow("ce_5", "m2", "解封", "2026-11-30", null),
      ceRow("ce_6", "m1", "开庭", "2026-11-05", null),
      ceRow("ce_7", "m3", "保全", "2026-10-01", null),
      ceRow("ce_8", "m1", "建案", today, null),
    ],
    boardEvents: [{ caseId: "m1", date: "2026-11-05" }],
    caseNameOf: (id: string) => (id === "m1" ? "合成案甲" : id === "m2" ? "合成案乙" : null),
  });
  check("E16 提醒输入（开庭/还款期 expires 优先+名称回落/保全到期；解封压制续封/孪生让位/无到期不猜/非三族不进/案名入题/默认提前 30+date-only 归一）",
    tlOut.length === 3
      && tlOut.map((r) => r.id).join(",") === "cev:ce_1,cev:ce_2,cev:ce_3"
      && tlOut[0].title === "合成案甲 · 开庭" && tlOut[0].date === "2026-11-02"
      && tlOut[1].date === "2026-12-10"
      && tlOut[2].title === "合成案乙 · 还款期" && tlOut[2].date === "2026-12-01"
      && tlOut.every((r) => r.remind === true && r.startAt === null && r.remindMinutes === BOARD_DEFAULT_LEAD_MINUTES),
    JSON.stringify(tlOut));
  // E16b 解封早于保全开始→不压制（宁提醒勿漏，CB-B11 同语义）
  const tlOut2 = boardTimelineReminderInputs({
    caseEvents: [ceRow("ce_9", "m3", "保全", "2026-10-27", "2027-10-27"), ceRow("ce_10", "m3", "解封", "2026-01-01", null)],
    boardEvents: [],
    caseNameOf: () => null,
  });
  check("E16b 解封早于保全开始→不压制+案名缺失退类型",
    tlOut2.length === 1 && tlOut2[0].id === "cev:ce_9" && tlOut2[0].title === "保全" && tlOut2[0].date === "2027-10-27",
    JSON.stringify(tlOut2));
} catch (e) {
  check("纯函数段", false, e?.message ?? String(e));
}

const pass = results.every((r) => r.ok);
console.log(pass ? "TIMELINE_SYNTH_PASS" : "TIMELINE_SYNTH_FAIL");
process.exit(pass ? 0 : 1);
