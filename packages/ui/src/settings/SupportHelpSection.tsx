// 设置页·帮助与反馈分区之工单+诊断包两段（功能 #31 支持通道，RE-31 §3.2/§3.3/§3.4；产品指引段在
// HelpFeedbackSection 内，本文件只装后两段）。
// 双形态（RE-31 §3.4 差异裁决）：有 opsApi 配置=全自动上传（隐身闸在桥侧，§3.2）；无配置=降级形态
// 纯本地（工单 Markdown 落盘+剪贴板+打开文件夹；诊断包导出文件+复制），不受 #9 约束。
// 加固三处（对拍 31/32/35，§3.2）：①2xx 无 ticket_key 回执=按失败处理（红字+不清表单+不写键，不复刻
// 竞品 A14 假成功）；②提交/上传/导出 in-flight 禁用（不复刻 A15 连击）；③60s 前端兜底计时器（A18，
// 仅渲染层复位：先行到期置 stale→按钮复位，A19 分流=工单线红字含超时文案/诊断线静默仅复位，
// A20 迟到返回一律丢弃——不清表单不出字不刷新不写键）。导出走本地保存对话框（用户可控终点，无
// fetch 悬挂面），只享加固②禁用、不起 60s 计时器。
// B22/B25 等量：诊断组包/上传失败仅 console，UI 无提示（超时按 A19 亦静默）。
import { useCallback, useEffect, useRef, useState } from "react";
import { ClipboardCopy, FolderOpen, LifeBuoy, Send } from "lucide-react";
import { Button } from "@/components/ui/button.js";
import { Checkbox } from "@/components/ui/checkbox.js";
import { Input } from "@/components/ui/input.js";
import { Textarea } from "@/components/ui/textarea.js";
import { SettingsGroupCard } from "@/settings/SettingsPageParts.js";
import { useServices } from "@/hooks/useServices.js";
import { usePlatform } from "@/hooks/usePlatform.js";

// A3 等量（我方无账号，#26 同款链）：设置层称呼择先非空（profile.displayName/userName/displayName）
// → 默认「Juscite 用户」。称呼变即换 localStorage 桶（A16 等量，帮助文案标注已知限制）。
const DEFAULT_REQUESTER = "Juscite 用户";
const bucketKeyOf = (requester: string) => `juscite.supportTicketKey.${requester.trim()}`;
// E31 文件名同款 UTC 压缩时间戳（渲染层只为导出文件名生成，与桥侧格式一致）
const tsCompact = (d = new Date()) => d.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, (m) => m.slice(1));

// A8 清洗等量：剥错误文本前缀（invoke/serialization 加持的 "Error: " 等），红字只留正文。
function cleanErrorMessage(e: unknown): string {
  return String((e as Error)?.message ?? e)
    .replace(/^Error invoking remote method '[^']+':\s*/i, "")
    .replace(/^(Error|error):\s*/, "")
    .trim();
}

// A11 等量（对拍 11）：预填总线——触发点=许可卡激活失败行内「提交支持工单」入口（F78/F79 激活面
// 另单，RE-B3 §5 无 UI 面；本节挂监听消费预填，导航随触发点落码）。payload 只带主题与摘要正文，
// 不含许可文件本体与设备指纹（§3.5 信息边界同族）。
export const SUPPORT_TICKET_PREFILL_EVENT = "juscite:support-ticket:prefill";
export function requestSupportTicketPrefill(payload: { subject: string; description: string }) {
  window.dispatchEvent(new CustomEvent(SUPPORT_TICKET_PREFILL_EVENT, { detail: payload }));
}

// A18/A19/A20 共用兜底：in-flight 置忙 + 60s 计时器先行到期置 stale 并复位；迟到返回（resolve/reject）
// 按 stale 判据丢弃（不清表单、不出字、不刷新、不写键）。提示动作随各线错误语义分流（A19/A8）。
const FALLBACK_TIMEOUT_MS = 60_000;
function useStaleGuard() {
  const seq = useRef(0);
  const stale = useRef(false);
  const timer = useRef<number | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => () => { if (timer.current != null) window.clearTimeout(timer.current); }, []);
  const run = useCallback(async (
    work: () => Promise<void>,
    handlers: { onTimeout: () => void; onError?: (e: unknown) => void },
  ) => {
    const mine = ++seq.current;
    stale.current = false;
    setBusy(true);
    timer.current = window.setTimeout(() => {
      if (seq.current !== mine) return;
      stale.current = true; // A19：兜底计时器先行到期置 stale（不要求桥侧 fetch 真中止，A18）
      setBusy(false); // A18：按钮复位可重按（复位全路径一致）
      handlers.onTimeout(); // A19 分流：工单线红字含超时文案 / 诊断线静默仅复位
    }, FALLBACK_TIMEOUT_MS);
    try {
      await work();
    } catch (e) {
      if (seq.current !== mine || stale.current) return; // A20：迟到 reject 同样丢弃
      if (handlers.onError) handlers.onError(e); // A8：各线既有错误路径（工单红字/诊断仅日志）
      else throw e;
    } finally {
      if (seq.current === mine) {
        if (timer.current != null) { window.clearTimeout(timer.current); timer.current = null; }
        setBusy(false);
      }
    }
  }, []);
  const isStale = useCallback(() => stale.current, []);
  return { busy, run, isStale };
}

type RemoteRow = { status?: string; subject?: string; reply?: string };
type LocalRow = { fileName: string; createdAt: string; subject: string | null; path: string };

export function SupportHelpSection() {
  const { zcodeAgentService, settingService } = useServices();
  const platform = usePlatform();

  // 三态：undefined=解析中 | null=降级（无任何配置） | string=有配置远端
  const [opsApi, setOpsApi] = useState<string | null | undefined>(undefined);
  const [supportDir, setSupportDir] = useState<string>("");
  const [requester, setRequester] = useState<string>(DEFAULT_REQUESTER);

  // ── 工单表单/消息/列表 ──
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [msgPath, setMsgPath] = useState<string | null>(null); // E37：成功反馈附「打开所在文件夹」的目标
  const [clipboardNote, setClipboardNote] = useState<string | null>(null); // E34 剪贴板失败不阻断
  const [rows, setRows] = useState<RemoteRow[]>([]); // remote 列表（A2 无键不发请求=恒空渲染）
  const [localRows, setLocalRows] = useState<LocalRow[] | null>(null);
  const [localError, setLocalError] = useState<string | null>(null); // E38 枚举失败一次性提示
  const ticket = useStaleGuard();
  const ticketInFlight = ticket.busy;

  // ── 诊断包（B14 会话级勾选=组件内 useState，关设置即卸载复位） ──
  const [consent, setConsent] = useState(false);
  const [diagJson, setDiagJson] = useState<string | null>(null);
  const [diagExporting, setDiagExporting] = useState(false); // 加固②：导出 in-flight 禁用
  const [diagCopyNote, setDiagCopyNote] = useState<string | null>(null); // E34 等量（导出/复制线）
  const diagUpload = useStaleGuard();

  const isRemote = typeof opsApi === "string";
  const degraded = opsApi === null;

  // 挂载：目标解析 + 称呼链（A3）+ A11 预填监听
  useEffect(() => {
    let alive = true;
    zcodeAgentService.supportInfoGet?.()
      .then((info) => { if (alive) { setOpsApi(info.opsApi); setSupportDir(info.supportDir); } })
      .catch((e) => { console.error("[support] 目标解析失败（按降级呈现）", e); if (alive) setOpsApi(null); });
    settingService.get()
      .then((s: unknown) => {
        if (!alive) return;
        const p = s as { profile?: { displayName?: string }; userName?: string; displayName?: string };
        const name = p?.profile?.displayName?.trim() || p?.userName?.trim() || p?.displayName?.trim() || "";
        setRequester(name || DEFAULT_REQUESTER);
      })
      .catch(() => { /* 设置层称呼缺席 → 默认称呼（#26 同款空源路径） */ });
    const onPrefill = (ev: Event) => {
      if (!alive) return;
      const d = (ev as CustomEvent<{ subject?: string; description?: string }>).detail;
      if (!d) return;
      if (typeof d.subject === "string") setSubject(d.subject);
      if (typeof d.description === "string") setDescription(d.description);
      setMsg(null);
    };
    window.addEventListener(SUPPORT_TICKET_PREFILL_EVENT, onPrefill);
    return () => {
      alive = false;
      window.removeEventListener(SUPPORT_TICKET_PREFILL_EVENT, onPrefill);
    };
  }, [zcodeAgentService, settingService]);

  // A2/A17/E38：进分区拉列表——remote 有键才 GET（失败/非数组静默空仅日志）；降级=本地枚举（失败给提示）
  const refreshLists = useCallback(() => {
    const svc = zcodeAgentService.supportTicketList;
    if (!svc) return;
    if (degraded) {
      svc({ requester, ticketKey: "" }) // 降级线桥侧不消费 requester/ticketKey（E38 全域枚举）
        .then((res) => {
          setLocalRows(res?.localRows ?? []);
          setLocalError(res?.error ?? null);
        })
        .catch((e: unknown) => { setLocalRows([]); setLocalError(cleanErrorMessage(e)); });
      return;
    }
    if (!isRemote) return; // 解析中不拉
    const key = window.localStorage.getItem(bucketKeyOf(requester));
    if (!key) { setRows([]); return; } // A2：无键不发请求，列表保持空
    svc({ requester, ticketKey: key })
      .then((res) => { setRows(Array.isArray(res?.rows) ? res.rows : []); })
      .catch((e: unknown) => {
        console.error("[support] 工单列表拉取失败（静默空列表，A17 等量）", e);
        setRows([]);
      });
  }, [zcodeAgentService, degraded, isRemote, requester]);

  useEffect(() => { refreshLists(); }, [refreshLists]);

  // ── 提交工单（remote 上传 / 降级落盘）──
  const handleSubmit = useCallback(() => {
    if (ticketInFlight) return; // 加固②：in-flight 禁用（防连击，A15 不复刻）
    if (!subject.trim()) return; // A5：主题 trim 空 → 前端静默拦截（不发请求、无提示）
    setMsg(null); setMsgPath(null); setClipboardNote(null);
    const sentKey = window.localStorage.getItem(bucketKeyOf(requester)) ?? undefined; // A6：取本地存键
    void ticket.run(
      async () => {
        const res = await zcodeAgentService.supportTicketCreate?.({
          requester, subject: subject.trim(), content: description, ticketKey: sentKey,
        });
        if (ticket.isStale()) return; // A20：迟到返回一律丢弃
        if (!res) return;
        if (res.mode === "remote") {
          if (!res.responseTicketKey) { // 加固①：2xx 无 ticket_key 回执 → 按失败处理
            setMsg({ kind: "err", text: "提交失败：服务端未回执工单密钥，响应异常，请稍后重试。" });
            return;
          }
          window.localStorage.setItem(bucketKeyOf(requester), res.responseTicketKey); // A7 写回
          setSubject(""); setDescription(""); // A7 清表单
          setMsg({ kind: "ok", text: "工单已提交，客服会异步回复，答复见下方列表。" });
        } else {
          // 降级成功（E37）：写键（§3.5②，日后配置 opsApi 可凭同 key 关联）+清表单+反馈含完整路径
          window.localStorage.setItem(bucketKeyOf(requester), res.ticketKey);
          setSubject(""); setDescription("");
          setMsg({ kind: "ok", text: `工单已保存到本地：${res.path}；请把文件内容经支持邮箱或社区渠道发送给我们。` });
          setMsgPath(res.path ?? null);
          // 剪贴板复制独立执行（E33/E34）：失败不阻断、不掩盖落盘事实
          navigator.clipboard?.writeText(res.content ?? "").then(
            () => setClipboardNote(null),
            () => setClipboardNote("剪贴板复制失败：请打开工单文件手动复制内容后发送。"),
          );
        }
        refreshLists(); // A7：随后自动刷新列表
      },
      {
        // A19 分流：工单线超时=红字含超时文案区分
        onTimeout: () => setMsg({ kind: "err", text: "请求超时，请检查网络后重试。" }),
        // A8：非 2xx/网络失败 → 红字「提交失败：<清洗后错误>」，表单保留可重试
        onError: (e: unknown) => setMsg({ kind: "err", text: `提交失败：${cleanErrorMessage(e)}` }),
      },
    );
  }, [ticket, ticketInFlight, subject, description, requester, zcodeAgentService, refreshLists]);

  // ── 诊断包勾选（B21：勾选组包→预览；取消隐藏；重勾重组包） ──
  const handleConsent = useCallback((checked: boolean) => {
    setConsent(checked);
    if (!checked) { setDiagJson(null); return; }
    zcodeAgentService.supportDiagnosticsBuild?.()
      .then((res) => {
        setDiagJson(res.json);
        if (res.supportDir) setSupportDir(res.supportDir);
      })
      .catch((e: unknown) => {
        console.error("[support] 诊断包组包失败（仅日志，B22 等量）", e);
        setDiagJson(null); // 勾选已置、无预览（B22 形状）
      });
  }, [zcodeAgentService]);

  // ── 诊断包上传（remote）：成功清预览+复位勾选（B24）；失败仅 console（B25）；超时静默仅复位（A19） ──
  const handleDiagUpload = useCallback(() => {
    if (diagUpload.busy || !diagJson) return;
    void diagUpload.run(
      async () => {
        await zcodeAgentService.supportDiagnosticsUpload?.({ requester, payload: diagJson });
        if (diagUpload.isStale()) return; // A20：迟到返回一律丢弃
        setDiagJson(null); setConsent(false); // B24 等量
      },
      {
        // A19：诊断线超时与既有失败同走静默，用户可见变化仅按钮复位
        onTimeout: () => { /* 静默 */ },
        onError: (e: unknown) => console.error("[support] 诊断包上传失败（仅日志，B25 等量）", e),
      },
    );
  }, [diagUpload, diagJson, requester, zcodeAgentService]);

  // ── 诊断包导出（降级）：保存对话框默认落 support 目录；取消=静默保留（E35）；成功反馈含路径+复位（E37） ──
  const handleDiagExport = useCallback(async () => {
    if (diagExporting || !diagJson) return;
    const saveFile = platform.saveFile;
    if (!saveFile) { // Web 端无宿主保存面：退回剪贴板路径（E34 同型指引，不阻断）
      navigator.clipboard?.writeText(diagJson).then(
        () => setDiagCopyNote("已复制到剪贴板，请粘贴保存为 .json 文件。"),
        () => setDiagCopyNote("复制失败：预览区内容可全选手动复制保存。"),
      );
      return;
    }
    setDiagExporting(true);
    try {
      const bytes = new TextEncoder().encode(diagJson);
      const buf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
      const res = await saveFile({
        data: buf,
        suggestedName: `diagnostics-${tsCompact()}.json`,
        defaultDir: supportDir || undefined, // §3.4：默认落 %APPDATA%\Juscite\support
      });
      if (res.canceled) return; // E35：取消≠失败，静默保留预览与勾选
      if (!res.success || !res.path) {
        console.error("[support] 诊断包导出失败", res.error);
        setDiagCopyNote(`导出失败：${res.error ?? "未知错误"}`);
        return;
      }
      setDiagJson(null); setConsent(false); // E37：导出成功复位授权勾选（对拍 24 降级语义）
      setMsg({ kind: "ok", text: `诊断包已导出：${res.path}` });
      setMsgPath(res.path);
    } catch (e) {
      console.error("[support] 诊断包导出异常", e);
      setDiagCopyNote(`导出失败：${cleanErrorMessage(e)}`);
    } finally {
      setDiagExporting(false);
    }
  }, [diagExporting, diagJson, platform, supportDir]);

  const handleDiagCopy = useCallback(() => {
    if (!diagJson) return;
    navigator.clipboard?.writeText(diagJson).then(
      () => setDiagCopyNote(null),
      () => setDiagCopyNote("复制失败：预览区内容可全选手动复制。"),
    );
  }, [diagJson]);

  // E36：打开失败提示含路径文本供手动导航
  const openPath = useCallback(async (p: string) => {
    try {
      const res = await platform.openInFileManager(p);
      if (res?.success) return;
      setMsg({ kind: "err", text: `打开失败：${res?.error ?? "未知错误"}。请手动前往：${p}` });
    } catch (e) {
      setMsg({ kind: "err", text: `打开失败：${cleanErrorMessage(e)}。请手动前往：${p}` });
    }
  }, [platform]);

  return (
    <div className="space-y-6" data-testid="support-help-section">
      {/* ── 段 2：提交工单（RE-31 §3.3-2） ── */}
      <SettingsGroupCard>
        <div className="border-t border-border px-4 py-3 first:border-t-0" data-testid="support-ticket-segment">
          <div className="text-ui-base font-medium text-foreground">提交工单</div>
          <p className="mt-1 text-ui-base leading-6 text-foreground-subtle">
            {degraded
              ? "未配置远端支持平台：提交的工单会以 Markdown 文件保存在本机 support 目录并复制到剪贴板，请经支持邮箱或社区渠道发送。改称呼后看不到旧工单属预期（按称呼分桶；下方本地列表不受此限）。"
              : "描述你遇到的问题提交给客服，答复会显示在下方工单列表。改称呼后看不到旧工单属预期（按称呼分桶）。"}
          </p>
          <div className="mt-3 space-y-2" data-testid="support-ticket-form">
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="工单主题，例如：导出文书时提示失败"
              disabled={ticketInFlight}
              data-testid="support-subject"
              aria-label="工单主题（必填）"
            />
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="问题描述（可留空）"
              disabled={ticketInFlight}
              data-testid="support-description"
              aria-label="问题描述"
            />
            <div className="flex justify-end">
              <Button size="sm" onClick={handleSubmit} disabled={ticketInFlight} data-testid="support-submit">
                <Send className="mr-1 size-3.5" />
                {ticketInFlight ? "提交中…" : "提交工单"}
              </Button>
            </div>
            {msg ? (
              <div
                className={`text-ui-sm ${msg.kind === "ok" ? "text-[#177a44]" : "text-[#b23c36]"}`}
                data-testid={msg.kind === "ok" ? "support-msg-ok" : "support-msg-err"}
                role="status"
              >
                <span>{msg.text}</span>
                {msgPath && msg.kind === "ok" ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-2"
                    onClick={() => void openPath(msgPath)}
                    data-testid="support-open-folder"
                  >
                    <FolderOpen className="mr-1 size-3.5" />打开所在文件夹
                  </Button>
                ) : null}
              </div>
            ) : null}
            {clipboardNote ? (
              <p className="text-ui-sm text-foreground-subtle" data-testid="support-clipboard-note">{clipboardNote}</p>
            ) : null}
          </div>
          {/* 列表区（A9/E38）：空态不渲染列表块 */}
          {degraded ? (
            <div className="mt-3" data-testid="support-local-list">
              {localError ? (
                <p className="text-ui-sm text-[#b23c36]" data-testid="support-local-error">本地工单读取失败：{localError}</p>
              ) : null}
              {localRows != null && localRows.length === 0 && !localError ? (
                <p className="text-ui-sm text-foreground-subtle" data-testid="support-local-empty">暂无本地工单</p>
              ) : null}
              {localRows != null && localRows.length > 0 ? (
                <ul className="mt-1 space-y-1">
                  {localRows.map((r) => (
                    <li key={r.fileName}>
                      <button
                        type="button"
                        className="w-full truncate rounded px-2 py-1 text-left text-ui-sm text-foreground hover:bg-muted/60"
                        onClick={() => void openPath(r.path)}
                        data-testid="support-local-item"
                        title={r.path}
                      >
                        <LifeBuoy className="mr-1 inline size-3.5 text-foreground-subtle" />
                        {r.createdAt} {r.subject ?? "（主题缺失）"}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : rows.length > 0 ? (
            <ul className="mt-3 space-y-1" data-testid="support-remote-list">
              {rows.map((r, i) => (
                <li key={i} className="rounded px-2 py-1 text-ui-sm text-foreground" data-testid="support-remote-item">
                  [{r.status ?? "open"}] {r.subject ?? ""}
                  {r.reply ? ` —— 客服回复：${r.reply}` : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </SettingsGroupCard>

      {/* ── 段 3：诊断包（RE-31 §3.3-3） ── */}
      <SettingsGroupCard>
        <div className="border-t border-border px-4 py-3 first:border-t-0" data-testid="support-diagnostics-segment">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-ui-base font-medium text-foreground">诊断包</div>
              <p className="mt-1 text-ui-base leading-6 text-foreground-subtle">
                仅版本、平台与各数据面行数统计，不含案件内容与材料。勾选即表示你授权生成本包（会话级，关闭设置后复位）。
              </p>
            </div>
            <Checkbox
              checked={consent}
              onCheckedChange={(v) => handleConsent(v === true)}
              disabled={diagUpload.busy || diagExporting}
              data-testid="support-diagnostics-consent"
              aria-label="授权生成诊断包"
            />
          </div>
          {diagJson != null ? (
            <div className="mt-3 space-y-2" data-testid="support-diagnostics-panel">
              <Textarea
                readOnly
                rows={3}
                value={diagJson}
                data-testid="support-diagnostics-preview"
                aria-label="诊断包预览"
                className="font-mono text-ui-xs"
              />
              <div className="flex justify-end gap-2">
                {isRemote ? (
                  <Button size="sm" onClick={handleDiagUpload} disabled={diagUpload.busy} data-testid="support-diagnostics-upload">
                    {diagUpload.busy ? "上传中…" : "上传诊断包"}
                  </Button>
                ) : (
                  <>
                    <Button size="sm" variant="ghost" onClick={handleDiagCopy} disabled={diagExporting} data-testid="support-diagnostics-copy">
                      <ClipboardCopy className="mr-1 size-3.5" />复制到剪贴板
                    </Button>
                    <Button size="sm" onClick={() => void handleDiagExport()} disabled={diagExporting} data-testid="support-diagnostics-export">
                      {diagExporting ? "导出中…" : "导出诊断包文件"}
                    </Button>
                  </>
                )}
              </div>
              {diagCopyNote ? (
                <p className="text-ui-sm text-foreground-subtle" data-testid="support-diagnostics-note">{diagCopyNote}</p>
              ) : null}
            </div>
          ) : null}
        </div>
      </SettingsGroupCard>
    </div>
  );
}
