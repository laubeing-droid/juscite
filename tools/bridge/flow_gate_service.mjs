// 审批关卡 gate 节点机制（机制规格-01，律见 lockVersion 乐观锁等量自写实现，2026-10-28）。
// 乐观锁全域（R1）：所有变更动作必须携带 expectedVersion（读时 lockVersion，写时回传），
// 缺省=VALIDATION 拒绝——不提供无锁路径。比对+推进在 BEGIN IMMEDIATE 事务内完成
// （单写者天然串行，无 TOCTOU），版本对不上→CONFLICT 回 currentVersion，由人刷新后重新决定——
// 永不自动重放人审决定（R2：旧画面上的"同意"不能默默算到改过之后的节点上）。
// 转交输入合同（R3）：reason 必填非空；不能转给自己。强制转交=逃生门（R4）：acknowledged
// 显式确认 + reason 必填；权限钩子 canForce 可注入（默认放行——真权限随 #35 Flow 引擎接入时接）。
// 审计留痕（R5）：每次变更落 flow_node_events 事件（含 from/to_version），任意节点可从事件流
// 重放全部改派与审批过程（A5）。改派后节点回 PENDING 等新处理人（版本+1）——TRANSFERRED 是
// 事件不是终态：节点还挂着，只是换了人。
// v1 收敛三动作 process(approve|reject)/transfer/force-transfer；加签/抄送/补件登记不做（规格-01 §五）。
import { randomUUID } from "node:crypto";

export class FlowGateError extends Error {
  // code: NOT_FOUND | VALIDATION | CONFLICT | FORBIDDEN；CONFLICT 附 currentVersion/status
  constructor(code, message, { currentVersion, status } = {}) {
    super(message); this.name = "FlowGateError"; this.code = code;
    if (code === "CONFLICT") { this.currentVersion = currentVersion; this.status = status; }
  }
}

const NODE_COLS = `id, instance_code, node_code, node_type, status, assignee_user,
  lock_version, payload_json, created_at, updated_at`;

function nowIso() { return new Date().toISOString(); }

function nodeToProtocol(r) {
  return {
    id: r.id, instanceCode: r.instance_code, nodeCode: r.node_code, nodeType: r.node_type,
    status: r.status, assigneeUser: r.assignee_user ?? null, lockVersion: r.lock_version,
    payload: JSON.parse(r.payload_json ?? "{}"),
    createdAt: r.created_at, updatedAt: r.updated_at,
  };
}

function eventToProtocol(e) {
  return {
    id: e.id, nodeId: e.node_id, eventType: e.event_type, action: e.action ?? null,
    actorUser: e.actor_user, targetUser: e.target_user ?? null, reason: e.reason ?? null,
    fromVersion: e.from_version, toVersion: e.to_version, createdAt: e.created_at,
  };
}

export function createFlowGate(db, { canForce } = {}) {
  const getRow = db.prepare(`SELECT ${NODE_COLS} FROM flow_nodes WHERE id = ?`);
  const eventsOf = db.prepare(`SELECT * FROM flow_node_events WHERE node_id = ? ORDER BY id ASC`);
  const assertForce = typeof canForce === "function" ? canForce : () => true;

  // 变更核心：比对+推进+事件落账在一个 IMMEDIATE 事务里（原子，A1/A4）。
  function mutate(nodeId, expectedVersion, apply) {
    if (!Number.isInteger(expectedVersion))
      throw new FlowGateError("VALIDATION", "expectedVersion 必填（整数，读自 lockVersion）——无锁路径不存在");
    db.exec("BEGIN IMMEDIATE");
    try {
      const r = getRow.get(nodeId);
      if (!r) throw new FlowGateError("NOT_FOUND", `节点不存在 ${nodeId}`);
      if (r.lock_version !== expectedVersion)
        throw new FlowGateError("CONFLICT", `版本已推进：你看到的是 v${expectedVersion}，当前 v${r.lock_version}，请刷新后重新决定`,
          { currentVersion: r.lock_version, status: r.status });
      const toVersion = apply(r);   // 事务内完成业务校验与行更新，返回新版本号
      db.exec("COMMIT");
      return toVersion;
    } catch (e) {
      db.exec("ROLLBACK");
      throw e;
    }
  }

  function insertEvent(nodeId, ev) {
    db.prepare(`INSERT INTO flow_node_events
        (node_id, event_type, action, actor_user, target_user, reason, from_version, to_version, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .run(nodeId, ev.eventType, ev.action ?? null, ev.actor, ev.target ?? null,
        ev.reason ?? null, ev.fromVersion, ev.toVersion, nowIso());
  }

  return {
    createNode({ instanceCode, nodeCode, nodeType = "gate", assigneeUser = null, payload = {} } = {}) {
      if (typeof instanceCode !== "string" || !instanceCode.trim()) throw new FlowGateError("VALIDATION", "instanceCode 必填");
      if (typeof nodeCode !== "string" || !nodeCode.trim()) throw new FlowGateError("VALIDATION", "nodeCode 必填");
      const id = "fgn_" + randomUUID().slice(0, 8);
      const ts = nowIso();
      db.prepare(`INSERT INTO flow_nodes
          (id, instance_code, node_code, node_type, status, assignee_user, lock_version, payload_json, created_at, updated_at)
          VALUES (?, ?, ?, ?, 'PENDING', ?, 1, ?, ?, ?)`)
        .run(id, instanceCode.trim(), nodeCode.trim(), nodeType, assigneeUser, JSON.stringify(payload ?? {}), ts, ts);
      insertEvent(id, { eventType: "created", actor: assigneeUser ?? "system", fromVersion: 0, toVersion: 1 });
      return this.getNode(id);
    },

    getNode(id) {
      const r = getRow.get(id);
      if (!r) throw new FlowGateError("NOT_FOUND", `节点不存在 ${id}`);
      return { node: nodeToProtocol(r), events: eventsOf.all(id).map(eventToProtocol) };
    },

    listNodes({ instanceCode, assigneeUser, status, limit = 50 } = {}) {
      const where = []; const args = [];
      if (instanceCode) { where.push("instance_code = ?"); args.push(instanceCode); }
      if (assigneeUser) { where.push("assignee_user = ?"); args.push(assigneeUser); }
      if (status) { where.push("status = ?"); args.push(status); }
      const sql = `SELECT ${NODE_COLS} FROM flow_nodes ${where.length ? "WHERE " + where.join(" AND ") : ""}
                   ORDER BY created_at DESC, id DESC LIMIT ?`;
      return db.prepare(sql).all(...args, Math.min(Math.max(Number(limit) || 50, 1), 200)).map(nodeToProtocol);
    },

    // 审批：action=approve|reject，PENDING→终态，节点封版（终态后任何变更=CONFLICT）。
    process(id, { actor, action, comment, expectedVersion } = {}) {
      if (typeof actor !== "string" || !actor.trim()) throw new FlowGateError("VALIDATION", "actor 必填");
      if (action !== "approve" && action !== "reject") throw new FlowGateError("VALIDATION", "action 仅 approve|reject");
      mutate(id, expectedVersion, (r) => {
        if (r.status !== "PENDING") throw new FlowGateError("CONFLICT", `节点已终态（${r.status}），审批决定不可再改`, { currentVersion: r.lock_version, status: r.status });
        const to = r.lock_version + 1;
        db.prepare(`UPDATE flow_nodes SET status = ?, lock_version = ?, updated_at = ? WHERE id = ?`)
          .run(action === "approve" ? "APPROVED" : "REJECTED", to, nowIso(), id);
        insertEvent(id, { eventType: "process", action, actor, reason: comment ?? null, fromVersion: r.lock_version, toVersion: to });
        return to;
      });
      return this.getNode(id);
    },

    // 转办/强制转交：reason 必填；不能转给当前处理人；force 需 acknowledged 显式确认 + canForce 钩子。
    transfer(id, { actor, targetUser, reason, expectedVersion, force = false, acknowledged = false } = {}) {
      if (typeof actor !== "string" || !actor.trim()) throw new FlowGateError("VALIDATION", "actor 必填");
      if (typeof targetUser !== "string" || !targetUser.trim()) throw new FlowGateError("VALIDATION", "targetUser 必填");
      if (typeof reason !== "string" || !reason.trim()) throw new FlowGateError("VALIDATION", "reason 必填——转交原因随审批记录留痕");
      if (force && acknowledged !== true)
        throw new FlowGateError("VALIDATION", "强制转交须 acknowledged=true（显式确认'我确认转交该审批任务，并记录转交原因'）");
      mutate(id, expectedVersion, (r) => {
        if (r.status !== "PENDING") throw new FlowGateError("CONFLICT", `节点已终态（${r.status}），不可转交`, { currentVersion: r.lock_version, status: r.status });
        if (targetUser.trim() === r.assignee_user) throw new FlowGateError("VALIDATION", "不能转给当前处理人本人");
        if (force && !assertForce(actor, r)) throw new FlowGateError("FORBIDDEN", "无强制转交权限");
        const to = r.lock_version + 1;
        db.prepare(`UPDATE flow_nodes SET assignee_user = ?, lock_version = ?, updated_at = ? WHERE id = ?`)
          .run(targetUser.trim(), to, nowIso(), id);
        insertEvent(id, {
          eventType: force ? "force_transfer" : "transfer", actor,
          target: targetUser.trim(), reason: reason.trim(), fromVersion: r.lock_version, toVersion: to,
        });
        return to;
      });
      return this.getNode(id);
    },
  };
}
