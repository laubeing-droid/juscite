// 功能 #29 新手引导合成用例（RE-29 §2 行为清单验收口径，全部合成材料）：
//   A 首启判定（A1 pending / P2b 同版本重开不翻判 / G3 强布尔 / G4 字面量校验 / D10 幂等重看）
//   B 旧库升级（A2：meta 缺 onboarding.status → 一次性 completed/skipped，守卫不重写）
//   C 演示导入（C2 台账防重 / C4 计数与本周锚定 / C6 demoChoice=demo / G6 单事务）
//   D 四表卫检（C3：任一非空即拒 + 回滚不落盘）
//   F 法库指路（F1 不可用拦截 / F2 状态查询抛错 fail-closed；行形态=laws-guide 本地注入，不触模型）
// 自管隔离桥实例（3071-3074，独立 bridge-{port}.db），不碰 :3030/:43127；末行 ONBOARD_SYNTH_PASS/FAIL。
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { isLawsRetrievalIntent, LAWS_GUIDANCE, currentWeekMonday } from "./onboarding_service.mjs";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const NODE = process.execPath;
const BRIDGE_DIR = join(homedir(), "AppData", "Roaming", "Juscite", "bridge");
const LAWS_DIR = join(BRIDGE_DIR, "laws");
const LAWS_INDEX = join(LAWS_DIR, "index.json");
const dbPathOf = (port) => join(BRIDGE_DIR, `bridge-${port}.db`);

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok });
  console.log(`[onboard-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function openDb(port) {
  const db = new DatabaseSync(dbPathOf(port));
  db.exec("PRAGMA busy_timeout = 5000"); // 桥进程持 WAL 时直读/直写等待，不立即 SQLITE_BUSY
  return db;
}
function countOf(db, table) { return db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n; }

function killPortBridge(port) {
  // 防跨轮连旧实例：占端口的进程若是 bridge_host.mjs 才杀（宁停不误杀）
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue).OwningProcess`],
    { encoding: "utf-8", timeout: 20000 });
  const pid = Number(String(r.stdout ?? "").trim().split(/\s+/)[0]);
  if (!pid) return;
  const cl = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  if (String(cl.stdout ?? "").includes("bridge_host.mjs")) {
    spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
    console.log(`[onboard-synth] 清理端口 ${port} 残留桥 pid=${pid}`);
  }
}

function spawnBridge(port) {
  const log = openSync(join(REPO_ROOT, ".local", `onboard-synth-bridge-${port}.log`), "a");
  const child = spawn(NODE, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(port) }, stdio: ["ignore", log, log], detached: true });
  child.unref();
  return child.pid;
}
async function probe(port) {
  try {
    const r = await fetch(`http://127.0.0.1:${port}/api/server-info`, { signal: AbortSignal.timeout(2500) });
    return r.ok && JSON.parse(await r.text()).store === "sqlite";
  } catch { return false; }
}
async function waitProbe(port, timeoutMs = 40000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) { if (await probe(port)) return true; await sleep(500); }
  return false;
}
async function killBridge(pid, port) {
  const cl = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  if (!String(cl.stdout ?? "").includes("bridge_host.mjs")) {
    throw new Error(`拒绝杀进程 pid=${pid}：命令行不含 bridge_host.mjs`);
  }
  spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probe(port))) await sleep(500);
}

// ---- RPC 客户端（每次重启桥后重连）----
let ch = null;
let ws = null;
async function connect(port) {
  ws = new WebSocket(`ws://127.0.0.1:${port}/ws`);
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
const callRaw = async (m, a) => { try { return { ok: true, v: await call(m, a) }; } catch (e) { return { ok: false, err: String(e?.message ?? e) }; } };

async function sendText(port, sessionId, text) {
  return call("sendConversationCommandV4", {
    workspacePath: "D:\mock\lvyin-demo", projectId: "lvyin-demo",
    envelope: { commandId: "cmd_ob_" + Math.random().toString(36).slice(2, 10), clientId: "onboard-synth",
      sessionId, type: "sendText", payload: { text }, issuedAt: Date.now() },
  });
}
async function createSession(port, sessionId) {
  return call("sendConversationCommandV4", {
    workspacePath: "D:\mock\lvyin-demo", projectId: "lvyin-demo",
    envelope: { commandId: "cmd_ob_new_" + Math.random().toString(36).slice(2, 10), clientId: "onboard-synth",
      sessionId: null, type: "createSession", payload: { sessionId, workspaceId: "D:\mock\lvyin-demo" }, issuedAt: Date.now() },
  });
}

// 意图判别与周一锚（纯函数直测，不开桥）
check("F1 意图判别正例", ["检索一下民间借贷的法条", "查一下诉讼时效相关法规", "帮我找一下法律依据"]
  .every((t) => isLawsRetrievalIntent(t)), "检索类动词×法规对象组合命中");
check("F1 意图判别负例", ["总结一下这份合同", "帮我起草起诉状", "你好"].every((t) => !isLawsRetrievalIntent(t)),
  "无检索动词或无法规对象不误拦");
{
  const m = currentWeekMonday();
  const d = new Date(m);
  check("周一锚定", d.getDay() === 1 && d.getHours() === 9, `getDay=${d.getDay()}（1=周一）`);
}

const pids = [];
try {
  // ── A 组：首启判定/强布尔/幂等/tour 上报（端口 3071，全新库）──
  const PA = 3071;
  killPortBridge(PA);
  rmSync(dbPathOf(PA), { force: true }); // 全新起点：删自管库文件（非用户数据）
  let pid = spawnBridge(PA);
  pids.push(pid);
  if (!(await waitProbe(PA))) throw new Error(`隔离桥 :${PA} 不可探`);
  await connect(PA);
  let st = await call("onboardingGet");
  check("A1 首启 pending+未置+未导入", st.status === "pending" && st.guideStatus === "pending"
    && st.demoChoice === null && st.demoImported === false, JSON.stringify(st));

  await killBridge(pid, PA);
  pid = spawnBridge(PA);
  await waitProbe(PA);
  await connect(PA);
  st = await call("onboardingGet");
  check("P2b 同版本 pending 重开不翻判", st.status === "pending" && st.guideStatus === "pending", JSON.stringify(st));

  // G3 强布尔：非 true 一律按 false
  const stG3 = await call("onboardingComplete", { demo: "true", startGuide: 1 });
  check("G3 强布尔+blank 路径", stG3.status === "completed" && stG3.demoChoice === "blank"
    && stG3.guideStatus === "skipped" && stG3.demoImported === false, JSON.stringify(stG3));
  {
    const db = openDb(PA);
    const seeded = ["demo_cases", "demo_documents", "demo_clients", "demo_schedule_events"].map((t) => countOf(db, t));
    db.close();
    check("blank 完成不导入任何演示数据", seeded.every((n) => n === 0), `counts=${seeded.join(",")}`);
  }

  // 幂等（D10/G3）：已 completed 再调（即使 demo:true）不重导、返回现状
  const stIdem = await call("onboardingComplete", { demo: true, startGuide: true });
  check("D10 幂等完成不重导", stIdem.status === "completed" && stIdem.demoChoice === "blank"
    && stIdem.demoImported === false && stIdem.guideStatus === "skipped", JSON.stringify(stIdem));

  // G4/D10：guideStatus 三态+非法拒收；重看不改 status
  const stG4a = await call("onboardingGuideStatus", { status: "completed" });
  const stG4b = await call("onboardingGuideStatus", { status: "skipped" });
  const g4bad = await callRaw("onboardingGuideStatus", { status: "bogus" });
  check("G4 guideStatus 合法写入+非法显式拒", stG4a.guideStatus === "completed" && stG4b.guideStatus === "skipped"
    && g4bad.ok === false && (g4bad.err ?? "").includes("无效的产品指引状态"), `a=${stG4a.guideStatus} b=${stG4b.guideStatus} err=${g4bad.err ?? ""}`);
  check("D10 重看不改 status", stG4b.status === "completed", `status=${stG4b.status}`);

  // F1：法库未安装 → 检索意图被拦，本地指路行注入，不触模型
  rmSync(LAWS_DIR, { recursive: true, force: true });
  {
    const sid = "ses_ob_f1_0001";
    await createSession(PA, sid);
    const ack = await sendText(PA, sid, "帮我检索一下民间借贷利率的法条和法规依据");
    await sleep(1200);
    const db = openDb(PA);
    const rows = db.prepare("SELECT * FROM session_rows WHERE session_id = ? ORDER BY row_seq").all(sid);
    db.close();
    const guide = rows.map((r) => JSON.parse(r.row_json)).find((r) => r.model === "laws-guide");
    check("F1 检索意图被拦+指路行注入", ack?.status === "accepted" && rows.length === 2
      && rows[0].kind === "userInput" && !!guide && guide.text === LAWS_GUIDANCE.unavailable,
      `rows=${rows.length} guide=${guide ? guide.text.slice(0, 18) + "…" : "无"}`);
  }
  // F2：法库状态查询抛错（索引损坏）→ fail-closed 指路，不静默失败
  {
    mkdirSync(LAWS_DIR, { recursive: true });
    writeFileSync(LAWS_INDEX, "{corrupt", "utf-8");
    const sid = "ses_ob_f2_0001";
    await createSession(PA, sid);
    await sendText(PA, sid, "查一下诉讼时效的法律法规");
    await sleep(1200);
    const db = openDb(PA);
    const rows = db.prepare("SELECT * FROM session_rows WHERE session_id = ? ORDER BY row_seq").all(sid);
    db.close();
    const guide = rows.map((r) => JSON.parse(r.row_json)).find((r) => r.model === "laws-guide");
    check("F2 状态查询抛错 fail-closed 指路", rows.length === 2 && !!guide && guide.text === LAWS_GUIDANCE.error,
      `guide=${guide ? guide.text.slice(0, 18) + "…" : "无"}`);
    rmSync(LAWS_DIR, { recursive: true, force: true }); // 清理自家命名空间
  }
  await killBridge(pid, PA);

  // ── B 组：旧库升级（端口 3072；A2：meta 缺 onboarding.status → 一次性 completed/skipped）──
  const PB = 3072;
  killPortBridge(PB);
  rmSync(dbPathOf(PB), { force: true });
  pid = spawnBridge(PB);
  await waitProbe(PB);
  await connect(PB);
  await killBridge(pid, PB);
  {
    // 模拟"真旧库"：删除三键（库文件在、meta 无 onboarding.status）。
    // 强杀后 WAL 收尾可能短暂持锁：重试数轮再放弃。
    let deleted = false;
    for (let i = 0; i < 6 && !deleted; i++) {
      await sleep(1000);
      try {
        const db = openDb(PB);
        db.prepare("DELETE FROM app_meta WHERE key LIKE 'onboarding.%'").run();
        db.close();
        deleted = true;
      } catch (e) {
        console.log(`[onboard-synth] meta 清理第 ${i + 1} 次重试：${String(e?.message ?? e).slice(0, 60)}`);
      }
    }
    if (!deleted) throw new Error("旧库 meta 清理失败（WAL 锁未释放）");
  }
  pid = spawnBridge(PB);
  await waitProbe(PB);
  await connect(PB);
  st = await call("onboardingGet");
  check("A2 旧库升级一次性 completed/skipped", st.status === "completed" && st.guideStatus === "skipped", JSON.stringify(st));
  await killBridge(pid, PB);
  pid = spawnBridge(PB);
  await waitProbe(PB);
  await connect(PB);
  st = await call("onboardingGet");
  check("A2 守卫不重写（升级态稳定）", st.status === "completed" && st.guideStatus === "skipped", JSON.stringify(st));
  await killBridge(pid, PB);

  // ── C 组：演示导入（端口 3073；C2/C4/C6/G6）──
  const PC = 3073;
  killPortBridge(PC);
  rmSync(dbPathOf(PC), { force: true });
  pid = spawnBridge(PC);
  await waitProbe(PC);
  await connect(PC);
  const stDemo = await call("onboardingComplete", { demo: true, startGuide: true });
  check("C6 demo 完成四元组", stDemo.status === "completed" && stDemo.demoChoice === "demo"
    && stDemo.guideStatus === "pending" && stDemo.demoImported === true, JSON.stringify(stDemo));
  {
    const db = openDb(PC);
    const n = {
      cases: countOf(db, "demo_cases"), clients: countOf(db, "demo_clients"),
      documents: countOf(db, "demo_documents"), schedule: countOf(db, "demo_schedule_events"),
      tasks: countOf(db, "demo_tasks"), parties: countOf(db, "demo_parties"),
      evidence: countOf(db, "demo_evidence"), strategies: countOf(db, "demo_strategies"),
      stages: countOf(db, "demo_stage_events"),
      ledger: countOf(db, "onboarding_demo_ledger"),
    };
    const monday = currentWeekMonday();
    const sched = db.prepare("SELECT MIN(due_at) AS lo, MAX(due_at) AS hi FROM demo_schedule_events").get();
    db.close();
    check("C4 演示集计数（六案/六客/八文档/七日程/任务8/当事人3/证据4/策略1/节点3/台账1）",
      n.cases === 6 && n.clients === 6 && n.documents === 8 && n.schedule === 7 && n.tasks === 8
      && n.parties === 3 && n.evidence === 4 && n.strategies === 1 && n.stages === 3 && n.ledger === 1,
      JSON.stringify(n));
    check("C4 日程全部落当前自然周（周一 00:00 起 7 天内）", sched.lo >= monday - 9 * 3600_000 && sched.hi < monday + 7 * 86_400_000,
      `span=[${new Date(sched.lo).toISOString()},${new Date(sched.hi).toISOString()}] monday=${new Date(monday).toISOString()}`);
    // C2 台账防重：再调 complete 不重导
    await call("onboardingComplete", { demo: true });
    const db2 = openDb(PC);
    const n2 = { cases: countOf(db2, "demo_cases"), ledger: countOf(db2, "onboarding_demo_ledger") };
    db2.close();
    check("C2 台账防重不重复灌", n2.cases === 6 && n2.ledger === 1, JSON.stringify(n2));
  }
  await killBridge(pid, PC);

  // ── D 组：四表卫检+回滚（端口 3074；C3/B7）──
  const PD = 3074;
  killPortBridge(PD);
  rmSync(dbPathOf(PD), { force: true });
  pid = spawnBridge(PD);
  await waitProbe(PD);
  await connect(PD);
  {
    const db = openDb(PD);
    db.prepare("INSERT INTO demo_cases (case_id, name, created_at) VALUES ('real_1', '既有业务案件（合成占位）', 0)").run();
    db.close();
  }
  const g = await callRaw("onboardingComplete", { demo: true, startGuide: false });
  {
    const db = openDb(PD);
    const after = {
      status: db.prepare("SELECT value FROM app_meta WHERE key='onboarding.status'").get()?.value,
      ledger: countOf(db, "onboarding_demo_ledger"),
      clients: countOf(db, "demo_clients"),
      docs: countOf(db, "demo_documents"),
    };
    db.close();
    check("C3 四表卫检显式拒绝", g.ok === false && /(导入已取消|业务数据)/.test(g.err ?? ""), `err=${(g.err ?? "").slice(0, 50)}`);
    check("B7 卫检失败回滚不落盘（状态/台账/种子均未动）",
      after.status === "pending" && after.ledger === 0 && after.clients === 0 && after.docs === 0, JSON.stringify(after));
  }
  await killBridge(pid, PD);
} finally {
  // 清场：不留隔离桥进程（自家端口自管实例）
  for (const port of [3071, 3072, 3073, 3074]) killPortBridge(port);
  rmSync(LAWS_DIR, { recursive: true, force: true });
}

const failed = results.filter((r) => !r.ok);
for (const f of failed) console.log(`[onboard-synth] FAILED: ${f.name}`);
console.log(failed.length ? "ONBOARD_SYNTH_FAIL" : "ONBOARD_SYNTH_PASS");
process.exit(failed.length ? 1 : 0);
