// 【步骤4·#26 LAN 团队同步】团队面板（RE-26-LAN 团队同步.md §3 UI 结构；行为锚点按 A/B/C/D/E/G 编号标注）。
// 形态等量、文案全自写（表达隔离：等量≠抄文案）；视觉自绘（角色徽章/新鲜度/日期条/皇冠头像）。
// 数据经桥 team* 十二命令（RPC 面）；可见权限过滤在后端 teamView 完成（B15），本面板只做编排与呈现。
// 有意减面（对拍 54）：详情页不渲染竞品遗留的空壳「更新状态」卡；竞品遗留 workflow_status 编辑路径不存在
// （本产品一开始就只有备注，D4/对拍 28）。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, Copy, Crown, Info, Loader2, RefreshCw, StickyNote, Undo2, Users,
} from "lucide-react";
import { useServices } from "../ui-kit.js";

// ── 桥 DTO 形状（与 team_sync_service 输出同构；secret/配对码已被桥剥除，F14）──
type TeamStatus = {
  configured: boolean;
  team?: { teamId: string; teamName: string; memberId: string; myName: string; role: "leader" | "member"; memberCount: number };
  pairingCode?: string | null;
  netRunning?: boolean;
  kickedFrom?: string;
};
type KeyDate = { date: string; label: string };
type TeamCase = {
  id: string; name: string; caseNo: string; court: string; cause: string; caseType: string;
  stage: string; filingDate: string; result: string; amountCents: number;
  keyDates: KeyDate[]; latestEvent: KeyDate | null; updatedAt: string;
  plaintiffs: string[]; defendants: string[]; thirdParties: string[];
  execTotalCents: number; execReceivedCents: number; execPendingCents: number; summary: string;
};
type TeamEdit = {
  id: string; editorId: string; editorName: string; targetMemberId: string;
  caseId: string; caseName: string; field: string; value: string;
  status: "pending" | "applied" | "rejected" | "reverted"; createdAt: string; appliedAt: string | null;
};
type TeamMember = {
  memberId: string; name: string; role: "leader" | "member";
  view: string[] | null; edit: string[]; isMe: boolean;
  snapshot: { seq: number; updatedAt: string; payload: { cases: TeamCase[] } } | null;
};
type TeamView = {
  configured: boolean;
  team?: { teamId: string; teamName: string; memberId: string; myName: string; role: "leader" | "member"; memberCount: number };
  members: TeamMember[];
  edits: TeamEdit[];
};
type DiscoverTeam = { teamId: string; teamName: string; online: number; leaderOnline: boolean };

type TeamSvc = {
  teamStatus?: () => Promise<TeamStatus>;
  teamCreate?: (p: { teamName: string; myName: string }) => Promise<TeamStatus>;
  teamDiscover?: () => Promise<{ teams: DiscoverTeam[] }>;
  teamJoin?: (p: { teamId: string; code: string; myName: string }) => Promise<TeamStatus>;
  teamLeave?: () => Promise<{ cleared: boolean }>;
  teamKick?: (p: { memberId: string }) => Promise<TeamStatus>;
  teamSetPermissions?: (p: { memberId: string; view: string[] | null; edit: string[] }) => Promise<TeamStatus>;
  teamRefreshCode?: () => Promise<{ pairingCode: string }>;
  teamSyncNow?: () => Promise<{ reached: number; snapshotsUpdated: number; failed: number; errors: string[] }>;
  teamView?: () => Promise<TeamView>;
  teamSubmitEdit?: (p: { targetMemberId: string; caseId: string; caseName: string; note: string }) => Promise<TeamEdit>;
  teamRevertEdit?: (p: { editId: string }) => Promise<TeamEdit>;
};

// ── 小工具（本地时区 YYYY-MM-DD；千分位金额；中文序）──
function todayStr(): string {
  const n = new Date();
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}-${String(n.getDate()).padStart(2, "0")}`;
}
function daysBetween(fromIso: string): number {
  const d = new Date(fromIso);
  if (Number.isNaN(d.getTime())) return -1;
  const a = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const n = new Date();
  const b = new Date(n.getFullYear(), n.getMonth(), n.getDate()).getTime();
  return Math.round((b - a) / 86400000);
}
function fmtAmount(cents: number): string {
  return "¥" + (cents / 100).toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}
function partiesOf(c: TeamCase): string | null {
  const p = (c.plaintiffs ?? []).filter(Boolean).join("、");
  const d = (c.defendants ?? []).filter(Boolean).join("、");
  if (!p && !d) return null;
  return `${p || "—"} 对 ${d || "—"}`;
}
function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
// ── 新鲜度三态（B7）──
function freshnessOf(member: TeamMember): { text: string; stale: boolean } {
  if (!member.snapshot) return { text: "尚未收到数据", stale: true };
  const days = daysBetween(member.snapshot.updatedAt);
  if (days === 0) return { text: "今天已同步", stale: false };
  if (days < 0) return { text: "尚未收到数据", stale: true };
  return { text: `上次同步 ${days} 天前`, stale: days >= 7 };
}
type ToastMsg = { text: string; level: "info" | "error" | "success" };

export function TeamPanel() {
  const { zcodeAgentService, settingService } = useServices() as unknown as {
    zcodeAgentService: unknown;
    settingService?: { get: () => Promise<unknown> };
  };
  const svc = zcodeAgentService as TeamSvc;
  const [status, setStatus] = useState<TeamStatus | null>(null);
  const [view, setView] = useState<TeamView | null>(null);
  const [loading, setLoading] = useState(true);          // G6 进页 loading 占位
  const [bootError, setBootError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastMsg | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const say = useCallback((text: string, level: ToastMsg["level"] = "info") => {
    setToast({ text, level });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4200);
  }, []);
  // 引导页表单态（A2/A4/A6/A9）
  const [createName, setCreateName] = useState("");
  const [createWho, setCreateWho] = useState("");
  const [creating, setCreating] = useState(false);
  const [discovering, setDiscovering] = useState(false);
  const [discovered, setDiscovered] = useState<DiscoverTeam[] | null>(null);
  const [pickedTeam, setPickedTeam] = useState<DiscoverTeam | null>(null);
  const [joinCode, setJoinCode] = useState("");
  const [joinWho, setJoinWho] = useState("");
  const [joining, setJoining] = useState(false);
  // 看板态（B2/B3/B4/详情/管理）
  const [sortBy, setSortBy] = useState<"member" | "latest">("member");
  const [manageOpen, setManageOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [sel, setSel] = useState<{ memberId: string; caseId: string } | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [editTarget, setEditTarget] = useState<{ memberId: string; c: TeamCase } | null>(null);
  const [permFor, setPermFor] = useState<string | null>(null);
  const [permViewAll, setPermViewAll] = useState(true);
  const [permView, setPermView] = useState<string[]>([]);
  const [permEdit, setPermEdit] = useState<string[]>([]);
  const [pairingShown, setPairingShown] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const me = status?.team ?? view?.team ?? null;
  const meId = me?.memberId ?? "";
  const isLeader = me?.role === "leader";

  const reload = useCallback(async () => {
    if (!svc.teamStatus || !svc.teamView) { setBootError("桥缺少团队通道（需重启桥进程加载团队模块）"); setLoading(false); return; }
    try {
      const st = await svc.teamStatus();
      if (st.kickedFrom) { // G8/F16：error toast 含团队名，本机已被桥自动清理
        say(`你已被移出「${st.kickedFrom}」，本机团队数据已清除`, "error");
        setStatus(st); setView(null); setSel(null); setLoading(false);
        return;
      }
      setStatus(st);
      if (st.configured) {
        const v = await svc.teamView();
        setView(v);
        if (sel) { // C11 打开的案件在同步后消失→自动回看板
          const m = v.members.find((x) => x.memberId === sel.memberId);
          if (!m?.snapshot?.payload.cases.some((c) => c.id === sel.caseId)) setSel(null);
        }
      } else setView(null);
      setBootError(null);
    } catch (e) {
      setBootError(String((e as Error)?.message ?? e)); // G5
    } finally { setLoading(false); }
  }, [svc, sel, say]);
  // A3 姓名预填：引导页姓名默认取产品称呼槽（localStorage juscite.board.displayName——案件看板
  // 问候行同源 CaseBoardPanel.tsx:649）；桥设置层称呼字段作次优源（现无该字段，接入后自动生效）。
  // 两源皆空=空串不预填可输入。
  useEffect(() => {
    let alive = true;
    let local = "";
    try { local = (window.localStorage.getItem("juscite.board.displayName") ?? "").trim(); } catch { /* 隐私模式=无源 */ }
    const apply = (v: string) => { if (alive && v) { setCreateWho(v); setJoinWho(v); } };
    settingService?.get?.()
      .then((raw) => {
        const s = (raw ?? {}) as { profile?: { displayName?: unknown }; userName?: unknown; displayName?: unknown };
        const fromSettings = [s.profile?.displayName, s.userName, s.displayName]
          .find((v) => typeof v === "string" && v.trim()) as string | undefined;
        apply((fromSettings ?? local).trim());
      })
      .catch(() => apply(local));
    return () => { alive = false; };
  }, [settingService]);
  useEffect(() => { void reload(); // eslint-disable-line react-hooks/exhaustive-deps
  }, []);

  const doCreate = useCallback(async () => {
    setCreating(true);
    try {
      await svc.teamCreate?.({ teamName: createName.trim(), myName: createWho.trim() });
      say("团队已创建：把配对码念给要加入的同事即可", "success"); // A5
      setPairingShown(false);
      await reload();
    } catch (e) { say(String((e as Error)?.message ?? e), "error"); } finally { setCreating(false); }
  }, [svc, createName, createWho, say, reload]);

  const doDiscover = useCallback(async () => {
    setDiscovering(true); setDiscovered(null); setPickedTeam(null);
    try {
      const r = await svc.teamDiscover?.();
      const teams = r?.teams ?? [];
      setDiscovered(teams);
      if (!teams.length) say("没有找到正在共享的团队：请确认团队长已打开应用，并与你在同一网络", "info"); // A7
    } catch (e) { say(String((e as Error)?.message ?? e), "error"); } finally { setDiscovering(false); }
  }, [svc, say]);

  const doJoin = useCallback(async () => {
    if (!pickedTeam) return;
    setJoining(true);
    try {
      await svc.teamJoin?.({ teamId: pickedTeam.teamId, code: joinCode, myName: joinWho.trim() });
      say(`已加入「${pickedTeam.teamName}」：正在拉取队友数据`, "success"); // A10
      await reload();
    } catch (e) { say(String((e as Error)?.message ?? e), "error"); } finally { setJoining(false); }
  }, [svc, pickedTeam, joinCode, joinWho, say, reload]);

  const doSyncNow = useCallback(async () => {
    setSyncing(true);
    try {
      const r = await svc.teamSyncNow?.();
      if (!r || (r.reached === 0 && r.failed === 0)) {
        say("这一轮没有同步到任何队友：对方需要开着应用并与你在同一网络", "info"); // B4
      } else if (r.failed > 0) {
        say(`同步完成：${r.reached} 位队友在场，${r.failed} 台失败`, "error"); // B4
      } else {
        say(`同步完成：${r.reached} 位队友在场，${r.snapshotsUpdated} 份快照有更新`, "success");
      }
      await reload();
    } catch (e) { say(String((e as Error)?.message ?? e), "error"); } finally { setSyncing(false); }
  }, [svc, say, reload]);

  const doLeave = useCallback(async () => {
    const ok = window.confirm(isLeader // E6 两套确认口径（文案自写）
      ? "确定解散团队？在场成员会立即退出并清除本机团队数据；不在线的成员会保留最后一次同步的数据，且团队即刻停止共享。"
      : "确定退出团队？本机的团队数据将被清除；你自己登记的案件不受影响，团队名单要等团队长将你移出后才会在其他成员端消失。");
    if (!ok) return;
    setLeaving(true);
    try {
      await svc.teamLeave?.();
      say(isLeader ? "团队已解散" : "已退出团队", "success");
      setSel(null); setDiscovered(null); setPickedTeam(null);
      await reload();
    } catch (e) { say(String((e as Error)?.message ?? e), "error"); } finally { setLeaving(false); }
  }, [svc, isLeader, say, reload]);

  const doKick = useCallback(async (member: TeamMember) => {
    if (!window.confirm(`确定将「${member.name}」移出团队？其应用下次同步时会自动退出并清除本机团队数据。`)) return; // E5
    try {
      await svc.teamKick?.({ memberId: member.memberId });
      say(`已移出「${member.name}」，正在同步通知其他成员`, "success");
      await reload();
    } catch (e) { say(String((e as Error)?.message ?? e), "error"); }
  }, [svc, say, reload]);

  const openPerm = useCallback((m: TeamMember) => { // E4
    setPermFor(m.memberId);
    setPermViewAll(m.view === null);
    setPermView(m.view === null ? [] : [...m.view]);
    setPermEdit([...m.edit]);
  }, []);
  const savePerm = useCallback(async () => {
    if (!permFor) return;
    try {
      await svc.teamSetPermissions?.({ memberId: permFor, view: permViewAll ? null : permView, edit: permEdit });
      say("权限已保存：随下一轮同步对对方生效", "success"); // E4
      setPermFor(null);
      await reload();
    } catch (e) { say(String((e as Error)?.message ?? e), "error"); }
  }, [svc, permFor, permViewAll, permView, permEdit, say, reload]);

  const doRefreshCode = useCallback(async () => { // E1
    try {
      const r = await svc.teamRefreshCode?.();
      setPairingShown(true);
      if (r?.pairingCode) setStatus((s) => (s ? { ...s, pairingCode: r.pairingCode } : s));
      say("已换新配对码，旧配对码立即作废", "success");
    } catch (e) { say(String((e as Error)?.message ?? e), "error"); }
  }, [svc, say]);

  const copyCode = useCallback(async () => {
    const code = status?.pairingCode ?? "";
    if (!code) return;
    try { await navigator.clipboard.writeText(code); say("配对码已复制", "success"); }
    catch { say("复制失败：请手动记下配对码", "error"); }
  }, [status, say]);

  const submitNote = useCallback(async (targetMemberId: string, c: TeamCase, note: string, selfCase: boolean) => {
    const text = note.trim();
    if (!text) { say("备注内容不能为空", "error"); return; }
    if (text.length > 200) { say("备注最多 200 字", "error"); return; } // D2/C4 UI 上限 200（桥侧 500 双限制，对拍 27）
    try {
      await svc.teamSubmitEdit?.({ targetMemberId, caseId: c.id, caseName: c.name, note: text });
      say(selfCase ? "备注已记录（自己的案件立即生效）" : "备注已提交，待对方同步后生效", "success");
      setNoteDraft(""); setEditTarget(null);
      await reload();
    } catch (e) { say(String((e as Error)?.message ?? e), "error"); }
  }, [svc, say, reload]);

  const doRevert = useCallback(async (editId: string, isLegacyStatusEdit: boolean) => {
    const ok = window.confirm(isLegacyStatusEdit // D11 两套文案（本产品无遗留状态路径，恒走备注文案）
      ? "撤销这条状态改动？（历史遗留的状态编辑入口）"
      : "撤销这条备注？撤销后对方的看板不再显示它，也不会改动你案件的本机数据。");
    if (!ok) return;
    try {
      await svc.teamRevertEdit?.({ editId });
      say("已撤销", "success");
      await reload();
    } catch (e) { say(String((e as Error)?.message ?? e), "error"); }
  }, [svc, say, reload]);

  // ── 派生数据 ──
  const today = useMemo(() => todayStr(), []);
  const dateBar = useMemo(() => { // B5：今天及以后（含当日）升序前 8
    const items: Array<{ date: string; label: string; caseName: string; memberName: string }> = [];
    for (const m of view?.members ?? []) {
      for (const c of m.snapshot?.payload.cases ?? []) {
        for (const k of c.keyDates ?? []) {
          if (k.date >= today) items.push({ date: k.date, label: k.label, caseName: c.name, memberName: m.name });
        }
      }
    }
    items.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
    return items.slice(0, 8);
  }, [view, today]);
  const daysUntil = (date: string) => {
    const a = new Date(date + "T00:00:00").getTime();
    const n = new Date(today + "T00:00:00").getTime();
    return Math.round((a - n) / 86400000);
  };
  const canEditOf = useCallback((m: TeamMember): boolean => {
    if (!meId) return false;
    if (isLeader) return true;  // 团队长恒可编辑
    // 观察者视角（E4）：我在名单里的条目.edit 含对方 → 我可给对方案件留言
    return (view?.members.find((x) => x.memberId === meId)?.edit ?? []).includes(m.memberId);
  }, [meId, isLeader, view]);
  const memberGroups = useMemo(() => { // B6：团队长置顶、余按姓名中文序
    const ms = [...(view?.members ?? [])];
    ms.sort((a, b) => {
      if (a.role !== b.role) return a.role === "leader" ? -1 : 1;
      return a.name.localeCompare(b.name, "zh-Hans-CN");
    });
    return ms;
  }, [view]);
  const flatCases = useMemo(() => { // B12：latest_event 新→旧、无进展沉底、同日期案件名中文序
    const out: Array<{ m: TeamMember; c: TeamCase }> = [];
    for (const m of view?.members ?? []) {
      for (const c of m.snapshot?.payload.cases ?? []) out.push({ m, c });
    }
    out.sort((a, b) => {
      const da = a.c.latestEvent?.date ?? "";
      const db = b.c.latestEvent?.date ?? "";
      if (!da && !db) return a.c.name.localeCompare(b.c.name, "zh-Hans-CN");
      if (!da) return 1;
      if (!db) return -1;
      if (da !== db) return da > db ? -1 : 1;
      return a.c.name.localeCompare(b.c.name, "zh-Hans-CN");
    });
    return out;
  }, [view]);
  const boardEmpty = (view?.members ?? []).every((m) => !(m.snapshot?.payload.cases ?? []).length);
  const myChanges = useMemo(() => { // D11：target=我 且 applied/rejected/reverted 前 20
    if (!view) return [];
    return view.edits.filter((e) => e.targetMemberId === meId && ["applied", "rejected", "reverted"].includes(e.status)).slice(0, 20);
  }, [view, meId]);
  const selDetail = useMemo(() => {
    if (!sel || !view) return null;
    const m = view.members.find((x) => x.memberId === sel.memberId);
    const c = m?.snapshot?.payload.cases.find((x) => x.id === sel.caseId);
    return m && c ? { m, c } : null;
  }, [sel, view]);
  const notesOf = (memberId: string, caseId: string): TeamEdit[] => // B10 最新 2 条已生效
    (view?.edits ?? []).filter((e) => e.targetMemberId === memberId && e.caseId === caseId && e.status === "applied")
      .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1)).slice(0, 2);
  const pendingCountOf = (memberId: string, caseId: string): number => // B11
    (view?.edits ?? []).filter((e) => e.targetMemberId === memberId && e.caseId === caseId && e.status === "pending").length;

  if (loading) { // G6
    return (
      <div className="flex items-center gap-2 p-8 text-ui-sm text-foreground-subtle" data-testid="team-loading">
        <Loader2 className="size-4 animate-spin" /> 团队数据加载中…
      </div>
    );
  }

  // ── 引导页（A2-A11）──
  if (!status?.configured) {
    const canCreate = createName.trim() !== "" && createWho.trim() !== ""; // A4
    const canJoin = pickedTeam !== null && pickedTeam.leaderOnline && joinCode.length === 6 && joinWho.trim() !== ""; // A9
    return (
      <div className="flex flex-col gap-6" data-testid="team-panel-guide">
        <header className="flex flex-col items-center gap-2 pt-6 text-center">
          <Users className="size-10 text-foreground-subtle" />
          <h1 className="text-ui-xl font-semibold">团队协作</h1>
          <p className="max-w-xl text-ui-sm text-foreground-subtle">
            与同事在局域网内接力同步案件登记信息——不需要服务器，数据只在团队成员的应用之间直接交换，文档原文不出本机。
          </p>
        </header>
        {bootError ? <p className="text-ui-sm text-red-500">读取团队状态失败：{bootError}</p> : null}
        <div className="mx-auto grid w-full max-w-3xl gap-4 md:grid-cols-2">
          <section className="rounded-workspace-panel border border-border bg-header p-4" data-testid="team-guide-create">
            <h2 className="mb-1 text-ui-base font-medium">创建团队</h2>
            <p className="mb-3 text-ui-caption text-foreground-subtle">我是团队长：建一个团队，把配对码分给同事。</p>
            <label className="mb-1 block text-ui-caption">团队名称</label>
            <input value={createName} onChange={(e) => setCreateName(e.target.value)} maxLength={40}
              placeholder="例如：某某律师事务所民事组"
              className="mb-3 w-full rounded border border-border bg-background px-2 py-1.5 text-ui-sm" />
            <label className="mb-1 block text-ui-caption">你的姓名</label>
            <input value={createWho} onChange={(e) => setCreateWho(e.target.value)} maxLength={20}
              placeholder="在看板中向队友展示的名字"
              className="mb-3 w-full rounded border border-border bg-background px-2 py-1.5 text-ui-sm" />
            <button type="button" disabled={!canCreate || creating} onClick={() => void doCreate()}
              data-testid="team-create-btn"
              className="flex w-full items-center justify-center gap-2 rounded bg-selected px-3 py-1.5 text-ui-sm disabled:cursor-not-allowed disabled:opacity-50">
              {creating ? <Loader2 className="size-4 animate-spin" /> : null}
              创建团队（我是团队长）
            </button>
          </section>
          <section className="rounded-workspace-panel border border-border bg-header p-4" data-testid="team-guide-join">
            <h2 className="mb-1 text-ui-base font-medium">加入团队</h2>
            <p className="mb-3 text-ui-caption text-foreground-subtle">搜索同一局域网内正在共享的团队。</p>
            <button type="button" onClick={() => void doDiscover()} disabled={discovering}
              data-testid="team-discover-btn"
              className="mb-3 flex w-full items-center justify-center gap-2 rounded border border-border px-3 py-1.5 text-ui-sm disabled:opacity-60">
              {discovering ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
              {discovering ? "正在搜索同一局域网内的团队…" : "搜索局域网内的团队"}
            </button>
            {discovered && discovered.length > 0 ? (
              <ul className="mb-3 flex flex-col gap-1" data-testid="team-discover-list">
                {discovered.map((t) => (
                  <li key={t.teamId}>
                    <button type="button" onClick={() => { setPickedTeam(t); setJoinCode(""); }}
                      className={`w-full rounded border px-2 py-1.5 text-left text-ui-sm ${pickedTeam?.teamId === t.teamId ? "border-selected bg-selected" : "border-border"}`}>
                      <span className="font-medium">{t.teamName}</span>
                      <span className="ml-2 text-ui-caption text-foreground-subtle">{t.online} 人在线</span>
                      {!t.leaderOnline ? <span className="ml-2 text-ui-caption text-amber-500">团队长不在线，暂不能加入</span> : null}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            {pickedTeam ? (
              <div className="mb-3">
                <label className="mb-1 block text-ui-caption">配对码（向团队长索取，6 位数字）</label>
                <input value={joinCode} onChange={(e) => setJoinCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  maxLength={6} placeholder="6 位配对码" data-testid="team-join-code"
                  className="mb-2 w-full rounded border border-border bg-background px-2 py-1.5 font-mono tracking-widest text-ui-sm" />
                <label className="mb-1 block text-ui-caption">你的姓名</label>
                <input value={joinWho} onChange={(e) => setJoinWho(e.target.value)} maxLength={20}
                  placeholder="在看板中向队友展示的名字"
                  className="w-full rounded border border-border bg-background px-2 py-1.5 text-ui-sm" />
              </div>
            ) : null}
            <button type="button" disabled={!canJoin || joining} onClick={() => void doJoin()} data-testid="team-join-btn"
              className="flex w-full items-center justify-center gap-2 rounded bg-selected px-3 py-1.5 text-ui-sm disabled:cursor-not-allowed disabled:opacity-50">
              {joining ? <Loader2 className="size-4 animate-spin" /> : null}
              加入「{pickedTeam?.teamName ?? "…"}」
            </button>
            <p className="mt-3 text-ui-caption text-foreground-subtle">
              配对码由团队长提供，成功加入一位成员后立即失效；下一位成员需要团队长提供新配对码。 {/* E2 */}
            </p>
          </section>
        </div>
        <p className="mx-auto max-w-3xl text-center text-ui-caption text-foreground-subtle">
          Windows 提示：如果搜索不到团队，请在防火墙中允许本应用通过「专用网络」通信。 {/* A11/对拍 13 */}
        </p>
      </div>
    );
  }

  const detail = selDetail;
  return (
    <div className="flex flex-col gap-4" data-testid="team-panel-board">
      {/* B1 顶栏 */}
      <header className="flex flex-wrap items-center gap-3">
        <Users className="size-6" />
        <div className="flex items-center gap-2">
          <h1 className="text-ui-xl font-semibold" data-testid="team-board-name">{me?.teamName}</h1>
          <span className="text-ui-caption text-foreground-subtle">{view?.members.length ?? 0} 名成员</span>
          <span className={`rounded px-1.5 py-px text-ui-caption ${isLeader ? "bg-amber-500/20 text-amber-500" : "bg-blue-500/20 text-blue-400"}`}
            data-testid="team-role-badge">
            {isLeader ? "团队长" : "成员"}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <div className="flex overflow-hidden rounded border border-border" role="group" aria-label="看板排序">
            <button type="button" onClick={() => setSortBy("member")} data-testid="team-sort-member"
              className={`px-2 py-1 text-ui-caption ${sortBy === "member" ? "bg-selected" : ""}`}>按成员</button>
            <button type="button" onClick={() => setSortBy("latest")} data-testid="team-sort-latest"
              className={`px-2 py-1 text-ui-caption ${sortBy === "latest" ? "bg-selected" : ""}`}>按最新进展</button>
          </div>
          <button type="button" onClick={() => void doSyncNow()} disabled={syncing} data-testid="team-sync-btn"
            className="flex items-center gap-1.5 rounded border border-border px-2.5 py-1 text-ui-sm disabled:opacity-60">
            {syncing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
            {syncing ? "正在同步…" : "立即同步"}
          </button>
          <button type="button" onClick={() => setManageOpen((v) => !v)} data-testid="team-manage-toggle"
            aria-expanded={manageOpen}
            className={`rounded border border-border px-2.5 py-1 text-ui-sm ${manageOpen ? "bg-selected" : ""}`}>
            管理
          </button>
        </div>
      </header>
      {bootError ? <p className="text-ui-sm text-red-500">读取团队数据失败：{bootError}</p> : null}

      {dateBar.length > 0 ? ( // B5
        <section className="rounded-workspace-panel border border-border bg-header px-3 py-2" data-testid="team-date-bar">
          <p className="mb-1.5 text-ui-caption text-foreground-subtle">近期关键日期（全队，今天起）</p>
          <ol className="flex flex-wrap gap-x-4 gap-y-1">
            {dateBar.map((it, i) => {
              const left = daysUntil(it.date);
              const warn = left <= 30;
              return (
                <li key={i} className={`text-ui-caption ${warn ? "text-red-500" : ""}`} title={`${it.caseName}（${it.memberName}）`}>
                  {it.date} · {it.label}
                  {left >= 0 ? <span className="ml-1 opacity-80">{left === 0 ? "（今天）" : `（剩 ${left} 天）`}</span> : null}
                </li>
              );
            })}
          </ol>
        </section>
      ) : null}

      {boardEmpty ? ( // B13
        <div className="rounded-workspace-panel border border-dashed border-border p-8 text-center text-ui-sm text-foreground-subtle"
          data-testid="team-board-empty">
          看板还是空的——等队友完成一轮同步后再来看看。
        </div>
      ) : sortBy === "member" ? (
        <div className="flex flex-col gap-4">
          {memberGroups.map((m) => {
            const fresh = freshnessOf(m);
            const cases = m.snapshot?.payload.cases ?? [];
            return (
              <section key={m.memberId}
                className={`rounded-workspace-panel border border-border p-3 ${fresh.stale ? "opacity-60" : ""}`}
                data-testid={`team-member-group-${m.isMe ? "me" : m.memberId.slice(0, 8)}`}>
                <div className="mb-2 flex items-center gap-2">
                  <span className="flex size-7 items-center justify-center rounded-full bg-selected text-ui-sm font-medium">
                    {(m.name || "?").slice(0, 1)}
                  </span>
                  <span className="text-ui-base font-medium">{m.name}{m.isMe ? "（我）" : ""}</span>
                  {m.role === "leader" ? <Crown className="size-4 text-amber-500" aria-label="团队长" /> : null}
                  <span className="text-ui-caption text-foreground-subtle" data-testid="team-freshness">
                    {cases.length} 个案件 · {fresh.text}
                  </span> {/* B6/B7 */}
                </div>
                {cases.length === 0 ? ( // B8
                  <div className="rounded border border-dashed border-border p-4 text-center text-ui-caption text-foreground-subtle">
                    {m.isMe ? "你还没有登记案件：到「法律工作台」的看板建档后，同步一轮即可共享给队友。" : "该成员还没有同步过案件。"}
                  </div>
                ) : (
                  <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                    {cases.map((c) => (
                      <CaseCard key={c.id} c={c} m={m} meId={meId} today={today}
                        notes={notesOf(m.memberId, c.id)} pendingCount={pendingCountOf(m.memberId, c.id)}
                        canEdit={canEditOf(m) && !m.isMe} showOwner={false}
                        onOpen={() => setSel({ memberId: m.memberId, caseId: c.id })}
                        onEdit={() => setEditTarget({ memberId: m.memberId, c })} />
                    ))}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      ) : (
        <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3" data-testid="team-flat-grid"> {/* B12 */}
          {flatCases.map(({ m, c }) => (
            <CaseCard key={m.memberId + "/" + c.id} c={c} m={m} meId={meId} today={today}
              notes={notesOf(m.memberId, c.id)} pendingCount={pendingCountOf(m.memberId, c.id)}
              canEdit={canEditOf(m) && !m.isMe} showOwner
              onOpen={() => setSel({ memberId: m.memberId, caseId: c.id })}
              onEdit={() => setEditTarget({ memberId: m.memberId, c })} />
          ))}
        </div>
      )}
      <p className="text-ui-caption text-foreground-subtle"> {/* B14 */}
        看板数据来自队友应用之间的局域网接力同步，只包含案件登记信息，不含文档原文。
      </p>

      {/* D2 卡上编辑面板 */}
      {editTarget ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setEditTarget(null)}>
          <div className="w-full max-w-md rounded-workspace-panel border border-border bg-background p-4"
            onClick={(e) => e.stopPropagation()} data-testid="team-edit-dialog">
            <h3 className="mb-1 text-ui-base font-medium">给「{editTarget.c.name}」留言</h3>
            <p className="mb-3 text-ui-caption text-foreground-subtle">
              留言以备注形式随同步送达所有者，对方应用后在其看板显示；不会改动对方的案件数据。
            </p>
            <textarea value={noteDraft} onChange={(e) => setNoteDraft(e.target.value)} maxLength={200} rows={3}
              placeholder="最多 200 字，例如：明天上午开庭，请提前准备证据原件。"
              className="mb-3 w-full rounded border border-border bg-header px-2 py-1.5 text-ui-sm" data-testid="team-edit-note" />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEditTarget(null)} className="rounded border border-border px-3 py-1 text-ui-sm">取消</button>
              <button type="button" onClick={() => void submitNote(editTarget.memberId, editTarget.c, noteDraft, false)}
                disabled={!noteDraft.trim()} data-testid="team-edit-submit"
                className="rounded bg-selected px-3 py-1 text-ui-sm disabled:opacity-50">提交备注</button>
            </div>
          </div>
        </div>
      ) : null}

      {/* 详情页（C 组） */}
      {detail ? (
        <CaseDetail m={detail.m} c={detail.c} meId={meId} isLeader={!!isLeader} canEdit={canEditOf(detail.m)}
          view={view} today={today}
          notes={(view?.edits ?? []).filter((e) => e.targetMemberId === detail.m.memberId
            && e.caseId === detail.c.id && e.status === "applied")
            .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))}
          myPending={(view?.edits ?? []).filter((e) => e.targetMemberId === detail.m.memberId
            && e.caseId === detail.c.id && e.editorId === meId && e.status === "pending")}
          onBack={() => setSel(null)}
          onRevert={(id) => void doRevert(id, false)}
          onSubmitNote={(text) => void submitNote(detail.m.memberId, detail.c, text, detail.m.isMe)} />
      ) : null}

      {/* E 组 管理区 */}
      {manageOpen && view ? (
        <section className="rounded-workspace-panel border border-border bg-header p-4" data-testid="team-manage">
          <h2 className="mb-3 text-ui-base font-medium">管理</h2>
          <div className="grid gap-4 md:grid-cols-2">
            {isLeader ? ( // E1/E2
              <div className="rounded border border-border p-3" data-testid="team-pairing">
                <p className="mb-1 text-ui-caption text-foreground-subtle">配对码（一次性，入队一位即失效）</p>
                {pairingShown && status?.pairingCode ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-ui-xl tracking-[0.5em]" data-testid="team-pairing-code">{status.pairingCode}</span>
                    <button type="button" onClick={() => void copyCode()}
                      className="flex items-center gap-1 rounded border border-border px-2 py-0.5 text-ui-caption">
                      <Copy className="size-3.5" /> 复制
                    </button>
                    <button type="button" onClick={() => void doRefreshCode()} data-testid="team-pairing-rotate"
                      className="flex items-center gap-1 rounded border border-border px-2 py-0.5 text-ui-caption">
                      <RefreshCw className="size-3.5" /> 换新码（旧码立即作废）
                    </button>
                  </div>
                ) : (
                  <button type="button" onClick={() => void doRefreshCode()} data-testid="team-pairing-refresh"
                    className="rounded border border-border px-2.5 py-1 text-ui-sm">
                    {status?.pairingCode ? "显示配对码" : "生成配对码"}
                  </button>
                )}
                <p className="mt-2 text-ui-caption text-foreground-subtle">新成员加入需要当面或另约渠道念码，配对码不长期有效。</p>
              </div>
            ) : null}
            <div className="rounded border border-border p-3" data-testid="team-members"> {/* E3/E8 */}
              <p className="mb-2 text-ui-caption text-foreground-subtle">成员（{view.members.length}）</p>
              <ul className="flex flex-col gap-1.5">
                {memberGroups.map((m) => {
                  const permText = m.view === null ? "可见全队" : `可见 ${m.view.length} 人`;
                  const editText = isLeader ? ` · 可编辑 ${m.edit.length} 人` : "";
                  return (
                    <li key={m.memberId} className="flex flex-wrap items-center gap-2 text-ui-sm">
                      <span className="flex size-6 items-center justify-center rounded-full bg-selected text-ui-caption">{(m.name || "?").slice(0, 1)}</span>
                      <span>{m.name}{m.isMe ? "（我）" : ""}</span>
                      {m.role === "leader" ? <Crown className="size-3.5 text-amber-500" /> : null}
                      <span className="text-ui-caption text-foreground-subtle">{permText}{editText}</span>
                      {isLeader && !m.isMe ? (
                        <span className="ml-auto flex gap-1">
                          <button type="button" onClick={() => openPerm(m)} data-testid={`team-perm-${m.memberId.slice(0, 8)}`}
                            className="rounded border border-border px-2 py-0.5 text-ui-caption">权限</button>
                          <button type="button" onClick={() => void doKick(m)} data-testid={`team-kick-${m.memberId.slice(0, 8)}`}
                            className="rounded border border-border px-2 py-0.5 text-ui-caption text-red-500">移出</button>
                        </span>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              <button type="button" onClick={() => void doLeave()} disabled={leaving} data-testid="team-leave-btn"
                className="mt-3 rounded border border-border px-2.5 py-1 text-ui-sm text-red-500 disabled:opacity-60">
                {isLeader ? "解散团队" : "退出团队"} {/* E6/E8 */}
              </button>
            </div>

            {/* D11 队友对我案件的改动 */}
            <div className="rounded border border-border p-3 md:col-span-2" data-testid="team-my-changes">
              <p className="mb-2 text-ui-caption text-foreground-subtle">队友对我案件的改动（最近 20 条）</p>
              {myChanges.length === 0 ? (
                <p className="text-ui-caption text-foreground-subtle">还没有队友给你留过言。</p>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {myChanges.map((e) => (
                    <li key={e.id} className="flex flex-wrap items-center gap-2 text-ui-sm">
                      <StickyNote className="size-3.5 text-foreground-subtle" />
                      <span className="text-ui-caption text-foreground-subtle">{fmtDateTime(e.createdAt)}</span>
                      <span>{e.editorName} → {e.caseName || "（案件已不存在）"}</span>
                      <span className="text-foreground-subtle">{e.value}</span>
                      {e.status === "rejected" ? (
                        <span className="rounded bg-red-500/15 px-1.5 py-px text-ui-caption text-red-500"
                          title="对方无权限，或该案件已不存在">
                          未通过
                        </span>
                      ) : null}
                      {e.status === "applied" ? (
                        <button type="button" onClick={() => void doRevert(e.id, e.field !== "note")}
                          data-testid={`team-revert-${e.id}`}
                          className="ml-auto flex items-center gap-1 rounded border border-border px-2 py-0.5 text-ui-caption">
                          <Undo2 className="size-3.5" /> 撤销
                        </button>
                      ) : null}
                      {e.status === "reverted" ? <span className="text-ui-caption text-foreground-subtle">已撤销</span> : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </section>
      ) : null}

      {/* E4 逐人权限编辑 */}
      {permFor && view ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setPermFor(null)}>
          <div className="w-full max-w-md rounded-workspace-panel border border-border bg-background p-4"
            onClick={(e) => e.stopPropagation()} data-testid="team-perm-dialog">
            {(() => {
              const target = view.members.find((m) => m.memberId === permFor);
              if (!target) return null;
              return (
                <>
                  <h3 className="mb-1 text-ui-base font-medium">「{target.name}」的权限</h3>
                  <p className="mb-3 text-ui-caption text-foreground-subtle">保存后随下一轮同步生效。</p>
                  <fieldset className="mb-3">
                    <legend className="mb-1 text-ui-caption">可见范围</legend>
                    <label className="mr-4 text-ui-sm">
                      <input type="radio" checked={permViewAll} onChange={() => setPermViewAll(true)} /> 全队可见
                    </label>
                    <label className="text-ui-sm">
                      <input type="radio" checked={!permViewAll} onChange={() => {
                        setPermViewAll(false);
                        setPermView((v) => (v.length ? v : view.members.filter((x) => x.isMe).map((x) => x.memberId)));
                      }} /> 自定义…
                    </label>
                    {!permViewAll ? (
                      <ul className="mt-2 flex flex-col gap-1">
                        {view.members.map((x) => (
                          <li key={x.memberId} className="text-ui-sm">
                            <label>
                              <input type="checkbox" checked={permView.includes(x.memberId)} disabled={x.isMe}
                                onChange={(e) => setPermView((v) => e.target.checked ? [...v, x.memberId] : v.filter((i) => i !== x.memberId))} />
                              {" "}{x.name}{x.isMe ? "（自己恒可见）" : ""}
                            </label>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </fieldset>
                  <fieldset className="mb-3">
                    <legend className="mb-1 text-ui-caption">可编辑其案件的成员（须先可见；子集语义）</legend>
                    <ul className="flex flex-col gap-1">
                      {view.members.filter((x) => permViewAll || permView.includes(x.memberId) || x.isMe).map((x) => (
                        <li key={x.memberId} className="text-ui-sm">
                          <label>
                            <input type="checkbox" checked={permEdit.includes(x.memberId)} disabled={x.isMe}
                              onChange={(e) => setPermEdit((v) => e.target.checked ? [...v, x.memberId] : v.filter((i) => i !== x.memberId))} />
                            {" "}{x.name}{x.isMe ? "（自己的案件无需授权）" : ""}
                          </label>
                        </li>
                      ))}
                    </ul>
                  </fieldset>
                  <div className="flex justify-end gap-2">
                    <button type="button" onClick={() => setPermFor(null)} className="rounded border border-border px-3 py-1 text-ui-sm">取消</button>
                    <button type="button" onClick={() => void savePerm()} data-testid="team-perm-save"
                      className="rounded bg-selected px-3 py-1 text-ui-sm">保存</button>
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      ) : null}

      {/* toast（G5/G8/A7/A10/B4 出口） */}
      {toast ? (
        <div role="status" data-testid="team-toast"
          className={`fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded border px-3 py-2 text-ui-sm shadow-lg
          ${toast.level === "error" ? "border-red-500/40 bg-red-500/10 text-red-500" : toast.level === "success" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500" : "border-border bg-background"}`}>
          {toast.level === "info" ? <Info className="mr-1 inline size-3.5" /> : null}
          {toast.text}
        </div>
      ) : null}
    </div>
  );
}

// ── 案件卡（B9/B10/B11/D1）──
function CaseCard({ c, m, meId, today, notes, pendingCount, canEdit, showOwner, onOpen, onEdit }: {
  c: TeamCase; m: TeamMember; meId: string; today: string;
  notes: TeamEdit[]; pendingCount: number; canEdit: boolean; showOwner: boolean;
  onOpen: () => void; onEdit: () => void;
}) {
  const nextKey = (c.keyDates ?? []).find((k) => k.date >= today); // ⏰ 下一未来关键日期
  const openable = Boolean(c.id); // 无 id 的旧快照卡不可打开详情（D1 同因）
  return (
    <div className="flex flex-col gap-1.5 rounded border border-border bg-header p-2.5" data-testid="team-case-card">
      <div className="flex items-start gap-2">
        <button type="button" onClick={openable ? onOpen : undefined} disabled={!openable}
          title={openable ? undefined : "对方应用版本较旧，暂不能打开详情"}
          className={`text-left text-ui-sm font-medium ${openable ? "hover:underline" : "cursor-not-allowed opacity-70"}`}>
          {c.name}
        </button>
        {c.stage ? (
          <span className="ml-auto shrink-0 rounded bg-selected px-1.5 py-px text-ui-caption">{c.stage}</span> /* 阶段徽章 */
        ) : null}
      </div>
      {c.caseNo ? <p className="text-ui-caption text-foreground-subtle">{c.caseNo}</p> : null}
      {partiesOf(c) ? <p className="text-ui-caption text-foreground-subtle">{partiesOf(c)}</p> : null}
      {c.amountCents > 0 ? <p className="text-ui-caption">标的额 {fmtAmount(c.amountCents)}</p> : null} {/* >0 才显示 */}
      {c.latestEvent ? (
        <p className="text-ui-caption">最新进展：{c.latestEvent.date} {c.latestEvent.label}</p>
      ) : c.summary ? (
        <p className="line-clamp-2 text-ui-caption text-foreground-subtle">{c.summary}</p> /* 回退摘要两行截断 */
      ) : null}
      {nextKey ? <p className="text-ui-caption text-amber-500">⏰ {nextKey.date} {nextKey.label}</p> : null}
      {notes.map((n) => (
        <p key={n.id} className="rounded bg-amber-500/10 px-1.5 py-0.5 text-ui-caption text-amber-600 dark:text-amber-400">
          {n.editorName}：{n.value}
        </p> /* B10 amber 底 */
      ))}
      {pendingCount > 0 ? (
        <p className="text-ui-caption text-foreground-subtle">⏳ {pendingCount} 条留言待对方同步生效</p> /* B11 */
      ) : null}
      {canEdit ? (
        <button type="button" onClick={onEdit} disabled={!openable} title={openable ? "留言（备注）" : "对方应用版本较旧，暂不能留言"}
          data-testid={`team-card-edit-${c.id.slice(0, 8)}`}
          className="mt-auto self-start rounded border border-border px-2 py-0.5 text-ui-caption disabled:opacity-50">
          留言
        </button> /* D1 */
      ) : null}
      {m.isMe ? <span className="sr-only">自己的案件</span> : null}
      {showOwner ? ( // B12 平铺视图可见所有者徽章（含(我)）；按成员视图组头已示名，保持 sr-only
        <p className="text-ui-caption text-foreground-subtle" data-testid="team-case-owner">
          所有者：{m.name}{m.memberId === meId ? "（我）" : ""}
        </p>
      ) : (
        <span className="sr-only">所有者 {m.name}{m.memberId === meId ? "（我）" : ""}</span>
      )}
    </div>
  );
}

// ── 案件详情页（C1-C8/C10；C9 空壳卡有意不渲染=对拍 54 减面）──
function CaseDetail({ m, c, meId, isLeader, canEdit, view, today, notes, myPending, onBack, onRevert, onSubmitNote }: {
  m: TeamMember; c: TeamCase; meId: string; isLeader: boolean; canEdit: boolean; today: string;
  view: TeamView | null;
  notes: TeamEdit[]; myPending: TeamEdit[];
  onBack: () => void; onRevert: (editId: string) => void; onSubmitNote: (text: string) => void;
}) {
  const [note, setNote] = useState("");
  const fresh = freshnessOf(m);
  const updatedLocal = (() => { // per-case updatedAt（F17 最近动态数据源，快照投影列 updatedAt）
    const d = new Date(c.updatedAt);
    return Number.isNaN(d.getTime()) ? "" : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  })();
  const rows: Array<[string, string]> = ([
    ["案号", c.caseNo], ["受理法院", c.court], ["案由", c.cause], ["案件类型", c.caseType],
    ["立案日期", c.filingDate], ["标的额", c.amountCents > 0 ? fmtAmount(c.amountCents) : ""],
    ["处理结果", c.result],
    ["最近动态", updatedLocal ? `更新于 ${updatedLocal}` : ""], // 竞品 last_activity 等量（文案自写）
  ] as Array<[string, string]>).filter(([, v]) => Boolean(v)); // C5 空字段不渲染该行
  const parties = partiesOf(c);
  const timeline = [...(c.keyDates ?? [])].sort((a, b) => (a.date < b.date ? 1 : -1)); // C8 降序
  return (
    <section className="rounded-workspace-panel border border-border bg-header p-4" data-testid="team-case-detail">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button type="button" onClick={onBack} data-testid="team-detail-back"
          className="flex items-center gap-1 rounded border border-border px-2 py-0.5 text-ui-caption">
          <ArrowLeft className="size-3.5" /> 返回看板
        </button> {/* C1 */}
        <h2 className="text-ui-base font-semibold">{c.name}</h2>
        {c.stage ? <span className="rounded bg-selected px-1.5 py-px text-ui-caption">{c.stage}</span> : null}
        <span className="text-ui-caption text-foreground-subtle">
          所有者：{m.name}{m.isMe ? "（我）" : ""} · {fresh.text}
        </span>
        {canEdit && !m.isMe ? (
          <button type="button" onClick={() => onSubmitNote(note)} disabled={!note.trim()} data-testid="team-detail-note-submit"
            className="ml-auto rounded bg-selected px-2 py-0.5 text-ui-caption disabled:opacity-50">留言</button>
        ) : null}
        {m.isMe || isLeader || canEdit ? (
          <div className="ml-auto flex w-full max-w-sm gap-1">
            <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200}
              placeholder={m.isMe ? "给自己的案件记一笔（立即生效）" : "留言给所有者（随同步送达）"}
              onKeyDown={(e) => { if (e.key === "Enter" && note.trim()) onSubmitNote(note); }} // C4 Enter 可提交
              className="w-full rounded border border-border bg-background px-2 py-1 text-ui-sm" data-testid="team-detail-note" />
          </div>
        ) : null}
      </div>

      {/* C2 置顶备注栏 */}
      <div className="mb-3 rounded border border-border p-2.5" data-testid="team-detail-notes">
        <p className="mb-1.5 text-ui-caption text-foreground-subtle">备注（{notes.length}）</p>
        {notes.length === 0 ? <p className="text-ui-caption text-foreground-subtle">还没有备注。</p> : null}
        <ul className="flex flex-col gap-1">
          {notes.map((n) => (
            <li key={n.id} className="flex flex-wrap items-center gap-2 rounded bg-amber-500/10 px-1.5 py-0.5 text-ui-caption">
              <span className="text-amber-600 dark:text-amber-400">{n.editorName}：{n.value}</span>
              <span className="ml-auto text-foreground-subtle">{fmtDateTime(n.createdAt)}</span>
              {m.isMe ? (
                <button type="button" onClick={() => onRevert(n.id)}
                  className="rounded border border-border px-1.5 py-px" data-testid={`team-note-revert-${n.id}`}>
                  撤销
                </button> /* C2 所有者可逐条删除（确认在 doRevert） */
              ) : null}
            </li>
          ))}
        </ul>
        {myPending.length > 0 ? ( // C3 自己 pending 待生效行
          <ul className="mt-1 flex flex-col gap-1">
            {myPending.map((n) => (
              <li key={n.id} className="rounded border border-dashed border-border px-1.5 py-0.5 text-ui-caption text-foreground-subtle">
                {n.value}（待对方同步生效）
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {/* C5 基本信息 */}
      {rows.length > 0 ? (
        <dl className="mb-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-ui-sm" data-testid="team-detail-info">
          {rows.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-ui-caption text-foreground-subtle">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {c.summary ? <p className="mb-3 rounded border border-border p-2 text-ui-sm">{c.summary}</p> : null}

      {/* C6 当事人区 */}
      {(c.plaintiffs.length > 0 || c.defendants.length > 0 || c.thirdParties.length > 0 || parties) ? (
        <div className="mb-3 text-ui-sm" data-testid="team-detail-parties">
          {c.plaintiffs.length > 0 ? <p><span className="text-ui-caption text-foreground-subtle">原告：</span>{c.plaintiffs.join("、")}</p> : null}
          {c.defendants.length > 0 ? <p><span className="text-ui-caption text-foreground-subtle">被告：</span>{c.defendants.join("、")}</p> : null}
          {c.thirdParties.length > 0 ? <p><span className="text-ui-caption text-foreground-subtle">第三人：</span>{c.thirdParties.join("、")}</p> : null}
          {!c.plaintiffs.length && !c.defendants.length && !c.thirdParties.length && parties ? (
            <p><span className="text-ui-caption text-foreground-subtle">当事人：</span>{parties}</p>
          ) : null}
        </div>
      ) : null}

      {c.execTotalCents > 0 ? (
        <div className="mb-3 grid grid-cols-3 gap-2 rounded border border-border p-2 text-ui-sm" data-testid="team-detail-exec">
          <div><p className="text-ui-caption text-foreground-subtle">应执行</p><p>{fmtAmount(c.execTotalCents)}</p></div>
          <div><p className="text-ui-caption text-foreground-subtle">已到账</p><p>{fmtAmount(c.execReceivedCents)}</p></div>
          <div><p className="text-ui-caption text-foreground-subtle">未到账</p><p>{fmtAmount(c.execPendingCents)}</p></div>
        </div>
      ) : null}

      {timeline.length > 0 ? (
        <ol className="mb-3 flex flex-col gap-1" data-testid="team-detail-timeline">
          {timeline.map((k, i) => {
            const future = k.date >= today;
            const isLatest = c.latestEvent?.date === k.date && c.latestEvent?.label === k.label;
            return (
              <li key={i} className={`text-ui-sm ${future ? "text-amber-500" : ""}`}>
                {future ? "⏰ " : ""}{k.date} {k.label}
                {isLatest ? <span className="ml-2 rounded bg-selected px-1.5 py-px text-ui-caption">最新进展</span> : null}
              </li>
            );
          })}
        </ol>
      ) : null}
      <p className="text-ui-caption text-foreground-subtle">
        登记信息由所有者的应用自动同步；文档原文、报告与 AI 助手仅在所有者本机可用。
      </p>
    </section>
  );
}
