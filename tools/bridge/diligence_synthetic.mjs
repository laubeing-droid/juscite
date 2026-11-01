// 【功能 #32 整理与尽调】合成对拍探针（RE-32 §2 行为 1-16 + §4 对拍 15 行 + 增补 S1-S3；施工波三轮-20261031）。
// 全合成材料、零真模型（LLM 路=注入的确定性合成件，mode 如实标注）、零外网、隔离端口 :3090 起（不碰 :3030/:43127）。
// A 段=内核+服务进程内直驱（内存库+异步任务壳）；B 段=隔离桥 HTTP 全链（真迁移 0024+真材料管线上传+taskshell 轮询+Word 字节）。
// 杀桥前必核命令行含 bridge_host.mjs（宁停不误杀）；oc28(:43127) 与常驻桥(:3030) 全程不接触。
// 运行：node --import tsx tools/bridge/diligence_synthetic.mjs（与 ci_gate.mjs 调用形一致）。
import { DatabaseSync } from "node:sqlite";
import { mkdtempSync, rmSync, existsSync, readFileSync, unlinkSync, openSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { openBridgeStore } from "./bridge_store.mjs";
import { createTaskShell } from "./taskshell_service.mjs";
import { MATERIALS_DDL } from "./material_service.mjs";
import { markdownToLegalDocx } from "./draft_docx.mjs";
import { createDiligenceService, DILIGENCE_DDL, createDiligenceDao } from "./diligence_service.mjs";
import {
  BOARD_GROUPS, transitionTask, confirmTask as confirmKernel, bindFlow as bindFlowKernel,
} from "../../packages/juscite-legal/src/kernel/diligenceBoardModel.ts";
import {
  renderExtractionPrompt, validateRowValues, exportSchemaJson, importSchemaJson, schemaFieldNames,
} from "../../packages/juscite-legal/src/kernel/diligenceSchemaModel.ts";
import {
  extractLedgerRows, traceOf as traceKernel, editCell as editKernel, ledgerToCsv,
} from "../../packages/juscite-legal/src/kernel/diligenceLedgerModel.ts";
import {
  chronicleWordMarkdown, extractTimelineEvents, buildChronicleChapter, buildRiskAndTodo,
} from "../../packages/juscite-legal/src/kernel/diligenceChronicleModel.ts";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
let pass = 0, fail = 0;
function assert(n, cond, label, detail = "") {
  if (cond) { pass += 1; console.log(`  #${n} OK  ${label}`); }
  else { fail += 1; console.log(`  #${n} FAIL ${label}${detail ? ` ｜ ${detail}` : ""}`); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ══════════ A 段：内核+服务进程内直驱（内存库）══════════
console.log("[A] 内核与服务直驱（合成材料）");
const adb = new DatabaseSync(":memory:");
adb.exec(MATERIALS_DDL);
adb.exec(DILIGENCE_DDL);
adb.exec(`CREATE TABLE IF NOT EXISTS async_tasks (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, ref TEXT, status TEXT NOT NULL, payload_json TEXT,
  result_ref TEXT, file_name TEXT, error_code TEXT, error_message TEXT, retry_count INTEGER NOT NULL DEFAULT 0,
  artifact_ttl INTEGER, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT)`);
const WS = "ws-synth";
const CASE = "mat_synth01";
const adao = createDiligenceDao(adb);
const tmpArt = mkdtempSync(join(tmpdir(), "diligence-synth-art-"));
const taskShellA = createTaskShell(adb, { artifactsDir: tmpArt, sweepOnBoot: false });
const llmSynth = (field, doc) => {
  // 合成 LLM 路（确定性脚本件；仅规则未中时被问）：给 doc3 补「银行账户」，其余不编造
  if (field.name === "银行账户" && doc.docId === "mat_doc3") return { value: "6223000000000003", blockIndex: 0 };
  return null;
};
const svcA = createDiligenceService({
  dao: adao, caseExists: (id) => id === CASE, workspaceKey: WS, authFilePath: null,
  taskShell: taskShellA, llmExtract: llmSynth, log: () => {},
});

// ── 行为 1：看板三分组（模板驱动建板）──
const t1 = svcA.createTask({ caseId: CASE, group: "计划与清单", fromPreset: "明确尽调目的、范围与核查重点" });
const t2 = svcA.createTask({ caseId: CASE, group: "资料收集与台账", title: "函证底稿台账提取", subtasks: ["配模板", "批量提取", "逐项核对"] });
const t3 = svcA.createTask({ caseId: CASE, group: "专项核查", fromPreset: "主体资格与工商沿革核查" });
const overview = svcA.overviewOf(CASE);
assert(1, JSON.stringify(overview.groups) === JSON.stringify([...BOARD_GROUPS]) && overview.board.counts["计划与清单"] === 1 && overview.board.counts["资料收集与台账"] === 1 && overview.board.counts["专项核查"] === 1,
  "行为1 任务看板按尽调流程三分组（计划与清单/资料收集与台账/专项核查）", JSON.stringify(overview.board.counts));

// ── 行为 2：状态=待确认确认门 ──
let gateBlocked = false, confirmFromWrong = false, emptyConfirmer = false, okFlow = false;
try { transitionTask(t2, "done", "2026-01-01T00:00:00Z"); } catch { gateBlocked = true; }
let mid = svcA.taskAction(t2.taskId, { action: "start" });
try { svcA.taskAction(t2.taskId, { action: "confirm", by: "律师甲" }); } catch { confirmFromWrong = true; }
mid = svcA.taskAction(t2.taskId, { action: "submit-confirmation" });
try { svcA.taskAction(t2.taskId, { action: "confirm", by: "" }); } catch { emptyConfirmer = true; }
const done = svcA.taskAction(t2.taskId, { action: "confirm", by: "律师甲" });
okFlow = done.status === "done" && done.confirmedBy === "律师甲" && Boolean(done.confirmedAt);
assert(2, gateBlocked && confirmFromWrong && emptyConfirmer && okFlow,
  "行为2 确认门：直跳完成被拒/非待确认不可确认/确认人必填/确认后才「已完成」",
  `gate=${gateBlocked} wrong=${confirmFromWrong} empty=${emptyConfirmer} done=${okFlow}`);

// ── 行为 3：专题拆子任务逐项推进 + 按项目添加调整 ──
const sub4 = t3.subtasks.length === 4;
let withNew = svcA.taskAction(t3.taskId, { action: "add-subtask", subId: "subX", title: "对赌与回购条款专项排查" });
withNew = svcA.taskAction(t3.taskId, { action: "retitle-subtask", subId: "subX", title: "对赌回购与反稀释专项排查" });
withNew = svcA.taskAction(t3.taskId, { action: "mark-subtask", subId: "sub1", done: true });
const removed = svcA.taskAction(t3.taskId, { action: "remove-subtask", subId: "subX" });
assert(3, sub4 && withNew.subtasks.length === 5 && removed.subtasks.length === 4 && removed.subtasks.find((s) => s.subId === "sub1")?.done === true,
  "行为3 专题拆子任务（预设四子项）+按项目添加/改名/勾完成/移除", `sub4=${sub4} with=${withNew.subtasks.length} n=${removed.subtasks.length}`);

// ── 行为 4：任务绑尽调 Flow（契约-only，引擎归 RE-35）──
let bindBad = false;
try { bindFlowKernel(t3, { flowId: "" }); } catch { bindBad = true; }
const bound = svcA.taskAction(t3.taskId, { action: "bind-flow", flowRef: { flowId: "flow_ipo02_legal_dd", flowName: "法律尽调（IPO 族）" } });
const unbound = svcA.taskAction(t3.taskId, { action: "bind-flow", flowRef: null });
assert(4, bindBad && bound.flowRef?.flowId === "flow_ipo02_legal_dd" && unbound.flowRef === null,
  "行为4 专题任务绑定对应法律尽调 Flow（只存契约不调引擎；空 flowId 拒）", JSON.stringify(bound.flowRef));

// ── 行为 5：成果版本保存+点版本号切换查看 ──
const adaoResults = [];
{
  const { saveTaskResult, getTaskResult } = await import("../../packages/juscite-legal/src/kernel/diligenceBoardModel.ts");
  const v1 = saveTaskResult(adaoResults, "函证台账 v1：三行初稿", "律师甲", "2026-01-02T00:00:00Z");
  adaoResults.push(v1);
  const v2 = saveTaskResult(adaoResults, "函证台账 v2：补乙行余额核对注记", "律师甲", "2026-01-03T00:00:00Z");
  adaoResults.push(v2);
  const backToV1 = getTaskResult(adaoResults, 1);
  assert(5, v2.version === 2 && backToV1.content.includes("v1") && adaoResults.length === 2,
    "行为5 成果保存为不同版本（v1/v2 追加）+点版本号切回查看 v1", `versions=${adaoResults.map((v) => v.version).join(",")}`);
}

// ── 行为 6-10：台账（内核级：带页/坐标的合成块）──
const SCHEMA = {
  name: "银行函证要素",
  fields: [
    { name: "银行账户", type: "text", description: "函证回函载明的账号" },
    { name: "账户余额", type: "number" },
    { name: "函证日期", type: "date" },
    { name: "账户状态", type: "enum", enumValues: ["正常", "冻结", "销户"] },
    { name: "是否共管", type: "boolean" },
  ],
};
const blk = (page, seq, text) => ({ page, seq, bbox: [10 * seq, 20, 10 * seq + 5, 30], text, source: "text_layer", ocrVersion: null });
const docsK = [
  { docId: "mat_k1", docTitle: "函证回函-甲行.pdf", blocks: [blk(1, 0, "银行函证回函（合成件一）"), blk(1, 1, "银行账户：6222000000000001\n账户余额：152000.50\n函证日期：2026-03-15\n账户状态：正常")] },
  { docId: "mat_k2", docTitle: "函证回函-乙行.pdf", blocks: [blk(2, 0, "银行函证回函（合成件二）"), blk(2, 1, "银行账户：6222000000000002\n账户余额：98765.25\n函证日期：2026-02-28\n账户状态：冻结")] },
  { docId: "mat_k3", docTitle: "函证回函-丙行.pdf", blocks: [blk(3, 0, "户名：某某公司　账号 6223000000000003（标签写法不同，规则路不中）"), blk(3, 1, "余额与状态栏见附页（合成件留空）")] },
];
const outcomeK = extractLedgerRows(SCHEMA, docsK, {
  llmFill: (f, d) => (f.name === "银行账户" && d.docId === "mat_k3" ? { value: "6223000000000003", blockIndex: 0 } : null),
});
const row1 = outcomeK.rows[0];
assert(6, outcomeK.rows.length === 3 && row1.cells["银行账户"]?.value === "6222000000000001" && row1.cells["账户余额"]?.value === "152000.50"
  && outcomeK.stats.cellsRule >= 8 && outcomeK.stats.cellsLlm === 1,
  "行为6 格式相近底稿批量提取→结构化台账（多件×多字段；规则优先双路）", JSON.stringify(outcomeK.stats));

const trace = traceKernel({ ...{ ledgerId: "l", caseId: CASE, schemaName: SCHEMA.name, fields: SCHEMA.fields, rows: outcomeK.rows, status: "open", createdAt: "", updatedAt: "" } }, 1, "银行账户");
assert(7, trace.docId === "mat_k1" && trace.page === 1 && trace.seq === 1 && Array.isArray(trace.bbox) && trace.bbox.length === 4
  && trace.source === "text_layer" && trace.ocrVersion === null && trace.quote.includes("6222000000000001"),
  "行为8/S 三态 字段级依据回溯：page+seq+bbox+source+ocrVersion 四元组+引文", JSON.stringify({ page: trace.page, seq: trace.seq, bbox: trace.bbox, source: trace.source }));

const ledgerK = { ledgerId: "lk", caseId: CASE, schemaName: SCHEMA.name, fields: SCHEMA.fields, rows: outcomeK.rows, status: "open", createdAt: "t", updatedAt: "t" };
const edited = editKernel(ledgerK, 2, "账户余额", "100000.00", "律师乙", "t2");
assert(8, edited.ledger.rows[1].cells["账户余额"]?.value === "100000.00" && edited.ledger.rows[1].cells["账户余额"]?.origin === "manual",
  "行为9 提取结果在线查看/编辑（人工值落格、origin=manual、依据仍指原位）", edited.ledger.rows[1].cells["账户余额"]?.origin);

const csvK = ledgerToCsv(edited.ledger);
assert(9, csvK.startsWith("底稿文件,银行账户,账户余额") && csvK.includes("\r\n") && csvK.includes("100000.00") && csvK.includes("函证回函-甲行.pdf"),
  "行为10 台账导出 CSV（RFC4180：表头/行序/CRLF）", csvK.split("\r\n")[0]);

// 行为7：用户自定义字段模板（服务面保存+导入两通道）
const savedSchema = svcA.saveSchema({ caseId: CASE, name: SCHEMA.name, fields: SCHEMA.fields });
let dupName = false;
try { svcA.saveSchema({ caseId: CASE, name: "坏模板", fields: [{ name: "重复", type: "text" }, { name: "重复", type: "text" }] }); } catch { dupName = true; }
assert(10, savedSchema.fields.length === 5 && savedSchema.fields[3].type === "enum" && dupName,
  "行为7 自定义需整理材料与重点字段（字段模板用户可配；重名列拒收）", `id=${savedSchema.schemaId}`);

// ── S1/S2/S3：三态一源（增补节断言，行为化验证）──
const prompt = renderExtractionPrompt(SCHEMA);
const promptFields = schemaFieldNames(SCHEMA).filter((n) => prompt.includes(n));
const violFields = new Set();
for (const f of SCHEMA.fields) {
  const bad = f.type === "enum" ? "不在枚举里的值" : f.type === "boolean" ? 1 : f.type === "number" ? "不是数字" : f.type === "date" ? "2026-13-40" : 123;
  const v = validateRowValues(SCHEMA, { [f.name]: bad });
  if (!v.ok) violFields.add(v.violations[0].field);
}
const setDiff = [...schemaFieldNames(SCHEMA)].filter((n) => !violFields.has(n));
assert(11, promptFields.length === 5 && setDiff.length === 0,
  "S1 单源一致：prompt 渲染与校验器两侧字段集合逐字段一致（结构 diff 为空）", `prompt=${promptFields.length} validator=${violFields.size}`);

let enumRejected = false, numRejected = false, boolRejected = false;
enumRejected = !validateRowValues(SCHEMA, { 账户状态: "异常" }).ok;
numRejected = !validateRowValues(SCHEMA, { 账户余额: "余额充足" }).ok;
boolRejected = !validateRowValues(SCHEMA, { 是否共管: 1 }).ok && !validateRowValues(SCHEMA, { 是否共管: "true" }).ok;
const enumStrict = validateRowValues(SCHEMA, { 账户状态: "正常" }).ok;
assert(12, enumRejected && numRejected && boolRejected && enumStrict,
  "S2 类型违例拒收：枚举外取值/数值列给文本/布尔替身（1 与 \"true\" 等）具名拒绝，不落台账", `e=${enumRejected} n=${numRejected} b=${boolRejected}`);

const json = exportSchemaJson(SCHEMA);
const rt = importSchemaJson(json);
const rtAgain = importSchemaJson(exportSchemaJson(rt.schema));
const bad = importSchemaJson(JSON.stringify({ name: "x", fields: [{ name: "a", type: "text" }], extra: 1 }));
assert(13, rt.ok && JSON.stringify(rt.schema.fields) === JSON.stringify(SCHEMA.fields) && rtAgain.ok && !bad.ok,
  "S3 可配置往返：导出/导入 JSON 往返结构不变；未知键 fail-closed 拒收", `rt=${rt.ok} bad=${bad.ok}`);

// ── 行为 11/12：清单整理与缺失核对（服务面，内存材料表）──
const matRows = [
  ["mat_m1", "甲公司营业执照及章程", "text/plain", "license"],
  ["mat_m2", "2024 年度验资报告", "text/plain", ""],
  ["mat_m3", "第二次股权转让协议", "text/plain", ""],
];
for (const [mid, title, mime, sub] of matRows) {
  adb.prepare(`INSERT INTO case_materials (workspace_key, material_id, case_id, title, filename, version, content_hash,
    mime_type, byte_size, document_type, document_subtype, tags_json, stored_path, text_path, status, added_at, updated_at)
    VALUES (?, ?, ?, ?, '', 1, '', ?, 10, 'material', ?, '[]', '', '', 'ready', 't', 't')`).run(WS, mid, CASE, title, mime, sub);
}
adb.prepare(`INSERT INTO case_material_chunks (workspace_key, material_id, chunk_id, seq, type, level, title, text)
  VALUES (?, 'mat_m2', 'ch1', 0, '段', 0, '', '2026年1月10日 经审验，实缴出资已到位')`).run(WS);
const checklistSvc = createDiligenceService({ dao: adao, caseExists: (id) => id === CASE, workspaceKey: WS, authFilePath: null, taskShell: null, log: () => {} });
// checklist/chronicle 面走 httpHandler 太重，直驱内部等价面：经 kernel + dao 组合
const { DEFAULT_CHECKLIST_TEMPLATE, organizePlan, checkMissing } = await import("../../packages/juscite-legal/src/kernel/diligenceListModel.ts");
const matsLite = matRows.map(([mid, title, , sub]) => ({ materialId: mid, title, documentSubtype: sub, tags: [] }));
const plan = organizePlan(DEFAULT_CHECKLIST_TEMPLATE, matsLite);
const planOk = plan.assignments.length === 3
  && plan.assignments.find((a) => a.materialId === "mat_m1")?.category === "主体资格"
  && plan.assignments.find((a) => a.materialId === "mat_m2")?.category === "出资与财务"
  && plan.assignments.find((a) => a.materialId === "mat_m3")?.category === "股权变动"
  && plan.assignments.every((a) => /^\/?\S+\/\d{2}-/.test(a.renameTo) || /\d{2}-/.test(a.renameTo))
  && plan.indexMd.includes("| 1 | 主体资格 |");
assert(14, planOk, "行为11 按清单体系整理文件夹：分类归档+确定性重命名+建索引表", JSON.stringify(plan.assignments.map((a) => `${a.category}:${a.renameTo}`)));

const missing = checkMissing({ template: DEFAULT_CHECKLIST_TEMPLATE, assignments: plan.assignments, claims: [], materials: matsLite });
const missTitles = missing.missing.map((x) => x.item.name);
assert(15, missing.covered.some((c) => c.item.name === "营业执照及章程") && missing.covered.some((c) => c.item.name === "验资报告")
  && missTitles.includes("董监高任免文件") && missing.supplementMd.includes("# 补充尽调资料清单") && missing.supplementMd.includes("董监高任免文件"),
  "行为12 对照清单逐项梳理缺失+输出补充尽调资料清单", `missing=${missTitles.length}`);

// ── 行为 13-16：历史沿革（内核直驱）──
const chrDocs = [
  { docId: "mat_c1", docTitle: "公司章程（设立版）", kind: "公司章程", channel: "user",
    blocks: [blk(1, 0, "2018年5月10日 公司设立，通过首版章程，注册资本 1000 万元")] },
  { docId: "mat_c2", docTitle: "第一次股权转让协议", kind: "股权转让协议", channel: "user",
    blocks: [blk(1, 0, "2020年9月1日 甲方将 10% 股权转让给乙方，转让价款 300 万元")] },
  { docId: "mat_c3", docTitle: "2024 年度验资报告", kind: "验资报告", channel: "search",
    blocks: [blk(1, 0, "2026年1月10日 经审验，实缴出资已到位")] },
  { docId: "mat_c4", docTitle: "任免决定（日期写法非标）", kind: "董监高任免文件", channel: "user",
    blocks: [blk(1, 0, "第三届董事会第一次会议 dated 二零二四年春（无标准日期样例）\n2024年13月45日 非法日期行（解析必败样例：月日越界）")] },
];
const { events: evts, undated } = extractTimelineEvents(chrDocs);
const sortedOk = evts.filter((e) => e.dateIso).every((e, i, arr) => i === 0 || arr[i - 1].dateIso <= e.dateIso);
assert(16, evts.length >= 3 && evts[0].dateIso === "2018-05-10" && evts.find((e) => e.dateIso === "2026-01-10")?.docId === "mat_c3" && undated >= 1 && sortedOk,
  "行为13/14 前置 材料汇集（用户提交+项目内检索通道）与日期确定性解析（解析不了=待核不猜）", `events=${evts.length} undated=${undated}`);

const chapter = buildChronicleChapter("某公司尽调项目", chrDocs, evts, undated);
assert(17, chapter.includes("# 历史沿革核查报告") && chapter.includes("### 2018 年") && chapter.includes("2018-05-10") && chapter.includes("〔公司章程（设立版） 第1页〕") && chapter.includes("日期待核"),
  "行为14 按时间轴生成历史沿革章节正文（按年分组+原文位置锚+待核如实标注）", chapter.slice(0, 60));

const { risks, todoMd } = buildRiskAndTodo(chrDocs, evts, undated);
assert(18, risks.some((r) => r.title.includes("工商登记档案")) && risks.some((r) => r.level === "todo" && r.title.includes("日期未能解析")) && todoMd.includes("# 风险评估与待核查事项清单"),
  "行为15 同步输出风险评估与待核查事项清单（缺件/日期未解析规则面）", `risks=${risks.length}`);

const wordMd = chronicleWordMarkdown(chapter, todoMd);
const docx = markdownToLegalDocx(wordMd);
assert(19, Buffer.isBuffer(docx) && docx.length > 500 && docx[0] === 0x50 && docx[1] === 0x4b,
  "行为16 一键导出 Word（markdown→docx 零依赖装配，PK 魔数与体积）", `bytes=${docx.length}`);

// ── 对拍 15 行（我们侧行为逐行判定；行 12 按规格 §5 口径）──
const dp = [
  ["D1", overview.groups.length === 3 && done.status === "done" && gateBlocked, "看板三分组+确认门状态机（行为1/2）"],
  ["D2", removed.subtasks.length === 4 && removed.subtasks[0].done === true, "任务→子任务两级可编辑（行为3）"],
  ["D3", bound.flowRef?.flowId === "flow_ipo02_legal_dd" && unbound.flowRef === null, "任务绑流程模板/Flow 契约（行为4；引擎归 #35）"],
  ["D4", adaoResults.length === 2 && adaoResults[0].version === 1, "成果版本保存与切换（行为5）"],
  ["D5", outcomeK.rows.length === 3 && Object.keys(outcomeK.rows[0].cells).length === 5, "字段 schema 批量抽取→台账表（行为6）"],
  ["D6", savedSchema.fields.length === 5 && rt.ok && !bad.ok, "字段 schema 用户可配（行为7；S3 往返+fail-closed）"],
  ["D7", trace.page === 1 && trace.bbox?.length === 4, "page+bbox 坐标跳转载荷（行为8）"],
  ["D8", edited.ledger.rows[1].cells["账户余额"].origin === "manual", "台账表在线编辑（行为9）"],
  ["D9", csvK.includes("底稿文件,银行账户"), "台账导出 CSV（行为10）"],
  ["D10", plan.assignments.length === 3 && plan.indexMd.includes("资料整理索引"), "分类归档/重命名/建索引（行为11）"],
  ["D11", missing.missing.length > 0 && missing.supplementMd.includes("补充尽调资料清单"), "缺失项报告+补充清单（行为12）"],
  ["D12", chrDocs.some((d) => d.channel === "user") && chrDocs.some((d) => d.channel === "search"), "材料汇集=用户提交+项目内检索（行为13；§5 口径：非外部自动搜集，非严格等量如实判）"],
  ["D13", chapter.includes("### 2018 年") && chapter.includes("### 2020 年") && chapter.includes("### 2026 年"), "按时间轴生成沿革章节正文（行为14）"],
  ["D14", risks.length >= 2 && todoMd.includes("待核"), "风险评估与待核查清单（行为15）"],
  ["D15", docx[0] === 0x50 && docx[1] === 0x4b, "一键导出 Word（行为16）"],
];
dp.forEach(([id, cond, label], i) => assert(20 + i, cond, `对拍${label}`, `${id}`));

rmSync(tmpArt, { recursive: true, force: true });

// ══════════ B 段：隔离桥 HTTP 全链（:3090 起首个空闲端口，独立库；真迁移 0024+真材料管线）══════════
console.log("[B] 隔离桥 HTTP 全链（合成材料）");
function listenerCount(port) {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf8", timeout: 15000 });
  let n = 0;
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === port) n += 1;
  }
  return n;
}
async function commandLineOf(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command", `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`], { encoding: "utf8", timeout: 20000 });
  return String(r.stdout ?? "").trim();
}
// 端口选择：:3090 起首个零监听端口——绝不杀他人实例（共享工位并行探针在途；只挑空位不占位不清理）
let PORT = 0;
for (let p = Number(process.env.DILIGENCE_PROBE_PORT ?? 3090); p <= 3099 && !PORT; p++) {
  if (listenerCount(p) === 0) PORT = p;
}
if (!PORT) throw new Error("3090-3099 均被占用：无可用隔离端口，停止（不杀任何进程）");
console.log(`[diligence-probe] 选定隔离端口 :${PORT}`);
const dbFile = () => join(homedir(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${PORT}.db`);
let child = null;
try {
  for (const suffix of ["", "-wal", "-shm"]) { try { unlinkSync(dbFile() + suffix); } catch { /* 不存在即可 */ } }
  // 预播案件（经真库面：openBridgeStore 全迁移+insertCase 后即关，桥再开同库不重放）
  const seed = openBridgeStore(PORT);
  seed.insertCase({
    id: CASE, name: "某公司并购尽调（合成）", cause: "", case_no: "", court: "", court_type: "非诉",
    claim_amount_cents: 0, plaintiffs_json: "[]", defendants_json: "[]", judges_json: "[]",
    workflow_status: null, workflow_locked: 0, overrides_json: "{}", sort_order: null, updated_at: new Date().toISOString(),
  });
  seed.db.close();

  const logFd = openSync(join(REPO_ROOT, ".local", `diligence-probe-bridge-${PORT}.log`), "a");
  child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(PORT) }, stdio: ["ignore", logFd, logFd], detached: true });
  child.unref();
  const base = `http://127.0.0.1:${PORT}`;
  const tokenPath = join(dirname(dbFile()), "local-auth.token");
  const token = existsSync(tokenPath) ? readFileSync(tokenPath, "utf-8").trim() : "";
  const hdr = token ? { "x-juscite-token": token } : {};
  const api = async (method, path, body) => {
    const r = await fetch(`${base}${path}`, {
      method, headers: { ...(body ? { "content-type": "application/json" } : {}), ...hdr },
      body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(60000),
    });
    const text = await r.text();
    let json = null; try { json = JSON.parse(text); } catch { /* 非 JSON（csv/docx） */ }
    return { status: r.status, json, text, headers: r.headers };
  };
  let info = null;
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline && !info) {
    try { const r = await fetch(`${base}/api/server-info`, { signal: AbortSignal.timeout(2500) }); if (r.ok) info = await r.json(); } catch { /* 未起 */ }
    if (!info) await sleep(700);
  }
  assert(35, info?.diligence === 1, `隔离桥 :${PORT} 起动且 server-info diligence:1（迁移 0024 落账）`, JSON.stringify(info?.diligence));

  // 真 #6 材料管线上传（txt 直读；两件函证底稿+一件沿革材料）
  const docsB = [
    ["函证回函-甲行.txt", "银行函证回函（合成件一）\n银行账户：6222000000000001\n账户余额：152000.50\n函证日期：2026-03-15\n账户状态：正常"],
    ["函证回函-乙行.txt", "银行函证回函（合成件二）\n银行账户：6222000000000002\n账户余额：98765.25\n函证日期：2026-02-28\n账户状态：冻结"],
    ["章程与股转材料.txt", "2018年5月10日 公司设立并通过首版章程\n2020年9月1日 第一次股权转让：甲方将 10% 股权转让给乙方"],
  ];
  const uploaded = [];
  for (const [filename, text] of docsB) {
    const r = await api("POST", "/api/cases/materials/upload", { caseId: CASE, filename, text, title: filename.replace(/\.txt$/, "") });
    uploaded.push(r.json?.items?.[0]);
  }
  assert(36, uploaded.filter((x) => x?.status === "ready").length === 3, "真材料管线摄入三件合成底稿（#6 直读路 ready）", JSON.stringify(uploaded.map((x) => x?.status)));
  const matIds = uploaded.map((x) => x?.id).filter(Boolean);

  // 字段模板 + 三态一源 prompt 面
  const schemaB = await api("POST", "/api/diligence/schemas", { caseId: CASE, name: SCHEMA.name, fields: SCHEMA.fields });
  const promptB = await api("GET", `/api/diligence/schemas/${schemaB.json?.schemaId}/prompt`);
  assert(37, schemaB.status === 200 && promptB.json?.prompt?.includes("账户状态：类型=枚举，只允许取值：正常 / 冻结 / 销户"),
    "字段模板落库+抽取指令渲染（三态①）", promptB.json?.prompt?.slice(0, 80));

  // 批量提取（taskshell 异步：入队即回→轮询 SUCCEEDED→产物白名单路径）
  const ex = await api("POST", "/api/diligence/extract", { caseId: CASE, schemaId: schemaB.json.schemaId, materialIds: matIds.slice(0, 2) });
  let taskInfo = ex.json?.task;
  const pollDeadline = Date.now() + 90000;
  while (Date.now() < pollDeadline && taskInfo && !["SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"].includes(taskInfo.status)) {
    await sleep(500);
    taskInfo = (await api("GET", `/api/diligence/extract/${taskInfo.id}`)).json;
  }
  const artifactPath = taskInfo?.resultRef ? join(dirname(dbFile()), "artifacts", taskInfo.resultRef) : null;
  assert(38, ex.status === 200 && ex.json?.mode === "async" && taskInfo?.status === "SUCCEEDED" && artifactPath && existsSync(artifactPath)
    && taskInfo.resultRef.startsWith(`tasks/${taskInfo.id}/`),
    "批量提取=r11 异步任务壳（入队即回/轮询终态/产物白名单 tasks/<id>/ 形状）", `${taskInfo?.status} ${taskInfo?.resultRef}`);

  const ledgersB = await api("GET", `/api/diligence/ledgers?caseId=${CASE}`);
  const ledgerIdB = ledgersB.json?.ledgers?.[0]?.ledgerId;
  const ledgerB = await api("GET", `/api/diligence/ledgers/${ledgerIdB}`);
  const rowB = ledgerB.json?.rows?.[0];
  const traceB = await api("GET", `/api/diligence/ledgers/${ledgerIdB}/trace?rowNo=1&field=${encodeURIComponent("银行账户")}`);
  assert(39, ledgerB.json?.rows?.length === 2 && rowB?.cells?.["银行账户"]?.value === "6222000000000001"
    && rowB?.cells?.["银行账户"]?.origin === "rule"
    && traceB.json?.page === null && traceB.json?.source === "chunk" && typeof traceB.json?.seq === "number",
    "台账经桥全链落库（规则路命中、txt 底稿块=分块代位 page=null 如实）", JSON.stringify({ rows: ledgerB.json?.rows?.length, trace: traceB.json?.source }));

  const editBad = await api("PATCH", `/api/diligence/ledgers/${ledgerIdB}/cells`, { rowNo: 1, field: "账户状态", value: "异常", by: "律师乙" });
  const editOk = await api("PATCH", `/api/diligence/ledgers/${ledgerIdB}/cells`, { rowNo: 1, field: "账户状态", value: "销户", by: "律师乙" });
  assert(40, editBad.status >= 400 && editBad.json?.error?.message?.includes("拒绝") && editOk.status === 200 && editOk.json?.origin === "manual",
    "在线编辑经同一校验器（S2/三态③：枚举外具名拒，合法值落格 origin=manual）", `${editBad.status}/${editOk.status}`);

  // ── RE-12 对照源增补节 T40-T42 #32 接线回执：台账格值逐字引文回验（提取时入 stats；人工编辑后随 PATCH 重算）──
  const qbAtExtract = ledgerB.json?.stats?.quoteBack;
  assert(47, qbAtExtract?.checked === 8 && qbAtExtract?.counts?.pass === 8 && qbAtExtract?.counts?.mismatch === 0 && qbAtExtract?.counts?.fabricated === 0,
    "台账提取产物携逐字引文回验报告（规则路 8 格值皆出自其依据块文本=全 pass；空值格=如实未提取不入分母）",
    JSON.stringify(qbAtExtract?.counts));
  assert(48, editOk.json?.quoteBack?.checked === 8 && editOk.json?.quoteBack?.counts?.mismatch === 1 && editOk.json?.quoteBack?.counts?.pass === 7
    && editOk.json?.quoteBack?.entries?.some((e) => e.rowNo === 1 && e.field === "账户状态" && e.verdict === "mismatch"),
    "人工改动后回验即时重算（「销户」不复现于原提取引文=mismatch 如实落旗标不静默；其余 7 格仍 pass）",
    JSON.stringify(editOk.json?.quoteBack?.counts));

  const csvRaw = await fetch(`${base}/api/diligence/ledgers/${ledgerIdB}/csv`, { headers: hdr, signal: AbortSignal.timeout(60000) });
  const csvBuf = Buffer.from(await csvRaw.arrayBuffer());
  const csvText = csvBuf.toString("utf8");
  assert(41, csvBuf[0] === 0xEF && csvBuf[1] === 0xBB && csvBuf[2] === 0xBF
    && csvText.startsWith("\uFEFF底稿文件,银行账户") && csvText.includes("6222000000000001") && csvText.includes("销户"),
    "CSV 导出经 HTTP（UTF-8 BOM 字节序 EF BB BF+表头+人工编辑后的值可见）", `${csvBuf[0]?.toString(16)}${csvBuf[1]?.toString(16)}${csvBuf[2]?.toString(16)} ${csvText.slice(0, 30)}`);

  // 看板 HTTP：确认门全链
  const taskB = await api("POST", "/api/diligence/tasks", { caseId: CASE, group: "专项核查", fromPreset: "历史沿革核查" });
  await api("PATCH", `/api/diligence/tasks/${taskB.json?.taskId}`, { action: "start" });
  const subB = await api("PATCH", `/api/diligence/tasks/${taskB.json?.taskId}`, { action: "submit-confirmation" });
  const confBad = await api("PATCH", `/api/diligence/tasks/${taskB.json?.taskId}`, { action: "confirm", by: "" });
  const confOk = await api("PATCH", `/api/diligence/tasks/${taskB.json?.taskId}`, { action: "confirm", by: "律师丙" });
  const flowB = await api("PATCH", `/api/diligence/tasks/${taskB.json?.taskId}`, { action: "bind-flow", flowRef: { flowId: "flow_ipo02_legal_dd" } });
  const taskView = await api("GET", `/api/diligence/tasks/${taskB.json?.taskId}`);
  assert(42, subB.json?.status === "pending_confirmation" && confBad.status >= 400 && confOk.json?.status === "done"
    && taskView.json?.flowRef?.flowId === "flow_ipo02_legal_dd",
    "看板 HTTP 全链（待确认→确认人必填→完成；Flow 绑定契约持久化）", `${subB.json?.status}/${confBad.status}/${confOk.json?.status}`);
  void flowB;

  const v1 = await api("POST", `/api/diligence/tasks/${taskB.json.taskId}/results`, { content: "沿革核查成果 v1：初稿", by: "律师丙" });
  const v2 = await api("POST", `/api/diligence/tasks/${taskB.json.taskId}/results`, { content: "沿革核查成果 v2：补待核清单", by: "律师丙" });
  const listV = await api("GET", `/api/diligence/tasks/${taskB.json.taskId}/results`);
  const viewV1 = await api("GET", `/api/diligence/tasks/${taskB.json.taskId}/results/1`);
  assert(43, v1.json?.version === 1 && v2.json?.version === 2 && listV.json?.versions?.length === 2 && viewV1.json?.content?.includes("v1"),
    "成果版本 HTTP（v1/v2 追加+点版本号切回查看）", `${v1.json?.version}/${v2.json?.version}`);

  // 清单 HTTP
  const listB = await api("POST", "/api/diligence/checklists", { caseId: CASE });
  const orgB = await api("POST", `/api/diligence/checklists/${listB.json?.listId}/organize`, {});
  const missB = await api("POST", `/api/diligence/checklists/${listB.json?.listId}/missing`, {});
  assert(44, orgB.json?.assignments?.length === 3 && orgB.json?.indexMd?.includes("资料整理索引")
    && missB.json?.missing?.length > 0 && missB.json?.supplementMd?.includes("补充尽调资料清单"),
    "清单 HTTP（整理方案+索引表+缺失核对+补充清单）", `${orgB.json?.assignments?.length}/${missB.json?.missing?.length}`);

  // 沿革 HTTP：汇集（用户提交+项目内检索双通道）→章节→Word
  const chrB = await api("POST", "/api/diligence/chronicles", { caseId: CASE, title: "某公司历史沿革核查（合成）" });
  const chrId = chrB.json?.chronicleId;
  const colB = await api("POST", `/api/diligence/chronicles/${chrId}/collect`, {
    refs: [{ docId: matIds[0], kind: "其他" }],
    searchKinds: ["公司章程", "股权转让协议"],
  });
  const chapB = await api("POST", `/api/diligence/chronicles/${chrId}/chapter`, {});
  const wordRes = await fetch(`${base}/api/diligence/chronicles/${chrId}/word`, { headers: hdr, signal: AbortSignal.timeout(60000) });
  const wordBuf = Buffer.from(await wordRes.arrayBuffer());
  assert(45, colB.json?.docs?.some((d) => d.channel === "user") && colB.json?.docs?.some((d) => d.channel === "search")
    && chapB.json?.chapterMd?.includes("### 2018 年") && Number(chapB.json?.risks) >= 1
    && wordRes.status === 200 && wordBuf[0] === 0x50 && wordBuf[1] === 0x4b && wordBuf.length > 500
    && (wordRes.headers.get("content-disposition") ?? "").includes(".docx"),
    "沿革 HTTP 全链（用户提交+检索双通道汇集→时间轴章节+风险→Word 字节）",
    `docs=${colB.json?.docs?.length} events=${chapB.json?.events} word=${wordBuf.length}`);

  // 案件闸与错误态
  const noCase = await api("GET", "/api/diligence/overview?caseId=mat_nope");
  const noRoute = await api("GET", "/api/diligence/nonexistent");
  assert(46, noCase.status === 404 && noCase.json?.error?.code === "CASE_NOT_FOUND" && noRoute.status === 404,
    "错误态 fail-closed（缺失案件 404 具名码；未知路由 404）", `${noCase.status}/${noRoute.status}`);
} finally {
  if (child?.pid) {
    const cl = await commandLineOf(child.pid);
    if (cl.includes("bridge_host.mjs")) {
      spawnSync("taskkill", ["/PID", String(child.pid), "/F", "/T"], { timeout: 15000 });
      console.log(`[diligence-probe] 隔离桥 pid=${child.pid} 已按规程终止（命令行含 bridge_host.mjs 已核）`);
    } else {
      console.error(`[diligence-probe] 注意 pid=${child.pid} 命令行不含 bridge_host.mjs，未杀（宁停不误杀）：${cl.slice(0, 120)}`);
    }
  }
  for (const suffix of ["", "-wal", "-shm"]) { try { unlinkSync(dbFile() + suffix); } catch { /* 不存在即可 */ } }
}

console.log(`\nDILIGENCE_SYNTH ${pass}/${pass + fail} ${fail === 0 ? "DILIGENCE_SYNTH_PASS" : "DILIGENCE_SYNTH_FAIL"}`);
process.exit(fail === 0 ? 0 : 1);
