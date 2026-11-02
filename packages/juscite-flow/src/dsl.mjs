// @juscite/flow · DSL 编译器（RE-35-Flow工作流.md §3.2 自研子集，域值照录规格 §2 B1/B2/B3/B4/B5/B8/B9/B10/B11）。
// 结构参照对齐物（Andoo workflow-v2 schema）的域值，实现与文案全部自写；净室纪律：未读其代码，只按规格转写域值。
// 节点四型裁定（规格 §3.1）：agent/activity/map/gate——code/join/wait 三型登记不实施，编译期拒绝并给诊断。
// 诊断 ≤1000 条且带 path（B11/对拍行 15）；additionalProperties 禁止（B1 11 字段合同）。

export const FLOW_FORMAT_VERSION = 2;
export const AGENT_PROMPT_VERSION = "juscite-agent-core-v1"; // 钉定字符串版本（规格 §3.2；我方命名自写）
export const NODE_TYPES = ["agent", "activity", "map", "gate"]; // §3.1 四型
export const REJECTED_NODE_TYPES = ["code", "join", "wait"]; // 登记不实施（§3.8）——编译诊断给出明确拒绝面
export const THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh"]; // 六档照录（B4）
export const OUTPUT_VERIFY_KINDS = [
  "document.structure", "document.businesses", "document.business-scopes", "document.claims",
  "document.claim-matches", "document.claim-verification", "document.business-consistency",
]; // 七类产物前置校验器（B4）
export const DATA_REF_KINDS_NODE = ["literal", "input", "node-output"]; // v1 收敛三形态（§3.2）
export const DATA_REF_KINDS_RUNTIME = [...DATA_REF_KINDS_NODE, "node-output-ref"]; // agent runtimeBindings 第五形态（B8）
export const MODEL_POLICY_KINDS = ["inherit-session", "trusted-default"]; // B4 两型，缺省 inherit-session
export const MAX_DIAGNOSTICS = 1000; // B11：诊断 ≤1000 条

// 预算六项域值（B10 照录）
export const BUDGET_DOMAIN = {
  maxDocuments: [2, 100],
  maxMapItems: [1, 10000],
  maxAgentExecutions: [1, 10000],
  maxInputBytesPerNode: [1024, 16777216], // 1KiB-16MiB
  maxRunDurationMs: [1000, 604800000], // 1s-7 天
};
const MAX_TITLE = 200;
const MAX_DESCRIPTION = 2000;
const MAX_INSTRUCTION = 20000;
const MAX_TIMEOUT_MS = 2592000000; // 30 天（B3）
const MAX_NODES = 256;
const MAX_GROUPS = 128;
const MAX_DEPENDS = 64;
const MAX_TOOLS = 16;
const MAX_INPUTS = 64;
const MAX_ATTEMPTS = 8;
const MAX_MAP_CONCURRENCY = 32;
const MAX_GROUP_NODES = 256;

function diag(list, path, code, message) {
  if (list.length < MAX_DIAGNOSTICS) list.push({ path, code, message });
}

function isInt(v) { return typeof v === "number" && Number.isInteger(v); }
function inRange(v, [lo, hi]) { return isInt(v) && v >= lo && v <= hi; }
function isPlainObject(v) { return v !== null && typeof v === "object" && !Array.isArray(v); }

// ── 数据引用形态（B8/对拍行 12）：节点输入 literal/input/node-output；agent runtimeBindings 另支持
//    node-output-ref；item 仅 map worker 输入可用（运行时内部形态，DSL 顶层仍不直写）──
export function validateDataRef(ref, list, path, { allowRuntime = false, allowItem = false } = {}) {
  if (!isPlainObject(ref)) { diag(list, path, "REF_SHAPE", "数据引用必须是对象 {kind, …}"); return false; }
  const kinds = allowRuntime ? DATA_REF_KINDS_RUNTIME : DATA_REF_KINDS_NODE;
  const kind = ref.kind;
  if (!kinds.includes(kind) && !(allowItem && kind === "item")) {
    diag(list, path, "REF_KIND", `数据引用 kind 仅限 ${kinds.join("/")}${allowRuntime ? "+node-output-ref" : ""}${allowItem ? "+item（仅 map worker 内部）" : ""}`);
    return false;
  }
  if (kind === "literal") { if (!("value" in ref)) { diag(list, path, "REF_LITERAL", "literal 引用必须带 value"); return false; } return true; }
  if (kind === "input") return true; // path 可选
  if (kind === "node-output" || kind === "node-output-ref") {
    if (typeof ref.nodeId !== "string" || !ref.nodeId) { diag(list, path, "REF_NODE_OUTPUT", `${kind} 引用必须带 nodeId`); return false; }
    return true;
  }
  return true;
}

function validateCommonNode(node, list, path, seenIds) {
  if (typeof node.id !== "string" || !node.id) { diag(list, `${path}.id`, "NODE_ID", "节点 id 必填（非空字符串）"); return false; }
  if (seenIds.has(node.id)) diag(list, `${path}.id`, "NODE_DUP", `节点 id 重复：${node.id}`);
  seenIds.add(node.id);
  if (typeof node.title !== "string" || !node.title.length || node.title.length > MAX_TITLE)
    diag(list, `${path}.title`, "NODE_TITLE", `节点 title 必填且 1-${MAX_TITLE} 字`);
  if ("dependsOn" in node) {
    if (!Array.isArray(node.dependsOn)) diag(list, `${path}.dependsOn`, "NODE_DEPS", "dependsOn 必须是字符串数组");
    else {
      if (node.dependsOn.length > MAX_DEPENDS) diag(list, `${path}.dependsOn`, "NODE_DEPS_MAX", `dependsOn 上限 ${MAX_DEPENDS} 项`);
      if (new Set(node.dependsOn).size !== node.dependsOn.length) diag(list, `${path}.dependsOn`, "NODE_DEPS_DUP", "dependsOn 必须去重");
    }
  }
  if ("timeoutMs" in node && !(isInt(node.timeoutMs) && node.timeoutMs > 0 && node.timeoutMs <= MAX_TIMEOUT_MS))
    diag(list, `${path}.timeoutMs`, "NODE_TIMEOUT", `timeoutMs 域 (0, ${MAX_TIMEOUT_MS}]（≤30 天）`);
  if ("retry" in node) {
    const r = node.retry;
    if (!isPlainObject(r)) diag(list, `${path}.retry`, "NODE_RETRY", "retry 必须是对象");
    else {
      if (!inRange(r.maxAttempts, [1, 10])) diag(list, `${path}.retry.maxAttempts`, "NODE_RETRY_MAX", "retry.maxAttempts 域 [1,10]");
      if (!inRange(r.backoffMs, [0, 300000])) diag(list, `${path}.retry.backoffMs`, "NODE_RETRY_BACKOFF", "retry.backoffMs 域 [0,300000]");
      for (const k of Object.keys(r)) if (k !== "maxAttempts" && k !== "backoffMs") diag(list, `${path}.retry.${k}`, "NODE_RETRY_KEY", `retry 未声明字段 ${k}`);
    }
  }
  return true;
}

function validateAgentNode(node, list, path, opts = {}) {
  if (typeof node.instruction !== "string" || !node.instruction.length || node.instruction.length > MAX_INSTRUCTION)
    diag(list, `${path}.instruction`, "AGENT_INSTRUCTION", `instruction 必填且 1-${MAX_INSTRUCTION} 字`);
  if ("systemPromptVersion" in node && node.systemPromptVersion !== AGENT_PROMPT_VERSION)
    diag(list, `${path}.systemPromptVersion`, "AGENT_PROMPT_VERSION", `systemPromptVersion 仅支持钉定版本 ${AGENT_PROMPT_VERSION}`);
  if ("inputs" in node) {
    if (!Array.isArray(node.inputs) || node.inputs.length > MAX_INPUTS) diag(list, `${path}.inputs`, "AGENT_INPUTS", `inputs 上限 ${MAX_INPUTS} 项`);
    else node.inputs.forEach((ref, i) => validateDataRef(ref, list, `${path}.inputs[${i}]`, opts));
  }
  if ("runtimeBindings" in node) {
    const rb = node.runtimeBindings;
    if (!isPlainObject(rb) || !Array.isArray(rb.bindings) || rb.bindings.length > MAX_INPUTS)
      diag(list, `${path}.runtimeBindings`, "AGENT_RB", "runtimeBindings 必须是 {bindings:[≤64]}");
    else rb.bindings.forEach((b, i) => {
      if (!isPlainObject(b) || typeof b.name !== "string" || !b.name) diag(list, `${path}.runtimeBindings.bindings[${i}]`, "AGENT_RB_NAME", "绑定必须带 name");
      else validateDataRef(b.value ?? b.ref, list, `${path}.runtimeBindings.bindings[${i}]`, { allowRuntime: true, allowItem: opts.allowItem === true });
    });
  }
  if ("tools" in node) {
    if (!Array.isArray(node.tools) || node.tools.length > MAX_TOOLS) diag(list, `${path}.tools`, "AGENT_TOOLS", `tools 上限 ${MAX_TOOLS} 项`);
    else if (new Set(node.tools).size !== node.tools.length) diag(list, `${path}.tools`, "AGENT_TOOLS_DUP", "tools 必须去重");
  }
  if ("modelPolicy" in node) {
    const mp = node.modelPolicy;
    if (!isPlainObject(mp) || !MODEL_POLICY_KINDS.includes(mp.kind)) diag(list, `${path}.modelPolicy`, "AGENT_MODEL_POLICY", `modelPolicy.kind 仅限 ${MODEL_POLICY_KINDS.join("/")}`);
  }
  if ("thinkingLevel" in node && !THINKING_LEVELS.includes(node.thinkingLevel))
    diag(list, `${path}.thinkingLevel`, "AGENT_THINKING", `thinkingLevel 六档：${THINKING_LEVELS.join("/")}`);
  if (!isPlainObject(node.outputSchema)) { diag(list, `${path}.outputSchema`, "AGENT_OUTPUT_SCHEMA", "agent 节点 outputSchema 必填（对象）"); }
  if ("outputSubmissionAttempts" in node && !inRange(node.outputSubmissionAttempts, [1, MAX_ATTEMPTS]))
    diag(list, `${path}.outputSubmissionAttempts`, "AGENT_ATTEMPTS", `outputSubmissionAttempts 域 [1,${MAX_ATTEMPTS}]`);
  if ("outputVerify" in node && !OUTPUT_VERIFY_KINDS.includes(node.outputVerify))
    diag(list, `${path}.outputVerify`, "AGENT_OUTPUT_VERIFY", `outputVerify 七类枚举：${OUTPUT_VERIFY_KINDS.join("/")}`);
}

function validateActivityNode(node, list, path, opts = {}) {
  if (typeof node.capability !== "string" || !node.capability)
    diag(list, `${path}.capability`, "ACT_CAPABILITY", "activity 节点必须声明 capability（能力 id）");
  if ("input" in node && !isPlainObject(node.input)) diag(list, `${path}.input`, "ACT_INPUT", "activity input 必须是 {字段: 数据引用} 映射");
  else if (isPlainObject(node.input))
    for (const [k, ref] of Object.entries(node.input)) validateDataRef(ref, list, `${path}.input.${k}`, opts);
}

function validateMapNode(node, list, path) {
  if (!("items" in node)) diag(list, `${path}.items`, "MAP_ITEMS", "map 节点必须声明 items（数据引用）");
  else validateDataRef(node.items, list, `${path}.items`);
  if (!inRange(node.maxConcurrency, [1, MAX_MAP_CONCURRENCY])) diag(list, `${path}.maxConcurrency`, "MAP_CONCURRENCY", `maxConcurrency 域 [1,${MAX_MAP_CONCURRENCY}]`);
  const w = node.worker;
  if (!isPlainObject(w) || (w.type !== "activity" && w.type !== "agent")) { diag(list, `${path}.worker`, "MAP_WORKER", "worker 必须是 activity|agent 二选一"); return; }
  if (w.type === "activity") validateActivityNode(w, list, `${path}.worker`, { allowItem: true });
  else validateAgentNode(w, list, `${path}.worker`, { allowItem: true });
}

function validateGateNode(node, list, path) {
  if (typeof node.gateKind !== "string" || !node.gateKind) diag(list, `${path}.gateKind`, "GATE_KIND", "gate 节点必须声明 gateKind（§3.6 v1 三动作：process/transfer/force-transfer 语义承载）");
  if (!isPlainObject(node.request)) diag(list, `${path}.request`, "GATE_REQUEST", "gate 节点必须带 request 对象（待审事项）");
}

function validateBudget(budget, list, path) {
  if (!isPlainObject(budget)) { diag(list, path, "BUDGET_SHAPE", "budget 必须是对象"); return; }
  for (const [k, [lo, hi]] of Object.entries(BUDGET_DOMAIN)) {
    if (k in budget && !inRange(budget[k], [lo, hi])) diag(list, `${path}.${k}`, "BUDGET_DOMAIN", `budget.${k} 域 [${lo},${hi}]`);
  }
  if ("runDurationPolicy" in budget) {
    const p = budget.runDurationPolicy;
    if (!isPlainObject(p) || p.kind !== "input-files") { diag(list, `${path}.runDurationPolicy`, "BUDGET_POLICY", "runDurationPolicy.kind 必须是 input-files"); return; }
    for (const k of ["baseMs", "perItemMs", "perMiBMs", "minMs", "maxMs"]) {
      if (!isInt(p[k]) || p[k] < 0) diag(list, `${path}.runDurationPolicy.${k}`, "BUDGET_POLICY_FIELD", `runDurationPolicy.${k} 必须是非负整数`);
    }
  }
  for (const k of Object.keys(budget)) {
    if (!(k in BUDGET_DOMAIN) && k !== "runDurationPolicy") diag(list, `${path}.${k}`, "BUDGET_KEY", `budget 未声明字段 ${k}`);
  }
}

const DEF_KEYS = new Set(["formatVersion", "id", "version", "title", "description", "inputSchema", "budget", "nodes", "groups", "output", "outputSchema"]);

// ── 编译（B1/B11/对拍行 5/15）：域值校验 + 诊断清单（带 path，≤1000 条）；失败 ok:false ──
export function compileDefinition(def) {
  const list = [];
  if (!isPlainObject(def)) return { ok: false, diagnostics: [{ path: "", code: "DEF_SHAPE", message: "流程定义必须是对象" }], definition: null };
  for (const k of Object.keys(def)) if (!DEF_KEYS.has(k)) diag(list, k, "DEF_KEY", `定义未声明字段 ${k}（additionalProperties 禁止，11 字段合同）`);
  if (def.formatVersion !== FLOW_FORMAT_VERSION) diag(list, "formatVersion", "DEF_VERSION", `formatVersion 必须是 ${FLOW_FORMAT_VERSION}`);
  if (typeof def.id !== "string" || !def.id) diag(list, "id", "DEF_ID", "定义 id 必填");
  if (!(isInt(def.version) && def.version >= 1)) diag(list, "version", "DEF_VERSION_FIELD", "version 必须 ≥1 整数");
  if (typeof def.title !== "string" || !def.title.length || def.title.length > MAX_TITLE) diag(list, "title", "DEF_TITLE", `title 必填且 1-${MAX_TITLE} 字`);
  if ("description" in def && (typeof def.description !== "string" || def.description.length > MAX_DESCRIPTION)) diag(list, "description", "DEF_DESC", `description ≤${MAX_DESCRIPTION} 字`);
  if (!isPlainObject(def.inputSchema)) diag(list, "inputSchema", "DEF_INPUT_SCHEMA", "inputSchema 必填（对象 schema）——流程输入合同");
  if ("budget" in def) validateBudget(def.budget, list, "budget");
  if (!Array.isArray(def.nodes) || def.nodes.length < 1) {
    diag(list, "nodes", "DEF_NODES", "nodes 必填（1-256 个节点）");
    return { ok: false, diagnostics: list, definition: null };
  }
  if (def.nodes.length > MAX_NODES) diag(list, "nodes", "DEF_NODES_MAX", `nodes 上限 ${MAX_NODES} 个`);
  const seenIds = new Set();
  const byId = new Map();
  def.nodes.slice(0, MAX_NODES).forEach((node, i) => {
    const path = `nodes[${i}]`;
    if (!isPlainObject(node)) { diag(list, path, "NODE_SHAPE", "节点必须是对象"); return; }
    for (const k of Object.keys(node)) {
      const known = ["id", "title", "dependsOn", "timeoutMs", "retry", "type", "instruction", "systemPromptVersion", "inputs", "runtimeBindings", "tools", "modelPolicy", "thinkingLevel", "outputSchema", "outputSubmissionAttempts", "outputVerify", "capability", "input", "items", "maxConcurrency", "worker", "gateKind", "request"];
      if (!known.includes(k)) diag(list, `${path}.${k}`, "NODE_KEY", `节点未声明字段 ${k}`);
    }
    if (!validateCommonNode(node, list, path, seenIds)) return;
    if (!NODE_TYPES.includes(node.type)) {
      if (REJECTED_NODE_TYPES.includes(node.type))
        diag(list, `${path}.type`, "NODE_TYPE_REJECTED", `节点型别 ${node.type} 登记不实施（§3.8：四型收敛），DSL 拒绝——如需该语义请另立施工件`);
      else diag(list, `${path}.type`, "NODE_TYPE", `节点型别仅限 ${NODE_TYPES.join("/")}`);
      return;
    }
    byId.set(node.id, node);
    if (node.type === "agent") validateAgentNode(node, list, path);
    else if (node.type === "activity") validateActivityNode(node, list, path);
    else if (node.type === "map") validateMapNode(node, list, path);
    else validateGateNode(node, list, path);
  });
  // dependsOn 引用闭合 + 环检测（执行序只由 dependsOn 决定，B9）
  for (const node of def.nodes) {
    if (!Array.isArray(node.dependsOn)) continue;
    for (const dep of node.dependsOn) if (!byId.has(dep)) diag(list, `nodes[${node.id}].dependsOn`, "NODE_DEP_MISSING", `dependsOn 引用不存在的节点 ${dep}`);
  }
  const order = topoOrder(def.nodes, byId);
  if (order === null) diag(list, "nodes", "NODE_CYCLE", "dependsOn 存在环——执行序不可定");
  if ("groups" in def) {
    if (!Array.isArray(def.groups) || def.groups.length > MAX_GROUPS) diag(list, "groups", "GROUPS_MAX", `groups 上限 ${MAX_GROUPS} 组`);
    else {
      const groupIds = new Set();
      def.groups.forEach((g, i) => {
        const p = `groups[${i}]`;
        if (!isPlainObject(g)) { diag(list, p, "GROUP_SHAPE", "组必须是对象 {id,title,nodeIds}"); return; }
        for (const k of Object.keys(g)) if (!["id", "title", "nodeIds"].includes(k)) diag(list, `${p}.${k}`, "GROUP_KEY", `组未声明字段 ${k}`);
        if (typeof g.id !== "string" || !g.id) diag(list, `${p}.id`, "GROUP_ID", "组 id 必填");
        else if (groupIds.has(g.id)) diag(list, `${p}.id`, "GROUP_DUP", `组 id 重复：${g.id}`);
        groupIds.add(g.id);
        if (typeof g.title !== "string" || !g.title.length || g.title.length > MAX_TITLE) diag(list, `${p}.title`, "GROUP_TITLE", `组 title 必填且 1-${MAX_TITLE} 字`);
        if (!Array.isArray(g.nodeIds) || g.nodeIds.length < 2) diag(list, `${p}.nodeIds`, "GROUP_NODES_MIN", "组 nodeIds 至少 2 项（仅用于界面展示的连续节点分组）");
        else {
          if (g.nodeIds.length > MAX_GROUP_NODES) diag(list, `${p}.nodeIds`, "GROUP_NODES_MAX", `组 nodeIds 上限 ${MAX_GROUP_NODES} 项`);
          if (new Set(g.nodeIds).size !== g.nodeIds.length) diag(list, `${p}.nodeIds`, "GROUP_NODES_DUP", "组 nodeIds 必须去重");
          for (const nid of g.nodeIds) if (!byId.has(nid)) diag(list, `${p}.nodeIds`, "GROUP_NODE_MISSING", `组引用不存在的节点 ${nid}`);
        }
      });
    }
  }
  return { ok: list.length === 0, diagnostics: list, definition: list.length === 0 ? def : null, order };
}

// Kahn 拓扑序（groups 不参与——B9：执行依赖只由 dependsOn 决定）
export function topoOrder(nodes, byId) {
  const indeg = new Map();
  const out = new Map();
  for (const n of nodes) { indeg.set(n.id, 0); out.set(n.id, []); }
  for (const n of nodes) {
    for (const dep of n.dependsOn ?? []) {
      if (!byId.has(dep)) continue;
      indeg.set(n.id, indeg.get(n.id) + 1);
      out.get(dep).push(n.id);
    }
  }
  const ready = nodes.filter((n) => indeg.get(n.id) === 0).map((n) => n.id);
  const order = [];
  while (ready.length) {
    const id = ready.shift();
    order.push(id);
    for (const nxt of out.get(id)) { indeg.set(nxt, indeg.get(nxt) - 1); if (indeg.get(nxt) === 0) ready.push(nxt); }
  }
  return order.length === nodes.length ? order : null;
}

// 计划能力集合（C5 运行前放权）：activity 节点（含 map worker=activity）声明的 capability 去重集合
export function plannedCapabilities(def) {
  const set = new Set();
  for (const n of def.nodes) {
    if (n.type === "activity" && typeof n.capability === "string") set.add(n.capability);
    if (n.type === "map" && isPlainObject(n.worker) && n.worker.type === "activity" && typeof n.worker.capability === "string") set.add(n.worker.capability);
  }
  return [...set];
}

// agent 执行数预算面（B10 maxAgentExecutions）：agent 节点 + map worker=agent
export function plannedAgentExecutions(def) {
  let c = 0;
  for (const n of def.nodes) {
    if (n.type === "agent") c++;
    if (n.type === "map" && isPlainObject(n.worker) && n.worker.type === "agent") c++;
  }
  return c;
}

// runDurationPolicy 体量估算（B10）：按输入文件件数与体量估运行时限，夹回 [minMs, min(maxMs, maxRunDurationMs)]
export function estimateRunDurationMs(policy, inputFiles) {
  const files = Array.isArray(inputFiles) ? inputFiles : [];
  const totalMiB = files.reduce((s, f) => s + (Number(f?.sizeMiB) || 0), 0);
  const est = policy.baseMs + files.length * policy.perItemMs + totalMiB * policy.perMiBMs;
  return Math.min(Math.max(est, policy.minMs), policy.maxMs);
}

// ── 轻量 schema 校验器（自写，能力 inputSchema 与 agent outputSchema 共用）：type/required/properties/items/enum ──
export function validateAgainstSchema(value, schema) {
  if (!isPlainObject(schema)) return { ok: true };
  const errs = [];
  const walk = (v, s, path) => {
    if (s.type === "object") {
      if (!isPlainObject(v)) { errs.push(`${path || "value"} 应为对象`); return; }
      for (const req of s.required ?? []) if (!(req in v)) errs.push(`${path || "value"} 缺必填字段 ${req}`);
      for (const [k, sub] of Object.entries(s.properties ?? {})) if (k in v) walk(v[k], sub, path ? `${path}.${k}` : k);
      return;
    }
    if (s.type === "array") {
      if (!Array.isArray(v)) { errs.push(`${path || "value"} 应为数组`); return; }
      if (s.items) v.forEach((item, i) => walk(item, s.items, `${path}[${i}]`));
      return;
    }
    if (s.type === "string" && typeof v !== "string") errs.push(`${path || "value"} 应为字符串`);
    if (s.type === "number" && typeof v !== "number") errs.push(`${path || "value"} 应为数值`);
    if (s.type === "integer" && !(typeof v === "number" && Number.isInteger(v))) errs.push(`${path || "value"} 应为整数`);
    if (s.type === "boolean" && typeof v !== "boolean") errs.push(`${path || "value"} 应为布尔`);
    if (Array.isArray(s.enum) && !s.enum.includes(v)) errs.push(`${path || "value"} 不在枚举内`);
  };
  walk(value, schema, "");
  return { ok: errs.length === 0, errors: errs };
}

// 描述符 inputExample 生成（C4/对拍行 19：示例值生成器自研，不从竞品拷贝）
export function inputExampleFromSchema(schema) {
  if (!isPlainObject(schema)) return null;
  const gen = (s) => {
    if (!isPlainObject(s)) return null;
    if (Array.isArray(s.enum)) return s.enum[0] ?? null;
    switch (s.type) {
      case "object": {
        const out = {};
        for (const [k, sub] of Object.entries(s.properties ?? {})) out[k] = gen(sub);
        return out;
      }
      case "array": return [gen(s.items ?? {})].filter((x) => x !== null);
      case "string": return "示例文本";
      case "number": case "integer": return 0;
      case "boolean": return false;
      default: return null;
    }
  };
  return gen(schema);
}
