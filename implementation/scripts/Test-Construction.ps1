# 产品名：律引（Lvyin / Juscite）｜工程代号：JusBench（历史保留）
param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$packageRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$evidenceDir = Join-Path $packageRoot 'evidence-design'
New-Item -ItemType Directory -Path $evidenceDir -Force | Out-Null
& $Python -X utf8 -B -m unittest discover -s (Join-Path $packageRoot 'implementation\tests') -v 2>&1 |
  Tee-Object -FilePath (Join-Path $evidenceDir 'python-wiring-tests.txt')
if ($LASTEXITCODE -ne 0) { throw 'Construction wiring tests failed; product tests remain NOT_RUN.' }
Write-Output 'Only delivered Python wiring was tested. No product/Agent/legal integration PASS.'
