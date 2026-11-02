import { readdirSync } from "node:fs";
import { rename, rm, stat } from "node:fs/promises";
import { join, relative, sep } from "node:path";

export const ASAR_UNPACK_NATIVE_GLOB = "*.{node,dll,dylib,exe}";

// 与 @electron/asar 3.4.1 的 minimatch（默认区分大小写、matchBase）对齐。
const NATIVE_UNPACK_BASENAME = /\.(?:node|dll|dylib|exe)$/;

async function describeCandidate(path) {
  try {
    const info = await stat(path);
    if (info.isDirectory()) return "dir";
    if (info.isFile()) return `file:${info.size}`;
    return "other";
  } catch (error) {
    if (error && error.code === "ENOENT") return "missing";
    throw error;
  }
}

function toPosixRelative(sourceDir, filePath) {
  return relative(sourceDir, filePath).split(sep).join("/");
}

function matchesUnpackTarget(relativePath, basename, unpackDirPrefix) {
  if (NATIVE_UNPACK_BASENAME.test(basename)) return true;
  return relativePath === unpackDirPrefix || relativePath.startsWith(`${unpackDirPrefix}/`);
}

// @electron/asar 只在至少有一个文件被 unpack 时才创建 `<archive>.unpacked`。
// 这里用真实目录树判断，而不是再跑一遍会在隐藏目录上失效的 `**/` glob。
export function findStagingUnpackTarget(sourceDir, targetPlatformKey) {
  const unpackDirPrefix = `node_modules/node-pty/prebuilds/${targetPlatformKey}`;
  const stack = [sourceDir];
  while (stack.length > 0) {
    const dir = stack.pop();
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const fullPath = join(dir, entry.name);
      if (entry.isDirectory() && !entry.isSymbolicLink()) {
        stack.push(fullPath);
        continue;
      }
      if (!entry.isFile() && !entry.isSymbolicLink()) continue;
      const relativePath = toPosixRelative(sourceDir, fullPath);
      if (matchesUnpackTarget(relativePath, entry.name, unpackDirPrefix)) {
        return relativePath;
      }
    }
  }
  return null;
}

export function createAppAsarPackArgs({ sourceDir, destinationPath, targetPlatformKey }) {
  return [
    "pack",
    sourceDir,
    destinationPath,
    "--unpack",
    ASAR_UNPACK_NATIVE_GLOB,
    "--unpack-dir",
    `node_modules/node-pty/prebuilds/${targetPlatformKey}`,
  ];
}

export async function replaceAppAsarFromStaging({
  sourceDir,
  appAsarPath,
  targetPlatformKey,
  runAsarCommand,
}) {
  const candidateAsarPath = `${appAsarPath}.next`;
  const candidateUnpackedPath = `${candidateAsarPath}.unpacked`;
  const unpackedPath = `${appAsarPath}.unpacked`;

  await Promise.all([
    rm(candidateAsarPath, { force: true, recursive: true }),
    rm(candidateUnpackedPath, { force: true, recursive: true }),
  ]);

  try {
    runAsarCommand(
      createAppAsarPackArgs({
        sourceDir,
        destinationPath: candidateAsarPath,
        targetPlatformKey,
      }),
    );

    const asarState = await describeCandidate(candidateAsarPath);
    const unpackedState = await describeCandidate(candidateUnpackedPath);
    const asarExists = asarState !== "missing";
    const unpackedExists = unpackedState !== "missing";
    // 只在 sidecar 缺失时扫 staging。命中 unpack 规则却没有 sidecar，才是 glob 失败；
    // 没有任何命中时 @electron/asar 本来就不会创建 `<archive>.unpacked`。
    const unpackTarget =
      asarExists && !unpackedExists ? findStagingUnpackTarget(sourceDir, targetPlatformKey) : null;

    if (!asarExists || (unpackTarget && !unpackedExists)) {
      // finally 会删掉候选，先把存在性写进日志，避免事后无法判断是没写出还是被清掉。
      console.error(
        `[asar-repack] candidates before cleanup ${candidateAsarPath}=${asarState} ${candidateUnpackedPath}=${unpackedState} unpackTarget=${unpackTarget ?? "none"}`,
      );
    }

    if (!asarExists) {
      throw new Error(
        `重打包结果缺少 app.asar 或 app.asar.unpacked: ${candidateAsarPath} (app.asar=${asarState}, app.asar.unpacked=${unpackedState})`,
      );
    }

    if (!unpackedExists) {
      if (unpackTarget) {
        throw new Error(
          `重打包结果缺少 app.asar 或 app.asar.unpacked: ${candidateUnpackedPath} (app.asar=${asarState}, app.asar.unpacked=${unpackedState}, unpackTarget=${unpackTarget})`,
        );
      }
      // 没有 unpack 命中时 asar 不写 sidecar。staging 里没有这些文件，不能用一份空替换
      // 盖掉 electron-builder 已经放好的 app.asar.unpacked。
      console.log(
        `[asar-repack] no unpack matches; replacing app.asar and keeping existing ${unpackedPath}`,
      );
      await rm(appAsarPath, { force: true });
      await rename(candidateAsarPath, appAsarPath);
      return;
    }

    // 先完整生成候选文件，再替换旧 archive 和 sidecar；不会把上一次打包的跨平台 native 留在 unpacked。
    await rm(unpackedPath, { force: true, recursive: true });
    await rename(candidateUnpackedPath, unpackedPath);
    await rm(appAsarPath, { force: true });
    await rename(candidateAsarPath, appAsarPath);
  } finally {
    await Promise.all([
      rm(candidateAsarPath, { force: true, recursive: true }),
      rm(candidateUnpackedPath, { force: true, recursive: true }),
    ]);
  }
}
