// Office 桥服务（方案 §三·S1）：工作台桌面进程内的本地回环服务。
//   ① HTTP 静态：伺服 taskpane 页（http://127.0.0.1:<动态端口>/taskpane/）
//   ② WebSocket：/ws 帧协议（pair→auth→request/subscribe/ping）
//   ③ 发现文件：<stateDir>/bridge.json（端口/bootstrapToken/公钥指纹）
//   ④ 仅绑 127.0.0.1，端口动态分配（0=系统分配）；单对端守卫（peerKey 唯一）
//   ⑤ bootstrapToken：TTL 过期报 bootstrap_token_invalid；配对成功即轮换（旧 token 立即作废）
// 明文 http/ws 是方案 §三 的零证书主案（元典 WPS 先例）；安全靠 token 绑定+指纹钉扎。
import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { extname, join, resolve, sep } from "node:path";
import { WebSocketServer } from "ws";
import { createBridgeIdentity } from "./identity.mjs";
import { createBootstrapToken, verifyBootstrapToken } from "./token.mjs";
import { discoveryPath, writeDiscovery, removeDiscovery } from "./discovery.mjs";
import { peerKeyOf } from "./pid-guard.mjs";
import { MAX_FRAME_BYTES, PROTOCOL_VERSION, SURFACES, ERROR_CODES, parseInbound, s2cFrame } from "./protocol.mjs";

const CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

export async function startOfficeBridge(options = {}) {
  const {
    host = "127.0.0.1",
    port = 0, // 动态端口：0 = 让系统分配（方案 §三·④）
    stateDir,
    taskpaneDir,
    tokenTtlMs = 15 * 60_000,
    log = () => {},
    onRequest, // (frame, ctx) => Promise<result>：request 帧的业务接线点（S5 接 agent 会话）
  } = options;
  if (!stateDir || !taskpaneDir) throw new Error("stateDir 与 taskpaneDir 必填");
  const taskpaneRoot = resolve(taskpaneDir);
  const serverInstanceId = randomUUID();
  const startedAt = new Date().toISOString();
  const identity = createBridgeIdentity();
  let bootstrapToken = createBootstrapToken(tokenTtlMs);

  // ── 单对端守卫状态 ──
  let pairedConn = null; // { ws, peerKey, surface, clientId }

  // ── request op 路由（逆向吸收波二·条 3：宿主桥 API 真身面）──
  // user.identity=桥自有事实（真通道真数据：实例身份+配对面+启动时刻）；
  // db.summary=工作台数据接线点——onRequest（工作台进程注入）给定时经其取真数据，
  // 未接线=显式 not_wired（fail-closed 不编造，绝不悄悄塞演示数据冒充真身）。
  const requestHandler = async (frame, ctx) => {
    if (frame.op === "user.identity") {
      return {
        source: "office-bridge",
        identity: { kind: "workbench-bridge", serverInstanceId, surface: ctx?.surface ?? null, peerKey: ctx?.peerKey ?? null, startedAt },
      };
    }
    if (frame.op === "db.summary") {
      if (typeof onRequest === "function") return onRequest(frame, ctx);
      return { op: "db.summary", ok: false, error: "db_not_wired", note: "案卷数据面由工作台进程经 onRequest 接线（S5）；当前桥实例未接数据源" };
    }
    if (typeof onRequest === "function") return onRequest(frame, ctx);
    return { echo: frame.kind, note: "S1 桩：agent 会话接线在 S5" };
  };

  const httpServer = createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "127.0.0.1"}`);
    try {
      if (req.method === "GET" && url.pathname === "/healthz") {
        sendJson(res, 200, { ok: true, protocolVersion: PROTOCOL_VERSION, serverInstanceId, startedAt });
        return;
      }
      // 页面同源取配对材料：回环限定，等价于读本机发现文件（方案 §三：明文不保密，安全靠钉扎）
      if (req.method === "GET" && url.pathname === "/pair-info") {
        sendJson(res, 200, {
          protocolVersion: PROTOCOL_VERSION,
          serverInstanceId,
          publicKeySha256: identity.fingerprint,
          bootstrapToken: bootstrapToken.value,
          expiresAt: bootstrapToken.expiresAt,
        });
        return;
      }
      if (req.method === "GET" && url.pathname.startsWith("/taskpane/")) {
        await serveStatic(res, taskpaneRoot, url.pathname.slice("/taskpane/".length));
        log(`[http] ${req.socket.remoteAddress} GET ${url.pathname} -> ${res.statusCode}`);
        return;
      }
      // 本地监控收件面（逆向吸收波二·条 2）：taskpane 页内白名单执法后的同源上报终点。
      // 只做形状校验+本地日志（log 回调），零外呼、无云告警通道（对照注记：无 alertChannel 面）。
      if (req.method === "POST" && url.pathname === "/api/v1/monitoring/report") {
        let body;
        try {
          body = JSON.parse(await readBody(req, 64_000));
        } catch {
          sendJson(res, 400, { ok: false, error: "monitoring_bad_payload" });
          return;
        }
        const events = body?.events;
        if (!Array.isArray(events) || events.length === 0 || events.length > 50
          || typeof body.source !== "string" || body.source.length > 64
          || events.some((ev) => typeof ev?.action !== "string" || typeof ev?.outcome !== "string" || ev.action.length > 32 || ev.outcome.length > 8)) {
          sendJson(res, 400, { ok: false, error: "monitoring_bad_payload" });
          return;
        }
        for (const ev of events) {
          log(`[monitoring] source=${body.source} action=${ev.action} outcome=${ev.outcome}${ev.errorType ? " error=" + ev.errorType : ""}`);
        }
        res.writeHead(204);
        res.end();
        return;
      }
      if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/taskpane")) {
        res.writeHead(302, { Location: "/taskpane/" });
        res.end();
        return;
      }
      sendJson(res, 404, { ok: false, error: "not_found" });
    } catch (err) {
      log(`[http] error ${url.pathname}: ${err.message}`);
      if (!res.headersSent) sendJson(res, 500, { ok: false, error: "internal" });
      else res.destroy();
    }
  });

  async function serveStatic(res, root, relPath) {
    const target = resolve(join(root, relPath || "index.html"));
    if (target !== root && !target.startsWith(root + sep)) {
      sendJson(res, 403, { ok: false, error: "forbidden" });
      return;
    }
    try {
      const body = await readFile(target);
      res.writeHead(200, { "Content-Type": CONTENT_TYPES[extname(target).toLowerCase()] ?? "application/octet-stream" });
      res.end(body);
    } catch {
      sendJson(res, 404, { ok: false, error: "not_found" });
    }
  }

  // 监控收件面用：限量读 JSON 体（超限/非 JSON 抛错由外层 500 兜住——收件面 best-effort）
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

  function sendJson(res, status, obj) {
    res.writeHead(status, { "Content-Type": CONTENT_TYPES[".json"] });
    res.end(JSON.stringify(obj));
  }

  // ── WebSocket /ws ──
  const wss = new WebSocketServer({ noServer: true, maxPayload: MAX_FRAME_BYTES });
  httpServer.on("upgrade", (req, socket, head) => {
    const { pathname } = new URL(req.url ?? "/", `http://${req.headers.host ?? "127.0.0.1"}`);
    if (pathname !== "/ws") {
      socket.destroy();
      return;
    }
    wss.handleUpgrade(req, socket, head, (ws) => handleConnection(ws));
  });

  function fatal(ws, code, message) {
    if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(s2cFrame("error", { code, message })));
    ws.close(1008, code);
  }

  function handleConnection(ws) {
    let phase = "new"; // new → paired
    let expectSequence = 1;

    ws.on("message", (data, isBinary) => {
      if (isBinary) return fatal(ws, ERROR_CODES.badFrame, "帧必须是 JSON 文本");
      if (data.length > MAX_FRAME_BYTES) return fatal(ws, ERROR_CODES.badFrame, "帧超限");
      const parsed = parseInbound(data.toString("utf-8"));
      if (!parsed.ok) return fatal(ws, parsed.err, "入站帧不合法");
      const frame = parsed.frame;

      if (frame.sequence !== expectSequence) {
        return fatal(ws, ERROR_CODES.badSequence, `sequence 应为 ${expectSequence}，收到 ${frame.sequence}`);
      }
      expectSequence += 1;

      if (phase === "new") {
        if (frame.kind !== "pair") return fatal(ws, ERROR_CODES.notPaired, "首帧必须是 pair");
        const paired = handlePair(ws, frame);
        if (paired) phase = "paired";
        return;
      }
      handlePairedFrame(ws, frame);
    });
    ws.on("close", () => {
      if (pairedConn && pairedConn.ws === ws) {
        log(`[ws] 对端断开 peerKey=${pairedConn.peerKey}`);
        pairedConn = null;
      }
    });
    ws.on("error", () => { /* close 钩子统一收尾 */ });
  }

  function handlePair(ws, frame) {
    const localPort = httpServer.address()?.port;
    const remoteAddress = ws._socket?.remoteAddress ?? "";
    const remotePort = ws._socket?.remotePort ?? 0;
    const myPeerKey = peerKeyOf(localPort, remoteAddress, remotePort);
    ws.juscitePeerKey = myPeerKey;

    // ① token：缺失/不匹配/过期 同码（不给探测口径）
    if (verifyBootstrapToken(bootstrapToken, frame.bootstrapToken) !== "ok") {
      log(`[ws] pair 拒绝（token 无效/过期）peerKey=${myPeerKey}`);
      return fatal(ws, ERROR_CODES.bootstrapTokenInvalid, "bootstrap token 无效或已过期");
    }
    // ② 公钥指纹钉扎
    if (frame.pinnedPublicKeySha256 !== identity.fingerprint) {
      log(`[ws] pair 拒绝（指纹不匹配）peerKey=${myPeerKey}`);
      return fatal(ws, ERROR_CODES.publicKeyMismatch, "公钥指纹不匹配");
    }
    // ③ 宿主面
    if (typeof frame.surface !== "string" || !SURFACES.has(frame.surface)) {
      return fatal(ws, ERROR_CODES.unsupportedSurface, "surface 不在支持面内");
    }
    // ④ 单对端守卫：旧对端仍活着且身份不同 → 拒新保旧
    if (pairedConn && pairedConn.ws.readyState === pairedConn.ws.OPEN && pairedConn.peerKey !== myPeerKey) {
      log(`[ws] pair 拒绝（单对端守卫）new=${myPeerKey} held=${pairedConn.peerKey}`);
      return fatal(ws, ERROR_CODES.peerAlreadyPaired, "已有配对对端占用");
    }
    if (pairedConn && pairedConn.ws !== ws) {
      pairedConn.ws.close(1000, "superseded"); // 同一 PID 重连：换新弃旧
    }

    pairedConn = { ws, peerKey: myPeerKey, surface: frame.surface, clientId: frame.clientId ?? "unknown" };
    // ⑤ token 轮换：配对成功即作废旧 token，发现文件同步重写
    bootstrapToken = createBootstrapToken(tokenTtlMs);
    persistDiscovery();

    log(`[ws] pair 成功 peerKey=${myPeerKey} surface=${frame.surface}`);
    ws.send(JSON.stringify(s2cFrame("ready", { serverInstanceId, protocolVersion: PROTOCOL_VERSION, peerKey: myPeerKey })));
    return true;
  }

  async function handlePairedFrame(ws, frame) {
    switch (frame.kind) {
      case "ping":
        ws.send(JSON.stringify(s2cFrame("pong", { seq: frame.sequence })));
        return;
      case "subscribe":
      case "unsubscribe": {
        const topics = Array.isArray(frame.topics) ? frame.topics.filter((t) => typeof t === "string") : [];
        ws.send(
          JSON.stringify(
            s2cFrame("response", { requestId: frame.requestId ?? null, ok: true, result: { op: frame.kind, topics } })
          )
        );
        return;
      }
      case "auth":
        // S1 阶段 auth 为轻校验占位：配对已携带身份声明；S5 接 agent 会话时扩展凭据面
        ws.send(JSON.stringify(s2cFrame("response", { requestId: frame.requestId ?? null, ok: true, result: { auth: "accepted" } })));
        return;
      case "request": {
        try {
          const result = await requestHandler(frame, { peerKey: ws.juscitePeerKey, surface: pairedConn?.surface });
          ws.send(JSON.stringify(s2cFrame("response", { requestId: frame.requestId ?? null, ok: true, result: result ?? null })));
        } catch (err) {
          ws.send(JSON.stringify(s2cFrame("response", { requestId: frame.requestId ?? null, ok: false, error: String(err?.message ?? err) })));
        }
        return;
      }
      default:
        fatal(ws, ERROR_CODES.badFrame, "配对后不接受该帧");
    }
  }

  function persistDiscovery() {
    const localPort = httpServer.address()?.port;
    return writeDiscovery(stateDir, {
      protocolVersion: PROTOCOL_VERSION,
      serverInstanceId,
      host,
      port: localPort,
      pageBaseUrl: `http://${host}:${localPort}/taskpane/`,
      publicKeySha256: identity.fingerprint,
      bootstrapToken: bootstrapToken.value,
      bootstrapTokenExpiresAt: bootstrapToken.expiresAt,
      startedAt,
    });
  }

  await new Promise((resolveListen, rejectListen) => {
    httpServer.once("error", rejectListen);
    httpServer.listen(port, host, () => {
      httpServer.removeListener("error", rejectListen);
      resolveListen();
    });
  });
  const boundPort = httpServer.address().port;
  const discoveryFile = persistDiscovery();
  log(`[office-bridge] listening http://${host}:${boundPort} discovery=${discoveryFile}`);

  async function stop() {
    if (pairedConn && pairedConn.ws.readyState === pairedConn.ws.OPEN) {
      pairedConn.ws.send(JSON.stringify(s2cFrame("goaway", { reason: ERROR_CODES.shutdown })));
    }
    await new Promise((r) => wss.close(() => r()));
    await new Promise((r) => httpServer.close(() => r()));
    removeDiscovery(stateDir);
    log("[office-bridge] stopped（发现文件已清）");
  }

  return {
    serverInstanceId,
    host,
    port: boundPort,
    discoveryFile: discoveryPath(stateDir),
    fingerprint: identity.fingerprint,
    // 测试/运维探针：只读当前 token（轮换后即新值）
    currentBootstrapToken: () => bootstrapToken.value,
    stop,
  };
}
