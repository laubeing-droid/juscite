// 审阅台·contract-review-3 转写件（吸收件转写规格 A5/A6/A7/A8/A9，竞品情报/2026-10-29-规格波/吸收件转写规格.md）。
// 源料=hub skills contract-review-3（SKILL.md frontmatter 声明 MIT-0 v3.4.1，本会话实读；目录内无 LICENSE
// 正文，正文级核验=UNKNOWN，本件按规格 §四默认路径=等量自写，零源码/文案复制）。
// 落位：A5→RE-10 修订通道（台账→render plan→确定性落痕）；A6→RE-18 补断言（反馈闭环边角+反哺规则）；
// A7→RE-12 台账（审查台账形状/状态机/损坏重建）；A8→RE-10 输出规范（中文 docx 字体双通道）；
// A9→RE-12 分型配置（分型规则包「形状位」，内容零采用）。
// 红线遵守：B1 第三方规则/数据候选零采用（法条锚点/比例/必备条款清单/关键词词表内容全不进，只取文件形状）；
// 涉法律规则/计算处一律过渡档九计算器，标「JC 完整档=修订中挂起」（juscite/docs/决策台账.md:69）。
// 吸收面=功能账 #20/#21 在案路径同族（tools/bridge 零依赖确定性小件）；文案全部自写（表达隔离）；输入全为合成材料。
import { parseZip } from "./skills_service.mjs";
import { buildZip } from "./draft_docx.mjs";
import { listParagraphs, splitParagraphSpan, runsToDelText, encodeXmlText, decodeXmlText } from "./docx_span_util.mjs";

const DOC_XML = "word/document.xml";
function normText(s) {
  return String(s ?? "").replace(/\s+/g, "");
}
function getEntry(entries, name) {
  return entries.get(name) ?? entries.get("/" + name);
}

// ═══════════════════════════════════════════════════════════════════
// A5 账本→render plan→确定性落痕（规格 §四 A5）：三段式。
// ① buildRevisionRenderPlan(ledger)：只收 status=confirmed 且非 needs_negotiation 的条目
//   （confirmed+needs_negotiation 走批注意见书通道、status≠confirmed 一律不落痕——落痕分流三通道）；
// ② plan 条目={issue_id, action:"replace", target_text, replacement_text, needs_negotiation:false}；
// ③ applyRevisionRenderPlan：段内精确替换为 <w:del><w:delText>旧</w:delText></w:del><w:ins><w:t>新</w:t></w:ins>
//   （Word 兼容：w:id 唯一+author/date 必带），plan+执行日志随返回值归档可复放；目标文本不在任何段落→报错不静默；
//   输出另存语义（返回新字节，从不回写源）。
// ═══════════════════════════════════════════════════════════════════
export function buildRevisionRenderPlan(ledger) {
  const items = (Array.isArray(ledger) ? ledger : ledger?.entries ?? [])
    .filter((e) => e.status === "confirmed" && !e.needs_negotiation)
    .map((e) => ({
      issue_id: e.id ?? e.issue_id,
      action: "replace",
      target_text: String(e.target_text ?? ""),
      replacement_text: String(e.replacement_text ?? ""),
      needs_negotiation: false,
    }))
    .filter((it) => it.target_text && it.replacement_text);
  return { version: 1, generated_by: "reviewbench_cr3 render plan", items };
}

export function applyRevisionRenderPlan(sourceBytes, plan, opts = {}) {
  const author = opts.author ?? "Juscite 审阅台";
  const date = opts.date ?? new Date().toISOString().replace(/\.\d+Z$/, "Z");
  const items = (plan?.items ?? plan ?? []).filter((it) => it?.target_text);
  if (!items.length) throw Object.assign(new Error("render plan 为空：没有可落痕条目"), { code: "PLAN_EMPTY" });
  let entries;
  try {
    entries = parseZip(sourceBytes);
  } catch (e) {
    throw Object.assign(new Error(`源 docx 解析失败：${e?.message ?? e}`), { code: "DOCX_INVALID" });
  }
  const docEntry = getEntry(entries, DOC_XML);
  if (!docEntry) throw Object.assign(new Error("源 docx 缺少 word/document.xml"), { code: "DOCX_INVALID" });
  const xml = docEntry.toString("utf8");
  const paras = listParagraphs(xml);

  // 定位：每条 plan 找第一个含目标文本的段落（确定性首中）；找不到=报错不静默。
  const targets = items.map((it) => {
    const key = normText(it.target_text);
    const para = paras.find((p) => normText(p.text).includes(key));
    if (!para) {
      throw Object.assign(new Error(`落痕目标文本不在任何段落中（${it.issue_id ?? "未编号"}）：${it.target_text.slice(0, 24)}…`), { code: "TARGET_NOT_FOUND", issue_id: it.issue_id });
    }
    return { it, para };
  });
  // 应用顺序：段落降序、段内按出现序升序（一次确定性应用，全部基于原文坐标）。
  targets.sort((a, b) => b.para.start - a.para.start);
  let out = xml;
  let nextMarkId = opts.firstMarkId ?? 70001;
  const applyLog = [];
  for (const { it, para } of targets) {
    const plain = normText(para.text);
    const key = normText(it.target_text);
    const targetStart = plain.indexOf(key);
    let acc = 0, from = -1;
    for (let i = 0; i < para.text.length; i++) {
      if (/\s/.test(para.text[i])) continue;
      if (acc === targetStart) { from = i; break; }
      acc++;
    }
    if (from < 0) throw Object.assign(new Error(`落痕目标定位失败：${it.target_text.slice(0, 24)}…`), { code: "TARGET_NOT_FOUND", issue_id: it.issue_id });
    let to = from, consumed = 0;
    while (to < para.text.length && consumed < key.length) {
      if (!/\s/.test(para.text[to])) consumed++;
      to++;
    }
    const parts = splitParagraphSpan(para.inner, from, to);
    const delBlock = `<w:del w:id="${nextMarkId++}" w:author="${encodeXmlText(author)}" w:date="${date}">${runsToDelText(parts.mid)}</w:del>`;
    const insBlock = `<w:ins w:id="${nextMarkId++}" w:author="${encodeXmlText(author)}" w:date="${date}"><w:r><w:t xml:space="preserve">${encodeXmlText(it.replacement_text)}</w:t></w:r></w:ins>`;
    const marked = parts.before + delBlock + insBlock + parts.after;
    out = out.slice(0, para.start) + marked + out.slice(para.end);
    applyLog.push({ issue_id: it.issue_id ?? null, action: "replace", result: "applied", para_index: paras.indexOf(para), target_text: it.target_text, replacement_text: it.replacement_text });
  }
  const newEntries = [];
  for (const [name, data] of entries) {
    if (name === DOC_XML || name === "/" + DOC_XML) continue;
    newEntries.push({ name, data }); // 其余 entry 原字节保留
  }
  newEntries.push({ name: DOC_XML, data: Buffer.from(out, "utf8") });
  const bytes = buildZip(newEntries);
  const planArchive = JSON.stringify({ plan: { version: 1, items }, applyLog, mark_id_range: [opts.firstMarkId ?? 70001, nextMarkId - 1], author, date }, null, 2);
  return { bytes, planArchive, applyLog };
}

// 复放：归档 JSON 里带 plan，重放=同 plan 对同源再应用（确定性 → 字节一致）。
export function replayRevisionArchive(sourceBytes, archiveJson, opts = {}) {
  const archive = JSON.parse(archiveJson);
  return applyRevisionRenderPlan(sourceBytes, archive.plan, { ...opts, firstMarkId: archive.mark_id_range?.[0], author: archive.author, date: archive.date });
}

// ═══════════════════════════════════════════════════════════════════
// A6 反馈闭环边角＋反哺规则（规格 §四 A6，RE-18 补断言；RE-18 主体已 done/pass 不动）：
// ① 定稿 Track Changes 与台账逐条比对判 accepted/partial/rejected；② 跨 run 拆分按拼接全文匹配
// （读 XML 层 w:ins/w:del，不吃 .text 静默亏）；③ 空修订守卫=专用退出码且零统计写入；
// ④ 驳回率≥阈值章节下轮降级+人工复核提示（阈值自定 0.6，不采源料数值）。
// ═══════════════════════════════════════════════════════════════════
export const EMPTY_REVISION_EXIT_CODE = 3;

// XML 层读取修订态：finalText=接受全部修订后的文本（w:ins 内 w:t 算、w:del 内不算）；
// originalText=接受前的文本（w:del 的 delText 算回来）。
export function extractDocxRevisionTexts(docxBytes) {
  let entries;
  try {
    entries = parseZip(docxBytes);
  } catch (e) {
    throw Object.assign(new Error(`docx 解析失败：${e?.message ?? e}`), { code: "DOCX_INVALID" });
  }
  const docEntry = getEntry(entries, DOC_XML);
  if (!docEntry) throw Object.assign(new Error("docx 缺少 word/document.xml"), { code: "DOCX_INVALID" });
  const xml = docEntry.toString("utf8");
  const paras = [];
  for (const seg of xml.split("</w:p>")) {
    let finalText = "", originalText = "";
    // 删 w:del 块：final 不计其 w:t/delText；original 计 delText
    const delBlocks = [...seg.matchAll(/<w:del\b[\s\S]*?<\/w:del>/g)].map((m) => m[0]);
    const withoutDel = seg.replace(/<w:del\b[\s\S]*?<\/w:del>/g, "");
    for (const m of withoutDel.matchAll(/<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/g)) finalText += decodeXmlText(m[1]);
    originalText = finalText;
    for (const blk of delBlocks) {
      for (const m of blk.matchAll(/<w:delText(?:\s[^>]*)?>([\s\S]*?)<\/w:delText>/g)) originalText += decodeXmlText(m[1]);
    }
    if (finalText !== "" || originalText !== "") paras.push({ finalText, originalText });
  }
  const finalAll = paras.map((p) => p.finalText).join("\n");
  const originalAll = paras.map((p) => p.originalText).join("\n");
  return { finalText: finalAll, originalText: originalAll, hasRevisionMarks: /<w:ins\b/.test(xml) || /<w:del\b/.test(xml) };
}

// judgeFeedbackRound({finalDocx, ledger, statsCollector})
// ledger 条目（A5 同形）：{id, chapter?, target_text, replacement_text}
// 返回 {guard, exitCode, judgments, chapterStats}；空修订 → guard="empty-revision" + 专用退出码 + judgments=[] 且 statsCollector 零触碰。
export function judgeFeedbackRound({ finalDocx, ledger = [], statsCollector = null }) {
  const rev = extractDocxRevisionTexts(finalDocx);
  if (!rev.hasRevisionMarks) {
    return {
      guard: "empty-revision",
      exitCode: EMPTY_REVISION_EXIT_CODE,
      judgments: [],
      chapterStats: [],
      notice: `空修订守卫：定稿中没有任何 Track Changes 修订标记（w:ins/w:del 零命中），不产生采纳/驳回判定，本轮统计零写入（专用退出码 ${EMPTY_REVISION_EXIT_CODE}）。`,
    };
  }
  const finalNorm = normText(rev.finalText);
  const judgments = [];
  const byChapter = new Map();
  for (const e of ledger) {
    const target = normText(e.target_text);
    const repl = normText(e.replacement_text);
    let verdict;
    if (repl && finalNorm.includes(repl) && !(target && finalNorm.includes(target))) verdict = "accepted";
    else if (target && finalNorm.includes(target)) verdict = "rejected"; // 原文保留=驳回
    else verdict = "partial"; // 有改动但与台账建议不一致（换写）
    judgments.push({ id: e.id ?? e.issue_id, chapter: e.chapter ?? "", verdict });
    const ch = e.chapter ?? "";
    if (!byChapter.has(ch)) byChapter.set(ch, { chapter: ch, accepted: 0, rejected: 0, partial: 0 });
    byChapter.get(ch)[verdict] += 1;
  }
  const chapterStats = [...byChapter.values()];
  if (statsCollector && typeof statsCollector.push === "function") {
    for (const cs of chapterStats) statsCollector.push(cs); // 仅非空修订轮写统计
  }
  return { guard: null, exitCode: 0, judgments, chapterStats };
}

// 反哺规则：驳回率 ≥ 阈值（默认 0.6，我方自定）的章节 → 下轮降级 + 人工复核提示。
export const FEEDBACK_REJECT_THRESHOLD = 0.6;
export function reweightHighRejectChapters(rounds, { threshold = FEEDBACK_REJECT_THRESHOLD } = {}) {
  const agg = new Map();
  for (const round of rounds ?? []) {
    for (const cs of round.chapterStats ?? round ?? []) {
      const ch = cs.chapter ?? "";
      if (!agg.has(ch)) agg.set(ch, { chapter: ch, accepted: 0, rejected: 0, partial: 0 });
      const a = agg.get(ch);
      a.accepted += cs.accepted ?? 0;
      a.rejected += cs.rejected ?? 0;
      a.partial += cs.partial ?? 0;
    }
  }
  const out = [];
  for (const a of agg.values()) {
    const total = a.accepted + a.rejected + a.partial;
    if (!total) continue;
    const rejectRate = a.rejected / total;
    if (rejectRate >= threshold) {
      out.push({
        ...a,
        rejectRate,
        threshold,
        downgradeNextRound: true,
        hint: `历史常驳回：该章节累计驳回率 ${Math.round(rejectRate * 100)}%（阈值 ${Math.round(threshold * 100)}%），下轮自动降定级并提示人工复核后再出意见。`,
      });
    }
  }
  return out;
}

// ═══════════════════════════════════════════════════════════════════
// A7 审查台账形状（规格 §四 A7）：字段集与状态机——id 单调不复用；status 四态
// （pending/confirmed/resolved/dismissed）流转；dismissed 保留记录可查；conflicts_with/related_issues
// 双向检索；损坏 JSON 重建须明示「台账已重置」。
// ═══════════════════════════════════════════════════════════════════
export const LEDGER_STATUSES = ["pending", "confirmed", "resolved", "dismissed"];
const LEDGER_TRANSITIONS = {
  pending: ["confirmed", "resolved", "dismissed"],
  confirmed: ["resolved", "dismissed"],
  resolved: [],
  dismissed: [], // 终态：记录保留、只进不删
};

export function createReviewLedger(seedEntries = []) {
  const entries = [];
  const usedIds = new Set();
  let seq = 0;
  const nextId = () => {
    seq += 1;
    return `L-${String(seq).padStart(3, "0")}`;
  };
  const find = (id) => entries.find((e) => e.id === id);
  const api = {
    add(e = {}) {
      let id = e.id;
      if (id != null) {
        if (usedIds.has(id)) throw Object.assign(new Error(`台账 id 复用被拒绝：${id}（id 单调不复用）`), { code: "LEDGER_ID_REUSED", id });
      } else {
        id = nextId();
      }
      usedIds.add(id);
      const entry = {
        id,
        chapter: e.chapter ?? "",
        original_text: e.original_text ?? "",
        finding: e.finding ?? "",
        risk_level: e.risk_level ?? "",
        priority: e.priority ?? "",
        status: "pending",
        needs_negotiation: !!e.needs_negotiation,
        revised_wording: e.revised_wording ?? "",
        alternative_wording: e.alternative_wording ?? "",
        conflicts_with: [],
        related_issues: [],
        status_history: [],
        ...(("target_text" in e) ? { target_text: e.target_text } : {}),
        ...(("replacement_text" in e) ? { replacement_text: e.replacement_text } : {}),
      };
      entries.push(entry);
      return entry;
    },
    setStatus(id, status, note = "") {
      const entry = find(id);
      if (!entry) throw Object.assign(new Error(`台账条目不存在：${id}`), { code: "LEDGER_ENTRY_NOT_FOUND", id });
      if (!LEDGER_STATUSES.includes(status)) throw Object.assign(new Error(`非法状态：${status}`), { code: "LEDGER_BAD_STATUS", status });
      if (!LEDGER_TRANSITIONS[entry.status].includes(status)) {
        throw Object.assign(new Error(`非法状态流转：${entry.status} → ${status}（四态流转表）`), { code: "LEDGER_BAD_TRANSITION", from: entry.status, to: status });
      }
      entry.status_history.push({ from: entry.status, to: status, note });
      entry.status = status;
      return entry;
    },
    link(aId, bId, kind = "conflicts") {
      const a = find(aId), b = find(bId);
      if (!a || !b) throw Object.assign(new Error(`link 目标不存在：${aId}/${bId}`), { code: "LEDGER_ENTRY_NOT_FOUND" });
      const field = kind === "related" ? "related_issues" : "conflicts_with";
      if (!a[field].includes(bId)) a[field].push(bId);
      if (!b[field].includes(aId)) b[field].push(aId); // 双向登记
      return true;
    },
    query({ status, relatedTo, kind = "conflicts" } = {}) {
      let out = entries;
      if (status) out = out.filter((e) => e.status === status);
      if (relatedTo) {
        const field = kind === "related" ? "related_issues" : "conflicts_with";
        out = out.filter((e) => e[field]?.includes(relatedTo)); // 双向检索：A↔B 任一方向都能查到
      }
      return out;
    },
    get entries() {
      return entries;
    },
    toJSON() {
      return JSON.stringify({ ledger_version: 1, entries }, null, 2);
    },
  };
  for (const e of seedEntries) api.add(e);
  return api;
}

// 读取/重建：JSON 损坏 → 重建空台账并明示「台账已重置」（降级矩阵行为；原文件留给调用方处置）。
export function loadReviewLedger(jsonText) {
  let parsed = null;
  try {
    parsed = JSON.parse(jsonText);
  } catch {
    return {
      ledger: createReviewLedger(),
      reset: true,
      resetNotice: "台账已重置：原台账文件损坏（JSON 无法解析），已重建空台账；历史条目不自动恢复，原文件保留待人工排查，重置事件须随轮次记录留痕。",
    };
  }
  if (!parsed || !Array.isArray(parsed.entries)) {
    return {
      ledger: createReviewLedger(),
      reset: true,
      resetNotice: "台账已重置：原台账结构无效（缺 entries 数组），已重建空台账；原文件保留待人工排查。",
    };
  }
  return { ledger: createReviewLedger(parsed.entries.map(({ status, status_history, conflicts_with, related_issues, ...rest }) => rest)), reset: false, resetNotice: null };
}

// ═══════════════════════════════════════════════════════════════════
// A8 中文 docx 字体双通道规范（规格 §四 A8）：统一辅助函数、每条 Run 同时设 Latin＋East Asian
// （只设 w:ascii 不设 w:eastAsia 会同字异重）；加粗仅限标题/编号/风险标识，禁段中局部加粗；
// 「Word 打开肉眼验证」升级为 XML 机检。
// ═══════════════════════════════════════════════════════════════════
export const DOCX_BASE_FONT = "宋体";

// 统一 Run 辅助函数：恒设 w:ascii/w:hAnsi/w:eastAsia 三通道同值。
export function dualChannelRun(text, { bold = false, sz = 24, font = DOCX_BASE_FONT } = {}) {
  return `<w:r><w:rPr><w:rFonts w:ascii="${font}" w:hAnsi="${font}" w:eastAsia="${font}"/>${bold ? "<w:b/>" : ""}<w:sz w:val="${sz}"/><w:szCs w:val="${sz}"/></w:rPr><w:t xml:space="preserve">${encodeXmlText(text)}</w:t></w:r>`;
}

// 块形态：title/heading（标题·编号，可加粗）；body（正文，禁局部加粗）；risk（风险标识行：标识 run 加粗+正文 run 不加粗）。
export function renderFontSafeDocx({ title, blocks = [] } = {}) {
  const body = [];
  if (title) body.push(`<w:p><w:pPr><w:jc w:val="center"/></w:pPr>${dualChannelRun(title, { bold: true, sz: 32 })}</w:p>`);
  for (const b of blocks) {
    if (b.type === "heading") body.push(`<w:p>${dualChannelRun(b.text, { bold: true, sz: 28 })}</w:p>`);
    else if (b.type === "risk") body.push(`<w:p>${dualChannelRun(b.label ?? "【风险】", { bold: true })}${dualChannelRun(b.text ?? "")}</w:p>`);
    else body.push(`<w:p>${dualChannelRun(b.text ?? "")}</w:p>`);
  }
  const documentXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' +
    body.join("") + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>';
  const contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    `<Override PartName="/${DOC_XML}" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`;
  const rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    `<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="${DOC_XML}"/></Relationships>`;
  return buildZip([
    { name: "[Content_Types].xml", data: Buffer.from(contentTypes, "utf8") },
    { name: "_rels/.rels", data: Buffer.from(rels, "utf8") },
    { name: DOC_XML, data: Buffer.from(documentXml, "utf8") },
  ]);
}

// XML 机检①：每个 w:r 必带 w:rFonts 且 w:ascii/w:hAnsi/w:eastAsia 三通道齐备、值一致。
export function checkFontDualChannel(xml) {
  const violations = [];
  const runs = [...xml.matchAll(/<w:r(?:\s[^>]*)?>([\s\S]*?)<\/w:r>/g)];
  runs.forEach((m, i) => {
    const fonts = /<w:rFonts\b([^>]*)\/>/.exec(m[1]);
    if (!fonts) { violations.push({ run: i, kind: "missing-rFonts", text: (/<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/.exec(m[1]) ?? [])[1] ?? "" }); return; }
    const attrs = {};
    for (const a of fonts[1].matchAll(/w:(ascii|hAnsi|eastAsia)="([^"]*)"/g)) attrs[a[1]] = a[2];
    const keys = ["ascii", "hAnsi", "eastAsia"];
    const missing = keys.filter((k) => !(k in attrs));
    const values = keys.map((k) => attrs[k]);
    if (missing.length || new Set(values).size !== 1) {
      violations.push({ run: i, kind: missing.length ? "missing-" + missing.join("+") : "mismatch", attrs, text: (/<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/.exec(m[1]) ?? [])[1] ?? "" });
    }
  });
  return { runCount: runs.length, violations };
}

// XML 机检②：加粗 run 的文本清单（供「加粗仅限标题/编号/风险标识」策略断言）。
export function findBoldRunTexts(xml) {
  const out = [];
  for (const m of xml.matchAll(/<w:r(?:\s[^>]*)?>([\s\S]*?)<\/w:r>/g)) {
    if (!/<w:b\/>/.test(m[1])) continue;
    const t = /<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/.exec(m[1]);
    if (t) out.push(decodeXmlText(t[1]));
  }
  return out;
}

// ═══════════════════════════════════════════════════════════════════
// A9 分型规则包「形状位」（规格 §四 A9，仅形状、内容零采用）：
// 每类型一 JSON（章锚点+必备条款{依据,要求,重要性,关键词}+特别规则+罚则位+常见缺失）＋
// 类型识别关键词计分。包内容全部为合成占位——第三方法条锚点/比例/条款清单/词表内容按 B1 全清单不采；
// 涉计算一律过渡档九计算器，标「JC 完整档=修订中挂起」（决策台账:69）。
// ═══════════════════════════════════════════════════════════════════
export const RULE_PACK_SHAPE_NOTE = "形状位：字段结构为自研分型配置形状；legal_basis 等内容字段一律由我方自建法源自写，第三方规则内容零采用；涉计算走过渡档九计算器（JC 完整档=修订中挂起）。";

export function validateRulePack(pack) {
  const errors = [];
  const need = (cond, msg) => { if (!cond) errors.push(msg); };
  need(pack && typeof pack === "object", "包必须是对象");
  if (!pack || typeof pack !== "object") return { ok: false, errors };
  need(typeof pack.type_id === "string" && /^[a-z][a-z0-9-]*$/.test(pack.type_id), "type_id 必须是 kebab-case 字符串");
  need(typeof pack.display_name === "string" && pack.display_name.length > 0, "display_name 必填");
  need(pack.chapter_anchor && typeof pack.chapter_anchor.code === "string" && typeof pack.chapter_anchor.title === "string", "chapter_anchor 需 {code,title}（章锚点位）");
  need(Array.isArray(pack.essential_clauses) && pack.essential_clauses.length > 0, "essential_clauses 必须非空数组");
  const IMPORTANCES = ["core", "important", "optional"];
  for (const [i, c] of (pack.essential_clauses ?? []).entries()) {
    need(c && typeof c.name === "string", `essential_clauses[${i}].name 必填`);
    need(c && typeof c.legal_basis === "string", `essential_clauses[${i}].legal_basis 必填（内容自写，第三方法条锚点不采）`);
    need(c && typeof c.requirement === "string", `essential_clauses[${i}].requirement 必填`);
    need(c && IMPORTANCES.includes(c.importance), `essential_clauses[${i}].importance ∈ ${IMPORTANCES.join("|")}`);
    need(Array.isArray(c?.keywords) && c.keywords.length > 0, `essential_clauses[${i}].keywords 必须非空数组`);
  }
  need(Array.isArray(pack.special_rules), "special_rules 需数组");
  need(Array.isArray(pack.penalty_provisions), "penalty_provisions 需数组（罚则位；比例类内容不采，数值计算走九计算器）");
  for (const [i, p] of (pack.penalty_provisions ?? []).entries()) {
    need(p && typeof p.legal_basis === "string" && typeof p.rule === "string", `penalty_provisions[${i}] 需 {legal_basis,rule}`);
  }
  need(Array.isArray(pack.common_gaps), "common_gaps 需数组");
  for (const [i, g] of (pack.common_gaps ?? []).entries()) {
    need(g && typeof g.issue === "string" && typeof g.risk === "string" && typeof g.suggestion === "string", `common_gaps[${i}] 需 {issue,risk,suggestion}`);
  }
  return { ok: errors.length === 0, errors };
}

// 类型识别=关键词计分（形态参照；词表内容自写）：distinct 关键词命中求和，
// 命中 ≥ threshold 且与次名分差 ≥ margin 才定性，否则 null（不猜）。
export function classifyContractType(text, packs, { threshold = 2, margin = 2 } = {}) {
  const t = String(text ?? "");
  const scored = (packs ?? []).map((p) => {
    const kws = new Set();
    for (const c of p.essential_clauses ?? []) for (const k of c.keywords ?? []) kws.add(k);
    let score = 0;
    for (const k of kws) if (k && t.includes(k)) score += 1;
    return { type_id: p.type_id, display_name: p.display_name, score };
  }).sort((a, b) => b.score - a.score);
  if (!scored.length || scored[0].score < threshold) return { matched: null, reason: "零命中或低于阈值，不定型", scored };
  if (scored.length > 1 && scored[0].score - scored[1].score < margin) {
    return { matched: null, reason: `相似类型分差不足（${scored[0].type_id}=${scored[0].score} vs ${scored[1].type_id}=${scored[1].score}），不定型留人工`, scored };
  }
  return { matched: scored[0].type_id, display_name: scored[0].display_name, scored };
}
