# 品牌二轮豁免清单（r12 波2 · D5）

> 依据：`docs/上游对齐债清零设计-r12-20261028.md` §二（品牌二轮清扫，D5）。
> 范围：用户可见层（UI 文案/标题/关于/设置/欢迎/安装向导/更新提示）中
> `ZCode|Z\.ai|智谱|GLM|ChatGLM|BigModel`（ci_gate 门禁正则另含旧品牌 `律引|Lvyin`）→ 一律 Juscite 或中性词。
> 本清单逐项记录**豁免外零命中**的豁免项；每项=文件×命中文本×豁免理由。
> 门禁：`tools/bridge/ci_gate.mjs` fast 链 `brand` 步（见文末"门禁语义"）。

## 一、豁免总则（四类，逐项见 §二）

1. **协议合同/数据匹配面**：字面量用于匹配 wire/server 数据、RPC 方法名、注册表键、握手版本串——改了断功能（设计 §二"不动"条款）。
2. **dev-mode 内部标识**：开发态错误文本、dev 应用名——不随安装物分发（设计 §二"不动"条款）。
3. **技术必需（路径/包名/bundle 名）**：与上游产物物理名对齐的路径、环境变量名——改名即与上游构建产物脱钩。
4. **非用户可见载体**：资源来源元数据、无引用的开发夹具、国际化消息 id（用户看到的是解析后的词条值，不是 id）。

## 二、逐项豁免（门禁机读表见 §三，此处人读明细）

| # | 文件（packages/ 前） | 命中字面量 | 类 | 理由 |
|---|---|---|---|---|
| 1 | desktop/src/main/desktopRuntimeEnv.ts | `"ZCode Computer Use Helper.app"` | 3 | macOS Computer Use Helper 的 bundle 物理名，与上游打包产物同名才可寻址；electron-builder.config.js HELPER_APP_NAME 同源，两处一致改名=动上游构建产物，归波4 构建外挂。 |
| 2 | desktop/src/main/desktopRuntimeEnv.ts | `"ZCode Computer Use Helper (Dev).app"` | 2 | dev 态 helper 名，同 #1 且仅开发机存在。 |
| 3 | desktop/src/main/desktopRuntimeEnv.ts | `"ZCode Dev"` | 2 | dev 态应用名（设计 §二"dev-mode 内部标识"明示不动；打包态已是 Juscite/Juscite Preview）。 |
| 4 | desktop/src/main/desktopRuntimeEnv.ts | `"GLM_BINARY_PATH"` | 3 | 环境变量名（GLM CLI 注入路径），上游环境合同，改名断注入。 |
| 5 | desktop/src/main/desktopWindowsOpenFolderContextMenu.ts | `"ZCode.OpenInZCode"` | 1 | HKCU 注册表菜单键名（`Directory\shell\ZCode.OpenInZCode`），老装机升级清理依赖同名键；标签文案已改 Juscite（本文件 MENU_LABELS）。 |
| 6 | desktop/src/renderer/src/desktopPlatform.ts | `"getZCodeStdioTapDevState"` | 1 | 渲染进程↔主进程 IPC 通道名（platform.ts 方法表同源），改名断线。 |
| 7 | desktop/src/main/zcodeDataSizeScanner.ts / zcodeDataSizeWorkerClient.ts | `"ZCode data size scan aborted"` / `"Invalid ZCode data size worker response"` / `"ZCode data size worker exited with code …"` | 2 | 主进程内部诊断错误文本（AbortError/worker 生命周期），不进 UI 面板；仅 devtools/日志可见。 |
| 8 | ui/src/v4/conversationProjectionStore.ts | `.includes("ZCode agent transport closed")` 等 4 条 | 1 | 与 services/src/zcode-agent（zcodeProtocolClient.ts:126 等，上游协议客户端）产出的错误字面量做匹配分类，改匹配串=错误分类失效；生产方在 C 类合同文件（波2.5 runtime-port 吸收）。 |
| 9 | ui/src/lib/zcodeUiError.ts | `"ZCode session failed"` | 1 | services 侧 adapter（zcodeTaskServiceAdapter.ts:4203，上游文件未动）产出同名字面量；本侧投影 fallback 已改 Juscite（zcodeSessionProjection.ts），两种字面量并录集合。 |
| 10 | ui/src/settings/model-provider-section/BigModelRegistrationHint.tsx | `"BigModel 账号未注册"` | 1 | 匹配 BigModel 服务端返回的原始错误文案（数据匹配面）；第三兜底 `not registered` 已含同名英文，中文原文必须保留才能命中。 |
| 11 | ui/src/hooks/workspacePrepareRpc.ts | `"ZCode Protocol/1"` | 1 | workspace prepare RPC 握手版本串（协议合同），改名断握手。 |
| 12 | ui/src/i18n/IntlProvider.tsx | `"useZCodeIntl 必须在 ZCodeIntlProvider 内使用"` | 2 | 开发者误用断言错误文本，提及的标识符本身即导出 API 名（协议合同标识符）；不随安装物分发。 |
| 13 | ui/src/store/StoreProvider.tsx | `"useZCodeStore 必须在 StoreProvider 内使用"` | 2 | 同 #12。 |
| 14 | ui/src/WindowsCaptionMenuButton.tsx | id `"titleBar.menu.help.toggleZCodeStdioTap"` | 4 | 国际化消息 id（标识符，非文案）；词条值"抓取 Agent stdio 通信"无品牌（本轮还原 locale 后该 id 重新可解析，顺带修复 m1 树 id 改名导致的整串裸露缺陷）。 |
| 15 | ui/src/assets/provider-icons/model-provider-logo-sources.json | `"…128x128 ZCode application PNG…"` / `"brand": "BigModel"` 等 4 条 | 4 | 图标资产来源出处元数据（资产溯源记录，非 UI 渲染文案）。 |
| 16 | ui/src/components/cloud-content-dialog/mocks/weekendPlanResultDialog.zh-CN.json | `"GLM-5.3-Flash 每日额度"` 等 2 条 | 4 | 云内容对话框开发夹具（mocks/ 目录，树内无 import 引用，不随安装物分发）。 |
| 17 | desktop/build/installer.nsh | `"$TEMP\ZCode-installer.log"` / `"$WINDIR\Logs\ZCode-installer.log"` / `"$TEMP\ZCode-uninstaller.log"` | 3 | 安装/卸载日志**文件名**（NSIS define 路径）：旧版本卸载器与新版本安装器按同一物理路径对账清理，跨版本文件名合同；安装向导**页面文案**（DetailPrint/MUI_HEADER_TEXT）已全部改 Juscite（本轮）。 |
| 18 | web/src/auth/webAuthLocale.ts | `"连接 Z.ai 继续使用"` / `"Connect to Z.ai"` / `"连接 BigModel 继续使用"` / `"Connect to BigModel"` | 1 | 第三方登录渠道展示名（Z.ai / BigModel IdP）。产品品牌是否改中性「登录」待主人裁定；本轮不改写，只登记以免 `packages/web/src` 进扫描面后把门禁打红。 |
| 19 | web/src/web-remote-control/ui/webRemoteControlDeviceListPage.tsx | `"Z.ai"` / `"BigModel"` | 1 | 设备列表账号行的渠道标签，与 #18 同一 IdP 展示名。待主人裁定保留或中性化；本轮不改写。 |
| 20 | ui/src/highspeed/HighspeedShareNoticeCard.tsx | `GLM-5.3-Highspeed` | 1 | 侧栏模型名展示。第三方型号 vs 产品品牌待主人裁定；标签文本节点进门禁后必须登记，本轮不改写该型号字符串。 |
| 21 | desktop/src/main/desktopCommandHandlers.ts | `<title>ZCode Endpoint</title>` / `ZCode endpoint origin` | 2 | 仅 `ZCODE_ENV===test` 的自定义 endpoint 覆盖对话框（窗口标题与表单标签）。命名的是上游 endpoint 覆盖，不是产品名牌；不随正式安装菜单分发。 |
| 22 | web/src/web-remote-control/contract.ts | `"getZCodeJwtToken"` | 1 | `Pick<WebAuthService, "getZCodeJwtToken">` 的方法名字符串。标识符命名空间，不是用户文案；改名即断登录边界类型。 |

不在表内亦不豁免的判定：
- **代码标识符**（`ZCodeIntlProvider`/`useZCodeTaskService`/`zcodeSessionProjection` 类型导出名、`/zcode-plugins-official/` 路径标记、`normalizeAgentProviderToZCodeAgent` 等 ≈4,690 处）：非字符串文案，出口在标识符命名空间（改名=跨包断线），属设计 §二"协议合同标识符"总豁免——门禁按"仅扫字符串字面量"天然不涉及。
- **注释**（ComputerUseSection/cuaPermissionRestartVerify/codingPlanUsageSources/desktopRuntimeEnv:67 等）：非用户可见字符串，门禁剥离注释后不涉及。
- **locale 基座文件**（ui/src/i18n/locales/*.ts）：已还原上游 3.16.2 原样（md5 cca29fa3/f6b6caa3 与上游 archive 全同），其中的品牌字样属上游内容，运行时由 `i18n/jusciteOverlay.ts` 全量覆盖——门禁对 locale 基座不走字面量零命中，改走**覆盖完备性断言**（基座每个品牌词条键必须有 overlay 键，缺一即红）。
- **wire 数据本身的模型名**（桥/oc28 返回的 `glm-*` 模型 id）：服务端数据，不在树内字符串清扫范围。

## 三、门禁机读豁免表（ci_gate brand 步消费；`file` 为 packages/ 后路径前缀，`literal` 为命中的字符串字面量全文或前缀）

```json
{
  "waivers": [
    { "file": "desktop/src/main/desktopRuntimeEnv.ts", "literal": "ZCode Computer Use Helper.app", "why": "helper bundle 物理名" },
    { "file": "desktop/src/main/desktopRuntimeEnv.ts", "literal": "ZCode Computer Use Helper (Dev).app", "why": "dev helper 名" },
    { "file": "desktop/src/main/desktopRuntimeEnv.ts", "literal": "ZCode Dev", "why": "dev 态应用名" },
    { "file": "desktop/src/main/desktopRuntimeEnv.ts", "literal": "GLM_BINARY_PATH", "why": "环境变量名" },
    { "file": "desktop/src/main/desktopWindowsOpenFolderContextMenu.ts", "literal": "ZCode.OpenInZCode", "why": "注册表键名" },
    { "file": "desktop/src/renderer/src/desktopPlatform.ts", "literal": "getZCodeStdioTapDevState", "why": "IPC 通道名" },
    { "file": "desktop/src/main/zcodeDataSizeScanner.ts", "literal": "ZCode data size", "why": "内部诊断错误" },
    { "file": "desktop/src/main/zcodeDataSizeWorkerClient.ts", "literal": "ZCode data size", "why": "内部诊断错误" },
    { "file": "ui/src/v4/conversationProjectionStore.ts", "literal": "ZCode agent transport closed", "why": "协议错误匹配面" },
    { "file": "ui/src/v4/conversationProjectionStore.ts", "literal": "ZCode Protocol client disposed", "why": "协议错误匹配面" },
    { "file": "ui/src/v4/conversationProjectionStore.ts", "literal": "ZCode Protocol client is disposed", "why": "协议错误匹配面" },
    { "file": "ui/src/v4/conversationProjectionStore.ts", "literal": "ZCode Agent runtime is not running", "why": "协议错误匹配面" },
    { "file": "ui/src/lib/zcodeUiError.ts", "literal": "ZCode session failed", "why": "services 侧同名字面量匹配" },
    { "file": "ui/src/settings/model-provider-section/BigModelRegistrationHint.tsx", "literal": "BigModel 账号未注册", "why": "服务端错误匹配面" },
    { "file": "ui/src/hooks/workspacePrepareRpc.ts", "literal": "ZCode Protocol/1", "why": "握手版本串" },
    { "file": "ui/src/i18n/IntlProvider.tsx", "literal": "useZCodeIntl 必须在 ZCodeIntlProvider 内使用", "why": "dev 断言文本" },
    { "file": "ui/src/store/StoreProvider.tsx", "literal": "useZCodeStore 必须在 StoreProvider 内使用", "why": "dev 断言文本" },
    { "file": "ui/src/WindowsCaptionMenuButton.tsx", "literal": "titleBar.menu.help.toggleZCodeStdioTap", "why": "i18n 消息 id" },
    { "file": "ui/src/assets/provider-icons/model-provider-logo-sources.json", "literal": "ZCode", "why": "资产溯源元数据" },
    { "file": "ui/src/assets/provider-icons/model-provider-logo-sources.json", "literal": "BigModel", "why": "资产溯源元数据" },
    { "file": "ui/src/components/cloud-content-dialog/mocks/weekendPlanResultDialog.zh-CN.json", "literal": "GLM", "why": "开发夹具" },
    { "file": "desktop/build/installer.nsh", "literal": "ZCode-installer.log", "why": "安装/卸载日志文件名（跨版本卸载器清理对同一物理路径的合同）" },
    { "file": "desktop/build/installer.nsh", "literal": "ZCode-uninstaller.log", "why": "卸载日志文件名（同上）" },
    { "file": "desktop/build/installer.nsh", "literal": "$ZCodeInstallerProcessRole", "why": "NSIS 变量名引用（DetailPrint 诊断载荷，运行时取值为 outer/elevated-inner）" },
    { "file": "web/src/auth/webAuthLocale.ts", "literal": "Z.ai", "why": "第三方 IdP 渠道展示名，待主人裁定保留或中性化" },
    { "file": "web/src/auth/webAuthLocale.ts", "literal": "BigModel", "why": "第三方 IdP 渠道展示名，待主人裁定保留或中性化" },
    { "file": "web/src/web-remote-control/ui/webRemoteControlDeviceListPage.tsx", "literal": "Z.ai", "why": "设备列表渠道标签，同登录页 IdP 展示名，待主人裁定" },
    { "file": "web/src/web-remote-control/ui/webRemoteControlDeviceListPage.tsx", "literal": "BigModel", "why": "设备列表渠道标签，同登录页 IdP 展示名，待主人裁定" },
    { "file": "ui/src/highspeed/HighspeedShareNoticeCard.tsx", "literal": "GLM-5.3-Highspeed", "why": "侧栏模型名展示，第三方型号待主人裁定，本轮不改写" },
    { "file": "desktop/src/main/desktopCommandHandlers.ts", "literal": "ZCode Endpoint", "why": "ZCODE_ENV===test 的 endpoint 覆盖对话框窗口标题" },
    { "file": "desktop/src/main/desktopCommandHandlers.ts", "literal": "ZCode endpoint origin", "why": "ZCODE_ENV===test 的 endpoint 覆盖对话框表单标签" },
    { "file": "web/src/web-remote-control/contract.ts", "literal": "getZCodeJwtToken", "why": "Pick 键上的方法名字符串，标识符命名空间，非用户文案" }
  ]
}
```

## 四、门禁语义（tools/bridge/ci_gate.mjs fast 链 brand 步）

1. **扫描面**：`packages/ui/src`、`packages/desktop/src`、`packages/web/src`、`packages/web/index.html`、`packages/desktop/build/installer.nsh`（安装向导）。
2. **只扫用户可见字符串**：剥离注释（`//`、`/* */`、NSIS `;`、HTML `<!-- -->`）、import/export 行、模板串 `${…}` 插值后，再在 `"…"`/`'…'`/`` `…` `` 字面量内匹配全品牌正则 `ZCode|Z\.ai|智谱|GLM|ChatGLM|BigModel|律引|Lvyin`（大小写敏感——小写 `zcode`/`z.ai` 属标识符与 wire 域名命名空间）。另扫成对 HTML/JSX 标签的静态文本（去掉 `{…}` 表达式，跳过 `script`/`style`），因此 `<title>…</title>`、`<span>品牌</span>` 这类无引号文本节点也进门禁。
3. **locale 基座覆盖断言**：对 `packages/ui/src/i18n/locales/{en-US,zh-CN}.ts` 逐键提取含品牌字样的键，逐一断言 `i18n/jusciteOverlay.ts` 存在同键（运行时 overlay 覆盖后才到用户眼前），缺键即红。
4. **豁免**：命中项按 §三 机读表（file 前缀 + literal 全文/前缀匹配）豁免；表外命中即 FAIL exit 1。
5. 本清单与机读表同源同改：改豁免先改本文件（含 §三 JSON），门禁每轮实时解析。
