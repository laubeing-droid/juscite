#!/usr/bin/env node
// S05 合成材料：同一任务 id 并发提交两次，第二次必须被拒绝，且库内只有一行。
import { DatabaseSync } from "node:sqlite";
import { createTaskShell, TaskShellError } from "../../tools/bridge/taskshell_service.mjs";

const db = new DatabaseSync(":memory:");
db.exec(`CREATE TABLE IF NOT EXISTS async_tasks (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, ref TEXT,
  status TEXT NOT NULL DEFAULT 'QUEUED' CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED','EXPIRED')),
  payload_json TEXT NOT NULL DEFAULT '{}', result_ref TEXT, file_name TEXT,
  error_code TEXT, error_message TEXT, retry_count INTEGER NOT NULL DEFAULT 0,
  artifact_ttl INTEGER, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT)`);

const shell = createTaskShell(db, { sweepOnBoot: false });
shell.register("noop", async () => ({}));

const id = "synth-task-dup";
const results = await Promise.all([
  Promise.resolve().then(() => {
    try {
      return { ok: true, task: shell.create("noop", { n: 1 }, { id }) };
    } catch (error) {
      return { ok: false, error };
    }
  }),
  Promise.resolve().then(() => {
    try {
      return { ok: true, task: shell.create("noop", { n: 1 }, { id }) };
    } catch (error) {
      return { ok: false, error };
    }
  }),
]);

const accepted = results.filter((r) => r.ok);
const rejected = results.filter((r) => !r.ok);
const rows = db.prepare("SELECT id, status FROM async_tasks WHERE id = ?").all(id);
const rejectedTyped = rejected.every((r) => r.error instanceof TaskShellError && r.error.code === "DUPLICATE");

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S05] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S05] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}

check("one accepted", accepted.length === 1, JSON.stringify(results.map((r) => (r.ok ? r.task.id : r.error?.code ?? String(r.error)))));
check("second rejected as DUPLICATE", rejected.length === 1 && rejectedTyped, rejected.map((r) => `${r.error?.code}:${r.error?.message}`).join(";"));
check("single row", rows.length === 1 && rows[0].id === id, JSON.stringify(rows));

const distinct = [shell.create("noop", { n: 2 }), shell.create("noop", { n: 2 })];
check("without id still distinct", distinct[0].id !== distinct[1].id);

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("RESULT pass");
