// 【功能 #6 材料上传解析】对话输入框附件区状态钩子（RE-6 §3 UI 结构 + 状态机裁决）。
// 行为锚点：多选逐个上传、单件失败隔离（对拍 43）；同 id（同内容）去重（对拍 7）；
// 图片上传前压缩+textFallback（对拍 6）；粘贴分流（对拍 3/4）；上传中无取消入口（对拍 49）；
// 存在上传中附件时发送禁用（对拍 48 裁决，由宿主把 hasInFlight 接到发送闸）。
// 草稿会话（sessionId=null）先落附件库（无作用域：HTTP 读回按桥面 fail-closed 403，
// 桥内回合注入按 id 命中——不复制竞品「双空=公开可读」缺陷，见对拍 9 收窄裁决）。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { nanoid } from "nanoid";
import {
  attachmentKindLabel,
  attachmentKindOf,
  listBridgeMaterialAttachments,
  planPasteIngest,
  uploadBridgeMaterialAttachment,
  type MaterialAttachmentKind,
} from "@/lib/bridgeMaterialAttachments.js";
import {
  compressImageForUpload,
  makeImageTextFallback,
} from "@/lib/materialImageCompress.js";

export interface BridgeMaterialChip {
  key: string;
  /** ready 后为 att_* 内容寻址 id；uploading/failed 期为 null。 */
  attachmentId: string | null;
  /** 图片 textFallback 副本的附件 id（随发送一并注入，不单独出芯片）。 */
  fallbackAttachmentId: string | null;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  isImage: boolean;
  badge: string;
  previewUrl: string | null;
  wasCompressed: boolean;
  state: "uploading" | "ready" | "failed";
  errorMessage: string | null;
}

export interface BridgeMaterialAttachmentsApi {
  chips: BridgeMaterialChip[];
  hasInFlight: boolean;
  /** 发送时随 payload.attachmentIds 上行的全部 id（主件+副本，ready 态）。 */
  attachmentIds: string[];
  readyCount: number;
  /** 本会话在桥附件库的文件总数（对话文件面板入口徽标；上传就绪后自动刷新）。 */
  libraryCount: number;
  addFiles: (files: File[]) => Promise<void>;
  /** 返回分流结果供提示；long-text 已内部转为「粘贴内容.txt」附件进入 addFiles。 */
  ingestPaste: (dataTransfer: DataTransfer) => Promise<"files" | "long-text" | "none">;
  removeChip: (key: string) => void;
  reset: () => void;
}

const PASTE_TEXT_FILENAME = "粘贴内容.txt";

export function useBridgeMaterialAttachments(options: { sessionId: string | null }): BridgeMaterialAttachmentsApi {
  const { sessionId } = options;
  const [chips, setChips] = useState<BridgeMaterialChip[]>([]);
  const chipsRef = useRef<BridgeMaterialChip[]>([]);
  chipsRef.current = chips;
  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;
  // 串行化并发 addFiles（拖拽/粘贴/菜单同帧多入口）：按 promise 链排队，逐件上传。
  const queueRef = useRef<Promise<void>>(Promise.resolve());

  const updateChip = useCallback((key: string, patch: Partial<BridgeMaterialChip>) => {
    setChips((current) => current.map((chip) => (chip.key === key ? { ...chip, ...patch } : chip)));
  }, []);

  const uploadOne = useCallback(
    async (file: File): Promise<{ mainId: string; fallbackId: string | null; sizeBytes: number; mimeType: string; wasCompressed: boolean }> => {
      const key = nanoid();
      const kind: MaterialAttachmentKind = attachmentKindOf(file.name, file.type);
      const isImage = kind === "image";
      let blob: Blob = file;
      let mimeType = file.type || "application/octet-stream";
      let wasCompressed = false;
      let previewUrl: string | null = null;
      if (isImage) {
        const outcome = await compressImageForUpload(file); // 对拍 6：超限才逐级压缩
        if (outcome) {
          blob = outcome.blob;
          mimeType = outcome.mimeType;
          wasCompressed = outcome.wasCompressed;
        }
        previewUrl = URL.createObjectURL(blob);
      }
      setChips((current) => [
        ...current,
        {
          key,
          attachmentId: null,
          fallbackAttachmentId: null,
          filename: file.name,
          mimeType,
          sizeBytes: blob.size,
          isImage,
          badge: attachmentKindLabel(isImage ? "image" : kind),
          previewUrl,
          wasCompressed,
          state: "uploading",
          errorMessage: null,
        },
      ]);
      const scope = { threadIds: sessionIdRef.current ? [sessionIdRef.current] : [] };
      try {
        const main = await uploadBridgeMaterialAttachment({
          bytes: new Uint8Array(await blob.arrayBuffer()),
          filename: file.name,
          mimeType,
          ...scope,
        });
        let fallbackId: string | null = null;
        if (isImage) {
          const fallback = await makeImageTextFallback(blob); // 对拍 6：textFallback 副本供文本模型
          if (fallback && fallback !== blob) {
            try {
              const stem = file.name.replace(/\.[^.]+$/, "") || file.name;
              const fb = await uploadBridgeMaterialAttachment({
                bytes: new Uint8Array(await fallback.arrayBuffer()),
                filename: `${stem}.文本回退.jpg`,
                mimeType: "image/jpeg",
                ...scope,
              });
              fallbackId = fb.attachmentId;
            } catch {
              // 副本失败不阻塞主件（主件已就绪）
            }
          }
        }
        // 对拍 7 UI 面（§2.1 条 9/§3 UI「同 id 去重」）：同内容（同 att id）重复上传合并进
        // 已有芯片、不重复进列表；后到芯片回收（含其预览 URL），textFallback 副本 id 并入已有芯片。
        setChips((current) => {
          const dupe = current.find((chip) => chip.key !== key && chip.attachmentId === main.attachmentId && chip.state === "ready");
          if (dupe) {
            if (previewUrl) URL.revokeObjectURL(previewUrl);
            return current
              .filter((chip) => chip.key !== key)
              .map((chip) =>
                chip.key === dupe.key ? { ...chip, fallbackAttachmentId: chip.fallbackAttachmentId ?? fallbackId } : chip,
              );
          }
          return current.map((chip) =>
            chip.key === key
              ? { ...chip, attachmentId: main.attachmentId, fallbackAttachmentId: fallbackId, sizeBytes: main.byteSize, state: "ready" as const }
              : chip,
          );
        });
        return { mainId: main.attachmentId, fallbackId, sizeBytes: main.byteSize, mimeType, wasCompressed };
      } catch (error) {
        updateChip(key, {
          state: "failed",
          errorMessage: error instanceof Error ? error.message : "上传失败，请重试",
        });
        throw error;
      }
    },
    [updateChip],
  );

  const addFiles = useCallback(
    (files: File[]) => {
      const list = files.filter((file) => file instanceof File);
      if (!list.length) return Promise.resolve();
      const task = queueRef.current.then(async () => {
        // 单件隔离（对拍 43）：一件失败不中断其余
        for (const file of list) {
          try {
            await uploadOne(file);
          } catch {
            // 失败已落芯片错误红字；继续下一件
          }
        }
      });
      queueRef.current = task.then(
        () => undefined,
        () => undefined,
      );
      return task;
    },
    [uploadOne],
  );

  const ingestPaste = useCallback(
    async (dataTransfer: DataTransfer): Promise<"files" | "long-text" | "none"> => {
      const files = Array.from(dataTransfer.files ?? []);
      const text = dataTransfer.getData("text/plain") ?? "";
      const plan = planPasteIngest({ files, text }); // 对拍 3/4：长文本优先、图片随行丢弃
      if (plan.kind === "long-text") {
        await addFiles([new File([plan.text], PASTE_TEXT_FILENAME, { type: "text/plain" })]);
        return "long-text";
      }
      if (plan.kind === "files") {
        await addFiles(files);
        return "files";
      }
      return "none";
    },
    [addFiles],
  );

  const removeChip = useCallback((key: string) => {
    setChips((current) => {
      const target = current.find((chip) => chip.key === key);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return current.filter((chip) => chip.key !== key);
    });
  }, []);

  const reset = useCallback(() => {
    setChips((current) => {
      for (const chip of current) {
        if (chip.previewUrl) URL.revokeObjectURL(chip.previewUrl);
      }
      return [];
    });
  }, []);

  // 卸载时回收缩略图 objectURL（防泄漏；对齐既有附件区 revoke 纪律）
  useEffect(() => {
    return () => {
      for (const chip of chipsRef.current) {
        if (chip.previewUrl) URL.revokeObjectURL(chip.previewUrl);
      }
    };
  }, []);

  const hasInFlight = useMemo(() => chips.some((chip) => chip.state === "uploading"), [chips]);
  const attachmentIds = useMemo(() => {
    const ids: string[] = [];
    for (const chip of chips) {
      if (chip.state === "ready" && chip.attachmentId) ids.push(chip.attachmentId);
      if (chip.state === "ready" && chip.fallbackAttachmentId) ids.push(chip.fallbackAttachmentId);
    }
    return ids.slice(0, 64);
  }, [chips]);
  const readyCount = useMemo(() => chips.filter((chip) => chip.state === "ready").length, [chips]);

  // 会话附件库总数（对话文件入口徽标）：换会话或本批上传就绪后刷新
  const [libraryCount, setLibraryCount] = useState(0);
  useEffect(() => {
    if (!sessionId) {
      setLibraryCount(0);
      return;
    }
    let alive = true;
    listBridgeMaterialAttachments({ threadId: sessionId })
      .then((items) => {
        if (alive) setLibraryCount(items.length);
      })
      .catch(() => {
        // 列表读取失败徽标保持原值；面板打开时会重读并显式报错
      });
    return () => {
      alive = false;
    };
  }, [sessionId, readyCount]);

  return { chips, hasInFlight, attachmentIds, readyCount, libraryCount, addFiles, ingestPaste, removeChip, reset };
}
