[CmdletBinding()]
param([switch]$Enable)

$ErrorActionPreference = 'Stop'
$edition = (Get-ComputerInfo).WindowsProductName
$supportedEdition = $edition -match 'Pro|Enterprise|Education'
$computer = Get-CimInstance Win32_ComputerSystem
$processor = Get-CimInstance Win32_Processor | Select-Object -First 1
$featureText = (& dism.exe /Online /Get-FeatureInfo /FeatureName:Containers-DisposableClientVM /English 2>&1 | Out-String)
$featureState = if ($featureText -match 'State\s*:\s*Enabled') { 'Enabled' } elseif ($featureText -match 'State\s*:\s*Disabled') { 'Disabled' } else { 'Unavailable' }
$result = [ordered]@{
    WindowsEdition = $edition
    SupportedEdition = $supportedEdition
    HypervisorPresent = [bool]$computer.HypervisorPresent
    FirmwareVirtualizationEnabled = [bool]$processor.VirtualizationFirmwareEnabled
    FeatureState = $featureState
    Ready = $false
    RestartRequired = $false
}

if (-not $supportedEdition) {
    $result.Remediation = 'Windows Sandbox requires Windows 11 Pro, Enterprise, or Education. Upgrade Windows or configure an independently audited external sandbox wrapper.'
    $result | ConvertTo-Json
    return
}
if (-not $processor.VirtualizationFirmwareEnabled -and -not $computer.HypervisorPresent) {
    $result.Remediation = 'Enable CPU virtualization (Intel VT-x/AMD-V) in UEFI/BIOS, then restart Windows.'
    $result | ConvertTo-Json
    return
}
if ($featureState -ne 'Enabled') {
    if (-not $Enable) {
        $result.Remediation = 'Run Enable Secure Sandbox.cmd as an administrator, then restart if requested.'
        $result | ConvertTo-Json
        return
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Administrator rights are required to enable the Windows Sandbox feature.'
    }
    $enabled = Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All -NoRestart
    $result.FeatureState = [string]$enabled.State
    $result.RestartRequired = [bool]$enabled.RestartNeeded
}
$result.Ready = $result.FeatureState -eq 'Enabled' -and ($result.HypervisorPresent -or $result.FirmwareVirtualizationEnabled)
$result.Remediation = if ($result.RestartRequired) { 'Restart Windows, then run Test-CleanroomIsolation.ps1.' } elseif ($result.Ready) { 'Windows Sandbox prerequisites are ready.' } else { 'Restart Windows and run this check again.' }
$result | ConvertTo-Json
