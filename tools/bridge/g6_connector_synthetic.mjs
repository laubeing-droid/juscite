#!/usr/bin/env node
// 【施工波三轮·桥健①】G6 连接器实弹对拍探针（合成查询；真源=自家 LCCC 轻量包+legal-cn-cases
// lcr 合成夹具库；第三方华宇元典 MCP 无凭据未实弹=仅机制参照——差异表如实记）。
// 链路：A 注册面（经 port registerTools 真跑挂载 oc28:43127+预阻断演示+连接器日志验
//        oc28 MCP client 真握手）
//      B 实弹查询（法条核验四分支+类案三案含 0 结果重试；直连连接器 stdio MCP——与
//        oc28 client 同一 wire 契约；agent 模型腿不在本探针（模型调用归桥真模型轮纪律））
//      C 权限门实弹（oc28 session.permission.create 落 ask → permission.asked 事件 →
//        port setPermissionGate 回调决策 → reply once/reject——真 oc28:43127 往返）
//      D 差异表输出+清场（experimental mcp remove；resident 桥下次启动自动重注册）。
// 自测口径：全部合成材料；只碰 %APPDATA%/Juscite 分区与临时目录；末行 G6_CONNECTOR_SYNTH_PASS。
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createOpenCodeRuntime, loadCredentials, makeClient } from "../../packages/juscite-runtime-adapters/opencode/src/opencodeAdapter.mjs";
import { decideToolCall } from "./tool_policy.mjs";
import { resolveCitationEnginePath, resolveCitationPackDir } from "./citation_verify_service.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(HERE, "..", "..");
let pass = 0, fail = 0;
const failures = [];
function check(name, ok, detail = "") {
  if (ok) { pass++; console.log(`  ok #${pass} ${name}`); }
  else { fail++; failures.push(name + (detail ? `（${detail}）` : "")); console.log(`  FAIL ${name}${detail ? "——" + detail : ""}`); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── 环境组装（与桥 g6ConnectorEnv 同形；探针独立于桥进程自设）──
const LCR_HOME = process.env.JUSCITE_G6_LCR_HOME || "D:\\Codex\\1.法律工作区\\legal-cn-cases工作区\\legal-cn-cases";
const TMP = mkdtempSync(join(tmpdir(), "g6-synth-"));
const ENV = {
  JUSCITE_G6_MCP_SCRIPT: join(HERE, "g6_connector_mcp.mjs"),
  JUSCITE_G6_MCP_LOG: join(TMP, "connector-mcp.log"),
  JUSCITE_G6_LCR_HOME: LCR_HOME,
  JUSCITE_G6_LCR_FIXTURES: join(LCR_HOME, "examples"),
  JUSCITE_G6_LCR_DB: join(TMP, "lcr-synth.sqlite"),
  BRIDGE_CITATION_ENGINE: resolveCitationEnginePath() ?? "",
  BRIDGE_CITATION_PACK_DIR: resolveCitationPackDir() ?? "",
};
Object.assign(process.env, ENV);
const SPECS = [
  { name: "juscite_statute_check", description: "法条有效性核验（探针）", parameters: { type: "object", properties: { query: { type: "string" } }, required: ["query"] } },
  { name: "juscite_case_search", description: "类案检索（探针）", parameters: { type: "object", properties: { query: { type: "string" } }, required: ["query"] } },
];
const BLOCKED_SPEC = { name: "web.search", description: "外部 web 检索（预阻断演示件：外部类未启用源）", parameters: { type: "object", properties: {} } };

// ── A 注册面：预阻断 + 经 port 挂载 oc28 + 握手验证 ──
console.log("== A 注册面（经 port 真跑 oc28:43127）==");
const runtime = createOpenCodeRuntime();
{
  const decisions = [...SPECS, BLOCKED_SPEC].map((s) => ({ spec: s, d: decideToolCall({ toolName: s.name, args: {}, permissionMode: "smart", shellEnabled: false }) }));
  const allowed = decisions.filter((x) => x.d.effect !== "deny").map((x) => x.spec);
  const blocked = decisions.filter((x) => x.d.effect === "deny");
  check("A1 预阻断：web.search 被策略拒（外部类未声明权限——deny 效果，原因码闭集内）", blocked.length === 1 && blocked[0].spec.name === "web.search", JSON.stringify(blocked.map((b) => `${b.spec.name}:${b.d.effect}/${b.d.code}`)));
  check("A2 两腿工具过策略（read_only 放行）", allowed.length === 2 && allowed.every((s) => SPECS.includes(s)));
  let mounted = false, mountErr = "";
  try { await runtime.registerTools(allowed); mounted = true; } catch (e) { mountErr = String(e?.message ?? e); }
  check("A3 registerTools 经 port 挂载成功（oc28 config policy 具名放行 juscite-g6）", mounted, mountErr);
  if (mounted) {
    const client = makeClient(loadCredentials());
    const listing = await client.mcpList();
    const row = (listing?.data ?? []).find((s) => s?.name === "juscite-g6");
    check("A4 GET /api/mcp 在册且 connected", row?.status?.status === "connected", JSON.stringify(row ?? "(不在册)"));
    await sleep(500);
    const log = existsSync(ENV.JUSCITE_G6_MCP_LOG) ? readFileSync(ENV.JUSCITE_G6_MCP_LOG, "utf-8") : "";
    check("A5 连接器日志见 oc28 MCP client initialize 握手", /initialize 自 /.test(log), log.slice(-200));
    check("A6 oc28 经 MCP 面拉取 tools/list（目录=两腿，预阻断件不在目录）", /tools\/list → juscite_statute_check,juscite_case_search/.test(log), log.slice(-300));
    check("A7 连接器 manifest 过滤：web.search 未广告", !/web\.search/.test(log));
  }
}

// ── B 实弹查询（直连连接器 stdio MCP——与 oc28 client 同 wire 契约）──
console.log("== B 实弹查询（合成材料）==");
function mcpCall(tool, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [ENV.JUSCITE_G6_MCP_SCRIPT], { env: process.env });
    let buf = ""; let settled = false;
    const timer = setTimeout(() => { if (!settled) { settled = true; child.kill(); reject(new Error("mcp_call_timeout")); } }, 130_000);
    const send = (msg) => child.stdin.write(JSON.stringify(msg) + "\n");
    child.stdout.setEncoding("utf-8");
    child.stdout.on("data", (d) => {
      buf += d;
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 1);
        if (!line.trim()) continue;
        let msg; try { msg = JSON.parse(line); } catch { continue; }
        if (msg.id === 2) { // tools/call 响应
          settled = true; clearTimeout(timer); child.kill();
          const text = msg.result?.content?.[0]?.text ?? "";
          try { resolve({ isError: msg.result?.isError === true, body: JSON.parse(text) }); } catch { resolve({ isError: true, body: { raw: text.slice(0, 200) } }); }
        }
      }
    });
    child.stdin.write("\n"); // 唤醒
    send({ jsonrpc: "2.0", id: 0, method: "initialize", params: { protocolVersion: "2025-06-18", clientInfo: { name: "g6-synth-probe", version: "1" } } });
    send({ jsonrpc: "2.0", method: "notifications/initialized" });
    send({ jsonrpc: "2.0", id: 1, method: "tools/list" });
    send({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: tool, arguments: args } });
    child.on("exit", () => { if (!settled) { settled = true; clearTimeout(timer); reject(new Error("mcp_child_exit_early")); } });
  });
}
{
  // 法条核验四分支（合成查询；标题取包内实名以保证命中面可断言——包名不带「中华人民共和国」前缀）
  const q = "本院依据《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》第一条、《合同法》第五十二条、《公司法》第二十条以及《中华人民共和国测试法》第一条作出认定。";
  const r = await mcpCall("juscite_statute_check", { query: q, as_of: "20261031" });
  check("B1 法条核验四引证全解析", !r.isError && r.body.total === 4, JSON.stringify(r.body).slice(0, 200));
  const byTitle = Object.fromEntries((r.body.citations ?? []).map((c) => [c.title, c]));
  check("B2 现行分支（民间借贷规定→现行/ALLOWED）", byTitle["最高人民法院关于审理民间借贷案件适用法律若干问题的规定"]?.status === "现行");
  check("B3 失效分支（合同法→失效/SUPERSEDED_NOT_CITABLE，日期窗已闭）", byTitle["合同法"]?.status === "失效" && byTitle["合同法"]?.code === "SUPERSEDED_NOT_CITABLE", JSON.stringify(byTitle["合同法"] ?? {}));
  check("B5 虚构分支（测试法→虚构/PACK_TITLE_MISS fail-closed）", byTitle["中华人民共和国测试法"]?.status === "虚构" && byTitle["中华人民共和国测试法"]?.code === "PACK_TITLE_MISS");
  // 时点选择（G6/RE-14）：公司法同条号跨版本内容切换——as_of 20240630=2018 版（股东滥用条款），
  // 20240701 起=2024 版（社会责任条款）；两时点同条号不同文=「条号新旧公司法核对」机制等量。
  const r0630 = await mcpCall("juscite_statute_check", { query: "《公司法》第二十条", as_of: "20240630" });
  const r0701 = await mcpCall("juscite_statute_check", { query: "《公司法》第二十条", as_of: "20240701" });
  const s0630 = r0630.body.citations?.[0]?.status, s0701 = r0701.body.citations?.[0]?.status;
  const snip0630 = r0630.body.citations?.[0]?.article_snippet ?? "", snip0701 = r0701.body.citations?.[0]?.article_snippet ?? "";
  check("B4 时点选择+同条号跨版本切换（两时点均现行；20240630=2018 版股东条款/20240701=2024 版社会责任条款）",
    s0630 === "现行" && s0701 === "现行" && r0630.body.as_of === "20240630" && r0701.body.as_of === "20240701"
      && snip0630.includes("股东") && snip0701.includes("社会责任") && snip0630 !== snip0701,
    `${s0630}/${s0701} snip=${snip0630.slice(0, 20)}…/${snip0701.slice(0, 20)}…`);
  check("B6 as_of 透传（引擎拒绝缺省猜时点——两时点回显分立）", r0630.body.as_of === "20240630" && r0701.body.as_of === "20240701");
  // 类案三案：命中/案由过滤/0 结果重试
  const c1 = await mcpCall("juscite_case_search", { query: "借款 还款 证明", cause_of_action: ["测试借款"], return_num: 6 });
  check("B7 类案命中（return_num 缺省档 6；夹具两卡全中）", !c1.isError && c1.body.hit_count === 2 && c1.body.return_num === 6, JSON.stringify(c1.body).slice(0, 160));
  check("B8 裁判日期下限（2024-07-01 缺省；夹具 2026-01-01 通过）", c1.body.hits?.every((h) => h.judge_date >= "2024-07-01"));
  const c2 = await mcpCall("juscite_case_search", { query: "还款 证明", cause_of_action: ["不存在的案由"] });
  check("B9 0 结果重试一次（去案由过滤+扩量 10+泛化）", !c2.isError && c2.body.retried_no_cause === true && c2.body.hit_count >= 1, JSON.stringify({ retried: c2.body.retried_no_cause, hits: c2.body.hit_count }));
  const c3 = await mcpCall("juscite_case_search", { query: "", });
  check("B10 缺参具名拒（query 必填 fail-closed）", c3.isError && c3.body.code === "query_required");
  // 夹具缺位字段如实标 null（不编造法院/案号）
  check("B11 法院/案号字段位在而夹具缺位=null 如实标", c1.body.hits?.every((h) => h.court === null && h.case_number === null));
}

// ── C 权限门实弹（oc28:43127 真往返）──
console.log("== C 权限门（port setPermissionGate 实弹）==");
{
  const client = makeClient(loadCredentials());
  const base = loadCredentials().baseUrl;
  const headers = loadCredentials().headers;
  const sid = "ses_g6_gate_probe_" + Date.now().toString(36);
  await runtime.createSession({ sessionId: sid, workspacePath: "C:\\Users\\being", title: "G6 权限门探针（合成）", model: { providerId: "deepseek-byok", modelId: "deepseek-chat" } });
  // 会话级 ask 规则（后置胜出）：一域词工具（应放行）一未知工具（应拒）
  const patch = await fetch(`${base}/api/session/${encodeURIComponent(sid)}`, { method: "PATCH", headers, body: JSON.stringify({ permissions: [
    { action: "juscite_g6_juscite_statute_check", resource: "*", effect: "ask" },
    { action: "probe_unknown_tool", resource: "*", effect: "ask" },
  ] }) });
  check("C1 会话级 ask 规则写入（session.patch permissions）", patch.status === 200 || patch.status === 204, `${patch.status} ${(await patch.text()).slice(0, 120)}`);
  const gateCalls = [];
  runtime.setPermissionGate((request) => {
    const domainTool = request.tool.startsWith("juscite_g6_") ? request.tool.slice("juscite_g6_".length) : request.tool;
    const d = decideToolCall({ toolName: domainTool, args: {}, permissionMode: "smart", shellEnabled: false });
    gateCalls.push({ tool: request.tool, domainTool, effect: d.effect, code: d.code });
    return d.effect === "allow"; // 域词白名单放行；未知工具 ask→按拒（fail-closed，同桥面接线）
  });
  const mk = async (action) => (await fetch(`${base}/api/session/${encodeURIComponent(sid)}/permission`, { method: "POST", headers, body: JSON.stringify({ action, resources: ["*"] }) })).json();
  const a1 = await mk("juscite_g6_juscite_statute_check");
  const a2 = await mk("probe_unknown_tool");
  check("C2 oc28 权限评估落 ask（两条 pending 创建）", a1?.data?.effect === "ask" && a2?.data?.effect === "ask", JSON.stringify([a1?.data?.effect, a2?.data?.effect]));
  await sleep(4000); // 等事件流回调+应答
  check("C3 权限门回调两达（oc28 事件→port gate）", gateCalls.length >= 2, JSON.stringify(gateCalls));
  const allowRow = gateCalls.find((g) => g.domainTool === "juscite_statute_check");
  const denyRow = gateCalls.find((g) => g.tool === "probe_unknown_tool");
  check("C4 域词还原+白名单放行（juscite_statute_check→allow/read_only）", allowRow?.effect === "allow" && allowRow?.code === "read_only");
  check("C5 未知工具 fail-closed 拒（unknown_tool→reject 应答）", denyRow?.effect === "ask" || denyRow?.code === "unknown_tool", JSON.stringify(denyRow));
  const pending = await (await fetch(`${base}/api/permission/request`, { headers })).json();
  const stillPending = (pending?.data ?? []).filter((r) => r?.sessionID === sid);
  check("C6 应答后 pending 清空（once/reject 均落定）", stillPending.length === 0, JSON.stringify(stillPending.map((r) => r.action)));
  runtime.setPermissionGate(null); // 关闸（探针不留门）
}

// ── D 差异表 + 清场 ──
console.log("== D 对拍差异表（华宇元典 MCP 机制笔记 vs 我方 G6 连接器实测）==");
const DIFF = [
  ["法条核验入参", "全部待引法条编号+核心内容组成单个自然语言 query", "同形（query 单串，引擎逐条解析）", "等量"],
  ["法源过滤", "限现行有效+四类法源（法律/司法解释/行政法规/部门规章）", "包内 43 部（含宪法/组织法等），效力按施行窗口推导；不做四类过滤", "我方收窄差异：数据面=轻量包，过滤维度未对齐（如实记）"],
  ["核验时点", "未记（笔记未提时点参数）", "as_of 可指定（B6 实测 20240630/20240701 两点决策可分）", "我方更细（RE-14 G6 承接）"],
  ["公司法新旧条号核对", "核对条号新旧公司法是否一致", "同条号跨版本内容切换（B4：as_of 20240630=2018 版「股东滥用」条款/20240701=2024 版「社会责任」条款，同条号两文可对照）；同名义务链后继在包内以施行窗衔接（2018 版 valid_to=2024 版 valid_from）", "等量（机制口径：时点切换+版本窗衔接，非条号映射表）"],
  ["类案时间窗", "仅 2024-07-01 之后裁判的民事案件", "judge_date_after 缺省 2024-07-01（B8 夹具 2026-01-01 通过；可参数化）", "等量（缺省同日，我方可调）"],
  ["案由映射表", "案由按纠纷类型映射表选取可并行多传（股东出资→加传股东损害债权人利益等）", "cause_of_action 数组并行多传（机制在）；映射表本体不内置（合成夹具无映射数据）", "部分等量：并行机制等量，映射知识缺位如实记"],
  ["return_num", "一次调用 return_num=6（另件 vector_search 缺省 45/强制 5/工作流 15/10/15 三处不一致以工作流为准）", "缺省 6（B7），≤20 封顶", "等量（我方单值无档位分裂）"],
  ["权威案例优先", "不分权威与普通检索，输出优先权威且至少列示 3 个", "lcr 命中一律 authority_status=CASE_SOURCE_CANDIDATE 不分级（lcr 铁律：检索结果是来源候选不是事实）", "我方收窄：不承诺权威分级（红线侧收窄，非缺陷）"],
  ["输出字段", "法院名称+案号+裁判日期+裁判要点", "行字段位同构（court/case_number/judge_date/summary）；合成夹具无法院/案号→null 如实标（B11）", "形状等量，数据缺位如实标注"],
  ["余额前置", "首次调用前查余额，不足整体跳过并说明", "本地库零成本，无余额面", "差异（我方无付费面，缺省免检）"],
  ["0 结果重试", "移除案由过滤+return_num 扩至 10+关键词泛化重试一次", "同机制（B9：retried_no_cause=true，去案由+扩量+确定性泛化）", "等量"],
  ["管辖约束", "未确认管辖地不得发起地域检索、不设默认管辖地", "连接器无地域检索参数（缺席即无默认值）", "等量（安全缺席）"],
  ["第三方实弹", "华宇元典=外部商业 MCP（本机无凭据/无端点）——未实弹，仅 readable 机制笔记参照", "我方真源（LCCC 轻量包+lcr 合成夹具库）实弹全分支", "差异表本行如实记录：第三方面 UNKNOWN 不编造"],
];
for (const [dim, theirs, ours, verdict] of DIFF) console.log(`| ${dim} | ${theirs} | ${ours} | ${verdict} |`);
console.log(`（差异表 ${DIFF.length} 行；第三方源=竞品情报 readable 件 cn-case-retrieval-mcp/cn-yuandian-case-search 机制笔记）`);

// 清场：撤挂载（resident 桥下次启动自动重注册）；删会话；临时目录留证（路径打印）
{
  const client = makeClient(loadCredentials());
  const base = loadCredentials().baseUrl;
  const headers = loadCredentials().headers;
  try { await client.mcpRemove("juscite-g6"); console.log("[cleanup] experimental mcp juscite-g6 已撤（runtime-only，不落配置）"); } catch (e) { console.log("[cleanup] mcpRemove:", e?.message ?? e); }
  for (const sid of [/* C 段会话已逐条删除? 保留给排查，逐条删 */]) { /* noop */ }
  // C 段会话清理：按前缀列出删除
  try {
    const list = await (await fetch(`${base}/api/session`, { headers })).json();
    for (const s of list?.data ?? []) {
      if (String(s?.id ?? "").startsWith("ses_g6_gate_probe_")) await fetch(`${base}/api/session/${encodeURIComponent(s.id)}`, { method: "DELETE", headers });
    }
  } catch { /* 会话清理失败不判 FAIL（探针会话残留无害） */ }
}
console.log(`\nG6 对拍结果：pass=${pass} fail=${fail}${fail ? "；失败项：" + failures.join(" / ") : ""}`);
console.log(`探针临时件（连接器 MCP 日志/合成 lcr 库）：${TMP}`);
if (fail === 0) console.log("G6_CONNECTOR_SYNTH_PASS");
process.exit(fail === 0 ? 0 : 1);
