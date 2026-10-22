"""Append-only disk-persisted conversation history manager for the API harness."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from shared.storage import get_history_path


class ConversationHistory:
    """Manages append-only conversation history in JSON Lines format on disk."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.history_file = get_history_path(data_dir)

    def append(self, session_id: str, role: str, content: Any) -> None:
        """Append a single message record to the JSONL history file on disk."""
        record = {
            "timestamp": round(time.time(), 4),
            "session_id": session_id,
            "role": role,
            "content": _serialize_content(content),
        }
        print(
            f"[history.py] Appending message (session='{session_id}', role='{role}') "
            f"to {self.history_file.name}"
        )
        with self.history_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

    def load_session(self, session_id: str) -> list[dict[str, Any]]:
        """Load all conversation messages belonging to a specific session_id."""
        print(f"[history.py] Loading session '{session_id}' from {self.history_file.name}")
        if not self.history_file.exists():
            return []

        messages: list[dict[str, Any]] = []
        with self.history_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("session_id") == session_id:
                    messages.append(
                        {
                            "role": record["role"],
                            "content": record["content"],
                        }
                    )
        print(f"[history.py] Loaded {len(messages)} message(s) for session '{session_id}'")
        return messages

    def count_all_records(self) -> int:
        """Return total number of appended JSONL records across all sessions."""
        if not self.history_file.exists():
            return 0
        with self.history_file.open("r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())


def _serialize_content(content: Any) -> Any:
    """Convert SDK/dataclass content blocks into JSON-serializable structures."""
    if isinstance(content, (str, int, float, bool)) or content is None:
        return content
    if isinstance(content, list):
        return [_serialize_content(item) for item in content]
    if isinstance(content, dict):
        return {k: _serialize_content(v) for k, v in content.items()}
    if hasattr(content, "model_dump"):
        return content.model_dump()
    if hasattr(content, "__dict__"):
        return {k: _serialize_content(v) for k, v in content.__dict__.items() if not k.startswith("_")}
    return str(content)
