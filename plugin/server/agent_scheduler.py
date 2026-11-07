from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from windows_sandbox import probe_windows_sandbox


PROVIDER_ORDER = ("codex", "claude", "gemini")
REVIEW_CONCLUSIONS = {"approved", "no_findings", "changes_required", "blocked"}
ACTIONABLE_SEVERITIES = {"critical", "high", "medium"}
ALLOWED_SEVERITIES = ACTIONABLE_SEVERITIES | {"low", "info"}
RUN_ID_RE = re.compile(r"^run-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$")
EVENT_LOCK = threading.Lock()
DETACHED_WORKERS: dict[int, subprocess.Popen[str]] = {}
WRAPPER_ATTESTATION_CACHE: dict[tuple[str, int], dict[str, Any]] = {}


def _run_probe(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8, shell=False)
        return result.returncode == 0, (result.stdout + result.stderr).strip()[-4000:]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _auth_status(name: str, executable: str) -> tuple[bool | str, str]:
    if name == "codex":
        ok, output = _run_probe([executable, "login", "status"])
        return (True if ok else "unknown"), output
    if name == "claude":
        ok, output = _run_probe([executable, "auth", "status", "--json"])
        if ok:
            try:
                payload = json.loads(output)
                return bool(payload.get("loggedIn")), output
            except json.JSONDecodeError:
                pass
        return False, output
    if name == "gemini":
        home = Path.home() / ".gemini"
        configured = any(path.is_file() and path.stat().st_size > 10 for path in (home / "oauth_creds.json", home / "google_accounts.json"))
        if configured:
            return True, "stored credential material detected"
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            return False, "environment API keys are intentionally not forwarded into isolated agent processes; use stored Gemini authentication"
        return "unknown", "authentication not verifiable without a model request"
    return "unknown", "unsupported provider"


def detect_providers() -> list[dict[str, Any]]:
    providers = []
    for name in PROVIDER_ORDER:
        executable = shutil.which(name)
        authenticated: bool | str = False
        detail = "executable not found"
        if executable:
            authenticated, detail = _auth_status(name, executable)
        providers.append({"name": name, "available": executable is not None, "executable": executable, "authenticated": authenticated, "authentication_detail": detail, "ready": executable is not None and authenticated is not False})
    return providers


def _attest_sandbox_wrapper(wrapper: Path) -> dict[str, Any]:
    """Prove the wrapper permits workspace writes while denying a sibling canary."""
    cache_key = (str(wrapper), wrapper.stat().st_mtime_ns)
    cached = WRAPPER_ATTESTATION_CACHE.get(cache_key)
    if cached:
        return cached
    with tempfile.TemporaryDirectory(prefix="cleanroom-sandbox-attestation-") as temporary:
        temporary_root = Path(temporary).resolve()
        workspace = temporary_root / "workspace"
        workspace.mkdir()
        canary = temporary_root / "outside-canary.txt"
        canary.write_text("must remain inaccessible", encoding="utf-8")
        proof = workspace / "inside-write.txt"
        probe = (
            "import pathlib,sys; outside=pathlib.Path(sys.argv[1]); inside=pathlib.Path(sys.argv[2]); "
            "denied=False; "
            "\ntry:\n outside.read_bytes()\nexcept (OSError,PermissionError):\n denied=True\n"
            "inside.write_text('workspace write allowed',encoding='utf-8'); sys.exit(0 if denied else 9)"
        )
        try:
            result = subprocess.run(
                [str(wrapper), "--workspace", str(workspace), "--", sys.executable, "-c", probe, str(canary), str(proof)],
                cwd=workspace,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                shell=False,
            )
            passed = result.returncode == 0 and proof.is_file() and proof.read_text(encoding="utf-8") == "workspace write allowed"
            detail = "wrapper canary attestation passed" if passed else f"wrapper canary attestation failed with exit code {result.returncode}: {(result.stderr or result.stdout)[-1000:]}"
        except Exception as exc:
            passed = False
            detail = f"wrapper canary attestation failed: {type(exc).__name__}: {exc}"
    attestation = {"passed": passed, "detail": detail, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    WRAPPER_ATTESTATION_CACHE.clear()
    WRAPPER_ATTESTATION_CACHE[cache_key] = attestation
    return attestation


def isolation_status() -> dict[str, Any]:
    preference = os.environ.get("CLEANROOM_SANDBOX_BACKEND", "auto").strip().casefold()
    if preference not in {"auto", "windows-sandbox", "external-wrapper", "none"}:
        return {"backend": "misconfigured", "enforced": False, "reason": f"invalid CLEANROOM_SANDBOX_BACKEND value: {preference}"}
    if preference in {"auto", "windows-sandbox"}:
        capability = probe_windows_sandbox()
        if capability["supported"]:
            return {
                "backend": "windows-sandbox-hyper-v",
                "enforced": True,
                "reason": "Hyper-V-isolated Windows Sandbox is available; each command must produce a runtime attestation",
                "capability": capability,
                "runtime_attestation_required": True,
            }
        if preference == "windows-sandbox":
            return {"backend": "windows-sandbox-unavailable", "enforced": False, "reason": capability["reason"], "capability": capability}
    configured = os.environ.get("CLEANROOM_ENFORCED_SANDBOX_WRAPPER", "").strip()
    if configured and preference != "none":
        wrapper = Path(configured).expanduser().resolve()
        if wrapper.is_file():
            attributes = getattr(wrapper.lstat(), "st_file_attributes", 0)
            if wrapper.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                return {"backend": "misconfigured", "enforced": False, "reason": "sandbox wrapper must not be a symbolic link or reparse point"}
            attestation = _attest_sandbox_wrapper(wrapper)
            if attestation["passed"]:
                return {"backend": "external-enforced-wrapper", "enforced": True, "wrapper": str(wrapper), "attestation": attestation}
            return {"backend": "misconfigured", "enforced": False, "wrapper": str(wrapper), "reason": attestation["detail"], "attestation": attestation}
        return {"backend": "misconfigured", "enforced": False, "reason": f"sandbox wrapper does not exist: {wrapper}"}
    if preference == "external-wrapper":
        return {"backend": "misconfigured", "enforced": False, "reason": "CLEANROOM_SANDBOX_BACKEND requires an external wrapper, but CLEANROOM_ENFORCED_SANDBOX_WRAPPER is unset"}
    reason = probe_windows_sandbox()["reason"] if preference == "auto" else "OS isolation was explicitly disabled"
    return {"backend": "provider-sandbox-and-directory-separation", "enforced": False, "reason": reason + ". Release-producing runs remain blocked. On supported Windows editions, enable Windows Sandbox; otherwise configure an audited external wrapper."}


def wrap_in_sandbox(command: list[str], workspace: Path, attestation_path: Path | None = None, timeout_seconds: int = 1800, working_directory: Path | None = None, credential_provider: str | None = None, read_only_workspace: bool = False, networking_enabled: bool = True) -> list[str]:
    isolation = isolation_status()
    if isolation["backend"] == "windows-sandbox-hyper-v" and isolation["enforced"]:
        wrapper = Path(__file__).resolve().with_name("windows_sandbox.py")
        prefix = [sys.executable, str(wrapper), "--workspace", str(workspace), "--timeout", str(timeout_seconds)]
        if attestation_path is not None:
            prefix.extend(["--attestation", str(attestation_path)])
        if working_directory is not None:
            prefix.extend(["--working-directory", str(working_directory)])
        if credential_provider is not None:
            prefix.extend(["--credential-provider", credential_provider])
        if read_only_workspace:
            prefix.append("--read-only-workspace")
        if not networking_enabled:
            prefix.append("--disable-networking")
        return [*prefix, "--", *command]
    if isolation["backend"] == "external-enforced-wrapper" and isolation["enforced"]:
        return [isolation["wrapper"], "--workspace", str(workspace), "--", *command]
    return command


def choose_plan(task: str, risk: str = "medium", mode: str = "auto", time_budget_minutes: int = 30) -> dict[str, Any]:
    detected = detect_providers()
    ready = [item["name"] for item in detected if item["ready"]]
    installed = [item["name"] for item in detected if item["available"]]
    if "codex" not in installed:
        raise RuntimeError("Codex CLI is required as the primary implementation orchestrator")
    desired = 1 if mode == "single" else 2 if mode == "dual" else 3 if mode == "triple" else 1 if risk == "low" or time_budget_minutes < 10 else 3 if risk == "high" and time_budget_minutes >= 20 else 2
    selected = [name for name in PROVIDER_ORDER if name in ready][:desired]
    if "codex" not in selected:
        selected.insert(0, "codex")
    selected = list(dict.fromkeys(selected))[:desired]
    roles = [{"provider": "codex", "role": "implementer", "write_access": True}]
    if "claude" in selected:
        roles.append({"provider": "claude", "role": "behavior-and-code reviewer", "write_access": False})
    if "gemini" in selected:
        roles.append({"provider": "gemini", "role": "test-and-platform verifier", "write_access": False})
    isolation = isolation_status()
    degraded_reasons = []
    if len(selected) < desired:
        degraded_reasons.append(f"requested {desired} ready provider(s), but selected {len(selected)}")
    if not isolation["enforced"]:
        degraded_reasons.append(isolation["reason"])
    return {"task": task, "risk": risk, "mode": mode, "time_budget_minutes": time_budget_minutes, "detected": detected, "selected": selected, "roles": roles, "strategy": "sanitized separated writer followed by parallel read-only reviews and bounded repair cycles", "early_exit": risk != "high", "degraded": bool(degraded_reasons), "degraded_reason": "; ".join(degraded_reasons) or None, "isolation": isolation, "cleanroom_boundary": "sanitized directory separation; OS enforcement only when isolation.enforced is true"}


def _atomic_json(path: Path, value: Any) -> None:
    if isinstance(value, dict):
        value = _seal_record(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _integrity_key() -> bytes:
    base = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or tempfile.gettempdir()) / "CleanroomRebuild"
    base.mkdir(parents=True, exist_ok=True)
    path = base / "integrity.key"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(os.urandom(32))
    except FileExistsError:
        pass
    data = path.read_bytes()
    if len(data) != 32:
        raise RuntimeError("clean-room integrity key is invalid")
    return data


def _seal_record(value: dict[str, Any]) -> dict[str, Any]:
    record = {key: item for key, item in value.items() if key != "integrity_hmac_sha256"}
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    record["integrity_hmac_sha256"] = hmac.new(_integrity_key(), payload, hashlib.sha256).hexdigest()
    return record


def _record_integrity_valid(value: dict[str, Any]) -> bool:
    supplied = value.get("integrity_hmac_sha256")
    return isinstance(supplied, str) and hmac.compare_digest(supplied, _seal_record(value)["integrity_hmac_sha256"])


def _event(run_root: Path, event_type: str, **fields: Any) -> None:
    record = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "type": event_type, **fields}
    with EVENT_LOCK:
        with (run_root / "events.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        return
    source_attributes = getattr(source.lstat(), "st_file_attributes", 0)
    if source.is_symlink() or source_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError(f"source root cannot be a symbolic link or reparse point: {source}")
    if destination.exists():
        destination_attributes = getattr(destination.lstat(), "st_file_attributes", 0)
        if destination.is_symlink() or destination_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ValueError(f"destination root cannot be a symbolic link or reparse point: {destination}")
    for item in source.rglob("*"):
        attributes = getattr(item.lstat(), "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if item.is_symlink() or attributes & reparse_flag:
            raise ValueError(f"symbolic links and reparse points are forbidden at the clean-room boundary: {item}")
        relative = item.relative_to(source)
        if any(part in {".git", "__pycache__", ".pytest_cache", "analysis", "evidence"} for part in relative.parts):
            continue
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _isolated_root(project_root: Path, run_id: str) -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "CleanroomRebuild" / "isolated"
    identity = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:16]
    return base / identity / run_id


def prepare_isolated_workspace(project_root: Path, run_id: str) -> Path:
    state = project_root / ".cleanroom"
    if state.is_symlink() or (state.exists() and getattr(state.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("project .cleanroom state cannot be a symbolic link or reparse point")
    workspace = _isolated_root(project_root, run_id)
    if workspace.exists():
        raise ValueError(f"isolated workspace already exists: {workspace}")
    (workspace / ".cleanroom" / "handoff").mkdir(parents=True, exist_ok=False)
    (workspace / "implementation").mkdir(parents=True, exist_ok=True)
    for source, destination in ((state / "CLEANROOM_WORKFLOW.md", workspace / ".cleanroom" / "CLEANROOM_WORKFLOW.md"), (state / "handoff" / "specification.json", workspace / ".cleanroom" / "handoff" / "specification.json"), (state / "implementation" / "plan.json", workspace / ".cleanroom" / "implementation-plan.json")):
        if source.is_file():
            attributes = getattr(source.lstat(), "st_file_attributes", 0)
            if source.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise ValueError(f"clean-room input cannot be a symbolic link or reparse point: {source}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    _copy_tree(state / "implementation", workspace / "implementation")
    (workspace / "AGENTS.md").write_text("# Isolated clean-room implementation\n\nRead `.cleanroom/CLEANROOM_WORKFLOW.md` completely. This workspace intentionally excludes analysis artifacts. Work only in `implementation/`.\n", encoding="utf-8")
    _run_probe([shutil.which("git") or "git", "-C", str(workspace), "init", "--quiet"])
    return workspace


def _sync_implementation(workspace: Path, project_root: Path) -> None:
    destination = project_root / ".cleanroom" / "implementation"
    parent = destination.parent
    if parent.is_symlink() or getattr(parent.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError("clean-room state root cannot be a symbolic link or reparse point")
    staging = Path(tempfile.mkdtemp(prefix="implementation-staging-", dir=parent))
    backup = parent / f"implementation-backup-{uuid.uuid4().hex}"
    try:
        _copy_tree(workspace / "implementation", staging)
        if destination.exists():
            attributes = getattr(destination.lstat(), "st_file_attributes", 0)
            if destination.is_symlink() or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
                raise ValueError("implementation destination cannot be a symbolic link or reparse point")
            os.replace(destination, backup)
        os.replace(staging, destination)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _enforce_workspace_budget(workspace: Path, maximum_mb: int) -> None:
    actual = _directory_size(workspace)
    limit = maximum_mb * 1024 * 1024
    if actual > limit:
        raise RuntimeError(f"isolated workspace exceeded disk budget: {actual} > {limit} bytes")


def _command(provider: str, role: str, workspace: Path, prompt: str, max_turns: int, attestation_path: Path, timeout_seconds: int) -> list[str]:
    if provider == "codex":
        command = [shutil.which("codex") or "codex", "exec", "--json", "--ephemeral", "--sandbox", "workspace-write", "--cd", str(workspace), prompt]
    elif provider == "claude":
        command = [shutil.which("claude") or "claude", "-p", prompt, "--output-format", "json", "--max-turns", str(max_turns), "--permission-mode", "plan", "--add-dir", str(workspace)]
    elif provider == "gemini":
        command = [shutil.which("gemini") or "gemini", "-p", prompt, "--output-format", "json", "--approval-mode", "plan"]
    else:
        raise ValueError(f"unsupported provider: {provider}")
    read_only = role not in {"implementer", "remediation writer"}
    return wrap_in_sandbox(command, workspace, attestation_path, timeout_seconds, credential_provider=provider, read_only_workspace=read_only, networking_enabled=True)


def _provider_environment() -> dict[str, str]:
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS", "LANG", "TERM", "COLORTERM"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except Exception:
        process.kill()


def _run_job(provider: str, role: str, workspace: Path, prompt: str, timeout_seconds: int, max_turns: int, run_root: Path) -> dict[str, Any]:
    started = time.time()
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    status = "failed"
    job_id = f"{provider}-{uuid.uuid4().hex[:8]}"
    stdout_path = run_root / f"{job_id}.stdout.log"
    stderr_path = run_root / f"{job_id}.stderr.log"
    attestation_path = run_root / f"{job_id}.sandbox-attestation.json"
    try:
        stdout_stream = stdout_path.open("w", encoding="utf-8")
        stderr_stream = stderr_path.open("w", encoding="utf-8")
        process = subprocess.Popen(_command(provider, role, workspace, prompt, max_turns, attestation_path, timeout_seconds), cwd=workspace, text=True, encoding="utf-8", errors="replace", stdout=stdout_stream, stderr=stderr_stream, env=_provider_environment(), shell=False, creationflags=flags, start_new_session=os.name != "nt")
        _event(run_root, "provider_started", provider=provider, role=role, pid=process.pid)
        while process.poll() is None:
            if (run_root / "cancel.request").exists():
                _terminate_process(process)
                status = "cancelled"
                break
            if time.time() - started > timeout_seconds:
                _terminate_process(process)
                status = "timed_out"
                break
            output_bytes = (stdout_path.stat().st_size if stdout_path.exists() else 0) + (stderr_path.stat().st_size if stderr_path.exists() else 0)
            if output_bytes > 20_000_000:
                _terminate_process(process)
                status = "resource_exceeded"
                break
            time.sleep(0.5)
        process.wait(timeout=15)
        stdout_stream.close()
        stderr_stream.close()
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        if status not in {"cancelled", "timed_out", "resource_exceeded"}:
            status = "completed" if process.returncode == 0 else "failed"
        isolation = isolation_status()
        attestation = None
        if attestation_path.is_file():
            try:
                attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
            except Exception:
                attestation = None
        if isolation.get("runtime_attestation_required") and (not attestation or not attestation.get("enforced")):
            status = "failed"
            stderr += "\nRequired Windows Sandbox runtime attestation is missing or invalid."
        result = {"provider": provider, "role": role, "status": status, "exit_code": process.returncode, "elapsed_seconds": round(time.time() - started, 2), "stdout": stdout[-200000:], "stderr": stderr[-50000:], "isolation_attestation": attestation, "isolation_attestation_sha256": hashlib.sha256(attestation_path.read_bytes()).hexdigest() if attestation_path.is_file() else None}
    except Exception as exc:
        active_process = locals().get("process")
        if active_process is not None:
            _terminate_process(active_process)
        for stream_name in ("stdout_stream", "stderr_stream"):
            stream = locals().get(stream_name)
            if stream and not stream.closed:
                stream.close()
        result = {"provider": provider, "role": role, "status": "failed", "exit_code": None, "elapsed_seconds": round(time.time() - started, 2), "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}
    _event(run_root, "provider_finished", provider=provider, role=role, status=result["status"], elapsed_seconds=result["elapsed_seconds"])
    return result


def _json_candidates(text: str) -> list[Any]:
    candidates: list[Any] = []
    try:
        candidates.append(json.loads(text))
    except Exception:
        pass
    for line in reversed(text.splitlines()):
        try:
            candidates.append(json.loads(line))
        except Exception:
            continue
    return candidates


def _find_review(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if "conclusion" in value and "findings" in value:
            return value
        for key in ("result", "message", "content", "response", "output", "structured_output"):
            if key in value:
                found = _find_review(value[key])
                if found:
                    return found
        for item in value.values():
            found = _find_review(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in reversed(value):
            found = _find_review(item)
            if found:
                return found
    elif isinstance(value, str) and value.strip().startswith(("{", "[")):
        for candidate in _json_candidates(value):
            found = _find_review(candidate)
            if found:
                return found
    return None


def _parse_review(job: dict[str, Any]) -> dict[str, Any]:
    if job["status"] != "completed":
        return {"valid": False, "conclusion": "blocked", "findings": [], "error": f"provider status: {job['status']}"}
    review = next((found for candidate in _json_candidates(job.get("stdout", "")) if (found := _find_review(candidate))), None)
    if not review or review.get("conclusion") not in REVIEW_CONCLUSIONS or not isinstance(review.get("findings"), list):
        return {"valid": False, "conclusion": "blocked", "findings": [], "error": "reviewer did not return the required JSON schema"}
    normalized = []
    for finding in review["findings"][:100]:
        if not isinstance(finding, dict):
            return {"valid": False, "conclusion": "blocked", "findings": [], "error": "finding is not an object"}
        severity = finding.get("severity")
        if not isinstance(severity, str) or severity not in ALLOWED_SEVERITIES:
            return {"valid": False, "conclusion": "blocked", "findings": [], "error": f"invalid finding severity: {severity!r}"}
        if not all(isinstance(finding.get(field), str) and finding[field].strip() for field in ("title", "evidence", "remediation")):
            return {"valid": False, "conclusion": "blocked", "findings": [], "error": "finding is missing required string fields"}
        normalized.append({"id": str(finding.get("id") or uuid.uuid4().hex[:12]), "severity": severity, "title": finding["title"][:300], "evidence": finding["evidence"][:4000], "remediation": finding["remediation"][:4000]})
    if review["conclusion"] == "no_findings" and normalized:
        return {"valid": False, "conclusion": "blocked", "findings": [], "error": "no_findings conclusion must have an empty findings array"}
    if review["conclusion"] == "approved" and any(item["severity"] in ACTIONABLE_SEVERITIES for item in normalized):
        return {"valid": False, "conclusion": "blocked", "findings": normalized, "error": "approved conclusion cannot contain actionable findings"}
    return {"valid": True, "conclusion": review["conclusion"], "findings": normalized, "commands_run": review.get("commands_run", [])[:100]}


def _review_prompt(common: str, role: str) -> str:
    schema = {"conclusion": "approved|no_findings|changes_required|blocked", "findings": [{"id": "stable-id", "severity": "critical|high|medium|low|info", "title": "short title", "evidence": "file/behavior and observed evidence", "remediation": "independent fix"}], "commands_run": ["actual commands only"]}
    return common + f"\n\nAct as the {role}. Review read-only; never edit files. Return ONLY a JSON object with this schema: " + json.dumps(schema)


def _write_status(run_root: Path, request: dict[str, Any], status: str, **fields: Any) -> None:
    current = {}
    path = run_root / "status.json"
    if path.is_file():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    _atomic_json(path, {**current, "run_id": request["run_id"], "status": status, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **fields})


def execute_request(request_path: Path) -> int:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if not _record_integrity_valid(request):
        raise ValueError("agent request integrity verification failed")
    project_root = Path(request["project_root"]).resolve()
    run_root = request_path.parent
    plan = request["plan"]
    timeout_seconds = max(60, int(plan["time_budget_minutes"] * 60))
    _write_status(run_root, request, "preparing", worker_pid=os.getpid(), phase="isolation", isolation=request.get("isolation"))
    try:
        workspace = prepare_isolated_workspace(project_root, request["run_id"])
        _event(run_root, "workspace_ready", workspace=str(workspace), source_boundary="sanitized-only")
        common = "Read .cleanroom/CLEANROOM_WORKFLOW.md completely. This sanitized workspace contains no analysis artifacts and is OS-isolated only when the recorded isolation attestation is enforced. Work only from its sanitized handoff and independent files. Task:\n" + plan["task"]
        jobs: list[dict[str, Any]] = []
        writer_role = next(item for item in plan["roles"] if item["role"] == "implementer")
        _write_status(run_root, request, "running", phase="implementation", workspace=str(workspace), jobs=jobs)
        writer = _run_job(writer_role["provider"], writer_role["role"], workspace, common + "\n\nImplement the smallest complete change in implementation/, run relevant tests, and report exact evidence.", timeout_seconds, int(request["max_turns"]), run_root)
        jobs.append(writer)
        if writer["status"] != "completed":
            raise RuntimeError(f"writer did not complete: {writer['status']}")
        _enforce_workspace_budget(workspace, int(request.get("max_workspace_mb", 4096)))
        _sync_implementation(workspace, project_root)
        reviewers = [item for item in plan["roles"] if not item["write_access"]]
        review_cycles: list[dict[str, Any]] = []
        max_cycles = int(request.get("max_repair_cycles", 2))
        for cycle in range(max_cycles + 1):
            if (run_root / "cancel.request").exists():
                _write_status(run_root, request, "cancelled", phase="cancelled", jobs=jobs, review_cycles=review_cycles)
                return 2
            if not reviewers:
                break
            _write_status(run_root, request, "running", phase=f"review-{cycle + 1}", jobs=jobs, review_cycles=review_cycles)
            cycle_jobs = []
            concurrency = 1 if request.get("isolation", {}).get("backend") == "windows-sandbox-hyper-v" else min(len(reviewers), int(request.get("max_parallel_reviewers", 2)))
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = {pool.submit(_run_job, item["provider"], item["role"], workspace, _review_prompt(common, item["role"]), timeout_seconds, int(request["max_turns"]), run_root): item for item in reviewers}
                for future in as_completed(futures):
                    job = future.result()
                    job["review"] = _parse_review(job)
                    jobs.append(job)
                    cycle_jobs.append(job)
            actionable = [finding for job in cycle_jobs for finding in job["review"]["findings"] if finding["severity"] in ACTIONABLE_SEVERITIES]
            approved = all(job["review"]["valid"] for job in cycle_jobs) and not actionable and all(job["review"]["conclusion"] in {"approved", "no_findings"} for job in cycle_jobs)
            review_cycles.append({"cycle": cycle + 1, "approved": approved, "actionable_findings": actionable, "reviews": [{"provider": job["provider"], **job["review"]} for job in cycle_jobs]})
            if approved or cycle >= max_cycles:
                break
            remediation = actionable or [{"title": "Invalid or blocked review", "remediation": "Resolve reviewer schema or verification blockers and rerun tests."}]
            _write_status(run_root, request, "running", phase=f"repair-{cycle + 1}", jobs=jobs, review_cycles=review_cycles)
            repair = _run_job("codex", "remediation writer", workspace, common + "\n\nIndependently remediate these findings, run tests, and edit only implementation/:\n" + json.dumps(remediation, indent=2), timeout_seconds, int(request["max_turns"]), run_root)
            jobs.append(repair)
            if repair["status"] != "completed":
                break
            _enforce_workspace_budget(workspace, int(request.get("max_workspace_mb", 4096)))
            _sync_implementation(workspace, project_root)
        approved = not reviewers or bool(review_cycles and review_cycles[-1]["approved"])
        result = {"run_id": request["run_id"], "started_at": request["created_at"], "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "plan": plan, "isolation": request.get("isolation"), "isolated_workspace": str(workspace), "jobs": jobs, "review_cycles": review_cycles, "status": "passed" if approved else "failed", "release_gate_override": False}
        _atomic_json(run_root / "result.json", result)
        _write_status(run_root, request, result["status"], phase="complete", jobs=jobs, review_cycles=review_cycles, result=str(run_root / "result.json"))
        _event(run_root, "run_finished", status=result["status"])
        return 0 if approved else 1
    except Exception as exc:
        _write_status(run_root, request, "failed", phase="failed", error=f"{type(exc).__name__}: {exc}")
        _event(run_root, "run_failed", error=f"{type(exc).__name__}: {exc}")
        return 1


def start_plan(project_root: str, plan: dict[str, Any], max_turns: int = 8, max_repair_cycles: int = 2, max_parallel_reviewers: int = 2, max_workspace_mb: int = 4096, require_enforced_isolation: bool = False) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("project_root must be an existing directory")
    isolation = isolation_status()
    if not isolation["enforced"]:
        raise RuntimeError(isolation["reason"])
    run_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    run_root = root / ".cleanroom" / "agents" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    request = {"run_id": run_id, "project_root": str(root), "plan": plan, "isolation": isolation, "max_turns": max_turns, "max_repair_cycles": max_repair_cycles, "max_parallel_reviewers": max_parallel_reviewers, "max_workspace_mb": max_workspace_mb, "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    request_path = run_root / "request.json"
    _atomic_json(request_path, request)
    _write_status(run_root, request, "queued", phase="queued")
    stdout = (run_root / "worker.stdout.log").open("w", encoding="utf-8")
    stderr = (run_root / "worker.stderr.log").open("w", encoding="utf-8")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", str(request_path)], cwd=run_root, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, close_fds=True, creationflags=flags, start_new_session=os.name != "nt")
    stdout.close()
    stderr.close()
    DETACHED_WORKERS[process.pid] = process
    def reap_worker() -> None:
        try:
            process.wait()
        finally:
            DETACHED_WORKERS.pop(process.pid, None)
    threading.Thread(target=reap_worker, name=f"cleanroom-reaper-{process.pid}", daemon=True).start()
    _write_status(run_root, request, "queued", phase="queued", worker_pid=process.pid)
    return {"run_id": run_id, "status": "queued", "worker_pid": process.pid, "status_path": str(run_root / "status.json"), "events_path": str(run_root / "events.jsonl"), "asynchronous": True}


def read_run_status(project_root: str, run_id: str | None = None) -> dict[str, Any]:
    agents = Path(project_root).expanduser().resolve() / ".cleanroom" / "agents"
    runs = []
    if agents.is_dir():
        for path in agents.glob("run-*"):
            try:
                runs.append(_validated_run_root(agents, path.name))
            except ValueError:
                continue
        runs.sort(reverse=True)
    target = _validated_run_root(agents, run_id) if run_id else runs[0] if runs else None
    if target is None:
        return {"run_count": 0, "latest": None, "events": []}
    if not target.is_dir():
        raise ValueError(f"agent run not found: {run_id}")
    status = json.loads((target / "status.json").read_text(encoding="utf-8")) if (target / "status.json").is_file() else {"run_id": target.name, "status": "unknown"}
    if not _record_integrity_valid(status):
        raise ValueError(f"agent status integrity verification failed: {target / 'status.json'}")
    events = []
    if (target / "events.jsonl").is_file():
        for line in (target / "events.jsonl").read_text(encoding="utf-8").splitlines()[-100:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return {"run_count": len(runs), "latest": status, "events": events}


def _validated_run_root(agents: Path, run_id: str) -> Path:
    if not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("invalid agent run ID")
    agents_resolved = agents.resolve()
    target = (agents_resolved / run_id).resolve()
    try:
        target.relative_to(agents_resolved)
    except ValueError as exc:
        raise ValueError("agent run path escapes the project") from exc
    if not target.is_dir() or target.is_symlink() or getattr(target.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError(f"agent run not found or unsafe: {run_id}")
    return target


def cancel_run(project_root: str, run_id: str | None = None) -> dict[str, Any]:
    status = read_run_status(project_root, run_id)
    latest = status.get("latest")
    if not latest:
        raise ValueError("no agent run exists")
    if latest.get("status") in {"passed", "failed", "cancelled"}:
        return {"run_id": latest["run_id"], "status": latest["status"], "cancel_requested": False}
    agents = Path(project_root).expanduser().resolve() / ".cleanroom" / "agents"
    run_root = _validated_run_root(agents, latest["run_id"])
    (run_root / "cancel.request").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n", encoding="utf-8")
    _event(run_root, "cancel_requested")
    return {"run_id": latest["run_id"], "status": latest.get("status"), "cancel_requested": True}


def resume_run(project_root: str, run_id: str | None = None) -> dict[str, Any]:
    status = read_run_status(project_root, run_id)
    latest = status.get("latest")
    if not latest:
        raise ValueError("no agent run exists")
    agents = Path(project_root).expanduser().resolve() / ".cleanroom" / "agents"
    old_root = _validated_run_root(agents, latest["run_id"])
    request = json.loads((old_root / "request.json").read_text(encoding="utf-8"))
    if not _record_integrity_valid(request):
        raise ValueError("agent request integrity verification failed")
    return start_plan(project_root, request["plan"], request["max_turns"], request.get("max_repair_cycles", 2), request.get("max_parallel_reviewers", 2), request.get("max_workspace_mb", 4096), bool(request.get("isolation", {}).get("enforced")))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        raise SystemExit(execute_request(Path(sys.argv[2]).resolve()))
    raise SystemExit("usage: agent_scheduler.py --worker <request.json>")
