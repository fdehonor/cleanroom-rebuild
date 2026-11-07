[CmdletBinding(SupportsShouldProcess=$true, ConfirmImpact='High')]
param([switch]$KeepTools, [switch]$KeepProjects, [switch]$Yes)
$ErrorActionPreference = 'Stop'
$toolsRoot = Join-Path $env:USERPROFILE 'Tools\Cleanroom-Rebuild'
$marketplaceRoot = Join-Path $env:USERPROFILE '.codex\local-marketplaces\cleanroom-tools'
$isolatedRoot = Join-Path $env:LOCALAPPDATA 'CleanroomRebuild'
if (-not $Yes) {
    $answer = Read-Host 'Type UNINSTALL to remove Cleanroom Rebuild registrations and selected local files'
    if ($answer -cne 'UNINSTALL') { throw 'Uninstall cancelled.' }
}
& codex plugin remove 'cleanroom-rebuild@cleanroom-tools' --json 2>$null | Out-Null
& codex mcp remove ReVa 2>$null | Out-Null
& codex mcp remove rea 2>$null | Out-Null
foreach ($target in @($marketplaceRoot,$isolatedRoot)) {
    if (Test-Path -LiteralPath $target -PathType Container) {
        $resolved = (Resolve-Path -LiteralPath $target).Path
        if ($resolved -notlike "$env:USERPROFILE*" -and $resolved -notlike "$env:LOCALAPPDATA*") { throw "Refusing unsafe removal target: $resolved" }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
if (-not $KeepTools -and (Test-Path -LiteralPath $toolsRoot -PathType Container)) {
    $resolvedTools = (Resolve-Path -LiteralPath $toolsRoot).Path
    if ($resolvedTools -ne $toolsRoot) { throw "Unexpected tools path: $resolvedTools" }
    if ($KeepProjects) {
        Get-ChildItem -LiteralPath $resolvedTools -Force | Where-Object Name -ne 'workspace' | Remove-Item -Recurse -Force
    } else {
        Remove-Item -LiteralPath $resolvedTools -Recurse -Force
    }
}
Write-Host 'Cleanroom Rebuild uninstalled. Third-party global CLIs were retained to avoid removing tools used by other applications.'
