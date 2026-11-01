# vendored office.js（Word 分支同源库）

- 来源：`https://appsforoffice.microsoft.com/lib/1.1/hosted/`（微软官方 Office.js 公开 CDN，
  2026-11-01 经本机代理一次性拉取；License 为微软 Office.js 发布许可，逐字文件零改动）。
- 用途：Word 宿主分支从**同源**加载 Office.js——满足 S2 断言"两宿主内页面加载无外呼（除 127.0.0.1）"。
- 已取：office.js（加载器）、o15apptofilemappingtable.js、MicrosoftAjax.js（旧内核回退）、
  word-win32-16.01.js（Word/Windows 桌面主体）、telemetry/oteljs_agave.js。
- 未取到（源站 404，对本机无影响——本机 Word 为 2007 无 WEF，Word 分支尚未有可实测宿主）：
  office_strings.<locale>.js、word-mac/ios/web/android 变体。
- 已知点：office.js 内部对**旧浏览器**（无 Promise）才回退 aspnetcdn 的 MicrosoftAjax、仅 SSO
  才拉 msauth 的 msal——两条都是条件路径，现代 WebView 不触发；零外呼断言以本仓自有文件扫描为准。
