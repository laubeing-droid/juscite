// 【施工单-10 单元二】结构化文件写入防御（YAML/JSON 配置面）桥面合成对拍。
// 面=agent/技能写 YAML 的真实落盘路径：tools/bridge/learning_runtime.mjs 两处
// （技能配置 SKILL.md frontmatter 重建 + 知识笔记 frontmatter）——经 createLearningRuntime
// 全 IO 注入假件（learning_synthetic A 段同法：临时根、零端口、零 %APPDATA%、零真模型零 oc28，
// oc28:43127/:3030 不动）。验收断言（施工单原文口径）：合成 payload（冒号键/多行/锚点 &a·*a/
// 标签 !!python）round-trip 后=纯标量、结构键集合零变化；键名面 typed 拒。
// 独立证伪用标准 YAML 解析器（yaml 包，与上游宿主同语）读回落盘字节，不是只被自家读回器自证。
// 末行 CONFIGWRITE_SYNTH_PASS / CONFIGWRITE_SYNTH_FAIL。
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { parse as parseYaml } from "yaml";
import { createLearningRuntime } from "./learning_runtime.mjs";
import { describeInstalledSkill } from "./skills_service.mjs";
import { OUTPUT_MARK_BEGIN, OUTPUT_MARK_END } from "../../packages/juscite-legal/src/kernel/learningModel.ts";
import {
  buildFrontmatterBlock, roundTripCheckFrontmatter, writeFrontmatterChecked, ConfigWriteError,
} from "../../packages/juscite-legal/src/kernel/configWriteModel.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const SCRATCH = join(REPO_ROOT, ".local", `cfgwrite-scratch-${Date.now()}`);
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`[configwrite-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const fails = () => results.filter((r) => !r.ok).length;

// ── 合成 payload（全部合成材料；覆盖施工单指定四族+引号/反斜杠/控制字符）──
const PAYLOAD_DESC = '先列证据清单: 再动笔 &a 锚点 *a 别名 !!python/object/apply:os.system 含"双引号"与\\反斜杠';
const PAYLOAD_TITLE = "标题前缀: 想当第二个键 &a *a !!python 多行\n第二行";
const PAYLOAD_SUMMARY = "摘要: 带冒号与锚点 &b *b !!str 的多行\n摘要第二行";
const PAYLOAD_MEMORY = "记忆内容带\"引号\"与\\反斜杠: 第一行\n第二行 *a !!python";
const NOTE_BODY = "综合多个线程的做法整理的合成笔记正文，用于结构化写入防御对拍；内容全部为合成材料，不含任何真实案件信息，长度满足下限要求。".repeat(2);
const flatten120 = (s) => [...String(s ?? "").replace(/\r?\n/g, " ")].slice(0, 120).join("");
const EXPECTED_DESC = flatten120(PAYLOAD_DESC);
const EXPECTED_TITLE = String(PAYLOAD_TITLE).replace(/\r?\n/g, " ");
const EXPECTED_SUMMARY = String(PAYLOAD_SUMMARY).replace(/\r?\n/g, " ");

const THREAD_A = "ses_seed_0001";
const THREAD_B = "ses_seed_0002";
function genTests() {
  const base = [
    { category: "should-trigger", input: "帮我起草起诉状", passed: true },
    { category: "should-not-trigger", input: "今天天气如何", passed: true },
    { category: "ambiguous", input: "整理一下这个", passed: true },
    { category: "sibling-confusion", input: "帮我审合同", passed: true },
  ];
  return [...base, ...base.map((t) => ({ ...t, input: t.input + "（变体）" }))];
}
function proposalJson(opts) {
  const bad = opts?.badSkillId;
  return JSON.stringify({
    title: "写作习惯与注入防御要点",
    summary: "这轮整理了一条带注入载荷的合成提案，用于配置写入防御对拍。",
    reportMarkdown: "## 这次学到了什么\n- 结构化写入防御对拍\n",
    memories: [{ action: "create", category: "workflow", content: PAYLOAD_MEMORY, confidence: 0.9, evidence: [{ sourceKey: `thread:${THREAD_A}`, sourceKind: "thread" }, { sourceKey: `thread:${THREAD_B}`, sourceKind: "thread" }], explicitCorrection: false }],
    skills: [bad
      ? { id: bad, name: "冒名", description: "这是一段足够长的中文描述文本", skillMarkdown: "---\nname: x\n---\n正文", evidence: [{ sourceKey: `thread:${THREAD_A}`, sourceKind: "thread" }, { sourceKey: `thread:${THREAD_B}`, sourceKind: "thread" }], tests: genTests() }
      : { id: "payload-skill", name: "载荷技能", description: PAYLOAD_DESC, skillMarkdown: "---\nname: payload-skill\n---\n# 载荷技能\n固定做法正文，含 --- 围栏行与 name: 伪装行用于正文面自证（正文在 frontmatter 闭合之后，不具结构语义）。", evidence: [{ sourceKey: `thread:${THREAD_A}`, sourceKind: "thread" }, { sourceKey: `thread:${THREAD_B}`, sourceKind: "knowledge" }], tests: genTests() }],
    knowledgeNotes: [{ action: "create", path: "注入防御载荷笔记.md", title: PAYLOAD_TITLE, summary: PAYLOAD_SUMMARY, content: NOTE_BODY, evidence: [{ sourceKey: `thread:${THREAD_A}`, sourceKind: "thread" }] }],
    rejected: [],
  });
}

// ── A 段同法：全 IO 注入假件（临时根隔离，不碰 %APPDATA%）──
function makeFakeIo(runTurnImpl) {
  const root = join(SCRATCH, "rt-" + Math.random().toString(36).slice(2, 8));
  mkdirSync(root, { recursive: true });
  const kbRoot = join(root, "kb");
  const skillsRoot = join(root, "skills");
  for (const d of [kbRoot, skillsRoot]) mkdirSync(d, { recursive: true });
  const dep = {
    root, kbRootDir: kbRoot, skillsRootDir: skillsRoot,
    loadSettings: () => ({ enabled: true, idleMinutes: 15, keepRunningInTray: true }),
    listThreads: () => [
      { id: THREAD_A, title: "合成线程甲", workspaceKey: "ws://main", phase: "completedSuccess", updatedAt: 1000 },
      { id: THREAD_B, title: "合成线程乙", workspaceKey: "ws://main", phase: "completedSuccess", updatedAt: 2000 },
    ],
    threadRows: (id) => id === THREAD_A
      ? [{ kind: "userInput", state: "complete", text: "帮我把这份材料整理成要点，注意结构化写入的安全边界。", createdAt: 1 }]
      : [{ kind: "userInput", state: "complete", text: "写文书前一般怎么做比较好？", createdAt: 4 }],
    workspacePathOf: () => join(root, "ws"),
    materialsList: () => [],
    readMaterialText: () => "",
    kbWalk: () => [],
    kbReadText: () => null,
    kbRoot: () => kbRoot,
    skillsRoot: () => skillsRoot,
    kbSync: async () => {},
    skillsList: () => { try { return readdirSync(skillsRoot).map((id) => ({ id, dir: join(skillsRoot, id), md: existsSync(join(skillsRoot, id, "SKILL.md")) ? readFileSync(join(skillsRoot, id, "SKILL.md"), "utf-8") : "" })); } catch { return []; } },
    protectedSkillIds: () => ["juscite-builtin-timeline-generation"],
    readDocxText: null,
    runTurn: runTurnImpl,
    auditWrite: () => {},
    pollMs: 3_600_000,
    log: () => {},
    now: () => Date.now(),
  };
  return dep;
}
async function runToCompletion(rt) {
  await rt.queue();
  let st = rt.status();
  for (let i = 0; i < 60 && st.running; i++) { await sleep(150); st = rt.status(); }
  return st;
}
const markedOutput = (json) => `分析如下：\n${OUTPUT_MARK_BEGIN}\n${json}\n${OUTPUT_MARK_END}\n以上。`;

// ── 正例：全链发布（技能配置+知识笔记+记忆三面落盘）──
{
  const dep = makeFakeIo(async () => ({ ok: true, text: markedOutput(proposalJson()) }));
  const rt = createLearningRuntime(dep);
  const st = await runToCompletion(rt);
  check("全链发布完成", st.status === "completed", `status=${st.status}`);
  const runId = readdirSync(join(dep.root, "runs"))[0];

  // ① 技能配置面：SKILL.md frontmatter 双引号化纯标量
  const skillMdPath = join(dep.skillsRootDir, "payload-skill", "SKILL.md");
  check("技能配置落盘", existsSync(skillMdPath) && existsSync(join(dep.skillsRootDir, "payload-skill", "test-prompts.json")) && existsSync(join(dep.skillsRootDir, "payload-skill", "learning.json")), "");
  const skillMd = existsSync(skillMdPath) ? readFileSync(skillMdPath, "utf-8") : "";
  const closeIdx = skillMd.indexOf("\n---", 4);
  const skillFm = closeIdx > 0 ? skillMd.slice(0, closeIdx + 4) : "";
  check("frontmatter 逐字段双引号化（含 name=id）", skillMd.startsWith('---\nname: "payload-skill"\ndescription: "'), skillMd.split("\n").slice(0, 3).join("⏎").slice(0, 90));
  let byYaml = null;
  try { byYaml = parseYaml(skillFm.replace(/\n---$/u, "")); } catch { byYaml = null; }
  check("标准 YAML 解析器读回：键集合恰 [name,description] 零变化", byYaml !== null && Object.keys(byYaml).sort().join(",") === "description,name", byYaml === null ? "yaml 解析失败" : Object.keys(byYaml).join(","));
  check("两值均为 string 纯标量（非映射/别名/标签）", byYaml !== null && typeof byYaml.name === "string" && typeof byYaml.description === "string", "");
  check("description round-trip 逐字相等（flatten+120 上限后）", byYaml !== null && byYaml.description === EXPECTED_DESC, JSON.stringify(byYaml?.description ?? "").slice(0, 60));
  let rtOwn = null;
  try { rtOwn = roundTripCheckFrontmatter(skillFm, ["name", "description"]); } catch (e) { rtOwn = e; }
  check("内核 round-trip 校验过（自家严格读回=回执面）", rtOwn !== null && !(rtOwn instanceof Error) && rtOwn.description === EXPECTED_DESC, rtOwn instanceof Error ? rtOwn.message : "");
  check("正文伪装键值行原样保留在 frontmatter 闭合之后（内容保真=只可能是数据）", skillMd.indexOf("name: 伪装行") > closeIdx, "");

  // ② skills_service 读回通道忠实（describeInstalledSkill→parseFrontmatter unescape）
  const desc = describeInstalledSkill(join(dep.skillsRootDir, "payload-skill")).description;
  check("skills_service 读回 description 逐字相等（转义还原）", desc === EXPECTED_DESC, JSON.stringify(desc ?? "").slice(0, 60));

  // ③ 知识笔记面：frontmatter 五键闭集
  const notePath = join(dep.kbRootDir, "沉淀笔记", "资料摘要", "注入防御载荷笔记.md");
  check("知识笔记落盘", existsSync(notePath), "");
  const note = existsSync(notePath) ? readFileSync(notePath, "utf-8") : "";
  const noteClose = note.indexOf("\n---", 4);
  const noteFm = noteClose > 0 ? note.slice(0, noteClose + 4) : "";
  let noteYaml = null;
  try { noteYaml = parseYaml(noteFm.replace(/\n---$/u, "")); } catch { noteYaml = null; }
  check("笔记键集合恰五键零变化（title/summary/generated_by/source_iteration/updated_at）",
    noteYaml !== null && Object.keys(noteYaml).sort().join(",") === "generated_by,source_iteration,summary,title,updated_at",
    noteYaml === null ? "yaml 解析失败" : Object.keys(noteYaml).join(","));
  check("title/summary 纯标量且逐字相等（含冒号/锚点/标签/多行压平）",
    noteYaml !== null && typeof noteYaml.title === "string" && noteYaml.title === EXPECTED_TITLE && noteYaml.summary === EXPECTED_SUMMARY,
    JSON.stringify(noteYaml?.title ?? "").slice(0, 50));
  check("generated_by/source_iteration/updated_at 均为引号化标量", noteYaml !== null && noteYaml.generated_by === "learning-iteration" && noteYaml.source_iteration === runId && /^\d{4}-\d{2}-\d{2}T/.test(String(noteYaml.updated_at)), "");
  check("笔记正文与学习标记在位（frontmatter 闭合后只可能是数据）", note.includes("juscite-learning-artifact") && note.includes(NOTE_BODY.slice(0, 20)), "");

  // ④ 更新清单/JSON 配置面：manifest 与 memories JSON 读回（JSON.stringify 天然引号化）
  const manifest = JSON.parse(readFileSync(join(dep.root, "runs", runId, "manifest.json"), "utf-8"));
  check("更新清单 manifest 读回键在位", manifest.summary.counts.memoriesCreated === 1 && manifest.summary.counts.skillsCreated === 1 && manifest.summary.counts.knowledgeNotesCreated === 1, "");
  const mems = JSON.parse(readFileSync(join(dep.root, "memories.json"), "utf-8"));
  check("JSON 配置面：记忆 payload 字符串逐字相等（零结构注入）", Array.isArray(mems) && mems.length === 1 && mems[0].content === PAYLOAD_MEMORY, "");

  // ⑤ 负例·上游闭集：id 含冒号的技能提案在 F2 门即拒（键/标识面先于写入面）
  {
    const dep2 = makeFakeIo(async () => ({ ok: true, text: markedOutput(proposalJson({ badSkillId: "bad:id &a" })) }));
    const rt2 = createLearningRuntime(dep2);
    const st2 = await runToCompletion(rt2);
    const runId2 = readdirSync(join(dep2.root, "runs"))[0];
    const m2 = JSON.parse(readFileSync(join(dep2.root, "runs", runId2, "manifest.json"), "utf-8"));
    const rej = m2.modelResult.rejected ?? [];
    check("冒号/锚点 id 提案被 F2 闭集拒（不落盘）", st2.status === "completed" && rej.some((r) => r.kind === "skill" && String(r.reason).includes("id 必须是小写英文")) && !existsSync(join(dep2.skillsRootDir, "bad:id &a")), (rej.find((r) => r.kind === "skill") ?? {}).reason ?? "");
  }

  // ⑥ 负例·内核闸：键名/重复键/键集合漂移 typed 拒（直接驱内核，不落盘）
  const throwsCode = (fn, code) => { try { fn(); return null; } catch (e) { return e instanceof ConfigWriteError ? e.message : `非typed:${String(e?.message ?? e)}`; } };
  check("冒号键/空格键/__proto__ 键 typed 拒 cfgwrite_key_invalid",
    throwsCode(() => buildFrontmatterBlock([{ key: "evil: &a", value: "x" }]), "cfgwrite_key_invalid") === "cfgwrite_key_invalid"
    && throwsCode(() => buildFrontmatterBlock([{ key: "__proto__", value: "x" }]), "cfgwrite_key_invalid") === "cfgwrite_key_invalid", "");
  check("重复键 typed 拒 cfgwrite_duplicate_key", throwsCode(() => buildFrontmatterBlock([{ key: "a", value: "1" }, { key: "a", value: "2" }])) === "cfgwrite_duplicate_key", "");
  check("expectedKeys 漂移 typed 拒 cfgwrite_roundtrip_mismatch",
    throwsCode(() => writeFrontmatterChecked([{ key: "name", value: "a" }, { key: "description", value: "b" }], ["name"])) === "cfgwrite_roundtrip_mismatch", "");
  // ⑦ 负例·注入加行：写后文本被注入多一行键→round-trip 校验拦下
  const good = writeFrontmatterChecked([{ key: "name", value: "a" }, { key: "description", value: "b: &c *d !!e" }], ["name", "description"]);
  const injected = good.split("\n").toSpliced(3, 0, 'injected: "x"').join("\n");
  check("注入加行被 round-trip 键集合校验拦（cfgwrite_roundtrip_mismatch）", throwsCode(() => roundTripCheckFrontmatter(injected, ["name", "description"])) === "cfgwrite_roundtrip_mismatch", "");
}

// 清场：合成材料不留痕
try { rmSync(SCRATCH, { recursive: true, force: true }); } catch { /* Windows 句柄延迟，留给下轮 */ }

const total = fails();
console.log(`[configwrite-synth] checks=${results.length} fail=${total}`);
console.log(total === 0 ? "CONFIGWRITE_SYNTH_PASS" : "CONFIGWRITE_SYNTH_FAIL");
process.exit(total === 0 ? 0 : 1);
