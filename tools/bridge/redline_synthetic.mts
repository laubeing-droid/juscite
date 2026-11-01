// 功能 #11 Word 红线改稿合成用例（施工单-03 任务一验收）：自管隔离桥实例（默认 :3055，不碰 :3030）。
// 链路：合成 .docx 落 scratch workspace → redlineRevise（桥内走 oc28 真模型出稿）→ 轮询至 ready →
// 修订项类型/文本校验 → 逐条决定（拒绝首条+接受其余）→ 终稿装配语义校验 → 定稿落盘文件比对 →
// 杀桥重启 → 记录与决定完整可读（持久化不丢）→ 隐身模式 fail-closed 负测。
// 前置：oc28 :43127 已运行（真模型回合，同 e2e 门禁口径）。材料全部合成。末行 REDLINE_PASS / REDLINE_FAIL。
import WebSocket from "ws";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { crc32 } from "node:zlib";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
process.chdir(REPO_ROOT);
const NODE = process.execPath;
const SCRATCH_PORT = Number(process.env.REDLINE_SCRATCH_PORT ?? 3055);
const WS_URL = process.env.BRIDGE_WS_URL ?? `ws://localhost:${SCRATCH_PORT}/ws`;
const SCRATCH_WS = join(REPO_ROOT, ".local", `redline-scratch-${Date.now()}`);
const MATERIALS = join(SCRATCH_WS, "materials");
mkdirSync(MATERIALS, { recursive: true });
const SETTING_PATH = join(homedir(), "AppData", "Roaming", "Juscite", "config", "mock", "setting.json");

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// 小工具：call 包装（首连接对象打字复用）

const results: Array<{ name: string; ok: boolean; detail: string }> = [];
function check(name: string, ok: boolean, detail: string) {
  results.push({ name, ok, detail });
  console.log(`[redline-synthetic] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}

// ── 合成 docx（stored zip，与 skills_service parseZip 契约一致）──
function buildDocxZip(paras: Array<[string, "text" | "del"]>): Buffer {
  const body = paras
    .map(([t, kind]) => kind === "del"
      ? `<w:p><w:del><w:r><w:delText>${t}</w:delText></w:r></w:del></w:p>`
      : `<w:p><w:r><w:t>${t}</w:t></w:r></w:p>`)
    .join("");
  const xml = `<?xml version="1.0"?><w:document xmlns:w="x"><w:body>${body}</w:body></w:document>`;
  const name = Buffer.from("word/document.xml");
  const data = Buffer.from(new TextEncoder().encode(xml));
  const crc = crc32(data);
  const lh = Buffer.alloc(30);
  lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(0, 6); lh.writeUInt16LE(0, 8);
  lh.writeUInt16LE(0, 10); lh.writeUInt16LE(0, 12); lh.writeUInt32LE(crc, 14);
  lh.writeUInt32LE(data.length, 18); lh.writeUInt32LE(data.length, 22);
  lh.writeUInt16LE(name.length, 26); lh.writeUInt16LE(0, 28);
  const cd = Buffer.alloc(46);
  cd.writeUInt32LE(0x02014b50, 0); cd.writeUInt16LE(20, 4); cd.writeUInt16LE(20, 6); cd.writeUInt16LE(0, 8);
  cd.writeUInt16LE(0, 10); cd.writeUInt16LE(0, 12); cd.writeUInt16LE(0, 14); cd.writeUInt32LE(crc, 16);
  cd.writeUInt32LE(data.length, 20); cd.writeUInt32LE(data.length, 24);
  cd.writeUInt16LE(name.length, 28); cd.writeUInt16LE(0, 30); cd.writeUInt16LE(0, 32);
  cd.writeUInt16LE(0, 34); cd.writeUInt16LE(0, 36); cd.writeUInt32LE(0, 38); cd.writeUInt32LE(0, 42);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(0, 8); eocd.writeUInt16LE(1, 10);
  eocd.writeUInt32LE(cd.length + name.length, 12); eocd.writeUInt32LE(lh.length + name.length + data.length, 16);
  return Buffer.concat([lh, name, data, cd, name, eocd]);
}

// ── 桥生命周期（子进程凭据自读注册文件；杀前验命令行含 bridge_host.mjs）──
function spawnBridge(port: number) {
  const child = spawn(NODE, ["--import", "tsx", "tools/bridge/bridge_host.mjs"], {
    cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(port) },
    stdio: ["ignore", "ignore", "ignore"], detached: false,
  });
  return child.pid as number;
}
async function waitProbe(port: number, timeoutMs = 40000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/server-info`, { signal: AbortSignal.timeout(2000) });
      if (r.ok) return true;
    } catch { /* not yet */ }
    await sleep(600);
  }
  return false;
}
function pidOfListener(port: number): number {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === port) return Number(m[2]);
  }
  return 0;
}
function cmdlineLooksLikeBridge(pid: number): boolean {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter 'ProcessId=${pid}').CommandLine`], { encoding: "utf-8", timeout: 20000 });
  return String(r.stdout ?? "").includes("bridge_host.mjs");
}
function killBridge(pid: number, why: string) {
  if (!cmdlineLooksLikeBridge(pid)) throw new Error(`拒绝杀 pid=${pid}（${why}）：命令行不含 bridge_host.mjs`);
  spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
}

type Detail = {
  revision: { revisionId: string; materialName: string; status: string; originalText: string; revisedText: string; finalText: string | null; finalPath: string | null; error: string | null };
  items: Array<{ itemIdx: number; type: string; aStart: number; oldText: string; newText: string; decision: string }>;
};

async function connect(): Promise<{ call: (m: string, a?: unknown) => Promise<never> } & { close: () => void }> {
  const ws = new WebSocket(WS_URL);
  ws.binaryType = "arraybuffer";
  const data = { fire: (_b: VSBuffer) => {} };
  ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
  await new Promise((res, rej) => { ws.on("open", res); ws.on("error", rej); });
  const isocket = {
    onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
    onClose: () => ({ dispose: () => {} }),
    onEnd: () => ({ dispose: () => {} }),
    write: (b: VSBuffer) => ws.send(b.buffer),
    end: () => ws.close(),
    drain: async () => {},
    dispose: () => ws.close(),
  };
  const ch = new ChannelClient(new SocketProtocol(isocket as never)).getChannel("zcode-agent");
  const call = (m: string, a?: unknown) => ch.call<never>(m, a === undefined ? [] : [a]);
  return { call, close: () => ws.close() };
}

// ── 起桥 ──
const pid1 = spawnBridge(SCRATCH_PORT);
if (!(await waitProbe(SCRATCH_PORT))) {
  console.log("REDLINE_FAIL: 隔离桥 40s 不可探");
  process.exit(1);
}
console.log(`[redline-synthetic] 隔离桥 :${SCRATCH_PORT} 就绪（pid=${pid1}）`);

// ── 合成材料 ──
const docxParas: Array<[string, "text" | "del"]> = [
  ["借款合同（送审稿）", "text"],
  ["甲方（出借人）：合成测试甲方", "text"],
  ["第三条 利息：年利率百分之十二（12%），超过法定上限。", "text"],
  ["第四条 违约金：日万分之五，明显过高。", "text"],
  ["第五条 通知条款：本条内容已过时应删除。", "del"],
];
writeFileSync(join(MATERIALS, "合同-红线改稿.docx"), buildDocxZip(docxParas));

try {
  const c1 = await connect();
  await c1.call("helloConversationV4");
  const listing = await c1.call("listWorkspaceDocuments", { workspacePath: SCRATCH_WS }) as { documents: Array<{ name: string; kind: string }> };
  check("材料通道含 docx", listing.documents.some((d) => d.name === "合同-红线改稿.docx" && d.kind === "word"),
    JSON.stringify(listing.documents.map((d) => [d.name, d.kind])));

  const submit = await c1.call("redlineRevise", {
    workspacePath: SCRATCH_WS, materialName: "合同-红线改稿.docx",
    instruction: "利率条款改为不超过 LPR 四倍（年利率百分之十四），违约金改为日万分之三，删除已过时的通知条款，保持条款编号连贯。",
  }) as { revisionId: string; status: string };
  check("提交改稿受理", Boolean(submit.revisionId) && submit.status === "revising", `id=${submit.revisionId}`);

  let detail: Detail | null = null;
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    await sleep(1500);
    detail = await c1.call("redlineGet", { workspacePath: SCRATCH_WS, revisionId: submit.revisionId }) as Detail;
    if (detail.revision.status !== "revising") break;
  }
  const rev = detail?.revision;
  check("改稿完成（模型出稿）", rev?.status === "ready", `status=${rev?.status} err=${rev?.error ?? "无"}`);
  const items = detail?.items ?? [];
  check("修订项非空且类型合法", items.length >= 1 && items.every((it) => ["add", "del", "mod"].includes(it.type)),
    `items=${items.length} types=${items.map((i) => i.type).join(",")}`);
  if (!rev || rev.status !== "ready" || items.length < 1) throw new Error("改稿未收敛，后续用例无法进行");

  // 决定：拒绝第 0 条，其余全部接受
  const c2 = await connect();
  await c2.call("helloConversationV4");
  await c2.call("redlineDecide", { workspacePath: SCRATCH_WS, revisionId: submit.revisionId, itemIdx: 0, decision: "rejected" });
  for (let i = 1; i < items.length; i++) {
    await c2.call("redlineDecide", { workspacePath: SCRATCH_WS, revisionId: submit.revisionId, itemIdx: i, decision: "accepted" });
  }
  const decided = await c2.call("redlineGet", { workspacePath: SCRATCH_WS, revisionId: submit.revisionId }) as Detail;
  const it0 = decided.items.find((i) => i.itemIdx === 0);
  check("决定落库", decided.items.every((i) => i.decision === (i.itemIdx === 0 ? "rejected" : "accepted")),
    `首条=${it0?.decision} 其余=${decided.items.slice(1).every((i) => i.decision === "accepted")}`);

  // 终稿装配语义：被拒条旧文仍在、被受条新文已入、未定=无
  const fin = await c2.call("redlineFinalize", { workspacePath: SCRATCH_WS, revisionId: submit.revisionId }) as { status: string; finalPath: string };
  const finalText = decided.revision.finalText ?? "";
  const rejectedOldIn = items[0].type !== "add" ? finalText.includes(items[0].oldText) : !finalText.includes(items[0].newText);
  const acceptedNewIn = items.slice(1).filter((i) => i.type !== "del").every((i) => finalText.includes(i.newText));
  check("装配语义（拒旧留/受新入）", rejectedOldIn && acceptedNewIn,
    `拒条旧文留=${rejectedOldIn} 受条新文入=${acceptedNewIn}`);
  check("定稿落盘", Boolean(fin.finalPath) && existsSync(fin.finalPath)
    && readFileSync(fin.finalPath, "utf-8") === finalText, fin.finalPath);
  c1.close(); c2.close();

  // ── 杀桥重启 → 记录与决定不丢 ──
  const pid = pidOfListener(SCRATCH_PORT);
  killBridge(pid, "redline 重启持久化验证");
  await sleep(2000);
  const pid2 = spawnBridge(SCRATCH_PORT);
  if (!(await waitProbe(SCRATCH_PORT))) throw new Error("重启后桥不可探");
  const c3 = await connect();
  await c3.call("helloConversationV4");
  const after = await c3.call("redlineGet", { workspacePath: SCRATCH_WS, revisionId: submit.revisionId }) as Detail;
  check("重启后记录完整", after.revision.status === "finalized"
    && after.items.length === items.length
    && after.items.every((i) => i.decision === (i.itemIdx === 0 ? "rejected" : "accepted"))
    && after.revision.finalPath === fin.finalPath,
    `status=${after.revision.status} items=${after.items.length}`);
  const listAfter = await c3.call("redlineList", { workspacePath: SCRATCH_WS }) as { revisions: Array<{ revisionId: string }> };
  check("重启后列表可见", listAfter.revisions.some((r) => r.revisionId === submit.revisionId), `list=${listAfter.revisions.length}`);
  c3.close();

  // ── 隐身模式 fail-closed 负测（读写即还原，窗口 <2s）──
  const prevSetting = existsSync(SETTING_PATH) ? readFileSync(SETTING_PATH, "utf-8") : null;
  let prevObj: Record<string, unknown> = {};
  try { prevObj = prevSetting ? JSON.parse(prevSetting) : {}; } catch { prevObj = {}; }
  writeFileSync(SETTING_PATH, JSON.stringify({ ...prevObj, stealthMode: { enabled: true } }));
  let stealthRejected = false;
  let stealthMsg = "";
  try {
    const c4 = await connect();
    await c4.call("helloConversationV4");
    await c4.call("redlineRevise", { workspacePath: SCRATCH_WS, materialName: "合同-红线改稿.docx", instruction: "负测：隐身模式应拒绝" });
    c4.close();
  } catch (e) {
    stealthRejected = true;
    stealthMsg = String((e as Error)?.message ?? e);
  }
  writeFileSync(SETTING_PATH, JSON.stringify({ ...prevObj, stealthMode: { enabled: false } }));
  if (prevSetting !== null && existsSync(SETTING_PATH)) writeFileSync(SETTING_PATH, prevSetting);
  check("隐身模式 fail-closed", stealthRejected, stealthMsg.slice(0, 80));
} finally {
  const pid = pidOfListener(SCRATCH_PORT);
  if (pid) killBridge(pid, "测试收尾清理");
  rmSync(SCRATCH_WS, { recursive: true, force: true });
}

const failed = results.filter((r) => !r.ok);
console.log(failed.length ? "REDLINE_FAIL" : "REDLINE_PASS");
process.exit(failed.length ? 1 : 0);

