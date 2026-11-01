// taskpane 主逻辑（自写）：宿主适配 → 桥配对（/pair-info 拿 token+指纹 → ws /ws pair 帧）
// → 会话 UI（发送/选区快照/插回光标）。S1-S3 阶段 request 走桥的 echo 桩；S5 换 agent 会话接线。
// 监控接线（逆向吸收波二·条 2）：连接/断开/提交/插入/读取经 jusciteMonitor 三值上报（本地通道）。
// 宿主桥（条 3）：ready 后 setLiveTransport(request)=真身；桥不可达/断开 goInert=演示假身+降级横幅。
(function () {
  "use strict";

  var monitor = window.jusciteMonitor || { report: function () { return false; } };

  // 失败→错误枚举映射（闭集成员；未知归 unknown_error 兜底）
  function errTypeOf(err) {
    var msg = String((err && err.message) || err);
    if (/超时/.test(msg)) return "local_bridge_timeout";
    if (/预览模式没有宿主文档|宿主/.test(msg)) return "host_unsupported";
    return "unknown_error";
  }

  var state = {
    adapter: null,
    ws: null,
    paired: false,
    sequence: 0,
    pending: Object.create(null), // requestId -> {resolve, reject}
    snapshot: "",
    lastReply: "",
    retryTimer: null,
  };

  var els = {
    badge: document.getElementById("host-badge"),
    dot: document.getElementById("link-dot"),
    chat: document.getElementById("chat"),
    note: document.getElementById("boot-note"),
    input: document.getElementById("input"),
    send: document.getElementById("btn-send"),
    insert: document.getElementById("btn-insert"),
    snapshot: document.getElementById("btn-snapshot"),
    snapshotHint: document.getElementById("snapshot-hint"),
  };

  function say(text, who, meta) {
    var div = document.createElement("div");
    div.className = "msg " + (who === "me" ? "me" : "them");
    if (meta) {
      var m = document.createElement("span");
      m.className = "meta";
      m.textContent = meta;
      div.appendChild(m);
    }
    div.appendChild(document.createTextNode(text));
    els.chat.appendChild(div);
    els.chat.scrollTop = els.chat.scrollHeight;
  }

  function note(text, warn) {
    els.note.textContent = text;
    els.note.className = warn ? "note warn" : "note";
  }

  function setPaired(on) {
    state.paired = on;
    els.dot.className = "dot " + (on ? "on" : "off");
    els.dot.title = on ? "已连接工作台桥" : "未连接——请启动工作台";
    els.send.disabled = !on;
  }

  // ── 宿主桥（条 3）：按当前态位呈现身份行——真身=经协议取的工作台桥身份；演示态=全合成假身 ──
  function renderIdentity() {
    var hb = window.jusciteHostBridge;
    if (!hb) return;
    hb.use("user").then(function (r) {
      if (r.mode === "live" && r.data && !r.error) {
        var id = r.data.identity || {};
        note("工作台真身已连（身份源=" + (r.data.source || "office-bridge")
          + (id.serverInstanceId ? "，实例 " + String(id.serverInstanceId).slice(0, 8) : "") + "）");
      } else if (r.mode === "live") {
        note("工作台桥已连，但身份读取失败：" + (r.error || "未知"), true);
      } else {
        note("本地演示态：身份与案卷数据为全合成演示假身（启动工作台后自动恢复真身）", true);
      }
    })["catch"](function () { /* use 只在能力闭集外 reject，此处不达 */ });
  }

  // ── 桥连接：同源取配对材料 → ws 首帧 pair（token + 客户端声明 + 公钥指纹钉扎）──
  function connectBridge() {
    fetch("/pair-info")
      .then(function (r) { return r.json(); })
      .then(function (info) {
        var proto = location.protocol === "https:" ? "wss://" : "ws://";
        var ws = new WebSocket(proto + location.host + "/ws");
        state.ws = ws;
        ws.onopen = function () {
          sendFrame("pair", {
            bootstrapToken: info.bootstrapToken,
            clientId: "taskpane-" + Math.random().toString(36).slice(2, 8),
            clientName: "juscite-taskpane",
            pluginVersion: "0.0.0",
            pinnedPublicKeySha256: info.publicKeySha256,
            surface: state.adapter.surface,
          });
        };
        ws.onmessage = function (ev) {
          var frame;
          try { frame = JSON.parse(ev.data); } catch { return; }
          handleFrame(frame);
        };
        ws.onclose = function () {
          setPaired(false);
          note("工作台桥已断开，10 秒后重试…", true);
          if (window.jusciteHostBridge) window.jusciteHostBridge.goInert("桥已断开");
          renderIdentity();
          clearTimeout(state.retryTimer);
          state.retryTimer = setTimeout(connectBridge, 10000);
        };
        ws.onerror = function () { /* onclose 统一收尾 */ };
      })
      .catch(function () {
        note("本地桥未响应——请先启动工作台桌面进程（127.0.0.1）", true);
        if (window.jusciteHostBridge) window.jusciteHostBridge.goInert("本地桥未响应");
        renderIdentity();
        clearTimeout(state.retryTimer);
        state.retryTimer = setTimeout(connectBridge, 10000);
      });
  }

  function sendFrame(kind, payload) {
    if (!state.ws || state.ws.readyState !== 1) return null;
    state.sequence += 1;
    var frame = Object.assign({ kind: kind, sequence: state.sequence }, payload);
    state.ws.send(JSON.stringify(frame));
    return frame;
  }

  function request(op, payload) {
    return new Promise(function (resolve, reject) {
      var requestId = "r" + state.sequence + "-" + Date.now();
      state.pending[requestId] = { resolve: resolve, reject: reject };
      sendFrame("request", { op: op, requestId: requestId, payload: payload || {} });
      setTimeout(function () {
        if (state.pending[requestId]) {
          delete state.pending[requestId];
          reject(new Error("请求超时: " + op));
        }
      }, 30000);
    });
  }

  function handleFrame(frame) {
    if (frame.kind === "ready") {
      setPaired(true);
      note("已连接工作台桥（surface=" + state.adapter.surface + "）");
      // 条 3：真身通道注入（此后 host.use('db'/'user') 经帧协议取真数据/身份）
      if (window.jusciteHostBridge) window.jusciteHostBridge.setLiveTransport(request, { detail: "surface=" + state.adapter.surface });
      renderIdentity();
      return;
    }
    if (frame.kind === "error") {
      note("桥错误：" + (frame.code || "unknown") + "——" + (frame.message || ""), true);
      return;
    }
    if (frame.kind === "response" && frame.requestId && state.pending[frame.requestId]) {
      var p = state.pending[frame.requestId];
      delete state.pending[frame.requestId];
      if (frame.ok) p.resolve(frame.result);
      else p.reject(new Error(frame.error || "请求失败"));
      return;
    }
    if (frame.kind === "run.events" && frame.payload && frame.payload.text) {
      say(frame.payload.text, "them", "工作台");
      state.lastReply = frame.payload.text;
      return;
    }
    if (frame.kind === "tool.request") {
      // S5 反向操作文档的预留入口：当前一期只回未实现，不吞帧
      sendFrame("request", { op: "tool.response", requestId: frame.requestId, payload: { implemented: false } });
    }
  }

  function doSend() {
    var text = els.input.value.trim();
    if (!text || !state.paired) return;
    say(text, "me", "我");
    if (state.snapshot) say("〔选区快照〕" + state.snapshot, "me");
    els.input.value = "";
    request("chat", { text: text, selection: state.snapshot, surface: state.adapter.surface })
      .then(function (result) {
        monitor.report("提交", "成功");
        var reply = (result && result.reply) || null;
        if (reply) { say(reply, "them", "工作台"); state.lastReply = reply; }
        else say("（桥已收到；agent 会话接线属 S5——当前为 S1 桥桩回执: " + JSON.stringify(result) + "）", "them");
      })
      .catch(function (err) {
        monitor.report("提交", "失败", errTypeOf(err));
        say("发送失败：" + err.message, "them");
      });
  }

  // ── 启动 ──
  els.send.disabled = true;
  els.send.addEventListener("click", doSend);
  els.input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); }
  });
  els.snapshot.addEventListener("click", function () {
    state.adapter.getSelection().then(function (text) {
      state.snapshot = text;
      monitor.report("读取", "成功");
      els.snapshotHint.textContent = text
        ? "已抓取 " + text.length + " 字（随下一条消息发送）"
        : "当前无选区文字";
    })["catch"](function (err) {
      monitor.report("读取", "失败", errTypeOf(err));
      els.snapshotHint.textContent = "选区读取失败：" + err.message;
    });
  });
  els.insert.addEventListener("click", function () {
    var text = state.lastReply;
    if (!text) { note("还没有可插入的工作台回复", true); return; }
    state.adapter.insertAtCursor(text).then(function () {
      monitor.report("插入", "成功");
      note("已插回光标处");
    })
      ["catch"](function (err) {
        monitor.report("插入", "失败", errTypeOf(err));
        note("插入失败：" + err.message, true);
      });
  });

  window.jusciteHostAdapters.initHost().then(function (adapter) {
    state.adapter = adapter;
    els.badge.textContent = adapter.label;
    note(adapter.surface === "standalone"
      ? "独立预览模式：宿主（Word/WPS）内打开本页才有文档能力"
      : "宿主就绪（" + adapter.label + "），正在连接本地桥…");
    connectBridge();
  });
})();
