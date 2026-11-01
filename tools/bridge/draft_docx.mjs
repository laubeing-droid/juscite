// 功能 #10 Word 导出（RE-10 §3.3 流程4 / §2 F2 F3 I13）：零依赖 docx 装配。
// 双路：①有原 DOCX（哈希校验过）→ 按模板占位段落槽位原位写回（仅改 word/document.xml，其余 entry 原字节保留）；
//       ②无原文件 → 自研 markdown→docx（宋体基线、中文序号标题规范化、简单竖线表格）。
// 原位写回结构损坏四态各自 throw（I13）：markdown 无可写块 / 缺 document.xml / body 结构无效 / 无可写段落。
import { parseZip } from "./skills_service.mjs";
import { crc32, deflateRawSync } from "node:zlib";


export function buildZip(entries) {
  const parts = [];
  const centrals = [];
  let offset = 0;
  for (const e of entries) {
    const compressed = deflateRawSync(e.data, { level: 6 });
    const crc = crc32(e.data) >>> 0;
    const nameBuf = Buffer.from(e.name, "utf8");
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0, 6);
    local.writeUInt16LE(8, 8);
    local.writeUInt16LE(0, 10);
    local.writeUInt16LE(0x21, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(compressed.length, 18);
    local.writeUInt32LE(e.data.length, 22);
    local.writeUInt16LE(nameBuf.length, 26);
    local.writeUInt16LE(0, 28);
    parts.push(local, nameBuf, compressed);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt16LE(0, 8);
    central.writeUInt16LE(8, 10);
    central.writeUInt16LE(0, 12);
    central.writeUInt16LE(0x21, 14);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(compressed.length, 20);
    central.writeUInt32LE(e.data.length, 24);
    central.writeUInt16LE(nameBuf.length, 28);
    central.writeUInt32LE(offset, 42);
    centrals.push(central, nameBuf);
    offset += 30 + nameBuf.length + compressed.length;
  }
  const centralStart = offset;
  let centralSize = 0;
  for (const c of centrals) centralSize += c.length;
  const eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0);
  eocd.writeUInt16LE(entries.length, 8);
  eocd.writeUInt16LE(entries.length, 10);
  eocd.writeUInt32LE(centralSize, 12);
  eocd.writeUInt32LE(centralStart, 16);
  return Buffer.concat([...parts, ...centrals, eocd]);
}

// ---------- XML 工具 ----------
function xmlEscape(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&apos;");
}
const FONT = "宋体"; // 字体基线：宋体（用户显式指定优先——当前导出面未开放字体选择，恒宋体）
function run(text, opts = {}) {
  const sz = opts.sz ?? 24;
  const rpr = `<w:rPr><w:rFonts w:ascii="${FONT}" w:eastAsia="${FONT}" w:hAnsi="${FONT}"/>` +
    (opts.bold ? "<w:b/>" : "") + `<w:sz w:val="${sz}"/><w:szCs w:val="${sz}"/></w:rPr>`;
  return `<w:r>${rpr}<w:t xml:space="preserve">${xmlEscape(text)}</w:t></w:r>`;
}
function para(text, opts = {}) {
  const jc = opts.center ? '<w:jc w:val="center"/>' : "";
  return `<w:p><w:pPr>${jc}</w:pPr>${run(text, opts)}</w:p>`;
}

// ---------- 中文序号标题规范化（标准格式路）：#→一、…；##→（一）…；剥既有序号防重复 ----------
function chineseOrdinal(n) {
  const D = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"];
  if (n <= 10) return n === 10 ? "十" : D[n];
  if (n < 20) return "十" + D[n - 10];
  if (n < 100) return D[Math.floor(n / 10)] + "十" + (n % 10 ? D[n % 10] : "");
  return String(n);
}
const STRIP_NUM = /^(?:[一二三四五六七八九十百\d]+\s*[、.．]\s*|（[一二三四五六七八九十]+）\s*)/;
export function normalizeHeadingsFull(md) {
  let h1 = 0;
  const out = [];
  for (const raw of String(md ?? "").split(/\r?\n/)) {
    const line = raw.replace(/^[ \t]+/, "");
    const m1 = /^#\s+(.*)$/.exec(line);
    const m2 = /^##\s+(.*)$/.exec(line);
    if (m1) { h1 += 1; out.push(chineseOrdinal(h1) + "、" + m1[1].replace(STRIP_NUM, "")); continue; }
    if (m2) { out.push("（" + chineseOrdinal(h1) + "）" + m2[1].replace(STRIP_NUM, "")); continue; }
    out.push(raw);
  }
  return out.join("\n");
}

// ---------- markdown → 标准法律文书 docx（标题/段落/简单竖线表格；宋体基线） ----------
export function markdownToLegalDocx(md) {
  const normed = normalizeHeadingsFull(md);
  const lines = String(normed ?? "").split(/\r?\n/);
  const body = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const parseRow = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const header = parseRow(line);
      const rows = [];
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(parseRow(lines[i])); i++; }
      const border = '<w:tblBorders><w:top w:val="single" w:sz="4"/><w:left w:val="single" w:sz="4"/><w:bottom w:val="single" w:sz="4"/><w:right w:val="single" w:sz="4"/><w:insideH w:val="single" w:sz="4"/><w:insideV w:val="single" w:sz="4"/></w:tblBorders>';
      const tr = (cells, bold) => "<w:tr>" + cells.map((c) =>
        `<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr><w:p>${run(c, { bold })}</w:p></w:tc>`).join("") + "</w:tr>";
      body.push(`<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>${border}</w:tblPr>${tr(header, true)}${rows.map((r) => tr(r, false)).join("")}</w:tbl>`);
      continue;
    }
    const t = line.trim();
    if (/^#\s+/.test(t)) body.push(para(t.replace(/^#\s+/, ""), { bold: true, sz: 32, center: true }));
    else if (/^##\s+/.test(t)) body.push(para(t.replace(/^##\s+/, ""), { bold: true, sz: 28 }));
    else if (t) body.push(para(t));
    i++;
  }
  const documentXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' +
    body.join("") +
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>';
  const contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>';
  const rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>';
  return buildZip([
    { name: "[Content_Types].xml", data: Buffer.from(contentTypes, "utf8") },
    { name: "_rels/.rels", data: Buffer.from(rels, "utf8") },
    { name: "word/document.xml", data: Buffer.from(documentXml, "utf8") },
  ]);
}

// ---------- 原位写回（保版式）：模板段落中「整段恰为一个 {{占位}}」者为槽位；生成段落按序入槽 ----------
function paragraphOf(xml) {
  // 返回 [{start,end,text,startTagEnd}]（startTagEnd=首个 <w:t 内容起点不好取，改为重建整段）
  const paras = [];
  const re = /<w:p\b[\s\S]*?<\/w:p>/g;
  let m;
  while ((m = re.exec(xml)) !== null) {
    let text = "";
    const tre = /<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/g;
    let t;
    while ((t = tre.exec(m[0])) !== null) text += t[1];
    paras.push({ start: m.index, end: m.index + m[0].length, inner: m[0], text });
  }
  return paras;
}
function decodeEntities(s) {
  return s.replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d))).replace(/&amp;/g, "&");
}
// 把段落 inner 重写为「保留首个 run 的 rPr、文本换新」的段；空文本=清空段内文字（保段落槽位）
function rewriteParagraph(inner, newText) {
  const firstRpr = (/<w:rPr>[\s\S]*?<\/w:rPr>/.exec(inner) ?? [""])[0];
  const body = newText === "" ? "" : `<w:r>${firstRpr}<w:t xml:space="preserve">${xmlEscape(newText)}</w:t></w:r>`;
  return inner.replace(/<w:r\b[\s\S]*?<\/w:r>/g, "").replace(/(<w:p\b[^>]*>)([\s\S]*?)(<\/w:p>)/, (_a, open, mid, close) => open + mid + body + close);
}
export function docxInPlaceFill(originalBytes, markdown) {
  // 四态前置：生成内容无可写块
  const blocks = String(markdown ?? "").split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!blocks.length) throw new Error("生成内容没有可写回的段落，无法原位导出");
  let entries;
  try {
    entries = parseZip(originalBytes);
  } catch (e) {
    throw new Error("模板原文件解析失败：" + (e?.message ?? e));
  }
  const docEntry = entries.get("word/document.xml") ?? entries.get("/word/document.xml");
  if (!docEntry) throw new Error("模板原文件缺少 word/document.xml，无法原位写回");
  const xml = docEntry.toString("utf8");
  const bodyStart = xml.indexOf("<w:body");
  if (bodyStart < 0) throw new Error("模板原文件 body 结构无效，无法原位写回");
  const paras = paragraphOf(xml);
  const slots = paras.filter((p) => {
    const t = decodeEntities(p.text).trim();
    return /^\{\{[^{}]+\}\}$/.test(t);
  });
  if (!slots.length) throw new Error("模板原文件中没有可写入的占位段落（未找到 {{占位}} 槽位）");
  if (blocks.length > slots.length) {
    throw new Error(`生成内容共 ${blocks.length} 段，多于模板可写段落 ${slots.length} 个；请改用标准格式导出或精简内容`);
  }
  // 逐槽位替换（从后往前改，避免位置漂移）；多余槽位清空文字
  let out = xml;
  for (let i = slots.length - 1; i >= 0; i--) {
    const newText = i < blocks.length ? blocks[i] : "";
    out = out.slice(0, slots[i].start) + rewriteParagraph(slots[i].inner, newText) + out.slice(slots[i].end);
  }
  const newEntries = [];
  for (const [name, data] of entries) {
    if (name === "word/document.xml" || name === "/word/document.xml") continue;
    newEntries.push({ name, data }); // 其余 entry 原字节保留：版式/样式/页眉页脚/表格全保
  }
  newEntries.push({ name: "word/document.xml", data: Buffer.from(out, "utf8") });
  return buildZip(newEntries);
}

// ---------- 【步骤4·#4 对拍 35】工作汇报「办案时间轴」节 docx（零依赖装配，复用 run/para/buildZip）----------
// 行结构由 caseTimelineModel.buildCaseTimelineReportLines 单源产出：日期 run 加粗（C12「日期加粗」），
// 事件/备注常规 run（「事件 — 备注」同构）；空表=整句兜底行。确定性纯装配，无 LLM 参与、不改既有导出管线。
export function buildCaseReportDocx({ docTitle, sectionTitle, lines, emptyText }) {
  const body = [];
  body.push(para(String(docTitle ?? "工作汇报"), { bold: true, sz: 32, center: true }));
  body.push(para(String(sectionTitle ?? "办案时间轴"), { bold: true, sz: 28 }));
  if (!Array.isArray(lines) || lines.length === 0) {
    body.push(para(String(emptyText ?? "该案暂无时间线节点。")));
  } else {
    for (const l of lines) {
      const runs = [run(String(l?.dateText ?? ""), { bold: true }), run("：" + String(l?.eventText ?? ""))];
      if (l?.noteText) runs.push(run(" — " + String(l.noteText)));
      body.push(`<w:p><w:pPr></w:pPr>${runs.join("")}</w:p>`);
    }
  }
  const documentXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' +
    body.join("") +
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>';
  const contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>';
  const rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>';
  return buildZip([
    { name: "[Content_Types].xml", data: Buffer.from(contentTypes, "utf8") },
    { name: "_rels/.rels", data: Buffer.from(rels, "utf8") },
    { name: "word/document.xml", data: Buffer.from(documentXml, "utf8") },
  ]);
}
