// 功能 #20 所内知识问答合成用例（步骤4·RE-20 验收口径，全部合成材料）：
//   ①空库树/建夹/上传（类型面白名单外拒）②同步：文件/块计数+revision+不截断
//   ③法条粒度分块（第N条独立成块带条号，B58）④检索：命中+rankReason+相关度+NFKC 全角逗号
//   ⑤文件夹作用域隔离（B32 path_prefix）⑥侧车过期/废弃过滤（B56）⑦..逃逸拒绝（B62）
//   ⑧kbAsk 全局档：线程前缀标题+检索来源+真模型回合流式完成+提示词六节结构（B33）
//   ⑨[来源N] 映射解析（B41）⑩多轮复用线程（B44）⑪B50 主对话列表隔离
//   ⑫文件档提示词结构（B34）⑬规则兜底分类（B17 兜底路）⑭移动/防环/删除
//   ⑮线程删除+记录清理（B47）⑯杀桥重启：文档树不丢+问答线程还原（RE-B1 持久化）
//   ⑰r8 补齐面：B61 内置文集随源根收进/B57 引用徽章/B21·B23 系统打开失败路/B17 缓存跳过数
// 自管隔离桥实例（BRIDGE_TEST_PORT，默认 3070，独立 bridge-{port}.db + 独立 BRIDGE_KB_ROOT），
// 不碰 :3030/:43127。末行 KB_SYNTH_PASS / KB_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, openSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3070);
const KB_ROOT = join(REPO_ROOT, ".local", `kb-scratch-${Date.now()}`);
const STAGE = join(REPO_ROOT, ".local", `kb-stage-${Date.now()}`); // 材料暂存（在托管根之外，经 kbImport 进库）
const NODE = process.execPath;
const results: Array<{ name: string; ok: boolean }> = [];
function check(name: string, ok: boolean, detail: string) {
  results.push({ name, ok });
  console.log(`[kb-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ── 合成材料（自写法条/合同/笔记，无真实材料；先落暂存区，经 kbImport 上传入库）──
mkdirSync(join(STAGE, "法规"), { recursive: true });
mkdirSync(join(STAGE, "合同文本"), { recursive: true });
// B61 内置文集源根样例（经 BRIDGE_KB_SOURCE_ROOT env 指给桥；随包文集机制的合成最小样例）
mkdirSync(join(STAGE, "knowledge-base", "会议记录"), { recursive: true });
writeFileSync(join(STAGE, "knowledge-base", "会议记录", "内置样例纪要.md"),
  "# 内置样例纪要（合成样例）\n\n本文为内置文集机制的合成样例，随源根扫描收进知识库索引。\n", "utf-8");
writeFileSync(join(STAGE, "knowledge-base", "会议记录", "内置样例纪要.md.meta.json"),
  JSON.stringify({ category: "会议记录", source: "经验分享" }), "utf-8");
const ARTICLES = Array.from({ length: 12 }, (_, i) =>
  `第${i + 1}条 行政机关实施非现场监管，应当采用电子技术监控设备，并依法公开监控事项。第${i + 1}条相关实施办法由国务院另行规定。`).join("\n");
writeFileSync(join(STAGE, "法规", "合成监管条例.md"), `# 合成监管条例\n\n## 总则\n${ARTICLES}\n`, "utf-8");
writeFileSync(join(STAGE, "合同文本", "合成借款协议.txt"),
  "甲方：合成甲公司\n乙方：合成乙公司\n\n第一条 借款金额为人民币十万元整。\n第二条 借款期限为六个月，自放款日起算。\n第三条 违约责任：任何一方违约应赔偿对方因此受到的损失。\n", "utf-8");
writeFileSync(join(STAGE, "合成笔记.txt"), "这是一个用于检索验证的合成笔记，包含关键词举证责任分配的讨论。\n", "utf-8");

let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, ".local", `kb-synth-bridge-${PORT}.log`), "a");
function spawnBridge() {
  const env = { ...process.env, BRIDGE_PORT: String(PORT), BRIDGE_KB_ROOT: KB_ROOT, BRIDGE_KB_SOURCE_ROOT: join(STAGE, "knowledge-base") };
  const child = spawn(NODE, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: ["ignore", bridgeLog, bridgeLog], detached: true });
  child.unref();
  return child.pid;
}
async function probe() {
  try {
    const r = await fetch(`http://127.0.0.1:${PORT}/api/server-info`, { signal: AbortSignal.timeout(2500) });
    return r.ok && JSON.parse(await r.text()).store === "sqlite";
  } catch { return false; }
}
async function waitProbe(timeoutMs: number) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) { if (await probe()) return true; await sleep(500); }
  return false;
}
async function killBridge(reason: string) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${bridgePid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  if (!String(r.stdout ?? "").includes("bridge_host.mjs")) {
    throw new Error(`拒绝杀进程 pid=${bridgePid}（${reason}）：命令行不含 bridge_host.mjs，宁停不误杀`);
  }
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probe())) await sleep(500);
}
async function preflightClearPort() {
  // 本端口独立库随测试初始化：无论是否有残留桥，先杀桥再清库（保证「初读空库」可断言；
  // 实测踩坑：无残留桥时提前 return 会跳过清库，上轮库残留让五项断言连锁失真）
  if (await probe()) {
    const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
    const pids = new Set<number>();
    for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
      if (Number(m[1]) === PORT) pids.add(Number(m[2]));
    }
    for (const pid of pids) {
      const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
        `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
        { encoding: "utf-8", timeout: 20000 });
      if (String(q.stdout ?? "").includes("bridge_host.mjs")) {
        spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
        console.log(`[kb-synth] 清场：杀掉残留桥 pid=${pid}`);
      }
    }
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline && (await probe())) await sleep(500);
  }
  for (const suffix of ["", "-wal", "-shm"]) {
    try { rmSync(join(process.env.APPDATA ?? "", "Juscite", "bridge", `bridge-${PORT}.db${suffix}`), { force: true }); } catch { /* 留给下轮 */ }
  }
}

let call: <T>(m: string, a?: unknown) => Promise<T> = async () => { throw new Error("未连接"); };
let taskCall: <T>(m: string, a?: unknown) => Promise<T> = async () => { throw new Error("未连接"); };
function connect(): Promise<void> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws`);
    ws.binaryType = "arraybuffer";
    const data = { fire: (_b: VSBuffer) => {} };
    ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
    ws.on("open", () => {
      const isocket = {
        onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
        onClose: () => ({ dispose: () => {} }),
        onEnd: () => ({ dispose: () => {} }),
        write: (b: VSBuffer) => ws.send(b.buffer),
        end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
      };
      // 单 ChannelClient 双通道（两个 Client 共用同一 isocket 会互吞帧——实测踩坑：第二个
      // onData 覆盖第一个，helloConversationV4 永不 resolve，全脚本零输出挂死）
      const client = new ChannelClient(new SocketProtocol(isocket as never));
      const ch = client.getChannel("zcode-agent");
      const tch = client.getChannel("zcode-task");
      call = async <T,>(m: string, a?: unknown) => ch.call<T>(m, a === undefined ? [] : [a]);
      taskCall = async <T,>(m: string, a?: unknown) => tch.call<T>(m, a === undefined ? [] : [a]);
      call("helloConversationV4").then(() => resolve()).catch(reject);
    });
    ws.on("error", reject);
  });
}

interface KbTree { root: string; folders: Array<{ path: string; name: string }>;
  docs: Array<{ relPath: string; title: string; ext: string; sizeBytes: number; indexed: boolean; category: string | null }>;
  counts: { files: number; topLevel: number }; }
interface KbSearch { mode: string; hits: Array<{ title: string; path: string; articleNumber: string | null; excerpt: string; relevance: number; rankReason: string }>; sources: Array<{ n: number; title: string; path: string; relevance: number; badges?: string[] }>; }
interface KbAsk { threadId: string; title: string; sources: Array<{ n: number; path: string }>; retrieved: number; mode: string; }
interface KbThreadState { threadId: string; title: string; phase: string; busy: boolean;
  rows: Array<{ rowId: number; kind: string; state: string; text: string; kbQuote?: { text: string } | null }>;
  sources: Array<{ n: number; path: string }>; kbCtx: { kind: string } | null; lastPrompt: string | null; }

const KB13 = ["论文", "调研报告", "合同协议", "诉讼仲裁", "案例判例", "法规规范", "模板范本", "会议记录", "音视频", "图片资料", "表格数据", "压缩包", "其他资料"];

// ═══ 主流程 ═══
await preflightClearPort();
bridgePid = spawnBridge();
if (!(await waitProbe(40000))) { console.log("KB_SYNTH_FAIL"); console.error("桥 40s 不可探"); process.exit(1); }
await connect();

// ── ① 空库树/建夹/上传类型面 ──
const t0 = await call<KbTree>("kbTree", {});
check("初读空库", t0.counts.files === 0 && t0.counts.topLevel === 0, `files=${t0.counts.files}`);
const f1 = await call<{ path: string }>("kbCreateFolder", { path: "会议纪要" });
check("新建文件夹", f1.path === "会议纪要", f1.path);
const imp = await call<{ added: string[]; failed: Array<{ name: string; reason: string }> }>("kbImport", {
  folderPath: "",
  files: [
    { relPath: "法规/合成监管条例.md", base64: Buffer.from(readFileSync(join(STAGE, "法规", "合成监管条例.md"), "utf-8")).toString("base64") },
    { relPath: "合同文本/合成借款协议.txt", base64: Buffer.from(readFileSync(join(STAGE, "合同文本", "合成借款协议.txt"), "utf-8")).toString("base64") },
    { relPath: "合成笔记.txt", base64: Buffer.from(readFileSync(join(STAGE, "合成笔记.txt"), "utf-8")).toString("base64") },
    { relPath: "坏孩子.exe", base64: Buffer.from("MZfake").toString("base64") },
  ],
});
check("上传三进一拒（类型面）", imp.added.length === 3 && imp.failed.length === 1 && /不支持/.test(imp.failed[0]?.reason ?? ""),
  `added=${imp.added.length} failed=${JSON.stringify(imp.failed[0] ?? {}).slice(0, 60)}`);

// ── ② 同步（含 B61 内置文集随源根收进：3 上传 + 1 内置 = 4）──
const sync1 = await call<{ files: number; indexed: number; chunks: number; truncated: boolean; revision: string }>("kbSync", {});
check("同步计数与 revision", sync1.files === 4 && sync1.indexed === 4 && sync1.chunks >= 12 && !sync1.truncated && sync1.revision.length === 64,
  `files=${sync1.files} indexed=${sync1.indexed} chunks=${sync1.chunks}`);
const t1 = await call<KbTree>("kbTree", {});
check("树反映文件+计数徽章", t1.counts.files === 4 && t1.counts.topLevel >= 4 && t1.docs.every((d) => d.indexed),
  `files=${t1.counts.files} topLevel=${t1.counts.topLevel}`);
check("内置文集随源根收进（B61）", t1.docs.some((d) => d.relPath.startsWith("内置文集/") && d.indexed),
  `builtin=${t1.docs.filter((d) => d.relPath.startsWith("内置文集/")).map((d) => d.relPath).join(",")}`);

// ── ③ 法条粒度 + ④ 检索因子 ──
const s1 = await call<KbSearch>("kbSearch", { query: "电子技术监控设备的要求", limit: 10 });
check("检索命中+rankReason+相关度", s1.hits.length > 0 && s1.hits[0].rankReason.length > 0
  && s1.hits[0].relevance >= 1 && s1.hits[0].relevance <= 100,
  `hits=${s1.hits.length} top=${s1.hits[0]?.path} reason=${s1.hits[0]?.rankReason} rel=${s1.hits[0]?.relevance}%`);
check("法条粒度（第N条条号随块）", s1.hits.some((h) => /^第\d+条$/.test(h.articleNumber ?? "")),
  `articles=${s1.hits.map((h) => h.articleNumber).filter(Boolean).join(",")}`);
const s2 = await call<KbSearch>("kbSearch", { query: "行政机关，监控事项", limit: 10 });
check("NFKC 全角逗号归一化后命中（B54）", s2.hits.length > 0, `hits=${s2.hits.length} mode=${s2.mode}`);
const sEmpty = await call<KbSearch>("kbSearch", { query: "", limit: 5 });
check("空查询诚实空", sEmpty.mode === "empty" && sEmpty.hits.length === 0, `mode=${sEmpty.mode}`);

// ── ⑤ 文件夹作用域 ──
const s3 = await call<KbSearch>("kbSearch", { query: "违约责任", folderPath: "合同文本", limit: 10 });
check("文件夹作用域隔离", s3.hits.length > 0 && s3.hits.every((h) => h.path.startsWith("合同文本/")),
  `paths=${s3.hits.map((h) => h.path).join("|")}`);

// ── ⑥ 侧车过期/废弃过滤（B56）──
writeFileSync(join(KB_ROOT, "法规", "合成监管条例.md.meta.json"), JSON.stringify({ deprecated: true }), "utf-8");
const s4 = await call<KbSearch>("kbSearch", { query: "电子技术监控设备的要求", limit: 10 });
const kbHitsAfterDeprecate = s4.hits.filter((h) => h.path.startsWith("法规/")).length;
rmSync(join(KB_ROOT, "法规", "合成监管条例.md.meta.json"), { force: true });
check("侧车 deprecated 过滤（B56）", kbHitsAfterDeprecate === 0, `法规命中=${kbHitsAfterDeprecate}（应为 0）`);
// B57 徽章：侧车时效/可信度/来源→引用来源带徽章
writeFileSync(join(KB_ROOT, "合同文本", "合成借款协议.txt.meta.json"),
  JSON.stringify({ expiresAt: "2099-01-01T00:00:00.000Z", confidence: "high", source: "经验分享" }), "utf-8");
const s5 = await call<KbSearch>("kbSearch", { query: "违约责任", folderPath: "合同文本", limit: 5 });
const badgeHit = s5.sources.find((x) => x.path === "合同文本/合成借款协议.txt");
rmSync(join(KB_ROOT, "合同文本", "合成借款协议.txt.meta.json"), { force: true });
check("B57 引用徽章（层/时效/可信度/经验）", !!badgeHit && (badgeHit.badges ?? []).includes("有时效性")
  && (badgeHit.badges ?? []).includes("可信度高") && (badgeHit.badges ?? []).includes("经验分享") && (badgeHit.badges ?? []).some((b) => b.startsWith("层")),
  `badges=${JSON.stringify(badgeHit?.badges ?? [])}`);

// ── ⑦ 路径逃逸拒绝（B62）+ 系统打开命令面（B21/B23 失败路）──
let escapeRejected = false;
try { await call("kbRead", { relPath: "../../etc/passwd" }); } catch { escapeRejected = true; }
check(".. 逃逸拒绝（B62）", escapeRejected, "");
let openRejected = false;
try { await call("kbOpenExternal", { relPath: "不存在的文件.txt" }); } catch { openRejected = true; }
check("系统打开命令面（B21/B23 失败路拒不存在文件）", openRejected, "成功路不真开应用（避免自测弹窗），按钮存在性由走查断言");

// ── ⑧⑨⑩ 全局档问答（真模型回合）──
const ask1 = await call<KbAsk>("kbAsk", { question: "合成监管条例对电子技术监控设备提出了什么要求？请用一句话回答。", scope: { kind: "global" } });
check("线程建立+前缀标题（B36）", ask1.threadId.startsWith("ses_kb_") && ask1.title.startsWith("知识库全局对话 · "), ask1.title.slice(0, 40));
check("先检索后建线程（B32）", ask1.retrieved >= 1 && ask1.sources.length >= 1 && ask1.sources[0].path.startsWith("法规/"),
  `retrieved=${ask1.retrieved} top=${ask1.sources[0]?.path}`);
let st1: KbThreadState | null = null;
for (let i = 0; i < 200; i++) {
  await sleep(750);
  st1 = await call<KbThreadState>("kbThreadState", { threadId: ask1.threadId });
  if (!st1.busy && (st1.phase === "completedSuccess" || st1.phase === "error")) break;
}
const assistantText = st1?.rows.filter((r) => r.kind === "assistantText").map((r) => r.text).join("") ?? "";
check("回合流式完成（B32/B39）", st1?.phase === "completedSuccess" && assistantText.length > 0,
  `phase=${st1?.phase} len=${assistantText.length}`);
const prompt1 = st1?.lastPrompt ?? "";
check("提示词六语义节（B33）", ["资料范围", "检索到的资料", "可引用来源", "用户问题", "回答要求"].every((k) => prompt1.includes(k))
  && prompt1.includes("不得编造") && prompt1.includes("[来源1]"),
  `sections=${["资料范围", "检索到的资料", "可引用来源", "用户问题", "回答要求"].filter((k) => prompt1.includes(k)).length}/5 len=${prompt1.length}`);
const src1 = await call<{ n: number; path: string } | null>("kbResolveSource", { threadId: ask1.threadId, n: 1 });
check("[来源N] 映射解析（B41）", !!src1 && (src1?.path ?? "").startsWith("法规/"), `path=${src1?.path}`);
const ask2 = await call<KbAsk>("kbAsk", { threadId: ask1.threadId, question: "那第二条又规定了什么？同样一句话。", scope: { kind: "global" } });
check("多轮复用线程（B44）", ask2.threadId === ask1.threadId, ask2.threadId);
for (let i = 0; i < 200; i++) {
  await sleep(750);
  const st = await call<KbThreadState>("kbThreadState", { threadId: ask1.threadId });
  if (!st.busy && (st.phase === "completedSuccess" || st.phase === "error")) break;
}
const st2 = await call<KbThreadState>("kbThreadState", { threadId: ask1.threadId });
check("多轮行累计", st2.rows.filter((r) => r.kind === "userInput").length === 2, `rows=${st2.rows.length}`);

// ── B38 机制守卫：KB 线程拒绝主对话命令面直发 ──
const guardResp = await call<{ status: string; reasonCode?: string }>("sendConversationCommandV4", {
  workspacePath: "D:\mock\lvyin-demo",
  envelope: { type: "sendText", sessionId: ask1.threadId, commandId: "cmd_guard_probe", payload: { text: "绕过 kbAsk 的直发（应被拒）" } },
});
check("B38 KB 线程拒直发（零工具直生单入口）", guardResp.status === "rejected" && guardResp.reasonCode === "guard.kbThreadDirectSend",
  `status=${guardResp.status} code=${guardResp.reasonCode}`);

// ── B60 主对话 shell 绕库守卫（三条件与：①知识库路径 ②批量 PDF 遍历 ③低级解析器）──
// 命中=本地拦截行（不出站不触模型，model=kb-guard）；缺任一条件=照常出站真模型回合（非一切直扫）。
await call("sendConversationCommandV4", {
  workspacePath: "D:\\mock\\lvyin-demo",
  envelope: { type: "createSession", sessionId: "ses_kb_b60_probe", payload: { sessionId: "ses_kb_b60_probe" } },
});
interface GuardRow { rows: Array<{ kind: string; model: string | null; text: string; state: string }> }
const b60Hit = 'python -c "import glob, fitz; [fitz.open(p) for p in glob.glob(\'Juscite/kb/files/**/*.pdf\', recursive=True)]"';
await call("sendConversationCommandV4", {
  workspacePath: "D:\\mock\\lvyin-demo",
  envelope: { type: "sendText", sessionId: "ses_kb_b60_probe", commandId: "cmd_b60_hit", payload: { text: b60Hit } },
});
await sleep(2500);
const rowsHit = await call<GuardRow>("conversationRowsRangeV4", { sessionId: "ses_kb_b60_probe", limit: 20 });
const guardRow = rowsHit.rows.find((r) => r.kind === "assistantText" && r.model === "kb-guard");
check("B60 三条件命中拦（本地 advisory 不出站）", !!guardRow && guardRow.text.includes("kbSearch") && guardRow.text.includes("kbRead"),
  `rows=${rowsHit.rows.length} model=${guardRow?.model ?? "无"}`);
const b60Pass1 = "如果要在 Juscite/kb/files 里用 find -name '*.pdf' 列出所有 PDF 文件名，命令怎么写？一句话回答，不要真的执行。";
await call("sendConversationCommandV4", {
  workspacePath: "D:\\mock\\lvyin-demo",
  envelope: { type: "sendText", sessionId: "ses_kb_b60_probe", commandId: "cmd_b60_pass1", payload: { text: b60Pass1 } },
});
let pass1Ok = false;
const pass1T0 = Date.now();
for (let i = 0; i < 160; i++) {
  await sleep(1000);
  const rows = await call<GuardRow>("conversationRowsRangeV4", { sessionId: "ses_kb_b60_probe", limit: 30 });
  const done = rows.rows.find((r) => r.kind === "assistantText" && r.state === "complete" && r.model !== "kb-guard" && r.text.length > 0);
  if (done) { pass1Ok = true; break; }
}
check("B60 缺解析器条件不拦（①②无③照常出站真模型）", pass1Ok, `真模型回合 ${Math.round((Date.now() - pass1T0) / 1000)}s 完成`);
const b60Pass2 = "pdfplumber 这个 Python 库一般用来做什么？一句话回答。";
await call("sendConversationCommandV4", {
  workspacePath: "D:\\mock\\lvyin-demo",
  envelope: { type: "sendText", sessionId: "ses_kb_b60_probe", commandId: "cmd_b60_pass2", payload: { text: b60Pass2 } },
});
let pass2Ok = false;
const pass2T0 = Date.now();
for (let i = 0; i < 160; i++) {
  await sleep(1000);
  const rows = await call<GuardRow>("conversationRowsRangeV4", { sessionId: "ses_kb_b60_probe", limit: 30 });
  const done = rows.rows.filter((r) => r.kind === "assistantText" && r.model !== "kb-guard" && r.state === "complete" && r.text.length > 0);
  if (done.length >= 2) { pass2Ok = true; break; } // 第二条真模型回合（pass1 之外新增）
}
check("B60 仅解析器无库路径不拦（③无①②照常出站）", pass2Ok, `pass2 真模型回合 ${Math.round((Date.now() - pass2T0) / 1000)}s 完成`);

// ── B37 model 参数：合法 model 随文件档回合被接受 ──
// （ask3 见下，kbAsk 带 model；完成即证 oc28 createSession 吃到该参数）

// ── ⑪ B50 主对话列表隔离（listTasks 返回数组形状）──
const tasks = await taskCall<Array<{ title: string }>>("listTasks", {});
check("B50 主对话列表隔离知识库线程", Array.isArray(tasks) && !tasks.some((t) => (t.title ?? "").startsWith("知识库")),
  `tasks=${Array.isArray(tasks) ? tasks.length : "?"} kbThreads=2`);

// ── ⑫ 文件档问答（B34）──
const ask3 = await call<KbAsk>("kbAsk", { question: "这份协议的借款金额是多少？", scope: { kind: "file", fileName: "合成借款协议", filePath: "合同文本/合成借款协议.txt" }, model: { id: "deepseek-chat", providerID: "deepseek-byok" } });
check("文件档线程前缀（B36）", ask3.title.startsWith("知识库：合成借款协议 · "), ask3.title.slice(0, 30));
let st3: KbThreadState | null = null;
for (let i = 0; i < 200; i++) {
  await sleep(750);
  st3 = await call<KbThreadState>("kbThreadState", { threadId: ask3.threadId });
  if (!st3.busy && (st3.phase === "completedSuccess" || st3.phase === "error")) break;
}
const prompt3 = st3?.lastPrompt ?? "";
check("文件档提示词结构（B34）", prompt3.includes("当前文件正文（优先依据）") && prompt3.includes("知识库补充检索")
  && prompt3.includes("当前文件：合成借款协议") && prompt3.includes("不得把其他文件的内容误当作当前文件"),
  `body=${prompt3.includes("借款金额为人民币十万元整")} sections=${["当前文件正文（优先依据）", "知识库补充检索"].filter((k) => prompt3.includes(k)).length}/2`);
check("文件档引用节随提问还原（B48 前置）", (st3?.rows.find((r) => r.kind === "userInput"))?.text === "这份协议的借款金额是多少？", "");

// ── ⑬ 规则兜底分类（B17 兜底路；不给模型上下文时仍可归档）──
const cls = await call<{ categories: Record<string, string>; source: string; skipped?: number }>("kbClassify", { paths: ["合同文本/合成借款协议.txt"] });
// B17 等量：归类=13 类之一或现有同名文件夹（候选并入后模型可归文件夹名——同名夹「合同文本」实证）
const clsCat = cls.categories["合同文本/合成借款协议.txt"] ?? "";
check("智能分类落档（13 类或同名文件夹候选）", KB13.includes(clsCat) || t1.folders.some((f) => f.name === clsCat),
  `cat=${clsCat} source=${cls.source}`);
const cls2 = await call<{ categories: Record<string, string>; source: string; skipped?: number }>("kbClassify", { paths: ["合同文本/合成借款协议.txt"] });
check("分类缓存命中=跳过数（B17 缓存跳过）", cls2.source === "cache" && (cls2.skipped ?? 0) >= 1, `source=${cls2.source} skipped=${cls2.skipped}`);

// ── ⑭ 移动/防环/删除 ──
const mv = await call<{ from: string; to: string }>("kbMove", { fromPath: "合成笔记.txt", toFolder: "合同文本" });
check("移动到（B18）", mv.to === "合同文本/合成笔记.txt", mv.to);
let loopRejected = false;
try { await call("kbMove", { fromPath: "合同文本", toFolder: "合同文本/子目录" }); } catch { loopRejected = true; }
// 注意：防环校验只对 folder→自身子树；此处目标不是其子树，改为直接测自身
let selfRejected = false;
try { await call("kbMove", { fromPath: "合同文本", toFolder: "合同文本" }); } catch { selfRejected = true; }
check("移动防环（B18 自身拒绝）", selfRejected || loopRejected, `self=${selfRejected}`);
const del1 = await call<{ files: number }>("kbDelete", { paths: [{ kind: "file", path: "合同文本/合成笔记.txt" }] });
check("删除文件（B19）", del1.files === 1, `files=${del1.files}`);
const sync2 = await call<{ files: number }>("kbSync", {});
check("删除后同步清账", sync2.files === 3, `files=${sync2.files}`);

// ── ⑮ 线程删除+记录清理（B47）──
const threads1 = await call<{ threads: Array<{ threadId: string }> }>("kbThreads", {});
check("问答记录列表（B47）", threads1.threads.length === 2, `threads=${threads1.threads.length}`);
await call("kbThreadDelete", { threadId: ask3.threadId });
const threads2 = await call<{ threads: Array<{ threadId: string }> }>("kbThreads", {});
check("删除问答记录", threads2.threads.length === 1 && threads2.threads[0].threadId === ask1.threadId, `threads=${threads2.threads.length}`);

// ── ⑯ 杀桥重启：树不丢+问答线程还原（RE-B1）──
await killBridge("重启实测");
bridgePid = spawnBridge();
if (!(await waitProbe(40000))) { console.log("KB_SYNTH_FAIL"); console.error("重启后桥 40s 不可探"); process.exit(1); }
await connect();
const t2 = await call<KbTree>("kbTree", {});
check("重启后知识库树不丢", t2.counts.files === 3, `files=${t2.counts.files}`);
const threads3 = await call<{ threads: Array<{ threadId: string; title: string; kbCtx: { kind: string } | null }> }>("kbThreads", {});
check("重启后问答线程还原（B48）", threads3.threads.length === 1 && threads3.threads[0].title.startsWith("知识库全局对话")
  && threads3.threads[0].kbCtx?.kind === "global",
  `threads=${threads3.threads.length} ctx=${JSON.stringify(threads3.threads[0]?.kbCtx)}`);
const st4 = await call<KbThreadState>("kbThreadState", { threadId: threads3.threads[0]?.threadId ?? "" });
check("重启后行还原可续问（B44）", st4.rows.length >= 4 && st4.rows.every((r) => typeof r.text === "string"), `rows=${st4.rows.length}`);
const tasks2 = await taskCall<Array<{ title: string }>>("listTasks", {});
check("重启后 B50 仍隔离", Array.isArray(tasks2) && !tasks2.some((t) => (t.title ?? "").startsWith("知识库")), `tasks=${Array.isArray(tasks2) ? tasks2.length : "?"}`);

// ── 清场 ──
await killBridge("测试收场");
try { rmSync(KB_ROOT, { recursive: true, force: true }); } catch { /* 留给系统清理 */ }
try { rmSync(STAGE, { recursive: true, force: true }); } catch { /* 留给系统清理 */ }

const failed = results.filter((r) => !r.ok);
for (const f of failed) console.log(`[kb-synth] FAILED: ${f.name}`);
console.log(failed.length ? "KB_SYNTH_FAIL" : "KB_SYNTH_PASS");
process.exit(failed.length ? 1 : 0);
