import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import {
  FEISHU_ASAR_INJECT_ROOT,
  assertAsarInjectRootsMatchLockfile,
  classifyAsarInjectRoots,
  collectLockfilePackageNames,
  extractInjectRootList,
  findResolvedInstallRoot,
  loadAsarInjectRootReport,
  packageNameFromLockKey,
} from "./check-asar-inject-roots.mjs";

test("real inject roots are in the lockfile, including Feishu", () => {
  const summary = assertAsarInjectRootsMatchLockfile();
  assert.match(summary, /via-lockfile=\d+/);
  assert.match(summary, /feishu-allow=0/);

  const report = loadAsarInjectRootReport();
  const feishu = report.alive.filter((entry) => entry.name === FEISHU_ASAR_INJECT_ROOT);
  assert.equal(feishu.length, 2);
  assert.ok(feishu.every((entry) => entry.via === "lockfile"));
  assert.equal(report.dead.length, 0);
  assert.equal(report.allowedQuirks.length, 0);
});

test("extracts root names and ignores comment quotes", () => {
  const source = `
const REQUIRED_ASAR_RUNTIME_MODULES = [
  "pngjs",
  // Cannot find module '@babel/runtime/helpers/interopRequireDefault',
  "undici",
  '@larksuiteoapi/node-sdk',
];
`;
  assert.deepEqual(extractInjectRootList(source, "REQUIRED_ASAR_RUNTIME_MODULES"), [
    "pngjs",
    "undici",
    "@larksuiteoapi/node-sdk",
  ]);
});

test("rejects a list line that is not a package name", () => {
  const source = `
const requiredRuntimeModules = [
  pngjs,
];
`;
  assert.throws(
    () => extractInjectRootList(source, "requiredRuntimeModules"),
    /无法识别的行/,
  );
});

test("reads scoped and peer-suffixed lockfile keys", () => {
  const lockText = `
lockfileVersion: '9.0'

importers:

  .:
    dependencies:
      ms:
        specifier: 2.1.3
        version: 2.1.3

packages:

  ms@2.1.3: {}

  '@larksuiteoapi/node-sdk@1.64.0':
    dependencies:
      axios: 1.13.6

  '@babel/plugin-syntax-jsx@7.28.6(@babel/core@7.29.0)': {}
`;
  const names = collectLockfilePackageNames(lockText);
  assert.equal(packageNameFromLockKey("@larksuiteoapi/node-sdk@1.64.0"), FEISHU_ASAR_INJECT_ROOT);
  assert.equal(names.has("ms"), true);
  assert.equal(names.has(FEISHU_ASAR_INJECT_ROOT), true);
  assert.equal(names.has("@babel/plugin-syntax-jsx"), true);
  assert.equal(names.has("axios"), false);
});

test("a missing root fails, Feishu quirk does not, an install root counts", () => {
  const missing = classifyAsarInjectRoots({
    lists: [
      {
        constName: "REQUIRED_ASAR_RUNTIME_MODULES",
        names: ["ghost-root", FEISHU_ASAR_INJECT_ROOT],
      },
    ],
    lockfileNames: new Set(["pngjs"]),
    resolveInstallRoot: () => null,
  });
  assert.deepEqual(
    missing.dead.map((entry) => entry.name),
    ["ghost-root"],
  );
  assert.deepEqual(
    missing.allowedQuirks.map((entry) => entry.name),
    [FEISHU_ASAR_INJECT_ROOT],
  );

  const installed = classifyAsarInjectRoots({
    lists: [{ constName: "requiredRuntimeModules", names: ["ghost-root"] }],
    lockfileNames: new Set(),
    resolveInstallRoot: (name) => (name === "ghost-root" ? "/tmp/ghost/package.json" : null),
  });
  assert.equal(installed.dead.length, 0);
  assert.equal(installed.alive[0]?.via, "install-root");
});

test("resolved install root sees a hoisted package and a pnpm store entry", () => {
  const repoRoot = mkdtempSync(resolve(tmpdir(), "asar-inject-roots-"));
  const desktopRoot = resolve(repoRoot, "packages", "desktop");
  const hoisted = resolve(repoRoot, "node_modules", "pngjs", "package.json");
  mkdirSync(dirname(hoisted), { recursive: true });
  writeFileSync(hoisted, "{\"name\":\"pngjs\"}\n");

  const stored = resolve(
    repoRoot,
    "node_modules",
    ".pnpm",
    "@larksuiteoapi+node-sdk@1.64.0",
    "node_modules",
    "@larksuiteoapi",
    "node-sdk",
    "package.json",
  );
  mkdirSync(dirname(stored), { recursive: true });
  writeFileSync(stored, "{\"name\":\"@larksuiteoapi/node-sdk\"}\n");

  assert.equal(
    findResolvedInstallRoot("pngjs", { repoRoot, desktopRoot }),
    hoisted,
  );
  assert.equal(
    findResolvedInstallRoot(FEISHU_ASAR_INJECT_ROOT, { repoRoot, desktopRoot }),
    stored,
  );
  assert.equal(findResolvedInstallRoot("ghost-root", { repoRoot, desktopRoot }), null);
});
