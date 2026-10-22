"""Offline unit tests for the 8 modules in API/harness/ using a fake client."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from API.agent import APIAgent
from API.harness.caching import apply_cache_breakpoints
from API.harness.compaction import compact_conversation
from API.harness.context import build_turn_system_context
from API.harness.history import ConversationHistory
from API.harness.loop import run_agent_loop
from API.harness.memory import MemoryStore
from API.harness.tokens import compute_cost_usd
from API.harness.tools import dispatch_tool_call, get_tool_schemas
from shared.storage import reset_state


@dataclass
class FakeUsage:
    input_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    output_tokens: int


@dataclass
class FakeResponse:
    content: list[dict[str, Any]]
    stop_reason: str
    usage: FakeUsage


class ScriptedMessagesEndpoint:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class ScriptedClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.messages = ScriptedMessagesEndpoint(responses)


class TestAPIHarnessModules(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        reset_state(self.data_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_loop_bundles_multiple_tool_results_into_single_message(self) -> None:
        fake_client = ScriptedClient(
            [
                FakeResponse(
                    content=[
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "add_task",
                            "input": {
                                "title": "code review",
                                "due_date": "Wednesday",
                                "category": "work",
                                "priority": "high",
                            },
                        },
                        {
                            "type": "tool_use",
                            "id": "call_2",
                            "name": "add_task",
                            "input": {
                                "title": "dentist appointment",
                                "due_date": "Thursday",
                                "category": "health",
                                "priority": "medium",
                            },
                        },
                    ],
                    stop_reason="tool_use",
                    usage=FakeUsage(100, 200, 0, 50),
                ),
                FakeResponse(
                    content=[{"type": "text", "text": "Added code review and dentist appointment."}],
                    stop_reason="end_turn",
                    usage=FakeUsage(120, 200, 0, 30),
                ),
            ]
        )
        history = ConversationHistory(self.data_dir)
        messages = [{"role": "user", "content": "Add code review and dentist appointment."}]

        reply, final_msgs, metrics = run_agent_loop(
            client=fake_client,
            model="claude-opus-4-6",
            system_prompt="You are a task manager helper.",
            tools_schema=get_tool_schemas(),
            messages=messages,
            history=history,
            session_id="test_sess",
            data_dir=self.data_dir,
        )

        self.assertEqual(reply, "Added code review and dentist appointment.")
        self.assertEqual(metrics["model_calls"], 2)
        self.assertEqual(metrics["tools_used"], ["add_task", "add_task"])

        bundled_user_msg = final_msgs[2]
        self.assertEqual(bundled_user_msg["role"], "user")
        self.assertEqual(len(bundled_user_msg["content"]), 2)
        self.assertEqual(bundled_user_msg["content"][0]["type"], "tool_result")
        self.assertEqual(bundled_user_msg["content"][1]["type"], "tool_result")

    def test_tools_returns_is_error_on_failure(self) -> None:
        err_block = dispatch_tool_call(
            tool_name="remove_task",
            tool_input={"title": "missing_task"},
            tool_use_id="call_err_1",
            data_dir=self.data_dir,
        )
        self.assertTrue(err_block.get("is_error"))
        self.assertIn("not found in task list", err_block["content"])

        unknown_block = dispatch_tool_call(
            tool_name="nonexistent_tool",
            tool_input={},
            tool_use_id="call_err_2",
            data_dir=self.data_dir,
        )
        self.assertTrue(unknown_block.get("is_error"))

    def test_history_is_append_only_and_loads_by_session(self) -> None:
        hist = ConversationHistory(self.data_dir)
        hist.append("s1", "user", "Hello from session 1")
        hist.append("s2", "user", "Hello from session 2")
        hist.append("s1", "assistant", "Reply in session 1")

        self.assertEqual(hist.count_all_records(), 3)
        s1_msgs = hist.load_session("s1")
        self.assertEqual(len(s1_msgs), 2)
        self.assertEqual(s1_msgs[0]["content"], "Hello from session 1")

    def test_memory_and_selective_context_engineering(self) -> None:
        mem = MemoryStore(self.data_dir)
        mem.extract_and_store(
            "Please remember my scheduling rules: I never schedule any tasks on Fridays, and I do not schedule work tasks on weekends (Saturday or Sunday).",
            session_id="s1",
        )
        all_mem = mem.load_all()
        self.assertGreaterEqual(len(all_mem), 2)

        dispatch_tool_call(
            "add_task",
            {"title": "prepare quarterly report", "due_date": "Monday", "category": "work", "priority": "high"},
            "t1",
            data_dir=self.data_dir,
        )
        dispatch_tool_call(
            "add_task",
            {"title": "buy groceries", "due_date": "Tuesday", "category": "personal", "priority": "medium"},
            "t2",
            data_dir=self.data_dir,
        )

        ctx = build_turn_system_context("Check work tasks in my schedule", mem, self.data_dir)
        self.assertIn("prepare quarterly report", ctx)
        self.assertIn("1 matched, 1 omitted", ctx)

    def test_compaction_summarizes_when_exceeding_threshold(self) -> None:
        long_messages = [
            {"role": "user", "content": f"Turn {i} user question about scheduled tasks"}
            if i % 2 == 0
            else {"role": "assistant", "content": f"Turn {i} assistant answer"}
            for i in range(10)
        ]
        compacted = compact_conversation(long_messages, max_messages=6, max_chars=200)
        self.assertLess(len(compacted), len(long_messages))
        self.assertIn("[Prior Conversation Summary]", compacted[0]["content"])

    def test_caching_adds_ephemeral_breakpoints(self) -> None:
        sys_blocks, cached_tools, cached_msgs = apply_cache_breakpoints(
            system_prompt="System instructions",
            tools=get_tool_schemas(),
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi"},
                {"role": "user", "content": "What tasks are on my list?"},
            ],
        )
        self.assertEqual(sys_blocks[0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(cached_tools[-1]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(
            cached_msgs[-2]["content"][0]["cache_control"],
            {"type": "ephemeral"},
        )

    def test_tokens_and_runtime_module_print_traces(self) -> None:
        cost = compute_cost_usd(1000, 2000, 500, 300, model="claude-opus-4-6")
        self.assertGreater(cost, 0.0)

        fake_client = ScriptedClient(
            [
                FakeResponse(
                    content=[
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "add_task",
                            "input": {
                                "title": "code review",
                                "due_date": "Wednesday",
                                "category": "work",
                                "priority": "high",
                            },
                        }
                    ],
                    stop_reason="tool_use",
                    usage=FakeUsage(80, 0, 500, 40),
                ),
                FakeResponse(
                    content=[{"type": "text", "text": "Added code review and saved Friday rule."}],
                    stop_reason="end_turn",
                    usage=FakeUsage(110, 500, 0, 35),
                ),
            ]
        )

        buf = io.StringIO()
        with redirect_stdout(buf):
            agent = APIAgent(session_id="trace_sess", data_dir=self.data_dir, client=fake_client)
            agent.run_turn(
                "Please remember I never schedule tasks on Fridays and add 'code review' (due_date: 'Wednesday', category: 'work')."
            )
        stdout_log = buf.getvalue()
        for mod_name in (
            "[memory.py]",
            "[context.py]",
            "[history.py]",
            "[compaction.py]",
            "[tools.py]",
            "[caching.py]",
            "[loop.py]",
            "[tokens.py]",
        ):
            self.assertIn(mod_name, stdout_log)


if __name__ == "__main__":
    unittest.main()
