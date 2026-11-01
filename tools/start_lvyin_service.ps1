# 律引（JusBench）V8 · T07 —— opencode 隔离服务启动包装（产品拓扑复刻用）。
#
# 用途：在命令行复刻与产品桌面一致的隔离服务（固定 127.0.0.1:43127），
#       供 tools/e02_tool_closure.py 等负测 harness 连接；
#       正式桌面启动仍走产品包脚本（scripts/launch_desktop_trial.py / 服务托管），不经过本文件。
#
# 用法（Git Bash）:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools/start_lvyin_service.ps1
# 前台运行，Ctrl+C 停止；或另开终端 netstat -ano | findstr 43127 后 taskkill /F /PID <pid>。
#
# 安全边界：运行根只指向 %APPDATA%\Juscite；绝不指向 %APPDATA%\JusBench（v6 遗留真数据）。

param(
  [string]$Oc28 = "D:\Codex\1.法律工作区\jusbench工作区\oc28",  # 上游只读检出（serve 入口，本脚本不写它）
  [int]$Port = 43127                                            # 产品隔离服务固定端口
)

$ErrorActionPreference = "Stop"

# ---- 产品运行根对齐（四个 XDG 变量决定 opencode 的状态/数据/配置/缓存落点）----
# XDG_STATE_HOME：服务注册（state\opencode\service-local.json，含 url+password）与会话状态。
$env:XDG_STATE_HOME  = Join-Path $env:APPDATA "Juscite\state"
# XDG_DATA_HOME：数据库与日志（data\opencode\log\，models.dev 观测看这里）。
$env:XDG_DATA_HOME   = Join-Path $env:APPDATA "Juscite\data"
# XDG_CONFIG_HOME：opencode.json（zhipu-smoke provider + 律引法律 profile）。
$env:XDG_CONFIG_HOME = Join-Path $env:APPDATA "Juscite\config"
# XDG_CACHE_HOME：进程缓存。
$env:XDG_CACHE_HOME  = Join-Path $env:APPDATA "Juscite\cache"

# models.dev 目录禁轮询：oc28 packages/cli/src/server-process.ts:113
# models.fetch = !truthy(OPENCODE_DISABLE_MODELS_FETCH)，置真即不 fork 刷新循环
#（T06 实测：缺省时默认每 5 分钟拉一次 models.dev）。
$env:OPENCODE_DISABLE_MODELS_FETCH = "1"

# 渠道与版本标记：只影响日志标识与 /api/info 的 version 字段，便于识别本复刻进程。
$env:OPENCODE_CHANNEL = "local"
$env:OPENCODE_VERSION = "2.0.28-local-t07"

# bun 解析：优先 PATH，回退本机安装位置（%USERPROFILE%\.bun\bun.exe，本机实测 1.4.2；
# 官方安装器布局 %USERPROFILE%\.bun\bin\bun.exe 一并兜底）。
$bun = (Get-Command bun -ErrorAction SilentlyContinue).Source
if (-not $bun) {
  foreach ($cand in @(
    (Join-Path $env:USERPROFILE ".bun\bun.exe"),
    (Join-Path $env:USERPROFILE ".bun\bin\bun.exe")
  )) { if (Test-Path $cand) { $bun = $cand; break } }
}
if (-not $bun) { throw "bun not found (PATH or $env:USERPROFILE\.bun)" }

Write-Host "[lvyin] state =$($env:XDG_STATE_HOME)"
Write-Host "[lvyin] data  =$($env:XDG_DATA_HOME)"
Write-Host "[lvyin] config=$($env:XDG_CONFIG_HOME)"
Write-Host "[lvyin] serving http://127.0.0.1:$Port (oc28=$Oc28, models_fetch=disabled)"

Push-Location $Oc28
try {
  & $bun run --cwd packages/cli --define=OPENCODE_VERSION=process.env.OPENCODE_VERSION `
    src/index.ts serve --service --hostname 127.0.0.1 --port $Port
}
finally {
  Pop-Location
}
