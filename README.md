# Juscite

Juscite 是一个面向中文律师的 AI 法律工作台：桌面应用 + 本地桥 + 自有包生态，让案件材料整理、法条检索、引证核验与文书加工在你自己的电脑上完成。

> 当前版本 0.1.0，处于早期开发阶段。功能与接口仍在演进，本文档随版本更新。

## Juscite 是什么

传统做法里，律师要把卷宗、合同、判决书粘贴给通用在线 AI 工具，换回一段查不到依据的回答——材料出了本机，法条引用可能凭空捏造，出了错无从追溯。

Juscite 换了一条路：**材料不出本机，结论必须可核。**

- **本地优先**：桌面应用把会话与案件数据落在本地 SQLite 和本地文件，不经云端中转。
- **AI 与确定性计算分工**：AI 负责起草、整理与解释；法条效力、引证核验、文档对比这类"错一次就是事故"的工作由确定性代码完成——结果要么附带出处，要么明确报告"未命中 / 未连接"，绝不编造。
- **面向执业场景**：法律工作台、知识库、检索研究、电子证据、流程编排、利益冲突预检、团队协作、安全审计中心等面板，覆盖从收案到结案的日常动线。

Juscite 不是判官，也不替代律师判断：它把可机械验证的部分交给机器，把判断留给你。

## 快速开始

前提：Node.js（建议 22 或更新）、pnpm 10（仓库经 `packageManager` 钉定 pnpm@10.33.2）、Python 3.12+（仅 Python 能力面与辅助脚本需要）。

```bash
# 在仓库根目录
corepack enable
pnpm install
pnpm typecheck                     # 类型检查
node tools/bridge/ci_gate.mjs fast # 语法/合同测试/e2e/合成自测/品牌检查，退出码 0 即通过
pnpm dev:web                       # 启动 Web 版工作台（开发模式）
```

桌面应用（Electron）：

```bash
pnpm --filter @zcode/desktop dev   # 开发模式
pnpm build:desktop                 # 生产构建
python scripts/launch_desktop_trial.py  # 以产物模式拉起桌面应用（Windows 下推荐此入口）
```

预期结果与常见问题见[快速上手](docs/getting-started.md)。

## 工作原理（一分钟版）

系统由四块组成：**桌面壳**（Electron）承载 **工作台界面**（React 面板族）；界面通过 WebSocket 连接**本地桥**——一个承载全部法律服务（法条手册、引证核验、文档对比、电子证据、流程编排等）与本地数据库的 Node 进程；桥再经一层自有的能力合同接入钉定版本的 **AI 运行时**。另外有一个以固定白名单入口连接外部确定性引擎的 Python 能力面。组件图与数据流详见[架构概览](docs/architecture.md)。

## 目录导航

| 目录 | 内容 |
|---|---|
| `packages/` | 工作区包：基础壳包（`@zcode/*`）与自有功能包（`@juscite/*`），一览见[自有包](docs/packages.md) |
| `tools/bridge/` | 本地桥核心：`bridge_host.mjs`（入口）与 `ci_gate.mjs`（验证门禁） |
| `implementation/python/` | Python 能力面：`legal_entry.py` 冻结白名单入口及功能模块 |
| `lawbook-packs/` | 内置法条数据包（公有领域法律文本，确定性打包、完整性校验） |
| `contracts/` | 机器可读的边界合同（注册点、引用图、类型快照等） |
| `config/` | 客户端内置默认配置 |
| `scripts/` | 构建、引用图生成与启动辅助脚本 |
| `LICENSE` / `NOTICE` / `THIRD-PARTY-NOTICES.md` | 许可与第三方声明 |

## 文档导航

### 律师用户
- [快速上手](docs/getting-started.md)：装起来、跑起来，以及"这个提示是什么意思"。
- [架构概览](docs/architecture.md)：想知道数据存在哪、AI 在哪个环节介入，读这页。

### 开发者
- [快速上手](docs/getting-started.md)：环境、命令与验证门禁。
- [架构概览](docs/architecture.md)：组件分层、一次请求的旅程、边界合同与门禁。
- [自有包一览](docs/packages.md)：每个 `@juscite/*` 包的职责、版本与依赖关系。

### 贡献者
从[快速上手](docs/getting-started.md)跑通环境，读[自有包一览](docs/packages.md)找到感兴趣的包，改动前先看[架构概览](docs/architecture.md)的边界合同一节。

## 参与贡献

在 BSL 1.1 许可下（见下节），你可以自由阅读、修改和再分发本代码（非生产使用）。提交改进前请确保 `pnpm typecheck` 与 `node tools/bridge/ci_gate.mjs fast` 全绿；本仓库尚小，暂无独立贡献指南，以本 README 与 `docs/` 为准。反馈与协作渠道以项目发布页公告为准。

## 许可证

- 本仓库代码以 **Business Source License 1.1（BSL 1.1）** 授权——**source-available，不是 open source**：允许复制、修改、再分发与**非生产**使用；自 Change Date **2030-11-01** 起，所涉版本自动转为 **Apache License 2.0**。全文见 [LICENSE](LICENSE)，随附 [LICENSE-APACHE-2.0](LICENSE-APACHE-2.0)。
- 本产品包含基于开源项目 ZCode（Apache-2.0）的代码，以及第三方组件；归属与声明见 [NOTICE](NOTICE) 与 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
