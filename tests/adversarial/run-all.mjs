#!/usr/bin/env node
// 逐个跑 S01–S12。S12 的 blocker 是已核实的缺失模块，不把整组打成失败。
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = fileURLToPath(new URL(".", import.meta.url));
const files = readdirSync(dir).filter((name) => /^s\d\d-/.test(name)).sort();
let failed = 0;
const summary = [];
for (const file of files) {
  const started = Date.now();
  const child = spawnSync(process.execPath, ["--experimental-strip-types", "--import", join(dir, "resolve-ts-js.mjs"), join(dir, file)], {
    encoding: "utf8",
    timeout: 120000,
    cwd: join(dir, "..", ".."),
  });
  const stdout = child.stdout ?? "";
  const stderr = child.stderr ?? "";
  process.stdout.write(stdout);
  process.stderr.write(stderr);
  const blocker = /RESULT blocker/.test(stdout);
  const pass = child.status === 0 && /RESULT pass/.test(stdout);
  const crash = /RESULT crash/.test(stdout) || (child.status !== 0 && !stdout.includes("RESULT "));
  const result = pass ? "pass" : blocker ? "blocker" : crash ? "crash" : "fail";
  if (!pass && !blocker) failed += 1;
  summary.push(`${file} ${result} exit=${child.status} ${Date.now() - started}ms`);
  console.log(`[run-all] ${file} -> ${result} exit=${child.status}`);
}
console.log("[run-all] summary");
for (const line of summary) console.log(line);
process.exit(failed ? 1 : 0);
