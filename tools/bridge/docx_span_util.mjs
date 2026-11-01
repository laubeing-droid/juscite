// OOXML 段内文本定位与 run 拆分底座（吸收件转写 A3 批注注入 / A5 修订落痕共用）。
// 纯字符串/正则确定性操作，零依赖（法律工作区约束：解析走确定性手段，不靠模型猜）。
// 职责：①枚举 document.xml 段落并取其拼接纯文本；②把段内某字符区间从 run 边界处
// 切开成 before/mid/after 三段 XML（mid 恰含目标文本，原 run 的 rPr 随拆分复制）；
// 供上层在 mid 两侧包注释锚/修订标记。拆不动（run 非单一 w:t，如含 w:br/w:tab）时
// 整 run 划入 mid（区间向外吸附到 run 边界），保证 mid 文本始终是超集、总文本不变。

export function decodeXmlText(s) {
  return String(s ?? "")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'").replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(Number(d)))
    .replace(/&amp;/g, "&");
}

export function encodeXmlText(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&apos;");
}

// 枚举段落：[{start,end,inner,text}]，text=段内全部 w:t 解码拼接（w:delText 不算正文）。
export function listParagraphs(xml) {
  const paras = [];
  const re = /<w:p\b[\s\S]*?<\/w:p>/g;
  let m;
  while ((m = re.exec(xml)) !== null) {
    let text = "";
    const tre = /<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/g;
    let t;
    while ((t = tre.exec(m[0])) !== null) text += decodeXmlText(t[1]);
    paras.push({ start: m.index, end: m.index + m[0].length, inner: m[0], text });
  }
  return paras;
}

// 单 run 的可拆分判定：恰一个 w:t、无其他内容子元素（w:br/w:tab 等不可拆）。
function runTextParts(runXml) {
  const parts = [];
  const re = /<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/g;
  let t;
  while ((t = re.exec(runXml)) !== null) parts.push(t[1]);
  return parts;
}
function isSplittable(runXml, partCount) {
  if (partCount !== 1) return false;
  const inner = runXml.replace(/^<w:r(?:\s[^>]*)?>/, "").replace(/<\/w:r>$/, "");
  // 除 rPr 与该 w:t 外还有别的内容子元素 → 不拆
  const rest = inner.replace(/<w:rPr>[\s\S]*?<\/w:rPr>/, "").replace(/<w:t(?:\s[^>]*)?>[\s\S]*?<\/w:t>/, "");
  return rest.trim() === "";
}
function runRPr(runXml) {
  return (/<w:rPr>[\s\S]*?<\/w:rPr>/.exec(runXml) ?? [""])[0];
}
function buildRun(rPr, text) {
  return `<w:r>${rPr}<w:t xml:space="preserve">${encodeXmlText(text)}</w:t></w:r>`;
}

// 把段落 inner 的字符区间 [from,to)（按 listParagraphs 的 text 口径）切成三段。
// 返回 {before, mid, after}；三段拼接的纯文本 === 原 text（结构不变式，上层自测可断言）。
export function splitParagraphSpan(inner, from, to) {
  if (!(from >= 0 && to >= from)) throw new Error(`非法区间 [${from},${to})`);
  const runs = [];
  const re = /<w:r\b[\s\S]*?<\/w:r>/g;
  let m;
  while ((m = re.exec(inner)) !== null) runs.push({ xml: m[0], start: m.index, end: m.index + m[0].length });
  let pos = 0; // 已走过的不含本函数产物的字符游标（按 text 口径）
  const out = { before: "", mid: "", after: "" };
  const routeGap = (gapXml) => {
    if (pos <= from) out.before += gapXml;       // 无文本间隙按当前游标归桶（pPr 恒在段首 → before）
    else if (pos < to) out.mid += gapXml;
    else out.after += gapXml;
  };
  let cursor = 0;
  const eat = (gapXml) => { routeGap(gapXml); };
  for (const r of runs) {
    eat(inner.slice(cursor, r.start));
    const rawParts = runTextParts(r.xml);
    const text = rawParts.map(decodeXmlText).join("");
    if (text === "") { routeGap(r.xml); cursor = r.end; continue; } // 无文本 run（如纯图片）按间隙处理
    const rStart = pos, rEnd = pos + text.length;
    if (rEnd <= from) out.before += r.xml;
    else if (rStart >= to) out.after += r.xml;
    else {
      const lead = Math.max(0, from - rStart);
      const tail = Math.max(0, rEnd - to);
      if (isSplittable(r.xml, rawParts.length)) {
        const rPr = runRPr(r.xml);
        if (lead > 0) out.before += buildRun(rPr, text.slice(0, lead));
        out.mid += buildRun(rPr, text.slice(lead, text.length - tail));
        if (tail > 0) out.after += buildRun(rPr, text.slice(text.length - tail));
      } else {
        out.mid += r.xml; // 不可拆 → 整 run 吸附进 mid（区间边界外扩到 run 边界）
      }
    }
    pos = rEnd;
    cursor = r.end;
  }
  eat(inner.slice(cursor));
  return out;
}

// mid 内全部 w:t 改名 w:delText（供 A5 修订删除块复用原 run）。
export function runsToDelText(midXml) {
  return midXml
    .replace(/<w:t(\s[^>]*)?>/g, "<w:delText$1>")
    .replace(/<\/w:t>/g, "</w:delText>");
}
