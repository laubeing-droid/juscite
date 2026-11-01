// 【步骤4·#5 冲突查重】合成自测（RE-5-冲突查重.md §2 行为清单+§3 实现规格；全部合成材料）：
//   纯模型段 E1-E21：归一化四例/33 地域前缀/探针门槛/四级匹配/严重度矩阵+证件升+归一降/互含恒 LOW/
//   去重留最高+双命中保留/条件构造消并/预检规范化/正式缺 role 拒/指纹键序/H5 判定核/
//   审批角色标签 B1/审批命中方式四分 E5/F10 覆盖比对核/G2 送审五查核/严格重跑比对/F7 冻结/G4 转案八条核；
//   桥面段 P1-P19：当事人登记与 F8 授权先行/盲索引/预检与案件复核双形态/自动结论/结论四态/
//   高风险备注闸 F5/指纹失效 F6/非最新拒 F6/复核卡动作 H1-H4/软删客户/收案形态 fail-closed/
//   杀桥重启持久化/审计事件族/在办收案命中外发剥 ID（E2，DB 直播种）/剥层不伤内部重跑比对。
// 隔离桥自管实例（CONFLICT_TEST_PORT 默认 3080，独立库），不碰 :3030/:43127。
// 末行 CONFLICT_SYNTH_PASS / CONFLICT_SYNTH_FAIL。
import { spawn, spawnSync } from "node:child_process";
import { openSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import WebSocket from "ws";
import { VSBuffer, SocketProtocol, ChannelClient } from "@zcode/rpc";
// 纯模型直接对拍（与桥同一来源文件）
import {
  normalizeOrgName, buildNameProbes, REGION_PREFIXES, nameMatchLevel, pickSeverity,
  bumpForIdMatch, downgradeForNormalized, severityOfNameHit, dedupeHits, sortHitsDesc,
  buildConflictQueries, normalizePrecheckQueries, normalizeFormalQueries, fingerprintPayload, reviewGateOutcome,
  ROLES, ROLE_LABEL, HIT_ROLE_LABEL, APPROVAL_ROLE_LABEL, matchKindOfApproval, APPROVAL_MATCH_KIND_LABEL,
  conflictQueryCoverage, intakeSubmitGateOutcome, rerunChangedCount, intakeFrozenForConclusion, intakeConvertGateOutcome,
  AUTO_NOTE_REVIEW,
} from "../../packages/juscite-legal/src/kernel/conflictModel.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.CONFLICT_TEST_PORT ?? 3080);
const NODE = process.execPath;
const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`[conflict-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function dbPath() { return join(process.env.APPDATA ?? "", "Juscite", "bridge", `bridge-${PORT}.db`); }
function openDb() { return new DatabaseSync(dbPath()); }

let bridgePid = 0;
const bridgeLog = openSync(join(REPO_ROOT, ".local", `conflict-synth-bridge-${PORT}.log`), "a");
function spawnBridge() {
  const env = { ...process.env, BRIDGE_PORT: String(PORT) };
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
async function waitProbe(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) { if (await probe()) return true; await sleep(500); }
  return false;
}
async function commandLineOf(pid) {
  const r = spawnSync("powershell.exe", ["-NoProfile", "-Command",
    `(Get-CimInstance Win32_Process -Filter "ProcessId=${pid}").CommandLine`],
    { encoding: "utf-8", timeout: 20000 });
  return String(r.stdout ?? "").trim();
}
function findListenerPids(port) {
  const r = spawnSync("netstat", ["-ano"], { encoding: "utf-8", timeout: 15000 });
  const pids = new Set();
  for (const m of String(r.stdout ?? "").matchAll(/\sTCP\s+\S*:(\d+)\s+\S+\s+LISTENING\s+(\d+)/g)) {
    if (Number(m[1]) === port) pids.add(Number(m[2]));
  }
  return [...pids];
}
async function killBridge(reason) {
  const line = await commandLineOf(bridgePid);
  if (!line.includes("bridge_host.mjs")) {
    throw new Error(`拒绝杀进程 pid=${bridgePid}（${reason}）：命令行不含 bridge_host.mjs，宁停不误杀`);
  }
  spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probe())) await sleep(500);
}
async function clearStaleBridge() {
  for (const pid of findListenerPids(PORT)) {
    const line = await commandLineOf(pid);
    if (!line.includes("bridge_host.mjs")) {
      throw new Error(`:${PORT} 被非桥进程占用（pid=${pid}），不接触`);
    }
    console.log(`[conflict-synth] 清残留桥 pid=${pid}`);
    spawnSync("taskkill", ["/PID", String(pid), "/F", "/T"], { timeout: 15000 });
  }
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline && (await probe())) await sleep(500);
}
async function callExpectError(name, params) {
  try { await call(name, params); return { threw: false, message: "" }; }
  catch (e) { return { threw: true, message: String(e?.message ?? e) }; }
}

let ch = null;
async function connect() {
  const ws = new WebSocket(`ws://127.0.0.1:${PORT}/ws`);
  ws.binaryType = "arraybuffer";
  const data = { fire: (_b) => {} };
  ws.on("message", (buf) => data.fire(VSBuffer.wrap(new Uint8Array(buf))));
  await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
  const isocket = {
    onData: (l) => { data.fire = l; return { dispose: () => {} }; },
    onClose: () => ({ dispose: () => {} }),
    onEnd: () => ({ dispose: () => {} }),
    write: (b) => ws.send(b.buffer),
    end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
  };
  ch = new ChannelClient(new SocketProtocol(isocket)).getChannel("zcode-agent");
  await ch.call("helloConversationV4", []);
}
const call = (m, a) => ch.call(m, a === undefined ? [] : [a]);

// ═══ 纯模型段（E 组）═══
{
  // E1 归一化保守变换四例（C6 实测口径：全角/括号段/迭代剥后缀/去地域不自动）
  check("E1 归一化四例（嘉吉贸易有限责任公司→嘉吉贸易/嘉吉（广州）→嘉吉/ＡＢＣ（上海）股份→abc/广东嘉吉贸易→广东嘉吉贸易）",
    normalizeOrgName("嘉吉贸易有限责任公司") === "嘉吉贸易"
    && normalizeOrgName("嘉吉（广州）有限公司") === "嘉吉"
    && normalizeOrgName("ＡＢＣ（上海）股份有限公司") === "abc"
    && normalizeOrgName("广东嘉吉贸易有限公司") === "广东嘉吉贸易",
    [normalizeOrgName("嘉吉贸易有限责任公司"), normalizeOrgName("嘉吉（广州）有限公司"),
      normalizeOrgName("ＡＢＣ（上海）股份有限公司"), normalizeOrgName("广东嘉吉贸易有限公司")].join("/"));
  // 分支机构不剥（独立主体）
  check("E1b 分公司/分店不剥", normalizeOrgName("合成贸易上海分公司") === "合成贸易上海分公司",
    normalizeOrgName("合成贸易上海分公司"));
  // E2 地域前缀 33 项无台湾；去地域核探针（≥3 字）
  check("E2 REGION_PREFIXES=33 且无台湾", REGION_PREFIXES.length === 33 && !REGION_PREFIXES.includes("台湾"),
    `n=${REGION_PREFIXES.length}`);
  check("E2b 去地域探针", JSON.stringify(buildNameProbes("广东嘉吉贸易有限公司")) === JSON.stringify(["广东嘉吉贸易有限公司", "广东嘉吉贸易", "嘉吉贸易"]),
    JSON.stringify(buildNameProbes("广东嘉吉贸易有限公司")));
  // E3 探针门槛：2 字名无模糊探针
  check("E3 2 字名无探针（张三）", buildNameProbes("张三").length === 0,
    JSON.stringify(buildNameProbes("张三")));
  // E4 四级双向匹配
  const m1 = nameMatchLevel("嘉吉贸易有限责任公司", "嘉吉贸易有限公司");
  const m2 = nameMatchLevel("合成甲律所", "合成甲律所");
  const m3 = nameMatchLevel("广东嘉吉贸易有限公司", "嘉吉贸易有限公司");
  const m4 = nameMatchLevel("嘉吉集团", "嘉吉贸易集团");
  const m5 = nameMatchLevel("完全无关名", "另一个名字");
  check("E4 四级匹配（NORM_EQUAL/EXACT/CONTAINS 比率/NORM_CONTAINS/null）",
    m1?.level === "NORMALIZED_EQUAL" && m2?.level === "EXACT"
    && m3?.level === "CONTAINS" && Math.abs(m3.ratio - 0.8) < 1e-9
    && m4?.level === "NORMALIZED_CONTAINS"
    && m5 === null,
    JSON.stringify([m1, m2, m3, m4, m5]));
  // E5 严重度矩阵 7 格+兜底（D1-D4）
  check("E5 矩阵 7 格（C×O=HIGH/O×C=BLOCKING/O×O=LOW/C×C=LOW/T×any=MEDIUM×3/兜底 MEDIUM）",
    pickSeverity("CLIENT", "OPPOSING_PARTY") === "HIGH"
    && pickSeverity("OPPOSING_PARTY", "CLIENT") === "BLOCKING"
    && pickSeverity("OPPOSING_PARTY", "OPPOSING_PARTY") === "LOW"
    && pickSeverity("CLIENT", "CLIENT") === "LOW"
    && pickSeverity("THIRD_PARTY", "CLIENT") === "MEDIUM"
    && pickSeverity("CLIENT", "THIRD_PARTY") === "MEDIUM"
    && pickSeverity("AGENT", "WITNESS") === "MEDIUM");
  // E6 证件一致升 1 封顶（D5）
  check("E6 证件 bump（LOW→MEDIUM/BLOCKING 封顶）",
    bumpForIdMatch("LOW") === "MEDIUM" && bumpForIdMatch("HIGH") === "BLOCKING" && bumpForIdMatch("BLOCKING") === "BLOCKING");
  // E7 归一降 1 地板 LOW（D6）
  check("E7 归一 downgrade（BLOCKING→HIGH/LOW 地板）",
    downgradeForNormalized("BLOCKING") === "HIGH" && downgradeForNormalized("LOW") === "LOW");
  // E8 原文互含恒 LOW；归一判定先于互含（D7：存储名是查询名子串→CONTAINS 不降级标注）
  check("E8 互含恒 LOW+归一先于互含",
    severityOfNameHit("CONTAINS", "OPPOSING_PARTY", "CLIENT") === "LOW"
    && severityOfNameHit("NORMALIZED_CONTAINS", "OPPOSING_PARTY", "CLIENT") === "LOW"
    && severityOfNameHit("NORMALIZED_EQUAL", "OPPOSING_PARTY", "CLIENT") === "HIGH"
    && severityOfNameHit("EXACT", "OPPOSING_PARTY", "CLIENT") === "BLOCKING");
  // E9 去重留最高+同主体名/证件双命中保留+降序（D8）
  const mk = (field, sev, val) => ({
    hitType: "HISTORICAL_PARTY", targetType: "matter", targetId: "T1", matchedName: "合成甲",
    matchedField: field, matchedValue: val, matchedRatio: 1, matchLevel: field === "name" ? "EXACT" : null,
    severity: sev, reason: "", storedRole: "OPPOSING_PARTY", storedStanding: null,
  });
  const dedup = sortHitsDesc(dedupeHits([mk("name", "HIGH", "合成甲"), mk("name", "LOW", "合成甲"), mk("idNumber", "BLOCKING", "X1")]));
  check("E9 去重留最高+双命中保留+降序",
    dedup.length === 2 && dedup[0].severity === "BLOCKING" && dedup[1].severity === "HIGH",
    JSON.stringify(dedup.map((h) => [h.matchedField, h.severity])));
  // E10 条件构造：委托方缺 Party 行则补+同名同角色带证件消并
  const q1 = buildConflictQueries({ name: "合成委托公司", idNumber: "X1" }, [
    { role: "OPPOSING_PARTY", name: "合成对手" }, { role: "OPPOSING_PARTY", name: "合成对手", idNumber: "X2" },
  ]);
  check("E10 条件构造（补委托方+同名同角色消并）",
    q1.length === 2 && q1[0].role === "CLIENT" && q1[0].name === "合成委托公司"
    && q1[1].role === "OPPOSING_PARTY" && q1[1].idNumber === "X2",
    JSON.stringify(q1));
  // E11 预检规范化：空行过滤/全空拦/缺省对方/证件大写
  const nq1 = normalizePrecheckQueries([{ name: "合成甲", idNumber: " x9 " }, {}]);
  const nq2 = normalizePrecheckQueries([{ name: "  " }]);
  check("E11 预检规范化（空行滤/全空拦/缺省对方/证件归一）",
    nq1.queries.length === 1 && nq1.queries[0].role === "OPPOSING_PARTY" && nq1.queries[0].idNumber === "X9"
    && nq2.error !== null && nq1.error === null,
    JSON.stringify([nq1, nq2]));
  // E12 正式检索缺 role 拒（B3）
  check("E12 正式缺 role 拒", normalizeFormalQueries([{ name: "合成甲" }]).error !== null
    && normalizeFormalQueries([{ role: "CLIENT", name: "合成甲" }]).error === null);
  // E13 指纹载荷键序稳定（跨对象键序漂移）
  check("E13 指纹载荷键序稳定", fingerprintPayload({ b: 1, a: 2 }) === fingerprintPayload({ a: 2, b: 1 }));
  // E14 H5 写路径门禁判定核（对拍 32）：三段次序=无记录∨漂移＞未过＞新增命中
  check("E14 H5 判定核（无记录/漂移→STALE＞未过→NOT_PASSED＞新增命中→NEW_HITS＞ok）",
    reviewGateOutcome({ hasRecord: false, fingerprintCurrent: false, conclusion: null, newHitCount: 0 }) === "STALE"
    && reviewGateOutcome({ hasRecord: true, fingerprintCurrent: false, conclusion: "DIFFERENT", newHitCount: 2 }) === "STALE"
    && reviewGateOutcome({ hasRecord: true, fingerprintCurrent: true, conclusion: "PENDING", newHitCount: 1 }) === "NOT_PASSED"
    && reviewGateOutcome({ hasRecord: true, fingerprintCurrent: true, conclusion: "DIFFERENT", newHitCount: 1 }) === "NEW_HITS"
    && reviewGateOutcome({ hasRecord: true, fingerprintCurrent: true, conclusion: "DIFFERENT", newHitCount: 0 }) === "ok");
  // E15 B1 审批侧第三套角色标签（r9 件4）：七值闭集；OPPOSING_PARTY=对方（预检页=对方当事人）；OTHER=其他
  check("E15 审批角色标签（OPPOSING_PARTY=对方≠预检面对方当事人；OTHER=其他≠reason 面当事人；七值全覆盖）",
    APPROVAL_ROLE_LABEL.OPPOSING_PARTY === "对方" && APPROVAL_ROLE_LABEL.OTHER === "其他"
    && HIT_ROLE_LABEL.OPPOSING_PARTY === "对方当事人" && ROLE_LABEL.OTHER === "当事人"
    && ROLES.every((r) => typeof APPROVAL_ROLE_LABEL[r] === "string" && APPROVAL_ROLE_LABEL[r].length > 0));
  // E16 E5 审批侧命中方式四分（r9 件4）：证件→证件一致；EXACT→名称相同；归一/互含→名称相似；异常→其他历史匹配
  check("E16 命中方式四分（证件/EXACT/归一互含/异常档「其他历史匹配」）",
    matchKindOfApproval({ matchedField: "idNumber", matchLevel: null, matchedName: "甲", matchedValue: "X1", matchedRatio: 1 }) === "id_number"
    && matchKindOfApproval({ matchedField: "name", matchLevel: "EXACT", matchedName: "甲有限公司", matchedValue: "甲有限公司", matchedRatio: 1 }) === "name_exact"
    && matchKindOfApproval({ matchedField: "name", matchLevel: "NORMALIZED_EQUAL", matchedName: "甲有限公司", matchedValue: "甲（新）有限公司", matchedRatio: 1 }) === "name_similar"
    && matchKindOfApproval({ matchedField: "name", matchLevel: "CONTAINS", matchedName: "甲有限公司", matchedValue: "甲有限", matchedRatio: 0.75 }) === "name_similar"
    && matchKindOfApproval({ matchedField: "name", matchLevel: null, matchedName: "甲", matchedValue: "乙", matchedRatio: null }) === "name_similar"
    && matchKindOfApproval({ matchedField: "standing", matchLevel: null, matchedName: "", matchedValue: "", matchedRatio: null }) === "other"
    && APPROVAL_MATCH_KIND_LABEL.other === "其他历史匹配" && APPROVAL_MATCH_KIND_LABEL.name_exact === "名称相同");
  // E17 F10 覆盖比对核（r9 件4）：齐=ok；存档档无可比对=incomplete；当事人已变更=missing 列举
  const cov1 = conflictQueryCoverage(
    [{ role: "CLIENT", name: "甲公司", idNumber: "X1" }, { role: "OPPOSING_PARTY", name: "乙公司", idNumber: "" }],
    [{ role: "CLIENT", name: "甲公司 ", idNumber: "X1" }, { role: "OPPOSING_PARTY", name: "乙公司", idNumber: "" }]);
  const cov2 = conflictQueryCoverage([{ role: "CLIENT", name: "甲公司", idNumber: "X1" }], []);
  const cov3 = conflictQueryCoverage(
    [{ role: "CLIENT", name: "甲新公司", idNumber: "" }],
    [{ role: "CLIENT", name: "甲公司", idNumber: "X1" }]);
  const cov4 = conflictQueryCoverage([], [{ role: "CLIENT", name: "甲公司", idNumber: "" }]);
  check("E17 F10 覆盖比对（齐=ok/存档空=incomplete/变更=missing 列举/当前空=双否）",
    cov1.ok && !cov1.incomplete && cov1.missing.length === 0
    && !cov2.ok && cov2.incomplete && cov2.missing.length === 1
    && !cov3.ok && !cov3.incomplete && cov3.missing.length === 1 && cov3.missing[0].includes("甲新公司") && cov3.missing[0].includes("委托方")
    && !cov4.ok && !cov4.incomplete && cov4.missing.length === 0);
  // E18 G2 送审五查判定核次序（r9 件4）：无检索→指纹失效→结论未承接→命中无备注→重跑新命中→ok；
  // requireConclusion=false（送审闸形态）不查结论/备注
  check("E18 G2 五查次序（NO_CHECK→STALE→NOT_DIFFERENT→NOTE_REQUIRED→NEW_HITS→ok；送审形态跳过结论备注查）",
    intakeSubmitGateOutcome({ hasCheck: false, fingerprintCurrent: false, requireConclusion: true, conclusion: null, hasHits: false, noteNonEmpty: false, changedHitCount: 0 }) === "NO_CHECK"
    && intakeSubmitGateOutcome({ hasCheck: true, fingerprintCurrent: false, requireConclusion: true, conclusion: "DIFFERENT", hasHits: false, noteNonEmpty: false, changedHitCount: 0 }) === "STALE"
    && intakeSubmitGateOutcome({ hasCheck: true, fingerprintCurrent: true, requireConclusion: true, conclusion: "PENDING", hasHits: true, noteNonEmpty: false, changedHitCount: 0 }) === "NOT_DIFFERENT"
    && intakeSubmitGateOutcome({ hasCheck: true, fingerprintCurrent: true, requireConclusion: true, conclusion: "DIFFERENT", hasHits: true, noteNonEmpty: false, changedHitCount: 0 }) === "NOTE_REQUIRED"
    && intakeSubmitGateOutcome({ hasCheck: true, fingerprintCurrent: true, requireConclusion: true, conclusion: "DIFFERENT", hasHits: true, noteNonEmpty: true, changedHitCount: 2 }) === "NEW_HITS"
    && intakeSubmitGateOutcome({ hasCheck: true, fingerprintCurrent: true, requireConclusion: true, conclusion: "DIFFERENT", hasHits: true, noteNonEmpty: true, changedHitCount: 0 }) === "ok"
    && intakeSubmitGateOutcome({ hasCheck: true, fingerprintCurrent: false, requireConclusion: false, conclusion: "PENDING", hasHits: true, noteNonEmpty: false, changedHitCount: 0 }) === "STALE");
  // E19 G2 当场重跑严格比对（键+严重度+reason 三元签名；r9 件4）：同键变严重度/变 reason=新；全同集合=0
  const rp = (sev: string, reason: string) => ({ targetId: "T1", matchedField: "name" as const, matchedValue: "甲", matchedName: "甲", severity: sev as never, reason });
  check("E19 严格重跑比对（变严重度=1/变 reason=1/集合全同=0）",
    rerunChangedCount([rp("LOW", "r")], [rp("HIGH", "r")]) === 1
    && rerunChangedCount([rp("LOW", "r")], [rp("LOW", "r2")]) === 1
    && rerunChangedCount([rp("LOW", "r"), rp("HIGH", "r2")], [rp("HIGH", "r2"), rp("LOW", "r")]) === 0);
  // E20 F7 送审冻结判定（r9 件4）：待审批态不可改结论
  check("E20 F7 冻结（PENDING_CONFIRMATION=true/INTAKE·NEEDS_REVISION·null=false）",
    intakeFrozenForConclusion("PENDING_CONFIRMATION") && !intakeFrozenForConclusion("INTAKE")
    && !intakeFrozenForConclusion("NEEDS_REVISION") && !intakeFrozenForConclusion(null));
  // E20b G4 转案内容闸判定核八条次序（r9 件4）
  const g4 = (over: Partial<Parameters<typeof intakeConvertGateOutcome>[0]> = {}) => intakeConvertGateOutcome({
    queryCount: 2, hasCheck: true, coverage: { ok: true, incomplete: false, missing: [] },
    conclusion: "DIFFERENT", hasHighOrBlocking: true, noteNonEmpty: true, ...over });
  check("E20b G4 八条次序（无当事人→无检索→条件不齐→PENDING→NEED_INFO→SAME_SUBJECT→异常兜底→高风险无备注→ok）",
    g4({ queryCount: 0 }) === "NO_PARTIES"
    && g4({ hasCheck: false }) === "NO_CHECK"
    && g4({ coverage: { ok: false, incomplete: true, missing: [] } }) === "COVERAGE_MISSING"
    && g4({ conclusion: "PENDING" }) === "PENDING"
    && g4({ conclusion: "NEED_INFO" }) === "NEED_INFO"
    && g4({ conclusion: "SAME_SUBJECT" }) === "SAME_SUBJECT"
    && g4({ conclusion: "SOMETHING_ELSE" }) === "ABNORMAL"
    && g4({ noteNonEmpty: false }) === "NOTE_REQUIRED"
    && g4() === "ok");
}

// ═══ 桥面段（P 组，隔离桥 :3080）═══
try {
  await clearStaleBridge();
  for (const suffix of ["", "-wal", "-shm"]) {
    try { unlinkSync(dbPath() + suffix); } catch { /* 不存在即可 */ }
  }
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error(`隔离桥 :${PORT} 40s 不可探`);
  await connect();

  // P1 历史案两件+当事人登记 round-trip+登记负测（角色越界/空名/F8 不存在案件）
  const h1 = await call("matterCreate", { name: "合成历史案·对手档案", cause: "合同纠纷" });
  const h2 = await call("matterCreate", { name: "合成历史案·客户档案", cause: "借贷纠纷" });
  const h3 = await call("matterCreate", { name: "合成历史案·后建对手", cause: "侵权纠纷" });
  const m1 = await call("matterCreate", { name: "合成在办案·拟承接", cause: "合同纠纷" });
  const m2 = await call("matterCreate", { name: "合成在办案·指纹失效", cause: "劳动争议" });
  const m3 = await call("matterCreate", { name: "合成在办案·零命中", cause: "知识产权" });
  const ps1 = await call("conflictPartySet", { subjectType: "matter", subjectId: h1.id, parties: [
    { role: "OPPOSING_PARTY", name: "合成对手甲有限公司", idNumber: "X110001" },
    { role: "CLIENT", name: "合成嘉吉贸易有限公司", idNumber: "X120001" },
  ] });
  check("P1 当事人登记 round-trip", ps1.parties.length === 2 && ps1.parties[0].role === "OPPOSING_PARTY"
    && ps1.parties[1].name === "合成嘉吉贸易有限公司",
    `n=${ps1.parties.length}`);
  const badRole = await callExpectError("conflictPartySet", { subjectType: "matter", subjectId: h1.id, parties: [{ role: "BOSS", name: "合成X" }] });
  const badName = await callExpectError("conflictPartySet", { subjectType: "matter", subjectId: h1.id, parties: [{ role: "CLIENT", name: " " }] });
  const badSubject = await callExpectError("conflictPartySet", { subjectType: "matter", subjectId: "matter_no_such", parties: [{ role: "CLIENT", name: "合成X" }] });
  check("P1b 登记负测（角色越界/空名/不存在案件 F8 显式拒）",
    badRole.threw && badName.threw && badSubject.threw && badSubject.message.includes("不存在或无权"),
    [badRole.message, badName.message, badSubject.message].join(" | "));

  // P2 客户档案：盲索引列在库（hex）、列表不回盲文；关联案件两件
  const up1 = await call("conflictClientUpsert", { name: "合成对家公司乙", idNumber: "x913001", matterIds: [h2.id] });
  const up2 = await call("conflictClientUpsert", { name: "合成客户丙", idNumber: "X913002", matterIds: [h2.id, h3.id] });
  const iso = await call("conflictClientUpsert", { name: "合成孤立客户丁", idNumber: "X913003", matterIds: [] });
  const { execSync } = await import("node:child_process");
  const blindCol = openDb().prepare("SELECT id_blind FROM conflict_clients WHERE id = ?").get(up1.client.id);
  check("P2 客户档案 upsert+盲索引在库（64 hex）+列表不带盲文",
    Boolean(up1.client.id) && /^[0-9a-f]{64}$/.test(blindCol?.id_blind ?? "") && up1.client.matterIds.length === 1,
    `blind=${String(blindCol?.id_blind ?? "").slice(0, 12)}…`);
  const cl = await call("conflictClientList");
  check("P2b 客户列表无盲文泄漏", cl.clients.length === 3 && !("idBlind" in cl.clients[0]) && !("id_blind" in cl.clients[0]),
    `n=${cl.clients.length}`);
  void execSync; void iso;

  // P3 预检：精确机构命中 HIGH（C×O）+归一化 BLOCKING→HIGH 降级+人工核对标注（D6）
  //（归一例用差括号名：探针「合成嘉吉贸易」命中存档→归一双向比对分级，C5/D6）
  const pre1 = await call("conflictRun", { queries: [
    { role: "CLIENT", name: "合成对手甲有限公司" },
    { role: "OPPOSING_PARTY", name: "合成嘉吉（广州）贸易有限公司" }, // 存档=合成嘉吉贸易有限公司 CLIENT → 归一相等（合成嘉吉贸易）BLOCKING→HIGH
  ] });
  const g1 = pre1.check.hits.filter((x) => x.matchedName === "合成对手甲有限公司");
  const g2 = pre1.check.hits.filter((x) => x.matchedName === "合成嘉吉贸易有限公司");
  check("P3 预检精确命中 HIGH+归一化命中降级 HIGH+人工核对 reason",
    pre1.check.conclusion === "PENDING" && g1.length === 1 && g1[0].severity === "HIGH" && g1[0].matchLevel === "EXACT"
    && g2.length === 1 && g2[0].severity === "HIGH" && g2[0].matchLevel === "NORMALIZED_EQUAL"
    && g2[0].reason.includes("人工核对"),
    JSON.stringify(pre1.check.hits.map((x) => [x.matchedName, x.severity, x.matchLevel])));
  check("P3b 命中字段全集+案件最小披露 brief（E1/E4）",
    ["hitType", "targetType", "targetId", "matchedName", "matchedField", "matchedValue", "matchedRatio",
      "matchLevel", "severity", "reason", "storedRole"].every((k) => k in g1[0])
    && g1[0].brief?.name === "合成历史案·对手档案" && g1[0].brief?.cause === "合同纠纷",
    JSON.stringify(g1[0].brief));
  check("P3c hitType/targetType=HISTORICAL_PARTY/matter", g1[0].hitType === "HISTORICAL_PARTY" && g1[0].targetType === "matter");

  // P4 双命中保留（同名+证件两条）+降序 BLOCKING 在前（D8）
  const pre2 = await call("conflictRun", { queries: [
    { role: "OPPOSING_PARTY", name: "合成对手甲有限公司", idNumber: "x110001" }, // 名称 EXACT O×O=LOW；证件 O×O LOW+1=MEDIUM
  ] });
  const dbl = pre2.check.hits.filter((x) => x.matchedName === "合成对手甲有限公司");
  check("P4 同主体名/证件双命中并存+证件升 1+降序",
    dbl.length === 2 && dbl[0].matchedField === "idNumber" && dbl[0].severity === "MEDIUM" && dbl[1].severity === "LOW",
    JSON.stringify(dbl.map((x) => [x.matchedField, x.severity])));

  // P5 预检恒 PENDING+不可下结论（F2）；零命中不自动结论
  const pre3 = await call("conflictRun", { queries: [{ name: "合成从无此人名" }] });
  const rejPre = await callExpectError("conflictConclude", { checkId: pre3.check.id, conclusion: "DIFFERENT", note: "x" });
  check("P5 预检恒 PENDING+conclude 拒（预检不出结论）",
    pre3.check.conclusion === "PENDING" && pre3.check.automatic === false && pre3.check.hits.length === 0
    && rejPre.threw && rejPre.message.includes("预检"),
    rejPre.message);
  const preEmpty = await callExpectError("conflictRun", { queries: [] });
  check("P5b 空主体预检拦截（B2 服务端同闸）", preEmpty.threw && preEmpty.message.includes("至少填写"), preEmpty.message);

  // P6 案件复核检索：排除自身（C2）+客户回溯 BLOCKING（D2 对手×委托客户）+盲索引仅证件命中（C3）
  await call("conflictPartySet", { subjectType: "matter", subjectId: m1.id, parties: [
    { role: "OPPOSING_PARTY", name: "合成对家公司乙", idNumber: "X913001" }, // 名称+证件双命中客户档案（乙，关联 h2）
  ] });
  const mr1 = await call("conflictMatterRun", { matterId: m1.id });
  const blk = mr1.check.hits.filter((x) => x.matchedName === "合成对家公司乙");
  check("P6 客户档案回溯命中 BLOCKING（对手×委托客户 D2）+排除自身+指纹落库",
    mr1.check.conclusion === "PENDING" && blk.length >= 1 && blk[0].severity === "BLOCKING"
    && !mr1.check.hits.some((x) => x.targetId === m1.id)
    && typeof mr1.check.fingerprint === "string" && mr1.check.fingerprint.length === 64,
    JSON.stringify(mr1.check.hits.map((x) => [x.matchedName, x.severity, x.hitType])));

  // P7 零命中复核自动 DIFFERENT+自写备注+automatic 标注+结论人隐藏（F2/F9）
  await call("conflictPartySet", { subjectType: "matter", subjectId: m3.id, parties: [
    { role: "CLIENT", name: "合成零命中公司" },
  ] });
  const mr2 = await call("conflictMatterRun", { matterId: m3.id });
  // F9：自动结论在协议面隐藏 decidedBy/decidedAt（DB 内 decided_at 即时落库——P17 前的 DB 直读在 P7b 核）
  const dbMr2 = openDb().prepare("SELECT decided_at, note FROM conflict_check WHERE id = ?").get(mr2.check.id);
  check("P7 零命中自动 DIFFERENT+自动备注+automatic+decidedBy/decidedAt 协议面隐藏（DB 侧 decided_at 即时）",
    mr2.check.conclusion === "DIFFERENT" && mr2.check.note === AUTO_NOTE_REVIEW
    && mr2.check.automatic === true && mr2.check.decidedBy === null && mr2.check.decidedAt === null
    && Boolean(dbMr2?.decided_at) && dbMr2.note === AUTO_NOTE_REVIEW,
    `note=${mr2.check.note} dbAt=${String(dbMr2?.decided_at)}`);

  // P8 结论四态+高风险必填备注（F5）+人工结论后 automatic 翻 false+审计行（F3/F9/F11）
  const rejNoNote = await callExpectError("conflictConclude", { checkId: mr1.check.id, conclusion: "DIFFERENT", note: "" });
  const okCon = await call("conflictConclude", { checkId: mr1.check.id, conclusion: "DIFFERENT", note: "合成备注：已核实非同一主体，书面同意在卷。" });
  const audit1 = await call("auditList", { limit: 200 });
  const setRows = audit1.rows.filter((r) => r.action === "conflict.conclusion.set");
  check("P8 高风险 DIFFERENT 无备注拒+有备注过+人工盖 decidedBy+审计 CONCLUSION_SET",
    rejNoNote.threw && rejNoNote.message.includes("备注")
    && okCon.check.conclusion === "DIFFERENT" && okCon.check.decidedBy === "律师" && okCon.check.automatic === false
    && setRows.some((r) => r.target === mr1.check.id),
    `${rejNoNote.message} | audit=${setRows.length}`);
  const badConc = await callExpectError("conflictConclude", { checkId: mr1.check.id, conclusion: "NO_SUCH", note: "x" });
  check("P8b 结论值域四态校验", badConc.threw && badConc.message.includes("四态"), badConc.message);

  // P9 F6 指纹失效+非最新拒
  await call("conflictPartySet", { subjectType: "matter", subjectId: m2.id, parties: [{ role: "CLIENT", name: "合成指纹公司" }] });
  const mr3 = await call("conflictMatterRun", { matterId: m2.id });
  await call("conflictPartySet", { subjectType: "matter", subjectId: m2.id, parties: [{ role: "CLIENT", name: "合成指纹公司改" }] });
  const rejStale = await callExpectError("conflictConclude", { checkId: mr3.check.id, conclusion: "DIFFERENT", note: "x" });
  const mr3b = await call("conflictMatterRun", { matterId: m2.id }); // 新检索（最新）
  const rejOld = await callExpectError("conflictConclude", { checkId: mr3.check.id, conclusion: "DIFFERENT", note: "x" });
  const okLatest = await call("conflictConclude", { checkId: mr3b.check.id, conclusion: "NEED_INFO", note: "合成：待补材料" });
  check("P9 指纹失效拒+非最新拒+最新可下结论（F6）",
    rejStale.threw && rejStale.message.includes("失效")
    && rejOld.threw && rejOld.message.includes("最新")
    && okLatest.check.conclusion === "NEED_INFO",
    `${rejStale.message} | ${rejOld.message}`);

  // P10 F8 授权先行不落库（不存在案件 run/decide 拒且记录数不增）
  const before = (await call("conflictCheckList", { subjectType: "matter" })).checks.length;
  const rejRun = await callExpectError("conflictMatterRun", { matterId: "matter_no_such" });
  const rejDec = await callExpectError("conflictMatterDecide", { matterId: "matter_no_such", checkId: "cchk_x", conclusion: "DIFFERENT", note: "x" });
  const after = (await call("conflictCheckList", { subjectType: "matter" })).checks.length;
  check("P10 对象级先行不落库（F8）", rejRun.threw && rejDec.threw && before === after,
    `before=${before} after=${after} ${rejRun.message}`);

  // P11 conflictReviewState needsReview 三态（H1：无记录/指纹漂移/最新结论≠DIFFERENT）
  const rs0 = await call("conflictReviewState", { matterId: m2.id });
  await call("conflictMatterRun", { matterId: m2.id });
  const rs1 = await call("conflictReviewState", { matterId: m2.id });
  await call("conflictPartySet", { subjectType: "matter", subjectId: m2.id, parties: [{ role: "CLIENT", name: "合成指纹公司再改" }] });
  const rs2 = await call("conflictReviewState", { matterId: m2.id });
  check("P11 needsReview（无记录 true→DIFFERENT+指纹同 false→主体变 true/stale）",
    rs0.needsReview === true && rs1.needsReview === false && rs2.needsReview === true
    && rs2.reasons.includes("主体或范围已变化") && rs2.parties.length === 1,
    JSON.stringify([rs0.needsReview, rs1.needsReview, rs2.needsReview, rs2.reasons]));

  // P12 H4 复核结论：理由必填+当场重跑新增命中拦+正常过
  //（顺序关键：先出旧检索（零命中），后给历史案 h3 添对家——主体集未变（指纹同）但候选面变了）
  const mr4 = await call("conflictMatterRun", { matterId: m3.id }); // 旧命中集=空（自动 DIFFERENT）
  await call("conflictPartySet", { subjectType: "matter", subjectId: h3.id, parties: [{ role: "OPPOSING_PARTY", name: "合成零命中公司" }] });
  const rejNoNote2 = await callExpectError("conflictMatterDecide", { matterId: m3.id, checkId: mr4.check.id, conclusion: "DIFFERENT", note: "" });
  // 当场重跑：h3 新增对手「合成零命中公司」（CLIENT 面查询×新 OPPOSING=HIGH）→新增命中拦
  const rejNew = await callExpectError("conflictMatterDecide", { matterId: m3.id, checkId: mr4.check.id, conclusion: "DIFFERENT", note: "合成理由" });
  // 清掉 h3 对手后正常下结论
  await call("conflictPartySet", { subjectType: "matter", subjectId: h3.id, parties: [{ role: "CLIENT", name: "合成别家公司" }] });
  const okDec = await call("conflictMatterDecide", { matterId: m3.id, checkId: mr4.check.id, conclusion: "DIFFERENT", note: "合成复核理由：风险已核实可控。" });
  check("P12 复核结论（无备注拒/新增命中拦/正常过+审计 MATTER_DECISION）",
    rejNoNote2.threw && rejNoNote2.message.includes("理由")
    && rejNew.threw && rejNew.message.includes("新增命中")
    && okDec.check.conclusion === "DIFFERENT" && okDec.check.decidedBy === "律师",
    `${rejNoNote2.message} | ${rejNew.message}`);

  // P13 审计事件族四件（F11 同名异文等量）
  const audit2 = await call("auditList", { limit: 200 });
  const acts = new Set(audit2.rows.map((r) => r.action));
  check("P13 审计事件族（check.run/matter.run/conclusion.set/matter.decision）",
    acts.has("conflict.check.run") && acts.has("conflict.matter.run")
    && acts.has("conflict.conclusion.set") && acts.has("conflict.matter.decision"),
    [...acts].filter((a) => a.startsWith("conflict.")).join(","));

  // P14 软删客户不检+孤立客户不产出命中（C1）
  await call("conflictClientDelete", { id: up1.client.id });
  const mr5 = await call("conflictMatterRun", { matterId: m1.id }); // m1 对手=已软删客户乙
  const mr6 = await call("conflictRun", { queries: [{ role: "OPPOSING_PARTY", name: "合成孤立客户丁" }] });
  check("P14 软删客户不入检+孤立客户无命中",
    !mr5.check.hits.some((x) => x.matchedName === "合成对家公司乙")
    && mr6.check.hits.length === 0,
    JSON.stringify([mr5.check.hits.length, mr6.check.hits.length]));

  // P15 收案形态 fail-closed（实体未接入显式拒，不伪造零命中）
  const rejIntake = await callExpectError("conflictRun", { intakeId: "intake_x", queries: [{ role: "CLIENT", name: "合成甲" }] });
  const rejIntakeParty = await callExpectError("conflictPartySet", { subjectType: "intake", subjectId: "intake_x", parties: [] });
  check("P15 收案形态显式拒（P1 随 #2 接线）",
    rejIntake.threw && rejIntake.message.includes("收案") && rejIntakeParty.threw,
    `${rejIntake.message}`);

  // P16 预检列表面：全局/预检过滤
  const allPre = await call("conflictCheckList", { subjectType: "precheck", subjectId: null });
  const allMatters = await call("conflictCheckList", { subjectType: "matter" });
  check("P16 检索记录列表（precheck 全 PENDING/matter 全带主体）",
    allPre.checks.length >= 3 && allPre.checks.every((c) => c.subjectType === "precheck" && c.conclusion === "PENDING")
    && allMatters.checks.every((c) => c.subjectType === "matter" && c.subjectId),
    `pre=${allPre.checks.length} matter=${allMatters.checks.length}`);

  // ── P17 杀桥重启：记录仍在+迁移账本不重放+五表在库 ──
  const dbA = openDb();
  const migBefore = dbA.prepare("SELECT COUNT(*) AS n FROM schema_migration").get().n;
  dbA.close();
  await killBridge("P17 重启持久化");
  bridgePid = spawnBridge();
  if (!(await waitProbe(40000))) throw new Error(`重启桥 :${PORT} 40s 不可探`);
  await connect();
  const afterR = await call("conflictCheckList", {});
  const rsR = await call("conflictReviewState", { matterId: m1.id });
  const dbB = openDb();
  const migAfter = dbB.prepare("SELECT COUNT(*) AS n FROM schema_migration").get().n;
  const tables = dbB.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('matter_parties','conflict_clients','conflict_client_matters','conflict_check','conflict_hit') ORDER BY name").all().map((r) => r.name);
  dbB.close();
  check("P17 杀桥重启记录仍在+账本不重放+五表在库",
    afterR.checks.length >= 8 && rsR.parties.length === 1
    && migAfter === migBefore
    && JSON.stringify(tables) === JSON.stringify(["conflict_check", "conflict_client_matters", "conflict_clients", "conflict_hit", "matter_parties"]),
    `checks=${afterR.checks.length} mig=${migBefore}/${migAfter} tables=${tables.join(",")}`);

  // ── P18 E2 在办收案命中最小披露（r9 件4）：候选面②直播种 intake 当事人行（收案实体写入面未开放
  // ——conflictPartySet intake 显拒由 P15 守住；DB 直种=合成材料，跨连接写桥侧下次读即见）→
  // 预检命中腿②→外发面 targetId 剥空+brief 置缺（收案实体列无源不伪造）；DB 行 target_id 原值留存
  //（剥 disclosure 层不剥数据层）。矩阵腿②：O×O 名称=LOW、证件升 1=MEDIUM；O×C=BLOCKING（D2）。
  {
    const dbSeed = openDb();
    const insParty = dbSeed.prepare(
      "INSERT INTO matter_parties (id, subject_type, subject_id, role, standing, name, id_number, social_code, created_at) VALUES (?,?,?,?,?,?,?,?,?)");
    const nowIso = new Date().toISOString();
    insParty.run("pt_int_a", "intake", "int_synth_1", "OPPOSING_PARTY", null, "合成收案对家有限公司", "X700001", null, nowIso);
    insParty.run("pt_int_b", "intake", "int_synth_2", "CLIENT", null, "合成收案委托人", "X700002", null, nowIso);
    dbSeed.close();
    const preInt = await call("conflictRun", { queries: [
      { role: "OPPOSING_PARTY", name: "合成收案对家有限公司", idNumber: "x700001" },
      { role: "OPPOSING_PARTY", name: "合成收案委托人" },
    ] });
    const intakeHits = preInt.check.hits.filter((x) => x.hitType === "IN_PROGRESS_INTAKE");
    const dbIntRows = openDb().prepare(
      "SELECT target_id, hit_type FROM conflict_hit WHERE check_id = ? AND hit_type = 'IN_PROGRESS_INTAKE'").all(preInt.check.id);
    const histHit = preInt.check.hits.find((x) => x.hitType === "HISTORICAL_PARTY");
    check("P18 E2 收案命中（外发剥 ID/DB 留原值/腿②矩阵 O×O=LOW+证件 MEDIUM+O×C=BLOCKING/历史腿不受扰）",
      intakeHits.length === 3
      && intakeHits.every((x) => x.targetId === null && x.brief === null)
      && intakeHits.some((x) => x.matchedName === "合成收案委托人" && x.severity === "BLOCKING")
      && intakeHits.some((x) => x.matchedName === "合成收案对家有限公司" && x.severity === "LOW" && x.matchLevel === "EXACT")
      && intakeHits.some((x) => x.matchedField === "idNumber" && x.severity === "MEDIUM")
      && dbIntRows.length === 3 && dbIntRows.every((r) => r.target_id === "int_synth_1" || r.target_id === "int_synth_2")
      && (histHit === undefined || histHit.targetId !== null),
      JSON.stringify(preInt.check.hits.map((x) => [x.hitType, x.matchedName, x.severity, x.targetId])));

    // ── P19 剥层不伤内部比对（r9 件4）：案件当事人与在办收案当事人同名同证件→复核命中含收案腿，
    // 当场重跑（内部面保原 targetId）不误报新增命中→结论正常通过（H4/G2 前置核不被 E2 误伤）。
    const m4 = await call("matterCreate", { name: "合成在办案·收案命中不误报", cause: "合同纠纷" });
    await call("conflictPartySet", { subjectType: "matter", subjectId: m4.id, parties: [
      { role: "OPPOSING_PARTY", name: "合成收案对家有限公司", idNumber: "X700001" },
    ] });
    const mrInt = await call("conflictMatterRun", { matterId: m4.id });
    const okInt = await call("conflictMatterDecide", { matterId: m4.id, checkId: mrInt.check.id, conclusion: "DIFFERENT", note: "合成：已核实为不同主体，书面说明留存。" });
    check("P19 剥层不伤内部比对（复核命中含收案腿+外发剥 ID+当场重跑不误报+结论过）",
      mrInt.check.hits.some((x) => x.hitType === "IN_PROGRESS_INTAKE")
      && mrInt.check.hits.filter((x) => x.hitType === "IN_PROGRESS_INTAKE").every((x) => x.targetId === null)
      && okInt.check.conclusion === "DIFFERENT" && okInt.check.decidedBy === "律师",
      JSON.stringify(mrInt.check.hits.map((x) => [x.hitType, x.severity, x.targetId])));
  }
} catch (e) {
  check("用例执行", false, e?.message ?? String(e));
} finally {
  try { await call("dispose"); } catch { /* 断连即可 */ }
  if (bridgePid) {
    try {
      if ((await commandLineOf(bridgePid)).includes("bridge_host.mjs")) {
        spawnSync("taskkill", ["/PID", String(bridgePid), "/F", "/T"], { timeout: 15000 });
      }
    } catch { /* 已死则忽略 */ }
  }
}

const pass = results.every((r) => r.ok);
console.log(pass ? "CONFLICT_SYNTH_PASS" : "CONFLICT_SYNTH_FAIL");
process.exit(pass ? 0 : 1);
