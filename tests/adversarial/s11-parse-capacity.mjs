#!/usr/bin/env node
// S11 合成材料：用 Buffer 分配超过 150MB 的表，解析上限必须立刻生效，不能在进程内展开整表。
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

if (process.argv.includes("--probe")) {
  const { parseCsvTable } = await import("../../packages/juscite-edisc/src/tableKernel.ts");
  const big = Buffer.alloc(150 * 1024 * 1024 + 1);
  const started = Date.now();
  try {
    const tables = parseCsvTable(big, "synth-oversize");
    console.log(`NO_LIMIT rows=${tables?.[0]?.rows?.length ?? "?"} ms=${Date.now() - started}`);
    process.exit(2);
  } catch (error) {
    console.log(`CODE ${error?.code ?? ""}`);
    console.log(`MS ${Date.now() - started}`);
    console.log(String(error?.message ?? error).slice(0, 200));
    process.exit(error?.code === "PAYLOAD_TOO_LARGE" ? 0 : 3);
  }
}

const child = spawn(process.execPath, ["--experimental-strip-types", fileURLToPath(import.meta.url), "--probe"], {
  cwd: fileURLToPath(new URL("../..", import.meta.url)),
  timeout: 8000,
});
let stdout = "";
let stderr = "";
child.stdout.on("data", (chunk) => { stdout += chunk; });
child.stderr.on("data", (chunk) => { stderr += chunk; });
const exitCode = await new Promise((resolve) => {
  child.on("exit", (code, signal) => resolve(signal ? `signal:${signal}` : code));
});

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S11] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S11] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}

check("oversize rejected by payload limit", exitCode === 0 && stdout.includes("CODE PAYLOAD_TOO_LARGE"), `exit=${exitCode} out=${stdout} err=${stderr.slice(0, 300)}`);
const ms = Number((stdout.match(/MS (\d+)/) ?? [])[1] ?? 99999);
check("rejection is bounded", Number.isFinite(ms) && ms < 3000, String(ms));

const { parseCsvTable } = await import("../../packages/juscite-edisc/src/tableKernel.ts");
const small = parseCsvTable("列甲,列乙\n合成,1\n", "synth-small");
check("small table still parses", small[0]?.rows?.length === 2 && small[0].rows[1].cells[0] === "合成", JSON.stringify(small));

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("RESULT pass");
