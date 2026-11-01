// 【功能 #6 材料上传解析】桥附件库 HTTP 客户端（RE-6 §3 /api/attachments* 消费面）。
// 对话输入框附件区与对话文件面板共用；错误一律映射为稳定自写文案（对拍 38/46 语义：
// 不外泄用户内容、状态码语义等量 400/401/403/404/413）。纯函数（类型判定/粘贴计划）独立
// 导出供 Node 单测。

export type MaterialAttachmentKind = "docx" | "pdf" | "image" | "audio" | "video" | "text" | "other";

export interface BridgeAttachmentItem {
  id: string;
  filename: string;
  mimeType: string;
  byteSize: number;
  createdAt: string;
  /** 对话文件面板分组（用户文件/Agent 产出）；旧桥缺列时按 user。 */
  producer: "user" | "agent";
}

export class BridgeMaterialHttpError extends Error {
  readonly status: number;
  readonly code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf(".");
  return dot >= 0 ? filename.slice(dot + 1).toLowerCase() : "";
}

/** 附件类型判定（面板徽章/预览路由/分组图标共用一份口径）。 */
export function attachmentKindOf(filename: string, mimeType?: string): MaterialAttachmentKind {
  const mime = (mimeType ?? "").split(";")[0]?.trim().toLowerCase() ?? "";
  const ext = extensionOf(filename);
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("audio/")) return "audio";
  if (mime.startsWith("video/")) return "video";
  if (mime === "application/pdf" || ext === "pdf") return "pdf";
  if (ext === "docx" || mime.includes("wordprocessingml")) return "docx";
  const imageExts = new Set(["png", "jpg", "jpeg", "webp", "gif", "bmp"]);
  if (imageExts.has(ext)) return "image";
  const audioExts = new Set(["mp3", "wav", "m4a", "aac", "ogg", "flac"]);
  if (audioExts.has(ext)) return "audio";
  const videoExts = new Set(["mp4", "mov", "webm", "mkv", "avi"]);
  if (videoExts.has(ext)) return "video";
  const textExts = new Set(["txt", "md", "markdown", "csv", "json", "log", "xml", "html", "yml", "yaml"]);
  if (mime.startsWith("text/") || textExts.has(ext)) return "text";
  return "other";
}

const KIND_LABELS: Record<MaterialAttachmentKind, string> = {
  docx: "文档",
  pdf: "PDF",
  image: "图片",
  audio: "音频",
  video: "视频",
  text: "文本",
  other: "文件",
};

export function attachmentKindLabel(kind: MaterialAttachmentKind): string {
  return KIND_LABELS[kind];
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function decodeBase64ToBytes(dataBase64: string): Uint8Array {
  const binary = atob(dataBase64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function errorOf(response: Response): Promise<BridgeMaterialHttpError> {
  const fallback = (status: number): string =>
    ({
      400: "附件内容或格式未通过校验",
      401: "缺少有效的本地访问凭据",
      403: "无权读取该附件",
      404: "附件不存在",
      413: "附件超过 100MB 上传上限",
    })[status] ?? "附件服务暂不可用";
  let code = "HTTP_ERROR";
  let message = fallback(response.status);
  try {
    const body = (await response.json()) as { error?: { code?: string; message?: string } };
    code = body?.error?.code ?? code;
    message = body?.error?.message ?? message;
  } catch {
    // 非 JSON 错误体保持稳定文案
  }
  return new BridgeMaterialHttpError(response.status, code, message);
}

export interface UploadBridgeAttachmentParams {
  bytes: Uint8Array;
  filename: string;
  mimeType: string;
  threadIds?: string[];
  caseIds?: string[];
  /** 对话文件面板分组（用户文件/Agent 产出）；缺省 user。 */
  producer?: "user" | "agent";
}

export interface UploadBridgeAttachmentResult {
  attachmentId: string;
  deduplicated: boolean;
  byteSize: number;
  filename: string;
  mimeType: string;
}

export async function uploadBridgeMaterialAttachment(
  params: UploadBridgeAttachmentParams,
): Promise<UploadBridgeAttachmentResult> {
  const response = await fetch("/api/attachments", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      dataBase64: bytesToBase64(params.bytes),
      filename: params.filename,
      mimeType: params.mimeType,
      ...(params.threadIds?.length ? { threadIds: params.threadIds } : {}),
      ...(params.caseIds?.length ? { caseIds: params.caseIds } : {}),
      ...(params.producer ? { producer: params.producer } : {}),
    }),
  });
  if (!response.ok) throw await errorOf(response);
  return (await response.json()) as UploadBridgeAttachmentResult;
}

export async function listBridgeMaterialAttachments(scope: { threadId?: string | null; caseId?: string | null }): Promise<BridgeAttachmentItem[]> {
  const qs = new URLSearchParams();
  if (scope.threadId) qs.set("threadId", scope.threadId);
  if (scope.caseId) qs.set("caseId", scope.caseId);
  const response = await fetch(`/api/attachments${qs.size ? `?${qs.toString()}` : ""}`, { cache: "no-store" });
  if (!response.ok) throw await errorOf(response);
  const body = (await response.json()) as { items?: Array<Partial<BridgeAttachmentItem>> };
  return (body.items ?? []).map((item) => ({
    id: String(item.id ?? ""),
    filename: String(item.filename ?? ""),
    mimeType: String(item.mimeType ?? ""),
    byteSize: Number(item.byteSize ?? 0),
    createdAt: String(item.createdAt ?? ""),
    producer: item.producer === "agent" ? "agent" : "user",
  }));
}

export interface BridgeAttachmentContent {
  bytes: Uint8Array;
  filename: string;
  mimeType: string;
  byteSize: number;
}

/** 作用域授权读取（无凭据 401 / 作用域不匹配 403 由桥面裁定，此处映射稳定文案）。 */
export async function fetchBridgeAttachmentBytes(
  attachmentId: string,
  scope: { threadId?: string | null; caseId?: string | null },
): Promise<BridgeAttachmentContent> {
  const qs = new URLSearchParams();
  if (scope.threadId) qs.set("threadId", scope.threadId);
  if (scope.caseId) qs.set("caseId", scope.caseId);
  const response = await fetch(`/api/attachments/${encodeURIComponent(attachmentId)}/content${qs.size ? `?${qs.toString()}` : ""}`, { cache: "no-store" });
  if (!response.ok) throw await errorOf(response);
  const body = (await response.json()) as { dataBase64?: string; filename?: string; mimeType?: string; byteSize?: number };
  if (!body.dataBase64) throw new BridgeMaterialHttpError(0, "EMPTY_CONTENT", "附件内容为空");
  return {
    bytes: decodeBase64ToBytes(body.dataBase64),
    filename: String(body.filename ?? attachmentId),
    mimeType: String(body.mimeType ?? "application/octet-stream"),
    byteSize: Number(body.byteSize ?? 0),
  };
}

// ── 粘贴决策（对拍 3/4）：纯函数，供 Node 单测与组件 onPaste 共用 ──
/** 长文本粘贴转附件阈值（对拍 4：≥200 字符）。 */
export const MATERIAL_PASTE_TEXT_MIN_CHARS = 200;

export interface PasteIngestInput {
  files: Array<{ name: string; type: string }>;
  text: string;
}

export interface PasteIngestPlan {
  kind: "files" | "long-text" | "none";
  /** kind=long-text 时随行的正文（转 粘贴内容.txt 附件）。 */
  text: string;
  /** 富文本粘贴时长文本优先、内嵌图片整批丢弃（对拍 4 裁决），此处记录被丢图片数供提示。 */
  droppedFileCount: number;
}

/**
 * 粘贴分流：图片/文件直接上传（对拍 3）；≥200 字纯文本转「粘贴内容.txt」（对拍 4）；
 * 长正文与内嵌图片并存时长文本优先、文件整批丢弃（对拍 4 富文本裁决）。短文本不收（输入框职责）。
 */
export function planPasteIngest(input: PasteIngestInput): PasteIngestPlan {
  const hasFiles = input.files.length > 0;
  const textLen = [...input.text].length; // 码点口径（§2 图例：BMP 中文两口径等值）
  if (textLen >= MATERIAL_PASTE_TEXT_MIN_CHARS) {
    return { kind: "long-text", text: input.text, droppedFileCount: input.files.length };
  }
  if (hasFiles) {
    return { kind: "files", text: "", droppedFileCount: 0 };
  }
  return { kind: "none", text: "", droppedFileCount: 0 };
}

// ── 目录拖拽收集（对拍 30 前半/§3 批量：目录拖拽仅收白名单扩展名）──
/**
 * 目录拖拽白名单（§3 批量钉定口径：对齐竞品 batch 八类、v1 加 docx/txt/md，投影到本版收单白名单——
 * tiff/tif 未入本版收单、doc 走 fail-closed「请转存 docx」提示，均不入目录拖拽自动收集；
 * csv/json/doc 等仍可手动选择上传，由桥 intake 决定收拒并明示）。
 */
const DIRECTORY_DROP_EXTENSIONS = new Set(["pdf", "docx", "txt", "md", "png", "jpg", "jpeg", "webp", "gif", "bmp"]);

/** 文件名是否落入目录拖拽白名单（纯函数，Node 可测）。 */
export function isIngestableMaterialName(filename: string): boolean {
  const dot = filename.lastIndexOf(".");
  if (dot < 0) return false;
  return DIRECTORY_DROP_EXTENSIONS.has(filename.slice(dot + 1).toLowerCase());
}

/** 目录项最小结构（兼容 FileSystemEntry 回调形态，便于 Node 造树单测）。 */
export interface FsEntryLike {
  readonly isFile: boolean;
  readonly isDirectory: boolean;
  readonly name: string;
  file?: (success: (file: File) => void, error?: (e: unknown) => void) => void;
  createReader?: () => {
    readEntries: (success: (entries: FsEntryLike[]) => void, error?: (e: unknown) => void) => void;
  };
}

function entryToFile(entry: FsEntryLike): Promise<File | null> {
  return new Promise((resolve) => {
    if (!entry.isFile || !entry.file) {
      resolve(null);
      return;
    }
    entry.file((file) => resolve(file), () => resolve(null));
  });
}

function readEntryDirectory(entry: FsEntryLike): Promise<FsEntryLike[]> {
  return new Promise((resolve) => {
    if (!entry.isDirectory || !entry.createReader) {
      resolve([]);
      return;
    }
    const reader = entry.createReader();
    const all: FsEntryLike[] = [];
    const step = () => {
      // readEntries 每批有上限，须读到空批为止
      reader.readEntries(
        (batch) => {
          if (!batch.length) {
            resolve(all);
            return;
          }
          all.push(...batch);
          step();
        },
        () => resolve(all),
      );
    };
    step();
  });
}

/** 入口树遍历：只收白名单扩展名文件（迭代队列，深目录不递归爆栈；单件读败跳过不中断——对拍 43 同源）。 */
export async function collectIngestableEntries(entries: FsEntryLike[]): Promise<File[]> {
  const out: File[] = [];
  const queue = [...entries];
  while (queue.length) {
    const entry = queue.shift() as FsEntryLike;
    if (entry.isFile) {
      if (!isIngestableMaterialName(entry.name)) continue;
      const file = await entryToFile(entry);
      if (file) out.push(file);
    } else if (entry.isDirectory) {
      queue.push(...(await readEntryDirectory(entry)));
    }
  }
  return out;
}

/**
 * drop 收集：含目录时走入口树+白名单过滤（对拍 30）；纯文件拖拽照旧收顶层
 * （未知扩展名仍由桥 intake 拒收明示，不静默吞——对拍 27 语义）。webkitGetAsEntry 须在
 * await 前同步取齐（DataTransferItem 跨 await 失效）；无 entries 能力时退回 files 照旧。
 */
export async function collectDroppedFiles(dataTransfer: DataTransfer): Promise<File[]> {
  const entries = Array.from(dataTransfer.items ?? [])
    .map((item) => (typeof item.webkitGetAsEntry === "function" ? (item.webkitGetAsEntry() as unknown as FsEntryLike | null) : null))
    .filter((entry): entry is FsEntryLike => Boolean(entry));
  if (entries.some((entry) => entry.isDirectory)) {
    return collectIngestableEntries(entries);
  }
  return Array.from(dataTransfer.files ?? []);
}
