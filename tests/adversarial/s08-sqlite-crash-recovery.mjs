#!/usr/bin/env node
// S08 合成材料：写到一半进程退出后重启，不得留下 status/phase/state = running 的僵尸任务或行。
import { register } from "node:module";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

await register(new URL("./resolve-ts-js.mjs", import.meta.url), import.meta.url);

const home = mkdtempSync(join(tmpdir(), "r3-s08-"));
process.env.HOME = home;
process.env.USERPROFILE = home;
delete process.env.APPDATA;

const PORT = 45192;
const { openBridgeStore } = await import("../../tools/bridge/bridge_store.mjs");

function insertZombies(db) {
  const now = "2026-01-01T00:00:00.000Z";
  db.prepare(`INSERT INTO async_tasks (id, kind, status, payload_json, retry_count, created_at)
    VALUES ('synth-async', 'noop', 'RUNNING', '{}', 0, ?)`).run(now);
  db.prepare(`INSERT INTO async_tasks (id, kind, status, payload_json, retry_count, created_at, finished_at)
    VALUES ('synth-async-ok', 'noop', 'SUCCEEDED', '{}', 0, ?, ?)`).run(now, now);
  db.prepare(`INSERT INTO research_records (id, status, query, record_json, updated_at)
    VALUES ('synth-research', 'running', '合成课题', ?, 1)`).run(JSON.stringify({ id: "synth-research", status: "running", query: "合成课题" }));
  db.prepare(`INSERT INTO session_rows (workspace_key, session_id, row_seq, kind, state, text, row_json)
    VALUES ('wk', 'ses-synth', 1, 'assistantText', 'streaming', '合成半句', ?)`).run(JSON.stringify({ state: "streaming", text: "合成半句" }));
  db.prepare(`INSERT INTO sessions (workspace_key, session_id, title, phase, busy, created_at, updated_at)
    VALUES ('wk', 'ses-synth', '合成会话', 'running', 1, 1, 1)`).run();
  db.prepare(`INSERT INTO edisc_tasks (workspace_key, task_id, case_id, status, created_at, updated_at)
    VALUES ('wk', 'etask-synth', 'case-synth', 'running', ?, ?)`).run(now, now);
  db.prepare(`INSERT INTO flow_runs (id, definition_id, definition_hash, status, created_at)
    VALUES ('run-synth', 'def-synth', 'hash', 'RUNNING', ?)`).run(now);
}

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S08] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S08] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}

{
  const store = openBridgeStore(PORT);
  insertZombies(store.db);
  store.db.close();
  const again = openBridgeStore(PORT);
  const db = again.db;
  const runningAsync = db.prepare("SELECT COUNT(*) AS n FROM async_tasks WHERE status IN ('QUEUED','RUNNING')").get().n;
  const okAsync = db.prepare("SELECT status, error_code FROM async_tasks WHERE id = 'synth-async'").get();
  const kept = db.prepare("SELECT status FROM async_tasks WHERE id = 'synth-async-ok'").get();
  const research = db.prepare("SELECT status, record_json FROM research_records WHERE id = 'synth-research'").get();
  const row = db.prepare("SELECT state, row_json FROM session_rows WHERE session_id = 'ses-synth'").get();
  const session = db.prepare("SELECT phase, busy FROM sessions WHERE session_id = 'ses-synth'").get();
  const edisc = db.prepare("SELECT status FROM edisc_tasks WHERE task_id = 'etask-synth'").get();
  const flow = db.prepare("SELECT status FROM flow_runs WHERE id = 'run-synth'").get();
  let researchDoc = {};
  try { researchDoc = JSON.parse(research.record_json); } catch { researchDoc = {}; }
  let rowDoc = {};
  try { rowDoc = JSON.parse(row.row_json); } catch { rowDoc = {}; }
  check("no running async", runningAsync === 0, String(runningAsync));
  check("async marked restart-failed", okAsync.status === "FAILED" && okAsync.error_code === "BRIDGE_RESTART", JSON.stringify(okAsync));
  check("succeeded kept", kept.status === "SUCCEEDED", JSON.stringify(kept));
  check("research not running", research.status !== "running" && researchDoc.status !== "running", JSON.stringify(research));
  check("row not streaming", row.state !== "streaming" && row.state !== "running" && rowDoc.state !== "streaming" && rowDoc.state !== "running", JSON.stringify(row));
  check("session not running", session.phase !== "running" && session.busy === 0, JSON.stringify(session));
  check("edisc task not running", edisc.status !== "running", JSON.stringify(edisc));
  check("flow run not running", flow.status !== "RUNNING" && flow.status !== "QUEUED", JSON.stringify(flow));
  again.db.close();
}

{
  const store = openBridgeStore(PORT + 1);
  store.db.exec("BEGIN IMMEDIATE");
  store.db.prepare(`INSERT INTO async_tasks (id, kind, status, payload_json, retry_count, created_at)
    VALUES ('synth-uncommitted', 'noop', 'RUNNING', '{}', 0, '2026-01-01T00:00:00.000Z')`).run();
  store.db.close();
  const again = openBridgeStore(PORT + 1);
  const row = again.db.prepare("SELECT status FROM async_tasks WHERE id = 'synth-uncommitted'").get();
  check("killed mid-write leaves no running row", !row || row.status !== "RUNNING", JSON.stringify(row));
  again.db.close();
}

rmSync(home, { recursive: true, force: true });
if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("RESULT pass");
