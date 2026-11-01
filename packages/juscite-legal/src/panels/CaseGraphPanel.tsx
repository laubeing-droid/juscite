// 功能 #19 轻量知识图谱（步骤4·RE-19 等量裁剪版）：案件人物/证据关系一屏。
// 单图单轨（无提案二轨/无多视图/无 MiniMap，RE-19 §3/§5 裁剪边界）：
//   建图两入口=①从案件数据一键建图（预览确认后才写入，对拍 #2）②手工表单确定性录入（禁拖拽建边）；
//   编辑自动锁定（对拍 #20）；模糊日期只走文字描述不造日期（对拍 #21 fail-closed）；
//   拖拽位置随保存落盘（对拍 #14）；撤销/重做内存栈 50（对拍 #25）；保存三态+防重入（对拍 #23）；
//   未保存 beforeunload 拦截（对拍 #24）；乐观锁冲突提示刷新（对拍 #26）；导出 PNG+JSON、
//   导出前自动保存+文件名净化（对拍 #28/#29）；服务端全量校验为唯一写闸（对拍 #30/#31/#32/#38）。
// 文案全部自写（表达隔离）；无右键菜单/无键盘快捷键（对拍 #39 对齐缺席）。
import { Component, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  FileText, ImageDown, Braces, Lock, LockOpen, Maximize, Network,
  RotateCw, Trash2, Undo2, Redo2, X, ZoomIn, ZoomOut,
} from "lucide-react";
import { useServices } from "../ui-kit.js";
import {
  EDGE_KINDS, EDGE_KIND_LABEL, GRAPH_STATUSES, LIMITS, NODE_KINDS, NODE_KIND_LABEL,
  STATUS_COLOR, STATUS_DASHED, STATUS_LABEL, layoutGraph, sanitizeGraphFilename,
  type GEdge, type GNode, type GraphDoc, type GraphStatus, type NodeKind, type EdgeKind,
} from "../kernel/caseGraphModel.js";
import { ConfrontationSection } from "./ConfrontationSection.js";

const CASE_ID = "default"; // 工作区单案占位 id（MatterLite/#3 落地后换真实案件 id，桥按 workspace+caseId 分键）
const NODE_W = 220;
const NODE_H = 84;
const DISCLIAMER = "本图由系统辅助整理、律师人工核对生成，仅供办案参考；未经复核不得作为确定事实或对外材料。";

type GraphSnapshot = { title: string; nodes: GNode[]; edges: GEdge[] };
type Selection = { kind: "node" | "edge"; id: string } | null;
type BuildPreview = {
  caseId: string; available: boolean; partiesCount: number; materialsCount: number; note: string;
  proposal: { title: string; nodes: GNode[]; edges: GEdge[]; config: GraphDoc["config"]; layout: GraphDoc["layout"] };
};
type SourcePreview = { name: string; text: string; truncated: boolean };

function emptyDoc(title: string): GraphDoc {
  return { schemaVersion: 1, title, nodes: [], edges: [], config: { direction: "TB", edgeLabels: true }, layout: { positions: {} }, updatedAt: "" };
}
function cloneSnapshot(doc: GraphDoc): GraphSnapshot {
  return { title: doc.title, nodes: JSON.parse(JSON.stringify(doc.nodes)), edges: JSON.parse(JSON.stringify(doc.edges)) };
}

/** 渲染错误就地降级+重试；不上报遥测、不发送案件内容（对拍 #34）。 */
class CaseGraphBoundary extends Component<{ children: ReactNode }, { err: Error | null }> {
  state = { err: null as Error | null };
  static getDerivedStateFromError(err: Error) { return { err }; }
  componentDidCatch() { /* 刻意留空：不外发任何内容 */ }
  render() {
    if (this.state.err) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-2 text-ui-sm text-foreground-subtle">
          <span>该图暂时无法渲染；图数据仍安全保留，未受影响。</span>
          <button type="button" className="rounded border border-border px-3 py-1 hover:bg-muted/60" onClick={() => this.setState({ err: null })}>
            重试渲染
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function CaseGraphPanel({ workspacePath }: { workspacePath?: string }) {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as {
    caseGraphGet?: (p: { workspacePath: string; caseId: string }) => Promise<
      | { exists: false; caseId: string }
      | { exists: true; caseId: string; revision: number; graph: unknown; updatedAt: number }>;
    caseGraphSave?: (p: { workspacePath: string; caseId: string; baseRevision: number; graph: unknown }) =>
      Promise<{ caseId: string; revision: number; updatedAt: string; nodeCount: number; edgeCount: number }>;
    caseGraphBuildPreview?: (p: { workspacePath: string; caseId: string }) => Promise<BuildPreview>;
    caseGraphClear?: (p: { workspacePath: string; caseId: string; baseRevision: number }) => Promise<{ cleared: boolean; caseId: string }>;
    caseGraphReadSource?: (p: { workspacePath: string; filename: string }) => Promise<SourcePreview>;
    listWorkspaceDocuments?: (p: { workspacePath: string }) => Promise<{ documents: Array<{ name: string; kind: string }> }>;
  };

  const [phase, setPhase] = useState<"loading" | "ready" | "error">("loading");
  const [exists, setExists] = useState(false);
  const [revision, setRevision] = useState(0);
  const [doc, setDoc] = useState<GraphDoc | null>(null);
  const [past, setPast] = useState<GraphSnapshot[]>([]);
  const [future, setFuture] = useState<GraphSnapshot[]>([]);
  const [semanticDirty, setSemanticDirty] = useState(false);
  const [layoutDirty, setLayoutDirty] = useState(false);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [banner, setBanner] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [receipt, setReceipt] = useState<string | null>(null);
  const [sel, setSel] = useState<Selection>(null);
  const [base, setBase] = useState<{ positions: Record<string, { x: number; y: number }>; width: number; height: number } | null>(null);
  const [layoutState, setLayoutState] = useState<"idle" | "pending" | "error">("idle");
  const [layoutError, setLayoutError] = useState("");
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const [preview, setPreview] = useState<BuildPreview | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [sourcePreview, setSourcePreview] = useState<SourcePreview | null>(null);
  const [materials, setMaterials] = useState<Array<{ name: string; kind: string }>>([]);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const fitDoneRef = useRef(false);
  const dragRef = useRef<{ id: string; startX: number; startY: number; origX: number; origY: number; moved: boolean } | null>(null);
  const panRef = useRef<{ x: number; y: number; vx: number; vy: number; moved: boolean } | null>(null);
  const exportLockRef = useRef(false);

  const dirty = semanticDirty || layoutDirty;

  // ── 读取（exists:false 是正常态，不是错误）──
  const reload = useCallback(async () => {
    setPhase("loading"); setBanner(null); setConflict(false); setSel(null);
    setPast([]); setFuture([]); setSemanticDirty(false); setLayoutDirty(false);
    setPreview(null); fitDoneRef.current = false;
    try {
      const r = await svc.caseGraphGet?.({ workspacePath: workspacePath ?? "", caseId: CASE_ID });
      if (!r) throw new Error("桥未提供关系图通道");
      if (!r.exists) { setExists(false); setDoc(null); setRevision(0); setPhase("ready"); return; }
      const g = r.graph as GraphDoc;
      setExists(true); setRevision(r.revision);
      setDoc({
        schemaVersion: 1, title: String(g.title ?? ""), nodes: g.nodes ?? [], edges: g.edges ?? [],
        config: { direction: g.config?.direction === "LR" ? "LR" : "TB", edgeLabels: g.config?.edgeLabels !== false },
        layout: { positions: g.layout?.positions ?? {} }, updatedAt: String(g.updatedAt ?? ""),
      });
      setPhase("ready");
    } catch (e) {
      setBanner(String((e as Error)?.message ?? e)); setPhase("error");
    }
  }, [svc, workspacePath]);
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => {
    svc.listWorkspaceDocuments?.({ workspacePath: workspacePath ?? "" })
      .then((r) => setMaterials(r?.documents ?? []))
      .catch(() => {});
  }, [svc, workspacePath]);

  // ── 布局：确定性分层纯函数；换结构/方向/重新布局后重算（对拍 #12/#13）──
  const layoutKey = doc ? `${doc.nodes.map((n) => n.id).join(",")}|${doc.edges.map((e) => `${e.source}>${e.target}`).join(",")}|${doc.config.direction}` : "";
  useEffect(() => {
    if (!doc) { setBase(null); return; }
    // 确定性分层 ≤100 节点为亚毫秒级纯函数：同步计算（rAF 在遮挡/后台窗口会被 Chrome 暂停，
    // 曾实测导致布局永不落、节点全叠 (0,0)——不得依赖帧回调做必要计算）。
    setLayoutState("pending");
    try {
      const r = layoutGraph(doc.nodes, doc.edges, doc.config.direction);
      setBase(r);
      setLayoutState("idle");
      if (!fitDoneRef.current && containerRef.current) {
        fitDoneRef.current = true;
        const rect = containerRef.current.getBoundingClientRect();
        const scale = Math.max(0.25, Math.min((rect.width - 48) / r.width, (rect.height - 48) / r.height, 1.25));
        setView({ x: (rect.width - r.width * scale) / 2, y: (rect.height - r.height * scale) / 2, scale });
      }
    } catch (e) {
      setLayoutState("error"); setLayoutError(String((e as Error)?.message ?? e));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutKey]);

  const posOf = useCallback((id: string): { x: number; y: number } =>
    doc?.layout.positions[id] ?? base?.positions[id] ?? { x: 0, y: 0 }, [doc, base]);

  // ── 撤销/重做（仅语义变更入栈，布局调整不入；栈深 50，空栈禁用）──
  const pushUndo = useCallback(() => {
    if (!doc) return;
    setPast((p) => [...p.slice(-49), cloneSnapshot(doc)]);
    setFuture([]);
  }, [doc]);
  const applySnapshot = useCallback((s: GraphSnapshot) => {
    setDoc((d) => (d ? { ...d, title: s.title, nodes: s.nodes, edges: s.edges } : d));
    setSemanticDirty(true);
  }, []);
  const undo = useCallback(() => {
    setPast((p) => {
      if (!p.length || !doc) return p;
      const prev = p[p.length - 1]!;
      setFuture((f) => [...f.slice(-49), cloneSnapshot(doc)]);
      applySnapshot(prev);
      return p.slice(0, -1);
    });
  }, [doc, applySnapshot]);
  const redo = useCallback(() => {
    setFuture((f) => {
      if (!f.length || !doc) return f;
      const next = f[f.length - 1]!;
      setPast((p) => [...p.slice(-49), cloneSnapshot(doc)]);
      applySnapshot(next);
      return f.slice(0, -1);
    });
  }, [doc, applySnapshot]);

  // ── 结构编辑（全部确定性表单录入；节点编辑自动锁定 provenance→user + 字段入 lockedFields）──
  const mutate = useCallback((fn: (d: GraphDoc) => GraphDoc, semantic: boolean) => {
    setDoc((d) => (d ? fn(d) : d));
    if (semantic) setSemanticDirty(true);
  }, []);
  const addNode = useCallback((kind: NodeKind, label: string) => {
    const text = label.trim();
    if (!text || !doc) return;
    pushUndo();
    mutate((d) => ({
      ...d,
      nodes: [...d.nodes, {
        id: `n-${crypto.randomUUID().slice(0, 8)}`, kind, label: text.slice(0, LIMITS.label),
        status: "uncertain" as GraphStatus, sourceRefs: [], provenance: "user" as const, lockedFields: [],
      }],
    }), true);
  }, [doc, mutate, pushUndo]);
  const patchNode = useCallback((id: string, patch: Partial<GNode>) => {
    pushUndo();
    mutate((d) => ({
      ...d,
      nodes: d.nodes.map((n) => n.id === id ? {
        ...n, ...patch,
        provenance: "user" as const,
        lockedFields: [...new Set([...n.lockedFields, ...Object.keys(patch)])],
      } : n),
    }), true);
  }, [mutate, pushUndo]);
  const toggleNodeLock = useCallback((id: string, field: string) => {
    pushUndo();
    mutate((d) => ({
      ...d,
      nodes: d.nodes.map((n) => n.id === id ? {
        ...n, provenance: "user" as const,
        lockedFields: n.lockedFields.includes(field) ? n.lockedFields.filter((f) => f !== field) : [...n.lockedFields, field],
      } : n),
    }), true);
  }, [mutate, pushUndo]);
  const removeNode = useCallback((id: string) => {
    // 人工删除：节点+全部相连边连带删（对拍 #19 用户路径；自动改动守卫在桥/模型层 removeNodeCascade actor=ai）
    pushUndo();
    mutate((d) => ({
      ...d,
      nodes: d.nodes.filter((n) => n.id !== id),
      edges: d.edges.filter((e) => e.source !== id && e.target !== id),
      layout: { positions: Object.fromEntries(Object.entries(d.layout.positions).filter(([k]) => k !== id)) },
    }), true);
    setSel(null);
  }, [mutate, pushUndo]);
  const addEdge = useCallback((source: string, target: string, kind: EdgeKind, label: string) => {
    if (!doc || !source || !target) return;
    pushUndo();
    mutate((d) => ({
      ...d,
      edges: [...d.edges, {
        id: `e-${crypto.randomUUID().slice(0, 8)}`, source, target, kind,
        label: label.trim() ? label.trim().slice(0, LIMITS.edgeLabel) : undefined,
        status: "uncertain" as GraphStatus, sourceRefs: [], provenance: "user" as const, lockedFields: [],
      }],
    }), true);
  }, [doc, mutate, pushUndo]);
  const patchEdge = useCallback((id: string, patch: Partial<GEdge>) => {
    pushUndo();
    mutate((d) => ({
      ...d,
      edges: d.edges.map((e) => e.id === id ? {
        ...e, ...patch,
        provenance: "user" as const,
        lockedFields: [...new Set([...e.lockedFields, ...Object.keys(patch)])],
      } : e),
    }), true);
  }, [mutate, pushUndo]);
  const removeEdge = useCallback((id: string) => {
    pushUndo();
    mutate((d) => ({ ...d, edges: d.edges.filter((e) => e.id !== id) }), true);
    setSel(null);
  }, [mutate, pushUndo]);
  const renameTitle = useCallback((title: string) => {
    pushUndo();
    mutate((d) => ({ ...d, title: title.slice(0, LIMITS.title) }), true);
  }, [mutate, pushUndo]);
  const setDirection = useCallback((direction: "TB" | "LR") => {
    mutate((d) => ({ ...d, config: { ...d.config, direction }, layout: { positions: {} } }), false);
    setLayoutDirty(true); // 方向属展示配置：随保存落盘，不入语义撤销栈
  }, [mutate]);

  // ── 拖拽（位置记忆；随保存落盘）与画布平移/缩放 ──
  const onNodePointerDown = useCallback((e: React.PointerEvent, node: GNode) => {
    e.stopPropagation();
    if (panRef.current) return;
    const p = posOf(node.id);
    dragRef.current = { id: node.id, startX: e.clientX, startY: e.clientY, origX: p.x, origY: p.y, moved: false };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setSel({ kind: "node", id: node.id });
  }, [posOf]);
  const onNodePointerMove = useCallback((e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d || !doc) return;
    const dx = (e.clientX - d.startX) / view.scale;
    const dy = (e.clientY - d.startY) / view.scale;
    if (Math.abs(dx) + Math.abs(dy) > 2) d.moved = true;
    if (!d.moved) return;
    const x = Math.max(0, Math.round(d.origX + dx));
    const y = Math.max(0, Math.round(d.origY + dy));
    mutate((g) => ({ ...g, layout: { positions: { ...g.layout.positions, [d.id]: { x, y } } } }), false);
    setLayoutDirty(true);
  }, [doc, mutate, view.scale]);
  const onNodePointerUp = useCallback(() => { dragRef.current = null; }, []);
  const onBackgroundPointerDown = useCallback((e: React.PointerEvent) => {
    if (dragRef.current) return;
    if ((e.target as Element).closest?.("button")) return; // 画布内控制条按钮（放大/缩小/适合窗口）：指针不收给容器，click 才能落到按钮（对拍 #16）
    panRef.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }, [view]);
  const onBackgroundPointerMove = useCallback((e: React.PointerEvent) => {
    const p = panRef.current;
    if (!p) return;
    const dx = e.clientX - p.x, dy = e.clientY - p.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) p.moved = true;
    setView((v) => ({ ...v, x: p.vx + dx, y: p.vy + dy }));
  }, []);
  const onBackgroundPointerUp = useCallback(() => {
    const p = panRef.current;
    panRef.current = null;
    if (p && !p.moved) setSel(null); // 点击空白处取消选中
  }, []);
  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const mx = e.clientX - rect.x, my = e.clientY - rect.y;
    setView((v) => {
      const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      const scale = Math.max(0.25, Math.min(1.8, v.scale * factor));
      return { scale, x: mx - ((mx - v.x) * scale) / v.scale, y: my - ((my - v.y) * scale) / v.scale };
    });
  }, []);
  const fitView = useCallback(() => {
    if (!base || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const scale = Math.max(0.25, Math.min((rect.width - 48) / base.width, (rect.height - 48) / base.height, 1.25));
    setView({ x: (rect.width - base.width * scale) / 2, y: (rect.height - base.height * scale) / 2, scale });
  }, [base]);

  // ── 保存（三态+防重入+乐观锁；冲突提示刷新）──
  const save = useCallback(async (): Promise<boolean> => {
    if (!doc || saveState === "saving" || !dirty) return false;
    setSaveState("saving"); setBanner(null); setConflict(false);
    try {
      const r = await svc.caseGraphSave?.({
        workspacePath: workspacePath ?? "", caseId: CASE_ID, baseRevision: revision, graph: doc,
      });
      if (!r) throw new Error("桥未提供关系图保存通道");
      setRevision(r.revision);
      setDoc((d) => (d ? { ...d, updatedAt: r.updatedAt } : d));
      setSemanticDirty(false); setLayoutDirty(false);
      setSaveState("saved");
      setReceipt(`已保存：修订 ${r.revision} · 节点 ${r.nodeCount} · 关系 ${r.edgeCount}`);
      window.setTimeout(() => setSaveState((s) => (s === "saved" ? "idle" : s)), 1500);
      return true;
    } catch (e) {
      const msg = String((e as Error)?.message ?? e);
      setBanner(msg);
      setConflict(msg.includes("修订冲突"));
      setSaveState("idle");
      return false;
    }
  }, [doc, dirty, revision, saveState, svc, workspacePath]);

  // ── 建图（预览确认制：未确认不写入；确认点击即授权；回执=真实写入结果）──
  const runPreview = useCallback(async () => {
    setPreviewBusy(true); setBanner(null);
    try {
      const r = await svc.caseGraphBuildPreview?.({ workspacePath: workspacePath ?? "", caseId: CASE_ID });
      if (!r) throw new Error("桥未提供建图预览通道");
      setPreview(r);
      if (!r.available) setBanner(`案件数据中暂无可建图记录（当事人 ${r.partiesCount} 名、材料 ${r.materialsCount} 份）`);
    } catch (e) {
      setBanner(String((e as Error)?.message ?? e));
    } finally { setPreviewBusy(false); }
  }, [svc, workspacePath]);
  const confirmBuild = useCallback(async () => {
    if (!preview?.available) return;
    setPreviewBusy(true); setBanner(null);
    try {
      const r = await svc.caseGraphSave?.({
        workspacePath: workspacePath ?? "", caseId: CASE_ID, baseRevision: revision, graph: preview.proposal,
      });
      if (!r) throw new Error("桥未提供关系图保存通道");
      setPreview(null);
      setReceipt(`建图完成：节点 ${r.nodeCount} · 关系 ${r.edgeCount}，已存为修订 ${r.revision}`);
      await reload();
    } catch (e) {
      setBanner(String((e as Error)?.message ?? e));
    } finally { setPreviewBusy(false); }
  }, [preview, revision, reload, svc, workspacePath]);
  const newEmpty = useCallback(() => {
    setDoc(emptyDoc("未命名关系图")); setExists(true); setRevision(revision);
    setSemanticDirty(true); setPreview(null);
  }, [revision]);
  const clearGraph = useCallback(async () => {
    if (!window.confirm("确定清空整张关系图吗？清空后可在保存前用撤销恢复，保存后不可恢复。")) return;
    try {
      await svc.caseGraphClear?.({ workspacePath: workspacePath ?? "", caseId: CASE_ID, baseRevision: revision });
      setDoc(null); setExists(false); setRevision(0);
      setPast([]); setFuture([]); setSemanticDirty(false); setLayoutDirty(false); setSel(null);
      setReceipt("已清空关系图");
    } catch (e) {
      setBanner(String((e as Error)?.message ?? e));
    }
  }, [revision, svc, workspacePath]);

  // ── 导出（导出前自动保存；文件名净化；PNG 白底+页脚免责句）──
  const exportPng = useCallback(async () => {
    if (!doc || !base || exportLockRef.current) return;
    exportLockRef.current = true;
    try {
      if (dirty && !(await save())) return;
      const positions: Record<string, { x: number; y: number }> = {};
      for (const n of doc.nodes) positions[n.id] = doc.layout.positions[n.id] ?? base.positions[n.id] ?? { x: 0, y: 0 };
      const W = Math.max(base.width, 720), H = Math.max(base.height + 64, 420);
      const scale = 2;
      const canvas = document.createElement("canvas");
      canvas.width = W * scale; canvas.height = H * scale;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("画布不可用，导出失败");
      ctx.scale(scale, scale);
      ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = "#111827"; ctx.font = "600 18px system-ui, sans-serif";
      ctx.fillText(doc.title || "关系图", 24, 30);
      ctx.fillStyle = "#6b7280"; ctx.font = "12px system-ui, sans-serif";
      ctx.fillText(`修订 ${revision} · 节点 ${doc.nodes.length} · 关系 ${doc.edges.length} · ${new Date().toLocaleString("zh-CN")}`, 24, 50);
      const center = (id: string) => { const q = positions[id] ?? { x: 0, y: 0 }; return { x: q.x + NODE_W / 2, y: q.y + NODE_H / 2 }; };
      for (const e of doc.edges) {
        const s = center(e.source), t = center(e.target);
        const color = STATUS_COLOR[e.status];
        ctx.strokeStyle = color; ctx.lineWidth = 1.6;
        ctx.setLineDash(STATUS_DASHED[e.status] ? [7, 5] : []);
        const dx = t.x - s.x, dy = t.y - s.y;
        // 折线顶点序：尾出边 → 拐点 → 入边；箭头角度取最后一段方向
        const pts: Array<{ x: number; y: number }> = [];
        if (Math.abs(dx) >= Math.abs(dy)) {
          const midX = (s.x + t.x) / 2;
          pts.push({ x: s.x + Math.sign(dx || 1) * (NODE_W / 2), y: s.y }, { x: midX, y: s.y }, { x: midX, y: t.y }, { x: t.x - Math.sign(dx || 1) * (NODE_W / 2), y: t.y });
        } else {
          const midY = (s.y + t.y) / 2;
          pts.push({ x: s.x, y: s.y + Math.sign(dy || 1) * (NODE_H / 2) }, { x: s.x, y: midY }, { x: t.x, y: midY }, { x: t.x, y: t.y - Math.sign(dy || 1) * (NODE_H / 2) });
        }
        const head = pts[pts.length - 1]!, prev = pts[pts.length - 2]!;
        ctx.beginPath();
        ctx.moveTo(pts[0]!.x, pts[0]!.y);
        for (const pt of pts) ctx.lineTo(pt.x, pt.y);
        ctx.stroke(); ctx.setLineDash([]);
        const ang = Math.atan2(head.y - prev.y, head.x - prev.x);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(head.x, head.y);
        ctx.lineTo(head.x - 8 * Math.cos(ang - Math.PI / 6), head.y - 8 * Math.sin(ang - Math.PI / 6));
        ctx.lineTo(head.x - 8 * Math.cos(ang + Math.PI / 6), head.y - 8 * Math.sin(ang + Math.PI / 6));
        ctx.closePath(); ctx.fill();
        if (doc.config.edgeLabels && e.label) {
          ctx.font = "11px system-ui, sans-serif";
          const lx = (pts[0]!.x + head.x) / 2, ly = (pts[0]!.y + head.y) / 2;
          ctx.lineWidth = 4; ctx.strokeStyle = "#ffffff";
          ctx.strokeText(e.label, lx + 4, ly - 4);
          ctx.fillStyle = color; ctx.fillText(e.label, lx + 4, ly - 4);
        }
      }
      for (const n of doc.nodes) {
        const p = positions[n.id] ?? { x: 0, y: 0 };
        ctx.fillStyle = "#ffffff"; ctx.strokeStyle = STATUS_COLOR[n.status]; ctx.lineWidth = 2;
        ctx.beginPath();
        if (typeof ctx.roundRect === "function") ctx.roundRect(p.x, p.y, NODE_W, NODE_H, 8);
        else ctx.rect(p.x, p.y, NODE_W, NODE_H);
        ctx.fill(); ctx.stroke();
        ctx.fillStyle = "#6b7280"; ctx.font = "10px system-ui, sans-serif";
        ctx.fillText(NODE_KIND_LABEL[n.kind], p.x + 8, p.y + 15);
        ctx.fillStyle = STATUS_COLOR[n.status];
        ctx.fillText(STATUS_LABEL[n.status], p.x + NODE_W - 8 - ctx.measureText(STATUS_LABEL[n.status]).width, p.y + 15);
        ctx.fillStyle = "#111827"; ctx.font = "600 13px system-ui, sans-serif";
        wrapText(ctx, n.label, p.x + 8, p.y + 36, NODE_W - 16, 17, 2);
        ctx.font = "10px system-ui, sans-serif"; ctx.fillStyle = "#6b7280";
        let bx = p.x + 8;
        ctx.fillText(`来源 ${n.sourceRefs.length}`, bx, p.y + NODE_H - 8);
        bx += ctx.measureText(`来源 ${n.sourceRefs.length}`).width + 10;
        if (n.lockedFields.length) { ctx.fillText("已锁定", bx, p.y + NODE_H - 8); bx += ctx.measureText("已锁定").width + 10; }
        if (n.importance === "critical") { ctx.fillStyle = "#b91c1c"; ctx.fillText("关键", bx, p.y + NODE_H - 8); }
      }
      ctx.fillStyle = "#9ca3af"; ctx.font = "11px system-ui, sans-serif";
      ctx.fillText(DISCLIAMER, 24, H - 16);
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("PNG 生成失败");
      downloadBlob(blob, `${sanitizeGraphFilename(doc.title)}-关系图.png`);
      setReceipt(`已导出 PNG（含修订 ${revision} 快照与页脚声明）`);
    } catch (e) {
      setBanner(String((e as Error)?.message ?? e));
    } finally { exportLockRef.current = false; }
  }, [base, dirty, doc, revision, save]);
  const exportJson = useCallback(async () => {
    if (!doc || exportLockRef.current) return;
    exportLockRef.current = true;
    try {
      if (dirty && !(await save())) return;
      const blob = new Blob([JSON.stringify({ ...doc, revision }, null, 2)], { type: "application/json;charset=utf-8" });
      downloadBlob(blob, `${sanitizeGraphFilename(doc.title)}-关系图.json`);
      setReceipt("已导出结构数据 JSON");
    } catch (e) {
      setBanner(String((e as Error)?.message ?? e));
    } finally { exportLockRef.current = false; }
  }, [dirty, doc, revision, save]);

  // ── 未保存拦截（beforeunload；面板无独立关闭钮，浏览器级兜底）──
  useEffect(() => {
    if (!dirty) return;
    const h = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);

  // ── 来源跳转（对拍 #22：来源引用点击打开文档；不在材料库→诚实提示）──
  const openSource = useCallback(async (filename: string) => {
    setBanner(null);
    try {
      const r = await svc.caseGraphReadSource?.({ workspacePath: workspacePath ?? "", filename });
      if (!r) throw new Error("桥未提供来源读取通道");
      setSourcePreview(r);
    } catch (e) {
      setBanner(`来源打不开：${String((e as Error)?.message ?? e)}`);
    }
  }, [svc, workspacePath]);

  const selectedNode = doc && sel?.kind === "node" ? doc.nodes.find((n) => n.id === sel.id) ?? null : null;
  const selectedEdge = doc && sel?.kind === "edge" ? doc.edges.find((e) => e.id === sel.id) ?? null : null;
  const nodeById = useMemo(() => new Map((doc?.nodes ?? []).map((n) => [n.id, n])), [doc]);

  return (
    <section data-testid="case-graph" className="rounded-workspace-panel border border-border bg-header p-4">
      <h2 className="mb-2 flex items-center gap-2 text-ui-lg font-medium">
        <Network className="size-4" /> 关系图（人物 · 证据一屏）
      </h2>

      {phase === "loading" ? <p className="text-ui-sm text-foreground-subtle" data-testid="case-graph-loading">正在读取关系图…</p> : null}
      {phase === "error" ? <p className="text-ui-sm text-red-500">读取失败：{banner}</p> : null}

      {phase === "ready" && !exists ? (
        <div data-testid="case-graph-empty" className="flex flex-col items-start gap-2 rounded border border-border bg-background p-4">
          <p className="text-ui-base font-medium">此案还没有关系图</p>
          <p className="text-ui-sm text-foreground-subtle">
            可以从案件数据（当事人与材料登记）一键建图，生成前先给你过目清单；也可以先建一张空图手工添加。
          </p>
          <div className="mt-1 flex flex-wrap gap-2">
            <button type="button" data-testid="case-graph-build" disabled={previewBusy}
              className="rounded border border-border px-3 py-1 text-ui-sm hover:bg-muted/60 disabled:opacity-50" onClick={() => void runPreview()}>
              {previewBusy ? "正在汇总案件数据…" : "从案件数据建图"}
            </button>
            <button type="button" data-testid="case-graph-new" className="rounded border border-border px-3 py-1 text-ui-sm hover:bg-muted/60" onClick={newEmpty}>
              手工新建空图
            </button>
          </div>
          {preview ? (
            <div className="mt-2 w-full rounded border border-border p-3" data-testid="case-graph-preview">
              <p className="text-ui-sm font-medium">将建：{preview.proposal.nodes.length} 个节点、{preview.proposal.edges.length} 条关系（未确认不写入）</p>
              <p className="mt-1 text-ui-caption text-foreground-subtle">{preview.note}</p>
              <ul className="mt-2 max-h-40 overflow-auto text-ui-sm">
                {preview.proposal.nodes.map((n) => (
                  <li key={n.id} className="rounded px-1 py-0.5 hover:bg-muted/50">
                    【{NODE_KIND_LABEL[n.kind]}】{n.label}
                  </li>
                ))}
                {!preview.proposal.nodes.length ? <li className="text-foreground-subtle">（无可建节点）</li> : null}
              </ul>
              <div className="mt-2 flex gap-2">
                <button type="button" data-testid="case-graph-build-confirm" disabled={previewBusy}
                  className="rounded bg-selected px-3 py-1 text-ui-sm disabled:opacity-50" onClick={() => void confirmBuild()}>
                  {previewBusy ? "正在写入…" : "确认建图"}
                </button>
                <button type="button" className="rounded border border-border px-3 py-1 text-ui-sm hover:bg-muted/60" onClick={() => setPreview(null)}>
                  取消
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {phase === "ready" && exists && doc ? (
        <div className="flex flex-col gap-2">
          {/* 顶条：标题+保存态+导出+重新布局（+方向/撤销/重做/清空） */}
          <div className="flex flex-wrap items-center gap-2" data-testid="case-graph-toolbar">
            <input
              data-testid="case-graph-title" defaultValue={doc.title} maxLength={LIMITS.title}
              className="h-7 w-52 rounded border border-transparent bg-transparent px-1 text-ui-base font-medium hover:border-border focus:border-border"
              aria-label="图标题"
              onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== doc.title) renameTitle(v); else e.target.value = doc.title; }}
            />
            <span className="text-ui-caption text-foreground-subtle">修订 {revision}</span>
            <button type="button" aria-label="撤销" title="撤销" disabled={!past.length}
              className="rounded border border-border px-2 py-1 disabled:opacity-40" onClick={undo}><Undo2 className="size-3.5" /></button>
            <button type="button" aria-label="重做" title="重做" disabled={!future.length}
              className="rounded border border-border px-2 py-1 disabled:opacity-40" onClick={redo}><Redo2 className="size-3.5" /></button>
            <select
              data-testid="case-graph-direction" value={doc.config.direction} aria-label="排布方向"
              className="h-7 rounded border border-border bg-background px-1 text-ui-sm"
              onChange={(e) => setDirection(e.target.value === "LR" ? "LR" : "TB")}
            >
              <option value="TB">从上到下</option>
              <option value="LR">从左到右</option>
            </select>
            <button type="button" data-testid="case-graph-relayout" className="flex items-center gap-1 rounded border border-border px-2 py-1 text-ui-sm hover:bg-muted/60"
              onClick={() => { mutate((d) => ({ ...d, layout: { positions: {} } }), false); setLayoutDirty(true); }}>
              <RotateCw className="size-3.5" /> 重新布局
            </button>
            <button type="button" data-testid="case-graph-export-png" className="flex items-center gap-1 rounded border border-border px-2 py-1 text-ui-sm hover:bg-muted/60" onClick={() => void exportPng()}>
              <ImageDown className="size-3.5" /> 导出 PNG
            </button>
            <button type="button" data-testid="case-graph-export-json" className="flex items-center gap-1 rounded border border-border px-2 py-1 text-ui-sm hover:bg-muted/60" onClick={() => void exportJson()}>
              <Braces className="size-3.5" /> 导出 JSON
            </button>
            <button type="button" data-testid="case-graph-clear" className="flex items-center gap-1 rounded border border-red-300 px-2 py-1 text-ui-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
              onClick={() => void clearGraph()}>
              <Trash2 className="size-3.5" /> 清空图
            </button>
            <button type="button" data-testid="case-graph-save" disabled={!dirty || saveState === "saving"}
              className="ml-auto flex items-center gap-1 rounded bg-selected px-3 py-1 text-ui-sm disabled:opacity-40" onClick={() => void save()}>
              {saveState === "saving" ? "保存中…" : saveState === "saved" ? "已保存" : "保存修改"}
            </button>
          </div>

          {banner ? (
            <div className="flex flex-wrap items-center gap-2 rounded border border-red-300 bg-red-50 px-3 py-1.5 text-ui-sm text-red-700 dark:bg-red-950 dark:text-red-300" data-testid="case-graph-banner" role="alert">
              <span>{banner}</span>
              {conflict ? (
                <button type="button" className="rounded border border-red-300 px-2 py-0.5 hover:bg-red-100 dark:hover:bg-red-900" onClick={() => void reload()}>
                  刷新读取最新版
                </button>
              ) : null}
            </div>
          ) : null}
          {receipt ? <p className="text-ui-caption text-foreground-subtle" data-testid="case-graph-receipt">{receipt}</p> : null}

          <div className="flex gap-3">
            {/* 左画布 */}
            <div
              ref={containerRef}
              data-testid="case-graph-canvas"
              className="relative h-[520px] flex-1 select-none overflow-hidden rounded border border-border bg-background"
              style={{
                backgroundImage: "radial-gradient(circle, rgba(127,127,127,0.35) 1px, transparent 1px)",
                backgroundSize: `${20 * view.scale}px ${20 * view.scale}px`,
                backgroundPosition: `${view.x}px ${view.y}px`,
              }}
              onWheel={onWheel}
              onPointerDown={onBackgroundPointerDown}
              onPointerMove={(e) => { onBackgroundPointerMove(e); onNodePointerMove(e); }}
              onPointerUp={() => { onBackgroundPointerUp(); onNodePointerUp(); }}
            >
              <CaseGraphBoundary key={layoutKey}>
                {doc.nodes.length === 0 ? (
                  <div className="flex h-full items-center justify-center text-ui-sm text-foreground-subtle" data-testid="case-graph-blank">
                    图中还没有节点：在右侧表单添加，或清空后从案件数据重新建图。
                  </div>
                ) : (
                  <div
                    className="absolute left-0 top-0"
                    style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`, transformOrigin: "0 0", width: base?.width ?? 1, height: base?.height ?? 1 }}
                  >
                    <svg className="pointer-events-none absolute inset-0" width={base?.width ?? 1} height={base?.height ?? 1}>
                      <defs>
                        {GRAPH_STATUSES.map((s) => (
                          <marker key={s} id={`cg-arrow-${s}`} markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
                            <path d="M0,0 L8,3 L0,6 Z" fill={STATUS_COLOR[s]} />
                          </marker>
                        ))}
                      </defs>
                      {doc.edges.map((e) => {
                        const sp = posOf(e.source), tp = posOf(e.target);
                        const sc = { x: sp.x + NODE_W / 2, y: sp.y + NODE_H / 2 };
                        const tc = { x: tp.x + NODE_W / 2, y: tp.y + NODE_H / 2 };
                        const dx = tc.x - sc.x, dy = tc.y - sc.y;
                        let d: string, lx: number, ly: number;
                        if (Math.abs(dx) >= Math.abs(dy)) {
                          const midX = (sc.x + tc.x) / 2;
                          const sx2 = sc.x + Math.sign(dx || 1) * (NODE_W / 2);
                          const tx2 = tc.x - Math.sign(dx || 1) * (NODE_W / 2);
                          d = `M ${sx2} ${sc.y} L ${midX} ${sc.y} L ${midX} ${tc.y} L ${tx2} ${tc.y}`;
                          lx = (sx2 + tx2) / 2; ly = (sc.y + tc.y) / 2;
                        } else {
                          const midY = (sc.y + tc.y) / 2;
                          const sy2 = sc.y + Math.sign(dy || 1) * (NODE_H / 2);
                          const ty2 = tc.y - Math.sign(dy || 1) * (NODE_H / 2);
                          d = `M ${sc.x} ${sy2} L ${sc.x} ${midY} L ${tc.x} ${midY} L ${tc.x} ${ty2}`;
                          lx = (sc.x + tc.x) / 2; ly = (sy2 + ty2) / 2;
                        }
                        return (
                          <g key={e.id}>
                            <path d={d} fill="none" stroke="transparent" strokeWidth={12} style={{ pointerEvents: "stroke" }} className="cursor-pointer"
                              onPointerDown={(ev) => { ev.stopPropagation(); setSel({ kind: "edge", id: e.id }); }} />
                            <path d={d} fill="none" stroke={STATUS_COLOR[e.status]} strokeWidth={1.6}
                              strokeDasharray={STATUS_DASHED[e.status] ? "7 5" : undefined}
                              markerEnd={`url(#cg-arrow-${e.status})`}
                              pointerEvents="none" opacity={sel?.kind === "edge" && sel.id === e.id ? 1 : 0.9} />
                            {doc.config.edgeLabels && e.label ? (
                              <text x={lx} y={ly - 4} fontSize="11" fill={STATUS_COLOR[e.status]}
                                stroke="#ffffff" strokeWidth={4} paintOrder="stroke" pointerEvents="none">{e.label}</text>
                            ) : null}
                          </g>
                        );
                      })}
                    </svg>
                    {doc.nodes.map((n) => {
                      const p = posOf(n.id);
                      const active = sel?.kind === "node" && sel.id === n.id;
                      return (
                        <div
                          key={n.id}
                          data-testid="case-graph-node"
                          data-node-id={n.id}
                          className="absolute cursor-grab rounded-lg border-2 bg-white shadow-sm active:cursor-grabbing"
                          style={{
                            left: p.x, top: p.y, width: NODE_W, height: NODE_H,
                            borderColor: STATUS_COLOR[n.status],
                            outline: active ? `2px solid ${STATUS_COLOR[n.status]}` : undefined,
                            outlineOffset: 2,
                          }}
                          onPointerDown={(e) => onNodePointerDown(e, n)}
                        >
                          <div className="flex items-center justify-between px-2 pt-1">
                            <span className="text-[10px] text-gray-500">{NODE_KIND_LABEL[n.kind]}</span>
                            <span className="flex items-center gap-1 text-[10px]" style={{ color: STATUS_COLOR[n.status] }}>
                              <span className="inline-block size-1.5 rounded-full" style={{ background: STATUS_COLOR[n.status] }} />
                              {STATUS_LABEL[n.status]}
                            </span>
                          </div>
                          <div className="line-clamp-2 px-2 pt-0.5 text-[13px] font-medium leading-tight text-gray-900">{n.label}</div>
                          <div className="absolute bottom-1 left-2 right-2 flex items-center gap-2 text-[10px] text-gray-500">
                            <span className="flex items-center gap-0.5"><FileText className="size-2.5" />来源 {n.sourceRefs.length}</span>
                            {n.lockedFields.length ? (
                              <span className="flex items-center gap-0.5"><Lock className="size-2.5" />已锁定</span>
                            ) : null}
                            {n.importance === "critical" ? <span className="font-medium text-red-600">关键</span> : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CaseGraphBoundary>
              {layoutState === "pending" ? (
                <div className="absolute inset-x-0 top-2 text-center text-ui-caption text-foreground-subtle">正在排布…</div>
              ) : null}
              {layoutState === "error" ? (
                <div className="absolute inset-x-0 top-2 text-center text-ui-caption text-red-600">排布失败：{layoutError}</div>
              ) : null}
              <div className="absolute bottom-2 left-2 flex gap-1">
                <button type="button" aria-label="放大" className="rounded border border-border bg-background px-1.5 py-0.5" onClick={() => setView((v) => ({ ...v, scale: Math.min(1.8, v.scale * 1.2) }))}><ZoomIn className="size-3.5" /></button>
                <button type="button" aria-label="缩小" className="rounded border border-border bg-background px-1.5 py-0.5" onClick={() => setView((v) => ({ ...v, scale: Math.max(0.25, v.scale / 1.2) }))}><ZoomOut className="size-3.5" /></button>
                <button type="button" aria-label="适合窗口" className="rounded border border-border bg-background px-1.5 py-0.5" onClick={fitView}><Maximize className="size-3.5" /></button>
              </div>
            </div>

            {/* 右抽屉：节点详情 / 关系详情 / 添加表单 */}
            <div className="flex w-80 shrink-0 flex-col gap-3 overflow-auto rounded border border-border bg-background p-3" data-testid="case-graph-drawer">
              {selectedNode ? (
                <NodeDetail
                  key={selectedNode.id}
                  node={selectedNode}
                  materials={materials}
                  onPatch={(patch) => patchNode(selectedNode.id, patch)}
                  onToggleLock={(field) => toggleNodeLock(selectedNode.id, field)}
                  onRemove={() => removeNode(selectedNode.id)}
                  onOpenSource={(f) => void openSource(f)}
                />
              ) : selectedEdge ? (
                <EdgeDetail
                  key={selectedEdge.id}
                  edge={selectedEdge}
                  nodeById={nodeById}
                  onPatch={(patch) => patchEdge(selectedEdge.id, patch)}
                  onRemove={() => removeEdge(selectedEdge.id)}
                />
              ) : (
                <AddForms doc={doc} onAddNode={addNode} onAddEdge={addEdge} />
              )}
            </div>
          </div>

          {/* 图例（四档配色）+ 免责页脚 */}
          <div className="flex flex-wrap items-center gap-3 text-ui-caption text-foreground-subtle" data-testid="case-graph-legend">
            {GRAPH_STATUSES.map((s) => (
              <span key={s} className="flex items-center gap-1">
                <span className="inline-block size-2.5 rounded-sm" style={{ background: STATUS_COLOR[s] }} />
                {STATUS_LABEL[s]}
              </span>
            ))}
            <span>（存疑为虚线）</span>
          </div>
          <p className="text-ui-caption text-foreground-subtle">{DISCLIAMER}</p>
        </div>
      ) : null}

      {/* 施工波二轮·可视化B轨 UI 件：对抗视图入口（语义 JSON 导入→桥面守卫→确定性渲染→预览/下载；
          判定全在桥面 @juscite/vizb；内部推演件不对法院出示。不依赖关系图文档是否存在） */}
      {phase !== "loading" ? <ConfrontationSection /> : null}

      {sourcePreview ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-8" onClick={() => setSourcePreview(null)}>
          <div className="max-h-[70vh] w-full max-w-2xl overflow-hidden rounded-lg border border-border bg-background shadow-lg" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <span className="text-ui-sm font-medium">{sourcePreview.name}{sourcePreview.truncated ? "（超长截断显示）" : ""}</span>
              <button type="button" aria-label="关闭来源预览" onClick={() => setSourcePreview(null)}><X className="size-4" /></button>
            </div>
            <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap p-3 text-xs leading-relaxed">{sourcePreview.text}</pre>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function wrapText(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, maxW: number, lineH: number, maxLines: number): void {
  let line = "", lines = 0;
  for (const ch of text) {
    if (ctx.measureText(line + ch).width > maxW) {
      lines += 1;
      if (lines >= maxLines) { ctx.fillText(`${line}…`, x, y); return; }
      ctx.fillText(line, x, y);
      y += lineH;
      line = ch;
    } else line += ch;
  }
  if (line) ctx.fillText(line, x, y);
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

const FIELD_HELP = "无法确认到具体日期时，只写文字描述，不要补造日期。";

function NodeDetail(props: {
  node: GNode;
  materials: Array<{ name: string; kind: string }>;
  onPatch: (patch: Partial<GNode>) => void;
  onToggleLock: (field: string) => void;
  onRemove: () => void;
  onOpenSource: (filename: string) => void;
}) {
  const { node } = props;
  const [label, setLabel] = useState(node.label);
  const [detail, setDetail] = useState(node.detail ?? "");
  const [dateLabel, setDateLabel] = useState(node.dateLabel ?? "");
  const [bindFile, setBindFile] = useState("");
  const [bindLocator, setBindLocator] = useState("");
  const [bindQuote, setBindQuote] = useState("");
  const locked = (f: string) => node.lockedFields.includes(f);

  return (
    <div className="flex flex-col gap-2.5" data-testid="case-graph-node-detail">
      <div className="flex items-center justify-between">
        <span className="text-ui-caption text-foreground-subtle">
          节点详情 · {NODE_KIND_LABEL[node.kind]} · {node.provenance === "user" ? "律师编辑" : "系统建图"}
        </span>
        <button type="button" className="flex items-center gap-1 text-ui-caption text-red-600 hover:underline" onClick={props.onRemove}>
          <Trash2 className="size-3" /> 删除节点
        </button>
      </div>

      <label className="flex flex-col gap-1 text-ui-caption">
        <span className="flex items-center justify-between">
          标题
          <button type="button" aria-label={locked("label") ? "解锁标题" : "锁定标题"} onClick={() => props.onToggleLock("label")}
            className={locked("label") ? "text-foreground" : "text-foreground-subtle"}>
            {locked("label") ? <Lock className="size-3" /> : <LockOpen className="size-3" />}
          </button>
        </span>
        <input data-testid="case-graph-node-label" value={label} maxLength={LIMITS.label}
          className="h-7 rounded border border-border bg-transparent px-2 text-ui-sm"
          onChange={(e) => setLabel(e.target.value)}
          onBlur={() => { const v = label.trim(); if (v && v !== node.label) props.onPatch({ label: v }); }} />
      </label>

      <label className="flex flex-col gap-1 text-ui-caption">
        <span className="flex items-center justify-between">
          备注 / 说明
          <button type="button" aria-label={locked("detail") ? "解锁备注" : "锁定备注"} onClick={() => props.onToggleLock("detail")}
            className={locked("detail") ? "text-foreground" : "text-foreground-subtle"}>
            {locked("detail") ? <Lock className="size-3" /> : <LockOpen className="size-3" />}
          </button>
        </span>
        <textarea value={detail} rows={4} maxLength={LIMITS.detail}
          className="rounded border border-border bg-transparent p-2 text-ui-sm"
          onChange={(e) => setDetail(e.target.value)}
          onBlur={() => { const v = detail.trim(); if ((v || node.detail) && v !== (node.detail ?? "")) props.onPatch(v ? { detail: v } : { detail: undefined }); }} />
      </label>

      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-ui-caption">事实状态
          <select value={node.status} className="h-7 rounded border border-border bg-background px-1 text-ui-sm"
            onChange={(e) => props.onPatch({ status: e.target.value as GraphStatus })}>
            {GRAPH_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
          </select>
        </label>
        <label className="mt-5 flex items-center gap-1.5 text-ui-caption">
          <input type="checkbox" checked={node.importance === "critical"}
            onChange={(e) => props.onPatch({ importance: e.target.checked ? "critical" : undefined })} />
          关键事实
        </label>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-ui-caption">确切日期
          <input type="date" value={node.date ?? ""} className="h-7 rounded border border-border bg-transparent px-1 text-ui-sm"
            onChange={(e) => props.onPatch(e.target.value ? { date: e.target.value } : { date: undefined })} />
        </label>
        <label className="flex flex-col gap-1 text-ui-caption">日期描述
          <input value={dateLabel} maxLength={LIMITS.dateLabel} placeholder="例如：2026 年 2 月上旬"
            className="h-7 rounded border border-border bg-transparent px-2 text-ui-sm"
            onChange={(e) => setDateLabel(e.target.value)}
            onBlur={() => { const v = dateLabel.trim(); if ((v || node.dateLabel) && v !== (node.dateLabel ?? "")) props.onPatch(v ? { dateLabel: v } : { dateLabel: undefined }); }} />
        </label>
      </div>
      <p className="text-ui-caption text-foreground-subtle">{FIELD_HELP}</p>

      <div className="flex flex-col gap-1">
        <span className="text-ui-caption">材料来源（{node.sourceRefs.length}）</span>
        {node.sourceRefs.length ? (
          <ul className="flex flex-col gap-1">
            {node.sourceRefs.map((r, i) => (
              <li key={i} className="rounded border border-border px-2 py-1.5">
                <div className="flex items-center justify-between gap-2">
                  <button type="button" className="truncate text-left text-ui-sm text-blue-700 hover:underline dark:text-blue-400"
                    onClick={() => props.onOpenSource(r.filename)} title={`打开来源：${r.filename}`}>
                    {r.filename}{r.locator ? ` · ${r.locator}` : ""}
                  </button>
                  <button type="button" aria-label="移除该来源" className="text-foreground-subtle hover:text-red-600"
                    onClick={() => props.onPatch({ sourceRefs: node.sourceRefs.filter((_, j) => j !== i) })}><X className="size-3" /></button>
                </div>
                {r.quote ? <p className="mt-0.5 line-clamp-3 text-ui-caption text-foreground-subtle">{r.quote}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-ui-caption text-foreground-subtle">尚未绑定材料来源；关键且已证实的节点必须至少绑定一条。</p>
        )}
        <div className="mt-1 flex flex-col gap-1 rounded border border-dashed border-border p-2">
          <select value={bindFile} className="h-7 rounded border border-border bg-background px-1 text-ui-sm"
            onChange={(e) => setBindFile(e.target.value)}>
            <option value="">选择材料…</option>
            {props.materials.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
          </select>
          <input value={bindLocator} placeholder="定位符（如：第 3 页 / 条款 5）" maxLength={LIMITS.locator}
            className="h-7 rounded border border-border bg-transparent px-2 text-ui-sm"
            onChange={(e) => setBindLocator(e.target.value)} />
          <input value={bindQuote} placeholder="摘录（可选）" maxLength={LIMITS.quote}
            className="h-7 rounded border border-border bg-transparent px-2 text-ui-sm"
            onChange={(e) => setBindQuote(e.target.value)} />
          <button type="button" disabled={!bindFile}
            className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-muted/60 disabled:opacity-40"
            onClick={() => {
              const ref = { filename: bindFile, ...(bindLocator.trim() ? { locator: bindLocator.trim() } : {}), ...(bindQuote.trim() ? { quote: bindQuote.trim() } : {}) };
              props.onPatch({ sourceRefs: [...node.sourceRefs, ref] });
              setBindFile(""); setBindLocator(""); setBindQuote("");
            }}>绑定来源</button>
        </div>
      </div>
    </div>
  );
}

function EdgeDetail(props: {
  edge: GEdge;
  nodeById: Map<string, GNode>;
  onPatch: (patch: Partial<GEdge>) => void;
  onRemove: () => void;
}) {
  const { edge } = props;
  const [label, setLabel] = useState(edge.label ?? "");
  return (
    <div className="flex flex-col gap-2.5" data-testid="case-graph-edge-detail">
      <div className="flex items-center justify-between">
        <span className="text-ui-caption text-foreground-subtle">关系详情</span>
        <button type="button" className="flex items-center gap-1 text-ui-caption text-red-600 hover:underline" onClick={props.onRemove}>
          <Trash2 className="size-3" /> 删除关系
        </button>
      </div>
      <p className="text-ui-sm">
        {props.nodeById.get(edge.source)?.label ?? edge.source} → {props.nodeById.get(edge.target)?.label ?? edge.target}
      </p>
      <label className="flex flex-col gap-1 text-ui-caption">关系类型
        <select value={edge.kind} className="h-7 rounded border border-border bg-background px-1 text-ui-sm"
          onChange={(e) => props.onPatch({ kind: e.target.value as EdgeKind })}>
          {EDGE_KINDS.map((k) => <option key={k} value={k}>{EDGE_KIND_LABEL[k]}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-ui-caption">关系标签
        <input value={label} maxLength={LIMITS.edgeLabel} className="h-7 rounded border border-border bg-transparent px-2 text-ui-sm"
          onChange={(e) => setLabel(e.target.value)}
          onBlur={() => { const v = label.trim(); if ((v || edge.label) && v !== (edge.label ?? "")) props.onPatch(v ? { label: v } : { label: undefined }); }} />
      </label>
      <label className="flex flex-col gap-1 text-ui-caption">事实状态
        <select value={edge.status} className="h-7 rounded border border-border bg-background px-1 text-ui-sm"
          onChange={(e) => props.onPatch({ status: e.target.value as GraphStatus })}>
          {GRAPH_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </select>
      </label>
      <p className="text-ui-caption text-foreground-subtle">编辑过的关系会自动锁定，自动改动不得覆盖；锁定仅可通过开关解除。</p>
    </div>
  );
}

function AddForms(props: {
  doc: GraphDoc;
  onAddNode: (kind: NodeKind, label: string) => void;
  onAddEdge: (source: string, target: string, kind: EdgeKind, label: string) => void;
}) {
  const [kind, setKind] = useState<NodeKind>("party");
  const [label, setLabel] = useState("");
  const [src, setSrc] = useState("");
  const [dst, setDst] = useState("");
  const [ekind, setEkind] = useState<EdgeKind>("prove");
  const [elabel, setElabel] = useState("");
  const nodes = props.doc.nodes;
  return (
    <div className="flex flex-col gap-4" data-testid="case-graph-add">
      <p className="text-ui-caption text-foreground-subtle">点击画布中的节点或连线可查看与编辑；未选中时在此添加。</p>
      <div className="flex flex-col gap-1.5">
        <span className="text-ui-caption">添加节点</span>
        <div className="flex gap-1.5">
          <select value={kind} aria-label="节点类型" className="h-7 w-28 rounded border border-border bg-background px-1 text-ui-sm"
            onChange={(e) => setKind(e.target.value as NodeKind)}>
            {NODE_KINDS.map((k) => <option key={k} value={k}>{NODE_KIND_LABEL[k]}</option>)}
          </select>
          <input value={label} placeholder="名称（如：张三）" maxLength={LIMITS.label} data-testid="case-graph-add-node-label"
            className="h-7 flex-1 rounded border border-border bg-transparent px-2 text-ui-sm"
            onChange={(e) => setLabel(e.target.value)} />
        </div>
        <button type="button" data-testid="case-graph-add-node" disabled={!label.trim()}
          className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-muted/60 disabled:opacity-40"
          onClick={() => { props.onAddNode(kind, label); setLabel(""); }}>添加节点</button>
      </div>
      <div className="flex flex-col gap-1.5">
        <span className="text-ui-caption">添加关系（只走表单，不支持拖线建边）</span>
        <div className="flex items-center gap-1.5">
          <select value={src} aria-label="关系起点" className="h-7 min-w-0 flex-1 rounded border border-border bg-background px-1 text-ui-sm"
            onChange={(e) => setSrc(e.target.value)}>
            <option value="">起点…</option>
            {nodes.map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
          </select>
          <span className="text-ui-caption">→</span>
          <select value={dst} aria-label="关系终点" className="h-7 min-w-0 flex-1 rounded border border-border bg-background px-1 text-ui-sm"
            onChange={(e) => setDst(e.target.value)}>
            <option value="">终点…</option>
            {nodes.map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
          </select>
        </div>
        <div className="flex gap-1.5">
          <select value={ekind} aria-label="关系类型" className="h-7 w-28 rounded border border-border bg-background px-1 text-ui-sm"
            onChange={(e) => setEkind(e.target.value as EdgeKind)}>
            {EDGE_KINDS.map((k) => <option key={k} value={k}>{EDGE_KIND_LABEL[k]}</option>)}
          </select>
          <input value={elabel} placeholder="标签（可选）" maxLength={LIMITS.edgeLabel}
            className="h-7 flex-1 rounded border border-border bg-transparent px-2 text-ui-sm"
            onChange={(e) => setElabel(e.target.value)} />
        </div>
        <button type="button" data-testid="case-graph-add-edge" disabled={!src || !dst}
          className="rounded border border-border px-2 py-1 text-ui-sm hover:bg-muted/60 disabled:opacity-40"
          onClick={() => { props.onAddEdge(src, dst, ekind, elabel); setElabel(""); }}>添加关系</button>
        {!nodes.length ? <p className="text-ui-caption text-foreground-subtle">先添加节点，才能连关系。</p> : null}
      </div>
    </div>
  );
}
