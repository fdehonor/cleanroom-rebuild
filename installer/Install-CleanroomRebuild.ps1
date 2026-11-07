[CmdletBinding()]
param(
    [switch]$DownloadModels,
    [switch]$AcceptThirdPartyLicenses,
    [ValidateSet('All','CodexOnly','ExistingOnly')]
    [string]$AgentProviders = 'All',
    [ValidateSet('Recommended','Full','ExistingOnly')]
    [string]$IDEProfile = 'Recommended'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$installerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$logPath = Join-Path $installerRoot 'install.log'
$toolsRoot = Join-Path $env:USERPROFILE 'Tools\Cleanroom-Rebuild'
$downloadRoot = Join-Path $toolsRoot 'downloads'
$sourceRoot = Join-Path $toolsRoot 'sources'
$marketplaceRoot = Join-Path $env:USERPROFILE '.codex\local-marketplaces\cleanroom-tools'

function Write-Step([string]$Message) {
    Write-Host "`n== $Message" -ForegroundColor Cyan
}

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program failed with exit code $LASTEXITCODE"
    }
}

function Ensure-NpmGlobalPackage([string]$Npm, [string]$Name, [string]$Version) {
    $installedVersion = $null
    try {
        $payload = (& $Npm list --global --depth=0 --json $Name 2>$null | Out-String) | ConvertFrom-Json
        $property = $payload.dependencies.PSObject.Properties[$Name]
        if ($property) { $installedVersion = $property.Value.version }
    } catch { $installedVersion = $null }
    if ($installedVersion -eq $Version) {
        Write-Host "Using installed npm package: $Name@$Version"
        return
    }
    Invoke-Checked $Npm @('install', '--global', "$Name@$Version")
}

function Find-Program([string[]]$Candidates) {
    foreach ($candidate in $Candidates) {
        if ([System.IO.Path]::IsPathRooted($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        $command = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command -and $command.Source -and $command.Source -notlike '*WindowsApps*') {
            return $command.Source
        }
    }
    return $null
}

function Get-VerifiedDownload([string]$Url, [string]$Destination, [string]$Sha256) {
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        $actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -eq $Sha256.ToLowerInvariant()) {
            Write-Host "Using verified cache: $Destination"
            return
        }
        Remove-Item -LiteralPath $Destination -Force
    }
    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
    $actual = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Sha256.ToLowerInvariant()) {
        Remove-Item -LiteralPath $Destination -Force
        throw "Checksum mismatch for $Url"
    }
}

function Ensure-Clone([string]$Git, [string]$Url, [string]$Commit, [string]$Destination) {
    if (Test-Path -LiteralPath (Join-Path $Destination '.git') -PathType Container) {
        $origin = (& $Git -C $Destination remote get-url origin).Trim()
        if ($LASTEXITCODE -ne 0 -or $origin.TrimEnd('/') -ne $Url.TrimEnd('/')) {
            throw "Repository origin mismatch at $Destination"
        }
    } else {
        if (Test-Path -LiteralPath $Destination) {
            throw "Refusing to overwrite non-repository path: $Destination"
        }
        Invoke-Checked $Git @('clone', '--filter=blob:none', '--no-checkout', $Url, $Destination)
    }
    Invoke-Checked $Git @('-C', $Destination, 'fetch', '--depth', '1', 'origin', $Commit)
    Invoke-Checked $Git @('-C', $Destination, 'checkout', '--detach', '--force', $Commit)
    $actual = (& $Git -C $Destination rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -ne $Commit) { throw "Pinned source checkout failed at $Destination" }
    Write-Host "Verified pinned source: $Destination @ $Commit"
}

function Set-UserEnvironment([string]$Name, [string]$Value) {
    [Environment]::SetEnvironmentVariable($Name, $Value, 'User')
    Set-Item -Path "Env:$Name" -Value $Value
}

function Add-UserPath([string]$Value) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @($userPath -split ';' | Where-Object { $_ })
    if ($entries -notcontains $Value) {
        [Environment]::SetEnvironmentVariable('Path', (($entries + $Value) -join ';'), 'User')
    }
    if (($env:Path -split ';') -notcontains $Value) {
        $env:Path = "$Value;$env:Path"
    }
}

Start-Transcript -LiteralPath $logPath -Force | Out-Null
try {
    if (-not $AcceptThirdPartyLicenses) {
        Write-Host 'This public installer downloads third-party software governed by its own licenses.' -ForegroundColor Yellow
        Write-Host 'Read THIRD-PARTY-NOTICES.md and the license files in third-party-licenses.'
        Write-Host 'LLM4Decompile model weights use the DeepSeek Model License, including use restrictions.'
        $answer = Read-Host "Type AGREE to accept the applicable third-party terms and continue"
        if ($answer -cne 'AGREE') { throw 'Third-party terms were not accepted; nothing was installed.' }
    }
    if (-not $IsWindows -and $PSVersionTable.PSEdition -eq 'Core') {
        throw 'This installer supports 64-bit Windows only.'
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'A 64-bit Windows installation is required.'
    }

    New-Item -ItemType Directory -Force -Path $toolsRoot, $downloadRoot, $sourceRoot | Out-Null

    Write-Step 'Checking Git, Node.js, Python, and Codex'
    $winget = Find-Program @('winget.exe')
    $git = Find-Program @('git.exe')
    $node = Find-Program @('node.exe')
    $npm = Find-Program @('npm.cmd')
    $python = Find-Program @('C:\Python315\python.exe', 'python.exe')
    $codex = Find-Program @('codex.exe', 'codex.cmd')
    if (-not $codex) {
        $storeCodex = Get-Command 'codex.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($storeCodex -and $storeCodex.Source) {
            & $storeCodex.Source --version *> $null
            if ($LASTEXITCODE -eq 0) { $codex = $storeCodex.Source }
        }
    }

    if (-not $git -and $winget) {
        Invoke-Checked $winget @('install', '--id', 'Git.Git', '--exact', '--accept-package-agreements', '--accept-source-agreements', '--silent')
        $git = Find-Program @("$env:ProgramFiles\Git\cmd\git.exe", 'git.exe')
    }
    if ((-not $node -or -not $npm) -and $winget) {
        Invoke-Checked $winget @('install', '--id', 'OpenJS.NodeJS.LTS', '--exact', '--accept-package-agreements', '--accept-source-agreements', '--silent')
        $node = Find-Program @("$env:ProgramFiles\nodejs\node.exe", 'node.exe')
        $npm = Find-Program @("$env:ProgramFiles\nodejs\npm.cmd", 'npm.cmd')
    }
    if (-not $python -and $winget) {
        Invoke-Checked $winget @('install', '--id', 'Python.Python.3.15', '--exact', '--accept-package-agreements', '--accept-source-agreements', '--silent', '--scope', 'user')
        $python = Find-Program @('C:\Python315\python.exe', 'python.exe')
    }
    if (-not $git -or -not $node -or -not $npm -or -not $python -or -not $codex) {
        throw 'Git, Node.js, Python 3.12+, and the Codex desktop/CLI must be installed. Reopen this installer after installing any item named above.'
    }
    $pythonVersion = & $python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
    $pythonOk = & $python -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)'; $pythonExit = $LASTEXITCODE
    if ($pythonExit -ne 0) { throw "Python 3.12 or newer is required; found $pythonVersion" }
    Write-Host "Python $pythonVersion at $python"
    $gpuPython = Find-Program @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "$env:LOCALAPPDATA\Python\pythoncore-3.12-64\python.exe")
    if (-not $gpuPython -and $winget) {
        Write-Host 'Installing an isolated Python 3.12 GPU worker; the latest Python remains global.'
        Invoke-Checked $winget @('install', '--id', 'Python.Python.3.12', '--exact', '--accept-package-agreements', '--accept-source-agreements', '--silent', '--scope', 'user')
        $gpuPython = Find-Program @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe", "$env:LOCALAPPDATA\Python\pythoncore-3.12-64\python.exe")
    }
    if (-not $gpuPython) { throw 'Python 3.12 GPU worker installation failed.' }

    Write-Step 'Downloading verified Ghidra, Java, Ant, and ReVa releases'
    $ghidraZip = Join-Path $downloadRoot 'ghidra_12.1.3_PUBLIC_20260817.zip'
    $jdkZip = Join-Path $downloadRoot 'OpenJDK21U-jdk_x64_windows_hotspot_21.0.13_9.zip'
    $antZip = Join-Path $downloadRoot 'apache-ant-1.10.18-bin.zip'
    $revaExtensionZip = Join-Path $downloadRoot 'ghidra_12.1.3_PUBLIC_20260903_reverse-engineering-assistant.zip'
    $revaWheel = Join-Path $downloadRoot 'reverse_engineering_assistant-7.3.1-py3-none-any.whl'
    Get-VerifiedDownload 'https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.3_build/ghidra_12.1.3_PUBLIC_20260817.zip' $ghidraZip '93a5d11a9ad510622acaaf908c556a7b9b764d338e78a7567f3689bf5081fd54'
    Get-VerifiedDownload 'https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.13%2B9/OpenJDK21U-jdk_x64_windows_hotspot_21.0.13_9.zip' $jdkZip 'a4dbaa05fca4bd89d84584e58c459bd732efebb1722af80ab13c6516832004f9'
    Get-VerifiedDownload 'https://archive.apache.org/dist/ant/binaries/apache-ant-1.10.18-bin.zip' $antZip 'd3d2009bc815e8fe4808e3af2f2aa7019cd666a26d112a3d9ea5a45345edf236'
    Get-VerifiedDownload 'https://github.com/cyberkaida/reverse-engineering-assistant/releases/download/v7.3.1/ghidra_12.1.3_PUBLIC_20260903_reverse-engineering-assistant.zip' $revaExtensionZip 'a87ce543a8835e5fe19282500bfc77f55b4bb32b3e18ff38c87ed44dd312cef5'
    Get-VerifiedDownload 'https://github.com/cyberkaida/reverse-engineering-assistant/releases/download/v7.3.1/reverse_engineering_assistant-7.3.1-py3-none-any.whl' $revaWheel '4ecc5b5a66a7d5762fe946d21efb6fb2e62ddeacc0bd385a636abe752cab6dde'

    Write-Step 'Installing Ghidra, Java, Ant, and the ReVa extension'
    $ghidraHome = Join-Path $toolsRoot 'ghidra_12.1.3_PUBLIC'
    $jdkHome = Join-Path $toolsRoot 'jdk-21.0.13+9'
    $antHome = Join-Path $toolsRoot 'apache-ant-1.10.18'
    if (-not (Test-Path -LiteralPath $ghidraHome)) { Expand-Archive -LiteralPath $ghidraZip -DestinationPath $toolsRoot -Force }
    if (-not (Test-Path -LiteralPath $jdkHome)) { Expand-Archive -LiteralPath $jdkZip -DestinationPath $toolsRoot -Force }
    if (-not (Test-Path -LiteralPath $antHome)) { Expand-Archive -LiteralPath $antZip -DestinationPath $toolsRoot -Force }
    $revaExtensionHome = Join-Path $ghidraHome 'Ghidra\Extensions\reverse-engineering-assistant'
    if (-not (Test-Path -LiteralPath $revaExtensionHome)) {
        Expand-Archive -LiteralPath $revaExtensionZip -DestinationPath (Join-Path $ghidraHome 'Ghidra\Extensions') -Force
    }
    Set-UserEnvironment 'JAVA_HOME' $jdkHome
    Set-UserEnvironment 'GHIDRA_INSTALL_DIR' $ghidraHome
    Set-UserEnvironment 'ANT_HOME' $antHome
    Add-UserPath (Join-Path $jdkHome 'bin')
    Add-UserPath (Join-Path $antHome 'bin')

    Write-Step 'Installing the ReVa bridge and LLM4Decompile runtime globally for this user'
    Invoke-Checked $python @('-m', 'pip', 'install', '--upgrade', '--user', 'pip', 'setuptools', 'wheel')
    Invoke-Checked $python @('-m', 'pip', 'install', '--upgrade', '--user', $revaWheel)
    Invoke-Checked $python @('-m', 'pip', 'install', '--upgrade', '--user', 'mcp==1.30.0')
    $gpuLock = Join-Path $installerRoot 'python-gpu-requirements.lock'
    if (-not (Test-Path -LiteralPath $gpuLock -PathType Leaf)) { throw 'Pinned GPU requirements lock is missing.' }
    Invoke-Checked $gpuPython @('-m', 'pip', 'install', '--upgrade', '--requirement', $gpuLock)
    $pythonScripts = & $python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))"
    Add-UserPath $pythonScripts
    $revaExe = Join-Path $pythonScripts 'mcp-reva.exe'
    if (-not (Test-Path -LiteralPath $revaExe)) { throw "ReVa launcher was not created at $revaExe" }

    Write-Step 'Installing REA and its Codex skill'
    Ensure-NpmGlobalPackage $npm 'rea-agents' '6.8.0'
    $npmPrefix = (& $npm prefix --global).Trim()
    $reaCmd = Join-Path $npmPrefix 'rea.cmd'
    $reaModule = Join-Path $npmPrefix 'node_modules\rea-agents\scripts\rea.mjs'
    Invoke-Checked $reaCmd @('setup', '--client', 'codex', '--skill', '--yes', '--format', 'json')

    Write-Step 'Installing automatic Codex, Claude, and Gemini coding-agent support'
    if ($AgentProviders -eq 'All') {
        Ensure-NpmGlobalPackage $npm '@anthropic-ai/claude-code' '2.1.318'
        Ensure-NpmGlobalPackage $npm '@google/gemini-cli' '0.67.0'
    }
    $claude = Find-Program @('claude.cmd', 'claude.exe', 'claude')
    $gemini = Find-Program @('gemini.cmd', 'gemini.exe', 'gemini')
    if ($AgentProviders -eq 'All' -and (-not $claude -or -not $gemini)) {
        throw 'Claude Code or Gemini CLI did not install correctly. Check the npm global binary directory in PATH.'
    }

    Write-Step 'Cloning the three source repositories'
    Ensure-Clone $git 'https://github.com/albertan017/LLM4Decompile.git' '85b364bf093eb2ee4f3687cfe38a203fca89f23e' (Join-Path $sourceRoot 'LLM4Decompile')
    Ensure-Clone $git 'https://github.com/cyberkaida/reverse-engineering-assistant.git' '4d2fc5b4c5f4ce00d95f0bd6bdf0c64b67e65fc2' (Join-Path $sourceRoot 'reverse-engineering-assistant')
    Ensure-Clone $git 'https://github.com/morluto/rea.git' 'f3c21665d8b098933e1e57dbd605ad2aa3f0c1c4' (Join-Path $sourceRoot 'rea')

    Write-Step 'Creating the coding workspace and configuring IDEs'
    $ideSetup = Join-Path $installerRoot 'Configure-IDEWorkspace.ps1'
    if (-not (Test-Path -LiteralPath $ideSetup)) { throw 'IDE workspace configurator is missing.' }
    & $ideSetup -Profile $IDEProfile -ToolsRoot $toolsRoot -SourceRoot $sourceRoot -Python $python
    if ($LASTEXITCODE -ne 0) { throw "IDE workspace setup failed with exit code $LASTEXITCODE" }

    Write-Step 'Installing the Cleanroom Rebuild Codex plugin'
    $payloadMarketplace = Join-Path $installerRoot 'payload\cleanroom-tools'
    if (-not (Test-Path -LiteralPath $payloadMarketplace)) { throw 'Bundled plugin payload is missing.' }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $marketplaceRoot) | Out-Null
    if (Test-Path -LiteralPath $marketplaceRoot) {
        Copy-Item -LiteralPath (Join-Path $payloadMarketplace '.agents') -Destination $marketplaceRoot -Recurse -Force
        Copy-Item -LiteralPath (Join-Path $payloadMarketplace 'plugins') -Destination $marketplaceRoot -Recurse -Force
    } else {
        Copy-Item -LiteralPath $payloadMarketplace -Destination $marketplaceRoot -Recurse -Force
    }
    $pluginMcp = Join-Path $marketplaceRoot 'plugins\cleanroom-rebuild\mcp.json'
    $mcpText = Get-Content -LiteralPath $pluginMcp -Raw
    $mcpText = $mcpText.Replace('__PYTHON__', ($gpuPython.Replace('\', '\\')))
    Set-Content -LiteralPath $pluginMcp -Value $mcpText -Encoding utf8
    & $codex plugin marketplace add $marketplaceRoot --json 2>$null | Out-Null
    & $codex plugin add 'cleanroom-rebuild@cleanroom-tools' --json 2>$null | Out-Null

    Write-Step 'Registering the ReVa and REA MCP servers with Codex'
    & $codex mcp remove ReVa 2>$null | Out-Null
    & $codex mcp remove rea 2>$null | Out-Null
    Invoke-Checked $codex @('mcp', 'add', 'ReVa', '--env', "GHIDRA_INSTALL_DIR=$ghidraHome", '--env', "JAVA_HOME=$jdkHome", '--', $revaExe)
    Invoke-Checked $codex @('mcp', 'add', 'rea', '--env', "GHIDRA_INSTALL_DIR=$ghidraHome", '--env', "JAVA_HOME=$jdkHome", '--', $node, $reaModule, 'mcp')
    Invoke-Checked $reaCmd @('setup', '--all-detected', '--skill', '--yes', '--format', 'json')

    if ($DownloadModels) {
        Write-Step 'Downloading the optional local 1.3B model weights'
        Invoke-Checked $gpuPython @('-c', "from huggingface_hub import snapshot_download; snapshot_download('LLM4Binary/llm4decompile-1.3b-v2'); snapshot_download('LLM4Binary/llm4decompile-1.3b-v1.5')")
    }

    Write-Step 'Verifying the complete installation'
    Invoke-Checked $python @('-c', "import jpype,importlib.metadata as m; print(jpype.__version__, m.version('reverse-engineering-assistant'))")
    Invoke-Checked $gpuPython @('-c', 'import torch,transformers,torch_directml; d=torch_directml.device(); x=torch.tensor([1.0]).to(d); assert (x+x).cpu().item()==2.0; print(torch.__version__, transformers.__version__, torch_directml.device_name(0))')
    Invoke-Checked $reaCmd @('doctor', '--client', 'codex', '--provider', 'ghidra', '--format', 'json')
    Invoke-Checked $codex @('--version')
    if ($claude) { Invoke-Checked $claude @('--version') }
    if ($gemini) { Invoke-Checked $gemini @('--version') }
    Invoke-Checked (Join-Path $jdkHome 'bin\java.exe') @('-version')
    if (-not (Test-Path -LiteralPath (Join-Path $ghidraHome 'support\analyzeHeadless.bat'))) { throw 'Ghidra headless launcher is missing.' }
    if (-not (Test-Path -LiteralPath $revaExtensionHome)) { throw 'ReVa Ghidra extension is missing.' }

    Write-Step 'Installing maintenance, diagnostics, and SBOM tools'
    $maintenanceRoot = Join-Path $toolsRoot 'maintenance'
    New-Item -ItemType Directory -Force -Path $maintenanceRoot | Out-Null
    foreach ($name in @('Install-CleanroomRebuild.ps1','Repair-CleanroomRebuild.ps1','Update-CleanroomRebuild.ps1','Uninstall-CleanroomRebuild.ps1','Export-Diagnostics.ps1','Generate-SBOM.ps1','Sign-Release.ps1','python-gpu-requirements.lock','CLEANROOM_WORKFLOW.md')) {
        $source = Join-Path $installerRoot $name
        if (Test-Path -LiteralPath $source -PathType Leaf) { Copy-Item -LiteralPath $source -Destination $maintenanceRoot -Force }
    }
    & (Join-Path $maintenanceRoot 'Generate-SBOM.ps1') -OutputPath (Join-Path $toolsRoot 'cleanroom-sbom.json') -Python $python -GpuPython $gpuPython -Npm $npm
    if ($LASTEXITCODE -ne 0) { throw 'SBOM generation failed.' }

    Write-Host "`nREADY. Close and reopen Codex, then ask: 'Start a clean-room rebuild project and analyze my authorized binary with Ghidra.'" -ForegroundColor Green
    Write-Host "IDE workspace: $(Join-Path $toolsRoot 'workspace\Cleanroom-Rebuild.code-workspace')"
    if ($claude) { Write-Host "One-time Claude sign-in: claude" -ForegroundColor Yellow }
    if ($gemini) { Write-Host "One-time Gemini sign-in: gemini" -ForegroundColor Yellow }
    Write-Host "Install log: $logPath"
    Write-Host "Maintenance tools: $maintenanceRoot"
    Write-Host "SBOM: $(Join-Path $toolsRoot 'cleanroom-sbom.json')"
}
catch {
    Write-Error $_
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
