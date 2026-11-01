// 【步骤4·#26 LAN 团队同步】团队同步纯内核（RE-26-LAN 团队同步.md §3 数据模型/身份与信任模型/状态机）。
// 桥/合成自测单一来源（沿 matter_service/caseTimelineModel 先例）；网络层副作用在 team_sync_service.mjs。
// 行为等量口径（§2 行为清单 F/D 组）：roster 对序列化原文 HMAC-SHA256 签名随 gossip 传播；
// 快照同 member_id 按 seq 新者胜、相同不覆盖；编辑状态机只升不降（pending0→applied1→rejected/reverted2，
// 未知 -1 恒被覆盖）；权限=自己恒可见/团队长恒可见恒可编辑/view=null 全队/名单外默认不显示/编辑须先可见。
// 自定字段与文案（表达隔离：等量≠抄文案）；不与 CaseBoard 线缆兼容（mDNS 域/HTTP 路径自定）。
import { createHmac, randomUUID, randomInt } from "node:crypto";

// ── 常量单源（F2/F3/F11/F18/D4 等量数值；服务类型/路径/主机名前缀自定不与竞品互通）──
export const TEAM_MDNS_TYPE = "juscite-team";          // mDNS 服务类型（竞品 _caseboard-team 有意不用）
export const TEAM_HTTP_PATH_JOIN = "/juscite-team/join";
export const TEAM_HTTP_PATH_EXCHANGE = "/juscite-team/exchange";
export const TEAM_MAX_BODY_BYTES = 4 * 1024 * 1024;    // F11 等量：body 上限 4MB
export const TEAM_MAX_HEADER_BYTES = 64 * 1024;        // F11 等量：头部 >64KB 报错
export const TEAM_HTTP_TIMEOUT_MS = 15000;             // F11 等量：超时 15s（服务端连接/客户端中止同值）
export const TEAM_PERIOD_MS = 600_000;                 // F3 等量：周期同步 600 秒/轮
export const TEAM_BROWSE_MS = 2500;                    // F4 等量：同步轮浏览 2500ms
export const TEAM_DISCOVER_MS = 3000;                  // A6 等量：入团扫描口径约 3 秒
export const TEAM_EDITS_WINDOW = 500;                  // F5 等量：edits 交换最近 500 条
export const TEAM_KEY_DATES_MAX = 20;                  // F17/F18 等量：关键日期截 20
export const TEAM_NAME_LIST_MAX = 4;                   // F17 等量：原/被/第三人名单各前 4
export const TEAM_NOTE_MAX = 500;                      // D4 等量：备注后端上限 500 字
export const TEAM_EDITABLE_FIELDS = ["note"];          // mod.rs:277 等量：字段白名单兜底（本产品无遗留状态路径）

// 编辑状态 rank（D8 等量：只升不降；未知 -1 恒被覆盖）
const EDIT_STATUS_RANK = { pending: 0, applied: 1, rejected: 2, reverted: 2 };
export function editStatusRank(status) {
  return Object.prototype.hasOwnProperty.call(EDIT_STATUS_RANK, status) ? EDIT_STATUS_RANK[status] : -1;
}

// ── 身份生成（§3 身份与信任模型：team_id uuid；team_secret=双 uuid hex 64；配对码 6 位数字一次性）──
export function makePairingCode() {
  return String(randomInt(0, 1_000_000)).padStart(6, "0");
}
export function makeTeamSecret() {
  return (randomUUID() + randomUUID()).replace(/-/g, "");
}
export function newTeamIdentity({ teamName, myName }) {
  return {
    teamId: randomUUID(),
    teamName: String(teamName),
    teamSecret: makeTeamSecret(),
    memberId: randomUUID(),
    myName: String(myName),
    role: "leader",
    pairingCode: makePairingCode(),
  };
}
// 团队身份形状校验（外边界防御：配置文件可被手改，坏形状按未配置处理，不半启）
export function isWellFormedIdentity(id) {
  return Boolean(id && typeof id === "object"
    && typeof id.teamId === "string" && id.teamId
    && typeof id.teamName === "string"
    && typeof id.teamSecret === "string" && /^[0-9a-f]{64}$/.test(id.teamSecret)
    && typeof id.memberId === "string" && id.memberId
    && typeof id.myName === "string"
    && (id.role === "leader" || id.role === "member")
    && typeof id.pairingCode === "string" && /^\d{6}$/.test(id.pairingCode));
}

// ── roster（签名件随 gossip 传播；seq 单调；members[{memberId,name,role,view,edit}]）──
// 签名对序列化原文 HMAC（等量：签名与验证共用同一序列化器，同构输入必得同字节，绕开 JSON 规范化坑）
export function rosterCanonicalJson(roster) {
  return JSON.stringify(roster);
}
export function signRoster(roster, teamSecret) {
  const sig = createHmac("sha256", teamSecret).update(rosterCanonicalJson(roster)).digest("hex");
  return { roster, sig };
}
export function isWellFormedSignedRoster(signed) {
  const r = signed?.roster;
  return Boolean(r && typeof r === "object"
    && typeof r.teamId === "string" && typeof r.teamName === "string"
    && Number.isInteger(r.seq) && r.seq >= 0
    && Array.isArray(r.members) && r.members.every((m) => m && typeof m.memberId === "string"
      && typeof m.name === "string" && (m.role === "leader" || m.role === "member")
      && (m.view === null || (Array.isArray(m.view) && m.view.every((x) => typeof x === "string")))
      && Array.isArray(m.edit) && m.edit.every((x) => typeof x === "string"))
    && typeof r.updatedAt === "string"
    && typeof signed.sig === "string" && /^[0-9a-f]{64}$/.test(signed.sig));
}
export function verifyRosterSig(signed, teamSecret) {
  if (!isWellFormedSignedRoster(signed)) return false;
  const expect = createHmac("sha256", teamSecret).update(rosterCanonicalJson(signed.roster)).digest("hex");
  return expect === signed.sig;
}
export function newLeaderRoster(identity) {
  return {
    teamId: identity.teamId,
    teamName: identity.teamName,
    seq: 1,
    members: [{ memberId: identity.memberId, name: identity.myName, role: "leader", view: null, edit: [] }],
    updatedAt: new Date().toISOString(),
  };
}
export function resignRoster(roster, teamSecret) {
  return signRoster({ ...roster, seq: roster.seq + 1, updatedAt: new Date().toISOString() }, teamSecret);
}
export function memberEntryOf(roster, memberId) {
  return roster.members.find((m) => m.memberId === memberId) ?? null;
}
export function isLeaderId(roster, memberId) {
  return memberEntryOf(roster, memberId)?.role === "leader";
}

// ── 权限判定（§3/E4 等量，观察者视角：成员条目持有"该成员可见谁/可编辑谁"两名单——
// 团队长逐人配置；自己恒可见（保存时强制含己）；团队长恒可见恒可编辑；view=null 全队；
// 名单外默认不显示；编辑须先可见（子集语义，保存时校验）。──
export function canViewMember(roster, viewerId, targetEntry) {
  if (!targetEntry) return false;
  if (viewerId === targetEntry.memberId) return true; // 自己恒可见
  const viewer = memberEntryOf(roster, viewerId);
  if (!viewer) return false;
  if (viewer.role === "leader") return true;          // 团队长恒可见
  if (viewer.view === null) return true;              // 全队
  return viewer.view.includes(targetEntry.memberId);  // 名单外默认不显示
}
export function canEditMember(roster, viewerId, targetEntry) {
  if (!targetEntry) return false;
  if (viewerId === targetEntry.memberId) return true; // 自己案件恒可编辑（C4：给自己备注立即生效）
  const viewer = memberEntryOf(roster, viewerId);
  if (!viewer) return false;
  if (viewer.role === "leader") return true;          // 团队长恒可编辑
  if (!canViewMember(roster, viewerId, targetEntry)) return false; // 编辑须先可见
  return viewer.edit.includes(targetEntry.memberId);
}

// ── roster 合并（F8 等量：验签+seq 更高才收；篡改/低 seq 不收；发现自己不在新名单→被踢信号）──
export function mergeRoster(localSigned, incomingSigned, teamSecret, myMemberId) {
  if (!verifyRosterSig(incomingSigned, teamSecret)) return { merged: false, kicked: false, rejected: "signature" };
  if (localSigned && incomingSigned.roster.seq <= localSigned.roster.seq) {
    return { merged: false, kicked: false, rejected: "seq" }; // 低 seq/同 seq 不收（防回退）
  }
  const kicked = !memberEntryOf(incomingSigned.roster, myMemberId);
  return { merged: true, kicked, rejected: null };
}

// ── 快照合并（F9 等量：同 member_id 按 seq 新者胜；seq 相同不覆盖防回退；首见必收）──
export function shouldAcceptSnapshot(localRow, incomingSeq) {
  if (!localRow) return true;
  return Number(incomingSeq) > Number(localRow.seq);
}

// ── 编辑合并（F10/D8 等量：本团队过滤在调用方；字段白名单兜底；rank 只升不降；未知状态拒收不进库）──
export function shouldAcceptEdit(localRow, incoming) {
  if (!TEAM_EDITABLE_FIELDS.includes(incoming.field)) return false; // 白名单兜底
  if (!localRow) return true;
  return editStatusRank(incoming.status) > editStatusRank(localRow.status);
}
export const TEAM_EDIT_STATUSES = ["pending", "applied", "rejected", "reverted"];
// 编辑行形状校验（合并入口与提交入口共用）
export function isWellFormedEdit(e) {
  return Boolean(e && typeof e === "object"
    && typeof e.id === "string" && e.id
    && typeof e.teamId === "string" && e.teamId
    && typeof e.editorId === "string" && e.editorId
    && typeof e.editorName === "string"
    && typeof e.targetMemberId === "string" && e.targetMemberId
    && typeof e.caseId === "string"
    && typeof e.caseName === "string"
    && typeof e.field === "string"
    && typeof e.value === "string"
    && (e.prevValue === null || e.prevValue === undefined || typeof e.prevValue === "string")
    && TEAM_EDIT_STATUSES.includes(e.status)
    && typeof e.createdAt === "string"
    && (e.appliedAt === null || e.appliedAt === undefined || typeof e.appliedAt === "string"));
}

// ── 所有者应用判定（D6 等量：note=可见即可写→applied；未知字段/无权限→rejected；
// 不回写本地案件表（D7 语义）由调用方保证——本模块不触碰任何案件写路径）──
export function applyEditDecision(edit, roster, myMemberId) {
  const myEntry = memberEntryOf(roster, myMemberId);
  if (!myEntry) return "rejected";
  if (!TEAM_EDITABLE_FIELDS.includes(edit.field)) return "rejected";
  const editorEntry = memberEntryOf(roster, edit.editorId);
  if (!editorEntry || !canEditMember(roster, edit.editorId, myEntry)) return "rejected";
  return "applied";
}

// ── 快照投影（F17/F18 等量：粒度=案件登记表；日期合并排序去重截 20；latest_event 只取已发生；
// stage 只取短状态不降级；名单各前 4；缺失字段置空不猜。数据源=桥轻量案件表投影入参，
// 绝不含文档原文/报告/聊天/路径/API key（F17 数据红线）。）──
// 入参行形状（桥面装配）：{ id,name,caseNo,court,cause,caseType,stage,filingDate,result,amountCents,
//   updatedAt, plaintiffs[],defendants[],thirdParties[], calendar:[{date,label}], timeline:[{date,label}] }
export function projectCaseSnapshot(rows, today) {
  return {
    generatedAt: new Date().toISOString(),
    cases: (Array.isArray(rows) ? rows : []).map((r) => {
      const keyDates = dedupeSortedDates([...(r.calendar ?? []), ...(r.timeline ?? [])]);
      const occurred = (r.timeline ?? [])
        .filter((e) => typeof e.date === "string" && e.date <= today)
        .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
      return {
        id: r.id,
        name: r.name,
        caseNo: r.caseNo ?? "",
        court: r.court ?? "",
        cause: r.cause ?? "",
        caseType: r.caseType ?? "",
        stage: r.stage ?? "", // 只取短状态；NULL（自动推断）→ 空串，不降级取长描述
        filingDate: r.filingDate ?? "",
        result: r.result ?? "",
        amountCents: Number.isInteger(r.amountCents) ? r.amountCents : 0,
        keyDates: keyDates.slice(0, TEAM_KEY_DATES_MAX),
        latestEvent: occurred[0] ? { date: occurred[0].date, label: occurred[0].label } : null,
        updatedAt: r.updatedAt ?? "",
        plaintiffs: (r.plaintiffs ?? []).slice(0, TEAM_NAME_LIST_MAX),
        defendants: (r.defendants ?? []).slice(0, TEAM_NAME_LIST_MAX),
        thirdParties: (r.thirdParties ?? []).slice(0, TEAM_NAME_LIST_MAX),
        execTotalCents: Number.isInteger(r.execTotalCents) ? r.execTotalCents : 0,
        execReceivedCents: Number.isInteger(r.execReceivedCents) ? r.execReceivedCents : 0,
        execPendingCents: Number.isInteger(r.execPendingCents) ? r.execPendingCents : 0,
        summary: r.summary ?? "",
      };
    }),
  };
}
function dedupeSortedDates(items) {
  const seen = new Map();
  for (const it of items ?? []) {
    if (!it || typeof it.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(it.date)) continue;
    const label = String(it.label ?? "").trim();
    if (!label) continue;
    const key = it.date + "\n" + label;
    if (!seen.has(key)) seen.set(key, { date: it.date, label });
  }
  return [...seen.values()].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

// ── 当事人串（F18 等量语义，文案自写：原告列/被告列 join，缺侧补占位，双侧空=null）──
export function partiesString(plaintiffs, defendants) {
  const p = (plaintiffs ?? []).filter(Boolean).join("、");
  const d = (defendants ?? []).filter(Boolean).join("、");
  if (!p && !d) return null;
  return (p || "—") + " 对 " + (d || "—");
}

// ── 通用配置保存的 team 段守卫（F13 等量：保存设置时 team 字段以磁盘现值整体覆盖——
// 结构上掐死设置表单冲掉团队身份的路；团队身份只经 team_sync_service 的 saveIdentity 写盘）──
export function mergeSettingKeepTeam(before, patch) {
  return { ...before, ...patch, team: before.team };
}

// ── 前端 DTO 剥密（F14 等量：嵌套 teamSecret/pairingCode 深剥离）──
export function sanitizeValueForFrontend(value) {
  if (Array.isArray(value)) return value.map(sanitizeValueForFrontend);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value)
      .filter(([k]) => k !== "teamSecret" && k !== "pairingCode")
      .map(([k, v]) => [k, sanitizeValueForFrontend(v)]));
  }
  return value;
}

// ── mDNS 接口钉定（多网卡机器真发现修复）：win32 实测（2026-10-28 复跑环境实锤）——
// multicast-dns 默认对全部网卡 addMembership 且 egress=内核默认（INADDR_ANY）；本机 Tailscale
// (CGNAT 100.64/10)+以太网+WSL 交换机并存时，内核默认组播出口与显式成员资格错配，同机发现收包为空。
// 实证矩阵（node dgram 直测）：tx 钉定网卡 + rx 同网卡成员资格 → 通；tx 默认 + rx 任意 → 不通。
// 故钉定单一 IPv4：同机双实例钉同址=必通；跨机发现=钉在真网段时通。选口规则（确定性、不猜）：
// 显式 env 钉定 > 非内环 IPv4 里排除 CGNAT 100.64/10（Tailscale 专用段，IANA 保留）取首 > 无候选返回 null（用库默认）。
export function isCgnatAddress(addr) {
  const m = /^(\d{1,3})\.(\d{1,3})\./.exec(addr ?? "");
  if (!m) return false;
  return Number(m[1]) === 100 && Number(m[2]) >= 64 && Number(m[2]) <= 127;
}
export function pickMdnsInterface(interfaces, override) {
  const pinned = (override ?? "").trim();
  if (pinned) return pinned;
  const v4 = [];
  for (const list of Object.values(interfaces ?? {})) {
    for (const ni of list ?? []) {
      if (ni.family === "IPv4" && !ni.internal && !isCgnatAddress(ni.address)) { v4.push(ni.address); break; }
    }
  }
  return v4[0] ?? null;
}
