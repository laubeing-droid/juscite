// 【功能 #6 材料上传解析】对话输入框附件区（RE-6 §3 UI 结构；对拍 1/2/3/4/5/6/43/47/48/49）。
// 挂在真实聊天输入框（ConversationComposer）正下方：芯片区（图片缩略图+删角标 / 文件图标+名+
// 类型徽章+删除 / 失败红字 / 上传中转圈）＋「＋」菜单（上传文件，多选，选后重置 input 同件可重选）
// ＋拖拽（copy 效果）＋粘贴分流（图片直传；≥200 字转「粘贴内容.txt」；长正文与图片并存长文本优先）
// ＋对话文件面板入口（总数徽标）。上传中无取消入口（对拍 49）；存在上传中附件时由宿主禁用发送
// （对拍 48）。全部文案自写（表达隔离）。
import { useEffect, useRef, useState } from "react";
import { FileText, Loader2, Paperclip, Plus, X } from "lucide-react";
import { collectDroppedFiles } from "@/lib/bridgeMaterialAttachments.js";
import type { BridgeMaterialChip } from "@/v4/composer/useBridgeMaterialAttachments.js";
import { ThreadFilesPanel } from "@/v4/composer/ThreadFilesPanel.js";

export interface BridgeMaterialBarProps {
  chips: BridgeMaterialChip[];
  hasInFlight: boolean;
  filesCount: number;
  sessionId: string | null;
  onFiles: (files: File[]) => void;
  onPaste: (dataTransfer: DataTransfer) => void;
  onRemove: (key: string) => void;
}

export function BridgeMaterialBar({
  chips,
  hasInFlight,
  filesCount,
  sessionId,
  onFiles,
  onPaste,
  onRemove,
}: BridgeMaterialBarProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const [pasteHint, setPasteHint] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  // 「＋」菜单点外关闭
  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  const hintTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showHint = (text: string) => {
    setPasteHint(text);
    if (hintTimer.current) clearTimeout(hintTimer.current);
    hintTimer.current = setTimeout(() => setPasteHint(null), 3200);
  };

  const uploadingCount = chips.filter((chip) => chip.state === "uploading").length;
  const readyCount = chips.filter((chip) => chip.state === "ready").length;

  return (
    <div
      ref={rootRef}
      data-testid="bridge-material-bar"
      className="relative mx-2 mb-1 rounded-lg border border-border bg-background/60"
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy"; // 对拍 2：dragover copy 效果
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        // 对拍 2/43：drop 批量收集、逐件隔离上传；含目录时按 §3 批量白名单展开收集（对拍 30）
        void collectDroppedFiles(event.dataTransfer).then((files) => {
          if (files.length) onFiles(files);
        });
      }}
    >
      {chips.length > 0 && (
        <div className="flex flex-wrap items-start gap-2 px-2 pt-2" data-testid="bridge-material-chips">
          {chips.map((chip) => (
            <div
              key={chip.key}
              data-testid="bridge-material-chip"
              className="group relative flex max-w-56 items-center gap-2 rounded-md border border-border bg-muted/40 px-2 py-1.5"
              title={chip.filename}
            >
              {chip.isImage && chip.previewUrl ? (
                <img src={chip.previewUrl} alt="" className="h-8 w-8 rounded object-cover" />
              ) : (
                <FileText className="h-4 w-4 shrink-0 text-foreground-subtle" />
              )}
              <div className="min-w-0">
                <div className="truncate text-xs text-foreground">{chip.filename}</div>
                <div className="flex items-center gap-1 text-[10px] text-foreground-subtle">
                  <span className="rounded bg-muted px-1 py-px">{chip.badge}</span>
                  <span>{formatSize(chip.sizeBytes)}</span>
                  {chip.wasCompressed && <span>·已压缩</span>}
                  {/* 对拍 5/49：上传中转圈、无取消入口 */}
                  {chip.state === "uploading" && <Loader2 className="h-3 w-3 animate-spin" data-testid="bridge-material-busy" />}
                </div>
                {chip.state === "failed" && (
                  <div className="text-[11px] text-red-600 dark:text-red-400" data-testid="bridge-material-error">
                    {chip.errorMessage ?? "上传失败，请重试"}
                  </div>
                )}
              </div>
              {chip.state !== "uploading" && ( // 对拍 49：上传中不提供取消/移除
                <button
                  type="button"
                  aria-label="移除该材料"
                  data-testid="bridge-material-remove"
                  className="absolute -right-1.5 -top-1.5 hidden h-4 w-4 items-center justify-center rounded-full border border-border bg-background text-foreground-subtle group-hover:flex"
                  onClick={() => onRemove(chip.key)}
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center gap-1 px-2 py-1.5">
        <div className="relative">
          <button
            type="button"
            aria-label="添加材料"
            data-testid="bridge-material-add"
            className="flex h-7 w-7 items-center justify-center rounded-md text-foreground-subtle hover:bg-muted"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <Plus className="h-4 w-4" />
          </button>
          {menuOpen && (
            <div className="absolute bottom-8 left-0 z-20 rounded-md border border-border bg-background py-1 shadow-md">
              <button
                type="button"
                data-testid="bridge-material-menu-upload"
                className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-muted"
                onClick={() => {
                  setMenuOpen(false);
                  inputRef.current?.click(); // 对拍 1：菜单→系统选择器
                }}
              >
                <Paperclip className="h-3.5 w-3.5" /> 上传文件
              </button>
            </div>
          )}
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          data-testid="bridge-material-input"
          className="hidden"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            if (files.length) onFiles(files);
            event.currentTarget.value = ""; // 对拍 1：重置 input，同件可重复选
          }}
        />
        <div
          className="min-w-0 flex-1 select-none truncate text-xs text-foreground-subtle"
          tabIndex={0}
          data-testid="bridge-material-paste-zone"
          onPaste={(event) => {
            event.preventDefault(); // 对拍 3/4：本区分流粘贴，不进聊天输入框
            void onPaste(event.clipboardData);
          }}
        >
          {dragging
            ? "松开即上传到材料区"
            : pasteHint
              ? pasteHint
              : "可拖入或粘贴文件到本区（图片/文档），随消息一并发送"}
        </div>
        {hasInFlight && (
          <span className="whitespace-nowrap text-[11px] text-amber-600 dark:text-amber-400" data-testid="bridge-material-inflight-note">
            正在上传 {uploadingCount} 件材料，发送暂不可用
          </span>
        )}
        {!hasInFlight && readyCount > 0 && (
          <span className="whitespace-nowrap text-[11px] text-foreground-subtle">已就绪 {readyCount} 件</span>
        )}
        <button
          type="button"
          data-testid="bridge-material-files-entry"
          className="relative flex h-7 shrink-0 items-center gap-1 rounded-md px-2 text-xs text-foreground-subtle hover:bg-muted"
          onClick={() => setFilesOpen(true)}
        >
          对话文件
          {filesCount > 0 && (
            <span
              data-testid="bridge-material-files-badge"
              className="ml-0.5 rounded-full bg-muted px-1.5 text-[10px] text-foreground"
            >
              {filesCount > 99 ? "99+" : filesCount}
            </span>
          )}
        </button>
      </div>
      {sessionId && (
        <ThreadFilesPanel
          open={filesOpen}
          onClose={() => setFilesOpen(false)}
          sessionId={sessionId}
        />
      )}
    </div>
  );
}

function formatSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
