#!/usr/bin/env node
// 【功能 #6 材料上传解析】合成自测（RE-6 §4 对拍清单落码面逐项验收）。
// 全合成材料：买卖合同 txt（UTF-8/GBK 两版）、合同 docx（零依赖 zip 写入器现造）、原生/扫描/损坏
// PDF、PNG 头图片件、空 txt、未知 .xyz——临时目录现造现删，零 %APPDATA% 触碰（库/四件套全落临时目录）。
// 覆盖（对拍行号=RE-6 §4）：7/8/9/10 内容寻址+MIME 闸+作用域授权+安全原名；15 质量闸五项；
// 17/53 OCR 钩子+fail-closed 按因归名；18/19/20/21/22/23/24/25/26/27/28/29/31/33/43/44/45/52/
// 54/57/58/60/61 管道与边界；34/46/50/51/56 HTTP 面（双形态/400/404/413/401/缺失案件空态）；
// 47 无删除；13/14/16 注入块（地图/全文/图片状态行）。
// 纯 Node 零依赖；单命令 exit 0/1，末行 MATERIAL_SYNTH_PASS 可判。
// 用法：node tools/bridge/material_synthetic.mjs
import { mkdtempSync, writeFileSync, readFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http from "node:http";
import { DatabaseSync } from "node:sqlite";

const dir = mkdtempSync(join(tmpdir(), "juscite-material-synth-"));
let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[material-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[material-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }
function assert(n, cond, msg, detail) {
  if (cond) { ok(n, msg); return; }
  fail(n, msg, typeof detail === "string" ? detail : JSON.stringify(detail));
}

const svc = await import("./material_service.mjs");
const { MATERIALS_DDL_FULL, MATERIALS_DDL_FULL_FALLBACK, createMaterialDao, createMaterialService } = svc;

const WS = "ws_test";
const CASE = "case_1";
function freshDb(file, { fallbackFts = false } = {}) {
  const db = new DatabaseSync(file);
  db.exec("PRAGMA foreign_keys = ON");
  db.exec(fallbackFts ? MATERIALS_DDL_FULL_FALLBACK : MATERIALS_DDL_FULL);
  // 迁移 0019：附件产出方列（新库同形状）。重开库（t11 重启用例）列已在——真实桥由
  // schema_migration 账本保证不重放，这里按同幂等语义容忍重复应用。
  try { db.exec(svc.BRIDGE_ATTACHMENTS_PRODUCER_DDL); } catch (e) {
    if (!/duplicate column/i.test(String(e?.message ?? e))) throw e;
  }
  return db;
}
function makeService(db, { root = join(dir, "artifacts"), authFilePath = join(dir, "auth.token") } = {}) {
  return createMaterialService({
    dao: createMaterialDao(db),
    caseExists: (id) => id === CASE,
    root, workspaceKey: WS, authFilePath,
    now: () => new Date().toISOString(),
    log: () => {},
    auditWrite: () => {}, // RE-30 §3.5 写入面挂点（审计行为验收归 re30_synthetic，此处桩空转）
  });
}

// ── 合成材料工厂 ──
const CONTRACT_TXT = [
  "钢材买卖合同",
  "甲方：上海某某贸易有限公司与乙方：北京某某科技有限公司",
  "签订日期：2024年8月1日",
  "第一条 合同金额：人民币128,000元，含运费。",
  "（一）买受人应于签订后 10 日内支付预付款。",
  "1. 预付款比例为 30%。",
  "（1）逾期付款按日计违约金。",
  "第二条 交付期限为 45天，交付地点：杭州市余杭区。",
  "第三条 年利率为 4.35%，租赁期限为 3年。",
].join("\n");
const MARKER_OLD = "旧版独有词樟木箱";
const MARKER_NEW = "新版独有检索词青瓷盏";
const LONGER = "。本段文字足够长以通过质量闸的五项检查，包含足够的语义字符与行数结构，避免被误判为噪声文本。";

// GBK 合成件（真实 GBK 字节序列，UTF-8 解码必失败→命中第三档 gbk）
const GBK_DOC = Buffer.from(
  "b9bacffabacfcdacbcc7c2bca3acbcd7b7bda3bab1b1b7bdbbfad0b5b3a7d3ebd2d2b7bda3bac4cfb7bdb8d6b2c4b9abcbbe"
  + "a3acbbf5bfeec8cbc3f1b1d2cee5c7a7d4aad5fba3acc7a9b6a9c8d5c6daa3ba32303234c4ea36d4c238c8d5a1a3b1beb6ce"
  + "b9bacffacdf9c0b4c4dac8ddd7e3b9bbb3a4a3acbaacd3d0d7e3b9bbb6e0b5c4d3efd2e5d7d6b7fbd3ebd3d0d0a7d0d0bde1"
  + "b9b9a3acc4dcb9bbcda8b9fdbde2cef6d6cac1bfd5a2b5c4c8abb2bfcee5cfeebcecb2e9d2aac7f3a3accaf4d3dad3d0d0a7"
  + "b5c4c3b3d2d7b9bacffabacfcdaccdf9c0b4b2c4c1cfa1a3",
  "hex",
);

// 最小 zip 写入器（store 方法 0 + CRC32），供 docx 现造与 parseZip 读回
function crc32(buf) {
  let table = crc32.table;
  if (!table) {
    table = crc32.table = new Int32Array(256);
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
function makeZip(entries) {
  const locals = [], centrals = [];
  let offset = 0;
  for (const [name, data] of entries) {
    const nameBuf = Buffer.from(name, "utf8");
    const crc = crc32(data);
    const local = Buffer.alloc(30 + nameBuf.length);
    local.writeUInt32LE(0x04034b50, 0); local.writeUInt16LE(20, 4); local.writeUInt16LE(0, 6);
    local.writeUInt16LE(0, 8); local.writeUInt16LE(0, 10);
    local.writeUInt32LE(crc, 14); local.writeUInt32LE(data.length, 18); local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBuf.length, 26); local.writeUInt16LE(0, 28);
    nameBuf.copy(local, 30);
    locals.push(local, data);
    const central = Buffer.alloc(46 + nameBuf.length);
    central.writeUInt32LE(0x02014b50, 0); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0, 8); central.writeUInt16LE(0, 10); central.writeUInt16LE(0, 12);
    central.writeUInt32LE(crc, 16); central.writeUInt32LE(data.length, 20); central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(nameBuf.length, 28); central.writeUInt16LE(0, 30); central.writeUInt16LE(0, 32);
    central.writeUInt16LE(0, 34); central.writeUInt16LE(0, 36); central.writeUInt32LE(offset, 42);
    nameBuf.copy(central, 46);
    centrals.push(central);
    offset += local.length + data.length;
  }
  const cd = Buffer.concat(centrals);
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10); eocd.writeUInt32LE(cd.length, 12); eocd.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, cd, eocd]);
}
function makeDocx(bodyXml) {
  const xml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${bodyXml}</w:body></w:document>`;
  return makeZip([
    ["[Content_Types].xml", Buffer.from("<Types/>")],
    ["word/document.xml", Buffer.from(xml, "utf8")],
  ]);
}
const DOCX_CONTRACT = makeDocx(
  "<w:p><w:r><w:t>房屋租赁合同</w:t></w:r></w:p>"
  + "<w:p><w:r><w:t>出租人（甲方）：李某</w:t></w:r></w:p>"
  + "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>项目</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>金额</w:t></w:r></w:p></w:tc></w:tr>"
  + "<w:tr><w:tc><w:p><w:r><w:t>月租金</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>12000元</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
  + "<w:p><w:r><w:t>第一条 租赁期限为 2年，租金见上表。</w:t></w:r></w:p>",
);
const DOCX_BROKEN = Buffer.from("this is not a zip file at all ......");

function makePdf(textOps) {
  const stream = `BT /F1 12 Tf ${textOps.map((t) => `(${t}) Tj`).join(" ")} ET`;
  const parts = [
    "%PDF-1.4\n",
    "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
    "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
    "3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj\n",
    `4 0 obj << /Length ${stream.length} >>\nstream\n${stream}\nendstream\nendobj\n`,
    "trailer << /Root 1 0 R /Size 5 >>\n%%EOF",
  ];
  return Buffer.from(parts.join(""), "latin1");
}
const PDF_NATIVE = makePdf([
  "SALES CONTRACT of steel products between two parties",
  "Article 1 Total amount RMB 128000 yuan including freight",
  "Article 2 Delivery within 45 days to Hangzhou city",
  "Article 3 Annual interest rate 4.35 percent per year",
]);
const PDF_SCANNED = makePdf([]); // 骨架在、无文本操作=扫描件
const PDF_BROKEN = Buffer.from("junk bytes not a pdf");
const PNG_BYTES = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(64, 7)]);
const EMPTY_TXT = Buffer.from("", "utf8");
const NOISE_TXT = Buffer.from("?!".repeat(120), "utf8"); // 紧凑≥40 但语义字符 0→质量闸③不过

// ══ 用例 1：Intake 路由矩阵（对拍 25/26/27/41 + 52 分类区分）══
{
  const r1 = svc.intakeRoute({ filename: "合同.txt", bytes: Buffer.from(CONTRACT_TXT) });
  assert(1, r1.decision === "parse" && r1.type === "text", "intake txt→text 放行", r1);
  const r2 = svc.intakeRoute({ filename: "怪文件.xyz", bytes: Buffer.from("x") });
  assert(2, r2.decision === "reject" && /暂不支持的文件格式/.test(r2.reason), "未知 .xyz 拒收（对拍 27 不跟）", r2.reason);
  const r3 = svc.intakeRoute({ filename: "老文档.doc", bytes: Buffer.from("x") });
  assert(3, r3.decision === "reject" && /docx/.test(r3.reason), "doc fail-closed 提示转存（对拍 41）", r3.reason);
  const r4 = svc.intakeRoute({ filename: "大.pdf", bytes: PDF_NATIVE, byteSize: 101 * 1024 * 1024 });
  assert(4, r4.decision === "reject" && /100MB/.test(r4.reason), "超 100MB 拒收+上限文案", r4.reason);
  const r5 = svc.intakeRoute({ filename: "扫.pdf", bytes: PDF_SCANNED });
  assert(5, r5.decision === "parse" && r5.hasTextLayer === false && r5.subKind === "scanned" && r5.humanReview === true, "无文本层 PDF 判 scanned+人工复核", JSON.stringify(r5));
  const r6 = svc.intakeRoute({ filename: "坏.pdf", bytes: PDF_BROKEN });
  assert(6, r6.decision === "parse" && r6.subKind === "damaged", "损坏 PDF 判 damaged（对拍 52 分类区分）", r6.subKind ?? "");
  const r7 = svc.intakeRoute({ filename: "照.png", bytes: PNG_BYTES });
  assert(7, r7.decision === "parse" && r7.type === "image" && r7.ocrRequired === true, "图片判需 OCR", r7.type);
  const r8 = svc.intakeRoute({ filename: "表.xlsx", bytes: Buffer.from("x") });
  assert(8, r8.decision === "reject", "xlsx v1 不做=明确拒收（对拍 40）", r8.reason);
}

// ══ 用例 2：解码链/规范化/质量闸（对拍 18/44/61/15）══
{
  const gbk = Buffer.from([0xb9, 0xba, 0xcf, 0xfa, 0xba, 0xcf, 0xcd, 0xac]); // "购销合同" GBK 字节
  const dec = svc.decodeTextBuffer(gbk);
  assert(9, dec.encoding === "gbk" && dec.text === "购销合同", "GBK 命中第三档（对拍 18/44）", JSON.stringify(dec));
  const norm = svc.normalizeExtractedText("a\u0000b\u200bc\uFEFF\n\n\n\n\nd");
  assert(10, norm === "abc\n\nd", "规范化去 NUL/零宽/BOM/压缩空行（对拍 61）", JSON.stringify(norm));
  assert(11, svc.usableExtractedText("short").ok === false && svc.usableExtractedText("short").item === "compact<40", "质量闸① 紧凑<40", "");
  assert(12, svc.usableExtractedText(`${"甲".repeat(40)}\uE000\uE001\uE002`).ok === false, "质量闸② 私用区超限", "");
  assert(13, svc.usableExtractedText("?!".repeat(60)).ok === false && svc.usableExtractedText("?!".repeat(60)).item === "semantic<20", "质量闸③ 语义绝对数<20", "");
  const mostlyNoise = `${"abcdefghij"}${"?!".repeat(200)}klmnopqrst`;
  assert(14, svc.usableExtractedText(mostlyNoise).ok === false && svc.usableExtractedText(mostlyNoise).item === "semantic-ratio<35%", "质量闸④ 语义占比<35%", svc.usableExtractedText(mostlyNoise).item ?? "");
  const lowLineValid = ["abcdefghij", "....", "klmnopqrst", "....", "uvwxyzabcd", "....", "....", "....", "...."].join("\n");
  assert(15, svc.usableExtractedText(lowLineValid).ok === false && svc.usableExtractedText(lowLineValid).item === "line-valid<50%", "质量闸⑤ 行有效比<50%", svc.usableExtractedText(lowLineValid).item ?? "");
}

// ══ 用例 3：docx 表格竖线/损坏 docx（对拍 19/52）══
{
  const text = svc.extractDocxMaterial(DOCX_CONTRACT);
  assert(16, text.includes("月租金 | 12000元"), "docx 表格行逐行+竖线连接（对拍 19）", text);
  let threw = null;
  try { svc.extractDocxMaterial(DOCX_BROKEN); } catch (e) { threw = e; }
  assert(17, threw && threw.code === "DAMAGED" && /文件损坏或无法读取/.test(threw.message), "损坏 docx 抛 DAMAGED 稳定文案（对拍 52）", threw?.message ?? "");
}

// ══ 用例 4：PDF 文本层块结构（对拍 20/29）══
{
  const { blocks, pageCount } = svc.extractPdfTextLayer(PDF_NATIVE);
  assert(18, blocks.length === 1 && blocks[0].page === 1 && blocks[0].seq === 0 && blocks[0].source === "text_layer" && blocks[0].bbox === null && blocks[0].ocrVersion === null, "PDF 块带 page/seq/source/bbox/ocrVersion 四元组", JSON.stringify(blocks[0]));
  assert(19, pageCount >= 1, "页数计数", String(pageCount));
  assert(20, svc.extractPdfTextLayer(PDF_SCANNED).blocks.length === 0, "扫描 PDF 无文本块（不产假文本，对拍 29 不跟）", "");
}

// ══ 用例 5：条款分块/层级树/日期样排除（对拍 21/57）══
{
  const chunks = svc.chunkClauses(CONTRACT_TXT);
  const types = chunks.map((c) => `${c.type}:${c.title}`);
  assert(21, types.includes("段:甲方") && types.includes("条:第一条") && types.includes("款:（一）") && types.includes("项:1.") && types.includes("目:（1）"), "五型分块+当事人段", types.join(","));
  const chunks2 = svc.chunkClauses(`第一条 总则\n2024年8月1日双方签字盖章\n第二条 其他`);
  assert(22, chunks2.length === 2 && chunks2[0].title === "第一条" && chunks2[1].title === "第二条", "日期样行不作分块头", JSON.stringify(chunks2.map((c) => c.title)));
  const tree = svc.buildClauseTree(chunks);
  const kuan = chunks.find((c) => c.type === "款");
  assert(23, (svc.clauseTreePathOf(tree, kuan.title) ?? "").startsWith("第一条>"), "层级树路径可寻址（第一条>款）", svc.clauseTreePathOf(tree, kuan.title) ?? "");
}

// ══ 用例 6：实体抽取六类+两缺陷修复+金额整型分（对拍 22/45；工程约束 2）══
{
  const ents = svc.extractEntities(CONTRACT_TXT);
  const parties = ents.filter((e) => e.type === "party").map((e) => e.text);
  assert(24, parties.includes("上海某某贸易有限公司"), "角色行贪婪截断修复：名称止于「与」（对拍 45）", parties.join("|"));
  assert(25, parties.includes("北京某某科技有限公司") && parties.includes("上海某某贸易有限公司"), "公司名整取无截断（竞品海某某缺陷不跟）", parties.join("|"));
  const amt = ents.find((e) => e.type === "amount");
  assert(26, amt && amt.normalized === String(128000 * 100) && amt.attributes.display === "128,000元" && amt.attributes.kind === "金额", "金额整型分+关键词类型（对拍 22，非竞品 float）", JSON.stringify(amt));
  const date = ents.find((e) => e.type === "date");
  assert(27, date && date.normalized === "2024-08-01" && date.attributes.kind === "签订", "日期+关键词类型标注", JSON.stringify(date));
  assert(28, ents.some((e) => e.type === "term" && e.normalized === "1095"), "期限 3 年→1095 天", JSON.stringify(ents.filter((e) => e.type === "term")));
  const ratio = ents.find((e) => e.type === "ratio" && e.normalized === "435");
  assert(29, ratio && ratio.unit === "bp", "利率 4.35%→435bp 整数无浮点", JSON.stringify(ents.filter((e) => e.type === "ratio")));
  assert(30, ents.some((e) => e.type === "location" && /杭州|余杭/.test(e.text)), "地点抽取", JSON.stringify(ents.filter((e) => e.type === "location")));
  assert(31, svc.inferDocType(CONTRACT_TXT).docSubtype === "sales_contract", "合同子类 sales_contract（对拍 23）", "");
  assert(32, svc.inferDocType("民事判决书").docSubtype === "civil_judgment" && svc.inferDocType("保密协议").docSubtype === "nda" && svc.inferDocType("起诉状").docSubtype === "complaint" && svc.inferDocType("答辩状").docSubtype === "answer" && svc.inferDocType("证据清单").docSubtype === "evidence_list", "其余类型推断子类表", "");
  const amounts = svc.amountToCents("128,000", "");
  assert(33, amounts === 12800000 && Number.isSafeInteger(amounts), "amountToCents 逗号千分位→整型分", String(amounts));
}

// ══ 用例 7：全管道（txt/docx/GBK/空/噪声/未知/扫描/损坏/图片/doc）＋四件套＋版本链＋检索+缓存 ══
{
  const db = freshDb(join(dir, "t7.db"));
  const root = join(dir, "art7");
  const m = makeService(db, { root });
  const txt = await m.ingestMaterial({ caseId: CASE, filename: "买卖合同.txt", bytes: Buffer.from(CONTRACT_TXT, "utf8") });
  assert(34, txt.status === "ready" && txt.version === 1 && txt.parse.engine === "direct_read(utf-8)", "txt 全管道 ready", txt.error?.message ?? "");
  assert(35, txt.semantic.chunkCount >= 5 && txt.semantic.entityCount >= 5 && txt.documentSubtype === "sales_contract", "txt 进语义层（对拍 57 不跟）", JSON.stringify(txt.semantic));

  const paths = svc.artifactsPaths(root, CASE, txt.id, "买卖合同.txt");
  assert(36, existsSync(paths.storedPath) && existsSync(paths.textPath) && existsSync(paths.semanticPath) && existsSync(paths.reportPath), "四件套落盘（对拍 24）", JSON.stringify(paths));
  const report = JSON.parse(readFileSync(paths.reportPath, "utf8"));
  const keys = Object.keys(report).sort();
  assert(37, JSON.stringify(keys) === JSON.stringify(["block_count", "doc_id", "file_name", "intake_decision", "ocr_result", "page_count", "processed_at", "semantic"]), "report 八键（对拍 24）", keys.join(","));
  assert(38, report.semantic.docSubtype === "sales_contract" && report.semantic.parties.includes("上海某某贸易有限公司"), "report 语义摘要含当事人", JSON.stringify(report.semantic.parties));

  // docx 管道
  const dx = await m.ingestMaterial({ caseId: CASE, filename: "租赁合同.docx", bytes: DOCX_CONTRACT });
  assert(39, dx.status === "ready" && dx.parse.engine === "docx_paragraphs" && dx.documentSubtype === "lease_contract", "docx 管道 ready+子类", JSON.stringify({ err: dx.error, eng: dx.parse.engine }));

  // GBK txt（对拍 44：多编码兜底全链路）
  const gk = await m.ingestMaterial({ caseId: CASE, filename: "购销记录.txt", bytes: GBK_DOC });
  assert(40, gk.status === "ready" && gk.parse.engine === "direct_read(gbk)", "GBK txt 解码入库不崩（对拍 44 不跟竞品 pipeline utf-8-only）", JSON.stringify({ err: gk.error, eng: gk.parse.engine }));

  // 空文本 fail-closed（对拍 28）
  const empty = await m.ingestMaterial({ caseId: CASE, filename: "空白.txt", bytes: EMPTY_TXT });
  assert(41, empty.status === "failed" && empty.error?.code === "EMPTY_TEXT" && empty.error.message === "未提取到文字", "空文本判失败（对拍 28 不跟）", JSON.stringify(empty.error));

  // 噪声文本：质量闸③拦截→EMPTY_TEXT
  const noise = await m.ingestMaterial({ caseId: CASE, filename: "噪声.txt", bytes: NOISE_TXT });
  assert(42, noise.status === "failed" && noise.error?.code === "EMPTY_TEXT", "质量闸不过→fail-closed（对拍 15）", JSON.stringify(noise.error));

  // 未知类型拒收
  let rej = null;
  try { await m.ingestMaterial({ caseId: CASE, filename: "怪文件.xyz", bytes: Buffer.from("x") }); } catch (e) { rej = e; }
  assert(43, rej && rej.code === "UNSUPPORTED_FORMAT" && rej.http === 400, "未知类型 400（对拍 27）", rej?.message ?? "");

  // 扫描 PDF：OCR 钩子未配→NEEDS_OCR（对拍 17/53 按因归名）
  const scanned = await m.ingestMaterial({ caseId: CASE, filename: "扫描件.pdf", bytes: PDF_SCANNED });
  assert(44, scanned.status === "failed" && scanned.error?.code === "NEEDS_OCR" && /需 OCR/.test(scanned.error.message) && scanned.parse.humanReview === true, "扫描件报需 OCR（不产假文本）", JSON.stringify(scanned.error));

  // 损坏 PDF/损坏 docx：DAMAGED 分类（对拍 52）
  const broken = await m.ingestMaterial({ caseId: CASE, filename: "损坏.pdf", bytes: PDF_BROKEN });
  assert(45, broken.status === "failed" && broken.error?.code === "DAMAGED" && /文件损坏或无法读取/.test(broken.error.message), "损坏 PDF 报损坏（非误导性需 OCR）", JSON.stringify(broken.error));
  const bdx = await m.ingestMaterial({ caseId: CASE, filename: "损坏.docx", bytes: DOCX_BROKEN });
  assert(46, bdx.status === "failed" && bdx.error?.code === "DAMAGED", "损坏 docx 捕获转 fail-closed（对拍 52 不跟竞品直穿）", JSON.stringify(bdx.error));

  // 图片：NEEDS_OCR 图片文案（对拍 53）
  const img = await m.ingestMaterial({ caseId: CASE, filename: "照片.png", bytes: PNG_BYTES });
  assert(47, img.status === "failed" && img.error?.code === "NEEDS_OCR" && /图片材料需 OCR/.test(img.error.message), "图片按因归名报需 OCR（非文本为空）", JSON.stringify(img.error));

  // 版本链（对拍 31）+ 只搜最新版（对拍 33）+ 解析缓存（对拍 60）
  const v1 = await m.ingestMaterial({ caseId: CASE, filename: "合同.txt", bytes: Buffer.from(`租赁合同条款示例。${MARKER_OLD}。租金人民币五千元，签订日期：2024年1月2日${LONGER}`, "utf8") });
  const v2 = await m.ingestMaterial({ caseId: CASE, filename: "合同.txt", bytes: Buffer.from(`租赁合同条款示例。${MARKER_NEW}。租金人民币六千元，签订日期：2024年2月3日${LONGER}`, "utf8") });
  assert(48, v1.version === 1 && v2.version === 2 && v2.supersedes === v1.id, "同名重传 v2+supersedes（对拍 31）", JSON.stringify({ v1: v1.version, v2: v2.version, sup: v2.supersedes }));
  const lst = m.listMaterials(CASE);
  const contractLatest = lst.latest.filter((x) => x.title === "合同"); // title 默认=文件名主干（对拍 31 同主干口径；损坏.pdf/.docx 同主干共链同竞品）
  assert(49, contractLatest.length === 1 && contractLatest[0].version === 2, "latest 只含最高版本", JSON.stringify(lst.latest.map((x) => `${x.title}v${x.version}`)));
  const hitNew = m.searchMaterials(CASE, MARKER_NEW);
  const hitOld = m.searchMaterials(CASE, MARKER_OLD);
  assert(50, hitNew.hits.length >= 1 && hitNew.hits.every((h) => h.materialId === v2.id), "检索命中新版（对拍 33 latest-only）", JSON.stringify({ newHits: hitNew.hits.length, mode: hitNew.mode }));
  assert(51, hitOld.hits.length === 0, "旧版内容不进检索", JSON.stringify(hitOld.hits));

  // 同内容重传→解析缓存命中（对拍 60）
  const v3 = await m.ingestMaterial({ caseId: CASE, filename: "合同.txt", bytes: Buffer.from(`租赁合同条款示例。${MARKER_NEW}。租金人民币六千元，签订日期：2024年2月3日${LONGER}`, "utf8") });
  const rep3 = JSON.parse(readFileSync(svc.artifactsPaths(root, CASE, v3.id, "合同.txt").reportPath, "utf8"));
  assert(52, v3.version === 3 && rep3.ocr_result.cacheHit === true, "五元组缓存命中不重复抽取（对拍 60）", JSON.stringify(rep3.ocr_result));

  // 案件缺失：上传 404、列表 200 双空、检索空（对拍 54/51）
  let nf = null;
  try { await m.ingestMaterial({ caseId: "case_missing", filename: "x.txt", bytes: Buffer.from(CONTRACT_TXT) }); } catch (e) { nf = e; }
  assert(53, nf && nf.http === 404 && nf.code === "CASE_NOT_FOUND", "缺失案件上传 404", nf?.message ?? "");
  const missList = m.listMaterials("case_missing");
  assert(54, missList.items.length === 0 && missList.latest.length === 0, "缺失案件列表=双空 200 态", "");
  assert(55, m.searchMaterials("case_missing", "任何词").hits.length === 0, "缺失案件检索=空结果态", "");

  // 无删除面（对拍 47）
  assert(56, !("deleteMaterial" in m) && !("removeMaterial" in m) && !("voidMaterial" in m), "服务无删除/作废入口（对拍 47）", Object.keys(m).join(","));
}

// ══ 用例 8：附件库（对拍 7/8/9/10/47）+ 注入块（对拍 13/14/16）══
{
  const db = freshDb(join(dir, "t8.db"));
  const m = makeService(db, { root: join(dir, "art8") });
  const a1 = m.putAttachment({ bytes: Buffer.from(CONTRACT_TXT, "utf8"), filename: "合同说明.txt", mimeType: "text/plain", threadIds: ["t1"] });
  const a2 = m.putAttachment({ bytes: Buffer.from(CONTRACT_TXT, "utf8"), filename: "合同说明.txt", mimeType: "text/plain", threadIds: ["t2"] });
  assert(57, a1.attachmentId.startsWith("att_") && a1.attachmentId.length === 28 && a2.attachmentId === a1.attachmentId && a2.deduplicated === true, "att_<sha256 前 24>+同内容合并作用域（对拍 7）", a1.attachmentId);
  const row = m.readAttachment(a1.attachmentId, { threadId: "t1" });
  assert(58, row.filename === "合同说明.txt" && existsSync(row.named_path), "安全原名落盘+作用域内可读（对拍 9/10）", row.named_path);
  let f403 = null;
  try { m.readAttachment(a1.attachmentId, { threadId: "other" }); } catch (e) { f403 = e; }
  assert(59, f403 && f403.http === 403, "作用域外 403（对拍 9）", f403?.message ?? "");
  const aNo = m.putAttachment({ bytes: Buffer.from("无作用域附件内容，用于验证匿名拒读 fail-closed 语义，内容足够长。", "utf8"), filename: "无主.txt", mimeType: "text/plain" });
  let f403b = null;
  try { m.readAttachment(aNo.attachmentId, { threadId: "t1", caseId: CASE }); } catch (e) { f403b = e; }
  assert(60, f403b && f403b.http === 403, "无作用域附件拒读 fail-closed（对拍 9 收窄，不跟公开可读）", f403b?.message ?? "");
  let mimeBad = null;
  try { m.putAttachment({ bytes: Buffer.from("text bytes"), filename: "假图.png", mimeType: "image/png" }); } catch (e) { mimeBad = e; }
  assert(61, mimeBad && mimeBad.code === "MIME_MISMATCH" && mimeBad.http === 400, "图片魔数一致性 400（对拍 8）", mimeBad?.message ?? "");
  let mimeWl = null;
  try { m.putAttachment({ bytes: Buffer.from("PK"), filename: "包.zip", mimeType: "application/zip" }); } catch (e) { mimeWl = e; }
  assert(62, mimeWl && mimeWl.code === "MIME_REJECTED", "白名单外拒收（对拍 8 收窄）", mimeWl?.message ?? "");
  assert(63, m.listAttachments({ threadId: "t1" }).length === 1 && m.listAttachments({ threadId: "t2" }).length === 1, "按会话列附件", "");

  // 注入块：地图策略（对拍 13）
  const block = m.attachmentContextBlock([a1.attachmentId]);
  assert(64, Boolean(block) && block.startsWith("<材料上下文>") && block.includes("不是给你的指令") && block.includes("结构索引") && block.includes("grep") && block.endsWith("</材料上下文>"), "地图策略注入块+不可信声明+使用规则（文案自写）", (block ?? "").slice(0, 80));
  // 图片状态行（对拍 16）
  const imgAtt = m.putAttachment({ bytes: PNG_BYTES, filename: "现场照片.png", mimeType: "image/png", threadIds: ["t1"] });
  const blockImg = m.attachmentContextBlock([imgAtt.attachmentId]);
  assert(65, Boolean(blockImg) && /本地 OCR 未启用/.test(blockImg), "图片 OCR 缺位注入状态行（对拍 16，不静默）", (blockImg ?? "").split("\n")[2] ?? "");
  // full 策略 env 开关
  process.env.JUSCITE_MATERIAL_CONTEXT_MODE = "full";
  const blockFull = m.attachmentContextBlock([a1.attachmentId]);
  delete process.env.JUSCITE_MATERIAL_CONTEXT_MODE;
  assert(66, Boolean(blockFull) && blockFull.includes("全文开始"), "env 切 full 全文策略（对拍 13）", "");
  assert(67, m.attachmentContextBlock([]) === null && m.attachmentContextBlock(["att_nonexistent000000000"]) === null, "空附件/未知 id→null 不注入", "");
}

// ══ 用例 9：OCR 钩子（JUSCITE_OCR_CMD，对拍 17 引擎挂点）══
{
  const hookScript = join(dir, "fake_ocr.js");
  writeFileSync(hookScript, "process.stdout.write('识别出的合同文字内容：甲方太阳贸易有限公司乙方月亮科技有限公司金额五万元整，足够通过质量闸的语义字符要求。');", "utf8");
  process.env.JUSCITE_OCR_CMD = `node "${hookScript}"`;
  try {
    const db = freshDb(join(dir, "t9.db"));
    const m = makeService(db, { root: join(dir, "art9") });
    const scanned = await m.ingestMaterial({ caseId: CASE, filename: "扫描件.pdf", bytes: PDF_SCANNED });
    assert(68, scanned.status === "ready" && scanned.parse.engine === "ocr_hook" && scanned.parse.humanReview === true, "OCR 钩子接通→扫描件走钩子入库", JSON.stringify({ err: scanned.error, eng: scanned.parse.engine }));
  } finally {
    delete process.env.JUSCITE_OCR_CMD;
  }
}

// ══ 用例 10：HTTP 面（对拍 34/46/50/51/54/56 + 43 批量隔离）══
async function withServer(m, fn) {
  const server = http.createServer(async (req, res) => {
    const handled = await m.httpHandler(req, res, new URL(req.url ?? "/", "http://localhost"));
    if (!handled) { res.writeHead(404); res.end("no route"); }
  });
  await new Promise((res) => server.listen(0, "127.0.0.1", res));
  const port = server.address().port;
  const base = `http://127.0.0.1:${port}`;
  try {
    return await fn(base);
  } finally {
    const closed = new Promise((res) => server.close(res));
    server.closeAllConnections(); // 413 中断读取后 keep-alive 插座不再可复用，显式清尽防 close 悬等
    await closed;
  }
}
{
  const db = freshDb(join(dir, "t10.db"));
  const m = makeService(db, { root: join(dir, "art10") });
  await withServer(m, async (base) => {
    // multipart 三件：好件+未知+空件 → 单件隔离+汇总（对拍 34/43）
    const fd = new FormData();
    fd.append("caseId", CASE);
    fd.append("files", new Blob([Buffer.from(CONTRACT_TXT, "utf8")]), "采购合同.txt");
    fd.append("files", new Blob([Buffer.from("x")]), "怪文件.xyz");
    fd.append("files", new Blob([EMPTY_TXT]), "空白.txt");
    const r1 = await fetch(`${base}/api/cases/materials/upload`, { method: "POST", body: fd });
    const d1 = await r1.json();
    assert(69, r1.status === 200 && d1.summary.ok === 1 && d1.summary.failed === 2 && d1.items[0].status === "ready" && d1.items[1].error?.code === "UNSUPPORTED_FORMAT" && d1.items[2].error?.code === "EMPTY_TEXT", "multipart 批量单件隔离+汇总（对拍 34/43）", JSON.stringify(d1.summary));

    // JSON text 双形态（对拍 34）
    const r2 = await fetch(`${base}/api/cases/materials/upload`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ caseId: CASE, text: `粘贴文本材料：买卖合同价款人民币九千元整，签订日期：2024年3月4日${LONGER}`, title: "粘贴文本" }),
    });
    const d2 = await r2.json();
    assert(70, r2.status === 200 && d2.items[0].status === "ready" && d2.items[0].title === "粘贴文本", "JSON text 形态入库", JSON.stringify(d2.items?.[0]?.error));

    // 400：无文件无文本（对拍 46）
    const r3 = await fetch(`${base}/api/cases/materials/upload`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ caseId: CASE }) });
    assert(71, r3.status === 400, "无文件无文本 400", String(r3.status));

    // 404 上传缺失案件 / 200 双空列表 / 空检索（对拍 54/51）
    const r4 = await fetch(`${base}/api/cases/materials/upload`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ caseId: "case_missing", text: `足够长的文本内容，包含合同与金额人民币三千元整以及签订日期：2024年5月6日${LONGER}` }) });
    const d4 = await r4.json();
    assert(72, r4.status === 404 && d4.error?.code === "CASE_NOT_FOUND", "缺失案件上传 404 稳定文案", JSON.stringify(d4.error));
    const r5 = await fetch(`${base}/api/cases/materials?caseId=case_missing`);
    const d5 = await r5.json();
    assert(73, r5.status === 200 && d5.items.length === 0 && d5.latest.length === 0, "缺失案件列表=200 双空（对拍 54 收窄）", "");
    const r6 = await fetch(`${base}/api/cases/materials/search?caseId=case_missing&q=合同`);
    const d6 = await r6.json();
    assert(74, r6.status === 200 && d6.hits.length === 0, "缺失案件检索=空结果态", "");

    // 详情+原件（对拍 10 预览通道）
    const mid = d1.items[0].id;
    const r7 = await fetch(`${base}/api/cases/materials/${mid}`);
    const d7 = await r7.json();
    assert(75, r7.status === 200 && d7.semanticFull && Array.isArray(d7.semanticFull.chunks), "详情含语义全量", "");
    const r8 = await fetch(`${base}/api/cases/materials/${mid}/file`);
    const fileText = await r8.text();
    assert(76, r8.status === 200 && fileText.includes("钢材买卖合同"), "原件可读（预览通道）", "");

    // 附件面：上传/去重/作用域读取/403/400（对拍 7/8/9/46）
    const attBytes = Buffer.from(CONTRACT_TXT, "utf8").toString("base64");
    const ra = await fetch(`${base}/api/attachments`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ dataBase64: attBytes, filename: "附件.txt", mimeType: "text/plain", threadIds: ["th1"] }) });
    const da = await ra.json();
    const ra2 = await fetch(`${base}/api/attachments`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ dataBase64: attBytes, filename: "附件.txt", mimeType: "text/plain", threadIds: ["th2"] }) });
    const da2 = await ra2.json();
    assert(77, ra.status === 200 && da.attachmentId.startsWith("att_") && da2.attachmentId === da.attachmentId && da2.deduplicated === true, "附件内容寻址去重", da.attachmentId ?? "");
    const rc1 = await fetch(`${base}/api/attachments/${da.attachmentId}/content?threadId=th1`);
    const dc1 = await rc1.json();
    assert(78, rc1.status === 200 && dc1.dataBase64 && Buffer.from(dc1.dataBase64, "base64").toString("utf8").includes("钢材买卖合同"), "作用域内 base64 读回（对拍 9/11）", "");
    const rc2 = await fetch(`${base}/api/attachments/${da.attachmentId}/content?threadId=nope`);
    assert(79, rc2.status === 403, "作用域外 403", String(rc2.status));
    const rm = await fetch(`${base}/api/attachments`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ dataBase64: Buffer.from("text").toString("base64"), filename: "假图.png", mimeType: "image/png" }) });
    assert(80, rm.status === 400, "MIME 魔数不符 400（对拍 8）", String(rm.status));

    // DELETE 无路由=404（对拍 47）
    const rd = await fetch(`${base}/api/cases/materials/${mid}`, { method: "DELETE" });
    assert(81, rd.status === 404, "无删除路由（对拍 47）", String(rd.status));

    // 401：本地鉴权挂点（对拍 56）——token 文件存在即强制
    writeFileSync(join(dir, "auth.token"), "synth-token-123", "utf8");
    const r401 = await fetch(`${base}/api/cases/materials?caseId=${CASE}`);
    assert(82, r401.status === 401, "token 文件存在+无凭据→401（对拍 56）", String(r401.status));
    const r200 = await fetch(`${base}/api/cases/materials?caseId=${CASE}`, { headers: { "x-juscite-token": "synth-token-123" } });
    assert(83, r200.status === 200, "带凭据放行", String(r200.status));
    rmSync(join(dir, "auth.token"), { force: true });
    const r200b = await fetch(`${base}/api/cases/materials?caseId=${CASE}`);
    assert(84, r200b.status === 200, "token 文件移除恢复回环默认姿态", String(r200b.status));

    // 413：multipart 超 100MB（对拍 50）——放本面最后（服务端在 100MB 处中断读取并回 413，
    // 未消费完的请求体会让客户端连接池里的 keep-alive 插座吃 RST，后续请求须用新连接）
    const big = new FormData();
    big.append("caseId", CASE);
    big.append("files", new Blob([Buffer.alloc(101 * 1024 * 1024, 1)]), "大文件.txt");
    const rbig = await fetch(`${base}/api/cases/materials/upload`, { method: "POST", body: big });
    const dbig = await rbig.json().catch(() => null);
    assert(85, rbig.status === 413 && dbig?.error?.code === "PAYLOAD_TOO_LARGE", "超 100MB→413（对拍 50）", String(rbig.status));
  });
}

// ══ 用例 11：FTS 降级（unicode61）与重启持久 ══
{
  const dbFile = join(dir, "t11.db");
  const db1 = freshDb(dbFile, { fallbackFts: true });
  const m1 = makeService(db1, { root: join(dir, "art11") });
  await m1.ingestMaterial({ caseId: CASE, filename: "降级库合同.txt", bytes: Buffer.from(CONTRACT_TXT, "utf8") });
  const hit = m1.searchMaterials(CASE, "钢材买卖");
  assert(86, hit.hits.length >= 1, "unicode61 降级库检索可用（迁移 fallbackSql 同构）", hit.mode);
  const db2 = freshDb(dbFile, { fallbackFts: true });
  const m2 = makeService(db2, { root: join(dir, "art11") });
  const lst = m2.listMaterials(CASE);
  assert(87, lst.items.length >= 1 && lst.items[0].status === "ready", "重开库记录仍在（重启不丢）", String(lst.items.length));
}

// ══ 用例 12：附件产出方标记（对话文件面板 用户文件/Agent 产出 分组数据源；迁移 0019）══
{
  const db = freshDb(join(dir, "t12.db"));
  const m = makeService(db, { root: join(dir, "art12"), authFilePath: "" });
  const up1 = m.putAttachment({ bytes: Buffer.from("用户上传件", "utf8"), filename: "用户件.txt", mimeType: "text/plain", threadIds: ["thp"] });
  const up2 = m.putAttachment({ bytes: Buffer.from("代理产出件", "utf8"), filename: "代理件.txt", mimeType: "text/plain", threadIds: ["thp"], producer: "agent" });
  const up3 = m.putAttachment({ bytes: Buffer.from("非法产出方", "utf8"), filename: "非法.txt", mimeType: "text/plain", threadIds: ["thp"], producer: "hacker" });
  assert(88, up1.producer === undefined || up1.producer === "user", "上传返回形状稳定", JSON.stringify(up1));
  const listed = m.listAttachments({ threadId: "thp" });
  const byName = new Map(listed.map((x) => [x.filename, x.producer]));
  assert(89, byName.get("用户件.txt") === "user" && byName.get("代理件.txt") === "agent", "producer 落库：缺省 user/agent 显式（分组数据源）", JSON.stringify([...byName]));
  assert(90, byName.get("非法.txt") === "user", "非法 producer 值按 user 收敛（闭集外不落 agent）", byName.get("非法.txt") ?? "");
  const up4 = m.putAttachment({ bytes: Buffer.from("用户上传件", "utf8"), filename: "用户件.txt", mimeType: "text/plain", threadIds: ["thp2"] });
  assert(91, up4.attachmentId === up1.attachmentId && up4.deduplicated === true, "同内容重传跨产出方仍去重（对拍 7 语义不变）", up4.attachmentId ?? "");
}

// ══ 用例 13：parse 置信度贯穿（§3 数据模型 parse「引擎/置信度/耗时/警告/human_review」；r8 缺项补齐）══
{
  const db = freshDb(join(dir, "t13.db"));
  const m = makeService(db, { root: join(dir, "art13"), authFilePath: "" });
  const txt = await m.ingestMaterial({ caseId: CASE, filename: "置信度合同.txt", bytes: Buffer.from(CONTRACT_TXT, "utf8") });
  assert(92, txt.status === "ready" && txt.parse.confidence === 1, "直读引擎置信度=1（无损直读）", JSON.stringify(txt.parse));
  const dx = await m.ingestMaterial({ caseId: CASE, filename: "置信度租赁.docx", bytes: DOCX_CONTRACT });
  assert(93, dx.status === "ready" && dx.parse.confidence === 0.95, "docx 引擎置信度=0.95（对齐竞品 auto 口径）", JSON.stringify(dx.parse));
  const pdf = await m.ingestMaterial({ caseId: CASE, filename: "置信度判决.pdf", bytes: PDF_NATIVE });
  assert(94, pdf.status === "ready" && pdf.parse.confidence === 0.9, "pdf 文本层置信度=0.9（对齐竞品 pymupdf 口径）", JSON.stringify(pdf.parse));
  const detail = m.getMaterialDetail(txt.id);
  assert(95, typeof detail.semanticFull === "object" && Array.isArray(detail.semanticFull.chunks), "详情语义全量仍可读（置信度增列不破坏既有面）", "");
  const report = JSON.parse(readFileSync(join(dir, "art13", CASE, "materials", `${txt.id}.report.json`), "utf8"));
  assert(96, report.ocr_result.confidence === 1 && typeof report.ocr_result.durationMs === "number", "report.ocr_result 带置信度（对齐竞品 ocr_report 引擎+置信+耗时键面）", JSON.stringify(report.ocr_result));
  const ocrRow = await m.ingestMaterial({ caseId: CASE, filename: "钩子扫描.pdf", bytes: PDF_SCANNED, title: "钩子扫描专属标题" });
  assert(97, ocrRow.status === "failed" && ocrRow.error?.code === "NEEDS_OCR" && ocrRow.parse.confidence === null, "失败/OCR 行置信度=null 如实（不伪造）", JSON.stringify(ocrRow.parse));
}

// ── 收尾 ──
try { rmSync(dir, { recursive: true, force: true }); } catch { /* 临时目录清理尽力而为 */ }
console.log(`[material-synth] 合成自测完成：${passed} OK / ${failed} FAIL`);
if (failed > 0) {
  console.error("[material-synth] MATERIAL_SYNTH_FAIL");
  process.exit(1);
}
console.log("[material-synth] MATERIAL_SYNTH_PASS");
process.exit(0);
