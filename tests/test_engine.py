from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SERVER = Path(__file__).resolve().parents[1] / "plugin" / "server" / "cleanroom_mcp.py"
SPEC = importlib.util.spec_from_file_location("cleanroom_mcp", SERVER)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


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


if __name__ == "__main__":
    unittest.main()
