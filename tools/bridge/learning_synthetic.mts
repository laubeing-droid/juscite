// 功能 #18 学习迭代合成用例·件2（RE-18 验收口径，全部合成材料）：
// A 段=运行时单驱（createLearningRuntime 全 IO 注入假件，不占端口）：
//   ①C13 无候选不建空报告 ②全链成功：采集（RAG 剥离/打招呼过滤）→三门→发布三件套→
//   回滚账本→游标推进（C10）→基线推进（K9）③D8 修复轮（MODEL_OUTPUT_RETRY_1+修复提示词）
//   ④K1 可恢复错误保留 pendingRunId 不写失败记录 ⑤K10 续跑复用 runId/run 目录 ⑥A7 失败退避
//   ⑦A3/A4 今日额度+排队清除 ⑧D5 取消两态 ⑨I1/I2 注入计划与豁免 ⑩H7 回滚 preflight 漂移中止
//   ⑪G5 发布中断逆序撤销 ⑫F6 内置技能保护 ⑬A6 线程面失败保守忙 ⑭E5/F3 通用名拒收
// B 段=隔离桥（BRIDGE_TEST_PORT 默认 3078 + mock oc28 + 预置库行/知识文件/材料；不碰 :3030/:43127）：
//   ⑮B2 status 全载荷键面+A1 默认开 ⑯手动排队全链（记录/REPORT/manifest/知识落盘/记忆落盘/
//   技能落盘/学习线程标题 [学习迭代] 前缀）⑰A3 手动也不破日额度 ⑱H8 回滚逆序+记录 rolled_back
//   ⑲H10 id 正则防路径逃逸 ⑳J15 未初始化兜底（根不可建桥实例）
// 末行 LEARN_SYNTH_PASS / LEARN_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { DatabaseSync } from "node:sqlite";
import { cpSync, existsSync, mkdirSync, openSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { AddressInfo } from "node:net";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { createLearningRuntime } from "./learning_runtime.mjs";
import { LEARNING_THREAD_PREFIX, OUTPUT_MARK_BEGIN, OUTPUT_MARK_END, RUN_ID_RE } from "../../packages/juscite-legal/src/kernel/learningModel.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3078);
const SCRATCH = join(REPO_ROOT, ".local", `re18-scratch-${Date.now()}`);
const NODE = process.execPath;
const results: Array<{ name: string; ok: boolean }> = [];
function check(name: string, ok: boolean, detail = "") {
  results.push({ name, ok });
  console.log(`[re18-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const fails = () => results.filter((r) => !r.ok).length;

// 模型输出装配（合成提案：一条记忆+一条知识笔记；技能按用例可选）
const THREAD_A = "ses_seed_0001";
const THREAD_B = "ses_seed_0002";
const NOTE_BODY = "综合多个线程的做法，举证责任分配按「谁主张谁举证」为基线，例外情形由法庭依职权审查；具体到合同纠纷中，违约方通常就免责事由举证。本条为合成笔记正文，长度满足下限要求，内容全部为合成材料，不含任何真实案件信息。".slice(0, 200);
function proposalJson(opts?: { skill?: boolean; builtinSkillId?: string; badNoteName?: string; allRejected?: boolean }): string {
  const memCat = opts?.allRejected ? "interest" : "workflow";
  const skills = opts?.builtinSkillId
    ? [{ id: opts.builtinSkillId, name: "冒名", description: "这是一段足够长的中文描述文本", skillMarkdown: "---\nname: x\n---\n正文", evidence: [{ sourceKey: `thread:${THREAD_A}`, sourceKind: "thread" }, { sourceKey: `thread:${THREAD_B}`, sourceKind: "thread" }], tests: genTests() }]
    : opts?.skill
      ? [{ id: "evidence-checklist", name: "证据清单先行", description: "写文书前先列证据清单再动笔的固定做法，来自用户反复执行的工作方式。", skillMarkdown: "---\nname: evidence-checklist\n---\n# 证据清单先行\n先列清单再动笔。", evidence: [{ sourceKey: `thread:${THREAD_A}`, sourceKind: "thread" }, { sourceKey: `thread:${THREAD_B}`, sourceKind: "knowledge" }], tests: genTests() }]
      : [];
  return JSON.stringify({
    title: "写作习惯与举证要点",
    summary: "这轮了解了你常用的写作习惯，并整理了一条举证要点笔记。",
    reportMarkdown: "## 这次学到了什么\n- 记住了工作方式：先列证据清单再写正文\n\n## 会带来哪些提升\n- 学会了「证据清单先行」\n\n## 以后会怎样帮你\n- 起草文书时主动附证据清单。",
    memories: [{ action: "create", category: memCat, content: "写文书前先列证据清单再动笔", confidence: 0.9, evidence: [{ sourceKey: `thread:${THREAD_A}`, sourceKind: "thread" }, { sourceKey: `thread:${THREAD_B}`, sourceKind: "thread" }], explicitCorrection: false }],
    skills,
    knowledgeNotes: [{ action: "create", path: opts?.badNoteName ?? "举证责任分配实务要点.md", title: "举证责任分配实务要点", summary: "综合两个线程的举证分配做法与例外情形。", content: NOTE_BODY, evidence: [{ sourceKey: `thread:${THREAD_A}`, sourceKind: "thread" }] }],
    rejected: [],
  });
}
function genTests() {
  const base = [
    { category: "should-trigger", input: "帮我起草起诉状", passed: true },
    { category: "should-not-trigger", input: "今天天气如何", passed: true },
    { category: "ambiguous", input: "整理一下这个", passed: true },
    { category: "sibling-confusion", input: "帮我审合同", passed: true },
  ];
  return [...base, ...base.map((t) => ({ ...t, input: t.input + "（变体）" }))];
}
function markedOutput(json: string): string {
  return `分析如下：\n${OUTPUT_MARK_BEGIN}\n${json}\n${OUTPUT_MARK_END}\n以上。`;
}

// ═══ A 段：运行时单驱 ═══
mkdirSync(SCRATCH, { recursive: true });
function makeFakeIo(opts?: { runTurnImpl?: (p: { prompt: string; attempt: number }) => Promise<{ ok: boolean; text?: string; error?: string }> }) {
  const root = join(SCRATCH, "rt-" + Math.random().toString(36).slice(2, 8));
  mkdirSync(root, { recursive: true });
  const kbRoot = join(root, "kb");
  const skillsRoot = join(root, "skills");
  const matsDir = join(root, "materials");
  const wsDir = join(root, "ws");
  for (const d of [kbRoot, skillsRoot, matsDir, wsDir]) mkdirSync(d, { recursive: true });
  const memories: Array<Record<string, unknown>> = [];
  let attempt = 0;
  const kbSyncCalls = { n: 0 };
  const io = {
    root, kbRoot, skillsRoot, matsDir, wsDir, memories, kbSyncCalls,
    dep: {
      root,
      loadSettings: () => ({ enabled: true, idleMinutes: 15, keepRunningInTray: true }),
      listThreads: () => [
        { id: THREAD_A, title: "合成线程甲", workspaceKey: "ws://main", phase: "completedSuccess", updatedAt: 1000 },
        { id: THREAD_B, title: "合成线程乙", workspaceKey: "ws://main", phase: "completedSuccess", updatedAt: 2000 },
      ],
      threadRows: (id: string) => id === THREAD_A
        ? [
            { kind: "userInput", state: "complete", text: "帮我看看这个合同怎么写\n## 所内资料\n[来源1] 合成条文", createdAt: 1 },
            { kind: "userInput", state: "complete", text: "在吗", createdAt: 2 },
            { kind: "assistantText", state: "complete", text: "好的，我们先列证据清单。", createdAt: 3 },
          ]
        : [{ kind: "userInput", state: "complete", text: "写文书前一般怎么做比较好？我想固定一个流程。", createdAt: 4 }],
      workspacePathOf: () => wsDir,
      materialsList: () => { try { return readdirSync(matsDir).map((name) => ({ name, abs: join(matsDir, name), sizeBytes: statSize(join(matsDir, name)) })); } catch { return []; } },
      readMaterialText: (abs: string) => readFileSync(abs, "utf-8"),
      kbWalk: () => { try { return readdirSync(kbRoot).filter((f) => f.endsWith(".md")).map((rel) => ({ rel, abs: join(kbRoot, rel), sizeBytes: statSize(join(kbRoot, rel)), mtimeMs: 0 })); } catch { return []; } },
      kbReadText: (abs: string) => { try { return readFileSync(abs, "utf-8"); } catch { return null; } },
      kbRoot: () => kbRoot,
      skillsRoot: () => skillsRoot,
      kbSync: async () => { kbSyncCalls.n++; },
      skillsList: () => { try { return readdirSync(skillsRoot).map((id) => ({ id, dir: join(skillsRoot, id), md: existsSync(join(skillsRoot, id, "SKILL.md")) ? readFileSync(join(skillsRoot, id, "SKILL.md"), "utf-8") : "" })); } catch { return []; } },
      protectedSkillIds: () => ["juscite-builtin-timeline-generation"],
      readDocxText: null,
      runTurn: async ({ prompt, shouldCancel }: { prompt: string; shouldCancel?: () => boolean }) => {
        const a = attempt++;
        if (opts?.runTurnImpl) return opts.runTurnImpl({ prompt, attempt: a });
        return { ok: true, text: markedOutput(proposalJson({ skill: true })) };
      },
      auditWrite: (_a: string, _t: string, _d?: string) => {},
      pollMs: 3_600_000,
      log: (_m: string) => {},
      now: () => Date.now(),
    } as any,
  };
  return io;
}
function statSize(p: string): number { try { return statSync(p).size; } catch { return 0; } }

// ① C13 无候选不建空报告
{
  const io = makeFakeIo();
  io.dep.listThreads = () => [];
  io.dep.materialsList = () => [];
  const rt = createLearningRuntime(io.dep);
  const r = await rt.tick({ manual: true });
  const state = JSON.parse(readFileSync(join(io.root, "state.json"), "utf-8"));
  const st = rt.status();
  check("C13 无候选只更新检查时间不建记录", r.ok === true && r.noNewData === true && state.lastCheckedAt > 0 && !existsSync(join(io.root, "runs")), `runs=${existsSync(join(io.root, "runs"))}`);
  check("C13 消息=无新数据", st.message.includes("没有发现值得学习的新数据"), st.message);
  check("K9 首轮 state 为空态基线", state.baselineComplete === false && state.pendingRunId === null, "");
}

// ② 全链成功
{
  const io = makeFakeIo();
  const kbNote = join(io.kbRoot, "既有知识笔记.md");
  writeFileSync(kbNote, "# 既有知识\n举证责任的一般原则内容，合成材料，用于知识源采集与证据引用测试。".repeat(3), "utf-8");
  const rt = createLearningRuntime(io.dep) as any;
  const q = await rt.queue();
  await sleep(300);
  // 等跑完
  let st = rt.status();
  for (let i = 0; i < 40 && st.running; i++) { await sleep(150); st = rt.status(); }
  check("全链：状态 completed+今日额度生效", st.status === "completed" && st.eligibleToday === "done-today", `status=${st.status} elig=${st.eligibleToday}`);
  const runIds = readdirSync(join(io.root, "runs"));
  check("H1 run 目录+五件套", runIds.length === 1 && RUN_ID_RE.test(runIds[0]!) && existsSync(join(io.root, "runs", runIds[0]!, "REPORT.md"))
    && existsSync(join(io.root, "runs", runIds[0]!, "manifest.json")) && existsSync(join(io.root, "runs", runIds[0]!, "INPUT.md"))
    && existsSync(join(io.root, "runs", runIds[0]!, "MODEL_OUTPUT.txt")) && existsSync(join(io.root, "runs", runIds[0]!, "rollback", "skills")), `dir=${runIds[0] ?? "?"}`);
  const inputMd = readFileSync(join(io.root, "runs", runIds[0]!, "INPUT.md"), "utf-8");
  check("C1 语料留档含 RAG 剥离后正文、无打招呼", inputMd.includes("帮我看看这个合同怎么写") && !inputMd.includes("所内资料") && !inputMd.includes("在吗"), "");
  check("C5 知识源采集+证据引用可达", inputMd.includes("既有知识笔记"), "");
  const manifest = JSON.parse(readFileSync(join(io.root, "runs", runIds[0]!, "manifest.json"), "utf-8"));
  check("G6 计数 13 项+记忆/知识发布计数", Object.keys(manifest.summary.counts).length === 13 && manifest.summary.counts.memoriesCreated === 1 && manifest.summary.counts.knowledgeNotesCreated === 1 && manifest.summary.canRollback === true, `mem=${manifest.summary.counts.memoriesCreated}`);
  const memsOnDisk = JSON.parse(readFileSync(join(io.root, "memories.json"), "utf-8")) as Array<Record<string, unknown>>;
  check("G1 记忆落盘出处四件套+tag", memsOnDisk.length === 1 && memsOnDisk[0]!.origin === "learning-iteration" && memsOnDisk[0]!.sourceIterationId === runIds[0] && (memsOnDisk[0]!.tags as string[]).includes("learning-iteration") && memsOnDisk[0]!.confidence >= 0.8, JSON.stringify(memsOnDisk[0] ?? {}).slice(0, 80));
  check("G4 知识落盘 frontmatter+学习标记", (() => {
    const noteRel = "沉淀笔记/资料摘要/举证责任分配实务要点.md";
    const p = join(io.kbRoot, ...noteRel.split("/"));
    if (!existsSync(p)) return false;
    const t = readFileSync(p, "utf-8");
    return t.includes('generated_by: "learning-iteration"') && t.includes("juscite-learning-artifact") && t.includes("举证责任分配");
  })(), "");
  check("G4 写后触发知识库同步", io.kbSyncCalls.n >= 1, `n=${io.kbSyncCalls.n}`);
  check("G3 技能落盘三件套", existsSync(join(io.skillsRoot, "evidence-checklist", "SKILL.md")) && existsSync(join(io.skillsRoot, "evidence-checklist", "test-prompts.json")) && existsSync(join(io.skillsRoot, "evidence-checklist", "learning.json")), "");
  const skillMd = readFileSync(join(io.skillsRoot, "evidence-checklist", "SKILL.md"), "utf-8");
  check("G3 frontmatter 重建 name=id 描述单行（单元二引号化后=双引号纯标量）", skillMd.startsWith('---\nname: "evidence-checklist"\ndescription: "') && !skillMd.split("\n")[2]!.includes("\n"), "");
  const state = JSON.parse(readFileSync(join(io.root, "state.json"), "utf-8"));
  check("C10 游标推进+K9 基线推进+lastLocalDay", state.sourceHashes["meta:thread:" + THREAD_A] !== undefined && state.baselineProcessed > 0 && typeof state.lastLocalDay === "string" && state.lastSuccessfulAt > 0, `meta=${state.sourceHashes["meta:thread:" + THREAD_A] !== undefined}`);
  check("H3 报告三节+计数表", readFileSync(join(io.root, "runs", runIds[0]!, "REPORT.md"), "utf-8").includes("## 这次学到了什么"), "");
  check("I1 注入计划含新记忆", (() => {
    const plan = rt.injectionPlan("帮我起草起诉状，按证据清单先行的习惯来");
    return plan.injectedIds.length === 1 && plan.block.includes("长期记忆参考");
  })(), "");
  check("I2 kb/学习线程不注入", rt.injectionAllowed("知识库全局对话 · x") === false && rt.injectionAllowed(`${LEARNING_THREAD_PREFIX} run`) === false && rt.injectionAllowed("普通对话") === true, "");
  // ⑰ H7：发布后改动记忆→回滚 preflight 漂移中止
  memsOnDisk[0]!.content = "被人为改过的记忆";
  writeFileSync(join(io.root, "memories.json"), JSON.stringify(memsOnDisk), "utf-8");
  let driftErr = "";
  try { await rt.rollback(runIds[0]!); } catch (e) { driftErr = String((e as Error).message ?? e); }
  check("H7 preflight 漂移即中止", driftErr.includes("回滚已停止"), driftErr.slice(0, 50));
  memsOnDisk[0]!.content = "写文书前先列证据清单再动笔";
  writeFileSync(join(io.root, "memories.json"), JSON.stringify(memsOnDisk), "utf-8");
  // ⑱ H8 回滚逆序
  const rb = await rt.rollback(runIds[0]!);
  check("H8 回滚后记录 rolled_back+文件删除", rb.status === "rolled_back" && rb.canRollback === false && !existsSync(join(io.kbRoot, "沉淀笔记", "资料摘要", "举证责任分配实务要点.md"))
    && (JSON.parse(readFileSync(join(io.root, "memories.json"), "utf-8")) as unknown[]).length === 0 && !existsSync(join(io.skillsRoot, "evidence-checklist")), "");
  check("H8 REPORT 追加回滚节", readFileSync(join(io.root, "runs", runIds[0]!, "REPORT.md"), "utf-8").includes("## 回滚"), "");
}

// ③ D8 修复轮
{
  const io = makeFakeIo({ runTurnImpl: async ({ attempt }: any) => {
    if (attempt === 0) return { ok: true, text: "模型说了一堆但没有合法 JSON {{{" };
    return { ok: true, text: markedOutput(proposalJson()) };
  } });
  const rt = createLearningRuntime(io.dep) as any;
  await rt.queue();
  let st = rt.status();
  for (let i = 0; i < 40 && st.running; i++) { await sleep(150); st = rt.status(); }
  const runId = readdirSync(join(io.root, "runs"))[0]!;
  check("D8 修复轮落盘 RETRY_1+修复提示带错误", existsSync(join(io.root, "runs", runId, "MODEL_OUTPUT_RETRY_1.txt")), "");
  check("D8 修复后完成", st.status === "completed", `status=${st.status}`);
}

// ④ D4 瞬时断连容错消息面（B5 reconnecting）：单次瞬时失败不再立即 K1，而是「连接恢复中」重试
{
  let calls = 0;
  let releaseTurn: () => void = () => {};
  const gate = new Promise<void>((r) => { releaseTurn = r; });
  const io = makeFakeIo({ runTurnImpl: async () => {
    calls++;
    if (calls === 1) return { ok: false, error: "fetch failed: ECONNRESET" };
    await gate;
    return { ok: true, text: markedOutput(proposalJson()) };
  } });
  const rt = createLearningRuntime(io.dep) as any;
  void rt.queue();
  await sleep(2200); // 首败 + 1.5s 后进入容错重试
  const stMid = rt.status();
  check("D4 容错重试消息=连接恢复中", stMid.message.includes("连接恢复中"), stMid.message);
  releaseTurn();
  await sleep(600);
  let st = rt.status();
  for (let i = 0; i < 40 && st.running; i++) { await sleep(200); st = rt.status(); }
  check("D4 容错后恢复完成", st.status === "completed" && calls === 2, `calls=${calls} status=${st.status}`);
}

// ⑤ K10 显式续跑复用 runId
{
  const io = makeFakeIo();
  const rt = createLearningRuntime(io.dep) as any;
  // 直接以 pendingRunId 注入假档（等价于上一轮 K1 断点；全新根=默认空态）
  const st0: any = { sourceHashes: {}, lastSuccessfulAt: null, lastCheckedAt: null, lastLocalDay: null, lastRetryAt: null, retryCount: 0, baselineComplete: false, baselineProcessed: 0, baselineRemaining: 0, pendingRunId: "2026-10-27-0900-resume01" };
  mkdirSync(join(io.root, "runs", st0.pendingRunId, "rollback", "skills"), { recursive: true });
  writeFileSync(join(io.root, "runs", st0.pendingRunId, "INPUT.md"), "# 上一轮语料留档（不应被改写）", "utf-8");
  writeFileSync(join(io.root, "state.json"), JSON.stringify(st0), "utf-8");
  await rt.tick({ manual: true });
  await sleep(300);
  let st = rt.status();
  for (let i = 0; i < 40 && st.running; i++) { await sleep(150); st = rt.status(); }
  const runIds = readdirSync(join(io.root, "runs"));
  check("K10 续跑 run 目录不换+INPUT 不重写", runIds.length === 1 && runIds[0] === st0.pendingRunId && readFileSync(join(io.root, "runs", runIds[0]!, "INPUT.md"), "utf-8").startsWith("# 上一轮语料留档"), `run=${runIds[0] ?? "?"}`);
}

// ⑥⑦ A7 退避 + A3/A4 额度与排队
{
  let calls = 0;
  const io = makeFakeIo({ runTurnImpl: async () => { calls++; return { ok: false, error: "磁盘写入失败 EIO" }; } });
  const rt = createLearningRuntime(io.dep) as any;
  await rt.queue();
  await sleep(400);
  check("H5 不可恢复错误写失败记录", calls === 1 && existsSync(join(io.root, "runs", readdirSync(join(io.root, "runs"))[0]!, "REPORT.md")), `calls=${calls}`);
  const rep = readFileSync(join(io.root, "runs", readdirSync(join(io.root, "runs"))[0]!, "REPORT.md"), "utf-8");
  check("H5 失败报告含不占用额度+退避分钟", rep.includes("不会占用今天的成功额度") && rep.includes("30 分钟"), "");
  const state = JSON.parse(readFileSync(join(io.root, "state.json"), "utf-8"));
  check("A7 失败记 lastRetryAt+retryCount=1", state.lastRetryAt > 0 && state.retryCount === 1, `rc=${state.retryCount}`);
  await rt.tick({ manual: false }); // A7 退避只拦自动 tick（手动=显式意图不拦，§3.2 forceRun 直入）
  await sleep(200);
  check("A7 退避窗口内自动不重查", calls === 1, `calls=${calls}`);
  // A3/A4：伪造今日成功→queue 拒+排队清除
  const st1 = JSON.parse(readFileSync(join(io.root, "state.json"), "utf-8"));
  st1.lastSuccessfulAt = Date.now();
  st1.lastLocalDay = new Date().toISOString().slice(0, 10);
  writeFileSync(join(io.root, "state.json"), JSON.stringify(st1), "utf-8");
  const q = await rt.queue();
  const st = rt.status();
  check("A3 今日已成功手动拒绝+额度话术", q.ok === false && q.reason === "done-today" && st.message.includes("明天"), q.message ?? "");
}

// ⑧ D5 取消
{
  let releaseTurn: () => void = () => {};
  const gate = new Promise<void>((r) => { releaseTurn = r; });
  const io = makeFakeIo({ runTurnImpl: async () => { await gate; return { ok: true, text: markedOutput(proposalJson()) }; } });
  const rt = createLearningRuntime(io.dep) as any;
  void rt.queue();
  await sleep(200);
  const c = rt.cancel();
  releaseTurn();
  await sleep(500);
  const st = rt.status();
  check("D5 运行中取消=阶段末停止", c.phase === "running" && st.running === false && st.message.includes("停止"), `msg=${st.message}`);
}

// ⑫⑭ F6 内置技能保护 + E5/F3 通用名拒收（走全链：提案中带内置 id+通用名笔记）
{
  const io = makeFakeIo({ runTurnImpl: async () => ({ ok: true, text: markedOutput(proposalJson({ builtinSkillId: "juscite-builtin-timeline-generation", badNoteName: "迭代记录1.md", allRejected: true })) }) });
  const rt = createLearningRuntime(io.dep) as any;
  await rt.queue();
  let st = rt.status();
  for (let i = 0; i < 40 && st.running; i++) { await sleep(150); st = rt.status(); }
  const runId = readdirSync(join(io.root, "runs"))[0]!;
  const manifest = JSON.parse(readFileSync(join(io.root, "runs", runId, "manifest.json"), "utf-8"));
  const rejected = manifest.modelResult.rejected as Array<{ kind: string; reason: string }>;
  check("F6 内置技能整批剔除+后台不覆盖理由", rejected.some((r) => r.kind === "skill" && r.reason.includes("后台不会覆盖")), rejected.map((r) => r.reason).join("|").slice(0, 60));
  check("F3/E5 通用名笔记拒收", rejected.some((r) => r.kind === "knowledgeNote" && (r.reason.includes("通用名") || r.reason.includes("主题"))), "");
  check("G7 全拒也发 completed 记录", manifest.summary.status === "completed" && manifest.summary.counts.rejected >= 2 && manifest.summary.canRollback === false, `rej=${manifest.summary.counts.rejected}`);
  check("G7 零变更报告双态标题", readFileSync(join(io.root, "runs", runId, "REPORT.md"), "utf-8").includes("本轮学习检查已完成"), "");
}

// ⑪ G5 发布中断逆序撤销
{
  const io = makeFakeIo();
  const rt = createLearningRuntime(io.dep) as any;
  // 知识写失败：把 kbRoot 换成文件制造 ENOTDIR
  const originalKbRoot = io.kbRoot;
  rmSync(originalKbRoot, { recursive: true, force: true });
  writeFileSync(originalKbRoot, "不是目录", "utf-8");
  await rt.queue();
  await sleep(500);
  let st = rt.status();
  for (let i = 0; i < 40 && st.running; i++) { await sleep(150); st = rt.status(); }
  const runId = readdirSync(join(io.root, "runs"))[0]!;
  const manifest = JSON.parse(readFileSync(join(io.root, "runs", runId, "manifest.json"), "utf-8"));
  check("G5 发布中断→失败记录", manifest.summary.status === "failed" && manifest.summary.canRollback === false, `status=${manifest.summary.status}`);
  check("G5 逆序撤销：记忆回滚+技能清除", (JSON.parse(readFileSync(join(io.root, "memories.json"), "utf-8")) as unknown[]).length === 0 && !existsSync(join(io.skillsRoot, "evidence-checklist")), "");
}

// ⑬ A6 线程面失败保守忙
{
  const io = makeFakeIo();
  io.dep.listThreads = () => { throw new Error("线程面炸了"); };
  const rt = createLearningRuntime(io.dep) as any;
  await rt.tick({ manual: false });
  const st = rt.status();
  check("A6 线程面失败不进轮且不忙门误判", st.running === false && st.message.includes("等待手头任务"), st.message);
}

// ⑭ 补齐件：C2 工具摘要/失败 tool_result + C4 knowledge_* 排除 + C3 pdf/附件去重
{
  const io = makeFakeIo();
  // 合成未压缩 PDF（拉丁文本流）+ .doc（应跳过）+ 附件 dup.txt；产物 gen.md / kb.md
  const pdfBody = "BT /F1 12 Tf (Synthetic PDF body line) Tj [(second) -250 (line)] TJ ET";
  const fakePdf = "%PDF-1.4\n1 0 obj\n<< /Length " + pdfBody.length + " >>\nstream\n" + pdfBody + "\nendstream\nendobj\n%%EOF\n";
  writeFileSync(join(io.matsDir, "re18-gap.pdf"), fakePdf, "utf-8");
  writeFileSync(join(io.matsDir, "skip.doc"), "OLE-old-format", "utf-8");
  writeFileSync(join(io.matsDir, "dup.txt"), "附件直采正文（按线程去重收集）。", "utf-8");
  mkdirSync(join(io.wsDir, "out"), { recursive: true });
  writeFileSync(join(io.wsDir, "out", "gen.md"), "# 产物正文\n文件变更产物内容，合成材料。", "utf-8");
  writeFileSync(join(io.wsDir, "out", "kb.md"), "# 知识工具产物\n不应入语料。", "utf-8");
  io.dep.threadRows = (id: string) => id === THREAD_A
    ? [
        { kind: "userInput", state: "complete", text: "帮我把这份材料整理成要点", attachments: ["re18-gap.pdf", "skip.doc", "dup.txt"] },
        { kind: "assistantText", state: "failed", text: "该回合因工具故障中断，这是失败前的部分文本。" },
        { kind: "assistantText", state: "complete", text: "好的，我先列证据清单。",
          toolCalls: [
            { name: "file_write", input: "写入 gen.md", output: JSON.stringify({ output_path: join(io.wsDir, "out", "gen.md") }) },
            { name: "knowledge_search", input: "知识检索", output: JSON.stringify({ output_path: join(io.wsDir, "out", "kb.md") }) },
            { name: "case_search", input: "案例检索", error: "case backend boom" },
            { name: "web_fetch", input: "长输出", output: "长".repeat(1200) },
          ] },
      ]
    : [{ kind: "userInput", state: "complete", text: "写文书前一般怎么做比较好？我想固定一个流程。" }];
  const rt = createLearningRuntime(io.dep) as any;
  await rt.queue();
  let st = rt.status();
  for (let i = 0; i < 60 && st.running; i++) { await sleep(150); st = rt.status(); }
  const runId = readdirSync(join(io.root, "runs"))[0]!;
  const inputMd = readFileSync(join(io.root, "runs", runId, "INPUT.md"), "utf-8");
  // C3：pdf 抽取入语料 + 附件按线程直采 + .doc 如实跳过
  check("C3 pdf 文本抽取入语料", inputMd.includes("Synthetic PDF body line") && inputMd.includes("second"), "");
  check("C3 attachmentIds 按线程直采", inputMd.includes("附件直采正文"), "");
  check("C3 .doc 老格式如实跳过", !inputMd.includes("OLE-old-format"), "");
  const manifest = JSON.parse(readFileSync(join(io.root, "runs", runId, "manifest.json"), "utf-8"));
  const names = manifest.sourceHashes && Object.keys(manifest.sourceHashes).filter((k: string) => k.startsWith("meta:upload:"));
  check("C3 附件去重不计双份（upload 基=2：pdf+dup）", names.length === 2, names.join(","));
  // C2：工具摘要 ≤500、失败 tool_result、失败回合
  const toolLine = (inputMd.split("\n").find((l) => l.startsWith("[工具] file_write")) ?? "");
  check("C2 工具摘要行在位", toolLine.startsWith("[工具] file_write："), toolLine.slice(0, 40));
  check("C2 摘要截 500", [...toolLine].length <= 500 + "[工具] file_write：".length, `len=${[...toolLine].length}`);
  check("C2 失败 tool_result 入语料", inputMd.includes("[工具失败] case_search：case backend boom"), "");
  check("C2 失败回合文本入语料", inputMd.includes("[失败回合] 该回合因工具故障中断"), "");
  // C4：knowledge_* 产物排除；普通产物照采
  check("C4 knowledge_* 工具产物排除（正文不入语料；摘要行提及路径属 C2 过程记录，合法）", !inputMd.includes("不应入语料"), "");
  check("C4 普通产物照采", inputMd.includes("gen.md"), "");
}

// ⑮ 补齐件：D4 轮内瞬时断连容错 ≤5（前两次 fetch failed 第三次成→完成）
{
  let calls = 0;
  const io = makeFakeIo({ runTurnImpl: async () => {
    calls++;
    if (calls <= 2) return { ok: false, error: "fetch failed: ECONNRESET" };
    return { ok: true, text: markedOutput(proposalJson()) };
  } });
  const rt = createLearningRuntime(io.dep) as any;
  await rt.queue();
  let st = rt.status();
  for (let i = 0; i < 80 && st.running; i++) { await sleep(200); st = rt.status(); }
  check("D4 瞬时断连 ≤5 次重试后完成", st.status === "completed" && calls === 3, `calls=${calls} status=${st.status}`);
}

// ⑯ 补齐件：D4 超限（1+5=6 次全失败）→ K1 requeue，不写失败记录
{
  let calls = 0;
  const io = makeFakeIo({ runTurnImpl: async () => { calls++; return { ok: false, error: "fetch failed: ECONNRESET" }; } });
  const rt = createLearningRuntime(io.dep) as any;
  await rt.queue();
  await sleep(9500);
  let st = rt.status();
  for (let i = 0; i < 40 && st.running; i++) { await sleep(200); st = rt.status(); }
  const state = JSON.parse(readFileSync(join(io.root, "state.json"), "utf-8"));
  check("D4 超限 6 次后落 K1 requeue", calls === 6 && state.pendingRunId !== null && state.lastRetryAt === null,
    `calls=${calls} pending=${state.pendingRunId}`);
  check("D4 超限消息=断连保留", st.message.includes("连接短暂中断"), st.message);
}

// ═══ B 段：隔离桥 ═══
const BRIDGE_LEARN_ROOT = join(SCRATCH, "bridge-learning");
const BRIDGE_KB = join(SCRATCH, "bridge-kb");
const BRIDGE_WS = "D:\\mock\\lvyin-demo"; // 桥 WORKSPACE.path（材料通道落点）
mkdirSync(BRIDGE_LEARN_ROOT, { recursive: true });
mkdirSync(BRIDGE_KB, { recursive: true });
mkdirSync(join(BRIDGE_WS, "materials"), { recursive: true });
writeFileSync(join(BRIDGE_KB, "合成检索资料.md"), "# 合成检索资料\n\n举证责任分配的通常做法与例外，全部为合成材料，用于知识源采集与检索回流验证。".repeat(4), "utf-8");
writeFileSync(join(BRIDGE_WS, "materials", "re18-synth-材料.txt"), "客户偏好：行文简洁，先结论后理由（合成材料）。", "utf-8");

// mock oc28：学习提示→合成提案 JSON；其他提示→普通回复
const mockSessions = new Map<string, Array<Record<string, unknown>>>();
let mockSeq = 0;
const learningPrompts: string[] = [];
const mockServer = createServer((req, res) => {
  const url = req.url ?? "";
  if (req.method === "POST" && url === "/api/session") { res.writeHead(200); res.end("{}"); return; }
  const pm = req.method === "POST" && url.match(/^\/api\/session\/([^/]+)\/prompt$/);
  if (pm) {
    let body = "";
    req.on("data", (c: Buffer) => { body += String(c); });
    req.on("end", () => {
      const sid = decodeURIComponent(pm[1]);
      const parsed = JSON.parse(body || "{}") as { id?: string; text?: string };
      const promptText = parsed.text ?? "";
      const list = mockSessions.get(sid) ?? [];
      list.push({ id: parsed.id ?? "u" + mockSeq, type: "user", time: { created: Date.now() }, content: [{ type: "text", text: promptText }] });
      const isLearning = promptText.includes(OUTPUT_MARK_BEGIN);
      if (isLearning) learningPrompts.push(promptText);
      const reply = isLearning
        ? markedOutput(proposalJson({ skill: true }))
        : "收到（合成回复，用于普通对话轮注入面）。";
      const mid = "a" + (mockSeq++);
      setTimeout(() => {
        const l2 = mockSessions.get(sid) ?? [];
        l2.push({ id: mid, type: "assistant", time: { created: Date.now(), completed: Date.now() }, content: [{ type: "text", text: reply }] });
        mockSessions.set(sid, l2);
      }, 250);
      mockSessions.set(sid, list);
      res.writeHead(200); res.end("{}");
    });
    return;
  }
  const lm = req.method === "GET" && url.match(/^\/api\/session\/([^/]+)\/message$/);
  if (lm) { res.writeHead(200, { "content-type": "application/json" }); res.end(JSON.stringify({ data: mockSessions.get(decodeURIComponent(lm[1])) ?? [] })); return; }
  res.writeHead(404); res.end("{}");
});
await new Promise<void>((resolve) => mockServer.listen(0, "127.0.0.1", () => resolve()));
const mockUrl = "http://127.0.0.1:" + (mockServer.address() as AddressInfo).port;

const DB = join(process.env.APPDATA ?? "", "Juscite", "bridge", `bridge-${PORT}.db`);
const bridgeLog = openSync(join(REPO_ROOT, ".local", `re18-synth-bridge-${PORT}.log`), "a");
function spawnBridge(extraEnv: Record<string, string> = {}) {
  const env = { ...process.env, BRIDGE_PORT: String(PORT), BRIDGE_OC28_SSE: "0", BRIDGE_OC28_URL: mockUrl, BRIDGE_OC28_PASSWORD: "synthetic",
    BRIDGE_LEARNING_ROOT: BRIDGE_LEARN_ROOT, BRIDGE_KB_ROOT: BRIDGE_KB, BRIDGE_LEARNING_POLL_MS: "3600000", ...extraEnv };
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
  while (Date.now() < deadline) { if (await probe()) return true; await sleep(400); }
  return false;
}
async function killBridge(pid: number) {
  if (!pid) return;
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`], { encoding: "utf-8", timeout: 20000 });
  if (!String(r.stdout ?? "").includes("bridge_host.mjs")) throw new Error(`拒绝杀 pid=${pid}：不是桥`);
  spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline && (await probe())) await sleep(300);
}
// 端口清场（残留桥必须换新——mock oc28 已随旧进程失效）
{
  if (await probe()) {
    const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
    const pids = new Set<string>();
    for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
      if (Number(m[1]) === PORT) pids.add(m[2]!);
    }
    for (const pid of pids) {
      const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
        `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`], { encoding: "utf-8", timeout: 20000 });
      if (String(q.stdout ?? "").includes("bridge_host.mjs")) { spawnSync("taskkill", ["/PID", pid, "/F", "/T"], { timeout: 15000 }); console.log("[re18-synth] 清场残留桥 pid=" + pid); }
    }
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline && (await probe())) await sleep(300);
  }
  for (const suffix of ["", "-wal", "-shm"]) { try { rmSync(DB + suffix, { force: true }); } catch { /* 留给下轮 */ } }
}
// 先起一次桥让迁移建表，杀掉后播种（空库直接插会 no such table）
// 迁移 spawn：一次性学习根+死 oc28——boot tick 不产生真轮、不碰共享学习根与技能根
let bridgePid = spawnBridge({ BRIDGE_LEARNING_ROOT: join(SCRATCH, "mig-learning-root"), BRIDGE_OC28_URL: "http://127.0.0.1:9" });
if (!(await waitProbe(40000))) { console.log("LEARN_SYNTH_FAIL"); console.error("桥 40s 不可探"); process.exit(1); }
await killBridge(bridgePid);
bridgePid = 0;
// 预置库行：两个合成对话线程（含 RAG 标记正文+打招呼行+assistant 过程行）
{
  mkdirSync(join(BRIDGE_LEARN_ROOT), { recursive: true });
  // Windows 杀桥→开库竞态：taskkill /F 后句柄/杀软扫描持锁有延迟，偶发 SQLITE_IOERR(1546)/CANTOPEN；
  // 按规格 K3 同款思路整体重试（8 次线性退避）。失败时必在插行前（prepare 阶段）或首插前，重做不重复；
  // 只稳测试脚手架，不改产品面。
  let db: DatabaseSync | null = null;
  let seeded = false;
  for (let attempt = 0; attempt < 8 && !seeded; attempt++) {
    try {
      db = db ?? new DatabaseSync(DB);
      const WS = BRIDGE_WS;
      const insS = db.prepare(`INSERT INTO sessions (workspace_key, session_id, oc28_id, title, project_id, workspace_path, last_outcome, phase, seq, row_seq, busy, last_command_id, meta_json, created_at, updated_at, deleted)
        VALUES (?, ?, NULL, ?, NULL, ?, 'completed', 'completedSuccess', 3, 3, 0, NULL, '{}', ?, ?, 0)`);
      const insR = db.prepare(`INSERT INTO session_rows (workspace_key, session_id, row_seq, kind, state, text, source_command_id, row_json)
        VALUES (?, ?, ?, ?, 'complete', ?, NULL, ?)`);
      const now0 = Date.now();
      insS.run(WS, THREAD_A, "合成线程甲：合同起草习惯", WS, now0 - 7200_000, now0 - 3600_000);
      insR.run(WS, THREAD_A, 1, "userInput", "帮我看看这个合同怎么写\n## 所内资料\n[来源1] 合成条文", JSON.stringify({ kind: "userInput", state: "complete", text: "帮我看看这个合同怎么写\n## 所内资料\n[来源1] 合成条文" }));
      insR.run(WS, THREAD_A, 2, "userInput", "在吗", JSON.stringify({ kind: "userInput", state: "complete", text: "在吗" }));
      insR.run(WS, THREAD_A, 3, "assistantText", "好的，我们先列证据清单。", JSON.stringify({ kind: "assistantText", state: "complete", text: "好的，我们先列证据清单。" }));
      insS.run(WS, THREAD_B, "合成线程乙：流程固定", WS, now0 - 7200_000, now0 - 1800_000);
      insR.run(WS, THREAD_B, 1, "userInput", "写文书前一般怎么做比较好？我想固定一个流程。", JSON.stringify({ kind: "userInput", state: "complete", text: "写文书前一般怎么做比较好？我想固定一个流程。" }));
      seeded = true;
    } catch (e) {
      try { db?.close(); } catch { /* 忽略关闭失败 */ }
      db = null;
      console.error(`[re18-synth] 预置库第 ${attempt + 1} 次失败：${String((e as Error).message ?? e)}`);
      if (attempt === 7) throw e;
      await sleep(1000 * (attempt + 1));
    }
  }
  db.close();
}
bridgePid = spawnBridge();
if (!(await waitProbe(40000))) { console.log("LEARN_SYNTH_FAIL"); console.error("播种后桥 40s 不可探"); process.exit(1); }

let call: <T>(m: string, a?: unknown) => Promise<T> = async () => { throw new Error("未连接"); };
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
      const client = new ChannelClient(new SocketProtocol(isocket as never));
      const ch = client.getChannel("zcode-agent");
      call = async <T,>(m: string, a?: unknown) => ch.call<T>(m, a === undefined ? [] : [a]);
      call("helloConversationV4").then(() => resolve()).catch(reject);
    });
    ws.on("error", reject);
  });
}
await connect();

// ⑮ status 载荷 + A1 默认开 + A2 启动即跑（boot tick 等它收口，产物供 ⑯ 断言）
{
  const st = await call<Record<string, unknown>>("learningStatus", {});
  const keys = ["enabled", "eligibleToday", "queued", "running", "status", "message", "lastSuccessfulAt", "lastCheckedAt", "nextEligibleAt", "baselineComplete", "baselineProgress", "pendingSourceCount"];
  check("B2 status 全载荷键面", keys.every((k) => k in st), Object.keys(st).join(","));
  check("A1 默认开启（显式 false 才关）", st.enabled === true, `enabled=${st.enabled}`);
  let st2: any = st;
  const bootDeadline = Date.now() + 90000;
  while (Date.now() < bootDeadline && (st2.running || st2.status === "running" || st2.status === "waiting" || st2.queued)) {
    await sleep(800);
    st2 = await call<any>("learningStatus", {});
    if (st2.status === "completed" || st2.status === "failed") break;
  }
  check("A2 启动即 sync 并跑完 boot 轮", st2.status === "completed" || st2.status === "failed", `status=${st2.status}`);
}

// ⑯ boot 轮产物对拍（全链数据面）
{
  check("D1 学习线程 [学习迭代] 前缀+纯文本分析提示", learningPrompts.length >= 1 && learningPrompts[0]!.includes("不要调用任何工具") && learningPrompts[0]!.includes("JSON 对象") && learningPrompts[0]!.includes("只修正 JSON 语法") === false, `n=${learningPrompts.length}`);
  const recs = await call<Array<Record<string, unknown>>>("learningList", {});
  check("H9 记录列表 1 条 completed", Array.isArray((recs as any).records) && (recs as any).records.length === 1 && (recs as any).records[0].status === "completed", JSON.stringify(recs).slice(0, 80));
  const recId = String((recs as any).records[0].id);
  const detail = await call<{ summary: any; reportMarkdown: string }>("learningGet", { id: recId });
  check("H10 详情含报告原文+displayName", detail.summary.id === recId && detail.reportMarkdown.includes("## 这次学到了什么") && String(detail.summary.displayName).includes(" · "), "");
  // 产物落盘面
  const kbNote = join(BRIDGE_KB, "沉淀笔记", "资料摘要", "举证责任分配实务要点.md");
  check("G4 知识笔记落盘+学习标记", existsSync(kbNote) && readFileSync(kbNote, "utf-8").includes("juscite-learning-artifact"), "");
  const memFile = join(BRIDGE_LEARN_ROOT, "memories.json");
  check("G1 记忆落盘 Juscite 分区内", existsSync(memFile) && (JSON.parse(readFileSync(memFile, "utf-8")) as any[]).length === 1, "");
  const skillsRoot = join(process.env.APPDATA ?? "", "Juscite", "bridge", "skills");
  check("G3 技能写用户技能根", existsSync(join(skillsRoot, "evidence-checklist", "SKILL.md")), "");
  check("C1 桥面语料 RAG 剥离+打招呼过滤", learningPrompts[0]!.includes("帮我看看这个合同怎么写") && !learningPrompts[0]!.includes("在吗") && !learningPrompts[0]!.includes("所内资料"), "");
  // ⑰ A3 手动不破日额度
  const q2 = await call<{ ok: boolean; reason?: string; message?: string }>("learningQueue", {});
  check("A3 手动也不破今日额度", q2.ok === false && q2.reason === "done-today" && String(q2.message).includes("明天"), JSON.stringify(q2).slice(0, 80));
  // ⑱ H8 回滚
  const rb = await call<{ ok: boolean; summary: any }>("learningRollback", { id: recId });
  check("H8 桥面回滚 rolled_back", rb.ok === true && rb.summary.status === "rolled_back" && rb.summary.canRollback === false, JSON.stringify(rb.summary ?? {}).slice(0, 80));
  check("H8 回滚后知识/记忆/技能撤销", !existsSync(kbNote) && (JSON.parse(readFileSync(memFile, "utf-8")) as any[]).length === 0 && !existsSync(join(skillsRoot, "evidence-checklist")), "");
  const detail2 = await call<{ summary: any; reportMarkdown: string }>("learningGet", { id: recId });
  check("H8 记录态回读含回滚节", detail2.summary.status === "rolled_back" && detail2.reportMarkdown.includes("## 回滚"), "");
  // ⑲ H10 id 校验
  let idErr = "";
  try { await call("learningGet", { id: "../evil" }); } catch (e) { idErr = String((e as Error).message ?? e); }
  check("H10 非法 id 拒绝", idErr.includes("非法记录 id"), idErr.slice(0, 50));
}

await killBridge(bridgePid);

// ⑳ J15 未初始化兜底（BRIDGE_LEARNING_ROOT 指向一个已存在文件 → mkdir 失败 → 运行时 null）
{
  const badRoot = join(SCRATCH, "not-a-dir");
  writeFileSync(badRoot, "x", "utf-8");
  bridgePid = spawnBridge({ BRIDGE_LEARNING_ROOT: badRoot });
  if (!(await waitProbe(40000))) { console.log("LEARN_SYNTH_FAIL"); console.error("兜底桥 40s 不可探"); process.exit(1); }
  await connect();
  const st = await call<Record<string, unknown>>("learningStatus", {});
  check("J15 status 未初始化兜底 disabled 全零", st.enabled === false && st.status === "disabled" && st.lastSuccessfulAt === null && st.pendingSourceCount === 0, JSON.stringify(st).slice(0, 80));
  const list = await call<{ ok?: boolean; error?: string }>("learningList", {});
  check("J15 其余命令兜底 ok:false", list.ok === false && String(list.error).includes("尚未初始化"), JSON.stringify(list).slice(0, 60));
  await killBridge(bridgePid);
}

// 清场：合成材料不留痕
try { rmSync(join(BRIDGE_WS, "materials", "re18-synth-材料.txt"), { force: true }); } catch { /* 留给下轮 */ }
try { rmSync(SCRATCH, { recursive: true, force: true }); } catch { /* Windows 句柄延迟，留给下轮 */ }

const total = fails();
console.log(`[re18-synth] checks=${results.length} fail=${total}`);
console.log(total === 0 ? "LEARN_SYNTH_PASS" : "LEARN_SYNTH_FAIL");
process.exit(total === 0 ? 0 : 1);
