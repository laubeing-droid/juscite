// 【步骤4·#5 冲突查重】快检弹窗（RE-5-冲突查重.md §3.4 面二；对拍 A2/E3/E5/I3）。
// 工作台入口的轻量快检：角色下拉+名称+证件单行式表单、命中列表（弹窗面渲染 reason 文字=
// 与预检页的披露分工差异，D9/E4）、零命中绿卡、链接到完整预检页。文案全自写（表达隔离）。
import { useEffect, useState } from "react";
import { FileSearch, ScanSearch, X } from "lucide-react";
import { Button } from "../ui-kit.js";
import { Input } from "../ui-kit.js";
import { useServices } from "../ui-kit.js";
import {
  HIT_ROLE_LABEL, MATCH_KIND_LABEL, SEVERITY_LABEL, SEVERITY_TONE, matchKindOf,
  type ConflictSeverity, type PartyRole,
} from "../kernel/conflictModel.js";
import type { ConflictCheckProto, ConflictHitProto } from "./ConflictPrecheckPanel.js";

const TONE_CLS: Record<string, string> = {
  red: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  orange: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  amber: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  gray: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
};
const ROLE_DROPDOWN: Array<{ value: PartyRole; label: string }> = [
  { value: "CLIENT", label: "拟委托方" },
  { value: "OPPOSING_PARTY", label: "对方" },
  { value: "THIRD_PARTY", label: "第三人" },
];

export function ConflictQuickDialog({ onClose, onOpenFull }: { onClose: () => void; onOpenFull: () => void }) {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as {
    conflictRun?: (p: Record<string, unknown>) => Promise<{ check: ConflictCheckProto }>;
  };
  const [role, setRole] = useState<PartyRole>("CLIENT");
  const [name, setName] = useState("");
  const [idNumber, setIdNumber] = useState("");
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ConflictCheckProto | null>(null);

  // 挂载即聚焦名称框（轻量动线）
  useEffect(() => {
    (document.querySelector("[data-testid=conflict-quick-name]") as HTMLInputElement | null)?.focus();
  }, []);

  const run = async () => {
    if (!svc.conflictRun) return;
    if (!name.trim() && !idNumber.trim()) {
      setError("请至少填写名称或证件号之一");
      return;
    }
    setSearching(true);
    setError(null);
    try {
      const r = await svc.conflictRun({
        queries: [{ role, name: name.trim(), idNumber: idNumber.toUpperCase().replace(/\s+/g, "") }],
      });
      setResult(r.check);
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" role="dialog" aria-modal="true" data-testid="conflict-quick-dialog">
      <div className="flex max-h-[85vh] w-[560px] max-w-[92vw] flex-col overflow-hidden rounded-xl border border-border bg-background shadow-lg">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="flex items-center gap-2 text-ui-base font-semibold">
            <ScanSearch className="size-4" /> 冲突快检
          </h2>
          <button type="button" onClick={onClose} aria-label="关闭快检" className="rounded p-1 hover:bg-subtle" data-testid="conflict-quick-close">
            <X className="size-4" />
          </button>
        </div>
        <div className="flex flex-col gap-3 overflow-auto p-4">
          <p className="text-ui-caption text-foreground-subtle">
            填入姓名或证件号（至少一项）快速查一查所内登记记录。快检仅供了解情况，不出结论。
          </p>
          <div className="flex items-center gap-2">
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as PartyRole)}
              className="rounded-md border border-border bg-background px-2 py-1.5 text-ui-sm"
              data-testid="conflict-quick-role"
              aria-label="主体角色"
            >
              {ROLE_DROPDOWN.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
            <Input
              value={name}
              maxLength={120}
              placeholder="名称"
              className="min-w-0 flex-1"
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void run(); }}
              data-testid="conflict-quick-name"
            />
            <Input
              value={idNumber}
              maxLength={50}
              placeholder="证件号"
              className="min-w-0 flex-1 font-mono"
              onChange={(e) => setIdNumber(e.target.value.toUpperCase().replace(/\s+/g, ""))}
              onKeyDown={(e) => { if (e.key === "Enter") void run(); }}
              data-testid="conflict-quick-id"
            />
            <Button size="sm" disabled={searching} onClick={() => void run()} data-testid="conflict-quick-run">
              {searching
                ? <span className="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent" aria-label="检索中" />
                : <FileSearch className="size-4" />}
              快检
            </Button>
          </div>
          {error ? <p className="text-ui-sm text-red-500" data-testid="conflict-quick-error">{error}</p> : null}

          {result ? (
            result.hits.length > 0 ? (
              <div className="flex flex-col gap-2" data-testid="conflict-quick-hits">
                {/* 成功反馈计数行（I3；同名/证件匹配细分后缀按 C9 恒零不出现，不拼） */}
                <p className="text-ui-caption text-foreground-subtle" data-testid="conflict-quick-count">
                  命中 {result.hits.length} 条，请逐条审阅。
                </p>
                {result.hits.map((h: ConflictHitProto) => (
                  <div key={h.id} className="rounded-lg border border-border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded px-1.5 py-0.5 text-ui-caption font-medium ${TONE_CLS[SEVERITY_TONE[h.severity]] ?? ""}`}>
                        {SEVERITY_LABEL[h.severity]}
                      </span>
                      <span className="text-ui-sm font-medium">{h.matchedName}</span>
                      <span className="rounded bg-subtle px-1.5 py-0.5 text-ui-caption">{MATCH_KIND_LABEL[matchKindOf(h)]}</span>
                      <span className="text-ui-caption text-foreground-subtle">
                        登记身份：{HIT_ROLE_LABEL[h.storedRole]}{h.storedStanding ? ` · ${h.storedStanding}` : ""}
                      </span>
                    </div>
                    {/* 弹窗面渲染 reason 文字（与预检页的披露分工差异，E4/D9） */}
                    <p className="mt-1 text-ui-caption text-foreground-subtle" data-testid="conflict-quick-reason">{h.reason}</p>
                    {h.brief ? (
                      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-ui-caption text-foreground-subtle">
                        {h.brief.caseNo ? <span>案号：{h.brief.caseNo}</span> : null}
                        {h.brief.name ? <span>案件：{h.brief.name}</span> : null}
                        {h.brief.cause ? <span>案由：{h.brief.cause}</span> : null}
                        {h.brief.status ? <span>状态：{h.brief.status}</span> : null}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-ui-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" data-testid="conflict-quick-zero">
                未发现相关记录。这仅表示所内登记记录里没有匹配，不等于确认无冲突：别名、关联企业、未录入系统的代理关系仍需自行核实。
              </div>
            )
          ) : null}

          <button
            type="button"
            className="self-start text-ui-caption text-foreground-subtle underline hover:text-foreground"
            onClick={onOpenFull}
            data-testid="conflict-quick-open-full"
          >
            需要多主体一次查完？打开完整预检页
          </button>
        </div>
      </div>
    </div>
  );
}
