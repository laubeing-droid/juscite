#!/usr/bin/env node
// G6 连接器 MCP 面（施工波三轮 20261031 · 桥健①②）。
// 定位：把「法条有效性核验＋类案检索」两腿以 stdio MCP 工具暴露给 runtime
// （oc28 经 experimental.mcp.add 运行时挂载拉起本进程）；真源=自家
//   ①法条腿=RE-13 轻量法条包（lawbook-packs，LCCC 路线）+ citation_verify_lite
//     单一核验权威（RE-14 §3.2：禁第二核验器）；
//   ②类案腿=legal-cn-cases lcr 公开 Store（合成夹具种子库，零真案）。
// 机制对拍锚=华宇元典 MCP（readable/cn-case-retrieval-mcp、cn-yuandian-case-search
// 机制笔记；第三方仅参考，文案全部自写——表达隔离）。
// 挂载协议：oc28 registerTools（runtime-port 能力⑤）→ PUT experimental/mcp/juscite-g6
// 携 JUSCITE_G6_TOOL_MANIFEST（经安全层预阻断过滤后的注册目录）→ 本进程只暴露
// manifest∩已实现 的工具；manifest 有名而无实现=stderr 记名不广告（诚实）。
// 纪律：零网络（两腿均本地数据面）；缺配置具名拒（fail-closed），不猜不编。

import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync, existsSync, mkdirSync, appendFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveCitationEnginePath, resolveCitationPackDir } from "./citation_verify_service.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));

// ── 工具实现（域词自写；probe 可直接 import 复用同一实现）──

const CITATION_TIMEOUT_MS = 120_000;

function todayCn() {
  // 与桥面 todayCn 同口径（UTC+8 固定日历日）；as_of 仍优先取调用方显式值。
  const now = new Date(Date.now() + 8 * 3600_000);
  return now.toISOString().slice(0, 10).replaceAll("-", "");
}

/** 法条有效性核验：NL query 文本→引证解析+效力核验（citation.verify_document 引擎直通）。 */
export async function statuteCheck(input) {
  const query = typeof input?.query === "string" ? input.query : "";
  if (!query.trim()) return { isError: true, code: "query_required", message: "query（自然语言法条问询全文）必填" };
  const asOf = /^\d{8}$/.test(String(input?.as_of ?? "")) ? String(input.as_of) : todayCn();
  const engine = resolveCitationEnginePath();
  if (!engine) return { isError: true, code: "citation_engine_not_found", message: "citation_verify_lite.py 未定位（BRIDGE_CITATION_ENGINE 可显式指定）" };
  const packDir = resolveCitationPackDir();
  const tmp = mkdtempSync(join(tmpdir(), "g6-statute-"));
  const reqPath = join(tmp, "req.json");
  writeFileSync(reqPath, JSON.stringify({ pack_dir: packDir, as_of: asOf, text: query }), "utf-8");
  const run = spawnSync(pythonBin(), ["-X", "utf8", engine, "citation.verify_document", reqPath], { timeout: CITATION_TIMEOUT_MS, encoding: "utf-8" });
  if (run.error) return { isError: true, code: "citation_engine_spawn_failed", message: String(run.error.message ?? run.error) };
  let body;
  try { body = JSON.parse(run.stdout); } catch { return { isError: true, code: "citation_engine_bad_output", message: (run.stdout || run.stderr || "").slice(0, 200) }; }
  if (body.status !== "OWNER_RESPONSE") return { isError: true, code: String(body.code ?? "citation_engine_not_connected"), message: "引擎具名拒（fail-closed）" };
  const r = body.result ?? {};
  return {
    as_of: asOf,
    total: r.summary?.total ?? (r.citations ?? []).length,
    by_status: r.summary?.by_status ?? {},
    citations: (r.citations ?? []).map((c) => ({
      citation_text: c.citation_text, title: c.title, article_ref: c.article_ref,
      status: c.status, decision: c.decision ?? null, code: c.code,
      replacement: c.replacement ?? null,
      article_snippet: c.support?.article_text ? String(c.support.article_text).slice(0, 120) : null,
    })),
    note: "本地包核验（RE-13 轻量包+RE-14 引擎直通）；付费/web 段声明缺口不外推（local_first_no_silent_escalation）",
  };
}

function pythonBin() { return process.env.JUSCITE_G6_PYTHON || "python"; }

/** 类案检索：lcr Store（合成夹具）＋0 结果重试一次机制（去案由/扩量/泛化）。 */
export async function caseSearch(input) {
  const query = typeof input?.query === "string" ? input.query : "";
  if (!query.trim()) return { isError: true, code: "query_required", message: "query（类案检索自然语言）必填" };
  const home = process.env.JUSCITE_G6_LCR_HOME;
  const fixtures = process.env.JUSCITE_G6_LCR_FIXTURES;
  const db = process.env.JUSCITE_G6_LCR_DB;
  if (!home || !fixtures || !db) {
    return { isError: true, code: "lcr_not_configured", message: "JUSCITE_G6_LCR_HOME/JUSCITE_G6_LCR_FIXTURES/JUSCITE_G6_LCR_DB 三 env 必设（fail-closed，不静默降级）" };
  }
  const tmp = mkdtempSync(join(tmpdir(), "g6-case-"));
  const reqPath = join(tmp, "req.json");
  writeFileSync(reqPath, JSON.stringify({
    db, fixtures_dir: fixtures, query,
    cause_of_action: Array.isArray(input?.cause_of_action) ? input.cause_of_action : [],
    return_num: Number.isInteger(input?.return_num) ? input.return_num : 6,
    judge_date_after: typeof input?.judge_date_after === "string" ? input.judge_date_after : undefined,
  }), "utf-8");
  const run = spawnSync(pythonBin(), ["-X", "utf8", join(HERE, "g6_case_search.py"), reqPath], { timeout: CITATION_TIMEOUT_MS, encoding: "utf-8" });
  if (run.error) return { isError: true, code: "case_search_spawn_failed", message: String(run.error.message ?? run.error) };
  let body;
  try { body = JSON.parse(run.stdout); } catch { return { isError: true, code: "case_search_bad_output", message: (run.stdout || run.stderr || "").slice(0, 200) }; }
  if (body.status !== "OK") return { isError: true, code: String(body.code ?? "case_search_not_connected"), message: "检索腿具名拒（fail-closed）" };
  return body.result;
}

export const TOOL_IMPLEMENTATIONS = {
  juscite_statute_check: statuteCheck,
  juscite_case_search: caseSearch,
};

// ── stdio MCP 服务（legacy initialize 握手；JSON-RPC 每行一帧）──

const logFile = process.env.JUSCITE_G6_MCP_LOG;
function log(line) {
  const stamp = new Date().toISOString();
  try {
    if (logFile) { mkdirSync(dirname(logFile), { recursive: true }); appendFileSync(logFile, `[${stamp}] ${line}\n`, "utf-8"); }
  } catch { /* 日志失败不拖垮服务面 */ }
  process.stderr.write(`[g6-mcp ${stamp}] ${line}\n`);
}

function loadManifest() {
  const raw = process.env.JUSCITE_G6_TOOL_MANIFEST;
  if (!raw) return null; // 无 manifest=未按注册面拉起（直连调试模式）：暴露全部已实现工具
  try {
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr)) return [];
    return arr.filter((t) => t && typeof t.name === "string");
  } catch { return []; }
}

function advertisedTools() {
  const manifest = loadManifest();
  const all = Object.keys(TOOL_IMPLEMENTATIONS);
  const names = manifest ? all.filter((n) => manifest.some((t) => t.name === n)) : all;
  if (manifest) {
    const skipped = manifest.map((t) => t.name).filter((n) => !all.includes(n));
    if (skipped.length) log(`manifest 有名无实现（不广告，诚实跳过）：${skipped.join(",")}`);
  }
  return names.map((name) => {
    const m = manifest?.find((t) => t.name === name);
    return {
      name,
      description: m?.description ?? "",
      inputSchema: m?.inputSchema ?? { type: "object", properties: {}, required: [] },
    };
  });
}

const out = (msg) => process.stdout.write(JSON.stringify(msg) + "\n");

async function handleRequest(msg) {
  if (msg.method === "initialize") {
    log(`initialize 自 ${JSON.stringify(msg.params?.clientInfo ?? {})} protocolVersion=${msg.params?.protocolVersion}`);
    return { protocolVersion: msg.params?.protocolVersion ?? "2025-06-18", capabilities: { tools: {} }, serverInfo: { name: "juscite-g6-connector", version: "1.0.0" } };
  }
  if (msg.method === "tools/list") {
    const tools = advertisedTools();
    log(`tools/list → ${tools.map((t) => t.name).join(",") || "(空)"}`);
    return { tools };
  }
  if (msg.method === "tools/call") {
    const name = msg.params?.name;
    const args = msg.params?.arguments ?? {};
    log(`tools/call ${name} args=${JSON.stringify(args).slice(0, 200)}`);
    const impl = TOOL_IMPLEMENTATIONS[name];
    if (!impl) return { content: [{ type: "text", text: `工具不在已实现目录：${name}` }], isError: true };
    const result = await impl(args);
    const isError = result?.isError === true;
    if (isError) log(`tools/call ${name} 具名拒 ${result.code}`);
    else log(`tools/call ${name} 完成`);
    return { content: [{ type: "text", text: JSON.stringify(result, null, 1) }], isError: Boolean(isError) };
  }
  if (msg.method === "ping") return {};
  return undefined; // 未知方法 → -32601
}

let buf = "";
process.stdin.setEncoding("utf-8");
process.stdin.on("data", (chunk) => {
  buf += chunk;
  let i;
  while ((i = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, i);
    buf = buf.slice(i + 1);
    if (!line.trim()) continue;
    let msg;
    try { msg = JSON.parse(line); } catch { log("坏帧丢弃（非 JSON 行）"); continue; }
    if (msg.id === undefined || msg.id === null) { log(`通知 ${msg.method}`); continue; }
    handleRequest(msg).then((result) => {
      if (result === undefined) out({ jsonrpc: "2.0", id: msg.id, error: { code: -32601, message: `method not found: ${msg.method}` } });
      else out({ jsonrpc: "2.0", id: msg.id, result });
    }).catch((e) => {
      out({ jsonrpc: "2.0", id: msg.id, error: { code: -32603, message: String(e?.message ?? e) } });
    });
  }
});
process.stdin.on("end", () => { log("stdin 结束，退出"); process.exit(0); });
log(`juscite-g6 连接器 MCP 启动 pid=${process.pid} manifest=${process.env.JUSCITE_G6_TOOL_MANIFEST ? "on" : "off(直连)"}`);
