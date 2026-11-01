# Adapter 行数纪律与能力对照（r12 波2.5 基线 · 设计 §一 L1b/§五③）

> 规则：**全部 adapter 合计行数 ≤ 桥代码 10%**（对标 dsh 模型层 ~3%）。进 upgrade 门禁监控
> （波5 落检查），超限爆红。本文件=基线台账；改 adapter 或桥面后复核并更新数字（附计数命令原样输出）。

## 口径（确定性计数，无歧义）

- **桥代码** = `tools/bridge/` 顶层 `*.mjs + *.mts`（与 ci_gate nodecheck 同目录口径），
  排除 `.bak` 与 `_tmp_` 前缀探针；不含子目录（node_modules/packages 构建残留不属桥源）。
- **adapter** = `packages/juscite-runtime-adapters/**/*.{mjs,ts}`（递归，排 node_modules）。
  L1a port 合同（`packages/juscite-runtime-port/`）是类型件不计入 adapter 预算（它是产品层依赖的接口，不是胶水）。

计数命令（工作区任意目录可跑；python）：

```python
import os, glob, io
def n(p):
    return sum(1 for _ in io.open(p, encoding="utf-8", errors="replace"))
bridge = [f for f in sorted(os.listdir("tools/bridge"))
          if (f.endswith(".mjs") or f.endswith(".mts")) and ".bak" not in f and not f.startswith("_tmp_")]
btot = sum(n(os.path.join("tools/bridge", f)) for f in bridge)
atot = 0
for dp, dns, fns in os.walk("packages/juscite-runtime-adapters"):
    dns[:] = [d for d in dns if d != "node_modules"]
    for fn in fns:
        if fn.endswith(".mjs") or fn.endswith(".ts"):
            atot += n(os.path.join(dp, fn))
print(len(bridge), btot, atot, "%.2f%%" % (atot * 100.0 / btot))
```

## 基线（2026-10-29 · r12 波2.5 落地时实测）

| 项 | 文件数 | 行数 |
|---|---|---|
| 桥代码（tools/bridge 顶层 .mjs+.mts） | 99 | **33,375** |
| adapters 合计（现仅 opencode） | 1 | **282** |
| **占比 / 10% 上限** | — | **0.84% / ≤10%（上限 3,337 行）** |
| （参照）L1a port 合同 index.ts | 1 | 158（含纪律注释；纯类型+适配基类，零运行时依赖） |

### 波5 复核（2026-10-29 · ci_gate upgrade ③步实跑输出）

自波2.5 后桥面有增改（波4 打包链/timeout 调整等），按本文件规则复核更新：

| 项 | 文件数 | 行数 |
|---|---|---|
| 桥代码（同口径） | 99 | **33,577** |
| adapters 合计（同口径） | 1 | **283** |
| **占比 / 10% 上限** | — | **0.84% / ≤10%（上限 3,357 行）** |

> 来源：`node tools/bridge/ci_gate.mjs upgrade` 第③步原样输出——
> `adapter 行数纪律：adapter 1 文件 283 行 / 桥 99 文件 33577 行 = 0.84%（上限 ≤10%）`。
> 自波5 起该比值进 upgrade 门禁自动监控（超限爆红），本表为人工台账存档。

- oc28client.mjs（143 行）自 tools/bridge 迁入 adapter 并扩为 port 域面实现（wire→域归一 +15 行级、
  port 方法壳）；同日 tools/bridge 删除该文件。
- 换底座成本口径：产品层唯一 adapter 引用=bridge_host.mjs 组合根一行
  （`import { createOpenCodeRuntime }` + `const runtime = createOpenCodeRuntime()`）；
  新 runtime=新增 `packages/juscite-runtime-adapters/<name>` 一个包（只写 adapter）+ 换组合根一行。

## 能力对照表（D6；adapter 未开放的能力调用即抛 UnsupportedCapabilityError）

| 能力面（runtime-port 域词） | opencode 绑定现状 |
|---|---|
| 生命周期 start/shutdown/health | health=GET /api/info 探活（start/shutdown=no-op：serve 进程不归 binding 拥有） |
| 会话创建 createSession | 已接线（POST /api/session，扁平 directory 优先 4xx/5xx 回落 location 形状；模型 ModelSelection→wire 映射） |
| 发送 send | 已接线（POST /api/session/{sid}/prompt） |
| 事件流增量 subscribeEvents + pullTranscript | 已接线（SSE /api/event→域事件词表；转录拉取→域形状归一，断线窗由对账兜底） |
| 工具注册 registerTools | **已开放（2026-10-31 · 施工波三轮桥健②）**：PUT /api/experimental/mcp/{server} 运行时挂载（{config:LocalConfig} wire 形状只住 adapter；不落配置不跨重启）→ 轮询 GET /api/mcp 三态收口（connected=成／failed=具名错／挂载后不在册=oc28 config policy 外闸移除，具名错不伪造成功）。执行体=桥侧 G6 连接器 stdio MCP（tools/bridge/g6_connector_mcp.mjs，oc28 作为 MCP client 拉起）；注册目录经 JUSCITE_G6_TOOL_MANIFEST 传递。**边界：oc28 无「自定义工具 HTTP 注册」端点——本能力面=运行时 MCP 挂载这一条 wire 面（V2_HTTP_API_AUDIT.md 实证无 tool 直注路由）；tools/call 只能经 agent 工具使用触发（无直调 HTTP 端点）** |
| 权限门 setPermissionGate | **已开放（同上）**：专用 /api/event SSE 流过滤 permission.asked 事件→域请求 {runtimeSessionId,tool,summary,respond}→gate 布尔→POST /api/session/{sid}/permission/{requestID}/reply {decision: once\|reject}；gate 未设=null 关闸（不动 pending，oc28 侧策略自决）；gate 抛错=按拒应答（fail-closed 不挂死）。**边界：只应答 ask 态请求——allow/deny 已由 oc28 规则/策略面落定不产生事件** |
| 取消 cancelTurn | **未开放**（同上；桥面今日以时限熔断收口） |

### 三轮复核（2026-10-31 · 施工波三轮桥健②后，本文件口径计数命令实跑输出）

| 项 | 文件数 | 行数 |
|---|---|---|
| 桥代码（tools/bridge 顶层 .mjs+.mts，同口径） | 135 | **45,380** |
| adapters 合计（同口径，仍仅 opencode 一个包） | 1 | **361** |
| **占比 / 10% 上限** | — | **0.80% / ≤10%（上限 4,538 行）** |

> 来源：本文件「计数命令」python 原样实跑输出 `135 45380 1 361 0.80%`。
> 本轮 adapter +78 行=registerTools/setPermissionGate 两能力面（挂载/轮询/事件流过滤/应答）；
> 桥面 +11,803 行系施工波二/三轮其余单元增量（本行只记口径复核，不归属本单）。

## 诚实边界

- port 合同文件未纳入根 `typecheck` 工程引用（tsc -b 名单未含新包；adapter 为 .mjs 不经 tsc）——
  类型正确性当前由 tsx 装载冒烟 + 桥 e2e 23 项兜底；入工程引用随波5 索引件一并处理。
- 探针/诊断（conversation.probe.mts、re30_synthetic.mts）仍 import adapter 的 wire 级导出
  （loadCredentials/makeClient/waitForAssistant）——产品层（bridge_host.mjs）禁用该面，只走 port。
