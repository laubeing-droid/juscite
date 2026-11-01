// Juscite 法律工作台（M3）：八法律面入口页——材料/审查/核验/期限/计算器/文书/企查查空态/隐身。
// 数据经 /api/legal（桥，合成数据）；隐身开关经 ISettingService（桥已消费 stealthMode）。
// #25 文档对比（施工单-03 任务四）：双栏对比+变更清单面板挂本页（材料通道走桥 RPC）。
import { useCallback, useEffect, useState } from "react";
import type { IServiceAccessor } from "@zcode/services";
import { Button } from "../ui-kit.js";
import { CaseGraphPanel } from "./CaseGraphPanel.js";
import { CaseBoardPanel } from "./CaseBoardPanel.js";
import { CaseTimelinePanel } from "./CaseTimelinePanel.js";
import { DocCompare } from "./DocCompare.js";
import { RedlinePanel } from "./RedlinePanel.js";
import { DocumentDraftingPanel } from "./DocumentDrafting.js";
// 【步骤4·#5 冲突查重】工作台快检弹窗（A2 工作台入口，轻量单主体快查）。
import { ConflictQuickDialog } from "./ConflictQuickDialog.js";
// 【#13 法条手册】内置法条包三区面板（RE-13 §3.2 UI 结构；数据经 /api/legal/laws* 桥端点族）。
import { LawBookPanel } from "./LawBookPanel.js";
// 【#14 引证核验】核验（法源）面真数据面（RE-14 §3.4；数据经 /api/verify/* 桥端点族）。
import { CitationVerifyPanel } from "./CitationVerifyPanel.js";
// 【功能 #6 材料上传解析】案件材料库面板（RE-6 §3 UI；数据经 /api/cases/materials* 桥端点族）。
import { CaseMaterialsPanel } from "./CaseMaterialsPanel.js";
// 【功能 #42 电子数据取证】取证五分区面板（RE-42 §3.3 UI；数据经 /api/edisc/* 桥端点族）。
import { EdiscPanel } from "./EdiscPanel.js";
// 【功能 #35 尾巴②】Flow Studio/运行看板面板（RE-35 §2 D/E/G 面 UI 消费；数据经 flow* 桥 RPC 族）。
import { FlowStudioPanel } from "./FlowStudioPanel.js";
import { Scale, ScanSearch } from "lucide-react";

interface LegalData {
  materials: Array<{ id: string; name: string; status: string }>;
  review: Array<{ aspect: string; finding: string; severity: string }>;
  citations: Array<{ source: string; valid: string; note: string }>;
  schedule: Array<{ id: string; title: string; due: string; kind: string }>;
  calc: Array<{ name: string; input: string; result: string }>;
  documents: Array<{ id: string; title: string; status: string }>;
}

const SECTIONS: Array<{ key: keyof LegalData | "qcc" | "stealth"; title: string }> = [
  { key: "materials", title: "材料库" },
  { key: "review", title: "审查（五方面）" },
  { key: "citations", title: "核验（法源）" },
  { key: "schedule", title: "期限" },
  { key: "calc", title: "计算器" },
  { key: "documents", title: "文书" },
  { key: "qcc", title: "企查查 / 天眼查" },
  { key: "stealth", title: "隐身模式" },
];

export function LegalWorkbench({ services, workspacePath, onOpenConflictPrecheck }: { services: IServiceAccessor; workspacePath?: string; onOpenConflictPrecheck?: () => void }) {
  const [data, setData] = useState<LegalData | null>(null);
  const [quickOpen, setQuickOpen] = useState(false); // #5 冲突快检弹窗开关
  const [stealth, setStealth] = useState(false);
  // 【#14 G9】手册条文页「核验此条」→单条核验预填（token 变化触发，不自动提交）。
  const [citationPrefill, setCitationPrefill] = useState<{ text: string; token: number }>({ text: "", token: 0 });
  const prefillCitation = useCallback((text: string) => setCitationPrefill({ text, token: Date.now() }), []);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/legal", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: LegalData) => { if (alive) setData(d); })
      .catch((e: Error) => { if (alive) setError(e.message); });
    services
      .settingService
      .get()
      // stealthMode 为 Juscite additive 字段（AppSettings 冻结 schema 外），运行时宽容、类型层断言桥接
      .then((s: unknown) => {
        const enabled = Boolean((s as { stealthMode?: { enabled?: boolean } })?.stealthMode?.enabled);
        if (alive) setStealth(enabled);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, [services]);

  const toggleStealth = useCallback(async () => {
    const next = !stealth;
    setStealth(next);
    try {
      await services.settingService.update({ stealthMode: { enabled: next } } as unknown as Parameters<typeof services.settingService.update>[0]);
    } catch (e) {
      setStealth(!next);
      setError(String(e));
    }
  }, [services, stealth]);

  return (
    <div className="flex flex-col gap-6" data-testid="legal-workbench">
      <header className="flex items-center gap-3">
        <Scale className="size-6" />
        <div className="min-w-0 flex-1">
          <h1 className="text-ui-xl font-semibold">法律工作台</h1>
          <p className="text-ui-caption text-foreground-subtle">
            材料 · 审查 · 核验 · 期限 · 计算 · 文书（合成演示数据，真源接线随 M2 尾巴）
          </p>
        </div>
        {/* 【#5 冲突快检】收案动线：先预检再建案（顶栏次级钮，A2 等量落位） */}
        <Button variant="outline" size="sm" onClick={() => setQuickOpen(true)} data-testid="conflict-quick-open">
          <ScanSearch className="size-4" /> 冲突快检
        </Button>
      </header>
      {quickOpen ? (
        <ConflictQuickDialog
          onClose={() => setQuickOpen(false)}
          onOpenFull={() => { setQuickOpen(false); onOpenConflictPrecheck?.(); }}
        />
      ) : null}
      {error ? <p className="text-ui-sm text-red-500">桥连接失败：{error}（请确认桥在 3030 运行）</p> : null}

      <section data-testid="legal-materials" className="rounded-workspace-panel border border-border bg-header p-4">
        <h2 className="mb-2 text-ui-lg font-medium">材料库</h2>
        <ul className="text-ui-base">
          {(data?.materials ?? []).map((m) => (
            <li key={m.id}>📄 {m.name} — <span className="text-foreground-subtle">{m.status}</span></li>
          ))}
          {!data?.materials?.length ? <li className="text-foreground-subtle">暂无材料</li> : null}
        </ul>
      </section>

      <section data-testid="legal-review" className="rounded-workspace-panel border border-border bg-header p-4">
        <h2 className="mb-2 text-ui-lg font-medium">审查（五方面）</h2>
        <ul className="text-ui-base">
          {(data?.review ?? []).map((r, i) => (
            <li key={i}>【{r.severity}】{r.aspect}：{r.finding}</li>
          ))}
          {!data?.review?.length ? <li className="text-foreground-subtle">暂无审查结论</li> : null}
        </ul>
      </section>

      <section data-testid="legal-citations" className="rounded-workspace-panel border border-border bg-header p-4">
        <h2 className="mb-2 text-ui-lg font-medium">核验（法源）</h2>
        {/* 功能 #14（RE-14 §3.4）：M3 合成演示替换为真数据面（/api/verify/*）；G3 徽章三态映射在面板内。 */}
        <CitationVerifyPanel prefill={citationPrefill} />
      </section>

      <section data-testid="legal-schedule" className="rounded-workspace-panel border border-border bg-header p-4">
        <h2 className="mb-2 text-ui-lg font-medium">期限</h2>
        <ul className="text-ui-base">
          {(data?.schedule ?? []).map((s) => (
            <li key={s.id}>⏰ [{s.kind}] {s.title} — <span className="font-medium">{s.due}</span></li>
          ))}
          {!data?.schedule?.length ? <li className="text-foreground-subtle">暂无期限条目</li> : null}
        </ul>
      </section>

      <section data-testid="legal-calc" className="rounded-workspace-panel border border-border bg-header p-4">
        <h2 className="mb-2 text-ui-lg font-medium">计算器</h2>
        <ul className="text-ui-base">
          {(data?.calc ?? []).map((c, i) => (
            <li key={i}>🧮 {c.name}：{c.input} → <span className="font-medium">{c.result}</span></li>
          ))}
          {!data?.calc?.length ? <li className="text-foreground-subtle">暂无试算</li> : null}
        </ul>
      </section>

      {/* 功能 #10 模板文书起草（RE-10）：模板库/材料字段/生成/预览导出/历史/五阶段浮窗（占位卡替换） */}
      <DocumentDraftingPanel workspacePath={workspacePath} />

      <section data-testid="legal-qcc" className="rounded-workspace-panel border border-border bg-header p-4">
        <h2 className="mb-2 text-ui-lg font-medium">企查查 / 天眼查</h2>
        <p className="text-ui-base">工商信息控制台（空态）：请登录企查查/天眼查并获取 API Key 填入设置后启用。</p>
        <p className="text-ui-caption text-foreground-subtle">未配置 Key 前不展示任何企业数据（fail-closed，不伪造）。</p>
      </section>

      {/* 功能 #11 Word 红线改稿（施工单-03 任务一）：AI 出稿→逐条终审→定稿落盘 */}
      <RedlinePanel workspacePath={workspacePath} />

      {/* 功能 #25 文档对比（施工单-03 任务四）：双栏对比+变更清单 */}
      <DocCompare workspacePath={workspacePath} />

      {/* 功能 #13 法条手册（RE-13）：主壳内嵌面板——目录树/阅读区/锚点目录三区+收藏+包管理面 */}
      <LawBookPanel onVerifyCitation={prefillCitation} />

      {/* 功能 #3 案件看板（步骤4·RE-3）：日程日历/提醒/出行/案件节点看板面（MatterLite 过渡数据面） */}
      <CaseBoardPanel />

      {/* 功能 #6 材料上传解析（RE-6 §3 UI）：案件材料库面板——上传/状态/版本/检索/空态（无删除入口） */}
      <CaseMaterialsPanel />

      {/* 功能 #4 案件时间线（步骤4·RE-4）：办案时间轴卡片节（竖排 rail+抽取/编辑流，双通道数据面） */}
      <CaseTimelinePanel workspacePath={workspacePath} />

      {/* 功能 #19 轻量知识图谱（步骤4·RE-19）：案件人物/证据关系一屏（单图单轨） */}
      <CaseGraphPanel workspacePath={workspacePath} />

      {/* 功能 #42 电子数据取证（RE-42 §3.3）：源列表/行浏览/归类看板/页卡阅读/审查工作台五分区 */}
      <EdiscPanel />

      {/* 功能 #35 尾巴② Flow Studio（RE-35）：流程库双来源+运行看板+关卡决断面（真模型 agent 轮的守门与留痕面） */}
      <FlowStudioPanel />

      <section data-testid="legal-stealth" className="rounded-workspace-panel border border-border bg-header p-4">
        <h2 className="mb-2 text-ui-lg font-medium">隐身模式</h2>
        <div className="flex items-center gap-3">
          <button
            type="button"
            data-testid="legal-stealth-toggle"
            aria-pressed={stealth}
            onClick={() => void toggleStealth()}
            className={stealth ? "rounded bg-selected px-3 py-1 text-ui-base" : "rounded border border-border px-3 py-1 text-ui-base"}
          >
            {stealth ? "已开启（点击关闭）" : "已关闭（点击开启）"}
          </button>
          <span className="text-ui-caption text-foreground-subtle">
            开启=对话出站全断（模型拒绝并提示）；五通道完整阻断（内嵌浏览器/更新/远程/语音）随 M3 尾实现
          </span>
        </div>
      </section>
    </div>
  );
}
