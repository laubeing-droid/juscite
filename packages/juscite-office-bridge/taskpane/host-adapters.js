// 宿主双适配层（方案 §五 S2）：同一页面，两套宿主 API 探测分支。
//   word 分支：Office.js（从同源 vendor/officejs/office.js 加载——零外呼，本地伺服）
//   wps 分支：WPS 客户端注入的 window.wps jsapi（无需外部库）
//   standalone 分支：普通浏览器/宿主缺失 → 降级提示（方案 §六.4：不白屏不报错）
// 选区读取/插入文本是本层全部文档能力面（一期文字，Excel/PPT 仅协议留名）。
// 注：WPS 分支的 jsapi 调用形状按 WPS 开放平台公开文档书写，本机尚未实测（S4 待证）。
(function (global) {
  "use strict";

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src; s.async = true;
      s.onload = function () { resolve(); };
      s.onerror = function () { reject(new Error("脚本加载失败: " + src)); };
      document.head.appendChild(s);
    });
  }

  var wordAdapter = {
    surface: "word",
    label: "Word",
    init: function () {
      if (global.Office) return Promise.resolve();
      return loadScript("./vendor/officejs/office.js").then(function () {
        if (!global.Office) throw new Error("office.js 已加载但未注册全局 Office");
      });
    },
    ready: function () {
      return new Promise(function (resolve) {
        global.Office.onReady(function () { resolve(); });
      });
    },
    getSelection: function () {
      return Word.run(function (ctx) {
        var sel = ctx.document.getSelection();
        sel.load("text");
        return ctx.sync().then(function () { return sel.text || ""; });
      });
    },
    insertAtCursor: function (text) {
      return Word.run(function (ctx) {
        var sel = ctx.document.getSelection();
        sel.insertText(text, "Replace");
        return ctx.sync().then(function () { return true; });
      });
    },
  };

  var wpsAdapter = {
    surface: "wps",
    label: "WPS",
    init: function () {
      if (!global.wps) throw new Error("WPS jsapi 未注入（window.wps 缺失）");
      return Promise.resolve();
    },
    ready: function () { return Promise.resolve(); },
    getSelection: function () {
      var selection = global.wps.WpsApplication().Selection;
      return Promise.resolve(selection ? String(selection.Text || "") : "");
    },
    insertAtCursor: function (text) {
      var selection = global.wps.WpsApplication().Selection;
      if (selection) selection.TypeText(text);
      return Promise.resolve(true);
    },
  };

  var standaloneAdapter = {
    surface: "standalone",
    label: "预览",
    init: function () { return Promise.resolve(); },
    ready: function () { return Promise.resolve(); },
    getSelection: function () { return Promise.resolve(""); },
    insertAtCursor: function () { return Promise.reject(new Error("预览模式没有宿主文档")); },
  };

  function detectHost() {
    // WPS 先判：WPS 宿主里不会注入 Office 全局；Word 宿主加载 office.js 后才有 Office 全局。
    // 独立浏览器两个都没有 → 预览分支。宿主注入顺序未知时不猜（fail-closed 到预览）。
    if (global.wps) return wpsAdapter;
    if (global.Office) return wordAdapter;
    return null; // Word 宿主需要先拉本地 office.js —— 由 initHost 决定
  }

  function initHost() {
    var direct = detectHost();
    if (direct) return direct.init().then(function () { return direct; });
    // Word 分支的 Office 全局由 office.js 自建：尝试同源加载；失败即预览分支（如实降级）
    return wordAdapter.init().then(function () { return wordAdapter; })["catch"](function () { return standaloneAdapter; });
  }

  global.jusciteHostAdapters = {
    detectHost: detectHost,
    initHost: initHost,
    wordAdapter: wordAdapter,
    wpsAdapter: wpsAdapter,
    standaloneAdapter: standaloneAdapter,
  };
})(window);
