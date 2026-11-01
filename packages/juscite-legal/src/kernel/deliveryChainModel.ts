// 【功能 #7 证据目录生成·全量面】交付链内核（RE-7 §3 流程"交付"段；对拍 22/23/23a/23b 的数据面）。
// 纯函数、零 IO。四件：
//   D1 消息内文件路径提取——扩展名以字母开头（拒"2025.03.07"日期假扩展名）、拒裸域名 token；
//   D3 交付清单双层过滤——内部过程文件硬过滤（assistant/工具事件两路径同裁）+ 草稿/脚本启发式
//      过滤（assistant 显式路径带"全 draft-like 回退"，工具事件路径无回退）；
//   D5 版本族去重——版本后缀剥除后按 stem::extension 折叠，同族后来者顶替并移至最新位；
//      跨扩展名不折叠；用户附件恒在列表最前；
//   D4 交付短路链两层——docx 唯一产物免复述轮（确定性落点话术）；"文件在哪"类追问复用最近
//      成功 docx 交付路径直接作答（≤80 字/位置词/排除授权语/仅 docx/stepIndex>0 闸）。
// 文案全部自写（表达隔离：等量语义≠抄竞品话术）。

// ── D1：消息内文件路径提取 ─────────────────────────────────────────
/** 无路径分隔符的裸 token 只在扩展名落入交付件白名单时才算文件（裸域名 example.com 由此拒绝）。 */
const BARE_TOKEN_DELIVERY_EXTENSIONS = new Set([
  "docx", "pdf", "xlsx", "xls", "txt", "md", "csv", "json", "png", "jpg", "jpeg",
  "webp", "gif", "bmp", "doc", "rtf", "zip", "pptx", "html",
]);
/** 候选 token：连续的非空白且非中日文标点片段（路径可含 /\:. 与中文文件名）。 */
const TOKEN_SPLIT = /[\s\u3000\u3001\u3002\uff0c\uff1a\uff1b\uff08\uff09\u3010\u3011\u201c\u201d\u2018\u2019"'`<>|]+/;
/** 扩展名形状：以字母开头，字母数字组成，长度 1-10（"03.07"之 类日期段不以字母开头即出局）。 */
const EXTENSION_SHAPE = /^[A-Za-z][A-Za-z0-9]{0,9}$/;

function basenameOf(token: string): string {
  const parts = token.split(/[\\/]/);
  return parts[parts.length - 1] || token;
}

function extensionOf(basename: string): string | null {
  const dot = basename.lastIndexOf(".");
  if (dot < 0 || dot === basename.length - 1) return null;
  const ext = basename.slice(dot + 1);
  return EXTENSION_SHAPE.test(ext) ? ext.toLowerCase() : null;
}

/** 单 token 是否构成交付文件路径主张（扩展名字母开头；裸 token 需白名单扩展名以拒裸域名）。 */
export function isDeliveryPathToken(token: string): boolean {
  const t = token.replace(/^[（(]+/, "").replace(/[)）.,;，。；]+$/, ""); // 剥首尾配对标点
  if (!t || !t.includes(".")) return false;
  const base = basenameOf(t);
  const ext = extensionOf(base);
  if (!ext) return false; // 日期假扩展名（2025.03.07）与数字扩展名在此出局
  const hasSeparator = /[\\/]/.test(t);
  if (hasSeparator) return true; // 带路径分隔符：目录内的文件名，按文件计
  if (/^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(t)) return true; // URL 里的文件路径
  return BARE_TOKEN_DELIVERY_EXTENSIONS.has(ext); // 裸 token：仅白名单扩展名（example.com 出局）
}

/** 从消息文本提取交付文件路径（去重保序）。 */
export function extractDeliveredPaths(text: string): string[] {
  const out: string[] = [];
  for (const raw of String(text ?? "").split(TOKEN_SPLIT)) {
    const token = raw.trim();
    if (!token) continue;
    if (isDeliveryPathToken(token) && !out.includes(token)) out.push(token);
  }
  return out;
}

// ── D3：双层过滤 ───────────────────────────────────────────────────
/** 内部过程文件（硬过滤，两路径同裁）：批量命令暂存/事件流/临时与抽取目录族的任何路径都不进交付清单。 */
const INTERNAL_PROCESS_BASENAMES = new Set(["batch_cmds.json", "events.jsonl", "scratch.log", "tmp.json"]);
const INTERNAL_PROCESS_SEGMENTS = /^(scratch|tmp|temp|extract_|parse_|__pycache__|node_modules$)/;

export function isInternalProcessFile(path: string): boolean {
  const base = basenameOf(String(path ?? "")).toLowerCase();
  if (INTERNAL_PROCESS_BASENAMES.has(base)) return true;
  return path.split(/[\\/]/).some((seg) => seg && INTERNAL_PROCESS_SEGMENTS.test(seg.toLowerCase()));
}

/** 草稿/工作稿名字模式 + 助手脚本前缀（启发式过滤）。 */
const DRAFT_LIKE_NAME = /(draft|working|wip|草稿|初稿|中间稿|底稿)/i;
const HELPER_SCRIPT_PREFIX = /^(export|generate|render|convert|extract|parse|merge|build|fix)[-_]/i;
const SCRIPT_EXTENSIONS = new Set(["py", "js", "mjs", "cjs", "ts", "mts", "cts", "sh", "ps1", "bat"]);

export function isDraftLikeName(path: string): boolean {
  const base = basenameOf(String(path ?? ""));
  const ext = extensionOf(base) ?? "";
  if (SCRIPT_EXTENSIONS.has(ext) && HELPER_SCRIPT_PREFIX.test(base)) return true; // merge_evidence.py 之 类
  return DRAFT_LIKE_NAME.test(base);
}

export type DeliverySource = "assistant" | "tool";

export interface DeliveryCandidate {
  path: string;
  source: DeliverySource;
}

/**
 * 交付清单过滤：①硬过滤内部过程文件（两路径同裁；用户同前缀真文件不经此面——附件上传通道
 * 天然分离，本函数只裁 agent 交付候选）；②草稿/脚本启发式——assistant 显式路径先剔除，
 * 仅当全部候选皆 draft-like 时整体保留（"用户要的就是脚本/草稿"）；工具事件路径无回退。
 */
export function filterDeliveries(candidates: DeliveryCandidate[]): DeliveryCandidate[] {
  const clean = candidates.filter((c) => !isInternalProcessFile(c.path));
  const assistant = clean.filter((c) => c.source === "assistant");
  const tool = clean.filter((c) => c.source === "tool");
  const keptTool = tool.filter((c) => !isDraftLikeName(c.path)); // 工具路径：无回退
  if (assistant.length === 0) return keptTool;
  const keptAssistant = assistant.filter((c) => !isDraftLikeName(c.path));
  const finalAssistant = keptAssistant.length > 0 ? keptAssistant : assistant; // 全 draft 回退：整体保留
  return [...finalAssistant, ...keptTool];
}

// ── D5：版本族去重 ─────────────────────────────────────────────────
/** 版本后缀族：（v2)/v2/rev2/final/终稿/定稿/copy/副本/（1)/(1)，可叠剥；裸 v2 直接缀尾也剥。 */
const VERSION_SUFFIX = /(?:[（(]\s*v\d+\s*[)）]|v\d+$|[-_. ]?rev\d+$|[-_. ]?final$|终稿$|定稿$|[-_. ]?copy$|副本$|[（(]\s*\d+\s*[)）])\s*$/i;

/** 剥版本后缀后的 stem（无后缀原样返回）。 */
export function stripVersionSuffix(stem: string): string {
  let s = String(stem ?? "").trim();
  for (let i = 0; i < 5; i++) {
    const next = s.replace(VERSION_SUFFIX, "").trim();
    if (next === s || !next) break;
    s = next;
  }
  return s;
}

export interface DeliverableItem {
  filename: string;
  producer: "user" | "agent";
}

/** 族键=剥版本后缀的 stem::extension（跨扩展名不折叠：docx 与 pdf 是两件交付）。 */
export function deliveryFamilyKey(filename: string): string {
  const base = basenameOf(filename);
  const dot = base.lastIndexOf(".");
  const stem = dot > 0 ? base.slice(0, dot) : base;
  const ext = dot > 0 ? base.slice(dot + 1).toLowerCase() : "";
  return `${stripVersionSuffix(stem)}::${ext}`;
}

/**
 * 版本族去重：用户件恒在前（稳定序不折叠）；agent 件同族后来者顶替并落位在最新一次出现处。
 */
export function dedupeVersionFamily<T extends DeliverableItem>(items: T[]): T[] {
  const user = items.filter((i) => i.producer !== "agent");
  const agent = items.filter((i) => i.producer === "agent");
  const lastIndexByFamily = new Map<string, number>();
  agent.forEach((item, idx) => lastIndexByFamily.set(deliveryFamilyKey(item.filename), idx));
  const kept: T[] = [];
  agent.forEach((item, idx) => {
    const key = deliveryFamilyKey(item.filename);
    if (lastIndexByFamily.get(key) === idx) kept.push(item); // 同族只留最后一份（后来者顶替）
  });
  return [...user, ...kept];
}

// ── D4：交付短路链两层 ─────────────────────────────────────────────
export type RequestedArtifactKind = "docx" | "xlsx" | "pdf" | "pptx";

export interface WordDeliveryRecord {
  path: string;
  status: "ok" | "error";
  /** docx=交付；inspect/profiles=查看类操作，不算交付（复用面只认交付）。 */
  kind: "docx" | "inspect" | "profiles" | "other";
}

/**
 * D4① docx 唯一产物免复述轮：本回合恰好只请求 docx 一个产物且有成功交付（非 inspect/profiles）
 * → 返回确定性落点话术（本地直出，不经模型）；否则 null。
 */
export function completedWordDeliveryMessage(input: {
  requestedArtifacts: Array<{ kind: RequestedArtifactKind }>;
  deliveries: WordDeliveryRecord[];
}): string | null {
  const req = input.requestedArtifacts ?? [];
  if (req.length !== 1 || req[0].kind !== "docx") return null;
  const delivered = (input.deliveries ?? []).filter((d) => d.kind === "docx" && d.status === "ok");
  if (delivered.length === 0) return null;
  return `已生成 Word 文档：\n\n${delivered[delivered.length - 1].path}`;
}

/** 位置追问词族与授权语族（追问触发面；授权语=用户放弃指定位置，不触发复用）。 */
const LOCATION_QUESTION_WORDS = /(文件在哪|放在哪|存到哪|在哪取|取哪|找到吗|在哪里|去了哪)/;
const LOCATION_AUTHORIZATION_WORDS = /(放哪都行|随便|都可以|你定|你来定|无所谓)/;

/**
 * D4② "文件在哪"追问复用：消息 ≤80 字、含位置追问词、非授权语、线程已有交付（stepIndex>0 闸
 * 由调用方传入 allowReuse），扫历史取最近一次成功 docx 交付 → 直接作答文本；否则 null。
 */
export function deliveredWordLocationAnswer(input: {
  message: string;
  history: WordDeliveryRecord[]; // 旧→新
  allowReuse: boolean; // stepIndex>0 闸（首轮无交付可复用，恒 false）
}): string | null {
  const msg = String(input.message ?? "").trim();
  if (!input.allowReuse) return null;
  if ([...msg].length > 80) return null; // 字数口径=码点
  if (!LOCATION_QUESTION_WORDS.test(msg)) return null;
  if (LOCATION_AUTHORIZATION_WORDS.test(msg)) return null;
  for (let i = input.history.length - 1; i >= 0; i--) {
    const d = input.history[i];
    if (d.kind === "docx" && d.status === "ok") return `刚生成的 Word 文档在这里：\n${d.path}`;
  }
  return null;
}

/** 用户消息的产物请求档探测（D4① 的请求面）：按扩展名/格式词识别，只认闭集四类。 */
export function requestedArtifactKinds(text: string): RequestedArtifactKind[] {
  const lower = String(text ?? "").toLowerCase();
  const kinds: RequestedArtifactKind[] = [];
  const push = (k: RequestedArtifactKind) => {
    if (!kinds.includes(k)) kinds.push(k);
  };
  if (/\.docx|\bdocx\b|word\s*(文档|文件)|word文档/.test(lower)) push("docx");
  if (/\.xlsx|\.xls\b|\bxlsx\b|excel|表格文件/.test(lower)) push("xlsx");
  if (/\.pdf\b|\bpdf\b/.test(lower)) push("pdf");
  if (/\.pptx|\bpptx\b|幻灯片/.test(lower)) push("pptx");
  return kinds;
}
