#!/usr/bin/env node
// 律引 Juscite 桥面本机分享站（功能#27 所内分享 · 步骤3 树内开闸 · 第 1 轮）。
// 上游 IConversationShareService 的云端分享站在本产品不可用（红线③材料不出域）；
// 本模块在桥的 HTTP 面上实现同一套 REST 契约的"所内"形态：
//   GET  /api/v1/shares/capabilities                 能力发现（仅 public_readonly、零工件）
//   POST /api/v1/shares/preparations                 发布制备
//   POST /api/v1/shares/preparations/:id/artifacts   工件上传（本站声明 0 容量，恒拒）
//   POST /api/v1/shares/preparations/:id/confirm     确认落库（canonical sha256 完整性校验，
//                                                    应答 data=分享记录，同 conversationShareConfirmDataSchema）
//   GET  /api/v1/shares/:code/preview                分享读取（公开；未知 404/3211，过期 410/3212，fail-closed）
//   POST /api/v1/shares/:code/continuation           导入（本站只读形态，恒拒 3214）
//   GET  /cn/share/:code · /share/:code              只读落地页（自写渲染，非上游 React 页）
// 持久化 = 每分享一个 JSON 文件（BRIDGE_SHARE_DIR 覆盖，缺省 %APPDATA%\Juscite\bridge\shares），
// 材料全程在本机/本域，不出站。全部断言面向上游 packages/shared/src/conversation-share.ts 契约。
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, readdirSync, unlinkSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { sha256ConversationShareJson } from "../../packages/services/src/conversation-share/conversationShareIntegrity.ts";
import { cspMeta, safeHtmlDocument } from "../../packages/juscite-vizb/src/shared/html.ts";

export const SHARE_TTL_MS = 7 * 24 * 3600_000; // 只读快照的有效期；过期预览 fail-closed

const SHARE_CODE_RE = /^[A-Za-z0-9_-]{8,64}$/u;
const SHA256_RE = /^[0-9a-f]{64}$/u;
// 能力发现（wire 形状 = conversationShareCapabilitiesWireSchema；allowed_artifacts 空表 =
// 诚实声明"桥面会话无工件通道"，客户端预检对任何工件都会给出显式阻断而不是上传失败）
const CAPABILITIES = {
  schema_version: 1,
  access_modes: ["public_readonly"],
  allowed_artifacts: [],
  ttl_ms: SHARE_TTL_MS,
  max_rows: 500,
  max_payload_bytes: 4_000_000,
  max_artifact_count: 0,
  max_artifact_bytes: 1,
  max_total_artifact_bytes: 1,
};

function shareDirOf() {
  return process.env.BRIDGE_SHARE_DIR || join(homedir(), "AppData", "Roaming", "Juscite", "bridge", "shares");
}
function sharePath(code) {
  return join(shareDirOf(), `${code}.json`);
}
function envelope(data) {
  return { code: 0, msg: "ok", data };
}
function errorEnvelope(res, status, code, msg) {
  res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  res.end(JSON.stringify({ code, msg }));
}

async function readBody(req, maxBytes) {
  const chunks = [];
  let total = 0;
  for await (const chunk of req) {
    total += chunk.length;
    if (total > maxBytes) throw new Error("payload too large");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf-8");
}

function loadShare(code) {
  if (!SHARE_CODE_RE.test(code)) return null;
  const p = sharePath(code);
  if (!existsSync(p)) return null;
  try {
    return JSON.parse(readFileSync(p, "utf-8"));
  } catch {
    return null;
  }
}

function sharePublicRecord(rec) {
  return {
    share_code: rec.share_code,
    share_url: rec.share_url,
    access_mode: rec.access_mode,
    expires_at: rec.expires_at,
  };
}

// ---------- 只读落地页（自写渲染；行 kinds 按 conversationRowSchema 认识的三类展开，其余计数提示） ----------
// 防注入（施工单-10 单元三）：骨架走 @juscite/vizb 安全基模板——CSP default-src 'none' 起步
// （script/style 只认一次性 nonce、connect-src 'self' 收取数接线），动态文本一律 escapeHtml 后进
// innerHTML（转义与 DOM 赋值二选一纪律的转义侧，页面内联脚本自带该函数）；code 在入口按
// SHARE_CODE_RE 闭集校验，防 JSON.stringify 串进 <script> 时被 </script> 截断。
// 监控接线（逆向吸收波二·条 2）：声明 coreActions=打开/渲染，页脚本经 jusciteMonitor 上报
// 三值结果；通道=本地（本站 /api/v1/monitoring/report 收件面 + 本地日志）。
function landingPage(code) {
  if (!SHARE_CODE_RE.test(code)) throw new Error(`分享码形状非法，拒绝出落地页：${code.slice(0, 16)}`);
  const nonce = randomBytes(16).toString("base64");
  return safeHtmlDocument({
    title: "所内分享 · 律引 Juscite",
    csp: cspMeta({ nonce, connectSelf: true }),
    monitoring: { key: "share-landing", coreActions: ["打开", "渲染"] },
    style: `
  :root { color-scheme: light dark; }
  body { margin: 0; font-family: system-ui, "Microsoft YaHei", sans-serif; background: #f6f7f9; color: #1c1e21; }
  main { max-width: 760px; margin: 0 auto; padding: 24px 16px 48px; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .meta { font-size: 12px; color: #6b7280; margin-bottom: 20px; }
  .turn { border-top: 1px dashed #d1d5db; margin: 20px 0 12px; padding-top: 10px; font-size: 12px; color: #9ca3af; }
  .bubble { border-radius: 10px; padding: 10px 14px; margin: 8px 0; font-size: 14px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
  .user { background: #e8f0fe; margin-left: 48px; }
  .assistant { background: #ffffff; border: 1px solid #e5e7eb; margin-right: 48px; }
  .assistant.failed { border-color: #fca5a5; background: #fef2f2; }
  .tag { display: inline-block; font-size: 11px; color: #6b7280; margin-bottom: 2px; }
  .note { font-size: 13px; color: #92400e; background: #fef3c7; border-radius: 8px; padding: 8px 12px; margin: 12px 0; }
  .status { text-align: center; color: #6b7280; padding: 48px 0; }
  footer { margin-top: 32px; font-size: 12px; color: #9ca3af; border-top: 1px solid #e5e7eb; padding-top: 12px; }
`,
    body: `<main>
<div id="app" class="status">正在读取分享内容……</div>
<footer>本页面由律引 Juscite 桥面本机分享站生成，仅作所内只读传阅；内容为发布时的会话快照，不含其后的对话，也不会随源会话更新。</footer>
</main>`,
    script: {
      nonce,
      js: `
(function () {
  var app = document.getElementById("app");
  var monitor = window.jusciteMonitor; // 声明式监控（条 2）：打开/渲染 三值上报，本地通道
  var code = ${JSON.stringify(code)};
  fetch("/api/v1/shares/" + encodeURIComponent(code) + "/preview").then(function (r) {
    return r.json().then(function (body) { return { ok: r.ok, body: body }; });
  }).then(function (res) {
    if (!res.ok || res.body.code !== 0) {
      var msg = res.body && res.body.code === 3212 ? "分享已过期（有效期 7 天）。"
        : res.body && res.body.code === 3211 ? "分享不存在或已被删除。"
        : "分享读取失败：" + ((res.body && res.body.msg) || "未知错误");
      app.textContent = msg;
      app.className = "status";
      if (monitor) monitor.report("打开", "失败");
      return;
    }
    if (monitor) monitor.report("打开", "成功");
    var d = res.body.data;
    var fmt = function (ms) { return new Date(ms).toLocaleString("zh-CN"); };
    var html = '<h1>' + escapeHtml(d.share.title) + '</h1>'
      + '<div class="meta">只读分享 · 发布于 ' + fmt(d.share.created_at) + ' · 有效期至 ' + fmt(d.share.expires_at) + '</div>';
    var round = 0, unsupported = 0;
    (d.rows || []).forEach(function (row) {
      if (row.kind === "turnHeader") {
        round += 1;
        html += '<div class="turn">第 ' + round + ' 轮</div>';
      } else if (row.kind === "userInput") {
        html += '<div class="tag">提问</div><div class="bubble user">' + escapeHtml(row.text || "") + '</div>';
      } else if (row.kind === "assistantText") {
        var failed = row.state === "failed";
        html += '<div class="tag">回答' + (failed ? "（该轮失败，仅保留错误说明）" : "") + '</div>'
        + '<div class="bubble assistant' + (failed ? ' failed' : '') + '">' + escapeHtml(row.text || "") + '</div>';
      } else {
        unsupported += 1;
      }
    });
    if (unsupported > 0) {
      html += '<div class="note">另有 ' + unsupported + ' 行内容（工具调用等）需在律引 Juscite 中查看，本页面未展示。</div>';
    }
    if ((d.rows || []).length === 0) {
      html += '<div class="status">这份分享没有可展示的内容。</div>';
    }
    app.className = "";
    app.innerHTML = html;
    if (monitor) monitor.report("渲染", "成功");
  }).catch(function () {
    app.textContent = "分享读取失败：无法连接分享站。";
    if (monitor) monitor.report("打开", "失败", "local_bridge_unavailable");
  });
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
})();
`,
    },
  });
}

// ---------- HTTP 分发（返回 true = 已应答） ----------
export function createShareStation({ port }) {
  mkdirSync(shareDirOf(), { recursive: true });
  const shareUrlBase = `http://127.0.0.1:${port}/cn/share`;
  // 制备登记：confirm 请求体不携带标题（上游契约如此），标题只能从制备阶段继承；
  // confirm 引用未知制备 = 契约外客户端，fail-closed 拒收。
  const preparations = new Map();

  async function handle(req, res, pathname) {
    // ── 本地监控收件面（逆向吸收波二·条 2）──
    // safeHtmlDocument 族交互页（分享落地页/订阅回调页）页内白名单执法后的同源上报终点。
    // 本面只做形状校验+本地日志；零外呼、无云告警通道（对照注记：上样本 alertChannel=Slack，
    // 我方零外呼红线不设此面）。挂在本站（桥 HTTP 面首个分发器）=全桥面交互页共用，不另立服务。
    if (req.method === "POST" && pathname === "/api/v1/monitoring/report") {
      let body;
      try {
        body = JSON.parse(await readBody(req, 64_000));
      } catch {
        errorEnvelope(res, 400, 3001, "监控上报不是合法 JSON");
        return true;
      }
      const events = body?.events;
      if (!Array.isArray(events) || events.length === 0 || events.length > 50
        || typeof body.source !== "string" || body.source.length > 64) {
        errorEnvelope(res, 400, 3001, "监控上报事件形状非法");
        return true;
      }
      for (const ev of events) {
        if (typeof ev?.action !== "string" || typeof ev?.outcome !== "string" || ev.action.length > 32 || ev.outcome.length > 8) {
          errorEnvelope(res, 400, 3001, "监控上报事件字段非法");
          return true;
        }
        console.log(`[monitoring] source=${body.source} action=${ev.action} outcome=${ev.outcome}`
          + (ev.errorType ? ` error=${ev.errorType}` : ""));
      }
      res.writeHead(204);
      res.end();
      return true;
    }
    // ── 能力发现 ──
    if (req.method === "GET" && pathname === "/api/v1/shares/capabilities") {
      res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
      res.end(JSON.stringify(envelope(CAPABILITIES)));
      return true;
    }
    // ── 发布制备 ──
    if (req.method === "POST" && pathname === "/api/v1/shares/preparations") {
      let body;
      try {
        body = JSON.parse(await readBody(req, 1_000_000));
      } catch {
        errorEnvelope(res, 400, 3001, "制备请求不是合法 JSON");
        return true;
      }
      if (!body || body.access_mode !== "public_readonly") {
        errorEnvelope(res, 400, 3200, "本分享站仅支持链接只读（public_readonly）形态");
        return true;
      }
      if (typeof body.title !== "string" || !body.title.trim() || !SHA256_RE.test(body.payload_sha256 ?? "")) {
        errorEnvelope(res, 400, 3001, "制备请求缺少合法的标题或载荷摘要");
        return true;
      }
      if ((body.artifact_count ?? 0) > CAPABILITIES.max_artifact_count) {
        errorEnvelope(res, 400, 3208, "本分享站不承载会话工件");
        return true;
      }
      console.log("[share-station] preparation:", body.client_request_id, "title=" + body.title.slice(0, 40));
      const preparationId = "prep_" + randomBytes(8).toString("hex");
      preparations.set(preparationId, { title: body.title.trim().slice(0, 200), access_mode: body.access_mode, created_at: Date.now() });
      res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
      res.end(JSON.stringify(envelope({
        preparation_id: preparationId,
        access_mode: body.access_mode,
        expires_at: Date.now() + SHARE_TTL_MS,
        status: "preparing",
      })));
      return true;
    }
    // ── 工件上传：声明 0 容量后客户端预检已阻断，此路只应被异常客户端打到 ──
    if (req.method === "POST" && /^\/api\/v1\/shares\/preparations\/[^/]+\/artifacts$/u.test(pathname)) {
      errorEnvelope(res, 400, 3208, "本分享站不承载会话工件");
      return true;
    }
    // ── 确认落库 ──
    let m = /^\/api\/v1\/shares\/preparations\/([^/]+)\/confirm$/u.exec(pathname);
    if (req.method === "POST" && m) {
      const preparationId = decodeURIComponent(m[1]);
      const preparation = preparations.get(preparationId);
      if (!preparation) {
        errorEnvelope(res, 404, 3211, "制备不存在或已失效");
        return true;
      }
      let body;
      try {
        body = JSON.parse(await readBody(req, CAPABILITIES.max_payload_bytes + 1_000_000));
      } catch {
        errorEnvelope(res, 400, 3001, "确认请求不是合法 JSON");
        return true;
      }
      const rows = body?.projection?.rows;
      const integrity = body?.integrity;
      const disclosure = body?.disclosure_confirmation;
      if (!Array.isArray(rows) || rows.length === 0) {
        errorEnvelope(res, 400, 3205, "分享投影没有任何内容");
        return true;
      }
      if (rows.length > CAPABILITIES.max_rows) {
        errorEnvelope(res, 400, 3209, `行数超出分享站上限 ${CAPABILITIES.max_rows}`);
        return true;
      }
      if (!disclosure || disclosure.version !== 1 || !disclosure.accepted_at || disclosure.acknowledged_no_secret_detection !== true) {
        errorEnvelope(res, 400, 3206, "缺少发布前敏感信息确认记录");
        return true;
      }
      if (!integrity || !SHA256_RE.test(integrity.projection_sha256 ?? "") || !SHA256_RE.test(integrity.artifact_set_sha256 ?? "")) {
        errorEnvelope(res, 400, 3001, "完整性摘要缺失或形状非法");
        return true;
      }
      // 完整性复核：canonical JSON sha256 必须与客户端对同一 rows 的计算一致；
      // artifact_set 固定为空集（"[]"）。不一致=传输损坏或客户端实现偏离，fail-closed 拒收。
      if (sha256ConversationShareJson(rows) !== integrity.projection_sha256) {
        errorEnvelope(res, 400, 3001, "分享投影完整性校验失败");
        return true;
      }
      if (sha256ConversationShareJson([]) !== integrity.artifact_set_sha256) {
        errorEnvelope(res, 400, 3001, "工件集完整性校验失败（本站不承载工件）");
        return true;
      }
      const now = Date.now();
      const share_code = randomBytes(9).toString("base64url");
      const rec = {
        share_code,
        share_url: `${shareUrlBase}/${share_code}`,
        title: preparation.title,
        access_mode: "public_readonly",
        created_at: now,
        expires_at: now + SHARE_TTL_MS,
        rows,
        integrity: {
          projection_sha256: integrity.projection_sha256,
          artifact_set_sha256: integrity.artifact_set_sha256,
        },
      };
      preparations.delete(preparationId);
      mkdirSync(shareDirOf(), { recursive: true });
      writeFileSync(sharePath(share_code), JSON.stringify(rec), "utf-8");
      console.log("[share-station] confirmed:", share_code, "rows=" + rows.length, "title=" + rec.title.slice(0, 40));
      // confirm 应答 data = 分享记录本身（conversationShareConfirmDataSchema），非制备联合形状
      res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
      res.end(JSON.stringify(envelope(sharePublicRecord(rec))));
      return true;
    }
    // ── 分享读取（公开；未知/过期 fail-closed） ──
    m = /^\/api\/v1\/shares\/([^/]+)\/preview$/u.exec(pathname);
    if (req.method === "GET" && m) {
      const rec = loadShare(decodeURIComponent(m[1]));
      if (!rec) {
        errorEnvelope(res, 404, 3211, "分享不存在");
        return true;
      }
      if (Date.now() >= rec.expires_at) {
        errorEnvelope(res, 410, 3212, "分享已过期");
        return true;
      }
      res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
      res.end(JSON.stringify(envelope({
        schema_version: 1,
        share: { title: rec.title, access_mode: rec.access_mode, created_at: rec.created_at, expires_at: rec.expires_at },
        rows: rec.rows,
        artifacts: [],
        integrity: rec.integrity,
      })));
      return true;
    }
    // ── 导入：只读形态明确不支持，不伪造可用 ──
    m = /^\/api\/v1\/shares\/([^/]+)\/continuation$/u.exec(pathname);
    if (req.method === "POST" && m) {
      errorEnvelope(res, 400, 3214, "本站分享为只读链接，暂不支持导入到工作区");
      return true;
    }
    // ── 落地页 ──
    m = /^\/(?:cn\/)?share\/([^/]+)\/?$/u.exec(pathname);
    if (req.method === "GET" && m) {
      const code = decodeURIComponent(m[1]);
      if (!SHARE_CODE_RE.test(code)) {
        res.writeHead(404, { "content-type": "text/html; charset=utf-8" });
        res.end(`<!doctype html><meta charset='utf-8'>${cspMeta()}<p>分享链接形状无效。</p>`);
        return true;
      }
      res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      res.end(landingPage(code));
      return true;
    }
    return false;
  }

  return { handle };
}

// 清理辅助（测试与运维用）：删除过期分享文件
export function pruneExpiredShares(now = Date.now()) {
  const dir = shareDirOf();
  if (!existsSync(dir)) return 0;
  let removed = 0;
  for (const f of readdirSync(dir)) {
    if (!f.endsWith(".json")) continue;
    try {
      const rec = JSON.parse(readFileSync(join(dir, f), "utf-8"));
      if (now >= rec.expires_at) {
        unlinkSync(join(dir, f));
        removed += 1;
      }
    } catch { /* 单文件损坏不阻塞清理 */ }
  }
  return removed;
}
