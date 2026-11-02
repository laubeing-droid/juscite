import { cpSync, existsSync, mkdirSync, realpathSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);

export function restoreTargetNodePtyPrebuild({ desktopPackageRoot, targetPlatform }) {
  // Windows 预编译在 node-pty 自己的 prebuilds/win32-x64 里，不走 Linux 的 @lydell 平台包。
  // 桌面依赖树那份经常没有 pty.node，beforePack 若直接跳过，asarUnpack 不会生成
  // app.asar.unpacked 下的对应路径。这里把已经解析到的 win32-x64 预编译复制进桌面包的 node-pty。
  if (targetPlatform.key === "win32-x64") {
    restoreWin32X64NodePtyPrebuild({ desktopPackageRoot, platformKey: targetPlatform.key });
    return;
  }

  if (targetPlatform.os !== "linux") {
    console.log(`[beforePack] node-pty prebuild restore skipped for ${targetPlatform.key}`);
    return;
  }

  const platformKey = targetPlatform.key;
  const sourcePackageName = `@lydell/node-pty-${platformKey}`;
  let sourceBinaryPath;

  try {
    sourceBinaryPath = resolveSourceNodePtyPrebuildPath({ sourcePackageName, platformKey });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`缺少 ${sourcePackageName}，无法为 ${platformKey} 打包 node-pty: ${message}`);
  }

  const nodePtyPackageRoot = dirname(
    require.resolve("node-pty/package.json", { paths: [desktopPackageRoot] }),
  );
  const targetPrebuildDir = resolve(nodePtyPackageRoot, "prebuilds", platformKey);
  const targetBinaryPath = resolve(targetPrebuildDir, "pty.node");

  // Linux 包中 node-pty 本体只会查自己的 prebuilds/linux-*/pty.node，
  // 但 Linux 预编译文件实际来自 @lydell/node-pty-linux-* 平台包；若排除该平台包，
  // 而 node-pty 自身目录没有 linux prebuild，最终安装包里会缺 pty.node，终端启动失败。
  // 这里在 beforePack 阶段恢复依赖资产，让后续 asarUnpack 按标准链路处理 native addon。
  mkdirSync(targetPrebuildDir, { recursive: true });
  cpSync(sourceBinaryPath, targetBinaryPath);

  if (!existsSync(targetBinaryPath))
    throw new Error(`node-pty 预编译产物恢复失败: ${targetBinaryPath}`);

  console.log(`[beforePack] node-pty prebuild restored: ${targetBinaryPath}`);
}

function sameExistingFile(left, right) {
  if (!left || !right) return false;
  if (left === right) return true;
  try {
    if (!existsSync(left) || !existsSync(right)) return false;
    return realpathSync(left) === realpathSync(right);
  } catch {
    return false;
  }
}

function findWorkspaceRoot(startDir) {
  let currentDir = resolve(startDir);
  while (true) {
    if (existsSync(resolve(currentDir, "pnpm-workspace.yaml"))) return currentDir;
    const parentDir = dirname(currentDir);
    if (parentDir === currentDir) return resolve(startDir, "..", "..");
    currentDir = parentDir;
  }
}

function nodePtyPrebuildAt(packageRoot, platformKey) {
  const candidatePath = resolve(
    packageRoot,
    "node_modules",
    "node-pty",
    "prebuilds",
    platformKey,
    "pty.node",
  );
  return existsSync(candidatePath) ? candidatePath : null;
}

function resolveWin32NodePtyPrebuildSource({ desktopPackageRoot, platformKey, targetBinaryPath }) {
  // 优先用已经装好的 node-pty（根目录 hoisted，其次桌面目录里另一份）的 win32-x64/pty.node。
  // 目标文件自己不算源；都没有时再试 @lydell/node-pty-win32-x64，和 Linux 的平台包查找一致。
  const workspaceRoot = findWorkspaceRoot(desktopPackageRoot);
  const candidates = [
    nodePtyPrebuildAt(workspaceRoot, platformKey),
    nodePtyPrebuildAt(desktopPackageRoot, platformKey),
  ];
  for (const candidatePath of candidates) {
    if (candidatePath && !sameExistingFile(candidatePath, targetBinaryPath)) return candidatePath;
  }

  try {
    const lydellBinaryPath = resolveSourceNodePtyPrebuildPath({
      sourcePackageName: `@lydell/node-pty-${platformKey}`,
      platformKey,
    });
    if (!sameExistingFile(lydellBinaryPath, targetBinaryPath)) return lydellBinaryPath;
  } catch {
    // node-pty 1.1 自带 Windows 预编译；@lydell 平台包在 Windows 上不是必需依赖。
  }

  if (existsSync(targetBinaryPath)) return targetBinaryPath;
  return null;
}

function restoreWin32X64NodePtyPrebuild({ desktopPackageRoot, platformKey }) {
  const nodePtyPackageRoot = dirname(
    require.resolve("node-pty/package.json", { paths: [desktopPackageRoot] }),
  );
  const targetPrebuildDir = resolve(nodePtyPackageRoot, "prebuilds", platformKey);
  const targetBinaryPath = resolve(targetPrebuildDir, "pty.node");
  const sourceBinaryPath = resolveWin32NodePtyPrebuildSource({
    desktopPackageRoot,
    platformKey,
    targetBinaryPath,
  });

  if (!sourceBinaryPath) {
    throw new Error(
      `缺少 node-pty 预编译产物，无法为 ${platformKey} 打包 node-pty: prebuilds/${platformKey}/pty.node`,
    );
  }

  if (!sameExistingFile(sourceBinaryPath, targetBinaryPath)) {
    mkdirSync(targetPrebuildDir, { recursive: true });
    cpSync(sourceBinaryPath, targetBinaryPath);
  }

  if (!existsSync(targetBinaryPath))
    throw new Error(`node-pty 预编译产物恢复失败: ${targetBinaryPath}`);

  console.log(`[beforePack] node-pty prebuild restored: ${targetBinaryPath}`);
}

export function resolveSourceNodePtyPrebuildPath({ sourcePackageName, platformKey }) {
  const sourcePackageEntry = require.resolve(sourcePackageName);
  let currentDir = dirname(sourcePackageEntry);

  while (currentDir !== dirname(currentDir)) {
    const candidatePath = resolve(currentDir, "prebuilds", platformKey, "pty.node");
    if (existsSync(candidatePath)) return candidatePath;

    currentDir = dirname(currentDir);
  }

  // @lydell/node-pty-linux-* 通过 package exports 只暴露 lib/index.js，
  // 不能再解析 package.json。这里从公开入口向上寻找 prebuilds，兼容 exports 限制。
  throw new Error(
    `缺少 node-pty 预编译产物: ${sourcePackageName}/prebuilds/${platformKey}/pty.node`,
  );
}

export function resolvePackagedNodePtyPrebuildPath({ resourcesDir, platformKey }) {
  return resolve(
    resourcesDir,
    "app.asar.unpacked",
    "node_modules",
    "node-pty",
    "prebuilds",
    platformKey,
    "pty.node",
  );
}
