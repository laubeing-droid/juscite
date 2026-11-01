// 功能 #25 文档对比合成用例（施工单-03 任务四验收）：走真桥 :3030 RPC 的材料通道。
// 1 已知改动的两份合成材料 → 增/删/改分类与逐条文本精确对拍；
// 2 两份完全相同 → 零变更诚实空；3 大文档（6000 行合成样本，>100 页当量）散布改动不崩不卡；
// 4 材料名目录穿越显式拒绝；5 缺失材料显式报错。材料全部合成、写本仓 .local 刮刮乐目录。
// 前置：桥 :3030 已运行。末行 COMPARE_PASS / COMPARE_FAIL。
import WebSocket from "ws";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const SCRATCH_WS = join(REPO_ROOT, ".local", `compare-scratch-${Date.now()}`);
const MATERIALS = join(SCRATCH_WS, "materials");
mkdirSync(MATERIALS, { recursive: true });
const WS_URL = process.env.BRIDGE_WS_URL ?? "ws://localhost:3030/ws";

const ws = new WebSocket(WS_URL);
ws.binaryType = "arraybuffer";
const data = { fire: (_b: VSBuffer) => {} };
ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
const isocket = {
  onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
  onClose: () => ({ dispose: () => {} }),
  onEnd: () => ({ dispose: () => {} }),
  write: (b: VSBuffer) => ws.send(b.buffer),
  end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
};
const ch = new ChannelClient(new SocketProtocol(isocket as never)).getChannel("zcode-agent");
const call = <T,>(m: string, a?: unknown) => ch.call<T>(m, a === undefined ? [] : [a]);
await call("helloConversationV4");

const results: Array<{ name: string; ok: boolean; detail: string }> = [];
function check(name: string, ok: boolean, detail: string) {
  results.push({ name, ok, detail });
  console.log(`[compare-synthetic] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}

const listDocs = () => call<{ documents: Array<{ name: string }> }>("listWorkspaceDocuments", { workspacePath: SCRATCH_WS });
const compare = (leftName: string, rightName: string) =>
  call<{
    hunks: Array<{ type: string; aStart: number; bStart: number; oldText: string; newText: string }>;
    stats: { added: number; deleted: number; modified: number };
  }>("compareDocuments", { workspacePath: SCRATCH_WS, leftName, rightName });

// ── 用例 1：已知改动 → 增/删/改 精确对拍 ──
const V1 = [
  "借款合同（第一版）",
  "甲方：张三",
  "乙方：李四",
  "利息：年利率百分之十二。",
  "违约金：日万分之五。",
  "签署页：本合同一式两份。",
].join("\n");
const V2 = [
  "借款合同（第二版）",
  "甲方：张三",
  "乙方：李四",
  "管辖条款：因本合同发生争议，由甲方住所地人民法院管辖。",
  "利息：年利率百分之十二。",
  "违约金：日万分之五。",
].join("\n");
writeFileSync(join(MATERIALS, "对拍-原版.txt"), V1, "utf-8");
writeFileSync(join(MATERIALS, "对拍-新版.txt"), V2, "utf-8");

const listing = await listDocs();
check("材料通道列表", listing.documents.length >= 2 && listing.documents.some((d) => d.name === "对拍-原版.txt"),
  `materials 共 ${listing.documents.length} 份`);

const r1 = await compare("对拍-原版.txt", "对拍-新版.txt");
const kinds = r1.hunks.map((h) => h.type);
const modH = r1.hunks.find((h) => h.type === "mod");
const addH = r1.hunks.find((h) => h.type === "add");
const delH = r1.hunks.find((h) => h.type === "del");
check("增/删/改各一处", r1.stats.added === 1 && r1.stats.deleted === 1 && r1.stats.modified === 1
  && kinds.filter((k) => k === "add").length === 1 && kinds.filter((k) => k === "del").length === 1 && kinds.filter((k) => k === "mod").length === 1,
  `hunks=${JSON.stringify(kinds)} stats=+${r1.stats.added}/-${r1.stats.deleted}/~${r1.stats.modified}`);
check("改条文本精确", !!modH && modH.oldText === "借款合同（第一版）" && modH.newText === "借款合同（第二版）",
  modH ? `「${modH.oldText}」→「${modH.newText}」` : "无 mod hunk");
check("增条文本与位置", !!addH && addH.newText.startsWith("管辖条款") && addH.aStart === 3 && addH.bStart === 3,
  addH ? `aStart=${addH.aStart} bStart=${addH.bStart}` : "无 add hunk");
check("删条文本与位置", !!delH && delH.oldText.startsWith("签署页") && delH.aStart === 5,
  delH ? `aStart=${delH.aStart}` : "无 del hunk");

// ── 用例 2：完全相同 → 零变更 ──
writeFileSync(join(MATERIALS, "相同-A.txt"), V1, "utf-8");
writeFileSync(join(MATERIALS, "相同-B.txt"), V1, "utf-8");
const r2 = await compare("相同-A.txt", "相同-B.txt");
check("相同材料零变更", r2.hunks.length === 0 && r2.stats.added + r2.stats.deleted + r2.stats.modified === 0,
  `hunks=${r2.hunks.length}`);

// ── 用例 3：大文档（6000 行 ≈ 100+ 页当量）散布 40 处改动，不崩不卡 ──
const BIG_LINES = 6000, BIG_EDITS = 40;
const bigA: string[] = [], bigB: string[] = [];
const editAt = new Set<number>();
for (let e = 0; e < BIG_EDITS; e++) editAt.add(Math.floor((e + 0.5) * (BIG_LINES / BIG_EDITS)));
for (let i = 0; i < BIG_LINES; i++) {
  const base = `第${i + 1}条 合成条款：本行系大文档性能样本正文内容，行号 ${i + 1}。`;
  bigA.push(base);
  bigB.push(editAt.has(i) ? `第${i + 1}条 合成条款（修订版措辞）：行号 ${i + 1} 已按对拍要求改写。` : base);
}
writeFileSync(join(MATERIALS, "大文档-原版.txt"), bigA.join("\n"), "utf-8");
writeFileSync(join(MATERIALS, "大文档-新版.txt"), bigB.join("\n"), "utf-8");
const t0 = Date.now();
const r3 = await compare("大文档-原版.txt", "大文档-新版.txt");
const elapsed = Date.now() - t0;
check("大文档不卡死（<15s）", elapsed < 15000, `耗时 ${elapsed}ms`);
check("大文档改动计数精确", r3.stats.modified === BIG_EDITS && r3.stats.added === 0 && r3.stats.deleted === 0,
  `改=${r3.stats.modified}（期望 ${BIG_EDITS}）增=${r3.stats.added} 删=${r3.stats.deleted}`);

// ── 用例 4：目录穿越显式拒绝 ──
let traversalRejected = false, traversalMsg = "";
try {
  await compare("..\\escape.txt", "对拍-原版.txt");
} catch (e) {
  traversalRejected = true;
  traversalMsg = String((e as Error)?.message ?? e);
}
check("目录穿越显式拒绝", traversalRejected, traversalMsg.slice(0, 80));

// ── 用例 5：缺失材料显式报错（不静默空结果）──
let missingRejected = false, missingMsg = "";
try {
  await compare("对拍-原版.txt", "不存在-材料.txt");
} catch (e) {
  missingRejected = true;
  missingMsg = String((e as Error)?.message ?? e);
}
check("缺失材料显式报错", missingRejected, missingMsg.slice(0, 80));

rmSync(SCRATCH_WS, { recursive: true, force: true });
ws.close();
const failed = results.filter((r) => !r.ok);
console.log(failed.length ? "COMPARE_FAIL" : "COMPARE_PASS");
process.exit(failed.length ? 1 : 0);
