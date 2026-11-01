# 自有包一览

本页回答"`packages/` 里有哪些 Juscite 自有包、各自做什么、谁依赖谁"，面向准备读代码或改代码的开发者。整体分层见[架构概览](architecture.md)。

## 范围

包含 `@juscite/*` 自有功能包；不包含基础壳包（`@zcode/*`，构成桌面壳与工作台界面的开源基础，职责见架构页）。

所有自有包均为私有工作区包（`private: true`），版本随仓库整体演进（仓库当前 0.1.0）；表中版本为各包 `package.json` 声明值。

## 包清单

| 包 | 目录 | 版本 | 一句话 | 依赖与消费关系 |
|---|---|---|---|---|
| `@juscite/legal` | `packages/juscite-legal` | 0.0.0 | 法律工作台的面板族与内核模型：法律工作台、知识库、检索研究、团队、利益冲突预检、学习迭代、电子证据、流程工作室、安全审计中心 | 依赖 `@zcode/services` 与 React；由 `packages/ui` 经唯一注册点挂载进工作台 |
| `@juscite/vizb` | `packages/juscite-vizb` | 0.0.0 | 面向庭审交付物的可视化渲染内核：大事记表与庭审对抗图——判据守卫不通过即拒绝出图出表，内容照录原文，可输出表格、文档与位图 | 零第三方依赖；由本地桥作为判定与渲染唯一源，面板零判据零渲染 |
| `@juscite/flow` | `packages/juscite-flow` | —（源码包，无独立 package.json） | 流程编排内核：代理运行时、事实核验、交叉验证、原文回引 | 由本地桥直接引用 |
| `@juscite/edisc` | `packages/juscite-edisc` | 0.0.0 | 电子证据内核：锚定、表格、审阅、任务四个子内核 | 零第三方依赖；由本地桥与工作台面板消费 |
| `@juscite/office-bridge` | `packages/juscite-office-bridge` | 0.0.0 | Word/WPS 互操作：只绑回环、配对认证的本地桥接服务，附零构建的任务窗格静态页与旁加载 CLI | 运行时仅用 Node 内建与 `ws`；由本地桥与桌面环境消费 |
| `@juscite/runtime-port` | `packages/juscite-runtime-port` | —（类型件） | AI 运行时最小能力合同：以自有域词定义产品层需要的能力面，协议形状全部引自真源，不照抄任何运行时的 API | 零运行时依赖；本地桥与流程内核唯一认可的能力面 |
| `@juscite/runtime-adapter-opencode` | `packages/juscite-runtime-adapters/opencode` | — | 把 `runtime-port` 合同落到 OpenCode 运行时的适配器 | 换运行时 = 新增一个适配器，产品层零改动 |
| `@juscite/desktop-pet` | `packages/juscite-desktop-pet` | 0.0.0 | 桌面伴侣小窗：独立 Electron 窗口，含精灵、物理与气泡交互 | 依赖 `@zcode/shared` 与 Electron；由桌面壳装配 |

工作区里另有两个非 `packages/` 目录的自有包：`@juscite/bridge`（`tools/bridge`，本地桥本体）与 `@juscite/mock-host`（`tools/mock_host`，界面开发用的合成数据桩）。

## 依赖关系速览

- 界面线：`packages/ui` --注册点--> `@juscite/legal` --> `@zcode/services`。
- 桥线：`@juscite/bridge`（tools/bridge）--> `@juscite/vizb`、`@juscite/edisc`、`@juscite/flow`、`@juscite/legal` 内核、`@juscite/office-bridge`、法条数据包。
- 运行时线：`@juscite/bridge` --> `@juscite/runtime-port` <--实现-- `@juscite/runtime-adapter-opencode` --> OpenCode 运行时。
- 桌面线：`packages/desktop` --> `@juscite/desktop-pet`；打包时把本地桥与所需自有包物化进安装产物。

## 相关文档

- 想知道这些包在系统里怎么协作：读[架构概览](architecture.md)，含组件总图与一次请求的旅程。
- 想跑起来亲手看：读[快速上手](getting-started.md)。
