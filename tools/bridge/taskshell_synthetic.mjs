#!/usr/bin/env node
// 【施工单-06·机制规格-02】桥内通用异步任务壳合成自测（ci_gate fast 随行步）。
// 全合成材料：内存流程不落盘，库=临时目录 node:sqlite，产物=临时目录；零 %APPDATA% 触碰。
// 覆盖规格验收断言：A1 全路径 / A2 软超时语义的桥内半边（终态即原因）/ A3 惰性过期 /
// A4 重启扫尾+重试 / A6 并发建任务独立；另覆盖取消两态与白名单取件。
// 纯 Node 零依赖；单命令 exit 0/1，末行 TASKSHELL_SYNTH_PASS 可判。
// 用法：node tools/bridge/taskshell_synthetic.mjs
import { mkdtempSync, writeFileSync, readFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";

const dir = mkdtempSync(join(tmpdir(), "juscite-taskshell-synth-"));
let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[taskshell-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[taskshell-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }

// 与 bridge_store.mjs 0014_async_tasks 同构的建表（测试自持，不依赖宿主迁移器）
function freshDb(file) {
  const db = new DatabaseSync(file);
  db.exec(`CREATE TABLE IF NOT EXISTS async_tasks (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, ref TEXT,
    status TEXT NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','EXPIRED')),
    payload_json TEXT NOT NULL DEFAULT '{}', result_ref TEXT, file_name TEXT,
    error_code TEXT, error_message TEXT, retry_count INTEGER NOT NULL DEFAULT 0,
    artifact_ttl INTEGER, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT)`);
  return db;
}
const { createTaskShell, TaskShellError } = await import("./taskshell_service.mjs");

function waitFor(fn, ms = 5000, step = 20) {
  return new Promise((res, rej) => {
    const t0 = Date.now();
    (function poll() {
      try { if (fn()) return res(true); } catch { /* 条件未到 */ }
      if (Date.now() - t0 > ms) return rej(new Error("waitFor 超时"));
      setTimeout(poll, step);
    })();
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 用例 1（A1）：QUEUED→RUNNING→SUCCEEDED 取件成功，result_ref 白名单形状 ──
{
  const db = freshDb(join(dir, "t1.db"));
  const artifactsDir = join(dir, "art1");
  const shell = createTaskShell(db, { artifactsDir, sweepOnBoot: false });
  shell.register("echo", async (ctx) => {
    writeFileSync(join(ctx.artifactDir, "out.txt"), "合成产物", "utf-8");
    return { fileName: "out.txt" };
  });
  const t = shell.create("echo", { hello: "world" });
  if (t.status !== "QUEUED" && t.status !== "RUNNING") fail(1, "建任务初态异常", t.status);
  const done = await waitFor(() => shell.get(t.id).status === "SUCCEEDED");
  const g = shell.get(t.id);
  const p = shell.artifactPath(t.id);
  if (done && g.resultRef === `tasks/${t.id}/out.txt` && g.fileName === "out.txt"
    && p.fileName === "out.txt" && existsSync(p.path)
    && readText(p.path) === "合成产物") ok(1, "全路径 SUCCEEDED+取件", g.resultRef);
  else fail(1, "全路径断言不过", JSON.stringify(g));
}

// ── 用例 2（R6/A1）：FAILED 带 errorMessage；仅 FAILED 可重试；retry_count 留痕 ──
{
  const db = freshDb(join(dir, "t2.db"));
  const shell = createTaskShell(db, { artifactsDir: join(dir, "art2"), sweepOnBoot: false });
  let flips = 0;
  shell.register("flaky", async () => {
    flips += 1;
    if (flips === 1) throw new Error("合成解析失败：第 3 页乱码");
    return { fileName: null };
  });
  const t = shell.create("flaky");
  await waitFor(() => shell.get(t.id).status === "FAILED");
  const g1 = shell.get(t.id);
  let threw = null;
  try { shell.artifactPath(t.id); } catch (e) { threw = e; }
  let retryOther = null;
  try { shell.retry("fgt_unknown"); } catch (e) { retryOther = e.code; }
  const t2 = shell.retry(t.id);
  await waitFor(() => shell.get(t.id).status === "SUCCEEDED");
  const g2 = shell.get(t.id);
  if (g1.errorCode === "RUNNER_ERROR" && g1.errorMessage?.includes("第 3 页乱码")
    && threw?.code === "INVALID_STATE" && retryOther === "NOT_FOUND"
    && g2.retryCount === 1 && g2.status === "SUCCEEDED") ok(2, "终态即原因+仅FAILED可重试+次数留痕");
  else fail(2, "重试语义不过", JSON.stringify({ g1, g2, retryOther }));
}

// ── 用例 3（R6）：QUEUED 取消=直接终态不执行 runner；RUNNING 取消=checkpoint 协作收口 ──
{
  const db = freshDb(join(dir, "t3.db"));
  const shell = createTaskShell(db, { artifactsDir: join(dir, "art3"), sweepOnBoot: false });
  let ran = 0;
  shell.register("never", async () => { ran += 1; return {}; });
  const tq = shell.create("never");
  const cq = shell.cancel(tq.id);   // setImmediate 起跑前的排队窗口
  await sleep(60);
  if (cq.status === "CANCELLED" && ran === 0) ok("3a", "排队即取消→runner 未执行");
  else fail("3a", "排队取消语义不过", JSON.stringify({ cq, ran }));

  shell.register("slow", async (ctx) => {
    for (let i = 0; i < 200; i++) { ctx.checkpoint(); await sleep(20); }
    return {};
  });
  const tr = shell.create("slow");
  await waitFor(() => shell.get(tr.id).status === "RUNNING");
  shell.cancel(tr.id);
  const done = await waitFor(() => shell.get(tr.id).status === "CANCELLED", 8000);
  if (done) ok("3b", "运行中取消→checkpoint 协作收口 CANCELLED");
  else fail("3b", "运行中取消未收口");
}

// ── 用例 4（A3）：TTL 过后读取惰性翻 EXPIRED+删产物；EXPIRED 不可 retry 须新建 ──
{
  const db = freshDb(join(dir, "t4.db"));
  const artifactsDir = join(dir, "art4");
  const shell = createTaskShell(db, { artifactsDir, sweepOnBoot: false });
  shell.register("quick", async (ctx) => {
    writeFileSync(join(ctx.artifactDir, "a.json"), "{}", "utf-8");
    return { fileName: "a.json" };
  });
  const t = shell.create("quick", {}, { ttlSeconds: 0 });
  await sleep(300);   // 等 runner 落完产物（TTL=0 时 SUCCEEDED 读即翻 EXPIRED，不可观测是服务语义）
  const file = join(artifactsDir, "tasks", t.id, "a.json");
  if (!existsSync(file)) { fail(4, "产物未落盘（前置破坏）"); }
  const g = shell.get(t.id);   // TTL=0 → 读取即翻 EXPIRED
  let artErr = null, retryErr = null;
  try { shell.artifactPath(t.id); } catch (e) { artErr = e; }
  try { shell.retry(t.id); } catch (e) { retryErr = e.code; }
  if (g.status === "EXPIRED" && !existsSync(file)
    && artErr?.code === "INVALID_STATE" && retryErr === "INVALID_STATE") ok(4, "惰性过期+产物清理+重试拒绝");
  else fail(4, "过期语义不过", JSON.stringify({ g, artErr: artErr?.code, retryErr }));
}

// ── 用例 5（A4）：崩溃扫尾——A 壳遗留 RUNNING，B 壳构造即 FAILED(BRIDGE_RESTART) 可重试 ──
{
  const dbPath = join(dir, "t5.db");
  const dbA = freshDb(dbPath);
  const shellA = createTaskShell(dbA, { artifactsDir: join(dir, "art5"), sweepOnBoot: false });
  let release = () => {};
  const gate = new Promise((res) => { release = res; });
  shellA.register("hang", async (ctx) => { while (!gateSettled()) { ctx.checkpoint(); await sleep(20); } return {}; });
  let settled = false;
  const gateSettled = () => settled;
  const t = shellA.create("hang");
  await waitFor(() => shellA.get(t.id).status === "RUNNING");

  const dbB = new DatabaseSync(dbPath);
  const shellB = createTaskShell(dbB, { artifactsDir: join(dir, "art5") });   // sweepOnBoot 默认 true
  const swept = shellB.get(t.id);
  shellB.register("hang", async () => ({ fileName: null }));
  const t2 = shellB.retry(t.id);
  await waitFor(() => shellB.get(t.id).status === "SUCCEEDED");
  settled = true; release();
  if (swept.status === "FAILED" && swept.errorCode === "BRIDGE_RESTART"
    && swept.errorMessage?.includes("可重试") && shellB.get(t.id).status === "SUCCEEDED") ok(5, "重启扫尾→FAILED 可重试→复跑成功");
  else fail(5, "扫尾语义不过", JSON.stringify({ swept }));
}

// ── 用例 6：NOT_FOUND 三连 + 未注册 kind + 终态不可再取消（INVALID_STATE） ──
{
  const db = freshDb(join(dir, "t6.db"));
  const shell = createTaskShell(db, { artifactsDir: join(dir, "art6"), sweepOnBoot: false });
  shell.register("noop", async () => ({}));
  const codes = [];
  for (const f of [(id) => shell.get(id), (id) => shell.cancel(id), (id) => shell.retry(id), (id) => shell.artifactPath(id)]) {
    try { f("fgt_nope"); } catch (e) { codes.push(e.code); }
  }
  let kindErr = null, stateErr = null;
  try { shell.create("ghost"); } catch (e) { kindErr = e.code; }
  const t = shell.create("noop");
  await waitFor(() => shell.get(t.id).status === "SUCCEEDED");
  try { shell.cancel(t.id); } catch (e) { stateErr = e.code; }
  if (codes.filter((c) => c === "NOT_FOUND").length === 4 && kindErr === "VALIDATION" && stateErr === "INVALID_STATE")
    ok(6, "NOT_FOUND×4+未注册 kind 拒+终态取消拒");
  else fail(6, "错误面不过", JSON.stringify({ codes, kindErr, stateErr }));
}

// ── 用例 7（A6）：同 kind 同 payload 两次 POST=两个独立任务不合并不去重 ──
{
  const db = freshDb(join(dir, "t7.db"));
  const shell = createTaskShell(db, { artifactsDir: join(dir, "art7"), sweepOnBoot: false });
  shell.register("noop", async () => ({}));
  const a = shell.create("noop", { same: 1 });
  const b = shell.create("noop", { same: 1 });
  await waitFor(() => shell.get(a.id).status === "SUCCEEDED" && shell.get(b.id).status === "SUCCEEDED");
  if (a.id !== b.id && shell.list().length >= 2) ok(7, "独立建任务不去重");
  else fail(7, "去重了（违反 A6）");
}

function readText(p) { return readFileSync(p, "utf-8"); }

console.log(`[taskshell-synth] ── ${passed} OK / ${failed} FAIL ──`);
if (failed > 0) { console.error("TASKSHELL_SYNTH_FAIL"); process.exit(1); }
console.log("TASKSHELL_SYNTH_PASS");
