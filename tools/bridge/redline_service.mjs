// 功能 #11 Word 红线改稿（施工单-03 任务一）：确定性小件。
// ①合成 .docx → 纯文本：零依赖 zip 解析（复用 skills_service parseZip）+ OOXML 正文提取
//   （document.xml：段落 </w:p> 断行、w:t 取字、XML 实体解码；w:del 块=被删文字不入正文）——
//   确定性解析，不靠模型猜（法律工作区约束）。
// ②终稿装配：按律师逐条接受/拒绝的决定，把修订项（docdiff hunk 形状）确定性套回原文。
import { parseZip } from "./skills_service.mjs";

// .docx → 正文文本（段落以 \n 相连）。缺 word/document.xml 或解析失败显式抛错。
export function extractDocxText(bytes) {
  let entries;
  try {
    entries = parseZip(bytes);
  } catch (e) {
    throw new Error(`docx 解析失败：${e?.message ?? e}`);
  }
  const xmlEntry = entries.get("word/document.xml") ?? entries.get("/word/document.xml");
  if (!xmlEntry) throw new Error("docx 缺少 word/document.xml（不是有效的 Word 文档）");
  return xmlBytesToText(xmlEntry);
}

function xmlBytesToText(xmlBytes) {
  const xml = xmlBytes.toString("utf8");
  const paras = [];
  for (const seg of xml.split("</w:p>")) {
    // 被删文字（w:del 块，内为 delText）不属于正文；插入文字（w:del 块内）用 w:t，照常计入。
    const cleaned = seg.replace(/<w:del\b[\s\S]*?<\/w:del>/g, "");
    let text = "";
    const re = /<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/g;
    let m;
    while ((m = re.exec(cleaned)) !== null) text += decodeXmlEntities(m[1]);
    if (text !== "") paras.push(text); // 全段被删/空段不入正文（避免幻影空行）
  }
  while (paras.length && paras[paras.length - 1] === "") paras.pop();
  return paras.join("\n");
}

function decodeXmlEntities(s) {
  return s
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d)))
    .replace(/&amp;/g, "&");
}

// 终稿装配：逐 hunk 顺序走原文行——未触及行照抄；hunk 处→接受吐 newText 行，
// 拒绝吐 oldText 行（纯增 hunk 拒绝=不加）。确定性，不依赖模型。
// items: [{type,aStart,aCount,oldText,newText,decision}]（0 基行号，同 docdiff hunk 形状）。
export function applyRedlineDecisions(originalText, items) {
  const a = originalText.split(/\r\n|\r|\n/);
  const out = [];
  let cursor = 0;
  for (const it of items) {
    for (let i = cursor; i < it.aStart && i < a.length; i++) out.push(a[i]);
    if (it.decision === "accepted") {
      if (it.newText) out.push(...it.newText.split("\n"));
    } else if (it.type === "mod" || it.type === "del") {
      out.push(...it.oldText.split("\n"));
    }
    cursor = it.aStart + (it.type === "add" ? 0 : it.aCount);
  }
  for (let i = cursor; i < a.length; i++) out.push(a[i]);
  return out.join("\n");
}
