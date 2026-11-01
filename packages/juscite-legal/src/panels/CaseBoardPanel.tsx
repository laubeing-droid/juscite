// 【步骤4·#3 案件看板】看板日历面（RE-3-案件看板.md §3.5 四段骨架；补齐件=行1-7 骨架/行12-17+26 重要提醒卡/
// 行27-29 月历三源+色点+折叠摘要/行32 删除确认区分/行35 案内待办卡；
// 补齐件2=行1 问候回退称谓/行2 三开关面/行29 默认折叠/行38 待办汇总卡/行40-44 状态机面+行47/48 筛选工具栏；
// 补齐件3=行12/13 重要位并时间线源+行64 案件集口径/行45-46 拖拽序+四排序键/行49-57 案件卡字段格·dim·
// 键盘可达·右键菜单·删除·多选·空态三层·列表视图/行61-67 域 tabs+计数+状态脊色/行68 图例/行70 近期日程
// 分组/行71 今日焦点/行92 无外发通道横幅；
// 补齐件4（r9 逐行终查回填）=行24 开庭 session 去重并时间线显示路径/行30 右键日程编辑删除菜单/
// 行48 工具栏关=强制 grid+状态序+升序全口径/行55 工具栏关自动退多选/行62 点开刑事案自动切 tab/
// 行66 列表行最近期限风险徽章。诚实边界：行49 抽取态脚注随 #6 产物计数接入后补（不伪造）；
// 行51 拖拽把手样式按本面板自绘（CB className 语义等量、视觉素材自绘）；
// 行62 导入自动切随建账面（本面板无导入入口，不伪造）。
// 数据经桥 matter* 桥面（MatterLite 过渡态，桥库翻牌后本组件仅换服务面）；文案全部自写（表达隔离）。
// 确定性纪律（§3.6）：日期一律本地日历日字符串比较；窗口/阶梯/色点/重要位走 boardCalendar/boardImportant 纯函数。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle, Bell, BellOff, BellRing, CalendarClock, CalendarDays, Car, ChevronDown, ChevronUp,
  Gavel, ListTodo, Pencil, Plus, ShieldAlert, Trash2,
} from "lucide-react";
import { useServices } from "../ui-kit.js";
import type { CaseEventProto } from "../kernel/caseTimelineModel.js";
import {
  BOARD_DEADLINE_TIERS, boardCellDotColor, boardDayDiff, boardDeadlineLadder, boardMonthCells,
  boardNextCaseNode, boardShapeTimelineRows, boardTodayStr,
} from "./boardCalendar.js";
import {
  BOARD_SCAN_INTERVAL_MS, boardFireLabel, boardFireMomentMs, boardTimelineReminderInputs,
  scanBoardReminders,
} from "./boardReminder.js";
import {
  briefingLevel, buildImportantReminders, boardDeleteConfirmCopy,
  type ImportantInput, type ImportantKind,
} from "./boardImportant.js";
// 【补齐件2·状态机面】11 档单源色表/推断链/locked 展示公式/排序桶（对拍行 40-44；boardStatus.ts 纯模型）
import {
  BOARD_STATUS_DEFS, boardDisplayStatus, boardSignalsFromRows, boardSortCasesByBucket,
  boardStatusChip, inferBoardWorkflowStatus,
} from "./boardStatus.js";
// 【补齐件3·案件列表面】域分类/四排序键/拖拽序/近期日程分组/今日焦点/案件集口径（行45-46/49/52/61-64/65/67/70/71）
import {
  BOARD_DOMAIN_TABS, BOARD_SORT_KEYS, boardApplyDragOrder, boardCaseGate, boardDeadlineRiskOf,
  boardDragOrderSeq, boardFilingDateOf, boardFocusItem, boardNextHearingDateOf, boardRecentGroups,
  boardSortCasesByKey, boardStatusWeight, boardYuan, filterCasesByDomain, isCriminalCase,
  type BoardDeadlineRisk, type BoardDomainTab, type BoardSortKey,
} from "./boardCaseList.js";
// 【补齐件4·行24】开庭 session 键去重并时间线显示路径（此前纯函数+自测在库、接线缺位）
import { boardDedupTimelineHearings } from "./boardPreservation.js";
// 【步骤4·#5 冲突查重】案件冲突复核卡（P2 先落复核卡与结论；仅待复核渲染 A5/H1）
import { ConflictReviewCard } from "./ConflictReviewCard.js";

export interface BoardCase {
  id: string; name: string;
  cause?: string; caseNo?: string;
  court?: string; plaintiffs?: string[]; defendants?: string[]; // 行47 筛选面字段
  courtType?: string;            // 行49：「法院」|「仲裁委」label 切换
  judges?: string[];             // 行49：承办法官·仲裁员
  claimAmountCents?: number | null; // 行46/49：诉讼金额（整型分）
  sortOrder?: number | null;     // 行45：拖拽序（null=新案追加尾）
  workflowStatus?: string | null; workflowLocked?: boolean;
  updatedAt?: string;
}
export interface BoardEvent {
  id: string; date: string; title: string; note: string | null;
  caseId: string | null; kind: string; location: string;
  startAt: string | null; endAt: string | null; trip: string | null;
  remind: boolean; remindMinutes: number; createdAt: string;
}
export interface BoardTodo {
  id: string; caseId: string | null; title: string; done: boolean;
  doneAt: string | null; dueDate: string | null; createdAt: string; updatedAt: string;
}

// kind 徽章（对拍行 81 自定词表；值单源在桥 matter_service.BOARD_KINDS，展示词与配色自绘）
const KIND_BADGE: Record<string, { label: string; cls: string }> = {
  hearing: { label: "庭审", cls: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300" },
  deadline: { label: "截止", cls: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
  schedule: { label: "日程", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
};
// 月历色点配色（boardCellDotColor 的 Tailwind 映射；对拍行 28）
const DOT_CLS: Record<string, string> = {
  red: "bg-red-500", amber: "bg-amber-400", blue: "bg-blue-500",
  purple: "bg-purple-500", green: "bg-emerald-500", gray: "bg-gray-400",
};
// 重要位五型图标（对拍行 17：开庭/待办/独立日程/其他期限+保全盾警型随 #4/#6 保全源启用）
const KIND_ICON: Record<string, typeof Gavel> = {
  hearing: Gavel, todo: ListTodo, manual: CalendarClock, deadline: AlertTriangle,
};
const TONE_CLS: Record<string, string> = {
  red: "text-red-600 dark:text-red-400", amber: "text-amber-600 dark:text-amber-400", gray: "text-foreground-subtle",
};
const WEEK_HEADS = ["一", "二", "三", "四", "五", "六", "日"];

// ── 功能开关注册表（对拍行 2：注册表+默认值+localStorage per-device；面渲染于看板头内联——
// 单机无独立设置页，与 CB「设置页自动渲染」的位差如实注记）──
// 滴答同步本版不做（§5）：开关位渲染但禁用+注记，不伪造可用行为。
const BOARD_SWITCHES = [
  { key: "filterToolbar", label: "筛选工具栏", def: false, wired: true },
  { key: "boardAssistant", label: "看板简报", def: true, wired: true },
  { key: "ticktick", label: "滴答类待办同步", def: false, wired: false },
] as const;

function lsGet(key: string): string | null {
  try { return window.localStorage.getItem(key); } catch { return null; }
}
function lsSet(key: string, v: string): void {
  try { window.localStorage.setItem(key, v); } catch { /* 隐私模式等静默 */ }
}

// 问候五档（对拍行 1：<6 深夜/<12 上午/<14 中午/<18 下午/其余晚上；措辞自写）
function greetingOf(hour: number): string {
  if (hour < 6) return "深夜好";
  if (hour < 12) return "上午好";
  if (hour < 14) return "中午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}

// 待办日期徽章三色三文案（对拍行 37：MM-DD·逾期N天 / 今天 / N天后）
function todoBadge(due: string, today: string): { cls: string; text: string } {
  const d = boardDayDiff(today, due);
  if (d === null) return { cls: "text-foreground-subtle", text: due };
  if (d < 0) return { cls: "text-red-600 dark:text-red-400", text: `${due.slice(5)} · 逾期${-d}天` };
  if (d <= 7) return { cls: "text-amber-600 dark:text-amber-400", text: d === 0 ? "今天" : `${d}天后` };
  return { cls: "text-blue-600 dark:text-blue-400", text: `${d}天后` };
}

// 当事人摘要（行49：原告 v 被告+等N人；措辞自写）
function partySummary(c: BoardCase): string {
  const ps = c.plaintiffs ?? [];
  const ds = c.defendants ?? [];
  if (!ps.length && !ds.length) return "";
  const side = (a: string[]): string => (a.length === 0 ? "-" : a.length === 1 ? (a[0] ?? "") : `${a[0] ?? ""} 等${a.length}人`);
  return `原告 ${side(ps)} 诉 被告 ${side(ds)}`;
}

// 260ms 页面入场动画（对拍行 4；keyframes 一次性注入）
let boardAnimInjected = false;
function ensureBoardAnimStyle(): void {
  if (boardAnimInjected || typeof document === "undefined") return;
  boardAnimInjected = true;
  const st = document.createElement("style");
  st.textContent = "@keyframes jusciteBoardEnter{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}";
  document.head.appendChild(st);
}

// 原生系统通知（桌面壳=Electron/Chromium 系统通知；浏览器 5173=Web 通知）。
// LX 对拍行 85 语义：isSupported 检查、异常静默不崩、未授权不强弹（授权请求须用户手势，
// 随首次保存日程动作请求一次）。
let boardNotifPermAsked = false;
export function fireBoardNotification(title: string, body: string): boolean {
  try {
    if (typeof window === "undefined" || !("Notification" in window)) return false;
    if (Notification.permission !== "granted") return false;
    new Notification(title, { body });
    return true;
  } catch { return false; }
}
function requestBoardNotifPermissionOnce(): void {
  try {
    if (boardNotifPermAsked || typeof window === "undefined" || !("Notification" in window)) return;
    if (Notification.permission !== "default") return;
    boardNotifPermAsked = true;
    void Notification.requestPermission().catch(() => {});
  } catch { /* 静默 */ }
}

interface EventDraft {
  id: string | null;
  title: string; date: string; kind: string; location: string;
  startAt: string; endAt: string; caseId: string; trip: string; note: string;
  remind: boolean; remindMinutes: number;
}

function draftOf(date: string): EventDraft {
  // 展示默认（对拍行 80）：起止 10:00-11:00、提前分钟 30、kind=日程
  return { id: null, title: "", date, kind: "schedule", location: "", startAt: "10:00", endAt: "11:00",
    caseId: "", trip: "", note: "", remind: true, remindMinutes: 30 };
}

export function CaseBoardPanel() {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as {
    matterList?: () => Promise<{ cases: BoardCase[] }>;
    matterUpdate?: (p: Record<string, unknown>) => Promise<BoardCase>; // 状态两写同语句（§3.3 桥面）；sortOrder 拖拽序写路径
    matterDelete?: (p: { id: string }) => Promise<{ deleted: string }>; // 行55：只删记录不动原文件夹（桥面已级联清待办/解绑日程）
    matterEventList?: () => Promise<{ events: BoardEvent[]; dayFireTime?: string }>;
    matterEventAdd?: (p: Record<string, unknown>) => Promise<BoardEvent>;
    matterEventUpdate?: (p: Record<string, unknown>) => Promise<BoardEvent>;
    matterEventDelete?: (p: { id: string }) => Promise<{ deleted: string }>;
    matterTodoList?: (p: Record<string, unknown>) => Promise<{ todos: BoardTodo[] }>;
    matterTodoAdd?: (p: Record<string, unknown>) => Promise<BoardTodo>;
    matterTodoSetDone?: (p: { id: string; done: boolean }) => Promise<BoardTodo>;
    matterTodoDelete?: (p: { id: string }) => Promise<{ deleted: string }>;
    // 【#4 时间线翻牌】案件阶段节点日期化/期限阶梯/日历并入的时间线数据源（只读）
    caseEventAllList?: () => Promise<{ events: CaseEventProto[] }>;
  };

  const [cases, setCases] = useState<BoardCase[]>([]);
  const [events, setEvents] = useState<BoardEvent[]>([]);
  const [todos, setTodos] = useState<BoardTodo[]>([]);
  const [caseEvents, setCaseEvents] = useState<CaseEventProto[]>([]);
  const [dayFireTime, setDayFireTime] = useState("09:00");
  const [scanNonce, setScanNonce] = useState(0); // 保存/增删后即时触发一轮扫描（对拍行 22 单机裁量）
  const [loadError, setLoadError] = useState<string | null>(null);
  const [bridgeReady, setBridgeReady] = useState(true);
  const today = useMemo(() => boardTodayStr(), []);
  const [cursor, setCursor] = useState(() => {
    const n = new Date();
    return { y: n.getFullYear(), m: n.getMonth() + 1 };
  });
  const [selectedDate, setSelectedDate] = useState(today);
  const [draft, setDraft] = useState<EventDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  // 补齐件：卡宽/开关/折叠/案内待办卡
  const [cardWidth, setCardWidth] = useState<"half" | "full">(() => (lsGet("juscite.board.cardWidth") === "full" ? "full" : "half"));
  const [assistantOn, setAssistantOn] = useState(() => lsGet("juscite.board.switch.boardAssistant") !== "0");
  // 行29：默认折叠=CB 口径（键缺省=折叠；显式 "0" 才展开——per-device 持久化语义不变）
  const [calendarCollapsed, setCalendarCollapsed] = useState(() => lsGet("juscite.board.calendarCollapsed") !== "0");
  const [selectedCaseId, setSelectedCaseId] = useState("");
  const [todoTitle, setTodoTitle] = useState("");
  const [todoDue, setTodoDue] = useState("");
  const [todoError, setTodoError] = useState<string | null>(null);
  const [todoOpError, setTodoOpError] = useState<string | null>(null);
  const [doneOpen, setDoneOpen] = useState(false);
  // 补齐件2：筛选工具栏（行2 开关+行47 面）/状态机面（行40-44）/待办汇总（行38）
  const [filterOn, setFilterOn] = useState(() => lsGet("juscite.board.switch.filterToolbar") === "1");
  const [filterStatuses, setFilterStatuses] = useState<string[]>([]);
  const [filterCourt, setFilterCourt] = useState("");
  const [filterParty, setFilterParty] = useState("");
  const [statusMenuFor, setStatusMenuFor] = useState<string | null>(null);
  const [caseToast, setCaseToast] = useState<string | null>(null);
  const [caseOpError, setCaseOpError] = useState<string | null>(null);
  // 补齐件3：域 tab/视图/排序（行62-63/65/52/46）/右键菜单（行54）/多选删除（行55-56）/拖拽（行45/51）
  const [domainTab, setDomainTab] = useState<BoardDomainTab>("civil");
  const [viewMode, setViewMode] = useState<"grid" | "list">(() => (lsGet("juscite.board.viewMode") === "list" ? "list" : "grid"));
  const [sortKey, setSortKey] = useState<BoardSortKey | "default">("default");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [ctxMenu, setCtxMenu] = useState<{ caseId: string; x: number; y: number } | null>(null);
  // 行30：右键日程菜单（编辑/删除两项；与案件卡右键菜单同型防溢出+多路关闭）
  const [eventMenu, setEventMenu] = useState<{ eventId: string; x: number; y: number } | null>(null);
  const [multiSelect, setMultiSelect] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [dragArmedId, setDragArmedId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const dragSeqRef = useRef<BoardCase[]>([]); // 拖放落位时的全序快照（boardDragOrderSeq 结果）

  useEffect(() => { ensureBoardAnimStyle(); }, []);

  const reload = useCallback(() => {
    if (!svc.matterEventList) { setBridgeReady(false); return; }
    Promise.all([
      svc.matterEventList().catch((e: unknown) => { throw e; }),
      svc.matterList?.().catch(() => ({ cases: [] })),
      svc.matterTodoList?.({}).catch(() => ({ todos: [] })),
      svc.caseEventAllList?.().catch(() => ({ events: [] as CaseEventProto[] })),
    ])
      .then(([ev, cs, td, ce]) => {
        setEvents(ev?.events ?? []);
        setCases(cs?.cases ?? []);
        setTodos(td?.todos ?? []);
        setCaseEvents(ce?.events ?? []);
        if (ev?.dayFireTime) setDayFireTime(ev.dayFireTime);
        setLoadError(null);
        setBridgeReady(true);
      })
      .catch((e: unknown) => setLoadError(String((e as Error)?.message ?? e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { reload(); }, [reload]);
  // 案内待办卡默认选中第一案
  useEffect(() => {
    setSelectedCaseId((prev) => (prev && cases.some((c) => c.id === prev) ? prev : cases[0]?.id ?? ""));
  }, [cases]);

  const cells = useMemo(() => boardMonthCells(cursor.y, cursor.m), [cursor]);
  const caseName = useCallback((id: string | null) => cases.find((c) => c.id === id)?.name ?? null, [cases]);

  // 时间线行映射（#4 翻牌：RE-3 对拍 84 案件阶段节点日期化 + 对拍 27 三源日历的「案件自动抽取」源 +
  // 对拍 91 阶梯的保全/还款期期限行——原「#4/#6 接入后并入」注记随 #4 落地兑现）
  const timelineKindOf = useCallback((eventType: string) => {
    if (eventType === "开庭" || eventType === "二审开庭" || eventType === "开庭排期") return "hearing";
    if (eventType === "还款期" || eventType === "保全" || eventType === "期限登记" || eventType === "执行立案") return "deadline";
    return "schedule";
  }, []);
  const timelineNodeRows = useMemo(
    () => caseEvents
      .filter((c) => c.date)
      .map((c) => ({ id: `cev:${c.eventId}`, ref: `cev:${c.eventId}`, date: c.date as string, title: c.eventType, caseId: c.matterId, kind: timelineKindOf(c.eventType), expiresAt: c.expiresAt ?? null, updatedAt: c.updatedAt })),
    [caseEvents, timelineKindOf],
  );
  // 行24（补齐件4）：同案同 session 键的开庭族行坍缩为最新文档一行（CB 同键最新权威），
  // 此前纯函数在库未接线——同日两文档重复登记「开庭」会双份上屏。二审开庭自成一族不与一审互吞。
  const dedupedTimelineRows = useMemo(() => boardDedupTimelineHearings(timelineNodeRows), [timelineNodeRows]);

  // 时间线行整编两份视图（boardShapeTimelineRows 纯函数，E14 对拍）：
  //   日历视图=仅孪生让位（建案等行政事实行仍上屏，#4 翻牌日历并入语义）；
  //   阶段节点视图=孪生让位+行政登记行不作节点（对拍行 84 节点=里程碑语义）。
  // 两份视图输入均先过行 24 开庭去重（先文档权威、后孪生/行政整编）。
  const calTimelineRows = useMemo(
    () => boardShapeTimelineRows(dedupedTimelineRows, events, false),
    [dedupedTimelineRows, events],
  );
  const stageTimelineRows = useMemo(
    () => boardShapeTimelineRows(dedupedTimelineRows, events, true),
    [dedupedTimelineRows, events],
  );

  // ── 状态机面（行40-44；补齐件3 上移：案件集口径 gate 依赖展示态）──
  // 每案推断线索=案绑时间线阶段行+案绑开庭日程；推断链/展示公式/排序桶全在 boardStatus 纯模型。
  const inferredByCase = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of cases) {
      const rows = [
        ...stageTimelineRows.filter((t) => t.caseId === c.id).map((t) => ({ type: t.title, date: t.date })),
        ...events.filter((e) => e.caseId === c.id && e.kind === "hearing").map((e) => ({ type: "开庭", date: e.date })),
      ];
      m.set(c.id, inferBoardWorkflowStatus(boardSignalsFromRows(rows), today));
    }
    return m;
  }, [cases, stageTimelineRows, events, today]);
  const displayStatusOf = useCallback((c: BoardCase): string => boardDisplayStatus({
    locked: c.workflowLocked === true,
    userValue: c.workflowStatus ?? null,
    userHistory: null, // 单机无 LLM 历史值——兜底位参数保留（§3.3 三态公式对齐）
    inferred: inferredByCase.get(c.id) ?? "接案",
  }), [inferredByCase]);

  // 案件集口径（对拍行 64；CB：提醒集「非已结案非已调解」/日历集「非已结案」）——只作用案绑行：
  // 案绑日程与时间线抽取行按所属案件展示态过门；独立日程/待办不属于案件集，不过门。
  const statusById = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of cases) m.set(c.id, displayStatusOf(c));
    return m;
  }, [cases, displayStatusOf]);
  const calEvents = useMemo(
    () => events.filter((e) => !e.caseId || boardCaseGate(statusById.get(e.caseId), "calendar")),
    [events, statusById],
  );
  const remEvents = useMemo(
    () => events.filter((e) => !e.caseId || boardCaseGate(statusById.get(e.caseId), "reminder")),
    [events, statusById],
  );
  const gateTimeline = useCallback(
    (view: "calendar" | "reminder") => calTimelineRows.filter((t) => !t.caseId || boardCaseGate(statusById.get(t.caseId) ?? null, view)),
    [calTimelineRows, statusById],
  );
  const calTimelineRowsCal = useMemo(() => gateTimeline("calendar"), [gateTimeline]);
  const calTimelineRowsRem = useMemo(() => gateTimeline("reminder"), [gateTimeline]);

  // 日历三源（对拍行 27）：日程（独立+案绑，案绑过行 64 日历集门）+带日期未完成待办+时间线行
  //（#4 翻牌并入，孪生已让位+过门）
  const dayEntries = useMemo(() => {
    const map = new Map<string, Array<{ kind: string; title: string; ref: string; todo?: BoardTodo; event?: BoardEvent }>>();
    const push = (date: string, kind: string, title: string, ref: string, entry: { todo?: BoardTodo; event?: BoardEvent }) => {
      const arr = map.get(date) ?? [];
      arr.push({ kind, title, ref, ...entry });
      map.set(date, arr);
    };
    for (const ev of calEvents) push(ev.date, ev.kind, ev.title, `evt:${ev.id}`, { event: ev });
    for (const td of todos) {
      if (td.done || !td.dueDate) continue;
      push(td.dueDate, "todo", td.title, `todo:${td.id}`, { todo: td });
    }
    for (const tn of calTimelineRowsCal) push(tn.date, tn.kind, tn.title, tn.ref, {});
    return map;
  }, [calEvents, todos, calTimelineRowsCal]);
  const byDate = useMemo(() => {
    const m = new Map<string, Array<{ kind: string; title: string; ref: string; todo?: BoardTodo; event?: BoardEvent }>>();
    for (const [date, arr] of dayEntries) {
      m.set(date, [...arr].sort((a, b) => a.kind.localeCompare(b.kind) || a.ref.localeCompare(b.ref)));
    }
    return m;
  }, [dayEntries]);
  const dayItems = byDate.get(selectedDate) ?? [];

  // 近 30 天日程（今天起）；空态两态（对拍行 82）——源=过行 64 日历集门的 calEvents
  const upcoming = useMemo(
    () => calEvents.filter((e) => e.date >= today && e.date <= shiftDay(today, 30)),
    [calEvents, today],
  );
  const allEnded = calEvents.length > 0 && upcoming.length === 0 && calEvents.every((e) => e.date < today);

  // 重要位（行 12/13）：案件源=开庭+保全两类（时间线行经 timelineKindOf 映射，非保全期限不进）+
  // 日程/待办合并 → buildImportantReminders（窗口/排序/截 12）。案绑行过行 64 提醒集门（排已结案+已调解）。
  const importantItems = useMemo(() => {
    const input: ImportantInput[] = [
      ...remEvents.map((e) => ({
        id: e.id,
        kind: (e.kind === "hearing" ? "hearing" : e.kind === "deadline" ? "deadline" : "manual") as ImportantKind,
        title: e.title, date: e.date,
        isPreservation: false, // 独立/案绑日程行无保全语义；保全标记只来自时间线抽取行
      })),
      // 时间线抽取行进重要位（补齐件3 接线：#4 翻牌后开庭/保全节点不再缺席重要位）。
      // 期限行到期基准与提醒引擎同源（boardTimelineReminderInputs）：保全/还款期优先 expires_at，
      // 还款/分期类回落行日期；无到期日不进（不猜年限，期限推算属抽取线）。
      ...calTimelineRowsRem.flatMap((t) => {
        const k = timelineKindOf(t.title);
        if (k === "schedule") return []; // 建案/任务登记等行政行不作提醒（CB 案件源=开庭+保全两类）
        const due = k === "hearing" ? t.date : (t.expiresAt ?? (/还款|分期/.test(t.title) ? t.date : null));
        if (!due) return [];
        return [{
          id: t.id,
          kind: k as ImportantKind,
          title: t.title, date: due,
          isPreservation: t.title === "保全",
        }];
      }),
      ...todos.filter((t) => !t.done && t.dueDate).map((t) => ({
        id: t.id, kind: "todo" as ImportantKind, title: t.title, date: t.dueDate as string, isPreservation: false,
      })),
    ];
    return buildImportantReminders(input, today);
  }, [remEvents, calTimelineRowsRem, timelineKindOf, todos, today]);
  const prominent = importantItems.filter((i) => i.urgency !== "normal");
  const others = importantItems.filter((i) => i.urgency === "normal");

  // 今日简报（行 7）：红→橙提醒→材料(随 #6)→更新→平静；anchor 面板内滚动
  const briefing = useMemo(
    () => briefingLevel({ important: importantItems, cases: cases.map((c) => ({ id: c.id, updatedAt: c.updatedAt ?? "" })) }),
    [importantItems, cases],
  );
  const jumpTo = useCallback((anchor: string) => {
    document.getElementById(`board-anchor-${anchor}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // 重要提醒卡自动翻页（行 26：5s/页、缓动、悬停停、到底回顶、不溢出不滚）
  const importantScrollRef = useRef<HTMLDivElement | null>(null);
  const importantHoverRef = useRef(false);
  useEffect(() => {
    const t = window.setInterval(() => {
      const el = importantScrollRef.current;
      if (!el || importantHoverRef.current) return;
      if (el.scrollHeight <= el.clientHeight + 2) return; // 不溢出不滚
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 2;
      if (atBottom) el.scrollTo({ top: 0, behavior: "smooth" });
      else el.scrollBy({ top: el.clientHeight, behavior: "smooth" });
    }, 5000);
    return () => window.clearInterval(t);
  }, [importantItems.length]);

  // 折叠态摘要（行 29）：近 30 天逾期+全部未来，天数升序（三源）
  const collapsedSummary = useMemo(() => {
    return [...dayEntries.entries()]
      .map(([date, arr]) => ({ date, daysLeft: boardDayDiff(today, date), first: arr[0], count: arr.length }))
      .filter((r) => r.daysLeft !== null && ((r.daysLeft < 0 && -r.daysLeft <= 30) || r.daysLeft >= 0))
      .sort((a, b) => (a.daysLeft ?? 0) - (b.daysLeft ?? 0) || a.date.localeCompare(b.date));
  }, [dayEntries, today]);

  const shiftMonth = (delta: number) => {
    setCursor((c) => {
      const n = new Date(c.y, c.m - 1 + delta, 1);
      return { y: n.getFullYear(), m: n.getMonth() + 1 };
    });
  };

  const openAddAt = useCallback((date: string) => {
    setFormError(null);
    setDraft(draftOf(date)); // 现取当日入参（防闭包跨天：日期由触发处显式给定）
  }, []);
  const openEdit = useCallback((ev: BoardEvent) => {
    setFormError(null);
    setDraft({
      id: ev.id, title: ev.title, date: ev.date, kind: ev.kind, location: ev.location,
      startAt: ev.startAt ?? "10:00", endAt: ev.endAt ?? "11:00",
      caseId: ev.caseId ?? "", trip: ev.trip ?? "", note: ev.note ?? "",
      remind: ev.remind, remindMinutes: ev.remindMinutes,
    });
  }, []);

  const saveDraft = useCallback(() => {
    if (!draft || saving) return;
    if (!draft.title.trim()) { setFormError("事项名不能为空"); return; }
    setSaving(true);
    setFormError(null);
    const payload: Record<string, unknown> = {
      date: draft.date, title: draft.title.trim(), kind: draft.kind,
      location: draft.location, startAt: draft.startAt || null, endAt: draft.endAt || null,
      caseId: draft.caseId || null, trip: draft.trip, note: draft.note || null,
      remind: draft.remind, remindMinutes: draft.remindMinutes,
    };
    const call = draft.id
      ? svc.matterEventUpdate?.({ id: draft.id, ...payload })
      : svc.matterEventAdd?.(payload);
    Promise.resolve(call)
      .then(() => {
        setDraft(null);
        setSaving(false);
        requestBoardNotifPermissionOnce(); // 授权请求须用户手势——挂在保存动作上一次
        reload();
        setScanNonce((n) => n + 1);
      })
      .catch((e: unknown) => { setSaving(false); setFormError(String((e as Error)?.message ?? e)); });
  }, [draft, reload, saving, svc]);

  // 删除确认文案区分（行 32）：本表全为手工记录（#4/#6 派生行走覆盖层、不落本表），
  // isAiDerived 现网恒 false；两分支文案在 boardDeleteConfirmCopy 单源+合成自测覆盖（F9）。
  const removeEvent = useCallback((ev: BoardEvent) => {
    if (!window.confirm(boardDeleteConfirmCopy(false, ev.title))) return;
    svc.matterEventDelete?.({ id: ev.id })
      .then(() => { reload(); setScanNonce((n) => n + 1); })
      .catch((e: unknown) => setFormError(String((e as Error)?.message ?? e)));
  }, [reload, svc]);

  // 出行与提醒卡开关提醒（逐条；对拍行 83/85）
  const toggleRemind = useCallback((ev: BoardEvent) => {
    svc.matterEventUpdate?.({ id: ev.id, remind: !ev.remind })
      .then(() => { reload(); setScanNonce((n) => n + 1); })
      .catch((e: unknown) => setFormError(String((e as Error)?.message ?? e)));
  }, [reload, svc]);

  // ── 提醒引擎宿主（等量 LX 引擎，进程内；RE-3 §3.4-5）──
  // 60s 周扫+保存/增删即扫（对拍行 22 单机裁量）；扫描窗口/去重/不补发全在 boardReminder 纯函数。
  // ⚠ 诚实边界：引擎随看板挂载运行（工作台关窗不扫描）；LX 为常驻主进程，常驻化随打包步骤收口。
  const firedRef = useRef<Set<string>>(new Set());
  const [engineNote, setEngineNote] = useState<string | null>(null);
  const displayStatusRef = useRef(displayStatusOf);
  displayStatusRef.current = displayStatusOf; // 扫描闭包内取最新展示态（不重挂 interval）
  useEffect(() => {
    if (!svc.matterEventList) return;
    let alive = true;
    const scan = async () => {
      try {
        const [ev, td, ce, cs] = await Promise.all([
          svc.matterEventList ? svc.matterEventList() : Promise.resolve({ events: [] as BoardEvent[] }),
          svc.matterTodoList ? svc.matterTodoList({}) : Promise.resolve({ todos: [] as BoardTodo[] }),
          svc.caseEventAllList?.().catch(() => ({ events: [] as CaseEventProto[] }))
            ?? Promise.resolve({ events: [] as CaseEventProto[] }),
          svc.matterList?.().catch(() => ({ cases: [] })) ?? Promise.resolve({ cases: [] }),
        ]);
        const nowMs = Date.now();
        // 案件集门（对拍行 64）：提醒面=已结案/已调解案件的案绑行不开火（独立行与待办不过门）。
        const gate = (caseId: string | null): boolean => !caseId || boardCaseGate(displayStatusRef.current(
          cs?.cases?.find((c) => c.id === caseId) ?? { id: caseId, name: "" }), "reminder");
        const remEvts = (ev?.events ?? []).filter((e) => gate(e.caseId));
        // #4 时间线节点→提醒（对拍 34/CB E1 补齐）：开庭/还款期/保全三族喂同一引擎；
        // 孪生让位+解封压制在 boardTimelineReminderInputs 纯函数（软删行已在上游过滤=覆盖同源）。
        const tlReminders = boardTimelineReminderInputs({
          caseEvents: (ce?.events ?? []).filter((c) => gate(c.matterId)),
          boardEvents: remEvts,
          caseNameOf: (id: string) => cs?.cases?.find((c) => c.id === id)?.name ?? null,
        });
        const r = scanBoardReminders({
          events: [...remEvts, ...tlReminders], todos: td?.todos ?? [], nowMs,
          firedKeys: firedRef.current, dayFireTime, fixedTitle: "Juscite 案件看板",
        });
        if (!alive) return;
        firedRef.current = r.firedKeys;
        let shown = 0;
        for (const f of r.fire) { if (fireBoardNotification(f.title, f.body)) shown += 1; }
        setEngineNote(shown > 0
          ? `刚弹出 ${shown} 条到点提醒（共命中 ${r.fire.length} 条）`
          : (r.fire.length > 0 ? `命中 ${r.fire.length} 条到点提醒，但系统通知未授权` : null));
      } catch { /* 读失败静默降级（读保空渲染，对拍行 60） */ }
    };
    void scan();
    const timer = window.setInterval(() => { void scan(); }, BOARD_SCAN_INTERVAL_MS);
    return () => { alive = false; window.clearInterval(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [svc, dayFireTime, scanNonce]);

  // 出行与提醒卡行集（今天起 30 天；出行行=trip 非空；提醒行=remind=1，按开火时刻升序）
  const tripRows = useMemo(
    () => events
      .filter((e) => e.trip && e.date >= today && e.date <= shiftDay(today, 30))
      .sort((a, b) => a.date.localeCompare(b.date) || (a.startAt ?? "").localeCompare(b.startAt ?? "")),
    [events, today],
  );
  const remindRows = useMemo(() => {
    const nowMs = Date.now();
    const rows = remEvents
      .filter((e) => e.remind)
      .map((e) => {
        const fireMs = boardFireMomentMs(e.date, e.startAt ?? dayFireTime);
        return { ev: e, fireMs };
      })
      // 卡片只列未来开火（已过/错过窗口的不再标「下一提醒」——错过不补发，引擎侧自会跳过）
      .filter((x): x is { ev: BoardEvent; fireMs: number } => x.fireMs !== null && x.fireMs >= nowMs);
    return rows.sort((a, b) => a.fireMs - b.fireMs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remEvents, dayFireTime]);
  const fmtNextFire = useCallback((fireMs: number) => {
    const d = new Date(fireMs);
    const hhmm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
    return `${boardFireLabel(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`, hhmm)}`;
  }, []);

  // 期限预警阶梯（对拍行 91）：待办+期限日程+#4 时间线带到期日行（保全/还款期，对拍行 59 增补兑现）；
  // 行66（补齐件4）期限风险徽章同源行集（补 caseId——阶梯按桶计数、徽章按案取最近逾期）。
  const deadlineItems = useMemo(() => [
    ...todos.filter((t) => !t.done && t.dueDate).map((t) => ({ id: t.id, title: t.title, dueDate: t.dueDate as string, caseId: t.caseId ?? null })),
    ...events.filter((e) => e.kind === "deadline").map((e) => ({ id: e.id, title: e.title, dueDate: e.date, caseId: e.caseId ?? null })),
    ...caseEvents.filter((c) => c.expiresAt).map((c) => ({ id: c.eventId, title: c.eventType, dueDate: c.expiresAt as string, caseId: c.matterId })),
  ], [todos, events, caseEvents]);
  const ladder = useMemo(() => boardDeadlineLadder(deadlineItems, today), [deadlineItems, today]);
  const LADDER_META: Array<{ key: string; label: string; cls: string; testid: string }> = [
    { key: "overdue", label: "已逾期", cls: "bg-red-500", testid: "board-ladder-overdue" },
    { key: "d3", label: "3 日内", cls: "bg-red-400", testid: "board-ladder-d3" },
    { key: "d7", label: "7 日内", cls: "bg-amber-400", testid: "board-ladder-d7" },
    { key: "d30", label: "30 日内", cls: "bg-blue-400", testid: "board-ladder-d30" },
  ];

  // 今日焦点卡（行71；LL 等量：全案最近一条期限/日程，≤3 天红点否则琥珀，逾期即焦点，30 天窗无→空态）
  const focus = useMemo(
    () => boardFocusItem({
      deadlines: deadlineItems.map((d) => ({ id: d.id, title: d.title, date: d.dueDate, caseId: d.caseId })),
      events: calEvents.map((e) => ({ id: e.id, title: e.title, date: e.date, kind: e.kind, startAt: e.startAt, caseId: e.caseId })),
      todayStr: today,
      caseInfoOf: (caseId: string) => {
        const c = cases.find((x) => x.id === caseId);
        return c ? { name: c.name, caseNo: c.caseNo ?? null } : null;
      },
    }),
    [calEvents, cases, deadlineItems, events, today],
  );
  // 行66（补齐件4）：每案最近一条已逾期未完期限（LL 列表行红字徽章；无逾期不显——红只用于逾期）
  const riskByCase = useMemo(() => {
    const m = new Map<string, BoardDeadlineRisk>();
    for (const c of cases) {
      const r = boardDeadlineRiskOf(deadlineItems, c.id, today);
      if (r) m.set(c.id, r);
    }
    return m;
  }, [cases, deadlineItems, today]);

  // ── 状态机面（行40-44）：推断/展示公式已上移至案件集 gate 之前（displayStatusOf 单源）──
  // 手设=写枚举值（桥两写同语句翻 locked=1）；恢复自动=写 null（locked=0）。已结案出引导 toast（行43）。
  const setCaseStatus = useCallback((c: BoardCase, v: string | null) => {
    setCaseOpError(null);
    svc.matterUpdate?.({ id: c.id, workflowStatus: v })
      .then(() => {
        reload();
        setStatusMenuFor(null);
        if (v === "已结案") {
          setCaseToast("已标记为已结案——记得沉淀本案办案经验");
          window.setTimeout(() => setCaseToast((cur) => (cur?.startsWith("已标记为已结案") ? null : cur)), 4000);
        }
      })
      .catch((e: unknown) => setCaseOpError(String((e as Error)?.message ?? e)));
  }, [reload, svc]);
  // 筛选工具栏（行47/48）：开关关=不过滤（降级口径）；开=状态多选+法院下拉+当事人子串模糊+清空筛选
  const courts = useMemo(
    () => [...new Set(cases.map((c) => (c.court ?? "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh")),
    [cases],
  );
  const hasFilter = filterStatuses.length > 0 || filterCourt !== "" || filterParty.trim() !== "";
  // 域 tabs（行62/63/65：诉讼=全部/刑事=启发式/执行=状态过滤；计数徽章随 tab）
  const domainCounts = useMemo(() => ({
    civil: cases.length,
    criminal: cases.filter((c) => isCriminalCase(c)).length,
    execution: cases.filter((c) => displayStatusOf(c) === "执行中").length,
  }), [cases, displayStatusOf]);
  const domainCases = useMemo(
    () => filterCasesByDomain(cases, domainTab, (c) => isCriminalCase(c), (c) => displayStatusOf(c)),
    [cases, domainTab, displayStatusOf],
  );
  const visibleCases = useMemo(() => {
    if (!filterOn || !hasFilter) return domainCases; // 行48：工具栏关（或无筛选）=不过滤
    const party = filterParty.trim().toLowerCase();
    const wanted = new Set(filterStatuses);
    return domainCases.filter((c) => {
      if (wanted.size && !wanted.has(displayStatusOf(c))) return false;
      if (filterCourt && (c.court ?? "") !== filterCourt) return false;
      if (party && ![...(c.plaintiffs ?? []), ...(c.defendants ?? [])].some((x) => x.toLowerCase().includes(party))) return false;
      return true;
    });
  }, [domainCases, displayStatusOf, filterCourt, filterOn, filterParty, filterStatuses, hasFilter]);
  // 行48（补齐件4）：工具栏关=强制 grid+状态序+升序+不过滤，拖拽仍持久化——用户先开工具栏
  // 选列表视图/自定义排序再关掉时，残留档位不生效（CB 降级口径；再开工具栏即恢复原档位）。
  const effViewMode = filterOn ? viewMode : "grid";
  const effSortKey: BoardSortKey | "default" = filterOn ? sortKey : "default";
  const effSortDir = filterOn ? sortDir : "asc";
  // 排序（行44/45/46）：默认=拖拽序（已落 sort_order 时；已结案强制沉底+新案追加尾），无拖拽序=稳定桶
  //（桶内 updated 倒序）；选键=四排序键（null 沉底，同值 updated 兜底）。口径走行48 effective 值。
  const sortOrderOf = useCallback((c: BoardCase): number | null => (typeof c.sortOrder === "number" ? c.sortOrder : null), []);
  const anyDragOrder = useMemo(() => visibleCases.some((c) => typeof c.sortOrder === "number"), [visibleCases]);
  const orderedCases = useMemo(() => {
    if (effSortKey !== "default") {
      const keyRows = calTimelineRows.map((t) => ({ caseId: t.caseId, date: t.date, hearing: t.kind === "hearing", type: t.title }));
      const valueOf = (c: BoardCase): string | number | null => {
        if (effSortKey === "status") return boardStatusWeight(displayStatusOf(c));
        if (effSortKey === "amount") return typeof c.claimAmountCents === "number" ? c.claimAmountCents : null;
        if (effSortKey === "filedAt") return boardFilingDateOf(keyRows, c.id);
        return boardNextHearingDateOf(keyRows, c.id, today);
      };
      return boardSortCasesByKey(visibleCases, effSortKey, effSortDir, valueOf);
    }
    if (anyDragOrder) {
      return boardDragOrderSeq(visibleCases, (c) => displayStatusOf(c) === "已结案", sortOrderOf);
    }
    return boardSortCasesByBucket(visibleCases);
  }, [anyDragOrder, calTimelineRows, displayStatusOf, effSortDir, effSortKey, sortOrderOf, today, visibleCases]);
  // 案件段：下一节点（数据源口径同前注）
  const caseCards = useMemo(
    () => orderedCases.map(
      (c) => ({ case: c, next: boardNextCaseNode([...events, ...stageTimelineRows], c.id, today) }),
    ),
    [orderedCases, events, stageTimelineRows, today],
  );
  const dragSeq = useMemo(
    () => boardDragOrderSeq(visibleCases, (c) => displayStatusOf(c) === "已结案", sortOrderOf),
    [displayStatusOf, sortOrderOf, visibleCases],
  );
  dragSeqRef.current = dragSeq;
  // 行45/51：拖拽仅在 grid+默认序生效（排序键激活/列表视图/多选中关闭）——口径走行48 effective 值
  const dragEnabled = effViewMode === "grid" && effSortKey === "default" && !multiSelect;
  // 待办汇总（行38）：跨案未完成按案分组、组内创建倒序；无未完成待办整卡不渲染
  const aggGroups = useMemo(() => {
    const m = new Map<string, BoardTodo[]>();
    for (const t of todos) {
      if (t.done) continue;
      const arr = m.get(t.caseId ?? "") ?? [];
      arr.push(t);
      m.set(t.caseId ?? "", arr);
    }
    return [...m.entries()]
      .map(([cid, rows]) => [cid, [...rows].sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""))] as [string, BoardTodo[]])
      .sort((a, b) => (caseName(a[0]) ?? "￿").localeCompare(caseName(b[0]) ?? "￿", "zh"));
  }, [todos, caseName]);
  const aggCount = aggGroups.reduce((n, [, rows]) => n + rows.length, 0);

  // ── 案内待办卡（行 35）──
  const caseTodos = useMemo(() => todos.filter((t) => t.caseId === selectedCaseId), [todos, selectedCaseId]);
  const openTodos = caseTodos.filter((t) => !t.done);
  const doneTodos = caseTodos.filter((t) => t.done);
  const addTodo = useCallback(() => {
    const title = todoTitle.trim();
    if (!title) { setTodoError("待办内容不能为空"); return; }
    if (!selectedCaseId) { setTodoError("先选择案件"); return; }
    setTodoError(null);
    svc.matterTodoAdd?.({ caseId: selectedCaseId, title, dueDate: todoDue || null })
      .then(() => { setTodoTitle(""); setTodoDue(""); reload(); setScanNonce((n) => n + 1); })
      .catch((e: unknown) => setTodoError(String((e as Error)?.message ?? e)));
  }, [reload, selectedCaseId, svc, todoDue, todoTitle]);

  // 打钩=乐观置 done 不删行（对拍行 35）；失败回滚+行内报错（撤销=置 false 清 done_at）
  const setTodoDone = useCallback((td: BoardTodo, done: boolean) => {
    const snapshot = todos;
    setTodos((prev) => prev.map((x) => (x.id === td.id ? { ...x, done, doneAt: done ? new Date().toISOString() : null } : x)));
    svc.matterTodoSetDone?.({ id: td.id, done })
      .then(() => { setTodoOpError(null); setScanNonce((n) => n + 1); })
      .catch((e: unknown) => {
        setTodos(snapshot); // 回滚
        setTodoOpError(String((e as Error)?.message ?? e));
      });
  }, [svc, todos]);
  const deleteTodo = useCallback((td: BoardTodo) => {
    if (!window.confirm(`删除待办「${td.title}」？删除后不可恢复。`)) return;
    svc.matterTodoDelete?.({ id: td.id })
      .then(() => { reload(); setScanNonce((n) => n + 1); })
      .catch((e: unknown) => setTodoOpError(String((e as Error)?.message ?? e)));
  }, [reload, svc]);

  // ── 案件列表面（补齐件3：行45/49/52-56）──
  // 打开案件=选中进案内待办（单机看板无独立案件详情页；行54 菜单「打开案件」同此语义）。
  // 行62（补齐件4）：诉讼 tab 点开刑事案自动切到刑事 tab（CB「点开时自动切 tab」口径；
  // 导入刑事案件自动切随建账面——本面板无导入入口，不伪造）。
  const openCase = useCallback((c: BoardCase) => {
    setSelectedCaseId(c.id);
    setDomainTab((tab) => (tab === "civil" && isCriminalCase(c) ? "criminal" : tab));
    jumpTo("casetodo");
  }, [jumpTo]);
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }, []);
  // 删除=只删看板记录不动原文件夹（行55，文案声明）；菜单链删除延一帧弹确认（行54；WebView 模态竞态同款修复）
  const deleteCaseOne = useCallback((c: BoardCase) => {
    setCtxMenu(null);
    window.setTimeout(() => {
      if (!window.confirm(`将从看板删除案件「${c.name}」：只删看板记录，不动原始材料文件夹；案内待办随记录一并删除。`)) return;
      svc.matterDelete?.({ id: c.id })
        .then(() => { setSelectedIds((prev) => prev.filter((x) => x !== c.id)); reload(); })
        .catch((e: unknown) => setCaseOpError(String((e as Error)?.message ?? e)));
    }, 0);
  }, [reload, svc]);
  const deleteSelected = useCallback(() => {
    const picked = cases.filter((c) => selectedIds.includes(c.id));
    if (!picked.length) return;
    if (!window.confirm(`将删除所选 ${picked.length} 件案件：只删看板记录，不动原始材料文件夹；确定后逐件删除。`)) return;
    void (async () => {
      for (const c of picked) {
        try { await svc.matterDelete?.({ id: c.id }); setSelectedIds((prev) => prev.filter((x) => x !== c.id)); }
        catch (e) { setCaseOpError(String((e as Error)?.message ?? e)); break; }
      }
      reload();
    })();
  }, [cases, reload, selectedIds, svc]);
  // 右键菜单四路关闭（行54）：点外/再右键他处/滚动/Esc；菜单位置防视口溢出（渲染时 clamp）
  useEffect(() => {
    if (!ctxMenu) return;
    const close = () => setCtxMenu(null);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    const onCtx = (e: MouseEvent) => {
      if (!(e.target as HTMLElement | null)?.closest?.("[data-board-case-card]")) close();
    };
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", onKey);
    window.addEventListener("contextmenu", onCtx);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("contextmenu", onCtx);
    };
  }, [ctxMenu]);
  // 行30：日程右键菜单四路关闭（点外/再右键他处/滚动/Esc）——与案件卡菜单同型
  useEffect(() => {
    if (!eventMenu) return;
    const close = () => setEventMenu(null);
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    const onCtx = (e: MouseEvent) => {
      if (!(e.target as HTMLElement | null)?.closest?.("[data-board-event-item]")) close();
    };
    window.addEventListener("click", close);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    window.addEventListener("keydown", onKey);
    window.addEventListener("contextmenu", onCtx);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("contextmenu", onCtx);
    };
  }, [eventMenu]);
  // 多选模式：案件列表变化剔除悬空选中 id（行56）
  useEffect(() => {
    setSelectedIds((prev) => prev.filter((id) => cases.some((c) => c.id === id)));
  }, [cases]);
  // 拖放落位（行45）：增量写 sort_order，全部落定后重读
  const dropReorder = useCallback((draggedId: string, targetId: string) => {
    const patches = boardApplyDragOrder(dragSeqRef.current, draggedId, targetId);
    if (!patches.length) return;
    Promise.all(patches.map((p) => svc.matterUpdate?.({ id: p.id, sortOrder: p.sortOrder }) ?? Promise.resolve(null)))
      .then(() => reload())
      .catch((e: unknown) => setCaseOpError(String((e as Error)?.message ?? e)));
  }, [reload, svc]);
  // 近期日程分组（行70）：30 天窗按日分组+tone 三档+开庭标题补全+前 3 组
  const recent = useMemo(
    () => boardRecentGroups(
      upcoming.map((ev) => ({ date: ev.date, kind: ev.kind, title: ev.title, ref: ev.id, startAt: ev.startAt, caseName: caseName(ev.caseId) })),
      today,
    ),
    [caseName, today, upcoming],
  );

  if (!bridgeReady) {
    return (
      <section data-testid="board-panel" className="rounded-workspace-panel border border-border bg-header p-4">
        <h2 className="mb-2 text-ui-lg font-medium">案件看板</h2>
        <p className="text-ui-sm text-foreground-subtle">桥面未提供日程通道（matterEventList 不可用），看板面停用。</p>
      </section>
    );
  }

  const widthGridCls = cardWidth === "half" ? "grid grid-cols-1 lg:grid-cols-2" : "grid grid-cols-1";

  return (
    <section
      data-testid="board-panel"
      className="rounded-workspace-panel border border-border bg-header p-4"
      style={{ animation: "jusciteBoardEnter 260ms ease-out" }}
    >
      {/* ── 段 1：问候+简报 ｜ 重要提醒（顶部双卡；h-80 内滚动 overscroll-contain；卡宽切换持久）── */}
      <div className="mb-3 flex items-center gap-2">
        <CalendarDays className="size-5" />
        <h2 className="text-ui-lg font-medium">案件看板</h2>
        <button
          type="button"
          data-testid="board-card-width"
          aria-label={cardWidth === "half" ? "切为整行宽" : "切为半行宽"}
          className="ml-auto rounded border border-border px-2 py-0.5 text-ui-caption"
          onClick={() => {
            const next = cardWidth === "half" ? "full" : "half";
            setCardWidth(next);
            lsSet("juscite.board.cardWidth", next);
          }}
        >
          {cardWidth === "half" ? "半行宽" : "整行宽"}
        </button>
      </div>
      {/* 开关注册表面（行2：三开关+默认值+per-device 持久化；渲染于看板头内联——单机无独立设置页，位差注记） */}
      <div className="mb-2 flex flex-wrap items-center gap-3" data-testid="board-switches">
        <label className="flex items-center gap-1 text-ui-caption">
          <input type="checkbox" data-testid="board-switch-filterToolbar" checked={filterOn}
            onChange={(e) => {
              setFilterOn(e.target.checked);
              lsSet("juscite.board.switch.filterToolbar", e.target.checked ? "1" : "0");
              // 行55：工具栏关闭自动退出多选（多选系工具栏模式；视图/排序降级由 effective 口径统一裁定）
              if (!e.target.checked) { setMultiSelect(false); setSelectedIds([]); }
            }} />
          筛选工具栏
        </label>
        <label className="flex items-center gap-1 text-ui-caption">
          <input type="checkbox" data-testid="board-switch-boardAssistant" checked={assistantOn}
            onChange={(e) => { setAssistantOn(e.target.checked); lsSet("juscite.board.switch.boardAssistant", e.target.checked ? "1" : "0"); }} />
          看板简报
        </label>
        <label className="flex items-center gap-1 text-ui-caption text-foreground-subtle" title="同步源未接入（RE-3 §5 本版不做），开关位保留不伪造">
          <input type="checkbox" data-testid="board-switch-ticktick" disabled checked={false} readOnly />
          滴答类待办同步（未接入）
        </label>
      </div>
      {/* 行92：LL「SMTP 未配置」维护横幅的单机等量——桌面端恒无外发通道（默认不出域），常显如实注记 */}
      <p className="mb-2 text-ui-caption text-foreground-subtle" data-testid="board-egress-note">
        提醒仅经本机系统通知触达；无外发通道，本产品默认不出域。
      </p>
      <div className="mb-4 h-80 overflow-y-auto overscroll-contain">
        <div className={widthGridCls}>
          <div className="rounded border border-border p-3" data-testid="board-greeting-card">
            <div className="text-ui-lg font-medium">
              {greetingOf(new Date().getHours())}，{(lsGet("juscite.board.displayName") ?? "").trim() || "律师"}，在办 {cases.filter((c) => c.workflowStatus !== "已结案").length} 件
            </div>
            {assistantOn && briefing ? (
              <button
                type="button"
                data-testid="board-briefing"
                onClick={() => jumpTo(briefing.anchor)}
                className={`mt-2 w-full rounded px-2 py-1.5 text-left text-ui-sm ${
                  briefing.level === "red" ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                    : briefing.level === "amber" ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                      : "bg-header text-foreground-subtle"
                }`}
              >
                {briefing.text} →
              </button>
            ) : null}
            <p className="mt-2 text-ui-caption text-foreground-subtle">今天 {today} · 提醒逐条提前量弹系统通知，改动后即时补扫</p>
          </div>
          <div className="rounded border border-border p-3" data-testid="board-important-card" id="board-anchor-important">
            <div className="mb-1 flex items-center gap-1.5">
              <h3 className="text-ui-base font-medium">重要提醒</h3>
              <span className="text-ui-caption text-foreground-subtle">窗口内 {importantItems.length} 条</span>
            </div>
            <div
              ref={importantScrollRef}
              data-testid="board-important-list"
              onMouseEnter={() => { importantHoverRef.current = true; }}
              onMouseLeave={() => { importantHoverRef.current = false; }}
              className="max-h-56 overflow-y-auto"
            >
              {prominent.map((i) => {
                const Icon = i.isPreservation ? ShieldAlert : (KIND_ICON[i.kind] ?? CalendarClock);
                return (
                  <button key={i.id} type="button" data-testid={`board-important-${i.id}`}
                    onClick={() => { setSelectedDate(i.date); jumpTo("calendar"); }}
                    className={`flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-ui-sm hover:bg-selected/30 ${TONE_CLS[i.tone]}`}>
                    <Icon className="size-3.5 shrink-0" />
                    <span className="truncate font-medium">{i.title}</span>
                    <span className="ml-auto shrink-0 text-ui-caption">{i.countdown}</span>
                  </button>
                );
              })}
              {others.length > 0 ? (
                <div className="mt-1 border-t border-border pt-1 text-ui-caption text-foreground-subtle">其他日程</div>
              ) : null}
              {others.map((i) => {
                const Icon = i.isPreservation ? ShieldAlert : (KIND_ICON[i.kind] ?? CalendarClock);
                return (
                  <button key={i.id} type="button" onClick={() => { setSelectedDate(i.date); jumpTo("calendar"); }}
                    className="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-ui-sm text-foreground-subtle hover:bg-selected/30">
                    <Icon className="size-3.5 shrink-0" />
                    <span className="truncate">{i.title}</span>
                    <span className="ml-auto shrink-0">{i.countdown}</span>
                  </button>
                );
              })}
              {!importantItems.length ? (
                <div className="flex flex-col items-center gap-0.5 py-3 text-center" data-testid="board-important-empty">
                  <CalendarClock className="size-5 text-foreground-subtle" />
                  <span className="text-ui-sm">暂无窗口内的重要事项</span>
                  <span className="text-ui-caption text-foreground-subtle">安排日程或建案后，开庭与期限会显示在这里</span>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      {/* 今日焦点卡（行71）：全案最近一条期限/日程；点击跳案件或日历；30 天窗无→空态 */}
      <div className="mb-3 rounded border border-border p-3" data-testid="board-focus-card">
        {focus ? (
          <button type="button" className="flex w-full items-center gap-2 text-left"
            onClick={() => { if (focus.caseId) { setSelectedCaseId(focus.caseId); jumpTo("casetodo"); } else { jumpTo("calendar"); } }}>
            <span aria-hidden className={`size-2 shrink-0 rounded-full ${focus.tone === "red" ? "bg-red-500 animate-pulse" : "bg-amber-400"}`} data-testid="board-focus-dot" />
            <span className={`text-ui-lg font-semibold ${focus.tone === "red" ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400"}`} data-testid="board-focus-countdown">{focus.countdown}</span>
            <span className="text-ui-sm font-medium" data-testid="board-focus-title">{focus.title}</span>
            <span className="text-ui-caption text-foreground-subtle">{focus.date}{focus.timeLabel ? ` ${focus.timeLabel}` : ""}</span>
            {focus.caseName ? (
              <span className="ml-auto text-ui-caption text-foreground-subtle" data-testid="board-focus-case">
                {focus.caseName}{focus.caseNo ? ` · ${focus.caseNo}` : ""} →
              </span>
            ) : null}
          </button>
        ) : (
          <p className="text-ui-sm text-emerald-700 dark:text-emerald-300" data-testid="board-focus-empty">✓ 未来 30 天没有到期期限与日程安排。</p>
        )}
      </div>

      <div className="mb-3 flex items-center gap-2">
        <button type="button" data-testid="board-btn-new" className="flex items-center gap-1 rounded bg-selected px-3 py-1 text-ui-sm" onClick={() => openAddAt(selectedDate)}>
          <Plus className="size-4" /> 新建日程
        </button>
        {loadError ? <span className="text-ui-sm text-red-500" data-testid="board-load-error">桥连接异常：{loadError}</span> : null}
      </div>

      {/* ── 段 2：生产力网格（单列/双列响应式）── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded border border-border p-3" data-testid="board-calendar-card" id="board-anchor-calendar">
          <div className="mb-1 flex items-center gap-2">
            <h3 className="text-ui-base font-medium">日程日历</h3>
            <div className="ml-auto flex items-center gap-1.5">
              <button type="button" data-testid="board-month-prev" aria-label="上一月" className="rounded border border-border px-2 py-0.5 text-ui-sm" onClick={() => shiftMonth(-1)}>←</button>
              <button type="button" data-testid="board-month-today" className="rounded border border-border px-2 py-0.5 text-ui-sm" onClick={() => { const n = new Date(); setCursor({ y: n.getFullYear(), m: n.getMonth() + 1 }); setSelectedDate(boardTodayStr()); }}>本月</button>
              <button type="button" data-testid="board-month-next" aria-label="下一月" className="rounded border border-border px-2 py-0.5 text-ui-sm" onClick={() => shiftMonth(1)}>→</button>
              <button
                type="button"
                data-testid="board-calendar-collapse"
                title={calendarCollapsed ? "展开日历" : "折叠为摘要"}
                aria-label={calendarCollapsed ? "展开日历" : "折叠为摘要"}
                className="rounded border border-border px-1.5 py-0.5"
                onClick={() => { setCalendarCollapsed(!calendarCollapsed); lsSet("juscite.board.calendarCollapsed", calendarCollapsed ? "0" : "1"); }}
              >
                {calendarCollapsed ? <ChevronDown className="size-4" /> : <ChevronUp className="size-4" />}
              </button>
            </div>
          </div>
          {/* 行68：常驻图例+着色纪律句（红色只用于逾期与法定期限） */}
          <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-ui-caption text-foreground-subtle" data-testid="board-legend">
            <span className="inline-flex items-center gap-1"><span className="size-1.5 rounded-full bg-blue-500" />庭审</span>
            <span className="inline-flex items-center gap-1"><span className="size-1.5 rounded-full bg-red-500" />截止</span>
            <span className="inline-flex items-center gap-1"><span className="size-1.5 rounded-full bg-emerald-500" />日程</span>
            <span className="inline-flex items-center gap-1"><span className="size-1.5 rounded-full bg-purple-500" />待办</span>
            <span>红色只用于逾期与法定期限。</span>
          </div>
          {calendarCollapsed ? (
            <div data-testid="board-collapsed-summary" className="flex flex-col gap-0.5">
              {collapsedSummary.map((r) => (
                <button key={r.date} type="button" className="rounded px-1 py-0.5 text-left text-ui-sm hover:bg-selected/30"
                  onClick={() => { setCalendarCollapsed(false); lsSet("juscite.board.calendarCollapsed", "0"); setSelectedDate(r.date); }}>
                  <span className={(r.daysLeft ?? 0) < 0 ? "text-red-600 dark:text-red-400" : ""}>
                    {r.date.slice(5)} {r.first?.title}{r.count > 1 ? ` 等 ${r.count} 条` : ""}
                  </span>
                  <span className="ml-1.5 text-ui-caption text-foreground-subtle">
                    {(r.daysLeft ?? 0) < 0 ? `逾期 ${-(r.daysLeft ?? 0)} 天` : (r.daysLeft === 0 ? "今天" : `${r.daysLeft} 天后`)}
                  </span>
                </button>
              ))}
              {!collapsedSummary.length ? (
                <p className="text-ui-sm text-foreground-subtle">近 30 天没有逾期项，也没有未来日程；展开日历新建一条。</p>
              ) : null}
            </div>
          ) : (
            <>
              <div className="mb-1 grid grid-cols-7 text-center text-ui-caption text-foreground-subtle">
                {WEEK_HEADS.map((w) => <span key={w}>{w}</span>)}
              </div>
              <div className="grid grid-cols-7 gap-0.5" data-testid="board-cal-grid">
                {cells.map((cell, idx) => {
                  const cellItems = cell.date ? (byDate.get(cell.date) ?? []) : [];
                  const isToday = cell.date === today;
                  const isSelected = cell.date === selectedDate;
                  const dots = cellItems.slice(0, 4).map((it) => boardCellDotColor(boardDayDiff(today, cell.date ?? today), it.kind));
                  return (
                    <button
                      key={cell.date ?? `pad-${idx}`}
                      type="button"
                      disabled={!cell.date}
                      data-testid={cell.date === today ? "board-cell-today" : undefined}
                      onClick={() => cell.date && setSelectedDate(cell.date)}
                      onContextMenu={(e) => { if (cell.date) { e.preventDefault(); setSelectedDate(cell.date); openAddAt(cell.date); } }}
                      title={cell.date && cellItems.length > 0 ? `${cell.date} · ${cellItems.length} 条` : cell.date ?? undefined}
                      className={[
                        "relative min-h-11 rounded border p-1 text-left text-ui-sm",
                        cell.inMonth ? "" : "opacity-40",
                        isSelected ? "border-selected ring-1 ring-selected" : "border-border",
                        isToday ? "bg-selected/40 font-medium" : "",
                      ].join(" ")}
                    >
                      <span>{cell.date ? cell.date.slice(8, 10) : ""}</span>
                      {cellItems.length > 0 ? (
                        <span className="absolute right-0.5 top-0.5 rounded-full bg-selected px-1 text-[10px]" data-testid="board-cell-count">{cellItems.length}</span>
                      ) : null}
                      {dots.length > 0 ? (
                        <span className="absolute bottom-0.5 left-0.5 flex gap-0.5" data-testid="board-cell-dots">
                          {dots.map((d, di) => <span key={di} className={`size-1.5 rounded-full ${DOT_CLS[d]}`} data-testid={`board-dot-${d}`} />)}
                        </span>
                      ) : null}
                    </button>
                  );
                })}
              </div>
              <p className="mt-1 text-ui-caption text-foreground-subtle">右键日期可直接在该日新建日程；点日期查看当日安排。</p>
            </>
          )}
        </div>

        <div>
          <div className="rounded border border-border p-3" data-testid="board-day-card">
            <h3 className="mb-1 text-ui-base font-medium" data-testid="board-day-title">{selectedDate} 安排</h3>
            <div data-testid="board-day-list" className="flex flex-col gap-1.5">
              {dayItems.map((it) => it.todo ? (
                <div key={it.ref} data-testid="board-day-item" className="rounded border border-border p-2">
                  <div className="flex items-center gap-1.5">
                    <input type="checkbox" aria-label={`完成待办 ${it.todo.title}`} checked={false}
                      onChange={() => setTodoDone(it.todo as BoardTodo, true)} />
                    <span className="text-ui-sm font-medium">{it.todo.title}</span>
                    <span className="ml-auto text-ui-caption text-foreground-subtle">待办</span>
                  </div>
                </div>
              ) : (
                <div key={it.ref} data-testid="board-day-item" data-board-event-item className="rounded border border-border p-2"
                  onContextMenu={(e) => {
                    // 行30：右键日程→编辑/删除菜单（CB CalendarEventActions 口径；原按钮入口保留）
                    if (!it.event) return;
                    e.preventDefault();
                    setEventMenu({ eventId: it.event.id, x: e.clientX, y: e.clientY });
                  }}>
                  <div className="flex items-center gap-1.5">
                    <span className={`rounded px-1 text-ui-caption ${KIND_BADGE[it.event?.kind ?? ""]?.cls ?? ""}`}>{KIND_BADGE[it.event?.kind ?? ""]?.label ?? it.kind}</span>
                    <span className="text-ui-sm font-medium">{it.event?.title}</span>
                    <span className="text-ui-caption text-foreground-subtle">{it.event?.startAt ? `${it.event.startAt}–${it.event.endAt ?? "?"}` : "全天"}</span>
                    {it.event?.remind ? <Bell className="ml-auto size-3.5 text-foreground-subtle" aria-label="已开提醒" /> : <BellOff className="ml-auto size-3.5 text-foreground-subtle/50" aria-label="未开提醒" />}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-ui-caption text-foreground-subtle">
                    {it.event?.location ? <span>📍 {it.event.location}</span> : null}
                    {caseName(it.event?.caseId ?? null) ? <span>案件：{caseName(it.event?.caseId ?? null)}</span> : null}
                    {it.event?.trip ? <span className="inline-flex items-center gap-0.5"><Car className="size-3.5" /> {it.event.trip}</span> : null}
                  </div>
                  <div className="mt-1 flex gap-1.5">
                    <button type="button" className="inline-flex items-center gap-0.5 rounded border border-border px-1.5 py-0.5 text-ui-caption" onClick={() => openEdit(it.event as BoardEvent)}>
                      <Pencil className="size-3" /> 编辑
                    </button>
                    <button type="button" data-testid={`board-event-del-${it.event?.id}`} className="inline-flex items-center gap-0.5 rounded border border-border px-1.5 py-0.5 text-ui-caption" onClick={() => removeEvent(it.event as BoardEvent)}>
                      <Trash2 className="size-3" /> 删除
                    </button>
                  </div>
                </div>
              ))}
              {!dayItems.length ? (
                <p className="text-ui-sm text-foreground-subtle" data-testid="board-day-empty">当天暂无安排；可右键此日期新建，或从上方「新建日程」进入。</p>
              ) : null}
            </div>

            <h3 className="mb-1 mt-3 text-ui-base font-medium">近期日程（30 天内 {upcoming.length} 条）</h3>
            {/* 行70：按日分组+tone 三档（≤3 红/≤7 琥珀/普通）+开庭标题补全+只列前 3 天（更多进日历） */}
            <div data-testid="board-upcoming-list" className="flex flex-col gap-1">
              {recent.groups.map((g) => (
                <div key={g.date} data-testid={`board-recent-group-${g.date}`} className="rounded px-1 py-0.5">
                  <button type="button" className={`flex w-full items-center gap-1.5 text-left text-ui-sm hover:bg-selected/30 ${g.tone === "urgent" ? "text-red-600 dark:text-red-400" : g.tone === "soon" ? "text-amber-600 dark:text-amber-400" : ""}`}
                    onClick={() => setSelectedDate(g.date)}>
                    <span className="font-medium">{g.date.slice(5)}</span>
                    <span data-testid={`board-recent-countdown-${g.date}`}>{g.countdown}</span>
                    {g.items.slice(0, 2).map((it) => (
                      <span key={it.ref} className="truncate text-foreground-subtle">
                        <span className={`mr-1 rounded px-1 text-ui-caption ${KIND_BADGE[it.kind]?.cls ?? ""}`}>{KIND_BADGE[it.kind]?.label ?? it.kind}</span>
                        {it.title}
                      </span>
                    ))}
                    {g.items.length > 2 ? <span className="text-ui-caption text-foreground-subtle">等 {g.items.length} 条</span> : null}
                  </button>
                </div>
              ))}
              {recent.extraDays > 0 ? (
                <p className="text-ui-caption text-foreground-subtle">另有 {recent.extraDays} 天的安排，见上方日历。</p>
              ) : null}
              {!upcoming.length && calEvents.length === 0 ? (
                <p className="text-ui-sm text-foreground-subtle" data-testid="board-empty-never">还没有日程。点右上角「新建日程」安排第一件。</p>
              ) : null}
              {!upcoming.length && allEnded ? (
                <p className="text-ui-sm text-foreground-subtle" data-testid="board-empty-ended">已安排的日程都已结束；可在日历中点选日期回看。</p>
              ) : null}
            </div>
          </div>

          {/* 【#5 冲突查重】案件冲突复核卡：仅待复核时渲染（A5/H1；P2 先落复核卡与结论，H5 闸位随写路径模块接入） */}
          {selectedCaseId ? (
            <ConflictReviewCard
              caseId={selectedCaseId}
              caseName={cases.find((c) => c.id === selectedCaseId)?.name ?? ""}
            />
          ) : null}

          {/* 案内待办卡（行 35）：输入+可选日期+打钩不删行+已完成区撤销/删除+日期徽章三色+两空态 */}
          <div className="mt-4 rounded border border-border p-3" data-testid="board-todo-card" id="board-anchor-casetodo">
            <div className="mb-1.5 flex items-center gap-2">
              <h3 className="text-ui-base font-medium">案内待办</h3>
              <select data-testid="board-case-select" className="ml-auto max-w-[50%] rounded border border-border px-1.5 py-0.5 text-ui-caption"
                value={selectedCaseId} onChange={(e) => setSelectedCaseId(e.target.value)}>
                {!cases.length ? <option value="">（尚无案件）</option> : null}
                {cases.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
            <div className="flex items-center gap-1.5">
              <input data-testid="board-todo-input" className="min-w-0 flex-1 rounded border border-border px-2 py-1 text-ui-sm"
                placeholder="加一条待办，回车提交" value={todoTitle}
                onChange={(e) => setTodoTitle(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTodo(); } }} />
              <input data-testid="board-todo-date" type="date" aria-label="截止日期（可选）"
                className="rounded border border-border px-1.5 py-1 text-ui-caption" value={todoDue}
                onChange={(e) => setTodoDue(e.target.value)} />
              <button type="button" data-testid="board-todo-add" className="rounded bg-selected px-2 py-1 text-ui-caption" onClick={addTodo}>添加</button>
            </div>
            {todoError ? <p className="mt-1 text-ui-caption text-red-500" data-testid="board-todo-error">{todoError}</p> : null}
            {todoOpError ? <p className="mt-1 text-ui-caption text-red-500" data-testid="board-todo-op-error">{todoOpError}</p> : null}
            <div className="mt-1.5 flex flex-col gap-0.5" data-testid="board-todo-list">
              {openTodos.map((t) => {
                const badge = t.dueDate ? todoBadge(t.dueDate, today) : null;
                return (
                  <div key={t.id} data-testid="board-todo-item" className="flex items-center gap-1.5 rounded px-1 py-0.5">
                    <input type="checkbox" data-testid={`board-todo-done-toggle-${t.id}`} aria-label={`完成 ${t.title}`}
                      checked={false} onChange={() => setTodoDone(t, true)} />
                    <span className="truncate text-ui-sm">{t.title}</span>
                    {badge ? <span className={`ml-auto shrink-0 text-ui-caption ${badge.cls}`}>{badge.text}</span> : null}
                  </div>
                );
              })}
              {!openTodos.length && !doneTodos.length ? (
                <p className="text-ui-sm text-foreground-subtle" data-testid="board-todo-empty-none">该案还没有待办；上方输入回车加一条。</p>
              ) : null}
              {!openTodos.length && doneTodos.length ? (
                <p className="text-ui-sm text-foreground-subtle" data-testid="board-todo-empty-alldone">都做完了 🎉</p>
              ) : null}
            </div>
            {doneTodos.length > 0 ? (
              <div className="mt-1.5" data-testid="board-todo-done-zone">
                <button type="button" className="flex items-center gap-1 text-ui-caption text-foreground-subtle"
                  onClick={() => setDoneOpen(!doneOpen)}>
                  {doneOpen ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                  已完成 {doneTodos.length}
                </button>
                {doneOpen ? (
                  <div className="mt-1 flex flex-col gap-0.5">
                    {doneTodos.map((t) => (
                      <div key={t.id} className="flex items-center gap-1.5 rounded px-1 py-0.5">
                        <span className="truncate text-ui-sm text-foreground-subtle line-through">{t.title}</span>
                        <button type="button" data-testid={`board-todo-undo-${t.id}`} className="ml-auto rounded border border-border px-1.5 py-0.5 text-ui-caption"
                          onClick={() => setTodoDone(t, false)}>撤销</button>
                        <button type="button" data-testid={`board-todo-del-${t.id}`} className="rounded border border-border px-1.5 py-0.5 text-ui-caption"
                          onClick={() => deleteTodo(t)}><Trash2 className="size-3" /></button>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {/* 待办汇总卡（行38：跨案未完成按案分组+组内创建倒序+打钩乐观回滚；无未完成待办整卡不渲染） */}
      {aggGroups.length > 0 ? (
        <div className="mt-4 rounded border border-border p-3" data-testid="board-todo-agg-card">
          <div className="mb-1 flex items-center gap-2">
            <h3 className="text-ui-base font-medium">待办汇总</h3>
            <span className="text-ui-caption text-foreground-subtle" data-testid="board-todo-agg-count">{aggCount} 条未完成</span>
          </div>
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            {aggGroups.map(([cid, rows]) => (
              <div key={cid} data-testid="board-todo-agg-group" className="rounded border border-border p-2">
                <button type="button" className="text-ui-caption text-foreground-subtle hover:underline" title="查看本案案内待办"
                  onClick={() => { setSelectedCaseId(cid); jumpTo("casetodo"); }}>
                  {caseName(cid) ?? "（未知案件）"} · {rows.length}
                </button>
                <div className="mt-0.5 flex flex-col gap-0.5">
                  {rows.map((t) => {
                    const badge = t.dueDate ? todoBadge(t.dueDate, today) : null;
                    return (
                      <div key={t.id} data-testid={`board-agg-todo-${t.id}`} className="flex items-center gap-1.5 rounded px-1 py-0.5">
                        <input type="checkbox" aria-label={`完成 ${t.title}`} checked={false}
                          onChange={() => setTodoDone(t, true)} />
                        <span className="truncate text-ui-sm">{t.title}</span>
                        {badge ? <span className={`ml-auto shrink-0 text-ui-caption ${badge.cls}`}>{badge.text}</span> : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* 出行与提醒卡（对拍行 83：出行项做可选字段不做独立规划面；提醒行=铃铛+开关+下一提醒时间） */}
      <div className="mt-4 rounded border border-border p-3" data-testid="board-trip-card">
        <div className="mb-1 flex items-center gap-2">
          <h3 className="text-ui-base font-medium">出行与提醒</h3>
          <span className="text-ui-caption text-foreground-subtle">到点前按每条提前量弹系统通知；60 秒一轮扫描，改动后即时补扫</span>
        </div>
        {engineNote ? <p className="mb-1 text-ui-caption" data-testid="board-engine-note">{engineNote}</p> : null}
        {tripRows.length === 0 && remindRows.length === 0 ? (
          <p className="text-ui-sm text-foreground-subtle" data-testid="board-trip-empty">近 30 天没有带出行安排或已开提醒的日程；在日程上填「出行安排」或打开「到点提醒」后会出现在这里。</p>
        ) : null}
        <div className="flex flex-col gap-1">
          {tripRows.map((ev) => (
            <div key={`trip-${ev.id}`} data-testid="board-trip-row" className="flex items-start gap-2 rounded border border-border px-2 py-1">
              <Car className="mt-0.5 size-4 shrink-0" aria-label="出行" />
              <div className="text-ui-sm">
                <span className="font-medium">{ev.date.slice(5)} {ev.title}</span>
                <span className="ml-2 text-foreground-subtle">{ev.trip}</span>
                {ev.startAt ? <span className="ml-2 text-ui-caption text-foreground-subtle">{ev.startAt} 开始</span> : null}
              </div>
            </div>
          ))}
          {remindRows.map(({ ev, fireMs }) => (
            <div key={`rem-${ev.id}`} data-testid="board-remind-row" className="flex items-center gap-2 rounded border border-border px-2 py-1">
              <BellRing className="size-4 shrink-0" aria-label="提醒中" />
              <span className="text-ui-sm font-medium">{ev.date.slice(5)} {ev.title}</span>
              <span className="text-ui-caption text-foreground-subtle" data-testid="board-next-fire">
                下一提醒 {fmtNextFire(fireMs)}（提前 {ev.remindMinutes} 分钟）
              </span>
              <button type="button" className="ml-auto rounded border border-border px-1.5 py-0.5 text-ui-caption" data-testid={`board-remind-toggle-${ev.id}`}
                onClick={() => toggleRemind(ev)}>
                关闭提醒
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 期限预警阶梯（对拍行 91；LL 阶梯卡等量：四桶+条形微图+档位脚注） */}
      <div className="mt-4 rounded border border-border p-3" data-testid="board-ladder">
        <div className="mb-1 flex items-center gap-2">
          <h3 className="text-ui-base font-medium">期限预警阶梯</h3>
          <span className="text-ui-caption text-foreground-subtle">未来 30 天 · 共 {deadlineItems.length} 项未完期限</span>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {ladder.map((b, i) => {
            const meta = LADDER_META[i];
            if (!meta) return null;
            const width = Math.min(100, Math.max(4, b.count * 20));
            return (
              <div key={b.key} className="rounded border border-border p-2" data-testid={meta.testid}>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-ui-lg font-semibold">{b.count}</span>
                  <span className="text-ui-caption text-foreground-subtle">{meta.label}</span>
                </div>
                <div className="mt-1 h-1.5 rounded bg-border/40">
                  <div className={`h-1.5 rounded ${meta.cls}`} style={{ width: b.count > 0 ? `${width}%` : "0%" }} />
                </div>
              </div>
            );
          })}
        </div>
        <p className="mt-1.5 text-ui-caption text-foreground-subtle" data-testid="board-ladder-footnote">
          提醒档位 {BOARD_DEADLINE_TIERS.join(" / ")}（与期限引擎偏移并集同源）；节假日顺延由期限引擎裁定，接入前按自然日计
        </p>
      </div>

      {/* 案件段（行84 下一节点；行40-44 状态机面；行47/48 筛选；行62/63/65 域 tabs+计数；行52/66 视图切换；行55/56 多选删除） */}
      <div className="mt-4" data-testid="board-cases" id="board-anchor-cases">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <h3 className="text-ui-base font-medium">在办案件</h3>
          <span className="text-ui-caption text-foreground-subtle">{visibleCases.length}/{cases.length} 件</span>
          {caseToast ? (
            <span className="rounded bg-teal-100 px-2 py-0.5 text-ui-caption text-teal-700 dark:bg-teal-950 dark:text-teal-300" data-testid="board-case-toast">
              {caseToast}
            </span>
          ) : null}
          <div className="ml-auto flex flex-wrap items-center gap-1.5">
            {BOARD_DOMAIN_TABS.map((t) => (
              <button key={t.key} type="button" data-testid={`board-tab-${t.key}`} aria-pressed={domainTab === t.key}
                title={t.key === "criminal" ? "按刑事启发式归类（案号/案由/词表，宁漏勿误）" : t.key === "execution" ? "按工作流状态「执行中」过滤" : undefined}
                className={`rounded px-1.5 py-0.5 text-ui-caption ${domainTab === t.key ? "bg-selected font-medium" : "border border-border text-foreground-subtle"}`}
                onClick={() => setDomainTab(t.key)}>
                {t.label} <span data-testid={`board-tab-count-${t.key}`}>({domainCounts[t.key]})</span>
              </button>
            ))}
            <span aria-hidden className="h-4 w-px bg-border" />
            {/* 行48/55（补齐件4）：视图切换与多选系工具栏档位——工具栏关=强制 grid+退多选，按钮随之隐藏 */}
            {filterOn ? (
              <>
                <button type="button" data-testid="board-view-grid" aria-pressed={viewMode === "grid"}
                  className={`rounded px-1.5 py-0.5 text-ui-caption ${viewMode === "grid" ? "bg-selected font-medium" : "border border-border text-foreground-subtle"}`}
                  onClick={() => { setViewMode("grid"); lsSet("juscite.board.viewMode", "grid"); }}>卡片</button>
                <button type="button" data-testid="board-view-list" aria-pressed={viewMode === "list"}
                  className={`rounded px-1.5 py-0.5 text-ui-caption ${viewMode === "list" ? "bg-selected font-medium" : "border border-border text-foreground-subtle"}`}
                  onClick={() => { setViewMode("list"); lsSet("juscite.board.viewMode", "list"); }}>列表</button>
                <span aria-hidden className="h-4 w-px bg-border" />
                {multiSelect ? (
                  <>
                    <button type="button" data-testid="board-multi-all" className="rounded border border-border px-1.5 py-0.5 text-ui-caption"
                      onClick={() => setSelectedIds(visibleCases.map((c) => c.id))}>全选可见</button>
                    <button type="button" data-testid="board-multi-delete" disabled={!selectedIds.length}
                      className="rounded border border-border px-1.5 py-0.5 text-ui-caption disabled:opacity-50"
                      onClick={deleteSelected}>删除所选{selectedIds.length ? `（${selectedIds.length}）` : ""}</button>
                    <button type="button" data-testid="board-multi-exit" className="rounded border border-border px-1.5 py-0.5 text-ui-caption"
                      onClick={() => { setMultiSelect(false); setSelectedIds([]); }}>退出多选</button>
                  </>
                ) : (
                  <button type="button" data-testid="board-multi-enter" className="rounded border border-border px-1.5 py-0.5 text-ui-caption"
                    onClick={() => setMultiSelect(true)}>多选</button>
                )}
              </>
            ) : null}
          </div>
        </div>
        {filterOn ? (
          <div className="mb-2 flex flex-wrap items-center gap-1.5" data-testid="board-filter-toolbar">
            {BOARD_STATUS_DEFS.map((d) => {
              const on = filterStatuses.includes(d.name);
              return (
                <button key={d.name} type="button" data-testid={`board-filter-status-${d.name}`} aria-pressed={on}
                  className={`rounded px-1.5 py-0.5 text-ui-caption ${on ? `${d.chip} font-medium` : "border border-border text-foreground-subtle"}`}
                  onClick={() => setFilterStatuses((prev) => (on ? prev.filter((x) => x !== d.name) : [...prev, d.name]))}>
                  {d.name}
                </button>
              );
            })}
            <select data-testid="board-filter-court" aria-label="按法院筛选" className="rounded border border-border px-1.5 py-0.5 text-ui-caption"
              value={filterCourt} onChange={(e) => setFilterCourt(e.target.value)}>
              <option value="">全部法院</option>
              {courts.map((ct) => <option key={ct} value={ct}>{ct}</option>)}
            </select>
            <input data-testid="board-filter-party" className="w-40 rounded border border-border px-2 py-0.5 text-ui-caption"
              placeholder="搜当事人（原告/被告）" value={filterParty} onChange={(e) => setFilterParty(e.target.value)} />
            <span aria-hidden className="h-4 w-px bg-border" />
            {/* 行46：四排序键+asc/desc 切换（默认=桶/拖拽序） */}
            <label className="flex items-center gap-1 text-ui-caption text-foreground-subtle">
              排序
              <select data-testid="board-sort-key" className="rounded border border-border px-1.5 py-0.5 text-ui-caption"
                value={sortKey} onChange={(e) => setSortKey(e.target.value as BoardSortKey | "default")}>
                {BOARD_SORT_KEYS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
              </select>
            </label>
            {sortKey !== "default" ? (
              <button type="button" data-testid="board-sort-dir" aria-label={sortDir === "asc" ? "切为降序" : "切为升序"}
                className="rounded border border-border px-1.5 py-0.5 text-ui-caption"
                onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}>
                {sortDir === "asc" ? "↑ 升序" : "↓ 降序"}
              </button>
            ) : null}
            {hasFilter ? (
              <button type="button" data-testid="board-filter-clear" className="rounded border border-border px-1.5 py-0.5 text-ui-caption"
                onClick={() => { setFilterStatuses([]); setFilterCourt(""); setFilterParty(""); }}>清空筛选</button>
            ) : null}
          </div>
        ) : null}
        {caseOpError ? <p className="mb-1 text-ui-caption text-red-500" data-testid="board-case-op-error">{caseOpError}</p> : null}
        {effViewMode === "list" ? (
          /* 行52/66：列表视图 5 列行（案件+当事人/案号+法院/法官+金额/状态/打开），无值占位 -，行首状态脊色 */
          <div className="flex flex-col gap-1" data-testid="board-case-list">
            {caseCards.map(({ case: c }) => {
              const display = displayStatusOf(c);
              const spine = (BOARD_STATUS_DEFS.find((d) => d.name === display)?.chip ?? "")
                .split(" ").filter((t) => t.startsWith("bg-")).join(" ") || "bg-gray-400";
              const isSel = selectedIds.includes(c.id);
              const risk = riskByCase.get(c.id);
              return (
                <div key={c.id} data-testid="board-case-row" tabIndex={0}
                  aria-label={multiSelect ? `选择案件 ${c.name}` : `打开案件 ${c.name}`}
                  className={`relative flex flex-wrap items-center gap-x-3 gap-y-0.5 rounded border border-border px-2 py-1 text-ui-sm ${display === "已结案" ? "opacity-60" : ""} ${multiSelect && isSel ? "border-selected ring-2 ring-selected" : ""}`}
                  onClick={() => (multiSelect ? toggleSelect(c.id) : openCase(c))}
                  onKeyDown={(e) => { if (!multiSelect && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openCase(c); } }}>
                  <span aria-hidden className={`h-4 w-1 shrink-0 rounded ${spine}`} data-testid="board-row-spine" />
                  <span className="min-w-0 flex-1 truncate font-medium">{c.name}
                    <span className="ml-1.5 text-ui-caption font-normal text-foreground-subtle">{partySummary(c) || "-"}</span>
                  </span>
                  <span className="font-mono text-ui-caption">{c.caseNo || "-"} · {c.court || "-"}</span>
                  <span className="text-ui-caption">{(c.judges ?? []).join("、") || "-"} · <span className="font-mono font-semibold">{boardYuan(c.claimAmountCents)}</span></span>
                  {/* 行66：最近期限风险徽章（LL 等量；红只用于逾期——无逾期不显） */}
                  {risk ? (
                    <span className="text-ui-caption text-red-600 dark:text-red-400" data-testid={`board-row-risk-${c.id}`}
                      title={`期限日 ${risk.date}`}>
                      逾期 {-risk.daysLeft} 天 · {risk.title}
                    </span>
                  ) : null}
                  <button type="button" data-testid={`board-case-status-${c.id}`} className={`rounded px-1 text-ui-caption ${boardStatusChip(display)}`}
                    onClick={(e) => { e.stopPropagation(); setStatusMenuFor((prev) => (prev === c.id ? null : c.id)); }}>
                    {display}
                  </button>
                  {statusMenuFor === c.id ? (
                    <div className="absolute right-1 z-20 w-32 -translate-y-6 flex-col gap-0.5 rounded border border-border bg-background p-1 shadow-lg flex" data-testid="board-status-menu">
                      {BOARD_STATUS_DEFS.map((d) => (
                        <button key={d.name} type="button" className={`rounded px-1.5 py-0.5 text-left text-ui-caption hover:bg-selected/30 ${display === d.name ? `${d.chip} font-medium` : ""}`}
                          onClick={(e) => { e.stopPropagation(); setCaseStatus(c, d.name); }}>
                          {display === d.name ? "✓ " : ""}{d.name}
                        </button>
                      ))}
                      {c.workflowLocked ? (
                        <button type="button" className="rounded px-1.5 py-0.5 text-left text-ui-caption text-foreground-subtle hover:bg-selected/30"
                          onClick={(e) => { e.stopPropagation(); setCaseStatus(c, null); }}>恢复自动推断</button>
                      ) : null}
                    </div>
                  ) : null}
                  <button type="button" data-testid={`board-row-open-${c.id}`} className="rounded border border-border px-1.5 py-0.5 text-ui-caption"
                    onClick={(e) => { e.stopPropagation(); openCase(c); }}>打开 →</button>
                </div>
              );
            })}
            {!cases.length ? (
              <p className="text-ui-sm text-foreground-subtle" data-testid="board-cases-empty">还没有案件记录；案件建账后这里显示在办列表与下一排期节点。</p>
            ) : null}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {caseCards.map(({ case: c, next }) => {
              const display = displayStatusOf(c);
              const closed = display === "已结案";
              const isSel = selectedIds.includes(c.id);
              const courtLabel = c.courtType === "仲裁委" ? "仲裁委" : "法院";
              const judgeLabel = c.courtType === "仲裁委" ? "仲裁员" : "承办法官";
              return (
              <div key={c.id} data-board-case-card data-testid="board-case-card" tabIndex={0}
                aria-label={multiSelect ? `选择案件 ${c.name}` : `打开案件 ${c.name}`}
                className={`relative rounded border border-border p-2.5 ${closed ? "opacity-60" : ""} ${multiSelect && isSel ? "border-selected ring-2 ring-selected" : ""} ${dragOverId === c.id ? "border-dashed" : ""}`}
                style={dragOverId === c.id ? { opacity: 0.7 } : undefined}
                draggable={dragEnabled && dragArmedId === c.id}
                onClick={() => (multiSelect ? toggleSelect(c.id) : openCase(c))}
                onKeyDown={(e) => { if (!multiSelect && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openCase(c); } }}
                onContextMenu={(e) => {
                  if (multiSelect) return;
                  e.preventDefault();
                  setCtxMenu({ caseId: c.id, x: e.clientX, y: e.clientY });
                }}
                onDragOver={(e) => { if (dragEnabled && dragArmedId && dragArmedId !== c.id) { e.preventDefault(); setDragOverId(c.id); } }}
                onDragLeave={() => setDragOverId((p) => (p === c.id ? null : p))}
                onDrop={(e) => {
                  e.preventDefault();
                  const src = dragArmedId;
                  setDragArmedId(null);
                  setDragOverId(null);
                  if (src && src !== c.id) dropReorder(src, c.id);
                }}
                onDragEnd={() => { setDragArmedId(null); setDragOverId(null); }}
              >
                <div className="flex items-center gap-1.5">
                  {/* 行51：拖拽把手左上角，默认低透明 hover 显现（仅 grid+默认序时生效） */}
                  <span data-testid="board-case-drag" aria-hidden
                    onMouseDown={() => { if (dragEnabled) setDragArmedId(c.id); }}
                    onMouseUp={() => setDragArmedId((p) => (p === c.id ? null : p))}
                    className={`cursor-grab select-none text-ui-caption leading-none text-foreground-subtle ${dragEnabled ? "opacity-20 hover:opacity-100" : "invisible"}`}>⠿</span>
                  <span className="min-w-0 truncate text-ui-sm font-medium">{c.cause ? `${c.cause}｜` : ""}{c.name}</span>
                  <button type="button" data-testid="board-case-status" aria-label={`案件状态：${display}`}
                    title={c.workflowLocked ? "手工设置·点击修改" : "自动推断·点击手工选择"}
                    className={`ml-auto shrink-0 rounded px-1 text-ui-caption ${boardStatusChip(display)}`}
                    onClick={(e) => { e.stopPropagation(); setStatusMenuFor((prev) => (prev === c.id ? null : c.id)); }}>
                    {display}
                  </button>
                </div>
                {statusMenuFor === c.id ? (
                  <div className="absolute right-1 top-7 z-20 flex w-32 flex-col gap-0.5 rounded border border-border bg-background p-1 shadow-lg" data-testid="board-status-menu">
                    {BOARD_STATUS_DEFS.map((d) => (
                      <button key={d.name} type="button" data-testid={`board-status-opt-${d.name}`} aria-current={display === d.name}
                        className={`rounded px-1.5 py-0.5 text-left text-ui-caption hover:bg-selected/30 ${display === d.name ? `${d.chip} font-medium` : ""}`}
                        onClick={(e) => { e.stopPropagation(); setCaseStatus(c, d.name); }}>
                        {display === d.name ? "✓ " : ""}{d.name}
                      </button>
                    ))}
                    {c.workflowLocked ? (
                      <button type="button" data-testid="board-status-auto" className="rounded px-1.5 py-0.5 text-left text-ui-caption text-foreground-subtle hover:bg-selected/30"
                        onClick={(e) => { e.stopPropagation(); setCaseStatus(c, null); }}>恢复自动推断</button>
                    ) : null}
                  </div>
                ) : null}
                {partySummary(c) ? (
                  <div className="mt-0.5 text-ui-caption text-foreground-subtle" data-testid="board-case-party">{partySummary(c)}</div>
                ) : null}
                {/* 行49：四字段格（案号 mono/法院·仲裁委 label 切换/承办法官·仲裁员/诉讼金额 mono）。抽取态脚注随 #6 计数接入后补，不伪造 */}
                <div className="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5 text-ui-caption text-foreground-subtle" data-testid="board-case-fields">
                  <span className="font-mono">{c.caseNo || "-"}</span>
                  <span>{courtLabel}：{c.court || "-"}</span>
                  <span>{judgeLabel}：{(c.judges ?? []).join("、") || "-"}</span>
                  <span className="font-mono font-semibold text-foreground">诉额 {boardYuan(c.claimAmountCents)}</span>
                </div>
                <div className="mt-1 text-ui-sm" data-testid="board-case-node">
                  {next ? (
                    <span>下一节点 <span className="font-medium">{next.date.slice(5)} {next.title}</span>
                      <span className="text-foreground-subtle">（{next.daysAway === 0 ? "今天" : `${next.daysAway} 天后`}）</span>
                    </span>
                  ) : (
                    <span className="text-foreground-subtle">暂无排期节点</span>
                  )}
                </div>
              </div>
            );
            })}
            {!cases.length ? (
              <p className="text-ui-sm text-foreground-subtle" data-testid="board-cases-empty">还没有案件记录；案件建账后这里显示在办卡片与下一排期节点。</p>
            ) : null}
          </div>
        )}
        {/* 空态三层（行57）：全库空（上）/筛选·tab 无匹配/刑事 tab 独立文案 */}
        {cases.length > 0 && caseCards.length === 0 ? (
          domainTab === "criminal" ? (
            <div className="mt-2 rounded border border-dashed border-border p-3 text-ui-sm text-foreground-subtle" data-testid="board-cases-criminal-empty">
              没有识别为刑事的案件。域分类按案号/案由自动识别归类——这里为空不是没有导入案件。
            </div>
          ) : (
            <div className="mt-2 rounded border border-dashed border-border p-3 text-ui-sm text-foreground-subtle" data-testid="board-cases-nomatch">
              当前筛选或域页签没有匹配案件；可调整条件或点「清空筛选」。
            </div>
          )
        ) : null}
      </div>

      {/* 行54：案件卡右键菜单（两项+防视口溢出+点外/右键/滚动/Esc 四路关闭；删除走延帧确认） */}
      {ctxMenu ? (() => {
        const c = cases.find((x) => x.id === ctxMenu.caseId);
        if (!c) return null;
        const vw = typeof window !== "undefined" ? window.innerWidth : 1280;
        const vh = typeof window !== "undefined" ? window.innerHeight : 800;
        return (
          <div role="menu" data-testid="board-case-menu"
            className="fixed z-50 flex w-44 flex-col gap-0.5 rounded border border-border bg-background p-1 shadow-lg"
            style={{ left: Math.max(4, Math.min(ctxMenu.x, vw - 190)), top: Math.max(4, Math.min(ctxMenu.y, vh - 100)) }}
            onClick={(e) => e.stopPropagation()}>
            <button type="button" data-testid="board-case-menu-open" className="rounded px-2 py-1 text-left text-ui-sm hover:bg-selected/30"
              onClick={() => { setCtxMenu(null); openCase(c); }}>打开案件</button>
            <button type="button" data-testid="board-case-menu-delete" className="rounded px-2 py-1 text-left text-ui-sm text-red-600 dark:text-red-400 hover:bg-selected/30"
              onClick={() => deleteCaseOne(c)}>从看板删除…</button>
          </div>
        );
      })() : null}

      {/* 行30：日程右键菜单（编辑/删除两项；防视口溢出 clamp） */}
      {eventMenu ? (() => {
        const ev = events.find((x) => x.id === eventMenu.eventId);
        if (!ev) return null;
        const vw = typeof window !== "undefined" ? window.innerWidth : 1280;
        const vh = typeof window !== "undefined" ? window.innerHeight : 800;
        return (
          <div role="menu" data-testid="board-event-menu"
            className="fixed z-50 flex w-32 flex-col gap-0.5 rounded border border-border bg-background p-1 shadow-lg"
            style={{ left: Math.max(4, Math.min(eventMenu.x, vw - 140)), top: Math.max(4, Math.min(eventMenu.y, vh - 90)) }}
            onClick={(e) => e.stopPropagation()}>
            <button type="button" data-testid="board-event-menu-edit" className="rounded px-2 py-1 text-left text-ui-sm hover:bg-selected/30"
              onClick={() => { setEventMenu(null); openEdit(ev); }}>编辑日程</button>
            <button type="button" data-testid="board-event-menu-delete" className="rounded px-2 py-1 text-left text-ui-sm text-red-600 dark:text-red-400 hover:bg-selected/30"
              onClick={() => { setEventMenu(null); removeEvent(ev); }}>删除日程…</button>
          </div>
        );
      })() : null}

      {draft ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" role="dialog" aria-modal="true" data-testid="board-dialog"
          onKeyDown={(e) => { if (e.key === "Escape") setDraft(null); }}>
          <div className="w-[26rem] max-w-[92vw] rounded-lg border border-border bg-background p-4 shadow-xl">
            <h3 className="mb-2 text-ui-base font-medium">{draft.id ? "编辑日程" : "新建日程"}</h3>
            <div className="flex flex-col gap-2 text-ui-sm">
              <label className="flex flex-col gap-0.5">
                <span>事项名（必填）</span>
                <input data-testid="board-dlg-title" autoFocus className="rounded border border-border px-2 py-1" value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); saveDraft(); } }} />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-0.5">
                  <span>日期</span>
                  <input data-testid="board-dlg-date" type="date" className="rounded border border-border px-2 py-1" value={draft.date}
                    onChange={(e) => setDraft({ ...draft, date: e.target.value })} />
                </label>
                <div className="flex flex-col gap-0.5">
                  <span>分类</span>
                  <div className="flex gap-1" data-testid="board-dlg-kinds">
                    {Object.entries(KIND_BADGE).map(([k, b]) => (
                      <button key={k} type="button" data-testid={`board-dlg-kind-${k}`} aria-pressed={draft.kind === k}
                        className={`rounded px-1.5 py-1 text-ui-caption ${draft.kind === k ? `${b.cls} font-medium` : "border border-border text-foreground-subtle"}`}
                        onClick={() => setDraft({ ...draft, kind: k })}>{b.label}</button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-0.5">
                  <span>开始（可空=全天）</span>
                  <input data-testid="board-dlg-start" type="time" className="rounded border border-border px-2 py-1" value={draft.startAt}
                    onChange={(e) => setDraft({ ...draft, startAt: e.target.value })} />
                </label>
                <label className="flex flex-col gap-0.5">
                  <span>结束</span>
                  <input data-testid="board-dlg-end" type="time" className="rounded border border-border px-2 py-1" value={draft.endAt}
                    onChange={(e) => setDraft({ ...draft, endAt: e.target.value })} />
                </label>
              </div>
              <label className="flex flex-col gap-0.5">
                <span>地点</span>
                <input data-testid="board-dlg-location" className="rounded border border-border px-2 py-1" value={draft.location}
                  onChange={(e) => setDraft({ ...draft, location: e.target.value })} />
              </label>
              <label className="flex flex-col gap-0.5">
                <span>关联案件（可选）</span>
                <select data-testid="board-dlg-case" className="rounded border border-border px-2 py-1" value={draft.caseId}
                  onChange={(e) => setDraft({ ...draft, caseId: e.target.value })}>
                  <option value="">不关联</option>
                  {cases.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-0.5">
                <span>出行安排（可选）</span>
                <input data-testid="board-dlg-trip" className="rounded border border-border px-2 py-1" placeholder="如：8:00 地铁 2 号线出发" value={draft.trip}
                  onChange={(e) => setDraft({ ...draft, trip: e.target.value })} />
              </label>
              <label className="flex flex-col gap-0.5">
                <span>备注</span>
                <input data-testid="board-dlg-note" className="rounded border border-border px-2 py-1" value={draft.note}
                  onChange={(e) => setDraft({ ...draft, note: e.target.value })} />
              </label>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-1">
                  <input data-testid="board-dlg-remind" type="checkbox" checked={draft.remind}
                    onChange={(e) => setDraft({ ...draft, remind: e.target.checked })} /> 到点提醒
                </label>
                <label className="flex items-center gap-1">
                  提前
                  <input data-testid="board-dlg-remind-minutes" type="number" min={0} step={1} disabled={!draft.remind}
                    className="w-16 rounded border border-border px-1 py-0.5" value={draft.remindMinutes}
                    onChange={(e) => setDraft({ ...draft, remindMinutes: Number(e.target.value) })} />
                  分钟
                </label>
              </div>
              {formError ? <p className="text-ui-caption text-red-500" data-testid="board-dlg-error">{formError}</p> : null}
              <div className="mt-1 flex justify-end gap-2">
                <button type="button" data-testid="board-dlg-cancel" className="rounded border border-border px-3 py-1" onClick={() => setDraft(null)}>取消</button>
                <button type="button" data-testid="board-dlg-save" disabled={saving} className="rounded bg-selected px-3 py-1 disabled:opacity-50" onClick={saveDraft}>
                  {saving ? "保存中…" : "保存"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function shiftDay(isoDate: string, days: number): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!m) return isoDate;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
