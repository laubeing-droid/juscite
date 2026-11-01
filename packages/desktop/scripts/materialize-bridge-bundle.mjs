// 桥随包物化（步骤5·桥随包单；销项 78b34899 记档的「无仓库布局机器桥 spawn fail-closed」边界）。
//
// 产物 = <desktop>/bridge-bundle/ 自足目录（extraResources 拷进安装包 resources/bridge）：
//   bridge-bundle/
//     tools/bridge/**            桥入口与桥面服务（真文件；排除依赖与运行残留）
//     packages/services/**       桥以相对路径 import 的 TS 源（package.json 供 #src 子路径导入）
//     knowledge-base/**          B61 内置文集（kbBuiltinSourceRoot 从 cwd 向上 8 级扫描）
//     lawbook-packs/**           RE-13 法条手册内置包（lawbook 服务从 cwd 向上扫描 lawbook-packs/）
//     node_modules/**            依赖闭包实件（pnpm deploy --prod --legacy @juscite/bridge，
//                                pnpm symlink 布局不解自明；剪除非目标平台原生二进制）
// 打包态 spawn 路径见 desktopHostProcess.ts resolveBridgePaths 的 app.isPackaged 分支。
// dev 态（仓库布局）不经过本目录，行为不变。
//
// 拷贝用 readdir+copyFile 自写实现：本机 node 22.23.1 的 fs.cpSync 递归拷贝原生崩溃
// （静默 exit 127，学习迭代轮在案），同 electron-builder.config.js copyModuleTreeSync 先例。
import { copyFileSync, existsSync, mkdirSync, readdirSync, renameSync, rmSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { runCommand } from "./spawn-command.mjs";
import { getTargetPlatform } from "./target-platform.mjs";

const BRIDGE_PACKAGE_DIR = "tools/bridge";
const SERVICES_PACKAGE_DIR = "packages/services";
// r12 波2.5 runtime-port：桥以相对路径 import 的 port 域面与 opencode adapter，随包同 services 法
// （package.json + src；缺失=打包态桥 spawn 即挂，essentials 断言兜底）。
const RUNTIME_PORT_DIR = join("packages", "juscite-runtime-port");
// r12 波3 法律内核出树：learning/caseGraph 等纯模型从 services/legal 迁 packages/juscite-legal/src/kernel，
// 桥以相对路径 import，随包同法（缺失=打包态桥 spawn 即挂，essentials 断言兜底）。
const LEGAL_PACKAGE_DIR = join("packages", "juscite-legal");
const RUNTIME_ADAPTER_OPENCODE_DIR = join("packages", "juscite-runtime-adapters", "opencode");
// 功能 #42 电子数据取证：edisc 服务以相对路径 import 的锚/行面/审查内核，随包同法。
const EDISC_PACKAGE_DIR = join("packages", "juscite-edisc");
// 施工波-20261030 可视化B轨：#4 大事记表/#19 庭审对抗图机制契约包（@juscite/vizb），桥以相对路径
// import（vizbChronicle*/vizbConfrontation*/vizbIntakeReconcile 五工具面），随包同法（essentials 断言兜底）。
const VIZB_PACKAGE_DIR = join("packages", "juscite-vizb");
const KNOWLEDGE_BASE_DIR = "knowledge-base";
// RE-13 法条手册内置包：lawbook 服务与 kb 同款 cwd 向上扫描，随包必须带上（§3.1 随产品分发）。
const LAWBOOK_PACKS_DIR = "lawbook-packs";
// timeline_skill.mjs 以 tools/bridge 相对路径读规范包唯一真源（../../implementation/skill-presets/，
// 桥启动即验存在性 fail-closed），随包必须带上。
const SKILL_PRESETS_DIR = join("implementation", "skill-presets");
// 【#14 引证核验】轻量引擎随包（RE-14 §3.2/§3.3）：单文件 std-lib Python，桥 spawn 一次性调用，
// 随包布局=桥文件相邻 ../../implementation/python/（citation_verify_service 解析序第二优先）。
const CITATION_ENGINE_FILE = join("implementation", "python", "citation_verify_lite.py");
// 剪除名单：esbuild 与 node-pty 的非目标平台原生二进制在打包目标上不可达，只占体积。
const PLATFORM_NATIVE_COPY_ROOTS = ["@esbuild", join("node-pty", "prebuilds")];

export function resolveBridgeBundleDir(desktopPackageRoot) {
  return resolve(desktopPackageRoot, "bridge-bundle");
}

// 随包只带桥源码真件：dev 态 symlink 依赖、本机运行残留 db、并行泳道临时件不进安装包。
function bridgeSourceEntryAllowed(name) {
  if (name === "node_modules") return false;
  if (name.startsWith("_tmp_")) return false;
  if (/\.(db|db-journal|db-wal|db-shm)$/.test(name)) return false;
  if (name.includes(".bak-")) return false;
  return true;
}

function copyTreeManual(source, target, entryFilter) {
  if (statSync(source).isDirectory()) {
    mkdirSync(target, { recursive: true });
    for (const entry of readdirSync(source)) {
      if (entryFilter && !entryFilter(entry)) continue;
      copyTreeManual(resolve(source, entry), join(target, entry), entryFilter);
    }
    return;
  }
  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(source, target);
}

function copyTreeVerified(source, target, entryFilter) {
  if (!existsSync(source)) {
    throw new Error(`bridge bundle source missing: ${source}`);
  }
  copyTreeManual(source, target, entryFilter);
}

function copyBridgeSources(repoRoot, bundleDir) {
  copyTreeVerified(
    resolve(repoRoot, BRIDGE_PACKAGE_DIR),
    join(bundleDir, BRIDGE_PACKAGE_DIR),
    bridgeSourceEntryAllowed,
  );
  copyTreeVerified(
    resolve(repoRoot, KNOWLEDGE_BASE_DIR),
    join(bundleDir, KNOWLEDGE_BASE_DIR),
  );
  copyTreeVerified(
    resolve(repoRoot, LAWBOOK_PACKS_DIR),
    join(bundleDir, LAWBOOK_PACKS_DIR),
  );
  copyTreeVerified(
    resolve(repoRoot, SKILL_PRESETS_DIR),
    join(bundleDir, SKILL_PRESETS_DIR),
  );
  copyTreeVerified(
    resolve(repoRoot, CITATION_ENGINE_FILE),
    join(bundleDir, CITATION_ENGINE_FILE),
  );
  // services 只带 package.json + src（桥面相对导入的唯一包内源）；其余（test/scripts）不随包。
  const servicesDir = resolve(repoRoot, SERVICES_PACKAGE_DIR);
  const destServices = join(bundleDir, SERVICES_PACKAGE_DIR);
  mkdirSync(destServices, { recursive: true });
  copyFileSync(join(servicesDir, "package.json"), join(destServices, "package.json"));
  copyTreeVerified(join(servicesDir, "src"), join(destServices, "src"));
  // runtime-port 两包同法（r12 波2.5）：package.json + src。
  for (const pkgDir of [RUNTIME_PORT_DIR, RUNTIME_ADAPTER_OPENCODE_DIR, LEGAL_PACKAGE_DIR, EDISC_PACKAGE_DIR, VIZB_PACKAGE_DIR]) {
    const srcPkg = resolve(repoRoot, pkgDir);
    const destPkg = join(bundleDir, pkgDir);
    mkdirSync(destPkg, { recursive: true });
    copyFileSync(join(srcPkg, "package.json"), join(destPkg, "package.json"));
    copyTreeVerified(join(srcPkg, "src"), join(destPkg, "src"));
  }
}

function pruneForeignPlatformBinaries(deployedModulesDir, platformKey) {
  for (const relativeRoot of PLATFORM_NATIVE_COPY_ROOTS) {
    const root = join(deployedModulesDir, relativeRoot);
    if (!existsSync(root)) continue;
    for (const name of readdirSync(root)) {
      if (name !== platformKey) {
        rmSync(join(root, name), { recursive: true, force: true });
      }
    }
  }
}

function deployBridgeModules(repoRoot, bundleDir, platformKey) {
  // deploy 落在 bundle 内的同盘临时目录（renameSync 不跨盘）；pnpm deploy 会顺带拷一份
  // tools/bridge 文件，本物化只取其实件 node_modules，源码以 copyBridgeSources 的仓库真件为准。
  const deployTmpRelative = "packages/desktop/bridge-bundle/.deploy-tmp";
  const deployTmpDir = resolve(repoRoot, deployTmpRelative);
  rmSync(deployTmpDir, { recursive: true, force: true });
  try {
    runCommand("pnpm", [
      "--filter", "@juscite/bridge", "deploy", "--prod", "--legacy", deployTmpRelative,
    ], { cwd: repoRoot });
    const deployedModules = join(deployTmpDir, "node_modules");
    if (!existsSync(join(deployedModules, "tsx", "dist", "cli.mjs"))) {
      throw new Error("pnpm deploy 未产出 tsx（随包运行时装载器缺失）");
    }
    pruneForeignPlatformBinaries(deployedModules, platformKey);
    renameSync(deployedModules, join(bundleDir, "node_modules"));
  } finally {
    rmSync(deployTmpDir, { recursive: true, force: true });
  }
}

function assertBundleEssentials(bundleDir, platformKey) {
  const essentials = [
    join(bundleDir, BRIDGE_PACKAGE_DIR, "bridge_host.mjs"),
    join(bundleDir, "node_modules", "tsx", "dist", "cli.mjs"),
    join(bundleDir, "node_modules", "@zcode", "services", "package.json"),
    join(bundleDir, "node_modules", "@esbuild", platformKey),
    join(bundleDir, SERVICES_PACKAGE_DIR, "src", "index.ts"),
    join(bundleDir, RUNTIME_PORT_DIR, "src", "index.ts"),
    join(bundleDir, RUNTIME_ADAPTER_OPENCODE_DIR, "src", "opencodeAdapter.mjs"),
    join(bundleDir, LEGAL_PACKAGE_DIR, "src", "kernel", "learningModel.ts"),
    join(bundleDir, EDISC_PACKAGE_DIR, "src", "index.ts"),
    join(bundleDir, VIZB_PACKAGE_DIR, "src", "chronicle", "index.ts"),
    join(bundleDir, VIZB_PACKAGE_DIR, "src", "confrontation", "index.ts"),
    join(bundleDir, KNOWLEDGE_BASE_DIR),
    join(bundleDir, LAWBOOK_PACKS_DIR, "base", "pack.meta"),
    join(bundleDir, SKILL_PRESETS_DIR, "timeline-generation", "skill.json"),
    join(bundleDir, SKILL_PRESETS_DIR, "evidence-catalog", "skill.json"), // #7 证据目录主技能（evidence_catalog_skill.mjs fail-closed 真源；施工波三轮）
    join(bundleDir, SKILL_PRESETS_DIR, "evidence-materials", "skill.json"), // #7 证据材料整理姊妹技能（evidence_materials_skill.mjs fail-closed 真源；施工波三轮）
  ];
  const missing = essentials.filter((p) => !existsSync(p));
  if (missing.length > 0) {
    throw new Error(`bridge bundle essentials missing: ${missing.join(", ")}`);
  }
}

function dirSizeBytes(dir) {
  let total = 0;
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) total += dirSizeBytes(full);
    else total += statSync(full).size;
  }
  return total;
}

export function materializeBridgeBundle({ desktopPackageRoot }) {
  const platformKey = getTargetPlatform().key;
  const repoRoot = resolve(desktopPackageRoot, "..", "..");
  const bundleDir = resolveBridgeBundleDir(desktopPackageRoot);
  rmSync(bundleDir, { recursive: true, force: true });
  mkdirSync(bundleDir, { recursive: true });
  copyBridgeSources(repoRoot, bundleDir);
  deployBridgeModules(repoRoot, bundleDir, platformKey);
  assertBundleEssentials(bundleDir, platformKey);
  const sizeMb = (dirSizeBytes(bundleDir) / 1024 / 1024).toFixed(1);
  console.log(`[bridge-bundle] materialized ${bundleDir} (${sizeMb} MB, platform ${platformKey})`);
  return bundleDir;
}

const invokedDirectly = process.argv[1] != null &&
  fileURLToPath(import.meta.url) === resolve(process.argv[1]);
if (invokedDirectly) {
  materializeBridgeBundle({ desktopPackageRoot: resolve(import.meta.dirname, "..") });
}
