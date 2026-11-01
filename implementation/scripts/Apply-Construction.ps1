# 产品名：律引（Lvyin / Juscite）｜工程代号：JusBench（历史保留）
param([Parameter(Mandatory)][string]$Repository, [switch]$Apply)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath $Repository).Path
$packageRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pin = Get-Content -LiteralPath (Join-Path $packageRoot 'implementation\config\upstream-pin.json') -Raw | ConvertFrom-Json
$head = & git -C $repoRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $head.Trim() -ne $pin.commit) { throw 'Exact pinned source commit required.' }
$dirty = & git -C $repoRoot status --porcelain
if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Use a clean separate checkout; preserve all ongoing work.' }
$patches = Get-ChildItem -LiteralPath (Join-Path $packageRoot 'implementation\patches') -Filter '*.patch' | Sort-Object Name
foreach ($patch in $patches) {
  & git -C $repoRoot apply --check -- $patch.FullName
  if ($LASTEXITCODE -ne 0) { throw "Patch check failed: $($patch.Name)" }
}
if (-not $Apply) { Write-Output 'Read-only patch checks complete. No files were changed.'; return }
foreach ($patch in $patches) {
  & git -C $repoRoot apply -- $patch.FullName
  if ($LASTEXITCODE -ne 0) { throw "Patch failed: $($patch.Name); inspect this separate checkout, do not reset." }
}
Write-Output 'Applied only delivered diffs to the explicitly selected checkout. Build and runtime tests still required.'
