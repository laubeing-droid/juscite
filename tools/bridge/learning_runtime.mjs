// 功能 #18 学习迭代（步骤4·RE-18）：桥侧运行时——调度/资格/忙门/采集/回合链驱动/
// 三门验证/事务发布/回滚账本/记录面/记忆注入。唯一依据 RE-18-学习迭代.md 实现规格
// §3.2/§3.3/§3.5。内核纯函数在 packages/juscite-legal/src/kernel/learningModel.ts（件1 单源）；
// 本文件只做 IO 装配与流程编排，fs/store/回合链全部注入（合成自测可整树替换）。
// 存储根=%APPDATA%\Juscite\bridge\learning-iterations\（BRIDGE_LEARNING_ROOT 仅测试覆盖；
// 红线：只碰 Juscite 分区）。文案全部自写（表达隔离）。
//
// 桥能力差异记档（§3.5「桥无对应能力时降级并记差异」）：
// - 系统空闲秒：桥面无 OS 空闲源（竞品 Electron powerMonitor）→ 忙门 idleSeconds=null 视为
//   空闲；空闲窗口设置照存（桌面打包步骤接线 powerMonitor 后即生效）。
// - 数据合规任务忙：合规任务面未建 → 恒 false。
// - 定时任务忙：定时任务触发即派生运行中对话 → 已被「运行中线程」门覆盖（对拍行 5 等量口径）。
// - turn 超时 4h/轮询 1.5s：桥回合链自身 150s 熔断更紧，4h 顶留给轮询等待侧（先到先停）。
// - 轮内 interrupt：桥回合无中断通道 → 取消=阶段末停止（已采集保留 pendingRunId），不伪装打断。
import { randomUUID } from "node:crypto";
import { inflateSync } from "node:zlib";
import {
  copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import {
  LEARNING_THREAD_PREFIX, KNOWLEDGE_ROOT_DIR,
  normalizeLearningSettings, deriveRunStatus, nextEligibleAtOf, backoffDue, backoffDelayMs,
  evaluateBusyGate, todayEligibilityOf, localDayOf, newRunId,
  stripRagContext, isTrivialMessage, truncateHeadTail,
  extractFilePathsFromPayload, isInternalOutputPath, pathInsideWorkspace,
  chunkSource, selectWithinBudget, redactText,
  buildLearningPrompt, parseModelOutput, clampProposal, diagnoseFailure,
  validateMemoryCandidate, validateSkillCandidate, validateKnowledgeCandidate,
  hasLearningMarker, partitionProtectedSkills,
  memoryWithProvenance, mergeDuplicateMemory, memoryComparableHash, directoryHash, contentHash,
  buildUserReport, buildFailureReport, appendRollbackSection, rollbackPreflight,
  retrieveMemoriesForInjection, shouldInjectMemories,
  atomicWriteFileSync, defaultLearningState, normalizeLearningState,
  normalizeManifest, normalizeCounts, emptyCounts, displayNameOf,
  isRecoverableError, shouldLogError, STAGE_MESSAGES, TURN_TIMEOUT_MS, RUN_ID_RE,
  TOOL_CALL_SUMMARY_CAP, TURN_TRANSIENT_LIMIT, TURN_POLL_MS,
  MAX_RETRY_COUNT,
} from "../../packages/juscite-legal/src/kernel/learningModel.ts";
// 【施工单-10 单元二】结构化配置写入防御内核（用户/模型来源字符串→YAML frontmatter：
// 值一律双引号化=纯标量、键闭集闸、写入前 round-trip 键集合校验 fail-closed；单源在 @juscite/legal）。
import { writeFrontmatterChecked } from "../../packages/juscite-legal/src/kernel/configWriteModel.ts";

const LEARNING_STATE_FILE = "state.json";
const MEMORIES_FILE = "memories.json";
const TEXT_EXTS = new Set([".txt", ".md", ".markdown", ".csv", ".tsv", ".log", ".json", ".xml", ".html", ".htm", ".srt"]);
const LEARNING_DOC_EXTS = new Set([".docx", ".pdf"]); // .doc 为 OLE 老格式零依赖抽取随 #6 材料解析管线落位后接入（如实边界）
// 最小 PDF 文本抽取（C3 子项补齐）：定位 stream…endstream 文本流，FlateDecode 用 zlib.inflateSync
// 还原，未压缩流直读；提取 (…)Tj 与 […]TJ 字面量并还原转义（nrtbf/括号/反斜杠/八进制）。
// 覆盖面=拉丁文本型 PDF（含 FlateDecode 与未压缩流）；CJK CID 字体、扫描件/加密件如实
// 返回空或有限文本（不伪造正文），完整抽取随 #6 材料解析管线落位后升级。
function extractPdfText(buf) {
  const raw = buf.toString("latin1");
  const out = [];
  const re = /stream\r?\n([\s\S]*?)endstream/g;
  for (const m of raw.matchAll(re)) {
    let body = m[1];
    const head = raw.slice(Math.max(0, m.index - 300), m.index);
    if (/FlateDecode/.test(head)) {
      try { body = inflateSync(Buffer.from(body, "latin1")).toString("latin1"); } catch { /* 损坏流跳过 */ }
    }
    if (!/\bTj\b|\bTJ\b/.test(body)) continue;
    for (const t of body.matchAll(/\(((?:\\.|[^\\)])*)\)\s*Tj|\[((?:[^\]\\]|\\.)*)\]\s*TJ/g)) {
      if (t[1] !== undefined) out.push(unescapePdfString(t[1]));
      else for (const u of String(t[2]).matchAll(/\(((?:\\.|[^\\)])*)\)/g)) out.push(unescapePdfString(u[1]));
    }
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}
function unescapePdfString(sv) {
  return String(sv).replace(/\\([nrtbf()\\]|[0-7]{1,3})/g, (_, c) => {
    if (c === "n") return "\n";
    if (c === "r") return "\r";
    if (c === "t") return "\t";
    if (c === "b" || c === "f") return "";
    if (c === "(" || c === ")" || c === "\\") return c;
    return String.fromCharCode(parseInt(c, 8));
  }).replace(/\\\n/g, "");
}

export function createLearningRuntime({
  root,
  loadSettings,        // () => raw settings（桥侧 loadSetting().learningIteration）
  listThreads,         // () => [{id,title,workspaceKey,phase,updatedAt}]；抛错=线程面不可用
  threadRows,          // (id) => [{kind,state,text,toolCalls?,createdAt}]
  workspacePathOf,     // () => 对话工作区（C4 产出文件越界判定基準）
  materialsList,       // () => [{name,abs,sizeBytes}]
  readMaterialText,    // (abs) => string
  kbWalk,              // () => [{rel,abs,sizeBytes,mtimeMs}]
  kbReadText,          // (abs, ext) => string|null
  kbRoot,             // () => 知识托管根绝对路径（发布/回滚落点）
  skillsRoot,          // () => 用户技能根绝对路径（技能安装落点，对齐 #21）
  kbSync,              // () => Promise（知识写后触发索引同步）
  skillsList,          // () => [{id,dir,md}]
  protectedSkillIds,   // () => string[]（内置/预设技能，F6 不可覆盖）
  readDocxText,        // (abs) => string|null（#11 抽取器复用）
  runTurn,             // async ({runId, prompt, shouldCancel}) => {ok, text, error}
  auditWrite,          // (action, target, detail?) => void
  pollMs = 5 * 60_000, // A2 默认 5 分钟（BRIDGE_LEARNING_POLL_MS 可配）
  log = () => {},
  now = () => Date.now(),
}) {
  // ── 进程内瞬态（不持久化；重启后由持久面自然恢复）──
  let running = false;
  let queuedManual = false;
  let cancelRequested = false;
  let lastMessageKey = "watching";
  let lastMessage = STAGE_MESSAGES.watching;
  let activeRunId = null;
  let pendingSourceCount = 0;

  const runsDir = () => join(root, "runs");
  const statePath = () => join(root, LEARNING_STATE_FILE);
  const memoriesPath = () => join(root, MEMORIES_FILE);

  // ── state.json 原子读写（K3：重试+线性退避+win32 直写降级）──
  const atomicFs = {
    writeFileDirect: (p, d) => writeFileSync(p, d, "utf-8"),
    writeTmp: (p, d) => { const t = p + ".tmp-" + randomUUID().slice(0, 6); writeFileSync(t, d, "utf-8"); return t; },
    rename: (from, to) => { rmSync(to, { force: true }); renameSync(from, to); },
    unlink: (p) => rmSync(p, { force: true }),
  };
  function readState() {
    try { return normalizeLearningState(JSON.parse(readFileSync(statePath(), "utf-8"))); } catch { return defaultLearningState(); } // K9 读失败=空态全量基线
  }
  function writeState(state) {
    mkdirSync(root, { recursive: true });
    atomicWriteFileSync(atomicFs, statePath(), JSON.stringify(state, null, 2), {
      sleep: (ms) => { const t = now() + ms; while (now() < t) { /* 同步线性退避自旋 */ } },
      platform: process.platform,
    });
  }

  // ── 记忆 store 最小集（§3.5：记忆 CRUD+检索注入+policy 门；文件 JSON）──
  function memoriesRead() {
    try {
      const v = JSON.parse(readFileSync(memoriesPath(), "utf-8"));
      return Array.isArray(v) ? v : [];
    } catch { return []; }
  }
  function memoriesWrite(list) {
    mkdirSync(root, { recursive: true });
    writeFileSync(memoriesPath(), JSON.stringify(list, null, 2), "utf-8");
  }

  // ── 记录面（H9/H10/H11）──
  function listRecords() {
    let ids = [];
    try { ids = readdirSync(runsDir()).filter((n) => existsSync(join(runsDir(), n, "manifest.json"))); } catch { return []; }
    const out = [];
    for (const id of ids) {
      const m = normalizeManifest(readJsonSafe(join(runsDir(), id, "manifest.json")));
      if (m) out.push(m.summary); // 坏档跳过（H9）
    }
    out.sort((a, b) => b.startedAt - a.startedAt);
    return out;
  }
  function readRunManifest(id) {
    if (!RUN_ID_RE.test(String(id ?? ""))) return null; // H10 防路径逃逸
    return normalizeManifest(readJsonSafe(join(runsDir(), String(id), "manifest.json")));
  }
  function readRecordDetail(id) {
    const m = readRunManifest(id);
    if (!m) return null;
    let reportMarkdown = "";
    try { reportMarkdown = readFileSync(join(runsDir(), String(id), "REPORT.md"), "utf-8"); } catch { /* 旧档缺报告→空 */ }
    return { summary: m.summary, reportMarkdown, userReport: reportMarkdown };
  }
  function readJsonSafe(p) {
    try { return JSON.parse(readFileSync(p, "utf-8")); } catch { return null; }
  }

  // ═══ 语料采集（C1-C13；七类源，全部有界）═══
  function collectCorpus(state) {
    const bases = []; // {baseKey, kind, title, metaFp, chunks:[LearningSource]}
    const ws = workspacePathOf();
    const stats = { threads: 0, knowledgeFiles: 0, uploadedFiles: 0, generatedFiles: 0 };
    const seenKinds = { thread: 0, memory: 0, knowledge: 0, skill: 0, "uploaded-file": 0, "generated-file": 0, process: 0 };
    const addBase = (baseKey, kind, title, metaFp, content) => {
      seenKinds[kind] = (seenKinds[kind] ?? 0) + 1;
      if (seenKinds[kind] > capOf(kind)) return; // C3/C5/C6/C7 数量帽
      const chunks = chunkSource({ kind, title, content, seedFingerprint: metaFp, metadata: { baseKey, cursorKey: baseKey, cursorFingerprint: metaFp } });
      bases.push({ baseKey, kind, title, metaFp, chunks });
    };
    const claimedAttachmentNames = new Set(); // C3 已按线程收过的附件名（跨线程去重）
    // C1/C2/C4/C8：线程正文+过程记录+Agent 产出（学习线程与独立工作区线程排除）
    let threads = [];
    let threadsUnavailable = false;
    try { threads = listThreads() ?? []; } catch { threadsUnavailable = true; } // A6 保守忙
    for (const t of threads) {
      if (t.workspaceKey === "learning://juscite-learning") continue; // C8 学习线程不作语料
      const metaFp = contentHash([t.id, t.title, t.phase, String(t.updatedAt ?? "")].join("|"));
      const baseKey = `thread:${t.id}`;
      if (state.sourceHashes[`meta:${baseKey}`] === metaFp) continue; // C9 meta 级增量
      let rows = [];
      try { rows = threadRows(t.id) ?? []; } catch { continue; }
      const userTexts = [];
      const processTexts = [];
      const toolPayloads = [];
      const threadAttachmentNames = new Set(); // C3：按线程 attachmentIds 去重收集
      for (const r of rows) {
        if (r.kind === "userInput") {
          const stripped = stripRagContext(r.text ?? ""); // C1 RAG 剥离
          if (isTrivialMessage(stripped)) continue;       // C1 无实义过滤
          userTexts.push(truncateHeadTail(stripped));      // C1 6000 掐头留尾
          for (const key of ["attachments", "attachmentIds", "attachmentNames"]) {
            const v = r[key];
            if (!Array.isArray(v)) continue;
            for (const a of v) {
              const name = typeof a === "string" ? a : String((a && (a.name ?? a.fileName ?? a.id)) ?? "");
              if (name.trim()) threadAttachmentNames.add(name.trim());
            }
          }
        } else if (r.kind === "assistantText" && r.state === "complete" && (r.text ?? "").trim()) {
          processTexts.push(truncateHeadTail(r.text, 4000, 1000)); // C2 ≤4000
        } else if (r.kind === "assistantText" && r.state === "failed" && (r.text ?? "").trim()) {
          processTexts.push("[失败回合] " + [...(r.text ?? "")].slice(0, TOOL_CALL_SUMMARY_CAP).join("")); // C2 失败回合截 500
        }
        if (Array.isArray(r.toolCalls)) for (const tc of r.toolCalls) {
          if (!tc) continue;
          toolPayloads.push(tc); // C4 产出来源
          // C2 工具调用摘要（≤500）：工具名+输出/输入概要；失败调用以错误详情入过程（失败 tool_result 要素）
          const brief = [...String(tc.error ?? tc.output ?? tc.input ?? "")].slice(0, TOOL_CALL_SUMMARY_CAP).join("");
          processTexts.push(tc.error
            ? "[工具失败] " + String(tc.name ?? "tool") + "：" + brief
            : "[工具] " + String(tc.name ?? "tool") + "：" + brief);
        }
      }
      if (userTexts.length) {
        stats.threads++;
        addBase(baseKey, "thread", t.title || t.id, metaFp, redactText(userTexts.join("\n\n"))); // C12 入语料前统一脱敏
      }
      if (processTexts.length) {
        const pBase = `process:${t.id}`;
        if (state.sourceHashes[`meta:${pBase}`] !== metaFp) {
          addBase(pBase, "process", (t.title || t.id) + " · 过程记录", metaFp, redactText(processTexts.join("\n\n")));
        }
      }
      // C4/K5：Agent 产出文件=成功 file_change 类调用（等量口径：有 output 无 error 的工具调用）
      let genCount = 0;
      for (const tc of toolPayloads) {
        if (genCount >= 16) break;
        if (!tc || tc.error || !tc.output) continue;
        if (/^knowledge[_-]/i.test(String(tc.name ?? ""))) continue; // C4：知识库工具产物排除（防自我吞噬同源口径）
        let payload;
        try { payload = JSON.parse(tc.output); } catch { payload = { path: tc.output }; } // 纯文本 output 也给单键一路
        let paths = [];
        try { paths = extractFilePathsFromPayload({ input: safeJson(tc.input), output: payload }); } catch { paths = []; }
        for (const p of paths) {
          if (genCount >= 16) break;
          if (isInternalOutputPath(p) || !pathInsideWorkspace(p, ws)) continue; // K5 越界/内部目录
          const abs = p.replace(/\//g, "\\");
          let st;
          try { st = statSync(abs); } catch { continue; } // 调用失败/不存在→不采
          if (st.size > 25 * 1024 * 1024) continue;
          const ext = abs.slice(abs.lastIndexOf(".")).toLowerCase();
          let text = null;
          if (TEXT_EXTS.has(ext)) { try { const buf = readFileSync(abs); if (!buf.includes(0)) text = buf.toString("utf-8"); } catch { continue; } }
          else if (LEARNING_DOC_EXTS.has(ext)) {
            try { const buf = readFileSync(abs); text = ext === ".pdf" ? extractPdfText(buf) : (readDocxText ? readDocxText(buf) : null); } catch { text = null; }
          }
          if (text === null || !text.trim()) continue;
          const gBase = `generated:${contentHash(abs)}`;
          if (state.sourceHashes[`meta:${gBase}`] === contentHash(text)) continue; // 内容未变
          genCount++;
          stats.generatedFiles++;
          addBase(gBase, "generated-file", abs.split("\\").pop() ?? abs, contentHash(text), redactText(truncateHeadTail(text, 20000, 2000)));
        }
      }
    }
    // C3：上传附件。优先按线程 attachmentIds 去重直采（≤16/线程，跨线程同名首见为准）；
    // 其余无归属材料走全局兜底 ≤16（桥面材料无归属记差异保留）。文本直读；.pdf 走
    // extractPdfText；.docx 走抽取器；.doc 待 #6（如实跳过）。
    try {
      const claimAttachment = (m) => {
        if (m.sizeBytes > 25 * 1024 * 1024) return false;
        const ext = m.name.slice(m.name.lastIndexOf(".")).toLowerCase();
        if (!TEXT_EXTS.has(ext) && !LEARNING_DOC_EXTS.has(ext)) return false;
        if (state.sourceHashes[`meta:upload:${m.name}`] === contentHash(`${m.name}|${m.sizeBytes}`)) return false;
        let text = null;
        try {
          if (TEXT_EXTS.has(ext)) {
            const t = readMaterialText(m.abs);
            text = String(t ?? "").trim() ? String(t) : null;
          } else {
            const buf = readFileSync(m.abs);
            text = ext === ".pdf" ? extractPdfText(buf) : (readDocxText ? readDocxText(buf) : null);
            if (text !== null && !String(text).trim()) text = null;
          }
        } catch { return false; }
        if (text === null) return false;
        stats.uploadedFiles++;
        addBase(`upload:${m.name}`, "uploaded-file", m.name, contentHash(`${m.name}|${m.sizeBytes}`), redactText(truncateHeadTail(text, 20000, 2000)));
        return true;
      };
      // ① 线程 attachmentIds 直采（每线程 ≤16）
      for (const t of threads) {
        let n = 0;
        try {
          for (const r of threadRows(t.id) ?? []) {
            if (n >= 16) break;
            for (const key of ["attachments", "attachmentIds", "attachmentNames"]) {
              const v = r && r[key];
              if (!Array.isArray(v)) continue;
              for (const a of v) {
                if (n >= 16) break;
                const name = (typeof a === "string" ? a : String((a && (a.name ?? a.fileName ?? a.id)) ?? "")).trim();
                if (!name || claimedAttachmentNames.has(name)) continue;
                const hit = (materialsList() ?? []).find((m) => m.name === name);
                if (!hit) continue;
                if (claimAttachment(hit)) { claimedAttachmentNames.add(name); n++; }
              }
            }
          }
        } catch { /* 单线程附件面读失败→跳过 */ }
      }
      // ② 无归属材料全局兜底 ≤16
      let upCount = 0;
      for (const m of materialsList() ?? []) {
        if (upCount >= 16) break;
        if (claimedAttachmentNames.has(m.name)) continue; // 已按线程收过→不重复入语料
        if (claimAttachment(m)) upCount++;
      }
    } catch { /* 材料面读失败→该类空 */ }
    // C5：知识库变更文件 ≤12（hash 增量）
    try {
      let kbCount = 0;
      for (const f of kbWalk() ?? []) {
        if (kbCount >= 12) break;
        const ext = f.rel.slice(f.rel.lastIndexOf(".")).toLowerCase();
        const text = kbReadText(f.abs, ext);
        if (text === null || !String(text).trim()) continue; // 读失败跳过
        const baseKey = `kb:${f.rel}`;
        const fp = contentHash(text);
        if (state.sourceHashes[`meta:${baseKey}`] === fp) continue;
        kbCount++;
        stats.knowledgeFiles++;
        addBase(baseKey, "knowledge", f.rel, fp, redactText(truncateHeadTail(String(text), 20000, 2000)));
      }
    } catch { /* 知识面读失败→该类空 */ }
    // C7：技能定义变更 ≤60
    try {
      let skCount = 0;
      for (const s of skillsList() ?? []) {
        if (skCount >= 60) break;
        if (!s.md.trim()) continue;
        const baseKey = `skill:${s.id}`;
        const fp = contentHash(s.md);
        if (state.sourceHashes[`meta:${baseKey}`] === fp) continue;
        skCount++;
        addBase(baseKey, "skill", s.id, fp, redactText(truncateHeadTail(s.md, 20000, 2000)));
      }
    } catch { /* 技能面读失败→该类空 */ }
    // C6：记忆变更 ≤60（全量可比 JSON hash 增量）
    try {
      let memCount = 0;
      for (const mem of memoriesRead()) {
        if (memCount >= 60) break;
        const body = JSON.stringify(mem);
        const baseKey = `memory:${mem.id}`;
        const fp = memoryComparableHash(mem);
        if (state.sourceHashes[`meta:${baseKey}`] === fp) continue;
        memCount++;
        addBase(baseKey, "memory", String(mem.category ?? "memory") + " · " + String(mem.id ?? ""), fp, redactText(truncateHeadTail(body, 20000, 2000)));
      }
    } catch { /* 记忆面读失败→该类空 */ }
    // C9 分块级增量：已学过的块（指纹一致）不再入语料
    const candidates = [];
    for (const b of bases) {
      const fresh = b.chunks.filter((c) => state.sourceHashes[`chk:${c.key}`] !== c.fingerprint);
      for (const c of fresh) candidates.push(c);
    }
    return { candidates, bases, stats, threadsUnavailable };
  }
  function capOf(kind) {
    return { thread: 9999, memory: 60, knowledge: 12, skill: 60, "uploaded-file": 16, "generated-file": 9999, process: 9999 }[kind] ?? 9999;
  }
  function safeJson(s) { try { return JSON.parse(s ?? ""); } catch { return { text: s }; } }

  // ═══ 单轮 run（§3.3 主流程）═══
  async function runOnce(manual) {
    const startedAt = now();
    const state0 = readState();
    // K10：pendingRunId 复用续跑（run 目录不换，不当作新轮）
    const runId = state0.pendingRunId && RUN_ID_RE.test(state0.pendingRunId) ? state0.pendingRunId : newRunId(startedAt, randomUUID().slice(0, 8));
    const runDir = join(runsDir(), runId);
    const resuming = state0.pendingRunId === runId;
    activeRunId = runId;
    setMessage("collecting");
    const collected = collectCorpus(state0);
    if (collected.threadsUnavailable) {
      // A6 线程面不可用按忙处理：不入轮，等下个 tick
      activeRunId = null;
      setMessage("waiting_idle");
      return { ok: false, reason: "busy-threads" };
    }
    const selection = selectWithinBudget(collected.candidates);
    pendingSourceCount = new Set(collected.candidates.map((c) => c.metadata.baseKey)).size;
    // 基线回填账（K9）：首轮记剩余基数，逐轮推进
    let state = state0;
    if (!state.baselineComplete && state.baselineRemaining === 0 && state.baselineProcessed === 0 && collected.bases.length > 0) {
      state = { ...state, baselineRemaining: collected.bases.length };
    }
    if (selection.selected.length === 0) {
      // C13 无变化不建空报告：只写检查时间与基线态，不建 run 目录不产生记录
      state = { ...state, lastCheckedAt: now(), pendingRunId: null };
      writeState(state);
      activeRunId = null;
      setMessage("no_new_data");
      return { ok: true, noNewData: true };
    }
    if (!resuming) {
      mkdirSync(join(runDir, "rollback", "skills"), { recursive: true });
      writeFileSync(join(runDir, "INPUT.md"), corpusArchive(collected, selection), "utf-8"); // H1 全语料留档（K8 明文）
      state = { ...state, pendingRunId: runId };
      writeState(state); // K10 落盘后进程重启可续
    }
    if (cancelRequested) { cancelRequested = false; setMessage("cancelled"); return { ok: false, reason: "cancelled" }; } // D5 阶段末停止
    setMessage("understanding");
    const prompt = buildLearningPrompt(selection.selected);
    // D3/D4/D8：学习回合（1.5s 轮询在 runTurn 内）+ 瞬时断连容错 + 修复重跑共 ≤2 轮
    let text = null;
    let lastError = null;
    let parseError = null;
    for (let attempt = 0; attempt < 2; attempt++) {
      if (cancelRequested) { cancelRequested = false; setMessage("cancelled"); return { ok: false, reason: "cancelled" }; }
      const p = attempt === 0 ? prompt : buildLearningPrompt(undefined, { repairError: parseError ?? "", previousOutput: text ?? "" });
      // D4：同一学习轮内瞬时断连容错 ≤TURN_TRANSIENT_LIMIT 次继续等（消息「连接恢复中」），超出落 K1 requeue
      let out = null;
      for (let transientTries = 0; ; transientTries++) {
        try { out = await runTurn({ runId, prompt: p, shouldCancel: () => cancelRequested }); } catch (e) { out = { ok: false, error: String(e?.message ?? e) }; }
        if (cancelRequested) break; // D5 轮内取消位（取消优先于容错）
        if (!out.ok && isRecoverableError(String(out.error ?? "")) && transientTries < TURN_TRANSIENT_LIMIT) {
          setMessage("reconnecting"); // B5「断连恢复中」：连接恢复中，继续本轮学习
          await new Promise((r) => setTimeout(r, TURN_POLL_MS)); // 1.5s 后重试同一轮
          continue;
        }
        break;
      }
      if (cancelRequested) { // D5 轮内取消位：本回合收口即停，已采集保留 pendingRunId
        cancelRequested = false;
        setMessage("cancelled");
        return { ok: false, reason: "cancelled" };
      }
      try { writeFileSync(join(runDir, attempt === 0 ? "MODEL_OUTPUT.txt" : "MODEL_OUTPUT_RETRY_1.txt"), out.text ?? "", "utf-8"); } catch { /* 落盘失败不阻流程 */ } // D8 每轮原始输出落盘
      if (!out.ok) {
        lastError = out.error ?? "模型连接失败";
        if (isRecoverableError(lastError)) {
          // K1 可恢复错误：保留本轮 requeue，不写失败记录、不上报错误
          state = { ...readState(), pendingRunId: runId };
          writeState(state);
          activeRunId = null;
          setMessage("disconnected_keep");
          return { ok: false, reason: "recoverable", error: lastError };
        }
        break;
      }
      text = out.text ?? "";
      try { parseModelOutput(text); parseError = null; break; } // 可解析→收口
      catch (e) {
        parseError = String(e?.message ?? e);
        if (attempt === 0) setMessage("repair_retry"); // D8 修复轮提示
      }
    }
    if (parseError !== null || text === null) {
      // D6 诊断四级回退 → 失败记录（H5）+ 退避（A7）
      const diagnosis = diagnoseFailure({ lastErrorItem: lastError ?? parseError, bareStatus: "学习回合未产出可解析结果" });
      return finalizeFailure(runId, runDir, collected, selection, diagnosis, resuming);
    }
    setMessage("verifying");
    let proposal;
    try { proposal = clampProposal(parseModelOutput(text)); } catch (e) {
      return finalizeFailure(runId, runDir, collected, selection, diagnoseFailure({ lastErrorItem: String(e?.message ?? e) }), resuming);
    }
    // ═══ Host 验证门（模型说了不算，F1-F7）═══
    const knownSources = new Map();
    for (const c of selection.selected) knownSources.set(c.key, { kind: c.kind });
    for (const b of collected.bases) knownSources.set(b.baseKey, { kind: b.kind });
    const counts = { ...emptyCounts(), sources: new Set(collected.candidates.map((c) => c.metadata.baseKey)).size, threads: collected.stats.threads, knowledgeFiles: collected.stats.knowledgeFiles, uploadedFiles: collected.stats.uploadedFiles, generatedFiles: collected.stats.generatedFiles };
    const rejectedList = [...(proposal.rejected ?? []).map((r) => ({ kind: r.kind, reason: String(r.reason ?? ""), brief: String(r.brief ?? "") }))];
    const memCtx = { existingMemories: memoriesRead(), knownSources };
    const validMemories = [];
    for (const m of proposal.memories ?? []) {
      const v = validateMemoryCandidate(m, memCtx);
      if (v.ok) validMemories.push(m);
      else rejectedList.push({ kind: "memory", reason: v.reason ?? "", brief: [...String(m.content ?? "")].slice(0, 40).join("") });
    }
    const prot = partitionProtectedSkills(proposal.skills ?? [], protectedSkillIds() ?? []); // F6
    for (const r of prot.rejected) rejectedList.push({ kind: "skill", reason: r.reason, brief: String(r.candidate.id ?? "") });
    const validSkills = [];
    for (const s of prot.allowed) {
      const v = validateSkillCandidate(s, { knownSources });
      if (v.ok) validSkills.push(s);
      else rejectedList.push({ kind: "skill", reason: v.reason ?? "", brief: String(s.id ?? "") });
    }
    const existingKb = new Set((kbWalk() ?? []).map((f) => f.rel));
    const learnedPaths = new Set();
    const validKnowledge = [];
    for (const k of proposal.knowledgeNotes ?? []) {
      const v = validateKnowledgeCandidate(k, { knownSources, existingPaths: existingKb, learnedPathsThisRun: learnedPaths });
      if (v.ok) { validKnowledge.push(k); learnedPaths.add(kPathOf(k.path)); }
      else rejectedList.push({ kind: "knowledgeNote", reason: v.reason ?? "", brief: String(k.title ?? k.path ?? "") });
    }
    counts.rejected = rejectedList.length;
    if (cancelRequested) { cancelRequested = false; setMessage("cancelled"); return { ok: false, reason: "cancelled" }; }
    // G7：0 变更也可成记录（全部被拒→completed、rejected>0、canRollback=false）
    setMessage("applying");
    const manifest = {
      version: 1,
      summary: {
        id: runId, title: [...String(proposal.title || "学习迭代")].slice(0, 40).join(""),
        displayName: displayNameOf(runId, [...String(proposal.title || "学习迭代")].slice(0, 40).join("")),
        status: "running", startedAt, finishedAt: now(),
        reportPath: join(runDir, "REPORT.md"), canRollback: false, counts,
      },
      sourceHashes: {},
      rollback: { memories: [], skills: [], knowledge: [] },
      modelResult: { ...proposal, rejected: rejectedList },
    };
    try {
      await publishAll({ runId, runDir, validMemories, validSkills, validKnowledge, counts, manifest, rejectedList });
    } catch (e) {
      // G5 发布中途失败：publishAll 已逆序撤销；整轮作失败记录
      return finalizeFailure(runId, runDir, collected, selection, diagnoseFailure({ lastErrorItem: "发布中断：" + String(e?.message ?? e) }), resuming);
    }
    // ═══ 收口：REPORT + manifest + state 游标合并 ═══
    const rollbackOps = manifest.rollback;
    const anyChange = rollbackOps.memories.length + rollbackOps.skills.length + rollbackOps.knowledge.length > 0;
    const zeroChange = !anyChange;
    manifest.summary.status = "completed";
    manifest.summary.finishedAt = now();
    manifest.summary.canRollback = anyChange;
    const report = buildUserReport({ modelResult: { ...proposal, rejected: rejectedList }, counts, canRollback: anyChange, zeroChange });
    writeFileSync(join(runDir, "REPORT.md"), report, "utf-8");
    // C9/C10 游标推进：全块入选的 base 才推 meta；入选块记指纹
    const selByBase = new Map();
    for (const c of selection.selected) {
      if (!selByBase.has(c.metadata.baseKey)) selByBase.set(c.metadata.baseKey, new Set());
      selByBase.get(c.metadata.baseKey).add(c.key);
    }
    const mergedHashes = { ...state.sourceHashes };
    for (const b of collected.bases) {
      const selSet = selByBase.get(b.baseKey);
      if (!selSet || selSet.size === 0) continue;
      const all = b.chunks.every((c) => selSet.has(c.key));
      for (const c of b.chunks) if (selSet.has(c.key)) mergedHashes[`chk:${c.key}`] = c.fingerprint;
      if (all) mergedHashes[`meta:${b.baseKey}`] = b.metaFp; // C10 全块入选才推 meta
    }
    const st2 = readState();
    const advanced = [...selByBase.keys()].filter((k) => collected.bases.some((b) => b.baseKey === k));
    const baselineProcessed = st2.baselineProcessed + advanced.length;
    const baselineRemaining = Math.max(0, st2.baselineRemaining - advanced.length);
    writeState({
      ...st2,
      sourceHashes: mergedHashes,
      lastCheckedAt: now(),
      lastSuccessfulAt: now(),
      lastLocalDay: localDayOf(now()),
      lastRetryAt: null,
      retryCount: 0,
      pendingRunId: null,
      baselineComplete: baselineRemaining === 0,
      baselineProcessed,
      baselineRemaining,
    });
    manifest.sourceHashes = mergedHashes; // H2 账本带游标
    writeJson(join(runDir, "manifest.json"), manifest);
    activeRunId = null;
    setMessage(zeroChange ? "no_new_data" : "applying", zeroChange ? STAGE_MESSAGES.no_new_data : undefined);
    log(`[learning] run ${runId} completed: mem=${counts.memoriesCreated + counts.memoriesUpdated + counts.memoriesDisabled} skill=${counts.skillsCreated + counts.skillsUpdated} kb=${counts.knowledgeNotesCreated + counts.knowledgeNotesUpdated} rejected=${counts.rejected}`);
    return { ok: true, runId };
  }

  function kPathOf(p) { return normalizeKnowledgePathRel(p); }
  function corpusArchive(collected, selection) {
    const lines = ["# 本轮语料留档", "", `生成时间：${new Date(now()).toLocaleString("zh-CN")}`, ""];
    for (const c of selection.selected) {
      lines.push(`## [${c.kind}] ${c.title}${c.metadata.chunkIndex !== undefined ? `（第 ${c.metadata.chunkIndex + 1}/${c.metadata.chunkCount} 段）` : ""}`, "", c.content, "");
    }
    if (!selection.selected.length) lines.push("（本轮无入选语料）");
    return lines.join("\n");
  }

  // ═══ 事务发布（G1-G6；发布序 记忆→技能→知识，逆序撤销=知识→技能→记忆）═══
  async function publishAll({ runId, runDir, validMemories, validSkills, validKnowledge, counts, manifest, rejectedList }) {
    const done = { memories: [], skills: [], knowledge: [] };
    const undo = async () => {
      // G5 逆序撤销已应用部分
      for (const op of [...done.knowledge].reverse()) await undoKnowledgeOp(op, runDir);
      for (const op of [...done.skills].reverse()) undoSkillOp(op, runDir);
      for (const op of [...done.memories].reverse()) undoMemoryOp(op);
    };
    try {
      // ── 记忆（G1/G2）──
      const mems = memoriesRead();
      for (const m of validMemories) {
        if (m.action === "disable") {
          const idx = mems.findIndex((x) => String(x.id) === String(m.targetId));
          if (idx < 0) { rejectedList.push({ kind: "memory", reason: "要停用的记忆不存在", brief: String(m.targetId ?? "") }); continue; }
          const before = { ...mems[idx] };
          mems[idx] = { ...before, disabled: true, updatedAt: now() }; // G2 disable 仅置 disabled
          manifest.rollback.memories.push({ area: "memory", op: "restore", id: before.id, before, afterHash: memoryComparableHash(mems[idx]) });
          done.memories.push(manifest.rollback.memories[manifest.rollback.memories.length - 1]);
          counts.memoriesDisabled++;
          continue;
        }
        if (m.action === "update") {
          const idx = mems.findIndex((x) => String(x.id) === String(m.targetId));
          if (idx < 0) { rejectedList.push({ kind: "memory", reason: "要更新的记忆不存在", brief: String(m.targetId ?? "") }); continue; }
          const before = { ...mems[idx] };
          mems[idx] = { ...before, content: String(m.content ?? before.content), confidence: Number(m.confidence) || before.confidence, updatedAt: now() };
          manifest.rollback.memories.push({ area: "memory", op: "restore", id: before.id, before, afterHash: memoryComparableHash(mems[idx]) });
          done.memories.push(manifest.rollback.memories[manifest.rollback.memories.length - 1]);
          counts.memoriesUpdated++;
          continue;
        }
        // create：等价重复=同类别+内容可比哈希一致
        const dupIdx = mems.findIndex((x) => !x.deleted && x.category === m.category && memoryComparableHash(x.content) === memoryComparableHash(m.content));
        if (dupIdx >= 0) {
          const before = { ...mems[dupIdx] };
          const merged = mergeDuplicateMemory(memoryWithProvenance(before, runId), memoryWithProvenance({ ...before, content: String(m.content), confidence: Number(m.confidence) || before.confidence, evidence: m.evidence ?? [] }, runId));
          mems[dupIdx] = merged;
          manifest.rollback.memories.push({ area: "memory", op: "restore", id: before.id, before, afterHash: memoryComparableHash(merged) });
          done.memories.push(manifest.rollback.memories[manifest.rollback.memories.length - 1]);
          counts.memoriesUpdated++;
          continue;
        }
        const created = memoryWithProvenance({
          id: "mem_" + randomUUID().replace(/-/g, "").slice(0, 12),
          category: m.category, content: String(m.content ?? ""), confidence: Number(m.confidence) || 0.85,
          evidence: m.evidence ?? [], always: false, createdAt: now(), updatedAt: now(),
        }, runId);
        mems.push(created);
        manifest.rollback.memories.push({ area: "memory", op: "delete-created", id: created.id, before: null, afterHash: memoryComparableHash(created) });
        done.memories.push(manifest.rollback.memories[manifest.rollback.memories.length - 1]);
        counts.memoriesCreated++;
      }
      memoriesWrite(mems);
      // ── 技能（G3：先备份→临时目录三件套→删旧→rename）──
      for (const s of validSkills) {
        const target = join(skillsRoot(), s.id);
        const tmp = join(runDir, "rollback", "skills", "." + s.id + ".tmp-" + randomUUID().slice(0, 6));
        mkdirSync(tmp, { recursive: true });
        const desc = [...String(s.description ?? "").replace(/\r?\n/g, " ")].slice(0, 120).join("");
        writeFileSync(join(tmp, "SKILL.md"), rebuildSkillMarkdown(s, desc), "utf-8");
        writeFileSync(join(tmp, "test-prompts.json"), JSON.stringify((s.tests ?? []).map((t) => ({ category: t.category, input: t.input, passed: t.passed })), null, 2), "utf-8");
        writeFileSync(join(tmp, "learning.json"), JSON.stringify({ generatedBy: "learning-iteration", sourceIterationId: runId, updatedAt: now() }, null, 2), "utf-8");
        const existed = existsSync(target);
        if (existed) {
          const backup = join(runDir, "rollback", "skills", s.id);
          copyDirSync(target, backup); // G3 已存在→先整目录备份（cpSync 本机 node 22.23.1 原生崩溃，用 readdir+copyFile 等价面）
          manifest.rollback.skills.push({ area: "skill", op: "restore", id: s.id, targetPath: target, backupPath: backup, afterHash: hashDirSafe(target) });
        } else {
          manifest.rollback.skills.push({ area: "skill", op: "delete-created", id: s.id, targetPath: target, afterHash: "" });
        }
        const op = manifest.rollback.skills[manifest.rollback.skills.length - 1];
        rmSync(target, { recursive: true, force: true }); // 删旧
        copyDirSync(tmp, target);          // rename 等量（跨卷安全用复制）
        rmSync(tmp, { recursive: true, force: true });
        op.afterHash = hashDirSafe(target); // H7 preflight 基准=发布后状态（目录递归 hash）
        done.skills.push(op);
        if (existed) counts.skillsUpdated++; else counts.skillsCreated++;
      }
      // ── 知识笔记（G4：统一 frontmatter+学习标记+写后同步）──
      for (const k of validKnowledge) {
        const rel = normalizeKnowledgePathRel(k.path);
        const abs = join(kbRoot(), ...rel.split("/"));
        if (!abs.toLowerCase().startsWith(kbRoot().toLowerCase())) throw new Error("知识落点越出托管根");
        const existed = existsSync(abs);
        let beforeContent = null;
        if (existed) {
          beforeContent = readFileSync(abs, "utf-8");
          if (!hasLearningMarker(beforeContent)) { // F5 update 仅限学习产物
            rejectedList.push({ kind: "knowledgeNote", reason: "目标笔记不是学习产物，不覆盖", brief: rel });
            continue;
          }
        }
        mkdirSync(dirname(abs), { recursive: true });
        const body = stripModelFrontmatter(String(k.content ?? ""));
        // 单元二防御：title/summary 为模型来源字符串——一律走 writeFrontmatterChecked
        // （双引号化纯标量+键闭集+round-trip 键集合零变化校验，坏配置 typed 拒不落盘）。
        const frontmatter = writeFrontmatterChecked([
          { key: "title", value: String(k.title ?? "").replace(/\r?\n/g, " ") },
          { key: "summary", value: String(k.summary ?? "").replace(/\r?\n/g, " ") },
          { key: "generated_by", value: "learning-iteration" },
          { key: "source_iteration", value: runId },
          { key: "updated_at", value: new Date(now()).toISOString() },
        ], ["title", "summary", "generated_by", "source_iteration", "updated_at"]);
        const finalContent = [
          frontmatter,
          "",
          `<!-- ${"juscite-learning-artifact"}：本文件由学习迭代生成，可整轮回滚 -->`,
          "",
          body.replace(new RegExp(`<!--\\s*${"juscite-learning-artifact"}[^>]*-->`, "g"), "").trim(),
          "",
        ].join("\n");
        writeFileSync(abs, finalContent, "utf-8");
        manifest.rollback.knowledge.push(existed
          ? { area: "knowledge", op: "restore", path: rel, beforeContent, afterHash: contentHash(finalContent) }
          : { area: "knowledge", op: "delete-created", path: rel, afterHash: contentHash(finalContent) });
        done.knowledge.push(manifest.rollback.knowledge[manifest.rollback.knowledge.length - 1]);
        if (existed) counts.knowledgeNotesUpdated++; else counts.knowledgeNotesCreated++;
      }
      try { await kbSync(); } catch { /* 索引同步失败不阻断发布（文件已落盘，下轮同步收敛） */ }
    } catch (e) {
      await undo();
      throw e;
    }
  }
  function rebuildSkillMarkdown(s, descSingleLine) {
    const body = stripModelFrontmatter(String(s.skillMarkdown ?? "")).trim();
    const skeleton = body || [
      "# " + String(s.name ?? s.id),
      "",
      "## 用途",
      String(s.description ?? ""),
      "",
      "## 做法",
      "1. 按用户交代的材料执行本技能的固定步骤。",
      "2. 完成后核对清单，逐条确认无遗漏。",
    ].join("\n");
    // 单元二防御：name(id)/description 为模型来源字符串——同知识笔记面，写前 round-trip 校验。
    const frontmatter = writeFrontmatterChecked([
      { key: "name", value: String(s.id ?? "") },
      { key: "description", value: descSingleLine },
    ], ["name", "description"]);
    return [frontmatter, "", skeleton, ""].join("\n");
  }
  function stripModelFrontmatter(md) {
    const m = /^---\r?\n[\s\S]*?\r?\n---\s*\n/.exec(md);
    return m ? md.slice(m[0].length) : md;
  }
  function undoMemoryOp(op) {
    const mems = memoriesRead();
    if (op.op === "delete-created") { memoriesWrite(mems.filter((x) => String(x.id) !== String(op.id))); return; }
    const idx = mems.findIndex((x) => String(x.id) === String(op.id));
    if (idx >= 0 && op.before) mems[idx] = op.before; // restore：快照含 disabled/restore 语义
    memoriesWrite(mems);
  }
  function undoSkillOp(op, runDir) {
    if (op.op === "delete-created") { rmSync(op.targetPath, { recursive: true, force: true }); return; }
    if (op.backupPath && existsSync(op.backupPath)) {
      rmSync(op.targetPath, { recursive: true, force: true });
      copyDirSync(op.backupPath, op.targetPath);
    }
  }
  async function undoKnowledgeOp(op, runDir) {
    const abs = join(kbRoot(), ...String(op.path).split("/"));
    if (op.op === "delete-created") { rmSync(abs, { force: true }); }
    else if (op.beforeContent !== undefined && op.beforeContent !== null) { writeFileSync(abs, op.beforeContent, "utf-8"); }
    try { await kbSync(); } catch { /* 同上 */ }
  }
  function hashDirSafe(dir) {
    if (!existsSync(dir)) return "";
    const files = [];
    const walk = (d, prefix) => {
      for (const e of readdirSync(d, { withFileTypes: true })) {
        const rel = prefix ? prefix + "/" + e.name : e.name;
        if (e.isDirectory()) walk(join(d, e.name), rel);
        else if (e.isFile()) { try { files.push({ rel, content: readFileSync(join(d, e.name), "utf-8") }); } catch { files.push({ rel, content: "<binary>" }); } }
      }
    };
    try { walk(dir, ""); } catch { return ""; }
    return directoryHash(files);
  }

  // ═══ 失败收口（H5/H6/A7）═══
  function finalizeFailure(runId, runDir, collected, selection, diagnosis, resuming) {
    const state = readState();
    const counts = normalizeCounts({ sources: new Set(collected.candidates.map((c) => c.metadata.baseKey)).size, threads: collected.stats.threads });
    const backoffMinutes = Math.round(backoffDelayMs(state.retryCount) / 60000);
    writeFileSync(join(runDir, "REPORT.md"), buildFailureReport(diagnosis, backoffMinutes), "utf-8");
    const manifest = {
      version: 1,
      summary: {
        id: runId, title: "本轮学习未完成", displayName: displayNameOf(runId, "本轮学习未完成"), status: "failed",
        startedAt: now(), finishedAt: now(), reportPath: join(runDir, "REPORT.md"),
        canRollback: false, error: diagnosis, counts,
      },
      sourceHashes: state.sourceHashes,
      rollback: { memories: [], skills: [], knowledge: [] },
    };
    writeJson(join(runDir, "manifest.json"), manifest);
    writeState({ ...state, lastRetryAt: now(), retryCount: Math.min(MAX_RETRY_COUNT, state.retryCount + 1), pendingRunId: null, lastCheckedAt: now() });
    if (shouldLogError(diagnosis)) log(`[learning] run ${runId} failed: ${diagnosis}`); // H6 错误分级上报
    activeRunId = null;
    setMessage("failed_reason", STAGE_MESSAGES.failed_reason + "：" + diagnosis);
    return { ok: false, reason: "failed", error: diagnosis };
  }

  // ═══ 回滚（H7/H8）═══
  async function rollbackRun(id) {
    if (running) throw new Error("本轮学习正在进行，不能回滚");
    const m = readRunManifest(id);
    if (!m) throw new Error("记录不存在或档案损坏");
    if (!m.summary.canRollback) throw new Error("该记录没有可回滚的变更");
    // preflight：三类对象当前 hash 逐一与 afterHash 比对，任一漂移→整体中止
    const mems = memoriesRead();
    const items = [];
    for (const op of m.rollback.memories) {
      const cur = mems.find((x) => String(x.id) === String(op.id));
      items.push({ area: "memory", ref: op.id, expectHash: op.afterHash, currentHash: cur ? memoryComparableHash(cur) : "" });
    }
    for (const op of m.rollback.skills) items.push({ area: "skill", ref: op.id, expectHash: op.afterHash, currentHash: hashDirSafe(op.targetPath) });
    for (const op of m.rollback.knowledge) {
      const abs = join(kbRoot(), ...String(op.path).split("/"));
      let cur = "";
      try { cur = contentHash(readFileSync(abs, "utf-8")); } catch { cur = ""; }
      items.push({ area: "knowledge", ref: op.path, expectHash: op.afterHash, currentHash: cur });
    }
    const pf = rollbackPreflight(items);
    if (!pf.ok) throw new Error("已有多处内容在后续发生了变化，回滚已停止（" + pf.drifted.map((d) => d.area + ":" + d.ref).slice(0, 3).join("、") + "…）");
    // 逆序执行：知识→技能→记忆
    for (const op of [...m.rollback.knowledge].reverse()) await undoKnowledgeOp(op, m.summary.id);
    for (const op of [...m.rollback.skills].reverse()) undoSkillOp(op, m.summary.id);
    for (const op of [...m.rollback.memories].reverse()) undoMemoryOp(op);
    // 记录收口
    m.summary.status = "rolled_back";
    m.summary.canRollback = false;
    m.summary.rolledBackAt = now();
    let report = "";
    try { report = readFileSync(join(runsDir(), m.summary.id, "REPORT.md"), "utf-8"); } catch { /* 缺报告容错 */ }
    writeFileSync(join(runsDir(), m.summary.id, "REPORT.md"), appendRollbackSection(report || "# 学习迭代", now()), "utf-8");
    writeJson(join(runsDir(), m.summary.id, "manifest.json"), m);
    auditWrite?.("learning.rollback", m.summary.id, `撤销记忆 ${m.rollback.memories.length}／技能 ${m.rollback.skills.length}／知识 ${m.rollback.knowledge.length}`);
    setMessage("cancelled", "最近一轮已整体回滚");
    return m.summary;
  }

  // ═══ 调度（A2-A8/K1/K2）═══
  let ticking = false;
  async function tick({ manual = false } = {}) {
    if (ticking) {
      if (manual) queuedManual = true; // 运行中来手动→排队
      return { ok: false, reason: "running" };
    }
    ticking = true;
    try {
      const settings = normalizeLearningSettings(loadSettings());
      const state = readState();
      const today = localDayOf(now());
      if (!settings.enabled) {
        queuedManual = false; cancelRequested = false; // A8 清排队置取消
        setMessage("disabled");
        return { ok: true, reason: "disabled" };
      }
      const doneToday = state.lastLocalDay === today && Boolean(state.lastSuccessfulAt);
      if (doneToday) {
        if (queuedManual) { queuedManual = false; } // A4 额度用后清排队，不泄漏到次日自动 tick
        setMessage("daily_quota");
        writeState({ ...state, lastCheckedAt: now() });
        return { ok: true, reason: "done-today" };
      }
      if (state.pendingRunId) {
        // K10 跨重启续跑：pendingRunId 在，直接续（绕过闲门重采集排队——续跑本身是恢复动作）
        running = true;
        try { return await runOnce(manual); } finally { running = false; }
      }
      if (!manual && !backoffDue(state, now())) return { ok: true, reason: "backoff" }; // A7
      // A6 忙门四连
      const threads = (() => { try { return listThreads() ?? []; } catch { return null; } })();
      const runningThreads = (threads ?? []).filter((t) => t.phase === "running")
        .map((t) => ({ id: t.id, isLearningThread: t.workspaceKey === "learning://juscite-learning" }));
      const gate = evaluateBusyGate({
        idleSeconds: null, // 桥面无 OS 空闲源（记差异，见文件头）
        idleMinutes: settings.idleMinutes,
        externalBusy: false, // 定时任务运行态=运行中对话，已并入 runningThreads（对拍行 5 口径）
        complianceBusy: false, // 合规任务面未建（记差异）
        runningThreads,
        threadsUnavailable: threads === null,
      }, manual);
      if (gate.busy && !manual) {
        setMessage("waiting_idle"); // K2 忙门未到排队保留
        return { ok: true, reason: "busy", gateReasons: gate.reasons };
      }
      if (gate.busy && manual) { queuedManual = true; setMessage("waiting_idle"); return { ok: true, reason: "queued" }; }
      if (manual) queuedManual = false;
      running = true;
      try { return await runOnce(manual); } finally { running = false; }
    } finally {
      ticking = false;
    }
  }

  function setMessage(key, text) {
    lastMessageKey = key;
    lastMessage = text ?? STAGE_MESSAGES[key] ?? STAGE_MESSAGES.watching;
  }

  // ═══ 状态载荷（B1-B4/J2/J3）═══
  function status() {
    const settings = normalizeLearningSettings(loadSettings());
    const state = readState();
    const records = listRecords();
    const latest = records[0] ?? null;
    const now0 = now();
    const today = localDayOf(now0);
    const doneToday = state.lastLocalDay === today && Boolean(state.lastSuccessfulAt);
    const derived = deriveRunStatus({ enabled: settings.enabled, running, queued: queuedManual, latest });
    const baselineProgress = state.baselineComplete ? 100
      : (state.baselineProcessed + state.baselineRemaining) > 0
        ? Math.round((state.baselineProcessed / (state.baselineProcessed + state.baselineRemaining)) * 100)
        : 0;
    return {
      enabled: settings.enabled,
      eligibleToday: todayEligibilityOf({ enabled: settings.enabled, queued: queuedManual, doneToday }),
      queued: queuedManual,
      running,
      status: derived,
      message: lastMessage,
      lastSuccessfulAt: state.lastSuccessfulAt,
      lastCheckedAt: state.lastCheckedAt,
      nextEligibleAt: nextEligibleAtOf(state, now0),
      baselineComplete: state.baselineComplete,
      baselineProgress,
      pendingSourceCount,
      activeRunId: running ? activeRunId : null,
      latest,
      idleMinutes: settings.idleMinutes,
      keepRunningInTray: settings.keepRunningInTray,
    };
  }
  const disabledFallback = () => ({
    enabled: false, eligibleToday: "disabled", queued: false, running: false, status: "disabled",
    message: STAGE_MESSAGES.disabled, lastSuccessfulAt: null, lastCheckedAt: null, nextEligibleAt: null,
    baselineComplete: false, baselineProgress: 0, pendingSourceCount: 0, activeRunId: null, latest: null,
    idleMinutes: 15, keepRunningInTray: true,
  });

  // I1：对话回合链记忆注入
  function injectionPlan(turnText) {
    return retrieveMemoriesForInjection(memoriesRead(), turnText, { budgetChars: 2000 });
  }
  function injectionAllowed(threadTitle) { return shouldInjectMemories(threadTitle); }

  // ═══ 启动 ═══
  mkdirSync(root, { recursive: true });
  let timer = null;
  function start() {
    log(`[learning] runtime started (root=${root}, poll=${pollMs}ms)`);
    void tick().catch((e) => log(`[learning] boot tick: ${e?.message ?? e}`)); // A2 启动即 sync
    timer = setInterval(() => { void tick().catch((e) => log(`[learning] tick: ${e?.message ?? e}`)); }, pollMs);
    timer.unref?.(); // A2 定时器不阻退出
    return runtime;
  }
  function stop() { if (timer) { clearInterval(timer); timer = null; } } // A8 stop 清定时器

  const runtime = {
    start, stop, tick, status, disabledFallback,
    queue: async () => {
      const settings = normalizeLearningSettings(loadSettings());
      if (!settings.enabled) { setMessage("disabled"); return { ok: false, reason: "disabled", message: STAGE_MESSAGES.disabled }; }
      const state = readState();
      if (state.lastLocalDay === localDayOf(now()) && state.lastSuccessfulAt) {
        setMessage("daily_quota");
        return { ok: false, reason: "done-today", message: STAGE_MESSAGES.daily_quota };
      }
      queuedManual = true;
      setMessage("preparing");
      void tick({ manual: true }).catch((e) => log(`[learning] manual tick: ${e?.message ?? e}`));
      return { ok: true };
    },
    cancel: () => {
      if (running) { cancelRequested = true; setMessage("cancelled", "将在当前阶段结束后停止"); return { ok: true, phase: "running", message: "将在当前阶段结束后停止" }; }
      if (queuedManual) { queuedManual = false; setMessage("cancel_pending"); return { ok: true, phase: "queued", message: STAGE_MESSAGES.cancel_pending }; }
      return { ok: true, phase: "none", message: "当前没有进行中的学习" };
    },
    rollback: rollbackRun,
    listRecords, readRecordDetail, readRunManifest,
    injectionPlan, injectionAllowed,
    memoriesRead, // 记忆面最小集暴露（诊断/测试）
    setStateMessage: setMessage,
  };
  return runtime;
}

// 注入用路径助手（模型路径 → 归一相对路径；与内核 normalizeKnowledgePath 同规）
import { normalizeKnowledgePath } from "../../packages/juscite-legal/src/kernel/learningModel.ts";
function normalizeKnowledgePathRel(p) {
  const v = normalizeKnowledgePath(String(p ?? ""));
  if (!v.ok) throw new Error(v.reason);
  return v.relPath;
}
function writeJson(p, v) { mkdirSync(dirname(p), { recursive: true }); writeFileSync(p, JSON.stringify(v, null, 2), "utf-8"); }

// 目录复制（readdir+copyFile 等价 cpSync -r；本机 node 22.23.1 cpSync 原生崩溃规避，2026-10-27 实测）
function copyDirSync(src, dest) {
  mkdirSync(dest, { recursive: true });
  for (const e of readdirSync(src, { withFileTypes: true })) {
    const s2 = join(src, e.name);
    const d2 = join(dest, e.name);
    if (e.isDirectory()) copyDirSync(s2, d2);
    else if (e.isFile()) copyFileSync(s2, d2);
  }
}
