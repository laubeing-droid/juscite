// 【功能 #35 尾巴②】Flow Studio/运行看板面板（RE-35 §2 D/E/G 面 UI 消费；桥 RPC=flow* 族已注册）。
// 三区：运行看板（状态徽章/事件流/链校验/AI-run 一等记录/待审关卡决断——乐观锁冲突回显不自动重放）；
// 流程库（Studio 双来源草稿/发布/内置只读、节点普查、导入导出、编译诊断）；发起面（草稿只可试跑）。
// 数据经 zcodeAgentService 的 flow* 可选方法（桥 RPC 转发）；文案全部自写（表达隔离）。
// agent 节点在正式运行/试跑中打真模型轮（尾巴①接线）——面板如实展示 AI-run 的模型钉定，不代判。
import { useCallback, useEffect, useState } from "react";
import { useServices } from "../ui-kit.js";
import {
  aiRunRowView, canStartDefinition, conflictCurrentVersionOf, defBadgeOf, defNodeCensus, defReadonlyOf,
  eventLevelBadge, runBadgeOf, summarizeRunFace,
} from "../kernel/flowStudioModel.js";

interface DefMeta { id: string; source: string; status: string; version: number; title: string; updatedAt: string; publishedHash?: string }
interface RunRow { id: string; definitionId: string; status: string; ref: string | null; actor: string | null; dryRun: boolean; errorCode: string | null; createdAt: string; finishedAt: string | null }
interface RunEvent { seq: number; kind: string; nodeId: string | null; level: string; payload: Record<string, unknown>; createdAt: string }
interface AiRunRow { id: string; nodeId: string; modelCode: string; promptVersion: string; riskLevel: string | null; riskScore: number | null; findingsCount: number | null; findings: Array<{ clause?: string | null; level?: string | null; description?: string | null; advice?: string | null }> | null; createdAt: string }
interface ArtifactRow { id: string; nodeId: string; type: string; payloadDigest: string; citeReceipt: { receiptId?: string; mode?: string }; createdAt: string }
interface RunFace { run: { id: string; status: string; actor: string | null; ref: string | null; dryRun: boolean; error: { code: string; message: string } | null; waiting: { kind?: string; nodeId?: string; gateNodeId?: string } | null }; events: RunEvent[]; aiRuns: AiRunRow[]; artifacts: ArtifactRow[]; chain: { verified: boolean; length?: number; reason?: string } }
interface GateNodeFace { node: { id: string; status: string; lockVersion: number; assigneeUser: string | null; payload: Record<string, unknown> }; events: Array<{ eventType: string; action: string | null; actorUser: string; reason: string | null; fromVersion: number; toVersion: number }> }

type Svc = {
  flowDefList?: () => Promise<{ rows: DefMeta[] }>;
  flowDefGet?: (p: { id: string }) => Promise<{ meta: DefMeta; definition: { nodes?: Array<{ type: string; title?: string }>; groups?: Array<{ nodeIds: string[] }> }; layout: unknown }>;
  flowDraftPublish?: (p: { id: string }) => Promise<DefMeta>;
  flowDefCompile?: (p: { definition: unknown }) => Promise<{ ok: boolean; diagnostics: Array<{ path: string; message: string }> }>;
  flowBundleExport?: (p: { id: string }) => Promise<{ format: string; version: number; definition: unknown; layout: unknown }>;
  flowBundleImport?: (p: { bundle: unknown; overwrite?: boolean }) => Promise<{ imported: string; overwrite: boolean }>;
  flowRunList?: (p?: { limit?: number }) => Promise<{ rows: RunRow[] }>;
  flowRunGet?: (p: { id: string }) => Promise<RunFace>;
  flowRunStart?: (p: { definitionId: string; input: unknown; testRun?: boolean; actor?: string; ref?: string }) => Promise<{ runId: string; status: string; artifacts?: unknown[] }>;
  flowRunResume?: (p: { id: string; actor?: string }) => Promise<{ runId: string; status: string }>;
  flowRunPause?: (p: { id: string }) => Promise<{ ok: boolean }>;
  flowRunCancel?: (p: { id: string; reason?: string }) => Promise<{ ok: boolean }>;
  flowGateGetNode?: (p: { id: string }) => Promise<GateNodeFace>;
  flowGateProcess?: (p: { id: string; actor: string; action: "approve" | "reject"; comment?: string; expectedVersion: number }) => Promise<GateNodeFace>;
};

const TONE_CLASS: Record<string, string> = {
  ok: "rounded bg-selected px-2 py-0.5 text-ui-caption",
  warn: "rounded bg-warning/20 border border-warning px-2 py-0.5 text-ui-caption",
  err: "rounded bg-red-500/15 border border-red-500 px-2 py-0.5 text-ui-caption",
  info: "rounded bg-accent/15 border border-accent px-2 py-0.5 text-ui-caption",
  idle: "rounded border border-border px-2 py-0.5 text-ui-caption text-foreground-subtle",
};

export function FlowStudioPanel() {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as unknown as Svc;
  const [tab, setTab] = useState<"board" | "defs">("board");
  const [note, setNote] = useState("");
  const [errorNote, setErrorNote] = useState("");
  const [busy, setBusy] = useState(false);

  const run = useCallback(async (fn: () => Promise<string>) => {
    setErrorNote("");
    setNote("");
    try { setNote(await fn()); } catch (e) { setErrorNote(e instanceof Error ? e.message : String(e)); }
  }, []);

  // ── 运行看板态 ──
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [runFace, setRunFace] = useState<RunFace | null>(null);
  const [gateFace, setGateFace] = useState<GateNodeFace | null>(null);
  const [gateComment, setGateComment] = useState("");
  const [conflictNote, setConflictNote] = useState("");
  const refreshRuns = useCallback(async () => {
    const r = await svc.flowRunList?.({ limit: 50 }).catch(() => null);
    setRuns(r?.rows ?? []);
  }, [svc]);
  const openRun = useCallback(async (id: string) => {
    setConflictNote("");
    const face = await svc.flowRunGet?.({ id }).catch((e: Error) => { setErrorNote(e.message); return null; });
    if (!face) return;
    setRunFace(face);
    const gateNodeId = face.run.waiting?.gateNodeId ?? null;
    setGateFace(gateNodeId ? await svc.flowGateGetNode?.({ id: gateNodeId }).catch(() => null) ?? null : null);
  }, [svc]);

  useEffect(() => {
    let alive = true;
    svc.flowRunList?.({ limit: 50 }).then((r) => { if (alive) setRuns(r.rows ?? []); }).catch(() => {});
    return () => { alive = false; };
  }, [svc]);

  // ── 流程库态 ──
  const [defs, setDefs] = useState<DefMeta[]>([]);
  const [defMeta, setDefMeta] = useState<DefMeta | null>(null);
  const [defCensus, setDefCensus] = useState<ReturnType<typeof defNodeCensus> | null>(null);
  const [importText, setImportText] = useState("");
  const refreshDefs = useCallback(async () => {
    const r = await svc.flowDefList?.().catch(() => null);
    setDefs(r?.rows ?? []);
  }, [svc]);
  useEffect(() => {
    let alive = true;
    svc.flowDefList?.().then((r) => { if (alive) setDefs(r.rows ?? []); }).catch(() => {});
    return () => { alive = false; };
  }, [svc]);
  const openDef = useCallback(async (id: string) => {
    const face = await svc.flowDefGet?.({ id }).catch((e: Error) => { setErrorNote(e.message); return null; });
    if (!face) return;
    setDefMeta(face.meta);
    setDefCensus(defNodeCensus(face.definition));
  }, [svc]);

  // ── 发起态 ──
  const [startDefId, setStartDefId] = useState("");
  const [startInput, setStartInput] = useState("{\n  \"lineId\": \"line.demo\"\n}");
  const selectedDef = defs.find((d) => d.id === startDefId) ?? null;
  const startGate = selectedDef ? canStartDefinition(selectedDef.source, selectedDef.status) : null;

  const badge = (b: { label: string; tone: string }) => <span className={TONE_CLASS[b.tone] ?? TONE_CLASS.idle}>{b.label}</span>;

  return (
    <section data-testid="flow-studio-panel" className="rounded-workspace-panel border border-border bg-header p-4">
      <header className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-ui-lg font-medium">流程工作台（Flow Studio · 运行看板）</h2>
        <div className="ml-auto flex gap-1">
          <button type="button" data-testid="flow-tab-board" onClick={() => setTab("board")}
            className={tab === "board" ? "rounded bg-selected px-2 py-1 text-ui-caption" : "rounded border border-border px-2 py-1 text-ui-caption"}>运行看板</button>
          <button type="button" data-testid="flow-tab-defs" onClick={() => setTab("defs")}
            className={tab === "defs" ? "rounded bg-selected px-2 py-1 text-ui-caption" : "rounded border border-border px-2 py-1 text-ui-caption"}>流程库</button>
        </div>
      </header>
      <p className="mb-3 text-ui-caption text-foreground-subtle">
        运行看板=已发起流程的守门与留痕面（事件流带本地信任锚校验；关卡决断走乐观锁，冲突只回显当前版本，绝不自动重放旧决定）；
        流程库=草稿/发布/内置只读双来源。agent 节点打真模型轮，模型与提示词版本逐次钉定落账。
      </p>
      {note ? <p data-testid="flow-note" className="mb-2 text-ui-sm text-foreground">{note}</p> : null}
      {errorNote ? <p data-testid="flow-error" className="mb-2 text-ui-sm text-red-500">{errorNote}</p> : null}

      {tab === "board" ? (
        <div className="flex flex-col gap-4">
          {/* 发起面 */}
          <div className="rounded border border-border p-3" data-testid="flow-start-box">
            <h3 className="mb-2 text-ui-sm font-medium">发起一次流程运行</h3>
            <div className="flex flex-wrap items-center gap-2">
              <select data-testid="flow-start-def" value={startDefId} onChange={(e) => setStartDefId(e.target.value)}
                className="rounded border border-border bg-background px-2 py-1 text-ui-sm">
                <option value="">选择流程定义…</option>
                {defs.map((d) => <option key={d.id} value={d.id}>{d.title}（{defBadgeOf(d.source, d.status).label}）</option>)}
              </select>
              <button type="button" data-testid="flow-start-btn" disabled={!selectedDef || busy}
                className="rounded border border-border px-2 py-1 text-ui-sm disabled:opacity-50"
                onClick={() => run(async () => {
                  setBusy(true);
                  try {
                    if (!svc.flowRunStart || !selectedDef) throw new Error("桥面未提供 flowRunStart 通道");
                    let input: unknown;
                    try { input = JSON.parse(startInput); } catch { throw new Error("输入不是合法 JSON 对象"); }
                    const gateInfo = canStartDefinition(selectedDef.source, selectedDef.status);
                    const r = await svc.flowRunStart({ definitionId: selectedDef.id, input, testRun: gateInfo.testRunOnly, ref: "studio-panel" });
                    await refreshRuns();
                    await openRun(r.runId);
                    return `已发起 ${r.runId}（${r.status}）${gateInfo.testRunOnly ? "——草稿试跑档" : ""}`;
                  } finally { setBusy(false); }
                })}>发起</button>
              {startGate ? <span className="text-ui-caption text-foreground-subtle">{startGate.note}</span> : null}
            </div>
            <textarea data-testid="flow-start-input" value={startInput} onChange={(e) => setStartInput(e.target.value)}
              className="mt-2 h-20 w-full rounded border border-border bg-background p-2 font-mono text-ui-caption" spellCheck={false} />
            <p className="mt-1 text-ui-caption text-foreground-subtle">运行含 agent 节点时将打真模型轮（产出受 outputSchema 硬校验，未过按诊断回喂重提）。</p>
          </div>

          {/* 运行列表 */}
          <div className="rounded border border-border p-3">
            <div className="mb-2 flex items-center gap-2">
              <h3 className="text-ui-sm font-medium">运行记录</h3>
              <button type="button" data-testid="flow-refresh-runs" className="rounded border border-border px-2 py-0.5 text-ui-caption"
                onClick={() => run(async () => { await refreshRuns(); return `已刷新（${runs.length || ""} 条）`; })}>刷新</button>
            </div>
            <table className="w-full text-ui-caption">
              <thead><tr className="text-foreground-subtle"><th className="text-left">运行</th><th className="text-left">状态</th><th className="text-left">定义</th><th className="text-left">发起人</th><th className="text-left">时间</th></tr></thead>
              <tbody data-testid="flow-run-rows">
                {runs.map((r) => (
                  <tr key={r.id} className="cursor-pointer border-t border-border" data-testid={`flow-run-row-${r.id}`}
                    onClick={() => void openRun(r.id)}>
                    <td className="py-1 font-mono">{r.id}{r.dryRun ? "（dry）" : ""}{r.errorCode ? <span className="text-red-500"> {r.errorCode}</span> : null}</td>
                    <td className="py-1">{badge(runBadgeOf(r.status))}</td>
                    <td className="py-1 font-mono">{r.definitionId}</td>
                    <td className="py-1">{r.actor ?? "—"}</td>
                    <td className="py-1">{r.createdAt}</td>
                  </tr>
                ))}
                {!runs.length ? <tr><td colSpan={5} className="py-2 text-foreground-subtle">暂无运行记录（上方发起一次即出现）</td></tr> : null}
              </tbody>
            </table>
          </div>

          {/* 运行详情 */}
          {runFace ? (
            <div className="rounded border border-border p-3" data-testid="flow-run-detail">
              {(() => {
                const s = summarizeRunFace(runFace);
                return (
                  <>
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <h3 className="font-mono text-ui-sm">{runFace.run.id}</h3>
                      {badge(s.status)}
                      <span className={s.chainOk ? TONE_CLASS.ok : TONE_CLASS.err} data-testid="flow-chain-badge">{s.chainOk ? `链校验通过（${runFace.chain.length ?? "?"} 事件）` : "链校验未过"}</span>
                      <span className="text-ui-caption text-foreground-subtle">心跳 {s.heartbeats} · AI-run {s.aiRunCount} · 产物 {s.artifactCount}{s.dryRun ? " · dry-run" : ""}</span>
                      <button type="button" className="ml-auto rounded border border-border px-2 py-0.5 text-ui-caption" onClick={() => void openRun(runFace.run.id)}>刷新详情</button>
                      <button type="button" data-testid="flow-run-pause" className="rounded border border-border px-2 py-0.5 text-ui-caption"
                        onClick={() => run(async () => { await svc.flowRunPause?.({ id: runFace.run.id }); await refreshRuns(); return "已请求暂停（下一节点/项界生效）"; })}>暂停</button>
                      <button type="button" data-testid="flow-run-resume" className="rounded border border-border px-2 py-0.5 text-ui-caption"
                        onClick={() => run(async () => { const r = await svc.flowRunResume?.({ id: runFace.run.id }); await refreshRuns(); await openRun(runFace.run.id); return `恢复结果：${r?.status ?? "通道不可用"}`; })}>恢复</button>
                      <button type="button" data-testid="flow-run-cancel" className="rounded border border-border px-2 py-0.5 text-ui-caption"
                        onClick={() => run(async () => { await svc.flowRunCancel?.({ id: runFace.run.id, reason: "面板取消" }); await refreshRuns(); return "已取消"; })}>取消</button>
                    </div>
                    {!s.chainOk ? <p className="mb-2 text-ui-caption text-red-500">{s.chainNote}</p> : null}

                    {/* 待审关卡决断面 */}
                    {s.waitingGate && gateFace ? (
                      <div className="mb-3 rounded border border-warning/60 bg-warning/10 p-2" data-testid="flow-gate-box">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="text-ui-sm font-medium">待审关卡（{gateFace.node.id} · v{gateFace.node.lockVersion}）</h4>
                          <span className="text-ui-caption text-foreground-subtle">{gateFace.node.status}</span>
                        </div>
                        <p className="mt-1 text-ui-caption text-foreground-subtle">决断携带乐观锁版本；版本冲突只回显服务端当前版本，由人刷新后重下决定（不自动重放）。</p>
                        {conflictNote ? <p data-testid="flow-gate-conflict" className="mt-1 text-ui-caption text-warning">{conflictNote}</p> : null}
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <input data-testid="flow-gate-comment" value={gateComment} onChange={(e) => setGateComment(e.target.value)}
                            placeholder="审批意见（随审计事件留痕）" className="min-w-64 rounded border border-border bg-background px-2 py-1 text-ui-caption" />
                          <button type="button" data-testid="flow-gate-approve" className="rounded bg-selected px-2 py-1 text-ui-caption"
                            onClick={() => run(async () => {
                              if (!svc.flowGateProcess) throw new Error("桥面未提供 flowGateProcess 通道");
                              try {
                                await svc.flowGateProcess({ id: gateFace.node.id, actor: "律师", action: "approve", comment: gateComment || undefined, expectedVersion: gateFace.node.lockVersion });
                              } catch (e) {
                                const msg = e instanceof Error ? e.message : String(e);
                                const cur = conflictCurrentVersionOf(msg);
                                setConflictNote(cur !== null ? `版本冲突：服务端当前 v${cur}，请刷新后重新决定（原文：${msg}）` : msg);
                                throw e;
                              }
                              setConflictNote("");
                              const r = await svc.flowRunResume?.({ id: runFace.run.id });
                              await refreshRuns();
                              await openRun(runFace.run.id);
                              return `已批准并恢复运行（${r?.status ?? "?"}）`;
                            })}>批准并恢复</button>
                          <button type="button" data-testid="flow-gate-reject" className="rounded border border-red-500 px-2 py-1 text-ui-caption text-red-500"
                            onClick={() => run(async () => {
                              if (!svc.flowGateProcess) throw new Error("桥面未提供 flowGateProcess 通道");
                              try {
                                await svc.flowGateProcess({ id: gateFace.node.id, actor: "律师", action: "reject", comment: gateComment || "驳回", expectedVersion: gateFace.node.lockVersion });
                              } catch (e) {
                                const msg = e instanceof Error ? e.message : String(e);
                                const cur = conflictCurrentVersionOf(msg);
                                setConflictNote(cur !== null ? `版本冲突：服务端当前 v${cur}，请刷新后重新决定（原文：${msg}）` : msg);
                                throw e;
                              }
                              await refreshRuns();
                              return "已驳回（关卡拒绝=运行判失败，无旁路）";
                            })}>驳回</button>
                          <button type="button" data-testid="flow-gate-refresh" className="rounded border border-border px-2 py-1 text-ui-caption"
                            onClick={() => run(async () => { await openRun(runFace.run.id); return "已刷新（重新读取当前版本）"; })}>刷新版本</button>
                        </div>
                      </div>
                    ) : null}

                    {/* AI-run 一等记录（G1-G4） */}
                    <div className="mb-3">
                      <h4 className="mb-1 text-ui-sm font-medium">AI 运行记录（模型与提示词版本钉定）</h4>
                      {runFace.aiRuns.length ? (
                        <ul className="flex flex-col gap-1" data-testid="flow-airun-rows">
                          {runFace.aiRuns.map((a) => {
                            const v = aiRunRowView(a);
                            return (
                              <li key={a.id} className="rounded border border-border p-2 text-ui-caption">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="font-mono">{a.nodeId}</span>
                                  <span className="text-foreground-subtle">{v.modelPinned}</span>
                                  <span>{v.riskLine}</span>
                                </div>
                                {v.findingsQuad.map((f, i) => (
                                  <div key={i} className="mt-1 text-foreground-subtle">发现{i + 1}：{f.clause || "—"}｜{f.level || "—"}｜{f.description || "—"}｜建议：{f.advice || "—"}</div>
                                ))}
                              </li>
                            );
                          })}
                        </ul>
                      ) : <p className="text-ui-caption text-foreground-subtle">本运行无 AI-run 记录（纯确定性节点或尚未到达 agent 节点）。</p>}
                    </div>

                    {/* 产物链 */}
                    <div className="mb-3">
                      <h4 className="mb-1 text-ui-sm font-medium">产物</h4>
                      {runFace.artifacts.length ? (
                        <ul data-testid="flow-artifact-rows" className="flex flex-col gap-1 text-ui-caption">
                          {runFace.artifacts.map((a) => (
                            <li key={a.id} className="rounded border border-border p-2 font-mono">
                              {a.nodeId} · {a.type} · digest {a.payloadDigest.slice(0, 16)}… · 回执 {a.citeReceipt.receiptId ?? "—"}（{a.citeReceipt.mode ?? "—"}）
                            </li>
                          ))}
                        </ul>
                      ) : <p className="text-ui-caption text-foreground-subtle">无产物（运行未到发布节点或无 output 声明）。</p>}
                    </div>

                    {/* 事件流 */}
                    <div>
                      <h4 className="mb-1 text-ui-sm font-medium">事件流（只追加，带信任锚链）</h4>
                      <ul data-testid="flow-event-rows" className="max-h-64 overflow-y-auto rounded border border-border p-2 font-mono text-ui-caption">
                        {runFace.events.map((e) => (
                          <li key={e.seq} className="flex gap-2 border-b border-border/50 py-0.5 last:border-0">
                            <span className="text-foreground-subtle">#{e.seq}</span>
                            {badge(eventLevelBadge(e.level))}
                            <span>{e.kind}{e.nodeId ? ` @${e.nodeId}` : ""}</span>
                            <span className="truncate text-foreground-subtle">{JSON.stringify(e.payload).slice(0, 120)}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </>
                );
              })()}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {/* 流程库列表 */}
          <div className="rounded border border-border p-3">
            <div className="mb-2 flex items-center gap-2">
              <h3 className="text-ui-sm font-medium">流程定义（双来源）</h3>
              <button type="button" data-testid="flow-refresh-defs" className="rounded border border-border px-2 py-0.5 text-ui-caption"
                onClick={() => run(async () => { await refreshDefs(); return "定义列表已刷新"; })}>刷新</button>
            </div>
            <table className="w-full text-ui-caption">
              <thead><tr className="text-foreground-subtle"><th className="text-left">标题</th><th className="text-left">来源/状态</th><th className="text-left">版本</th><th className="text-left">更新时间</th></tr></thead>
              <tbody data-testid="flow-def-rows">
                {defs.map((d) => (
                  <tr key={d.id} className="cursor-pointer border-t border-border" data-testid={`flow-def-row-${d.id}`} onClick={() => void openDef(d.id)}>
                    <td className="py-1">{d.title}<span className="ml-2 font-mono text-foreground-subtle">{d.id}</span></td>
                    <td className="py-1">{badge(defBadgeOf(d.source, d.status))}</td>
                    <td className="py-1">v{d.version}</td>
                    <td className="py-1">{d.updatedAt}</td>
                  </tr>
                ))}
                {!defs.length ? <tr><td colSpan={4} className="py-2 text-foreground-subtle">暂无定义（内置流程应在服务启动时种子注入）</td></tr> : null}
              </tbody>
            </table>
          </div>

          {/* 定义详情与操作 */}
          {defMeta ? (
            <div className="rounded border border-border p-3" data-testid="flow-def-detail">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <h3 className="text-ui-sm font-medium">{defMeta.title}</h3>
                {badge(defBadgeOf(defMeta.source, defMeta.status))}
                <span className="text-ui-caption text-foreground-subtle">v{defMeta.version}{defMeta.publishedHash ? ` · 发布哈希 ${defMeta.publishedHash.slice(0, 12)}…` : ""}</span>
                {defReadonlyOf(defMeta.source) ? <span className="text-ui-caption text-foreground-subtle">内置只读——编辑请另存草稿</span> : null}
              </div>
              {defCensus ? (
                <p className="text-ui-caption text-foreground-subtle">
                  节点普查：{defCensus.total} 个（{defCensus.byType.map((t) => `${t.type}×${t.count}`).join("、")}）· {defCensus.groupsNote}
                </p>
              ) : null}
              <div className="mt-2 flex flex-wrap gap-2">
                <button type="button" data-testid="flow-def-publish" disabled={defReadonlyOf(defMeta.source) || defMeta.status === "published"}
                  className="rounded border border-border px-2 py-1 text-ui-caption disabled:opacity-50"
                  onClick={() => run(async () => {
                    const r = await svc.flowDraftPublish?.({ id: defMeta.id });
                    await refreshDefs();
                    await openDef(defMeta.id);
                    return `已发布：${r?.publishedHash ?? "?"}（发布前编译校验通过）`;
                  })}>发布（编译校验前置）</button>
                <button type="button" data-testid="flow-def-export" className="rounded border border-border px-2 py-1 text-ui-caption"
                  onClick={() => run(async () => {
                    const b = await svc.flowBundleExport?.({ id: defMeta.id });
                    if (!b) throw new Error("导出通道不可用");
                    const blob = new Blob([JSON.stringify(b, null, 2)], { type: "application/json" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `${defMeta.id}.studio.json`;
                    a.click();
                    setTimeout(() => URL.revokeObjectURL(url), 4000);
                    return `已导出 ${defMeta.id}.studio.json（定义与布局分离打包）`;
                  })}>导出</button>
              </div>
            </div>
          ) : null}

          {/* 导入面 */}
          <div className="rounded border border-border p-3" data-testid="flow-import-box">
            <h3 className="mb-2 text-ui-sm font-medium">导入流程包（本地草稿，不建内置商店）</h3>
            <p className="mb-2 text-ui-caption text-foreground-subtle">粘贴导出的 JSON 包；同名定义已存在时须勾选覆盖（覆盖只作用于本地草稿，内置只读不可覆盖）。</p>
            <textarea data-testid="flow-import-text" value={importText} onChange={(e) => setImportText(e.target.value)}
              className="h-24 w-full rounded border border-border bg-background p-2 font-mono text-ui-caption" spellCheck={false} />
            <div className="mt-2 flex gap-2">
              <button type="button" data-testid="flow-import-btn" className="rounded border border-border px-2 py-1 text-ui-caption"
                onClick={() => run(async () => {
                  if (!svc.flowBundleImport) throw new Error("桥面未提供 flowBundleImport 通道");
                  let bundle: unknown;
                  try { bundle = JSON.parse(importText); } catch { throw new Error("粘贴内容不是合法 JSON"); }
                  const r = await svc.flowBundleImport({ bundle });
                  await refreshDefs();
                  return `已导入为草稿：${r.imported}`;
                })}>导入为草稿</button>
              <button type="button" data-testid="flow-import-overwrite-btn" className="rounded border border-border px-2 py-1 text-ui-caption"
                onClick={() => run(async () => {
                  if (!svc.flowBundleImport) throw new Error("桥面未提供 flowBundleImport 通道");
                  let bundle: unknown;
                  try { bundle = JSON.parse(importText); } catch { throw new Error("粘贴内容不是合法 JSON"); }
                  const r = await svc.flowBundleImport({ bundle, overwrite: true });
                  await refreshDefs();
                  return `已覆盖导入：${r.imported}`;
                })}>覆盖导入</button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
