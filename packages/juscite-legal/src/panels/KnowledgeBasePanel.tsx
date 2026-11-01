// 【步骤4·#20 所内知识问答】知识库工作区（RE-20 §3 UI 结构；三栏：文集树侧栏｜文件表｜问答侧栏）。
// 数据经桥 kb* 桥面（kbTree/kbImport/kbSync/kbAsk/kbThreadState…，走 M4 回合链流式，轮询投影）；
// 文案全部自写（表达隔离）；行为锚点在注释按对拍行号标注（B01-B50）。检索/提示词/同步全在桥侧
// kb_service.mjs（零 embedding 纯本地稀疏，B51）；本面板只做编排与呈现。
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Eye, FolderOpen, FolderPlus, MessageSquare, MessageSquareOff, PanelRightClose, PanelRightOpen,
  Pencil, RotateCw, Sparkles, Trash2, Upload, X,
} from "lucide-react";
import { useServices } from "../ui-kit.js";
import { PdfPreviewContent } from "../ui-kit.js";

// ── 类型（桥面协议形状）──
interface KbFolder { path: string; name: string; updatedAt: number }
interface KbDoc {
  relPath: string; title: string; ext: string; sizeBytes: number; mtimeMs: number;
  category: string | null; tags: string[]; keywords: string[]; indexed: boolean;
}
interface KbTree { root: string; folders: KbFolder[]; docs: KbDoc[]; counts: { files: number; topLevel: number } }
interface KbSource { n: number; title: string; path: string; relevance: number }
interface KbQuote { text: string; source: string; page?: number | null }
interface KbMsg {
  rowId: number; kind: "userInput" | "assistantText"; state: string;
  text: string; reasoning?: string; createdAt: number; kbQuote?: KbQuote | null;
}
interface KbModelSel { providerId: string; modelId: string }
interface KbThreadState {
  threadId: string; title: string; phase: string; busy: boolean;
  lastError: { message: string } | null;
  rows: KbMsg[]; sources: KbSource[];
  kbCtx: { kind: string; folderPath: string | null; fileName: string | null; filePath: string | null } | null;
}
interface KbModelChoice { value: string; label: string; model: KbModelSel | null } // model=null=跟随对话
interface KbThreadRec {
  threadId: string; title: string; phase: string; updatedAt: number; createdAt: number;
  kbCtx: { kind: string; folderPath: string | null; fileName: string | null; filePath: string | null } | null;
}
type QaScope = { kind: "global" } | { kind: "folder"; folderPath: string; folderName: string } | { kind: "file"; fileName: string; filePath: string; fileSize?: string };

// ── B05 类型徽章色卡（20 扩展名键，自绘；其余灰=大写扩展名；文件夹独立蓝）──
const EXT_BADGES: Record<string, { label: string; cls: string }> = {
  pdf: { label: "PDF", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
  doc: { label: "DOC", cls: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300" },
  docx: { label: "DOC", cls: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300" },
  ppt: { label: "PPT", cls: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300" },
  pptx: { label: "PPT", cls: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300" },
  xls: { label: "XLS", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  xlsx: { label: "XLS", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  csv: { label: "CSV", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  txt: { label: "TXT", cls: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300" },
  md: { label: "MD", cls: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300" },
  markdown: { label: "MD", cls: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300" },
  mp3: { label: "音频", cls: "bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300" },
  wav: { label: "音频", cls: "bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300" },
  m4a: { label: "音频", cls: "bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300" },
  aac: { label: "音频", cls: "bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300" },
  flac: { label: "音频", cls: "bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300" },
  ogg: { label: "音频", cls: "bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300" },
  zip: { label: "压缩", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  rar: { label: "压缩", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  "7z": { label: "压缩", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
};
function extBadge(ext: string) {
  const key = ext.replace(/^\./, "").toLowerCase();
  return EXT_BADGES[key] ?? { label: key.slice(0, 5).toUpperCase() || "文件", cls: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300" };
}
const PREVIEWABLE_EXTS = new Set([".txt", ".md", ".markdown", ".csv", ".tsv", ".log", ".json", ".xml", ".html", ".htm", ".srt", ".docx", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"]);

function fmtSize(n: number): string {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " MB";
  return (n / 1024 / 1024 / 1024).toFixed(1) + " GB";
}
function fmtTime(ms: number): string {
  if (!ms) return "—";
  const d = new Date(ms);
  const y = d.getFullYear();
  const nowY = new Date().getFullYear();
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const md = `${d.getMonth() + 1}-${d.getDate()} ${hm}`;
  return y === nowY ? md : `${y}-${md}`;
}
function bytesToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
// 深层文件夹枚举（B11 拖拽含文件夹递归，保留相对路径）
interface PickedFile { relPath: string; file: File }
async function walkEntry(entry: FileSystemEntry, prefix: string, out: PickedFile[]): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File | null>((res) => (entry as FileSystemFileEntry).file(res, () => res(null)));
    if (file) out.push({ relPath: prefix + file.name, file });
  } else if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    const batch = await new Promise<FileSystemEntry[]>((res) => reader.readEntries((es) => res(es), () => res([])));
    for (const e of batch) await walkEntry(e, prefix + entry.name + "/", out);
  }
}

// ── B42 思考过程：行内 reasoning 字段优先；正文遗留 <think>/<details> 块确定性提取 ──
function splitReasoning(text: string, reasoning?: string): { answer: string; reasoning: string } {
  let answer = text;
  let out = (reasoning ?? "").trim();
  const fence = answer.match(/^<[tT]hink>([\s\S]*?)<\/[tT]hink>\s*/u) ?? answer.match(/^<details[^>]*type="reasoning"[^>]*>([\s\S]*?)<\/details>\s*/iu);
  if (!fence || !fence[0] || !fence[1]) return { answer: answer.trim(), reasoning: out };
  out = out ? out + "\n\n" + fence[1].trim() : fence[1].trim();
  answer = answer.slice(fence[0].length);
  return { answer: answer.trim(), reasoning: out };
}

// ── [来源N] → 可点锚点（B40/B41；映射=最近一轮提问的来源）──
function AnswerBody({ text, onSource }: { text: string; onSource: (n: number) => void }) {
  const parts = useMemo(() => text.split(/(\[来源\d+\])/g), [text]);
  return (
    <div className="whitespace-pre-wrap break-words text-ui-sm leading-relaxed">
      {parts.map((p, i) => {
        const m = p.match(/^\[来源(\d+)\]$/);
        return m ? (
          <button key={i} type="button" data-testid="kb-source-anchor"
            onClick={() => onSource(Number(m[1]))}
            className="mx-0.5 rounded bg-selected px-1 py-px align-baseline text-ui-xs font-medium hover:underline"
            title="打开来源文件">[{Number(m[1])}]</button>
        ) : (<span key={i}>{p}</span>);
      })}
    </div>
  );
}

// ── 问答侧栏（B26-B46）──
function QaSidebar(props: {
  scope: QaScope; threadId: string | null; msgs: KbMsg[]; sources: KbSource[];
  qaState: "idle" | "retrieving" | "streaming" | "error"; errorMsg: string | null;
  onSend: (text: string, quote: KbQuote | null) => void; onClear: () => void;
  onSource: (n: number) => void; pendingQuote: KbQuote | null; onRemoveQuote: () => void;
  onClose?: () => void;
  modelChoices: KbModelChoice[]; modelValue: string; onModelChange: (v: string) => void;
}) {
  const [input, setInput] = useState("");
  const { scope, threadId, msgs, sources, qaState, errorMsg, onSend, onClear, onSource, pendingQuote, onRemoveQuote } = props;
  const sending = qaState === "retrieving" || qaState === "streaming";
  // B37：文件档问答侧栏头部模型选择器（发送中锁定）；非文件档跟随主对话（选择器不出现在头部）。
  const showModelPicker = scope.kind === "file";
  const scopeTag = scope.kind === "global" ? "全部文件"
    : scope.kind === "folder" ? `文件夹 · ${scope.folderName}` : `文件 · ${scope.fileName}`;
  const placeholder = scope.kind === "global" ? "输入对知识库的问题…"
    : scope.kind === "folder" ? `输入关于「${scope.folderName}」的问题…` : "针对当前文件提问…";
  const emptyCard = scope.kind === "global"
    ? "围绕全部已收录文件提问，可查条文原文、比对案例、跨文件归纳要点。"
    : scope.kind === "folder"
      ? "只检索当前文件夹及其子文件夹，其他目录的内容不会混入回答。"
      : "基于当前文件内容继续追问，可问关键条款、风险点或内容摘要。";
  const send = () => {
    if (!input.trim() || sending) return;
    onSend(input, pendingQuote); // B30：发送即清空输入行，引用卡随发送消费
    setInput("");
  };
  return (
    <div className="flex h-full min-h-0 flex-col border-l border-border bg-header" data-testid="kb-qa-sidebar">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <MessageSquare className="size-4 shrink-0" />
        <span className="truncate text-ui-sm font-medium">知识库问答</span>
        <span className="max-w-[45%] truncate rounded bg-selected px-1.5 py-0.5 text-ui-xs" data-testid="kb-qa-scope-tag">{scopeTag}</span>
        {showModelPicker ? (
          <select
            data-testid="kb-model-select"
            aria-label="回答模型"
            value={props.modelValue}
            disabled={sending}
            onChange={(e) => props.onModelChange(e.target.value)}
            className="max-w-[30%] truncate rounded border border-border bg-background px-1 py-0.5 text-ui-xs outline-none disabled:opacity-50"
          >
            {props.modelChoices.map((c) => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        ) : null}
        <span className="flex-1" />
        {msgs.length > 0 ? (
          <button type="button" data-testid="kb-qa-clear" onClick={onClear} className="text-ui-xs text-foreground-subtle hover:text-foreground">清空对话</button>
        ) : null}
        {props.onClose ? (
          <button type="button" aria-label="收起问答" onClick={props.onClose} className="text-foreground-subtle hover:text-foreground">
            <PanelRightClose className="size-4" />
          </button>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3" data-testid="kb-qa-messages">
        {msgs.length === 0 ? (
          <div className="mt-6 rounded-workspace-panel border border-border p-4 text-ui-sm text-foreground-subtle" data-testid="kb-qa-empty-card">
            {emptyCard}
          </div>
        ) : null}
        {msgs.map((m) => (
          m.kind === "userInput" ? (
            <div key={m.rowId} className="ml-8" data-testid="kb-msg-user">
              {m.kbQuote ? (
                <div className="mb-1 rounded-workspace-panel border border-border bg-background px-2 py-1.5">
                  <p className="text-ui-xs font-medium">{m.kbQuote.source}</p>
                  <p className="max-h-24 overflow-y-auto whitespace-pre-wrap text-ui-xs text-foreground-subtle">{m.kbQuote.text}</p>
                </div>
              ) : null}
              <div className="rounded-workspace-panel rounded-br-sm bg-selected px-3 py-2 text-ui-sm whitespace-pre-wrap break-words">{m.text}</div>
              <p className="mt-0.5 text-right text-ui-xs text-foreground-subtle">{fmtTime(m.createdAt)}</p>
            </div>
          ) : (
            <div key={m.rowId} className="mr-4" data-testid="kb-msg-assistant">
              {(() => {
                const parts = splitReasoning(m.text, m.reasoning);
                const showBubble = parts.reasoning && (m.state !== "complete" || true);
                return showBubble ? (
                  <details className="mb-1 rounded-workspace-panel border border-border bg-muted/40 px-2 py-1.5" data-testid="kb-msg-reasoning">
                    <summary className="cursor-pointer select-none text-ui-xs text-foreground-subtle">思考过程</summary>
                    <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap text-ui-xs leading-relaxed text-foreground-subtle">{parts.reasoning}</p>
                  </details>
                ) : null;
              })()}
              {m.state === "streaming" && !m.text ? (
                <div className="flex items-center gap-2 text-ui-sm text-foreground-subtle">
                  <span className="size-2 animate-pulse rounded-full bg-current" />
                  {qaState === "retrieving" ? "正在检索知识库…" : "AI 思考中…"}
                </div>
              ) : m.text ? (
                <div className="rounded-workspace-panel rounded-bl-sm border border-border bg-background px-3 py-2">
                  <AnswerBody text={splitReasoning(m.text, m.reasoning).answer} onSource={onSource} />
                  {m.state !== "complete" ? <p className="mt-1 text-ui-xs text-foreground-subtle">回答中…</p> : null}
                </div>
              ) : m.state === "failed" ? null : null}
              {m.state === "complete" && !m.text ? (
                <div className="rounded-workspace-panel border border-border bg-background px-3 py-2 text-ui-sm text-foreground-subtle">（AI 没有返回内容）</div>
              ) : null}
              {m.state === "failed" && m.text ? (
                <div className="rounded-workspace-panel border border-red-300 bg-red-50 px-3 py-2 text-ui-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">{m.text}</div>
              ) : null}
              <p className="mt-0.5 text-ui-xs text-foreground-subtle">{fmtTime(m.createdAt)}</p>
            </div>
          )
        ))}
        {qaState === "streaming" && msgs.some((m) => m.kind === "assistantText" && m.text) ? (
          <p className="text-ui-xs text-foreground-subtle">回答生成中…</p>
        ) : null}
      </div>
      {errorMsg ? (
        <p className="mx-3 mb-2 rounded border border-red-300 bg-red-50 px-2 py-1.5 text-ui-xs text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300" data-testid="kb-qa-error">{errorMsg}</p>
      ) : null}
      <div className="border-t border-border px-3 py-2">
        {pendingQuote ? (
          <div className="mb-2 rounded-workspace-panel border border-border bg-background px-2 py-1.5" data-testid="kb-quote-card">
            <div className="flex items-center gap-2">
              <p className="flex-1 truncate text-ui-xs font-medium">{pendingQuote.source}</p>
              <button type="button" aria-label="移除引用" onClick={onRemoveQuote}><X className="size-3" /></button>
            </div>
            <p className="max-h-20 overflow-y-auto whitespace-pre-wrap text-ui-xs text-foreground-subtle">{pendingQuote.text}</p>
          </div>
        ) : null}
        {sources.length > 0 ? (
          <p className="mb-1 truncate text-ui-xs text-foreground-subtle" data-testid="kb-qa-sources">
            本轮来源：{sources.map((s) => `[${s.n}] ${s.title}`).join("　")}
          </p>
        ) : null}
        <div className="flex items-center gap-2">
          <input
            data-testid="kb-qa-input"
            value={input}
            disabled={sending}
            placeholder={placeholder}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) send(); }}
            className="min-w-0 flex-1 rounded border border-border bg-background px-2 py-1.5 text-ui-sm outline-none focus:border-ring"
          />
          <button type="button" data-testid="kb-qa-send" aria-label="发送" disabled={!input.trim() || sending}
            onClick={send}
            className={`shrink-0 rounded-full px-3 py-1.5 text-ui-sm ${!input.trim() || sending ? "bg-muted text-foreground-subtle" : "bg-primary text-primary-foreground"}`}>↑</button>
        </div>
        <p className="mt-1 text-ui-xs text-foreground-subtle">按 Enter 发送</p>
      </div>
      {threadId ? <span className="hidden" data-testid="kb-qa-thread-id">{threadId}</span> : null}
    </div>
  );
}

// ── 文件预览页左栏（B21/B23）──
type PreviewData = { kind: "text"; text: string } | { kind: "binary"; mime: string; base64: string } | { kind: "none"; note: string };
function FilePreview({ data, ext, highlight, onPdfPage, onOpenExternal }: { data: PreviewData | null; ext: string; highlight: string[]; onPdfPage: (p: number) => void; onOpenExternal: () => void }) {
  const wrapHighlighted = (text: string) => {
    // 高亮=本地覆盖（会话内，不入库，B35 语义）：文本预览把划选词包 <mark>
    let nodes: Array<string | { hl: string }> = [text];
    for (const word of highlight) {
      if (!word.trim()) continue;
      const next: Array<string | { hl: string }> = [];
      for (const n of nodes) {
        if (typeof n !== "string") { next.push(n); continue; }
        const segs = n.split(word);
        segs.forEach((s, i) => { if (i) next.push({ hl: word }); if (s) next.push(s); });
      }
      nodes = next;
    }
    return nodes;
  };
  if (!data) return <p className="p-4 text-ui-sm text-foreground-subtle">正在读取文件…</p>;
  if (data.kind === "none") return (
    <div className="p-4 text-ui-sm text-foreground-subtle" data-testid="kb-preview-none">
      {data.note}。可在系统中用默认应用打开该类型文件。
      <div className="mt-2">
        <button type="button" data-testid="kb-open-external" onClick={onOpenExternal}
          className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected">系统打开</button>
      </div>
    </div>
  );
  if (data.kind === "binary") {
    if (data.mime === "application/pdf") {
      const bin = Uint8Array.from(atob(data.base64), (c) => c.charCodeAt(0));
      return <div className="h-full overflow-auto" data-testid="kb-preview-pdf">
        <PdfPreviewContent source={bin} onPageChange={onPdfPage} labels={{ loading: "正在载入 PDF…", loadError: "PDF 载入失败", noData: "没有 PDF 数据", previousPage: "上一页", nextPage: "下一页", pageInput: "页码", zoomIn: "放大", zoomOut: "缩小" }} />
      </div>;
    }
    if (data.mime.startsWith("image/")) {
      return <div className="flex h-full items-center justify-center p-3" data-testid="kb-preview-image">
        <img src={`data:${data.mime};base64,${data.base64}`} alt="文件预览" className="max-h-full max-w-full object-contain" />
      </div>;
    }
    if (data.mime.startsWith("audio/")) {
      return <div className="flex h-full items-center justify-center p-4" data-testid="kb-preview-audio">
        <audio controls src={`data:${data.mime};base64,${data.base64}`} className="w-full max-w-md" />
      </div>;
    }
    return <p className="p-4 text-ui-sm text-foreground-subtle">该类型暂不支持应用内预览。</p>;
  }
  const isMarkdown = [".md", ".markdown"].includes(ext);
  if (isMarkdown) {
    // 轻量 markdown 面（标题/粗体/代码不展开全解析；正文优先可读性）
    return (
      <div className="p-4" data-testid="kb-preview-text">
        {data.text.split(/\n{2,}/).map((para, i) => {
          const h = para.match(/^(#{1,6})\s+(.*)$/);
          if (h) return <h3 key={i} className={`mb-1 font-semibold ${(h[1]?.length ?? 1) <= 2 ? "text-ui-lg" : "text-ui-base"}`}>{h[2]}</h3>;
          const parts = wrapHighlighted(para);
          return <p key={i} className="mb-2 whitespace-pre-wrap text-ui-sm leading-relaxed">
            {parts.map((p, j) => typeof p === "string" ? <span key={j}>{p}</span> : <mark key={j} className="rounded bg-yellow-200 px-0.5 dark:bg-yellow-700 dark:text-yellow-50">{p.hl}</mark>)}
          </p>;
        })}
      </div>
    );
  }
  return (
    <pre className="p-4 font-mono text-ui-xs leading-relaxed whitespace-pre-wrap break-words" data-testid="kb-preview-text">
      {wrapHighlighted(data.text).map((p, j) => typeof p === "string" ? <span key={j}>{p}</span> : <mark key={j} className="rounded bg-yellow-200 px-0.5 dark:bg-yellow-700 dark:text-yellow-50">{p.hl}</mark>)}
    </pre>
  );
}

// ── B24 文件视图错误边界：视图渲染崩溃兜底（自写文案；「回到文件列表」复位）──
interface FileBoundaryState { error: Error | null }
class KbFileErrorBoundary extends React.Component<{ fileName: string; onBack: () => void; children: React.ReactNode }, FileBoundaryState> {
  state: FileBoundaryState = { error: null };
  static getDerivedStateFromError(error: unknown): FileBoundaryState {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-6" data-testid="kb-file-error-boundary">
          <p className="text-ui-base font-medium">打开「{this.props.fileName}」时视图出错</p>
          <p className="max-w-md text-center text-ui-sm text-foreground-subtle">{this.state.error.message}</p>
          <div className="flex gap-2">
            <button type="button" onClick={() => this.setState({ error: null })}
              className="rounded border border-border px-3 py-1 text-ui-sm hover:bg-selected">重试渲染</button>
            <button type="button" data-testid="kb-file-boundary-back" onClick={this.props.onBack}
              className="rounded bg-primary px-3 py-1 text-ui-sm text-primary-foreground">回到文件列表</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// ═══ 主面板 ═══
export function KnowledgeBasePanel() {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as {
    kbTree?: () => Promise<KbTree>;
    kbCreateFolder?: (p: { path: string }) => Promise<{ path: string }>;
    kbImport?: (p: { folderPath: string; files: Array<{ relPath: string; base64: string }> }) => Promise<{ added: string[]; failed: Array<{ name: string; reason: string }> }>;
    kbDelete?: (p: { paths: Array<{ kind: string; path: string }> }) => Promise<{ files: number; folders: number }>;
    kbMove?: (p: { fromPath: string; toFolder: string }) => Promise<{ from: string; to: string }>;
    kbRead?: (p: { relPath: string }) => Promise<PreviewData & { relPath: string; ext: string }>;
    kbSync?: (p?: { maxFiles?: number }) => Promise<{ files: number; indexed: number; truncated: boolean }>;
    kbAsk?: (p: { threadId?: string | null; question: string; quote?: KbQuote | null; scope: QaScope; model?: KbModelSel | null }) => Promise<{ threadId: string; title: string; sources: KbSource[]; retrieved: number; mode: string }>;
    kbThreadState?: (p: { threadId: string }) => Promise<KbThreadState>;
    kbThreads?: () => Promise<{ threads: KbThreadRec[] }>;
    kbThreadDelete?: (p: { threadId: string }) => Promise<{ deleted: string }>;
    kbResolveSource?: (p: { threadId: string; n: number }) => Promise<{ n: number; title: string; path: string } | null>;
    kbOpenExternal?: (p: { relPath: string }) => Promise<{ ok: boolean; rel: string }>;
    kbClassify?: (p: { paths: string[] }) => Promise<{ categories: Record<string, string>; source: string; skipped?: number }>;
    modelSelectionService?: { getView: () => Promise<{ effectiveSelection: KbModelSel | null; providers?: ReadonlyArray<{ providerId: string; providerName?: string; models?: ReadonlyArray<{ modelId: string }> }> }> };
  };
  const kbReady = Boolean(svc.kbTree && svc.kbAsk);

  // ── 数据面 ──
  const [tree, setTree] = useState<KbTree | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);      // B08 管理面错误条
  const [mgmtBusy, setMgmtBusy] = useState(false);                      // 同步/分类进行中
  const [syncing, setSyncing] = useState(false);
  const [toast, setToast] = useState<{ kind: "ok" | "warn"; text: string } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((kind: "ok" | "warn", text: string, ms = 2200) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast({ kind, text });
    toastTimer.current = setTimeout(() => setToast(null), ms);
  }, []);
  // ── 导航面（B09/B27 上下文档自动跟随：根=全局、进文件夹=文件夹、开文件=文件）──
  const [folderStack, setFolderStack] = useState<string[]>([]);
  const currentFolder = folderStack.length ? folderStack[folderStack.length - 1] : null;
  const [openedFile, setOpenedFile] = useState<string | null>(null);
  // ── B21/B23 系统打开：文件页内失败错误条（IPC 异常与 !ok 两路都落这里）──
  const [fileError, setFileError] = useState<string | null>(null);
  const scope: QaScope = openedFile
    ? { kind: "file", fileName: openedFile.split("/").pop() ?? openedFile, filePath: openedFile, fileSize: undefined }
    : currentFolder
      ? { kind: "folder", folderPath: currentFolder, folderName: currentFolder.split("/").pop() ?? currentFolder }
      : { kind: "global" };
  // ── 选择面（B15/B16）──
  const [selected, setSelected] = useState<string[]>([]);
  const lastClickedRef = useRef<string | null>(null);
  // ── 过滤面（B10）──
  const [filter, setFilter] = useState("");
  // ── 模态 ──
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [moveTarget, setMoveTarget] = useState<string[] | null>(null); // 待移动集合（B16 批移=选中快照；右键菜单=单元素）
  const [confirmDelete, setConfirmDelete] = useState<Array<{ kind: string; path: string }> | null>(null);
  // ── 上传反馈（B12）──
  const [upload, setUpload] = useState<{ done: number; total: number } | null>(null);
  const [uploadDone, setUploadDone] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState(false);
  // ── 问答面（B32 状态机：idle→retrieving→streaming→idle；error 可清空重问）──
  const [qaState, setQaState] = useState<"idle" | "retrieving" | "streaming" | "error">("idle");
  const [qaError, setQaError] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<KbMsg[]>([]);
  const [sources, setSources] = useState<KbSource[]>([]);
  const [pendingQuote, setPendingQuote] = useState<KbQuote | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const deadlineRef = useRef(0);
  const [chatOpen, setChatOpen] = useState(true);
  const [chatWidth, setChatWidth] = useState(400);
  // ── 记录面（B47/B48）──
  const [records, setRecords] = useState<KbThreadRec[] | null>(null);
  const [sidebarTab, setSidebarTab] = useState<"files" | "records">("files");
  // ── B37 模型面：跟随主对话当前所选（modelSelectionService.getView().effectiveSelection）；
  // 文件档头部选择器可选覆盖（含「跟随对话」项）；无任何选择=不传，桥回落内置默认。──
  const [mainSelection, setMainSelection] = useState<KbModelSel | null>(null);
  // 初始即含「跟随对话」默认项（视图异步到达前选择器也永不空——实测踩坑：空 options 致 W6b 挂）
  const [modelChoices, setModelChoices] = useState<KbModelChoice[]>([{ value: "follow", label: "跟随对话", model: null }]);
  const [modelValue, setModelValue] = useState("follow");
  useEffect(() => {
    const svc = zcodeAgentService as { modelSelectionService?: { getView: () => Promise<{ effectiveSelection: KbModelSel | null; providers?: ReadonlyArray<{ providerId: string; providerName?: string; models?: ReadonlyArray<{ modelId: string }> }> }> } };
    if (!svc.modelSelectionService?.getView) return;
    svc.modelSelectionService.getView()
      .then((view) => {
        setMainSelection(view.effectiveSelection ?? null);
        const choices: KbModelChoice[] = [...(modelChoices.length ? modelChoices : [{ value: "follow", label: "跟随对话", model: null }])];
        for (const prov of view.providers ?? []) {
          for (const m of prov.models ?? []) {
            choices.push({
              value: `${prov.providerId}/${m.modelId}`,
              label: (prov.providerName ? prov.providerName + " · " : "") + m.modelId,
              model: { providerId: prov.providerId, modelId: m.modelId },
            });
          }
        }
        setModelChoices(choices);
      })
      .catch(() => { /* 读不到主选择=诚实回落桥内置默认 */ });
  }, [zcodeAgentService, openedFile]);
  const resolveAskModel = useCallback((): KbModelSel | null => {
    if (scope.kind === "file") {
      const picked = modelChoices.find((c) => c.value === modelValue);
      if (picked?.model) return picked.model;
    }
    return mainSelection; // 跟随主对话；null=桥内置默认
  }, [scope, modelValue, modelChoices, mainSelection]);
  // ── 预览面 ──
  const [preview, setPreview] = useState<PreviewData | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null); // B23 文件内容加载失败红字
  const [highlights, setHighlights] = useState<string[]>([]);
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; path: string; kind: "file" | "folder" } | null>(null);

  const reloadTree = useCallback(async () => {
    if (!svc.kbTree) { setLoadError("桥面未提供知识库通道（kbTree 不可用），请确认桥在 3030 运行。"); return; }
    try {
      const t = await svc.kbTree();
      setTree(t);
      setLoadError(null);
    } catch (e) {
      setLoadError(String((e as Error)?.message ?? e)); // B08：列表上方红色错误条持续显示
    }
  }, [svc]);
  const reloadRecords = useCallback(async () => {
    if (!svc.kbThreads) return;
    try { setRecords((await svc.kbThreads()).threads); } catch { setRecords([]); }
  }, [svc]);
  useEffect(() => { void reloadTree(); void reloadRecords(); }, [reloadTree, reloadRecords]);

  // 同步索引（B22）：上传/删除/移动后静默自动；手动按钮带 toast（截断警告 6s）
  const syncIndex = useCallback(async (manual: boolean) => {
    if (!svc.kbSync) return;
    setSyncing(manual);
    try {
      const r = await svc.kbSync();
      if (manual) {
        if (r.truncated) showToast("warn", `文件数超出单次同步上限，本次仅收录前 ${r.files} 个，建议分批整理后再同步。`, 6000);
        else showToast("ok", `知识库索引已同步（${r.files} 个文件）`);
      }
      void reloadTree();
    } catch (e) {
      setLoadError(`同步失败：${String((e as Error)?.message ?? e)}`); // B22：同步失败=错误条（手动与静默自动同反馈）
    } finally { setSyncing(false); }
  }, [svc, showToast, reloadTree]);

  // ── 问答轮询（流式投影 + 终态对账；120 秒上限；卸载中断）──
  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);
  useEffect(() => () => stopPoll(), [stopPoll]); // B45：组件卸载中断在途请求
  const startPoll = useCallback((tid: string) => {
    stopPoll();
    deadlineRef.current = Date.now() + 120000; // B45：120 秒轮询上限
    pollRef.current = setInterval(async () => {
      if (!svc.kbThreadState) return;
      try {
        const st = await svc.kbThreadState({ threadId: tid });
        setMsgs(st.rows.filter((r) => r.kind === "userInput" || r.kind === "assistantText"));
        setSources(st.sources ?? []);
        if (!st.busy) {
          stopPoll();
          if (st.phase === "completedSuccess") {
            setQaState("idle");
            const answer = st.rows.filter((r) => r.kind === "assistantText").at(-1);
            if (answer && !answer.text) setMsgs((prev) => prev.map((r) => (r.rowId === answer.rowId ? { ...r, state: "complete" } : r))); // B46 空回复兜底显示
          } else if (st.phase === "error") {
            setQaState("error");
            setQaError(st.lastError?.message ?? "本轮回答未能完成，请重试。");
          }
        }
        if (Date.now() > deadlineRef.current) { // B45：超时
          stopPoll();
          setQaState("error");
          setQaError("回答超过 120 秒未完成，已停止等待。可清空对话后重问。");
        }
      } catch (e) {
        stopPoll();
        setQaState("error");
        setQaError(String((e as Error)?.message ?? e));
      }
    }, 700);
  }, [svc, stopPoll]);

  const ask = useCallback(async (text: string, quote: KbQuote | null) => {
    if (!svc.kbAsk) { setQaError("桥面未提供问答通道。"); return; }
    setQaError(null);
    setQaState("retrieving"); // 检索期搜索态（B39）
    setPendingQuote(null); // B30 括注：引用卡随发送消费（发送即消费，失败不回滚；乐观行已携带 quote）
    // 本地乐观插入用户行（真实行随 kbThreadState 对账回填）
    const optimistic: KbMsg = { rowId: -Date.now(), kind: "userInput", state: "complete", text, createdAt: Date.now(), kbQuote: quote };
    setMsgs((prev) => [...prev, optimistic]);
    try {
      const r = await svc.kbAsk({ threadId, question: text, quote, scope, model: resolveAskModel() });
      setThreadId(r.threadId);
      setSources(r.sources ?? []);
      setQaState("streaming");
      startPoll(r.threadId);
    } catch (e) {
      setMsgs((prev) => prev.filter((m) => m.rowId !== optimistic.rowId));
      setQaState("error");
      setQaError(String((e as Error)?.message ?? e));
    }
  }, [svc, threadId, scope, startPoll, resolveAskModel]);

  // B44 清空对话：中断在途轮询+清消息+复位线程 id+恢复当前上下文档
  const clearChat = useCallback(() => {
    stopPoll();
    setThreadId(null); setMsgs([]); setSources([]); setQaState("idle"); setQaError(null); setPendingQuote(null);
  }, [stopPoll]);

  // B41 [来源N] 点击：映射查路径→打开文件
  const openBySource = useCallback(async (n: number) => {
    if (!threadId || !svc.kbResolveSource) return;
    try {
      const s = await svc.kbResolveSource({ threadId, n });
      if (s?.path) openFile(s.path);
    } catch { /* 无映射不动作 */ }
  }, [threadId, svc]);

  // ── B21/B23 系统打开：交系统默认应用打开当前文件；失败两路（异常/!ok）落文件页错误条 ──
  const openExternal = useCallback(async (rel: string) => {
    if (!svc.kbOpenExternal) { setFileError("桥面未提供系统打开通道。"); return; }
    try {
      const r = await svc.kbOpenExternal({ relPath: rel });
      if (!r?.ok) setFileError(`打开文件失败：${rel}`);
      else setFileError(null);
    } catch (e) {
      setFileError(`打开文件失败：${String((e as Error)?.message ?? e)}`);
    }
  }, [svc]);

  // ── 文件页（B23）──
  const openFile = useCallback((rel: string) => {
    setOpenedFile(rel);
    setPreview(null);
    setPreviewError(null);
    setFileError(null);
    setHighlights([]);
    setPendingQuote(null);
    pdfPageRef.current = null;
    if (!svc.kbRead) { setPreviewError("桥面未提供文件读取通道。"); return; }
    svc.kbRead({ relPath: rel })
      .then((r) => { setPreview({ kind: r.kind, text: (r as { text?: string }).text ?? "", mime: (r as { mime?: string }).mime ?? "", base64: (r as { base64?: string }).base64 ?? "", note: (r as { note?: string }).note ?? "该类型暂不支持应用内预览" } as PreviewData); })
      .catch((e) => setPreviewError(String((e as Error)?.message ?? e)));
  }, [svc]);

  // ── B35 划选引用：预览区 mouseup 读选区 → 挂引用卡；PDF 档来源带当前页码 ──
  const previewAreaRef = useRef<HTMLDivElement | null>(null);
  const pdfPageRef = useRef<number | null>(null);
  const [selToolbar, setSelToolbar] = useState<{ x: number; y: number; text: string } | null>(null);
  const onPreviewMouseUp = useCallback(() => {
    const sel = window.getSelection();
    const text = sel?.toString().trim() ?? "";
    if (!sel || sel.isCollapsed || text.length < 2 || !previewAreaRef.current?.contains(sel.anchorNode)) {
      setSelToolbar(null);
      return;
    }
    const rect = previewAreaRef.current.getBoundingClientRect();
    let x = rect.width / 2 - 60;
    try {
      const r = sel.getRangeAt(0).getBoundingClientRect();
      if (r.width) x = Math.min(Math.max(8, r.left - rect.left), Math.max(8, rect.width - 140));
    } catch { /* 位置不可得时居中落位 */ }
    setSelToolbar({ x, y: 16, text: text.slice(0, 6000) });
  }, []);
  const quoteFromSelection = useCallback(() => {
    if (!selToolbar || !openedFile) return;
    const name = openedFile.split("/").pop() ?? openedFile;
    const page = pdfPageRef.current;
    setPendingQuote({ text: selToolbar.text, source: page ? `${name} · 第 ${page} 页` : `${name} · 划选内容`, page });
    setSelToolbar(null);
    setChatOpen(true);
    window.getSelection()?.removeAllRanges();
  }, [selToolbar, openedFile]);
  const highlightSelection = useCallback(() => {
    if (selToolbar?.text) setHighlights((prev) => [...new Set([...prev, selToolbar.text])]);
    setSelToolbar(null);
    window.getSelection()?.removeAllRanges();
  }, [selToolbar]);

  // ── 上传（B11/B12/B13）──
  const uploadFiles = useCallback(async (picked: PickedFile[]) => {
    if (!svc.kbImport || !picked.length) return;
    setUploadDone(null);
    setUpload({ done: 0, total: picked.length });
    const files = picked.filter((p) => p.file.size <= 50 * 1024 * 1024);
    const added: string[] = [];
    const failed: Array<{ name: string; reason: string }> = [];
    for (let i = 0; i < files.length; i++) {
      const item = files[i];
      if (!item) break;
      try {
        const b64 = bytesToBase64(await item.file.arrayBuffer());
        const r = await svc.kbImport({ folderPath: currentFolder ?? "", files: [{ relPath: item.relPath, base64: b64 }] });
        added.push(...r.added);
        failed.push(...r.failed);
      } catch (e) {
        failed.push({ name: item.relPath, reason: String((e as Error)?.message ?? e) });
      }
      if (failed.length) break; // B12：任一文件上传失败=中止后续上传
      setUpload({ done: i + 1, total: files.length });
    }
    setUpload(null); // B12：失败即中止进度反馈（成功时也在此收尾）
    if (added.length) {
      setUploadDone(added.length);
      setTimeout(() => setUploadDone(null), 3000); // B12 成功态 3s 淡出
      void reloadTree();
      void syncIndex(false); // B22 静默自动同步
    }
    if (failed.length) setLoadError(`上传失败（${failed.length} 个）：${failed.map((f) => `${f.name}（${f.reason}）`).join("；").slice(0, 300)}`);
  }, [svc, currentFolder, reloadTree, syncIndex]);

  const onFileInputPicked = useCallback((ev: React.ChangeEvent<HTMLInputElement>, folderMode: boolean) => {
    const list = Array.from(ev.target.files ?? []);
    const picked: PickedFile[] = list.map((f) => ({
      relPath: folderMode && "webkitRelativePath" in f && f.webkitRelativePath ? f.webkitRelativePath : f.name,
      file: f,
    }));
    ev.target.value = "";
    void uploadFiles(picked);
  }, [uploadFiles]);

  // ── 拖拽（B11）──
  const onDrop = useCallback(async (ev: React.DragEvent) => {
    ev.preventDefault();
    setDragOver(false);
    const items = Array.from(ev.dataTransfer.items ?? []);
    const entries = items.map((it) => (it.webkitGetAsEntry ? it.webkitGetAsEntry() : null)).filter(Boolean) as FileSystemEntry[];
    const picked: PickedFile[] = [];
    try {
      if (entries.length) {
        for (const e of entries) await walkEntry(e, "", picked);
      } else {
        for (const f of Array.from(ev.dataTransfer.files ?? [])) picked.push({ relPath: f.name, file: f });
      }
    } catch (e) {
      setLoadError(`拖拽上传失败：${String((e as Error)?.message ?? e)}`);
      return;
    }
    void uploadFiles(picked);
  }, [uploadFiles]);

  // ── 管理：新建夹（B14）/删除（B19）/移动（B18）/分类（B17）──
  const createFolder = useCallback(async () => {
    const name = newFolderName.trim();
    setNewFolderOpen(false);
    setNewFolderName("");
    if (!name || !svc.kbCreateFolder) return; // 空名直接关闭（B14）
    try {
      const parent = currentFolder ? currentFolder + "/" : "";
      await svc.kbCreateFolder({ path: parent + name });
      showToast("ok", "文件夹已创建");
      void reloadTree();
    } catch (e) {
      setLoadError(`创建文件夹失败：${String((e as Error)?.message ?? e)}`);
    }
  }, [newFolderName, svc, currentFolder, showToast, reloadTree]);

  const doDelete = useCallback(async () => {
    const paths = confirmDelete ?? [];
    setConfirmDelete(null);
    if (!paths.length || !svc.kbDelete) return;
    try {
      await svc.kbDelete({ paths });
      showToast("ok", "已删除所选项目");
      if (openedFile && paths.some((p) => openedFile === p.path || openedFile.startsWith(p.path + "/"))) setOpenedFile(null);
      void reloadTree();
      void syncIndex(false);
    } catch (e) {
      setLoadError(`删除失败：${String((e as Error)?.message ?? e)}`);
    }
  }, [confirmDelete, svc, openedFile, showToast, reloadTree, syncIndex]);

  const doMove = useCallback(async (toFolder: string) => {
    const batch = moveTarget ?? [];
    setMoveTarget(null);
    if (!batch.length || !svc.kbMove) return;
    let moved = 0;
    const failedMoves: string[] = [];
    for (const from of batch) {
      try {
        await svc.kbMove({ fromPath: from, toFolder });
        if (openedFile && (openedFile === from || openedFile.startsWith(from + "/"))) setOpenedFile(null);
        moved++;
      } catch (e) {
        failedMoves.push(`${from}（${String((e as Error)?.message ?? e)}）`);
      }
    }
    if (moved) showToast("ok", moved === batch.length ? `已移动 ${moved} 项` : `已移动 ${moved} 项`);
    if (failedMoves.length) setLoadError(`移动失败：${failedMoves.join("；").slice(0, 300)}`);
    if (moved) { void reloadTree(); void syncIndex(false); }
  }, [moveTarget, svc, openedFile, showToast, reloadTree, syncIndex]);

  const doClassify = useCallback(async (paths: string[]) => {
    if (!paths.length || !svc.kbClassify) return;
    setMgmtBusy(true);
    try {
      const r = await svc.kbClassify({ paths });
      const skipped = r.skipped ?? 0;
      showToast("ok", `已智能整理 ${Object.keys(r.categories).length - skipped} 项，跳过 ${skipped} 项${r.source === "rules" ? "（规则归类）" : ""}`);
      void reloadTree();
    } catch (e) {
      setLoadError(`智能分类失败：${String((e as Error)?.message ?? e)}`);
    } finally { setMgmtBusy(false); }
  }, [svc, showToast, reloadTree]);

  // ── B47 记录还原（B48）：拉线程块→还原消息流+上下文档；B49 文件联动 ──
  const openRecord = useCallback(async (rec: KbThreadRec) => {
    if (!svc.kbThreadState) return;
    try {
      const st = await svc.kbThreadState({ threadId: rec.threadId });
      stopPoll();
      setThreadId(rec.threadId);
      setMsgs(st.rows);
      setSources(st.sources ?? []);
      setQaState("idle");
      setQaError(null);
      const ctx = st.kbCtx;
      if (ctx?.kind === "file") {
        // B49：文件档记录联动——文件丢失/不匹配显式报错；旧记录无路径时按文件名唯一匹配兜底（重名不猜）
        let target = ctx.filePath ?? null;
        const fallbackName = ctx.fileName;
        if (!target && fallbackName) {
          const base = fallbackName.replace(/\.[^.]+$/u, "");
          const byName = (tree?.docs ?? []).filter((d) => d.relPath.split("/").pop() === fallbackName || d.title === base);
          target = byName.length === 1 ? (byName[0]?.relPath ?? null) : null;
          if (!target) { setQaError(`未找到这条对话对应的文件「${fallbackName}」（重名或已不存在，不做猜测匹配）。`); setChatOpen(true); void reloadRecords(); return; }
        }
        const exists = target ? tree?.docs.some((d) => d.relPath === target) : false;
        if (!exists) {
          setQaError("未找到这条对话对应的文件（可能已被移动、重命名或删除）。");
        } else {
          openFile(target!);
        }
      } else if (ctx?.kind === "folder" && ctx.folderPath) {
        const folderExists = ctx.folderPath === "" || tree?.folders.some((f) => f.path === ctx.folderPath) || tree?.docs.some((d) => d.relPath.startsWith(ctx.folderPath + "/"));
        if (folderExists) setFolderStack(ctx.folderPath.split("/").reduce<string[]>((acc, _, i, arr) => [...acc, arr.slice(0, i + 1).join("/")], []));
        else setQaError("这条对话所在的文件夹已不存在，问答仍可继续，但范围已按全局处理。");
      }
      setChatOpen(true);
      void reloadRecords();
    } catch (e) {
      setQaError(String((e as Error)?.message ?? e));
    }
  }, [svc, tree, stopPoll, openFile, reloadRecords]);

  const deleteRecord = useCallback(async (tid: string) => {
    if (!svc.kbThreadDelete) return;
    if (!window.confirm("删除这条问答记录？删除后不可恢复。")) return;
    try {
      await svc.kbThreadDelete({ threadId: tid });
      if (threadId === tid) clearChat();
      void reloadRecords();
    } catch (e) {
      setQaError(String((e as Error)?.message ?? e));
    }
  }, [svc, threadId, clearChat, reloadRecords]);

  // ── 派生：过滤后的文件夹与文件（B10 名称或路径子串过滤，保留文件夹结构）──
  const q = filter.trim().toLowerCase();
  const visibleFolders = useMemo(() => {
    let list = (tree?.folders ?? []).filter((f) => (currentFolder ? f.path === currentFolder || f.path.startsWith(currentFolder + "/") : !f.path.includes("/")));
    if (currentFolder) list = list.filter((f) => f.path !== currentFolder && f.path.split("/").length === currentFolder.split("/").length + 1);
    if (!q) return list;
    const keep = new Set<string>();
    for (const f of (tree?.folders ?? [])) if (f.path.toLowerCase().includes(q)) { keep.add(f.path); let p = f.path; while (p.includes("/")) { p = p.slice(0, p.lastIndexOf("/")); keep.add(p); } }
    for (const d of (tree?.docs ?? [])) if (d.relPath.toLowerCase().includes(q)) { let p = d.relPath.includes("/") ? d.relPath.slice(0, d.relPath.lastIndexOf("/")) : ""; while (p) { keep.add(p); p = p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : ""; } }
    return list.filter((f) => keep.has(f.path));
  }, [tree, currentFolder, q]);
  const visibleDocs = useMemo(() => {
    let list = (tree?.docs ?? []).filter((d) => (currentFolder ? (d.relPath.startsWith(currentFolder + "/") && !d.relPath.slice(currentFolder.length + 1).includes("/")) : !d.relPath.includes("/")));
    if (q) list = list.filter((d) => d.relPath.toLowerCase().includes(q));
    return list;
  }, [tree, currentFolder, q]);
  const visiblePaths = useMemo(() => [...visibleFolders.map((f) => f.path), ...visibleDocs.map((d) => d.relPath)], [visibleFolders, visibleDocs]);

  // B15 勾选（含 Shift 范围选，按当前可见序）
  const toggleSelect = useCallback((path: string, ev: React.MouseEvent) => {
    setSelected((prev) => {
      if (ev.shiftKey && lastClickedRef.current) {
        const a = visiblePaths.indexOf(lastClickedRef.current);
        const b = visiblePaths.indexOf(path);
        if (a >= 0 && b >= 0) {
          const [lo, hi] = a < b ? [a, b] : [b, a];
          const range = visiblePaths.slice(lo, hi + 1);
          return [...new Set([...prev, ...range])];
        }
      }
      lastClickedRef.current = path;
      return prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path];
    });
  }, [visiblePaths]);

  const docByPath = useMemo(() => new Map((tree?.docs ?? []).map((d) => [d.relPath, d])), [tree]);

  if (!kbReady) {
    return (
      <div className="flex h-full items-center justify-center" data-testid="kb-panel-unready">
        <p className="text-ui-sm text-foreground-subtle">桥面未提供知识库通道（kbTree/kbAsk 不可用），请确认桥在 3030 运行后刷新。</p>
      </div>
    );
  }

  const folderNodes = (tree?.folders ?? []);

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="kb-panel"
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={(e) => { if (e.currentTarget === e.target) setDragOver(false); }}
      onDrop={onDrop}
      onClick={() => setCtxMenu(null)}
    >
      {dragOver ? (
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center bg-background/70" data-testid="kb-drop-overlay">
          <p className="rounded-workspace-panel border border-border bg-header px-6 py-4 text-ui-lg font-medium">松开即上传到「{currentFolder ?? "全部文件"}」</p>
        </div>
      ) : null}
      {/* 头部（B03 五钮） */}
      <header className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2">
        <FolderOpen className="size-5" />
        <h1 className="text-ui-lg font-semibold">知识库</h1>
        <span className="text-ui-caption text-foreground-subtle">所内文集 · 本地检索问答（零出域）</span>
        <span className="flex-1" />
        <label className="cursor-pointer rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected">
          <Upload className="mr-1 inline size-3.5" />上传文件
          <input type="file" multiple className="hidden" onChange={(e) => onFileInputPicked(e, false)} />
        </label>
        <label className="cursor-pointer rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected">
          <Upload className="mr-1 inline size-3.5" />上传文件夹
          <input ref={(el) => { if (el) el.setAttribute("webkitdirectory", ""); }} type="file" multiple className="hidden" onChange={(e) => onFileInputPicked(e, true)} />
        </label>
        <button type="button" data-testid="kb-new-folder" onClick={() => setNewFolderOpen(true)}
          className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected"><FolderPlus className="mr-1 inline size-3.5" />新建文件夹</button>
        <button type="button" data-testid="kb-sync" disabled={syncing} onClick={() => void syncIndex(true)}
          className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected disabled:opacity-50">
          <RotateCw className={`mr-1 inline size-3.5 ${syncing ? "animate-spin" : ""}`} />{syncing ? "同步中" : "同步索引"}
        </button>
        <button type="button" data-testid="kb-chat-toggle" onClick={() => setChatOpen((v) => !v)}
          className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected">
          {chatOpen ? <><MessageSquareOff className="mr-1 inline size-3.5" />收起问答</> : <><MessageSquare className="mr-1 inline size-3.5" />AI 问答</>}
        </button>
      </header>
      <div className="flex min-h-0 flex-1">
        {/* 左栏（B02/B06）：资料库侧栏 */}
        <aside className="flex w-56 shrink-0 flex-col border-r border-border" data-testid="kb-sidebar">
          <div className="flex gap-1 border-b border-border px-2 py-1.5">
            <button type="button" data-testid="kb-tab-files" onClick={() => setSidebarTab("files")}
              className={`flex-1 rounded px-2 py-1 text-ui-sm ${sidebarTab === "files" ? "bg-selected font-medium" : "text-foreground-subtle"}`}>资料库</button>
            <button type="button" data-testid="kb-tab-records" onClick={() => { setSidebarTab("records"); void reloadRecords(); }}
              className={`flex-1 rounded px-2 py-1 text-ui-sm ${sidebarTab === "records" ? "bg-selected font-medium" : "text-foreground-subtle"}`}>问答记录</button>
          </div>
          {sidebarTab === "files" ? (
            <nav className="min-h-0 flex-1 overflow-y-auto px-2 py-2 text-ui-sm">
              <button type="button" data-testid="kb-all-files"
                onClick={() => { setFolderStack([]); }}
                className={`mb-1 flex w-full items-center gap-1.5 rounded px-2 py-1 ${!currentFolder ? "bg-selected font-medium" : "hover:bg-selected"}`}>
                <FolderOpen className="size-4" />全部文件
                <span className="ml-auto rounded-full bg-muted px-1.5 text-ui-xs" data-testid="kb-all-count">{tree?.counts.topLevel ?? 0}</span>
              </button>
              {folderNodes.filter((f) => !f.path.includes("/")).map((f) => (
                <button key={f.path} type="button" data-testid="kb-folder-item"
                  onClick={() => setFolderStack(f.path.split("/").reduce<string[]>((acc, _, i, arr) => [...acc, arr.slice(0, i + 1).join("/")], []))}
                  className={`flex w-full items-center gap-1.5 rounded px-2 py-1 text-left ${currentFolder === f.path || currentFolder?.startsWith(f.path + "/") ? "bg-selected font-medium" : "hover:bg-selected"}`}>
                  <FolderOpen className="size-4" /><span className="truncate">{f.name}</span>
                </button>
              ))}
            </nav>
          ) : (
            <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2 text-ui-sm" data-testid="kb-records">
              <p className="mb-1 px-1 text-ui-xs text-foreground-subtle">共 {records?.length ?? 0} 条</p>
              {records && records.length === 0 ? (
                <p className="px-1 text-ui-xs text-foreground-subtle">还没有问答记录，在右侧提问后这里会出现记录。</p>
              ) : null}
              {(records ?? []).map((r) => (
                <div key={r.threadId} className="group relative mb-1">
                  <button type="button" data-testid="kb-record-item" onClick={() => void openRecord(r)}
                    className="w-full rounded px-2 py-1.5 pr-6 text-left hover:bg-selected">
                    <p className="truncate text-ui-xs font-medium">{r.title}</p>
                    <p className="text-ui-xs text-foreground-subtle">{fmtTime(r.updatedAt)}</p>
                  </button>
                  <button type="button" aria-label="删除记录" data-testid="kb-record-delete"
                    onClick={(e) => { e.stopPropagation(); void deleteRecord(r.threadId); }}
                    className="absolute top-1.5 right-1 hidden text-foreground-subtle hover:text-red-500 group-hover:block">
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="border-t border-border px-3 py-1.5">
            <button type="button" onClick={() => setFolderStack([])} className="text-ui-xs text-foreground-subtle hover:text-foreground">返回全部文件</button>
          </div>
        </aside>

        {/* 中栏（B04-B22 文件表） */}
        <main className="flex min-h-0 min-w-0 flex-1 flex-col" data-testid="kb-file-table-area">
          {openedFile ? (
            <KbFileErrorBoundary fileName={openedFile.split("/").pop() ?? openedFile} onBack={() => { setOpenedFile(null); setPreview(null); setPreviewError(null); setFileError(null); }}>
            <FilePage
              rel={openedFile} preview={preview} previewError={previewError} ext={(docByPath.get(openedFile)?.ext ?? "").toLowerCase()}
              sizeBytes={docByPath.get(openedFile)?.sizeBytes}
              fileError={fileError} onOpenExternal={() => void openExternal(openedFile)}
              onPdfPage={(p) => { pdfPageRef.current = p; }}
              highlights={highlights}
              previewRefCb={(el) => { previewAreaRef.current = el; }}
              onMouseUp={onPreviewMouseUp}
              onBack={() => { setOpenedFile(null); setPreview(null); setPreviewError(null); setFileError(null); }}
              onRetry={() => openFile(openedFile)}
              selToolbar={selToolbar}
              onAskSelection={quoteFromSelection}
              onHighlightSelection={highlightSelection}
              chatOpen={chatOpen} onToggleChat={() => setChatOpen((v) => !v)} qaSlot={
                <QaSidebar scope={scope} threadId={threadId} msgs={msgs} sources={sources} qaState={qaState}
                  errorMsg={qaError} onSend={(t, qt) => void ask(t, qt)} onClear={clearChat} onSource={(n) => void openBySource(n)}
                  pendingQuote={pendingQuote} onRemoveQuote={() => setPendingQuote(null)}
                  modelChoices={modelChoices} modelValue={modelValue} onModelChange={setModelValue} />
              }
              chatWidth={chatWidth}
              onChatWidth={setChatWidth}
            />
            </KbFileErrorBoundary>
          ) : (
            <>
              {/* B08 管理面错误条 + toast + 上传反馈 */}
              <div className="shrink-0 px-4 pt-2">
                {loadError ? <p className="rounded border border-red-300 bg-red-50 px-2 py-1.5 text-ui-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300" data-testid="kb-mgmt-error">{loadError}</p> : null}
                {upload ? (
                  <div className="rounded border border-border bg-background px-2 py-1.5 text-ui-sm" data-testid="kb-upload-progress">
                    正在上传 {upload.done}/{upload.total}
                    <span className="ml-2 inline-block h-1.5 w-40 overflow-hidden rounded bg-muted align-middle">
                      <span className="block h-full bg-primary transition-all" style={{ width: `${Math.round((upload.done / Math.max(1, upload.total)) * 100)}%` }} />
                    </span>
                  </div>
                ) : null}
                {uploadDone !== null ? (
                  <p className="rounded border border-emerald-300 bg-emerald-50 px-2 py-1.5 text-ui-sm text-emerald-700 transition-opacity duration-300 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" data-testid="kb-upload-done">上传完成，已加入 {uploadDone} 个文件</p>
                ) : null}
                {toast ? (
                  <p className={`rounded border px-2 py-1.5 text-ui-sm ${toast.kind === "ok" ? "border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" : "border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300"}`} data-testid="kb-toast">{toast.text}</p>
                ) : null}
              </div>
              {/* B09 面包屑 + B10 过滤 */}
              <div className="flex shrink-0 items-center gap-2 px-4 py-2 text-ui-sm">
                <nav className="flex min-w-0 flex-1 items-center gap-1" data-testid="kb-breadcrumb">
                  <button type="button" onClick={() => setFolderStack([])} className={currentFolder ? "text-foreground-subtle hover:underline" : "font-medium"}>全部文件</button>
                  {folderStack.map((p, i) => (
                    <span key={p} className="flex items-center gap-1">
                      <span className="text-foreground-subtle">›</span>
                      <button type="button" onClick={() => setFolderStack(folderStack.slice(0, i + 1))}
                        className={i === folderStack.length - 1 ? "font-medium" : "text-foreground-subtle hover:underline"}>{p.split("/").pop()}</button>
                    </span>
                  ))}
                </nav>
                <input data-testid="kb-filter" value={filter} onChange={(e) => setFilter(e.target.value)}
                  placeholder="按名称或路径过滤…" className="w-52 rounded border border-border bg-background px-2 py-1 text-ui-sm outline-none focus:border-ring" />
              </div>
              {/* B15 表头全选 */}
              {selected.length > 0 ? (
                <div className="mx-4 mb-1 flex shrink-0 items-center gap-2 rounded border border-border bg-header px-2 py-1 text-ui-sm" data-testid="kb-selection-bar">
                  <span>已选 {selected.length} 项</span>
                  <button type="button" disabled={mgmtBusy} onClick={() => void doClassify(selected.filter((p) => docByPath.has(p)))}
                    className="rounded px-1.5 py-0.5 hover:bg-selected disabled:opacity-50"><Sparkles className="mr-0.5 inline size-3.5" />智能分类</button>
                  <button type="button" onClick={() => setMoveTarget([...selected])}
                    disabled={!selected.length}
                    className="rounded px-1.5 py-0.5 hover:bg-selected disabled:opacity-50"><Pencil className="mr-0.5 inline size-3.5" />移动到</button>
                  <button type="button" onClick={() => setConfirmDelete(selected.map((p) => ({ kind: docByPath.has(p) ? "file" : "folder", path: p })))}
                    className="rounded px-1.5 py-0.5 text-red-600 hover:bg-red-50 dark:hover:bg-red-950"><Trash2 className="mr-0.5 inline size-3.5" />删除</button>
                  <button type="button" onClick={() => setSelected([])} className="ml-auto text-foreground-subtle hover:text-foreground">取消</button>
                </div>
              ) : null}
              <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-2">
                {/* B07 空态 / B08 加载态 */}
                {!tree ? (
                  <p className="mt-10 text-center text-ui-sm text-foreground-subtle" data-testid="kb-loading">加载中…</p>
                ) : visibleFolders.length === 0 && visibleDocs.length === 0 ? (
                  <div className="mt-10 text-center" data-testid="kb-empty">
                    <FolderOpen className="mx-auto mb-2 size-10 text-foreground-subtle" />
                    <p className="text-ui-sm">{q ? "没有匹配的文件" : "当前文件夹为空"}</p>
                    {!q ? <p className="mt-1 text-ui-xs text-foreground-subtle">可以上传文件、上传文件夹，或直接把文件拖到这里。</p> : null}
                  </div>
                ) : (
                  <table className="w-full text-ui-sm" data-testid="kb-file-table">
                    <thead>
                      <tr className="border-b border-border text-left text-ui-xs text-foreground-subtle">
                        <th className="w-8 py-1.5">
                          <input type="checkbox" aria-label="全选" data-testid="kb-select-all"
                            checked={visiblePaths.length > 0 && visiblePaths.every((p) => selected.includes(p))}
                            onChange={(e) => setSelected(e.target.checked ? [...visiblePaths] : selected.filter((p) => !visiblePaths.includes(p)))} />
                        </th>
                        <th className="py-1.5">名称</th>
                        <th className="w-20 py-1.5">类型</th>
                        <th className="w-24 py-1.5">大小</th>
                        <th className="w-36 py-1.5">更新时间</th>
                        <th className="w-16 py-1.5" />
                      </tr>
                    </thead>
                    <tbody>
                      {visibleFolders.map((f) => (
                        <tr key={"f:" + f.path} data-testid="kb-row" className="group border-b border-border/60 hover:bg-selected"
                          onContextMenu={(e) => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, path: f.path, kind: "folder" }); }}>
                          <td className="py-1.5"><input type="checkbox" checked={selected.includes(f.path)} onClick={(e) => toggleSelect(f.path, e)} onChange={() => {}} /></td>
                          <td className="cursor-pointer py-1.5" onClick={() => setFolderStack(f.path.split("/").reduce<string[]>((acc, _, i, arr) => [...acc, arr.slice(0, i + 1).join("/")], []))}>
                            <span className="mr-1.5 inline-flex items-center rounded bg-blue-100 px-1 text-ui-xs text-blue-700 dark:bg-blue-950 dark:text-blue-300">DIR</span>
                            {f.name}
                          </td>
                          <td className="py-1.5 text-foreground-subtle">文件夹</td>
                          <td className="py-1.5 text-foreground-subtle">—</td>
                          <td className="py-1.5 text-foreground-subtle">{fmtTime(f.updatedAt)}</td>
                          <td className="py-1.5 text-right">
                            <span className="inline-flex gap-1 opacity-0 group-hover:opacity-100">
                              <button type="button" aria-label="打开" onClick={() => setFolderStack(f.path.split("/").reduce<string[]>((acc, _, i, arr) => [...acc, arr.slice(0, i + 1).join("/")], []))}><FolderOpen className="size-3.5" /></button>
                              <button type="button" aria-label="删除" onClick={() => setConfirmDelete([{ kind: "folder", path: f.path }])}><Trash2 className="size-3.5" /></button>
                            </span>
                          </td>
                        </tr>
                      ))}
                      {visibleDocs.map((d) => {
                        const badge = extBadge(d.ext);
                        return (
                          <tr key={d.relPath} data-testid="kb-row" className="group border-b border-border/60 hover:bg-selected"
                            onContextMenu={(e) => { e.preventDefault(); setCtxMenu({ x: e.clientX, y: e.clientY, path: d.relPath, kind: "file" }); }}>
                            <td className="py-1.5"><input type="checkbox" checked={selected.includes(d.relPath)} onClick={(e) => toggleSelect(d.relPath, e)} onChange={() => {}} /></td>
                            <td className="cursor-pointer py-1.5" onClick={() => openFile(d.relPath)} data-testid="kb-doc-name">
                              <span className={`mr-1.5 inline-flex items-center rounded px-1 text-ui-xs ${badge.cls}`}>{badge.label}</span>
                              {d.title}{d.ext}
                              {!d.indexed ? <span className="ml-1.5 text-ui-xs text-foreground-subtle" title="该类型暂不参与全文检索">未索引</span> : null}
                            </td>
                            <td className="py-1.5 text-foreground-subtle">{badge.label}</td>
                            <td className="py-1.5 text-foreground-subtle">{fmtSize(d.sizeBytes)}</td>
                            <td className="py-1.5 text-foreground-subtle">{fmtTime(d.mtimeMs)}</td>
                            <td className="py-1.5 text-right">
                              <span className="inline-flex gap-1 opacity-0 group-hover:opacity-100">
                                <button type="button" aria-label="预览" data-testid="kb-row-preview" onClick={() => openFile(d.relPath)}><Eye className="size-3.5" /></button>
                                <button type="button" aria-label="删除" onClick={() => setConfirmDelete([{ kind: "file", path: d.relPath }])}><Trash2 className="size-3.5" /></button>
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
              <div className="shrink-0 px-4 pb-2">
                <button type="button" data-testid="kb-go-up" disabled={!currentFolder} onClick={() => setFolderStack(folderStack.slice(0, -1))}
                  className="rounded border border-border px-2 py-1 text-ui-xs hover:bg-selected disabled:opacity-40">返回上级</button>
                <span className="ml-2 text-ui-xs text-foreground-subtle">{tree ? `${tree.counts.files} 个文件 · 本地索引` : ""}</span>
              </div>
            </>
          )}
        </main>

        {/* 右栏：问答侧栏（B26 视图头部钮开合；文件页时由 FilePage 内嵌） */}
        {!openedFile && chatOpen ? (
          <div className="flex shrink-0 flex-col" style={{ width: chatWidth }} data-testid="kb-qa-container">
            <QaSidebar scope={scope} threadId={threadId} msgs={msgs} sources={sources} qaState={qaState}
              errorMsg={qaError} onSend={(t, qt) => void ask(t, qt)} onClear={clearChat} onSource={(n) => void openBySource(n)}
              pendingQuote={pendingQuote} onRemoveQuote={() => setPendingQuote(null)} onClose={() => setChatOpen(false)}
              modelChoices={modelChoices} modelValue={modelValue} onModelChange={setModelValue} />
          </div>
        ) : null}
      </div>

      {/* B20 右键菜单 */}
      {ctxMenu ? (
        <div className="fixed z-50 rounded border border-border bg-header py-1 text-ui-sm shadow-lg" style={{ left: ctxMenu.x, top: ctxMenu.y }} data-testid="kb-ctx-menu">
          {ctxMenu.kind === "file" ? (
            <button type="button" className="block w-full px-3 py-1 text-left hover:bg-selected disabled:opacity-40"
              disabled={!PREVIEWABLE_EXTS.has((docByPath.get(ctxMenu.path)?.ext ?? "").toLowerCase())}
              onClick={() => { openFile(ctxMenu.path); setCtxMenu(null); }}>预览</button>
          ) : (
            <button type="button" className="block w-full px-3 py-1 text-left hover:bg-selected"
              onClick={() => { setFolderStack(ctxMenu.path.split("/").reduce<string[]>((acc, _, i, arr) => [...acc, arr.slice(0, i + 1).join("/")], [])); setCtxMenu(null); }}>打开</button>
          )}
          <button type="button" className="block w-full px-3 py-1 text-left hover:bg-selected"
            onClick={() => { setMoveTarget([ctxMenu.path]); setCtxMenu(null); }}>移动到</button>
          <button type="button" className="block w-full px-3 py-1 text-left text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
            onClick={() => { setConfirmDelete([{ kind: ctxMenu.kind, path: ctxMenu.path }]); setCtxMenu(null); }}>删除</button>
        </div>
      ) : null}

      {/* B14 新建文件夹模态 */}
      {newFolderOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/60" data-testid="kb-new-folder-modal"
          onClick={() => setNewFolderOpen(false)}>
          <div className="w-80 rounded-workspace-panel border border-border bg-header p-4" onClick={(e) => e.stopPropagation()}>
            <p className="mb-2 text-ui-base font-medium">新建文件夹</p>
            <input autoFocus data-testid="kb-new-folder-input" value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void createFolder(); if (e.key === "Escape") setNewFolderOpen(false); }}
              placeholder="文件夹名称" className="w-full rounded border border-border bg-background px-2 py-1.5 text-ui-sm outline-none focus:border-ring" />
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" onClick={() => setNewFolderOpen(false)} className="rounded border border-border px-3 py-1 text-ui-sm">取消</button>
              <button type="button" data-testid="kb-new-folder-confirm" onClick={() => void createFolder()} className="rounded bg-primary px-3 py-1 text-ui-sm text-primary-foreground">创建</button>
            </div>
          </div>
        </div>
      ) : null}

      {/* B18 移动到模态（B16 批移：目标列表排除待移动对象自身及其子树） */}
      {moveTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/60" data-testid="kb-move-modal" onClick={() => setMoveTarget(null)}>
          <div className="max-h-96 w-80 overflow-y-auto rounded-workspace-panel border border-border bg-header p-4" onClick={(e) => e.stopPropagation()}>
            <p className="mb-2 text-ui-base font-medium">移动到…（{moveTarget.length} 项）</p>
            <button type="button" onClick={() => void doMove("")} className="block w-full rounded px-2 py-1 text-left text-ui-sm hover:bg-selected">（根目录）</button>
            {folderNodes.filter((f) => !moveTarget.some((m) => f.path === m || f.path.startsWith(m + "/"))).map((f) => (
              <button key={f.path} type="button" onClick={() => void doMove(f.path)}
                className="block w-full truncate rounded px-2 py-1 text-left text-ui-sm hover:bg-selected"
                style={{ paddingLeft: 8 + (f.path.split("/").length - 1) * 14 }}>{f.name}</button>
            ))}
          </div>
        </div>
      ) : null}

      {/* B19 删除确认 */}
      {confirmDelete ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/60" data-testid="kb-delete-modal" onClick={() => setConfirmDelete(null)}>
          <div className="w-80 rounded-workspace-panel border border-border bg-header p-4" onClick={(e) => e.stopPropagation()}>
            <p className="mb-2 text-ui-base font-medium">确认删除</p>
            <p className="text-ui-sm text-foreground-subtle">将删除 {confirmDelete.length} 项，该操作不可撤销。</p>
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" onClick={() => setConfirmDelete(null)} className="rounded border border-border px-3 py-1 text-ui-sm">取消</button>
              <button type="button" data-testid="kb-delete-confirm" onClick={() => void doDelete()} className="rounded bg-red-600 px-3 py-1 text-ui-sm text-white">删除</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ── 文件页（B23/B24/B35）：左预览+右问答，分隔条可拖宽（320-520，预览保最小宽）；头部含
//    大小/系统打开/AI 对话开合（B23）；问答栏可收起（B26 文件页右栏常驻可开合）──
function FilePage(props: {
  rel: string; preview: PreviewData | null; previewError: string | null; ext: string; sizeBytes?: number;
  fileError: string | null; onOpenExternal: () => void; onPdfPage: (p: number) => void;
  highlights: string[]; previewRefCb: (el: HTMLDivElement | null) => void;
  onMouseUp: () => void; onBack: () => void; onRetry: () => void;
  selToolbar: { x: number; y: number; text: string } | null;
  onAskSelection: () => void; onHighlightSelection: () => void;
  chatOpen: boolean; onToggleChat: () => void; qaSlot: React.ReactNode; chatWidth: number; onChatWidth: (w: number) => void;
}) {
  const docExt = props.ext;
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);
  const onSepDown = useCallback((e: React.MouseEvent) => {
    dragRef.current = { startX: e.clientX, startW: props.chatWidth };
    const move = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const next = dragRef.current.startW - (ev.clientX - dragRef.current.startX);
      props.onChatWidth(Math.min(520, Math.max(320, next)));
    };
    const up = () => { dragRef.current = null; window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }, [props]);
  return (
    <div className="flex min-h-0 flex-1">
      <section className="flex min-h-0 min-w-0 flex-1 flex-col" data-testid="kb-file-page">
        <header className="flex shrink-0 items-center gap-2 border-b border-border px-4 py-2">
          <button type="button" data-testid="kb-file-back" onClick={props.onBack}
            className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected">← 返回</button>
          <span className={`inline-flex items-center rounded px-1 text-ui-xs ${extBadge(docExt).cls}`}>{extBadge(docExt).label}</span>
          <span className="truncate text-ui-sm font-medium">{props.rel.split("/").pop()}</span>
          <span className="truncate text-ui-xs text-foreground-subtle">{props.rel}</span>
          {typeof props.sizeBytes === "number" ? <span className="shrink-0 text-ui-xs text-foreground-subtle">{fmtSize(props.sizeBytes)}</span> : null}
          <span className="flex-1" />
          <button type="button" data-testid="kb-open-external-header" onClick={props.onOpenExternal}
            className="shrink-0 rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected">系统打开</button>
          <button type="button" data-testid="kb-file-chat-toggle" onClick={props.onToggleChat}
            className="shrink-0 rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected">
            {props.chatOpen ? <><MessageSquareOff className="mr-1 inline size-3.5" />收起问答</> : <><MessageSquare className="mr-1 inline size-3.5" />AI 对话</>}
          </button>
        </header>
        {props.fileError ? (
          <p className="mx-4 mt-2 rounded border border-red-300 bg-red-50 px-2 py-1.5 text-ui-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300" data-testid="kb-file-error">{props.fileError}</p>
        ) : null}
        {props.previewError ? (
          <div className="p-4" data-testid="kb-preview-error">
            <p className="text-ui-sm text-red-600 dark:text-red-400">文件内容加载失败：{props.previewError}</p>
            <div className="mt-2 flex gap-2">
              <button type="button" onClick={props.onRetry} className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected">重试读取</button>
              <button type="button" data-testid="kb-open-external" onClick={props.onOpenExternal}
                className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected">系统打开</button>
            </div>
          </div>
        ) : (
          <div ref={props.previewRefCb} onMouseUp={props.onMouseUp} className="relative min-h-0 flex-1 overflow-auto">
            <FilePreview data={props.preview} ext={docExt} highlight={props.highlights}
              onPdfPage={props.onPdfPage} onOpenExternal={props.onOpenExternal} />
            {props.selToolbar ? (
              <div className="absolute z-10 flex gap-1 rounded border border-border bg-header px-1 py-1 shadow-lg" style={{ left: props.selToolbar.x, top: props.selToolbar.y }} data-testid="kb-sel-toolbar">
                <button type="button" onClick={props.onHighlightSelection} className="rounded px-2 py-0.5 text-ui-xs hover:bg-selected">高亮</button>
                <button type="button" data-testid="kb-sel-ask" onClick={props.onAskSelection} className="rounded bg-primary px-2 py-0.5 text-ui-xs text-primary-foreground">问 AI</button>
              </div>
            ) : null}
          </div>
        )}
      </section>
      {/* 分隔条（拖宽 320-520）+ 问答栏（B26 文件页常驻可开合） */}
      {props.chatOpen ? (
        <>
          <div className="w-1 shrink-0 cursor-col-resize bg-border/60 hover:bg-border" onMouseDown={onSepDown} data-testid="kb-splitter" />
          <div className="flex min-h-0 shrink-0" style={{ width: props.chatWidth }}>
            {props.qaSlot}
          </div>
        </>
      ) : null}
    </div>
  );
}
