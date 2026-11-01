// 【步骤4·#18 学习迭代】学习工作区面板（RE-18-学习迭代.md §3.4 UI 结构；行为锚点按 J 编号标注）。
// 布局=左记录侧栏（总览/搜索/记录列表带状态图标）+主区（总览页/记录详情页）。
// 总览=状态卡（徽章七态五色+消息+立即学习/取消等待）→4 指标卡→最新一轮 5 指标带→七阶段流程条
// →最近报告摘要+回滚最近一轮；记录页=徽章+回滚本轮→成果报告（eyebrow+双态标题+overview+
// 圆环计数+5 格统计带+成果横条图+安全卡+学到什么/带来什么两列+下次怎样帮你 checklist+技术记录折叠）。
// 数据经桥 learning* 六命令（learningStatus/list/get/queue/cancel/rollback），5s 并行轮询（J13）；
// 选中记录消失自动清选回总览（J13）。文案全部自写（表达隔离）；视觉自绘（§3.4）。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, BookOpen, BrainCircuit, CheckCircle2, ChevronDown, ClipboardList, Clock,
  GraduationCap, ListChecks, Loader2, RotateCcw, Search, ShieldCheck, Sparkles, Wrench, XCircle,
} from "lucide-react";
import { useServices } from "../ui-kit.js";

type RunStatus = "disabled" | "idle" | "waiting" | "running" | "completed" | "failed" | "rolled_back";
type TodayEligibility = "can-check" | "done-today" | "queued" | "disabled";

interface LearningCounts {
  sources: number; threads: number; knowledgeFiles: number; uploadedFiles: number; generatedFiles: number;
  memoriesCreated: number; memoriesUpdated: number; memoriesDisabled: number;
  skillsCreated: number; skillsUpdated: number;
  knowledgeNotesCreated: number; knowledgeNotesUpdated: number; rejected: number;
}
interface RecordSummary {
  id: string; title: string; displayName: string; status: RunStatus;
  startedAt: number; finishedAt: number; reportPath: string; canRollback: boolean;
  rolledBackAt?: number; error?: string; counts: LearningCounts;
}
interface LearningStatusPayload {
  enabled: boolean; eligibleToday: TodayEligibility; queued: boolean; running: boolean;
  status: RunStatus; message: string;
  lastSuccessfulAt: number | null; lastCheckedAt: number | null; nextEligibleAt: number | null;
  baselineComplete: boolean; baselineProgress: number; pendingSourceCount: number;
  activeRunId: string | null; latest: RecordSummary | null;
  idleMinutes: number; keepRunningInTray: boolean;
}
interface LearningSvc {
  learningStatus?: () => Promise<LearningStatusPayload>;
  learningList?: () => Promise<{ records: RecordSummary[] } | { ok: false; error: string }>;
  learningGet?: (p: { id: string }) => Promise<{ summary: RecordSummary; reportMarkdown: string }>;
  learningQueue?: (p?: unknown) => Promise<{ ok: boolean; reason?: string; message?: string }>;
  learningCancel?: (p?: unknown) => Promise<{ ok: boolean; phase?: string; message?: string }>;
  learningRollback?: (p: { id: string }) => Promise<{ ok: boolean; summary?: RecordSummary }>;
}

const POLL_MS = 5000; // J13 5s 轮询
// J5 七阶段流程条（阶段名自拟）
const STAGE_BAR = ["增量收集", "整体理解", "结构提取", "交叉核对", "内容构造", "可靠性检查", "统一发布"];
// 徽章五色+七态文案（J2 色板自绘）
const STATUS_VIEW: Record<RunStatus, { text: string; cls: string }> = {
  disabled: { text: "已关闭", cls: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300" },
  idle: { text: "待检查", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  waiting: { text: "排队中", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
  running: { text: "学习中", cls: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300" },
  completed: { text: "已完成", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  failed: { text: "未完成", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
  rolled_back: { text: "已回滚", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
};
function StatusBadge({ status, testId }: { status: RunStatus; testId?: string }) {
  const m = STATUS_VIEW[status] ?? STATUS_VIEW.idle;
  return <span data-testid={testId ?? "learning-status-badge"} className={`rounded px-1.5 py-0.5 text-ui-xs font-medium ${m.cls}`}>{m.text}</span>;
}
function fmtTime(ts: number | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
// J4 最新一轮 5 指标（与内核 latestRoundMetrics 同构）
function latestMetrics(c: LearningCounts) {
  return [
    { key: "browse", label: "浏览并理解", value: c.sources },
    { key: "memories", label: "更懂你的地方", value: c.memoriesCreated + c.memoriesUpdated + c.memoriesDisabled },
    { key: "skills", label: "新掌握的方法", value: c.skillsCreated + c.skillsUpdated },
    { key: "knowledge", label: "知识库沉淀", value: c.knowledgeNotesCreated + c.knowledgeNotesUpdated },
    { key: "rejected", label: "谨慎未采纳", value: c.rejected },
  ];
}
// 轻量 markdown 渲染（标题/列表/段落/粗体；报告三节够用，零注入面）
function MdLite({ text }: { text: string }) {
  const blocks = useMemo(() => {
    const out: Array<{ kind: "h1" | "h2" | "li" | "p"; text: string }> = [];
    for (const raw of String(text ?? "").replace(/\r/g, "").split("\n")) {
      const line = raw.trimEnd();
      if (!line.trim()) continue;
      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) out.push({ kind: (h[1] ?? "#").length <= 1 ? "h1" : "h2", text: h[2] ?? "" });
      else if (/^[-*]\s+/.test(line.trim())) out.push({ kind: "li", text: line.trim().replace(/^[-*]\s+/, "") });
      else out.push({ kind: "p", text: line.trim() });
    }
    return out;
  }, [text]);
  const bold = (s: string) => s.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    p.startsWith("**") && p.endsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>);
  return (
    <div className="text-ui-sm leading-relaxed">
      {blocks.map((b, i) => b.kind === "h1" ? <h3 key={i} className="mb-1 mt-3 text-ui-base font-semibold first:mt-0">{b.text}</h3>
        : b.kind === "h2" ? <h4 key={i} className="mb-1 mt-3 text-ui-sm font-semibold first:mt-0">{b.text}</h4>
        : b.kind === "li" ? <div key={i} className="flex gap-1.5 pl-1"><span className="text-foreground-subtle">·</span><span>{bold(b.text)}</span></div>
        : <p key={i} className="my-1">{bold(b.text)}</p>)}
    </div>
  );
}
// 成果横条图（J8：4 行按最大值比例，0 不显示，含 aria 文案）
function Bars({ rows }: { rows: Array<{ label: string; value: number }> }) {
  const shown = rows.filter((r) => r.value > 0);
  const max = Math.max(1, ...shown.map((r) => r.value));
  if (!shown.length) return <p className="text-ui-xs text-foreground-subtle">本轮没有可展示的变更分布。</p>;
  return (
    <div className="flex flex-col gap-1.5" data-testid="learning-bars" role="img"
      aria-label={"变更分布：" + shown.map((r) => `${r.label} ${r.value} 项`).join("，")}>
      {shown.map((r) => (
        <div key={r.label} className="flex items-center gap-2">
          <span className="w-24 shrink-0 text-ui-xs text-foreground-subtle">{r.label}</span>
          <div className="h-2.5 flex-1 overflow-hidden rounded bg-header">
            <div className="h-full rounded bg-emerald-500/70 dark:bg-emerald-600" style={{ width: `${Math.max(6, Math.round((r.value / max) * 100))}%` }} />
          </div>
          <span className="w-6 text-right text-ui-xs font-medium">{r.value}</span>
        </div>
      ))}
    </div>
  );
}
// 记录状态图标（J12：failed 红/rolled_back 琥珀/其余绿）
function RecordIcon({ status }: { status: RunStatus }) {
  if (status === "failed") return <XCircle className="size-3.5 shrink-0 text-red-500" />;
  if (status === "rolled_back") return <AlertTriangle className="size-3.5 shrink-0 text-amber-500" />;
  return <CheckCircle2 className="size-3.5 shrink-0 text-emerald-500" />;
}

// ═══ 记录详情页（J7-J11）═══
function RecordDetail({ id, svc, onBack }: { id: string; svc: LearningSvc; onBack: () => void }) {
  const [detail, setDetail] = useState<{ summary: RecordSummary; reportMarkdown: string } | null>(null);
  const [loadErr, setLoadErr] = useState(false);
  const [rolling, setRolling] = useState(false);
  const [techOpen, setTechOpen] = useState(false);
  const reload = useCallback(() => {
    svc.learningGet?.({ id }).then(setDetail).catch(() => setLoadErr(true));
  }, [id, svc]);
  useEffect(() => { reload(); }, [reload]);
  if (loadErr) {
    return (
      <div className="rounded-workspace-panel border border-border bg-header p-6 text-center" data-testid="learning-detail-error">
        <p className="text-ui-sm text-foreground-subtle">这份记录读取失败或已被清理。</p>
        <button type="button" className="mt-3 rounded border border-border px-3 py-1 text-ui-sm hover:bg-selected" onClick={onBack}>回到总览</button>
      </div>
    );
  }
  if (!detail) return <div className="flex items-center gap-2 p-6 text-ui-sm text-foreground-subtle"><Loader2 className="size-4 animate-spin" />记录加载中…</div>;
  const { summary, reportMarkdown } = detail;
  const c = summary.counts;
  const accepted = c.memoriesCreated + c.memoriesUpdated + c.memoriesDisabled + c.skillsCreated + c.skillsUpdated + c.knowledgeNotesCreated + c.knowledgeNotesUpdated;
  const zeroChange = accepted === 0;
  const ringR = 34, ringC = 2 * Math.PI * ringR;
  const ringPct = Math.min(100, accepted * 10);
  const metricRows = [
    { label: "记住的内容", value: c.memoriesCreated + c.memoriesUpdated + c.memoriesDisabled },
    { label: "掌握的方法", value: c.skillsCreated + c.skillsUpdated },
    { label: "知识库沉淀", value: c.knowledgeNotesCreated + c.knowledgeNotesUpdated },
    { label: "谨慎未采纳", value: c.rejected },
  ];
  // 三列内容（J10）：从报告 markdown 抽三节（与桥侧 buildUserReport 固定节名同源；行解析零转义坑）
  const sectionOf = (name: string): string[] => {
    const lines = reportMarkdown.replace(/\r/g, "").split("\n");
    const out: string[] = [];
    let inSection = false;
    for (const line of lines) {
      const isH2 = /^##\s+/.test(line.trim());
      if (isH2) { inSection = line.trim().replace(/^##\s+/, "") === name; continue; }
      if (!inSection) continue;
      const t = line.trim().replace(/^[-*]\s+/, "").trim();
      if (t && !t.startsWith("|") && !t.startsWith("#")) out.push(t);
    }
    return out;
  };
  const learned = sectionOf("这次学到了什么");
  const improvements = sectionOf("会带来哪些提升");
  const nextHelp = sectionOf("以后会怎样帮你");
  const plainOverview = reportMarkdown.split("\n").filter((l) => !l.startsWith("#") && !l.startsWith("|") && !l.startsWith("-")).join("\n").trim() || "这一轮没有改动任何沉淀内容。";
  const doRollback = async () => {
    setRolling(true);
    try { await svc.learningRollback?.({ id }); reload(); } catch { /* 失败提示随重载状态呈现 */ } finally { setRolling(false); }
  };
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4" data-testid="learning-detail">
      <div className="flex items-center gap-2">
        <button type="button" className="rounded border border-border px-2 py-0.5 text-ui-xs hover:bg-selected" onClick={onBack}>← 总览</button>
        <StatusBadge status={summary.status} testId="learning-detail-badge" />
        {summary.canRollback ? (
          <button type="button" data-testid="learning-rollback-this" disabled={rolling}
            className="ml-auto flex items-center gap-1 rounded border border-border px-2.5 py-1 text-ui-xs hover:bg-selected disabled:opacity-50"
            onClick={() => void doRollback()}>
            {rolling ? <Loader2 className="size-3 animate-spin" /> : <RotateCcw className="size-3" />} 回滚本轮
          </button>
        ) : null}
      </div>
      <div className="rounded-workspace-panel border border-border bg-header p-4">
        <p className="text-ui-xs uppercase tracking-wide text-foreground-subtle">学习成果报告</p>
        <div className="mt-1 flex items-start gap-4">
          <div className="min-w-0 flex-1">
            <h2 className="text-ui-lg font-semibold" data-testid="learning-detail-title">
              {zeroChange ? "本轮学习检查已完成" : summary.title}
            </h2>
            <p className="mt-0.5 text-ui-xs text-foreground-subtle">完成于 {fmtTime(summary.finishedAt)} · {summary.displayName}</p>
            <div className="mt-2 text-ui-sm leading-relaxed"><MdLite text={plainOverview} /></div>
          </div>
          {/* 右侧圆环计数（J8：accepted=三类变更和） */}
          <div className="relative shrink-0" data-testid="learning-ring" role="img" aria-label={`本轮共 ${accepted} 处变更`}>
            <svg width="88" height="88" viewBox="0 0 88 88">
              <circle cx="44" cy="44" r={ringR} fill="none" stroke="currentColor" className="text-border" strokeWidth="8" />
              <circle cx="44" cy="44" r={ringR} fill="none" stroke="currentColor" className="text-emerald-500" strokeWidth="8"
                strokeDasharray={`${(ringPct / 100) * ringC} ${ringC}`} strokeLinecap="round" transform="rotate(-90 44 44)" />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-ui-lg font-semibold">{accepted}</span>
              <span className="text-ui-xs text-foreground-subtle">处变更</span>
            </div>
          </div>
        </div>
      </div>
      {/* 5 格统计带（J8） */}
      <div className="grid grid-cols-5 gap-2" data-testid="learning-stat-band">
        {[
          { label: "变化来源", value: c.sources }, { label: "记住的内容", value: c.memoriesCreated + c.memoriesUpdated + c.memoriesDisabled },
          { label: "掌握的方法", value: c.skillsCreated + c.skillsUpdated }, { label: "知识库沉淀", value: c.knowledgeNotesCreated + c.knowledgeNotesUpdated },
          { label: "谨慎未采纳", value: c.rejected },
        ].map((m) => (
          <div key={m.label} className="rounded-workspace-panel border border-border bg-header px-2 py-2 text-center">
            <div className="text-ui-base font-semibold">{m.value}</div>
            <div className="text-ui-xs text-foreground-subtle">{m.label}</div>
          </div>
        ))}
      </div>
      {/* 成果横条图（J8） */}
      <div className="rounded-workspace-panel border border-border bg-header p-3">
        <Bars rows={metricRows} />
        <p className="mt-1.5 text-ui-xs text-foreground-subtle">条长按本轮最大值归一，仅作分布示意。</p>
      </div>
      {/* 安全卡（J9：固定说明+rejected 二态提示） */}
      <div className="rounded-workspace-panel border border-border bg-header p-3" data-testid="learning-safety-card">
        <div className="flex items-center gap-2 text-ui-sm font-medium"><ShieldCheck className="size-4 text-emerald-500" />这一轮的安全边界</div>
        <ul className="mt-1.5 space-y-0.5 text-ui-xs text-foreground-subtle">
          <li>· 只学习有把握的稳定内容，拿不准的一律不采纳</li>
          <li>· 新笔记只写入沉淀笔记目录，不覆盖你的原始文件</li>
          <li>· 每一轮都可以整轮撤销</li>
        </ul>
        <p className="mt-1.5 text-ui-xs" data-testid="learning-safety-rejected">
          {c.rejected > 0
            ? `另有 ${c.rejected} 条想法因证据不够确定而没有采纳，明细见技术记录。`
            : "这一轮没有需要搁置的存疑内容。"}
        </p>
      </div>
      {/* 三列内容区（J10） */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2" data-testid="learning-three-cols">
        <div className="rounded-workspace-panel border border-border bg-header p-3">
          <div className="mb-1.5 flex items-center gap-1.5 text-ui-sm font-medium"><BrainCircuit className="size-4" />这次学到了什么</div>
          {learned.length ? learned.slice(0, 6).map((l, i) => (
            <div key={i} className="flex gap-1.5 text-ui-sm"><span className="text-foreground-subtle">·</span><span>{l}</span></div>
          )) : <p className="text-ui-sm text-foreground-subtle">没有发现足够稳定的新习惯。</p>}
        </div>
        <div className="rounded-workspace-panel border border-border bg-header p-3">
          <div className="mb-1.5 flex items-center gap-1.5 text-ui-sm font-medium"><Sparkles className="size-4" />会带来哪些提升</div>
          {improvements.length ? improvements.slice(0, 6).map((l, i) => (
            <div key={i} className="flex gap-1.5 text-ui-sm"><span className="text-foreground-subtle">·</span><span>{l}</span></div>
          )) : <p className="text-ui-sm text-foreground-subtle">本轮没有新增方法或笔记。</p>}
        </div>
      </div>
      <div className="rounded-workspace-panel border border-border bg-header p-3">
        <div className="mb-1.5 flex items-center gap-1.5 text-ui-sm font-medium"><ListChecks className="size-4" />下次会怎样帮你</div>
        <div className="grid grid-cols-1 gap-1 md:grid-cols-2">
          {nextHelp.length ? nextHelp.slice(0, 4).map((l, i) => (
            <label key={i} className="flex items-start gap-1.5 text-ui-sm"><CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-emerald-500" /><span>{l}</span></label>
          )) : <p className="text-ui-sm text-foreground-subtle">本轮没有新增内容，一切保持原样。</p>}
        </div>
      </div>
      {/* 技术记录折叠（J11：内嵌渲染原始 REPORT.md） */}
      <details className="rounded-workspace-panel border border-border bg-header p-3" data-testid="learning-tech-record" open={techOpen}>
        <summary className="flex cursor-pointer items-center gap-1.5 text-ui-sm font-medium" onClick={(e) => { e.preventDefault(); setTechOpen(!techOpen); }}>
          <ChevronDown className={`size-4 transition-transform ${techOpen ? "rotate-180" : ""}`} />技术记录（原始报告）
        </summary>
        {techOpen ? <div className="mt-2 max-h-80 overflow-auto rounded border border-border bg-background p-3"><MdLite text={reportMarkdown} /></div> : null}
      </details>
    </div>
  );
}

// ═══ 主面板 ═══
export function LearningIterationPanel() {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as LearningSvc;
  const ready = Boolean(svc.learningStatus && svc.learningList);
  const [status, setStatus] = useState<LearningStatusPayload | null>(null);
  const [records, setRecords] = useState<RecordSummary[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [acting, setActing] = useState(false); // 动作进行中（J2 禁用条件）
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [unavailable, setUnavailable] = useState(false); // J15 未初始化兜底面
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    if (!svc.learningStatus || !svc.learningList) return;
    const [st, ls] = await Promise.allSettled([svc.learningStatus(), svc.learningList()]);
    if (st.status === "fulfilled") setStatus(st.value);
    if (ls.status === "fulfilled") {
      const v = ls.value as { records?: RecordSummary[]; ok?: boolean; error?: string };
      if (Array.isArray(v.records)) { setRecords(v.records); setUnavailable(false); }
      else if (v.ok === false) { setUnavailable(true); setRecords((r) => r ?? []); }
    }
  }, [svc]);
  // J13：5s 并行轮询 status+records；动作后即时刷新
  useEffect(() => {
    void refresh();
    pollRef.current = setInterval(() => { void refresh(); }, POLL_MS);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [refresh]);
  // J13：选中记录消失→自动清选回总览
  useEffect(() => {
    if (selectedId && records && !records.some((r) => r.id === selectedId)) setSelectedId(null);
  }, [records, selectedId]);

  const runQueue = async () => {
    setActing(true); setNotice(null);
    try {
      const r = await svc.learningQueue?.({});
      if (r && r.ok === false) setNotice({ kind: "err", text: r.message ?? "这一刻无法开始学习" });
      else setNotice({ kind: "ok", text: "已加入本轮学习队列" });
      await refresh();
    } finally { setActing(false); }
  };
  const runCancel = async () => {
    setActing(true); setNotice(null);
    try {
      const r = await svc.learningCancel?.({});
      setNotice({ kind: "ok", text: r?.message ?? "已请求停止" });
      await refresh();
    } finally { setActing(false); }
  };
  const runRollbackLatest = async () => {
    if (!status?.latest) return;
    setActing(true); setNotice(null);
    try {
      await svc.learningRollback?.({ id: status.latest.id });
      setNotice({ kind: "ok", text: "最近一轮已整体回滚" });
      await refresh();
    } catch {
      setNotice({ kind: "err", text: "回滚没有执行：内容在后续又发生了变化，或本轮没有可回滚的变更" });
    } finally { setActing(false); }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return records ?? [];
    return (records ?? []).filter((r) => (r.displayName ?? "").toLowerCase().includes(q) || (r.title ?? "").toLowerCase().includes(q)); // J12 不区分大小写子串
  }, [records, query]);
  const s = status;
  // J2 立即学习禁用条件：未启用/运行中/排队中/动作进行中
  const queueDisabled = !s || !s.enabled || s.running || s.queued || acting;
  const cancelVisible = Boolean(s && (s.running || s.queued)); // J2 取消等待仅 running/queued 出现
  const metricCards = s ? [
    { label: "最近成功时间", value: fmtTime(s.lastSuccessfulAt), testId: "learning-metric-last" },
    { label: "今日资格", value: ({ "can-check": "可检查", "done-today": "今日已完成", queued: "已排队", disabled: "已关闭" } as const)[s.eligibleToday], testId: "learning-metric-elig" },
    { label: "基线进度", value: s.baselineComplete ? "100%（历史基线已完成）" : `${s.baselineProgress}%`, testId: "learning-metric-baseline" },
    { label: "下一批数据量", value: `${s.pendingSourceCount} 个变化来源`, testId: "learning-metric-pending" },
  ] : [];
  const latest = s?.latest ?? null;
  const stageDone = latest ? latest.status === "completed" || latest.status === "rolled_back" : false; // J5 三态

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center p-6" data-testid="learning-unavailable">
        <div className="max-w-md rounded-workspace-panel border border-border bg-header p-5 text-center">
          <GraduationCap className="mx-auto size-6 text-foreground-subtle" />
          <p className="mt-2 text-ui-sm font-medium">学习迭代暂时不可用</p>
          <p className="mt-1 text-ui-xs text-foreground-subtle">学习迭代运行时尚未初始化（桥连接后自动恢复）。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 gap-3" data-testid="learning-panel">
      {/* 记录侧栏（J12） */}
      <aside className="flex w-60 shrink-0 flex-col gap-2 rounded-workspace-panel border border-border bg-header p-2" data-testid="learning-sidebar">
        <button type="button" data-testid="learning-overview-btn"
          className={`w-full rounded px-2 py-1.5 text-left text-ui-sm font-medium ${!selectedId ? "bg-selected text-foreground" : "hover:bg-selected"}`}
          onClick={() => setSelectedId(null)}>
          总览
        </button>
        <div className="flex items-center gap-1.5 rounded border border-border px-2 py-1">
          <Search className="size-3.5 text-foreground-subtle" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索记录" data-testid="learning-search"
            className="w-full bg-transparent text-ui-sm outline-none placeholder:text-foreground-subtle" />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto" data-testid="learning-record-list">
          {filtered.length ? filtered.map((r) => (
            <button type="button" key={r.id} data-testid="learning-record-item"
              className={`flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-left text-ui-sm ${selectedId === r.id ? "bg-selected" : "hover:bg-selected"}`}
              onClick={() => setSelectedId(r.id)}>
              <RecordIcon status={r.status} />
              <span className="min-w-0 flex-1 truncate">{r.displayName || r.id}</span>
            </button>
          )) : (
            <div className="px-2 py-4 text-ui-xs text-foreground-subtle" data-testid="learning-record-empty">
              {query ? "没有匹配的记录，换个关键词试试。" : records && records.length === 0 ? "还没有学习记录。完成第一次学习后，成果会出现在这里。" : ""}
            </div>
          )}
        </div>
      </aside>
      {/* 主区 */}
      <div className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
        {notice ? (
          <div className={`rounded border px-3 py-1.5 text-ui-sm ${notice.kind === "ok" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "border-red-500/40 bg-red-500/10 text-red-600 dark:text-red-300"}`} data-testid="learning-notice">
            {notice.text}
          </div>
        ) : null}
        {unavailable && !s ? (
          <div className="rounded-workspace-panel border border-border bg-header p-5 text-center text-ui-sm text-foreground-subtle" data-testid="learning-disabled-fallback">
            学习迭代运行时尚未初始化。
          </div>
        ) : selectedId ? (
          <RecordDetail id={selectedId} svc={svc} onBack={() => setSelectedId(null)} />
        ) : (
          <>
            {/* 状态卡（J2） */}
            <section className="rounded-workspace-panel border border-border bg-header p-4" data-testid="learning-status-card">
              <div className="flex items-center gap-2">
                <GraduationCap className="size-5" />
                <h2 className="text-ui-lg font-semibold">学习迭代</h2>
                {s ? <StatusBadge status={s.status} /> : null}
                {s?.running ? <span className="flex items-center gap-1 text-ui-xs text-foreground-subtle"><Loader2 className="size-3 animate-spin" />进行中</span> : null}
              </div>
              <p className="mt-1.5 text-ui-sm text-foreground-subtle" data-testid="learning-message">{s?.message ?? "正在读取学习状态…"}</p>
              <div className="mt-3 flex items-center gap-2">
                <button type="button" data-testid="learning-queue-btn" disabled={queueDisabled}
                  className="flex items-center gap-1.5 rounded bg-selected px-3 py-1.5 text-ui-sm font-medium hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                  onClick={() => void runQueue()}>
                  <Sparkles className="size-3.5" />立即学习
                </button>
                {cancelVisible ? (
                  <button type="button" data-testid="learning-cancel-btn" disabled={acting}
                    className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-ui-sm hover:bg-selected disabled:opacity-50"
                    onClick={() => void runCancel()}>
                    <XCircle className="size-3.5" />取消等待
                  </button>
                ) : null}
              </div>
            </section>
            {/* 4 指标卡（J3） */}
            <section className="grid grid-cols-2 gap-2 md:grid-cols-4" data-testid="learning-metric-cards">
              {metricCards.map((m) => (
                <div key={m.label} className="rounded-workspace-panel border border-border bg-header p-3" data-testid={m.testId}>
                  <div className="text-ui-xs text-foreground-subtle">{m.label}</div>
                  <div className="mt-1 text-ui-base font-semibold">{m.value}</div>
                </div>
              ))}
            </section>
            {/* 最新一轮 5 指标带（J4） */}
            {latest ? (
              <section className="rounded-workspace-panel border border-border bg-header p-4" data-testid="learning-latest-metrics">
                <div className="flex items-center justify-between">
                  <h3 className="text-ui-sm font-medium">最近一轮 · {latest.displayName || latest.title}</h3>
                  <StatusBadge status={latest.status} testId="learning-latest-badge" />
                </div>
                <div className="mt-2 grid grid-cols-5 gap-2">
                  {latestMetrics(latest.counts).map((m) => (
                    <div key={m.key} className="rounded border border-border px-2 py-1.5 text-center">
                      <div className="text-ui-base font-semibold">{m.value}</div>
                      <div className="text-ui-xs text-foreground-subtle">{m.label}</div>
                    </div>
                  ))}
                </div>
                {/* 七阶段流程条（J5：最近一轮 completed/rolled_back 全勾；running 第 3 格转圈；idle 全空） */}
                <div className="mt-3 flex items-center gap-1" data-testid="learning-stage-bar" role="img"
                  aria-label={"流程进度：" + (s?.running ? "进行到第 3 步" : stageDone ? "七步全部完成" : "尚未开始")}>
                  {STAGE_BAR.map((name, i) => (
                    <div key={name} className="flex flex-1 flex-col items-center gap-1">
                      <div className={`flex size-6 items-center justify-center rounded-full border text-ui-xs ${
                        s?.running && i === 2 ? "border-blue-500 text-blue-500" : stageDone ? "border-emerald-500 bg-emerald-500 text-white" : "border-border text-foreground-subtle"}`}>
                        {s?.running && i === 2 ? <Loader2 className="size-3 animate-spin" /> : stageDone ? <CheckCircle2 className="size-3.5" /> : i + 1}
                      </div>
                      <span className="text-center text-ui-xs text-foreground-subtle">{name}</span>
                    </div>
                  ))}
                </div>
                {latest.canRollback ? (
                  <button type="button" data-testid="learning-rollback-latest" disabled={acting}
                    className="mt-3 flex items-center gap-1.5 rounded border border-border px-2.5 py-1 text-ui-xs hover:bg-selected disabled:opacity-50"
                    onClick={() => void runRollbackLatest()}>
                    <RotateCcw className="size-3" />回滚最近一轮
                  </button>
                ) : null}
              </section>
            ) : null}
            {/* 最近报告摘要卡（J6） */}
            {latest && latest.counts ? (
              <section className="rounded-workspace-panel border border-border bg-header p-4" data-testid="learning-latest-summary">
                <div className="flex items-center gap-2 text-ui-sm font-medium"><ClipboardList className="size-4" />最近报告摘要</div>
                <p className="mt-1 text-ui-xs text-foreground-subtle">
                  记住了 {latest.counts.memoriesCreated + latest.counts.memoriesUpdated + latest.counts.memoriesDisabled} 条 ·
                  掌握了 {latest.counts.skillsCreated + latest.counts.skillsUpdated} 个方法 ·
                  沉淀了 {latest.counts.knowledgeNotesCreated + latest.counts.knowledgeNotesUpdated} 篇笔记 ·
                  搁置了 {latest.counts.rejected} 条存疑内容 · {fmtTime(latest.finishedAt)}
                </p>
                <button type="button" data-testid="learning-open-latest"
                  className="mt-2 rounded border border-border px-2.5 py-1 text-ui-xs hover:bg-selected"
                  onClick={() => setSelectedId(latest.id)}>
                  查看完整报告
                </button>
              </section>
            ) : null}
            {s && !s.enabled ? (
              <section className="rounded-workspace-panel border border-border bg-header p-4 text-ui-sm text-foreground-subtle" data-testid="learning-disabled-hint">
                学习迭代当前已关闭。可在「设置 → 通用 → 学习迭代」重新打开。
              </section>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
