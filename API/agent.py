"""SmartTasks Agent built on the raw Anthropic Messages API harness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import anthropic

from API.harness.compaction import compact_conversation
from API.harness.context import build_turn_system_context
from API.harness.history import ConversationHistory
from API.harness.loop import run_agent_loop
from API.harness.memory import MemoryStore
from API.harness.tools import get_tool_schemas
from shared.config import DEFAULT_DATA_DIR, DEFAULT_EFFORT, DEFAULT_MODEL


class APIAgent:
    """Agent orchestrated manually by the 8 modules in API/harness/."""

    def __init__(
        self,
        session_id: str = "session_1",
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        data_dir: Path | str | None = None,
        client: Any | None = None,
    ) -> None:
        self.session_id = session_id
        self.model = model
        self.effort = effort
        self.data_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.history = ConversationHistory(data_dir=self.data_dir)
        self.memory = MemoryStore(data_dir=self.data_dir)

        # Load persisted state from disk on startup (enables multi-session continuity)
        self.messages: list[dict[str, Any]] = self.history.load_session(self.session_id)
        self.memory.load_all()

        self.client = client if client is not None else anthropic.Anthropic()

    def run_turn(self, user_message: str) -> tuple[str, dict[str, Any]]:
        """Execute a single conversational turn through all 8 harness stages."""
        # 1. Extract and persist long-term memory rules from user message
        self.memory.extract_and_store(user_message=user_message, session_id=self.session_id)

        # 2. Build selective per-turn system context
        system_context = build_turn_system_context(
            user_message=user_message,
            memory_store=self.memory,
            data_dir=self.data_dir,
        )

        # 3. Append user message to active session and disk history
        self.messages.append({"role": "user", "content": user_message})
        self.history.append(session_id=self.session_id, role="user", content=user_message)

        # 4. Compact conversation window if it exceeds threshold
        self.messages = compact_conversation(self.messages)

        # 5. Load tool JSON schemas
        tools_schema = get_tool_schemas()

        # 6. Run agent tool_use loop (applies caching & tracks token/cost metrics)
        reply_text, updated_messages, turn_metrics = run_agent_loop(
            client=self.client,
            model=self.model,
            system_prompt=system_context,
            tools_schema=tools_schema,
            messages=self.messages,
            history=self.history,
            session_id=self.session_id,
            data_dir=self.data_dir,
        )
        self.messages = updated_messages
        return reply_text, turn_metrics
