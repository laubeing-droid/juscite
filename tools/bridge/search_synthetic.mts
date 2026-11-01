// 功能 #15 案内文档搜索合成用例（RE-15 §5 验收）：对既有会话的完成 chunk 做 4 类断言——
// 1 FTS 模式命中已知词；2 短词（2 字）回落 LIKE 命中；3 无命中诚实空；4 单案作用域隔离。
// 前置：桥 :3030 已运行且目标会话已完成至少一轮（无则先跑 persist/latency 探针造数）。
// 末行 SEARCH_PASS / SEARCH_FAIL。合成材料。
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";

const ws = new WebSocket("ws://localhost:3030/ws");
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
const search = (sessionId: string, query: string) =>
  call<{ mode: string; results: Array<{ kind: string; text: string }> }>("searchSessionDocuments", {
    workspacePath: "D:\\mock\\lvyin-demo", sessionId, query, limit: 8,
  });

const results: Array<{ name: string; ok: boolean; detail: string }> = [];
function check(name: string, ok: boolean, detail: string) {
  results.push({ name, ok, detail });
  console.log(`[search-synthetic] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}

// 用例素材：取库里任一有完成行的会话（从 sessions-index reconcile 不适用，直接按已知验收会话；缺省时提示造数）
const stateFile = ".local/ci-gate-logs";
const { readdirSync, readFileSync } = await import("node:fs");
let sessionId = "";
let probeWord = "持久化";
try {
  const dirs = readdirSync(stateFile).filter((d) => d.startsWith("persist-")).sort();
  for (let i = dirs.length - 1; i >= 0 && !sessionId; i--) {
    const f = `${stateFile}/${dirs[i]}/persist-state.json`;
    try {
      const st = JSON.parse(readFileSync(f, "utf-8"));
      if (st.sessionId && st.rows?.length >= 2) { sessionId = st.sessionId; probeWord = (st.rows.find((r: { kind: string }) => r.kind === "assistantText")?.text ?? "持久化").slice(0, 3); }
    } catch { /* 该轮无状态文件 */ }
  }
} catch { /* 目录缺失 */ }
if (!sessionId) { console.log("SEARCH_FAIL: 无可用合成会话（先跑 ci_gate persist 造数）"); process.exit(1); }
console.log(`[search-synthetic] 目标会话 ${sessionId}（探针词「${probeWord}」取自其助手回复首 3 字）`);

const r1 = await search(sessionId, probeWord);
check("FTS 模式命中", r1.mode === "fts" && r1.results.length > 0 && r1.results.some((x) => x.text.includes(probeWord)),
  `mode=${r1.mode} hits=${r1.results.length}`);

const r2 = await search(sessionId, probeWord.slice(0, 2));
check("短词 LIKE 回落", (r2.mode === "like" || r2.mode === "fts") && r2.results.length > 0,
  `mode=${r2.mode} hits=${r2.results.length}`);

const r3 = await search(sessionId, "绝不存在的词组xyzq");
check("无命中诚实空", r3.results.length === 0, `mode=${r3.mode} hits=${r3.results.length}`);

const r0 = await search(sessionId, probeWord);
const otherSession = "ses_" + "x".repeat(10);
const r4 = await search(otherSession, probeWord);
check("单案作用域隔离", r0.results.length > 0 && r4.results.length === 0,
  `本案 hits=${r0.results.length} 异案 hits=${r4.results.length}`);

ws.close();
const failed = results.filter((r) => !r.ok);
console.log(failed.length ? "SEARCH_FAIL" : "SEARCH_PASS");
process.exit(failed.length ? 1 : 0);
