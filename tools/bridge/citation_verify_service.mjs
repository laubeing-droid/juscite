// 功能 #14 引证核验桥面（RE-14-引证核验.md §3.3 落码，2026-10-28）。
// 端点族（方法组冻结，F1 等量纪律）：
//   POST /api/verify/citation          {citation, as_of?} → 单条记录（B 全段字段）
//   POST /api/verify/document          {text, as_of?}     → {citations:[逐条+index+span], summary}
//   GET  /api/verify/citation/config   包在位性＋包 meta（UI 空态/错误态具名提示，43 行）
//   GET  /api/verify/citation/history?limit=20  F4 落账倒序（缺省 20/≤0 或非整数
//                                      invalid_limit/>100 封顶 100，§3.3 第 5 轮钉死边界）
// 引擎=implementation/python/citation_verify_lite.py（子进程一次性：temp JSON 进、JSON 出，
// 与冻结 recon 同纪律 §3.3；解析毫秒级）。as_of 由桥注入：缺省今天（UTC+8 固定日历日，
// 同 #13 todayCn 口径），用户可指定；引擎自身缺 as_of 拒绝不猜（B1）。
// 失败响应：HTTP 200＋{status:"NOT_CONNECTED", code} 信封（UI 按 G7 呈现）；body 非 JSON→
// request_body_not_json；缺必填字段→引擎字段级具名码透传（F2）。
// 落账（F4）：citation_checks 同库只追加（迁移 0017_citation_checks），不出域不外发；
// 消费路径闭合=history 端点＋UI 历史抽屉（G10）。
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { todayCn } from "./lawbook_model.mjs";

const HISTORY_DEFAULT = 20;
const HISTORY_CAP = 100;
const ENGINE_TIMEOUT_MS = 120_000; // 轻量包毫秒级；超时=环境异常具名拒

// 产品引证权威的文件名。BRIDGE_CITATION_ENGINE 只能改这个文件的位置。
const PRODUCT_CITATION_ENGINE = "citation_verify_lite.py";

function citationEngineBasename(p) {
  const norm = String(p).replace(/\\/g, "/");
  const slash = norm.lastIndexOf("/");
  return slash === -1 ? norm : norm.slice(slash + 1);
}

// 引擎路径解析：env 覆盖 > 随包布局（<bundle>/tools/bridge 相邻 ../../implementation/python）
// > dev 布局 cwd 向上 8 级扫描（kb/lawbook 同款）。
// 文件名必须是 citation_verify_lite.py。env 指向其它文件名（哪怕文件存在）返回 null，
// 不回退到内置轻量核——第二核不能被当成核验成功。文件名正确但路径不存在时，仍走随包/dev 查找。
export function resolveCitationEnginePath() {
  const env = process.env.BRIDGE_CITATION_ENGINE;
  if (env) {
    if (citationEngineBasename(env) !== PRODUCT_CITATION_ENGINE) return null;
    if (existsSync(env)) return env;
  }
  const bundled = fileURLToPath(new URL("../../implementation/python/citation_verify_lite.py", import.meta.url));
  if (existsSync(bundled)) return bundled;
  let dir = process.cwd();
  for (let i = 0; i < 8 && dir; i++) {
    const cand = join(dir, "implementation", "python", "citation_verify_lite.py");
    if (existsSync(cand)) return cand;
    const parent = resolve(dir, "..");
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

// 包目录解析（本期单包，§3.1 多包边界：多包聚合不预设计）：env 显式设置=权威
//（坏路径不静默回退——交给引擎落 citation_pack_not_configured 具名拒，D5）；
// 未设 env 时 lawbook-packs/ 根（cwd 向上 8 级）内首个含 pack.sqlite3 的包目录（字典序确定）。
export function resolveCitationPackDir() {
  const env = process.env.BRIDGE_CITATION_PACK_DIR;
  if (env) return env;
  let dir = process.cwd();
  for (let i = 0; i < 8 && dir; i++) {
    const root = join(dir, "lawbook-packs");
    if (existsSync(root)) {
      const packs = readdirSync(root, { withFileTypes: true })
        .filter((d) => d.isDirectory() && existsSync(join(root, d.name, "pack.sqlite3")))
        .map((d) => d.name).sort();
      if (packs.length) return join(root, packs[0]);
    }
    const parent = resolve(dir, "..");
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function packMetaOf(packDir) {
  try {
    const meta = JSON.parse(readFileSync(join(packDir, "pack.meta"), "utf-8"));
    const db = join(packDir, "pack.sqlite3");
    return {
      name: String(meta.name ?? ""), hash: String(meta.hash ?? ""),
      update: Number(meta.update ?? 0), filesize: Number(meta.filesize ?? 0),
      size: existsSync(db) ? statSync(db).size : 0,
    };
  } catch {
    return null;
  }
}

export function createCitationVerifyService({ store }) {
  // ── 引擎子进程一次性调用（temp JSON 进、JSON 出；exit 0/3 出口码合同 F2）──
  function runEngine(method, payload) {
    const engine = resolveCitationEnginePath();
    if (!engine) return { notConnected: "citation_engine_unavailable" };
    const work = mkdtempSync(join(tmpdir(), "juscite-cite-"));
    const reqPath = join(work, "request.json");
    try {
      writeFileSync(reqPath, JSON.stringify(payload), "utf-8");
      const py = process.env.BRIDGE_PYTHON || "python";
      const r = spawnSync(py, ["-X", "utf8", engine, method, reqPath], {
        encoding: "buffer", timeout: ENGINE_TIMEOUT_MS,
      });
      if (r.error && r.error.code === "ENOENT") {
        return { notConnected: "citation_engine_unavailable" };
      }
      if (r.error || r.signal) {
        return { notConnected: "citation_engine_timeout_or_failed" };
      }
      let envelope = null;
      try { envelope = JSON.parse((r.stdout ?? "").toString("utf-8").trim()); } catch { /* 落具名拒 */ }
      if (!envelope || typeof envelope !== "object" || !("status" in envelope)) {
        return { notConnected: "citation_engine_output_unreadable" };
      }
      if (envelope.status === "OWNER_RESPONSE") return { result: envelope.result };
      return { notConnected: String(envelope.code ?? "citation_engine_not_connected") };
    } finally {
      try { rmSync(work, { recursive: true, force: true }); } catch { /* 尽力而为 */ }
    }
  }

  function packDirOrNull() {
    return resolveCitationPackDir();
  }

  // F4 落账：只追加（单条 1 行；全文按逐条记账各 1 行），不出域不外发
  function ledgerAppend(rows, asOf) {
    for (const row of rows) {
      try {
        store.cvAppendCheck({
          id: randomUUID(),
          requested_at: Date.now(),
          as_of: asOf,
          citation_text: String(row.citation_text ?? ""),
          status: String(row.status ?? ""),
          code: String(row.code ?? ""),
          verified_scoped: row.verified_scoped ? 1 : 0,
          reasons_json: JSON.stringify(row.reasons ?? []),
        });
      } catch { /* 落账失败不阻塞核验应答；如实缺口 */ }
    }
  }

  function asOfOf(body) {
    const raw = typeof body?.as_of === "string" ? body.as_of.trim() : "";
    return raw || todayCn().replaceAll("-", ""); // G6 缺省今天（UTC+8 固定口径）
  }

  function configInfo() {
    const packDir = packDirOrNull();
    const usable = Boolean(packDir && existsSync(join(packDir, "pack.sqlite3")));
    return {
      available: usable,
      packDir: packDir ?? "",
      pack: packDir ? packMetaOf(packDir) : null,
      engine: Boolean(resolveCitationEnginePath()),
      python: Boolean(process.env.BRIDGE_PYTHON || spawnSyncSupport()),
      note: usable ? "" : "法条包未配置：请到法条手册确认 lawbook-packs 内置包（citation_pack_not_configured）",
    };
  }
  function spawnSyncSupport() {
    const r = spawnSync(process.env.BRIDGE_PYTHON || "python", ["--version"], { encoding: "utf-8", timeout: 10_000 });
    return r.status === 0;
  }

  async function httpHandler(req, res, url) {
    const path = url.pathname;
    if (!path.startsWith("/api/verify/")) return false;
    const send = (code, obj) => {
      if (res.headersSent) { res.end(); return; }
      res.writeHead(code, { "content-type": "application/json; charset=utf-8" });
      res.end(JSON.stringify(obj));
    };
    const readBodyJson = async () => {
      const chunks = [];
      let size = 0;
      for await (const c of req) {
        size += c.length;
        if (size > 4 * 1024 * 1024) {
          const e = new Error("请求体超限"); e.http = 413; throw e;
        }
        chunks.push(c);
      }
      const raw = Buffer.concat(chunks).toString("utf-8");
      if (!raw.trim()) return {};
      try { return JSON.parse(raw); } catch {
        const e = new Error("request_body_not_json"); e.named = true; throw e;
      }
    };
    const sendNotConnected = (codeName) => send(200, { status: "NOT_CONNECTED", code: codeName });
    try {
      const m = req.method ?? "GET";
      if (path === "/api/verify/citation/config" && m === "GET") { send(200, configInfo()); return true; }
      if (path === "/api/verify/citation/history" && m === "GET") {
        const raw = url.searchParams.get("limit");
        let limit = HISTORY_DEFAULT;
        if (raw !== null && raw !== "") { // §3.3 边界：缺省 20/≤0 或非整数 invalid_limit/>100 封顶 100
          const n = Number(raw);
          if (!Number.isInteger(n) || n <= 0) { sendNotConnected("invalid_limit"); return true; }
          limit = Math.min(n, HISTORY_CAP);
        }
        send(200, { status: "OWNER_RESPONSE", result: { items: store.cvListChecks(limit) } });
        return true;
      }
      if (path === "/api/verify/citation" && m === "POST") {
        let body;
        try { body = await readBodyJson(); } catch (e) {
          if (e.named) { sendNotConnected("request_body_not_json"); return true; }
          send(e.http ?? 500, { error: { message: e.message } }); return true;
        }
        const asOf = asOfOf(body);
        const r = runEngine("citation.verify", {
          citation: body?.citation, as_of: asOf, pack_dir: packDirOrNull(),
        });
        if (r.notConnected) { sendNotConnected(r.notConnected); return true; }
        const record = r.result;
        if (record && typeof record === "object" && "status" in record) {
          ledgerAppend([record], asOf);
          send(200, { status: "OWNER_RESPONSE", business_complete: false, result: record });
        } else {
          sendNotConnected("citation_engine_output_unreadable");
        }
        return true;
      }
      if (path === "/api/verify/document" && m === "POST") {
        let body;
        try { body = await readBodyJson(); } catch (e) {
          if (e.named) { sendNotConnected("request_body_not_json"); return true; }
          send(e.http ?? 500, { error: { message: e.message } }); return true;
        }
        const asOf = asOfOf(body);
        const r = runEngine("citation.verify_document", {
          text: body?.text, as_of: asOf, pack_dir: packDirOrNull(),
        });
        if (r.notConnected) { sendNotConnected(r.notConnected); return true; }
        const result = r.result;
        if (result && typeof result === "object" && Array.isArray(result.citations)) {
          ledgerAppend(result.citations, asOf);
          send(200, { status: "OWNER_RESPONSE", business_complete: false, result });
        } else {
          sendNotConnected("citation_engine_output_unreadable");
        }
        return true;
      }
      send(404, { status: "NOT_CONNECTED", code: "verify_route_not_found" });
      return true;
    } catch (e) {
      send(200, { status: "NOT_CONNECTED", code: "verify_internal_error" });
      return true;
    }
  }

  return { httpHandler, configInfo, runEngine };
}
