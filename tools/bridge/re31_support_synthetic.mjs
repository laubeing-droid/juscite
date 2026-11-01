#!/usr/bin/env node
// 功能 #31 支持通道合成自测（RE-31 §4 对拍；ci_gate fast 随行步）。
// 全合成材料：工单/诊断落盘与 ops-config 全部临时目录（os.tmpdir()）；ops 平台=本进程内 stub
// http 服务（127.0.0.1 随机口、合成数据、跑完即关）；零 %APPDATA% 触碰——唯隐身闸一例经
// %APPDATA%\Juscite\config\mock\setting.json 备份-翻转-还原（红线分区内的既有设置文件，收场还原原字节）。
// 桥接线（真子进程径）：自拉 bridge_host.mjs 独立实例（随机空闲口+BRIDGE_OC28_SSE=0 隔离 oc28），
// RPC 经 ChannelClient("zcode-agent") 直调（persist_probe.mts 已验证手法），收场杀自家实例
// （杀前核验命令行含 bridge_host.mjs，同 ci_gate 纪律）并清掉自己的 bridge-<port>.db*。
// 纯 Node 零依赖；单命令 exit 0/1，末行 RE31_SUPPORT_SYNTH_PASS 可判。
// 用法：node tools/bridge/re31_support_synthetic.mjs
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import {
  appVersionOf, buildSupportDiagnostics, buildTicketMarkdown, generateTicketKey,
  listLocalTickets, opsConfigFilePath, parseTicketMarkdown, resolveOpsBase,
  supportRootDir, timestampCompact, writeTicketFile,
} from "./support_service.mjs";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url)); // tools/bridge/ → 仓库根
let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[re31-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[re31-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }
const jsonEq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const scratch = mkdtempSync(join(tmpdir(), "juscite-re31-synth-"));

// ── 模块级：C27 ops base 三层解析（env > 文件 > 无默认远端；两来源剥尾斜杠）──
{
  const cfg = join(scratch, "ops-config.json");
  const withEnv = (v) => ({ JUSCITE_SUPPORT_OPS_API: v });
  // 1：env 优先 + 剥尾斜杠
  const r1 = resolveOpsBase({ env: withEnv("http://env.example///"), configFile: join(scratch, "absent.json") });
  if (r1.opsApi === "http://env.example" && r1.source === "env") ok(1, "C27 env 优先+剥尾斜杠");
  else fail(1, "env 解析", JSON.stringify(r1));
  // 2：无 env 读文件 + 剥尾斜杠
  writeFileSync(cfg, JSON.stringify({ opsApi: "https://file.example/" }), "utf-8");
  const r2 = resolveOpsBase({ env: {}, configFile: cfg });
  if (r2.opsApi === "https://file.example" && r2.source === "file") ok(2, "C27 文件层+剥尾斜杠");
  else fail(2, "文件层解析", JSON.stringify(r2));
  // 3：env 空串跳过 → 文件；坏 JSON 跳过 → 无默认远端（降级）
  const r3 = resolveOpsBase({ env: withEnv("   "), configFile: cfg });
  if (r3.opsApi === "https://file.example" && r3.source === "file") ok(3, "C27 env 空值跳过落文件层");
  else fail(3, "env 空值", JSON.stringify(r3));
  writeFileSync(cfg, "{oops", "utf-8");
  const r4 = resolveOpsBase({ env: {}, configFile: cfg });
  if (r4.opsApi === null && r4.source === "none") ok(4, "C27 坏 JSON→无默认远端（降级，不抛）");
  else fail(4, "坏 JSON 降级", JSON.stringify(r4));
  const r5 = resolveOpsBase({ env: {}, configFile: join(scratch, "absent.json") });
  if (r5.opsApi === null && r5.source === "none") ok(5, "C27 无任何配置=降级形态（无默认远端）");
  else fail(5, "无配置", JSON.stringify(r5));
}

// ── 模块级：A6 密钥生成 + E31 时间戳形 ──
{
  const k1 = generateTicketKey(), k2 = generateTicketKey();
  if (/^[A-Za-z0-9_-]{32}$/.test(k1) && k1 !== k2) ok(6, "A6 ticket_key=randomBytes(24) base64url 32 字符且随机");
  else fail(6, "密钥形", k1);
  if (/^\d{8}T\d{9}Z$/.test(timestampCompact(new Date(Date.UTC(2026, 9, 27, 8, 30, 12, 456))))) ok(7, "E31 UTC 毫秒压缩时间戳形");
  else fail(7, "时间戳形", timestampCompact(new Date(Date.UTC(2026, 9, 27, 8, 30, 12, 456))));
}

// ── 模块级：§3.5 Markdown 模板字段级定义 + 机器可解析回读 ──
{
  const md = buildTicketMarkdown({
    requester: "走查律师", ticketKey: "k-123", subject: "导出失败", content: "第一步就报错",
    createdAtIso: "2026-10-28T00:00:00.000Z", appVersion: "0.1.0", platform: "win32", arch: "x64",
  });
  const parsed = parseTicketMarkdown(md);
  const fieldsOk = parsed.requester === "走查律师" && parsed.ticketKey === "k-123" && parsed.subject === "导出失败"
    && parsed.createdAt === "2026-10-28T00:00:00.000Z" && parsed.appVersion === "0.1.0"
    && parsed.platform === "win32" && parsed.arch === "x64";
  const bodyOk = md.includes("# 导出失败") && md.includes("第一步就报错");
  const boundaryOk = !md.includes("license") && !md.includes("fingerprint"); // §3.5 信息边界（无许可/指纹字段）
  if (fieldsOk && bodyOk && boundaryOk) ok(8, "§3.5 头部元数据 7 字段机器可解析+正文原文+信息边界");
  else fail(8, "Markdown 模板", JSON.stringify({ parsed, bodyOk, boundaryOk }));
  const inj = buildTicketMarkdown({ requester: "a\nb", ticketKey: "k", subject: "s\nt", content: "c", createdAtIso: "x", appVersion: "v", platform: "p", arch: "a" });
  const injOk = !/\n[^\n]*^b /m.test(inj.split("-->")[0]) && parseTicketMarkdown(inj).requester === "a b" && parseTicketMarkdown(inj).subject === "s t";
  if (injOk) ok(9, "§3.5 元数据值单行化（换行注入不断行破坏解析）");
  else fail(9, "单行化", JSON.stringify(parseTicketMarkdown(inj)));
  if (parseTicketMarkdown("没有元数据的文件").subject === null) ok(10, "E38 容错：无元数据文件解析不出不抛");
  else fail(10, "容错解析");
}

// ── 模块级：E31/E32/E33 落盘边角 ──
{
  const dir = join(scratch, "support-e31");
  const now = new Date(Date.UTC(2026, 9, 27, 8, 30, 12, 456));
  const f1 = writeTicketFile({ rootDir: dir, markdown: "第一份", now });
  if (f1.fileName === "ticket-20261027T083012456Z.md" && existsSync(f1.path)) ok(11, "E31 目录递归建+UTC 毫秒文件名");
  else fail(11, "E31", JSON.stringify(f1));
  const f2 = writeTicketFile({ rootDir: dir, markdown: "第二份", now }); // 同毫秒撞名
  const firstIntact = readFileSync(f1.path, "utf-8") === "第一份";
  if (f2.fileName === "ticket-20261027T083012456Z-2.md" && firstIntact) ok(12, "E32 撞名序号后缀不覆盖既有文件");
  else fail(12, "E32", JSON.stringify({ f2: f2.fileName, firstIntact }));
  const blocker = join(scratch, "blocker-file");
  writeFileSync(blocker, "x", "utf-8");
  try {
    writeTicketFile({ rootDir: join(blocker, "sub"), markdown: "y", now: new Date(Date.UTC(2026, 9, 27, 8, 30, 13, 0)) });
    fail(13, "E33 应抛未抛");
  } catch (e) {
    const msgText = String(e?.message ?? e);
    if (msgText.includes("工单落盘失败") && msgText.includes(join(blocker, "sub"))) ok(13, "E33 落盘失败错误含目标完整路径");
    else fail(13, "E33 错误形", msgText);
  }
}

// ── 模块级：E38 本地枚举（倒序+主题解析+目录缺失/失败提示）──
{
  const empty = listLocalTickets({ rootDir: join(scratch, "no-such-dir") });
  if (empty.rows.length === 0 && empty.error === "support_dir_absent") ok(14, "E38 目录不存在=空列表+提示");
  else fail(14, "E38 目录缺失", JSON.stringify(empty));
  const dir = join(scratch, "support-e38");
  const mk = (name, subject) => writeTicketFile({
    rootDir: dir,
    markdown: buildTicketMarkdown({ requester: "r", ticketKey: "k", subject, content: "", createdAtIso: "2026-01-01T00:00:00.000Z", appVersion: "v", platform: "p", arch: "a" }),
    now: { 1: new Date(Date.UTC(2026, 0, 1, 0, 0, 1, 0)), 2: new Date(Date.UTC(2026, 0, 1, 0, 0, 2, 0)), 3: new Date(Date.UTC(2026, 0, 1, 0, 0, 3, 0)) }[name],
  });
  mk(1, "最早"); mk(2, "中间"); mk(3, "最新");
  writeFileSync(join(dir, "readme.md"), "不是工单", "utf-8"); // 非 ticket-* 文件不入列
  const list = listLocalTickets({ rootDir: dir });
  const orderOk = list.rows.length === 3 && list.rows[0].subject === "最新" && list.rows[2].subject === "最早";
  if (orderOk && list.error === null) ok(15, "E38 枚举倒序+主题解析+杂文件忽略");
  else fail(15, "E38 枚举", JSON.stringify(list));
  const bad = listLocalTickets({ rootDir: join(dir, "readme.md") }); // 枚举失败（路径是文件）
  if (bad.rows.length === 0 && bad.error) ok(16, "E38 枚举失败给提示");
  else fail(16, "E38 失败提示", JSON.stringify(bad));
}

// ── 模块级：B15-B20 诊断包 9 键固定键序 + B18 降级 + B19 只嵌 state/reason ──
{
  const db = new DatabaseSync(":memory:");
  db.exec("CREATE TABLE case_board_cases(id TEXT); CREATE TABLE document_chunks(id TEXT); CREATE TABLE demo_evidence(id TEXT); CREATE TABLE case_board_events(id TEXT); CREATE TABLE audit_log(id TEXT)");
  db.exec("INSERT INTO case_board_cases VALUES ('a'),('b'); INSERT INTO audit_log VALUES ('x')");
  const lic = { state: "valid", tier: "advanced", reason: "ok", modules: {} };
  const d = buildSupportDiagnostics({ appVersion: "0.1.0-test", license: lic, db, now: new Date("2026-10-28T00:00:00.000Z") });
  const keys = Object.keys(d.payload);
  const wantKeys = ["app_version", "platform", "arch", "generated_at", "license_state", "license_reason", "agent_status", "table_counts", "note"];
  const countsOk = d.payload.table_counts.cases === 2 && d.payload.table_counts.audit === 1
    && d.payload.table_counts.documents === 0 && d.payload.table_counts.evidence === 0 && d.payload.table_counts.schedules === 0;
  const b19Ok = !("licensee" in d.payload) && !("expiresAt" in d.payload) && !("features" in d.payload);
  if (jsonEq(keys, wantKeys) && d.payload.app_version === "0.1.0-test" && d.payload.license_state === "valid"
    && d.payload.license_reason === "ok" && countsOk && b19Ok && d.payload.platform === process.platform && d.payload.arch === process.arch) {
    ok(17, "B15 9 键固定键序+B17 五面计数+B19 只嵌 state/reason+真实 platform/arch");
  } else fail(17, "诊断包", JSON.stringify(d.payload));
  const dNoDb = buildSupportDiagnostics({ license: { state: "base", reason: "no_license_file" }, db: null });
  if (jsonEq(dNoDb.payload.table_counts, {}) && dNoDb.payload.license_state === "base") ok(18, "B18 db 缺失→table_counts={} 静默降级");
  else fail(18, "B18", JSON.stringify(dNoDb.payload));
  const throwDb = { prepare: () => { throw new Error("boom"); } };
  const dThrow = buildSupportDiagnostics({ license: lic, db: throwDb });
  if (jsonEq(dThrow.payload.table_counts, {})) ok(19, "B18 查询抛错→{} 静默降级（包照常出）");
  else fail(19, "B18 抛错", JSON.stringify(dThrow.payload));
  const saved = process.env.JUSCITE_APP_VERSION;
  process.env.JUSCITE_APP_VERSION = "9.9.9-env";
  const envVer = appVersionOf();
  if (saved === undefined) delete process.env.JUSCITE_APP_VERSION; else process.env.JUSCITE_APP_VERSION = saved;
  if (envVer === "9.9.9-env") ok(20, "B16 不复刻：app_version 优先取 JUSCITE_APP_VERSION（桌面端传 app.getVersion()）");
  else fail(20, "app_version", envVer);
}

// ── 桥接线（真子进程径 + 本进程 stub ops 平台 + WS RPC 直调）──
function pickFreePort() {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const used = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING/g)) used.add(Number(m[1]));
  let p = 32400 + Math.floor(Math.random() * 1500);
  while (used.has(p)) p += 1;
  return p;
}
function commandLineLooksLikeBridge(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  return String(r.stdout ?? "").includes("bridge_host.mjs");
}
const storeDir = join(homedir(), "AppData", "Roaming", "Juscite", "bridge");
function cleanupBridgeFiles(port) {
  for (const suffix of [".db", ".db-wal", ".db-shm"]) {
    try { rmSync(join(storeDir, `bridge-${port}${suffix}`), { force: true }); } catch { /* 尽力而为 */ }
  }
}
async function killOwnBridge(pid, port) {
  if (!commandLineLooksLikeBridge(pid)) throw new Error(`pid=${pid} 命令行不含 bridge_host.mjs，宁停不误杀`);
  spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
    if (!new RegExp(`\\sTCP\\s+\\S*:${port}\\s+\\S+\\s+LISTENING`).test(String(r.stdout ?? ""))) break;
    await new Promise((res) => setTimeout(res, 500));
  }
  cleanupBridgeFiles(port);
}
async function probeServerInfo(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/server-info`, { signal: AbortSignal.timeout(2500) });
      if (r.ok) return JSON.parse(await r.text());
    } catch { /* 未起，重试 */ }
    await new Promise((res) => setTimeout(res, 500));
  }
  return null;
}
function connectRpc(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";
    const data = { fire: (_b) => {} };
    ws.on("message", (buf) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
    ws.on("error", (e) => reject(e));
    ws.on("open", () => {
      const isocket = {
        onData: (l) => { data.fire = l; return { dispose: () => {} }; },
        onClose: () => ({ dispose: () => {} }),
        onEnd: () => ({ dispose: () => {} }),
        write: (b) => ws.send(b.buffer),
        end: () => ws.close(),
        drain: async () => {},
        dispose: () => ws.close(),
      };
      const client = new ChannelClient(new SocketProtocol(isocket));
      const ch = client.getChannel("zcode-agent");
      resolve((m, a) => ch.call(m, a === undefined ? [] : [a]));
    });
  });
}
// stub ops 平台：记录请求（method/url/headers/body），响应剧本可换
function startOpsStub() {
  const hits = [];
  const script = { ticketBody: { ticket_key: "srv-echo-key-0123456789abcdef" }, listBody: [{ status: "open", subject: "合成工单一", reply: "已收到" }], diagStatus: 200 };
  const server = createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => { raw += c; });
    req.on("end", () => {
      hits.push({ method: req.method, url: req.url, ticketKeyHeader: req.headers["x-ticket-key"] ?? null, body: raw ? JSON.parse(raw) : null });
      if (req.url === "/support/tickets" && req.method === "POST") {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify(script.ticketBody));
      } else if (req.url?.startsWith("/support/tickets") && req.method === "GET") {
        res.writeHead(200, { "content-type": "application/json" });
        res.end(JSON.stringify(script.listBody));
      } else if (req.url === "/support/diagnostics" && req.method === "POST") {
        res.writeHead(script.diagStatus, { "content-type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
      } else {
        res.writeHead(404); res.end();
      }
    });
  });
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => resolve({ server, hits, script, port: server.address().port }));
  });
}
const licenseFile = join(scratch, "license.json");
writeFileSync(licenseFile, JSON.stringify({
  schema: "juscite-license/1", licenseId: "re31-synth", issuedAt: new Date(Date.now() - 86_400_000).toISOString(), modules: { H1: true },
}), "utf-8");

const ops = await startOpsStub();
const opsBase = `http://127.0.0.1:${ops.port}`;
const supportRoot1 = join(scratch, "wire-remote-support"); // 有配置实例的落盘根（不应被用到）
const supportRoot2 = join(scratch, "wire-local-support"); // 降级实例的落盘根
const settingPath = join(homedir(), "AppData", "Roaming", "Juscite", "config", "mock", "setting.json");
const settingBackup = existsSync(settingPath) ? readFileSync(settingPath) : null;

async function spawnBridge(envExtra) {
  const port = pickFreePort();
  const env = { ...process.env, BRIDGE_PORT: String(port), BRIDGE_OC28_SSE: "0", ...envExtra };
  const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: "ignore", detached: true });
  // 2026-10-31 清障二轮：60s→300s（re26 走查同款窗口放宽先例）——共享工位并发施工期桥冷载实测 >90s，
  // 环境性停顿非产品缺陷；断言面零改动，仅等桥起来。
  const info = await probeServerInfo(port, 300000);
  if (!info) { await killOwnBridge(child.pid, port).catch(() => {}); throw new Error(`:${port} 桥 300s 不可探`); }
  const call = await connectRpc(`ws://127.0.0.1:${port}/ws`);
  return { child, port, call, info };
}

let remote = null, local = null;
try {
  // 实例一：有配置（env opsApi → stub 平台）
  remote = await spawnBridge({
    JUSCITE_SUPPORT_OPS_API: `${opsBase}/`, // 故意带尾斜杠：C27 剥洗后必须仍命中 stub
    BRIDGE_SUPPORT_ROOT: supportRoot1,
    BRIDGE_LICENSE_FILE: licenseFile,
    JUSCITE_APP_VERSION: "0.1.0-synth",
  });
  // 21：supportInfoGet（C27 env 层经剥尾斜杠命中 stub 域）
  const info1 = await remote.call("supportInfoGet");
  if (info1.opsApi === opsBase && info1.source === "env" && info1.appVersion === "0.1.0-synth" && info1.supportDir === supportRoot1) {
    ok(21, "supportInfoGet：env 层剥尾斜杠+app_version 真版本通道+supportDir 回带");
  } else fail(21, "supportInfoGet", JSON.stringify(info1));

  // 22：remote create → POST body 四字段（A6）+ 密钥缺省桥侧生成 + 回执回带
  const c1 = await remote.call("supportTicketCreate", { requester: "走查律师", subject: "  导出失败  ", content: "第一步报错" });
  const hit1 = ops.hits.find((h) => h.method === "POST" && h.url === "/support/tickets");
  const bodyOk = hit1 && hit1.body.requester === "走查律师" && hit1.body.subject === "导出失败"
    && hit1.body.content === "第一步报错" && /^[A-Za-z0-9_-]{32}$/.test(hit1.body.ticket_key ?? "");
  if (c1.mode === "remote" && c1.ok === true && c1.responseTicketKey === ops.script.ticketBody.ticket_key && c1.ticketKey === hit1?.body?.ticket_key && bodyOk) {
    ok(22, "A6/A7 remote create：POST 四字段 body（subject 桥侧 trim）+ticket_key 缺省生成+服务端回执回带");
  } else fail(22, "remote create", JSON.stringify({ c1, hit: hit1 }));

  // 23：remote create 携本地存键（A6 取键不重生成）
  await remote.call("supportTicketCreate", { requester: "走查律师", subject: "带键工单", content: "", ticketKey: "existing-key-0123456789abcdef00" });
  const hit2 = ops.hits.filter((h) => h.method === "POST" && h.url === "/support/tickets").at(-1);
  if (hit2?.body?.ticket_key === "existing-key-0123456789abcdef00" && hit2.body.content === "") ok(23, "A6 携存键透传+空 content 补空串");
  else fail(23, "携键 create", JSON.stringify(hit2));

  // 24：A12 校验——缺主题抛错
  try {
    await remote.call("supportTicketCreate", { requester: "走查律师", subject: "   " });
    fail(24, "A12 应抛未抛");
  } catch (e) {
    const t = String((e)?.message ?? e);
    if (t.includes("主题") || t.includes("称呼")) ok(24, "A12 create 缺 requester/subject 同构校验抛错");
    else fail(24, "A12 错误文案", t);
  }

  // 25：A10 remote list → GET ?requester=<enc> + x-ticket-key 头 + rows 透传
  const l1 = await remote.call("supportTicketList", { requester: "张 三", ticketKey: "tk-1" });
  const getHit = ops.hits.find((h) => h.method === "GET" && h.url === `/support/tickets?requester=${encodeURIComponent("张 三")}`);
  if (l1.mode === "remote" && Array.isArray(l1.rows) && l1.rows[0]?.subject === "合成工单一" && getHit && getHit.ticketKeyHeader === "tk-1") {
    ok(25, "A10 remote list：GET 查询串 encodeURIComponent+x-ticket-key 头+rows 透传");
  } else fail(25, "remote list", JSON.stringify({ l1, getHit }));

  // 26：A10 校验——缺 ticketKey 抛错
  try {
    await remote.call("supportTicketList", { requester: "走查律师", ticketKey: "" });
    fail(26, "A10 应抛未抛");
  } catch (e) {
    const t = String(e?.message ?? e);
    if (t.includes("密钥") || t.includes("称呼")) ok(26, "A10 list 缺 ticket_key 同构校验抛错");
    else fail(26, "A10 错误文案", t);
  }

  // 27：诊断组包（桥库真表计数+许可文件判定表翻转）
  const d1 = await remote.call("supportDiagnosticsBuild");
  const keys = Object.keys(d1.payload ?? {});
  const wantKeys = ["app_version", "platform", "arch", "generated_at", "license_state", "license_reason", "agent_status", "table_counts", "note"];
  const counts = d1.payload?.table_counts ?? {};
  if (jsonEq(keys, wantKeys) && d1.payload.license_state === "valid" && d1.payload.license_reason === "ok"
    && ["cases", "documents", "evidence", "schedules", "audit"].every((k) => typeof counts[k] === "number")
    && !("licensee" in d1.payload) && !("features" in d1.payload)) {
    ok(27, "B15/B17/B19 桥面组包：9 键序+许可判定表翻转+五面计数（无 licensee/features）");
  } else fail(27, "桥面组包", JSON.stringify(d1.payload));

  // 28：B24 上传 → POST {requester|'unknown', payload}
  await remote.call("supportDiagnosticsUpload", { requester: "走查律师", payload: d1.json });
  const diagHit = ops.hits.find((h) => h.method === "POST" && h.url === "/support/diagnostics");
  if (diagHit?.body?.requester === "走查律师" && diagHit.body.payload === d1.json) ok(28, "B24 上传 body 形状等量");
  else fail(28, "上传", JSON.stringify(diagHit));
  // 29：B23 空 payload 抛错；B24 'unknown' 兜底
  try {
    await remote.call("supportDiagnosticsUpload", { payload: "  " });
    fail(29, "B23 应抛未抛");
  } catch (e) {
    if (String(e?.message ?? e).includes("空")) ok(29, "B23 空 payload 同构校验抛错");
    else fail(29, "B23 错误文案", String(e?.message ?? e));
  }
  await remote.call("supportDiagnosticsUpload", { payload: "{}" });
  const diagHit2 = ops.hits.filter((h) => h.method === "POST" && h.url === "/support/diagnostics").at(-1);
  if (diagHit2?.body?.requester === "unknown") ok(30, "B24 requester 缺省回 unknown");
  else fail(30, "unknown 兜底", JSON.stringify(diagHit2));

  // 隐身闸（§3.2 出站闸）：备份-翻转-还原 %APPDATA%\Juscite\config\mock\setting.json（桥每请求热读）
  try {
    mkdirForSetting();
    writeFileSync(settingPath, JSON.stringify({ stealthMode: { enabled: true } }), "utf-8");
    let stealthThrew = false;
    try { await remote.call("supportTicketCreate", { requester: "走查律师", subject: "隐身期工单" }); } catch { stealthThrew = true; }
    let diagThrew = false;
    try { await remote.call("supportDiagnosticsUpload", { payload: "{}" }); } catch { diagThrew = true; }
    if (stealthThrew && diagThrew) ok(31, "§3.2/B26 隐身开启→工单/诊断出站请求不出（错误上浮）");
    else fail(31, "隐身闸", JSON.stringify({ stealthThrew, diagThrew }));
  } finally {
    if (settingBackup === null) rmSync(settingPath, { force: true });
    else writeFileSync(settingPath, settingBackup);
  }

  // 实例二：无任何配置 → 降级形态（独立 support 根）
  local = await spawnBridge({
    BRIDGE_SUPPORT_ROOT: supportRoot2,
    BRIDGE_LICENSE_FILE: licenseFile,
  });
  // 32：supportInfoGet 无配置 → opsApi=null（降级）
  const info2 = await local.call("supportInfoGet");
  if (info2.opsApi === null && info2.source === "none") ok(32, "无配置=降级形态判定（opsApi=null）");
  else fail(32, "降级判定", JSON.stringify(info2));

  // 33：降级 create → §3.5 Markdown 落盘（E31）+ticketKey 回带+元数据在物
  const c2 = await local.call("supportTicketCreate", { requester: "走查律师", subject: "本地工单", content: "降级内容" });
  const mdOnDisk = c2.path && existsSync(c2.path) ? readFileSync(c2.path, "utf-8") : "";
  const parsedOnDisk = parseTicketMarkdown(mdOnDisk);
  if (c2.mode === "local" && c2.ok === true && mdOnDisk.includes("降级内容")
    && parsedOnDisk.ticketKey === c2.ticketKey && parsedOnDisk.subject === "本地工单" && parsedOnDisk.requester === "走查律师") {
    ok(33, "E31/§3.5 降级落盘：Markdown 元数据（含降级仍生成的 ticket_key）+正文在物");
  } else fail(33, "降级落盘", JSON.stringify({ c2, mdOnDisk: mdOnDisk.slice(0, 200) }));

  // 34：E38 降级列表 → 本地枚举回显（倒序+主题解析）
  await local.call("supportTicketCreate", { requester: "另一个人", subject: "跨桶第二单", content: "" });
  const l2 = await local.call("supportTicketList", { requester: "走查律师", ticketKey: "" });
  const rows2 = l2.localRows ?? [];
  if (l2.mode === "local" && rows2.length === 2 && rows2[0].subject === "跨桶第二单"
    && rows2.every((r) => r.path && r.fileName.startsWith("ticket-"))) {
    ok(34, "E38 降级列表：本地枚举倒序+主题解析+跨桶可见（有意差异）");
  } else fail(34, "E38 列表", JSON.stringify(l2));

  // 35：降级不受 #9 隐身约束（§3.4 钉死）——翻转设置后降级落盘照常
  try {
    mkdirForSetting();
    writeFileSync(settingPath, JSON.stringify({ stealthMode: { enabled: true } }), "utf-8");
    const c3 = await local.call("supportTicketCreate", { requester: "走查律师", subject: "隐身期本地单", content: "" });
    if (c3.mode === "local" && c3.ok === true && existsSync(c3.path)) ok(35, "§3.4 降级×隐身组合：本地落盘照常（不受 #9 约束）");
    else fail(35, "降级隐身", JSON.stringify(c3));
  } finally {
    if (settingBackup === null) rmSync(settingPath, { force: true });
    else writeFileSync(settingPath, settingBackup);
  }

  // 36：A17 等量——remote list 响应非数组抛错（渲染层捕获后静默空列表）
  ops.script.listBody = { oops: true };
  try {
    await remote.call("supportTicketList", { requester: "走查律师", ticketKey: "tk-1" });
    fail(36, "A17 应抛未抛");
  } catch (e) {
    if (String(e?.message ?? e).includes("数组")) ok(36, "A17 响应非数组→桥抛错（渲染层静默空列表）");
    else fail(36, "A17 错误文案", String(e?.message ?? e));
  }
} catch (e) {
  fail("fatal", e.message);
} finally {
  for (const [label, b] of [["remote", remote], ["local", local]]) {
    if (b) { try { await killOwnBridge(b.child.pid, b.port); } catch (e) { fail(`cleanup-${label}`, e.message); } }
  }
  try { ops.server.close(); } catch { /* 尽力而为 */ }
  try { rmSync(scratch, { recursive: true, force: true }); } catch { /* 尽力而为 */ }
}

function mkdirForSetting() {
  mkdirSync(join(settingPath, ".."), { recursive: true });
}

console.log(`[re31-synth] ── ${passed} OK / ${failed} FAIL ──`);
if (failed > 0) { console.error("RE31_SUPPORT_SYNTH_FAIL"); process.exit(1); }
console.log("RE31_SUPPORT_SYNTH_PASS");
