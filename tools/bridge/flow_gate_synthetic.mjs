#!/usr/bin/env node
// 【施工单-06·机制规格-01】审批关卡 gate 节点合成自测（ci_gate fast 随行步）。
// 全合成材料：库=临时目录 node:sqlite，零 %APPDATA% 触碰，无真实案件无人名。
// 覆盖规格验收断言：A1 并发 CAS（旧版本先赢后输）/ A2 强转交缺 reason/acknowledged 拒、
// 成功落 force_transfer 事件含 from/to_version / A3 无锁路径不存在 / A4 转给自己拒 /
// A5 事件流重放全程。纯 Node 零依赖；单命令 exit 0/1，末行 FLOWGATE_SYNTH_PASS 可判。
// 用法：node tools/bridge/flow_gate_synthetic.mjs
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";

const dir = mkdtempSync(join(tmpdir(), "juscite-flowgate-synth-"));
let passed = 0, failed = 0;
function ok(n, msg) { passed += 1; console.log(`[flowgate-synth] ${n}: OK ${msg}`); }
function fail(n, msg, detail) { failed += 1; console.error(`[flowgate-synth] ${n}: FAIL ${msg}${detail ? `\n  ${detail}` : ""}`); }

function freshDb(file) {
  const db = new DatabaseSync(file);
  db.exec(`CREATE TABLE IF NOT EXISTS flow_nodes (
    id TEXT PRIMARY KEY, instance_code TEXT NOT NULL, node_code TEXT NOT NULL,
    node_type TEXT NOT NULL DEFAULT 'gate',
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','SUPERSEDED','SKIPPED')),
    assignee_user TEXT, lock_version INTEGER NOT NULL DEFAULT 1,
    payload_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`);
  db.exec(`CREATE TABLE IF NOT EXISTS flow_node_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('created','process','transfer','force_transfer')),
    action TEXT, actor_user TEXT NOT NULL, target_user TEXT, reason TEXT,
    from_version INTEGER NOT NULL, to_version INTEGER NOT NULL, created_at TEXT NOT NULL)`);
  return db;
}
const { createFlowGate, FlowGateError } = await import("./flow_gate_service.mjs");
const db = freshDb(join(dir, "fg.db"));
const gate = createFlowGate(db);
const tryCode = (fn) => { try { fn(); return null; } catch (e) { return e; } };

// ── 用例 1：建节点 PENDING v1 + created 事件；缺字段 VALIDATION ──
{
  const { node, events } = gate.createNode({ instanceCode: "syn-inst-001", nodeCode: "gate-review", assigneeUser: "张律师", payload: { 摘要: "合成审批事项" } });
  const e1 = tryCode(() => gate.createNode({ nodeCode: "x" }));
  if (node.status === "PENDING" && node.lockVersion === 1 && node.assigneeUser === "张律师"
    && events.length === 1 && events[0].eventType === "created" && events[0].fromVersion === 0 && events[0].toVersion === 1
    && e1?.code === "VALIDATION") ok(1, "建节点+created 事件+缺字段拒");
  else fail(1, "建节点语义不过", JSON.stringify({ node, e1: e1?.code }));
}

// ── 用例 2（A3/A1）：无锁路径不存在（缺 expectedVersion=VALIDATION）；旧版本=CONFLICT 回 currentVersion ──
{
  const { node } = gate.createNode({ instanceCode: "syn-inst-001", nodeCode: "gate-a3", assigneeUser: "张律师" });
  const noLock = tryCode(() => gate.process(node.id, { actor: "张律师", action: "approve" }));
  const stale = tryCode(() => gate.process(node.id, { actor: "张律师", action: "approve", expectedVersion: 99 }));
  const staleT = tryCode(() => gate.transfer(node.id, { actor: "张律师", targetUser: "李律师", reason: "合成", expectedVersion: 99 }));
  const cur = gate.getNode(node.id).node;
  if (noLock?.code === "VALIDATION" && stale?.code === "CONFLICT" && stale?.currentVersion === 1
    && staleT?.code === "CONFLICT" && staleT?.currentVersion === 1 && cur.lockVersion === 1 && cur.status === "PENDING")
    ok(2, "无锁路径不存在+CONFLICT 带 currentVersion+节点未被污染");
  else fail(2, "乐观锁语义不过", JSON.stringify({ noLock: noLock?.code, stale: stale?.code, staleT: staleT?.code, cur }));
}

// ── 用例 3（A1）：A、B 各持 v=1，A 先 approve 成功，B 再提→CONFLICT(v=2)，界面刷新不重放 ──
{
  const { node } = gate.createNode({ instanceCode: "syn-inst-001", nodeCode: "gate-a1", assigneeUser: "张律师" });
  gate.process(node.id, { actor: "张律师", action: "approve", expectedVersion: 1 });
  const late = tryCode(() => gate.process(node.id, { actor: "李律师", action: "approve", expectedVersion: 1 }));
  const after = gate.getNode(node.id).node;
  if (late?.code === "CONFLICT" && late.currentVersion === 2 && late.status === "APPROVED"
    && after.status === "APPROVED" && after.lockVersion === 2
    && tryCode(() => gate.process(node.id, { actor: "李律师", action: "reject", expectedVersion: 2 }))?.code === "CONFLICT")
    ok(3, "旧画面决定不重放+终态封版");
  else fail(3, "并发 CAS 不过", JSON.stringify({ late: late?.code, after }));
}

// ── 用例 4：reject 终态 + action 白名单 ──
{
  const { node } = gate.createNode({ instanceCode: "syn-inst-001", nodeCode: "gate-rej", assigneeUser: "张律师" });
  const bad = tryCode(() => gate.process(node.id, { actor: "张律师", action: "delegate", expectedVersion: 1 }));
  const { node: done } = gate.process(node.id, { actor: "张律师", action: "reject", comment: "材料不全", expectedVersion: 1 });
  if (bad?.code === "VALIDATION" && done.status === "REJECTED") ok(4, "action 白名单+reject 终态");
  else fail(4, "reject 语义不过", JSON.stringify({ bad: bad?.code, done }));
}

// ── 用例 5（R3/A4）：转办——reason 必填/不能转给自己/成功=换人回 PENDING 版本+1 ──
{
  const { node } = gate.createNode({ instanceCode: "syn-inst-001", nodeCode: "gate-xfer", assigneeUser: "张律师" });
  const noReason = tryCode(() => gate.transfer(node.id, { actor: "张律师", targetUser: "李律师", reason: "  ", expectedVersion: 1 }));
  const toSelf = tryCode(() => gate.transfer(node.id, { actor: "张律师", targetUser: "张律师", reason: "合成", expectedVersion: 1 }));
  const { node: moved, events } = gate.transfer(node.id, { actor: "张律师", targetUser: "李律师", reason: "张律师出庭委托", expectedVersion: 1 });
  const ev = events.at(-1);
  if (noReason?.code === "VALIDATION" && toSelf?.code === "VALIDATION"
    && moved.status === "PENDING" && moved.assigneeUser === "李律师" && moved.lockVersion === 2
    && ev.eventType === "transfer" && ev.reason === "张律师出庭委托" && ev.fromVersion === 1 && ev.toVersion === 2)
    ok(5, "转办合同三连+换人回 PENDING+事件留痕");
  else fail(5, "转办语义不过", JSON.stringify({ noReason: noReason?.code, toSelf: toSelf?.code, moved, ev }));
}

// ── 用例 6（R4/A2）：强制转交——缺 acknowledged 拒；确认后成，force_transfer 事件可还原现场 ──
{
  const { node } = gate.createNode({ instanceCode: "syn-inst-001", nodeCode: "gate-force", assigneeUser: "王律师" });
  const noAck = tryCode(() => gate.transfer(node.id, { actor: "发起人", targetUser: "李律师", reason: "超时未处理", expectedVersion: 1, force: true }));
  const { node: forced, events } = gate.transfer(node.id, {
    actor: "发起人", targetUser: "李律师", reason: "王律师休假超 48h 未处理，按规程转交", expectedVersion: 1, force: true, acknowledged: true,
  });
  const ev = events.at(-1);
  if (noAck?.code === "VALIDATION" && forced.assigneeUser === "李律师" && forced.lockVersion === 2
    && ev.eventType === "force_transfer" && ev.actorUser === "发起人" && ev.fromVersion === 1 && ev.toVersion === 2)
    ok(6, "强制转交确认门+事件留痕");
  else fail(6, "强转交语义不过", JSON.stringify({ noAck: noAck?.code, ev }));
}

// ── 用例 7：终态节点不可转交（CONFLICT）──
{
  const { node } = gate.createNode({ instanceCode: "syn-inst-001", nodeCode: "gate-term", assigneeUser: "张律师" });
  gate.process(node.id, { actor: "张律师", action: "approve", expectedVersion: 1 });
  const t = tryCode(() => gate.transfer(node.id, { actor: "发起人", targetUser: "李律师", reason: "合成", expectedVersion: 2, force: true, acknowledged: true }));
  if (t?.code === "CONFLICT" && t.status === "APPROVED") ok(7, "终态封版不可转交");
  else fail(7, "终态转交未拒", JSON.stringify({ t: t?.code }));
}

// ── 用例 8（A5）：事件流重放——单节点全生命周期版本链连续、可还原每步 ──
{
  const { node } = gate.createNode({ instanceCode: "syn-inst-001", nodeCode: "gate-replay", assigneeUser: "张律师" });
  gate.transfer(node.id, { actor: "张律师", targetUser: "李律师", reason: "一转", expectedVersion: 1 });
  gate.transfer(node.id, { actor: "李律师", targetUser: "王律师", reason: "二转", expectedVersion: 2, force: true, acknowledged: true });
  gate.process(node.id, { actor: "王律师", action: "approve", comment: "通过", expectedVersion: 3 });
  const { events } = gate.getNode(node.id);
  const chainOk = events.every((e, i) => e.fromVersion === (i === 0 ? 0 : events[i - 1].toVersion));
  const final = gate.getNode(node.id).node;
  if (events.length === 4 && chainOk && events[3].eventType === "process" && events[3].action === "approve"
    && final.status === "APPROVED" && final.lockVersion === 4) ok(8, "事件链 0→1→2→3→4 连续可重放");
  else fail(8, "重放链断裂", JSON.stringify({ events }));
}

// ── 用例 9：canForce 钩子拒权（FORBIDDEN）+ listNodes 过滤 ──
{
  const gate2 = createFlowGate(freshDb(join(dir, "fg2.db")), { canForce: (actor) => actor === "管理员" });
  const { node } = gate2.createNode({ instanceCode: "syn-inst-002", nodeCode: "gate-perm", assigneeUser: "王律师" });
  const denied = tryCode(() => gate2.transfer(node.id, { actor: "张律师", targetUser: "李律师", reason: "合成", expectedVersion: 1, force: true, acknowledged: true }));
  gate2.createNode({ instanceCode: "syn-inst-002", nodeCode: "gate-perm2", assigneeUser: "王律师" });
  const listed = gate2.listNodes({ instanceCode: "syn-inst-002", assigneeUser: "王律师" });
  if (denied?.code === "FORBIDDEN" && listed.length === 2) ok(9, "canForce 钩子拒权+listNodes 过滤");
  else fail(9, "权限钩子不过", JSON.stringify({ denied: denied?.code, listed: listed.length }));
}

console.log(`[flowgate-synth] ── ${passed} OK / ${failed} FAIL ──`);
if (failed > 0) { console.error("FLOWGATE_SYNTH_FAIL"); process.exit(1); }
console.log("FLOWGATE_SYNTH_PASS");
