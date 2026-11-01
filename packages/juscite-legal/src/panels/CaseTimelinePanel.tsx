// 【步骤4·#4 案件时间线】办案时间轴卡片节（RE-4-案件时间线.md 实现规格 §3 UI 结构）：
// 竖排 rail（左竖线+圆点+行悬停高亮）；主行=类型加粗+日期等宽、副行=备注灰字；开庭三态归一；
// 状态徽章六档+来源计数+点选展开详情；编辑模式内联三字段+逐字段↺+软删×+底部还原 chips
// （空态下照常渲染，D5a）；空态虚线框含双通道语义（抽取或业务动作后自动生成，文案自写）；
// 通道一抽取按钮确认制（对拍 39）+状态机（空态→生成中→已生成/失败+重试）+语料警告与忽略材料。
// 数据经桥 caseEvent* 桥面（⚠ 过渡数据面，随案件族翻牌）；文案全部自写（表达隔离）。
import { Component, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Clock, Eye, EyeOff, Pencil, RefreshCw, RotateCcw, X } from "lucide-react";
import { useServices } from "../ui-kit.js";
import {
  buildCaseTimelineReportLines, CASE_REPORT_EMPTY_TEXT, displayDateOf, hearingStatusText, todayStr,
  type CaseEventProto, type EditableField,
} from "../kernel/caseTimelineModel.js";
import { ChronicleSection } from "./ChronicleSection.js";

// 状态徽章六档（值单源在桥/模型 CASE_EVENT_STATUSES；展示词与配色自绘）
const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  confirmed: { label: "已证实", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  our_claim: { label: "我方主张", cls: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300" },
  opponent_claim: { label: "对方主张", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  disputed: { label: "有争议", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
  inferred: { label: "推断", cls: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300" },
  unknown: { label: "待核实", cls: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300" },
};
const IMPORTANCE_LABEL: Record<string, string> = { critical: "关键", normal: "普通", context: "背景" };

function lsGet(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}
function lsSet(key: string, v: string): void {
  try { window.localStorage.setItem(key, v); } catch { /* 隐私模式等静默 */ }
}
function ignoredListOf(matterId: string): string[] {
  try {
    const raw = JSON.parse(lsGet(`juscite.timeline.ignore.${matterId}`) ?? "[]");
    return Array.isArray(raw) ? raw.filter((x) => typeof x === "string") : [];
  } catch { return []; }
}

// 视图崩溃错误边界（对拍 38/D9）：渲染崩溃兜底"时间线数据仍然安全保留"语义；
// componentDidCatch 有意留空——错误内容（含案件内容/节点标题）不进任何遥测通道。
interface RailBoundaryState { error: Error | null }
class TimelineRailErrorBoundary extends Component<{ children: ReactNode }, RailBoundaryState> {
  state: RailBoundaryState = { error: null };
  static getDerivedStateFromError(error: unknown): RailBoundaryState {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }
  componentDidCatch(): void {
    // 故意留空（D9 隐私纪律：错误详情不外发，本产品亦无遥测通道）
  }
  render() {
    if (this.state.error) {
      return (
        <div className="rounded border border-dashed border-border p-4 text-center" data-testid="timeline-rail-error-boundary">
          <Clock className="mx-auto size-5 text-foreground-subtle" />
          <p className="mt-1 text-ui-sm font-medium">时间轴视图渲染出错</p>
          <p className="mt-0.5 text-ui-caption text-foreground-subtle">时间线数据仍然安全保留；可重试渲染，或切换案件后再回来。</p>
          <p className="mt-0.5 text-ui-caption text-foreground-subtle">{this.state.error.message}</p>
          <button type="button" data-testid="timeline-rail-boundary-retry" className="mt-2 rounded border border-border px-2 py-0.5 text-ui-caption"
            onClick={() => this.setState({ error: null })}>重试渲染</button>
        </div>
      );
    }
    return this.props.children;
  }
}

interface BoardCaseLite { id: string; name: string }
interface ExtractResult {
  inserted: number; updated: number; kept: number; total: number;
  corpus: string[]; ignoredCount: number; warnings: string[];
}

export function CaseTimelinePanel({ workspacePath }: { workspacePath?: string }) {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as {
    matterList?: () => Promise<{ cases: BoardCaseLite[] }>;
    caseEventList?: (p: Record<string, unknown>) => Promise<{ events: CaseEventProto[] }>;
    caseEventAllList?: () => Promise<{ events: CaseEventProto[] }>;
    caseEventDeletedList?: (p: { matterId: string }) => Promise<{ events: CaseEventProto[] }>;
    caseEventExtract?: (p: Record<string, unknown>) => Promise<ExtractResult>;
    caseEventEdit?: (p: Record<string, unknown>) => Promise<CaseEventProto>;
    caseEventEditRestore?: (p: { matterId: string; eventId: string; field: EditableField }) => Promise<CaseEventProto>;
    caseEventSoftDelete?: (p: { matterId: string; eventId: string }) => Promise<CaseEventProto>;
    caseEventRestore?: (p: { matterId: string; eventId: string }) => Promise<CaseEventProto>;
    // 工作汇报导出（对拍 35 = CB C12：服务端以库内现值重算 full 口径并装配 docx）
    caseEventReportExport?: (p: { matterId: string }) => Promise<{ docxBase64: string; fileName: string }>;
  };

  const [cases, setCases] = useState<BoardCaseLite[]>([]);
  const [matterId, setMatterId] = useState("");
  const [events, setEvents] = useState<CaseEventProto[]>([]);
  const [deleted, setDeleted] = useState<CaseEventProto[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [bridgeReady, setBridgeReady] = useState(true);
  const [extractPhase, setExtractPhase] = useState<"idle" | "loading" | "error">("idle");
  const [extractError, setExtractError] = useState<string | null>(null);
  const [extractInfo, setExtractInfo] = useState<ExtractResult | null>(null);
  const [ignored, setIgnored] = useState<string[]>([]);
  const [editMode, setEditMode] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<{ eventType: string; date: string; note: string }>({ eventType: "", date: "", note: "" });
  const [rowError, setRowError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [reportBusy, setReportBusy] = useState(false);
  const [reportNote, setReportNote] = useState<string | null>(null);
  const [cardHidden, setCardHidden] = useState(() => lsGet("juscite.timeline.hidden") === "1");
  const today = useMemo(() => todayStr(), []);

  useEffect(() => { setIgnored(ignoredListOf(matterId)); }, [matterId]);

  const reload = useCallback((mid: string) => {
    if (!svc.caseEventList) { setBridgeReady(false); return; }
    if (!mid) { setEvents([]); setDeleted([]); return; }
    Promise.all([
      svc.caseEventList({ matterId: mid, mode: "full" }),
      svc.caseEventDeletedList?.({ matterId: mid }).catch(() => ({ events: [] as CaseEventProto[] })),
    ])
      .then(([ev, del]) => {
        setEvents(ev?.events ?? []);
        setDeleted(del?.events ?? []);
        setLoadError(null);
        setBridgeReady(true);
      })
      .catch((e: unknown) => setLoadError(String((e as Error)?.message ?? e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    svc.matterList?.().catch(() => ({ cases: [] }))
      .then((r) => {
        const list = r?.cases ?? [];
        setCases(list);
        setMatterId((prev) => (prev && list.some((c) => c.id === prev) ? prev : list[0]?.id ?? ""));
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { reload(matterId); }, [matterId, reload]);

  const toggleIgnored = useCallback((name: string) => {
    setIgnored((prev) => {
      const next = prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name];
      lsSet(`juscite.timeline.ignore.${matterId}`, JSON.stringify(next));
      return next;
    });
  }, [matterId]);

  // 生成/刷新时间线（确认制，对拍 39；通道一状态机：loading→已生成/失败+重试）
  const runExtract = useCallback(() => {
    if (!matterId || extractPhase === "loading") return;
    if (!window.confirm("将从本案材料抽取时间线并合并入库：已有抽取结果只增改不删除，你手工改过的字段不会被覆盖。继续？")) return;
    setExtractPhase("loading");
    setExtractError(null);
    svc.caseEventExtract?.({ matterId, workspacePath: workspacePath || undefined, ignoredMaterials: ignored })
      .then((r) => {
        setExtractPhase("idle");
        setExtractInfo(r ?? null);
        reload(matterId);
      })
      .catch((e: unknown) => {
        setExtractPhase("error");
        setExtractError(String((e as Error)?.message ?? e));
      });
  }, [ignored, matterId, reload, svc, workspacePath, extractPhase]);

  const saveEdit = useCallback(() => {
    if (!editingId) return;
    svc.caseEventEdit?.({
      matterId, eventId: editingId,
      eventType: editDraft.eventType, date: editDraft.date || null, note: editDraft.note || null,
    })
      .then(() => { setEditingId(null); setRowError(null); reload(matterId); })
      .catch((e: unknown) => setRowError(String((e as Error)?.message ?? e)));
  }, [editDraft, editingId, matterId, reload, svc]);

  const restoreField = useCallback((eventId: string, field: EditableField) => {
    svc.caseEventEditRestore?.({ matterId, eventId, field })
      .then(() => { setRowError(null); reload(matterId); })
      .catch((e: unknown) => setRowError(String((e as Error)?.message ?? e)));
  }, [matterId, reload, svc]);

  const softDelete = useCallback((eventId: string) => {
    svc.caseEventSoftDelete?.({ matterId, eventId })
      .then(() => reload(matterId))
      .catch((e: unknown) => setRowError(String((e as Error)?.message ?? e)));
  }, [matterId, reload, svc]);

  const restoreRow = useCallback((eventId: string) => {
    svc.caseEventRestore?.({ matterId, eventId })
      .then(() => reload(matterId))
      .catch((e: unknown) => setRowError(String((e as Error)?.message ?? e)));
  }, [matterId, reload, svc]);

  // ── 工作汇报（对拍 35 = CB C12 等量，文案自写）：办案时间轴节预览+导出 Word ──
  // 预览/导出同源=full 口径 events（覆盖应用+软删滤+日期升序+业务次序表）；导出走桥
  // caseEventReportExport（服务端库内现值重算装配，客户端不传正文防两处口径漂移）。
  const caseName = cases.find((c) => c.id === matterId)?.name ?? matterId;
  const report = useMemo(() => buildCaseTimelineReportLines(events), [events]);
  const exportReport = useCallback(() => {
    if (!matterId || reportBusy || !svc.caseEventReportExport) return;
    setReportBusy(true);
    setReportNote(null);
    svc.caseEventReportExport({ matterId })
      .then((r) => {
        const blob = new Blob([Uint8Array.from(atob(r.docxBase64), (c) => c.charCodeAt(0))],
          { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = r.fileName; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 4000);
        setReportNote(`已导出：${r.fileName}（浏览器下载目录）`);
      })
      .catch((e: unknown) => setReportNote(`导出失败：${String((e as Error)?.message ?? e)}`))
      .finally(() => setReportBusy(false));
  }, [matterId, reportBusy, svc]);

  if (cardHidden) {
    return (
      <section data-testid="timeline-panel-hidden" className="rounded-workspace-panel border border-border bg-header p-3">
      <button type="button" className="inline-flex items-center gap-1 text-ui-sm text-foreground-subtle"
        onClick={() => { setCardHidden(false); lsSet("juscite.timeline.hidden", "0"); }}>
        <Eye className="size-4" /> 显示办案时间轴
      </button>
      </section>
    );
  }

  if (!bridgeReady) {
    return (
      <section data-testid="timeline-panel" className="rounded-workspace-panel border border-border bg-header p-4">
        <h2 className="mb-2 text-ui-lg font-medium">办案时间轴</h2>
        <p className="text-ui-sm text-foreground-subtle">桥面未提供时间线通道（caseEventList 不可用），时间轴面停用。</p>
      </section>
    );
  }

  return (
    <section data-testid="timeline-panel" className="rounded-workspace-panel border border-border bg-header p-4">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Clock className="size-5" />
        <h2 className="text-ui-lg font-medium">办案时间轴</h2>
        <select data-testid="timeline-case-select" className="max-w-[16rem] rounded border border-border px-1.5 py-0.5 text-ui-sm"
          value={matterId} onChange={(e) => { setMatterId(e.target.value); setEditingId(null); setExpandedId(null); }}>
          {!cases.length ? <option value="">（尚无案件）</option> : null}
          {cases.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        {matterId ? (
          <button type="button" data-testid="timeline-extract-btn" className="inline-flex items-center gap-1 rounded bg-selected px-2 py-1 text-ui-sm disabled:opacity-50"
            disabled={extractPhase === "loading"} onClick={runExtract}>
            <RefreshCw className={`size-4 ${extractPhase === "loading" ? "animate-spin" : ""}`} />
            {extractPhase === "loading" ? "正在抽取…" : (events.length ? "刷新时间线" : "生成时间轴")}
          </button>
        ) : null}
        <button type="button" data-testid="timeline-edit-toggle" aria-pressed={editMode}
          className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-ui-sm ${editMode ? "border-selected bg-selected/40" : "border-border"}`}
          onClick={() => { setEditMode(!editMode); setEditingId(null); setRowError(null); }}>
          <Pencil className="size-3.5" /> 编辑模式
        </button>
        <button type="button" aria-label="隐藏时间轴卡片" className="ml-auto rounded border border-border px-1.5 py-1"
          onClick={() => { setCardHidden(true); lsSet("juscite.timeline.hidden", "1"); }}>
          <EyeOff className="size-4" />
        </button>
      </div>
      <p className="mb-2 text-ui-caption text-foreground-subtle" data-testid="timeline-caption">
        时间轴为办案辅助整理：不构成法律意见或事实认定；有争议的节点应标注后核实。
      </p>
      {loadError ? <p className="mb-2 text-ui-sm text-red-500" data-testid="timeline-load-error">桥连接异常：{loadError}</p> : null}
      {extractPhase === "error" && extractError ? (
        <div className="mb-2 rounded border border-red-300 bg-red-50 p-2 text-ui-sm text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300" data-testid="timeline-extract-error">
          <p>时间线抽取失败：{extractError}</p>
          <button type="button" data-testid="timeline-extract-retry" className="mt-1 rounded border border-red-300 px-2 py-0.5 text-ui-caption" onClick={runExtract}>重试</button>
        </div>
      ) : null}
      {extractInfo ? (
        <p className="mb-2 text-ui-caption text-foreground-subtle" data-testid="timeline-extract-info">
          上次抽取：新增 {extractInfo.inserted} · 更新 {extractInfo.updated} · 保留 {extractInfo.kept}（语料 {extractInfo.corpus.length} 份
          {extractInfo.ignoredCount ? `，已忽略 ${extractInfo.ignoredCount} 份` : ""}）
        </p>
      ) : null}
      {extractInfo?.warnings?.length ? (
        <ul className="mb-2 rounded border border-amber-300 bg-amber-50 p-2 text-ui-caption text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300" data-testid="timeline-warnings">
          {extractInfo.warnings.map((w, i) => <li key={i}>· {w}</li>)}
        </ul>
      ) : null}
      {extractInfo?.corpus?.length ? (
        <div className="mb-2 flex flex-wrap items-center gap-1 text-ui-caption" data-testid="timeline-corpus">
          <span className="text-foreground-subtle">语料材料（点击切换是否参与下次抽取）：</span>
          {extractInfo.corpus.map((name) => {
            const off = ignored.includes(name);
            return (
              <button key={name} type="button" data-testid={`timeline-corpus-chip`}
                aria-pressed={!off} title={off ? "已忽略：点击恢复参与抽取" : "参与抽取：点击忽略"}
                className={`rounded px-1.5 py-0.5 ${off ? "border border-border text-foreground-subtle line-through" : "bg-selected text-foreground"}`}
                onClick={() => toggleIgnored(name)}>
                {name}
              </button>
            );
          })}
        </div>
      ) : null}

      {/* 竖排 rail（C1/C2）：左竖线+圆点+行悬停高亮；主行=类型加粗+日期等宽；副行=备注灰字；
          外包视图崩溃错误边界（对拍 38/D9：崩溃显"数据仍安全保留"，错误不进遥测） */}
      <TimelineRailErrorBoundary>
      <div className="relative" data-testid="timeline-rail">
        {events.length ? <div className="absolute bottom-2 left-[7px] top-2 w-px bg-border" data-testid="timeline-rail-line" /> : null}
        {events.map((ev) => {
          const dateView = displayDateOf(ev);
          const hearing = ev.eventType === "开庭" ? hearingStatusText(ev.date, today) : null;
          const isEditing = editMode && editingId === ev.eventId;
          const editable = ev.origin !== "auto";
          const refs = ev.sourceRefs ?? [];
          return (
            <div key={ev.eventId} data-testid="timeline-node"
              className="relative rounded px-1 py-1.5 pl-6 hover:bg-selected/20">
              <span className={`absolute left-0 top-2.5 size-3.5 rounded-full ring-2 ring-background ${
                ev.origin === "auto" ? "bg-emerald-500" : ev.origin === "user" ? "bg-amber-500" : "bg-blue-500"}`}
                title={ev.origin === "auto" ? "业务动作自动生成" : ev.origin === "user" ? "手工整理" : "材料抽取"} />
              {isEditing ? (
                <div className="flex flex-wrap items-center gap-1.5" data-testid="timeline-edit-row">
                  <input data-testid="timeline-edit-type" className="w-32 rounded border border-border px-1.5 py-0.5 text-ui-sm"
                    value={editDraft.eventType} onChange={(e) => setEditDraft({ ...editDraft, eventType: e.target.value })} aria-label="事件类型" />
                  <input data-testid="timeline-edit-date" type="date" className="rounded border border-border px-1.5 py-0.5 text-ui-sm"
                    value={editDraft.date} onChange={(e) => setEditDraft({ ...editDraft, date: e.target.value })} aria-label="日期" />
                  <input data-testid="timeline-edit-note" className="min-w-0 flex-1 rounded border border-border px-1.5 py-0.5 text-ui-sm"
                    value={editDraft.note} onChange={(e) => setEditDraft({ ...editDraft, note: e.target.value })} aria-label="备注" placeholder="备注" />
                  <button type="button" data-testid="timeline-edit-save" className="rounded bg-selected px-2 py-0.5 text-ui-caption" onClick={saveEdit}>保存</button>
                  <button type="button" className="rounded border border-border px-2 py-0.5 text-ui-caption" onClick={() => { setEditingId(null); setRowError(null); }}>取消</button>
                </div>
              ) : (
                <>
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <button type="button" data-testid="timeline-node-main" className="text-left"
                      onClick={() => setExpandedId(expandedId === ev.eventId ? null : ev.eventId)}>
                      <span className="font-medium">{ev.eventType}</span>
                    </button>
                    <span className={`rounded px-1 text-ui-caption ${STATUS_BADGE[ev.status]?.cls ?? ""}`} data-testid="timeline-node-status">
                      {STATUS_BADGE[ev.status]?.label ?? ev.status}
                    </span>
                    {hearing ? <span className="font-mono text-ui-caption text-foreground-subtle" data-testid="timeline-node-hearing">{hearing}</span> : null}
                    <span className="font-mono text-ui-caption text-foreground-subtle" data-testid="timeline-node-date">{dateView.text}</span>
                    {ev.importance === "critical" ? <span className="rounded bg-red-100 px-1 text-ui-caption text-red-700 dark:bg-red-950 dark:text-red-300">关键</span> : null}
                    <button type="button" className="text-ui-caption text-foreground-subtle hover:underline" data-testid="timeline-node-refs"
                      onClick={() => setExpandedId(expandedId === ev.eventId ? null : ev.eventId)}>
                      {refs.length ? `${refs.length} 项材料依据` : "未绑定材料"}
                    </button>
                    {editMode ? (
                      editable ? (
                        <span className="ml-auto flex gap-1">
                          <button type="button" aria-label="编辑节点" className="rounded border border-border px-1 py-0.5"
                            onClick={() => { setEditingId(ev.eventId); setEditDraft({ eventType: ev.eventType, date: ev.date ?? "", note: ev.note ?? "" }); setRowError(null); }}>
                            <Pencil className="size-3" />
                          </button>
                          <button type="button" data-testid={`timeline-node-del-${ev.eventId}`} aria-label="隐藏节点（只删显示不删数据）"
                            title="隐藏节点（只删显示，可从还原条恢复）" className="rounded border border-border px-1 py-0.5"
                            onClick={() => softDelete(ev.eventId)}>
                            <X className="size-3" />
                          </button>
                        </span>
                      ) : (
                        <span className="ml-auto flex items-center gap-1">
                          <span className="rounded bg-emerald-100 px-1 text-ui-caption text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">业务动作生成</span>
                          <button type="button" data-testid={`timeline-node-del-${ev.eventId}`} aria-label="隐藏节点（只删显示不删数据）"
                            title="业务动作事件不可改字段值，只能隐藏" className="rounded border border-border px-1 py-0.5"
                            onClick={() => softDelete(ev.eventId)}>
                            <X className="size-3" />
                          </button>
                        </span>
                      )
                    ) : null}
                  </div>
                  {ev.note ? <div className="mt-0.5 text-ui-sm text-foreground-subtle" data-testid="timeline-node-note">{ev.note}</div> : null}
                  {expandedId === ev.eventId ? (
                    <div className="mt-1 rounded border border-border p-2 text-ui-caption" data-testid="timeline-node-detail">
                      <div>精度：{dateView.precision === "exact" ? "日期明确" : dateView.precision === "range" ? "日期范围" : "待核对"}
                        ｜重要度：{IMPORTANCE_LABEL[ev.importance] ?? ev.importance}
                        ｜来源：{ev.provenance === "system" ? "系统动作" : ev.provenance === "user" ? "人工" : "抽取"}</div>
                      {ev.phase ? <div>阶段：{ev.phase}</div> : null}
                      {ev.side ? <div>立场：{ev.side}</div> : null}
                      {ev.expiresAt ? <div>到期日：{ev.expiresAt}</div> : null}
                      {ev.payload?.subjects?.length ? <div>涉及主体：{ev.payload.subjects.join("、")}</div> : null}
                      {ev.payload?.behavior_nature ? <div>行为性质：{ev.payload.behavior_nature}</div> : null}
                      {ev.payload?.amount_text ? <div>涉及金额（原文）：{ev.payload.amount_text}</div> : null}
                      {ev.payload?.dispute_note ? <div>争议说明：{ev.payload.dispute_note}</div> : null}
                      {typeof ev.payload?.confidence === "number" ? <div>置信度：{Math.round(ev.payload.confidence * 100)}%（抽取自评，供复核排序参考）</div> : null}
                      {ev.origin === "llm_extract" && !refs.some((r) => r.filename && r.locator) ? (
                        <div className="mt-0.5 text-amber-700 dark:text-amber-300">⚠ 本节点缺（材料名+页码/段落）双引用出处，待补核</div>
                      ) : null}
                      {refs.length ? (
                        <div className="mt-1">
                          <div>材料依据：</div>
                          <ul className="ml-2 list-disc">
                            {refs.map((r, i) => (
                              <li key={i}>{r.filename}{r.locator ? ` · ${r.locator}` : ""}{r.quote ? `：「${r.quote}」` : ""}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      {editMode && ev.lockedFields.length ? (
                        <div className="mt-1 flex items-center gap-1">
                          <span>已覆盖字段：</span>
                          {ev.lockedFields.map((f) => (
                            <button key={f} type="button" data-testid={`timeline-node-restore-${f}`}
                              title="恢复到抽取原值" className="inline-flex items-center gap-0.5 rounded border border-border px-1 py-0.5"
                              onClick={() => restoreField(ev.eventId, f as EditableField)}>
                              <RotateCcw className="size-3" /> {f === "eventType" ? "类型" : f === "date" ? "日期" : "备注"}
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </>
              )}
            </div>
          );
        })}

        {/* 空态虚线框（对拍 28 结构、文案自写，含双通道语义） */}
        {!events.length ? (
          <div className="rounded border border-dashed border-border p-4 text-center" data-testid="timeline-empty">
            <Clock className="mx-auto size-5 text-foreground-subtle" />
            <p className="mt-1 text-ui-sm">该案还没有时间轴节点</p>
            <p className="text-ui-caption text-foreground-subtle">
              点上方「生成时间轴」从材料抽取，或办理业务动作（建案/排期开庭/登记期限/新增任务）后在此自动生成
            </p>
          </div>
        ) : null}
        {rowError ? <p className="mt-1 text-ui-caption text-red-500" data-testid="timeline-row-error">{rowError}</p> : null}
      </div>
      </TimelineRailErrorBoundary>

      {/* 工作汇报（对拍 35 = CB C12 等量，文案自写）：办案时间轴节——每条「日期（加粗）：事件 — 备注」，
          无日期/无事件逐项兜底、空表整句（兜底词在模型单源）；导出 Word 与预览同源 */}
      <div className="mt-3 rounded border border-border p-2" data-testid="timeline-report">
        <div className="flex items-center gap-2">
          <h3 className="text-ui-sm font-medium">工作汇报</h3>
          <span className="text-ui-caption text-foreground-subtle">办案时间轴节随汇报导出（docx）</span>
          <button type="button" data-testid="timeline-report-export"
            className="ml-auto rounded border border-border px-2 py-0.5 text-ui-caption disabled:opacity-50"
            disabled={reportBusy || !matterId || !svc.caseEventReportExport} onClick={exportReport}>
            {reportBusy ? "正在导出…" : "导出 Word"}
          </button>
        </div>
        {report.empty ? (
          <p className="mt-1 text-ui-caption text-foreground-subtle" data-testid="timeline-report-empty">{CASE_REPORT_EMPTY_TEXT}</p>
        ) : (
          <ul className="mt-1 space-y-0.5" data-testid="timeline-report-lines">
            {report.lines.map((l, i) => (
              <li key={i} className="text-ui-sm" data-testid="timeline-report-line">
                <span className="font-medium">{l.dateText}</span>：{l.eventText}
                {l.noteText ? <span className="text-foreground-subtle"> — {l.noteText}</span> : null}
              </li>
            ))}
          </ul>
        )}
        {reportNote ? <p className="mt-1 text-ui-caption text-foreground-subtle" data-testid="timeline-report-note">{reportNote}</p> : null}
      </div>

      {/* 施工波二轮·可视化B轨 UI 件：大事记入口（投影→摄入对账→桥面守卫→四件同源交付预览/下载；
          判定全在桥面 @juscite/vizb，面板零判据零渲染） */}
      <ChronicleSection events={events} caseName={caseName} workspacePath={workspacePath} ignored={ignored} />

      {/* 还原 chips（D5/D5a：非空态在列表底、空态在空态框下照常渲染） */}
      {deleted.length ? (
        <div className="mt-2 flex flex-wrap items-center gap-1" data-testid="timeline-restore-chips">
          <span className="text-ui-caption text-foreground-subtle">已隐藏节点，点击还原：</span>
          {deleted.map((ev) => (
            <button key={ev.eventId} type="button" data-testid={`timeline-chip-${ev.eventId}`}
              className="rounded border border-border px-1.5 py-0.5 text-ui-caption hover:bg-selected/30"
              onClick={() => restoreRow(ev.eventId)}>
              {ev.eventType}{ev.date ? ` · ${ev.date.slice(5)}` : ""}
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}
