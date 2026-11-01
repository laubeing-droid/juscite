// 法条手册模型件（RE-13-法条手册.md §3.2/§3.3 落码，纯函数零依赖）：
//   md 内容契约校验 + 确定性解析（正则+状态机，禁 LLM）+ 效力徽章推导 + 修订链/跨法废止。
// 打包期（lawbook_pack_build.mjs）与桥解析（lawbook_service.mjs）共用本件=双闸同规；
// 契约违规一律 fail-closed 具名报错（法 ID+违规类型+行号），不静默吞正文、不崩溃（§2 H7 不复刻）。
// 术语锚点（对齐规格）：titles/info(信息块)/INFO END/FORCE BREAK/TABLE/修正案模式/lineStartRe。

// 条文分段正则（与竞品 Consts.swift lineStartRe 等价：第X条 ∣ 一、中文数字顿号）
export const LINE_START_RE = /^((第[一二三四五六七八九十零百千万]+条)|[一二三四五六七八九十零百千万]+、)/;
const HEADING_RE = /^(#{2,6})\s+(.+)$/; // 层级标题（## 起；# 单独收 titles）
const TITLE1_RE = /^#\s+(.+)$/; // 整法标题（可多行：# 标题 + # 分编名）
const BARE_HEADING_RE = /^#{1,6}\s*$/; // 裸 # 行（无空格无标题=畸形标题，契约违规②）
const REPEAL_RE = /((?:《[^》]+》[、和，]?)+)(?:同时)?废止/g; // 跨法废止书名号组（等量 database.py invalidate_laws）
const EFFECT_DATE_RE = /自(\d{4})年(\d{1,2})月(\d{1,2})日起施行/; // 正文生效日正则（三分支①）
const EFFECT_KEYWORD_DIRECT = ["自公布之日起施行", "自发布之日起施行", "本解释公布施行后", "自公布施行之日起"]; // 关键词直取公布日（并入②③）

export class LawbookContractError extends Error {
  constructor(lawId, violations) {
    const head = violations.map((v) => `${v.type}@L${v.line}`).join("; ");
    super(`法条 md 契约违规（法 ID=${lawId}）：${head}`);
    this.name = "LawbookContractError";
    this.lawId = lawId;
    this.violations = violations;
  }
}

// ── 契约校验（双闸同规：打包期预校验与解析期同一函数）──
// 违规清单（§3.3/§2 H7 我方 fail-closed 四类）：
//   ①INFO_END_MISSING 信息块未终结 ②BARE_HEADING 裸 # 行 ③TABLE_UNCLOSED/TABLE_PAIRING 表标记不配对 ④EMPTY_BODY 正文为空
export function validateLawMd(text) {
  const violations = [];
  const lines = String(text ?? "").split(/\r?\n/);
  let infoEndSeen = 0;
  let tableOpenLine = 0;
  let inTable = false;
  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].trim();
    if (t === "<!-- INFO END -->") { infoEndSeen += 1; continue; }
    if (BARE_HEADING_RE.test(t)) violations.push({ type: "BARE_HEADING", line: i + 1 });
    if (t === "<!-- TABLE -->") {
      if (inTable) violations.push({ type: "TABLE_PAIRING", line: i + 1 });
      inTable = true; tableOpenLine = i + 1; continue;
    }
    if (t === "<!-- TABLE END -->") {
      if (!inTable) violations.push({ type: "TABLE_PAIRING", line: i + 1 });
      inTable = false; continue;
    }
  }
  if (infoEndSeen === 0) violations.push({ type: "INFO_END_MISSING", line: 0 });
  if (inTable) violations.push({ type: "TABLE_UNCLOSED", line: tableOpenLine });
  // ④正文为空（打包闸词法近似：END 后无任何非空行；语义判定仍由解析期权威兜底）
  if (infoEndSeen > 0) {
    const infoEndIdx = lines.findIndex((l) => l.trim() === "<!-- INFO END -->");
    if (!lines.slice(infoEndIdx + 1).some((l) => l.trim() !== "")) {
      violations.push({ type: "EMPTY_BODY", line: infoEndIdx + 1 });
    }
  }
  return { ok: violations.length === 0, violations, lineCount: lines.length };
}

// ── 确定性解析（等量 LawContentPraser 语义；违规即 throw LawbookContractError）──
// 产出：titles（可多行）/ info（键值行+无键行）/ sections（扁平，层级=##数量）/ toc（树）/ paragraphs（带行号）
export function parseLawMd(text, lawId = "?") {
  const v = validateLawMd(text);
  if (!v.ok) throw new LawbookContractError(lawId, v.violations);
  const lines = String(text).split(/\r?\n/);
  let infoEndIdx = lines.findIndex((l) => l.trim() === "<!-- INFO END -->");

  const titles = [];
  const info = [];
  for (let i = 0; i < infoEndIdx; i++) {
    const t = lines[i].trim();
    if (!t) continue;
    const h1 = t.match(TITLE1_RE);
    if (h1) { titles.push(h1[1].trim()); continue; }
    const cut = t.indexOf(" ");
    if (cut > 0) info.push({ key: t.slice(0, cut), value: t.slice(cut + 1).trim() });
    else info.push({ key: "", value: t }); // 无键行（渲染层按居中 markdown 处理，等量 B5）
  }

  const isAmendment = titles.some((t) => t.includes("修正")); // 标题含"修正"→修正案模式（- 开头=续行）
  const sections = []; // {level(2..6), title, line}
  const paragraphs = []; // {line, text, articleNo|null, table?}
  let cur = null;
  let inTable = false;
  let tableRows = null;
  let tableLine = 0;
  const flush = () => {
    if (cur && cur.parts.length) {
      // 续行拼接不插换行（§2 H7(c) 第 7 轮钉定：解析层不插换行，等量显示效果由渲染层折行承担）
      paragraphs.push({ line: cur.line, text: cur.parts.join(""), articleNo: cur.articleNo ?? null });
    }
    cur = null;
  };
  for (let i = infoEndIdx + 1; i < lines.length; i++) {
    const t = lines[i].trim();
    if (!t) continue; // 空行仅作源排版分隔，不切段（等量 lineStartRe 语义：命中才新段）
    if (t === "<!-- FORCE BREAK -->") { flush(); continue; }
    if (t === "<!-- TABLE -->") { flush(); inTable = true; tableRows = []; tableLine = i + 1; continue; }
    if (t === "<!-- TABLE END -->") {
      flush();
      if (tableRows?.length) paragraphs.push({ line: tableLine, text: "", articleNo: null, table: tableRows });
      inTable = false; tableRows = null; continue;
    }
    if (inTable) {
      if (isTableSeparatorRow(t)) continue; // 跳过 |- 分隔行（等量 B8）
      tableRows.push(t.startsWith("|") ? t : `| ${t}`); // 管道表行原样保留（渲染层切列）
      continue;
    }
    const h = t.match(HEADING_RE);
    if (h) { flush(); sections.push({ level: h[1].length, title: h[2].trim(), line: i + 1 }); continue; }
    const h1 = t.match(TITLE1_RE);
    if (h1) { flush(); titles.push(h1[1].trim()); continue; } // END 后再出 # 标题（罕见）照收
    const am = t.match(LINE_START_RE);
    if (am) { flush(); cur = { line: i + 1, parts: [t], articleNo: am[1] }; continue; }
    if (isAmendment && t.startsWith("-")) {
      if (!cur) cur = { line: i + 1, parts: [], articleNo: null };
      cur.parts.push(t.replace(/^-/, "")); // 修正案模式：- 开头=上一条续行（去 - 拼接）
      continue;
    }
    if (!cur) { cur = { line: i + 1, parts: [t], articleNo: null }; continue; }
    cur.parts.push(t); // lineStartRe 未命中=续行拼接（等量）
  }
  flush();
  // TABLE_UNCLOSED 已由 validateLawMd 兜住（抛错路径），此处防御无副作用
  return { titles, info, sections, toc: buildTocTree(sections), paragraphs };
}

function isTableSeparatorRow(t) {
  const cells = t.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  return cells.length > 0 && cells.every((c) => /^:?-{1,}:?$/.test(c));
}

// TOC 树：章=可展开组、节=叶子（等量 B4；indent=## 数量，行号=滚动锚）
export function buildTocTree(sections) {
  const root = [];
  const stack = [];
  for (const s of sections) {
    const node = { level: s.level, title: s.title, line: s.line, children: [] };
    while (stack.length && stack[stack.length - 1].level >= s.level) stack.pop();
    (stack.length ? stack[stack.length - 1].children : root).push(node);
    stack.push(node);
  }
  return root;
}

// ── 效力徽章推导（§3.1；运行时推导不硬编码列）──
// today 口径=UTC+8 日历日（固定 Asia/Shanghai，y-m-d 字符串序比较；§3.1 第 7 轮钉定）
export function todayCn(nowMs = Date.now()) {
  return new Date(nowMs + 8 * 3600 * 1000).toISOString().slice(0, 10);
}
function isDateStr(s) { return typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s); }
// 返回 'repealed' 已废止 | 'not_yet' 暂未施行 | 'current' 现行有效
export function deriveEffect({ valid_from, valid_to, publish }, today = todayCn()) {
  const to = isDateStr(valid_to) ? valid_to : "";
  const from = isDateStr(valid_from) ? valid_from : "";
  if (to && to <= today) return "repealed"; // valid_to 非空且 <= today（含失效当天）
  if (from && from > today) return "not_yet"; // valid_from 非空且在未来
  return "current"; // valid_from 缺失/不可解析=已施行（等量 TLaw is_valid）
}
export const EFFECT_LABEL = { repealed: "已废止", not_yet: "暂未施行", current: "现行有效" };

// ── 标题搜索分词（等量 C2/C10：分词器可换实现，语义=顺序无关全包含）──
// ASCII 词元（小写）+ 汉字二元词元（相邻滑窗，末字奇数落单）；全 token 被法名包含即命中。
export function tokenizeQuery(q) {
  const s = String(q ?? "").trim().toLowerCase();
  if (!s) return [];
  const tokens = [];
  for (const m of s.matchAll(/[a-z0-9]+|[\u4e00-\u9fff]+/g)) {
    const run = m[0];
    if (/^[a-z0-9]+$/.test(run)) { tokens.push(run); continue; }
    if (run.length === 1) { tokens.push(run); continue; }
    for (let i = 0; i + 2 <= run.length; i += 2) tokens.push(run.slice(i, i + 2));
    if (run.length % 2 === 1) tokens.push(run[run.length - 1]);
  }
  return tokens;
}
export function titleMatches(name, query) {
  const q = String(query ?? "").trim();
  if (!q) return false;
  if (name.includes(q)) return true;
  const tokens = tokenizeQuery(q);
  return tokens.length > 0 && tokens.every((t) => name.includes(t));
}

// ── 生效日提取（打包期 ingest；三分支见 RE-13 §2 H1/§3.1）──
// 返回 '' 或 YYYY-MM-DD：①正文正则提取 ②关键词直取公布日；提取值<公布日→封顶公布日（②并入）。
export function extractValidFrom(bodyText, publish) {
  const body = String(bodyText ?? "");
  const m = body.match(EFFECT_DATE_RE);
  if (m) {
    const date = `${m[1]}-${String(Number(m[2])).padStart(2, "0")}-${String(Number(m[3])).padStart(2, "0")}`;
    return publish && date < publish ? publish : date;
  }
  if (EFFECT_KEYWORD_DIRECT.some((k) => body.includes(k))) return publish || "";
  return "";
}

// ── 跨法废止抽取（等量 H2）：返回被废法名组（已去"中华人民共和国"前缀）──
export function extractRepealedNames(bodyText) {
  const body = String(bodyText ?? "");
  const names = [];
  for (const m of body.matchAll(REPEAL_RE)) {
    for (const bm of m[1].matchAll(/《([^》]+)》/g)) {
      const n = bm[1].replace(/^中华人民共和国/, "");
      if (!names.includes(n)) names.push(n);
    }
  }
  return names;
}

// ── 修订链构建（等量 H1：同名多版本按 publish 排序→ver=同名数→旧版 valid_to=新版生效日）──
// rows: [{id,name,level,publish,valid_from}]；返回 {updates:Map(id→{ver,valid_to?}), warnings:string[]}
// 纪律：三分支回填仅对入链的同名多版本；单版本 valid_from 留空不回填；司法解释不入链；
//       缺 publish / level 不一致→警告不入链（版本本身仍计 ver=同名数，等量 update_versions 口径）。
export function buildRevisionChain(rows) {
  const updates = new Map();
  const warnings = [];
  const byName = new Map();
  for (const r of rows) {
    if (!byName.has(r.name)) byName.set(r.name, []);
    byName.get(r.name).push(r);
    updates.set(r.id, { ver: 1 });
  }
  for (const [name, group] of byName) {
    if (group.length < 2) continue;
    for (const g of group) updates.get(g.id).ver = group.length; // ver=同名版本数
    const levels = new Set(group.map((g) => g.level));
    if (levels.size > 1) { warnings.push(`同名多版本 level 不一致，警告不入链：${name}`); continue; }
    if (levels.has("司法解释")) continue; // 司法解释不入链（ver 仍计数）
    const missingPub = group.filter((g) => !g.publish);
    if (missingPub.length) { warnings.push(`同名多版本缺 publish，警告不入链：${name}（${missingPub.length} 版）`); continue; }
    const ordered = [...group].sort((a, b) => (a.publish < b.publish ? -1 : a.publish > b.publish ? 1 : 0));
    for (let i = 0; i + 1 < ordered.length; i++) {
      const next = ordered[i + 1];
      const eff = next.valid_from || next.publish; // 新版生效日：valid_from 缺失→取其公布日（链内三分支③）
      updates.get(ordered[i].id).valid_to = eff;
    }
  }
  return { updates, warnings };
}

// ── 跨法废止链（等量 H2）：repealer 行（含废止条款）→ 被废法最后一版 valid_to=施行日 ──
// 防呆四则：同名排除（版本衔接归 H1）/ 被废法须早于废止生效日已发布 / 去国名前缀 / 无生效日→警告跳过。
// bodies: Map(id→正文全文)；rows 同上（需 ver 已定）。返回 {updates:Map(id→{valid_to}), warnings}
export function buildRepealChain(rows, bodies) {
  const updates = new Map();
  const warnings = [];
  const lastByName = new Map();
  for (const r of rows) {
    const prev = lastByName.get(r.name);
    if (!prev || (r.publish ?? "") >= (prev.publish ?? "")) lastByName.set(r.name, r);
  }
  for (const r of rows) {
    const body = bodies.get(r.id) ?? "";
    const names = extractRepealedNames(body);
    if (!names.length) continue;
    const effective = r.valid_from || r.publish;
    if (!effective) { warnings.push(`含废止条款但无生效日期，警告跳过不入链：${r.name}`); continue; }
    for (const name of names) {
      if (name === r.name) continue; // 同名排除（版本衔接归 H1 管）
      const target = lastByName.get(name);
      if (!target) continue; // 不在包内：不造不猜
      if (!target.publish || target.publish >= effective) {
        warnings.push(`被废法发布期防呆命中（须早于生效日已发布），跳过：${name} ← ${r.name}`);
        continue;
      }
      const prev = updates.get(target.id)?.valid_to;
      if (!prev || effective < prev) updates.set(target.id, { valid_to: effective }); // 多处废止取最早
    }
  }
  return { updates, warnings };
}
