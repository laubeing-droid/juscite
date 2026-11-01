#!/usr/bin/env node
// S12：Flow 预算。先核实 engine.mjs / dsl.mjs 是否在当前分支尖存在。
// 缺失时不发明整套引擎，只留下路径证据。
import { existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../..", import.meta.url));
const relative = [
  "packages/juscite-flow/src/engine.mjs",
  "packages/juscite-flow/src/dsl.mjs",
  "packages/juscite-flow/src/index.mjs",
];
const missing = relative.filter((rel) => !existsSync(join(root, rel)));
console.log(`[S12] root ${root}`);
for (const rel of relative) console.log(`[S12] ${existsSync(join(root, rel)) ? "present" : "MISSING"} ${rel}`);

if (missing.length === 0) {
  console.error("[S12] engine files exist; this probe expected the documented gap and does not invent a budget run");
  console.log("RESULT fail");
  process.exit(1);
}

let importCode = "";
try {
  await import("../../packages/juscite-flow/src/engine.mjs");
  importCode = "loaded";
} catch (error) {
  importCode = error?.code ?? "error";
  console.log(`[S12] import engine.mjs -> ${importCode} ${String(error?.message ?? error).split("\n")[0]}`);
}
let dslCode = "";
try {
  await import("../../packages/juscite-flow/src/dsl.mjs");
  dslCode = "loaded";
} catch (error) {
  dslCode = error?.code ?? "error";
  console.log(`[S12] import dsl.mjs -> ${dslCode} ${String(error?.message ?? error).split("\n")[0]}`);
}

if (importCode !== "ERR_MODULE_NOT_FOUND" || dslCode !== "ERR_MODULE_NOT_FOUND") {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("S12_BLOCKER_EVIDENCE missing engine.mjs dsl.mjs index.mjs; over-budget pipeline not runnable without inventing the engine");
console.log("RESULT blocker");
