[CmdletBinding()]
param([string]$Destination = (Join-Path $env:TEMP "Cleanroom-Diagnostics-$((Get-Date).ToString('yyyyMMdd-HHmmss')).zip"))
$ErrorActionPreference = 'Stop'
$temporary = Join-Path $env:TEMP "cleanroom-diagnostics-$([guid]::NewGuid())"
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $report = [ordered]@{
        generatedAt = [DateTime]::UtcNow.ToString('o')
        windows = [Environment]::OSVersion.VersionString
        architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        codex = (& codex --version 2>&1 | Out-String).Trim()
        claude = (& claude --version 2>&1 | Out-String).Trim()
        gemini = (& gemini --version 2>&1 | Out-String).Trim()
        python = (& python --version 2>&1 | Out-String).Trim()
        gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion,AdapterRAM)
        environmentPresence = @{
            JAVA_HOME = [bool]$env:JAVA_HOME
            GHIDRA_INSTALL_DIR = [bool]$env:GHIDRA_INSTALL_DIR
            GEMINI_API_KEY = [bool]$env:GEMINI_API_KEY
            GOOGLE_API_KEY = [bool]$env:GOOGLE_API_KEY
        }
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $temporary 'system.json') -Encoding utf8
    $log = Join-Path $env:USERPROFILE 'Tools\Cleanroom-Rebuild\install.log'
    if (Test-Path -LiteralPath $log) {
        $logInfo = Get-Item -LiteralPath $log
        @{ exists=$true; length=$logInfo.Length; lastWriteTimeUtc=$logInfo.LastWriteTimeUtc.ToString('o'); note='Raw transcript intentionally excluded because it may contain credentials or proprietary paths.' } |
            ConvertTo-Json | Set-Content -LiteralPath (Join-Path $temporary 'install-log-metadata.json') -Encoding utf8
    }
    Compress-Archive -LiteralPath (Join-Path $temporary '*') -DestinationPath $Destination -Force
    Write-Host "Diagnostics exported without credential values: $Destination"
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
