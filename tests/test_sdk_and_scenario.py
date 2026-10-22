"""Offline tests for the SDK agent configuration and replaces annotations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from SDK.agent import SDKAgent
from shared.config import PROJECT_ROOT
from shared.evaluator import HARNESS_MODULES, compute_harness_loc_breakdown


class TestSDKAndScenario(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sdk_options_and_replaces_annotations(self) -> None:
        agent = SDKAgent(session_id="test_sdk_sess", data_dir=self.temp_path)
        opts = agent._build_options()
        self.assertTrue(getattr(opts, "strict_mcp_config", False))
        self.assertEqual(getattr(opts, "setting_sources", []), ["project"])
        self.assertEqual(getattr(opts, "resume", ""), "test_sdk_sess")
        self.assertIn("mcp__tasks__add_task", getattr(opts, "allowed_tools", []))

        loc_info = compute_harness_loc_breakdown(PROJECT_ROOT)
        for mod in HARNESS_MODULES:
            self.assertGreater(
                loc_info["sdk_replaces_by_module"][mod],
                0,
                f"Expected at least one '# replaces: {mod}' annotation in SDK/",
            )


if __name__ == "__main__":
    unittest.main()
