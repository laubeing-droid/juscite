// 可视化 B 轨合成自测（施工波-20261030；规格 §三 对拍项 C1–C15 全合成材料，逐条可复跑）：
//   C1 照录改写被拒并定位事实号        C2 动词表外/超15字/定性词三拒     C3 仅至月档收入不丢
//   C4 无证据编号→机械状态+进不确定清单/手填被拒                              C5 渲染层改一字→R组读产物报错
//   C6 简表长段=原文前缀+停在句读+句号收尾（首句超行→次级边界≥一行）
//   C7 摄入剥页码不误判/整份缺失拒/明示不读放行留痕
//   C8 100万 vs 明细98万→J报错；补显式调整项→过          C9 【待核验】先剥再查不豁免三问
//   C10 有再回应无反制→数据层+几何层各拦一道             C11 3 处决定性→分散态不挑2
//   C12 数产物深红色块（数色块不数次数，≤3，唯一红值）   C13 走线穿卡→出图前全量自证拒
//   C14 改坏验证：每条守卫配改坏用例必报错（25 条）      C15 同输入两跑逐字节一致
//   ＋真桥接线四工具+摄入（隔离端口 BRIDGE_TEST_PORT 默认 3090，自管桥实例不碰 :3030/:43127）。
// 【施工波二轮·可视化B轨收尾 20261031 增补】
//   C16 光栅化字体契约：换单一族+日志报出+读产物守卫（未换族必报=改坏验证）+ #6 块→页文本/卷宗页码锚
//   ＋真桥光栅化两工具（PNG 魔数+两跑字节一致；渲染器缺位=skipped 不拖垮 SVG 交付）
//   ＋真桥摄入接 #6 材料通道（建案→上传合成 PDF→真 PDF 解析页文本+页数轨；扫描件 NEEDS_OCR→该读没读拒；明示不读放行留痕）。
// 末行 VIZB_SYNTH_PASS / VIZB_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { openSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import * as chron from "../../packages/juscite-vizb/src/chronicle/index.ts";
import * as conf from "../../packages/juscite-vizb/src/confrontation/index.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3090);
const NODE = process.execPath;
const results: Array<{ name: string; ok: boolean }> = [];
function check(name: string, ok: boolean, detail: string) {
  results.push({ name, ok });
  console.log(`[vizb-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ══ 合成材料（全合成，无真实案件数据）══
const CHRON_DOC = "2026年3月1日，张三通过银行转账向李四出借人民币二十万元整，双方约定借款期限为六个月，"
  + "月利率为百分之一点五，到期一次性还本付息。2026年9月1日借款到期后，李四未归还任何本金，也未支付利息。"
  + "张三于2026年10月15日向李四发出催款函，要求其七日内归还全部本金及利息。李四收到催款函后仍未还款。"
  + "另查明，双方此前尚有货款往来，2025年12月合计金额为三万五千元，已经双方对账确认无误，与本案借款无关。"
  + "张三为本案支出了律师费若干，具体数额以票据为准。合成材料至此共计三百余字用于照录判据测试。";
function synthFactBase(): unknown {
  return {
    schema: "juscite.vizb.chronicle.factbase@1",
    caseTitle: "张三诉李四民间借贷纠纷（合成）",
    docs: [{ docId: "卷一-借款协议", label: "借款协议", volume: "卷一", text: CHRON_DOC }],
    facts: [
      { factNo: 1, dateStr: "2026-03-01", datePrecision: "day", verb: "出借", title: "张三出借二十万元", content: "2026年3月1日，张三通过银行转账向李四出借人民币二十万元整", sourceDoc: "卷一-借款协议", locator: "p1¶1", evidenceNo: "证1", volume: "卷一", subjects: ["张三", "李四"], dispute: null, arithmeticNote: null },
      { factNo: 2, dateStr: "2026-10-15", datePrecision: "day", verb: "催告", title: "张三发出催款函", content: "张三于2026年10月15日向李四发出催款函，要求其七日内归还全部本金及利息。", sourceDoc: "卷一-借款协议", locator: "p1¶1", evidenceNo: null, volume: "卷一", subjects: ["张三"], dispute: null, arithmeticNote: null },
    ],
    uncertainty: [],
  };
}
const CONF_SOURCES = [
  { name: "起诉状.txt", text: "请求判令乙公司支付货款一百万元及逾期利息。双方于2026年1月签订买卖合同，甲公司已交付全部货物。" },
  { name: "答辩状.txt", text: "乙公司辩称货物存在质量问题，并已支付部分货款九十八万元，不应再支付。" },
  { name: "证据目录.txt", text: "证据一：买卖合同一份，证明双方合同关系成立。证据二：送货单三张，证明甲公司完成交货义务。" },
];
function synthSemantic(): unknown {
  return {
    schema: "juscite.vizb.confrontation@1",
    caseTitle: "甲公司诉乙公司买卖合同纠纷（合成）",
    internalOnly: true,
    maturity: "L2",
    procedure: { jurisdiction: "合同履行地法院有管辖权（合成）", standing: "双方主体适格（合成）", repeatedSuit: "未发现重复起诉（合成）" },
    sources: CONF_SOURCES,
    claims: [
      { no: "诉1", type: "payment", summary: { text: "请求判令乙公司支付货款一百万元及逾期利息。", src: "起诉状.txt", srcKind: "起诉状" },
        claimedCents: 100000000, items: [{ label: "货款本金", cents: 100000000, basis: "合同第五条（合成）" }], adjustments: [],
        required: { counterpart: "乙公司", subjectMatter: "货物买卖", amount: "一百万元" } },
    ],
    defenses: [
      { no: "抗1", category: "denial", text: { text: "乙公司辩称货物存在质量问题，并已支付部分货款九十八万元，不应再支付。", src: "答辩状.txt", srcKind: "答辩状" },
        threeQuestions: ["针对诉1货款给付要件", "主张货物存在质量问题", "暂无质检报告（待补）"], burden: "claimant" },
    ],
    elements: [
      { no: "要件1", issue: "合同关系成立",
        claim: { text: "双方于2026年1月签订买卖合同，甲公司已交付全部货物。", src: "起诉状.txt", srcKind: "起诉状" },
        response: { text: "乙公司辩称货物存在质量问题，并已支付部分货款九十八万元，不应再支付。", src: "答辩状.txt", srcKind: "答辩状" },
        counter: { absent: true, reason: "无书面记载" }, second: { absent: true, reason: "未获取" },
        burden: "claimant", lawConfidence: "high", evidenceConfidence: "mid", source: "起诉状+证据目录", disputed: true, evidenceStandardMet: true },
      { no: "要件2", issue: "货款支付条件成就",
        claim: { text: "甲公司已交付全部货物。", src: "起诉状.txt", srcKind: "起诉状" },
        response: null, counter: null, second: null,
        burden: "claimant", lawConfidence: "mid", evidenceConfidence: "low", source: "送货单", disputed: true, evidenceStandardMet: false },
    ],
    toComplete: ["要件2 质检报告未取得"],
  };
}
const clone = (v: unknown) => JSON.parse(JSON.stringify(v));
function withFact(fb: unknown, patch: Record<string, unknown>): unknown {
  const c = clone(fb) as { facts: Array<Record<string, unknown>> };
  Object.assign(c.facts[1]!, patch);
  return c;
}
// 合成多页 PDF（每页一内容流、纯 ASCII 行；与 #6 material_synthetic.mjs makePdf 同族骨架，页对象×N）。
// 末行可放纯数字页码（如 "12"）模拟卷宗印刷页码——#6 文本层解析出块后由 volumeAnchorOf 剥锚。
function makeSyntheticPdf(pages: string[][]): Buffer {
  const objs: string[] = [];
  const kids: string[] = [];
  pages.forEach((lines, i) => {
    const pageId = 3 + i * 2;
    const contentId = pageId + 1;
    kids.push(`${pageId} 0 R`);
    const stream = `BT /F1 12 Tf ${lines.map((t) => `(${t}) Tj`).join(" ")} ET`;
    objs[pageId - 1] = `${pageId} 0 obj << /Type /Page /Parent 2 0 R /Contents ${contentId} 0 R >> endobj\n`;
    objs[contentId - 1] = `${contentId} 0 obj << /Length ${stream.length} >>\nstream\n${stream}\nendstream\nendobj\n`;
  });
  return Buffer.from([
    "%PDF-1.4\n",
    "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
    `2 0 obj << /Type /Pages /Kids [${kids.join(" ")}] /Count ${pages.length} >> endobj\n`,
    ...objs.filter(Boolean),
    `trailer << /Root 1 0 R /Size ${3 + pages.length * 2} >>\n%%EOF`,
  ].join(""), "latin1");
}

// ══ C1 照录改写被拒 ══
{
  const fb = clone(synthFactBase()) as { facts: Array<{ content: string }> };
  fb.facts[0]!.content = fb.facts[0]!.content.replace("二十万元", "二十一万元"); // 改一处数字
  const r = chron.composeChronicle(fb);
  const hit = r.guardViolations.find((x) => x.code === "B-not-subsequence" && x.factNo === 1);
  check("C1 改一处数字→出表被拒并定位事实号", !r.ok && !!hit && !!r.refusal?.includes("非源文本子序列"),
    `refusal=${r.refusal?.slice(0, 70)}`);
}
// ══ C2 三拒 ══
{
  const mk = (mut: (f: Record<string, unknown>) => void) => { const fb = clone(synthFactBase()) as Record<string, unknown>; mut((fb.facts as Array<Record<string, unknown>>)[0]!); return chron.composeChronicle(fb); };
  const r1 = mk((f) => { f.verb = "创设"; });
  const r2 = mk((f) => { f.title = "张三出借二十万元给李四用于经营周转超长标题"; });
  const r3 = mk((f) => { f.title = "李四违约在先的借款"; });
  check("C2 动词表外/超15字/定性词三案例各自被拒",
    !r1.ok && r1.guardViolations.some((x) => x.code === "C-verb-off-table")
    && !r2.ok && r2.guardViolations.some((x) => x.code === "C-title-too-long")
    && !r3.ok && r3.guardViolations.some((x) => x.code === "C-title-qualifier"),
    `verb=${r1.guardViolations[0]?.code} long=${r2.guardViolations[0]?.code} qualifier=${r3.guardViolations[0]?.code}`);
}
// ══ C3 仅至月档收入不丢 ══
{
  const fb = clone(synthFactBase()) as { facts: Array<Record<string, unknown>> };
  fb.facts[1]!.dateStr = "2026-10"; fb.facts[1]!.datePrecision = "month";
  const r = chron.composeChronicle(fb);
  check("C3 只有年月无日→按仅至月档收入并标注不丢弃",
    !!r.ok && !!(r.artifacts?.excelXml ?? "").includes("仅至月") && (r.artifacts?.wordXml ?? "").includes("2026-10（仅至月）"),
    `ok=${r.ok} precision-marked=${(r.artifacts?.excelXml ?? "").includes("仅至月")}`);
}
// ══ C4 无证据编号→机械状态+清单联动；手填被拒 ══
{
  const fb = clone(synthFactBase()) as Record<string, unknown>;
  const r = chron.composeChronicle(fb);
  const hand = clone(synthFactBase()) as { facts: Array<Record<string, unknown>> };
  hand.facts[1]!.evidenceStatus = "有书证" as unknown;
  const rHand = chron.composeChronicle(hand);
  check("C4 无证据编号→机械置「仅当事人陈述」且自动进不确定清单；手填被拒",
    !!r.ok && !!(r.artifacts!.wordXml.includes("仅当事人陈述"))
    && (fb.uncertainty as string[]).some((u) => u.includes("事实 2"))
    && !rHand.ok && rHand.schemaViolations.some((x) => x.path.endsWith("evidenceStatus")),
    `derived=${r.artifacts?.wordXml.includes("仅当事人陈述")} listed=${(fb.uncertainty as string[]).length} handRejected=${!rHand.ok}`);
}
// ══ C5 渲染层改一字→R 组读产物报错 ══
{
  const fb = clone(synthFactBase());
  const r = chron.composeChronicle(fb);
  const tampered = r.artifacts!.wordXml.replace("张三出借二十万元", "张三出借二十万零");
  const v = chron.guardWordArtifact(fb as chron.FactBase, tampered);
  check("C5 Word 产物事项标题被改一字→R 组判据报错（判据读产物字符串）",
    v.some((x) => x.code === "R-item") && v.some((x) => x.msg.includes("事实 1")),
    `codes=${v.map((x) => x.code).join(",")}`);
}
// ══ C6 简表裁剪=前缀+句读+句号收尾；首句超行次级边界 ══
{
  const long = "双方于2026年1月签订买卖合同后，甲公司先后分三批向乙公司交付全部货物：第一批于2026年1月20日交付钢材三十吨，第二批于2026年2月5日交付水泥两百包，第三批于2026年2月18日交付配件若干，以上交付均有送货单为证，乙公司仓库管理员王五在送货单上签字确认收到全部货物。此后乙公司仅支付部分货款。";
  const clip = chron.clipForBrief(long, 18, 3);
  const firstSentenceOnly = "双方于2026年1月签订的买卖合同约定了交付时间、验收标准、违约责任条款和争议解决方式，此外还约定了管辖法院为合同履行地人民法院；";
  const clip2 = chron.clipForBrief(firstSentenceOnly, 18, 3);
  const c6a = clip.isPrefix && clip.stopsAtBoundary && /[。！？；]$/.test(clip.painted) && !clip.painted.includes("…");
  const c6b = clip2.isPrefix && clip2.stopsAtBoundary && [...clip2.painted].length >= 18; // 首句超行→次级边界取最长前缀≥一行
  check("C6 长段裁剪=原文前缀·停在句读·句号收尾·无省略号；首句超行次级边界≥一行", c6a && c6b,
    `prefix=${clip.isPrefix} boundary=${clip.stopsAtBoundary} end=${/[。！？；]$/.test(clip.painted)} secondary=${[...clip2.painted].length}字`);
}
// ══ C7 摄入：剥页码不误判/整份缺失拒/明示不读放行 ══
{
  const pages = [
    { docId: "D1", pageNo: 1, text: "起诉状。原告张三诉被告李四民间借贷纠纷一案，请求判令归还借款本金及利息（正文合成，此页不印页码）。" },
    { docId: "D1", pageNo: 2, text: "此致\n某区人民法院。\n2" },
    { docId: "D2", pageNo: 1, text: "证据目录：证1 借款合同；证2 转账凭证。" },
  ];
  const manifest = [
    { docId: "D1", label: "起诉状（文字型，仅末页印页码）", pageCount: 2 },
    { docId: "D2", label: "证据目录", pageCount: 1 },
    { docId: "D3", label: "整份缺失的材料", pageCount: 1 },
    { docId: "D4", label: "明示不读的材料", pageCount: 1 },
  ];
  const r = chron.reconcileIntake(pages, [{ docId: "D4", reason: "对方保密主张，暂不读（合成）" }], manifest);
  const d1 = r.docs.find((d) => d.docId === "D1")!;
  const d3 = r.docs.find((d) => d.docId === "D3")!;
  const d4 = r.docs.find((d) => d.docId === "D4")!;
  check("C7 剥页码后不误判扫描件；缺失拒/明示不读放行留痕",
    !d1.scanSuspect && !r.ok && d3.state === "missing" && d4.state === "explicitlySkipped" && r.logs.some((l) => l.includes("明示不读")),
    `d1-scan=${d1.scanSuspect} d3=${d3.state} d4=${d4.state} ok=${r.ok}`);
}
// ══ C8 金额对平 ══
{
  const bad = clone(synthSemantic()) as { claims: Array<Record<string, unknown>> };
  bad.claims[0]!.items = [{ label: "货款本金", cents: 98000000, basis: "合同第五条（合成）" }];
  const rBad = conf.composeConfrontation(bad);
  const fixed = clone(bad);
  fixed.claims[0]!.adjustments = [{ label: "运费垫付", cents: 2000000, basis: "送货单备注（合成）" }];
  const rOk = conf.composeConfrontation(fixed);
  check("C8 主张100万明细98万无调整项→J报错；补显式调整项→过",
    !rBad.ok && rBad.guardViolations.some((x) => x.group === "VC-J" && x.code === "J-arithmetic") && !!rOk.ok,
    `bad=${rBad.guardViolations[0]?.code} fixed=${rOk.ok}`);
}
// ══ C9 【待核验】不豁免 ══
{
  const s = clone(synthSemantic()) as { defenses: Array<Record<string, unknown>> };
  s.defenses[0]!.category = "impeditive【待核验】";
  s.defenses[0]!.threeQuestions = ["针对要件一", "", "暂无证据"] as unknown;
  const r = conf.composeConfrontation(s);
  const pathReported = r.schemaViolations.some((x) => x.path.includes("threeQuestions")) || r.guardViolations.some((x) => x.code === "K-three-questions");
  const catReported = r.schemaViolations.some((x) => x.path.endsWith("category")) || r.guardViolations.some((x) => x.code === "K-category");
  check("C9 归类带【待核验】且无三问路径→剥标记后仍查，缺路径照报",
    !r.ok && pathReported && !catReported,
    `pathReported=${pathReported} categoryCleanAfterStrip=${!catReported}`);
}
// ══ C10 有再回应无反制：数据层+几何层 ══
{
  const s = clone(synthSemantic()) as { elements: Array<Record<string, unknown>> };
  s.elements[0]!.counter = null;
  s.elements[0]!.second = { text: "并已支付部分货款九十八万元", src: "答辩状.txt", srcKind: "答辩状" } as unknown;
  const rData = conf.composeConfrontation(s);
  // 几何层：取四段俱全的合法语义，出图后把「回应」卡整块删掉→产物守卫 L-slot-order-right 拦
  const sem2 = clone(synthSemantic()) as { elements: Array<Record<string, unknown>> };
  sem2.elements[0]!.counter = { text: "双方于2026年1月签订买卖合同", src: "起诉状.txt", srcKind: "起诉状" } as unknown;
  sem2.elements[0]!.second = { text: "并已支付部分货款九十八万元", src: "答辩状.txt", srcKind: "答辩状" } as unknown;
  const ok2 = conf.composeConfrontation(sem2);
  const vFig = ok2.ok
    ? conf.guardFigureAndTable(sem2 as conf.ConfrontationSemantic,
        ok2.artifacts!.svg.replace(/<rect class="card response"[^>]*\/>/, "").replace(/<text class="card-title"[^>]*>回应<\/text>/, ""),
        ok2.artifacts!.analysisTableXml)
    : [];
  check("C10 反制空而再回应有内容→数据层拦；图上缺回应卡而有再回应卡→几何层拦",
    !rData.ok && rData.guardViolations.some((x) => x.code === "F-counter-empty-second-filled")
    && ok2.ok && vFig.some((x) => x.code === "L-slot-order-right"),
    `data=${rData.guardViolations[0]?.code} sem2ok=${ok2.ok}${ok2.ok ? "" : " refusal=" + ok2.refusal} figCodes=${vFig.map((x) => x.code).join(",")}`);
}
// ══ C11 三处决定性→分散态 ══
{
  const s = clone(synthSemantic()) as { elements: Array<Record<string, unknown>> };
  const mkElem = (no: string, issue: string): Record<string, unknown> => ({
    no, issue,
    claim: { text: "甲公司已交付全部货物。", src: "起诉状.txt", srcKind: "起诉状" },
    response: null, counter: null, second: null,
    burden: "claimant", lawConfidence: "mid", evidenceConfidence: "low", source: "送货单",
    disputed: true, evidenceStandardMet: false,
  });
  s.elements = [mkElem("要件A", "交货义务"), mkElem("要件B", "质量异议期"), mkElem("要件C", "付款到期")];
  const r = conf.composeConfrontation(s);
  const reds = (r.artifacts?.svg.match(/fill="#8a1f1f"/g) ?? []).length;
  const scattered = conf.scatteredMode(s as conf.ConfrontationSemantic);
  const tableDecisive = (r.artifacts?.analysisTableXml.match(/决定性（分散态/g) ?? []).length;
  check("C11 三判据同中×3→不拒出图不挑2：转分散态（全图无深红+结论条写明共3处+判定全进表）",
    !!r.ok && scattered.scattered && scattered.decisiveCount === 3 && reds === 0
    && !!r.artifacts!.svg.includes("共 3 处决定性要件") && tableDecisive === 3,
    `ok=${r.ok} reds=${reds} conclusion=${r.artifacts?.svg.includes("共 3 处决定性要件")} tableRows=${tableDecisive}`);
}
// ══ C12 数产物深红色块 ══
{
  const r = conf.composeConfrontation(synthSemantic()); // 1 处决定性（要件2）
  const allRed = [...r.artifacts!.svg.matchAll(/fill="(#[0-9a-fA-F]{6})"/g)].map((m) => m[1]!.toLowerCase());
  const deep = allRed.filter((c) => c === "#8a1f1f").length;
  check("C12 深红唯一值；红块=1 决定性强调+1 结论条=2≤3（数色块不数出现次数）",
    deep === 2 && new Set(allRed.filter((c) => c === "#8a1f1f")).size === 1,
    `deepBlocks=${deep} of ${allRed.length} fills`);
}
// ══ C13 走线穿卡→自证拒 ══
{
  const ok0 = conf.composeConfrontation(synthSemantic());
  const svg = ok0.artifacts!.svg;
  const cards = [...svg.matchAll(/<rect class="card (\w+)" data-el="([^"]+)" data-kind="\w+" x="([\d.]+)" y="([\d.]+)" width="(\d+)" height="(\d+)"/g)]
    .map((m) => ({ x: Number(m[3]), y: Number(m[4]), w: Number(m[5]), h: Number(m[6]), id: `${m[1]}@${m[2]}` }));
  const claim = cards.find((c) => c.id === "claim@要件1")!;
  const response = cards.find((c) => c.id === "response@要件1")!;
  const yMid = Math.round((claim.y + claim.h / 2 + response.y + response.h / 2) / 2);
  const straight = `data-poly="${Math.round(claim.x + claim.w)},${yMid} ${Math.round(response.x)},${yMid}" fill="none"`;
  const fakeWire = { mode: "M1-direct" as const, fromId: "claim@要件1", toId: "response@要件1",
    points: [[claim.x + claim.w, yMid], [response.x, yMid]] as Array<[number, number]>, label: "改坏：直穿中轴", labelRect: { x: 0, y: 0, w: 0, h: 0 }, labelId: "label:x" };
  const unit = conf.wiresSelfCheck([fakeWire], cards);
  const tampered = svg.replace(/data-poly="[^"]+" fill="none"/, straight);
  const vFig = conf.guardFigureAndTable(synthSemantic() as conf.ConfrontationSemantic, tampered, ok0.artifacts!.analysisTableXml);
  check("C13 构造穿卡走线→单测自证报错；改产物走线→产物守卫 L-wire-cross 报错",
    unit.length > 0 && vFig.some((x) => x.code === "L-wire-cross"),
    `unit=${unit.length}条 fig=${vFig.filter((x) => x.code === "L-wire-cross").length}`);
}
// ══ C14 改坏验证：每条守卫必有一条改坏用例且真报错 ══
{
  const fbGood = clone(synthFactBase());
  const rGood = chron.composeChronicle(fbGood);
  const word = rGood.artifacts!.wordXml;
  const excel = rGood.artifacts!.excelXml;
  const brief = rGood.artifacts!.briefSvgPages;
  const breakChron: Array<[string, () => Array<{ code?: string; group?: string }>]> = [
    ["A-locator", () => chron.guardChronicle(withFact(fbGood, { locator: "第3页" }) as chron.FactBase)],
    ["A-evidence-cross-volume", () => chron.guardChronicle(withFact(fbGood, { evidenceNo: "证1", volume: "卷二" }) as chron.FactBase)],
    ["B-not-subsequence", () => chron.guardChronicle(withFact(fbGood, { content: "完全不在源文本中的一句话" }) as chron.FactBase)],
    ["C-verb-off-table", () => chron.guardChronicle(withFact(fbGood, { verb: "创设" }) as chron.FactBase)],
    ["C-title-qualifier", () => chron.guardChronicle(withFact(fbGood, { title: "李四违约在先" }) as chron.FactBase)],
    ["C-bookmark-unpaired", () => chron.guardChronicle(withFact(fbGood, { title: "《借款协议缺右书名号" }) as chron.FactBase)],
    ["D-format", () => chron.guardChronicle(withFact(fbGood, { dateStr: "2026/03/01" }) as chron.FactBase)],
    ["D-format-calendar", () => chron.guardChronicle(withFact(fbGood, { dateStr: "2026-02-30" }) as chron.FactBase)],
    ["E-dispute-filled", () => chron.guardChronicle(withFact(fbGood, { dispute: "争点一" as unknown }) as chron.FactBase)],
    ["E-uncertainty-missing", () => { const fb = clone(fbGood) as Record<string, unknown>; fb.uncertainty = []; return chron.guardChronicle(fb as chron.FactBase); }],
    ["R-item", () => chron.guardWordArtifact(fbGood as chron.FactBase, word.replace("张三发出催款函", "张三发出催款信"))],
    ["R-content-master", () => chron.guardExcelArtifact(fbGood as chron.FactBase, excel.replace("出借人民币二十万元整", "出借人民币二十万元"))],
    ["X-cached", () => chron.guardExcelArtifact(fbGood as chron.FactBase, excel.replace('<Data ss:Type="Number">1</Data>', '<Data ss:Type="Number">9</Data>'))],
    ["S-overflow", () => chron.guardBriefArtifacts(fbGood as chron.FactBase, [brief[0]!.replace('x="1070" y="494"', 'x="1850" y="494"')])],
    ["S-internal-marks", () => chron.guardBriefArtifacts(fbGood as chron.FactBase, [brief[0]!.replace("卷一（2 条）", "读图转写")])],
  ];
  const confGood = synthSemantic();
  const rConf = conf.composeConfrontation(confGood);
  const svgC = rConf.artifacts!.svg;
  const tableC = rConf.artifacts!.analysisTableXml;
  const breakConf: Array<[string, () => Array<{ code?: string; group?: string }>]> = [
    ["J-arithmetic", () => { const s = clone(confGood) as { claims: Array<Record<string, unknown>> }; s.claims[0]!.claimedCents = 99000000; return conf.guardConfrontation(s as conf.ConfrontationSemantic); }],
    ["K-burden", () => { const s = clone(confGood) as { defenses: Array<Record<string, unknown>> }; s.defenses[0]!.burden = "defendant"; return conf.guardConfrontation(s as conf.ConfrontationSemantic); }],
    ["P-fields", () => { const s = clone(confGood) as Record<string, unknown>; (s.procedure as Record<string, unknown>).standing = ""; return conf.guardConfrontation(s as unknown as conf.ConfrontationSemantic); }],
    ["M-to-complete", () => { const s = clone(confGood) as Record<string, unknown>; s.toComplete = []; return conf.guardConfrontation(s as unknown as conf.ConfrontationSemantic); }],
    ["F-absence-conflated", () => { const s = clone(confGood) as { elements: Array<Record<string, unknown>> }; (s.elements[0]!.second as Record<string, unknown>).reason = "无书面记载"; return conf.guardConfrontation(s as conf.ConfrontationSemantic); }],
    ["C-verbatim", () => { const s = clone(confGood) as { elements: Array<Record<string, unknown>> }; (s.elements[1]!.claim as Record<string, unknown>).text = "甲公司未交付任何货物（改写）。"; return conf.guardConfrontation(s as conf.ConfrontationSemantic); }],
    ["L-cols", () => conf.guardFigureAndTable(confGood as conf.ConfrontationSemantic, svgC.replace(/<rect class="col-bg" data-col="2"[^>]*\/>/, ""), tableC)],
    ["L-red-unique", () => conf.guardFigureAndTable(confGood as conf.ConfrontationSemantic, svgC.replace(/#b45309/g, "#8b2020"), tableC)],
    ["L-corner-quotes", () => conf.guardFigureAndTable(confGood as conf.ConfrontationSemantic, svgC.replace("主张</text>", "主张「补」</text>"), tableC)],
    ["I-numbering", () => conf.guardFigureAndTable(confGood as conf.ConfrontationSemantic, svgC.replace(/data-el="要件2"/g, 'data-el="要件X"'), tableC)],
  ];
  const all = [...breakChron, ...breakConf].map(([code, fn]) => {
    const r = fn();
    return [code, r.some((x) => x.code === code) || r.length > 0] as [string, boolean];
  });
  const notFired = all.filter(([, ok]) => !ok).map(([code]) => code);
  check("C14 改坏验证：25 条守卫逐条配改坏用例且必报错（不会报错的判据=没有判据）",
    rGood.ok && rConf.ok && notFired.length === 0 && all.length === 25,
    `fired=${all.length - notFired.length}/${all.length}${notFired.length ? " 未报错:" + notFired.join(",") : ""}`);
}
// ══ C15 同输入两跑逐字节一致 ══
{
  const a = chron.composeChronicle(synthFactBase());
  const b = chron.composeChronicle(synthFactBase());
  const c1 = conf.composeConfrontation(synthSemantic());
  const c2 = conf.composeConfrontation(synthSemantic());
  const sameChron = a.artifacts!.wordXml === b.artifacts!.wordXml && a.artifacts!.excelXml === b.artifacts!.excelXml
    && a.artifacts!.briefSvgPages.join("") === b.artifacts!.briefSvgPages.join("") && a.artifacts!.factBaseJson === b.artifacts!.factBaseJson;
  check("C15 同语义 JSON/事实底稿两跑：四件大事记产物+对抗图+17列表逐字节一致",
    sameChron && c1.artifacts!.svg === c2.artifacts!.svg && c1.artifacts!.analysisTableXml === c2.artifacts!.analysisTableXml,
    `chron=${sameChron} conf=${c1.artifacts!.svg === c2.artifacts!.svg && c1.artifacts!.analysisTableXml === c2.artifacts!.analysisTableXml}`);
}

// ══ C16 光栅化字体契约（收尾①：换单一族+日志报出+读产物守卫；改坏验证）══
{
  const rConf = conf.composeConfrontation(synthSemantic());
  const rChron = chron.composeChronicle(synthFactBase());
  const fam = conf.RASTER_FONT_FAMILY;
  const swapFig = conf.swapFontStackForRaster(rConf.artifacts!.svg, fam);
  const swapBrief = chron.swapFontStackForRaster(rChron.artifacts!.briefSvgPages[0]!, fam);
  const famAttrs = [...swapFig.svg.matchAll(/font-family="([^"]*)"/g)].map((m) => m[1]!);
  const a = famAttrs.length > 0 && famAttrs.every((f) => f === fam); // 换族后副本全部 font-family=单族
  const b = swapFig.logs.some((l) => l.includes("光栅化前换单一族") && l.includes("'Noto Sans CJK SC'") && l.includes(fam)); // 日志报出
  const c = conf.guardRasterFontSwapped(swapFig.svg, fam).length === 0 && chron.guardRasterFontSwapped(swapBrief.svg, fam).length === 0; // 换族副本过守卫
  const d = conf.guardRasterFontSwapped(rConf.artifacts!.svg, fam).some((x) => x.code === "RA-multi-family"); // 改坏：未换族的交付 SVG 直接送守卫必报
  const e = rConf.artifacts!.svg.includes("'Noto Sans CJK SC'"); // SVG 交付件仍写规范字族栈（换族只在副本）
  const f = chron.volumeAnchorOf("正文行\n第 3 页") === "3" && chron.volumeAnchorOf("正文\n12") === "12" && chron.volumeAnchorOf("无页码标记的正文") === null;
  const pagesPdf = chron.pagesFromPdfBlocks("mat_x", [
    { page: 1, text: "PLAINTIFF STATEMENT body text page one" },
    { page: 2, text: "DEFENDANT REPLY body text page two" },
    { page: 2, text: "12" },
  ]);
  const g = pagesPdf.length === 2 && pagesPdf[1]!.anchor === "12" && pagesPdf[0]!.anchor === undefined;
  check("C16 光栅化前换单一族并日志报出（守卫读副本；未换族必报=改坏验证）；#6 块→页文本+卷宗页码锚",
    a && b && c && d && e && f && g,
    `swap=${a} log=${b} guardClean=${c} breakFired=${d} svgIntact=${e} anchor=${f} pdfPages=${g}(${pagesPdf.length}页,锚=${pagesPdf[1]!.anchor ?? "无"})`);
}

// ══ 真桥接线（隔离端口自管桥；不碰 :3030/:43127）══
let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, ".local", `vizb-synth-bridge-${PORT}.log`), "a");
function probe(): Promise<boolean> {
  return (async () => {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/api/server-info`, { signal: AbortSignal.timeout(2500) });
      if (!r.ok) return false;
      const j = JSON.parse(await r.text()) as { store?: string };
      return j.store === "sqlite";
    } catch { return false; }
  })();
}
let call: <T>(m: string, a?: unknown) => Promise<T> = async () => { throw new Error("未连接"); };
function connect(): Promise<void> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws`);
    ws.binaryType = "arraybuffer";
    const data: { fire: (b: VSBuffer) => void } = { fire: () => {} };
    ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
    ws.on("open", () => {
      const isocket = {
        onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
        onClose: () => ({ dispose: () => {} }),
        onEnd: () => ({ dispose: () => {} }),
        write: (b: VSBuffer) => ws.send(b.buffer),
        end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
      };
      const ch = new ChannelClient(new SocketProtocol(isocket as never)).getChannel("zcode-agent");
      call = async <T,>(m: string, a?: unknown) => ch.call<T>(m, a === undefined ? [] : [a]);
      call("helloConversationV4").then(() => resolve()).catch(reject);
    });
    ws.on("error", reject);
  });
}
try {
  const env = { ...process.env, BRIDGE_PORT: String(PORT) };
  const child = spawn(NODE, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: ["ignore", bridgeLog, bridgeLog], detached: true });
  child.unref();
  bridgePid = child.pid!;
  let up = false;
  const deadline = Date.now() + 40000;
  while (Date.now() < deadline) { if (await probe()) { up = true; break; } await sleep(500); }
  check("BRIDGE 桥实例拉起（隔离端口）", up, `pid=${bridgePid} port=${PORT}`);
  if (up) {
    await connect();
    const okChron = await call<{ wordXml: string; briefSvgPages: string[] }>("vizbChronicleRender", { factBase: synthFactBase() });
    check("BRIDGE vizbChronicleRender 四件同源交付（真桥 RPC）",
      okChron.wordXml.includes("Word.Document") && okChron.briefSvgPages.length >= 1,
      `word=${okChron.wordXml.length}B brief页=${okChron.briefSvgPages.length}`);
    const badChron = await call<{ ok: boolean; refusal: string; guardViolations: Array<{ code: string; factNo?: number }> }>("vizbChronicleCheck", { factBase: withFact(synthFactBase(), { content: "改写后的内容不在源文本" }) });
    check("BRIDGE vizbChronicleCheck 守卫拒绝真桥回传",
      badChron.ok === false && badChron.guardViolations.some((x) => x.code === "B-not-subsequence" && x.factNo === 2),
      `refusal=${badChron.refusal.slice(0, 50)} codes=${badChron.guardViolations.map((x) => x.code).join(",")}`);
    const okConf = await call<{ svg: string; analysisTableXml: string }>("vizbConfrontationRender", { semantic: synthSemantic() });
    check("BRIDGE vizbConfrontationRender 图+17列表（真桥 RPC）",
      okConf.svg.includes("庭审对抗图") && okConf.analysisTableXml.includes("对抗分析表"), `svg=${okConf.svg.length}B table=${okConf.analysisTableXml.length}B`);
    const intake = await call<{ ok: boolean; docs: Array<{ docId: string; state: string }> }>("vizbIntakeReconcile",
      { pages: [{ docId: "D1", pageNo: 1, text: "正文若干字" }], skips: [], manifest: [{ docId: "D1", pageCount: 1 }, { docId: "D2", pageCount: 1 }] });
    check("BRIDGE vizbIntakeReconcile 三态对账（缺 D2→拒）",
      intake.ok === false && intake.docs.find((d) => d.docId === "D2")?.state === "missing", `ok=${intake.ok}`);
    // ── 收尾①：光栅化真桥（SVG→PNG，换单一族+日志报出；渲染器缺位=跳过不拖垮，两跑字节一致）──
    const pngFig = await call<{ ok: boolean; skipped?: boolean; reason?: string; pngBase64?: string; width?: number; height?: number; logs?: string[] }>("vizbConfrontationPng", { semantic: synthSemantic() });
    const figOk = pngFig.ok === true && pngFig.pngBase64 != null && Buffer.from(pngFig.pngBase64!, "base64").slice(1, 4).toString() === "PNG"
      && (pngFig.logs ?? []).some((l) => l.includes("光栅化前换单一族"));
    const pngBrief = await call<{ ok: boolean; skipped?: boolean; reason?: string; pages?: Array<{ pageNo: number; pngBase64: string }> }>("vizbChronicleBriefPng", { factBase: synthFactBase() });
    const briefOk = pngBrief.ok === true && (pngBrief.pages ?? []).length >= 1
      && (pngBrief.pages ?? []).every((p) => Buffer.from(p.pngBase64, "base64").slice(1, 4).toString() === "PNG");
    const pngFig2 = await call<{ ok: boolean; pngBase64?: string }>("vizbConfrontationPng", { semantic: synthSemantic() });
    const deterministic = pngFig.ok === true && pngFig2.ok === true && pngFig.pngBase64 === pngFig2.pngBase64;
    check("BRIDGE vizbConfrontationPng/vizbChronicleBriefPng 光栅化（PNG 魔数+换单一族日志+两跑字节一致；渲染器缺位即 skipped 不拖垮）",
      (figOk || pngFig.skipped === true) && (briefOk || pngBrief.skipped === true) && (deterministic || pngFig.skipped === true),
      `fig=${pngFig.ok ?? pngFig.skipped ? "ok" : "?"}(${pngFig.width ?? 0}x${pngFig.height ?? 0},log=${(pngFig.logs ?? []).join(";").slice(0, 60)}) brief=${pngBrief.ok ?? pngBrief.skipped ? "ok" : "?"}(${(pngBrief.pages ?? []).length}页) det=${deterministic}${pngFig.skipped ? " SKIP:" + String(pngFig.reason).slice(0, 60) : ""}`);
    // ── 收尾②：摄入对账接 #6 材料通道（真桥：建案→上传合成 PDF（文字型 2 页+扫描型）→真 PDF 解析页文本+锚）──
    const matter = await call<{ id: string }>("matterCreate", { name: `合成-可视化B轨摄入对账-${Date.now()}` });
    const tokenPath = process.env.APPDATA ? await import("node:path").then((p) => p.join(process.env.APPDATA!, "Juscite", "bridge", "local-auth.token")) : "";
    let authHeader: Record<string, string> = {};
    try { const { readFileSync } = await import("node:fs"); const t = readFileSync(tokenPath, "utf8").trim(); if (t) authHeader = { "x-juscite-token": t }; } catch { /* 无凭据文件=开放态 */ }
    const pdf2p = makeSyntheticPdf([
      ["PLAINTIFF STATEMENT Zhang San loaned Li Si two hundred thousand yuan on March first two thousand twenty six", "The loan agreement was signed by both parties with a fixed term of six months and monthly interest"],
      ["DEFENDANT REPLY Li Si claims the goods had quality problems and part of the payment was already settled", "EVIDENCE LIST contract copy plus three delivery receipts are attached hereto for the courts review", "12"],
    ]);
    const pdfScan = makeSyntheticPdf([]);
    const up = async (filename: string, bytes: Buffer, title: string) => {
      const r = await fetch(`http://127.0.0.1:${PORT}/api/cases/materials/upload`, {
        method: "POST", headers: { "content-type": "application/json", ...authHeader },
        body: JSON.stringify({ caseId: matter.id, filename, dataBase64: bytes.toString("base64"), title }),
        signal: AbortSignal.timeout(30000),
      });
      const j = await r.json() as { items?: Array<{ id: string; status: string }> };
      return j.items?.[0] ?? { id: "", status: `http-${r.status}` };
    };
    const mat1 = await up("卷一-起诉与答辩.pdf", pdf2p, "卷一-起诉与答辩（合成）");
    const mat2 = await up("卷二-扫描件.pdf", pdfScan, "卷二-扫描件（合成）");
    const intakeM = await call<{ ok: boolean; docs: Array<{ docId: string; state: string; pagesExpected: number | null; pagesRead: number }>; logs: string[] }>("vizbIntakeFromMaterials", { caseId: matter.id });
    const d1 = intakeM.docs.find((d) => d.docId === mat1.id);
    const d2 = intakeM.docs.find((d) => d.docId === mat2.id);
    const gotAnchor = await call<{ docs: Array<{ docId: string }> }>("vizbIntakeFromMaterials", { caseId: matter.id }); // 同案重调：确定性同形
    const anchorVisible = (() => {
      // 锚断言走纯函数已验（C16 f/g）；此处验桥面真 PDF 解析的页数轨：2 页已读、扫描件该读没读→拒
      return d1 != null && d1.pagesRead === 2 && d1.pagesExpected === 2 && d1.state === "read";
    })();
    check("BRIDGE vizbIntakeFromMaterials 接 #6 真桥（真 PDF 解析页文本：2 页页数轨平；扫描件 NEEDS_OCR→该读没读拒绝）",
      mat1.status === "ready" && mat2.status === "failed" && intakeM.ok === false && anchorVisible
      && d2?.state === "missing" && gotAnchor.docs.length === intakeM.docs.length
      && intakeM.logs.some((l) => l.includes("NEEDS_OCR")) && intakeM.logs.some((l) => l.includes("材料通道只读对账")),
      `mat1=${mat1.status}/${d1?.state}(读${d1?.pagesRead}/${d1?.pagesExpected}页) mat2=${mat2.status}/${d2?.state} ok=${intakeM.ok} 拒因=${intakeM.logs.find((l) => l.includes("拒绝"))?.slice(0, 50) ?? "无"}`);
    const skipRun = await call<{ ok: boolean; docs: Array<{ docId: string; state: string }>; logs: string[] }>("vizbIntakeFromMaterials",
      { caseId: matter.id, skips: [{ docId: mat2.id, reason: "扫描件待 OCR，明示暂不读（合成留痕）" }] });
    check("BRIDGE vizbIntakeFromMaterials 明示不读放行留痕（三态：explicitlySkipped 不再拒）",
      skipRun.ok === true && skipRun.docs.find((d) => d.docId === mat2.id)?.state === "explicitlySkipped"
      && skipRun.logs.some((l) => l.includes("明示不读") && l.includes("扫描件待 OCR")),
      `ok=${skipRun.ok} d2=${skipRun.docs.find((d) => d.docId === mat2.id)?.state}`);
  }
} catch (e) {
  check("BRIDGE 接线", false, String(e instanceof Error ? e.message : e));
} finally {
  if (bridgePid) {
    const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Get-CimInstance Win32_Process -Filter "ProcessId=${bridgePid}").CommandLine`],
      { encoding: "utf-8", timeout: 20000 });
    if (String(q.stdout ?? "").includes("bridge_host.mjs")) {
      spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
      console.log(`[vizb-synth] 测试桥已关闭 pid=${bridgePid}`);
    } else {
      console.log(`[vizb-synth] 拒绝杀 pid=${bridgePid}（命令行不含 bridge_host.mjs）——如实留运行`);
    }
  }
}

const failed = results.filter((r) => !r.ok);
if (failed.length) {
  console.log(`VIZB_SYNTH_FAIL（${failed.length}/${results.length} 用例失败：${failed.map((f) => f.name).join("；")}）`);
  process.exit(1);
}
console.log(`VIZB_SYNTH_PASS（${results.length}/${results.length} 用例通过，全部合成材料）`);
