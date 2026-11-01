// 功能 #43 订阅型推理引擎·UI 消费面桥路（RE-43 §3.5 面行为合同，2026-10-30）。
// 引擎=implementation/python/subscription_engine.py，经 legal_entry 冻结方法组 subscription.*
// （legal_entry.py:704-713，main() --request-json/--config 一次性子进程：temp JSON 进、JSON 出，
// 与 citation_verify_service.mjs 同纪律；零密钥材料进桥——令牌只住引擎侧 credential_vault）。
// 端点族（消费面只读投影+登录动线，不含任何引擎内状态改写旁路）：
//   GET  /api/subscription/status                 → subscription.status（引擎/账号/可用三查投影）
//   POST /api/subscription/login_begin            → subscription.login_begin（redirect_port=桥自身
//                                                    端口，回调钉回本桥 /auth/callback；UI 零端口推断）
//   POST /api/subscription/logout {sub}           → subscription.logout（revoke≤3 试+清本地+留映射）
//   GET  /api/subscription/models?refresh=1        → subscription.models（「测试连接」=强刷模型列表：
//                                                    令牌+API 可达性零轮次消耗的具名探针）
//   POST /api/subscription/chat {input,...}       → subscription.chat（回执 backend/fallbackReason=
//                                                    用量提示条与回落提示的唯一数据源）
//   GET  /auth/callback?code=&state=（或 ?error=）→ subscription.login_callback → 登录回调三分支页
//                                                    （成功[含未开套餐提示]/拒绝/超时；RE-43 §3.5
//                                                    律台 server.js:529-544 同构、文案自写=表达隔离）
// 失败响应：HTTP 200＋{status:"NOT_CONNECTED", code} 信封（subscription_failed: 前缀剥除后透传
// typed siwc_* 码，legal_entry.py:3277-3284 同法；UI 具名呈现不白屏）。
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { cspMeta, htmlEscape, safeHtmlDocument } from "../../packages/juscite-vizb/src/shared/html.ts";

const ENGINE_TIMEOUT_MS = 120_000; // 登录/模型列表毫秒-秒级；对话轮非流式整读放宽到 120s

// 引擎路径解析：env 覆盖 > 随包布局（<bundle>/tools/bridge 相邻 ../../implementation/python）
// > dev 布局 cwd 向上 8 级扫描（citation_verify_service.mjs:29-43 同款）。
export function resolveSubscriptionEnginePath() {
  const env = process.env.BRIDGE_SUBSCRIPTION_ENGINE;
  if (env && existsSync(env)) return env;
  const bundled = fileURLToPath(new URL("../../implementation/python/legal_entry.py", import.meta.url));
  if (existsSync(bundled)) return bundled;
  let dir = process.cwd();
  for (let i = 0; i < 8 && dir; i++) {
    const cand = join(dir, "implementation", "python", "legal_entry.py");
    if (existsSync(cand)) return cand;
    const parent = resolve(dir, "..");
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

// 订阅状态根（index/账号登记；令牌不在此——只进引擎侧 vault）：env 覆盖（合成自测隔离）>
// %APPDATA%\Juscite\subscription（support_service.mjs:21-24 同款口径：APPDATA env 优先、homedir 回退）。
export function subscriptionStateRoot() {
  if (process.env.BRIDGE_SUBSCRIPTION_STATE_ROOT) return process.env.BRIDGE_SUBSCRIPTION_STATE_ROOT;
  const appData = process.env.APPDATA ?? join(homedir(), "AppData", "Roaming");
  return join(appData, "Juscite", "subscription");
}

// ── 登录回调三分支判定（与 @juscite/legal kernel/subscriptionUiModel.loginBranchOf 同合同；
// 桥侧独立实现——bridge 零 TS import，合同由两测各锚其面）──
export function loginBranchOf(code) {
  if (!code) return "success";
  if (code === "siwc_login_window_expired") return "timeout";
  if (String(code).startsWith("siwc_exchange_unreachable")) return "timeout";
  return "rejected";
}

// 三分支页文案（自写；RE-43 §3.5 律台同构=结构等量，表达隔离=逐句自写）。
// 未开套餐=成功分支内的具名子提示（scope 缺套餐用量位，引擎 account.planUsage=false 亲告）。
export function loginBranchCopy(branch, code, planUsage) {
  if (branch === "success") {
    return {
      title: "登录成功",
      detail: planUsage === false
        ? "订阅账号已连接本机，但该账号未开通套餐用量（scope 缺用量位）：对话轮将自动回落 API Key。"
        : "订阅账号已连接本机。回到应用「设置 → 订阅引擎」查看账号与模型列表。",
    };
  }
  if (branch === "timeout") {
    return {
      title: "登录未完成",
      detail: "授权等待超时或网络不可达，本次登录未生效。请回到应用重新发起登录（code: "
        + (code || "timeout") + "）。",
    };
  }
  return {
    title: "登录被拒绝",
    detail: "授权服务器或安全校验未通过，本机未保存任何令牌。请回到应用重新发起登录（code: "
      + (code || "rejected") + "）。",
  };
}

// 防注入（施工单-10 单元三）：code 来自回调 URL query（外部可达面），此前未转义直插 HTML=反射注入；
// 现一律 htmlEscape 后进模板，骨架走 @juscite/vizb 安全基模板（CSP default-src 'none' 起步，
// 样式收进 nonce 授权的 <style>，零内联事件属性）。
// 监控接线（逆向吸收波二·条 2）：声明 coreActions=打开/渲染；本页从此有一段 nonce 授权的
// 页脚本（上报打开/渲染三值结果），CSP 因此最小放开 connect-src 'self'（同源本地桥上报通道）。
export function renderCallbackPage(branch, code, planUsage) {
  const copy = loginBranchCopy(branch, code, planUsage);
  const tone = branch === "success" ? "#177a44" : branch === "timeout" ? "#8a6d1d" : "#b23c36";
  const bg = branch === "success" ? "#1d9e571a" : branch === "timeout" ? "#c9971d1a" : "#d0453e1a";
  const badge = branch === "success" ? "成功" : branch === "timeout" ? "超时" : "拒绝";
  const nonce = randomBytes(16).toString("base64");
  return safeHtmlDocument({
    title: "订阅引擎登录回调",
    csp: cspMeta({ nonce, connectSelf: true }),
    monitoring: { key: "subscription-callback", coreActions: ["打开", "渲染"] },
    style: `
  body { font-family: system-ui, sans-serif; margin: 0; display: flex; align-items: center;
    justify-content: center; min-height: 100vh; background: #f6f7f8; }
  main { background: #fff; border: 1px solid #e4e6e8; border-radius: 12px; padding: 32px 40px;
    max-width: 520px; text-align: center; }
  h1 { font-size: 20px; margin: 0 0 8px; color: ${tone}; }
  p { font-size: 14px; line-height: 1.6; color: #444; margin: 0; }
  .badge-row { margin: 20px 0 0; }
  .badge { display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: 12px;
    background: ${bg}; color: ${tone}; }
`,
    body:
      `<main data-testid="login-callback-page" data-branch="${branch}">`
      + `<h1 data-testid="login-callback-title">${htmlEscape(copy.title)}</h1>`
      + `<p data-testid="login-callback-detail">${htmlEscape(copy.detail)}</p>`
      + `<p class="badge-row"><span data-testid="login-callback-branch" class="badge">${badge}</span></p>`
      + "</main>",
    // 页脚本只做监控上报（页面本体为服务端渲染静态页；分支文案已转义进模板）：
    // 打开/渲染各报一次成功（脚本运行到此处=页面已打开且渲染完成；登录拒绝/超时是
    // 页面内容分支，不是页面打开/渲染失败）。
    script: {
      nonce,
      js: '(function () { var m = window.jusciteMonitor; if (!m) return;'
        + ' m.report("打开", "成功"); m.report("渲染", "成功"); })();',
    },
  });
}

export function createSubscriptionService({ port }) {
  // ── 引擎一次性子进程调用（legal_entry main 信封：OWNER_RESPONSE/NOT_CONNECTED）──
  function runEngine(method, args) {
    const engine = resolveSubscriptionEnginePath();
    if (!engine) return { notConnected: "subscription_engine_unavailable" };
    const work = mkdtempSync(join(tmpRoot(), "juscite-siwc-"));
    const reqPath = join(work, "request.json");
    const cfgPath = join(work, "config.json");
    try {
      writeFileSync(reqPath, JSON.stringify({ method, args: args ?? {} }), "utf-8");
      writeFileSync(cfgPath, JSON.stringify(engineConfig()), "utf-8");
      const py = process.env.BRIDGE_PYTHON || "python";
      const r = spawnSync(py, ["-X", "utf8", engine, "--request-json", reqPath, "--config", cfgPath], {
        encoding: "buffer", timeout: ENGINE_TIMEOUT_MS, cwd: resolve(engine, ".."), // 引擎同目录模块经 sys.path[0]（脚本目录）自取
      });
      if (r.error && r.error.code === "ENOENT") {
        return { notConnected: "subscription_python_unavailable" };
      }
      if (r.error || r.signal) return { notConnected: "subscription_engine_timeout_or_failed" };
      let envelope = null;
      try { envelope = JSON.parse((r.stdout ?? "").toString("utf-8").trim()); } catch { /* 具名拒 */ }
      if (!envelope || typeof envelope !== "object" || !("status" in envelope)) {
        return { notConnected: "subscription_engine_output_unreadable" };
      }
      if (envelope.status === "OWNER_RESPONSE") return { result: envelope.result };
      // NOT_CONNECTED 码剥 legal_entry 包装前缀，typed siwc_* 原样透传（零密钥材料，引擎红线）。
      const raw = String(envelope.code ?? "subscription_engine_not_connected");
      return { notConnected: raw.startsWith("subscription_failed:") ? raw.slice("subscription_failed:".length) : raw };
    } finally {
      try { rmSync(work, { recursive: true, force: true }); } catch { /* 尽力而为 */ }
    }
  }

  function tmpRoot() {
    return existsSync(process.env.TEMP || "/tmp") ? (process.env.TEMP || "/tmp") : ".";
  }

  function engineConfig() {
    // 状态根必填（引擎 siwc_state_root_not_configured fail-closed）；auth/api 域名 seam 由引擎侧
    // env（JUSCITE_SIWC_AUTH_BASE/JUSCITE_SIWC_API_BASE）承接，桥不重复传递（规格 §2.1#13）。
    return { subscription_state_root: subscriptionStateRoot() };
  }

  function send(res, code, obj) {
    if (res.headersSent) { res.end(); return; }
    res.writeHead(code, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify(obj));
  }

  function sendEnvelope(res, out) {
    if (out.notConnected) send(res, 200, { status: "NOT_CONNECTED", code: out.notConnected });
    else send(res, 200, { status: "OWNER_RESPONSE", result: out.result });
  }

  async function readJsonBody(req) {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    if (!chunks.length) return {};
    try { return JSON.parse(Buffer.concat(chunks).toString("utf-8")); } catch { return null; }
  }

  async function httpHandler(req, res, url) {
    const path = url.pathname;
    // ── OAuth 回调落地（浏览器整页；非 /api 族，先于 API 判定）──
    if (path === "/auth/callback") {
      if (url.searchParams.get("error")) {
        // 授权服务器错误重定向（用户拒绝等）：仍交引擎核销 state（一次性窗占用的真源在引擎），
        // code 置空——换令牌必败，落「拒绝」分支；state 缺失无物可核销，直接具名渲染。
        const urlError = url.searchParams.get("error");
        const state = url.searchParams.get("state");
        if (!state) return sendHtml(res, renderCallbackPage("rejected", urlError));
        const out = runEngine("subscription.login_callback", { code: "", state });
        const code = out.notConnected ?? "";
        // 页面回显授权错误码优先（用户在授权页看到的因由），引擎核销码兜底。
        return sendHtml(res, renderCallbackPage(loginBranchOf(code), urlError || code));
      }
      const code = url.searchParams.get("code");
      const state = url.searchParams.get("state");
      if (!state) return sendHtml(res, renderCallbackPage("rejected", "siwc_state_mismatch"));
      const out = runEngine("subscription.login_callback", { code: code ?? "", state });
      const errCode = out.notConnected ?? "";
      const planUsage = out.result?.account?.planUsage;
      return sendHtml(res, renderCallbackPage(loginBranchOf(errCode), errCode || "success", planUsage));
    }
    if (!path.startsWith("/api/subscription/")) return false;
    if (path === "/api/subscription/status") {
      sendEnvelope(res, runEngine("subscription.status", {}));
      return true;
    }
    if (path === "/api/subscription/login_begin") {
      // redirect_port=桥自身端口：引擎钉 redirect_uri=http://127.0.0.1:<桥端口>/auth/callback，
      // 回调落回本桥 /auth/callback（UI 零端口推断，不重复暴露第二监听）。
      sendEnvelope(res, runEngine("subscription.login_begin", { redirect_port: port }));
      return true;
    }
    if (path === "/api/subscription/logout") {
      const body = await readJsonBody(req);
      if (!body || typeof body !== "object") {
        send(res, 200, { status: "NOT_CONNECTED", code: "subscription_body_not_json" });
        return true;
      }
      sendEnvelope(res, runEngine("subscription.logout", { sub: body.sub }));
      return true;
    }
    if (path === "/api/subscription/models") {
      const refresh = url.searchParams.get("refresh") === "1";
      sendEnvelope(res, runEngine("subscription.models", refresh ? { refresh: true } : {}));
      return true;
    }
    if (path === "/api/subscription/chat") {
      const body = await readJsonBody(req);
      if (!body || typeof body !== "object") {
        send(res, 200, { status: "NOT_CONNECTED", code: "subscription_body_not_json" });
        return true;
      }
      const args = { input: body.input };
      if (typeof body.model === "string" && body.model) args.model = body.model;
      if (typeof body.reasoning === "string" && body.reasoning) args.reasoning = body.reasoning;
      if (body.fallback && typeof body.fallback === "object") args.fallback = body.fallback;
      sendEnvelope(res, runEngine("subscription.chat", args));
      return true;
    }
    send(res, 404, { status: "NOT_CONNECTED", code: "subscription_endpoint_unknown" });
    return true;
  }

  function sendHtml(res, html) {
    if (res.headersSent) { res.end(); return; }
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    res.end(html);
  }

  return { httpHandler };
}
