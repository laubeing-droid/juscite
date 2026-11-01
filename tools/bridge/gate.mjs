// M3 闸门执行器：world.run 输出 cap(256KB) 限制下的大输出命令包装。
// 用法：node gate.mjs <typecheck|build> — 真命令 stdout/stderr 落 D:/Codex/.../.local/gate-logs/，
// 本进程只打印 exit code 与尾部摘要（≤8KB）。
import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const WT = "D:/Codex/1.法律工作区/jusbench工作区/juscite/.local/worktrees/m1-u01";
const NODE = "C:/Users/being/AppData/Local/hermes/node/node.exe";
const PNM = "C:/Users/being/AppData/Local/node/corepack/v1/pnpm/10.33.2/bin/pnpm.cjs";
const LOGDIR = join(WT, ".local", "gate-logs");
const mode = process.argv[2];

const CMDS = {
  typecheck: [PNM, ["--dir", WT, "exec", "tsc", "-b",
    "packages/rpc", "packages/provider", "packages/provider-node", "packages/shared",
    "packages/services", "packages/client", "packages/ui", "packages/web",
    "packages/desktop/tsconfig.host.json"]],
  build: [PNM, ["--dir", WT, "--filter", "@zcode/desktop", "run", "build"]],
};
const cmd = CMDS[mode];
if (!cmd) { console.error("usage: gate.mjs <typecheck|build>"); process.exit(2); }

mkdirSync(LOGDIR, { recursive: true });
const r = spawnSync(NODE, [cmd[0], ...cmd[1]], {
  encoding: "buffer",
  maxBuffer: 64 * 1024 * 1024,
  env: { ...process.env, HTTPS_PROXY: "http://127.0.0.1:10808" },
});
const out = (r.stdout ?? Buffer.alloc(0)).toString("utf-8");
const err = (r.stderr ?? Buffer.alloc(0)).toString("utf-8");
writeFileSync(join(LOGDIR, mode + ".out.log"), out);
writeFileSync(join(LOGDIR, mode + ".err.log"), err);
const tail = (s) => (s.length > 6000 ? s.slice(-6000) : s);
console.log(`[gate:${mode}] exit=${r.status} stdoutBytes=${out.length} stderrBytes=${err.length}`);
console.log("--- stdout tail ---"); console.log(tail(out));
console.log("--- stderr tail ---"); console.log(tail(err));
process.exit(r.status ?? 1);
