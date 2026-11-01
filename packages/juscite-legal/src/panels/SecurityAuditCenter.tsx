// 功能 #30 安全审计中心（RE-30 §3.6/§3.7 等量自绘，文案自写）：全屏遮罩弹窗（遮罩点击关+×关，
// role=dialog/aria-modal/aria-label）；链徽章三态（校验中灰/链完整绿/链异常红）数据=打开时
// audit.list 一次返回的 chainOk，错误出口不触 chainOk（徽章等量停留灰态，不转红）；摘要四卡；
// 三筛选 tab（切换改过滤+清选中）；双栏（左列表右详情）；详情有效行回退链
// m = 过滤集.find(id===selectedId) ?? 过滤集[0] ?? null——占位仅在过滤集为空时可达。
// 条件挂载（App 层 openToken>0 才挂载）：卸载即销毁全部组件态，重开=全新拉取（对拍 55/56）；
// 无轮询无手动重验（对拍 7），打开期间新写入行不可见（对拍 57）。
// 【#21 安全层】增补「工具决策」tab（RE-21 增补 §3.1：RE-30 面板扩展过滤 tab 复用 tool_audits
// 专表，迁移 0021 在物）：数据=挂载时 toolAuditsList 一次往返（缺省=跨会话最近 ≤200 倒序），
// 专表专视图不混排 audit_log 三 tab；查询通道不可用如实降级，不伪装空账。
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronRight, Shield, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { useServices } from "../ui-kit.js";
import {
  AUDIT_POLICY_VERSION, REDACTION_RULE_CATALOG, formatAuditTime, hitChipsOf, hitLinesOf,
  opsDetailSummary, privacyDetailOf, scenarioKeyOf, scenarioName, selectEffectiveRow,
  totalHitsOf, truncateDigest,
  type AuditRow, type PrivacyRedactionDetail,
} from "./securityAuditModel.js";
import {
  TOOL_DECISIONS_EMPTY_TEXT, TOOL_DECISIONS_UNAVAILABLE_TEXT,
  auditRowsForTab, effectMetaOf, reasonCodeLabel, selectEffectiveToolDecision,
  toToolDecisionRows, toolRowsForTab, userDecisionLabel,
  type SecurityAuditTab, type ToolDecisionRow,
} from "./toolSecurityModel.js";

/** 跨组件触发总线：侧栏入口与设置安全节导流卡都发同一事件，App 层消费（关设置 tab→令牌+1）。 */
export const SECURITY_AUDIT_EVENT = "juscite:security-audit:open";
export function requestSecurityAuditCenter() {
  window.dispatchEvent(new CustomEvent(SECURITY_AUDIT_EVENT));
}

const BADGE_STATES = {
  checking: { cls: "bg-[#787f8a1a] text-[#6d737c]", label: "链校验中" },
  ok: { cls: "bg-[#1d9e571a] text-[#177a44]", label: "链校验通过" },
  bad: { cls: "bg-[#d0453e1a] text-[#b23c36]", label: "链校验异常" },
} as const;

// 链校验徽章（RE-30 §2.2 三态三色胶囊+盾形小图标；错误路径保持 checking 灰态）
function ChainBadge({ chainOk }: { chainOk: boolean | null }) {
  const state = chainOk === null ? BADGE_STATES.checking : chainOk ? BADGE_STATES.ok : BADGE_STATES.bad;
  return (
    <span
      data-testid="audit-chain-badge"
      data-state={chainOk === null ? "checking" : chainOk ? "ok" : "bad"}
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${state.cls}`}
    >
      {chainOk === null ? (
        <Shield className="size-3.5" aria-hidden />
      ) : chainOk ? (
        <ShieldCheck className="size-3.5" aria-hidden />
      ) : (
        <ShieldAlert className="size-3.5" aria-hidden />
      )}
      {state.label}
    </span>
  );
}

function SummaryCard(props: { testId: string; label: string; value: string; note: string }) {
  return (
    <div data-testid={props.testId} className="rounded-lg border border-border/60 p-3">
      <div className="text-ui-caption text-foreground-subtle">{props.label}</div>
      <div className="mt-1 text-lg font-semibold text-foreground">{props.value}</div>
      <div className="mt-0.5 text-ui-caption text-foreground-subtle">{props.note}</div>
    </div>
  );
}

// 行类型徽章：出站脱敏（青）/操作（灰）双色
function RowKindBadge({ isPrivacy }: { isPrivacy: boolean }) {
  return isPrivacy ? (
    <span className="inline-flex shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium bg-[#1d9e571a] text-[#177a44]">
      出站脱敏
    </span>
  ) : (
    <span className="inline-flex shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium bg-foreground/8 text-foreground-subtle">
      操作
    </span>
  );
}

function rowTitle(row: AuditRow, privacy: PrivacyRedactionDetail | null): string {
  if (privacy) return scenarioName(scenarioKeyOf(privacy.requestId, privacy.scenario));
  return row.action || "（无动作）";
}

function DetailField(props: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-ui-caption text-foreground-subtle">{props.label}</div>
      <div className="mt-0.5 break-words text-ui-sm text-foreground">{props.children}</div>
    </div>
  );
}

// 详情栏——工具决策行（RE-21 增补 §3.3 十一字段面板化：决定徽章+六字段栅格+原因+
// 参数摘要+凭证红线说明。deny 与用户拒绝一样全量在账——被拒的调用正是复盘要看的事件）。
function ToolDecisionDetail({ row }: { row: ToolDecisionRow }) {
  const meta = effectMetaOf(row.effect);
  return (
    <div className="space-y-4" data-testid="audit-detail-tool">
      <div>
        <div className="text-ui-caption font-semibold tracking-wide text-foreground-subtle">工具决策详情</div>
        <div className="mt-1 flex items-center gap-2">
          <h3 className="min-w-0 break-all text-base font-semibold text-foreground">
            {row.toolName || "（未知工具）"}
          </h3>
          <span
            data-testid="audit-detail-tool-effect"
            className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${meta.cls}`}
          >
            {meta.label}
          </span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <DetailField label="原因码">{reasonCodeLabel(row.code)}</DetailField>
        <DetailField label="策略版本">{String(row.policyVersion)}</DetailField>
        <DetailField label="用户决定">{userDecisionLabel(row.userDecision)}</DetailField>
        <DetailField label="发生时间">{formatAuditTime(row.createdAt)}</DetailField>
        <DetailField label="会话">{row.conversationId || "未记录"}</DetailField>
        <DetailField label="运行">{row.runId || "—"}</DetailField>
      </div>
      <DetailField label="给人看的原因">{row.reason || "—"}</DetailField>
      <div className="rounded-lg border border-border/60 p-3">
        <div className="text-ui-sm font-medium text-foreground">参数摘要</div>
        <p
          className="mt-1 break-all font-mono text-ui-caption leading-relaxed text-foreground-subtle"
          data-testid="audit-detail-tool-args"
        >
          {row.argsSummary || "（无参数）"}
        </p>
        <p className="mt-2 text-ui-caption text-foreground-subtle">
          参数摘要中形似凭据的键值已整串替换为「[已隐藏]」——掩码前缀也不保留；台账不保存完整参数。
        </p>
      </div>
    </div>
  );
}

// 详情栏——出站脱敏行（RE-30 §2.7：状态徽章+六字段栅格+命中规则列表+原文不保存说明+技术栅格）
function PrivacyDetail({ row, detail }: { row: AuditRow; detail: PrivacyRedactionDetail }) {
  const status = detail.status ?? "success";
  const statusLabel = status === "success" ? "已完成" : status === "error" ? "出错" : "已中止";
  const statusCls =
    status === "success"
      ? "bg-[#1d9e571a] text-[#177a44]"
      : status === "error"
        ? "bg-[#d0453e1a] text-[#b23c36]"
        : "bg-[#787f8a1a] text-[#6d737c]";
  const lines = hitLinesOf(detail.counts);
  const digest = truncateDigest(detail.payloadDigest);
  return (
    <div className="space-y-4" data-testid="audit-detail-privacy">
      <div>
        <div className="text-ui-caption font-semibold tracking-wide text-foreground-subtle">出站脱敏详情</div>
        <div className="mt-1 flex items-center gap-2">
          <h3 className="text-base font-semibold text-foreground">
            {scenarioName(scenarioKeyOf(detail.requestId, detail.scenario))}
          </h3>
          <span data-testid="audit-detail-status" className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusCls}`}>
            {statusLabel}
          </span>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <DetailField label="对象">{row.target || "未记录"}</DetailField>
        <DetailField label="发生时间">{row.ts || "未记录"}</DetailField>
        <DetailField label="模型渠道">{detail.provider || "未记录"}</DetailField>
        <DetailField label="模型">{detail.model || "未记录"}</DetailField>
        <DetailField label="处理字符">
          {`${detail.originalChars ?? 0} → ${detail.outboundChars ?? 0}`}
        </DetailField>
        <DetailField label="工具调用">{`${detail.toolCalls ?? 0} 次`}</DetailField>
      </div>
      <div className="rounded-lg border border-border/60 p-3" data-testid="audit-detail-hits">
        <div className="text-ui-sm font-medium text-foreground">
          本次脱敏命中：{lines.reduce((n, l) => n + l.count, 0)} 处
        </div>
        {lines.length ? (
          <ul className="mt-2 space-y-1.5">
            {lines.map((l) => (
              <li key={l.id} className="text-ui-caption text-foreground-subtle">
                <span className="font-medium text-foreground">{l.count}×</span> {l.name} — {l.description}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-ui-caption text-foreground-subtle">
            本次请求经隐私网关处理，未命中任何敏感项。
          </p>
        )}
      </div>
      <p className="rounded-lg bg-muted/40 p-3 text-ui-caption leading-relaxed text-foreground-subtle" data-testid="audit-detail-privacy-note">
        为什么看不到被替换的原文：审计只记录命中的类别与数量，不保存任何原值——避免这份台账变成第二份敏感数据。
      </p>
      <div className="grid grid-cols-2 gap-3 border-t border-border/60 pt-3">
        <DetailField label="规则版本">{detail.policyVersion || "—"}</DetailField>
        <DetailField label="安全摘要">
          {digest ? (
            <span title={detail.payloadDigest} className="font-mono">{digest}</span>
          ) : (
            "—"
          )}
        </DetailField>
        {detail.errorCode ? <DetailField label="错误代码">{detail.errorCode}</DetailField> : null}
      </div>
    </div>
  );
}

// 详情栏——本地操作行（RE-30 §2.8：操作人/发生时间/对象/补充信息四字段）
function OpsDetail({ row }: { row: AuditRow }) {
  return (
    <div className="space-y-4" data-testid="audit-detail-ops">
      <div>
        <div className="text-ui-caption font-semibold tracking-wide text-foreground-subtle">本地操作详情</div>
        <h3 className="mt-1 break-all text-base font-semibold text-foreground">{row.action || "（无动作）"}</h3>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <DetailField label="操作人">{row.actor || "未记录"}</DetailField>
        <DetailField label="发生时间">{formatAuditTime(row.ts)}</DetailField>
        <DetailField label="对象">{row.target || "未记录"}</DetailField>
        <DetailField label="补充信息">{typeof row.detail === "string" && row.detail.trim() ? row.detail : "无"}</DetailField>
      </div>
    </div>
  );
}

function SecurityAuditPanel({ onClose }: { onClose: () => void }) {
  const { zcodeAgentService } = useServices();
  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState<AuditRow[] | null>(null);
  const [chainOk, setChainOk] = useState<boolean | null>(null); // null=校验在途（徽章灰态）
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<SecurityAuditTab>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rulesOpen, setRulesOpen] = useState(false);
  // 工具决策（tool_audits 专表）：null=查询通道不可用（如实降级，与空账区分）
  const [toolRows, setToolRows] = useState<ToolDecisionRow[] | null>(null);
  const [toolsLoading, setToolsLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    zcodeAgentService
      .auditList?.()
      .then((res) => {
        if (!alive) return;
        const list: AuditRow[] = Array.isArray(res?.rows) ? res.rows : [];
        setRows(list);
        setChainOk(res?.chainOk === true);
        // 挂载自动选中（对拍 53）：首个出站脱敏行优先，否则首行
        setSelectedId(list.find((r) => privacyDetailOf(r))?.id ?? list[0]?.id ?? null);
        setLoading(false);
      })
      .catch((e: unknown) => {
        // 错误出口只置错误信息，不触 chainOk（RE-30 §2.2/§3.7：徽章等量停留灰态，勿转红）
        if (alive) {
          setError(String((e as Error)?.message ?? e));
          setLoading(false);
        }
      });
    // 【#21 安全层】工具决策一次往返：缺省（无 conversationId）=跨会话最近 ≤200 倒序；
    // 失败只降级本 tab（工具决策查询不可用），不触 audit_log 三 tab 的错误出口。
    zcodeAgentService
      .toolAuditsList?.()
      .then((res) => {
        if (!alive) return;
        setToolRows(toToolDecisionRows(res?.rows));
        setToolsLoading(false);
      })
      .catch(() => {
        if (alive) {
          setToolRows(null);
          setToolsLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [zcodeAgentService]);

  const privacyCount = useMemo(() => (rows ?? []).filter((r) => privacyDetailOf(r)).length, [rows]);
  const tools = toolRows ?? [];
  const toolsFiltered = useMemo(() => toolRowsForTab(tab, tools), [tab, tools]);
  const filtered = useMemo(() => {
    if (tab === "tools") return []; // 工具决策专表专视图：audit_log 三 tab 语义不变，互不混排
    const list = rows ?? [];
    if (tab === "privacy") return list.filter((r) => privacyDetailOf(r));
    if (tab === "ops") return list.filter((r) => !privacyDetailOf(r));
    return list;
  }, [rows, tab]);
  // 详情有效行回退链（对拍 54）：清选/切 tab 后详情自动落回新过滤集首行，不出占位
  const m = selectEffectiveRow(filtered, selectedId);
  const mPrivacy = m ? privacyDetailOf(m) : null;
  const mt = tab === "tools" ? selectEffectiveToolDecision(toolsFiltered, selectedId) : null;

  const switchTab = useCallback((next: SecurityAuditTab) => {
    setTab(next);
    setSelectedId(null); // 切 tab=改过滤+清选中（对拍 10）
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4"
      data-testid="audit-center-overlay"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="安全审计中心"
        data-testid="audit-center"
        className="flex h-full max-h-[720px] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-border bg-background shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部：眉题+标题+链徽章+副题 */}
        <div className="flex items-start justify-between gap-4 border-b border-border/60 px-5 py-4">
          <div>
            <div className="text-[11px] font-semibold tracking-[0.18em] text-foreground-subtle">AUDIT LOG</div>
            <div className="mt-0.5 flex items-center gap-2.5">
              <h2 className="text-lg font-semibold text-foreground">安全审计中心</h2>
              <ChainBadge chainOk={chainOk} />
            </div>
            <p className="mt-1 text-ui-caption text-foreground-subtle">
              记录每次 AI 出站的脱敏命中与本地关键操作；台账不保存敏感原文。
            </p>
          </div>
          <button
            type="button"
            aria-label="关闭安全审计中心"
            data-testid="audit-close"
            onClick={onClose}
            className="rounded p-1.5 text-foreground-subtle hover:bg-foreground/8 hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* 摘要四卡 */}
        <div className="grid grid-cols-2 gap-3 px-5 pt-4 md:grid-cols-4" aria-label="审计摘要">
          <SummaryCard testId="audit-card-total" label="记录总数" value={String(rows?.length ?? 0)} note="仅最近 200 条" />
          <SummaryCard testId="audit-card-privacy" label="出站脱敏请求" value={String(privacyCount)} note="含成功/出错/中止" />
          <SummaryCard testId="audit-card-hits" label="敏感项命中" value={String(totalHitsOf(rows ?? []))} note="按规则类目累计" />
          <SummaryCard
            testId="audit-card-policy"
            label="规则版本"
            value={AUDIT_POLICY_VERSION}
            note={`${REDACTION_RULE_CATALOG.length} 类规则`}
          />
        </div>

        {/* 工具行：四筛选 tab（带实时计数；tools=工具决策专表视图）+规则目录折叠 */}
        <div className="flex flex-wrap items-center gap-2 px-5 pt-4" role="tablist" aria-label="审计筛选">
          {(
            [
              { id: "all", label: "全部", count: rows?.length ?? 0, testId: "audit-tab-all" },
              { id: "privacy", label: "出站脱敏", count: privacyCount, testId: "audit-tab-privacy" },
              { id: "ops", label: "本地操作", count: (rows?.length ?? 0) - privacyCount, testId: "audit-tab-ops" },
              { id: "tools", label: "工具决策", count: tools.length, testId: "audit-tab-tools" },
            ] as Array<{ id: SecurityAuditTab; label: string; count: number; testId: string }>
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              data-testid={t.testId}
              onClick={() => switchTab(t.id)}
              className={`rounded-full px-3 py-1 text-ui-sm transition-colors ${
                tab === t.id
                  ? "bg-foreground text-background font-medium"
                  : "text-foreground-subtle hover:bg-foreground/8"
              }`}
            >
              {t.label} {t.count}
            </button>
          ))}
          <button
            type="button"
            data-testid="audit-rules-toggle"
            onClick={() => setRulesOpen((v) => !v)}
            className="ml-auto text-ui-sm text-foreground-subtle underline-offset-2 hover:text-foreground hover:underline"
          >
            {rulesOpen ? "收起规则目录" : "查看脱敏规则目录"}
          </button>
        </div>
        {rulesOpen ? (
          <ul className="mx-5 mt-2 grid grid-cols-1 gap-x-6 gap-y-1 rounded-lg border border-border/60 p-3 md:grid-cols-2" data-testid="audit-rules-list">
            {REDACTION_RULE_CATALOG.map((r) => (
              <li key={r.id} className="text-ui-caption text-foreground-subtle">
                <span className="font-medium text-foreground">{r.name}</span> — {r.description}
              </li>
            ))}
          </ul>
        ) : null}

        {/* 双栏工作区 */}
        <div className="flex min-h-0 flex-1 gap-3 px-5 pb-5 pt-3">
          {/* 左列表 */}
          <div className="flex min-h-0 w-[42%] flex-col rounded-lg border border-border/60">
            <div className="flex items-center justify-between border-b border-border/60 px-3 py-2 text-ui-caption text-foreground-subtle">
              <span>时间与事件</span>
              <span>对象 / 命中情况</span>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto" data-testid="audit-list">
              {tab === "tools" ? (
                // 【#21 安全层】工具决策行（tool_audits 专表；加载/不可用/空账三态如实分流）
                toolsLoading ? (
                  <p className="p-4 text-ui-sm text-foreground-subtle" data-testid="audit-tools-loading">工具决策加载中…</p>
                ) : toolRows === null ? (
                  <p className="p-4 text-ui-sm leading-relaxed text-foreground-subtle" data-testid="audit-tools-unavailable">
                    {TOOL_DECISIONS_UNAVAILABLE_TEXT}
                  </p>
                ) : toolsFiltered.length === 0 ? (
                  <p className="p-4 text-ui-sm leading-relaxed text-foreground-subtle" data-testid="audit-tools-empty">
                    {TOOL_DECISIONS_EMPTY_TEXT}
                  </p>
                ) : (
                  toolsFiltered.map((row) => {
                    const meta = effectMetaOf(row.effect);
                    const active = mt?.id === row.id;
                    return (
                      <button
                        key={row.id}
                        type="button"
                        data-testid={`audit-tool-row-${row.id}`}
                        data-tool-effect={row.effect}
                        onClick={() => setSelectedId(row.id)}
                        className={`block w-full border-b border-border/40 px-3 py-2 text-left transition-colors ${
                          active ? "bg-selected" : "hover:bg-foreground/5"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`inline-flex shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${meta.cls}`}>
                            {meta.label}
                          </span>
                          <span className="min-w-0 truncate text-ui-sm font-medium text-foreground">
                            {row.toolName || "（未知工具）"}
                          </span>
                        </div>
                        <div className="mt-0.5 text-ui-caption text-foreground-subtle">
                          {formatAuditTime(row.createdAt)} · {reasonCodeLabel(row.code)}
                          {row.userDecision ? ` · ${userDecisionLabel(row.userDecision)}` : ""}
                        </div>
                        <div className="mt-1 min-w-0">
                          <span className="truncate text-ui-caption text-foreground-subtle" title={row.reason}>
                            {row.reason || "—"}
                          </span>
                        </div>
                      </button>
                    );
                  })
                )
              ) : loading ? (
                <p className="p-4 text-ui-sm text-foreground-subtle" data-testid="audit-loading">审计记录加载中…</p>
              ) : error ? (
                <p className="p-4 text-ui-sm text-[#b23c36]" role="alert" data-testid="audit-error">加载审计记录失败：{error}</p>
              ) : filtered.length === 0 ? (
                tab === "privacy" ? (
                  <p className="p-4 text-ui-sm leading-relaxed text-foreground-subtle" data-testid="audit-empty-privacy">
                    还没有出站脱敏记录。完成一次对话、摘要、策略推演或文书任务并通过出站脱敏后，这里会出现命中明细。
                  </p>
                ) : (
                  <p className="p-4 text-ui-sm text-foreground-subtle" data-testid="audit-empty-generic">没有符合当前筛选的记录。</p>
                )
              ) : (
                filtered.map((row) => {
                  const privacy = privacyDetailOf(row);
                  const hits = privacy ? hitChipsOf(privacy.counts) : null;
                  const active = m?.id === row.id;
                  return (
                    <button
                      key={row.id}
                      type="button"
                      data-testid={`audit-row-${row.id}`}
                      data-row-kind={privacy ? "privacy" : "ops"}
                      onClick={() => setSelectedId(row.id)}
                      className={`block w-full border-b border-border/40 px-3 py-2 text-left transition-colors ${
                        active ? "bg-selected" : "hover:bg-foreground/5"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <RowKindBadge isPrivacy={Boolean(privacy)} />
                        <span className="min-w-0 truncate text-ui-sm font-medium text-foreground">{rowTitle(row, privacy)}</span>
                      </div>
                      <div className="mt-0.5 text-ui-caption text-foreground-subtle">
                        {formatAuditTime(row.ts)} · {row.actor || "未记录"}
                      </div>
                      <div className="mt-1 flex min-w-0 items-center gap-1.5 text-ui-caption">
                        <span className="max-w-[45%] truncate text-foreground-subtle" title={row.target ?? undefined}>
                          {row.target || "—"}
                        </span>
                        {hits ? (
                          hits.zero ? (
                            <span className="text-foreground-subtle">本次未命中敏感项</span>
                          ) : (
                            <>
                              {hits.chips.map((c) => (
                                <span key={c.name} className="rounded bg-foreground/8 px-1.5 py-0.5 text-[10px] text-foreground">
                                  {c.name} ×{c.count}
                                </span>
                              ))}
                              {hits.overflow > 0 ? (
                                <span className="text-foreground-subtle">+{hits.overflow} 类</span>
                              ) : null}
                            </>
                          )
                        ) : (
                          <span className="truncate text-foreground-subtle" title={row.detail ?? undefined}>
                            {opsDetailSummary(row)}
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
          {/* 右详情 */}
          <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-border/60 p-4" data-testid="audit-detail">
            {tab === "tools" ? (
              !toolsLoading && mt ? (
                <ToolDecisionDetail row={mt} />
              ) : (
                <p className="text-ui-sm text-foreground-subtle" data-testid="audit-detail-placeholder">
                  {toolsLoading ? "工具决策加载中…" : "当前没有可展示的工具决策。"}
                </p>
              )
            ) : !loading && !error && m ? (
              mPrivacy ? <PrivacyDetail row={m} detail={mPrivacy} /> : <OpsDetail row={m} />
            ) : (
              <p className="text-ui-sm text-foreground-subtle" data-testid="audit-detail-placeholder">
                {loading ? "审计记录加载中…" : error ? "—" : "当前筛选下没有可展示的记录。"}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// 门面（常驻挂载于 App）：openToken>0 才渲染面板；每次打开重新挂载=全新拉取（对拍 55），
// 选中 id 与 tab 不跨开关保留（初始 all+挂载自动选中，对拍 56）。
export function SecurityAuditCenter({ openToken }: { openToken: number }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (openToken > 0) setOpen(true);
  }, [openToken]);
  const close = useCallback(() => setOpen(false), []);
  if (!open) return null;
  return <SecurityAuditPanel onClose={close} />;
}

// 侧栏底部常驻入口（对拍 1：盾形图标+主文案+副文案+右箭头+悬浮说明；位置=账户区之下）
export function SecurityAuditSidebarEntry() {
  return (
    <button
      type="button"
      data-testid="audit-sidebar-entry"
      title="查看 AI 出站脱敏与本地操作留痕"
      onClick={() => requestSecurityAuditCenter()}
      className="flex w-full items-center gap-2 px-4 py-2 text-left hover:bg-foreground/8"
    >
      <Shield className="size-4 shrink-0 text-foreground-subtle" />
      <span className="min-w-0 flex-1">
        <span className="block text-ui-sm font-medium text-foreground">安全审计</span>
        <span className="block text-ui-caption text-foreground-subtle">脱敏与操作留痕</span>
      </span>
      <ChevronRight className="size-3.5 shrink-0 text-foreground-subtle" />
    </button>
  );
}
