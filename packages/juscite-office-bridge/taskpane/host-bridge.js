// 宿主桥 API 同构（逆向吸收波二·条 3；B-Office插件复刻方案-v1 §六风险 4 落地；净室自写）。
// host.use('db'/'user') 形状（机制学习自 appifact 宿主 API 样本——形状可学、实现自写）：
//   工作台在 = 真身：经 office-bridge 帧协议 request op（user.identity / db.summary）取真数据/身份；
//   工作台不在 = inert 降级：use() 即答合成演示假身（零网络零报错）+ inertHealth() 全 no-op
//   + 降级提示横幅——不白屏不报错（方案 §六风险 4）。
// 两态切换：app.js 在桥配对成功后 setLiveTransport(request) 注入真身通道；桥不可达/断开时
// goInert(reason) 进入降级态。假身纪律：演示数据一律全合成并带显式 synthetic 标记，绝不冒充真身；
// 真身通道失败=如实失败（data=null+具名 error），不悄悄换假身。
(function (global) {
  "use strict";

  var CAPABILITIES = ["db", "user"]; // 能力闭集
  var BANNER_ID = "degrade-banner";

  var state = { mode: "inert", reason: "尚未连接工作台", transport: null, since: Date.now(), inertReported: false };

  // ── 合成演示假身（全合成材料——仅降级态呈现，显式标记，绝不冒充真身）──
  function demoUser() {
    return { synthetic: true, demo: true, note: "演示身份（全合成）",
      displayName: "演示用户（合成）", account: "demo-synthetic@invalid" };
  }
  function demoDb() {
    return { synthetic: true, demo: true, note: "演示案卷概览（全合成）",
      matters: 3, sessions: 12, updatedAt: null };
  }

  function banner(on, text) {
    var el = document.getElementById(BANNER_ID);
    if (!el) return;
    el.hidden = !on;
    if (text) el.textContent = text;
  }

  function use(cap) {
    if (CAPABILITIES.indexOf(cap) < 0) return Promise.reject(new Error("未知能力: " + cap));
    if (state.mode === "live" && state.transport) {
      var op = cap === "user" ? "user.identity" : "db.summary";
      return state.transport(op, {}).then(function (result) {
        return { mode: "live", capability: cap, data: result };
      }, function (err) {
        // 真身通道失败=如实失败（调用方可据 mode/error 甄别），不悄悄换假身
        return { mode: "live", capability: cap, data: null, error: String((err && err.message) || err) };
      });
    }
    var demo = cap === "user" ? demoUser() : demoDb();
    return Promise.resolve({ mode: "inert", capability: cap, data: demo });
  }

  // ── inertHealth 全 no-op 降级（样本同构：宿主缺失时健康/监控面 no-op 化，调用零效应零报错）──
  function inertHealth() {
    return { report: function () { return false; }, flush: function () {},
      note: "inert：工作台不在，健康面上报 no-op" };
  }
  function liveHealth() { return global.jusciteMonitor || inertHealth(); }

  function setLiveTransport(transport, opts) {
    state.mode = "live";
    state.transport = transport;
    state.reason = "";
    state.since = Date.now();
    state.inertReported = false;
    banner(false);
    if (global.jusciteMonitor) {
      global.jusciteMonitor.report("连接", "成功", null, (opts && opts.detail) || null);
    }
  }

  function goInert(reason) {
    var wasLive = state.mode === "live";
    state.mode = "inert";
    state.transport = null;
    state.reason = String(reason || "工作台不可达");
    state.since = Date.now();
    banner(true, "工作台未连接——" + state.reason
      + "；当前为本地演示态（数据全合成），启动工作台后自动恢复。");
    // 监控只在态位迁移时上报（重试循环不刷屏）：live→inert 报「断开」，首入 inert 报「连接失败」
    if (!state.inertReported && global.jusciteMonitor) {
      global.jusciteMonitor.report(wasLive ? "断开" : "连接", "失败", "local_bridge_unavailable", state.reason);
      state.inertReported = true;
    }
  }

  global.jusciteHostBridge = {
    use: use,
    health: function () { return { mode: state.mode, reason: state.reason, since: state.since }; },
    healthReporter: function () { return state.mode === "live" ? liveHealth() : inertHealth(); },
    setLiveTransport: setLiveTransport,
    goInert: goInert,
    CAPABILITIES: CAPABILITIES.slice(),
  };
})(window);
