// 【施工波二轮·可视化B轨 UI 件】对抗视图入口节（功能 #19 深化，挂案件关系图面板内）。
// 语义 JSON 是模型/律师侧产出（判断带三标、三处结论留空等律师回填），面板不生产语义：
// 本节=粘贴导入 → 桥面判据守卫校验（vizbConfrontationCheck）→ 确定性渲染（vizbConfrontationRender）
// → 产物预览（三栏对抗 SVG + 要件摘要表）与下载（SVG 图/17 列分析表）。
// 对抗图为内部推演件：产品文案随交付面携带「不对法院出示」限制（规格 §五·出示边界）。
// 判定全在桥面 @juscite/vizb；守卫不成立即拒绝出图并具名报违例，面板不降级硬填。
// 文案全部自写（表达隔离）。
import { useCallback, useEffect, useState } from "react";
import { FileSpreadsheet, ImageDown, Swords } from "lucide-react";
import { useServices } from "../ui-kit.js";
import { sanitizeDownloadName } from "./chronicleView.js";
import { parseConfrontationSemantic, summarizeConfrontation } from "./confrontationView.js";

interface CheckResult {
  ok: boolean;
  refusal: string | null;
  schemaViolations: Array<{ path: string; msg: string }>;
  guardViolations: Array<{ group: string; code: string; msg: string }>;
  figureViolations: Array<{ group: string; code: string; msg: string }>;
}
interface Artifacts {
  svg: string;
  analysisTableXml: string;
}

const LS_KEY = "juscite.graph.confrontation.semantic";

function lsGet(): string {
  try { return window.localStorage.getItem(LS_KEY) ?? ""; } catch { return ""; }
}
function lsSet(v: string): void {
  try { window.localStorage.setItem(LS_KEY, v); } catch { /* 隐私模式等静默 */ }
}
function downloadText(content: string, filename: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export function ConfrontationSection() {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as {
    vizbConfrontationCheck?: (p: { semantic: unknown }) => Promise<CheckResult>;
    vizbConfrontationRender?: (p: { semantic: unknown }) => Promise<Artifacts>;
  };

  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [flowError, setFlowError] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [violations, setViolations] = useState<Array<{ group?: string; code?: string; msg: string }> | null>(null);
  const [artifacts, setArtifacts] = useState<Artifacts | null>(null);
  const [summary, setSummary] = useState<ReturnType<typeof summarizeConfrontation> | null>(null);

  useEffect(() => { if (open && !text) setText(lsGet()); /* 只在首次展开时回填上次成功校验的语义 */ }, [open, text]);

  const run = useCallback(() => {
    if (busy) return;
    if (!svc.vizbConfrontationCheck || !svc.vizbConfrontationRender) {
      setFlowError("桥面未提供对抗视图通道（vizbConfrontationCheck/Render 不可用），本面停用。");
      return;
    }
    const parsed = parseConfrontationSemantic(text);
    if (!parsed.ok) {
      setFlowError(parsed.error);
      return;
    }
    setBusy(true);
    setFlowError(null);
    setRefusal(null);
    setViolations(null);
    setArtifacts(null);
    setSummary(null);
    svc.vizbConfrontationCheck({ semantic: parsed.value })
      .then((ck) => {
        if (!ck.ok) {
          setRefusal(ck.refusal ?? "判据守卫不成立，拒绝出图。");
          setViolations(ck.guardViolations.length ? ck.guardViolations : ck.schemaViolations.length ? ck.schemaViolations : ck.figureViolations);
          setBusy(false);
          return;
        }
        lsSet(text); // 仅缓存通过桥面守卫的语义文本，便于下回合复用
        setSummary(summarizeConfrontation(parsed.value));
        return svc.vizbConfrontationRender!({ semantic: parsed.value }).then((arts) => {
          setArtifacts(arts);
          setBusy(false);
        });
      })
      .catch((e: unknown) => {
        setBusy(false);
        setFlowError(String((e as Error)?.message ?? e));
      });
  }, [busy, text, svc]);

  const nameBase = sanitizeDownloadName(summary?.caseTitle || "对抗视图");

  return (
    <div className="mt-3 rounded border border-border p-3" data-testid="case-graph-confrontation">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-1 text-ui-sm font-medium">
          <Swords className="size-4" /> 对抗视图（内部推演件）
        </h3>
        <button type="button" data-testid="case-graph-confrontation-toggle" aria-expanded={open}
          className="ml-auto rounded border border-border px-2 py-0.5 text-ui-caption"
          onClick={() => setOpen(!open)}>
          {open ? "收起" : "展开"}
        </button>
      </div>
      <p className="mt-1 text-ui-caption text-foreground-subtle">
        庭审对抗图为内部推演件：可含我方薄弱点与待补证，<span className="font-medium text-foreground">不对法院出示</span>；
        语义 JSON 由律师/模型侧产出后粘贴导入，本面板只做校验与确定性渲染，判断带三标、
        证明前景/决定性排序/另定性风险三处结论由律师回填，代码不代判。
      </p>
      {open ? (
        <div className="mt-2 flex flex-col gap-2">
          <textarea
            data-testid="case-graph-confrontation-input"
            className="min-h-40 rounded border border-border bg-background p-2 font-mono text-ui-caption"
            placeholder={"在此粘贴语义 JSON（schema juscite.vizb.confrontation@1，封闭 schema 校验与判据守卫在桥面）"}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex items-center gap-2">
            <button type="button" data-testid="case-graph-confrontation-check"
              className="rounded bg-selected px-3 py-1 text-ui-sm disabled:opacity-50"
              disabled={busy || !text.trim()} onClick={run}>
              {busy ? "正在出图…" : "导入并出图"}
            </button>
            {text ? (
              <button type="button" className="rounded border border-border px-2 py-1 text-ui-caption"
                onClick={() => { setText(""); lsSet(""); }}>
                清空
              </button>
            ) : null}
          </div>
          {flowError ? <p className="text-ui-caption text-red-500" data-testid="case-graph-confrontation-error">{flowError}</p> : null}

          {refusal ? (
            <div className="rounded border border-red-300 bg-red-50 p-2 text-ui-caption text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
              data-testid="case-graph-confrontation-refusal">
              <p>{refusal}</p>
              {violations?.length ? (
                <ul className="mt-1 list-disc ml-4">
                  {violations.map((v, i) => (
                    <li key={i}>{v.group ? `[${v.group}/${v.code}] ` : ""}{v.msg}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          {artifacts && summary ? (
            <div data-testid="case-graph-confrontation-result">
              <div className="mt-1 flex flex-wrap items-center gap-2" data-testid="case-graph-confrontation-downloads">
                <span className="text-ui-caption text-foreground-subtle">产物下载：</span>
                <button type="button" data-testid="case-graph-confrontation-download-svg"
                  className="inline-flex items-center gap-1 rounded border border-border px-2 py-0.5 text-ui-caption"
                  onClick={() => downloadText(artifacts.svg, `${nameBase}-对抗图.svg`, "image/svg+xml;charset=utf-8")}>
                  <ImageDown className="size-3" /> 对抗图 SVG
                </button>
                <button type="button" data-testid="case-graph-confrontation-download-table"
                  className="inline-flex items-center gap-1 rounded border border-border px-2 py-0.5 text-ui-caption"
                  onClick={() => downloadText(artifacts.analysisTableXml, `${nameBase}-对抗分析表.xls`, "application/vnd.ms-excel")}>
                  <FileSpreadsheet className="size-3" /> 17 列分析表
                </button>
              </div>

              <div className="mt-2" data-testid="case-graph-confrontation-svg">
                <p className="text-ui-caption text-foreground-subtle">三栏对抗图预览（A4 横版；深红只用于决定性强调与结论条）：</p>
                <img alt="庭审对抗图" className="max-w-full border border-border"
                  src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(artifacts.svg)}`} />
              </div>

              <div className="mt-2 overflow-auto" data-testid="case-graph-confrontation-table">
                <p className="text-ui-caption text-foreground-subtle">
                  要件摘要（只读展示；案「{summary.caseTitle}」·成熟度 {summary.maturity} ·诉请 {summary.claimsCount}
                  ·抗辩 {summary.defensesCount} ·来源 {summary.sourcesCount} ·待补 {summary.toCompleteCount}）：
                </p>
                <table className="w-full border-collapse text-ui-caption">
                  <thead>
                    <tr className="bg-selected/30 text-left">
                      <th className="border border-border px-1 py-0.5">板块</th>
                      <th className="border border-border px-1 py-0.5">要件/争点</th>
                      <th className="border border-border px-1 py-0.5">举证责任</th>
                      <th className="border border-border px-1 py-0.5">法律置信</th>
                      <th className="border border-border px-1 py-0.5">证据置信</th>
                      <th className="border border-border px-1 py-0.5">有争议</th>
                      <th className="border border-border px-1 py-0.5">达证明标准</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.rows.map((r) => (
                      <tr key={r.no} data-testid="case-graph-confrontation-table-row">
                        <td className="border border-border px-1 py-0.5">{r.no}</td>
                        <td className="border border-border px-1 py-0.5">{r.issue}</td>
                        <td className="border border-border px-1 py-0.5">{r.burden}</td>
                        <td className="border border-border px-1 py-0.5">{r.lawConfidence}</td>
                        <td className="border border-border px-1 py-0.5">{r.evidenceConfidence}</td>
                        <td className="border border-border px-1 py-0.5">{r.disputed ? "是" : "否"}</td>
                        <td className="border border-border px-1 py-0.5">{r.evidenceStandardMet ? "是" : "否"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
