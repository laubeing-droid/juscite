// 【步骤4·#26 LAN 团队同步】团队同步网络层与编排（RE-26-LAN 团队同步.md §3 状态机/流程 + §3 技术选型）。
// 谁发起谁控制：UI/agent 发起命令；本模块机械装配；无任何常驻云端。
// 技术选型等量：mDNS 用 bonjour-service（发布/浏览 TXT tid/tname/mid/role）；HTTP 用 node:http 手搓
// 极简服务（仅 POST+Content-Length+JSON、4MB 上限、15s 超时，不引框架）；HMAC/随机用 node:crypto；
// 客户端 fetch+15s 超时。服务类型/HTTP 路径/主机名前缀自定（_juscite-team._tcp，不与 CaseBoard 互通）。
// 数据红线（F17 等量继承）：快照只含登记层字段；secret 只存本机配置文件不进库不进日志；退团清三表。
import http from "node:http";
import os from "node:os";
import { createHmac, randomUUID } from "node:crypto";
import { Bonjour } from "bonjour-service";
import {
  TEAM_MDNS_TYPE, TEAM_HTTP_PATH_JOIN, TEAM_HTTP_PATH_EXCHANGE,
  TEAM_MAX_BODY_BYTES, TEAM_HTTP_TIMEOUT_MS, TEAM_PERIOD_MS, TEAM_BROWSE_MS, TEAM_DISCOVER_MS,
  TEAM_EDITS_WINDOW, TEAM_NOTE_MAX, TEAM_EDITABLE_FIELDS,
  makePairingCode, newTeamIdentity, isWellFormedIdentity,
  signRoster, verifyRosterSig, newLeaderRoster, resignRoster, memberEntryOf,
  canViewMember, mergeRoster, shouldAcceptSnapshot, shouldAcceptEdit,
  applyEditDecision, isWellFormedEdit, isWellFormedSignedRoster, projectCaseSnapshot,
  pickMdnsInterface,
} from "./team_sync_model.mjs";

const TEAM_PORT_DEFAULT = Number(process.env.BRIDGE_TEAM_PORT ?? 0); // 0=随机端口（mDNS SRV 广播实际值）

function hmacOf(teamSecret, bytes) {
  return createHmac("sha256", teamSecret).update(bytes).digest("hex");
}
function ipv4Of(addresses) {
  for (const a of addresses ?? []) {
    if (typeof a === "string" && /^\d{1,3}(\.\d{1,3}){3}$/.test(a)) return a;
  }
  return null;
}

export function createTeamSync({
  store, loadSetting, saveSetting, auditWrite,
  projectCaseRows,           // () => 快照投影入参行（桥轻量案件表装配，见 projectCaseSnapshot 注）
  periodMs = TEAM_PERIOD_MS, browseMs = TEAM_BROWSE_MS, discoverMs = TEAM_DISCOVER_MS,
  port = TEAM_PORT_DEFAULT,
}) {
  const net = {
    running: false, port: null, server: null, bonjour: null, published: null,
    timer: null, syncing: false, lastReport: null,
  };
  const joinTargets = new Map(); // teamId -> [{host, port, mid, role, tname, at}]（discover/join 缓存；mDNS 缺席时的直连兜底由调用方注入）

  // ── 身份与本地态（F13 等量：身份存配置文件不进 SQLite；roster 签名件/own_seq/被踢通知存 team_state）──
  function identity() {
    const id = loadSetting()?.team;
    return isWellFormedIdentity(id) ? id : null;
  }
  function saveIdentity(id) {
    const s = loadSetting();
    s.team = id;
    saveSetting(s);
  }
  function clearIdentity() {
    const s = loadSetting();
    delete s.team;
    saveSetting(s);
  }
  function rosterState() {
    const raw = store.teamGetState("roster");
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      return isWellFormedSignedRoster(parsed) ? parsed : null;
    } catch { return null; }
  }
  function saveRosterState(signed) {
    store.teamSetState("roster", JSON.stringify(signed));
  }
  function ownSeq() {
    return Number(store.teamGetState("own_seq") ?? 0);
  }

  // ── 快照重建（F4/F18：own_seq 自增；投影行来自桥轻量案件表，缺失字段置空不猜）──
  function rebuildOwnSnapshot() {
    const id = identity();
    if (!id) return null;
    const seq = ownSeq() + 1;
    store.teamSetState("own_seq", String(seq));
    const payload = projectCaseSnapshot(projectCaseRows(), todayStr());
    store.teamPutSnapshot({
      member_id: id.memberId, name: id.myName, seq,
      updated_at: new Date().toISOString(), payload_json: JSON.stringify(payload),
    });
    return { seq, payload };
  }
  function todayStr() {
    const n = new Date();
    return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
  }

  // ── 合并入口（F8/F9/F10 等量）：签名 roster / seq 胜快照 / 白名单+本团队+rank 升编辑；
  // 被踢检测→写一次性通知；应用目标=我的 pending，应用>0 重建本人快照让改动随响应传出。──
  function mergeIncoming({ roster: incomingRoster, snapshots, edits }) {
    const id = identity();
    if (!id) return { applied: 0, kicked: false };
    let kicked = false;
    if (incomingRoster) {
      const local = rosterState();
      const verdict = mergeRoster(local, incomingRoster, id.teamSecret, id.memberId);
      if (verdict.merged) {
        saveRosterState(incomingRoster);
        if (verdict.kicked) {
          kicked = true;
          store.teamSetState("kicked_notice", JSON.stringify({ teamName: incomingRoster.roster.teamName, at: Date.now() }));
        }
      }
    }
    for (const snap of Array.isArray(snapshots) ? snapshots : []) {
      if (!snap || typeof snap.memberId !== "string" || !Number.isInteger(snap.seq)) continue;
      if (!shouldAcceptSnapshot(store.teamGetSnapshot(snap.memberId), snap.seq)) continue;
      store.teamPutSnapshot({
        member_id: snap.memberId, name: String(snap.name ?? ""), seq: snap.seq,
        updated_at: String(snap.updatedAt ?? ""), payload_json: JSON.stringify(snap.payload ?? null),
      });
    }
    const localTeamId = rosterState()?.roster.teamId ?? id.teamId;
    for (const e of Array.isArray(edits) ? edits : []) {
      if (!isWellFormedEdit(e) || e.teamId !== localTeamId) continue; // 他队残留过滤（F10）
      if (!shouldAcceptEdit(editRowFromStore(store.teamGetEdit(e.id)), e)) continue;
      store.teamPutEdit(editRowToStore(e));
    }
    const applied = applyPendingForMe();
    if (applied > 0) rebuildOwnSnapshot();
    return { applied, kicked };
  }

  function applyPendingForMe() {
    const id = identity();
    const signed = rosterState();
    if (!id || !signed) return 0;
    let applied = 0;
    for (const row of store.teamListEditsByTarget(id.memberId, "pending")) {
      const e = editRowFromStore(row);
      const decision = applyEditDecision(e, signed.roster, id.memberId); // note=可见即可写；其余 rejected（D6/D7）
      store.teamUpdateEditStatus(e.id, decision, decision === "applied" ? new Date().toISOString() : null);
      if (decision === "applied") applied++;
    }
    return applied;
  }

  // ── 编辑行 store(snake)/wire(camel) 映射 ──
  function editRowFromStore(r) {
    return r ? {
      id: r.id, teamId: r.team_id, editorId: r.editor_id, editorName: r.editor_name,
      targetMemberId: r.target_member_id, caseId: r.case_id, caseName: r.case_name,
      field: r.field, value: r.value, prevValue: r.prev_value ?? null, status: r.status,
      createdAt: r.created_at, appliedAt: r.applied_at ?? null,
    } : null;
  }
  function editRowToStore(e) {
    return {
      id: e.id, team_id: e.teamId, editor_id: e.editorId, editor_name: e.editorName,
      target_member_id: e.targetMemberId, case_id: e.caseId, case_name: e.caseName,
      field: e.field, value: e.value, prev_value: e.prevValue ?? null, status: e.status,
      created_at: e.createdAt, applied_at: e.appliedAt ?? null,
    };
  }

  // ── 手搓 HTTP 服务（F11/F12 等量：仅 POST+Content-Length+JSON；body 4MB 上限；15s 超时；
  // 错误码语义：403 not-in-team/auth failed/team mismatch/配对码错；400 坏 body/GET；404 未知路径/非团队长）──
  function startServer() {
    return new Promise((resolve, reject) => {
      const server = http.createServer((req, res) => {
        const fail = (code, message) => {
          const body = JSON.stringify({ error: message });
          res.writeHead(code, { "content-type": "application/json" });
          res.end(body);
        };
        if (req.method !== "POST") return fail(400, "仅支持 POST 请求");
        const path = (req.url ?? "").split("?")[0];
        if (path !== TEAM_HTTP_PATH_JOIN && path !== TEAM_HTTP_PATH_EXCHANGE) return fail(404, "未知路径");
        const lenHeader = req.headers["content-length"];
        const len = Number(lenHeader);
        if (!lenHeader || !Number.isFinite(len) || len < 0) return fail(400, "缺少 Content-Length");
        if (len > TEAM_MAX_BODY_BYTES) return fail(413, "请求体超过 4MB 上限");
        const chunks = [];
        let size = 0;
        let done = false;
        req.on("data", (c) => {
          size += c.length;
          if (size > TEAM_MAX_BODY_BYTES) { fail(413, "请求体超过 4MB 上限"); req.destroy(); return; }
          chunks.push(c);
        });
        req.on("error", () => { done = true; });
        req.on("end", async () => {
          if (done) return;
          done = true;
          const bytes = Buffer.concat(chunks);
          try {
            if (path === TEAM_HTTP_PATH_JOIN) return await handleJoin(bytes, res);
            return await handleExchange(bytes, req.headers["x-team-auth"], res);
          } catch (e) {
            const err = e ?? {};
            return fail(err.statusCode ?? 500, err.statusCode ? err.message : "内部错误");
          }
        });
      });
      server.requestTimeout = TEAM_HTTP_TIMEOUT_MS;
      server.headersTimeout = TEAM_HTTP_TIMEOUT_MS;
      server.keepAliveTimeout = TEAM_HTTP_TIMEOUT_MS;
      server.on("error", reject);
      server.listen(net.port ?? port, "0.0.0.0", () => {
        net.port = server.address().port;
        resolve(server);
      });
      net.server = server;
    });
  }

  class HttpError extends Error {
    constructor(statusCode, message) { super(message); this.statusCode = statusCode; }
  }

  // /join（F7 等量）：仅团队长能批；码对→入 roster（已存在只改名）seq+1 重签→响应含 secret+签名
  // roster（无鉴权头）→配对码立即轮换（防码扩散被外人入队，E2）。
  async function handleJoin(bytes, res) {
    const id = identity();
    const signed = rosterState();
    if (!id || !signed || id.role !== "leader") throw new HttpError(404, "该应用不是团队长，无法接受加入");
    let body;
    try { body = JSON.parse(bytes.toString("utf-8")); } catch { throw new HttpError(400, "请求体不是合法 JSON"); }
    if (!body || typeof body !== "object") throw new HttpError(400, "请求体不是合法 JSON");
    if (typeof body.teamId !== "string" || body.teamId !== id.teamId) throw new HttpError(403, "团队不匹配，请重新搜索后加入");
    if (typeof body.code !== "string" || body.code !== id.pairingCode) throw new HttpError(403, "配对码不正确，请向团队长确认最新配对码");
    if (typeof body.memberName !== "string" || !body.memberName.trim()) throw new HttpError(400, "姓名不能为空");
    if (typeof body.memberId !== "string" || !body.memberId.trim()) throw new HttpError(400, "缺少成员标识");
    const roster = { ...signed.roster, updatedAt: new Date().toISOString() };
    const existing = memberEntryOf(roster, body.memberId);
    if (existing) {
      roster.members = roster.members.map((m) => (m.memberId === body.memberId ? { ...m, name: body.memberName.trim() } : m));
    } else {
      roster.members = [...roster.members,
        { memberId: body.memberId, name: body.memberName.trim(), role: "member", view: null, edit: [] }];
    }
    const freshSigned = resignRoster(roster, id.teamSecret); // seq+1 重签
    saveRosterState(freshSigned);
    const freshId = { ...id, pairingCode: makePairingCode() }; // 配对码一次性：入队成功即轮换（E2）
    saveIdentity(freshId);
    console.log(`[team] member joined: ${body.memberName.trim()} (roster seq=${freshSigned.roster.seq}, pairing code rotated)`);
    const respBytes = Buffer.from(JSON.stringify({
      teamId: id.teamId, teamName: id.teamName, teamSecret: id.teamSecret,
      memberId: body.memberId, roster: freshSigned,
    }), "utf-8");
    res.writeHead(200, { "content-type": "application/json" }); // 无鉴权头（F7 等量：join 响应不签）
    res.end(respBytes);
  }

  // /exchange（F5/F6 等量）：请求响应同形；x-team-auth 双向 HMAC-SHA256(对原文 body 字节)；
  // 验不过=403；接收方未入团=403；team_id 不匹配=403；合并后应用目标=我的 pending。
  async function handleExchange(bytes, auth, res) {
    const id = identity();
    const signed = rosterState();
    if (!id || !signed) throw new HttpError(403, "本机尚未加入任何团队");
    if (auth !== hmacOf(id.teamSecret, bytes)) throw new HttpError(403, "鉴权失败（HMAC 校验未通过）");
    let body;
    try { body = JSON.parse(bytes.toString("utf-8")); } catch { throw new HttpError(400, "请求体不是合法 JSON"); }
    if (!body || typeof body !== "object" || typeof body.teamId !== "string") throw new HttpError(400, "请求体不是合法 JSON");
    if (body.teamId !== id.teamId) throw new HttpError(403, "团队不匹配");
    const { applied } = mergeIncoming(body);
    const freshSigned = rosterState();
    const respBody = {
      teamId: id.teamId,
      fromMember: id.memberId,
      snapshots: allSnapshotsForWire(),
      roster: freshSigned,
      edits: store.teamListEditsForExchange(TEAM_EDITS_WINDOW).map(editRowFromStore),
      ...(applied > 0 ? { applied } : {}),
    };
    const respBytes = Buffer.from(JSON.stringify(respBody), "utf-8");
    res.writeHead(200, { "content-type": "application/json", "x-team-auth": hmacOf(id.teamSecret, respBytes) });
    res.end(respBytes);
  }
  function allSnapshotsForWire() {
    return store.teamAllSnapshots().map((r) => {
      let payload = null;
      try { payload = JSON.parse(r.payload_json ?? "null"); } catch { payload = null; }
      return { memberId: r.member_id, name: r.name, seq: r.seq, updatedAt: r.updated_at, payload };
    });
  }

  // ── 同步轮（F4/F9 等量）：重建本人快照→浏览→同团队非己逐台顺序互换→单台失败进报告不中断──
  async function browseTargets(timeoutMs) {
    const id = identity();
    if (!id || !net.bonjour) return [];
    return new Promise((resolve) => {
      const found = new Map();
      const browser = net.bonjour.find({ type: TEAM_MDNS_TYPE }, (svc) => {
        const mid = svc?.txt?.mid;
        const tid = svc?.txt?.tid;
        if (!tid || !mid || mid === id.memberId) return;          // 同团队非己（F4）
        if (id && tid !== id.teamId) return;                      // 在团只收同队（F4/对拍43，竞品 net.rs:536-566 过滤同 team_id 且非己=根本不尝试别队）；未入团扫描（discover 时身份为空）=全量聚合
        const host = ipv4Of(svc.addresses) ?? svc.referer?.address ?? svc.host;
        if (!host) return;
        found.set(mid + "@" + svc.port, {
          host, port: svc.port, mid, role: svc.txt.role ?? "member", tname: svc.txt.tname ?? "", tid,
        });
      });
      setTimeout(() => {
        try { browser.stop(); } catch { /* 已停止 */ }
        resolve([...found.values()]);
      }, timeoutMs);
    });
  }

  async function runSyncRound({ withBrowse = true, targets = null } = {}) {
    const id = identity();
    const signed = rosterState();
    if (!id || !signed || !net.running || net.syncing) {
      return { reached: 0, snapshotsUpdated: 0, failed: 0, errors: [], skipped: true };
    }
    net.syncing = true;
    const report = { reached: 0, snapshotsUpdated: 0, failed: 0, errors: [] };
    try {
      rebuildOwnSnapshot(); // 先重建本人快照（own_seq 自增）
      let list = targets;
      if (!list && withBrowse) list = await browseTargets(browseMs);
      for (const t of list ?? []) {
        if (identity()?.teamId !== id.teamId) break; // 退团/被踢即停
        try {
          const result = await exchangeOne(t.host, t.port);
          report.reached++;
          report.snapshotsUpdated += result.appliedSnapshots;
        } catch (e) {
          report.failed++;
          report.errors.push(`${t.host}:${t.port} ${String(e?.message ?? e).slice(0, 160)}`);
        }
      }
      net.lastReport = { ...report, at: Date.now() };
      return report;
    } finally {
      net.syncing = false;
    }
  }

  async function exchangeOne(host, port) {
    const id = identity();
    const signed = rosterState();
    const body = {
      teamId: id.teamId,
      fromMember: id.memberId,
      snapshots: allSnapshotsForWire(), // 全量互换不搞增量（F5）
      roster: signed,
      edits: store.teamListEditsForExchange(TEAM_EDITS_WINDOW).map(editRowFromStore),
    };
    const bytes = Buffer.from(JSON.stringify(body), "utf-8");
    const res = await fetch(`http://${host}:${port}${TEAM_HTTP_PATH_EXCHANGE}`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-team-auth": hmacOf(id.teamSecret, bytes) },
      body: new Uint8Array(bytes),
      signal: AbortSignal.timeout(TEAM_HTTP_TIMEOUT_MS), // 客户端总超时 15s（F11 等量）
    });
    const resBytes = Buffer.from(await res.arrayBuffer());
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { msg = JSON.parse(resBytes.toString("utf-8"))?.error ?? msg; } catch { /* 保留状态码 */ }
      throw new Error(msg); // 人话错误透传链（A10/G9）
    }
    const resAuth = res.headers.get("x-team-auth");
    if (!resAuth || resAuth !== hmacOf(id.teamSecret, resBytes)) {
      throw new Error("响应鉴权失败（HMAC 校验未通过），本轮不合并"); // 响应验签失败=不合并（F6）
    }
    const parsed = JSON.parse(resBytes.toString("utf-8"));
    const before = store.teamAllSnapshots().map((s) => `${s.member_id}:${s.seq}`).join("|");
    mergeIncoming(parsed);
    const after = store.teamAllSnapshots().map((s) => `${s.member_id}:${s.seq}`).join("|");
    return { appliedSnapshots: before !== after ? 1 : 0, applied: parsed.applied ?? 0 };
  }

  // ── 网络生命周期（F1 等量）：建团/入团/启动已配置即启（监听+mDNS 广播+周期同步）；
  // 退团/解散/被踢自动停。mDNS 主机名前缀自定 juscite-{memberId 前 8}（F2 同构）。──
  async function startNet() {
    const id = identity();
    if (!id || net.running) return net.running;
    net.port = port || null;
    await startServer();
    // mDNS 接口钉定（多网卡真发现修复，选口规则见 team_sync_model.pickMdnsInterface）：
    // env JUSCITE_TEAM_MDNS_IF 显式钉定 > 自动选主 IPv4（排除 CGNAT）> null=库默认全网卡。
    const mdnsIf = pickMdnsInterface(os.networkInterfaces(), process.env.JUSCITE_TEAM_MDNS_IF);
    net.bonjour = new Bonjour(mdnsIf ? { interface: mdnsIf } : {});
    const name = `juscite-${id.memberId.slice(0, 8)}`;
    net.published = net.bonjour.publish({
      name, host: `juscite-${id.memberId.slice(0, 8)}.local`, port: net.port, type: TEAM_MDNS_TYPE,
      txt: { tid: id.teamId, tname: id.teamName, mid: id.memberId, role: id.role },
    });
    net.running = true;
    net.timer = setInterval(() => { void runSyncRound().catch((e) => console.error("[team] period sync:", e?.message ?? e)); }, periodMs);
    console.log(`[team] net started on :${net.port} (mdns ${TEAM_MDNS_TYPE}${mdnsIf ? ", if " + mdnsIf : ""}, period ${Math.round(periodMs / 1000)}s)`);
    return true;
  }
  function stopNet() {
    if (net.timer) { clearInterval(net.timer); net.timer = null; }
    try { net.published?.stop?.(); } catch { /* 尽力停广播 */ }
    try { net.bonjour?.destroy?.(); } catch { /* 尽力销毁 */ }
    try { net.server?.close?.(); } catch { /* 尽力关监听 */ }
    net.published = null; net.bonjour = null; net.server = null;
    net.running = false; net.port = null; net.lastReport = null;
    joinTargets.clear();
  }
  function startIfConfigured() {
    if (!identity()) return false;
    void startNet().then(() => { void runSyncRound().catch(() => {}); }) // F3：启动先跑一轮（失败静默记日志）
      .catch((e) => console.error("[team] autostart failed:", e?.message ?? e));
    return true;
  }

  // ── 被踢惰性处理（F16 等量）：读到一次性通知或（非团队长）当前名单无我→自动清本机三表与身份→
  // 返回一次性提示（teamName 只在本次返回中出现，取走即清）。──
  function consumeKickedIfAny() {
    const id = identity();
    if (!id) return null;
    const noticeRaw = store.teamGetState("kicked_notice");
    let teamName = null;
    if (noticeRaw) {
      try { teamName = JSON.parse(noticeRaw)?.teamName ?? id.teamName; } catch { teamName = id.teamName; }
    } else if (id.role !== "leader") {
      const signed = rosterState();
      if (signed && !memberEntryOf(signed.roster, id.memberId)) teamName = signed.roster.teamName;
    }
    if (!teamName) return null;
    store.teamClearAll(); // 三表清（F15：snapshots+state+edits）
    clearIdentity();
    stopNet();
    console.log(`[team] local team data cleared (kicked/left: ${teamName})`);
    return { teamName };
  }

  // ── 命令面（等量语义；文案自写）──
  function status() {
    const kicked = consumeKickedIfAny();
    if (kicked) return { configured: false, kickedFrom: kicked.teamName };
    const id = identity();
    if (!id) return { configured: false, netRunning: false };
    const signed = rosterState();
    return {
      configured: true,
      team: { teamId: id.teamId, teamName: id.teamName, memberId: id.memberId, myName: id.myName, role: id.role,
        memberCount: signed?.roster.members.length ?? 1 },
      // 配对码仅团队长展示（E1）；身份内层永不携带 secret/配对码（F14 剥密在 sanitizeValueForFrontend）
      pairingCode: id.role === "leader" ? id.pairingCode : null,
      netRunning: net.running, port: net.port,
    };
  }

  function createTeam({ teamName, myName }) {
    const name = String(teamName ?? "").trim();
    const who = String(myName ?? "").trim();
    if (!name) throw new Error("团队名不能为空");
    if (!who) throw new Error("你的姓名不能为空");
    if (identity()) throw new Error("已加入团队，请先退出当前团队再创建");
    const id = newTeamIdentity({ teamName: name, myName: who });
    const signed = signRoster(newLeaderRoster(id), id.teamSecret); // roster seq=1 仅自己（A5）
    saveIdentity(id);
    saveRosterState(signed);
    store.teamSetState("own_seq", "0");
    rebuildOwnSnapshot();
    auditWrite?.("team.create", id.teamId, `创建团队「${name}」（成员 ${who}）`);
    void startNet().then(() => { void runSyncRound().catch(() => {}); }).catch((e) => console.error("[team] create start:", e?.message ?? e));
    return status();
  }

  // 入团扫描（A6-A8）：浏览约 3 秒，按团队聚合（团队名+在线数+团队长在线否），按团队名升序。
  async function discover() {
    if (identity()) throw new Error("已加入团队，请先退出当前团队再搜索");
    const list = await browseTargets(discoverMs);
    const byTeam = new Map();
    for (const t of list) {
      const cur = byTeam.get(t.tid) ?? { teamId: t.tid, teamName: t.tname || "（未命名团队）", online: 0, leaderOnline: false, host: t.host, port: t.port };
      cur.online++;
      if (t.role === "leader") { cur.leaderOnline = true; cur.host = t.host; cur.port = t.port; }
      byTeam.set(t.tid, cur);
    }
    const out = [...byTeam.values()].sort((a, b) => (a.teamName < b.teamName ? -1 : a.teamName > b.teamName ? 1 : 0));
    joinTargets.clear();
    for (const t of out) joinTargets.set(t.teamId, t);
    return out;
  }

  // 入团（A9/A10/F7/G3/G7）：对团队长 POST /join→验签名 roster→落身份→立即拉一轮（失败不拦断）。
  async function joinTeam({ teamId, code, myName, host, port }) {
    const who = String(myName ?? "").trim();
    if (!who) throw new Error("你的姓名不能为空");
    if (typeof code !== "string" || !/^\d{6}$/.test(code)) throw new Error("请输入 6 位数字配对码");
    if (identity()) throw new Error("已加入团队，请先退出当前团队再加入");
    const t = (typeof host === "string" && Number.isInteger(port))
      ? { host, port }
      : joinTargets.get(String(teamId ?? ""));
    if (!t) throw new Error("没有找到该团队的团队长在线实例，请确认团队长已打开应用并重新搜索");
    const memberId = randomUUID();
    const bytes = Buffer.from(JSON.stringify({ teamId: String(teamId ?? ""), code, memberName: who, memberId }), "utf-8");
    const res = await fetch(`http://${t.host}:${t.port}${TEAM_HTTP_PATH_JOIN}`, {
      method: "POST",
      headers: { "content-type": "application/json", "content-length": String(bytes.length) },
      body: new Uint8Array(bytes),
      signal: AbortSignal.timeout(TEAM_HTTP_TIMEOUT_MS),
    });
    const resBytes = Buffer.from(await res.arrayBuffer());
    let payload = null;
    try { payload = JSON.parse(resBytes.toString("utf-8")); } catch { payload = null; }
    if (!res.ok) throw new Error(payload?.error ?? `HTTP ${res.status}`); // 后端人话错误透传（A10）
    if (!payload || typeof payload.teamSecret !== "string"
      || !isWellFormedSignedRoster(payload.roster)
      || !verifyRosterSig(payload.roster, payload.teamSecret)) {
      throw new Error("入团响应校验失败（签名不符），请重新加入"); // 验签名 roster 后才落身份
    }
    if (!memberEntryOf(payload.roster.roster, memberId)) throw new Error("入团响应未包含本机成员，请重新加入");
    const id = {
      teamId: payload.teamId, teamName: payload.teamName, teamSecret: payload.teamSecret,
      memberId, myName: who, role: "member", pairingCode: "000000", // 成员不持有配对码（占位满足形状校验）
    };
    saveIdentity(id);
    saveRosterState(payload.roster);
    store.teamSetState("own_seq", "0");
    rebuildOwnSnapshot();
    auditWrite?.("team.join", id.teamId, `加入团队「${id.teamName}」（成员 ${who}）`);
    void startNet().then(() => { void runSyncRound().catch(() => {}); }) // G7：立即拉一轮，失败不拦断入团
      .catch((e) => console.error("[team] join start:", e?.message ?? e));
    return status();
  }

  // 退出/解散（E6/E7/E9 口径分层）：成员=只清本机（不改 roster 不广播不通知任何人）；
  // 团队长=解散：签发空名单墓碑+尽力广播一轮（在场成员当场走被踢清理；不在线成员靠后续接力或手动退出）。
  async function leaveTeam({ targets = null } = {}) {
    const id = identity();
    if (!id) return { cleared: false };
    if (id.role === "leader") {
      const signed = rosterState();
      const tombstone = resignRoster({ ...signed.roster, members: [] }, id.teamSecret); // 空名单墓碑 seq+1
      let list = targets;
      if (!list) { try { list = net.running ? await browseTargets(browseMs) : []; } catch { list = []; } }
      const body = { teamId: id.teamId, fromMember: id.memberId, snapshots: [], roster: tombstone, edits: [] };
      const bytes = Buffer.from(JSON.stringify(body), "utf-8");
      for (const t of list) { // 尽力广播：逐台试，失败不打断（无服务器的诚实边界）
        try {
          await fetch(`http://${t.host}:${t.port}${TEAM_HTTP_PATH_EXCHANGE}`, {
            method: "POST",
            headers: { "content-type": "application/json", "x-team-auth": hmacOf(id.teamSecret, bytes) },
            body: new Uint8Array(bytes), signal: AbortSignal.timeout(TEAM_HTTP_TIMEOUT_MS),
          });
        } catch { /* 尽力 */ }
      }
      auditWrite?.("team.dissolve", id.teamId, `解散团队「${id.teamName}」`);
    } else {
      auditWrite?.("team.leave", id.teamId, `退出团队「${id.teamName}」`);
    }
    stopNet();
    store.teamClearAll(); // 退团清三表（F15：漏清会把旧团队内容接力外带进新团队）
    clearIdentity();
    return { cleared: true };
  }

  // 移出成员（E5）：确认在调用方；roster 删人 seq+1 重签→后台立即同步传播；不能移出自己。
  async function kickMember(memberId) {
    const id = identity();
    const signed = rosterState();
    if (!id || !signed || id.role !== "leader") throw new Error("仅团队长可以移出成员");
    if (memberId === id.memberId) throw new Error("不能移出自己（如需退出请使用解散）");
    if (!memberEntryOf(signed.roster, memberId)) throw new Error("该成员不在名单中");
    const roster = { ...signed.roster, members: signed.roster.members.filter((m) => m.memberId !== memberId) };
    const fresh = resignRoster(roster, id.teamSecret);
    saveRosterState(fresh);
    auditWrite?.("team.kick", memberId, `将成员移出「${id.teamName}」`);
    void runSyncRound().catch(() => {}); // 后台立即传播
    return status();
  }

  // 逐人权限（E4）：可见范围=全队(null)或自定义多选（自己恒可见）；可编辑=多选（子集语义）；
  // 保存→seq+1 重签→随下次同步生效。
  async function setPermissions(memberId, view, edit) {
    const id = identity();
    const signed = rosterState();
    if (!id || !signed || id.role !== "leader") throw new Error("仅团队长可以修改成员权限");
    const entry = memberEntryOf(signed.roster, memberId);
    if (!entry) throw new Error("该成员不在名单中");
    let viewNorm;
    if (view === null || view === "all") viewNorm = null;
    else if (Array.isArray(view)) {
      viewNorm = [...new Set(view.filter((x) => typeof x === "string" && x))];
      if (!viewNorm.includes(memberId)) viewNorm.push(memberId); // 自己恒可见
    } else throw new Error("可见范围须为 null（全队）或成员标识数组");
    const editNorm = [...new Set((Array.isArray(edit) ? edit : []).filter((x) => typeof x === "string" && x))];
    if (viewNorm !== null && editNorm.some((x) => !viewNorm.includes(x))) {
      throw new Error("可编辑名单必须是可见名单的子集（编辑功能先要可见）");
    }
    const roster = { ...signed.roster, members: signed.roster.members.map((m) => (
      m.memberId === memberId ? { ...m, view: viewNorm, edit: editNorm } : m)) };
    const fresh = resignRoster(roster, id.teamSecret);
    saveRosterState(fresh);
    void runSyncRound().catch(() => {}); // 保存→即时触发一轮（§3 同步轮触发面）
    return status();
  }

  // 刷新配对码（E1/G4）：仅团队长；旧码立即作废。
  function refreshCode() {
    const id = identity();
    if (!id) throw new Error("尚未加入团队");
    if (id.role !== "leader") throw new Error("仅团队长可以刷新配对码");
    const fresh = { ...id, pairingCode: makePairingCode() };
    saveIdentity(fresh);
    return { pairingCode: fresh.pairingCode };
  }

  // 立即同步（B4）：转圈/结果汇总在 UI；报告={在场人数,更新快照数,失败数,errors 逐台}。
  async function syncNow() {
    const id = identity();
    if (!id) throw new Error("尚未加入团队");
    return runSyncRound();
  }

  // 团队视图（B15）：可见权限过滤在后端完成；自己案件现查现重建（我在看板永远最新，不落库不动 seq）。
  function view() {
    const kicked = consumeKickedIfAny();
    if (kicked) return { configured: false, kickedFrom: kicked.teamName };
    const id = identity();
    const signed = rosterState();
    if (!id || !signed) return { configured: false };
    const roster = signed.roster;
    const visible = roster.members.filter((m) => canViewMember(roster, id.memberId, m));
    const visibleIds = new Set(visible.map((m) => m.memberId));
    const freshPayload = projectCaseSnapshot(projectCaseRows(), todayStr());
    const members = visible.map((m) => {
      if (m.memberId === id.memberId) {
        return { ...m, isMe: true, snapshot: { seq: ownSeq(), updatedAt: new Date().toISOString(), payload: freshPayload } };
      }
      const row = store.teamGetSnapshot(m.memberId);
      let snapshot = null;
      if (row) {
        let payload = null;
        try { payload = JSON.parse(row.payload_json ?? "null"); } catch { payload = null; }
        snapshot = { seq: row.seq, updatedAt: row.updated_at, payload };
      }
      return { ...m, isMe: false, snapshot };
    });
    // 相关编辑记录=目标在我可见名单内的行 + 我提交的行（含 pending，C3 待生效行数据源）
    const edits = store.teamListEditsRelated([...visibleIds], id.memberId, TEAM_EDITS_WINDOW).map(editRowFromStore);
    return {
      configured: true,
      team: { teamId: id.teamId, teamName: id.teamName, memberId: id.memberId, myName: id.myName, role: id.role,
        memberCount: roster.members.length },
      rosterSeq: roster.seq,
      members, edits,
    };
  }

  // 提交备注编辑（D2/D3/D4/D5）：仅 note 字段（本产品无遗留状态路径）；1..500 字；可见即可写；
  // 提交即本机落 pending 并后台立即触发一轮同步。
  function submitEdit({ targetMemberId, caseId, caseName, note }) {
    const id = identity();
    const signed = rosterState();
    if (!id || !signed) throw new Error("尚未加入团队");
    if (typeof note !== "string" || !note.trim()) throw new Error("备注内容不能为空");
    if (note.length > TEAM_NOTE_MAX) throw new Error(`备注不能超过 ${TEAM_NOTE_MAX} 字`);
    const target = memberEntryOf(signed.roster, String(targetMemberId ?? ""));
    if (!target) throw new Error("目标成员不在团队名单中");
    if (!canViewMember(signed.roster, id.memberId, target)) throw new Error("该成员的案件对你不可见，无法备注");
    const selfCase = target.memberId === id.memberId; // 给自己案件备注：立即生效不待接力（C4）
    const row = {
      id: "te_" + randomUUID().slice(0, 8), team_id: id.teamId, editor_id: id.memberId, editor_name: id.myName,
      target_member_id: target.memberId, case_id: String(caseId ?? ""), case_name: String(caseName ?? ""),
      field: TEAM_EDITABLE_FIELDS[0], value: note, prev_value: null,
      status: selfCase ? "applied" : "pending", created_at: new Date().toISOString(),
      applied_at: selfCase ? new Date().toISOString() : null,
    };
    store.teamPutEdit(row);
    if (!selfCase) void runSyncRound().catch(() => {}); // D3：后台立即触发一轮（对方不在线就等周期接力）
    return editRowFromStore(store.teamGetEdit(row.id));
  }

  // 撤销（D9/D10）：仅本人案件、仅 applied 可撤→reverted（备注隐藏；不回写本地案件数据）；
  // 撤销后重建本人快照并即时传播。
  function revertEdit(editId) {
    const id = identity();
    if (!id) throw new Error("尚未加入团队");
    const row = editRowFromStore(store.teamGetEdit(String(editId ?? "")));
    if (!row) throw new Error("编辑记录不存在");
    if (row.targetMemberId !== id.memberId) throw new Error("只能撤销队友对我案件的备注");
    if (row.status !== "applied") throw new Error("仅已生效的备注可以撤销");
    store.teamUpdateEditStatus(row.id, "reverted", null);
    void runSyncRound().catch(() => {}); // D10：即时传播
    return editRowFromStore(store.teamGetEdit(row.id));
  }

  return {
    status, createTeam, discover, joinTeam, leaveTeam, kickMember, setPermissions, refreshCode,
    syncNow, view, submitEdit, revertEdit,
    startIfConfigured, stopNet,
    netState: () => ({ running: net.running, port: net.port, syncing: net.syncing, lastReport: net.lastReport }),
    __test: { mergeIncoming, rebuildOwnSnapshot, identity, rosterState, browseTargets, runSyncRound, exchangeOne }, // 合成自测观察面（不进 UI/命令面）
  };
}
