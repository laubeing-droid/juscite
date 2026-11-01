#!/usr/bin/env node
// 【#21 安全层】设置面板+审计「工具决策」tab 桥面合成自测（施工波二轮 2026-10-30）。
// 本单改动面：tool_audit_service.mjs 新增 listToolAuditsRecent（跨会话最近 ≤limit 倒序，默认 200）
// + bridge_host.mjs toolAuditsList 缺省 conversationId 走最近面（会话 id 在=按会话升序，向后兼容）。
// 全合成材料：A 段=临时目录 node:sqlite 直测服务层；B 段=自拉隔离桥实例（端口自 :3090 起探首个
// 空闲，BRIDGE_OC28_SSE=0 隔离 oc28，零真实会话/工具流量、零 %APPDATA% 设置写入）经 @zcode/rpc
// 真通道打 RPC；收场杀前核验命令行含 bridge_host.mjs 并清自家 bridge-<port>.db*。
// 纯 Node；B 段 @zcode/rpc 为 TS 源 → 需 tsx 加载。单命令 exit 0/1，末行 RE21_TOOLSEC_UI_SYNTH_PASS。
// 用法：node --import tsx tools/bridge/re21_toolsec_ui_synthetic.mjs
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createRequire } from "node:module";
const { DatabaseSync } = createRequire(import.meta.url)("node:sqlite");

const dir = mkdtempSync(join(tmpdir(), "juscite-re21-toolsec-"));
let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[re21-toolsec] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[re21-toolsec] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }

const { createToolAuditService } = await import("./tool_audit_service.mjs");

// ── A1：listToolAuditsRecent——跨会话最近倒序（同刻时间戳按 rowid 兜底保序）+camel 字段+limit 上限 ──
{
  const db = new DatabaseSync(join(dir, "a1.db"));
  const audit = createToolAuditService(db);
  audit.recordToolAudit({ conversationId: "ses-a", toolName: "bash", effect: "deny", code: "shell_disabled", reason: "r1", policyVersion: 1, args: { command: "dir" } });
  audit.recordToolAudit({ conversationId: "ses-a", toolName: "matter.read", effect: "allow", code: "read_only", reason: "r2", policyVersion: 1, args: {} });
  audit.recordToolAudit({ conversationId: "ses-b", toolName: "bash", effect: "deny", code: "shell_disabled", reason: "r3", policyVersion: 1, args: { command: "dir" } });
  const recent = audit.listToolAuditsRecent();
  const recent2 = audit.listToolAuditsRecent(2);
  const convA = audit.listToolAudits("ses-a");
  const convEmpty = audit.listToolAudits("");
  const cols = Object.keys(recent[0]);
  if (recent.length === 3
    && recent[0].conversationId === "ses-b" && recent[0].toolName === "bash" // 最新=最后写入行
    && recent[2].conversationId === "ses-a" && recent[2].effect === "deny" // 最早=首写入行
    && recent2.length === 2 && recent2[0].id === recent[0].id // limit 截最近
    && cols.length === 11 && cols.includes("conversationId") && cols.includes("argsSummary")
    && convA.length === 2 && convA[0].effect === "deny" && convA[1].effect === "allow" // 按会话升序原语义不变
    && convEmpty.length === 0) // 空会话 id 原语义不变（守旧调用方）
    ok("A1", "listToolAuditsRecent 最近倒序+limit+十一字段；listToolAudits 按会话升序/空会话零行原语义不变");
  else fail("A1", "最近面/兼容面不过", JSON.stringify({ recent: recent.length, recent2: recent2.length, convA: convA.length, cols }));
}

// ── B1：真桥接线——隔离桥实例，toolAuditsList 缺省=最近面/带会话 id=按会话升序（向后兼容） ──
{
  const { spawn, spawnSync } = await import("node:child_process");
  const { homedir } = await import("node:os");
  const { fileURLToPath } = await import("node:url");
  const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
  const storeDir = join(homedir(), "AppData", "Roaming", "Juscite", "bridge");
  // 端口自 :3090 起探首个空闲（本单隔离端口段；netstat 探 LISTENING 防撞在跑实例）
  const pickFreePort = () => {
    const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
    const busy = new Set(
      String(r.stdout ?? "").split("\n")
        .map((l) => /TCP\s+\S*:(\d+)\s+\S+\s+LISTENING/.exec(l)?.[1])
        .filter(Boolean),
    );
    for (let p = 3090; p < 3190; p += 1) if (!busy.has(String(p))) return p;
    throw new Error(":3090-3189 无空闲端口");
  };
  const port = pickFreePort();
  const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(port), BRIDGE_OC28_SSE: "0" }, stdio: "ignore", detached: true });
  try {
    const wsMod = await import("ws");
    const rpcMod = await import("@zcode/rpc");
    // 起探（/api/server-info 通用探活面）
    let up = false;
    const deadline = Date.now() + 60000;
    while (Date.now() < deadline && !up) {
      try {
        const r = await fetch(`http://127.0.0.1:${port}/api/server-info`, { signal: AbortSignal.timeout(2500) });
        if (r.ok) up = true;
      } catch { /* 未起，重试 */ }
      if (!up) await new Promise((res) => setTimeout(res, 500));
    }
    if (!up) throw new Error(`:${port} 60s 不可探`);
    const ws = new wsMod.default(`ws://127.0.0.1:${port}/ws`);
    ws.binaryType = "arraybuffer";
    const data = { fire: (_b) => {} };
    ws.on("message", (buf) => data.fire(rpcMod.VSBuffer.wrap(new Uint8Array(buf))));
    await new Promise((res, rej) => { ws.on("open", res); ws.on("error", rej); });
    const isocket = {
      onData: (l) => { data.fire = l; return { dispose: () => {} }; },
      onClose: () => ({ dispose: () => {} }),
      onEnd: () => ({ dispose: () => {} }),
      write: (b) => ws.send(b.buffer),
      end: () => ws.close(),
      drain: async () => {},
      dispose: () => ws.close(),
    };
    const client = new rpcMod.ChannelClient(new rpcMod.SocketProtocol(isocket));
    const ch = client.getChannel("zcode-agent");
    const call = (m, a) => ch.call(m, a === undefined ? [] : [a]);
    const convA = `ses-toolsec-a-${port}`;
    const convB = `ses-toolsec-b-${port}`;
    // 决策三连（设置默认 shell 关：deny 入账；只读 allow 入账）——审计行真实落库
    const d1 = await call("toolPolicyDecide", { conversationId: convA, toolName: "bash", args: { command: "dir" } });
    const d2 = await call("toolPolicyDecide", { conversationId: convA, toolName: "matter.read", args: {} });
    const d3 = await call("toolPolicyDecide", { conversationId: convB, toolName: "bash", args: { command: "dir" } });
    const recent = await call("toolAuditsList", {}); // 缺省 conversationId=跨会话最近面
    const recentLimited = await call("toolAuditsList", { limit: 2 });
    const byConv = await call("toolAuditsList", { conversationId: convA }); // 向后兼容面
    const emptyConv = await call("toolAuditsList", { conversationId: "" }); // 空串=归入最近面分支
    ws.close();
    // 直开桥库断言 0021 迁移在物 + 行数
    const db = new DatabaseSync(join(storeDir, `bridge-${port}.db`), { readOnly: true });
    const tables = new Set(db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map((r) => r.name));
    const count = db.prepare("SELECT COUNT(*) AS n FROM tool_audits").get().n;
    db.close();
    const r0 = recent.rows?.[0];
    if (d1.effect === "deny" && d1.code === "shell_disabled"
      && d2.effect === "allow" && d3.effect === "deny"
      && Array.isArray(recent.rows) && recent.rows.length === 3
      && r0?.conversationId === convB && r0?.toolName === "bash" // 最近倒序：最后写入在前
      && recent.rows[2]?.conversationId === convA && recent.rows[2]?.effect === "deny"
      && recentLimited.rows?.length === 2 && recentLimited.rows[0]?.id === r0?.id
      && byConv.rows?.length === 2 && byConv.rows[0]?.effect === "deny" && byConv.rows[1]?.effect === "allow"
      && emptyConv.rows?.length === 3 // 空串会话 id=最近面分支（不误判为「按空会话过滤」）
      && tables.has("tool_audits") && count === 3)
      ok("B1", `真桥 RPC（:${port}）：决策三连入账+toolAuditsList 缺省=最近倒序/带会话 id=升序兼容/0021 在物`);
    else fail("B1", "真桥接线不过", JSON.stringify({
      d1: d1?.effect, d2: d2?.effect, d3: d3?.effect,
      recent: recent.rows?.length, first: r0, limited: recentLimited.rows?.length,
      byConv: byConv.rows?.length, emptyConv: emptyConv.rows?.length, tables: tables.has("tool_audits"), count,
    }));
  } catch (e) {
    fail("B1", "真桥接线异常", String(e?.message ?? e));
  } finally {
    const looksBridge = (pid) => {
      const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
        `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
        { encoding: "utf-8", timeout: 20000 });
      return String(r.stdout ?? "").includes("bridge_host.mjs");
    };
    if (looksBridge(child.pid)) {
      spawnSync("taskkill", ["/PID", String(child.pid), "/F", "/T"], { timeout: 15000 });
    } else {
      fail("cleanup", `pid=${child.pid} 命令行不含 bridge_host.mjs，宁停不误杀（库文件未清）`);
    }
    for (const suffix of [".db", ".db-wal", ".db-shm"]) {
      try { rmSync(join(storeDir, `bridge-${port}${suffix}`), { force: true }); } catch { /* 尽力而为 */ }
    }
  }
}

try { rmSync(dir, { recursive: true, force: true }); } catch { /* 尽力而为 */ }

if (failed > 0) {
  console.error(`[re21-toolsec] FAIL ${failed} 用例失败（${passed} 过）`);
  process.exit(1);
}
console.log(`[re21-toolsec] ${passed} 用例全过`);
console.log("RE21_TOOLSEC_UI_SYNTH_PASS");
