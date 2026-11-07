from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER = Path(__file__).resolve().parents[1] / "plugin" / "server" / "cleanroom_mcp.py"
SPEC = importlib.util.spec_from_file_location("cleanroom_mcp", SERVER)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
import agent_scheduler as SCHEDULER


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        os.environ["LOCALAPPDATA"] = self.temporary.name
        self.root = Path(self.temporary.name) / "project"
        MODULE._initialize({
            "project_root": str(self.root),
            "project_name": "Fixture",
            "product_goal": "Exercise the deterministic workflow engine.",
            "source_description": "Synthetic test target.",
            "authorization_basis": "Test fixture authored by this project.",
        })

    def test_incomplete_project_is_blocked(self) -> None:
        gate = MODULE._release_gate({"project_root": str(self.root)})
        self.assertFalse(gate["release_ready"])
        self.assertTrue(gate["blockers"])

    def test_only_engine_executed_validation_satisfies_gate_kind(self) -> None:
        MODULE._record_validation({
            "project_root": str(self.root), "kind": "build", "name": "manual claim",
            "passed": True, "command": "not executed", "evidence_reference": "manual note",
        })
        gate = MODULE._release_gate({"project_root": str(self.root)})
        self.assertIn("build", next(item for item in gate["blockers"] if item.startswith("Missing passing validation kinds")))
        executed = MODULE._run_validation({
            "project_root": str(self.root), "kind": "build", "name": "engine fixture",
            "command": [os.sys.executable, "-c", "print('built')"], "timeout_seconds": 30,
            "require_enforced_isolation": False,
        })
        self.assertTrue(executed["passed"])
        self.assertTrue(executed["engine_executed"])
        gate = MODULE._release_gate({"project_root": str(self.root)})
        missing = next(item for item in gate["blockers"] if item.startswith("Missing passing validation kinds"))
        self.assertIn("build", missing)
        MODULE._record_validation({
            "project_root": str(self.root), "kind": "build", "name": "attested engine fixture",
            "passed": True, "command": f"{os.sys.executable} -c print('built')",
            "evidence_reference": "attested fixture", "_engine_executed": True,
            "_isolation_enforced": True,
        })
        gate = MODULE._release_gate({"project_root": str(self.root)})
        missing = next(item for item in gate["blockers"] if item.startswith("Missing passing validation kinds"))
        self.assertNotIn("build", missing)

    def test_detailed_agent_contract_is_installed_in_every_project(self) -> None:
        contract = self.root / ".cleanroom" / "CLEANROOM_WORKFLOW.md"
        self.assertTrue(contract.is_file())
        text = contract.read_text(encoding="utf-8")
        for heading in (
            "Non-negotiable clean-room boundary",
            "Automatic end-to-end state machine",
            "Provider responsibilities",
            "Failure and recovery rules",
            "Prohibited actions",
        ):
            self.assertIn(heading, text)
        expected = MODULE._read_json(self.root / ".cleanroom" / "policy.json", {})["agent_workflow_sha256"]
        self.assertEqual(MODULE.hashlib.sha256(text.encode("utf-8")).hexdigest(), expected)

    def test_dashboard_is_direct_and_model_free(self) -> None:
        snapshot = MODULE._dashboard({"project_root": str(self.root)})
        self.assertTrue(snapshot["configured"])
        self.assertTrue(snapshot["no_llm_used"])
        self.assertEqual(snapshot["data_source"], "direct local workflow state")
        self.assertEqual(len(snapshot["progress"]["steps"]), 10)

    def test_source_shaped_handoff_fact_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            MODULE._record({
                "project_root": str(self.root),
                "category": "behavior",
                "statement": "def copied(): return 1; return 2; return 3;",
                "source_tool": "fixture",
                "source_reference": "fixture",
                "confidence": "observed",
            })

    def test_dashboard_resource_is_registered(self) -> None:
        listed = MODULE._handle({"jsonrpc": "2.0", "id": 1, "method": "resources/list", "params": {}})
        self.assertEqual(listed["result"]["resources"][0]["mimeType"], "text/html;profile=mcp-app")
        read = MODULE._handle({"jsonrpc": "2.0", "id": 2, "method": "resources/read", "params": {"uri": MODULE.STATUS_RESOURCE_URI}})
        self.assertIn("Clean-room Live Status", read["result"]["contents"][0]["text"])

    def test_agent_plan_is_deterministic_and_model_free(self) -> None:
        MODULE._record({
            "project_root": str(self.root), "category": "behavior",
            "statement": "For input A the product returns B.", "source_tool": "fixture",
            "source_reference": "black-box test", "confidence": "observed",
        })
        MODULE._handoff({"project_root": str(self.root)})
        with patch("agent_scheduler.shutil.which", side_effect=lambda name: f"/fixture/{name}" if name in {"codex", "claude"} else None):
            plan = MODULE._agent_plan({
                "project_root": str(self.root), "task": "Implement fixture behavior.",
                "risk": "medium", "mode": "auto", "time_budget_minutes": 30,
            })
        self.assertEqual(plan["selected"][0], "codex")
        self.assertLessEqual(len(plan["selected"]), 2)
        status = MODULE._agent_status({"project_root": str(self.root)})
        self.assertTrue(status["no_llm_used"])

    def test_installer_and_plugin_contracts_match(self) -> None:
        repository = SERVER.parents[2]
        installer = repository / "installer" / "CLEANROOM_WORKFLOW.md"
        bundled = repository / "plugin" / "CLEANROOM_WORKFLOW.md"
        self.assertEqual(installer.read_bytes(), bundled.read_bytes())

    def test_supply_chain_and_lifecycle_assets_are_present(self) -> None:
        repository = SERVER.parents[2]
        installer = repository / "installer"
        for name in (
            "python-gpu-requirements.lock",
            "Generate-SBOM.ps1",
            "Export-Diagnostics.ps1",
            "Repair-CleanroomRebuild.ps1",
            "Update-CleanroomRebuild.ps1",
            "Uninstall-CleanroomRebuild.ps1",
            "Sign-Release.ps1",
        ):
            self.assertTrue((installer / name).is_file(), name)
        lock = (installer / "python-gpu-requirements.lock").read_text(encoding="utf-8")
        self.assertIn("torch==2.4.1", lock)
        self.assertIn("transformers==4.55.3", lock)
        self.assertNotIn(">=", lock)

    def test_mcp_exposes_async_lifecycle_tools(self) -> None:
        names = {tool["name"] for tool in MODULE.TOOLS}
        self.assertEqual(len(names), 21)
        for name in ("cleanroom_agent_run", "cleanroom_agent_status", "cleanroom_agent_cancel", "cleanroom_agent_resume"):
            self.assertIn(name, names)
        self.assertIn("cleanroom_run_validation", names)

    def _install_fake_agents(self, sleep_seconds: float = 0) -> None:
        binary = Path(self.temporary.name) / "fake-bin"
        binary.mkdir(exist_ok=True)
        script = binary / "fake_cli.py"
        script.write_text(
            "import json,os,sys,time\n"
            "from pathlib import Path\n"
            "role=sys.argv[1]\n"
            "time.sleep(5 if 'SLOW_TEST' in ' '.join(sys.argv) else 0)\n"
            "if role=='codex':\n"
            " p=Path.cwd()/'implementation'/'artifact.txt';p.parent.mkdir(exist_ok=True);p.write_text('independent build\\n',encoding='utf-8');print(json.dumps({'type':'agent_message','text':'implemented'}))\n"
            "else:\n"
            " print(json.dumps({'conclusion':'approved','findings':[],'commands_run':['fake verification']}))\n",
            encoding="utf-8",
        )
        if os.name == "nt":
            for name in ("codex", "claude", "gemini"):
                (binary / f"{name}.cmd").write_text(f'@echo off\r\n"{os.environ.get("PYTHON", os.sys.executable)}" "%~dp0fake_cli.py" {name} %*\r\n', encoding="utf-8")
        else:
            for name in ("codex", "claude", "gemini"):
                wrapper = binary / name
                wrapper.write_text(f"#!/bin/sh\nexec '{os.sys.executable}' '{script}' '{name}' \"$@\"\n", encoding="utf-8")
                wrapper.chmod(0o755)
        previous_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(binary) + os.pathsep + previous_path
        self.addCleanup(lambda: os.environ.__setitem__("PATH", previous_path))

    def _scheduler_plan(self) -> dict:
        return {
            "task": "Build the synthetic independent implementation.",
            "risk": "high", "mode": "triple", "time_budget_minutes": 2,
            "selected": ["codex", "claude", "gemini"],
            "roles": [
                {"provider": "codex", "role": "implementer", "write_access": True},
                {"provider": "claude", "role": "behavior-and-code reviewer", "write_access": False},
                {"provider": "gemini", "role": "test-and-platform verifier", "write_access": False},
            ],
        }

    def test_async_isolated_agent_run_and_structured_reviews(self) -> None:
        self._install_fake_agents()
        handoff = self.root / ".cleanroom" / "handoff" / "specification.json"
        handoff.write_text(json.dumps({"behavior": "A returns B"}), encoding="utf-8")
        started = SCHEDULER.start_plan(str(self.root), self._scheduler_plan(), max_turns=2, max_repair_cycles=1)
        self.assertTrue(started["asynchronous"])
        deadline = time.time() + 20
        while time.time() < deadline:
            status = SCHEDULER.read_run_status(str(self.root), started["run_id"])
            if status["latest"]["status"] in {"passed", "failed", "cancelled"}:
                break
            time.sleep(0.2)
        self.assertEqual(status["latest"]["status"], "passed")
        workspace = Path(status["latest"]["workspace"])
        self.assertFalse((workspace / ".cleanroom" / "analysis").exists())
        self.assertTrue((self.root / ".cleanroom" / "implementation" / "artifact.txt").is_file())
        self.assertTrue(any(event["type"] == "workspace_ready" for event in status["events"]))

    def test_async_agent_run_can_be_cancelled(self) -> None:
        self._install_fake_agents(sleep_seconds=5)
        handoff = self.root / ".cleanroom" / "handoff" / "specification.json"
        handoff.write_text(json.dumps({"behavior": "A returns B"}), encoding="utf-8")
        plan = self._scheduler_plan()
        plan["task"] += " SLOW_TEST"
        plan["roles"] = plan["roles"][:1]
        plan["selected"] = ["codex"]
        started = SCHEDULER.start_plan(str(self.root), plan, max_turns=1)
        time.sleep(0.8)
        cancelled = SCHEDULER.cancel_run(str(self.root), started["run_id"])
        self.assertTrue(cancelled["cancel_requested"])
        deadline = time.time() + 15
        while time.time() < deadline:
            status = SCHEDULER.read_run_status(str(self.root), started["run_id"])
            if status["latest"]["status"] in {"cancelled", "failed"}:
                break
            time.sleep(0.2)
        self.assertIn(status["latest"]["status"], {"cancelled", "failed"})

    def test_run_id_traversal_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            SCHEDULER.read_run_status(str(self.root), "../outside")
        with self.assertRaises(ValueError):
            SCHEDULER.cancel_run(str(self.root), "C:\\Windows")

    def test_malformed_reviewer_severity_is_not_approved(self) -> None:
        job = {
            "status": "completed",
            "stdout": json.dumps({
                "conclusion": "approved",
                "findings": [{"id": "x", "severity": "HIGH ", "title": "Issue", "evidence": "evidence", "remediation": "fix"}],
                "commands_run": [],
            }),
        }
        review = SCHEDULER._parse_review(job)
        self.assertFalse(review["valid"])
        self.assertEqual(review["conclusion"], "blocked")

    def test_provider_environment_excludes_secrets(self) -> None:
        os.environ["CLEANROOM_TEST_SECRET_TOKEN"] = "must-not-leak"
        self.addCleanup(lambda: os.environ.pop("CLEANROOM_TEST_SECRET_TOKEN", None))
        environment = SCHEDULER._provider_environment()
        self.assertNotIn("CLEANROOM_TEST_SECRET_TOKEN", environment)

    def test_high_risk_can_require_enforced_isolation(self) -> None:
        previous = os.environ.pop("CLEANROOM_ENFORCED_SANDBOX_WRAPPER", None)
        self.addCleanup(lambda: previous is None or os.environ.__setitem__("CLEANROOM_ENFORCED_SANDBOX_WRAPPER", previous))
        with self.assertRaises(RuntimeError):
            SCHEDULER.start_plan(str(self.root), self._scheduler_plan(), require_enforced_isolation=True)


if __name__ == "__main__":
    unittest.main()
