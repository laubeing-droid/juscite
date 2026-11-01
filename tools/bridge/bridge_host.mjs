#!/usr/bin/env node
// Juscite 应用桥进程——打包桌面端经 desktopHostProcess 拉起的应用级单例（entry=本文件，
// packages/desktop/src/main/desktopHostProcess.ts:75；WebSocket :3030 + /api/server-info）。
// 沿称 "mock-host" 仅指帧内业务数据为合成 mock 语义（上游骨架遗传），非 dev-only 工具（复核 M2 正名）。
// 协议与注册机制结论见同目录 NOTES.md；骨架照抄上游 server/src/http.ts 挂载模式。
import http from "node:http";
import { spawn } from "node:child_process";
// L1b 组合根（r12 波2.5）：产品层只经 runtime-port 域面调 runtime；oc28 wire 知识全在
// adapter（packages/juscite-runtime-adapters/opencode），换底座=只换本行（设计 §一 L1a/L1b）。
import { createOpenCodeRuntime } from "../../packages/juscite-runtime-adapters/opencode/src/opencodeAdapter.mjs";
import { openBridgeStore } from "./bridge_store.mjs";
import { randomUUID } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { extname, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocketServer } from "ws";
import { createTaskGroupService } from "../../packages/services/src/task-groups/index.ts";
import { runTasksDatabaseMigrations } from "../../packages/services/src/session/tasksDatabase/migrations.ts";
import { VSBuffer, SocketProtocol, ChannelServer, LoggingChannelServer, ProxyChannel, Event, Emitter } from "@zcode/rpc";
import { IConversationShareService } from "@zcode/services";
// 功能#27 所内分享（步骤3 树内开闸）：上游分享服务实现整包拎起，分享站契约由本机桥面承接
// （云端分享站在本产品不可用——红线③材料不出域；装配样例=packages/services/src/node.ts createDefaultServices）。
import { ConversationShareService } from "../../packages/services/src/conversation-share/conversationShareService.ts";
import { ConversationShareHttpClient } from "../../packages/services/src/conversation-share/conversationShareHttpClient.ts";
import { createLocalConversationShareArtifactSource } from "../../packages/services/src/conversation-share/conversationShareArtifactSource.ts";
import { createShareStation } from "./share_station.mjs";
import {
  ServiceCollection,
  ISettingService,
  IZCodeAgentService,
  IZCodeSessionService,
  IZCodeTaskService,
  IOnboardingRecordService,
  ITaskGroupService,
  IPluginManagementService,
  ISubagentsService,
  IOffPeakTaskService,
  ISkillsService,
} from "@zcode/services";
import { createPluginManagementService } from "../../packages/services/src/plugins/pluginManagementService.ts";
// 功能 #22 定时任务（ZCode 顶·树内开闸）：管理/调度/存储全在树内（AutomationService/Repo + croner），
// 桥只做接线——任务表落桥同库 SQLite（repo 注入 bridge-{port}.db），派发翻译成本桥会话回合。
import { AutomationService } from "../../packages/services/src/session/automationService.ts";
import { AutomationRepo } from "../../packages/services/src/session/automationRepo.ts";
import { computeAutomationNextRunAt, isOneShotAutomation } from "../../packages/services/src/session/automationCron.ts";
import {
  parseZip, installSkillArchiveEntries, listInstalledSkillDirs, describeInstalledSkill, removeSkillDir, skillsRoot,
} from "./skills_service.mjs";
// 功能 #25 文档对比（施工单-03 任务四）：确定性行 diff（增/删/改分类），纯算法不靠模型。
import { splitLines, diffOps, buildHunks, diffStats } from "./docdiff.mjs";
// 功能 #29 新手引导与产品指引（RE-29 §3）：onboarding 状态机/演示集导入/法库指路（F1/F2）。
import {
  initOnboardingState, getOnboardingState, completeOnboarding, setProductGuideStatus,
  lawsLibraryStatus, isLawsRetrievalIntent, LAWS_GUIDANCE, LAWS_INDEX_PATH,
} from "./onboarding_service.mjs";
// 功能 #31 支持通道（RE-31 §3）：工单+授权诊断包+无运营平台降级形态（落盘/导出）。
import {
  resolveOpsBase, supportRootDir, appVersionOf, generateTicketKey,
  buildSupportDiagnostics, buildTicketMarkdown, writeTicketFile, listLocalTickets,
} from "./support_service.mjs";
// 功能 #30 安全审计中心（RE-30 §3.3）：audit 哈希链单实例（append/verify/migrate/list，三代哈希）。
import { createAuditService } from "./audit_service.mjs";
// 桥内机制件（施工单-06，机制规格-01/02 等量自写）：通用异步任务壳 + 审批关卡 gate 节点。
import { createTaskShell } from "./taskshell_service.mjs";
import { createFlowGate } from "./flow_gate_service.mjs";
// 功能 #13 法条手册（RE-13 §3.2）：包聚合/解析/搜索/收藏/包管理面 + /api/legal/laws* HTTP 路由。
import { createLawbookService } from "./lawbook_service.mjs";
// 功能 #14 引证核验（RE-14 §3.3）：轻量引擎子进程调用 + /api/verify/* 四端点 + F4 落账。
import { createCitationVerifyService, resolveCitationEnginePath, resolveCitationPackDir } from "./citation_verify_service.mjs";
// 功能 #6 材料上传解析（RE-6 §3）：四步材料管道+案件材料面+对话附件库+回合注入 + /api/cases/materials* 与 /api/attachments* 路由。
// 后三个导出=可视化B轨摄入对账只读消费（A7：只读公开行为契约——listMaterials/readOriginal 服务面+文本层/解码/抽取公开函数）。
import { createMaterialService, decodeTextBuffer, extractDocxMaterial, extractPdfTextLayer } from "./material_service.mjs";
// 功能 #42 电子数据取证（RE-42 §2.A-H）：三类首做（微信记录 PDF→页/坐标锚+对话段、流水/表格 xlsx·csv→行面）
// + 虚拟归类 + 候选清单与校验 + 审查标注预置；内核=@juscite/edisc（packages/juscite-edisc 出树自有包）。
import { createEdiscService } from "./edisc_service.mjs";
// 功能 #32 整理与尽调（RE-32 §2 行为 1-16+增补 S1-S3）：任务看板（三分组/确认门/子任务/Flow 契约/成果版本）
// + 字段模板三态一源批量提取台账 + 清单整理与缺失核对 + 历史沿革章节与 Word 导出；
// 内核=packages/juscite-legal/src/kernel/diligence*.ts（相对路径消费同 kernel 先例）；
// 批量提取挂 r11 通用异步任务壳（register("diligence-extract")，入队即回轮询取件）。
import { createDiligenceService } from "./diligence_service.mjs";
// 【#21 安全层】Allow/Ask/Deny 工具策略决策函数+审批缓存（RE-21 增补 §3.2）+宿主最后闸（§3.4）。
// 审计表单实例在 bridge_store（迁移 0021）；shell 默认=关（2026-10-30 主控裁定），用户可翻设置 toolSecurity.shellEnabled。
import { TOOL_POLICY_VERSION, PERMISSION_MODES, decideToolCall, createApprovalCache } from "./tool_policy.mjs";
import { gateCommand, gateWorkspacePath } from "./host_gate.mjs";
// 功能 #11 Word 红线改稿（施工单-03 任务一）：docx 提取与终稿装配（确定性小件，回合走 oc28 会话通道）。
import { extractDocxText, applyRedlineDecisions } from "./redline_service.mjs";
// 功能 #10 文书起草技能（自写 SKILL.md；随 #21 技能安装线分发——内置合成技能，禁抄竞品文案）
import { DRAFT_SKILL_MD, DRAFT_SKILL_TRIGGERS } from "./draft_skill.mjs";
// 功能 #4 办案时间线技能（RE-4 §3 技能类附加；真源=skill-presets/timeline-generation 包，运行时读取）
import { TIMELINE_SKILL_MD, TIMELINE_SKILL_META } from "./timeline_skill.mjs";
import { RESEARCH_SKILL_MD, RESEARCH_SKILL_META } from "./research_skill.mjs";
// 功能 #42 电子数据取证技能（RE-42 §3.4 技能注入；真源=skill-presets/edisc 包，运行时读取）
import { EDISC_SKILL_META, EDISC_SKILL_MD } from "./edisc_skill.mjs";
// 【施工波三轮·#7 证据目录全量面】技能包两件（主=证据目录生成/姊妹=证据材料整理；真源=skill-presets 包，运行时读取）
import { EVIDENCE_CATALOG_SKILL_META, EVIDENCE_CATALOG_SKILL_MD } from "./evidence_catalog_skill.mjs";
import { EVIDENCE_MATERIALS_SKILL_META, EVIDENCE_MATERIALS_SKILL_MD } from "./evidence_materials_skill.mjs";
// 【施工波三轮·#7 证据目录全量面】触发语义+交付链内核（@juscite/legal 出树自有包；桥只接线）：
// 激活四通道/预算 24000 字节/上限 3（skillActivationModel）；路径提取/双层过滤/版本族去重/
// docx 唯一产物与"文件在哪"短路（deliveryChainModel）。RE-7 §3 技能类附加+流程"交付"段。
import {
  planSkillInjection, searchSkills, loadSkill,
} from "../../packages/juscite-legal/src/kernel/skillActivationModel.ts";
import {
  extractDeliveredPaths, filterDeliveries, dedupeVersionFamily,
  completedWordDeliveryMessage, deliveredWordLocationAnswer, requestedArtifactKinds,
} from "../../packages/juscite-legal/src/kernel/deliveryChainModel.ts";

// 功能 #10 模板文书起草（RE-10）：引擎/存储/导出三件（持久化只落 %APPDATA%\Juscite）。
import {
  CATALOG_TEMPLATES, resolveDocumentTemplate, withInferredTemplateFields,
  assembleGenerationPrompt, settleGeneration, WORKFLOW_STAGES,
  extractDeliveryAnchors, validateDeliveryContent, FACT_FIDELITY_BLOCK,
} from "./draft_engine.mjs";
import {
  listUserTemplates, getUserTemplate, createUserTemplateFromUpload, upsertUserTemplate,
  deleteUserTemplate, readTemplateSourceDocx, listDraftHistory, getDraftHistory,
  addDraftHistoryRecord, deleteDraftHistory,
} from "./draft_store.mjs";
import { markdownToLegalDocx, docxInPlaceFill, buildCaseReportDocx } from "./draft_docx.mjs";

// 【步骤4·案件族底座】MatterLite：桥内轻量案件表（RE-3 §3.2/§3.3/§3.4-3）——枚举单源/强校验/行形状。
import {
  MATTER_STATUS_DEFS, normalizeCaseFields, mergeCalendarOverride,
  caseToProtocol, todoToProtocol, eventToProtocol, optionalDate, requiredDate, optionalNote,
  BOARD_KINDS, BOARD_DEFAULT_KIND, BOARD_DAY_FIRE_TIME, BOARD_DEFAULT_LEAD_MINUTES,
  normalizeEventFields, isBoardTime,
} from "./matter_service.mjs";
// 功能 #19 轻量知识图谱（步骤4·RE-19）：共享纯模型（校验/规则建图/文件名净化）——桥/UI/自测单一来源。
import {
  validateGraph, buildGraphFromCaseRecords, sanitizeGraphFilename,
} from "../../packages/juscite-legal/src/kernel/caseGraphModel.ts";
// 【施工波-20261030·可视化B轨】#4 大事记表/#19 庭审对抗图：机制契约单一来源=顶层自有包 @juscite/vizb
// （四契约：模型出语义 JSON/脚本算几何/文字=原句子序列/判据守卫；AGPL-3.0 净室，注册点见文末 vizb 块）。
import * as vizbChronicle from "../../packages/juscite-vizb/src/chronicle/index.ts";
import * as vizbConfrontation from "../../packages/juscite-vizb/src/confrontation/index.ts";
// 【施工波二轮·可视化B轨收尾】光栅化环境面（A9 字体坑机制：PNG 前换单一族+日志报出；
// 渲染器/字族缺位=跳过 PNG 导出不拖垮 SVG 交付——cairo 缺失先例同款姿态）。
import { rasterizeSvgToPng } from "./vizb_raster.mjs";
// 【步骤4·#5 冲突查重】检索纯模型（RE-5 §3.2）：归一化/探针/四级匹配/严重度矩阵/去重键/
// 条件构造/预检规范化/指纹载荷/新增命中比对——桥/UI/自测单一来源（哈希在桥侧做，模型零 node 依赖）。
import {
  CONCLUSIONS, ROLES, AUTO_NOTE_FORMAL, AUTO_NOTE_REVIEW,
  nameMatchLevel, severityOfNameHit, reasonOfHit, dedupeHits, sortHitsDesc,
  buildNameProbes, buildConflictQueries, idVariants, normalizeIdNumber,
  normalizePrecheckQueries, pickSeverity, bumpForIdMatch,
  fingerprintPayload, newHitKeys, hasHighOrBlocking, reviewGateOutcome,
} from "../../packages/juscite-legal/src/kernel/conflictModel.ts";
// 【步骤4·#4 案件时间线】CaseEvent 纯模型（RE-4 §3）：值域/排序/行键/开庭归一/日期兜底/后处理。
import {
  AUTO_EVENT_TYPES, CB_EVENT_TYPES, FACT_EVENT_TYPES, RECORDABLE_EVENT_TYPES,
  EDITABLE_FIELDS, isCalendarDate, normalizeImportance, normalizeStatus, sortCaseEventsFull,
  parseExtractionOutput, postprocessExtracted, planCaseEventMerge,
  assembleExtractionPrompt, docHintOf, applyCaseEventEdit, restoreCaseEventField,
  sanitizeSourceRefs, sanitizePayload,
  buildCaseTimelineReportLines, CASE_REPORT_EMPTY_TEXT,
} from "../../packages/juscite-legal/src/kernel/caseTimelineModel.ts";
// 功能 #20 所内知识问答（步骤4·RE-20）：检索内核纯函数（B51-B58/B62）——分块/规划/打分/
// 软惩罚重排/RRF/上下文预算/提示词装配/路径安全，全部正则+状态机零模型。
import {
  KB_SYNC_DEFAULT_LIMIT, KB_SYNC_CONTRACT_LIMIT, KB_FTS_THRESHOLD, KB_RECALL_LIMIT,
  KB_MAX_SOURCES, KB_MANAGED_EXTS, KB_TEXT_EXTS, KB_DOC_EXTS, KB_BINARY_PREVIEW_EXTS,
  KB_SKIP_FILES, KB_SKIP_DIRS,
  isMetaSidecar, normalizeQuery, planQueries, tokenize, chunkText, scoreChunk, rankReasonOf, rerank,
  rrfFuse, isMetaExpired, buildRetrievalContext, buildAskPrompt, threadTitle, isKbThreadTitle,
  safeRelPath, extOf, ruleClassify, KB_CATEGORIES, inferDocLayer, routeLayer, cleanAnswer, sha256,
  kbShellBypassGuard, KB_BYPASS_ADVISORY,
} from "./kb_service.mjs";
// 【步骤4·#16 调研报告】调研纯模型（RE-16 §3）：即时规划/规划评分器/三桶切分/报告完整性/
// 证据门/工具剔除/配额错误/裸话题/导出预处理/编辑落账/导出命名/提示词装配/法规库兜底——
// 桥/UI/合成自测单一来源（同 caseGraphModel/caseTimelineModel 先例）。
import {
  MAX_REPORT_CONTINUATIONS,
  newResearchRecord, normalizeRecord, applyReportEdit, exportFileName,
  isPlanPublished, extractStageNo, isReportComplete, splitResearchStream,
  buildResearchPrompt, primarySourceDirective, buildStageDirective,
  evidenceGate, cullToolCatalog, isQuotaAuthError, isBareResearchTopic,
  toResearchStep, buildEvidenceDirective, buildQuotaFallbackDirective, classifyContinuation,
  preprocessReportMarkdown, researchThreadTitle, deriveFromRows,
  lookupLawsLibrary, LAW_LOOKUP_UNAVAILABLE, isResearchThreadTitle,
} from "../../packages/juscite-legal/src/kernel/researchModel.ts";
// 【步骤4·#26 LAN 团队同步】团队同步纯内核+网络层（RE-26 §3；F13 team 段守卫/F14 剥密单源）。
import { createTeamSync } from "./team_sync_service.mjs";
import { mergeSettingKeepTeam, sanitizeValueForFrontend, projectCaseSnapshot } from "./team_sync_model.mjs";
// 【步骤4·#18 学习迭代】运行时（RE-18 §3.5：桥侧 TS 模块+桥会话链路复用；存储根 Juscite 分区内）
import { createLearningRuntime } from "./learning_runtime.mjs";
// 【步骤4·#36 分层记忆】运行时（RE-36 §3：四层两作用域本地可读文件族；存储根 Juscite 分区内）
import { createLayeredMemoryRuntime } from "./layered_memory_runtime.mjs";
// 【步骤5·F78/F79 许可骨架】许可读取与形态判定（RE-B3 §3：三态 fail-closed，文件=形态开关非凭据）。
import { readLicenseShape } from "./license_shape.mjs";
import { LEARNING_THREAD_PREFIX, TURN_TIMEOUT_MS } from "../../packages/juscite-legal/src/kernel/learningModel.ts";

const PORT = Number(process.env.BRIDGE_PORT ?? 3030); // 桥固定占 3030（vite 代理指向）
// 【步骤4·#3 看板日历面】date-only 行归一开火时刻（§3.4-5 桥常量可配）+agent 查询 limit 钳制（对拍行 86：1..50）
const boardDayFireTime = () => {
  const v = process.env.BRIDGE_BOARD_DAY_FIRE_TIME;
  return v && isBoardTime(v) ? v : BOARD_DAY_FIRE_TIME;
};
const boardQueryLimit = (v) => {
  if (v === undefined || v === null || v === "") return 20;
  if (!Number.isInteger(v) || v < 1 || v > 50) throw new Error("limit 须为 1..50 整数（实收 " + JSON.stringify(v) + "）");
  return v;
};
// ── 【步骤4·#4 案件时间线】CaseEvent 装配器（RE-4 §3；模块层单点，auto 通道/挂点/桥面共用）──
// 本地日历日（§3.6 确定性纪律：本地时区 YYYY-MM-DD，无时区隐式转换）
function todayStrOf() {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}
// auto 通道行装配（唯一写入口内部固定 origin='auto'/provenance='system'/status=confirmed/
// importance=normal；date 缺省=动作发生当日，LL F3 等量）
function autoCaseEventRec(matterId, eventType, note, dateStr) {
  const now = new Date().toISOString();
  return {
    event_id: "ce_" + randomUUID().slice(0, 8), matter_id: matterId, event_type: eventType,
    date: dateStr ?? todayStrOf(), date_label: null, note: note ?? null, expires_at: null,
    status: "confirmed", importance: "normal", phase: null, side: null,
    origin: "auto", source_refs_json: "[]", payload_json: null, provenance: "system",
    locked_fields_json: "[]", orig_json: null, deleted: 0, created_at: now, updated_at: now,
  };
}
// 通道一行装配（llm_extract 固定 origin/provenance=ai；row.eventType 允许白名单外自由文本兜底）
function extractedCaseEventRec(matterId, row) {
  const now = new Date().toISOString();
  return {
    event_id: "ce_" + randomUUID().slice(0, 8), matter_id: matterId, event_type: row.eventType,
    date: row.date, date_label: row.dateLabel, note: row.note, expires_at: row.expiresAt,
    status: row.status, importance: row.importance, phase: row.phase, side: row.side,
    origin: "llm_extract", source_refs_json: JSON.stringify(row.sourceRefs ?? []),
    payload_json: row.payload ? JSON.stringify(row.payload) : null, provenance: "ai",
    locked_fields_json: "[]", orig_json: null, deleted: 0, created_at: now, updated_at: now,
  };
}
// store snake 行 → 协议 camel 形状（桥 JSON-RPC / UI 共用）
function caseEventToProtocol(row) {
  const jsonArrSafe = (s) => { try { const v = JSON.parse(s || "[]"); return Array.isArray(v) ? v : []; } catch { return []; } };
  const jsonObjSafe = (s) => { try { const v = JSON.parse(s ?? "null"); return v && typeof v === "object" && !Array.isArray(v) ? v : null; } catch { return null; } };
  return {
    eventId: row.event_id, matterId: row.matter_id, eventType: row.event_type,
    date: row.date ?? null, dateLabel: row.date_label ?? null, note: row.note ?? null,
    expiresAt: row.expires_at ?? null, status: row.status, importance: row.importance,
    phase: row.phase ?? null, side: row.side ?? null, origin: row.origin,
    sourceRefs: jsonArrSafe(row.source_refs_json), payload: jsonObjSafe(row.payload_json),
    provenance: row.provenance, lockedFields: jsonArrSafe(row.locked_fields_json),
    orig: jsonObjSafe(row.orig_json), deleted: row.deleted === 1,
    createdAt: row.created_at, updatedAt: row.updated_at,
  };
}
const MOCK_SETTING_PATH = join(homedir(), "AppData", "Roaming", "Juscite", "config", "mock", "setting.json");
// 本地演示 workspace：不带 workspaceIdentity——UI 的 isRemoteWorkspaceTarget 把带 identity
// 的 tab 判为远程断连占位（workspaceServiceResolver.ts:49），任务分片被整段排除，
// 侧栏任务列表/工作区准备全不启动（现象=“lvyin-demo 重新连接”+任务永远空）。
const WORKSPACE = { path: "D:\\mock\\lvyin-demo" };
const WORKSPACE_KEY = WORKSPACE.path; // workspaceKey 口径 = workspaceIdentity ?? workspacePath
// F5 单源派生（RE-B1 §3.2）：会话键写/读/回执统一走此函数，禁止再散写派生链。
function workspaceKeyOf(params) {
  const identity = typeof params?.workspaceIdentity === "string" ? params.workspaceIdentity.trim() : "";
  return identity || params?.workspacePath || WORKSPACE_KEY;
}
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
  providerFamilyDomain: "zai", // 必须合法家族 id（zai|bigmodel）：usePlanIdentitySnapshot 经 getModelProviderFamilySpec 查表，非法值 undefined.individualCodingPlanProviderId 崩输入区
  // 【#21 安全层】工具策略设置（RE-21 增补 §3.1「三档模式进设置」+§5① 裁定）：
  // shellEnabled 默认 false=关（2026-10-30 主控裁定——策略层 deny 默认与红线一致；用户可翻）；
  // permissionMode 三档 always_ask|smart|yolo，默认 smart。
  toolSecurity: { shellEnabled: false, permissionMode: "smart" },
};

function loadSetting() {
  try { return JSON.parse(readFileSync(MOCK_SETTING_PATH, "utf-8")); } catch { return DEFAULT_SETTING; }
}
function saveSetting(s) {
  mkdirSync(join(MOCK_SETTING_PATH, ".."), { recursive: true });
  writeFileSync(MOCK_SETTING_PATH, JSON.stringify(s, null, 2), "utf-8");
}

// ---------- 材料通道（施工单-03 #25/#11 共用）：workspace/materials 目录下的合成材料 ----------
// 外边界防御（HERO）：RPC 可指任意路径，这里收口——材料名禁路径分隔符与 ..，落点必须仍在
// materials 目录内；扩展名白名单。#25 本轮只放行纯文本（.txt/.md，= #6 解析产物文本形态）。
const MATERIALS_TEXT_EXT = new Set([".txt", ".md"]);
const MATERIALS_WORD_EXT = new Set([".docx"]); // #11：红线改稿另收 Word 材料
const MATERIALS_ALL_EXT = new Set([...MATERIALS_TEXT_EXT, ...MATERIALS_WORD_EXT]);
function materialsDirOf(workspacePath) {
  const ws = typeof workspacePath === "string" && workspacePath.trim() ? workspacePath.trim() : WORKSPACE.path;
  return join(ws, "materials");
}
function resolveMaterialPath(workspacePath, name, exts = MATERIALS_TEXT_EXT) {
  const dir = materialsDirOf(workspacePath);
  if (typeof name !== "string" || !name.trim()) throw new Error("材料名不能为空");
  if (/[\\/]|\.\./.test(name)) throw new Error(`材料名不得含路径分隔符或 ..：${name.slice(0, 40)}`);
  if (!exts.has(extname(name).toLowerCase())) throw new Error(`仅支持纯文本材料（.txt/.md）：${name.slice(0, 40)}`);
  const p = join(dir, name);
  if (!p.toLowerCase().startsWith(dir.toLowerCase() + "\\")) throw new Error("材料落点越出 materials 目录");
  return p;
}
function readMaterialText(workspacePath, name) {
  const p = resolveMaterialPath(workspacePath, name);
  let text;
  try {
    text = readFileSync(p, "utf-8");
  } catch (e) {
    throw new Error(`材料读取失败（${name}）：不存在或不可读`);
  }
  if (text.includes("\u0000")) throw new Error(`材料（${name}）含二进制内容，拒绝解析`);
  return { name, path: p, text };
}

// #11 红线改稿材料：另收 .docx（零依赖 unzip 提取 document.xml 正文；w:del 不计、w:ins 计入）。
function readRedlineMaterial(workspacePath, name) {
  if (extname(String(name ?? "")).toLowerCase() === ".docx") {
    const p = resolveMaterialPath(workspacePath, name, MATERIALS_ALL_EXT);
    let bytes;
    try {
      bytes = readFileSync(p);
    } catch (e) {
      throw new Error(`材料读取失败（${name}）：不存在或不可读`);
    }
    return { name: String(name), path: p, text: extractDocxText(bytes) };
  }
  return readMaterialText(workspacePath, name);
}


// #11 修订详情出栈（snake 行 → camel 协议形状）
function redlineDetail(workspaceKey, revisionId) {
  const rec = store.getRedline(workspaceKey, revisionId);
  if (!rec) throw new Error("改稿记录不存在");
  const items = store.listRedlineItems(workspaceKey, revisionId).map((i) => ({
    itemIdx: i.item_idx, type: i.type, aStart: i.a_start, aCount: i.a_count,
    bStart: i.b_start, bCount: i.b_count, oldText: i.old_text, newText: i.new_text, decision: i.decision,
  }));
  return {
    revision: {
      revisionId: rec.revision_id, materialName: rec.material_name, instruction: rec.instruction,
      status: rec.status, originalText: rec.original_text, revisedText: rec.revised_text,
      finalText: rec.final_text, finalPath: rec.final_path, error: rec.error,
      createdAt: rec.created_at, updatedAt: rec.updated_at,
    },
    items,
  };
}

// #11 改稿回合：专用 oc28 会话一发一收（800ms 轮询+稳定 2 次收口，180s 时限）。
// 不走对话投影/回执链（红线稿不是会话消息），但同用 oc28 凭据自愈与模型配置。
const REDLINE_TURN_TIMEOUT_MS = 180000;
async function runRedlineTurn(instruction, originalText) {
  const oc28Id = "ses_redline_" + randomUUID().slice(0, 8);
  await runtime.createSession({ sessionId: oc28Id, workspacePath: WORKSPACE.path, title: "红线改稿（合成）", model: BRIDGE_MODEL });
  const prompt = "你是法律文书改稿助手。下面给出一篇文书全文和改稿要求。请只输出修改后的文书全文：保持原有段落划分与条款编号风格，只做改稿要求所述的修改，不要添加任何解释、前言或结语，不要使用 Markdown 代码块。\n\n【改稿要求】\n" + instruction + "\n\n【文书全文】\n" + originalText;
  const before = new Set((await runtime.pullTranscript(oc28Id)).map((e) => e.messageId));
  await runtime.send(oc28Id, { clientMessageId: "msg_" + randomUUID().slice(0, 8), text: prompt });
  let seen = "";
  let stable = 0;
  const deadline = Date.now() + REDLINE_TURN_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 800));
    const msgs = (await runtime.pullTranscript(oc28Id)).filter((e) => !before.has(e.messageId));
    const full = msgs.filter((e) => e.role === "assistant" && !e.error)
      .map((e) => e.text)
      .filter(Boolean).join("\n\n");
    if (full.length > seen.length) { seen = full; stable = 0; continue; }
    const err = [...msgs].reverse().find((e) => e.error);
    if (err && !seen) throw new Error(err.error);
    if (seen) stable++;
    if (stable >= 2) return seen;
  }
  throw new Error("模型改稿未在时限内完成");
}

// 【步骤4·#4 案件时间线】通道一抽取回合：专用 oc28 会话一发一收（800ms 轮询+稳定 2 次收口，
// 180s 时限）——同 runRedlineTurn 手法，不走对话投影/回执链。
const TIMELINE_TURN_TIMEOUT_MS = 180000;
async function runTimelineExtractTurn(prompt) {
  const oc28Id = "ses_timeline_" + randomUUID().slice(0, 8);
  await runtime.createSession({ sessionId: oc28Id, workspacePath: WORKSPACE.path, title: "时间线抽取（合成）", model: BRIDGE_MODEL });
  const before = new Set((await runtime.pullTranscript(oc28Id)).map((e) => e.messageId));
  await runtime.send(oc28Id, { clientMessageId: "msg_" + randomUUID().slice(0, 8), text: prompt });
  let seen = "";
  let stable = 0;
  const deadline = Date.now() + TIMELINE_TURN_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 800));
    const msgs = (await runtime.pullTranscript(oc28Id)).filter((e) => !before.has(e.messageId));
    const full = msgs.filter((e) => e.role === "assistant" && !e.error)
      .map((e) => e.text)
      .filter(Boolean).join("\n\n");
    if (full.length > seen.length) { seen = full; stable = 0; continue; }
    const err = [...msgs].reverse().find((e) => e.error);
    if (err && !seen) throw new Error(err.error);
    if (seen) stable++;
    if (stable >= 2) return seen;
  }
  throw new Error("模型抽取未在时限内完成");
}

// ══ 功能 #20 所内知识问答（步骤4·RE-20）：托管根/检索编排/同步/问答线程链 ══
// 托管根（§3 数据模型）：默认 %APPDATA%/Juscite/kb/files；BRIDGE_KB_ROOT 仅测试覆盖（合成材料）。
const KB_ROOT = process.env.BRIDGE_KB_ROOT
  || join(homedir(), "AppData", "Roaming", "Juscite", "kb", "files");
// 问答线程独立工作区键（B50 主对话列表隔离的第二道闸：主工作区 sessions-index 永不携带）；
// 标题前缀过滤（isKbThreadTitle）为第一道闸（synthTaskMetas），与竞品 chat-store 同机制。
const KB_WORKSPACE_KEY = "kb://juscite-kb";

// 【步骤4·#16 调研报告】调研线程独立工作区键（B09 独立内部会话不进主对话列表：与 KB 同款双闸——
// 独立 workspaceId + 主对话命令面直发拒绝）。取消/死亡两集合：取消=停止续跳；死亡=链尾不复活已删行。
const RESEARCH_WORKSPACE_KEY = "research://juscite-research";
// 【步骤4·#18 学习迭代】学习线程独立工作区键（C8 同款双闸：主列表不携带+忙门/语料排除）
const LEARNING_WORKSPACE_KEY = "learning://juscite-learning";
let learningRuntime = null; // 学习迭代运行时（模块尾创建；早声明供回合链注入点引用）
let layeredMemory = null; // 分层记忆运行时（模块尾创建；早声明供回合链注入点引用）
const researchCancelled = new Set();
const researchDead = new Set();
const RESEARCH_CHAIN_POLL_MS = 300;      // 续跳收口轮询
const RESEARCH_CHAIN_TIMEOUT_MS = 560000; // 单跳收口熔断（与 runAssistantTurn 内 150s 时限留余量）

// ── #16 调研记录持久化助手（文档列 JSON + 键面列双形；死亡集合防链尾复活已删行）──
const researchSleep = (ms) => new Promise((r) => setTimeout(r, ms));
function researchRecordFromJson(json) {
  try { return normalizeRecord(JSON.parse(json)); } catch { return null; } // 坏数据容错回 null（B46 等量语义）
}
// B27 轻量期等量（对拍 28）：启动前确认检索源状态再首轮——本地法规库可用性即自家"初始化等待"面
// （官方法规 API/真实 MCP 初始化等待随数据工程解挂，RE-16 §5.1 钦定挂起，此处为可执行的同构面）。
function researchLawsAvailability() {
  if (process.env.BRIDGE_LAWS_INDEX) {
    try { return JSON.parse(readFileSync(process.env.BRIDGE_LAWS_INDEX, "utf-8")).enabled !== false; } catch { return false; }
  }
  try { return lawsLibraryStatus().available; } catch { return false; }
}
function persistResearchRecord(rec, { force = false } = {}) {
  if (!force && researchDead.has(rec.id)) return;
  store.upsertResearchRecord({
    id: rec.id, status: rec.status, query: rec.query, thread_id: rec.threadId ?? null,
    record_json: JSON.stringify(rec), updated_at: Date.now(),
  });
}
function mergeResearchRecord(rec, patch) {
  const next = { ...rec, ...patch, updatedAt: Date.now() };
  persistResearchRecord(next);
  return next;
}
function finalizeResearchRecord(rec, patch, { force = false } = {}) {
  const next = { ...rec, ...patch, updatedAt: Date.now() };
  persistResearchRecord(next, { force });
  return next;
}
const kbSourcesByThread = new Map(); // threadId -> [{n,title,path,relevance}]（只保留最近一轮，B41）
// 文本抽取（v1 面）：文本 11 种直读 utf-8 + .docx 走 #11 抽取器；pdf/ppt/xlsx 等
// 二进制格式托管但不索引（待 #6 材料上传解析抽取管线落位后接入——诚实边界，提交说明同步）。
function kbReadTextIfIndexable(absPath, ext) {
  if (KB_TEXT_EXTS.includes(ext)) {
    const buf = readFileSync(absPath);
    if (buf.includes(0)) return null; // 二进制混入的伪文本文件不入索引（防乱码入模）
    return buf.toString("utf-8");
  }
  if (ext === ".docx") {
    try { return extractDocxText(readFileSync(absPath)); } catch { return null; }
  }
  return null;
}
function kbAbs(rel) {
  const relNorm = safeRelPath(rel);
  const abs = join(KB_ROOT, ...relNorm.split("/"));
  if (!abs.toLowerCase().startsWith(KB_ROOT.toLowerCase() + "\\")) throw new Error("知识库路径越出托管根（逃逸拒绝）");
  return { rel: relNorm, abs };
}
// 同步遍历：返回 [{rel, abs, sizeBytes, mtimeMs}]（跳过 index.json/*.meta.json/SKIP_DIRS/隐藏项，B62/B61）
function kbWalkFiles() {
  const out = [];
  const walk = (dir, prefix) => {
    let entries;
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      if (e.name.startsWith(".") || KB_SKIP_DIRS.has(e.name)) continue;
      const rel = prefix ? prefix + "/" + e.name : e.name;
      const abs = join(dir, e.name);
      if (e.isDirectory()) { walk(abs, rel); continue; }
      if (!e.isFile()) continue; // 符号链接等非普通文件不收（B62 防穿越）
      if (KB_SKIP_FILES.has(e.name) || isMetaSidecar(e.name)) continue;
      if (!KB_MANAGED_EXTS.has(extname(e.name).toLowerCase())) continue;
      let st;
      try { st = statSync(abs); } catch { continue; }
      out.push({ rel, abs, sizeBytes: st.size, mtimeMs: Math.round(st.mtimeMs) });
    }
  };
  walk(KB_ROOT, "");
  out.sort((a, b) => a.rel.localeCompare(b.rel, "zh-Hans-CN"));
  return out;
}
// 侧车元数据（B56）：<file>.meta.json；解析失败静默用默认（§3）
function kbLoadSidecar(rel) {
  try {
    const raw = readFileSync(join(KB_ROOT, ...rel.split("/")) + ".meta.json", "utf-8");
    const v = JSON.parse(raw);
    return v && typeof v === "object" && !Array.isArray(v) ? v : {};
  } catch { return {}; }
}
// 内置文集默认源根扫描（B61，机制同构自写）：env BRIDGE_KB_SOURCE_ROOT 覆盖优先；否则从
// cwd 向上 8 级逐级找 knowledge-base/ 目录（随包轻量文集落位处）。找不到=无内置文集（返回 null）。
function kbBuiltinSourceRoot() {
  if (process.env.BRIDGE_KB_SOURCE_ROOT) return process.env.BRIDGE_KB_SOURCE_ROOT;
  let dir = process.cwd();
  for (let i = 0; i < 8 && dir; i++) {
    const cand = join(dir, "knowledge-base");
    try { if (statSync(cand).isDirectory()) return cand; } catch { /* 该级无，上一级 */ }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}
// 内置文集收进托管根（B61）：源根内受管类型文件复制到「内置文集/」前缀下（同名跳过不覆盖，
// 以首次收进为准）；<file>.meta.json 侧车随行。kb_meta 记源根，同根不重复导（幂等）。返回新收件数。
function kbImportBuiltinCorpus() {
  const root = kbBuiltinSourceRoot();
  if (!root) return 0;
  if (store.kbGetMeta("builtin_source") === root) return 0;
  let added = 0;
  const walk = (dir, prefix) => {
    let entries;
    try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const e of entries) {
      if (e.name.startsWith(".") || KB_SKIP_DIRS.has(e.name)) continue;
      const rel = prefix ? prefix + "/" + e.name : e.name;
      const abs = join(dir, e.name);
      if (e.isDirectory()) { walk(abs, rel); continue; }
      if (!e.isFile() || KB_SKIP_FILES.has(e.name) || isMetaSidecar(e.name)) continue;
      if (!KB_MANAGED_EXTS.has(extname(e.name).toLowerCase())) continue;
      const target = "内置文集/" + rel;
      const { abs: targetAbs } = kbAbs(target);
      if (existsSync(targetAbs)) continue;
      mkdirSync(join(targetAbs, ".."), { recursive: true });
      copyFileSync(abs, targetAbs);
      const sidecar = abs + ".meta.json";
      if (existsSync(sidecar)) copyFileSync(sidecar, targetAbs + ".meta.json");
      added++;
    }
  };
  try { walk(root, ""); } catch { return added; }
  store.kbSetMeta("builtin_source", root);
  return added;
}
// 单路召回：FTS（≥KB_FTS_THRESHOLD 自动启用）token-OR 串 MATCH→LIKE 兜底；内存路径同打分器（B51）。
// 召回=任一查询词命中即可（最终排序由多因子打分完成）；整串子串过滤会把
// 「电子技术监控设备的要求」这类跨标点查询错杀成零召回（实测踩坑已修）。
function kbRecallRoute(route, { folderPrefix, useFts }) {
  const toks = [...new Set(tokenize(route))];
  if (!toks.length) return [];
  if (useFts) {
    try {
      const expr = toks.map((t) => `"${t.replace(/"/g, '""')}"`).join(" OR ");
      const hits = store.kbRecallFts(expr, folderPrefix ?? null, KB_RECALL_LIMIT);
      if (hits.length) return hits;
    } catch { /* MATCH 异常（如纯 2 字符 trigram 不命中）→ 落扫描 */ }
  }
  const scanned = store.kbScanChunks(folderPrefix ?? null, 4000);
  return scanned.filter((c) => toks.some((t) => c.content.includes(t))).slice(0, KB_RECALL_LIMIT);
}
// 检索编排（§3 流程1）：多路召回→打分→RRF→过期/废弃过滤→层路由过滤（不排无标文档，B55）
// →软惩罚重排（B53）→上下文预算装配（B57，来源与可见证据严格对齐）
function kbRetrieve(rawQuery, { folderPrefix } = {}) {
  const routes = planQueries(rawQuery);
  if (!routes.length) return { mode: store.kbFtsMode(), hits: [], contextText: "", sources: [], routes };
  const docCount = store.kbCountDocuments();
  const useFts = docCount >= KB_FTS_THRESHOLD;
  const routeResults = [];
  const routedLayer = routeLayer(rawQuery);
  const idfCache = new Map();
  for (const route of routes) {
    const candidates = kbRecallRoute(route, { folderPrefix, useFts }).map((c) => {
      let keywords = [];
      try { keywords = JSON.parse(c.keywords_json || "[]"); } catch { keywords = []; }
      return {
        chunkId: String(c.chunk_id), docId: c.document_id, content: c.content,
        title: c.title, path: c.rel_path, category: c.category || null, keywords,
        articleNumber: c.article_number ?? null,
        layer: inferDocLayer(c.category || ""),
        routeLayer: routedLayer,
      };
    });
    // 层过滤：仅排除带层标且不匹配的文档；无层标文档一律保留（B55 防淹没语义）
    const layerFiltered = routedLayer === "all"
      ? candidates
      : candidates.filter((c) => !c.layer || c.layer === routedLayer);
    const tokens = tokenize(route);
    const normRoute = normalizeQuery(route);
    // IDF 权重（1..4，B52）：df 取本路候选池；稀有词权重高
    const pool = layerFiltered.length ? layerFiltered : candidates;
    const N = Math.max(1, pool.length);
    const df = new Map();
    for (const t of new Set(tokens)) {
      let n = 0;
      for (const c of pool) if (c.content.includes(t)) n++;
      df.set(t, n);
    }
    const idf = (t) => {
      if (!idfCache.has(t)) {
        const d = df.get(t) ?? 0;
        idfCache.set(t, Math.min(4, Math.max(1, 1 + 3 * (Math.log(1 + N / (d + 0.5)) / Math.log(1 + N)))));
      }
      return idfCache.get(t);
    };
    const scored = pool
      .map((c) => ({ ...c, ...scoreChunk(tokens, normRoute, c, idf) }))
      .filter((c) => c.score > 0)
      .sort((a, b) => b.score - a.score)
      .map((c) => ({ ...c, rankReason: rankReasonOf(c.factors) }));
    routeResults.push(scored);
  }
  const fused = routes.length > 1 ? rrfFuse(routeResults) : routeResults[0] ?? [];
  // 过期/废弃过滤（B56）：侧车 meta 命中即剔除；meta 随命中挂载（B57 徽章推导源）
  const sidecarCache = new Map();
  const alive = fused.filter((h) => {
    if (!sidecarCache.has(h.path)) sidecarCache.set(h.path, kbLoadSidecar(h.path));
    const m = sidecarCache.get(h.path);
    h.meta = m;
    return !isMetaExpired(m);
  });
  const ranked = rerank(alive, { limit: KB_MAX_SOURCES });
  const { contextText, sources } = buildRetrievalContext(ranked);
  return { mode: useFts ? store.kbFtsMode() : "memory", hits: ranked, contextText, sources, routes };
}
// 智能分类模型回合（B17）：批量一文一 JSON；60s 时限；失败抛（调用方回落规则兜底）
async function runKbClassifyTurn(items, extraCandidates) {
  const oc28Id = "ses_kbcls_" + randomUUID().slice(0, 8);
  await runtime.createSession({ sessionId: oc28Id, workspacePath: WORKSPACE.path, title: "知识库分类（合成）", model: BRIDGE_MODEL });
  const body = items.map((it, i) => `【文件${i + 1}】${it.rel}\n${it.text.slice(0, 1500)}`).join("\n\n");
  const candidateNote = extraCandidates?.length
    ? `除上述固定分类外，资料库中已有同名文件夹也可作为候选分类（文件夹名：${extraCandidates.join("/")}），若文件主题与某文件夹明显对应可归入该文件夹名。`
    : "";
  const prompt = "你是律所资料整理员。下面给出若干文件的相对路径与正文开头，请把每个文件归入以下分类之一："
    + KB_CATEGORIES.join("/") + "。" + candidateNote
    + "只输出 JSON 对象：{\"分类结果\":[{\"路径\":\"<原样返回相对路径>\",\"分类\":\"<候选中选一>\"}]}，不要输出其他内容。\n\n" + body;
  const before = new Set((await runtime.pullTranscript(oc28Id)).map((e) => e.messageId));
  await runtime.send(oc28Id, { clientMessageId: "msg_" + randomUUID().slice(0, 8), text: prompt });
  let seen = "";
  let stable = 0;
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 800));
    const msgs = (await runtime.pullTranscript(oc28Id)).filter((e) => !before.has(e.messageId));
    const full = msgs.filter((e) => e.role === "assistant" && !e.error)
      .map((e) => e.text)
      .filter(Boolean).join("\n\n");
    if (full.length > seen.length) { seen = full; stable = 0; continue; }
    if (seen) stable++;
    if (stable >= 2) break;
  }
  if (!seen) throw new Error("分类模型未在时限内返回");
  const m = seen.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("分类模型输出无 JSON");
  const parsed = JSON.parse(m[0]);
  const rows = Array.isArray(parsed["分类结果"]) ? parsed["分类结果"] : [];
  const allowed = new Set([...KB_CATEGORIES, ...(extraCandidates ?? [])]);
  const out = {};
  for (const r of rows) {
    if (r && typeof r["路径"] === "string" && allowed.has(r["分类"])) out[r["路径"]] = r["分类"];
  }
  return out;
}

// ---------- Event 工厂（帧推送面：先回静默 Event，迭代期按 UI 报错补真帧） ----------
// ── 功能 #10 模板文书起草：生成任务表 + AI 学习流水（RE-10 §3.2 模板学习 FSM / §3.3 流程3） ──
// 学习=专用 oc28 会话一发一收（60s 时限）；JSON 解析围栏+裸对象双兜底；类型白名单外回落 text；
// 解析失败=整文降级单字段模板（不炸）；缺 name/content 才判 failed（learningError 保留供重试）。
// 诚实边界：oc28 prompt 面无 temperature/JSON-mode 参数（桥面无该参数轴），超时分档与降级语义等量。
const draftJobs = new Map(); // draftId -> job（进程内；重启即清，进行中任务不跨重启承诺）
const DRAFT_LEARN_TIMEOUT_MS = 60000;
const FIELD_TYPES = new Set(["text", "textarea", "date", "select", "array"]);
function normalizeLearnedField(f) {
  const label = String(f?.label ?? f?.id ?? "").trim().slice(0, 120);
  const type = FIELD_TYPES.has(f?.type) ? f.type : "text"; // 白名单外回落 text
  return {
    id: String(f?.id ?? label).trim().slice(0, 120) || ("字段" + Math.random().toString(36).slice(2, 6)),
    label: label || "未命名字段", type,
    placeholder: typeof f?.placeholder === "string" ? f.placeholder.slice(0, 200) : undefined,
    options: Array.isArray(f?.options) ? f.options.map(String).slice(0, 20) : undefined,
  };
}
async function runDraftLearnTurn(templateText) {
  const oc28Id = "ses_draftlearn_" + randomUUID().slice(0, 8);
  await runtime.createSession({ sessionId: oc28Id, workspacePath: WORKSPACE.path, title: "模板学习（合成）", model: BRIDGE_MODEL });
  const prompt = [
    "你是法律文书模板解析助手。把下面的模板全文整理为结构化 JSON，只输出 JSON 本体，不要解释，不要代码块围栏。",
    'JSON 形状：{"name":"模板名称","description":"一句话用途","content":"保留 {{字段}} 占位符的 Markdown 全文","fields":[{"id":"与占位符同名","label":"中文字段名","type":"text|textarea|date|select|array","placeholder":"填写提示"}],"legalBasis":"主要法律依据（简述）"}',
    "要求：content 必须保留模板原有结构与段落顺序，把原文中的具体信息位置改写为 {{中文字段}} 占位符；fields 须覆盖 content 中出现的全部占位符。",
    "【模板全文】",
    String(templateText ?? "").slice(0, 30000), // 学习 prompt 文档内容截 3 万字
  ].join("\n");
  const before = new Set((await runtime.pullTranscript(oc28Id)).map((e) => e.messageId));
  await runtime.send(oc28Id, { clientMessageId: "msg_" + randomUUID().slice(0, 8), text: prompt });
  let seen = "", stable = 0;
  const deadline = Date.now() + DRAFT_LEARN_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 800));
    const msgs = (await runtime.pullTranscript(oc28Id)).filter((e) => !before.has(e.messageId));
    const full = msgs.filter((e) => e.role === "assistant" && !e.error)
      .map((e) => e.text)
      .filter(Boolean).join("\n\n");
    if (full.length > seen.length) { seen = full; stable = 0; continue; }
    const err = [...msgs].reverse().find((e) => e.error);
    if (err && !seen) throw new Error(err.error);
    if (seen) stable++;
    if (stable >= 2) break;
  }
  if (!seen.trim()) throw new Error("模型学习未在时限内完成");
  // 围栏+裸对象双兜底解析
  let parsed = null;
  const fenced = /```(?:json)?\s*([\s\S]*?)```/.exec(seen);
  const candidates = [fenced ? fenced[1] : null, seen];
  for (const c of candidates) {
    if (!c) continue;
    try {
      const start = c.indexOf("{");
      const end = c.lastIndexOf("}");
      if (start < 0 || end <= start) continue;
      parsed = JSON.parse(c.slice(start, end + 1));
      break;
    } catch { /* 尝试下一候选 */ }
  }
  if (!parsed) return null; // JSON 解析失败 → 调用方整文降级单字段
  if (!parsed.name || !parsed.content) throw new Error("学习结果缺 name/content"); // 才判失败
  return parsed;
}
async function draftScheduleLearning(templateId) {
  try {
    const tpl = getUserTemplate(templateId);
    if (!tpl) return;
    upsertUserTemplate({ ...tpl, learningStatus: "analyzing", learningError: "" });
    let learned = null;
    let failed = "";
    try {
      learned = await runDraftLearnTurn(tpl.content);
    } catch (e) { failed = String(e?.message ?? e); }
    if (learned) {
      const fields = (Array.isArray(learned.fields) ? learned.fields : []).slice(0, 200).map(normalizeLearnedField);
      const merged = withInferredTemplateFields(fields, String(learned.content)); // 未定义 {{占位}} 自动补 textarea
      upsertUserTemplate({
        ...tpl,
        name: String(learned.name).slice(0, 120),
        description: String(learned.description ?? "").slice(0, 300),
        content: String(learned.content).slice(0, 50000),
        fields: merged,
        legalBasis: String(learned.legalBasis ?? "").slice(0, 500),
        learningStatus: "done", learningError: "",
      });
      console.log("[bridge] draft template learned: " + templateId + " fields=" + merged.length);
    } else if (failed) {
      const tpl2 = getUserTemplate(templateId);
      if (tpl2) upsertUserTemplate({ ...tpl2, learningStatus: "failed", learningError: failed });
    } else {
      // 解析失败：整文降级为单字段模板（C7 回退不炸）
      const tpl2 = getUserTemplate(templateId);
      if (tpl2) upsertUserTemplate({ ...tpl2, learningStatus: "done", learningError: "", fields: [{ id: "全文（文本）", label: "全文（文本）", type: "textarea", placeholder: "模板全部文字" }] });
      console.log("[bridge] draft template learn degraded to single-field: " + templateId);
    }
  } catch (e) {
    try {
      const tpl = getUserTemplate(templateId);
      if (tpl) upsertUserTemplate({ ...tpl, learningStatus: "failed", learningError: String(e?.message ?? e) });
    } catch { /* 双失败保留原状 */ }
    console.error("[bridge] draft template learning failed:", e?.message ?? e);
  }
}


const silentEvent = () => {
  const e = new Emitter();
  return e.event;
};
// agentService on* 帧通道表（订阅即静默；M1-D 迭代时逐个换成合成帧发射器）
// 注：onDynamic* 是"动态事件"——必须 (arg) => Event（ProxyChannel.isDynamicEvent 约定）
const AGENT_EVENTS = {
  // 3.16.2 UI 订阅面（缺省会被 ProxyChannel listen 打 Event not found，反复重试）
  onDynamicLocalTtftFacts: () => silentEvent(),
  onAgentRuntimeLifecycle: () => ({ dispose() {} }),
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
// 2026-10-26：真实桥会话进任务列表（此前列表=静态合成，UI 无活跃任务可切视图）。
const liveSessions = new Map();
const sessionsIndexSeq = new Map(); // workspaceId -> 权威 seq
const sessionsIndexSubscriptions = new Map(); // subscriptionId -> { topic, initialSent }
// topic\0subscriptionId → 单调 ordinal（assembler 要求 logicalFrameOrdinal ≥1 且单调）
const sessionsIndexRouteOrdinals = new Map();

function sessionsIndexTopicOf(params) {
  return `sessions-index/${workspaceKeyOf(params)}`;
}

function synthSessionSummariesFor(workspaceId) {
  const live = [...liveSessions.values()].filter((s) => s.workspaceId === workspaceId).map((s) => ({ ...s }));
  if (workspaceId !== WORKSPACE_KEY) return live;
  return [...live, ...SYNTH_SESSIONS.map((s) => ({
    sessionId: s.id,
    workspaceId,
    title: s.title,
    titleSource: "generated",
    phase: s.phase,
    sessionEnded: s.phase !== "running",
    hasBackgroundWork: false,
    // §六.A#6：终局结果小圆点事实（main sessionSummarySchema.lastOutcome:
    // "completed"|"error"|"interrupted" optional）——running 会话无终局，键缺席即诚实。
    ...(s.phase !== "running" ? { lastOutcome: "completed" } : {}),
    lastActivityAt: s.lastActivityAt,
    createdAt: s.createdAt,
  }))];
}

function emitSessionsIndexSnapshotFrame(topic, subscriptionId, delivery = "initial") {
  const subscription = sessionsIndexSubscriptions.get(subscriptionId);
  if (subscription?.topic !== topic) return;
  const routeKey = `${topic}\0${subscriptionId}`;
  const ordinal = (sessionsIndexRouteOrdinals.get(routeKey) ?? 0) + 1;
  sessionsIndexRouteOrdinals.set(routeKey, ordinal);
  const workspaceId = topic.slice("sessions-index/".length);
  const frame = {
    topic,
    subscriptionId,
    // snapshot 帧区间记账：fromSeq=0，toSeq=权威水位（store 快照 apply 取 toSeq）
    fromSeq: 0,
    toSeq: sessionsIndexSeq.get(workspaceId) ?? 0,
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
    deliveryKind: delivery,
    logicalFrameId: "lframe_" + randomUUID().slice(0, 8),
    logicalFrameOrdinal: ordinal,
    topic,
    subscriptionId,
    frame,
  });
  subscription.initialSent = true;
  console.log(`[mock-host] sessions-index snapshot fired: topic=${topic} sub=${subscriptionId} ordinal=${ordinal}`);
}

function emitSessionsIndexDeltaFrame(topic, deltas) {
  const workspaceId = topic.slice("sessions-index/".length);
  const seq = (sessionsIndexSeq.get(workspaceId) ?? 0);
  sessionsIndexSeq.set(workspaceId, seq + deltas.length);
  for (const [subscriptionId, subscription] of sessionsIndexSubscriptions) {
    // ACK 到 initial snapshot 之间发生的变更由快照承接，不能先发 online。
    if (subscription.topic !== topic || !subscription.initialSent) continue;
    const routeKey = topic + "\0" + subscriptionId;
    const ordinal = (sessionsIndexRouteOrdinals.get(routeKey) ?? 0) + 1;
    sessionsIndexRouteOrdinals.set(routeKey, ordinal);
    sessionsIndexFrameEmitter.fire({
      wireVersion: 3, kind: "complete", deliveryKind: "online",
      logicalFrameId: "lframe_" + randomUUID().slice(0, 8),
      logicalFrameOrdinal: ordinal, topic, subscriptionId,
      frame: { topic, subscriptionId, fromSeq: seq, toSeq: seq + deltas.length, sentAt: Date.now(), payload: { kind: "deltas", deltas } },
    });
  }
  console.log(`[bridge] sessions-index delta fired: topic=${topic} n=${deltas.length} seq ${seq}->${seq + deltas.length}`);
}

// ---------- 服务实例（合成数据，仅 dev 点亮用） ----------
// settingService.update 接 #30 隐身开关审计（对拍 36：开/关各落一条，actor=律师；对拍 51 条件对：
// stealth.on/stealth.off 随开关方向二选一落值）。audit 常量在本文件后段初始化，RPC 到达前已就绪。
const settingService = {
  get: async () => loadSetting(),
  update: async (patch) => {
    const before = loadSetting();
    // RE-26 F13 等量：team 段以磁盘现值整体覆盖——设置表单保存冲不掉团队身份（mergeSettingKeepTeam 单源）。
    const s = mergeSettingKeepTeam(before, patch);
    saveSetting(s);
    const wasOn = Boolean(before.stealthMode?.enabled);
    const isOn = Boolean(s.stealthMode?.enabled);
    if (wasOn !== isOn) auditWrite(isOn ? "stealth.on" : "stealth.off", "settings");
    return s;
  },
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

// ══ 【步骤4·#5 冲突查重】检索内核装配（RE-5-冲突查重.md 实现规格 §3.2/§3.3；对拍 2-28）══
// 算法内核=conflictModel.ts 纯模型（桥/UI/自测单一来源）；候选查询/存取在 bridge_store
// （conflict* 系）；⚠过渡态：候选主体挂 MatterLite 案件族（迁移 0013 注），收案（intake）
// 实体未接入前收案检索/送审转案闸（P1 G1-G5）与审批页签（F9-F11 对位面）随 #2 接线，
// 收案形态入口先 fail-closed 显式拒，不伪造零命中。
// ── 【对拍复核缺项·#2 收案/审批实体接线挂点清单（对拍 partial 2026-10-27；r9 更新 2026-10-28）】
//    行为分两层推进：实体无关判定核已落地（r9 件4，conflictModel.ts 单源+合成 E15-E21 覆盖，
//    沿 reviewGateOutcome 先例「核先行、接入即挂不重写」）；实体/审批模块依赖的接线面按下表随 #2 挂：
//    已落核（接线时直接取用）：
//    · B1 审批侧第三套角色标签=conflictModel.APPROVAL_ROLE_LABEL（OPPOSING_PARTY 显「对方」、OTHER 显「其他」）。
//    · E5 审批侧命中方式四分=matchKindOfApproval+APPROVAL_MATCH_KIND_LABEL（含「其他历史匹配」）。
//    · F10 覆盖比对核=conflictQueryCoverage（ok/incomplete/missing 三支；审批页签与 G4 ③取用）。
//    · G2 送审五查核=intakeSubmitGateOutcome（五段次序）+rerunChangedCount（键+严重度+reason 严格比对）。
//    · F7 冻结判定=intakeFrozenForConclusion（PENDING_CONFIRMATION→不可改结论；conclude 事务内同位调）。
//    · G4 转案内容闸核=intakeConvertGateOutcome（八条次序）。
//    · E2 剥 ID 已挂 conflictHitToProtocol 外发面（external=true→IN_PROGRESS_INTAKE targetId 置空；
//      内部比对面保原值防重跑误报）。
//    待 #2 接线（结构依赖收案实体/审批模块，未接入前不预造）：
//    · A3 收案详情「利益冲突检索」卡+空态——收案详情面对位（UI §3.4 面三）；本桥 conflictRun
//      {intakeId} 形态已 fail-closed（见 conflictRun 内显式拒，合成 P15 验证），接线时替换为正式检索。
//    · A4 收案向导提交后自动检索并按命中决定送审（G1）——收案向导提交动作同位挂 conflictRun(intakeId)。
//    · A6 审批弹窗「冲突核查」页签+计数角标——审批面 §3.4 面五；数据面 conflictCheckList 已就绪。
//    · C2 excludeIntakeId 传入端——store.conflictParty* 已带 excludeSubjectId 参数位（缺省 null），
//      收案形态开放时由 conflictRun(intakeId) 传自身 id（防死参数，不预穿）。
//    · C7 在办收案关联客户回退（竞品 algorithm.ts:505 等量位）——候选面②已挂 subject_type='intake'
//      （合成 P18 直播种验证可命中）；回退查询源=收案关联客户（收案实体列随 #2），接入后在
//      收案权威重派处补委托方查询（buildConflictQueries 的 client 参数位现成）。
//    · E2 余项：收案名称/登记人/状态/登记日期四披露字段装配（收案实体列无源，现置缺不伪造）。
//    · E8 收案区/审批侧空态文案——随 A3/A6 面落地。
//    · F7/G2/G4 接线位——conflictConclude 事务内收案状态闸（:1714 注）、收案提交/转案动作同位
//      调 intakeSubmitGateOutcome/intakeConvertGateOutcome；G3 IntakeRevision 快照冻结、G4b 事务闸
//      五段、G5 转案继承复核记录——均随收案状态机表落地。
// 并发口径（对拍 35/I5 等量）：写动作全进单事务（store.withTransaction），事务内重校验
// 最新记录/指纹/命中集后落库——SQLite 单写者串行等量替代竞品 Serializable+advisory 锁，
// 竞态浮出为既有报错文案，不静默丢写。
// F13 动作层闸位（对拍 36）：桥为本地单主体面（无会话/角色域），闸位=requireConflictActor()
// ——本地身份恒在、当前恒放行；多用户面接入时在此同位收紧，拒绝不依赖 UI 隐藏。
// ══ 【步骤4·#5 冲突查重】桥面动作（RE-5-冲突查重.md 实现规格 §3.2/§3.3；对拍 2-28）══
// 算法内核=conflictModel.ts 纯模型（桥/UI/自测单一来源）；候选查询/存取在 bridge_store
// （conflict* 系）；⚠过渡态：候选主体挂 MatterLite 案件族（迁移 0013 注），收案（intake）
// 实体未接入前收案检索/送审转案闸（P1 G1-G5）与审批页签（F9-F11 对位面）随 #2 接线，
// 收案形态入口先 fail-closed 显式拒，不伪造零命中。
// 并发口径（对拍 35/I5 等量）：写动作全进单事务（store.withTransaction），事务内重校验
// 最新记录/指纹/命中集后落库——SQLite 单写者串行等量替代竞品 Serializable+advisory 锁，
// 竞态浮出为既有报错文案，不静默丢写。
// F13 动作层闸位（对拍 36）：桥为本地单主体面（无会话/角色域），闸位=requireConflictActor()
// ——本地身份恒在、当前恒放行；多用户面接入时在此同位收紧，拒绝不依赖 UI 隐藏。
const conflictActor = () => "律师"; // 本地单主体身份；审计 actor 同源
// JSON 文档列安全解析（检索条件 payload；坏 JSON 容错回 null）
function conflictJsonObj(s) {
  try { const v = JSON.parse(s ?? "null"); return v && typeof v === "object" && !Array.isArray(v) ? v : null; }
  catch { return null; }
}
// 候选行 → 命中草稿（E1 字段全集；角色/证件两列都比对，C3）
function conflictHitsFromCandidates(query, candidates, hitType) {
  const hits = [];
  for (const row of candidates) {
    const storedRole = row.role;
    const storedStanding = row.standing ?? null;
    // 名称腿：四级双向匹配分级（C5）
    if (query.name) {
      const m = nameMatchLevel(query.name, row.name);
      if (m) {
        const severity = severityOfNameHit(m.level, query.role, storedRole);
        const draft = {
          hitType, targetType: row.subject_type, targetId: row.subject_id,
          matchedName: row.name, matchedField: "name", matchedValue: query.name,
          matchedRatio: m.ratio, matchLevel: m.level, severity,
          reason: "", storedRole, storedStanding,
        };
        draft.reason = reasonOfHit(draft);
        hits.push(draft);
      }
    }
    // 证件腿：原文或大写归一变体相等（C4）；一致 → 矩阵升 1 封顶 BLOCKING（D5）
    if (query.idNumber) {
      const variants = idVariants(query.idNumber);
      const storedIds = [row.id_number, row.social_code].filter(Boolean);
      if (variants.some((v) => storedIds.includes(v))) {
        const severity = bumpForIdMatch(pickSeverity(query.role, storedRole));
        const draft = {
          hitType, targetType: row.subject_type, targetId: row.subject_id,
          matchedName: row.name, matchedField: "idNumber", matchedValue: query.idNumber,
          matchedRatio: 1, matchLevel: null, severity,
          reason: "", storedRole, storedStanding,
        };
        draft.reason = reasonOfHit(draft);
        hits.push(draft);
      }
    }
  }
  return hits;
}
// 每查询三查（C1/C7）：①历史案件当事人（精确含证件变体→模糊探针 take20）②在办收案当事人
//（过渡态恒空，面已就位）③客户档案→关联案件回溯（软删客户不检、孤立客户不产出命中）。
// 精确/模糊分两条查询防同名大姓挤占窗口（C8）；候选超上限静默截断，不加溢出提示（C10）。
function conflictSearchHits(queries, { excludeMatterId = null } = {}) {
  const FUZZY_TAKE = 20, CLIENT_TAKE = 50;
  const drafts = [];
  for (const query of queries) {
    const probes = buildNameProbes(query.name);
    const variants = idVariants(query.idNumber);
    // ①历史案件当事人
    drafts.push(...conflictHitsFromCandidates(query, store.conflictPartyExactByName("matter", query.name, excludeMatterId), "HISTORICAL_PARTY"));
    drafts.push(...conflictHitsFromCandidates(query, store.conflictPartyExactById("matter", variants, excludeMatterId), "HISTORICAL_PARTY"));
    drafts.push(...conflictHitsFromCandidates(query, store.conflictPartyFuzzyByProbes("matter", probes, FUZZY_TAKE, excludeMatterId), "HISTORICAL_PARTY"));
    // ②在办收案当事人（subject_type='intake'——收案实体未接入恒空；写入面同样未开放，见 conflictPartySet）
    drafts.push(...conflictHitsFromCandidates(query, store.conflictPartyExactByName("intake", query.name, null), "IN_PROGRESS_INTAKE"));
    drafts.push(...conflictHitsFromCandidates(query, store.conflictPartyExactById("intake", variants, null), "IN_PROGRESS_INTAKE"));
    drafts.push(...conflictHitsFromCandidates(query, store.conflictPartyFuzzyByProbes("intake", probes, FUZZY_TAKE, null), "IN_PROGRESS_INTAKE"));
    // ③客户档案（客户即本所委托方档案：storedRole 恒 CLIENT，D2 对手×委托=BLOCKING 由此出）
    const seenClients = new Set();
    const clientCands = [
      ...store.conflictClientExactByName(query.name),
      ...store.conflictClientFuzzyByProbes(probes, CLIENT_TAKE),
      ...store.conflictClientByBlind(store.conflictBlindOf(query.idNumber)),
    ];
    for (const client of clientCands) {
      if (seenClients.has(client.id)) continue;
      seenClients.add(client.id);
      const clientRow = { subject_type: "matter", subject_id: "", role: "CLIENT", standing: null, name: client.name, id_number: client.id_number, social_code: null };
      // 客户档案命中 → 回溯关联案件逐案出命中（孤立客户不产出命中，C1）
      for (const link of store.conflictClientMatters(client.id)) {
        if (excludeMatterId && link.matter_id === excludeMatterId) continue;
        const perMatter = { ...clientRow, subject_id: link.matter_id, brief_case_no: link.brief_case_no, brief_name: link.brief_name, brief_cause: link.brief_cause, brief_court_type: link.brief_court_type, brief_status: link.brief_status };
        drafts.push(...conflictHitsFromCandidates(query, [perMatter], "HISTORICAL_PARTY"));
      }
    }
  }
  return sortHitsDesc(dedupeHits(drafts));
}
// 检索条件服务端权威重派（B8）：案件主体=当事人行+客户档案回退补委托方（委托方缺 Party 行则补）
function conflictDeriveQueriesForMatter(matterId) {
  const partyRows = store.listPartiesBySubject("matter", matterId);
  const parties = partyRows.map((p) => ({ role: p.role, name: p.name, idNumber: p.id_number ?? "" }));
  const linked = partyRows.some((p) => p.role === "CLIENT")
    ? null
    : (store.conflictListClients().find((c) => !c.deleted_at && store.conflictClientMatters(c.id).some((l) => l.matter_id === matterId)) ?? null);
  return buildConflictQueries(linked ? { name: linked.name, idNumber: linked.id_number ?? "" } : null, parties);
}
// 案件指纹（F6 过渡态字段集，见 conflictModel.ts 注）：{queries,cause,courtType}
function conflictMatterFingerprint(matterId, queries) {
  const matter = store.getCase(matterId);
  return sha256(fingerprintPayload({
    queries: queries.map((q) => [q.role, q.name, q.idNumber]),
    cause: matter?.cause ?? "", courtType: matter?.court_type ?? "",
  }));
}
// 命中行落库形状
function conflictHitRec(checkId, h) {
  return {
    id: "chit_" + randomUUID().slice(0, 8), check_id: checkId,
    hit_type: h.hitType, target_type: h.targetType, target_id: h.targetId,
    matched_name: h.matchedName, matched_field: h.matchedField, matched_value: h.matchedValue,
    matched_ratio: h.matchedRatio, match_level: h.matchLevel, severity: h.severity,
    reason: h.reason, stored_role: h.storedRole, stored_standing: h.storedStanding,
  };
}
function conflictHitToProtocol(r, external = false) {
  // 案件最小披露在读取时按当前档案解析（E4/E6；命中行不存 brief 快照，改名/改状态后显当前值）。
  // E2 在办收案命中最小披露（r9 落地段）：外发面（external=true，RPC 返回）剥收案 ID——
  // targetId 置空、无查看收案入口数据，收案内容不因预检/审批开放；披露=命中角色（storedRole/
  // storedStanding）。收案名称/登记人/状态/登记日期四字段无源（收案实体表随 #2），置缺不伪造；
  // 内部面（默认 external=false，当场重跑比对/去重键）保留原 targetId——剥错层会把重跑比对
  // 全数误判为新增命中（G2/H4 失真），故剥 disclosure 层不剥数据层。DB 行 target_id 原值留存。
  const stripIntakeId = external && r.hit_type === "IN_PROGRESS_INTAKE";
  const matter = r.target_type === "matter" && r.target_id ? store.getCase(r.target_id) : null;
  return {
    id: r.id, checkId: r.check_id, hitType: r.hit_type, targetType: r.target_type, targetId: stripIntakeId ? null : r.target_id,
    matchedName: r.matched_name, matchedField: r.matched_field, matchedValue: r.matched_value,
    matchedRatio: r.matched_ratio, matchLevel: r.match_level, severity: r.severity,
    reason: r.reason, storedRole: r.stored_role, storedStanding: r.stored_standing,
    brief: matter ? {
      caseNo: matter.case_no ?? null, name: matter.name ?? null, cause: matter.cause ?? null,
      courtType: matter.court_type ?? null, status: matter.workflow_status ?? null,
    } : null,
  };
}
function conflictCheckToProtocol(r, { withHits = false, external = false } = {}) {
  const payload = conflictJsonObj(r.query_payload_json) ?? {};
  const hits = withHits ? store.conflictListHitsByCheck(r.id) : [];
  const hitCount = withHits ? hits.length : payload.hitCount ?? null;
  // 自动结论判定（F9 等量链）：无人工结论审计 + conclusion=DIFFERENT + 零命中 + note=自动常量
  const manual = audit.hasAudit(["conflict.conclusion.set", "conflict.matter.decision"], r.id);
  const automatic = !manual && r.conclusion === "DIFFERENT" && hitCount === 0
    && (r.note === AUTO_NOTE_FORMAL || r.note === AUTO_NOTE_REVIEW);
  return {
    id: r.id, subjectType: r.subject_type, subjectId: r.subject_id,
    queries: Array.isArray(payload.queries) ? payload.queries : [],
    fingerprint: r.subject_fingerprint,
    conclusion: r.conclusion,
    decidedBy: automatic ? null : r.decided_by,   // 自动结论隐藏结论人（F9）
    decidedAt: automatic ? null : r.decided_at,
    automatic,
    note: r.note, checkedAt: r.checked_at, hitCount,
    hits: hits.map((h) => conflictHitToProtocol(h, external)),
  };
}
function conflictRowsToProtocol(rows, external = false) {
  // 批量版：为每条 check 附命中行（含 brief 列），复用 conflictCheckToProtocol 的自动判定
  return rows.map((r) => {
    const hits = store.conflictListHitsByCheck(r.id);
    const payload = conflictJsonObj(r.query_payload_json) ?? {};
    const manual = audit.hasAudit(["conflict.conclusion.set", "conflict.matter.decision"], r.id);
    const automatic = !manual && r.conclusion === "DIFFERENT" && hits.length === 0
      && (r.note === AUTO_NOTE_FORMAL || r.note === AUTO_NOTE_REVIEW);
    return {
      id: r.id, subjectType: r.subject_type, subjectId: r.subject_id,
      queries: Array.isArray(payload.queries) ? payload.queries : [],
      fingerprint: r.subject_fingerprint, conclusion: r.conclusion,
      decidedBy: automatic ? null : r.decided_by, decidedAt: automatic ? null : r.decided_at,
      automatic, note: r.note, checkedAt: r.checked_at, hitCount: hits.length,
      hits: hits.map((h) => conflictHitToProtocol(h, external)),
    };
  });
}
// F8 对象级授权先行（对拍 24）：主体不存在/不可见先拒绝，不落任何检索记录。
// 本地单主体：可见性=案件存在（多用户面接入时在此按成员可见性收紧）。
function conflictAssertMatterVisible(matterId) {
  if (!matterId || !store.getCase(matterId)) throw new Error("案件不存在或无权访问");
}
// H5 写路径硬门禁（对拍 32；规格 P2「闸挂后继写路径位」）：新增程序/委托合同生效/计费登记类
// 写路径接入时在事务内同位调用本闸——三段闸次序与判定核 reviewGateOutcome 单源（模型层），
// 报错文案自写。事实登记与待办记录类写路径不得调用（H5 明文不阻断）。现 MatterLite 无
// 程序/合同/计费写域：本闸先落位+判定核随合成自测覆盖，对应模块接入即挂不重写。
function assertReviewCurrent(matterId) {
  conflictAssertMatterVisible(matterId);
  const queries = conflictDeriveQueriesForMatter(matterId);
  const latest = store.conflictLatestCheck("matter", matterId);
  const fingerprintCurrent = Boolean(latest && conflictMatterFingerprint(matterId, queries) === latest.subject_fingerprint);
  // 当场重跑仅对最新且未漂移的记录有意义（漂移已在第一段拦截，重跑失无比对基准）
  const newHitCount = latest && fingerprintCurrent
    ? newHitKeys(
        store.conflictListHitsByCheck(latest.id).map((h) => conflictHitToProtocol(h)),
        conflictSearchHits(queries, { excludeMatterId: matterId }),
      ).length
    : 0;
  const outcome = reviewGateOutcome({
    hasRecord: Boolean(latest),
    fingerprintCurrent,
    conclusion: latest?.conclusion ?? null,
    newHitCount,
  });
  if (outcome === "STALE") throw new Error("案件主体或服务范围已变化，需先完成动态冲突复核才能继续办理");
  if (outcome === "NOT_PASSED") throw new Error("本案最新冲突复核结论未通过，暂不能继续办理");
  if (outcome === "NEW_HITS") throw new Error("复核后新出现相关命中，请重新检索并复核后再继续");
}
// 正式/复核检索核心：服务端重派条件→指纹→检索→事务内落 check+hits→（正式零命中自动结论）→审计。
function conflictRunCore({ subjectType, subjectId, queries, excludeMatterId, autoNote }) {
  const now = new Date().toISOString();
  const checkId = "cchk_" + randomUUID().slice(0, 8);
  const hits = conflictSearchHits(queries, { excludeMatterId });
  const fingerprint = subjectId && subjectType === "matter" ? conflictMatterFingerprint(subjectId, queries) : null;
  const auto = !hits.length && subjectType !== "precheck"; // F2：零命中且正式（含案件复核）才自动结论
  store.withTransaction(() => {
    store.conflictInsertCheck({
      id: checkId, subject_type: subjectType, subject_id: subjectId ?? null,
      query_payload_json: JSON.stringify({ queries, hitCount: hits.length }),
      subject_fingerprint: fingerprint, conclusion: auto ? "DIFFERENT" : "PENDING",
      decided_by: null, decided_at: auto ? now : null, note: auto ? autoNote : null, checked_at: now,
    });
    for (const h of hits) store.conflictInsertHit(conflictHitRec(checkId, h));
  });
  return { checkId, hits, auto };
}

const agentService = {
  ...AGENT_EVENTS,
  // sessions-index 帧面（动态事件约定：(arg) => Event）
  onDynamicSessionsIndexFrame: () => sessionsIndexFrameEmitter.event,
  prepareStorage: async () => {},
  getStorageStartupState: async () => null,
  initialize: async () => ({ ok: true, agentVersion: "mock" }),
  // v4 连接握手（agentSessionsIndexTransport.ensureAgentV4ConnectionHandshake；
  // hello 返回形状按 transport.ts helloMessageSchema .strict()——顶层多一个未知键整条握手
  // 失败。§六.A#3：capabilities 只声明已支持键。持久化后订阅仍即回全量 snapshot（含恢复
  // 历史，RE-B1 §3.4⑥）——historyFirst 位依旧不声明：hostCapabilitiesSchema 白名单
  // （aac4755 transport.ts:23）无此键，declared-only 契约下声明即违约；UI 侧消费验证由
  // ci_gate persist 历史对拍 + fast e2e coldSnapshot/recoveryRows 承担。UI 侧 clientHello
  // 的 capabilities 是 strict 的单向声明（host hello 见到 workflowRunDeltas===true 才回带），
  // 桥不声明该位，UI 不会带；桥侧消费入参天然 strip 不校验。
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
  subscribeSessionsIndexV4: async (rawParams) => {
    // §六.A#2：白名单剥键容忍演进，unknown 剥掉不拒帧
    const params = stripUnknownKeys(rawParams, SUBSCRIBE_KNOWN_KEYS, "subscribeSessionsIndexV4");
    const subscriptionId = "sub_" + randomUUID().slice(0, 8);
    const topic = sessionsIndexTopicOf(params);
    sessionsIndexSubscriptions.set(subscriptionId, { topic, initialSent: false });
    setTimeout(() => emitSessionsIndexSnapshotFrame(topic, subscriptionId), 0);
    return { ack: { subscriptionId, mode: "snapshot", logEpoch: MOCK_LOG_EPOCH } };
  },
  resyncSessionsIndexV4: async (rawParams) => {
    const params = stripUnknownKeys(rawParams, RESYNC_KNOWN_KEYS, "resyncSessionsIndexV4");
    const topic = sessionsIndexSubscriptions.get(params?.subscriptionId)?.topic ?? sessionsIndexTopicOf(params);
    if (params?.subscriptionId) {
      setTimeout(() => emitSessionsIndexSnapshotFrame(topic, params.subscriptionId, "recovery"), 0);
    }
    return { ack: { subscriptionId: params?.subscriptionId ?? "", mode: "snapshot", logEpoch: MOCK_LOG_EPOCH } };
  },
  // §六.A#6：v4/sessionsIndex/reconcile 合同面（main transport.ts V4_METHODS 新方法，
  // aac4755 UI 不调用——升版后的兜底查询面）。按明确 ID 查持久事实，不创建/不恢复运行实例；
  // 结果形状按 main sessionsIndexReconcileResultSchema：exists:false 时 deleted 恒 false
  // （查询不动持久态，"snapshot 缺席≠删除"）。
  reconcileSessionsIndexV4: async (rawParams) => {
    const params = stripUnknownKeys(rawParams, new Set(["workspaceId", "sessionIds"]), "reconcileSessionsIndexV4");
    const ids = Array.isArray(params?.sessionIds) ? params.sessionIds : [];
    return {
      sessions: ids.slice(0, 256).map((sessionId) => {
        const s = synthSessionSummariesFor(params.workspaceId).find((x) => x.sessionId === sessionId);
        if (!s) return { sessionId, exists: false, deleted: false };
        return {
          sessionId,
          exists: true,
          deleted: false,
          title: s.title,
          titleSource: s.titleSource,
          createdAt: s.createdAt,
          updatedAt: s.lastActivityAt,
          ...(s.lastOutcome ? { lastOutcome: s.lastOutcome } : {}),
        };
      }),
    };
  },
  unsubscribeSessionsIndexV4: async (params) => {
    const topic = sessionsIndexSubscriptions.get(params?.subscriptionId)?.topic;
    sessionsIndexSubscriptions.delete(params?.subscriptionId);
    if (topic) sessionsIndexRouteOrdinals.delete(`${topic}\0${params.subscriptionId}`);
  },
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
  listPlugins: async () => ({ plugins: [], diagnostics: [] }),
  getPluginReferenceCatalog: async () => ({ refs: [] }),
  // ── 功能 #29 新手引导与产品指引（RE-29 三通道等量：get/complete/guideStatus；G3 强布尔、
  // G4 字面量校验非法抛错；无独立演示导入通道——导入只随 complete 单事务进入，对拍 36 收口）──
  onboardingGet: async () => getOnboardingState(store.db),
  onboardingComplete: async (params) =>
    completeOnboarding(store.db, { demo: params?.demo === true, startGuide: params?.startGuide === true }),
  onboardingGuideStatus: async (params) => setProductGuideStatus(store.db, params?.status),
  // ── 功能 #30 安全审计中心（RE-30 §3.4 桥 API 等量同形）：audit.list 一次往返同返
  // {rows 最近≤200 倒序, chainOk}（徽章数据源，无单独校验通道）；audit.append 等量保留
  // 渲染层任意写入面（§5 决策①：等量=不收窄 action 白名单）。无轮询无推送——打开期间
  // 新写入行到重开面板才可见（对拍 57）。──
  auditList: async (params) => ({ rows: audit.listAudit(params?.limit), chainOk: audit.verifyAuditChain() }),
  auditAppend: async (entry) => { audit.appendAudit(entry); return true; },
  // ── 功能 #31 支持通道（RE-31 §3）：工单/诊断 三线。有 opsApi 配置=自动上传（隐身闸 §3.2，
  // 关→请求不出错误上浮）；无配置=降级形态纯本地（落盘/枚举，不受 #9 约束）。工单/诊断线 fetch
  // 无显式超时无重试（A8 等量；60s 兜底在渲染层，A18 不向桥传取消）。ticket_key 桥侧生成
  // （randomBytes(24) base64url 32 字符），localStorage 桶归渲染层（A3/A7 等量分工）。──
  supportInfoGet: async () => {
    const { opsApi, source } = resolveOpsBase();
    return { opsApi, source, supportDir: supportRootDir(), appVersion: appVersionOf() };
  },
  supportTicketCreate: async (params) => {
    const requester = typeof params?.requester === "string" ? params.requester.trim() : "";
    const subject = typeof params?.subject === "string" ? params.subject.trim() : "";
    const content = typeof params?.content === "string" ? params.content : "";
    if (!requester || !subject) throw new Error("缺少工单称呼（requester）或主题（subject），未提交"); // A12 同构校验（文案自写）
    const ticketKey = typeof params?.ticketKey === "string" && params.ticketKey.trim()
      ? params.ticketKey.trim() : generateTicketKey();
    const { opsApi } = resolveOpsBase();
    if (opsApi) {
      if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：出站通道全断，工单上传未执行。请在设置中关闭隐身模式后重试。");
      const res = await fetch(`${opsApi}/support/tickets`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ requester, subject, content: content || "", ticket_key: ticketKey }), // A6 body 四字段等量
      });
      const text = await res.text().catch(() => "");
      if (!res.ok) throw new Error(`远端 ${res.status}：${text.slice(0, 300) || res.statusText || "无响应体"}`); // A8 红字素材，清洗在渲染层
      let body = null;
      try { body = JSON.parse(text); } catch { /* 非法 JSON 体按 null 回；ticketKey 回显判据失效由渲染层按加固 1 处理 */ }
      const echoed = typeof body?.ticket_key === "string" && body.ticket_key ? body.ticket_key : null;
      return { mode: "remote", ok: true, ticketKey, responseTicketKey: echoed };
    }
    // 降级形态：§3.5 Markdown 落盘（E31 递归建目录/E32 撞名不覆盖/E33 失败含路径上抛）
    const createdAtIso = new Date().toISOString();
    const markdown = buildTicketMarkdown({
      requester, ticketKey, subject, content,
      createdAtIso, appVersion: appVersionOf(), platform: process.platform, arch: process.arch,
    });
    const file = writeTicketFile({ markdown });
    return { mode: "local", ok: true, ticketKey, ...file, content: markdown, createdAt: createdAtIso };
  },
  supportTicketList: async (params) => {
    const { opsApi } = resolveOpsBase();
    if (!opsApi) {
      // E38 降级列表（跨桶全域枚举，有意差异）；localRows 键位与 remote rows 分开，渲染层按 mode 取
      const { rows: localRows, error } = listLocalTickets();
      return { mode: "local", localRows, error };
    }
    if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：出站通道全断，工单列表未拉取。请在设置中关闭隐身模式后重试。");
    const requester = typeof params?.requester === "string" ? params.requester.trim() : "";
    const ticketKey = typeof params?.ticketKey === "string" ? params.ticketKey.trim() : "";
    if (!requester || !ticketKey) throw new Error("缺少工单称呼（requester）或工单密钥（ticket_key），未拉取"); // A10 同构校验（文案自写）
    const res = await fetch(`${opsApi}/support/tickets?requester=${encodeURIComponent(requester)}`, {
      headers: { "x-ticket-key": ticketKey }, // A10 头等量
    });
    const text = await res.text().catch(() => "");
    if (!res.ok) throw new Error(`远端 ${res.status}：${text.slice(0, 300) || res.statusText || "无响应体"}`);
    let rows;
    try { rows = JSON.parse(text); } catch { rows = null; }
    if (!Array.isArray(rows)) throw new Error("响应格式异常：工单列表不是数组"); // A17 渲染层捕获 → 静默空列表仅日志
    return { mode: "remote", ok: true, rows };
  },
  supportDiagnosticsBuild: async () => {
    const { payload } = buildSupportDiagnostics({ license: LICENSE_SHAPE, db: store.db }); // B15 9 键固定键序；B18/B19 等量在模块内
    return { payload, json: JSON.stringify(payload), supportDir: supportRootDir(), appVersion: appVersionOf() };
  },
  supportDiagnosticsUpload: async (params) => {
    const payload = typeof params?.payload === "string" ? params.payload : "";
    if (!payload.trim()) throw new Error("诊断包内容为空，未上传"); // B23 同构校验（文案自写）
    const { opsApi } = resolveOpsBase();
    if (!opsApi) throw new Error("未配置上传目标（opsApi），本机为降级形态：请用「导出诊断包文件」走本地导出。");
    if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：出站通道全断，诊断包上传未执行。请在设置中关闭隐身模式后重试。");
    const requester = typeof params?.requester === "string" ? params.requester.trim() : "";
    const res = await fetch(`${opsApi}/support/diagnostics`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ requester: requester || "unknown", payload }), // B24 body 形状等量
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`远端 ${res.status}：${text.slice(0, 300) || res.statusText || "无响应体"}`);
    }
    return { mode: "remote", ok: true };
  },
  // ── 桥内通用异步任务壳（机制规格-02）：建/查/列/取消/重试/取件。取件走 RPC 同源面（等量于
  // 规格 R5 下载白名单：result_ref 由壳按 `tasks/<本任务id>/<fileName>` 生成，不存"塞什么地址拉什么"
  // 的面）；文件内容 base64 随通道回，v1 只装小产物（大文件走面改残另议）──
  taskCreate: async (params) => taskShell.create(params?.kind, params?.payload, { ref: params?.ref, ttlSeconds: params?.ttlSeconds }),
  taskGet: async (params) => taskShell.get(params?.id),
  taskList: async (params) => taskShell.list(params),
  taskCancel: async (params) => { taskShell.cancel(params?.id); return true; },
  taskRetry: async (params) => taskShell.retry(params?.id),
  taskArtifact: async (params) => {
    const p = taskShell.artifactPath(params?.id);
    return { fileName: p.fileName, contentBase64: readFileSync(p.path).toString("base64") };
  },
  // ── 审批关卡 gate 节点（机制规格-01）：三动作 process/transfer(+force)。乐观锁全域：
  // 变更缺 expectedVersion=VALIDATION；版本对不上=CONFLICT{currentVersion,status}——前端刷新
  // 不自动重试（永不重放人审决定）。错误 code（VALIDATION/CONFLICT/…）随通道异常文本回 ──
  flowGateCreateNode: async (params) => flowGate.createNode(params),
  flowGateGetNode: async (params) => flowGate.getNode(params?.id),
  flowGateListNodes: async (params) => flowGate.listNodes(params),
  flowGateProcess: async (params) => flowGate.process(params?.id, params),
  flowGateTransfer: async (params) => flowGate.transfer(params?.id, params),
  // ── 【#21 安全层】工具策略面（RE-21 增补 §3.2/§3.3/§3.6）：决策（+审计入账，deny 也入账）/
  // 「总是允许」记忆（技能实例+签名双维键，绑 policyVersion；跨技能/跨通道/跨版本不继承）/
  // 会话缓存清空（会话切换）/运行中止在途审批按 deny
  // 解析/决策审计按会话升序查询/宿主闸检视面（路径闸+命令闸——执行入口消费，面板可查）。──
  toolPolicyDecide: async (params) => decideAndAuditToolCall(
    String(params?.conversationId ?? ""), String(params?.runId ?? ""),
    String(params?.toolName ?? ""), params?.args ?? {},
    {
      skillPermissions: params?.skillPermissions,
      skillId: params?.skillId, matterId: params?.matterId,
      workspacePath: params?.workspacePath, enabledSourceIds: params?.enabledSourceIds,
    },
  ),
  toolPolicyRemember: async (params) => {
    const cache = approvalCacheOf(String(params?.conversationId ?? ""));
    // skillId=记忆的技能实例维（§3.6：跨技能/跨通道/跨版本不继承；缺省 ""=匿名作用域）
    return { ok: cache.remember(String(params?.toolName ?? ""), params?.args ?? {}, params?.userDecision, String(params?.skillId ?? "")) };
  },
  toolPolicyReset: async (params) => {
    toolApprovalCaches.delete(String(params?.conversationId ?? "")); // 会话切换清空（记忆按会话隔离）
    return { ok: true };
  },
  toolPolicyAbort: async (params) => {
    const conversationId = String(params?.conversationId ?? "");
    const cache = toolApprovalCaches.get(conversationId);
    if (!cache) return { aborted: 0 };
    const aborted = cache.abortPending(); // 在途审批一律按 deny 解析，不挂死
    for (const p of aborted) {
      store.toolAudits.recordToolAudit({
        conversationId, runId: null, toolName: p.toolName, effect: "deny",
        code: p.code, reason: `运行中止：在途审批按拒绝解析（${p.reason}）`,
        policyVersion: TOOL_POLICY_VERSION, userDecision: "deny", args: p.args,
      });
    }
    return { aborted: aborted.length };
  },
  toolAuditsList: async (params) => {
    const conversationId = String(params?.conversationId ?? "");
    // 会话 id 在=按会话升序全量（RE-21 §2.8 对拍 #35）；缺省=审计中心「工具决策」tab 的
    // 跨会话最近面（≤limit 倒序，默认 200，与 auditList 同口径）。
    return {
      rows: conversationId
        ? store.toolAudits.listToolAudits(conversationId)
        : store.toolAudits.listToolAuditsRecent(params?.limit),
    };
  },
  hostGateCommand: async (params) => gateCommand(String(params?.command ?? ""), {
    shellEnabled: toolSecuritySetting().shellEnabled,
    workspaceRoot: String(params?.workspaceRoot ?? WORKSPACE.path),
  }),
  hostGatePath: async (params) => gateWorkspacePath(
    String(params?.root ?? ""), String(params?.target ?? ""), { delete: params?.delete === true },
  ),
  // 功能 #15：案内文档全文搜（FTS5 trigram；短词/零命中回落 LIKE 子串）。单案作用域，
  // 完成 chunk 才可检索（RE-15 §3；对齐 LegalWork case_system.search 的单案+latest_only+top_k 语义）。
  searchSessionDocuments: async (params) => {
    const workspaceKey = workspaceKeyOf(params);
    const query = typeof params?.query === "string" ? params.query.trim() : "";
    const sessionId = typeof params?.sessionId === "string" ? params.sessionId : "";
    if (!query || !sessionId) return { results: [], mode: "empty" };
    const limit = Math.min(Number(params?.limit) || 8, 50);
    const { hits, mode } = store.searchDocumentChunks(workspaceKey, sessionId, query, limit);
    return {
      mode,
      results: hits.map((h) => ({
        chunkId: String(h.chunk_id), kind: h.kind, sourceLabel: h.source_label,
        text: h.text, createdAt: h.created_at,
      })),
    };
  },
  // ── 功能 #11 Word 红线改稿（施工单-03 任务一）：材料进 → 模型出稿（修订项呈现）→
  // 律师逐条接受/拒绝 → 定稿落盘 workspace/定稿/。记录落桥 SQLite（重启不丢）；隐身 fail-closed。
  redlineRevise: async (params) => {
    if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：出站通道全断，改稿未连接任何模型。请在设置中关闭隐身模式后重试。");
    const workspaceKey = workspaceKeyOf(params);
    const mat = readRedlineMaterial(params?.workspacePath, params?.materialName);
    if (!mat.text.trim()) throw new Error("材料正文为空，无法改稿");
    const instruction = typeof params?.instruction === "string" ? params.instruction.trim().slice(0, 2000) : "";
    const revisionId = "red_" + randomUUID().slice(0, 8);
    const now = Date.now();
    store.upsertRedline({ workspace_key: workspaceKey, revision_id: revisionId, material_name: mat.name,
      instruction, status: "revising", original_text: mat.text, revised_text: "", final_text: null,
      final_path: null, error: null, created_at: now, updated_at: now });
    (async () => {
      try {
        const revisedText = await runRedlineTurn(instruction, mat.text);
        const hunks = buildHunks(diffOps(splitLines(mat.text), splitLines(revisedText)));
        store.putRedlineItems(workspaceKey, revisionId, hunks.map((h, idx) => ({
          item_idx: idx, type: h.type, a_start: h.aStart, a_count: h.aCount,
          b_start: h.bStart, b_count: h.bCount, old_text: h.oldText, new_text: h.newText, decision: "pending",
        })));
        store.upsertRedline({ workspace_key: workspaceKey, revision_id: revisionId, material_name: mat.name,
          instruction, status: "ready", original_text: mat.text, revised_text: revisedText, final_text: null,
          final_path: null, error: null, created_at: now, updated_at: Date.now() });
        console.log("[bridge] redline ready " + revisionId + " items=" + hunks.length);
      } catch (e) {
        store.upsertRedline({ workspace_key: workspaceKey, revision_id: revisionId, material_name: mat.name,
          instruction, status: "failed", original_text: mat.text, revised_text: "", final_text: null,
          final_path: null, error: String(e?.message ?? e), created_at: now, updated_at: Date.now() });
        console.error("[bridge] redline failed:", e?.message ?? e);
      }
    })();
    return { revisionId, status: "revising" };
  },
  redlineGet: async (params) => redlineDetail(workspaceKeyOf(params), String(params?.revisionId ?? "")),
  redlineList: async (params) => {
    const workspaceKey = workspaceKeyOf(params);
    const revisions = store.listRedlines(workspaceKey).map((r) => {
      const items = store.listRedlineItems(workspaceKey, r.revision_id);
      return { revisionId: r.revision_id, materialName: r.material_name, status: r.status,
        itemCount: items.length, decidedCount: items.filter((i) => i.decision !== "pending").length, createdAt: r.created_at };
    });
    return { revisions };
  },
  redlineDecide: async (params) => {
    const workspaceKey = workspaceKeyOf(params);
    const revisionId = String(params?.revisionId ?? "");
    const rec = store.getRedline(workspaceKey, revisionId);
    if (!rec) throw new Error("改稿记录不存在");
    if (rec.status === "finalized") throw new Error("已定稿，不能再改决定（如需重改请新建一轮改稿）");
    if (rec.status !== "ready") throw new Error("改稿尚未完成（" + rec.status + "），暂不能审");
    const decision = params?.decision;
    if (!["accepted", "rejected", "pending"].includes(decision)) throw new Error("非法决定值");
    const idx = Number(params?.itemIdx);
    if (!Number.isInteger(idx)) throw new Error("修订项序号非法");
    store.setRedlineItemDecision(workspaceKey, revisionId, idx, decision);
    const fresh = store.listRedlineItems(workspaceKey, revisionId);
    const finalText = applyRedlineDecisions(rec.original_text, fresh.map((i) => ({
      type: i.type, aStart: i.a_start, aCount: i.a_count, bStart: i.b_start, bCount: i.b_count,
      oldText: i.old_text, newText: i.new_text, decision: i.decision })));
    store.upsertRedline({ ...rec, final_text: finalText, updated_at: Date.now() });
    return redlineDetail(workspaceKey, revisionId);
  },
  redlineFinalize: async (params) => {
    const workspaceKey = workspaceKeyOf(params);
    const revisionId = String(params?.revisionId ?? "");
    const rec = store.getRedline(workspaceKey, revisionId);
    if (!rec) throw new Error("改稿记录不存在");
    if (rec.status === "finalized") return { revisionId, status: "finalized", finalPath: rec.final_path };
    if (rec.status !== "ready") throw new Error("当前状态不能定稿：" + rec.status);
    const items = store.listRedlineItems(workspaceKey, revisionId);
    const pending = items.filter((i) => i.decision === "pending").length;
    if (pending > 0) throw new Error("还有 " + pending + " 条修订未审：逐条接受/拒绝后才能定稿（不静默全收）");
    const base = typeof params?.workspacePath === "string" && params.workspacePath.trim() ? params.workspacePath.trim() : WORKSPACE.path;
    const dir = join(base, "定稿");
    mkdirSync(dir, { recursive: true });
    const stem = rec.material_name.replace(/\.(txt|md|docx)$/i, "");
    const finalPath = join(dir, stem + "-定稿.txt");
    writeFileSync(finalPath, rec.final_text ?? "", "utf-8");
    store.upsertRedline({ ...rec, status: "finalized", final_path: finalPath, updated_at: Date.now() });
    // 功能 #30 对拍 31/32 补齐：定稿落盘（AI 改稿采纳应用为正式文书）落 doc.ai.apply；
    // detail 只落路径与修订计数（改稿正文不进审计）；落盘/写库抛错则不落=业务写成功才入账。
    auditWrite("doc.ai.apply", revisionId, {
      finalPath, decidedCount: items.length - pending, materialName: rec.material_name,
    });
    console.log("[bridge] redline finalized " + revisionId + " -> " + finalPath);
    return { revisionId, status: "finalized", finalPath };
  },
  // ── 【步骤4·案件族底座】MatterLite 桥面（RE-3-案件看板.md 实现规格 §3.2/§3.3/§3.4-3）──
  // （boardDayFireTime/boardQueryLimit 见文件顶部常量区）
  // 轻量三表过渡态：MatterStore 解挂后翻牌真源、轻量表退役（决策台账 2026-10-27 03:35；
  // 迁移 0005_case_board 同注）。桥只做机械 CRUD+强校验；状态推断/提醒引擎/排序桶全为 UI 侧
  // 纯函数（§3.4-1/2），每案抽取态计数随 #6 产物表接入后补（§3.4-1），本层不预做。
  matterList: async () => ({ cases: store.listCases().map(caseToProtocol) }),
  matterCreate: async (params) => {
    const p = params ?? {};
    const cols = normalizeCaseFields(p, { requireName: true });
    const id = "mat_" + randomUUID().slice(0, 8);
    // 通道二挂点（LL F1/F2 等量）：建案动作发生即写时间线事件，与业务写同事务（任一失败整体回滚）
    store.withTransaction(() => {
      store.insertCase({
        id,
        name: cols.name,
        cause: cols.cause ?? "",
        case_no: cols.case_no ?? "",
        court: cols.court ?? "",
        court_type: cols.court_type ?? "法院",
        claim_amount_cents: cols.claim_amount_cents ?? 0,
        plaintiffs_json: cols.plaintiffs_json ?? "[]",
        defendants_json: cols.defendants_json ?? "[]",
        judges_json: cols.judges_json ?? "[]",
        workflow_status: null, // NULL=自动推断（§3.2：推断在 UI 侧纯函数）
        workflow_locked: 0,
        overrides_json: "{}",
        sort_order: null,
        updated_at: new Date().toISOString(),
      });
      store.insertCaseEvent(autoCaseEventRec(id, "建案", `新建案件「${cols.name}」`));
    });
    auditWrite("case.create", id, cols.name);
    return caseToProtocol(store.getCase(id));
  },
  matterUpdate: async (params) => {
    const p = params ?? {};
    const id = String(p.id ?? "");
    if (!store.getCase(id)) throw new Error("案件不存在：" + id.slice(0, 40));
    const cols = normalizeCaseFields(p, { requireName: false });
    // 状态两写同语句（§3.3）：手设=写枚举值+locked=1；恢复自动=写 NULL+locked=0。
    if ("workflowStatus" in p) {
      const v = p.workflowStatus;
      if (v !== null && !MATTER_STATUS_DEFS.includes(v)) {
        throw new Error(`状态须为 ${MATTER_STATUS_DEFS.join("/")} 之一，或 null（恢复自动推断）`);
      }
      cols.workflow_status = v ?? null;
      cols.workflow_locked = v === null ? 0 : 1;
    }
    if ("sortOrder" in p) {
      const v = p.sortOrder;
      if (v !== null && !Number.isInteger(v)) throw new Error("sortOrder 须为整数或 null");
      cols.sort_order = v;
    }
    if (!Object.keys(cols).length) throw new Error("无可更新字段");
    cols.updated_at = new Date().toISOString();
    store.updateCase(id, cols);
    auditWrite("case.update", id, "更新字段 " + Object.keys(cols).filter((k) => k !== "updated_at").join("/"));
    return caseToProtocol(store.getCase(id));
  },
  matterDelete: async (params) => {
    const id = String(params?.id ?? "");
    if (!store.getCase(id)) throw new Error("案件不存在：" + id.slice(0, 40));
    store.clearEventCaseLink(id); // 日程的关联案件置空（0007 增列无 FK，显式清防悬空引用）
    store.deleteCase(id); // 案内待办与时间线事件随 FK 级联清（迁移 0005/0010 ON DELETE CASCADE）
    auditWrite("case.delete", id);
    return { deleted: id };
  },
  // 覆盖层写回（§3.4-3）：只并 calendar_events[sourceKey] 增量，原值不在本表不可被覆盖；
  // 服务端校验 fail-closed：sourceKey 非空/日期格式/非隐藏标题非空/JSON 损坏拒绝（对拍行 33）。
  matterSetOverride: async (params) => {
    const id = String(params?.id ?? "");
    const row = store.getCase(id);
    if (!row) throw new Error("案件不存在：" + id.slice(0, 40));
    let overrides;
    try { overrides = JSON.parse(row.overrides_json || "{}"); } catch { overrides = null; }
    if (!overrides || typeof overrides !== "object" || Array.isArray(overrides)) {
      throw new Error("覆盖层数据损坏，拒绝写入（可整体清除覆盖层后重试）");
    }
    const merged = mergeCalendarOverride(overrides, params?.sourceKey, params?.patch);
    store.updateCase(id, { overrides_json: JSON.stringify(merged), updated_at: new Date().toISOString() });
    return caseToProtocol(store.getCase(id));
  },
  // 覆盖层整体清除（对拍行 89：可整体清除；本表无原值，清除即回空覆盖层）
  matterClearOverrides: async (params) => {
    const id = String(params?.id ?? "");
    if (!store.getCase(id)) throw new Error("案件不存在：" + id.slice(0, 40));
    store.updateCase(id, { overrides_json: "{}", updated_at: new Date().toISOString() });
    return caseToProtocol(store.getCase(id));
  },
  // 案内待办（§3.2 case_board_todos）：打钩只翻 done 位不删行（对拍行 35），撤销清 done_at。
  matterTodoAdd: async (params) => {
    const caseId = String(params?.caseId ?? "");
    if (!store.getCase(caseId)) throw new Error("案件不存在：" + caseId.slice(0, 40));
    const title = typeof params?.title === "string" ? params.title.trim() : "";
    if (!title) throw new Error("待办标题不能为空");
    const id = "cbt_" + randomUUID().slice(0, 8);
    const now = new Date().toISOString();
    const todoRec = { id, case_id: caseId, title, done: 0, done_at: null,
      due_date: optionalDate(params?.dueDate, "待办日期"), created_at: now, updated_at: now };
    // 通道二挂点（LL F1 等量）：任务新增动作发生即写时间线事件，与待办写同事务
    store.withTransaction(() => {
      store.insertTodo(todoRec);
      store.insertCaseEvent(autoCaseEventRec(caseId, "任务登记", `新增任务：${title}`, todoRec.due_date));
    });
    auditWrite("task.add", id, title);
    return todoToProtocol(store.getTodo(id));
  },
  matterTodoList: async (params) => {
    const caseId = typeof params?.caseId === "string" && params.caseId ? params.caseId : null;
    return { todos: store.listTodos(caseId).map(todoToProtocol) };
  },
  matterTodoSetDone: async (params) => {
    const id = String(params?.id ?? "");
    if (!store.getTodo(id)) throw new Error("待办不存在：" + id.slice(0, 40));
    const done = params?.done ? 1 : 0;
    store.updateTodo(id, { done, done_at: done ? new Date().toISOString() : null,
      updated_at: new Date().toISOString() });
    auditWrite("task.toggle", id, done ? "勾选完成" : "撤销完成");
    return todoToProtocol(store.getTodo(id));
  },
  matterTodoDelete: async (params) => {
    const id = String(params?.id ?? "");
    if (!store.getTodo(id)) throw new Error("待办不存在：" + id.slice(0, 40));
    store.deleteTodo(id);
    auditWrite("task.remove", id);
    return { deleted: id };
  },
  // ── 【步骤4·#3 看板日历面】日程（RE-3 对拍行 80/81/83/85 字段面：kind/地点/起止时刻/关联案件/
  // 出行项/提醒开关+提前分钟）──
  // 桥存诚实值：起止缺省不在桥面补造（10:00-11:00 是 UI 对话框的展示默认，对拍行 80）；
  // 未带时刻=date-only 行，提醒引擎按当日 09:00（dayFireTime）归一开火（§3.4-5）。
  matterEventAdd: async (params) => {
    const p = params ?? {};
    const cols = normalizeEventFields(p, { requireTitle: true });
    if (cols.case_id && !store.getCase(cols.case_id)) {
      throw new Error("关联案件不存在：" + cols.case_id.slice(0, 40));
    }
    if (cols.start_at && cols.end_at && cols.end_at <= cols.start_at) {
      throw new Error("结束时刻须晚于开始时刻");
    }
    const id = "cbe_" + randomUUID().slice(0, 8);
    // 通道二挂点（LL F1 等量）：案绑日程的开庭/期限登记动作发生即写时间线事件，同事务提交；
    // 未绑案件的独立日程不产时间线事件（无 matter 归属）。标题=服务端办案语言短句（LL F5 等量）。
    store.withTransaction(() => {
      store.insertEvent({ id, date: cols.date, title: cols.title, note: cols.note ?? null,
        case_id: cols.case_id ?? null, kind: cols.kind ?? BOARD_DEFAULT_KIND,
        location: cols.location ?? "", start_at: cols.start_at ?? null, end_at: cols.end_at ?? null,
        trip: cols.trip ?? "",
        remind: cols.remind ?? 0, remind_minutes: cols.remind_minutes ?? BOARD_DEFAULT_LEAD_MINUTES,
        created_at: new Date().toISOString() });
      if (cols.case_id && cols.kind === "hearing") {
        const where = cols.location ? `（${cols.location}）` : "";
        store.insertCaseEvent(autoCaseEventRec(cols.case_id, "开庭排期", `排期开庭：${cols.title}${where}`, cols.date));
      } else if (cols.case_id && cols.kind === "deadline") {
        store.insertCaseEvent(autoCaseEventRec(cols.case_id, "期限登记", `登记期限：${cols.title}`, cols.date));
      }
    });
    auditWrite("schedule.create", id, cols.title);
    return eventToProtocol(store.getEvent(id));
  },
  // dayFireTime=§3.4-5 date-only 行归一开火时刻（桥常量，BRIDGE_BOARD_DAY_FIRE_TIME 可配）
  matterEventList: async () => ({ events: store.listEvents().map(eventToProtocol), dayFireTime: boardDayFireTime() }),
  matterEventUpdate: async (params) => {
    const p = params ?? {};
    const id = String(p.id ?? "");
    const row = store.getEvent(id);
    if (!row) throw new Error("日程不存在：" + id.slice(0, 40));
    const cols = normalizeEventFields(p, { requireTitle: false });
    if (cols.case_id && !store.getCase(cols.case_id)) {
      throw new Error("关联案件不存在：" + cols.case_id.slice(0, 40));
    }
    // 起止时刻跨语句一致性：与库中现值合并后校验（fail-closed，防拆成两次更新造出 end<=start）
    const effStart = cols.start_at !== undefined ? cols.start_at : row.start_at ?? null;
    const effEnd = cols.end_at !== undefined ? cols.end_at : row.end_at ?? null;
    if (effStart && effEnd && effEnd <= effStart) throw new Error("结束时刻须晚于开始时刻");
    if (!Object.keys(cols).length) throw new Error("无可更新字段");
    store.updateEvent(id, cols);
    auditWrite("schedule.update", id, cols.title ?? row.title);
    return eventToProtocol(store.getEvent(id));
  },
  matterEventDelete: async (params) => {
    const id = String(params?.id ?? "");
    if (!store.getEvent(id)) throw new Error("日程不存在：" + id.slice(0, 40));
    store.deleteEvent(id);
    auditWrite("schedule.delete", id);
    return { deleted: id };
  },
  // ── agent 可读日程/任务面（对拍行 86；LX mcp-schedule list_schedule/list_tasks 只读查询等量：
  // 日期区间/案件过滤/limit 1..50（默认 20），日程按 date+start_at 升序、任务按 done ASC+due ASC）──
  // 只读：不触任何写路径；caseId 不做存在性校验（读面按过滤语义返回空，不伪造错误）。
  matterScheduleQuery: async (params) => {
    const p = params ?? {};
    const from = p.from === undefined || p.from === null || p.from === "" ? null : requiredDate(p.from, "from");
    const to = p.to === undefined || p.to === null || p.to === "" ? null : requiredDate(p.to, "to");
    const caseId = typeof p.caseId === "string" && p.caseId.trim() ? p.caseId.trim() : null;
    return { events: store.listEventsQuery({ from, to, caseId, limit: boardQueryLimit(p.limit) }).map(eventToProtocol) };
  },
  matterTaskQuery: async (params) => {
    const p = params ?? {};
    const caseId = typeof p.caseId === "string" && p.caseId.trim() ? p.caseId.trim() : null;
    const done = p.done === undefined || p.done === null ? null : Boolean(p.done);
    return { tasks: store.listTasksQuery({ caseId, done, limit: boardQueryLimit(p.limit) }).map(todoToProtocol) };
  },
  conflictRun: async (params) => {
    const p = params ?? {};
    conflictActor();
    // 收案形态：实体未接入先显式拒（P1 随 #2 接线，不伪造零命中）
    if (p.intakeId) throw new Error("收案实体尚未接入桥面，收案正式检索随收案模块接入后开放");
    if (p.matterId) {
      // 案件主体形态（H3 复核检索同核）：对象级可见先行（F8）；条件服务端重派（B8）+排除本案（C2）
      const matterId = String(p.matterId);
      conflictAssertMatterVisible(matterId);
      const queries = conflictDeriveQueriesForMatter(matterId);
      if (!queries.length) throw new Error("请先登记本案当事人，再运行冲突检索");
      const { checkId, hits, auto } = conflictRunCore({
        subjectType: "matter", subjectId: matterId, queries, excludeMatterId: matterId, autoNote: AUTO_NOTE_REVIEW,
      });
      auditWrite("conflict.matter.run", matterId, { checkId, hitCount: hits.length, autoConclusion: auto });
      const rec = conflictCheckToProtocol(store.conflictGetCheck(checkId), { withHits: true, external: true });
      return { check: rec };
    }
    // 工作区预检形态（F2 不带主体）：入参即条件（角色可省默认对方）；恒 PENDING、不可下结论
    const { queries, error } = normalizePrecheckQueries(p.queries);
    if (error) throw new Error(error);
    const { checkId, hits } = conflictRunCore({ subjectType: "precheck", subjectId: null, queries, excludeMatterId: null, autoNote: null });
    auditWrite("conflict.check.run", checkId, { kind: "precheck", hitCount: hits.length, autoConclusion: false });
    const rec = conflictCheckToProtocol(store.conflictGetCheck(checkId), { withHits: true, external: true });
    return { check: rec };
  },
  conflictConclude: async (params) => {
    const p = params ?? {};
    const actor = conflictActor();
    const checkId = String(p.checkId ?? "");
    const conclusion = String(p.conclusion ?? "");
    if (!CONCLUSIONS.includes(conclusion)) throw new Error(`结论须为四态之一（实收 ${JSON.stringify(p.conclusion ?? null)}）`);
    const note = p.note === undefined || p.note === null ? "" : String(p.note).trim();
    if ([...note].length > 500) throw new Error("备注不能超过 500 字");
    // I5 并发口径：事务内重校验最新/指纹/高风险备注后落库
    return store.withTransaction(() => {
      const check = store.conflictGetCheck(checkId);
      if (!check) throw new Error("检索记录不存在：" + checkId.slice(0, 40));
      if (check.subject_type === "precheck") throw new Error("预检记录仅供了解情况，不出结论；正式结论请在案件冲突复核中给出");
      if (!check.subject_id) throw new Error("检索记录缺少主体，无法下结论");
      const latest = store.conflictLatestCheck(check.subject_type, check.subject_id);
      if (!latest || latest.id !== check.id) throw new Error("检索已有更新记录，只能对最新一次检索下结论");
      // F7 送审冻结：收案在 PENDING_CONFIRMATION（待审批）期间不可改结论，须先撤回——
      // 闸位随 #2 收案状态机接线（现挂点清单见本文件 #5 头注）；precheck 已在上方拒、matter 无冻结态。
      // F6 指纹失效：按当前主体状态重算比对
      const queries = conflictDeriveQueriesForMatter(check.subject_id);
      if (conflictMatterFingerprint(check.subject_id, queries) !== check.subject_fingerprint) {
        throw new Error("主体或范围已变化，该检索已失效，请重新检索");
      }
      const hits = store.conflictListHitsByCheck(check.id);
      // F5：有高风险/阻塞命中时 DIFFERENT 必填备注（前端提示恒在+服务端兜底恒生效）
      if (conclusion === "DIFFERENT" && hasHighOrBlocking(hits) && !note) {
        throw new Error("存在高风险或阻塞命中，须在备注中写明排除理由或书面同意留痕");
      }
      store.conflictUpdateCheckConclusion(check.id, {
        conclusion, decided_by: actor, decided_at: new Date().toISOString(), note: note || null,
      });
      auditWrite("conflict.conclusion.set", check.id, { conclusion, subjectType: check.subject_type, subjectId: check.subject_id });
      return { check: conflictCheckToProtocol(store.conflictGetCheck(check.id), { withHits: true, external: true }) };
    });
  },
  conflictCheckList: async (params) => {
    const p = params ?? {};
    const subjectType = p.subjectType === "matter" || p.subjectType === "intake" || p.subjectType === "precheck"
      ? p.subjectType : null;
    // subjectId 缺省=该类型全量；subjectType 缺省=全局；precheck 显式传 null=所有预检行
    const rows = store.conflictListChecksBySubject(subjectType, p.subjectId);
    return { checks: conflictRowsToProtocol(rows, true) };
  },
  // H1 需复核判定：无复核记录 / 指纹漂移 / 最新结论≠DIFFERENT（三者任一即 needsReview）
  conflictReviewState: async (params) => {
    const matterId = String(params?.matterId ?? "");
    conflictAssertMatterVisible(matterId);
    const queries = conflictDeriveQueriesForMatter(matterId);
    const fingerprint = conflictMatterFingerprint(matterId, queries);
    const latest = store.conflictLatestCheck("matter", matterId);
    const noRecord = !latest;
    const stale = Boolean(latest && latest.subject_fingerprint !== fingerprint);
    const notPassed = Boolean(latest && latest.conclusion !== "DIFFERENT");
    const parties = store.listPartiesBySubject("matter", matterId).map((r) => ({
      id: r.id, role: r.role, standing: r.standing, name: r.name, idNumber: r.id_number ?? "", socialCode: r.social_code ?? "",
    }));
    const history = conflictRowsToProtocol(store.conflictListChecksBySubject("matter", matterId), true);
    return {
      matterId, needsReview: noRecord || stale || notPassed,
      reasons: [
        ...(noRecord ? ["尚无复核记录"] : []),
        ...(stale ? ["主体或范围已变化"] : []),
        ...(notPassed ? ["最新结论未通过"] : []),
      ],
      parties, fingerprint, history,
    };
  },
  conflictPartySet: async (params) => {
    const p = params ?? {};
    const subjectType = p.subjectType === "matter" ? "matter" : null;
    if (!subjectType) throw new Error("subjectType 须为 matter（intake 实体未接入，随收案模块开放）");
    const subjectId = String(p.subjectId ?? "");
    conflictAssertMatterVisible(subjectId);
    if (!Array.isArray(p.parties)) throw new Error("parties 须为数组");
    const now = new Date().toISOString();
    const rows = p.parties.map((raw) => {
      const role = String(raw?.role ?? "").trim();
      if (!ROLES.includes(role)) throw new Error(`当事人角色不在值域内（实收 ${JSON.stringify(raw?.role ?? null)}）`);
      const name = String(raw?.name ?? "").trim();
      if (!name) throw new Error("当事人名称不能为空");
      if ([...name].length > 120) throw new Error("当事人名称不能超过 120 字");
      const idNumber = normalizeIdNumber(String(raw?.idNumber ?? ""));
      if (idNumber.length > 50) throw new Error("证件号不能超过 50 字符");
      const standing = raw?.standing === undefined || raw?.standing === null || String(raw.standing).trim() === ""
        ? null : String(raw.standing).trim().slice(0, 40);
      const socialCode = raw?.socialCode === undefined || raw?.socialCode === null || String(raw.socialCode).trim() === ""
        ? null : normalizeIdNumber(String(raw.socialCode)).slice(0, 50);
      return {
        id: "pt_" + randomUUID().slice(0, 8), subject_type: subjectType, subject_id: subjectId,
        role, standing, name, id_number: idNumber || null, social_code: socialCode, created_at: now,
      };
    });
    store.withTransaction(() => {
      store.deletePartiesBySubject(subjectType, subjectId);
      for (const r of rows) store.insertParty(r);
    });
    auditWrite("conflict.party.set", subjectId, { count: rows.length });
    return { parties: store.listPartiesBySubject(subjectType, subjectId).map((r) => ({
      id: r.id, role: r.role, standing: r.standing, name: r.name, idNumber: r.id_number ?? "", socialCode: r.social_code ?? "",
    })) };
  },
  conflictPartyList: async (params) => {
    const p = params ?? {};
    const subjectType = p.subjectType === "intake" ? "intake" : "matter";
    const subjectId = String(p.subjectId ?? "");
    return { parties: store.listPartiesBySubject(subjectType, subjectId).map((r) => ({
      id: r.id, role: r.role, standing: r.standing, name: r.name, idNumber: r.id_number ?? "", socialCode: r.social_code ?? "",
    })) };
  },
  conflictClientUpsert: async (params) => {
    const p = params ?? {};
    conflictActor();
    const name = String(p.name ?? "").trim();
    if (!name) throw new Error("客户名称不能为空");
    if ([...name].length > 120) throw new Error("客户名称不能超过 120 字");
    const idNumber = normalizeIdNumber(String(p.idNumber ?? ""));
    if (idNumber.length > 50) throw new Error("证件号不能超过 50 字符");
    const matterIds = Array.isArray(p.matterIds) ? p.matterIds.map(String) : [];
    for (const m of matterIds) {
      if (!store.getCase(m)) throw new Error("关联案件不存在：" + m.slice(0, 40));
    }
    const id = typeof p.id === "string" && p.id ? p.id : "ccl_" + randomUUID().slice(0, 8);
    const prev = store.conflictGetClient(id);
    const rec = {
      id, name, id_number: idNumber || null,
      id_blind: idNumber ? store.conflictBlindOf(idNumber) : null,
      deleted_at: prev?.deleted_at ?? null,
      created_at: prev?.created_at ?? new Date().toISOString(),
    };
    store.conflictUpsertClient(rec);
    store.conflictSetClientMatters(id, matterIds);
    auditWrite("conflict.client.upsert", id, name);
    // 盲索引密文不回传（密文只落库；列表面同样不带）
    return { client: { id, name, idNumber: rec.id_number, deleted: Boolean(rec.deleted_at), matterIds } };
  },
  conflictClientDelete: async (params) => {
    const id = String(params?.id ?? "");
    const rec = store.conflictGetClient(id);
    if (!rec) throw new Error("客户档案不存在：" + id.slice(0, 40));
    // 软删（C1：软删客户不入检；历史检索记录不受影响）
    store.conflictUpsertClient({ ...rec, deleted_at: new Date().toISOString() });
    auditWrite("conflict.client.delete", id, rec.name);
    return { deleted: id };
  },
  conflictClientList: async () => ({
    clients: store.conflictListClients().map((r) => ({
      id: r.id, name: r.name, idNumber: r.id_number ?? "", deleted: Boolean(r.deleted_at),
      matterIds: store.conflictClientMatters(r.id).map((l) => l.matter_id),
    })),
  }),
  // H3 案件复核检索（与 conflictRun matter 形态同核，独立命名面供复核卡直接驱动）
  conflictMatterRun: async (params) => {
    const matterId = String(params?.matterId ?? "");
    conflictAssertMatterVisible(matterId);
    const queries = conflictDeriveQueriesForMatter(matterId);
    if (!queries.length) throw new Error("请先登记本案当事人，再运行冲突检索");
    const { checkId, hits, auto } = conflictRunCore({
      subjectType: "matter", subjectId: matterId, queries, excludeMatterId: matterId, autoNote: AUTO_NOTE_REVIEW,
    });
    auditWrite("conflict.matter.run", matterId, { checkId, hitCount: hits.length, autoConclusion: auto });
    return { check: conflictCheckToProtocol(store.conflictGetCheck(checkId), { withHits: true, external: true }) };
  },
  // H4 复核结论：理由必填；仅最新+指纹相符；当场重跑发现新增命中→拦
  conflictMatterDecide: async (params) => {
    const p = params ?? {};
    const actor = conflictActor();
    const matterId = String(p.matterId ?? "");
    conflictAssertMatterVisible(matterId);
    const checkId = String(p.checkId ?? "");
    const conclusion = String(p.conclusion ?? "");
    if (!CONCLUSIONS.includes(conclusion)) throw new Error(`结论须为四态之一（实收 ${JSON.stringify(p.conclusion ?? null)}）`);
    const note = p.note === undefined || p.note === null ? "" : String(p.note).trim();
    if ([...note].length > 500) throw new Error("备注不能超过 500 字");
    if (!note) throw new Error("复核结论必须填写理由及处理措施");
    return store.withTransaction(() => {
      const check = store.conflictGetCheck(checkId);
      if (!check || check.subject_type !== "matter" || check.subject_id !== matterId) {
        throw new Error("复核记录不存在或不属于本案");
      }
      const latest = store.conflictLatestCheck("matter", matterId);
      if (!latest || latest.id !== check.id) throw new Error("复核已有更新记录，只能对最新一次复核下结论");
      const queries = conflictDeriveQueriesForMatter(matterId);
      if (conflictMatterFingerprint(matterId, queries) !== check.subject_fingerprint) {
        throw new Error("主体或范围已变化，该复核已失效，请重新检索");
      }
      // 当场重跑：新增命中（键集合差异）→ 重新检索复核
      const recorded = store.conflictListHitsByCheck(check.id).map((h) => conflictHitToProtocol(h));
      const fresh = conflictSearchHits(queries, { excludeMatterId: matterId });
      const newKeys = newHitKeys(recorded, fresh);
      if (newKeys.length) throw new Error("检索后发现新增命中，请重新检索复核");
      store.conflictUpdateCheckConclusion(check.id, {
        conclusion, decided_by: actor, decided_at: new Date().toISOString(), note,
      });
      auditWrite("conflict.matter.decision", matterId, { checkId: check.id, conclusion });
      return { check: conflictCheckToProtocol(store.conflictGetCheck(check.id), { withHits: true, external: true }) };
    });
  },
  // ══ #5 冲突查重桥面结束 ══
  // ── 【步骤4·#4 案件时间线】CaseEvent 桥面（RE-4-案件时间线.md 实现规格 §3；装配器见模块层
  // autoCaseEventRec/caseEventToProtocol/todayStrOf）──
  // 唯一写入口（对拍 48）：matterId 须存在；eventType 闭集（CB 14 ∪ auto 21）；date 可选须日历日。
  // 可选富字段（expiresAt/dateLabel/status/importance/phase/side/sourceRefs/payload）：供保全登记
  // （expires_at 按标的年限）等暂无既有桥动作的业务经本入口承接（对拍 47 缺口注记：材料上传为
  // 文件直写、无案绑上传 RPC，属 #6 域；既有可挂集合=建案/开庭排期/期限登记/任务登记四动作）。
  caseEventRecord: async (params) => {
    const p = params ?? {};
    const matterId = String(p.matterId ?? "");
    if (!store.getCase(matterId)) throw new Error("案件不存在：" + matterId.slice(0, 40));
    const eventType = typeof p.eventType === "string" ? p.eventType.trim() : "";
    if (!eventType) throw new Error("事件类型不能为空");
    if (!RECORDABLE_EVENT_TYPES.has(eventType)) {
      throw new Error(`事件类型须在值域内（CB 白名单/auto 枚举，实收 ${JSON.stringify(p.eventType)}）`);
    }
    const note = p.note === undefined || p.note === null ? null : String(p.note);
    let date = null;
    if (p.date !== undefined && p.date !== null && p.date !== "") {
      if (!isCalendarDate(p.date)) throw new Error("日期须为 YYYY-MM-DD 日历日（实收 " + JSON.stringify(p.date) + "）");
      date = p.date;
    }
    let expiresAt = null;
    if (p.expiresAt !== undefined && p.expiresAt !== null && p.expiresAt !== "") {
      if (!isCalendarDate(p.expiresAt)) throw new Error("到期日须为 YYYY-MM-DD 日历日（实收 " + JSON.stringify(p.expiresAt) + "）");
      expiresAt = p.expiresAt;
    }
    const rec = {
      ...autoCaseEventRec(matterId, eventType, note, date),
      date_label: typeof p.dateLabel === "string" && p.dateLabel.trim() ? p.dateLabel.trim().slice(0, 80) : null,
      expires_at: expiresAt,
      status: normalizeStatus(p.status),
      importance: normalizeImportance(p.importance),
      phase: typeof p.phase === "string" && p.phase.trim() ? p.phase.trim().slice(0, 40) : null,
      side: typeof p.side === "string" && p.side.trim() ? p.side.trim().slice(0, 40) : null,
      source_refs_json: JSON.stringify(sanitizeSourceRefs(p.sourceRefs)),
      payload_json: (() => { const pl = sanitizePayload(p.payload); return pl ? JSON.stringify(pl) : null; })(),
    };
    store.insertCaseEvent(rec);
    auditWrite("timeline.record", rec.event_id, eventType);
    return caseEventToProtocol(store.getCaseEvent(rec.event_id));
  },
  // 读取契约（对拍 50/51）：viewer=customer 或未知角色 → 查询层强制叠 FACT_EVENT_TYPES 白名单
  // （可见性过滤不靠前端隐藏）；feed=倒序 LIMIT 50；full=全量读出后走 C3 确定性排序升序。
  caseEventList: async (params) => {
    const p = params ?? {};
    const matterId = String(p.matterId ?? "");
    if (!matterId) throw new Error("matterId 不能为空");
    const mode = p.mode === "feed" ? "feed" : "full";
    const viewer = typeof p.viewer === "string" && p.viewer.trim() ? p.viewer.trim() : "internal";
    const factOnly = viewer !== "internal"; // 未知 viewer 一律按最严（fail-closed）
    if (mode === "feed") {
      const rows = store.listCaseEventsFeed(matterId, factOnly ? [...FACT_EVENT_TYPES] : null, 50);
      return { events: rows.map(caseEventToProtocol), viewer, mode };
    }
    const rows = store.listCaseEventsByMatter(matterId).map(caseEventToProtocol);
    const visible = factOnly ? rows.filter((r) => FACT_EVENT_TYPES.includes(r.eventType)) : rows;
    return { events: sortCaseEventsFull(visible), viewer, mode };
  },
  // ── 通道一：LLM 全局抽取（CB 线，对拍 10-17）。语料=workspace/materials 文本材料（.txt/.md，
  // 用户主动排除不进语料也不算缺口）；无可用材料→停在空态不调模型（空语料显式报错，对拍 10）；
  // 语料不完整（非文本/空文本/读取失败）出警告；确定性后处理+COALESCE 合并（对拍 33）全在
  // 纯模型函数（parseExtractionOutput/postprocessExtracted/planCaseEventMerge），本面只装配。
  caseEventExtract: async (params) => {
    const p = params ?? {};
    const matterId = String(p.matterId ?? "");
    if (!store.getCase(matterId)) throw new Error("案件不存在：" + matterId.slice(0, 40));
    const wsPath = typeof p.workspacePath === "string" && p.workspacePath.trim() ? p.workspacePath.trim() : WORKSPACE.path;
    const ignored = Array.isArray(p.ignoredMaterials) ? p.ignoredMaterials.map((n) => String(n)) : [];
    const dir = materialsDirOf(wsPath);
    let fileNames = [];
    try {
      fileNames = readdirSync(dir, { withFileTypes: true }).filter((e) => e.isFile()).map((e) => e.name);
    } catch {
      throw new Error("材料目录不可读（按空语料处理，停在不调模型）：" + dir);
    }
    const textNames = fileNames.filter((n) => MATERIALS_TEXT_EXT.has(extname(n).toLowerCase()));
    const nonTextCount = fileNames.length - textNames.length;
    const warnings = [];
    if (nonTextCount > 0) warnings.push(`${nonTextCount} 份非文本材料未进语料（当前仅收 .txt/.md 文本）`);
    const corpus = [];
    for (const name of textNames) {
      if (ignored.includes(name)) continue; // 用户主动排除：不进语料也不算缺口（对拍 10）
      try {
        const m = readMaterialText(wsPath, name);
        if (!m.text.trim()) { warnings.push(`材料《${name}》正文为空，未进语料`); continue; }
        const hintInfo = docHintOf(name);
        corpus.push({ name, text: m.text, hint: hintInfo.hint, addNodes: hintInfo.addNodes });
      } catch (e) {
        warnings.push(`材料《${name}》读取失败：${String(e?.message ?? e).slice(0, 80)}`);
      }
    }
    if (!corpus.length) {
      throw new Error("语料为空：无可用文本材料，停在空态不调模型" + (warnings.length ? "（" + warnings.join("；") + "）" : ""));
    }
    const raw = await runTimelineExtractTurn(assembleExtractionPrompt(corpus, todayStrOf()));
    const items = parseExtractionOutput(raw); // 不可解析→抛错（状态机失败态+重试）
    const { rows, warnings: postWarnings } = postprocessExtracted(items);
    const existing = store.listCaseEventsByMatter(matterId).map(caseEventToProtocol);
    const plan = planCaseEventMerge(existing, rows, new Date().toISOString());
    store.withTransaction(() => {
      for (const ins of plan.inserts) store.insertCaseEvent(extractedCaseEventRec(matterId, ins));
      for (const upd of plan.updates) store.updateCaseEvent(upd.eventId, upd.cols);
    });
    auditWrite("timeline.extract", matterId, `新增 ${plan.inserts.length}/更新 ${plan.updates.length}/保留 ${plan.keptCount}`);
    return {
      inserted: plan.inserts.length, updated: plan.updates.length, kept: plan.keptCount,
      total: store.listCaseEventsByMatter(matterId).length,
      corpus: corpus.map((c) => c.name), ignoredCount: ignored.length,
      warnings: [...warnings, ...postWarnings],
    };
  },
  // ── 编辑流（对拍 30-33）：llm_extract/user 行字段覆盖（provenance=user+locked_fields+
  //    orig 原值快照）；auto 行不可编辑字段值（只能隐藏）；校验/快照/恢复全在纯模型函数。──
  caseEventEdit: async (params) => {
    const p = params ?? {};
    const row = store.getCaseEvent(String(p.eventId ?? ""));
    if (!row || row.matter_id !== String(p.matterId ?? "")) throw new Error("时间线节点不存在");
    const { cols, editedFields } = applyCaseEventEdit(caseEventToProtocol(row),
      { eventType: p.eventType, date: p.date, note: p.note }, new Date().toISOString());
    store.updateCaseEvent(row.event_id, cols);
    auditWrite("timeline.edit", row.event_id, "覆盖 " + editedFields.join("/"));
    return caseEventToProtocol(store.getCaseEvent(row.event_id));
  },
  caseEventEditRestore: async (params) => {
    const p = params ?? {};
    const row = store.getCaseEvent(String(p.eventId ?? ""));
    if (!row || row.matter_id !== String(p.matterId ?? "")) throw new Error("时间线节点不存在");
    const field = String(p.field ?? "");
    if (!EDITABLE_FIELDS.includes(field)) throw new Error("字段不可恢复：" + field.slice(0, 20));
    const { cols } = restoreCaseEventField(caseEventToProtocol(row), field, new Date().toISOString());
    store.updateCaseEvent(row.event_id, cols);
    auditWrite("timeline.restore", row.event_id, "恢复 " + field);
    return caseEventToProtocol(store.getCaseEvent(row.event_id));
  },
  // 软删（D4：只删显示不删库；auto 行也可隐藏）与还原 chips（D5/D5a：空态下也照常渲染）
  caseEventSoftDelete: async (params) => {
    const p = params ?? {};
    const row = store.getCaseEvent(String(p.eventId ?? ""));
    if (!row || row.matter_id !== String(p.matterId ?? "")) throw new Error("时间线节点不存在");
    store.updateCaseEvent(row.event_id, { deleted: 1, updated_at: new Date().toISOString() });
    auditWrite("timeline.hide", row.event_id, row.origin);
    return caseEventToProtocol(store.getCaseEvent(row.event_id));
  },
  caseEventRestore: async (params) => {
    const p = params ?? {};
    const row = store.getCaseEvent(String(p.eventId ?? ""));
    if (!row || row.matter_id !== String(p.matterId ?? "")) throw new Error("时间线节点不存在");
    store.updateCaseEvent(row.event_id, { deleted: 0, updated_at: new Date().toISOString() });
    auditWrite("timeline.unhide", row.event_id, row.origin);
    return caseEventToProtocol(store.getCaseEvent(row.event_id));
  },
  caseEventDeletedList: async (params) => {
    const matterId = String(params?.matterId ?? "");
    if (!matterId) throw new Error("matterId 不能为空");
    return { events: store.listDeletedCaseEvents(matterId).map(caseEventToProtocol) };
  },
  // 看板联动源（RE-3 对拍 84 翻牌：案件阶段节点日期化的时间线数据源；跨案全量只读）
  caseEventAllList: async () => ({ events: store.listCaseEventsAll().map(caseEventToProtocol) }),
  // ── 工作汇报「办案时间轴」节导出（对拍 35 = CB C12 等量，2026-10-28 补齐件）：服务端以库内
  // 现值重算（full 口径=覆盖应用+软删滤+C3 排序），行结构纯模型单源；docx 走 #10 零依赖装配
  // （buildCaseReportDocx，日期 run 加粗），与 researchExportWord 同形返回 base64+文件名。
  caseEventReportExport: async (params) => {
    const matterId = String(params?.matterId ?? "");
    const matter = matterId ? store.getCase(matterId) : null;
    if (!matter) throw new Error("案件不存在：" + matterId.slice(0, 40));
    const rows = sortCaseEventsFull(store.listCaseEventsByMatter(matterId).map(caseEventToProtocol));
    const report = buildCaseTimelineReportLines(rows);
    const docx = buildCaseReportDocx({
      docTitle: `工作汇报：${matter.name}`,
      sectionTitle: "办案时间轴",
      lines: report.lines,
      emptyText: CASE_REPORT_EMPTY_TEXT,
    });
    auditWrite("timeline.export", matterId, "办案时间轴节导出");
    const stem = `${matter.name}-工作汇报`.replace(/[\\/:*?"<>|\u0000-\u001f]/gu, "_").replace(/[\s.]+$/gu, "")
      || "工作汇报";
    return { docxBase64: docx.toString("base64"), fileName: `${stem}.docx` };
  },
  // ── 【步骤4·#26 LAN 团队同步】桥面十二命令（RE-26 §3；文案自写；secret/配对码不出本机）──
  teamStatus: async () => sanitizeValueForFrontend(teamSync.status()),
  teamCreate: async (params) => sanitizeValueForFrontend(
    teamSync.createTeam({ teamName: params?.teamName, myName: params?.myName })),
  teamDiscover: async () => ({ teams: await teamSync.discover() }),
  teamJoin: async (params) => sanitizeValueForFrontend(await teamSync.joinTeam({
    teamId: params?.teamId, code: params?.code, myName: params?.myName,
    ...(typeof params?.host === "string" && Number.isInteger(params?.port) ? { host: params.host, port: params.port } : {}),
  })),
  teamLeave: async () => teamSync.leaveTeam(),
  teamKick: async (params) => sanitizeValueForFrontend(await teamSync.kickMember(String(params?.memberId ?? ""))),
  teamSetPermissions: async (params) => sanitizeValueForFrontend(await teamSync.setPermissions(
    String(params?.memberId ?? ""), params?.view ?? null, Array.isArray(params?.edit) ? params.edit : [])),
  teamRefreshCode: async () => teamSync.refreshCode(),
  teamSyncNow: async () => teamSync.syncNow(),
  teamView: async () => sanitizeValueForFrontend(teamSync.view()),
  teamSubmitEdit: async (params) => teamSync.submitEdit({
    targetMemberId: String(params?.targetMemberId ?? ""), caseId: String(params?.caseId ?? ""),
    caseName: String(params?.caseName ?? ""), note: params?.note,
  }),
  teamRevertEdit: async (params) => teamSync.revertEdit(String(params?.editId ?? "")),
  // ── 功能 #19 轻量知识图谱（步骤4·RE-19）：graph 文档式 JSON 落桥同库（一图一行，不建三表）。
  // 写路径全量校验 fail-closed（防注入/限额/悬空引用/ISO 日期/关键事实须来源/config 白名单）；
  // 版本号乐观锁（baseRevision≠当前→冲突报错提示刷新）；规则建图数据同源案件记录
  // （当事人=MatterLite case_board_cases，证据=materials 登记目录），预览确认后写入（点击即授权）。
  caseGraphGet: async (params) => {
    const workspaceKey = workspaceKeyOf(params);
    const caseId = typeof params?.caseId === "string" ? params.caseId.trim().slice(0, 80) : "";
    if (!caseId) throw new Error("caseId 不能为空");
    const rec = store.getCaseGraph(workspaceKey, caseId);
    if (!rec) return { exists: false, caseId };
    let graph;
    try { graph = JSON.parse(rec.graph_json); } catch { throw new Error("关系图文档损坏（JSON 解析失败），拒绝读出"); }
    return { exists: true, caseId, revision: rec.revision, graph, updatedAt: rec.updated_at };
  },
  caseGraphSave: async (params) => {
    const workspaceKey = workspaceKeyOf(params);
    const caseId = typeof params?.caseId === "string" ? params.caseId.trim().slice(0, 80) : "";
    if (!caseId) throw new Error("caseId 不能为空");
    const graph = validateGraph(params?.graph); // 全量校验 fail-closed（RE-19 对拍 #30/#31/#32/#38）
    const rec = store.getCaseGraph(workspaceKey, caseId);
    const current = rec ? rec.revision : 0;
    const base = Number(params?.baseRevision);
    if (!Number.isInteger(base) || base !== current) {
      throw new Error(`修订冲突：这份关系图已被保存到修订 ${current}（你提交时基于修订 ${Number.isNaN(base) ? "?" : base}）。请刷新读取最新版后再保存。`);
    }
    const revision = current + 1;
    const updatedAtIso = new Date().toISOString();
    const doc = { ...graph, updatedAt: updatedAtIso };
    store.upsertCaseGraph(workspaceKey, caseId, JSON.stringify(doc), revision, Date.now());
    return { caseId, revision, updatedAt: updatedAtIso, nodeCount: doc.nodes.length, edgeCount: doc.edges.length };
  },
  // 规则建图预览：只出「将建的节点/关系清单」，不落库（对拍 #2：未确认不写入）。
  // 当事人读 MatterLite（#3 底座表，缺席/字段不齐时诚实跳过并说明）；证据读 materials 登记目录。
  caseGraphBuildPreview: async (params) => {
    const caseName = typeof params?.caseName === "string" ? params.caseName.trim().slice(0, 80) : "";
    const parties = [];
    let partiesNote = "当事人记录表尚未建立，本次只从材料登记建证据节点";
    try {
      const t = store.db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='case_board_cases'").get();
      if (t) {
        for (const row of store.listCases()) {
          for (const key of ["plaintiffs_json", "defendants_json"]) {
            let arr;
            try { arr = JSON.parse(row[key] || "[]"); } catch { arr = []; }
            for (const name of Array.isArray(arr) ? arr : []) {
              if (typeof name === "string" && name.trim()) parties.push({ name: name.trim() });
            }
          }
        }
        if (parties.length) partiesNote = `已从案件记录并入 ${parties.length} 名当事人`;
      }
    } catch { partiesNote = "当事人记录表读取失败，本次只从材料登记建证据节点"; }
    const dir = materialsDirOf(params?.workspacePath);
    let evidences = [];
    try {
      mkdirSync(dir, { recursive: true });
      evidences = readdirSync(dir)
        .filter((f) => MATERIALS_ALL_EXT.has(extname(f).toLowerCase()))
        .sort((a, b) => a.localeCompare(b, "zh-Hans-CN"))
        .map((f) => ({ name: f.replace(/\.(txt|md|docx)$/i, ""), filename: f }));
    } catch { evidences = []; }
    const proposal = buildGraphFromCaseRecords({
      title: caseName ? `${caseName}·关系图` : "案件关系图",
      parties, evidences,
    });
    return {
      caseId: typeof params?.caseId === "string" ? params.caseId.trim().slice(0, 80) : "",
      available: proposal.nodes.length > 0,
      partiesCount: parties.length,
      materialsCount: evidences.length,
      note: partiesNote,
      proposal,
    };
  },
  // 清空图（UI 侧先确认；乐观锁防误清他处新版本）
  caseGraphClear: async (params) => {
    const workspaceKey = workspaceKeyOf(params);
    const caseId = typeof params?.caseId === "string" ? params.caseId.trim().slice(0, 80) : "";
    if (!caseId) throw new Error("caseId 不能为空");
    const rec = store.getCaseGraph(workspaceKey, caseId);
    if (!rec) return { cleared: true, caseId };
    const base = Number(params?.baseRevision);
    if (!Number.isInteger(base) || base !== rec.revision) {
      throw new Error(`修订冲突：这份关系图已被保存到修订 ${rec.revision}。请刷新读取最新版后再清空。`);
    }
    store.deleteCaseGraph(workspaceKey, caseId);
    return { cleared: true, caseId };
  },
  // 来源跳转（对拍 #22）：按文件名回读材料正文（#6 文档库落地前走 materials 通道，file-closed 不出域）
  caseGraphReadSource: async (params) => {
    const mat = readRedlineMaterial(params?.workspacePath, params?.filename);
    const MAX = 40000;
    return { name: mat.name, text: mat.text.slice(0, MAX), truncated: mat.text.length > MAX };
  },

  // ══ 功能 #20 所内知识问答（步骤4·RE-20）桥面 ══
  // 树/上传/建夹/删除/移动/读取/同步/检索/问答线程（复用 M4 send 链 runAssistantTurn——
  // 同一 oc28 回合链/投影/落库/崩溃结算，B32「先检索后建 side 线程+SSE 流式+终态对账」等量）。
  // 隐身模式 fail-closed 与 #11/#25 同语义。
  kbTree: async () => {
    mkdirSync(KB_ROOT, { recursive: true });
    const folders = store.kbListCollections().map((c) => ({ path: c.path, name: c.name, updatedAt: c.updated_at }));
    const docs = store.kbListDocuments().map((d) => ({
      relPath: d.rel_path, title: d.title, ext: d.ext, sizeBytes: d.size_bytes, mtimeMs: d.mtime_ms,
      category: d.category || null, tags: (() => { try { return JSON.parse(d.tags_json || "[]"); } catch { return []; } })(),
      keywords: (() => { try { return JSON.parse(d.keywords_json || "[]"); } catch { return []; } })(),
      indexed: d.indexed_at > 0,
    }));
    const topLevel = new Set();
    for (const f of folders) topLevel.add(f.path.split("/")[0]);
    for (const d of docs) topLevel.add(d.relPath.split("/")[0]);
    return { root: KB_ROOT, folders, docs, counts: { files: docs.length, topLevel: topLevel.size } };
  },
  kbCreateFolder: async (params) => {
    const rel = safeRelPath(params?.path);
    if (rel.includes("/")) {
      // 父目录链上缺失的层级一并登记（创建 a/b 只建 a/b 一行——父链目录随文件落盘自动 mkdir）
      const parent = rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "";
      if (parent) {
        mkdirSync(join(KB_ROOT, ...parent.split("/")), { recursive: true });
        store.kbUpsertCollection({ id: "kbc_" + sha256(parent).slice(0, 10), name: parent.split("/").pop(), path: parent, created_at: Date.now(), updated_at: Date.now() });
      }
    }
    mkdirSync(join(KB_ROOT, ...rel.split("/")), { recursive: true });
    store.kbUpsertCollection({ id: "kbc_" + sha256(rel).slice(0, 10), name: rel.split("/").pop(), path: rel, created_at: Date.now(), updated_at: Date.now() });
    return { path: rel, name: rel.split("/").pop() };
  },
  // 上传落盘（B13）：主进程复制语义的桥面等量——目标经安全解析、父目录自动创建、
  // 同名静默覆盖（自研显式取舍=与竞品等量语义：覆盖既有文件，更新时间在树中可见）；
  // 失败逐文件报原因（B12「上传失败」错误条数据源）。
  kbImport: async (params) => {
    if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：出站通道全断，知识库上传未执行。请在设置中关闭隐身模式后重试。");
    mkdirSync(KB_ROOT, { recursive: true });
    const folderPath = params?.folderPath ? safeRelPath(params.folderPath) : "";
    const files = Array.isArray(params?.files) ? params.files : [];
    if (!files.length) throw new Error("未收到任何上传文件");
    const added = [];
    const failed = [];
    for (const f of files) {
      try {
        const name = String(f?.relPath ?? "");
        if (!name.trim()) throw new Error("文件名为空");
        const target = folderPath ? folderPath + "/" + safeRelPath(name) : safeRelPath(name);
        if (!KB_MANAGED_EXTS.has(extname(target).toLowerCase())) throw new Error("不支持的文件类型（不进托管根）");
        const buf = Buffer.from(String(f?.base64 ?? ""), "base64");
        if (!buf.length) throw new Error("文件内容为空");
        const { abs } = kbAbs(target);
        mkdirSync(join(abs, ".."), { recursive: true });
        writeFileSync(abs, buf); // 同名=静默覆盖（B13 自研取舍：覆盖，树上以更新时间体现）
        // 父目录链登记为文集行（树侧栏/表格式列表以 collections+documents 为数据面）
        const parent = target.includes("/") ? target.slice(0, target.lastIndexOf("/")) : "";
        if (parent) {
          for (let pi = parent.indexOf("/"); ; pi = parent.indexOf("/", pi + 1)) {
            const sub = pi === -1 ? parent : parent.slice(0, pi);
            store.kbUpsertCollection({ id: "kbc_" + sha256(sub).slice(0, 10), name: sub.split("/").pop(), path: sub, created_at: Date.now(), updated_at: Date.now() });
            if (pi === -1) break;
          }
        }
        added.push(target);
      } catch (e) {
        failed.push({ name: String(f?.relPath ?? "?"), reason: String(e?.message ?? e) });
      }
    }
    return { added, failed };
  },
  kbDelete: async (params) => {
    if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：知识库删除未执行。");
    const paths = Array.isArray(params?.paths) ? params.paths : [];
    if (!paths.length) throw new Error("未选择要删除的对象");
    let files = 0, folders = 0;
    for (const p of paths) {
      const rel = safeRelPath(p?.path);
      const { abs } = kbAbs(rel);
      if (p?.kind === "folder") {
        rmSync(abs, { recursive: true, force: true });
        store.kbDeleteCollectionsUnder(rel);
        for (const d of store.kbListDocuments()) {
          if (d.rel_path === rel || d.rel_path.startsWith(rel + "/")) store.kbDeleteDocument(d.rel_path);
        }
        folders++;
      } else {
        try { rmSync(abs, { force: true }); } catch { /* 缺盘文件仍清账 */ }
        store.kbDeleteDocument(rel);
        files++;
      }
    }
    return { files, folders };
  },
  kbMove: async (params) => {
    if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：知识库移动未执行。");
    const fromRel = safeRelPath(params?.fromPath);
    const toFolder = params?.toFolder ? safeRelPath(params.toFolder) : "";
    const name = fromRel.split("/").pop();
    if (toFolder === fromRel || toFolder.startsWith(fromRel + "/")) throw new Error("不能把对象移入其自身或其子文件夹（B18 防环）");
    const toRel = toFolder ? toFolder + "/" + name : name;
    if (toRel === fromRel) return { from: fromRel, to: toRel };
    const { abs: fromAbs } = kbAbs(fromRel);
    const { abs: toAbs } = kbAbs(toRel);
    mkdirSync(join(toAbs, ".."), { recursive: true });
    if (existsSync(toAbs)) throw new Error("目标位置已存在同名文件（不静默覆盖移动）");
    renameSync(fromAbs, toAbs);
    const doc = store.kbGetDocument(fromRel);
    if (doc) {
      store.kbUpdateDocumentPath(fromRel, toRel);
      // 空壳父目录不追残骸：源父目录若空则清 collections 记录
      const oldParent = fromRel.includes("/") ? fromRel.slice(0, fromRel.lastIndexOf("/")) : "";
      if (oldParent) {
        const left = store.kbListDocuments().some((d) => d.rel_path.startsWith(oldParent + "/"));
        const leftFolders = store.kbListCollections().some((c) => c.path.startsWith(oldParent + "/") || c.path === oldParent);
        if (!left && !leftFolders) store.kbDeleteCollection(oldParent);
      }
    }
    return { from: fromRel, to: toRel };
  },
  kbRead: async (params) => {
    const { rel, abs } = kbAbs(params?.relPath);
    let st;
    try { st = statSync(abs); } catch { throw new Error("文件不存在（可能已被移动或删除）"); }
    const ext = extname(abs).toLowerCase();
    const base = { relPath: rel, ext, sizeBytes: st.size, mtimeMs: Math.round(st.mtimeMs) };
    const text = kbReadTextIfIndexable(abs, ext);
    if (text !== null) return { ...base, kind: "text", text: text.slice(0, 200000) };
    if (KB_BINARY_PREVIEW_EXTS.includes(ext) || [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"].includes(ext)) {
      const MAX_PREVIEW_BYTES = 20 * 1024 * 1024;
      if (st.size > MAX_PREVIEW_BYTES) return { ...base, kind: "none", note: "文件超过预览大小上限" };
      const mime = ext === ".pdf" ? "application/pdf"
        : [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"].includes(ext) ? "audio/" + ext.slice(1)
        : "image/" + ext.slice(1);
      return { ...base, kind: "binary", mime, base64: readFileSync(abs).toString("base64") };
    }
    return { ...base, kind: "none", note: "该类型暂不支持应用内预览" };
  },
  // 系统打开（B21/B23）：交本机默认应用打开托管根内文件（本机行为，零出域零改库，不设隐身拦截）。
  // 失败两路（spawn 异常/退出码非零）一律 throw，UI 落「打开文件失败」错误条。
  kbOpenExternal: async (params) => {
    const { rel, abs } = kbAbs(params?.relPath);
    let st;
    try { st = statSync(abs); } catch { throw new Error("文件不存在（可能已被移动或删除）"); }
    if (!st.isFile()) throw new Error("目标不是普通文件，无法用系统应用打开");
    if (process.platform !== "win32") throw new Error("系统打开当前仅支持 Windows 平台");
    await new Promise((resolve, reject) => {
      let child;
      try { child = spawn("cmd.exe", ["/c", "start", "", abs], { stdio: "ignore", detached: true }); }
      catch (e) { reject(e); return; }
      child.on("error", reject);
      child.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`系统打开命令退出码 ${code}`))));
    });
    return { ok: true, rel };
  },
  // 索引同步（B22/D03 反向修正）：上限单源=KB_SYNC_DEFAULT_LIMIT（UI 不再另传小上限）；
  // 截断如实回报 truncated 供 UI 警告 toast。
  kbSync: async (params) => {
    mkdirSync(KB_ROOT, { recursive: true });
    try { kbImportBuiltinCorpus(); } catch { /* 内置文集收进失败不阻塞手动同步 */ }
    const requested = Number.isInteger(params?.maxFiles) ? params.maxFiles : KB_SYNC_DEFAULT_LIMIT;
    const maxFiles = Math.min(Math.max(1, requested), KB_SYNC_CONTRACT_LIMIT);
    const all = kbWalkFiles();
    const truncated = all.length > maxFiles;
    const batch = truncated ? all.slice(0, maxFiles) : all;
    const known = new Set(store.kbListDocuments().map((d) => d.rel_path));
    const seen = new Set();
    let indexed = 0, chunksTotal = 0, skipped = 0;
    for (const f of batch) {
      seen.add(f.rel);
      const ext = extname(f.rel).toLowerCase();
      let hash;
      try {
        const buf = readFileSync(f.abs);
        hash = buf.length <= 8 * 1024 * 1024 ? sha256(buf) : sha256(f.sizeBytes + ":" + f.mtimeMs); // >8MB 摘要哈希（诚实标注，不冒充全文哈希）
      } catch { skipped++; continue; }
      const prev = store.kbGetDocument(f.rel);
      if (prev && prev.content_hash === hash && prev.size_bytes === f.sizeBytes) { continue; }
      const text = kbReadTextIfIndexable(f.abs, ext);
      const relName = f.rel.split("/").pop();
      const sidecar = kbLoadSidecar(f.rel);
      const docId = "kbd_" + sha256(f.rel).slice(0, 12);
      let chunks = [];
      if (text !== null && text.trim()) chunks = chunkText(text);
      const category = typeof sidecar.category === "string" && KB_CATEGORIES.includes(sidecar.category)
        ? sidecar.category : (prev?.category ?? ruleClassify(text ?? "", relName));
      store.kbUpsertDocument({
        id: docId, collection_path: f.rel.includes("/") ? f.rel.slice(0, f.rel.lastIndexOf("/")) : "",
        title: relName.replace(/\.[^.]+$/u, "") || relName, rel_path: f.rel, ext,
        size_bytes: f.sizeBytes, mtime_ms: f.mtimeMs, content_hash: hash, category,
        tags_json: JSON.stringify(Array.isArray(sidecar.tags) ? sidecar.tags.map(String).slice(0, 20) : []),
        keywords_json: JSON.stringify(Array.isArray(sidecar.keywords) ? sidecar.keywords.map(String).slice(0, 30) : []),
        indexed_at: chunks.length ? Date.now() : 0,
      });
      if (chunks.length) {
        store.kbReplaceChunks(docId, chunks);
        indexed++;
        chunksTotal += chunks.length;
      }
    }
    for (const rel of known) {
      if (!seen.has(rel)) store.kbDeleteDocument(rel);
    }
    // 盘上目录登记为文集行（同步以盘为真源；上传通道外的文件夹也进树）
    const seenDirs = new Set();
    for (const f of batch) {
      let p = f.rel.includes("/") ? f.rel.slice(0, f.rel.lastIndexOf("/")) : "";
      while (p) { seenDirs.add(p); p = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : ""; }
    }
    for (const d of seenDirs) {
      store.kbUpsertCollection({ id: "kbc_" + sha256(d).slice(0, 10), name: d.split("/").pop(), path: d, created_at: Date.now(), updated_at: Date.now() });
    }
    // revision=全部(rel,hash) 串接 sha256（契约口径）
    const revision = sha256(store.kbListDocuments().map((d) => d.rel_path + "\0" + d.content_hash).sort().join("\n"));
    store.kbSetMeta("synced_at", String(Date.now()));
    store.kbSetMeta("revision", revision);
    store.kbSetMeta("schema_version", "1");
    store.kbSetMeta("retriever_version", "juscite-sparse-v1");
    return { files: batch.length, indexed, chunks: chunksTotal, skipped, truncated, revision, ftsMode: store.kbFtsMode() };
  },
  // 检索面（B59 首版裁剪=检索件；字节经济学：≤5 源/摘录 500/总序列化 ≤8000）
  kbSearch: async (params) => {
    const query = typeof params?.query === "string" ? params.query.trim() : "";
    if (!query) return { mode: "empty", hits: [], sources: [], contextText: "" };
    const folderPrefix = params?.folderPath ? safeRelPath(params.folderPath) : null;
    const r = kbRetrieve(query, { folderPrefix });
    const excerptCap = 500;
    return {
      mode: r.mode, routes: r.routes,
      hits: r.hits.slice(0, Math.min(Number(params?.limit) || 5, 20)).map((h) => ({
        title: h.title, path: h.path, articleNumber: h.articleNumber ?? null,
        excerpt: h.content.slice(0, excerptCap), score: Math.round(h.score * 1000) / 1000,
        relevance: Math.min(100, Math.round((h.score / 30) * 100)), rankReason: h.rankReason,
      })),
      sources: r.sources, contextText: r.contextText.slice(0, 8000),
    };
  },
  // 问答（B32 流程）：先本地检索→[来源N] 映射→拼提示词→建/复用 side 线程→M4 回合链流式
  kbAsk: async (params) => {
    const question = typeof params?.question === "string" ? params.question.trim() : "";
    if (!question) throw new Error("问题不能为空");
    if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：出站通道全断，知识库问答未连接任何模型。请在设置中关闭隐身模式后重试。");
    const scope = params?.scope && typeof params.scope === "object" ? params.scope : { kind: "global" };
    const kind = scope.kind === "folder" || scope.kind === "file" ? scope.kind : "global";
    const folderPath = kind === "folder" && scope.folderPath ? safeRelPath(scope.folderPath) : null;
    const quote = params?.quote && typeof params.quote.text === "string" && params.quote.text.trim()
      ? { text: params.quote.text.slice(0, 6000), source: String(params.quote.source ?? "划选内容"), page: Number.isInteger(params.quote.page) ? params.quote.page : null } : null;
    // B37 模型选择：UI 跟随主对话所选（或文件档选择器）传入；缺省/非法回落内置 BRIDGE_MODEL。
    // 桥面 UI 参数形状 {id,providerID} 为既有接线合同；runtime 面一律 ModelSelection。
    let askModel = BRIDGE_MODEL;
    if (params?.model && typeof params.model === "object") {
      const mid = typeof params.model.id === "string" ? params.model.id.trim().slice(0, 120) : "";
      const mpid = typeof params.model.providerID === "string" ? params.model.providerID.trim().slice(0, 120) : "";
      if (mid && mpid) askModel = { modelId: mid, providerId: mpid };
      else if (mid) askModel = { modelId: mid, providerId: BRIDGE_MODEL.providerId };
    }
    // 建/复用线程（B36 标题=功能前缀+问题前 30 字；B44 同视图复用）
    let threadId = typeof params?.threadId === "string" ? params.threadId : "";
    if (threadId && !liveSessions.has(threadId)) threadId = "";
    if (threadId && convStateOf(threadId).busy) throw new Error("上一条回答仍在生成中，请稍候或清空对话后重问");
    const now = Date.now();
    if (!threadId) {
      threadId = "ses_kb_" + randomUUID().slice(0, 8);
      liveSessions.set(threadId, {
        sessionId: threadId, workspaceId: KB_WORKSPACE_KEY,
        title: threadTitle({ kind, folderName: folderPath ? folderPath.split("/").pop() : "", fileName: scope.fileName }, question),
        titleSource: "generated", workspacePath: WORKSPACE.path, projectId: null,
        phase: "draft", sessionEnded: false, hasBackgroundWork: false, lastActivityAt: now, createdAt: now,
      });
    }
    const st = convStateOf(threadId);
    st.kbCtx = { kind, folderPath, fileName: scope.fileName ?? null, filePath: scope.filePath ? safeRelPath(scope.filePath) : null };
    // ①本地检索（B32 步 1；文件档=问题+文件名+路径拼串查询，正文直读优先）
    let retrieval = { contextText: "", sources: [] };
    let fileBody = "";
    if (kind === "file" && st.kbCtx.filePath) {
      try {
        const { abs } = kbAbs(st.kbCtx.filePath);
        const ext = extname(abs).toLowerCase();
        const t = kbReadTextIfIndexable(abs, ext);
        if (t !== null) fileBody = t;
      } catch { /* 读不到正文→提示词内如实列文件信息（B34 降级路） */ }
      retrieval = kbRetrieve(question + " " + (scope.fileName ?? "") + " " + st.kbCtx.filePath, {});
    } else {
      retrieval = kbRetrieve(question, { folderPrefix: folderPath });
    }
    // ②[来源N]→路径映射（≤8，只保留最近一轮，B41）
    kbSourcesByThread.set(threadId, retrieval.sources);
    // ③拼提示词（B33/B34；文案全自写）
    const prompt = buildAskPrompt({
      question, scope: { kind, folderName: folderPath ? folderPath.split("/").pop() : "", fileName: scope.fileName, fileSize: scope.fileSize },
      retrieval, fileBody: fileBody.slice(0, 4000), fileName: scope.fileName, quote,
    });
    st.lastPrompt = prompt; // 诊断/测试面（内存态，不入库）
    // ④用户行+回合链（M4 runAssistantTurn：oc28 流式/投影/落库/崩溃结算全复用）
    const ack = { commandId: "cmd_" + randomUUID().slice(0, 8), status: "accepted", revisionAtDecision: 1 };
    const turnId = "turn_" + randomUUID().slice(0, 8);
    const pti = "pt_" + randomUUID().slice(0, 8);
    const userRow = { ...baseRow(st, turnId, pti, { canEdit: false }), kind: "userInput", origin: "realUser",
      text: question, sourceCommandId: ack.commandId, ...(quote ? { kbQuote: quote } : {}) };
    st.rows.push(userRow);
    persistRow(threadId, userRow);
    const summary = liveSessions.get(threadId);
    summary.phase = "running";
    summary.lastActivityAt = Date.now();
    st.phase = "running";
    st.lastError = null;
    st.lastCommandId = ack.commandId;
    persistSessionState(threadId);
    const turnHeaderRow = { ...baseRow(st, turnId, pti), kind: "turnHeader", origin: "userInput", executionKind: "agent", state: "running", startedAt: Date.now() };
    st.rows.push(turnHeaderRow);
    persistRow(threadId, turnHeaderRow);
    runAssistantTurn(threadId, ack, turnId, pti, turnHeaderRow, prompt, { model: askModel, kbThread: true });
    return {
      threadId,
      title: summary.title,
      sources: retrieval.sources.map((s) => ({ n: s.n, title: s.title, path: s.path, relevance: s.relevance })),
      retrieved: retrieval.sources.length,
      mode: retrieval.mode,
    };
  },
  // 线程状态轮询（问答面流式投影；SSE 中断由终态对账兜底的同款语义——轮询读权威 rows）
  kbThreadState: async (params) => {
    const threadId = String(params?.threadId ?? "");
    const summary = liveSessions.get(threadId);
    if (!summary) throw new Error("问答线程不存在（可能已被删除）");
    const st = convStateOf(threadId);
    // 答案后处理（B40）：完成行剥重复问题头/协议残帧（kb_service.cleanAnswer 单源）；streaming 原样
    const lastQuestion = [...st.rows].reverse().find((r) => r.kind === "userInput")?.text ?? "";
    return {
      threadId, title: summary.title, phase: st.phase, busy: st.busy,
      lastError: st.lastError,
      rows: st.rows.filter((r) => r.kind === "userInput" || r.kind === "assistantText").map((r) => ({
        rowId: r.rowId, kind: r.kind, state: r.state,
        text: r.kind === "assistantText" && r.state === "complete" ? cleanAnswer(r.text ?? "", lastQuestion) : (r.text ?? ""),
        reasoning: r.reasoning ?? "",
        createdAt: r.createdAt, model: r.model ?? null, kbQuote: r.kbQuote ?? null,
      })),
      sources: kbSourcesByThread.get(threadId) ?? [],
      kbCtx: st.kbCtx ?? null,
      lastPrompt: st.lastPrompt ?? null,
    };
  },
  kbThreads: async () => ({
    threads: [...liveSessions.values()]
      .filter((s) => s.workspaceId === KB_WORKSPACE_KEY)
      .sort((a, b) => b.lastActivityAt - a.lastActivityAt)
      .map((s) => ({ threadId: s.sessionId, title: s.title, phase: s.phase,
        updatedAt: s.lastActivityAt, createdAt: s.createdAt,
        kbCtx: convStates.get(s.sessionId)?.kbCtx ?? null })),
  }),
  kbThreadDelete: async (params) => {
    const threadId = String(params?.threadId ?? "");
    const summary = liveSessions.get(threadId);
    if (!summary) return { deleted: threadId };
    if (convStateOf(threadId).busy) throw new Error("该问答正在生成中，等回答结束后再删除");
    store.deleteSession(summary.workspaceId, threadId);
    liveSessions.delete(threadId);
    convStates.delete(threadId);
    kbSourcesByThread.delete(threadId);
    return { deleted: threadId };
  },
  // [来源N] 点击解析（B41）：映射表只保留最近一次提问的来源；无映射不动作（返回 null）
  kbResolveSource: async (params) => {
    const threadId = String(params?.threadId ?? "");
    const n = Number(params?.n);
    const sources = kbSourcesByThread.get(threadId) ?? [];
    const hit = sources.find((s) => s.n === n);
    return hit ? { n: hit.n, title: hit.title, path: hit.path, relevance: hit.relevance } : null;
  },

  // ══ 功能 #16 调研报告（步骤4·RE-16）桥面 ══
  // 记录 CRUD/编辑落账/清空 + 调研回合链（B09 独立内部会话 + B24 有界续跑 ≤5 + B37 停止）
  // + 导出 Word/MD（B39/B41 默认名清洗+后缀强制在桥侧单源）+ 本地法规库兜底检索（B31 轻量期，
  // fail-closed 不升级浏览器自动化）。派生字段（规划/阶段/报告三桶）由共享纯模型 deriveFromRows
  // 单源产出，UI 只做呈现；隐身模式 fail-closed 与 #20 同语义。
  researchStatus: async () => {
    let lawsAvailable = false;
    lawsAvailable = researchLawsAvailability(); // 读不出按 false（F2 同语义，B06 提示条事实源）
    const settings = loadSetting();
    const primary = settings.primaryLegalSource; // B50（AppSettings additive 字段，缺省无；运行时宽容）
    return {
      lawsAvailable,
      stealth: Boolean(settings.stealthMode?.enabled),
      primaryLegalSource: typeof primary === "string" ? primary : null,
    };
  },
  researchRun: async (params) => {
    const query = typeof params?.query === "string" ? params.query.trim() : "";
    if (!query) throw new Error("课题不能为空");
    if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：出站通道全断，调研未连接任何模型。请在设置中关闭隐身模式后重试。");
    if (isBareResearchTopic(query)) {
      // B29 裸话题防误触发（本工作区发送的是固定模板，此闸兜住其他入口直启的标题式输入）
      throw new Error("这更像一个话题词而不是调研指令：请补充一句具体要求（例如「请调研××相关的法律规定与典型案例」）后再发起。");
    }
    // B10 模型回退：UI 传主对话所选（两种命名形状都收）；缺省/非法回落内置 BRIDGE_MODEL。
    let runModel = BRIDGE_MODEL;
    const m = params?.model;
    if (m && typeof m === "object") {
      const mid = typeof m.id === "string" && m.id.trim() ? m.id.trim().slice(0, 120)
        : typeof m.modelId === "string" && m.modelId.trim() ? m.modelId.trim().slice(0, 120) : "";
      const mpid = typeof m.providerID === "string" && m.providerID.trim() ? m.providerID.trim().slice(0, 120)
        : typeof m.providerId === "string" && m.providerId.trim() ? m.providerId.trim().slice(0, 120) : "";
      if (mid && mpid) runModel = { modelId: mid, providerId: mpid };
      else if (mid) runModel = { modelId: mid, providerId: BRIDGE_MODEL.providerId };
    }
    const now = Date.now();
    const rec = newResearchRecord(query, now); // B07：id=时间戳串；B08：初始 planning=即时规划
    const promptParts = [buildResearchPrompt(query)]; // B11 五要素模板（自写），课题内插
    // B27 轻量期等量（对拍 28）：启动前确认检索源状态再首轮——本地法规库可用与否注入首跳
    promptParts.push(researchLawsAvailability()
      ? "检索源状态：所内法规库当前可用，法规依据优先取自所内法规库并核对效力。"
      : "检索源状态：所内法规库当前不可用，法规依据请改用官方发布渠道，取不到即在来源节如实标注「未经核验」。");
    const primary = loadSetting().primaryLegalSource;
    if (typeof primary === "string" && primary) {
      const dir = primarySourceDirective(primary); // B50 首选源指令按配置注入
      if (dir) promptParts.push(dir);
    }
    const prompt = promptParts.join("\n\n");
    // B09 独立内部会话：专用工作区键，主对话 sessions-index 永不携带（标题=功能名+课题前 60 字）
    const threadId = "ses_res_" + randomUUID().slice(0, 8);
    liveSessions.set(threadId, {
      sessionId: threadId, workspaceId: RESEARCH_WORKSPACE_KEY,
      title: researchThreadTitle(query), titleSource: "generated",
      workspacePath: WORKSPACE.path, projectId: null,
      phase: "draft", sessionEnded: false, hasBackgroundWork: false,
      lastActivityAt: now, createdAt: now,
    });
    rec.threadId = threadId;
    researchCancelled.delete(rec.id);
    researchDead.delete(rec.id);
    persistResearchRecord(rec, { force: true });
    void runResearchTurnChain(rec, threadId, prompt, runModel); // 回合链异步推进，UI 靠轮询投影
    return { record: rec, threadId };
  },
  // 轮询投影（B36 对账口：流式增量以桥内权威 rows 为准；派生三桶在此单源产出）
  researchThreadState: async (params) => {
    const threadId = String(params?.threadId ?? "");
    const summary = liveSessions.get(threadId);
    if (!summary || summary.workspaceId !== RESEARCH_WORKSPACE_KEY) throw new Error("调研会话不存在（可能已被清理或桥已重启）");
    const st = convStateOf(threadId);
    const rows = st.rows.filter((r) => r.kind === "userInput" || r.kind === "assistantText").map((r) => ({
      rowId: r.rowId, kind: r.kind, state: r.state, text: r.text ?? "", reasoning: r.reasoning ?? "", createdAt: r.createdAt,
    }));
    const derived = deriveFromRows(rows.filter((r) => r.state !== "failed"));
    // B15 步骤投影（live）：tool-call → ResearchStep（错误步骤文案在内核 toResearchStep 单源）
    const liveSteps = [];
    for (const r of st.rows) {
      if (r.kind !== "assistantText" || !Array.isArray(r.toolCalls)) continue;
      for (let i = 0; i < r.toolCalls.length; i++) {
        const tc = r.toolCalls[i];
        liveSteps.push(toResearchStep({
          id: `${threadId}-${r.rowId}-${i}`, name: tc.name, input: tc.input, output: tc.output,
          error: r.state === "failed" ? (st.lastError?.message ?? "调用失败") : tc.error,
          status: r.state === "failed" || tc.error ? "error" : r.state === "streaming" ? "running" : "done",
        }));
      }
    }
    return {
      threadId, title: summary.title, phase: st.phase, busy: st.busy, lastError: st.lastError,
      rows, planning: derived.planning, updates: derived.updates, summary: derived.summary,
      reasoning: derived.reasoning, lastPrompt: st.lastPrompt ?? null,
      steps: liveSteps, // B28：目录/步骤信息面（只追加，不落错）
    };
  },
  researchRecordGet: async (params) => {
    const row = store.getResearchRecord(String(params?.id ?? ""));
    return row ? researchRecordFromJson(row.record_json) : null;
  },
  // 记录落账（B38/B45 边角）：UI 侧乐观记录/本地错误记录持久化；死亡集合可用 force 绕行由调用方把关
  researchRecordSave: async (params) => {
    const rec = normalizeRecord(params?.record);
    if (!rec) throw new Error("调研记录形状非法");
    persistResearchRecord(rec, { force: true });
    return { record: rec };
  },
  // B36 对账失败落错：running 记录标记终态错误（会话不存在等）；非 running 原样返回
  researchRecordFail: async (params) => {
    const id = String(params?.id ?? "");
    const row = store.getResearchRecord(id);
    if (!row) throw new Error("调研记录不存在");
    const rec = researchRecordFromJson(row.record_json);
    if (!rec || rec.status !== "running") return rec;
    researchCancelled.add(id);
    return finalizeResearchRecord(rec, {
      status: "error",
      error: String(params?.message ?? "调研会话已失效（对账失败）。"),
    }, { force: true });
  },
  researchRecordList: async () => ({
    records: store.listResearchRecords().map((r) => researchRecordFromJson(r.record_json)).filter(Boolean),
  }),
  // 编辑落账（B43）：summary=editedSummary=新文、reportRevision=编辑时间戳；页面/两种导出同步用编辑版
  researchRecordEdit: async (params) => {
    const id = String(params?.id ?? "");
    const text = typeof params?.summary === "string" ? params.summary : "";
    if (!text.trim()) throw new Error("报告内容不能为空");
    const row = store.getResearchRecord(id);
    if (!row) throw new Error("调研记录不存在");
    const rec = researchRecordFromJson(row.record_json);
    if (!rec) throw new Error("调研记录数据损坏");
    const next = applyReportEdit(rec, text);
    persistResearchRecord(next, { force: true });
    return { record: next };
  },
  researchRecordDelete: async (params) => {
    const id = String(params?.id ?? "");
    const row = store.getResearchRecord(id);
    if (row) {
      const rec = researchRecordFromJson(row.record_json);
      if (rec && rec.status === "running") {
        // B44：running 条目删除先触发停止（链不再续跳；链尾不复活已删行）
        researchCancelled.add(id);
        researchDead.add(id);
      }
    }
    store.deleteResearchRecord(id);
    return { deleted: id };
  },
  researchClearRecords: async () => {
    // B45 清空：在跑链一并取消；死亡集合防链尾复活
    for (const r of store.listResearchRecords()) { researchCancelled.add(r.id); researchDead.add(r.id); }
    store.clearResearchRecords();
    return { cleared: true };
  },
  // B37 手动停止：取消续跳 + 末帧补提交（当前 rows 投影写进记录）+ 落停止终态
  researchStop: async (params) => {
    const id = String(params?.id ?? "");
    const row = store.getResearchRecord(id);
    if (!row) throw new Error("调研记录不存在");
    const rec = researchRecordFromJson(row.record_json);
    if (!rec) throw new Error("调研记录数据损坏");
    if (rec.status !== "running") return { record: rec };
    researchCancelled.add(id);
    let merged = { planning: rec.planning, updates: rec.updates, summary: rec.summary };
    if (rec.threadId && liveSessions.has(rec.threadId)) {
      const st = convStateOf(rec.threadId);
      const derived = deriveFromRows(st.rows.filter((r) => r.kind === "assistantText" && r.state !== "failed")
        .map((r) => ({ kind: r.kind, text: r.text ?? "", reasoning: r.reasoning ?? "" })));
      merged = {
        planning: rec.planning ?? derived.planning ?? undefined,
        updates: derived.updates.length ? derived.updates : rec.updates,
        summary: rec.summary || derived.summary,
      };
    }
    const next = finalizeResearchRecord(rec, {
      ...merged,
      status: "error",
      error: "已停止：本次调研被手动中止。",
    }, { force: true });
    return { record: next };
  },
  // B39 导出 Word：预处理→标准法律文书 docx（零依赖装配复用 #10 管线）；默认名清洗+.docx 强制
  researchExportWord: async (params) => {
    const markdown = typeof params?.markdown === "string" && params.markdown.trim() ? params.markdown : null;
    if (!markdown) throw new Error("导出内容不能为空");
    const query = typeof params?.query === "string" ? params.query : "";
    // B40 首版只走标准转换（模板填充保版式随文书线解挂，§5 边界 2）；模板源丢失报错路不适用
    const docx = markdownToLegalDocx(preprocessReportMarkdown(markdown));
    return { docxBase64: docx.toString("base64"), fileName: exportFileName(query, ".docx"), mode: "standard" };
  },
  // B41 导出 MD：同一默认名规则；导出与展示共用预处理（B42）
  researchExportMd: async (params) => {
    const markdown = typeof params?.markdown === "string" ? params.markdown : "";
    const query = typeof params?.query === "string" ? params.query : "";
    return { text: preprocessReportMarkdown(markdown), fileName: exportFileName(query, ".md") };
  },
  // B31 轻量期兜底：本地法规库索引直检（三策略+排序+时效标签；只认带文件名出处的条目）；
  // 库不可用/损坏=fail-closed 话术，不升级浏览器自动化。BRIDGE_LAWS_INDEX 仅测试覆盖（合成材料）。
  researchLegalLookup: async (params) => {
    const query = typeof params?.query === "string" ? params.query : "";
    const indexPath = process.env.BRIDGE_LAWS_INDEX || LAWS_INDEX_PATH;
    let entries;
    try {
      const parsed = JSON.parse(readFileSync(indexPath, "utf-8"));
      if (parsed && parsed.enabled === false) return { ok: false, hits: [], notice: LAW_LOOKUP_UNAVAILABLE };
      entries = Array.isArray(parsed) ? parsed : Array.isArray(parsed?.laws) ? parsed.laws : [];
    } catch {
      return { ok: false, hits: [], notice: LAW_LOOKUP_UNAVAILABLE };
    }
    return lookupLawsLibrary(entries, query);
  },
  // 智能分类（B17）：模型按正文归类（批量一回合，候选=13 类+同名文件夹并入）+同内容缓存
  // （缓存命中=跳过不重复调模型，跳过数随 skipped 回报）+规则兜底
  kbClassify: async (params) => {
    const rels = Array.isArray(params?.paths) ? params.paths.map(String) : [];
    if (!rels.length) throw new Error("未选择要分类的文件");
    if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：智能分类未连接任何模型，仅可走规则兜底。");
    const jobs = [];
    const cached = {};
    let skipped = 0;
    const folderNames = new Set(store.kbListCollections().map((c) => c.name)); // 同名文件夹并入候选（B17）
    for (const rel of rels.slice(0, 200)) {
      const { abs } = kbAbs(rel);
      const ext = extname(abs).toLowerCase();
      const text = kbReadTextIfIndexable(abs, ext);
      const key = "classify:" + sha256(text ?? "ext:" + ext);
      const hit = store.kbGetMeta(key);
      if (hit && (KB_CATEGORIES.includes(hit) || folderNames.has(hit))) { cached[rel] = hit; skipped++; continue; }
      jobs.push({ rel, text: text ?? "", key });
    }
    let source = jobs.length ? "cache" : "cache";
    if (jobs.length) {
      let modelMap = null;
      const folderCandidates = [...new Set(store.kbListCollections().map((c) => c.name))].filter((n) => n && !KB_CATEGORIES.includes(n));
      try { modelMap = await runKbClassifyTurn(jobs, folderCandidates); source = "model"; }
      catch { source = "rules"; } // 无模型/超时/输出不合法→规则兜底（B17）
      for (const j of jobs) {
        const cat = (modelMap && modelMap[j.rel]) || ruleClassify(j.text, j.rel.split("/").pop());
        const doc = store.kbGetDocument(j.rel);
        if (doc) store.kbUpsertDocument({ ...doc, category: cat });
        store.kbSetMeta(j.key, cat); // 同内容缓存不重复调模型
        cached[j.rel] = cat;
      }
    }
    return { categories: cached, source, skipped };
  },
  kbDiagnose: async () => ({
    root: KB_ROOT,
    documents: store.kbCountDocuments(),
    chunks: store.db.prepare("SELECT COUNT(*) AS n FROM kb_chunks").get().n,
    ftsMode: store.kbFtsMode(),
    ftsThreshold: KB_FTS_THRESHOLD,
    lastSyncedAt: Number(store.kbGetMeta("synced_at") ?? 0) || null,
    revision: store.kbGetMeta("revision"),
    syncLimit: KB_SYNC_DEFAULT_LIMIT,
  }),
  getSkillReferenceCatalog: async () => ({ refs: [] }),
  readMcpResource: async () => ({ contents: [] }),
  // ── 功能 #25 文档对比（施工单-03 任务四）：材料通道 + 确定性对比 ──
  // 列 materials/ 目录纯文本材料（.txt/.md）；compareDocuments 产增/删/改 hunk 与统计，
  // 双栏渲染由 UI 复用树内 @pierre/diffs（split）完成。
  listWorkspaceDocuments: async (params) => {
    const dir = materialsDirOf(params?.workspacePath);
    mkdirSync(dir, { recursive: true });
    const documents = [];
    for (const f of readdirSync(dir)) {
      const ext = extname(f).toLowerCase();
      const isText = MATERIALS_TEXT_EXT.has(ext);
      const isWord = MATERIALS_WORD_EXT.has(ext);
      if (!isText && !isWord) continue;
      let st;
      try { st = statSync(join(dir, f)); } catch { continue; }
      if (!st.isFile()) continue;
      documents.push({ name: f, kind: isWord ? "word" : "text", size: st.size, updatedAt: Math.round(st.mtimeMs) });
    }
    documents.sort((a, b) => a.name.localeCompare(b.name, "zh-Hans-CN"));
    return { dir, documents };
  },
  compareDocuments: async (params) => {
    const left = readMaterialText(params?.workspacePath, params?.leftName);
    const right = readMaterialText(params?.workspacePath, params?.rightName);
    const a = splitLines(left.text), b = splitLines(right.text);
    const hunks = buildHunks(diffOps(a, b));
    return {
      left: { name: left.name, text: left.text },
      right: { name: right.name, text: right.text },
      hunks,
      stats: diffStats(a.length, b.length, hunks),
    };
  },
  // ── 任务三补面（R3）：plugins/* 全词表桩（形状按 @zcode/shared schema；合成面诚实空态）。
  // ── 功能 #10 模板文书起草（RE-10）：目录/上传学习/隐藏模板解析/生成执行/中途引导/历史/导出 ──
  // 生成=独立隐藏工作区线程（专用 oc28 会话，标题"文书写作：<模板名>"，不进对话主会话列表）；
  // 五阶段为桥内步骤事件驱动展示相位（非真实编排）；完成结算双通道（流式累计+落库回捞，取最后过文书判定者）；
  // 隐身 fail-closed；历史写失败不阻塞生成（E17）；steer=运行中向同 oc28 会话追加排队消息（E9）。
  draftCatalog: async () => {
    let userTemplates = [];
    try {
      userTemplates = listUserTemplates().map((t) => ({
        id: t.id, name: t.name, description: t.description, category: "custom",
        fields: t.fields, learningStatus: t.learningStatus, learningError: t.learningError,
        hasSourceDocx: Boolean(t.sourceDocument), createdAt: t.createdAt,
      }));
    } catch { userTemplates = []; } // 列表加载失败静默回退只用内置目录（RE-10 §2 I9）
    return { builtin: CATALOG_TEMPLATES, userTemplates };
  },
  draftUploadTemplate: async (params) => {
    const fileName = String(params?.fileName ?? "");
    const ext = extname(fileName).toLowerCase();
    const WHITELIST = new Set([".docx", ".doc", ".pdf", ".txt", ".md"]);
    if (!WHITELIST.has(ext)) throw new Error("仅支持 .docx/.doc/.pdf/.txt/.md 模板文件");
    const base64 = String(params?.base64 ?? "");
    if (!base64) throw new Error("文件内容为空");
    const bytes = Buffer.from(base64, "base64");
    let text = "";
    if (ext === ".txt" || ext === ".md") text = bytes.toString("utf-8");
    else if (ext === ".docx") text = extractDocxText(bytes);
    else throw new Error("PDF/DOC 需走 OCR 通道（当前未接入）：请先转换为 txt 或 md 再上传"); // 依赖挂起降级（RE-10 §5）
    text = text.replace(/\u0000/g, ""); // NUL 清洗
    if (!text.trim()) throw new Error("未能提取到文字：文件可能为空或为扫描件");
    if (text.length > 50000) text = text.slice(0, 50000); // 截断 5 万字
    const rec = createUserTemplateFromUpload({ fileName, text, sourceBase64: ext === ".docx" ? base64 : undefined });
    void draftScheduleLearning(rec.id); // AI 学习流水异步（上传应答不阻塞）
    return {
      template: { id: rec.id, name: rec.name, description: rec.description, category: "custom",
        fields: rec.fields, learningStatus: rec.learningStatus, learningError: "", hasSourceDocx: Boolean(rec.sourceDocument), createdAt: rec.createdAt },
    };
  },
  draftRetryLearning: async (params) => {
    const id = String(params?.templateId ?? "");
    const tpl = getUserTemplate(id);
    if (!tpl) throw new Error("模板不存在");
    void draftScheduleLearning(id);
    return { id, learningStatus: "analyzing" };
  },
  draftDeleteTemplate: async (params) => {
    const id = String(params?.templateId ?? "");
    const ok = deleteUserTemplate(id);
    if (!ok) throw new Error("模板不存在");
    auditWrite("doc.delete", id, "删除自定义模板"); // 对拍 31 补账：文档域第二调用点（模板面，target=custom-* 与历史面 dh-* 自区分），业务成功才入账
    return { ok };
  },
  // 隐藏模板解析三态（resolve_legal_document_template 等量）：类型非法=isError；未命中=带全案由清单；命中=模板+随附指令
  draftResolveTemplate: async (params) => resolveDocumentTemplate({ documentType: params?.documentType, query: params?.query }),
  draftGenerate: async (params) => {
    if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：出站通道全断，文书生成未连接任何模型。请在设置中关闭隐身模式后重试。");
    const materialNames = (Array.isArray(params?.materialNames) ? params.materialNames : []).slice(0, 20).map((n) => String(n));
    const pastedCase = typeof params?.pastedCase === "string" ? params.pastedCase : "";
    const fieldValuesIn = (params?.fieldValues && typeof params.fieldValues === "object" && !Array.isArray(params.fieldValues)) ? params.fieldValues : {};
    const filledCount = Object.values(fieldValuesIn).filter((v) => typeof v === "string" && v.trim()).length;
    // 生成门（服务端同守 D9）：材料/粘贴/字段 三源择一非空
    if (!materialNames.length && !pastedCase.trim() && !filledCount) {
      throw new Error("请上传案件材料、粘贴案情文字，或填写必要的文书信息后再生成");
    }
    const templateSource = params?.templateSource === "custom" ? "custom" : "builtin";
    let templateContent = "", templateName = "", legalBasis = "", templateIsHidden = false, categoryLabel = "内置";
    if (templateSource === "custom") {
      const tpl = getUserTemplate(String(params?.templateId ?? ""));
      if (!tpl) throw new Error("所选自定义模板不存在或已被删除");
      templateContent = tpl.content; templateName = tpl.name; categoryLabel = "自定义";
    } else {
      const b = CATALOG_TEMPLATES.find((t) => t.id === params?.templateId);
      if (b) { templateContent = b.content; templateName = b.name; legalBasis = b.legalBasis ?? ""; categoryLabel = b.category === "litigation" ? "诉讼" : "非诉"; }
      else if (params?.hiddenDocumentType) {
        const r = resolveDocumentTemplate({ documentType: params.hiddenDocumentType, query: String(params?.hiddenQuery ?? params?.pastedCase ?? "") });
        if (r.matched) { templateContent = r.template.content; templateName = r.template.name; templateIsHidden = true; categoryLabel = "诉讼"; }
      }
    }
    const materials = [];
    const materialErrors = [];
    for (const name of materialNames) {
      try {
        const m = readRedlineMaterial(params?.workspacePath, name); // txt/md 直读；docx 零依赖提取；失败不阻塞其他材料
        if (m.text.trim()) materials.push({ name: m.name, text: m.text });
        else materialErrors.push(name + "：正文为空，已跳过");
      } catch (e) { materialErrors.push(name + "：" + (e?.message ?? e)); }
    }
    const instructions = String(params?.instructions ?? "").slice(0, 5000); // 指令 ≤5000（生成请求合同）
    const fieldValues = {};
    for (const [k, v] of Object.entries(fieldValuesIn)) fieldValues[String(k).slice(0, 200)] = String(v ?? "").slice(0, 50000);
    const ourParty = String(fieldValues["我方主体"] ?? "").trim();
    const prompt = assembleGenerationPrompt({
      templateName, templateContent,
      documentTypeName: params?.hiddenDocumentType === "answer" ? "民事答辩状" : "民事起诉状",
      fieldValues, ourParty, materials, pastedCase, instructions,
      hasUserTemplate: templateSource === "custom", legalResearchAvailable: false, templateIsHidden,
      legalBasis,
    });
    const draftId = "draft_" + randomUUID().slice(0, 8);
    const job = {
      id: draftId, status: "running", stages: {}, lastTool: "装配案件材料", text: "",
      verdict: "", notice: "", error: "", cancelled: false, oc28Id: "",
      templateName: templateName || "法律文书", templateSource, categoryLabel,
      materialNames: materials.map((m) => m.name), instructions, startedAt: Date.now(), endedAt: 0,
    };
    for (const s of WORKFLOW_STAGES) job.stages[s.key] = "pending";
    job.stages.materials = "running";
    draftJobs.set(draftId, job);
    void (async () => {
      const ctxText = JSON.stringify(fieldValues) + "\n" + pastedCase + "\n" + materials.map((m) => m.text).join("\n");
      try {
        job.stages.materials = "done";
        job.lastTool = "归纳争议焦点";
        job.stages.analysis = "running";
        job.oc28Id = "ses_draft_" + randomUUID().slice(0, 8);
        await runtime.createSession({ sessionId: job.oc28Id, workspacePath: WORKSPACE.path, title: "文书写作：" + job.templateName, model: BRIDGE_MODEL });
        job.stages.analysis = "done";
        job.lastTool = "法条核验（检索通道未接入：引用将标注依据未核验）";
        job.stages.research = "done";
        job.stages.argumentation = "done";
        job.lastTool = "模型撰写中";
        const before = new Set((await runtime.pullTranscript(job.oc28Id)).map((e) => e.messageId));
        await runtime.send(job.oc28Id, { clientMessageId: "msg_" + randomUUID().slice(0, 8), text: prompt });
        let seen = "", stable = 0, draftingStarted = false;
        const deadline = Date.now() + 180000; // 文书生成时限 180s（与简版/改稿同档；轮询 700ms）
        while (Date.now() < deadline) {
          if (job.cancelled) { job.status = "cancelled"; job.error = "已取消"; job.endedAt = Date.now(); return; }
          await new Promise((r) => setTimeout(r, 700));
          let msgs = [];
          try { msgs = await runtime.pullTranscript(job.oc28Id); } catch { continue; }
          msgs = msgs.filter((e) => !before.has(e.messageId));
          const full = msgs.filter((e) => e.role === "assistant" && !e.error)
            .map((e) => e.text)
            .filter(Boolean).join("\n\n");
          if (full.length > seen.length) {
            seen = full; job.text = full; stable = 0;
            if (!draftingStarted) { draftingStarted = true; job.stages.drafting = "running"; } // 正文增量到达→撰写 running
            continue;
          }
          const err = [...msgs].reverse().find((e) => e.error);
          if (err && !seen) throw new Error(err.error);
          if (seen) stable++;
          if (stable >= 2) break;
        }
        // 完成结算双通道：候选一=流式累计；候选二=落库线程回捞（runtime 会话转录全量重读）
        let recovered = "";
        try {
          recovered = (await runtime.pullTranscript(job.oc28Id)).filter((e) => !before.has(e.messageId))
            .filter((e) => e.role === "assistant" && !e.error)
            .map((e) => e.text)
            .filter(Boolean).join("\n\n");
        } catch { recovered = ""; }
        const settled = settleGeneration({ streamedText: seen, recoveredText: recovered, contextText: ctxText });
        if (!settled.ok) {
          job.stages.drafting = "error";
          job.status = "error"; job.error = settled.reason; job.endedAt = Date.now();
          return;
        }
        job.text = settled.content;
        job.stages.drafting = "done";
        job.verdict = settled.verdict;
        job.notice = settled.notice;
        job.status = settled.verdict === "partial" ? "partial" : "done";
        job.endedAt = Date.now();
        try { // 历史自动写：失败不阻塞生成（E17）
          const historyId = "dh-" + Date.now();
          addDraftHistoryRecord({
            id: historyId, templateName: job.templateName, templateCategory: job.categoryLabel,
            templateSource: job.templateSource, fieldValues, materialFileNames: job.materialNames,
            instructions, generatedContent: settled.content, verdict: settled.verdict,
            model: "deepseek-chat", createdAt: Date.now(),
          });
          // 功能 #30 对拍 31/32 补齐：AI 文书保存（起草完成落历史）落 doc.ai.create；
          // detail 只落模板名/结论/字数摘要（正文不进审计）；历史写失败则不落=业务写成功才入账。
          auditWrite("doc.ai.create", historyId, {
            templateName: job.templateName, verdict: settled.verdict, chars: settled.content.length,
          });
        } catch (e) { console.error("[bridge] draft history write failed:", e?.message ?? e); }
      } catch (e) {
        for (const s of WORKFLOW_STAGES) if (job.stages[s.key] === "running") job.stages[s.key] = "error";
        job.status = "error"; job.error = String(e?.message ?? e); job.endedAt = Date.now();
        console.error("[bridge] draft generate failed:", e?.message ?? e);
      }
    })();
    return { draftId, status: "running", materialErrors };
  },
  draftStatus: async (params) => {
    const job = draftJobs.get(String(params?.draftId ?? ""));
    if (!job) throw new Error("生成任务不存在");
    return {
      draftId: job.id, status: job.status, stages: { ...job.stages }, lastTool: job.lastTool,
      materialCount: job.materialNames.length, // E7 浮窗材料数动态文案
      textLength: job.text.length, verdict: job.verdict, notice: job.notice, error: job.error,
      templateName: job.templateName, startedAt: job.startedAt, endedAt: job.endedAt,
      content: job.status === "running" ? undefined : (job.text || undefined),
    };
  },
  // 简版生成备用通道（RE-10 §2 I3）：无 agent 直调 LLM——服务端拼 prompt（模板结构截 2000 字+
  // 字段清单+粘贴案情），LLM 一次性产出；无偏好卡/无工作流/不写历史。主路径不走它。
  draftGenerateLite: async (params) => {
    if (loadSetting().stealthMode?.enabled) throw new Error("隐身模式已开启：出站通道全断，未连接任何模型。");
    const pasted = String(params?.pastedCase ?? "").slice(0, 20000);
    const fieldValues = (params?.fieldValues && typeof params.fieldValues === "object") ? params.fieldValues : {};
    let templateStructure = String(params?.templateContent ?? "").slice(0, 2000); // 模板结构截 2000 字
    if (!templateStructure && params?.hiddenDocumentType) {
      const r = resolveDocumentTemplate({ documentType: params.hiddenDocumentType, query: String(params?.hiddenQuery ?? pasted) });
      if (r.matched) templateStructure = String(r.template.content).slice(0, 2000);
    }
    if (!pasted.trim() && !templateStructure) throw new Error("简版生成需要粘贴案情或可解析的文书类型/模板");
    const fieldLines = Object.entries(fieldValues).filter(([, v]) => String(v ?? "").trim())
      .map(([k, v]) => "- " + k + "：" + String(v).slice(0, 500)).join("\n");
    const prompt = [
      "你是法律文书起草助手。直接产出完整的 Markdown 文书正文，不要任何前言或解释。",
      templateStructure ? "【模板结构参考（项目顺序为准，截前 2000 字）】\n" + templateStructure : "",
      fieldLines ? "【已填信息】\n" + fieldLines : "",
      "【案情材料】\n" + pasted,
      "材料未载明的信息以【待核实：具体事项】标注，不得虚构。"
    ].filter(Boolean).join("\n\n");
    const oc28Id = "ses_draftlite_" + randomUUID().slice(0, 8);
    await runtime.createSession({ sessionId: oc28Id, workspacePath: WORKSPACE.path, title: "简版文书生成（合成）", model: BRIDGE_MODEL });
    const before = new Set((await runtime.pullTranscript(oc28Id)).map((e) => e.messageId));
    await runtime.send(oc28Id, { clientMessageId: "msg_" + randomUUID().slice(0, 8), text: prompt });
    let seen = "", stable = 0;
    const deadline = Date.now() + 180000; // 简版 180s（I2 对齐竞品 document-generation-service 同档）
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 800));
      const msgs = (await runtime.pullTranscript(oc28Id)).filter((e) => !before.has(e.messageId));
      const full = msgs.filter((e) => e.role === "assistant" && !e.error)
        .map((e) => e.text)
        .filter(Boolean).join("\n\n");
      if (full.length > seen.length) { seen = full; stable = 0; continue; }
      const err = [...msgs].reverse().find((e) => e.error);
      if (err && !seen) throw new Error(err.error);
      if (seen) stable++;
      if (stable >= 2) break;
    }
    if (!seen.trim()) throw new Error("简版生成未在时限内完成");
    return { content: seen, model: "deepseek-chat" };
  },
  draftSteer: async (params) => {
    const job = draftJobs.get(String(params?.draftId ?? ""));
    if (!job) throw new Error("生成任务不存在");
    if (job.status !== "running") throw new Error("生成已结束，无法再发送引导");
    const text = String(params?.text ?? "").trim().slice(0, 5000);
    if (!text) throw new Error("引导内容不能为空");
    await runtime.send(job.oc28Id, { clientMessageId: "msg_" + randomUUID().slice(0, 8), text }); // 排队消息：运行中的模型回合续读
    job.lastTool = "收到中途引导";
    return { ok: true };
  },
  draftCancel: async (params) => {
    const job = draftJobs.get(String(params?.draftId ?? ""));
    if (!job) throw new Error("生成任务不存在");
    if (job.status === "running") job.cancelled = true; // 下一轮询退出（E10/E11：重生成/卸载先 abort）
    return { ok: true, status: job.status };
  },
  draftHistoryList: async () => ({
    records: listDraftHistory().map((r) => ({
      id: r.id, templateName: r.templateName, templateCategory: r.templateCategory,
      templateSource: r.templateSource, materialCount: r.materialFileNames.length,
      hasInstructions: Boolean(r.instructions), verdict: r.verdict, createdAt: r.createdAt,
    })),
  }),
  draftHistoryGet: async (params) => {
    const rec = getDraftHistory(String(params?.id ?? ""));
    if (!rec) throw new Error("历史记录不存在或已淘汰");
    return { record: rec };
  },
  draftHistoryDelete: async (params) => {
    const ok = deleteDraftHistory(String(params?.id ?? ""));
    if (!ok) throw new Error("历史记录不存在");
    auditWrite("doc.delete", String(params?.id ?? ""));
    return { ok };
  },
  draftExportWord: async (params) => {
    const markdown = String(params?.markdown ?? "");
    if (params?.templateSource === "custom") {
      const rec = getUserTemplate(String(params?.templateId ?? ""));
      if (rec?.sourceDocument) {
        const { bytes } = readTemplateSourceDocx(String(params.templateId)); // 哈希校验/缺失=硬报错（F2③）
        const docx = docxInPlaceFill(bytes, markdown); // 结构损坏四态各自 throw（I13）
        auditWrite("doc.export", String(params?.templateId ?? "unbound"), { mode: "inplace" });
        return { docxBase64: docx.toString("base64"), mode: "inplace", warning: "" };
      }
      auditWrite("doc.export", String(params?.templateId ?? "unbound"), {
        mode: "standard", warning: "custom-原文件缺失",
      });
      return { docxBase64: markdownToLegalDocx(markdown).toString("base64"), mode: "standard", warning: "未找到该模板的原 DOCX 文件，已按标准法律文书格式导出（版式可能与原模板不同）" };
    }
    auditWrite("doc.export", "unbound", { mode: "standard" });
    return { docxBase64: markdownToLegalDocx(markdown).toString("base64"), mode: "standard", warning: "" };
  },

  //    plugin-management 通道由 createPluginManagementService 包装本对象后注册（见 services 段）。
  getPluginsOverview: async () => ({
    marketplaces: [], availablePlugins: [], installedPlugins: [], restorableBuiltins: [],
    diagnostics: [], capability: { supported: false },
  }),
  resolveSuggestedPluginReference: async () => ({}),
  onDynamicPluginOperationProgress: () => silentEvent(),
  addPluginMarketplace: async () => ({ diagnostics: [] }),
  removePluginMarketplace: async () => ({ diagnostics: [] }),
  updatePluginMarketplace: async () => ({ diagnostics: [] }),
  installPlugin: async () => ({}),
  cancelPluginOperation: async () => ({}),
  uninstallPlugin: async () => ({}),
  updatePlugin: async () => ({}),
  restoreBuiltinPlugin: async () => ({}),
  configurePlugin: async () => ({}),
  resetPluginConfig: async () => ({}),
  validatePlugin: async () => ({}),
  describePlugin: async () => ({}),
  setPluginEnabled: async () => ({}),
  // ── 功能 #22 定时任务（ZCode 顶·树内开闸）：管理面走树内 AutomationService（参数映射对齐官方
  //    zcodeAgentService.ts:5136-5234）；执行面=automationDispatch/automationTick（见后）。
  //    automationService 定义在对话通道段之后（RPC 到达前已初始化，闭包引用安全）。
  listAllAutomations: () => automationService.list(),
  listAutomationRuns: (p) => automationService.listRuns(p?.automationId, p),
  createAutomation: (p) => automationService.create({
    projectId: p?.projectId ?? null,
    title: p?.title,
    cronExpr: p?.cronExpr,
    relativeDelayMinutes: p?.relativeDelayMinutes,
    prompt: p?.prompt,
    modelSelection: p?.modelSelection,
    mode: p?.mode,
    workspacePath: p?.workspacePath,
    workspaceIdentity: p?.workspaceIdentity,
    recurring: p?.recurring ?? true,
    maxRuns: p?.maxRuns,
    endAt: p?.endAt,
    scheduleRule: p?.scheduleRule,
  }),
  updateAutomation: (p) => automationService.update(p?.automationId, {
    title: p?.title, cronExpr: p?.cronExpr, prompt: p?.prompt, modelSelection: p?.modelSelection,
    mode: p?.mode, recurring: p?.recurring, maxRuns: p?.maxRuns, endAt: p?.endAt,
    scheduleRule: p?.scheduleRule, scheduleEditedByUser: p?.scheduleEditedByUser,
  }, p),
  deleteAutomation: (p) => automationService.delete(p?.automationId, p),
  setAutomationEnabled: (p) => automationService.setEnabled(p?.automationId, p?.enabled, p),
  restartAutomation: (p) => automationService.restart(p?.automationId, p),
  runAutomationNow: async (p) => {
    const claimed = await automationService.runNow(p?.automationId, p);
    if (!claimed) return { status: "duplicate" }; // single-flight 在途：UI 不得误报"已触发"
    dispatchAutomationRun(claimed.automation, claimed.run.runId, "manual", claimed.run.scheduledAt ?? null)
      .catch((e) => console.error("[bridge] automation manual dispatch:", e?.message ?? e));
    return { status: "queued" };
  },
  deleteAutomationRun: (p) => automationService.deleteRun(p?.runId, p),
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
  const workspaces = scope?.workspacePath
    ? [scope.workspaceIdentity || scope.workspacePath]
    : [...new Set([WORKSPACE_KEY, ...[...liveSessions.values()].map((s) => s.workspaceId)])];
  // 功能 #20（B50）：主对话列表隔离知识库问答线程——标题前缀过滤（功能身份=前缀，B36 同机制）。
  return workspaces.flatMap(synthSessionSummariesFor)
    .filter((s) => !isKbThreadTitle(s.title))
    .filter((s) => !isResearchThreadTitle(s.title)) // 功能 #16（B09 同款双闸）：调研线程不进主对话任务列表
    .filter((s) => s.phase !== "draft").map((s) => ({
    taskId: s.sessionId,
    traceId: "trace_" + s.sessionId,
    title: s.title,
    workspacePath: liveSessions.get(s.sessionId)?.workspacePath ?? WORKSPACE.path,
    createdAt: s.createdAt,
    updatedAt: s.lastActivityAt,
    mode: "default",
    status: s.phase === "error" ? "error" : s.phase === "running" ? "running" : "completed",
    projectId: liveSessions.has(s.sessionId) ? liveSessions.get(s.sessionId).projectId : "lvyin-demo",
    hostId: "local", pinned: false, archived: false,
  }));
}
const zcodeTaskService = new Proxy(
  {
    listTasks: async (p) => synthTaskMetas(p),
    listPinnedTaskIds: async () => [],
    listPinnedTasks: async () => [],
    listArchivedTasks: async () => [],
    listDeletedTaskIds: async () => [],
    listTaskList: async () => { const items = synthTaskMetas(); return { items, total: items.length, hasMore: false }; },
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

// ---------- M2 桥段：对话流接真后端 oc28（其余面保持合成数据） ----------
// ---------- §六.A 桥协议对齐（3.16.2 演进，行为对齐不抄码） ----------
// 依据：竞品情报/targeted-reverse/2026-10-24-zcode-3163/findings.md §六.A 六条。
// runtimeInitialization 状态机（main snapshot.ts:476 discriminatedUnion）：
//   initializing{attemptId} | ready{attemptId} | failed{attemptId, reasonCode, message}。
// 挂 conversationSnapshot 顶层（main:489 optional）。aac4755 UI 的 conversationSnapshotSchema
// 是 strip 型 z.object——桥多出的这个键会被旧 UI 剥掉不拒帧，升版后即为正式合同。
// 桥对 UI 永远报 ready（合成数据面自足，不依赖 oc28 存活）；failed 语义由
// retryInitialization 消费（resync）+ 命令门禁（guard.*）承载，诚实报状态时即用同一套。
const runtimeInitStates = new Map(); // sessionId -> {status, attemptId, reasonCode?, message?}
function runtimeInitOf(sessionId) {
  let st = runtimeInitStates.get(sessionId);
  if (!st) {
    st = { status: "ready", attemptId: randomUUID() };
    runtimeInitStates.set(sessionId, st);
  }
  return st;
}
// §六.A#4：命令门禁对齐 main v4-gateway guard 语义——桥态非 ready 明确拒收而非静默，
// reasonCode 用上游同词 guard.runtimeInitializationFailed / guard.runtimeInitializing。
function guardRuntimeCommand(sid, env) {
  const ri = runtimeInitStates.get(sid);
  if (!ri || ri.status === "ready") return null;
  const failed = ri.status === "failed";
  console.log("[bridge] command rejected by runtime guard: type=" + (env?.type ?? "") + " status=" + ri.status);
  return {
    commandId: env?.commandId ?? "cmd_" + randomUUID().slice(0, 8),
    status: "rejected",
    reasonCode: failed ? "guard.runtimeInitializationFailed" : "guard.runtimeInitializing",
    message: failed ? (ri.message || "runtime initialization failed") : "runtime initializing",
    revisionAtDecision: 1,
  };
}
// §六.A#2：subscribe/resync 入参容忍演进——白名单剥键，不拒帧（拒帧=整个会话打不开）。
// 已知新可选键（main transport.ts）：retryInitialization / additionalDirectories / historyFirst。
const SUBSCRIBE_KNOWN_KEYS = new Set([
  "topic", "base", "visibility", "connectionId", "clientMode", "workspace", "legacyTaskIds",
  "resumeThoughtLevel", "workflowRunDeltas", "sessionId", "historyFirst", "additionalDirectories",
  // workspaceRef 内联展开（agentSessionsIndexTransport:126-130 ...workspace）+ runtimePolicy
  "workspacePath", "workspaceIdentity", "remoteSessionId", "workspaceKey", "runtimePolicy",
]);
const RESYNC_KNOWN_KEYS = new Set([
  "subscriptionId", "base", "forceSnapshot", "topic", "connectionId", "retryInitialization",
  "workspacePath", "workspaceIdentity", "remoteSessionId", "workspaceKey", "runtimePolicy",
]);
function stripUnknownKeys(rawParams, known, label) {
  if (!rawParams || typeof rawParams !== "object") return rawParams;
  const unknown = Object.keys(rawParams).filter((k) => !known.has(k));
  if (unknown.length) console.log(`[bridge] ${label}: stripped unknown keys: ${unknown.join(",")}`);
  return rawParams;
}
// §六.A#5：通知类演进纪律——产帧口 op 白名单（delta.ts conversationDeltaSchema 闭集 11 op），
// 未知 op 成员剥键不整帧失败；解析侧同理（桥消费 UI 入参天然 strip，不 strict）。
const KNOWN_DELTA_OPS = new Set([
  "row.appended", "row.upserted", "row.removed", "row.delta", "state.updated",
  "pluginUi.resourceUpdated", "pluginUi.resourceListChanged", "pluginUi.instanceClosed",
  "pluginUi.appToolCall", "workflowRun.updated", "workflowRun.removed",
]);
function sanitizeDeltas(deltas) {
  if (!Array.isArray(deltas)) return deltas;
  return deltas.filter((d) => {
    if (d && KNOWN_DELTA_OPS.has(d.op)) return true;
    console.log("[bridge] delta op not in closed set, stripped:", d?.op);
    return false;
  });
}

// L1b 组合根：runtime 句柄只有 port 域面（@juscite/runtime-port）；oc28 wire 形状不出 adapter。
const runtime = createOpenCodeRuntime();
// ---------- runtime 事件流真流式（任务二，RE-B2；r12 波2.5 起经 port 域事件词表） ----------
// 设计（RE-B2 §4）：增量计算完全复用 pullTranscript diff 权威逻辑——事件到达即唤醒对账
// （首字延迟从 ≤700ms 轮询间隔降到事件即达），事件流断开则回落 700ms 轮询兜底（断线重连
// 不丢增量：Last-Event-ID 不重放已实测，断线窗由对账兜底）。BRIDGE_OC28_SSE=0 关闭事件流
// 走纯轮询（=旧行为，供首字延迟 A/B 对比；env 名为既有接线合同，不改）。
const SSE_ENABLED = process.env.BRIDGE_OC28_SSE !== "0";
const SSE_POLL_FALLBACK_MS = 700;
const sseHub = { waiters: new Set(), executionDone: new Set() };
function wakeSseWaiters() {
  for (const w of [...sseHub.waiters]) { sseHub.waiters.delete(w); w(); }
}
const sseHandle = SSE_ENABLED ? runtime.subscribeEvents((evt) => {
  if (evt.kind === "turn.succeeded" && evt.runtimeSessionId) {
    sseHub.executionDone.add(evt.runtimeSessionId);
    wakeSseWaiters();
    return;
  }
  if (evt.kind === "stream.down") return; // 断线：无唤醒 → 各 turn 自然回落轮询
  wakeSseWaiters(); // turn.text.*/turn.step.ended/turn.failed/stream.up → 对账唤醒
}, { log: (m) => console.log("[bridge] " + m) }) : null;
console.log(`[bridge] runtime 事件流(opencode): ${SSE_ENABLED ? "enabled" : "disabled (poll-only)"}`);
const conversationFrameEmitter = new Emitter();
const conversationRouteOrdinals = new Map();
// logEpoch=桥进程代次（RE-B1 §3.4⑥）：重启即换代，UI store 判 epoch 不等必走全量 snapshot，
// 恢复的 rows/seq 以快照整体替换进入投影，不存在跨代 resume。
const CONV_LOG_EPOCH = "bridge-conv-" + randomUUID().slice(0, 8);
const conversationSubscriptions = new Map();
const conversationSubTopics = new Map(); // subscriptionId -> topic（UI resync/unsubscribe 只带 subscriptionId，须反查）
const convStates = new Map();
// 模型选择=V4 真源 ModelSelection 形状（@zcode/shared model-selection）；wire 形状由 adapter 映射。
const BRIDGE_MODEL = { providerId: "deepseek-byok", modelId: "deepseek-chat" };
// ---------- 持久化（RE-B1 §3；F2：每实例一分库 bridge-{port}.db，fail-closed） ----------
const store = openBridgeStore(PORT);
// ---------- 功能 #13 法条手册单实例（RE-13 §3.2）：包首载校验 fail-closed，坏包占位不崩主壳 ----------
const lawbook = createLawbookService({ workspaceKey: WORKSPACE_KEY, store });
// ---------- 功能 #14 引证核验单实例（RE-14 §3.3）：引擎子进程一次性，包只读消费 ----------
const citationVerify = createCitationVerifyService({ workspaceKey: WORKSPACE_KEY, store });
// ---------- 【步骤4·#26】团队同步单实例（RE-26 §3 架构定位：桥机械装配，无云端） ----------
// 快照投影数据源=桥内轻量案件表（过渡态真源）：日程(case_board_events)+时间线(case_events)合成关键日期，
// 立案日期/处理结果/概要/执行款等轻量表暂无的字段置空不猜（F17/F18 缺字段置空）。
const teamSync = createTeamSync({
  store,
  loadSetting,
  saveSetting,
  auditWrite,
  projectCaseRows: () => {
    const timelineByCase = new Map();
    for (const ev of store.listCaseEventsAll()) {
      if (ev.deleted) continue;
      const list = timelineByCase.get(ev.matter_id) ?? [];
      list.push({ date: ev.date, label: String(ev.note ?? "").trim() || ev.event_type });
      timelineByCase.set(ev.matter_id, list);
    }
    const boardByCase = new Map();
    for (const b of store.listEvents()) {
      if (!b.case_id) continue;
      const list = boardByCase.get(b.case_id) ?? [];
      list.push({ date: b.date, label: b.title });
      boardByCase.set(b.case_id, list);
    }
    return store.listCases().map((row) => {
      const c = caseToProtocol(row);
      return {
        id: c.id, name: c.name, caseNo: c.caseNo, court: c.court, cause: c.cause,
        caseType: c.courtType, stage: c.workflowStatus ?? "", filingDate: "", result: "",
        amountCents: c.claimAmountCents, updatedAt: c.updatedAt,
        plaintiffs: c.plaintiffs, defendants: c.defendants, thirdParties: [],
        calendar: boardByCase.get(c.id) ?? [], timeline: timelineByCase.get(c.id) ?? [],
      };
    });
  },
});
// 功能 #29（RE-29 A1/A2）：首建→pending；旧库升级（meta 无 onboarding.status）→一次性 completed/skipped。
initOnboardingState(store.db, store.existedBeforeOpen);
console.log(`[bridge] onboarding: ${JSON.stringify(getOnboardingState(store.db))} (existedBeforeOpen=${store.existedBeforeOpen})`);
// 功能 #30（RE-30 §3.3）：审计服务单实例（密钥 fail-closed 初始化在 createAuditService 内）+
// 启动自动迁移 v1/v2→v3（幂等），计数>0 打一行日志。
const audit = createAuditService(store.db);
const auditMigrated = audit.migrateAuditChainToHmac();
if (auditMigrated > 0) console.log(`[bridge] 审计链已迁移为 HMAC 链（${auditMigrated} 行）`);
// 写入面接线（RE-30 §3.5 映射）：桥内既有功能点就地落审计行，actor=律师；
// 业务写成功才入账（审计行=已发生事实）；无对应功能的竞品动作不虚设（未落地清单见提交说明）。
function auditWrite(action, target, detail) {
  audit.appendAudit({ actor: "律师", action, target, detail: detail ?? null });
}

// 桥内机制件单实例（施工单-06）：任务壳产物目录钉死与库同分区（%APPDATA%\Juscite\bridge\artifacts，
// 红线②零外溢）；构造即崩溃扫尾（QUEUED/RUNNING 遗留→FAILED(BRIDGE_RESTART) 可重试）。
const taskShell = createTaskShell(store.db, { artifactsDir: join(dirname(store.dbPath), "artifacts") });
const flowGate = createFlowGate(store.db);

// ══ 【#21 安全层】工具策略+决策审计（RE-21 增补 §2.6/§3.2/§3.3/§3.6）══
// 决策输入从设置读（toolSecurity.shellEnabled 默认 false=关·2026-10-30 主控裁定，用户可翻；
// permissionMode 三档默认 smart）；「总是允许」审批缓存按「技能实例+签名」双维键+会话隔离+绑
// policyVersion（版本升旧批准作废；跨技能/跨通道/跨版本不继承——§3.6 定稿 2026-10-31，v2）。
// 调用面闸落点=桥回合转录观测点（runAssistantTurn 内逐工具调用过决策并落审计行——deny 也入账，
// 事件复盘要看的就是被拒的调用）；oc28 内部工具面经桥接线（施工波三轮·桥健②：adapter
// registerTools/setPermissionGate 已开放并接线——注册面预阻断见 registerG6Connector，
// runtime 权限请求经 setPermissionGate 回流本决策链；oc28 侧 config policy 仍为外闸）。
// shell 类工具在 ask/allow 之外再经宿主命令闸（host_gate，最后闸独立具名码）：即使审批通过，
// 宿主闸不过=不执行（渲染层/策略层被攻破不得扩大宿主行为面）。
const toolApprovalCaches = new Map(); // conversationId → 审批缓存（会话隔离；reset=会话切换清空）
function approvalCacheOf(conversationId) {
  let cache = toolApprovalCaches.get(conversationId);
  if (!cache) {
    cache = createApprovalCache();
    toolApprovalCaches.set(conversationId, cache);
  }
  return cache;
}
function toolSecuritySetting() {
  const ts = loadSetting().toolSecurity;
  return {
    shellEnabled: ts?.shellEnabled === true, // 默认关；不认非布尔真值
    permissionMode: PERMISSION_MODES.has(ts?.permissionMode) ? ts.permissionMode : "smart",
  };
}
// 决策+审计一条链：策略决策→ask 且缓存命中「总是允许」（绑版本）→allow→审计入账（best-effort）。
// shell 类附宿主命令闸结果（gateCommand，含 shell 开关复检——不信任本层读到的开关）。
function decideAndAuditToolCall(conversationId, runId, toolName, args, extra = {}) {
  const { shellEnabled, permissionMode } = toolSecuritySetting();
  let parsedArgs = args;
  if (typeof args === "string") {
    try { parsedArgs = JSON.parse(args); } catch { parsedArgs = args; /* 非对象就按原文摘要 */ }
  }
  const decision = decideToolCall({
    toolName, args: parsedArgs, permissionMode, shellEnabled,
    skillPermissions: Array.isArray(extra.skillPermissions) ? extra.skillPermissions : [],
    skillId: extra.skillId ?? null,
    matterId: extra.matterId ?? null,
    workspacePath: extra.workspacePath ?? WORKSPACE.path,
    enabledSourceIds: Array.isArray(extra.enabledSourceIds) ? extra.enabledSourceIds : [],
  });
  const outcome = { ...decision };
  let userDecision = null;
  // 技能实例维（§3.6 定稿）：记忆键=（技能实例,工具,参数签名）——extra.skillId
  // 即 decideToolCall 同源入参（安全层 package_id@version / catzip 名 / 空=匿名）。
  const skillKey = String(extra.skillId ?? "");
  if (decision.effect === "ask" && conversationId) {
    const cache = approvalCacheOf(conversationId);
    if (cache.check(toolName, parsedArgs, skillKey) === "allow") {
      outcome.effect = "allow"; // 用户此前「总是允许」同一技能实例同一签名（版本一致才有效；跨实例不继承）
      userDecision = "always";
    } else {
      cache.markPending(toolName, parsedArgs, { code: decision.code, reason: decision.reason }, skillKey);
    }
  }
  // 宿主命令闸（shell 类必检；对 allow/ask 都给调用方看——审批不能越过宿主闸）。
  let hostGate;
  if (/^(bash|shell\.exec|terminal\.run)$/.test(toolName)) {
    const cmdText = parsedArgs && typeof parsedArgs === "object"
      ? String(parsedArgs.command ?? parsedArgs.cmd ?? "") : String(parsedArgs ?? "");
    hostGate = gateCommand(cmdText, {
      shellEnabled,
      workspaceRoot: extra.workspacePath ?? WORKSPACE.path,
    });
    if (!hostGate.ok && outcome.effect !== "deny") {
      // 策略放行/待批但宿主闸拒绝：终局 deny（审计 code 仍为策略码闭集；宿主闸具名
      // 码随 reason 与 hostGate 字段外带，不进对话框——审批不能越过宿主闸）。
      outcome.effect = "deny";
      outcome.reason = `宿主命令闸拒绝（${hostGate.code}），即使审批通过也不执行：${outcome.reason}`;
    }
  }
  store.toolAudits.recordToolAudit({
    conversationId, runId: runId || null, toolName,
    effect: outcome.effect, code: outcome.code, reason: outcome.reason,
    policyVersion: decision.policyVersion, userDecision, args: parsedArgs,
  });
  return { ...outcome, hostGate, userDecision };
}
// ══ 【施工波三轮·桥健②】G6 连接器注册面预阻断＋runtime 权限门接线（经 port，禁绕）══
// 能力面=r12 波2.5 预留合同位 registerTools/setPermissionGate（2026-10-31 adapter 开放，
// contracts/adapter-budget.md 能力表同步）。两道闸：
//   ①注册面预阻断：注册目录装配后先过 decideToolCall——deny 的工具根本不注册（模型看不见，
//     安全层21.md:52 挂账项本笔销账），deny 也入审计账；
//   ②runtime 权限门：oc28 权限评估落 ask 时经 port 权限门回调本层决策函数——ask=无交互
//     审批面在此边界，按拒应答（fail-closed）并落审计行（事件复盘看的就是被拒的调用）。
// 真源：法条腿=RE-13 轻量包+RE-14 引擎（单一核验权威）；类案腿=legal-cn-cases lcr 公开
// Store（合成夹具种子库）。oc28 侧 config policy（integration.use mcp:* deny）仍是外闸。
const G6_CONNECTOR_SPECS = [
  {
    name: "juscite_statute_check",
    description: "法条有效性核验：把待引法条（编号+核心内容）组成一段自然语言问询，逐条核对现行有效/失效/修订替代，可指定核验时点（as_of，YYYYMMDD）。数据面=本地法条包（轻量包路线），付费与网络段为声明缺口不外推。",
    parameters: { type: "object", properties: { query: { type: "string", description: "待核验法条的自然语言问询全文" }, as_of: { type: "string", description: "核验时点 YYYYMMDD，缺省今天" } }, required: ["query"] },
  },
  {
    name: "juscite_case_search",
    description: "类案检索：按自然语言案情在案例证据卡库检索来源候选（不分级权威/普通，一律来源候选非事实），支持案由过滤与裁判日期下限（缺省 2024-07-01 后）；零命中自动去案由过滤、扩量并泛化关键词重试一次。",
    parameters: { type: "object", properties: { query: { type: "string", description: "类案检索自然语言案情" }, cause_of_action: { type: "array", items: { type: "string" }, description: "案由过滤（可多传并行提高命中）" }, return_num: { type: "integer", description: "返回条数，缺省 6" }, judge_date_after: { type: "string", description: "裁判日期下限 YYYY-MM-DD，缺省 2024-07-01" } }, required: ["query"] },
  },
];
// 连接器执行体/数据面路径解析（桥进程解析后经 env 传给 oc28 拉起的连接器子进程）。
const G6_LCR_HOME = process.env.JUSCITE_G6_LCR_HOME || "D:\\Codex\\1.法律工作区\\legal-cn-cases工作区\\legal-cn-cases";
const G6_LCR_FIXTURES = join(G6_LCR_HOME, "examples");
const G6_LCR_DB = process.env.JUSCITE_G6_LCR_DB
  || join(homedir(), "AppData", "Roaming", "Juscite", "bridge", "g6", "lcr-synth.sqlite"); // 红线②：只碰 Juscite 分区
function g6ConnectorEnv() {
  const env = {
    JUSCITE_G6_MCP_SCRIPT: fileURLToPath(new URL("g6_connector_mcp.mjs", import.meta.url)),
    JUSCITE_G6_LCR_DB,
    JUSCITE_G6_MCP_LOG: join(dirname(G6_LCR_DB), "connector-mcp.log"),
  };
  if (existsSync(G6_LCR_FIXTURES)) {
    env.JUSCITE_G6_LCR_HOME = G6_LCR_HOME;
    env.JUSCITE_G6_LCR_FIXTURES = G6_LCR_FIXTURES;
  }
  const engine = resolveCitationEnginePath();
  if (engine) env.BRIDGE_CITATION_ENGINE = engine;
  const packDir = resolveCitationPackDir();
  if (packDir) env.BRIDGE_CITATION_PACK_DIR = packDir;
  return env;
}
// ②runtime 权限门：域请求→安全层决策（同一 decideAndAuditToolCall 链，deny/ask 均审计入账）。
// oc28 的 MCP 工具 action 名=命名空间(server)_工具名（juscite_g6_<tool>）——桥侧先去命名空间
// 还原域词再进决策函数（wire 命名知识不进 tool_policy 纯函数）。
runtime.setPermissionGate((request) => {
  const domainTool = request.tool.startsWith("juscite_g6_") ? request.tool.slice("juscite_g6_".length) : request.tool;
  const outcome = decideAndAuditToolCall("", null, domainTool, {}, {
    workspacePath: WORKSPACE.path,
  });
  console.log(`[bridge][g6-gate] runtime 权限请求 tool=${request.tool}（域词 ${domainTool}） summary=${JSON.stringify(request.summary)} → ${outcome.effect}(${outcome.code})`);
  return outcome.effect === "allow";
});
// ①注册面预阻断+经 port 注册（失败具名不拖垮桥启动：其余桥功能不依赖连接器在册）。
async function registerG6Connector() {
  const { shellEnabled, permissionMode } = toolSecuritySetting();
  const allowed = [];
  for (const spec of G6_CONNECTOR_SPECS) {
    const decision = decideToolCall({ toolName: spec.name, args: {}, permissionMode, shellEnabled });
    if (decision.effect === "deny") {
      store.toolAudits.recordToolAudit({
        conversationId: "", runId: null, toolName: spec.name,
        effect: "deny", code: decision.code, reason: `注册面预阻断：${decision.reason}`,
        policyVersion: decision.policyVersion, userDecision: null, args: {},
      });
      console.log(`[bridge][g6] 注册面预阻断 ${spec.name}（${decision.code}）——不注册，模型不可见`);
      continue;
    }
    allowed.push(spec);
  }
  Object.assign(process.env, g6ConnectorEnv()); // adapter registerTools 从 env 组装挂载配置
  await runtime.registerTools(allowed);
  console.log(`[bridge][g6] 连接器工具经 port 注册进 oc28 运行时：${allowed.map((s) => s.name).join(",")}`);
}

// 功能 #6 材料上传解析（RE-6 §3）：材料管道+案件材料面+对话附件库单实例。
// 四件套/附件落 %APPDATA%\Juscite\bridge\cases\（与库同分区，红线②：只碰 Juscite 域，材料不出域）；
// case_id 归属走 MatterLite 案件表（过渡态同 0005 注：MatterStore 解挂后翻牌真源随迁）；
// 本地鉴权挂点=local-auth.token（对拍 56：存在即强制 x-juscite-token，无凭据 401）。
const materials = createMaterialService({
  dao: store.materials,
  caseExists: (caseId) => Boolean(store.getCase(caseId)),
  root: join(dirname(store.dbPath), "cases"),
  workspaceKey: WORKSPACE_KEY,
  authFilePath: join(dirname(store.dbPath), "local-auth.token"),
  log: (msg) => console.log(`[bridge][materials] ${msg}`),
  auditWrite, // RE-30 §3.5：材料域写入面（file.upload/file.parse）接线——同一 audit 单实例（对拍 52），业务成功才入账
});

// 功能 #42 电子数据取证（RE-42 §3.2 状态机）：进场→锚/行索引→归类→候选清单→校验→审查标注。
// 本地工件落 %APPDATA%\Juscite\bridge\cases\<case>\edisc\（红线②：只碰 Juscite 域，原件只读 G1）；
// 鉴权挂点同材料面（local-auth.token 存在即强制）；审计走同一 audit 单实例（登记/归类/清单/确认/更正入账）。
const edisc = createEdiscService({
  dao: store.edisc,
  caseExists: (caseId) => Boolean(store.getCase(caseId)),
  root: join(dirname(store.dbPath), "cases"),
  workspaceKey: WORKSPACE_KEY,
  authFilePath: join(dirname(store.dbPath), "local-auth.token"),
  log: (msg) => console.log(`[bridge][edisc] ${msg}`),
  auditWrite,
});

// 功能 #32 整理与尽调（RE-32 §3 承载=MatterLite 案件面扩展）：看板/台账/清单/沿革四分面单实例。
// 台账与沿革的底稿来源=#6 材料表只读消费（PDF 文本层重放+分块代位，页/序/坐标四元组口径）；
// 批量提取挂 r11 异步任务壳（taskShell 同实例）；LLM 路注入缺省 null=fail-closed 不编造（真模型接线挂后续集成单）；
// 鉴权挂点同材料面；RE-30 §3.5 映射表无尽调域动作行，审计不新增类别（同 #36 先例记档）。
const diligence = createDiligenceService({
  dao: store.diligence,
  caseExists: (caseId) => Boolean(store.getCase(caseId)),
  workspaceKey: WORKSPACE_KEY,
  authFilePath: join(dirname(store.dbPath), "local-auth.token"),
  taskShell,
  llmExtract: null,
  log: (msg) => console.log(`[bridge][diligence] ${msg}`),
});

function convStateOf(sessionId) {
  let st = convStates.get(sessionId);
  if (!st) {
    st = { rowSeq: { n: 0 }, oc28Id: null, turn: 0, busy: false, rows: [], seq: 0, phase: "draft", lastError: null,
      lastCommandId: null, oc28SeenIds: [], attachmentIds: [] }; // 持久化扩展字段（RE-B1 §3.2/§3.3；attachmentIds=#6 对话附件跨回合继承）
    convStates.set(sessionId, st);
  }
  return st;
}

// 会话态落库（索引+水位+busy+lastCommandId；summary 缺席=draft 瞬态，不持久化）
function persistSessionState(sid) {
  const st = convStates.get(sid);
  const summary = liveSessions.get(sid);
  if (!st || !summary) return;
  store.upsertSession({
    workspace_key: summary.workspaceId, session_id: sid,
    oc28_id: st.oc28Id, title: summary.title ?? "", project_id: summary.projectId ?? null,
    workspace_path: summary.workspacePath ?? WORKSPACE.path,
    last_outcome: summary.lastOutcome ?? null, phase: st.phase,
    seq: st.seq, row_seq: st.rowSeq.n, busy: st.busy ? 1 : 0,
    last_command_id: st.lastCommandId ?? null,
    meta_json: JSON.stringify({ oc28SeenIds: st.oc28SeenIds ?? [], lastError: st.lastError ?? null, kbCtx: st.kbCtx ?? null, attachmentIds: st.attachmentIds ?? [] }),
    created_at: summary.createdAt, updated_at: summary.lastActivityAt ?? Date.now(),
  });
}
// 行落库：整行对象入 row_json（F4 字段零丢失：rowId/turnId/createdAt/createdAtSeq/actions/…）
function persistRow(sid, row) {
  const summary = liveSessions.get(sid);
  if (!summary || !row) return;
  store.upsertRow({
    workspace_key: summary.workspaceId, session_id: sid, row_seq: row.rowId,
    kind: row.kind ?? "", state: row.state ?? "", text: row.text ?? "",
    source_command_id: row.sourceCommandId ?? null, row_json: JSON.stringify(row),
  });
  // 功能 #15：完成行进案内全文索引（userInput 直入；assistantText 仅 complete——
  // streaming 中间态不入，与 LegalWork latest_only 版本收敛语义同向，RE-15 §2）
  if (row.kind === "userInput" || (row.kind === "assistantText" && row.state === "complete")) {
    store.upsertDocumentChunk({
      chunk_id: String(row.rowId), workspace_key: summary.workspaceId, session_id: sid,
      source_label: `${row.kind === "userInput" ? "用户输入" : "助手回复"} · ${new Date(row.createdAt ?? Date.now()).toLocaleString("zh-CN")}`,
      kind: row.kind, created_at: row.createdAt ?? Date.now(), text: row.text ?? "",
    });
  }
}
// 回执落库：仅终态（turn completed/failed 后）调用；accept 态只存进程内（F1①）。
// 同时写入进程内回执缓存：结算补记的终态回执必须当场可见，否则同代内重放会 miss 缓存重执行。
function persistReceipt(sid, commandId, ack, outcome) {
  const summary = liveSessions.get(sid);
  if (!summary || !commandId || !ack) return;
  store.putReceipt({
    workspace_key: summary.workspaceId, command_id: commandId, session_id: sid,
    ack_json: JSON.stringify(ack), outcome, created_at: Date.now(),
  });
  commandReceipts.set(JSON.stringify([`sessions-index/${summary.workspaceId}`, sid, commandId]), Promise.resolve(ack));
}
function emitConvFrame(topic, payload, delivery = "online", targetSubscriptionId) {
  // 快照与增量共用权威 rows/seq，流中重订阅也能立即恢复，不再等待模型结束。
  const subs = conversationSubscriptions.get(topic) ?? new Set();
  const safePayload = payload.kind === "deltas" ? { ...payload, deltas: sanitizeDeltas(payload.deltas) } : payload;
  const seqSt = convStateOf(topic.startsWith("conversation/") ? topic.slice("conversation/".length) : "draft");
  const frameFrom = seqSt.seq;
  const frameTo = payload.kind === "deltas" ? seqSt.seq + safePayload.deltas.length : seqSt.seq;
  seqSt.seq = frameTo;
  for (const subscriptionId of subs) {
    if (targetSubscriptionId && subscriptionId !== targetSubscriptionId) continue;
    const routeKey = topic + "\0" + subscriptionId;
    const ordinal = (conversationRouteOrdinals.get(routeKey) ?? 0) + 1;
    conversationRouteOrdinals.set(routeKey, ordinal);
    // 2026-10-26 水位修复：逻辑帧 fromSeq/toSeq = 会话权威 seq（UI 规则：delta.fromSeq 必须等于
    // 投影当前 seq；此前硬编码 wire ordinal 造成首 delta 即"断档"死循环，快照 seq/rows 恒空加剧）。
    const frame = { topic, subscriptionId, fromSeq: frameFrom, toSeq: frameTo, sentAt: Date.now(), payload: safePayload };
    console.log("[bridge] firing conv frame, listeners=" + conversationFrameEmitter.listeners?.size); conversationFrameEmitter.fire({
      wireVersion: 3, kind: "complete", deliveryKind: delivery,
      logicalFrameId: "lframe_" + randomUUID().slice(0, 8),
      logicalFrameOrdinal: ordinal, topic, subscriptionId, frame,
    });
  }
  console.log("[bridge] conv frame:", topic, payload.kind, "seq", frameFrom, "->", frameTo);
}
function baseRow(st, turnId, pti, actions) {
  // pti = productTurnId（功能#27）：分享预检/投影的轮次权威身份；同轮各行共用一个。
  // 旧路径（隐身拒绝行等）不传 pti → 无轮次身份，不进分享面板（诚实：未产出的内容不可分享）。
  // entityId（功能#23）：canonical 行身份——forkAssistant/editUserQuery 的 target 定位与
  // UI 分支入口渲染（ConversationRowView:1627 `onFork && entityId`）都依赖它。
  return { rowId: ++st.rowSeq.n, turnId, ...(pti ? { productTurnId: pti } : {}), entityId: "ent_" + randomUUID().slice(0, 8), createdAt: Date.now(), createdAtSeq: 0, actions: actions ?? {} };
}
// 功能#23：fork 出口只挂最新稳定 assistant 行（CLI stable resolver 语义：Command forkAssistant
// “running 时对稳定 assistant row 可用”；TurnGroup 也只在 latestAssistantTextRow 渲染 fork 入口）。
// 上一持行降级（落库+upsert 帧），新行置 canFork；失败行永不获得（state 恒非 complete）。
function demotePrevForkTarget(sid, newRow) {
  // 旧行降级但不在此处发帧：complete 行的重复 upsert 若先于本轮完成帧出现，
  // 会被按「首个 complete upsert=本轮终态」消费的端（e2e separateTurns/sseDrop、
  // 转发类消费者）拿成上一轮文本——降级帧由 runAssistantTurn 在终态序列之后补发。
  const st = convStateOf(sid);
  const prev = st.rows.find((r) => r !== newRow && r.kind === "assistantText" && r.state === "complete" && r.actions?.canFork === true);
  if (!prev) return null;
  prev.actions = {};
  return prev;
}
// 【施工波三轮·#7 证据目录全量面】交付链收尾（RE-7 §3 流程"交付"段；对拍 22/23/23a 桥面）：
// ①assistant 回复文本+工具事件入参两路提取文件路径（扩展名字母开头拒日期假扩展名、拒裸域名）；
// ②双层过滤（内部过程文件硬过滤两路径同裁；草稿/脚本启发式——assistant 路径全 draft 回退、
// 工具路径无回退）；③版本族去重（后缀剥除 stem::ext 折叠、跨扩展名不折叠）；④在盘文件读字节
// 落对话附件库 producer=agent（"对话文件"浮层 Agent 产出组；附件 MIME 白名单外（如 xlsx，
// #6 面收窄）与不在盘路径如实跳过不伪造）；⑤D4① docx 唯一产物免复述轮——本回合恰好只请求
// docx 一个产物且有工具面成功交付、而回复未报路径时，本地直出确定性落点话术（不经模型复述）。
// 全部 best-effort，失败只落日志不阻塞已交付回合（同交付锚点机检先例）。
const DELIVERY_AGENT_MIME_BY_EXT = new Map([
  [".pdf", "application/pdf"],
  [".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
  [".txt", "text/plain"], [".md", "text/markdown"], [".csv", "text/csv"], [".json", "application/json"],
  [".png", "image/png"], [".jpg", "image/jpeg"], [".jpeg", "image/jpeg"],
  [".webp", "image/webp"], [".gif", "image/gif"], [".bmp", "image/bmp"],
]);
function resolveDeliveryFile(p) {
  try {
    if (existsSync(p)) return p;
    const rel = join(WORKSPACE.path, String(p).replace(/^([A-Za-z]:)?[\\/]/, ""));
    if (existsSync(rel)) return rel;
  } catch { /* 路径解析失败按不在盘处理 */ }
  return null;
}
function registerTurnDeliveries({ sid, st, topic, turnId, pti, userText, assistantText, toolPaths }) {
  const candidates = [
    ...extractDeliveredPaths(String(assistantText ?? "")).map((p) => ({ path: p, source: "assistant" })),
    ...(toolPaths ?? []).map((p) => ({ path: p, source: "tool" })),
  ];
  const filtered = filterDeliveries(candidates);
  const deduped = dedupeVersionFamily(filtered.map((c) => ({ filename: c.path.split(/[\\/]/).pop(), producer: "agent", source: c.source })));
  const registered = [];
  for (const item of deduped) {
    const ext = (item.filename.match(/\.[A-Za-z0-9]+$/) ?? [""])[0].toLowerCase();
    const mime = DELIVERY_AGENT_MIME_BY_EXT.get(ext);
    if (!mime) { console.log("[bridge] delivery skip (mime whitelist):", item.filename); continue; }
    const file = resolveDeliveryFile(filtered.find((c) => c.path.split(/[\\/]/).pop() === item.filename)?.path ?? item.filename);
    if (!file) { console.log("[bridge] delivery skip (not on disk):", item.filename); continue; }
    try {
      const bytes = readFileSync(file);
      materials.putAttachment({ bytes, filename: item.filename, mimeType: mime, threadIds: [sid], producer: "agent" });
      registered.push({ filename: item.filename, path: file });
      console.log("[bridge] delivery registered (agent):", item.filename);
    } catch (e) { console.log("[bridge] delivery register failed:", item.filename, e?.message ?? e); }
  }
  // D4①：docx 唯一产物免复述轮（确定性落点话术本地直出，回复已含路径则不重复）
  const toolDocx = (toolPaths ?? []).filter((p) => /\.docx$/i.test(p));
  if (toolDocx.length > 0) {
    const msg = completedWordDeliveryMessage({
      requestedArtifacts: requestedArtifactKinds(String(userText ?? "")).map((kind) => ({ kind })),
      deliveries: toolDocx.map((p) => ({ path: p, status: "ok", kind: "docx" })),
    });
    if (msg && !String(assistantText ?? "").includes(toolDocx[toolDocx.length - 1])) {
      const deliverRow = { ...baseRow(st, turnId, pti), kind: "assistantText", text: msg, state: "complete", model: "delivery-local" };
      st.rows.push(deliverRow);
      persistRow(sid, deliverRow);
      emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.appended", row: deliverRow }] });
      console.log("[bridge] delivery short-circuit (docx-only):", toolDocx[toolDocx.length - 1]);
    }
  }
  return registered;
}

// 功能#23：assistant 回合执行体从 sendText 分支抽出——sendText（新建轮）与 editUserQuery
// （回退重生成）共用同一条 oc28 回合链（投影/落库/回执/隐身语义零分叉）。
function runAssistantTurn(sid, ack, turnId, pti, turnHeaderRow, text, opts) {
  const topic = `conversation/${sid}`;
  const st = convStateOf(sid);
  const summary = liveSessions.get(sid);
  let asstRow;
  (async () => {
    try {
      console.log("[bridge] turn: begin sid=" + sid);
      st.busy = true;
      if (!st.oc28Id) {
        st.oc28Id = "ses_oc28_" + randomUUID().slice(0, 8);
        console.log("[bridge] turn: creating runtime session " + st.oc28Id);
        await runtime.createSession({ sessionId: st.oc28Id, workspacePath: summary?.workspacePath ?? WORKSPACE.path,
          title: opts?.learningThread ? "学习迭代（合成）" : opts?.researchThread ? "调研报告（合成）" : opts?.kbThread ? "知识库问答（合成）" : "律引导航桥（合成）",
          model: opts?.model ?? BRIDGE_MODEL });
        console.log("[bridge] turn: runtime session created");
      }
      persistSessionState(sid); // oc28Id/busy 已定：mid-turn 崩溃结算的凭据（F3）
      asstRow = { ...baseRow(st, turnId, pti), kind: "assistantText", text: "", state: "streaming",
        model: (opts?.model ?? BRIDGE_MODEL).modelId,
        // 功能 #20（B39 数据驱动面）：assistant 消息里非 text part（reasoning/thinking 等）投到
        // row.reasoning（当前 deepseek-chat 实测只有 text part，探针 PART_TYPES=[["text"]]——
        // 字段恒缺省不伪造；选到 reasoner 模型时该面自然点亮，UI 按行内 reasoning 渲染）。
        ...(opts?.kbThread || opts?.researchThread ? { reasoning: "" } : {}) };
      st.rows.push(asstRow);
      emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.appended", row: asstRow }] });
      const previousMessageIds = new Set((await runtime.pullTranscript(st.oc28Id)).map((e) => e.messageId));
      sseHub.executionDone.delete(st.oc28Id); // 上一轮的 succeeded 残留不得当作本轮完成信号
      // 【#18 I1/I2】记忆检索注入（对拍 70 等量：注入进对话提示词；id 落 row 供对账）：
      // kb/调研/学习线程不注入（I2——kb 自带提示词结构，学习线程自带指令）。
      let outboundText = text;
      if (!opts?.kbThread && !opts?.researchThread && !opts?.learningThread) {
        try {
          if (learningRuntime && learningRuntime.injectionAllowed(summary?.title ?? "")) {
            const plan = learningRuntime.injectionPlan(text);
            if (plan.block) {
              outboundText = plan.block + "\n\n" + text;
              asstRow.injectedMemoryIds = plan.injectedIds;
            }
          }
        } catch { /* 注入失败不阻塞对话 */ }
        // 【#36 分层记忆注入】（RE-36 §3 注入：对话上下文按层装配，项目约定优先于个人偏好；
        // 会话绑定项目才有项目层，偏好用户级跨案跟随；类型偏好>通用偏好；缺失静默跳过 F15；
        // 块尾部追加不改前缀缓存友好，同 #6 材料注入先例；注入失败不阻塞对话。）
        try {
          if (layeredMemory) {
            const plan36 = layeredMemory.injectionPlan({
              projectId: summary?.projectId ?? null,
              turnText: text,
            });
            if (plan36.block) {
              outboundText = outboundText + "\n\n" + plan36.block;
              asstRow.injectedMemoryLayerKeys = plan36.usedKeys;
            }
          }
        } catch { /* 注入失败不阻塞对话 */ }
        // 【#6 对话材料注入】（RE-6 §3 上下文注入；对拍 11/12/13/14/16）：会话全部历史附件
        // 跨回合继承（st.attachmentIds），抽取按 id+指纹缓存（materials 服务内）；默认"地图"
        // 策略块绑定本 user_message 尾部追加（不改前缀，缓存友好）；注入失败不阻塞对话。
        try {
          const ctxBlock = materials.attachmentContextBlock(st.attachmentIds ?? []);
          if (ctxBlock) {
            outboundText = outboundText + "\n\n" + ctxBlock;
            asstRow.attachedMaterialIds = [...(st.attachmentIds ?? [])];
          }
        } catch { /* 注入失败不阻塞对话 */ }
        // 【施工波三轮·#7 证据目录全量面】技能指令注入（RE-7 §3 技能类附加；对拍 1~8/1a）：
        // 激活四通道（explicit 1000+/command startsWith 900/pattern 500/fileType 300——fileType 来源=
        // 会话附件文件名+消息内扩展名扫描）→排序（explicit→native→分值→id 字典序）→上限 3→
        // 预算 24000 字节静默跳过；注入块置于全部上下文块之后（history 后易变段，前缀缓存友好）；
        // kb/调研/学习线程不注入（A9 知识库问答线程技能解析整体短路；调研/学习线程自带指令结构）。
        // 注入 id 落 row 供对账（同记忆注入先例）；注入失败不阻塞对话。
        try {
          const skillPlan = planTurnSkills({
            text,
            attachmentFilenames: materials.attachmentFilenamesOf(st.attachmentIds ?? []),
            threadKind: opts?.kbThread ? "knowledge-qa" : "conversation",
          });
          if (skillPlan.block) {
            outboundText = outboundText + "\n\n" + skillPlan.block;
            asstRow.injectedSkillIds = skillPlan.activations.map((a) => a.skill.id);
            if (skillPlan.skippedOverBudget.length) {
              console.log("[bridge] turn: skills over budget skipped:", skillPlan.skippedOverBudget.map((a) => a.skill.id).join(","));
            }
          }
        } catch { /* 注入失败不阻塞对话 */ }
      }
      console.log("[bridge] turn: prompting runtime (" + text.slice(0, 30) + "...)");
      await runtime.send(st.oc28Id, { clientMessageId: "msg_" + randomUUID().slice(0, 8), text: outboundText });
      console.log("[bridge] turn: prompt submitted");
      let seen = "", stable = 0;
      let newAssistantIds = []; // 本轮新投影的 oc28 assistant 消息 id（持久化去重凭据，RE-B1 §3.5）
      const auditedToolCallKeys = new Set(); // 【#21 安全层】本轮已过决策审计的工具调用键（消息 id#序，去重）
      const turnToolPaths = []; // 【施工波三轮·#7】本轮工具事件里的文档类产物路径（交付链工具路径候选，去重）
      const deadline = Date.now() + 150000;
      while (Date.now() < deadline) {
        // 事件流唤醒即对账（真流式）；事件流断开时无唤醒 → 700ms 轮询兜底（断线重连不丢增量）
        await new Promise((res) => {
          const w = () => { sseHub.waiters.delete(w); clearTimeout(tid); res(); };
          const tid = setTimeout(() => { sseHub.waiters.delete(w); res(); }, SSE_POLL_FALLBACK_MS);
          sseHub.waiters.add(w);
        });
        // runtime 转录序与新旧无关；只投影本次 send 后新增的条目，按 createdAt 排序。
        const msgs = (await runtime.pullTranscript(st.oc28Id))
          .filter((e) => !previousMessageIds.has(e.messageId))
          .sort((a, b) => a.createdAt - b.createdAt);
        // 2026-10-25 真机实测：模型可能先发 tool-calls 轮（assistant、空文本）再发正文轮——
        // 只看"最后一条 assistant"会抓到空文本轮漏掉真回复（replyLen=0 转圈根因）。拼接全部无错
        // assistant 文本；完成判定取最后一条非空文本条目的 completedAt。
        const assistantMsgs = msgs.filter((e) => e.role === "assistant" && !e.error);
        // 【#21 安全层】调用面闸（RE-21 增补 §3.2 双点·调用点）：本轮转录里新增的模型工具调用
        // 逐条过工具策略并落决策审计（deny 也入账——只记成功调用会让被拒调用隐形）。审计
        // best-effort 不阻塞回合；oc28 内部执行不经桥（预阻断随 runtime 权限门开放，见装配处注）。
        try {
          for (const e of assistantMsgs) {
            if (!Array.isArray(e.toolCalls)) continue;
            e.toolCalls.forEach((tc, i) => {
              const key = e.messageId + "#" + i;
              if (auditedToolCallKeys.has(key)) return;
              auditedToolCallKeys.add(key);
              decideAndAuditToolCall(sid, turnId, String(tc?.name ?? ""), tc?.input, {
                workspacePath: summary?.workspacePath ?? WORKSPACE.path,
              });
              // 【施工波三轮·#7】工具事件交付候选（D3 工具路径）：文档生成类工具的入参里出现的
              // 文件路径记为本轮工具面候选（读取类工具名不收，防输入件误记为产出）。
              if (/evidencecat|document_skill|draft|docx|export|generate|merge|convert/i.test(String(tc?.name ?? ""))) {
                try {
                  for (const p of extractDeliveredPaths(JSON.stringify(tc?.input ?? {}))) {
                    if (!turnToolPaths.includes(p)) turnToolPaths.push(p);
                  }
                } catch { /* 候选提取失败忽略 */ }
              }
            });
          }
        } catch { /* 决策/审计失败不阻塞回合（best-effort） */ }
        newAssistantIds = assistantMsgs.map((e) => e.messageId);
        const full = assistantMsgs
          .map((e) => e.text)
          .filter(Boolean)
          .join("\n\n");
        const last = [...assistantMsgs].reverse().find((e) => e.text);
        // KB 线程（B39）：推理面/工具步已由 adapter 归一进 entry（reasoning/toolCalls），
        // 增量随 upsert 帧走；无此类面时保持空串/不加键（不伪造思考面）。
        if (opts?.kbThread || opts?.researchThread) {
          // 工具步骤捕获（B15）：步骤只追加（B28 目录漂移语义：增长仅进信息面，不判失败）
          const toolCallsFull = assistantMsgs.flatMap((e) => e.toolCalls ?? []);
          if (toolCallsFull.length !== (asstRow.toolCalls ?? []).length) {
            asstRow.toolCalls = toolCallsFull;
          }
          const reasoningFull = assistantMsgs
            .map((e) => e.reasoning ?? "")
            .filter(Boolean)
            .join("\n\n");
          if (reasoningFull && reasoningFull.length > (asstRow.reasoning ?? "").length) {
            asstRow.reasoning = reasoningFull;
            emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.delta", rowId: asstRow.rowId, path: "reasoning", append: reasoningFull.slice((asstRow.reasoning ?? "").length) }] });
          }
        }
        if (full.length > seen.length) {
          asstRow.text = full;
          emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.delta", rowId: asstRow.rowId, path: "text", append: full.slice(seen.length) }] });
          seen = full; stable = 0;
        } else if (seen && last?.completedAt) { stable++; if (stable >= 2) break; }
        // 事件流完成信号：turn.succeeded 已达本轮会话 → 权威全文（text.ended 含全文）已投影，立即收口
        if (seen && sseHub.executionDone.has(st.oc28Id)) { stable = 2; break; }
        const err = [...msgs].reverse().find((e) => e.error);
        if (err && !seen) {
          throw new Error(err.error);
        }
      }
      if (!seen || stable < 2) throw new Error("模型回复未在时限内完成");
      st.phase = "completedSuccess";
      console.log("[bridge] turn: complete, replyLen=" + seen.length);
      Object.assign(asstRow, { text: seen, state: "complete" });
      asstRow.actions = { canFork: true }; // 功能#23：fork 出口移交到本轮稳定行（完成帧即带入口）
      const demoted = demotePrevForkTarget(sid, asstRow);
      emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.upserted", row: asstRow }] });
      Object.assign(turnHeaderRow, { state: "completedSuccess", endedAt: Date.now() });
      persistRow(sid, turnHeaderRow);
      emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.upserted", row: turnHeaderRow }] });
      // 终态落库：行+水位+oc28 幂等凭据+终态回执（F1①：只有终态回执进 SQLite）
      st.oc28SeenIds = [...(st.oc28SeenIds ?? []), ...newAssistantIds];
      persistRow(sid, asstRow);
      persistReceipt(sid, ack.commandId, ack, "completed");
      persistSessionState(sid);
      // 旧行降级帧收尾（功能#23）：位于本轮终态序列之后，不抢占「首个 complete upsert」位置
      if (demoted) {
        persistRow(sid, demoted);
        emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.upserted", row: demoted }] });
      }
      // 功能#10 H8：对话内文书交付锚点终稿机检（RE-10 §2）——逐项报结果（未过项点名），本地信息行
      // 落账（同 F1 指路行形态：不进 oc28、不占终态回执）；机检抛错不阻塞已交付回合。
      if (opts?.deliveryAnchors) {
        try {
          const checks = validateDeliveryContent(seen, opts.deliveryAnchors);
          const okN = checks.filter((c) => c.ok).length;
          const report = "【交付锚点机检】共 " + checks.length + " 项：" + okN + " 项通过" + (okN < checks.length ? "，" + (checks.length - okN) + " 项未过（修订后可重新交付）：" : "。") + "\n" +
            checks.map((c) => (c.ok ? "✓ " : "✗ ") + c.label + (c.detail ? "（" + c.detail + "）" : "")).join("\n");
          const checkRow = { ...baseRow(st, turnId, pti), kind: "assistantText", text: report, state: "complete", model: "draft-anchor-check" };
          st.rows.push(checkRow);
          persistRow(sid, checkRow);
          emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.appended", row: checkRow }] });
          console.log("[bridge] delivery anchor check: " + okN + "/" + checks.length + " pass sid=" + sid);
        } catch (e) { console.error("[bridge] delivery anchor check failed:", e?.message ?? e); }
      }
      // 【施工波三轮·#7 证据目录全量面】交付链收尾（D1 提取/D3 双层过滤/D5 版本族去重/agent 落账/
      // D4① docx 唯一产物免复述轮）：best-effort，失败不阻塞已交付回合。
      try {
        registerTurnDeliveries({ sid, st, topic, turnId, pti, userText: text, assistantText: seen, toolPaths: turnToolPaths });
      } catch (e) { console.error("[bridge] delivery chain failed:", e?.message ?? e); }
    } catch (e) {
      st.phase = "error";
      st.lastError = { code: "bridge.turnFailed", message: e?.message ?? String(e), recoverable: true, at: Date.now(), source: "provider" };
      if (asstRow) {
        Object.assign(asstRow, { text: asstRow.text || st.lastError.message, state: "failed" });
        emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.upserted", row: asstRow }] });
        persistRow(sid, asstRow);
      }
      if (turnHeaderRow) {
        Object.assign(turnHeaderRow, { state: "failed", endedAt: Date.now() });
        persistRow(sid, turnHeaderRow);
        emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.upserted", row: turnHeaderRow }] });
      }
      persistReceipt(sid, ack.commandId, ack, "failed"); // 终态（failed）回执：重放得显式失败，不再静默吞命令（F1）
      persistSessionState(sid);
      console.error("[bridge] turn error:", e?.message ?? e);
    } finally {
      st.busy = false;
      emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "state.updated", patch: { control: buildConvSnapshot(sid).control } }] });
      persistSessionState(sid); // 在最后一帧发射后落库：seq 水位与快照口径一致（否则恢复差 1）
      if (summary) {
        Object.assign(summary, { phase: st.phase, sessionEnded: st.phase === "completedSuccess", lastOutcome: st.phase === "error" ? "error" : "completed", lastActivityAt: Date.now() });
        emitSessionsIndexDeltaFrame(`sessions-index/${summary.workspaceId}`, [{ op: "session.upserted", session: summary }]);
      }
    }
  })();
}

// ── #16 调研回合链（B24 有界续跑 ≤5 + 终态判定；主循环护轨的轻量期等量）──
// 首跳=五要素模板（B11）；续跳=阶段指令（B25：不重复规划/不扩张/直接交付完整报告/标注局限继续）。
// 报告完整性由共享纯模型 isReportComplete 单源判定（trim≥300+节名≥4/5，B24）；每跳全量复用 M4
// runAssistantTurn（oc28 流式/投影/落库/崩溃结算）。停止/删除即不再续跳（B37/B44）；每跳落账
// 流中投影（B08 模型规划流出后替换即时规划）；B33 无可展示内容落专属错误文案；B34 部分内容+
// 错误→done 保留部分。工具证据门/目录剔除的判定器随共享模型就位（evidenceGate/cullToolCatalog），
// 接入点=检索工具循环落地时（当前桥回合链无工具事件源，判定器已合成自测）。
async function runResearchTurnChain(rec, threadId, firstPrompt, model) {
  const st = convStateOf(threadId);
  let prompt = firstPrompt;
  // B26 配额切兜底旗标 + B30 三类续跑计数（各 ≤2）+ 增量基线（B22/B23 判定输入）
  let quotaFallback = false;
  const continuationCounts = { reasoning_only: 0, no_tool: 0, announce_no_call: 0 };
  let prevText = "";
  let prevReasoning = "";
  let prevToolCount = 0;
  try {
    for (let attempt = 0; attempt <= MAX_REPORT_CONTINUATIONS; attempt++) {
      if (researchCancelled.has(rec.id)) return; // B37/B44：停止/删除后不再续跳
      const ack = { commandId: "cmd_" + randomUUID().slice(0, 8), status: "accepted", revisionAtDecision: 1 };
      const turnId = "turn_" + randomUUID().slice(0, 8);
      const pti = "pt_" + randomUUID().slice(0, 8);
      const userRow = { ...baseRow(st, turnId, pti, { canEdit: false }), kind: "userInput", origin: "realUser",
        text: prompt, sourceCommandId: ack.commandId };
      st.rows.push(userRow);
      persistRow(threadId, userRow);
      const summary = liveSessions.get(threadId);
      if (summary) { summary.phase = "running"; summary.lastActivityAt = Date.now(); }
      st.phase = "running";
      st.lastError = null;
      st.lastCommandId = ack.commandId;
      st.lastPrompt = prompt; // 诊断/测试面（内存态，不入库）
      persistSessionState(threadId);
      const turnHeaderRow = { ...baseRow(st, turnId, pti), kind: "turnHeader", origin: "userInput",
        executionKind: "agent", state: "running", startedAt: Date.now() };
      st.rows.push(turnHeaderRow);
      persistRow(threadId, turnHeaderRow);
      runAssistantTurn(threadId, ack, turnId, pti, turnHeaderRow, prompt, { model, researchThread: true });
      // 等本跳收口（runAssistantTurn finally 释放 busy）；超时熔断不无限等
      const hopDeadline = Date.now() + RESEARCH_CHAIN_TIMEOUT_MS;
      while (st.busy && Date.now() < hopDeadline) await researchSleep(RESEARCH_CHAIN_POLL_MS);
      if (researchCancelled.has(rec.id)) return; // 跳中停止：终态已由 researchStop 落，链尾直接退出
      // 派生落账（失败行不计入派生——错误文案不得污染报告桶，B34 部分内容口径）
      const rowsForDerive = st.rows.filter((r) => r.kind === "assistantText" && r.state !== "failed")
        .map((r) => ({ kind: r.kind, text: r.text ?? "", reasoning: r.reasoning ?? "" }));
      const derived = deriveFromRows(rowsForDerive);
      const hopSteps = [];
      for (const r of st.rows) {
        if (r.kind !== "assistantText" || !Array.isArray(r.toolCalls)) continue;
        for (let i = 0; i < r.toolCalls.length; i++) {
          const tc = r.toolCalls[i];
          const id = `${threadId}-${r.rowId}-${i}`;
          if (rec.steps.some((st2) => st2.id === id)) continue; // 步骤只追加（B28 同源语义）
          hopSteps.push(toResearchStep({
            id, name: tc.name, input: tc.input, output: tc.output,
            error: r.state === "failed" ? (st.lastError?.message ?? "调用失败") : tc.error,
            status: r.state === "failed" || tc.error ? "error" : "done",
          }));
        }
      }
      rec = mergeResearchRecord(rec, {
        steps: hopSteps.length ? [...(rec.steps ?? []), ...hopSteps] : rec.steps,
        planning: derived.planning ?? rec.planning ?? undefined,
        updates: derived.updates.length ? derived.updates : rec.updates,
        summary: derived.summary || rec.summary,
        reasoning: derived.reasoning || rec.reasoning,
        blocks: st.rows.slice(-200).map((r) => ({ kind: r.kind, state: r.state, text: r.text ?? "", reasoning: r.reasoning ?? "", createdAt: r.createdAt })),
        threadId, turnId,
      });
      if (st.phase === "error") {
        // B26：配额/鉴权确定性错误 → 立即切 web 兜底指令续跑、不再重试该类来源（对拍 27）
        if (!quotaFallback && isQuotaAuthError(st.lastError?.message ?? "")) {
          quotaFallback = true;
          if (attempt < MAX_REPORT_CONTINUATIONS) {
            prompt = buildStageDirective({ hasPlan: Boolean(rec.planning), continuation: true }) + "\n\n" + buildQuotaFallbackDirective();
            continue;
          }
        }
        // B34：连接错误但有真实产出（报告/阶段播报）→ done 保留部分；仅剩即时规划占位或全无 → error 连接中断前缀
        if (rec.summary || (rec.updates && rec.updates.length)) {
          rec = finalizeResearchRecord(rec, { status: "done", error: undefined });
        } else {
          rec = finalizeResearchRecord(rec, { status: "error", error: "调研连接中断：" + (st.lastError?.message ?? "模型连接失败") });
        }
        return;
      }
      // ── B22/B23/B26/B30：证据门活接线（判定器输入=本链工具事件；指令驱动下一跳）──
      const hopTools = st.rows.flatMap((r) => (r.kind === "assistantText" && Array.isArray(r.toolCalls)) ? r.toolCalls : [])
        .map((tc) => ({ name: tc.name, payloadText: tc.output || tc.input || "", isError: Boolean(tc.error) }));
      const hopGate = evidenceGate(hopTools);
      const curText = st.rows.filter((r) => r.kind === "assistantText" && r.state !== "failed").map((r) => r.text ?? "").join("\n\n");
      const curReasoning = st.rows.filter((r) => r.kind === "assistantText" && r.state !== "failed").map((r) => r.reasoning ?? "").filter(Boolean).join("\n\n");
      // B30 三类续跑分类计数（各 ≤2）：同一形态反复出现即收口，不无限续跑
      const kind = classifyContinuation(
        { text: prevText, reasoning: prevReasoning, toolCount: prevToolCount },
        { text: curText, reasoning: curReasoning, toolCount: hopTools.length, gate: hopGate, hasPlan: Boolean(rec.planning) },
      );
      if (kind !== "none") continuationCounts[kind]++;
      prevText = curText; prevReasoning = curReasoning; prevToolCount = hopTools.length;
      if (isReportComplete(rec.summary)) break; // 报告完整 → 放行终态
      if (attempt >= MAX_REPORT_CONTINUATIONS) break; // B24 有界续跑上限 5，到限放行
      if (continuationCounts[kind] > 2) break; // B30：同一续跑形态超 2 次 → 收口（落当前内容终态）
      // 下一跳指令装配：B26 配额兜底优先（不再重试主库类来源）；否则阶段指令+证据指令（B22 强制取证 / B23 剔除装饰）
      prompt = buildStageDirective({ hasPlan: Boolean(rec.planning), continuation: true });
      if (quotaFallback) {
        prompt += "\n\n" + buildQuotaFallbackDirective();
      } else {
        const evDirective = buildEvidenceDirective(hopGate, Boolean(rec.planning));
        if (evDirective) prompt += "\n\n" + evDirective;
      }
    }
    // 终态：B33 回合结束但无可展示内容 → 专属错误文案（区别于连接失败）；否则完成
    const hasContent = Boolean(rec.summary || rec.planning || (rec.updates && rec.updates.length));
    rec = finalizeResearchRecord(rec, hasContent
      ? { status: "done", error: undefined }
      : { status: "error", error: "本轮调研未收到任何可展示内容。" });
  } catch (e) {
    rec = finalizeResearchRecord(rec, { status: "error", error: "调研连接中断：" + String(e?.message ?? e) });
  }
}
// 最小合法 conversation 快照（启动自检 safeParse 迭代调通，子区形状以 zod 报错为准）
function buildConvSnapshot(sessionId) {
  const st = convStateOf(sessionId);
  return {
    // §六.A#1：snapshot 顶层产出 runtimeInitialization——桥态恒 ready（合成数据面自足）；
    // statePatch（state.updated patch）侧同键为已知可选键，桥当前无 state.updated 产径，
    // 产出口径与 snapshot 同（main delta.ts statePatchSchema 键集）。
    runtimeInitialization: { status: "ready", attemptId: runtimeInitOf(sessionId).attemptId },
    protocolVersion: 1, sessionId, logEpoch: CONV_LOG_EPOCH,
    seq: convStates.get(sessionId)?.seq ?? 0, revision: 1,
    control: { phase: st.phase, sessionEnded: st.phase.startsWith("completed"), canStop: false, stopState: "idle", stopTargetKind: "assistant", activeWorks: [], lastError: st.lastError, apiRetry: null },
    availability: { fork: { allowed: true }, compact: { allowed: true }, switchModelConfig: { allowed: true }, setFollowupMode: { allowed: true }, queueEdit: { allowed: true }, sendQueuedNow: { allowed: true }, pauseGoal: { allowed: true }, resumeGoal: { allowed: true }, rewind: { allowed: true }, retry: { allowed: true }, interrupt: { allowed: true }, compactAll: { allowed: true }, forkAll: { allowed: true }, planMode: { allowed: true } },
    inputRouting: { mode: "startNow" },
    meta: { title: liveSessions.get(sessionId)?.title ?? "", titleSource: liveSessions.get(sessionId)?.titleSource ?? "default" },
    config: { provider: "deepseek-byok", model: "deepseek-chat", thought: "medium", followupMode: "guide" },
    usage: { contextWindow: { usedTokens: 0, maxTokens: 65536, autoCompactThresholdTokens: 0 }, cumulative: { inputTokens: 0, outputTokens: 0, cacheReadTokens: 0, cacheWriteTokens: 0 } },
    queue: { items: [], size: 0, admission: {}, capacity: {}, autoDrain: false },
    pendingInteractions: [], pendingCommands: [], backgroundWorks: [],
    modelTransition: null, goal: null, plan: null,
    rows: { window: st.rows, totalCount: st.rows.length, firstRowId: st.rows[0]?.rowId ?? null },
  };
}

Object.assign(agentService, {
  onDynamicConversationFrame: (p) => { console.log("[bridge] onDynamicConversationFrame listener attaching params=" + JSON.stringify(p)); return conversationFrameEmitter.event; },
  subscribeConversationV4: async (rawParams) => {
    // §六.A#2：白名单剥键容忍演进（historyFirst/additionalDirectories 等，unknown 剥掉不拒帧）
    const params = stripUnknownKeys(rawParams, SUBSCRIBE_KNOWN_KEYS, "subscribeConversationV4");
    const topic = params?.topic || `conversation/${params?.sessionId || "draft"}`;
    const subscriptionId = "sub_" + randomUUID().slice(0, 8);
    if (!conversationSubscriptions.has(topic)) conversationSubscriptions.set(topic, new Set());
    conversationSubscriptions.get(topic).add(subscriptionId);
    conversationSubTopics.set(subscriptionId, topic);
    const sid = topic.startsWith("conversation/") ? topic.slice("conversation/".length) : "draft";
    convStateOf(sid);
    runtimeInitOf(sid);
    setTimeout(() => emitConvFrame(topic, { kind: "snapshot", snapshot: buildConvSnapshot(sid) }, "initial", subscriptionId), 0);
    return { ack: { subscriptionId, mode: "snapshot", logEpoch: CONV_LOG_EPOCH } };
  },
  resyncConversationV4: async (rawParams) => {
    // UI resync 只带 subscriptionId（agentConversationTransport.ts:296）——反查 topic 再推帧；
    // 推错 topic 会让 UI recovery 超时 fault.subscription.recoveryFrameTimedOut（真机实测根因）
    const params = stripUnknownKeys(rawParams, RESYNC_KNOWN_KEYS, "resyncConversationV4");
    const subscriptionId = params?.subscriptionId || "sub_" + randomUUID().slice(0, 8);
    const topic = conversationSubTopics.get(subscriptionId) || params?.topic || "conversation/draft";
    const sid = topic.startsWith("conversation/") ? topic.slice("conversation/".length) : "draft";
    // §六.A#1：retryInitialization 仅消费当前 failed attempt（main gateway 语义：
    // 校验 failed.attemptId === retryAttempt 才重跑）；attempt 不匹配→剥键照常 snapshot。
    // 桥态恒 ready，此键正常情况下剥掉无感。
    const retryAttempt = typeof params?.retryInitialization === "string" ? params.retryInitialization : "";
    const ri = runtimeInitStates.get(sid);
    if (retryAttempt && ri?.status === "failed") {
      if (ri.attemptId === retryAttempt) {
        ri.status = "ready"; delete ri.reasonCode; delete ri.message;
        console.log("[bridge] retryInitialization consumed: sid=" + sid + " attempt=" + retryAttempt);
      } else {
        console.log("[bridge] retryInitialization attempt mismatch, ignored: " + retryAttempt);
      }
    }
    runtimeInitOf(sid);
    setTimeout(() => emitConvFrame(topic, { kind: "snapshot", snapshot: buildConvSnapshot(sid) }, "recovery", subscriptionId), 0);
    return { ack: { subscriptionId, mode: "snapshot", logEpoch: CONV_LOG_EPOCH } };
  },
  unsubscribeConversationV4: async (params) => {
    const sid0 = params?.subscriptionId;
    const topic0 = sid0 ? conversationSubTopics.get(sid0) : undefined;
    if (topic0) {
      conversationSubscriptions.get(topic0)?.delete(sid0);
      conversationSubTopics.delete(sid0);
    }
  },
  // conversation 查询面全家空实现（UI 会调，Method not found 会进错误重试循环）
  conversationWorkflowRunsV4: async () => ({ runs: [] }),
  conversationWorkflowRunEventsV4: async () => ({ events: [] }),
  conversationWorkflowRunArtifactsV4: async () => ({ artifacts: [] }),
  conversationWorkflowRunArtifactDataV4: async () => ({ items: [], hasMore: false }),
  conversationWorkflowRunWorkspaceV4: async () => ({ nodes: [] }),
  conversationPlansV4: async () => ({ plans: [] }),
  // 功能#27：真实现（分享服务 loadAllRows 全量分页取行用）。行集=权威 st.rows（升序），
  // 尾部起 window，beforeRowId 游标语义与 transport.ts v4ConversationRowsRangeParamsSchema 一致。
  conversationRowsRangeV4: async (params) => {
    const st = convStates.get(params?.sessionId);
    const all = st?.rows ?? [];
    const limit = Math.max(1, Math.min(params?.limit ?? 200, 200));
    let startIdx;
    if (params?.beforeRowId !== undefined) {
      const cut = all.findIndex((r) => r.rowId >= params.beforeRowId);
      const before = cut === -1 ? all : all.slice(0, cut);
      startIdx = Math.max(0, before.length - limit);
    } else {
      startIdx = Math.max(0, all.length - limit);
    }
    const rows = all.slice(startIdx);
    return { rows, hasMore: startIdx > 0, atSeq: st?.seq ?? 0, atRevision: 1, atLogEpoch: CONV_LOG_EPOCH };
  },
  conversationFileChangesV4: async () => ({ changes: [] }),
  conversationFileRewindPreviewV4: async () => ({ preview: null }),
  // 功能#27 分享服务的附件查询面：合成桥会话行不携带附件，通道诚实拒绝（不伪造空附件）。
  conversationAttachmentReadV4: async () => { throw new Error("合成桥未开放会话附件读取通道（会话行无附件）"); },
  conversationAttachmentStatV4: async () => { throw new Error("合成桥未开放会话附件 stat 通道（会话行无附件）"); },
  sendConversationCommandV4: async (params) => {
    const env = params?.envelope ?? {};
    console.log("[bridge] command received: type=" + env.type + " sid=" + env.sessionId + " keys=" + Object.keys(params ?? {}).join(","));
    const sid = env.sessionId || "ses_bridge_" + randomUUID().slice(0, 6);
    // §六.A#4：runtime 门禁先行——桥态非 ready 明确拒收（guard.*），不静默吞命令。
    // 桥态恒 ready 时此路不通，仅诚实报 failed/initializing 时生效。
    const guardRejection = guardRuntimeCommand(sid, env);
    if (guardRejection) return guardRejection;
    // 功能 #20（B38 机制保证）：知识库问答线程拒绝主对话命令面直发——只允许 kbAsk 单一入口
    // 驱动回合（检索→拼提示词→直生，无工具循环、无 plan 命令入口；B36 前缀+独立工作区键同闸）。
    if (liveSessions.get(sid)?.workspaceId === KB_WORKSPACE_KEY
        && ["sendText", "editUserQuery", "forkAssistant"].includes(env.type)) {
      console.log("[bridge] kb guard: direct chat command rejected for KB thread " + sid);
      return { commandId: env.commandId ?? "cmd_" + randomUUID().slice(0, 8), status: "rejected",
        reasonCode: "guard.kbThreadDirectSend", revisionAtDecision: 1 };
    }
    // 功能 #16（B09 机制保证）：调研线程拒绝主对话命令面直发——只允许 researchRun 单一入口
    // 驱动回合（五要素模板+有界续跑，无主对话 plan 命令入口；独立工作区键同闸）。
    if (liveSessions.get(sid)?.workspaceId === RESEARCH_WORKSPACE_KEY
        && ["sendText", "editUserQuery", "forkAssistant"].includes(env.type)) {
      console.log("[bridge] research guard: direct chat command rejected for research thread " + sid);
      return { commandId: env.commandId ?? "cmd_" + randomUUID().slice(0, 8), status: "rejected",
        reasonCode: "guard.researchThreadDirectSend", revisionAtDecision: 1 };
    }
    // 隐身模式（M4 验收第 3 条）：开启即出站全断——sendText fail-closed 拒绝，UI 显示错误行
    if (env.type === "sendText" && loadSetting().stealthMode?.enabled) {
      const topic0 = `conversation/${sid}`;
      if (!conversationSubscriptions.has(topic0)) conversationSubscriptions.set(topic0, new Set());
      if (conversationSubscriptions.get(topic0).size === 0) conversationSubscriptions.get(topic0).add("sub_self_" + sid.slice(-6));
      const st0 = convStateOf(sid);
      const turnId0 = "turn_" + randomUUID().slice(0, 8);
      const stealthUser = { ...baseRow(st0, turnId0), kind: "userInput", text: env.payload?.text ?? "" };
      const stealthAsst = { ...baseRow(st0, turnId0), kind: "assistantText", text: "隐身模式已开启：出站通道全断，未连接任何模型。请在设置中关闭隐身模式后重试。", state: "failed", model: "stealth" };
      st0.rows.push(stealthUser, stealthAsst);
      emitConvFrame(topic0, { kind: "deltas", deltas: [{ op: "row.appended", row: stealthUser }] });
      emitConvFrame(topic0, { kind: "deltas", deltas: [{ op: "row.appended", row: stealthAsst }] });
      console.log("[bridge] stealth: outbound blocked for", sid);
      return { commandId: env.commandId ?? "cmd_" + randomUUID().slice(0, 8), status: "accepted", revisionAtDecision: 1 };
    }
    // 功能 #20（B60 机制保证）：主对话 shell 绕库守卫——三条件与（①指向知识库路径 ②批量 PDF
    // 遍历 ③低级 PDF 解析器）同时命中才拦；纯直扫/列目录/单文件读取不触发（阈值语义同竞品 B60，
    // 判定式单源在 kb_service.kbShellBypassGuard）。拦截点=桥面 sendText 出站边界（主对话唯一可
    // 拦层；oc28 运行时内部工具循环不经桥面，此为同阈值语义非同位拦截，如实注记）。拦截=不出站
    // 不触模型，本地落 advisory 行（文案自写，自家工具名 kbSearch/kbRead）。
    if (env.type === "sendText" && kbShellBypassGuard(String(env.payload?.text ?? ""), { kbRoot: KB_ROOT })) {
      const topicG = `conversation/${sid}`;
      if (!conversationSubscriptions.has(topicG)) conversationSubscriptions.set(topicG, new Set());
      if (conversationSubscriptions.get(topicG).size === 0) conversationSubscriptions.get(topicG).add("sub_self_" + sid.slice(-6));
      const stG = convStateOf(sid);
      const turnG = "turn_" + randomUUID().slice(0, 8);
      const userRowG = { ...baseRow(stG, turnG, undefined, { canEdit: true }), kind: "userInput", origin: "realUser", text: env.payload?.text ?? "", sourceCommandId: env.commandId ?? null };
      const guardRowG = { ...baseRow(stG, turnG), kind: "assistantText", text: KB_BYPASS_ADVISORY, state: "complete", model: "kb-guard" };
      stG.rows.push(userRowG, guardRowG);
      persistSessionState(sid);
      emitConvFrame(topicG, { kind: "deltas", deltas: [{ op: "row.appended", row: userRowG }, { op: "row.appended", row: guardRowG }] });
      persistRow(sid, userRowG);
      persistRow(sid, guardRowG);
      console.log("[bridge] kb shell guard: bulk bypass command intercepted for", sid);
      return { commandId: env.commandId ?? "cmd_" + randomUUID().slice(0, 8), status: "accepted", revisionAtDecision: 1 };
    }
    // 功能 #16 技能触发合同（RE-16 §3 技能类附加，对拍 50 分发面）：对话内 /research、/调研 直达
    // 调研工作流——剥指令词取课题，走 researchRun 单一入口（独立内部会话+五要素模板+有界续跑）；
    // 主对话只落本地行（不触主对话模型回合）。空课题→本地引导行；启动被拒（隐身/裸话题）→如实
    // 回显拒因。置于隐身闸之后（隐身优先 fail-closed）、法库指路之前（斜线指令优先于意图猜路）。
    if (env.type === "sendText" && /^\/(?:research|调研)(?:[\s：:]|$)/.test(String(env.payload?.text ?? ""))) {
      const restText = String(env.payload?.text ?? "").replace(/^\/(?:research|调研)[\s：:]*/, "").trim();
      const topicD = `conversation/${sid}`;
      if (!conversationSubscriptions.has(topicD)) conversationSubscriptions.set(topicD, new Set());
      if (conversationSubscriptions.get(topicD).size === 0) conversationSubscriptions.get(topicD).add("sub_self_" + sid.slice(-6));
      const stD = convStateOf(sid);
      const turnD = "turn_" + randomUUID().slice(0, 8);
      const userRowD = { ...baseRow(stD, turnD, undefined, { canEdit: true }), kind: "userInput", origin: "realUser", text: env.payload?.text ?? "", sourceCommandId: env.commandId ?? null };
      let replyTextD;
      if (!restText) {
        replyTextD = "请在 /调研 后补充课题内容，例如「/调研 股东出资纠纷相关的法律规定与典型案例」。";
      } else {
        try {
          await agentService.researchRun({ query: restText });
          replyTextD = "已发起调研报告：课题「" + (restText.length > 40 ? restText.slice(0, 40) + "…" : restText) + "」。调研在「调研报告」工作区独立进行，完成后可到该工作区查看、编辑与导出。";
        } catch (e) {
          replyTextD = "调研未能启动：" + String(e?.message ?? e); // 隐身 fail-closed/裸话题提示等原样回显
        }
      }
      const replyRowD = { ...baseRow(stD, turnD), kind: "assistantText", text: replyTextD, state: "complete", model: "research-dispatch" };
      stD.rows.push(userRowD, replyRowD);
      persistSessionState(sid);
      emitConvFrame(topicD, { kind: "deltas", deltas: [{ op: "row.appended", row: userRowD }, { op: "row.appended", row: replyRowD }] });
      persistRow(sid, userRowD);
      persistRow(sid, replyRowD);
      console.log("[bridge] research dispatch: slash command handled for", sid);
      return { commandId: env.commandId ?? "cmd_" + randomUUID().slice(0, 8), status: "accepted", revisionAtDecision: 1 };
    }
    // 【施工波三轮·#7 证据目录全量面】D4②"文件在哪"追问复用（RE-7 对拍 23 第二层）：消息 ≤80 字、
    // 含位置追问词、非授权语（"放哪都行/随便"不触发），且线程已有交付回合（stepIndex>0 闸——首轮
    // 无交付可复用恒不触发）时，取线程最近一次 agent docx 交付（对话附件库 thread 作用域，只认
    // 交付不认查看）直接作答并短路——本地行记账，不触模型回合（同 F1 指路行形态）。
    if (env.type === "sendText") {
      const stQ = convStateOf(sid);
      const hadPriorTurn = (stQ.rows ?? []).some((r) => r.kind === "assistantText");
      if (hadPriorTurn) {
        let history = [];
        try { history = materials.listAttachments({ threadId: sid }); } catch { /* 附件库不可读则无复用面 */ }
        const wordHistory = history
          .filter((a) => a.producer === "agent" && /\.docx$/i.test(a.filename))
          .map((a) => ({ path: a.filename, status: "ok", kind: "docx" }));
        const answer = deliveredWordLocationAnswer({
          message: String(env.payload?.text ?? ""),
          history: wordHistory,
          allowReuse: wordHistory.length > 0,
        });
        if (answer) {
          const topicQ = `conversation/${sid}`;
          if (!conversationSubscriptions.has(topicQ)) conversationSubscriptions.set(topicQ, new Set());
          if (conversationSubscriptions.get(topicQ).size === 0) conversationSubscriptions.get(topicQ).add("sub_self_" + sid.slice(-6));
          const turnQ = "turn_" + randomUUID().slice(0, 8);
          const userRowQ = { ...baseRow(stQ, turnQ, undefined, { canEdit: true }), kind: "userInput", origin: "realUser", text: env.payload?.text ?? "", sourceCommandId: env.commandId ?? null };
          const replyRowQ = { ...baseRow(stQ, turnQ), kind: "assistantText", text: answer, state: "complete", model: "delivery-local" };
          stQ.rows.push(userRowQ, replyRowQ);
          persistSessionState(sid);
          emitConvFrame(topicQ, { kind: "deltas", deltas: [{ op: "row.appended", row: userRowQ }, { op: "row.appended", row: replyRowQ }] });
          persistRow(sid, userRowQ);
          persistRow(sid, replyRowQ);
          console.log("[bridge] delivery location reuse: short-circuited for", sid);
          return { commandId: env.commandId ?? "cmd_" + randomUUID().slice(0, 8), status: "accepted", revisionAtDecision: 1 };
        }
      }
    }
    // 功能 #29 场景化引导（RE-29 F1/F2）：对话发送命中"检索法规"意图且本地法规库不可用时，
    // 不触模型、不执行检索，本地注入指路行（文案自写）；状态查询本身抛错走 fail-closed 指路。
    // 行形态与隐身拒绝行同族（无 productTurnId 不进分享面板；state=complete 仅本地记账）。
    if (env.type === "sendText" && isLawsRetrievalIntent(env.payload?.text)) {
      let guidance = null;
      try {
        if (!lawsLibraryStatus().available) guidance = LAWS_GUIDANCE.unavailable; // F1
      } catch {
        guidance = LAWS_GUIDANCE.error; // F2：法库状态查询抛错 → fail-closed 指路，不静默失败
      }
      if (guidance) {
        const topicL = `conversation/${sid}`;
        if (!conversationSubscriptions.has(topicL)) conversationSubscriptions.set(topicL, new Set());
        if (conversationSubscriptions.get(topicL).size === 0) conversationSubscriptions.get(topicL).add("sub_self_" + sid.slice(-6));
        const stL = convStateOf(sid);
        const turnL = "turn_" + randomUUID().slice(0, 8);
        // user 行带 sourceCommandId（UI hasAcceptedInputProjection 对账键，缺字段=投影静默，同正常路径注释）；
        // canEdit/origin 与正常 sendText user 行同形。
        const userRowL = { ...baseRow(stL, turnL, undefined, { canEdit: true }), kind: "userInput", origin: "realUser", text: env.payload?.text ?? "", sourceCommandId: env.commandId ?? null };
        const guideRowL = { ...baseRow(stL, turnL), kind: "assistantText", text: guidance, state: "complete", model: "laws-guide" };
        stL.rows.push(userRowL, guideRowL);
        persistSessionState(sid);
        emitConvFrame(topicL, { kind: "deltas", deltas: [{ op: "row.appended", row: userRowL }] });
        emitConvFrame(topicL, { kind: "deltas", deltas: [{ op: "row.appended", row: guideRowL }] });
        persistRow(sid, userRowL);
        persistRow(sid, guideRowL);
        console.log("[bridge] laws guidance: intercepted retrieval-intent send for", sid);
        return { commandId: env.commandId ?? "cmd_" + randomUUID().slice(0, 8), status: "accepted", revisionAtDecision: 1 };
      }
    }
    const topic = `conversation/${sid}`;
    if (!conversationSubscriptions.has(topic)) conversationSubscriptions.set(topic, new Set());
    if (conversationSubscriptions.get(topic).size === 0) conversationSubscriptions.get(topic).add("sub_self_" + sid.slice(-6));
    const st = convStateOf(sid);
    const ack = { commandId: env.commandId ?? "cmd_" + randomUUID().slice(0, 8), status: "accepted", revisionAtDecision: 1 };
    if (env.type === "createSession") {
      // M3 补面：draft 发送链需要 createSession ack.result（v4 command.ts commandResultSchema）。
      // 本地记账不触 oc28；出站仍收敛在 sendText 分支，隐身语义不变。
      const newSid = env.payload?.sessionId || "ses_bridge_" + randomUUID().slice(0, 6);
      console.log("[bridge] createSession ->", newSid);
      const now = Date.now();
      // F5：workspaceId 单源走 workspaceKeyOf（payload.workspaceId 优先是 UI 合同，非第二派生链）
      const workspaceId = env.payload?.workspaceId || workspaceKeyOf(params);
      convStateOf(newSid);
      liveSessions.set(newSid, {
        sessionId: newSid, workspaceId, title: "", titleSource: "default",
        workspacePath: params?.workspacePath || WORKSPACE.path, projectId: params?.projectId ?? null,
        phase: "draft", sessionEnded: false, hasBackgroundWork: false,
        lastActivityAt: now, createdAt: now,
      });
      persistSessionState(newSid);
      emitSessionsIndexDeltaFrame(`sessions-index/${workspaceId}`, [
        { op: "session.upserted", session: liveSessions.get(newSid) },
      ]);
      return { ...ack, result: { type: "createSession", sessionId: newSid } };
    }
    if (env.type === "setFollowupMode") {
      // 3.16.2 UI 命令链：createSession→setFollowupMode→sendText 串行，followupMode 的 ack
      // 带 inputDisposition result 才放行后续发送（commandResult discriminatedUnion）
      return { ...ack, result: { type: "inputDisposition", delivery: "startNow" } };
    }
    // ── 功能#23 对话分支画布（ZCode 顶·树内开闸）：分支创建（forkAssistant）/回退重生成
    //    （editUserQuery rewind）接线 V4 会话命令面。UI 侧能力在树内全备（ConversationRowView
    //    fork/edit 行入口 + SessionPane handleFork/handleEdit + projection 以 row.removed 为
    //    权威裁剪边界），此前桥缺三件：行不带 entityId/canFork/canEdit（入口永不渲染）、
    //    两命令裸 ack 无 result（分支创建/回退全死）、裁剪行不出库（重启复活旧分支）。
    if (env.type === "forkAssistant") {
      const target = env.payload?.target ?? {};
      const fsummary = liveSessions.get(sid);
      const frow = st.rows.find((r) => r.rowId === target.rowId);
      const stable = frow && frow.kind === "assistantText" && frow.state === "complete"
        && frow.actions?.canFork === true
        && (typeof target.entityId !== "string" || frow.entityId === target.entityId);
      if (!stable) {
        return { commandId: ack.commandId, status: "rejected", reasonCode: "guard.forkTargetNotStable", revisionAtDecision: 1 };
      }
      const childId = "ses_bridge_" + randomUUID().slice(0, 6);
      const now = Date.now();
      const forkWorkspaceId = workspaceKeyOf(params);
      convStateOf(childId);
      liveSessions.set(childId, {
        sessionId: childId, workspaceId: forkWorkspaceId,
        title: (fsummary?.title ?? "对话") + "（分支）", titleSource: "generated",
        workspacePath: params?.workspacePath || WORKSPACE.path,
        projectId: params?.projectId ?? fsummary?.projectId ?? null,
        phase: "draft", sessionEnded: false, hasBackgroundWork: false,
        lastActivityAt: now, createdAt: now,
      });
      const cst = convStateOf(childId);
      // child 会话首部 forkNotice（rows.ts：出现在 child 会话首部）；点击=跳父会话
      // （SessionPane Tier 1 onNavigateToRow → onSessionCreated(parentId)）=分支切换回链。
      const noticeRow = { ...baseRow(cst, "turn_fork_" + randomUUID().slice(0, 4)), kind: "timelineMarker", lane: "turnTailBoundary", marker: { type: "forkNotice", parentSessionId: sid, parentRowId: frow.rowId } };
      cst.rows.push(noticeRow);
      persistRow(childId, noticeRow);
      persistSessionState(childId);
      // 父会话 forkCreated（rows.ts：出现在 parent，可选展示）
      const createdRow = { ...baseRow(st, "turn_fork_" + randomUUID().slice(0, 4)), kind: "timelineMarker", lane: "turnTailBoundary", marker: { type: "forkCreated", childSessionId: childId, atRowId: frow.rowId } };
      st.rows.push(createdRow);
      persistRow(sid, createdRow);
      persistSessionState(sid);
      emitConvFrame(`conversation/${childId}`, { kind: "deltas", deltas: [{ op: "row.appended", row: noticeRow }] });
      emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.appended", row: createdRow }] });
      emitSessionsIndexDeltaFrame(`sessions-index/${forkWorkspaceId}`, [{ op: "session.upserted", session: liveSessions.get(childId) }]);
      console.log("[bridge] forkAssistant: " + sid + " row " + frow.rowId + " -> " + childId);
      return { ...ack, result: { type: "forkAssistant", sessionId: childId } };
    }
    if (env.type === "editUserQuery") {
      const target = env.payload?.target ?? {};
      const esummary = liveSessions.get(sid);
      const newText = typeof env.payload?.newText === "string" ? env.payload.newText : "";
      if (st.busy || !newText.trim()) {
        return { commandId: ack.commandId, status: "rejected", reasonCode: st.busy ? "guard.sessionBusy" : "guard.editEmptyQuery", revisionAtDecision: 1 };
      }
      const userRows = st.rows.filter((r) => r.kind === "userInput");
      const urow = st.rows.find((r) => r.rowId === target.rowId && r.kind === "userInput");
      // command 层守卫（官方语义）：edit 只打最新真实 user query（行内编辑=回退重生成该轮）
      const isLatest = urow && userRows.length > 0 && userRows[userRows.length - 1].rowId === urow.rowId;
      if (!isLatest) {
        return { commandId: ack.commandId, status: "rejected", reasonCode: "guard.editTargetNotLatest", revisionAtDecision: 1 };
      }
      // rewind：替换目标行文本（sourceCommandId=本次 edit 命令，hasAcceptedInputProjection
      // 对账键）+ row.removed 权威裁剪其后全部行 + 重跑一轮（runAssistantTurn 同款链）
      urow.text = newText;
      urow.sourceCommandId = env.commandId ?? urow.sourceCommandId ?? null;
      const removedFrom = urow.rowId + 1;
      const cutCount = st.rows.filter((r) => r.rowId >= removedFrom).length;
      st.rows = st.rows.filter((r) => r.rowId < removedFrom);
      st.rowSeq.n = urow.rowId;
      // 被裁行出库（含 #15 全文索引块），否则重启复活旧分支
      if (esummary && cutCount > 0) store.deleteRowsFrom(esummary.workspaceId, sid, removedFrom);
      // 裁剪后模型上下文以新 oc28 会话重建（诚实边界：裁剪点之前的轮次不重放进新 oc28 上下文）
      st.oc28Id = null;
      st.oc28SeenIds = [];
      persistRow(sid, urow);
      persistSessionState(sid);
      emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.upserted", row: urow }] });
      if (cutCount > 0) emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.removed", fromRowId: removedFrom }] });
      st.phase = "running";
      st.lastError = null;
      st.lastCommandId = ack.commandId;
      if (esummary) {
        Object.assign(esummary, { phase: "running", sessionEnded: false, lastActivityAt: Date.now() });
        delete esummary.lastOutcome;
        emitSessionsIndexDeltaFrame(`sessions-index/${esummary.workspaceId}`, [{ op: "session.upserted", session: esummary }]);
      }
      emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "state.updated", patch: { control: buildConvSnapshot(sid).control, meta: buildConvSnapshot(sid).meta } }] });
      const turnId = "turn_" + randomUUID().slice(0, 8);
      const pti = "pt_" + randomUUID().slice(0, 8);
      const turnHeaderRow = { ...baseRow(st, turnId, pti), kind: "turnHeader", origin: "userInput", executionKind: "agent", state: "running", startedAt: Date.now() };
      st.rows.push(turnHeaderRow);
      persistRow(sid, turnHeaderRow);
      emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.appended", row: turnHeaderRow }] });
      runAssistantTurn(sid, ack, turnId, pti, turnHeaderRow, newText);
      return { ...ack, result: { type: "editUserQuery", disposition: "rewind", sessionId: sid } };
    }
    if (env.type !== "sendText") return ack;
    let text = env.payload?.text ?? "";
    // 【#6 对话附件跨回合继承】（RE-6 §3 上下文注入；对拍 11）：本条消息携带的 attachmentIds
    // 并入会话附件集合（去重，上限 64），此后每一回合（含后续无附件消息）都随注入块进入模型
    // 上下文——等量竞品 attachmentIdsForTurn "Every later turn receives every user attachment"。
    if (Array.isArray(env.payload?.attachmentIds) && env.payload.attachmentIds.length) {
      const merged = new Set(st.attachmentIds ?? []);
      for (const x of env.payload.attachmentIds) {
        if (typeof x === "string" && x.trim() && merged.size < 64) merged.add(x.trim());
      }
      st.attachmentIds = [...merged];
    }
    // 功能#10（RE-10 §2 H5/H7）：对话内起草起诉/答辩时，隐藏结构模板工具同源绑定——
    // 确定性意图正则（起诉状|答辩状，禁模型猜）命中即解析隐藏模板；命中则把随附指令+结构参考
    // 并入本轮模型输入（用户行仍显示原文）；未命中不注入（不阻塞交付）。用户自定义模板优先合同
    // 写在随附指令内。隐身模式由 runAssistantTurn 内既有 fail-closed 链兜底（此处仅文本装配）。
    let deliveryAnchors = null; // H8 锚点：本轮若提到可机验要求，随回合传给完成结算做终稿机检
    const userText = text; // 锚点只从用户原文提取（模板注入文本不参与）
    if (!loadSetting().stealthMode?.enabled && /(?:民事)?(?:起诉|答辩)状/.test(text)) {
      try {
        const resolved = resolveDocumentTemplate({
          documentType: /答辩状/.test(text) ? "answer" : "complaint",
          query: text,
        });
        if (resolved.matched && resolved.template && resolved.instructions) {
          text = text + "\n\n【系统注入·内置结构模板（仅当用户未提供自定义模板时遵循）】\n随附指令：" + resolved.instructions + "\n模板结构参考（项目顺序为准）：\n" + resolved.template.content;
          console.log("[bridge] sendText drafting intent bound: " + resolved.template.name);
        }
        // H8/H9 文书重叠部分：锚点机提取（确定性正则）→注入任务提示+事实忠实度指令；提取不到不注入不机检，不阻塞交付。
        const anchors = extractDeliveryAnchors(userText);
        if (anchors.hasAny) {
          const want = [];
          if (anchors.minChars > 0) want.push("- 字数下限：不少于 " + anchors.minChars + " 字");
          for (const sec of anchors.requiredSections) want.push("- 必需章节：「" + sec + "」");
          for (const no of anchors.caseNos) want.push("- 案号须原文写入：" + no);
          want.push("- 禁占位符：全文唯一合法占位=【待核实：具体事项】");
          text = text + "\n\n【交付锚点（终稿将逐项机检）】\n" + want.join("\n") + "\n" + FACT_FIDELITY_BLOCK;
          deliveryAnchors = anchors;
          console.log("[bridge] sendText delivery anchors bound: " + JSON.stringify({ minChars: anchors.minChars, sections: anchors.requiredSections.length, caseNos: anchors.caseNos.length }));
        }
      } catch { /* 解析失败不阻塞对话（工具失败不阻塞交付） */ }
    }
    st.phase = "running";
    st.lastError = null;
    st.lastCommandId = ack.commandId; // 结算与终态回执都要认得本轮命令（F1/F3）
    const summary = liveSessions.get(sid);
    if (summary) {
      Object.assign(summary, { phase: "running", sessionEnded: false, lastActivityAt: Date.now() });
      if (!summary.title) Object.assign(summary, { title: text.slice(0, 80), titleSource: "generated" });
      delete summary.lastOutcome;
      emitSessionsIndexDeltaFrame(`sessions-index/${summary.workspaceId}`, [{ op: "session.upserted", session: summary }]);
    }
    emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "state.updated", patch: { control: buildConvSnapshot(sid).control, meta: buildConvSnapshot(sid).meta } }] });
    const turnId = "turn_" + randomUUID().slice(0, 8);
    // 功能#27：每轮发射 turnHeader 边界行（分享预检/选择面板的 product turn 权威，
    // rows.ts turnHeaderRowSchema），行随终态翻转 state（running→completedSuccess/failed）。
    const pti = "pt_" + randomUUID().slice(0, 8);
    const turnHeaderRow = { ...baseRow(st, turnId, pti), kind: "turnHeader", origin: "userInput", executionKind: "agent", state: "running", startedAt: Date.now() };
    st.rows.push(turnHeaderRow);
    persistRow(sid, turnHeaderRow);
    emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.appended", row: turnHeaderRow }] });
    // 2026-10-26：UI hasAcceptedInputProjection 以 row.sourceCommandId 对账 sendText 的
    // envelope.commandId——缺字段=投影静默→same-sub recovery 循环（conversationProjectionStore.ts:90-93）。
    // canEdit（功能#23）：user 行编辑入口（行内编辑=editUserQuery 回退重生成该轮）。
    const userRow = { ...baseRow(st, turnId, pti, { canEdit: true }), kind: "userInput", origin: "realUser", text, sourceCommandId: env.commandId ?? null };
    st.rows.push(userRow);
    persistRow(sid, userRow);
    persistSessionState(sid);
    emitConvFrame(topic, { kind: "deltas", deltas: [{ op: "row.appended", row: userRow }] });
    runAssistantTurn(sid, ack, turnId, pti, turnHeaderRow, text, deliveryAnchors ? { deliveryAnchors } : undefined);
    return ack;
  },
});

// 重连查询只返回本进程实际接受的回执；桥重启后的未知命令保持 unknown。
const commandReceipts = new Map();
const executeConversationCommand = agentService.sendConversationCommandV4;
agentService.sendConversationCommandV4 = (params) => {
  const env = params.envelope;
  const key = JSON.stringify([sessionsIndexTopicOf(params), env.sessionId ?? null, env.commandId]);
  if (!commandReceipts.has(key)) commandReceipts.set(key, executeConversationCommand(params));
  return commandReceipts.get(key);
};
agentService.queryConversationCommandsV4 = async (params) => ({
  results: await Promise.all(params.commands.map(async (key) => ({
    key,
    result: await (commandReceipts.get(JSON.stringify([sessionsIndexTopicOf(params), key.sessionId, key.commandId])) ?? "unknown"),
  }))),
});

// ── 功能 #22 定时任务执行面（树内开闸）：任务表=桥同库 SQLite（repo 注入 bridge-{port}.db，
//    automations/automation_runs 两表由 tasks migrations 建好），调度语义对齐官方 desktop scheduler
//    （packages/desktop/src/scheduler/index.ts：20s 轮询 / 5min misfire / 一次性终态 / 退避重试），
//    派发=桥内会话通道（createSession+sendText 走 oc28 真回合），产物=侧栏可见任务+运行历史可跳转。
//    诚实边界：本桥回合固定走 oc28 配置的 provider（BRIDGE_MODEL），automation.modelSelection 仅存档
//    不换轨（桥无多 provider 运行时）；隐身模式开启时回合按 sendText 同一 fail-closed 语义失败。
const automationRepo = new AutomationRepo(store.dbPath);
const automationService = new AutomationService(automationRepo, async (projectId) => ({
  projectId, hostId: "local", workspacePath: WORKSPACE.path, additionalDirectories: [],
}));
const AUTOMATION_POLL_MS = 20_000; // 官方同款：cron 分钟粒度下 20s 轮询足矣
const AUTOMATION_MISFIRE_GRACE_MS = 5 * 60_000; // 官方同款：错过窗口记 skipped 不补跑
const AUTOMATION_TURN_DEADLINE_MS = 240_000; // 覆盖 sendText 回合 150s 时限+余量
const automationWatchdogs = new Map(); // runId -> watchdog timer

// 回合终态结算：run outcome running→succeeded/failed；manual claim 由真实终态释放（官方同款），
// 长回合期间 60s 续租防 CLAIM_STALE_MS 僵尸回收。
function automationWatchdog(sid, runId, automationId, workspaceKey, trigger) {
  const started = Date.now();
  let beats = 0;
  const timer = setInterval(() => {
    if (trigger === "manual" && ++beats >= 30) {
      beats = 0;
      automationRepo.touchManualClaim(automationId, workspaceKey)
        .catch((e) => console.error("[bridge] automation touchManualClaim:", e?.message ?? e));
    }
    const st = convStates.get(sid);
    const settled = st && !st.busy && (st.phase === "completedSuccess" || st.phase === "error");
    const expired = Date.now() - started > AUTOMATION_TURN_DEADLINE_MS;
    if (!settled && !expired) return;
    clearInterval(timer);
    automationWatchdogs.delete(runId);
    const ok = st?.phase === "completedSuccess";
    automationRepo.markRunOutcome(runId, ok ? "succeeded" : "failed",
      ok ? undefined : (st?.lastError?.message ?? "运行未在时限内完成"))
      .catch((e) => console.error("[bridge] automation outcome:", e?.message ?? e));
    if (trigger === "manual") {
      automationRepo.releaseManualClaim(automationId, workspaceKey)
        .catch((e) => console.error("[bridge] automation releaseManualClaim:", e?.message ?? e));
    }
    console.log(`[bridge] automation run settled: ${runId} -> ${ok ? "succeeded" : "failed"}`);
  }, 2000);
  automationWatchdogs.set(runId, timer);
}

// 派发一次运行：会话产物走与 UI 完全相同的 sendText 回合链（oc28/投影/落库/回执全复用）。
async function dispatchAutomationRun(automation, runId, trigger, scheduledAt) {
  const workspaceKey = workspaceKeyOf({
    workspacePath: automation.workspacePath,
    workspaceIdentity: automation.workspaceIdentity,
  });
  try {
    await automationRepo.ensureRunClaimed({ runId, automationId: automation.automationId, workspaceKey, scheduledAt, trigger });
    await automationRepo.markRunOutcome(runId, "running");
    const sid = "ses_auto_" + randomUUID().slice(0, 6);
    const commandBase = {
      workspacePath: automation.workspacePath,
      ...(automation.workspaceIdentity ? { workspaceIdentity: automation.workspaceIdentity } : {}),
      projectId: automation.projectId ?? undefined,
    };
    await executeConversationCommand({ ...commandBase, envelope: {
      type: "createSession", sessionId: sid,
      commandId: "cmd_auto_" + randomUUID().slice(0, 8),
      payload: { sessionId: sid, workspaceId: workspaceKey },
    } });
    const summary = liveSessions.get(sid);
    if (summary && automation.title) summary.title = automation.title; // 产物任务用定时任务名；sendText 只补空标题
    await executeConversationCommand({ ...commandBase, envelope: {
      type: "sendText", sessionId: sid,
      commandId: "cmd_auto_" + randomUUID().slice(0, 8),
      payload: { text: automation.prompt },
    } });
    // 派发结算：schedule 推进调度态（next_run_at/run_count/lifecycle）；manual 只回填台账不改节奏
    if (trigger === "manual") {
      await automationRepo.markManualRunDispatched({ runId, sessionId: sid, dispatchedAt: Date.now() });
    } else {
      await automationRepo.markRunDispatch({ runId, dispatchStatus: "dispatched", sessionId: sid });
      const current = await automationRepo.get(automation.automationId);
      const nextRunAt = current ? computeAutomationNextRunAt(current, Date.now()) : null;
      await automationRepo.markDispatched(automation.automationId, { dispatchedAt: Date.now(), nextRunAt });
    }
    automationWatchdog(sid, runId, automation.automationId, workspaceKey, trigger);
    console.log(`[bridge] automation dispatched: ${runId} -> ${sid}`);
  } catch (e) {
    const message = e?.message ?? String(e);
    console.error("[bridge] automation dispatch failed:", message);
    try {
      await automationRepo.markRunDispatch({ runId, dispatchStatus: "failed_to_dispatch", error: message });
      if (trigger === "manual") {
        await automationRepo.releaseManualClaim(automation.automationId, workspaceKey);
      } else {
        await automationRepo.markDispatchFailed(automation.automationId, {
          failedAt: Date.now(), error: message, kind: "transient",
          nextRunAt: await automationRepo.get(automation.automationId)
            .then((a) => (a ? computeAutomationNextRunAt(a, Date.now()) : null)),
        });
      }
    } catch (e2) { console.error("[bridge] automation dispatch settle failed:", e2?.message ?? e2); }
  }
}

// 到期认领处理；错过触发窗口（桥停跑/休眠）→ skipAndReschedule 如实记 skipped，不静默吞。
async function handleClaimedAutomation(automation, now) {
  const scheduledAt = automation.nextRunAt ?? automation.retryAt ?? now;
  const runId = `${automation.automationId}:${scheduledAt}`;
  const workspaceKey = workspaceKeyOf({
    workspacePath: automation.workspacePath,
    workspaceIdentity: automation.workspaceIdentity,
  });
  const isRetry = automation.dispatchAttempts > 0;
  const missed = !isRetry && automation.nextRunAt != null
    && automation.nextRunAt <= now - AUTOMATION_MISFIRE_GRACE_MS;
  if (missed) {
    const finalize = isOneShotAutomation(automation);
    const nextRunAt = finalize ? null : computeAutomationNextRunAt(automation, now);
    await automationRepo.skipAndReschedule({
      automationId: automation.automationId, runId, workspaceKey, scheduledAt,
      reason: "computer_asleep_or_app_not_running", nextRunAt, finalize,
    });
    console.log(`[bridge] automation skipped (missed window): ${runId}`);
    return;
  }
  await automationRepo.upsertRunClaimed({ runId, automationId: automation.automationId, workspaceKey, scheduledAt, trigger: "schedule" });
  await dispatchAutomationRun(automation, runId, "schedule", scheduledAt);
}

let automationTicking = false;
async function automationTick() {
  if (automationTicking) return;
  automationTicking = true;
  try {
    const now = Date.now();
    for (const automation of await automationRepo.claimDue(now)) {
      await handleClaimedAutomation(automation, now);
    }
    for (const m of await automationRepo.claimManualRuns(now)) {
      await dispatchAutomationRun(m.automation, m.run.runId, "manual", m.run.scheduledAt ?? null);
    }
  } catch (e) {
    console.error("[bridge] automation tick:", e?.message ?? e);
  } finally {
    automationTicking = false;
  }
}
function startAutomationScheduler() {
  console.log("[bridge] automation scheduler started (poll " + AUTOMATION_POLL_MS + "ms, misfire grace " + AUTOMATION_MISFIRE_GRACE_MS + "ms)");
  void automationTick();
  setInterval(automationTick, AUTOMATION_POLL_MS).unref();
}

const services = new ServiceCollection();
services.register(ISettingService, settingService);
services.register(IZCodeAgentService, agentService);
services.register(IZCodeSessionService, sessionService);
services.register(IZCodeTaskService, zcodeTaskService);
services.register(IOnboardingRecordService, onboardingService);
// 首发会登记未分组任务；复用已有分组实现，库随桥实例持久化（RE-B1 §3.2；账本表
// tasks_schema_migration 与存储层 schema_migration 同库不撞名）。
const taskGroupDatabase = store.db;
await runTasksDatabaseMigrations(taskGroupDatabase, { dbPath: store.dbPath });
services.register(ITaskGroupService, createTaskGroupService({
  database: async () => taskGroupDatabase,
  resolveTasks: async (refs) => synthTaskMetas().filter((task) => refs.some((ref) =>
    ref.hostId === task.hostId && ref.workspacePath === task.workspacePath && ref.taskId === task.taskId)),
  afterChange: async () => {},
}));

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
const SYNTH_PROVIDER_CFG = {
  id: "deepseek",
  name: "DeepSeek（合成 BYOK）",
  models: [SYNTH_MODEL],
  // 3.16.2 模型菜单硬门禁（modelSelectionGroups.ts:28）：config.api.type 为空 → 整个供应商被过滤 →
  // 菜单空 → 无模型可路由（真机"模型都没选择出来"根因）。glm 是 3.16.2 唯一白名单 provider，
  // 会话级 provider 默认 undefined→displayProvider="glm" 放行，列表项只需 api.type 非空。
  api: { type: "openai-compatible" },
  access: { type: "api-key" },
};
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
  // 律引无账号体系（BYOK）：登录入口的 OAuth 走"无提供方"优雅空态，不崩 3.16.2 UI
  startOAuthWithPolling: async () => { throw new Error("律引为本地 BYOK 模式，无 OAuth 登录通道；请在设置→模型供应商填入 API Key。"); },
  startOAuth: async () => { throw new Error("律引为本地 BYOK 模式，无 OAuth 登录通道。"); },
  cancelPending: async () => {},
  pollPendingOAuth: async () => null,
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
  "window-controller", "client-config", "client-scenes", "skill-sync", "mcp-sync",
  "plugins", "plugin-sync", "subagents", "commands", "hooks", "memory", "usage-stats",
  "feedback", "prompt-attachment-transfer", "bots", "highspeed", "marketing-touch",
  "output-style", "conversation-share", "plugin-ui-bridge", "gen-ui",
]) {
  services.register({ channelName: name }, silentStub);
}

// ── 功能 #21：skills 通道真实现（合成内置 + cat-zip/SkillHub 双格式 zip 装卸，RE-21）──
const BUILTIN_SKILLS = [
  // 【施工波三轮·#7 全量面】triggers/rootPath=技能激活引擎注册数据（RE-7 §3 技能类附加：
  // explicit/command/pattern/fileType 四通道+预算 24000 字节+上限 3；无 triggers 的演示件只剩 explicit 点名）。
  { id: "juscite-builtin-document-drafting", name: "文书起草助手（内置合成）", description: "起诉状/答辩状/代理词/法律意见书/律师函/合同等文书起草规范（/draft）", body: DRAFT_SKILL_MD,
    triggers: DRAFT_SKILL_TRIGGERS, rootPath: "builtin/draft-skill" },
  { id: "juscite-builtin-contract-review", name: "合同审查要点（内置合成）", description: "合成内置技能：合同审查要点清单（演示用）", body: "内置合成技能正文（合成材料）。" },
  { id: "juscite-builtin-legal-timeline", name: "诉讼期限速查（内置合成）", description: "合成内置技能：常见诉讼期限速查（演示用）", body: "内置合成技能正文（合成材料）。" },
  // 功能 #4 办案时间线（RE-4 §3 技能类附加）：触发族 /时间线（文案自写，真源在 skill-presets 包）
  { id: "juscite-builtin-timeline-generation", name: "办案时间线整理（内置合成）", description: "从案件材料抽取事实时间线：表格/时间轴图/结构化清单三格式（/时间线）", body: TIMELINE_SKILL_MD,
    triggers: TIMELINE_SKILL_META.triggers, aliasIds: [TIMELINE_SKILL_META.id], rootPath: "implementation/skill-presets/timeline-generation" },
  // 功能 #16 调研报告（RE-16 §3 技能类附加，对拍 50）：触发族 /research、/调研（真源在 skill-presets 包）
  { id: "juscite-builtin-research", name: "法律调研助手（内置合成）", description: "课题→多来源检索→结构化调研报告：四层方法+五节报告（/research、/调研）", body: RESEARCH_SKILL_MD,
    triggers: RESEARCH_SKILL_META.triggers, aliasIds: [RESEARCH_SKILL_META.id], rootPath: "implementation/skill-presets/research" },
  // 功能 #42 电子数据取证（RE-42 §3.4 技能注入，对拍规格必配）：触发词族+/edisc（真源在 skill-presets/edisc 包）
  { id: "juscite-builtin-edisc", name: `${EDISC_SKILL_META.name}（内置合成）`, description: EDISC_SKILL_META.description, body: EDISC_SKILL_MD,
    triggers: EDISC_SKILL_META.triggers, aliasIds: [EDISC_SKILL_META.id], rootPath: "implementation/skill-presets/edisc" },
  // 【施工波三轮·#7 证据目录全量面】主技能：证据目录生成（RE-7 §3 技能包；触发族 /evidencecat+
  // 证据目录/证据清单/证据组织/证据管理；真源在 skill-presets/evidence-catalog 包）
  { id: "juscite-builtin-evidence-catalog", name: `${EVIDENCE_CATALOG_SKILL_META.name}（内置合成）`, description: EVIDENCE_CATALOG_SKILL_META.description, body: EVIDENCE_CATALOG_SKILL_MD,
    triggers: EVIDENCE_CATALOG_SKILL_META.triggers, aliasIds: [EVIDENCE_CATALOG_SKILL_META.id], rootPath: "implementation/skill-presets/evidence-catalog" },
  // 【施工波三轮·#7 证据目录全量面】姊妹技能：证据材料整理（RE-7 §3；触发族 /evidencezheng+
  // 整理证据/制作证据/证据合集/证据材料整理；与主技能共享"证据目录/证据清单"词族→双技能同回合命中，
  // id 字典序 juscite-builtin-evidence-catalog 排前；真源在 skill-presets/evidence-materials 包）
  { id: "juscite-builtin-evidence-materials", name: `${EVIDENCE_MATERIALS_SKILL_META.name}（内置合成）`, description: EVIDENCE_MATERIALS_SKILL_META.description, body: EVIDENCE_MATERIALS_SKILL_MD,
    triggers: EVIDENCE_MATERIALS_SKILL_META.triggers, aliasIds: [EVIDENCE_MATERIALS_SKILL_META.id], rootPath: "implementation/skill-presets/evidence-materials" },
];
const skillsUserState = new Map(); // skillId -> enabled
// 【施工波三轮·#7 全量面】技能激活注册表（RE-7 §3 技能类附加）：builtin=native（四通道自动激活）；
// 用户根 zip 技能=supplemental（默认不自动注入，仅显式点名——对齐竞品 supplemental 语义）。
// disabled 技能不参与激活。数据单源=BUILTIN_SKILLS 的 triggers/rootPath + 各 skill.json 真源。
function buildSkillRegistry() {
  const builtins = BUILTIN_SKILLS
    .filter((b) => skillsUserState.get(b.id) !== false)
    .map((b) => ({
      id: b.id, aliasIds: b.aliasIds, name: b.name, description: b.description, body: b.body,
      triggers: b.triggers, priority: 0, scope: "builtin", rootPath: b.rootPath ?? "builtin",
    }));
  const users = listInstalledSkillDirs().map((dir) => {
    const d = describeInstalledSkill(dir);
    const id = `user-${d.name}`;
    return {
      id, name: d.name, description: d.description, body: d.body,
      scope: "user", autoInject: false, rootPath: dir, // supplemental：默认不自动注入（explicit 点名仍可）
      enabled: skillsUserState.get(id) !== false,
    };
  }).filter((u) => u.enabled);
  return [...builtins, ...users];
}
/** 回合技能激活（桥侧装配：消息文本+会话附件名→注入计划；threadKind=knowledge-qa 整体短路）。 */
function planTurnSkills({ text, attachmentFilenames, threadKind }) {
  try {
    return planSkillInjection({ skills: buildSkillRegistry(), text, attachmentFilenames, threadKind });
  } catch { // 激活失败不阻塞对话（同记忆/材料注入先例）
    return { activations: [], block: null, skippedOverBudget: [] };
  }
}
const skillsService = {
  list: async () => {
    const skills = [
      ...BUILTIN_SKILLS.map((b) => ({
        id: b.id, name: b.name, description: b.description, body: b.body, path: "",
        scope: "plugin", enabled: skillsUserState.get(b.id) ?? true,
        pluginName: "juscite-builtin", pluginId: "juscite-builtin",
      })),
      ...listInstalledSkillDirs().map((dir) => {
        const d = describeInstalledSkill(dir);
        const id = `user-${d.name}`;
        return {
          id, name: d.name, description: d.description, body: d.body,
          path: join(dir, "SKILL.md"), scope: "user",
          enabled: skillsUserState.get(id) ?? true,
        };
      }),
    ];
    return { skills, capability: { userScopeAvailable: true }, diagnostics: [] };
  },
  setEnabled: async (p) => { skillsUserState.set(p?.skillId, !!p?.enabled); },
  // 【施工波三轮·#7 全量面】buildPromptContext 真实现（RE-7 对拍 1~8/1a 桥面）：激活引擎算
  // 注入计划（explicit/command/pattern/fileType 四通道+预算 24000 字节+上限 3），返回增强后
  // prompt 与 activatedSkillNames（此处无附件面，fileType 通道按消息内扩展名扫描生效）。
  buildPromptContext: async (p) => {
    const prompt = p?.prompt ?? "";
    const plan = planTurnSkills({ text: prompt, threadKind: "conversation" });
    return {
      prompt: plan.block ? prompt + "\n\n" + plan.block : prompt,
      activatedSkillNames: plan.activations.map((a) => a.skill.name),
    };
  },
  copyToCommon: async (p) => ({ newPath: join(skillsRoot(), String(p?.skillId ?? "skill")) }),
  removeFromCommon: async (p) => {
    const id = String(p?.skillId ?? "");
    if (id.startsWith("juscite-builtin")) throw new Error("内置合成技能不可移除");
    removeSkillDir(id.replace(/^user-/, ""));
  },
  deleteSkill: async (p) => {
    const id = String(p?.skillId ?? "");
    if (id.startsWith("juscite-builtin")) throw new Error("内置合成技能不可删除");
    if (!removeSkillDir(id.replace(/^user-/, ""))) throw new Error(`技能不存在：${id}`);
  },
  installSkillArchive: async (p) => {
    const bytes = Buffer.from(String(p?.archiveBase64 ?? ""), "base64");
    const parsed = parseZip(bytes); // 格式校验/解压/CRC 全在此
    const installed = installSkillArchiveEntries(parsed);
    console.log(`[bridge] skill zip installed: ${installed.name} (${installed.format})`);
    return installed;
  },
};
services.register(ISkillsService, skillsService);
services.register({ channelName: "model-selection" }, modelSelectionService);
// 3.16.2 新 UI 面精修：highspeed-card（发送链 prepareTurn/getSnapshot；silentStub 返回 undefined 会让
// SessionPane 读 serviceSnapshot.card 直接崩子树——用户真机 React subtree crashed 根因）
const highspeedCardService = {
  prepareTurn: async () => ({ kind: "fallback", reason: "draw-miss", nextDrawAt: null }),
  getSnapshot: async () => ({ card: null }),
  invalidateCard: async () => true,
  healthy: async () => ({ cardId: "", promptTokens: 0, completionTokens: 0, durationSeconds: 0 }),
};
services.register({ channelName: "highspeed-card" }, highspeedCardService);
// system.info 精修：useWorkspaceHomePath 读 info.homedir（undefined.homedir 崩 uncaught promise）
const systemServiceExact = new Proxy(
  { info: async () => ({ homedir: "C:/Users/being", platform: "win32", version: "3.16.2-bridge" }) },
  { get: (t, prop) => (prop in t ? t[prop] : (typeof prop === "string" && prop.startsWith("on") ? silentEvent() : async () => undefined)) },
);
services.register({ channelName: "system" }, systemServiceExact);
// 3.16.2 发送路径第二阻塞项：project 面（createSession 带 projectId 后查项目目录/树/会话准备）
// 空态=单项目 lvyin-demo（与 mock 侧栏一致），不伪造多项目。
const SYNTH_VIRTUAL_PROJECT = () => ({
  id: "lvyin-demo",
  hostId: "local",
  name: "lvyin-demo",
  nameOverridden: false,
  roots: [{ rootPath: WORKSPACE.path, position: 0, isPrimary: true }],
  position: 0,
  pinned: false,
  deleted: false,
  createdAt: Date.now(),
  updatedAt: Date.now(),
});
const projectServiceExact = new Proxy(
  {
    // 合同（project-storage/contract.ts）：readTree→{projects: VirtualProject[], tasks}
    readDirectory: async () => ({ path: WORKSPACE.path, entries: [] }),
    readProjects: async () => [SYNTH_VIRTUAL_PROJECT()],
    readTree: async () => ({ projects: [SYNTH_VIRTUAL_PROJECT()], tasks: synthTaskMetas() }),
    prepareSession: async () => ({ workspacePath: WORKSPACE.path, additionalDirectories: [], projectId: "lvyin-demo" }),
    resolveSessionDirectories: async () => ({ workspacePath: WORKSPACE.path, additionalDirectories: [], projectId: "lvyin-demo" }),
    moveTask: async () => {},
    saveProject: async () => SYNTH_VIRTUAL_PROJECT(),
    deleteProject: async () => {},
    reorderProjects: async () => {},
  },
  {
    get: (t, prop) => (prop in t ? t[prop] : (typeof prop === "string" && prop.startsWith("on") ? silentEvent() : async () => undefined)),
  },
);
services.register({ channelName: "project" }, projectServiceExact);
// 3.16.2 发送路径阻塞项：remote-projects 面缺失时 UI 调用 1000ms 超时 → 整个发送被判死
// （真机"发送失败，请稍后重试 / Channel remote-projects timed out"根因）。律引无远端主机，全部空态。
services.register({ channelName: "remote-projects" }, new Proxy(
  {
    readDirectory: async () => ({ hosts: [], entries: [] }),
    connectHost: async () => { throw new Error("律引未配置远端主机"); },
    saveHost: async () => { throw new Error("律引未配置远端主机"); },
    removeHost: async () => {},
    addEntry: async () => { throw new Error("律引未配置远端主机"); },
    refreshEntry: async () => {},
    removeEntry: async () => {},
  },
  {
    get: (t, prop) => (prop in t ? t[prop] : (typeof prop === "string" && prop.startsWith("on") ? silentEvent() : async () => undefined)),
  },
));
// 3.16.2 输入区模型控件崩溃链（V4ComposerModelControls）：依赖 coding-plan 套餐面与配置文件面
const codingPlanSubscriptionExact = new Proxy(
  {
    getDynamicWorkflowClientConfig: async () => ({ enabled: false }),
    getEnterprisePricing: async () => ({ plans: [] }),
  },
  {
    get: (t, prop) => (prop in t ? t[prop] : (typeof prop === "string" && prop.startsWith("on") ? silentEvent() : async () => undefined)),
  },
);
services.register({ channelName: "coding-plan-subscription" }, codingPlanSubscriptionExact);
const providerConfigFileExact = new Proxy(
  { getWorkspaceProviderConfigFile: async () => null },
  {
    get: (t, prop) => (prop in t ? t[prop] : (typeof prop === "string" && prop.startsWith("on") ? silentEvent() : async () => undefined)),
  },
);
services.register({ channelName: "zcode-task-config" }, providerConfigFileExact);
// window-controller 3.16.2 任务列表订阅（windowControllerTaskListRegistry 读 result.ack.subscriptionId；
// 挂到既有 silentStub 之上——proxy 命中前置方法，其余仍走兜底）
services.register({ channelName: "window-controller" }, new Proxy(
  {
    subscribeControllerV4: async () => ({ ack: { subscriptionId: "sub_wc_" + randomUUID().slice(0, 8), mode: "snapshot", logEpoch: CONV_LOG_EPOCH } }),
    unsubscribeControllerV4: async () => {},
  },
  {
    get: (target, prop) => {
      if (prop in target) return target[prop];
      if (typeof prop === "string" && prop.startsWith("onDynamic")) return () => silentEvent();
      if (typeof prop === "string" && prop.startsWith("on")) return silentEvent();
      return async () => undefined;
    },
  },
));
services.register({ channelName: "provider-settings" }, providerSettingsService);
services.register({ channelName: "oauth" }, oauthService);
services.register({ channelName: "file" }, fileService);
services.register({ channelName: "settings-sync" }, settingsSyncService);

// ── 任务三补面（R3 遗留 + 基线走查新发现）────────────────────────────
// plugin-management：真薄服务包装 agentService（形状/演进收口在官方实现一处，桥不另造协议词）
services.register(IPluginManagementService, createPluginManagementService({ zcodeAgentService: agentService }));
// ── 功能#27 所内分享（步骤3 树内开闸）：上游分享服务整包 + 桥面本机分享站 ────────────
// 云端分享站在本产品不可用（红线③材料不出域）；HttpClient 指向本桥 HTTP 面的分享站路由，
// shareWebUrl 同源 → 发布回链 = http://127.0.0.1:<port>/cn/share/<code>，材料全程本机不出站。
const shareStation = createShareStation({ port: PORT });
const conversationShareService = new ConversationShareService({
  zcodeAgentService: agentService,
  client: new ConversationShareHttpClient({
    apiClient: { request: (url, init = {}) => fetch(url, { ...init, signal: AbortSignal.timeout(init.timeoutMs ?? 15_000) }) },
    baseUrl: `http://127.0.0.1:${PORT}/api/v1`,
    tokenProvider: async () => "juscite-bridge-local-share", // 本机站不校验；客户端合同要求写操作携带非空 token
  }),
  artifactSource: createLocalConversationShareArtifactSource(),
  // 导入通道本站未开放（分享站 continuation 恒拒 3214）；落盘根仍显式钉在 Juscite 域内。
  conversationWorkspaceRoot: join(homedir(), "AppData", "Roaming", "Juscite", "bridge", "share-imports"),
  shareWebUrl: `http://127.0.0.1:${PORT}/cn/share`,
});
services.register(IConversationShareService, conversationShareService);
// subagents：UI 侧栏子代理上下文（subagentsContextStore.list/setEnabled）——合成空态
services.register(ISubagentsService, {
  list: async () => ({ agents: [], userAgents: [], pluginAgents: [], capability: { userScopeAvailable: false } }),
  setEnabled: async () => { throw new Error("合成桥未接子代理启停（桩）"); },
});
// off-peak-task：错峰任务（基线走查 1s 超时刷屏源）——合成空态；unsupported 诚实上报（无套餐面）
services.register(IOffPeakTaskService, {
  getCodingPlanSupport: async () => ({ supported: false, reason: "jwt_missing" }),
  getTakeNumberAvailability: async () => ({ canTakeNumber: false }),
  createTask: async () => { throw new Error("合成桥未接错峰任务创建（桩）"); },
  cancelTask: async () => null,
  pauseTask: async () => null,
  continueTask: async () => null,
  deleteTask: async () => {},
  deleteHistory: async () => null,
  updateTask: async () => null,
  list: async () => [],
  get: async () => null,
});

const server = http.createServer(async (req, res) => {
  // 功能#27：本机分享站路由（/api/v1/shares/* + /cn/share/*、/share/*）最先分发
  try {
    if (await shareStation.handle(req, res, new URL(req.url ?? "/", "http://localhost").pathname)) return;
  } catch (e) {
    console.error("[share-station] handler error:", e?.message ?? e);
    if (!res.headersSent) {
      res.writeHead(500, { "content-type": "application/json" });
      res.end(JSON.stringify({ code: 3001, msg: "分享站内部错误" }));
    }
    return;
  }
  if (req.url === "/api/legal") {
    // M3 八法律面合成数据（真源接线随 M2 尾巴；fail-closed：缺数据即空数组）
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({
      materials: [
        { id: "mat_001", name: "合成：借款合同扫描件.pdf", status: "已解析 · 12 条款" },
        { id: "mat_002", name: "合成：转账凭证（3 笔）.xlsx", status: "已对账" },
        { id: "mat_003", name: "合成：微信聊天记录导出.txt", status: "已脱敏" },
      ],
      review: [
        { aspect: "主体资格", finding: "双方主体明确，签署权限未见瑕疵", severity: "通过" },
        { aspect: "利率条款", finding: "约定年利率 12%，在 LPR 四倍上限内", severity: "通过" },
        { aspect: "违约金", finding: "日万分之五偏高，诉讼中可能被酌减", severity: "提示" },
        { aspect: "担保", finding: "仅有保证人签字，未约定保证方式（按一般保证处理）", severity: "风险" },
        { aspect: "管辖", finding: "约定原告所在地法院管辖，有效", severity: "通过" },
      ],
      citations: [
        { source: "《民法典》第 188 条（三年诉讼时效）", valid: "valid", note: "现行有效" },
        { source: "《民间借贷司法解释》第 25 条（LPR 四倍上限）", valid: "valid", note: "现行有效" },
        { source: "某地方高院会议纪要（示例失效条目）", valid: "invalid", note: "已被新纪要替代（fail-closed 示例）" },
      ],
      schedule: [
        { id: "sch_001", title: "举证期限届满", due: "2026-11-05", kind: "举证" },
        { id: "sch_002", title: "开庭（第一次）", due: "2026-11-20 09:30", kind: "开庭" },
        { id: "sch_003", title: "上诉期届满", due: "2026-12-05", kind: "上诉" },
      ],
      calc: [
        { name: "违约金试算", input: "本金 200,000 元 × 日万分之五 × 90 天", result: "9,000.00 元" },
        { name: "诉讼时效剩余", input: "起算 2024-08-01，三年期", result: "剩余约 281 天" },
      ],
      documents: [
        { id: "doc_001", title: "民事起诉状（草稿 v3）", status: "待确认事实部分" },
        { id: "doc_002", title: "证据清单", status: "已生成" },
      ],
    }));
    return;
  }
  // 功能 #13 法条手册（RE-13 §3.2 新增端点族）：/api/legal/laws*（categories/search/detail/过滤/收藏/历史）
  // 与 /api/legal/packs*（包管理面）。M3 八法律面既有合成桩 /api/legal 原样保留（前端 LegalWorkbench 在用）。
  if (req.url?.startsWith("/api/legal/laws") || req.url?.startsWith("/api/legal/packs")) {
    const handled = await lawbook.httpHandler(req, res, new URL(req.url ?? "/", "http://localhost"));
    if (handled) return;
  }
  // 功能 #14 引证核验（RE-14 §3.3 新增端点族）：/api/verify/citation{,/config,/history} + /api/verify/document。
  if (req.url?.startsWith("/api/verify/")) {
    const handled = await citationVerify.httpHandler(req, res, new URL(req.url ?? "/", "http://localhost"));
    if (handled) return;
  }
  // 功能 #6 材料上传解析（RE-6 §3 HTTP 面）：/api/cases/materials*（multipart/JSON 双形态上传、
  // 列表/详情/检索/原件；100MB 上限 413、缺失案件上传 404/列表 200 双空、本地鉴权挂点 401）
  // 与 /api/attachments*（内容寻址附件库，作用域授权读取）。
  if (req.url?.startsWith("/api/cases/materials") || req.url?.startsWith("/api/attachments")) {
    const handled = await materials.httpHandler(req, res, new URL(req.url ?? "/", "http://localhost"));
    if (handled) return;
  }
  // 功能 #42 电子数据取证（RE-42 §3 HTTP 面）：/api/edisc/*（源登记/扫描/画像/行面/搜索/归类/
  // 候选清单+校验+确认+元数据干跑/锚回跳/页卡/批注/审查标注/审查报告/精化留痕）。
  if (req.url?.startsWith("/api/edisc/")) {
    const handled = await edisc.httpHandler(req, res, new URL(req.url ?? "/", "http://localhost"));
    if (handled) return;
  }
  // 功能 #32 整理与尽调（RE-32 §3 HTTP 面）：/api/diligence/*（看板/任务动作/成果版本/字段模板三态一源/
  // 批量提取异步轮询/台账查看编辑回溯 CSV/清单整理缺失核对/沿革汇集章节 Word）。
  if (req.url?.startsWith("/api/diligence/")) {
    const handled = await diligence.httpHandler(req, res, new URL(req.url ?? "/", "http://localhost"));
    if (handled) return;
  }
  if (req.url === "/api/dev/sse-drop") {
    // 任务二 e2e 注入面：强制断开 oc28 SSE（自动重连）。验证断线重连不丢增量（RE-B2 §5 对拍 6）。
    sseHandle?.drop();
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ dropped: true, reconnect: "auto" }));
    return;
  }
  if (req.url === "/api/server-info") {
    res.writeHead(200, { "content-type": "application/json" });
    // store=sqlite：持久化能力标记（ci_gate 据此判旧桥并先升级再测，RE-B1 §5 升级代偿）；
    // kb=知识库面能力代（#20）：旧桥缺标记时走查/门禁可判旧换新。
    // license=F78/F79 形态判定表（RE-B3 §3.5；wire 面只出 state/tier/reason/modules，无凭据字段）。
    // 放行条件②（RE-B3 §5）钉死：判定表消费必须桥侧执行——本面=本地匿名 HTTP 可读（server.listen 未绑
    // 127.0.0.1，既有面），前端读 modules 自行隐藏/开启入口=客户端旁路，解挂接消费方时禁走此面。
    res.end(JSON.stringify({
      version: "mock-1.0", store: "sqlite", kb: 1, workspaces: [WORKSPACE],
      // 桥内机制件能力标记（施工单-06；wire 自测据旧桥缺标记判旧换新，同 kb 标记惯例）
      taskshell: 1, flowgate: 1,
      lawbook: 1, // 功能 #13 法条手册能力标记（旧桥缺标记判旧换新，同 kb/taskshell 惯例）
      citation: 1, // 功能 #14 引证核验能力标记（旧桥缺标记判旧换新，同 kb/lawbook 惯例）
      edisc: 1, // 功能 #42 电子数据取证能力标记（旧桥缺标记判旧换新，同上惯例）
      diligence: 1, // 功能 #32 整理与尽调能力标记（旧桥缺标记判旧换新，同上惯例）
      license: { state: LICENSE_SHAPE.state, tier: LICENSE_SHAPE.tier, reason: LICENSE_SHAPE.reason, modules: LICENSE_SHAPE.modules },
    }));
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

// ---------- 启动恢复 + 崩溃遗留结算（RE-B1 §3.4；F3：恢复后不允许任何会话停留 running/busy） ----------
const restoredSessions = store.listSessions();
for (const rec of restoredSessions) {
  const st = convStateOf(rec.session_id);
  st.oc28Id = rec.oc28_id ?? null;
  st.seq = rec.seq;
  st.phase = rec.phase;
  st.busy = !!rec.busy;
  st.lastCommandId = rec.last_command_id ?? null;
  const meta = JSON.parse(rec.meta_json || "{}");
  st.oc28SeenIds = Array.isArray(meta.oc28SeenIds) ? meta.oc28SeenIds : [];
  st.lastError = meta.lastError ?? null;
  st.kbCtx = meta.kbCtx && typeof meta.kbCtx === "object" ? meta.kbCtx : null; // #20 问答线程上下文档还原（B48）
  st.attachmentIds = Array.isArray(meta.attachmentIds) ? meta.attachmentIds : []; // #6 对话附件跨回合继承还原
  // 整行对象还原（F4：rowId/turnId/createdAt/createdAtSeq/actions/origin/model 等全字段保真）
  st.rows = store.listRows(rec.workspace_key, rec.session_id).map((r) => JSON.parse(r.row_json));
  st.rowSeq.n = st.rows.reduce((m, r) => Math.max(m, r.rowId ?? 0), rec.row_seq);
  liveSessions.set(rec.session_id, {
    sessionId: rec.session_id, workspaceId: rec.workspace_key, title: rec.title,
    titleSource: rec.title ? "generated" : "default",
    workspacePath: rec.workspace_path ?? WORKSPACE.path, projectId: rec.project_id ?? null,
    phase: rec.phase, sessionEnded: rec.phase === "completedSuccess", hasBackgroundWork: false,
    lastActivityAt: rec.updated_at, createdAt: rec.created_at,
    ...(rec.last_outcome ? { lastOutcome: rec.last_outcome } : {}),
  });
}
console.log(`[bridge] restored ${restoredSessions.length} session(s) from ${store.dbPath}`);
// 恢复的终态回执直接入缓存：重放同 envelope 得存档 ack（行必已落，F1②），非终态回执本就不落库
for (const r of store.listReceipts()) {
  const topicId = `sessions-index/${r.workspace_key}`;
  commandReceipts.set(JSON.stringify([topicId, r.session_id, r.command_id]), Promise.resolve(JSON.parse(r.ack_json)));
}
async function settleCrashedSession(rec) {
  const sid = rec.session_id;
  const st = convStates.get(sid);
  const summary = liveSessions.get(sid);
  const commandId = rec.last_command_id ?? null;
  const ack = { commandId: commandId ?? "cmd_unknown", status: "accepted", revisionAtDecision: 1 };
  const finishError = (message, withReceipt) => {
    st.phase = "error";
    st.busy = false;
    st.lastError = { code: "bridge.restartInterrupted", message, recoverable: true, at: Date.now(), source: "provider" };
    const pti = "pt_" + randomUUID().slice(0, 8);
    const header = { ...baseRow(st, "turn_restart", pti), kind: "turnHeader", origin: "userInput", executionKind: "agent", state: "failed", startedAt: Date.now(), endedAt: Date.now() };
    const errRow = { ...baseRow(st, "turn_restart", pti), kind: "assistantText", text: message, state: "failed", model: "deepseek-chat" };
    st.rows.push(header, errRow);
    persistRow(sid, header);
    persistRow(sid, errRow);
    if (withReceipt && commandId) persistReceipt(sid, commandId, ack, "failed");
    Object.assign(summary, { phase: st.phase, sessionEnded: false, lastOutcome: "error", lastActivityAt: Date.now() });
    persistSessionState(sid);
    console.log(`[bridge] settle: ${sid} -> error (${message.slice(0, 60)})`);
  };
  try {
    if (!st.oc28Id) return finishError("桥重启中断：会话尚未建立模型连接，原消息未被处理", true);
    const msgs = await runtime.pullTranscript(st.oc28Id);
    const seen = new Set(st.oc28SeenIds ?? []);
    const fresh = msgs
      .filter((e) => !seen.has(e.messageId) && e.role === "assistant" && !e.error)
      .sort((a, b) => a.createdAt - b.createdAt);
    const full = fresh
      .map((e) => e.text)
      .filter(Boolean).join("\n\n");
    if (full && fresh.some((e) => e.completedAt)) {
      // 崩溃前 oc28 已收到完整回复：补行转 completedSuccess + 终态回执（重放不再吞命令）
      const pti = "pt_" + randomUUID().slice(0, 8);
      const header = { ...baseRow(st, "turn_restart", pti), kind: "turnHeader", origin: "userInput", executionKind: "agent", state: "completedSuccess", startedAt: Date.now(), endedAt: Date.now() };
      const row = { ...baseRow(st, "turn_restart", pti), kind: "assistantText", text: full, state: "complete", model: "deepseek-chat", sourceCommandId: commandId };
      st.rows.push(header, row);
      st.oc28SeenIds = [...(st.oc28SeenIds ?? []), ...fresh.map((e) => e.messageId)];
      st.phase = "completedSuccess";
      st.busy = false;
      st.lastError = null;
      persistRow(sid, header);
      persistRow(sid, row);
      if (commandId) persistReceipt(sid, commandId, ack, "completed");
      Object.assign(summary, { phase: st.phase, sessionEnded: true, lastOutcome: "completed", lastActivityAt: Date.now() });
      persistSessionState(sid);
      console.log(`[bridge] settle: ${sid} -> completedSuccess (recovered replyLen=${full.length})`);
    } else {
      const errMsg = [...msgs].reverse().find((e) => e.error);
      finishError(errMsg ? `桥重启中断：模型返回错误（${errMsg.error}）` : "桥重启中断：模型回复未完成，请重发消息", true);
    }
  } catch (e) {
    // oc28 不可达：不伪造终态回执（该命令重放可重执行），但绝不留 running 相位（F3）
    st.phase = "error";
    st.busy = false;
    st.lastError = { code: "bridge.settleUnavailable", message: `桥重启对账失败：${e?.message ?? String(e)}`, recoverable: true, at: Date.now(), source: "provider" };
    Object.assign(summary, { phase: "error", sessionEnded: false, lastOutcome: "error", lastActivityAt: Date.now() });
    persistSessionState(sid);
    console.error(`[bridge] settle: ${sid} oc28 unavailable:`, e?.message ?? e);
  }
}
for (const rec of restoredSessions.filter((r) => r.phase === "running" || r.busy)) {
  await settleCrashedSession(rec);
}

// 功能 #22：崩溃遗留结算后再开调度（首次 tick 立即补认领，错过窗口按 misfire 如实记 skipped）
startAutomationScheduler();
// 【步骤4·#26】团队网络自启（F1 等量：已配置身份即拉起监听+mDNS 广播+周期同步，启动先跑一轮）
teamSync.startIfConfigured();

// ══ 【步骤4·#18 学习迭代】运行时装配 + 六命令面（RE-18 §3.5；J14/J15）══
// 存储根=%APPDATA%\Juscite\bridge\learning-iterations\（BRIDGE_LEARNING_ROOT 仅测试覆盖；
// 红线：只碰 Juscite 分区）。IO 全注入：线程/材料/知识/技能/回合链/审计，学习回合复用
// runAssistantTurn（桥会话链路等价 side 线程+纯文本分析，§3.5）。
const LEARNING_ROOT = process.env.BRIDGE_LEARNING_ROOT
  || join(homedir(), "AppData", "Roaming", "Juscite", "bridge", "learning-iterations");
function learningThreadTitle(runId) { return `${LEARNING_THREAD_PREFIX} ${runId}`; } // D1 标题前缀（自有标识）
async function learningTurn({ runId, prompt, shouldCancel }) {
  // D1/D3：独立 side 线程（独立工作区键+专属标题）；1.5s 轮询收口；4h 顶（桥回合自身 150s 熔断更紧，先到先停）
  const threadId = "ses_lr_" + randomUUID().slice(0, 8);
  liveSessions.set(threadId, {
    sessionId: threadId, workspaceId: LEARNING_WORKSPACE_KEY,
    title: learningThreadTitle(runId), titleSource: "generated",
    workspacePath: WORKSPACE.path, projectId: null,
    phase: "draft", sessionEnded: false, hasBackgroundWork: false,
    lastActivityAt: Date.now(), createdAt: Date.now(),
  });
  const st = convStateOf(threadId);
  const ack = { commandId: "cmd_" + randomUUID().slice(0, 8), status: "accepted", revisionAtDecision: 1 };
  const turnId = "turn_" + randomUUID().slice(0, 8);
  const pti = "pt_" + randomUUID().slice(0, 8);
  const userRow = { ...baseRow(st, turnId, pti, { canEdit: false }), kind: "userInput", origin: "realUser", text: prompt, sourceCommandId: ack.commandId };
  st.rows.push(userRow);
  persistRow(threadId, userRow);
  const summary = liveSessions.get(threadId);
  summary.phase = "running";
  st.phase = "running";
  st.lastError = null;
  st.lastCommandId = ack.commandId;
  persistSessionState(threadId);
  const turnHeaderRow = { ...baseRow(st, turnId, pti), kind: "turnHeader", origin: "userInput", executionKind: "agent", state: "running", startedAt: Date.now() };
  st.rows.push(turnHeaderRow);
  persistRow(threadId, turnHeaderRow);
  runAssistantTurn(threadId, ack, turnId, pti, turnHeaderRow, prompt, { model: BRIDGE_MODEL, learningThread: true });
  const deadline = Date.now() + TURN_TIMEOUT_MS;
  while (st.busy && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 1500)); // D3 轮询 1.5s
    if (shouldCancel?.()) { return { ok: false, error: "用户取消了本轮学习" }; } // D5 轮内取消位
  }
  const rows = st.rows.filter((r) => r.kind === "assistantText");
  const lastComplete = [...rows].reverse().find((r) => r.state === "complete");
  if (!lastComplete || !(lastComplete.text ?? "").trim()) {
    return { ok: false, error: st.lastError?.message ?? "学习回合未产出可解析文本" };
  }
  return { ok: true, text: lastComplete.text };
}
function learningListThreads() {
  // 主列表（内存）+ 持久会话（重启后仍在库的）合并；学习工作区线程照列（忙门/语料两侧各自排除）
  const byId = new Map();
  for (const s of liveSessions.values()) {
    byId.set(s.sessionId, { id: s.sessionId, title: s.title ?? "", workspaceKey: s.workspaceId, phase: s.phase, updatedAt: s.lastActivityAt });
  }
  try {
    for (const r of store.listSessions()) {
      if (!byId.has(r.session_id)) {
        byId.set(r.session_id, { id: r.session_id, title: r.title ?? "", workspaceKey: r.workspace_key, phase: r.phase ?? "draft", updatedAt: Number(r.updated_at) || 0 });
      }
    }
  } catch { throw new Error("线程列表读取失败"); } // A6 线程面失败→保守忙
  return [...byId.values()];
}
function learningThreadRows(id) {
  const st = convStates.get(id);
  if (st) return st.rows;
  for (const wk of new Set([WORKSPACE_KEY, KB_WORKSPACE_KEY, RESEARCH_WORKSPACE_KEY, LEARNING_WORKSPACE_KEY])) {
    const rows = store.listRows(wk, id);
    if (rows.length) return rows.map((r) => { try { return JSON.parse(r.row_json); } catch { return null; } }).filter(Boolean);
  }
  return [];
}
function learningMaterialsList() {
  const dir = materialsDirOf(WORKSPACE.path);
  const out = [];
  let entries = [];
  try { entries = readdirSync(dir, { withFileTypes: true }); } catch { return out; }
  for (const e of entries) {
    if (!e.isFile()) continue;
    try {
      const st = statSync(join(dir, e.name));
      out.push({ name: e.name, abs: join(dir, e.name), sizeBytes: st.size });
    } catch { /* 单文件 stat 失败跳过 */ }
  }
  return out;
}
try {
  learningRuntime = createLearningRuntime({
    root: LEARNING_ROOT,
    loadSettings: () => loadSetting().learningIteration,
    listThreads: learningListThreads,
    threadRows: learningThreadRows,
    workspacePathOf: () => WORKSPACE.path,
    materialsList: learningMaterialsList,
    readMaterialText: (abs) => readFileSync(abs, "utf-8"),
    kbWalk: () => kbWalkFiles(),
    kbReadText: (abs, ext) => kbReadTextIfIndexable(abs, ext),
    kbRoot: () => KB_ROOT,
    kbSync: async () => { const fn = agentService.kbSync; if (typeof fn === "function") await fn.call(agentService, { maxFiles: 20000 }); }, // G4 写后触发知识库同步
    skillsRoot: () => skillsRoot(),
    skillsList: () => listInstalledSkillDirs().map((dir) => ({ id: dir.split(/[\\/]/).pop() ?? "", dir, md: describeInstalledSkill(dir).body ?? "" })),
    protectedSkillIds: () => BUILTIN_SKILLS.map((b) => b.id), // F6 内置/预设技能不可覆盖
    readDocxText: (abs) => extractDocxText(readFileSync(abs)),
    runTurn: learningTurn,
    auditWrite,
    pollMs: Number(process.env.BRIDGE_LEARNING_POLL_MS) > 0 ? Number(process.env.BRIDGE_LEARNING_POLL_MS) : 5 * 60_000, // A2 间隔可配默认 5 分钟
    log: (m) => console.log(m),
  });
  learningRuntime.start(); // A2 主进程启动即 sync 运行时+每 5 分钟轮询（unref 不阻退出）
} catch (e) {
  console.error("[bridge] learning runtime 初始化失败（六命令走未初始化兜底）：", e?.message ?? e);
  learningRuntime = null;
}
// J15 IPC 六命令：status/list/get/queue/cancel/rollback；未初始化全部兜底；get/rollback 的 id 过正则串校验
function learningRuntimeFallbackStatus() {
  return {
    enabled: false, eligibleToday: "disabled", queued: false, running: false, status: "disabled",
    message: "学习迭代已关闭", lastSuccessfulAt: null, lastCheckedAt: null, nextEligibleAt: null,
    baselineComplete: false, baselineProgress: 0, pendingSourceCount: 0, activeRunId: null, latest: null,
    idleMinutes: 15, keepRunningInTray: true,
  };
}
Object.assign(agentService, {
  learningStatus: async () => learningRuntime ? learningRuntime.status() : learningRuntimeFallbackStatus(),
  learningList: async () => learningRuntime ? { records: learningRuntime.listRecords() } : { ok: false, error: "学习迭代运行时尚未初始化" },
  learningGet: async (params) => {
    if (!learningRuntime) return { ok: false, error: "学习迭代运行时尚未初始化" };
    const id = String(params?.id ?? "");
    if (!/^[A-Za-z0-9._-]{1,128}$/.test(id)) throw new Error("非法记录 id");
    const detail = learningRuntime.readRecordDetail(id);
    if (!detail) throw new Error("记录不存在或档案损坏");
    return detail;
  },
  learningQueue: async () => learningRuntime ? learningRuntime.queue() : { ok: false, error: "学习迭代运行时尚未初始化" },
  learningCancel: async () => learningRuntime ? learningRuntime.cancel() : { ok: false, error: "学习迭代运行时尚未初始化" },
  learningRollback: async (params) => {
    if (!learningRuntime) return { ok: false, error: "学习迭代运行时尚未初始化" };
    const id = String(params?.id ?? "");
    if (!/^[A-Za-z0-9._-]{1,128}$/.test(id)) throw new Error("非法记录 id");
    const summary = await learningRuntime.rollback(id);
    return { ok: true, summary };
  },
});

// ══ 【步骤4·#36 分层记忆】运行时装配 + 十一命令面（RE-36 §3；对拍 12 行）══
// 存储根=%APPDATA%\Juscite\bridge\layered-memory\（BRIDGE_LAYERED_MEMORY_ROOT 仅测试覆盖；
// 红线②：只碰 Juscite 分区）。四层两作用域：用户级=个人偏好/操作纠正（跨案跟随律师，D2）；
// 项目级=项目约定/资源指引（随项目隔离，D3 全本地）。本地可读文件族（F1 Markdown/JSON）；
// 偏好 md 族可直接编辑新建（F16）、自动维护文件无手工写入入口（F17）、
// 可查看（原样读）+可清除（删文件/删作用域级，红线：用户数据可控）。
// 审计不入账：RE-30 §3.5 映射表无记忆域动作行，严格等量不增竞品没有的审计类别（r9 同款边界记档）。
const LAYERED_MEMORY_ROOT = process.env.BRIDGE_LAYERED_MEMORY_ROOT
  || join(homedir(), "AppData", "Roaming", "Juscite", "bridge", "layered-memory");
try {
  layeredMemory = createLayeredMemoryRuntime({
    root: LAYERED_MEMORY_ROOT,
    log: (m) => console.log(m),
  });
} catch (e) {
  console.error("[bridge] layered-memory runtime 初始化失败（命令面走未初始化兜底）：", e?.message ?? e);
  layeredMemory = null;
}
function memoryLayerReady() {
  if (!layeredMemory) throw new Error("分层记忆运行时尚未初始化");
  return layeredMemory;
}
Object.assign(agentService, {
  memoryLayerOverview: async () => memoryLayerReady().overview(), // 可查看：四层×两作用域概览+文件清单
  memoryLayerRead: async (params) => memoryLayerReady().readRaw(String(params?.rel ?? "")), // 可查看：原样读
  memoryLayerWrite: async (params) => memoryLayerReady().writeHandwritten(String(params?.rel ?? ""), String(params?.content ?? "")), // 手写族编辑（auto 拒=F17）
  memoryLayerClear: async (params) => params?.scope
    ? memoryLayerReady().clearScope(String(params.scope), params.projectId == null ? undefined : String(params.projectId)) // 清除：作用域级
    : memoryLayerReady().clearFile(String(params?.rel ?? "")), // 清除：删文件级
  memoryLayerCorrection: async (params) => memoryLayerReady().recordCorrection({ // 写入触发①：显式纠正
    scene: String(params?.scene ?? ""), wrong: String(params?.wrong ?? ""), right: String(params?.right ?? ""),
    origin: params?.origin == null ? undefined : String(params.origin),
  }),
  memoryLayerTaxonomyWrite: async (params) => memoryLayerReady().sedimentTaxonomy({ // 写入触发②：分类回写（F2/F4）
    projectId: String(params?.projectId ?? ""), treeKey: params?.treeKey, path: params?.path,
  }),
  memoryLayerRepresentativeWrite: async (params) => memoryLayerReady().sedimentRepresentative({ // 确认回写五要素（F12/F13）
    projectId: String(params?.projectId ?? ""), name: String(params?.name ?? ""),
    role: params?.role == null ? undefined : String(params.role),
    category: params?.category == null ? undefined : String(params.category),
    scale: params?.scale == null ? undefined : String(params.scale),
    date: params?.date == null ? undefined : String(params.date),
  }),
  memoryLayerGate: async (params) => memoryLayerReady().resolveGate({ // 置信门（F8/F9/F10/F11/F18）
    candidates: Array.isArray(params?.candidates) ? params.candidates : [],
    inputs: params?.inputs && typeof params.inputs === "object" ? params.inputs : {},
  }),
  memoryLayerInjectionPlan: async (params) => memoryLayerReady().injectionPlan({ // 注入装配预览（对账面）
    projectId: params?.projectId ?? null,
    category: params?.category == null ? undefined : String(params.category),
    turnText: params?.turnText == null ? undefined : String(params.turnText),
  }),
  memoryLayerResearchWrite: async (params) => memoryLayerReady().sedimentResearch({ // researched 沉淀（F5，F6 空不落）
    projectId: String(params?.projectId ?? ""), leafName: String(params?.leafName ?? ""), content: String(params?.content ?? ""),
  }),
  memoryLayerResearchGet: async (params) => memoryLayerReady().researchReuse({ // 复用查询（F5）
    projectId: String(params?.projectId ?? ""), leafName: String(params?.leafName ?? ""),
  }),
});

// ══ 【施工波-20261030·可视化B轨】#4 大事记表 / #19 庭审对抗图：注册点（桥面一行转发壳）══
// 机制契约实现在顶层自有包 @juscite/vizb（packages/juscite-vizb，AGPL-3.0 净室、四契约：
// 模型出语义 JSON/脚本算几何/文字=原句子序列/判据守卫清单），桥面只做参数形状核验+转发，
// 零几何零文案逻辑（插桩登记 contracts/pin-points.json #9）。摄入对账=两件共用前置（A7）。
Object.assign(agentService, {
  vizbChronicleCheck: async (params) => {
    if (!params || typeof params !== "object" || !params.factBase) throw new Error("factBase 不能为空（大事记事实底稿=既有事件账本投影视图）");
    const r = vizbChronicle.composeChronicle(params.factBase);
    return { ok: r.ok, refusal: r.refusal, schemaViolations: r.schemaViolations, guardViolations: r.guardViolations, artifactViolations: r.artifactViolations };
  },
  vizbChronicleRender: async (params) => {
    if (!params || typeof params !== "object" || !params.factBase) throw new Error("factBase 不能为空");
    const r = vizbChronicle.composeChronicle(params.factBase);
    if (!r.ok) throw new Error(r.refusal ?? "大事记判据守卫不成立，拒绝出表");
    return r.artifacts; // {wordXml, excelXml, briefSvgPages, factBaseJson} 四件同源交付
  },
  vizbConfrontationCheck: async (params) => {
    if (!params || typeof params !== "object" || !params.semantic) throw new Error("semantic 不能为空（对抗图语义 JSON=封闭 schema）");
    const r = vizbConfrontation.composeConfrontation(params.semantic);
    return { ok: r.ok, refusal: r.refusal, schemaViolations: r.schemaViolations, guardViolations: r.guardViolations, figureViolations: r.figureViolations };
  },
  vizbConfrontationRender: async (params) => {
    if (!params || typeof params !== "object" || !params.semantic) throw new Error("semantic 不能为空");
    const r = vizbConfrontation.composeConfrontation(params.semantic);
    if (!r.ok) throw new Error(r.refusal ?? "对抗图判据守卫不成立，拒绝出图");
    return r.artifacts; // {svg, analysisTableXml} 内部推演件·不对法院出示
  },
  vizbIntakeReconcile: async (params) => { // I 组共用前置：三态对账仅「该读没读」拒绝；明示不读放行留痕
    const pages = Array.isArray(params?.pages) ? params.pages : [];
    const skips = Array.isArray(params?.skips) ? params.skips : [];
    const manifest = Array.isArray(params?.manifest) ? params.manifest : [];
    return vizbChronicle.reconcileIntake(pages, skips, manifest);
  },
  // ── 【施工波二轮·可视化B轨收尾】①光栅化：SVG 交付件照出，另出 PNG（换单一族+日志报出）──
  vizbConfrontationPng: async (params) => {
    if (!params || typeof params !== "object" || !params.semantic) throw new Error("semantic 不能为空");
    const r = vizbConfrontation.composeConfrontation(params.semantic);
    if (!r.ok) throw new Error(r.refusal ?? "对抗图判据守卫不成立，拒绝出图");
    const png = await rasterizeSvgToPng(r.artifacts.svg);
    if (!png.ok) return { ok: false, skipped: true, reason: png.reason };
    return { ok: true, pngBase64: png.png.toString("base64"), byteSize: png.png.length, width: png.width, height: png.height, logs: png.logs };
  },
  vizbChronicleBriefPng: async (params) => {
    if (!params || typeof params !== "object" || !params.factBase) throw new Error("factBase 不能为空");
    const r = vizbChronicle.composeChronicle(params.factBase);
    if (!r.ok) throw new Error(r.refusal ?? "大事记判据守卫不成立，拒绝出表");
    const pages = [];
    const logs = [];
    for (let i = 0; i < r.artifacts.briefSvgPages.length; i++) {
      const png = await rasterizeSvgToPng(r.artifacts.briefSvgPages[i]);
      if (!png.ok) return { ok: false, skipped: true, reason: png.reason, pagesDone: i };
      pages.push({ pageNo: i + 1, pngBase64: png.png.toString("base64"), byteSize: png.png.length, width: png.width, height: png.height });
      logs.push(...png.logs.filter((l) => !logs.includes(l)));
    }
    return { ok: true, pages, logs };
  },
  // ── ②摄入对账接 #6 材料通道（A7 只读公开行为契约：listMaterials/readOriginal+公开抽取函数）──
  vizbIntakeFromMaterials: async (params) => {
    const caseId = String(params?.caseId ?? "");
    if (!caseId) throw new Error("caseId 不能为空（摄入对账的目标案件）");
    const skips = Array.isArray(params?.skips) ? params.skips : [];
    const list = materials.listMaterials(caseId, { latestOnly: true }); // 对拍 33 同源语义：只对最新版
    const pages = [];
    const manifest = [];
    const logs = [`[vizb-intake] #6 材料通道只读对账：案件 ${caseId} 最新版材料 ${list.latest.length} 份`];
    for (const m of list.latest) {
      manifest.push(vizbChronicle.manifestDocFromMaterial({
        docId: m.id, label: m.title,
        pageCount: m.parse?.pageCount ?? null,
        kind: m.error?.code === "NEEDS_OCR" ? "scan" : undefined, // 通道已判需 OCR=如实声明扫描件
      }));
      if (m.status !== "ready") {
        logs.push(`[vizb-intake] 《${m.title}》（${m.id}）未就绪（${m.error?.code ?? m.status}），无页文本——按该读没读处置（明示不读走 skips 留痕）`);
        continue;
      }
      try {
        const orig = materials.readOriginal(m.id); // 只读原件（不出域）
        const bytes = readFileSync(orig.storedPath);
        const lower = (m.filename ?? "").toLowerCase();
        if (lower.endsWith(".pdf")) {
          const { blocks } = extractPdfTextLayer(bytes); // 真 PDF 解析：页文本+页码（锚另从页文本剥）
          pages.push(...vizbChronicle.pagesFromPdfBlocks(m.id, blocks));
        } else if (lower.endsWith(".docx")) {
          pages.push({ docId: m.id, pageNo: 1, text: extractDocxMaterial(bytes) }); // #6 v1 扁平文本无页粒度——整文一页如实
        } else {
          pages.push({ docId: m.id, pageNo: 1, text: decodeTextBuffer(bytes).text });
        }
      } catch (e) {
        logs.push(`[vizb-intake] 《${m.title}》（${m.id}）页文本读取失败：${String(e?.message ?? e).slice(0, 80)}——按缺页对账`);
      }
    }
    const result = vizbChronicle.reconcileIntake(pages, skips, manifest);
    return { ...result, logs: [...logs, ...result.logs] };
  },
});

// ══ 【步骤5·F78/F79 许可骨架】桥启动读许可文件 → 形态判定（RE-B3 §3.3-3.5；骨架级）══
// 读取时机=启动一次、同步、listen 之前（判定表先于任何请求就绪；无热更无周期轮询，改许可重启生效）。
// 路径=%APPDATA%\Juscite\license\license.json（BRIDGE_LICENSE_FILE 仅测试覆盖；红线：只碰 Juscite 分区）。
// 三态：无文件 | 损坏（解析失败/结构非法/过期/不可读）=全基础形态（免费层全开、H1-H11 门全关）；
// 有合法许可=判定表按文件开关位读出。付费实体全挂起：开关只做判定输出（本日志+server-info），不接任何功能。
const LICENSE_SHAPE = readLicenseShape();

server.listen(PORT, () => {
  console.log(`[mock-host] listening http+ws on :${PORT} (synthetic data, dev-only)`);
  console.log(`[mock-host] setting file: ${MOCK_SETTING_PATH}`);
  // F78/F79 形态判定表挂启动日志（RE-B3 §3.4）：一行形态+一行 H1-H11 开关位；licenseId 非凭据仅本地日志。
  console.log(`[license] state=${LICENSE_SHAPE.state} tier=${LICENSE_SHAPE.tier} reason=${LICENSE_SHAPE.reason} path=${LICENSE_SHAPE.path}`
    + (LICENSE_SHAPE.licenseId ? ` licenseId=${LICENSE_SHAPE.licenseId}` : "")
    + (LICENSE_SHAPE.expiresAt ? ` expiresAt=${LICENSE_SHAPE.expiresAt}` : ""));
  console.log(`[license] modules=${JSON.stringify(LICENSE_SHAPE.modules)}`);
  // 【施工波三轮·桥健②】G6 连接器注册（listen 后异步落：预阻断→经 port 注册→oc28 运行时挂载）。
  // 失败具名记日志不拖垮桥（其余桥功能不依赖连接器在册；重注册幂等——PUT 覆盖挂载）。
  registerG6Connector().catch((e) => {
    console.error(`[bridge][g6] 连接器注册失败（桥继续运行，重连 oc28 后重启桥自动重试）：${e?.message ?? e}`);
  });
});
