// 吸收件转写·contract-review-3 合成自测（规格=竞品情报/2026-10-29-规格波/吸收件转写规格.md §四 A5/A6/A7/A8/A9 验收断言）。
// 全部合成材料（自写文本，零竞品条款/文案/词表）；末行 CR3_BENCH_SYNTH_PASS/FAIL，exit 0/1。
import { createHash } from "node:crypto";
import { markdownToLegalDocx, buildZip } from "./draft_docx.mjs";
import { parseZip } from "./skills_service.mjs";
import {
  buildRevisionRenderPlan, applyRevisionRenderPlan, replayRevisionArchive,
  extractDocxRevisionTexts, judgeFeedbackRound, reweightHighRejectChapters, EMPTY_REVISION_EXIT_CODE,
  createReviewLedger, loadReviewLedger,
  renderFontSafeDocx, checkFontDualChannel, findBoldRunTexts,
  validateRulePack, classifyContractType,
} from "./reviewbench_cr3_service.mjs";

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " ｜ " + detail : ""}`);
}
const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");
const W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';
function rawDocx(bodyXml) {
  return buildZip([
    { name: "[Content_Types].xml", data: Buffer.from('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>', "utf8") },
    { name: "word/document.xml", data: Buffer.from(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document ${W}><w:body>${bodyXml}</w:body></w:document>`, "utf8") },
  ]);
}
const p = (t) => `<w:p><w:r><w:t xml:space="preserve">${t}</w:t></w:r></w:p>`;
const del = (id, t) => `<w:del w:id="${id}" w:author="合成对方" w:date="2026-10-30T00:00:00Z"><w:r><w:delText xml:space="preserve">${t}</w:delText></w:r></w:del>`;
const ins = (id, runs) => `<w:ins w:id="${id}" w:author="合成对方" w:date="2026-10-30T00:00:00Z">${runs.map((t) => `<w:r><w:t xml:space="preserve">${t}</w:t></w:r>`).join("")}</w:ins>`;

// ── A5 账本→render plan→确定性落痕（①仅 confirmed 非谈判落痕 ②del/ins 文本+Word 兼容 ③其余零落痕 ④归档重放一致 ⑤目标缺失报错）──
const srcMd = [
  "# 合成购销合同（待修订稿）",
  "第一条 付款时间为合同签订后 60 日内，逾期按日计收滞纳金。",
  "第二条 质量标准以双方确认的技术附件为准。",
  "第三条 本合同项下争议由合成市人民法院管辖。",
].join("\n");
const srcDoc = markdownToLegalDocx(srcMd);
const srcHash = sha256(srcDoc);
const ledger5 = [
  { id: "L-001", status: "confirmed", needs_negotiation: false, chapter: "价款与支付", target_text: "付款时间为合同签订后 60 日内", replacement_text: "验收合格后 10 个工作日内付款" },
  { id: "L-002", status: "confirmed", needs_negotiation: true, chapter: "违约责任", target_text: "逾期按日计收滞纳金", replacement_text: "逾期按同期贷款市场报价利率支付违约金" },
  { id: "L-003", status: "pending", chapter: "争议解决", target_text: "由合成市人民法院管辖", replacement_text: "提交合成仲裁委员会仲裁" },
];
const plan5 = buildRevisionRenderPlan(ledger5);
check("A5① plan 只收 confirmed 且非需谈判条目（仅第 1 条）", plan5.items.length === 1 && plan5.items[0].issue_id === "L-001", `items=${plan5.items.map((i) => i.issue_id).join(",")}`);
const applied5 = applyRevisionRenderPlan(srcDoc, plan5);
const outXml5 = parseZip(applied5.bytes).get("word/document.xml").toString("utf8");
const delTexts = [...outXml5.matchAll(/<w:delText(?:\s[^>]*)?>([\s\S]*?)<\/w:delText>/g)].map((m) => m[1]);
const insTexts = [...outXml5.matchAll(/<w:ins\b[\s\S]*?<\/w:ins>/g)].map((m) => m[0]);
check(
  "A5② <w:del> 文本=目标原文且 w:ins 含替换文本（Word 兼容 id/author/date）",
  delTexts.some((t) => t.includes("付款时间为合同签订后 60 日内")) &&
    insTexts.length === 1 && insTexts[0].includes("验收合格后 10 个工作日内付款") &&
    /<w:del w:id="\d+" w:author="[^"]+" w:date="[^"]+">/.test(outXml5) && /<w:ins w:id="\d+" w:author="[^"]+" w:date="[^"]+">/.test(outXml5),
);
check(
  "A5③ needs_negotiation/pending 两条零落痕（正文原样、无 del 包裹）",
  outXml5.includes("逾期按日计收滞纳金") && !/<w:delText[^>]*>[^<]*逾期按日计收滞纳金/.test(outXml5) &&
    outXml5.includes("由合成市人民法院管辖") && !/<w:delText[^>]*>[^<]*合成市人民法院/.test(outXml5),
);
check("A5+ 源字节零改动（输出另存语义）", sha256(srcDoc) === srcHash);
check(
  "A5④ plan 归档在且重放结果字节一致",
  !!applied5.planArchive && JSON.parse(applied5.planArchive).applyLog.length === 1 &&
    replayRevisionArchive(srcDoc, applied5.planArchive).bytes.equals(applied5.bytes),
);
let notFound = null;
try {
  applyRevisionRenderPlan(srcDoc, { items: [{ issue_id: "L-009", target_text: "本条文本不存在于任何段落", replacement_text: "x" }] });
} catch (e) { notFound = e; }
check("A5⑤ 目标文本不在段落中 → 报错不静默", notFound?.code === "TARGET_NOT_FOUND", `code=${notFound?.code}`);

// ── A6 反馈闭环边角＋反哺（①三态 ②跨 run 不误判驳回 ③空修订专用退出码+零统计 ④历史常驳回标注）──
const ledger6 = [
  { id: "L-001", chapter: "价款与支付", target_text: "付款时间为合同签订后 60 日内", replacement_text: "验收合格后 10 个工作日内付款" },
];
// 正常接受：直接用 A5 的落痕产物当「对方全盘接受后的定稿」
const finalAccept = applied5.bytes;
const j1 = judgeFeedbackRound({ finalDocx: finalAccept, ledger: ledger6 });
check("A6①a 修订与建议一致 → accepted", j1.guard === null && j1.judgments[0]?.verdict === "accepted", j1.judgments?.[0]?.verdict);
// 跨 run 拆分：替换文本被拆成 3 个 run，拼接全文仍命中
const finalCrossRun = rawDocx(
  p("第一条 ") + del(1, "付款时间为合同签订后 60 日内") + ins(2, ["验收合格后 ", "10 个", "工作日内付款"]) + p("。"),
);
const j2 = judgeFeedbackRound({ finalDocx: finalCrossRun, ledger: ledger6 });
check("A6② 跨 run 拆分按拼接全文匹配 → accepted 不误判驳回", j2.judgments[0]?.verdict === "accepted", j2.judgments?.[0]?.verdict);
// 原文保留=驳回（他处有修订标记，本条未动）
const finalReject = rawDocx(p("第一条 付款时间为合同签订后 60 日内，逾期按日计收滞纳金。") + p("第五条 ") + ins(3, ["双方各执一份。"]));
const j3 = judgeFeedbackRound({ finalDocx: finalReject, ledger: ledger6 });
check("A6①b 原文保留 → rejected", j3.judgments[0]?.verdict === "rejected", j3.judgments?.[0]?.verdict);
// 改了但不是建议文本 → partial
const finalPartial = rawDocx(p("第一条 ") + del(4, "付款时间为合同签订后 60 日内") + ins(5, ["付款安排由双方另行协商确定"]) + p("。"));
const j4 = judgeFeedbackRound({ finalDocx: finalPartial, ledger: ledger6 });
check("A6①c 换写（有改动但不符建议） → partial", j4.judgments[0]?.verdict === "partial", j4.judgments?.[0]?.verdict);
// 空修订守卫：无任何 w:ins/w:del → 专用退出码 + 零统计写入
const statsSink = [];
const j5 = judgeFeedbackRound({ finalDocx: srcDoc, ledger: ledger6, statsCollector: statsSink });
check(
  "A6③ 空修订 → 专用退出码且 stats 零写入",
  j5.guard === "empty-revision" && j5.exitCode === EMPTY_REVISION_EXIT_CODE && j5.judgments.length === 0 && statsSink.length === 0,
  `guard=${j5.guard} exit=${j5.exitCode} stats=${statsSink.length}`,
);
// 正常轮统计可写
const statsAll = [];
judgeFeedbackRound({ finalDocx: finalReject, ledger: ledger6, statsCollector: statsAll });
check("A6+ 非空修订轮正常累计章节统计", statsAll.length === 1 && statsAll[0].rejected === 1);
// ④ 两轮高驳回 → 历史常驳回标注+下轮降级
const rounds = [
  { chapterStats: [{ chapter: "违约责任", accepted: 1, rejected: 3, partial: 0 }] },
  { chapterStats: [{ chapter: "违约责任", accepted: 1, rejected: 3, partial: 0 }] },
];
const reweighted = reweightHighRejectChapters(rounds);
check(
  "A6④ 高驳回章节（≥0.6 我方自定阈值）→ 「历史常驳回」标注+下轮降级",
  reweighted.length === 1 && reweighted[0].chapter === "违约责任" && reweighted[0].downgradeNextRound === true && reweighted[0].hint.includes("历史常驳回"),
  JSON.stringify(reweighted.map((r) => ({ ch: r.chapter, rate: r.rejectRate }))),
);
const reweightedLow = reweightHighRejectChapters([{ chapterStats: [{ chapter: "管辖", accepted: 4, rejected: 1, partial: 0 }] }]);
check("A6+ 低驳回章节不降级（阈值内零误伤）", reweightedLow.length === 0);

// ── A7 审查台账形状（①id 复用检测 ②dismissed 保留可查 ③冲突双向检索 ④损坏重建明示重置）──
const led = createReviewLedger();
const e1 = led.add({ chapter: "管辖", finding: "管辖条款与仲裁条款并存", risk_level: "high" });
const e2 = led.add({ chapter: "保密", finding: "保密期限未约定", risk_level: "medium" });
led.setStatus(e2.id, "dismissed", "经复核属商业惯例，驳回");
const e3 = led.add({ chapter: "管辖", finding: "管辖法院与合同履行地不一致", risk_level: "medium" });
led.setStatus(e1.id, "confirmed");
led.link(e1.id, e3.id, "conflicts");
let idReuse = null;
try { led.add({ id: e1.id, chapter: "x", finding: "故意复用 id" }); } catch (err) { idReuse = err; }
check("A7① 显式复用既有 id → 拒绝（id 单调不复用）", idReuse?.code === "LEDGER_ID_REUSED", `code=${idReuse?.code}`);
check("A7② dismissed 记录保留仍可查（只进不删）", led.query({ status: "dismissed" }).some((x) => x.id === e2.id) && led.entries.length === 3);
check(
  "A7③ 冲突关系双向检索（从 L-003 反查到 L-001）",
  led.query({ relatedTo: e3.id }).some((x) => x.id === e1.id) && led.query({ relatedTo: e1.id }).some((x) => x.id === e3.id),
);
let badTrans = null;
try { led.setStatus(e2.id, "confirmed", "终态后再流转"); } catch (err) { badTrans = err; }
check("A7+ 四态流转表：dismissed 终态不可再流转", badTrans?.code === "LEDGER_BAD_TRANSITION");
const broken = loadReviewLedger('{"entries": [ 这不是合法JSON');
check("A7④ 损坏 JSON → 重建且明示「台账已重置」", broken.reset === true && broken.resetNotice.includes("台账已重置") && broken.ledger.entries.length === 0);
const good = loadReviewLedger(led.toJSON());
check("A7+ 正常往返（toJSON→load 保条目）", good.reset === false && good.ledger.entries.length === 3);

// ── A8 中文 docx 字体双通道（每 Run 三通道同值＋加粗仅限标题/编号/风险标识；XML 机检）──
const fontDoc = renderFontSafeDocx({
  title: "合成审查意见书",
  blocks: [
    { type: "heading", text: "一、总体评价" },
    { type: "body", text: "付款条款 Payment Terms 需与交付里程碑挂钩（中英混排+标点。；、）测试双通道字体。" },
    { type: "risk", label: "【风险·高】", text: "付款条件缺失时点约束，可能造成回款周期失控。" },
  ],
});
const fontXml = parseZip(fontDoc).get("word/document.xml").toString("utf8");
const fontCheck = checkFontDualChannel(fontXml);
check("A8① 每个 w:r 双通道齐备且值一致（w:ascii/w:hAnsi/w:eastAsia）", fontCheck.runCount >= 5 && fontCheck.violations.length === 0, `runs=${fontCheck.runCount} violations=${fontCheck.violations.length}`);
const boldTexts = findBoldRunTexts(fontXml);
check(
  "A8② 加粗仅限标题/编号/风险标识（正文零局部加粗）",
  boldTexts.length === 3 && boldTexts.includes("合成审查意见书") && boldTexts.includes("一、总体评价") && boldTexts.includes("【风险·高】") && !boldTexts.some((t) => t.includes("Payment Terms")),
  JSON.stringify(boldTexts),
);
const badFontXml = '<w:r><w:rPr><w:rFonts w:ascii="宋体"/><w:b/></w:rPr><w:t>缺通道</w:t></w:r><w:r><w:rPr><w:rFonts w:ascii="宋体" w:hAnsi="Calibri" w:eastAsia="宋体"/></w:rPr><w:t>不一致</w:t></w:r>';
const badCheck = checkFontDualChannel(badFontXml);
check("A8+ 机检负例（缺通道/值不一致均可检出）", badCheck.violations.length === 2, JSON.stringify(badCheck.violations.map((v) => v.kind)));

// ── A9 分型规则包形状位（合成自写包 schema 过＋类型识别命中＋相似类型零误触；不对源料 21 包内容做断言）──
const loanPack = {
  type_id: "synthetic-loan",
  display_name: "合成借款合同（形状示例）",
  chapter_anchor: { code: "SYN-11", title: "合成合同编借款合同章（占位章锚，内容自写）" },
  essential_clauses: [
    { name: "借款金额与币种", legal_basis: "合成法源锚A（自写占位，第三方锚点零采用）", requirement: "写明本金数额与币种", importance: "core", keywords: ["借款金额", "本金"] },
    { name: "利率", legal_basis: "合成法源锚B", requirement: "约定利率且不得触碰上限（上限计算走九计算器过渡档，JC 完整档=修订中挂起）", importance: "core", keywords: ["利率", "利息"] },
    { name: "还款期限", legal_basis: "合成法源锚C", requirement: "写明还款期限与方式", importance: "core", keywords: ["还款期限", "分期还款"] },
  ],
  special_rules: ["涉利息计算一律走过渡档九计算器，标「JC 完整档=修订中挂起」"],
  penalty_provisions: [{ legal_basis: "合成法源锚D", rule: "逾期还款责任条款位（比例内容不采，数值走九计算器）" }],
  common_gaps: [{ issue: "缺提前还款约定", risk: "还款安排单方受制", suggestion: "补提前还款通知与费用条款" }],
};
const guaranteePack = {
  ...loanPack,
  type_id: "synthetic-guarantee",
  display_name: "合成保证合同（形状示例）",
  essential_clauses: [
    { name: "保证方式", legal_basis: "合成法源锚E", requirement: "一般保证或连带责任保证须写明", importance: "core", keywords: ["保证方式", "连带责任"] },
    { name: "保证期间", legal_basis: "合成法源锚F", requirement: "写明保证期间起算与长度", importance: "core", keywords: ["保证期间"] },
    { name: "保证范围", legal_basis: "合成法源锚G", requirement: "圈定主债权范围", importance: "core", keywords: ["保证范围"] },
  ],
};
const vLoan = validateRulePack(loanPack);
check("A9① 合成自写规则包 schema 校验过", vLoan.ok, vLoan.errors.join(";"));
const vBad = validateRulePack({ ...loanPack, chapter_anchor: null, essential_clauses: [] });
check("A9+ 负例（缺章锚点/必备条款空）可检出", !vBad.ok && vBad.errors.length >= 2, vBad.errors.join(";"));
const loanText = "本合同借款金额为人民币若干元，利率按合成口径约定，还款期限为十二个月，可分期还款。";
const guaranteeText = "保证方式为连带责任保证，保证期间为主债务履行期届满后六个月，保证范围包括主债权及合成费用。";
const cLoan = classifyContractType(loanText, [loanPack, guaranteePack]);
const cGuar = classifyContractType(guaranteeText, [loanPack, guaranteePack]);
check(
  "A9② 类型识别命中正确且相似类型零误触",
  cLoan.matched === "synthetic-loan" && cGuar.matched === "synthetic-guarantee" && cLoan.scored.find((s) => s.type_id === "synthetic-guarantee").score === 0,
  JSON.stringify({ loan: cLoan.scored, guar: cGuar.scored }),
);
const mixedText = "本合同约定借款金额、利率、保证方式与保证期间等内容（两类信号均衡）。";
const cMixed = classifyContractType(mixedText, [loanPack, guaranteePack]);
check("A9+ 分差不足不定型（不猜，留人工）", cMixed.matched === null && cMixed.reason.includes("分差不足"));

// ── 收口 ──
const failed = results.filter((r) => !r.ok);
console.log(`CR3 合成自测：${results.length - failed.length}/${results.length} 过`);
console.log(failed.length ? "CR3_BENCH_FAIL" : "CR3_BENCH_SYNTH_PASS");
process.exit(failed.length ? 1 : 0);
