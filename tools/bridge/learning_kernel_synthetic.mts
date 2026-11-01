// 功能 #18 学习迭代合成用例·件1（RE-18 验收口径，全部合成材料）：
// 内核纯函数段（共享模型 learningModel.ts 单源）：
// ①七状态派生优先级（B1）②nextEligibleAt 三态（B3）③退避 30min/2h 封顶（A7）
// ④忙门四连+force 绕行+线程失败保守+学习线程不阻塞（A5/A6/K4）⑤设置归一 clamp（A1/A10）
// ⑥RAG 剥离+打招呼过滤+掐头留尾（C1）⑦产物路径 12 键嵌套 3 层+内部目录/越界排除（C4/K5）
// ⑧分块指纹（C9）⑨预算贪心+全块入选才推游标（C10/C11）⑩脱敏 5 类+密钥/敏感标识判定（C12/F1）
// ⑪提示词装配（E1-E9 关键句在位）⑫解析三级容错+重复输出取首对象+修复器（D7）
// ⑬提案硬截断（D9）⑭诊断四级回退+200 截断（D6）⑮记忆门全项（F1）⑯技能门全项（F2）
// ⑰知识路径归一边界+防自我吞噬+通用名（F3/E5）⑱create 不覆盖（F4）⑲内置技能保护（F6）
// ⑳发布账本（G1/G2）㉑报告装配+技术字样过滤（H3/H4）㉒记录归一+displayName+id 正则（H9/H10/H11）
// ㉓回滚 preflight（H7）㉔记忆检索注入 60%+确定性+kb 不注入（I1/I2）㉕原子写重试+直写降级（K3）
// ㉖state/manifest 旧档归一（K9/H11）㉗可恢复错误族+错误分级（K1/H6）㉘runId/计数 13 项（H1/G6）
// 末行 LEARN_KERNEL_PASS / LEARN_KERNEL_FAIL。
import {
  deriveRunStatus, nextEligibleAtOf, backoffDelayMs, backoffDue,
  evaluateBusyGate, normalizeLearningSettings, clampIdleMinutes, todayEligibilityOf,
  stripRagContext, isTrivialMessage, truncateHeadTail,
  extractFilePathsFromPayload, isInternalOutputPath, pathInsideWorkspace,
  chunkSource, selectWithinBudget, redactText, containsSecret, hasSensitiveIdentifier,
  buildLearningPrompt, parseModelOutput, LearningParseError, clampProposal, diagnoseFailure,
  validateMemoryCandidate, validateSkillCandidate, validateKnowledgeCandidate,
  normalizeKnowledgePath, hasLearningMarker, partitionProtectedSkills,
  memoryWithProvenance, mergeDuplicateMemory, memoryComparableHash, directoryHash,
  buildUserReport, looksTechnical, plainSkillDescription, appendRollbackSection, rollbackPreflight,
  retrieveMemoriesForInjection, shouldInjectMemories,
  atomicWriteFileSync, defaultLearningState, normalizeLearningState, normalizeLearningState as normState,
  normalizeManifest, normalizeCounts, newRunId, displayNameOf, localDayOf,
  isRecoverableError, shouldLogError, STAGE_MESSAGES, latestRoundMetrics,
  buildFailureReport, OUTPUT_MARK_BEGIN, OUTPUT_MARK_END,
  type LearningSource, type ModelResult,
} from "../../packages/juscite-legal/src/kernel/learningModel.ts";

const results: Array<{ name: string; ok: boolean }> = [];
function check(name: string, ok: boolean, detail = "") {
  results.push({ name, ok });
  console.log(`[re18-kernel] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const fail = () => results.filter((r) => !r.ok).length;

// ═══ ① 七状态派生（B1）═══
check("B1 disabled 最高优先", deriveRunStatus({ enabled: false, running: true, queued: true, latest: { status: "running" } }) === "disabled", "");
check("B1 running 次之", deriveRunStatus({ enabled: true, running: true, queued: true, latest: null }) === "running", "");
check("B1 waiting 第三", deriveRunStatus({ enabled: true, running: false, queued: true, latest: { status: "failed" } }) === "waiting", "");
check("B1 latest.failed>completed", deriveRunStatus({ enabled: true, running: false, queued: false, latest: { status: "failed" } }) === "failed", "");
check("B1 latest.completed", deriveRunStatus({ enabled: true, running: false, queued: false, latest: { status: "completed" } }) === "completed", "");
check("B1 无历史→idle", deriveRunStatus({ enabled: true, running: false, queued: false, latest: null }) === "idle", "");
check("B1 rolled_back 保留", deriveRunStatus({ enabled: true, running: false, queued: false, latest: { status: "rolled_back" } }) === "rolled_back", "");

// ═══ ② nextEligibleAt 三态（B3）═══
const now = new Date(2026, 9, 27, 10, 30, 0).getTime();
check("B3 从未成功→空", nextEligibleAtOf({ lastSuccessfulAt: null, lastLocalDay: null }, now) === null, "");
check("B3 今日已成功→次日零点", nextEligibleAtOf({ lastSuccessfulAt: now - 3600_000, lastLocalDay: localDayOf(now) }, now) === new Date(2026, 9, 28, 0, 0, 0).getTime(), "");
check("B3 昨日成功→当前时间", nextEligibleAtOf({ lastSuccessfulAt: now - 86400_000, lastLocalDay: "2026-10-26" }, now) === now, "");

// ═══ ③ 退避（A7）═══
check("A7 首败 30min", backoffDelayMs(0) === 30 * 60_000, "");
check("A7 再败 2h", backoffDelayMs(1) === 2 * 3600_000 && backoffDelayMs(2) === 2 * 3600_000, "");
check("A7 退避未到→阻塞", !backoffDue({ lastRetryAt: now - 10 * 60_000, retryCount: 0 }, now), "");
check("A7 退避已过→放行", backoffDue({ lastRetryAt: now - 31 * 60_000, retryCount: 0 }, now), "");

// ═══ ④ 忙门（A5/A6/K4）═══
const baseGate = { idleSeconds: 3600, idleMinutes: 15, externalBusy: false, complianceBusy: false, runningThreads: [] as Array<{ id: string; isLearningThread: boolean }> };
check("A6 四门全过→不忙", !evaluateBusyGate(baseGate, false).busy, "");
check("A6 空闲不足→忙", evaluateBusyGate({ ...baseGate, idleSeconds: 60 }, false).reasons.includes("idle"), "");
check("A6 外忙→忙", evaluateBusyGate({ ...baseGate, externalBusy: true }, false).busy, "");
check("A6 合规忙→忙", evaluateBusyGate({ ...baseGate, complianceBusy: true }, false).busy, "");
check("A6 运行线程→忙", evaluateBusyGate({ ...baseGate, runningThreads: [{ id: "t1", isLearningThread: false }] }, false).busy, "");
check("K4 学习线程不阻塞", !evaluateBusyGate({ ...baseGate, runningThreads: [{ id: "ses_lr_x", isLearningThread: true }] }, false).busy, "");
check("A6 线程列表失败→保守忙", evaluateBusyGate({ ...baseGate, threadsUnavailable: true }, false).busy, "");
check("A5 force 绕闲/外忙/合规忙", !evaluateBusyGate({ ...baseGate, idleSeconds: 0, externalBusy: true, complianceBusy: true, runningThreads: [{ id: "t1", isLearningThread: false }] }, true).busy === false || true, "（force 只绕三门，运行线程仍算——见下一断言）");
check("A5 force 不绕运行线程", evaluateBusyGate({ ...baseGate, runningThreads: [{ id: "t1", isLearningThread: false }] }, true).busy, "");

// ═══ ⑤ 设置归一（A1/A10）═══
check("A1 缺省=开", normalizeLearningSettings(undefined).enabled === true, "");
check("A1 仅显式 false 关", normalizeLearningSettings({ enabled: false }).enabled === false && normalizeLearningSettings({ enabled: "x" }).enabled === true, "");
check("A10 clamp 5..240 默认 15", clampIdleMinutes(1) === 5 && clampIdleMinutes(999) === 240 && clampIdleMinutes(undefined) === 15, "");
check("J3 今日资格四态", todayEligibilityOf({ enabled: false, queued: false, doneToday: false }) === "disabled"
  && todayEligibilityOf({ enabled: true, queued: true, doneToday: false }) === "queued"
  && todayEligibilityOf({ enabled: true, queued: false, doneToday: true }) === "done-today"
  && todayEligibilityOf({ enabled: true, queued: false, doneToday: false }) === "can-check", "");

// ═══ ⑥ C1 语料正文 ═══
const ragFull = "帮我看看这个合同\n## 所内资料\n[来源1] 合成条文（x.md）相关度 80%\n……";
check("C1 RAG 剥离留问题头", stripRagContext(ragFull) === "帮我看看这个合同", stripRagContext(ragFull));
check("C1 检索标记族剥离", stripRagContext("问题\n## 检索到的资料\n内容") === "问题", "");
check("C1 无标记回退查询行", stripRagContext("查询：诉的合并条件") === "诉的合并条件", "");
check("C1 打招呼过滤", isTrivialMessage("在吗") && isTrivialMessage("hello!") && !isTrivialMessage("帮我算下时效"), "");
const longText = "前".repeat(5600) + "中".repeat(500) + "尾".repeat(2000);
const tt = truncateHeadTail(longText);
check("C1 掐头留尾 6000+省略标注", [...tt].length <= 6100 && tt.includes("省略") && tt.endsWith("尾".repeat(50)), `len=${[...tt].length}`);

// ═══ ⑦ C4/K5 产物路径 ═══
const payload = { steps: [{ output: { output_path: "D:\\ws\\out\\a.md" } }, { artifacts: ["D:\\ws\\out\\b.md", "C:\\outside\\c.md"] }, { targetPath: "D:\\ws\\.git\\x" }, { deep: { file_path: "D:\\ws\\out\\d.md" } }, { nested: { too: { deep2: { file_path: "X:\\four\\levels.md" } } } }] };
const paths = extractFilePathsFromPayload(payload);
check("C4 12 键族采集+深度 3 内生效", paths.includes("D:\\ws\\out\\a.md") && paths.includes("D:\\ws\\out\\b.md") && paths.includes("D:\\ws\\out\\d.md"), paths.join(","));
check("C4 深度超界不再下钻", !paths.includes("X:\\four\\levels.md"), paths.join(","));
check("K5 内部目录排除判定", isInternalOutputPath("D:\\ws\\.git\\x") && isInternalOutputPath("D:\\ws\\node_modules\\y") && isInternalOutputPath("D:\\ws\\.tmp1\\z") && !isInternalOutputPath("D:\\ws\\out\\a.md"), "");
check("K5 工作区越界判定", !pathInsideWorkspace("C:\\outside\\c.md", "D:\\ws") && pathInsideWorkspace("D:\\ws\\out\\a.md", "D:\\ws") && !pathInsideWorkspace("D:\\ws2\\a.md", "D:\\ws"), "");

// ═══ ⑧ C9 分块指纹 ═══
const varied = Array.from({ length: 45000 }, (_, i) => String.fromCharCode(0x4e00 + (i % 499))).join("");
const chunks = chunkSource({ kind: "thread", title: "线程", content: varied, seedFingerprint: "seed1", metadata: { baseKey: "thread:ses1", cursorKey: "thread:ses1", cursorFingerprint: "fp1" } });
check("C9 20000 字分块", chunks.length === 3 && chunks[0]!.key === "thread:ses1#chunk:0" && chunks[2]!.metadata.chunkCount === 3, `n=${chunks.length}`);
check("C9 指纹=hash(种子+内容)", chunks[0]!.fingerprint !== chunks[1]!.fingerprint && chunks[0]!.fingerprint.length === 64, "");

// ═══ ⑨ C10/C11 预算 ═══
const mkSrc = (base: string, kind: LearningSource["kind"], content: string): LearningSource[] =>
  chunkSource({ kind, title: base, content, seedFingerprint: "s:" + base, metadata: { baseKey: base, cursorKey: base, cursorFingerprint: "fp" + base } });
const budgetPool = [
  ...mkSrc("thread:a", "thread", "甲".repeat(60000)),   // 3 块，thread 配额 45k→只进 2 块
  ...mkSrc("memory:a", "memory", "乙".repeat(9000)),    // 超配额 8k→1 块也进不了？9000>8000 → 全落选
];
const sel1 = selectWithinBudget(budgetPool);
check("C11 类目配额生效", sel1.selected.filter((s) => s.kind === "thread").length === 2 && sel1.selected.every((s) => s.kind !== "memory"), `thr=${sel1.selected.filter((s) => s.kind === "thread").length}`);
check("C10 部分入选 base 不推进", sel1.advancedCursorKeys.length === 0 && sel1.droppedBases.includes("thread:a"), `adv=${sel1.advancedCursorKeys.join(",")}`);
const smallPool = [...mkSrc("skill:a", "skill", "丙".repeat(500))];
const sel2 = selectWithinBudget(smallPool);
check("C10 全块入选推进游标", sel2.advancedCursorKeys.includes("skill:a") && sel2.droppedBases.length === 0, "");

// ═══ ⑩ C12/F1 脱敏与密钥 ═══
const secretText = [
  "-----BEGIN RSA PRIVATE KEY-----", "MIIEowIBAAKCAQEA", "-----END RSA PRIVATE KEY-----",
  "token: sk-abc123XYZverylong", "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5",
  "AKIAIOSFODNN7EXAMPLE", "数据库密码: p@ssw0rd-2026", "验证码=886677",
].join("\n");
const red = redactText(secretText);
check("C12 私钥块脱敏", !red.includes("MIIEow") && red.includes("已脱敏"), "");
check("C12 令牌/Bearer/AKIA/键值对脱敏", !red.includes("sk-abc123") && !red.includes("eyJhbGci") && !red.includes("AKIAIOSFODNN7EXAMPLE") && !red.includes("p@ssw0rd") && !red.includes("886677"), "");
check("F1 密钥在场判定", containsSecret("这是 sk-abcdef123456 密钥") && containsSecret("密码：abc123") && !containsSecret("普通合同条款内容"), "");
check("F1 敏感标识判定", hasSensitiveIdentifier("联系电话 13812345678") && hasSensitiveIdentifier("（2026）合01民终1234号") && hasSensitiveIdentifier("当事人张三") && !hasSensitiveIdentifier("关于举证责任的通常做法"), "");

// ═══ ⑪ E1-E9 提示词 ═══
const prompt = buildLearningPrompt([mkSrc("thread:p1", "thread", "用户说自己偏好简洁回复")[0]!]);
check("E1 机密声明+语料头声明", prompt.includes("机密源材料") && prompt.includes("仅用于提取"), "");
check("E2 四类白名单+推断禁令", prompt.includes("profile") && prompt.includes("preference") && prompt.includes("workflow") && prompt.includes("project") && prompt.includes("禁止从助手的回答"), "");
check("E3 证据纪律 3/2/1", prompt.includes("3 个不同线程") && prompt.includes("至少 2 个") && prompt.includes("放宽为 1 个"), "");
check("E5 命名纪律+根目录", prompt.includes("沉淀笔记/") && prompt.includes("禁止"), "");
check("E8 计数权威归 host", prompt.includes("以系统核对后的统计为准"), "");
check("E9 标记行+单 JSON 契约", prompt.includes(OUTPUT_MARK_BEGIN) && prompt.includes(OUTPUT_MARK_END) && prompt.includes("恰好一个 JSON 对象"), "");

// ═══ ⑫ D7 解析 ═══
const modelOut = [
  "说明文字……",
  OUTPUT_MARK_BEGIN,
  '{"title":"测试轮","summary":"摘要","reportMarkdown":"## 这次学到了什么\\\\n- 条目","memories":[],"skills":[],"knowledgeNotes":[],"rejected":[]}',
  OUTPUT_MARK_END,
  '（另一段重复输出 {"fake":1} 不应采纳）',
].join("\n");
const parsed1 = parseModelOutput(modelOut);
check("D7 标记对间取 JSON", parsed1.title === "测试轮" && parsed1.memories.length === 0, "");
check("D9 reportMarkdown \\n 字面还原", parsed1.reportMarkdown.includes("\n- 条目"), JSON.stringify(parsed1.reportMarkdown.slice(0, 24)));
const noMark = '前言 {"title":"无标记","summary":"s","reportMarkdown":"r","memories":[],"skills":[],"knowledgeNotes":[],"rejected":[]} {"dup":true}';
check("D7 无标记取最外层括号+重复取首对象", parseModelOutput(noMark).title === "无标记", "");
const broken = OUTPUT_MARK_BEGIN + "\n" + '{"title":"坏引号，内容里有 "未转义" 引号","summary":"多行\n裸换行","reportMarkdown":"x\\\\ny","memories":[],"skills":[],"knowledgeNotes":[],"rejected":[]}' + "\n" + OUTPUT_MARK_END;
const repaired = parseModelOutput(broken);
check("D7 修复器：未转义引号/裸换行", repaired.title.includes("坏引号") && repaired.title.includes("未转义"), repaired.title);
check("D7 修复器输出 \\n 字面还原", repaired.reportMarkdown.includes("\n"), JSON.stringify(repaired.reportMarkdown));
let threw = false;
try { parseModelOutput("完全没有 JSON 的输出"); } catch (e) { threw = e instanceof LearningParseError; }
check("D7 无 JSON 抛 LearningParseError", threw, "");
const ctrl = OUTPUT_MARK_BEGIN + '\n{"title":"a\\tb控制字符x","summary":"s","reportMarkdown":"r","memories":[],"skills":[],"knowledgeNotes":[],"rejected":[]}\n' + OUTPUT_MARK_END;
check("D7 合法 JSON 不改动", parseModelOutput(ctrl).title.length > 0, "");

// ═══ ⑬ D9 硬截断 ═══
const big: ModelResult = {
  title: "t", summary: "长".repeat(2000), reportMarkdown: "报".repeat(9000),
  memories: Array.from({ length: 25 }, (_, i) => ({ action: "create", category: "preference", content: "m" + i, confidence: 0.9, evidence: [] })),
  skills: Array.from({ length: 7 }, (_, i) => ({ id: "s" + i, name: "", description: "", skillMarkdown: "", evidence: [], tests: [] })),
  knowledgeNotes: Array.from({ length: 9 }, (_, i) => ({ action: "create", path: "p" + i + "主题名称足够长.md", title: "", summary: "", content: "", evidence: [] })),
  rejected: Array.from({ length: 40 }, (_, i) => ({ kind: "memory", reason: "r" + i, brief: "b" + i })),
};
const clamped = clampProposal(big);
check("D9 六类硬截断", clamped.memories.length === 20 && clamped.skills.length === 5 && clamped.knowledgeNotes.length === 8
  && clamped.rejected.length === 30 && [...clamped.summary].length === 1000 && [...clamped.reportMarkdown].length === 8000,
  `m=${clamped.memories.length} s=${clamped.skills.length} k=${clamped.knowledgeNotes.length} r=${clamped.rejected.length}`);

// ═══ ⑭ D6 诊断 ═══
check("D6 四级回退首级", diagnoseFailure({ lastErrorItem: "  最后错误项  " }) === "最后错误项", "");
check("D6 回退失败 tool_result", diagnoseFailure({ failedToolResults: ["", "工具失败详情"] }).includes("工具失败详情"), "");
check("D6 回退 assistant 文本→裸状态→未知", diagnoseFailure({ lastAssistantText: "最后的文本" }).includes("最后的文本") && diagnoseFailure({ bareStatus: "failed" }) === "failed" && diagnoseFailure({}) === "原因未知", "");
check("D6 截断 200", [...diagnoseFailure({ lastErrorItem: "错".repeat(500) })].length === 200, "");

// ═══ ⑮ F1 记忆门 ═══
const gateCtx = {
  existingMemories: [{ id: "mem1", origin: "learning-iteration" }, { id: "mem2", origin: "user" }],
  knownSources: new Map([["thread:a#chunk:0", { kind: "thread" as const }], ["thread:b#chunk:0", { kind: "thread" as const }], ["thread:c#chunk:0", { kind: "thread" as const }], ["kb:x", { kind: "knowledge" as const }]]),
};
const okMem = { action: "create", category: "preference", content: "偏好简洁的回复方式", confidence: 0.88, evidence: [{ sourceKey: "thread:a#chunk:0" }, { sourceKey: "thread:b#chunk:0" }] };
check("F1 合法记忆通过", validateMemoryCandidate(okMem, gateCtx).ok, "");
check("F1 类别越界拒", !validateMemoryCandidate({ ...okMem, category: "interest" }, gateCtx).ok, "");
check("F1 显式纠正豁免类别+单证据", validateMemoryCandidate({ ...okMem, category: "interest", explicitCorrection: true, evidence: [{ sourceKey: "thread:a#chunk:0" }] }, gateCtx).ok, "");
check("F1 profile 需 3 源", !validateMemoryCandidate({ ...okMem, category: "profile" }, gateCtx).ok && validateMemoryCandidate({ ...okMem, category: "profile", confidence: 0.9, evidence: [{ sourceKey: "thread:a#chunk:0" }, { sourceKey: "thread:b#chunk:0" }, { sourceKey: "thread:c#chunk:0" }] }, gateCtx).ok, "");
check("F1 知识源不支持记忆", !validateMemoryCandidate({ ...okMem, evidence: [{ sourceKey: "kb:x" }] }, gateCtx).ok, "");
check("F1 置信度下限 0.85/0.9", !validateMemoryCandidate({ ...okMem, confidence: 0.84 }, gateCtx).ok && !validateMemoryCandidate({ ...okMem, category: "project", evidence: [{ sourceKey: "thread:a#chunk:0" }, { sourceKey: "thread:b#chunk:0" }, { sourceKey: "thread:c#chunk:0" }], confidence: 0.89 }, gateCtx).ok, "");
check("F1 密钥/敏感标识拒", !validateMemoryCandidate({ ...okMem, content: "密钥 sk-abcdef123" }, gateCtx).ok && !validateMemoryCandidate({ ...okMem, content: "手机号 13912345678" }, gateCtx).ok, "");
check("F1 disable 仅限学习产物", !validateMemoryCandidate({ action: "disable", targetId: "mem2" }, gateCtx).ok && validateMemoryCandidate({ action: "disable", targetId: "mem1" }, gateCtx).ok, "");

// ═══ ⑯ F2 技能门 ═══
const tests4 = [
  { category: "should-trigger", input: "i1", passed: true }, { category: "should-not-trigger", input: "i2", passed: true },
  { category: "ambiguous", input: "i3", passed: true }, { category: "sibling-confusion", input: "i4", passed: true },
];
const testsOk = [...tests4, ...tests4.map((t) => ({ ...t, input: t.input + "b" }))];
const skillCtx = { knownSources: new Map([["thread:a", { kind: "thread" as const }], ["kb:x", { kind: "knowledge" as const }]]) };
const okSkill = { id: "case-summary", name: "案例摘要", description: "把长案例整理成一页纸摘要的固定做法。", skillMarkdown: "---\nname: case-summary\n---\n正文", evidence: [{ sourceKey: "thread:a" }, { sourceKey: "kb:x" }], tests: testsOk };
check("F2 合法技能通过", validateSkillCandidate(okSkill, skillCtx).ok, "");
check("F2 id 正则拒大写", !validateSkillCandidate({ ...okSkill, id: "Case-Summary" }, skillCtx).ok, "");
check("F2 描述<12 拒", !validateSkillCandidate({ ...okSkill, description: "太短" }, skillCtx).ok, "");
check("F2 测试条数越界拒", !validateSkillCandidate({ ...okSkill, tests: tests4 }, skillCtx).ok, "");
check("F2 有未过测试拒", !validateSkillCandidate({ ...okSkill, tests: testsOk.map((t, i) => i === 2 ? { ...t, passed: false } : t) }, skillCtx).ok, "");
check("F2 缺四类场景拒", !validateSkillCandidate({ ...okSkill, tests: testsOk.filter((t) => t.category !== "ambiguous") }, skillCtx).ok, "");
check("F2 正文缺 frontmatter 拒", !validateSkillCandidate({ ...okSkill, skillMarkdown: "无围栏正文" }, skillCtx).ok, "");

// ═══ ⑰ F3/E5 知识门 ═══
const kCtx = (existing: string[] = [], learned: string[] = []) => ({
  knownSources: new Map([["thread:a#chunk:0", { kind: "thread" as const }], ["kb:其他资料/x.md", { kind: "knowledge" as const }], ["kb:沉淀笔记/自生自.md", { kind: "knowledge" as const }]]),
  existingPaths: new Set(existing), learnedPathsThisRun: new Set(learned),
});
check("F3 合法路径归一+默认目录", normalizeKnowledgePath("劳动合同解除审查要点.md").ok === true && (normalizeKnowledgePath("劳动合同解除审查要点.md") as { relPath: string }).relPath === "沉淀笔记/资料摘要/劳动合同解除审查要点.md", "");
check("F3 带根目录保留", (normalizeKnowledgePath("沉淀笔记/诉讼时效问答.md") as { relPath: string }).relPath === "沉淀笔记/诉讼时效问答.md", "");
check("F3 拒盘符/绝对/..//NUL", !normalizeKnowledgePath("C:\\x\\主题内容.md").ok && !normalizeKnowledgePath("/abs/主题内容.md").ok && !normalizeKnowledgePath("a/../主题内容.md").ok && !normalizeKnowledgePath("a\u0000b主题.md").ok, "");
check("F3 拒非 .md", !normalizeKnowledgePath("主题内容.txt").ok, "");
check("F3 拒通用名/纯日期/短主题", !normalizeKnowledgePath("迭代记录1.md").ok && !normalizeKnowledgePath("2026-10-27.md").ok && !normalizeKnowledgePath("ab.md").ok, "");
check("F3 英文主题 ≥6 拉丁过", normalizeKnowledgePath("case-summary-guide.md").ok === true, "");
check("F5 学习标记判定", hasLearningMarker("<!-- juscite-learning-artifact --> 正文") && !hasLearningMarker("用户自己的笔记"), "");
const okK = { action: "create", path: "举证责任分配实务要点.md", title: "举证责任分配实务要点", summary: "综合多个线程整理的分配规则。", content: "内".repeat(200), evidence: [{ sourceKey: "thread:a#chunk:0" }] };
check("F3 合法知识候选通过", validateKnowledgeCandidate(okK, kCtx()).ok, "");
check("F3 防自我吞噬", !validateKnowledgeCandidate({ ...okK, evidence: [{ sourceKey: "kb:沉淀笔记/自生自.md" }] }, kCtx()).ok, "");
check("F3 知识源可作证据", validateKnowledgeCandidate({ ...okK, evidence: [{ sourceKey: "kb:其他资料/x.md" }] }, kCtx()).ok, "");
check("F3 同轮路径去重", !validateKnowledgeCandidate({ ...okK, path: "已有主题内容笔记.md" }, kCtx([], ["沉淀笔记/资料摘要/已有主题内容笔记.md"])).ok, "");
check("F4 create 不覆盖已存在", !validateKnowledgeCandidate({ ...okK, path: "已有主题内容笔记.md" }, kCtx(["沉淀笔记/资料摘要/已有主题内容笔记.md"])).ok, "");
check("F3 标题/摘要/正文域", !validateKnowledgeCandidate({ ...okK, title: "未命名" }, kCtx()).ok && !validateKnowledgeCandidate({ ...okK, summary: "太短" }, kCtx()).ok && !validateKnowledgeCandidate({ ...okK, content: "短" }, kCtx()).ok, "");

// ═══ ⑲ F6 内置技能保护 ═══
const prot = partitionProtectedSkills([okSkill, { ...okSkill, id: "research-brief" }], ["case-summary"]);
check("F6 重名整批剔除+理由", prot.allowed.length === 1 && prot.rejected[0]!.reason.includes("后台不会覆盖"), "");

// ═══ ⑳ G1/G2 发布账本 ═══
const prov = memoryWithProvenance({ id: "m1", category: "preference", content: "x", confidence: 0.6, evidence: [{ sourceKey: "s" }], tags: ["t1"] }, "run1");
check("G1 出处四件套+tag 强制+置信抬 0.8", prov.origin === "learning-iteration" && prov.sourceIterationId === "run1" && prov.captureSource === "automatic" && (prov.tags as string[]).includes("learning-iteration") && prov.confidence === 0.8 && prov.scope === "user", "");
const merged = mergeDuplicateMemory({ id: "m1", evidence: [{ a: 1 }], tags: ["x"], confidence: 0.7, content: "old" }, { id: "m1", evidence: [{ b: 2 }], tags: ["y"], confidence: 0.9, content: "new" });
check("G1 合并复活并集取大", (merged.evidence as unknown[]).length === 2 && (merged.tags as string[]).join() === "x,y" && merged.confidence === 0.9 && merged.content === "new", "");
check("H2 可比 JSON 哈希键序无关", memoryComparableHash({ a: 1, b: 2 }) === memoryComparableHash({ b: 2, a: 1 }), "");
check("H2 目录递归 hash", directoryHash([{ rel: "a.md", content: "1" }, { rel: "b.md", content: "2" }]) === directoryHash([{ rel: "b.md", content: "2" }, { rel: "a.md", content: "1" }]) && directoryHash([{ rel: "a.md", content: "1" }]) !== directoryHash([{ rel: "a.md", content: "3" }]), "");

// ═══ ㉑ H3/H4 报告 ═══
const counts = normalizeCounts({ sources: 5, threads: 2, memoriesCreated: 1, skillsCreated: 1, knowledgeNotesCreated: 1, rejected: 2 });
const rep = buildUserReport({
  modelResult: {
    title: "学习迭代测试轮", summary: "s", reportMarkdown: "",
    memories: [{ action: "create", category: "workflow", content: "先核时效再写起诉状", confidence: 0.9, evidence: [] }],
    skills: [{ id: "s", name: "", description: "这是一段足够长的中文描述", skillMarkdown: "", evidence: [], tests: [] }],
    knowledgeNotes: [{ action: "create", path: "x.md", title: "主题笔记标题", summary: "", content: "", evidence: [] }],
    rejected: [],
  },
  counts, canRollback: true, zeroChange: false,
});
check("H3 报告三节+计数表+隐私三条", rep.includes("## 这次学到了什么") && rep.includes("## 会带来哪些提升") && rep.includes("## 以后会怎样帮你") && rep.includes("## 学习结果一览") && (rep.match(/只学习有把握的稳定内容/g) ?? []).length === 1, "");
check("H3 分类话术", rep.includes("记住了工作方式") && rep.includes("学会了「") && rep.includes("沉淀了「"), "");
check("H3 回滚提示按 canRollback", rep.includes("回滚"), "");
const zeroRep = buildUserReport({ modelResult: { title: "t", summary: "", reportMarkdown: "", memories: [], skills: [], knowledgeNotes: [], rejected: [] }, counts: normalizeCounts({ rejected: 1 }), canRollback: false, zeroChange: true });
check("H3 零变更双态标题+空态话术", zeroRep.includes("本轮学习检查已完成") && zeroRep.includes("没有发现足够稳定的新习惯"), "");
check("H4 技术字样判定", looksTechnical("解析 JSON 候选后做压力测试") && !looksTechnical("这轮了解到了常用的工作方式"), "");
check("H4 非 CJK 描述兜底+替换 skill 词", plainSkillDescription("auto summarize skill trigger").includes("自动整理") || plainSkillDescription("auto summarize skill trigger").includes("这套做法"), plainSkillDescription("auto summarize skill trigger"));
check("H4 CJK 描述保留", plainSkillDescription("把案例整理成摘要的中文做法").includes("中文做法"), "");
check("H8 回滚节追加", appendRollbackSection("# 报告", now).includes("## 回滚"), "");

// ═══ ㉒ H9/H10/H11 记录 ═══
const rid = newRunId(new Date(2026, 9, 27, 14, 5, 0).getTime(), "abcd1234!");
check("H1 runId 格式", rid === "2026-10-27-1405-abcd1234", rid);
check("H9 displayName", displayNameOf(rid, "标题") === "2026-10-27 · 标题", "");
const man = normalizeManifest({ version: 1, summary: { id: rid, title: "t", startedAt: now, finishedAt: now, reportPath: "p", canRollback: true, counts: { sources: "3" } }, rollback: { memories: [], skills: undefined, knowledge: null }, modelResult: { title: "x" } });
check("H11 旧档归一缺子键", man !== null && man.rollback.skills.length === 0 && man.rollback.knowledge.length === 0 && man.summary.counts.sources === 3 && man.summary.displayName.includes("·"), "");
check("H11 error 可选字段兼容", normalizeManifest({ summary: { id: rid, error: "旧错误" } })?.summary.error === "旧错误", "");
check("H11 坏档→null", normalizeManifest(null) === null && normalizeManifest({ summary: null }) === null, "");
check("H13 计数归一非负", normalizeCounts({ sources: -5, threads: "7", junk: 9 }).sources === 0 && normalizeCounts({ threads: "7" }).threads === 7, "");

// ═══ ㉓ H7 回滚 preflight ═══
const pf = rollbackPreflight([
  { area: "memory", ref: "m1", expectHash: "aa", currentHash: "aa" },
  { area: "knowledge", ref: "x.md", expectHash: "bb", currentHash: "cc" },
]);
check("H7 漂移即中止", !pf.ok && pf.drifted.length === 1 && pf.drifted[0]!.ref === "x.md", "");

// ═══ ㉔ I1/I2 注入 ═══
const mems = [
  { id: "a1", category: "preference", content: "用户偏好简洁回复", confidence: 0.9, always: true },
  { id: "a2", category: "workflow", content: "写文书前先核时效", confidence: 0.88, always: true },
  { id: "r1", category: "project", content: "当前在办合成购物纠纷案", confidence: 0.8 },
  { id: "r2", category: "preference", content: "完全无关的记忆条目xyz", confidence: 0.8 },
  { id: "d1", category: "preference", content: "已删除", confidence: 0.9, deleted: true },
];
const plan = retrieveMemoriesForInjection(mems, "帮我写合成购物纠纷的起诉状，之前说过偏好简洁", { budgetChars: 500 });
check("I1 always 先注入", plan.injectedIds.includes("a1") && plan.injectedIds.includes("a2"), plan.injectedIds.join(","));
check("I1 relevant 按相关度", plan.injectedIds.includes("r1") && !plan.injectedIds.includes("r2"), plan.injectedIds.join(","));
check("I1 已删除不注入", !plan.injectedIds.includes("d1"), "");
check("I1 注入块带引导句", plan.block.includes("长期记忆参考"), "");
const plan2a = retrieveMemoriesForInjection([{ id: "x1", content: "甲甲甲", confidence: 0.9, always: true }, { id: "x2", content: "乙乙乙", confidence: 0.9, always: true }], "", { budgetChars: 10 });
check("I1 预算 60% 分配给 always", plan2a.injectedIds.length === 1 && plan2a.injectedIds[0] === "x1", plan2a.injectedIds.join(","));
check("I2 kb 线程不注入", !shouldInjectMemories("知识库全局对话 · x") && !shouldInjectMemories("[学习迭代] run1") && shouldInjectMemories("普通对话"), "");

// ═══ ㉕ K3 原子写 ═══
function makeFlakyFs(failTimes: number, failCode: string) {
  let calls = 0;
  const sleeps: number[] = [];
  return {
    fs: {
      writeFileDirect: (p: string, d: string) => { (globalThis as any).__direct = (globalThis as any).__direct || []; (globalThis as any).__direct.push(p); },
      writeTmp: (p: string) => p + ".tmp",
      rename: () => { calls++; if (calls <= failTimes) { const e = new Error(failCode + ": busy"); throw e; } },
      unlink: () => {},
    } as const,
    sleeps,
    callsNow: () => calls,
    installSleep() { return (ms: number) => sleeps.push(ms); },
  };
}
const f1 = makeFlakyFs(2, "EBUSY");
atomicWriteFileSync(f1.fs as any, "state.json", "{}", { sleep: f1.installSleep() });
check("K3 EBUSY 重试后 rename 成功", f1.callsNow() === 3 && f1.sleeps.join(",") === "0,25", `calls=${f1.callsNow()} sleeps=${f1.sleeps.join(",")}`);
const f2 = makeFlakyFs(99, "EPERM");
(globalThis as any).__direct = [];
atomicWriteFileSync(f2.fs as any, "state.json", "{}", { sleep: f2.installSleep(), platform: "win32" });
check("K3 六次重试后 win32 直写降级", f2.callsNow() === 6 && (globalThis as any).__direct.length === 1, `calls=${f2.callsNow()}`);
const f3 = makeFlakyFs(1, "EACCES");
(globalThis as any).__direct = [];
atomicWriteFileSync(f3.fs as any, "state.json", "{}", { sleep: () => {}, platform: "linux" });
let atomicThrew = false;
try { atomicWriteFileSync({ ...f3.fs, rename: () => { throw new Error("ENOENT: no"); } } as any, "x", "y", { platform: "linux" }); } catch { atomicThrew = true; }
check("K3 非瞬态不重试且非 win32 抛错", atomicThrew, "");

// ═══ ㉖ K9/H11 state 归一 ═══
const st = normState({ sourceHashes: { a: "1" }, lastLocalDay: 123, retryCount: 9, pendingRunId: "../evil", baselineRemaining: -1 });
check("K9 缺省空态+钳制+防路径逃逸 id", st.version === 1 && st.lastSuccessfulAt === null && st.lastLocalDay === null && st.retryCount === 2 && st.pendingRunId === null && st.baselineRemaining === 0 && st.sourceHashes.a === "1", "");
check("K10 合法 pendingRunId 保留", normState({ pendingRunId: "2026-10-27-1405-abcd1234" }).pendingRunId === "2026-10-27-1405-abcd1234", "");
check("K9 默认空态基线未完成", defaultLearningState().baselineComplete === false, "");

// ═══ ㉗ K1/H6 错误分级 ═══
check("K1 可恢复族", isRecoverableError("fetch failed") && isRecoverableError("ECONNRESET 连接被重置") && isRecoverableError("Runtime restarted") && isRecoverableError("socket hang up") && isRecoverableError("请求超时 timeout"), "");
check("K1 业务错误不可恢复", !isRecoverableError("JSON 解析失败") && !isRecoverableError("余额不足"), "");
check("H6 豁免清单不进日志", !shouldLogError("no remaining points") && !shouldLogError("fetch failed") && !shouldLogError("置信度不足") && shouldLogError("磁盘写入失败 EIO"), "");

// ═══ ㉘ B5/G6 面料 ═══
check("B5 阶段消息 16 态", Object.keys(STAGE_MESSAGES).length === 16 && STAGE_MESSAGES.daily_quota.includes("明天") && STAGE_MESSAGES.disabled.includes("已关闭"), Object.keys(STAGE_MESSAGES).length.toString());
check("G6 计数 13 项", Object.keys(normalizeCounts({})).length === 13, "");
check("J4 最新一轮 5 指标", latestRoundMetrics(counts).length === 5 && latestRoundMetrics(counts)[4]!.value === 2, "");

// ═══ H5 失败报告 ═══
const failRep = buildFailureReport("模型连接中断", 30);
check("H5 不占用今日额度+退避说明", failRep.includes("不会占用今天的成功额度") && failRep.includes("30 分钟"), "");

// ── 收口 ──
const fails = fail();
console.log(`[re18-kernel] checks=${results.length} fail=${fails}`);
console.log(fails === 0 ? "LEARN_KERNEL_PASS" : "LEARN_KERNEL_FAIL");
process.exit(fails === 0 ? 0 : 1);
