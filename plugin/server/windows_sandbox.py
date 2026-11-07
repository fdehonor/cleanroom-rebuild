from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


SCHEMA_VERSION = 1
SANDBOX_ROOT = Path(r"C:\Cleanroom")
WORKSPACE_IN_SANDBOX = SANDBOX_ROOT / "workspace"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def probe_windows_sandbox() -> dict[str, Any]:
    """Return fail-closed host capability evidence without changing Windows features."""
    result: dict[str, Any] = {
        "supported": False,
        "platform": platform.platform(),
        "reason": "Windows Sandbox is available only on supported Windows editions",
    }
    if os.name != "nt":
        return result
    try:
        edition = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "(Get-ComputerInfo).WindowsProductName"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, shell=False,
        ).stdout.strip()
    except Exception as exc:
        return {**result, "reason": f"could not determine Windows edition: {type(exc).__name__}: {exc}"}
    result["windows_edition"] = edition
    if not any(name in edition.casefold() for name in ("pro", "enterprise", "education")):
        result["reason"] = f"Windows Sandbox is not supported by this edition: {edition or 'unknown'}"
        return result
    try:
        feature = subprocess.run(
            ["dism.exe", "/Online", "/Get-FeatureInfo", "/FeatureName:Containers-DisposableClientVM", "/English"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, shell=False,
        )
        feature_text = feature.stdout + feature.stderr
    except Exception as exc:
        result["reason"] = f"could not query the Windows Sandbox feature: {type(exc).__name__}: {exc}"
        return result
    result["feature_enabled"] = feature.returncode == 0 and "State : Enabled" in feature_text
    if not result["feature_enabled"]:
        result["reason"] = "the Containers-DisposableClientVM Windows feature is not enabled"
        return result
    try:
        virtualization = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "[bool](Get-CimInstance Win32_ComputerSystem).HypervisorPresent"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, shell=False,
        ).stdout.strip().casefold() == "true"
    except Exception:
        virtualization = False
    result["hypervisor_present"] = virtualization
    if not virtualization:
        result["reason"] = "the Windows hypervisor is not active; enable firmware virtualization and restart"
        return result
    executable = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsSandbox.exe"
    if not executable.is_file():
        discovered = shutil.which("WindowsSandbox.exe")
        if not discovered:
            result["reason"] = "WindowsSandbox.exe was not found"
            return result
        executable = Path(discovered)
    result.update({"supported": True, "executable": str(executable.resolve()), "reason": "Windows Sandbox host prerequisites are present"})
    return result


def _safe_copy(source: Path, destination: Path) -> None:
    if source.is_file() and not source.is_symlink():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _stage_credentials(destination: Path, provider: str | None) -> list[str]:
    """Copy only provider bootstrap credentials/config, never histories or workspaces."""
    copied: list[str] = []
    home = Path.home()
    allowed_by_provider = {
        "codex": ((home / ".codex" / "auth.json", Path(".codex/auth.json")),),
        "claude": ((home / ".claude" / ".credentials.json", Path(".claude/.credentials.json")),),
        "gemini": (
            (home / ".gemini" / "oauth_creds.json", Path(".gemini/oauth_creds.json")),
            (home / ".gemini" / "google_accounts.json", Path(".gemini/google_accounts.json")),
        ),
    }
    allowed = allowed_by_provider.get(provider or "", ())
    for source, relative in allowed:
        if source.is_file() and not source.is_symlink():
            _safe_copy(source, destination / relative)
            copied.append(relative.as_posix())
    return copied


def _runtime_roots(command: list[str], provider: str | None = None) -> list[Path]:
    executable = Path(command[0])
    if not executable.is_absolute():
        resolved = shutil.which(command[0])
        if not resolved:
            raise FileNotFoundError(f"command executable was not found: {command[0]}")
        executable = Path(resolved)
    executable = executable.resolve()
    roots = [executable.parent]
    # npm launchers refer to sibling node_modules; map the complete global prefix.
    if executable.suffix.casefold() in {".cmd", ".ps1"} and (executable.parent / "node_modules").is_dir():
        roots = [executable.parent]
    if provider:
        node = shutil.which("node.exe") or shutil.which("node")
        if node:
            roots.append(Path(node).resolve().parent)
        git = shutil.which("git.exe") or shutil.which("git")
        if git:
            roots.append(Path(git).resolve().parent.parent)
        roots.append(Path(sys.executable).resolve().parent)
    unique: list[Path] = []
    for root in roots:
        if root.is_dir() and root not in unique:
            unique.append(root)
    return unique


def _translate(value: str, workspace: Path, mappings: list[tuple[Path, Path]]) -> str:
    candidate = Path(value)
    if not candidate.is_absolute():
        return value
    resolved = candidate.resolve()
    all_mappings = [(workspace, WORKSPACE_IN_SANDBOX), *mappings]
    for host, sandbox in all_mappings:
        try:
            relative = resolved.relative_to(host)
            return str(sandbox / relative)
        except ValueError:
            continue
    # Absolute host paths that are not explicitly mapped must never leak through.
    raise ValueError(f"absolute command argument is outside the sandbox allowlist: {value}")


def _runner_script() -> str:
    return r'''$ErrorActionPreference = 'Stop'
$control = 'C:\Cleanroom\control'
$outbox = 'C:\Cleanroom\outbox'
$spec = Get-Content -LiteralPath "$control\command.json" -Raw | ConvertFrom-Json
$env:PATH = (($spec.runtimePath + @($env:SystemRoot + '\System32', $env:SystemRoot)) -join ';')
$worker = 'CleanroomWorker'
$passwordText = ([Guid]::NewGuid().ToString('N') + 'aA1!')
$securePassword = ConvertTo-SecureString $passwordText -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential(".\$worker", $securePassword)
& net.exe user $worker $passwordText /add /expires:never /passwordchg:no | Out-Null
$workerSid = (New-Object Security.Principal.NTAccount($env:COMPUTERNAME, $worker)).Translate([Security.Principal.SecurityIdentifier]).Value
& icacls.exe $control /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" /deny "*${workerSid}:(OI)(CI)F" | Out-Null
& icacls.exe $outbox /inheritance:r /grant:r "${env:USERNAME}:(OI)(CI)F" /deny "*${workerSid}:(OI)(CI)F" | Out-Null
$workspaceGrant = if ($spec.readOnlyWorkspace) { '(OI)(CI)RX' } else { '(OI)(CI)M' }
& icacls.exe 'C:\Cleanroom\workspace' /grant "*${workerSid}:$workspaceGrant" | Out-Null
foreach ($runtime in $spec.runtimePath) { & icacls.exe $runtime /grant "*${workerSid}:(OI)(CI)RX" | Out-Null }
$workerProfile = "C:\Users\$worker"
New-Item -ItemType Directory -Force -Path $workerProfile | Out-Null
if (Test-Path -LiteralPath "$control\auth") {
  Get-ChildItem -LiteralPath "$control\auth" -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $workerProfile -Recurse -Force }
}
& icacls.exe $workerProfile /inheritance:r /grant:r "*${workerSid}:(OI)(CI)F" "${env:USERNAME}:(OI)(CI)F" | Out-Null
$localStdout = 'C:\Windows\Temp\cleanroom.stdout.log'
$localStderr = 'C:\Windows\Temp\cleanroom.stderr.log'
$started = [DateTime]::UtcNow.ToString('o')
try {
  $process = Start-Process -FilePath $spec.fileName -ArgumentList $spec.arguments -WorkingDirectory $spec.workingDirectory -Credential $credential -LoadUserProfile -WindowStyle Hidden -RedirectStandardOutput $localStdout -RedirectStandardError $localStderr -Wait -PassThru
  Copy-Item -LiteralPath $localStdout -Destination "$outbox\stdout.log" -Force
  Copy-Item -LiteralPath $localStderr -Destination "$outbox\stderr.log" -Force
  @{ exitCode = $process.ExitCode; startedAt = $started; finishedAt = [DateTime]::UtcNow.ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath "$outbox\result.json" -Encoding UTF8
} catch {
  $_.Exception.ToString() | Set-Content -LiteralPath "$outbox\stderr.log" -Encoding UTF8
  @{ exitCode = 126; startedAt = $started; finishedAt = [DateTime]::UtcNow.ToString('o'); error = $_.Exception.Message } | ConvertTo-Json | Set-Content -LiteralPath "$outbox\result.json" -Encoding UTF8
} finally {
  & net.exe user $worker /delete | Out-Null
  Start-Process -FilePath shutdown.exe -ArgumentList '/s','/t','0' -WindowStyle Hidden
}
'''


def _mapped_folder(host: Path, sandbox: Path, read_only: bool) -> str:
    return (
        "<MappedFolder>"
        f"<HostFolder>{escape(str(host))}</HostFolder>"
        f"<SandboxFolder>{escape(str(sandbox))}</SandboxFolder>"
        f"<ReadOnly>{str(read_only).lower()}</ReadOnly>"
        "</MappedFolder>"
    )


def build_configuration(workspace: Path, control: Path, outbox: Path, runtime_roots: list[Path], workspace_read_only: bool = False, networking_enabled: bool = True) -> tuple[str, list[tuple[Path, Path]]]:
    mappings = [(root, SANDBOX_ROOT / "runtime" / str(index)) for index, root in enumerate(runtime_roots)]
    folders = [
        _mapped_folder(workspace, WORKSPACE_IN_SANDBOX, workspace_read_only),
        _mapped_folder(control, SANDBOX_ROOT / "control", True),
        _mapped_folder(outbox, SANDBOX_ROOT / "outbox", False),
        *(_mapped_folder(host, sandbox, True) for host, sandbox in mappings),
    ]
    configuration = (
        "<Configuration>"
        f"<VGpu>Disable</VGpu><Networking>{'Enable' if networking_enabled else 'Disable'}</Networking>"
        "<AudioInput>Disable</AudioInput><VideoInput>Disable</VideoInput>"
        "<ClipboardRedirection>Disable</ClipboardRedirection><PrinterRedirection>Disable</PrinterRedirection>"
        "<ProtectedClient>Enable</ProtectedClient><MemoryInMB>8192</MemoryInMB>"
        f"<MappedFolders>{''.join(folders)}</MappedFolders>"
        "<LogonCommand><Command>powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\\Cleanroom\\control\\runner.ps1</Command></LogonCommand>"
        "</Configuration>"
    )
    return configuration, mappings


def run_in_windows_sandbox(command: list[str], workspace: Path, timeout: int, attestation_path: Path | None = None, working_directory: Path | None = None, credential_provider: str | None = None, workspace_read_only: bool = False, networking_enabled: bool = True) -> int:
    capability = probe_windows_sandbox()
    if not capability["supported"]:
        raise RuntimeError(capability["reason"])
    workspace = workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("workspace must be a directory")
    jobs_root = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "CleanroomRebuild" / "sandbox-jobs"
    jobs_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="job-", dir=jobs_root) as temporary_job:
        job_root = Path(temporary_job)
        control, outbox = job_root / "control", job_root / "outbox"
        control.mkdir()
        outbox.mkdir()
        runtime_roots = _runtime_roots(command, credential_provider)
        configuration, mappings = build_configuration(workspace, control, outbox, runtime_roots, workspace_read_only, networking_enabled)
        translated = [_translate(value, workspace, mappings) for value in command]
        translated_cwd = _translate(str((working_directory or workspace).resolve()), workspace, mappings)
        executable = translated[0]
        arguments = subprocess.list2cmdline(translated[1:])
        if Path(executable).suffix.casefold() in {".cmd", ".bat"}:
            arguments = "/d /s /c " + subprocess.list2cmdline([subprocess.list2cmdline(translated)])
            executable = r"C:\Windows\System32\cmd.exe"
        copied_credentials = _stage_credentials(control / "auth", credential_provider)
        command_spec = {
            "fileName": executable,
            "arguments": arguments,
            "workingDirectory": translated_cwd,
            "runtimePath": [str(sandbox) for _, sandbox in mappings],
            "readOnlyWorkspace": workspace_read_only,
        }
        (control / "runner.ps1").write_text(_runner_script(), encoding="utf-8-sig")
        (control / "command.json").write_text(json.dumps(command_spec, indent=2), encoding="utf-8")
        config_path = job_root / "job.wsb"
        config_path.write_text(configuration, encoding="utf-8-sig")
        started = _now()
        launch = subprocess.Popen([capability["executable"], str(config_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
        timed_out = False
        try:
            launch.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(["taskkill.exe", "/PID", str(launch.pid), "/T", "/F"], capture_output=True, timeout=15)
        result_path = outbox / "result.json"
        if timed_out:
            result = {"exitCode": 124, "error": "sandbox command timed out"}
        elif not result_path.is_file():
            result = {"exitCode": 126, "error": "trusted guest runner did not produce a completion record"}
        else:
            result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        stdout = (outbox / "stdout.log").read_text(encoding="utf-8-sig", errors="replace") if (outbox / "stdout.log").is_file() else ""
        stderr = (outbox / "stderr.log").read_text(encoding="utf-8-sig", errors="replace") if (outbox / "stderr.log").is_file() else str(result.get("error", ""))
        sys.stdout.write(stdout)
        sys.stderr.write(stderr)
        attestation = {
            "schema_version": SCHEMA_VERSION,
            "backend": "windows-sandbox-hyper-v",
            "enforced": True,
            "started_at": started,
            "finished_at": _now(),
            "exit_code": int(result.get("exitCode", 126)),
            "timed_out": timed_out,
            "configuration_sha256": _sha256(config_path),
            "command_sha256": hashlib.sha256(json.dumps(command_spec, sort_keys=True).encode("utf-8")).hexdigest(),
            "workspace": str(workspace),
            "workspace_writable": not workspace_read_only,
            "mapped_runtime_roots": [str(root) for root in runtime_roots],
            "mapped_runtime_read_only": True,
            "credential_provider": credential_provider,
            "credential_seed_files": copied_credentials,
            "credential_seed_read_only": True,
            "worker_principal_separated": True,
            "clipboard_disabled": True,
            "device_redirection_disabled": True,
            "networking_enabled": networking_enabled,
            "host_capability": capability,
        }
        if attestation_path:
            attestation_path.parent.mkdir(parents=True, exist_ok=True)
            attestation_path.write_text(json.dumps(attestation, indent=2) + "\n", encoding="utf-8")
        return attestation["exit_code"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one command in a disposable Windows Sandbox VM")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--attestation")
    parser.add_argument("--working-directory")
    parser.add_argument("--credential-provider", choices=("codex", "claude", "gemini"))
    parser.add_argument("--read-only-workspace", action="store_true")
    parser.add_argument("--disable-networking", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        parser.error("a command is required after --")
    return run_in_windows_sandbox(command, Path(args.workspace), args.timeout, Path(args.attestation) if args.attestation else None, Path(args.working_directory) if args.working_directory else None, args.credential_provider, args.read_only_workspace, not args.disable_networking)


if __name__ == "__main__":
    raise SystemExit(main())
