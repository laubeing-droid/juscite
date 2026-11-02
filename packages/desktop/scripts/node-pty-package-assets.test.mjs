import assert from "node:assert/strict";
import {
  chmodSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  statSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import {
  materializePackagedWin32NodePtyPrebuild,
  resolvePackagedNodePtyPrebuildPath,
} from "./node-pty-package-assets.mjs";

function writeTree(root, files) {
  for (const [relativePath, contents] of Object.entries(files)) {
    const fullPath = join(root, ...relativePath.split("/"));
    mkdirSync(join(fullPath, ".."), { recursive: true });
    writeFileSync(fullPath, contents);
  }
}

function createFixture() {
  const root = mkdtempSync(join(tmpdir(), "node-pty-materialize-"));
  writeFileSync(join(root, "pnpm-workspace.yaml"), "packages:\n  - packages/*\n");
  const desktopPackageRoot = join(root, "packages", "desktop");
  mkdirSync(desktopPackageRoot, { recursive: true });
  const resourcesDir = join(root, "win-unpacked", "resources");
  return { root, desktopPackageRoot, resourcesDir };
}

function packagedPtyPath(resourcesDir) {
  return resolvePackagedNodePtyPrebuildPath({
    resourcesDir,
    platformKey: "win32-x64",
  });
}

test("materialize copies win32-x64 pty.node and sibling helpers into the assert path", () => {
  const fixture = createFixture();
  try {
    const sourceDir = join(
      fixture.root,
      "node_modules",
      "node-pty",
      "prebuilds",
      "win32-x64",
    );
    writeTree(fixture.root, {
      "node_modules/node-pty/package.json": JSON.stringify({ name: "node-pty" }),
      "node_modules/node-pty/prebuilds/win32-x64/pty.node": "pty-bytes",
      "node_modules/node-pty/prebuilds/win32-x64/winpty-agent.exe": "agent",
      "node_modules/node-pty/prebuilds/win32-x64/spawn-helper": "helper",
      "node_modules/node-pty/prebuilds/win32-x64/conpty/console-list.exe": "conpty",
      "win-unpacked/resources/app.asar.unpacked/keep.txt": "keep",
    });
    chmodSync(join(sourceDir, "spawn-helper"), 0o755);
    const realBinary = join(fixture.root, "real-pty.node");
    writeFileSync(realBinary, "pty-bytes");
    rmSync(join(sourceDir, "pty.node"));
    symlinkSync(realBinary, join(sourceDir, "pty.node"));

    materializePackagedWin32NodePtyPrebuild({
      desktopPackageRoot: fixture.desktopPackageRoot,
      resourcesDir: fixture.resourcesDir,
      targetPlatform: { key: "win32-x64", os: "win32" },
    });

    const targetDir = join(fixture.resourcesDir, "app.asar.unpacked", "node_modules", "node-pty", "prebuilds", "win32-x64");
    const targetPty = join(targetDir, "pty.node");
    assert.equal(lstatSync(targetPty).isSymbolicLink(), false);
    assert.equal(readFileSync(targetPty, "utf8"), "pty-bytes");
    assert.equal(readFileSync(join(targetDir, "winpty-agent.exe"), "utf8"), "agent");
    assert.equal(readFileSync(join(targetDir, "spawn-helper"), "utf8"), "helper");
    assert.equal(statSync(join(targetDir, "spawn-helper")).mode & 0o777, 0o755);
    assert.equal(readFileSync(join(targetDir, "conpty", "console-list.exe"), "utf8"), "conpty");
    assert.equal(
      readFileSync(join(fixture.resourcesDir, "app.asar.unpacked", "keep.txt"), "utf8"),
      "keep",
    );
    assert.equal(packagedPtyPath(fixture.resourcesDir), targetPty);
  } finally {
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("materialize prefers the hoisted prebuild over a different desktop copy", () => {
  const fixture = createFixture();
  try {
    writeTree(fixture.root, {
      "node_modules/node-pty/package.json": JSON.stringify({ name: "node-pty" }),
      "node_modules/node-pty/prebuilds/win32-x64/pty.node": "from-hoisted",
      "node_modules/node-pty/prebuilds/win32-x64/winpty-agent.exe": "hoisted-agent",
      "packages/desktop/node_modules/node-pty/package.json": JSON.stringify({ name: "node-pty" }),
      "packages/desktop/node_modules/node-pty/prebuilds/win32-x64/pty.node": "from-desktop",
      "packages/desktop/node_modules/node-pty/prebuilds/win32-x64/winpty-agent.exe": "desktop-agent",
    });

    materializePackagedWin32NodePtyPrebuild({
      desktopPackageRoot: fixture.desktopPackageRoot,
      resourcesDir: fixture.resourcesDir,
      targetPlatform: { key: "win32-x64", os: "win32" },
    });

    const targetDir = join(
      fixture.resourcesDir,
      "app.asar.unpacked",
      "node_modules",
      "node-pty",
      "prebuilds",
      "win32-x64",
    );
    assert.equal(readFileSync(join(targetDir, "pty.node"), "utf8"), "from-hoisted");
    assert.equal(readFileSync(join(targetDir, "winpty-agent.exe"), "utf8"), "hoisted-agent");
  } finally {
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("materialize uses the desktop-resolved node-pty package when nothing is hoisted", () => {
  const fixture = createFixture();
  try {
    writeTree(fixture.root, {
      "packages/desktop/node_modules/node-pty/package.json": JSON.stringify({ name: "node-pty" }),
      "packages/desktop/node_modules/node-pty/prebuilds/win32-x64/pty.node": "from-desktop",
      "packages/desktop/node_modules/node-pty/prebuilds/win32-x64/spawn-helper": "desktop-helper",
    });

    materializePackagedWin32NodePtyPrebuild({
      desktopPackageRoot: fixture.desktopPackageRoot,
      resourcesDir: fixture.resourcesDir,
      targetPlatform: { key: "win32-x64", os: "win32" },
    });

    const targetDir = join(
      fixture.resourcesDir,
      "app.asar.unpacked",
      "node_modules",
      "node-pty",
      "prebuilds",
      "win32-x64",
    );
    assert.equal(readFileSync(join(targetDir, "pty.node"), "utf8"), "from-desktop");
    assert.equal(readFileSync(join(targetDir, "spawn-helper"), "utf8"), "desktop-helper");
  } finally {
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("materialize is a no-op off the win32-x64 pack path", () => {
  const fixture = createFixture();
  try {
    writeTree(fixture.root, {
      "node_modules/node-pty/prebuilds/win32-x64/pty.node": "pty-bytes",
    });

    for (const targetPlatform of [
      { key: "linux-x64", os: "linux" },
      { key: "linux-arm64", os: "linux" },
      { key: "darwin-arm64", os: "darwin" },
      { key: "win32-arm64", os: "win32" },
    ]) {
      materializePackagedWin32NodePtyPrebuild({
        desktopPackageRoot: fixture.desktopPackageRoot,
        resourcesDir: fixture.resourcesDir,
        targetPlatform,
      });
    }

    assert.equal(existsSync(join(fixture.resourcesDir, "app.asar.unpacked")), false);
  } finally {
    rmSync(fixture.root, { recursive: true, force: true });
  }
});

test("materialize throws when the win32-x64 prebuild cannot be resolved", () => {
  const fixture = createFixture();
  try {
    assert.throws(
      () =>
        materializePackagedWin32NodePtyPrebuild({
          desktopPackageRoot: fixture.desktopPackageRoot,
          resourcesDir: fixture.resourcesDir,
          targetPlatform: { key: "win32-x64", os: "win32" },
        }),
      /prebuilds\/win32-x64\/pty\.node/,
    );
  } finally {
    rmSync(fixture.root, { recursive: true, force: true });
  }
});
