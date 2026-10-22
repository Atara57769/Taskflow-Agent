"""Context window compaction for conversations exceeding the size threshold."""

from __future__ import annotations

import json
from typing import Any


def compact_conversation(
    messages: list[dict[str, Any]],
    max_messages: int = 6,
    max_chars: int = 2200,
) -> list[dict[str, Any]]:
    """Summarize older messages when conversation history exceeds threshold."""
    total_chars = sum(len(json.dumps(m, default=str)) for m in messages)
    print(
        f"[compaction.py] Checking context window: {len(messages)} message(s), "
        f"{total_chars} chars (limits: {max_messages} msgs / {max_chars} chars)"
    )

    if len(messages) <= max_messages and total_chars <= max_chars:
        print("[compaction.py] Conversation within threshold; no compaction required")
        return list(messages)

    # Find a safe split point that starts at a plain user text message (not a tool_result)
    split_idx = max(2, len(messages) - 3)
    while split_idx > 0 and not _is_plain_user_message(messages[split_idx]):
        split_idx -= 1

    if split_idx <= 1:
        print("[compaction.py] No safe split boundary found; keeping full messages")
        return list(messages)

    older = messages[:split_idx]
    recent = messages[split_idx:]
    summary_text = _summarize_messages(older)

    compacted: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": f"[Prior Conversation Summary]\n{summary_text}",
        },
        {
            "role": "assistant",
            "content": "Understood. I have the compacted summary of earlier turns.",
        },
        *recent,
    ]
    new_chars = sum(len(json.dumps(m, default=str)) for m in compacted)
    print(
        f"[compaction.py] Compacted {len(older)} older message(s) -> "
        f"window reduced from {len(messages)} to {len(compacted)} messages ({total_chars} -> {new_chars} chars)"
    )
    return compacted


def _is_plain_user_message(message: dict[str, Any]) -> bool:
    if message.get("role") != "user":
        return False
    content = message.get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        )
    return False


def _summarize_messages(messages: list[dict[str, Any]]) -> str:
    bullet_points: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str):
            snippet = content.strip().replace("\n", " ")[:120]
            bullet_points.append(f"- {role}: {snippet}")
        elif isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    btype = block.get("type", "")
                    if btype == "text":
                        parts.append(block.get("text", "")[:80])
                    elif btype == "tool_use":
                        parts.append(f"called {block.get('name')}")
                    elif btype == "tool_result":
                        parts.append(f"result: {str(block.get('content', ''))[:60]}")
            if parts:
                bullet_points.append(f"- {role}: {'; '.join(parts)}")
    return "\n".join(bullet_points[:8])
