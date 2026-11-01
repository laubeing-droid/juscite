// 功能 #19 轻量知识图谱（步骤4·RE-19 等量裁剪版）：共享纯模型（数据/校验/规则建图/分层布局）。
// 单一来源三方复用：桥（写路径 fail-closed 校验+规则建图）、UI（类型/标签/布局）、合成自测。
// 枚举值与中文标签全部自写（表达隔离，不抄竞品）；限额降档 100/200/80（RE-19 §3）。
// 不可裁四条硬规则：防注入正则 / 关键事实须有来源 / 悬空引用拒绝 / ISO 日期 fail-closed。

export const GRAPH_SCHEMA_VERSION = 1 as const;

export const NODE_KINDS = ["party", "witness", "evidence", "event", "issue", "amount"] as const;
export type NodeKind = (typeof NODE_KINDS)[number];
export const NODE_KIND_LABEL: Record<NodeKind, string> = {
  party: "当事人", witness: "证人", evidence: "证据", event: "事件", issue: "争点", amount: "金额",
};

export const EDGE_KINDS = ["kin", "contract", "pay", "possess", "prove", "support", "refute", "cause"] as const;
export type EdgeKind = (typeof EDGE_KINDS)[number];
export const EDGE_KIND_LABEL: Record<EdgeKind, string> = {
  kin: "亲属", contract: "合同相对", pay: "支付", possess: "占有",
  prove: "证明", support: "支持", refute: "反驳", cause: "引发",
};

export const GRAPH_STATUSES = ["confirmed", "ours", "theirs", "uncertain"] as const;
export type GraphStatus = (typeof GRAPH_STATUSES)[number];
export const STATUS_LABEL: Record<GraphStatus, string> = {
  confirmed: "已证实", ours: "我方主张", theirs: "对方主张", uncertain: "存疑",
};
/** 自绘四档色板（不取竞品 hex）；存疑虚线，其余实线。 */
export const STATUS_COLOR: Record<GraphStatus, string> = {
  confirmed: "#0e7a4e", ours: "#1d4ed8", theirs: "#b91c1c", uncertain: "#a16207",
};
export const STATUS_DASHED: Record<GraphStatus, boolean> = {
  confirmed: false, ours: false, theirs: false, uncertain: true,
};

/** 锁定字段白名单（lockedFields 只允许这些值；锁定仅约束自动改动，人工编辑始终直改）。 */
export const NODE_LOCKABLE_FIELDS = ["label", "detail", "status", "date", "dateLabel", "importance", "sourceRefs"] as const;
export const EDGE_LOCKABLE_FIELDS = ["label", "status", "sourceRefs"] as const;

/** 限额（RE-19 §3 降档起步：节点 100 / 边 200 / 标题 80）。 */
export const LIMITS = {
  nodes: 100,
  edges: 200,
  title: 80,
  label: 80,
  detail: 2000,
  quote: 500,
  locator: 200,
  id: 200,
  filename: 200,
  sourceRefs: 100,
  edgeLabel: 200,
  dateLabel: 200,
  caseId: 80,
  depth: 12,
} as const;

export type SourceRef = {
  documentId?: string;
  filename: string;
  locator?: string;
  quote?: string;
};

export type GNode = {
  id: string;
  kind: NodeKind;
  label: string;
  detail?: string;
  date?: string;
  dateLabel?: string;
  status: GraphStatus;
  importance?: "normal" | "critical";
  sourceRefs: SourceRef[];
  provenance: "ai" | "user";
  lockedFields: string[];
};

export type GEdge = {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  label?: string;
  status: GraphStatus;
  sourceRefs: SourceRef[];
  provenance: "ai" | "user";
  lockedFields: string[];
};

export type GraphDoc = {
  schemaVersion: typeof GRAPH_SCHEMA_VERSION;
  title: string;
  nodes: GNode[];
  edges: GEdge[];
  config: { direction: "TB" | "LR"; edgeLabels: boolean };
  layout: { positions: Record<string, { x: number; y: number }> };
  updatedAt: string;
};

// ---------- 防注入（J3 等量：全部文本禁 HTML 标签、http(s) URL、javascript: 协议） ----------
const RE_HTML_TAG = /<\s*\/?\s*[a-z][^>]*>/i;
const RE_URL = /\bhttps?:\/\/\S+/i;
const RE_JS_PROTO = /\bjavascript\s*:/i;

function rejectUnsafeText(value: string, field: string): void {
  if (RE_HTML_TAG.test(value)) throw new Error(`「${field}」含 HTML 标签，已拒绝（防注入）`);
  if (RE_URL.test(value)) throw new Error(`「${field}」含网页链接，已拒绝（防注入）`);
  if (RE_JS_PROTO.test(value)) throw new Error(`「${field}」含脚本协议，已拒绝（防注入）`);
}

// ---------- ISO 日期 fail-closed（J4 等量：只收真实存在的 YYYY-MM-DD，模糊时间走 dateLabel） ----------
export function isRealIsoDate(value: string): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return false;
  const y = Number(m[1]), mo = Number(m[2]), d = Number(m[3]);
  const dt = new Date(y, mo - 1, d);
  return dt.getFullYear() === y && dt.getMonth() === mo - 1 && dt.getDate() === d;
}

// ---------- 深度上限（J3 等量：JSON 嵌套 ≤12） ----------
export function assertDepth(value: unknown, max = LIMITS.depth): void {
  const walk = (v: unknown, d: number) => {
    if (d > max) throw new Error(`数据嵌套超过 ${max} 层，已拒绝`);
    if (Array.isArray(v)) { for (const item of v) walk(item, d + 1); }
    else if (v && typeof v === "object") { for (const k of Object.keys(v as object)) walk((v as Record<string, unknown>)[k], d + 1); }
  };
  walk(value, 0);
}

function checkText(value: string | undefined, field: string, limit: number, required = false): void {
  if (value === undefined || value === "") {
    if (required) throw new Error(`「${field}」不能为空`);
    return;
  }
  if (typeof value !== "string") throw new Error(`「${field}」必须是文本`);
  if (value.length > limit) throw new Error(`「${field}」超过 ${limit} 字上限`);
  rejectUnsafeText(value, field);
}

function checkSourceRefs(refs: unknown, owner: string): void {
  if (!Array.isArray(refs)) throw new Error(`${owner} 的来源引用必须是数组`);
  if (refs.length > LIMITS.sourceRefs) throw new Error(`${owner} 的来源引用超过 ${LIMITS.sourceRefs} 条上限`);
  for (const r of refs as SourceRef[]) {
    if (!r || typeof r !== "object") throw new Error(`${owner} 的来源引用格式非法`);
    checkText(r.filename, `${owner} 来源文件名`, LIMITS.filename, true);
    checkText(r.documentId, `${owner} 来源文档 id`, LIMITS.id);
    checkText(r.locator, `${owner} 来源定位符`, LIMITS.locator);
    checkText(r.quote, `${owner} 来源摘录`, LIMITS.quote);
  }
}

function checkLockedFields(fields: unknown, owner: string, whitelist: readonly string[]): void {
  if (!Array.isArray(fields)) throw new Error(`${owner} 的锁定字段必须是数组`);
  for (const f of fields) {
    if (typeof f !== "string" || !whitelist.includes(f)) throw new Error(`${owner} 含非法锁定字段：${String(f)}`);
  }
}

/**
 * 全量校验一张图文档（写路径唯一闸门，fail-closed：首个违规即抛错拒绝）。
 * 等量移植 RE-19 对拍 #30/#31/#32/#38 四条硬规则 + 限额降档。
 */
export function validateGraph(graph: unknown): GraphDoc {
  if (!graph || typeof graph !== "object") throw new Error("关系图数据缺失或格式非法");
  const g = graph as Record<string, unknown>;
  const allowed = new Set(["schemaVersion", "title", "nodes", "edges", "config", "layout", "updatedAt"]);
  for (const key of Object.keys(g)) {
    if (!allowed.has(key)) throw new Error(`关系图含未知字段「${key}」，已拒绝`);
  }
  assertDepth(g);
  if (g.schemaVersion !== GRAPH_SCHEMA_VERSION) throw new Error(`schemaVersion 必须为 ${GRAPH_SCHEMA_VERSION}`);
  checkText(typeof g.title === "string" ? g.title : undefined, "图标题", LIMITS.title, true);

  const nodes = g.nodes, edges = g.edges;
  if (!Array.isArray(nodes) || !Array.isArray(edges)) throw new Error("nodes/edges 必须是数组");
  if (nodes.length > LIMITS.nodes) throw new Error(`节点数超过 ${LIMITS.nodes} 上限`);
  if (edges.length > LIMITS.edges) throw new Error(`关系数超过 ${LIMITS.edges} 上限`);

  const nodeIds = new Set<string>();
  const checked: GNode[] = nodes.map((raw: unknown, i: number) => {
    const n = raw as Record<string, unknown>;
    const owner = `节点#${i + 1}`;
    if (!n || typeof n !== "object") throw new Error(`${owner} 格式非法`);
    for (const key of Object.keys(n)) {
      if (!["id", "kind", "label", "detail", "date", "dateLabel", "status", "importance", "sourceRefs", "provenance", "lockedFields"].includes(key)) {
        throw new Error(`${owner} 含未知字段「${key}」`);
      }
    }
    if (typeof n.id !== "string" || !n.id.trim() || n.id.length > LIMITS.id) throw new Error(`${owner} 的 id 非法（1..${LIMITS.id} 字）`);
    if (nodeIds.has(n.id)) throw new Error(`节点 id 重复：${n.id}`);
    nodeIds.add(n.id);
    if (typeof n.kind !== "string" || !NODE_KINDS.includes(n.kind as NodeKind)) throw new Error(`${owner}（${n.id}）的节点类型不在白名单内`);
    checkText(n.label as string, `${owner} 标题`, LIMITS.label, true);
    checkText(n.detail as string, `${owner} 备注`, LIMITS.detail);
    checkText(n.dateLabel as string, `${owner} 日期描述`, LIMITS.dateLabel);
    if (n.date !== undefined && n.date !== "") {
      if (typeof n.date !== "string" || !isRealIsoDate(n.date)) {
        throw new Error(`${owner}（${n.id}）的日期不是真实存在的年月日（如 2 月 30 日会被拒）；无法确认到日请只填日期描述`);
      }
    }
    if (typeof n.status !== "string" || !GRAPH_STATUSES.includes(n.status as GraphStatus)) throw new Error(`${owner}（${n.id}）的事实状态不在白名单内`);
    if (n.importance !== undefined && !["normal", "critical"].includes(n.importance as string)) throw new Error(`${owner}（${n.id}）的重要性取值非法`);
    if (n.provenance !== "ai" && n.provenance !== "user") throw new Error(`${owner}（${n.id}）的 provenance 非法`);
    checkLockedFields(n.lockedFields, `${owner}（${n.id}）`, NODE_LOCKABLE_FIELDS);
    checkSourceRefs(n.sourceRefs, `${owner}（${n.id}）`);
    // J5 等量：关键且已证实的节点必须至少带一条来源
    if (n.importance === "critical" && n.status === "confirmed" && (!(n.sourceRefs as unknown[]).length)) {
      throw new Error(`关键且已证实的节点必须至少绑定一条材料来源（${n.id}）`);
    }
    return n as unknown as GNode;
  });

  const edgeIds = new Set<string>();
  for (let i = 0; i < edges.length; i++) {
    const e = edges[i] as Record<string, unknown>;
    const owner = `关系#${i + 1}`;
    if (!e || typeof e !== "object") throw new Error(`${owner} 格式非法`);
    for (const key of Object.keys(e)) {
      if (!["id", "source", "target", "kind", "label", "status", "sourceRefs", "provenance", "lockedFields"].includes(key)) {
        throw new Error(`${owner} 含未知字段「${key}」`);
      }
    }
    if (typeof e.id !== "string" || !e.id.trim() || e.id.length > LIMITS.id) throw new Error(`${owner} 的 id 非法`);
    if (edgeIds.has(e.id)) throw new Error(`关系 id 重复：${e.id}`);
    edgeIds.add(e.id);
    if (typeof e.source !== "string" || !nodeIds.has(e.source)) throw new Error(`${owner} 悬空引用：起点节点 ${String(e.source)} 不存在`);
    if (typeof e.target !== "string" || !nodeIds.has(e.target)) throw new Error(`${owner} 悬空引用：终点节点 ${String(e.target)} 不存在`);
    if (typeof e.kind !== "string" || !EDGE_KINDS.includes(e.kind as EdgeKind)) throw new Error(`${owner} 的关系类型不在白名单内`);
    checkText(e.label as string, `${owner} 标签`, LIMITS.edgeLabel);
    if (typeof e.status !== "string" || !GRAPH_STATUSES.includes(e.status as GraphStatus)) throw new Error(`${owner} 的事实状态不在白名单内`);
    if (e.provenance !== "ai" && e.provenance !== "user") throw new Error(`${owner} 的 provenance 非法`);
    checkLockedFields(e.lockedFields, `${owner}`, EDGE_LOCKABLE_FIELDS);
    checkSourceRefs(e.sourceRefs, `${owner}`);
  }

  // config 白名单（对拍 #38 等量：非白名单键/非法值一律拒绝）
  const cfg = g.config as Record<string, unknown> | undefined;
  if (cfg !== undefined) {
    if (!cfg || typeof cfg !== "object" || Array.isArray(cfg)) throw new Error("config 格式非法");
    for (const key of Object.keys(cfg)) {
      if (!["direction", "edgeLabels"].includes(key)) throw new Error(`config 含白名单之外的字段「${key}」`);
    }
    if (cfg.direction !== undefined && cfg.direction !== "TB" && cfg.direction !== "LR") throw new Error("config.direction 只接受 TB（从上到下）或 LR（从左到右）");
    if (cfg.edgeLabels !== undefined && typeof cfg.edgeLabels !== "boolean") throw new Error("config.edgeLabels 只接受布尔值");
  }
  // layout：位置只允许已存在节点、数值坐标
  const layout = g.layout as Record<string, unknown> | undefined;
  if (layout !== undefined) {
    if (!layout || typeof layout !== "object" || Array.isArray(layout)) throw new Error("layout 格式非法");
    const positions = layout.positions;
    if (positions !== undefined) {
      if (!positions || typeof positions !== "object" || Array.isArray(positions)) throw new Error("layout.positions 格式非法");
      for (const [id, pos] of Object.entries(positions as Record<string, unknown>)) {
        if (!nodeIds.has(id)) throw new Error(`布局位置引用了不存在的节点：${id}`);
        const p = pos as Record<string, unknown>;
        if (!p || typeof p.x !== "number" || typeof p.y !== "number" || !Number.isFinite(p.x) || !Number.isFinite(p.y)) {
          throw new Error(`节点 ${id} 的布局坐标必须是有限数值`);
        }
        if (Math.abs(p.x) > 1e6 || Math.abs(p.y) > 1e6) throw new Error(`节点 ${id} 的布局坐标越界`);
      }
    }
  }
  return g as unknown as GraphDoc;
}

// ---------- 确定性分层布局（自写 ≤100 行：最长路分层+层内定序+固定间距；环=剩余顺排不打死） ----------
export const LAYOUT_PARAMS = { NODE_W: 220, NODE_H: 84, GAP_LAYER: 72, GAP_SAME: 36, PAD: 32 } as const;

export function layoutGraph(
  nodes: Array<{ id: string; label: string }>,
  edges: Array<{ source: string; target: string }>,
  direction: "TB" | "LR" = "TB",
): { positions: Record<string, { x: number; y: number }>; width: number; height: number } {
  const { NODE_W, NODE_H, GAP_LAYER, GAP_SAME, PAD } = LAYOUT_PARAMS;
  const ids = nodes.map((n) => n.id);
  const idSet = new Set(ids);
  const indeg = new Map<string, number>(ids.map((id) => [id, 0]));
  const adj = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const e of edges) {
    if (idSet.has(e.source) && idSet.has(e.target)) {
      adj.get(e.source)!.push(e.target);
      indeg.set(e.target, (indeg.get(e.target) ?? 0) + 1);
    }
  }
  // 最长路分层：仅从入度 0 出发传播；环上节点（未达）统一顺排到最后一层之后
  const layer = new Map<string, number>();
  const queue = ids.filter((id) => indeg.get(id) === 0);
  for (const id of queue) layer.set(id, 0);
  let head = 0;
  while (head < queue.length) {
    const id = queue[head++]!;
    for (const t of adj.get(id)!) {
      const next = layer.get(id)! + 1;
      if (!layer.has(t) || layer.get(t)! < next) {
        layer.set(t, next);
        if (!queue.includes(t)) queue.push(t); // 队列可能重复入，靠 layer 取 max 收敛
      }
    }
  }
  let maxLayer = 0;
  for (const v of layer.values()) if (v > maxLayer) maxLayer = v;
  const overflow = maxLayer + 1;
  for (const n of nodes) if (!layer.has(n.id)) layer.set(n.id, overflow);
  // 层内定序：标签本地化序 + id 兜底（同输入恒同输出）；层内序号定横向位，层号定纵向位
  const groups = new Map<number, string[]>();
  for (const n of nodes) {
    const L = layer.get(n.id)!;
    if (!groups.has(L)) groups.set(L, []);
    groups.get(L)!.push(n.id);
  }
  const labelOf = new Map(nodes.map((n) => [n.id, n.label]));
  const positions: Record<string, { x: number; y: number }> = {};
  const layers = [...groups.keys()].sort((a, b) => a - b);
  let maxCross = 0;
  for (const L of layers) {
    const col = groups.get(L)!.sort((a, b) =>
      String(labelOf.get(a)).localeCompare(String(labelOf.get(b)), "zh-Hans-CN") || a.localeCompare(b));
    col.forEach((id, i) => {
      positions[id] = direction === "LR"
        ? { x: PAD + L * (NODE_W + GAP_LAYER), y: PAD + i * (NODE_H + GAP_SAME) }
        : { x: PAD + i * (NODE_W + GAP_SAME), y: PAD + L * (NODE_H + GAP_LAYER) };
    });
    if (col.length > maxCross) maxCross = col.length;
  }
  const alongLayers = layers.length;
  const width = direction === "LR"
    ? PAD * 2 + alongLayers * NODE_W + Math.max(0, alongLayers - 1) * GAP_LAYER
    : PAD * 2 + maxCross * NODE_W + Math.max(0, maxCross - 1) * GAP_SAME;
  const height = direction === "LR"
    ? PAD * 2 + maxCross * NODE_H + Math.max(0, maxCross - 1) * GAP_SAME
    : PAD * 2 + alongLayers * NODE_H + Math.max(0, alongLayers - 1) * GAP_LAYER;
  return { positions, width: Math.max(width, 200), height: Math.max(height, 160) };
}

// ---------- 规则建图（确定性：只从既有案件记录抽取，不造日期、不造状态、不猜关系） ----------
export type CaseRecordsInput = {
  title: string;
  parties?: Array<{ name: string }>;
  evidences?: Array<{ name: string; documentId?: string; filename?: string; locator?: string; quote?: string }>;
  /** 显式关系记录（名字对）；名字对不上的一律丢弃计数，不猜。 */
  relations?: Array<{ source: string; target: string; kind?: EdgeKind }>;
};

export function buildGraphFromCaseRecords(input: CaseRecordsInput): { schemaVersion: typeof GRAPH_SCHEMA_VERSION; title: string; nodes: GNode[]; edges: GEdge[]; config: GraphDoc["config"]; layout: GraphDoc["layout"] } {
  const nodes: GNode[] = [];
  const edges: GEdge[] = [];
  const nameToId = new Map<string, string>();
  const clip = (s: string, n: number) => (s.length > n ? s.slice(0, n) : s);
  (input.parties ?? []).forEach((p, i) => {
    const name = clip(String(p?.name ?? "").trim(), LIMITS.label);
    if (!name || nameToId.has(name)) return;
    const id = `p${i + 1}`;
    nameToId.set(name, id);
    nodes.push({ id, kind: "party", label: name, status: "uncertain", sourceRefs: [], provenance: "ai", lockedFields: [] });
  });
  (input.evidences ?? []).forEach((e, i) => {
    const name = clip(String(e?.name ?? "").trim(), LIMITS.label);
    if (!name) return;
    const ref: SourceRef = { filename: clip(String(e.filename ?? e.name ?? ""), LIMITS.filename) };
    if (e.documentId) ref.documentId = clip(e.documentId, LIMITS.id);
    if (e.locator) ref.locator = clip(e.locator, LIMITS.locator);
    if (e.quote) ref.quote = clip(e.quote, LIMITS.quote);
    nodes.push({ id: `e${i + 1}`, kind: "evidence", label: name, status: "uncertain", sourceRefs: ref.filename ? [ref] : [], provenance: "ai", lockedFields: [] });
  });
  let droppedRelations = 0;
  (input.relations ?? []).forEach((r, i) => {
    const s = nameToId.get(String(r?.source ?? "").trim());
    const t = nameToId.get(String(r?.target ?? "").trim());
    if (!s || !t) { droppedRelations += 1; return; }
    edges.push({ id: `r${i + 1}`, source: s, target: t, kind: r.kind ?? "prove", status: "uncertain", sourceRefs: [], provenance: "ai", lockedFields: [] });
  });
  return {
    schemaVersion: GRAPH_SCHEMA_VERSION,
    title: clip(input.title || "案件关系图", LIMITS.title),
    nodes,
    edges,
    config: { direction: "TB", edgeLabels: true },
    layout: { positions: {} },
  };
}

// ---------- 删除守卫（对拍 #19 等量：自动改动尊重锁定——被锁定关系相连的节点整体拒删；人工删除连带删边） ----------
export function removeNodeCascade(graph: { nodes: GNode[]; edges: GEdge[] }, nodeId: string, actor: "user" | "ai"): { nodes: GNode[]; edges: GEdge[] } {
  const touching = graph.edges.filter((e) => e.source === nodeId || e.target === nodeId);
  if (actor !== "user" && touching.some((e) => e.lockedFields.length > 0)) {
    throw new Error(`节点 ${nodeId} 与律师锁定的关系相连，自动改动不得删除（请先解除锁定或由律师手动处理）`);
  }
  return {
    nodes: graph.nodes.filter((n) => n.id !== nodeId),
    edges: graph.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
  };
}

/** 自动改动（actor!=="user"）触碰 lockedFields 内字段 → 拒绝；人工编辑始终直改。 */
export function lockedFieldGuard(existing: { lockedFields: string[] }, patch: Record<string, unknown>, actor: "user" | "ai"): void {
  if (actor === "user") return;
  for (const field of Object.keys(patch)) {
    if (existing.lockedFields.includes(field)) throw new Error(`字段「${field}」已由律师锁定，自动改动不得覆盖`);
  }
}

// ---------- 文件名净化（对拍 #29 等量：\/:*?"<>| 与换行→下划线、去首尾点、空回退） ----------
export function sanitizeGraphFilename(title: string, fallback = "关系图"): string {
  const cleaned = String(title ?? "")
    .replace(/[\\/:*?"<>|\r\n]+/g, "_")
    .replace(/^[\s._]+|[\s._]+$/g, "")
    .replace(/^_+|_+$/g, "")
    .slice(0, 60);
  return cleaned || fallback;
}
