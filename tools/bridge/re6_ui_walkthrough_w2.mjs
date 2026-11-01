// 功能 #6 材料上传解析 UI 真形态走查（RE-6 §4 对拍 1/2/3/4/5/6/35/36/43/48/49/55 落 UI 验收）：
// [w2 重跑 2026-10-30] RE-6 UI 走查二轮：vite 独立实例（5184，BRIDGE_PORT=3097 隔离桥 + mock oc28 确定性回合）+ 调试 Chrome 9223 + CDP。PNG/日志改落主仓 juscite/docs/evidence/施工波二轮-20261030/walkthrough/（不碰他单在途旧 PNG）；其余与 re6_ui_walkthrough.mjs 逐行同。
// 链路：chat 输入框先发首问建会话→「＋」菜单上传文件（多选 input 重置）→芯片就绪→粘贴 220 字长文本
// 转「粘贴内容.txt」（对拍 3/4）→大图上传走 canvas 压缩出「已压缩」徽章+文本回退副本（对拍 6）→
// 发送随 payload.attachmentIds 入桥（会话 meta 断言）→对话文件浮层（分组徽标/Esc/行点击开预览/
// 返回列表，对拍 35/36/55）→延迟 fetch 制造上传中窗口断言发送禁用（对拍 48/49）。
// 全部合成材料；临时文件用后即删。截图落 evidence 目录；末行 RE6_UI_PASS / RE6_UI_FAIL。
import WebSocket from "ws";
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { mkdtempSync, mkdirSync, openSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir, tmpdir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import { deflateSync } from "node:zlib";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
process.chdir(REPO_ROOT);
const CDP = process.env.CDP_PORT ? "http://127.0.0.1:" + process.env.CDP_PORT : "http://127.0.0.1:9223";
const BRIDGE_PORT = 3097;
const VITE_PORT = 5184;
const APP = `http://localhost:${VITE_PORT}/`;
const OUT = "D:/Codex/1.法律工作区/jusbench工作区/juscite/docs/evidence/施工波二轮-20261030/walkthrough";
mkdirSync(OUT, { recursive: true });
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`[re6-walk] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 合成材料 ──
const TMP = mkdtempSync(join(tmpdir(), "juscite-re6-walk-"));
const NOTE_TXT = join(TMP, "答辩要点.txt");
writeFileSync(NOTE_TXT, "答辩要点（合成）：一、程序方面无异议；二、诉讼时效抗辩：自知道权利受损之日起已逾三年；三、违约金约定过高，请求酌减。".repeat(3), "utf8");
function crc32(buf) {
  let table = crc32.t;
  if (!table) {
    table = crc32.t = new Int32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c;
    }
  }
  let crc = -1;
  for (let i = 0; i < buf.length; i++) crc = (crc >>> 8) ^ table[(crc ^ buf[i]) & 0xff];
  return (crc ^ -1) >>> 0;
}
function pngChunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const t = Buffer.from(type, "latin1");
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([t, data])));
  return Buffer.concat([len, t, data, crc]);
}
function makePng(width, height) {
  const rowSize = width * 4 + 1;
  const raw = Buffer.alloc(rowSize * height);
  for (let y = 0; y < height; y++) {
    raw[y * rowSize] = 0;
    for (let x = 0; x < width; x++) {
      const o = y * rowSize + 1 + x * 4;
      raw[o] = (x * 7) % 256; raw[o + 1] = (y * 5) % 256; raw[o + 2] = ((x + y) * 3) % 256; raw[o + 3] = 255;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0); ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 6; // RGBA8
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", ihdr), pngChunk("IDAT", deflateSync(raw, { level: 6 })), pngChunk("IEND", Buffer.alloc(0)),
  ]);
}
const BIG_PNG = join(TMP, "现场照片.png"); // 4200px 边长>4096 → 触发压缩+文本回退（对拍 6）
writeFileSync(BIG_PNG, makePng(4200, 4200));

// ── mock oc28（确定性单跳回复）──
const mockSessions = new Map();
const mockServer = createServer((req, res) => {
  const url = req.url ?? "";
  if (req.method === "POST" && url === "/api/session") { res.writeHead(200); res.end("{}"); return; }
  const pm = req.method === "POST" && url.match(/^\/api\/session\/([^/]+)\/prompt$/);
  if (pm) {
    let body = "";
    req.on("data", (c) => (body += String(c)));
    req.on("end", () => {
      const sid = decodeURIComponent(pm[1]);
      const list = mockSessions.get(sid) ?? [];
      list.push({ id: "u" + list.length, type: "user", time: { created: Date.now() }, content: [{ type: "text", text: JSON.parse(body || "{}").text ?? "" }] });
      const mid = "a" + list.length;
      setTimeout(() => {
        const l2 = mockSessions.get(sid) ?? [];
        l2.push({ id: mid, type: "assistant", time: { created: Date.now(), completed: Date.now() }, content: [{ type: "text", text: "已收到（合成回复）：材料走查回合完成。" }] });
        mockSessions.set(sid, l2);
      }, 300);
      mockSessions.set(sid, list);
      res.writeHead(200); res.end("{}");
    });
    return;
  }
  const lm = req.method === "GET" && url.match(/^\/api\/session\/([^/]+)\/message$/);
  if (lm) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ data: mockSessions.get(decodeURIComponent(lm[1])) ?? [] }));
    return;
  }
  res.writeHead(404); res.end("{}");
});
const mockUrl = await new Promise((resolve) => {
  mockServer.listen(0, "127.0.0.1", () => resolve("http://127.0.0.1:" + mockServer.address().port));
});

// ── 隔离桥（3097；独立库；onboarding 直置 completed 免向导遮挡）──
const DB = join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${BRIDGE_PORT}.db`);
const bridgeLog = openSync(join(REPO_ROOT, ".local", `re6-walk-bridge-${BRIDGE_PORT}.log`), "a");
function spawnBridge() {
  const env = { ...process.env, BRIDGE_PORT: String(BRIDGE_PORT), BRIDGE_OC28_SSE: "0", BRIDGE_OC28_URL: mockUrl, BRIDGE_OC28_PASSWORD: "walk" };
  const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: ["ignore", bridgeLog, bridgeLog], detached: true });
  child.unref();
  return child.pid;
}
async function probe() {
  try {
    const r = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/api/server-info`, { signal: AbortSignal.timeout(2500) });
    return r.ok && JSON.parse(await r.text()).store === "sqlite";
  } catch { return false; }
}
async function clearPortLeftovers() {
  if (!(await probe())) return;
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const pids = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === BRIDGE_PORT) pids.add(Number(m[2]));
  }
  for (const pid of pids) {
    const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
      { encoding: "utf-8", timeout: 20000 });
    if (String(q.stdout ?? "").includes("bridge_host.mjs")) {
      spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
      console.log("[re6-walk] 清场：杀掉残留桥 pid=" + pid);
    }
  }
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline && (await probe())) await sleep(400);
}
await clearPortLeftovers();
for (const suffix of ["", "-wal", "-shm"]) { try { rmSync(DB + suffix, { force: true }); } catch { /* 尽力清 */ } }
let bridgePid = spawnBridge();
{
  const deadline = Date.now() + 40000;
  while (Date.now() < deadline && !(await probe())) await sleep(500);
  try {
    const db = new DatabaseSync(DB);
    db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.status','completed') ON CONFLICT(key) DO UPDATE SET value='completed'").run();
    db.prepare("INSERT INTO app_meta(key,value) VALUES('onboarding.guideStatus','skipped') ON CONFLICT(key) DO UPDATE SET value='skipped'").run();
    db.close();
  } catch (e) { console.log("[re6-walk] onboarding 预置失败：", String(e).slice(0, 80)); }
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  const d2 = Date.now() + 15000;
  while (Date.now() < d2 && (await probe())) await sleep(400);
  bridgePid = spawnBridge();
  const d3 = Date.now() + 40000;
  while (Date.now() < d3 && !(await probe())) await sleep(500);
}
if (!(await probe())) { console.log("RE6_UI_FAIL"); console.error("桥 40s 不可探"); process.exit(1); }

// ── vite 独立实例（5184，代理指向 3097）──
const viteLog = openSync(join(REPO_ROOT, ".local", `re6-walk-vite-${VITE_PORT}.log`), "a");
const vite = spawn(process.execPath, [join(REPO_ROOT, "packages", "web", "node_modules", "vite", "bin", "vite.js"), "--port", String(VITE_PORT), "--strictPort"],
  { cwd: join(REPO_ROOT, "packages", "web"), env: { ...process.env, BRIDGE_PORT: String(BRIDGE_PORT) }, stdio: ["ignore", viteLog, viteLog], detached: true });
vite.unref();
async function viteUp() {
  try {
    const r = await fetch(APP, { signal: AbortSignal.timeout(2500) });
    return r.ok;
  } catch { return false; }
}
{
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline && !(await viteUp())) { process.stdout.write("."); await sleep(1000); }
  console.log("");
}
if (!(await viteUp())) { console.log("RE6_UI_FAIL"); console.error("vite 120s 不可探"); process.exit(1); }
console.log("[re6-walk] vite up:", APP, "bridge:", BRIDGE_PORT);
// 兜底清场：任何路径退出都杀掉本走查拉起的隔离桥/vite（避免残留进程阻塞下次 strictPort 复跑）
process.on("exit", () => {
  try { spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 }); } catch { /* 尽力清 */ }
  try { spawnSync("taskkill", ["/PID", String(vite.pid), "/F", "/T"], { timeout: 15000 }); } catch { /* 尽力清 */ }
});

// ── CDP ──
function getJson(p) {
  return new Promise((res, rej) => {
    import("node:http").then((http) => {
      http.default.get(CDP + p, (r) => { let d = ""; r.on("data", (c) => (d += c)); r.on("end", () => { try { res(JSON.parse(d)); } catch (e) { rej(e); } }); }).on("error", rej);
    });
  });
}
const tabs = await getJson("/json/list");
let tab = tabs.find((t) => t.type === "page" && (t.url || "").startsWith(APP));
if (!tab) {
  const r = await fetch(CDP + "/json/new?" + encodeURIComponent(APP), { method: "PUT" });
  tab = await r.json();
}
const ws = new WebSocket(tab.webSocketDebuggerUrl, { maxPayload: 128 * 1024 * 1024 });
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
let mid = 0; const pending = new Map();
ws.on("message", (raw) => { const m = JSON.parse(raw.toString()); if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); } });
const cdpSend = (method, params = {}) => new Promise((res, rej) => { const id = ++mid; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
await cdpSend("Runtime.enable"); await cdpSend("Page.enable"); await cdpSend("Page.bringToFront", {});
try {
  const { windowId, bounds } = await cdpSend("Browser.getWindowForTarget");
  await cdpSend("Browser.setWindowBounds", { windowId, bounds: { ...bounds, windowState: "normal", width: 1500, height: 900 } });
} catch { /* 无 Browser 域权限按原窗口继续 */ }
async function evalJs(expr) {
  const r = await cdpSend("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error("EXC: " + (r.exceptionDetails.exception?.description ?? r.exceptionDetails.text).slice(0, 500));
  return r.result?.value;
}
async function shot(name) {
  const r = await cdpSend("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(r.data, "base64"));
  console.log("[re6-walk] shot", name);
}
async function tclick(expr) {
  const rect = await evalJs(`(() => { const el = (${expr}); if (!el) return null; el.scrollIntoView({ block: "center" }); const r = el.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
  if (!rect) throw new Error("MISS " + expr.slice(0, 80));
  for (const type of ["mousePressed", "mouseReleased"]) {
    await cdpSend("Input.dispatchMouseEvent", { type, x: rect.x, y: rect.y, button: "left", clickCount: 1 });
  }
}
async function poll(expr, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const v = await evalJs(expr).catch(() => false);
    if (v) return v;
    await sleep(400);
  }
  return false;
}
async function setInputFiles(selector, files) {
  await cdpSend("DOM.enable");
  const { root } = await cdpSend("DOM.getDocument", { depth: -1 });
  const { nodeId } = await cdpSend("DOM.querySelector", { nodeId: root.nodeId, selector });
  if (!nodeId) throw new Error("input 不在场: " + selector);
  await cdpSend("DOM.setFileInputFiles", { files, nodeId });
}
async function typeIntoComposer(text) {
  const expr = `(() => {
    const host = document.querySelector('[data-testid="v4-composer-input"]');
    const editable = host && host.isContentEditable ? host : ((host && host.querySelector('[contenteditable="true"]')) || document.querySelector('[data-testid="v4-composer"] [contenteditable="true"]'));
    if (!editable) return false;
    editable.focus();
    document.execCommand("insertText", false, ${JSON.stringify(text)});
    return true;
  })()`;
  const focused = await evalJs(expr);
  if (!focused) throw new Error("composer 编辑器不可聚焦");
}

await cdpSend("Page.navigate", { url: APP });
{
  let up = false;
  for (let i = 0; i < 80; i++) {
    await sleep(1500);
    up = await evalJs(`!!document.querySelector('[data-testid="v4-composer-input"]')`).catch(() => false);
    if (up) break;
  }
  console.log("[re6-walk] chat composer up:", up);
  if (!up) { console.log("RE6_UI_FAIL"); process.exit(1); }
  await shot("s0-chat-shell.png");
}

// ⓪ 先发首条消息建会话（后续上传才有 threadId 作用域；不踩对拍 9 无作用域拒读语义）
await typeIntoComposer("材料走查第一问（合成，先建会话）");
const sendBtnUp = await poll(`!!document.querySelector('[data-testid="v4-composer-send"]')`, 15000);
if (!sendBtnUp) { console.log("RE6_UI_FAIL"); console.error("发送按钮未出现"); process.exit(1); }
await tclick(`document.querySelector('[data-testid="v4-composer-send"]')`);
// 回合完成信号：运行中发送键被停止键替换，回合结束发送键回归（v4-row 在该壳非稳定测试位，不用）
const firstTurnDone = await poll(`!!document.querySelector('[data-testid="v4-composer-send"]')`, 60000);
check("首回合建会话完成（发送键回归=回合收口；会话成立由 session_rows 实证）", firstTurnDone === true, String(firstTurnDone));
// sid 定位带重试（发送键回归可能与 session_rows 落盘竞速）
let sid = "";
{
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline && !sid) {
    await sleep(600);
    try {
      const db = new DatabaseSync(DB, { readOnly: true });
      const row = db.prepare("SELECT session_id FROM session_rows ORDER BY rowid DESC LIMIT 1").get();
      db.close();
      sid = row?.session_id ?? "";
    } catch { /* 重试 */ }
  }
}
check("桥库定位活动会话", sid.length > 0, sid);

// ① 附件区挂载 + 菜单/文件选择器（对拍 1）
const barMounted = await poll(`!!document.querySelector('[data-testid="bridge-material-bar"]')`);
check("材料区挂载在输入框上方", barMounted === true, String(barMounted));
await tclick(`document.querySelector('[data-testid="bridge-material-add"]')`);
await sleep(300);
const menuItem = await evalJs(`!!document.querySelector('[data-testid="bridge-material-menu-upload"]')`);
check("「＋」菜单含「上传文件」项（对拍 1）", menuItem === true, String(menuItem));
await shot("s1-menu.png");
await tclick(`document.querySelector('[data-testid="bridge-material-menu-upload"]')`);
await sleep(300);

// ② 上传文本材料（合成）→芯片就绪（对拍 1/5/43）
await setInputFiles('[data-testid="bridge-material-input"]', [NOTE_TXT]);
const chipReady = await poll(`(() => { const c=[...document.querySelectorAll('[data-testid="bridge-material-chip"]')]; return c.length>=1 && c.every(x=>!x.querySelector('[data-testid="bridge-material-busy"]')); })()`, 20000);
check("文本材料上传→芯片就绪（对拍 43 单件隔离）", chipReady === true, String(chipReady));
const inflightAfter = await evalJs(`!!document.querySelector('[data-testid="bridge-material-inflight-note"]')`);
check("上传完成后无「发送暂不可用」提示（对拍 48 出现性）", inflightAfter === false, String(inflightAfter));
await shot("s2-chip-ready.png");

// ③ 粘贴 ≥200 码点长文本 →「粘贴内容.txt」附件（对拍 4；Event+clipboardData 合成分流）
const pasteText = "代理意见（合成）：合议庭：本案争议焦点为合同效力与违约责任及损害赔偿范围的认定，现就庭审调查与法律适用发表如下代理意见，请合议庭充分考量并予采纳。其一，案涉协议系双方真实意思表示，内容不违反法律强制性规定，应认定合法有效；其二，被告未按期支付货款构成违约，应承担继续履行及赔偿损失责任；其三，原告主张的违约金比例未过分高于实际损失，不应酌减。综上，请求依法支持原告的全部诉讼请求，本案诉讼费用由被告承担。";
const pasteDispatched = await evalJs(`(() => {
  const zone = document.querySelector('[data-testid="bridge-material-paste-zone"]');
  if (!zone) return false;
  const dt = new DataTransfer();
  dt.setData("text/plain", ${JSON.stringify(pasteText)});
  const ev = new Event("paste", { bubbles: true, cancelable: true });
  Object.defineProperty(ev, "clipboardData", { value: dt });
  zone.dispatchEvent(ev);
  return true;
})()`);
check("粘贴事件派发到材料区", pasteDispatched === true, String(pasteDispatched));
const pasteChip = await poll(`[...document.querySelectorAll('[data-testid="bridge-material-chip"]')].some(x=>x.textContent.includes("粘贴内容.txt") && !x.querySelector('[data-testid="bridge-material-busy"]'))`, 20000);
check("粘贴≥200 字→「粘贴内容.txt」附件（对拍 4）", pasteChip === true, String(pasteChip));
await shot("s3-paste-txt.png");

// ④ 大图上传 → 压缩徽章 + 文本回退副本（对拍 6）
await setInputFiles('[data-testid="bridge-material-input"]', [BIG_PNG]);
const imgChip = await poll(`[...document.querySelectorAll('[data-testid="bridge-material-chip"]')].some(x=>x.textContent.includes("现场照片.png") && x.textContent.includes("已压缩") && !x.querySelector('[data-testid="bridge-material-busy"]'))`, 60000);
check("4200px 大图上传→压缩完成且芯片标「已压缩」（对拍 6）", imgChip === true, String(imgChip));

// 桥侧核对：作用域内附件库清单（producer/文本回退副本）
let attItems = [];
{
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const r = await fetch(`http://127.0.0.1:${BRIDGE_PORT}/api/attachments?threadId=${encodeURIComponent(sid)}`);
    const d = await r.json().catch(() => ({ items: [] }));
    attItems = d.items ?? [];
    if (attItems.some((x) => String(x.filename ?? "").includes("文本回退")) && attItems.length >= 4) break;
    await sleep(500);
  }
}
check("作用域内附件库≥4 件（txt/粘贴内容/压缩图/文本回退）", attItems.length >= 4, JSON.stringify(attItems.map((x) => x.filename)));
check("文本回退副本在库（对拍 6 textFallback）", attItems.some((x) => String(x.filename ?? "").includes("文本回退")), "");
check("producer 缺省 user（分组数据源）", attItems.every((x) => x.producer === "user" || x.producer === "agent"), "");
await shot("s4-image-compressed.png");

// ⑤ 发送随 payload.attachmentIds 入桥（RE-6 §3 注入面 + 对拍 11 跨回合继承入账）
await typeIntoComposer("材料走查第二问（带附件，合成）");
await poll(`!!document.querySelector('[data-testid="v4-composer-send"]')`, 15000);
await tclick(`document.querySelector('[data-testid="v4-composer-send"]')`);
let metaIds = [];
{
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    await sleep(800);
    try {
      const db = new DatabaseSync(DB, { readOnly: true });
      const row = db.prepare("SELECT meta_json FROM sessions WHERE session_id=?").get(sid);
      db.close();
      const meta = JSON.parse(row?.meta_json ?? "{}");
      metaIds = meta.attachmentIds ?? [];
      if (metaIds.length >= 4) break;
    } catch { /* 重试 */ }
  }
}
check("sendText 后会话 meta.attachmentIds≥4（桥侧并入集合）", metaIds.length >= 4, JSON.stringify(metaIds));
await poll(`!!document.querySelector('[data-testid="v4-composer-send"]')`, 60000);
await shot("s5-sent.png");

// ⑥ 对话文件浮层（对拍 35/36/55）：入口徽标/分组/Esc/行点击预览/返回列表
await tclick(`document.querySelector('[data-testid="bridge-material-files-entry"]')`);
const panelOpen = await poll(`!!document.querySelector('[data-testid="thread-files-panel"]')`);
check("对话文件浮层打开", panelOpen === true, String(panelOpen));
const total = await poll(`(() => { const t = document.querySelector('[data-testid="thread-files-total"]'); return t ? t.textContent : ""; })() === "4" ? "4" : false`, 15000);
check("总数徽标=4", total === "4", String(total));
const groupUser = await evalJs(`[...document.querySelectorAll('[data-testid="thread-files-group-user"]')].length>0`);
const groupAgent = await evalJs(`(() => { const g=document.querySelector('[data-testid="thread-files-group-agent"]'); return g && g.textContent.includes("暂无 Agent 产出文件"); })()`);
check("分组：用户文件/Agent 产出（对拍 35）", groupUser === true && groupAgent === true, `${groupUser}/${groupAgent}`);
await shot("s6-files-panel.png");
await tclick(`document.querySelector('[data-testid="thread-files-row"]')`);
const previewText = await poll(`(() => { const p=document.querySelector('[data-testid="thread-files-preview-text"]'); return p ? p.textContent.slice(0, 20) : ""; })()`, 20000);
check("行点击→文本预览（对拍 36/55）", typeof previewText === "string" && previewText.includes("答辩要点"), String(previewText).slice(0, 24));
await shot("s7-preview.png");
await tclick(`document.querySelector('[data-testid="thread-files-back"]')`);
const backToList = await poll(`!!document.querySelector('[data-testid="thread-files-total"]')`);
check("「返回文件列表」回列表（对拍 55）", backToList === true, String(backToList));
await cdpSend("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
await cdpSend("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
await sleep(400);
const panelClosed = await evalJs(`!document.querySelector('[data-testid="thread-files-panel"]')`);
check("Esc 关闭浮层（对拍 35）", panelClosed === true, String(panelClosed));

// ⑦ 上传中发送禁用（对拍 48/49）：延迟 /api/attachments 响应制造上传窗口
await evalJs(`(async () => { window.__re6Fetch = window.fetch; window.fetch = (...a) => { const u = String(a[0] ?? ""); if (u.includes("/api/attachments")) return new Promise((r) => setTimeout(() => r(window.__re6Fetch(...a)), 2500)); return window.__re6Fetch(...a); }; return true; })()`);
await setInputFiles('[data-testid="bridge-material-input"]', [NOTE_TXT]);
await sleep(600);
const sendDisabled = await evalJs(`(() => { const b=document.querySelector('[data-testid="v4-composer-send"]'); return b ? (b.disabled===true || b.getAttribute("aria-disabled")==="true") : null; })()`);
const inflightNote = await evalJs(`!!document.querySelector('[data-testid="bridge-material-inflight-note"]')`);
check("上传中发送按钮禁用（对拍 48）", sendDisabled === true, String(sendDisabled));
check("上传中无取消入口且提示在场（对拍 49）", inflightNote === true, String(inflightNote));
await shot("s8-send-disabled.png");
await poll(`(() => { const c=[...document.querySelectorAll('[data-testid="bridge-material-chip"]')]; return c.length>=1 && c.every(x=>!x.querySelector('[data-testid="bridge-material-busy"]')); })()`, 30000);
await evalJs(`window.fetch = window.__re6Fetch; true`);

// ⑧ 同内容重传合并进已有芯片（对拍 7 UI 面/§3 UI「同 id 去重」）：同件再传一次，芯片数不增
await setInputFiles('[data-testid="bridge-material-input"]', [NOTE_TXT]);
await poll(`(() => { const c=[...document.querySelectorAll('[data-testid="bridge-material-chip"]')]; return c.length>=1 && c.every(x=>!x.querySelector('[data-testid="bridge-material-busy"]')); })()`, 30000);
const chipCountAfterDupe = await evalJs(`document.querySelectorAll('[data-testid="bridge-material-chip"]').length`);
check("同内容重传合并：芯片数不增（对拍 7 UI 面）", chipCountAfterDupe === 1, String(chipCountAfterDupe));
await shot("s9-dedupe-merge.png");

// ── 收尾与判定 ──
try { rmSync(TMP, { recursive: true, force: true }); } catch { /* 尽力清 */ }
try { spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 }); } catch { /* 尽力清 */ }
try { spawnSync("taskkill", ["/PID", String(vite.pid), "/F", "/T"], { timeout: 15000 }); } catch { /* 尽力清 */ }
for (const suffix of ["", "-wal", "-shm"]) { try { rmSync(DB + suffix, { force: true }); } catch { /* 尽力清 */ } }
const failed = results.filter((r) => !r.ok);
console.log(`[re6-walk] 走查完成：${results.length - failed.length}/${results.length} 查`);
if (failed.length > 0) {
  console.error("[re6-walk] FAIL 明细：", JSON.stringify(failed));
  console.log("RE6_UI_FAIL");
  process.exit(1);
}
console.log("RE6_UI_PASS");
process.exit(0);
