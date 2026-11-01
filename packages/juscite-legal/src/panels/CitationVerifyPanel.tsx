// 功能 #14 引证核验（RE-14-引证核验.md §3.4 UI 结构落码）：核验（法源）面真数据面。
// 双模式（全文核验 textarea＋单条核验输入框 G1/G5）＋时点选择（缺省今天 YYYYMMDD，G6）＋
// 结果区（逐条卡片：徽章/引用原文/状态中文名/具名码/理由列表/现行条目可展开条文回读 G2）＋
// 汇总条（C3 形态，无「全文通过」类表述 G4）＋历史抽屉（G10，F4 落账唯一 UI 消费面）。
// 徽章三态映射（G3）：现行=✅、未知=⚠️、其余六态=❌（❌ 统一表达「废条不过」）。
// 双空态（G7）：结果区「本次会话尚未执行核验」/历史抽屉「暂无核验记录」；加载态防重复提交；
// 错误态（桥断连/包未配置显示具名错误，不白屏）。多轮语义（G11）：再次提交结果区整体替换。
// 零引用呈现态（G14）：已执行且 total=0→「本次核验完成：未发现引用」＋汇总条全零如实。
// 渲染体量上限（G13）：逐条卡片 500 条封顶折叠，汇总条恒全量如实。
// 隐身模式联动（G8）：核验纯本地零出站，隐身开启功能照常可用（本面板无任何出站门控）。
// 隐藏交互显式排除（G12）：无专属快捷键/右键菜单/拖拽；文本选择复制粘贴走系统标准行为。
// 数据经 /api/verify/* 桥端点族（RE-14 §3.3）；文案全部自写（表达隔离）。
import { useCallback, useEffect, useState } from "react";
import { History, RotateCw, X } from "lucide-react";

type CitationRecord = {
  index?: number; span?: [number, number];
  citation_text: string; title: string; article_ref: string | null;
  article_number: number | null; quote: string | null;
  status: string; decision: string | null; code: string | null;
  reasons: string[]; scope: string[]; verified_scoped: boolean;
  support: {
    article_located: boolean; article_text: string | null;
    quote_in_article: boolean | null; quote_in_document: boolean | null;
    text_carrier: string | null;
  } | null;
  replacement: string | null; replacement_reason: string;
};
type DocSummary = {
  total: number; by_status: Record<string, number>;
  not_fully_verifiable_statuses: string[]; accounting: string; note: string;
  data_face: string; source_chain: string[];
};
type HistoryRow = {
  id: string; requestedAt: number; asOf: string; citationText: string;
  status: string; code: string; verifiedScoped: boolean; reasons: string[];
};
type PanelConfig = { available: boolean; packDir: string; note: string };
type ResultData =
  | { kind: "single"; record: CitationRecord }
  | { kind: "document"; citations: CitationRecord[]; summary: DocSummary };

const RENDER_CAP = 500; // G13 渲染上限（汇总条恒全量）

function badgeOf(status: string): string {
  if (status === "现行") return "✅";
  if (status === "未知") return "⚠️";
  return "❌"; // 其余六态统一表达「废条不过」（G3）
}
function todayYmd(): string {
  return new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 10).replaceAll("-", "");
}
function timeText(ms: number): string {
  const d = new Date(ms);
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function CitationVerifyPanel({ prefill }: { prefill?: { text: string; token: number } }) {
  const [mode, setMode] = useState<"document" | "single">("document");
  const [docText, setDocText] = useState("");
  const [singleText, setSingleText] = useState("");
  const [asOf, setAsOf] = useState(todayYmd());
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [config, setConfig] = useState<PanelConfig | null>(null);
  const [result, setResult] = useState<ResultData | null>(null); // null=本次会话尚未执行（G7）
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<HistoryRow[] | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/verify/citation/config", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: PanelConfig) => { if (alive) setConfig(d); })
      .catch(() => { if (alive) setConfig({ available: false, packDir: "", note: "配置读取失败（桥未连接）" }); });
    return () => { alive = false; };
  }, []);

  // G9：手册「核验此条」→单条核验预填（切单条模式+填输入框，不自动提交）
  useEffect(() => {
    if (!prefill || !prefill.text) return;
    setMode("single");
    setSingleText(prefill.text);
    setErr(null);
  }, [prefill?.token]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadHistory = useCallback(async () => {
    setHistory(null);
    try {
      const r = await fetch("/api/verify/citation/history?limit=20", { cache: "no-store" });
      const d = await r.json();
      setHistory(d?.status === "OWNER_RESPONSE" ? d.result.items : []);
    } catch { setHistory([]); }
  }, []);

  async function submit() {
    if (busy) return; // G7 加载态防重复提交
    setBusy(true);
    setErr(null);
    setExpanded(new Set());
    try {
      const isDoc = mode === "document";
      const r = await fetch(isDoc ? "/api/verify/document" : "/api/verify/citation", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(isDoc ? { text: docText, as_of: asOf } : { citation: singleText, as_of: asOf }),
      });
      const d = await r.json();
      if (d?.status === "OWNER_RESPONSE") {
        // G11 整体替换：不清空重置、不追加混排
        setResult(d.result.citations
          ? { kind: "document", citations: d.result.citations, summary: d.result.summary }
          : { kind: "single", record: d.result });
      } else {
        setResult(null);
        setErr(String(d?.code ?? `HTTP ${r.status}`)); // G7 错误态具名呈现
      }
    } catch (e) {
      setResult(null);
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function refill(text: string, asOfValue: string) { // G10 点击历史回填可重跑（不自动提交）
    setMode("single");
    setSingleText(text);
    setAsOf(asOfValue);
    setErr(null);
  }

  const docResult = result?.kind === "document" ? result : null;
  const records: CitationRecord[] = docResult
    ? docResult.citations
    : result?.kind === "single" ? [result.record] : [];
  const summary: DocSummary | null = docResult?.summary ?? null;

  return (
    <div data-testid="citation-verify-panel" className="flex flex-col gap-3">
      {/* 模式切换 + 时点选择（G5/G6） */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded border border-border">
          <button type="button" data-testid="citation-mode-document"
            className={mode === "document" ? "bg-selected px-3 py-1 text-ui-sm" : "px-3 py-1 text-ui-sm hover:bg-selected"}
            onClick={() => setMode("document")}>全文核验</button>
          <button type="button" data-testid="citation-mode-single"
            className={mode === "single" ? "bg-selected px-3 py-1 text-ui-sm" : "px-3 py-1 text-ui-sm hover:bg-selected"}
            onClick={() => setMode("single")}>单条核验</button>
        </div>
        <label className="flex items-center gap-1 text-ui-caption text-foreground-subtle">
          核验时点
          <input data-testid="citation-as-of" value={asOf} onChange={(e) => setAsOf(e.target.value.trim())}
            placeholder="YYYYMMDD" size={8}
            className="rounded border border-border bg-header px-2 py-1 text-ui-sm text-foreground" />
        </label>
        <button type="button" data-testid="citation-submit" disabled={busy}
          onClick={() => void submit()}
          className="rounded border border-border px-3 py-1 text-ui-sm hover:bg-selected disabled:opacity-40">
          {busy ? "核验中…" : "执行核验"}
        </button>
        <button type="button" data-testid="citation-history-toggle"
          onClick={() => { const next = !historyOpen; setHistoryOpen(next); if (next) void loadHistory(); }}
          className="ml-auto flex items-center gap-1 rounded border border-border px-2 py-1 text-ui-sm hover:bg-selected">
          <History className="size-3.5" /> 核验记录
        </button>
      </div>

      {/* 输入区：双模式分立（G1/G5） */}
      {mode === "document" ? (
        <textarea data-testid="citation-doc-input" value={docText}
          onChange={(e) => setDocText(e.target.value)} rows={4}
          placeholder="粘贴或输入待核验文本，将对其中的法条引用逐条记账（如：《合同法》第一条“……”。）"
          className="w-full rounded border border-border bg-header p-2 text-ui-sm" />
      ) : (
        <input data-testid="citation-single-input" value={singleText}
          onChange={(e) => setSingleText(e.target.value)}
          placeholder="单条引用（如：《民事诉讼法》第一百二十二条）"
          className="w-full rounded border border-border bg-header px-2 py-1.5 text-ui-sm" />
      )}

      {/* 包未配置具名指引（§3.4）；错误态具名不白屏（G7） */}
      {config && !config.available ? (
        <p className="text-ui-sm text-amber-600" data-testid="citation-pack-missing">{config.note}</p>
      ) : null}
      {err ? <p className="text-ui-sm text-red-500" data-testid="citation-error">核验未执行：{err}</p> : null}

      {/* 历史抽屉（G10：最近 20 条落账倒序；点击回填；纯本地读取） */}
      {historyOpen ? (
        <div data-testid="citation-history" className="rounded border border-border p-2">
          <div className="mb-1 flex items-center justify-between text-ui-caption text-foreground-subtle">
            <span>最近 20 条核验落账（倒序，点击回填可重跑）</span>
            <button type="button" aria-label="收起历史" onClick={() => setHistoryOpen(false)} className="p-0.5 hover:bg-selected">
              <X className="size-3.5" />
            </button>
          </div>
          {history === null ? (
            <p className="text-ui-sm text-foreground-subtle">读取中…</p>
          ) : history.length === 0 ? (
            <p className="text-ui-sm text-foreground-subtle" data-testid="citation-history-empty">暂无核验记录</p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {history.map((h) => (
                <li key={h.id}>
                  <button type="button" data-testid="citation-history-item"
                    onClick={() => refill(h.citationText, h.asOf)}
                    className="block w-full truncate rounded px-1 py-0.5 text-left text-ui-sm hover:bg-selected">
                    {badgeOf(h.status)} {timeText(h.requestedAt)} · {h.citationText.length > 40 ? `${h.citationText.slice(0, 40)}…` : h.citationText}
                    <span className="text-foreground-subtle">（{h.status} · {h.asOf}）</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      {/* 结果区 */}
      <div data-testid="citation-results" className="flex flex-col gap-2">
        {result === null && !err && !busy ? (
          <p className="text-ui-sm text-foreground-subtle" data-testid="citation-empty">本次会话尚未执行核验</p>
        ) : null}
        {busy ? <p className="text-ui-sm text-foreground-subtle" data-testid="citation-busy">核验中，请稍候…</p> : null}

        {/* G14 零引用呈现态：与预执行空态分立 */}
        {docResult && docResult.summary.total === 0 ? (
          <div data-testid="citation-no-citations">
            <p className="text-ui-sm">本次核验完成：未发现引用。</p>
            <p className="text-ui-caption text-foreground-subtle">共 0 条引用（汇总计数如实呈现）</p>
          </div>
        ) : null}

        {/* 汇总条（C3/G4：总数+各状态计数，无「全文通过」类表述） */}
        {docResult && docResult.summary.total > 0 ? (
          <div data-testid="citation-summary" className="flex flex-wrap items-center gap-2 rounded border border-border px-2 py-1 text-ui-sm">
            <span>共 {docResult.summary.total} 条引用</span>
            {Object.entries(docResult.summary.by_status).map(([st, cnt]) => (
              <span key={st}>{badgeOf(st)} {st} × {cnt}</span>
            ))}
            <span className="text-ui-caption text-foreground-subtle">逐条范围记账，无文档级笼统结论</span>
          </div>
        ) : null}

        {/* 单条模式汇总（verified_scoped 徽章承担「已核验」语义，对拍 34） */}
        {result?.kind === "single" ? (
          <div data-testid="citation-single-summary" className="flex items-center gap-2 text-ui-sm">
            <span>{badgeOf(result.record.status)} {result.record.status}</span>
            <span className="text-foreground-subtle text-ui-caption">
              {result.record.verified_scoped ? "时点范围内核验通过" : "未通过时点范围核验"}
            </span>
          </div>
        ) : null}

        {/* 逐条卡片（G13：渲染上限 500，超出折叠如实计数） */}
        {records.slice(0, RENDER_CAP).map((rec, i) => {
          const idx = rec.index ?? i;
          const open = expanded.has(idx);
          const canExpand = Boolean(rec.support?.article_text);
          return (
            <div key={idx} data-testid="citation-record" className="rounded border border-border p-2">
              <div className="flex flex-wrap items-baseline gap-2">
                <span aria-label={`状态 ${rec.status}`}>{badgeOf(rec.status)}</span>
                <span className="text-ui-sm font-medium">{rec.citation_text}</span>
                <span className="text-ui-caption text-foreground-subtle">{rec.status}</span>
                {rec.code ? <span className="text-ui-caption text-foreground-subtle">[{rec.code}]</span> : null}
                {rec.verified_scoped ? <span className="text-ui-caption">✓ 已核</span> : null}
                {rec.replacement && rec.replacement !== "unknown" ? (
                  <span className="text-ui-caption text-foreground-subtle">替代：{rec.replacement}</span>
                ) : null}
              </div>
              {rec.reasons.length ? (
                <ul className="mt-1 flex flex-col gap-0.5">
                  {rec.reasons.map((rs, j) => (
                    <li key={j} className="text-ui-caption text-foreground-subtle">· {rs}</li>
                  ))}
                </ul>
              ) : null}
              {canExpand ? (
                <div className="mt-1">
                  <button type="button" data-testid="citation-expand"
                    onClick={() => setExpanded((prev) => {
                      const next = new Set(prev);
                      if (next.has(idx)) next.delete(idx); else next.add(idx);
                      return next;
                    })}
                    className="text-ui-caption text-foreground-subtle underline-offset-2 hover:underline">
                    {open ? "收起条文回读" : "展开条文回读"}
                  </button>
                  {open ? (
                    <pre data-testid="citation-article-text" className="mt-1 whitespace-pre-wrap break-words rounded bg-header p-2 text-ui-sm">{rec.support?.article_text}</pre>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
        {docResult && docResult.summary.total > RENDER_CAP ? (
          <p className="text-ui-caption text-foreground-subtle" data-testid="citation-render-capped">
            共 {docResult.summary.total} 条（已渲染前 {RENDER_CAP}）
          </p>
        ) : null}
        {records.length > 0 ? (
          <button type="button" onClick={() => { setResult(null); setErr(null); }}
            className="self-start text-ui-caption text-foreground-subtle underline-offset-2 hover:underline">
            <RotateCw className="mr-1 inline size-3" />清除本次结果
          </button>
        ) : null}
      </div>
    </div>
  );
}
