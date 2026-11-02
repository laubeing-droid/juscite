// @juscite/flow · 能力注册表（RE-35 §3.3 声明式控权，C1-C5 域规则照录；实现与文案自写）。
// 注册合同 {id, displayName?, risk, idempotency, approval?, inputSchema}：
//   - risk 三级 read/write/external；幂等三级 read/idempotent-write/non-idempotent（external/non-idempotent 为预留枚举，v1 内置能力零实例——对拍行 18）
//   - approval:"implicit" 当且仅当 write+idempotent-write（C2/对拍行 17：违反注册即抛）——隐式审批=执行前置入 gate 队列（与既有 gate 节点机制的接缝）
//   - 描述符分层（C4/对拍行 19）：注册层存 inputSchema；对外描述符不透出；inputExample 由 schema 生成（示例值生成器自研）
import { inputExampleFromSchema, validateAgainstSchema } from "./dsl.mjs";

export const RISKS = ["read", "write", "external"];
export const IDEMPOTENCIES = ["read", "idempotent-write", "non-idempotent"];

export class CapabilityError extends Error {
  constructor(code, message) { super(message); this.name = "CapabilityError"; this.code = code; }
}

export function createCapabilityRegistry() {
  const byId = new Map();
  function assertApprovalPolicy(risk, idempotency, approval) {
    if (approval === undefined || approval === null) return;
    if (approval !== "implicit") throw new CapabilityError("VALIDATION", `approval 仅支持 "implicit"（显式审批走 gate 节点，不在能力层声明）`);
    if (!(risk === "write" && idempotency === "idempotent-write"))
      throw new CapabilityError("VALIDATION", 'approval:"implicit" 当且仅当 risk=write 且 idempotency=idempotent-write——非写幂等能力声明隐式审批，注册拒绝');
  }
  return {
    // 注册：域值校验+重复 id 拒绝（C1）；存储深冻结克隆（注册后不可变——改字段=重新注册新面）
    register({ id, displayName, risk, idempotency, approval, inputSchema }) {
      if (typeof id !== "string" || !id.trim()) throw new CapabilityError("VALIDATION", "能力 id 必填（非空字符串）");
      if (displayName !== undefined && (typeof displayName !== "string" || !displayName.trim() || displayName.trim().length > 200))
        throw new CapabilityError("VALIDATION", "displayName 可缺省；给了就必须是 trim 后 1-200 字的非空串");
      if (!RISKS.includes(risk)) throw new CapabilityError("VALIDATION", `risk 三级枚举：${RISKS.join("/")}`);
      if (!IDEMPOTENCIES.includes(idempotency)) throw new CapabilityError("VALIDATION", `idempotency 三级枚举：${IDEMPOTENCIES.join("/")}`);
      assertApprovalPolicy(risk, idempotency, approval);
      if (inputSchema !== undefined && typeof inputSchema !== "object") throw new CapabilityError("VALIDATION", "inputSchema 必须是对象 schema（注册层合同，不进描述符）");
      if (byId.has(id)) throw new CapabilityError("DUP_ID", `能力 id 已注册：${id}——重复 id 拒绝`);
      const frozen = Object.freeze({
        id, displayName: displayName?.trim() || undefined, risk, idempotency,
        approval: approval ?? null,
        inputSchema: inputSchema === undefined ? null : Object.freeze(structuredClone(inputSchema)),
      });
      byId.set(id, frozen);
      return frozen;
    },
    has(id) { return byId.has(id); },
    get(id) { return byId.get(id) ?? null; },
    // 能力输入校验（activity 执行前置：声明式控权的取数面）
    validateInput(id, input) {
      const cap = byId.get(id);
      if (!cap) throw new CapabilityError("UNKNOWN_CAPABILITY", `能力未注册：${id}`);
      if (!cap.inputSchema) return { ok: true };
      return validateAgainstSchema(input, cap.inputSchema);
    },
    // 对外描述符（C4）：不含 inputSchema；inputExample 由 schema 生成
    descriptors() {
      return [...byId.values()].map((c) => ({
        id: c.id,
        ...(c.displayName ? { displayName: c.displayName } : {}),
        risk: c.risk,
        idempotency: c.idempotency,
        ...(c.inputSchema ? { inputExample: inputExampleFromSchema(c.inputSchema) } : {}),
      }));
    },
    size() { return byId.size; },
  };
}

// v1 内置能力面（办案线六阶段消费用；全部自写命名）。
// external / non-idempotent 预留零实例（对拍行 18）：连接器面将来挂 external，不预写误导用例。
export function registerBuiltinLineCapabilities(registry) {
  const defs = [
    { id: "line.intake.materials", displayName: "材料进来（清单+解析）", risk: "read", idempotency: "read", inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] } },
    { id: "line.evidence.fix", displayName: "证据固定（哈希+页锚编号）", risk: "read", idempotency: "read", inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] } },
    { id: "line.facts.reconcile", displayName: "事实整理（勾稽表落账）", risk: "write", idempotency: "idempotent-write", approval: "implicit", inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] } },
    { id: "line.compute.ninecalc", displayName: "计算（规则组过渡档九计算器）", risk: "read", idempotency: "read", inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] } },
    { id: "line.drafting.assemble", displayName: "文书装配（模板组三件）", risk: "write", idempotency: "idempotent-write", approval: "implicit", inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] } },
    { id: "line.deadlines.calendar", displayName: "程序期限（日历账+期限表）", risk: "read", idempotency: "read", inputSchema: { type: "object", properties: { lineId: { type: "string" } }, required: ["lineId"] } },
  ];
  for (const d of defs) registry.register(d);
  return defs.map((d) => d.id);
}
