import {
  chmodSync,
  copyFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  realpathSync,
  statSync,
} from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);

export function restoreTargetNodePtyPrebuild({ desktopPackageRoot, targetPlatform }) {
  // Windows 预编译在 node-pty 自己的 prebuilds/win32-x64 里，不走 Linux 的 @lydell 平台包。
  // 桌面依赖树那份经常没有 pty.node。这里把已经解析到的预编译写回 node-pty，供开发态读取。
  // 桌面 package.json 不声明 node-pty，electron-builder 不会把它收进 asar，asarUnpack 匹配为空；
  // 安装包路径由 afterPack 的 materializePackagedWin32NodePtyPrebuild 落到 app.asar.unpacked。
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

  if (targetBinaryPath && existsSync(targetBinaryPath)) return targetBinaryPath;
  return null;
}

function resolveNodePtyPackageBinaryPath({ desktopPackageRoot, platformKey }) {
  try {
    const nodePtyPackageRoot = dirname(
      require.resolve("node-pty/package.json", { paths: [desktopPackageRoot] }),
    );
    return resolve(nodePtyPackageRoot, "prebuilds", platformKey, "pty.node");
  } catch {
    return null;
  }
}

function copyPrebuildTree(sourceDir, targetDir) {
  mkdirSync(targetDir, { recursive: true });
  for (const entry of readdirSync(sourceDir, { withFileTypes: true })) {
    const sourcePath = resolve(sourceDir, entry.name);
    const targetPath = resolve(targetDir, entry.name);
    const isDirectory =
      entry.isDirectory() || (entry.isSymbolicLink() && statSync(sourcePath).isDirectory());
    if (isDirectory) {
      copyPrebuildTree(sourcePath, targetPath);
      continue;
    }
    if (!entry.isFile() && !entry.isSymbolicLink()) continue;
    // copyFile 会跟随 junction / symlink，把文件内容写进安装包，而不是链接回仓库。
    copyFileSync(sourcePath, targetPath);
    chmodSync(targetPath, statSync(sourcePath).mode & 0o777);
  }
}

export function materializePackagedWin32NodePtyPrebuild({
  desktopPackageRoot,
  resourcesDir,
  targetPlatform,
}) {
  // 只补 Windows x64。Linux 仍走 beforePack 写回 node-pty 再由 asarUnpack 拆出；
  // 其它平台直接返回，避免在没有 win32 预编译的打包机上失败。
  if (targetPlatform.key !== "win32-x64") return;

  // 与 restore 同一条源查找：hoisted / 桌面 node-pty / 从桌面包解析到的 node-pty / @lydell。
  // targetBinaryPath 用 node-pty 包内路径而不是安装包路径，这样「文件已经在包里」的回退
  // 和 beforePack 一致，不会把尚未落盘的 app.asar.unpacked 当成源。
  const targetBinaryPath = resolvePackagedNodePtyPrebuildPath({
    resourcesDir,
    platformKey: targetPlatform.key,
  });
  const sourceBinaryPath = resolveWin32NodePtyPrebuildSource({
    desktopPackageRoot,
    platformKey: targetPlatform.key,
    targetBinaryPath: resolveNodePtyPackageBinaryPath({
      desktopPackageRoot,
      platformKey: targetPlatform.key,
    }),
  });

  if (!sourceBinaryPath) {
    // 预编译已经在断言路径上时不再失败；源缺失且目标也缺失才是打包失败。
    if (existsSync(targetBinaryPath)) return;
    throw new Error(
      `缺少 node-pty 预编译产物，无法为 ${targetPlatform.key} 打包 node-pty: prebuilds/${targetPlatform.key}/pty.node`,
    );
  }

  if (!sameExistingFile(sourceBinaryPath, targetBinaryPath)) {
    copyPrebuildTree(dirname(sourceBinaryPath), dirname(targetBinaryPath));
  }

  if (!existsSync(targetBinaryPath))
    throw new Error(`node-pty 预编译产物物化失败: ${targetBinaryPath}`);

  console.log(`[afterPack] node-pty prebuild materialized: ${targetBinaryPath}`);
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
