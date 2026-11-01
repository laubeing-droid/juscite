# 产品名：律引（Lvyin / Juscite）｜工程代号：JusBench（历史保留）
param([Parameter(Mandatory = $true)][string]$SourceRepo)
$ErrorActionPreference = 'Stop'
$expected = '026b106bc5d41b679ffc413264229c340871e4d3'
$repo = (Resolve-Path -LiteralPath $SourceRepo).Path
$patch = Join-Path $PSScriptRoot 'opencode-v2.0.28-legal-workbench.patch'
$head = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $head -ne $expected) { throw "Source HEAD must be $expected; found $head" }
& git -C $repo apply --check -- $patch
if ($LASTEXITCODE -ne 0) { throw 'Patch cannot be applied cleanly. No files were changed.' }
Write-Output 'PASS: exact fixed HEAD and git apply --check. This script does not apply the patch or build.'
