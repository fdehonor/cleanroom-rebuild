[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$CertificateThumbprint, [string]$Path = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$certificate = Get-Item -LiteralPath "Cert:\CurrentUser\My\$CertificateThumbprint" -ErrorAction Stop
if (-not $certificate.HasPrivateKey) { throw 'The selected certificate has no private key.' }
$timestamp = 'http://timestamp.digicert.com'
$files = Get-ChildItem -LiteralPath $Path -Recurse -File | Where-Object Extension -in @('.ps1','.psm1','.psd1')
foreach ($file in $files) {
    $signature = Set-AuthenticodeSignature -LiteralPath $file.FullName -Certificate $certificate -TimestampServer $timestamp -HashAlgorithm SHA256
    if ($signature.Status -ne 'Valid') { throw "Signing failed for $($file.FullName): $($signature.StatusMessage)" }
}
Write-Host "Signed $($files.Count) PowerShell file(s). Build the release archive after signing."
