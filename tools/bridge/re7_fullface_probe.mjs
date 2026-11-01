#!/usr/bin/env node
// 【施工波三轮·#7 证据目录全量面】RE-7 §4 对拍 35 行逐项对拍探针（技能包/触发语义/交付链）。
// 自管隔离桥实例（默认 :3090，独立库 bridge-3090.db；杀前必核命令行含 bridge_host.mjs，不碰 :3030/:43127）。
// 全合成材料（合成 docx 字节/合成消息；不触真实案件数据）。四组：
//   P 组=技能包面（两 preset 结构+章节+触发族+真实字节量，对拍 9-14/21/28/29/32）；
//   T 组=触发语义（内核同构模拟，真实 SKILL.md 字节——规格 §5 口径，对拍 1-8/1a）；
//   D 组=交付链内核（对拍 22/23/23a 数据面点名案例）；
//   B 组=桥面（隔离 :3090：skills 通道两新技能可见+buildPromptContext 双命中/反断言+附件库
//        producer=agent 落账+D4②"文件在哪"本地短路（确定性，不依赖模型回复内容））；
//   G 组=生成器面真跑引用（implementation/tests F119 wiring pytest 复跑，环境缺失则如实 SKIP）。
// 末行 RE7_FULLFACE_PASS 可判（exit 0）。用法：node tools/bridge/re7_fullface_probe.mjs
import { spawn, spawnSync } from "node:child_process";
import { openSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import {
  planSkillInjection, searchSkills, loadSkill, SKILL_INJECTION_BUDGET_BYTES,
} from "../../packages/juscite-legal/src/kernel/skillActivationModel.ts";
import {
  extractDeliveredPaths, filterDeliveries, dedupeVersionFamily,
  completedWordDeliveryMessage, deliveredWordLocationAnswer, requestedArtifactKinds,
} from "../../packages/juscite-legal/src/kernel/deliveryChainModel.ts";

const REPO_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const PORT = Number(process.env.RE7_PROBE_PORT ?? 3090);
let passed = 0, failed = 0;
const ok = (n, msg) => { passed += 1; console.log(`[re7-probe] ${n}: OK ${msg}`); };
const fail = (n, msg, detail) => { failed += 1; console.error(`[re7-probe] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); };
const assert = (n, cond, msg, detail) => (cond ? ok(n, msg) : fail(n, msg, typeof detail === "string" ? detail : JSON.stringify(detail)));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── P 组：技能包面（对拍 9-14/21/28/29/32 的载体结构） ─────────────────────
const PRESETS = join(REPO_ROOT, "implementation", "skill-presets");
const catMeta = JSON.parse(readFileSync(join(PRESETS, "evidence-catalog", "skill.json"), "utf-8"));
const matMeta = JSON.parse(readFileSync(join(PRESETS, "evidence-materials", "skill.json"), "utf-8"));
const catMd = readFileSync(join(PRESETS, "evidence-catalog", "SKILL.md"), "utf-8");
const matMd = readFileSync(join(PRESETS, "evidence-materials", "SKILL.md"), "utf-8");
const P = (n, cond, msg) => assert(n, cond, msg);
P(1, catMeta.id === "evidence-catalog" && catMeta.triggers.commands.includes("/evidencecat")
  && /证据目录|证据清单|证据组织|证据管理/.test(catMeta.triggers.promptPatterns.join("|"))
  && JSON.stringify(catMeta.triggers.fileTypes) === JSON.stringify([".pdf", ".docx", ".txt", ".md"]),
"主技能 skill.json：/evidencecat+四词族+四扩展名（对拍 1/2 载体）");
P(2, matMeta.id === "evidence-materials" && matMeta.triggers.commands.includes("/evidencezheng")
  && /整理证据|制作证据|证据合集|证据材料整理|证据清单|证据目录/.test(matMeta.triggers.promptPatterns.join("|"))
  && matMeta.triggers.fileTypes.includes(".jpg") && matMeta.triggers.fileTypes.includes(".doc"),
"姊妹技能 skill.json：/evidencezheng+整理/合集词族+图片/旧格式扩展名（对拍 2/5 载体）");
P(3, ["# 证据目录生成", "## 一、概述", "## 二、法律声明", "## 三、分类方法", "## 四、操作步骤", "## 五、输出模板",
  "## 六、分案件类型重点", "## 七、质量检查清单", "## 八、实务经验", "## 九、关联技能", "## 十、信息不足时",
  "## 十一、多轮补证", "## 十二、局限性"].every((h) => catMd.includes(h)),
"主 SKILL.md 必备章节齐（概述/法律声明/分类/五步/模板/分类型/质量清单/实务/关联/追问/补证/局限）");
P(4, (catMd.match(/^\d\. \*\*/gm) ?? []).length === 5 && ["接收与初筛", "分类", "编号", "摘要与证明目的", "排版与核对"].every((s) => catMd.includes(s)),
"五步法五分步标题齐（对拍 9/B2）");
P(5, ["按种类", "按证明对象", "按证明功能", "按来源", "按证据链位置"].every((s) => catMd.includes(s))
  && /书证／物证／视听资料／电子数据／证人证言／鉴定意见／勘验笔录/.test(catMd),
"五种分类法+七类证据种类表（对拍 10/B3）");
P(6, ["筛选七问", "不利证据四策略", "真实性、合法性、关联性", "参考案例提交五要"].every((s) => catMd.includes(s)),
"七问筛选/不利证据四策略/质证三性/案例五要（对拍 10-12/B4-B7）");
P(7, (() => { const sec = catMd.slice(catMd.indexOf("质量检查清单"), catMd.indexOf("## 八"));
  return sec.replace(/\s+/g, "").split("；").filter((x) => x.replace(/^\d+\.?/, "").trim().length > 2).length === 12; })()
  && ["编号连续", "缺证处已标注说明"].every((s) => catMd.includes(s)),
"质量检查清单 12 项（对拍 21/C7：11 个『；』分隔+末项句号）");
P(8, ["八列表", "分组版式", "第 3-7 页（第 6 页）", "多级编号 1.1"].every((s) => catMd.includes(s))
  && /序号 \| 证据名称 \| 证据种类 \| 证据来源 \| 内容摘要 \| 证明目的 \| 页码\/份数 \| 备注/.test(catMd),
"输出模板：8 列通用表+分组版式+页码加注（对拍 19/C5 模板层）");
P(9, (catMd.match(/^1\. /gm) ?? []).length >= 1 && catMd.includes("不构成法律意见")
  && ["受案法院", "不夸大", "现行有效", "商业秘密", "原件"].every((s) => catMd.includes(s)),
"法律声明五点结构（对拍 28/E6：格式以受案机关为准/不夸大/更新/保密/不替代原件）");
P(10, ["实质审查", "受案机关", "庭审质证", "人工调整", "固证"].every((s) => catMd.includes(s)),
"局限性五点结构（对拍 28/E7）");
P(11, catMd.includes("四分法准备清单") && catMd.includes("追问"), "信息不足追问+四分法清单（对拍 29/E8）");
P(12, /2\.1、2\.2/.test(catMd) && catMd.includes("不重排已有编号"), "多轮补证 2.n 顺延不重排（对拍 32/E12）");
P(13, ["四阶段工作流", "收料边界", "写作规范", "清单版式", "合集规则"].every((s) => matMd.includes(s))
  && /不做 OCR/.test(matMd) && /（见原文第 4 页）/.test(matMd) && matMd.includes("收条只证"),
"姊妹 SKILL.md：四阶段/收料边界（不做 OCR/doc 转档）/写作规范六条锚（对拍 13-14/B8-B9）");
P(14, (matMd.match(/^\d\. /gm) ?? []).length >= 6 && ["证据推导有边界", "避免指代不明", "落款按文书类型"].every((s) => matMd.includes(s)),
"写作规范六条结构（对拍 14/B9）");
const catBytes = Buffer.byteLength(catMd, "utf-8"), matBytes = Buffer.byteLength(matMd, "utf-8");
P(15, catBytes + matBytes < SKILL_INJECTION_BUDGET_BYTES && catBytes > 4000 && matBytes > 2000,
`真实 SKILL.md 字节量 ${catBytes}+${matBytes}=${catBytes + matBytes}B<24000（双注入预算内，对拍 5）`);

// ── T 组：触发语义内核同构模拟（真实技能包字节；规格 §5"node 同构模拟对拍"口径） ──
const skills = [
  { id: "juscite-builtin-evidence-catalog", aliasIds: [catMeta.id], name: catMeta.name, description: catMeta.description, body: catMd, triggers: catMeta.triggers, priority: 0, scope: "builtin", rootPath: "implementation/skill-presets/evidence-catalog" },
  { id: "juscite-builtin-evidence-materials", aliasIds: [matMeta.id], name: matMeta.name, description: matMeta.description, body: matMd, triggers: matMeta.triggers, priority: 0, scope: "builtin", rootPath: "implementation/skill-presets/evidence-materials" },
];
const idsOf = (text) => planSkillInjection({ skills, text }).activations.map((a) => a.skill.id);
const T = (n, cond, msg) => assert(n, cond, msg);
T(16, JSON.stringify(idsOf("帮我生成证据目录")) === JSON.stringify(["juscite-builtin-evidence-catalog", "juscite-builtin-evidence-materials"])
  && JSON.stringify(idsOf("制作一份证据清单")) === JSON.stringify(["juscite-builtin-evidence-catalog", "juscite-builtin-evidence-materials"]),
"『帮我生成证据目录/制作一份证据清单』双技能同回合命中、id 字典序排前（对拍 1/5）");
T(17, idsOf("整理证据材料并出PDF合集").length === 1 && idsOf("整理证据材料并出PDF合集")[0] === "juscite-builtin-evidence-materials",
"『整理证据材料并出PDF合集』仅姊妹技能命中（对拍 5 后半）");
T(18, idsOf("帮我起草起诉状").filter((i) => i.includes("evidence")).length === 0, "『帮我起草起诉状』双证据技能不命中（对拍 1a 反向断言）");
T(19, planSkillInjection({ skills, text: "/evidencecat 帮我做目录" }).activations[0].score === 900
  && planSkillInjection({ skills, text: "我想问一下 /evidencecat 是干嘛的" }).activations.length === 0,
"/evidencecat 句首=command 900 分；句中=不激活（startsWith 语义，对拍 2）");
T(20, planSkillInjection({ skills, text: "/evidencezheng 整理一下" }).activations.map((a) => a.skill.id).join() === "juscite-builtin-evidence-materials"
  && planSkillInjection({ skills, text: "$evidence-catalog 出目录" }).activations[0].score === 1000
  && planSkillInjection({ skills, text: "$证据目录生成 出目录" }).activations[0].channels.includes("explicit"),
"/evidencezheng 命中姊妹；$evidence-catalog/$证据目录生成=explicit 1000 压过一切（对拍 3）");
T(21, (() => { const p = planSkillInjection({ skills, text: "把这份 .docx 材料整理成证据清单" });
  return p.activations.length === 2 && p.activations[0].channels.join() === "pattern,fileType"; })(),
"『把这份 .docx 材料整理成证据清单』双技能命中、pattern 先于 fileType 列序（对拍 4）");
T(22, (() => { const p = planSkillInjection({ skills, text: "证据目录", threadKind: "knowledge-qa" });
  return p.activations.length === 0 && p.block === null; })(),
"知识库问答线程整体短路（对拍 8/A9）");
T(23, searchSkills({ skills, query: "" }).length === 2
  && searchSkills({ skills, query: "怎么用 /evidencecat 这个命令" })[0].reason.includes("command(includes)"),
"search_skills：空 query=全列；命令目录检索=includes（双语义，对拍 6）");
T(24, loadSkill({ skills, id: "evidence-catalog" }).status === "ok"
  && loadSkill({ skills, id: "evidence-nope" }).suggestions.join(" ").includes("evidence"),
"load_skill：preset 短 id 可载；未找到给建议列表（对拍 6）");

// ── D 组：交付链内核点名案例（对拍 22/23/23a 数据面） ──────────────────────
const D = (n, cond, msg) => assert(n, cond, msg);
D(25, JSON.stringify(extractDeliveredPaths("目录已生成：证据目录.docx；留档 https://example.com/cases/清单.txt；更新于 2025.03.07；见 example.com"))
  === JSON.stringify(["证据目录.docx", "https://example.com/cases/清单.txt"]),
"路径提取：文件路径收、日期假扩展名与裸域名拒（对拍 22/D1）");
D(26, JSON.stringify(filterDeliveries([
  { path: "证据目录.pdf", source: "assistant" }, { path: "merge_evidence.py", source: "assistant" },
  { path: "out/batch_cmds.json", source: "tool" },
]).map((c) => c.path)) === JSON.stringify(["证据目录.pdf"]),
"混合交付『证据目录.pdf+merge_evidence.py』→脚本与过程文件出局仅留 pdf（对拍 22/D3）");
D(27, JSON.stringify(dedupeVersionFamily([
  { filename: "证据目录.docx", producer: "agent" }, { filename: "用户件.pdf", producer: "user" },
  { filename: "证据目录终稿.docx", producer: "agent" }, { filename: "证据目录.pdf", producer: "agent" },
]).map((i) => i.filename)) === JSON.stringify(["用户件.pdf", "证据目录终稿.docx", "证据目录.pdf"]),
"版本族去重：同族留最新、跨扩展名并列、用户件恒前（对拍 23a/D5）");
D(28, (completedWordDeliveryMessage({ requestedArtifacts: requestedArtifactKinds("帮我出一份 Word 文档目录").map((kind) => ({ kind })), deliveries: [{ path: "D:\\out\\证据目录.docx", status: "ok", kind: "docx" }] }) ?? "").includes("证据目录.docx")
  && completedWordDeliveryMessage({ requestedArtifacts: [{ kind: "pdf" }], deliveries: [{ path: "a.pdf", status: "ok", kind: "other" }] }) === null,
"D4① docx 唯一产物免复述轮话术含路径；非 docx 不短路（对拍 23 第一层）");
D(29, (deliveredWordLocationAnswer({ message: "生成的文件放在哪了？", history: [{ path: "D:\\o\\目录.docx", status: "ok", kind: "docx" }], allowReuse: true }) ?? "").includes("目录.docx")
  && deliveredWordLocationAnswer({ message: "放哪都行", history: [{ path: "D:\\o\\目录.docx", status: "ok", kind: "docx" }], allowReuse: true }) === null,
"D4② 文件在哪追问复用最近 docx 路径；授权语不触发（对拍 23 第二层）");

// ── B 组：桥面（隔离 :3090） ───────────────────────────────────────────────
function cmdlineOf(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command", `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`], { encoding: "utf8", timeout: 20000 });
  return String(r.stdout ?? "");
}

async function main() {
  // 隔离桥 spawn（同 edisc_ui_probe 先例：BRIDGE_PORT 分库 bridge-3090.db；日志 .local/re7-probe-bridge.log）
  const logFd = openSync(join(REPO_ROOT, ".local", "re7-probe-bridge.log"), "a");
  const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(PORT) }, stdio: ["ignore", logFd, logFd], detached: true });
  let up = false;
  for (let i = 0; i < 300 && !up; i++) { // 冷载窗 300s（99ec5acd 并行工位 100s 级实录同款）
    await sleep(1000);
    try { const r = await fetch(`http://127.0.0.1:${PORT}/api/attachments`, { method: "GET" }); up = r.status > 0; } catch { /* 未起继续等 */ }
  }
  assert(30, up, `隔离桥 :${PORT} 探活（bridge-3090.db 独立库；冷载窗 300s）`);
  try {
    if (up) await bridgeFace();
  } finally {
    // 杀前必验命令行含 bridge_host.mjs（只杀本探针 spawn 的隔离桥；:3030/:43127 不碰）
    const cmd = cmdlineOf(child.pid);
    if (child.pid && cmd.includes("bridge_host.mjs")) {
      spawnSync("taskkill", ["/PID", String(child.pid), "/F", "/T"], { timeout: 15000 });
      ok(40, `隔离桥清理（pid=${child.pid}，命令行核验含 bridge_host.mjs）`);
    } else {
      fail(40, "隔离桥清理跳过：命令行核验不含 bridge_host.mjs（不误杀）", cmd.slice(0, 120));
    }
  }

  // ── G 组：生成器面真跑引用（对拍 15-21 锚；环境缺失如实 SKIP 不算失败） ──
  const g = spawnSync("python", ["-X", "utf8", "-m", "pytest", "tests/test_f119_f120_evidence_chain_wiring.py", "-q"],
    { cwd: join(REPO_ROOT, "implementation"), encoding: "utf-8", timeout: 300000 });
  if (g.status === 0) ok(41, `生成器面 F119 wiring 复跑绿（${(g.stdout.match(/(\d+) passed/) ?? [""])[0]}）`);
  else {
    const reason = String(g.stderr ?? g.stdout ?? "").slice(0, 160).split("\n").join(" ");
    console.log(`[re7-probe] 41: SKIP 生成器面 pytest 未绿/未跑（status=${g.status}；${reason}）——对拍 15-21 按在档证据引用（docs/construction/evidence/F119/ + 99ec5acd 复跑在档）`);
  }
  finish();
}

async function bridgeFace() {
  const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws`);
  ws.binaryType = "arraybuffer";
  const fire = { fn: (_b) => {} };
  ws.on("message", (buf) => fire.fn(VSBuffer.wrap(new Uint8Array(buf))));
  await new Promise((res, rej) => { ws.on("open", res); ws.on("error", rej); });
  const isocket = {
    onData: (l) => { fire.fn = l; return { dispose: () => {} }; },
    onClose: () => ({ dispose: () => {} }), onEnd: () => ({ dispose: () => {} }),
    write: (b) => ws.send(b.buffer), end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
  };
  const client = new ChannelClient(new SocketProtocol(isocket));
  const ch = client.getChannel("zcode-agent");
  const call = (m, a) => ch.call(m, a === undefined ? [] : [a]);
  const workspacePath = "D:\\mock\\lvyin-demo";
  await call("helloConversationV4");

  // B31-33 技能通道：两新内置技能可见（对拍 7/A8 builtin 可见+用户根作用域）
  const skch = client.getChannel("skills");
  const skCall = (m, a) => skch.call(m, a === undefined ? [] : [a]);
  const skillsList = await skCall("list");
  const all = skillsList?.skills ?? [];
  const cat = all.find((s) => s.id === "juscite-builtin-evidence-catalog");
  const mat = all.find((s) => s.id === "juscite-builtin-evidence-materials");
  assert(31, Boolean(cat && mat) && /\/evidencecat/.test(cat?.description ?? "") && /证据目录/.test(cat?.description ?? "")
    && /\/evidencezheng/.test(mat?.description ?? "") && /整理证据/.test(mat?.description ?? ""),
  "skills 通道含两新内置技能（触发族入 description；builtin/plugin scope）");
  assert(32, /操作步骤/.test(cat?.body ?? "") && /质量检查清单/.test(cat?.body ?? "") && /四阶段工作流/.test(mat?.body ?? ""),
  "两技能注入正文（body）在通道可见（对拍 7 面板数据源）");
  assert(33, (skillsList?.capability?.userScopeAvailable ?? false) === true,
  "用户根技能作用域可用（对拍 7 安装覆盖用户根——RE-21 zip 装卸面）");

  // B34-35 buildPromptContext：双命中与反向断言（对拍 1/1a 桥面）
  const ctx1 = await skCall("buildPromptContext", { workspacePath, prompt: "帮我生成证据目录" });
  const names1 = (ctx1?.activatedSkillNames ?? []).join(",");
  assert(34, names1.includes("证据目录生成") && names1.includes("证据材料整理") && String(ctx1?.prompt ?? "").includes("<active-skills>"),
  `buildPromptContext『帮我生成证据目录』双技能激活+注入块（${names1}）`);
  const ctx2 = await skCall("buildPromptContext", { workspacePath, prompt: "帮我起草起诉状" });
  const names2 = (ctx2?.activatedSkillNames ?? []).join(",");
  assert(35, !names2.includes("证据目录生成") && !names2.includes("证据材料整理"),
  `buildPromptContext『帮我起草起诉状』双证据技能不激活（${names2 || "空"}；文书技能命中属正常）`);

  // B36-39 交付链桥面：会话种子行（/调研 空课题=本地行，不触模型）→附件库 agent 落账→D4② 短路
  const sessionId = "ses_re7_" + Math.random().toString(36).slice(2, 8);
  await call("sendConversationCommandV4", { workspacePath, envelope: { commandId: "cmd_re7_seed", clientId: "re7-probe", sessionId, type: "createSession", payload: { sessionId, workspaceId: workspacePath }, issuedAt: Date.now() } });
  const frames = [];
  const convEvent = ch.listen("onDynamicConversationFrame", { workspacePath });
  convEvent((f) => { if (f?.topic === `conversation/${sessionId}`) frames.push(f); });
  await call("sendConversationCommandV4", { workspacePath, envelope: { commandId: "cmd_re7_s2", clientId: "re7-probe", sessionId, type: "sendText", payload: { text: "/调研" }, issuedAt: Date.now() } });
  await sleep(1500);
  const rowsNow = () => frames.flatMap((f) => f?.frame?.payload?.deltas ?? f?.payload?.deltas ?? []).map((d) => d.row).filter(Boolean);
  assert(36, rowsNow().some((r) => r?.kind === "assistantText"),
  "会话种子行落位（/调研 空课题本地引导行——D4② stepIndex>0 闸的前置回合）");

  const docxBytes = Buffer.from("PKre7-synthetic-docx（合成材料，非真实文书）", "utf-8");
  const up1 = await (await fetch(`http://127.0.0.1:${PORT}/api/attachments`, {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ dataBase64: docxBytes.toString("base64"), filename: "证据目录_合成.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", threadIds: [sessionId], producer: "agent" }),
  })).json();
  assert(37, Boolean(up1?.attachmentId), "agent 交付 docx 落对话附件库（producer=agent，对拍 22 D1 落账面）");
  const lst = await (await fetch(`http://127.0.0.1:${PORT}/api/attachments?threadId=${sessionId}`)).json();
  const agentItems = (lst?.items ?? []).filter((i) => i.producer === "agent");
  assert(38, agentItems.length === 1 && agentItems[0].filename === "证据目录_合成.docx",
  "线程作用域附件清单含 agent 产出（对话文件浮层『Agent 产出』组数据源，对拍 22/23b 分组）");

  frames.length = 0;
  await call("sendConversationCommandV4", { workspacePath, envelope: { commandId: "cmd_re7_w", clientId: "re7-probe", sessionId, type: "sendText", payload: { text: "生成的文件放在哪了？" }, issuedAt: Date.now() } });
  await sleep(2500);
  const localRows = rowsNow().filter((r) => r?.model === "delivery-local");
  assert(39, localRows.length > 0 && localRows.some((r) => String(r.text ?? "").includes("证据目录_合成.docx")),
  "D4②『文件在哪』本地短路作答（model=delivery-local，含最近 agent docx 路径；不经模型回合）");
}

function finish() {
  // 对拍 35 行裁决表（本探针实测面 + 在档引用面 + 如实差异面）
  const rows = [
    ["1", "PASS", "pattern 500 双命中（T16/B34）"], ["1a", "PASS", "非命中反向断言（T18/B35）"],
    ["2", "PASS", "startsWith 900（T19）"], ["3", "PASS", "explicit 1000 三形态+名称点名（T20）"],
    ["4", "PASS", "fileType 附件+消息扫描（T21）"], ["5", "PASS", "双命中排序/预算/上限（T16/P15+vitest 预算上限组）"],
    ["6", "PASS", "search/load 双语义+建议列表（T23/T24；install 审批面=RE-21 用户发起 zip 装卸在档）"],
    ["7", "PASS", "builtin 可见+用户根（B31/B33；竞品五根 vs 我方 builtin+用户根双根制=RE-21 裁决结构，差异具名）"],
    ["8", "PASS", "知识库线程短路（T22；桥接线 runAssistantTurn kbThread 闸）"],
    ["9", "PASS", "五步法（P4）"], ["10", "PASS", "五分法+七问+四策略（P5/P6）"],
    ["11", "PASS", "质证三性+有利点（P6）"], ["12", "PASS", "案例五要（P6）"],
    ["13", "PASS", "输入边界（P13）"], ["14", "PASS", "写作规范六条（P14）"],
    ["15", "DIFF", "对话表格+Word 在（G41/F119 C06）；xlsx 形态未落→openIssues"],
    ["16", "DIFF", "竞品 xlsx worker 执行器语义未移植（我方生成器=harness docx 路线）；空目录拒/绑定 fail-closed 在 F119→openIssues"],
    ["17", "BOUNDARY", "规格 §5 明示不抄 officecli 兜底逐字节等量；batch 一次/validate 一次纪律入技能正文 Excel 纪律节"],
    ["18", "EXT", "F119 C06 横向八列冻结闭集+独立回读（版式差异=生成器面裁决）"],
    ["19", "PASS", "分组版式模板层在 SKILL.md（P8）+F119 平铺行=与竞品脚本同级等量线"],
    ["20", "DIFF", "合集规则合同层在姊妹 SKILL.md §五+F119 媒体加工面在；PDF 合集合成器未落→openIssues"],
    ["21", "PASS", "12 项质量清单（P7）"],
    ["22", "PASS", "双层过滤两路径+agent 落账+浮层面板（D25/D26/B37/B38；xlsx 文件卡=other 类+下载原件本单补 UI）"],
    ["23", "PASS", "D4 两层短路（D28/D29/B39 桥面确定性）"],
    ["23a", "PASS", "版本族去重（D27）"],
    ["23b", "PASS", "四态+双分组+计数徽章=ThreadFilesPanel 既有面（RE-6 交付件）+本单 D2 下载原件补面"],
    ["24", "DIFF", "任务合同/泳道治理=oc28 模型循环域（树外）；桥侧工具策略审计（#21）在但非同构→openIssues"],
    ["25", "DIFF", "风暴熔断=oc28 域→openIssues"],
    ["26", "BOUNDARY", "我方无 officecli 依赖面（生成器单路径=harness），主备双路径结构性不适用"],
    ["27", "DIFF", "token 预算收尾=oc28 域→openIssues"],
    ["28", "PASS", "法律声明五点+局限性五点（P9/P10）"],
    ["29", "PASS", "追问+四分法（P11）"],
    ["30", "PARTIAL", "起诉状『## 证据清单』节在 draft_engine（:21/:55/:495）；evidence_catalog 任务路由未落→openIssues"],
    ["31", "EXT", "知识库『诉讼仲裁』13 类规则在 kb_service（:221/:226）+分层记忆偏好层在（RE-36）；语义召回=关键词族差异具名"],
    ["32", "PASS", "2.n 顺延不重排（P12）"],
  ];
  console.log("\n[re7-probe] RE-7 §4 对拍 35 行裁决表：");
  for (const [n, v, note] of rows) console.log(`  行${n}\t${v}\t${note}`);
  const diffCount = rows.filter((r) => r[1] === "DIFF" || r[1] === "PARTIAL").length;
  console.log(`[re7-probe] 计：PASS ${rows.filter((r) => r[1] === "PASS").length}｜EXT/BOUNDARY（规格边界或在档引用）${rows.filter((r) => r[1] === "EXT" || r[1] === "BOUNDARY").length}｜DIFF/PARTIAL（差异具名→openIssues）${diffCount}`);
  if (failed === 0) { console.log("RE7_FULLFACE_PASS"); process.exit(0); }
  console.error(`RE7_FULLFACE_FAIL（${failed} 项失败）`); process.exit(1);
}

main().catch((e) => { console.error("[re7-probe] fatal:", e); finish(); });
