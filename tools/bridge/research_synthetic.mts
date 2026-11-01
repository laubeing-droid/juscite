// 功能 #16 调研报告合成用例（步骤4·RE-16 验收口径，全部合成材料）：
//   纯函数段（共享模型 researchModel.ts 单源）：
//   ①即时规划 5 条内插 ②规划评分器（+20/+4/+2/-5/-12、裸执行日志行终结候选组、日志前缀剔除、
//   两级降级）③编号分隔双判定器分立（UI [.)、：:] / loop [.)、．]，B12）④阶段号中英数字
//   ⑤三桶切分 ⑥报告完整性（trim≥300+节名≥4/5）⑦证据门（mcp_search 不计/装饰不计/isError 不计/
//   ≥160/案号）⑧工具目录剔除 ⑨配额错误族（403/forbidden 不判）⑩裸话题（中文逗号不豁免）
//   ⑪导出预处理（框图围栏/||| 列表/H1 截取/空行折叠）⑫编辑落账 ⑬导出命名 ⑭提示词装配
//   （五要素+首选源+续跑指令）⑮记录工厂/坏数据容错 ⑯法规库兜底（三策略/位阶/时效/fail-closed）
//   桥面段（自管隔离桥 BRIDGE_TEST_PORT 默认 3076 + mock oc28 + 合成法规索引；
//   不碰 :3030/:43127）：
//   ⑰空课题/裸话题拒 ⑱researchRun 记录+即时规划+独立会话（B07/B08/B09）⑲主对话列表隔离+
//   直发拒绝（B09 双闸）⑳回合链：首跳不完整→续跑→完整报告落 done（B24）+阶段播报+规划替换
//   ㉑researchThreadState 派生三桶 ㉒编辑落账 revision（B43）㉓导出 Word/MD（B39/B41/B42）
//   ㉔手动停止（B37）+删除 running 先停（B44）+链尾不复活已删行 ㉕杀桥重启记录不丢（B46）
//   ㉖检索通道断开→连接中断前缀 error（B34）㉇法规兜底通道+库缺失 fail-closed（B31/B06）
//   ㉘-㉛ B15/B23/B27·B22·B26·B30 指令注入与收口 ㉜ B51 证据齐→综合收敛指令（对拍 53）
//   ㉝ 技能触发合同（对拍 50）：skills 清单注册+/research、/调研 斜线分发+空/裸课题本地兜住
// 末行 RESEARCH_SYNTH_PASS / RESEARCH_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, mkdirSync, openSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AddressInfo } from "node:net";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import {
  instantPlan, extractPlan, isPlanPublished, isUiNumberedItem, extractStageNo,
  splitResearchStream, isReportComplete, reportSectionHits,
  evidenceGate, cullToolCatalog, isQuotaAuthError, isBareResearchTopic,
  preprocessReportMarkdown, applyReportEdit, exportFileName,
  buildResearchPrompt, primarySourceDirective, buildStageDirective,
  newResearchRecord, normalizeRecord, deriveFromRows,
  lookupLawsLibrary, validityOf, LAW_LOOKUP_UNAVAILABLE,
  type ResearchRecord,
} from "../../packages/juscite-legal/src/kernel/researchModel.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3076);
const SCRATCH = join(REPO_ROOT, ".local", `re16-scratch-${Date.now()}`);
const NODE = process.execPath;
const results: Array<{ name: string; ok: boolean }> = [];
function check(name: string, ok: boolean, detail = "") {
  results.push({ name, ok });
  console.log(`[re16-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ═══ 纯函数段 ═══
// ① 即时规划
const ip = instantPlan("企业间借贷合同效力");
check("即时规划 5 条编号+主题内插", (ip.match(/^\d+\.\s/gm) ?? []).length === 5 && ip.includes("企业间借贷合同效力"), ip.slice(0, 60));

// ② 规划评分器
const planText = [
  "调研规划：网络直播带货纠纷",
  "1. 检索直播带货相关的现行法律法规与司法解释",
  "2. 收集直播带货纠纷的典型案例与裁判要旨",
  "3. 分析平台责任的构成要件与免责事由",
  "接下来我先检查一下已有的检索结果",
  "4. 输出调研报告并核对来源",
].join("\n");
const pe = extractPlan(planText);
check("规划提取：裸执行日志行终结候选组（切分语义，第一组 3 项）", pe.plan !== null && (pe.plan.match(/^\d+\./gm) ?? []).length === 3 && pe.candidates.length === 2, `items=${(pe.plan?.match(/^\d+\./gm) ?? []).length} groups=${pe.candidates.length}`);
const c0 = pe.candidates[0];
check("评分器：显式标题+20、每项+4、动作词+2", c0 && c0.title !== null && c0.score === 20 + 3 * 4 + 3 * 2, `score=${c0?.score}`);
const dropText = [
  "调研规划：测试",
  "1. 检索法规",
  "2. 收集案例",
  "3. 分析风险",
  "4. 我需要先复述系统要求再开始",
].join("\n");
const pe2 = extractPlan(dropText);
check("评分器：日志前缀条目剔除并计 -5", pe2.plan !== null && (pe2.plan.match(/^\d+\./gm) ?? []).length === 3 && pe2.candidates[0]?.removed === 1,
  `items=${(pe2.plan?.match(/^\d+\./gm) ?? []).length} removed=${pe2.candidates[0]?.removed}`);
const metaText = "好的，下面是你的任务：\n调研规划：测试\n1. 检索法规\n2. 收集案例\n3. 分析风险";
const pe3 = extractPlan(metaText);
check("评分器：元语境 -12", pe3.plan !== null && pe3.candidates[0] && pe3.candidates[0].score === 20 + 12 + 6 - 12, `score=${pe3.candidates[0]?.score}`);
const bullets = "要点如下：\n- 检索法规\n- 收集案例\n- 分析风险";
check("降级②要点列表", extractPlan("无编号结构\n" + bullets).plan !== null, "");
const sentences = "这是第一句关于课题的说明文字。这是第二句关于课题范围界限的文字说明。这是第三句关于成果交付形态的说明文字。";
check("降级③按句切分", extractPlan(sentences).plan !== null, "");

// ③ 编号分隔双判定器（B12 两口径分立）
check("UI 口径收冒号", isUiNumberedItem("1：检索法规"), "");
check("UI 口径不收全角点", !isUiNumberedItem("１．检索法规") && !isUiNumberedItem("1．检索法规"), "");
check("loop 口径收全角点（发布判定）", isPlanPublished("调研规划\n1．检索法规\n2．收集案例\n3．分析风险"), "");
check("loop 口径不收冒号（发布判定）", !isPlanPublished("调研规划\n1：检索法规\n2：收集案例\n3：分析风险"), "");

// ④ 阶段号
check("阶段号：阶段四→4", extractStageNo("阶段四：法规检索") === 4, "");
check("阶段号：第5阶段→5", extractStageNo("第5阶段 案例收集") === 5, "");
check("阶段号：步骤十二→12", extractStageNo("步骤十二 综合整理") === 12, "");
check("阶段号：越界 100→null", extractStageNo("第100阶段") === null, "");

// ⑤ 三桶切分
const mixed = [
  "## 调研规划",
  "1. 检索法规",
  "2. 收集案例",
  "3. 输出报告",
  "",
  "## 阶段一",
  "已梳理课题焦点，开始法规检索。",
  "",
  "## 结论与建议",
  "综合来看，本案倾向于支持原告主张。",
].join("\n");
const sp = splitResearchStream(mixed, 1234567);
check("三桶切分：规划/阶段/报告", sp.planning !== null && sp.planning.includes("调研规划") && sp.updates.length === 1
  && sp.updates[0].text.includes("阶段一") && sp.summary.startsWith("## 结论与建议"),
  `planning=${sp.planning !== null} updates=${sp.updates.length} summary=${sp.summary.slice(0, 12)}`);
check("阶段号优先于顺序号（模型阶段号入播报）", sp.updates[0] !== undefined && extractStageNo(sp.updates[0].text) === 1, "");

// ⑥ 报告完整性
const full = [
  "## 结论与建议", "综合全部分析，本案请求权基础成立，建议以合同违约作为主要主张，并同时准备不当得利的备位主张，以应对合同效力被否定的风险；同时在庭前补强履约与催告证据，降低举证不能的风险。",
  "## 法律依据与效力", "（一）《合成民法典》第二百零九条，现行有效，效力层级为法律；（二）《合成司法解释》第一条，现行有效。",
  "## 相关案例", "（2023）合01民终1234号：同类案件支持违约主张；（2022）合01民初5678号：备位主张获支持。",
  "## 分析与风险", "主要风险在于证据链是否完整；次要风险在于诉讼时效起算点的认定分歧，建议提前准备中断证据。",
  "## 来源与核验", "以上法条与案例均来自所内合成法规库与合成案例库，核验状态为现行有效。",
].join("\n");
check("完整性：五节+≥300 字 → true", isReportComplete(full), `hits=${reportSectionHits(full)} len=${[...full].length}`);
check("完整性：仅两节 → false", !isReportComplete("## 结论与建议\n支持。\n## 来源与核验\n合成库。"), `hits=${reportSectionHits("## 结论与建议\n支持。\n## 来源与核验\n合成库。")}`);
check("完整性：四节但 <300 字 → false", !isReportComplete(["## 结论与建议", "支持。", "## 法律依据与效力", "第N条。", "## 相关案例", "案号。", "## 来源与核验", "库。"].join("\n")), "");

// ⑦ 证据门
const gate = evidenceGate([
  { name: "laws_search", payloadText: "《合成民法典》" + "第五百零九条 当事人应当按照约定全面履行自己的义务。".repeat(9) },
  { name: "case_search", payloadText: "（2023）合01民终1234号 " + "本院认为，合同合法有效。".repeat(16) },
]);
check("证据门：法规+案例齐 → synthesisReady", gate.regulationReady && gate.caseReady && gate.synthesisReady, JSON.stringify(gate));
const gate2 = evidenceGate([{ name: "mcp_search", payloadText: "发现可用法规工具列表" + "x".repeat(200) }]);
check("证据门：mcp_search 发现不计证据", !gate2.regulationReady, "");
const gate3 = evidenceGate([
  { name: "laws_search", payloadText: "法规内容" + "x".repeat(200), isError: true },
  { name: "link_enhance", payloadText: "装饰链接" + "x".repeat(200) },
]);
check("证据门：isError 与装饰类不计", !gate3.regulationReady, "");
check("证据门：<160 字不计", !evidenceGate([{ name: "laws_search", payloadText: "太短" }]).regulationReady, "");

// ⑧ 工具目录剔除
const catalog = ["laws_search", "case_search", "web_search", "web_fetch", "link_enhance", "引证核验"];
const culled = cullToolCatalog(catalog, true);
check("证据就绪后剔除装饰类工具", !culled.includes("web_search") && !culled.includes("引证核验") && culled.includes("laws_search"), culled.join(","));
check("证据未就绪不动目录", cullToolCatalog(catalog, false).length === catalog.length, "");

// ⑨ 配额错误族
check("配额：90001→true", isQuotaAuthError("error 90001: points used up"), "");
check("配额：remaining points→true", isQuotaAuthError("no remaining points"), "");
check("配额：401→true", isQuotaAuthError("HTTP 401 unauthorized"), "");
check("配额：invalid key→true", isQuotaAuthError("invalid api key"), "");
check("配额：积分不足→true", isQuotaAuthError("账户积分不足，请充值"), "");
check("配额：quota exhausted→true", isQuotaAuthError("quota exhausted for this month"), "");
check("配额：403/forbidden 明确不判", !isQuotaAuthError("HTTP 403 Forbidden") && !isQuotaAuthError("forbidden by policy"), "");
check("配额：普通错误→false", !isQuotaAuthError("connection reset by peer"), "");

// ⑩ 裸话题
check("裸话题：中文逗号不豁免（婚姻家庭，财产分割）", isBareResearchTopic("婚姻家庭，财产分割"), "");
check("裸话题：问号豁免", !isBareResearchTopic("合同法第二十条规定了什么？"), "");
check("裸话题：指令动词不判", !isBareResearchTopic("请检索违约责任相关规定"), "");
const OVER49 = "这是一个用来验证超长上限的四十九字以上纯汉字话题词条目完全没有出现任何豁免标点符号确实已经超出了上限";
check("裸话题：过短/过长不判", !isBareResearchTopic("合同效") && !isBareResearchTopic(OVER49) && isBareResearchTopic("物权确认"), `[4字]->${isBareResearchTopic("物权确认")} over49len=${[...OVER49].length}`);
check("裸话题：上下文指代不判", !isBareResearchTopic("这个继续深入一下"), "");

// ⑪ 导出预处理
const box = "前置文字\n┌─────┬────┐\n│ a   │ b  │\n└─────┴────┘\n后置文字";
check("预处理：框图围栏化", preprocessReportMarkdown(box).includes("```text") && preprocessReportMarkdown(box).includes("│ a   │ b  │"), "");
const pipe = "对比项 ||| 甲方案 ||| 乙方案";
const piped = preprocessReportMarkdown(pipe);
check("预处理：||| 转两空格缩进列表（前导空格保留）", piped.startsWith("- 对比项") && (piped.match(/^  - /gm) ?? []).length === 2 && piped.includes("  -  甲方案") && piped.includes("乙方案"), piped.slice(0, 48));
check("预处理：规划 H1 前剥离", preprocessReportMarkdown("# 调研规划\n1. x\n\n# 结论与建议\n正文").startsWith("# 结论与建议"), "");
check("预处理：4+ 空行折叠", !/\n{5,}/u.test(preprocessReportMarkdown("a\n\n\n\n\n\n\nb")), "");

// ⑫ 编辑落账
const edRec = { summary: "旧", editedSummary: undefined, reportRevision: undefined, updatedAt: 1 };
const ed = applyReportEdit(edRec as never, "新报告", 777);
check("编辑落账：summary=editedSummary+revision", ed.summary === "新报告" && ed.editedSummary === "新报告" && ed.reportRevision === 777, "");

// ⑬ 导出命名
check("导出命名：前缀+30 字+非法字符清洗+.docx 强制",
  exportFileName('企业借贷/效力:问题' + "很".repeat(40), ".docx") === "调研报告_企业借贷_效力_问题很很很很很很很很很很很很很很很很很很很很很很很很很很很很很.docx"
  || (exportFileName('企业借贷/效力:问题', ".docx").startsWith("调研报告_企业借贷_效力_问题") && exportFileName("abc", ".docx").endsWith(".docx")),
  exportFileName('企业借贷/效力:问题', ".docx"));
check("导出命名：md 后缀强制", exportFileName("课题", ".md") === "调研报告_课题.md", exportFileName("课题", ".md"));

// ⑭ 提示词装配
const prompt = buildResearchPrompt("股东出资纠纷");
check("提示词：五要素+课题内插", (prompt.match(/^\d\./gm) ?? []).length === 5 && prompt.includes("股东出资纠纷") && !prompt.includes("网页替代"), "");
check("首选源指令：pkulaw→北大法宝；未知→null",
  (primarySourceDirective("pkulaw") ?? "").includes("北大法宝") && (primarySourceDirective("pkulaw") ?? "").includes("web 检索") && primarySourceDirective("nope") === null, "");
check("续跑阶段指令：不重复规划+直接交付", buildStageDirective({ hasPlan: true, continuation: true }).includes("不要重新规划") && buildStageDirective({ hasPlan: true, continuation: true }).includes("完整报告"), "");

// ⑮ 记录工厂/容错
const rec0 = newResearchRecord("  课题  ", 1690000000000);
check("记录工厂：id=时间戳串+trim+初始即时规划", rec0.id === "research-1690000000000" && rec0.query === "课题" && rec0.status === "running" && (rec0.planning ?? "").includes("1."), "");
check("坏数据容错：非对象/缺 id → null", normalizeRecord(null) === null && normalizeRecord({}) === null && normalizeRecord({ id: "x", status: "weird" })?.status === "running", "");
const dv = deriveFromRows([
  { kind: "userInput", text: "课题" },
  { kind: "assistantText", text: "## 阶段一\n检索完成。\n\n## 结论与建议\n支持。", reasoning: "先想清楚结构" },
  { kind: "assistantText", text: "failed 行不计", state: "failed" },
]);
check("派生：三桶+reasoning+失败行不计", dv.updates.length === 1 && dv.summary.startsWith("## 结论与建议") && dv.reasoning === "先想清楚结构", `updates=${dv.updates.length}`);

// ⑯ 法规库兜底（纯函数）
const lawEntries = [
  { id: "2", name: "合成监管条例（旧版）", level: "法律", filename: "旧版.md", valid_from: "2000-01-01", valid_to: "2019-12-31" },
  { id: "1", name: "合成监管条例", level: "法律", filename: "合成监管条例.md", valid_from: "2020-01-01", valid_to: "2099-12-31", content: "第一条 违约责任由违约方承担。" },
  { id: "3", name: "合成监管条例实施拾遗", level: "行政法规", filename: "拾遗.md", valid_to: "2099-12-31" },
  { id: "4", name: "合成批复", level: "规范性文件", filename: "批复.md" },
];
const lk = lookupLawsLibrary(lawEntries, "合成监管条例");
const idxOf = (id: string) => lk.hits.findIndex((h) => h.id === id);
check("法规兜底：标题精确>模糊、现行>已废止", lk.ok && lk.hits[0]?.id === "1" && lk.hits[0]?.validity === "现行"
  && idxOf("3") < idxOf("2") && lk.hits.find((h) => h.id === "2")?.validity === "已废止",
  `hits=${lk.hits.map((h) => h.id + ":" + h.validity).join(",")}`);
check("法规兜底：正文模糊命中", (lookupLawsLibrary(lawEntries, "违约责任").hits[0]?.id ?? "") === "1", "");
check("法规兜底：位阶排序（法律>行政法规>规范性文件）", (() => {
  const r = lookupLawsLibrary(lawEntries, "合成");
  const idx = (id: string) => r.hits.findIndex((h) => h.id === id);
  return idx("1") < idx("3") && idx("3") < idx("4");
})(), "");
check("时效标签：1970 墓碑→已废止、2099→现行", validityOf({ valid_to: "1970-01-01" }) === "已废止" && validityOf({ valid_to: "2099-12-31" }) === "现行", "");
check("fail-closed 话术就位", LAW_LOOKUP_UNAVAILABLE.includes("就此停止") && LAW_LOOKUP_UNAVAILABLE.includes("浏览器自动化"), "");

// ═══ 桥面段（mock oc28 + 隔离桥）═══
mkdirSync(SCRATCH, { recursive: true });
const LAWS_INDEX = join(SCRATCH, "laws-index.json");
writeFileSync(LAWS_INDEX, JSON.stringify(lawEntries), "utf-8");

// ── mock oc28：确定性回合（首跳不完整→续跑完整；挂起模式供停止测试）──
const FULL_REPORT = [
  "## 阶段二",
  "检索完成，进入综合整理。",
  "",
  "## 结论与建议",
  "综合全部分析，本案请求权基础成立，建议以合同违约作为主要主张，并同时准备不当得利的备位主张，以应对合同效力被否定的风险；同时在庭前补强履约与催告证据，降低举证不能的风险。",
  "## 法律依据与效力",
  "（一）《合成民法典》第二百零九条，现行有效，效力层级为法律；（二）《合成司法解释》第一条，现行有效。",
  "## 相关案例",
  "（2023）合01民终1234号：同类案件支持违约主张；（2022）合01民初5678号：备位主张获支持。",
  "## 分析与风险",
  "主要风险在于证据链是否完整；次要风险在于诉讼时效起算点的认定分歧，建议提前准备中断证据。",
  "## 来源与核验",
  "以上法条与案例均来自所内合成法规库与合成案例库，核验状态为现行有效。",
].join("\n");
const ANNOUNCE_TEXT = "接下来我将调用检索工具查找相关法规依据，然后整理成文。";
const HOP1_TEXT = [
  "## 调研规划",
  "1. 检索股东出资纠纷相关法律法规（模型规划版）",
  "2. 收集典型裁判案例",
  "3. 按五节结构成文并核对来源",
  "",
  "## 阶段一",
  "已梳理课题焦点，开始法规与案例检索。",
].join("\n");
let MOCK_URL = "http://127.0.0.1:9"; // mock oc28 地址（listen 后回填）
type MockMsg = { id: string; type: string; error?: unknown; time: { created: number; completed?: number }; content: Array<Record<string, unknown>> };
const mockSessions = new Map<string, MockMsg[]>();
const mockPrompts = new Map<string, string[]>(); // 每会话收到的 prompt 回放
const mockSessionMode = new Map<string, string>(); // 会话级场景模式（quota/announce）
let mockMsgSeq = 0;
let mockHang = false; // true=不落 completed（挂起，供停止测试）
const mockServer = createServer((req, res) => {
  const url = req.url ?? "";
  if (req.method === "POST" && url === "/api/session") {
    void req.resume();
    res.writeHead(200, { "content-type": "application/json" });
    res.end("{}");
    return;
  }
  const promptM = req.method === "POST" && url.match(/^\/api\/session\/([^/]+)\/prompt$/);
  if (promptM) {
    let body = "";
    req.on("data", (c: Buffer) => { body += String(c); });
    req.on("end", () => {
      const sid = decodeURIComponent(promptM[1]);
      const parsed = JSON.parse(body || "{}") as { id?: string; text?: string };
      const promptText = parsed.text ?? "";
      if (!mockPrompts.has(sid)) mockPrompts.set(sid, []);
      mockPrompts.get(sid)!.push(promptText); // prompt 回放（指令注入断言面）
      const list = mockSessions.get(sid) ?? [];
      list.push({ id: parsed.id ?? ("u" + mockMsgSeq), type: "user", time: { created: Date.now() }, content: [{ type: "text", text: promptText }] });
      const isContinuation = promptText.includes("尚未形成完整");
      const isHang = promptText.includes("HANG_FOR_STOP"); // 挂起模式：不落 completed
      if (promptText.includes("宣布调用的走查测试课题")) mockSessionMode.set(sid, "announce");
      if (promptText.includes("证据门指令注入")) mockSessionMode.set(sid, "no_tool"); // 无工具首跳→B22 强制取证
      if (promptText.includes("配额切换的走查测试课题")) mockSessionMode.set(sid, "quota");
      if (promptText.includes("综合收敛的走查测试课题")) mockSessionMode.set(sid, "synthready"); // 首跳法规+案例双齐→B51 综合收敛
      const mode = mockSessionMode.get(sid) ?? "";
      const text = isContinuation ? (mode === "announce" ? ANNOUNCE_TEXT : FULL_REPORT)
        : mode === "announce" ? ANNOUNCE_TEXT
        : HOP1_TEXT;
      const isQuotaHop = mode === "quota" && !isContinuation; // 首跳回配额错误（B26）
      if (isHang) mockHang = true;
      const mid = "a" + (mockMsgSeq++);
      const created = Date.now();
      // 300ms 后落 assistant 消息；挂起模式不落 completed（桥侧轮询永不稳定→可稳定地先停再断言）
      setTimeout(() => {
        const l2 = mockSessions.get(sid) ?? [];
        const parts: Array<Record<string, unknown>> = [{ type: "text", text }];
        if (!isContinuation && mode === "") { // 仅默认会话首跳带工具证据（no_tool 会话不带→触发强制取证）
          // 首跳带 tool-call parts（B15/B23）：laws_search 正常 + case_search 报错（法规证据单齐→剔除指令路）
          parts.push({ type: "tool-call", name: "laws_search", input: "合成监管条例", output: "《合成民法典》" + "第五百零九条 当事人应当按照约定全面履行自己的义务。".repeat(9) });
          parts.push({ type: "tool-call", name: "case_search", input: "股东出资 案例检索", error: "case backend boom" });
        }
        if (!isContinuation && mode === "synthready") { // 首跳法规+案例双证据齐（B51 综合收敛路）
          parts.push({ type: "tool-call", name: "laws_search", input: "合成监管条例", output: "《合成民法典》" + "第五百零九条 当事人应当按照约定全面履行自己的义务。".repeat(9) });
          parts.push({ type: "tool-call", name: "case_search", input: "股东出资 案例", output: "（2023）合01民终1234号 股东出资纠纷案 " + "裁判要旨合成文本，出资不实的股东应在未出资本息范围内承担补充赔偿责任。".repeat(12) });
        }
        const msg: MockMsg = { id: mid, type: "assistant", time: { created }, content: parts as MockMsg["content"] };
        if (!isHang && !isQuotaHop) msg.time.completed = Date.now();
        if (isQuotaHop) { msg.error = { message: "Error 90001: no remaining points" }; }
        l2.push(msg);
        mockSessions.set(sid, l2);
      }, 300);
      mockSessions.set(sid, list);
      res.writeHead(200, { "content-type": "application/json" });
      res.end("{}");
    });
    return;
  }
  const listM = req.method === "GET" && url.match(/^\/api\/session\/([^/]+)\/message$/);
  if (listM) {
    const sid = decodeURIComponent(listM[1]);
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ data: mockSessions.get(sid) ?? [] }));
    return;
  }
  res.writeHead(404); res.end("{}");
});
const mockListening = new Promise<void>((resolve) => mockServer.listen(0, "127.0.0.1", () => resolve()));
await mockListening;
const mockPort = (mockServer.address() as AddressInfo).port;
MOCK_URL = `http://127.0.0.1:${mockPort}`;

let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, ".local", `re16-synth-bridge-${PORT}.log`), "a");
function spawnBridge() {
  const env = { ...process.env, BRIDGE_PORT: String(PORT), BRIDGE_LAWS_INDEX: LAWS_INDEX, BRIDGE_OC28_SSE: "0",
  BRIDGE_OC28_URL: MOCK_URL, BRIDGE_OC28_PASSWORD: "synthetic" }; // mock oc28（禁回落真 serve）
  const child = spawn(NODE, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: ["ignore", bridgeLog, bridgeLog], detached: true });
  child.unref();
  return child.pid;
}
async function probe() {
  try {
    const r = await fetch(`http://127.0.0.1:${PORT}/api/server-info`, { signal: AbortSignal.timeout(2500) });
    return r.ok && JSON.parse(await r.text()).store === "sqlite";
  } catch { return false; }
}
async function waitProbe(timeoutMs: number) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) { if (await probe()) return true; await sleep(500); }
  return false;
}
async function killBridge() {
  if (!bridgePid) return;
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${bridgePid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  if (!String(r.stdout ?? "").includes("bridge_host.mjs")) {
    throw new Error(`拒绝杀进程 pid=${bridgePid}：命令行不含 bridge_host.mjs，宁停不误杀`);
  }
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probe())) await sleep(500);
  bridgePid = 0;
}
async function preflightClearPort() {
  if (await probe()) {
    const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
    const pids = new Set<number>();
    for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
      if (Number(m[1]) === PORT) pids.add(Number(m[2]));
    }
    for (const pid of pids) {
      const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
        `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
        { encoding: "utf-8", timeout: 20000 });
      if (String(q.stdout ?? "").includes("bridge_host.mjs")) {
        spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
        console.log(`[re16-synth] 清场：杀掉残留桥 pid=${pid}`);
      }
    }
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline && (await probe())) await sleep(500);
  }
  for (const suffix of ["", "-wal", "-shm"]) {
    try { rmSync(join(process.env.APPDATA ?? "", "Juscite", "bridge", `bridge-${PORT}.db${suffix}`), { force: true }); } catch { /* 留给下轮 */ }
  }
}

let call: <T>(m: string, a?: unknown) => Promise<T> = async () => { throw new Error("未连接"); };
let taskCall: <T>(m: string, a?: unknown) => Promise<T> = async () => { throw new Error("未连接"); };
let settingCall: <T>(m: string, a?: unknown) => Promise<T> = async () => { throw new Error("未连接"); };
let skillsCall: <T>(m: string, a?: unknown) => Promise<T> = async () => { throw new Error("未连接"); };
function connect(): Promise<void> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws`);
    ws.binaryType = "arraybuffer";
    const data = { fire: (_b: VSBuffer) => {} };
    ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
    ws.on("open", () => {
      const isocket = {
        onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
        onClose: () => ({ dispose: () => {} }),
        onEnd: () => ({ dispose: () => {} }),
        write: (b: VSBuffer) => ws.send(b.buffer),
        end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
      };
      // 单 ChannelClient 多通道（多 Client 共用同一 isocket 会互吞帧——kb_synthetic 实测踩坑）
      const client = new ChannelClient(new SocketProtocol(isocket as never));
      const ch = client.getChannel("zcode-agent");
      const tch = client.getChannel("zcode-task");
      const sch = client.getChannel("setting");
      const skch = client.getChannel("skills");
      call = async <T,>(m: string, a?: unknown) => ch.call<T>(m, a === undefined ? [] : [a]);
      taskCall = async <T,>(m: string, a?: unknown) => tch.call<T>(m, a === undefined ? [] : [a]);
      settingCall = async <T,>(m: string, a?: unknown) => sch.call<T>(m, a as never), // setting 通道封送不展开：直传对象（re16 探针实测）
      skillsCall = async <T,>(m: string, a?: unknown) => skch.call<T>(m, a === undefined ? [] : [a]);
      call("helloConversationV4").then(() => resolve()).catch(reject);
    });
    ws.on("error", reject);
  });
}
interface RecState { phase?: string; busy?: boolean; planning?: string | null; updates: Array<{ id: string; text: string }>; summary?: string; reasoning?: string }
async function waitRecordDone(id: string, timeoutMs = 90000): Promise<ResearchRecord | null> {
  const deadline = Date.now() + timeoutMs;
  let last: ResearchRecord | null = null;
  while (Date.now() < deadline) {
    last = await call<ResearchRecord | null>("researchRecordGet", { id });
    if (last && last.status !== "running") return last;
    await sleep(500);
  }
  return last;
}

// ═══ 桥面主流程 ═══
await preflightClearPort();
bridgePid = spawnBridge();
if (!(await waitProbe(40000))) { console.log("RESEARCH_SYNTH_FAIL"); console.error("桥 40s 不可探"); process.exit(1); }
await connect();

// ⑰ 空课题/裸话题拒
let threw = "";
try { await call("researchRun", { query: "   " }); } catch (e) { threw = String((e as Error).message ?? e); }
check("空课题拒绝", threw.includes("课题不能为空"), threw.slice(0, 40));
threw = "";
try { await call("researchRun", { query: "婚姻家庭，财产分割" }); } catch (e) { threw = String((e as Error).message ?? e); }
check("裸话题拒绝（B29）", threw.includes("话题词"), threw.slice(0, 40));

// ⑱⑲⑳ 正常调研：记录+即时规划+独立会话+续跑到完整
const run = await call<{ record: ResearchRecord; threadId: string }>("researchRun", { query: "请调研股东出资纠纷相关的法律规定与典型案例", model: { providerId: "deepseek-byok", modelId: "deepseek-chat" } });
const recId = run.record.id;
check("researchRun：running 记录+即时规划+ses_res 会话", run.record.status === "running" && (run.record.planning ?? "").includes("1.")
  && run.record.query === "请调研股东出资纠纷相关的法律规定与典型案例" && run.threadId.startsWith("ses_res_"), `id=${recId}`);
check("B09 主对话列表隔离（listTasks 无调研标题）", await (async () => {
  const tasks = await taskCall<Array<{ title?: string }>>("listTasks", {});
  return Array.isArray(tasks) && !tasks.some((t) => (t.title ?? "").startsWith("调研报告"));
})(), "");
const guard = await call<{ status?: string; reasonCode?: string }>("sendConversationCommandV4", { envelope: { type: "sendText", sessionId: run.threadId, payload: { text: "直发测试" } } });
check("B09 调研线程直发拒绝（双闸）", guard.status === "rejected" && guard.reasonCode === "guard.researchThreadDirectSend", JSON.stringify(guard).slice(0, 80));
const doneRec = await waitRecordDone(recId);
check("B24 回合链：首跳不完整→续跑→完整报告 done", doneRec?.status === "done" && (doneRec.summary ?? "").includes("结论与建议")
  && (doneRec.summary ?? "").includes("来源与核验"), `status=${doneRec?.status} len=${(doneRec?.summary ?? "").length}`);
check("B08 模型规划替换即时规划", (doneRec?.planning ?? "").includes("模型规划版"), (doneRec?.planning ?? "").slice(0, 40));
check("B14 阶段播报两条（阶段一+阶段二）", (doneRec?.updates ?? []).length === 2, `updates=${(doneRec?.updates ?? []).length}`);

// ㉑ 轮询投影派生
const ts = await call<RecState & { rows: Array<{ kind: string }> }>("researchThreadState", { threadId: run.threadId });
check("researchThreadState：派生三桶+rows 投影", ts.summary === doneRec?.summary && ts.updates.length === 2 && ts.rows.length >= 4,
  `updates=${ts.updates.length} rows=${ts.rows.length}`);
let tsThrew = "";
try { await call("researchThreadState", { threadId: "ses_res_不存在" }); } catch (e) { tsThrew = String((e as Error).message ?? e); }
check("未知调研会话诚实报错（B36 对账失败路）", tsThrew.includes("不存在"), tsThrew.slice(0, 40));

// ㉒ 编辑落账
const edited = await call<{ record: ResearchRecord }>("researchRecordEdit", { id: recId, summary: "编辑后的报告正文" });
check("B43 编辑落账：editedSummary+revision", edited.record.editedSummary === "编辑后的报告正文" && edited.record.summary === "编辑后的报告正文"
  && typeof edited.record.reportRevision === "number" && edited.record.reportRevision > 0, "");

// ㉓ 导出
const mdOut = await call<{ text: string; fileName: string }>("researchExportMd", { markdown: "# 调研规划\n1. x\n\n# 结论与建议\n对比项 ||| 甲 ||| 乙\n\n\n\n\n\n\n尾", query: "股东出资纠纷" });
check("B41/B42 MD 导出：预处理+命名", mdOut.fileName.startsWith("调研报告_股东出资纠纷") && mdOut.text.startsWith("# 结论与建议")
  && mdOut.text.includes("  -  甲") && !/\n{5,}/u.test(mdOut.text), mdOut.fileName); // 前导空格保留形态
const wordOut = await call<{ docxBase64: string; fileName: string; mode: string }>("researchExportWord", { markdown: doneRec?.summary ?? "", query: "股东出资纠纷" });
const zipHead = Buffer.from(wordOut.docxBase64, "base64").subarray(0, 2).toString("latin1");
check("B39/B40 Word 导出：docx 字节+标准转换+命名", zipHead === "PK" && wordOut.mode === "standard" && wordOut.fileName.endsWith(".docx")
  && wordOut.fileName.startsWith("调研报告_股东出资纠纷"), `${zipHead} ${wordOut.fileName}`);

// ㉔ 停止/删除
const run2 = await call<{ record: ResearchRecord; threadId: string }>("researchRun", { query: "HANG_FOR_STOP 请研究停止语义的测试课题" });
await sleep(1200); // 让首跳进入挂起轮询
const stopped = await call<{ record: ResearchRecord }>("researchStop", { id: run2.record.id });
check("B37 手动停止：停止终态+末帧补提交", stopped.record.status === "error" && (stopped.record.error ?? "").includes("已停止"), stopped.record.error ?? "");
const delRunning = await call<{ deleted: string }>("researchRecordDelete", { id: run2.record.id });
check("B44 删除 running 条目", delRunning.deleted === run2.record.id, "");
await sleep(1500);
const afterDel = await call<ResearchRecord | null>("researchRecordGet", { id: run2.record.id });
check("链尾不复活已删行", afterDel === null, `afterDel=${JSON.stringify(afterDel)?.slice(0, 40)}`);

// ㉘ B15 工具步骤面（tool-call parts→steps；错误步骤）+ B23 剔除指令 + B27 可用性注入
{
  const prompts1 = (() => {
    for (const texts of mockPrompts.values()) {
      if (texts.some((t) => t.includes("请调研股东出资纠纷相关的法律规定与典型案例"))) return texts;
    }
    return [];
  })();
  const doneSteps = await call<ResearchRecord | null>("researchRecordGet", { id: recId }); // 裸记录（无包装）
  const stepsRec = doneSteps?.steps ?? [];
  console.log("[re16-synth] debug recId=" + recId + " raw=" + JSON.stringify(doneSteps).slice(0, 1400));
  check("B27 首跳注入检索源可用性", prompts1[0]?.includes("所内法规库当前可用") === true, (prompts1[0] ?? "").slice(0, 40));
  check("B15 记录 steps：2 步（1 done 1 error）", stepsRec.length === 2
    && stepsRec.some((st) => st.tool === "laws_search" && st.status === "done" && st.icon === "statute")
    && stepsRec.some((st) => st.tool === "case_search" && st.status === "error" && (st.detail ?? "").includes("boom")),
    `steps=${stepsRec.map((x) => x.tool + ":" + x.status + ":" + (x.icon ?? "")).join(",")}`);
  const liveSteps = await call<{ steps: Array<{ tool: string; status: string }> }>("researchThreadState", { threadId: run.threadId });
  check("B15 轮询投影 steps 面板数据", liveSteps.steps.length === 2, `live=${liveSteps.steps.length}`);
  check("B23 法规证据就绪→剔除装饰类指令注入下一跳", (prompts1[1] ?? "").includes("不要再使用网页检索"), (prompts1[1] ?? "").slice(-60));
}

// ㉙ B22 证据未齐→强制取证指令注入
{
  const keysE = new Set(mockPrompts.keys());
  const runE = await call<{ record: ResearchRecord; threadId: string }>("researchRun", { query: "请调研证据门指令注入的走查测试课题" });
  await waitRecordDone(runE.record.id, 60000);
  const sidE = [...mockPrompts.keys()].find((k) => !keysE.has(k));
  const promptsE = mockPrompts.get(sidE ?? "") ?? [];
  check("B22 规划后证据未齐→强制取证指令注入下一跳", (promptsE[1] ?? "").includes("检索证据尚未齐备") && (promptsE[1] ?? "").includes("case_search"),
    (promptsE[1] ?? "").slice(-70));
}

// ㉚ B26 配额错误→切 web 兜底不再重试
{
  const keysQ = new Set(mockPrompts.keys());
  const runQ = await call<{ record: ResearchRecord; threadId: string }>("researchRun", { query: "请调研配额切换的走查测试课题" });
  const recQ = await waitRecordDone(runQ.record.id, 90000);
  const sidQ = [...mockPrompts.keys()].find((k) => !keysQ.has(k));
  const promptsQ = mockPrompts.get(sidQ ?? "") ?? [];
  check("B26 配额错误→兜底指令注入且不落连接中断", recQ?.status === "done" && (promptsQ[1] ?? "").includes("权威来源出现鉴权或配额类确定性错误"),
    `status=${recQ?.status} p2=${(promptsQ[1] ?? "").slice(-50)}`);
}

// ㉛ B30 宣布要调工具没调 ≤2 收口（第 3 次同类续跑即收口：3 跳 vs 无收口时的 6 跳）
{
  const keysA = new Set(mockPrompts.keys());
  const runA = await call<{ record: ResearchRecord; threadId: string }>("researchRun", { query: "请调研宣布调用的走查测试课题" });
  const recA = await waitRecordDone(runA.record.id, 120000);
  const sidA = [...mockPrompts.keys()].find((k) => !keysA.has(k));
  const promptCount = (mockPrompts.get(sidA ?? "") ?? []).length;
  check("B30 宣布没调三类续跑 ≤2 收口（3 跳收口，不跑满 6 跳）", recA?.status === "done" && (recA.summary ?? "") === "" && promptCount === 3,
    `status=${recA?.status} prompts=${promptCount} summaryLen=${(recA?.summary ?? "").length}`);
}

// ㉜ B51 证据齐→综合跳收敛指令（对拍 53 轻量期同构=指令收敛思考面；真实 reasoningEffort 随 oc28 面解挂）
{
  const keysS = new Set(mockPrompts.keys());
  const runS = await call<{ record: ResearchRecord; threadId: string }>("researchRun", { query: "请调研综合收敛的走查测试课题" });
  const recS = await waitRecordDone(runS.record.id, 90000);
  const sidS = [...mockPrompts.keys()].find((k) => !keysS.has(k));
  const promptsS = mockPrompts.get(sidS ?? "") ?? [];
  const stepsS = (await call<ResearchRecord | null>("researchRecordGet", { id: runS.record.id }))?.steps ?? [];
  check("B51 首跳双证据齐（steps 2 步全 done）", stepsS.length === 2 && stepsS.every((x) => x.status === "done"),
    `steps=${stepsS.map((x) => x.tool + ":" + x.status).join(",")}`);
  check("B51 法规+案例证据齐→综合收敛指令注入下一跳且报告落 done", recS?.status === "done"
    && (recS.summary ?? "").includes("结论与建议")
    && (promptsS[1] ?? "").includes("证据均已齐备") && (promptsS[1] ?? "").includes("直接整理"),
    `status=${recS?.status} p2=${(promptsS[1] ?? "").slice(-70)}`);
}

// ㉝ 技能触发合同（对拍 50）：BUILTIN_SKILLS 注册 + /research、/调研 斜线分发面
{
  const skills = await skillsCall<{ skills: Array<{ id: string; description: string; body: string }> }>("list");
  const rSkill = skills.skills.find((s) => s.id === "juscite-builtin-research");
  check("对拍50 skills 清单注册 research（/research、/调研 随描述在场+SKILL 正文随体）", Boolean(rSkill)
    && (rSkill?.description ?? "").includes("/research") && (rSkill?.description ?? "").includes("/调研")
    && (rSkill?.body ?? "").includes("法律调研"), (rSkill?.description ?? "").slice(0, 56));
  const cntBefore = (await call<{ records: ResearchRecord[] }>("researchRecordList", {})).records.length;
  const keysD = new Set(mockPrompts.keys());
  const ackD = await call<{ status?: string }>("sendConversationCommandV4",
    { envelope: { type: "sendText", sessionId: "ses_disp_check", payload: { text: "/调研 合成斜线派发的调研课题足够长" } } });
  check("对拍50 /调研 分发 accepted", ackD.status === "accepted", JSON.stringify(ackD).slice(0, 60));
  await sleep(800); // researchRun 在分发内 await：ack 即已落记录，此处仅等链启动
  const newRec = (await call<{ records: ResearchRecord[] }>("researchRecordList", {})).records
    .find((r) => r.query === "合成斜线派发的调研课题足够长");
  check("对拍50 /调研 分发建记录并走独立链至 done", Boolean(newRec) && (await waitRecordDone(newRec!.id, 90000))?.status === "done",
    `rec=${Boolean(newRec)}`);
  const sidD = [...mockPrompts.keys()].find((k) => !keysD.has(k));
  const pD = mockPrompts.get(sidD ?? "") ?? [];
  check("对拍50 派发走五要素模板（内部会话续跑）", (pD[0] ?? "").includes("法律调研助手") && pD.length >= 2, `hops=${pD.length}`);
  const cntMid = (await call<{ records: ResearchRecord[] }>("researchRecordList", {})).records.length;
  await call("sendConversationCommandV4", { envelope: { type: "sendText", sessionId: "ses_disp_check", payload: { text: "/调研" } } });
  await call("sendConversationCommandV4", { envelope: { type: "sendText", sessionId: "ses_disp_check", payload: { text: "/research 婚姻家庭，财产分割" } } });
  await sleep(600);
  const cntAfter = (await call<{ records: ResearchRecord[] }>("researchRecordList", {})).records.length;
  check("对拍50 空/裸课题分发不建记录（本地行兜住不触模型）", cntMid === cntBefore + 1 && cntAfter === cntMid,
    `before=${cntBefore} mid=${cntMid} after=${cntAfter}`);
}

// ㉕ 杀桥重启：记录不丢（RE-B1 持久化）
const beforeRestart = await call<{ records: ResearchRecord[] }>("researchRecordList", {});
await killBridge();
bridgePid = spawnBridge();
if (!(await waitProbe(40000))) { console.log("RESEARCH_SYNTH_FAIL"); console.error("重启桥 40s 不可探"); process.exit(1); }
await connect();
const afterRestart = await call<{ records: ResearchRecord[] }>("researchRecordList", {});
const beforeEdited = beforeRestart.records.find((r) => r.id === recId);
const afterEdited = afterRestart.records.find((r) => r.id === recId);
check("B46 杀桥重启：记录字段全等", Boolean(afterEdited) && JSON.stringify(beforeEdited) === JSON.stringify(afterEdited)
  && afterEdited?.status === "done" && afterEdited?.editedSummary === "编辑后的报告正文",
  `before=${beforeRestart.records.length} after=${afterRestart.records.length}`);

// ㉖ 检索通道断开 → 连接中断 error（B34）
await new Promise<void>((resolve) => mockServer.close(() => resolve()));
const run3 = await call<{ record: ResearchRecord; threadId: string }>("researchRun", { query: "请分析通道断开后的连接中断语义测试课题足够长" });
const errRec = await waitRecordDone(run3.record.id, 60000);
check("B34 无内容连接错误→中断前缀 error", errRec?.status === "error" && (errRec.error ?? "").startsWith("调研连接中断："), errRec?.error?.slice(0, 60));

// ㉇ 法规兜底通道 + fail-closed + B06 事实源
const st0 = await call<{ lawsAvailable: boolean; stealth: boolean; primaryLegalSource: string | null }>("researchStatus", {});
check("B06 researchStatus：法规库可用事实源", st0.lawsAvailable === true && st0.primaryLegalSource === null, JSON.stringify(st0));
const lk1 = await call<{ ok: boolean; hits: Array<{ id: string; validity: string }>; notice?: string }>("researchLegalLookup", { query: "违约责任" });
check("B31 法规兜底通道：正文模糊命中", lk1.ok && lk1.hits[0]?.id === "1", JSON.stringify(lk1.hits).slice(0, 60));
rmSync(LAWS_INDEX, { force: true });
const lk2 = await call<{ ok: boolean; hits: unknown[]; notice?: string }>("researchLegalLookup", { query: "合成监管条例" });
check("B31 库缺失 fail-closed（不升级浏览器自动化）", lk2.ok === false && lk2.hits.length === 0 && (lk2.notice ?? "").includes("浏览器自动化"), (lk2.notice ?? "").slice(0, 40));

// ⑱补 隐身 fail-closed（与 #20 同语义）
await settingCall("update", [{ stealthMode: { enabled: true } }]);
threw = "";
try { await call("researchRun", { query: "隐身模式下的调研请求课题" }); } catch (e) { threw = String((e as Error).message ?? e); }
await settingCall("update", [{ stealthMode: { enabled: false } }]);
check("隐身模式 fail-closed 拒绝", threw.includes("隐身模式"), threw.slice(0, 40));

// 清场
await killBridge();
mockServer.closeAllConnections?.();
mockServer.close();
try { rmSync(SCRATCH, { recursive: true, force: true }); } catch { /* 留给系统清理 */ }

const failed = results.filter((r) => !r.ok);
console.log(`[re16-synth] ── ${results.length - failed.length}/${results.length} PASS ──`);
if (failed.length) {
  console.log("RESEARCH_SYNTH_FAIL");
  for (const f of failed) console.error(`  FAIL: ${f.name}`);
  process.exit(1);
} else {
  console.log("RESEARCH_SYNTH_PASS");
}
