#!/usr/bin/env node
// Juscite M3 dev 编排：tsup watch + vite dev + electron（等 build-ready 标记后拉起，替代上游 dev-desktop-env.mjs 的 CUA/env 包装）。
import { spawn } from "node:child_process";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const pnpmCommand = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
const children = [];

function run(name, command, args) {
  const child = spawn(command, args, { cwd: root, stdio: "inherit", shell: process.platform === "win32" });
  child.on("exit", (code) => {
    console.log(`[dev-all] ${name} exited (${code})`);
    for (const other of children) {
      if (other !== child && other.exitCode === null) other.kill();
    }
    process.exit(code ?? 0);
  });
  children.push(child);
}

run("tsup", pnpmCommand, ["exec", "tsup", "--watch", "src", "--ignore-watch", "node_modules/**"]);
run("vite", pnpmCommand, ["exec", "vite", "dev"]);
run("electron", process.execPath, ["scripts/dev.mjs"]);
