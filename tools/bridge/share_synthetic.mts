// 功能#27 所内分享 · 合成自测（步骤3 树内开闸）。
// 真桥隔离实例（:3056，BRIDGE_SHARE_DIR=临时目录）+ 上游真实分享服务栈（ConversationShareService
// + HttpClient + 本机 artifact source）+ 合成会话行（与桥面发射形状一致：turnHeader+userInput+assistantText
// 且带 productTurnId）。覆盖：能力发现/预检/发布回链/落地页/预览/完整性 fail-closed/越权模式拒绝/
// 导入明确不支持/凭证门禁/桥重启后分享仍在/过期 fail-closed。材料全部合成，不出域。
// 末行 SHARE_PASS（全部 OK）或 SHARE_FAIL（有 FAIL）exit 1/0 可判。
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { ConversationShareService } from "../../packages/services/src/conversation-share/conversationShareService.ts";
import { ConversationShareHttpClient } from "../../packages/services/src/conversation-share/conversationShareHttpClient.ts";
import { createLocalConversationShareArtifactSource } from "../../packages/services/src/conversation-share/conversationShareArtifactSource.ts";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const PORT = Number(process.env.SHARE_TEST_PORT ?? 3056);
const BASE = `http://127.0.0.1:${PORT}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const checks = {};
function ok(name, cond, detail = "") {
  checks[name] = Boolean(cond);
  console.log(`[share-syn] ${name}: ${cond ? "OK" : "FAIL"}${detail ? " — " + detail : ""}`);
}

// ── 合成会话（与 bridge_host sendText 发射形状一致；两轮六行） ──
const T0 = Date.now() - 60_000;
const PT1 = "pt_syn0001", PT2 = "pt_syn0002";
const ROWS = [
  { rowId: 1, turnId: "turn_syn01", productTurnId: PT1, kind: "turnHeader", origin: "userInput", executionKind: "agent", state: "completedSuccess", startedAt: T0, endedAt: T0 + 4000, createdAt: T0, createdAtSeq: 0, actions: {} },
  { rowId: 2, turnId: "turn_syn01", productTurnId: PT1, kind: "userInput", origin: "realUser", text: "合成提问：借款合同约定年利率 12% 是否受法律保护？", sourceCommandId: "cmd_syn01", createdAt: T0 + 100, createdAtSeq: 0, actions: {} },
  { rowId: 3, turnId: "turn_syn01", productTurnId: PT1, kind: "assistantText", text: "合成回答：依据民间借贷司法解释，年利率 12% 未超过一年期 LPR 四倍上限，应受保护。（合成材料，仅供测试）", state: "complete", model: "deepseek-chat", createdAt: T0 + 500, createdAtSeq: 0, actions: {} },
  { rowId: 4, turnId: "turn_syn02", productTurnId: PT2, kind: "turnHeader", origin: "userInput", executionKind: "agent", state: "completedSuccess", startedAt: T0 + 10_000, endedAt: T0 + 15_000, createdAt: T0 + 10_000, createdAtSeq: 0, actions: {} },
  { rowId: 5, turnId: "turn_syn02", productTurnId: PT2, kind: "userInput", origin: "realUser", text: "合成提问：那约定 36% 呢？", sourceCommandId: "cmd_syn02", createdAt: T0 + 10_100, createdAtSeq: 0, actions: {} },
  { rowId: 6, turnId: "turn_syn02", productTurnId: PT2, kind: "assistantText", text: "合成回答：超过司法保护上限的部分不受保护，已付部分可主张抵扣。（合成材料，仅供测试）", state: "complete", model: "deepseek-chat", createdAt: T0 + 11_000, createdAtSeq: 0, actions: {} },
];
// 与桥面同款行分页（尾部起、升序、atSeq/atRevision/atLogEpoch 水位）
const stubAgentService = {
  conversationRowsRangeV4: async (params) => {
    const limit = Math.max(1, Math.min(params?.limit ?? 200, 200));
    let startIdx;
    if (params?.beforeRowId !== undefined) {
      const cut = ROWS.findIndex((r) => r.rowId >= params.beforeRowId);
      const before = cut === -1 ? ROWS : ROWS.slice(0, cut);
      startIdx = Math.max(0, before.length - limit);
    } else {
      startIdx = Math.max(0, ROWS.length - limit);
    }
    const rows = ROWS.slice(startIdx);
    return { rows, hasMore: startIdx > 0, atSeq: 42, atRevision: 1, atLogEpoch: "syn-epoch-1" };
  },
  conversationFileChangesV4: async () => ({ changes: [] }),
  conversationAttachmentReadV4: async () => { throw new Error("synthetic: no attachment channel"); },
  conversationAttachmentStatV4: async () => { throw new Error("synthetic: no attachment channel"); },
  conversationWorkflowRunsV4: async () => ({ runs: [] }),
  conversationWorkflowRunEventsV4: async () => ({ events: [] }),
  conversationWorkflowRunArtifactsV4: async () => ({ artifacts: [] }),
  conversationWorkflowRunArtifactDataV4: async () => ({ items: [], hasMore: false }),
  conversationWorkflowRunArtifactReadV4: async () => { throw new Error("synthetic: no workflow artifact"); },
};

// ── 桥生命周期（自拉自收：本用例自己 spawn 的子进程） ──
const shareDir = mkdtempSync(join(tmpdir(), "juscite-share-syn-"));
let child = null;
function spawnBridge() {
  child = spawn(process.execPath, ["--import", "tsx", join("tools", "bridge", "bridge_host.mjs")], {
    cwd: REPO_ROOT,
    env: { ...process.env, BRIDGE_PORT: String(PORT), BRIDGE_SHARE_DIR: shareDir },
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", () => {});
  child.stderr.on("data", (d) => process.stderr.write("[bridge] " + d));
}
async function waitProbe(timeoutMs = 40_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`${BASE}/api/server-info`, { signal: AbortSignal.timeout(1500) });
      if (r.ok) return true;
    } catch { /* 未起 */ }
    await sleep(400);
  }
  return false;
}
function stopBridge() {
  if (child) { try { child.kill(); } catch { /* 已退 */ } child = null; }
}

// ── 被测服务栈（真实实现，client 指向真桥的分享站） ──
const httpClient = new ConversationShareHttpClient({
  apiClient: { request: (url, init = {}) => fetch(url, { ...init, signal: AbortSignal.timeout(init.timeoutMs ?? 15_000) }) },
  baseUrl: `${BASE}/api/v1`,
  tokenProvider: async () => "share-synthetic-local",
});
const service = new ConversationShareService({
  zcodeAgentService: stubAgentService,
  client: httpClient,
  artifactSource: createLocalConversationShareArtifactSource(),
  shareWebUrl: `${BASE}/cn/share`,
  conversationWorkspaceRoot: join(shareDir, "imports"),
});

const SESSION_INPUT = { workspacePath: "D:\\mock\\lvyin-demo", sessionId: "ses_syn0001" };

async function main() {
  spawnBridge();
  try {
    ok("bridgeUp", await waitProbe());

    // 1. 能力发现（raw + client 双口径）
    const rawCap = await (await fetch(`${BASE}/api/v1/shares/capabilities`)).json();
    ok("capabilitiesEnvelope", rawCap?.code === 0 && Array.isArray(rawCap?.data?.access_modes));
    const caps = await service.getCapabilities();
    ok("capabilitiesReadOnlyOnly", caps.access_modes.length === 1 && caps.access_modes[0] === "public_readonly",
      JSON.stringify(caps.access_modes));
    ok("capabilitiesNoArtifacts", caps.max_artifact_count === 0 && caps.allowed_artifacts.length === 0);

    // 2. 预检：两轮全过；不存在的轮次给出显式阻断
    const preflight = await service.preflight({ ...SESSION_INPUT, selection: { kind: "productTurns", productTurnIds: [PT1, PT2] } });
    ok("preflightClean", preflight.blockingIssues.length === 0 && preflight.turnResults.length === 2,
      JSON.stringify(preflight.blockingIssues));
    ok("preflightWatermark", typeof preflight.revision === "number" && preflight.logEpoch.length > 0);
    const preflightMiss = await service.preflight({ ...SESSION_INPUT, selection: { kind: "productTurns", productTurnIds: ["pt_absent"] } });
    ok("preflightUnknownTurnBlocked", preflightMiss.blockingIssues.some((i) => i.code === "invalid_selection" || i.code === "missing_product_turn"),
      JSON.stringify(preflightMiss.blockingIssues));

    // 3. 发布：回链指向本机分享站；进度事件到达 complete
    const phases = [];
    const opId = "op_syn_" + Date.now();
    service.onDynamicPublishProgress(opId)((p) => phases.push(p.phase));
    const record = await service.publish({
      ...SESSION_INPUT,
      title: "合成分享：借贷利率两问",
      accessMode: "public_readonly",
      selection: { kind: "productTurns", productTurnIds: [PT1, PT2] },
      clientRequestId: "req_syn_" + Date.now(),
      disclosureAcceptedAt: Date.now(),
      locale: "zh-CN",
    }, opId);
    const urlRe = new RegExp(`^${BASE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/cn/share/[A-Za-z0-9_-]{8,64}$`);
    ok("publishLocalShareUrl", urlRe.test(record.share_url), record.share_url);
    ok("publishAccessMode", record.access_mode === "public_readonly" && record.expires_at > Date.now());
    ok("publishProgressComplete", phases.includes("collecting") && phases.includes("complete"), phases.join(","));

    const code = decodeURIComponent(new URL(record.share_url).pathname.split("/").pop());

    // 4. 落地页：静态 HTML 只含加载态与取数接线（内容在浏览器运行时渲染，
    // 真渲染形态由 UI CDP 走查单独取证）；正文断言在下方预览检查覆盖。
    const page = await fetch(record.share_url);
    const pageText = await page.text();
    ok("landingHtml", page.ok && page.headers.get("content-type")?.includes("text/html") && pageText.includes(code));
    ok("landingWiring", pageText.includes("正在读取分享内容") && pageText.includes("/api/v1/shares/"));

    // 5. 预览：rows/integrity 全量回带
    const preview = await service.getPreview(code);
    ok("previewRows", preview.rows.length === 6 && preview.unsupportedRowCount === 0, `rows=${preview.rows.length}`);
    ok("previewIntegrity", /^[0-9a-f]{64}$/.test(preview.integrity.projection_sha256) && /^[0-9a-f]{64}$/.test(preview.integrity.artifact_set_sha256));
    ok("previewMeta", preview.share.title === "合成分享：借贷利率两问" && preview.share.access_mode === "public_readonly");

    // 6. 越界行为 fail-closed：未知 code/导入/篡改完整性/不支持模式/缺披露
    const missRes = await fetch(`${BASE}/api/v1/shares/zzzzzzzz/preview`);
    ok("previewUnknown404", missRes.status === 404 && (await missRes.json()).code === 3211);
    const contRes = await fetch(`${BASE}/api/v1/shares/${code}/continuation`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ schema_version: 1, client_request_id: "req_syn_c" }) });
    ok("continuationRejected", contRes.status === 400 && (await contRes.json()).code === 3214);
    const prep = await (await fetch(`${BASE}/api/v1/shares/preparations`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ client_request_id: "req_syn_t", title: "合成", schema_version: 1, access_mode: "public_readonly", payload_sha256: "0".repeat(64), artifact_count: 0 }) })).json();
    const tamper = await fetch(`${BASE}/api/v1/shares/preparations/${encodeURIComponent(prep.data.preparation_id)}/confirm`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ selected_product_turn_ids: ["share-product-turn-1"], projection: { rows: [{ rowId: 1, turnId: "share-turn-1", productTurnId: "share-product-turn-1", kind: "userInput", text: "被篡改的内容", createdAt: T0, createdAtSeq: 0 }] }, integrity: { projection_sha256: "0".repeat(64), artifact_set_sha256: "1".repeat(64) }, disclosure_confirmation: { version: 1, accepted_at: Date.now(), acknowledged_no_secret_detection: true } }) });
    ok("tamperRejected", tamper.status === 400 && (await tamper.json()).code === 3001);
    let featureErr = "";
    try {
      await service.publish({ ...SESSION_INPUT, title: "合成", accessMode: "private", selection: { kind: "productTurns", productTurnIds: [PT1] }, clientRequestId: "req_syn_p", disclosureAcceptedAt: Date.now() }, "op_syn_p");
    } catch (e) { featureErr = e?.kind ?? e?.message; }
    ok("privateModeRejected", featureErr === "feature_disabled", featureErr);
    let disclosureErr = "";
    try {
      await service.publish({ ...SESSION_INPUT, title: "合成", accessMode: "public_readonly", selection: { kind: "productTurns", productTurnIds: [PT1] }, clientRequestId: "req_syn_d", disclosureAcceptedAt: 0 }, "op_syn_d");
    } catch (e) { disclosureErr = e?.kind ?? e?.message; }
    ok("disclosureRequired", disclosureErr === "disclosure_required", disclosureErr);

    // 7. 桥重启后分享仍在（分享站文件持久化）
    const beforeRows = (await service.getPreview(code)).rows.length;
    stopBridge();
    await sleep(800);
    spawnBridge();
    ok("bridgeRestartUp", await waitProbe());
    const afterPreview = await service.getPreview(code);
    ok("shareSurvivesRestart", afterPreview.rows.length === beforeRows && afterPreview.rows.length === 6);

    // 8. 过期 fail-closed：直接放一份过期分享文件进分享站
    const expiredCode = "expired001";
    writeFileSync(join(shareDir, `${expiredCode}.json`), JSON.stringify({
      share_code: expiredCode, share_url: `${BASE}/cn/share/${expiredCode}`, title: "过期合成分享",
      access_mode: "public_readonly", created_at: Date.now() - 7200_000, expires_at: Date.now() - 3600_000,
      rows: ROWS, integrity: { projection_sha256: "0".repeat(64), artifact_set_sha256: "1".repeat(64) },
    }));
    const expRes = await fetch(`${BASE}/api/v1/shares/${expiredCode}/preview`);
    ok("expiredFailClosed", expRes.status === 410 && (await expRes.json()).code === 3212);

    // 9. 站点无出站：整轮交互只落在 127.0.0.1（结构上由 baseUrl/落地页同源保证；此处复核回链主机）
    ok("localhostOnly", new URL(record.share_url).hostname === "127.0.0.1");
  } finally {
    stopBridge();
    try { rmSync(shareDir, { recursive: true, force: true }); } catch { /* 临时目录残留无害 */ }
  }

  const failed = Object.entries(checks).filter(([, v]) => !v).map(([k]) => k);
  for (const [name, passed] of Object.entries(checks)) console.log(`[share-syn] ${name}: ${passed ? "OK" : "FAIL"}`);
  if (failed.length > 0) {
    console.log(`[share-syn] SHARE_FAIL failed=${failed.join(",")}`);
    process.exit(1);
  }
  console.log("[share-syn] SHARE_PASS");
}

main().catch((e) => {
  console.error("[share-syn] fatal:", e?.stack ?? e);
  console.log("[share-syn] SHARE_FAIL fatal");
  stopBridge();
  process.exit(1);
});
