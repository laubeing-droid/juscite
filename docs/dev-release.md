# 开发与发布流程

本页给维护者一条可以独自走完的路径：分支、提交前的本地门禁、PR、合并、版本标签、桌面试跑。命令只写仓库里已经存在的脚本。GitHub 上目前没有自动检查。

## 范围

包含：日常开发到一次手工发布。不包含功能说明（见[快速上手](getting-started.md)）和许可条文。

## 现在处在哪

v0.1.0，BSL 1.1，基于 ZCode 的早期公开 source-available MVP。本地门禁已经能跑。缺的是远程 CI、PR 自动检查和发布打包流水线，不是重写产品。

| 已经能在本机做 | 还没有，不要当成已完成 |
|---|---|
| 根 `package.json` 的 `version`（当前 `0.1.0`）是安装包版本来源 | `.github/workflows` 不存在，Actions 为空 |
| `pnpm typecheck`；`node tools/bridge/ci_gate.mjs` 的 `fast` / `persist` / `full` / `package` / `upgrade` | PR 自动检查、自动发版 |
| Web / Electron 开发模式，以及 Windows 上的产物试跑 | 可用的自动更新源。feed 固定为 `https://updates.juscite.invalid/`，自动更新构建期默认关 |

PR 页面没有检查项，就表示没有 CI 结论。本机退出码 0 才算这条门禁通过。远程 CI 接上之后，改这一节和文末 TODO，不要留着「Actions 为空」。

## 1. 日常分支

环境见[快速上手](getting-started.md)：Node.js 22+、pnpm 10.33.2（`corepack enable`）。只有改 Python 能力面或跑桌面启动脚本时才需要 Python 3.12+。

```bash
git checkout main
git pull
git checkout -b <短主题>
pnpm install
```

按一人维护来走：分支从 `main` 拉出，做完合回 `main`。合入不依赖 Actions 状态检查（当前工作流数为 0）。GitHub 分支保护若在网页设置里另有规则，以设置为准；没有远程勾选可以当成已经通过。

## 2. 开 PR 前的本地门禁

在仓库根执行。两条都要退出码 0，这是每次改动的必跑项（README 的贡献门槛与此相同）：

```bash
pnpm typecheck
node tools/bridge/ci_gate.mjs fast
```

`fast` 覆盖桥源语法、UI 合同测试、桥端到端、合成自测和品牌检查。日志在 `.local/ci-gate-logs/`（不入库）。失败时看第一个失败步骤，修完整段重跑。

改动碰到下面的面时再加跑。这些仍是本机命令：

| 何时 | 命令 | 注意 |
|---|---|---|
| 要确认重启桥后会话还在 | `node tools/bridge/ci_gate.mjs persist --port 3055` | 不带 `--port` 会动默认的 :3030，并停掉正在跑的桥。探活和结束进程按 Windows（`netstat` / `taskkill`）编写。 |
| 改 `@zcode/*` 基础壳，或改了 `contracts/` 接面 | `node tools/bridge/ci_gate.mjs upgrade` | 含豁免 patch 预检、类型快照 diff、适配层行数、品牌和 `fast`。接面符号变了就先 `node scripts/gen-ref-graph.mjs`，把 `contracts/ref-graph.json` 与 `contracts/type-snapshot.json` 的 diff 放进同一个提交。 |
| 要交出 Windows 安装包 | 第 6 节的 `package` | 重，不作为每次 PR 的门。 |

`full` 等于 `persist`（其中已含 `fast`），不必两套都跑。

`implementation/python` 不在必跑门禁里。外部引擎没检出时，相关测试会跳过；跳过不是通过。

## 3. PR 清单

PR 目标分支是 `main`。描述里写明本机跑了哪几条、退出码是什么。没跑的不要写成通过。

- [ ] `pnpm typecheck` 退出码 0
- [ ] `node tools/bridge/ci_gate.mjs fast` 退出码 0
- [ ] 动过基础壳或接面时，加跑项已跑，合同 diff 在本 PR 里
- [ ] 没有改 `LICENSE`，也没有夹带无关的版本号变动
- [ ] 没有写「GitHub CI 已通过」——现在没有这项检查

## 4. 合并

本地门禁通过后，维护者把 PR 合入 `main`。Actions 不会拦截这次合入，也不会为它提供通过证明。合入后在更新过的 `main` 上再跑一遍第 2 节的两条命令。

## 5. 版本、标签与发布

产品版本只改仓库根 `package.json` 的 `version`。桌面构建由 `packages/desktop/scripts/build-metadata.mjs` 读取它，写入 `packages/desktop/out/metadata/build-meta.json`（版本、8 位 commit、构建时间）；electron-builder 用这份版本号。`@juscite/*` 仍是私有工作区包（`0.0.0` 或无独立版本），不要跟着产品号改。

发版是手工步骤，仓库里没有发版脚本：

1. 在要发布的 `main` 上确认第 2 节两条命令为 0。要附安装包时再跑第 6 节。
2. 只改根 `package.json` 的 `version`（语义化版本）并单独提交。日常发版不要改 `LICENSE` 的 Change Date 或 Licensed Work 表述。
3. 看现有标签，再打附注标签并推送：

```bash
git tag -l
git tag -a vX.Y.Z -m "Juscite vX.Y.Z"
git push origin vX.Y.Z
```

`git tag -l` 为空时，版本点只存在于根 `package.json` 和提交说明里（初始公开是提交 `Juscite v0.1.0 — initial public release`，不是 tag）。

4. 在 GitHub 上用该 tag 建 Release，正文写变更和本机门禁结果。安装包不会自动附上，需要的话从本机 `packages/desktop/dist/` 手工上传。

自动更新不是发布渠道。`packages/desktop/electron-builder.config.js` 的 `publish.url`、`packages/desktop/dev-app-update.yml`、`packages/desktop/src/main/autoUpdater.ts` 的 `JUSCITE_UPDATE_FEED_ORIGIN` 都指向 `https://updates.juscite.invalid/`。`ZCODE_AUTO_UPDATE_ENABLED` 默认 false。这三处换成真实地址之前，应用内不会收到更新。

## 6. 桌面试跑与安装包

开发与产物试跑：

```bash
pnpm dev:web
pnpm --filter @zcode/desktop dev
pnpm build:desktop
python scripts/launch_desktop_trial.py
```

`pnpm build:desktop` 只产生 `packages/desktop/out/`，不是安装包。`launch_desktop_trial.py` 检查 `out/` 和 `packages/desktop/node_modules/electron/dist/electron.exe` 后，以产物模式拉起 Electron，面向 Windows。它只读探测 `%APPDATA%\Juscite\state\opencode\service-local.json`，不启动 oc28；没有这份注册文件时，对话保持 fail-closed。

Windows x64 NSIS 安装包（本地门禁，不是 GitHub 任务）：

```bash
node tools/bridge/ci_gate.mjs package
```

顺序是桥语法检查、许可骨架自测、`build-metadata`、生产构建、`electron-builder --win --x64`。通过时 `packages/desktop/dist/` 里有本轮新生成的安装 exe、对应 blockmap、`latest.yml`，并且随包桥探针通过。打包按小时计，只在要交付安装包时跑。产物留在本机。代码签名默认不跑，只有设置 `ZCODE_ENABLE_WINDOWS_SIGN=1` 才走 Windows 签名钩子。

## 远程 CI（TODO）

接入 GitHub Actions 时先做日常门，不要把 `package` 放进每次 PR：

1. checkout
2. Node.js 22，pnpm 10.33.2（与根 `packageManager` 一致）
3. `pnpm install`
4. `pnpm typecheck`
5. `node tools/bridge/ci_gate.mjs fast`

`package` 另要 Windows runner 和 Electron / NSIS 工具链，单独一条工作流。`.github/workflows/` 里出现文件并且某次运行给出结论之前，PR 上没有 CI 状态。

## 相关文档

- [快速上手](getting-started.md)
- [架构概览](architecture.md)（`ci_gate` 模式表）
- [自有包一览](packages.md)
