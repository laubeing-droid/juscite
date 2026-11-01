#!/usr/bin/env node
// 【桥·增强三式·式三】真 CLI 路径演练（2026-10-30 真模型轮施工单）：
// 真机 codex CLI（codex-cli 0.155.0，hermes npm 布局 .cmd 包装，%dp0% 变量形态）
// → PATH 发现 → shim 解析 → node 直跑分派 → --version 探活（UNKNOWN-2 兜底）。
// 边界：只解析+探活，不向 codex 投递任何提示词（不触用户 codex 会话/配额/登录）；
// 长提示词字节无损由 cli_shim_synthetic 用例②合成覆盖——此边界如实标注。
// 用法：node tools/bridge/cli_shim_real_drill.mjs  末行 CLI_SHIM_REAL_DRILL_PASS 可判。
import { findCliExecutable, probeCliVersion, resolveCliCommand } from "./cli_shim.mjs";

const found = findCliExecutable("codex");
console.log("[real-drill] 发现(PATH):", found);
const resolved = resolveCliCommand("codex", { explicitPath: found });
console.log("[real-drill] 解析:", JSON.stringify({
  origin: resolved.origin,
  command: resolved.command,
  argsPrefix: resolved.argsPrefix,
  targetPath: resolved.targetPath,
  droppedInterpreter: resolved.droppedInterpreter,
  droppedSecondary: resolved.droppedSecondary ?? [],
}));
if (resolved.origin !== "shim-node" || !/\.js$/i.test(resolved.targetPath)) {
  console.error("[real-drill] 分派形态不符：期望 shim-node+js 入口");
  console.log("CLI_SHIM_REAL_DRILL_FAIL");
  process.exit(1);
}
const probe = probeCliVersion(resolved);
console.log("[real-drill] --version 探活:", JSON.stringify(probe));
const pass = probe.ok && probe.stdout.length > 0;
console.log(pass ? "CLI_SHIM_REAL_DRILL_PASS" : "CLI_SHIM_REAL_DRILL_FAIL");
process.exit(pass ? 0 : 1);
