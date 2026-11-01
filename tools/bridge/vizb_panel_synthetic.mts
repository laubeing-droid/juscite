// 可视化B轨 UI 件合成自测（施工波二轮；全合成材料，逐条可复跑）：
// 面板侧投影（@juscite/legal chronicleView/confrontationView 纯函数，进程内直调）
// → 桥面五工具（vizbChronicleCheck/Render、vizbConfrontationCheck/Render、vizbIntakeReconcile，
//   隔离端口自管桥实例经真 RPC，默认 :3093 可 BRIDGE_PANEL_TEST_PORT 覆盖；不碰 :3030/:43127，
//   杀前核验命令行含 bridge_host.mjs）。覆盖面板按钮全链路中除浏览器 DOM 外的每一环：
//   P1 投影编入/排除裁决        P2 投影确定性（同输入逐字节一致）
//   P3 真桥 check ok + render 四件同源交付
//   P4 真桥同底稿两跑 render 逐字节一致（确定性渲染，经 RPC）
//   P5 表外动词透传→真桥拒绝并报 C-verb-off-table（表外拒绝走补表流程，不本地改写）
//   P6 摄入对账整份单页口径：缺文本拒（该读没读）+ 明示不读放行留痕（真桥）
//   P7 对抗语义 check ok + render 图表两件（真桥 RPC）
//   P8 对抗摘要纯函数与语义一致（面板表格预览数据源）
// 末行 VIZB_PANEL_SYNTH_PASS / VIZB_PANEL_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { openSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
import { projectChronicleFactBase, buildIntakePayload } from "../../packages/juscite-legal/src/panels/chronicleView.ts";
import { parseConfrontationSemantic, summarizeConfrontation } from "../../packages/juscite-legal/src/panels/confrontationView.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.BRIDGE_PANEL_TEST_PORT ?? 3093);
const NODE = process.execPath;
const results: Array<{ name: string; ok: boolean }> = [];
function check(name: string, ok: boolean, detail: string) {
  results.push({ name, ok });
  console.log(`[vizb-panel-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ══ 合成材料（全合成；借贷案名/人名/金额均为本单自拟）══
const DOC_TEXT = "2026年4月10日，王五于本市向赵六出借现金伍万元整，双方口头约定同年年底归还。"
  + "2026年8月1日，法院判决赵六偿还本金伍万元。2026年9月20日，赵六仅归还壹万元。合成材料至此为止。";
const DOCS = [{ filename: "借条与判决合成材料.txt", text: DOC_TEXT, truncated: false }];
const QUOTE_LOAN = "王五于本市向赵六出借现金伍万元整";
const QUOTE_JUDGE = "法院判决赵六偿还本金伍万元";
const QUOTE_REPAY = "赵六仅归还壹万元";
function panelEvents() {
  return [
    { eventId: "s1", eventType: "开庭", date: "2026-04-10", sourceRefs: [{ filename: "借条与判决合成材料.txt", locator: "p1¶1", quote: QUOTE_LOAN }], payload: { subjects: ["王五", "赵六"] } },
    { eventId: "s2", eventType: "判决", date: "2026-08-01", sourceRefs: [{ filename: "借条与判决合成材料.txt", locator: "p1¶2", quote: QUOTE_JUDGE }], payload: null },
    { eventId: "s3", eventType: "期限登记", date: null, sourceRefs: [], payload: null }, // 无日期→排除
    { eventId: "s4", eventType: "材料登记", date: "2026-09-20", sourceRefs: [{ filename: "借条与判决合成材料.txt" }], payload: null }, // 缺引文→排除
  ];
}

// ══ P1/P2 投影纯函数 ══
{
  const proj = projectChronicleFactBase(panelEvents(), DOCS, "王五诉赵六借贷纠纷（合成）");
  check("P1 投影编入/排除裁决：有日期+有引文编入 2 条，无日期/缺引文各排除并具名",
    proj.included === 2 && proj.excluded.length === 2
    && proj.excluded.some((x) => x.reason.includes("无确切日期")) && proj.excluded.some((x) => x.reason.includes("引文"))
    && proj.factBase.facts[0]!.content === QUOTE_LOAN && proj.factBase.facts[0]!.subjects.join(",") === "王五,赵六",
    `included=${proj.included} excluded=${proj.excluded.map((x) => x.reason.slice(0, 6)).join("/")}`);
  const again = JSON.stringify(projectChronicleFactBase(panelEvents(), DOCS, "王五诉赵六借贷纠纷（合成）"));
  check("P2 投影确定性：同输入两跑逐字节一致", again === JSON.stringify(proj), "byte-equal");
}

// ══ P8 对抗摘要纯函数 ══
const SEMANTIC_TEXT = JSON.stringify(synthSemantic());
{
  const parsed = parseConfrontationSemantic(SEMANTIC_TEXT);
  const s = summarizeConfrontation(parsed.value);
  check("P8 对抗摘要：2 要件行只读展示（三标/争议标记原样，不判决定性）",
    parsed.ok && s.ok && s.rows.length === 2 && s.rows[0]!.lawConfidence === "high"
    && s.rows[1]!.evidenceStandardMet === false && s.claimsCount === 1 && s.defensesCount === 1,
    `rows=${s.rows.length} claims=${s.claimsCount} defenses=${s.defensesCount}`);
}

function synthSemantic(): unknown {
  return {
    schema: "juscite.vizb.confrontation@1",
    caseTitle: "戊公司诉丙公司买卖合同纠纷（合成）",
    internalOnly: true,
    maturity: "L2",
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
        disputed: true, evidenceStandardMet: false },
    ],
    toComplete: ["要件2 质检报告未取得（合成）"],
  };
}

// ══ 真桥接线（隔离端口自管桥实例；不碰 :3030/:43127）══
let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, ".local", `vizb-panel-synth-bridge-${PORT}.log`), "a");
function probe(): Promise<boolean> {
  return (async () => {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/api/server-info`, { signal: AbortSignal.timeout(2500) });
      return r.ok;
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
  const pre = await probe();
  if (pre) throw new Error(`端口 :${PORT} 已被占用（拒绝复用来历不明的桥实例；请改 BRIDGE_PANEL_TEST_PORT）`);
  const env = { ...process.env, BRIDGE_PORT: String(PORT) };
  const child = spawn(NODE, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")],
    { cwd: REPO_ROOT, env, stdio: ["ignore", bridgeLog, bridgeLog], detached: true });
  child.unref();
  bridgePid = child.pid!;
  let up = false;
  const deadline = Date.now() + 40000;
  while (Date.now() < deadline) { if (await probe()) { up = true; break; } await sleep(500); }
  check("BRIDGE 桥实例拉起（隔离端口 :" + PORT + "）", up, `pid=${bridgePid}`);
  if (!up) throw new Error("隔离桥未在超时内就绪");

  await connect();
  const proj = projectChronicleFactBase(panelEvents(), DOCS, "王五诉赵六借贷纠纷（合成）");

  // P3 校验+渲染四件同源交付（面板按钮主链路）
  const ck = await call<{ ok: boolean; refusal: string | null; guardViolations: Array<{ code: string }> }>(
    "vizbChronicleCheck", { factBase: proj.factBase });
  const arts = await call<{ wordXml: string; excelXml: string; briefSvgPages: string[]; factBaseJson: string }>(
    "vizbChronicleRender", { factBase: proj.factBase });
  check("P3 真桥 check ok + render 四件同源交付（Word/Excel/简表SVG/底稿JSON）",
    ck.ok === true && arts.wordXml.includes("Word.Document") && arts.excelXml.length > 0
    && arts.briefSvgPages.length >= 1 && arts.briefSvgPages[0]!.includes("<svg")
    && arts.factBaseJson.includes("王五诉赵六借贷纠纷"),
    `word=${arts.wordXml.length}B excel=${arts.excelXml.length}B brief页=${arts.briefSvgPages.length}`);

  // P4 确定性渲染：同底稿两跑 render 逐字节一致（经真桥 RPC）
  const arts2 = await call<{ wordXml: string; briefSvgPages: string[]; factBaseJson: string }>(
    "vizbChronicleRender", { factBase: proj.factBase });
  check("P4 同底稿两跑 render 逐字节一致（确定性渲染经 RPC）",
    arts2.wordXml === arts.wordXml && arts2.briefSvgPages.join("") === arts.briefSvgPages.join("")
    && arts2.factBaseJson === arts.factBaseJson,
    "byte-equal");

  // P5 表外动词透传→桥面拒绝并指明补表流程（面板不改写不降级）
  const offTable = projectChronicleFactBase(
    panelEvents().slice(0, 1).concat([{ eventId: "s5", eventType: "还款期", date: "2026-09-20", sourceRefs: [{ filename: "借条与判决合成材料.txt", locator: "p1¶3", quote: QUOTE_REPAY }], payload: null }]),
    DOCS, "王五诉赵六借贷纠纷（合成）");
  const ckBad = await call<{ ok: boolean; refusal: string; guardViolations: Array<{ code: string }> }>(
    "vizbChronicleCheck", { factBase: offTable.factBase });
  check("P5 表外动词透传→真桥拒绝并报 C-verb-off-table（补表流程指名）",
    ckBad.ok === false && ckBad.guardViolations.some((x) => x.code === "C-verb-off-table")
    && ckBad.refusal.includes("补表"),
    `refusal=${ckBad.refusal.slice(0, 60)}`);

  // P6 摄入对账（整份单页口径）：缺文本拒 + 明示不读放行留痕（真桥）
  const intakeBad = await call<{ ok: boolean; docs: Array<{ docId: string; state: string }> }>("vizbIntakeReconcile",
    buildIntakePayload(DOCS, ["借条与判决合成材料.txt", "缺席材料.txt"], []));
  const intakeSkip = await call<{ ok: boolean; logs: string[]; docs: Array<{ docId: string; state: string }> }>("vizbIntakeReconcile",
    buildIntakePayload(DOCS, ["借条与判决合成材料.txt"], ["借条与判决合成材料.txt"]));
  check("P6 摄入对账：取不到文本=该读没读拒；明示不读=放行留痕（真桥）",
    intakeBad.ok === false && intakeBad.docs.find((d) => d.docId === "缺席材料.txt")?.state === "missing"
    && intakeSkip.ok === true && intakeSkip.logs.some((l) => l.includes("明示不读")),
    `missing=${intakeBad.docs.find((d) => d.docId === "缺席材料.txt")?.state} skipLogs=${intakeSkip.logs.length}`);

  // P7 对抗语义 check ok + render 图表两件（真桥 RPC）
  const ckC = await call<{ ok: boolean; refusal: string | null }>("vizbConfrontationCheck", { semantic: synthSemantic() });
  const artsC = await call<{ svg: string; analysisTableXml: string }>("vizbConfrontationRender", { semantic: synthSemantic() });
  check("P7 真桥对抗 check ok + render 图表两件",
    ckC.ok === true && artsC.svg.includes("<svg") && artsC.svg.includes("戊公司诉丙公司买卖合同纠纷")
    && artsC.analysisTableXml.includes("对抗分析表"),
    `svg=${artsC.svg.length}B table=${artsC.analysisTableXml.length}B`);
} catch (e) {
  check("BRIDGE 接线", false, String(e instanceof Error ? e.message : e));
} finally {
  if (bridgePid) {
    const q = spawnSync("powershell.exe", ["-NoProfile", "-Command",
      `(Get-CimInstance Win32_Process -Filter "ProcessId=${bridgePid}").CommandLine`],
      { encoding: "utf-8", timeout: 20000 });
    if (String(q.stdout ?? "").includes("bridge_host.mjs")) {
      spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
      console.log(`[vizb-panel-synth] 测试桥已关闭 pid=${bridgePid}`);
    } else {
      console.log(`[vizb-panel-synth] 拒绝杀 pid=${bridgePid}（命令行不含 bridge_host.mjs）——如实留运行`);
    }
  }
}

const failed = results.filter((r) => !r.ok);
if (failed.length) {
  console.log(`VIZB_PANEL_SYNTH_FAIL（${failed.length}/${results.length} 用例失败：${failed.map((f) => f.name).join("；")}）`);
  process.exit(1);
}
console.log(`VIZB_PANEL_SYNTH_PASS（${results.length}/${results.length} 用例通过，全部合成材料）`);
