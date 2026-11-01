// L1a runtime-port（r12 波2.5 · 设计 §一 L1a）：按我方域模型定义的 runtime 最小能力合同。
// 纪律：
//   ①接口不照抄任何 runtime 的 API——方法名/事件名/参数形状一律我方域词；
//   ②协议类型一律 import 树内真源（@zcode/shared 的 model-selection / zcode-protocol-v4），
//     禁止在本包重定义任何协议形状（§八原则1）；
//   ③产品层（桥）只认本包接口；换底座=新增一个 adapter（§一 L1b），产品层零动。
// 本包只放类型+适配基类，零运行时依赖（类型 import 编译期擦除）。
import type { ModelSelection } from "../../shared/src/model-selection.js";
import type { Timestamp } from "../../shared/src/zcode-protocol-v4/index.js";

// ── 七能力面的支撑类型 ──

/** 生命周期健康态；detail 只做人读诊断，不进协议。 */
export interface RuntimeHealth {
  ok: boolean;
  detail?: string;
}

/** ②会话创建入参：sessionId=调用方持久化的会话主键；model 用 V4 真源 ModelSelection。 */
export interface RuntimeSessionSpec {
  sessionId: string;
  workspacePath: string;
  title: string;
  model: ModelSelection;
}

export interface RuntimeSessionRef {
  runtimeSessionId: string;
}

/** ③发送：clientMessageId=调用方持久化的消息 id（对账/重放凭据）。 */
export interface RuntimeOutboundMessage {
  clientMessageId: string;
  text: string;
}

/**
 * ④事件流增量：域事件词表（不照抄任何 runtime 的 wire 事件名）。
 * stream.up/down=事件流连接起落；turn.*=回合文本/步进/成败；textDelta 仅 turn.text.delta 携带。
 */
export type RuntimeEventKind =
  | "stream.up"
  | "stream.down"
  | "turn.text.started"
  | "turn.text.delta"
  | "turn.text.ended"
  | "turn.step.ended"
  | "turn.succeeded"
  | "turn.failed";

export interface RuntimeEvent {
  kind: RuntimeEventKind;
  runtimeSessionId: string;
  at: Timestamp;
  textDelta?: string;
  detail?: string;
}

export interface RuntimeStreamHooks {
  log?: (line: string) => void;
}

/** 事件流句柄：close=永久关闭；drop=只断当前连接（自动重连，供注入断线）。 */
export interface RuntimeEventStreamHandle {
  close(): void;
  drop(): void;
}

/** 工具调用域形状（与产品 researchModel 提取产物同形）。 */
export interface RuntimeToolCall {
  name: string;
  input: string;
  output: string;
  error?: string;
}

/**
 * ④对账拉取：回合转录的域形状（文本/推理/工具步已按域归一，wire part 形状不出 adapter）。
 * 序=runtime 返回原序（排序/去重是产品对账逻辑）。
 */
export interface RuntimeTranscriptEntry {
  messageId: string;
  role: "user" | "assistant";
  text: string;
  reasoning?: string;
  toolCalls?: RuntimeToolCall[];
  createdAt: Timestamp;
  completedAt?: Timestamp;
  error?: string;
}

/** ⑤工具注册入参（运行时能力声明，非 V4 wire 形状）。 */
export interface RuntimeToolSpec {
  name: string;
  description: string;
  parameters?: unknown;
}

/** ⑥权限门：runtime 请求放行某工具/动作时回调；resolve(true)=放行。 */
export interface RuntimePermissionRequest {
  runtimeSessionId: string;
  tool: string;
  summary: string;
  respond(allow: boolean): void;
}

export type RuntimePermissionGate = (request: RuntimePermissionRequest) => Promise<boolean>;

// ── 端口合同（七能力面）──

/**
 * 我方域模型的 runtime 最小能力面：
 * ①生命周期 start/shutdown/health ②会话创建 ③发送 ④事件流增量（订阅+对账拉取）
 * ⑤工具注册 ⑥权限门 ⑦取消。
 */
export interface RuntimePort {
  readonly runtimeId: string;
  start(): Promise<void>;
  shutdown(): Promise<void>;
  health(): Promise<RuntimeHealth>;
  createSession(spec: RuntimeSessionSpec): Promise<RuntimeSessionRef>;
  send(runtimeSessionId: string, message: RuntimeOutboundMessage): Promise<void>;
  subscribeEvents(listener: (event: RuntimeEvent) => void, hooks?: RuntimeStreamHooks): RuntimeEventStreamHandle;
  pullTranscript(runtimeSessionId: string): Promise<RuntimeTranscriptEntry[]>;
  registerTools(tools: readonly RuntimeToolSpec[]): Promise<void>;
  setPermissionGate(gate: RuntimePermissionGate | null): void;
  cancelTurn(runtimeSessionId: string, clientMessageId?: string): Promise<void>;
}

/** adapter 未开放某能力时抛出（fail-fast，不伪造成功）。 */
export class UnsupportedCapabilityError extends Error {
  constructor(capability: string, runtimeId: string) {
    super(`runtime "${runtimeId}" 未开放能力 ${capability}（当前绑定未接线）`);
    this.name = "UnsupportedCapabilityError";
  }
}

/**
 * 适配基类：adapter 只覆写自己真支持的能力，未覆写的一律显式抛
 * UnsupportedCapabilityError（诚实能力对照表的机制化起点，D6）。
 */
export abstract class RuntimeAdapterBase implements RuntimePort {
  abstract readonly runtimeId: string;
  /** 外置 runtime 进程不由 binding 拥有时，start/shutdown 缺省=no-op。 */
  async start(): Promise<void> {}
  async shutdown(): Promise<void> {}
  async health(): Promise<RuntimeHealth> { throw this.unsupported("health"); }
  async createSession(_spec: RuntimeSessionSpec): Promise<RuntimeSessionRef> { throw this.unsupported("createSession"); }
  async send(_runtimeSessionId: string, _message: RuntimeOutboundMessage): Promise<void> { throw this.unsupported("send"); }
  subscribeEvents(_listener: (event: RuntimeEvent) => void, _hooks?: RuntimeStreamHooks): RuntimeEventStreamHandle { throw this.unsupported("subscribeEvents"); }
  async pullTranscript(_runtimeSessionId: string): Promise<RuntimeTranscriptEntry[]> { throw this.unsupported("pullTranscript"); }
  async registerTools(_tools: readonly RuntimeToolSpec[]): Promise<void> { throw this.unsupported("registerTools"); }
  setPermissionGate(_gate: RuntimePermissionGate | null): void { throw this.unsupported("setPermissionGate"); }
  async cancelTurn(_runtimeSessionId: string, _clientMessageId?: string): Promise<void> { throw this.unsupported("cancelTurn"); }
  protected unsupported(capability: string): UnsupportedCapabilityError {
    return new UnsupportedCapabilityError(capability, this.runtimeId);
  }
}
