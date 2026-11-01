// 功能 #36 分层记忆合成用例（RE-36 §4 对拍 12 行验收口径，全部合成材料）：
// A 段=运行时直驱（createLayeredMemoryRuntime，root=仓库 .local 刮擦目录，不碰 %APPDATA%）：
//   ①空库直接可用+四层两作用域概览（对拍 1/12；F4）②偏好文件族写读原样+新建类型文件自动识别
//   （对拍 4；F16）③自动维护文件拒绝手写（F17）+路径逃逸拒绝④显式纠正去重累加+时间戳（对拍 1/§3）
//   ⑤分类树回写：空库创建/去重合并/新节点追加/计数+last_updated（对拍 5；F2/F4）+deal_type 六选一拒绝
//   ⑥代表方回写五要素（对拍 10；F12/F13）⑦置信门：唯一命中直采+告知可改（对拍 7；F8/F10）/
//   多命中弹窗置顶·并列取最近（对拍 8；F9）/无历史按无记忆（F18）⑧inputs 显式传入优先：
//   被覆盖字段不进 questions、整组全被覆盖整批不发（对拍 9；F11）⑨类别匹配注入：类型>通用、
//   多命中只取第一、缺失静默、项目约定优先于个人偏好、会话无项目无项目层（对拍 11；F14/F15/§3）
//   ⑩researched 沉淀复用+研究未做不沉淀不改标记（对拍 6；F5/F6）⑪清除：删文件级+删作用域级
//   （对拍 4 红线可清除）⑫taxonomy 损坏按空库重建/corrections 损坏如实抛错（§6-⑥我方裁决面）
// B 段=隔离桥（BRIDGE_TEST_PORT 默认 3086 + BRIDGE_LAYERED_MEMORY_ROOT 刮擦目录；不碰 :3030/:43127）：
//   ⑬RPC 十一命令面接线冒烟：overview/read/write/auto 拒/correction/taxonomy/representative/gate/
//   injectionPlan/research/clear 全走真桥（对拍 1-12 桥面等价）。
// 末行 RE36_SYNTH_PASS / RE36_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { createLayeredMemoryRuntime } from "./layered_memory_runtime.mjs";
import { emptyTaxonomyFile, mergeTaxonomy, resolveConfidenceGate, matchPreferenceFiles } from "../../packages/juscite-legal/src/kernel/layeredMemoryModel.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_TEST_PORT ?? 3086);
const SCRATCH = join(REPO_ROOT, ".local", `re36-scratch-${Date.now()}`);
mkdirSync(SCRATCH, { recursive: true });
const results: Array<{ name: string; ok: boolean }> = [];
function check(name: string, ok: boolean, detail = "") {
  results.push({ name, ok });
  console.log(`[re36-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const fails = () => results.filter((r) => !r.ok).length;
async function expectReject(name: string, fn: () => unknown | Promise<unknown>, detailNeedle = "") {
  let rejected = false, msg = "";
  try { await fn(); } catch (e) { rejected = true; msg = String((e as Error)?.message ?? e); }
  check(name, rejected && (!detailNeedle || msg.includes(detailNeedle)), msg.slice(0, 70));
}

// ═══ A 段：运行时直驱（真实 fs，落仓库刮擦目录）═══
const rt = createLayeredMemoryRuntime({ root: SCRATCH, log: () => {} });

// ── ① 空库直接可用（F4）+ 概览形状 ──
{
  const ov = rt.overview();
  check("空库直接可用：概览零文件不报错", ov.files.length === 0 && ov.layers.preference.fileCount === 0, JSON.stringify(ov.layers));
  const plan = rt.injectionPlan({ projectId: null });
  check("空库注入=空块静默（F15）", plan.block === "" && plan.usedKeys.length === 0, `block 长度 ${plan.block.length}`);
}

// ── ② 偏好文件族写读原样 + 新建类型文件自动识别（F16）──
{
  const w = rt.writeHandwritten("user/preferences.md", "文书落款统一用「此致 敬礼」两行式。\n");
  check("通用偏好文件写入", w.rel === "user/preferences.md" && w.kind === "handwritten", w.rel);
  const r = rt.readRaw("user/preferences.md");
  check("原样读回（可查看）", r.exists && r.content.includes("此致 敬礼"), r.content.slice(0, 20));
  rt.writeHandwritten("user/preferences-技术合同.md", "技术合同审查优先核对保密条款与知识产权归属。\n");
  rt.writeHandwritten("user/preferences-劳务.md", "劳务合同优先核对工伤责任与竞业限制边界。\n");
  const matched = matchPreferenceFiles(
    [{ fileName: "preferences.md", typeKey: null, body: "通用" }, { fileName: "preferences-技术合同.md", typeKey: "技术合同", body: "技术" }],
    "软件开发（技术合同类）",
  );
  check("类别关键词命中类型文件（F14）", matched.typeFile?.fileName === "preferences-技术合同.md" && matched.commonFile?.fileName === "preferences.md", matched.typeFile?.fileName ?? "null");
  const planT = rt.injectionPlan({ projectId: null, category: "技术服务（技术合同）" });
  check("注入含类型偏好段", planT.usedKeys.includes("user/preferences-技术合同.md"), planT.usedKeys.join(","));
}

// ── ③ 自动维护文件拒绝手写（F17）+ 路径逃逸拒绝 ──
{
  await expectReject("自动维护文件拒绝手写（F17）", () => rt.writeHandwritten("user/corrections.json", "{}"), "自动维护");
  await expectReject("自动维护树文件拒绝手写（F17）", () => rt.writeHandwritten("projects/mat_x1/auto/taxonomy.json", "{}"), "自动维护");
  await expectReject("上级目录逃逸拒绝", () => rt.writeHandwritten("user/../../evil.md", "x"));
  await expectReject("绝对路径拒绝", () => rt.readRaw("C:/Windows/notepad.exe"));
  await expectReject("记忆域白名单外拒绝", () => rt.writeHandwritten("user/notes.txt", "x"));
}

// ── ④ 显式纠正：首次追加 / 同类累加次数与时间戳（§3 写入触发①）──
{
  const r1 = rt.recordCorrection({ scene: "文书起草", wrong: "把违约金写成固定 5 万", right: "违约金按合同约定比例表述并注明上限", origin: "对话纠正" });
  check("显式纠正首次追加", r1.merged === "appended" && r1.rel === "user/corrections.json", r1.id);
  const r2 = rt.recordCorrection({ scene: "文书起草", wrong: "把违约金写成固定 5 万", right: "违约金按合同约定比例表述并注明上限" });
  check("同类纠正去重累加（count=2）", r2.merged === "updated", r2.id);
  const raw = JSON.parse(rt.readRaw("user/corrections.json").content);
  check("纠正记录带来源与时间戳（§3）", raw.records.length === 1 && raw.records[0].count === 2
    && raw.records[0].source === "explicit" && raw.records[0].createdAt > 0 && raw.records[0].updatedAt >= raw.records[0].createdAt,
  `rows=${raw.records.length}`);
  const planC = rt.injectionPlan({ projectId: null, turnText: "帮我把违约金写成固定 5 万" });
  check("纠正注入按轮次文本命中渲染", planC.usedKeys.includes("user/corrections.json") && planC.block.includes("已纠正 2 次"), planC.usedKeys.join(","));
}

// ── ⑤ 分类树回写：空库创建/去重/追加/计数+last_updated（F2/F4）+ deal_type 六选一 ──
{
  const s1 = rt.sedimentTaxonomy({ projectId: "mat_re36a", treeKey: "contract_category", path: ["服务合同", "技术开发"] });
  check("空库直接创建路径（F4）", s1.appended.join("/") === "服务合同/技术开发" && s1.totalClassified === 1, s1.appended.join("/"));
  const s2 = rt.sedimentTaxonomy({ projectId: "mat_re36a", treeKey: "contract_category", path: ["服务合同", "技术开发"] });
  check("已有路径去重合并不重复（F2）", s2.appended.length === 0 && s2.totalClassified === 2, `appended=${s2.appended.length}`);
  const s3 = rt.sedimentTaxonomy({ projectId: "mat_re36a", treeKey: "contract_category", path: ["服务合同", "技术服务"] });
  check("新节点沿既有父追加（F2）", s3.appended.join("/") === "技术服务", s3.appended.join("/"));
  const tree = JSON.parse(rt.readRaw("projects/mat_re36a/auto/taxonomy.json").content);
  const svc = tree.trees.contract_category.find((n: { name: string }) => n.name === "服务合同");
  check("树结构=单根双子且 meta 计数/日期在（F2/F3）", svc?.children?.length === 2 && tree._meta.total_classified === 3 && tree._meta.last_updated !== "",
    `children=${svc?.children?.map((c: { name: string }) => c.name).join("/")}`);
  await expectReject("deal_type 根节点六选一外拒绝", () => rt.sedimentTaxonomy({ projectId: "mat_re36a", treeKey: "deal_type", path: ["虚拟行为"] }), "六选一");
  const s4 = rt.sedimentTaxonomy({ projectId: "mat_re36a", treeKey: "deal_type", path: ["服务行为"] });
  check("deal_type 六选一内放行", s4.appended.join("/") === "服务行为", s4.appended.join("/"));
  await expectReject("非法项目 id 拒绝", () => rt.sedimentTaxonomy({ projectId: "../evil", treeKey: "contract_category", path: ["x"] }), "项目 id");

  // 纯模型幂等核对：merge 不改调用方入参
  const base = emptyTaxonomyFile(Date.now());
  const merged = mergeTaxonomy(base, "industry_sector", ["建筑业"], Date.now());
  check("纯模型回写不改入参", base.trees.industry_sector.length === 0 && merged.file.trees.industry_sector.length === 1, "clone 生效");
}

// ── ⑥ 代表方回写五要素（F12/F13）──
{
  const w1 = rt.sedimentRepresentative({ projectId: "mat_re36a", name: "合成科技（厦门）有限公司", role: "买方", category: "买卖合同", scale: "严格", date: "2026-10-01" });
  check("新主体追加一行", w1.merged === "appended" && w1.rowCount === 1, w1.rel);
  rt.sedimentRepresentative({ projectId: "mat_re36a", name: "合成科技（厦门）有限公司", role: "买方", category: "技术合同", scale: "严格", date: "2026-10-20" });
  rt.sedimentRepresentative({ projectId: "mat_re36a", name: "合成贸易（福建）有限公司", role: "卖方", category: "买卖合同", scale: "宽松", date: "2026-10-21" });
  const rep = JSON.parse(rt.readRaw("projects/mat_re36a/auto/representatives.json").content);
  const a = rep.rows.find((r: { name: string }) => r.name === "合成科技（厦门）有限公司");
  check("五要素：去重+次数+日期+类别并入+尺度计票（F12）",
    rep.rows.length === 2 && a.selectCount === 2 && a.lastSelectedAt === "2026-10-20"
    && a.categories.join("/") === "买卖合同/技术合同" && a.scaleVotes["严格"] === 2,
    `count=${a?.selectCount} cats=${a?.categories.join("/")}`);
  check("未确认主体不入账（F13 只回写调用方确认项）", !rep.rows.some((r: { name: string }) => r.name === "未确认相对方"), "调用方不送即不写");
}

// ── ⑦ 置信门：唯一命中直采+告知可改 / 多命中置顶 / 无历史（F8/F9/F10/F18）──
{
  const g1 = resolveConfidenceGate([{ name: "合成科技（厦门）有限公司", role: "买方", selectCount: 2, lastSelectedAt: "2026-10-20", scaleVotes: { "严格": 2 } }], {});
  check("唯一命中=高置信直采+一句话告知（F8/F10）", g1.mode === "direct" && g1.adopted.name === "合成科技（厦门）有限公司"
    && g1.notice.includes("如需更换") && g1.questions.length === 0, g1.notice.slice(0, 30));
  const g2 = resolveConfidenceGate([
    { name: "甲公司", selectCount: 3, lastSelectedAt: "2026-09-01" },
    { name: "乙公司", selectCount: 3, lastSelectedAt: "2026-10-05" },
    { name: "丙公司", selectCount: 1, lastSelectedAt: "2026-10-28" },
  ], {});
  check("多命中=弹窗置顶（次数最高；并列取最近日期）（F9）", g2.mode === "ask" && g2.questions[0]?.key === "party" && g2.questions[0]?.pinnedDefault === "乙公司", g2.questions[0]?.pinnedDefault);
  const g3 = resolveConfidenceGate([], {});
  check("无历史=题照出无默认（F18）", g3.mode === "ask" && g3.questions.some((q) => q.key === "party" && q.pinnedDefault === undefined), JSON.stringify(g3.questions));
  const g4 = resolveConfidenceGate([{ name: "甲公司", selectCount: 1, lastSelectedAt: "2026-10-01", scaleVotes: { "严格": 3 } }], {});
  check("尺度单一→尺度题跳过（F8）", !g4.questions.some((q) => q.key === "scale") && g4.adopted.scale === "严格", JSON.stringify(g4.questions));
  const g5 = resolveConfidenceGate([{ name: "甲公司", selectCount: 1, lastSelectedAt: "2026-10-01", scaleVotes: { "严格": 2, "宽松": 2 } }], {});
  check("尺度拉锯→题照出+默认置顶（F9）", g5.questions.some((q) => q.key === "scale" && q.pinnedDefault === "严格"), JSON.stringify(g5.questions));
  const gate = rt.resolveGate({ candidates: [{ name: "甲公司", selectCount: 1, lastSelectedAt: "2026-10-01" }], inputs: {} });
  check("运行时门与纯模型等价：主体直采+无尺度记录→尺度题照出（F8+F18 同族）",
    gate.mode === "ask" && gate.adopted.name === "甲公司" && gate.notice.includes("如需更换")
    && gate.questions.length === 1 && gate.questions[0].key === "scale", JSON.stringify(gate.questions));
}

// ── ⑧ inputs 显式传入优先（F11）──
{
  const f1 = resolveConfidenceGate([{ name: "甲公司", selectCount: 5, lastSelectedAt: "2026-10-01" }, { name: "乙公司", selectCount: 4, lastSelectedAt: "2026-10-02" }],
    { partyName: "丙公司" });
  check("inputs 传主体→主体题不进 questions 且不提示历史", !f1.questions.some((q) => q.key === "party") && f1.notice === "" && f1.adopted.name === "丙公司", JSON.stringify(f1.questions));
  const f2 = resolveConfidenceGate([], { partyName: "丙公司", scale: "严格" });
  check("整组全被覆盖→整批不发（questions 空）", f2.mode === "direct" && f2.questions.length === 0, JSON.stringify(f2.questions));
  const f3 = resolveConfidenceGate([{ name: "甲公司", selectCount: 1, lastSelectedAt: "2026-10-01", scaleVotes: { "严格": 2, "宽松": 2 } }], { scale: "宽松" });
  check("inputs 传尺度→尺度题剔除、历史题保留", f3.questions.length === 0 && f3.adopted.scale === "宽松", JSON.stringify(f3.questions));
}

// ── ⑨ 注入装配：项目约定优先于个人偏好；类型>通用；无项目无项目层（§3/F14）──
{
  rt.writeHandwritten("projects/mat_re36a/conventions.md", "本项目金额表述统一用人民币大写+小写并列。\n");
  rt.writeHandwritten("projects/mat_re36a/resources.md", "常用模板在 knowledge-base/合同模板/技术委托.docx。\n");
  const plan1 = rt.injectionPlan({ projectId: "mat_re36a", category: "技术合同" });
  const convIdx = plan1.block.indexOf("【项目约定】");
  const typeIdx = plan1.block.indexOf("【个人偏好】");
  const resIdx = plan1.block.indexOf("【资源指引】");
  const corrIdx = plan1.block.indexOf("【操作纠正】");
  check("块序=项目约定>个人偏好>操作纠正>资源指引（§3）", convIdx >= 0 && convIdx < typeIdx && typeIdx < corrIdx && corrIdx < resIdx,
    `conv=${convIdx} pref=${typeIdx} corr=${corrIdx} res=${resIdx}`);
  check("类型偏好注入且先于通用（F14）", plan1.block.indexOf("知识产权归属") < plan1.block.indexOf("此致 敬礼"), "type<common");
  const plan2 = rt.injectionPlan({ projectId: "mat_re36a", category: "完全不沾边类别" });
  check("类别不命中→只有通用偏好（多命中只取第一的反向面）", plan2.block.includes("此致 敬礼") && !plan2.block.includes("知识产权归属"), "common only");
  const plan3 = rt.injectionPlan({ projectId: "mat_other", category: "技术合同" });
  check("无记忆项目=无项目层只用户层（F15 静默）", !plan3.block.includes("项目约定") && plan3.block.includes("此致 敬礼"), plan3.usedKeys.join(","));
  const plan4 = rt.injectionPlan({ projectId: null });
  check("会话未绑项目=无项目层（D2 两作用域）", !plan4.block.includes("项目约定") && !plan4.block.includes("资源指引"), plan4.usedKeys.join(","));
  await expectReject("注入项目 id 非法拒绝", () => rt.injectionPlan({ projectId: ".." }), "项目 id");
}

// ── ⑩ researched 沉淀复用 + 研究未做不沉淀不改标记（F5/F6）──
{
  const r0 = rt.researchReuse({ projectId: "mat_re36a", leafName: "技术开发" });
  check("未研究叶=needResearch", r0.needResearch && !r0.reuse && r0.sediment === null, JSON.stringify(r0));
  const skip = rt.sedimentResearch({ projectId: "mat_re36a", leafName: "技术开发", content: "   " });
  check("研究未做（空内容）→不沉淀不改标记（F6）", skip.sedimented === false && rt.readRaw("projects/mat_re36a/auto/research/技术开发.md").exists === false, "no write");
  const w = rt.sedimentResearch({ projectId: "mat_re36a", leafName: "技术开发", content: "技术开发合同审查要点：验收标准须可量化；保密期不超过 5 年。（合成沉淀）" });
  check("研究完成→沉淀文件+researched 标记（F5）", w.sedimented && rt.readRaw(w.rel).exists, w.rel);
  const again = rt.researchReuse({ projectId: "mat_re36a", leafName: "技术开发" });
  check("同类复用=不再研究（F5）", again.reuse && !again.needResearch && again.sediment?.includes("验收标准"), "reuse");
  await expectReject("叶不在分类树→标记拒绝不虚设", () => rt.sedimentResearch({ projectId: "mat_re36a", leafName: "幽灵节点", content: "正文" }), "不存在");
}

// ── ⑪ 清除（红线：可清除，删文件级+删作用域级）──
{
  rt.writeHandwritten("user/preferences-临时.md", "临时偏好\n");
  rt.clearFile("user/preferences-临时.md");
  check("删文件级清除", rt.readRaw("user/preferences-临时.md").exists === false, "gone");
  rt.clearScope("project", "mat_re36a");
  check("删作用域级清除（项目）", rt.listFiles().every((f) => !f.rel.startsWith("projects/mat_re36a/")), rt.listFiles().map((f) => f.rel).join(","));
  await expectReject("清除非法项目 id 拒绝", () => rt.clearScope("project", "../../evil"), "项目 id");
}

// ── ⑫ 损坏面（§6-⑥ 竞品无载；我方裁决：自动知识树重建、用户纠正记录 fail-closed）──
{
  const pid = "mat_re36b";
  rt.sedimentTaxonomy({ projectId: pid, treeKey: "contract_category", path: ["买卖合同"] });
  const rel = `projects/${pid}/auto/taxonomy.json`;
  const abs = join(SCRATCH, "projects", pid, "auto", "taxonomy.json");
  writeFileSync(abs, "{corrupted!!", "utf-8");
  const s = rt.sedimentTaxonomy({ projectId: pid, treeKey: "contract_category", path: ["租赁合同"] });
  check("taxonomy 损坏→按空库重建可继续写（自定裁决）", s.appended.join("/") === "租赁合同" && s.totalClassified === 1, JSON.stringify(s));
  const crel = "user/corrections.json";
  writeFileSync(join(SCRATCH, "user", "corrections.json"), "not-json", "utf-8");
  await expectReject("corrections 损坏→如实抛错不吞用户数据（fail-closed）", () => rt.recordCorrection({ scene: "s", wrong: "w", right: "r" }), "损坏");
  const planBad = rt.injectionPlan({ projectId: null });
  check("corrections 损坏不阻塞注入", planBad.usedKeys.every((k) => k !== "user/corrections.json"), planBad.usedKeys.join(","));
  rmSync(join(SCRATCH, "user", "corrections.json"), { force: true });
}

// ═══ B 段：隔离桥 RPC 接线（:3086，独立刮擦根）═══
const SCRATCH_B = join(REPO_ROOT, ".local", `re36-bridge-scratch-${Date.now()}`);
mkdirSync(SCRATCH_B, { recursive: true });
let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, ".local", `re36-synth-bridge-${PORT}.log`), "a");
const NODE = process.execPath;
let call: <T>(m: string, a?: unknown) => Promise<T> = async () => { throw new Error("未连接"); };
function bridgeSpawn() {
  const env = { ...process.env, BRIDGE_PORT: String(PORT), BRIDGE_LAYERED_MEMORY_ROOT: SCRATCH_B };
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
  while (Date.now() < deadline) { if (await probe()) return true; await new Promise((r) => setTimeout(r, 500)); }
  return false;
}
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
      const ch = new ChannelClient(new SocketProtocol(isocket as never)).getChannel("zcode-agent");
      call = async <T,>(m: string, a?: unknown) => ch.call<T>(m, a === undefined ? [] : [a]);
      call("helloConversationV4").then(() => resolve()).catch(reject);
    });
    ws.on("error", reject);
  });
}

bridgePid = bridgeSpawn();
if (!(await waitProbe(40000))) { console.log("RE36_SYNTH_FAIL"); console.error("桥 40s 不可探"); process.exit(1); }
await connect();

{
  const ov = await call<{ files: Array<{ rel: string }>; layers: Record<string, unknown> }>("memoryLayerOverview", {});
  check("B① RPC 概览=空库可用（F4）", ov.files.length === 0, JSON.stringify(ov.layers).slice(0, 60));
  await call("memoryLayerWrite", { rel: "user/preferences.md", content: "桥面写偏好\n" });
  const rd = await call<{ exists: boolean; content: string }>("memoryLayerRead", { rel: "user/preferences.md" });
  check("B② RPC 写读原样", rd.exists && rd.content.includes("桥面写偏好"), rd.content.slice(0, 20));
  await expectReject("B③ RPC 自动维护文件拒绝手写（F17）", () => call("memoryLayerWrite", { rel: "user/corrections.json", content: "{}" }), "自动维护");
  const cor = await call<{ merged: string }>("memoryLayerCorrection", { scene: "看板", wrong: "手改状态列", right: "走看板操作改状态" });
  check("B④ RPC 显式纠正落盘", cor.merged === "appended", cor.merged);
  const tax = await call<{ totalClassified: number }>("memoryLayerTaxonomyWrite", { projectId: "mat_re36c", treeKey: "contract_category", path: ["服务合同"] });
  check("B⑤ RPC 分类回写", tax.totalClassified === 1, String(tax.totalClassified));
  const rep = await call<{ merged: string }>("memoryLayerRepresentativeWrite", { projectId: "mat_re36c", name: "桥面合成主体", role: "承租方", category: "租赁合同", scale: "严格" });
  check("B⑥ RPC 代表方回写", rep.merged === "appended", rep.merged);
  const gate = await call<{ mode: string; adopted: { name?: string }; notice: string; questions: Array<{ key: string; pinnedDefault?: string }> }>("memoryLayerGate", { candidates: [{ name: "桥面合成主体", selectCount: 1, lastSelectedAt: "2026-10-29" }], inputs: {} });
  check("B⑦ RPC 置信门：主体直采+无尺度记录→尺度题照出（F8/F18）",
    gate.mode === "ask" && gate.adopted.name === "桥面合成主体" && gate.notice.includes("如需更换")
    && gate.questions.length === 1 && gate.questions[0].key === "scale", JSON.stringify(gate.questions));
  const gateFull = await call<{ mode: string; questions: Array<{ key: string }> }>("memoryLayerGate",
    { candidates: [{ name: "桥面合成主体", selectCount: 1, lastSelectedAt: "2026-10-29", scaleVotes: { "严格": 2 } }], inputs: { scale: "严格" } });
  check("B⑦b RPC 置信门：齐备候选+inputs 尺度→直采整批发（F8/F11）", gateFull.mode === "direct" && gateFull.questions.length === 0, gateFull.mode);
  const planB = await call<{ block: string; usedKeys: string[] }>("memoryLayerInjectionPlan", { projectId: "mat_re36c", category: "技术合同", turnText: "" });
  check("B⑧ RPC 注入预览含用户层", planB.usedKeys.includes("user/preferences.md"), planB.usedKeys.join(","));
  const rs = await call<{ sedimented: boolean }>("memoryLayerResearchWrite", { projectId: "mat_re36c", leafName: "服务合同", content: "桥面合成沉淀：服务合同验收以里程碑单为准。" });
  check("B⑨ RPC 沉淀（F5）", rs.sedimented, JSON.stringify(rs));
  const rg = await call<{ reuse: boolean }>("memoryLayerResearchGet", { projectId: "mat_re36c", leafName: "服务合同" });
  check("B⑩ RPC 复用查询", rg.reuse, JSON.stringify(rg));
  await call("memoryLayerClear", { scope: "project", projectId: "mat_re36c" });
  const ov2 = await call<{ files: Array<{ rel: string }> }>("memoryLayerOverview", {});
  check("B⑪ RPC 作用域级清除", ov2.files.every((f) => !f.rel.startsWith("projects/mat_re36c/")), ov2.files.map((f) => f.rel).join(","));
}

// ── 收口 ──
const bad = fails();
console.log(`[re36-synth] 合计 ${results.length} 检查，FAIL ${bad}`);
if (bridgePid) {
  const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${bridgePid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  if (String(q.stdout ?? "").includes("bridge_host.mjs")) {
    spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
    console.log(`[re36-synth] 清场：桥 pid=${bridgePid} 已收`);
  }
}
if (bad > 0) { console.log("RE36_SYNTH_FAIL"); process.exit(1); }
console.log("RE36_SYNTH_PASS");
process.exit(0);
