// 【步骤4·#5 冲突查重】案件冲突复核卡（RE-5-冲突查重.md §3.4 面四+§3.5 P2；对拍 H1-H4/A5）。
// 挂看板案件上下文（案内待办卡同位）：仅待复核时渲染（H1 needsReview / A5）；
// 说明句+当事人登记（复核检索前置）+按当前主体重新检索（H3）+历次记录（H2）+备注+三结论键
//（备注非空才可点，H2/H4）。结论值域四态单源在 conflictModel；文案全自写（表达隔离）。
// ⚠ 过渡态：H5 写路径硬门禁（新增程序/合同生效/计费登记）随对应模块接入挂闸位
//（assertReviewCurrent 已在桥侧导出）；收案来源继承（G5）随收案实体接入。
import { useCallback, useEffect, useState } from "react";
import { RefreshCcw, ShieldAlert } from "lucide-react";
import { Button } from "../ui-kit.js";
import { Input } from "../ui-kit.js";
import { useServices } from "../ui-kit.js";
import {
  HIT_ROLE_LABEL, SEVERITY_LABEL, SEVERITY_TONE,
  type ConflictSeverity, type PartyRole,
} from "../kernel/conflictModel.js";
import type { ConflictCheckProto } from "./ConflictPrecheckPanel.js";

const TONE_CLS: Record<string, string> = {
  red: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  orange: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  amber: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  gray: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
};
const CONCLUSION_LABEL: Record<string, string> = {
  PENDING: "待结论", SAME_SUBJECT: "有冲突（不承接）", DIFFERENT: "可承接", NEED_INFO: "信息不足",
};
const ROLE_DROPDOWN: Array<{ value: PartyRole; label: string }> = [
  { value: "CLIENT", label: "委托方" },
  { value: "OPPOSING_PARTY", label: "对方" },
  { value: "THIRD_PARTY", label: "第三人" },
];
interface PartyRow { id: string; role: PartyRole; standing: string | null; name: string; idNumber: string; socialCode: string }
interface ReviewStateProto {
  matterId: string; needsReview: boolean; reasons: string[];
  parties: PartyRow[]; fingerprint: string | null; history: ConflictCheckProto[];
}
interface PartyDraft { role: PartyRole; name: string; idNumber: string }

export function ConflictReviewCard({ caseId, caseName }: { caseId: string; caseName: string }) {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as {
    conflictReviewState?: (p: Record<string, unknown>) => Promise<ReviewStateProto>;
    conflictMatterRun?: (p: Record<string, unknown>) => Promise<{ check: ConflictCheckProto }>;
    conflictMatterDecide?: (p: Record<string, unknown>) => Promise<{ check: ConflictCheckProto }>;
    conflictPartySet?: (p: Record<string, unknown>) => Promise<{ parties: PartyRow[] }>;
  };
  const [state, setState] = useState<ReviewStateProto | null>(null);
  const [drafts, setDrafts] = useState<PartyDraft[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!svc.conflictReviewState || !caseId) return;
    try {
      const s = await svc.conflictReviewState({ matterId: caseId });
      setState(s);
      setDrafts(s.parties.length
        ? s.parties.map((p) => ({ role: p.role, name: p.name, idNumber: p.idNumber }))
        : [{ role: "CLIENT", name: "", idNumber: "" }]);
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
    }
  }, [caseId, svc]);

  useEffect(() => {
    setState(null);
    setError(null);
    setNotice(null);
    setNote("");
    void reload();
  }, [reload]);

  if (!svc.conflictReviewState) return null;
  // A5/H1：仅待复核时渲染（无案件选择或 needsReview=false → 不渲染，不占主视觉）
  if (!state || !state.needsReview) return null;

  const saveParties = async () => {
    if (!svc.conflictPartySet) return;
    const filled = drafts.filter((d) => d.name.trim());
    if (!filled.length) { setError("请先登记至少一位当事人（名称必填）"); return; }
    setBusy(true); setError(null);
    try {
      await svc.conflictPartySet({
        subjectType: "matter", subjectId: caseId,
        parties: filled.map((d) => ({ role: d.role, name: d.name.trim(), idNumber: d.idNumber })),
      });
      setNotice("当事人已登记。");
      await reload();
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
    } finally { setBusy(false); }
  };

  const runReview = async () => {
    if (!svc.conflictMatterRun) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const r = await svc.conflictMatterRun({ matterId: caseId });
      const n = r.check.hits.length;
      setNotice(n > 0 ? `复核检索完成：命中 ${n} 条，请逐条核查后给出结论。` : "复核检索完成：登记记录未命中，已自动标记可承接。");
      await reload();
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
    } finally { setBusy(false); }
  };

  const decide = async (conclusion: string) => {
    if (!svc.conflictMatterDecide) return;
    const latest = state.history[0];
    if (!latest) { setError("还没有复核检索记录"); return; }
    setBusy(true); setError(null); setNotice(null);
    try {
      await svc.conflictMatterDecide({ matterId: caseId, checkId: latest.id, conclusion, note: note.trim() });
      setNotice("复核结论已保存。");
      setNote("");
      await reload();
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
    } finally { setBusy(false); }
  };

  return (
    <div className="mt-4 rounded border border-amber-400/60 bg-amber-50/40 p-3 dark:border-amber-700 dark:bg-amber-950/30" data-testid="conflict-review-card">
      <div className="mb-1.5 flex items-center gap-2">
        <ShieldAlert className="size-4 text-amber-600 dark:text-amber-400" />
        <h3 className="text-ui-base font-medium">利益冲突复核 · {caseName}</h3>
      </div>
      <p className="text-ui-caption text-foreground-subtle">
        {state.reasons.includes("主体或范围已变化") ? "主体或代理范围已变化；" : "本案尚无有效冲突复核；"}
        复核通过前，新增程序、委托合同与补充协议无法办理。
      </p>

      {/* 当事人登记（复核检索前置；服务端权威重派由此取数） */}
      <div className="mt-2 rounded border border-border p-2" data-testid="conflict-review-parties">
        <p className="mb-1 text-ui-caption font-medium">本案当事人（名称必填；证件号选填，用于精确比对）</p>
        {drafts.map((d, i) => (
          <div key={i} className="mb-1 flex items-center gap-1.5">
            <select
              value={d.role} aria-label="当事人角色"
              className="rounded border border-border px-1 py-0.5 text-ui-caption"
              onChange={(e) => setDrafts((ds) => ds.map((x, j) => (j === i ? { ...x, role: e.target.value as PartyRole } : x)))}
              data-testid={`conflict-review-role-${i}`}
            >
              {ROLE_DROPDOWN.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
            <Input
              value={d.name} maxLength={120} placeholder="当事人名称"
              className="min-w-0 flex-1" data-testid={`conflict-review-name-${i}`}
              onChange={(e) => setDrafts((ds) => ds.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))}
            />
            <Input
              value={d.idNumber} maxLength={50} placeholder="证件号"
              className="min-w-0 flex-1 font-mono" data-testid={`conflict-review-id-${i}`}
              onChange={(e) => setDrafts((ds) => ds.map((x, j) => (j === i ? { ...x, idNumber: e.target.value.toUpperCase().replace(/\s+/g, "") } : x)))}
            />
          </div>
        ))}
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={busy}
            onClick={() => setDrafts((ds) => [...ds, { role: "OPPOSING_PARTY", name: "", idNumber: "" }])}
            data-testid="conflict-review-add-party">
            加一位当事人
          </Button>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => void saveParties()} data-testid="conflict-review-save-parties">
            保存当事人
          </Button>
          <Button size="sm" disabled={busy} onClick={() => void runReview()} data-testid="conflict-review-run">
            {busy ? <span className="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent" aria-label="检索中" /> : <RefreshCcw className="size-4" />}
            按当前主体重新检索
          </Button>
        </div>
      </div>

      {/* 命中摘要（最新一次） */}
      {state.history[0]?.hits.length ? (
        <div className="mt-2 flex flex-col gap-1" data-testid="conflict-review-hits">
          {state.history[0].hits.map((h) => (
            <div key={h.id} className="flex flex-wrap items-center gap-2 rounded border border-border px-2 py-1 text-ui-caption">
              <span className={`rounded px-1.5 py-0.5 font-medium ${TONE_CLS[SEVERITY_TONE[h.severity as ConflictSeverity]] ?? ""}`}>
                {SEVERITY_LABEL[h.severity as ConflictSeverity]}
              </span>
              <span className="font-medium">{h.matchedName}</span>
              <span className="text-foreground-subtle">登记身份：{HIT_ROLE_LABEL[h.storedRole as PartyRole] ?? h.storedRole}{h.storedStanding ? ` · ${h.storedStanding}` : ""}</span>
              {h.brief?.name ? <span className="text-foreground-subtle">案件：{h.brief.name}</span> : null}
            </div>
          ))}
        </div>
      ) : null}

      {/* 历次记录（H2）：时间·结论·失效标记·备注·结论人 */}
      {state.history.length ? (
        <div className="mt-2 text-ui-caption text-foreground-subtle" data-testid="conflict-review-history">
          <p className="font-medium text-foreground">历次复核</p>
          <ul className="mt-0.5 space-y-0.5">
            {state.history.slice(0, 5).map((h) => {
              const stale = h.fingerprint !== state.fingerprint;
              return (
                <li key={h.id} className="flex flex-wrap items-center gap-2">
                  <span>{h.checkedAt.slice(0, 19).replace("T", " ")}</span>
                  <span>{CONCLUSION_LABEL[h.conclusion] ?? h.conclusion}</span>
                  {stale ? <span className="rounded bg-subtle px-1 py-0.5">主体或范围已变化</span> : null}
                  {h.automatic ? <span className="rounded bg-subtle px-1 py-0.5">系统自动</span> : null}
                  {h.decidedBy ? <span>结论人：{h.decidedBy}</span> : null}
                  {h.note ? <span className="truncate">备注：{h.note}</span> : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {/* 备注+三结论键（备注非空才可点，H2/H4） */}
      <div className="mt-2">
        <textarea
          value={note} maxLength={500} rows={2}
          placeholder="复核理由及处理措施（给出结论时必填）"
          className="w-full rounded border border-border px-2 py-1 text-ui-sm"
          onChange={(e) => setNote(e.target.value)}
          data-testid="conflict-review-note"
        />
        <div className="mt-1 flex flex-wrap items-center gap-2">
          {(["DIFFERENT", "SAME_SUBJECT", "NEED_INFO"] as const).map((c) => (
            <Button
              key={c} variant="outline" size="sm"
              disabled={busy || !note.trim()}
              onClick={() => void decide(c)}
              data-testid={`conflict-review-decide-${c}`}
              className={c === "DIFFERENT" ? "border-emerald-400 text-emerald-700 dark:text-emerald-300"
                : c === "SAME_SUBJECT" ? "border-red-400 text-red-700 dark:text-red-300" : ""}
            >
              {CONCLUSION_LABEL[c]}
            </Button>
          ))}
          <span className="text-ui-caption text-foreground-subtle">结论须填复核理由（写明处理措施或书面同意留痕）</span>
        </div>
      </div>

      {error ? <p className="mt-1 text-ui-caption text-red-500" data-testid="conflict-review-error">{error}</p> : null}
      {notice ? <p className="mt-1 text-ui-caption text-emerald-600 dark:text-emerald-400" data-testid="conflict-review-notice">{notice}</p> : null}
    </div>
  );
}
