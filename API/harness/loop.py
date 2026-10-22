"""Agent execution loop for the raw Anthropic Messages API."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from API.harness.caching import apply_cache_breakpoints
from API.harness.history import ConversationHistory
from API.harness.tokens import TurnTokenMetrics
from API.harness.tools import dispatch_tool_call
from shared.config import DEFAULT_MODEL, MAX_TOKENS


def run_agent_loop(
    client: Any,
    model: str,
    system_prompt: str,
    tools_schema: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    history: ConversationHistory,
    session_id: str,
    data_dir: Path | str | None = None,
    max_iterations: int = 8,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Run the Messages API loop while stop_reason == 'tool_use'.

    All tool_result blocks produced in an iteration are returned in a single user message.
    """
    start_time = time.perf_counter()
    metrics = TurnTokenMetrics()
    working_messages = list(messages)

    print(f"[loop.py] Starting turn loop (session='{session_id}', model='{model}')")
    cached_system, cached_tools, cached_messages = apply_cache_breakpoints(
        system_prompt=system_prompt,
        tools=tools_schema,
        messages=working_messages,
    )

    response = client.messages.create(
        model=model or DEFAULT_MODEL,
        max_tokens=MAX_TOKENS,
        system=cached_system,
        tools=cached_tools,
        messages=cached_messages,
    )
    metrics.record_response_usage(response.usage, model=model)
    print(f"[loop.py] Initial model response stop_reason='{response.stop_reason}'")

    iteration = 0
    while response.stop_reason == "tool_use" and iteration < max_iterations:
        iteration += 1
        assistant_blocks = _normalize_content_blocks(response.content)
        working_messages.append({"role": "assistant", "content": assistant_blocks})
        history.append(session_id=session_id, role="assistant", content=assistant_blocks)

        tool_use_blocks = [b for b in assistant_blocks if b.get("type") == "tool_use"]
        print(
            f"[loop.py] Iteration {iteration}: executing {len(tool_use_blocks)} tool_use block(s)"
        )

        # Execute all tool calls and bundle all tool_result blocks into ONE user message
        tool_results: list[dict[str, Any]] = []
        for block in tool_use_blocks:
            tool_name = block["name"]
            tool_input = block.get("input", {})
            tool_use_id = block["id"]
            metrics.tools_used.append(tool_name)
            result_block = dispatch_tool_call(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_use_id=tool_use_id,
                data_dir=data_dir,
            )
            tool_results.append(result_block)

        print(
            f"[loop.py] Bundling {len(tool_results)} tool_result block(s) into a single user message"
        )
        working_messages.append({"role": "user", "content": tool_results})
        history.append(session_id=session_id, role="user", content=tool_results)

        cached_system, cached_tools, cached_messages = apply_cache_breakpoints(
            system_prompt=system_prompt,
            tools=tools_schema,
            messages=working_messages,
        )
        response = client.messages.create(
            model=model or DEFAULT_MODEL,
            max_tokens=MAX_TOKENS,
            system=cached_system,
            tools=cached_tools,
            messages=cached_messages,
        )
        metrics.record_response_usage(response.usage, model=model)
        print(f"[loop.py] Iteration {iteration} model response stop_reason='{response.stop_reason}'")

    final_blocks = _normalize_content_blocks(response.content)
    working_messages.append({"role": "assistant", "content": final_blocks})
    history.append(session_id=session_id, role="assistant", content=final_blocks)

    final_text = _extract_text(final_blocks)
    metrics.duration_seconds = time.perf_counter() - start_time
    print(f"[loop.py] Completed turn loop in {metrics.duration_seconds:.3f}s")
    return final_text, working_messages, metrics.to_dict()


def _normalize_content_blocks(content: Any) -> list[dict[str, Any]]:
    """Convert response content blocks into plain dictionaries."""
    normalized: list[dict[str, Any]] = []
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    for block in content or []:
        if isinstance(block, dict):
            normalized.append(dict(block))
        else:
            btype = getattr(block, "type", "text")
            if btype == "text":
                normalized.append({"type": "text", "text": getattr(block, "text", "")})
            elif btype == "tool_use":
                normalized.append(
                    {
                        "type": "tool_use",
                        "id": getattr(block, "id", "toolu_0"),
                        "name": getattr(block, "name", ""),
                        "input": dict(getattr(block, "input", {}) or {}),
                    }
                )
    return normalized


def _extract_text(blocks: list[dict[str, Any]]) -> str:
    texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    return "\n".join(t for t in texts if t).strip()
