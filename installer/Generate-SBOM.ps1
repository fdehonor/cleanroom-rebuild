[CmdletBinding()]
param(
    [string]$OutputPath = (Join-Path $PSScriptRoot 'cleanroom-sbom.json'),
    [string]$Python = 'python',
    [string]$GpuPython = 'python',
    [string]$Npm = 'npm'
)
$ErrorActionPreference = 'Stop'
function Read-JsonCommand([scriptblock]$Command) {
    try { return (& $Command 2>$null | Out-String | ConvertFrom-Json) } catch { return $null }
}
$pythonPackages = Read-JsonCommand { & $Python -m pip list --format json }
$gpuPackages = Read-JsonCommand { & $GpuPython -m pip list --format json }
$nodePackages = Read-JsonCommand { & $Npm list --global --depth=0 --json }
$artifacts = @()
foreach ($path in Get-ChildItem -LiteralPath $PSScriptRoot -File -Recurse) {
    if ($path.Name -eq (Split-Path $OutputPath -Leaf)) { continue }
    $artifacts += @{
        path = $path.FullName.Substring($PSScriptRoot.Length).TrimStart('\')
        sha256 = (Get-FileHash -LiteralPath $path.FullName -Algorithm SHA256).Hash
        size = $path.Length
    }
}
$sbom = @{
    bomFormat = 'CycloneDX-compatible'
    specVersion = '1.5'
    serialNumber = "urn:uuid:$([guid]::NewGuid())"
    generatedAt = [DateTime]::UtcNow.ToString('o')
    components = @{
        python = @($pythonPackages)
        gpuPython = @($gpuPackages)
        node = $nodePackages.dependencies
    }
    artifacts = $artifacts
}
$sbom | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $OutputPath -Encoding utf8
Write-Host "SBOM written: $OutputPath"
