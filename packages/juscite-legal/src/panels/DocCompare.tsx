// 功能 #25 文档对比（施工单-03 任务四）：双栏对比 + 变更清单。
// 材料通道=桥 listWorkspaceDocuments/compareDocuments（workspace/materials 下纯文本材料，
// 即 #6 解析产物的文本形态）；增/删/改清单来自桥确定性行 diff；
// 分栏渲染复用树内 @pierre/diffs（DiffViewer，split 模式）。文案自写。
import { useCallback, useEffect, useState } from "react";
import { Columns2, RefreshCw } from "lucide-react";
import { DiffViewer } from "../ui-kit.js";
import { useServices } from "../ui-kit.js";

type DocHunk = {
  type: "add" | "del" | "mod";
  aStart: number; aCount: number;
  bStart: number; bCount: number;
  oldText: string; newText: string;
};

type CompareResult = {
  left: { name: string; text: string };
  right: { name: string; text: string };
  hunks: DocHunk[];
  stats: { added: number; deleted: number; modified: number; unchangedOld: number; unchangedNew: number };
};

const HUNK_BADGE: Record<DocHunk["type"], { label: string; cls: string }> = {
  add: { label: "增", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  del: { label: "删", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
  mod: { label: "改", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
};

export function DocCompare({ workspacePath }: { workspacePath?: string }) {
  const { zcodeAgentService } = useServices();
  const [documents, setDocuments] = useState<Array<{ name: string; kind: string }>>([]);
  const [leftName, setLeftName] = useState("");
  const [rightName, setRightName] = useState("");
  const [result, setResult] = useState<CompareResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshList = useCallback(() => {
    zcodeAgentService.listWorkspaceDocuments?.({ workspacePath: workspacePath ?? "" })
      .then((r) => {
        setDocuments((r?.documents ?? []).filter((d) => d.kind !== "word")); // Word 材料走红线改稿面板
        setLeftName((prev) => prev || r?.documents?.[0]?.name || "");
        setRightName((prev) => prev || r?.documents?.[1]?.name || "");
      })
      .catch((e: unknown) => setError(String((e as Error)?.message ?? e)));
  }, [zcodeAgentService, workspacePath]);

  useEffect(() => { refreshList(); }, [refreshList]);

  const runCompare = useCallback(() => {
    if (!leftName || !rightName || busy) return;
    setBusy(true);
    setError(null);
    zcodeAgentService.compareDocuments?.({ workspacePath: workspacePath ?? "", leftName, rightName })
      .then((r) => setResult(r ?? null))
      .catch((e: unknown) => { setError(String((e as Error)?.message ?? e)); setResult(null); })
      .finally(() => setBusy(false));
  }, [busy, leftName, rightName, workspacePath, zcodeAgentService]);

  return (
    <section data-testid="doc-compare" className="rounded-workspace-panel border border-border bg-header p-4">
      <h2 className="mb-2 flex items-center gap-2 text-ui-lg font-medium">
        <Columns2 className="size-4" /> 文档对比（双栏 + 变更清单）
      </h2>
      <p className="mb-3 text-ui-caption text-foreground-subtle">
        选两份文本材料（workspace/materials 目录）出对比：左=原版，右=新版；增/删/改逐条列示。
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select
          data-testid="doc-compare-left"
          value={leftName}
          onChange={(e) => setLeftName(e.target.value)}
          className="h-7 max-w-56 rounded border border-border bg-background px-2 text-ui-sm"
        >
          {!documents.length ? <option value="">（materials 目录为空）</option> : null}
          {documents.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
        </select>
        <span className="text-ui-caption text-foreground-subtle">对比</span>
        <select
          data-testid="doc-compare-right"
          value={rightName}
          onChange={(e) => setRightName(e.target.value)}
          className="h-7 max-w-56 rounded border border-border bg-background px-2 text-ui-sm"
        >
          {!documents.length ? <option value="">（materials 目录为空）</option> : null}
          {documents.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
        </select>
        <button
          type="button"
          data-testid="doc-compare-run"
          disabled={!leftName || !rightName || busy || leftName === rightName}
          onClick={runCompare}
          className="flex items-center gap-1 rounded border border-border px-3 py-1 text-ui-sm hover:bg-muted/60 disabled:opacity-50"
        >
          <RefreshCw className={`size-3.5 ${busy ? "animate-spin" : ""}`} /> 开始对比
        </button>
        <button
          type="button"
          onClick={refreshList}
          className="rounded px-2 py-1 text-ui-caption text-foreground-subtle hover:text-foreground"
        >
          刷新材料列表
        </button>
      </div>
      {error ? <p data-testid="doc-compare-error" className="mb-2 text-ui-sm text-red-500">{error}</p> : null}

      {result ? (
        <div className="flex flex-col gap-3">
          <div data-testid="doc-compare-stats" className="flex flex-wrap items-center gap-2 text-ui-sm">
            <span className="rounded bg-emerald-100 px-2 py-0.5 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">增 {result.stats.added} 处</span>
            <span className="rounded bg-red-100 px-2 py-0.5 text-red-700 dark:bg-red-950 dark:text-red-300">删 {result.stats.deleted} 处</span>
            <span className="rounded bg-amber-100 px-2 py-0.5 text-amber-700 dark:bg-amber-950 dark:text-amber-300">改 {result.stats.modified} 处</span>
            <span className="text-foreground-subtle">未变行 {result.stats.unchangedNew}</span>
          </div>

          <div data-testid="doc-compare-changes" className="max-h-64 overflow-auto rounded border border-border p-1">
            <div className="mb-1 px-1 text-ui-caption text-foreground-subtle">变更清单（{result.hunks.length} 条）</div>
            {result.hunks.length === 0 ? (
              <div className="px-2 py-3 text-center text-ui-sm text-foreground-subtle">两份材料内容一致，无变更</div>
            ) : result.hunks.map((h, i) => {
              const badge = HUNK_BADGE[h.type];
              const loc = h.type === "add"
                ? `右第 ${h.bStart + 1} 行起`
                : h.type === "del"
                  ? `左第 ${h.aStart + 1} 行起`
                  : `左第 ${h.aStart + 1} 行 → 右第 ${h.bStart + 1} 行`;
              return (
                <div key={i} className="rounded-md px-2 py-1.5 hover:bg-muted/50">
                  <div className="flex items-center gap-2">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${badge.cls}`}>{badge.label}</span>
                    <span className="text-[10px] text-foreground-subtle">{loc}</span>
                  </div>
                  {h.oldText ? (
                    <div className="mt-0.5 whitespace-pre-wrap text-xs leading-relaxed text-red-600 line-through dark:text-red-400">{h.oldText}</div>
                  ) : null}
                  {h.newText ? (
                    <div className="mt-0.5 whitespace-pre-wrap text-xs leading-relaxed text-emerald-700 dark:text-emerald-400">{h.newText}</div>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div data-testid="doc-compare-split" className="h-96 overflow-hidden rounded border border-border">
            <DiffViewer
              oldFile={{ name: result.left.name, contents: result.left.text }}
              newFile={{ name: result.right.name, contents: result.right.text }}
              options={{ diffStyle: "split" }}
            />
          </div>
        </div>
      ) : null}
    </section>
  );
}
