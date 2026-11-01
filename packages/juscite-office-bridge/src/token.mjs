// bootstrapToken 生命周期：签发（随机 32B base64url + 过期时刻）→ 校验（缺失/不匹配/过期一律
// 归并同一错误码，不给探测者区分口径）→ 轮换（配对成功即作废旧 token，发现文件同步重写）。
import { randomBytes } from "node:crypto";

export function createBootstrapToken(ttlMs = 15 * 60_000) {
  const now = Date.now();
  return { value: randomBytes(32).toString("base64url"), issuedAt: now, expiresAt: now + ttlMs };
}

// 'ok' = 放行；'stale' = 缺失/不匹配/过期（服务端统一映射为 bootstrap_token_invalid）
export function verifyBootstrapToken(record, presented, now = Date.now()) {
  if (typeof presented !== "string" || !record || presented !== record.value) return "stale";
  if (now >= record.expiresAt) return "stale";
  return "ok";
}
