#!/usr/bin/env node
// S15：模型目录暴露 juscite_statute_check，权威核验面是 /api/verify/*。两面同时在。
// permission 落 ask 且没有交互审批面时，运行时权限门按拒（fail-closed）。
// 本探针只记录共存，不裁定 smart/yolo 下模型触发核验是否产品允许。
import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import http from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { decideToolCall } from "../../tools/bridge/tool_policy.mjs";
import { createCitationVerifyService } from "../../tools/bridge/citation_verify_service.mjs";
import { createOpenCodeRuntime } from "../../packages/juscite-runtime-adapters/opencode/src/opencodeAdapter.mjs";

const repo = fileURLToPath(new URL("../..", import.meta.url));
const hostSrc = readFileSync(join(repo, "tools/bridge/bridge_host.mjs"), "utf8");
const connectorPath = fileURLToPath(new URL("../../tools/bridge/g6_connector_mcp.mjs", import.meta.url));

let failed = 0;
function check(name, cond, detail = "") {
  if (cond) console.log(`[S15] OK ${name}`);
  else {
    failed += 1;
    console.error(`[S15] FAIL ${name}${detail ? " — " + detail : ""}`);
  }
}

function sliceBetween(source, startMark, endMark) {
  const start = source.indexOf(startMark);
  const end = source.indexOf(endMark, start + startMark.length);
  if (start < 0 || end < 0) return "";
  return source.slice(start, end);
}

// 与 bridge_host setPermissionGate 同形：去 juscite_g6_ 前缀，空会话（无交互审批缓存），只放行 allow。
function gateAllows(request, permissionMode) {
  const tool = String(request?.tool ?? "");
  const domainTool = tool.startsWith("juscite_g6_") ? tool.slice("juscite_g6_".length) : tool;
  const decision = decideToolCall({ toolName: domainTool, args: {}, permissionMode, shellEnabled: false });
  const conversationId = "";
  if (decision.effect === "ask" && conversationId) {
    throw new Error("空会话不得进入交互审批缓存");
  }
  return decision.effect === "allow";
}

const catalogBlock = sliceBetween(hostSrc, "const G6_CONNECTOR_SPECS = [", "function g6ConnectorEnv");
const gateBlock = sliceBetween(hostSrc, "runtime.setPermissionGate((request) => {", "async function registerG6Connector");
const registerBlock = sliceBetween(hostSrc, "async function registerG6Connector()", "function convStateOf");
check("model catalog lists juscite_statute_check", /name:\s*"juscite_statute_check"/.test(catalogBlock), catalogBlock.slice(0, 180));
check(
  "runtime gate refuses unless effect is allow",
  /decideAndAuditToolCall\(\s*""/.test(gateBlock) && /return outcome\.effect === "allow"/.test(gateBlock),
  gateBlock.replace(/\s+/g, " ").slice(0, 240),
);
check("register preblock strips deny only", /decision\.effect === "deny"/.test(registerBlock), registerBlock.slice(0, 180));

const askDecision = decideToolCall({
  toolName: "juscite_statute_check",
  args: { query: "《合成测试法》第一条" },
  permissionMode: "always_ask",
  shellEnabled: false,
});
check("always_ask stays ask (catalog is not preblocked)", askDecision.effect === "ask" && askDecision.code === "read_only", JSON.stringify(askDecision));
const smartDecision = decideToolCall({
  toolName: "juscite_statute_check",
  args: {},
  permissionMode: "smart",
  shellEnabled: false,
});
console.log(`[S15] observed smart effect=${smartDecision.effect} code=${smartDecision.code}（观察值，不裁定产品政策）`);
check(
  "ask without interactive surface is not allow",
  gateAllows({ tool: "juscite_g6_juscite_statute_check" }, "always_ask") === false,
);

const manifest = JSON.stringify([{
  name: "juscite_statute_check",
  description: "法条有效性核验（合成目录探针）",
  parameters: { type: "object", properties: { query: { type: "string" } }, required: ["query"] },
}]);
const mcp = spawn(process.execPath, [connectorPath], {
  env: { ...process.env, JUSCITE_G6_TOOL_MANIFEST: manifest },
  stdio: ["pipe", "pipe", "pipe"],
});
let mcpOut = "";
let mcpErr = "";
mcp.stdout.on("data", (chunk) => { mcpOut += chunk; });
mcp.stderr.on("data", (chunk) => { mcpErr += chunk; });
const mcpLine = await new Promise((resolve) => {
  const timer = setTimeout(() => resolve(""), 4000);
  const take = () => {
    const idx = mcpOut.indexOf("\n");
    if (idx < 0) return;
    clearTimeout(timer);
    resolve(mcpOut.slice(0, idx));
  };
  mcp.stdout.on("data", take);
  mcp.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }) + "\n");
  take();
});
mcp.kill();
await new Promise((resolve) => mcp.on("exit", resolve));
let listed = [];
try {
  listed = JSON.parse(mcpLine)?.result?.tools?.map((tool) => tool.name) ?? [];
} catch { listed = []; }
console.log(`[S15] tools/list ${listed.join(",") || "(empty)"}`);
check("tools/list exposes juscite_statute_check", listed.includes("juscite_statute_check"), mcpLine || mcpErr.slice(0, 240));
check("tools/list did not execute the tool", !mcpErr.includes("tools/call"), mcpErr.slice(0, 240));

const dir = mkdtempSync(join(tmpdir(), "s15-verify-"));
process.env.BRIDGE_CITATION_PACK_DIR = join(dir, "missing-pack");
const citation = createCitationVerifyService({
  store: {
    cvAppendCheck() { throw new Error("s15 不应落账"); },
    cvListChecks() { return []; },
  },
});

const replies = [];
let nextEvent = null;
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", "http://127.0.0.1");
  if (url.pathname.startsWith("/api/verify/")) {
    const handled = await citation.httpHandler(req, res, url);
    if (handled) return;
  }
  if (url.pathname === "/api/event") {
    res.writeHead(200, {
      "content-type": "text/event-stream",
      "cache-control": "no-cache",
      connection: "keep-alive",
    });
    if (nextEvent) res.write(`data: ${JSON.stringify(nextEvent)}\n\n`);
    return;
  }
  if (req.method === "POST" && /\/permission\/[^/]+\/reply$/.test(url.pathname)) {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const raw = Buffer.concat(chunks).toString("utf8");
    replies.push({ path: url.pathname, body: raw ? JSON.parse(raw) : {} });
    res.writeHead(200, { "content-type": "application/json" });
    res.end("{}");
    return;
  }
  res.writeHead(404);
  res.end();
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const { port } = server.address();
process.env.BRIDGE_OC28_URL = `http://127.0.0.1:${port}`;
process.env.BRIDGE_OC28_PASSWORD = "synthetic-not-a-secret";

function askedEvent(id) {
  return {
    id,
    type: "permission.asked",
    created: 1,
    data: {
      id,
      sessionID: "sess-synth",
      source: { type: "tool", id: "juscite_g6_juscite_statute_check" },
      action: "juscite_g6_juscite_statute_check",
      resources: ["*"],
    },
  };
}

function waitReply(after, ms = 4000) {
  const start = Date.now();
  return new Promise((resolve) => {
    const timer = setInterval(() => {
      if (replies.length > after || Date.now() - start > ms) {
        clearInterval(timer);
        resolve(replies[after] ?? null);
      }
    }, 20);
  });
}

let runtime = null;
try {
  const configRes = await fetch(`http://127.0.0.1:${port}/api/verify/citation/config`);
  const config = await configRes.json();
  const historyRes = await fetch(`http://127.0.0.1:${port}/api/verify/citation/history?limit=20`);
  const history = await historyRes.json();
  console.log(`[S15] GET /api/verify/citation/config ${configRes.status} ${JSON.stringify(config)}`);
  console.log(`[S15] GET /api/verify/citation/history ${historyRes.status} ${JSON.stringify(history)}`);
  check(
    "authority surface /api/verify/citation/config",
    configRes.status === 200 && typeof config.available === "boolean" && typeof config.engine === "boolean" && "packDir" in config && !config.materials && !config.citations,
    JSON.stringify(config),
  );
  check(
    "authority ledger envelope",
    historyRes.status === 200 && history.status === "OWNER_RESPONSE" && Array.isArray(history.result?.items),
    JSON.stringify(history),
  );
  check(
    "catalog and verify surface coexist",
    listed.includes("juscite_statute_check") && configRes.status === 200,
  );

  runtime = createOpenCodeRuntime();
  nextEvent = askedEvent("req-ask");
  runtime.setPermissionGate((request) => gateAllows(request, "always_ask"));
  const askReply = await waitReply(0);
  console.log(`[S15] ask reply ${JSON.stringify(askReply)}`);
  check(
    "ask with no interactive surface replies reject",
    askReply?.body?.decision === "reject" && askReply.path.includes("/permission/req-ask/reply"),
    JSON.stringify(askReply),
  );

  runtime.setPermissionGate(null);
  nextEvent = askedEvent("req-throw");
  runtime.setPermissionGate(() => { throw new Error("无交互审批面"); });
  const throwReply = await waitReply(1);
  console.log(`[S15] thrown gate reply ${JSON.stringify(throwReply)}`);
  check(
    "thrown gate fail-closed reject",
    throwReply?.body?.decision === "reject" && throwReply.path.includes("/permission/req-throw/reply"),
    JSON.stringify(throwReply),
  );
} finally {
  try { runtime?.setPermissionGate(null); } catch { /* 闸已关 */ }
  await new Promise((resolve) => server.close(resolve));
  rmSync(dir, { recursive: true, force: true });
}

if (failed) {
  console.log("RESULT fail");
  process.exit(1);
}
console.log("[S15] 两面共存：juscite_statute_check 在模型目录，/api/verify/* 是权威面；ask 且无交互审批面按拒。不裁定模型触发核验的产品政策");
console.log("RESULT pass");
