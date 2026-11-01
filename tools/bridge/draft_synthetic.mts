// 功能 #10 模板文书起草合成用例（RE-10 验收）：
//  A 引擎纯逻辑（模板集/匹配三态/渲染节序/借贷机检/文书判定/预算/prompt 装配/结算双通道/交付锚点提取+终稿机检）；
//  B 存储（用户模板 sha256+原子写、上限拒收、历史滚动剔除）；
//  C 桥 RPC 真跑（目录/解析三态/生成门负测/隐身负测/真模型出稿/steer 结束拒绝/导出双路/历史恢复/对话面交付锚点机检行）。
// 材料全部合成；末行 DRAFT_PASS / DRAFT_FAIL。
import WebSocket from "ws";
import { mkdirSync, openSync, unlinkSync, writeFileSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import {
  CATALOG_TEMPLATES, HIDDEN_CAUSES, resolveDocumentTemplate, renderHiddenTemplate, matchCause,
  normalizeQuery, withInferredTemplateFields, detectLoanMoneyContext, checkConditionalMoneyHedges,
  looksLikeLegalDocument, stripProcessPreamble, budgetMaterialText, assembleGenerationPrompt,
  settleGeneration, WORKFLOW_STAGES, extractDeliveryAnchors, validateDeliveryContent, FACT_FIDELITY_BLOCK,
} from "./draft_engine.mjs";
import {
  listUserTemplates, createUserTemplateFromUpload, upsertUserTemplate, deleteUserTemplate,
  addDraftHistoryRecord, listDraftHistory, deleteDraftHistory,
} from "./draft_store.mjs";
import { markdownToLegalDocx, docxInPlaceFill } from "./draft_docx.mjs";
import { extractDocxText } from "./redline_service.mjs";

const results: Array<{ name: string; ok: boolean; detail: string }> = [];
function check(name: string, ok: boolean, detail: string) {
  results.push({ name, ok, detail });
  console.log(`[draft-synthetic] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}

// ── A. 引擎纯逻辑 ──
const lit = CATALOG_TEMPLATES.filter((t) => t.category === "litigation");
const non = CATALOG_TEMPLATES.filter((t) => t.category === "non-litigation");
check("A1 目录 40 模板（诉讼20+非诉20）", CATALOG_TEMPLATES.length === 40 && lit.length === 20 && non.length === 20,
  `total=${CATALOG_TEMPLATES.length} lit=${lit.length} non=${non.length}`);
check("A2 隐藏 11 案由×2", HIDDEN_CAUSES.length === 11 && HIDDEN_CAUSES.every((c) => c.complaint && c.answer),
  `causes=${HIDDEN_CAUSES.length}`);
check("A3 目录模板含占位与字段", CATALOG_TEMPLATES.every((t) => t.content.includes("{{") && Array.isArray(t.fields) && t.fields.length >= 3),
  "content 均含 {{}} 且字段 ≥3");

const rHit = resolveDocumentTemplate({ documentType: "complaint", query: "帮我写一份物业服务合同纠纷的起诉状，业主要求追讨物业费" });
check("A4 命中：物业费→起诉状+优先级+随附指令", rHit.matched === true && rHit.template?.name === "民事起诉状（物业服务合同纠纷）"
  && rHit.priority === "embedded-after-user-template" && /自定义模板/.test(rHit.instructions ?? ""),
  `${rHit.template?.name}`);
const rAns = resolveDocumentTemplate({ documentType: "答辩状", query: "物业费纠纷答辩" });
check("A5 中文类型归一：答辩状→answer", rAns.matched === true && rAns.template?.documentType === "answer", rAns.template?.name ?? "miss");
const rMiss = resolveDocumentTemplate({ documentType: "complaint", query: "探望权纠纷起诉" });
check("A6 未命中不猜：matched:false+全案由清单", rMiss.matched === false && rMiss.supportedCauses?.length === 11 && !("isError" in rMiss),
  `causes=${rMiss.supportedCauses?.length}`);
const rBad = resolveDocumentTemplate({ documentType: "hello", query: "x" });
check("A7 非法类型 isError+原因", rBad.isError === true && !!rBad.reason, rBad.reason ?? "");
const rLong = resolveDocumentTemplate({ documentType: "complaint", query: "民间借贷纠纷 " + "x".repeat(5000) });
check("A8 query 截断 4000 仍命中", rLong.matched === true, "truncated query hit");
check("A9 别名最长优先（交通事故）", matchCause("机动车交通事故责任纠纷（交通事故）")?.entry.cause === "机动车交通事故责任纠纷"
  && matchCause("Labor Dispute wrongful termination") === null, String(matchCause("机动车交通事故责任纠纷（交通事故）")?.alias));
check("A10 空/英文 query 不命中", matchCause("") === null && matchCause("Personal Injury Case") === null, "null=null 不猜");

const rendered = renderHiddenTemplate(HIDDEN_CAUSES[0], "complaint");
const sections = (rendered.content.match(/^## .+$/gm) ?? []);
check("A11 渲染节序固定", sections.join("|") === "## 案号与案由|## 当事人信息|## 诉讼请求和依据|## 事实和理由|## 管辖、保全与其他说明|## 证据清单"
  && /具状人：\{\{原告签字或盖章\}\}/.test(rendered.content) && rendered.content.includes("【待核实："),
  sections.join(" | "));
const ansNoFacts = HIDDEN_CAUSES.find((c) => !c.answer.facts?.length);
const rAnsNoFacts = ansNoFacts ? renderHiddenTemplate(ansNoFacts, "answer") : null;
check("A12 facts 缺席=整节约去+答辩尾部", !!rAnsNoFacts && !rAnsNoFacts.content.includes("## 事实和理由") && /答辩人：\{\{答辩人签字或盖章\}\}/.test(rAnsNoFacts.content),
  ansNoFacts?.cause ?? "none");
check("A13 sourceFileId 溯源", rendered.sourceFileId.startsWith("hidden-cause-") && !!rendered.id, rendered.sourceFileId);

check("A14 占位推断补字段+已知不重", (() => {
  const fields = withInferredTemplateFields([{ id: "原告", label: "原告", type: "text" }], "原告：{{原告}}，被告：{{被告姓名}}，案号：{{案号}}");
  return fields.length === 3 && fields[1].type === "textarea" && fields[1].placeholder === "请填写该占位字段";
})(), "2 推断新增 1 已知不重");
check("A15 借贷三合一检测（缺一即否）", detectLoanMoneyContext("被告向原告借款 5 万元，约定利息") === true
  && detectLoanMoneyContext("被告向原告借款，但无金额数字") === false
  && detectLoanMoneyContext("合同金额 5000 元，双方系买卖关系") === false, "loan∧money∧digit");
check("A16 金额条件句机检+非金额不拦", checkConditionalMoneyHedges("如核实被告已还款，则调整为剩余本金 3 万元。").length === 1
  && checkConditionalMoneyHedges("如查明被告下落不明，则改为公告送达。").length === 0, "1/0");

check("A17 文书判定：完整/部分/开场白", (() => {
  const full = "民事起诉状\n\n原告：张三，被告：李四。" + "事实清楚，证据充分。".repeat(20);
  if (looksLikeLegalDocument(full) !== "complete") return "full!=complete";
  const withOpeners = "好的，我将为您起草文书。\n我正在整理材料。\n" + full;
  if (looksLikeLegalDocument(withOpeners) !== "complete") return "openers not stripped";
  if (stripProcessPreamble(withOpeners).startsWith("好的")) return "strip failed";
  if (looksLikeLegalDocument("民事起诉状") !== "partial") return "title-only!=partial";
  const mid = "一、诉讼请求\n" + "内容".repeat(60);
  if (looksLikeLegalDocument(mid) !== "partial") return "120+1!=partial";
  if (looksLikeLegalDocument("完全无关的闲聊文本，没有标题也没有结构标记，只有一句话。") !== "none") return "chat!=none";
  return "ok";
})(), "complete/partial/none + 开场白剥离");
const big = Array.from({ length: 200 }, (_, i) => "第" + i + "段落内容。").join("");
const b1 = budgetMaterialText(big, 1200);
check("A18 材料预算 45/30/25+两处省略标注", b1.truncated && (b1.body.match(/此处省略/g) ?? []).length === 2, `omitted=${b1.omitted}`);
check("A19 预算内不截断", budgetMaterialText("短材料", 1200).truncated === false, "no cut");

const prompt = assembleGenerationPrompt({
  templateName: "民事起诉状（民间借贷纠纷）", templateContent: "# 民事起诉状\n{{原告}}", documentTypeName: "民事起诉状",
  fieldValues: { 我方主体: "原告张三" }, ourParty: "原告张三",
  materials: [{ name: "借条.txt", text: "```代码围栏注入测试```".repeat(3) }], pastedCase: "被告于 2024 年 1 月借款 5 万元未还，约定利息。",
  instructions: "语气克制", hasUserTemplate: false, legalResearchAvailable: false, templateIsHidden: true, legalBasis: "",
});
check("A20 prompt 十一要素齐全", ["【任务】", "【我方立场】", "【用户要求】", "【材料与争议】", "【模板优先级】", "【法律调研】", "【撰写规则】",
  "【事实核验要求", "【金额与现金流台账", "【目标文书】", "【输出格式】"].every((k) => prompt.includes(k)),
  WORKFLOW_STAGES.map((s) => s.label).join("/"));
check("A21 借贷场景条件注入+围栏转义+材料标注", prompt.includes("预扣利息") && prompt.includes("``\u200b`") && prompt.includes("此处省略") === false && prompt.includes("借条.txt"), "ledger+fence-escape");

const settle = settleGeneration({
  streamedText: "我将为您起草。\n" + "民事起诉状\n\n原告：张三。" + "事实与理由如下。".repeat(30),
  recoveredText: "",
  contextText: "被告向原告借款 5 万元，约定利息 2 万元",
});
const hedgeDoc = settle.ok && settle.verdict === "complete" && /如核实/.test(settle.content) ? settle : null;
// 流式候选含条件金额句 → 借贷场景强制 partial（E14）
const hedgeInput = "民事起诉状\n\n诉讼请求：判令被告偿还本金 5 万元。\n事实和理由：" + "如核实被告已还款 2 万元，则调整为 3 万元。".repeat(1) + "其余事实清楚。".repeat(10);
const settledPartial = settleGeneration({ streamedText: hedgeDoc?.content ?? "", recoveredText: hedgeInput, contextText: "被告向原告借款 5 万元" });
check("A22 结算双通道：取最后过判定者", settledPartial.ok === true && settledPartial.content.includes("如核实被告已还款"), "candidate2 wins");
// E14：借贷+条件金额 → partial+提示（用含条件句的候选）
const withHedge = "民事起诉状\n\n诉讼请求：判令被告偿还借款本金 5 万元。\n\n## 事实和理由\n双方系民间借贷关系。\n如核实被告已还款 2 万元，则调整为偿还 3 万元。\n" + "事实清楚。".repeat(30);
const s2 = settleGeneration({ streamedText: withHedge, recoveredText: "", contextText: "借款 5 万元 利息 本金 民间借贷" });
check("A23 借贷条件金额→partial+核对提示", s2.ok && s2.verdict === "partial" && /诉请金额仍需核对/.test(s2.notice), s2.verdict);
check("A24 无正文→显式报错不出空稿", (() => { const r = settleGeneration({ streamedText: "闲聊", recoveredText: "", contextText: "" }); return !r.ok && r.verdict === "error" && /未返回可用文书正文/.test(r.reason); })(), "error 显式");

// ── H8/H9 交付合同文书重叠部分：锚点机提取（确定性正则）+终稿逐项机检 ──
const a25 = extractDeliveryAnchors("起草起诉状：全文不少于800字，必须包含「诉讼请求」「事实和理由」，写明案号（2025）京01民终123号。");
check("A25 锚点提取：字数/章节列表/案号", a25.minChars === 800 && a25.requiredSections.join("|") === "诉讼请求|事实和理由"
  && a25.caseNos.length === 1 && a25.caseNos[0].includes("京01民终123号") && a25.hasAny === true,
  JSON.stringify(a25));
check("A26 中文数字字数+顿号拆节", (() => {
  const a = extractDeliveryAnchors("答辩状不少于五百字，须包含「争议焦点、证据目录」两节");
  return a.minChars === 500 && a.requiredSections.join("|") === "争议焦点|证据目录";
})(), JSON.stringify(extractDeliveryAnchors("答辩状不少于五百字，须包含「争议焦点、证据目录」两节")));
check("A27 无锚点不猜：hasAny=false", extractDeliveryAnchors("帮我起草一份物业服务合同纠纷的起诉状").hasAny === false, "no anchors");
check("A28 终稿机检逐项：全过/字数缺/缺章节/缺案号/占位词", (() => {
  const good = "民事起诉状。" + "事实充分。".repeat(170) + "诉讼请求：还款。事实和理由：清楚。案号（2025）京01民终123号已列。";
  const passAll = validateDeliveryContent(good, a25);
  const short = validateDeliveryContent("太短", a25);
  const ph = validateDeliveryContent("正文待补充。", { minChars: 0, requiredSections: [], caseNos: [], hasAny: false });
  return passAll.every((c) => c.ok) && short.filter((c) => !c.ok).length === 4 && ph.length === 1 && ph[0].ok === false;
})(), validateDeliveryContent("太短", a25).map((c) => c.label + (c.ok ? "√" : "×")).join(","));
check("A29 事实忠实度指令块（H9 等量自写）", FACT_FIDELITY_BLOCK.includes("既成事实") && FACT_FIDELITY_BLOCK.includes("主语") && FACT_FIDELITY_BLOCK.includes("【待核实：具体事项】"), "block 在");

// ── B. 存储（%APPDATA%\Juscite 内；用后即删） ──
const uploaded = createUserTemplateFromUpload({ fileName: "合成模板-测试.txt", text: "授权委托书\n委托人：张三\n受托人：李四\n事项：{{代理事项}}", sourceBase64: undefined });
check("B1 上传即建 custom-<时间戳>+单全文字段", uploaded.id.startsWith("custom-") && uploaded.learningStatus === "analyzing" && uploaded.fields.length === 1, uploaded.id);
check("B2a 上传超 5 万截断（C3）", (() => {
  const rec = createUserTemplateFromUpload({ fileName: "超大.txt", text: "x".repeat(50001), sourceBase64: undefined });
  const len = rec.content.length; deleteUserTemplate(rec.id); return len === 50000;
})(), "clamped to 50000");
const tooBig = (() => { try { upsertUserTemplate({ id: "custom-x", name: "超限", content: "x".repeat(50001), fields: [] }); return "NO_THROW"; } catch (e) { return String((e as Error).message); } })();
check("B2b 直写超 5 万拒收（不静默截断入库）", /不合法|超上限/.test(tooBig), tooBig.slice(0, 40));
check("B2 content 超 5 万拒收", /不合法|超上限/.test(tooBig), tooBig.slice(0, 40));
deleteUserTemplate(uploaded.id);
check("B3 删除后列表不含", !listUserTemplates().some((t) => t.id === uploaded.id), "deleted");
const hist = addDraftHistoryRecord({ templateName: "合成历史-测试", templateCategory: "自定义", templateSource: "custom",
  fieldValues: { 原告: "张三" }, materialFileNames: ["借条.txt"], instructions: "测试指令", generatedContent: "民事起诉状……", verdict: "done", createdAt: Date.now() });
const histList = listDraftHistory();
check("B4 历史落盘可读+字段值全量（无 200 截断）", histList.some((r) => r.id === hist.id && r.fieldValues["原告"] === "张三"), hist.id);
deleteDraftHistory(hist.id);
check("B5 历史单删", !listDraftHistory().some((r) => r.id === hist.id), "deleted");

// ── C. 桥 RPC 真跑（自管隔离桥：测当前树 bridge_host 代码；不依赖 ：3030 常驻旧桥——
//     常驻桥内存代码滞后于工作树，锚点机检等新面必须起自家实例才验得到。board_synthetic 同款纪律：
//     杀前核验命令行含 bridge_host.mjs 宁停不误杀；收场自清自家 bridge-<port>.db*）──
const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3068);
const NODE_BIN = process.execPath;
let bridgePid = 0;
const bridgeLogPath = join(REPO_ROOT, ".local", `draft-synth-bridge-${PORT}.log`);
const bridgeLog = openSync(bridgeLogPath, "a");
function bridgeDbPath() { return join(_hd(), "AppData", "Roaming", "Juscite", "bridge", `bridge-${PORT}.db`); }
function spawnBridge() {
  const env = { ...process.env, BRIDGE_PORT: String(PORT) };
  const child = spawn(NODE_BIN, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: ["ignore", bridgeLog, bridgeLog], detached: true });
  child.unref();
  bridgePid = child.pid ?? 0;
}
async function probeBridge() {
  try {
    const r = await fetch(`http://127.0.0.1:${PORT}/api/server-info`, { signal: AbortSignal.timeout(2500) });
    return r.ok;
  } catch { return false; }
}
async function waitBridge(timeoutMs: number) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) { if (await probeBridge()) return true; await new Promise((r) => setTimeout(r, 500)); }
  return false;
}
async function commandLineOf(pid: number) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`], { encoding: "utf-8", timeout: 20000 });
  return String(r.stdout ?? "").trim();
}
async function killBridge(reason: string) {
  if (!bridgePid) return;
  const line = await commandLineOf(bridgePid);
  if (!line.includes("bridge_host.mjs")) {
    throw new Error(`拒绝杀进程 pid=${bridgePid}（${reason}）：命令行不含 bridge_host.mjs，宁停不误杀`);
  }
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probeBridge())) await new Promise((r) => setTimeout(r, 500));
}
{
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) !== PORT) continue;
    const line = await commandLineOf(Number(m[2]));
    if (!line.includes("bridge_host.mjs")) throw new Error(`:${PORT} 被非桥进程占用（pid=${m[2]}），不接触`);
    console.log(`[draft-synthetic] 清残留桥 pid=${m[2]}`);
    spawnSync("taskkill", ["/PID", String(m[2]), "/F", "/T"], { timeout: 15000 });
  }
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probeBridge())) await new Promise((r) => setTimeout(r, 500));
  for (const suffix of ["", "-wal", "-shm"]) { try { unlinkSync(bridgeDbPath() + suffix); } catch { /* 不存在即可 */ } }
  spawnBridge();
  if (!(await waitBridge(40000))) throw new Error(`隔离桥 :${PORT} 40s 不可探（日志 ${bridgeLogPath}）`);
}
const SCRATCH_WS = join(REPO_ROOT, ".local", `draft-scratch-${Date.now()}`);
const MATERIALS = join(SCRATCH_WS, "materials");
mkdirSync(MATERIALS, { recursive: true });
writeFileSync(join(MATERIALS, "合成借条.txt"), "借条：今借到张三人民币伍万元整（50000 元），约定月利率 1%，2025 年 12 月 31 日前归还。借款人：李四。", "utf-8");
writeFileSync(join(MATERIALS, "合成合同.txt"), "服务合同：甲方委托乙方提供法律服务，服务费 8000 元，于签约后 7 日内支付。", "utf-8");
const WS_URL = process.env.BRIDGE_WS_URL ?? `ws://127.0.0.1:${PORT}/ws`;
const ws = new WebSocket(WS_URL);
ws.binaryType = "arraybuffer";
const data = { fire: (_b: VSBuffer) => {} };
ws.on("message", (buf: ArrayBuffer) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
const isocket = {
  onData: (l: (b: VSBuffer) => void) => { data.fire = l; return { dispose: () => {} }; },
  onClose: () => ({ dispose: () => {} }),
  onEnd: () => ({ dispose: () => {} }),
  write: (b: VSBuffer) => ws.send(b.buffer),
  end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
};
const ch = new ChannelClient(new SocketProtocol(isocket as never)).getChannel("zcode-agent");
const call = <T,>(m: string, a?: unknown) => ch.call<T>(m, a === undefined ? [] : [a]);
await call("helloConversationV4");

const rpcCatalog = await call<{ builtin: BuiltinLite[]; userTemplates: unknown[] }>("draftCatalog", { workspacePath: SCRATCH_WS });
check("C1 RPC 目录 40+隐藏不露出", rpcCatalog.builtin.length === 40 && rpcCatalog.userTemplates.length >= 0, `builtin=${rpcCatalog.builtin.length}`);
interface BuiltinLite { id: string; name: string; category: string }
const rpcResolve = await call<{ matched: boolean; template?: { name: string }; instructions?: string; supportedCauses?: string[] }>(
  "draftResolveTemplate", { documentType: "complaint", query: "机动车交通事故责任纠纷索赔" });
check("C2 RPC 解析命中三态", rpcResolve.matched === true && !!rpcResolve.template && /不得以内置模板覆盖/.test(rpcResolve.instructions ?? ""), rpcResolve.template?.name ?? "miss");
const rpcMiss = await call<{ matched: boolean; supportedCauses?: string[]; reason?: string }>(
  "draftResolveTemplate", { documentType: "answer", query: "图形作品著作权纠纷" });
check("C3 RPC 未命中带全案由+不猜语义", rpcMiss.matched === false && rpcMiss.supportedCauses?.length === 11 && /自主生成结构/.test(rpcMiss.reason ?? ""), `causes=${rpcMiss.supportedCauses?.length}`);

// 生成门负测：三源全空 → 显式错误不发请求
const gateErr = await call<unknown>("draftGenerate", { workspacePath: SCRATCH_WS, templateSource: "builtin", fieldValues: {}, materialNames: [], pastedCase: "" })
  .then(() => "NO_THROW").catch((e: Error) => String(e.message));
check("C4 生成门：三源全空显式拒绝", /请上传案件材料|粘贴案情|文书信息/.test(gateErr), gateErr.slice(0, 50));


// 隐身负测：直改 mock 设置文件（桥 loadSetting 每次调用重读；setting 通道 RPC 在合成客户端未握手不可用）。
import { readFileSync as _rf, writeFileSync as _wf } from "node:fs";
import { homedir as _hd } from "node:os";
const SETTING_FILE = join(_hd(), "AppData", "Roaming", "Juscite", "config", "mock", "setting.json");
function setStealth(on: boolean) {
  const cur = JSON.parse(_rf(SETTING_FILE, "utf-8"));
  cur.stealthMode = { enabled: on };
  _wf(SETTING_FILE, JSON.stringify(cur, null, 2), "utf-8");
}
setStealth(true);
const stealthErr = await call<unknown>("draftGenerate", { workspacePath: SCRATCH_WS, templateSource: "builtin",
  fieldValues: { 原告: "张三" }, materialNames: [], pastedCase: "有内容" }).then(() => "NO_THROW").catch((e: Error) => String(e.message));
setStealth(false); // 恢复
check("C5 隐身 fail-closed 显式拒绝+已恢复", /隐身模式已开启/.test(stealthErr), stealthErr.slice(0, 60));

// 真模型出稿：材料+粘贴案情+隐藏案由模板（无选中模板 → 自动匹配物业服务合同纠纷？不，材料是借贷 → 用 hiddenQuery 指定）
const gen = await call<{ draftId: string; status: string; materialErrors: string[] }>("draftGenerate", {
  workspacePath: SCRATCH_WS, templateSource: "builtin",
  hiddenDocumentType: "complaint", hiddenQuery: "民间借贷纠纷 追讨借款本金和利息",
  fieldValues: { 我方主体: "原告张三" },
  materialNames: ["合成借条.txt", "不存在的材料.txt"],
  pastedCase: "2025 年 1 月被告李四向原告张三借款 50000 元，出具借条，到期未还。原告诉请偿还本金 50000 元及利息。",
  instructions: "金额以借条为准，语气克制。",
});
check("C6 发起生成：draftId+失败材料不阻塞", !!gen.draftId && gen.status === "running" && gen.materialErrors.some((m) => m.includes("不存在的材料.txt")),
  `draftId=${gen.draftId} materialErrors=${gen.materialErrors.length}`);

let final: null | { status: string; verdict: string; notice: string; error: string; content?: string; stages: Record<string, string> } = null;
for (let i = 0; i < 170; i++) {
  await new Promise((r) => setTimeout(r, 1500));
  const st = await call<{ status: string; verdict: string; notice: string; error: string; content?: string; stages: Record<string, string> }>("draftStatus", { draftId: gen.draftId });
  final = st;
  if (st.status !== "running") break;
}
check("C7 生成完成且文书判定过线", final?.status === "done" && final.verdict === "complete" && !!final.content && final.content.includes("民事起诉状"),
  `status=${final?.status} verdict=${final?.verdict} len=${final?.content?.length ?? 0}`);
check("C8 五阶段终态全 done", WORKFLOW_STAGES.every((s) => final?.stages?.[s.key] === "done"), JSON.stringify(final?.stages));
check("C9 生成包含借条金额（材料取材）", !!final?.content && final.content.includes("50000"), "material fact used");

const steerErr = await call<unknown>("draftSteer", { draftId: gen.draftId, text: "再强调违约责任" }).then(() => "NO_THROW").catch((e: Error) => String(e.message));
check("C10 steer 结束后拒绝（E9）", /生成已结束|无法再发送引导/.test(steerErr), steerErr.slice(0, 50));

// 历史链：生成后自动写历史 → 列表可见 → Get 恢复形状 → 删除
const histAfter = await call<{ records: Array<{ id: string; templateName: string; templateCategory: string; materialCount: number }> }>("draftHistoryList", {});
const mine = histAfter.records.find((r) => r.templateName.includes("民事起诉状"));
check("C11 生成自动写历史（E17/G5）", !!mine, mine ? `${mine.templateName} · ${mine.templateCategory} · 材料${mine.materialCount}` : "not found");
const histGet = mine ? await call<{ record: { generatedContent: string; fieldValues: Record<string, string>; materialFileNames: string[] } }>("draftHistoryGet", { id: mine.id }) : null;
check("C12 历史恢复形状：正文+字段值+材料名", !!histGet?.record.generatedContent && !!histGet.record.fieldValues && histGet.record.materialFileNames.includes("合成借条.txt"), "restorable shape");
if (mine) { try { await call("draftHistoryDelete", { id: mine.id }); } catch { /* 已删 */ } }

// 导出双路：内置模板→标准格式；自定义 docx 模板→原位写回
const exportStd = await call<{ docxBase64: string; mode: string; warning: string }>("draftExportWord",
  { templateSource: "builtin", templateId: "lt-civil-complaint", markdown: final?.content ?? "民事起诉状\n\n原告：张三。" });
check("C13 Word 标准格式导出（zip 可解析+宋体）", exportStd.mode === "standard" && exportStd.docxBase64.slice(0, 8) === "UEsDBBQA"
  || (exportStd.mode === "standard" && Buffer.from(exportStd.docxBase64, "base64").subarray(0, 2).toString("latin1") === "PK"),
  `mode=${exportStd.mode} warning=${exportStd.warning.length}`);


// 上传 docx 模板（含 {{槽位}}）→ 导出原位写回（F2①）；txt 模板→标准格式+警告（F2②）
const tplDocx = markdownToLegalDocx("# 授权委托书\n\n{{委托人姓名}}\n{{委托事项}}");
const upDocx = await call<{ template: { id: string; learningStatus: string } }>("draftUploadTemplate",
  { fileName: "合成授权委托书模板.docx", base64: tplDocx.toString("base64") });
check("C14 上传 docx 建模板+留存原文件", !!upDocx.template.id && upDocx.template.learningStatus === "analyzing", upDocx.template.id);
// 等学习落定（真模型，≤90s；失败也继续——导出不依赖学习态）
for (let i = 0; i < 60; i++) {
  await new Promise((r) => setTimeout(r, 1500));
  const cat = await call<{ userTemplates: Array<{ id: string; learningStatus: string; learningError: string }> }>("draftCatalog", {});
  const t = cat.userTemplates.find((x) => x.id === upDocx.template.id);
  if (t && t.learningStatus !== "analyzing") { console.log(`[draft-synthetic] learning -> ${t.learningStatus} ${t.learningError.slice(0, 60)}`); break; }
}
const exportInplace = await call<{ docxBase64: string; mode: string; warning: string }>("draftExportWord",
  { templateSource: "custom", templateId: upDocx.template.id, markdown: "兹委托李四代为立案\n\n一般授权（可代为诉讼代理人）" });
check("C15 原位写回导出（F2①保版式）", exportInplace.mode === "inplace" && extractDocxText(Buffer.from(exportInplace.docxBase64, "base64")).includes("兹委托李四代为立案"),
  `mode=${exportInplace.mode}`);
const upTxt = await call<{ template: { id: string } }>("draftUploadTemplate", { fileName: "合成纯文本模板.txt", base64: Buffer.from("催款函模板全文：致欠款方……", "utf-8").toString("base64") });
const exportWarn = await call<{ docxBase64: string; mode: string; warning: string }>("draftExportWord",
  { templateSource: "custom", templateId: upTxt.template.id, markdown: "催款函\n\n正文……" });
check("C16 无原文件→标准格式+警告（F2②）", exportWarn.mode === "standard" && /标准法律文书格式/.test(exportWarn.warning), exportWarn.warning.slice(0, 40));
import { unlinkSync as _unlink, existsSync as _exists } from "node:fs";
const srcFile = join(_hd(), "AppData", "Roaming", "Juscite", "user-templates", "sources", upDocx.template.id + ".docx");
let srcGone = false;
if (_exists(srcFile)) { _unlink(srcFile); srcGone = true; }
const badExport = await call<unknown>("draftExportWord", { templateSource: "custom", templateId: upDocx.template.id, markdown: "内容" }).then(() => "NO_THROW").catch((e: Error) => String(e.message));
void srcGone;
check("C17 原文件缺失硬报错不降级（F2③）", /不存在|未找到/.test(badExport), badExport.slice(0, 50));

// 上传白名单负测（.exe 拒绝）
const badUp = await call<unknown>("draftUploadTemplate", { fileName: "恶意的.exe", base64: Buffer.from("MZ").toString("base64") }).then(() => "NO_THROW").catch((e: Error) => String(e.message));
check("C18 上传白名单外拒绝（C3）", /仅支持/.test(badUp), badUp.slice(0, 40));

  // I3 简版通道：无 agent 直调 LLM 一次性产出（180s 时限；无工作流/不写历史）
  const lite = await call<{ content: string; model: string } | { err: string }>("draftGenerateLite", {
    hiddenDocumentType: "complaint", hiddenQuery: "买卖合同纠纷 催收货款",
    fieldValues: { 原告: "合成甲公司", 被告: "合成乙公司" },
    pastedCase: "合成甲公司向合成乙公司供应货物，货款 30000 元到期未付，经催收未果。",
  }).then((r) => r).catch((e: Error) => ({ err: String(e.message) }));
  const liteObj = lite as { content?: string; err?: string };
  check("C20 简版通道一次性产出（I3）", !!liteObj.content && liteObj.content.includes("起诉状"),
    liteObj.err ? liteObj.err.slice(0, 60) : "len=" + liteObj.content!.length);

  // H5 对话面绑定：sendText 起诉状意图 → 隐藏模板注入 → 回合正文按模板结构产出
  const conv = await call<{ result: { sessionId: string } }>("sendConversationCommandV4", { workspacePath: SCRATCH_WS, projectId: "lvyin-demo", envelope: { commandId: "cmd_c21_" + Date.now(), clientId: "draft-synthetic", sessionId: "", type: "createSession", payload: { title: "C21" }, issuedAt: Date.now() } });
  await call("sendConversationCommandV4", { workspacePath: SCRATCH_WS, envelope: { commandId: "cmd_c21s_" + Date.now(), clientId: "draft-synthetic", sessionId: conv.result.sessionId, type: "sendText", payload: { text: "请帮我起草一份物业服务合同纠纷的起诉状：原告合成物业公司，被告合成业主李某，拖欠 2025 年 1-6 月物业费共 3600 元。" }, issuedAt: Date.now()  } });
  let convText = "";
  for (let i = 0; i < 170; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    const snap = await call<{ rows: Array<{ kind: string; state: string; text: string }> }>("conversationRowsRangeV4", { sessionId: conv.result.sessionId, limit: 200 });
    const asst = (snap.rows ?? []).filter((r) => r.kind === "assistantText" && r.state === "complete").pop();
    if (asst) { convText = asst.text; break; }
  }
  check("C21 对话面起诉状意图绑定隐藏模板（H5）", convText.includes("民事起诉状") && convText.includes("物业服务"),
    "len=" + convText.length + " head=" + convText.slice(0, 30).split("\n").join("/"));

  // H8 桥路：带锚点起草要求 → 注入交付锚点+忠实度指令 → 回合完成落「交付锚点机检」逐项结果行
  const conv2 = await call<{ result: { sessionId: string } }>("sendConversationCommandV4", { workspacePath: SCRATCH_WS, projectId: "lvyin-demo", envelope: { commandId: "cmd_c22_" + Date.now(), clientId: "draft-synthetic", sessionId: "", type: "createSession", payload: { title: "C22" }, issuedAt: Date.now() } });
  await call("sendConversationCommandV4", { workspacePath: SCRATCH_WS, envelope: { commandId: "cmd_c22s_" + Date.now(), clientId: "draft-synthetic", sessionId: conv2.result.sessionId, type: "sendText", payload: { text: "请起草一份物业服务合同纠纷起诉状：原告合成物业公司，被告合成业主李某，拖欠 2025 年 1-6 月物业费 3600 元。全文不少于 500 字，必须包含「诉讼请求」「事实和理由」。" }, issuedAt: Date.now() } });
  let checkRowText = "";
  for (let i = 0; i < 170; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    const snap = await call<{ rows: Array<{ kind: string; state: string; text: string; model?: string }> }>("conversationRowsRangeV4", { sessionId: conv2.result.sessionId, limit: 200 });
    const chk = (snap.rows ?? []).find((r) => r.kind === "assistantText" && r.model === "draft-anchor-check" && r.state === "complete");
    if (chk) { checkRowText = chk.text; break; }
  }
  check("C22 交付锚点注入+终稿机检行落账（H8）", checkRowText.includes("交付锚点机检") && checkRowText.includes("诉讼请求") && checkRowText.includes("字数下限 ≥500 字"),
    "len=" + checkRowText.length + " head=" + checkRowText.slice(0, 40).split("\n").join("/"));
// 收尾清理：删除测试模板（连带源文件）
for (const id of [upDocx.template.id, upTxt.template.id]) {
  try { await call("draftDeleteTemplate", { templateId: id }); } catch { /* 幂等 */ }
}
const catClean = await call<{ userTemplates: Array<{ id: string }> }>("draftCatalog", {});
check("C19 测试模板已清理（连带删除）", !catClean.userTemplates.some((t) => t.id === upDocx.template.id || t.id === upTxt.template.id), "cleaned");

const failed = results.filter((r) => !r.ok);
console.log(`[draft-synthetic] ${results.length - failed.length}/${results.length} checks passed`);
// 收尾：杀自管隔离桥（命令行核验防误杀）+清自家 bridge-<port>.db*（board_synthetic 同款纪律）
try { await killBridge("draft-synth 收尾"); } catch (e) { console.error(String((e as Error).message ?? e)); }
for (const suffix of ["", "-wal", "-shm"]) { try { unlinkSync(bridgeDbPath() + suffix); } catch { /* 不存在即可 */ } }
console.log(failed.length ? "DRAFT_FAIL" : "DRAFT_PASS");
process.exit(failed.length ? 1 : 0);
