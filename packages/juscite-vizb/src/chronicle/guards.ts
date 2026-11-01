// 大事记判据守卫（契约四：判据先行；任何一条不成立即拒绝出表，禁止降级硬填）。
// 编号=我方重编（VB-前缀），语义族对齐规格 §2.4 大事记侧：A 切分/B 照录/C 标题/D 日期/E 不判断
// ＋ I 摄入（intake.ts）＋ R 渲染零改动（读产物，见 parseBack+renderGuard）＋ W/X 交付自检。
// 元纪律：每条守卫配改坏用例（vizb_synthetic BREAK_CASES）；判据可被证伪即撤回并留痕。

import { CHRONICLE_BANNED_QUALIFIERS, CHRONICLE_VERBS, checkDateStr } from "./tables.ts";
import { deriveEvidenceStatus, type FactBase, type FactRow } from "./factbase.ts";
import { firstDivergence, isSubsequence, stripPunct } from "./textcheck.ts";

export interface Violation {
  group: "VB-A" | "VB-B" | "VB-C" | "VB-D" | "VB-E";
  code: string;
  msg: string;
  factNo?: number;
}

const RE_LOCATOR = /^p\d{1,4}(?:¶\d{1,3})?$/;

/** A/B/C/D/E 五组底稿守卫（全部可机验；返回空=通过）。 */
export function guardChronicle(fb: FactBase): Violation[] {
  const v: Violation[] = [];
  const docIds = new Set(fb.docs.map((d) => d.docId));
  const evidenceVolume = new Map<string, string>(); // 证据编号 → 册（同号不跨册）
  const evidenceDoc = new Map<string, string>();    // 证据编号 → 文档

  for (const f of fb.facts) {
    // ── VB-A 切分 ──
    if (!RE_LOCATOR.test(f.locator)) v.push({ group: "VB-A", code: "A-locator", msg: `定位「${f.locator}」不符 p页[¶段] 形态（每条事实须带页码/段落定位）`, factNo: f.factNo });
    if (f.evidenceNo) {
      const prevV = evidenceVolume.get(f.evidenceNo);
      if (prevV != null && prevV !== f.volume) v.push({ group: "VB-A", code: "A-evidence-cross-volume", msg: `证据编号「${f.evidenceNo}」跨册使用（先见 ${prevV}，再见 ${f.volume}；同一证据编号不跨材料册）`, factNo: f.factNo });
      else evidenceVolume.set(f.evidenceNo, f.volume);
      const prevD = evidenceDoc.get(f.evidenceNo);
      if (prevD != null && prevD !== f.sourceDoc) v.push({ group: "VB-A", code: "A-evidence-cross-doc", msg: `证据编号「${f.evidenceNo}」跨文档使用（先见 ${prevD}，再见 ${f.sourceDoc}）`, factNo: f.factNo });
      else evidenceDoc.set(f.evidenceNo, f.sourceDoc);
    }
    // ── VB-B 照录（保真兜底：去标点子序列）──
    const doc = fb.docs.find((d) => d.docId === f.sourceDoc);
    if (!doc) {
      v.push({ group: "VB-A", code: "A-source-missing", msg: `来源文档「${f.sourceDoc}」不存在（材料编号须存在）`, factNo: f.factNo });
    } else {
      const needle = stripPunct(f.content);
      const hay = stripPunct(doc.text);
      if (!isSubsequence(needle, hay)) {
        const at = firstDivergence(needle, hay);
        v.push({
          group: "VB-B", code: "B-not-subsequence",
          msg: `主要内容非源文本子序列（去标点保序核验失败，事实 ${f.factNo} 于第 ${at + 1} 字处失配：「${needle.slice(Math.max(0, at - 3), at + 4)}」在源文无保序对应）——只许少取，不许改写`,
          factNo: f.factNo,
        });
      }
      // 切分可复原（不漏段·保序）：同源事实按序拼接仍是源文子序列
      const same = fb.facts.filter((x) => x.sourceDoc === f.sourceDoc);
      if (same[0] === f) {
        const joined = stripPunct(same.map((x) => x.content).join(""));
        if (!isSubsequence(joined, hay)) v.push({ group: "VB-A", code: "A-restore-broken", msg: `来源「${f.sourceDoc}」各事实按序拼接后非源文子序列（切分不可复原，疑似乱序或改写）` });
      }
      // 主体照录：每个主体名须在源文中出现（照录不归并的机械面）
      for (const s of f.subjects) if (!isSubsequence(stripPunct(s), hay)) v.push({ group: "VB-E", code: "E-subject-not-verbatim", msg: `主体「${s}」非源文照录（主体角色照录不归并）`, factNo: f.factNo });
    }
    // ── VB-C 标题 ──
    if (!CHRONICLE_VERBS.has(f.verb)) v.push({ group: "VB-C", code: "C-verb-off-table", msg: `动词「${f.verb}」不在封闭动词表（表外拒绝；律师确认后补表并记 changelog）`, factNo: f.factNo });
    const titleChars = [...f.title];
    if (titleChars.length > 15) v.push({ group: "VB-C", code: "C-title-too-long", msg: `事项标题 ${titleChars.length} 字超 15 字上限`, factNo: f.factNo });
    for (const w of CHRONICLE_BANNED_QUALIFIERS) if (f.title.includes(w)) v.push({ group: "VB-C", code: "C-title-qualifier", msg: `事项标题含定性词「${w}」（定性词表只禁模型撰写字段，不断案）`, factNo: f.factNo });
    const open = (f.title.match(/《/g) ?? []).length;
    const close = (f.title.match(/》/g) ?? []).length;
    if (open !== close || (open > 0 && /》[^《]*》/.test(f.title)) || f.title.indexOf("》") < f.title.indexOf("《")) {
      v.push({ group: "VB-C", code: "C-bookmark-unpaired", msg: `事项标题书名号不配对（《${open} 只》${close} 只）`, factNo: f.factNo });
    }
    if (!docIds.has(f.sourceDoc)) v.push({ group: "VB-C", code: "C-doc-missing", msg: `材料编号「${f.sourceDoc}」不存在`, factNo: f.factNo });
    // ── VB-D 日期 ──
    const err = checkDateStr(f.dateStr, f.datePrecision);
    if (err) v.push({ group: "VB-D", code: "D-format", msg: `日期「${f.dateStr}」/精度「${f.datePrecision}」：${err}`, factNo: f.factNo });
    // ── VB-E 不判断 ──
    if (f.dispute !== null) v.push({ group: "VB-E", code: "E-dispute-filled", msg: "争点字段被填写（判断字段禁填；争点由律师在母表回填）", factNo: f.factNo });
    if (f.evidenceStatus !== undefined) v.push({ group: "VB-E", code: "E-status-handfilled", msg: `证据状态被手填「${String(f.evidenceStatus)}」（由有无证据编号机械决定，手填即拒）`, factNo: f.factNo });
    const derived = deriveEvidenceStatus(f);
    if (derived === "仅当事人陈述") {
      const listed = fb.uncertainty.some((u) => u.includes(`事实 ${f.factNo}`));
      if (!listed) v.push({ group: "VB-E", code: "E-uncertainty-missing", msg: `事实 ${f.factNo} 无书证（仅当事人陈述）但未进不确定清单（清单联动）`, factNo: f.factNo });
    }
  }
  return v;
}

/** 排序视图（区间取起点；同键按事实号稳定排序）——渲染输入唯一排序源。 */
export function sortedFacts(fb: FactBase): FactRow[] {
  const key = (f: FactRow) => f.datePrecision === "span"
    ? require_spanKey(f.dateStr)
    : f.datePrecision === "day" ? f.dateStr : f.datePrecision === "month" ? `${f.dateStr}-01` : `${f.dateStr}-01-01`;
  return fb.facts.slice().sort((a, b) => key(a).localeCompare(key(b)) || a.factNo - b.factNo);
}
// 局部小函数避免与 tables 循环依赖（span 起点规则同 tables.sortKeyOfSpan：缺省补 01）
function require_spanKey(dateStr: string): string {
  const m = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?~/.exec(dateStr);
  if (!m) return "9999-99-99";
  return `${m[1]}-${(m[2] ?? "01").padStart(2, "0")}-${(m[3] ?? "01").padStart(2, "0")}`;
}
