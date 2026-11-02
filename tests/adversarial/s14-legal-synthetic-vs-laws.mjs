#!/usr/bin/env node
// S14：GET /api/legal 是工作台合成桩，GET /api/legal/laws* 是法条手册面。
// 合成桩可以带 valid:"valid"，但没有法条记录身份字段，不得当成法条手册真源（非权威源）。
// 本探针不撤 /api/legal。夹具是临时合成包，不起完整桌面。
import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import http from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { fileURLToPath } from "node:url";

const repo = fileURLToPath(new URL("../..", import.meta.url));
const hostPath = join(repo, "tools/bridge/bridge_host.mjs");

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S14] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S14] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}

function liveLegalStub(source) {
  const marker = 'if (req.url === "/api/legal")';
  const at = source.indexOf(marker);
  if (at < 0) throw new Error("bridge_host 缺少精确路由 /api/legal");
  const call = source.indexOf("JSON.stringify(", at);
  const end = source.indexOf("}));", call);
  if (call < 0 || end < 0) throw new Error("无法从 bridge_host 抽出 /api/legal 合成桩");
  const literal = source.slice(call + "JSON.stringify(".length, end + 1);
  return new Function(`return (${literal});`)();
}

function isLawbookRecord(row) {
  return Boolean(row)
    && typeof row.id === "string"
    && typeof row.name === "string"
    && typeof row.level === "string"
    && typeof row.effect === "string"
    && typeof row.effectLabel === "string";
}

function acceptAsLawbook(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) return false;
  if (typeof body.available === "boolean" && Array.isArray(body.packs) && typeof body.total === "number") return true;
  if (typeof body.mode === "string" && typeof body.count === "number" && Array.isArray(body.results) && body.results.every(isLawbookRecord)) return true;
  if (body.law && isLawbookRecord(body.law)) return true;
  return false;
}

function keysOf(value, out = new Set()) {
  if (Array.isArray(value)) {
    for (const item of value) keysOf(item, out);
    return out;
  }
  if (value && typeof value === "object") {
    for (const [key, inner] of Object.entries(value)) {
      out.add(key);
      keysOf(inner, out);
    }
  }
  return out;
}

const LAWS_IDENTITY = ["level", "effect", "effectLabel", "categoryId"];
const WORKBENCH = ["materials", "review", "citations", "schedule", "calc", "documents"];

const hostSrc = readFileSync(hostPath, "utf8");
check("route /api/legal still in bridge_host", hostSrc.includes('if (req.url === "/api/legal")'));
check("laws route still separate", hostSrc.includes('req.url?.startsWith("/api/legal/laws")'));

let synthetic;
try {
  synthetic = liveLegalStub(hostSrc);
  check("extracted live /api/legal stub", Array.isArray(synthetic?.materials));
} catch (error) {
  check("extracted live /api/legal stub", false, String(error));
  synthetic = null;
}

const dir = mkdtempSync(join(tmpdir(), "s14-legal-"));
const packDir = join(dir, "alpha");
mkdirSync(join(packDir, "content"), { recursive: true });
const md = [
  "# 合成测试法",
  "",
  "（合成机关 二〇二六年制定）",
  "制定机关 合成常委会",
  "<!-- INFO END -->",
  "## 第一编 总则",
  "",
  "第一条 合成测试法第一条正文，含合成墨线词。",
  "",
].join("\n");
writeFileSync(join(packDir, "content", "合成测试法.md"), md, "utf8");
const dbPath = join(packDir, "pack.sqlite3");
const packDb = new DatabaseSync(dbPath);
packDb.exec(`CREATE TABLE law (id TEXT PRIMARY KEY, name TEXT NOT NULL, subtitle TEXT, level TEXT NOT NULL,
  category_id TEXT, publish TEXT, valid_from TEXT DEFAULT '', valid_to TEXT DEFAULT '2099-12-31',
  ver INTEGER NOT NULL DEFAULT 1, tags TEXT NOT NULL DEFAULT '[]', filename TEXT NOT NULL, order_num INTEGER NOT NULL DEFAULT 0);
  CREATE TABLE category (id TEXT PRIMARY KEY, name TEXT NOT NULL, folder TEXT, is_subfolder INTEGER NOT NULL DEFAULT 0,
  "group" TEXT, sort_order INTEGER NOT NULL DEFAULT 0);`);
packDb.prepare('INSERT INTO category VALUES (?,?,?,?,?,?)').run(
  "caaa0000000000000000000000000ca1", "测试民法", "测试民法", 1, "测试组块", 1,
);
packDb.prepare("INSERT INTO law VALUES (?,?,?,?,?,?,?,?,?,?,?,?)").run(
  "a00000000000000000000000000000a1", "合成测试法", null, "法律",
  "caaa0000000000000000000000000ca1", "2020-01-01", "2020-03-01", "2099-12-31",
  1, "[]", "合成测试法.md", 0,
);
packDb.close();
const buf = readFileSync(dbPath);
writeFileSync(join(packDir, "pack.meta"), JSON.stringify({
  name: "alpha",
  hash: createHash("sha256").update(buf).digest("hex"),
  update: 1,
  filesize: buf.length,
}), "utf8");

process.env.BRIDGE_LAWBOOK_PACK_ROOT = dir;
const { createLawbookService } = await import("../../tools/bridge/lawbook_service.mjs");
const lawbook = createLawbookService({ workspaceKey: "s14-synth", store: {} });

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", "http://127.0.0.1");
  if (req.url === "/api/legal") {
    res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify(synthetic));
    return;
  }
  if (url.pathname.startsWith("/api/legal/laws") || url.pathname.startsWith("/api/legal/packs")) {
    const handled = await lawbook.httpHandler(req, res, url);
    if (handled) return;
  }
  res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
  res.end("s14 harness");
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const { port } = server.address();

async function get(path) {
  const res = await fetch(`http://127.0.0.1:${port}${path}`);
  const text = await res.text();
  let body = null;
  try { body = JSON.parse(text); } catch { body = text; }
  return { status: res.status, body };
}

try {
  const legal = await get("/api/legal");
  const status = await get("/api/legal/laws/status");
  const found = await get("/api/legal/laws?query=" + encodeURIComponent("合成测试法") + "&mode=title");
  const cited = await get("/api/legal/laws?query=" + encodeURIComponent("民法典") + "&mode=title");
  console.log(`[S14] GET /api/legal status=${legal.status} keys=${legal.body && typeof legal.body === "object" ? Object.keys(legal.body).join(",") : typeof legal.body}`);
  console.log(`[S14] GET /api/legal/laws/status status=${status.status} available=${status.body?.available} total=${status.body?.total}`);
  console.log(`[S14] GET /api/legal/laws?query=合成测试法 count=${found.body?.count} sample=${JSON.stringify(found.body?.results?.[0] ?? null)}`);
  console.log(`[S14] GET /api/legal/laws?query=民法典 count=${cited.body?.count}`);

  check("route /api/legal kept", legal.status === 200, String(legal.status));
  check(
    "stub is workbench shape",
    legal.status === 200 && WORKBENCH.every((key) => Array.isArray(legal.body?.[key])),
    JSON.stringify(legal.body)?.slice(0, 240),
  );
  const stubKeys = synthetic ? keysOf(synthetic) : new Set();
  check(
    "stub has no lawbook identity fields",
    LAWS_IDENTITY.every((key) => !stubKeys.has(key)),
    [...stubKeys].sort().join(","),
  );
  const markedValid = Array.isArray(legal.body?.citations) ? legal.body.citations.filter((row) => row?.valid === "valid") : [];
  const syntheticNames = Array.isArray(legal.body?.materials) && legal.body.materials.every((row) => String(row?.name ?? "").startsWith("合成："));
  check("stub materials carry 合成 marker", syntheticNames === true, JSON.stringify(legal.body?.materials?.[0] ?? null));
  check(
    "非权威源",
    legal.status === 200
      && !acceptAsLawbook(legal.body)
      && markedValid.length > 0
      && markedValid.every((row) => !isLawbookRecord(row)),
    JSON.stringify(markedValid[0] ?? null),
  );
  check(
    "laws status is lawbook surface",
    status.status === 200 && acceptAsLawbook(status.body) && status.body.available === true && status.body.total === 1,
    JSON.stringify(status.body)?.slice(0, 300),
  );
  check(
    "laws search returns lawbook records",
    found.status === 200 && acceptAsLawbook(found.body) && found.body.count === 1 && isLawbookRecord(found.body.results[0]) && found.body.results[0].name === "合成测试法",
    JSON.stringify(found.body)?.slice(0, 300),
  );
  check(
    "stub citation is not a laws hit",
    cited.status === 200 && cited.body?.count === 0 && !acceptAsLawbook(legal.body),
    JSON.stringify(cited.body),
  );
  check(
    "laws path is not served the stub",
    status.body && !WORKBENCH.some((key) => key in status.body),
    Object.keys(status.body ?? {}).join(","),
  );
} finally {
  await new Promise((resolve) => server.close(resolve));
  rmSync(dir, { recursive: true, force: true });
}

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("[S14] /api/legal 合成桩是非权威源；/api/legal/laws* 仍是法条手册面，路由未撤");
console.log("RESULT pass");
