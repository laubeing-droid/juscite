// 【步骤4·#18 学习迭代】学习纯模型（RE-18-学习迭代.md 实现规格 §3）。
// 桥/UI/合成自测单一来源（沿 researchModel/kb_service 先例）：七状态派生/资格与退避/忙门评估/
// 语料采集规则（RAG 剥离/打招呼过滤/掐头留尾/产物路径键/分块指纹/预算贪心/统一脱敏）/
// 学习提示词装配/输出解析三级容错+修复器/提案硬截断/三门验证（记忆/技能/知识）/发布账本/
// 用户报告装配/技术字样过滤/记录归一/原子写/回滚 preflight/记忆检索注入。
// 全部正则+状态机零模型（工作区铁律）；文案全部自写（表达隔离：等量≠抄文案）。
// 介质无关：fs/db 由调用方注入，本文件零 node 依赖（sha256 为文件内纯实现，浏览器可打包）。

// ── 品牌与标识（§5 明确不抄：竞品品牌串/Learning iteration 前缀/learning-artifact 标记均换自有）──
export const LEARNING_THREAD_PREFIX = "[学习迭代]";
export const LEARNING_ARTIFACT_MARKER = "juscite-learning-artifact";
export const KNOWLEDGE_ROOT_DIR = "沉淀笔记"; // 竞品「学习沉淀」等量自定（§3.5）
export const KNOWLEDGE_DEFAULT_DIR = "沉淀笔记/资料摘要";

// ── 数据模型（§3.1）──
export type LearningRunStatus =
  | "disabled" | "idle" | "waiting" | "running" | "completed" | "failed" | "rolled_back";

export type SourceKind =
  | "thread" | "memory" | "knowledge" | "skill" | "uploaded-file" | "generated-file" | "process";

export interface LearningSource {
  key: string;
  kind: SourceKind;
  title: string;
  fingerprint: string;
  content: string; // ≤SOURCE_SINGLE_CAP
  metadata: {
    baseKey: string;
    cursorKey: string;
    cursorFingerprint: string;
    cursorGroup?: string;
    chunkIndex?: number;
    chunkCount?: number;
  };
}

export interface LearningCounts {
  sources: number; threads: number; knowledgeFiles: number; uploadedFiles: number;
  generatedFiles: number; memoriesCreated: number; memoriesUpdated: number; memoriesDisabled: number;
  skillsCreated: number; skillsUpdated: number;
  knowledgeNotesCreated: number; knowledgeNotesUpdated: number; rejected: number;
}

export interface RecordSummary {
  id: string;                // YYYY-MM-DD-HHMM-uuid8
  title: string;             // ≤40
  displayName: string;       // 「本地日 · 标题」
  status: LearningRunStatus;
  startedAt: number;
  finishedAt: number;
  reportPath: string;
  canRollback: boolean;
  rolledBackAt?: number;
  error?: string;            // 旧档兼容可选
  counts: LearningCounts;
}

export interface LearningState {
  version: 1;
  sourceHashes: Record<string, string>; // key→sha256（meta 级+分块级共用一账）
  lastSuccessfulAt: number | null;
  lastCheckedAt: number | null;
  lastLocalDay: string | null;          // YYYY-MM-DD 本地日
  lastRetryAt: number | null;
  retryCount: number;                   // 0..2
  baselineComplete: boolean;
  baselineProcessed: number;
  baselineRemaining: number;
  pendingRunId: string | null;
}

export type RollbackOp =
  | { area: "memory"; op: "delete-created" | "restore"; id: string; before?: Record<string, unknown> | null; afterHash: string }
  | { area: "skill"; op: "delete-created" | "restore"; id: string; targetPath: string; backupPath?: string; afterHash: string }
  | { area: "knowledge"; op: "delete-created" | "restore"; path: string; beforeContent?: string; afterHash: string };

export interface LearningManifest {
  version: 1;
  summary: RecordSummary;
  sourceHashes: Record<string, string>;
  rollback: { memories: RollbackOp[]; skills: RollbackOp[]; knowledge: RollbackOp[] };
  modelResult?: {
    title: string; summary: string; reportMarkdown: string;
    memories: unknown[]; skills: unknown[]; knowledgeNotes: unknown[]; rejected: unknown[];
  };
}

// ── 提案形状（模型输出契约）──
export interface MemoryProposal {
  action: "create" | "update" | "disable";
  category: "profile" | "preference" | "workflow" | "project" | string;
  content: string;
  confidence: number;
  evidence: Array<{ sourceKey: string; sourceKind: string; excerpt?: string }>;
  explicitCorrection?: boolean;
  targetId?: string;
  origin?: string;
  confirmedSensitive?: boolean;
}
export interface SkillTestCase {
  category: "should-trigger" | "should-not-trigger" | "ambiguous" | "sibling-confusion" | string;
  input: string;
  passed: boolean;
}
export interface SkillProposal {
  id: string; name: string; description: string; skillMarkdown: string;
  evidence: Array<{ sourceKey: string; sourceKind: string }>;
  tests: SkillTestCase[];
}
export interface KnowledgeProposal {
  action: "create" | "update";
  path: string; title: string; summary: string; content: string;
  evidence: Array<{ sourceKey: string; sourceKind: string }>;
}
export interface RejectedItem { kind: "memory" | "skill" | "knowledgeNote"; reason: string; brief: string }
export interface ModelResult {
  title: string; summary: string; reportMarkdown: string;
  memories: MemoryProposal[]; skills: SkillProposal[]; knowledgeNotes: KnowledgeProposal[];
  rejected: RejectedItem[];
}

// ── 设置（§3.1/对拍 1/9/8；A1 仅显式 false 才关）──
export interface LearningSettings {
  enabled: boolean;
  idleMinutes: number;        // 默认 15，clamp 5..240，UI 四档 5/15/30/60
  keepRunningInTray: boolean; // 默认开（托盘挂接随打包步骤，桥侧只存行为开关）
}
export const IDLE_CHOICES = [5, 15, 30, 60];
export function normalizeLearningSettings(raw: unknown): LearningSettings {
  const r = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  return {
    enabled: r.enabled !== false, // 仅显式 false 关（A1）
    idleMinutes: clampIdleMinutes(r.idleMinutes),
    keepRunningInTray: r.keepRunningInTray !== false,
  };
}
export function clampIdleMinutes(v: unknown): number {
  const n = Number(v);
  if (!Number.isFinite(n)) return 15;
  return Math.min(240, Math.max(5, Math.round(n)));
}

// ── 阈值单源（§2 C/D 类钉死口径）──
export const SOURCE_SINGLE_CAP = 20000;      // 单源截断（C11）
export const TOTAL_BUDGET = 120000;          // 语料总预算（C11）
export const KIND_BUDGETS: Record<SourceKind, number> = {
  thread: 45000, memory: 8000, knowledge: 24000, skill: 8000,
  "uploaded-file": 16000, "generated-file": 16000, process: 8000,
};
export const CHUNK_CHARS = 20000;            // 内容分块（C9）
export const THREAD_TEXT_CAP = 6000;         // 单条线程正文（C1 掐头留尾）
export const THREAD_TAIL_KEEP = 1000;
export const PROCESS_TEXT_CAP = 4000;        // 过程记录（C2）
export const TOOL_CALL_SUMMARY_CAP = 500;
export const UPLOADS_PER_THREAD_CAP = 16;    // C3/C4
export const GENERATED_PER_THREAD_CAP = 16;
export const UPLOAD_SIZE_CAP = 25 * 1024 * 1024;
export const KNOWLEDGE_FILES_CAP = 12;       // C5
export const MEMORY_CHANGES_CAP = 60;        // C6
export const SKILL_CHANGES_CAP = 60;         // C7
export const POLL_INTERVAL_MS_DEFAULT = 5 * 60_000; // A2 五分钟轮询（间隔可配）
export const BACKOFF_FIRST_MS = 30 * 60_000;  // A7
export const BACKOFF_SECOND_MS = 2 * 3600_000;
export const MAX_RETRY_COUNT = 2;
export const TURN_POLL_MS = 1500;             // D3
export const TURN_TIMEOUT_MS = 4 * 3600_000;  // D3 4 小时
export const TURN_TRANSIENT_LIMIT = 5;        // D4 断连容错
export const DIAGNOSIS_CAP = 200;             // D6
export const PROPOSAL_CAPS = { memories: 20, skills: 5, knowledgeNotes: 8, rejected: 30 } as const; // D9
export const SUMMARY_CAP = 1000;
export const REPORT_MD_CAP = 8000;
export const MEMORY_CONTENT_CAP = 1500;       // F1
export const SKILL_MD_CAP = 30000;            // F2
export const KNOWLEDGE_CONTENT_MAX = 30000;   // F3
export const KNOWLEDGE_CONTENT_MIN = 80;
export const KNOWLEDGE_PATH_MAX = 500;
export const SKILL_ID_RE = /^[a-z0-9][a-z0-9-]{0,62}$/; // F2 小写连字符
export const RUN_ID_RE = /^[A-Za-z0-9._-]{1,128}$/;      // H10 防路径逃逸
export const COUNT_KEYS: Array<keyof LearningCounts> = [
  "sources", "threads", "knowledgeFiles", "uploadedFiles", "generatedFiles",
  "memoriesCreated", "memoriesUpdated", "memoriesDisabled", "skillsCreated", "skillsUpdated",
  "knowledgeNotesCreated", "knowledgeNotesUpdated", "rejected",
];

export function emptyCounts(): LearningCounts {
  return {
    sources: 0, threads: 0, knowledgeFiles: 0, uploadedFiles: 0, generatedFiles: 0,
    memoriesCreated: 0, memoriesUpdated: 0, memoriesDisabled: 0,
    skillsCreated: 0, skillsUpdated: 0, knowledgeNotesCreated: 0, knowledgeNotesUpdated: 0,
    rejected: 0,
  };
}
export function normalizeCounts(raw: unknown): LearningCounts {
  const base = emptyCounts();
  if (!raw || typeof raw !== "object") return base;
  for (const k of COUNT_KEYS) {
    const v = Number((raw as Record<string, unknown>)[k]);
    if (Number.isFinite(v) && v >= 0) base[k] = Math.floor(v);
  }
  return base;
}

// ── sha256（纯 TS 实现，浏览器/桥/自测同源；FIPS 180-4）──
const K64 = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];
export function sha256Hex(input: string): string {
  const msg = new TextEncoder().encode(input);
  const bitLen = msg.length * 8;
  const withPad = new Uint8Array((((msg.length + 8) >> 6) + 1) << 6);
  withPad.set(msg);
  withPad[msg.length] = 0x80;
  const dv = new DataView(withPad.buffer);
  dv.setUint32(withPad.length - 8, Math.floor(bitLen / 0x100000000));
  dv.setUint32(withPad.length - 4, bitLen >>> 0);
  let h0 = 0x6a09e667, h1 = 0xbb67ae85, h2 = 0x3c6ef372, h3 = 0xa54ff53a,
    h4 = 0x510e527f, h5 = 0x9b05688c, h6 = 0x1f83d9ab, h7 = 0x5be0cd19;
  const w = new Int32Array(64);
  const rr = (x: number, n: number) => (x >>> n) | (x << (32 - n));
  for (let off = 0; off < withPad.length; off += 64) {
    for (let i = 0; i < 16; i++) w[i] = dv.getInt32(off + i * 4);
    for (let i = 16; i < 64; i++) {
      const s0 = rr(w[i - 15]!, 7) ^ rr(w[i - 15]!, 18) ^ (w[i - 15]! >>> 3);
      const s1 = rr(w[i - 2]!, 17) ^ rr(w[i - 2]!, 19) ^ (w[i - 2]! >>> 10);
      w[i] = (w[i - 16]! + s0 + w[i - 7]! + s1) | 0;
    }
    let a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;
    for (let i = 0; i < 64; i++) {
      const S1 = rr(e!, 6) ^ rr(e!, 11) ^ rr(e!, 25);
      const ch = (e! & f!) ^ (~e! & g!);
      const t1 = (h! + S1 + ch + K64[i]! + w[i]!) | 0;
      const S0 = rr(a!, 2) ^ rr(a!, 13) ^ rr(a!, 22);
      const maj = (a! & b!) ^ (a! & c!) ^ (b! & c!);
      const t2 = (S0 + maj) | 0;
      h = g; g = f; f = e; e = (d! + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    h0 = (h0 + a) | 0; h1 = (h1 + b) | 0; h2 = (h2 + c) | 0; h3 = (h3 + d) | 0;
    h4 = (h4 + e) | 0; h5 = (h5 + f) | 0; h6 = (h6 + g) | 0; h7 = (h7 + h) | 0;
  }
  return [h0, h1, h2, h3, h4, h5, h6, h7].map((x) => (x >>> 0).toString(16).padStart(8, "0")).join("");
}
export const contentHash = (s: string): string => sha256Hex(String(s ?? ""));
// 记忆可比 JSON（G1/H7：键序稳定 → 哈希可比）
export function comparableJson(v: unknown): string {
  if (v === null || typeof v !== "object") return JSON.stringify(v ?? null);
  if (Array.isArray(v)) return "[" + v.map(comparableJson).join(",") + "]";
  const o = v as Record<string, unknown>;
  return "{" + Object.keys(o).sort().map((k) => JSON.stringify(k) + ":" + comparableJson(o[k])).join(",") + "}";
}
export const memoryComparableHash = (m: unknown): string => contentHash(comparableJson(m));
// 技能目录递归 hash：文件相对路径+内容逐一并入（H7）
export function directoryHash(files: Array<{ rel: string; content: string }>): string {
  const sorted = [...files].sort((a, b) => (a.rel < b.rel ? -1 : 1));
  return contentHash(sorted.map((f) => f.rel + "\u0000" + f.content).join("\u0001"));
}

// ── 本地日（确定性纪律：本地时区 YYYY-MM-DD）──
export function localDayOf(now = Date.now()): string {
  const n = new Date(now);
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}
function pad2(n: number): string { return String(n).padStart(2, "0"); }

// ── runId（H1）：YYYY-MM-DD-HHMM-uuid8 ──
export function newRunId(now: number, uuid8: string): string {
  const n = new Date(now);
  return `${n.getFullYear()}-${pad2(n.getMonth() + 1)}-${pad2(n.getDate())}-${pad2(n.getHours())}${pad2(n.getMinutes())}-${String(uuid8 ?? "").replace(/[^a-zA-Z0-9]/g, "").slice(0, 8) || "run"}`;
}

// ── 七状态派生（B1 优先级 disabled>running>waiting>latest.failed>latest.completed>idle）──
export interface DeriveInput {
  enabled: boolean;
  running: boolean;
  queued: boolean;
  latest: { status: LearningRunStatus } | null;
}
export function deriveRunStatus(inp: DeriveInput): LearningRunStatus {
  if (!inp.enabled) return "disabled";
  if (inp.running) return "running";
  if (inp.queued) return "waiting";
  const s = inp.latest?.status;
  if (s === "failed" || s === "rolled_back") return s; // 失败与已回滚保留至下一轮
  if (s === "completed") return "completed";
  return "idle";
}
// 状态徽章五色（J2；色板自绘）：failed 红/running 蓝/waiting 琥珀/disabled 灰/其余绿
export function statusToneOf(status: LearningRunStatus): "red" | "blue" | "amber" | "gray" | "green" {
  switch (status) {
    case "failed": return "red";
    case "running": return "blue";
    case "waiting": return "amber";
    case "disabled": return "gray";
    default: return "green";
  }
}

// ── nextEligibleAt 三态（B3）──
export function nextEligibleAtOf(state: Pick<LearningState, "lastSuccessfulAt" | "lastLocalDay">, now: number): number | null {
  if (!state.lastSuccessfulAt) return null;               // 从未成功→空
  if (state.lastLocalDay === localDayOf(now)) {           // 今日已成功→次日零点
    const t = new Date(now);
    return new Date(t.getFullYear(), t.getMonth(), t.getDate() + 1).getTime();
  }
  return now;                                             // 今日可用→当前时间
}

// ── 退避（A7）：首败 30min，再败 2h，封顶 2 次 ──
export function backoffDelayMs(retryCount: number): number {
  return retryCount <= 0 ? BACKOFF_FIRST_MS : BACKOFF_SECOND_MS;
}
export function backoffDue(state: Pick<LearningState, "lastRetryAt" | "retryCount">, now: number): boolean {
  if (state.lastRetryAt === null) return true;
  return now - state.lastRetryAt >= backoffDelayMs(state.retryCount);
}

// ── 忙门四连（A5/A6/K4；force 绕闲/外忙/合规忙，不绕日额度与总开关）──
export interface BusyGateInput {
  idleSeconds: number | null;        // 系统空闲秒；桥面无 OS 空闲源时传 null（视为空闲，记差异）
  idleMinutes: number;
  externalBusy: boolean;             // 桥内运行任务+定时任务（对拍 5 等量口径）
  complianceBusy: boolean;           // 数据合规 pending/running（面未建恒 false，记差异）
  runningThreads: Array<{ id: string; isLearningThread: boolean }>;
  threadsUnavailable?: boolean;      // 线程列表请求失败→按忙（保守）
}
export interface BusyGateResult { busy: boolean; reasons: string[] }
export function evaluateBusyGate(inp: BusyGateInput, forceRun: boolean): BusyGateResult {
  const reasons: string[] = [];
  const needIdle = !forceRun;
  // idleSeconds=null=桥面无 OS 空闲源（§3.5 桥能力差异记档）：视为空闲，不阻塞自动轮
  if (needIdle && inp.idleSeconds !== null && inp.idleSeconds < inp.idleMinutes * 60) reasons.push("idle");
  if (!forceRun && inp.externalBusy) reasons.push("external");
  if (!forceRun && inp.complianceBusy) reasons.push("compliance");
  if (inp.threadsUnavailable) { reasons.push("threads"); return { busy: true, reasons }; }
  if (inp.runningThreads.some((t) => !t.isLearningThread)) reasons.push("threads"); // K4：学习线程自身与陈旧学习线程不阻塞
  return { busy: reasons.length > 0, reasons };
}

// ── 今日资格四态（J3）──
export type TodayEligibility = "can-check" | "done-today" | "queued" | "disabled";
export function todayEligibilityOf(inp: { enabled: boolean; queued: boolean; doneToday: boolean }): TodayEligibility {
  if (!inp.enabled) return "disabled";
  if (inp.queued) return "queued";
  if (inp.doneToday) return "done-today";
  return "can-check";
}

// ═══ 语料采集（C1-C12）═══
// C1 RAG 上下文剥离：竞品三标记等量自写（桥内 kb 提示词的同形节名族）
const RAG_MARKERS = ["## 所内资料", "## 检索到的资料", "【知识库检索结果】"];
export function stripRagContext(text: string): string {
  const s = String(text ?? "");
  let cut = s.length;
  for (const mk of RAG_MARKERS) {
    const i = s.indexOf(mk);
    if (i >= 0 && i < cut) cut = i;
  }
  let head = s.slice(0, cut);
  const qm = head.match(/^查询[：:]\s*(.+)$/m); // 无标记回退取查询行
  if (qm && cut === s.length) head = qm[1]!;
  return head.trim();
}
// C1 无实义消息过滤（打招呼/寒暄/占位）
const GREETING_RE = /^(在吗|在么|在？|你好|您好|hello|hi|hey|你是谁|新会话|新建会话|测试|test|ok|嗯|好的)[！!。．\s.]*$/i;
export function isTrivialMessage(text: string): boolean {
  const s = String(text ?? "").trim();
  if (!s) return true;
  return GREETING_RE.test(s);
}
// C1 单条 6000 掐头留尾（尾 1000，中段标注省略）
export function truncateHeadTail(text: string, cap = THREAD_TEXT_CAP, tailKeep = THREAD_TAIL_KEEP): string {
  const s = String(text ?? "");
  if ([...s].length <= cap) return s;
  const arr = [...s];
  const headLen = cap - tailKeep;
  return arr.slice(0, headLen).join("") + "\n…（中段内容因篇幅省略）…\n" + arr.slice(arr.length - tailKeep).join("");
}

// C4 产物路径提取：单值键 7+列表键 5，嵌套深度 3
const PATH_SINGLE_KEYS = ["path", "filePath", "file_path", "outputPath", "output_path", "targetPath", "target_path"];
const PATH_LIST_KEYS = ["artifacts", "files", "paths", "outputFiles", "output_files"];
export function extractFilePathsFromPayload(payload: unknown, depth = 0): string[] {
  if (depth > 3 || payload === null || typeof payload !== "object") return [];
  const out: string[] = [];
  if (Array.isArray(payload)) {
    for (const item of payload) out.push(...extractFilePathsFromPayload(item, depth + 1));
    return out;
  }
  const obj = payload as Record<string, unknown>;
  for (const k of PATH_SINGLE_KEYS) {
    const v = obj[k];
    if (typeof v === "string" && v.trim()) out.push(v.trim());
  }
  for (const k of PATH_LIST_KEYS) {
    const v = obj[k];
    if (Array.isArray(v)) for (const item of v) if (typeof item === "string" && item.trim()) out.push(item.trim());
  }
  for (const v of Object.values(obj)) {
    if (v && typeof v === "object") out.push(...extractFilePathsFromPayload(v, depth + 1));
  }
  return out;
}
// C4/K5 内部目录与越界排除
const INTERNAL_DIR_RE = /(^|[\\/])(\.git|node_modules|dist|build)([\\/]|$)|(^|[\\/])\.tmp/;
export function isInternalOutputPath(p: string): boolean {
  return INTERNAL_DIR_RE.test(String(p ?? ""));
}
export function pathInsideWorkspace(p: string, workspace: string): boolean {
  const a = String(p ?? "").replace(/\\/g, "/").toLowerCase();
  const b = String(workspace ?? "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  if (!b) return false;
  return a !== b && a.startsWith(b + "/");
}

// C9 分块：20000 字符/块，key=base#chunk:N，指纹=hash(基础指纹+内容 hash)
export function chunkSource(base: {
  kind: SourceKind;
  title: string;
  content: string;
  seedFingerprint: string; // 基础指纹（base 级身份种子）
  metadata: Omit<LearningSource["metadata"], "chunkIndex" | "chunkCount">;
}): LearningSource[] {
  const arr = [...base.content];
  const count = Math.max(1, Math.ceil(arr.length / CHUNK_CHARS));
  const out: LearningSource[] = [];
  for (let i = 0; i < count; i++) {
    const part = arr.slice(i * CHUNK_CHARS, (i + 1) * CHUNK_CHARS).join("");
    const fp = contentHash(base.seedFingerprint + contentHash(part));
    out.push({
      key: `${base.metadata.baseKey}#chunk:${i}`,
      kind: base.kind,
      title: base.title,
      fingerprint: fp,
      content: part,
      metadata: { ...base.metadata, chunkIndex: i, chunkCount: count },
    });
  }
  return out;
}

// C10/C11 预算选择：先按类目配额、再按剩余总量贪心；仅当某 base 的候选块全部入选才推进游标
export interface BudgetSelection {
  selected: LearningSource[];
  advancedCursorKeys: string[]; // 可安全推进的 base（全块入选）
  droppedBases: string[];       // 有块落选的 base（游标不动，下轮重来）
}
export function selectWithinBudget(sources: LearningSource[], opts?: { total?: number }): BudgetSelection {
  const total = opts?.total ?? TOTAL_BUDGET;
  const usedByKind = new Map<SourceKind, number>();
  const selected: LearningSource[] = [];
  let usedTotal = 0;
  // 稳定序：key 排序（确定性）；同 base 块序自然连号
  const ordered = [...sources].sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0));
  for (const s of ordered) {
    const cap = KIND_BUDGETS[s.kind] ?? 0;
    const used = usedByKind.get(s.kind) ?? 0;
    const len = [...s.content].length;
    if (used + len > cap) continue;
    if (usedTotal + len > total) continue;
    usedByKind.set(s.kind, used + len);
    usedTotal += len;
    selected.push(s);
  }
  const byBase = new Map<string, LearningSource[]>();
  for (const s of ordered) {
    const base = s.metadata.baseKey;
    if (!byBase.has(base)) byBase.set(base, []);
    byBase.get(base)!.push(s);
  }
  const selectedKeys = new Set(selected.map((s) => s.key));
  const advancedCursorKeys: string[] = [];
  const droppedBases: string[] = [];
  for (const [base, list] of byBase) {
    if (list.every((s) => selectedKeys.has(s.key))) advancedCursorKeys.push(base);
    else droppedBases.push(base);
  }
  return { selected, advancedCursorKeys, droppedBases };
}

// C12 统一脱敏 5 类：私钥块/token（sk-/pk-/api- 前缀）/Bearer/AWS AKIA/凭据键值对（含中文键）
const SECRET_PATTERNS: Array<[RegExp, string]> = [
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g, "【已脱敏：私钥块】"],
  [/\b(?:sk|pk|api)-[A-Za-z0-9_-]{8,}/g, "【已脱敏：访问令牌】"],
  [/Bearer\s+[A-Za-z0-9._-]{8,}/g, "【已脱敏：凭据头】"],
  [/AKIA[0-9A-Z]{16}/g, "【已脱敏：云访问密钥】"],
  [/^\s*.{0,24}(密码|口令|密钥|验证码|password|passwd|secret|token|api[_-]?key)\s*[:：=]\s*\S{1,120}\s*$/gim, "【已脱敏：凭据键值对】"],
];
export function redactText(text: string): string {
  let t = String(text ?? "");
  for (const [re, placeholder] of SECRET_PATTERNS) t = t.replace(re, placeholder);
  return t;
}
// F1/F2/F3 密钥命中判定（门上复用同族模式，命中即拒）
const SECRET_PRESENT_RE = [
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  /\b(?:sk|pk|api)-[A-Za-z0-9_-]{8,}/,
  /Bearer\s+[A-Za-z0-9._-]{8,}/,
  /AKIA[0-9A-Z]{16}/,
  /(?:密码|口令|密钥|验证码|password|passwd|secret|api[_-]?key)\s*[:：=]\s*\S{1,120}/i,
];
export function containsSecret(text: string): boolean {
  return SECRET_PRESENT_RE.some((re) => re.test(String(text ?? "")));
}
// F1 敏感标识（未经确认→拒）
const SENSITIVE_ID_RE = /1[3-9]\d{9}|身份证|身份证号|\d{17}[\dXx]|[\w.+-]+@[\w-]+\.[\w.]+|当事人|案号|（\d{4}）.{0,12}号|客户|委托人|账号/;
export function hasSensitiveIdentifier(text: string): boolean {
  return SENSITIVE_ID_RE.test(String(text ?? ""));
}

// ═══ 学习提示词（E1-E9；全文自写）═══
export function buildLearningPrompt(sources: LearningSource[], opts?: { repairError?: string; previousOutput?: string }): string {
  if (opts?.repairError !== undefined) {
    return [
      "上一轮输出无法按约定解析，解析器报告如下：",
      opts.repairError,
      "",
      "上一轮原始输出附在本指令末尾。请只修正 JSON 语法（引号闭合、换行转义、多余尾逗号等），",
      "一字不改内容本身，重新按原输出契约给出完整的 JSON 对象。",
      opts.previousOutput ? `\n<上一轮输出>\n${opts.previousOutput.slice(0, 8000)}\n</上一轮输出>` : "",
    ].join("\n");
  }
  const corpusBlocks = (sources ?? []).map((s) => {
    const tag = s.metadata.chunkIndex !== undefined ? `（第 ${s.metadata.chunkIndex! + 1}/${s.metadata.chunkCount ?? 1} 段）` : "";
    return `### [${s.kind}] ${s.title}${tag}\n${s.content}`;
  });
  return [
    // 首段声明（E1 prompt 侧：客户事实=机密源材料、最小化身份标识、绝不复制凭据密钥）
    "你是一次本地知识整理任务的阅读与分析员。下面交给你的材料属于机密源材料：只在本轮内部使用，不得在输出中复述客户的具体身份信息，尽量淡化可识别个人的细节，绝不复制任何密钥、令牌或凭据原文。",
    "本轮是纯文本分析：不要调用任何工具，不要发起检索或写入，只依据下方语料作答。",
    "",
    "## 你的任务",
    "通读全部语料，提取其中稳定、可复用、可核对的三类沉淀：长期记忆（用户的稳定工作方式与偏好）、技能（可重复执行的作业方法）、知识笔记（可检索的结构化知识）。只提取有把握的内容，宁缺毋滥。",
    "",
    "## 记忆红线（逐条硬约束）",
    "- 记忆只允许四类：profile（用户的角色与长期背景）、preference（使用偏好）、workflow（工作流程习惯）、project（当前项目的稳定事实）。",
    "- 禁止把兴趣爱好、具体案件事实、客户身份、账号、密钥、验证码写成记忆。",
    "- 禁止从助手的回答、任务主题、检索到的文档、文件名或产物去推断用户的职业、身份、偏好或工作流；记忆只能来自用户自己明确表达过的内容。",
    "- 显式纠正（用户明确否定过某个旧做法）可以单独成条，且只要求一条证据。",
    "",
    "## 证据纪律",
    "- 记忆候选只能引用 thread 类来源作证据；知识或技能来源可以支持技能与知识笔记，但不能支持用户记忆。",
    "- profile 与 project 类记忆至少需要 3 个不同线程的独立证据；其余类别至少 2 个；显式纠正放宽为 1 个。",
    "- 知识笔记与技能的证据至少 1 条即可，但必须真的来自语料，不得虚构来源键。",
    "",
    "## 知识笔记命名纪律",
    `- 路径必须落在 ${KNOWLEDGE_ROOT_DIR}/ 之下，用具体主题命名（例：${KNOWLEDGE_ROOT_DIR}/劳动合同解除审查要点.md 这类具体题目）。`,
    "- 禁止「记录1」「笔记2」「未命名」「纯日期」这类没有主题的通用名。新建的笔记必须对已有资料有增量价值（综合、结构化或交叉引用），禁止整段照抄源文件。",
    "",
    "## 技能纪律",
    "- 技能名称与描述用中文写，id 用小写英文与连字符。",
    "",
    "## 报告纪律",
    "- 报告面向使用者本人，用平实的白话中文写，分固定三节：这次学到了什么／会带来哪些提升／以后会怎样帮你。",
    "- 报告里不要出现来源键、内部会话标识、框架名或实现细节；不要宣称最终采纳或拒收了多少条——以系统核对后的统计为准。",
    "",
    "## 输出契约（严格遵守）",
    "在下面两行标记之间，输出恰好一个 JSON 对象；不要使用 Markdown 代码围栏；不要输出多余文字。",
    "字段：title（本轮简短标题）、summary（≤1000 字白话摘要）、reportMarkdown（≤8000 字报告，换行写成 \\n 字面量）、memories（数组，元素含 action/category/content/confidence/evidence/explicitCorrection）、skills（数组，元素含 id/name/description/skillMarkdown/evidence/tests，tests 为 6 到 10 条且 passed 全为 true、四类场景各至少一条）、knowledgeNotes（数组，元素含 action/path/title/summary/content/evidence）、rejected（数组，元素含 kind/reason/brief，说明哪些想法因证据不足而放弃）。",
    "",
    "<<<JUSCITE_LEARNING_OUTPUT",
    JSON.stringify({
      title: "示例标题",
      summary: "示例摘要",
      reportMarkdown: "## 这次学到了什么\\n- 示例",
      memories: [{ action: "create", category: "preference", content: "示例", confidence: 0.9,
        evidence: [{ sourceKey: "示例来源键", sourceKind: "thread" }], explicitCorrection: false }],
      skills: [],
      knowledgeNotes: [],
      rejected: [],
    }),
    "JUSCITE_LEARNING_OUTPUT>>>",
    "",
    "## 语料声明",
    "以下语料仅用于提取稳定、可复用、可审计的记忆／方法／知识笔记。",
    "",
    ...corpusBlocks,
  ].join("\n");
}

// 输出标记行（E9）
export const OUTPUT_MARK_BEGIN = "<<<JUSCITE_LEARNING_OUTPUT";
export const OUTPUT_MARK_END = "JUSCITE_LEARNING_OUTPUT>>>";

// ═══ 解析三级容错（D7）+ 重复输出取首对象 ═══
export class LearningParseError extends Error {}

export function parseModelOutput(raw: string): ModelResult {
  const text = String(raw ?? "");
  // ① 标记对间取 JSON
  let candidate: string | null = null;
  const b = text.indexOf(OUTPUT_MARK_BEGIN);
  const e = text.indexOf(OUTPUT_MARK_END);
  if (b >= 0 && e > b) candidate = text.slice(b + OUTPUT_MARK_BEGIN.length, e).trim();
  // ② 无标记取最外层大括号
  if (candidate === null) {
    const first = text.indexOf("{");
    const last = text.lastIndexOf("}");
    if (first >= 0 && last > first) candidate = text.slice(first, last + 1);
  }
  if (candidate === null || !candidate.trim()) throw new LearningParseError("输出中未找到 JSON 对象");
  // ③ 模型输出尾部重复 JSON：取首个完整对象
  let jsonText = firstCompleteObject(candidate);
  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonText);
  } catch (err1) {
    const repaired = repairJson(candidate); // 修复器作用于整段候选（含重复段修复后仍取首对象）
    try {
      jsonText = firstCompleteObject(repaired);
      parsed = JSON.parse(jsonText);
    } catch (err2) {
      throw new LearningParseError("JSON 解析失败：" + String((err2 as Error).message ?? err2).slice(0, 160));
    }
    void err1;
  }
  return shapeResult(parsed);
}

// 取首个完整 JSON 对象（大括号配平，字符串字面量感知）
export function firstCompleteObject(text: string): string {
  const start = text.indexOf("{");
  if (start < 0) return text;
  let depth = 0, inStr = false, esc = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i]!;
    if (inStr) {
      if (esc) esc = false;
      else if (ch === "\\") esc = true;
      else if (ch === '"') inStr = false;
      continue;
    }
    if (ch === '"') inStr = true;
    else if (ch === "{") depth++;
    else if (ch === "}") {
      depth--;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  return text.slice(start); // 不配平则整段交给 JSON.parse 报错
}

// 修复器（D7）：字符串内未转义引号/裸换行/控制字符/非法反斜杠；结构错误不猜（直接抛）
export function repairJson(text: string): string {
  let out = "";
  let inStr = false, esc = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]!;
    if (!inStr) {
      if (ch === '"') { inStr = true; out += ch; }
      else out += ch;
      continue;
    }
    if (esc) { esc = false; out += ch; continue; }
    if (ch === "\\") {
      const next = text[i + 1];
      if (next === undefined) throw new LearningParseError("字符串以孤立反斜杠结尾");
      if ('"\\/bfnrtu'.includes(next)) { esc = true; out += ch; }
      else if (next === "\n") { out += "\\n"; i++; } // 裸反斜杠+换行
      else { out += "\\\\"; } // 非法转义序列→反斜杠字面量化，next 照常处理
      continue;
    }
    if (ch === '"') {
      // 判定是否真正收尾：向后看第一个非空白字符，若是 , } ] : 视为收尾；否则视为字符串内未转义引号
      let j = i + 1;
      while (j < text.length && /\s/.test(text[j]!)) j++;
      const nxt = text[j];
      if (nxt === undefined || [, ",", "}", "]", ":"].includes(nxt)) { inStr = false; out += ch; }
      else out += '\\"';
      continue;
    }
    if (ch === "\n") { out += "\\n"; continue; }
    if (ch === "\r") { continue; }
    const code = ch.codePointAt(0)!;
    if (code < 0x20) { out += "\\u" + code.toString(16).padStart(4, "0"); continue; }
    out += ch;
  }
  if (inStr) throw new LearningParseError("字符串未闭合");
  return out;
}

function asArray(v: unknown): unknown[] { return Array.isArray(v) ? v : []; }
function strOf(v: unknown, fallback = ""): string { return typeof v === "string" ? v : fallback; }
function numOf(v: unknown, fallback = 0): number { const n = Number(v); return Number.isFinite(n) ? n : fallback; }

function shapeResult(parsed: unknown): ModelResult {
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new LearningParseError("顶层不是 JSON 对象");
  const o = parsed as Record<string, unknown>;
  const memories = asArray(o.memories).filter((m): m is MemoryProposal => Boolean(m && typeof m === "object")).map((m) => m as MemoryProposal);
  const skills = asArray(o.skills).filter((s): s is SkillProposal => Boolean(s && typeof s === "object")).map((s) => s as SkillProposal);
  const knowledgeNotes = asArray(o.knowledgeNotes).filter((k): k is KnowledgeProposal => Boolean(k && typeof k === "object")).map((k) => k as KnowledgeProposal);
  const rejected = asArray(o.rejected).filter((r): r is RejectedItem => Boolean(r && typeof r === "object")).map((r) => r as RejectedItem);
  return {
    title: strOf(o.title, "本轮学习"),
    summary: strOf(o.summary),
    reportMarkdown: strOf(o.reportMarkdown).replace(/\\n/g, "\n"),
    memories, skills, knowledgeNotes, rejected,
  };
}

// D9 提案硬截断（summary/reportMarkdown 长度帽 + \n 字面还原已在 shapeResult）
export function clampProposal(r: ModelResult): ModelResult {
  return {
    ...r,
    summary: [...r.summary].slice(0, SUMMARY_CAP).join(""),
    reportMarkdown: [...r.reportMarkdown].slice(0, REPORT_MD_CAP).join(""),
    memories: r.memories.slice(0, PROPOSAL_CAPS.memories),
    skills: r.skills.slice(0, PROPOSAL_CAPS.skills),
    knowledgeNotes: r.knowledgeNotes.slice(0, PROPOSAL_CAPS.knowledgeNotes),
    rejected: r.rejected.slice(0, PROPOSAL_CAPS.rejected),
  };
}

// D6 失败诊断四级回退：最后 error 项→失败 tool_result→最后 assistant 文本→裸状态；截断 200
export function diagnoseFailure(inp: {
  lastErrorItem?: string | null;
  failedToolResults?: string[];
  lastAssistantText?: string | null;
  bareStatus?: string;
}): string {
  const raw = inp.lastErrorItem?.trim()
    || inp.failedToolResults?.find((t) => t.trim())
    || inp.lastAssistantText?.trim()
    || inp.bareStatus?.trim()
    || "原因未知";
  return [...raw].slice(0, DIAGNOSIS_CAP).join("");
}

// ═══ H4 技术字样过滤 ═══
const TECHNICAL_RE = /thread:|RIA|TV\+\+|JSON|Markdown|候选|压力测试|schema|payload|token|解析器/i;
export function looksTechnical(summary: string): boolean {
  return TECHNICAL_RE.test(String(summary ?? ""));
}
export function plainOverviewOf(modelResult: ModelResult, counts: LearningCounts): string {
  const learned = counts.memoriesCreated + counts.memoriesUpdated + counts.memoriesDisabled
    + counts.skillsCreated + counts.skillsUpdated + counts.knowledgeNotesCreated + counts.knowledgeNotesUpdated;
  if (learned <= 0) return "这一轮没有改动任何沉淀内容，可以当作一次例行检查。";
  return "这一轮系统通读了最近的工作记录，并把其中有把握的内容整理进了记忆、方法与知识库，具体见下方清单。";
}
const SKILL_WORD_RE = /\b(skill|trigger)\b|技能触发器|技能词/g;
export function plainSkillDescription(description: string): string {
  const cjk = (String(description ?? "").match(/[\u4e00-\u9fff]/g) ?? []).length;
  if (cjk < 4) return "按你常用的处理方式自动整理的作业方法。";
  return String(description).replace(SKILL_WORD_RE, "这套做法");
}

// ═══ F1 记忆验证门 ═══
const MEMORY_CATEGORIES = new Set(["profile", "preference", "workflow", "project"]);
export interface MemoryGateContext {
  existingMemories: Array<Record<string, unknown>>; // store 现量（查 origin/disable 权限）
  knownSources: Map<string, { kind: SourceKind }>;  // sourceKey→kind（证据合法性）
}
export interface GateVerdict { ok: boolean; reason?: string }
export function validateMemoryCandidate(c: MemoryProposal, ctx: MemoryGateContext): GateVerdict {
  if (!["create", "update", "disable"].includes(c.action)) return { ok: false, reason: "动作只能是新建、更新或停用" };
  if (c.action === "disable") {
    // disable 仅限自动学习产物（origin=learning）；按 targetId 查现量
    const target = ctx.existingMemories.find((m) => String(m.id ?? "") === String(c.targetId ?? ""));
    if (!target) return { ok: false, reason: "要停用的记忆不存在" };
    if (String(target.origin ?? "") !== "learning-iteration") return { ok: false, reason: "只能停用学习迭代自己写入的记忆" };
    return { ok: true };
  }
  const corrected = c.explicitCorrection === true;
  if (!corrected && !MEMORY_CATEGORIES.has(c.category)) return { ok: false, reason: `记忆类别不在允许范围（${c.category}）` };
  if (!String(c.content ?? "").trim()) return { ok: false, reason: "内容为空" };
  if ([...String(c.content)].length > MEMORY_CONTENT_CAP) return { ok: false, reason: "内容超过长度上限" };
  if (containsSecret(c.content)) return { ok: false, reason: "内容含密钥或凭据" };
  if (c.confirmedSensitive !== true && hasSensitiveIdentifier(c.content)) return { ok: false, reason: "内容含身份标识且未经确认" };
  // 证据：仅 thread 源计数、按 base 源去重
  const bases = new Set<string>();
  for (const ev of c.evidence ?? []) {
    if (!ev || typeof ev !== "object") continue;
    const kind = ctx.knownSources.get(String(ev.sourceKey ?? ""))?.kind ?? (ev.sourceKind === "thread" ? "thread" : null);
    if (kind !== "thread") continue;
    bases.add(String(ev.sourceKey ?? "").split("#")[0]!);
  }
  const need = corrected ? 1 : c.category === "profile" || c.category === "project" ? 3 : 2;
  if (bases.size < need) return { ok: false, reason: `证据线程不足（需要 ${need} 个不同线程，实得 ${bases.size}）` };
  const floor = corrected ? 0 : c.category === "profile" || c.category === "project" ? 0.9 : 0.85;
  if (Number(c.confidence) < floor) return { ok: false, reason: `置信度不足（下限 ${floor}）` };
  return { ok: true };
}

// ═══ F2 技能验证门 ═══
const TEST_CATEGORIES = ["should-trigger", "should-not-trigger", "ambiguous", "sibling-confusion"];
export interface SkillGateContext {
  knownSources: Map<string, { kind: SourceKind }>;
}
export function validateSkillCandidate(c: SkillProposal, ctx: SkillGateContext): GateVerdict {
  if (!SKILL_ID_RE.test(String(c.id ?? ""))) return { ok: false, reason: "id 必须是小写英文与连字符" };
  const evidenceKinds = new Set<string>();
  for (const ev of c.evidence ?? []) {
    const kind = ctx.knownSources.get(String(ev?.sourceKey ?? ""))?.kind;
    if (kind === "thread" || kind === "knowledge") evidenceKinds.add(kind);
  }
  if (evidenceKinds.size < 2 && (c.evidence ?? []).length < 2) return { ok: false, reason: "证据不足（至少 2 条 thread 或知识来源）" };
  if ([...String(c.description ?? "")].length < 12) return { ok: false, reason: "描述太短（至少 12 字）" };
  const md = String(c.skillMarkdown ?? "");
  if ([...md].length > SKILL_MD_CAP) return { ok: false, reason: "正文超过长度上限" };
  if (!md.includes("---")) return { ok: false, reason: "正文缺少 frontmatter 结构" };
  if (containsSecret(md)) return { ok: false, reason: "正文含密钥或凭据" };
  const tests = Array.isArray(c.tests) ? c.tests : [];
  if (tests.length < 6 || tests.length > 10) return { ok: false, reason: `测试条数须为 6 到 10 条（实得 ${tests.length}）` };
  if (!tests.every((t) => t?.passed === true)) return { ok: false, reason: "存在未通过的测试" };
  const cats = new Set(tests.map((t) => String(t?.category ?? "")));
  for (const cat of TEST_CATEGORIES) if (!cats.has(cat)) return { ok: false, reason: `测试缺少场景：${cat}` };
  return { ok: true };
}

// ═══ F3 知识验证门 ═══
const GENERIC_NAME_RE = /^(迭代记录|学习笔记|笔记|记录|总结|未命名|untitled|new[-_ ]?note|doc)\d*$/i;
const PURE_DATE_RE = /^\d{4}[-_/年]?\d{0,2}[-_/月]?\d{0,2}[日]?$/;
export type PathVerdict = { ok: true; relPath: string } | { ok: false; reason: string }
export function normalizeKnowledgePath(input: string): PathVerdict {
  const original = String(input ?? "").trim();
  let s = original.replace(/\\/g, "/");
  if (!s) return { ok: false, reason: "路径为空" };
  if (s.includes("\u0000")) return { ok: false, reason: "路径含非法字符" };
  if (/^[a-zA-Z]:/.test(s)) return { ok: false, reason: "不允许盘符绝对路径" };
  if (/^[\\/]/.test(original)) return { ok: false, reason: "不允许绝对路径" };
  s = s.replace(/^\/+/, "");
  const parts = s.split("/").filter((p) => p && p !== ".");
  if (parts.some((p) => p === "..")) return { ok: false, reason: "路径不得含 .." };
  const full = parts.join("/");
  if (full.length > KNOWLEDGE_PATH_MAX) return { ok: false, reason: "路径过长" };
  if (!/\.md$/i.test(full)) return { ok: false, reason: "必须是 .md 笔记" };
  // 无根路径默认落 资料摘要/
  const rel = full.startsWith(KNOWLEDGE_ROOT_DIR + "/") ? full : `${KNOWLEDGE_DEFAULT_DIR}/${full}`;
  const name = rel.split("/").pop()!.replace(/\.md$/i, "");
  const cjk = (name.match(/[\u4e00-\u9fff]/g) ?? []).length;
  const latin = (name.match(/[a-zA-Z]/g) ?? []).length;
  const topicOk = name.length >= 4 && (cjk >= 4 || latin >= 6);
  if (!topicOk) return { ok: false, reason: "文件名缺少主题语义（至少 4 个汉字或 6 个英文字母）" };
  if (GENERIC_NAME_RE.test(name) || PURE_DATE_RE.test(name)) return { ok: false, reason: "文件名是通用名或纯日期，请用具体主题命名" };
  return { ok: true, relPath: rel };
}
export function knowledgeTitleOk(title: string): boolean {
  const t = String(title ?? "").trim();
  if ([...t].length < 4) return false;
  const cjk = (t.match(/[\u4e00-\u9fff]/g) ?? []).length;
  const latin = (t.match(/[a-zA-Z]/g) ?? []).length;
  if (cjk < 4 && latin < 6) return false;
  return !GENERIC_NAME_RE.test(t) && !PURE_DATE_RE.test(t);
}
export interface KnowledgeGateContext {
  knownSources: Map<string, { kind: SourceKind }>;
  existingPaths: Set<string>;   // 知识库现有相对路径（F4 create 不覆盖）
  learnedPathsThisRun: Set<string>; // 学习产物路径（F5 update 白名单 + 同轮去重 + 防自我吞噬）
}
export function validateKnowledgeCandidate(c: KnowledgeProposal, ctx: KnowledgeGateContext): GateVerdict {
  const pv = normalizeKnowledgePath(String(c.path ?? ""));
  if (!pv.ok) return { ok: false, reason: pv.reason };
  if (ctx.learnedPathsThisRun.has(pv.relPath)) return { ok: false, reason: "同轮出现重复目标路径" };
  if (!knowledgeTitleOk(String(c.title ?? ""))) return { ok: false, reason: "标题缺少主题语义或是通用名" };
  if ([...String(c.summary ?? "").trim()].length < 8) return { ok: false, reason: "摘要太短（至少 8 字）" };
  const clen = [...String(c.content ?? "")].length;
  if (clen < KNOWLEDGE_CONTENT_MIN || clen > KNOWLEDGE_CONTENT_MAX) return { ok: false, reason: "正文长度不在允许范围" };
  if (containsSecret(String(c.content ?? ""))) return { ok: false, reason: "正文含密钥或凭据" };
  // 证据 ≥1（五类源），但排除来自学习产物目录内部的知识源（防自我吞噬）
  let count = 0;
  for (const ev of c.evidence ?? []) {
    const key = String(ev?.sourceKey ?? "");
    const kind = ctx.knownSources.get(key)?.kind;
    if (!kind) continue;
    if (kind === "knowledge" && key.startsWith("kb:" + KNOWLEDGE_ROOT_DIR)) continue;
    count++;
  }
  if (count < 1) return { ok: false, reason: "缺少有效证据来源" };
  const exists = [...ctx.existingPaths].some((p) => p.replace(/\\/g, "/") === pv.relPath);
  if (c.action === "update" && !exists) return { ok: false, reason: "要更新的笔记不存在" };
  if (c.action !== "update" && exists) return { ok: false, reason: "目标笔记已存在，不覆盖（可改为更新或换名新建）" }; // F4
  return { ok: true };
}
// F5 update 仅限学习产物（文件内容须含学习标记注释）
export function hasLearningMarker(fileContent: string): boolean {
  return String(fileContent ?? "").includes(LEARNING_ARTIFACT_MARKER);
}

// F6 内置/项目技能保护：整批剔除 + 拒收理由
export function partitionProtectedSkills(
  candidates: SkillProposal[],
  protectedIds: Iterable<string>,
): { allowed: SkillProposal[]; rejected: Array<{ candidate: SkillProposal; reason: string }> } {
  const prot = new Set([...protectedIds]);
  const allowed: SkillProposal[] = [];
  const rejected: Array<{ candidate: SkillProposal; reason: string }> = [];
  for (const c of candidates) {
    if (prot.has(String(c.id ?? ""))) rejected.push({ candidate: c, reason: "后台不会覆盖系统自带的同名技能" });
    else allowed.push(c);
  }
  return { allowed, rejected };
}

// ═══ G1 记忆发布账本 ═══
export const MEMORY_ORIGIN = "learning-iteration";
export function memoryWithProvenance(mem: Record<string, unknown>, runId: string): Record<string, unknown> {
  const tags = new Set((Array.isArray(mem.tags) ? mem.tags : []).map(String));
  tags.add("learning-iteration");
  const conf = Number(mem.confidence);
  return {
    ...mem,
    captureSource: "automatic",
    origin: MEMORY_ORIGIN,
    sourceIterationId: runId,
    scope: typeof mem.scope === "string" && mem.scope ? mem.scope : "user", // G1 scope 默认 user
    tags: [...tags],
    confidence: Number.isFinite(conf) ? Math.max(conf, 0.8) : 0.8, // 置信度下限抬 0.8
  };
}
// 重复记忆合并复活：evidence 并集/tags 并集/confidence 取大（caller 保证等价判定）
export function mergeDuplicateMemory(existing: Record<string, unknown>, incoming: Record<string, unknown>): Record<string, unknown> {
  const evA = Array.isArray(existing.evidence) ? existing.evidence : [];
  const evB = Array.isArray(incoming.evidence) ? incoming.evidence : [];
  const seen = new Set(evA.map((e) => JSON.stringify(e)));
  const evidence = [...evA, ...evB.filter((e) => !seen.has(JSON.stringify(e)))];
  const tagSet = new Set([...(Array.isArray(existing.tags) ? existing.tags : []).map(String),
    ...(Array.isArray(incoming.tags) ? incoming.tags : []).map(String)]);
  return {
    ...existing,
    ...incoming,
    id: existing.id,
    evidence,
    tags: [...tagSet],
    confidence: Math.max(Number(existing.confidence) || 0, Number(incoming.confidence) || 0),
    deleted: 0,
  };
}

// ═══ H2/H11 记录与 manifest ═══
export function titleOf40(modelTitle: string): string {
  const t = String(modelTitle ?? "").trim() || "学习迭代";
  return [...t].slice(0, 40).join("");
}
export function displayNameOf(id: string, title: string): string {
  const day = id.split("-").slice(0, 3).join("-"); // YYYY-MM-DD
  return `${day} · ${title}`;
}
export function newRecordSummary(id: string, title: string, now: number, reportPath: string): RecordSummary {
  return {
    id, title: titleOf40(title), displayName: displayNameOf(id, titleOf40(title)),
    status: "running", startedAt: now, finishedAt: now, reportPath, canRollback: false,
    counts: emptyCounts(),
  };
}
export function normalizeManifest(raw: unknown): LearningManifest | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, any>;
  if (!o.summary || typeof o.summary !== "object") return null;
  const s = o.summary as Record<string, any>;
  const summary: RecordSummary = {
    id: strOf(s.id), title: strOf(s.title, "学习迭代"), displayName: strOf(s.displayName, displayNameOf(strOf(s.id), strOf(s.title, "学习迭代"))),
    status: (["disabled", "idle", "waiting", "running", "completed", "failed", "rolled_back"].includes(s.status) ? s.status : "completed") as LearningRunStatus,
    startedAt: numOf(s.startedAt), finishedAt: numOf(s.finishedAt),
    reportPath: strOf(s.reportPath), canRollback: Boolean(s.canRollback),
    ...(s.rolledBackAt ? { rolledBackAt: numOf(s.rolledBackAt) } : {}),
    ...(s.error !== undefined ? { error: strOf(s.error) } : {}),
    counts: normalizeCounts(s.counts),
  };
  return {
    version: 1,
    summary,
    sourceHashes: (o.sourceHashes && typeof o.sourceHashes === "object" ? o.sourceHashes : {}) as Record<string, string>,
    rollback: {
      memories: Array.isArray(o.rollback?.memories) ? o.rollback.memories : [],
      skills: Array.isArray(o.rollback?.skills) ? o.rollback.skills : [],
      knowledge: Array.isArray(o.rollback?.knowledge) ? o.rollback.knowledge : [],
    },
    ...(o.modelResult && typeof o.modelResult === "object" ? { modelResult: o.modelResult } : {}),
  };
}

// H5 失败记录报告（自写话术）
export function buildFailureReport(diagnosis: string, backoffMinutes: number): string {
  return [
    "# 本轮学习未完成",
    "",
    "这次检查没有完成，但不会占用今天的成功额度；系统会按下面的节奏自动重试。",
    "",
    `## 原因`,
    diagnosis || "原因未知",
    "",
    `## 接下来`,
    `预计约 ${backoffMinutes} 分钟后会自动重试；你也可以随时在本页面手动发起一次检查。`,
  ].join("\n");
}

// ═══ H3 用户报告装配（全文自写）═══
export interface ReportInput {
  modelResult: ModelResult;
  counts: LearningCounts;
  canRollback: boolean;
  zeroChange: boolean; // 本轮全部被拒/无变更（G7 双态标题）
}
export function buildUserReport(inp: ReportInput): string {
  const { counts } = inp;
  const learnedItems: string[] = [];
  for (const m of inp.modelResult.memories) {
    const phrase = m.action === "disable" ? "不再沿用旧习惯"
      : m.action === "update" ? "更新了解"
      : m.category === "workflow" ? "记住了工作方式"
      : m.category === "preference" ? "使用偏好"
      : m.category === "profile" ? "长期重点"
      : "记住了项目情况";
    learnedItems.push(`${phrase}：${[...String(m.content ?? "")].slice(0, 60).join("")}`);
  }
  const improvements: string[] = [];
  for (const s of inp.modelResult.skills.slice(0, 5)) improvements.push(`学会了「${plainSkillDescription(s.description).slice(0, 24)}」`);
  for (const k of inp.modelResult.knowledgeNotes.slice(0, 5)) improvements.push(`沉淀了「${String(k.title ?? "").slice(0, 24)}」`);
  if (learnedItems.length > 0 && improvements.length === 0) improvements.push("这些了解会自然融入之后的对话，不需要你重复交代背景。");
  const rules: string[] = [];
  if (counts.memoriesCreated + counts.memoriesUpdated > 0) rules.push("对话时不再需要反复说明固定的偏好与习惯。");
  if (counts.skillsCreated + counts.skillsUpdated > 0) rules.push("遇到同类任务时会直接按整理好的方法执行。");
  if (counts.knowledgeNotesCreated + counts.knowledgeNotesUpdated > 0) rules.push("相关知识会进入知识库检索，回答时可直接引用。");
  if (!rules.length) rules.push("本轮没有新增内容，一切保持原样。");
  const accepted = counts.memoriesCreated + counts.memoriesUpdated + counts.memoriesDisabled
    + counts.skillsCreated + counts.skillsUpdated + counts.knowledgeNotesCreated + counts.knowledgeNotesUpdated;
  const lines: string[] = [];
  lines.push(inp.zeroChange ? "# 本轮学习检查已完成" : `# ${titleOf40(inp.modelResult.title)}`);
  lines.push("");
  lines.push(inp.zeroChange ? "这一轮没有发现足够稳定的新习惯，因此没有写入任何内容。" : plainOverviewOf(inp.modelResult, counts));
  lines.push("");
  lines.push("## 这次学到了什么");
  if (learnedItems.length === 0) lines.push("没有发现足够稳定的新习惯。");
  else for (const it of learnedItems.slice(0, 6)) lines.push(`- ${it}`);
  lines.push("");
  lines.push("## 会带来哪些提升");
  if (improvements.length === 0) lines.push("本轮没有新增方法或笔记。");
  else for (const it of improvements.slice(0, 10)) lines.push(`- ${it}`);
  lines.push("");
  lines.push("## 学习结果一览");
  lines.push("");
  lines.push("| 项目 | 数量 |");
  lines.push("|---|---|");
  lines.push(`| 记住的内容 | ${counts.memoriesCreated + counts.memoriesUpdated + counts.memoriesDisabled} |`);
  lines.push(`| 掌握的方法 | ${counts.skillsCreated + counts.skillsUpdated} |`);
  lines.push(`| 知识库沉淀 | ${counts.knowledgeNotesCreated + counts.knowledgeNotesUpdated} |`);
  lines.push(`| 因信息不够确定而未采纳 | ${counts.rejected} |`);
  lines.push(`| 浏览的变化来源 | ${counts.sources} |`);
  lines.push("");
  lines.push("## 以后会怎样帮你");
  for (const r of rules.slice(0, 4)) lines.push(`- ${r}`);
  lines.push("");
  lines.push("## 隐私与控制");
  lines.push("- 只学习有把握的稳定内容；拿不准的一律不采纳。");
  lines.push("- 新笔记只写入指定的沉淀目录，不会覆盖你的原始文件。");
  lines.push("- 每一轮都可以整轮撤销，随时可在记录页回滚。");
  if (inp.canRollback && accepted > 0) {
    lines.push("");
    lines.push(`如需撤销本轮，请在记录页使用回滚（共 ${accepted} 处变更可撤销）。`);
  }
  return lines.join("\n");
}

// H8 REPORT.md 追加回滚节
export function appendRollbackSection(report: string, when: number): string {
  return report.trimEnd() + `\n\n## 回滚\n\n本轮全部变更已于 ${new Date(when).toLocaleString("zh-CN")} 整体撤销，文件与记忆恢复到本轮之前的状态。\n`;
}

// H7 回滚 preflight：任一 afterHash 漂移→中止
export interface PreflightItem { area: RollbackOp["area"]; ref: string; expectHash: string; currentHash: string }
export function rollbackPreflight(items: PreflightItem[]): { ok: boolean; drifted: PreflightItem[] } {
  const drifted = items.filter((i) => i.expectHash !== i.currentHash);
  return { ok: drifted.length === 0, drifted };
}

// ═══ I1 记忆检索注入 ═══
export interface MemoryRecord {
  id: string;
  category: string;
  content: string;
  confidence: number;
  always?: boolean;
  deleted?: boolean;
  tags?: string[];
  origin?: string;
  [k: string]: unknown;
}
export interface InjectionPlan { block: string; injectedIds: string[] }
export function retrieveMemoriesForInjection(
  memories: MemoryRecord[],
  turnText: string,
  opts?: { budgetChars?: number; alwaysShare?: number },
): InjectionPlan {
  const budget = opts?.budgetChars ?? 2000;
  const alwaysShare = opts?.alwaysShare ?? 0.6;
  const live = memories.filter((m) => !m.deleted && String(m.content ?? "").trim());
  const q = String(turnText ?? "");
  const scoreOf = (m: MemoryRecord): number => {
    // 相关度=内容二元组命中轮次文本（正则滑窗，零模型）；再加置信度底分
    const chars = [...String(m.content ?? "")];
    let hits = 0;
    for (let i = 0; i + 2 <= chars.length; i++) {
      const gram = chars.slice(i, i + 2).join("");
      if (q.includes(gram)) hits++;
    }
    return hits * 2 + (Number(m.confidence) || 0);
  };
  const alwaysList = live.filter((m) => m.always === true)
    .sort((a, b) => b.confidence - a.confidence || (a.id < b.id ? -1 : 1));
  const relevantList = live.filter((m) => m.always !== true)
    .map((m) => ({ m, s: scoreOf(m) }))
    .filter((x) => x.s > 1)
    .sort((a, b) => b.s - a.s || (a.m.id < b.m.id ? -1 : 1)); // id 收尾保前缀缓存确定性
  const alwaysBudget = Math.floor(budget * alwaysShare);
  const lines: string[] = [];
  const ids: string[] = [];
  let used = 0;
  for (const m of alwaysList) {
    const line = `- ${m.content}`;
    if (used + line.length > alwaysBudget) break;
    used += line.length; lines.push(line); ids.push(m.id);
  }
  let relevantBudget = budget - used;
  for (const { m } of relevantList) {
    const line = `- ${m.content}`;
    if (relevantBudget <= 0 || used + line.length > budget) break;
    used += line.length; relevantBudget -= line.length; lines.push(line); ids.push(m.id);
  }
  if (!lines.length) return { block: "", injectedIds: [] };
  return { block: "【长期记忆参考】以下是你此前确认过的稳定偏好与习惯，回答时自然遵循即可，不要逐条复述：\n" + lines.join("\n"), injectedIds: ids };
}
// I2：知识问答线程不注入（kb 前缀同族）；学习线程自带指令也不注入
export function shouldInjectMemories(threadTitle: string): boolean {
  const t = String(threadTitle ?? "");
  if (t.startsWith("知识库")) return false;
  if (t.startsWith(LEARNING_THREAD_PREFIX)) return false;
  return true;
}

// ═══ K3 原子写（Windows 竞争容错；fs 由调用方注入）═══
export interface AtomicFs {
  writeFileDirect: (path: string, data: string) => void;           // 直写
  writeTmp: (path: string, data: string) => string;                // 写临时文件，返回 tmp 路径
  rename: (from: string, to: string) => void;
  unlink: (path: string) => void;
}
const ATOMIC_RETRY_TOTAL = 6;
const ATOMIC_BASE_DELAY_MS = 25;
const TRANSIENT_WRITE_RE = /EPERM|EACCES|EBUSY/i;
export function atomicWriteFileSync(fs: AtomicFs, target: string, data: string, opts?: { sleep?: (ms: number) => void; platform?: string }): void {
  const sleep = opts?.sleep ?? ((ms: number) => { /* 同步默认不等待（自测注入真实定时器） */ });
  const platform = opts?.platform ?? "win32";
  let lastErr: unknown = null;
  for (let attempt = 0; attempt < ATOMIC_RETRY_TOTAL; attempt++) {
    const tmp = fs.writeTmp(target, data);
    try {
      fs.rename(tmp, target);
      return;
    } catch (e) {
      lastErr = e;
      try { fs.unlink(tmp); } catch { /* tmp 已消失 */ }
      if (!TRANSIENT_WRITE_RE.test(String((e as Error)?.message ?? e))) break; // 非瞬态不重试
      sleep(ATOMIC_BASE_DELAY_MS * attempt); // 线性退避 25ms×attempt
    }
  }
  if (platform === "win32") {
    try { fs.writeFileDirect(target, data); return; } catch (e2) { lastErr = e2; } // 直写降级
  }
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr ?? "原子写失败"));
}

// K9/K10：state 默认空态（首次运行=全量基线回填）
export function defaultLearningState(): LearningState {
  return {
    version: 1, sourceHashes: {}, lastSuccessfulAt: null, lastCheckedAt: null, lastLocalDay: null,
    lastRetryAt: null, retryCount: 0, baselineComplete: false, baselineProcessed: 0, baselineRemaining: 0,
    pendingRunId: null,
  };
}
export function normalizeLearningState(raw: unknown): LearningState {
  const d = defaultLearningState();
  if (!raw || typeof raw !== "object") return d;
  const o = raw as Record<string, any>;
  return {
    version: 1,
    sourceHashes: (o.sourceHashes && typeof o.sourceHashes === "object" ? o.sourceHashes : {}) as Record<string, string>,
    lastSuccessfulAt: o.lastSuccessfulAt == null ? null : numOf(o.lastSuccessfulAt),
    lastCheckedAt: o.lastCheckedAt == null ? null : numOf(o.lastCheckedAt),
    lastLocalDay: typeof o.lastLocalDay === "string" ? o.lastLocalDay : null,
    lastRetryAt: o.lastRetryAt == null ? null : numOf(o.lastRetryAt),
    retryCount: Math.min(MAX_RETRY_COUNT, Math.max(0, Math.floor(numOf(o.retryCount)))),
    baselineComplete: Boolean(o.baselineComplete),
    baselineProcessed: Math.max(0, Math.floor(numOf(o.baselineProcessed))),
    baselineRemaining: Math.max(0, Math.floor(numOf(o.baselineRemaining))),
    pendingRunId: typeof o.pendingRunId === "string" && RUN_ID_RE.test(o.pendingRunId) ? o.pendingRunId : null,
  };
}

// K1 可恢复错误族（同族词面；不含业务/解析/额度错误）
const RECOVERABLE_RE = /fetch failed|ECONNRESET|ECONNREFUSED|socket hang up|network error|connection reset|Runtime restarted|ETIMEDOUT|timeout|超时/i;
export function isRecoverableError(message: string): boolean {
  return RECOVERABLE_RE.test(String(message ?? ""));
}
// H6 错误分级上报豁免清单（不进错误日志）
const SILENT_ERROR_RE = /余额不足|no remaining points|未配|api key|没有配置|401|403|FreeTier|置信度|JSON 解析|解析失败/i;
export function shouldLogError(message: string): boolean {
  const m = String(message ?? "");
  if (isRecoverableError(m)) return false;
  return !SILENT_ERROR_RE.test(m);
}

// B5 阶段消息 16 态（等量语义，文案全自写）
export type StageKey =
  | "watching" | "collecting" | "understanding" | "verifying" | "applying"
  | "no_new_data" | "disconnected_keep" | "cancelled" | "cancel_pending" | "preparing"
  | "waiting_idle" | "repair_retry" | "reconnecting" | "failed_reason" | "daily_quota" | "disabled";
export const STAGE_MESSAGES: Record<StageKey, string> = {
  watching: "持续留意可学习的新数据",
  collecting: "正在收集最近的数据变化",
  understanding: "正在通读并理解收集到的内容",
  verifying: "正在核对提取结果",
  applying: "正在把确认的内容写入对应位置",
  no_new_data: "这个周期没有发现值得学习的新数据",
  disconnected_keep: "与模型的连接短暂中断，本轮内容已保留",
  cancelled: "已停止本轮学习",
  cancel_pending: "已取消排队，本轮不会开始",
  preparing: "正在准备本轮学习",
  waiting_idle: "正在等待手头任务结束并满足空闲条件",
  repair_retry: "输出格式需要修正，正在自动重试",
  reconnecting: "连接恢复中，继续本轮学习",
  failed_reason: "本轮学习未完成",
  daily_quota: "今天已经完成过一次学习，请明天再来检查",
  disabled: "学习迭代已关闭",
};

// 七阶段流程条（J5 阶段名自拟）
export const STAGE_BAR = ["增量收集", "整体理解", "结构提取", "交叉核对", "内容构造", "可靠性检查", "统一发布"] as const;

// J4 最新一轮 5 指标（从 counts 派生）
export function latestRoundMetrics(counts: LearningCounts): Array<{ key: string; value: number }> {
  return [
    { key: "browse", value: counts.sources },
    { key: "memories", value: counts.memoriesCreated + counts.memoriesUpdated + counts.memoriesDisabled },
    { key: "skills", value: counts.skillsCreated + counts.skillsUpdated },
    { key: "knowledge", value: counts.knowledgeNotesCreated + counts.knowledgeNotesUpdated },
    { key: "rejected", value: counts.rejected },
  ];
}
