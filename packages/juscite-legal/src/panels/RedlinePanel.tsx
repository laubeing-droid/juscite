// 功能 #11 Word 红线改稿（施工单-03 任务一）：改稿面板。
// 流转：材料（.docx/.txt/.md）+改稿要求 → 桥 redlineRevise（桥内走 oc28 会话通道出稿）→
// 修订项以红线样式呈现（删=红删除线，增=绿下划线）→ 律师逐条接受/拒绝 → 定稿落盘（桥写文件）。
// 记录落桥 SQLite（重启桥历史不丢）；隐身模式下出站被桥 fail-closed 拒绝。文案自写。
import { useCallback, useEffect, useRef, useState } from "react";
import { FilePenLine } from "lucide-react";
import { useServices } from "../ui-kit.js";

type RedlineItem = {
  itemIdx: number;
  type: "add" | "del" | "mod";
  aStart: number; aCount: number;
  bStart: number; bCount: number;
  oldText: string; newText: string;
  decision: "pending" | "accepted" | "rejected";
};

type RedlineRevision = {
  revisionId: string;
  materialName: string;
  instruction: string;
  status: "revising" | "ready" | "failed" | "finalized";
  originalText: string;
  revisedText: string;
  finalText: string | null;
  finalPath: string | null;
  error: string | null;
  createdAt: number;
  updatedAt: number;
};

type RedlineDetail = { revision: RedlineRevision; items: RedlineItem[] };

const ITEM_BADGE: Record<RedlineItem["type"], { label: string; cls: string }> = {
  add: { label: "增", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  del: { label: "删", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
  mod: { label: "改", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
};

const STATUS_LABEL: Record<RedlineRevision["status"], string> = {
  revising: "改稿中（模型出稿）",
  ready: "待终审",
  failed: "改稿失败",
  finalized: "已定稿",
};

export function RedlinePanel({ workspacePath }: { workspacePath?: string }) {
  const { zcodeAgentService } = useServices();
  const [documents, setDocuments] = useState<Array<{ name: string; kind: string }>>([]);
  const [materialName, setMaterialName] = useState("");
  const [instruction, setInstruction] = useState("");
  const [detail, setDetail] = useState<RedlineDetail | null>(null);
  const [history, setHistory] = useState<Array<{ revisionId: string; materialName: string; status: string; decidedCount: number; itemCount: number; createdAt: number }>>([]);
  const [starting, setStarting] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const svc = zcodeAgentService as {
    listWorkspaceDocuments?: (p: { workspacePath: string }) => Promise<{ documents: Array<{ name: string; kind: string }> }>;
    redlineRevise?: (p: { workspacePath: string; materialName: string; instruction: string }) => Promise<{ revisionId: string; status: string }>;
    redlineGet?: (p: { workspacePath: string; revisionId: string }) => Promise<RedlineDetail>;
    redlineList?: (p: { workspacePath: string }) => Promise<{ revisions: Array<{ revisionId: string; materialName: string; status: string; decidedCount: number; itemCount: number; createdAt: number }> }>;
    redlineDecide?: (p: { workspacePath: string; revisionId: string; itemIdx: number; decision: "accepted" | "rejected" | "pending" }) => Promise<RedlineDetail>;
    redlineFinalize?: (p: { workspacePath: string; revisionId: string }) => Promise<{ revisionId: string; status: string; finalPath: string }>;
  };

  const refreshList = useCallback(() => {
    svc.redlineList?.({ workspacePath: workspacePath ?? "" })
      .then((r) => setHistory(r?.revisions ?? []))
      .catch(() => {});
  }, [svc, workspacePath]);

  useEffect(() => {
    svc.listWorkspaceDocuments?.({ workspacePath: workspacePath ?? "" })
      .then((r) => {
        setDocuments(r?.documents ?? []);
        setMaterialName((prev) => prev || r?.documents?.[0]?.name || "");
      })
      .catch((e: unknown) => setError(String((e as Error)?.message ?? e)));
    refreshList();
    return () => { if (pollRef.current !== null) window.clearTimeout(pollRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const watchRevision = useCallback((revisionId: string) => {
    const tick = () => {
      svc.redlineGet?.({ workspacePath: workspacePath ?? "", revisionId })
        .then((d) => {
          setDetail(d);
          if (d?.revision?.status === "revising") {
            pollRef.current = window.setTimeout(tick, 1500);
          } else {
            refreshList();
          }
        })
        .catch((e: unknown) => { setError(String((e as Error)?.message ?? e)); setStarting(false); });
    };
    tick();
  }, [refreshList, svc, workspacePath]);

  const startRevise = useCallback(() => {
    if (!materialName || starting) return;
    setStarting(true);
    setError(null);
    svc.redlineRevise?.({ workspacePath: workspacePath ?? "", materialName, instruction: instruction.trim() })
      .then((r) => { setStarting(false); watchRevision(r.revisionId); })
      .catch((e: unknown) => { setStarting(false); setError(String((e as Error)?.message ?? e)); });
  }, [instruction, materialName, starting, svc, watchRevision, workspacePath]);

  const decide = useCallback((itemIdx: number, decision: "accepted" | "rejected" | "pending") => {
    if (!detail) return;
    svc.redlineDecide?.({ workspacePath: workspacePath ?? "", revisionId: detail.revision.revisionId, itemIdx, decision })
      .then(setDetail)
      .catch((e: unknown) => setError(String((e as Error)?.message ?? e)));
  }, [detail, svc, workspacePath]);

  const decideAll = useCallback((decision: "accepted" | "rejected") => {
    if (!detail) return;
    const pending = detail.items.filter((it) => it.decision === "pending");
    // 逐条顺序落决定（每条独立持久化）；量级为单文书条款数，串行即可
    (async () => {
      let d = detail;
      for (const it of pending) {
        try {
          const r = await svc.redlineDecide?.({ workspacePath: workspacePath ?? "", revisionId: d.revision.revisionId, itemIdx: it.itemIdx, decision });
          if (r) { d = r; setDetail(r); }
        } catch (e) {
          setError(String((e as Error)?.message ?? e));
          return;
        }
      }
    })();
  }, [detail, svc, workspacePath]);

  const finalize = useCallback(() => {
    if (!detail || finalizing) return;
    setFinalizing(true);
    setError(null);
    svc.redlineFinalize?.({ workspacePath: workspacePath ?? "", revisionId: detail.revision.revisionId })
      .then((r) => {
        setFinalizing(false);
        setDetail({ ...detail, revision: { ...detail.revision, status: "finalized", finalPath: r.finalPath } });
        refreshList();
      })
      .catch((e: unknown) => { setFinalizing(false); setError(String((e as Error)?.message ?? e)); });
  }, [detail, finalizing, refreshList, svc, workspacePath]);

  const openHistory = useCallback((revisionId: string) => {
    setError(null);
    svc.redlineGet?.({ workspacePath: workspacePath ?? "", revisionId })
      .then((d) => { if (d) { setDetail(d); setMaterialName(d.revision.materialName); } })
      .catch((e: unknown) => setError(String((e as Error)?.message ?? e)));
  }, [svc, workspacePath]);

  const revision = detail?.revision ?? null;
  const items = detail?.items ?? [];
  const decidedCount = items.filter((it) => it.decision !== "pending").length;
  const allDecided = items.length > 0 && decidedCount === items.length;

  return (
    <section data-testid="redline-panel" className="rounded-workspace-panel border border-border bg-header p-4">
      <h2 className="mb-2 flex items-center gap-2 text-ui-lg font-medium">
        <FilePenLine className="size-4" /> Word 红线改稿（AI 出稿 · 律师终审）
      </h2>
      <p className="mb-3 text-ui-caption text-foreground-subtle">
        选 Word/文本材料并写改稿要求：模型出稿以修订标记呈现（删=红色删除线，增=绿色下划线），
        逐条接受/拒绝后定稿落盘到 workspace/定稿/。隐身模式开启时改稿出站被拒绝。
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select
          data-testid="redline-material"
          value={materialName}
          onChange={(e) => setMaterialName(e.target.value)}
          className="h-7 max-w-60 rounded border border-border bg-background px-2 text-ui-sm"
        >
          {!documents.length ? <option value="">（materials 目录为空）</option> : null}
          {documents.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
        </select>
        <input
          data-testid="redline-instruction"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="改稿要求，如：利率不得超过 LPR 四倍，违约金改为日万分之三"
          className="h-7 min-w-72 flex-1 rounded border border-border bg-background px-2 text-ui-sm outline-none placeholder:text-muted-foreground/70"
        />
        <button
          type="button"
          data-testid="redline-start"
          disabled={!materialName || starting}
          onClick={startRevise}
          className="rounded border border-border px-3 py-1 text-ui-sm hover:bg-muted/60 disabled:opacity-50"
        >
          {starting ? "提交中…" : "开始改稿"}
        </button>
      </div>
      {error ? <p data-testid="redline-error" className="mb-2 text-ui-sm text-red-500">{error}</p> : null}

      {revision ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2 text-ui-sm">
            <span data-testid="redline-status" className="rounded bg-muted px-2 py-0.5">{STATUS_LABEL[revision.status]}</span>
            <span className="text-foreground-subtle">{revision.materialName} · 修订 {items.length} 条 · 已审 {decidedCount}</span>
            {items.length ? (
              <>
                <button type="button" data-testid="redline-accept-all" onClick={() => decideAll("accepted")} className="rounded border border-border px-2 py-0.5 hover:bg-muted/60">全部接受</button>
                <button type="button" data-testid="redline-reject-all" onClick={() => decideAll("rejected")} className="rounded border border-border px-2 py-0.5 hover:bg-muted/60">全部拒绝</button>
              </>
            ) : null}
            <button
              type="button"
              data-testid="redline-finalize"
              disabled={!allDecided || revision.status === "finalized" || finalizing}
              onClick={finalize}
              className="rounded border border-emerald-600/40 px-2 py-0.5 text-emerald-700 hover:bg-emerald-50 disabled:opacity-40 dark:text-emerald-400 dark:hover:bg-emerald-950"
            >
              定稿落盘
            </button>
          </div>
          {revision.status === "failed" && revision.error ? (
            <p className="text-ui-sm text-red-500">改稿失败：{revision.error}</p>
          ) : null}
          {revision.finalPath ? (
            <p data-testid="redline-path" className="text-ui-sm text-emerald-700 dark:text-emerald-400">定稿已写入：{revision.finalPath}</p>
          ) : null}
          <div data-testid="redline-items" className="flex max-h-96 flex-col gap-1 overflow-auto rounded border border-border p-1">
            {items.length === 0 && revision.status === "revising" ? (
              <div className="px-2 py-4 text-center text-ui-sm text-foreground-subtle">模型改稿中，出稿后此处逐条列示修订…</div>
            ) : null}
            {items.length === 0 && revision.status !== "revising" ? (
              <div className="px-2 py-4 text-center text-ui-sm text-foreground-subtle">本次改稿没有产生修订（原文与改稿一致）。</div>
            ) : null}
            {items.map((it) => {
              const badge = ITEM_BADGE[it.type];
              const loc = it.type === "add"
                ? `插入于原文第 ${it.aStart + 1} 行前`
                : it.type === "del"
                  ? `原文第 ${it.aStart + 1} 行起删除`
                  : `原文第 ${it.aStart + 1} 行`;
              return (
                <div key={it.itemIdx} className="rounded-md border border-border/60 px-2 py-1.5">
                  <div className="flex items-center gap-2">
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${badge.cls}`}>{badge.label}</span>
                    <span className="text-[10px] text-foreground-subtle">{loc}</span>
                    <span className="flex-1" />
                    <button
                      type="button"
                      data-testid={`redline-item-${it.itemIdx}-accept`}
                      onClick={() => decide(it.itemIdx, it.decision === "accepted" ? "pending" : "accepted")}
                      className={`rounded px-2 py-0.5 text-xs ${it.decision === "accepted" ? "bg-emerald-600 text-white" : "border border-border hover:bg-muted/60"}`}
                    >
                      接受
                    </button>
                    <button
                      type="button"
                      data-testid={`redline-item-${it.itemIdx}-reject`}
                      onClick={() => decide(it.itemIdx, it.decision === "rejected" ? "pending" : "rejected")}
                      className={`rounded px-2 py-0.5 text-xs ${it.decision === "rejected" ? "bg-red-600 text-white" : "border border-border hover:bg-muted/60"}`}
                    >
                      拒绝
                    </button>
                  </div>
                  {it.oldText ? (
                    <div className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-red-600 line-through dark:text-red-400">{it.oldText}</div>
                  ) : null}
                  {it.newText ? (
                    <div className="mt-0.5 whitespace-pre-wrap text-xs leading-relaxed text-emerald-700 underline decoration-emerald-500/60 underline-offset-2 dark:text-emerald-400">{it.newText}</div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {history.length ? (
        <div className="mt-3">
          <div className="mb-1 text-ui-caption text-foreground-subtle">改稿记录（桥库留存，重启不丢）</div>
          <div className="flex max-h-32 flex-col gap-0.5 overflow-auto">
            {history.map((h) => (
              <button
                key={h.revisionId}
                type="button"
                data-testid={`redline-history-${h.revisionId}`}
                onClick={() => openHistory(h.revisionId)}
                className="rounded px-2 py-1 text-left text-ui-sm hover:bg-muted/60"
              >
                {h.materialName} · {STATUS_LABEL[h.status as RedlineRevision["status"]] ?? h.status} · {h.decidedCount}/{h.itemCount} 已审
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
