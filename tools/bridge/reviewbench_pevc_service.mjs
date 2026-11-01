// 审阅台·pe-vc 转写件（吸收件转写规格 A1/A2/A3/A4/A10，竞品情报/2026-10-29-规格波/吸收件转写规格.md）。
// 源料=hub skills pe-vc-transaction-docs-review（SKILL.md frontmatter 声明 Apache-2.0，本会话实读；
// 目录内无 LICENSE 正文，正文级核验=UNKNOWN，本件按规格 §四默认路径=等量自写，零源码/文案复制）。
// 落位：A1→RE-12 增量审查（多轮红线稿跟踪）；A2→RE-33 入口前置（文件族地图+候选冲突矩阵）；
// A3→RE-10 交付通道（Word 原生批注）；A4→RE-12 质量门（完成门禁三态）；A10→RE-12 报告规范（市场比例披露纪律）。
// 吸收面=功能账 #20/#21 在案路径同族（tools/bridge 零依赖确定性小件）；文案全部自写（表达隔离）。
// 全部输入为合成材料口径；涉法律规则/计算处一律过渡档九计算器，标「JC 完整档=修订中挂起」（决策台账:69）。
import { createHash } from "node:crypto";
import { parseZip } from "./skills_service.mjs";
import { buildZip } from "./draft_docx.mjs";
import { extractDocxText } from "./redline_service.mjs";
import { listParagraphs, splitParagraphSpan, encodeXmlText } from "./docx_span_util.mjs";

// ═══════════════════════════════════════════════════════════════════
// A1 多轮红线稿跟踪闭环（规格 §四 A1）：台账条目跨轮稳定 issue_id＋状态枚举
// （open/accepted/partial/rejected/reopened/new）；轮次对比器输入=当前稿＋上一版＋上轮台账；
// 缺上一版基线时只做当前文本风险审阅、禁止推断谈判状态；对方明确保留争议文本判 rejected 而非 open。
// ═══════════════════════════════════════════════════════════════════
const NEGOTIATION_STATES = ["accepted", "partial", "rejected", "reopened", "new"];

function normText(s) {
  return String(s ?? "").replace(/\s+/g, "");
}

function nextIssueId(usedIds) {
  let max = 0;
  for (const id of usedIds) {
    const m = /^R-(\d+)$/.exec(String(id ?? ""));
    if (m) max = Math.max(max, Number(m[1]));
  }
  return `R-${String(max + 1).padStart(3, "0")}`;
}

// trackReviewRound({ currentDocx, previousDocx, priorLedger, currentFindings })
// priorLedger 条目：{issue_id, problem_text, status, note?}；currentFindings：[{problem_text, note?}]（本轮审阅新发现的候选争议文本）。
// 返回 {entries, limitations, counts}；缺 previousDocx → limitations 含「无法判断接受状态」披露且零谈判状态断言
// （既有条目状态原样保留，新发现仅记 open=当前文本风险，不属谈判状态断言）。
export function trackReviewRound({ currentDocx, previousDocx, priorLedger = [], currentFindings = [] }) {
  const currentText = extractDocxText(currentDocx);
  const curNorm = normText(currentText);
  const hasBaseline = previousDocx != null;
  const prevNorm = hasBaseline ? normText(extractDocxText(previousDocx)) : null;

  const entries = [];
  const limitations = [];
  for (const e of priorLedger) {
    entries.push({ ...e });
  }
  if (!hasBaseline) {
    limitations.push("无法判断接受状态：未提供上一版基线，本轮仅做当前文本风险审阅，不推断对方对各项意见的谈判态度。");
  }
  for (const e of entries) {
    if (!hasBaseline) continue; // 零状态断言：不做任何 accepted/rejected/… 判定
    if (!normText(e.problem_text)) continue;
    const kept = curNorm.includes(normText(e.problem_text));
    const was = e.status;
    e.status = kept ? "rejected" : "accepted"; // 对方返还稿中明确保留争议文本 → rejected（而非留 open）
    e.last_round_note = kept
      ? "对方在本轮返还稿中保留了该争议文本，判 rejected。"
      : "该问题文本在本轮稿中已消失，判 accepted。";
    e.status_history = [...(e.status_history ?? []), { from: was, to: e.status }];
  }
  for (const f of currentFindings ?? []) {
    const key = normText(f.problem_text);
    if (!key) continue;
    const hit = entries.find((e) => normText(e.problem_text) === key);
    if (hit) {
      hit.seen_again = true;
      continue;
    }
    entries.push({
      issue_id: nextIssueId(entries.map((e) => e.issue_id)),
      problem_text: f.problem_text,
      note: f.note ?? "",
      status: hasBaseline ? "new" : "open", // 无基线时不给 new（新现判定需上一版对照）
      ...(hasBaseline ? { last_round_note: prevNorm && !prevNorm.includes(key) ? "本轮新现（上一版中无该文本）。" : "本轮新登记（上一版已有该文本但上轮台账未列）。" } : {}),
    });
  }
  const counts = {};
  for (const e of entries) counts[e.status] = (counts[e.status] ?? 0) + 1;
  return { entries, limitations, counts };
}

// ═══════════════════════════════════════════════════════════════════
// A2 整套文件地图＋轻量候选冲突矩阵（规格 §四 A2）：文件名 token 分类只作线索、
// 正文证据定稿；跨文件同字段抽值对比产候选冲突清单（回正文人工确认），字段划分参照
// 主体/金额/违约/管辖/期限五字段并加股比。RE-33 重流程的入口轻量件。
// ═══════════════════════════════════════════════════════════════════
const FILE_ROLES = {
  main_agreement: {
    bodyKeywords: ["增资协议", "投资协议", "主协议", "交割先决条件", "鉴于："],
    nameTokens: ["主协议", "增资协议", "投资协议", "SPA"],
  },
  charter: {
    bodyKeywords: ["公司章程", "股东会", "董事会", "表决程序", "章程修订"],
    nameTokens: ["章程"],
  },
  supplemental: {
    bodyKeywords: ["补充协议", "本协议为", "原协议的补充"],
    nameTokens: ["补充协议", "补充"],
  },
  term_sheet: {
    bodyKeywords: ["条款清单", "Term Sheet", "优先清算权"],
    nameTokens: ["条款清单", "TS"],
  },
  closing_checklist: {
    bodyKeywords: ["交割清单", "交割事项", "交割条件"],
    nameTokens: ["交割清单"],
  },
};

export function classifyPackageFile(fileName, text) {
  const scores = {};
  const notes = [];
  for (const [role, def] of Object.entries(FILE_ROLES)) {
    let body = 0;
    for (const kw of def.bodyKeywords) if (text.includes(kw)) body += 1;
    let name = 0;
    for (const tok of def.nameTokens) if (fileName.includes(tok)) name += 1;
    scores[role] = { body, name, total: body * 3 + name };
    if (body) notes.push(`正文命中 ${role} 信号 ×${body}`);
    if (name) notes.push(`文件名命中 ${role} 线索 ×${name}`);
  }
  let best = null, bestScore = 0, tie = false;
  for (const [role, s] of Object.entries(scores)) {
    if (s.total > bestScore) { best = role; bestScore = s.total; tie = false; }
    else if (s.total === bestScore && s.total > 0) tie = true;
  }
  if (!best || tie) return { role: "unclassified", evidence: notes, scores, basis: "正文与文件名证据均不足或并列，留人工定稿" };
  const bodyDriven = scores[best].body > 0;
  return {
    role: best,
    evidence: notes,
    scores,
    basis: bodyDriven ? "正文证据定稿（文件名仅作线索）" : "正文无信号，按文件名线索定稿",
  };
}

// 字段抽值（合成材料口径的正则；真实材料未断言）：返回 [{field, raw, normalized, clause, paraIndex, excerpt}]
const FIELD_PATTERNS = [
  { field: "amount", re: /(?:投资总额|投资金额|增资金额|交易对价)[^0-9\n]{0,8}([\d,，.]+)\s*(万元|元|美元|港元)/g, norm: (v, u) => `${v.replace(/[，,]/g, "")}${u}` },
  { field: "equity_ratio", re: /(?:增资后持股比例|持股比例|股权比例)[^0-9\n]{0,8}([\d.]+)\s*%/g, norm: (v) => `${Number(v)}%` },
  { field: "governing", re: /(?:管辖|争议解决|争议)[^。；\n]{0,30}?(?:由|提交)([^，。；\n]{2,24}?(?:人民法院|仲裁委员会))/g, norm: (v) => v.replace(/\s+/g, "") },
  { field: "term", re: /(?:合作期限|锁定期|有效期)[^0-9\n]{0,8}(\d+)\s*(年|个月|月|日)/g, norm: (v, u) => `${v}${u}` },
  { field: "breach", re: /(?:应当|须)承担(?:相应的)?违约责任/g, norm: () => "有违约责任条款" },
];

function clauseLocator(text, index) {
  const before = text.slice(0, index);
  const clauses = [...before.matchAll(/第[一二三四五六七八九十百\d]+条/g)];
  const clause = clauses.length ? clauses[clauses.length - 1][0] : null;
  const paraIndex = before.split(/\n/).length; // 1 基段落序
  return { clause, paraIndex };
}

export function extractPackageFields(text) {
  const out = [];
  for (const { field, re, norm } of FIELD_PATTERNS) {
    let m;
    re.lastIndex = 0;
    while ((m = re.exec(text)) !== null) {
      const groups = m.slice(1);
      const raw = m[0];
      const loc = clauseLocator(text, m.index);
      out.push({
        field,
        raw,
        normalized: norm(...groups),
        clause: loc.clause,
        paraIndex: loc.paraIndex,
        excerpt: raw.length > 48 ? raw.slice(0, 48) + "…" : raw,
      });
    }
  }
  return out;
}

// mapDealPackage(files)：files=[{name, text}]。跨文件同字段对比：≥2 份文件给出该字段且
// 归一值互不相等 → 候选冲突（带文件+条款定位）；全部相等 → 入 consistent（零误报=不进冲突清单）。
export function mapDealPackage(files) {
  const fileMap = files.map((f) => ({
    name: f.name,
    ...classifyPackageFile(f.name, f.text ?? ""),
    fields: extractPackageFields(f.text ?? ""),
  }));
  const byField = new Map(); // field -> [{file, item}]
  for (const fm of fileMap) {
    for (const item of fm.fields) {
      if (!byField.has(item.field)) byField.set(item.field, []);
      byField.get(item.field).push({ file: fm.name, role: fm.role, item });
    }
  }
  const conflicts = [];
  const consistent = [];
  for (const [field, hits] of byField) {
    const distinct = [...new Set(hits.map((h) => h.item.normalized))];
    if (distinct.length >= 2) {
      conflicts.push({
        field,
        kind: "inconsistent",
        values: hits.map((h) => ({ file: h.file, role: h.role, normalized: h.item.normalized, clause: h.item.clause, paraIndex: h.item.paraIndex, excerpt: h.item.excerpt })),
      });
    } else {
      consistent.push({ field, files: hits.map((h) => h.file), normalized: hits[0]?.item.normalized });
    }
  }
  return {
    fileMap,
    conflicts,
    consistent,
    notice: "以上冲突为候选：字段抽取是确定性的，条款归属与业务取舍须回正文逐条人工确认后方可定性。",
  };
}

// ═══════════════════════════════════════════════════════════════════
// A3 Word 原生批注通道（规格 §四 A3）：批注计划→OOXML comments 注入。
// 锚点=唯一原文片段（找不到/不唯一都 fail-fast 拒绝）；输出另存副本（本函数返回新字节，
// 从不回写源文件）；宿主 docx 层不可用时降级=交付批注计划文本并明示未生成原生批注。
// ═══════════════════════════════════════════════════════════════════
const DOC_XML = "word/document.xml";

function getEntry(entries, name) {
  return entries.get(name) ?? entries.get("/" + name);
}

export function injectDocxComments(sourceBytes, commentPlan, opts = {}) {
  const author = opts.author ?? "Juscite 审阅台";
  const date = opts.date ?? new Date().toISOString().replace(/\.\d+Z$/, "Z");
  if (!Array.isArray(commentPlan) || commentPlan.length === 0) {
    throw Object.assign(new Error("批注计划为空：无锚点可注入"), { code: "PLAN_EMPTY" });
  }
  let entries;
  try {
    entries = parseZip(sourceBytes);
  } catch (e) {
    throw Object.assign(new Error(`源 docx 解析失败：${e?.message ?? e}`), { code: "DOCX_INVALID" });
  }
  const docEntry = getEntry(entries, DOC_XML);
  if (!docEntry) throw Object.assign(new Error("源 docx 缺少 word/document.xml，不是可批注的 Word 文档"), { code: "DOCX_INVALID" });
  const xml = docEntry.toString("utf8");
  const paras = listParagraphs(xml);

  // 锚点唯一性：找不到=拒绝；出现两次=拒绝（fail-fast，不落任何批注）。
  const anchors = [];
  for (const p of commentPlan) {
    const key = normText(p.anchor_text);
    if (!key) throw Object.assign(new Error("批注计划含空锚点"), { code: "ANCHOR_EMPTY" });
    const hits = paras.filter((pa) => normText(pa.text).includes(key));
    if (hits.length === 0) {
      throw Object.assign(new Error(`锚点在正文中找不到：${String(p.anchor_text).slice(0, 24)}…`), { code: "ANCHOR_NOT_FOUND" });
    }
    if (hits.length > 1) {
      throw Object.assign(new Error(`锚点在正文中出现 ${hits.length} 次、不唯一，拒绝落批注：${String(p.anchor_text).slice(0, 24)}…`), { code: "ANCHOR_NOT_UNIQUE" });
    }
    const para = hits[0];
    const plain = normText(para.text);
    const targetStart = plain.indexOf(key);
    let acc = 0, from = -1; // normText 去掉的空白在原文中的游标还原
    for (let i = 0; i < para.text.length; i++) {
      if (/\s/.test(para.text[i])) continue;
      if (acc === targetStart) { from = i; break; }
      acc++;
    }
    if (from < 0) throw Object.assign(new Error(`锚点定位失败：${String(p.anchor_text).slice(0, 24)}…`), { code: "ANCHOR_NOT_FOUND" });
    // 锚点区间右端：从 from 起消耗 key.length 个非空白字符（锚点内含空白也可命中）
    let to = from, consumed = 0;
    while (to < para.text.length && consumed < key.length) {
      if (!/\s/.test(para.text[to])) consumed++;
      to++;
    }
    anchors.push({ para, from, to, comment: String(p.comment ?? ""), anchorText: p.anchor_text });
  }
  anchors.sort((a, b) => a.para.start - b.para.start || a.from - b.from);

  // 重写顺序：段落降序（后段先改，前段偏移不受影响）；同段内多锚点按 from 降序逐个套。
  // 注释 id 按文档序（升序）分配，与 comments.xml 一致。
  const byPara = new Map();
  for (let i = 0; i < anchors.length; i++) {
    const a = anchors[i];
    a.id = i;
    if (!byPara.has(a.para.start)) byPara.set(a.para.start, { para: a.para, items: [] });
    byPara.get(a.para.start).items.push(a);
  }
  let out = xml;
  const commentDefs = new Array(anchors.length);
  for (const paraStart of [...byPara.keys()].sort((x, y) => y - x)) {
    const group = byPara.get(paraStart);
    let inner = group.para.inner;
    for (const a of group.items.sort((x, y) => y.from - x.from)) {
      const from = Math.max(0, Math.min(a.from, group.para.text.length));
      const to = Math.max(from, Math.min(a.to, group.para.text.length));
      const parts = splitParagraphSpan(inner, from, to);
      inner =
        parts.before +
        `<w:commentRangeStart w:id="${a.id}"/>` +
        parts.mid +
        `<w:commentRangeEnd w:id="${a.id}"/><w:r><w:commentReference w:id="${a.id}"/></w:r>` +
        parts.after;
    }
    out = out.slice(0, group.para.start) + inner + out.slice(group.para.end);
  }
  for (const a of anchors) {
    commentDefs[a.id] = `<w:comment w:id="${a.id}" w:author="${encodeXmlText(author)}" w:date="${date}"><w:p><w:r><w:t xml:space="preserve">${encodeXmlText(a.comment)}</w:t></w:r></w:p></w:comment>`;
  }

  const commentsXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">' +
    commentDefs.join("") + "</w:comments>";

  // [Content_Types].xml 注册 comments 部件
  let ct = (getEntry(entries, "[Content_Types].xml") ?? Buffer.from(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    `<Override PartName="/${DOC_XML}" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>`,
    "utf8",
  )).toString("utf8");
  if (!ct.includes("/word/comments.xml")) {
    ct = ct.replace(/<\/Types>$/, '<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/></Types>');
  }

  // word/_rels/document.xml.rels 挂 comments 关系
  const relsName = "word/_rels/document.xml.rels";
  let rels = getEntry(entries, relsName)?.toString("utf8");
  if (rels === undefined) {
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>';
  }
  let relId = 1;
  for (const m of rels.matchAll(/Id="rId(\d+)"/g)) relId = Math.max(relId, Number(m[1]) + 1);
  if (!rels.includes("Target=\"comments.xml\"")) {
    rels = rels.replace(/<\/Relationships>$/, `<Relationship Id="rId${relId}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/></Relationships>`);
  }

  const newEntries = [];
  for (const [name, data] of entries) {
    if (name === DOC_XML || name === "/" + DOC_XML) continue;
    if (name === "[Content_Types].xml") { newEntries.push({ name, data: Buffer.from(ct, "utf8") }); continue; }
    if (name === relsName) { newEntries.push({ name, data: Buffer.from(rels, "utf8") }); continue; }
    newEntries.push({ name, data }); // 其余 entry 原字节保留
  }
  newEntries.push({ name: DOC_XML, data: Buffer.from(out, "utf8") });
  newEntries.push({ name: "word/comments.xml", data: Buffer.from(commentsXml, "utf8") });
  return buildZip(newEntries);
}

export const DOCX_COMMENT_ERROR_CODES = ["DOCX_INVALID", "ANCHOR_NOT_FOUND", "ANCHOR_NOT_UNIQUE", "ANCHOR_EMPTY", "PLAN_EMPTY"];

// 降级交付面：docx 层不可用（解析失败/缺部件）→ 输出批注计划文本＋明示未生成原生批注；
// 计划本身的问题（锚点不唯一/找不到）仍 fail-fast 上抛（校验错误不是降级理由）。
export function deliverCommentAnnotations(sourceBytes, commentPlan, opts = {}) {
  try {
    const bytes = injectDocxComments(sourceBytes, commentPlan, opts);
    return { mode: "native", bytes, notice: null };
  } catch (e) {
    if (e?.code !== "DOCX_INVALID") throw e;
    const lines = commentPlan.map((p, i) => `${i + 1}. 锚点：${p.anchor_text}\n   意见：${p.comment}`);
    return {
      mode: "plan-text",
      bytes: null,
      notice: `未生成原生批注：${e?.message ?? e}（源文件不是可解析的 Word 文档）。以下为批注计划文本，请人工对照执行；本说明为明示降级，非静默省略。`,
      planText: lines.join("\n"),
    };
  }
}

// ═══════════════════════════════════════════════════════════════════
// A4 审阅完成门禁三态（规格 §四 A4）：机器检查（源指纹一致/阶段终态齐备/产物存在）＋
// 判断门四项（事项与权威/实质覆盖/高风险抽查/交付与保密）→ passed / passed_with_limitations / blocked。
// limitations 强制首页披露；blocked 禁任何完成表述。只闸机器可查项，法律内容正确性不在此闸。
// ═══════════════════════════════════════════════════════════════════
export const REVIEW_JUDGMENT_GATES = ["事项与权威", "实质覆盖", "高风险抽查", "交付与保密"];
const STAGE_FINAL_STATES = ["completed", "completed_with_limitations", "not_applicable"];

export function gateReviewCompletion(review) {
  const machine = [];
  for (const s of review.sources ?? []) {
    const actual = s.actualSha256 ?? (s.actualBytes ? createHash("sha256").update(s.actualBytes).digest("hex") : null);
    const ok = actual != null && actual === String(s.expectedSha256 ?? "").toLowerCase();
    machine.push({ check: `源指纹一致：${s.path}`, ok, detail: ok ? "" : `登记指纹与当前内容不一致（${actual ? `现=${actual.slice(0, 12)}…` : "当前内容缺失"}）` });
  }
  for (const st of review.stages ?? []) {
    const ok = STAGE_FINAL_STATES.includes(st.finalState);
    machine.push({ check: `阶段终态齐备：${st.name}`, ok, detail: ok ? st.finalState : `终态缺失或非法（${st.finalState ?? "无"}）` });
  }
  for (const a of review.artifacts ?? []) {
    machine.push({ check: `产物存在：${a.path}`, ok: !!a.exists, detail: a.exists ? "" : "交付产物缺失" });
  }
  const machineFail = machine.filter((m) => !m.ok);

  const judgments = [];
  for (const gate of REVIEW_JUDGMENT_GATES) {
    const j = (review.judgments ?? []).find((x) => x.gate === gate);
    if (!j) { judgments.push({ gate, result: "fail", note: "判断门未登记" }); continue; }
    judgments.push({ gate, result: j.result, note: j.note ?? "" });
  }
  const judgmentFail = judgments.filter((j) => j.result === "fail");
  const stageLimited = (review.stages ?? []).filter((st) => st.finalState === "completed_with_limitations");

  if (machineFail.length || judgmentFail.length) {
    return {
      status: "blocked",
      machine, judgments,
      failures: [...machineFail, ...judgmentFail],
      disclosure: null,
      statement: "本事项未通过完成门禁（blocked）：存在机器检查失败或判断门不通过项，禁止作任何完成表述；未决项处理完毕后重新过闸。",
    };
  }
  const limitationItems = [];
  for (const st of stageLimited) limitationItems.push(`阶段「${st.name}」以带限制终态完成`);
  for (const j of judgments.filter((x) => x.result === "limitation")) limitationItems.push(`判断门「${j.gate}」带限制：${j.note || "（未注记限制内容）"}`);
  if (limitationItems.length) {
    return {
      status: "passed_with_limitations",
      machine, judgments,
      failures: [],
      disclosure: `【交付首页披露·必载】本次审阅以下限制须在报告首页向委托人披露：\n- ${limitationItems.join("\n- ")}`,
      statement: "审阅以带限制通过（passed_with_limitations）：首页披露段为交付必载件，缺失即不得交付。",
    };
  }
  return {
    status: "passed",
    machine, judgments,
    failures: [],
    disclosure: null,
    statement: "审阅完成门禁全绿（passed）：机器可查项与四项判断门全部通过。法律内容正确性不在本闸范围，仍走判断门与律师复核。",
  };
}

// ═══════════════════════════════════════════════════════════════════
// A10 市场比例披露纪律（规格 §四 A10，机制可学、数据不采——B3：数据本体零采用，须自建可溯源）：
// 对外整数百分比＋「约/不足 1%」限定词、精确值仅内部、市场数据与法律结论分区、不披露统计来源名。
// ═══════════════════════════════════════════════════════════════════
function publicPhrase(precise) {
  const n = Number(precise);
  if (!Number.isFinite(n)) throw new Error("市场统计输入含非数值，拒绝渲染");
  if (n >= 0 && n < 0.5) return "不足 1%";
  return `约 ${Math.round(n)}%`;
}

// renderMarketDisclosure({stats, legalConclusion, requestPrecise})
// stats=[{topic, precisePercent, samplePeriod, boundary, sourceName?}]；legalConclusion=法律结论文本（原样入 legalBlock，绝不混入市场数据）。
export function renderMarketDisclosure({ stats = [], legalConclusion = "", requestPrecise = false }) {
  const lines = [];
  for (const s of stats) {
    if (requestPrecise) {
      lines.push(`- ${s.topic}：${Number(s.precisePercent)}%（样本期间：${s.samplePeriod ?? "未登记"}；边界：${s.boundary ?? "未登记"}；内部精确口径，仅应本单显式索要提供）`);
    } else {
      lines.push(`- ${s.topic}：${publicPhrase(s.precisePercent)}（市场谈判背景参考，不构成法律要求或法律意见）`);
    }
  }
  const marketBlock = lines.length ? `## 市场数据（谈判背景参考区）\n${lines.join("\n")}` : "";
  const legalBlock = String(legalConclusion ?? ""); // 分区呈现：法律结论区零市场数据混入（本函数不做任何注入）
  const rendered = [marketBlock, legalBlock ? `## 法律结论（法律区）\n${legalBlock}` : ""].filter(Boolean).join("\n\n");
  // 不向用户披露统计来源名：即便输入带 sourceName，输出也必须不含。
  for (const s of stats) {
    if (s.sourceName && rendered.includes(s.sourceName)) {
      throw new Error(`披露纪律违反：输出不得包含统计来源名（${s.sourceName}）`);
    }
  }
  return { marketBlock, legalBlock, rendered, requestPrecise: !!requestPrecise };
}
