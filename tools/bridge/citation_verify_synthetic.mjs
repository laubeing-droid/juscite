#!/usr/bin/env node
// 【功能 #14】引证核验桥端合成自测（ci_gate fast 随行步，RE-14 §3.5 桥端针组+引擎针组编排）。
// 三段：
//   A. 引擎针组：子进程跑 citation_engine_probe.py（60 针：解析/12 态/全文记账/S5 fail-closed/
//      AST 零网络零写零模型），末行 CITATION_ENGINE_PROBE_PASS 可判。
//   B. 桥端 HTTP 针（真子进程桥，隔离端口+BRIDGE_OC28_SSE=0）：§3.5 桥端四针——
//      ①history limit 缺省=20；②limit≤0/非整数→invalid_limit；③limit>100→封顶 100 如实返回；
//      ④body 非 JSON→request_body_not_json＋缺必填字段字段级具名码透传——外加端到端核验
//      （真实内置包）、F4 落账（0018 迁移表直查，只追加）、G14 零引用 HTTP 形态、config 端点、
//      server-info citation 能力标记。
//   C. 无包实例针：第二隔离桥（BRIDGE_CITATION_PACK_DIR 指向空目录）→config available=false
//      ＋核验 NOT_CONNECTED citation_pack_not_configured（D5 不静默降级，UI G7 错误态数据径）。
// 收场杀自家实例（杀前核验命令行含 bridge_host.mjs，同 ci_gate 纪律）并清自己的 bridge-<port>.db*。
// 纯 Node 零依赖；单命令 exit 0/1，末行 CITATION_VERIFY_SYNTH_PASS 可判。
// 用法：node tools/bridge/citation_verify_synthetic.mjs
import { spawn, spawnSync } from "node:child_process";
import { rmSync, mkdtempSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url)); // tools/bridge/ → 仓库根
let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[citation-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[citation-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }
function check(n, cond, msg, detail) { if (cond) ok(n, msg); else fail(n, msg, detail); }

function pickFreePort() {
  for (let p = 30400 + Math.floor(Math.random() * 2000); ; p += 1) {
    const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Test-NetConnection -ComputerName 127.0.0.1 -Port ${p} -InformationLevel Quiet -WarningAction SilentlyContinue)`],
      { encoding: "utf-8", timeout: 20000 });
    if (String(r.stdout ?? "").trim() !== "True") return p;
  }
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

async function postJson(port, path, body) {
  const r = await fetch(`http://127.0.0.1:${port}${path}`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
    signal: AbortSignal.timeout(120_000),
  });
  return { code: r.status, body: await r.json() };
}
async function getJson(port, path) {
  const r = await fetch(`http://127.0.0.1:${port}${path}`, { signal: AbortSignal.timeout(15_000) });
  return { code: r.status, body: await r.json() };
}

const todayCn = () => new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 10);

async function main() {
  let n = 0;
  // ── A. 引擎针组 ──
  const py = process.env.BRIDGE_PYTHON || "python";
  const probe = spawnSync(py, ["-X", "utf8", join("tools", "bridge", "citation_engine_probe.py")],
    { cwd: REPO_ROOT, encoding: "utf-8", timeout: 300_000, maxBuffer: 32 * 1024 * 1024 });
  n += 1;
  check(n, probe.status === 0 && probe.stdout.includes("CITATION_ENGINE_PROBE_PASS"),
    `A 引擎针组 CITATION_ENGINE_PROBE_PASS（${(probe.stdout.match(/PASS=(\d+) FAIL=(\d+)/) ?? ["", "?", "?"]).slice(1).join("/")}）`,
    probe.status === 0 ? probe.stdout.slice(-400) : probe.stderr.slice(-800));

  // ── B. 桥端 HTTP 针（真子进程桥）──
  const port = pickFreePort();
  const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(port), BRIDGE_OC28_SSE: "0" }, stdio: "ignore" });
  try {
    // 2026-10-31 清障二轮：60s→300s（re26 走查同款窗口放宽先例）——共享工位并发施工期桥冷载实测 >90s，
    // 环境性停顿非产品缺陷；断言面零改动，仅等桥起来。
    const info = await probeServerInfo(port, 300_000);
    if (!info) { fail(n += 1, `:${port} 300s 不可探`); throw new Error("桥未起，后续用例跳过"); }
    n += 1;
    check(n, info.citation === 1, "server-info 携 citation 能力标记（旧桥判旧换新）", JSON.stringify(info).slice(0, 160));

    // 端到端单条核验（真实内置包，缺省时点注入）
    const v1 = await postJson(port, "/api/verify/citation", { citation: "《合同法》第一条" });
    n += 1;
    check(n, v1.code === 200 && v1.body.status === "OWNER_RESPONSE"
      && v1.body.business_complete === false
      && v1.body.result.status === "失效" && v1.body.result.code === "SUPERSEDED_NOT_CITABLE"
      && v1.body.result.replacement === "unknown" && v1.body.result.title === "合同法",
      "端到端单条：合同法→失效（真实包；OWNER_RESPONSE 信封）",
      JSON.stringify(v1.body).slice(0, 240));
    const today = todayCn().replaceAll("-", "");
    n += 1;
    check(n, v1.body.result.decision === "BLOCKED" && Array.isArray(v1.body.result.scope)
      && v1.body.result.verified_scoped === false,
      "单条记录 B 全段字段（decision/scope/verified_scoped）", v1.body.result.decision);

    // 端到端全文核验 + G14 零引用 HTTP 形态
    const v2 = await postJson(port, "/api/verify/document", {
      text: "《合同法》第一条《公司法》第一条《不存在于包中的法》第一条。", as_of: "20250101",
    });
    n += 1;
    check(n, v2.body.status === "OWNER_RESPONSE" && Array.isArray(v2.body.result.citations)
      && v2.body.result.citations.length === 3
      && v2.body.result.citations.map((c) => c.index).join(",") === "0,1,2"
      && v2.body.result.summary.total === 3
      && !("document_pass" in v2.body.result.summary),
      "端到端全文：3 引用逐条记账（index/span/summary，无文档级 PASS）",
      JSON.stringify(v2.body.result.summary).slice(0, 200));
    n += 1;
    check(n, v2.body.result.citations[0].status === "失效"
      && v2.body.result.citations[1].status === "现行"
      && v2.body.result.citations[2].status === "虚构",
      "全文三状态互不覆盖（失效/现行/虚构，C2）",
      v2.body.result.citations.map((c) => c.status).join("/"));
    const v3 = await postJson(port, "/api/verify/document", { text: "本段没有任何书名号引用。" });
    n += 1;
    check(n, v3.body.status === "OWNER_RESPONSE" && v3.body.result.citations.length === 0
      && v3.body.result.summary.total === 0,
      "G14 零引用 HTTP 形态（citations=[]＋total=0）", JSON.stringify(v3.body).slice(0, 160));

    // F4 落账：0018 表直查（单条 1 行＋全文 3 行＝4）
    const dbPath = join(storeDir, `bridge-${port}.db`);
    const db = new DatabaseSync(dbPath, { readOnly: false });
    n += 1;
    check(n, db.prepare("SELECT COUNT(*) AS c FROM citation_checks").get().c === 4,
      "F4 落账只追加（1+3=4 行，0018_citation_checks）",
      db.prepare("SELECT COUNT(*) AS c FROM citation_checks").get().c);
    n += 1;
    const topRow = db.prepare("SELECT * FROM citation_checks ORDER BY requested_at DESC, rowid DESC LIMIT 1").get();
    // 最新落账行=全文核验末条引用（同一毫秒内 rowid DESC 兜底排序）
    check(n, topRow && topRow.citation_text === "《不存在于包中的法》第一条"
      && topRow.status === "虚构" && topRow.as_of === "20250101"
      && topRow.verified_scoped === 0 && JSON.parse(topRow.reasons_json).length > 0,
      "落账行字段齐（时间/as_of/引文/状态/码/verified_scoped/reasons_json）",
      JSON.stringify(topRow).slice(0, 200));
    const contractRow = db.prepare(
      "SELECT * FROM citation_checks WHERE citation_text = '《合同法》第一条' AND as_of = ?")
      .get(today);
    n += 1;
    check(n, contractRow && contractRow.status === "失效"
      && contractRow.verified_scoped === 0,
      "单条核验落账行（缺省时点注入=今天，失效态如实记账）",
      JSON.stringify(contractRow).slice(0, 160));
    // 铺底 121 行合成落账（针①③的量测材料；requested_at 递减保证倒序确定性）
    const ins = db.prepare(`INSERT INTO citation_checks
      (id, requested_at, as_of, citation_text, status, code, verified_scoped, reasons_json)
      VALUES (?, ?, '20200101', ?, '现行', 'CURRENT_IN_FORCE_CITABLE', 1, '[]')`);
    db.exec("BEGIN IMMEDIATE");
    for (let i = 0; i < 121; i++) ins.run(`synth-${i}`, 1_700_000_000_000 - i, `《铺底法》第${i}条`);
    db.exec("COMMIT");
    db.close();

    // ① history 缺省=20
    const h1 = await getJson(port, "/api/verify/citation/history");
    n += 1;
    check(n, h1.body.status === "OWNER_RESPONSE" && h1.body.result.items.length === 20
      && h1.body.result.items[0].citationText === "《不存在于包中的法》第一条"
      && h1.body.result.items.some((it) => it.citationText === "《合同法》第一条" && it.status === "失效"),
      "① history limit 缺省=20 且倒序（最新核验在首，含单条落账行）",
      `items=${h1.body.result.items.length} first=${h1.body.result.items[0]?.citationText}`);
    // ② limit≤0/非整数→invalid_limit
    for (const bad of ["0", "-3", "abc", "1.5"]) {
      const hb = await getJson(port, `/api/verify/citation/history?limit=${encodeURIComponent(bad)}`);
      n += 1;
      check(n, hb.code === 200 && hb.body.status === "NOT_CONNECTED"
        && hb.body.code === "invalid_limit",
        `② limit=${bad}→invalid_limit（HTTP 200 信封）`, JSON.stringify(hb.body));
    }
    // ③ limit>100 封顶 100 如实返回（不带「截断」以外语义）
    const h3 = await getJson(port, "/api/verify/citation/history?limit=500");
    n += 1;
    check(n, h3.body.status === "OWNER_RESPONSE" && h3.body.result.items.length === 100,
      "③ limit>100 封顶 100 如实返回", `items=${h3.body.result.items.length}`);
    const h4 = await getJson(port, "/api/verify/citation/history?limit=3");
    n += 1;
    check(n, h4.body.result.items.length === 3
      && h4.body.result.items.every((it) => it.verifiedScoped === true || it.verifiedScoped === false)
      && typeof h4.body.result.items[0].requestedAt === "number",
      "history 行形态（verifiedScoped 布尔/时间数值，G10 回填数据径）",
      JSON.stringify(h4.body.result.items[0]).slice(0, 160));

    // ④ body 非 JSON + 缺必填字段字段级透传
    const r1 = await fetch(`http://127.0.0.1:${port}/api/verify/citation`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: "{citation: 不是JSON", signal: AbortSignal.timeout(15_000),
    });
    const b1 = await r1.json();
    n += 1;
    check(n, r1.status === 200 && b1.status === "NOT_CONNECTED" && b1.code === "request_body_not_json",
      "④ body 非 JSON→request_body_not_json（HTTP 200 信封）", JSON.stringify(b1));
    const r2 = await postJson(port, "/api/verify/citation", { text: "字段名错" });
    n += 1;
    check(n, r2.body.status === "NOT_CONNECTED" && r2.body.code === "citation_text_required",
      "④ 缺 citation→引擎字段级具名码透传", JSON.stringify(r2.body));
    const r3 = await postJson(port, "/api/verify/document", {});
    n += 1;
    check(n, r3.body.status === "NOT_CONNECTED" && r3.body.code === "citation_document_text_required",
      "④ document 缺 text→字段级具名码透传（C5）", JSON.stringify(r3.body));
    const r4 = await postJson(port, "/api/verify/citation", { citation: "《合同法》第一条", as_of: "abc" });
    n += 1;
    check(n, r4.body.status === "NOT_CONNECTED" && r4.body.code === "citation_as_of_must_be_yyyymmdd",
      "④ 非法 as_of→字段级具名码透传（B2）", JSON.stringify(r4.body));
    const r5 = await postJson(port, "/api/verify/citation", { citation: "没有引用" });
    n += 1;
    check(n, r5.body.status === "NOT_CONNECTED"
      && r5.body.code === "citation_exactly_one_expected_got:0",
      "④ 恰一条数约束透传（B3）", JSON.stringify(r5.body));

    // config 端点（包在位性＋meta，UI 空态/错误态具名提示数据径）
    const cfg = await getJson(port, "/api/verify/citation/config");
    n += 1;
    check(n, cfg.body.available === true && cfg.body.engine === true
      && cfg.body.pack && cfg.body.pack.name === "base" && cfg.body.pack.hash.length === 64,
      "config 端点：包在位＋pack.meta 四字段（D6 数据径）", JSON.stringify(cfg.body.pack).slice(0, 160));
  } finally {
    await killOwnBridge(child.pid, port);
  }

  // ── C. 无包实例针（D5 不静默降级；UI G7 错误态数据径）──
  const emptyPack = mkdtempSync(join(tmpdir(), "juscite-cite-nopack-"));
  const port2 = pickFreePort();
  const child2 = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    {
      cwd: REPO_ROOT,
      env: {
        ...process.env, BRIDGE_PORT: String(port2), BRIDGE_OC28_SSE: "0",
        BRIDGE_CITATION_PACK_DIR: emptyPack,
      },
      stdio: "ignore",
    });
  try {
    const info2 = await probeServerInfo(port2, 60_000);
    if (!info2) { fail(n += 1, `:${port2} 60s 不可探`); throw new Error("无包桥未起"); }
    const cfg2 = await getJson(port2, "/api/verify/citation/config");
    n += 1;
    check(n, cfg2.body.available === false
      && String(cfg2.body.note).includes("citation_pack_not_configured"),
      "C 无包 config：available=false＋具名指引（UI 空态数据径）", JSON.stringify(cfg2.body).slice(0, 200));
    const v9 = await postJson(port2, "/api/verify/citation", { citation: "《合同法》第一条" });
    n += 1;
    check(n, v9.code === 200 && v9.body.status === "NOT_CONNECTED"
      && v9.body.code === "citation_pack_not_configured",
      "C 无包核验→NOT_CONNECTED citation_pack_not_configured（不静默降级 D5）",
      JSON.stringify(v9.body));
  } finally {
    await killOwnBridge(child2.pid, port2);
    try { rmSync(emptyPack, { recursive: true, force: true }); } catch { /* 尽力而为 */ }
  }

  console.log(`[citation-synth] PASS=${passed} FAIL=${failed}`);
  if (failed) {
    console.log("[citation-synth] CITATION_VERIFY_SYNTH_FAIL");
    return 1;
  }
  console.log("[citation-synth] CITATION_VERIFY_SYNTH_PASS");
  return 0;
}

main().then((code) => process.exit(code)).catch((e) => {
  console.error("[citation-synth] FATAL:", e?.message ?? e);
  console.log(`[citation-synth] PASS=${passed} FAIL=${failed + 1}`);
  console.log("[citation-synth] CITATION_VERIFY_SYNTH_FAIL");
  process.exit(1);
});
