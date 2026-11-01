# M1-B mock Host 侦察结论与续作指南（2026-10-24 主控亲做，上下文交接面）

> 状态：第一版骨架已写（mock_host.mjs）；剩余=迭代填面直至 UI 点亮（M1-D）。
> 所有结论均有源码出处；续作直接照此，不必重侦察。

## 连接契约（已验，源码级）

1. **vite dev 代理已配好**（`packages/web/vite.config.ts:56-69`）：`/ws → ws://localhost:3030`、`/api → http://localhost:3030`。**mock 只需监听 3030**，零 vite 改动。
2. **UI 启动路径**（`packages/web/src/main.tsx:2375-2393`）：`resolveWebBootstrap()` → `fetch("/api/server-info")`（拿 workspaces[0].path/workspaceIdentity）→ `connectViaWebSocket(wsUrl)`（`ws(s)://{origin}/ws`）。
3. **服务端挂载骨架**（照抄 `zcode-oss/packages/server/src/http.ts:89-135`，只读参考未拎包）：
   ```js
   import { VSBuffer, SocketProtocol, ChannelServer } from "@zcode/rpc";        // worktree dist
   import { ServiceCollection } from "@zcode/services";
   import { ProxyChannel } from "@zcode/rpc";
   // ws connection → wrapWebSocket(ws)（~30 行样板，见 http.ts:40-85）
   // → new SocketProtocol(socket) → new ChannelServer(protocol, "server")
   // → services.exposeOnChannelServer(server) → 每 channel 用 ProxyChannel.fromService 自动映射方法
   ```
4. **注册机制**（`packages/services/src/collection.ts`）：`services.register(descriptor, instance)`；descriptor=`{channelName}` 常量在各接口文件尾部（`export const ISettingService = createServiceDescriptor(...ServiceChannels.Setting)`）。`exposeOnChannelServer` 遍历注册表自动 `registerChannel(channelName, ProxyChannel.fromService(instance))`。
5. **包产物**：`@zcode/rpc`/`@zcode/services` dist 已由 typecheck（tsc -b composite）产出，Node ESM 直接 import worktree 包（经 node_modules workspace 链接解析）。

## 服务面清单（mock 要注册的 channel）

- **IZCodeAgentService**（`services/src/zcode-agent/zcodeAgent.ts:613`，V4 主通道——UI 会话数据全走它）：bootstrap 必需 `initialize/getWorkspaceRuntimeIdentity/readWorkspacePresentation/prepareStorage/getStorageStartupState`；会话面 `createSession/resumeSession/listSessions(ZCodeSessionInfo[])/readSession/readSessionMessages`；**帧推送**（conversation/sessions-index，接口 Event 段 ~:900-1000）**待迭代填**——Proxy 兜底对 `on*` Event 属性无效（UI 会 subscribe），Event 必须返回真 Event 对象。
- **IZCodeSessionService**（`zcode-session/zcodeSession.ts:143`）：`initializeWorkspace/createSession/listSessions/...`（send 主路径已收敛 v4 sendText **命令**，不在此服务）。
- **ISettingService**（`setting/setting.ts:5`）：`get(): Promise<AppSettings>` / `update` / `updateDataBaseDir`；落 `%APPDATA%\Juscite\config\mock\setting.json`（**不碰 JusBench**）。
- **V4 命令管道（sendText/snapshot/delta）**：走 shared `zcode-protocol-v4/command.ts` 的 CommandEnvelope（zod）——**合成数据在运行时 import 这些 zod schema 构造**（`@zcode/shared/dist/zcode-protocol-v4/*`），字段名由 schema 保证，不手抄。rows/snapshot/delta/sessions-index schema 同目录。
- **terminal/git**：空 stub（ITerminalService/IGitService 注册返回空对象/空数组的实例）。
- **project readTree/attachmentPut**：所属服务待 UI 报错定位（file/fileWatcher/fs 或 project-catalog，见 accessor.ts 接口清单）。
- UI 侧自带 fallback stub 模式（main.tsx `createUnsupportedHomeOnlyService`），缺注册的 channel UI 端可能自带兜底——**迭代法：先起 mock+UI，看 console 报哪个 channel 缺，逐个补注册**。

## 迭代流程（M1-D 前置）

1. 起 mock：`node tools/mock_host/mock_host.mjs`（3030）
2. 起 UI：worktree 根 `corepack pnpm dev:web`（vite 5173，代理已配）
3. 浏览器开 http://localhost:5173 ，看 UI console + mock 侧日志，按缺失 channel/方法逐个补
4. 验收（v4 §7 M1）：四主题切换/Ctrl+K 四类目/新建事务草稿态/侧栏案件树（readTree 或 sessions-index）＋与 ZCode 并排截图比对

## 环境事实

- 主控亲做原因：账号模型并发=1，子代理五连挂（user/model concurrency），本时段子代理通道不可用
- M1-A 已提交：worktree m1 分支 `f2f6fc5`（typecheck 八包 0 错）；上游钉 `aac4755`
- `scripts/third-party-notices.mjs` 已从上游拷入（vite.config 引用）
