#!/usr/bin/env node
// S13：Flow 装配失败关闭。内核文件在 #22 之后已在树上，本探针不把「文件缺失」当成缺口。
// 桥启动只装配 FlowGate，并 import FLOW_ENGINE_DDL；createFlowEngineService 在入口抛可捕获的
// 「拒绝装配」（ERR_MODULE_NOT_FOUND）。拒绝发生在装配调用上，不在模块加载，也不把进程打死。
// 本探针不把装配器打开。
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const repo = fileURLToPath(new URL("../..", import.meta.url));
const KERNEL = [
  "packages/juscite-flow/src/index.mjs",
  "packages/juscite-flow/src/engine.mjs",
  "packages/juscite-flow/src/dsl.mjs",
];

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S13] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S13] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}

console.log(`[S13] tip probe repo=${repo}`);
for (const rel of KERNEL) {
  check(`kernel file present ${rel}`, existsSync(join(repo, rel)));
}

const flow = await import("../../packages/juscite-flow/src/index.mjs");
check("kernel exports createFlowEngine", typeof flow.createFlowEngine === "function");

const hostSrc = readFileSync(join(repo, "tools/bridge/bridge_host.mjs"), "utf8");
check(
  "bridge startup wires FlowGate only",
  hostSrc.includes("const flowGate = createFlowGate(store.db)") && !hostSrc.includes("createFlowEngineService"),
);

const childSource = `
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { FLOW_ENGINE_DDL, createFlowEngineService } from "./tools/bridge/flow_engine_service.mjs";
import { createFlowGate } from "./tools/bridge/flow_gate_service.mjs";

const dir = mkdtempSync(join(tmpdir(), "s13-flow-boot-"));
const db = new DatabaseSync(join(dir, "gate.db"));
db.exec("PRAGMA foreign_keys = ON");
db.exec(\`CREATE TABLE IF NOT EXISTS flow_nodes (
  id TEXT PRIMARY KEY, instance_code TEXT NOT NULL, node_code TEXT NOT NULL,
  node_type TEXT NOT NULL DEFAULT 'gate',
  status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','SUPERSEDED','SKIPPED')),
  assignee_user TEXT, lock_version INTEGER NOT NULL DEFAULT 1,
  payload_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)\`);
db.exec(\`CREATE TABLE IF NOT EXISTS flow_node_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('created','process','transfer','force_transfer')),
  action TEXT, actor_user TEXT NOT NULL, target_user TEXT, reason TEXT,
  from_version INTEGER NOT NULL, to_version INTEGER NOT NULL, created_at TEXT NOT NULL)\`);
db.exec(FLOW_ENGINE_DDL);
const gate = createFlowGate(db);
const created = gate.createNode({ instanceCode: "s13-synth", nodeCode: "gate.only", assigneeUser: "合成审批人" });
console.log("BOOT_OK " + created.node.status);
let refused = null;
try {
  const value = createFlowEngineService({ db, gate, trustDir: dir });
  refused = { threw: false, value: value ? "returned" : "empty" };
} catch (error) {
  refused = { threw: true, code: error?.code ?? "", message: String(error?.message ?? error) };
}
console.log("ASSEMBLE " + JSON.stringify(refused));
const again = gate.getNode(created.node.id);
console.log("GATE_STILL_UP " + again.node.status + " v" + again.node.lockVersion);
db.close();
rmSync(dir, { recursive: true, force: true });
`;

const child = spawnSync(
  process.execPath,
  ["--experimental-strip-types", "--input-type=module", "-e", childSource],
  { cwd: repo, encoding: "utf8", timeout: 30000 },
);
process.stdout.write(child.stdout ?? "");
process.stderr.write(child.stderr ?? "");
check("fresh process boots with FlowGate and exits 0", child.status === 0, `exit=${child.status} signal=${child.signal ?? ""}`);
const boot = child.stdout ?? "";
check("module import does not kill startup", /BOOT_OK PENDING/.test(boot), boot.trim().slice(0, 400));
const assembleLine = boot.split("\n").find((line) => line.startsWith("ASSEMBLE ")) ?? "";
let assemble = null;
try { assemble = JSON.parse(assembleLine.slice("ASSEMBLE ".length)); } catch { assemble = null; }
check(
  "assemble fail-closed 拒绝装配",
  assemble?.threw === true && assemble.code === "ERR_MODULE_NOT_FOUND" && assemble.message.includes("拒绝装配"),
  assembleLine,
);
check("refuse is on assemble, gate still serves", /GATE_STILL_UP PENDING v1/.test(boot), boot.trim().slice(-200));

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("[S13] createFlowEngineService 拒绝装配；FlowGate 启动路径仍活着");
console.log("RESULT pass");
