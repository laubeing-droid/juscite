// 功能 #30 安全审计中心合成用例（RE-30 §2 行为清单验收口径，全部合成材料）：
//   A 链层直测（内存/临时库）：空库验真 P1 / v1 追加形状 P2 / 有密钥 v3+混链 P3 / v2 兼容 P5 /
//     迁移幂等 P4 / 篡改-断链-删行验假 P6-P8-P11 / limit 窗口 P9 / 密钥解不开 fail-closed 保留原值 P12
//   B UI 纯模型（经 tsx 引 securityAuditModel.ts）：隐私行判定容错 / 场景 9 类映射 / 时间双试回退 /
//     摘要 >24 截断阈值 / chips≤3 与 +N 类 / totalMatches 合计优先 / 详情回退链 m=??[0]??null
//   C 桥 RPC 真跑（隔离桥实例独立端口独立库，不碰 :3030/:43127）：audit.list {rows,chainOk} 同返 /
//     audit.append 渲染层通道 / 写入面 case.*/task.*/schedule.*/stealth.on-off/doc.export/doc.delete/
//     材料域 file.upload/file.parse 逐动作落行 / 读操作不虚设行 / 全程链验真。末行 RE30_SYNTH_PASS / RE30_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { createAuditService } from "./audit_service.mjs";
import {
  AUDIT_POLICY_VERSION, formatAuditTime, hitChipsOf, hitLinesOf, opsDetailSummary,
  privacyDetailOf, scenarioKeyOf, scenarioName, selectEffectiveRow, totalHitsOf, truncateDigest,
  type AuditRow,
} from "../../packages/juscite-legal/src/panels/securityAuditModel.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const NODE = process.execPath;
const results: Array<{ name: string; ok: boolean }> = [];
function check(name: string, ok: boolean, detail = "") {
  results.push({ name, ok });
  console.log(`[re30-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
  return ok;
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ══════════════ A. 链层直测 ══════════════
function freshDb(): DatabaseSync {
  const db = new DatabaseSync(":memory:");
  db.exec(`CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT DEFAULT (datetime('now')))`); // 生产由迁移 0005 建；直测自备
  return db;
}
const PRIVACY_DETAIL = JSON.stringify({
  kind: "privacy-redaction", requestId: "sum-abc123", scenario: "summary", provider: "deepseek",
  model: "deepseek-chat", policyVersion: AUDIT_POLICY_VERSION, status: "success",
  originalChars: 1200, outboundChars: 1130, totalMatches: 7,
  counts: { person_name: 3, id_card: 2, bank_card: 2 }, toolCalls: 1,
  payloadDigest: "a".repeat(64),
});

// A1 空库 verify=true（P1）
{
  const audit = createAuditService(freshDb());
  check("A1 空库验链=true", audit.verifyAuditChain() === true);
}
// A2 无密钥 v1 追加×2（P2）。预置坏密文走 fail-closed 键-less 分支——按 §3.3 缺失即自动生成密钥
// （首启即 v3），v1 形态只在无密钥可写时出现，故用坏密文等价制造「初始化失败链保持旧格式」。
{
  const db = freshDb();
  db.prepare("INSERT INTO app_meta (key, value) VALUES ('audit.hmac', ?)").run("bad-ciphertext");
  const audit = createAuditService(db);
  audit.appendAudit({ actor: "律师", action: "case.create", target: "mat_x1", detail: "借合同纠纷" });
  audit.appendAudit({ actor: "律师", action: "case.delete", target: "mat_x1" });
  const rows = audit.listAudit();
  check("A2 倒序+八字段", rows.length === 2 && Object.keys(rows[0]).length === 8
    && ["id", "ts", "actor", "action", "target", "detail", "prev_hash", "hash"].every((k) => k in rows[0]));
  const [top, first] = rows as Array<Record<string, string | null>>;
  check("A2 首行 prev=null+链式衔接", (first.prev_hash === null) && top.prev_hash === first.hash);
  check("A2 v1 无前缀 base64url", /^[A-Za-z0-9_-]+$/.test(first.hash ?? ""));
  check("A2 ts=ISO 含T含Z", typeof first.ts === "string" && first.ts.includes("T") && first.ts.endsWith("Z"));
  check("A2 缺 detail 存 null", top.detail === null);
  check("A2 无密钥链验真", audit.verifyAuditChain() === true);
}
// A3 有密钥 v3 前缀+混链验真（P3）
{
  const db = freshDb();
  db.prepare("INSERT INTO app_meta (key, value) VALUES ('audit.hmac', ?)")
    .run(Buffer.alloc(32, 7).toString("base64"));
  const audit = createAuditService(db);
  audit.appendAudit({ actor: "律师", action: "case.create", target: "c1" });
  audit.appendAudit({ actor: "律师", action: "task.add", target: "t1", detail: "举证" });
  const rows = audit.listAudit() as Array<Record<string, string | null>>;
  check("A3 v3: 前缀", rows.every((r) => (r.hash ?? "").startsWith("v3:")));
  check("A3 v3 混 v1 一链验真", audit.verifyAuditChain() === true);
}
// A4 手工 v2 行兼容（P5）：payload=同 v1 明文（含本行 prev_hash 实值）
{
  const db = freshDb();
  db.prepare("INSERT INTO app_meta (key, value) VALUES ('audit.hmac', ?)")
    .run(Buffer.alloc(32, 9).toString("base64"));
  const audit = createAuditService(db);
  audit.appendAudit({ actor: "律师", action: "case.create", target: "c1" });
  const { createHmac } = (await import("node:crypto")) as typeof import("node:crypto");
  const key = Buffer.alloc(32, 9);
  const firstHash = (audit.listAudit()[0] as { hash: string }).hash;
  const v2 = "v2:" + createHmac("sha256", key)
    .update(`v2id|律师|case.update|c1|${firstHash}`, "utf-8")
    .digest("base64url");
  db.prepare("INSERT INTO audit_log (id, ts, actor, action, target, detail, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?)")
    .run("v2id", new Date().toISOString(), "律师", "case.update", "c1", null, firstHash, v2);
  check("A4 v2 行入链验真", audit.verifyAuditChain() === true);
}
// A5 迁移幂等（P4）：坏密文期写的 v1 行×2 → 修好密文重开服务 → 迁移数=2 全 v3、verify=true、二次=0
{
  const db = freshDb();
  db.prepare("INSERT INTO app_meta (key, value) VALUES ('audit.hmac', ?)").run("bad-ciphertext");
  const a1 = createAuditService(db);
  a1.appendAudit({ actor: "律师", action: "case.create", target: "c1" });
  a1.appendAudit({ actor: "律师", action: "case.update", target: "c1", detail: "x" });
  check("A5 前置：无密钥期为 v1 行", (a1.listAudit() as Array<{ hash: string }>).every((r) => !(r.hash ?? "").startsWith("v3:")));
  db.prepare("UPDATE app_meta SET value = ? WHERE key = 'audit.hmac'")
    .run(Buffer.alloc(32, 3).toString("base64"));
  const a2 = createAuditService(db);
  const n1 = a2.migrateAuditChainToHmac();
  const rows = a2.listAudit() as Array<Record<string, string | null>>;
  check("A5 迁移数=2+全 v3+验真", n1 === 2 && rows.every((r) => (r.hash ?? "").startsWith("v3:")) && a2.verifyAuditChain() === true);
  check("A5 二次迁移=0 幂等", a2.migrateAuditChainToHmac() === 0);
}
// A6 篡改验假三途径（P6/P7/P8/P11）
{
  const db = freshDb();
  const audit = createAuditService(db);
  for (const [actor, action, target] of [["律师", "case.create", "c1"], ["律师", "task.add", "t1"], ["律师", "case.delete", "c1"]] as const) {
    audit.appendAudit({ actor, action, target });
  }
  const setCol = (col: string, v: string | null, rid: number) =>
    db.prepare(`UPDATE audit_log SET ${col} = ? WHERE rowid = ?`).run(v, rid);
  const middle = db.prepare("SELECT rowid AS rid, detail FROM audit_log ORDER BY rowid LIMIT 1 OFFSET 1").get() as { rid: number; detail: string | null };
  const original = middle.detail;
  setCol("detail", "篡改", middle.rid);
  check("A6 篡改中间行 detail→false", audit.verifyAuditChain() === false);
  setCol("detail", original, middle.rid);
  check("A6 还原→true", audit.verifyAuditChain() === true);
  setCol("prev_hash", "deadbeef", middle.rid);
  check("A6 破坏 prev_hash→false", audit.verifyAuditChain() === false);
  setCol("prev_hash", null, middle.rid); // 中间行 prev=null 仍断链（第二行 prev 应为第一行 hash）
  check("A6 中间行 prev 置空→false", audit.verifyAuditChain() === false);
  const first = db.prepare("SELECT rowid AS rid FROM audit_log ORDER BY rowid LIMIT 1").get() as { rid: number };
  db.prepare("DELETE FROM audit_log WHERE rowid = ?").run(first.rid);
  check("A6 删首行→false", audit.verifyAuditChain() === false);
}
// A7 v3 篡改 ts 验假（P11，全字段 payload 实证）
{
  const db = freshDb();
  db.prepare("INSERT INTO app_meta (key, value) VALUES ('audit.hmac', ?)").run(Buffer.alloc(32, 5).toString("base64"));
  const audit = createAuditService(db);
  audit.appendAudit({ actor: "律师", action: "case.create", target: "c1" });
  db.prepare("UPDATE audit_log SET ts = ?").run("1999-01-01T00:00:00.000Z");
  check("A7 v3 篡改 ts→false", audit.verifyAuditChain() === false);
}
// A8 limit 窗口（P9）
{
  const db = freshDb();
  const audit = createAuditService(db);
  for (let i = 0; i < 205; i++) audit.appendAudit({ actor: "律师", action: "case.update", target: "c" + i });
  check("A8 默认 200/库内 205/指定 5", audit.listAudit().length === 200
    && (db.prepare("SELECT COUNT(*) AS n FROM audit_log").get() as { n: number }).n === 205
    && audit.listAudit(5).length === 5);
}
// A9 密钥解不开：不抛、按无密钥 v1 继续、原密文保留（P12 等量 + fail-closed）
{
  const db = freshDb();
  db.prepare("INSERT INTO app_meta (key, value) VALUES ('audit.hmac', ?)").run("!!!不是密文!!!");
  let audit: ReturnType<typeof createAuditService> | null = null;
  try {
    audit = createAuditService(db);
  } catch (e) {
    check("A9 解不开不抛 fail-closed", false, String(e));
  }
  const before = (db.prepare("SELECT value FROM app_meta WHERE key='audit.hmac'").get() as { value: string }).value;
  audit!.appendAudit({ actor: "律师", action: "case.create", target: "c9" });
  const after = (db.prepare("SELECT value FROM app_meta WHERE key='audit.hmac'").get() as { value: string }).value;
  check("A9 原密文保留不轮换", before === after && before === "!!!不是密文!!!");
  check("A9 本轮 v1 可写可验", /^[A-Za-z0-9_-]+$/.test(audit!.listAudit()[0].hash ?? "") && audit!.verifyAuditChain() === true);
}
// A10 id 自补 a-<ts36>-<rand4> 形 + detail 对象 JSON 化（对拍 30）
{
  const db = freshDb();
  const audit = createAuditService(db);
  audit.appendAudit({ action: "case.create", detail: { mode: "standard" } });
  const row = audit.listAudit()[0];
  check("A10 id 形 a-<ts36>-<hex4>", /^a-[a-z0-9]+-[0-9a-f]{4}$/.test(row.id), row.id);
  check("A10 detail 对象→JSON 串", row.detail === '{"mode":"standard"}');
}

// ══════════════ B. UI 纯模型 ══════════════
const row = (over: Partial<AuditRow>): AuditRow => ({
  id: "r1", ts: "2026-10-27T09:30:00.000Z", actor: "律师", action: "case.create",
  target: "c1", detail: null, prev_hash: null, hash: "h", ...over,
});
const privacyRow = row({ id: "p1", action: "privacy.redaction", detail: PRIVACY_DETAIL });
// B1 隐私行判定+容错回退（对拍 28）
check("B1 隐私行命中", privacyDetailOf(privacyRow)?.kind === "privacy-redaction");
check("B1 非 privacy 动作→操作行", privacyDetailOf(row({ id: "o1" })) === null);
check("B1 detail 非 JSON→回退操作行", privacyDetailOf(row({ id: "o2", action: "privacy.redaction", detail: "不是json" })) === null);
check("B1 JSON 缺 kind→回退操作行", privacyDetailOf(row({ id: "o3", action: "privacy.redaction", detail: '{"a":1}' })) === null);
// B2 场景 9 类映射（对拍 48）
check("B2 场景映射", (
  scenarioKeyOf("catalog-1") === "catalog"
  && scenarioKeyOf("sum-1") === "summary" && scenarioKeyOf("summary2") === "summary"
  && scenarioKeyOf("strat-1") === "strategy" && scenarioKeyOf("risk-1") === "risk"
  && scenarioKeyOf("gen-1") === "drafting"
  && scenarioKeyOf("brief-trial-7") === "trial_brief" && scenarioKeyOf("brief-庭审-7") === "trial_brief"
  && scenarioKeyOf("brief-1") === "case_brief"
  && scenarioKeyOf("whatever") === "chat"
  && scenarioKeyOf(undefined, "case_autofill") === "autofill"
));
check("B2 场景中文名", scenarioName("drafting") === "文书起草" && scenarioName("trial_brief") === "庭审要点");
// B3 时间双试回退（对拍 15）
check("B3 ISO 解析", formatAuditTime("2026-10-27T09:30:00.000Z").includes("10/27"));
check("B3 空格变体解析", formatAuditTime("2026-10-27 09:30:00").includes("10/27"));
check("B3 垃圾原样回退", formatAuditTime("昨天下午") === "昨天下午");
check("B3 空值→—", formatAuditTime(null) === "—");
// B4 安全摘要 >24 阈值（对拍 26）
check("B4 >24 截断 12+…+8", truncateDigest("a".repeat(64)) === "a".repeat(12) + "…" + "a".repeat(8));
check("B4 =24 原样", truncateDigest("b".repeat(24)) === "b".repeat(24));
check("B4 空→null", truncateDigest(null) === null && truncateDigest("") === null);
// B5 chips≤3 / +N 类 / 0 命中（对拍 16）
check("B5 两类 chips", (() => { const h = hitChipsOf({ person_name: 3, id_card: 1 }); return h.chips.length === 2 && h.overflow === 0 && !h.zero; })());
check("B5 五类取 3+折 2", (() => { const h = hitChipsOf({ a: 5, b: 4, c: 3, d: 2, e: 1 }); return h.chips.length === 3 && h.overflow === 2 && h.chips[0].name !== undefined; })());
check("B5 零命中", hitChipsOf({}).zero === true);
check("B5 详情命中行带说明", hitLinesOf({ person_name: 2 }).length === 1 && hitLinesOf({ person_name: 2 })[0].description.length > 0);
// B6 合计 totalMatches 优先 / counts 求和（对拍 8/34）
check("B6 totalMatches 优先", totalHitsOf([privacyRow]) === 7);
check("B6 缺 totalMatches 按 counts 求和", totalHitsOf([row({ id: "p2", action: "privacy.redaction", detail: JSON.stringify({ kind: "privacy-redaction", counts: { person_name: 2, id_card: 3 } }) })]) === 5);
check("B6 操作行不计入", totalHitsOf([row({ id: "o9" })]) === 0);
// B7 详情回退链（对拍 21/53/54 状态机核心）
{
  const filtered = [row({ id: "a" }), row({ id: "b" })];
  check("B7 选中在集→该行", selectEffectiveRow(filtered, "b").id === "b");
  check("B7 选中不在集→首行（切 tab 清选自动回退）", selectEffectiveRow(filtered, "zzz").id === "a");
  check("B7 空过滤集→null（占位唯一可达路径）", selectEffectiveRow([], null) === null);
}
// B8 操作行摘要回退（对拍 17）
check("B8 空.detail→无补充说明", opsDetailSummary(row({ id: "x", detail: null })) === "无补充说明");
check("B8 长文本截断", opsDetailSummary(row({ id: "y", detail: "长".repeat(60) })).length === 49 && opsDetailSummary(row({ id: "y", detail: "长".repeat(60) })).endsWith("…"));

// ══════════════ C. 桥 RPC 真跑（隔离实例） ══════════════
// 端口 3076 与 re19_ui_walkthrough/research_synthetic 树内同端口：并行单元同时跑会互杀桥、互删同库
// bridge-3076.db（2026-10-28 实测 C8 假 FAIL 根因）。冲突时段以 RE30_SYNTH_PORT 改道空闲端口即可。
const PORT = Number(process.env.RE30_SYNTH_PORT ?? 3076);
const dbPathOf = (p: number) => join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${p}.db`);
function killPortBridge(port: number) {
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
    console.log(`[re30-synth] 清理端口 ${port} 残留桥 pid=${pid}`);
  }
}
killPortBridge(PORT);
// 跨轮防串：本用例要求 C1 空库起点，旧库（含 WAL/SHM）先清（仅本隔离端口的库文件）。
// rmSync 带重试：killPortBridge 后 Windows 句柄释放有竞速（2026-10-28 实测旧库残留致 C1/C2
// 绝对计数假 FAIL 根因），5×400ms 内清不掉才放弃。
for (const suffix of ["", "-wal", "-shm"]) {
  const p = dbPathOf(PORT) + suffix;
  for (let attempt = 0; ; attempt++) {
    try { rmSync(p, { force: true }); break; } catch { /* 被占用→稍候重试 */ }
    if (attempt >= 4) break; // 清不掉即带旧库继续（C1 会如实 FAIL，不静默假绿）
    await sleep(400);
  }
}
const bridgeLog = openSync(join(REPO_ROOT, ".local", `re30-synth-bridge-${PORT}.log`), "a");
const bridge = spawn(NODE, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
  { cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(PORT) }, stdio: ["ignore", bridgeLog, bridgeLog], detached: true });
bridge.unref();

let ch: any = null;
async function connect(port: number) {
  const ws = new WebSocket(`ws://127.0.0.1:${port}/ws`);
  ws.binaryType = "arraybuffer";
  const data: { fire: (_b: unknown) => void } = { fire: () => {} };
  ws.on("message", (buf) => data.fire(VSBuffer.wrap(new Uint8Array(buf as ArrayBuffer))));
  await new Promise((r, j) => { ws.on("open", r as never); ws.on("error", j); });
  const isocket = {
    onData: (l: never) => { data.fire = l; return { dispose: () => {} }; },
    onClose: () => ({ dispose: () => {} }),
    onEnd: () => ({ dispose: () => {} }),
    write: (b: { buffer: ArrayBuffer }) => ws.send(b.buffer),
    end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
  };
  ch = new ChannelClient(new SocketProtocol(isocket) as never).getChannel("zcode-agent");
  await ch.call("helloConversationV4", []);
}
const call = (m: string, a?: unknown) => ch.call(m, a === undefined ? [] : [a]);
async function waitProbe(port: number, timeoutMs = 40000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/server-info`, { signal: AbortSignal.timeout(2500) });
      if (r.ok) return true;
    } catch { /* 未起 */ }
    await sleep(500);
  }
  return false;
}

try {
  if (!(await waitProbe(PORT))) throw new Error("隔离桥未在超时内就绪");
  await connect(PORT);

  // C1 空库 audit.list {rows, chainOk} 同返（对拍 37/P10）
  const empty = await call("auditList");
  check("C1 空库 {rows:[], chainOk:true} 一次同返", Array.isArray(empty.rows) && empty.rows.length === 0 && empty.chainOk === true);

  // C2 渲染层 audit.append 通道（对拍 38）+一条隐私行（UI 出站脱敏渲染数据源）
  check("C2 auditAppend 返回 true", (await call("auditAppend", {
    actor: "隐私网关", action: "privacy.redaction", target: "unbound", detail: JSON.parse(PRIVACY_DETAIL),
  })) === true);
  const afterAppend = await call("auditList");
  check("C2 追加可见+链验真", afterAppend.rows.length === 1 && afterAppend.chainOk === true
    && afterAppend.rows[0].action === "privacy.redaction");

  // C3 写入面：案件/任务/日程族（对拍 31）
  const created = await call("matterCreate", { name: "合成：审计对拍案", cause: "民间借贷纠纷" });
  const caseId = created.case?.id ?? created.id;
  await call("matterUpdate", { id: caseId, name: "合成：审计对拍案（改名）" });
  const todo = await call("matterTodoAdd", { caseId, title: "合成：递交证据" });
  await call("matterTodoSetDone", { id: todo.todo?.id ?? todo.id, done: true });
  const event = await call("matterEventAdd", { date: "2026-11-02", title: "合成：开庭" });
  const rowsNow = (await call("auditList")).rows as Array<Record<string, string | null>>;
  const actions = rowsNow.map((r) => r.action);
  check("C3 case.create/update 落行", actions.includes("case.create") && actions.includes("case.update"));
  check("C3 task.add/toggle 落行", actions.includes("task.add") && actions.includes("task.toggle"));
  check("C3 schedule.create 落行", actions.includes("schedule.create"));
  const createRow = rowsNow.find((r) => r.action === "case.create")!;
  check("C3 actor=律师+target=案件id", createRow.actor === "律师" && createRow.target === caseId);
  check("C3 task.add detail=标题", rowsNow.find((r) => r.action === "task.add")!.detail === "合成：递交证据");

  // C4 读操作不虚设行（对拍 31 不虚设口径）
  const beforeRead = ((await call("auditList")).rows as unknown[]).length;
  await call("matterList");
  await call("matterTodoList", { caseId });
  const afterRead = ((await call("auditList")).rows as unknown[]).length;
  check("C4 读操作不落行", beforeRead === afterRead);

  // C5 隐身开关条件对（对拍 36/51）：on/off 各落一条。
  // 隐身开关走 ISettingService 通道（独立 channel），开第二连接完成条件对验证。
  function openChannel(port: number, name: string): Promise<any> {
    return new Promise((resolve, reject) => {
      const ws2 = new WebSocket(`ws://127.0.0.1:${port}/ws`);
      ws2.binaryType = "arraybuffer";
      const data2: { fire: (_b: unknown) => void } = { fire: () => {} };
      ws2.on("message", (buf) => data2.fire(VSBuffer.wrap(new Uint8Array(buf as ArrayBuffer))));
      ws2.on("open", () => {
        const isocket2 = {
          onData: (l: never) => { data2.fire = l; return { dispose: () => {} }; },
          onClose: () => ({ dispose: () => {} }),
          onEnd: () => ({ dispose: () => {} }),
          write: (b: { buffer: ArrayBuffer }) => ws2.send(b.buffer),
          end: () => ws2.close(), drain: async () => {}, dispose: () => ws2.close(),
        };
        resolve(new ChannelClient(new SocketProtocol(isocket2) as never).getChannel(name));
      });
      ws2.on("error", reject);
    });
  }
  const settingCh = await openChannel(PORT, "setting");
  await settingCh.call("update", [{ stealthMode: { enabled: true } }]);
  await settingCh.call("update", [{ stealthMode: { enabled: false } }]);
  const rowsStealth = (await call("auditList")).rows as Array<Record<string, string | null>>;
  const stealthActions = rowsStealth.filter((r) => (r.action ?? "").startsWith("stealth.")).map((r) => r.action);
  check("C5 stealth.on/off 各一条", stealthActions.includes("stealth.on") && stealthActions.includes("stealth.off"));
  check("C5 开关 actor=律师 target=settings", rowsStealth.filter((r) => (r.action ?? "").startsWith("stealth."))
    .every((r) => r.actor === "律师" && r.target === "settings"));

  // C6 doc.export（对拍 31 文档域；draftExportWord 纯本地不触模型）
  await call("draftExportWord", { markdown: "# 合成：审计对拍文书\n\n正文。", templateSource: "builtin" });
  const rowsDoc = (await call("auditList")).rows as Array<Record<string, string | null>>;
  check("C6 doc.export 落行", rowsDoc.some((r) => r.action === "doc.export" && (r.detail ?? "").includes("standard")));

  // C6b 文档域补账（对拍 31·写入面映射缺口收口）：自定义模板删除=doc.delete 第二调用点，
  // target=custom-* 与历史面 dh-* 自区分；上传合成 .md（纯本地白名单后缀，学习异步失败不炸）。
  const upTpl = await call("draftUploadTemplate", {
    fileName: "合成：审计对拍模板.md",
    base64: Buffer.from("# 合成模板（对拍用）\n\n【原告】{{原告}}\n【被告】{{被告}}", "utf-8").toString("base64"),
  });
  const tplId = String(upTpl?.template?.id ?? "");
  check("C6b 合成模板上传 custom-*", tplId.startsWith("custom-"), tplId);
  await call("draftDeleteTemplate", { templateId: tplId });
  const rowsTpl = (await call("auditList")).rows as Array<Record<string, string | null>>;
  const delTpl = rowsTpl.find((r) => r.action === "doc.delete" && r.target === tplId) ?? null;
  check("C6b doc.delete（模板面）落行+自描述 detail", Boolean(delTpl) && (delTpl?.detail ?? "").includes("模板"));

  // C9 材料域写入面（对拍 31·RE-30 §3.5 映射行 file.upload/parse 接线收口；RE-6 HTTP 面真跑）：
  // 上传合成文本 → file.upload+file.parse(ready) 落行且原文不进审计（对拍 33 红线）；损坏 docx →
  // file.parse(failed) 落行（拒绝/失败路径入账，对拍 35 同族语义）；不支持格式 → 400 无行
  // （业务不成功不入账）。file.delete：材料域无删除功能面，不虚设（对拍 31 口径）。
  const longText = "合成材料：甲方于2024年5月10日与乙方签订钢材买卖合同，约定货款人民币128,000元，" +
    "签订后十日内支付预付款30%，逾期付款按日计付违约金。双方约定履行地为上海市浦东新区，争议提交仲裁解决。";
  const matReady = await (await fetch(`http://127.0.0.1:${PORT}/api/cases/materials/upload`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ caseId, filename: "合成：审计材料.txt", title: "合成：审计材料", text: longText }),
  })).json() as { items: Array<{ id?: string; status?: string }> };
  const readyMat = matReady.items?.[0];
  check("C9 材料 ready 上传成功", readyMat?.status === "ready", JSON.stringify(matReady).slice(0, 120));
  const rowsMat = (await call("auditList")).rows as Array<Record<string, string | null>>;
  const upRow = rowsMat.find((r) => r.action === "file.upload" && r.target === readyMat?.id) ?? null;
  check("C9 file.upload 落行（detail 摘要，原文不进审计）",
    Boolean(upRow) && (upRow!.detail ?? "").includes("合成：审计材料") && !(upRow!.detail ?? "").includes("钢材买卖合同"));
  const parseRow = rowsMat.find((r) => r.action === "file.parse" && r.target === readyMat?.id) ?? null;
  check("C9 file.parse(ready) 落行", Boolean(parseRow) && (parseRow!.detail ?? "").includes("ready"),
    JSON.stringify(parseRow ?? {}).slice(0, 140));
  const matFail = await (await fetch(`http://127.0.0.1:${PORT}/api/cases/materials/upload`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ caseId, filename: "合成：损坏材料.docx", dataBase64: Buffer.from("这不是docx内容", "utf-8").toString("base64") }),
  })).json() as { items: Array<{ id?: string; status?: string }> };
  const failMat = matFail.items?.[0];
  check("C9 损坏 docx 终态 failed", failMat?.status === "failed");
  const rowsFail = (await call("auditList")).rows as Array<Record<string, string | null>>;
  const failParse = rowsFail.find((r) => r.action === "file.parse" && r.target === failMat?.id) ?? null;
  check("C9 file.parse(failed) 落行（失败路径入账）", Boolean(failParse) && (failParse!.detail ?? "").includes("failed"));
  const beforeReject = rowsFail.length;
  await fetch(`http://127.0.0.1:${PORT}/api/cases/materials/upload`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ caseId, filename: "合成：拒绝用例.exe", dataBase64: Buffer.from("MZ", "utf-8").toString("base64") }),
  });
  const afterReject = ((await call("auditList")).rows as unknown[]).length;
  check("C9 不支持格式拒绝无行（业务不成功不入账）", beforeReject === afterReject);

  // C7 删除族落行 + 链全程验真（对拍 40/43）
  await call("matterTodoDelete", { id: todo.todo?.id ?? todo.id });
  await call("matterEventDelete", { id: event.event?.id ?? event.id });
  await call("matterDelete", { id: caseId });
  const finalRows = (await call("auditList")).rows as Array<Record<string, string | null>>;
  check("C7 task.remove/schedule.delete/case.delete 落行",
    finalRows.some((r) => r.action === "task.remove") && finalRows.some((r) => r.action === "schedule.delete")
    && finalRows.some((r) => r.action === "case.delete"));
  check("C7 全程写入后链验真", (await call("auditList")).chainOk === true);

  // C8 restart 幂等：杀桥重拉（同库）→ chainOk true + 行数不丢 + 无迁移日志刷屏
  const countBeforeRestart = finalRows.length;
  spawnSync("taskkill", ["/PID", String(bridge.pid), "/F", "/T"], { timeout: 15000 });
  await sleep(1500);
  const bridge2 = spawn(NODE, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(PORT) }, stdio: ["ignore", bridgeLog, bridgeLog], detached: true });
  bridge2.unref();
  if (!(await waitProbe(PORT))) throw new Error("重启桥未就绪");
  await connect(PORT);
  const afterRestart = await call("auditList");
  check("C8 重启后行数不丢+链验真", afterRestart.rows.length === countBeforeRestart && afterRestart.chainOk === true,
    `before=${countBeforeRestart} after=${afterRestart.rows.length} chainOk=${afterRestart.chainOk}`);
} catch (e) {
  check("C 桥 RPC 链路", false, String((e as Error)?.message ?? e));
}

// ══════════════ D. 条件真跑段（对拍 31/32 补齐验证）：oc28 可用才跑起草/定稿真链；
// 不可用如实 SKIP（不计 FAIL，不假绿——写入面逻辑行随 D 段在标准环境验证）══════════════
try {
  const { loadCredentials } = await import("../../packages/juscite-runtime-adapters/opencode/src/opencodeAdapter.mjs");
  let oc28Up = false;
  let baseUrl = "";
  try {
    const cred = (loadCredentials as () => { baseUrl: string; headers: Record<string, string> })();
    baseUrl = cred.baseUrl;
    const r = await fetch(cred.baseUrl + "/api/info", { headers: cred.headers, signal: AbortSignal.timeout(3000) });
    oc28Up = r.ok;
  } catch (e) {
    check("D0 oc28 条件真跑段", true, "SKIP oc28 不可达（" + String((e as Error)?.message ?? e).slice(0, 80) + "）");
  }
  if (oc28Up) {
    // 合成工作区+材料（写 D:\mock\re30-synth-ws，全部合成虚构文本）
    const wsDir = "D:\\mock\\re30-synth-ws";
    mkdirSync(join(wsDir, "materials"), { recursive: true });
    const matName = "合成：借贷事实材料.txt";
    writeFileSync(join(wsDir, "materials", matName),
      "合成材料：2024 年 3 月 1 日，张三借给李四人民币伍万元整，约定 2025 年 3 月 1 日归还，月利率百分之壹。李四出具借条一张。",
      "utf-8");
    // D1 起草完成（真模型，200s 时限）→ doc.ai.create（AI 文书保存=落历史）
    const gen = await call("draftGenerate", {
      workspacePath: wsDir, templateSource: "builtin", hiddenDocumentType: "complaint",
      materialNames: [matName],
      pastedCase: "张三诉李四民间借贷纠纷：本金 50000 元，月利率 1%，到期未还，多次催收无果。",
      fieldValues: { 原告: "张三", 被告: "李四" },
    });
    const dl1 = Date.now() + 200000;
    let st: any = null;
    while (Date.now() < dl1) {
      st = await call("draftStatus", { draftId: gen.draftId });
      if (st?.status !== "running") break;
      await sleep(2000);
    }
    check("D1 起草完成（done|partial）", st && (st.status === "done" || st.status === "partial"),
      "status=" + (st?.status ?? "timeout") + (st?.error ? " err=" + String(st.error).slice(0, 80) : ""));
    const rowsDraft = (await call("auditList")).rows as Array<Record<string, string | null>>;
    const createAi = rowsDraft.find((r) => r.action === "doc.ai.create") ?? null;
    check("D2 doc.ai.create 落行（target=dh-*+detail 摘要，正文不进审计）",
      Boolean(createAi) && String(createAi!.target ?? "").startsWith("dh-")
      && (createAi!.detail ?? "").includes("templateName") && !(createAi!.detail ?? "").includes("张三借给"),
      JSON.stringify(createAi ?? {}).slice(0, 180));
    // D3 改稿→逐条接受→定稿落盘 → doc.ai.apply（AI 文书应用=定稿采纳）
    const revResp = await call("redlineRevise", { workspacePath: wsDir, materialName: matName, instruction: "合成：核对金额与日期表述，修正错别字" });
    const revisionId = String(revResp?.revisionId ?? "");
    const dl2 = Date.now() + 200000;
    let rstatus = "";
    while (Date.now() < dl2) {
      const one = await call("redlineGet", { workspacePath: wsDir, revisionId });
      rstatus = String(one?.revision?.status ?? one?.status ?? "");
      if (rstatus === "ready" || rstatus === "failed") break;
      await sleep(2000);
    }
    check("D3 改稿 ready", rstatus === "ready", "status=" + rstatus);
    if (rstatus === "ready") {
      const detail = await call("redlineGet", { workspacePath: wsDir, revisionId });
      const items: Array<{ itemIdx?: number; decision?: string }> = detail?.items ?? [];
      for (let i = 0; i < items.length; i++) {
        if ((items[i].decision ?? "pending") === "pending") {
          await call("redlineDecide", { workspacePath: wsDir, revisionId, itemIdx: items[i].itemIdx ?? i, decision: "accepted" });
        }
      }
      await call("redlineFinalize", { workspacePath: wsDir, revisionId });
      const rowsApply = (await call("auditList")).rows as Array<Record<string, string | null>>;
      const apply = rowsApply.find((r) => r.action === "doc.ai.apply") ?? null;
      check("D4 doc.ai.apply 落行（target=revisionId+detail.finalPath）",
        Boolean(apply) && apply!.target === revisionId && (apply!.detail ?? "").includes("finalPath"),
        JSON.stringify(apply ?? {}).slice(0, 180));
    } else {
      check("D4 doc.ai.apply 落行", false, "改稿未 ready（" + rstatus + "），无法定稿");
    }
    check("D5 真跑段全程链验真", (await call("auditList")).chainOk === true);
  }
} catch (e) {
  check("D 条件真跑段", false, String((e as Error)?.message ?? e).slice(0, 160));
}

const failed = results.filter((r) => !r.ok);
for (const f of failed) console.log(`[re30-synth] FAIL -> ${f.name}`);
console.log(failed.length === 0 ? `RE30_SYNTH_PASS (${results.length} checks)` : `RE30_SYNTH_FAIL (${failed.length}/${results.length} failed)`);
process.exit(failed.length === 0 ? 0 : 1);
