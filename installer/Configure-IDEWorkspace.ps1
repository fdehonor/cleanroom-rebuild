[CmdletBinding()]
param(
    [ValidateSet('Recommended','Full','ExistingOnly')]
    [string]$Profile = 'Recommended',
    [Parameter(Mandatory=$true)][string]$ToolsRoot,
    [Parameter(Mandatory=$true)][string]$SourceRoot,
    [Parameter(Mandatory=$true)][string]$Python
)

$ErrorActionPreference = 'Stop'
$workspaceRoot = Join-Path $ToolsRoot 'workspace'
$vscodeRoot = Join-Path $workspaceRoot '.vscode'
$runRoot = Join-Path $workspaceRoot '.run'
New-Item -ItemType Directory -Force -Path $workspaceRoot,$vscodeRoot,$runRoot | Out-Null

function Find-Executable([string[]]$Candidates) {
    foreach ($candidate in $Candidates) {
        if ([IO.Path]::IsPathRooted($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) { return $candidate }
        $command = Get-Command $candidate -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) { return $command.Source }
    }
    return $null
}

function Install-WingetPackage([string]$Id, [string[]]$Extra = @()) {
    $winget = Find-Executable @('winget.exe')
    if (-not $winget) { Write-Warning "winget is unavailable; skipped $Id"; return }
    & $winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements @Extra
    if ($LASTEXITCODE -ne 0) { Write-Warning "$Id could not be installed automatically." }
}

if ($Profile -ne 'ExistingOnly') {
    if (-not (Find-Executable @('code.cmd',"$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code.cmd","$env:ProgramFiles\Microsoft VS Code\bin\code.cmd"))) {
        Install-WingetPackage 'Microsoft.VisualStudioCode'
    }
    Install-WingetPackage 'Kitware.CMake'
    Install-WingetPackage 'Ninja-build.Ninja'
    Install-WingetPackage 'LLVM.LLVM'
}

if ($Profile -eq 'Full') {
    Install-WingetPackage 'Microsoft.VisualStudio.2022.Community' @('--override','--wait --quiet --norestart --add Microsoft.VisualStudio.Workload.NativeDesktop --add Microsoft.VisualStudio.Workload.ManagedDesktop --includeRecommended')
    Install-WingetPackage 'JetBrains.PyCharm.Community'
    Install-WingetPackage 'JetBrains.IntelliJIDEA.Community'
}

$editorCommands = @()
foreach ($candidateSet in @(
    @('code.cmd',"$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code.cmd","$env:ProgramFiles\Microsoft VS Code\bin\code.cmd"),
    @('cursor.cmd',"$env:LOCALAPPDATA\Programs\cursor\resources\app\bin\cursor.cmd"),
    @('windsurf.cmd',"$env:LOCALAPPDATA\Programs\Windsurf\bin\windsurf.cmd")
)) {
    $editor = Find-Executable $candidateSet
    if ($editor) { $editorCommands += $editor }
}
$editorCommands = $editorCommands | Select-Object -Unique

$extensions = @(
    'openai.chatgpt',
    'ms-python.python',
    'ms-vscode.cpptools',
    'ms-vscode.cmake-tools',
    'ms-vscode.powershell'
)
foreach ($editor in $editorCommands) {
    foreach ($extension in $extensions) {
        & $editor --install-extension $extension --force
        if ($LASTEXITCODE -ne 0) { Write-Warning "$extension could not be installed through $editor" }
    }
}

$sourceFolders = @()
foreach ($name in @('LLM4Decompile','reverse-engineering-assistant','rea')) {
    $path = Join-Path $SourceRoot $name
    if (Test-Path -LiteralPath $path) { $sourceFolders += @{ name=$name; path=$path } }
}
$sourceFolders += @{ name='Cleanroom Workspace'; path=$workspaceRoot }

$workspace = @{
    folders = $sourceFolders
    settings = @{
        'python.defaultInterpreterPath' = $Python
        'python.terminal.activateEnvironment' = $false
        'terminal.integrated.defaultProfile.windows' = 'PowerShell'
        'files.exclude' = @{ '**/__pycache__'=$true; '**/.pytest_cache'=$true }
        'search.exclude' = @{ '**/.git'=$true; '**/node_modules'=$true; '**/.cleanroom/analysis'=$true }
        'files.associations' = @{ '*.cleanroom.json'='json' }
    }
}
$workspace | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $workspaceRoot 'Cleanroom-Rebuild.code-workspace') -Encoding utf8

@{
    recommendations = $extensions
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $vscodeRoot 'extensions.json') -Encoding utf8

$tasks = @{
    version='2.0.0'
    tasks=@(
        @{ label='Cleanroom: Verify Python runtime'; type='process'; command=$Python; args=@('-c','import torch,transformers; print(torch.__version__, transformers.__version__)'); problemMatcher=@() },
        @{ label='Cleanroom: REA health check'; type='shell'; command='rea doctor --client codex --provider ghidra --format json'; problemMatcher=@() },
        @{ label='Cleanroom: Start Ghidra'; type='shell'; command='& "$env:GHIDRA_INSTALL_DIR\ghidraRun.bat"'; problemMatcher=@() },
        @{ label='Cleanroom: Show MCP registrations'; type='shell'; command='codex mcp list'; problemMatcher=@() }
        @{ label='Cleanroom: Check coding agents'; type='shell'; command='codex --version; claude --version; gemini --version'; problemMatcher=@() }
    )
}
$tasks | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $vscodeRoot 'tasks.json') -Encoding utf8

$settings = @{
    'python.defaultInterpreterPath'=$Python
    'terminal.integrated.defaultProfile.windows'='PowerShell'
    'cmake.configureOnOpen'=$false
}
$settings | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $vscodeRoot 'settings.json') -Encoding utf8

$vsconfig = @{
    version='1.0'
    components=@(
        'Microsoft.VisualStudio.Workload.NativeDesktop',
        'Microsoft.VisualStudio.Workload.ManagedDesktop',
        'Microsoft.VisualStudio.Component.VC.CMake.Project'
    )
}
$vsconfig | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $workspaceRoot 'Cleanroom-Rebuild.vsconfig') -Encoding utf8

$jetbrainsRun = @'
<component name="ProjectRunConfigurationManager">
  <configuration default="false" name="Codex CLI" type="ShConfigurationType">
    <option name="SCRIPT_TEXT" value="codex" />
    <option name="INDEPENDENT_SCRIPT_PATH" value="true" />
    <option name="SCRIPT_PATH" value="" />
    <option name="SCRIPT_OPTIONS" value="" />
    <option name="INDEPENDENT_SCRIPT_WORKING_DIRECTORY" value="true" />
    <option name="SCRIPT_WORKING_DIRECTORY" value="$PROJECT_DIR$" />
    <method v="2" />
  </configuration>
</component>
'@
$jetbrainsRun | Set-Content -LiteralPath (Join-Path $runRoot 'Codex CLI.run.xml') -Encoding utf8

$agents = @'
# Cleanroom Rebuild workspace

Use the globally registered REA and ReVa MCP servers for authorized analysis.
Keep decompiler output in the analysis room. Implementation must use only the
behavior-only handoff under `.cleanroom/handoff`.

Open the Clean-room Live Status app in Codex for direct, zero-LLM progress.
Do not call work complete until `cleanroom_release_gate` returns release-ready.
'@
$agents | Set-Content -LiteralPath (Join-Path $workspaceRoot 'AGENTS.md') -Encoding utf8
$agents.Replace('Codex','Claude Code') | Set-Content -LiteralPath (Join-Path $workspaceRoot 'CLAUDE.md') -Encoding utf8
$agents.Replace('Codex','Gemini CLI') | Set-Content -LiteralPath (Join-Path $workspaceRoot 'GEMINI.md') -Encoding utf8

$readme = @"
# Cleanroom Rebuild coding workspace

Open `Cleanroom-Rebuild.code-workspace` in VS Code, Cursor, or Windsurf.
Visual Studio users can import `Cleanroom-Rebuild.vsconfig` to install the C++,
.NET, and CMake workloads. JetBrains IDEs discover the shared Codex CLI run
configuration in `.run`.

The official Codex extension is installed in detected VS Code-compatible
editors. The clean-room scheduler uses Codex as its isolated writer and can
run Claude Code and Gemini CLI as parallel read-only reviewers. Each optional
provider requires its own account and one-time sign-in.
"@
$readme | Set-Content -LiteralPath (Join-Path $workspaceRoot 'README.md') -Encoding utf8

Write-Host "IDE workspace ready: $(Join-Path $workspaceRoot 'Cleanroom-Rebuild.code-workspace')"
