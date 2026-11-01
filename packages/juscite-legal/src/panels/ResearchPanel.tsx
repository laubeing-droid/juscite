// 【步骤4·#16 调研报告】调研工作区面板（RE-16-调研报告.md §3 UI 结构；行为锚点按 B 编号标注）。
// 布局=左历史栏+主列（页头/搜索条/提示行/[法规库提示条]/[报告管理条]/滚动结果区）；结果卡序=
// 课题卡→实时状态条（running 吸顶）→调研规划卡→阶段播报卡→调研总结卡→错误条。
// 数据经桥 research* 桥面（researchRun/researchThreadState/researchRecord*，走 M4 回合链轮询投影，
// B36 对账同源）；派生字段（规划/阶段/报告三桶）由桥侧共享纯模型单源产出，本面板只做编排与呈现。
// 文案全部自写（表达隔离）；视觉自绘（徽章三态色/思考球自绘，§3「我们落地」节）。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle, AlertTriangle, BookOpen, CheckCircle2, Download, FileCheck, FileText, Globe, Loader2, Pencil, Scale, Search, Square, Telescope, Trash2, Wrench, X,
} from "lucide-react";
import { useServices } from "../ui-kit.js";
import {
  durationFormat, orbStateOf, extractStageNo, STEP_ERROR_TEXT,
  type ResearchRecord, type ResearchUpdate, type ResearchStep, type StepIconKind,
} from "../kernel/researchModel.js";

type ResearchSvc = {
  researchStatus?: () => Promise<{ lawsAvailable: boolean; stealth: boolean; primaryLegalSource: string | null }>;
  researchRun?: (p: { query: string; model?: { providerId: string; modelId: string } | null }) => Promise<{ record: ResearchRecord; threadId: string }>;
  researchThreadState?: (p: { threadId: string }) => Promise<ThreadState>;
  researchRecordGet?: (p: { id: string }) => Promise<ResearchRecord | null>;
  researchRecordList?: () => Promise<{ records: ResearchRecord[] }>;
  researchRecordSave?: (p: { record: ResearchRecord }) => Promise<{ record: ResearchRecord }>;
  researchRecordEdit?: (p: { id: string; summary: string }) => Promise<{ record: ResearchRecord }>;
  researchRecordFail?: (p: { id: string; message: string }) => Promise<ResearchRecord | null>;
  researchRecordDelete?: (p: { id: string }) => Promise<{ deleted: string }>;
  researchClearRecords?: () => Promise<{ cleared: boolean }>;
  researchStop?: (p: { id: string }) => Promise<{ record: ResearchRecord }>;
  researchExportWord?: (p: { markdown: string; query: string }) => Promise<{ docxBase64: string; fileName: string; mode: string }>;
  researchExportMd?: (p: { markdown: string; query: string }) => Promise<{ text: string; fileName: string }>;
  modelSelectionService?: { getView: () => Promise<{ effectiveSelection: { providerId: string; modelId: string } | null }> };
};
interface ThreadState {
  threadId: string; title: string; phase: string; busy: boolean;
  lastError: { message: string } | null;
  rows: Array<{ rowId: number; kind: string; state: string; text: string; reasoning: string; createdAt: number }>;
  planning: string | null;
  updates: ResearchUpdate[];
  summary: string;
  reasoning: string;
  lastPrompt: string | null;
  steps: ResearchStep[];
}

const POLL_MS = 800;

// ── 轻量 markdown 渲染（自绘零注入面：标题/列表/粗体/行内码/段落；报告五节够用）──
function MdInline({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return (
    <>
      {parts.map((p, i) => {
        if (p.startsWith("**") && p.endsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
        if (p.startsWith("`") && p.endsWith("`")) return <code key={i} className="rounded bg-header px-1 py-px text-[0.85em]">{p.slice(1, -1)}</code>;
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}
function MarkdownView({ text }: { text: string }) {
  const blocks = useMemo(() => {
    const out: Array<{ kind: "h1" | "h2" | "h3" | "p" | "li"; text: string }> = [];
    for (const raw of String(text ?? "").replace(/\r/g, "").split("\n")) {
      const line = raw.trimEnd();
      if (!line.trim()) { continue; }
      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) { const lv = (h[1] ?? "#").length; out.push({ kind: lv <= 1 ? "h1" : lv === 2 ? "h2" : "h3", text: h[2] ?? "" }); }
      else if (/^[-*]\s+/.test(line.trim())) out.push({ kind: "li", text: line.trim().replace(/^[-*]\s+/, "") });
      else if (/^\d{1,3}[.、．]\s*/.test(line.trim())) out.push({ kind: "li", text: line.trim().replace(/^\d{1,3}[.、．]\s*/, "") });
      else out.push({ kind: "p", text: line.trim() });
    }
    return out;
  }, [text]);
  return (
    <div className="text-ui-sm leading-relaxed">
      {blocks.map((b, i) => b.kind === "h1" ? <h3 key={i} className="mb-1 mt-3 text-ui-base font-semibold first:mt-0">{b.text}</h3>
        : b.kind === "h2" ? <h4 key={i} className="mb-1 mt-3 text-ui-sm font-semibold first:mt-0">{b.text}</h4>
        : b.kind === "h3" ? <h5 key={i} className="mb-0.5 mt-2 text-ui-sm font-medium first:mt-0">{b.text}</h5>
        : b.kind === "li" ? <div key={i} className="flex gap-1.5 pl-1"><span className="text-foreground-subtle">·</span><span><MdInline text={b.text} /></span></div>
        : <p key={i} className="my-1"><MdInline text={b.text} /></p>)}
    </div>
  );
}

// ── 工具步骤八类图标（B15：搜索/案例/文献/法规/总结/web/通用/错误；自绘映射）──
function StepIcon({ kind }: { kind: StepIconKind }) {
  const cls = "size-3.5 shrink-0";
  switch (kind) {
    case "search": return <Search className={cls} />;
    case "case": return <Scale className={cls} />;
    case "doc": return <FileText className={cls} />;
    case "statute": return <BookOpen className={cls} />;
    case "summary": return <FileCheck className={cls} />;
    case "web": return <Globe className={cls} />;
    case "error": return <AlertTriangle className={cls + " text-red-500"} />;
    default: return <Wrench className={cls} />;
  }
}

// ── 徽章三态色（§3 UI 结构）──
function StatusBadge({ status }: { status: ResearchRecord["status"] }) {
  const map = {
    running: { text: "调研中", cls: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300" },
    done: { text: "已完成", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
    error: { text: "未完成", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
  } as const;
  const m = map[status];
  return <span data-testid="research-status-badge" className={`rounded px-1.5 py-0.5 text-ui-xs font-medium ${m.cls}`}>{m.text}</span>;
}
// ── 思考球（B18：自绘 spinner+分类文案；映射同构）──
function Orb({ text, phase }: { text: string; phase: "planning" | "running" }) {
  const label = { composing: "整理成文中", searching: "检索资料中", working: "调研进行中", solving: "拟定调研规划" }[orbStateOf(text, phase)];
  return <span className="inline-flex items-center gap-1.5 text-ui-xs text-foreground-subtle"><Loader2 className="size-3 animate-spin" />{label}</span>;
}

// ── 编辑对话框（B43：全屏、渲染/源码双模式、Ctrl+S 保存、Esc 关闭不保存）──
function EditorDialog({ record, onClose, onSave }: {
  record: ResearchRecord;
  onClose: () => void;
  onSave: (text: string) => void;
}) {
  const [mode, setMode] = useState<"render" | "source">("render");
  const [draft, setDraft] = useState(record.editedSummary ?? record.summary);
  const onKey = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") { e.preventDefault(); onClose(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); onSave(draft); }
  }, [draft, onClose, onSave]);
  useEffect(() => {
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onKey]);
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background" data-testid="research-editor-dialog">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <div className="flex items-center gap-2">
          <Pencil className="size-4" />
          <span className="text-ui-sm font-medium">编辑调研报告</span>
          <span className="text-ui-caption text-foreground-subtle">Ctrl/⌘+S 保存 · Esc 关闭不保存</span>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" data-testid="research-editor-mode"
            onClick={() => setMode(mode === "render" ? "source" : "render")}
            className="rounded border border-border px-2 py-1 text-ui-xs hover:bg-selected">
            {mode === "render" ? "切到源码" : "切到渲染"}
          </button>
          <button type="button" data-testid="research-editor-save"
            onClick={() => onSave(draft)}
            className="rounded bg-selected px-3 py-1 text-ui-xs font-medium">保存</button>
          <button type="button" aria-label="关闭" onClick={onClose} className="rounded p-1 hover:bg-selected"><X className="size-4" /></button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {mode === "render"
          ? <div className="mx-auto max-w-3xl"><MarkdownView text={draft} /></div>
          : <textarea value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck={false}
              className="mx-auto block h-full min-h-[60vh] w-full max-w-3xl resize-none rounded border border-border bg-header p-3 font-mono text-ui-sm outline-none" />}
      </div>
    </div>
  );
}

// ═══ 主面板 ═══
// onOpenLawBook：B06「去配置」对应物——法规库的配置面在应用内「法律工作台·法条手册」（法条包
// 安装/启用/包状态都在该工作区），由 Shell 注入导航回调；缺省不渲染该钮（裸挂载面不受影响）。
export function ResearchPanel({ onOpenLawBook }: { onOpenLawBook?: () => void } = {}) {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as ResearchSvc;
  const ready = Boolean(svc.researchRun && svc.researchThreadState);

  // ── 记录面（B07 启动即落+选中；B46 持久化=桥内轻量表权威，坏数据容错在桥侧 normalizeRecord）──
  const [records, setRecords] = useState<ResearchRecord[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = records?.find((r) => r.id === selectedId) ?? null;
  const running = selected?.status === "running";
  // ── 搜索条（B02 空禁用；B03 IME 守卫；B04 running 禁用+停止钮）──
  const [input, setInput] = useState("");
  const [composing, setComposing] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  // ── B06 法规库提示条事实源 ──
  const [lawsAvailable, setLawsAvailable] = useState<boolean | null>(null);
  // ── 流式派生面（轮询投影）──
  const [livePlanning, setLivePlanning] = useState<string | null>(null);
  const [liveUpdates, setLiveUpdates] = useState<ResearchUpdate[]>([]);
  const [liveSummary, setLiveSummary] = useState("");
  const [liveReasoning, setLiveReasoning] = useState("");
  const [liveSteps, setLiveSteps] = useState<ResearchStep[]>([]);
  const [planStreaming, setPlanStreaming] = useState(false);
  // ── B48 计时器仅 running 每秒 ──
  const [nowTick, setNowTick] = useState(Date.now());
  // ── 导出/通知（B39/B41）──
  const [exporting, setExporting] = useState<"" | "docx" | "md">("");
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  // ── 编辑（B43）──
  const [editorOpen, setEditorOpen] = useState(false);
  // ── B10 模型：跟随主对话所选 ──
  const mainSelectionRef = useRef<{ providerId: string; modelId: string } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // B49 挂载自动聚焦 + 记录载入 + B36 对账
  useEffect(() => {
    inputRef.current?.focus();
    if (!svc.researchRecordList) return;
    let alive = true;
    svc.researchRecordList()
      .then(({ records: recs }) => {
        if (!alive) return;
        setRecords(recs);
        const stuck = recs.filter((r) => r.status === "running");
        for (const r of stuck) void reconcile(r);
      })
      .catch(() => { if (alive) setRecords([]); });
    svc.modelSelectionService?.getView?.()
      .then((v) => { mainSelectionRef.current = v.effectiveSelection ?? null; })
      .catch(() => { /* 读不到主选择=诚实回落桥内置默认（B10 三级回退的末级） */ });
    svc.researchStatus?.()
      .then((s) => setLawsAvailable(s.lawsAvailable))
      .catch(() => setLawsAvailable(false));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // B36 对账：running 记录恢复轮询；会话不存在→落对账失败终态
  const reconcile = useCallback(async (rec: ResearchRecord) => {
    if (!rec.threadId || !svc.researchThreadState) return;
    try {
      await svc.researchThreadState({ threadId: rec.threadId });
      startPolling(rec.id, rec.threadId);
    } catch {
      const next = await svc.researchRecordFail?.({ id: rec.id, message: "调研会话已失效：内部会话不存在，流式对账失败。" }).catch(() => null);
      if (next) applyRecord(next);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [svc.researchThreadState, svc.researchRecordFail]);

  const applyRecord = useCallback((rec: ResearchRecord) => {
    setRecords((prev) => {
      const base = prev ?? [];
      const idx = base.findIndex((r) => r.id === rec.id);
      if (idx < 0) return [rec, ...base];
      const next = [...base];
      next[idx] = rec;
      return next;
    });
  }, []);

  // ── 轮询投影（B20 合批：每轮一次 setState 组提交；B36 流式对账以桥内权威 rows 为准）──
  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);
  const startPolling = useCallback((recordId: string, threadId: string) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const st = await svc.researchThreadState!({ threadId });
        // B20：一轮投影一次组提交（桥侧 800ms 快照节流即合批语义；帧内不再多次 setState）
        requestAnimationFrame(() => {
          setLivePlanning(st.planning);
          setLiveUpdates(st.updates);
          setLiveSummary(st.summary);
          setLiveReasoning(st.reasoning);
          setLiveSteps(st.steps ?? []);
          setPlanStreaming(st.busy && !st.planning);
        });
        if (!st.busy) {
          const rec = await svc.researchRecordGet!({ id: recordId });
          if (rec && rec.status !== "running") {
            applyRecord(rec);
            stopPolling();
            setPlanStreaming(false);
          }
        }
      } catch {
        // 会话失效：对账失败落错（B36 尾）
        const next = await svc.researchRecordFail?.({ id: recordId, message: "调研会话已失效：流式对账失败。" }).catch(() => null);
        if (next) applyRecord(next);
        stopPolling();
      }
    }, POLL_MS);
  }, [svc, applyRecord, stopPolling]);

  // B48 计时器仅 running 每秒走
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNowTick(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  useEffect(() => () => stopPolling(), [stopPolling]);

  // ── B01/B02/B03/B04/B07/B08/B10/B38：发起调研 ──
  const doRun = useCallback(async () => {
    const query = input.trim();
    if (!query || running || !svc.researchRun) return;
    stopPolling();
    setNotice(null);
    setLivePlanning(null); setLiveUpdates([]); setLiveSummary(""); setLiveReasoning(""); setLiveSteps([]); setPlanStreaming(true);
    // B07：立即（不等待网络）写一条 running 记录并选中（乐观记录，含即时规划 B08）
    const optimistic: ResearchRecord = {
      id: `research-${Date.now()}`,
      query, timestamp: new Date().toLocaleString("zh-CN", { hour12: false }),
      updatedAt: Date.now(), status: "running",
      planning: ["调研规划：", "1. 界定课题核心法律问题与争议焦点", "2. 检索相关现行法规与司法解释", "3. 收集典型案例与裁判要旨", "4. 梳理风险点形成分析框架", "5. 按五节结构完成报告并核对来源"].join("\n"),
      reasoning: "", steps: [], updates: [], summary: "", blocks: [],
    };
    setRecords((prev) => [optimistic, ...(prev ?? [])]);
    setSelectedId(optimistic.id);
    try {
      const { record } = await svc.researchRun({ query, model: mainSelectionRef.current });
      // 乐观记录与桥侧权威记录时间戳不同 id 必不同：先摘乐观行再并入权威记录（防列表重复）
      setRecords((prev) => {
        const base = (prev ?? []).filter((r) => r.id !== optimistic.id);
        const idx = base.findIndex((r) => r.id === record.id);
        if (idx < 0) return [record, ...base];
        const next = [...base];
        next[idx] = record;
        return next;
      });
      setSelectedId(record.id);
      setLivePlanning(record.planning ?? null);
      if (record.threadId) startPolling(record.id, record.threadId);
    } catch (e) {
      // B38 启动异常：当前记录标 error「调研启动失败：<原因>」
      const msg = String((e as Error)?.message ?? e);
      const failed: ResearchRecord = { ...optimistic, status: "error", error: `调研启动失败：${msg}` };
      applyRecord(failed);
      setSelectedId(failed.id);
      setPlanStreaming(false);
      svc.researchRecordSave?.({ record: failed }).then(({ record: saved }) => applyRecord(saved)).catch(() => { /* 桥不可达时记录留本地 */ });
    }
  }, [input, running, svc, applyRecord, startPolling, stopPolling]);

  // B37 手动停止：abort 语义=桥侧取消续跳+末帧补提交+落停止终态
  const doStop = useCallback(async () => {
    if (!selected || !svc.researchStop) return;
    stopPolling();
    try {
      const { record } = await svc.researchStop({ id: selected.id });
      applyRecord(record);
    } catch (e) {
      setNotice({ kind: "err", text: String((e as Error)?.message ?? e) });
    }
    setPlanStreaming(false);
  }, [selected, svc, applyRecord, stopPolling]);

  // ── B32/B39/B41 导出（预处理在桥侧单源；默认名清洗+.docx 强制在桥侧）──
  const doExport = useCallback(async (kind: "docx" | "md") => {
    const text = selected?.editedSummary ?? selected?.summary ?? "";
    if (!text || exporting || !selected) return;
    if (kind === "docx" && !svc.researchExportWord) { setNotice({ kind: "err", text: "当前宿主不支持导出 Word。" }); return; }
    if (kind === "md" && !svc.researchExportMd) { setNotice({ kind: "err", text: "当前宿主不支持导出 Markdown。" }); return; }
    setExporting(kind);
    setNotice(null);
    try {
      if (kind === "docx") {
        const r = await svc.researchExportWord!({ markdown: text, query: selected.query });
        const blob = new Blob([Uint8Array.from(atob(r.docxBase64), (c) => c.charCodeAt(0))],
          { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = r.fileName; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 4000);
        setNotice({ kind: "ok", text: `已导出：${r.fileName}（浏览器下载目录）` });
      } else {
        const r = await svc.researchExportMd!({ markdown: text, query: selected.query });
        const blob = new Blob([r.text], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = r.fileName; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 4000);
        setNotice({ kind: "ok", text: `已导出：${r.fileName}（浏览器下载目录）` });
      }
    } catch (e) {
      setNotice({ kind: "err", text: String((e as Error)?.message ?? e) });
    } finally {
      setExporting("");
    }
  }, [selected, exporting, svc]);

  // B43 编辑保存：桥侧落账 summary=editedSummary=新文+revision；页面/两种导出同步用编辑版
  const doSaveEdit = useCallback(async (text: string) => {
    if (!selected || !svc.researchRecordEdit) return;
    try {
      const { record } = await svc.researchRecordEdit({ id: selected.id, summary: text });
      applyRecord(record);
      setLiveSummary(record.editedSummary ?? record.summary);
      setEditorOpen(false);
      setNotice({ kind: "ok", text: "报告已保存编辑版。" });
    } catch (e) {
      setNotice({ kind: "err", text: String((e as Error)?.message ?? e) });
    }
  }, [selected, svc, applyRecord]);

  // B44/B45 删除与清空（running 条目删除先触发停止=桥侧 researchRecordDelete 已内建取消）
  const doDelete = useCallback(async (id: string) => {
    try {
      await svc.researchRecordDelete?.({ id });
      setRecords((prev) => (prev ?? []).filter((r) => r.id !== id));
      if (selectedId === id) { setSelectedId(null); stopPolling(); setEditorOpen(false); }
    } catch (e) {
      setNotice({ kind: "err", text: String((e as Error)?.message ?? e) });
    }
  }, [svc, selectedId, stopPolling]);
  const doClear = useCallback(async () => {
    if (!window.confirm("确定清空全部调研记录？进行中的调研也会一并中止。")) return;
    try {
      await svc.researchClearRecords?.();
      setRecords([]);
      setSelectedId(null);
      stopPolling();
      setEditorOpen(false);
      setLivePlanning(null); setLiveUpdates([]); setLiveSummary("");
    } catch (e) {
      setNotice({ kind: "err", text: String((e as Error)?.message ?? e) });
    }
  }, [svc, stopPolling]);

  // B47 切换记录：关编辑框+滚动重置
  const doSelect = useCallback((id: string) => {
    setSelectedId(id);
    setEditorOpen(false);
    stopPolling();
    setLivePlanning(null); setLiveUpdates([]); setLiveSummary(""); setLiveReasoning(""); setLiveSteps([]);
    const rec = records?.find((r) => r.id === id);
    if (rec?.status === "running" && rec.threadId) void reconcile(rec);
    requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: 0 }));
  }, [records, reconcile, stopPolling]);

  // ── B19 自动滚动跟随（rAF 平滑指数插值；reduced-motion 直跳；上滚解除+回底恢复）──
  const followRef = useRef(true);
  const lastWheelUpRef = useRef(0);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    let raf = 0;
    let last = performance.now();
    const reduced = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const step = (t: number) => {
      const dt = Math.min(50, Math.max(1, t - last)); // 插值 elapsed 钳制 [1,50]ms（B19）
      last = t;
      if (followRef.current && el.scrollHeight > el.clientHeight) {
        const target = el.scrollHeight - el.clientHeight;
        const dist = target - el.scrollTop;
        if (Math.abs(dist) <= 0.75) el.scrollTop = target; // |距离|≤0.75 直达
        else if (reduced) el.scrollTop = target; // reduced-motion 直跳
        else el.scrollTop += dist * (1 - Math.exp(-dt / 90)); // 平滑指数插值
      }
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    const onWheel = (e: WheelEvent) => {
      if (e.deltaY < 0) {
        followRef.current = false; // 用户上滚解除跟随
        lastWheelUpRef.current = Date.now();
      }
    };
    const onScroll = () => {
      // 回到底部阈值（12px）内自动恢复跟随
      const el2 = scrollRef.current;
      if (!el2) return;
      if (!followRef.current && el2.scrollHeight - el2.clientHeight - el2.scrollTop <= 12 && Date.now() - lastWheelUpRef.current > 400) {
        followRef.current = true;
      }
    };
    el.addEventListener("wheel", onWheel, { passive: true });
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("wheel", onWheel);
      el.removeEventListener("scroll", onScroll);
    };
  }, []);

  // ── 展示派生（running 用 live 流；终态用记录字段）──
  const planning = running ? (livePlanning ?? selected?.planning ?? null) : (selected?.planning ?? null);
  const updates = running ? liveUpdates : (selected?.updates ?? []);
  const summary = running ? liveSummary : (selected?.editedSummary ?? selected?.summary ?? "");
  const steps = running ? liveSteps : (selected?.steps ?? []);
  // B16 当前执行工具名=最后一个未完成步骤；无则「等待下一条结果」（B15 步骤面接线）
  const lastPendingTool = [...steps].reverse().find((st) => st.status === "running" || st.status === "pending")?.tool;
  const showEditorButton = selected && selected.status !== "running" && Boolean(selected.editedSummary ?? selected.summary);
  const duration = selected?.status === "running" ? durationFormat(nowTick - selected.updatedAt) : "";

  return (
    <div className="flex h-[calc(100vh-8rem)] min-h-0 gap-4" data-testid="research-panel">
      {/* ── 左历史栏（B44/B45/B47）── */}
      <aside className="flex w-64 shrink-0 flex-col rounded-workspace-panel border border-border bg-header">
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <span className="text-ui-sm font-medium">调研历史{records ? ` · 共 ${records.length} 条` : ""}</span>
          {records && records.length > 0 ? (
            <button type="button" data-testid="research-clear" onClick={() => void doClear()}
              className="rounded p-1 text-foreground-subtle hover:bg-selected hover:text-foreground" aria-label="清空记录">
              <Trash2 className="size-3.5" />
            </button>
          ) : null}
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-1.5">
          {!records ? <p className="p-3 text-ui-caption text-foreground-subtle">记录读取中…</p> : null}
          {records && records.length === 0 ? (
            <div className="p-3 text-ui-caption text-foreground-subtle" data-testid="research-history-empty">
              <p>还没有调研记录。</p>
              <p>发起一次调研后，记录会自动保存在这里。</p>
            </div>
          ) : null}
          {(records ?? []).map((r) => (
            <div key={r.id} data-testid="research-history-item"
              className={`group relative mb-1 cursor-pointer rounded px-2.5 py-2 ${r.id === selectedId ? "bg-selected" : "hover:bg-selected/60"}`}
              onClick={() => doSelect(r.id)}>
              <div className="flex items-start gap-1.5">
                {r.status === "running" ? <Loader2 className="mt-0.5 size-3.5 shrink-0 animate-spin text-blue-500" />
                  : r.status === "error" ? <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-red-500" />
                  : <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-emerald-500" />}
                <div className="min-w-0 pr-5">
                  <p className="truncate text-ui-sm" title={r.query}>{r.query}</p>
                  <p className="text-ui-caption text-foreground-subtle">{r.timestamp}</p>
                  {r.status === "error" && r.error ? <p className="truncate text-ui-caption text-red-500" title={r.error}>{r.error}</p> : null}
                </div>
              </div>
              <button type="button" aria-label="删除记录" data-testid="research-item-delete"
                className="absolute right-1.5 top-2 hidden rounded p-1 text-foreground-subtle hover:bg-background hover:text-foreground group-hover:block"
                onClick={(e) => { e.stopPropagation(); void doDelete(r.id); }}>
                <Trash2 className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* ── 主列 ── */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 pb-2">
          <Telescope className="size-5" />
          <div>
            <h1 className="text-ui-lg font-semibold">调研报告</h1>
            <p className="text-ui-caption text-foreground-subtle">课题 → 多来源检索 → 结构化调研报告（结论 / 依据 / 案例 / 风险 / 来源）</p>
          </div>
        </header>

        {/* 搜索条（B02/B03/B04） */}
        <div className="flex items-center gap-2 pb-2">
          <div className="flex min-w-0 flex-1 items-center gap-2 rounded-workspace-panel border border-border bg-header px-3 py-1.5">
            <Search className="size-4 shrink-0 text-foreground-subtle" />
            <input ref={inputRef} data-testid="research-input" value={input} disabled={running}
              placeholder="例：请调研竞业限制补偿标准的法律规定与典型案例"
              onChange={(e) => setInput(e.target.value)}
              onCompositionStart={() => setComposing(true)}
              onCompositionEnd={() => setComposing(false)}
              onKeyDown={(e) => {
                // B03：Enter 触发；IME 组合态 / keyCode 229 不触发
                if (e.key === "Enter" && !composing && e.keyCode !== 229) { e.preventDefault(); void doRun(); }
              }}
              className="min-w-0 flex-1 bg-transparent text-ui-sm outline-none placeholder:text-foreground-subtle" />
          </div>
          {running ? (
            <button type="button" data-testid="research-stop" onClick={() => void doStop()}
              className="flex shrink-0 items-center gap-1.5 rounded bg-red-500 px-4 py-1.5 text-ui-sm font-medium text-white hover:bg-red-600">
              <Square className="size-3.5" /> 停止
            </button>
          ) : (
            <button type="button" data-testid="research-run" disabled={!input.trim() || !ready} onClick={() => void doRun()}
              className="shrink-0 rounded bg-selected px-4 py-1.5 text-ui-sm font-medium disabled:opacity-50">
              开始调研
            </button>
          )}
        </div>

        {/* B06 法规库提示条（不阻断启动；「去配置」=跳转法条手册配置面，竞品为系统浏览器外链，
            自家配置面在应用内法律工作台，等量取应用内导航） */}
        {lawsAvailable === false ? (
          <div data-testid="research-laws-hint" className="mb-2 flex items-start gap-2 rounded border border-amber-300 bg-amber-50 px-3 py-1.5 text-ui-xs text-amber-800 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200">
            <span className="min-w-0 flex-1">
              未检测到可用的本地法规库：调研将仅基于模型内置知识与其他所内资料，法条原文与效力请以官方发布为准。安装并启用本地法规库后此提示自动消失。
            </span>
            {onOpenLawBook ? (
              <button type="button" data-testid="research-laws-hint-config" onClick={onOpenLawBook}
                className="shrink-0 rounded border border-amber-400 px-2 py-0.5 font-medium underline underline-offset-2 hover:bg-amber-100 dark:border-amber-600 dark:hover:bg-amber-900">
                去配置
              </button>
            ) : null}
          </div>
        ) : null}

        {/* 报告管理条（B32：仅非 running 且有报告出现三钮；B39/B41 通知文本） */}
        {showEditorButton ? (
          <div className="mb-2 flex items-center gap-2 rounded-workspace-panel border border-border bg-header px-3 py-1.5">
            <span className="min-w-0 flex-1 truncate text-ui-xs text-foreground-subtle" data-testid="research-notice">
              {notice ? (notice.kind === "ok" ? `✓ ${notice.text}` : `✗ ${notice.text}`) : ""}
            </span>
            <button type="button" data-testid="research-edit" onClick={() => setEditorOpen(true)} disabled={exporting !== ""}
              className="flex items-center gap-1 rounded border border-border px-2 py-1 text-ui-xs hover:bg-selected disabled:opacity-50">
              <Pencil className="size-3" /> 编辑报告
            </button>
            <button type="button" data-testid="research-export-word" onClick={() => void doExport("docx")} disabled={exporting !== ""}
              className="flex items-center gap-1 rounded border border-border px-2 py-1 text-ui-xs hover:bg-selected disabled:opacity-50">
              {exporting === "docx" ? <Loader2 className="size-3 animate-spin" /> : <Download className="size-3" />}
              {exporting === "docx" ? "导出中…" : "导出 Word"}
            </button>
            <button type="button" data-testid="research-export-md" onClick={() => void doExport("md")} disabled={exporting !== ""}
              className="flex items-center gap-1 rounded border border-border px-2 py-1 text-ui-xs hover:bg-selected disabled:opacity-50">
              {exporting === "md" ? <Loader2 className="size-3 animate-spin" /> : <FileText className="size-3" />}
              {exporting === "md" ? "导出中…" : "导出 MD"}
            </button>
          </div>
        ) : notice ? (
          <div className="mb-2 px-1 text-ui-xs" data-testid="research-notice">{notice.kind === "ok" ? `✓ ${notice.text}` : `✗ ${notice.text}`}</div>
        ) : null}

        {/* 滚动结果区（B19 跟随） */}
        <div ref={scrollRef} data-testid="research-scroll" className="min-h-0 flex-1 overflow-y-auto rounded-workspace-panel border border-border bg-header p-4 [scrollbar-gutter:stable]">
          {!selected ? (
            <div className="flex h-full flex-col items-center justify-center gap-1 text-center" data-testid="research-empty">
              <Telescope className="size-8 text-foreground-subtle" />
              <p className="text-ui-base font-medium">输入一个法律课题，开始一次结构化调研</p>
              <p className="text-ui-caption text-foreground-subtle">记录会自动保存在左侧，可随时回看与导出。</p>
            </div>
          ) : (
            <div className="mx-auto flex max-w-3xl flex-col gap-3">
              {/* 课题卡 */}
              <div className="rounded border border-border bg-background p-3" data-testid="research-query-card">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-ui-sm font-medium">{selected.query}</p>
                  <StatusBadge status={selected.status} />
                </div>
                <p className="mt-1 text-ui-caption text-foreground-subtle">{selected.timestamp}</p>
              </div>

              {/* 实时状态条（B16：running 吸顶；时长秒跳+当前工具名或等待文案） */}
              {running ? (
                <div className="sticky top-0 z-10 flex items-center gap-2 rounded border border-border bg-background/95 px-3 py-1.5 backdrop-blur" data-testid="research-live-bar">
                  <Orb text={liveReasoning || liveUpdates.at(-1)?.text || liveSummary || planning || ""} phase={planStreaming ? "planning" : "running"} />
                  <span className="animate-pulse text-ui-xs text-foreground-subtle">· 已进行 {duration}</span>
                  <span className="text-ui-xs text-foreground-subtle" data-testid="research-live-tool">
                    · {lastPendingTool ? `当前执行：${lastPendingTool}` : "等待下一条结果"}
                  </span>
                </div>
              ) : null}

              {/* 调研规划卡（B08/B12/B13） */}
              <div className="rounded border border-border bg-background p-3" data-testid="research-planning-card">
                <div className="mb-1.5 flex items-center gap-2">
                  <span className="text-ui-sm font-medium">调研规划</span>
                  {running && !planning ? (
                    <span className="inline-flex items-center gap-1 text-ui-xs text-foreground-subtle"><Loader2 className="size-3 animate-spin" />正在形成调研规划</span>
                  ) : running ? (
                    <span className="inline-flex items-center gap-1 text-ui-xs text-foreground-subtle"><Loader2 className="size-3 animate-spin" />规划中</span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-ui-xs text-emerald-600"><CheckCircle2 className="size-3" />已形成</span>
                  )}
                </div>
                {planning ? (
                  <div className="text-ui-sm leading-relaxed">
                    {planning.split("\n").filter((l) => l.trim()).map((line, i) => {
                      const m = line.match(/^(\d{1,3}[.、．:：)]?)\s*(.*)$/);
                      const isLast = i === planning.split("\n").filter((l2) => l2.trim()).length - 1;
                      return (
                        <div key={i} className="flex gap-1.5">
                          {m ? <span className="shrink-0 font-medium text-foreground-subtle">{m[1]}</span> : null}
                          <span>{m ? m[2] : line}{running && isLast && planStreaming ? <span className="animate-pulse">▍</span> : null}</span>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <p className="text-ui-caption text-foreground-subtle">规划内容将在调研启动后出现在这里。</p>
                )}
              </div>

              {/* 阶段播报卡（B14：独立编号徽章+模型阶段号优先；流式思考球+完成打勾；卡头计数） */}
              {updates.length ? (
                <div className="rounded border border-border bg-background p-3" data-testid="research-updates-card">
                  <div className="mb-1.5 text-ui-sm font-medium">阶段播报 · {updates.length} 个阶段</div>
                  <div className="flex flex-col gap-2">
                    {updates.map((u, i) => {
                      const stageNo = extractStageNo(u.text) ?? i + 1;
                      const last = i === updates.length - 1;
                      const streaming = running && last;
                      // 剥掉首行阶段标题（徽章已承载阶段号），只播报正文
                      const firstLine = u.text.split("\n")[0] ?? "";
                      const bodyLines = /^(?:#{1,6}\s*)?(?:阶段|第\s*\S+\s*(?:个\s*)?阶段|步骤)/u.test(firstLine.trim())
                        ? u.text.split("\n").slice(1).join("\n").trim() : u.text.trim();
                      return (
                        <div key={u.id} className="flex items-start gap-2">
                          <span className="mt-0.5 shrink-0 rounded bg-selected px-1.5 py-0.5 text-ui-xs font-medium" data-testid="research-stage-badge">阶段{stageNo}</span>
                          <div className="min-w-0 flex-1 whitespace-pre-wrap break-words text-ui-sm">
                            {bodyLines || firstLine}
                            {u.completed !== false
                              ? <CheckCircle2 className="ml-1.5 inline size-3 text-emerald-500" />
                              : <Loader2 className="ml-1.5 inline size-3 animate-spin" />}
                            {streaming ? <span className="animate-pulse">▍</span> : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {/* 工具步骤卡（B15：每次工具事件一条；八类图标；错误步骤文案；B28 步骤只追加） */}
              {steps.length ? (
                <div className="rounded border border-border bg-background p-3" data-testid="research-steps-card">
                  <div className="mb-1.5 text-ui-sm font-medium">工具步骤 · {steps.length} 步</div>
                  <div className="flex flex-col gap-1.5">
                    {steps.map((st) => (
                      <div key={st.id} className="flex items-center gap-2" data-testid="research-step-item">
                        <StepIcon kind={st.icon} />
                        <span className="text-ui-sm">{st.tool}</span>
                        {st.status === "running" || st.status === "pending" ? <Loader2 className="size-3 animate-spin text-foreground-subtle" /> : null}
                        {st.status === "done" ? <CheckCircle2 className="size-3 text-emerald-500" /> : null}
                        {st.status === "error" ? <AlertCircle className="size-3 text-red-500" /> : null}
                        <span className="min-w-0 flex-1 truncate text-ui-caption text-foreground-subtle" title={st.detail ?? st.input}>
                          {st.status === "error" ? STEP_ERROR_TEXT : (st.input || st.output || "")}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              {/* 调研总结卡（B17：running 卡头整理中；无正文三段骨架占位） */}
              <div className="rounded border border-border bg-background p-3" data-testid="research-summary-card">
                <div className="mb-1.5 flex items-center gap-2">
                  <FileText className="size-3.5" />
                  <span className="text-ui-sm font-medium">调研总结</span>
                  {running ? <span className="inline-flex items-center gap-1 text-ui-xs text-foreground-subtle"><Loader2 className="size-3 animate-spin" />整理中</span> : null}
                </div>
                {summary ? (
                  <div key={`${selected.id}-${selected.reportRevision ?? 0}`} data-testid="research-summary-body">
                    <MarkdownView text={summary} />
                  </div>
                ) : running ? (
                  <div className="flex flex-col gap-2" data-testid="research-summary-skeleton">
                    <div className="h-3 w-3/4 animate-pulse rounded bg-selected" />
                    <div className="h-3 w-full animate-pulse rounded bg-selected" />
                    <div className="h-3 w-5/6 animate-pulse rounded bg-selected" />
                  </div>
                ) : (
                  <p className="text-ui-caption text-foreground-subtle">
                    {selected.status === "error" ? "本次调研未产出报告。" : "报告内容将在调研完成后出现在这里。"}
                  </p>
                )}
              </div>

              {/* 错误条（B33/B34/B35/B37/B38 文案由桥侧落账；首错保留） */}
              {selected.status === "error" && selected.error ? (
                <div className="flex items-start gap-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-ui-sm text-red-700 dark:border-red-700 dark:bg-red-950 dark:text-red-300" data-testid="research-error-bar">
                  <AlertCircle className="mt-0.5 size-4 shrink-0" />
                  <span>{selected.error}</span>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {/* 编辑对话框（B43） */}
      {editorOpen && selected ? (
        <EditorDialog
          record={selected}
          onClose={() => setEditorOpen(false)}
          onSave={(text) => void doSaveEdit(text)}
        />
      ) : null}
    </div>
  );
}
