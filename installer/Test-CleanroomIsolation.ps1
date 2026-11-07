[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$server = Join-Path $env:USERPROFILE '.codex\local-marketplaces\cleanroom-tools\plugins\cleanroom-rebuild\server'
$python = [Environment]::GetEnvironmentVariable('CLEANROOM_GPU_PYTHON', 'User')
if (-not $python -or -not (Test-Path -LiteralPath $python -PathType Leaf)) {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
}
$probe = "import json,sys; sys.path.insert(0,r'$($server.Replace("'", "''"))'); from agent_scheduler import isolation_status; print(json.dumps(isolation_status(), indent=2))"
& $python -c $probe
exit $LASTEXITCODE
