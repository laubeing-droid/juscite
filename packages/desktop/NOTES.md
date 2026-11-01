# Juscite Desktop 壳（M3 施工账）

上游源：zcode-oss @ `aac4755`（v3.15.1）——拎包钉版，冻版不追（v4 §12.4）。
施工依据：`docs/ui/UI施工方案-v4.md` §1.3 桌面壳砍法 + 战役二 M3 单。

## 砍账（desktop/src/main 233 → 174 文件）

- 砍整目录：`mcpUserDirectory/`（7；连接器走技能内配置，mcp-sync=空 stub）。
- ARMS/遥测 13 + 卫星：appARMSBootstrap、appTelemetryRuntime、armsBrowserPerfLoadNudge、
  armsEventRedaction、armsUserIdentity、desktopArmsCustomEvent、desktopMcpTelemetry、
  desktopNetworkTelemetry、desktopRemoteUsageArmsTelemetry、desktopResourceTelemetry、
  desktopStabilityTelemetry、desktopTelemetryFetch、desktopZCodeDataSizeTelemetry、
  databaseStartupTelemetry、networkTelemetryAggregator、localTtft*3、rendererActionTrace*4、
  startupTelemetryDelivery、zcodeDataSizeTelemetryState、taskRealtimeBus（宿主事件中继）、
  shared/arms*3、renderer arms/localTtft/userActionTrace、preload armsRumBridgeForward。
- CUA 11：cua*6、desktopCua*3、windowsCuaOperationIndicator*2（+preload/renderer 面板）。
- webRemoteControl 9（main）——终裁丢弃（云中继链整体废弃）。
- OAuth/深链 5：desktopOAuthDeepLink、desktopDeepLinkUrl、desktopSecondInstanceDeepLink、
  desktopLinuxDeepLinkRegistration、startupWorkspaceDeepLinkGate（单实例锁保留聚焦语义）。
- 随宿主废弃：src/host/ 整目录（tsconfig.host.json 留空壳项目仅保闸门清单可解析）（@zcode/server 打包宿主）、desktopRemoteSessions、
  desktopMainIpcRemote、desktopWslTargetResolver、desktopContextPromptRollout、e2e 面
  （tsconfig.e2e/wdio/test/ 1514 文件未拎入）。
- 保留闸后件：browserView 31、Chrome 数据簇（chrome*、browserDataManager）、pluginSandbox、
  resourceManager/processResource、托盘/崩溃采集/desktopCronScheduler（派发目标暂空——
  待桥 cron 映射，v4 §2）、autoUpdater（换源说明见下）。

## 换宿主（v4 §1.3 换芯点）

- `desktopHostProcess.ts` 重写：应用级单例桥进程 `spawn(Electron二进制, [tsx cli, tools/bridge/bridge_host.mjs])`
  （ELECTRON_RUN_AS_NODE=1，BRIDGE_PORT 默认 3030）；renderer 经 query `bridgeWsUrl`
  直连 `ws://127.0.0.1:3030/ws`（`connectViaWebSocket`），MessagePortMain 服务端口链废弃。
- oc28 检测：读 `%APPDATA%\Juscite\state\opencode\service-local.json`，HTTP 探针
  `GET <url>/api/info`（凭据不落日志）；未运行→dialog 提示"手动启动 oc28 serve"，
  **不自动拉起**（spawn oc28 留待用户裁决）。
- `desktopDataBaseDirBootstrap`：settings 落 `%APPDATA%\Juscite\config\setting.json`，
  无显式 dataBaseDir 时默认 `%APPDATA%\Juscite\data`（services 在其下拼 `.zcode/v2`，
  内层段由 @zcode/services 收口，非本包轨道）。
- package.json 解除：@zcode/server、@zcode/zcode-cua、@zcode/e2e-report（+@arms/@opentelemetry/
  node-pty/ssh2/node-forge/yauzl/@larksuiteoapi 等随簇死依赖）；@zcode/client 保留底座。
  electron-updater 钉 6.8.3 对齐上游 lockfile。
- autoUpdater 换源（步骤5 打包单②补全）：更新源已换自家占位桩——当前**无真实更新源**，
  用 RFC 2606 保留 TLD `.invalid` 的自家命名桩 `https://updates.juscite.invalid/`（保证不可解析，
  绝不指向 Z.ai 旧 feed），三处同步：①electron-builder.config.js `publish.url`（随包 app-update.yml）
  ②dev-app-update.yml（dev 占位）③src/main/autoUpdater.ts `JUSCITE_UPDATE_FEED_ORIGIN`
  （运行时 manifest provider 的 endpointOrigin 默认与 resolveEndpointOrigin 回退，兜住「误开」路径）。
  双保险：ZCODE_AUTO_UPDATE_ENABLED 构建期默认关（无 config/private 构建默认即关闭），
  生产 flavor 才可启用（index.ts:1519）→ 骨架下更新功能实际不可达，桩仅为配置面占位。
  真实源就位后：改三处常量，或运行时经 `ZCODE_UPDATE_FEED_URL` / `--zcode-update-feed-url`
  注入 manifestUrl（既有注入口）。隐身闸随 §8 五通道移植波接入。

## 构建/启动（dev 态）

```bash
# 构建（产物 out/{main,preload,renderer,scheduler,plugin-sandbox}）
pnpm --filter @zcode/desktop build
# 拉起 Electron（读 out/ 产物；桥由 main 自动 spawn）
pnpm --filter @zcode/desktop start
# 全 watch 开发态（tsup watch + vite dev + electron）
pnpm --filter @zcode/desktop dev
```

前置：oc28 serve 需用户手动启动（注册文件就位后桌面端对话可用，否则 fail-closed 提示）。

## 已知边界（如实）

- cron 派发目标为空（scheduler 底座保留、transient 回执），待桥 cron 映射。
- 打包态（步骤5 第 1 轮补全）：①electron-builder.config.js 已按 M3 砍账适配——HELPER_APP_NAME
  内联、spawn-command 改用 desktop/scripts 同名件、native-search 计划内联禁用、
  bundled-agents/glm 与 bundled-tools/ripgrep 随包条目砍除（rg 回退系统 PATH）、
  CUA koffi 在物断言砍除、THIRD-PARTY-NOTICES.md 存在才随包（发行三件套随发行单收口，
  本单不伪造法律文本）；node-pty 为 @zcode/services 运行时依赖（services/package.json:35），
  prebuild 在物断言保留且实测过；另：本机 node 22.23.1 fs.cpSync 递归拷贝原生崩溃
  （静默 exit 127，学习迭代轮在案）波及 afterPack 运行时模块注入，已按同先例改
  readdir+copyFile（config 内 copyModuleTreeSync）；materialize-bridge-bundle.mjs 同坑同修。
- 桥随包（步骤5 r8 轮，销项上轮 ②「桥不随包」边界）：`scripts/materialize-bridge-bundle.mjs`
  在 electron-builder 配置求值期物化自足桥目录 bridge-bundle/（git 忽略）——tools/bridge 真件
  （排 node_modules/db/临时件）+ packages/services（package.json+src，`#src` 子路径导入）+
  knowledge-base/（B61 内置文集，cwd 向上扫描可达）+ implementation/skill-presets/
  （timeline_skill 真源，桥启动 fail-closed 验在物）+ node_modules 实件闭包
  （`pnpm --filter @juscite/bridge deploy --prod --legacy`，tsx 已挪 dependencies——运行时装载器
  非构建工具；非目标平台 @esbuild 与 node-pty prebuilds 剪除）。extraResources 主树/依赖树分开
  映射拷进 resources/bridge（electron-builder 跳过 from 根下 node_modules，同 cua-helper 先例）；
  desktopHostProcess `resolveBridgePaths` 打包态改 `process.resourcesPath/bridge`（dev 布局原样）。
  ⚠ afterPack sourcemap 剥离对 resources/bridge 子树跳过（resourcesSkipRootEntryNames）：tsx 等
  第三方压缩件在模板字符串内嵌 sourceMappingURL 文本（内含真实换行仍构成「行首」），行首锚定
  剥离会整行吞掉产出语法损坏文件（首轮 gate 实证 tsx register 损坏、子树 936 文件被改）——
  该子树引用与 .map 自洽保留，app.asar/app 侧清理行为不变。
  ci_gate package 增随包桥探针（bridge_bundle_synthetic.mjs：物化要件 + ELECTRON_RUN_AS_NODE +
  包内 tsx spawn，/api/server-info 应答即过）。package 绿只认 Windows NSIS + 该探针，
  Linux 构建/产物 ≠ package 门禁绿。**真机安装器安装+装机首跑验收仍缺（如实）**——
  门禁探针=win-unpacked 树直接以打包分支同款 spawn 参数验证，等价 spawn 径，非装机验收。
- 产物身份换牌（步骤5 r8 品牌单，收口上轮 ③）：构建期 identity 单源
  scripts/desktop-product-identity.mjs 改 Juscite——appId `app.juscite.desktop`
  （preview `app.juscite.desktop.preview`）/ productName `Juscite`（preview `Juscite Preview`）/
  linux executable/package 名 juscite(-preview)；产物名随 productName
  （`Juscite-0.1.0-win-x64.exe`）；包元 homepage/author/maintainer 换 juscite.invalid
  （RFC 2606 桩，同更新源纪律）；desktopRuntimeEnv 运行时应用名打包态同步 `Juscite`
  （app.setName/窗口托盘题名/userData=%APPDATA%\Juscite，与桥侧数据域同根）；
  dev 态应用名仍 `ZCode Dev`（与安装包互不污染）。dev-only 身份（devElectronAppBundle 的
  dev.zcode.app.development、desktopFinderOpenFolderWorkflow 的 finder 工作流 bundle id、
  开发态 AUMID cn.aminer.zcode）不在安装物范围，原样保留。
  ④本机无签名链（ZCODE_ENABLE_WINDOWS_SIGN 未设），安装包未签名（NotSigned 如实）。
- 远程连接（remote-connection 律所位）M6；其 main 侧 IPC 已随宿主清理，UI 面留待 M6 翻牌。
- 上游 main 从未经 tsc（只过 tsup）；本次清出的 ~90 处严格性错误为上游存量（dns.lookup 新签名、
  electron console-message 重载、noUncheckedIndexedAccess 守卫等），逐处最小修，无行为改动意图。
