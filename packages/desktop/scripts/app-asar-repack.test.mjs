import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import {
  findStagingUnpackTarget,
  replaceAppAsarFromStaging,
} from "./app-asar-repack.mjs";

function writeTree(root, files) {
  for (const [relativePath, contents] of Object.entries(files)) {
    const fullPath = join(root, ...relativePath.split("/"));
    mkdirSync(join(fullPath, ".."), { recursive: true });
    writeFileSync(fullPath, contents);
  }
}

test("findStagingUnpackTarget matches native basenames and node-pty prebuilds only", () => {
  const root = mkdtempSync(join(tmpdir(), "asar-unpack-scan-"));
  try {
    writeTree(root, {
      "index.js": "js",
      "node_modules/pngjs/png.js": "png",
      "node_modules/node-pty/lib/unixTerminal.js": "js",
      "tools/spawn-helper": "not-a-prebuild",
      "vendor/Native.DLL": "case",
    });
    assert.equal(findStagingUnpackTarget(root, "win32-x64"), null);

    writeTree(root, {
      "node_modules/node-pty/prebuilds/win32-x64/spawn-helper": "helper",
    });
    assert.equal(
      findStagingUnpackTarget(root, "win32-x64"),
      "node_modules/node-pty/prebuilds/win32-x64/spawn-helper",
    );

    const nativeRoot = mkdtempSync(join(tmpdir(), "asar-unpack-scan-native-"));
    try {
      writeTree(nativeRoot, { "node_modules/foo/bar.node": "native" });
      assert.equal(findStagingUnpackTarget(nativeRoot, "win32-x64"), "node_modules/foo/bar.node");
    } finally {
      rmSync(nativeRoot, { recursive: true, force: true });
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("repack without unpack matches swaps app.asar and keeps the existing sidecar", async () => {
  const root = mkdtempSync(join(tmpdir(), "asar-repack-js-"));
  try {
    const sourceDir = join(root, "stage");
    const resourcesDir = join(root, "resources");
    mkdirSync(sourceDir, { recursive: true });
    mkdirSync(resourcesDir, { recursive: true });
    writeTree(sourceDir, { "index.js": "next-app" });
    const appAsarPath = join(resourcesDir, "app.asar");
    writeFileSync(appAsarPath, "old-asar");
    mkdirSync(join(resourcesDir, "app.asar.unpacked"), { recursive: true });
    writeFileSync(join(resourcesDir, "app.asar.unpacked", "pty.node"), "stale");

    await replaceAppAsarFromStaging({
      sourceDir,
      appAsarPath,
      targetPlatformKey: "win32-x64",
      runAsarCommand(args) {
        assert.equal(args[0], "pack");
        assert.equal(args[3], "--unpack");
        assert.equal(args[4], "*.{node,dll,dylib,exe}");
        writeFileSync(args[2], "new-asar");
      },
    });

    assert.equal(readFileSync(appAsarPath, "utf8"), "new-asar");
    assert.equal(readFileSync(join(`${appAsarPath}.unpacked`, "pty.node"), "utf8"), "stale");
    assert.equal(existsSync(`${appAsarPath}.next`), false);
    assert.equal(existsSync(`${appAsarPath}.next.unpacked`), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("repack keeps the previous archive when natives were not unpacked", async () => {
  const root = mkdtempSync(join(tmpdir(), "asar-repack-native-miss-"));
  try {
    const sourceDir = join(root, "stage");
    const resourcesDir = join(root, "resources");
    writeTree(sourceDir, { "node_modules/foo/bar.node": "native" });
    const appAsarPath = join(resourcesDir, "app.asar");
    mkdirSync(resourcesDir, { recursive: true });
    writeFileSync(appAsarPath, "old-asar");
    mkdirSync(`${appAsarPath}.unpacked`, { recursive: true });
    writeFileSync(join(`${appAsarPath}.unpacked`, "keep.node"), "keep");

    await assert.rejects(
      () =>
        replaceAppAsarFromStaging({
          sourceDir,
          appAsarPath,
          targetPlatformKey: "win32-x64",
          runAsarCommand(args) {
            writeFileSync(args[2], "new-asar-only");
          },
        }),
      /app\.asar\.unpacked=missing.*unpackTarget=node_modules\/foo\/bar\.node/,
    );

    assert.equal(readFileSync(appAsarPath, "utf8"), "old-asar");
    assert.equal(readFileSync(join(`${appAsarPath}.unpacked`, "keep.node"), "utf8"), "keep");
    assert.equal(existsSync(`${appAsarPath}.next`), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("repack swaps both candidates when asar writes a sidecar", async () => {
  const root = mkdtempSync(join(tmpdir(), "asar-repack-both-"));
  try {
    const sourceDir = join(root, "stage");
    const resourcesDir = join(root, "resources");
    mkdirSync(sourceDir, { recursive: true });
    mkdirSync(resourcesDir, { recursive: true });
    writeTree(sourceDir, { "node_modules/foo/bar.node": "native" });
    const appAsarPath = join(resourcesDir, "app.asar");
    writeFileSync(appAsarPath, "old-asar");
    mkdirSync(`${appAsarPath}.unpacked`, { recursive: true });
    writeFileSync(join(`${appAsarPath}.unpacked`, "old.node"), "old");

    await replaceAppAsarFromStaging({
      sourceDir,
      appAsarPath,
      targetPlatformKey: "win32-x64",
      runAsarCommand(args) {
        writeFileSync(args[2], "new-asar");
        const unpacked = `${args[2]}.unpacked`;
        mkdirSync(join(unpacked, "node_modules", "foo"), { recursive: true });
        writeFileSync(join(unpacked, "node_modules", "foo", "bar.node"), "new-native");
      },
    });

    assert.equal(readFileSync(appAsarPath, "utf8"), "new-asar");
    assert.equal(
      readFileSync(join(`${appAsarPath}.unpacked`, "node_modules", "foo", "bar.node"), "utf8"),
      "new-native",
    );
    assert.equal(existsSync(join(`${appAsarPath}.unpacked`, "old.node")), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

function resolveAsarCli() {
  const require = createRequire(import.meta.url);
  return require.resolve("@electron/asar/bin/asar.js");
}

function runRealAsar(asarCli) {
  return (args) => {
    const result = spawnSync(process.execPath, [asarCli, ...args], { encoding: "utf8" });
    assert.equal(result.status, 0, result.stderr || result.stdout);
  };
}

test("@electron/asar omits the sidecar under a hidden staging dir when nothing matches", async (t) => {
  let asarCli;
  try {
    asarCli = resolveAsarCli();
  } catch {
    t.skip("@electron/asar is not installed");
    return;
  }

  const root = mkdtempSync(join(tmpdir(), "asar-repack-real-"));
  const hiddenStage = join(root, ".tmp", "stage");
  const resourcesDir = join(root, "resources");
  try {
    writeTree(hiddenStage, {
      "index.js": "js",
      "node_modules/pngjs/png.js": "png",
    });
    mkdirSync(resourcesDir, { recursive: true });
    const appAsarPath = join(resourcesDir, "app.asar");
    writeFileSync(appAsarPath, "old");
    mkdirSync(`${appAsarPath}.unpacked`, { recursive: true });
    writeFileSync(join(`${appAsarPath}.unpacked`, "stale.node"), "stale");

    await replaceAppAsarFromStaging({
      sourceDir: hiddenStage,
      appAsarPath,
      targetPlatformKey: "win32-x64",
      runAsarCommand: runRealAsar(asarCli),
    });

    assert.equal(existsSync(appAsarPath), true);
    assert.notEqual(readFileSync(appAsarPath, "utf8"), "old");
    assert.equal(readFileSync(join(`${appAsarPath}.unpacked`, "stale.node"), "utf8"), "stale");
    assert.equal(existsSync(`${appAsarPath}.next`), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("@electron/asar still writes the sidecar for natives staged under a hidden directory", async (t) => {
  let asarCli;
  try {
    asarCli = resolveAsarCli();
  } catch {
    t.skip("@electron/asar is not installed");
    return;
  }

  const root = mkdtempSync(join(tmpdir(), "asar-repack-real-native-"));
  const hiddenStage = join(root, ".tmp", "stage");
  const resourcesDir = join(root, "resources");
  try {
    writeTree(hiddenStage, {
      "index.js": "js",
      "node_modules/foo/bar.node": "native-bytes",
      "node_modules/node-pty/prebuilds/win32-x64/spawn-helper": "helper",
    });
    mkdirSync(resourcesDir, { recursive: true });
    const appAsarPath = join(resourcesDir, "app.asar");
    writeFileSync(appAsarPath, "old");

    await replaceAppAsarFromStaging({
      sourceDir: hiddenStage,
      appAsarPath,
      targetPlatformKey: "win32-x64",
      runAsarCommand: runRealAsar(asarCli),
    });

    assert.equal(
      readFileSync(join(`${appAsarPath}.unpacked`, "node_modules", "foo", "bar.node"), "utf8"),
      "native-bytes",
    );
    assert.equal(
      readFileSync(
        join(
          `${appAsarPath}.unpacked`,
          "node_modules",
          "node-pty",
          "prebuilds",
          "win32-x64",
          "spawn-helper",
        ),
        "utf8",
      ),
      "helper",
    );
    assert.equal(existsSync(`${appAsarPath}.next`), false);
    assert.equal(existsSync(`${appAsarPath}.next.unpacked`), false);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
