[CmdletBinding()]
param([switch]$IncludePrerelease, [switch]$RequirePublisherSignature)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repository = 'fdehonor/cleanroom-rebuild'
$endpoint = if ($IncludePrerelease) { "https://api.github.com/repos/$repository/releases?per_page=20" } else { "https://api.github.com/repos/$repository/releases/latest" }
$response = Invoke-RestMethod -Uri $endpoint -Headers @{ Accept='application/vnd.github+json'; 'User-Agent'='Cleanroom-Rebuild-Updater' }
$release = if ($response -is [array]) { $response | Where-Object { -not $_.draft -and ($IncludePrerelease -or -not $_.prerelease) } | Select-Object -First 1 } else { $response }
if (-not $release -or $release.html_url -notlike "https://github.com/$repository/releases/*") { throw 'Release origin validation failed.' }
$zipAsset = $release.assets | Where-Object name -match '^Cleanroom-Rebuild-Installer-[0-9.]+\.zip$' | Select-Object -First 1
$hashAsset = $release.assets | Where-Object name -eq "$($zipAsset.name).sha256" | Select-Object -First 1
if (-not $zipAsset -or -not $hashAsset) { throw 'The release is missing its installer or checksum asset.' }
foreach ($asset in @($zipAsset,$hashAsset)) {
    if ($asset.browser_download_url -notlike "https://github.com/$repository/releases/download/*") { throw "Unexpected asset origin: $($asset.browser_download_url)" }
}
$temporary = Join-Path $env:TEMP "cleanroom-update-$([guid]::NewGuid())"
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $zipPath = Join-Path $temporary $zipAsset.name
    $hashPath = Join-Path $temporary $hashAsset.name
    Invoke-WebRequest -Uri $zipAsset.browser_download_url -OutFile $zipPath -UseBasicParsing
    Invoke-WebRequest -Uri $hashAsset.browser_download_url -OutFile $hashPath -UseBasicParsing
    $expected = ((Get-Content -LiteralPath $hashPath -Raw).Trim() -split '\s+')[0].ToUpperInvariant()
    if ($expected -notmatch '^[0-9A-F]{64}$') { throw 'Published checksum format is invalid.' }
    $actual = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($actual -ne $expected) { throw 'Installer checksum verification failed.' }
    $expanded = Join-Path $temporary 'expanded'
    New-Item -ItemType Directory -Path $expanded | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
    try {
        $expandedPrefix = [System.IO.Path]::GetFullPath($expanded).TrimEnd('\') + '\'
        foreach ($entry in $archive.Entries) {
            $relative = $entry.FullName.Replace('/', '\')
            if ([System.IO.Path]::IsPathRooted($relative) -or ($relative -split '[\\/]' | Where-Object { $_ -eq '..' })) {
                throw "Unsafe archive entry: $($entry.FullName)"
            }
            $target = [System.IO.Path]::GetFullPath((Join-Path $expanded $relative))
            if (-not $target.StartsWith($expandedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Archive entry escapes extraction root: $($entry.FullName)"
            }
            $unixType = (($entry.ExternalAttributes -shr 16) -band 0xF000)
            if ($unixType -eq 0xA000 -or (($entry.ExternalAttributes -band [int][IO.FileAttributes]::ReparsePoint) -ne 0)) {
                throw "Archive links are not allowed: $($entry.FullName)"
            }
        }
    } finally { $archive.Dispose() }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $expanded
    $installer = Get-ChildItem -LiteralPath $expanded -Filter 'Install-CleanroomRebuild.ps1' -Recurse -File | Select-Object -First 1
    if (-not $installer) { throw 'Verified archive does not contain the installer.' }
    $currentSignature = Get-AuthenticodeSignature -LiteralPath $PSCommandPath
    $installerSignature = Get-AuthenticodeSignature -LiteralPath $installer.FullName
    if ($currentSignature.Status -eq 'Valid') {
        if ($installerSignature.Status -ne 'Valid' -or $installerSignature.SignerCertificate.Thumbprint -ne $currentSignature.SignerCertificate.Thumbprint) {
            throw 'Updated installer is not signed by the same trusted publisher as this updater.'
        }
    } elseif ($RequirePublisherSignature -and $installerSignature.Status -ne 'Valid') {
        throw 'A valid publisher signature is required but the downloaded installer is not validly signed.'
    }
    & $installer.FullName -AcceptThirdPartyLicenses
    if ($LASTEXITCODE -ne 0) { throw "Updated installer failed with exit code $LASTEXITCODE" }
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
