"""SmartTasks Agent configured declaratively on top of the Claude Agent SDK."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from SDK.tools import ALLOWED_TASK_TOOLS, build_tasks_mcp_server
from shared.config import (
    DEFAULT_DATA_DIR,
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    PROJECT_ROOT,
    SYSTEM_PROMPT,
    calculate_turn_cost_usd,
)

SDK_SYSTEM_PROMPT = (
    f"{SYSTEM_PROMPT}\n"
    "When the user states scheduling rules or work-life restrictions, persist them to CLAUDE.md "
    "so they are remembered across sessions."
)


class SDKAgent:
    """Agent configured declaratively using ClaudeAgentOptions and ClaudeSDKClient."""

    def __init__(
        self,
        session_id: str = "session_1",
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        data_dir: Path | str | None = None,
        client_factory: Any | None = None,
    ) -> None:
        # Unset ANTHROPIC_API_KEY so Claude Code uses personal login instead of API key billing
        os.environ.pop("ANTHROPIC_API_KEY", None)

        self.session_id = session_id
        self.model = model
        self.effort = effort
        self.data_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.client_factory = client_factory

    def _build_options(self) -> ClaudeAgentOptions:
        mcp_server = build_tasks_mcp_server(data_dir=self.data_dir)  # replaces: tools.py
        return ClaudeAgentOptions(
            system_prompt=SDK_SYSTEM_PROMPT,  # replaces: context.py
            model=self.model,
            mcp_servers={"tasks": mcp_server},  # replaces: tools.py
            allowed_tools=list(ALLOWED_TASK_TOOLS),  # replaces: tools.py
            strict_mcp_config=True,  # replaces: tools.py
            setting_sources=["project"],  # replaces: memory.py
            resume=self.session_id,  # replaces: history.py
            cwd=str(PROJECT_ROOT),
            # Context window compaction is handled automatically by Claude Code  # replaces: compaction.py
            # Ephemeral prompt caching is handled automatically by Claude Code  # replaces: caching.py
        )

    def run_turn(self, user_message: str) -> tuple[str, dict[str, Any]]:
        """Run a single turn synchronously by delegating to the async SDK loop."""
        return asyncio.run(self.run_turn_async(user_message))

    async def run_turn_async(self, user_message: str) -> tuple[str, dict[str, Any]]:
        """Execute a turn using ClaudeSDKClient.query() and receive_response()."""
        start_time = time.perf_counter()
        options = self._build_options()
        client = (
            self.client_factory(options)
            if self.client_factory is not None
            else ClaudeSDKClient(options=options)
        )

        reply_text = ""
        tools_used: list[str] = []
        usage_dict: dict[str, Any] = {}
        total_cost_usd = 0.0
        model_calls = 1

        async with client as active:
            await active.query(user_message)  # replaces: loop.py
            async for message in active.receive_response():  # replaces: loop.py
                if hasattr(message, "tools_used") and message.tools_used:
                    tools_used.extend(message.tools_used)
                if hasattr(message, "content") and isinstance(message.content, list):
                    for block in message.content:
                        if getattr(block, "type", "") == "tool_use" or type(block).__name__ == "ToolUseBlock":
                            tools_used.append(getattr(block, "name", "tool"))
                        elif hasattr(block, "text"):
                            reply_text = getattr(block, "text", "")
                if hasattr(message, "result") and message.result:
                    reply_text = str(message.result)
                if hasattr(message, "usage") and message.usage:  # replaces: tokens.py
                    usage_dict = (
                        dict(message.usage)
                        if isinstance(message.usage, dict)
                        else getattr(message.usage, "__dict__", {})
                    )
                if hasattr(message, "total_cost_usd") and message.total_cost_usd is not None:  # replaces: tokens.py
                    total_cost_usd = float(message.total_cost_usd)
                if hasattr(message, "num_turns") and message.num_turns:
                    model_calls = int(message.num_turns)

        duration = time.perf_counter() - start_time
        inp = int(usage_dict.get("input_tokens", 0) or 0)
        cache_read = int(usage_dict.get("cache_read_input_tokens", 0) or 0)
        cache_write = int(usage_dict.get("cache_creation_input_tokens", 0) or 0)
        out = int(usage_dict.get("output_tokens", 0) or 0)
        calls = int(usage_dict.get("model_calls", model_calls) or 1)

        if total_cost_usd == 0.0 and (inp or cache_read or cache_write or out):
            total_cost_usd = calculate_turn_cost_usd(
                input_tokens=inp,
                cache_read_tokens=cache_read,
                cache_write_tokens=cache_write,
                output_tokens=out,
                model=self.model,
            )

        metrics = {
            "input_tokens": inp,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
            "output_tokens": out,
            "model_calls": calls,
            "tools_used": tools_used,
            "cost_usd": round(total_cost_usd, 6),
            "duration_seconds": round(duration, 4),
        }
        return reply_text, metrics
