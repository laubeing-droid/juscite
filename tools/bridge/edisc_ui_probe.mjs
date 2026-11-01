#!/usr/bin/env node
// 【功能 #42 取证 UI+技能注入】面板消费面合成探针（RE-42 §3.3/§3.4；施工波二轮 UI 单）。
// 自管隔离桥实例（默认 :3090，独立库 bridge-3090.db；杀前必核命令行含 bridge_host.mjs，不碰 :3030/:43127）。
// 全合成材料（合成聊天导出 PDF/合成流水 xlsx/合成表格 CSV，临时构造零真实当事人）：
//   H 组=面板五分区逐路消费（进场登记/源画像/行浏览/搜索/归类/看板清单/校验/确认/干跑更正/
//        页卡/批注/审查标注/七节报告/精化留痕）——与 EdiscPanel.tsx fetch 序列同形；
//   A 组=agent 工具契约七工具（read/search 无确认、update_metadata 默认干跑）+ bash 不入面负测；
//   S 组=技能注入（skills 通道 BUILTIN 列表含 juscite-builtin-edisc，正文含律师闸声明）。
// 单命令 exit 0/1，末行 EDISC_UI_PROBE_PASS 可判。用法：node tools/bridge/edisc_ui_probe.mjs
import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { openSync, unlinkSync, readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { crc32 } from "node:zlib";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const PORT = Number(process.env.EDISC_UI_PROBE_PORT ?? 3090);
let passed = 0, failed = 0;
const ok = (n, msg) => { passed += 1; console.log(`[edisc-ui-probe] ${n}: OK ${msg}`); };
const fail = (n, msg, detail) => { failed += 1; console.error(`[edisc-ui-probe] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); };
const assert = (n, cond, msg, detail) => (cond ? ok(n, msg) : fail(n, msg, typeof detail === "string" ? detail : JSON.stringify(detail)));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 合成材料工厂（自写；与 edisc_synthetic 同格式但内容独立）──
const pdfEsc = (s) => s.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
function buildPdf(pages) {
  const objs = []; const pageObjNums = []; let next = 4; const contents = [];
  for (const p of pages) {
    const pageNum = next++; const contentNum = next++;
    pageObjNums.push(pageNum);
    const body = p.lines.map((line, i) => `${i === 0 ? "1 0 0 1 56 780 Tm" : "0 -14 Td"}\n(${pdfEsc(line)}) Tj`).join("\n");
    contents.push({ num: contentNum, stream: `BT\n/F1 10 Tf\n${body}\nET` });
    objs[pageNum] = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents ${contentNum} 0 R >>`;
  }
  objs[1] = "<< /Type /Catalog /Pages 2 0 R >>";
  objs[2] = `<< /Type /Pages /Kids [${pageObjNums.map((n) => `${n} 0 R`).join(" ")}] /Count ${pageObjNums.length} >>`;
  objs[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>";
  const chunks = [Buffer.from("%PDF-1.4\n", "latin1")]; const offs = [];
  const maxObj = next - 1;
  const bodyOf = (n) => {
    const c = contents.find((x) => x.num === n);
    if (c) {
      const data = Buffer.from(c.stream, "utf8");
      return Buffer.concat([Buffer.from(`${n} 0 obj\n<< /Length ${data.length} >>\nstream\n`, "latin1"), data, Buffer.from("\nendstream\nendobj\n", "latin1")]);
    }
    return Buffer.from(`${n} 0 obj\n${objs[n] ?? "<< >>"}\nendobj\n`, "latin1");
  };
  for (let n = 1; n <= maxObj; n++) { offs[n] = chunks.reduce((a, c) => a + c.length, 0); chunks.push(bodyOf(n)); }
  const xrefPos = chunks.reduce((a, c) => a + c.length, 0);
  let xref = `xref\n0 ${maxObj + 1}\n0000000000 65535 f \n`;
  for (let n = 1; n <= maxObj; n++) xref += `${String(offs[n]).padStart(10, "0")} 00000 n \n`;
  xref += `trailer\n<< /Size ${maxObj + 1} /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`;
  chunks.push(Buffer.from(xref, "latin1"));
  return Buffer.concat(chunks);
}
function buildZip(entries) {
  const locals = [], centrals = []; let offset = 0;
  for (const [name, data] of entries) {
    const nameBuf = Buffer.from(name, "utf8");
    const crc = crc32(data) >>> 0;
    const lh = Buffer.alloc(30);
    lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4);
    lh.writeUInt32LE(crc, 14); lh.writeUInt32LE(data.length, 18); lh.writeUInt32LE(data.length, 22);
    lh.writeUInt16LE(nameBuf.length, 26);
    locals.push(lh, nameBuf, data);
    const ch = Buffer.alloc(46);
    ch.writeUInt32LE(0x02014b50, 0); ch.writeUInt16LE(20, 4); ch.writeUInt16LE(20, 6);
    ch.writeUInt32LE(crc, 16); ch.writeUInt32LE(data.length, 20); ch.writeUInt32LE(data.length, 24);
    ch.writeUInt16LE(nameBuf.length, 28); ch.writeUInt32LE(offset, 42);
    centrals.push(Buffer.concat([ch, nameBuf]));
    offset += 30 + nameBuf.length + data.length;
  }
  const cd = Buffer.concat(centrals);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(entries.length, 8); eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(cd.length, 12); eocd.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, cd, eocd]);
}
const CHAT_PDF = buildPdf([
  { lines: [
    "第 1 页",
    "测试甲 2026-03-05 09:12:41",
    "王经理，上月的货款请安排一下",
    "测试乙 2026-03-05 09:13:02",
    "收到，今天下午对公转账",
  ] },
]);
const STMT_HEADERS = ["交易时间", "交易对方", "对方账户", "摘要", "收/支", "金额(元)"];
const STMT_ROWS = [
  ["2026-04-01 10:00:00", "探针示例贸易有限公司", "6222****4321", "货款,对公", "收", "9800.00"],
  ["2026-04-02 11:30:00", "探针物业服务有限公司", "8801****8765", "物业费", "支", "1200.00"],
];
function xmlEsc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function buildStatementXlsx() {
  const strings = []; const si = (t) => (strings.push(t), strings.length - 1);
  const rows = [`<row r="1">${STMT_HEADERS.map((h, j) => `<c r="${String.fromCharCode(65 + j)}1" t="s"><v>${si(h)}</v></c>`).join("")}</row>`];
  STMT_ROWS.forEach((r, i) => {
    const rn = i + 2;
    rows.push(`<row r="${rn}">${r.map((c, j) => {
      const addr = `${String.fromCharCode(65 + j)}${rn}`;
      return j === 5 ? `<c r="${addr}"><v>${c}</v></c>` : `<c r="${addr}" t="s"><v>${si(c)}</v></c>`;
    }).join("")}</row>`);
  });
  const sheetXml = `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${rows.join("")}</sheetData></worksheet>`;
  const sstXml = `<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="${strings.length}" uniqueCount="${strings.length}">${strings.map((t) => `<si><t>${xmlEsc(t)}</t></si>`).join("")}</sst>`;
  return buildZip([
    ["[Content_Types].xml", Buffer.from(`<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>`, "utf8")],
    ["xl/workbook.xml", Buffer.from(`<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="流水" sheetId="1" r:id="rId1"/></sheets></workbook>`, "utf8")],
    ["xl/_rels/workbook.xml.rels", Buffer.from(`<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`, "utf8")],
    ["xl/worksheets/sheet1.xml", Buffer.from(sheetXml, "utf8")],
    ["xl/sharedStrings.xml", Buffer.from(sstXml, "utf8")],
  ]);
}
const STMT_XLSX = buildStatementXlsx();
const TABLE_CSV = ["品名,数量,金额(元),备注", "合成构件,6,\"7,200.00\",\"含,运费\"", "合成配件,10,180.00,现货"].join("\n");

const b64 = (buf) => buf.toString("base64");

// ── 隔离桥生命周期（杀前必核命令行含 bridge_host.mjs）──
const dbPath = () => join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${PORT}.db`);
async function commandLineOf(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command", `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`], { encoding: "utf8", timeout: 20000 });
  return String(r.stdout ?? "").trim();
}
function findListenerPids(port) {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf8", timeout: 15000 });
  const pids = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === port) pids.add(Number(m[2]));
  }
  return [...pids];
}
async function probeInfo() {
  try {
    const r = await fetch(`http://127.0.0.1:${PORT}/api/server-info`, { signal: AbortSignal.timeout(2500) });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}
try {
  for (const pid of findListenerPids(PORT)) {
    const line = await commandLineOf(pid);
    if (!line.includes("bridge_host.mjs")) throw new Error(`:${PORT} 被非桥进程占用（pid=${pid}），不接触`);
    console.log(`[edisc-ui-probe] 清残留桥 pid=${pid}`);
    spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
  }
  for (const suffix of ["", "-wal", "-shm"]) { try { unlinkSync(dbPath() + suffix); } catch { /* 不存在即可 */ } }
  const logFd = openSync(join(REPO_ROOT, ".local", `edisc-ui-probe-bridge-${PORT}.log`), "a");
  const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(PORT) }, stdio: ["ignore", logFd, logFd], detached: true });
  child.unref();
  let info = null;
  const deadline = Date.now() + 45000;
  while (Date.now() < deadline && !info) { info = await probeInfo(); if (!info) await sleep(600); }
  assert(1, Boolean(info?.edisc === 1), `隔离桥 :${PORT} 起动且 server-info edisc:1`, JSON.stringify(info?.edisc));

  // ── RPC 连接（zcode-agent 建案 + skills 通道验注入；单 Client 多通道）──
  const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws`);
  ws.binaryType = "arraybuffer";
  const data = { fire: (_b) => {} };
  ws.on("message", (buf) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
  await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
  const isocket = {
    onData: (l) => { data.fire = l; return { dispose: () => {} }; },
    onClose: () => ({ dispose: () => {} }),
    onEnd: () => ({ dispose: () => {} }),
    write: (b) => ws.send(b.buffer),
    end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
  };
  const client = new ChannelClient(new SocketProtocol(isocket));
  const ch = client.getChannel("zcode-agent");
  const skch = client.getChannel("skills");
  const call = (m, a) => ch.call(m, a === undefined ? [] : [a]);
  const skillsCall = (m, a) => skch.call(m, a === undefined ? [] : [a]);
  await call("helloConversationV4");
  const created = await call("matterCreate", { name: "合成案件·取证UI探针" });
  const caseId = created?.caseId ?? created?.id ?? created?.matter?.id;
  assert(2, Boolean(caseId), "RPC matterCreate 合成案件（面板案件下拉数据源）", JSON.stringify(created).slice(0, 120));

  // ── S 组：技能注入 ──
  const skills = await skillsCall("list");
  const ediscSkill = (skills?.skills ?? []).find((s) => s.id === "juscite-builtin-edisc");
  assert(3, Boolean(ediscSkill), "skills 通道含 juscite-builtin-edisc（触发词族+/edisc 入 description）",
    ediscSkill?.description?.slice(0, 80) ?? "缺");
  assert(4, /\/edisc/.test(ediscSkill?.description ?? "") && /电子数据/.test(ediscSkill?.description ?? ""),
    "触发词族（/edisc+电子数据/取证…）在技能描述中", ediscSkill?.description?.slice(0, 60));
  assert(5, /律师闸/.test(ediscSkill?.body ?? "") && /待证事实/.test(ediscSkill?.body ?? "") && /局限/.test(ediscSkill?.body ?? "")
    && /须核实/.test(ediscSkill?.body ?? "") && /保密/.test(ediscSkill?.body ?? "") && /六要素/.test(ediscSkill?.body ?? ""),
    "注入正文必备章节在位（目的三档/待证事实先行/形式六要素/来源标签须核实/律师闸/保密继承/局限声明…）", String(ediscSkill?.body?.length ?? 0));

  // ── HTTP 面（与 EdiscPanel fetch 序列同形）──
  let token = "";
  const tokenPath = join(homedir(), "AppData", "Roaming", "Juscite", "bridge", "local-auth.token");
  if (existsSync(tokenPath)) token = readFileSync(tokenPath, "utf8").trim();
  const H = token ? { "x-juscite-token": token } : {};
  const api = async (path, init) => {
    const r = await fetch(`http://127.0.0.1:${PORT}${path}`, { cache: "no-store", ...init, headers: { ...H, ...(init?.headers ?? {}) } });
    const d = await r.json().catch(() => null);
    return { status: r.status, data: d };
  };
  const post = (path, body) => api(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

  const upChat = await post("/api/edisc/sources", { caseId, kind: "chat", filename: "合成聊天导出.pdf", dataBase64: b64(CHAT_PDF) });
  assert(6, upChat.status === 200 && upChat.data?.parseStatus === "done" && Boolean(upChat.data?.fileHash) && upChat.data?.pageCount >= 1,
    "进场：聊天 PDF 登记（入册即哈希+解析，页/块落库）", JSON.stringify(upChat.data).slice(0, 160));
  const chatId = upChat.data?.id;
  const upStmt = await post("/api/edisc/sources", { caseId, kind: "statement", filename: "合成流水.xlsx", dataBase64: b64(STMT_XLSX) });
  assert(7, upStmt.status === 200 && upStmt.data?.parseStatus === "done", "进场：流水 xlsx 登记（行面解析）", JSON.stringify(upStmt.data).slice(0, 120));
  const stmtId = upStmt.data?.id;
  const upTable = await post("/api/edisc/sources", { caseId, kind: "table", filename: "合成表格.csv", dataBase64: b64(Buffer.from(TABLE_CSV, "utf8")) });
  assert(8, upTable.status === 200 && upTable.data?.parseStatus === "done", "进场：表格 CSV 登记", JSON.stringify(upTable.data).slice(0, 120));

  const listSources = await api(`/api/edisc/sources?caseId=${encodeURIComponent(caseId)}`);
  const srcItems = listSources.data?.items ?? [];
  assert(9, srcItems.length === 3 && srcItems.every((s) => "parseStatus" in s && "ocrStatus" in s && "fileHash" in s && "kind" in s),
    "源列表（A3）：三件源+三态徽章字段齐（hash/parse/ocr）", JSON.stringify(srcItems.map((s) => [s.kind, s.parseStatus])));

  const prof = await api(`/api/edisc/sources/${encodeURIComponent(chatId)}/profile`);
  assert(10, prof.data?.chatMessages === 2 && prof.data?.pages === 1 && Boolean(prof.data?.coordSystem),
    "源画像抽屉（B1）：对话段数/页数/坐标系", JSON.stringify(prof.data).slice(0, 160));

  const rowsChat = await api(`/api/edisc/sources/${encodeURIComponent(chatId)}/rows?table=${encodeURIComponent("聊天记录")}&rowStart=1&rowEnd=50`);
  assert(11, rowsChat.data?.rows?.length === 2 && rowsChat.data?.rows?.every((r) => Boolean(r.blockId)) && Boolean(rowsChat.data?.fileHash),
    "行浏览（B2 默认 1..50）：聊天虚拟表 2 行且行行回链锚块", JSON.stringify(rowsChat.data?.rows?.map((r) => r.rowNo)));
  const rowsStmt = await api(`/api/edisc/sources/${encodeURIComponent(stmtId)}/rows?table=${encodeURIComponent("流水")}&rowStart=1&rowEnd=50`);
  const amtCells = (rowsStmt.data?.rows ?? []).flatMap((r) => r.amounts ?? []);
  assert(12, rowsStmt.data?.rows?.length === 3 && amtCells.some((a) => a.cents !== undefined || /^[￥¥]/.test(String(a.text))),
    "行浏览：流水 3 行+金额双轨字段在读取面出现（H2 禁浮点）", JSON.stringify(amtCells).slice(0, 120));

  const search = await api(`/api/edisc/search?caseId=${encodeURIComponent(caseId)}&q=${encodeURIComponent("货款")}`);
  assert(13, (search.data?.hits?.length ?? 0) >= 2 && /定位线索/.test(search.data?.note ?? ""),
    "行搜索（B3）：跨源命中+E5 两段纪律文案随返回", JSON.stringify({ n: search.data?.hits?.length }));

  const cls = await post("/api/edisc/classifications", {
    caseId, category: "应收货款", reason: "对账单与聊天记录互相印证",
    refs: [
      { kind: "rows", sourceId: chatId, tableName: "聊天记录", rowStart: 1, rowEnd: 1 },
      { kind: "rows", sourceId: stmtId, tableName: "流水", rowStart: 2, rowEnd: 2 },
    ],
  });
  assert(14, cls.status === 200 && Boolean(cls.data?.id) && cls.data?.createdBy, "归类打标（C1/C3 覆盖层+操作者留名）", JSON.stringify(cls.data).slice(0, 120));
  const clsList = await api(`/api/edisc/classifications?caseId=${encodeURIComponent(caseId)}`);
  assert(15, clsList.data?.items?.length === 1, "归类读回（C2）", JSON.stringify(clsList.data?.items?.length));

  const fix = await post("/api/edisc/fix-lists", { caseId, category: "应收货款" });
  assert(16, fix.data?.created?.length >= 1 && /建议/.test(fix.data?.suggestionNote ?? ""), "候选清单生成（D1 只吃人工归类行+建议档声明）", JSON.stringify(fix.data?.created?.length));
  const fixList = await api(`/api/edisc/fix-lists?caseId=${encodeURIComponent(caseId)}`);
  const cand = fixList.data?.items?.[0];
  assert(17, Boolean(cand?.id) && cand?.status === "suggested" && (cand?.anchors ?? []).length >= 1, "候选清单项带锚（suggested 待确认）", JSON.stringify(cand?.anchors?.map((a) => a.label)));

  const dry = await post(`/api/edisc/fix-lists/${encodeURIComponent(cand.id)}/metadata`, { title: "应收货款九千八（对公）", reason: "标题精确化" });
  assert(18, dry.data?.dryRun === true && dry.data?.applied === undefined && dry.data?.after?.title === "应收货款九千八（对公）",
    "元数据更正默认干跑（G3）：预览不落库", JSON.stringify({ dryRun: dry.data?.dryRun }));
  const apply = await post(`/api/edisc/fix-lists/${encodeURIComponent(cand.id)}/metadata`, { title: "应收货款九千八（对公）", reason: "标题精确化", confirmed: true, by: "探针律师" });
  assert(19, apply.data?.applied === true, "confirmed=true 落库（G2 精化留痕路径）", JSON.stringify({ applied: apply.data?.applied }));

  const verify = await post("/api/edisc/fix-lists/verify", { caseId });
  assert(20, verify.data?.ok === true && verify.data?.backjumpChecked >= 1 && verify.data?.backjumpMismatched === 0,
    "清单校验（D2/G6）：锚一一对应+回跳核验一致", JSON.stringify({ ok: verify.data?.ok, bj: verify.data?.backjumpChecked, mm: verify.data?.backjumpMismatched, checked: verify.data?.checked, problems: verify.data?.problems }));

  const confirm = await post(`/api/edisc/fix-lists/${encodeURIComponent(cand.id)}/confirm`, { confirmedBy: "探针律师" });
  assert(21, confirm.data?.status === "confirmed" && confirm.data?.confirmedBy === "探针律师", "人工确认分权（D3 留名）", JSON.stringify(confirm.data?.status));

  const page = await api(`/api/edisc/sources/${encodeURIComponent(chatId)}/pages?page=1`);
  assert(22, page.data?.blocks?.length >= 5 && page.data?.blocks?.every((b) => Array.isArray(b.bbox) && b.bbox.length === 4),
    "页卡阅读（E4）：整页块序+bbox 坐标", JSON.stringify(page.data?.blocks?.length));
  const blk = page.data.blocks[1];
  const ann = await post("/api/edisc/annotations", {
    caseId, sourceId: chatId, pageNumber: 1, rects: [blk.bbox], type: "highlight", textContent: "本行系货款催告意思表示",
  });
  assert(23, ann.status === 200 && Boolean(ann.data?.id), "坐标批注（E3 矩形取块 bbox，虚拟覆盖层）", JSON.stringify(ann.data?.id));
  const annList = await api(`/api/edisc/annotations?caseId=${encodeURIComponent(caseId)}`);
  assert(24, annList.data?.items?.length === 1 && annList.data.items[0].pageNumber === 1, "批注读回（按页分组入参页过滤可用）", JSON.stringify(annList.data?.items?.length));

  const flag = await post("/api/edisc/review-flags", { caseId, sourceId: chatId, targetLabel: "测试甲与测试乙的微信聊天记录（合成）", kind: "chat", notarized: false });
  assert(25, flag.data?.level === "doubt" && flag.data?.proofStrength === "弱" && (flag.data?.tags ?? []).includes("存疑"),
    "审查标注预置（F5）：未经公证聊天默认存疑+证明力弱", JSON.stringify({ level: flag.data?.level, ps: flag.data?.proofStrength, tags: flag.data?.tags }));

  const report = await api(`/api/edisc/review-report?caseId=${encodeURIComponent(caseId)}`);
  assert(26, typeof report.data?.report === "string" && /待证事实/.test(report.data.report) && /律师/.test(report.data.report) && report.data?.verify?.ok === true,
    "七节审查报告（F12）+校验随报告", JSON.stringify({ len: report.data?.report?.length, ok: report.data?.verify?.ok }));

  const refine = await api(`/api/edisc/fix-lists/refinements`.replace("/fix-lists/refinements", "/refinements") + `?caseId=${encodeURIComponent(caseId)}`);
  const ops = (refine.data?.items ?? []).map((r) => r.op);
  assert(27, ops.includes("metadata") && ops.includes("confirm"), "精化留痕可查（G2）：metadata+confirm 两笔在账", JSON.stringify(ops));

  // ── A 组：agent 工具契约（七工具转发+bash 不入面）──
  const a1 = await call("ediscListSources", { caseId });
  assert(28, (a1?.items?.length ?? 0) === 3, "agent 工具 ediscListSources（A3 等量）", JSON.stringify(a1?.items?.length));
  const a2 = await call("ediscSearchRows", { caseId, q: "货款" });
  assert(29, (a2?.hits?.length ?? 0) >= 2, "agent 工具 ediscSearchRows（B3 等量）", JSON.stringify(a2?.hits?.length));
  const a3 = await call("ediscReadRows", { sourceId: stmtId, table: "流水", rowStart: 1, rowEnd: 50 });
  assert(30, a3?.rows?.length === 3, "agent 工具 ediscReadRows（B2 等量）", JSON.stringify(a3?.rows?.length));
  const a4 = await call("ediscReadPageCards", { sourceId: chatId, page: 1 });
  assert(31, (a4?.blocks?.length ?? 0) >= 5, "agent 工具 ediscReadPageCards（E4 等量）", JSON.stringify(a4?.blocks?.length));
  const a5 = await call("ediscProposeClassification", {
    caseId, category: "往来核对", refs: [{ kind: "rows", sourceId: stmtId, tableName: "流水", rowStart: 3, rowEnd: 3 }], createdBy: "探针agent",
  });
  assert(32, Boolean(a5?.id) && a5?.createdBy === "探针agent", "agent 工具 ediscProposeClassification（C1 建议覆盖层+留名）", JSON.stringify(a5?.id));
  const a6 = await call("ediscUpdateMetadata", { candidateId: cand.id, title: "应收货款九千八（对公）·agent 复核" });
  assert(33, a6?.dryRun === true, "agent 工具 ediscUpdateMetadata 默认干跑（confirmed 缺省≠落库，G3）", JSON.stringify({ dryRun: a6?.dryRun }));
  const a7 = await call("ediscGenerateFixList", { caseId });
  assert(34, Array.isArray(a7?.created), "agent 工具 ediscGenerateFixList（D1 等量）", JSON.stringify(a7?.created?.length));
  let bashAbsent = false;
  try { await call("ediscExec", { cmd: "dir" }); } catch (e) { bashAbsent = /not found|不存在|Method/i.test(String(e?.message ?? e)); }
  assert(35, bashAbsent, "bash 类裸执行工具不入面（ediscExec 调用=方法不存在）", "agent 契约无 shell 通道（G1-G4 边界）");

  // ── R 组：对拍收尾面（施工波三轮：F1/F2/F4/F6/G5/报告文案——与 EdiscPanel 新表单 fetch 序列同形）──
  const fact = await post("/api/edisc/facts", { caseId, text: "双方存在买卖合同关系（探针）" });
  const factList = await api(`/api/edisc/facts?caseId=${encodeURIComponent(caseId)}`);
  assert(36, fact.status === 200 && Boolean(fact.data?.id) && factList.data?.items?.length === 1 && /无争议/.test(factList.data?.exclusionNote ?? ""),
    "F1 待证事实登记+读回（四类排除纪律随发）", JSON.stringify({ n: factList.data?.items?.length }));

  const formal = await post(`/api/edisc/fix-lists/${encodeURIComponent(cand.id)}/elements`, {
    elements: { 名称: "应收货款九千八（对公）", 形成时间: "2026-04-01", 出具方: "自银行导出", 原件或复印件: "导出 xlsx", 证明目的: "证明到账事实", 对应待证事实: "1" },
  });
  const candAfter = (await api(`/api/edisc/fix-lists?caseId=${encodeURIComponent(caseId)}`)).data?.items?.find((c) => c.id === cand.id);
  assert(37, formal.data?.check?.complete === true && candAfter?.formal?.check?.complete === true,
    "F2 形式六要素登记：齐备随候选读回（缺项路径合成面 47 号已验）", JSON.stringify({ complete: formal.data?.check?.complete }));

  const tripleBad = await post("/api/edisc/triple-reviews", { caseId, targetLabel: "x", findings: [{ attr: "真实性", conclusion: "完美" }] });
  const triple = await post("/api/edisc/triple-reviews", {
    caseId, sourceId: chatId, targetLabel: "测试甲与测试乙的微信聊天记录（合成）",
    findings: [
      { attr: "真实性", conclusion: "存疑", reason: "未经公证（探针）" },
      { attr: "合法性", conclusion: "符合", reason: "本人手机导出" },
      { attr: "关联性", conclusion: "符合", reason: "对应货款到账待证事实" },
    ],
  });
  assert(38, tripleBad.status === 400 && triple.status === 200 && triple.data?.findings?.length === 3,
    "F4 三性表单：结论闭集拒收+逐项结论+理由落库", JSON.stringify({ bad: tripleBad.status, n: triple.data?.findings?.length }));

  const gapBad = await post("/api/edisc/gaps", { caseId, kind: "其他", suggestion: "x" });
  const gap = await post("/api/edisc/gaps", {
    caseId, kind: "证明力不足", factText: "货款到账事实", suggestion: "补充对账单与聊天记录印证",
    sourceChannel: "对方提供", difficulty: "易", deadlineNote: "庭前举证期限内",
  });
  assert(39, gapBad.status === 400 && gap.status === 200 && gap.data?.kind === "证明力不足",
    "F6 四类缺口结构化登记（类目闭集）", JSON.stringify({ bad: gapBad.status, kind: gap.data?.kind }));

  const upPending = await post("/api/edisc/sources", {
    caseId, kind: "chat", filename: "任务整理件.pdf",
    dataBase64: b64(buildPdf([{ lines: ["第 1 页", "探针甲 2026-05-01 09:00:00", "任务整理的合成消息", "探针乙 2026-05-01 09:01:00", "任务整理的合成回复"] }])),
    parse: false,
  });
  const taskStart = await post("/api/edisc/tasks", { caseId, sourceIds: [upPending.data?.id], pageCardsOnly: true, tickMs: 20 });
  let task = taskStart.data;
  for (let i = 0; i < 60 && (!task || task.status === "running"); i++) {
    await sleep(60);
    task = (await api(`/api/edisc/tasks/${encodeURIComponent(taskStart.data?.id ?? "")}`)).data;
  }
  assert(40, upPending.data?.parseStatus === "pending" && taskStart.data?.status === "running" && taskStart.data?.summary?.checkpoint === 0
    && task?.status === "done" && task?.summary?.checkpoint === 1,
    "G5 整理任务：启动即返检查点回执→后台逐件完成（仅页卡档）", JSON.stringify({ st: task?.status, sum: task?.summary?.checkpoint }));

  const report2 = await api(`/api/edisc/review-report?caseId=${encodeURIComponent(caseId)}`);
  assert(41, /双方存在买卖合同关系（探针）/.test(report2.data?.report ?? "") && /形式六要素：齐备/.test(report2.data?.report ?? "")
    && /真实性=存疑（未经公证（探针））/.test(report2.data?.report ?? "") && /【证明力不足】/.test(report2.data?.report ?? "")
    && /须核实/.test(report2.data?.report ?? "") && /保密继承/.test(report2.data?.report ?? ""),
    "报告收尾面：待证事实先行+六要素齐备+三性逐项+缺口结构化+须核实纪律+保密继承（F1/F2/F4/F6/F9/F14）",
    String(report2.data?.report?.length ?? 0));

  // ── 收尾：核验命令行后杀自家桥 ──
  const cl = await commandLineOf(child.pid);
  if (cl.includes("bridge_host.mjs")) {
    spawnSync("taskkill", ["/PID", String(child.pid), "/F", "/T"], { timeout: 15000 });
  } else {
    console.error(`[edisc-ui-probe] 注意 pid=${child.pid} 命令行不含 bridge_host.mjs，未杀（宁停不误杀）：${cl.slice(0, 120)}`);
  }
  ws.close();
} catch (e) {
  fail(99, "探针主链异常", String(e?.stack ?? e));
}
console.log(failed > 0 ? `EDISC_UI_PROBE_FAIL passed=${passed} failed=${failed}` : `EDISC_UI_PROBE_PASS passed=${passed}/${passed + failed}`);
process.exit(failed > 0 ? 1 : 0);
