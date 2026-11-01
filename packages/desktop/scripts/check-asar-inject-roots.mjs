#!/usr/bin/env node

// 干跑对拍：REQUIRED_ASAR_RUNTIME_MODULES / requiredRuntimeModules 里的注入根
// 必须出现在 pnpm-lock.yaml 的 packages 段，或已经能解析到的安装根。
// 名单上的死名以前会在 afterPack / bundle 校验里告警后跳过，删掉的包可以悄悄回到名单。
// 飞书 @larksuiteoapi/node-sdk 即使锁或安装根解析有癖性也不许因此失败，更不许靠删名单过检。

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const FEISHU_ASAR_INJECT_ROOT = "@larksuiteoapi/node-sdk";

const INJECT_ROOT_SOURCES = [
  {
    constName: "REQUIRED_ASAR_RUNTIME_MODULES",
    relativePath: "electron-builder.config.js",
  },
  {
    constName: "requiredRuntimeModules",
    relativePath: "scripts/bundle.mjs",
  },
];

export function extractInjectRootList(source, constName) {
  const marker = new RegExp(String.raw`(?:export\s+)?const\s+${constName}\s*=\s*\[`);
  const match = marker.exec(source);
  if (!match) {
    throw new Error(`未找到注入名单 ${constName}`);
  }

  const bodyStart = match.index + match[0].length;
  const bodyEnd = source.indexOf("\n];", bodyStart);
  if (bodyEnd < 0) {
    throw new Error(`注入名单 ${constName} 未以换行 ]; 结束`);
  }

  const names = [];
  for (const rawLine of source.slice(bodyStart, bodyEnd).split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("//") || line.startsWith("/*") || line.startsWith("*")) {
      continue;
    }

    const entry = /^(?:"([^"]+)"|'([^']+)')\s*,?\s*(?:\/\/.*)?$/.exec(line);
    if (!entry) {
      throw new Error(`注入名单 ${constName} 有无法识别的行: ${line}`);
    }
    names.push(entry[1] ?? entry[2]);
  }

  if (names.length === 0) {
    throw new Error(`注入名单 ${constName} 为空`);
  }
  return names;
}

export function packageNameFromLockKey(key) {
  const match = /^(@[^/]+\/[^@()]+|[^@()]+)@/.exec(key);
  return match ? match[1] : null;
}

export function collectLockfilePackageNames(lockText) {
  const marker = "\npackages:\n";
  const start = lockText.startsWith("packages:\n") ? 0 : lockText.indexOf(marker);
  if (start < 0) {
    throw new Error("pnpm-lock.yaml 缺少 packages 段");
  }

  const section = start === 0 ? lockText : lockText.slice(start + 1);
  const names = new Set();
  const packageKey = /^  (?! )(?:'([^']+)'|"([^"]+)"|([^:'"]+))\s*:/;
  for (const rawLine of section.split("\n")) {
    const line = rawLine.trimEnd();
    const match = packageKey.exec(line);
    if (!match) {
      continue;
    }

    const name = packageNameFromLockKey(match[1] ?? match[2] ?? match[3]);
    if (name) {
      names.add(name);
    }
  }

  if (names.size === 0) {
    throw new Error("pnpm-lock.yaml packages 段没有包名");
  }
  return names;
}

function pnpmStorePackageJson(storeRoot, moduleName) {
  const store = resolve(storeRoot, "node_modules", ".pnpm");
  if (!existsSync(store)) {
    return null;
  }

  const folderPrefix = `${moduleName.replace("/", "+")}@`;
  for (const entry of readdirSync(store, { withFileTypes: true })) {
    if (!entry.isDirectory() || !entry.name.startsWith(folderPrefix)) {
      continue;
    }

    const packageJsonPath = resolve(store, entry.name, "node_modules", moduleName, "package.json");
    if (existsSync(packageJsonPath)) {
      return packageJsonPath;
    }
  }
  return null;
}

export function findResolvedInstallRoot(moduleName, { repoRoot, desktopRoot }) {
  const lookupRoots = [desktopRoot, repoRoot];
  for (const lookupRoot of lookupRoots) {
    const packageJsonPath = resolve(lookupRoot, "node_modules", moduleName, "package.json");
    if (existsSync(packageJsonPath)) {
      return packageJsonPath;
    }
  }

  for (const storeRoot of [repoRoot, desktopRoot]) {
    const packageJsonPath = pnpmStorePackageJson(storeRoot, moduleName);
    if (packageJsonPath) {
      return packageJsonPath;
    }
  }
  return null;
}

export function classifyAsarInjectRoots({
  lists,
  lockfileNames,
  resolveInstallRoot,
  allowUnresolved = [FEISHU_ASAR_INJECT_ROOT],
}) {
  const alive = [];
  const allowedQuirks = [];
  const dead = [];

  for (const list of lists) {
    for (const name of list.names) {
      if (lockfileNames.has(name)) {
        alive.push({ list: list.constName, name, via: "lockfile" });
        continue;
      }

      const installRoot = resolveInstallRoot(name);
      if (installRoot) {
        alive.push({ list: list.constName, name, via: "install-root", installRoot });
        continue;
      }

      if (allowUnresolved.includes(name)) {
        allowedQuirks.push({ list: list.constName, name });
        continue;
      }

      dead.push({ list: list.constName, name });
    }
  }

  return { alive, allowedQuirks, dead };
}

function defaultRoots() {
  const desktopRoot = resolve(import.meta.dirname, "..");
  return {
    desktopRoot,
    repoRoot: resolve(desktopRoot, "../.."),
  };
}

export function loadAsarInjectRootReport(options = {}) {
  const roots = {
    ...defaultRoots(),
    ...options,
  };
  const lockText = readFileSync(resolve(roots.repoRoot, "pnpm-lock.yaml"), "utf8");
  const lists = INJECT_ROOT_SOURCES.map((source) => ({
    constName: source.constName,
    names: extractInjectRootList(
      readFileSync(resolve(roots.desktopRoot, source.relativePath), "utf8"),
      source.constName,
    ),
  }));

  return classifyAsarInjectRoots({
    lists,
    lockfileNames: collectLockfilePackageNames(lockText),
    resolveInstallRoot: (moduleName) => findResolvedInstallRoot(moduleName, roots),
  });
}

export function formatAsarInjectRootSummary(report) {
  const viaLockfile = report.alive.filter((entry) => entry.via === "lockfile").length;
  const viaInstallRoot = report.alive.filter((entry) => entry.via === "install-root").length;
  return (
    `[asar-inject-roots] ok roots=${report.alive.length + report.allowedQuirks.length} ` +
    `via-lockfile=${viaLockfile} via-install-root=${viaInstallRoot} ` +
    `feishu-allow=${report.allowedQuirks.length}`
  );
}

export function assertAsarInjectRootsMatchLockfile(options = {}) {
  const report = loadAsarInjectRootReport(options);
  if (report.dead.length > 0) {
    const lines = report.dead.map((entry) => `- ${entry.list}: ${entry.name}`);
    throw new Error(
      `asar 注入根不在锁或安装根中，死根不能静默回到名单:\n${lines.join("\n")}\n` +
        `${FEISHU_ASAR_INJECT_ROOT} 即使解析有癖性也不许从名单删除来换通过。`,
    );
  }

  for (const entry of report.allowedQuirks) {
    console.warn(
      `[asar-inject-roots] ${entry.list}: ${entry.name} 未在锁或安装根解析到，按飞书允许名单放过，不从注入名单删除`,
    );
  }

  return formatAsarInjectRootSummary(report);
}

const entryHref = process.argv[1] ? pathToFileURL(process.argv[1]).href : null;
if (entryHref === import.meta.url) {
  try {
    console.log(assertAsarInjectRootsMatchLockfile());
  } catch (error) {
    console.error(`[asar-inject-roots] ${error instanceof Error ? error.message : String(error)}`);
    process.exit(1);
  }
}
