import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { REQUIRED_ASAR_RUNTIME_MODULES } from "../electron-builder.config.js";
import { requiredRuntimeModules } from "./bundle.mjs";

function lockPackageNames(lockText) {
  const lines = lockText.split(/\r?\n/);
  const start = lines.indexOf("packages:");
  if (start < 0) throw new Error("pnpm-lock.yaml missing packages: section");
  const names = new Set();
  for (let i = start + 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.length > 0 && !/^\s/.test(line)) break;
    if (!/^ {2}\S/.test(line)) continue;
    let key = line.slice(2).replace(/:$/, "");
    if (key.startsWith("'") || key.startsWith('"')) key = key.slice(1, -1);
    const paren = key.indexOf("(");
    if (paren !== -1) key = key.slice(0, paren);
    const at = key.lastIndexOf("@");
    if (at > 0) names.add(key.slice(0, at));
  }
  return names;
}

export function assertInjectNamesInLockPackages(names, lockText) {
  const locked = lockPackageNames(lockText);
  const missing = [...new Set(names)].filter((name) => !locked.has(name));
  if (missing.length === 0) return;
  throw new Error(`inject module missing from pnpm-lock.yaml packages: ${missing.join(", ")}`);
}

export function assertInjectListsHitLockPackages() {
  assertInjectNamesInLockPackages(
    [...REQUIRED_ASAR_RUNTIME_MODULES, ...requiredRuntimeModules],
    readFileSync(resolve(import.meta.dirname, "../../..", "pnpm-lock.yaml"), "utf8"),
  );
}
