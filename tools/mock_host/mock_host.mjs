#!/usr/bin/env node
// 律引 M1-B mock Host —— 合成数据，仅 dev 点亮用（WebSocket :3030 + /api/server-info）
// 协议与注册机制结论见同目录 NOTES.md；骨架照抄上游 server/src/http.ts 挂载模式。
import http from "node:http";
import { randomUUID } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { WebSocketServer } from "ws";
import { VSBuffer, SocketProtocol, ChannelServer, LoggingChannelServer, ProxyChannel, Event, Emitter } from "@zcode/rpc";
import {
  ServiceCollection,
  ISettingService,
  IZCodeAgentService,
  IZCodeSessionService,
  IZCodeTaskService,
  IOnboardingRecordService,
} from "@zcode/services";

const PORT = Number(process.env.MOCK_PORT ?? 3039); // 桥占 3030；mock 回归桩默认 3039
const MOCK_SETTING_PATH = join(homedir(), "AppData", "Roaming", "Juscite", "config", "mock", "setting.json");
// 本地演示 workspace：不带 workspaceIdentity——UI 的 isRemoteWorkspaceTarget 把带 identity
// 的 tab 判为远程断连占位（workspaceServiceResolver.ts:49），任务分片被整段排除，
// 侧栏任务列表/工作区准备全不启动（现象=“lvyin-demo 重新连接”+任务永远空）。
const WORKSPACE = { path: "D:\\mock\\lvyin-demo" };
const WORKSPACE_KEY = WORKSPACE.path; // workspaceKey 口径 = workspaceIdentity ?? workspacePath
// 对话工作区（“新建对话任务”目标）：真 mkdir 合成目录，目录本身就是合成数据
const CONVERSATION_DIR = "D:\\mock\\lvyin-conversations";

// ---------- 合成数据（全部合成，无真实材料） ----------
const NOW_MS = Date.now();
const HOUR = 3600_000;
const SYNTH_SESSIONS = [
  { id: "ses_mock_0001", title: "合成：借款合同审查（利率/期限/违约金）", phase: "completedSuccess", createdAt: NOW_MS - 72 * HOUR, lastActivityAt: NOW_MS - 5 * HOUR },
  { id: "ses_mock_0002", title: "合成：劳动仲裁时效试算", phase: "running", createdAt: NOW_MS - 26 * HOUR, lastActivityAt: NOW_MS - 20 * 60_000 },
  { id: "ses_mock_0003", title: "合成：商标近似检索核验", phase: "completedSuccess", createdAt: NOW_MS - 8 * HOUR, lastActivityAt: NOW_MS - 30 * 60_000 },
];
const DEFAULT_SETTING = {
  theme: "zai-dark", uiFontSize: 14, language: "zh-CN", dataBaseDir: undefined,
  appearance: { theme: "system" }, stealthMode: { enabled: false },
  providerFamilyDomain: "mock.local",
};

function loadSetting() {
  try { return JSON.parse(readFileSync(MOCK_SETTING_PATH, "utf-8")); } catch { return DEFAULT_SETTING; }
}
function saveSetting(s) {
  mkdirSync(join(MOCK_SETTING_PATH, ".."), { recursive: true });
  writeFileSync(MOCK_SETTING_PATH, JSON.stringify(s, null, 2), "utf-8");
}

// ---------- Event 工厂（帧推送面：先回静默 Event，迭代期按 UI 报错补真帧） ----------
const silentEvent = () => {
  const e = new Emitter();
  return e.event;
};
// agentService on* 帧通道表（订阅即静默；M1-D 迭代时逐个换成合成帧发射器）
// 注：onDynamic* 是"动态事件"——必须 (arg) => Event（ProxyChannel.isDynamicEvent 约定）
const AGENT_EVENTS = {
  onConversationDelta: silentEvent(), onConversationSnapshot: silentEvent(),
  onDynamicStorageStartupState: () => silentEvent(),
  onConversationTopicCandidates: silentEvent(), onConversationTelemetry: silentEvent(),
  // runtime 换代通知：Event 直值约定（(listener)=>IDisposable），静默即可
  onAgentRuntimeRestarted: () => ({ dispose() {} }),
};

// ---------- sessions-index 真帧发射器（侧栏任务列表实时数据源） ----------
// UI 链：useWorkspaceTaskLists → sessionsIndexRegistry.acquireSessionsIndex →
// agentSessionsIndexTransport（helloConversationV4 握手 → subscribeSessionsIndexV4 拿
// ACK{subscriptionId,mode,logEpoch} → onDynamicSessionsIndexFrame(workspace) 收
// TopicWireFrameCandidate 帧流）。帧形状按 shared/zcode-protocol-v4：
// transport.ts sessionsIndexTopicWireCandidateSchema + wire-assembler COMPLETE_WIRE_KEYS
// （complete 外壳恰好 8 键）、sessions-index.ts sessionsIndexSnapshotSchema、
// wire.ts V4_WIRE_PROTOCOL_VERSION=3。
const MOCK_LOG_EPOCH = "mock-log-epoch-1";
const sessionsIndexFrameEmitter = new Emitter();
// topic\0subscriptionId → 单调 ordinal（assembler 要求 logicalFrameOrdinal ≥1 且单调）
const sessionsIndexRouteOrdinals = new Map();

function sessionsIndexTopicOf(params) {
  const identity = typeof params?.workspaceIdentity === "string" ? params.workspaceIdentity.trim() : "";
  const workspaceId = identity || params?.workspacePath || WORKSPACE_KEY;
  return `sessions-index/${workspaceId}`;
}

function synthSessionSummariesFor(workspaceId) {
  if (workspaceId !== WORKSPACE_KEY) return [];
  return SYNTH_SESSIONS.map((s) => ({
    sessionId: s.id,
    workspaceId,
    title: s.title,
    titleSource: "generated",
    phase: s.phase,
    sessionEnded: s.phase !== "running",
    hasBackgroundWork: false,
    lastActivityAt: s.lastActivityAt,
    createdAt: s.createdAt,
  }));
}

function emitSessionsIndexSnapshotFrame(topic, subscriptionId) {
  const routeKey = `${topic}\0${subscriptionId}`;
  const ordinal = (sessionsIndexRouteOrdinals.get(routeKey) ?? 0) + 1;
  sessionsIndexRouteOrdinals.set(routeKey, ordinal);
  const workspaceId = topic.slice("sessions-index/".length);
  const frame = {
    topic,
    subscriptionId,
    // snapshot 帧区间记账：fromSeq 固定 0，toSeq = 单调水位（store 快照 apply 取 toSeq）
    fromSeq: 0,
    toSeq: ordinal,
    sentAt: Date.now(),
    payload: {
      kind: "snapshot",
      snapshot: {
        protocolVersion: 1,
        workspaceId,
        logEpoch: MOCK_LOG_EPOCH,
        sessions: synthSessionSummariesFor(workspaceId),
      },
    },
  };
  sessionsIndexFrameEmitter.fire({
    wireVersion: 3,
    kind: "complete",
    deliveryKind: "initial",
    logicalFrameId: "lframe_" + randomUUID().slice(0, 8),
    logicalFrameOrdinal: ordinal,
    topic,
    subscriptionId,
    frame,
  });
  console.log(`[mock-host] sessions-index snapshot fired: topic=${topic} sub=${subscriptionId} ordinal=${ordinal}`);
}

// ---------- 服务实例（合成数据，仅 dev 点亮用） ----------
const settingService = {
  get: async () => loadSetting(),
  update: async (patch) => { const s = { ...loadSetting(), ...patch }; saveSetting(s); return s; },
  updateDataBaseDir: async () => {},
};

// file 面精修：ensureConversationWorkspace 是“新建对话任务”链的第一跳
// （useConversationWorkspaceActions.handleCreateConversationTask → fileService.ensureConversationWorkspace，
// 失败/undefined 被 UI 空 catch 静默吞掉，表现为点击无反应）。此处按真实返回形状精实现，
// 其余 file 方法保持静默 stub 行为。
const fileService = new Proxy(
  {
    ensureConversationWorkspace: async () => {
      const created = mkdirSync(CONVERSATION_DIR, { recursive: true }) !== undefined;
      return { path: CONVERSATION_DIR, created, workspacePurpose: "conversation" };
    },
  },
  {
    get: (target, prop) => {
      if (prop in target) return target[prop];
      if (typeof prop === "string" && prop.startsWith("onDynamic")) return () => silentEvent();
      if (typeof prop === "string" && prop.startsWith("on")) return silentEvent();
      return async () => undefined;
    },
  },
);

const agentService = {
  ...AGENT_EVENTS,
  // sessions-index 帧面（动态事件约定：(arg) => Event）
  onDynamicSessionsIndexFrame: () => sessionsIndexFrameEmitter.event,
  prepareStorage: async () => {},
  getStorageStartupState: async () => null,
  initialize: async () => ({ ok: true, agentVersion: "mock" }),
  // v4 连接握手（agentSessionsIndexTransport.ensureAgentV4ConnectionHandshake；
  // hello 返回形状按 transport.ts helloMessageSchema .strict()）
  helloConversationV4: async () => ({
    kind: "hello",
    protocolVersion: 3,
    connectionId: "mock-conn-1",
    clientMode: "desktop-continuous",
    deliveryProfile: "continuous",
    serverTime: Date.now(),
    capabilities: { nativeDialogs: false, localTerminal: false, binaryFrames: true, compression: "none" },
    auth: {},
  }),
  initializeConversationV4: async () => {},
  // sessions-index 订阅面：ACK-only response + ACK 后推 initial snapshot 帧
  subscribeSessionsIndexV4: async (params) => {
    const subscriptionId = "sub_" + randomUUID().slice(0, 8);
    const topic = sessionsIndexTopicOf(params);
    setTimeout(() => emitSessionsIndexSnapshotFrame(topic, subscriptionId), 0);
    return { ack: { subscriptionId, mode: "snapshot", logEpoch: MOCK_LOG_EPOCH } };
  },
  resyncSessionsIndexV4: async (params) => {
    const topic = sessionsIndexTopicOf(params);
    if (params?.subscriptionId) {
      setTimeout(() => emitSessionsIndexSnapshotFrame(topic, params.subscriptionId), 0);
    }
    return { ack: { subscriptionId: params?.subscriptionId ?? "", mode: "snapshot", logEpoch: MOCK_LOG_EPOCH } };
  },
  unsubscribeSessionsIndexV4: async () => {},
  syncAppRuntimePreferences: async () => {},
  syncDynamicWorkflowUserMode: async () => {},
  // 本地 workspace：不回 identity（回 identity 会让 UI 把 tab 判成远程断连占位）
  getWorkspaceRuntimeIdentity: async (p) => {
    const path = typeof p?.workspacePath === "string" && p.workspacePath ? p.workspacePath : WORKSPACE.path;
    return { generation: 1, identity: path, workspaceKey: path };
  },
  readWorkspacePresentation: async (p) => {
    const path = typeof p?.workspacePath === "string" && p.workspacePath ? p.workspacePath : WORKSPACE.path;
    return { workspacePath: path, name: path === WORKSPACE.path ? "律引演示工作区（合成）" : "对话工作区（合成）" };
  },
  grantWorkspaceHookTrust: async () => ({ granted: true }),
  createSession: async () => ({ sessionId: "ses_mock_" + randomUUID().slice(0, 8), rows: [] }),
  resumeSession: async (p) => ({ sessionId: p?.sessionId ?? "ses_mock_0001", rows: [] }),
  listSessions: async () => SYNTH_SESSIONS.map((s) => ({
    id: s.id, title: s.title,
    updatedAt: new Date(s.lastActivityAt).toISOString(),
    workspacePath: WORKSPACE.path,
  })),
  listSessionSubagents: async () => ({ subagents: [] }),
  readSession: async (p) => ({ sessionId: p?.sessionId ?? "ses_mock_0001", rows: [] }),
  readSessionMessages: async () => [],
  readSessionEvents: async () => [],
  readSessionDebug: async () => ({ sessions: [] }),
  getAppUsageStats: async () => ({ tokens: 0, cost: 0 }),
  getTaskTokenUsage: async () => ({ usage: [] }),
  listMcpServerStatuses: async () => ({ servers: [] }),
  listPlugins: async () => ({ plugins: [] }),
  getPluginReferenceCatalog: async () => ({ refs: [] }),
  getSkillReferenceCatalog: async () => ({ refs: [] }),
  readMcpResource: async () => ({ contents: [] }),
};

const sessionService = {
  initializeWorkspace: async () => ({ ok: true }),
  getWorkspaceRuntimeIdentity: async (p) => {
    const path = typeof p?.workspacePath === "string" && p.workspacePath ? p.workspacePath : WORKSPACE.path;
    return { generation: 1, identity: path, workspaceKey: path };
  },
  readWorkspacePresentation: async (p) => {
    const path = typeof p?.workspacePath === "string" && p.workspacePath ? p.workspacePath : WORKSPACE.path;
    return { workspacePath: path, name: path === WORKSPACE.path ? "律引演示工作区（合成）" : "对话工作区（合成）" };
  },
  createSession: async () => ({ sessionId: "ses_mock_" + randomUUID().slice(0, 8), rows: [] }),
  resumeSession: async (p) => ({ sessionId: p?.sessionId ?? "ses_mock_0001", rows: [] }),
  listSessions: async () => SYNTH_SESSIONS.map((s) => ({
    id: s.id, title: s.title,
    updatedAt: new Date(s.lastActivityAt).toISOString(),
    workspacePath: WORKSPACE.path,
  })),
  readSession: async (p) => ({ sessionId: p?.sessionId ?? "ses_mock_0001", rows: [] }),
  readSessionMessages: async () => [],
  readSessionEvents: async () => [],
  promoteDeferredDraftSession: async () => {},
  closeSession: async () => {},
  closeDeferredDraftSession: async () => true,
  setModel: async (p) => ({ sessionId: p?.sessionId ?? "ses_mock_0001", rows: [] }),
  setThoughtLevel: async (p) => ({ sessionId: p?.sessionId ?? "ses_mock_0001", rows: [] }),
  setMode: async (p) => ({ sessionId: p?.sessionId ?? "ses_mock_0001", rows: [] }),
  respondProviderRuntimeHeaders: async () => {},
};

// zcode-task：侧栏持久行左表（UI fetchTaskListMembershipSets 用
// listTasks/listPinnedTasks/listArchivedTasks 三分区行集合，sessions-index 帧只补实时
// activity；三分区任一 RPC 失败 UI 会抛“tasks-index task 行读取不完整”，故此处必须真返回数组）
function synthTaskMetas(scope) {
  const pathOk = !scope?.workspacePath || scope.workspacePath === WORKSPACE.path;
  if (!pathOk) return [];
  return SYNTH_SESSIONS.map((s) => ({
    taskId: s.id,
    traceId: "trace_" + s.id,
    title: s.title,
    workspacePath: WORKSPACE.path,
    createdAt: s.createdAt,
    updatedAt: s.lastActivityAt,
    mode: "default",
    status: s.phase === "running" ? "running" : "completed",
  }));
}
const zcodeTaskService = new Proxy(
  {
    listTasks: async (p) => synthTaskMetas(p),
    listPinnedTaskIds: async () => [],
    listPinnedTasks: async () => [],
    listArchivedTasks: async () => [],
    listDeletedTaskIds: async () => [],
    listTaskList: async () => ({ items: synthTaskMetas({}), total: SYNTH_SESSIONS.length, hasMore: false }),
    listGroupedTaskViewStructure: async () => ({ groups: [], members: [], topLevelOrders: [] }),
    onDynamicWorkspaceEvent: () => silentEvent(),
    onError: silentEvent(),
  },
  {
    get: (target, prop) => {
      if (prop in target) return target[prop];
      if (typeof prop === "string" && prop.startsWith("onDynamic")) return () => silentEvent();
      if (typeof prop === "string" && prop.startsWith("on")) return silentEvent();
      return async () => undefined;
    },
  },
);

// onboarding：shouldOnboard=false 跳过首启向导（M1-D 验收主壳用；产品态向导照常走）
const onboardingService = {
  shouldOnboard: async () => false,
  getLatestEntry: async () => ({ occupation: "legal_admin_hr", completedAt: new Date().toISOString() }),
  appendRecord: async () => {}, dismissOnboarding: async () => {}, claimAnonymousRecord: async () => {},
  syncSettingsFromRecord: async () => null, updateRecordPreferences: async () => {},
  getRecords: async () => null, clearRecords: async () => {},
};

// terminal / git 空 stub（连接即静默，不实现任何功能）
const silentStub = new Proxy({}, {
  get: (_t, prop) => {
    if (typeof prop === "string" && prop.startsWith("onDynamic")) return () => silentEvent();
    if (typeof prop === "string" && prop.startsWith("on")) return silentEvent();
    return async () => undefined;
  },
});

// ---------- 装配与挂载 ----------
const services = new ServiceCollection();
services.register(ISettingService, settingService);
services.register(IZCodeAgentService, agentService);
services.register(IZCodeSessionService, sessionService);
services.register(IZCodeTaskService, zcodeTaskService);
services.register(IOnboardingRecordService, onboardingService);

// 兜底 stub 批量注册：方法静默返回 undefined、on* 返回静默 Event（迭代期按 Unknown channel 报错增补）
// 精修面（UI 读字段会崩的，返回最小合法形状）：
const VIEW = { revision: 1 };
// 模型 config 必须带 optionSpecs.reasoningLevel.values（SessionPane 经
// validateModelSelectionOptions 读 model.config.optionSpecs.reasoningLevel，缺省会崩主区）
const SYNTH_MODEL_CONFIG = {
  enabled: true,
  properties: {
    requiresMfjsToolSchema: true,
    contextWindow: 128000,
    inputFormat: { supportsText: true },
    outputFormat: { supportsText: true },
    supportsToolCall: true,
    supportsJsonSchemaOutput: true,
    supportsNativeWebSearch: false,
    supportsMidConversationSystem: true,
  },
  optionSpecs: {
    reasoningLevel: { values: ["off", "on"], map: "{}" },
    maxOutputTokens: { max: 8192, map: "{}" },
  },
};
const SYNTH_MODEL = { modelId: "deepseek-chat", config: SYNTH_MODEL_CONFIG };
const SYNTH_PROVIDER_CFG = { id: "deepseek", name: "DeepSeek（合成 BYOK）", models: [SYNTH_MODEL] };
const modelSelectionService = {
  onDidChange: silentEvent(),
  getView: async () => ({
    ...VIEW,
    providers: [{ providerId: "deepseek", providerName: "DeepSeek（合成）", config: SYNTH_PROVIDER_CFG, models: [SYNTH_MODEL] }],
    preferredSelection: { providerId: "deepseek", modelId: "deepseek-chat", options: { reasoningLevel: "on" } },
    // UI draftConfig.modelSelection 读 effectiveSelection（useDraftConfigControl:effectiveSelection ?? draft）；
    // 缺省=发送按钮 submissionReady=false 永久禁用（M4 前拔除的头号遗留）
    effectiveSelection: { providerId: "deepseek", modelId: "deepseek-chat", options: { reasoningLevel: "on" } },
  }),
  resolveModelConfig: async () => ({}),
};
const providerSettingsService = {
  onDidChange: silentEvent(),
  getView: async () => ({
    ...VIEW, providerTemplates: [], providerOrder: ["deepseek"],
    providers: [{
      providerId: "deepseek", providerName: "DeepSeek（合成）", enabled: true, executable: true,
      effectiveConfig: SYNTH_PROVIDER_CFG, issues: [],
      models: [{ ...SYNTH_MODEL, config: { ...SYNTH_MODEL_CONFIG, name: "deepseek-chat", label: "DeepSeek Chat（合成）" } }],
    }],
  }),
  refresh: async () => ({
    ...VIEW, providerTemplates: [], providerOrder: ["deepseek"],
    providers: [{
      providerId: "deepseek", providerName: "DeepSeek（合成）", enabled: true, executable: true,
      effectiveConfig: SYNTH_PROVIDER_CFG, issues: [],
      models: [{ ...SYNTH_MODEL, config: { ...SYNTH_MODEL_CONFIG, name: "deepseek-chat", label: "DeepSeek Chat（合成）" } }],
    }],
  }),
};
const oauthService = {
  onDidChange: silentEvent(),
  getProviders: async () => [],
  restoreCachedSessionState: async () => ({ status: "signed-out" }),
  getActiveProvider: async () => null,
  startLogin: () => {}, logout: async () => {},
  getZCodeJwtToken: () => null,
};
// settings-sync 精修：OnboardingDialog 挂 useSettingsSync（detect/getFirstRunPromptState/
// getClaudeAgentsFileMigrationStatus），批量静默 stub 返 undefined 曾让 OnboardingDialog
// 子树崩（TypeError reading 'length' → ScopedErrorBoundary:onboarding-dialog crashed，
// 连带侧栏任务链路停摆）。空 discovery=首启提示已处理，onboarding 不弹。
const settingsSyncService = {
  detect: async () => ({ agents: [] }),
  getFirstRunPromptState: async () => ({ handled: true }),
  markFirstRunPromptHandled: async () => {},
  getClaudeAgentsFileMigrationStatus: async () => ({
    sourcePath: "C:\\Users\\mock\\.claude\\agents",
    targetPath: "C:\\Users\\mock\\.zcode\\agents",
    sourceExists: false,
    targetExists: false,
    supported: false,
    unavailableReason: "missingSource",
  }),
  copyClaudeAgentsFileToZcodeAgentsFile: async () => ({
    sourcePath: "C:\\Users\\mock\\.claude\\agents",
    targetPath: "C:\\Users\\mock\\.zcode\\agents",
    status: "skipped",
    overwritten: false,
    skippedReason: "missingSource",
  }),
  importSelected: async () => ({ results: [], totalImported: 0, totalSkipped: 0 }),
};

for (const name of [
  "broadcast", "coding-plan-subscription", "fs", "file-watcher", "git", "terminal", "media-preview", "credential", "system",
  "window-controller", "client-config", "client-scenes", "skills", "skill-sync", "mcp-sync",
  "plugins", "plugin-sync", "subagents", "commands", "hooks", "memory", "usage-stats",
  "feedback", "prompt-attachment-transfer", "bots", "highspeed", "marketing-touch",
  "output-style", "conversation-share", "plugin-ui-bridge", "gen-ui",
]) {
  services.register({ channelName: name }, silentStub);
}
services.register({ channelName: "model-selection" }, modelSelectionService);
services.register({ channelName: "provider-settings" }, providerSettingsService);
services.register({ channelName: "oauth" }, oauthService);
services.register({ channelName: "file" }, fileService);
services.register({ channelName: "settings-sync" }, settingsSyncService);

const server = http.createServer((req, res) => {
  if (req.url === "/api/server-info") {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ version: "mock-1.0", workspaces: [WORKSPACE] }));
    return;
  }
  res.writeHead(404); res.end("mock host: only /api/server-info");
});

const wss = new WebSocketServer({ noServer: true });
server.on("upgrade", (req, socket, head) => {
  if (req.url === "/ws") wss.handleUpgrade(req, socket, head, (ws) => wss.emit("connection", ws, req));
});

wss.on("connection", (ws) => {
  const emitters = { data: new Emitter(), close: new Emitter(), end: new Emitter() };
  ws.binaryType = "arraybuffer";
  ws.on("message", (buf) => {
    try {
      emitters.data.fire(VSBuffer.wrap(new Uint8Array(buf)));
    } catch (err) {
      // dev mock：单条消息处理失败只记日志断这条消息，不带崩进程
      console.error("[mock-host] message handler error (suppressed):", err);
    }
  });
  ws.on("close", () => { emitters.close.fire(); emitters.end.fire(); });
  ws.on("error", () => { emitters.close.fire(); emitters.end.fire(); });

  const isocket = {
    onData: emitters.data.event, onClose: emitters.close.event, onEnd: emitters.end.event,
    write: (b) => { if (ws.readyState === ws.OPEN) ws.send(b.buffer); },
    end: () => ws.close(), drain: async () => {}, dispose: () => ws.close(),
  };
  const protocol = new SocketProtocol(isocket);
  const rawServer = new ChannelServer(protocol, "mock-server");
  const channelServer = new LoggingChannelServer(rawServer, (...a) => console.log("[rpc]", ...a));
  services.exposeOnChannelServer(channelServer);
  emitters.close.event(() => rawServer.dispose());
  console.log("[mock-host] channel server attached");
});

server.listen(PORT, () => {
  console.log(`[mock-host] listening http+ws on :${PORT} (synthetic data, dev-only)`);
  console.log(`[mock-host] setting file: ${MOCK_SETTING_PATH}`);
});
