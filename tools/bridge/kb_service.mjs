// 功能 #20 所内知识问答（步骤4·RE 等量）：检索内核纯函数件。
// 唯一依据：juscite/docs/RE规格库/RE-20-所内知识问答.md 实现规格节（§3 数据模型/流程/UI 结构）
// 与行为清单 B51-B58/B62（检索与引用内里）。文案全部自写（表达隔离）；零 embedding/零向量库/
// 零出域（B51，竞品双例背书，红线③一致）。解析一律正则+状态机（工作区铁律），不用模型。
//
// 本文件全部为可独立单测的纯函数（fs/db 依赖由调用方注入），桥面接线在 bridge_host.mjs。

import { createHash } from "node:crypto";

// ── 常量单源（§3 数据模型；B22/D03 反向修正：UI 同步上限与默认一致，不再双常量打架）──
export const KB_SYNC_DEFAULT_LIMIT = 20000;   // 单次同步默认上限
export const KB_SYNC_CONTRACT_LIMIT = 50000;  // 契约顶（超过即拒，不静默截断）
export const KB_FTS_THRESHOLD = 2000;         // ≥2000 文件自动启用 FTS 候选召回（B51）
export const KB_CHUNK_TARGET = 1800;          // 分块目标字符
export const KB_CHUNK_HARD_CAP = 2400;        // 分块硬顶（B58 探针口径：块长≤2400）
export const KB_CHUNK_OVERLAP = 160;          // 分块重叠
export const KB_CONTEXT_BUDGET = 8000;        // 上下文预算字符（B57，装不下整条丢弃）
export const KB_EXCERPT_MAX = 600;            // 单来源摘录帽（B57）
export const KB_MAX_SOURCES = 8;              // 可引用来源清单帽（B32/B33）
export const KB_FILE_BODY_CAP = 4000;         // 文件档正文截帽（B34）
export const KB_RECALL_LIMIT = 240;           // FTS 候选召回帽（B51）
export const KB_RERANK_POOL = 80;             // 重排候选池（B53）
export const KB_RRF_K = 60;                   // 多路融合常数（B54）
export const KB_SCHEMA_VERSION = 1;
export const KB_RETRIEVER_VERSION = "juscite-sparse-v1";

// ── 托管类型面（B25：文本 11+PDF/Word/PPT/Excel/音频 6/图片 5/压缩包 3；其余不进托管根）──
export const KB_TEXT_EXTS = [".txt", ".md", ".markdown", ".csv", ".tsv", ".log", ".json", ".xml", ".html", ".htm", ".srt"];
export const KB_DOC_EXTS = [".docx"]; // v1 可抽正文：文本 11 种 + .docx（复用 #11 extractDocxText；pdf/ppt/xlsx 待 #6 抽取管线落位后接入）
export const KB_BINARY_PREVIEW_EXTS = [".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"]; // 预览走字节
export const KB_MANAGED_EXTS = new Set([
  ...KB_TEXT_EXTS,
  ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
  ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg",
  ".png", ".jpg", ".jpeg", ".gif", ".webp",
  ".zip", ".rar", ".7z",
]);
// 永不入索引（B62）：索引账本与侧车元数据
export const KB_SKIP_FILES = new Set(["index.json"]);
export const KB_SKIP_DIRS = new Set(["node_modules", ".git"]);
export function isMetaSidecar(name) { return name.endsWith(".meta.json"); }

// ── 查询规划（B54）：NFKC 归一化+空白折叠→CJK n-gram(≤4)+英文词干切词→停用词→
//    长任务剥脚手架→法律同义词组扩展；各路 RRF 融合（k=60）──
export const KB_STOPWORDS = new Set(["的", "了", "在", "是", "与", "及", "这", "哪些", "什么", "the", "a", "an", "of", "to", "and", "is"]);
// 法律同义词组 6 组（自写词表，语义等量；命中即扩展一路别名查询）
export const KB_SYNONYM_GROUPS = [
  ["非现场监管", "电子技术监控"],
  ["算法裁量", "机器裁量"],
  ["个人信息保护", "数据保护"],
  ["诉讼时效", "时效期间"],
  ["电子证据", "电子数据"],
  ["举证责任", "证明责任"],
];
// 法律信号词（B55：法律信号查询→全层检索不收窄）
const LEGAL_SIGNAL_RE = /(法|条|款|项|诉|判|裁|案|庭审|合同|证据|时效|管辖|被告|原告|当事人|侵权|赔偿|处罚|许可|登记|司法解释)/;
// 输出格式要求（长任务脚手架识别）
const OUTPUT_FORMAT_RE = /(总结|归纳|清单|表格|报告|要点|列点|罗列|梳理|对比|输出|格式)/;

export function normalizeQuery(q) {
  // 第 5 轮补强同款（B54）：NFKC 把全角逗号"，"转半角","、全角数字转半角；再折叠空白
  return String(q ?? "").normalize("NFKC").replace(/\s+/g, " ").trim();
}

// CJK n-gram（2..4 字）+英文小写词干（去 s/es/ing/ed 尾）；停用词剔除
export function tokenize(q) {
  const s = normalizeQuery(q);
  const out = [];
  for (const m of s.matchAll(/[a-zA-Z][a-zA-Z0-9_-]*/g)) {
    const w = m[0].toLowerCase().replace(/(ing|ed|es|s)$/u, "");
    if (w && !KB_STOPWORDS.has(w)) out.push(w);
  }
  const cjkRuns = s.match(/[\u4e00-\u9fff]+/g) ?? [];
  for (const run of cjkRuns) {
    const n = [...run];
    if (n.length === 1) { if (!KB_STOPWORDS.has(run)) out.push(run); continue; }
    for (let len = Math.min(4, n.length); len >= 2; len--) {
      for (let i = 0; i + len <= n.length; i++) {
        const g = n.slice(i, i + len).join("");
        if (!KB_STOPWORDS.has(g)) out.push(g);
      }
    }
  }
  return out;
}

// 短=1 路；长任务查询（>80 字符或法律信号+输出格式要求）剥任务脚手架产聚焦查询，
// 各子句得分≤0 时回落[归一化原查询+别名组]两路（B54）。
export function planQueries(rawQuery) {
  const norm = normalizeQuery(rawQuery);
  if (!norm) return [];
  const routes = [norm];
  const long = norm.length > 80 || (LEGAL_SIGNAL_RE.test(norm) && OUTPUT_FORMAT_RE.test(norm));
  if (long) {
    const clauses = norm.split(/[，。；？！?!;,.\n]+/).map((c) => c.trim()).filter((c) => c.length >= 2);
    const full = new Set(tokenize(norm));
    const scored = clauses
      .map((c) => { const t = tokenize(c); const hit = t.filter((x) => full.has(x)).length; return { c, s: hit - (t.length - hit) * 0.5 }; })
      .sort((a, b) => b.s - a.s);
    const best = scored[0];
    if (best && best.s > 0) routes.push(best.c);
  }
  // 同义词组：命中任一词→把组内其他词拼成别名路
  for (const group of KB_SYNONYM_GROUPS) {
    if (group.some((w) => norm.includes(w))) {
      const alias = norm;
      for (const w of group) {
        if (!norm.includes(w)) { routes.push(alias + " " + w); break; }
      }
    }
  }
  return [...new Set(routes)].slice(0, 4);
}

// ── 结构化分块（B58/§3）：目标 1800/硬顶 2400/重叠 160；锚点=markdown 标题/第N编章节条/
//    判决书固定节名/一、/1. ——正则+状态机，不用模型 ──
const HEADING_RES = [
  { re: /^#{1,6}\s+/u, kind: "md" },
  { re: /^(第[零一二三四五六七八九十百千0-9]+编|第[零一二三四五六七八九十百千0-9]+章|第[零一二三四五六七八九十百千0-9]+节)[\s、．.]?\S{0,40}/u, kind: "vol" },
  { re: /^(本院认为|经审理查明|裁判理由|裁判结果|诉讼请求|事实与理由|本院经审理查明|审判人员)/u, kind: "judgement" },
  { re: /^(第[零一二三四五六七八九十百千0-9]+条)\s*/u, kind: "article", article: true },
  { re: /^[一二三四五六七八九十]+、\S{0,40}/u, kind: "cnlist" },
  { re: /^\d{1,2}[.、]\s*\S{0,40}/u, kind: "numlist" },
];
function headingOf(line) {
  for (const h of HEADING_RES) {
    const m = line.match(h.re);
    if (m) return { kind: h.kind, text: m[0].trim(), article: h.article ? (m[0].match(/^(第[零一二三四五六七八九十百千0-9]+条)/u)?.[1] ?? null) : null };
  }
  return null;
}
export function chunkText(text) {
  const src = String(text ?? "");
  if (!src.trim()) return [];
  // 1) 按锚点切段（状态机：顺序扫描，锚点行开新段；start/end 为原文精确字符区间）
  const segments = [];
  let cur = null;
  let pos = 0;
  let mdStack = []; // markdown 标题栈（headingPath 用）
  const pushSeg = () => { if (cur && cur.text) segments.push(cur); };
  for (const line of src.split(/(?=\n)/u)) { // 保留换行归属，逐行（含行首换行）推进
    const bare = line.replace(/^\n/u, "");
    const h = headingOf(bare);
    if (h && cur?.text?.trim()) { pushSeg(); cur = null; }
    if (!cur) cur = { start: pos, text: "", heading: h ?? null };
    else if (h && !cur.text.trim()) cur.heading = h;
    cur.text += line;
    pos += line.length;
    if (h?.kind === "md") {
      const level = (bare.match(/^#+/u)?.[0] ?? "#").length;
      mdStack = mdStack.slice(0, level - 1);
      mdStack[level - 1] = bare.replace(/^#+\s*/u, "").trim();
    }
  }
  pushSeg();
  // 2) 段→块：小段并入（≤目标 1800）；超硬顶的段按硬顶+重叠 160 切开。
  //    charStart/charEnd=原文未裁剪区间精确坐标；content=trim 后正文。
  const chunks = [];
  let buf = null;
  const flush = () => {
    if (!buf || !buf.text.trim()) { buf = null; return; }
    const rawLen = buf.text.length;
    if (rawLen > KB_CHUNK_HARD_CAP) {
      const arr = [...buf.text];
      let off = 0;
      while (off < arr.length) {
        const piece = arr.slice(off, Math.min(off + KB_CHUNK_HARD_CAP, arr.length)).join("");
        if (piece.trim()) {
          chunks.push({ content: piece.trim(), charStart: buf.start + off, charEnd: buf.start + off + piece.length,
            headingPath: buf.headings, articleNumber: buf.article });
        }
        if (off + KB_CHUNK_HARD_CAP >= arr.length) break;
        off += KB_CHUNK_HARD_CAP - KB_CHUNK_OVERLAP;
      }
    } else {
      chunks.push({ content: buf.text.trim(), charStart: buf.start, charEnd: buf.start + rawLen,
        headingPath: buf.headings, articleNumber: buf.article });
    }
    buf = null;
  };
  for (const seg of segments) {
    // 第N条独立成块（B58 法条粒度）：条文段不与前后合并，自成一块（超硬顶再切）
    const standaloneArticle = seg.heading?.kind === "article";
    if (standaloneArticle || (buf && buf.text.length + seg.text.length > KB_CHUNK_TARGET)) flush();
    if (!buf) { buf = { start: seg.start, text: "", headings: [], article: seg.heading?.article ?? null }; }
    if (seg.heading?.article) buf.article = seg.heading.article;
    if (seg.heading?.kind === "md") buf.headings = [...mdStack].filter(Boolean);
    else if (seg.heading) buf.headings = [...buf.headings, seg.heading.text].slice(-6);
    buf.text += seg.text;
    if (standaloneArticle) flush();
  }
  flush();
  return chunks.map((c) => ({ ...c, chunkHash: sha256(c.content) }));
}
export function sha256(s) { return createHash("sha256").update(String(s), "utf8").digest("hex"); }

// ── 层路由（B55）：法律信号→全层；工程类按关键词路由 L1-L5；过滤不排除无层标文档 ──
// L1=法规规范 L2=案例判例 L3=模板范本 L4=内部经验 L5=其他资料（层语义自定，档位等量）
export const KB_LAYERS = ["L1", "L2", "L3", "L4", "L5"];
export const KB_CATEGORY_TO_LAYER = {
  "法规规范": "L1", "案例判例": "L2", "模板范本": "L3", "诉讼仲裁": "L2", "合同协议": "L3",
  "论文": "L4", "调研报告": "L4", "会议记录": "L4", "其他资料": "L5",
  "音视频": "L5", "图片资料": "L5", "表格数据": "L5", "压缩包": "L5",
};
const LAYER_KEYWORDS = [
  ["L1", /(法条|条文|法规|条例|司法解释|规范)/u],
  ["L2", /(判例|裁判|判决书|案例|裁定)/u],
  ["L3", /(模板|范本|文书样式|起诉状|答辩状|合同文本)/u],
  ["L4", /(心得|经验|总结|笔记|培训)/u],
];
export function routeLayer(query) {
  const s = normalizeQuery(query);
  if (LEGAL_SIGNAL_RE.test(s)) return "all";
  for (const [layer, re] of LAYER_KEYWORDS) if (re.test(s)) return layer;
  return "all";
}
// 层推断（D01 不复制缺陷：纯中文内容也按分类映射可推断——不走英文 \b 词边界路径）
export function inferDocLayer(category) { return KB_CATEGORY_TO_LAYER[category] ?? null; }

// ── 智能分类 13 类（B17）与规则兜底 ──
export const KB_CATEGORIES = ["论文", "调研报告", "合同协议", "诉讼仲裁", "案例判例", "法规规范", "模板范本", "会议记录", "音视频", "图片资料", "表格数据", "压缩包", "其他资料"];
const CATEGORY_RULES = [
  ["法规规范", /(第.+条|法条|条例|司法解释|部门规章)/u],
  ["案例判例", /(判决书|裁定书|本院认为|经审理查明|裁判结果)/u],
  ["合同协议", /(合同|协议|甲方|乙方|违约责任|签订)/u],
  ["诉讼仲裁", /(起诉状|答辩状|仲裁申请|诉讼请求|代理词)/u],
  ["模板范本", /(模板|范本|样式|____+|\{\{)/u],
  ["会议记录", /(会议纪要|与会人员|议题|主持会议)/u],
  ["调研报告", /(调研|研究报告|分析报告|白皮书)/u],
  ["论文", /(摘要|关键词|参考文献|Abstract)/u],
  ["表格数据", /^\s*[,，\t|].*[,，\t|]/mu],
];
export function ruleClassify(text, fileName) {
  const ext = (fileName.match(/\.[^.]+$/u)?.[0] ?? "").toLowerCase();
  if ([".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"].includes(ext)) return "音视频";
  if ([".png", ".jpg", ".jpeg", ".gif", ".webp"].includes(ext)) return "图片资料";
  if ([".zip", ".rar", ".7z"].includes(ext)) return "压缩包";
  if ([".csv", ".tsv", ".xlsx", ".xls"].includes(ext)) return "表格数据";
  const body = String(text ?? "").slice(0, 4000);
  for (const [cat, re] of CATEGORY_RULES) if (re.test(body)) return cat;
  return "其他资料";
}

// ── 多因子可解释打分（B52）。候选={content,title,path,category,keywords,articleNumber,layer}──
// 因子：整短语命中+12 / 层匹配+8 / 词项IDF权重×长度权重 / 覆盖度×12 / 字段命中
// （标题5·路径3·分类4·关键词4，fieldWeight=min(2.5,IDF权重)）/ 词频余弦×18 / 邻近度(6/3/1)
export function scoreChunk(routeTokens, normRoute, cand, idf) {
  const factors = [];
  const content = cand.content ?? "";
  const tokens = [...new Set(routeTokens)];
  const present = tokens.filter((t) => content.includes(t));
  if (!present.length) return { score: 0, factors };
  let score = 0;
  // 整短语命中
  if (normRoute.length >= 2 && content.includes(normRoute)) { score += 12; factors.push(["整短语命中", 12]); }
  // 层匹配
  if (cand.layer && cand.routeLayer && cand.layer === cand.routeLayer) { score += 8; factors.push(["层匹配", 8]); }
  // 词项 IDF×长度权重（≥4 字 2.4、否则 1.2；重复出现 0.3 折计一次全额+余量折）
  let termScore = 0;
  for (const t of present) {
    const w = idf(t) ?? 1;
    const lw = [...t].length >= 4 ? 2.4 : 1.2;
    const occurrences = content.split(t).length - 1;
    termScore += w * lw * (1 + (occurrences - 1) * 0.3);
  }
  if (termScore > 0) { score += termScore; factors.push(["关键词权重", termScore]); }
  // 覆盖度×12
  const coverage = present.length / Math.max(1, tokens.length);
  if (coverage > 0) { const p = coverage * 12; score += p; factors.push(["覆盖度", p]); }
  // 字段命中（fieldWeight=min(2.5, IDF 权重)——B52/G3 帽）
  let fieldScore = 0;
  const fw = Math.min(2.5, idf(present[0]) ?? 1);
  if (cand.title && present.some((t) => cand.title.includes(t))) fieldScore += 5 * fw;
  if (cand.path && present.some((t) => cand.path.includes(t))) fieldScore += 3 * fw;
  if (cand.category && present.some((t) => String(cand.category).includes(t))) fieldScore += 4 * fw;
  if (Array.isArray(cand.keywords) && cand.keywords.length && present.some((t) => cand.keywords.some((k) => String(k).includes(t)))) fieldScore += 4 * fw;
  if (fieldScore > 0) { score += fieldScore; factors.push(["字段命中", fieldScore]); }
  // 词频余弦×18（共享维稀疏向量）
  let dot = 0, q2 = 0, c2 = 0;
  for (const t of present) {
    const qtf = routeTokens.filter((x) => x === t).length;
    const ctf = content.split(t).length - 1;
    dot += qtf * ctf; q2 += qtf * qtf; c2 += ctf * ctf;
  }
  if (dot > 0 && q2 > 0 && c2 > 0) { const p = (dot / Math.sqrt(q2 * c2)) * 18; score += p; factors.push(["词频相似", p]); }
  // 邻近度（≥2 个不同词项共现窗）
  if (present.length >= 2) {
    const first = content.indexOf(present[0]);
    let window = Infinity;
    for (const t of present.slice(1)) {
      const j = content.indexOf(t, Math.max(0, first - 400));
      if (j >= 0) window = Math.min(window, Math.abs(j - first) + t.length);
    }
    if (window !== Infinity) {
      const p = window <= 120 ? 6 : window <= 360 ? 3 : 1;
      score += p; factors.push(["邻近", p]);
    }
  }
  return { score, factors };
}
// rankReason=前三因子中文标签（B52），分降序
export function rankReasonOf(factors) {
  return [...factors].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([l]) => l).join(" · ");
}

// ── 重排多样性（B53）：软惩罚非硬顶——同文档已入选≥2 条后每条罚 14；同类目罚 1.5；
//    与已选 Jaccard 相似×4 罚；池 80 取 limit。分数优势>14 同文档仍可继续入选 ──
function jaccard(aSet, bSet) {
  let inter = 0;
  for (const x of aSet) if (bSet.has(x)) inter++;
  const uni = aSet.size + bSet.size - inter;
  return uni ? inter / uni : 0;
}
export function rerank(cands, { limit = 5, tokenOf } = {}) {
  const pool = [...cands].sort((a, b) => b.score - a.score).slice(0, KB_RERANK_POOL);
  const selected = [];
  const tok = tokenOf ?? ((c) => new Set(tokenize(c.content)));
  while (selected.length < limit && pool.length) {
    let bestIdx = -1, bestAdj = -Infinity;
    for (let i = 0; i < pool.length; i++) {
      const c = pool[i];
      let adj = c.score;
      const docCount = selected.filter((s) => s.docId === c.docId).length;
      if (docCount >= 2) adj -= 14; // 软罚非硬顶（B53 勘误语义）
      if (c.category && selected.some((s) => s.category === c.category && s.docId !== c.docId)) adj -= 1.5;
      const ct = tok(c);
      for (const s of selected) adj -= jaccard(ct, tok(s)) * 4;
      if (adj > bestAdj) { bestAdj = adj; bestIdx = i; }
    }
    if (bestIdx < 0) break;
    selected.push(pool.splice(bestIdx, 1)[0]);
  }
  return selected;
}

// ── 多路 RRF 融合（B54，k=60；同 chunk 去重保留最佳路得分）──
export function rrfFuse(routeResults) {
  const byId = new Map();
  for (const list of routeResults) {
    list.forEach((hit, idx) => {
      const id = hit.chunkId;
      const rrf = 1 / (KB_RRF_K + 1 + idx);
      const prev = byId.get(id);
      if (!prev) byId.set(id, { ...hit, rrf: rrf, routeScore: hit.score });
      else { prev.rrf += rrf; if (hit.score > prev.routeScore) { prev.routeScore = hit.score; prev.rankReason = hit.rankReason; } }
    });
  }
  return [...byId.values()].sort((a, b) => b.rrf - a.rrf || b.routeScore - a.routeScore);
}

// ── 有效性过滤（B56）：侧车 deprecated/expiresAt 命中即剔除 ──
export function isMetaExpired(meta, now = Date.now()) {
  if (!meta || typeof meta !== "object") return false;
  if (meta.deprecated === true) return true;
  if (typeof meta.expiresAt === "string" && meta.expiresAt.trim()) {
    const t = Date.parse(meta.expiresAt);
    if (!Number.isNaN(t) && t < now) return true;
  }
  return false;
}

// ── 上下文预算装配（B57）：引用三件套=[引用名]+徽章+≤600 字符摘录；预算装不下来源就整条不进
//    （列表与可见证据严格对齐）──
// 徽章自写词表（B57 等量徽章面，来源=层标+侧车 meta）：层标/有时效性/已废弃/可信度高/经验分享
export function badgesOf(meta, layer) {
  const m = meta && typeof meta === "object" ? meta : {};
  const out = [];
  if (layer) out.push("层" + layer);
  if (m.deprecated === true) out.push("已废弃");
  else if (typeof m.expiresAt === "string" && m.expiresAt.trim() && !Number.isNaN(Date.parse(m.expiresAt))) out.push("有时效性");
  if (m.confidence === "high") out.push("可信度高");
  if (typeof m.source === "string" && m.source.includes("经验")) out.push("经验分享");
  return out;
}
export function buildRetrievalContext(hits, { budget = KB_CONTEXT_BUDGET, maxSources = KB_MAX_SOURCES } = {}) {
  const sources = [];
  let used = 0;
  for (const h of hits) {
    if (sources.length >= maxSources) break;
    const relPct = Math.min(100, Math.round((h.score / 30) * 100));
    const excerpt = (h.content ?? "").slice(0, KB_EXCERPT_MAX);
    const badges = badgesOf(h.meta, h.layer);
    const head = `[来源${sources.length + 1}] ${h.title}（${h.path}）相关度 ${relPct}%` + (badges.length ? `〔${badges.join("·")}〕` : "");
    const block = head + "\n" + excerpt;
    if (used + block.length > budget) break; // 整条丢弃
    used += block.length;
    sources.push({ n: sources.length + 1, title: h.title, path: h.path, relevance: relPct, excerpt, citation: citationOf(h), layer: h.layer ?? null, badges });
  }
  const contextText = sources.length
    ? sources.map((s) => `[来源${s.n}] ${s.title}（${s.path}）相关度 ${s.relevance}%${s.badges.length ? `〔${s.badges.join("·")}〕` : ""}\n${s.excerpt}`).join("\n---\n")
    : "";
  return { contextText, sources };
}
// 著录串（简化 GB/T 7714 面貌；D02 不复制缺陷：作者取行首至第一个句读，不整段吞）
export function citationOf(hit) {
  const body = String(hit.content ?? "");
  const firstLine = body.split(/\n/u)[0] ?? "";
  const author = firstLine.split(/[。；;，,]/u)[0]?.trim().slice(0, 30) ?? "";
  const year = (body.match(/(19|20)\d{2}/u)?.[0] ?? "");
  const kind = /\.docx$/u.test(hit.path ?? "") ? "D" : "Z"; // 本地资料面：docx→[D] 其余→[Z]
  const head = author && !/^(第|【|\{)/u.test(author) ? author + ". " : "";
  return `${head}${hit.title}[${kind}]${year ? ". " + year + "." : ""}`;
}

// ── 提示词装配（B33/B34）：身份句+5 个 ## 节共 6 个语义节；文案全自写 ──
export function buildAskPrompt({ question, scope, retrieval, fileBody, fileName, quote }) {
  const sections = [];
  sections.push("你是本所知识库问答助手，只依据所内知识库资料作答，不引入资料之外的依据。");
  sections.push("## 资料范围\n" + (scope.kind === "folder"
    ? `仅可使用文件夹「${scope.folderName}」及其子文件夹内的资料；范围之外的文件一律不得引用。`
    : "可使用本所知识库全部已收录文件。"));
  if (quote?.text) {
    sections.push("## 划选引用\n" + `（来源：${quote.source}）\n〈〈〈\n${quote.text.slice(0, 6000)}\n〉〉〉\n请优先分析这段划选内容。`);
  }
  if (scope.kind === "file") {
    const body = fileBody?.trim()
      ? fileBody.slice(0, KB_FILE_BODY_CAP)
      : `（未能抽取正文：文件「${fileName}」${scope.fileSize ? `（${scope.fileSize}）` : ""}为无法直接抽文的类型，请结合补充检索与提问作答，并如实说明正文不可用。）`;
    sections.push("## 当前文件正文（优先依据）\n" + body);
    sections.push("## 知识库补充检索（仅作补充，不得替代当前文件）\n" + (retrieval?.contextText || "（补充检索无结果）"));
    sections.push("## 可引用来源\n" + (retrieval?.sources?.length
      ? ["当前文件：" + fileName + "（来自文件预览页直接读取）", ...retrieval.sources.map((s) => `[来源${s.n}] ${s.title}（${s.path}，相关度 ${s.relevance}%）`)].join("\n")
      : "当前文件：" + fileName + "（来自文件预览页直接读取）"));
    sections.push("## 回答要求\n先依据当前文件正文回答；补充检索只作交叉参考，不得把其他文件的内容误当作当前文件的表述；资料不足时明确说明；引用知识库来源时标注对应 [来源N]；不得编造资料中不存在的依据。");
  } else {
    sections.push("## 检索到的资料\n" + (retrieval?.contextText || "（未检索到相关知识库内容）"));
    sections.push("## 可引用来源\n" + (retrieval?.sources?.length
      ? retrieval.sources.map((s) => `[来源${s.n}] ${s.title}（${s.path}，相关度 ${s.relevance}%）`).join("\n")
      : "无"));
    sections.push("## 回答要求\n直接回答问题，不要复述问题；所内资料不足以回答时如实说明；引用资料时标注对应 [来源N]；不得编造资料中不存在的依据。"
      + (scope.kind === "folder" ? "回答仅可引用文件夹「" + scope.folderName + "」范围内的资料。" : ""));
  }
  sections.push("## 用户问题\n" + question);
  return sections.join("\n\n");
}

// ── 线程标题（B36）：前缀即功能身份 ──
export const KB_THREAD_PREFIX_GLOBAL = "知识库全局对话";
export const KB_THREAD_PREFIX_FILE = "知识库：";
export function threadTitle(scope, question) {
  const q30 = normalizeQuery(question).slice(0, 30) + "…";
  return scope.kind === "file" ? `${KB_THREAD_PREFIX_FILE}${scope.fileName ?? "文件"} · ${q30}` : `${KB_THREAD_PREFIX_GLOBAL} · ${q30}`;
}
export function isKbThreadTitle(title) {
  return typeof title === "string" && (title.startsWith(KB_THREAD_PREFIX_GLOBAL) || title.startsWith(KB_THREAD_PREFIX_FILE));
}

// ── 路径安全（B62）：拒绝 .. 逃逸/绝对路径/盘符；分隔符统一 / 存库 ──
/**
 * 同步差集删除。全量扫完才按「账上有、盘上无」删除；截断时只删除排序不晚于
 * 本批最后一条的未见路径（与 kbWalkFiles 的 zh-Hans-CN 序一致）。晚于 cutoff
 * 的账本行这次没被扫到，不能当成已删除。
 * @param {Iterable<string>} knownRels
 * @param {Iterable<string>} seenRels
 * @param {{truncated?: boolean, cutoff?: string}} [opts]
 * @returns {string[]}
 */
export function kbIndexRemovals(knownRels, seenRels, { truncated = false, cutoff = "" } = {}) {
  const seen = seenRels instanceof Set ? seenRels : new Set(seenRels);
  const out = [];
  for (const rel of knownRels) {
    if (seen.has(rel)) continue;
    if (!truncated) {
      out.push(rel);
      continue;
    }
    if (cutoff && String(rel).localeCompare(cutoff, "zh-Hans-CN") <= 0) out.push(rel);
  }
  return out;
}

export function safeRelPath(input) {
  const raw = String(input ?? "").replace(/\\/g, "/").replace(/^\/+/, "");
  if (/^[a-zA-Z]:/.test(raw)) throw new Error("知识库路径不得为盘符绝对路径");
  const parts = raw.split("/").filter((p) => p && p !== ".");
  if (parts.some((p) => p === "..")) throw new Error("知识库路径不得含 ..（逃逸拒绝）");
  if (parts.some((p) => /[<>:"|?*\u0000-\u001f]/.test(p))) throw new Error("文件名含非法字符");
  if (!parts.length) throw new Error("知识库路径不能为空");
  return parts.join("/");
}
export function extOf(relPath) {
  const m = String(relPath).match(/\.[^.]+$/u);
  return m ? m[0].toLowerCase() : "";
}
// 答案后处理（B40）：剥离把用户问题当开头的重复；DSML 残帧按自家模型风险裁量（当前模型
// 未见协议泄漏实例，仅剥显式全角竖线残帧，不做过重清洗——对拍 40 裁量注记）。
export function cleanAnswer(text, question) {
  let t = String(text ?? "");
  // 协议残帧按自家模型风险裁量（对拍 40）：仅剥显式全/半角竖线残帧，不做重清洗
  t = t.replace(/[｜|][a-zA-Z\-]{4,}[｜|]/gu, "");
  const q = normalizeQuery(question);
  if (q) {
    const head = t.slice(0, q.length + 40);
    const qVariants = [q, q.replace(/？$/, ""), q.replace(/[?？]$/, "")];
    for (const v of qVariants) {
      if (v.length >= 4 && head.startsWith(v)) {
        t = t.slice(v.length).replace(/^[\s:：\n]+/, "").replace(/^[#*]{1,6}\s*/u, "");
        break;
      }
    }
  }
  return t.trim();
}

// ── B60 shell 绕库守卫（主对话出站边界，三条件与）：①指向知识库路径 ②批量 PDF 遍历
//    ③低级 PDF 解析器——三者同时命中才拦；纯直扫/列目录/单文件读取不触发（阈值语义同
//    RE-20 B60：非一切直扫）。拦截点如实注记：竞品拦模型生成的 bash 工具调用（其 agent-loop
//    内层）；自家桥的回合出站收敛在 oc28 运行时，桥面唯一可拦层=sendText 出站文本——同阈值
//    语义落此边界，非同位拦截（差异在提交语与对拍注记中如实载明，不伪造）。
const KB_GUARD_TARGET_RE = /(kb[\/\\]+files|juscite[\/\\]+kb|知识库(?:目录|根|路径|文件|文集)?)/i;
const KB_GUARD_BULK_RE = /(glob\.glob|\.rglob\(|os\.walk|find\s+\S+\s+-name|for\s+[^;\n]{0,80}\*\.pdf|get-childitem[^;\n]{0,80}-recurse)/i;
const KB_GUARD_PARSER_RE = /\b(fitz|pymupdf|pdfplumber|pypdf|pdftotext|tesseract|ocrmypdf)\b/i;
export function kbShellBypassGuard(text, { kbRoot } = {}) {
  const s = String(text ?? "");
  if (!s.trim()) return null;
  if (!KB_GUARD_TARGET_RE.test(s) && !(kbRoot && s.includes(kbRoot))) return null; // ①
  if (!KB_GUARD_BULK_RE.test(s)) return null; // ②
  if (!KB_GUARD_PARSER_RE.test(s)) return null; // ③
  return { target: true, bulk: true, parser: true };
}
// 拦截 advisory（文案自写，自家工具名；竞品内嵌其工具名不抄）
export const KB_BYPASS_ADVISORY =
  "这条消息看起来在要求批量解析知识库目录下的 PDF 文件，已在本地面停，未交模型执行。" +
  "请改为：先用知识库检索（kbSearch）缩小候选文件，再对单个文件用读文件（kbRead）查看或抽取原文。";
