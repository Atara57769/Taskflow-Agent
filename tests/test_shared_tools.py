"""Offline unit tests for shared task management domain tools and storage."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.storage import load_tasks, reset_state, save_memories
from shared.tools_impl import (
    add_task,
    check_public_holidays,
    get_tasks,
    remove_task,
)


class TestSharedTools(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        reset_state(self.data_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_get_and_remove_task(self) -> None:
        res1 = add_task(
            "Prepare Quarterly Report",
            "Monday",
            "work",
            "high",
            data_dir=self.data_dir,
        )
        self.assertIn("added 'prepare quarterly report'", res1)

        res2 = add_task(
            "Buy Groceries",
            "Tuesday",
            "personal",
            "medium",
            data_dir=self.data_dir,
        )
        self.assertIn("total=2", res2)

        work_only = get_tasks(category="work", data_dir=self.data_dir)
        self.assertIn("prepare quarterly report", work_only)
        self.assertNotIn("buy groceries", work_only)

        rem = remove_task("Buy Groceries", data_dir=self.data_dir)
        self.assertIn("removed 'buy groceries'", rem)
        tasks = load_tasks(self.data_dir)
        self.assertNotIn("buy groceries", tasks)
        self.assertIn("prepare quarterly report", tasks)

    def test_remove_missing_task_raises_error(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            remove_task("nonexistent_task", data_dir=self.data_dir)
        self.assertIn("not found in task list", str(ctx.exception))

    def test_schedule_conflict_blocks_forbidden_day(self) -> None:
        save_memories(
            [
                {
                    "category": "scheduling_restriction",
                    "rule": "No Friday tasks: strictly never schedule any tasks on Fridays.",
                    "forbidden_days": ["friday"],
                },
                {
                    "category": "scheduling_restriction",
                    "rule": "No weekend work: strictly do not schedule work tasks on weekends (Saturday or Sunday).",
                    "forbidden_days": ["saturday", "sunday", "weekend"],
                },
            ],
            data_dir=self.data_dir,
        )
        with self.assertRaises(ValueError) as ctx_fri:
            add_task("Client budget meeting", "Friday", "work", "high", data_dir=self.data_dir)
        self.assertIn("Friday", str(ctx_fri.exception))

        with self.assertRaises(ValueError) as ctx_wknd:
            add_task("Server migration", "Saturday", "work", "high", data_dir=self.data_dir)
        self.assertIn("weekend", str(ctx_wknd.exception))

        # Allowed day succeeds
        ok_res = add_task("Server deployment", "Thursday", "work", "high", data_dir=self.data_dir)
        self.assertIn("added 'server deployment'", ok_res)

    @patch("shared.tools_impl._fetch_nager_holidays")
    def test_check_public_holidays_compact_output(
        self, mock_fetch: unittest.mock.MagicMock
    ) -> None:
        mock_fetch.return_value = [
            {
                "date": "2026-01-01",
                "localName": "New Year's Day",
                "name": "New Year's Day",
                "countryCode": "US",
                "fixed": False,
                "global": True,
            },
            {
                "date": "2026-07-03",
                "localName": "Independence Day",
                "name": "Independence Day",
                "countryCode": "US",
                "fixed": False,
                "global": True,
            },
        ]
        output = check_public_holidays("US", year=2026, max_results=2, data_dir=self.data_dir)
        self.assertIn("holidays(US, 2026, top 2):", output)
        self.assertIn("Independence Day", output)
        self.assertLess(len(output), 300)


if __name__ == "__main__":
    unittest.main()
