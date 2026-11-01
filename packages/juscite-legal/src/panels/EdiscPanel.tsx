// 【功能 #42 电子数据取证】取证面板（RE-42 §3.3 UI 五分区；桥面 /api/edisc/* 19 路由）。
// 源列表（A3 三状态徽章+源画像抽屉）/ 行浏览（B2/B3 表选择+行区间分页+搜索+选中归类 C1）/
// 归类看板（C2 按 category 分组→D1 清单生成）/ 页卡阅读（E4 页卡+块坐标；E3 矩形批注+按页分组）/
// 审查工作台（F 三档色标+预置标注+候选清单确认分权 D3+干跑元数据 G3+校验可读差异 D2+律师闸 F10+七节报告）。
// 文案全部自写（表达隔离）；本版页卡为文本层页卡（页图渲染未接线，坐标以块 bbox 呈现，如实展示）。
import { useCallback, useEffect, useMemo, useState } from "react";
import { FileSearch, FolderOpen, ShieldCheck, Table2 } from "lucide-react";
import { useServices } from "../ui-kit.js";
import {
  EDISC_ATTR_BADGE, EDISC_ATTR_CONCLUSIONS, EDISC_FACT_EXCLUSIONS, EDISC_FORMAL_ELEMENTS, EDISC_GAP_KINDS,
  EDISC_KIND_LABELS, EDISC_LEVEL_BADGE, EDISC_OCR_BADGE, EDISC_PARSE_BADGE, EDISC_SECTIONS,
  EDISC_TASK_STATUS_BADGE, EDISC_TRIPLE_ATTRIBUTES,
  canExportReviewReport, formatGapEntry, formatRowAddress, groupAnnotationsByPage, groupClassificationsByCategory,
  missingFormalElements, rowRefOf, summarizeTaskProgress, summarizeVerify,
  type EdiscAttrConclusion, type EdiscFlagLevel, type EdiscFormalElement, type EdiscGapKind, type EdiscOcrStatus,
  type EdiscParseStatus, type EdiscRowRef, type EdiscSectionKey, type EdiscSourceKind, type EdiscTaskStatus,
} from "../kernel/ediscUiModel.js";

interface SourceItem {
  id: string; kind: EdiscSourceKind; filename: string; fileHash: string; format: string; byteSize: number;
  pageCount: number | null; blockCount: number | null;
  tables: Array<{ name: string; rowCount: number }>;
  parseStatus: EdiscParseStatus; ocrStatus: EdiscOcrStatus;
  error: { code: string; message: string } | null;
  preprocess: Record<string, unknown>;
  registeredAt: string; registeredBy: string;
}
interface ProfileItem {
  id: string; kind: EdiscSourceKind; format: string; fileHash: string;
  tables: Array<{ name: string; rowCount: number }>;
  pages: number | null; blocks: number | null; coordSystem: string | null; chatMessages: number | null;
}
interface RowData { rowNo: number; cells: string[]; text: string; blockId: string | null }
interface SearchHit { sourceId: string; sourceFilename: string; tableName: string; rowNo: number; text: string; blockId: string | null; note?: string }
interface Classification { id: string; refs: EdiscRowRef[]; category: string; reason: string; createdBy: string; createdAt: string }
interface AnchorJson { kind: string; label: string; rows?: { tableName: string; rowStart: number; rowEnd: number }; digest?: string }
interface Candidate {
  id: string; category: string; title: string; purpose: string; anchors: AnchorJson[];
  suggestionLevel: string; status: "suggested" | "confirmed"; confirmedBy: string | null; confirmedAt: string | null;
  formal?: { elements: Record<string, string>; check: { complete: boolean; missing: string[]; note: string } } | null;
}
interface ReviewFlag {
  id: string; targetLabel: string; kind: EdiscSourceKind; level: EdiscFlagLevel; proofStrength: string;
  issues: string[]; supports: string[]; weakens: string[]; lawyerAction: string; tags: string[]; createdBy: string;
}
interface Annotation { id: string; sourceId: string; pageNumber: number; rects: number[][]; type: string; color: string; textContent: string; comment: string; createdBy: string }
interface PageCard { sourceId: string; page: number; fileHash: string; coordSystem: string; fullText: string; blocks: Array<{ seq: number; bbox: number[]; text: string; blockId: string }>; note: string }
interface VerifyResult { ok: boolean; checked: number; problems: Array<{ ref: string; issue: string }>; backjumpChecked: number; backjumpMismatched: number; candidates: number }
interface FactItem { id: string; text: string; note: string; createdBy: string; createdAt: string }
interface TripleReview { id: string; targetLabel: string; sourceId: string | null; findings: Array<{ attr: string; conclusion: string; reason: string }>; createdBy: string }
interface GapItem { id: string; kind: EdiscGapKind; factText: string; suggestion: string; sourceChannel: string; difficulty: string; deadlineNote: string; createdBy: string }
interface FormalState { elements: Partial<Record<EdiscFormalElement, string>>; check?: { complete: boolean; missing: string[]; note: string } }
interface TaskInfo {
  id: string; status: EdiscTaskStatus; checkpoint: number; pageCardsOnly: boolean; stopOnError: boolean;
  summary: { status: EdiscTaskStatus; total: number; done: number; failed: number; pending: number; checkpoint: number };
  items: Array<{ sourceId: string; label: string; state: string; attempts: number; error: string | null }>;
}
interface BoardCaseLite { id: string; name: string }

async function ediscApi<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { cache: "no-store", ...init });
  const d = await r.json().catch(() => null) as (T & { error?: { message?: string } }) | null;
  if (!r.ok || !d || d.error) throw new Error(d?.error?.message ?? `请求失败（${r.status}）`);
  return d;
}
async function fileBase64(f: File): Promise<string> {
  const bytes = new Uint8Array(await f.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

export function EdiscPanel() {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as { matterList?: () => Promise<{ cases: BoardCaseLite[] }> };
  const [cases, setCases] = useState<BoardCaseLite[]>([]);
  const [caseId, setCaseId] = useState<string>("");
  const [section, setSection] = useState<EdiscSectionKey>("sources");
  const [note, setNote] = useState("");
  const [errorNote, setErrorNote] = useState("");
  const run = useCallback(async (fn: () => Promise<string>) => {
    setErrorNote(""); setNote("");
    try { setNote(await fn()); } catch (e) { setErrorNote(e instanceof Error ? e.message : String(e)); }
  }, []);

  useEffect(() => {
    let alive = true;
    svc.matterList?.().catch(() => ({ cases: [] })).then((r: { cases: BoardCaseLite[] }) => {
      if (!alive) return;
      setCases(r.cases ?? []);
      setCaseId((cur) => cur || r.cases?.[0]?.id || "");
    });
    return () => { alive = false; };
  }, [svc]);

  // ═══ 源列表（A3/A2/A1/B1）═══
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [uploadKind, setUploadKind] = useState<EdiscSourceKind>("chat");
  const [scanPath, setScanPath] = useState("");
  const [profile, setProfile] = useState<ProfileItem | null>(null); // 源画像抽屉
  const refreshSources = useCallback(async (cid: string) => {
    if (!cid) { setSources([]); return; }
    try { setSources((await ediscApi<{ items: SourceItem[] }>(`/api/edisc/sources?caseId=${encodeURIComponent(cid)}`)).items); setErrorNote(""); }
    catch (e) { setErrorNote(e instanceof Error ? e.message : String(e)); }
  }, []);
  useEffect(() => { void refreshSources(caseId); setProfile(null); }, [caseId, refreshSources]);

  // ═══ 批量整理任务（G5 长任务生命周期：启动即返检查点/暂停/恢复/取消/失败件重跑）═══
  const [task, setTask] = useState<TaskInfo | null>(null);
  const [taskPageCardsOnly, setTaskPageCardsOnly] = useState(false);
  const [taskStopOnError, setTaskStopOnError] = useState(false);
  const refreshTask = useCallback(async (cid: string) => {
    if (!cid) { setTask(null); return; }
    try {
      const d = await ediscApi<{ items: TaskInfo[] }>(`/api/edisc/tasks?caseId=${encodeURIComponent(cid)}`);
      setTask(d.items?.[0] ?? null);
    } catch { /* 切案瞬态：统一 errorNote 呈现 */ }
  }, []);
  useEffect(() => { void refreshTask(caseId); }, [caseId, refreshTask]);
  useEffect(() => {
    if (task?.status !== "running") return;
    const t = setInterval(() => { void refreshTask(caseId); }, 1500);   // 运行中轮询检查点推进
    return () => clearInterval(t);
  }, [task?.status, caseId, refreshTask]);
  const taskCtl = (action: "start" | "pause" | "resume" | "cancel" | "recover-failed") => void run(async () => {
    if (action === "start") {
      const d = await ediscApi<TaskInfo>("/api/edisc/tasks", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ caseId, pageCardsOnly: taskPageCardsOnly, stopOnError: taskStopOnError }),
      });
      setTask(d);
      return `整理任务已后台启动（检查点 ${d.summary.checkpoint}/${d.summary.total}，可随时暂停/取消）`;
    }
    if (!task) throw new Error("还没有整理任务");
    const d = await ediscApi<TaskInfo>(`/api/edisc/tasks/${encodeURIComponent(task.id)}/${action}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: "{}",
    });
    setTask(d);
    return `任务${action === "pause" ? "已暂停（断点保留，可恢复续传）" : action === "resume" ? "已自检查点恢复" : action === "cancel" ? "已取消" : "失败件已重排回队重跑"}`;
  });

  // ═══ 行浏览（B2/B3/C1）═══
  const [rowSourceId, setRowSourceId] = useState("");
  const [rowTable, setRowTable] = useState("");
  const [rowStart, setRowStart] = useState(1);
  const [rowEnd, setRowEnd] = useState(50);
  const [rows, setRows] = useState<Array<RowData & { fileHash: string; sourceId: string; tableName: string }>>([]);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [picked, setPicked] = useState<number[]>([]);          // 选中行号
  const [category, setCategory] = useState("");
  const [reason, setReason] = useState("");
  const rowSource = sources.find((s) => s.id === rowSourceId);
  const readRows = () => void run(async () => {
    if (!rowSourceId) throw new Error("先选择一个已解析的源");
    const d = await ediscApi<{ rows: RowData[]; fileHash: string }>(`/api/edisc/sources/${encodeURIComponent(rowSourceId)}/rows?table=${encodeURIComponent(rowTable || "聊天记录")}&rowStart=${rowStart}&rowEnd=${rowEnd}`);
    setRows(d.rows.map((r) => ({ ...r, fileHash: d.fileHash, sourceId: rowSourceId, tableName: rowTable || "聊天记录" })));
    setPicked([]);
    return `已读 ${d.rows.length} 行（${formatRowAddress(rowRefOf(rowSourceId, rowTable || "聊天记录", rowStart))} 起）`;
  });
  const doSearch = () => void run(async () => {
    const q = query.trim();
    if (!q) { setHits(null); return "输入关键词后再检索"; }
    const d = await ediscApi<{ hits: SearchHit[]; note: string }>(`/api/edisc/search?caseId=${encodeURIComponent(caseId)}&q=${encodeURIComponent(q)}`);
    setHits(d.hits);
    return d.note;
  });
  const classify = () => void run(async () => {
    const cat = category.trim();
    if (!cat || !picked.length || !rowSource) throw new Error("选中行并填写类目后才能归类");
    const refs = picked.map((n) => rowRefOf(rowSource.id, rowTable || "聊天记录", n));
    const d = await ediscApi<{ id: string }>("/api/edisc/classifications", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ caseId, refs, category: cat, reason }),
    });
    setPicked([]); setCategory(""); setReason("");
    return `已归类（${d.id}）：覆盖层不写回原件`;
  });

  // ═══ 归类看板（C2/D1）═══
  const [classes, setClasses] = useState<Classification[]>([]);
  const refreshClasses = useCallback(async (cid: string) => {
    if (!cid) { setClasses([]); return; }
    try { setClasses((await ediscApi<{ items: Classification[] }>(`/api/edisc/classifications?caseId=${encodeURIComponent(cid)}`)).items); } catch { /* 案件切换瞬态：面板统一 errorNote 呈现 */ }
  }, []);
  const genFixList = (cat: string) => void run(async () => {
    const d = await ediscApi<{ created: unknown[]; suggestionNote: string }>("/api/edisc/fix-lists", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ caseId, category: cat }),
    });
    return `已生成 ${d.created.length} 个候选清单项。${d.suggestionNote}`;
  });
  useEffect(() => { void refreshClasses(caseId); }, [caseId, refreshClasses]);
  const boardGroups = useMemo(() => groupClassificationsByCategory(classes), [classes]);

  // ═══ 页卡阅读（E4/E3）═══
  const pdfSources = sources.filter((s) => s.format === ".pdf" && s.parseStatus === "done");
  const [pageSourceId, setPageSourceId] = useState("");
  const [pageNo, setPageNo] = useState(1);
  const [card, setCard] = useState<PageCard | null>(null);
  const [annots, setAnnots] = useState<Annotation[]>([]);
  const [annSeq, setAnnSeq] = useState<number | null>(null);      // 批注目标块
  const [annType, setAnnType] = useState("highlight");
  const [annColor, setAnnColor] = useState("#8c6d1f");
  const [annText, setAnnText] = useState("");
  const readPage = () => void run(async () => {
    const sid = pageSourceId || pdfSources[0]?.id;
    if (!sid) throw new Error("先登记并解析一个 PDF 源");
    const d = await ediscApi<PageCard>(`/api/edisc/sources/${encodeURIComponent(sid)}/pages?page=${pageNo}`);
    setCard(d); setAnnSeq(null);
    return d.note;
  });
  const refreshAnnots = useCallback(async (cid: string) => {
    if (!cid) { setAnnots([]); return; }
    try { setAnnots((await ediscApi<{ items: Annotation[] }>(`/api/edisc/annotations?caseId=${encodeURIComponent(cid)}`)).items); } catch { /* 同上：切案瞬态 */ }
  }, []);
  useEffect(() => { void refreshAnnots(caseId); }, [caseId, refreshAnnots]);
  const saveAnnotation = () => void run(async () => {
    if (!card) throw new Error("先读取页卡");
    const blk = card.blocks.find((b) => b.seq === annSeq);
    if (!blk) throw new Error("先在页卡中选中一个文本块作为批注落点");
    const d = await ediscApi<{ id: string }>("/api/edisc/annotations", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ caseId, sourceId: card.sourceId, pageNumber: card.page, rects: [blk.bbox], type: annType, color: annColor, textContent: annText }),
    });
    setAnnText("");
    await refreshAnnots(caseId);
    return `批注已保存（${d.id}）：挂页/坐标覆盖层，不篡改原件`;
  });
  const annotGroups = useMemo(() => groupAnnotationsByPage(annots), [annots]);

  // ═══ 审查工作台（F/D2/D3/G3/F10/G2）═══
  const [flags, setFlags] = useState<ReviewFlag[]>([]);
  const [flagTarget, setFlagTarget] = useState("");
  const [flagKind, setFlagKind] = useState<EdiscSourceKind>("chat");
  const [notarized, setNotarized] = useState(false);
  const [flagLevel, setFlagLevel] = useState<"" | EdiscFlagLevel>(""); // 空=桥预置档
  const refreshFlags = useCallback(async (cid: string) => {
    if (!cid) { setFlags([]); return; }
    try { setFlags((await ediscApi<{ items: ReviewFlag[] }>(`/api/edisc/review-flags?caseId=${encodeURIComponent(cid)}`)).items); } catch { /* 同上 */ }
  }, []);
  const saveFlag = () => void run(async () => {
    if (!flagTarget.trim()) throw new Error("填写标注对象（如：张三与李四的微信聊天记录）");
    const body: Record<string, unknown> = { caseId, targetLabel: flagTarget.trim(), kind: flagKind, notarized };
    if (flagLevel) body.level = flagLevel;
    const d = await ediscApi<{ id: string }>("/api/edisc/review-flags", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
    });
    setFlagTarget("");
    await refreshFlags(caseId);
    return `审查标注已登记（${d.id}）：预置档仅建议，定档归律师`;
  });
  useEffect(() => { void refreshFlags(caseId); }, [caseId, refreshFlags]);

  // ── F1 待证事实登记（审查先行件；四类排除纪律提示）──
  const [facts, setFacts] = useState<FactItem[]>([]);
  const [factText, setFactText] = useState("");
  const refreshFacts = useCallback(async (cid: string) => {
    if (!cid) { setFacts([]); return; }
    try { setFacts((await ediscApi<{ items: FactItem[] }>(`/api/edisc/facts?caseId=${encodeURIComponent(cid)}`)).items); } catch { /* 同上 */ }
  }, []);
  useEffect(() => { void refreshFacts(caseId); }, [caseId, refreshFacts]);
  const addFact = () => void run(async () => {
    const t = factText.trim();
    if (!t) throw new Error("填写一条待证事实（如：双方存在买卖合同关系）");
    await ediscApi("/api/edisc/facts", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ caseId, text: t }),
    });
    setFactText("");
    await refreshFacts(caseId);
    return "待证事实已登记（审查先行：先定待证事实，再审证据）";
  });

  // ── F4 三性评估表单（真实性/合法性/关联性逐项结论+理由）──
  const [triples, setTriples] = useState<TripleReview[]>([]);
  const [tripleTarget, setTripleTarget] = useState("");
  const [tripleConclusions, setTripleConclusions] = useState<Record<string, EdiscAttrConclusion>>({});
  const [tripleReasons, setTripleReasons] = useState<Record<string, string>>({});
  const refreshTriples = useCallback(async (cid: string) => {
    if (!cid) { setTriples([]); return; }
    try { setTriples((await ediscApi<{ items: TripleReview[] }>(`/api/edisc/triple-reviews?caseId=${encodeURIComponent(cid)}`)).items); } catch { /* 同上 */ }
  }, []);
  useEffect(() => { void refreshTriples(caseId); }, [caseId, refreshTriples]);
  const saveTriple = () => void run(async () => {
    const label = tripleTarget.trim();
    if (!label) throw new Error("填写三性评估对象（与审查标注对象一致，如：张三与李四的微信聊天记录）");
    const findings = EDISC_TRIPLE_ATTRIBUTES
      .filter((a) => tripleConclusions[a])
      .map((a) => ({ attr: a, conclusion: tripleConclusions[a], reason: tripleReasons[a] ?? "" }));
    if (!findings.length) throw new Error("至少给一项三性结论（真实性/合法性/关联性各选符合/存疑/不符合）");
    const d = await ediscApi<{ id: string }>("/api/edisc/triple-reviews", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ caseId, targetLabel: label, findings }),
    });
    setTripleConclusions({}); setTripleReasons({});
    await refreshTriples(caseId);
    return `三性评估已登记（${d.id}）：逐项结论+理由入卷，随七节报告第三节输出`;
  });

  // ── F6 四类缺口结构化（完全缺口/证明力不足/证据链断裂/形式瑕疵）──
  const [gaps, setGaps] = useState<GapItem[]>([]);
  const [gapKind, setGapKind] = useState<EdiscGapKind>("完全缺口");
  const [gapFact, setGapFact] = useState("");
  const [gapSuggestion, setGapSuggestion] = useState("");
  const [gapChannel, setGapChannel] = useState("");
  const [gapDifficulty, setGapDifficulty] = useState("");
  const [gapDeadline, setGapDeadline] = useState("");
  const refreshGaps = useCallback(async (cid: string) => {
    if (!cid) { setGaps([]); return; }
    try { setGaps((await ediscApi<{ items: GapItem[] }>(`/api/edisc/gaps?caseId=${encodeURIComponent(cid)}`)).items); } catch { /* 同上 */ }
  }, []);
  useEffect(() => { void refreshGaps(caseId); }, [caseId, refreshGaps]);
  const addGap = () => void run(async () => {
    if (!gapSuggestion.trim()) throw new Error("缺口登记必须给补充建议（拟取得什么证据）");
    await ediscApi("/api/edisc/gaps", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({
        caseId, kind: gapKind, factText: gapFact, suggestion: gapSuggestion,
        sourceChannel: gapChannel, difficulty: gapDifficulty, deadlineNote: gapDeadline,
      }),
    });
    setGapFact(""); setGapSuggestion(""); setGapChannel(""); setGapDifficulty(""); setGapDeadline("");
    await refreshGaps(caseId);
    return "缺口已结构化登记（随报告第五节输出建议与期限警示）";
  });

  // ── F2 形式六要素（逐候选登记；缺项显示"先补齐再实质审查"）──
  const [formalDraft, setFormalDraft] = useState<Record<string, FormalState>>({}); // candidateId → 表单
  const saveFormal = (id: string) => void run(async () => {
    const st = formalDraft[id] ?? { elements: candidates.find((c) => c.id === id)?.formal?.elements ?? {} };
    const d = await ediscApi<{ check: { complete: boolean; missing: string[]; note: string } }>(`/api/edisc/fix-lists/${encodeURIComponent(id)}/elements`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ elements: st.elements, by: confirmer.trim() || "律师" }),
    });
    setFormalDraft((cur) => ({ ...cur, [id]: { elements: st.elements, check: d.check } }));
    return d.check.complete ? "形式六要素齐备" : `已登记（${d.check.note}）`;
  });
  const setFormalField = (id: string, key: EdiscFormalElement, v: string) => {
    setFormalDraft((cur) => {
      const base = cur[id] ?? { elements: candidates.find((c) => c.id === id)?.formal?.elements ?? {} };
      return { ...cur, [id]: { ...base, elements: { ...base.elements, [key]: v } } };
    });
  };

  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [confirmer, setConfirmer] = useState("");
  const [metaTitle, setMetaTitle] = useState("");
  const [metaPurpose, setMetaPurpose] = useState("");
  const refreshCandidates = useCallback(async (cid: string) => {
    if (!cid) { setCandidates([]); return; }
    try { setCandidates((await ediscApi<{ items: Candidate[] }>(`/api/edisc/fix-lists?caseId=${encodeURIComponent(cid)}`)).items); } catch { /* 同上 */ }
  }, []);
  useEffect(() => { void refreshCandidates(caseId); }, [caseId, refreshCandidates]);
  const confirmCandidate = (id: string) => void run(async () => {
    const by = confirmer.trim();
    if (!by) throw new Error("确认必须留名（确认人）");
    await ediscApi(`/api/edisc/fix-lists/${encodeURIComponent(id)}/confirm`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ confirmedBy: by }),
    });
    await refreshCandidates(caseId);
    return "已确认入正式目录（建议-确认分权，操作留名）";
  });
  const correctMeta = (id: string, confirmed: boolean) => void run(async () => {
    if (!metaTitle.trim() && !metaPurpose.trim()) throw new Error("填写要更正的标题或证明目的");
    const d = await ediscApi<{ dryRun?: boolean; applied?: boolean; note?: string; after?: { title: string; purpose: string } }>(`/api/edisc/fix-lists/${encodeURIComponent(id)}/metadata`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ title: metaTitle, purpose: metaPurpose, confirmed, by: confirmer.trim() || "律师" }),
    });
    if (confirmed) { setMetaTitle(""); setMetaPurpose(""); await refreshCandidates(caseId); return "更正已落库并记精化留痕"; }
    return `干跑预览：${d.after?.title ?? ""}｜${d.after?.purpose ?? ""}（${d.note ?? ""}）`;
  });

  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const doVerify = () => void run(async () => {
    const d = await ediscApi<VerifyResult>("/api/edisc/fix-lists/verify", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ caseId }),
    });
    setVerify(d);
    return "校验完成";
  });
  const verifyLines = useMemo(() => (verify ? summarizeVerify(verify) : []), [verify]);

  const [lawyerOk, setLawyerOk] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  const gate = useMemo(() => canExportReviewReport({ flagCount: flags.length, lawyerConfirmed: lawyerOk }), [flags.length, lawyerOk]);
  const buildReport = () => void run(async () => {
    if (!gate.ok) throw new Error(gate.reason);
    const d = await ediscApi<{ report: string }>("/api/edisc/review-report?caseId=" + encodeURIComponent(caseId));
    setReport(d.report);
    return "七节审查报告已生成（引用均带锚，可回跳核验）";
  });

  const caseLabel = cases.find((c) => c.id === caseId)?.name ?? "";

  return (
    <section data-testid="edisc-panel" className="rounded-workspace-panel border border-border bg-header p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-ui-lg font-medium">电子数据取证</h2>
        <span className="text-ui-caption text-foreground-subtle">微信记录 · 转账流水 · 表格｜页/坐标锚固定 · 虚拟归类 · 清单校验</span>
        <div className="ml-auto flex items-center gap-2">
          <select
            aria-label="选择案件" data-testid="edisc-case"
            className="rounded border border-border bg-background px-2 py-1 text-ui-sm"
            value={caseId}
            onChange={(e) => { setCaseId(e.target.value); setHits(null); setRows([]); setCard(null); setReport(null); setVerify(null); }}
          >
            {cases.length === 0 ? <option value="">（暂无案件）</option> : null}
            {cases.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      </div>

      <div className="mb-3 flex flex-wrap gap-1" data-testid="edisc-tabs" role="tablist">
        {EDISC_SECTIONS.map((s) => (
          <button
            key={s.key} type="button" role="tab" aria-selected={section === s.key}
            data-testid={`edisc-tab-${s.key}`}
            onClick={() => setSection(s.key)}
            className={section === s.key
              ? "rounded bg-selected px-2 py-1 text-ui-sm"
              : "rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent"}
          >
            {s.label}
          </button>
        ))}
      </div>

      {note ? <p data-testid="edisc-note" className="mb-2 text-ui-caption">{note}</p> : null}
      {errorNote ? <p data-testid="edisc-error" className="mb-2 text-ui-sm text-red-500">{errorNote}</p> : null}
      {!caseId ? <p className="text-ui-caption text-foreground-subtle">先在上方选择案件；电子数据源按案件归档。</p> : null}

      {section === "sources" && caseId ? (
        <div data-testid="edisc-sources">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <select aria-label="登记类型" data-testid="edisc-upload-kind" className="rounded border border-border bg-background px-2 py-1 text-ui-sm" value={uploadKind} onChange={(e) => setUploadKind(e.target.value as EdiscSourceKind)}>
              {(Object.keys(EDISC_KIND_LABELS) as EdiscSourceKind[]).map((k) => <option key={k} value={k}>{EDISC_KIND_LABELS[k]}</option>)}
            </select>
            <label className="flex cursor-pointer items-center gap-1 rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent" data-testid="edisc-upload">
              登记源（入册即哈希+解析）
              <input type="file" className="hidden" onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void run(async () => {
                  const d = await ediscApi<{ id: string; deduplicated?: boolean; parseStatus: string }>("/api/edisc/sources", {
                    method: "POST", headers: { "content-type": "application/json" },
                    body: JSON.stringify({ caseId, kind: uploadKind, filename: f.name, dataBase64: await fileBase64(f) }),
                  });
                  await refreshSources(caseId);
                  return `已登记 ${f.name}（${d.id}${d.deduplicated ? "，同哈希去重" : ""}，解析 ${d.parseStatus}）`;
                });
                if (e.target) e.target.value = "";
              }} />
            </label>
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <input
              data-testid="edisc-scan-path" aria-label="扫描目录"
              className="w-72 rounded border border-border bg-background px-2 py-1 text-ui-sm" placeholder="服务器上的电子数据目录绝对路径（粗扫不哈希）"
              value={scanPath} onChange={(e) => setScanPath(e.target.value)}
            />
            <button
              type="button" data-testid="edisc-scan"
              className="rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!scanPath.trim()}
              onClick={() => void run(async () => {
                const d = await ediscApi<{ items: Array<{ filename?: string; status: string }>; summary: { ok: number; failed: number } }>("/api/edisc/scan", {
                  method: "POST", headers: { "content-type": "application/json" },
                  body: JSON.stringify({ caseId, rootPath: scanPath.trim() }),
                });
                await refreshSources(caseId);
                return `扫描完成：登记 ${d.summary.ok} 件、失败 ${d.summary.failed} 件（粗扫档不哈希，入册须重新登记）`;
              })}
            >
              <FolderOpen className="mr-1 inline size-3.5" />扫描目录
            </button>
          </div>
          <div className="mb-3 rounded border border-border bg-background p-2" data-testid="edisc-task-panel">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="text-ui-sm font-medium">批量整理任务</span>
              <label className="text-ui-caption">
                <input type="checkbox" className="mr-1" data-testid="edisc-task-pagecards" checked={taskPageCardsOnly} onChange={(e) => setTaskPageCardsOnly(e.target.checked)} />
                仅页卡档（只产页卡/块锚，跳过对话段结构化）
              </label>
              <label className="text-ui-caption">
                <input type="checkbox" className="mr-1" data-testid="edisc-task-stoponerr" checked={taskStopOnError} onChange={(e) => setTaskStopOnError(e.target.checked)} />
                出错即停（断点保留，恢复后续传）
              </label>
              <button type="button" data-testid="edisc-task-start" className="rounded border border-border px-2 py-0.5 text-ui-caption hover:bg-accent" onClick={() => taskCtl("start")}>
                启动整理（已登记未解析的源逐件后台处理）
              </button>
            </div>
            {task ? (
              <div data-testid="edisc-task-status" className="text-ui-caption">
                <span className={`mr-1 rounded px-1 ${(EDISC_TASK_STATUS_BADGE[task.status] ?? EDISC_TASK_STATUS_BADGE.running).cls}`}>
                  {(EDISC_TASK_STATUS_BADGE[task.status] ?? EDISC_TASK_STATUS_BADGE.running).label}
                </span>
                {summarizeTaskProgress(task.summary)}
                {task.pageCardsOnly ? "｜仅页卡档" : ""}{task.stopOnError ? "｜出错即停" : ""}
                <span className="ml-2 flex-wrap inline-flex gap-1">
                  <button type="button" data-testid="edisc-task-pause" disabled={task.status !== "running"} className="rounded border border-border px-1 hover:bg-accent disabled:opacity-40" onClick={() => taskCtl("pause")}>暂停</button>
                  <button type="button" data-testid="edisc-task-resume" disabled={task.status !== "paused"} className="rounded border border-border px-1 hover:bg-accent disabled:opacity-40" onClick={() => taskCtl("resume")}>恢复续传</button>
                  <button type="button" data-testid="edisc-task-cancel" disabled={task.status !== "running" && task.status !== "paused"} className="rounded border border-border px-1 hover:bg-accent disabled:opacity-40" onClick={() => taskCtl("cancel")}>取消</button>
                  <button type="button" data-testid="edisc-task-recover" disabled={task.status === "running" || !task.items.some((i) => i.state === "failed")} className="rounded border border-border px-1 hover:bg-accent disabled:opacity-40" onClick={() => taskCtl("recover-failed")}>失败件重跑</button>
                </span>
                {task.items.some((i) => i.state === "failed") ? (
                  <ul className="mt-1 text-red-500">
                    {task.items.filter((i) => i.state === "failed").map((i) => (
                      <li key={i.sourceId}>· {i.label}：{i.error ?? "解析失败"}（已尝试 {i.attempts} 次，可重跑）</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : (
              <p className="text-ui-caption text-foreground-subtle">逐件整理"已登记未解析"的源（登记时选择不解析的件在此后台补解析）；启动即返回检查点回执，可暂停/恢复/取消，失败件可重跑；粗扫态（无内容副本）会如实记为失败并提示重新入册。</p>
            )}
          </div>
          {sources.length === 0 ? (
            <p className="text-ui-caption text-foreground-subtle">这个案件还没有电子数据源。聊天记录用带文本层的导出 PDF，流水与表格用 xlsx/csv。</p>
          ) : (
            <ul data-testid="edisc-source-list" className="space-y-1">
              {sources.map((s) => {
                const pb = EDISC_PARSE_BADGE[s.parseStatus] ?? EDISC_PARSE_BADGE.pending;
                const ob = EDISC_OCR_BADGE[s.ocrStatus] ?? EDISC_OCR_BADGE.not_required;
                return (
                  <li key={s.id} data-testid="edisc-source-row" className="flex flex-wrap items-center gap-2 rounded border border-border bg-background px-2 py-1.5 text-ui-sm">
                    <Table2 className="size-4 shrink-0 text-foreground-subtle" />
                    <span className="font-medium">{s.filename}</span>
                    <span className="rounded bg-accent px-1 text-ui-caption">{EDISC_KIND_LABELS[s.kind] ?? s.kind}</span>
                    <span className={`rounded px-1 text-ui-caption ${pb.cls}`}>{pb.label}</span>
                    <span className={`rounded px-1 text-ui-caption ${ob.cls}`}>{ob.label}</span>
                    <span className="text-ui-caption text-foreground-subtle">{s.fileHash ? `哈希 ${s.fileHash.slice(0, 12)}…` : "未哈希（粗扫态）"}</span>
                    <button
                      type="button" data-testid="edisc-profile"
                      className="ml-auto rounded border border-border px-2 py-0.5 text-ui-caption hover:bg-accent"
                      onClick={() => void run(async () => {
                        setProfile(await ediscApi<ProfileItem>(`/api/edisc/sources/${encodeURIComponent(s.id)}/profile`));
                        return "源画像已打开";
                      })}
                    >
                      <FileSearch className="mr-1 inline size-3" />源画像
                    </button>
                    {s.error ? <span className="w-full text-ui-caption text-red-500">{s.error.message}</span> : null}
                  </li>
                );
              })}
            </ul>
          )}
          {profile ? (
            <div data-testid="edisc-profile-drawer" className="mt-2 rounded border border-border bg-background p-3 text-ui-sm">
              <div className="mb-1 flex items-center gap-2">
                <span className="font-medium">源画像</span>
                <span className="text-ui-caption text-foreground-subtle">{profile.fileHash ? `哈希 ${profile.fileHash.slice(0, 12)}…` : "未哈希"}</span>
                {profile.coordSystem ? <span className="text-ui-caption text-foreground-subtle">坐标系 {profile.coordSystem}</span> : null}
                <button type="button" className="ml-auto rounded border border-border px-2 py-0.5 text-ui-caption hover:bg-accent" onClick={() => setProfile(null)}>收起</button>
              </div>
              {profile.tables.length ? (
                <ul className="mb-1">
                  {profile.tables.map((t) => (
                    <li key={t.name} className="text-ui-caption">表「{t.name}」· {t.rowCount} 行</li>
                  ))}
                </ul>
              ) : null}
              {profile.pages != null ? <p className="text-ui-caption text-foreground-subtle">{profile.pages} 页 · {profile.blocks ?? 0} 块{profile.chatMessages != null ? ` · 对话段 ${profile.chatMessages}` : ""}</p> : null}
              <p className="text-ui-caption text-foreground-subtle">画像为结构概览（表清单/页块统计），行内容在「行浏览」按区间读取。</p>
            </div>
          ) : null}
        </div>
      ) : null}

      {section === "rows" && caseId ? (
        <div data-testid="edisc-rows-view">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <select aria-label="选择源" data-testid="edisc-rows-source" className="rounded border border-border bg-background px-2 py-1 text-ui-sm"
              value={rowSourceId}
              onChange={(e) => {
                const sid = e.target.value;
                setRowSourceId(sid);
                const t = sources.find((s) => s.id === sid)?.tables?.[0]?.name ?? "";
                setRowTable(t);
              }}
            >
              <option value="">（选择源）</option>
              {sources.filter((s) => s.parseStatus === "done").map((s) => (
                <option key={s.id} value={s.id}>{s.filename}</option>
              ))}
            </select>
            {rowSource?.tables?.length ? (
              <select aria-label="选择表" data-testid="edisc-rows-table" className="rounded border border-border bg-background px-2 py-1 text-ui-sm" value={rowTable} onChange={(e) => setRowTable(e.target.value)}>
                {rowSource.tables.map((t) => <option key={t.name} value={t.name}>{t.name}（{t.rowCount} 行）</option>)}
              </select>
            ) : null}
            <label className="text-ui-caption">行区间
              <input type="number" min={1} data-testid="edisc-rows-start" className="ml-1 w-16 rounded border border-border bg-background px-1 py-1 text-ui-sm" value={rowStart} onChange={(e) => setRowStart(Math.max(1, Number(e.target.value) || 1))} />
              –
              <input type="number" min={1} data-testid="edisc-rows-end" className="ml-1 w-16 rounded border border-border bg-background px-1 py-1 text-ui-sm" value={rowEnd} onChange={(e) => setRowEnd(Math.max(1, Number(e.target.value) || 1))} />
            </label>
            <button type="button" data-testid="edisc-rows-read" className="rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent" onClick={readRows}>读取行</button>
          </div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <input data-testid="edisc-rows-query" className="flex-1 rounded border border-border bg-background px-2 py-1 text-ui-sm" placeholder="按对方户名/金额/摘要关键词搜行（跨源，命中仅为定位线索）"
              value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }} />
            <button type="button" data-testid="edisc-rows-search" className="rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent" onClick={doSearch}>搜索</button>
          </div>
          {hits !== null ? (
            hits.length === 0 ? (
              <p data-testid="edisc-nohits" className="mb-2 text-ui-caption text-foreground-subtle">没有命中。换关键词，或先完成源登记解析。</p>
            ) : (
              <ul data-testid="edisc-hits" className="mb-2 space-y-1">
                {hits.slice(0, 30).map((h, i) => (
                  <li key={`${h.sourceId}-${h.rowNo}-${i}`} className="rounded border border-border bg-background px-2 py-1 text-ui-sm">
                    <span className="mr-1 rounded bg-accent px-1 text-ui-caption">{h.sourceFilename}·{h.tableName}·第 {h.rowNo} 行</span>
                    {h.text.length > 120 ? `${h.text.slice(0, 120)}…` : h.text}
                  </li>
                ))}
              </ul>
            )
          ) : null}
          {rows.length ? (
            <div>
              <table className="w-full border-collapse text-ui-sm" data-testid="edisc-rows">
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.rowNo} className="border-b border-border">
                      <td className="w-8 py-1">
                        <input
                          type="checkbox" aria-label={`选中第 ${r.rowNo} 行`} data-testid="edisc-row-check"
                          checked={picked.includes(r.rowNo)}
                          onChange={(e) => setPicked((cur) => (e.target.checked ? [...cur, r.rowNo] : cur.filter((n) => n !== r.rowNo)))}
                        />
                      </td>
                      <td className="w-14 py-1 text-ui-caption text-foreground-subtle">{r.rowNo}</td>
                      <td className="py-1">{r.text.length > 200 ? `${r.text.slice(0, 200)}…` : r.text}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className="text-ui-caption">已选 {picked.length} 行 · 引用地址={rowTable || "聊天记录"} 行区间+源哈希</span>
                <input data-testid="edisc-classify-category" className="w-32 rounded border border-border bg-background px-2 py-1 text-ui-sm" placeholder="类目（如：收/支/往来）" value={category} onChange={(e) => setCategory(e.target.value)} />
                <input data-testid="edisc-classify-reason" className="w-56 rounded border border-border bg-background px-2 py-1 text-ui-sm" placeholder="归类理由（可选）" value={reason} onChange={(e) => setReason(e.target.value)} />
                <button type="button" data-testid="edisc-classify" className="rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent" onClick={classify}>归类打标（虚拟覆盖层）</button>
              </div>
            </div>
          ) : (
            <p className="text-ui-caption text-foreground-subtle">选择源与行区间后读取；行号从 1 起，默认 1–50，单次至多 500 行。</p>
          )}
        </div>
      ) : null}

      {section === "board" && caseId ? (
        <div data-testid="edisc-board-view">
          {boardGroups.length === 0 ? (
            <p className="text-ui-caption text-foreground-subtle">还没有归类记录。到「行浏览」选中行打标后，这里按类目汇总。</p>
          ) : (
            <ul className="space-y-2">
              {boardGroups.map((g) => (
                <li key={g.category} data-testid="edisc-board-group" className="rounded border border-border bg-background p-2 text-ui-sm">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-medium">类目「{g.category}」</span>
                    <span className="text-ui-caption text-foreground-subtle">{g.items.length} 条归类</span>
                    <button type="button" data-testid="edisc-fixlist-gen" className="ml-auto rounded border border-border px-2 py-0.5 text-ui-caption hover:bg-accent"
                      onClick={() => genFixList(g.category)}>
                      生成候选清单
                    </button>
                  </div>
                  <ul className="text-ui-caption text-foreground-subtle">
                    {g.items.slice(0, 6).map((c) => (
                      <li key={c.id}>{c.refs.map((r) => formatRowAddress(r)).join("；")}{c.reason ? `｜理由：${c.reason}` : ""}｜by {c.createdBy}</li>
                    ))}
                    {g.items.length > 6 ? <li>…其余 {g.items.length - 6} 条</li> : null}
                  </ul>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-ui-caption text-foreground-subtle">候选清单只聚合已人工归类的行，属建议档；未经律师确认不进正式证据目录。</p>
        </div>
      ) : null}

      {section === "pages" && caseId ? (
        <div data-testid="edisc-pages-view">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <select aria-label="选择 PDF 源" data-testid="edisc-page-source" className="rounded border border-border bg-background px-2 py-1 text-ui-sm" value={pageSourceId} onChange={(e) => { setPageSourceId(e.target.value); setCard(null); }}>
              <option value="">（选择 PDF 源）</option>
              {pdfSources.map((s) => <option key={s.id} value={s.id}>{s.filename}</option>)}
            </select>
            <label className="text-ui-caption">页码
              <input type="number" min={1} data-testid="edisc-page-no" className="ml-1 w-16 rounded border border-border bg-background px-1 py-1 text-ui-sm" value={pageNo} onChange={(e) => setPageNo(Math.max(1, Number(e.target.value) || 1))} />
            </label>
            <button type="button" data-testid="edisc-page-read" className="rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent" onClick={readPage}>读取页卡</button>
            <span className="text-ui-caption text-foreground-subtle">引用前须整页覆盖阅读，不得抽样代替。</span>
          </div>
          {card ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div data-testid="edisc-page-text" className="rounded border border-border bg-background p-2 text-ui-sm">
                <p className="mb-1 text-ui-caption text-foreground-subtle">第 {card.page} 页全文（文本层页卡；页图渲染后补，坐标见右侧块 bbox）</p>
                <pre className="whitespace-pre-wrap">{card.fullText || "（本页无文本块）"}</pre>
              </div>
              <div>
                <ul data-testid="edisc-page-blocks" className="mb-2 max-h-64 space-y-1 overflow-y-auto">
                  {card.blocks.map((b) => (
                    <li key={b.seq}>
                      <button type="button"
                        className={`w-full rounded border px-2 py-1 text-left text-ui-caption ${annSeq === b.seq ? "border-selected bg-selected" : "border-border bg-background hover:bg-accent"}`}
                        onClick={() => setAnnSeq(b.seq)}>
                        块 {b.seq}｜bbox [{b.bbox.map((n) => Math.round(n)).join(", ")}]
                        <span className="ml-1 text-foreground-subtle">{b.text.slice(0, 40)}{b.text.length > 40 ? "…" : ""}</span>
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="flex flex-wrap items-center gap-2 text-ui-sm">
                  <select aria-label="批注类型" data-testid="edisc-annot-type" className="rounded border border-border bg-background px-1 py-1 text-ui-caption" value={annType} onChange={(e) => setAnnType(e.target.value)}>
                    <option value="highlight">高亮</option>
                    <option value="note">批注</option>
                    <option value="mark">标记</option>
                  </select>
                  <input type="color" aria-label="批注颜色" data-testid="edisc-annot-color" className="size-7 rounded border border-border bg-background" value={annColor} onChange={(e) => setAnnColor(e.target.value)} />
                  <input data-testid="edisc-annot-text" className="flex-1 rounded border border-border bg-background px-2 py-1 text-ui-sm" placeholder="批注文字" value={annText} onChange={(e) => setAnnText(e.target.value)} />
                  <button type="button" data-testid="edisc-annot-save" className="rounded border border-border bg-background px-2 py-1 hover:bg-accent" onClick={saveAnnotation}>保存批注</button>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-ui-caption text-foreground-subtle">读取页卡后逐块覆盖阅读；点击文本块选中为批注落点（矩形取块 bbox）。</p>
          )}
          {annotGroups.length ? (
            <div data-testid="edisc-annot-list" className="mt-3">
              <p className="mb-1 text-ui-caption font-medium">批注（按页分组）</p>
              {annotGroups.map((g) => (
                <div key={g.page} className="mb-1">
                  <span className="text-ui-caption text-foreground-subtle">第 {g.page} 页</span>
                  <ul>
                    {g.items.map((a) => (
                      <li key={a.id} className="text-ui-caption">
                        <span className="mr-1 inline-block size-2 rounded-sm align-middle" style={{ background: a.color }} />
                        [{a.type}] {a.textContent || "（无文字）"}｜矩形 [{a.rects.map((r) => r.map((n) => Math.round(n)).join(",")).join("] [")}]｜by {a.createdBy}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {section === "review" && caseId ? (
        <div data-testid="edisc-review-view">
          <div className="mb-2 rounded border border-border bg-background p-2" data-testid="edisc-facts">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="text-ui-sm font-medium">待证事实（先定待证事实，再审证据）</span>
              <input data-testid="edisc-fact-input" className="w-72 rounded border border-border bg-background px-2 py-1 text-ui-sm" placeholder="一条待证事实（如：2026-03 双方约定了货款结算方式）" value={factText} onChange={(e) => setFactText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") addFact(); }} />
              <button type="button" data-testid="edisc-fact-add" className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-accent" onClick={addFact}>登记待证事实</button>
            </div>
            <p className="text-ui-caption text-foreground-subtle">四类不入清单：{EDISC_FACT_EXCLUSIONS.join("／")}；提炼自诉求与争点，判断归律师。</p>
            {facts.length ? (
              <ol className="mt-1 list-decimal pl-5 text-ui-caption" data-testid="edisc-fact-list">
                {facts.map((f) => <li key={f.id}>{f.text}（by {f.createdBy}）</li>)}
              </ol>
            ) : null}
          </div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <input data-testid="edisc-flag-target" className="w-64 rounded border border-border bg-background px-2 py-1 text-ui-sm" placeholder="标注对象（如：张三与李四的微信聊天记录）" value={flagTarget} onChange={(e) => setFlagTarget(e.target.value)} />
            <select aria-label="证据类型" data-testid="edisc-flag-kind" className="rounded border border-border bg-background px-2 py-1 text-ui-sm" value={flagKind} onChange={(e) => setFlagKind(e.target.value as EdiscSourceKind)}>
              {(Object.keys(EDISC_KIND_LABELS) as EdiscSourceKind[]).map((k) => <option key={k} value={k}>{EDISC_KIND_LABELS[k]}</option>)}
            </select>
            <label className="text-ui-caption">
              <input type="checkbox" data-testid="edisc-flag-notarized" className="mr-1" checked={notarized} onChange={(e) => setNotarized(e.target.checked)} />
              已公证/可信时间戳
            </label>
            <select aria-label="档位覆写" data-testid="edisc-flag-level" className="rounded border border-border bg-background px-2 py-1 text-ui-sm" value={flagLevel} onChange={(e) => setFlagLevel(e.target.value as "" | EdiscFlagLevel)}>
              <option value="">档位=按预置规则</option>
              {(Object.keys(EDISC_LEVEL_BADGE) as EdiscFlagLevel[]).map((lv) => <option key={lv} value={lv}>{EDISC_LEVEL_BADGE[lv].label}</option>)}
            </select>
            <button type="button" data-testid="edisc-flag-save" className="rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent" onClick={saveFlag}>登记审查标注</button>
          </div>
          <p className="mb-2 text-ui-caption text-foreground-subtle">未经公证的聊天/流水/表格默认存疑保留（证明力预置弱，需印证或申请鉴定）；预置档只是建议，定档归律师。</p>
          {flags.length ? (
            <ul data-testid="edisc-flag-list" className="mb-3 space-y-1">
              {flags.map((f) => {
                const lb = EDISC_LEVEL_BADGE[f.level] ?? EDISC_LEVEL_BADGE.doubt;
                return (
                  <li key={f.id} className="rounded border border-border bg-background px-2 py-1 text-ui-sm">
                    <span className={`mr-1 rounded px-1 text-ui-caption ${lb.cls}`}>{lb.label}</span>
                    <span className="font-medium">{f.targetLabel}</span>
                    <span className="mr-1 rounded bg-accent px-1 text-ui-caption">{EDISC_KIND_LABELS[f.kind] ?? f.kind}</span>
                    {f.proofStrength ? <span className="mr-1 text-ui-caption text-foreground-subtle">证明力：{f.proofStrength}</span> : null}
                    {f.tags.map((t) => <span key={t} className="mr-1 rounded bg-accent px-1 text-ui-caption">#{t}</span>)}
                    <span className="block text-ui-caption text-foreground-subtle">{f.issues.join("；")}{f.lawyerAction ? `｜建议：${f.lawyerAction}` : ""}</span>
                  </li>
                );
              })}
            </ul>
          ) : null}

          <div className="mb-2 rounded border border-border bg-background p-2" data-testid="edisc-triple">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="text-ui-sm font-medium">三性评估（逐项结论+理由）</span>
              <input data-testid="edisc-triple-target" className="w-64 rounded border border-border bg-background px-2 py-1 text-ui-sm" placeholder="评估对象（如：张三与李四的微信聊天记录）" value={tripleTarget} onChange={(e) => setTripleTarget(e.target.value)} />
              <button type="button" data-testid="edisc-triple-save" className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-accent" onClick={saveTriple}>登记三性评估</button>
            </div>
            {EDISC_TRIPLE_ATTRIBUTES.map((a) => (
              <div key={a} className="mb-1 flex flex-wrap items-center gap-2 text-ui-caption">
                <span className="w-14">{a}</span>
                <select aria-label={`${a}结论`} data-testid={`edisc-triple-${a}`} className="rounded border border-border bg-background px-1 py-0.5" value={tripleConclusions[a] ?? ""} onChange={(e) => setTripleConclusions((cur) => ({ ...cur, [a]: e.target.value as EdiscAttrConclusion }))}>
                  <option value="">（未评）</option>
                  {EDISC_ATTR_CONCLUSIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                <input aria-label={`${a}理由`} data-testid={`edisc-triple-${a}-reason`} className="flex-1 rounded border border-border bg-background px-1 py-0.5" placeholder="理由（结论的依据，可选）" value={tripleReasons[a] ?? ""} onChange={(e) => setTripleReasons((cur) => ({ ...cur, [a]: e.target.value }))} />
              </div>
            ))}
            {triples.length ? (
              <ul className="mt-1 text-ui-caption" data-testid="edisc-triple-list">
                {triples.map((t) => (
                  <li key={t.id}>
                    {t.findings.map((f, i) => {
                      const b = EDISC_ATTR_BADGE[f.conclusion as EdiscAttrConclusion];
                      return (
                        <span key={`${t.id}-${f.attr}`}>
                          {i === 0 ? `${t.targetLabel}：` : "，"}
                          {f.attr}=
                          <span className={`rounded px-0.5 ${b?.cls ?? ""}`}>{f.conclusion}</span>
                          {f.reason ? `（${f.reason}）` : ""}
                        </span>
                      );
                    })}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <div className="mb-2 rounded border border-border bg-background p-2" data-testid="edisc-gaps">
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="text-ui-sm font-medium">缺口盘点（四类缺口+补充建议）</span>
              <select aria-label="缺口类目" data-testid="edisc-gap-kind" className="rounded border border-border bg-background px-1 py-0.5 text-ui-caption" value={gapKind} onChange={(e) => setGapKind(e.target.value as EdiscGapKind)}>
                {EDISC_GAP_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
              <button type="button" data-testid="edisc-gap-add" className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-accent" onClick={addGap}>登记缺口</button>
            </div>
            <div className="mb-1 flex flex-wrap gap-1 text-ui-caption">
              <input data-testid="edisc-gap-fact" className="w-40 rounded border border-border bg-background px-1 py-0.5" placeholder="对应待证事实" value={gapFact} onChange={(e) => setGapFact(e.target.value)} />
              <input data-testid="edisc-gap-suggestion" className="w-56 rounded border border-border bg-background px-1 py-0.5" placeholder="建议补充的证据（必填）" value={gapSuggestion} onChange={(e) => setGapSuggestion(e.target.value)} />
              <input data-testid="edisc-gap-channel" className="w-40 rounded border border-border bg-background px-1 py-0.5" placeholder="取得渠道（如：向银行调取）" value={gapChannel} onChange={(e) => setGapChannel(e.target.value)} />
              <input data-testid="edisc-gap-difficulty" className="w-24 rounded border border-border bg-background px-1 py-0.5" placeholder="收集难度" value={gapDifficulty} onChange={(e) => setGapDifficulty(e.target.value)} />
              <input data-testid="edisc-gap-deadline" className="w-40 rounded border border-border bg-background px-1 py-0.5" placeholder="举证期限警示（可选）" value={gapDeadline} onChange={(e) => setGapDeadline(e.target.value)} />
            </div>
            <p className="text-ui-caption text-foreground-subtle">完全缺口=没有任何证据；证明力不足=有但偏弱；证据链断裂=中间环节缺失；形式瑕疵=六要素不全。每个缺口给补充建议与取得渠道，涉期限的给硬性警示。</p>
            {gaps.length ? (
              <ul className="mt-1 text-ui-caption" data-testid="edisc-gap-list">
                {gaps.map((g) => <li key={g.id}>{formatGapEntry(g)}</li>)}
              </ul>
            ) : null}
          </div>

          <div className="mb-2 flex flex-wrap items-center gap-2">
            <input data-testid="edisc-confirmer" className="w-32 rounded border border-border bg-background px-2 py-1 text-ui-sm" placeholder="确认人姓名" value={confirmer} onChange={(e) => setConfirmer(e.target.value)} />
            <button type="button" data-testid="edisc-verify" className="rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent" onClick={doVerify}>校验清单（锚一一对应+回跳）</button>
            <label className="text-ui-caption">
              <input type="checkbox" data-testid="edisc-lawyer-gate" className="mr-1" checked={lawyerOk} onChange={(e) => setLawyerOk(e.target.checked)} />
              <ShieldCheck className="mr-1 inline size-3.5" />我已逐项过目全部存疑/不足标注（执业律师）
            </label>
            <button type="button" data-testid="edisc-report" className="rounded border border-border bg-background px-2 py-1 text-ui-sm hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!gate.ok} title={gate.reason || undefined} onClick={buildReport}>
              生成七节审查报告
            </button>
          </div>
          {verifyLines.length ? (
            <div data-testid="edisc-verify-lines" className="mb-2 rounded border border-border bg-background p-2 text-ui-caption">
              {verifyLines.map((l, i) => <p key={i}>{l}</p>)}
            </div>
          ) : null}
          {!gate.ok && flags.length ? <p data-testid="edisc-gate-reason" className="mb-2 text-ui-caption text-amber-600 dark:text-amber-400">{gate.reason}</p> : null}
          {report ? (
            <pre data-testid="edisc-report-text" className="mb-3 max-h-80 overflow-y-auto whitespace-pre-wrap rounded border border-border bg-background p-2 text-ui-caption">{report}</pre>
          ) : null}

          {candidates.length ? (
            <ul data-testid="edisc-candidate-list" className="space-y-1">
              {candidates.map((c) => (
                <li key={c.id} className="rounded border border-border bg-background px-2 py-1 text-ui-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{c.title}</span>
                    <span className="rounded bg-accent px-1 text-ui-caption">{c.category}</span>
                    <span className={`rounded px-1 text-ui-caption ${c.status === "confirmed" ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"}`}>
                      {c.status === "confirmed" ? `已确认（${c.confirmedBy ?? ""}）` : "建议档待确认"}
                    </span>
                    <span className={`rounded px-1 text-ui-caption ${(formalDraft[c.id]?.check ?? c.formal?.check)?.complete ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"}`}>
                      形式六要素：{(formalDraft[c.id]?.check ?? c.formal?.check)
                        ? ((formalDraft[c.id]?.check ?? c.formal?.check)!).complete
                          ? "齐备"
                          : `待补齐（${((formalDraft[c.id]?.check ?? c.formal?.check)!).missing.join("、")}，先补齐再实质审查）`
                        : "未登记"}
                    </span>
                    {c.status !== "confirmed" ? (
                      <button type="button" data-testid="edisc-candidate-confirm" className="ml-auto rounded border border-border px-2 py-0.5 text-ui-caption hover:bg-accent" onClick={() => confirmCandidate(c.id)}>确认入正式目录</button>
                    ) : null}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-ui-caption">
                    <span className="text-foreground-subtle">{c.anchors.map((a) => a.label).join("；")}</span>
                    <input data-testid="edisc-meta-title" className="w-48 rounded border border-border bg-background px-1 py-0.5 text-ui-caption" placeholder="更正标题" value={metaTitle} onChange={(e) => setMetaTitle(e.target.value)} />
                    <input data-testid="edisc-meta-purpose" className="w-48 rounded border border-border bg-background px-1 py-0.5 text-ui-caption" placeholder="更正证明目的" value={metaPurpose} onChange={(e) => setMetaPurpose(e.target.value)} />
                    <button type="button" data-testid="edisc-meta-dry" className="rounded border border-border px-2 py-0.5 hover:bg-accent" onClick={() => correctMeta(c.id, false)}>干跑预览</button>
                    <button type="button" data-testid="edisc-meta-apply" className="rounded border border-border px-2 py-0.5 hover:bg-accent" onClick={() => correctMeta(c.id, true)}>确认落库</button>
                  </div>
                  <details className="mt-1" data-testid={`edisc-formal-box-${c.id}`}>
                    <summary className="cursor-pointer text-ui-caption text-foreground-subtle">形式六要素登记（名称/形成时间/出具方/原件或复印件/证明目的/对应待证事实）</summary>
                    <div className="mt-1 flex flex-wrap items-center gap-1">
                      {EDISC_FORMAL_ELEMENTS.map((k) => (
                        <label key={k} className="text-ui-caption">
                          <span className="mr-0.5 text-foreground-subtle">{k}</span>
                          <input aria-label={k} data-testid={`edisc-formal-${k}`} className="w-32 rounded border border-border bg-background px-1 py-0.5 text-ui-caption"
                            value={(formalDraft[c.id]?.elements ?? c.formal?.elements ?? {})[k] ?? ""}
                            onChange={(e) => setFormalField(c.id, k, e.target.value)} />
                        </label>
                      ))}
                      <button type="button" data-testid="edisc-formal-save" className="rounded border border-border px-2 py-0.5 hover:bg-accent" onClick={() => saveFormal(c.id)}>登记六要素</button>
                      <span className="text-ui-caption text-foreground-subtle">
                        {(() => {
                          const st = formalDraft[c.id]?.elements ?? c.formal?.elements ?? {};
                          const miss = missingFormalElements(st as Partial<Record<EdiscFormalElement, string>>);
                          return miss.length ? `待补齐：${miss.join("、")}` : "六要素齐备";
                        })()}
                      </span>
                    </div>
                  </details>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-ui-caption text-foreground-subtle">还没有候选清单项。到「归类看板」按类目生成。</p>
          )}
        </div>
      ) : null}

      {caseId ? (
        <p className="mt-3 text-ui-caption text-foreground-subtle">
          当前案件 {caseLabel}｜原件只读：登记后任何操作不回写原件；归类/批注/更正全部是覆盖层，精化留痕可在桥面审计查。
        </p>
      ) : null}
    </section>
  );
}
