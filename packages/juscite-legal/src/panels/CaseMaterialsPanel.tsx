// 【功能 #6 材料上传解析】案件材料库面板（RE-6 §3 UI 落码；桥面 /api/cases/materials*）。
// 行为面（全部文案自写，表达隔离）：多选/拖拽上传→逐件状态（解析中/就绪/失败原因）+批次汇总；
// 版本号与被替代标记/标签/类型徽章；检索走桥 FTS5（只搜最新版）；不设删除/作废入口（对拍 47，
// 误传=同名重传新版本覆盖）；空库空态引导；检索无命中空结果（不报错）；案件缺失=稳定文案，
// 列表对缺失案件=空结果态（对拍 54）；上传进行中禁再次上传/检索（对拍 48 同源裁决：在途禁并发动作）。
import { useCallback, useEffect, useRef, useState } from "react";
import { FileText, FolderOpen, Search, Upload } from "lucide-react";
import { useServices } from "../ui-kit.js";
import { collectDroppedFiles } from "../ui-kit.js";

export interface MaterialItem {
  id: string; caseId: string; title: string; filename: string;
  version: number; supersedes: string | null; contentHash: string;
  mimeType: string; byteSize: number; documentType: string; documentSubtype: string;
  tags: string[]; status: "parsing" | "ready" | "failed";
  error: { code: string; message: string } | null;
  parse: { engine: string | null; durationMs: number | null; warnings: string[]; humanReview: boolean; pageCount: number | null; blockCount: number | null };
  semantic: { docType: string; docSubtype: string; chunkCount: number; entityCount: number };
  addedAt: string; updatedAt: string;
}
interface BoardCaseLite { id: string; name: string }

// 状态徽章（值单源=桥 case_materials.status 三态；展示词自写）
const STATUS_BADGE: Record<MaterialItem["status"], { label: string; cls: string }> = {
  parsing: { label: "解析中", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  ready: { label: "就绪", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  failed: { label: "失败", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
};

export function CaseMaterialsPanel() {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as { matterList?: () => Promise<{ cases: BoardCaseLite[] }> };
  const [cases, setCases] = useState<BoardCaseLite[]>([]);
  const [caseId, setCaseId] = useState<string>("");
  const [items, setItems] = useState<MaterialItem[]>([]);
  const [latestIds, setLatestIds] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false); // 上传/检索在途（对拍 48 同源裁决：在途禁并发动作）
  const [batchNote, setBatchNote] = useState<string>("");
  const [errorNote, setErrorNote] = useState<string>("");
  const [query, setQuery] = useState<string>("");
  const [hits, setHits] = useState<Array<{ materialId: string; materialTitle: string; chunkId?: string; title: string; text: string }> | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    svc.matterList?.().catch(() => ({ cases: [] })).then((r: { cases: BoardCaseLite[] }) => {
      if (!alive) return;
      setCases(r.cases ?? []);
      setCaseId((cur) => cur || r.cases?.[0]?.id || "");
    });
    return () => { alive = false; };
  }, [svc]);

  const refresh = useCallback(async (cid: string) => {
    if (!cid) { setItems([]); setLatestIds(new Set()); return; }
    try {
      const r = await fetch(`/api/cases/materials?caseId=${encodeURIComponent(cid)}`, { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const d = await r.json() as { items: MaterialItem[]; latest: MaterialItem[] };
      setItems(d.items ?? []);
      setLatestIds(new Set((d.latest ?? []).map((m) => m.id)));
      setErrorNote(""); // 列表对缺失案件=空结果态（对拍 54），不报错
    } catch {
      setErrorNote("材料列表读取失败，请确认桥在 3030 运行");
    }
  }, []);

  useEffect(() => { void refresh(caseId); }, [caseId, refresh]);

  const uploadFiles = useCallback(async (files: File[]) => {
    if (!files.length || !caseId || busy) return;
    setBusy(true);
    setErrorNote("");
    setBatchNote(`正在解析 ${files.length} 份材料…`);
    try {
      const fd = new FormData();
      fd.append("caseId", caseId);
      for (const f of files) fd.append("files", f, f.name);
      const r = await fetch("/api/cases/materials/upload", { method: "POST", body: fd });
      const d = await r.json().catch(() => null) as { items?: Array<{ status?: string; error?: { message?: string } }>; summary?: { ok: number; failed: number }; error?: { message?: string } } | null;
      if (!r.ok || !d) {
        // 案件缺失等稳定错误（对拍 54：404 类文案，不透传异常）
        setErrorNote(d?.error?.message ?? `上传失败（${r.status}）`);
        setBatchNote("");
        return;
      }
      const okN = d.summary?.ok ?? 0;
      const badN = d.summary?.failed ?? 0;
      setBatchNote(badN === 0 ? `已入库 ${okN} 份材料` : `已入库 ${okN} 份，${badN} 份失败（逐件独立，互不影响）`);
      await refresh(caseId);
    } catch {
      setErrorNote("上传失败：无法连接桥（3030）");
      setBatchNote("");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = ""; // 重置 input：同件可重复选择
    }
  }, [caseId, busy, refresh]);

  const runSearch = useCallback(async () => {
    if (!caseId || busy) return;
    const q = query.trim();
    if (!q) { setHits(null); return; }
    setBusy(true);
    setErrorNote("");
    try {
      const r = await fetch(`/api/cases/materials/search?caseId=${encodeURIComponent(caseId)}&q=${encodeURIComponent(q)}`, { cache: "no-store" });
      const d = await r.json().catch(() => null) as { hits?: Array<{ materialId: string; materialTitle: string; chunkId?: string; title: string; text: string }>; error?: { message?: string } } | null;
      if (!r.ok || !d) {
        setErrorNote(d?.error?.message ?? `检索失败（${r.status}）`);
        return;
      }
      setHits(d.hits ?? []);
    } catch {
      setErrorNote("检索失败：无法连接桥（3030）");
    } finally {
      setBusy(false);
    }
  }, [caseId, query, busy]);

  const dropFiles = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    // §3 批量：目录拖拽仅收白名单扩展名（对拍 30）；纯文件拖拽照旧、单件隔离+汇总
    void collectDroppedFiles(e.dataTransfer).then((files) => void uploadFiles(files));
  }, [uploadFiles]);

  const emptyLibrary = items.length === 0 && !busy;
  const currentCase = cases.find((c) => c.id === caseId);

  return (
    <section
      data-testid="case-materials"
      className="rounded-workspace-panel border border-border bg-header p-4"
      onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={dropFiles}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-ui-lg font-medium">案件材料库</h2>
        <span className="text-ui-caption text-foreground-subtle">材料解析入库 · 版本留痕 · 全文检索</span>
        <div className="ml-auto flex items-center gap-2">
          <select
            aria-label="选择案件"
            data-testid="case-materials-case"
            className="rounded border border-border bg-background px-2 py-1 text-ui-sm"
            value={caseId}
            onChange={(e) => { setCaseId(e.target.value); setHits(null); setBatchNote(""); }}
          >
            {cases.length === 0 ? <option value="">（暂无案件）</option> : null}
            {cases.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <button
            type="button"
            data-testid="case-materials-upload"
            className="flex items-center gap-1 rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!caseId || busy}
            onClick={() => fileRef.current?.click()}
          >
            <Upload className="size-3.5" /> 上传材料
          </button>
          <input
            ref={fileRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => void uploadFiles([...(e.target.files ?? [])])}
          />
        </div>
      </div>

      {dragOver ? (
        <p className="mb-2 rounded border border-dashed border-border px-3 py-2 text-ui-caption text-foreground-subtle">松开鼠标，把文件放入当前案件</p>
      ) : null}

      <div className="mb-3 flex items-center gap-2">
        <div className="flex flex-1 items-center gap-1 rounded border border-border bg-background px-2">
          <Search className="size-3.5 text-foreground-subtle" />
          <input
            data-testid="case-materials-search"
            className="w-full bg-transparent py-1 text-ui-sm outline-none"
            placeholder="在当前案件材料中检索关键词（只搜最新版本）"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void runSearch(); }}
            disabled={!caseId || busy}
          />
        </div>
        <button
          type="button"
          className="rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
          onClick={() => void runSearch()}
          disabled={!caseId || busy}
        >
          检索
        </button>
        {hits !== null ? (
          <button
            type="button"
            className="rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent"
            onClick={() => { setHits(null); setQuery(""); }}
          >
            清空检索
          </button>
        ) : null}
      </div>

      {busy ? <p data-testid="case-materials-busy" className="mb-2 text-ui-caption text-foreground-subtle">解析进行中，请稍候（上传完成前不能再次上传或检索）</p> : null}
      {batchNote ? <p data-testid="case-materials-batch" className="mb-2 text-ui-caption">{batchNote}</p> : null}
      {errorNote ? <p data-testid="case-materials-error" className="mb-2 text-ui-sm text-red-500">{errorNote}</p> : null}

      {hits !== null ? (
        hits.length === 0 ? (
          <p data-testid="case-materials-nohits" className="text-ui-caption text-foreground-subtle">没有命中「{query}」的段落。可换一个关键词，或清空检索返回材料列表。</p>
        ) : (
          <ul data-testid="case-materials-hits" className="mb-2 space-y-1">
            {hits.slice(0, 20).map((h, i) => (
              <li key={`${h.materialId}-${h.chunkId ?? i}`} className="rounded border border-border bg-background px-2 py-1 text-ui-sm">
                <span className="mr-1 rounded bg-accent px-1 text-ui-caption">{h.materialTitle}</span>
                {h.title ? <span className="mr-1 text-ui-caption text-foreground-subtle">{h.title}</span> : null}
                {h.text.length > 160 ? `${h.text.slice(0, 160)}…` : h.text}
              </li>
            ))}
          </ul>
        )
      ) : null}

      {emptyLibrary && !errorNote ? (
        <div data-testid="case-materials-empty" className="rounded border border-dashed border-border px-4 py-6 text-center">
          <FolderOpen className="mx-auto mb-2 size-6 text-foreground-subtle" />
          <p className="text-ui-sm">这个案件还没有材料。点击右上角「上传材料」，或把文件拖进来。</p>
          <p className="text-ui-caption text-foreground-subtle">支持 PDF / Word(docx) / 纯文本 / 图片；材料只在本机解析，不会外发。</p>
        </div>
      ) : null}

      {!emptyLibrary && hits === null ? (
        <ul data-testid="case-materials-list" className="space-y-1">
          {items.map((m) => {
            const badge = STATUS_BADGE[m.status] ?? STATUS_BADGE.parsing;
            const isLatest = latestIds.has(m.id);
            return (
              <li key={m.id} data-testid="case-materials-row" className="flex flex-wrap items-center gap-2 rounded border border-border bg-background px-2 py-1.5 text-ui-sm">
                <FileText className="size-4 shrink-0 text-foreground-subtle" />
                <span className="font-medium">{m.title}</span>
                <span className={`rounded px-1 text-ui-caption ${badge.cls}`}>{badge.label}</span>
                <span className="rounded bg-accent px-1 text-ui-caption">
                  {m.documentSubtype ? m.documentSubtype : m.documentType}
                </span>
                <span className="text-ui-caption text-foreground-subtle">v{m.version}{isLatest ? " · 最新" : " · 已被新版本替代"}</span>
                {m.tags.map((t) => (
                  <span key={t} className="rounded bg-accent px-1 text-ui-caption">#{t}</span>
                ))}
                <span className="ml-auto text-ui-caption text-foreground-subtle">
                  {m.status === "ready" ? `${m.semantic.chunkCount} 块 · ${m.semantic.entityCount} 实体` : ""}
                </span>
                {m.status === "failed" && m.error ? (
                  <span className="w-full text-ui-caption text-red-500">{m.error.message}</span>
                ) : null}
                {m.parse.warnings.length ? (
                  <span className="w-full text-ui-caption text-amber-600 dark:text-amber-400">{m.parse.warnings.join("；")}</span>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}

      {items.length > 0 ? (
        <p className="mt-2 text-ui-caption text-foreground-subtle">
          当前案件 {currentCase?.name ?? ""}：共 {items.length} 份材料（含历史版本）。传错的材料用同名文件重新上传即可覆盖为新版本；本面板不提供删除。
        </p>
      ) : null}
    </section>
  );
}
