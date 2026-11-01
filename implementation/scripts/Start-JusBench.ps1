# 产品名：律引（Lvyin / Juscite）｜工程代号：JusBench（历史保留）
param([Parameter(Mandatory)][string]$Repository, [string]$Bun='bun', [switch]$Run)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath $Repository).Path
$desktopRoot = Join-Path $repoRoot 'packages\desktop'
$config = Get-Content -LiteralPath (Join-Path $desktopRoot 'package.json') -Raw | ConvertFrom-Json
if ($config.version -ne '2.0.28' -or -not $config.scripts.dev) { throw 'Expected pinned native desktop source.' }
if (-not (Test-Path -LiteralPath (Join-Path $repoRoot 'node_modules'))) { throw 'Dependencies absent. Authorized construction must install from the pinned lockfile; this script does not install.' }
$main = Get-Content -LiteralPath (Join-Path $desktopRoot 'src\main\index.ts') -Raw
if ($main -notmatch 'service|JusBench' -or $main -notmatch 'XDG_STATE_HOME') { throw 'Apply the product isolation patch before launch.' }
Write-Output "Working directory: $desktopRoot"
Write-Output 'Command: bun run dev; native UI, dedicated product profile; no JC/Harness requirement.'
if (-not $Run) { Write-Output 'Preflight only; no process started. Use -Run in the separate authorized checkout.'; return }
Push-Location -LiteralPath $desktopRoot
try { & $Bun run dev; if ($LASTEXITCODE -ne 0) { throw 'Native desktop exited with a failure.' } }
finally { Pop-Location }
