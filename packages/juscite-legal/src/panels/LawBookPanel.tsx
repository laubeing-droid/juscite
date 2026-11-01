// 功能 #13 法条手册（RE-13-法条手册.md §3.2 UI 结构落码）：主壳内嵌面板，三区布局。
// 左=分组目录树（组折叠+子文件夹组+>8 截断"更多"）+全局搜索（目录/全文双模式+历史）；
// 中=内容阅读区（效力横幅/居中标题/分节正文+分隔线/条号加粗/管道表）；右=篇内锚点目录+篇内搜索。
// 状态机（§3.2）：列表 idle→loading→ready/error；内容 loading→ready/error；搜索 idle→searching→ready/error
// （取消在途回 idle）；篇内过滤 filtering（保留上一结果）/ready/error；收藏乐观更新失败回滚。
// 数据经 /api/legal/laws* 与 /api/legal/packs*（桥端点族）；fail-closed 具名报错→错误占位，不白屏不崩溃。
// 文案全部自写（表达隔离）；深浅色跟随壳主题（主题 token）。
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  Bookmark, ChevronDown, ChevronRight, Copy, Heart, Info, ListTree, Package,
  RotateCw, Search, Settings, Share2, X,
} from "lucide-react";

// ── 类型（桥端点形状）──
type Effect = "current" | "repealed" | "not_yet";
type LawMeta = {
  id: string; name: string; subtitle: string; level: string; categoryId: string; categoryName: string;
  publish: string; ver: number; publishShow: boolean; effect: Effect; effectLabel: string;
};
type Para = { line: number; text: string; articleNo: string | null; table?: string[] };
type Section = { level: number; title: string; line: number };
type TocNode = { level: number; title: string; line: number; children: TocNode[] };
type LawContent = {
  titles: string[]; info: Array<{ key: string; value: string }>;
  sections: Section[]; toc: TocNode[]; paragraphs: Para[];
};
type CatsResp = {
  available: boolean; total: number;
  dept: Array<{ id: string; name: string; folder: string; group: string; sortOrder: number; count: number; repealed: number; notYet: number }>;
  levels: Array<{ level: string; count: number; repealed: number; notYet: number }>;
  levelOrder: string[];
};
type FilterResp = { query: string; hitCount: number; firstHitLine: number | null; sections: Section[]; paragraphs: Para[] };
type FavData = {
  folders: Array<{ id: string; name: string; sortOrder: number }>;
  laws: Array<{ rowId: string; lawId: string; name: string; effect: string; createdAt: number }>;
  contents: Array<{ rowId: string; lawId: string; line: number; folderId: string; name: string; effect: string; text: string | null }>;
};
type HistoryItem = { rowId: string; text: string; lawId: string | null; searchT: number };
type PackInfo = { name: string; state: string; lawCount: number; reason: string; hash: string; update: number; filesize: number };

// ── 偏好（面板级本地偏好：值域自研钉定 10–40 / 0–20，步进到界停走；默认 17/0.6/4.5/4 等量竞品）──
const PREF_KEY = "lawbook.prefs.v1";
const FONT_RANGE = { min: 10, max: 40, step: 1, def: 17 };
const SPACING_RANGE = { min: 0, max: 20, step: 0.1, def: 4.5 };
const TRACKING_RANGE = { min: 0, max: 20, step: 0.6, def: 0.6 }; // 步长 0.6×?——字间距步进 0.1 基准，见 clampStep
type Prefs = { font: number; tracking: number; lineSpacing: number; articleSpacing: number };
const DEFAULT_PREFS: Prefs = { font: 17, tracking: 0.6, lineSpacing: 4.5, articleSpacing: 4 };
// G4 超时口径（RE-13 §3.2 第 17 轮钉定）：搜索与篇内过滤 ?q= 均为前端 fetch 侧判定（AbortController），
// 阈值 10s——轻量包本地桥内遍历毫秒级，10s 只覆盖异常路径；超时与失败同入 error 态可重试。
const FETCH_TIMEOUT_MS = 10000;
function clamp(v: number, min: number, max: number) { return Math.min(max, Math.max(min, v)); }
function loadPrefs(): Prefs {
  try {
    const raw = JSON.parse(localStorage.getItem(PREF_KEY) ?? "{}");
    return {
      font: clamp(Number(raw.font ?? DEFAULT_PREFS.font), FONT_RANGE.min, FONT_RANGE.max),
      tracking: clamp(Number(raw.tracking ?? DEFAULT_PREFS.tracking), SPACING_RANGE.min, SPACING_RANGE.max),
      lineSpacing: clamp(Number(raw.lineSpacing ?? DEFAULT_PREFS.lineSpacing), SPACING_RANGE.min, SPACING_RANGE.max),
      articleSpacing: clamp(Number(raw.articleSpacing ?? DEFAULT_PREFS.articleSpacing), SPACING_RANGE.min, SPACING_RANGE.max),
    };
  } catch { return { ...DEFAULT_PREFS }; }
}

const EFFECT_STYLE: Record<Effect, { warn: string; text: string }> = {
  current: { warn: "", text: "" },
  repealed: { warn: "text-foreground-subtle", text: "text-foreground-subtle" }, // 已废止=灰字+灰⚠
  not_yet: { warn: "text-amber-500", text: "text-foreground-subtle" }, // 未施行=灰字+橙⚠（等量 A5）
};
const EFFECT_BANNER: Record<Exclude<Effect, "current">, { cls: string }> = {
  repealed: { cls: "border-border bg-header text-foreground-subtle" },
  not_yet: { cls: "border-amber-500/50 bg-amber-500/10 text-amber-600 dark:text-amber-400" },
};

export function LawBookPanel({ onVerifyCitation }: { onVerifyCitation?: (citation: string) => void } = {}) {
  // 【#14 G9 联动】「核验此条」两挂点：条文页工具行（标题级预填）+段落右键菜单（带条号预填）。
  // 预填文本确定性构造：《法名》（包内精确名）+Para.articleNo（解析产物，不猜条号）。
  // ── 列表面状态机：idle→loading→ready/error（A6/A8/§3.2）──
  const [catsStatus, setCatsStatus] = useState<"loading" | "ready" | "error">("loading");
  const [cats, setCats] = useState<CatsResp | null>(null);
  const [catsErr, setCatsErr] = useState("");
  const [packStatus, setPackStatus] = useState<PackInfo[]>([]);
  const [groupMode, setGroupMode] = useState<"dept" | "level">(() => (localStorage.getItem("lawbook.groupMode") === "level" ? "level" : "dept"));
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [showAll, setShowAll] = useState<Set<string>>(new Set());
  const [activeCat, setActiveCat] = useState("");

  // ── 全局搜索（C1–C6）──
  const [view, setView] = useState<"browse" | "bookmarks">("browse");
  const [searchQ, setSearchQ] = useState("");
  const [searchMode, setSearchMode] = useState<"title" | "fulltext">("title");
  const [searchState, setSearchState] = useState<"idle" | "searching" | "ready" | "error">("idle");
  const [searchResults, setSearchResults] = useState<LawMeta[]>([]);
  const [searchErr, setSearchErr] = useState("");
  const [historyScope, setHistoryScope] = useState<"shared" | "standalone">(() =>
    localStorage.getItem("lawbook.historyScope") === "standalone" ? "standalone" : "shared");
  const [history, setHistory] = useState<HistoryItem[]>([]);

  // ── 内容面状态机：idle→loading→ready/error（§3.2）──
  const [content, setContent] = useState<{ state: "idle" | "loading" | "ready" | "error"; law?: LawMeta; data?: LawContent; err?: string }>({ state: "idle" });
  // ── 篇内过滤（B6）：filtering 保留上一结果 + 轻量进行中标记 ──
  const [filter, setFilter] = useState<{ state: "idle" | "filtering" | "ready" | "error"; data?: FilterResp; err?: string; q: string }>({ state: "idle", q: "" });
  const [filterDraft, setFilterDraft] = useState("");

  // ── 收藏（B7/B9/D1–D4）──
  const [fav, setFav] = useState<FavData>({ folders: [], laws: [], contents: [] });
  const [favorited, setFavorited] = useState(false);
  const [heartBusy, setHeartBusy] = useState(false);
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; para: Para } | null>(null);
  const [pickFolder, setPickFolder] = useState<{ para: Para } | null>(null);
  const [shareCard, setShareCard] = useState<{ title: string; text: string } | null>(null);
  const [toast, setToast] = useState("");

  // ── 书签子页（D2–D4）──
  const [bookmarkFolder, setBookmarkFolder] = useState<string | null>(null);
  const [editingBookmarks, setEditingBookmarks] = useState(false);
  const [pickedRows, setPickedRows] = useState<Set<string>>(new Set());
  const [newFolderName, setNewFolderName] = useState("");
  const [renamingFolder, setRenamingFolder] = useState<{ id: string; name: string } | null>(null);

  // ── 对话框族 ──
  const [showToc, setShowToc] = useState(false);
  const [showAbout, setShowAbout] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showPacks, setShowPacks] = useState(false);
  const [showSource, setShowSource] = useState(false);
  const [prefs, setPrefs] = useState<Prefs>(() => loadPrefs());

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const searchAbort = useRef<AbortController | null>(null);
  const contentAbort = useRef<AbortController | null>(null);
  const filterAbort = useRef<AbortController | null>(null);

  const flash = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((t) => (t === msg ? "" : t)), 2200);
  }, []);

  // 前端 fetch 侧 10s 超时（G4）：到时 abort；timedOut 标记区分「超时入 error 可重试」与「用户取消静默回 idle」。
  const armTimeout = useCallback((ac: AbortController) => {
    const flag = { timedOut: false };
    const timer = window.setTimeout(() => { flag.timedOut = true; ac.abort(); }, FETCH_TIMEOUT_MS);
    return { flag, disarm: () => window.clearTimeout(timer) };
  }, []);

  const api = useCallback(async <T,>(path: string, init?: RequestInit & { signal?: AbortSignal }): Promise<T> => {
    const r = await fetch(`/api/legal/laws${path}`, { cache: "no-store", ...init });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j?.error?.message ?? `桥应答 ${r.status}`);
    return j as T;
  }, []);

  const loadFav = useCallback(async () => {
    try { setFav(await api<FavData>("/favorites")); } catch { /* 书签面自显错误态，列表静默 */ }
  }, [api]);

  const loadHistory = useCallback(async (scope: "shared" | "standalone", lawId?: string) => {
    try {
      const q = new URLSearchParams({ scope });
      if (scope === "standalone" && lawId) q.set("lawId", lawId);
      const r = await api<{ items: HistoryItem[] }>(`/history?${q}`);
      setHistory(r.items);
    } catch { setHistory([]); }
  }, [api]);

  const loadCats = useCallback(async () => {
    setCatsStatus("loading"); setCatsErr("");
    try {
      const [c, s] = await Promise.all([api<CatsResp>("/categories"), api<{ packs: PackInfo[] }>("/status")]);
      setCats(c);
      setPackStatus(s.packs);
      setCatsStatus("ready");
    } catch (e) {
      setCatsErr(e instanceof Error ? e.message : String(e));
      setCatsStatus("error");
    }
  }, [api]);

  useEffect(() => { void loadCats(); void loadFav(); void loadHistory(historyScope); }, [loadCats, loadFav, loadHistory, historyScope]);

  // ── 打开法条（B10：loading/error 态；C3：带词自动篇内过滤）──
  const openLaw = useCallback(async (meta: LawMeta, opts?: { filterWord?: string }) => {
    contentAbort.current?.abort();
    filterAbort.current?.abort(); // 取消前一篇在途篇内过滤（?q= 走 G4 超时口径，独立 AbortController）
    const ac = new AbortController();
    contentAbort.current = ac;
    setView("browse");
    setContent({ state: "loading", law: meta });
    setFilter({ state: "idle", q: "" });
    setFilterDraft(opts?.filterWord ?? "");
    setFavorited(false);
    try {
      const d = await api<{ law: LawMeta; content: LawContent }>(`/${meta.id}`, { signal: ac.signal });
      setContent({ state: "ready", law: d.law, data: d.content });
      if (opts?.filterWord) {
        const fac = new AbortController();
        filterAbort.current = fac;
        const ft = armTimeout(fac);
        setFilter({ state: "filtering", q: opts.filterWord });
        try {
          const f = await api<FilterResp>(`/${meta.id}?q=${encodeURIComponent(opts.filterWord)}`, { signal: fac.signal });
          setFilter({ state: "ready", data: f, q: opts.filterWord });
        } catch (e) {
          if (fac.signal.aborted && ft.flag.timedOut) setFilter({ state: "error", err: `篇内过滤超时（${FETCH_TIMEOUT_MS / 1000} 秒），可重试`, q: opts.filterWord });
          else if (!fac.signal.aborted) setFilter({ state: "error", err: e instanceof Error ? e.message : String(e), q: opts.filterWord });
        } finally { ft.disarm(); }
      }
      api<{ favorited: boolean }>(`/favorites/law?lawId=${encodeURIComponent(meta.id)}`)
        .then((r) => setFavorited(r.favorited))
        .catch(() => { /* 心形回读失败保持未收藏，可重开刷新 */ });
    } catch (e) {
      if (ac.signal.aborted) return;
      setContent({ state: "error", law: meta, err: e instanceof Error ? e.message : String(e) });
    }
  }, [api, armTimeout]);

  // ── 全局搜索提交（长任务三态+可取消；改词/切模式取消在途，C1）──
  const runSearch = useCallback(async (word: string, mode: "title" | "fulltext") => {
    const q = word.trim();
    searchAbort.current?.abort();
    if (!q) { // C6：空查询提交=清空结果回历史
      setSearchState("idle"); setSearchResults([]); setSearchErr("");
      void loadHistory(historyScope);
      return;
    }
    const ac = new AbortController();
    searchAbort.current = ac;
    const t = armTimeout(ac);
    setSearchState("searching"); setSearchErr("");
    try {
      // 全局搜索不夹带目录树选中项（activeCat 只作用于组内浏览展开，避免隐性过滤）
      const r = await api<{ results: LawMeta[] }>(`?query=${encodeURIComponent(q)}&mode=${mode}`, { signal: ac.signal });
      setSearchResults(r.results);
      setSearchState("ready");
    } catch (e) {
      if (ac.signal.aborted && t.flag.timedOut) { // 超时与失败同入 error 态可重试（§3.2 G4 口径）
        setSearchErr(`搜索超时（${FETCH_TIMEOUT_MS / 1000} 秒），可重试`);
        setSearchState("error");
      } else if (ac.signal.aborted) {
        return; // 用户取消/改词取消：静默回 idle
      } else {
        setSearchErr(e instanceof Error ? e.message : String(e));
        setSearchState("error");
      }
    } finally { t.disarm(); }
  }, [api, armTimeout, historyScope, loadHistory]);

  // 历史落库（C4/对拍 11：提交与点击历史项都刷新时间戳——同词=刷新原记录不新增，竞品点击 updateSearchT 同语义）
  const putHistoryText = useCallback((text: string) => {
    void api("/history", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text, scope: historyScope, lawId: null }) })
      .then(() => loadHistory(historyScope))
      .catch(() => { /* 历史落库失败不阻塞搜索 */ });
  }, [api, historyScope, loadHistory]);

  const submitSearch = useCallback(() => {
    const q = searchQ.trim();
    putHistoryText(q);
    void runSearch(q, searchMode);
  }, [putHistoryText, runSearch, searchMode, searchQ]);

  // ── 篇内过滤提交（B6：filtering/error/取消三态；清空恢复全文）──
  const runFilter = useCallback(async (word: string) => {
    if (!content.law) return;
    filterAbort.current?.abort();
    const q = word.trim();
    if (!q) { setFilter({ state: "idle", q: "" }); return; }
    const ac = new AbortController();
    filterAbort.current = ac;
    const t = armTimeout(ac); // ?q= 归 G4 前端 10s 超时口径（§3.2）
    setFilter({ state: "filtering", q });
    try {
      const f = await api<FilterResp>(`/${content.law.id}?q=${encodeURIComponent(q)}`, { signal: ac.signal });
      setFilter({ state: "ready", data: f, q });
    } catch (e) {
      if (ac.signal.aborted && t.flag.timedOut) setFilter({ state: "error", err: `篇内过滤超时（${FETCH_TIMEOUT_MS / 1000} 秒）`, q });
      else if (ac.signal.aborted) return;
      else setFilter({ state: "error", err: e instanceof Error ? e.message : String(e), q });
    } finally { t.disarm(); }
  }, [api, armTimeout, content.law]);

  // ── 整法收藏开关（B9：乐观更新失败回滚；回读中不可点）──
  const toggleFavLaw = useCallback(async () => {
    if (!content.law || heartBusy) return;
    setHeartBusy(true);
    const prev = favorited;
    setFavorited(!prev);
    try {
      const r = await api<{ favorited: boolean }>("/favorites/law/toggle", {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ lawId: content.law.id }),
      });
      setFavorited(r.favorited);
      void loadFav();
    } catch (e) {
      setFavorited(prev); // 失败回滚
      flash(e instanceof Error ? e.message : "收藏失败");
    } finally { setHeartBusy(false); }
  }, [api, content.law, favorited, flash, heartBusy, loadFav]);

  // ── 段落收藏（B7：选夹；无幂等——重复收藏新增条目）──
  const favPara = useCallback(async (folderId: string, para: Para) => {
    if (!content.law) return;
    try {
      await api("/favorites/content", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ lawId: content.law.id, line: para.line, folderId }),
      });
      flash("已收藏到夹");
      void loadFav();
    } catch (e) { flash(e instanceof Error ? e.message : "收藏失败"); }
  }, [api, content.law, flash, loadFav]);

  const copyText = useCallback(async (text: string) => {
    try { await navigator.clipboard.writeText(text); flash("已复制"); }
    catch { flash("复制失败（浏览器拒绝剪贴板）"); }
  }, [flash]);

  const scrollToLine = useCallback((line: number) => {
    const el = scrollRef.current?.querySelector(`[data-line="${line}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "start" }); // 等量 B4：平滑滚动到行号锚
  }, []);

  const switchGroup = (m: "dept" | "level") => {
    setGroupMode(m);
    localStorage.setItem("lawbook.groupMode", m);
    setShowAll(new Set());
  };

  // ── 目录树数据（A1–A4/A8：分组/折叠/截断/空态）──
  // 分类→法条列表由桥端点按需拉取：目录组仅承载计数（等量形态：组→组内子文件夹/法列表两级）
  const [catLaws, setCatLaws] = useState<Record<string, LawMeta[]>>({});
  const loadCatLaws = useCallback(async (catId: string) => {
    if (catLaws[catId]) return;
    // 部门组键走桥 category 过滤（A1）；阶位组键 level:* 走桥 level 过滤（A2/对拍 1 双分组浏览同构）
    const qs = catId.startsWith("level:")
      ? `level=${encodeURIComponent(catId.slice("level:".length))}`
      : `category=${encodeURIComponent(catId)}`;
    try {
      const r = await api<{ results: LawMeta[] }>(`?query=&mode=title&${qs}`);
      setCatLaws((m) => ({ ...m, [catId]: r.results }));
    } catch { setCatLaws((m) => ({ ...m, [catId]: [] })); }
  }, [api, catLaws]);

  if (catsStatus === "loading") {
    return <PanelShell><div className="flex h-40 items-center justify-center text-ui-sm text-foreground-subtle" data-testid="lawbook-loading">法条手册加载中…</div></PanelShell>;
  }
  if (catsStatus === "error") {
    return (
      <PanelShell>
        <div className="flex h-40 flex-col items-center justify-center gap-2" data-testid="lawbook-list-error">
          <p className="text-ui-sm text-red-500">目录拉取失败：{catsErr}</p>
          <Button2 onClick={() => void loadCats()}><RotateCw className="size-4" /> 重试</Button2>
        </div>
      </PanelShell>
    );
  }
  const packBroken = cats ? !cats.available : false;

  return (
    <PanelShell>
      {/* ── 面板头 ── */}
      <div className="mb-3 flex items-center gap-2">
        <ListTree className="size-5" />
        <h2 className="text-ui-lg font-medium">法条手册</h2>
        <span className="text-ui-caption text-foreground-subtle">内置快照 · 效力徽章运行时推导（UTC+8 日历日）</span>
        <div className="ml-auto flex items-center gap-1">
          <IconBtn title="书签" testid="lawbook-bookmarks" active={view === "bookmarks"} onClick={() => { setView(view === "bookmarks" ? "browse" : "bookmarks"); setBookmarkFolder(null); void loadFav(); }}><Bookmark className="size-4" /></IconBtn>
          <IconBtn title="法条包" testid="lawbook-packs-btn" onClick={() => setShowPacks(true)}><Package className="size-4" /></IconBtn>
          <IconBtn title="阅读偏好" testid="lawbook-settings-btn" onClick={() => setShowSettings(true)}><Settings className="size-4" /></IconBtn>
          <IconBtn title="数据来源与声明" testid="lawbook-source-btn" onClick={() => setShowSource(true)}><Info className="size-4" /></IconBtn>
        </div>
      </div>

      {packBroken ? (
        /* 首启包引导失败兜底（§3.1）：面板降级占位，主壳不崩、不静默用残包 */
        <div className="flex h-56 flex-col items-center justify-center gap-2 rounded border border-border" data-testid="lawbook-pack-face">
          <p className="text-ui-base font-medium">法条包不可用</p>
          <p className="max-w-md text-center text-ui-caption text-foreground-subtle">
            {packStatus.map((p) => `${p.name}：${p.reason}`).join("；") || "未安装法条包"}
          </p>
          <div className="flex gap-2">
            <Button2 onClick={() => { void api("/../packs", {}).catch(() => {}); void loadCats(); }}><RotateCw className="size-4" /> 重试</Button2>
            <Button2 onClick={() => setShowPacks(true)}><Package className="size-4" /> 查看法条包</Button2>
          </div>
        </div>
      ) : view === "bookmarks" ? (
        /* ── 书签子页（D1–D4）── */
        <BookmarksView />
      ) : (
        /* ── 三区主面 ── */
        <div className="grid grid-cols-[300px_1fr_260px] gap-3" style={{ height: 620 }}>
          {/* 左栏 */}
          <div className="flex min-h-0 flex-col rounded border border-border bg-background">
            <div className="border-b border-border p-2">
              <div className="flex items-center gap-1">
                <input
                  data-testid="lawbook-search-input"
                  className="min-w-0 flex-1 rounded border border-border bg-header px-2 py-1 text-ui-sm"
                  placeholder="搜索法条名称或全文…"
                  value={searchQ}
                  onChange={(e) => { setSearchQ(e.target.value); if (searchState === "searching") searchAbort.current?.abort(); if (searchState !== "idle") { setSearchState("idle"); setSearchResults([]); } }} // 改词=取消在途回 idle（§3.2 状态机）
                  onKeyDown={(e) => { if (e.key === "Enter") submitSearch(); }}
                />
                {searchState === "searching"
                  ? <Button2 testid="lawbook-search-cancel" onClick={() => { searchAbort.current?.abort(); setSearchState("idle"); }}>取消</Button2>
                  : <Button2 testid="lawbook-search-go" onClick={submitSearch}><Search className="size-4" /></Button2>}
              </div>
              <div className="mt-1 flex items-center gap-1 text-ui-caption">
                {(["title", "fulltext"] as const).map((m) => (
                  <button
                    key={m} type="button" data-testid={`lawbook-search-mode-${m}`}
                    className={`rounded px-2 py-0.5 ${searchMode === m ? "bg-selected text-ui-base" : "text-foreground-subtle"}`}
                    onClick={() => { setSearchMode(m); searchAbort.current?.abort(); setSearchState("idle"); setSearchResults([]); }} // 切模式=取消在途+清空结果（C1/§3.2 状态机）
                  >{m === "title" ? "目录" : "全文"}</button>
                ))}
                <span className="ml-auto flex items-center gap-1">
                  历史域
                  <select
                    data-testid="lawbook-history-scope"
                    className="rounded border border-border bg-header px-1"
                    value={historyScope}
                    onChange={(e) => {
                      const s = e.target.value as "shared" | "standalone";
                      setHistoryScope(s); localStorage.setItem("lawbook.historyScope", s);
                      void loadHistory(s);
                    }}
                  ><option value="shared">共享</option><option value="standalone">独立</option></select>
                </span>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-2">
              {searchState === "idle" ? (
                /* 未提交态=历史（C4：最近 10 条、倒序、单删、清空、点击重搜） */
                <div data-testid="lawbook-history">
                  <div className="mb-1 flex items-center justify-between text-ui-caption text-foreground-subtle">
                    <span>最近搜索</span>
                    {history.length > 0 && (
                      <button type="button" data-testid="lawbook-history-clear" className="hover:underline"
                        onClick={async () => { try { await api("/history/clear", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ scope: historyScope, lawId: null }) }); void loadHistory(historyScope); } catch { /* ignore */ } }}>清空</button>
                    )}
                  </div>
                  {history.length === 0 ? <p className="text-ui-caption text-foreground-subtle">暂无搜索历史</p> : null}
                  {history.map((h) => (
                    <div key={h.rowId} className="group flex items-center rounded px-1 hover:bg-selected">
                      <button type="button" data-testid="lawbook-history-item" className="min-w-0 flex-1 truncate py-1 text-left text-ui-sm"
                        onClick={() => { setSearchQ(h.text); putHistoryText(h.text); void runSearch(h.text, searchMode); }}>{h.text}</button>
                      <button type="button" className="px-1 text-foreground-subtle opacity-0 group-hover:opacity-100" title="删除该条"
                        onClick={async () => { try { await api("/history/delete", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ rowId: h.rowId }) }); void loadHistory(historyScope); } catch { /* ignore */ } }}>×</button>
                    </div>
                  ))}
                  <div className="mt-3 border-t border-border pt-2">
                    <TreeFace />
                  </div>
                </div>
              ) : searchState === "searching" ? (
                <div className="flex h-24 items-center justify-center text-ui-sm text-foreground-subtle" data-testid="lawbook-searching">搜索中…</div>
              ) : searchState === "error" ? (
                <div className="flex flex-col items-center gap-2 p-4" data-testid="lawbook-search-error">
                  <p className="text-ui-sm text-red-500">搜索失败：{searchErr}</p>
                  <Button2 onClick={() => void runSearch(searchQ, searchMode)}><RotateCw className="size-4" /> 重试</Button2>
                </div>
              ) : (
                <div data-testid="lawbook-search-results">
                  <p className="mb-1 text-ui-caption text-foreground-subtle">{searchResults.length} 条结果</p>
                  {searchResults.length === 0 ? (
                    /* 空态：搜索无结果占位（§3.2 自研增补，竞品为空列表） */
                    <div className="flex flex-col items-center gap-1 py-6 text-center" data-testid="lawbook-search-empty">
                      <p className="text-ui-sm">未找到匹配的法规</p>
                      <p className="text-ui-caption text-foreground-subtle">可换个关键词，或切换「目录 / 全文」模式重搜。</p>
                    </div>
                  ) : searchResults.map((m) => <LawRow key={m.id} meta={m} onOpen={() => void openLaw(m, searchMode === "fulltext" ? { filterWord: searchQ.trim() } : undefined)} />)}
                </div>
              )}
            </div>
          </div>

          {/* 中栏：内容阅读区 */}
          <div className="flex min-h-0 flex-col rounded border border-border bg-background">
            {content.state === "idle" ? (
              <div className="flex h-full items-center justify-center text-ui-sm text-foreground-subtle" data-testid="lawbook-content-idle">
                从左侧选择一部法规开始阅读
              </div>
            ) : content.state === "loading" ? (
              <div className="flex h-full items-center justify-center text-ui-sm text-foreground-subtle" data-testid="lawbook-content-loading">正文加载中…</div>
            ) : content.state === "error" ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 p-6" data-testid="lawbook-content-error">
                <p className="text-ui-sm text-red-500">正文读取失败：{content.err}</p>
                <div className="flex gap-2">
                  {content.law && <Button2 onClick={() => void openLaw(content.law!)}><RotateCw className="size-4" /> 重试</Button2>}
                  <Button2 onClick={() => setContent({ state: "idle" })}>返回列表</Button2>
                </div>
              </div>
            ) : (
              <ContentView />
            )}
          </div>

          {/* 右栏：锚点目录 + 篇内搜索 */}
          <div className="flex min-h-0 flex-col rounded border border-border bg-background">
            <div className="border-b border-border p-2">
              <input
                data-testid="lawbook-filter-input"
                className="w-full rounded border border-border bg-header px-2 py-1 text-ui-sm"
                placeholder="篇内搜索（回车过滤）…"
                value={filterDraft}
                onChange={(e) => {
                  setFilterDraft(e.target.value);
                  if (!e.target.value.trim() && filter.state !== "idle") setFilter({ state: "idle", q: "" }); // 清空恢复全文
                }}
                onKeyDown={(e) => { if (e.key === "Enter") void runFilter(filterDraft); }}
              />
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-2" data-testid="lawbook-toc">
              {/* B4 右栏常驻形态：无 sections 的法=空态占位（文案自写），篇内搜索框仍可用（§2 B4 第 18 轮补） */}
              {content.state === "ready" && content.data
                ? (content.data.toc.length
                  ? <TocNodes nodes={content.data.toc} depth={0} />
                  : <p className="text-ui-caption text-foreground-subtle" data-testid="lawbook-toc-empty">本篇无分节目录</p>)
                : <p className="text-ui-caption text-foreground-subtle">打开法条后显示目录</p>}
            </div>
          </div>
        </div>
      )}

      {/* ── 对话框族 ── */}
      {ctxMenu ? <ContextMenu /> : null}
      {pickFolder && content.law ? <FolderPicker para={pickFolder.para} /> : null}
      {shareCard ? <ShareCardView /> : null}
      {showToc && content.data ? <TocSheet /> : null}
      {showAbout && content.data ? <AboutSheet /> : null}
      {showSettings ? <SettingsSheet /> : null}
      {showPacks ? <PacksSheet /> : null}
      {showSource ? <SourceSheet /> : null}
      {toast ? <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded bg-foreground px-3 py-1.5 text-ui-sm text-background shadow" data-testid="lawbook-toast">{toast}</div> : null}
    </PanelShell>
  );

  // ── 子组件（同文件就近维护）──
  function PanelShell({ children }: { children: ReactNode }) {
    return (
      <section data-testid="lawbook-panel" className="rounded-workspace-panel border border-border bg-header p-4">
        {children}
      </section>
    );
  }
  function Button2({ children, onClick, testid, disabled }: { children: ReactNode; onClick?: () => void; testid?: string; disabled?: boolean }) {
    return (
      <button type="button" data-testid={testid} disabled={disabled} onClick={onClick}
        className="flex items-center gap-1 rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected disabled:opacity-50">
        {children}
      </button>
    );
  }
  function IconBtn({ children, onClick, title, testid, active }: { children: ReactNode; onClick?: () => void; title: string; testid?: string; active?: boolean }) {
    return (
      <button type="button" title={title} data-testid={testid} onClick={onClick}
        className={`rounded p-1.5 hover:bg-selected ${active ? "bg-selected" : ""}`}>{children}</button>
    );
  }

  function TreeFace() {
    if (!cats) return null;
    if (cats.total === 0 || cats.dept.length === 0) {
      // A8：整列表零分组=左栏空态占位（自研增补，竞品为空白 List）
      return (
        <div className="flex flex-col items-center gap-1 py-8 text-center" data-testid="lawbook-list-empty">
          <p className="text-ui-sm">未安装法条包，或包不可用</p>
          <p className="text-ui-caption text-foreground-subtle">可在「法条包」面板查看状态或重新导入</p>
          <Button2 testid="lawbook-list-empty-packs" onClick={() => setShowPacks(true)}><Package className="size-4" /> 查看法条包</Button2>
        </div>
      );
    }
    const entries = groupMode === "dept"
      ? (() => {
        // 部门模式：顶层组=group 块（A3 子文件夹组）+group 为空的顶层目录
        const tops = cats.dept.filter((c) => !c.group);
        const grouped = new Map<string, typeof cats.dept>();
        for (const c of cats.dept) {
          if (!c.group) continue;
          const arr = grouped.get(c.group) ?? [];
          arr.push(c);
          grouped.set(c.group, arr);
        }
        return [
          ...[...grouped.entries()].map(([g, arr]) => ({ key: `gp:${g}`, label: g, cats: arr })),
          ...tops.map((c) => ({ key: `cat:${c.id}`, label: c.name, cats: [c] })),
        ];
      })()
      : [{ key: "levels", label: "", cats: cats.dept.filter((c) => cats.levels.some((l) => l.level === c.name)) }];
    return (
      <div>
        <div className="mb-1 flex items-center gap-1 text-ui-caption">
          <span className="text-foreground-subtle">分组方式</span>
          <button type="button" data-testid="lawbook-group-dept" className={`rounded px-1.5 ${groupMode === "dept" ? "bg-selected" : "text-foreground-subtle"}`} onClick={() => switchGroup("dept")}>法律部门</button>
          <button type="button" data-testid="lawbook-group-level" className={`rounded px-1.5 ${groupMode === "level" ? "bg-selected" : "text-foreground-subtle"}`} onClick={() => switchGroup("level")}>法律阶位</button>
        </div>
        {groupMode === "level" ? cats.levels.map((l) => {
          const key = `level:${l.level}`; // 阶位行可展开浏览组内法规（A2/对拍 1：双分组目录树同构；组序=桥固定 11 档序）
          return (
            <div key={l.level}>
              <button type="button" data-testid="lawbook-level-item"
                className={`flex w-full items-center justify-between rounded px-1 py-0.5 text-ui-sm hover:bg-selected ${activeCat === key ? "bg-selected" : ""}`}
                onClick={() => { setActiveCat(key); void loadCatLaws(key); }}>
                <span>{l.level}</span>
                <span className="text-foreground-subtle">{l.count}{l.repealed ? `（废 ${l.repealed}）` : ""}{l.notYet ? `（未施行 ${l.notYet}）` : ""}</span>
              </button>
              {activeCat === key ? <CatLaws catId={key} /> : null}
            </div>
          );
        }) : null}
        {groupMode === "dept" ? entries.map((g) => (
          <div key={g.key} className="mb-1">
            {g.label ? (
              <button type="button" className="flex w-full items-center gap-1 py-0.5 text-ui-sm font-medium"
                onClick={() => setCollapsed((s) => { const n = new Set(s); n.has(g.key) ? n.delete(g.key) : n.add(g.key); return n; })}>
                {collapsed.has(g.key) ? <ChevronRight className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                {g.label}
              </button>
            ) : null}
            {!collapsed.has(g.key) ? g.cats.map((c) => (
              <div key={c.id} className="ml-2">
                <button type="button" data-testid="lawbook-cat-item"
                  className={`flex w-full items-center justify-between rounded px-1 py-0.5 text-ui-sm hover:bg-selected ${activeCat === c.id ? "bg-selected" : ""}`}
                  onClick={() => { setActiveCat(c.id); void loadCatLaws(c.id); }}>
                  <span>{c.name}</span>
                  <span className="text-foreground-subtle">{c.count}{c.repealed ? `（废 ${c.repealed}）` : ""}</span>
                </button>
                {activeCat === c.id ? <CatLaws catId={c.id} /> : null}
              </div>
            )) : null}
          </div>
        )) : null}
      </div>
    );
  }

  function CatLaws({ catId }: { catId: string }) {
    const laws = catLaws[catId];
    if (!laws) return <p className="ml-3 py-0.5 text-ui-caption text-foreground-subtle">载入中…</p>;
    const expanded = showAll.has(catId);
    // A4/对拍 2：仅 >8 且未展开才截前 5+「更多」；≤8 部全量平铺；展开（showAll）不截断
    const visible = laws.length > 8 && !expanded ? laws.slice(0, 5) : laws;
    return (
      <div className="ml-3 border-l border-border pl-1">
        {laws.length === 0 ? <p className="py-0.5 text-ui-caption text-foreground-subtle">本组暂无法规</p> : null}
        {visible.map((m) => <LawRow key={m.id} meta={m} onOpen={() => void openLaw(m)} />)}
        {laws.length > 8 && !expanded ? (
          <button type="button" data-testid="lawbook-more-btn" className="px-1 py-0.5 text-ui-caption text-foreground-subtle hover:underline"
            onClick={() => setShowAll((s) => { const n = new Set(s); n.add(catId); return n; })}>更多（共 {laws.length} 部）</button>
        ) : null}
        {expanded && laws.length > 8 ? (
          <button type="button" className="px-1 py-0.5 text-ui-caption text-foreground-subtle hover:underline"
            onClick={() => setShowAll((s) => { const n = new Set(s); n.delete(catId); return n; })}>收起</button>
        ) : null}
      </div>
    );
  }

  function LawRow({ meta, onOpen }: { meta: LawMeta; onOpen: () => void }) {
    const st = EFFECT_STYLE[meta.effect];
    return (
      <button type="button" data-testid="lawbook-law-item" onClick={onOpen} className="block w-full rounded px-1 py-0.5 text-left hover:bg-selected">
        <span className={`block truncate text-ui-sm ${st.text}`}>
          {meta.effect !== "current" ? <span className={EFFECT_STYLE[meta.effect].warn}>⚠ </span> : null}
          {meta.name}
        </span>
        {meta.subtitle || meta.publishShow ? (
          <span className="block truncate text-ui-caption text-foreground-subtle">
            {meta.subtitle}{meta.publishShow && meta.subtitle ? " · " : ""}{meta.publishShow ? `公布 ${meta.publish}` : ""}
          </span>
        ) : null}
      </button>
    );
  }

  function ContentView() {
    const law = content.law!;
    const data = content.data!;
    const filtering = filter.state === "filtering";
    const fReady = filter.state === "ready" ? filter.data : null;
    return (
      <>
        {/* 工具行：标题+心形+目录+关于 */}
        <div className="flex items-start gap-2 border-b border-border p-3">
          <div className="min-w-0 flex-1">
            <p className="break-words text-center text-ui-lg font-semibold" data-testid="lawbook-content-title">{data.titles.join(" · ")}</p>
            <p className="text-ui-caption text-foreground-subtle">
              {law.categoryName} · {law.level}
              {law.publishShow ? ` · 公布 ${law.publish}` : ""}
              {law.ver > 1 ? ` · ${law.ver} 个版本` : ""}
            </p>
          </div>
          {onVerifyCitation ? (
            <button type="button" data-testid="lawbook-verify-btn" title="核验此法（单条核验预填）"
              onClick={() => onVerifyCitation(`《${law.name}》`)}
              className="rounded p-1.5 hover:bg-selected text-ui-caption">核验此条</button>
          ) : null}
          <button type="button" data-testid="lawbook-heart" title={favorited ? "取消整法收藏" : "整法收藏"} disabled={heartBusy}
            onClick={() => void toggleFavLaw()} className="rounded p-1.5 hover:bg-selected disabled:opacity-40">
            <Heart className={`size-4 ${favorited ? "fill-red-500 text-red-500" : ""}`} />
          </button>
          {data.toc.length ? <IconBtn title="目录" testid="lawbook-toc-btn" onClick={() => setShowToc(true)}><ListTree className="size-4" /></IconBtn> : null}
          <IconBtn title="关于本法" testid="lawbook-about-btn" onClick={() => setShowAbout(true)}><Info className="size-4" /></IconBtn>
        </div>
        {/* B2：效力横幅两态 */}
        {law.effect !== "current" ? (
          <div className={`mx-3 mt-3 rounded border px-3 py-2 text-ui-sm ${EFFECT_BANNER[law.effect].cls}`} data-testid={`lawbook-banner-${law.effect}`}>
            ⚠ {law.effect === "repealed" ? "本法已废止，条文仅作历史查阅参考。" : "本法暂未施行，以下为公布文本。"}
          </div>
        ) : null}
        {/* 篇内过滤进行中标记（保留上一结果 + 轻量标记） */}
        {filtering ? <div className="mx-3 mt-2 text-ui-caption text-foreground-subtle" data-testid="lawbook-filtering">篇内过滤中：「{filter.q}」…</div> : null}
        {filter.state === "error" ? (
          <div className="mx-3 mt-2 flex items-center gap-2 text-ui-sm text-red-500" data-testid="lawbook-filter-error">
            篇内过滤失败：{filter.err}
            <Button2 onClick={() => void runFilter(filter.q)}>重试</Button2>
            <Button2 onClick={() => { setFilter({ state: "idle", q: "" }); setFilterDraft(""); }}>恢复全文</Button2>
          </div>
        ) : null}
        {/* 正文（过滤态=命中段；否则分节全文） */}
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto px-6 py-4"
          style={{ fontSize: prefs.font, letterSpacing: prefs.tracking, lineHeight: 1.6 + prefs.lineSpacing / 10 }}>
          {filter.state === "ready" && fReady ? (
            fReady.hitCount === 0 ? (
              <div className="flex h-40 flex-col items-center justify-center gap-1 text-foreground-subtle" data-testid="lawbook-filter-empty">
                <p className="text-ui-sm">篇内没有命中「{filter.q}」的条文</p>
                <button type="button" className="text-ui-caption underline" onClick={() => { setFilter({ state: "idle", q: "" }); setFilterDraft(""); }}>恢复全文</button>
              </div>
            ) : (
              <div data-testid="lawbook-filter-hits">
                <p className="mb-2 text-ui-caption text-foreground-subtle">命中 {fReady.hitCount} 段</p>
                {fReady.paragraphs.map((p) => <ParaView key={p.line} para={p} highlight={filter.q} />)}
              </div>
            )
          ) : (
            <div data-testid="lawbook-content-body">
              {data.sections.length === 0
                ? data.paragraphs.map((p) => <ParaView key={p.line} para={p} />)
                : data.sections.map((s, i) => {
                  const next = data.sections[i + 1];
                  const inFilter = filter.state === "ready" && fReady ? fReady.sections.some((fs) => fs.line === s.line) : true;
                  if (!inFilter) return null;
                  const paras = data.paragraphs.filter((p) => p.line >= s.line && p.line < (next?.line ?? Infinity));
                  return (
                    <div key={s.line} data-line={s.line} className="mb-4">
                      <p className="mb-2 text-center font-semibold" style={{ fontSize: prefs.font * (1 + (s.level <= 2 ? 0.12 : 0)) }}>{s.title}</p>
                      {paras.map((p) => <ParaView key={p.line} para={p} />)}
                      {i < data.sections.length - 1 ? <hr className="my-4 border-border" /> : null}
                    </div>
                  );
                })}
            </div>
          )}
        </div>
      </>
    );
  }

  function ParaView({ para, highlight }: { para: Para; highlight?: string }) {
    const body = para.table
      ? (
        <table className="my-1 w-full border-collapse border border-border text-ui-sm">
          <tbody>
            {para.table.map((row, i) => (
              <tr key={i}>
                {row.replace(/^\||\|$/g, "").split("|").map((cell, j) => (
                  <td key={j} className="border border-border px-2 py-0.5">{cell.trim()}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )
      : highlightWith(para.text, highlight);
    // 条号加粗：段首条号加粗渲染，正文从条号之后起（避免条号重复出现）
    const text = para.articleNo && para.text.startsWith(para.articleNo) ? para.text.slice(para.articleNo.length) : para.text;
    return (
      <p
        data-line={para.line}
        className="whitespace-pre-wrap break-words"
        style={{ marginTop: 0, marginBottom: prefs.articleSpacing }}
        onContextMenu={(e) => {
          if (para.table) return;
          e.preventDefault();
          setCtxMenu({ x: e.clientX, y: e.clientY, para });
        }}
      >
        {para.articleNo ? <strong>{para.articleNo}</strong> : null}
        {body === para.text ? text : body}
      </p>
    );
  }

  function highlightWith(text: string, word?: string): ReactNode {
    const w = (word ?? "").trim();
    if (!w || !text.includes(w)) return text;
    const parts: ReactNode[] = [];
    let rest = text;
    let k = 0;
    while (rest) {
      const i = rest.indexOf(w);
      if (i < 0) { parts.push(rest); break; }
      parts.push(rest.slice(0, i));
      parts.push(<mark key={k++} className="rounded bg-amber-200 px-0.5 font-semibold text-inherit dark:bg-amber-500/40" style={{ fontSize: "1.08em" }}>{w}</mark>);
      rest = rest.slice(i + w.length);
    }
    return parts;
  }

  function TocNodes({ nodes, depth, onJump }: { nodes: TocNode[]; depth: number; onJump?: () => void }) {
    return (
      <ul className={depth === 0 ? "" : "ml-3 border-l border-border pl-2"}>
        {nodes.map((n) => (
          <li key={`${n.line}`}>
            <button type="button" data-testid="lawbook-toc-item" className="block w-full truncate py-0.5 text-left text-ui-sm hover:underline"
              onClick={() => { scrollToLine(n.line); onJump?.(); }}>{n.title}</button>
            {n.children.length ? <TocNodes nodes={n.children} depth={depth + 1} onJump={onJump} /> : null}
          </li>
        ))}
      </ul>
    );
  }

  function Dialog({ title, onClose, children, wide, testid }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean; testid?: string }) {
    return (
      <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
        <div className={`max-h-[80vh] overflow-auto rounded border border-border bg-background p-4 shadow-lg ${wide ? "w-[720px]" : "w-[480px]"}`} data-testid={testid}>
          <div className="mb-2 flex items-center justify-between">
            <p className="text-ui-base font-medium">{title}</p>
            <button type="button" onClick={onClose} className="rounded p-1 hover:bg-selected" data-testid="lawbook-dialog-close"><X className="size-4" /></button>
          </div>
          {children}
        </div>
      </div>
    );
  }

  function TocSheet() {
    return (
      <Dialog title="目录" onClose={() => setShowToc(false)} testid="lawbook-toc-sheet">
        <TocNodes nodes={content.data!.toc} depth={0} onJump={() => setShowToc(false)} /> {/* 点击→关 sheet→滚动（等量 B4） */}
      </Dialog>
    );
  }

  function AboutSheet() {
    const info = content.data!.info;
    return (
      <Dialog title="关于本法" onClose={() => setShowAbout(false)} testid="lawbook-about-sheet">
        <div className="flex flex-col gap-2">
          {info.map((kv, i) => kv.key ? (
            <div key={i} className="text-ui-sm"><span className="font-medium">{kv.key}</span><span className="ml-2 text-foreground-subtle">{kv.value}</span></div>
          ) : (
            <p key={i} className="text-center text-ui-sm">{kv.value}</p> // 无键行=居中渲染（等量 B5）
          ))}
          {info.length === 0 ? <p className="text-ui-caption text-foreground-subtle">本法未附制定沿革信息</p> : null}
        </div>
      </Dialog>
    );
  }

  function SettingsSheet() {
    const rows: Array<{ key: keyof Prefs; label: string; range: { min: number; max: number; step: number } }> = [
      { key: "font", label: "正文字号", range: FONT_RANGE },
      { key: "tracking", label: "字间距", range: { min: 0, max: 20, step: 0.1 } },
      { key: "lineSpacing", label: "行间距", range: { min: 0, max: 20, step: 0.1 } },
      { key: "articleSpacing", label: "条间距", range: { min: 0, max: 20, step: 1 } },
    ];
    const step = (k: keyof Prefs, dir: 1 | -1, range: { min: number; max: number; step: number }) => {
      setPrefs((p) => {
        const raw = clamp(Number((p[k] + dir * range.step).toFixed(2)), range.min, range.max); // 到界停走（自研钉值域）
        const next = { ...p, [k]: raw };
        localStorage.setItem(PREF_KEY, JSON.stringify(next));
        return next;
      });
    };
    return (
      <Dialog title="阅读偏好" onClose={() => setShowSettings(false)} testid="lawbook-settings-sheet">
        <div className="flex flex-col gap-3">
          {rows.map((r) => (
            <div key={r.key} className="flex items-center gap-2 text-ui-sm">
              <span className="w-16">{r.label}</span>
              <button type="button" data-testid={`lawbook-pref-${r.key}-dec`} disabled={prefs[r.key] <= r.range.min} onClick={() => step(r.key, -1, r.range)} className="rounded border border-border px-2 disabled:opacity-40">−</button>
              <span className="w-12 text-center tabular-nums" data-testid={`lawbook-pref-${r.key}`}>{prefs[r.key]}</span>
              <button type="button" data-testid={`lawbook-pref-${r.key}-inc`} disabled={prefs[r.key] >= r.range.max} onClick={() => step(r.key, 1, r.range)} className="rounded border border-border px-2 disabled:opacity-40">+</button>
            </div>
          ))}
          {/* 实时预览（合成示例条文，非真实法条） */}
          <div className="rounded border border-border p-3" style={{ fontSize: prefs.font, letterSpacing: prefs.tracking, lineHeight: 1.6 + prefs.lineSpacing / 10 }}>
            <p className="mb-1 text-center font-semibold" style={{ fontSize: prefs.font * 1.12 }}>示例标题</p>
            <p className="mb-2 text-center text-foreground-subtle">示例编 · 示例章</p>
            <p style={{ marginBottom: prefs.articleSpacing }}><strong>第一条</strong> 这是偏好预览用的合成示例条文，用于查看字号与间距效果。</p>
            <p style={{ marginBottom: prefs.articleSpacing }}><strong>第二条</strong> 本段为第二行示例，与上段间距即条间距设置。</p>
          </div>
          <div className="flex justify-end">
            <Button2 testid="lawbook-pref-reset" onClick={() => { setPrefs({ ...DEFAULT_PREFS }); localStorage.setItem(PREF_KEY, JSON.stringify(DEFAULT_PREFS)); }}>恢复默认</Button2>
          </div>
        </div>
      </Dialog>
    );
  }

  function PacksSheet() {
    const [packs, setPacks] = useState<PackInfo[]>(packStatus);
    const refresh = async () => {
      try { const s = await api<{ packs: PackInfo[] }>("/status"); setPacks(s.packs); } catch { /* 保持旧态 */ }
    };
    return (
      <Dialog title="法条包" onClose={() => setShowPacks(false)} testid="lawbook-packs-sheet">
        <div className="flex flex-col gap-2">
          <p className="text-ui-caption text-foreground-subtle">本地包聚合（远端订阅线本期未开放，仅留接口形状）。</p>
          {packs.map((p) => (
            <div key={p.name} className="flex items-center gap-2 rounded border border-border px-2 py-1.5 text-ui-sm" data-testid="lawbook-pack-row">
              <span className="font-medium">{p.name}</span>
              <span className={`text-ui-caption ${p.state === "success" ? "text-foreground-subtle" : "text-red-500"}`}>
                {p.state === "success" ? `正常 · ${p.lawCount} 部 · ${(p.filesize / 1024 / 1024).toFixed(2)} MB` : p.state === "deleted" ? "已标记删除（重启后清理）" : `异常 · ${p.reason}`}
              </span>
              <span className="ml-auto flex gap-1">
                {p.state === "success" ? (
                  <>
                    <Button2 testid={`lawbook-pack-delete-${p.name}`} onClick={async () => {
                      try { await apiU("/api/legal/packs/delete", { name: p.name }); flash("已标记删除，重启桥后清理"); void refresh(); } catch (e) { flash(e instanceof Error ? e.message : "操作失败"); }
                    }}>删除</Button2>
                  </>
                ) : p.state === "deleted" ? (
                  <Button2 testid={`lawbook-pack-revert-${p.name}`} onClick={async () => {
                    try { await apiU("/api/legal/packs/revert", { name: p.name }); flash("已撤销删除标记"); void refresh(); } catch (e) { flash(e instanceof Error ? e.message : "操作失败"); }
                  }}>撤销删除</Button2>
                ) : null}
              </span>
            </div>
          ))}
        </div>
      </Dialog>
    );
  }

  async function apiU(url: string, body: unknown) {
    const r = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j?.error?.message ?? `桥应答 ${r.status}`);
    return j;
  }

  function SourceSheet() {
    return (
      <Dialog title="数据来源与声明" onClose={() => setShowSource(false)} testid="lawbook-source-sheet" wide>
        <div className="flex flex-col gap-2 text-ui-sm">
          <p>本面板法条文本来自公开法库快照，依据《中华人民共和国著作权法》第五条，本法不适用于法律、法规等官方文件，相关文本属公有领域。</p>
          <p>效力徽章由本地数据推导（生效日/废止日/修订链），仅供办案检索参考；正式引用前请以官方公布文本为准。</p>
          <p>
            官方法库：
            <a className="underline" href="https://flk.npc.gov.cn" target="_blank" rel="noreferrer">国家法律法规数据库</a>
            （外链为用户主动点击跳转，本产品不自动出站）。
          </p>
          <p className="text-foreground-subtle">逐条与官方库人工核对尚未进行；日期缺失时按「已施行/未废止」处理，见包内 README 的诚实边界说明。</p>
        </div>
      </Dialog>
    );
  }

  function ContextMenu() {
    const menu = ctxMenu;
    if (!menu) return null;
    const foldersList = fav.folders;
    return (
      <div className="fixed inset-0 z-40" onMouseDown={() => setCtxMenu(null)} onContextMenu={(e) => { e.preventDefault(); setCtxMenu(null); }}>
        <div className="absolute rounded border border-border bg-background py-1 shadow-lg" style={{ left: Math.min(menu.x, window.innerWidth - 180), top: Math.min(menu.y, window.innerHeight - 200) }} data-testid="lawbook-ctx-menu">
          <button type="button" data-testid="lawbook-ctx-fav" className="block w-full px-3 py-1.5 text-left text-ui-sm hover:bg-selected"
            onClick={() => { setPickFolder({ para: menu.para }); setCtxMenu(null); }}>收藏到夹…</button>
          <button type="button" data-testid="lawbook-ctx-copy" className="block w-full px-3 py-1.5 text-left text-ui-sm hover:bg-selected"
            onClick={() => { void copyText(`${content.law?.name ?? ""}\n\n${menu.para.text}`); setCtxMenu(null); }}>
            <Copy className="mr-1 inline size-3.5" />复制条文
          </button>
          <button type="button" data-testid="lawbook-ctx-share" className="block w-full px-3 py-1.5 text-left text-ui-sm hover:bg-selected"
            onClick={() => { setShareCard({ title: content.law?.name ?? "", text: menu.para.text }); setCtxMenu(null); }}>
            <Share2 className="mr-1 inline size-3.5" />分享此段
          </button>
          {onVerifyCitation && content.law ? (
            <button type="button" data-testid="lawbook-ctx-verify" className="block w-full px-3 py-1.5 text-left text-ui-sm hover:bg-selected"
              onClick={() => { onVerifyCitation(`《${content.law?.name ?? ""}》${menu.para.articleNo ?? ""}`); setCtxMenu(null); }}>
              核验此条
            </button>
          ) : null}
          <div className="my-1 border-t border-border" />
          <p className="px-3 py-0.5 text-ui-caption text-foreground-subtle">收藏夹：{foldersList.length ? "" : "（暂无，先新建）"}</p>
          {foldersList.slice(0, 6).map((f) => (
            <button key={f.id} type="button" className="block w-full truncate px-3 py-1 text-left text-ui-sm hover:bg-selected"
              onClick={() => { void favPara(f.id, menu.para); setCtxMenu(null); }}>· {f.name}</button>
          ))}
        </div>
      </div>
    );
  }

  function FolderPicker({ para }: { para: Para }) {
    const [name, setName] = useState("");
    return (
      <Dialog title="收藏到夹" onClose={() => setPickFolder(null)} testid="lawbook-folder-picker">
        <div className="flex flex-col gap-2 text-ui-sm">
          {fav.folders.map((f) => (
            <button key={f.id} type="button" data-testid="lawbook-picker-folder" className="rounded border border-border px-2 py-1.5 text-left hover:bg-selected"
              onClick={() => { void favPara(f.id, para); setPickFolder(null); }}>{f.name}</button>
          ))}
          {fav.folders.length === 0 ? <p className="text-foreground-subtle">还没有收藏夹，先新建一个：</p> : null}
          <div className="flex gap-1">
            <input className="min-w-0 flex-1 rounded border border-border bg-header px-2 py-1" placeholder="新收藏夹名称" value={name} onChange={(e) => setName(e.target.value)} data-testid="lawbook-picker-new-name" />
            <Button2 testid="lawbook-picker-new-go" onClick={async () => {
              try {
                const r = await api<{ id: string }>("/favorites/folders", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ action: "create", name }) });
                await favPara(r.id, para);
                setPickFolder(null);
              } catch (e) { flash(e instanceof Error ? e.message : "新建失败"); }
            }}>新建并收藏</Button2>
          </div>
        </div>
      </Dialog>
    );
  }

  function ShareCardView() {
    return (
      <Dialog title="分享卡" onClose={() => setShareCard(null)} testid="lawbook-share-card">
        <div className="flex flex-col gap-2">
          <p className="text-ui-base font-medium">{shareCard?.title}</p>
          <p className="whitespace-pre-wrap rounded border border-border p-2 text-ui-sm">{shareCard?.text}</p>
          <div className="flex justify-end gap-1">
            <Button2 onClick={() => void copyText(`${shareCard?.title ?? ""}\n\n${shareCard?.text ?? ""}`)}>复制全文</Button2>
          </div>
          <p className="text-ui-caption text-foreground-subtle">分享在本机内进行（材料不出域），复制后可粘贴到任意本机应用。</p>
        </div>
      </Dialog>
    );
  }

  function BookmarksView() {
    const folder = fav.folders.find((f) => f.id === bookmarkFolder) ?? null;
    const contents = folder ? fav.contents.filter((c) => c.folderId === folder.id) : [];
    const byLaw = new Map<string, typeof contents>();
    for (const c of contents) {
      const arr = byLaw.get(c.lawId) ?? [];
      arr.push(c);
      byLaw.set(c.lawId, arr);
    }
    return (
      <div className="grid grid-cols-[300px_1fr] gap-3" style={{ height: 620 }} data-testid="lawbook-bookmarks">
        <div className="flex min-h-0 flex-col rounded border border-border bg-background p-2">
          <div className="mb-2 flex items-center gap-1">
            <input className="min-w-0 flex-1 rounded border border-border bg-header px-2 py-1 text-ui-sm" placeholder="新收藏夹名称" value={newFolderName} onChange={(e) => setNewFolderName(e.target.value)} data-testid="lawbook-bm-new-name" />
            <Button2 testid="lawbook-bm-new-go" onClick={async () => {
              try { await api("/favorites/folders", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ action: "create", name: newFolderName }) }); setNewFolderName(""); void loadFav(); } catch (e) { flash(e instanceof Error ? e.message : "新建失败"); }
            }}>新建</Button2>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            {fav.folders.length === 0 ? <p className="py-6 text-center text-ui-caption text-foreground-subtle">暂无收藏夹</p> : null}
            {fav.folders.map((f) => {
              const n = fav.contents.filter((c) => c.folderId === f.id).length;
              return (
                <div key={f.id} draggable
                  onDragStart={(e) => e.dataTransfer.setData("text/lawbook-folder", f.id)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    const src = e.dataTransfer.getData("text/lawbook-folder");
                    if (!src || src === f.id) return;
                    const ids = fav.folders.map((x) => x.id);
                    const from = ids.indexOf(src);
                    const to = ids.indexOf(f.id);
                    const moved = ids.splice(from, 1)[0];
                    if (moved !== undefined) ids.splice(to, 0, moved);
                    void api("/favorites/folders", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ action: "reorder", orderedIds: ids }) }).then(loadFav).catch(() => flash("排序保存失败"));
                  }}>
                  <div className={`group flex items-center rounded px-1 hover:bg-selected ${bookmarkFolder === f.id ? "bg-selected" : ""}`}>
                    <button type="button" data-testid="lawbook-bm-folder" className="min-w-0 flex-1 truncate py-1 text-left text-ui-sm"
                      onClick={() => setBookmarkFolder(f.id)}>{f.name} <span className="text-foreground-subtle">({n})</span></button>
                    <button type="button" title="重命名" className="px-1 text-foreground-subtle opacity-0 group-hover:opacity-100" onClick={() => setRenamingFolder({ id: f.id, name: f.name })}>✎</button>
                    <button type="button" title="删除夹" data-testid={`lawbook-bm-folder-del-${f.name}`} className="px-1 text-foreground-subtle opacity-0 group-hover:opacity-100"
                      onClick={async () => {
                        const n2 = fav.contents.filter((c) => c.folderId === f.id).length;
                        const msg = n2 > 0 ? `该收藏夹内有 ${n2} 条收藏，删除后将一并移除，确定？` : "删除空收藏夹？"; // 自写文案；非空确认带条数（等量 D2 语义）
                        if (!window.confirm(msg)) return; // 非空确认带条数；删夹=级联连删（桥面已级联）
                        try { await api("/favorites/folders", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ action: "delete", folderId: f.id }) }); if (bookmarkFolder === f.id) setBookmarkFolder(null); void loadFav(); } catch (e) { flash(e instanceof Error ? e.message : "删除失败"); }
                      }}>×</button>
                  </div>
                </div>
              );
            })}
            <p className="mt-2 text-ui-caption text-foreground-subtle">拖动夹名可排序。</p>
          </div>
        </div>
        <div className="min-h-0 overflow-auto rounded border border-border bg-background p-3">
          {!folder ? (
            <div className="flex h-full items-center justify-center text-ui-sm text-foreground-subtle" data-testid="lawbook-bm-empty">
              {fav.folders.length ? "选择左侧收藏夹查看内容" : "还没有收藏；在正文中右键段落即可收藏"}
            </div>
          ) : contents.length === 0 ? (
            <div className="flex h-full items-center justify-center text-ui-sm text-foreground-subtle" data-testid="lawbook-bm-folder-empty">此夹暂无收藏段落</div>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-2">
                <h3 className="text-ui-base font-medium">{folder.name}</h3>
                <span className="text-ui-caption text-foreground-subtle">{contents.length} 条</span>
                <div className="ml-auto flex gap-1">
                  <Button2 onClick={() => setEditingBookmarks(!editingBookmarks)}>{editingBookmarks ? "退出编辑" : "编辑模式"}</Button2>
                  <Button2 onClick={() => void copyText(contents.map((c) => `${c.name}\n${c.text ?? "（原文缺失）"}`).join("\n\n"))}>整组复制</Button2>
                </div>
              </div>
              {editingBookmarks && fav.folders.length > 1 ? (
                <div className="flex items-center gap-1 text-ui-sm">
                  <span className="text-foreground-subtle">把选中 {pickedRows.size} 条移动到：</span>
                  {fav.folders.filter((f) => f.id !== folder.id).map((f) => (
                    <Button2 key={f.id} onClick={async () => {
                      if (!pickedRows.size) { flash("先勾选要移动的条目"); return; }
                      try { await api("/favorites/content/move", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ rowIds: [...pickedRows], folderId: f.id }) }); setPickedRows(new Set()); void loadFav(); flash("已移动"); } catch (e) { flash(e instanceof Error ? e.message : "移动失败"); }
                    }}>{f.name}</Button2>
                  ))}
                </div>
              ) : null}
              {[...byLaw.entries()].map(([lawId, arr]) => arr.length === 0 ? null : (
                <div key={lawId} data-testid="lawbook-bm-law-group">
                  <p className="mb-1 border-b border-border pb-1 font-medium">
                    {arr[0]!.name}
                    {arr[0]!.effect === "repealed" ? <span className="ml-2 text-foreground-subtle">⚠ 已废止</span> : null}
                    {arr[0]!.effect === "not_yet" ? <span className="ml-2 text-amber-500">⚠ 暂未施行</span> : null}
                  </p>
                  {arr.map((c) => (
                    <div key={c.rowId} className="group flex items-start gap-2 py-1 text-ui-sm" data-testid="lawbook-bm-item">
                      {editingBookmarks ? (
                        <input type="checkbox" className="mt-1" checked={pickedRows.has(c.rowId)}
                          onChange={(e) => setPickedRows((s) => { const n2 = new Set(s); e.target.checked ? n2.add(c.rowId) : n2.delete(c.rowId); return n2; })} />
                      ) : null}
                      <p className="min-w-0 flex-1 whitespace-pre-wrap">{(c.text ?? "（原文缺失：该包内容不可读）").length > 160 ? `${(c.text ?? "").slice(0, 160)}…` : c.text ?? "（原文缺失）"}</p>
                      <button type="button" title="移除该条" className="px-1 text-foreground-subtle opacity-0 group-hover:opacity-100"
                        onClick={async () => { try { await api("/favorites/content/delete", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ rowId: c.rowId }) }); void loadFav(); } catch { flash("移除失败"); } }}>×</button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
        {renamingFolder ? (
          <Dialog title="重命名收藏夹" onClose={() => setRenamingFolder(null)}>
            <div className="flex gap-1">
              <input className="min-w-0 flex-1 rounded border border-border bg-header px-2 py-1 text-ui-sm" value={renamingFolder.name}
                onChange={(e) => setRenamingFolder({ ...renamingFolder, name: e.target.value })} data-testid="lawbook-bm-rename-input" />
              <Button2 onClick={async () => {
                try { await api("/favorites/folders", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ action: "rename", folderId: renamingFolder.id, name: renamingFolder.name }) }); setRenamingFolder(null); void loadFav(); } catch (e) { flash(e instanceof Error ? e.message : "重命名失败"); }
              }}>保存</Button2>
            </div>
          </Dialog>
        ) : null}
      </div>
    );
  }
}
