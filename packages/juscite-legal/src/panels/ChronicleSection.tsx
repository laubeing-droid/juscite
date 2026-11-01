// 【施工波二轮·可视化B轨 UI 件】大事记入口节（功能 #4 深化，挂办案时间轴面板内）。
// 流程：投影（chronicleView.ts 纯函数）→ 摄入对账（桥面 vizbIntakeReconcile）→ 判据守卫校验
// （桥面 vizbChronicleCheck）→ 四件同源交付（桥面 vizbChronicleRender）→ 产物预览（简表 SVG +
// 底稿行表格）与下载（Word 交付版/Excel 母表/机器读底稿）。
// 判定全部在桥面 @juscite/vizb：守卫不成立即拒绝出表并具名报违例，面板不降级硬填、不本地改判。
// 文案全部自写（表达隔离）；窗口文案如实披露投影口径（单册/无日期不编入/证据状态机械判定）。
import { useCallback, useState } from "react";
import { FileSpreadsheet, FileText, ScrollText } from "lucide-react";
import { useServices } from "../ui-kit.js";
import {
  buildIntakePayload, projectChronicleFactBase, sanitizeDownloadName,
  type ChronicleDocText, type ChronicleEventLike,
} from "./chronicleView.js";

interface CheckResult {
  ok: boolean;
  refusal: string | null;
  schemaViolations: Array<{ path: string; msg: string }>;
  guardViolations: Array<{ group: string; code: string; msg: string; factNo?: number }>;
  artifactViolations: Array<{ group: string; code: string; msg: string }>;
}
interface IntakeResult {
  ok: boolean;
  docs: Array<{ docId: string; state: string; pagesRead: number; notes: string[] }>;
  logs: string[];
}
interface Artifacts {
  wordXml: string;
  excelXml: string;
  briefSvgPages: string[];
  factBaseJson: string;
}

const INTAKE_STATE_LABEL: Record<string, string> = {
  read: "已读",
  explicitlySkipped: "明示不读（放行留痕）",
  missing: "该读没读",
  "partial-missing": "部分缺页",
};

function downloadText(content: string, filename: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export function ChronicleSection({ events, caseName, workspacePath, ignored }: {
  events: ChronicleEventLike[];
  caseName: string;
  workspacePath?: string;
  ignored: string[];
}) {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as {
    caseGraphReadSource?: (p: { workspacePath: string; filename: string }) => Promise<{ name: string; text: string; truncated: boolean }>;
    vizbIntakeReconcile?: (p: { pages: unknown[]; skips: unknown[]; manifest: unknown[] }) => Promise<IntakeResult>;
    vizbChronicleCheck?: (p: { factBase: unknown }) => Promise<CheckResult>;
    vizbChronicleRender?: (p: { factBase: unknown }) => Promise<Artifacts>;
  };

  const [busy, setBusy] = useState(false);
  const [flowError, setFlowError] = useState<string | null>(null);
  const [intake, setIntake] = useState<IntakeResult | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [violations, setViolations] = useState<CheckResult["guardViolations"] | CheckResult["schemaViolations"] | null>(null);
  const [artifacts, setArtifacts] = useState<Artifacts | null>(null);
  const [excluded, setExcluded] = useState<Array<{ eventId: string; eventType: string; reason: string }>>([]);
  const [included, setIncluded] = useState(0);

  const run = useCallback(() => {
    if (busy) return;
    if (!svc.vizbChronicleRender || !svc.vizbChronicleCheck) {
      setFlowError("桥面未提供大事记通道（vizbChronicleCheck/Render 不可用），本面停用。");
      return;
    }
    setBusy(true);
    setFlowError(null);
    setIntake(null);
    setRefusal(null);
    setViolations(null);
    setArtifacts(null);
    setExcluded([]);
    setIncluded(0);

    // 需要取全文的材料 = 有引文出处的引用名集合（去重）
    const referenced: string[] = [];
    for (const ev of events) {
      for (const r of ev.sourceRefs ?? []) {
        if (typeof r.filename === "string" && r.filename && typeof r.quote === "string" && r.quote
          && !referenced.includes(r.filename)) referenced.push(r.filename);
      }
    }
    if (!svc.caseGraphReadSource) {
      setBusy(false);
      setFlowError("桥面未提供材料文本读取通道（caseGraphReadSource 不可用），照录无法核验。");
      return;
    }
    Promise.allSettled(
      referenced.map((filename) => svc.caseGraphReadSource!({ workspacePath: workspacePath ?? "", filename })),
    )
      .then((settled) => {
        const texts: ChronicleDocText[] = [];
        settled.forEach((s, i) => {
          if (s.status === "fulfilled" && s.value && typeof s.value.text === "string") {
            texts.push({ filename: referenced[i]!, text: s.value.text, truncated: s.value.truncated === true });
          }
        });
        const proj = projectChronicleFactBase(events, texts, caseName || "未命名案件");
        setIncluded(proj.included);
        setExcluded(proj.excluded);

        // 共用前置：摄入对账（整份单页口径；取不到文本的材料缺席 pages → 桥面判该读没读）
        const intakeRun: Promise<IntakeResult | null> = svc.vizbIntakeReconcile
          ? svc.vizbIntakeReconcile(buildIntakePayload(texts, referenced, ignored))
          : Promise.resolve(null);
        return intakeRun.then((ir) => {
          setIntake(ir);
          if (ir && !ir.ok) {
            setRefusal("材料摄入对账不通过（该读没读）：下列材料未能读到全文，拒绝出表。");
            setBusy(false);
            return;
          }
          return svc.vizbChronicleCheck!({ factBase: proj.factBase }).then((ck) => {
            if (!ck.ok) {
              setRefusal(ck.refusal ?? "判据守卫不成立，拒绝出表。");
              setViolations(ck.guardViolations.length ? ck.guardViolations : ck.schemaViolations);
              setBusy(false);
              return;
            }
            return svc.vizbChronicleRender!({ factBase: proj.factBase }).then((arts) => {
              setArtifacts(arts);
              setBusy(false);
            });
          });
        });
      })
      .catch((e: unknown) => {
        setBusy(false);
        setFlowError(String((e as Error)?.message ?? e));
      });
  }, [busy, events, caseName, workspacePath, ignored, svc]);

  // 底稿行预览数据（同源 factBaseJson；仅展示，判定与渲染均在桥面）
  let factRows: Array<{ factNo: number; dateStr: string; title: string; content: string; sourceDoc: string; locator: string }> = [];
  if (artifacts) {
    try {
      const fb = JSON.parse(artifacts.factBaseJson) as { facts?: typeof factRows };
      factRows = fb.facts ?? [];
    } catch { /* 底稿 JSON 解析失败时表格留空，四件原件照常可下载 */ }
  }
  const nameBase = sanitizeDownloadName(caseName || "案件");

  return (
    <div className="mt-3 rounded border border-border p-2" data-testid="timeline-chronicle">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-ui-sm font-medium">大事记</h3>
        <span className="text-ui-caption text-foreground-subtle">
          从带引文出处的时间线事件投影出事实底稿，桥面判据守卫通过后出四件同源交付（单册口径）
        </span>
        <button type="button" data-testid="timeline-chronicle-run"
          className="ml-auto rounded border border-border px-2 py-0.5 text-ui-caption disabled:opacity-50"
          disabled={busy} onClick={run}>
          {busy ? "正在出表…" : "生成大事记"}
        </button>
      </div>
      <p className="mt-1 text-ui-caption text-foreground-subtle">
        大事记为办案辅助整理，呈报前须律师逐行复核；证据状态由有无证据编号机械判定（本面投影无证据编号，一律记「仅当事人陈述」并进不确定清单）。
      </p>
      {flowError ? <p className="mt-1 text-ui-caption text-red-500" data-testid="timeline-chronicle-error">{flowError}</p> : null}

      {included || excluded.length ? (
        <p className="mt-1 text-ui-caption text-foreground-subtle" data-testid="timeline-chronicle-projection">
          投影结果：编入 {included} 条事实；未编入 {excluded.length} 条
          （无日期不造日、无引文无照录，逐条如实披露）。
        </p>
      ) : null}
      {excluded.length ? (
        <ul className="mt-1 text-ui-caption text-foreground-subtle" data-testid="timeline-chronicle-excluded">
          {excluded.map((x) => <li key={x.eventId}>· {x.eventType}：{x.reason}</li>)}
        </ul>
      ) : null}

      {intake ? (
        <div className="mt-1 text-ui-caption" data-testid="timeline-chronicle-intake">
          摄入对账（整份单页口径）：
          {intake.docs.map((d) => (
            <span key={d.docId} className="mr-2">
              {d.docId}={INTAKE_STATE_LABEL[d.state] ?? d.state}
            </span>
          ))}
          {!intake.ok ? <span className="text-red-500">{intake.logs.join("；")}</span> : null}
        </div>
      ) : null}

      {refusal ? (
        <div className="mt-1 rounded border border-red-300 bg-red-50 p-2 text-ui-caption text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300"
          data-testid="timeline-chronicle-refusal">
          <p>{refusal}</p>
          {violations?.length ? (
            <ul className="mt-1 list-disc ml-4">
              {violations.map((v, i) => (
                <li key={i}>
                  {"group" in v && v.group ? `[${(v as { group: string }).group}/${(v as { code: string }).code}] ` : ""}
                  {(v as { msg: string }).msg}{"factNo" in v && (v as { factNo?: number }).factNo != null ? `（事实 ${(v as { factNo: number }).factNo}）` : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {artifacts ? (
        <div data-testid="timeline-chronicle-result">
          <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="timeline-chronicle-downloads">
            <span className="text-ui-caption text-foreground-subtle">四件同源交付下载：</span>
            <button type="button" data-testid="timeline-chronicle-download-word"
              className="inline-flex items-center gap-1 rounded border border-border px-2 py-0.5 text-ui-caption"
              onClick={() => downloadText(artifacts.wordXml, `${nameBase}-大事记交付版.doc`,
                "application/vnd.ms-word")}>
              <FileText className="size-3" /> Word 交付版
            </button>
            <button type="button" data-testid="timeline-chronicle-download-excel"
              className="inline-flex items-center gap-1 rounded border border-border px-2 py-0.5 text-ui-caption"
              onClick={() => downloadText(artifacts.excelXml, `${nameBase}-大事记母表.xls`,
                "application/vnd.ms-excel")}>
              <FileSpreadsheet className="size-3" /> Excel 母表
            </button>
            <button type="button" data-testid="timeline-chronicle-download-json"
              className="inline-flex items-center gap-1 rounded border border-border px-2 py-0.5 text-ui-caption"
              onClick={() => downloadText(artifacts.factBaseJson, `${nameBase}-大事记底稿.json`,
                "application/json;charset=utf-8")}>
              <ScrollText className="size-3" /> 机器读底稿
            </button>
          </div>

          <div className="mt-2" data-testid="timeline-chronicle-svg">
            <p className="text-ui-caption text-foreground-subtle">A4 呈报简表预览（{artifacts.briefSvgPages.length} 页；红仅用于分组色块）：</p>
            {artifacts.briefSvgPages.map((svg, i) => (
              <img key={i} alt={`大事记简表第 ${i + 1} 页`} className="max-w-full border border-border"
                src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`} />
            ))}
          </div>

          <div className="mt-2 overflow-auto" data-testid="timeline-chronicle-table">
            <p className="text-ui-caption text-foreground-subtle">事实底稿行（与四件交付同源；争点列在 Excel 母表由律师回填）：</p>
            <table className="w-full border-collapse text-ui-caption">
              <thead>
                <tr className="bg-selected/30 text-left">
                  <th className="border border-border px-1 py-0.5">号</th>
                  <th className="border border-border px-1 py-0.5">日期</th>
                  <th className="border border-border px-1 py-0.5">事项</th>
                  <th className="border border-border px-1 py-0.5">主要内容（照录）</th>
                  <th className="border border-border px-1 py-0.5">出处</th>
                  <th className="border border-border px-1 py-0.5">定位</th>
                </tr>
              </thead>
              <tbody>
                {factRows.map((f) => (
                  <tr key={f.factNo} data-testid="timeline-chronicle-table-row">
                    <td className="border border-border px-1 py-0.5">{f.factNo}</td>
                    <td className="border border-border px-1 py-0.5 font-mono">{f.dateStr}</td>
                    <td className="border border-border px-1 py-0.5">{f.title}</td>
                    <td className="border border-border px-1 py-0.5">{f.content}</td>
                    <td className="border border-border px-1 py-0.5">{f.sourceDoc}</td>
                    <td className="border border-border px-1 py-0.5 font-mono">{f.locator}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
