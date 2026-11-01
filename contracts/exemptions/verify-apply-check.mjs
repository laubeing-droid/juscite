// r12 波4 · 豁免集 apply --check 验证（设计 §五 ci_gate upgrade 模式第①步的可复跑实现）。
// 语义：contracts/exemptions/*.patch 每一个都必须能干净打在基线树（3.16.2 原版）上——
// 在临时 index 上 read-tree 基线后逐个 git apply --cached --check，不触碰工作树。
// 用法：node contracts/exemptions/verify-apply-check.mjs
//   基线可用 env JUSCITE_EXEMPT_BASE 覆盖（默认 3.16.2 = 3c5b2276…，即 upstream/main）。
//   基线对象不存在时先：git fetch upstream main（见 manifest.json meta.baseline）。
// 单命令 exit 0/1 可判；末行 APPLY_CHECK_PASS / APPLY_CHECK_FAIL。
import { spawnSync } from "node:child_process";
import { readdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const EXEMPT_DIR = fileURLToPath(new URL("./", import.meta.url));
const REPO_ROOT = resolve(EXEMPT_DIR, "../.."); // contracts/exemptions/ → 仓库根（m1-u01）
const BASE = process.env.JUSCITE_EXEMPT_BASE || "3c5b227649371507ddc4eb46ac5133afe6db1cab";

function git(args, env = {}) {
  return spawnSync("git", args, { cwd: REPO_ROOT, encoding: "utf-8", env: { ...process.env, ...env } });
}

// 1) 基线对象在位检查（未 fetch 时给出明确指引，而非含糊失败）。
const probe = git(["cat-file", "-t", BASE]);
if (probe.status !== 0 || probe.stdout.trim() !== "commit") {
  console.error(`[apply-check] 基线对象不可达：${BASE}\n` +
    "  先挂上游并取基线：git remote add upstream https://github.com/zai-org/ZCode.git\n" +
    "  以及（shallow 即可）：git fetch --depth=1 upstream main");
  process.exit(1);
}

// 2) 临时 index 载入基线树（不触碰工作树；index 文件放系统临时目录，用完即删）。
const indexFile = join(tmpdir(), "juscite-exempt-check-index");
rmSync(indexFile, { force: true });
const treeArgs = ["read-tree", `${BASE}^{tree}`];
const readTree = git(treeArgs, { GIT_INDEX_FILE: indexFile });
if (readTree.status !== 0) {
  console.error(`[apply-check] read-tree 失败：${readTree.stderr.trim()}`);
  process.exit(1);
}

// 3) 逐 patch --cached --check（顺序无关；任一失败即整体 FAIL）。
const patches = readdirSync(EXEMPT_DIR).filter((f) => f.endsWith(".patch")).sort();
if (patches.length === 0) {
  console.error("[apply-check] contracts/exemptions/ 下无 *.patch（豁免集为空或路径错）");
  process.exit(1);
}
let failed = 0;
for (const patch of patches) {
  const r = git(["apply", "--cached", "--check", join("contracts", "exemptions", patch)], {
    GIT_INDEX_FILE: indexFile,
  });
  if (r.status === 0) {
    console.log(`[apply-check] APPLY_OK ${patch}`);
  } else {
    failed += 1;
    console.error(`[apply-check] APPLY_FAIL ${patch}\n${(r.stderr || "").trim().split("\n").slice(0, 6).join("\n")}`);
  }
}
rmSync(indexFile, { force: true });

if (failed > 0) {
  console.error(`APPLY_CHECK_FAIL ${patches.length - failed}/${patches.length} 过，${failed} 个 patch 无法干净打在基线 ${BASE.slice(0, 9)} 上`);
  process.exit(1);
}
console.log(`APPLY_CHECK_PASS ${patches.length}/${patches.length} patch 干净适用于基线 ${BASE.slice(0, 9)}（3.16.2 原树）`);
