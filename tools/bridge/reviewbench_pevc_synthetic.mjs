// 吸收件转写·pe-vc 合成自测（规格=竞品情报/2026-10-29-规格波/吸收件转写规格.md §四 A1/A2/A3/A4/A10 验收断言）。
// 全部合成材料（自写文本，零竞品条款/文案）；末行 PEVC_BENCH_SYNTH_PASS/FAIL，exit 0/1。
import { createHash } from "node:crypto";
import { markdownToLegalDocx, buildZip } from "./draft_docx.mjs";
import { parseZip } from "./skills_service.mjs";
import {
  trackReviewRound, mapDealPackage, classifyPackageFile,
  injectDocxComments, deliverCommentAnnotations,
  gateReviewCompletion, renderMarketDisclosure,
} from "./reviewbench_pevc_service.mjs";
import { listParagraphs } from "./docx_span_util.mjs";

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " ｜ " + detail : ""}`);
}
const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");
const NEGOTIATION_STATES = ["accepted", "partial", "rejected", "reopened", "new"];

// ── A1 多轮红线稿跟踪（规格断言 ①消失→accepted ②保留→rejected ③新现→new ④缺上一版→披露+零状态断言）──
const v1Md = [
  "# 合成增资协议第一轮稿",
  "回购条款：若公司未能在五年内完成合格上市，投资方有权要求创始人按投资款加计年息回购。",
  "优先清算权条款：公司发生清算事件时，投资方有权优先于普通股股东取得投资款返还。",
  "投资总额为人民币 1200 万元。",
].join("\n");
const v2Md = [
  "# 合成增资协议第二轮稿",
  "回购安排：回购触发情形由双方另行书面约定（第一轮回购条款整条换写）。",
  "优先清算权条款：公司发生清算事件时，投资方有权优先于普通股股东取得投资款返还。",
  "反稀释条款：后续融资估值低于本轮时，投资方有权按加权平均法调整持股数量。",
  "投资总额为人民币 1200 万元。",
].join("\n");
const v1 = markdownToLegalDocx(v1Md);
const v2 = markdownToLegalDocx(v2Md);
const priorLedger = [
  { issue_id: "R-001", problem_text: "回购条款：若公司未能在五年内完成合格上市", status: "open" },
  { issue_id: "R-002", problem_text: "优先清算权条款：公司发生清算事件时", status: "open" },
];
const round = trackReviewRound({
  currentDocx: v2, previousDocx: v1, priorLedger,
  currentFindings: [{ problem_text: "反稀释条款", note: "本轮新发现" }],
});
const st = (id) => round.entries.find((e) => e.issue_id === id)?.status;
check("A1① 问题文本在 v2 消失 → accepted", st("R-001") === "accepted", `R-001=${st("R-001")}`);
check("A1② 问题文本在 v2 保留 → rejected（非 open）", st("R-002") === "rejected", `R-002=${st("R-002")}`);
check("A1③ v2 新现 → new 且跨轮 id 稳定递增", st("R-003") === "new" && round.entries.find((e) => e.issue_id === "R-003")?.problem_text === "反稀释条款", JSON.stringify(round.counts));
check("A1 既有 id 全部保持稳定（跨轮不复读）", round.entries.filter((e) => ["R-001", "R-002"].includes(e.issue_id)).length === 2);

const noBase = trackReviewRound({
  currentDocx: v2, previousDocx: null, priorLedger,
  currentFindings: [{ problem_text: "反稀释条款" }],
});
check(
  "A1④ 缺上一版 → 含「无法判断接受状态」披露且零谈判状态断言",
  noBase.limitations.some((l) => l.includes("无法判断接受状态")) &&
    noBase.entries.every((e) => !NEGOTIATION_STATES.includes(e.status)),
  `limitations=${noBase.limitations.length}, states=${noBase.entries.map((e) => e.status).join("/")}`,
);

// ── A2 文件族地图＋候选冲突矩阵（规格断言：两处不一致带定位／一致零误报／改名负例正文定稿）──
const mainText = [
  "合成增资协议（主协议）",
  "第一条 投资总额为人民币 1200 万元，超出部分计入资本公积。",
  "第二条 投资方增资后持股比例为 10%。",
  "第三条 本协议项下争议由合成仲裁委员会仲裁解决。",
  "第四条 违约方应当承担违约责任。",
].join("\n");
const charterText = [
  "合成公司章程",
  "第五条 投资方增资后持股比例为 12%（与主协议记载不一致）。",
  "第六条 公司章程的修订须经股东会表决程序通过，董事会负责解释。",
  "第七条 相关争议由合成仲裁委员会仲裁解决。",
].join("\n");
const suppText = [
  "合成补充协议（一）",
  "第八条 主协议项下投资总额确认为人民币 1500 万元（与主协议正文不一致）。",
  "第九条 本补充协议作为主协议的补充，与其冲突时以本补充协议为准。",
  "第十条 相关争议由合成仲裁委员会仲裁解决。",
].join("\n");
const pkg = mapDealPackage([
  { name: "合成主协议.docx", text: mainText },
  { name: "合成公司章程.docx", text: charterText },
  { name: "合成补充协议.docx", text: suppText },
]);
const conflictFields = pkg.conflicts.map((c) => c.field).sort();
check("A2① 金额与股比两处不一致进候选冲突清单", conflictFields.join(",") === "amount,equity_ratio", `fields=${conflictFields.join(",")}`);
const amountConflict = pkg.conflicts.find((c) => c.field === "amount");
check(
  "A2① 冲突带文件＋条款定位",
  !!amountConflict && amountConflict.values.length === 2 && amountConflict.values.every((v) => (v.clause || v.paraIndex) && v.file),
  JSON.stringify(amountConflict?.values?.map((v) => ({ f: v.file, c: v.clause, n: v.normalized }))),
);
check(
  "A2② 一致字段零误报（governing 一致不进冲突清单）",
  !pkg.conflicts.some((c) => c.field === "governing") && pkg.consistent.some((c) => c.field === "governing"),
  `consistent=${pkg.consistent.map((c) => c.field).join(",")}`,
);
const renamed = classifyPackageFile("协议.docx", charterText);
check("A2③ 文件名误导负例：正文证据定稿（章程改名后仍判 charter）", renamed.role === "charter" && renamed.basis.includes("正文"), `role=${renamed.role} basis=${renamed.basis}`);

// ── A3 Word 原生批注通道（①源不变 ②commentsPart+文本+锚段 ③锚点重复报错 ④降级明示）──
const cMd = [
  "# 合成合同审阅稿",
  "第一条 标的与价款：本合同标的为合成演示服务，价款为人民币 30 万元。",
  "第二条 交付时间：乙方应于合同签订后 30 日内完成交付。",
  "第三条 违约责任：任何一方违约应赔偿守约方损失。",
].join("\n");
const cSrc = markdownToLegalDocx(cMd);
const srcBefore = sha256(cSrc);
const plan = [
  { anchor_text: "价款为人民币 30 万元", comment: "金额条款缺支付时点，建议补「验收后 10 个工作日内支付」。" },
  { anchor_text: "乙方应于合同签订后 30 日内完成交付", comment: "交付验收标准未定义，建议附验收单作为附件。" },
];
const injected = injectDocxComments(cSrc, plan);
check("A3① 源文件 sha256 前后一致（输出另存语义）", sha256(cSrc) === srcBefore && !injected.equals(cSrc), `src=${srcBefore.slice(0, 12)}…`);
const outEntries = parseZip(injected);
const commentsXml = outEntries.get("word/comments.xml")?.toString("utf8") ?? "";
const outXml = outEntries.get("word/document.xml").toString("utf8");
check("A3② commentsPart 存在且 comment 文本=计划文本", commentsXml.includes("<w:comment ") && plan.every((p) => commentsXml.includes(p.comment)));
const outParas = listParagraphs(outXml);
const anchorPara = outParas.find((p) => p.text.includes("价款为人民币 30 万元"));
check(
  "A3② commentRange/Reference 锚定段落正确",
  !!anchorPara && anchorPara.inner.includes('<w:commentRangeStart w:id="0"/>') && anchorPara.inner.includes('<w:commentReference w:id="0"/>'),
);
check(
  "A3② 段落纯文本零丢失（span 拆分不变式）",
  outParas.map((p) => p.text).join("\n") === listParagraphs(parseZip(cSrc).get("word/document.xml").toString("utf8")).map((p) => p.text).join("\n"),
);
let dupThrew = null;
try {
  injectDocxComments(markdownToLegalDocx(["# 双锚文档", "甲方应在 30 日内付款。", "乙方也应在 30 日内备货。"].join("\n")), [{ anchor_text: "30 日内", comment: "重复锚" }]);
} catch (e) { dupThrew = e; }
check("A3③ 锚点出现两次 → fail-fast 报错不落批注", dupThrew?.code === "ANCHOR_NOT_UNIQUE" && /2 次|两次|不唯一/.test(dupThrew.message), `code=${dupThrew?.code}`);
const degraded = deliverCommentAnnotations(Buffer.from("这不是一个docx压缩包", "utf8"), plan);
check(
  "A3④ 依赖不可用 → 降级为批注计划文本且明示未生成原生批注",
  degraded.mode === "plan-text" && degraded.notice.includes("未生成原生批注") && degraded.planText.includes("价款为人民币 30 万元") && degraded.bytes === null,
);
// 多 run 段内锚点（拆 run 路径）：手造 document.xml，锚点跨 run 边界
const multiRunDoc = buildZip([
  { name: "[Content_Types].xml", data: Buffer.from('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>', "utf8") },
  { name: "word/document.xml", data: Buffer.from(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' +
    '<w:p><w:r><w:rPr><w:rFonts w:ascii="宋体" w:eastAsia="宋体" w:hAnsi="宋体"/></w:rPr><w:t>分期付款：</w:t></w:r>' +
    '<w:r><w:rPr><w:rFonts w:ascii="宋体" w:eastAsia="宋体" w:hAnsi="宋体"/></w:rPr><w:t>首付三成，</w:t></w:r>' +
    '<w:r><w:rPr><w:rFonts w:ascii="宋体" w:eastAsia="宋体" w:hAnsi="宋体"/></w:rPr><w:t xml:space="preserve">余款一年内付清。</w:t></w:r></w:p>' +
    "</w:body></w:document>", "utf8") },
]);
const multiInjected = injectDocxComments(multiRunDoc, [{ anchor_text: "首付三成，余款一年内付清", comment: "分期安排缺每期时点。" }]);
const multiXml = parseZip(multiInjected).get("word/document.xml").toString("utf8");
const multiPara = listParagraphs(multiXml)[0];
check(
  "A3+ 跨 run 锚点可注入且文本不变",
  multiPara.inner.includes('w:id="0"') && multiPara.text === "分期付款：首付三成，余款一年内付清。",
  `text=${multiPara.text}`,
);

// ── A4 审阅完成门禁三态（①指纹篡改→blocked ②缺终态→blocked ③限制→首页披露 ④全绿→passed）──
const mkReview = (over = {}) => ({
  sources: [
    { path: "main.docx", expectedSha256: sha256(Buffer.from("main-v2-bytes")), actualBytes: Buffer.from("main-v2-bytes") },
    { path: "charter.docx", expectedSha256: sha256(Buffer.from("charter-v2-bytes")), actualBytes: Buffer.from("charter-v2-bytes") },
    { path: "supp.docx", expectedSha256: sha256(Buffer.from("supp-v2-bytes")), actualBytes: Buffer.from("supp-v2-bytes") },
  ],
  stages: [
    { name: "文本提取", finalState: "completed" },
    { name: "整套矩阵勾稽", finalState: "completed" },
    { name: "市场数据查询", finalState: "not_applicable" },
  ],
  artifacts: [{ path: "问题清单.csv", exists: true }],
  judgments: [
    { gate: "事项与权威", result: "pass" },
    { gate: "实质覆盖", result: "pass" },
    { gate: "高风险抽查", result: "pass" },
    { gate: "交付与保密", result: "pass" },
  ],
  ...over,
});
const tampered = mkReview({ sources: mkReview().sources.map((s, i) => i === 1 ? { ...s, actualBytes: Buffer.from("charter-TAMPERED") } : s) });
const g1 = gateReviewCompletion(tampered);
check("A4① 指纹篡改 → blocked 且禁完成表述", g1.status === "blocked" && /禁止任何完成表述|禁止作任何完成表述/.test(g1.statement), `status=${g1.status}`);
const missingStage = mkReview({ stages: [{ name: "文本提取", finalState: "completed" }, { name: "整套矩阵勾稽", finalState: null }, { name: "市场数据查询", finalState: "not_applicable" }] });
const g2 = gateReviewCompletion(missingStage);
check("A4② 缺任一阶段终态 → blocked", g2.status === "blocked" && g2.failures.some((f) => f.check.includes("整套矩阵勾稽")));
const withLimit = mkReview({ judgments: [
  { gate: "事项与权威", result: "pass" },
  { gate: "实质覆盖", result: "limitation", note: "附件二为扫描件，OCR 未完成，该部分未实质审阅" },
  { gate: "高风险抽查", result: "pass" },
  { gate: "交付与保密", result: "pass" },
] });
const g3 = gateReviewCompletion(withLimit);
check("A4③ 判断门带限制 → passed_with_limitations 且输出含首页披露段", g3.status === "passed_with_limitations" && g3.disclosure.includes("首页披露") && g3.disclosure.includes("附件二为扫描件"));
const g4 = gateReviewCompletion(mkReview());
check("A4④ 全绿 → passed", g4.status === "passed" && g4.failures.length === 0);

// ── A10 市场比例披露纪律（整数+限定词／分区零混入／精确值须附期间边界／不披露来源名）──
const stats = [
  { topic: "合成样本中约定回购触发条款的比例", precisePercent: 23.7, samplePeriod: "2025 年合成样本期", boundary: "仅境内人民币架构合成样本", sourceName: "内部合成统计库甲" },
  { topic: "合成样本中出现一票否决权的比例", precisePercent: 0.3, samplePeriod: "2025 年合成样本期", boundary: "仅境内人民币架构合成样本", sourceName: "内部合成统计库乙" },
];
const legal = "法律结论区：本条回购安排在合成样本规则下的效力与履行风险判断（合成文本，与市场数据无关）。";
const pub = renderMarketDisclosure({ stats, legalConclusion: legal });
check("A10① 对外渲染整数百分比＋限定词（无小数位）", pub.rendered.includes("约 24%") && pub.rendered.includes("不足 1%") && !/\d+\.\d+%/.test(pub.rendered), pub.marketBlock.replace(/\n/g, " "));
check("A10② 法律结论区零市场数据混入（原样分区）", pub.legalBlock === legal && !pub.legalBlock.includes("24%"));
check("A10+ 统计来源名不进任何输出区", !pub.rendered.includes("内部合成统计库"));
const precise = renderMarketDisclosure({ stats, legalConclusion: legal, requestPrecise: true });
check("A10③ 索要精确值 → 附样本期间与边界声明", precise.rendered.includes("23.7%") && precise.rendered.includes("样本期间：2025 年合成样本期") && precise.rendered.includes("边界：仅境内人民币架构合成样本"));

// ── 收口 ──
const failed = results.filter((r) => !r.ok);
console.log(`PE 合成自测：${results.length - failed.length}/${results.length} 过`);
console.log(failed.length ? "PEVC_BENCH_FAIL" : "PEVC_BENCH_SYNTH_PASS");
process.exit(failed.length ? 1 : 0);
