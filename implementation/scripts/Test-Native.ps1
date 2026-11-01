# 产品名：律引（Lvyin / Juscite）｜工程代号：JusBench（历史保留）
param([Parameter(Mandatory)][string]$Repository, [string]$Bun='bun', [switch]$Run)
$ErrorActionPreference='Stop'
$repoRoot=(Resolve-Path -LiteralPath $Repository).Path
Write-Output 'Runs app/desktop typecheck and build in the provided checkout; no install, deployment, push or credential access.'
if (-not $Run) { Write-Output 'Preflight only. Native build/runtime checks NOT_RUN.';return }
foreach ($name in @('app','desktop')) {
  Push-Location -LiteralPath (Join-Path $repoRoot "packages\$name")
  try {
    & $Bun run typecheck
    if ($LASTEXITCODE -ne 0) {throw "Typecheck failed: $name"}
    & $Bun run build
    if ($LASTEXITCODE -ne 0) {throw "Build failed: $name"}
  } finally {Pop-Location}
}
Write-Output 'Typecheck/build complete; real model, privacy, recoverability and legal tests still required.'
