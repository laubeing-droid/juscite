#!/usr/bin/env node
// 【功能 #42 电子数据取证】合成自测（RE-42 §4 末验收口径：三类首做各以合成材料实跑
// “进场→锚→归类→清单→审查标注→回跳核验”全链；任何清单引用回跳原文位置一致方算 PASS）。
// 全合成材料（临时目录现造现删）：合成聊天导出 PDF（UTF-8 文本层+Tm/Td 定位，两页）、
// 合成银行流水 xlsx（store zip+sharedStrings）、合成业务表格 CSV（引号内逗号/千分位金额）。
// 零 %APPDATA% 触碰的进程内服务全链（库/工件全落临时目录）+ 隔离端口桥实例接线冒烟
// （:3091，server-info 能力标记 edisc:1 + 路由接通 + 迁移 0020_edisc 落账；杀前核验命令行）。
// 纯 Node（服务全链经本机回环 HTTP：隔离端口 3090 起，占位回落临时端口）；单命令 exit 0/1，
// 末行 EDISC_SYNTH_PASS 可判。用法：node --import tsx tools/bridge/edisc_synthetic.mjs
import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, rmSync, mkdirSync, openSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";
import { crc32 } from "node:zlib";
import { DatabaseSync } from "node:sqlite";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const svc = await import("./edisc_service.mjs");
const { EDISC_DDL, EDISC_REVIEW_DDL, createEdiscDao, createEdiscService } = svc;

const dir = mkdtempSync(join(tmpdir(), "juscite-edisc-synth-"));
const WS = "ws_edisc";
const CASE = "case_edisc_1";
let passed = 0, failed = 0;
const ok = (n, msg) => { passed += 1; console.log(`[edisc-synth] ${n}: OK ${msg}`); };
const fail = (n, msg, detail) => { failed += 1; console.error(`[edisc-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); };
const assert = (n, cond, msg, detail) => (cond ? ok(n, msg) : fail(n, msg, typeof detail === "string" ? detail : JSON.stringify(detail)));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sha256hex = (buf) => createHash("sha256").update(buf).digest("hex");

// ══════════ 合成材料工厂（全部自写；无真实当事人）══════════
function pdfEsc(s) { return s.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)"); }
function buildPdf(pages) {
  const objs = [];
  const pageObjNums = [];
  let next = 4;
  const contents = [];
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
  const chunks = [Buffer.from("%PDF-1.4\n", "latin1")];
  const offs = [];
  const maxObj = next - 1;
  const bodyOf = (n) => {
    const c = contents.find((x) => x.num === n);
    if (c) {
      const data = Buffer.from(c.stream, "utf8");
      return Buffer.concat([Buffer.from(`${n} 0 obj\n<< /Length ${data.length} >>\nstream\n`, "latin1"), data, Buffer.from("\nendstream\nendobj\n", "latin1")]);
    }
    return Buffer.from(`${n} 0 obj\n${objs[n] ?? "<< >>"}\nendobj\n`, "latin1");
  };
  for (let n = 1; n <= maxObj; n++) {
    offs[n] = chunks.reduce((a, c) => a + c.length, 0);
    chunks.push(bodyOf(n));
  }
  const xrefPos = chunks.reduce((a, c) => a + c.length, 0);
  let xref = `xref\n0 ${maxObj + 1}\n0000000000 65535 f \n`;
  for (let n = 1; n <= maxObj; n++) xref += `${String(offs[n]).padStart(10, "0")} 00000 n \n`;
  xref += `trailer\n<< /Size ${maxObj + 1} /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`;
  chunks.push(Buffer.from(xref, "latin1"));
  return Buffer.concat(chunks);
}

function buildZip(entries) {
  const locals = [], centrals = [];
  let offset = 0;
  for (const [name, data] of entries) {
    const nameBuf = Buffer.from(name, "utf8");
    const crc = crc32(data) >>> 0;
    const lh = Buffer.alloc(30);
    lh.writeUInt32LE(0x04034b50, 0);
    lh.writeUInt16LE(20, 4); lh.writeUInt16LE(0, 6); lh.writeUInt16LE(0, 8);
    lh.writeUInt16LE(0, 10); lh.writeUInt16LE(0, 12);
    lh.writeUInt32LE(crc, 14); lh.writeUInt32LE(data.length, 18); lh.writeUInt32LE(data.length, 22);
    lh.writeUInt16LE(nameBuf.length, 26); lh.writeUInt16LE(0, 28);
    locals.push(lh, nameBuf, data);
    const ch = Buffer.alloc(46);
    ch.writeUInt32LE(0x02014b50, 0);
    ch.writeUInt16LE(20, 4); ch.writeUInt16LE(20, 6); ch.writeUInt16LE(0, 8); ch.writeUInt16LE(0, 10);
    ch.writeUInt16LE(0, 12); ch.writeUInt16LE(0, 14);
    ch.writeUInt32LE(crc, 16); ch.writeUInt32LE(data.length, 20); ch.writeUInt32LE(data.length, 24);
    ch.writeUInt16LE(nameBuf.length, 28); ch.writeUInt16LE(0, 30); ch.writeUInt16LE(0, 32);
    ch.writeUInt16LE(0, 34); ch.writeUInt16LE(0, 36); ch.writeUInt32LE(0, 38);
    ch.writeUInt32LE(offset, 42);
    centrals.push(Buffer.concat([ch, nameBuf]));
    offset += 30 + nameBuf.length + data.length;
  }
  const cd = Buffer.concat(centrals);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(entries.length, 8); eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(cd.length, 12); eocd.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, cd, eocd]);
}

// 合成聊天导出 PDF：两页、页码行、双行式消息、含一条两行内容消息
const CHAT_PDF = buildPdf([
  { lines: [
    "第 1 页",
    "张某某 2026-03-05 09:12:41",
    "李经理，上月的货款一万二千八请安排一下",
    "李某某 2026-03-05 09:13:02",
    "收到，今天下午走对公转账",
    "李某某 2026-03-05 15:42:17",
    "已转 12800 元，回单已发邮箱",
    "另：发票这周也一并寄出",
  ] },
  { lines: [
    "第 2 页",
    "张某某 2026-03-12 08:50:11",
    "收到，发票抬头开：合成示例贸易有限公司",
  ] },
]);
const CHAT_EXPECT = [
  { sender: "张某某", sentAt: "2026-03-05 09:12:41", head: "李经理，上月的货款一万二千八请安排一下" },
  { sender: "李某某", sentAt: "2026-03-05 09:13:02", head: "收到，今天下午走对公转账" },
  { sender: "李某某", sentAt: "2026-03-05 15:42:17", head: "已转 12800 元，回单已发邮箱\n另：发票这周也一并寄出" },
  { sender: "张某某", sentAt: "2026-03-12 08:50:11", head: "收到，发票抬头开：合成示例贸易有限公司" },
];

// G5 任务面专用合成 PDF（内容与 CHAT_PDF 不同→不同哈希，避开登记去重回旧源）
const TASK_PDF_A = buildPdf([{ lines: ["第 1 页", "赵某某 2026-04-01 10:00:00", "整理任务的合成消息一", "钱某某 2026-04-01 10:01:00", "整理任务的合成回复一"] }]);
const TASK_PDF_B = buildPdf([{ lines: ["第 1 页", "孙某某 2026-04-02 11:00:00", "续传件的合成消息二", "周某某 2026-04-02 11:01:00", "续传件的合成回复二"] }]);

// 合成银行流水 xlsx：sharedStrings（含逗号摘要）+ 数字串金额
const STMT_HEADERS = ["交易时间", "交易对方", "对方账户", "摘要", "收/支", "金额(元)", "余额(元)"];
const STMT_ROWS = [
  ["2026-03-05 15:40:00", "合成示例贸易有限公司", "6222****1234", "货款,对公", "收", "12800.00", "50233.60"],
  ["2026-03-06 09:21:00", "合成物业服务有限公司", "8801****5678", "房租,物业", "支", "6600.00", "43633.60"],
  ["2026-03-10 14:05:00", "王某某", "6217****9012", "往来款", "往来", "5000.00", "48633.60"],
  ["2026-03-15 10:00:00", "合成物流有限公司", "7702****3456", "运费", "支", "320.50", "48313.10"],
];
function xmlEsc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
function buildStatementXlsx() {
  const strings = [];
  const si = (t) => (strings.push(t), strings.length - 1);
  const rows = [`<row r="1">${STMT_HEADERS.map((h, j) => `<c r="${String.fromCharCode(65 + j)}1" t="s"><v>${si(h)}</v></c>`).join("")}</row>`];
  STMT_ROWS.forEach((r, i) => {
    const rn = i + 2;
    rows.push(`<row r="${rn}">${r.map((c, j) => {
      const addr = `${String.fromCharCode(65 + j)}${rn}`;
      return (j === 5 || j === 6) ? `<c r="${addr}"><v>${c}</v></c>` : `<c r="${addr}" t="s"><v>${si(c)}</v></c>`;
    }).join("")}</row>`);
  });
  const sheetXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${rows.join("")}</sheetData></worksheet>`;
  const sstXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="${strings.length}" uniqueCount="${strings.length}">${strings.map((t) => `<si><t>${xmlEsc(t)}</t></si>`).join("")}</sst>`;
  return buildZip([
    ["[Content_Types].xml", Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>`, "utf8")],
    ["_rels/.rels", Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`, "utf8")],
    ["xl/workbook.xml", Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="流水" sheetId="1" r:id="rId1"/></sheets></workbook>`, "utf8")],
    ["xl/_rels/workbook.xml.rels", Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`, "utf8")],
    ["xl/worksheets/sheet1.xml", Buffer.from(sheetXml, "utf8")],
    ["xl/sharedStrings.xml", Buffer.from(sstXml, "utf8")],
  ]);
}
const STMT_XLSX = buildStatementXlsx();

// 合成业务表格 CSV（引号内逗号、千分位金额、表头）
const TABLE_CSV = [
  "序号,品名,数量,单价(元),金额(元),备注",
  "1,钢结构构件,12,\"1,200.00\",\"14,400.00\",含运费",
  "2,紧固件套件,40,35.50,\"1,420.00\",\"备注含,逗号\"",
  "3,密封胶,8,45.00,\"360.00\",按桶计",
].join("\n");

// ══════════ 进程内服务（隔离端口 HTTP 面）══════════
const db = new DatabaseSync(join(dir, "edisc.db"));
db.exec("PRAGMA foreign_keys = ON");
db.exec(EDISC_DDL);
db.exec(EDISC_REVIEW_DDL);
const dao = createEdiscDao(db);
const auditLog = [];
const service = createEdiscService({
  dao,
  caseExists: (id) => id === CASE,
  root: join(dir, "artifacts"),
  workspaceKey: WS,
  authFilePath: join(dir, "auth.token"),
  now: () => new Date().toISOString(),
  log: () => {},
  auditWrite: (action, target, detail) => auditLog.push({ action, target, detail }),
});

const server = await new Promise((resolve) => {
  const s = http.createServer(async (req, res) => {
    const handled = await service.httpHandler(req, res, new URL(req.url ?? "/", "http://localhost"));
    if (!handled) { res.writeHead(404); res.end("unknown"); }
  });
  s.once("error", () => { s.removeAllListeners("error"); s.listen(0, "127.0.0.1", () => resolve(s)); }); // 3090 占用→临时端口回落
  s.listen(3090, "127.0.0.1", () => resolve(s));
});
await new Promise((r) => setTimeout(r, 100));
const port = server.address().port;
const base = `http://127.0.0.1:${port}`;
let token = null;
async function api(method, path, body) {
  const headers = { "content-type": "application/json" };
  if (token) headers["x-juscite-token"] = token;
  const r = await fetch(`${base}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  let data = null;
  try { data = await r.json(); } catch { data = null; }
  return { status: r.status, data };
}

// ══════════ A 面：进场 ══════════
const scanDir = join(dir, "scan-root");
mkdirSync(scanDir, { recursive: true });
writeFileSync(join(scanDir, "合成聊天记录.pdf"), CHAT_PDF);
writeFileSync(join(scanDir, "合成流水.xlsx"), STMT_XLSX);
writeFileSync(join(scanDir, "交付清单.csv"), TABLE_CSV, "utf8");

// 1 A1 粗扫默认不哈希（对拍 1 前半）
{
  const r = await api("POST", "/api/edisc/scan", { caseId: CASE, rootPath: scanDir });
  const items = r.data?.items ?? [];
  assert(1, r.status === 200 && items.length === 3 && items.every((x) => x.hashed === false && x.status === "registered"),
    "A1 目录扫描默认不哈希：3 件粗扫登记（对拍 1）", JSON.stringify(r.data));
}
// 2 A1 粗扫态字段：pending + 空 fileHash（入册前不可引用）
{
  const r = await api("GET", `/api/edisc/sources?caseId=${CASE}`);
  const stubs = r.data?.items?.filter((s) => !s.fileHash) ?? [];
  const all = r.data?.items ?? [];
  assert(2, r.status === 200 && all.length === 3 && stubs.length === 3 && stubs.every((s) => s.parseStatus === "pending"),
    "A1 粗扫源 parseStatus=pending 且 fileHash 空（A3 列表）", JSON.stringify(all.map((s) => [s.parseStatus, s.fileHash])));
}
// 3 A2 单源登记默认哈希+解析（对拍 1 后半）——聊天 PDF
let CHAT_ID = null;
{
  const r = await api("POST", "/api/edisc/sources", { caseId: CASE, kind: "chat", filename: "合成聊天记录.pdf", dataBase64: CHAT_PDF.toString("base64") });
  CHAT_ID = r.data?.id ?? null;
  assert(3, r.status === 200 && r.data?.parseStatus === "done" && r.data?.fileHash?.length === 64 && r.data?.ocrStatus === "not_required"
    && r.data?.blockCount > 0 && r.data?.pageCount === 2,
    "A2 聊天 PDF 登记默认哈希+解析 done（对拍 1）", JSON.stringify(r.data));
}
// 4 H1 对话段结构化（4 段，含两行内容段；引用必带锚）
{
  const r = await api("GET", `/api/edisc/sources/${CHAT_ID}/rows`);
  const rows = r.data?.rows ?? [];
  const match = rows.length === 4 && rows.every((x, i) =>
    x.cells[0] === CHAT_EXPECT[i].sentAt && x.cells[1] === CHAT_EXPECT[i].sender && x.cells[2] === CHAT_EXPECT[i].head
    && typeof x.blockId === "string" && x.blockId.startsWith("eb_"));
  assert(4, match, "H1 聊天段结构化：发送方/时间/内容逐段抽取且行行带锚（对拍 34）", JSON.stringify(rows.map((x) => x.cells[2])));
}
// 5 A2 内容寻址去重
{
  const r = await api("POST", "/api/edisc/sources", { caseId: CASE, kind: "chat", filename: "合成聊天记录-再传.pdf", dataBase64: CHAT_PDF.toString("base64") });
  assert(5, r.status === 200 && r.data?.deduplicated === true && r.data?.id === CHAT_ID, "A2 同内容重登记去重（同哈希同案同类型）", JSON.stringify({ id: r.data?.id }));
}
// 6 A2 流水 xlsx 登记 + B1 表清单（对拍 3 前半）
let STMT_ID = null;
{
  const r = await api("POST", "/api/edisc/sources", { caseId: CASE, kind: "statement", filename: "合成流水.xlsx", dataBase64: STMT_XLSX.toString("base64") });
  STMT_ID = r.data?.id ?? null;
  assert(6, r.status === 200 && r.data?.parseStatus === "done" && r.data?.tables?.length === 1 && r.data?.tables[0]?.name === "流水" && r.data?.tables[0]?.rowCount === 5,
    "A2/H2 流水 xlsx 登记解析：表清单=流水 5 行（对拍 3）", JSON.stringify(r.data?.tables));
}
// 7 A2 表格 CSV 登记（H3：行列对应保持）
let TABLE_ID = null;
{
  const r = await api("POST", "/api/edisc/sources", { caseId: CASE, kind: "table", filename: "交付清单.csv", dataBase64: Buffer.from(TABLE_CSV, "utf8").toString("base64") });
  TABLE_ID = r.data?.id ?? null;
  const prof = await api("GET", `/api/edisc/sources/${TABLE_ID}/profile`);
  const rowCount = prof.data?.tables?.[0]?.rowCount ?? 0;
  assert(7, r.status === 200 && r.data?.parseStatus === "done" && rowCount === 4,
    "A2/H3 表格 CSV 登记解析：4 行（表头+3 数据行，引号内逗号不破行）", JSON.stringify(prof.data?.tables));
}
// 8 A4 三态底座字段
{
  const r = await api("GET", `/api/edisc/sources/${STMT_ID}`);
  assert(8, r.status === 200 && r.data?.fileHash?.length === 64 && ["pending", "parsing", "done", "failed"].includes(r.data?.parseStatus)
    && ["not_required", "required", "hooked"].includes(r.data?.ocrStatus) && typeof r.data?.preprocess === "object",
    "A4 源级 fileHash/parseStatus/ocrStatus 三态底座+进场预处理记录可查（对拍 2/G7）", JSON.stringify({ h: r.data?.fileHash?.slice(0, 8), p: r.data?.parseStatus, o: r.data?.ocrStatus }));
}
// 9 A2 图片聊天 fail-closed（H1 首版=PDF 路径；截图需 OCR 明示）
{
  const png = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 0]);
  const r = await api("POST", "/api/edisc/sources", { caseId: CASE, kind: "chat", filename: "聊天截图.png", dataBase64: png.toString("base64") });
  assert(9, r.status === 200 && r.data?.parseStatus === "failed" && r.data?.error?.code === "NEEDS_OCR" && r.data?.ocrStatus === "required",
    "H1 聊天截图（图片）fail-closed：NEEDS_OCR 明示不伪造（UNKNOWN-4 口径）", JSON.stringify(r.data?.error));
}
// 10 缺失案件 404
{
  const r = await api("POST", "/api/edisc/sources", { caseId: "case_none", kind: "table", filename: "x.csv", dataBase64: Buffer.from("a,b\n1,2", "utf8").toString("base64") });
  assert(10, r.status === 404 && r.data?.error?.code === "CASE_NOT_FOUND", "缺失案件登记 404（对拍 54 同族）", JSON.stringify(r.data));
}

// ══════════ B 面：行寻址 ══════════
// 11 B2 默认区间与行号从 1 起（对拍 3）
{
  const r = await api("GET", `/api/edisc/sources/${STMT_ID}/rows?table=${encodeURIComponent("流水")}`);
  const rows = r.data?.rows ?? [];
  assert(11, r.status === 200 && r.data?.rowStart === 1 && r.data?.rowEnd === 50 && rows.length === 5 && rows[0]?.rowNo === 1,
    "B2 行读取默认 1..50、行号从 1 起（对拍 3）", JSON.stringify({ rowStart: r.data?.rowStart, rowEnd: r.data?.rowEnd, n: rows.length }));
}
// 12 B2 区间切片 + B4 三件套+哈希
{
  const r = await api("GET", `/api/edisc/sources/${STMT_ID}/rows?table=${encodeURIComponent("流水")}&rowStart=2&rowEnd=3`);
  const rows = r.data?.rows ?? [];
  assert(12, r.status === 200 && rows.length === 2 && rows[0]?.rowNo === 2 && rows[0]?.cells?.[1] === "合成示例贸易有限公司"
    && r.data?.sourceId === STMT_ID && r.data?.tableName === "流水" && r.data?.fileHash?.length === 64,
    "B2 区间即地址 + B4 行地址三件套+源哈希（对拍 5）", JSON.stringify(r.data?.rows?.[0]?.cells));
}
// 13 B2 行号 0 拒收
{
  const r = await api("GET", `/api/edisc/sources/${STMT_ID}/rows?table=${encodeURIComponent("流水")}&rowStart=0&rowEnd=3`);
  assert(13, r.status === 400, "B2 行号从 1 起：rowStart=0 拒收", JSON.stringify(r.data));
}
// 14 H2 金额双轨：字符串+整数分，禁浮点（对拍 35）
{
  const r = await api("GET", `/api/edisc/sources/${STMT_ID}/rows?table=${encodeURIComponent("流水")}&rowStart=2&rowEnd=2`);
  const amts = r.data?.rows?.[0]?.amounts ?? [];
  const a = amts.find((x) => x.text === "12800.00");
  const bal = amts.find((x) => x.text === "50233.60");
  assert(14, a && a.cents === 1280000 && bal && bal.cents === 5023360 && !amts.some((x) => x.cents !== null && !Number.isInteger(x.cents)),
    "H2 金额原文串+整数分双轨（12800.00→1280000 分），无浮点（对拍 35）", JSON.stringify(amts));
}
// 15 H3 CSV 千分位金额双轨
{
  const r = await api("GET", `/api/edisc/sources/${TABLE_ID}/rows?table=${encodeURIComponent("交付清单")}&rowStart=2&rowEnd=2`);
  const cells = r.data?.rows?.[0]?.cells ?? [];
  const amts = r.data?.rows?.[0]?.amounts ?? [];
  const a = amts.find((x) => x.text === "14,400.00");
  assert(15, cells.length === 6 && cells[1] === "钢结构构件" && a && a.cents === 1440000,
    "H3 CSV 行列对应（引号内逗号单元格完整）+千分位金额双轨（对拍 36）", JSON.stringify({ cells, a }));
}
// 16 B3 行搜索（可按案件/源收窄；命中=定位线索）+ E5 两段纪律（对拍 4/14）
{
  const r = await api("GET", `/api/edisc/search?caseId=${CASE}&q=${encodeURIComponent("货款")}`);
  const hits = r.data?.hits ?? [];
  const tables = [...new Set(hits.map((h) => h.tableName))];
  assert(16, r.status === 200 && hits.length >= 2 && tables.includes("聊天记录") && tables.includes("流水")
    && typeof r.data?.note === "string" && r.data.note.includes("定位线索"),
    "B3 行搜索跨聊天/流水命中 + 检索命中=定位线索纪律（对拍 4/14）", JSON.stringify({ n: hits.length, tables, note: r.data?.note?.slice(0, 24) }));
}
// 17 B3 limit 钳制 ≤200
{
  const r = await api("GET", `/api/edisc/search?caseId=${CASE}&q=${encodeURIComponent("元")}&limit=999`);
  assert(17, r.status === 200 && r.data?.limit === 200, "B3 limit 上限 200（对拍 4）", JSON.stringify({ limit: r.data?.limit }));
}
// 18 B3 按源收窄
{
  const r = await api("GET", `/api/edisc/search?caseId=${CASE}&sourceId=${STMT_ID}&q=${encodeURIComponent("房租")}`);
  const hits = r.data?.hits ?? [];
  assert(18, r.status === 200 && hits.length === 1 && hits[0]?.sourceId === STMT_ID && hits[0]?.rowNo === 3,
    "B3 按源收窄（对拍 4）", JSON.stringify(hits));
}
// 19 粗扫态源无行面（fail-closed）
{
  const list = await api("GET", `/api/edisc/sources?caseId=${CASE}`);
  const stub = list.data.items.find((s) => !s.fileHash);
  const r = await api("GET", `/api/edisc/sources/${stub.id}/rows`);
  assert(19, r.status === 409 && r.data?.error?.code === "NOT_PARSED", "粗扫源读行 409（入册前无行面）", JSON.stringify(r.data));
}

// ══════════ C 面：虚拟归类 ══════════
// 20 C1 归类负例：行号 0 / 引用粗扫源
{
  const list = await api("GET", `/api/edisc/sources?caseId=${CASE}`);
  const stub = list.data.items.find((s) => !s.fileHash);
  const r0 = await api("POST", "/api/edisc/classifications", { caseId: CASE, refs: [{ kind: "rows", sourceId: STMT_ID, tableName: "流水", rowStart: 0, rowEnd: 2 }], category: "x" });
  const r1 = await api("POST", "/api/edisc/classifications", { caseId: CASE, refs: [{ kind: "rows", sourceId: stub.id, tableName: "流水", rowStart: 1, rowEnd: 1 }], category: "x" });
  assert(20, r0.status === 400 && r1.status === 409 && r1.data?.error?.code === "NOT_HASHED",
    "C1 归类负例：非法行号 400 / 粗扫源 409（对拍 6 前置）", JSON.stringify([r0.data?.error?.code, r1.data?.error?.code]));
}
// 21 C1 三类归类（对拍 6：row 区间+category+reason，不改原件）
{
  const rc = await api("POST", "/api/edisc/classifications", { caseId: CASE, refs: [{ kind: "rows", sourceId: CHAT_ID, tableName: "聊天记录", rowStart: 1, rowEnd: 2 }], category: "借款沟通", reason: "对账与催款对话", createdBy: "律师甲" });
  const rs = await api("POST", "/api/edisc/classifications", { caseId: CASE, refs: [{ kind: "rows", sourceId: STMT_ID, tableName: "流水", rowStart: 2, rowEnd: 3 }], category: "货款收支", reason: "货款对应收支" });
  const rt = await api("POST", "/api/edisc/classifications", { caseId: CASE, refs: [{ kind: "rows", sourceId: TABLE_ID, tableName: "交付清单", rowStart: 2, rowEnd: 4 }], category: "交付明细", reason: "交付范围" });
  assert(21, rc.status === 200 && rs.status === 200 && rt.status === 200 && rc.data?.id && rs.data?.id && rt.data?.id,
    "C1 三类首做各归一行区间（对拍 6）", JSON.stringify([rc.data?.id, rs.data?.id, rt.data?.id]));
}
// 22 C2 读回 + C3 操作者留名（对拍 7）
{
  const r = await api("GET", `/api/edisc/classifications?caseId=${CASE}`);
  const items = r.data?.items ?? [];
  const bySrc = await api("GET", `/api/edisc/classifications?caseId=${CASE}&sourceId=${CHAT_ID}`);
  assert(22, items.length === 3 && bySrc.data?.items?.length === 1
    && items.some((x) => x.createdBy === "律师甲") && items.some((x) => x.createdBy === "律师"),
    "C2 归类按案件/源读回 + C3 操作者留名（默认律师/可指定）（对拍 7）", JSON.stringify(items.map((x) => [x.category, x.createdBy])));
}

// ══════════ D 面：候选清单与校验 ══════════
// 23 D1 从归类生成候选（对拍 8 前半）
let FIX = null;
{
  const r = await api("POST", "/api/edisc/fix-lists", { caseId: CASE });
  FIX = r.data?.created ?? [];
  assert(23, r.status === 200 && FIX.length === 3 && FIX.every((c) => c.status === "suggested" && c.anchors?.length >= 1 && c.anchors[0]?.digest?.length === 64)
    && typeof r.data?.suggestionNote === "string",
    "D1 已归类行→候选清单（3 类，建议档+落款摘要）（对拍 8）", JSON.stringify(FIX.map((c) => c.title)));
}
// 24 D1 重放去重
{
  const r = await api("POST", "/api/edisc/fix-lists", { caseId: CASE });
  assert(24, r.status === 200 && r.data?.created?.length === 0, "D1 同覆盖重生成去重", JSON.stringify({ n: r.data?.created?.length }));
}
// 25 D2/G6 校验全绿 + 回跳一致（验收口径）
{
  const r = await api("POST", "/api/edisc/fix-lists/verify", { caseId: CASE });
  assert(25, r.status === 200 && r.data?.ok === true && r.data?.checked >= 3 && r.data?.backjumpChecked >= 3 && r.data?.backjumpMismatched === 0,
    "D2/G6 校验：锚一一对应+回跳一致（对拍 8/33）", JSON.stringify(r.data));
}
// 26 G6 负例：白盒改动行文→回跳不一致可读指出（回读恢复后复绿）
{
  const stmtAnchor = FIX.find((c) => c.category === "货款收支").anchors[0];
  const row = dao.getRow(WS, STMT_ID, "流水", stmtAnchor.rows.rowStart);
  const orig = row.text;
  db.prepare("UPDATE edisc_rows SET text = ? WHERE workspace_key = ? AND source_id = ? AND table_name = ? AND row_no = ?")
    .run(orig + "（事后改动）", WS, STMT_ID, "流水", stmtAnchor.rows.rowStart);
  const bad = await api("POST", "/api/edisc/fix-lists/verify", { caseId: CASE });
  db.prepare("UPDATE edisc_rows SET text = ? WHERE workspace_key = ? AND source_id = ? AND table_name = ? AND row_no = ?")
    .run(orig, WS, STMT_ID, "流水", stmtAnchor.rows.rowStart);
  const good = await api("POST", "/api/edisc/fix-lists/verify", { caseId: CASE });
  assert(26, bad.data?.ok === false && bad.data?.backjumpMismatched === 1 && /回跳原文/.test(bad.data?.problems?.[0]?.issue ?? "") && good.data?.ok === true,
    "G6 行文被改→回跳不一致可读差异；恢复后复绿（对拍 33 负向）", JSON.stringify(bad.data?.problems));
}
// 27 E2 锚回跳：块锚（页/坐标）原文一致
{
  const r = await api("POST", "/api/edisc/anchors/resolve", { kind: "block", sourceId: CHAT_ID, page: 1, seq: 2 });
  assert(27, r.status === 200 && r.data?.text === CHAT_EXPECT[0].head && r.data?.bbox?.[0] === 56 && r.data?.bbox?.[1] === 752 && r.data?.bbox?.[3] === 762
    && r.data?.invariantOk === true && r.data?.coordSystem === "pdf-pt-v1-estwidth",
    "E2 块锚回跳：页1/seq2 原文与坐标框一致（56,752 → y1=762）（对拍 10/11）", JSON.stringify({ t: r.data?.text, bbox: r.data?.bbox }));
}
// 28 E2 锚回跳：行锚原文一致
{
  const r = await api("POST", "/api/edisc/anchors/resolve", { kind: "rows", sourceId: TABLE_ID, tableName: "交付清单", rowStart: 3, rowEnd: 3 });
  const cells = r.data?.rows?.[0]?.cells ?? [];
  assert(28, r.status === 200 && r.data?.invariantOk === true && cells[1] === "紧固件套件" && cells[5] === "备注含,逗号",
    "E2 行锚回跳：CSV 行原文一致（引号内逗号原样）（对拍 11）", JSON.stringify(cells));
}
// 29 E4 页卡整页覆盖（不抽样）
{
  const r = await api("GET", `/api/edisc/sources/${CHAT_ID}/pages?page=1`);
  const ft = r.data?.fullText ?? "";
  assert(29, r.status === 200 && ft.includes(CHAT_EXPECT[0].head) && ft.includes(CHAT_EXPECT[2].head.split("\n")[1])
    && Array.isArray(r.data?.blocks) && r.data.blocks.length >= 8 && typeof r.data?.note === "string",
    "E4 页卡整页块序+全文（禁抽样代覆盖阅读，纪律文案随发）（对拍 13）", JSON.stringify({ blocks: r.data?.blocks?.length }));
}
// 30 E4 越界页 404
{
  const r = await api("GET", `/api/edisc/sources/${CHAT_ID}/pages?page=99`);
  assert(30, r.status === 404, "E4 越界页 404", JSON.stringify(r.data));
}
// 31 E3 坐标批注（对拍 12）
{
  const r = await api("POST", "/api/edisc/annotations", { caseId: CASE, sourceId: CHAT_ID, pageNumber: 1, rects: [[56, 752, 221, 762]], type: "highlight", textContent: "催款", comment: "对应用户陈述", createdBy: "律师甲" });
  const list = await api("GET", `/api/edisc/annotations?caseId=${CASE}&sourceId=${CHAT_ID}&page=1`);
  const bad1 = await api("POST", "/api/edisc/annotations", { caseId: CASE, sourceId: CHAT_ID, pageNumber: 1, rects: [[1, 2]] });
  const bad2 = await api("POST", "/api/edisc/annotations", { caseId: CASE, sourceId: CHAT_ID, pageNumber: 1, rects: [[1, 2, 3, 4]], type: "涂改" });
  assert(31, r.status === 200 && list.data?.items?.length === 1 && list.data.items[0]?.rects?.[0]?.[1] === 752
    && bad1.status === 400 && bad2.status === 400,
    "E3 页/坐标批注挂虚拟层（rects 校验/类型闭集）（对拍 12）", JSON.stringify(list.data?.items?.[0]?.rects));
}

// ══════════ D3/G2/G3：确认分权与精化留痕 ══════════
const chatCand = FIX.find((c) => c.category === "借款沟通");
// 32 D3 无留名确认拒收
{
  const r = await api("POST", `/api/edisc/fix-lists/${chatCand.id}/confirm`, {});
  assert(32, r.status === 400, "D3 确认必须留名（对拍 9 前置）", JSON.stringify(r.data));
}
// 33 D3 律师确认→confirmed（候选不自动入正式）
{
  const r = await api("POST", `/api/edisc/fix-lists/${chatCand.id}/confirm`, { confirmedBy: "王律师" });
  assert(33, r.status === 200 && r.data?.status === "confirmed" && r.data?.confirmedBy === "王律师",
    "D3 人工确认分权：suggested→confirmed+留名（对拍 9）", JSON.stringify({ s: r.data?.status, by: r.data?.confirmedBy }));
}
// 34 G3 元数据更正默认干跑
{
  const r = await api("POST", `/api/edisc/fix-lists/${chatCand.id}/metadata`, { title: "微信对话：货款催收与到账", reason: "标题过泛" });
  const after = await api("GET", `/api/edisc/fix-lists?caseId=${CASE}`);
  const item = after.data.items.find((c) => c.id === chatCand.id);
  assert(34, r.status === 200 && r.data?.dryRun === true && item.title !== "微信对话：货款催收与到账",
    "G3 元数据更正默认 dry_run 预览不落库（对拍 30）", JSON.stringify({ dryRun: r.data?.dryRun, title: item.title }));
}
// 35 G3 confirmed=true 落库 + G2 精化留痕（对拍 29/30）
{
  const r = await api("POST", `/api/edisc/fix-lists/${chatCand.id}/metadata`, { title: "微信对话：货款催收与到账", reason: "标题过泛", confirmed: true, by: "王律师" });
  const audit = await api("GET", `/api/edisc/refinements?caseId=${CASE}`);
  const ops = audit.data?.items?.map((x) => x.op) ?? [];
  assert(35, r.status === 200 && r.data?.applied === true && ops.includes("metadata") && ops.includes("confirm")
    && audit.data.items.every((x) => x.before && x.after && x.by && x.at),
    "G3 confirmed 落库 + G2 精化通道留痕（before/after/by/at）（对拍 29/30）", JSON.stringify(ops));
}

// ══════════ F 面：审查标注与报告 ══════════
// 36 F5 未经公证聊天→默认存疑档+证明力弱（对拍 19）
let FLAG = null;
{
  const r = await api("POST", "/api/edisc/review-flags", { caseId: CASE, sourceId: CHAT_ID, targetLabel: "合成聊天记录.pdf", kind: "chat" });
  FLAG = r.data;
  assert(36, r.status === 200 && r.data?.level === "doubt" && r.data?.proofStrength === "弱"
    && r.data?.tags?.includes("存疑") && r.data?.tags?.includes("核实") && (r.data?.issues?.length ?? 0) >= 3
    && /篡改/.test((r.data?.weakens ?? []).join("")),
    "F5 未经公证聊天默认 ⚠️ 存疑+证明力弱+篡改攻击预判（对拍 19/20）", JSON.stringify({ l: r.data?.level, ps: r.data?.proofStrength, t: r.data?.tags }));
}
// 37 F5 公证/时间戳→ok 档
{
  const r = await api("POST", "/api/edisc/review-flags", { caseId: CASE, sourceId: STMT_ID, targetLabel: "合成流水.xlsx", kind: "statement", notarized: true });
  assert(37, r.status === 200 && r.data?.level === "ok" && r.data?.proofStrength === "中",
    "F5 经公证/时间戳→✅ 档（对拍 19 前半）", JSON.stringify({ l: r.data?.level }));
}
// 38 F11 档位/标记闭集
{
  const r1 = await api("POST", "/api/edisc/review-flags", { caseId: CASE, targetLabel: "x", kind: "chat", level: "完美" });
  const r2 = await api("POST", "/api/edisc/review-flags", { caseId: CASE, targetLabel: "x", kind: "chat", tags: ["随手标"] });
  assert(38, r1.status === 400 && r2.status === 400, "F11 档位/标记闭集拒收（对拍 26）", JSON.stringify([r1.status, r2.status]));
}
// 39 F12 七节报告 + F10 律师闸 + 引用核实双轮
{
  const r = await api("GET", `/api/edisc/review-report?caseId=${CASE}`);
  const t = r.data?.report ?? "";
  const sections = ["一、待证事实", "二、证据清单", "三、存疑标注清单", "四、不足记录", "五、缺口与补充建议", "六、质证预判", "七、规律性观察"];
  assert(39, r.status === 200 && sections.every((s) => t.includes(s)) && t.includes("律师逐项过目") && t.includes("原始载体")
    && t.includes("微信对话：货款催收与到账") && t.includes("回跳核验") && t.includes("局限声明") && r.data?.verify?.ok === true,
    "F12 七节报告+F10 律师闸+F8 引用核实双轮（对拍 26/25/23）", t.slice(0, 80));
}
// 40 F5 同类集中存疑合并（规律性观察）
{
  const r = await api("GET", `/api/edisc/review-report?caseId=${CASE}`);
  assert(40, /同类集中存疑/.test(r.data?.report ?? ""), "F5 末条 同类集中存疑合并为单一决定点（对拍 21）", "");
}

// ══════════ G 面：治理红线 ══════════
// 41 G1 原件只读：全链后存储件哈希不变
{
  const detail = await api("GET", `/api/edisc/sources/${CHAT_ID}`);
  const stored = readFileSync(join(dir, "artifacts", CASE, "edisc", "files", `${CHAT_ID}_合成聊天记录.pdf`));
  assert(41, sha256hex(stored) === detail.data?.fileHash, "G1 全链后原件字节不变（哈希一致）（对拍 28）", "");
}
// 42 G4 无破坏性删除入口
{
  const r = await api("DELETE", `/api/edisc/sources/${CHAT_ID}`);
  const r2 = await api("DELETE", `/api/edisc/fix-lists/${chatCand.id}`);
  assert(42, r.status === 404 && r2.status === 404, "G4 无删除路由（404=未暴露）（对拍 31）", JSON.stringify([r.status, r2.status]));
}
// 43 对拍 56 同族：本地鉴权挂点
{
  writeFileSync(join(dir, "auth.token"), "edisc-synth-token", "utf8");
  token = null;
  const no = await api("GET", `/api/edisc/sources?caseId=${CASE}`);
  token = "edisc-synth-token";
  const yes = await api("GET", `/api/edisc/sources?caseId=${CASE}`);
  token = null;
  rmSync(join(dir, "auth.token"), { force: true });
  assert(43, no.status === 401 && yes.status === 200, "本地鉴权挂点：token 文件在→401/带凭据→200（对拍 56 同族）", JSON.stringify([no.status, yes.status]));
}
// 44 审计入账（#30 面挂点）
{
  const actions = auditLog.map((a) => a.action);
  assert(44, ["edisc.source.register", "edisc.classify", "edisc.fixlist.generate", "edisc.fixlist.confirm", "edisc.metadata.refine", "edisc.annotation.create", "edisc.flag.create"].every((a) => actions.includes(a)),
    "审计挂点：登记/扫描/归类/清单/确认/更正/批注/标注全入账", JSON.stringify([...new Set(actions)]));
}

// ══════════ 对拍收尾面（施工波三轮 20261031：F1/F2/F4/F6/F9/F14/G5）══════════
// 46 F1 待证事实登记+读回+四类排除纪律随读回下发
{
  const r = await api("POST", "/api/edisc/facts", { caseId: CASE, text: "双方于 2026-03 就货款结算方式达成一致", note: "自聊天记录与流水印证" });
  const list = await api("GET", `/api/edisc/facts?caseId=${CASE}`);
  const bad = await api("POST", "/api/edisc/facts", { caseId: CASE, text: "  " });
  const rep = await api("GET", `/api/edisc/review-report?caseId=${CASE}`);
  assert(46, r.status === 200 && Boolean(r.data?.id) && list.data?.items?.length === 1
    && /无争议/.test(list.data?.exclusionNote ?? "") && bad.status === 400
    && rep.data.report.includes("1. 双方于 2026-03 就货款结算方式达成一致") && /公知事实/.test(rep.data.report),
    "F1 待证事实登记入卷：报告第一节以事实清单先行（四类排除纪律随发）（对拍 15）",
    JSON.stringify({ n: list.data?.items?.length, bad: bad.status }));
}
// 47 F2 形式六要素：缺项可读+补齐后齐备+落候选读回
{
  const partial = await api("POST", `/api/edisc/fix-lists/${chatCand.id}/elements`, { elements: { 名称: "微信对话：货款催收与到账", 形成时间: "2026-03-05" } });
  const full = await api("POST", `/api/edisc/fix-lists/${chatCand.id}/elements`, {
    elements: { 名称: "微信对话：货款催收与到账", 形成时间: "2026-03-05", 出具方: "自微信导出", 原件或复印件: "导出 PDF", 证明目的: "证明催款事实", 对应待证事实: "1" },
  });
  const list = await api("GET", `/api/edisc/fix-lists?caseId=${CASE}`);
  const item = list.data.items.find((c) => c.id === chatCand.id);
  const rep = await api("GET", `/api/edisc/review-report?caseId=${CASE}`);
  assert(47, partial.data?.check?.complete === false && partial.data.check.missing.length === 4 && /先补齐/.test(partial.data.check.note)
    && full.data?.check?.complete === true && item.formal?.check?.complete === true
    && /形式六要素：齐备/.test(rep.data.report),
    "F2 形式六要素：缺项给「先补齐再实质审查」可读提示；齐备随候选与报告（对拍 16）",
    JSON.stringify({ miss: partial.data?.check?.missing }));
}
// 48 F4 三性表单：闭集拒收+逐项结论理由落库+报告第三节输出
{
  const bad = await api("POST", "/api/edisc/triple-reviews", { caseId: CASE, targetLabel: "合成聊天记录.pdf", findings: [{ attr: "真实性", conclusion: "完美" }] });
  const bad2 = await api("POST", "/api/edisc/triple-reviews", { caseId: CASE, targetLabel: "x", findings: [{ attr: "客观性", conclusion: "符合" }] });
  const r = await api("POST", "/api/edisc/triple-reviews", {
    caseId: CASE, sourceId: CHAT_ID, targetLabel: "合成聊天记录.pdf",
    findings: [
      { attr: "真实性", conclusion: "存疑", reason: "未经公证，需印证" },
      { attr: "合法性", conclusion: "符合", reason: "本人手机导出" },
      { attr: "关联性", conclusion: "符合", reason: "直接对应货款结算待证事实" },
    ],
  });
  const list = await api("GET", `/api/edisc/triple-reviews?caseId=${CASE}`);
  const rep = await api("GET", `/api/edisc/review-report?caseId=${CASE}`);
  assert(48, bad.status === 400 && bad2.status === 400 && r.status === 200 && list.data?.items?.length === 1
    && list.data.items[0].findings.length === 3
    && rep.data.report.includes("真实性=存疑（未经公证，需印证）") && rep.data.report.includes("关联性=符合"),
    "F4 三性表单：属性/结论闭集拒收；逐项结论+理由入卷随报告第三节（对拍 18）",
    JSON.stringify({ bad: bad.status, bad2: bad2.status, n: list.data?.items?.[0]?.findings?.length }));
}
// 49 F6 四类缺口结构化：类目闭集+必给建议+报告第五节结构化行（含期限警示）
{
  const bad = await api("POST", "/api/edisc/gaps", { caseId: CASE, kind: "别的缺口", suggestion: "x" });
  const bad2 = await api("POST", "/api/edisc/gaps", { caseId: CASE, kind: "完全缺口" });
  const r = await api("POST", "/api/edisc/gaps", {
    caseId: CASE, kind: "证据链断裂", factText: "货款结算方式约定", suggestion: "调取对公账户全程流水印证",
    sourceChannel: "向银行申请调取", difficulty: "中", deadlineNote: "举证期限届满前提交",
  });
  const list = await api("GET", `/api/edisc/gaps?caseId=${CASE}`);
  const rep = await api("GET", `/api/edisc/review-report?caseId=${CASE}`);
  assert(49, bad.status === 400 && bad2.status === 400 && r.status === 200 && list.data?.items?.length === 1
    && /【证据链断裂】/.test(rep.data.report) && rep.data.report.includes("建议补充：调取对公账户全程流水印证")
    && /期限警示/.test(rep.data.report) && /取得渠道：向银行申请调取/.test(rep.data.report),
    "F6 四类缺口结构化：类目闭集+建议必填+四件套（事实/建议/渠道/难度）与期限警示随报告第五节（对拍 22）",
    JSON.stringify({ bad: bad.status, bad2: bad2.status }));
}
// 50 F9/F14 来源标签纪律+保密继承文案随报告
{
  const r = await api("GET", `/api/edisc/review-report?caseId=${CASE}`);
  assert(50, /须核实/.test(r.data.report) && /不得删标签/.test(r.data.report) && /不得无声补充/.test(r.data.report)
    && /保密继承/.test(r.data.report) && /随源保密/.test(r.data.report),
    "F9 网络来源须核实标签纪律+F14 保密继承文案入报告（对拍 24/27）", "");
}
// 51 G5 纯页卡档：pending 源经整理任务→done 且只产页卡/块锚（无对话段行面）
{
  const reg = await api("POST", "/api/edisc/sources", { caseId: CASE, kind: "chat", filename: "页卡档聊天.pdf", dataBase64: TASK_PDF_A.toString("base64"), parse: false });
  const sid = reg.data?.id;
  const t = await api("POST", "/api/edisc/tasks", { caseId: CASE, sourceIds: [sid], pageCardsOnly: true, tickMs: 20 });
  let task = t.data;
  for (let i = 0; i < 60 && task?.status === "running"; i++) {
    await sleep(50);
    task = (await api("GET", `/api/edisc/tasks/${t.data?.id}`)).data;
  }
  const detail = await api("GET", `/api/edisc/sources/${sid}`);
  const prof = await api("GET", `/api/edisc/sources/${sid}/profile`);
  assert(51, reg.data?.parseStatus === "pending" && t.data?.status === "running" && t.data?.summary?.checkpoint === 0
    && task?.status === "done" && task?.summary?.checkpoint === 1 && task?.summary?.done === 1
    && detail.data?.parseStatus === "done" && detail.data?.fileHash?.length === 64
    && prof.data?.chatMessages === 0 && (prof.data?.tables ?? []).length === 0 && (prof.data?.blocks ?? 0) > 0,
    "G5 仅页卡档：任务后台启动即返检查点 0；完成 checkpoint=1；只产页卡/块锚（对话段 0、表清单空）（对拍 32）",
    JSON.stringify({ st: task?.status, sum: task?.summary, chat: prof.data?.chatMessages }));
}
// 52 G5 stopOnError：失败即停（断点保留）→恢复→失败件重跑（attempts 累加）→取消
{
  const regGood = await api("POST", "/api/edisc/sources", { caseId: CASE, kind: "chat", filename: "整理件二.pdf", dataBase64: TASK_PDF_B.toString("base64"), parse: false });
  const regBad = await api("POST", "/api/edisc/sources", { caseId: CASE, kind: "chat", filename: "坏件整理.txt", dataBase64: Buffer.from("plain text", "utf8").toString("base64"), parse: false });
  const t = await api("POST", "/api/edisc/tasks", { caseId: CASE, sourceIds: [regGood.data?.id, regBad.data?.id], stopOnError: true, tickMs: 30 });
  let task = t.data;
  for (let i = 0; i < 80 && (!task || task.status === "running"); i++) {
    await sleep(50);
    task = (await api("GET", `/api/edisc/tasks/${t.data?.id}`)).data;
  }
  const pausedOk = task?.status === "paused" && task?.summary?.checkpoint === 2 && task?.summary?.done === 1 && task?.summary?.failed === 1;
  const badPause = await api("POST", `/api/edisc/tasks/${t.data?.id}/pause`);           // 已暂停再暂停=非法迁移 409
  const resumed = await api("POST", `/api/edisc/tasks/${t.data?.id}/resume`);           // 无待处理件→直接 done
  const recover = await api("POST", `/api/edisc/tasks/${t.data?.id}/recover-failed`);   // 失败件重排回队
  let task2 = recover.data;
  for (let i = 0; i < 80 && (!task2 || task2.status === "running"); i++) {
    await sleep(50);
    task2 = (await api("GET", `/api/edisc/tasks/${t.data?.id}`)).data;
  }
  const badItem = task2?.items?.find((i) => i.sourceId === regBad.data?.id);
  const canceled = await api("POST", `/api/edisc/tasks/${t.data?.id}/cancel`);
  assert(52, pausedOk && badPause.status === 409 && resumed.data?.status === "done"
    && recover.data?.status === "running" && task2?.status === "paused" && badItem?.attempts === 2
    && /PDF/.test(badItem?.error ?? "") && canceled.data?.status === "canceled",
    "G5 出错即停断点保留→恢复（终态 done）→失败件重跑（attempts 2）→取消；非法迁移 409（对拍 32）",
    JSON.stringify({ paused: task?.summary, st2: task2?.status, att: badItem?.attempts }));
}
// 53 G5 运行中暂停：检查点停在半程，恢复续传后全部完成
{
  const regA = await api("POST", "/api/edisc/sources", { caseId: CASE, kind: "chat", filename: "续传件A.pdf", dataBase64: TASK_PDF_A.toString("base64"), parse: false });
  const regB = await api("POST", "/api/edisc/sources", { caseId: CASE, kind: "table", filename: "续传件B.csv", dataBase64: Buffer.from(TABLE_CSV, "utf8").toString("base64"), parse: false });
  const t = await api("POST", "/api/edisc/tasks", { caseId: CASE, sourceIds: [regA.data?.id, regB.data?.id], tickMs: 120 });
  const paused = await api("POST", `/api/edisc/tasks/${t.data?.id}/pause`);             // 首 tick 前（+120ms）注入暂停
  const mid = paused.data?.summary;
  const resumed = await api("POST", `/api/edisc/tasks/${t.data?.id}/resume`);
  let task = resumed.data;
  for (let i = 0; i < 80 && (!task || task.status === "running"); i++) {
    await sleep(50);
    task = (await api("GET", `/api/edisc/tasks/${t.data?.id}`)).data;
  }
  const doneA = await api("GET", `/api/edisc/sources/${regA.data?.id}`);
  const doneB = await api("GET", `/api/edisc/sources/${regB.data?.id}`);
  assert(53, paused.data?.status === "paused" && mid.checkpoint < 2 && resumed.data?.status === "running"
    && task?.status === "done" && task?.summary?.done === 2 && task?.summary?.checkpoint === 2
    && doneA.data?.parseStatus === "done" && doneB.data?.parseStatus === "done",
    "G5 运行中暂停（检查点保留半程）→恢复续传→两件全 done（对拍 32）",
    JSON.stringify({ mid, fin: task?.summary }));
}
// 54 收尾面审计入账（事实/六要素/三性/缺口/任务五动作+任务终态）
{
  const actions = auditLog.map((a) => a.action);
  assert(54, ["edisc.fact.register", "edisc.formal.save", "edisc.triple.save", "edisc.gap.register",
    "edisc.task.start", "edisc.task.pause", "edisc.task.resume", "edisc.task.cancel", "edisc.task.recover.failed"].every((a) => actions.includes(a)),
    "收尾面审计挂点：事实/六要素/三性/缺口/任务（启停恢复取消失败重跑）全入账", JSON.stringify([...new Set(actions)]));
}

server.close();
db.close();

// ══════════ 接线冒烟：隔离端口桥实例（:3091；BRIDGE_PORT 自管，不碰 :3030/:43127）══════════
// 45 迁移 0020_edisc + 能力标记 + 路由接通（杀前核验命令行含 bridge_host.mjs）
{
  const PORT2 = Number(process.env.EDISC_TEST_BRIDGE_PORT ?? 3091);
  const logFd = openSync(join(dir, "bridge-3091.log"), "a");
  const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(PORT2) }, stdio: ["ignore", logFd, logFd], detached: true });
  child.unref();
  const probe = async () => {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT2}/api/server-info`, { signal: AbortSignal.timeout(2500) });
      return r.ok ? await r.json() : null;
    } catch { return null; }
  };
  let info = null;
  const deadline = Date.now() + 45000;
  while (Date.now() < deadline && !info) { info = await probe(); if (!info) await sleep(600); }
  let wired = false;
  let migrationOk = false;
  try {
    if (info) {
      const r = await fetch(`http://127.0.0.1:${PORT2}/api/edisc/sources?caseId=x`, { signal: AbortSignal.timeout(3000) });
      const body = await r.json().catch(() => null);
      // 路由接通：401（token 在）或 404 CASE_NOT_FOUND（token 不在）都证明分发到了 edisc 面
      wired = (r.status === 401 && body?.error?.code === "UNAUTHORIZED") || (r.status === 404 && body?.error?.code === "CASE_NOT_FOUND");
    }
    if (info) {
      const { homedir } = await import("node:os");
      const dbPath2 = join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${PORT2}.db`);
      const db2 = new DatabaseSync(dbPath2, { readOnly: true });
      migrationOk = db2.prepare("SELECT COUNT(*) AS n FROM schema_migration WHERE id IN ('0020_edisc', '0023_edisc_review')").get().n === 2;
      db2.close();
    }
  } catch (e) {
    fail(45, "桥接线冒烟异常", String(e?.message ?? e));
  }
  // 收尾：核验命令行后杀桥
  const cl = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${child.pid}").CommandLine`], { encoding: "utf8", timeout: 20000 });
  if (String(cl.stdout ?? "").includes("bridge_host.mjs")) {
    spawnSync("taskkill", ["/PID", String(child.pid), "/F", "/T"], { timeout: 15000 });
  } else {
    console.error(`[edisc-synth] 45: 注意 pid=${child.pid} 命令行不含 bridge_host.mjs，未杀（宁停不误杀）：${String(cl.stdout ?? "").slice(0, 120)}`);
  }
  assert(45, Boolean(info?.edisc === 1) && wired && migrationOk,
    "桥接线冒烟：server-info edisc:1 + /api/edisc 路由接通 + 迁移 0020_edisc/0023_edisc_review 落账", JSON.stringify({ edisc: info?.edisc, wired, migrationOk }));
}

// ══════════ 收尾 ══════════
rmSync(dir, { recursive: true, force: true });
if (failed > 0) {
  console.error(`EDISC_SYNTH_FAIL passed=${passed} failed=${failed}`);
  process.exit(1);
}
console.log(`EDISC_SYNTH_PASS passed=${passed}/${passed + failed}`);
process.exit(0);
