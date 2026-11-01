// 功能 #10 模板文书起草（RE-10 §3.4）：文书面板。
// 左栏=模板库|历史页签（搜索+四分类+两列卡片+自定义三态徽标）；中栏=空态|表单态（材料勾选+粘贴案情+字段卡，
// 我方主体置顶+15 项折叠）|预览态（MD 渲染+免责行）；右栏=就绪摘要+生成门|导出按钮组+反馈条；
// 浮窗=五阶段工作流（pending/running/done/error 四态）+运行中引导输入+最小化胶囊三态；上传弹窗=拖拽/点击+白名单+OCR 提示。
// 文案全部自写（表达隔离）；生成走桥独立隐藏线程（draftGenerate/draftStatus 轮询，runId 防过期事件串台）。
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen, CheckCircle2, CircleDashed, Download, FileEdit, FileText, FileUp, History,
  Loader2, Minimize2, Scale, Send, ShieldAlert, Trash2, TriangleAlert, Upload, X, XCircle,
} from "lucide-react";
import { MessageResponse } from "../ui-kit.js";
import { useServices } from "../ui-kit.js";

type FieldDef = { id: string; label: string; type: string; placeholder?: string; options?: string[] };
type BuiltinTemplate = {
  id: string; name: string; category: "litigation" | "non-litigation"; description: string;
  content: string; fields: FieldDef[]; legalBasis?: string; icon?: string;
};
type UserTemplateInfo = {
  id: string; name: string; description: string; category: "custom"; fields: FieldDef[];
  learningStatus: "idle" | "analyzing" | "done" | "failed"; learningError: string;
  hasSourceDocx: boolean; createdAt: number;
};
type HistorySummary = {
  id: string; templateName: string; templateCategory: string; templateSource: string;
  materialCount: number; hasInstructions: boolean; verdict: string; createdAt: number;
};
type SelectedTemplate =
  | { source: "builtin"; id: string; name: string; fields: FieldDef[]; category: "litigation" | "non-litigation" }
  | { source: "custom"; id: string; name: string; fields: FieldDef[]; learningStatus: UserTemplateInfo["learningStatus"]; hasSourceDocx: boolean }
  | null;

const OUR_PARTY_FIELD: FieldDef = { id: "我方主体", label: "我方主体", type: "text", placeholder: "本次文书代表的当事人；可留空，由 AI 从材料中识别" };
const MAX_VISIBLE_FIELDS = 15;

function sanitizeFileName(name: string): string {
  return name.replace(/[<>:"/\|?*]/g, "_"); // 导出前文件名净化
}
function bytesToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}
function downloadBase64(base64: string, fileName: string, mime: string): void {
  const blob = new Blob([Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = fileName; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
const STAGE_LABELS: Array<{ key: string; label: string }> = [
  { key: "materials", label: "理解材料" },
  { key: "analysis", label: "归纳争议" },
  { key: "research", label: "法律调研" },
  { key: "argumentation", label: "研究论证" },
  { key: "drafting", label: "撰写文书" },
];
function StageGlyph({ state }: { state: string }) {
  if (state === "done") return <CheckCircle2 className="size-3.5 text-emerald-500" />;
  if (state === "running") return <Loader2 className="size-3.5 animate-spin text-blue-500" />;
  if (state === "error") return <XCircle className="size-3.5 text-red-500" />;
  return <CircleDashed className="size-3.5 text-foreground-subtle" />;
}

export function DocumentDraftingPanel({ workspacePath }: { workspacePath?: string }) {
  const { zcodeAgentService } = useServices();
  const [builtin, setBuiltin] = useState<BuiltinTemplate[]>([]);
  const [userTemplates, setUserTemplates] = useState<UserTemplateInfo[]>([]);
  const [documents, setDocuments] = useState<Array<{ name: string; kind: string }>>([]);
  const [leftTab, setLeftTab] = useState<"templates" | "history">("templates");
  const [catTab, setCatTab] = useState<"all" | "litigation" | "non-litigation" | "custom">("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<SelectedTemplate>(null);
  const [checkedMaterials, setCheckedMaterials] = useState<string[]>([]);
  const [pastedCase, setPastedCase] = useState("");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [mode, setMode] = useState<"editing" | "running" | "preview">("editing");
  const [gen, setGen] = useState<{ status: string; stages: Record<string, string>; lastTool: string; notice: string; error: string; verdict: string; materialCount?: number } | null>(null);
  const [previewContent, setPreviewContent] = useState("");
  const [floatVisible, setFloatVisible] = useState(false);
  const [floatMinimized, setFloatMinimized] = useState(false);
  const [steerText, setSteerText] = useState("");
  const [steerMsg, setSteerMsg] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [exportingFormat, setExportingFormat] = useState<"" | "docx" | "md">("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [showMoreFields, setShowMoreFields] = useState(false);
  const [historyRecords, setHistoryRecords] = useState<HistorySummary[]>([]);
  const [historySearch, setHistorySearch] = useState("");
  const [historyBusyId, setHistoryBusyId] = useState("");
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [editView, setEditView] = useState<"visual" | "source">("visual");
  const [deletingTplId, setDeletingTplId] = useState("");
  const [editDraft, setEditDraft] = useState("");
  const runIdRef = useRef(0);
  const draftIdRef = useRef("");

  const refreshCatalog = useCallback(() => {
    setCatalogLoading(true);
    zcodeAgentService.draftCatalog?.({ workspacePath: workspacePath ?? "" })
      .then((r) => { setBuiltin(r?.builtin ?? []); setUserTemplates(r?.userTemplates ?? []); setCatalogLoading(false); })
      .catch(() => { setBuiltin([]); setUserTemplates([]); setCatalogLoading(false); }); // 列表加载失败静默回退内置（I9）
  }, [zcodeAgentService, workspacePath]);
  const refreshHistory = useCallback(() => {
    zcodeAgentService.draftHistoryList?.({ workspacePath: workspacePath ?? "" })
      .then((r) => { setHistoryRecords(r?.records ?? []); setHistoryError(null); })
      .catch((e: unknown) => setHistoryError(String((e as Error)?.message ?? e)));
  }, [zcodeAgentService, workspacePath]);
  useEffect(() => { refreshCatalog(); refreshHistory(); }, [refreshCatalog, refreshHistory]);
  useEffect(() => {
    zcodeAgentService.listWorkspaceDocuments?.({ workspacePath: workspacePath ?? "" })
      .then((r) => setDocuments(r?.documents ?? []))
      .catch(() => setDocuments([]));
  }, [zcodeAgentService, workspacePath]);
  // 卸载清理（E11）：中止运行中的生成线程
  useEffect(() => () => {
    if (draftIdRef.current) void zcodeAgentService.draftCancel?.({ draftId: draftIdRef.current });
  }, [zcodeAgentService]);

  const templateList = useMemo(() => {
    const kw = search.trim().toLowerCase();
    const hitName = (n: string) => !kw || n.toLowerCase().includes(kw); // 仅过滤名称，大小写不敏感
    const customs = userTemplates.filter((t) => hitName(t.name));
    const builtins = builtin.filter((t) => hitName(t.name));
    if (catTab === "custom") return { customs, builtins: [] };
    if (catTab === "litigation") return { customs: [], builtins: builtins.filter((t) => t.category === "litigation") };
    if (catTab === "non-litigation") return { customs: [], builtins: builtins.filter((t) => t.category === "non-litigation") };
    return { customs, builtins };
  }, [builtin, userTemplates, search, catTab]);

  const filledCount = useMemo(() => {
    if (!selected) return 0;
    const base = (fieldValues["我方主体"] ?? "").trim() ? 1 : 0;
    return base + (selected?.fields ?? []).filter((f) => (fieldValues[f.id] ?? "").trim()).length;
  }, [fieldValues, selected]);
  const totalFields = (selected?.fields.length ?? 0) + (selected ? 1 : 0);
  const canGenerate = checkedMaterials.length > 0 || pastedCase.trim().length > 0 || filledCount > 0;

  const pickTemplate = useCallback((t: SelectedTemplate) => {
    setSelected(t);
    setFieldValues({});
    setShowMoreFields(false);
    setFormError(null);
    setMode("editing");
    setPreviewContent("");
  }, []);

  const runGenerate = useCallback(() => {
    // 生成门（D9）：三源择一非空；不预禁用按钮，空则报错不发请求
    if (!canGenerate) {
      setFormError("请先勾选案件材料、粘贴案情文字，或填写文书字段（至少一项）后再生成。");
      return;
    }
    setFormError(null);
    const myRun = ++runIdRef.current;
    const prev = draftIdRef.current;
    const start = (id: string) => {
      setMode("running");
      setFloatVisible(true);
      setFloatMinimized(false);
      setSteerMsg(null);
      const poll = () => {
        if (runIdRef.current !== myRun) return; // runId 防过期事件串台（E10）
        zcodeAgentService.draftStatus?.({ draftId: id })
          .then((st) => {
            if (runIdRef.current !== myRun) return;
            setGen({ status: st?.status ?? "running", stages: st?.stages ?? {}, lastTool: st?.lastTool ?? "", notice: st?.notice ?? "", error: st?.error ?? "", verdict: st?.verdict ?? "", materialCount: st?.materialCount });
            if (st?.status && st.status !== "running") {
              if (st.status === "cancelled") { setMode("editing"); return; }
              if (st.status === "error") { setMode("editing"); setFormError(st.error || "生成失败，请重试。"); refreshHistory(); return; }
              setPreviewContent(st.content ?? "");
              setMode("preview");
              refreshHistory(); // 生成后自动刷新历史（G5）
              return;
            }
            setTimeout(poll, 900);
          })
          .catch((e: unknown) => {
            if (runIdRef.current !== myRun) return;
            setMode("editing");
            setFormError(String((e as Error)?.message ?? e));
          });
      };
      poll();
    };
    if (prev) {
      zcodeAgentService.draftCancel?.({ draftId: prev }).catch(() => {}).finally(() => {
        zcodeAgentService.draftGenerate?.({
          workspacePath: workspacePath ?? "",
          templateSource: selected?.source ?? "builtin",
          templateId: selected?.id,
          fieldValues,
          materialNames: checkedMaterials,
          pastedCase,
        })
          .then((r) => { draftIdRef.current = r?.draftId ?? ""; setGen(null); start(r.draftId); })
          .catch((e: unknown) => { setMode("editing"); setFormError(String((e as Error)?.message ?? e)); });
      });
      return;
    }
    zcodeAgentService.draftGenerate?.({
      workspacePath: workspacePath ?? "",
      templateSource: selected?.source ?? "builtin",
      templateId: selected?.id,
      fieldValues,
      materialNames: checkedMaterials,
      pastedCase,
    })
      .then((r) => { draftIdRef.current = r?.draftId ?? ""; if (r?.materialErrors?.length) setFormError(r.materialErrors.join("；")); setGen(null); start(r.draftId); })
      .catch((e: unknown) => { setMode("editing"); setFormError(String((e as Error)?.message ?? e)); });
  }, [canGenerate, checkedMaterials, fieldValues, pastedCase, selected, workspacePath, zcodeAgentService, refreshHistory]);


  const sendSteer = useCallback(() => {
    const text = steerText.trim();
    if (!text || !draftIdRef.current) return;
    zcodeAgentService.draftSteer?.({ draftId: draftIdRef.current, text })
      .then(() => { setSteerMsg("引导已送达，模型将在生成中采纳。"); setSteerText(""); })
      .catch((e: unknown) => setSteerMsg(String((e as Error)?.message ?? e)));
  }, [steerText, zcodeAgentService]);

  const doExportWord = useCallback(() => {
    if (!previewContent || exportingFormat) return;
    setExportingFormat("docx");
    setFeedback(null);
    zcodeAgentService.draftExportWord?.({
      templateSource: selected?.source ?? "builtin",
      templateId: selected?.id,
      markdown: previewContent,
    })
      .then((r) => {
        downloadBase64(r.docxBase64, sanitizeFileName((selected?.name ?? "法律文书") + ".docx"),
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
        setFeedback({ kind: "ok", text: (r.mode === "inplace" ? "已基于原 DOCX 原位写入并导出（版式保留）。" : "已按标准法律文书格式导出。") + (r.warning || "") });
      })
      .catch((e: unknown) => setFeedback({ kind: "err", text: String((e as Error)?.message ?? e) }))
      .finally(() => setExportingFormat(""));
  }, [previewContent, exportingFormat, selected, zcodeAgentService]);

  const doExportMarkdown = useCallback(() => {
    if (!previewContent || exportingFormat) return;
    setExportingFormat("md");
    try {
      const blob = new Blob([previewContent], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = sanitizeFileName((selected?.name ?? "法律文书") + ".md"); a.click();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch (e) { console.error("markdown 导出失败", e); } // 失败仅 console 不打扰（F5）
    setExportingFormat("");
  }, [previewContent, exportingFormat, selected]);

  const handleUploadFile = useCallback((file: File) => {
    setUploadError(null);
    const dotParts = file.name.split(".");
    const ext = dotParts.length > 1 ? ("." + (dotParts.pop() ?? "")).toLowerCase() : "";
    if (![".docx", ".doc", ".pdf", ".txt", ".md"].includes(ext)) {
      setUploadError("仅支持 .docx / .doc / .pdf / .txt / .md 模板文件。");
      return;
    }
    if (ext === ".pdf" || ext === ".doc") setUploadError("提示：PDF/DOC 需走 OCR 通道（当前未接入），建议先转换为 txt 或 md。");
    setUploadName(file.name);
    setUploadBusy(true);
    file.arrayBuffer()
      .then((buf) => zcodeAgentService.draftUploadTemplate?.({ fileName: file.name, base64: bytesToBase64(buf) }))
      .then((r) => {
        setUploadOpen(false);
        refreshCatalog();
        if (r?.template) pickTemplate({ source: "custom", id: r.template.id, name: r.template.name, fields: (r.template.fields as FieldDef[]) ?? [], learningStatus: (r.template.learningStatus as UserTemplateInfo["learningStatus"]) ?? "analyzing", hasSourceDocx: Boolean(r.template.hasSourceDocx) });
      })
      .catch((e: unknown) => setUploadError(String((e as Error)?.message ?? e)))
      .finally(() => setUploadBusy(false));
  }, [zcodeAgentService, refreshCatalog, pickTemplate]);

  const deleteTemplate = useCallback((id: string) => {
    if (deletingTplId) return; // 删除中禁重复点（B4）
    setDeletingTplId(id);
    zcodeAgentService.draftDeleteTemplate?.({ templateId: id })
      .then(() => {
        refreshCatalog();
        if (selected?.id === id) pickTemplate(null); // 当前选中模板被删 → 重置编辑器（C10）
      })
      .catch((e: unknown) => setFormError(String((e as Error)?.message ?? e)))
      .finally(() => setDeletingTplId(""));
  }, [zcodeAgentService, refreshCatalog, pickTemplate, selected]);

  const retryLearning = useCallback((id: string) => {
    zcodeAgentService.draftRetryLearning?.({ templateId: id })
      .then(() => refreshCatalog())
      .catch((e: unknown) => setFormError(String((e as Error)?.message ?? e)));
  }, [zcodeAgentService, refreshCatalog]);

  const restoreHistory = useCallback((id: string) => {
    if (historyBusyId) return;
    setHistoryBusyId(id);
    setHistoryError(null);
    zcodeAgentService.draftHistoryGet?.({ id })
      .then((r) => {
        const rec = r?.record;
        if (!rec) throw new Error("历史记录不存在");
        // 恢复：回填字段值/正文/指令；模板按名称匹配当前库，匹配不到仍回填（仅不选中模板）；清空材料（历史只存文件名）
        setCheckedMaterials([]);
        setPastedCase("");
        setFieldValues({ ...(rec.fieldValues ?? {}) });
        setPreviewContent(rec.generatedContent ?? "");
        const hitBuiltin = builtin.find((t) => t.name === rec.templateName);
        const hitCustom = userTemplates.find((t) => t.name === rec.templateName);
        if (hitBuiltin) setSelected({ source: "builtin", id: hitBuiltin.id, name: hitBuiltin.name, fields: hitBuiltin.fields, category: hitBuiltin.category });
        else if (hitCustom) setSelected({ source: "custom", id: hitCustom.id, name: hitCustom.name, fields: hitCustom.fields, learningStatus: hitCustom.learningStatus, hasSourceDocx: hitCustom.hasSourceDocx });
        else setSelected(null);
        setLeftTab("templates"); // 切回模板页签（G3）
        setMode(rec.generatedContent ? "preview" : "editing");
      })
      .catch((e: unknown) => setHistoryError(String((e as Error)?.message ?? e)))
      .finally(() => setHistoryBusyId(""));
  }, [historyBusyId, builtin, userTemplates, zcodeAgentService]);

  const deleteHistory = useCallback((id: string) => {
    if (historyBusyId) return;
    setHistoryBusyId(id); // 单删直删无确认（G4）
    setHistoryError(null);
    zcodeAgentService.draftHistoryDelete?.({ id })
      .then(() => refreshHistory())
      .catch((e: unknown) => setHistoryError(String((e as Error)?.message ?? e)))
      .finally(() => setHistoryBusyId(""));
  }, [historyBusyId, zcodeAgentService, refreshHistory]);

  const saveEdit = useCallback(() => {
    setPreviewContent(editDraft);
    setEditOpen(false);
  }, [editDraft]);

  // 上传弹窗 Esc 退出（上传中禁退，C1）
  useEffect(() => {
    if (!uploadOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !uploadBusy) setUploadOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [uploadOpen, uploadBusy]);

  // 编辑弹窗保存快捷键（Ctrl+S / Cmd+S）
  useEffect(() => {
    if (!editOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveEdit(); }
      if (e.key === "Escape") setEditOpen(false); // Esc 关闭不保存（I12）
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editOpen, saveEdit]);

  const fieldsToRender = useMemo(() => {
    if (!selected) return [];
    const all = [OUR_PARTY_FIELD, ...selected.fields]; // 我方主体置顶（D6）
    return showMoreFields || all.length <= MAX_VISIBLE_FIELDS ? all : all.slice(0, MAX_VISIBLE_FIELDS);
  }, [selected, showMoreFields]);

  const historyFiltered = useMemo(() => {
    const kw = historySearch.trim().toLowerCase();
    return historyRecords.filter((r) => !kw || r.templateName.toLowerCase().includes(kw));
  }, [historyRecords, historySearch]);

  const setStatusText = mode === "running"
    ? "生成中"
    : mode === "preview"
      ? (gen?.verdict === "partial" ? "草稿已保留（待核对）" : "已完成")
      : canGenerate ? "可以生成" : "需要补充";

  return (
    <section data-testid="legal-documents" className="rounded-workspace-panel border border-border bg-header p-4">
      <h2 className="mb-1 flex items-center gap-2 text-ui-lg font-medium">
        <FileEdit className="size-4" /> 文书起草（模板驱动）
      </h2>
      <p className="mb-3 text-ui-caption text-foreground-subtle">
        选模板 → 勾材料/贴案情 → 填字段 → 生成 → 预览导出。材料通道 = 工作区 materials 目录（#6 解析通道接入后可直接上传）。
      </p>
      {formError ? <p data-testid="doc-draft-form-error" className="mb-2 rounded border border-red-300 bg-red-50 px-2 py-1 text-ui-sm text-red-600 dark:border-red-800 dark:bg-red-950 dark:text-red-300">{formError}</p> : null}
      <div className="flex gap-3">
        {/* 左栏 */}
        <aside className="w-64 shrink-0 rounded border border-border bg-background p-2">
          <div className="mb-2 flex items-center gap-1">
            <button type="button" data-testid="doc-draft-tab-templates" onClick={() => setLeftTab("templates")}
              className={leftTab === "templates" ? "rounded bg-selected px-2 py-1 text-ui-sm" : "rounded px-2 py-1 text-ui-sm hover:bg-muted/60"}>
              模板库
            </button>
            <button type="button" data-testid="doc-draft-tab-history" onClick={() => setLeftTab("history")}
              className={leftTab === "history" ? "rounded bg-selected px-2 py-1 text-ui-sm" : "rounded px-2 py-1 text-ui-sm hover:bg-muted/60"}>
              历史
            </button>
            <span className="flex-1" />
            <button type="button" data-testid="doc-draft-upload-open" title="上传自定义模板"
              onClick={() => { setUploadOpen(true); setUploadError(null); setUploadName(""); }}
              className="rounded p-1 hover:bg-muted/60" aria-label="上传模板">
              <FileUp className="size-4" />
            </button>
          </div>
          {leftTab === "templates" ? (
            <>
              <div className="relative mb-2">
                <input data-testid="doc-draft-search" value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="搜索模板名称" className="h-7 w-full rounded border border-border bg-background pl-2 pr-7 text-ui-sm" />
                {search ? (
                  <button type="button" data-testid="doc-draft-search-clear" title="清空搜索" aria-label="清空搜索"
                    onClick={() => setSearch("")} className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-0.5 text-foreground-subtle hover:text-foreground">
                    <X className="size-3.5" />
                  </button>
                ) : null}
              </div>
              <div className="mb-2 flex gap-1 text-ui-caption">
                {([["all", "全部"], ["litigation", "诉讼"], ["non-litigation", "非诉"], ["custom", "我的"]] as const).map(([k, label]) => (
                  <button key={k} type="button" onClick={() => setCatTab(k)}
                    className={catTab === k ? "rounded bg-selected px-1.5 py-0.5" : "rounded px-1.5 py-0.5 hover:bg-muted/60"}>{label}</button>
                ))}
              </div>
              {catTab === "custom" && catalogLoading ? (
                <div data-testid="doc-draft-custom-loading" className="flex h-40 flex-col items-center justify-center gap-1 text-ui-caption text-foreground-subtle">
                  <Loader2 className="size-5 animate-spin text-blue-500" /> 正在加载我的模板…
                </div>
              ) : (
              <>
              <div className="grid max-h-96 grid-cols-2 gap-1.5 overflow-auto">
                {templateList.customs.map((t) => (
                  <div key={t.id} data-testid={"doc-draft-tpl-custom-" + t.id}
                    className={"group relative cursor-pointer rounded border p-2 " + (selected?.id === t.id ? "border-blue-500 bg-selected" : "border-border hover:bg-muted/40")}
                    onClick={() => pickTemplate({ source: "custom", id: t.id, name: t.name, fields: t.fields, learningStatus: t.learningStatus, hasSourceDocx: t.hasSourceDocx })}>
                    <FileText className="mb-1 size-4 text-foreground-subtle" />
                    <div className="line-clamp-2 text-ui-caption" title={t.name}>{t.name}</div>
                    <div className="mt-1 flex items-center gap-1 text-[10px]">
                      <span className="rounded bg-blue-100 px-1 text-blue-700 dark:bg-blue-950 dark:text-blue-300">自定义</span>
                      {t.learningStatus === "analyzing" ? <span className="flex items-center gap-0.5 text-foreground-subtle"><Loader2 className="size-3 animate-spin" />AI 分析中</span> : null}
                      {t.learningStatus === "failed" ? <span className="flex items-center gap-0.5 text-red-500" title={t.learningError}><TriangleAlert className="size-3" />AI 分析失败</span> : null}
                    </div>
                    {t.learningStatus === "failed" ? (
                      <button type="button" onClick={(e) => { e.stopPropagation(); retryLearning(t.id); }}
                        className="absolute bottom-1 right-1 rounded bg-red-50 px-1 text-[10px] text-red-600 dark:bg-red-950 dark:text-red-300">重试</button>
                    ) : null}
                    <button type="button" title="删除模板" disabled={deletingTplId === t.id}
                      onClick={(e) => { e.stopPropagation(); deleteTemplate(t.id); }}
                      className="absolute right-1 top-1 hidden rounded p-0.5 hover:bg-muted group-hover:block disabled:opacity-60">
                      {deletingTplId === t.id ? <Loader2 className="size-3 animate-spin" /> : <Trash2 className="size-3" />}
                    </button>
                  </div>
                ))}
                {templateList.builtins.map((t) => (
                  <div key={t.id} data-testid={"doc-draft-tpl-" + t.id}
                    className={"cursor-pointer rounded border p-2 " + (selected?.id === t.id ? "border-blue-500 bg-selected" : "border-border hover:bg-muted/40")}
                    onClick={() => pickTemplate({ source: "builtin", id: t.id, name: t.name, fields: t.fields, category: t.category })}
                    title={t.description}>
                    {t.category === "litigation" ? <Scale className="mb-1 size-4 text-foreground-subtle" /> : <BookOpen className="mb-1 size-4 text-foreground-subtle" />}
                    <div className="line-clamp-2 text-ui-caption" title={t.name}>{t.name}</div>
                  </div>
                ))}
              </div>
              {!templateList.customs.length && !templateList.builtins.length ? (
                <div className="p-3 text-center text-ui-caption text-foreground-subtle">
                  {catTab === "custom" ? "还没有自定义模板，点右上角上传。" : search ? "没有匹配的模板。" : "模板目录为空。"}
                </div>
              ) : null}
              </>
              )}
            </>
          ) : (
            <>
              <input data-testid="doc-draft-history-search" value={historySearch} onChange={(e) => setHistorySearch(e.target.value)}
                placeholder="按模板名搜索历史" className="mb-2 h-7 w-full rounded border border-border bg-background px-2 text-ui-sm" />
              {historyError ? <p className="mb-1 text-ui-caption text-red-500">{historyError}</p> : null}
              <div className="max-h-96 space-y-1 overflow-auto">
                {historyFiltered.map((r) => (
                  <div key={r.id} data-testid={"doc-draft-history-" + r.id}
                    className={"group relative cursor-pointer rounded border border-border p-2 hover:bg-muted/40 " + (historyBusyId === r.id ? "opacity-50" : "")}
                    onClick={() => restoreHistory(r.id)}>
                    <div className="line-clamp-1 text-ui-caption">{r.templateName}</div>
                    <div className="text-[10px] text-foreground-subtle">
                      {r.templateCategory} · 材料 {r.materialCount} 份{r.hasInstructions ? " · 有说明" : ""} · {new Date(r.createdAt).toLocaleString("zh-CN")}
                    </div>
                    <button type="button" title="删除该记录" onClick={(e) => { e.stopPropagation(); deleteHistory(r.id); }}
                      className="absolute right-1 top-1 hidden rounded p-0.5 hover:bg-muted group-hover:block">
                      {historyBusyId === r.id ? <Loader2 className="size-3 animate-spin" /> : <Trash2 className="size-3" />}
                    </button>
                  </div>
                ))}
                {!historyFiltered.length ? <div className="p-3 text-center text-ui-caption text-foreground-subtle">{historySearch ? "没有匹配的记录。" : "暂无生成历史。"}</div> : null}
              </div>
            </>
          )}
        </aside>
        {/* 中栏 */}
        <main className="min-w-0 flex-1 rounded border border-border bg-background p-3">
          {!selected ? (
            <div data-testid="doc-draft-empty" className="flex h-72 flex-col items-center justify-center gap-2 text-center">
              <FileText className="size-10 text-foreground-subtle" />
              <p className="text-ui-base">从左侧选择一个模板开始</p>
              <p className="text-ui-caption text-foreground-subtle">内置模板即选即用；也可上传自己的模板让 AI 学习字段。</p>
            </div>
          ) : mode === "preview" ? (
            <div data-testid="doc-draft-preview" className="flex h-[28rem] flex-col">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-ui-sm font-medium">{selected.name} · 预览</span>
                <span className="text-ui-caption text-foreground-subtle">模型生成稿，仅供起草参考；对外使用前须经律师审核。</span>
              </div>
              <div className="min-h-0 flex-1 overflow-auto rounded border border-border p-3">
                <MessageResponse className="w-full break-words text-foreground">{previewContent}</MessageResponse>
              </div>
              {gen?.verdict === "partial" ? (
                <p className="mt-1 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-ui-caption text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300">
                  {gen.notice || "已保留当前可用文书草稿，可继续编辑或重新生成。"}
                </p>
              ) : null}
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2 text-ui-sm">
                <span className="font-medium">{selected.name}</span>
                <span className="text-ui-caption text-foreground-subtle">{selected.fields.length + 1} 个字段 · {checkedMaterials.length} 份材料</span>
                <span className="flex-1" />
                <button type="button" onClick={() => pickTemplate(null)} className="rounded px-2 py-0.5 text-ui-caption text-foreground-subtle hover:text-foreground">新建</button>
              </div>
              <div className="rounded border border-border p-2">
                <div className="mb-1 text-ui-caption">案件材料（来自工作区 materials 目录）</div>
                {documents.length ? (
                  <div className="flex flex-wrap gap-1.5">
                    {documents.map((d) => (
                      <label key={d.name} className="flex cursor-pointer items-center gap-1 rounded border border-border px-2 py-0.5 text-ui-caption hover:bg-muted/40">
                        <input type="checkbox" checked={checkedMaterials.includes(d.name)}
                          onChange={(e) => setCheckedMaterials((prev) => e.target.checked ? [...prev, d.name] : prev.filter((n) => n !== d.name))} />
                        {d.name}
                      </label>
                    ))}
                  </div>
                ) : (
                  <p className="text-ui-caption text-foreground-subtle">materials 目录暂无文件（.txt/.md/.docx 可被读取；PDF 请先转换）。</p>
                )}
              </div>
              <div>
                <div className="mb-1 text-ui-caption">粘贴案情（可选，5000 字内；与上传材料择一即可，也可并用）</div>
                <textarea data-testid="doc-draft-paste" value={pastedCase} maxLength={5000}
                  onChange={(e) => setPastedCase(e.target.value)} rows={3}
                  className="w-full rounded border border-border bg-background p-2 text-ui-sm" />
              </div>
              <div>
                <div className="mb-1 flex items-center justify-between text-ui-caption">
                  <span>文书信息（已填 {filledCount}/{totalFields}）</span>
                  <span>{selected.fields.length + 1 > MAX_VISIBLE_FIELDS ? (showMoreFields ? "收起" : "展开其余 " + (selected.fields.length + 1 - MAX_VISIBLE_FIELDS) + " 项") : ""}</span>
                </div>
                <div className="mb-1 h-1 w-full overflow-hidden rounded bg-muted">
                  <div className="h-full bg-blue-500 transition-all" style={{ width: totalFields ? Math.round((filledCount / totalFields) * 100) + "%" : "0%" }} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {fieldsToRender.map((f) => (
                    <label key={f.id} className="flex flex-col gap-0.5 text-ui-caption">
                      <span title={f.id}>{f.label}{f.id === "我方主体" ? "（可留空）" : ""}</span>
                      {f.type === "textarea" ? (
                        <textarea value={fieldValues[f.id] ?? ""} rows={2} placeholder={f.placeholder ?? ""}
                          onChange={(e) => setFieldValues((prev) => ({ ...prev, [f.id]: e.target.value }))}
                          className="rounded border border-border bg-background p-1.5 text-ui-sm" />
                      ) : f.type === "date" ? (
                        <input type="date" value={fieldValues[f.id] ?? ""} placeholder={f.placeholder ?? ""}
                          onChange={(e) => setFieldValues((prev) => ({ ...prev, [f.id]: e.target.value }))}
                          className="rounded border border-border bg-background p-1.5 text-ui-sm" />
                      ) : f.type === "select" && f.options?.length ? (
                        <select value={fieldValues[f.id] ?? ""} onChange={(e) => setFieldValues((prev) => ({ ...prev, [f.id]: e.target.value }))}
                          className="rounded border border-border bg-background p-1.5 text-ui-sm">
                          <option value="">（请选择）</option>
                          {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                        </select>
                      ) : (
                        <input type="text" value={fieldValues[f.id] ?? ""} placeholder={f.placeholder ?? ""}
                          onChange={(e) => setFieldValues((prev) => ({ ...prev, [f.id]: e.target.value }))}
                          className="rounded border border-border bg-background p-1.5 text-ui-sm" />
                      )}
                    </label>
                  ))}
                </div>
                {selected.fields.length + 1 > MAX_VISIBLE_FIELDS ? (
                  <button type="button" onClick={() => setShowMoreFields((v) => !v)}
                    className="mt-1 rounded px-2 py-0.5 text-ui-caption text-blue-600 hover:underline dark:text-blue-400">
                    {showMoreFields ? "收起字段" : "展开其余 " + (selected.fields.length + 1 - MAX_VISIBLE_FIELDS) + " 项"}
                  </button>
                ) : null}
              </div>
            </div>
          )}
        </main>
        {/* 右栏 */}
        <aside className="w-60 shrink-0 rounded border border-border bg-background p-2">
          {mode !== "preview" ? (
            <>
              <div className="mb-2 text-ui-caption font-medium">就绪情况</div>
              <ul className="mb-2 space-y-0.5 text-ui-caption text-foreground-subtle">
                <li>材料：{checkedMaterials.length} 份已勾选</li>
                <li>已填信息：{filledCount}/{totalFields || "—"} 项</li>
                <li>
                  状态：
                  <span data-testid="doc-draft-ready" className={mode === "running" ? "text-blue-500" : canGenerate ? "text-emerald-500" : "text-amber-500"}>{setStatusText}</span>
                </li>
              </ul>
              <button type="button" data-testid="doc-draft-generate" onClick={runGenerate} disabled={mode === "running"}
                className="flex w-full items-center justify-center gap-1 rounded bg-blue-600 px-3 py-1.5 text-ui-sm text-white hover:bg-blue-500 disabled:opacity-50">
                {mode === "running" ? <Loader2 className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
                {mode === "running" ? "生成中…" : "生成文书"}
              </button>
              <p className="mt-1 text-[10px] text-foreground-subtle">不选模板也可生成（起诉/答辩将自动匹配内置结构模板）。</p>
            </>
          ) : (
            <div className="flex flex-col gap-1.5">
              <div className="mb-1 text-ui-caption font-medium">导出与编辑</div>
              <button type="button" data-testid="doc-draft-export-word" onClick={doExportWord} disabled={exportingFormat !== ""}
                className="flex items-center justify-center gap-1 rounded border border-border px-2 py-1 text-ui-sm hover:bg-muted/60 disabled:opacity-50">
                {exportingFormat === "docx" ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />} 导出 Word
              </button>
              {selected?.source === "custom" && selected.hasSourceDocx ? (
                <p className="text-[10px] text-foreground-subtle">已保留原 DOCX：导出将原位写入副本，保留版式。</p>
              ) : null}
              <button type="button" data-testid="doc-draft-export-md" onClick={doExportMarkdown} disabled={exportingFormat !== ""}
                className="flex items-center justify-center gap-1 rounded border border-border px-2 py-1 text-ui-sm hover:bg-muted/60 disabled:opacity-50">
                {exportingFormat === "md" ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />} 导出 Markdown
              </button>
              <button type="button" data-testid="doc-draft-edit-open" onClick={() => { setEditDraft(previewContent); setEditView("visual"); setEditOpen(true); }}
                className="flex items-center justify-center gap-1 rounded border border-border px-2 py-1 text-ui-sm hover:bg-muted/60">
                <FileEdit className="size-3.5" /> 编辑文书
              </button>
              <button type="button" data-testid="doc-draft-back-edit"
                onClick={() => { setMode("editing"); setGen(null); }}
                className="flex items-center justify-center gap-1 rounded border border-border px-2 py-1 text-ui-sm hover:bg-muted/60">
                返回修改信息
              </button>
              {feedback ? (
                <p className={"rounded px-2 py-1 text-ui-caption " + (feedback.kind === "ok" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" : "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-300")}>
                  {feedback.text}
                </p>
              ) : null}
            </div>
          )}
        </aside>
      </div>
      {/* 五阶段工作流浮窗（右下） */}
      {floatVisible && mode !== "editing" ? (
        floatMinimized ? (
          <button type="button" data-testid="doc-draft-float-pill" onClick={() => setFloatMinimized(false)}
            className="fixed bottom-4 right-4 z-40 flex items-center gap-1 rounded-full border border-border bg-background px-3 py-1.5 text-ui-caption shadow-lg">
            {mode === "running" ? <Loader2 className="size-3.5 animate-spin text-blue-500" /> : gen?.verdict === "partial" ? <TriangleAlert className="size-3.5 text-amber-500" /> : <CheckCircle2 className="size-3.5 text-emerald-500" />}
            {mode === "running" ? "文书生成中…" : gen?.verdict === "partial" ? "已保留草稿" : "已完成"}
          </button>
        ) : (
          <div data-testid="doc-draft-float" className="fixed bottom-4 right-4 z-40 w-72 rounded-lg border border-border bg-background p-3 shadow-xl">
            <div className="mb-2 flex items-center gap-1 text-ui-caption font-medium">
              {mode === "running" ? <Loader2 className="size-3.5 animate-spin text-blue-500" /> : <CheckCircle2 className="size-3.5 text-emerald-500" />}
              工作流 · {gen?.lastTool || (mode === "running" ? "进行中" : "已结束")}
              <span className="flex-1" />
              <button type="button" title="最小化" onClick={() => setFloatMinimized(true)} className="rounded p-0.5 hover:bg-muted"><Minimize2 className="size-3.5" /></button>
              <button type="button" title="关闭" onClick={() => setFloatVisible(false)} className="rounded p-0.5 hover:bg-muted"><X className="size-3.5" /></button>
            </div>
            <ol className="mb-2 space-y-1">
              {STAGE_LABELS.map((s) => (
                <li key={s.key} data-testid={"doc-draft-stage-" + s.key} className="flex items-center gap-1.5 text-ui-caption">
                  <StageGlyph state={gen?.stages?.[s.key] ?? "pending"} />
                  {s.key === "materials" && gen?.materialCount ? s.label + "（" + gen.materialCount + " 份）" : s.label}
                </li>
              ))}
            </ol>
            {mode === "running" ? (
              <div>
                <div className="flex gap-1">
                  <input data-testid="doc-draft-steer-input" value={steerText} onChange={(e) => setSteerText(e.target.value)}
                    placeholder="中途引导：补充要求发给生成中的模型" className="h-7 min-w-0 flex-1 rounded border border-border bg-background px-2 text-ui-caption" />
                  <button type="button" data-testid="doc-draft-steer-send" onClick={sendSteer} className="rounded border border-border px-2 text-ui-caption hover:bg-muted/60">发送</button>
                </div>
                {steerMsg ? <p className="mt-1 text-[10px] text-foreground-subtle">{steerMsg}</p> : null}
              </div>
            ) : (
              <p className="text-[10px] text-foreground-subtle">
                {gen?.status === "error" ? "生成失败：" + (gen.error || "未知错误") : gen?.verdict === "partial" ? "已保留当前可用草稿，可继续编辑或重新生成。" : "生成完成，可在预览区查看与导出。"}
              </p>
            )}
          </div>
        )
      ) : null}
      {/* 上传弹窗 */}
      {uploadOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => { if (!uploadBusy) setUploadOpen(false); }}>
          <div className="w-96 rounded-lg border border-border bg-background p-4 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center gap-1 text-ui-sm font-medium">
              <Upload className="size-4" /> 上传自定义模板
              <span className="flex-1" />
              <button type="button" data-testid="doc-draft-upload-close" onClick={() => { if (!uploadBusy) setUploadOpen(false); }} className="rounded p-0.5 hover:bg-muted"><X className="size-4" /></button>
            </div>
            <div
              data-testid="doc-draft-upload-drop"
              className="mb-2 flex h-28 cursor-pointer flex-col items-center justify-center gap-1 rounded border-2 border-dashed border-border text-ui-caption text-foreground-subtle hover:bg-muted/40"
              onClick={() => document.getElementById("doc-draft-upload-file")?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); if (!uploadBusy && e.dataTransfer.files[0]) void handleUploadFile(e.dataTransfer.files[0]); }}
            >
              <FileUp className="size-6" />
              <span>拖拽文件到此处，或点击选择</span>
              <span className="text-[10px]">支持 .docx / .doc / .pdf / .txt / .md；PDF/DOC 走 OCR 通道（需耐心）</span>
            </div>
            <input id="doc-draft-upload-file" type="file" accept=".docx,.doc,.pdf,.txt,.md" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleUploadFile(f); e.target.value = ""; }} />
            {uploadBusy ? (
              <p className="flex items-center gap-1 text-ui-caption text-blue-500"><Loader2 className="size-3.5 animate-spin" /> 正在读取并分析「{uploadName}」…</p>
            ) : null}
            {uploadError ? <p data-testid="doc-draft-upload-error" className="rounded bg-red-50 px-2 py-1 text-ui-caption text-red-600 dark:bg-red-950 dark:text-red-300">{uploadError}</p> : null}
          </div>
        </div>
      ) : null}
      {/* 编辑文书弹窗 */}
      {editOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="flex h-[32rem] w-[44rem] flex-col rounded-lg border border-border bg-background p-3 shadow-xl">
            <div className="mb-2 flex items-center gap-1 text-ui-sm font-medium">
              编辑文书
              <span className="ml-2 flex gap-1 text-ui-caption">
                <button type="button" data-testid="doc-draft-edit-view-visual" onClick={() => setEditView("visual")}
                  className={editView === "visual" ? "rounded bg-selected px-2 py-0.5" : "rounded px-2 py-0.5 hover:bg-muted/60"}>可视化</button>
                <button type="button" data-testid="doc-draft-edit-view-source" onClick={() => setEditView("source")}
                  className={editView === "source" ? "rounded bg-selected px-2 py-0.5" : "rounded px-2 py-0.5 hover:bg-muted/60"}>源码</button>
              </span>
              <span className="text-ui-caption text-foreground-subtle">Esc 关闭不保存</span>
              <span className="flex-1" />
              <span className="flex-1" />
              <button type="button" data-testid="doc-draft-edit-cancel" onClick={() => setEditOpen(false)} className="rounded p-0.5 hover:bg-muted"><X className="size-4" /></button>
            </div>
            {editView === "visual" ? (
              <div data-testid="doc-draft-edit-visual" className="min-h-0 flex-1 overflow-auto rounded border border-border p-2">
                <MessageResponse className="w-full break-words text-foreground">{editDraft}</MessageResponse>
              </div>
            ) : (
              <textarea data-testid="doc-draft-edit-area" value={editDraft} onChange={(e) => setEditDraft(e.target.value)}
                className="min-h-0 flex-1 resize-none rounded border border-border bg-background p-2 font-mono text-ui-sm" />
            )}
            <div className="mt-2 flex justify-end gap-2">
              <button type="button" onClick={() => setEditOpen(false)} className="rounded border border-border px-3 py-1 text-ui-sm hover:bg-muted/60">取消</button>
              <button type="button" data-testid="doc-draft-edit-save" onClick={saveEdit} className="rounded bg-blue-600 px-3 py-1 text-ui-sm text-white hover:bg-blue-500">保存（Ctrl+S）</button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
