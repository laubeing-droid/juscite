// L1b opencode adapter（r12 波2.5：tools/bridge/oc28client.mjs 重构入）。
// 职责：把 opencode(oc28) serve HTTP API 的 wire 形状映射为 runtime-port（@juscite/runtime-port）
// 的域模型——oc28 的端点/part 形状/事件名等 wire 知识只住在本文件，桥产品层只见 port 域词
// （设计 §一 L1a/L1b、§八原则1：协议类型消费树内真源，wire 形状不外溢产品层）。
// 端点契约 = implementation/python/opencode_http.py + tools/s0_smoke.py（战役一 S0 已验链路）。
// 凭据从服务注册文件读取，不落盘不打印。
// 探测/诊断工具（conversation.probe / re30_synthetic）仍可 import 本文件导出的 wire 级
// 工具（loadCredentials/makeClient/waitForAssistant）；产品层（bridge_host.mjs）只用
// createOpenCodeRuntime() 返回的 port 面。
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { RuntimeAdapterBase } from "../../../juscite-runtime-port/src/index.ts";

export function loadCredentials() {
  // 环境变量优先（固定凭据直连 serve）；缺省回落注册文件（桌面 host 拉起时的实例化凭据）
  const envUrl = process.env.BRIDGE_OC28_URL;
  const envPassword = process.env.BRIDGE_OC28_PASSWORD;
  if (envUrl && envPassword) {
    const auth = "Basic " + Buffer.from(`opencode:${envPassword}`).toString("base64");
    return { baseUrl: envUrl, headers: { Authorization: auth, "Content-Type": "application/json" }, pid: 0 };
  }
  const reg = JSON.parse(
    readFileSync(join(homedir(), "AppData", "Roaming", "Juscite", "state", "opencode", "service-local.json"), "utf-8"),
  );
  const auth = "Basic " + Buffer.from(`opencode:${reg.password}`).toString("base64");
  return { baseUrl: reg.url, headers: { Authorization: auth, "Content-Type": "application/json" }, pid: reg.pid };
}

async function req(_cred, method, path, body) {
  // 每次请求重读注册文件：oc28 serve 重启会换 password（2026-10-24 真机实测 401 因桥缓存旧凭据）
  const cred = loadCredentials();
  const res = await fetch(cred.baseUrl + path, {
    method,
    headers: cred.headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}: ${text.slice(0, 200)}`);
  return text ? JSON.parse(text) : null;
}

export function makeClient(cred) {
  return {
    info: () => req(cred, "GET", "/api/info"),
    // 模型必须在 create 时绑定（prompt body 的 model 不生效——2026-10-24 实测：不带则回落
    // 会话默认 opencode 免费档 403 FreeTierError，即 S0 时代同一坑）。
    // directory 形状随 oc28 版本分叉：dev-21296（2026-10-27 常驻实例）吃扁平 directory；
    // 旧钉定版 2.0.28 要 location:{directory}（2026-10-24 实测）。扁平优先，4xx/5xx 回落旧形状。
    createSession: async (id, directory, model, title) => {
      const flat = { id, title: title ?? "Juscite（合成）", directory, model };
      try {
        return await req(cred, "POST", "/api/session", flat);
      } catch (e) {
        if (!/-> [45]\d\d:/.test(String(e))) throw e;
        return await req(cred, "POST", "/api/session",
          { id, title: flat.title, location: { directory }, model });
      }
    },
    prompt: (sid, body) => {
      if (typeof body.text !== "string" || !body.id) throw new Error("prompt_requires_text_and_caller_persisted_message_id");
      return req(cred, "POST", `/api/session/${encodeURIComponent(sid)}/prompt`, body);
    },
    listMessages: (sid) => req(cred, "GET", `/api/session/${encodeURIComponent(sid)}/message`),
    inbox: (sid) => req(cred, "GET", `/api/session/${encodeURIComponent(sid)}/inbox`),
    // ── 能力⑤工具注册面（2026-10-31 开放）：oc28 的运行时工具挂载=MCP 运行时覆盖
    //    （PUT experimental/mcp，不落配置文件不跨重启；协议形状 {config:LocalConfig}
    //    ——wire 知识只住本 adapter）。──
    mcpAdd: (server, config) => req(cred, "PUT", `/api/experimental/mcp/${encodeURIComponent(server)}`, { config }),
    mcpRemove: (server) => req(cred, "DELETE", `/api/experimental/mcp/${encodeURIComponent(server)}`),
    mcpConnect: (server) => req(cred, "POST", `/api/experimental/mcp/${encodeURIComponent(server)}/connect`),
    mcpList: () => req(cred, "GET", "/api/mcp"),
    // ── 能力⑥权限门面：pending 请求应答（decision once|always|reject）。──
    permissionReply: (sid, requestId, decision) =>
      req(cred, "POST", `/api/session/${encodeURIComponent(sid)}/permission/${encodeURIComponent(requestId)}/reply`, { decision }),
  };
}

// ── wire→域模型归一（oc28 part 形状族知识只住本 adapter；产品层拿到的已是域形状）──

function joinTextParts(message) {
  const parts = message?.content ?? message?.parts ?? [];
  return parts.filter((p) => p.type === "text").map((p) => p.text).join("\n");
}

// 推理面 part 族（reasoning/thinking/reasoning_content；2026-10-25 实测口径）→ 域 reasoning 串。
function joinReasoningParts(message) {
  const parts = message?.content ?? [];
  const joined = parts
    .filter((p) => p.type === "reasoning" || p.type === "thinking" || p.type === "reasoning_content" || typeof p.reasoning_content === "string")
    .map((p) => (typeof p.reasoning_content === "string" ? p.reasoning_content : p.text ?? ""))
    .join("\n");
  return joined || undefined;
}

// 工具步 part 形状族到达即点亮（与产品 researchModel.extractToolCalls 同一形状族、同一域形状；
// 本份住在 adapter=wire 归一层，产品层消费 entry.toolCalls 即可）。
function extractWireToolCalls(message) {
  const out = [];
  for (const p of message?.content ?? []) {
    const isCall = p && (p.type === "tool-call" || p.type === "tool_use" || typeof p.toolName === "string");
    if (!isCall) continue;
    const name = String(p.name ?? p.toolName ?? "").trim();
    if (!name) continue;
    const rawInput = p.input ?? p.arguments;
    const input = typeof rawInput === "string" ? rawInput : rawInput ? JSON.stringify(rawInput) : "";
    const rawOut = p.output;
    const output = typeof rawOut === "string" ? rawOut : rawOut ? JSON.stringify(rawOut) : "";
    out.push({ name, input, output, error: typeof p.error === "string" ? p.error : undefined });
  }
  return out;
}

// oc28 消息 wire 形状 → RuntimeTranscriptEntry；非 user/assistant 的 wire 类型不在域模型内
// （桥面今日也不消费），跳过。序保持 runtime 返回原序（新到旧），排序是对账方产品逻辑。
function toTranscriptEntry(m) {
  const role = m?.type === "assistant" ? "assistant" : m?.type === "user" ? "user" : null;
  if (!role) return null;
  const toolCalls = extractWireToolCalls(m);
  return {
    messageId: m.id,
    role,
    text: joinTextParts(m),
    reasoning: joinReasoningParts(m),
    ...(toolCalls.length ? { toolCalls } : {}),
    createdAt: m.time.created,
    ...(m.time?.completed ? { completedAt: m.time.completed } : {}),
    ...(m.error ? { error: String(m.error?.message ?? "unknown") } : {}),
  };
}

// oc28 事件 wire 名 → port 域事件词表（@juscite/runtime-port RuntimeEventKind）。
// server.connected 不在此表：连接起落由 openEventStream 的 onUp/onDown 统一映射 stream.up/down。
const OC28_EVENT_KIND_MAP = {
  "session.text.started": "turn.text.started",
  "session.text.delta": "turn.text.delta",
  "session.text.ended": "turn.text.ended",
  "session.step.ended": "turn.step.ended",
  "session.execution.succeeded": "turn.succeeded",
  "session.execution.failed": "turn.failed",
};

// 任务二：oc28 /api/event SSE 长连接（RE-B2 §2 实测契约）。
// 线格式：data: {id,type,created,data,...} 行，帧间 \n\n；": heartbeat" 注释帧保活。
// Last-Event-ID 重连不重放（实测带 id 重连只回 server.connected）→ 断线窗增量由调用方
// 经 pullTranscript 对账补齐，本函数只负责"连着+事件即达+断线自动重连"。
// 生命周期经 onUp/onDown 映射为 port 的 stream.up/down 域事件；close() 永久关闭；
// drop() 只断当前连接（自动重连，供 e2e 注入断线）。
export function openEventStream({ onEvent, onDown, onUp, log } = {}) {
  let closed = false;
  let delay = 500;
  let abort = null;
  async function loop() {
    while (!closed) {
      try {
        const cred = loadCredentials();
        abort = new AbortController();
        const res = await fetch(cred.baseUrl + "/api/event", { headers: cred.headers, signal: abort.signal });
        if (!res.ok || !res.body) throw new Error(`SSE -> ${res.status}`);
        delay = 500;
        onUp?.();
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n\n")) >= 0) {
            const chunk = buf.slice(0, i);
            buf = buf.slice(i + 2);
            const line = chunk.split("\n").find((l) => l.startsWith("data: "));
            if (!line) continue; // 心跳等注释帧
            try { onEvent?.(JSON.parse(line.slice(6))); } catch { /* 单帧损坏只弃帧 */ }
          }
        }
      } catch (e) {
        if (closed) return;
        log?.(`SSE 断开（${e?.name ?? e?.message ?? "?"}），${delay}ms 后重连`);
      }
      if (closed) return;
      onDown?.();
      await new Promise((r) => setTimeout(r, delay));
      delay = Math.min(delay * 2, 5000);
    }
  }
  void loop();
  return {
    close: () => { closed = true; try { abort?.abort(); } catch { /* 已断 */ } },
    drop: () => { try { abort?.abort(); } catch { /* 已断 */ } },
  };
}

// 伪流式：轮询 message 列表，assistant 文本增量回调（探针专用；产品层走
// subscribeEvents+pullTranscript 域面）。
export async function waitForAssistant(client, sid, { timeoutMs = 120000, intervalMs = 600, onDelta } = {}) {
  const deadline = Date.now() + timeoutMs;
  let seen = "";
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const listing = await client.listMessages(sid).catch(() => null);
    const msgs = Array.isArray(listing) ? listing : listing?.data ?? [];
    const last = [...msgs].reverse().find((m) => m.type === "assistant");
    const text = extractText(last);
    if (text && text.length > seen.length) {
      onDelta?.(seen ? text.slice(seen.length) : text, text);
      seen = text;
    }
    if (text && isFinal(msgs)) return { text: seen, done: true };
  }
  return { text: seen, done: false };
}

function extractText(message) {
  if (!message) return "";
  const parts = message.content ?? message.parts ?? [];
  return parts.filter((p) => p.type === "text").map((p) => p.text).join("\n");
}

function isFinal(msgs) {
  // OpenCode 收尾标志：inbox 空或最后 assistant 消息带 finish 态——骨架版以"文本 2 轮无增长"近似。
  return false; // 由调用方用二次采样或 inbox 判定；探针阶段超时返回即可
}

// ── port 面（产品层唯一入口）──

class OpenCodeRuntime extends RuntimeAdapterBase {
  runtimeId = "opencode";
  #client = makeClient(loadCredentials());

  async health() {
    try {
      await this.#client.info();
      return { ok: true };
    } catch (e) {
      return { ok: false, detail: String(e?.message ?? e) };
    }
  }

  // spec.model 为 V4 ModelSelection{providerId,modelId}；wire 形状 {id,providerID} 只在此映射。
  async createSession(spec) {
    await this.#client.createSession(
      spec.sessionId,
      spec.workspacePath,
      { id: spec.model.modelId, providerID: spec.model.providerId },
      spec.title,
    );
    return { runtimeSessionId: spec.sessionId };
  }

  async send(runtimeSessionId, message) {
    await this.#client.prompt(runtimeSessionId, { id: message.clientMessageId, text: message.text });
  }

  subscribeEvents(listener, hooks = {}) {
    const handle = openEventStream({
      onEvent: (evt) => {
        const kind = OC28_EVENT_KIND_MAP[evt?.type ?? ""];
        if (!kind) return;
        listener({
          kind,
          runtimeSessionId: typeof evt?.data?.sessionID === "string" ? evt.data.sessionID : "",
          at: typeof evt?.created === "number" ? evt.created : 0,
        });
      },
      onUp: () => listener({ kind: "stream.up", runtimeSessionId: "", at: Date.now() }),
      onDown: () => listener({ kind: "stream.down", runtimeSessionId: "", at: Date.now() }),
      log: hooks.log,
    });
    return { close: () => handle.close(), drop: () => handle.drop() };
  }

  async pullTranscript(runtimeSessionId) {
    const listing = await this.#client.listMessages(runtimeSessionId);
    const msgs = Array.isArray(listing) ? listing : listing?.data ?? [];
    const out = [];
    for (const m of msgs) {
      const entry = toTranscriptEntry(m);
      if (entry) out.push(entry);
    }
    return out;
  }

  // ── 能力⑤工具注册（2026-10-31 开放）：RuntimeToolSpec[] → oc28 运行时 MCP 挂载。
  // 语义：注册=把工具目录挂进 runtime 的运行时 MCP 面（experimental.mcp.add，204 即挂载
  // 并立即连接；不落配置不跨重启）。执行体=桥侧 G6 连接器 stdio MCP 进程
  // （JUSCITE_G6_MCP_SCRIPT 指向 .mjs，由 oc28 作为 MCP client 拉起）；
  // 目录经 JUSCITE_G6_TOOL_MANIFEST 传给连接器（连接器只暴露 manifest∩已实现——注册面
  // 与执行面一致性由桥的预阻断+连接器诚实跳过双保）。oc28 侧 config policy
  // （experimental.policies integration.use mcp:* deny）可把服务器从运行时集合移除——
  // 那是产品既定外闸；本方法观测到「挂载后不在册」时抛具名错（不伪造成功）。
  async registerTools(tools) {
    const script = process.env.JUSCITE_G6_MCP_SCRIPT;
    if (!script) throw new Error("g6_mcp_script_not_configured（JUSCITE_G6_MCP_SCRIPT 未设，拒绝挂载）");
    const manifest = (tools ?? []).filter((t) => t && typeof t.name === "string");
    const environment = {
      JUSCITE_G6_TOOL_MANIFEST: JSON.stringify(manifest),
      ...(process.env.JUSCITE_G6_MCP_LOG ? { JUSCITE_G6_MCP_LOG: process.env.JUSCITE_G6_MCP_LOG } : {}),
      ...(process.env.JUSCITE_G6_LCR_HOME ? { JUSCITE_G6_LCR_HOME: process.env.JUSCITE_G6_LCR_HOME } : {}),
      ...(process.env.JUSCITE_G6_LCR_FIXTURES ? { JUSCITE_G6_LCR_FIXTURES: process.env.JUSCITE_G6_LCR_FIXTURES } : {}),
      ...(process.env.JUSCITE_G6_LCR_DB ? { JUSCITE_G6_LCR_DB: process.env.JUSCITE_G6_LCR_DB } : {}),
      ...(process.env.BRIDGE_CITATION_ENGINE ? { BRIDGE_CITATION_ENGINE: process.env.BRIDGE_CITATION_ENGINE } : {}),
      ...(process.env.BRIDGE_CITATION_PACK_DIR ? { BRIDGE_CITATION_PACK_DIR: process.env.BRIDGE_CITATION_PACK_DIR } : {}),
    };
    await this.#client.mcpAdd("juscite-g6", { type: "local", command: [process.execPath, script], environment });
    // 观测收口：挂载后轮询在册状态（connected/failed/不在册三态都如实抛给调用方）。
    const deadline = Date.now() + 15_000;
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000));
      const listing = await this.#client.mcpList();
      const row = (listing?.data ?? []).find((s) => s?.name === "juscite-g6");
      if (row?.status?.status === "connected") return;
      if (row?.status?.status === "failed") throw new Error(`g6_mcp_connect_failed（${row.status.error ?? "?"}）`);
      if (Date.now() > deadline) {
        if (!row) throw new Error("g6_mcp_not_listed_after_mount（挂载 204 后不在运行时集合——oc28 config policy integration.use mcp:* deny 外闸移除，须 oc28 配置面放行 juscite-g6 具名例外）");
        throw new Error(`g6_mcp_mount_timeout（status=${row.status?.status ?? "?"}）`);
      }
    }
  }

  // ── 能力⑥权限门（2026-10-31 开放）：桥安全层决策函数接进 runtime 的 pending 权限请求。
  // 机制：oc28 权限评估落在 ask（无规则命中/规则 ask）时发 permission.asked 事件并挂起
  // 等待 reply；本方法开一条专用事件流过滤该事件，逐条调 gate（域形状
  // {runtimeSessionId,tool,summary,respond}），布尔结果→POST reply（once|reject）。
  // gate 未设/null=关闸（不再动 pending 请求，oc28 侧策略自决）；fail-closed：gate 抛错
  // 按拒应答（不挂死一个没人答的请求）。close 幂等（重复 set 覆盖旧流）。
  #permissionWatch = null;
  setPermissionGate(gate) {
    if (this.#permissionWatch) { try { this.#permissionWatch.close(); } catch { /* 已断 */ } this.#permissionWatch = null; }
    if (!gate) return;
    const replied = new Set();
    this.#permissionWatch = openEventStream({
      onEvent: (evt) => {
        if (evt?.type !== "permission.asked") return;
        const d = evt.data ?? {};
        const requestId = String(d.id ?? "");
        const sid = String(d.sessionID ?? "");
        if (!requestId || replied.has(requestId)) return;
        replied.add(requestId);
        const tool = d.source?.type === "tool" ? String(d.source.id ?? "") : String(d.action ?? "");
        const summary = `${d.action ?? ""} ${Array.isArray(d.resources) ? d.resources.join(",") : ""}`.trim();
        const respond = (allow) => this.#client
          .permissionReply(sid, requestId, allow ? "once" : "reject")
          .catch((e) => process.stderr.write(`[opencodeAdapter] permissionReply 失败 request=${requestId}: ${e?.message ?? e}\n`));
        Promise.resolve()
          .then(() => gate({ runtimeSessionId: sid, tool, summary, respond }))
          .then((allow) => respond(allow === true))
          .catch(() => respond(false)); // gate 崩=按拒（fail-closed）
      },
      log: (line) => process.stderr.write(`[opencodeAdapter] ${line}\n`),
    });
  }

  // 取消：未开放（继承基类抛 UnsupportedCapabilityError；桥面以时限熔断收口）。
}

/** 组合根唯一入口：桥产品层经本工厂取得 port 面（换底座=换这一行）。 */
export function createOpenCodeRuntime() {
  return new OpenCodeRuntime();
}
