// 【#21 安全层】工具决策审计（RE-21 增补 §2.8/§3.3；MingJuris 机制净室）。
// 每次决策一行 tool_audits（十一字段，DDL 同构规格 §3.3）；deny 也入账
// ——「模型试图跑 shell 被拒」正是事件复盘要看的，只记成功调用会让它隐形。
// 参数摘要红线（硬红线，规格 §3.3）：凭证形键值**替换而非截断**（token/
// secret/password/apikey/api_key/credential/authorization——掩码前缀也是
// 泄漏进用户可能外发的日志，值整串换占位符）；全文 300 字符截断；不可序
// 列化参数有兜底文案。写入 best-effort：无会话 id 不写、写失败吞掉不阻断
// 运行（不并入 RE-30 audit_log 主链、不强加 HMAC——竞品无完整性链，不为
// 其外加承诺；RE-30 面板后续可加「工具决策」过滤 tab 复用本表）。
// 查询：按会话升序全量返回（对拍 #35）。
import { randomUUID } from "node:crypto";

/** DDL 单源（迁移 0020 与合成自测共用同一份，防两处漂移——材料表先例）。 */
export const TOOL_AUDITS_DDL = `
      CREATE TABLE IF NOT EXISTS tool_audits (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL,
        run_id TEXT,
        tool_name TEXT NOT NULL,
        effect TEXT NOT NULL,        -- allow | ask | deny
        code TEXT NOT NULL,          -- 原因码闭集
        reason TEXT NOT NULL,        -- 给人看的原因（自写文案）
        policy_version INTEGER NOT NULL,
        user_decision TEXT,          -- allow | always | deny | NULL(未询问)
        args_summary TEXT NOT NULL,  -- 凭证键值已替换为占位符；≤300 字符
        created_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_tool_audits_conversation ON tool_audits(conversation_id, created_at);
`;

const AUDIT_COLS = "id, conversation_id, run_id, tool_name, effect, code, reason, policy_version, user_decision, args_summary, created_at";

// 凭证形键（小写比对；命中即整值替换——不是打码前缀，是替换）。
const CREDENTIAL_KEY_RE = /^(token|secret|password|apikey|api_key|credential|authorization)([_-].*)?$/i;

/** 参数摘要：凭证键值替换→300 字符截断→不可序列化兜底（三件套硬红线）。 */
export function summarizeArgs(args) {
  let text;
  try {
    let value = args;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      const redacted = { ...value };
      for (const key of Object.keys(redacted)) {
        if (CREDENTIAL_KEY_RE.test(key)) redacted[key] = "[已隐藏]";
      }
      value = redacted;
    }
    text = JSON.stringify(value);
  } catch {
    return "（参数不可序列化，已省略）"; // 拷贝/序列化任一失败都有兜底，绝不因摘要阻断
  }
  if (typeof text !== "string") return "（参数不可序列化，已省略）";
  return text.length > 300 ? text.slice(0, 300) : text;
}

/** 建服务实例。入参 db=node:sqlite DatabaseSync（迁移已跑完；服务侧
 * CREATE TABLE IF NOT EXISTS 幂等兜底，与 audit_service 先例同款）。 */
export function createToolAuditService(db) {
  db.exec(TOOL_AUDITS_DDL);
  const qInsert = db.prepare(
    `INSERT INTO tool_audits (${AUDIT_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  );
  const qList = db.prepare(
    `SELECT ${AUDIT_COLS} FROM tool_audits WHERE conversation_id = ? ORDER BY created_at ASC, rowid ASC`,
  );
  // 跨会话最近面（审计中心「工具决策」tab）：最近 ≤limit 行倒序（默认 200，
  // 与 audit.listAudit 同口径 audit_service.mjs:13）；同刻时间戳按 rowid 兜底保序。
  const qRecent = db.prepare(
    `SELECT ${AUDIT_COLS} FROM tool_audits ORDER BY created_at DESC, rowid DESC LIMIT ?`,
  );

  const mapRow = (r) => ({
    id: r.id,
    conversationId: r.conversation_id,
    runId: r.run_id,
    toolName: r.tool_name,
    effect: r.effect,
    code: r.code,
    reason: r.reason,
    policyVersion: r.policy_version,
    userDecision: r.user_decision,
    argsSummary: r.args_summary,
    createdAt: r.created_at,
  });

  /**
   * 决策入账（best-effort）：无 conversationId 不写；写失败吞掉不阻断运行。
   * @param entry {conversationId, runId?, toolName, effect, code, reason,
   *   policyVersion, userDecision?, args?}
   */
  function recordToolAudit(entry) {
    const e = entry ?? {};
    if (typeof e.conversationId !== "string" || !e.conversationId) return false;
    try {
      qInsert.run(
        typeof e.id === "string" && e.id ? e.id : ("ta-" + randomUUID()),
        e.conversationId,
        typeof e.runId === "string" && e.runId ? e.runId : null,
        String(e.toolName ?? ""),
        String(e.effect ?? ""),
        String(e.code ?? ""),
        String(e.reason ?? ""),
        Number.isInteger(e.policyVersion) ? e.policyVersion : 0,
        e.userDecision === "allow" || e.userDecision === "always" || e.userDecision === "deny"
          ? e.userDecision : null,
        summarizeArgs(e.args),
        new Date().toISOString(),
      );
      return true;
    } catch (err) {
      // 写入失败吞掉：审计是 best-effort，绝不阻断运行（规格 §2.8）。
      console.error("[bridge][tool-audit] 审计写入失败（不阻断运行）：", err?.message ?? err);
      return false;
    }
  }

  /** 按会话升序全量返回（对拍 #35）。 */
  function listToolAudits(conversationId) {
    if (typeof conversationId !== "string" || !conversationId) return [];
    return qList.all(conversationId).map(mapRow);
  }

  /** 跨会话最近 ≤limit 行倒序（默认 200；审计中心「工具决策」tab 消费）。 */
  function listToolAuditsRecent(limit) {
    const n = Number.isInteger(limit) && limit > 0 ? limit : 200;
    return qRecent.all(n).map(mapRow);
  }

  return { recordToolAudit, listToolAudits, listToolAuditsRecent };
}
