# 索引策略

本页回答当前阶段要不要新建索引、先建哪一种、产物放在哪。面向改 Juscite 代码的开发者。清点日期：2026-11-01，以仓库内源码为准。

## 范围

包含：仓库里已经在跑的检索与索引、三类索引的取舍、下一步只做开发导航时的落地顺序。

不包含：向量库实现、`lawbook-packs/` 内容或版本变更。本页不引入新的检索引擎。

## 结论

**下一步只做 A：开发者代码导航。** 产品侧的稀疏检索和 SQLite 全文已经按设计在跑，当前阶段不要换成神经向量库。法条包仍小，全文扫描够用；包变大之后再在桥的本地库加缓存，不要改包内的 `pack.sqlite3`。

2026-11-01 清点（排除 `node_modules`、`dist`、`out`、`.venv`）：非测试 TypeScript / TSX / Python 约 83 万行，加上桥的 `.mjs` / `.mts` 约 90 万行；测试另计约 52 万行。行数集中在 `packages/ui` 与 `packages/services`。这个新公开仓库的 GitHub 代码搜索不可作为导航依据，以本地工具为准。

## 已经有什么

这些都是**产品数据或工程门禁**用的索引，不能当成全仓库的 IDE 符号索引。

| 用途 | 位置 | 实际机制 |
|---|---|---|
| 所内知识库问答 | `tools/bridge/kb_service.mjs`，检索编排在 `tools/bridge/bridge_host.mjs` 的 `kbRetrieve` | 检索器版本 `juscite-sparse-v1`。文件头写明零 embedding、零向量库。CJK n-gram + 法律同义词多路查询，RRF（`k=60`）融合，多因子打分后重排。`kb_documents` 行数 ≥ `KB_FTS_THRESHOLD`（2000）才走 SQLite FTS5（`kb_chunks_fts`，trigram，失败降级 unicode61），否则内存扫描。面板 `packages/juscite-legal/src/panels/KnowledgeBasePanel.tsx` 只编排展示，检索在桥上 |
| 用户知识库 RAG | `implementation/python/kb_rag.py`，经 `implementation/python/legal_entry.py` 白名单调用 | 合同 `kb-rag/1`，检索合同名 `f71_hybrid/1`。缺省后端 `local-deterministic-v1`：sha256 把字符 n-gram 桶化成 256 维 TF，再与词面覆盖率混合。代码写明这不是神经向量模型；未知 `kb_backend` 具名拒绝，不静默换后端。状态是 `kb_state_root` 下的 JSONL，缺配置则 `NOT_CONNECTED` |
| 专家分身咨询 | `implementation/python/expert_store.py` | 同一套确定性 n-gram 评分，零模型。咨询越界则具名弃答 |
| 案件材料全文 | `tools/bridge/material_service.mjs` 的 `case_material_chunks_fts` | 桥 SQLite FTS5（trigram，短词回落 LIKE）。`CaseMaterialsPanel` 只搜最新版 |
| 会话文档块 | `tools/bridge/bridge_store.mjs` 迁移 `0003_document_fts_v2` | 普通表为权威副本，触发器同步 external-content FTS5。这是会话文本，不是源码 |
| 法条手册 | `tools/bridge/lawbook_service.mjs` + `lawbook-packs/` | 包内 `pack.sqlite3` 只有 `law` / `category` 与名称、类目索引，**没有 FTS**。标题搜索走 `titleMatches`，全文搜索逐部解析后做子串包含，结果帽 200。包根 README：32 部、约 1.7MB。首载 sha256 + `PRAGMA quick_check`，失败则面板「法条包不可用」 |
| 任务列表 | `packages/services/src/session/taskIndexRepo.ts`，同步器 `packages/services/src/zcode-agent/zcodeTaskIndexSyncer.ts` | 桌面壳的会话/任务 SQLite（`~/.zcode/v2/tasks-index.sqlite`）。`searchable_text` 用 `LIKE`。对应协议是 `packages/shared/src/zcode-protocol-v4/sessions-index.ts` 的列表活性，不是源码索引 |
| 界面内查找 | `packages/ui/src/v4/conversationFindIndex.ts`；`packages/ui/src/workspace-file-tree/useWorkspaceFileSearchIndex.ts` | 已加载对话的内存子串；工作区文件列表的过滤。都不建符号库 |
| 边界引用图 | `scripts/gen-ref-graph.mjs` → `contracts/ref-graph.json`，查询 `scripts/query-graph.mjs` | 门禁用的符号级 import 图。入库基线（`meta.generated` 2026-10-30）：扫描 190 个文件、124 条边、39 个被消费导出、5 个合同模块。扫描面是桥顶层脚本、若干 `@juscite/*` 源码和 `contracts/pin-points.json`，**不覆盖** `packages/ui` 与 `packages/services` |

外部类案混合检索（`lcr.hybrid-search/1`）在 `legal_entry.py` 只做回执审计。外部引擎没有 `execution.hybrid` 时具名拒绝，本仓库不自带那份向量语料。

`kb_rag` 复用的名字 `f71_hybrid/1` 是检索接口名。它和上面的外部类案回执不是同一个库。

## 三类索引，当前建哪一种

### A. 开发者代码导航 — 现在做

给改代码的人用：TypeScript 工程引用 + 编辑器语言服务，桥脚本和 Python 用 ripgrep，可选本地 ctags。有 SciTools Understand 许可证的人可以另建个人知识库（`.ua` / `.udb`），只留在本机。

仓库里已经有一半：`tsconfig.base.json` 开了 `composite`，壳包之间有 `references`。`pnpm typecheck` 是

```bash
tsc -b packages/rpc packages/provider packages/provider-node packages/shared \
  packages/services packages/client packages/ui packages/web packages/desktop \
  packages/desktop/tsconfig.host.json
```

`packages/ui` 的工程引用带上了 `packages/juscite-legal`，桌面主进程带上了 `packages/juscite-desktop-pet`。缺的是：

- 仓库根没有 solution `tsconfig.json`。语言服务要打开某个包的 `tsconfig`，或依赖上面这条 `tsc -b` 列表，才会串起整张图。
- `packages/juscite-vizb`、`packages/model-option-map` 有自己的 `tsconfig.json`，不在 `pnpm typecheck` 这条链上。
- `tools/bridge` 的 `.mjs` 和 `implementation/python` 不进 tsserver。仓库里没有 `pyrightconfig.json`、`pyproject.toml`、ctags 配置。
- 边界引用图故意只覆盖接面，不能代替「这个符号在 `packages/ui` 哪里被调用」。

这一类**不接入**桌面壳，也不接入本地桥。它只服务编辑器和命令行。

### B. 语义 / 神经向量库 — 以后，单独决策

产品搜索今天的合同是稀疏和确定性的：所内库声明零 embedding；用户库缺省后端自己写明不是神经模型，并且拒绝未知后端。把默认路径换成 embedding 模型，会改掉可复现打分、离线可用和 fail-closed 这三条约定。

若将来产品明确要求语义召回，做法是在 `kb_rag.BACKENDS` 旁**注册一个新后端**（新的 `backend_id`，权重只放本机，模型缺失则具名失败），用配置 `kb_backend` 显式打开。所内库的 `juscite-sparse-v1` 与法条的确定性查找保持原样。向量文件放用户数据目录，不进 git。当前阶段不建这个库，也不选模型。

### C. 文档 / 法条检索 — 维持现状，包变大再加桥侧缓存

所内知识库、案件材料、会话文档块已经走桥上的稀疏打分和 FTS5。用户知识库走 `kb_rag` 的确定性评分。这些路径继续用，不另起一套。

法条包是另一条线：内容在 `lawbook-packs/`，完整性由 `pack.meta` 的 sha256 与文件大小钉死，桥对不上就整包不可用。现在 32 部、目录约 1.7MB，`pack.sqlite3` 约 40KB，全文用子串扫描。这个规模不必建第二份全文索引。

包增长到线性扫描成为问题时，在**桥自己的 SQLite**里加 FTS5 缓存（与 `kb_chunks_fts` 相同的外部内容表模式），以 `pack.meta.hash` 为键，校验通过后在本地重建。缓存跟着桥库走，不写进 `pack.sqlite3`，因此不改包哈希、不改包版本。HTTP 仍是 `lawbook_service` 上的 `/api/legal/laws*`，`LawBookPanel` 只展示。

## 产物放哪

| 产物 | 路径 | 是否入库 |
|---|---|---|
| 边界引用图、类型快照 | `contracts/ref-graph.json`、`contracts/type-snapshot.json` | 入库。文本，门禁 diff 用。只在接面变更时由 `node scripts/gen-ref-graph.mjs` 重生成 |
| TypeScript 增量信息 | 各包 `*.tsbuildinfo` | 不入库（`.gitignore` 已忽略） |
| ctags | `.local/tags` | 不入库（`.local/` 已忽略） |
| Understand 知识库 | `.local/understand/` 下的 `.ua` / `.udb` | 不入库。个人许可证产物，不是 CI 输入 |
| 桥上的 FTS（知识库、材料、会话、将来的法条缓存） | `~/AppData/Roaming/Juscite/bridge/bridge-<port>.db`（`tools/bridge/bridge_store.mjs` 的 `openBridgeStore`） | 不入库。运行时库；`*.db` 已忽略 |
| 任务列表库 | `~/.zcode/v2/tasks-index.sqlite` | 不入库。桌面壳用户数据 |
| 用户知识库 JSONL | 配置项 `kb_state_root` 指向的目录 | 不入库 |
| 法条包 | `lawbook-packs/base/pack.sqlite3` 与 `pack.meta` | 已入库，但是**内容包**，不是可随意重建的开发索引。改它会改 sha256 |

落地 ctags 或 Understand 时，另补 `.gitignore`：`tags`、`*.ua`、`*.udb`。在那之前不要把这些文件加进提交。

## 和桌面壳、本地桥怎么接

桌面壳（`packages/desktop`）拉起本地桥；工作台经 WebSocket RPC 与 HTTP 调用桥。检索的归属已经固定：

- 所内问答：面板 → 桥 `kbRetrieve` → `kb_service.mjs` + `kb_chunks_fts`。
- 用户知识库 / 专家分身：桥 → `legal_entry.py` 白名单 → `kb_rag.py` / `expert_store.py`。
- 法条：`LawBookPanel` → 桥 `createLawbookService` 的 `/api/legal/laws*`。
- 案件材料：`CaseMaterialsPanel` → 桥材料服务的 FTS5。
- 任务列表：壳内 `TaskIndexRepo` + `zcodeTaskIndexSyncer`，与桥上的法律检索无关。

A 类索引停在编辑器，不增加桥端口，不增加面板。C 类将来的法条 FTS 只改 `lawbook_service.mjs` 的 `search` 内部，响应形状保持 `{ mode, query, count, results }`。B 类若做，只加 `kb_rag` 的后端注册项，不改所内库的 `juscite-sparse-v1`。

## 实施顺序

1. **本页。** 先把三类索引和已有实现写清。不改代码，不改法条包。
2. **日常导航，零新产物。** 跨语言查找用 ripgrep（仓库已忽略 `node_modules`）。查接面用 `node scripts/query-graph.mjs summary`，以及 `consumers` / `symbols` / `imports` / `pins`。TypeScript 跳转依赖现有 project references；全图类型检查用根目录 `pnpm typecheck`。
3. **补一张根 solution `tsconfig.json`（单独的代码 PR）。** 引用与 `pnpm typecheck` 相同的工程，并把 `packages/juscite-vizb`、`packages/model-option-map` 纳入或明确排除。不改变各包的 `composite` 与 `outDir` 行为，不把声明产物提交入库。
4. **桥脚本与 Python 的本地符号表（可选）。** 用 universal-ctags 写到 `.local/tags`，把 `.mjs`、`.py`、`.ts`、`.tsx` 纳入，排除 `node_modules`、`dist`、`lawbook-packs`。需要时再忽略 `tags`、`*.ua`、`*.udb`。Understand 仅当本机已有许可证时使用，库文件放 `.local/understand/`，不进 CI。
5. **法条 FTS 缓存（包变大之后，另案）。** 触发条件是全文子串扫描在目标包尺寸下变慢，而不是现在这 32 部。缓存放桥库，键为 `pack.meta.hash`，校验失败不建索引。不修改 `lawbook-packs/`，不抬包版本。
6. **神经向量后端（更后，另案）。** 仅在产品要求语义召回、并且接受「新后端、本机权重、缺失即失败」时再做。默认路径保持 `juscite-sparse-v1` 与 `local-deterministic-v1`。

## 相关文档

- 组件与数据流：[架构概览](architecture.md)
- 环境与 `pnpm typecheck`：[快速上手](getting-started.md)
- 自有包职责：[自有包一览](packages.md)
- 法条包完整性：`lawbook-packs/README.md`
