// 一次性走查驱动：功能 #20 知识库 UI 真形态走查（CDP 9223 独立调试 Chrome + vite 5173 + 桥 :3030）。
// 断言：三栏渲染/种子文件行/计数徽章/文件夹导航/文件页预览/上下文档标签/问答真回合（先检索
// 后回答流式上屏）/[来源N] 锚点点击开文件/问答记录还原与删除；截图落 evidence 目录。
// 桥侧：:3030 若在跑旧代码（无 kb* 通道）→核验命令行后重启换新（ci_gate 升级代偿同款）。
// 用法: node tools/bridge/kb_walk.mjs <截图输出目录>
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const CDP = process.env.CDP_PORT ? "http://127.0.0.1:" + process.env.CDP_PORT : "http://127.0.0.1:9223";
const OUT = process.argv[2] ?? join("evidence", "步骤4-所内知识问答-RE20-20261027");
mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`[kb-walk] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 桥侧：确保 :3030 跑的是带 kb* 通道的新代码 ──
async function httpProbe(port = 3030) {
  try {
    const r = await fetch(`http://127.0.0.1:${port}/api/server-info`, { signal: AbortSignal.timeout(2500) });
    return r.ok;
  } catch { return false; }
}
// 知识库面能力代（/api/server-info.kb）：旧桥缺标记 → 换新（与 ci_gate 升级代偿同款）
async function kbCapable() {
  try {
    const r = await fetch("http://127.0.0.1:3030/api/server-info", { signal: AbortSignal.timeout(2500) });
    return r.ok && JSON.parse(await r.text()).kb === 1;
  } catch { return false; }
}
function listenerPids(port) {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const pids = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === port) pids.add(Number(m[2]));
  }
  return [...pids];
}
function cmdlineOf(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  return String(r.stdout ?? "").trim();
}
async function ensureKbBridge() {
  // RPC 探活：kbTree 应答即视为新桥
  const kbAlive = await (async () => {
    try {
      const t = await rpcCall("kbTree", {});
      return Boolean(t?.counts);
    } catch { return false; }
  })();
  if (kbAlive && (await kbCapable())) return;
  console.log("[kb-walk] :3030 桥缺 kb 通道或能力代（旧代码在跑）→ 核验后重启换新");
  for (const pid of listenerPids(3030)) {
    const cl = cmdlineOf(pid);
    if (cl.includes("bridge_host.mjs")) {
      spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
      console.log(`[kb-walk] 杀旧桥 pid=${pid}`);
    } else {
      console.log(`[kb-walk] 跳过非桥进程 pid=${pid}`);
    }
  }
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline && (await httpProbe())) await sleep(500);
  const fd = spawnSync("node", ["-e", "process.stdout.write('1')"], { encoding: "utf-8" });
  void fd;
  const { openSync } = await import("node:fs");
  const log = openSync(".local/kb-walk-bridge-3030.log", "a");
  const child = spawn(process.execPath, ["--import", "tsx", "tools/bridge/bridge_host.mjs"],
    { cwd: process.cwd(), stdio: ["ignore", log, log], detached: true, env: { ...process.env, BRIDGE_PORT: "3030" } });
  child.unref();
  const dl2 = Date.now() + 40000;
  while (Date.now() < dl2 && !(await httpProbe())) await sleep(500);
  if (!(await httpProbe())) throw new Error("桥 :3030 换新后 40s 不可探");
  console.log("[kb-walk] 新桥已拉起");
}

// ── RPC 客户端（种子材料/清理用）──
let rpcCall = async () => { throw new Error("rpc 未连接"); };
async function rpcConnect() {
  const ws = new WebSocket("ws://127.0.0.1:3030/ws");
  ws.binaryType = "arraybuffer";
  const data = { fire: (_b) => {} };
  ws.on("message", (buf) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
  await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); setTimeout(() => j(new Error("ws open timeout")), 8000); });
  const isocket = {
    onData: (l) => { data.fire = l; return { dispose: () => {} }; },
    onClose: () => ({ dispose: () => {} }),
    onEnd: () => ({ dispose: () => {} }),
    write: (b) => ws.send(b.buffer),
    end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
  };
  // 单 ChannelClient 双通道（与 kb_synthetic 同款教训：两个 Client 互吞帧）
  const client = new ChannelClient(new SocketProtocol(isocket));
  const ch = client.getChannel("zcode-agent");
  rpcCall = async (m, a) => ch.call(m, a === undefined ? [] : [a]);
  await rpcCall("helloConversationV4");
}

// ── CDP 驱动 ──
function getJson(path) {
  return new Promise((res, rej) => {
    import("node:http").then(({ default: http }) => {
      http.get(CDP + path, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => res(JSON.parse(d))); }).on("error", rej);
    });
  });
}
let ws = null;
let mid = 0; const pending = new Map();
async function connect() {
  const fresh = (await getJson("/json/list")).find((t) => t.type === "page" && (t.url || "").includes("localhost:5173"));
  if (!fresh) throw new Error("NO_5173_TAB");
  ws = new WebSocket(fresh.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 });
  ws.on("message", (raw) => { const m = JSON.parse(raw.toString()); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
  // 实测踩坑（W16 轮）：CDP 套接字死亡后 send() 永不结案、evalJs 的 catch 永不触发，整单挂死
  // ——socket close/error 时拒绝全部在途 pending（evalJs 捕获后走既有重连路径）。
  ws.on("close", () => { for (const [, p] of pending) p.rej(new Error("CDP socket closed")); pending.clear(); });
  ws.on("error", () => { for (const [, p] of pending) p.rej(new Error("CDP socket error")); pending.clear(); });
  await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); setTimeout(() => j(new Error("ws open timeout")), 8000); });
}
const send = (method, params = {}, timeoutMs = 20000) => new Promise((res, rej) => {
  const id = ++mid;
  const timer = setTimeout(() => { pending.delete(id); rej(new Error("CDP timeout: " + method)); }, timeoutMs);
  pending.set(id, { res: (v) => { clearTimeout(timer); res(v); }, rej: (e) => { clearTimeout(timer); rej(e); } });
  ws.send(JSON.stringify({ id, method, params }));
});
const withTimeout = (p, ms, tag) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error("RPC timeout: " + tag)), ms))]);
async function evalJs(expr) {
  for (let i = 0; i < 3; i++) {
    try {
      const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
      if (r.exceptionDetails) throw new Error("EXC: " + (r.exceptionDetails.exception?.description ?? r.exceptionDetails.text));
      return r.result?.value;
    } catch (e) {
      if (i === 2) throw e;
      await sleep(800); await connect();
    }
  }
}
async function shot(name) {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(r.data, "base64"));
}
async function clickAt(el) {
  const rect = await evalJs(`(() => { const el = ${el}; if (!el) return null; el.scrollIntoView({ block: "center" }); const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  if (!rect) return false;
  for (const type of ["mousePressed", "mouseReleased"]) {
    await send("Input.dispatchMouseEvent", { type, x: rect.x, y: rect.y, button: "left", clickCount: 1 });
  }
  return true;
}
const q = (sel) => `document.querySelector('${sel}')`;
async function typeInto(sel, text) {
  if (!(await clickAt(q(sel)))) return false;
  await evalJs(`(() => { const el = document.querySelector('${sel}'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, ""); el.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  await send("Input.insertText", { text });
  return true;
}
// reload 后轮询进板（boot 完成前侧栏不存在）
async function gotoKb(maxMs = 45000) {
  const deadline = Date.now() + maxMs;
  while (Date.now() < deadline) {
    await evalJs("location.reload()").catch(() => {});
    await sleep(2500);
    const dl = Date.now() + 8000;
    while (Date.now() < dl) {
      const ok = await evalJs(`Boolean(document.querySelector('[data-testid="knowledge-base-sidebar-open"]'))`).catch(() => false);
      if (ok) break;
      await sleep(600);
    }
    const clicked = await clickAt(q('[data-testid="knowledge-base-sidebar-open"]')).catch(() => false);
    if (clicked) {
      const dl2 = Date.now() + 8000;
      while (Date.now() < dl2) {
        const panel = await evalJs(`Boolean(document.querySelector('[data-testid="kb-panel"]'))`).catch(() => false);
        if (panel) return true;
        await sleep(500);
      }
    }
  }
  return false;
}

// ═══ 主流程 ═══
await rpcConnect();
await ensureKbBridge();
await rpcConnect(); // 换桥后重连

// ── 种子合成材料（走 kbImport 真上传链；名称带合成前缀，收尾清理）──
// 开工先清上轮残留（同内容再传 sync 会按 hash 跳过致 indexed=0 断言失真——实测踩坑）
try {
  await rpcCall("kbDelete", { paths: [{ kind: "folder", path: "合成法规" }, { kind: "folder", path: "合成合同" }] });
} catch { /* 首轮无残留 */ }
const seedFiles = [
  { relPath: "合成法规/合成监管条例.md", text: "# 合成监管条例\n\n" + Array.from({ length: 8 }, (_, i) => `第${i + 1}条 行政机关实施非现场监管，应当采用电子技术监控设备，并依法公开监控事项。第${i + 1}条由国务院另行制定办法。`).join("\n") + "\n" },
  { relPath: "合成合同/合成借款协议.txt", text: "甲方：合成甲公司\n乙方：合成乙公司\n\n第一条 借款金额为人民币十万元整。\n第二条 借款期限为六个月。\n第三条 违约责任：任何一方违约应赔偿对方损失。\n" },
];
const imp = await rpcCall("kbImport", { folderPath: "", files: seedFiles.map((f) => ({ relPath: f.relPath, base64: Buffer.from(f.text, "utf-8").toString("base64") })) });
const sync1 = await rpcCall("kbSync", {});
check("种子落库（上传+同步）", imp.added.length === 2 && sync1.files >= 2 && sync1.indexed >= 2,
  `added=${imp.added.length} files=${sync1.files} indexed=${sync1.indexed}`);

// ── CDP ──
let dialogAccept = false;
await connect();
await send("Page.enable");
await send("Runtime.enable");
await send("Page.enable").catch(() => {});
// window.confirm 自动接受（记录删除确认用）
ws.on("message", async (raw) => {
  const m = JSON.parse(raw.toString());
  if (m.method === "Page.javascriptDialogOpening" && dialogAccept) {
    await send("Page.handleJavaScriptDialog", { accept: true }).catch(() => {});
  }
});
await evalJs("1").catch(async () => { await connect(); });
await send("Page.bringToFront", {}).catch(() => {});
await send("Emulation.setFocusEmulationEnabled", { enabled: true }).catch(() => {});
await sleep(1200);

// W1 进板
const entered = await gotoKb();
check("W1 侧栏入口进板", entered, "");
if (!entered) { console.log("KB_WALK_FAIL"); process.exit(1); }

// W2 三栏（等树数据面落位：空表也可能是合法空态，等文件表或空态二者其一出现）
for (let i = 0; i < 10; i++) {
  const ready = await evalJs(`Boolean(document.querySelector('[data-testid="kb-file-table"]') || document.querySelector('[data-testid="kb-empty"]'))`).catch(() => false);
  if (ready) break;
  await sleep(600);
}
const cols = await evalJs(`(() => ({
  sidebar: Boolean(document.querySelector('[data-testid="kb-sidebar"]')),
  table: Boolean(document.querySelector('[data-testid="kb-file-table"]')),
  qa: Boolean(document.querySelector('[data-testid="kb-qa-sidebar"]')),
}))()`);
check("W2 三栏渲染（侧栏/文件表/问答栏）", cols.sidebar && cols.table && cols.qa, JSON.stringify(cols));

// W3 计数徽章 + 文件行
await sleep(800);
const badge = await evalJs(`document.querySelector('[data-testid="kb-all-count"]')?.textContent ?? ""`);
const rowTexts = await evalJs(`Array.from(document.querySelectorAll('[data-testid="kb-row"]')).map((e) => e.textContent.trim())`);
check("W3 计数徽章+种子行（根=文件夹行）", badge.trim().length > 0 && rowTexts.some((r) => r.includes("合成法规")),
  `badge=${badge} rows=${rowTexts.join("|").slice(0, 80)}`);
await shot("kb-walk-1-panel.png");

// W4 文件夹导航（点击侧栏文件夹条目——钉种子夹「合成法规」，内置文集收进后首项不再一定是它）
const folderIdx = await evalJs(`Array.from(document.querySelectorAll('[data-testid="kb-folder-item"]')).findIndex((e) => e.textContent.includes("合成法规"))`);
const folderClicked = folderIdx >= 0 && await clickAt(`document.querySelectorAll('[data-testid="kb-folder-item"]')[${folderIdx}]`);
await sleep(900);
const crumb = await evalJs(`document.querySelector('[data-testid="kb-breadcrumb"]')?.textContent ?? ""`);
const inDocs = await evalJs(`Array.from(document.querySelectorAll('[data-testid="kb-doc-name"]')).map((e) => e.textContent.trim())`);
check("W4 文件夹导航+面包屑+夹内文件行", folderClicked && crumb.includes("合成") && inDocs.length > 0,
  `crumb=${crumb.slice(0, 40)} docs=${inDocs.join("|").slice(0, 50)}`);

// W5 文件页（双栏+预览）
const docClicked = await clickAt(q('[data-testid="kb-doc-name"]'));
await sleep(1500);
const filePage = await evalJs(`(() => ({
  page: Boolean(document.querySelector('[data-testid="kb-file-page"]')),
  preview: (document.querySelector('[data-testid="kb-preview-text"]')?.textContent ?? "").slice(0, 60),
  scopeTag: document.querySelector('[data-testid="kb-qa-scope-tag"]')?.textContent ?? "",
  placeholder: document.querySelector('[data-testid="kb-qa-input"]')?.placeholder ?? "",
  headerSize: /[0-9]+([.][0-9]+)? (B|KB|MB)/.test(document.querySelector('[data-testid="kb-file-page"]')?.querySelector("header")?.textContent ?? ""),
  openBtn: Boolean(document.querySelector('[data-testid="kb-open-external-header"]')),
}))()`);
check("W5 文件页双栏+正文预览", filePage.page && filePage.preview.trim().length > 10, `preview=${filePage.preview.slice(0, 30)}`);
check("W5b 文件页头部大小+系统打开钮（B23）", filePage.headerSize && filePage.openBtn, JSON.stringify({ headerSize: filePage.headerSize, openBtn: filePage.openBtn }));
check("W6 文件档上下文标签+占位（B27/B31）", filePage.scopeTag.startsWith("文件 · ") && filePage.placeholder.includes("当前文件"),
  `tag=${filePage.scopeTag} ph=${filePage.placeholder}`);
const modelSel = await evalJs(`(() => {
  const el = document.querySelector('[data-testid="kb-model-select"]');
  return el ? { options: Array.from(el.options).map((o) => o.textContent), value: el.value } : null;
})()`);
check("W6b 文件档模型选择器（B37）", !!modelSel && modelSel.options.some((o) => o.includes("跟随对话")),
  `opts=${modelSel ? modelSel.options.join("|").slice(0, 60) : "none"}`);

// W6c 文件页问答栏可开合（B26 常驻可收起）：点收起→问答栏消失→再点→恢复
await clickAt(q('[data-testid="kb-file-chat-toggle"]'));
await sleep(500);
const qaCollapsed = await evalJs(`!document.querySelector('[data-testid="kb-qa-sidebar"]')`);
await clickAt(q('[data-testid="kb-file-chat-toggle"]'));
await sleep(500);
const qaRestored = await evalJs(`Boolean(document.querySelector('[data-testid="kb-qa-sidebar"]'))`);
check("W6c 文件页问答栏开合（B26）", qaCollapsed && qaRestored, `collapsed=${qaCollapsed} restored=${qaRestored}`);
await shot("kb-walk-2-filepage.png");

// W7 返回列表
await clickAt(q('[data-testid="kb-file-back"]'));
await sleep(600);
const backOk = await evalJs(`Boolean(document.querySelector('[data-testid="kb-file-table"]'))`);
check("W7 返回列表", backOk, "");

// W8 全局档问答真回合（先检索后回答，流式上屏）
await evalJs(`(() => { const b = document.querySelector('[data-testid="kb-folder-item"]'); })()`);
// 回根目录
await evalJs(`(() => { const up = document.querySelector('[data-testid="kb-go-up"]'); if (up && !up.disabled) up.click(); return true; })()`);
await sleep(500);
// 列表视图问答侧栏为独立实例：W7 返回后存在重挂载窗口，输入可能落在已卸载元素上
// （实测踩坑：vite 重编译后挂载变慢必现）——轮询等输入就位+输入回读校验+最多三试。
let asked = false;
for (let attempt = 0; attempt < 3 && !asked; attempt++) {
  let ok = false;
  const dl = Date.now() + 6000;
  while (Date.now() < dl) {
    ok = await evalJs(`Boolean(document.querySelector('[data-testid="kb-qa-input"]'))`).catch(() => false);
    if (ok) break;
    await sleep(500);
  }
  if (!ok) { await sleep(1200); continue; }
  await typeInto('[data-testid="kb-qa-input"]', "合成借款协议的借款金额是多少？一句话回答。");
  const typed = await evalJs(`(document.querySelector('[data-testid="kb-qa-input"]')?.value ?? "").length`);
  if (!typed) { await sleep(1000); continue; }
  await clickAt(q('[data-testid="kb-qa-send"]'));
  await sleep(2000);
  const sent = await evalJs(`Boolean(document.querySelector('[data-testid="kb-msg-user"]'))`).catch(() => false);
  if (sent) { asked = true; break; }
}
check("W8 发送（输入行清空 B30）", asked, "");

await sleep(2500);
const during = await evalJs(`(() => ({
  user: Boolean(document.querySelector('[data-testid="kb-msg-user"]')),
  inputCleared: (document.querySelector('[data-testid="kb-qa-input"]')?.value ?? "x") === "",
}))()`);
check("W9 用户行上屏+输入已清空", during.user && during.inputCleared, JSON.stringify(during));
// 轮询回答完成（真模型回合，≤150s）
let answerText = "";
for (let i = 0; i < 100; i++) {
  await sleep(1500);
  answerText = await evalJs(`Array.from(document.querySelectorAll('[data-testid="kb-msg-assistant"]')).map((e) => e.textContent).join("")`).catch(() => "");
  if (answerText && !answerText.includes("回答生成中") && answerText.length > 10) break;
}
check("W10 回答流式完成（真模型回合）", answerText.length > 10, `len=${answerText.length} head=${answerText.slice(0, 50)}`);
const anchors = await evalJs(`document.querySelectorAll('[data-testid="kb-source-anchor"]').length`);
check("W11 [来源N] 锚点渲染（B40）", anchors > 0, `anchors=${anchors}`);
await shot("kb-walk-3-qa-answer.png");

// W12 锚点点击开文件（B41）
if (anchors > 0) {
  await clickAt(q('[data-testid="kb-source-anchor"]'));
  await sleep(1200);
  const opened = await evalJs(`(() => ({
    filePage: Boolean(document.querySelector('[data-testid="kb-file-page"]')),
    name: document.querySelector('[data-testid="kb-file-page"]')?.textContent?.includes("合成借款协议"),
  }))()`);
  check("W12 来源锚点点击开文件", opened.filePage && opened.name, JSON.stringify(opened));
  await clickAt(q('[data-testid="kb-file-back"]'));
  await sleep(500);
} else {
  check("W12 来源锚点点击开文件", false, "无锚点可点");
}
await shot("kb-walk-4-after-source-click.png");

// W13 问答记录还原+删除（B47/B48）
await clickAt(q('[data-testid="kb-tab-records"]'));
await sleep(1500);
const recs = await evalJs(`Array.from(document.querySelectorAll('[data-testid="kb-record-item"]')).map((e) => e.textContent.slice(0, 30))`);
check("W13 问答记录列表（B47）", recs.length >= 1, `recs=${recs.join("|").slice(0, 60)}`);
if (recs.length >= 1) {
  dialogAccept = true;
  await clickAt(q('[data-testid="kb-record-item"]'));
  await sleep(1500);
  const restored = await evalJs(`(() => ({
    msgs: document.querySelectorAll('[data-testid="kb-msg-user"]').length,
    tag: document.querySelector('[data-testid="kb-qa-scope-tag"]')?.textContent ?? "",
  }))()`);
  check("W14 记录还原消息流（B48）", restored.msgs >= 1, JSON.stringify(restored));
  await shot("kb-walk-5-record-restore.png");
}

// W16 文件档引用卡随发送消费（B30 括注）：编程选区→mouseup 出工具条→问 AI 挂卡→发送→
// 卡随发送消失+输入行清空+用户行携带引用（乐观行 kbQuote）；回答完成后再清场（防在途回合）。
// 整块 try/catch 兜底：W16 失败降级为该项 FAIL，不拖死后续清场（实测踩坑：面板被踢出工作区时
// 无兜底会连累整单挂死）。
try {
  await clickAt(q('[data-testid="kb-tab-files"]'));
  await sleep(800);
  const fIdx = await evalJs(`Array.from(document.querySelectorAll('[data-testid="kb-folder-item"]')).findIndex((e) => e.textContent.includes("合成法规"))`);
  if (fIdx >= 0) await clickAt(`document.querySelectorAll('[data-testid="kb-folder-item"]')[${fIdx}]`);
  await sleep(800);
  await clickAt(q('[data-testid="kb-doc-name"]'));
  await sleep(1800);
  const armed = await evalJs(`(() => {
    const node = document.querySelector('[data-testid="kb-preview-text"]');
    if (!node) return "no-preview";
    const range = document.createRange();
    range.selectNodeContents(node);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    // mouseup 须发自预览节点向上冒泡经过容器（onMouseUp 挂在容器 div；对祖先 section 派发
    // 不经过容器=React 合成事件永不触发——实测踩坑）
    node.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    return String(sel).length;
  })()`);
  // 工具条=React setState 异步出画（实测踩坑：同一表达式同步读恒 false）——轮询等它出现
  let toolbarUp = false;
  for (let i = 0; i < 8 && armed !== "no-preview"; i++) {
    toolbarUp = await evalJs(`Boolean(document.querySelector('[data-testid="kb-sel-toolbar"]'))`);
    if (toolbarUp) break;
    await sleep(500);
  }
  let w16 = { card: false, input: "x", quoteGone: false, userRowQuote: false };
  if (toolbarUp) {
    await clickAt(q('[data-testid="kb-sel-ask"]'));
    await sleep(400);
    let cardUp = false;
    for (let i = 0; i < 6; i++) {
      cardUp = await evalJs(`Boolean(document.querySelector('[data-testid="kb-quote-card"]'))`);
      if (cardUp) break;
      await sleep(500);
    }
    for (let attempt = 0; cardUp && attempt < 3; attempt++) {
      const ok = await typeInto('[data-testid="kb-qa-input"]', "划选内容里第 1 条讲了什么？一句话。");
      if (!ok) { await sleep(1000); continue; }
      await clickAt(q('[data-testid="kb-qa-send"]'));
      await sleep(1500);
      w16 = await evalJs(`(() => ({
        card: true,
        input: document.querySelector('[data-testid="kb-qa-input"]')?.value ?? "x",
        quoteGone: !document.querySelector('[data-testid="kb-quote-card"]'),
        userRowQuote: (() => { const rows = document.querySelectorAll('[data-testid="kb-msg-user"]'); const last = rows[rows.length - 1]; return Boolean(last && last.textContent.includes("第1条")); })(),
      }))()`);
      if (w16.quoteGone && w16.userRowQuote) break;
      await sleep(1200);
    }
  }
  const w16ctx = await evalJs(`(() => ({
    page: Boolean(document.querySelector('[data-testid="kb-file-page"]')),
    preview: Boolean(document.querySelector('[data-testid="kb-preview-text"]')),
    selLen: String(window.getSelection() ?? "").length,
  }))()`).catch(() => ({}));
  check("W16 引用卡随发送消费（B30：卡消失+输入清空+用户行带引用）",
    w16.card && w16.quoteGone && w16.input === "" && w16.userRowQuote,
    JSON.stringify({ ...w16, armed, toolbarUp, ...w16ctx }));
  await shot("kb-walk-6-quote-consumed.png");
  // 等本回合回答完成再清场（防在途回合撞 W15 删文件）
  for (let i = 0; i < 100; i++) {
    await sleep(1500);
    const done = await evalJs(`Array.from(document.querySelectorAll('[data-testid="kb-msg-assistant"]')).some((e) => e.textContent.length > 10 && !e.textContent.includes("回答生成中"))`).catch(() => false);
    if (done) break;
  }
} catch (e) {
  check("W16 引用卡随发送消费（B30：卡消失+输入清空+用户行带引用）", false, String(e).slice(0, 80));
}

// ── 清场（删种子文件+同步；桥留给门禁复用；RPC 带超时防挂死）──
try {
  await withTimeout(rpcCall("kbDelete", { paths: [{ kind: "folder", path: "合成法规" }, { kind: "folder", path: "合成合同" }] }), 30000, "kbDelete");
  await withTimeout(rpcCall("kbSync", {}), 60000, "kbSync");
  const t = await withTimeout(rpcCall("kbTree", {}), 30000, "kbTree");
  const left = t.docs.filter((d) => d.relPath.startsWith("合成")).length;
  check("W15 清场（合成材料出库）", left === 0, `left=${left}`);
} catch (e) {
  check("W15 清场（合成材料出库）", false, String(e).slice(0, 60));
}

const failed = results.filter((r) => !r.ok);
console.log(failed.length ? "KB_WALK_FAIL" : "KB_WALK_PASS");
process.exit(failed.length ? 1 : 0);
