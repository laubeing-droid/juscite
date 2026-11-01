# 模块边界与可维护性评估

本页回答「代码按什么边界切开、依赖往哪流、哪里已经难改」，面向要排维护顺序的开发者。它是一次静态勘察的结论，不是新的架构规范。组件职责与一次请求怎么走，仍以[架构概览](architecture.md)为准；`@juscite/*` 包的声明职责见[自有包一览](packages.md)。

## 范围与计数口径

勘察对象是 2026-11-01 工作区 `main` 尖端 `3ecdc2b`。只读源码与清单，没有改产品代码，也没有跑 `pnpm typecheck` 或 `node tools/bridge/ci_gate.mjs`。

行数按换行符计，排除 `node_modules`、`dist`、`out`、`.git`。测试文件的粗分规则：路径含 `/test/`、`/tests/`、`/__tests__/`，或文件名以 `.test.` / `.spec.` 结尾，或 Python 测试文件以 `test_` 开头。这套规则**不会**把 `tools/bridge/*synthetic*` 算成测试，桥的验证脚本在下文单独计数。

依赖方向用静态 `import` / `export from` / `require()` / `import()` 的字符串字面量扫描 `packages/` 与 `tools/` 下的 `ts`、`tsx`、`mjs`、`mts`、`js`。动态拼接的路径扫不到。运行时图排除了路径含测试目录、以及文件名含 `synthetic`、`walkthrough`、`probe`、`_walk`、`e2e` 或以 `cdp_` 开头的文件。

| 区域 | 文件数 | 行数 | 置信度 |
|---|---:|---:|---|
| `packages/`（ts/tsx/js/mjs/py） | 5,113 | 1,203,908 | 高（全量计数） |
| `tools/` | 240 | 134,676 | 高 |
| `implementation/` | 207 | 92,541 | 高 |
| 其中 `implementation/python/` 生产 `.py` | 87 | 48,011 | 高 |
| 其中 `implementation/tests/` | 111 | 43,298 | 高 |

`packages/` 里按上面的测试启发式拆开后，体量集中在四个壳包：

| 包目录 | 生产文件 / 行 | 测试文件 / 行 |
|---|---:|---:|
| `packages/ui` | 1,950 / 406,647 | 1,177 / 295,130 |
| `packages/services` | 468 / 124,949 | 321 / 119,529 |
| `packages/desktop` | 325 / 85,800 | 11 / 878 |
| `packages/shared` | 302 / 53,439 | 155 / 34,799 |
| `packages/juscite-legal` | 54 / 21,947 | 6 / 887 |

`desktop` 的「生产行」含脚本与资源旁的 js/mjs；稍后按 ts/tsx 再数，`desktop/src` 约 6.4 万行，主体在 `src/main`（约 2.6 万行，其中 `main/browserView` 约 1.1 万行）。

## 当前模块地图

仓库是 pnpm 工作区（`pnpm-workspace.yaml`：`packages/*`、`tools/bridge`、`tools/mock_host`）。根包名是 `juscite-frontend`，产品名是 Juscite，壳包沿用 ZCode 的 `@zcode/*`，法律能力用 `@juscite/*`。这是继承下来的双前缀，不是偶然重名。

意图中的四层（与[架构概览](architecture.md)一致）：

1. **桌面壳** `packages/desktop`（`@zcode/desktop`）拉起 Electron，并用 `packages/desktop/src/main/desktopHostProcess.ts` 启动桥进程，入口固定为 `tools/bridge/bridge_host.mjs`，WebSocket 默认端口 3030。
2. **工作台界面** `packages/web`（`@zcode/web`）+ `packages/ui`（`@zcode/ui`）+ `packages/client`（`@zcode/client`）。法律面板经 `packages/ui/src/legal/register.tsx` 注入 UI 套件，面板实现放在 `packages/juscite-legal`。
3. **本地桥** `tools/bridge`（包名 `@juscite/bridge`）装配法律服务、SQLite、对 AI 运行时的调用。
4. **确定性 Python 面** `implementation/python/legal_entry.py` 的 `call(method, args, config)`，加上白名单外的若干直接 CLI。

自有包与「像包但还不是工作区包」的目录：

| 位置 | 包名 | 实际角色 |
|---|---|---|
| `packages/juscite-legal` | `@juscite/legal` | 法律面板 + `src/kernel/` 纯函数模型。工作台真页面大多在包内互相引用 |
| `packages/juscite-vizb` | `@juscite/vizb` | 大事记 / 庭审对抗图渲染核。桥用相对路径引用 `src/` |
| `packages/juscite-edisc` | `@juscite/edisc` | 电子证据四核。`tools/bridge/edisc_service.mjs` 直接 import 四个 `src/*Kernel.ts` |
| `packages/juscite-flow` | 无 `package.json` | 四个 `.mjs`（事实核验、交叉验证、代理运行时、原文回引），约 2,310 行。不在工作区包清单的「有名字」意义上存在 |
| `packages/juscite-office-bridge` | `@juscite/office-bridge` | Word 旁加载桥。生产壳与 `bridge_host.mjs` 都没有 import 它 |
| `packages/juscite-runtime-port` | `@juscite/runtime-port` | AI 能力合同，单文件 `src/index.ts`（约 158 行） |
| `packages/juscite-runtime-adapters/opencode` | 无 `package.json` | 唯一适配器 `opencodeAdapter.mjs`（预算台账记 361 行） |
| `packages/juscite-desktop-pet` | `@juscite/desktop-pet` | 桌面伴侣窗，由 desktop 装配 |
| `packages/zcode-cua` | `@zcode/zcode-cua` | Computer Use 占位包，运行时失败关闭 |
| `implementation/ui/` | 无 | 针对 OpenCode v2.0.28 的 Solid 法律工作台补丁，README 写明未应用到生产 |
| `tools/mock_host` | `@juscite/mock-host` | 界面开发用合成桩 |
| `lawbook-packs/` | 无 | 法条数据包，供轻量引证引擎只读 |

壳内的大目录（生产 ts/tsx 行，置信度高）：

- `packages/ui/src`：`v4` 约 6.0 万、`settings` 约 6.0 万、根上散文件约 4.3 万、`lib` 约 4.3 万、`components` 约 4.1 万。
- `packages/services/src`：`zcode-agent` 约 2.2 万、`bots` 约 2.0 万、`session` 约 1.4 万。
- `packages/shared/src`：根上散文件约 3.2 万，另有 `zcode-protocol-v4` 约 1.2 万。协议与校验类型堆在根文件，例如 `validation.ts` 1,911 行、`channels.ts` 1,372 行、`platform.ts` 1,238 行。

`pnpm typecheck`（根 `package.json`）是 `tsc -b`，工程引用能带到的自有包只有两条：`@juscite/legal`（被 `packages/ui/tsconfig.json` 引用）、`@juscite/desktop-pet`（被 `packages/desktop/tsconfig.main.json` 引用）。`juscite-vizb` 有自己的 `tsconfig.json` 但没有被任何工程引用；`juscite-edisc`、`juscite-flow`、`juscite-runtime-port`、`juscite-office-bridge`、运行时适配器都没有进入这棵引用树。它们由桥在运行时按相对路径加载（适配器与 flow 是 `.mjs`，edisc/vizb/legal kernel 是 `.ts`，经 `tsx`）。置信度高。

## 依赖方向

运行时静态依赖（语句次数，方向是「谁 import 谁」）。只列产品代码里次数 ≥ 3 的边，样例路径在勘察笔记里核对过。

```text
ui        → shared (819)  services (205)  provider (33)  juscite-legal (12)  rpc (9)
services  → shared (313)  rpc (48)  zcode-cua (13)  provider (9)  provider-node (3)
desktop   → shared (122)  ui (37)  services (29)
web       → shared (22)  ui (13)
provider  → shared (12)
provider-node → shared (6)  provider (5)
client    → shared (19)  rpc (6)  services (3)
tools/bridge → services (11)  vizb (5)  rpc (4)  shared (4)  adapters/opencode (3)
             → juscite-legal (3)  juscite-flow (3)
juscite-legal → services (2)
juscite-desktop-pet → shared (5)
juscite-runtime-port → shared (2，相对路径类型导入)
adapters/opencode → juscite-runtime-port (1)
shared → model-option-map (1)
```

包级环：在上述运行时过滤下 **0 个**。把测试文件也算进去时能扫到 4 个环，全部经过测试边（例如 `packages/services/test/cloudContentService.test.ts` import `packages/desktop/scripts/cloud-content-mock.mjs`）。产品包之间没有 import 环。置信度高；漏报只可能来自非字面量动态 import。

方向本身是健康的：界面指向共享类型与服务、桌面壳指向界面、法律包不反向依赖 `ui`。适配器规模也守得住：`contracts/adapter-budget.md` 自述桥代码约 4.5 万行、适配器 361 行、约 0.80%（上限 10%）。这次没有复跑那条计数命令，以该文件 2026-10-31 的记录为准，置信度中。

真正的边界问题不在「有环」，而在边的落点：桥不走包的 `exports`，而是钻进 `packages/*/src`；`ui` 依赖的 `@zcode/services` 是 Node 服务实现包（含 `node-pty` 等），不是单独的渲染端类型包。

`ui/src` 对 `@zcode/services` 的 205 处 import 里，多数是 `import type`（`verbatimModuleSyntax` 已打开）。抽查到的运行时值包括 `createConversationTelemetryService`（`packages/ui/src/v4/telemetry/ConversationTelemetryAttachment.tsx`）、`withPluginTelemetry`、`isValidCronExpr`、`isCuaPermissionStatusAvailable`。法律面板则同时用两套读数方式：`useServices()` 走服务访问器，引证面板直接 `fetch("/api/verify/...")`。置信度：语句次数高；「多少是类型导入」中（多行 import 的分类是启发式）。

## 主要问题（按严重度）

### 1. 严重：引证核验有两套引擎、三条入口

律师在界面上点的核验，和 Python 白名单里名叫 `citation.*` 的核验，不是同一个实现。

| 入口 | 引擎 | 数据 |
|---|---|---|
| `CitationVerifyPanel.tsx` → `POST /api/verify/citation` 与 `/api/verify/document` | `tools/bridge/citation_verify_service.mjs` 子进程启动 `implementation/python/citation_verify_lite.py` | `lawbook-packs/` 里的 `pack.sqlite3` |
| `tools/bridge/g6_connector_mcp.mjs` 的「法条有效性核验」 | 同一个 `citation_verify_lite.py`，但是自己 `spawnSync`，方法名直接写 `citation.verify_document` | 同上，不经过 `createCitationVerifyService` |
| `legal_entry.call` 的 `CITATION_METHODS`（`citation.parse` / `citation.verify` / `citation.verify_document`） | `legal_entry.py` 约 3614 行 `from citation_verifier import citation_call` | `citation_verifier.py` 再进 `statute_validity`（外部法源 / LCCC 冻结面） |

`citation_verify_lite.py` 文件头写明：解析层从 `citation_verifier.py` 等量复制，数据层换成轻量法条包，并声明「单一核验权威……禁第二核验器」。`legal_entry.py` 仍把 `citation.*` 路由到 `citation_verifier.py`。两条注释互相否定。

G6 连接器绕过桥服务还有一个具体后果：`citation_verify_service.mjs` 负责历史落账（`citation_checks`、`/api/verify/citation/history`），直连 CLI 的调用不走这段。面板历史与工具核验是否同一本账，代码上没有共用函数保证。置信度高。

同一形状的分叉还有两处，严重度低一档，因为当前 React 面板只挂了其中一侧：

- **文档对比**。`DocCompare.tsx` 调用 `zcodeAgentService.compareDocuments`。实现写在 `bridge_host.mjs` 约 2941 行，算法是 `tools/bridge/docdiff.mjs` 的行级 diff，对象是 `workspace/materials` 下的纯文本。Python 侧另有 `document_compare.py`（F55，PDF/DOCX 分段对比），经 `legal_entry` 的文档对比方法组进入。工作台面板不调用它。
- **Word / WPS**。架构图把 `@juscite/office-bridge` 画成桥的下游。全库生产路径里，`startOfficeBridge` 只出现在 `packages/juscite-office-bridge` 自己的测试和 `tools/bridge/monitoring_synthetic.mjs`。桌面壳与 `bridge_host.mjs` 都不启动它。Python 侧另有 `wps_host.py`、`wps_host_surface.py`，经 `legal_entry` 的 `wpshost.*` 进入。Office 包目前是一条还没接到壳上的并行实现。

### 2. 严重：组合根过大，产品代码和验证脚本放在同一层

两个文件各自承担「整个产品的 switch」：

- `tools/bridge/bridge_host.mjs`，5,839 行。它同时是进程入口、服务装配和部分功能实现（文档对比的 `compareDocuments` 就在这个文件里，而不是在 `docdiff.mjs` 旁的服务模块）。它用相对路径拉起 ZCode 服务内部文件（`packages/services/src/task-groups/index.ts`、`session/tasksDatabase/migrations.ts`、`conversation-share/*`、`plugins/pluginManagementService.ts`、`session/automationService.ts`）、法律内核（`skillActivationModel.ts`、`deliveryChainModel.ts`）、vizb 和 OpenCode 适配器。
- `implementation/python/legal_entry.py`，5,060 行。文件顶部约 125 个 `*_METHODS` frozenset，其中字符串方法名约 602 个（正则抽取，置信度高）。前缀最多的是 `harness`（约 196）。唯一的 `call()` 用长串 `if method in ...` 分发。领域实现大多已经在同目录的独立模块里，分发本身仍堆在这一个函数里。

`tools/bridge/` 顶层没有子目录来分开产品与验证（按文件名启发式，置信度中高）：

| 类别 | 文件 | 行数 |
|---|---:|---:|
| `*synthetic*` | 52 | 17,872 |
| 文件名含 walk | 14 | 5,245 |
| probe / `cdp_*` | 13 | 2,180 |
| e2e | 2 | 410 |
| host / gate（含 `bridge_host.mjs`、`ci_gate.mjs`、`bridge_store.mjs`） | 5 | 8,180 |
| 文件名像 `*_service.mjs` | 21 | 9,408 |
| 其余产品向脚本（模型、技能、diff、运行时） | 31 | 4,984 |

`ci_gate.mjs` 的 `fast` 模式直接点名同目录下的合成脚本。验证因此「能跑」，但新人无法从目录看出哪一个文件是进程的一部分、哪一个只是门禁步骤。`bridge_host.mjs.bak-seqfix` 还留在目录里。

壳侧也有同类大文件，改对话或机器人时不可避免：非测试 ts/tsx 中 ≥3,000 行的有 11 个，≥1,500 行的有 47 个。最大的几个：

| 行数 | 文件 |
|---:|---|
| 9,887 | `packages/services/src/bots/botsService.ts` |
| 8,104 / 7,691 | `packages/ui/src/i18n/locales/en-US.ts`、`zh-CN.ts`（文案表） |
| 6,776 | `packages/services/src/zcode-agent/zcodeAgentService.ts` |
| 6,020 | `packages/ui/src/v4/SessionPane.tsx` |
| 5,845 | `packages/services/src/zcode-agent/zcodeTaskServiceAdapter.ts` |
| 4,631 | `packages/desktop/src/main/browserView/browserGuestManager.ts` |
| 4,381 | `packages/shared/src/zcode-protocol/index.ts` |
| 3,565 | `packages/ui/src/lib/zcodeSessionProjection.ts` |
| 3,260 | `packages/services/src/node.ts`（服务装配桶） |
| 3,018 | `packages/ui/src/app-shell/WorkspaceShellLayout.tsx` |

i18n 大文件是数据，不是控制流。`botsService.ts`、`zcodeAgentService.ts`、`SessionPane.tsx`、`bridge_host.mjs`、`legal_entry.py` 是控制流，优先拆。

### 3. 高：自有包的公开边界和真实挂载不一致

`packages/juscite-legal/package.json` 的 `exports` 有 16 项。`src/panels/` 里有 23 个 ts/tsx **不在** exports 中，包括工作台实际渲染的 `DocCompare.tsx`、`CitationVerifyPanel.tsx`、`LawBookPanel.tsx`、`SubscriptionPanel.tsx`、`CaseBoardPanel.tsx` 等。它们由 `LegalWorkbench.tsx` 用相对路径引入，这半边是清楚的。

另一半不清楚：`packages/ui` 仍直接 import 法律面板，而不只是注册套件。

- `packages/ui/src/legal/register.tsx` 只做 `configureLegalUiKit(...)`。
- `App.tsx` import `SecurityAuditCenter`。
- `SettingsPage.tsx` import `SubscriptionPanel`（这条路径不在 `@juscite/legal` 的 exports 里）。
- `app-shell/WorkspaceShellLayout.tsx` import `LegalWorkbench`、`KnowledgeBasePanel`、`ResearchPanel`、`TeamPanel`、`ConflictPrecheckPanel`、`LearningIterationPanel`。
- `settings/StealthSettingsSection.tsx`、`project-sidebar/index.tsx` 再引安全审计与工具策略面板。

`register.tsx` 的注释写「本文件是法律 UI 出树后唯一留在 ui 包内的挂载胶水」。挂载点实际分散在上述文件。注释还指向 `docs/上游对齐债清零设计-r12-20261028.md`（`ui-kit.ts` 同样指向它），仓库里没有这个文件。

桥对内核的引用同样绕过 exports：`edisc_service.mjs` 四条 import 都指向 `packages/juscite-edisc/src/*Kernel.ts`；flow 没有包入口可引。这样「换运行时只换适配器」在 runtime-port 上成立（`bridge_host.mjs` 第 10 行附近一处 `createOpenCodeRuntime`），在法律内核上不成立。

`packages/ui` 与 `packages/services` 的 `AGENTS.md` 要求先读 `DESIGN.md`、`CONTEXT.md`、`docs/agents/runtime-boundaries.md`。这三个路径在仓库中不存在。壳的贡献者规则指向了上游文档残留。

### 4. 高：测试跟着工单号走，不跟着模块走

壳包的测试是密的，而且和实现同包：`ui` 约 1,177 个测试文件 / 29.5 万行，`services` 约 321 / 12.0 万行，`shared` 约 155 / 3.5 万行。这是 ZCode 层可维护的部分。

Juscite 自己的核不是这样放的：

| 实现 | 包内测试 |
|---|---|
| `packages/juscite-flow`（4 个模块） | 0 |
| `packages/juscite-edisc`（4 个核） | 0 |
| `packages/juscite-vizb` | 0 |
| `packages/juscite-desktop-pet` | 0 |
| `packages/juscite-legal`（约 2.2 万行） | 6 个文件、887 行：`configWriteModel`、`deliveryChainModel`、`flowStudioModel`、`skillActivationModel`、`tabularExportGuard`、`vizbPanelContract` |
| `packages/desktop` | 测试集中在 `pluginSandbox/` 与安装脚本；桥进程生命周期、`browserGuestManager.ts` 没有同级测试 |
| `implementation/python`（87 模块、4.8 万行） | 测试在 `implementation/tests/`，108 个 `test_*.py`，命名是 `test_f70_wiring.py`、`test_f55_f58_compare_export_wiring.py` 这种工单号。快速上手写明：外部引擎未检出时大量跳过 |

flow 的事实核验 / 交叉验证由 `tools/bridge/fact_verification_synthetic.mjs`、`cross_verification_synthetic.mjs` 覆盖，并被 `ci_gate.mjs` 的 `fast` 点名。引证由 `citation_verify_synthetic.mjs` 覆盖。这些检查绑定的是「桥进程 + 脚本末行 PASS」，不是「模块可单独 import 的单元」。把内核从桥里抽走时，测试不会跟着走，因为测试就住在桥目录里。

根脚本也没有一条 `pnpm test`。能单包跑 vitest 的是 `rpc`、`provider`、`provider-node`、`model-option-map`。`ui` 有 `vitest.config.ts`，但测试入口写在 `ci_gate.mjs` 的 `VITEST_TESTS` 清单里（注释期望 150 项，只覆盖少数合同测试，不是 1,177 个文件全跑）。两套门禁各管一块，没有一张图说明「改了 `citation_verify_lite.py` 应该跑哪条」。

本次没有测量行覆盖率。上面是测试文件落点，不是「测到了百分之几」。置信度高。

### 5. 中：所有权还挂在文件名上的临时代码，以及第三套 UI 草稿

- `tools/PENDING_OWNER_*.py` 有 111 个文件、约 86,085 行。名字已经标明所有者未定。它们和产品桥、发行脚本放在同一个 `tools/` 下。
- `implementation/ui/README.md` 描述一份 OpenCode v2.0.28 的 Solid 法律工作台补丁，并写明没有应用到生产。当前用户看到的法律 UI 是 `packages/juscite-legal` 的 React 面板。仓库里同时躺着第三套界面草稿，后续功能容易改错树。
- 桥入口注释仍写「沿称 mock-host」。`packages/ui/src` 里约 1,350 个文件出现 `zcode` / `ZCode` 字样（约 7,781 次）。双前缀可以保留，但用户可见字符串与包名的收敛应继续走现有品牌门禁（`ci_gate.mjs` 的 brand 步、`contracts/brand-exemptions.md`），而不是再引入第三个产品名。
- `packages/services/src/node.ts`（3,260 行）是壳的服务装配桶；桥又按文件从 `services/src` 里另拎一套（分享、自动化、插件、任务组）。同一服务有「壳的默认装配」和「桥的手工装配」两处主人。置信度高（import 列表），两套装配是否行为等价未逐项比对，置信度低，不在这里下结论。

## 改进步骤

按依赖顺序做。每一步都应该能单独合并，并且不要求重写壳或合并两套算法。

1. **先写死引证的唯一产品入口，再改 G6。** 在 `contracts/` 加一张短表（机器可读 JSON 或门禁能读的清单即可）：律师可见核验只允许 `citation_verify_service.mjs` → `citation_verify_lite.py`。`g6_connector_mcp.mjs` 改为调用该服务已导出的函数，删除自己的 `spawnSync`。`legal_entry` 的 `citation.*` 继续指向 `citation_verifier.py` 时，在方法注释和任何会展示给律师的文案里标明数据源是外部法源，不与法条包核验共用一句「已核验」。这一步不要合并两个解析器。做完后跑现有 `citation_verify_synthetic.mjs`。

2. **把 `tools/bridge` 拆成两个目录，不改行为。** `host/` 放 `bridge_host.mjs`、`bridge_store.mjs`、`*_service.mjs`、`docdiff.mjs`、技能与运行时；`verify/` 放 synthetic、walkthrough、probe、cdp、e2e。`ci_gate.mjs` 只改路径。删掉或移出 `bridge_host.mjs.bak-seqfix`。同时把 `compareDocuments` 从 `bridge_host.mjs` 挪到 `docdiff` 旁边的薄模块，宿主文件只保留 import 与路由注册。

3. **补上缺失的包入口，并禁止新的深链。** 给 `packages/juscite-flow` 和 `packages/juscite-runtime-adapters/opencode` 加 `package.json` 与 `exports`。把 `bridge_host.mjs`、`edisc_service.mjs`、`flow_engine_real_model.mjs` 的相对 `src/` 路径改到这些入口（已有 exports 的 vizb、edisc 先改 import，行为不变）。加一条小检查：`tools/bridge/host` 里新增的 `../../packages/` 深链失败，现存深链列进豁免并只减不增。把 `juscite-vizb` 和 `juscite-edisc`（先补 `tsconfig.json`）放进根 `tsc -b`。`@juscite/legal` 二选一写进 exports 注释：要么把 `SettingsPage.tsx` 用到的 `SubscriptionPanel` 补进 exports，要么改成只从 `LegalWorkbench` 进入并删掉那条包外 import。以 `package.json` 的 exports 为准，不要让注释里的「唯一注册点」继续和 `WorkspaceShellLayout.tsx` 矛盾。

4. **给没有包内测试的核各加一个不启动桥的测试。** 优先 `juscite-flow` 的 `fact-verification.mjs` / `cross-verification.mjs`，以及 `juscite-edisc` 的四个 kernel：从对应 synthetic 里抽出纯函数断言，synthetic 留下「真桥接线」那几条。Python 侧新测试放在被测模块可发现的名字下（例如 `implementation/tests/test_citation_verify_lite.py`），工单号可以留在文件头，不要只留在文件名里。不要试图把 `ui` 的 1,177 个测试一次接进 `fast`；那是另一项工程。

5. **收紧 `legal_entry.call` 的分发，而不是重写领域模块。** 把 `if method in SOME_METHODS` 收成一张表：方法集 → 处理函数。每次只搬一个前缀（建议从已经是独立模块的 `citation.*`、`statute.*`、`subscription.*` 开始）。`call()` 的前置闸（persona/observer 拒绝、技能工具白名单）留在原函数。目标是这个文件不再随每个新方法线性变长。

6. **处理所有权悬空的树，避免下次功能改错地方。** 把 `tools/PENDING_OWNER_*.py` 移到单独目录（例如 `tools/recon/`）并在目录 README 写明它们不是产品运行时。`implementation/ui/` 在 README 已声明「未应用到生产」的前提下，于[架构概览](architecture.md)的全景图旁加一句：生产法律 UI 只有 `packages/juscite-legal`；该目录是未合并的 OpenCode 补丁。`@juscite/office-bridge` 同理：在架构图修正前，不要再写「桥已经连接 Word」。要么由 `desktopHostProcess` 或桥显式启动它，要么在架构页把它标成未接线。

7. **大文件只在下一次改到时纵向切开。** `botsService.ts` 按渠道拆（飞书实现已经在 `bots/providers/feishuProvider.ts`，主文件仍有 9,887 行）。`SessionPane.tsx` 按已经存在的 `v4/composer/` 子目录继续外移，不要新开一套组件库。`zcode-protocol/index.ts` 与 `shared/src` 根上的 `validation.ts`、`channels.ts` 按域拆文件并保持原 export 路径。这些不是本评估的阻塞项，插在相关功能改动里做。

明确不做：重写 `@zcode/ui`，把 ZCode 对话栈换成另一套前端，或把 Python 确定性面整体搬进 Node。壳的测试密度和「无包级环」说明那一层值得留着；成本在法律能力的入口和第二组合根。

## 勘察未覆盖

- 没有运行类型检查、`ci_gate` 和 Python 测试，所以不知道上述 exports 裂缝今天是否已经让 `tsc -b` 失败。
- 没有比对 `node.ts` 默认装配与桥手工装配的运行时行为。
- 没有读 `contracts/ref-graph.json` 的全量符号（该文件是壳升级用的引用图，不是本页的依赖图）。
- `tools/` 里除 `PENDING_OWNER_*` 与 `bridge/` 之外还有大量以工单号命名的单文件脚本（`e12_corpus_gen.py`、`f31_ledger_apply.py` 等）。它们影响「tools 目录能否当工具箱用」，没有逐个判断是否仍被门禁调用。
