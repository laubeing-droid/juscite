#!/usr/bin/env node
// 逐个跑 tests/adversarial/sNN-*.mjs（含 S13–S15）。blocker 只跳过该文件，其余失败把整组打成失败。
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const dir = fileURLToPath(new URL(".", import.meta.url));
const files = readdirSync(dir).filter((name) => /^s\d\d-/.test(name)).sort();
let failed = 0;
const summary = [];
for (const file of files) {
  const started = Date.now();
  // Windows 绝对路径（D:\...）会被 ESM loader 当成 "d:" 协议 URL 拒载（ERR_UNSUPPORTED_ESM_URL_SCHEME）；
  // --import 必须给 file:// URL，位置参数脚本路径两种系统都接受原路径。
  const child = spawnSync(process.execPath, ["--experimental-strip-types", "--import", pathToFileURL(join(dir, "resolve-ts-js.mjs")).href, join(dir, file)], {
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
