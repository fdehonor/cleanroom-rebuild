[CmdletBinding()]
param([ValidateSet('Recommended','Full','ExistingOnly')][string]$IDEProfile = 'Recommended')
$ErrorActionPreference = 'Stop'
$installer = Join-Path $PSScriptRoot 'Install-CleanroomRebuild.ps1'
if (-not (Test-Path -LiteralPath $installer)) { throw 'Install-CleanroomRebuild.ps1 is missing.' }
& $installer -AcceptThirdPartyLicenses -IDEProfile $IDEProfile -AgentProviders All
if ($LASTEXITCODE -ne 0) { throw "Repair failed with exit code $LASTEXITCODE" }
