from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


PROVIDER_ORDER = ("codex", "claude", "gemini")


def detect_providers() -> list[dict[str, Any]]:
    """Detect supported CLIs without making a model call."""
    providers = []
    for name in PROVIDER_ORDER:
        executable = shutil.which(name)
        providers.append({
            "name": name,
            "available": executable is not None,
            "executable": executable,
            "authenticated": "unknown" if executable else False,
        })
    return providers


def choose_plan(
    task: str,
    risk: str = "medium",
    mode: str = "auto",
    time_budget_minutes: int = 30,
) -> dict[str, Any]:
    detected = detect_providers()
    available = [item["name"] for item in detected if item["available"]]
    if "codex" not in available:
        raise RuntimeError("Codex CLI is required as the primary implementation orchestrator")

    if mode == "single":
        desired = 1
    elif mode == "dual":
        desired = 2
    elif mode == "triple":
        desired = 3
    else:
        # Short/low-risk jobs avoid reviewer startup cost. Normal work gets one
        # independent review. High-risk release work gets two when time permits.
        desired = 1 if risk == "low" or time_budget_minutes < 10 else 3 if risk == "high" and time_budget_minutes >= 20 else 2

    selected = [name for name in PROVIDER_ORDER if name in available][:desired]
    roles = []
    if selected:
        roles.append({"provider": "codex", "role": "implementer", "write_access": True})
    if "claude" in selected:
        roles.append({"provider": "claude", "role": "behavior-and-code reviewer", "write_access": False})
    if "gemini" in selected:
        roles.append({"provider": "gemini", "role": "test-and-platform verifier", "write_access": False})

    return {
        "task": task,
        "risk": risk,
        "mode": mode,
        "time_budget_minutes": time_budget_minutes,
        "detected": detected,
        "selected": selected,
        "roles": roles,
        "strategy": "one isolated writer followed by parallel read-only reviews",
        "early_exit": desired > len(selected) or risk != "high",
        "degraded": len(selected) < desired,
        "degraded_reason": None if len(selected) == desired else f"requested {desired} provider(s), but {len(selected)} are installed",
        "cleanroom_boundary": "implementation agents receive only the sanitized handoff and public materials",
    }


def _command(provider: str, workspace: Path, prompt: str, max_turns: int) -> list[str]:
    if provider == "codex":
        return [
            shutil.which("codex") or "codex", "exec", "--json", "--ephemeral",
            "--sandbox", "workspace-write", "--cd", str(workspace), prompt,
        ]
    if provider == "claude":
        return [
            shutil.which("claude") or "claude", "-p", prompt,
            "--output-format", "json", "--max-turns", str(max_turns),
            "--permission-mode", "plan", "--add-dir", str(workspace),
        ]
    if provider == "gemini":
        return [
            shutil.which("gemini") or "gemini", "-p", prompt,
            "--output-format", "json", "--approval-mode", "plan",
        ]
    raise ValueError(f"unsupported provider: {provider}")


def _run_job(provider: str, role: str, workspace: Path, prompt: str, timeout_seconds: int, max_turns: int) -> dict[str, Any]:
    started = time.time()
    command = _command(provider, workspace, prompt, max_turns)
    try:
        result = subprocess.run(
            command,
            cwd=workspace,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            env=os.environ.copy(),
            shell=False,
        )
        return {
            "provider": provider,
            "role": role,
            "status": "passed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "elapsed_seconds": round(time.time() - started, 2),
            "stdout": result.stdout[-200000:],
            "stderr": result.stderr[-50000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "provider": provider,
            "role": role,
            "status": "timed_out",
            "exit_code": None,
            "elapsed_seconds": round(time.time() - started, 2),
            "stdout": (exc.stdout or "")[-200000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-50000:] if isinstance(exc.stderr, str) else "",
        }
    except Exception as exc:
        return {
            "provider": provider,
            "role": role,
            "status": "failed",
            "exit_code": None,
            "elapsed_seconds": round(time.time() - started, 2),
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }


def run_plan(project_root: str, plan: dict[str, Any], sanitized_handoff: str, max_turns: int = 8) -> dict[str, Any]:
    """Run the writer first, then independent reviewers concurrently."""
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("project_root must be an existing directory")
    run_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    run_root = root / ".cleanroom" / "agents" / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    workflow_path = root / ".cleanroom" / "CLEANROOM_WORKFLOW.md"
    if not workflow_path.is_file():
        raise ValueError("project is missing .cleanroom/CLEANROOM_WORKFLOW.md; reinitialize it with the current engine")
    timeout_seconds = max(60, int(plan["time_budget_minutes"] * 60))
    common = (
        "First read .cleanroom/CLEANROOM_WORKFLOW.md completely and follow it as the authoritative "
        "operating contract. You are working in an authorized clean-room implementation. Do not seek or use original, "
        "decompiled, or reconstructed source. Work only from this behavior-only handoff:\n\n"
        + sanitized_handoff
        + "\n\nTask:\n" + plan["task"]
    )
    jobs: list[dict[str, Any]] = []

    implementer = next(item for item in plan["roles"] if item["role"] == "implementer")
    writer_prompt = common + "\n\nImplement the smallest complete change, run relevant tests, and report exact evidence."
    writer = _run_job(implementer["provider"], implementer["role"], root, writer_prompt, timeout_seconds, max_turns)
    jobs.append(writer)

    reviewers = [item for item in plan["roles"] if not item["write_access"]]
    if writer["status"] == "passed" and reviewers:
        remaining = max(60, timeout_seconds - int(writer["elapsed_seconds"]))
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=len(reviewers)) as pool:
            futures = {}
            for item in reviewers:
                review_prompt = common + (
                    "\n\nReview the current workspace read-only. Do not edit files. Identify behavioral gaps, "
                    "test failures, security issues, or unsupported claims. Return concise findings and commands run."
                )
                future = pool.submit(_run_job, item["provider"], item["role"], root, review_prompt, remaining, max_turns)
                futures[future] = item
            for future in as_completed(futures):
                with lock:
                    jobs.append(future.result())

    result = {
        "run_id": run_id,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "plan": plan,
        "jobs": jobs,
        "status": "passed" if jobs and all(item["status"] == "passed" for item in jobs) else "failed",
        "release_gate_override": False,
    }
    (run_root / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result
