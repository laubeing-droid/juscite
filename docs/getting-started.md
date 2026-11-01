# 快速上手

本页回答"怎么把 Juscite 装起来、跑起来、确认它是好的"，面向所有读者；开发细节见[架构概览](architecture.md)。

## 范围

包含：环境前提、安装、Web 与桌面两种运行方式、安装验证、常见问题。
不包含：功能使用教程（界面内自带新手引导）、部署与许可管理。

## 前提环境

| 依赖 | 版本 | 用途 |
|---|---|---|
| Node.js | 建议 22 或更新 | 桌面壳、工作台界面、本地桥、构建工具链 |
| pnpm | 10（仓库钉定 pnpm@10.33.2） | 包管理，`corepack enable` 后自动启用 |
| Python | 3.12 或更新 | Python 能力面（`implementation/python/`）与辅助脚本，纯前端使用可不装 |

网络需能访问 npm registry 与 Electron 二进制下载源。仓库根 `.npmrc` 指向官方 registry。

## 安装

在仓库根目录：

```bash
corepack enable        # 启用钉定的 pnpm 版本
pnpm install
```

## 运行

**Web 版（开发模式）**

```bash
pnpm dev:web
```

启动 Vite 开发服务器并打开工作台界面。界面开发可配合 `tools/mock_host/`（`@juscite/mock-host`）提供的合成数据桩。

**桌面应用（Electron）**

```bash
pnpm --filter @zcode/desktop dev         # 开发模式（热更新）
pnpm build:desktop                       # 生产构建
python scripts/launch_desktop_trial.py   # 产物模式拉起
```

桌面应用启动时会自行拉起本地桥（`tools/bridge/bridge_host.mjs`，WebSocket 端口 3030）。`launch_desktop_trial.py` 会先校验构建产物与本地 Electron 二进制在位，再以产物模式启动；Windows 下建议用这个入口，避免 Git Bash 在中文路径下直启 Electron 的乱码问题。

## 验证安装

"安装成功"与"产品可用"是两件事，分开确认：

1. **安装成功**：`pnpm install` 无错误，且以下两项全绿——

   ```bash
   pnpm typecheck
   node tools/bridge/ci_gate.mjs fast
   ```

   `fast` 门禁覆盖桥源码语法检查、UI 合同测试、桥端到端测试、各合成自测与品牌检查，单命令退出码 0/1 可判。

2. **产品可用**：桌面应用能启动、本地桥能连接（应用内会话可收发）、法条手册面板能检索出条文。

## 常见问题

| 症状 | 可能原因 | 如何确认 | 修复或下一步 |
|---|---|---|---|
| `pnpm install` 长时间卡住 | 网络无法访问 npm 或 Electron 下载源 | 观察输出停在哪个包 | 配好网络代理或镜像后重跑 `pnpm install` |
| 桌面应用提示桥连接失败 | 端口 3030 被占用，或已有 Juscite 实例在跑 | 检查 3030 端口占用进程 | 关闭已有实例后重启应用 |
| Windows 下直启 Electron 出现乱码/参数错位 | Git Bash 在中文路径下派生进程的已知问题 | 换用脚本启动是否复现 | 用 `python scripts/launch_desktop_trial.py` |
| 法条手册面板显示"法条包不可用" | 法条数据包完整性校验未通过（sha256 / 快速检查任一失败） | 重启后仍复现即为包损坏 | 恢复或重装 `lawbook-packs/` 后重启；产品不会静默使用残包 |
| 某功能显示"未连接" | 对应能力依赖的外部引擎或配置未就绪（如 Python 能力面） | 对照 `implementation/config/legal-entry.example.json` | 按需配置；这是 fail-closed 设计行为，不是崩溃，产品不会伪造成功 |
| `ci_gate.mjs fast` 失败 | 见输出中第一个失败段落 | 阅读门禁输出 | 修复后重跑；门禁各步骤具名，可逐段定位 |
| Python 侧测试大量跳过 | `implementation/tests/` 依赖不随本仓库分发的外部引擎检出 | 查看跳过原因 | 属预期行为：未配置的依赖按守卫跳过，不产生假通过 |

## 下一步

- 想知道数据存在哪、AI 在哪个环节介入：读[架构概览](architecture.md)。
- 想读代码、找感兴趣的模块：读[自有包一览](packages.md)。
