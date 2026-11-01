# mock Host（M1-B）

合成数据、仅 dev 点亮用。协议结论与迭代指南见 `NOTES.md`。

## 启动

```bash
cd <worktree 根>
corepack pnpm exec tsx tools/mock_host/mock_host.mjs   # 监听 http+ws :3030
```

（tsx 为必须：上游 @zcode/* 包 exports 指 TS 源，Node 直跑不吃 TS；与上游 server 的 tsup bundle 等效的轻量替代。）

## UI 侧

vite dev 代理已配（`packages/web/vite.config.ts`）：`/ws`、`/api` → localhost:3030。
`corepack pnpm dev:web` → 打开 http://localhost:5173

## 自测

```bash
corepack pnpm exec tsx tools/mock_host/roundtrip.test.mts
# 期望末行 ROUNDTRIP_PASS（setting.get + listSessions 往返）
```

## 八面状态

| 面 | 状态 |
|---|---|
| setting（get/update/updateDataBaseDir） | ✅ 落 %APPDATA%\Juscite\config\mock\setting.json |
| sessions-index / listSessions / createSession / readSession* | ✅ 3 条合成会话（agentService+sessionService 双注册） |
| snapshot+delta 流 | ⏳ Event 通道已占位（静默），迭代期按 UI 报错补真帧 |
| sendText 命令 | ⏳ 待迭代（V4 CommandEnvelope 通道） |
| resolveInteraction | ⏳ 待迭代 |
| readTree / attachmentPut | ⏳ 待迭代（所属 channel 按 UI 报错定位） |
| terminal / git | ✅ 空 stub（Proxy 静默） |
| /api/server-info | ✅ 合成 workspace |

## 红线

仅合成数据；setting 落 Juscite 隔离目录（不碰 %APPDATA%\JusBench）；不读任何真实案件材料。
