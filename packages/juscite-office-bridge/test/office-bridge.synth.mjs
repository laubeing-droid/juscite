#!/usr/bin/env node
// Office 桥合成自测（方案 §五 S1/S2 断言，全部合成材料，不碰真实宿主）：
//   A1/A2. 无 token / 伪造 token 连接 → 拒（bootstrap_token_invalid）
//   A3. 单对端守卫：占位对端在连时，真第三方进程（子进程，不同 PID）持有效 token 也被拒
//   B. token 过期后 pair → bootstrap_token_invalid（同义错误码断言）
//   C. 正常链：发现文件 → pair（指纹钉扎）→ ready → ping/pong → subscribe → request 桩 → sequence 跳号被拒
//   D. 公钥指纹不匹配 → public_key_mismatch
//   E. token 轮换：pair 成功后旧值重放被拒
//   F. S2 页面零外呼：taskpane 自有文件（html/js/css，vendor 官方库另有口径）非 127.0.0.1 引用=0
//   G/J. stop() 发现文件清理；动态端口（port=0）系统分配且发现文件同步
// 运行：node packages/juscite-office-bridge/test/office-bridge.synth.mjs（隔离端口 :3090 起）
import WebSocket from "ws";
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";
import { startOfficeBridge, readDiscovery } from "../src/index.mjs";
import { injectWpsAddon, removeWpsAddon, wpsAddonState, versionAtLeast, WPS_PLUGIN_NAME } from "../src/wps-install.mjs";

const PKG_ROOT = fileURLToPath(new URL("..", import.meta.url));
const TASKPANE_DIR = join(PKG_ROOT, "taskpane");
const PORT_BASE = 3090; // 施工纪律：自测隔离端口 :3090 起

const results = [];
let failed = 0;
function check(name, ok, detail = "") {
  const line = `${ok ? "OK " : "FAIL"} ${name}${detail ? "｜" + detail : ""}`;
  results.push(line);
  console.log(`[office-bridge-synth] ${line}`); // 即时落 stdout：负载机上也看得到进度
  if (!ok) failed++;
}

async function freePortFrom(base) {
  const { createServer } = await import("node:http");
  for (let p = base; p < base + 50; p++) {
    const probe = createServer();
    const free = await new Promise((res) => {
      probe.once("error", () => res(false));
      probe.listen(p, "127.0.0.1", () => res(true));
    });
    probe.close();
    if (free) return p;
  }
  throw new Error(`:${base} 起找不到空闲端口`);
}

function dial(port) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}/ws`);
    const frames = [];
    ws.on("open", () => resolve({ ws, frames }));
    ws.on("message", (d) => frames.push(JSON.parse(String(d))));
    ws.on("error", reject);
  });
}
async function until(frames, pred, ms = 4000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    const hit = frames.find(pred);
    if (hit) return hit;
    await sleep(50);
  }
  return null;
}
const isErr = (code) => (f) => f.kind === "error" && f.code === code;
// 已关连接直接兑现：close 事件可能在挂监听前就已发过（until 轮询比关闭握手慢时）
const closed = (ws) =>
  new Promise((r) => {
    if (ws.readyState === WebSocket.CLOSED) return r();
    ws.on("close", r);
  });

// 真第三方进程：独立 node 子进程（不同 PID）拿 token 去 pair（stdout+stderr 全收）
function thirdPartyPair(port, token, fp) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, ["--input-type=module", "-e", `
      const WebSocket = (await import("ws")).default;
      const ws = new WebSocket("ws://127.0.0.1:${port}/ws");
      ws.on("open", () => ws.send(JSON.stringify({ kind: "pair", sequence: 1, bootstrapToken: process.env.OB_TOKEN, clientId: "third-party-proc", pinnedPublicKeySha256: process.env.OB_FP, surface: "word" })));
      ws.on("message", (d) => { const f = JSON.parse(String(d)); if (f.kind === "error") { console.log("OB_CHILD_ERR:" + f.code); ws.close(); } if (f.kind === "ready") { console.log("OB_CHILD_READY"); ws.close(); } });
      ws.on("error", (e) => { console.log("OB_CHILD_WSERR:" + e.message); process.exit(4); });
      ws.on("close", () => process.exit(0));
      setTimeout(() => { console.log("OB_CHILD_TIMEOUT"); process.exit(3); }, 8000);
    `], {
      cwd: join(PKG_ROOT, "..", ".."),
      env: { ...process.env, OB_TOKEN: token, OB_FP: fp },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "";
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (out += d));
    child.on("exit", (code) => resolve({ code, out }));
  });
}

async function main() {
  // 负载机看门狗：90s 未收口即打印所在阶段退出（不悬挂调用方）
  const stage = { at: "boot" };
  const watchdog = setTimeout(() => {
    console.error(`[office-bridge-synth] 看门狗超时（stage=${stage.at}）`);
    console.log("OFFICE_BRIDGE_SYNTH_FAIL");
    process.exit(1);
  }, 90_000);
  watchdog.unref?.();

  const stateDir = mkdtempSync(join(tmpdir(), "juscite-ob-synth-"));
  stage.at = "free-port";
  const port = await freePortFrom(PORT_BASE);
  stage.at = `start-bridge:${port}`;
  const bridge = await startOfficeBridge({ port, stateDir, taskpaneDir: TASKPANE_DIR, tokenTtlMs: 15 * 60_000, log: () => {} });
  console.log(`[office-bridge-synth] 桥已起 :${port}（隔离段 ${PORT_BASE} 起）`);

  const discovery = readDiscovery(stateDir);
  const fp = discovery.publicKeySha256;
  check("S1-发现文件已写（动态端口/指纹/token/pageBaseUrl 齐）",
    discovery.port === port && discovery.publicKeySha256.length === 64 && typeof discovery.bootstrapToken === "string" && discovery.pageBaseUrl === `http://127.0.0.1:${port}/taskpane/`,
    `port=${port}`);

  // A1：无 token
  {
    const { ws, frames } = await dial(port);
    ws.send(JSON.stringify({ kind: "pair", sequence: 1, clientId: "attacker-1", pinnedPublicKeySha256: fp, surface: "word" }));
    check("S1-断言A1 无 token 连接被拒（bootstrap_token_invalid）", !!(await until(frames, isErr("bootstrap_token_invalid"))));
    await closed(ws);
  }
  // A2：伪造 token
  {
    const { ws, frames } = await dial(port);
    ws.send(JSON.stringify({ kind: "pair", sequence: 1, bootstrapToken: "forged-token-value", pinnedPublicKeySha256: fp, surface: "word" }));
    check("S1-断言A2 伪造 token 被拒（同码无区分口径）", !!(await until(frames, isErr("bootstrap_token_invalid"))));
    await closed(ws);
  }
  // C：正常链
  {
    const info = await (await fetch(`http://127.0.0.1:${port}/pair-info`)).json();
    check("S1-pair-info 与发现文件同源（指纹一致）", info.publicKeySha256 === fp);
    const { ws, frames } = await dial(port);
    ws.send(JSON.stringify({ kind: "pair", sequence: 1, bootstrapToken: info.bootstrapToken, clientId: "taskpane-synth", clientName: "juscite-taskpane", pluginVersion: "0.0.0", pinnedPublicKeySha256: fp, surface: "wps" }));
    const ready = await until(frames, (f) => f.kind === "ready");
    check("S1-pair 成功收 ready（serverInstanceId/peerKey）", !!ready && !!ready.serverInstanceId && typeof ready.peerKey === "string", ready?.peerKey ?? "");
    ws.send(JSON.stringify({ kind: "ping", sequence: 2 }));
    check("S1-ping→pong", !!(await until(frames, (f) => f.kind === "pong")));
    ws.send(JSON.stringify({ kind: "subscribe", sequence: 3, topics: ["run.events"] }));
    check("S1-subscribe→response ok", !!(await until(frames, (f) => f.kind === "response" && f.ok === true && f.result?.op === "subscribe")));
    ws.send(JSON.stringify({ kind: "request", sequence: 4, requestId: "synth-1", op: "chat", payload: { text: "合成自测消息", selection: "合成选区" } }));
    const resp = await until(frames, (f) => f.kind === "response" && f.requestId === "synth-1");
    check("S1-request→response（S5 前为桥桩回执）", !!resp && resp.ok === true && !!resp.result?.echo);
    ws.send(JSON.stringify({ kind: "ping", sequence: 9 }));
    check("S1-sequence 跳号被拒（bad_sequence）", !!(await until(frames, isErr("bad_sequence"))));
    ws.close();
    await sleep(200);
  }
  // E：token 轮换后旧值重放被拒
  {
    const staleToken = discovery.bootstrapToken; // C 之前签发的初代 token（已被 pair 轮换）
    const { ws, frames } = await dial(port);
    ws.send(JSON.stringify({ kind: "pair", sequence: 1, bootstrapToken: staleToken, clientId: "replay-old-token", pinnedPublicKeySha256: fp, surface: "word" }));
    check("S1-断言E token 轮换后旧值重放被拒", !!(await until(frames, isErr("bootstrap_token_invalid"))));
    await closed(ws);
  }
  // D：指纹不匹配
  {
    const info = await (await fetch(`http://127.0.0.1:${port}/pair-info`)).json();
    const { ws, frames } = await dial(port);
    ws.send(JSON.stringify({ kind: "pair", sequence: 1, bootstrapToken: info.bootstrapToken, clientId: "wrong-pin", pinnedPublicKeySha256: "f".repeat(64), surface: "word" }));
    check("S1-断言D 公钥指纹钉扎不匹配被拒（public_key_mismatch）", !!(await until(frames, isErr("public_key_mismatch"))));
    await closed(ws);
  }
  // A3：单对端守卫——占位对端在连时，真第三方进程（子进程，不同 PID）持有效 token 也被拒
  {
    const c1 = await dial(port);
    c1.ws.send(JSON.stringify({ kind: "pair", sequence: 1, bootstrapToken: bridge.currentBootstrapToken(), clientId: "holder", pinnedPublicKeySha256: bridge.fingerprint, surface: "word" }));
    await until(c1.frames, (f) => f.kind === "ready");
    const second = await thirdPartyPair(port, bridge.currentBootstrapToken(), bridge.fingerprint);
    check("S1-断言A3 单对端守卫：第三方进程持有效 token 也被拒（peer_already_paired）",
      second.out.includes("OB_CHILD_ERR:peer_already_paired"), `childExit=${second.code} out=${second.out.trim()}`);
    c1.ws.close();
    await sleep(300); // 等服务端清 pairedConn（close 钩子）
  }
  // A1'：第三方进程无 token（子进程直连，独立 PID 面上复核）
  {
    const r = await thirdPartyPair(port, "", bridge.fingerprint);
    check("S1-断言A1' 第三方进程无 token 被拒（子进程面上复核）", r.out.includes("OB_CHILD_ERR:bootstrap_token_invalid"), `childExit=${r.code} out=${r.out.trim()}`);
  }
  // B：token 过期
  {
    await bridge.stop();
    const shortLived = await startOfficeBridge({ port, stateDir, taskpaneDir: TASKPANE_DIR, tokenTtlMs: 120, log: () => {} });
    const expired = shortLived.currentBootstrapToken();
    await sleep(250); // 越过 120ms TTL
    const { ws, frames } = await dial(port);
    ws.send(JSON.stringify({ kind: "pair", sequence: 1, bootstrapToken: expired, clientId: "late-client", pinnedPublicKeySha256: shortLived.fingerprint, surface: "word" }));
    check("S1-断言B token 过期后 pair 报 bootstrap_token_invalid（同义错误）", !!(await until(frames, isErr("bootstrap_token_invalid"))));
    await closed(ws);
    // J：动态端口（port=0 由系统分配——方案 §三·④）
    const dyn = await startOfficeBridge({ port: 0, stateDir, taskpaneDir: TASKPANE_DIR, log: () => {} });
    check("S1-动态端口 port=0 系统分配且发现文件同步", dyn.port > 0 && dyn.port !== port && readDiscovery(stateDir).port === dyn.port, `dynPort=${dyn.port}`);
    await dyn.stop();
    check("S1-G stop() 发现文件清理（动态实例）", !existsSync(join(stateDir, "bridge.json")));
    await shortLived.stop();
  }
  // F：S2 页面零外呼扫描（自有文件；vendor 官方库的已知条件路径见 vendor/officejs/README.md）
  {
    const violations = [];
    const walk = (dir) => {
      for (const e of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, e.name);
        if (e.isDirectory()) { if (e.name !== "vendor") walk(full); continue; }
        if (!/\.(html|js|css)$/.test(e.name)) continue;
        for (const m of readFileSync(full, "utf-8").matchAll(/https?:\/\/[^\s"'`)]+/g)) {
          if (!/^https?:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/.test(m[0])) violations.push(`${e.name}: ${m[0]}`);
        }
      }
    };
    walk(TASKPANE_DIR);
    check("S2-断言F taskpane 自有文件零外呼（非 127.0.0.1 引用=0）", violations.length === 0, violations.slice(0, 3).join("; ") || "clean");
  }
  // S2：页面经桥同源伺服
  {
    const srv = await startOfficeBridge({ port, stateDir, taskpaneDir: TASKPANE_DIR, log: () => {} });
    const r1 = await fetch(`http://127.0.0.1:${port}/taskpane/`);
    const html = await r1.text();
    const r2 = await fetch(`http://127.0.0.1:${port}/taskpane/host-adapters.js`);
    const r3 = await fetch(`http://127.0.0.1:${port}/taskpane/vendor/officejs/office.js`);
    const r4 = await fetch(`http://127.0.0.1:${port}/taskpane/%2e%2e/%2e%2e/package.json`); // 越界读取必须被挡
    check("S2-页面/适配层/本地 office.js 均同源伺服 200 且页面挂双适配层",
      r1.status === 200 && r2.status === 200 && r3.status === 200 && html.includes("host-adapters.js"),
      `page=${r1.status} adapter=${r2.status} officejs=${r3.status} dual=${html.includes("host-adapters.js")}`);
    check("S2-静态路径越界被拒（403/404）", r4.status === 403 || r4.status === 404, `status=${r4.status}`);
    await srv.stop();
  }

  // S4：publish.xml 注入/移除幂等 + 他名条目保留 + 版本门槛（全合成材料，隔离临时目录）
  {
    const jsaddons = mkdtempSync(join(tmpdir(), "juscite-wps-synth-"));
    const URL1 = "http://127.0.0.1:3090/taskpane/";
    const URL2 = "http://127.0.0.1:3091/taskpane/";
    const r1 = injectWpsAddon({ jsaddonsDir: jsaddons, url: URL1 });
    const s1 = wpsAddonState(jsaddons);
    const r2 = injectWpsAddon({ jsaddonsDir: jsaddons, url: URL1 }); // 再注一次（幂等）
    const s2 = wpsAddonState(jsaddons);
    const r3 = injectWpsAddon({ jsaddonsDir: jsaddons, url: URL2 }); // 换端口（原位更新）
    const s3 = wpsAddonState(jsaddons);
    check("S4-注入幂等（重复注入=单条目）+ 换 url 原位更新",
      s1.mine && s1.url === URL1 && s1.total === 1 && s2.total === 1 && s3.mine && s3.url === URL2 && s3.total === 1,
      `t1=${s1.total} t2=${s2.total} t3=${s3.total}`);
    // 他名条目保留：预置一条 AutoClaw 形状的竞品条目（合成等价物，非抄其文案）
    const competitor = `<?xml version="1.0" encoding="utf-8"?>\n<jsplugins>\n  <jspluginonline name="competitor-synth-plugin" type="wps" url="https://competitor.invalid/wps/" enable="true" install="null"/>\n</jsplugins>\n`;
    writeFileSync(join(jsaddons, "publish.xml"), competitor);
    injectWpsAddon({ jsaddonsDir: jsaddons, url: URL1 });
    const s4 = wpsAddonState(jsaddons);
    const keepTxt = readFileSync(join(jsaddons, "publish.xml"), "utf-8");
    const rm1 = removeWpsAddon({ jsaddonsDir: jsaddons });
    const s5 = wpsAddonState(jsaddons);
    const afterRmTxt = readFileSync(join(jsaddons, "publish.xml"), "utf-8");
    check("S4-他名条目逐字保留 + 移除后零自家残留且他名仍在",
      s4.total === 2 && keepTxt.includes('name="competitor-synth-plugin"') && rm1.removed && s5.total === 1 && !s5.mine && afterRmTxt.includes('name="competitor-synth-plugin"') && !afterRmTxt.includes(WPS_PLUGIN_NAME),
      `total=${s4.total}→${s5.total}`);
    // 只剩他名时移除自家（已移除）→ 幂等 no-op；文件不删
    const rm2 = removeWpsAddon({ jsaddonsDir: jsaddons });
    check("S4-移除幂等（无自家条目=no-op 不删文件）", !rm2.removed && wpsAddonState(jsaddons).total === 1);
    // 本单元自建文件且清空 → 删文件回原样
    const jsaddons2 = mkdtempSync(join(tmpdir(), "juscite-wps-synth2-"));
    injectWpsAddon({ jsaddonsDir: jsaddons2, url: URL1 });
    const rm3 = removeWpsAddon({ jsaddonsDir: jsaddons2 });
    check("S4-自建文件清空即删（回到注入前原样）", rm3.fileDeleted && !existsSync(join(jsaddons2, "publish.xml")));
    // 版本门槛：达标/不达标/无法解析
    check("S4-版本门槛（12.1.0.29680 达标、6.12.9 不达标、乱串 fail-closed）",
      versionAtLeast("12.1.0.29680") && versionAtLeast("6.13.0") && !versionAtLeast("6.12.9") && !versionAtLeast("未知版本") && !versionAtLeast(""));
    rmSync(jsaddons, { recursive: true, force: true });
    rmSync(jsaddons2, { recursive: true, force: true });
  }

  rmSync(stateDir, { recursive: true, force: true });

  console.log(`[office-bridge-synth] 共 ${results.length} 项，失败 ${failed}`);
  console.log(failed === 0 ? "OFFICE_BRIDGE_SYNTH_PASS" : "OFFICE_BRIDGE_SYNTH_FAIL");
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error("[office-bridge-synth] 异常退出:", err);
  console.log("OFFICE_BRIDGE_SYNTH_FAIL");
  process.exit(1);
});
