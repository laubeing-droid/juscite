# M2 桥转接层骨架 · 续作指南（2026-10-24 开工，主控亲做）

> **当前检查点（2026-10-26）**：M4 发送链已收口，源码 `ea8ee20`。本页早期“发送不发出 / 帧未到达 / barrier 阻断”均为历史诊断，续作以末尾收口段和取证文档为准。

> 定案（M1 收尾工作流尾洞）：上表面合同=mock 精修 10 面；下表面=oc28 serve；首批打通对话流 sendText→snapshot/delta 一轮往返；mock 降格回归桩。
> 本文件=断点交接面，续作照此，不必重侦察。

## 下表面（已打通；r12 波2.5 起=packages/juscite-runtime-adapters/opencode，产品层只经 packages/juscite-runtime-port 域面）

- 服务：oc28 serve 常驻 127.0.0.1:43127（dev 版 2.0.0-local，F-4 已知正常）；凭据=`%APPDATA%\Juscite\state\opencode\service-local.json`（url+password→basic auth opencode:password），loadCredentials() 自动读。
- 端点（契约=implementation/python/opencode_http.py，S0 已验）：
  - POST /api/session {id, directory}
  - POST /api/session/{sid}/prompt {id:调用方消息id, text, model:{id,providerID}, files?:[{uri,name}]}
  - GET /api/session/{sid}/message（轮询；返回数组或 {data:[]}，assistant 消息 content/parts 里 type:"text" 拼接）
  - GET /api/session/{sid}/inbox
- Provider：`deepseek-byok`（@ai-sdk/openai-compatible，models: deepseek-chat/deepseek-reasoner，key 已配于 %APPDATA%\Juscite\config\opencode\opencode.json——不入 git 不打印）。
- 流式：当前=轮询伪流式（600ms 增量 diff）；升级路径=oc28 SSE /api/event（M2 尾或 M3）。

## 上表面对话流四件套（zcodeAgent.ts :870-960，桥要实现）

1. `helloConversationV4(): HelloMessage`——握手；UI 会校验后回 clientHello（initializeConversationV4）。
2. `subscribeConversationV4(params): V4ConversationSubscribeResult`——订阅+首屏快照。
3. `sendConversationCommandV4(params): CommandAck`——**对话主入口**；params 含 CommandType（sendText 见 shared/src/zcode-protocol-v4/command.ts:92）。
4. `onDynamicConversationFrame(params: WorkspaceTarget): Event<ConversationTopicWireCandidate>`——workspace 级下行帧流（v4/conversation/frame topic），动态事件=(arg)=>Event（违者 ChannelServer 崩，M1 已付学费）。

帧 schema 位置：packages/shared/src/zcode-protocol-v4/（rows.ts 9 种行/delta.ts/wire.ts V4_WIRE_PROTOCOL_VERSION/snapshot.ts）；参考实现=tools/mock_host/sessionsindex.test.mts 的帧构造与 zod 严验手法（M1 工作流 4991c9f）。
已知 UI 消费噪声（验收记录）：sendConversationCommandV4 / onDynamicLocalTtftFacts / onDynamicConversationFrame / onAgentRuntimeLifecycle——UI 已在调，桥实现后噪声自消。

## 续作步骤（M2-2 帧投影组装）

1. 读 command.ts sendText 的 CommandPayloadMap + rows.ts 行类型 → 设计投影：OpenCode assistant 文本增量→V4 conversation frame（user 行=本地直造，assistant 行=delta 增量，toolCall/其他行 v1 占位）。
2. bridge_host.mjs：以 mock_host.mjs 为基座复制（10 面照抄），替换四件套为真实现（runtime adapter + 帧发射器 Emitter）；hello/sessions-index 面照 mock。
3. 端口策略：桥顶替 :3030（vite 代理不动）；mock_host 改 --port 3039 作回归桩（mock_host.mjs 的 PORT 参数化）。
4. 测试：tools/bridge/conversation.e2e.mts（ChannelClient hello→sendText→收帧断言）+ 真机（浏览器发一句话见流式回复）。
5. 完成标准（v4 §7 M2 节选）：真 oc28 进程下 UI 发一句话收到流式回复；失败=对照 mock 面补映射。

## 红线

合成问题/材料；key 不入 git 不入日志；测试输出只打回复文本；%APPDATA%\JusBench 零触碰。

## M4 发送链断点交接（2026-10-25 深夜，GUI 层最后一公里）

**现状**：桥侧九发修复全 commit（模型菜单 api.type/remote-projects/project 面/轮询拼接/system.info/snapshot busy 门禁/oauth 空态/事件面）；协议层全绿（e2e E2E_PASS+framecheck 帧过 UI 同款 schema 5/5+turn 全链 131-458 字回复推齐）。**卡点=GUI 渲染层**：真浏览器（IAB 实测复现）发送→命令接受→"加载中"→对话区不渲染行→25s+ 不恢复；桥日志显示 UI subscribe 后立即 unsubscribe（传输层放弃）。

**已排除**：帧 schema 非法（framecheck 过）；帧序乱序（busy 门禁后 snapshot 不插队）；模型菜单/路由/服务面缺失（全修）；oc28/DeepSeek（探针秒回）。

**嫌疑聚焦**：UI v4 订阅 choreography 的某环（barrier bind/activate 时序、recovery deadline、physical batch 语义）与桥实现不匹配——黑盒已到水底。

**黄金线索（下会话主攻）**：上游自带官方 host fixture=`zcode-oss/packages/desktop/scripts/mcp-apps-host-fixture/managed-environment.ts`（含 subscribeConversationV4 完整实现，官方用它测 UI=**能让 UI 完整工作的权威参考**）。两条路任选：
A. 直接跑官方 fixture 当宿主（UI 若活→逐面对比我们的桥找差异）；
B. 精读 conversationProjectionStore.ts（992 行 failRecovery）+agentConversationTransport.ts 全状态机逐环对齐。
优先 A——差异对比比通读快十倍。

## M4 发送链断点 v2（2026-10-26 凌晨，UI 编排最后一环）

**今晚质变**：⑫deliveryKind "event"→"online"（官方枚举只有 initial/online/recovery——event 一词让每帧被判 proto.frameAssemblyMetadataMismatch 全弃，**整晚转圈的总根源**）+⑬userInput origin 必填+⑭followupMode inputDisposition。**官方 TopicWireFrameAssembler 跑桥帧 5/5 全 complete**；真浏览器 UI 开始渲染行（错误条按钮出现=行渲染管线打通）。

**下一断点（精确）**：UI 命令编排 createSession→setFollowupMode 后 sendText 仍不发出（桥只收到前两条）。追查方向（按优先级）：①SessionPane.tsx 3655 prewarmTargetBeforeSend（draft 预热会话 promote 链）；②pendingCommandRegistry.acceptComposer 对 setFollowupMode ack 的消费（inputDisposition 之外的期待）；③useDraftConfigControl 三态初始化的 promotion 分支。武器：官方 fixture（mcp-apps-host-fixture）仍可用作时序参照；assemblecheck.mts 已是常备验证器。

## M4 发送链收口（CODEX，2026-10-26）

源码提交 `ea8ee200bc23fb80d1608a3cb3c55ef889d514cd`。核心断点是 `project.readTree()` 恒返空任务，UI 的 `commitCreatedTask` 因此一直不能提交详情切换。现已让首发形成任务目录行，并接通独立 sessions-index 订阅、权威快照/增量、分组登记和命令查询。

已验：可见 Chrome 两轮发送上屏（首轮 374 字，第二轮无前文重复）；同一桥进程下重开浏览器，原会话四行完全恢复；`conversation.e2e.mts` 22 项通过，两个 UI 合同测试文件 62 项通过。`ackActivationBarrier.ts` 临时日志已还原，源码卫生检查通过。

[完整取证与可复跑命令](../../docs/ui/M4-发送链浏览器动态取证-20261026.md)是本次验收的权威记录。仍为合成材料开发桥：会话映射、投影、命令回执和分组内存库不跨桥进程重启保存。CI、完整构建与 M4 其他模块未运行；未 push、PR 或发布。原有备份/探针保留，不 reset/clean。
