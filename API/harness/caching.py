"""Prompt caching breakpoint manager for the raw Anthropic Messages API."""

from __future__ import annotations

import copy
from typing import Any

EPHEMERAL_CACHE = {"type": "ephemeral"}


def apply_cache_breakpoints(
    system_prompt: str,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Attach ephemeral cache_control breakpoints to system prompt, tools, and message prefix."""
    breakpoints_added = 0

    # 1. System prompt breakpoint
    cached_system = [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": dict(EPHEMERAL_CACHE),
        }
    ]
    breakpoints_added += 1

    # 2. Last tool schema breakpoint
    cached_tools = copy.deepcopy(tools)
    if cached_tools:
        cached_tools[-1]["cache_control"] = dict(EPHEMERAL_CACHE)
        breakpoints_added += 1

    # 3. Conversation history prefix breakpoint (second-to-last message)
    cached_messages = copy.deepcopy(messages)
    if len(cached_messages) >= 2:
        target_msg = cached_messages[-2]
        content = target_msg.get("content")
        if isinstance(content, str):
            target_msg["content"] = [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": dict(EPHEMERAL_CACHE),
                }
            ]
            breakpoints_added += 1
        elif isinstance(content, list) and content:
            last_block = content[-1]
            if isinstance(last_block, dict):
                last_block["cache_control"] = dict(EPHEMERAL_CACHE)
                breakpoints_added += 1

    print(f"[caching.py] Applied {breakpoints_added} ephemeral cache_control breakpoint(s)")
    return cached_system, cached_tools, cached_messages
