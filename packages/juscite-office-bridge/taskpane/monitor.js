// 声明式监控白名单契约 · taskpane 静态页运行时（逆向吸收波二·条 2；净室自写）。
// 与 @juscite/vizb shared/html.ts 的 monitoringRuntimeJs() 是同一契约的两面实现：
// 本页零构建直发（静态文件），vizb 侧服务模板族——两实现由 tools/bridge/monitoring_synthetic.mjs
// 同一断言矩阵各锚其面（防漂移）。契约形状学习自 appifact 运行时样本（无许可仓——机制可学、
// 词表/文案零采用）：读页面内嵌声明（key+monitoring{coreActions}）→ 上报只收声明内动作 →
// 结果三值 → 错误枚举闭集 → 未声明动作丢弃并警告。
// 我方化对照注记：上样本走 Slack 云告警通道——我方零外呼红线，不设任何云告警面；
// 通道=本地（本地 console 日志恒记 + 同源本地桥 best-effort POST，失败静默不影响页面）。
(function (global) {
  "use strict";

  var decl = null;
  try {
    var el = document.getElementById("juscite-monitoring-declaration");
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
})(window);
