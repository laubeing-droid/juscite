// 【步骤4·#26 LAN 团队同步】合成自测（RE-26 §5 验收口径：合并/鉴权/白名单语义按探针同构断言回归；
// 双实例=同机双 teamSync 实例（自定端口+合成材料），真 HTTP+真 mDNS，全部合成数据零真实案件）。
//   P 组=纯内核（身份/签名/合并规则/状态机/权限/投影/F13 守卫/剥密）；
//   N 组=HTTP 传输约束与错误码语义（GET/未知路径/无鉴权/坏 body/teamId 不匹配/非团队长 join/错码/4MB）；
//   L 组=双实例全生命周期（建团/入团/配对码一次性/权限/备注接力/撤销/退团残留/移出/解散墓碑/被踢清本机/
//        单台失败不中断/mDNS 真发现）；
//   B 组=真桥进程冒烟（隔离端口拉起：迁移 0012 三表就位+server-info 应答，即桥面命令面载体）。
// 末行 TEAM_SYNTH_PASS / TEAM_SYNTH_FAIL。密钥只在进程内存，不入日志不入 git。
import { spawn, spawnSync } from "node:child_process";
import { DatabaseSync } from "node:sqlite";
import { openSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { openBridgeStore } from "./bridge_store.mjs";
import { createTeamSync } from "./team_sync_service.mjs";
import {
  TEAM_MDNS_TYPE, TEAM_HTTP_PATH_EXCHANGE, TEAM_HTTP_PATH_JOIN, TEAM_MAX_BODY_BYTES,
  makePairingCode, newTeamIdentity, newLeaderRoster, signRoster, resignRoster, memberEntryOf,
  verifyRosterSig, mergeRoster, shouldAcceptSnapshot, shouldAcceptEdit, editStatusRank,
  canViewMember, canEditMember, applyEditDecision, projectCaseSnapshot, partiesString,
  mergeSettingKeepTeam, sanitizeValueForFrontend, isWellFormedSignedRoster,
  pickMdnsInterface, isCgnatAddress,
} from "./team_sync_model.mjs";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const results: Array<{ name: string; ok: boolean; detail?: string }> = [];
function check(name: string, ok: boolean, detail = "") {
  results.push({ name, ok });
  console.log(`[team-synth] ${name}: ${ok ? "OK" : "FAIL"} ${detail}`);
}
const eq = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
async function runRoundTo(inst: ReturnType<typeof makeInstance>, target: { host: string; port: number }, tries = 3) {
  let rep: any = await (inst.svc.__test as any).runSyncRound({ targets: [target] });
  for (let i = 0; rep?.skipped && i < tries; i++) {
    await sleep(3200); // 在途后台轮（2.5s 浏览）结束再试
    rep = await (inst.svc.__test as any).runSyncRound({ targets: [target] });
  }
  return rep;
}
async function waitUntil(fn: () => boolean, label: string, timeoutMs = 12000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try { if (fn()) return true; } catch { /* 未就绪 */ }
    await sleep(200);
  }
  return false;
}
const todayStr = () => {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
};

// ── 实例工厂：独立 SQLite 库（Juscite bridge 目录按端口分库，RE-B1 F2）+内存配置文件（不碰真实 setting.json）──
function makeInstance(name: string, dbPort: number, httpPort: number) {
  let cfgRaw = "{}"; // 内存配置文件（字符串落库模拟磁盘语义：load 每次出新对象，save 整体覆写）
  const store = openBridgeStore(dbPort);
  store.teamClearAll(); // 复跑幂等：清残留团队三表
  store.db.prepare("DELETE FROM case_board_cases").run(); // 复跑幂等：清合成案件（todos/events 随 FK 级联）
  const svc = createTeamSync({
    store,
    loadSetting: () => JSON.parse(cfgRaw),
    saveSetting: (s) => { cfgRaw = JSON.stringify(s); },
    auditWrite: () => {},
    projectCaseRows: () => store.listCases().map((row: any) => ({
      id: row.id, name: row.name, caseNo: row.case_no, court: row.court, cause: row.cause,
      caseType: row.court_type, stage: row.workflow_status ?? "", filingDate: "", result: "",
      amountCents: row.claim_amount_cents, updatedAt: row.updated_at,
      plaintiffs: JSON.parse(row.plaintiffs_json || "[]"), defendants: JSON.parse(row.defendants_json || "[]"),
      thirdParties: [], calendar: [], timeline: [],
    })),
    periodMs: 600_000, browseMs: 2500, discoverMs: 3000, port: httpPort,
  });
  return { name, store, svc, get cfg() { return JSON.parse(cfgRaw); } };
}
async function waitPort(inst: ReturnType<typeof makeInstance>, timeoutMs = 8000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const st = (inst.svc.netState as any)();
    if (st.port && st.running) return st.port as number; // running=监听+mDNS 发布齐备，同步轮不再 skipped
    await sleep(100);
  }
  throw new Error(`${inst.name} 网络端口未就绪`);
}
function insertSyntheticCase(store: ReturnType<typeof openBridgeStore>, name: string) {
  const id = "mat_synth_" + Math.random().toString(36).slice(2, 8);
  store.db.prepare(`INSERT INTO case_board_cases (id, name, cause, case_no, court, court_type,
      claim_amount_cents, plaintiffs_json, defendants_json, judges_json, workflow_status, workflow_locked,
      overrides_json, sort_order, updated_at)
    VALUES (?, ?, '', '', '', '法院', 0, '[]', '[]', '[]', '审理中', 0, '{}', NULL, ?)`)
    .run(id, name, new Date().toISOString());
  return id;
}

console.log(`[team-synth] ===== P 组：纯内核 =====`);
// P01 身份形状（§3：team_id uuid；secret 双 uuid hex64；配对码 6 位数字）
const id1 = newTeamIdentity({ teamName: "合成团队", myName: "团队长甲" });
check("P01 身份形状", /^[0-9a-f]{8}-/.test(id1.teamId) && /^[0-9a-f]{64}$/.test(id1.teamSecret)
  && /^\d{6}$/.test(id1.pairingCode) && id1.role === "leader" && id1.myName === "团队长甲");
// P02 leader roster seq=1 仅自己（A5）
const ros1 = newLeaderRoster(id1);
check("P02 建团 roster seq=1 仅自己", ros1.seq === 1 && ros1.members.length === 1
  && ros1.members[0].memberId === id1.memberId && ros1.members[0].view === null);
// P03 签名正验+篡改拒（F8）
const signed1 = signRoster(ros1, id1.teamSecret);
const tampered = { roster: { ...ros1, seq: 99 }, sig: signed1.sig };
check("P03 签名验证/篡改拒收", verifyRosterSig(signed1, id1.teamSecret) && !verifyRosterSig(tampered, id1.teamSecret)
  && !verifyRosterSig(signed1, "f".repeat(64)));
// P04 mergeRoster：高 seq 收/同低 seq 拒/坏签名拒/名单无我→kicked（F8/B21/B23）
const ros2 = resignRoster(ros1, id1.teamSecret);
const mHigh = mergeRoster(signed1, ros2, id1.teamSecret, id1.memberId);
const mSame = mergeRoster(signed1, signed1, id1.teamSecret, id1.memberId);
const mBad = mergeRoster(signed1, tampered, id1.teamSecret, id1.memberId);
const noMe = resignRoster({ ...ros2.roster, members: ros2.roster.members.filter((m) => m.memberId !== id1.memberId) }, id1.teamSecret);
const mKick = mergeRoster(signed1, noMe, id1.teamSecret, id1.memberId);
check("P04 roster 合并四分支", mHigh.merged && !mHigh.kicked && !mSame.merged && !mBad.merged
  && mKick.merged && mKick.kicked);
// P05 快照合并：首见收/seq 大胜/同 seq 不覆盖（F9/B17-B20）
check("P05 快照 seq 胜负", shouldAcceptSnapshot(null, 3) && shouldAcceptSnapshot({ seq: 3 } as any, 4)
  && !shouldAcceptSnapshot({ seq: 4 } as any, 4) && !shouldAcceptSnapshot({ seq: 5 } as any, 4));
// P06 编辑合并：白名单兜底+rank 只升不降+未知状态拒（D8/A05/B33/B34）
const editBase = { id: "e1", teamId: "T", editorId: "B", editorName: "乙", targetMemberId: "A",
  caseId: "c1", caseName: "案", field: "note", value: "v", prevValue: null, createdAt: "2026-01-01", appliedAt: null };
const mk = (status: string, field = "note") => ({ ...editBase, status, field }) as any;
check("P06a 白名单兜底", !shouldAcceptEdit(null, mk("pending", "workflow_status")));
check("P06b rank 只升不降", shouldAcceptEdit(null, mk("pending"))
  && shouldAcceptEdit(mk("pending"), mk("applied")) && !shouldAcceptEdit(mk("applied"), mk("pending"))
  && shouldAcceptEdit(mk("applied"), mk("rejected")) && !shouldAcceptEdit(mk("rejected"), mk("reverted")));
check("P06c 未知 rank=-1", editStatusRank("pending") === 0 && editStatusRank("applied") === 1
  && editStatusRank("rejected") === 2 && editStatusRank("reverted") === 2 && editStatusRank("weird") === -1);
// P07 权限（E4 观察者视角：成员条目=该成员可见谁/可编辑谁）
const rosPerm = { teamId: "T", teamName: "队", seq: 5, updatedAt: "2026-01-01", members: [
  { memberId: "L", name: "长", role: "leader", view: null, edit: [] },
  { memberId: "A", name: "甲", role: "member", view: null, edit: [] },
  { memberId: "B", name: "乙", role: "member", view: ["A", "B"], edit: ["A"] },   // 乙只见甲与自己、可编辑甲
  { memberId: "C", name: "丙", role: "member", view: ["B"], edit: [] },            // 丙只见乙
] } as any;
const entryOf = (mid: string) => rosPerm.members.find((m: any) => m.memberId === mid);
check("P07a 自己恒可见", canViewMember(rosPerm, "A", entryOf("A")));
check("P07b 团队长恒可见恒可编辑", canViewMember(rosPerm, "L", entryOf("C")) && canEditMember(rosPerm, "L", entryOf("A")));
check("P07c view=null 全队", canViewMember(rosPerm, "A", entryOf("B")) && canViewMember(rosPerm, "A", entryOf("C")));
check("P07d 名单外不显示+名单内显示", !canViewMember(rosPerm, "B", entryOf("C")) && canViewMember(rosPerm, "B", entryOf("A"))
  && !canViewMember(rosPerm, "C", entryOf("A")) && canViewMember(rosPerm, "C", entryOf("B")));
check("P07e 编辑须先可见+可编辑", !canEditMember(rosPerm, "C", entryOf("B")) && canEditMember(rosPerm, "B", entryOf("A"))
  && !canEditMember(rosPerm, "B", entryOf("L")));
const rosApply = { teamId: "T", teamName: "队", seq: 1, updatedAt: "x", members: [
  { memberId: "L", name: "长", role: "leader", view: null, edit: [] },
  { memberId: "M", name: "员", role: "member", view: null, edit: ["L"] },
  { memberId: "X", name: "客", role: "member", view: null, edit: [] },
] } as any;
check("P08 应用判定", applyEditDecision({ field: "note", editorId: "M" } as any, rosApply, "L") === "applied"
  && applyEditDecision({ field: "note", editorId: "X" } as any, rosApply, "L") === "rejected"
  && applyEditDecision({ field: "workflow_status", editorId: "M" } as any, rosApply, "L") === "rejected"
  && applyEditDecision({ field: "note", editorId: "M" } as any, rosApply, "M") === "applied");
// P09 快照投影（F18：合并排序去重截20/latest_event 只取已发生/stage 不降级/名单前4/缺字段置空）
const proj = projectCaseSnapshot([{
  id: "c1", name: "合成案", caseNo: "(2026)合0101号", court: "合成法院", cause: "合同纠纷",
  caseType: "法院", stage: null, amountCents: 1234567, updatedAt: "2026-10-27T00:00:00Z",
  plaintiffs: ["甲", "乙", "丙", "丁", "戊"], defendants: ["被告一"], thirdParties: [],
  calendar: [{ date: "2026-12-01", label: "开庭" }, { date: "2026-11-01", label: "举证期限" }],
  timeline: [{ date: "2026-10-20", label: "立案" }, { date: "2026-12-01", label: "开庭" },
    { date: todayStr(), label: "提交代理词" }, { date: "2099-01-01", label: "宣判(未来)" }],
}], todayStr()) as any;
const c1 = proj.cases[0];
check("P09a 关键日期合并排序去重（含未来项）", eq(c1.keyDates, [
  { date: "2026-10-20", label: "立案" }, { date: todayStr(), label: "提交代理词" },
  { date: "2026-11-01", label: "举证期限" }, { date: "2026-12-01", label: "开庭" },
  { date: "2099-01-01", label: "宣判(未来)" }]));
check("P09b latest_event 只取已发生最近件", eq(c1.latestEvent, { date: todayStr(), label: "提交代理词" }));
check("P09c stage 不降级/缺字段置空", c1.stage === "" && c1.filingDate === "" && c1.result === "" && c1.summary === "");
check("P09d 名单截前4", c1.plaintiffs.length === 4 && eq(c1.plaintiffs, ["甲", "乙", "丙", "丁"]));
check("P09e 标的额整型保真", c1.amountCents === 1234567);
check("P09f 截 20 上限", (() => {
  const many = projectCaseSnapshot([{ id: "c", name: "n", timeline: Array.from({ length: 30 }, (_, i) => ({
    date: "2026-01-" + String(i + 1).padStart(2, "0"), label: "事" + i })) }], todayStr()) as any;
  return many.cases[0].keyDates.length === 20;
})());
// P10 当事人串三态（F18 等量语义，文案自写）
check("P10 当事人串", partiesString(["甲"], ["乙", "丙"]) === "甲 对 乙、丙"
  && partiesString([], ["乙"]) === "— 对 乙" && partiesString([], []) === null);
// P11 F13 守卫：patch 带 team 被磁盘现值整体覆盖
const disk = { theme: "zai-dark", team: { teamId: "KEEP" } };
const merged = mergeSettingKeepTeam(disk, { theme: "light", team: { teamId: "WIPE" } } as any);
check("P11 F13 team 段磁盘优先", (merged as any).team.teamId === "KEEP" && (merged as any).theme === "light");
// P12 剥密（F14：嵌套 teamSecret/pairingCode 深剥离）
const dto = sanitizeValueForFrontend({ team: { teamId: "T", teamSecret: "S", pairingCode: "123456",
  nested: { teamSecret: "S2" } }, list: [{ pairingCode: "9" }] }) as any;
check("P12 前端 DTO 剥密", dto.team.teamSecret === undefined && dto.team.pairingCode === undefined
  && dto.team.nested.teamSecret === undefined && dto.list[0].pairingCode === undefined && dto.team.teamId === "T");
check("P13 配对码 6 位数字", /^\d{6}$/.test(makePairingCode()));
// P14 mDNS 接口钉定选口（多网卡真发现修复的纯函数面）：排除内环与 CGNAT 100.64/10（Tailscale）、
// env 显式钉定优先、全虚拟段兜底 null（用库默认）；同机双实例钉同址=发现必通（见 L08）。
const ifs = {
  tailscale: [{ family: "IPv4", internal: false, address: "100.92.165.62" }],
  lan: [{ family: "IPv4", internal: false, address: "192.168.31.95" }],
  loopback: [{ family: "IPv4", internal: true, address: "127.0.0.1" }],
  wsl: [{ family: "IPv4", internal: false, address: "172.27.240.1" }],
};
check("P14a 选口排除内环与 CGNAT 取首个真网卡", pickMdnsInterface(ifs, undefined) === "192.168.31.95");
check("P14b env 显式钉定优先", pickMdnsInterface(ifs, " 10.0.0.5 ") === "10.0.0.5");
check("P14c 全 CGNAT/无候选兜底 null", pickMdnsInterface({ t: ifs.tailscale }, undefined) === null
  && pickMdnsInterface({}, undefined) === null);
check("P14d CGNAT 边界 100.64/10", !isCgnatAddress("100.63.0.1") && isCgnatAddress("100.64.0.1")
  && isCgnatAddress("100.127.255.1") && !isCgnatAddress("100.128.0.1") && !isCgnatAddress("nope"));
console.log("[team-synth] ===== N/L 组：双实例真 HTTP+真 mDNS =====");
const A = makeInstance("A(团队长)", 3501, 3551);
const B = makeInstance("B(成员)", 3502, 3552);
let F: ReturnType<typeof makeInstance> | null = null; // L08c 异队实例（try 内赋值，收尾停网用）
try {
  // N/L 前置：A 建团（A5：roster seq=1 仅自己+身份落配置+网络启动）
  const stA0: any = A.svc.createTeam({ teamName: "合成小队", myName: "团队长甲" });
  const portA = await waitPort(A); // 等监听+mDNS 发布齐备再断言
  check("L01 建团身份态", stA0.configured && stA0.team.role === "leader" && stA0.team.memberCount === 1
    && stA0.pairingCode && /^\d{6}$/.test(stA0.pairingCode) && A.svc.netState().running);
  const code0: string = stA0.pairingCode;
  const aRoster = (A.svc.__test as any).rosterState();
  check("L01b 建团 roster/快照", aRoster.roster.seq === 1 && aRoster.roster.members.length === 1
    && Number(A.store.teamGetState("own_seq") ?? "0") >= 1
    && A.store.teamGetSnapshot((A.svc.status() as any).team.memberId) !== null);

  // N 组：传输约束与错误码（F11/F12；对拍 8/11/49）
  async function rawPost(port: number, path: string, body: Buffer | string, headers: Record<string, string> = {}) {
    const res = await fetch("http://127.0.0.1:" + port + path, {
      method: "POST", headers, body: new Uint8Array(Buffer.from(body)),
      signal: AbortSignal.timeout(8000),
    });
    return { status: res.status, text: await res.text() };
  }
  const getRes = await fetch("http://127.0.0.1:" + portA + TEAM_HTTP_PATH_EXCHANGE);
  check("N01a GET→400", getRes.status === 400);
  const nf = await fetch("http://127.0.0.1:" + portA + "/no-such-path", { method: "POST", body: "{}" });
  check("N01b 未知路径→404", nf.status === 404);
  const noAuth = await rawPost(portA, TEAM_HTTP_PATH_EXCHANGE, "{}");
  check("N02a 无鉴权头→403", noAuth.status === 403 && noAuth.text.includes("鉴权"));
  const { createHmac } = await import("node:crypto");
  const badAuth = await rawPost(portA, TEAM_HTTP_PATH_EXCHANGE, JSON.stringify({ teamId: "x" }),
    { "x-team-auth": "0".repeat(64), "content-type": "application/json" });
  check("N02b HMAC 错→403", badAuth.status === 403);
  const bigBody = "x".repeat(TEAM_MAX_BODY_BYTES + 1);
  const bigRes = await rawPost(portA, TEAM_HTTP_PATH_JOIN, bigBody, { "content-type": "application/json" });
  check("N03 超 4MB→413", bigRes.status === 413);
  const badJson = await rawPost(portA, TEAM_HTTP_PATH_JOIN, "{nope", { "content-type": "application/json" });
  check("N04 坏 JSON→400", badJson.status === 400);

  // B 视角：join 前的 N05/N06（B 未入团先不启动网络，直接对 A 打请求）
  const joinWrong = await rawPost(portA, TEAM_HTTP_PATH_JOIN,
    JSON.stringify({ teamId: stA0.team.teamId, code: "000000" === code0 ? "999999" : "000000",
      memberName: "乙", memberId: "memB" }), { "content-type": "application/json" });
  check("N05 错配对码→403 人话", joinWrong.status === 403 && joinWrong.text.includes("配对码不正确"));
  const joinNoName = await rawPost(portA, TEAM_HTTP_PATH_JOIN,
    JSON.stringify({ teamId: stA0.team.teamId, code: code0, memberName: "", memberId: "memB" }),
    { "content-type": "application/json" });
  check("N06 空姓名→400", joinNoName.status === 400);
  const joinWrongTeam = await rawPost(portA, TEAM_HTTP_PATH_JOIN,
    JSON.stringify({ teamId: "其他团队", code: code0, memberName: "乙", memberId: "memB" }),
    { "content-type": "application/json" });
  check("N07 teamId 不匹配→403", joinWrongTeam.status === 403 && joinWrongTeam.text.includes("团队不匹配"));

  // L02 入团（直连团队长；join 响应含 secret+签名 roster 无鉴权头；配对码一次性轮换 E2/B08）
  const portB = await (async () => { await B.svc.joinTeam({ teamId: stA0.team.teamId, code: code0, myName: "成员乙", host: "127.0.0.1", port: portA }); return waitPort(B); })();
  const stA1: any = A.svc.status();
  const stB1: any = B.svc.status();
  const bRos = (B.svc.__test as any).rosterState();
  check("L02 入团成功", stB1.configured && stB1.team.role === "member" && stB1.team.memberCount === 2
    && bRos.roster.seq === 2 && memberEntryOf(bRos.roster, stB1.team.memberId) !== null);
  check("L02b 配对码一次性轮换", stA1.pairingCode !== code0 && /^\d{6}$/.test(stA1.pairingCode));
  const joinOldCode = await rawPost(portA, TEAM_HTTP_PATH_JOIN,
    JSON.stringify({ teamId: stA0.team.teamId, code: code0, memberName: "丙", memberId: "memC" }),
    { "content-type": "application/json" });
  check("L02c 旧码立即作废", joinOldCode.status === 403);
  // N08 join 到成员实例→404（对拍 11）
  const joinMember = await rawPost(portB, TEAM_HTTP_PATH_JOIN,
    JSON.stringify({ teamId: stA0.team.teamId, code: "123456", memberName: "丙", memberId: "memC" }),
    { "content-type": "application/json" });
  check("N08 非团队长实例 join→404", joinMember.status === 404 && joinMember.text.includes("不是团队长"));

  // L03 权限配置（E4 观察者视角：乙的条目加「可编辑甲」→乙可备注甲的案件）
  await A.svc.setPermissions(stB1.team.memberId, null, [stA1.team.memberId]);
  const aRos2 = (A.svc.__test as any).rosterState();
  const bEntry = memberEntryOf(aRos2.roster, stB1.team.memberId);
  check("L03 权限保存 seq+1 重签", aRos2.roster.seq === 3 && bEntry.edit.includes(stA1.team.memberId)
    && verifyRosterSig(aRos2, (A.cfg as any).team.teamSecret)
    && !verifyRosterSig({ roster: aRos2.roster, sig: aRos2.sig.slice(0, 62) + "ff" }, (A.cfg as any).team.teamSecret));

  // L04 快照互通：A 侧合成案件→B syncRound（显式 targets）→B.view 看到甲案件（数据源=轻量案件表投影）
  const caseA = insertSyntheticCase(A.store, "合成·买卖合同纠纷");
  A.store.db.prepare("UPDATE case_board_cases SET case_no=?, claim_amount_cents=? WHERE id=?")
    .run("(2026)合0101号", 880000, caseA);
  await runRoundTo(A, { host: "127.0.0.1", port: portB }); // A 侧轮次重建快照并推送（F4）
  const repB1: any = await runRoundTo(B, { host: "127.0.0.1", port: portA });
  const sawA = await waitUntil(() => {
    const v: any = B.svc.view();
    const mA = v.members.find((m: any) => m.memberId === stA1.team.memberId);
    return !!mA?.snapshot?.payload?.cases?.length;
  }, "B 看到 A 快照");
  const viewB1: any = B.svc.view();
  const memberA = viewB1.members.find((m: any) => m.memberId === stA1.team.memberId);
  check("L04 同步报告形状+跨端看案件", typeof repB1.reached === "number" && Array.isArray(repB1.errors)
    && sawA && viewB1.members.length === 2
    && memberA.snapshot.payload.cases.length === 1
    && memberA.snapshot.payload.cases[0].name === "合成·买卖合同纠纷"
    && memberA.snapshot.payload.cases[0].amountCents === 880000
    && memberA.snapshot.payload.cases[0].stage === "审理中",
    "repB1=" + JSON.stringify(repB1) + " sawA=" + sawA + " members=" + viewB1.members.length
    + " snapCases=" + (memberA.snapshot ? memberA.snapshot.payload.cases.map((c: any) => c.name) : "null"));
  // 反向：B 的快照也到 A（同步轮是 B→A 单向请求，A 的合并发生在处理请求时）
  const sawB = await waitUntil(() => {
    const v: any = A.svc.view();
    return v.members.some((m: any) => m.memberId === stB1.team.memberId && m.snapshot);
  }, "A 看到 B 快照");
  check("L04b A 端看到 B 快照", sawB);

  // L05 备注接力（D2/D3/D6）：乙提交备注→pending→同步→甲端 applied+applied_at
  const edit1: any = B.svc.submitEdit({ targetMemberId: stA1.team.memberId, caseId: caseA,
    caseName: "合成·买卖合同纠纷", note: "管辖权异议已提交，注意答辩期" });
  check("L05a 提交即 pending", edit1.status === "pending" && edit1.editorName === "成员乙");
  const viewB2: any = B.svc.view();
  check("L05b 自己 pending 行可见（C3 数据源）", viewB2.edits.some((e: any) => e.id === edit1.id && e.status === "pending"));
  await runRoundTo(B, { host: "127.0.0.1", port: portA });
  const gotApplied = await waitUntil(() => {
    const v: any = A.svc.view();
    const row = v.edits.find((e: any) => e.id === edit1.id);
    return !!row && row.status === "applied" && !!row.appliedAt;
  }, "A 端应用 applied");
  const viewA2: any = A.svc.view();
  const appliedRow = viewA2.edits.find((e: any) => e.id === edit1.id);
  check("L05c 所有者应用 applied", gotApplied && !!appliedRow && appliedRow.status === "applied" && !!appliedRow.appliedAt);
  // D7：不回写本地案件表——case_board_cases 该行各列与备注前一致（备注只活在 team_edits）
  const caseRow: any = A.store.getCase(caseA);
  check("L05d 不回写案件表", caseRow.name === "合成·买卖合同纠纷" && caseRow.case_no === "(2026)合0101号"
    && caseRow.workflow_status === "审理中");

  // L06 撤销（D9/D10）：仅所有者、仅 applied→reverted；乙端同步后见 reverted（备注隐藏）
  let revertErr = "";
  try { B.svc.revertEdit(edit1.id); } catch (e: any) { revertErr = String(e.message); }
  check("L06a 非所有者撤销被拒", revertErr.includes("只能撤销队友对我案件的备注"));
  const reverted: any = A.svc.revertEdit(edit1.id);
  check("L06b 所有者撤销 applied→reverted", reverted.status === "reverted");
  await runRoundTo(A, { host: "127.0.0.1", port: portB });
  const gotReverted = await waitUntil(() => {
    const v: any = B.svc.view();
    return v.edits.find((e: any) => e.id === edit1.id)?.status === "reverted";
  }, "乙端见 reverted");
  const viewB3: any = B.svc.view();
  check("L06c 乙端见 reverted", gotReverted && viewB3.edits.find((e: any) => e.id === edit1.id)?.status === "reverted");

  // L07 管理区列表（D11）：甲端「队友对我案件的改动」=applied/reverted 行可见（前 20 由 SQL LIMIT 承载）
  const viewA3: any = A.svc.view();
  check("L07 队友改动列表含已生效与已撤销", viewA3.edits.filter((e: any) => e.targetMemberId === stA1.team.memberId
    && ["applied", "reverted", "rejected"].includes(e.status)).length >= 1);

  // L08 mDNS 真发现（F2/F4 同构）：B 浏览发现 A 实例（同机多播已由环境 spike 实证；真发现为规格 UNKNOWN 面，
  // 本断言按「本机环境可发现」口径执行）
  const browsed: any[] = await (B.svc.__test as any).browseTargets(6000);
  check("L08 mDNS 真发现 A 实例", browsed.some((t) => t.mid === stA1.team.memberId && t.tid === stA0.team.teamId),
    JSON.stringify(browsed.map((t) => t.mid.slice(0, 8))));
  // mDNS 全自动同步轮（F3/F4：B syncNow 走真浏览→互换）
  const repB2: any = await B.svc.syncNow();
  check("L08b syncNow 全自动轮", repB2.skipped !== true && repB2.reached >= 1);

  // L08c/L08d 跨团队隔离（F4/对拍43）：在团实例浏览只收同队 tid、全自动轮不尝试异队实例
  // （修前探针实证：异队实例被互换尝试并计入 failed=1；竞品 net.rs:536-566 过滤同 team_id 且非己）
  F = makeInstance("F(异队)", 3506, 3556);
  const stF0: any = F.svc.createTeam({ teamName: "异队小队", myName: "己" });
  await waitPort(F);
  {
    // F 实例 HTTP 在场锚（排除「F 未上线致排除断言空过」：修前该互换被真实尝试并计入 failed）
    let fUp = false;
    try {
      const rf = await fetch("http://127.0.0.1:" + (F.svc.netState() as any).port + "/juscite-team/exchange",
        { method: "POST", body: "{}", signal: AbortSignal.timeout(3000) });
      fUp = rf.status === 403; // 无鉴权头→403（N02a 同语义）
    } catch { /* 未起 */ }
    check("L08c0 异队实例 HTTP 在场", fUp);
  }
  const browsedF: any[] = await (B.svc.__test as any).browseTargets(6000);
  check("L08c 在团浏览只收同队实例", browsedF.some((t) => t.tid === stA0.team.teamId)
    && browsedF.every((t) => t.tid === stA0.team.teamId), JSON.stringify(browsedF.map((t) => t.tid)));
  const repB3: any = await B.svc.syncNow();
  check("L08d 全自动轮不试异队不误报失败", repB3.skipped !== true && repB3.failed === 0
    && repB3.reached >= 1, "failed=" + repB3.failed + " reached=" + repB3.reached);

  // L09 退团只清本机（E9/B43-B47）：乙退→乙三表空+身份清；甲端名单仍含、快照残留、视图仍显示（stale）
  await B.svc.leaveTeam();
  const stB2: any = B.svc.status();
  check("L09a 退团清本机三表+身份", stB2.configured === false
    && B.store.teamAllSnapshots().length === 0 && B.store.teamGetState("roster") === null
    && B.store.teamGetEdit(edit1.id) === null);
  const viewA4: any = A.svc.view();
  const aRos3 = (A.svc.__test as any).rosterState();
  check("L09b 退团残留多方态", aRos3.roster.members.some((m: any) => m.memberId === stB1.team.memberId)
    && viewA4.members.some((m: any) => m.memberId === stB1.team.memberId && m.snapshot)
    && viewA4.team.memberCount === 2);
  // L09c 团队长移出（E5）→roster 删人 seq+1；残留快照行仍在但无视图路径
  await A.svc.kickMember(stB1.team.memberId);
  const aRos4 = (A.svc.__test as any).rosterState();
  check("L09c 移出后视图消失", aRos4.roster.seq === 4
    && !aRos4.roster.members.some((m: any) => m.memberId === stB1.team.memberId)
    && A.svc.view().members.every((m: any) => m.memberId !== stB1.team.memberId)
    && A.store.teamGetSnapshot(stB1.team.memberId) !== null);
  let kickSelfErr = "";
  try { await A.svc.kickMember(stA1.team.memberId); } catch (e: any) { kickSelfErr = String(e.message); }
  check("L09d 不能移出自己", kickSelfErr.includes("不能移出自己"));

  // L10 被踢惰性处理（F16/E5 传播路径）：新对 C(长)+D(员)——C 踢 D 后 syncRound 推新名单→
  // D 合并发现名单无己→一次性通知→status 消费即清本机并返回 kickedFrom
  const C = makeInstance("C(团队长)", 3503, 3553);
  const D = makeInstance("D(成员)", 3504, 3554);
  const stC0: any = C.svc.createTeam({ teamName: "合成二队", myName: "队长丙" });
  const portC = await waitPort(C);
  const codeC: string = stC0.pairingCode;
  await D.svc.joinTeam({ teamId: stC0.team.teamId, code: codeC, myName: "成员丁", host: "127.0.0.1", port: portC });
  const portD = await waitPort(D);
  const stD1: any = D.svc.status();
  await C.svc.kickMember(stD1.team.memberId);
  await runRoundTo(C, { host: "127.0.0.1", port: portD });
  let stD2: any = null;
  const dKicked = await waitUntil(() => {
    stD2 = D.svc.status();
    return stD2.configured === false; // 消费被踢通知即清本机
  }, "D 收到被踢通知");
  check("L10 被踢一次性通知+清本机", dKicked && stD2 && stD2.kickedFrom === "合成二队"
    && D.store.teamAllSnapshots().length === 0 && D.store.teamGetEdit("x") === null);
  const stD3: any = D.svc.status();
  check("L10b 一次性提示取走即清", stD3.kickedFrom === undefined);

  // L11 解散=空名单墓碑+尽力广播（E7）：在场成员收墓碑→当场走被踢清理
  const E = makeInstance("E(成员)", 3505, 3555);
  const stC1: any = C.svc.status();
  const codeC1: string = stC1.pairingCode;
  await E.svc.joinTeam({ teamId: stC0.team.teamId, code: codeC1, myName: "成员戊", host: "127.0.0.1", port: portC });
  const portE = await waitPort(E);
  await C.svc.leaveTeam({ targets: [{ host: "127.0.0.1", port: portE }] }); // 真广播回路（命令面不传 targets 走 mDNS）
  let stE1: any = null;
  const eKicked = await waitUntil(() => {
    stE1 = E.svc.status();
    return stE1.configured === false;
  }, "E 收到解散墓碑");
  check("L11 解散墓碑传播", eKicked && stE1 && stE1.kickedFrom === "合成二队"
    && E.store.teamAllSnapshots().length === 0);
  const stC2: any = C.svc.status();
  check("L11b 团队长解散清本机", stC2.configured === false && C.store.teamAllSnapshots().length === 0);

  // L12 单台失败不中断（G9/B4）：A 的轮次对已停端口→failed 进 errors，报告形状完整
  let repA2: any = await (A.svc.__test as any).runSyncRound({ targets: [{ host: "127.0.0.1", port: 3599 }] });
  if (repA2.skipped) { await sleep(3200); repA2 = await (A.svc.__test as any).runSyncRound({ targets: [{ host: "127.0.0.1", port: 3599 }] }); }
  check("L12 单台失败进报告不抛", repA2.skipped !== true && repA2.failed === 1 && repA2.errors.length === 1 && repA2.reached === 0);

  // L13 DTO 剥密面（F14）：status/view 序列化串不含 secret；成员无 pairingCode
  const stA2: any = A.svc.status();
  const viewA5: any = A.svc.view();
  check("L13 DTO 剥密", !JSON.stringify(stA2).includes("teamSecret")
    && !JSON.stringify(viewA5).includes("teamSecret") && !JSON.stringify(viewA5).includes("pairingCode")
    && typeof stA2.pairingCode === "string"); // 团队长顶层配对码例外（E1 展示面）
  const stB3: any = B.svc.status();
  check("L13b 成员无配对码", stB3.configured === false || stB3.pairingCode === null || stB3.pairingCode === undefined);

  // L14 重复建团/入团被拒（G1）
  let g1a = ""; let g1b = "";
  try { A.svc.createTeam({ teamName: "再建", myName: "甲" }); } catch (e: any) { g1a = String(e.message); }
  try { await A.svc.joinTeam({ teamId: stA0.team.teamId, code: "123456", myName: "甲", host: "127.0.0.1", port: portA }); } catch (e: any) { g1b = String(e.message); }
  check("L14 已在团再建/再加被拒", g1a.includes("先退出") && g1b.includes("先退出"));

  // L15 刷新配对码仅团队长（G4/E1）
  await A.svc.refreshCode();
  const codeA2: string = (A.svc.status() as any).pairingCode;
  check("L15 刷新配对码作废旧码", /^\d{6}$/.test(codeA2) && codeA2 !== stA1.pairingCode);

  // L16 未入团 syncNow/view 被拒/空态（B13/G 语义）
  let nsErr = "";
  try { await B.svc.syncNow(); } catch (e: any) { nsErr = String(e.message); }
  check("L16 未入团命令面空态", nsErr.includes("尚未加入团队") && (B.svc.view() as any).configured === false);
} catch (e: any) {
  check("L-EXCEPTION 生命周期意外中断", false, String(e?.stack ?? e).slice(0, 400));
}

console.log("[team-synth] ===== B 组：真桥进程冒烟（隔离端口） =====");
const BPORT = 3509;
{
  const log = join(REPO_ROOT, ".local", "team-synth-bridge.log");
  const child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")], {
    cwd: REPO_ROOT, env: { ...process.env, BRIDGE_PORT: String(BPORT) },
    stdio: ["ignore", openSync(log, "a"), openSync(log, "a")], detached: true,
  });
  child.unref();
  let up = false;
  for (let i = 0; i < 80 && !up; i++) {
    await sleep(500);
    try {
      const r = await fetch("http://127.0.0.1:" + BPORT + "/api/server-info", { signal: AbortSignal.timeout(2000) });
      up = r.ok;
    } catch { /* 未起 */ }
  }
  check("B01 桥进程拉起", up, "port " + BPORT);
  if (up) {
    // 迁移 0012：三表就位（同进程另开只读连接读 schema_migration 与 sqlite_master）
    const dbp = join(process.env.APPDATA ?? "", "Juscite", "bridge", "bridge-" + BPORT + ".db");
    const rd = new DatabaseSync(dbp, { readOnly: true });
    const applied = rd.prepare("SELECT id FROM schema_migration WHERE id='0012_team_sync'").get();
    const tables = rd.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('team_snapshots','team_state','team_edits') ORDER BY name").all();
    rd.close();
    check("B02 迁移 0012 三表就位", !!applied && tables.length === 3, JSON.stringify(tables));
    spawnSync("taskkill", ["/PID", String(child.pid), "/F", "/T"], { timeout: 15000 });
  }
}

// 收尾：停网络（关监听/停 mDNS）+ 清隔离库（进程退出前句柄在本进程，Windows 须先 close——
// openBridgeStore 未暴露 close，sqlite 句柄随进程退出释放；隔离库文件按端口固定，复跑幂等）
A.svc.stopNet(); B.svc.stopNet(); F?.svc.stopNet();
const passed = results.filter((r) => r.ok).length;
const failed = results.length - passed;
for (const r of results.filter((x) => !x.ok)) console.log(`[team-synth] FAIL → ${r.name} ${r.detail ?? ""}`);
console.log(`[team-synth] PASS=${passed} FAIL=${failed}`);
console.log(failed === 0 ? "TEAM_SYNTH_PASS" : "TEAM_SYNTH_FAIL");
process.exit(failed === 0 ? 0 : 1);
