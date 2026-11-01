// #43 订阅引擎·UI 消费面合成自测（RE-43 §3.5；2026-10-30）。
// 隔离桥=:3090（ask 钉定自测隔离端口）+合成材料+全离线安全路径（不碰真 OpenAI 端点，
// 规格红线 §3.7；引擎全链真服务测试已由 implementation/tests/test_subscription_engine.py
// 13 用例承载，本测只锚消费面桥路+三分支页渲染）。
// 覆盖：status 投影信封／login_begin 回授权 URL（redirect_uri 钉回 :3090/auth/callback、
// scope 套餐用量位）／回调三分支页（state 不符=拒绝、缺 state=拒绝、error 重定向=拒绝、
// 渲染面三分支+未开套餐子提示）／models 未登录具名拒／chat 未登录无回落具名拒不伪答／
// logout 未知账号具名拒／未知端点 404 具名码。
// 用法：node --import tsx tools/bridge/subscription_ui_synthetic.mjs（末行 SUBSCRIPTION_UI_SYNTH_PASS，exit 0/1；
// 施工单-10 单元三起 subscription_service 经 @juscite/vizb shared/html.ts 出安全基模板，须 tsx 装载）。
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http_ from "node:http";
import {
  createSubscriptionService, loginBranchOf, loginBranchCopy,
  renderCallbackPage, subscriptionStateRoot, resolveSubscriptionEnginePath,
} from "./subscription_service.mjs";

const PORT = Number(process.env.SUBSCRIPTION_UI_TEST_PORT ?? 3090); // 可覆盖隔离端口（SHARE_TEST_PORT 同款；默认仍 3090）
const BASE = `http://127.0.0.1:${PORT}`;
let pass = 0;
let fail = 0;

function check(name, ok, detail) {
  if (ok) { pass += 1; console.log(`[subscription-ui-synth] ${name}: OK`); }
  else { fail += 1; console.error(`[subscription-ui-synth] ${name}: FAIL${detail ? " — " + detail : ""}`); }
}

async function req(path, init) {
  const r = await fetch(BASE + path, init);
  const text = await r.text();
  let json = null;
  try { json = JSON.parse(text); } catch { /* HTML 面 */ }
  return { status: r.status, text, json };
}

// ── 临时状态根（合成隔离；令牌只进引擎侧 vault 同一状态根下 siwc/ 分区）──
const stateRoot = mkdtempSync(join(tmpdir(), "juscite-siwc-ui-synth-"));
process.env.BRIDGE_SUBSCRIPTION_STATE_ROOT = stateRoot;

const service = createSubscriptionService({ port: PORT });
const server = http_.createServer(async (req, res) => {
  try {
    const handled = await service.httpHandler(req, res, new URL(req.url ?? "/", BASE));
    if (!handled) { res.writeHead(404); res.end("synth: not handled"); }
  } catch (e) {
    if (!res.headersSent) { res.writeHead(500, { "content-type": "application/json" }); }
    res.end(JSON.stringify({ status: "NOT_CONNECTED", code: "synth_internal:" + (e?.message ?? e) }));
  }
});
await new Promise((resolve) => server.listen(PORT, "127.0.0.1", resolve));

try {
  // 0. 引擎/状态根在位
  check("引擎路径解析在位", Boolean(resolveSubscriptionEnginePath()), resolveSubscriptionEnginePath() ?? "null");
  check("状态根 env 生效", subscriptionStateRoot() === stateRoot);

  // 1. status：OWNER_RESPONSE 信封+引擎投影（离线：无账号→不可用具名 siwc_not_logged_in）
  {
    const r = await req("/api/subscription/status");
    const ok = r.json?.status === "OWNER_RESPONSE"
      && r.json?.result?.engine === "siwc/1"
      && r.json?.result?.available === false
      && r.json?.result?.unavailableReason === "siwc_not_logged_in"
      && Array.isArray(r.json?.result?.accounts);
    check("status 投影信封+三查具名", ok, JSON.stringify(r.json)?.slice(0, 200));
  }

  // 2. login_begin：授权 URL 钉回本桥回调+state+套餐用量 scope（离线纯本地构造）
  let state = "";
  {
    const r = await req("/api/subscription/login_begin", { method: "POST" });
    const url = String(r.json?.result?.authorizationUrl ?? "");
    state = String(r.json?.result?.state ?? "");
    const u = new URL(url);
    const ok = r.json?.status === "OWNER_RESPONSE"
      && u.pathname.endsWith("/authorize")
      && u.searchParams.get("redirect_uri") === `${BASE}/auth/callback`
      && u.searchParams.get("code_challenge_method") === "S256"
      && (u.searchParams.get("scope") ?? "").includes("chatgpt.tokens.use.direct")
      && state.length > 0
      && r.json?.result?.redirectUri === `${BASE}/auth/callback`;
    check("login_begin 授权 URL 钉回 :3090/auth/callback+PKCE+用量 scope", ok, url.slice(0, 160));
  }

  // 3. 回调三分支页（全部离线路径）
  {
    const r1 = await req(`/auth/callback?code=x&state=bogus-state`);
    check("回调 state 不符→拒绝分支页", r1.text.includes('data-branch="rejected"')
      && r1.text.includes("登录被拒绝"), r1.text.slice(0, 120));
    const r2 = await req("/auth/callback?code=x");
    check("回调缺 state→拒绝分支页", r2.text.includes('data-branch="rejected"'));
    const r3 = await req("/auth/callback?error=access_denied&state=missing");
    check("授权错误重定向→拒绝分支页（含错误码）", r3.text.includes('data-branch="rejected"')
      && r3.text.includes("access_denied"));
    // 渲染面：成功（未开套餐=具名子提示；已开套餐=不含）/超时回显码/拒绝锚+testid
    const okPage = renderCallbackPage("success", null, false).includes("未开通套餐用量")
      && !renderCallbackPage("success", null, true).includes("未开通套餐用量")
      && renderCallbackPage("timeout", "siwc_login_window_expired").includes("siwc_login_window_expired")
      && renderCallbackPage("rejected", "siwc_state_mismatch").includes('data-branch="rejected"')
      && renderCallbackPage("success", null, true).includes('data-testid="login-callback-page"');
    check("三分支页渲染面（成功含未开套餐/超时回显码/拒绝锚）", okPage);
    // 桥侧 loginBranchOf 与 kernel 合同同形
    check("桥侧三分支判定合同", loginBranchOf(null) === "success"
      && loginBranchOf("siwc_login_window_expired") === "timeout"
      && loginBranchOf("siwc_exchange_unreachable:http_503") === "timeout"
      && loginBranchOf("siwc_id_token_nonce_mismatch") === "rejected"
      && loginBranchCopy("success").title.length > 0);
  }

  // 4. models：未登录→具名拒（离线 fail-closed）
  {
    const r = await req("/api/subscription/models");
    check("models 未登录具名拒", r.json?.status === "NOT_CONNECTED"
      && String(r.json?.code).startsWith("siwc_"), r.json?.code);
  }

  // 5. chat：未登录且未配回落→具名拒不伪答（规格 §2.3：不静默）
  {
    const r = await req("/api/subscription/chat", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ input: "合成试驾" }),
    });
    check("chat 未登录无回落具名拒不伪答", r.json?.status === "NOT_CONNECTED"
      && r.json?.code === "siwc_not_logged_in", r.json?.code);
  }

  // 6. logout：未知账号→具名拒
  {
    const r = await req("/api/subscription/logout", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ sub: "no-such-sub" }),
    });
    check("logout 未知账号具名拒", r.json?.status === "NOT_CONNECTED"
      && r.json?.code === "siwc_account_unknown", r.json?.code);
  }

  // 7. 未知端点 404 具名码
  {
    const r = await req("/api/subscription/nope");
    check("未知端点 404 具名码", r.status === 404
      && r.json?.code === "subscription_endpoint_unknown");
  }

  // 8. login_begin 发起的 pending state 已在引擎窗内：用真 state 走假 code 会打授权服务器
  //    （离线安全红线不碰）——故此处不消耗真 state，留窗自然过期（10 分钟一次性）。
  check("真 state 不做网络消耗（离线红线）", state.length > 0);
} finally {
  await new Promise((resolve) => server.close(resolve));
  try { rmSync(stateRoot, { recursive: true, force: true }); } catch { /* 尽力而为 */ }
}

console.log(`[subscription-ui-synth] PASS ${pass} FAIL ${fail}`);
if (fail > 0) { console.error("SUBSCRIPTION_UI_SYNTH_FAIL"); process.exit(1); }
console.log("SUBSCRIPTION_UI_SYNTH_PASS");
process.exit(0);
