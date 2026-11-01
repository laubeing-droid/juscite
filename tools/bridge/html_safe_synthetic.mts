// 施工单-10 单元三 · HTML 报告防注入+CSP 模板 合成自测（2026-11-01；全合成材料）。
// 覆盖面（单元③验收断言的机械形态）：
//   M 组 共享安全模块 @juscite/vizb shared/html.ts（转义/scheme 白名单/CSP/安全基模板 fail-fast）
//   L 组 所内分享落地页（share_station.mjs）——合成分享行含 <script>/<img onerror>/javascript:/data:text/html
//         等载荷 → jsdom 危险模式真执行取数桩 → 渲染后 DOM 走查零可执行残留＋零外域引用
//   C 组 订阅登录回调页（subscription_service.mjs）——error 回调参数反射载荷走查（修复前=反射注入实洞）
//   V 组 可视化 B 轨交付件回归——载荷案卷过大事记简表 SVG/对抗图 SVG/Word/Excel，属性与文本零逃逸；
//         确定性（同输入两跑逐字节一致）与 raster 换族链不破（f4f103fe 先例=改动须证不伤既有链）
// 隔离端口 :3091/:3092（≥3090 起自管；不碰 :3030/:43127，零桥 spawn）。
// 用法：node --import tsx tools/bridge/html_safe_synthetic.mts（末行 HTML_SAFE_SYNTH_PASS / _FAIL，exit 0/1）。
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import http_ from "node:http";
import { JSDOM } from "jsdom";
import { htmlEscape, sanitizeUrl, cspMeta, safeHtmlDocument } from "../../packages/juscite-vizb/src/shared/html.ts";
import { renderBrief } from "../../packages/juscite-vizb/src/chronicle/renderBrief.ts";
import { renderWord } from "../../packages/juscite-vizb/src/chronicle/renderWord.ts";
import { renderExcel } from "../../packages/juscite-vizb/src/chronicle/renderExcel.ts";
import { buildFigureModel } from "../../packages/juscite-vizb/src/confrontation/render.ts";
import { swapFontStackForRaster, guardRasterFontSwapped } from "../../packages/juscite-vizb/src/shared/raster.ts";
import { createShareStation } from "./share_station.mjs";

const results: Array<[string, boolean]> = [];
function check(name: string, ok: boolean, detail = "") {
  results.push([name, ok]);
  console.log(`[html-safe-synth] ${name}: ${ok ? "OK" : "FAIL"}${detail ? " — " + detail.slice(0, 220) : ""}`);
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// ══ 合成载荷（单元③点名四类 + 同族变体；全自拟，无真实案件数据）══
const PAYLOADS = [
  "<script>alert(1)</script>",
  '<img src=x onerror=alert(2)>',
  '<a href="javascript:alert(3)">点此领奖</a>',
  "data:text/html;base64,PHNjcmlwdD5hbGVydCg0KTwvc2NyaXB0Pg==",
  "<svg onload=alert(5)>",
  '"><script>alert(6)</script>',
  "<iframe src=\"data:text/html,<script>alert(7)</script>\"></iframe>",
  "<body onload=alert(8)>",
  "'-alert(9)-'",
  "vbscript:msgbox(10)",
];
const ATTR_PAYLOAD = '诉1" onload="alert(11)" data-x="y'; // 属性逃逸载荷（对抗图 data-el ← el.no）

// ── DOM 走查共用：全元素全属性扫描 ──
interface WalkHit { onAttr: string[]; badUrl: string[]; external: string[] }
const URL_ATTRS = new Set(["href", "src", "action", "formaction", "poster", "background", "xlink:href", "srcset", "data", "cite", "longdesc"]);
function walkDom(doc: Document, pageOrigin: string): WalkHit {
  const hit: WalkHit = { onAttr: [], badUrl: [], external: [] };
  for (const el of doc.querySelectorAll("*")) {
    for (const a of el.getAttributeNames()) {
      const v = el.getAttribute(a) ?? "";
      if (/^on[a-z]+$/i.test(a)) hit.onAttr.push(`${el.tagName}[${a}]`);
      if (URL_ATTRS.has(a.toLowerCase()) || a.toLowerCase().endsWith(":href") || a.toLowerCase().endsWith(":src")) {
        if (/^\s*(javascript|vbscript|data)\s*:/i.test(v)) hit.badUrl.push(`${el.tagName}[${a}]=${v.slice(0, 40)}`);
        if (/^https?:\/\//i.test(v) && !v.startsWith(pageOrigin)) hit.external.push(`${el.tagName}[${a}]=${v.slice(0, 60)}`);
        if (v.startsWith("//")) hit.external.push(`${el.tagName}[${a}]=${v.slice(0, 40)}`);
      }
    }
  }
  return hit;
}
function assertCleanDom(label: string, doc: Document, pageOrigin: string, expectScripts: number) {
  const hit = walkDom(doc, pageOrigin);
  check(`${label}·零内联事件属性`, hit.onAttr.length === 0, JSON.stringify(hit.onAttr));
  check(`${label}·零 javascript:/data: 协议引用`, hit.badUrl.length === 0, JSON.stringify(hit.badUrl));
  check(`${label}·零外域引用`, hit.external.length === 0, JSON.stringify(hit.external));
  check(`${label}·script 元素恰 ${expectScripts} 个（模板自有）`, doc.querySelectorAll("script").length === expectScripts,
    String(doc.querySelectorAll("script").length));
}

// ══════ M 组：共享安全模块 ══════
{
  const esc = htmlEscape(`<a href="x">'&"</a>`);
  check("M1 htmlEscape 五实体全转义", esc === "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&quot;&lt;/a&gt;", esc);

  const pass = ["https://example.com/a", "http://127.0.0.1:3030/x", "/api/v1/shares/abc", "#frag", "?q=1", "cn/share/xy"];
  check("M2 sanitizeUrl 放行 http/https/相对/锚/查询", pass.every((u) => sanitizeUrl(u) === u), pass.map((u) => `${u}→${sanitizeUrl(u)}`).join(" "));
  const deny = ["javascript:alert(1)", " JavaScript:alert(1)", "java\tscript:alert(1)", "java\nscript:alert(1)",
    "vbscript:msgbox(1)", "data:text/html,<x>", "DATA:TEXT/HTML;base64,PHM+", "//evil.example.com/x", "data:image/svg+xml;base64,PHN2Zz4="];
  check("M3 sanitizeUrl 拒 javascript:/vbscript:/data:text/html/协议相对/控制字符变体", deny.every((u) => sanitizeUrl(u) === null),
    deny.map((u) => `${JSON.stringify(u)}→${sanitizeUrl(u)}`).join(" "));
  const ok64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==";
  check("M4 sanitizeUrl data:image 位图仅声明处放行（svg+xml 恒拒）",
    sanitizeUrl(ok64) === null && sanitizeUrl(ok64, { allowDataImage: true }) === ok64
      && sanitizeUrl("data:image/png;base64,<!notb64>", { allowDataImage: true }) === null
      && sanitizeUrl("data:image/svg+xml;base64,PHN2Zz4=", { allowDataImage: true }) === null, "");

  const csp = cspMeta({ nonce: "AAAAAAAAAAAAAAAAAAAAAAAAAAA=", connectSelf: true });
  check("M5 cspMeta default-src 'none' 起步+nonce 指令+无 unsafe-inline",
    csp.includes("default-src 'none'") && csp.includes(`script-src 'nonce-AAAAAAAAAAAAAAAAAAAAAAAAAAA='`)
      && csp.includes("connect-src 'self'") && !csp.includes("unsafe-inline"), csp);
  let badNonce = "";
  try { cspMeta({ nonce: "short" }); } catch (e) { badNonce = String((e as Error).message); }
  check("M5b cspMeta 非 base64 短 nonce 拒", badNonce.length > 0, badNonce);
  let badImg = "";
  try { cspMeta({ imgSources: ["https://evil.example.com/*"] }); } catch (e) { badImg = String((e as Error).message); }
  check("M6 cspMeta img 来源闭集外拒", badImg.length > 0, badImg);

  let noNonce = "";
  try { safeHtmlDocument({ title: "t", csp: cspMeta(), body: "b", script: { nonce: "", js: "x" } }); } catch (e) { noNonce = String((e as Error).message); }
  let styleNoNonce = "";
  try { safeHtmlDocument({ title: "t", csp: cspMeta(), body: "b", style: "p{}" }); } catch (e) { styleNoNonce = String((e as Error).message); }
  let mismatch = "";
  const otherCsp = cspMeta({ nonce: "BBBBBBBBBBBBBBBBBBBBBBBBBBB=" });
  try { safeHtmlDocument({ title: "t", csp: otherCsp, body: "b", script: { nonce: "AAAAAAAAAAAAAAAAAAAAAAAAAAA=", js: "x" } }); } catch (e) { mismatch = String((e as Error).message); }
  check("M7 safeHtmlDocument 无 nonce 脚本/无 nonce 样式/nonce 不一致三拒", noNonce.length > 0 && styleNoNonce.length > 0 && mismatch.length > 0,
    [noNonce, styleNoNonce, mismatch].join(" | "));
  const doc = safeHtmlDocument({
    title: '题"引<>&',
    csp: cspMeta({ nonce: "AAAAAAAAAAAAAAAAAAAAAAAAAAA=" }),
    body: '<p id="only">静态骨架</p>',
    style: "p{color:red}",
    script: { nonce: "AAAAAAAAAAAAAAAAAAAAAAAAAAA=", js: "var x=1;" },
  });
  const dom = new JSDOM(doc);
  const metaEl = dom.window.document.querySelector('meta[http-equiv="Content-Security-Policy"]');
  check("M8 基模板骨架：CSP meta 在 head、script/style 带 nonce、题转义、零 on* 属性",
    Boolean(metaEl) && dom.window.document.head.querySelector("style")?.getAttribute("nonce") === "AAAAAAAAAAAAAAAAAAAAAAAAAAA="
      && dom.window.document.querySelector("script")?.getAttribute("nonce") === "AAAAAAAAAAAAAAAAAAAAAAAAAAA="
      && dom.window.document.title === `题"引<>&` // 解码后回原文=转义正确
      && walkDom(dom.window.document, "").onAttr.length === 0, "");
}

// ══════ L 组：分享落地页（隔离 :3091；合成分享文件含载荷）══════
const L_PORT = 3091;
const L_BASE = `http://127.0.0.1:${L_PORT}`;
{
  const shareDir = mkdtempSync(join(tmpdir(), "juscite-htmlsafe-share-"));
  process.env.BRIDGE_SHARE_DIR = shareDir;
  const station = createShareStation({ port: L_PORT });
  const server = http_.createServer((req, res) => {
    station.handle(req, res, new URL(req.url ?? "/", L_BASE).pathname)
      .then((handled) => { if (!handled) { res.writeHead(404); res.end(); } })
      .catch((e) => { if (!res.headersSent) res.writeHead(500); res.end(String(e?.message ?? e)); });
  });
  await new Promise<void>((r) => server.listen(L_PORT, "127.0.0.1", r));
  try {
    // 合成分享：标题与三类行文本全塞载荷（载荷=案卷字符串进产物 HTML 的真实路径）
    const code = "htmlsafe1";
    const rows = [
      { kind: "turnHeader" },
      { kind: "userInput", text: `合成提问：${PAYLOADS[0]} 与 ${PAYLOADS[1]}` },
      { kind: "assistantText", text: `合成回答：${PAYLOADS[2]} 与 ${PAYLOADS[3]}`, state: "complete" },
      { kind: "userInput", text: `二问：${PAYLOADS[4]}${PAYLOADS[5]}` },
      { kind: "assistantText", text: `二答：${PAYLOADS[6]}｜${PAYLOADS[8]}｜${PAYLOADS[9]}`, state: "complete" },
    ];
    writeFileSync(join(shareDir, `${code}.json`), JSON.stringify({
      share_code: code, share_url: `${L_BASE}/cn/share/${code}`, title: `合成分享：${PAYLOADS[7]}`,
      access_mode: "public_readonly", created_at: Date.now() - 60_000, expires_at: Date.now() + 3600_000,
      rows, integrity: { projection_sha256: "0".repeat(64), artifact_set_sha256: "1".repeat(64) },
    }), "utf-8");

    const pageRes = await fetch(`${L_BASE}/cn/share/${code}`);
    const page = await pageRes.text();
    const cspText = /<meta http-equiv="Content-Security-Policy" content="([^"]*)"/.exec(page)?.[1] ?? "";
    check("L1 落地页应答 text/html 且 CSP 形齐（default-src 'none'+nonce+connect-src 'self'，无 unsafe-inline）",
      (pageRes.headers.get("content-type") ?? "").includes("text/html")
        && cspText.startsWith("default-src 'none'") && cspText.includes("script-src 'nonce-") && cspText.includes("style-src 'nonce-")
        && cspText.includes("connect-src 'self'") && !cspText.includes("unsafe-inline"), cspText);

    // jsdom 危险模式真执行：取数桩回载荷行，走完 innerHTML 渲染后走查 DOM
    let fetchedUrl = "";
    const dom = new JSDOM(page, {
      runScripts: "dangerously",
      url: `${L_BASE}/cn/share/${code}`,
      beforeParse(window) {
        window.fetch = (async (url: string) => {
          fetchedUrl = String(url);
          return {
            ok: true,
            json: async () => ({
              code: 0,
              data: {
                share: { title: `合成分享：${PAYLOADS[7]}`, access_mode: "public_readonly", created_at: Date.now() - 60_000, expires_at: Date.now() + 3600_000 },
                rows,
                artifacts: [],
              },
            }),
          };
        }) as unknown as typeof fetch;
      },
    });
    const app = dom.window.document.getElementById("app");
    for (let i = 0; i < 50 && app?.getAttribute("class") !== ""; i++) await sleep(100);
    check("L2 载荷行渲染完成（取数桩→innerHTML 渲染态到位）", app?.getAttribute("class") === "", app?.getAttribute("class") ?? "null");
    check("L2b 取数接线只打同源相对路径", fetchedUrl.startsWith("/api/v1/shares/"), fetchedUrl);
    const doc = dom.window.document;
    const scriptNonce = doc.querySelector("script")?.getAttribute("nonce") ?? "";
    check("L3 渲染后 script 恰 1 个且 nonce 与 CSP 同值",
      doc.querySelectorAll("script").length === 1 && scriptNonce.length >= 22 && cspText.includes(`'nonce-${scriptNonce}'`),
      `scripts=${doc.querySelectorAll("script").length} nonce=${scriptNonce.slice(0, 8)}…`);
    assertCleanDom("L4/L5/L6 落地页渲染后 DOM", doc, L_BASE, 1);
    const bodyText = doc.body.textContent ?? "";
    const rendered = PAYLOADS.filter((p) => bodyText.includes(p));
    check("L7 载荷十发十在场（照录不丢，全部只作文本）", rendered.length === PAYLOADS.length,
      `在场 ${rendered.length}/${PAYLOADS.length}：缺 ${PAYLOADS.filter((p) => !bodyText.includes(p)).join(" ｜ ").slice(0, 160)}`);

    // 非法 code：404 mini 页也带 CSP；handler 闭集外的载荷 code 不进模板
    const bad = await fetch(`${L_BASE}/cn/share/${encodeURIComponent('"><script>alert(1)</script>')}`);
    const badText = await bad.text();
    check("L8 非法载荷 code=404 mini 页（带 default-src 'none'，零 script）",
      bad.status === 404 && badText.includes(`default-src 'none'`) && !badText.includes("<script>"),
      `${bad.status} ${badText.slice(0, 120)}`);
  } finally {
    await new Promise<void>((r) => server.close(() => r()));
    try { rmSync(shareDir, { recursive: true, force: true }); } catch { /* 临时目录残留无害 */ }
    delete process.env.BRIDGE_SHARE_DIR;
  }
}

// ══════ C 组：订阅登录回调页（隔离 :3092；error 参数反射载荷）══════
{
  const { createSubscriptionService, renderCallbackPage } = await import("./subscription_service.mjs");
  const stateRoot = mkdtempSync(join(tmpdir(), "juscite-htmlsafe-siwc-"));
  process.env.BRIDGE_SUBSCRIPTION_STATE_ROOT = stateRoot;
  const service = createSubscriptionService({ port: 3092 });
  const server = http_.createServer((req, res) => {
    service.httpHandler(req, res, new URL(req.url ?? "/", "http://127.0.0.1:3092"))
      .then((handled) => { if (!handled) { res.writeHead(404); res.end(); } })
      .catch((e) => { if (!res.headersSent) res.writeHead(500); res.end(String(e?.message ?? e)); });
  });
  await new Promise<void>((r) => server.listen(3092, "127.0.0.1", r));
  try {
    // error=载荷 & state 缺失 → 拒绝分支页直接渲染（不走引擎，离线）
    const q = encodeURIComponent(`${PAYLOADS[1]}｜${PAYLOADS[2]}｜${PAYLOADS[3]}`);
    const page = await (await fetch(`http://127.0.0.1:3092/auth/callback?error=${q}`)).text();
    check("C1 回调页载荷全转义（&lt;img…&gt; 在场、裸 <script>/<img 在 HTML 源不在）",
      page.includes("&lt;img src=x onerror=alert(2)&gt;") && page.includes("javascript&#39;") === false
        && !page.includes("<script>") && !page.includes("<img "), page.slice(0, 200));
    const dom = new JSDOM(page);
    assertCleanDom("C2/C3 回调页 DOM", dom.window.document, "http://127.0.0.1:3092", 0);
    const cspText = /<meta http-equiv="Content-Security-Policy" content="([^"]*)"/.exec(page)?.[1] ?? "";
    check("C3b 回调页 CSP：default-src 'none'+nonce 样式、无 unsafe-inline、无 connect-src",
      cspText.startsWith("default-src 'none'") && cspText.includes("style-src 'nonce-") && !cspText.includes("unsafe-inline") && !cspText.includes("connect-src"), cspText);
    check("C4 回调页载荷作为正文文本在场", (dom.window.document.body.textContent ?? "").includes("data:text/html;base64,PHNjcmlwdD5hbGVydCg0KTwvc2NyaXB0Pg=="), "");

    // 三分支全走查（直调渲染函数；timeout/rejected 回显码也须只作文本）
    let branchesClean = true;
    const branchDetail: string[] = [];
    for (const [branch, code] of [["success", null], ["timeout", `siwc_x</p><script>alert(1)</script>`], ["rejected", `<img src=x onerror=alert(1)>`]] as Array<[string, string | null]>) {
      const html = renderCallbackPage(branch, code, false);
      const d = new JSDOM(html).window.document;
      const hit = walkDom(d, "");
      const bad = d.querySelectorAll("script").length !== 0 || hit.onAttr.length > 0 || hit.badUrl.length > 0;
      if (bad) branchesClean = false;
      branchDetail.push(`${branch}:${bad ? "DIRTY" : "clean"}`);
      if (branch === "rejected") {
        check("C5 rejected 分支：data-testid/branch 锚保留（既有测试合同不破）",
          html.includes('data-testid="login-callback-page"') && html.includes('data-branch="rejected"')
            && (d.body.textContent ?? "").includes("<img src=x onerror=alert(1)>"), "");
      }
    }
    check("C6 三分支页全走查零可执行残留", branchesClean, branchDetail.join(" "));
  } finally {
    await new Promise<void>((r) => server.close(() => r()));
    try { rmSync(stateRoot, { recursive: true, force: true }); } catch { /* 尽力而为 */ }
    delete process.env.BRIDGE_SUBSCRIPTION_STATE_ROOT;
  }
}

// ══════ V 组：可视化 B 轨交付件载荷回归（确定性+raster 链不破）══════
{
  // 合成案卷：载荷进案件名/事实标题与内容/主体/文档名（大事记四件交付面）
  const payloadDoc = { docId: "卷一-合成载荷", label: `载荷文档${PAYLOADS[4]}`, volume: "卷一", text: "合成正文。" };
  const fb = {
    schema: "juscite.vizb.chronicle.factbase@1" as const,
    caseTitle: `王五诉赵六载荷案（合成）${PAYLOADS[0]}`,
    docs: [payloadDoc],
    facts: [
      { factNo: 1, dateStr: "2026-04-01", datePrecision: "day" as const, verb: "出借", title: `出借${PAYLOADS[1]}`,
        content: `2026年4月1日，王五出借合成款项${PAYLOADS[2]}${PAYLOADS[3]}`, sourceDoc: "卷一-合成载荷", locator: "p1¶1",
        evidenceNo: "证1", volume: "卷一", subjects: [`王五${PAYLOADS[5]}`, "赵六"], dispute: null, arithmeticNote: null },
      { factNo: 2, dateStr: "2026-09-01", datePrecision: "day" as const, verb: "归还", title: `归还${PAYLOADS[3]}`,
        content: `赵六归还部分款项${PAYLOADS[6]}，余款未付${PAYLOADS[9]}`, sourceDoc: "卷一-合成载荷", locator: "p1¶2",
        evidenceNo: null, volume: "卷一", subjects: ["赵六"], dispute: null, arithmeticNote: null },
    ],
    uncertainty: [],
  };
  const briefPages = renderBrief(fb);
  let v1Ok = true;
  let v1Why = "";
  for (const pg of briefPages) {
    try {
      const d = new JSDOM(pg, { contentType: "image/svg+xml" }).window.document;
      if (d.querySelectorAll("script").length !== 0 || walkDom(d, "").onAttr.length > 0) { v1Ok = false; v1Why += "dirty页 "; }
    } catch (e) {
      v1Ok = false;
      v1Why += `XML解析失败:${String(e).slice(0, 60)} `;
    }
  }
  check("V1 大事记简表 SVG：逐页 XML 可解析+零 script+零 on* 属性+载荷只作文本",
    v1Ok && briefPages.join("").includes("&lt;img src=x onerror=alert(2)&gt;")
      && briefPages.join("").includes("data:text/html;base64,PHNjcmlwdD5hbGVydCg0KTwvc2NyaXB0Pg=="),
    `${v1Why}页数=${briefPages.length}`);

  const word = renderWord(fb);
  const wordDom = new JSDOM(word).window.document;
  check("V2 大事记 Word XML：载荷全转义（&lt;script&gt; 文本在场、源无裸 <script）、解析零 script 元素",
    word.includes("&lt;script&gt;") && !word.includes("<script>") && wordDom.querySelectorAll("script").length === 0, "");
  const excel = renderExcel(fb);
  const excelDom = new JSDOM(excel).window.document;
  check("V3 大事记 Excel XML：载荷全转义、解析零 script 元素",
    excel.includes("&lt;img src=x onerror=alert(2)&gt;") && !excel.includes("<img ") && excelDom.querySelectorAll("script").length === 0, "");

  // 对抗图：el.no 属性逃逸载荷（修复点 data-el/data-from/data-to）
  const sem = {
    schema: "juscite.vizb.confrontation@1" as const,
    caseTitle: `载荷对抗案（合成）${PAYLOADS[0]}`,
    internalOnly: true as const,
    maturity: "L2" as const,
    procedure: { jurisdiction: "合成管辖", standing: "合成主体", repeatedSuit: "合成无重复" },
    sources: [{ name: "起诉状.txt", text: "请求支付货款一万元。" }],
    claims: [{ no: "诉1", type: "payment", summary: { text: "请求支付货款一万元。", src: "起诉状.txt", srcKind: "起诉状" as const },
      claimedCents: 1000000, items: [{ label: "货款", cents: 1000000, basis: "合同（合成）" }], adjustments: [], required: { counterpart: "乙", subjectMatter: "货款", amount: "一万元" } }],
    defenses: [],
    elements: [{ no: ATTR_PAYLOAD, issue: `交付义务${PAYLOADS[1]}`,
      claim: { text: "甲已交付全部货物。", src: "起诉状.txt", srcKind: "起诉状" as const },
      response: { text: `乙称未收货${PAYLOADS[2]}。`, src: "起诉状.txt", srcKind: "答辩状" as const },
      counter: { absent: true as const, reason: "无书面记载" as const }, second: { absent: true as const, reason: "未获取" as const },
      burden: "claimant" as const, lawConfidence: "high" as const, evidenceConfidence: "mid" as const, source: "起诉状", disputed: true, evidenceStandardMet: true }],
    toComplete: [],
  };
  const fig = buildFigureModel(sem);
  const confDom = new JSDOM(fig.svg, { contentType: "image/svg+xml" });
  const confDoc = confDom.window.document;
  const dataEls = [...confDoc.querySelectorAll("[data-el]")].map((e) => e.getAttribute("data-el") ?? "");
  check("V4 对抗图 SVG：属性载荷零逃逸（data-el 值=原串带引号、全图零 on* 属性、零 script、载荷文本在场）",
    confDoc.querySelectorAll("script").length === 0 && walkDom(confDoc, "").onAttr.length === 0
      && dataEls.some((v) => v === ATTR_PAYLOAD) && (confDoc.documentElement.textContent ?? "").includes("javascript:alert(3)"),
    `data-el 样本=${JSON.stringify(dataEls.slice(0, 3))}`);

  check("V5 确定性不破：简表/对抗图同输入两跑逐字节一致",
    renderBrief(fb).join("\n") === briefPages.join("\n") && buildFigureModel(sem).svg === fig.svg, "");
  const swap = swapFontStackForRaster(fig.svg, "Juscite Raster CJK");
  check("V6 raster 换族链不破：载荷 SVG 换族后单族守卫全过（f4f103fe 先例=改动证不伤既有链）",
    guardRasterFontSwapped(swap.svg, "Juscite Raster CJK").length === 0 && swap.logs.length > 0, swap.logs[0] ?? "");
}

// ══ 汇总 ══
const failed = results.filter(([, ok]) => !ok).map(([n]) => n);
console.log(`[html-safe-synth] PASS ${results.length - failed.length}/${results.length}`);
if (failed.length > 0) {
  console.error(`HTML_SAFE_SYNTH_FAIL failed=${failed.join(",")}`);
  process.exit(1);
}
console.log("HTML_SAFE_SYNTH_PASS");
process.exit(0);
