#!/usr/bin/env node
// 声明式监控白名单 + 宿主桥降级 合成自测（逆向吸收波二·条 2/条 3；全部合成材料）。
// 条 2 断言面：A 契约常量与构建期校验（词表闭集/三值/错误枚举/fail-fast）
//              B safeHtmlDocument 注入（声明块+执法运行时+nonce 一致性）
//              C 页内执法（vizb 运行时 与 taskpane/monitor.js 双实现同矩阵：白名单放行/
//                未声明丢弃+警告/三值闭集/错误枚举闭集/本地通道 best-effort）
//              D 消费面接线（share 落地页/subscription 回调页/taskpane 静态页零漂移/零外呼/收件面）
// 条 3 断言面：E 宿主桥 host.use('db'/'user') 两态（真身经真协议/降级假身全合成+inertHealth
//              no-op+横幅/降级零报错/能力闭集/live 通道失败不悄悄换假身）
// 隔离端口 ：3090 段（先探活避让）；oc28(:43127) 与 :3030 全程不碰。
// 运行：node --import tsx tools/bridge/monitoring_synthetic.mjs（末行 MONITORING_SYNTH_PASS）
import { createServer } from "node:http";
import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
import WebSocket from "ws";
import {
  MONITORING_CORE_ACTIONS, MONITORING_OUTCOMES, MONITORING_ERROR_TYPES,
  MONITORING_DECL_ID, monitoringDeclaration, safeHtmlDocument, cspMeta,
} from "../../packages/juscite-vizb/src/shared/html.ts";
import { createShareStation } from "./share_station.mjs";
import { renderCallbackPage } from "./subscription_service.mjs";
import { startOfficeBridge } from "../../packages/juscite-office-bridge/src/index.mjs";

const REPO_ROOT = fileURLToPath(new URL("../..", import.meta.url));
const TASKPANE_DIR = join(REPO_ROOT, "packages", "juscite-office-bridge", "taskpane");
const PORT_BASE = 3090; // 施工纪律：自测隔离端口 :3090 段，先探活避让

const results = [];
let failed = 0;
function check(name, ok, detail = "") {
  const line = `${ok ? "OK " : "FAIL"} ${name}${detail ? "｜" + detail : ""}`;
  results.push(line);
  console.log(`[monitoring-synth] ${results.length}: ${line}`);
  if (!ok) failed++;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function freePortFrom(base) {
  for (let p = base; p < base + 50; p++) {
    const probe = createServer();
    const free = await new Promise((res) => {
      probe.once("error", () => res(false));
      probe.listen(p, "127.0.0.1", () => res(true));
    });
    probe.close();
    if (free) return p;
  }
  throw new Error(`:${base} 起找不到空闲端口`);
}

// 探活避让双保险：除探活外还避开「已用过且 undici 连接池持有 keep-alive 套接字的端口」——
// 新服务复用同号端口会被陈旧池连接打 ECONNRESET（实测踩坑：站点→桥1 首跳即中）。
const pooledPorts = new Set();
async function freePortAvoidingPooled() {
  for (let p = PORT_BASE; p < PORT_BASE + 60; p++) {
    if (pooledPorts.has(p)) continue;
    const probe = createServer();
    const free = await new Promise((res) => {
      probe.once("error", () => res(false));
      probe.listen(p, "127.0.0.1", () => res(true));
    });
    probe.close();
    if (free) return p;
  }
  throw new Error(":3090 段找不到空闲端口");
}

// ── vm 页面环境：document/fetch/console 桩 + 未捕获错误收集 ──
function makePageContext({ declarationText } = {}) {
  const logs = { log: [], warn: [], error: [] };
  const fetchCalls = [];
  const monitorReports = [];
  const elements = {};
  if (declarationText !== undefined) elements[MONITORING_DECL_ID] = { textContent: declarationText };
  elements["degrade-banner"] = { hidden: true, textContent: "" };
  const sandbox = {
    console: {
      log: (...a) => logs.log.push(a.map(String).join(" ")),
      warn: (...a) => logs.warn.push(a.map(String).join(" ")),
      error: (...a) => logs.error.push(a.map(String).join(" ")),
    },
    document: { getElementById: (id) => elements[id] ?? null },
    fetch: async (url, init) => {
      fetchCalls.push({ url: String(url), body: init?.body ? JSON.parse(init.body) : null });
      return { ok: true, status: 204 };
    },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  return { context: vm.createContext(sandbox), sandbox, logs, fetchCalls, monitorReports, elements };
}
function runInPage(page, code, label) {
  try {
    new vm.Script(code, { filename: label }).runInContext(page.context);
    return null;
  } catch (e) {
    page.logs.error.push(`vm 异常: ${e.message}`);
    return e;
  }
}

// 从 safeHtmlDocument 产物中抽取声明块与首个 nonce 脚本（=监控执法运行时，注入在正文前）
function extractMonitoringBlocks(html) {
  const decl = new RegExp(`<script type="application/json" id="${MONITORING_DECL_ID}">([\\s\\S]*?)</script>`).exec(html);
  const reporter = /<script nonce="([^"]+)">([\s\S]*?)<\/script>/.exec(html);
  return { declText: decl?.[1] ?? null, reporterJs: reporter?.[2] ?? null, reporterNonce: reporter?.[1] ?? null };
}

async function main() {
  const watchdog = setTimeout(() => {
    console.error("[monitoring-synth] 看门狗超时");
    console.log("MONITORING_SYNTH_FAIL");
    process.exit(1);
  }, 120_000);
  watchdog.unref?.();

  // ══ A. 契约常量与构建期校验 ══
  {
    const dup = (arr) => new Set(arr).size !== arr.length;
    check("A1 词表/三值/错误枚举闭集自洽（非空/无重复/词表全中文动作词=我方自拟语义）",
      MONITORING_CORE_ACTIONS.length > 0 && MONITORING_OUTCOMES.length === 3 && MONITORING_ERROR_TYPES.length > 0
      && !dup(MONITORING_CORE_ACTIONS) && !dup(MONITORING_OUTCOMES) && !dup(MONITORING_ERROR_TYPES)
      && MONITORING_CORE_ACTIONS.every((a) => /^[\u4e00-\u9fff]{1,4}$/u.test(a))
      && MONITORING_OUTCOMES.join() === "成功,失败,中止",
      `词表=${MONITORING_CORE_ACTIONS.length} 词 错误枚举=${MONITORING_ERROR_TYPES.length} 枚`);
    const declText = monitoringDeclaration({ key: "synth-page", coreActions: ["打开", "渲染"] });
    const decl = JSON.parse(declText);
    check("A2 monitoringDeclaration 产出（channel=local/无 alertChannel 键/词表序保留/`<` 已转义防 </script> 截断）",
      decl.key === "synth-page" && decl.monitoring.channel === "local"
      && !("alertChannel" in decl.monitoring) && !declText.includes("<")
      && JSON.stringify(decl.monitoring.coreActions) === JSON.stringify(["打开", "渲染"])
      && JSON.stringify(decl.monitoring.outcomes) === JSON.stringify([...MONITORING_OUTCOMES])
      && JSON.stringify(decl.monitoring.errorTypes) === JSON.stringify([...MONITORING_ERROR_TYPES]),
      `channel=${decl.monitoring.channel}`);
    const throws = (fn) => { try { fn(); return false; } catch { return true; } };
    check("A3 构建期 fail-fast（词表外动作/空 coreActions/坏 key/重复动作 均 throw）",
      throws(() => monitoringDeclaration({ key: "k", coreActions: ["save"] }))
      && throws(() => monitoringDeclaration({ key: "k", coreActions: [] }))
      && throws(() => monitoringDeclaration({ key: "Bad Key!", coreActions: ["打开"] }))
      && throws(() => monitoringDeclaration({ key: "k", coreActions: ["打开", "打开"] })));
  }

  // ══ B. safeHtmlDocument 注入 ══
  const pageDecl = monitoringDeclaration({ key: "synth-page", coreActions: ["打开", "渲染", "提交"] });
  let synthHtml = "";
  {
    const nonce = "AAAAAAAAAAAAAAAAAAAAAA=="; // base64 22 字符（满足 NONCE_RE）
    synthHtml = safeHtmlDocument({
      title: "监控合成页",
      csp: cspMeta({ nonce }),
      monitoring: { key: "synth-page", coreActions: ["打开", "渲染", "提交"] },
      body: '<p data-marker="body-start">ok</p>',
    });
    const blocks = extractMonitoringBlocks(synthHtml);
    const iDecl = synthHtml.indexOf(`<script type="application/json" id="${MONITORING_DECL_ID}">`);
    const iBody = synthHtml.indexOf('data-marker="body-start"');
    check("B1 模板注入结构（声明数据块+执法运行时在正文前；nonce 与 CSP 一致；声明文=monitoringDeclaration 同源）",
      iDecl >= 0 && iDecl < iBody && !!blocks.reporterJs && blocks.reporterJs.includes("jusciteMonitor")
      && synthHtml.includes(`'nonce-${blocks.reporterNonce}'`) && blocks.declText === pageDecl);
    check("B2 monitoring 缺 nonce 授权=拒绝出稿（fail-fast，不静默降级）",
      (() => { try { safeHtmlDocument({ title: "t", csp: cspMeta(), monitoring: { key: "k", coreActions: ["打开"] }, body: "" }); return false; } catch { return true; } })());
  }

  // ══ C. 页内执法（vizb 运行时 与 taskpane/monitor.js 双实现同一断言矩阵） ══
  const monitorJsStatic = readFileSync(join(TASKPANE_DIR, "monitor.js"), "utf-8");
  const impls = [
    ["vizb-runtime", extractMonitoringBlocks(synthHtml).reporterJs],
    ["taskpane-monitor.js", monitorJsStatic],
  ];
  for (const [implLabel, code] of impls) {
    // 该实现配本页声明跑一遍完整矩阵
    const page = makePageContext({ declarationText: pageDecl });
    runInPage(page, code, implLabel);
    const m = page.sandbox.jusciteMonitor;
    const ok1 = !!m && m.report("打开", "成功") === true;
    await sleep(20);
    const c1 = page.fetchCalls.length === 1 && page.fetchCalls[0].url === "/api/v1/monitoring/report"
      && page.fetchCalls[0].body.source === "synth-page" && page.fetchCalls[0].body.events[0].action === "打开";
    const logged = page.logs.log.some((l) => l.includes('"action":"打开"'));
    check(`C1(${implLabel}) 白名单放行（声明内动作+成功 → true；本地日志恒记+同源本地桥 POST）`,
      ok1 && c1 && logged, `fetch=${page.fetchCalls.length}`);
    // C2 未声明丢弃：词表内但未声明 + 词表外
    page.fetchCalls.length = 0;
    const before2 = page.logs.warn.length;
    const d1 = m.report("删除", "成功") === false; // 词表内、本页未声明
    const d2 = m.report("save", "成功") === false; // 词表外（英文=非我方词表）
    await sleep(20);
    check(`C2(${implLabel}) 未声明动作丢弃并警告（未声明/词表外 → false+console.warn+零上报）`,
      d1 && d2 && page.logs.warn.length >= before2 + 2 && page.fetchCalls.length === 0,
      `warns+${page.logs.warn.length - before2}`);
    // C3 三值闭集
    const v1 = m.report("渲染", "成功") === true && m.report("渲染", "失败") === true && m.report("渲染", "中止") === true;
    const v2 = m.report("渲染", "完成") === false && page.logs.warn.some((l) => l.includes("三值"));
    check(`C3(${implLabel}) 结果三值闭集（成功/失败/中止 放行；第四值「完成」丢弃+警告）`, v1 && v2);
    // C4 错误枚举闭集
    const e1 = m.report("提交", "失败", "local_bridge_unavailable") === true;
    const e2 = m.report("提交", "失败", "slack_alert_channel") === false; // 闭集外（对照注记：无云告警面）
    const e3 = m.report("提交", "失败") === true && m.report("提交", "成功", null) === true; // 省略/null 放行
    check(`C4(${implLabel}) 错误枚举闭集（枚举内放行；闭集外拒；errorType 可省略）`, e1 && e2 && e3);
    // C5 本地桥 best-effort：fetch 抛错/被拦 → 仍 true、零异常（本地日志已记）
    page.sandbox.fetch = async () => { throw new Error("CSP 拦截/无 fetch"); };
    const c5 = m.report("打开", "成功") === true && page.logs.error.length === 0;
    check(`C5(${implLabel}) 本地桥通道 best-effort（上报失败静默=不影响页面，返回仍 true）`, c5);
    // C6 无声明数据块=全拒绝（fail-closed）
    const bare = makePageContext({});
    runInPage(bare, code, implLabel + "-bare");
    const c6 = bare.sandbox.jusciteMonitor.report("打开", "成功") === false;
    check(`C6(${implLabel}) 页面缺声明数据块=一切上报丢弃（fail-closed）`, c6);
  }

  // ══ D. 消费面接线 ══
  process.env.BRIDGE_SHARE_DIR = mkdtempSync(join(tmpdir(), "juscite-mon-share-"));
  const stationPort = await freePortAvoidingPooled();
  pooledPorts.add(stationPort);
  const station = createShareStation({ port: stationPort });
  const stationSrv = createServer(async (req, res) => {
    const pathname = new URL(req.url ?? "/", "http://127.0.0.1").pathname;
    if (!(await station.handle(req, res, pathname))) { res.writeHead(404); res.end(); }
  });
  await new Promise((r) => stationSrv.listen(stationPort, "127.0.0.1", r));
  {
    // D1 分享落地页
    const html = await (await fetch(`http://127.0.0.1:${stationPort}/cn/share/Abcd12345678`)).text();
    const blocks = extractMonitoringBlocks(html);
    const decl = blocks.declText ? JSON.parse(blocks.declText) : null;
    check("D1 share 落地页补声明接线（key=share-landing；coreActions ⊆ 词表；页脚本经 jusciteMonitor 上报打开/渲染）",
      !!decl && decl.key === "share-landing" && decl.monitoring.coreActions.every((a) => MONITORING_CORE_ACTIONS.includes(a))
      && !!blocks.reporterJs && /report\("打开"/.test(html) && /report\("渲染"/.test(html),
      `coreActions=${decl?.monitoring.coreActions.join("/")}`);
    // D2 订阅回调页
    const cb = renderCallbackPage("success", null, true);
    const cbBlocks = extractMonitoringBlocks(cb);
    const cbDecl = cbBlocks.declText ? JSON.parse(cbBlocks.declText) : null;
    check("D2 subscription 回调页补声明接线（key=subscription-callback；CSP 最小放开 connect-src 'self'=同源本地上报通道；上报脚本在）",
      !!cbDecl && cbDecl.key === "subscription-callback" && cb.includes("connect-src 'self'")
      && /report\("打开", "成功"\)/.test(cb) && /report\("渲染", "成功"\)/.test(cb));
    // D3 taskpane 静态声明与 vizb 常量零漂移
    const tpHtml = readFileSync(join(TASKPANE_DIR, "index.html"), "utf-8");
    const mDecl = new RegExp(`<script type="application/json" id="${MONITORING_DECL_ID}">([\\s\\S]*?)</script>`).exec(tpHtml);
    const tpDecl = mDecl ? JSON.parse(mDecl[1]) : null;
    check("D3 taskpane 静态页声明零漂移（coreActions ⊆ 词表；outcomes/errorTypes 与 vizb 常量逐项一致；channel=local 无 alertChannel）",
      !!tpDecl && tpDecl.key === "office-taskpane"
      && tpDecl.monitoring.coreActions.every((a) => MONITORING_CORE_ACTIONS.includes(a))
      && JSON.stringify(tpDecl.monitoring.outcomes) === JSON.stringify([...MONITORING_OUTCOMES])
      && JSON.stringify(tpDecl.monitoring.errorTypes) === JSON.stringify([...MONITORING_ERROR_TYPES])
      && tpDecl.monitoring.channel === "local" && !("alertChannel" in tpDecl.monitoring),
      `coreActions=${tpDecl?.monitoring.coreActions.join("/")}`);
    // D4 零外呼：taskpane 自有文件（含新增 monitor.js/host-bridge.js）+ 监控运行时，非回环引用=0
    const violations = [];
    const walk = (dir) => {
      for (const e of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, e.name);
        if (e.isDirectory()) { if (e.name !== "vendor") walk(full); continue; }
        if (!/\.(html|js|css)$/.test(e.name)) continue;
        for (const mm of readFileSync(full, "utf-8").matchAll(/https?:\/\/[^\s"'`)]+/g)) {
          if (!/^https?:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/.test(mm[0])) violations.push(`${e.name}: ${mm[0]}`);
        }
      }
    };
    walk(TASKPANE_DIR);
    check("D4 零外呼（taskpane 自有文件+两实现运行时，非 127.0.0.1 引用=0；上报通道无云告警面）",
      violations.length === 0 && !monitorJsStatic.includes("alertChannel")
      && !extractMonitoringBlocks(synthHtml).reporterJs.includes("alertChannel"),
      violations.slice(0, 2).join("; ") || "clean");
    // D5 分享站收件面（本地桥通道终点）
    const okPost = await fetch(`http://127.0.0.1:${stationPort}/api/v1/monitoring/report`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ source: "synth-page", events: [{ action: "打开", outcome: "成功", errorType: null, detail: "合成" }] }),
    });
    const badJson = await fetch(`http://127.0.0.1:${stationPort}/api/v1/monitoring/report`, { method: "POST", body: "not-json" });
    const badShape = await fetch(`http://127.0.0.1:${stationPort}/api/v1/monitoring/report`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ source: "synth-page", events: [] }),
    });
    check("D5 分享站本地收件面（合法 204/坏 JSON 400/坏形状 400——只收形状，白名单执法在页内）",
      okPost.status === 204 && badJson.status === 400 && badShape.status === 400,
      `${okPost.status}/${badJson.status}/${badShape.status}`);
    // D6 app.js 接线静态检查（真身/降级切换+五动作上报 ⊆ 声明 coreActions）
    const appJs = readFileSync(join(TASKPANE_DIR, "app.js"), "utf-8");
    const reported = [...appJs.matchAll(/report\("([^"]+)"/g)].map((x) => x[1]);
    check("D6 app.js 接线（setLiveTransport/goInert 两态切换+身份行；上报动作 ⊆ 声明 coreActions）",
      appJs.includes("setLiveTransport") && appJs.includes("goInert") && appJs.includes("renderIdentity")
      && reported.length > 0 && reported.every((a) => tpDecl.monitoring.coreActions.includes(a)),
      `上报动作=${[...new Set(reported)].join("/")}`);
  }
  stationSrv.close();
  rmSync(process.env.BRIDGE_SHARE_DIR, { recursive: true, force: true });

  // ══ E. 宿主桥 host.use('db'/'user') 两态（vm 跑 taskpane/host-bridge.js） ══
  const hostBridgeJs = readFileSync(join(TASKPANE_DIR, "host-bridge.js"), "utf-8");
  const page = makePageContext({ declarationText: readFileSync(join(TASKPANE_DIR, "index.html"), "utf-8").match(new RegExp(`id="${MONITORING_DECL_ID}">([\\s\\S]*?)</script`))[1] });
  page.sandbox.jusciteMonitor = { report: (a, o, e, d) => { page.monitorReports.push({ a, o, e, d }); return true; } };
  const loadErr = runInPage(page, hostBridgeJs, "host-bridge.js");
  const hb = page.sandbox.jusciteHostBridge;
  {
    // E1 初始 inert：use 即答全合成假身；inertHealth 全 no-op；零报错
    const rU = await hb.use("user");
    const rD = await hb.use("db");
    const ih = hb.healthReporter();
    const noOpOk = ih.report("连接", "成功") === false && (ih.flush(), true);
    check("E1 初始降级态（use 即答假身：synthetic/demo 显式标记+演示文案；inertHealth 全 no-op 零报错）",
      !loadErr && !!hb && rU.mode === "inert" && rU.data.synthetic === true && rU.data.demo === true
      && rD.mode === "inert" && rD.data.synthetic === true && hb.health().mode === "inert" && noOpOk
      && page.logs.error.length === 0,
      `user=${rU.data.displayName}`);
    // E2 能力闭集
    let rejected = null;
    await hb.use("fs").catch((e) => { rejected = e; });
    check("E2 能力闭集（'db'/'user' 外拒用）", !!rejected && /未知能力/.test(rejected.message));
    // E3 live 真身（注入通道）：经通道取数；通道失败=如实失败不换假身
    const ops = [];
    hb.setLiveTransport(async (op) => {
      ops.push(op);
      if (op === "db.summary") throw new Error("请求超时: db.summary");
      return { op, identity: { kind: "workbench-bridge" } };
    });
    const lu = await hb.use("user");
    const ld = await hb.use("db");
    check("E3 真身态（use 经注入通道发 op user.identity/db.summary；通道失败=data=null+具名 error，不悄悄换假身）",
      ops.join() === "user.identity,db.summary" && lu.mode === "live" && lu.data.op === "user.identity"
      && ld.mode === "live" && ld.data === null && /超时/.test(ld.error) && !ld.data?.synthetic
      && page.elements["degrade-banner"].hidden === true && page.monitorReports.some((r) => r.a === "连接" && r.o === "成功"));
    // E4 live→inert 降级：横幅+假身回位+断开上报（仅态位迁移一次，重试不刷屏）
    hb.goInert("合成测试降级");
    const banner = page.elements["degrade-banner"];
    const rAfter = await hb.use("user");
    const disconnectReports = page.monitorReports.filter((r) => r.a === "断开");
    hb.goInert("合成测试降级再来一次");
    check("E4 降级横幅+假身回位（横幅显示且文案含「全合成」；use 回假身；断开失败上报恰一次）",
      banner.hidden === false && banner.textContent.includes("全合成") && rAfter.mode === "inert"
      && rAfter.data.synthetic === true && disconnectReports.length === 1
      && disconnectReports[0].e === "local_bridge_unavailable"
      && page.monitorReports.filter((r) => r.a === "断开").length === 1,
      `横幅=${banner.textContent.slice(0, 24)}…`);
    check("E5 降级态零报错（E1-E4 全程序零未捕获异常/零 console.error）", page.logs.error.length === 0);
  }

  // ══ E6-E9. 真协议端到端（spawn 真 office-bridge，隔离 :3090 段） ══
  const stateDir = mkdtempSync(join(tmpdir(), "juscite-mon-ob-"));
  const port = await freePortAvoidingPooled();
  pooledPorts.add(port);
  const monLogs = [];
  const bridge = await startOfficeBridge({ port, stateDir, taskpaneDir: TASKPANE_DIR, log: (m) => monLogs.push(m) });
  {
    const info = await (await fetch(`http://127.0.0.1:${port}/pair-info`)).json();
    const frames = [];
    const ws = new WebSocket(`ws://127.0.0.1:${port}/ws`);
    await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
    ws.on("message", (d) => frames.push(JSON.parse(String(d))));
    ws.send(JSON.stringify({ kind: "pair", sequence: 1, bootstrapToken: info.bootstrapToken, clientId: "mon-synth", clientName: "juscite-taskpane", pluginVersion: "0.0.0", pinnedPublicKeySha256: info.publicKeySha256, surface: "wps" }));
    const until = async (pred, ms = 4000) => {
      const dl = Date.now() + ms;
      while (Date.now() < dl) { const f = frames.find(pred); if (f) return f; await sleep(50); }
      return null;
    };
    await until((f) => f.kind === "ready");
    // E6 真身身份：user.identity 经帧协议回服务器自有事实（与 /healthz 实例一致）
    ws.send(JSON.stringify({ kind: "request", sequence: 2, requestId: "mon-uid", op: "user.identity", payload: {} }));
    const r1 = await until((f) => f.kind === "response" && f.requestId === "mon-uid");
    const hz = await (await fetch(`http://127.0.0.1:${port}/healthz`)).json();
    check("E6 真身身份经真协议（user.identity=桥自有事实，serverInstanceId 与 /healthz 一致；surface 随配对上下文）",
      !!r1 && r1.ok === true && r1.result.identity.serverInstanceId === hz.serverInstanceId
      && r1.result.identity.surface === "wps" && r1.result.identity.kind === "workbench-bridge");
    // E7 db 未接线=fail-closed（显式 not_wired，不编造、不塞演示数据）
    ws.send(JSON.stringify({ kind: "request", sequence: 3, requestId: "mon-db", op: "db.summary", payload: {} }));
    const r2 = await until((f) => f.kind === "response" && f.requestId === "mon-db");
    check("E7 真身 db 未接线 fail-closed（db.summary=ok:false db_not_wired，不悄悄塞演示数据冒充真身）",
      !!r2 && r2.ok === true && r2.result.ok === false && r2.result.error === "db_not_wired");
    // E8 桥侧监控收件面 + taskpane 页面/孪生件同源伺服
    const sinkOk = await fetch(`http://127.0.0.1:${port}/api/v1/monitoring/report`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ source: "office-taskpane", events: [{ action: "连接", outcome: "成功" }] }),
    });
    const sinkBad = await fetch(`http://127.0.0.1:${port}/api/v1/monitoring/report`, { method: "POST", body: "{" });
    const [pHtml, pMon, pHb] = await Promise.all([
      fetch(`http://127.0.0.1:${port}/taskpane/`),
      fetch(`http://127.0.0.1:${port}/taskpane/monitor.js`),
      fetch(`http://127.0.0.1:${port}/taskpane/host-bridge.js`),
    ]);
    const htmlText = await pHtml.text();
    check("E8 桥侧收件面+页面同源伺服（合法 204/坏 JSON 400；index/monitor/host-bridge 200 且页挂声明+横幅位）",
      sinkOk.status === 204 && sinkBad.status === 400 && pHtml.status === 200 && pMon.status === 200 && pHb.status === 200
      && htmlText.includes(MONITORING_DECL_ID) && htmlText.includes("degrade-banner")
      && monLogs.some((l) => l.includes("[monitoring]") && l.includes("连接")),
      `sink=${sinkOk.status}/${sinkBad.status} page=${pHtml.status}/${pMon.status}/${pHb.status}`);
    ws.close();
    await sleep(150);
  }
  await bridge.stop();
  rmSync(stateDir, { recursive: true, force: true });

  // E9 工作台经 onRequest 接线的真数据点（合成材料经真通道——测试一律合成纪律；
  // 端口避开连接池旧端口，见 freePortAvoidingPooled 注记）
  {
    const stateDir2 = mkdtempSync(join(tmpdir(), "juscite-mon-ob2-"));
    const port2 = await freePortAvoidingPooled();
    pooledPorts.add(port2);
    const bridge2 = await startOfficeBridge({
      port: port2, stateDir: stateDir2, taskpaneDir: TASKPANE_DIR,
      onRequest: async (frame) => ({ op: frame.op, synthetic: true, matters: 7, note: "合成演示数据（经真通道回）" }),
      log: () => {},
    });
    const info = await (await fetch(`http://127.0.0.1:${port2}/pair-info`)).json();
    const frames = [];
    const ws = new WebSocket(`ws://127.0.0.1:${port2}/ws`);
    await new Promise((r, j) => { ws.on("open", r); ws.on("error", j); });
    ws.on("message", (d) => frames.push(JSON.parse(String(d))));
    ws.send(JSON.stringify({ kind: "pair", sequence: 1, bootstrapToken: info.bootstrapToken, clientId: "mon-synth-2", pinnedPublicKeySha256: info.publicKeySha256, surface: "wps" }));
    const until = async (pred, ms = 4000) => {
      const dl = Date.now() + ms;
      while (Date.now() < dl) { const f = frames.find(pred); if (f) return f; await sleep(50); }
      return null;
    };
    await until((f) => f.kind === "ready");
    ws.send(JSON.stringify({ kind: "request", sequence: 2, requestId: "mon-db2", op: "db.summary", payload: {} }));
    const r = await until((f) => f.kind === "response" && f.requestId === "mon-db2");
    check("E9 工作台接线态 db 真数据点（onRequest 注入经帧协议回，合成材料走真通道）",
      !!r && r.ok === true && r.result.op === "db.summary" && r.result.synthetic === true && r.result.matters === 7);
    ws.close();
    await sleep(150);
    await bridge2.stop();
    rmSync(stateDir2, { recursive: true, force: true });
  }

  console.log(`[monitoring-synth] 共 ${results.length} 项，失败 ${failed}`);
  console.log(failed === 0 ? "MONITORING_SYNTH_PASS" : "MONITORING_SYNTH_FAIL");
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error("[monitoring-synth] 异常退出:", err);
  console.log("MONITORING_SYNTH_FAIL");
  process.exit(1);
});
