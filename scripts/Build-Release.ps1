[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path (Split-Path -Parent $PSScriptRoot) 'release')
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$resolvedRepository = (Resolve-Path -LiteralPath $repositoryRoot).Path
$outputParent = Split-Path -Parent $OutputDirectory
New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
$releaseRoot = Join-Path $OutputDirectory 'Cleanroom-Rebuild-Installer'

if (Test-Path -LiteralPath $releaseRoot) {
    $resolvedRelease = (Resolve-Path -LiteralPath $releaseRoot).Path
    if (-not $resolvedRelease.StartsWith((Resolve-Path -LiteralPath $OutputDirectory).Path, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to replace a release directory outside the selected output directory.'
    }
    Remove-Item -LiteralPath $resolvedRelease -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
Copy-Item -Path (Join-Path $resolvedRepository 'installer\*') -Destination $releaseRoot -Recurse -Force
Copy-Item -LiteralPath (Join-Path $resolvedRepository 'LICENSE') -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $resolvedRepository 'THIRD-PARTY-NOTICES.md') -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $resolvedRepository 'PUBLIC-USE.md') -Destination $releaseRoot -Force
Copy-Item -LiteralPath (Join-Path $resolvedRepository 'third-party-licenses') -Destination $releaseRoot -Recurse -Force

$marketplaceRoot = Join-Path $releaseRoot 'payload\cleanroom-tools'
$catalogRoot = Join-Path $marketplaceRoot '.agents\plugins'
$pluginsRoot = Join-Path $marketplaceRoot 'plugins'
New-Item -ItemType Directory -Force -Path $catalogRoot,$pluginsRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $resolvedRepository 'plugin') -Destination (Join-Path $pluginsRoot 'cleanroom-rebuild') -Recurse -Force

$mcpPath = Join-Path $pluginsRoot 'cleanroom-rebuild\mcp.json'
$mcp = Get-Content -LiteralPath $mcpPath -Raw | ConvertFrom-Json
$mcp.mcpServers.'cleanroom-engine'.command = '__PYTHON__'
$mcp.mcpServers.'cleanroom-engine'.args = @('${PLUGIN_ROOT}/server/cleanroom_mcp.py')
$mcp | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $mcpPath -Encoding utf8

$marketplace = @{
    name='cleanroom-tools'
    interface=@{ displayName='Clean-room Tools' }
    plugins=@(
        @{
            name='cleanroom-rebuild'
            source=@{ source='local'; path='./plugins/cleanroom-rebuild' }
            policy=@{ installation='AVAILABLE'; authentication='ON_INSTALL' }
            category='Developer Tools'
        }
    )
}
$marketplace | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $catalogRoot 'marketplace.json') -Encoding utf8

$archive = Join-Path $OutputDirectory 'Cleanroom-Rebuild-Installer.zip'
Compress-Archive -LiteralPath $releaseRoot -DestinationPath $archive -CompressionLevel Optimal -Force
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
"$hash  Cleanroom-Rebuild-Installer.zip" | Set-Content -LiteralPath "$archive.sha256" -Encoding ascii
Write-Host "Built $archive"
Write-Host "SHA-256 $hash"
