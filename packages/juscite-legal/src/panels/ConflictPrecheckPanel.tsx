// 【步骤4·#5 冲突查重】预检页（RE-5-冲突查重.md §3.4 面一；对拍 A/B/C/D/E 组 UI 面）。
// 文案全部自写（表达隔离：语义结构对齐≠抄竞品句子）；视觉自绘徽章/色卡。
// 行为面：主体行增删改（首行拟委托方/新行对方 A8）+证件大写化 B4+Enter 检索 B6+空行过滤 B7+
// 检索后行只读-修改键 B5+四格统计条 E6+按主体分组命中卡（严重度染色+命中方式三分+最小披露；
// 预检页命中卡不渲染 reason 文字 E4）+未命中主体区+免责声明 E7+侧栏小结 E9+新建预检重置。
// 数据经桥 conflictRun 桥面（件1）；角色/严重度标签值单源在 conflictModel。
import { useCallback, useEffect, useMemo, useState } from "react";
import { Eye, FileSearch, Lock, Pencil, Plus, RotateCcw, ScanSearch, Trash2 } from "lucide-react";
import { Button } from "../ui-kit.js";
import { Input } from "../ui-kit.js";
import { useServices } from "../ui-kit.js";
import {
  INPUT_ROLES, MATCH_KIND_LABEL, SEVERITY_LABEL, SEVERITY_RANK, SEVERITY_TONE,
  HIT_ROLE_LABEL, matchKindOf,
  type ConflictSeverity, type PartyRole,
} from "../kernel/conflictModel.js";

// 桥协议形状（与桥 conflictRun 返回同构；本地镜像声明，字段缺失按空兜底）
export interface ConflictHitProto {
  id: string; hitType: string; targetType: string; targetId: string | null;
  matchedName: string; matchedField: "name" | "idNumber"; matchedValue: string;
  matchedRatio: number; matchLevel: string | null; severity: ConflictSeverity;
  reason: string; storedRole: PartyRole; storedStanding: string | null;
  brief: { caseNo: string | null; name: string | null; cause: string | null; courtType: string | null; status: string | null } | null;
}
export interface ConflictCheckProto {
  id: string; subjectType: string; subjectId: string | null;
  queries: Array<{ role: PartyRole; name: string; idNumber: string }>;
  fingerprint: string | null;
  conclusion: string; decidedBy: string | null; decidedAt: string | null; automatic: boolean; note: string | null;
  checkedAt: string; hitCount: number | null; hits: ConflictHitProto[];
}
interface RowInput { role: PartyRole; name: string; idNumber: string }

// 严重度→配色（预检页卡染tone；SEVERITY_TONE 值单源在模型，色表 UI 自绘）
const TONE_CLS: Record<string, string> = {
  red: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  orange: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  amber: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  gray: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
};
const ROLE_INPUT_LABEL: Record<string, string> = {
  CLIENT: "拟委托方", OPPOSING_PARTY: "对方", THIRD_PARTY: "第三人",
};
const ID_RE = /\s+/g;

function emptyRow(role: PartyRole): RowInput {
  return { role, name: "", idNumber: "" };
}
// 证件输入归一（B4）：大写化+去空白
function normalizeIdInput(v: string): string {
  return v.toUpperCase().replace(ID_RE, "");
}
function rowHasInput(r: RowInput): boolean {
  return r.name.trim().length > 0 || r.idNumber.trim().length > 0;
}
// 命中反推所属主体（E6）：证件命中按 matchedValue=查询证件、名称命中按 matchedValue=查询名称
function hitsOfQuery(q: RowInput, idNorm: string, hits: ConflictHitProto[]): ConflictHitProto[] {
  return hits.filter((h) => h.matchedField === "idNumber"
    ? idNorm.length > 0 && h.matchedValue.toUpperCase() === idNorm
    : h.matchedValue === q.name.trim());
}

export function ConflictPrecheckPanel({ onViewMatter }: { onViewMatter?: () => void }) {
  const { zcodeAgentService } = useServices();
  const svc = zcodeAgentService as {
    conflictRun?: (p: Record<string, unknown>) => Promise<{ check: ConflictCheckProto }>;
  };
  const [rows, setRows] = useState<RowInput[]>([emptyRow("CLIENT")]); // A8 首行=拟委托方
  const [locked, setLocked] = useState(false); // 检索后行只读（B5）
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [result, setResult] = useState<ConflictCheckProto | null>(null);

  // A7：URL ?name= 预填首行检索主体（截 100 字）。工作台视图无路由，location.search 与
  // 视图状态并存——带参链接打开应用后，进入预检页即预填；只消费一次（挂载期）。
  useEffect(() => {
    try {
      const raw = new URLSearchParams(window.location.search).get("name") ?? "";
      const name = raw.slice(0, 100);
      if (name) setRows((rs) => rs.map((r, i) => (i === 0 ? { ...r, name } : r)));
    } catch { /* 无 location 环境等静默 */ }
  }, []);

  const run = useCallback(async (inputRows: RowInput[]) => {
    if (!svc.conflictRun) return;
    const filled = inputRows.filter(rowHasInput); // B7 空行自动过滤
    if (!filled.length) {
      setError("请至少填写一个主体的名称或证件号");
      return;
    }
    setSearching(true);
    setError(null);
    setNotice(null);
    try {
      const r = await svc.conflictRun({
        queries: filled.map((q) => ({ role: q.role, name: q.name.trim(), idNumber: normalizeIdInput(q.idNumber) })),
      });
      setResult(r.check);
      setLocked(true); // B5 提交后输入区转只读
      const n = r.check.hits.length;
      setNotice(n > 0 ? `预检完成，共 ${n} 条相关记录。` : "预检完成，登记记录中未发现相关记录。");
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
    } finally {
      setSearching(false);
    }
  }, [svc]);

  const updateRow = (i: number, patch: Partial<RowInput>) => {
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  };
  const removeRow = (i: number) => {
    setRows((rs) => (rs.length <= 1 ? rs : rs.filter((_, j) => j !== i))); // 仅剩 1 行不可删（B5）
  };
  const reset = () => {
    setRows([emptyRow("CLIENT")]);
    setLocked(false);
    setResult(null);
    setError(null);
    setNotice(null);
  };

  // 行与证件归一值成对（索引免 undefined：随 rows 派生）
  const rowPairs = useMemo(() => rows.map((row) => ({ row, idNorm: normalizeIdInput(row.idNumber) })), [rows]);

  // 统计条四格（E6）：有相关记录的主体 x/y、涉及历史案件数、涉及在办收案数、重点关注/高风险数
  const stats = useMemo(() => {
    if (!result) return null;
    const filled = rows.filter(rowHasInput);
    let subjectsWithHits = 0;
    let critical = 0;
    const seenMatters = new Set<string>();
    const seenIntakes = new Set<string>();
    for (const { row: q, idNorm } of rowPairs) {
      if (!rowHasInput(q)) continue;
      const mine = hitsOfQuery(q, idNorm, result.hits);
      if (mine.length > 0) subjectsWithHits += 1;
      for (const h of mine) {
        // 案件/收案按目标 id 去重（E6 语义=涉及案件数，同一案的多条命中只计一案）
        if (h.hitType === "HISTORICAL_PARTY" && h.targetId) seenMatters.add(h.targetId);
        if (h.hitType === "IN_PROGRESS_INTAKE" && h.targetId) seenIntakes.add(h.targetId);
      }
    }
    const historical = seenMatters.size;
    const inProgress = seenIntakes.size;
    for (const h of result.hits) {
      if (SEVERITY_RANK[h.severity] >= SEVERITY_RANK.HIGH) critical += 1;
    }
    return { total: filled.length, subjectsWithHits, historical, inProgress, critical };
  }, [result, rowPairs]);

  // 按主体分组（E6）：每个有输入的主体一组；命中卡按目标合并取最高严重度染卡
  const groups = useMemo(() => {
    if (!result) return [];
    const hitTargets: Array<{ hit: ConflictHitProto; top: ConflictSeverity; hits: ConflictHitProto[] }> = [];
    const byTarget = new Map<string, { hit: ConflictHitProto; top: ConflictSeverity; hits: ConflictHitProto[] }>();
    for (const h of result.hits) {
      const key = `${h.targetType}\u0000${h.targetId ?? ""}\u0000${h.matchedName}`;
      const cur = byTarget.get(key);
      if (cur) {
        cur.hits.push(h);
        if (SEVERITY_RANK[h.severity] > SEVERITY_RANK[cur.top]) cur.top = h.severity;
      } else {
        const entry = { hit: h, top: h.severity, hits: [h] };
        byTarget.set(key, entry);
        hitTargets.push(entry);
      }
    }
    hitTargets.sort((a, b) => SEVERITY_RANK[b.top] - SEVERITY_RANK[a.top]);
    return rowPairs.map(({ row, idNorm }) => ({
      row, idNorm,
      hits: hitsOfQuery(row, idNorm, result.hits),
    })).map((g) => ({
      ...g,
      // 目标卡归属：以目标条目的首个命中归属主体（同名多主体极端场景卡归首主体，染卡取组内最高）
      targets: hitTargets.filter((t) => g.hits.includes(t.hit)),
    }));
  }, [result, rowPairs]);

  const noHitSubjects = useMemo(() => {
    if (!result) return [];
    return rowPairs.map(({ row, idNorm }) => ({ row, idNorm, mine: hitsOfQuery(row, idNorm, result.hits) }))
      .filter((g) => rowHasInput(g.row) && g.mine.length === 0);
  }, [result, rowPairs]);

  if (!svc.conflictRun) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <p className="text-ui-sm text-foreground-subtle">桥面未提供冲突预检通道（conflictRun 不可用），预检面停用。</p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 gap-4 overflow-auto p-4" data-testid="conflict-precheck-panel">
      {/* 主列：说明+主体行+结果 */}
      <div className="flex min-w-0 flex-1 flex-col gap-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="flex items-center gap-2 text-ui-xl font-semibold">
              <ScanSearch className="size-5" /> 冲突预检
            </h1>
            <p className="text-ui-caption text-foreground-subtle">
              收案前查一查所内登记记录有没有相关主体。预检只作了解情况，不出结论；正式结论在案件冲突复核中给出。
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {locked ? (
              <>
                <Button variant="outline" size="sm" onClick={() => setLocked(false)} data-testid="conflict-edit-rows">
                  <Pencil className="size-4" /> 修改
                </Button>
                <Button variant="outline" size="sm" onClick={reset} data-testid="conflict-new-precheck">
                  <RotateCcw className="size-4" /> 新建预检
                </Button>
              </>
            ) : null}
          </div>
        </div>

        {/* 主体行（B1/B4/B5/B6） */}
        <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
          {rows.map((row, i) => (
            <div key={i} className="flex items-center gap-2" data-testid={`conflict-row-${i}`}>
              <div className="flex shrink-0 overflow-hidden rounded-md border border-border" data-testid={`conflict-role-${i}`}>
                {INPUT_ROLES.map((role) => (
                  <button
                    key={role}
                    type="button"
                    disabled={locked}
                    aria-pressed={row.role === role}
                    onClick={() => updateRow(i, { role })}
                    className={`px-2 py-1 text-ui-caption ${row.role === role
                      ? "bg-selected text-foreground"
                      : "text-foreground-subtle hover:bg-subtle"}`}
                  >
                    {ROLE_INPUT_LABEL[role]}
                  </button>
                ))}
              </div>
              <Input
                value={row.name}
                disabled={locked}
                maxLength={120}
                placeholder="主体名称（选填）"
                className="min-w-0 flex-1"
                onChange={(e) => updateRow(i, { name: e.target.value })}
                onKeyDown={(e) => { if (e.key === "Enter") void run(rows); }}
                data-testid={`conflict-name-${i}`}
              />
              <Input
                value={row.idNumber}
                disabled={locked}
                maxLength={50}
                placeholder="证件号 / 统一社会信用代码（选填，精确比对）"
                className="min-w-0 flex-1 font-mono"
                onChange={(e) => updateRow(i, { idNumber: normalizeIdInput(e.target.value) })}
                onKeyDown={(e) => { if (e.key === "Enter") void run(rows); }}
                data-testid={`conflict-id-${i}`}
              />
              <Button
                variant="ghost" size="sm" disabled={locked || rows.length <= 1}
                onClick={() => removeRow(i)} aria-label="移除该主体"
                data-testid={`conflict-remove-${i}`}
              >
                <Trash2 className="size-4" />
              </Button>
            </div>
          ))}
          <div className="flex items-center gap-2">
            <Button
              variant="outline" size="sm" disabled={locked}
              onClick={() => setRows((rs) => [...rs, emptyRow("OPPOSING_PARTY")])} // A8 新行默认对方
              data-testid="conflict-add-row"
            >
              <Plus className="size-4" /> 添加主体
            </Button>
            <Button
              size="sm" disabled={searching || locked}
              onClick={() => void run(rows)}
              data-testid="conflict-run"
            >
              {searching
                ? <span className="inline-block size-3 animate-spin rounded-full border-2 border-current border-t-transparent" aria-label="检索中" />
                : <FileSearch className="size-4" />}
              {locked ? "重新预检" : "开始预检"}
            </Button>
            {locked ? <Lock className="size-3 text-foreground-subtle" aria-label="主体行已锁定" /> : null}
          </div>
          {error ? <p className="text-ui-sm text-red-500" data-testid="conflict-error">{error}</p> : null}
          {notice ? <p className="text-ui-sm text-emerald-600 dark:text-emerald-400" data-testid="conflict-notice">{notice}</p> : null}
        </div>

        {/* 空态（E8）：未检索占位卡 */}
        {!result ? (
          <div
            className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border p-10 text-center"
            data-testid="conflict-empty-state"
          >
            <ScanSearch className="size-6 text-foreground-subtle" />
            <p className="text-ui-sm font-medium">填写主体后开始预检</p>
            <p className="max-w-md text-ui-caption text-foreground-subtle">
              名称与证件号至少填一项；可添加多个主体一次查完。预检不做结论，只提示所内登记记录中的相关主体。
            </p>
          </div>
        ) : (
          <>
            {/* 四格统计条（E6） */}
            {stats ? (
              <div className="grid grid-cols-4 gap-2" data-testid="conflict-stats">
                {[
                  { label: "有相关记录的主体", value: `${stats.subjectsWithHits}/${stats.total}` },
                  { label: "涉及历史案件", value: String(stats.historical) },
                  { label: "涉及在办收案", value: String(stats.inProgress) },
                  { label: "重点关注/高风险命中", value: String(stats.critical) },
                ].map((cell) => (
                  <div key={cell.label} className="rounded-lg border border-border p-2 text-center">
                    <div className="text-ui-lg font-semibold" data-testid={`conflict-stat-${cell.label}`}>{cell.value}</div>
                    <div className="text-ui-caption text-foreground-subtle">{cell.label}</div>
                  </div>
                ))}
              </div>
            ) : null}

            {/* 按主体分组的命中区（E6）——预检页命中卡不渲染 reason 文字（E4） */}
            {groups.filter((g) => g.hits.length > 0).map((g, gi) => (
              <div key={gi} className="flex flex-col gap-2" data-testid={`conflict-subject-group-${gi}`}>
                <div className="flex items-center gap-2 text-ui-sm font-medium">
                  <span className="rounded-md bg-subtle px-2 py-0.5 text-ui-caption">{ROLE_INPUT_LABEL[g.row.role]}</span>
                  <span>{g.row.name.trim() || "（未填名称）"}</span>
                  {g.idNorm ? <span className="font-mono text-ui-caption text-foreground-subtle">{g.idNorm}</span> : null}
                  <span className="text-ui-caption text-foreground-subtle">· {g.hits.length} 条相关记录</span>
                </div>
                {g.targets.map((t, ti) => (
                  <div key={ti} className={`rounded-lg border p-3 ${t.top === "BLOCKING" || t.top === "HIGH" ? "border-red-300 dark:border-red-900" : "border-border"}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded px-1.5 py-0.5 text-ui-caption font-medium ${TONE_CLS[SEVERITY_TONE[t.top]] ?? ""}`}>
                        {SEVERITY_LABEL[t.top]}
                      </span>
                      <span className="text-ui-sm font-medium">{t.hit.matchedName}</span>
                      {t.hits.map((h) => (
                        <span key={h.id} className="rounded bg-subtle px-1.5 py-0.5 text-ui-caption">
                          {MATCH_KIND_LABEL[matchKindOf(h)]}
                        </span>
                      ))}
                      <span className="text-ui-caption text-foreground-subtle">
                        登记身份：{HIT_ROLE_LABEL[t.hit.storedRole]}{t.hit.storedStanding ? ` · ${t.hit.storedStanding}` : ""}
                      </span>
                      {t.hit.matchedField === "name" && t.hit.matchedRatio < 1 ? (
                        <span className="text-ui-caption text-foreground-subtle">相似度 {Math.round(t.hit.matchedRatio * 100)}%</span>
                      ) : null}
                    </div>
                    {t.hit.brief ? (
                      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-ui-caption text-foreground-subtle md:grid-cols-4">
                        {t.hit.brief.caseNo ? <span>案号：{t.hit.brief.caseNo}</span> : null}
                        {t.hit.brief.name ? <span>案件：{t.hit.brief.name}</span> : null}
                        {t.hit.brief.cause ? <span>案由：{t.hit.brief.cause}</span> : null}
                        {t.hit.brief.status ? <span>状态：{t.hit.brief.status}</span> : null}
                      </div>
                    ) : null}
                    {t.hit.targetType === "matter" && t.hit.targetId && onViewMatter ? (
                      <Button variant="ghost" size="sm" className="mt-1" onClick={onViewMatter} data-testid={`conflict-view-matter-${ti}`}>
                        <Eye className="size-4" /> 查看案件
                      </Button>
                    ) : null}
                  </div>
                ))}
              </div>
            ))}

            {/* 未命中主体单列区+免责声明（E7） */}
            {noHitSubjects.length > 0 ? (
              <div className="rounded-lg border border-border p-3" data-testid="conflict-no-hit-zone">
                <p className="text-ui-sm font-medium">未发现相关记录的主体</p>
                <ul className="mt-1 list-inside list-disc text-ui-caption text-foreground-subtle">
                  {noHitSubjects.map((g, i) => (
                    <li key={i}>{g.row.name.trim() || g.idNorm}</li>
                  ))}
                </ul>
                <p className="mt-2 text-ui-caption text-foreground-subtle">
                  「未发现」仅表示所内登记记录中没有匹配，不等于确认无冲突：别名、关联企业、未录入系统的代理关系仍需自行核实。正式收案时将重新检索。
                </p>
              </div>
            ) : null}
            {result.hits.length === 0 ? (
              <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-ui-sm text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" data-testid="conflict-zero-hit-card">
                未发现相关记录（不等于确认无冲突）：别名、关联企业、未录入系统的代理关系仍需自行核实。
              </div>
            ) : null}
          </>
        )}
      </div>

      {/* 侧栏：本次预检小结+披露口径（E9/E4） */}
      <aside className="flex w-64 shrink-0 flex-col gap-3">
        <div className="rounded-lg border border-border p-3" data-testid="conflict-summary-card">
          <p className="text-ui-sm font-medium">本次预检</p>
          {result ? (
            <dl className="mt-2 space-y-1 text-ui-caption text-foreground-subtle">
              <div className="flex justify-between"><dt>检索主体</dt><dd data-testid="conflict-summary-subjects">{rows.filter(rowHasInput).length} 个</dd></div>
              <div className="flex justify-between"><dt>填写证件</dt><dd>{rows.filter((r) => normalizeIdInput(r.idNumber)).length} 个</dd></div>
              <div className="flex justify-between"><dt>相关记录</dt><dd data-testid="conflict-summary-hits">{result.hits.length} 条</dd></div>
              <div className="flex justify-between"><dt>预检时间</dt><dd>{result.checkedAt.slice(0, 19).replace("T", " ")}</dd></div>
            </dl>
          ) : (
            <p className="mt-2 text-ui-caption text-foreground-subtle">尚未开始预检</p>
          )}
        </div>
        <div className="rounded-lg border border-border p-3 text-ui-caption text-foreground-subtle">
          <p className="text-ui-sm font-medium text-foreground">披露口径</p>
          <p className="mt-1">命中仅展示编号、名称、案由、状态与登记身份等最小信息；案件正文与材料不因预检开放。每次预检均写入审计日志。</p>
          <p className="mt-1">严重度标签为业务语言的风险提示，不是结论；命中后请人工核对并留存依据。</p>
        </div>
      </aside>
    </div>
  );
}
