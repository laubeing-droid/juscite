// 【功能 #6 材料上传解析】对话文件浮层面板（RE-6 §3 UI 结构；对拍 35/36/55）。
// 行为锚点：入口总数徽标（在 BridgeMaterialBar）；浮层分「用户文件 / Agent 产出」两组计数列表
// （对拍 35，分组数据源=bridge_attachments.producer，迁移 0019）；空态引导文案（自写）；
// Esc 关闭；点击文件行→关闭列表并打开右侧预览，预览头部「返回文件列表」回列表（对拍 55）；
// 预览按类型分派：图片 / PDF（pdf.js 懒加载）/ docx（docx-preview 转 HTML）/ 文本（语言徽章）/
// 不支持格式信息卡；读取中与失败红字（对拍 36）。文案全部自写（表达隔离）。
import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { ArrowLeft, FileText, RefreshCw, X } from "lucide-react";
import {
  attachmentKindOf,
  fetchBridgeAttachmentBytes,
  listBridgeMaterialAttachments,
  type BridgeAttachmentItem,
  type MaterialAttachmentKind,
} from "@/lib/bridgeMaterialAttachments.js";
import { PreviewPaneOfficeDocxContent } from "@/previewPaneOfficeDocxContent.js";

// pdf.js 在模块导入阶段依赖浏览器 DOMMatrix；仅在渲染 PDF 分支懒加载（同 ChatMedia 预览先例）。
const LazyPdfViewer = lazy(async () => {
  const module = await import("@/components/ui/pdf-viewer.js");
  return { default: module.PdfViewer };
});

const GROUPS: Array<{ producer: "user" | "agent"; title: string; empty: string }> = [
  { producer: "user", title: "用户文件", empty: "本会话还没有上传过文件，可在下方材料区拖入或粘贴。" },
  { producer: "agent", title: "Agent 产出", empty: "暂无 Agent 产出文件。" },
];

const LANG_BADGES: Record<string, string> = {
  txt: "TXT", md: "MD", markdown: "MD", csv: "CSV", json: "JSON",
  xml: "XML", html: "HTML", log: "LOG", yml: "YAML", yaml: "YAML",
};

interface PreviewState {
  item: BridgeAttachmentItem;
  status: "loading" | "ready" | "failed";
  errorMessage: string | null;
  bytes: Uint8Array | null;
}

export function ThreadFilesPanel({ open, onClose, sessionId }: { open: boolean; onClose: () => void; sessionId: string }) {
  const [items, setItems] = useState<BridgeAttachmentItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PreviewState | null>(null);

  const load = useCallback(async () => {
    setItems(null);
    setLoadError(null);
    try {
      setItems(await listBridgeMaterialAttachments({ threadId: sessionId }));
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "文件列表读取失败");
    }
  }, [sessionId]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  // 对拍 35：Esc 关闭浮层
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose]);

  const openPreview = useCallback(
    (item: BridgeAttachmentItem) => {
      // 对拍 55：点击行→关列表开预览；内容经作用域授权读回（无凭据/越权由桥面裁定）
      setPreview({ item, status: "loading", errorMessage: null, bytes: null });
      fetchBridgeAttachmentBytes(item.id, { threadId: sessionId })
        .then((content) => setPreview({ item, status: "ready", errorMessage: null, bytes: content.bytes }))
        .catch((error) =>
          setPreview({
            item,
            status: "failed",
            errorMessage: error instanceof Error ? error.message : "文件内容读取失败",
            bytes: null,
          }),
        );
    },
    [sessionId],
  );

  if (!open) return null;
  const total = items?.length ?? 0;
  const kindOf = (item: BridgeAttachmentItem): MaterialAttachmentKind => attachmentKindOf(item.filename, item.mimeType);

  return (
    <div
      data-testid="thread-files-panel"
      className="absolute bottom-full right-0 z-30 mb-2 w-96 max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-border bg-background shadow-xl"
    >
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        {preview ? (
          <button
            type="button"
            aria-label="返回文件列表"
            data-testid="thread-files-back"
            className="flex items-center gap-1 text-xs text-foreground-subtle hover:text-foreground"
            onClick={() => setPreview(null)} // 对拍 55：返回列表
          >
            <ArrowLeft className="h-3.5 w-3.5" /> 返回文件列表
          </button>
        ) : (
          <span className="text-xs font-medium text-foreground">
            对话文件
            <span className="ml-1.5 rounded-full bg-muted px-1.5 text-[10px] text-foreground-subtle" data-testid="thread-files-total">
              {total}
            </span>
          </span>
        )}
        <div className="flex items-center gap-1">
          {!preview && (
            <button
              type="button"
              aria-label="刷新文件列表"
              className="flex h-6 w-6 items-center justify-center rounded text-foreground-subtle hover:bg-muted"
              onClick={() => void load()}
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            type="button"
            aria-label="关闭文件面板"
            data-testid="thread-files-close"
            className="flex h-6 w-6 items-center justify-center rounded text-foreground-subtle hover:bg-muted"
            onClick={onClose}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {preview ? (
        <div className="max-h-96 overflow-auto p-3" data-testid="thread-files-preview">
          <div className="mb-2 truncate text-xs font-medium text-foreground" title={preview.item.filename}>
            {preview.item.filename}
            <span className="ml-2 rounded bg-muted px-1 py-px text-[10px] font-normal text-foreground-subtle">
              {attachmentKindOf(preview.item.filename, preview.item.mimeType) === "text"
                ? (LANG_BADGES[preview.item.filename.split(".").pop()?.toLowerCase() ?? ""] ?? "文本")
                : preview.item.mimeType.split("/").pop()?.toUpperCase()}
            </span>
          </div>
          {preview.status === "loading" && (
            <div className="py-8 text-center text-xs text-foreground-subtle" data-testid="thread-files-preview-loading">
              正在读取文件内容…
            </div>
          )}
          {preview.status === "failed" && (
            <div className="py-4 text-center text-xs text-red-600 dark:text-red-400" data-testid="thread-files-preview-error">
              {preview.errorMessage ?? "文件内容读取失败"}
            </div>
          )}
          {preview.status === "ready" && preview.bytes && renderPreviewBody(kindOf(preview.item), preview.bytes)}
        </div>
      ) : (
        <div className="max-h-80 overflow-auto px-3 py-2">
          {loadError && (
            <div className="py-3 text-xs text-red-600 dark:text-red-400">{loadError}</div>
          )}
          {!loadError && items === null && (
            <div className="py-6 text-center text-xs text-foreground-subtle">正在读取文件列表…</div>
          )}
          {!loadError && items !== null && total === 0 && (
            <div className="py-6 text-center text-xs text-foreground-subtle" data-testid="thread-files-empty">
              会话中上传的文件会集中显示在这里，便于随时回看。
            </div>
          )}
          {!loadError &&
            items !== null &&
            GROUPS.map((group) => {
              const groupItems = items.filter((item) => (item.producer === "agent" ? "agent" : "user") === group.producer);
              return (
                <div key={group.producer} className="mb-2" data-testid={`thread-files-group-${group.producer}`}>
                  <div className="mb-1 flex items-center gap-1.5 text-[11px] text-foreground-subtle">
                    {group.title}
                    <span className="rounded-full bg-muted px-1.5 text-[10px]">{groupItems.length}</span>
                  </div>
                  {groupItems.length === 0 ? (
                    <div className="rounded border border-dashed border-border px-2 py-2 text-[11px] text-foreground-subtle">
                      {group.empty}
                    </div>
                  ) : (
                    <div className="space-y-1">
                      {groupItems.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          data-testid="thread-files-row"
                          className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left hover:bg-muted"
                          onClick={() => openPreview(item)} // 对拍 55：行点击开预览
                        >
                          <FileText className="h-3.5 w-3.5 shrink-0 text-foreground-subtle" />
                          <span className="min-w-0 flex-1 truncate text-xs text-foreground">{item.filename}</span>
                          <span className="shrink-0 rounded bg-muted px-1 py-px text-[10px] text-foreground-subtle">
                            {attachmentKindLabelOf(kindOf(item))}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}

function attachmentKindLabelOf(kind: MaterialAttachmentKind): string {
  return ({
    docx: "文档",
    pdf: "PDF",
    image: "图片",
    audio: "音频",
    video: "视频",
    text: "文本",
    other: "文件",
  })[kind];
}

function renderPreviewBody(kind: MaterialAttachmentKind, bytes: Uint8Array) {
  if (kind === "image") {
    const blob = new Blob([bytes as BlobPart], { type: "image/png" });
    return <img src={URL.createObjectURL(blob)} alt="附件预览" className="max-h-72 w-full rounded object-contain" data-testid="thread-files-preview-image" />;
  }
  if (kind === "pdf") {
    return (
      <div className="h-72 overflow-hidden rounded border border-border" data-testid="thread-files-preview-pdf">
        <Suspense fallback={<div className="p-4 text-center text-xs text-foreground-subtle">正在装载 PDF 阅读器…</div>}>
          <LazyPdfViewer source={bytes} className="h-full" />
        </Suspense>
      </div>
    );
  }
  if (kind === "docx") {
    return (
      <div className="overflow-auto rounded border border-border" data-testid="thread-files-preview-docx">
        <PreviewPaneOfficeDocxContent
          buffer={bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer}
          errorMessage=""
          sourcePath=""
        />
      </div>
    );
  }
  if (kind === "text") {
    const text = new TextDecoder().decode(bytes);
    return (
      <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-all rounded border border-border bg-muted/30 p-2 text-[11px] leading-relaxed text-foreground" data-testid="thread-files-preview-text">
        {text}
      </pre>
    );
  }
  return (
    <div className="rounded border border-dashed border-border px-3 py-6 text-center text-xs text-foreground-subtle" data-testid="thread-files-preview-unsupported">
      此格式暂不支持内嵌预览；原件已随会话保存，可在需要时按名称取回。
    </div>
  );
}
