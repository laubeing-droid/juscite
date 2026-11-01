# r12 波3 · 插桩清单（法律 UI/内核出树后的树内注册点）

> 依据：`docs/上游对齐债清零设计-r12-20261028.md` §一 L2「树内只留注册点」+ §八 原则3；波1 `contracts/mod-map.json`（B 类 ui/src/legal 面板族 25 件 + L3 类 services/src/legal 内核 6 件）。
> 施工：r12 波3员（插件化）。日期：2026-10-29。面板族 → `packages/juscite-legal`（@juscite/legal）；
> plugin-ui（上游 MCP Apps 页宿主）不适用本迁移：法律面板为共享服务上下文的 React 组件族，改走 MCP 页管线即行为变更，故按施工单取「顶层自有包」路线。
> 波5 产出 `contracts/pin-points.json`（符号级）时应吸收本清单第 1–8 点。

## 注册点（树内仅存）

| # | 位置 | 挂载内容 | 消费方 |
|---|---|---|---|
| 1 | `packages/ui/src/legal/register.tsx` | **唯一注册点文件**：把 ui 内部件（Button/Input/DiffViewer/MessageResponse/PdfPreviewContent/collectDroppedFiles/useServices）注入 `@juscite/legal` 的 legalUiKit 窄适配层（`configureLegalUiKit`） | `App.tsx` 静态导入（模块加载即注册，先于任何面板渲染） |
| 2 | `packages/ui/src/App.tsx:25-26` | `import "@/legal/register.js"`（注册副作用）+ `SecurityAuditCenter`/`SECURITY_AUDIT_EVENT` → `@juscite/legal/panels/SecurityAuditCenter`；渲染点 App.tsx:1222 `<SecurityAuditCenter>` | App 根 |
| 3 | `packages/ui/src/app-shell/WorkspaceShellLayout.tsx:115-135` | `LegalWorkbench` 静态 + KnowledgeBasePanel/ResearchPanel/TeamPanel/ConflictPrecheckPanel/LearningIterationPanel 五个 lazy（代码分割边界原样保留）；渲染点 2217/2263/2278（及 web 分支 2750/2796/2811）；视图键 `workspaceMainView === "legal"` 字符串合同不改 | 工作区壳 |
| 4 | `packages/ui/src/project-sidebar/index.tsx:53` | `SecurityAuditSidebarEntry` → `@juscite/legal/panels/SecurityAuditCenter` | 侧栏 |
| 5 | `packages/ui/src/settings/StealthSettingsSection.tsx:12` | `requestSecurityAuditCenter` → 同上 | 设置页 |
| 6 | `packages/ui/package.json` | 新依赖 `"@juscite/legal": "workspace:*"` | pnpm/vite/tsc 解析 |
| 7 | `packages/ui/tsconfig.json` | 新工程引用 `{ "path": "../juscite-legal" }`（ui 发射型 → juscite-legal 发射型，无环：juscite-legal 只引用 services） | tsc -b 图 |
| 8 | `packages/services/package.json` | **注销**过渡映射：删除 `./legal/case-graph-model` 等四条 exports（波1 G 类注记"legal 内核出树过渡映射"的本单兑现）；`packages/services/src/legal/` 目录归零 | — |
| 9 | `tools/bridge`（13 文件） | 桥内核深导入改指 `packages/juscite-legal/src/kernel/*.ts`：bridge_host.mjs(5)、learning_runtime.mjs(3)、layered_memory_runtime.mjs(2)、graph/conflict/learning_kernel/learning/research/timeline/re36_synthetic.mts(各1)、board_synthetic.mts(6)、re30_synthetic.mts(1)、timeline_synthetic.mts(+1) | tsx 运行时/合成自测 |
| 10 | `packages/desktop/scripts/materialize-bridge-bundle.mjs` | 随包补拷 `packages/juscite-legal`（package.json+src，沿 runtime-port 同法）+ essentials 断言 `src/kernel/learningModel.ts` | 打包门禁 |

## 面板 → kit 接线（行为不变机制）

- 面板 25 件迁 `packages/juscite-legal/src/panels/`，import 全改：`@/legal/*`→`./`、内核模型→`../kernel/*.js`、ui 内部件七种→`../ui-kit.js`（同名活绑定，渲染期取到注册真件）；`@zcode/services`（IServiceAccessor 类型）保持直依。
- 内核 6 件迁 `packages/juscite-legal/src/kernel/`（零 import，逐字节未动）。
- `ui-kit.ts` 未注册即渲染 fail-fast 抛错（不静默降级）；类型口径=按面板实际用面的结构类型，注册端赋值编译期校验。
- 桌宠/向导/设置节/v4 composer 等 ui 包内其余 A 类件**不在本单范围**（波4 构建外挂+豁免集），维持原状。

## 边界与诚实记录

1. `packages/juscite-legal/tsconfig.json` 关 `noUncheckedIndexedAccess`（仅 kernel 六件既状口径；HEAD 版对该旗标同报 15 处，系增量 tsbuildinfo 掩蔽、ci_gate fast 无 tsc 步未暴露；出树零行为变更故不因搬家收紧）。panels 仍全严格。
2. 根 `npm run typecheck` 在 HEAD 基线即不绿（229 错，非门禁步，tsbuildinfo 掩蔽存量债，含 desktopPlatform 等 remote-workspace 类型漂移）；本单验证口径=同法全清重建对比：我方树 22 错全部 ⊆ HEAD2 基线 (file,code) 集合，**新增 0**；面板族带走的存量严格债见证据 `evidence/r12-波3-面板插件化-20261029/`。
3. `packages/ui/src/lib/bridgeMaterialAttachments.ts`、`materialImageCompress.ts`、`previewPanePdfContent.tsx` 等 ui 包内支持件仍被 ui 内其他消费方（v4 composer/previewPane）共用，留在树内（出树=波4 裁量，不属 §九 ui/src/legal 面板族）。
4. desktop 桌宠族 13 件（mod-map L3）按波1 分账归波4。
