# OpenCode v2.0.28 原生 Solid 法律工作台补丁

适用：官方 `anomalyco/opencode` 固定提交 `026b106bc5d41b679ffc413264229c340871e4d3`（v2.0.28）。这是独立交付补丁，没有应用到生产或原稿，没有安装、启动或部署。首次目标是可使用的原生法律工作面，JC／法律 Harness 后续分批接入。

补丁新增 `packages/app/src/legal-workbench/legal-workbench.tsx`，并仅修改真实入口 `packages/app/src/shell/routes/routes.tsx`：在原生 Shell 内包裹法律工作台。使用 Solid signals／For／Show 和原生 Router A；不新增依赖，不复制 ZCode，不创建第二会话、模型循环或 Python UI。

可用交互：五场景任务简报、客户目标／材料／约束编辑、复制到原生会话、导出 Markdown、新建原生任务及设置导航。原生会话输入框、文件、provider／模型、权限及工具继续由 OpenCode 负责。复制后需要用户粘贴和发送；按钮不伪装自动提交。简报是当前页面内存，不是案件数据库，刷新前须导出。JC／Harness未接能力明确显示，不冒充完成。

## 应用步骤（由人工在获准的独立源码检出执行）

1. 准备固定提交的完整官方源码，保留其 LICENSE／notices，确认工作树没有与两个目标路径冲突的修改。
2. 运行只读检查：`pwsh -File .\check-ui-patch.ps1 -SourceRepo '绝对源码路径'`。该命令只做 HEAD 与 `git apply --check`，不改代码。
3. 人工应用：在源码根运行 `git apply -- '本交付目录\opencode-v2.0.28-legal-workbench.patch'`。不要再复制源 TSX，以免重复添加。也可人工复制新增 TSX，并按 diff 的两处修改入口。
4. 固定提交根 `package.json` 已核包管理器为 **Bun 1.4.2**；依赖准备与原生件步骤按整包脚本执行。准备完成后，从源码根启动 **`bun run dev:desktop`**（根脚本为 `bun --cwd packages/desktop dev`，desktop脚本实际执行 `bun ./scripts/dev.ts`）。或在 `packages/desktop` 工作目录执行 `bun run dev`。app单独开发入口是源码根 `bun run dev:web`，它只启动Web开发，不替代有认证服务配置。必须先应用整包的独立service／数据根补丁，避免复用用户当前运行的全局服务。
5. 可在源码根执行 `bun --cwd packages/app typecheck`、`bun --cwd packages/app build`；desktop实际包命令为 `bun --cwd packages/desktop build` 和对应平台 `package:win`。这些是从固定package.json核到的命令，**本轮均未运行**。安装／发布脚本由整包交付另行提供，不能将补丁检查写成构建通过。
6. OpenCode SDK的 `database.path`、`events.persist` 不是已核CLI配置文件键；本补丁不向 `opencode.json` 写这些选项。原生serve的准确数据库／event配置按整体运行时隔离交付核验，不混用SDK无listener与原生WebUI服务拓扑。
7. 打开原生任务，点“编写法律任务”，填简报；复制、粘贴至原生 Composer，选择获准材料、模型与权限后发送。验证下面各项后再交中期试用。

## 验收与状态

- 只读静态检查：补丁可逆向重建基线、挂载点唯一、无 React／新依赖／虚构业务 API；记录在 `static-check.json`。
- 实际 `git apply --check`：需要完整源码检出，本轮没有在生产执行；脚本已交付。
- Typecheck／build／Electron启动／UI交互：**NOT_RUN**，不能声称可运行已验。
- 待真机验证：原生首页／会话／新任务正常布局；键盘与窄屏；五场景选择与表单；剪贴板失败提示；Markdown落地；原生模型与权限选择、附件读取、工具执行、会话恢复；新布局不遮挡审批对话框。
- 剩余风险：包装后的 flex 高度与原生 SessionRouteFrame 的实际排版需真机验证；导出在普通浏览器与Electron下载处理上有差异；首期通用模型处理不代替确定性JC结果或Harness业务准入。

不要为缺少JC／Harness阻止原生工作面试用，也不要把它们未接入写成已通过。后续功能继续依据全量施工台账接入。

这是一份可人工应用的**中期UI增量**，不是V7全部法律业务实现；五场景简报为任务入口，证据重评、取证、策略、原生编辑、回款等完整业务仍按主施工方案分批接入。
