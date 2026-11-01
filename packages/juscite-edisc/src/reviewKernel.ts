// 【功能 #42 电子数据取证】审查内核（RE-42 §2.D/§2.F/§2.G，纯模型零 I/O，文案全部自写）。
// 三档分类（F3）：ok=明显充分 / doubt=存疑保留（默认档，双向门：宁可多标注交律师，不可漏标）/
// insufficient=明显不足（只记录建议，不自动排除）。三性/证明力由律师在面板逐项评估，
// 本层只给电子数据专项的确定性预置（F5）与四类标记（F11：核实/存疑/引用待定/举证期限）。
// 人机分工边界（对拍竞品情报/2026-10-29-规格波/yuanli-深挖台账v2.md §2 chat-recording-evidence
// 行为级参照，CC BY-NC-SA 禁吸收、只对拍机制）：工具做定位/锚定/聚合/校验加速，
// 定档权与真实性判断归人——预置档一律落 doubt 待律师过目，无自动终档通道。

export type FlagLevel = "ok" | "doubt" | "insufficient";
export const FLAG_LEVELS: FlagLevel[] = ["ok", "doubt", "insufficient"];
export const FLAG_TAGS = ["核实", "存疑", "引用待定", "举证期限"] as const;
export type FlagTag = (typeof FLAG_TAGS)[number];
export const PROOF_STRENGTHS = ["强", "中", "弱", "无"] as const; // 证明力四级（F4）

// ── F1 待证事实（审查先行件；提炼自诉求与争点，四类不入清单——文案自写）──
export const FACT_EXCLUSIONS = [
  "各方均无争议的事实",
  "已由生效裁判文书确认的事实",
  "纯法律适用问题",
  "公知事实",
] as const;
export const FACT_EXCLUSION_NOTE =
  `待证事实自诉求与争点提炼；以下四类不入清单：${FACT_EXCLUSIONS.join("、")}。`;

// ── F2 形式六要素（先查形式再实质审查；缺项=先补齐）──
export const FORMAL_ELEMENTS = ["名称", "形成时间", "出具方", "原件或复印件", "证明目的", "对应待证事实"] as const;
export type FormalElementKey = (typeof FORMAL_ELEMENTS)[number];
export interface FormalElementCheck {
  complete: boolean;
  missing: FormalElementKey[];
  note: string;
}
/** 六要素逐项查空（trim 后非空才算在位）；缺项给"先补齐再实质审查"可读提示。 */
export function checkFormalElements(elements: Partial<Record<FormalElementKey, string>> = {}): FormalElementCheck {
  const missing = FORMAL_ELEMENTS.filter((k) => !String(elements?.[k] ?? "").trim());
  return {
    complete: missing.length === 0,
    missing,
    note: missing.length
      ? `形式要素待补齐：${missing.join("、")}（先补齐，再作实质审查）`
      : "形式六要素齐备",
  };
}

// ── F4 三性评估（真实性/合法性/关联性逐项结论+理由；结论闭集自定）──
export const TRIPLE_ATTRIBUTES = ["真实性", "合法性", "关联性"] as const;
export const ATTR_CONCLUSIONS = ["符合", "存疑", "不符合"] as const;
export type TripleAttr = (typeof TRIPLE_ATTRIBUTES)[number];
export type AttrConclusion = (typeof ATTR_CONCLUSIONS)[number];
export interface TripleFinding { attr: TripleAttr; conclusion: AttrConclusion; reason: string }
/** 三性表单归一：属性/结论闭集校验+去重+理由可空；不合格返回可读错误（不在此抛 HTTP）。 */
export function normalizeTripleFindings(
  findings: { attr?: string; conclusion?: string; reason?: string }[] = [],
): { ok: true; findings: TripleFinding[] } | { ok: false; error: string } {
  if (!Array.isArray(findings) || findings.length === 0) return { ok: false, error: "三性评估至少要有一项（真实性/合法性/关联性）" };
  const seen = new Set<string>();
  const out: TripleFinding[] = [];
  for (const f of findings) {
    const attr = String(f?.attr ?? "");
    const conclusion = String(f?.conclusion ?? "");
    if (!(TRIPLE_ATTRIBUTES as readonly string[]).includes(attr)) {
      return { ok: false, error: `三性属性必须是 ${TRIPLE_ATTRIBUTES.join("/")}（收到：${attr || "空"}）` };
    }
    if (!(ATTR_CONCLUSIONS as readonly string[]).includes(conclusion)) {
      return { ok: false, error: `三性结论必须是 ${ATTR_CONCLUSIONS.join("/")}（收到：${conclusion || "空"}）` };
    }
    if (seen.has(attr)) return { ok: false, error: `三性属性重复：${attr}` };
    seen.add(attr);
    out.push({ attr: attr as TripleAttr, conclusion: conclusion as AttrConclusion, reason: String(f?.reason ?? "").trim() });
  }
  return { ok: true, findings: out };
}

// ── F6 四类缺口（结构化：类目闭集+补充建议四件套）──
export const GAP_KINDS = ["完全缺口", "证明力不足", "证据链断裂", "形式瑕疵"] as const;
export type GapKind = (typeof GAP_KINDS)[number];
export interface GapSuggestion {
  id: string; caseId: string; kind: GapKind;
  factText: string;      // 对应待证事实
  suggestion: string;    // 建议取得的证据
  sourceChannel: string; // 取得渠道/方式
  difficulty: string;    // 收集难度
  deadlineNote: string;  // 举证期限硬约束提示
  createdBy: string; createdAt: string;
}
/** 缺口行可读格式（报告第五节与 UI 共用形状）。 */
export function formatGapLine(g: Pick<GapSuggestion, "kind" | "factText" | "suggestion" | "sourceChannel" | "difficulty" | "deadlineNote">): string {
  const seg = [
    `对应待证事实：${g.factText || "（未指定）"}`,
    `建议补充：${g.suggestion}`,
    `取得渠道：${g.sourceChannel || "待定"}`,
    `收集难度：${g.difficulty || "未评估"}`,
  ];
  if (g.deadlineNote) seg.push(`期限警示：${g.deadlineNote}（逾期风险单独提示）`);
  return `【${g.kind}】${seg.join("｜")}`;
}

// ── F9 规则引用来源标签（网络检索/模型知识类必须带「须核实」限定）──
export const RULE_SOURCE_ORIGINS = ["自写预置", "法源线现行版", "网络检索", "模型知识"] as const;
export type RuleSourceOrigin = (typeof RULE_SOURCE_ORIGINS)[number];
export const VERIFY_REQUIRED_MARK = "须核实";
/** 来源标签：网络检索/模型知识→附「须核实」限定；其余原样。 */
export function ruleSourceLabel(origin: RuleSourceOrigin | string): string {
  return origin === "网络检索" || origin === "模型知识" ? `${origin}（${VERIFY_REQUIRED_MARK}）` : String(origin);
}
export const SOURCE_LABEL_DISCIPLINE =
  "规则引用一律带来源标签；来自网络检索或模型知识的内容必须带「须核实」限定，不得删标签；检索不到就写检索不到，不得无声补充。";

export type EdiscKind = "chat" | "statement" | "table" | "generic";

export interface ReviewFlagPreset {
  kind: EdiscKind;
  level: FlagLevel;
  proofStrength: (typeof PROOF_STRENGTHS)[number];
  issues: string[];
  supports: string[];
  weakens: string[];
  lawyerAction: string;
  tags: FlagTag[];
}

/** 电子数据专项预置（F5；措辞自写，法规内容按法源线现行版本另行核验，不在此引条号）：
 *  经公证/可信时间戳 → ok；未经公证（默认假设）→ doubt + 证明力预置弱 + 印证/鉴定两问；
 *  真实性攻击预判必含“已被篡改”方向（F5/F7），应对=补充印证证据/申请鉴定。 */
export function presetReviewFlag(kind: EdiscKind, opts: { notarized?: boolean } = {}): ReviewFlagPreset {
  const notarized = Boolean(opts.notarized);
  if (notarized) {
    return {
      kind,
      level: "ok",
      proofStrength: "中",
      issues: ["已附公证或可信时间戳凭证，仍建议核对载体与导出件的一致性"],
      supports: ["公证/时间戳凭证在卷"],
      weakens: [],
      lawyerAction: "律师核对公证范围是否覆盖本批记录的全部页与时间段",
      tags: ["核实"],
    };
  }
  const base: Record<Exclude<EdiscKind, "generic">, ReviewFlagPreset> = {
    chat: {
      kind: "chat",
      level: "doubt",
      proofStrength: "弱",
      issues: [
        "未经公证的即时通信记录：需核对原始载体（原始手机或完整导出件）",
        "能否以其他证据（转账流水、书面确认等）印证，尚待逐段核查",
        "是否需要申请电子数据鉴定，由律师结合争议金额与对抗强度判断",
      ],
      supports: [],
      weakens: ["存在被截取、被删改或账号冒用的可能（真实性攻击预判：电子数据已被篡改方向）"],
      lawyerAction: "律师逐段过目后再定档；未经确认的标注不得作为行动依据",
      tags: ["存疑", "核实"],
    },
    statement: {
      kind: "statement",
      level: "doubt",
      proofStrength: "弱",
      issues: [
        "流水未经银行盖章或未从官方渠道调取的，真实性需补强",
        "对方账户与当事人身份的对应关系需要印证材料",
        "是否存在对方主张的还款、抵销等相反记录，需完整对读",
      ],
      supports: [],
      weakens: ["单方导出的流水存在选择性截取的可能"],
      lawyerAction: "律师核对每笔关键交易与待证事实的对应；必要时申请法院调取全程流水",
      tags: ["存疑", "核实"],
    },
    table: {
      kind: "table",
      level: "doubt",
      proofStrength: "弱",
      issues: [
        "自制表格属于单方整理材料，需回到其底层原始凭证核对",
        "表格行列与原件的对应关系需逐行抽查勾稽",
      ],
      supports: [],
      weakens: ["单方制表存在选择性录入的可能"],
      lawyerAction: "律师确认底稿来源并抽查勾稽后定档",
      tags: ["存疑", "核实"],
    },
  };
  return base[kind as Exclude<EdiscKind, "generic">] ?? {
    kind: "generic",
    level: "doubt",
    proofStrength: "弱",
    issues: ["电子数据来源形式未定，先按未经公证的存疑档处理"],
    supports: [],
    weakens: [],
    lawyerAction: "律师过目定档",
    tags: ["存疑"],
  };
}

// ── 候选证据清单（D1/D3）──
export interface CandidateAnchor {
  kind: "rows" | "block";
  sourceId: string;
  label: string; // 人读引用串（行区间三件套或页/块锚）
  rows?: { tableName: string; rowStart: number; rowEnd: number };
  block?: { page: number; seq: number };
}

export interface CandidateDraft {
  category: string;
  sourceId: string;
  sourceName: string;
  classIds: string[];
  anchors: CandidateAnchor[];
  title: string;
  suggestionLevel: "suggested";
}

/** 从人工归类聚合候选（D1：只聚合已归类行——归类是人工动作，工具不自动归类） */
export function aggregateCandidates(
  classifications: { classId: string; sourceId: string; sourceName: string; category: string; refs: { tableName: string; rowStart: number; rowEnd: number }[] }[],
): CandidateDraft[] {
  const byKey = new Map<string, { category: string; sourceId: string; sourceName: string; classIds: string[]; refs: { tableName: string; rowStart: number; rowEnd: number }[] }>();
  for (const c of classifications) {
    const key = `${c.category}\u0000${c.sourceId}`;
    let g = byKey.get(key);
    if (!g) {
      g = { category: c.category, sourceId: c.sourceId, sourceName: c.sourceName, classIds: [], refs: [] };
      byKey.set(key, g);
    }
    g.classIds.push(c.classId);
    g.refs.push(...c.refs);
  }
  return [...byKey.values()].map((g) => {
    const ranges = g.refs.map((r) => `${r.tableName}第${r.rowStart}-${r.rowEnd}行`).join("、");
    return {
      category: g.category,
      sourceId: g.sourceId,
      sourceName: g.sourceName,
      classIds: g.classIds,
      anchors: g.refs.map((r): CandidateAnchor => ({
        kind: "rows",
        sourceId: g.sourceId,
        label: `${g.sourceName} ${r.tableName}第${r.rowStart}-${r.rowEnd}行`,
        rows: { tableName: r.tableName, rowStart: r.rowStart, rowEnd: r.rowEnd },
      })),
      title: `${g.category} · ${g.sourceName}（${ranges}）`,
      suggestionLevel: "suggested" as const,
    };
  });
}

// ── 校验（D2/G6：清单项 ↔ 源行/页锚一一对应，缺漏可读指出）──
export interface VerifyProblem {
  ref: string;
  issue: string;
}
export interface VerifyResult {
  ok: boolean;
  checked: number;
  problems: VerifyProblem[];
  /** 引用回跳一致性：报告内引用锚经解析器回读，文本一致方计入（验收口径：回跳一致才算数） */
  backjumpChecked: number;
  backjumpMismatched: number;
}

/** 校验纯逻辑：resolver 由服务层注入（查源/查行/查块）。失败不静默，逐条可读差异。 */
export function verifyCandidates(
  candidates: { candidateId: string; title: string; anchors: CandidateAnchor[]; status: string }[],
  resolve: {
    sourceHash: (sourceId: string) => { fileHash: string } | null;
    rowExists: (sourceId: string, tableName: string, rowNo: number) => { fileHash: string } | null;
    blockExists: (sourceId: string, page: number, seq: number) => { fileHash: string } | null;
  },
  backjump: (a: CandidateAnchor) => { text: string } | null,
  expectedTexts: { anchor: CandidateAnchor; expectText: string }[] = [],
): VerifyResult {
  const problems: VerifyProblem[] = [];
  let checked = 0;
  for (const c of candidates) {
    if (!c.anchors.length) {
      problems.push({ ref: c.title, issue: "候选没有任何引用锚，无法回溯到原文" });
      continue;
    }
    for (const a of c.anchors) {
      checked += 1;
      const src = resolve.sourceHash(a.sourceId);
      if (!src) { problems.push({ ref: a.label, issue: `引用的源 ${a.sourceId} 不存在或已被移除` }); continue; }
      if (!src.fileHash) { problems.push({ ref: a.label, issue: "源未完成入册哈希（粗扫态不可作取证引用）" }); continue; }
      if (a.kind === "rows" && a.rows) {
        for (let no = a.rows.rowStart; no <= a.rows.rowEnd; no++) {
          const row = resolve.rowExists(a.sourceId, a.rows.tableName, no);
          if (!row) { problems.push({ ref: a.label, issue: `第 ${no} 行不存在（行区间与源现状不符）` }); break; }
          if (row.fileHash !== src.fileHash) { problems.push({ ref: a.label, issue: `第 ${no} 行的锚哈希与源哈希不一致（锚不变式破坏）` }); break; }
        }
      } else if (a.kind === "block" && a.block) {
        const blk = resolve.blockExists(a.sourceId, a.block.page, a.block.seq);
        if (!blk) { problems.push({ ref: a.label, issue: `页 ${a.block.page} 块序 ${a.block.seq} 不存在` }); continue; }
        if (blk.fileHash !== src.fileHash) { problems.push({ ref: a.label, issue: "块锚哈希与源哈希不一致（锚不变式破坏）" }); continue; }
      }
    }
  }
  let backjumpChecked = 0;
  let backjumpMismatched = 0;
  for (const e of expectedTexts) {
    const hit = backjump(e.anchor);
    backjumpChecked += 1;
    if (!hit || hit.text !== e.expectText) {
      backjumpMismatched += 1;
      problems.push({ ref: e.anchor.label, issue: "引用回跳原文不一致（引用文字与锚处原文不符）" });
    }
  }
  return { ok: problems.length === 0, checked, problems, backjumpChecked, backjumpMismatched };
}

// ── 审查报告（F12 七节，结构等量、措辞全自写；F10 律师闸随报告输出）──
export interface ReportInput {
  caseId: string;
  facts?: string[];        // F1 已登记待证事实（无则回退归类类目代位+显式声明）
  categories: string[];    // 归类类目（facts 为空时作工作底稿代位；待证事实上游提炼属 #34/#7 链）
  candidates: { title: string; status: string; confirmedBy?: string | null; anchors: CandidateAnchor[]; formal?: FormalElementCheck }[];
  flags: { targetLabel: string; kind: string; level: FlagLevel; issues: string[]; lawyerAction: string; tags: string[] }[];
  triples?: { targetLabel: string; findings: TripleFinding[] }[]; // F4 三性评估（逐项结论+理由）
  gaps?: Array<Pick<GapSuggestion, "kind" | "factText" | "suggestion" | "sourceChannel" | "difficulty" | "deadlineNote">>;
  verify: VerifyResult;
}

export function buildReviewReport(input: ReportInput): string {
  const L: string[] = [];
  const doubt = input.flags.filter((f) => f.level === "doubt");
  const insuff = input.flags.filter((f) => f.level === "insufficient");
  const confirmed = input.candidates.filter((c) => c.status === "confirmed");
  const facts = (input.facts ?? []).filter((t) => String(t ?? "").trim());
  const gaps = input.gaps ?? [];
  const triples = input.triples ?? [];
  const tripleLine = (t: { targetLabel: string; findings: TripleFinding[] }) =>
    `- ${t.targetLabel}：${t.findings.map((a) => `${a.attr}=${a.conclusion}${a.reason ? `（${a.reason}）` : ""}`).join("，")}`;
  L.push(`# 电子数据初步审查工作底稿（案件 ${input.caseId}）`);
  L.push("");
  L.push("> 定位：初步审查。全部存疑与不足标注须经律师逐项过目方可作为行动依据，本底稿无豁免通道。");
  L.push("> 原始载体请妥为保留（原始手机、原始导出件、原始流水介质）；本底稿的任何整理动作都不改动原件。");
  L.push("");
  L.push("## 一、待证事实");
  if (facts.length) {
    L.push(`先行登记的待证事实（自诉求与争点提炼，归人判断；${FACT_EXCLUSION_NOTE}）：`);
    L.push(facts.map((t, i) => `${i + 1}. ${t}`).join("\n"));
  } else {
    L.push("本版以待证事实清单上游输入为前置（由案情梳理线提供）。当前工作底稿以人工归类类目代位记录：");
    L.push(input.categories.length ? input.categories.map((c) => `- ${c}`).join("\n") : "-（尚未建立归类）");
  }
  L.push("");
  L.push("## 二、证据清单（候选）");
  L.push(confirmed.length
    ? confirmed.map((c) => {
        const formal = c.formal
          ? `｜形式六要素：${c.formal.complete ? "齐备" : `待补齐（${c.formal.missing.join("、")}，先补齐再实质审查）`}`
          : "｜形式六要素：未登记";
        return `- ${c.title}｜确认人：${c.confirmedBy ?? ""}｜引用锚 ${c.anchors.length} 处${formal}`;
      }).join("\n")
    : "-（尚无经确认的候选；未确认候选不进入正式清单）");
  const unconfirmed = input.candidates.filter((c) => c.status !== "confirmed");
  if (unconfirmed.length) {
    L.push("");
    L.push(`另有 ${unconfirmed.length} 项候选待确认（建议档，未列正文）。`);
  }
  L.push("");
  L.push("## 三、存疑标注清单");
  L.push(doubt.length
    ? doubt.map((f) => `- ${f.targetLabel}（${f.kind}）：${f.issues.join("；")}→ ${f.lawyerAction}`).join("\n")
    : "-（无）");
  if (triples.length) {
    L.push("");
    L.push("三性评估（逐项结论与理由）：");
    L.push(triples.map(tripleLine).join("\n"));
  }
  L.push("");
  L.push("## 四、不足记录（只记录，不执行排除）");
  L.push(insuff.length
    ? insuff.map((f) => `- ${f.targetLabel}：${f.issues.join("；")}`).join("\n")
    : "-（无）");
  L.push("");
  L.push("## 五、缺口与补充建议");
  if (gaps.length) {
    L.push(gaps.map((g) => `- ${formatGapLine(g)}`).join("\n"));
  } else {
    L.push("-（尚未登记结构化缺口）通用提示：未经公证的电子数据优先补充可印证材料；印证不足的评估电子数据鉴定必要性与举证期限，逾期风险单独提示。");
  }
  L.push("");
  L.push("## 六、质证预判");
  L.push("- 真实性方向：对方可能主张记录被截取、删改或账号非本人使用；应对=完整载体+交叉印证。");
  L.push("- 合法性方向：核对取证的程序来源；个人自助取证一般可用，但需说明取得方式。");
  L.push("- 关联性方向：逐段对应待证事实，删除与争点无关段落须经律师确认。");
  L.push("");
  L.push("## 七、规律性观察");
  if (doubt.length) {
    L.push(`- 本案 ${doubt.length} 项电子数据标注均未经公证，属同类集中存疑：可作为单一决定点统一处理（一次公证/鉴定评估覆盖全批）。`);
  } else {
    L.push("-（暂无同类集中存疑）");
  }
  L.push("");
  L.push("## 引用核实（双轮记录）");
  L.push(`- 引用锚共校验 ${input.verify.checked} 处；回跳核验 ${input.verify.backjumpChecked} 处，不一致 ${input.verify.backjumpMismatched} 处。`);
  if (input.verify.problems.length) {
    L.push("- 未能核实项（不得写成已确认）：");
    L.push(input.verify.problems.map((p) => `  · ${p.ref}：${p.issue}`).join("\n"));
  } else {
    L.push("- 全部引用锚回跳一致。");
  }
  L.push(`- 规则引用来源标签：本底稿规则句来源=${ruleSourceLabel("自写预置")}（未引外部来源即如实标注）。${SOURCE_LABEL_DISCIPLINE}`);
  L.push("");
  L.push("---");
  L.push("局限声明：本底稿不替代质证策略，不作证据充分性终局判断，不排除任何证据，不捏造法条与案例；法规适用以法源线现行版本核验为准。");
  L.push("保密继承：本底稿继承所引全部来源材料的保密属性；来源材料属保密的，本底稿随源保密，对外分发前须承办律师确认分发范围。");
  return L.join("\n");
}
