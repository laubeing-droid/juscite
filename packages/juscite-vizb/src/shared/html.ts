// 可视化 B 轨共享：HTML 报告防注入件（施工单-10 单元三；净室自写，机制学习零文本搬运）。
// 与 xml.ts 同一层的交付面共用件，给一切桥面/树内 HTML 产物（分享落地页、登录回调页、
// 后续报告页）三个统一承诺 +（逆向吸收波二·条 2 追加）声明式监控白名单契约面：
//  ① 动态文本只经 htmlEscape 进模板（或调用侧走 textContent——转义与 DOM 赋值二选一，不裸拼）；
//  ② URL 一律 sanitizeUrl 过 scheme 白名单（http/https；声明内嵌图片处按需最小放行 data:image）；
//  ③ 文档一律 safeHtmlDocument 出稿：CSP meta 以 default-src 'none' 起步、按产物实际资源面
//     最小放开；内联脚本/样式只带一次性 nonce；模板自身零内联事件属性（on*=禁止）。
// 边界面在此（HTML 出稿=外边界），调用侧互信：body 传入者负责其内动态文本已转义。

/** HTML 文本/属性值转义（五实体；属性值须在双引号语境使用）。 */
export function htmlEscape(s: string): string {
  return String(s).replace(/[&<>"']/gu, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" } as Record<string, string>
  )[c]!);
}

const URL_SCHEME_RE = /^[A-Za-z][A-Za-z0-9+.-]*:/;
// 内嵌图片最小放行：只认四类位图的完整 base64 串（svg+xml 不放行——SVG 可携带脚本）
const DATA_IMAGE_RE = /^data:image\/(?:png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+$/;

/**
 * URL scheme 白名单：http/https 放行；声明内嵌图片处可最小放行 data:image 位图；
 * 其余（javascript:/vbscript:/data:text/html…）一律 null=调用方不得写入 href/src。
 * 相对引用（含 #锚 / ?查询）放行=同源；协议相对 `//host` 拒（构建期不可证同源）。
 * 控制字符（浏览器在 URL 内会静默忽略 \t\n\r 等）先剥再判，防 `java\tscript:` 变体绕过。
 */
export function sanitizeUrl(raw: string, opts: { allowDataImage?: boolean } = {}): string | null {
  const u = String(raw)
    .replace(/^[\u0000-\u0020]+/u, "")
    .replace(/[\u0000-\u001f\u007f]/gu, "");
  if (u.startsWith("//")) return null;
  const m = URL_SCHEME_RE.exec(u);
  if (!m) return u; // 无 scheme=相对引用
  const scheme = m[0].toLowerCase();
  if (scheme === "http:" || scheme === "https:") return u;
  if (opts.allowDataImage && DATA_IMAGE_RE.test(u)) return u;
  return null;
}

const NONCE_RE = /^[A-Za-z0-9+/=]{22,}$/u; // CSP nonce=base64 至少 16 字节（22 字符起）

const DANGEROUS_HTML_TAG = "script|iframe|object|embed|noscript|noembed|svg|math|title|textarea|style|link|meta|base|form|foreignobject|annotation-xml";

/** 正文片段去可执行面：危险标签、内联事件、javascript/vbscript/data: URL。骨架标签保留。 */
function neutralizeHtmlFragment(html: string): string {
  let s = String(html ?? "");
  const paired = new RegExp(`<\\s*(${DANGEROUS_HTML_TAG})\\b[^>]*>[\\s\\S]*?<\\s*/\\s*\\1\\s*>`, "gi");
  for (let pass = 0; pass < 4; pass += 1) s = s.replace(paired, "");
  s = s.replace(new RegExp(`<\\s*/?\\s*(?:${DANGEROUS_HTML_TAG})\\b[^>]*>`, "gi"), "");
  s = s.replace(/\s+on[a-z0-9:-]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, "");
  s = s.replace(
    /\b(href|src|xlink:href|action|formaction)\s*=\s*(["'])\s*(?:javascript|vbscript|data)\s*:[^"']*\2/gi,
    "$1=$2#$2",
  );
  s = s.replace(/\b(href|src|xlink:href|action|formaction)\s*=\s*(?:javascript|vbscript|data)\s*:[^\s>]*/gi, "$1=\"#\"");
  return s;
}

function neutralizeStyle(css: string): string {
  return String(css).replace(/</g, "\\3c ");
}

function neutralizeScript(js: string): string {
  return String(js).replace(/<\s*\/\s*script/gi, "<\\/script");
}

/** CSP 图片来源闭集：'self' 或四类位图 data 子串（声明内嵌图片时按需最小放行）。 */
const IMG_SOURCE_RE = /^'(self)'$|^data:image\/(?:png|jpeg|gif|webp)$/;

export interface CspDirectives {
  /** 一次性 nonce（crypto.randomBytes(16).toString("base64") 每次出稿新生成）：
   *  script-src/style-src 都只认带该 nonce 的元素，模板因此无需 'unsafe-inline'。 */
  nonce?: string;
  /** 同源取数接线（fetch/XHR → connect-src 'self'）。 */
  connectSelf?: boolean;
  /** 图片来源闭集内取值，如 ["'self'"] 或声明内嵌图片时 ["'self'", "data:image/png"]。 */
  imgSources?: string[];
}

/** CSP meta 标签：default-src 'none' 起步，按产物实际资源面最小放开；指令序确定。
 *  指令串全部出自闭集词表（nonce/imgSources 入口已验），属性值只需断 `& < > "`，单引号
 *  是 CSP 语法的字面成分（'self'/'nonce-x'），转义会破坏策略本身。 */
export function cspMeta(o: CspDirectives = {}): string {
  const parts = ["default-src 'none'"];
  if (o.nonce !== undefined) {
    if (!NONCE_RE.test(o.nonce)) throw new Error(`CSP nonce 形状非法（须 base64 ≥16 字节）：${o.nonce.slice(0, 8)}…`);
    parts.push(`script-src 'nonce-${o.nonce}'`, `style-src 'nonce-${o.nonce}'`);
  }
  if (o.connectSelf) parts.push("connect-src 'self'");
  if (o.imgSources?.length) {
    for (const s of o.imgSources) {
      if (!IMG_SOURCE_RE.test(s)) throw new Error(`CSP img 来源不在闭集（'self'/data:image 位图）：${s}`);
    }
    parts.push(`img-src ${o.imgSources.join(" ")}`);
  }
  const attr = parts.join("; ").replace(/[&<>"]/gu, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);
  return `<meta http-equiv="Content-Security-Policy" content="${attr}">`;
}

export interface SafeDocOptions {
  /** 页题（模板内转义）。 */
  title: string;
  /** cspMeta() 的返回值（整标签）。 */
  csp: string;
  /** 正文 HTML——其中的动态文本必须先经 htmlEscape（调用方责任；模板只保证骨架）。 */
  body: string;
  /** 模板自有样式（只写模板常量；经 nonce 授权，与 csp 的 nonce 同值）。 */
  style?: string;
  /** 内联脚本：必须带 nonce，缺 nonce=拒绝出稿（fail-fast，不静默降级）。 */
  script?: { nonce: string; js: string };
  /** 声明式监控白名单（逆向吸收波二·条 2）：给定时模板内嵌声明+页内执法运行时
   *  （见 monitoringDeclaration/monitoringRuntimeJs）；需 nonce 授权。 */
  monitoring?: MonitoringOptions;
  /** 缺省 zh-CN。 */
  lang?: string;
}

/** 安全基模板（复用件）：CSP meta 置 head 首位；charset/viewport；样式与脚本只带 nonce；
 *  骨架零内联事件属性、零外联资源引用。 */
export function safeHtmlDocument(o: SafeDocOptions): string {
  if (o.script && !NONCE_RE.test(o.script.nonce)) {
    throw new Error(`内联脚本 nonce 形状非法（须 base64 ≥16 字节）：${String(o.script.nonce).slice(0, 8)}…`);
  }
  const nonce = o.script?.nonce ?? o.csp.match(/'nonce-([A-Za-z0-9+/=]+)'/)?.[1];
  if (o.script && !o.csp.includes(`'nonce-${o.script.nonce}'`)) {
    throw new Error("内联脚本 nonce 与 CSP 不一致——脚本会被自己的页面策略拦截，拒绝出稿");
  }
  if (o.style && !nonce) {
    throw new Error("内联样式缺 nonce 授权（cspDirectives.nonce 未给）——样式会被页面策略拦截，拒绝出稿");
  }
  if (o.monitoring && !nonce) {
    throw new Error("监控运行时缺 nonce 授权（cspDirectives.nonce 未给）——上报脚本会被页面策略拦截，拒绝出稿");
  }
  const monitoringBlock = o.monitoring
    ? `<script type="application/json" id="${MONITORING_DECL_ID}">${monitoringDeclaration(o.monitoring)}</script>\n`
      + `<script nonce="${nonce}">${neutralizeScript(monitoringRuntimeJs())}</script>\n`
    : "";
  return `<!doctype html>
<html lang="${htmlEscape(o.lang ?? "zh-CN")}"><head>
<meta charset="utf-8">
${o.csp}
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${htmlEscape(o.title)}</title>
${o.style ? `<style nonce="${nonce}">${neutralizeStyle(o.style)}</style>` : ""}
</head><body>
${monitoringBlock}${neutralizeHtmlFragment(o.body)}
${o.script ? `<script nonce="${o.script.nonce}">${neutralizeScript(o.script.js)}</script>` : ""}
</body></html>`;
}

// ── 声明式监控白名单契约（逆向吸收波二·条 2，2026-11-01 追加；净室自写）──
// 契约形状学习自 appifact 运行时契约样本（竞品情报 wesky820 仓实读，无许可仓——机制可学、
// 词表/枚举/文案零采用；形态等量非抄词表）：交互 HTML 内嵌声明式监控声明（key +
// monitoring{coreActions}），运行时上报只收声明内动作，结果三值，错误枚举闭集，
// 未声明动作丢弃并警告。
// 我方化对照注记（与样本的差异，均为有意）：
//  ① 上样本 alertChannel=Slack 频道（云告警接其内部健康体系）——我方默认零外呼红线：
//    无任何 alertChannel 云告警面；上报通道=本地（本地 console 日志恒记 + 同源本地桥
//    best-effort POST，失败静默不影响页面）。
//  ② 上样本 coreActions=18 个英文动词固定词表——我方词表按我方产品动作语义自拟（中文动作词）。
//  ③ 上样本 ERROR_TYPES=27 枚——我方按我方面上真实错误闭集自拟（9 枚，少而实）。
// 适用面登记（如实分档）：本契约只约束「HTML 宿主的交互页」（safeHtmlDocument 族 +
// office-bridge taskpane 静态页）；B 轨可视化 SVG 族（confrontation/render.ts、chronicle
// renderBrief.ts 等 SVG 交付件）与 Word/Excel 单文件 XML 交付件（shared/xml.ts）非 HTML
// 宿主、零脚本运行时 → 不适用，不硬套。

/** 内嵌声明数据块的 DOM id（monitoringRuntimeJs 与 taskpane/monitor.js 同约定）。 */
export const MONITORING_DECL_ID = "juscite-monitoring-declaration";

/** 监控动作词表（闭集；我方动作语义自拟——非抄任何外部词表）。 */
export const MONITORING_CORE_ACTIONS: readonly string[] = [
  "打开", "渲染", "保存", "编辑", "导出", "导入", "检索", "提交",
  "上传", "下载", "生成", "插入", "删除", "排序", "连接", "断开", "读取",
];

/** 上报结果三值（闭集）。 */
export const MONITORING_OUTCOMES: readonly string[] = ["成功", "失败", "中止"];

/** 错误枚举（闭集；我方真实错误面自拟，命名从桥错误码 snake_case 口径）。 */
export const MONITORING_ERROR_TYPES: readonly string[] = [
  "local_bridge_unavailable", // 本地桥不可达
  "local_bridge_timeout", // 本地桥无应答/超时
  "host_unsupported", // 宿主不支持该操作
  "invalid_argument", // 参数非法
  "parse_failed", // 解析失败
  "payload_too_large", // 载荷超限
  "storage_unavailable", // 本地存储不可用
  "permission_denied", // 权限拒绝
  "unknown_error", // 兜底
];

const MONITORING_KEY_RE = /^[a-z0-9][a-z0-9._-]{0,63}$/u;

export interface MonitoringOptions {
  /** 产物键（页面族标识；小写 ASCII 闭集形状）。 */
  key: string;
  /** 本页声明监控的动作（⊆ MONITORING_CORE_ACTIONS；构建期校验 fail-fast）。 */
  coreActions: readonly string[];
}

/** 声明式监控声明（JSON 文本，供 <script type="application/json"> 内嵌；
 *  `<` 转义为 \u003c 防 </script> 截断；outcomes/errorTypes 随声明内嵌=页内执法自包含）。 */
export function monitoringDeclaration(o: MonitoringOptions): string {
  if (!MONITORING_KEY_RE.test(o.key)) {
    throw new Error(`monitoring.key 形状非法（小写 ASCII ≤64 位）：${o.key.slice(0, 16)}`);
  }
  if (o.coreActions.length === 0) {
    throw new Error("monitoring.coreActions 不能为空（页面无监控面则不传 monitoring）");
  }
  const vocab = new Set(MONITORING_CORE_ACTIONS);
  const seen = new Set<string>();
  for (const a of o.coreActions) {
    if (!vocab.has(a)) throw new Error(`monitoring.coreActions 动作不在词表闭集：${a}`);
    if (seen.has(a)) throw new Error(`monitoring.coreActions 动作重复：${a}`);
    seen.add(a);
  }
  return JSON.stringify({
    key: o.key,
    monitoring: {
      coreActions: [...o.coreActions],
      outcomes: [...MONITORING_OUTCOMES],
      errorTypes: [...MONITORING_ERROR_TYPES],
      channel: "local", // 我方默认零外呼：本地通道（对照注记①，无 alertChannel 云告警面）
    },
  }).replace(/</g, "\\u003c");
}

/** 监控上报运行时（页内一次性脚本常量；ES5 形状，读内嵌声明→白名单执法→本地通道上报）。
 *  契约执法在页内：未声明动作 / 三值外结果 / 闭集外错误码一律丢弃并 console.warn（不抛错
 *  不影响页面）；上报=本地日志恒记 + 同源 best-effort POST（无 fetch/被 CSP 拦时静默降级为
 *  纯日志）。taskpane/monitor.js 是同一契约的静态页孪生实现，两测各锚其面（防漂移）。 */
export function monitoringRuntimeJs(): string {
  return `(function (global) {
  "use strict";
  var decl = null;
  try {
    var el = document.getElementById("${MONITORING_DECL_ID}");
    decl = el ? JSON.parse(el.textContent) : null;
  } catch (e) { decl = null; }
  var m = decl && decl.monitoring;
  var coreActions = m && Array.isArray(m.coreActions) ? m.coreActions : [];
  var outcomes = m && Array.isArray(m.outcomes) ? m.outcomes : [];
  var errorTypes = m && Array.isArray(m.errorTypes) ? m.errorTypes : [];
  function warn(msg) { try { console.warn("[juscite-monitor] " + msg); } catch (e) {} }
  function report(action, outcome, errorType, detail) {
    if (coreActions.indexOf(action) < 0) { warn("未声明动作已丢弃: " + action); return false; }
    if (outcomes.indexOf(outcome) < 0) { warn("结果不在三值闭集，已丢弃: " + outcome); return false; }
    if (errorType !== undefined && errorType !== null && errorTypes.indexOf(errorType) < 0) {
      warn("错误码不在枚举闭集，已丢弃: " + errorType); return false;
    }
    var event = { key: decl && decl.key, action: action, outcome: outcome,
      errorType: errorType || null, detail: typeof detail === "string" ? detail.slice(0, 200) : null,
      at: new Date().toISOString() };
    try { console.log("[juscite-monitor] " + JSON.stringify(event)); } catch (e) {}
    try {
      fetch("/api/v1/monitoring/report", { method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ source: event.key, events: [event] }) }).catch(function () {});
    } catch (e) { /* 无 fetch/CSP 拦截=静默，本地日志已记 */ }
    return true;
  }
  global.jusciteMonitor = { report: report, declared: coreActions.slice() };
})(window);`;
}
