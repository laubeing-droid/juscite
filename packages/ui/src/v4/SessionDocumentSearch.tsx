// 功能 #15 案内文档全文搜入口（RE-15）：会话面板右上角浮动搜索。
// 查询走桥 searchSessionDocuments（SQLite FTS5 trigram，短词/零命中回落 LIKE 子串）；
// 命中=完成 chunk（用户输入/助手回复）片段+来源标签。合成桥面板，文案自写。
import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { useServices } from "@/hooks/useServices.js";

interface DocumentHit {
  chunkId: string;
  kind: string;
  sourceLabel: string;
  text: string;
  createdAt: number;
}

export function SessionDocumentSearch({ sessionId, workspacePath }: {
  sessionId: string | null;
  workspacePath: string;
}) {
  const { zcodeAgentService } = useServices();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<DocumentHit[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");

  useEffect(() => {
    if (!open || !sessionId) return;
    const q = query.trim();
    if (q.length < 2) { setHits([]); setStatus("idle"); return; }
    setStatus("loading");
    const timer = setTimeout(() => {
      void zcodeAgentService
        .searchSessionDocuments?.({ workspacePath, sessionId, query: q, limit: 8 })
        .then((r) => { setHits(r?.results ?? []); setStatus("done"); })
        .catch(() => { setHits([]); setStatus("done"); });
    }, 250);
    return () => clearTimeout(timer);
  }, [open, query, sessionId, workspacePath, zcodeAgentService]);

  if (!sessionId) return null;
  return (
    <div className="absolute right-3 top-3 z-40 flex flex-col items-end gap-2">
      <div className="flex items-center gap-1">
        {!open ? (
          <button
            type="button"
            data-testid="document-search-toggle"
            onClick={() => setOpen(true)}
            title="案内文档搜索"
            className="flex size-7 items-center justify-center rounded-md border border-border bg-background/85 text-muted-foreground shadow-sm transition hover:text-foreground"
          >
            <Search className="size-3.5" />
          </button>
        ) : (
          <div className="flex items-center gap-1 rounded-lg border border-border bg-background/95 px-2 py-1 shadow-sm backdrop-blur">
            <Search className="size-3.5 text-muted-foreground" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="案内全文搜索（≥2 字）"
              data-testid="document-search-input"
              className="h-6 w-52 bg-transparent text-xs text-foreground outline-none placeholder:text-muted-foreground/70"
            />
            <button
              type="button"
              onClick={() => { setOpen(false); setQuery(""); setHits([]); }}
              className="text-muted-foreground transition hover:text-foreground"
              title="关闭"
            >
              <X className="size-3.5" />
            </button>
          </div>
        )}
      </div>
      {open && query.trim().length >= 2 ? (
        <div
          data-testid="document-search-results"
          className="max-h-72 w-80 overflow-auto rounded-lg border border-border bg-background/95 p-1 shadow-md backdrop-blur"
        >
          {status === "loading" ? (
            <div className="px-2 py-3 text-center text-xs text-muted-foreground">检索中…</div>
          ) : hits.length === 0 ? (
            <div className="px-2 py-3 text-center text-xs text-muted-foreground">本案无命中</div>
          ) : (
            hits.map((h) => {
              const q = query.trim();
              const at = h.text.indexOf(q);
              const snippet = at >= 0
                ? `${at > 24 ? "…" : ""}${h.text.slice(Math.max(0, at - 24), at + q.length + 60)}${h.text.length > at + q.length + 60 ? "…" : ""}`
                : `${h.text.slice(0, 90)}${h.text.length > 90 ? "…" : ""}`;
              return (
                <div key={h.chunkId} className="rounded-md px-2 py-1.5 hover:bg-muted/60">
                  <div className="flex items-center justify-between gap-2 text-[10px] text-muted-foreground">
                    <span className={h.kind === "userInput" ? "text-sky-600 dark:text-sky-400" : "text-emerald-600 dark:text-emerald-400"}>
                      {h.kind === "userInput" ? "用户输入" : "助手回复"}
                    </span>
                    <span className="truncate">{h.sourceLabel}</span>
                  </div>
                  <div className="mt-0.5 text-xs leading-relaxed text-foreground">{snippet}</div>
                </div>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}
