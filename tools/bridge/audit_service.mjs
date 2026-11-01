// 功能 #30 安全审计中心（RE-30 §3.2/§3.3）：桥侧 audit 哈希链存储。
// 三代哈希行为等量（自写实现）：v1=无密钥对 `id|actor|action|target|prev` 明文 base64url；
// v2=同 payload 的 HMAC-SHA256 base64url 存 "v2:" 前缀；v3=JSON 全字段
// [id,ts,actor,action,target,detail,prev] 的 HMAC 存 "v3:" 前缀。三代可混存一链整体验真。
// 单实例共享：全桥只建一个服务实例，写面统一走 appendAudit（对拍 52：不复制审计链函数副本）。
// 密钥存储等量说明（诚实偏差记账）：竞品走 DPAPI/Keychain 加密凭据库；桥运行时无加密凭据机制，
// 等价落同库 app_meta 键 "audit.hmac"——独立键命名空间=用途区分（审计密钥≠AI 服务凭据），
// 「存在但解不开→报错保留原密文、不轮换（fail-closed）」语义逐字保留：解码须为合法 base64 且
// 恰 32 字节，否则按解不开处理，进程以无密钥 v1 链继续可写（v2/v3 历史行验假）。
import { createHmac, randomBytes } from "node:crypto";

export const AUDIT_META_KEY = "audit.hmac";
export const AUDIT_DEFAULT_LIMIT = 200;

const AUDIT_COLS = "id, ts, actor, action, target, detail, prev_hash, hash";

function b64url(buf) {
  return Buffer.from(buf).toString("base64url");
}
// v1/v2 共用明文 payload（RE-30 §3.3：v2=同 payload 的 HMAC）
function v1Payload(row) {
  return `${row.id}|${row.actor}|${row.action}|${row.target}|${row.prev ?? ""}`;
}
function hmacB64url(key, payload) {
  return createHmac("sha256", key).update(payload, "utf-8").digest("base64url");
}
function v3Hash(key, row) {
  return "v3:" + hmacB64url(key, JSON.stringify([
    row.id, row.ts ?? null, row.actor, row.action, row.target, row.detail ?? null, row.prev ?? null,
  ]));
}
// 密钥只接受非空 Buffer（P12 等量：非 Buffer/空一律按无密钥处理）
function keyUsable(k) {
  return Buffer.isBuffer(k) && k.length > 0;
}

// 密钥初始化（RE-30 §3.3）：app_meta 查 audit.hmac；缺失→randomBytes(32) 存回；
// 存在但解不开→报错保留原密文、不轮换，返回 null（无密钥 v1 模式，v2/v3 行将验假）。
function loadOrCreateHmacKey(db) {
  const row = db.prepare("SELECT value FROM app_meta WHERE key = ?").get(AUDIT_META_KEY);
  if (!row) {
    const fresh = randomBytes(32);
    try {
      db.prepare(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
      ).run(AUDIT_META_KEY, fresh.toString("base64"));
      return fresh;
    } catch (e) {
      console.error("[bridge][audit] 审计密钥写入失败（原值未动）；本轮按无密钥 v1 链继续：", e?.message ?? e);
      return null;
    }
  }
  const raw = String(row.value ?? "");
  try {
    if (!/^[A-Za-z0-9+/]+={0,2}$/.test(raw)) throw new Error("不是合法 base64 密文");
    const buf = Buffer.from(raw, "base64");
    if (buf.length !== 32) throw new Error(`解码后长度 ${buf.length} ≠ 32 字节`);
    return buf;
  } catch (e) {
    console.error(
      "[bridge][audit] 审计密钥密文解不开（保留原密文不轮换，fail-closed）；本轮按无密钥 v1 链继续，v2/v3 历史行将验假：",
      e?.message ?? e,
    );
    return null;
  }
}

// 建服务实例。入参 db=node:sqlite DatabaseSync（迁移已跑完，app_meta/audit_log 可用）。
export function createAuditService(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS audit_log (
      id TEXT PRIMARY KEY,
      ts TEXT,
      actor TEXT,
      action TEXT,
      target TEXT,
      detail TEXT,
      prev_hash TEXT,
      hash TEXT
    )
  `);
  const key = loadOrCreateHmacKey(db);
  const qLast = db.prepare(`SELECT ${AUDIT_COLS} FROM audit_log ORDER BY rowid DESC LIMIT 1`);
  const qAll = db.prepare(`SELECT ${AUDIT_COLS} FROM audit_log ORDER BY rowid`);
  const qInsert = db.prepare(
    `INSERT INTO audit_log (${AUDIT_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  );

  // 追加即入链：prev=末行 hash（空链=null）；ts=新 ISO 时间戳；有密钥 v3 / 无密钥 v1。
  // 入参宽容（RE-30 §2.9 等量：渲染层可写任意 entry，无 actor/action 校验）；缺 id 自补
  // a-<ts36>-<rand4> 形（对拍 30：唯一+可读来源）；detail 只收字符串/可 JSON 化对象，敏感原文不落审计由调用方保证。
  function appendAudit(entry) {
    const e = entry ?? {};
    const prev = qLast.get()?.hash ?? null;
    const row = {
      id: typeof e.id === "string" && e.id ? e.id : `a-${Date.now().toString(36)}-${randomBytes(2).toString("hex")}`,
      ts: new Date().toISOString(),
      actor: typeof e.actor === "string" ? e.actor : null,
      action: typeof e.action === "string" ? e.action : null,
      target: typeof e.target === "string" ? e.target : null,
      detail: e.detail === undefined || e.detail === null ? null
        : typeof e.detail === "string" ? e.detail : JSON.stringify(e.detail),
      prev,
    };
    row.hash = keyUsable(key) ? v3Hash(key, row) : b64url(v1Payload(row));
    qInsert.run(row.id, row.ts, row.actor, row.action, row.target, row.detail, row.prev, row.hash);
    return true;
  }

  // 全表逐行验链（RE-30 §2.2/§3.3）：prev_hash 链接性+按存储前缀选代重算；空库=true。
  function verifyAuditChain() {
    let prev = null;
    for (const r of qAll.iterate()) {
      if ((r.prev_hash ?? null) !== prev) return false;
      const stored = r.hash ?? "";
      let ok;
      if (stored.startsWith("v3:")) {
        ok = keyUsable(key) && v3Hash(key, { ...r, prev: r.prev_hash ?? null }) === stored;
      } else if (stored.startsWith("v2:")) {
        ok = keyUsable(key) && "v2:" + hmacB64url(key, v1Payload({ ...r, prev: r.prev_hash })) === stored;
      } else {
        ok = b64url(v1Payload({ ...r, prev: r.prev_hash })) === stored;
      }
      if (!ok) return false;
      prev = stored;
    }
    return true;
  }

  // 启动自动迁移（幂等）：有密钥时全链重算 v3+prev，与现值不同才回写并计数；返回计数。
  function migrateAuditChainToHmac() {
    if (!keyUsable(key)) return 0;
    const rows = db.prepare(`SELECT rowid AS rid, ${AUDIT_COLS} FROM audit_log ORDER BY rowid`).all();
    const upd = db.prepare("UPDATE audit_log SET prev_hash = ?, hash = ? WHERE rowid = ?");
    let prev = null;
    let count = 0;
    for (const r of rows) {
      const hash = v3Hash(key, { id: r.id, ts: r.ts, actor: r.actor, action: r.action, target: r.target, detail: r.detail, prev });
      if (hash !== (r.hash ?? "") || (r.prev_hash ?? null) !== prev) {
        upd.run(prev, hash, r.rid);
        count += 1;
      }
      prev = hash;
    }
    return count;
  }

  // 最近 ≤limit 行（rowid 倒序八字段）；limit 为查询参数默认值，库内不裁剪（对拍 9/47）。
  function listAudit(limit) {
    const n = Number.isInteger(limit) && limit > 0 ? limit : AUDIT_DEFAULT_LIMIT;
    return db.prepare(`SELECT ${AUDIT_COLS} FROM audit_log ORDER BY rowid DESC LIMIT ?`).all(n);
  }

  // 反查（#5 冲突查重 F9 等量链的「CONFLICT_CONCLUSION_SET 审计反查」位）：目标是否发生过
  // 指定动作族之一。只读、不改链；actions=动作名数组，target=审计 target 列。
  function hasAudit(actions, target) {
    if (!Array.isArray(actions) || !actions.length || !target) return false;
    const ph = actions.map(() => "?").join(",");
    const row = db.prepare(`SELECT 1 FROM audit_log WHERE action IN (${ph}) AND target = ? LIMIT 1`)
      .get(...actions, target);
    return Boolean(row);
  }

  return { appendAudit, verifyAuditChain, migrateAuditChainToHmac, listAudit, hasAudit };
}
