"""Selective per-turn context engineering for the API harness."""

from __future__ import annotations

from pathlib import Path

from API.harness.memory import MemoryStore
from shared.config import SYSTEM_PROMPT
from shared.storage import load_tasks


def build_turn_system_context(
    user_message: str,
    memory_store: MemoryStore,
    data_dir: Path | str | None = None,
) -> str:
    """Build a selective system prompt containing only context relevant to the current turn."""
    print("[context.py] Selecting relevant context for current turn")
    sections: list[str] = [SYSTEM_PROMPT]

    # 1. Selective Memory Injection
    relevant_memories = memory_store.retrieve_relevant(user_message)
    if relevant_memories:
        mem_lines = [f"- {m['rule']}" for m in relevant_memories]
        sections.append("Active Scheduling Rules & Memory:\n" + "\n".join(mem_lines))

    # 2. Selective Task List Snapshot (only categories or task titles mentioned in the turn)
    all_tasks = load_tasks(data_dir)
    q_lower = user_message.lower()
    matched_items: list[str] = []
    omitted_count = 0

    for title, info in sorted(all_tasks.items()):
        cat = info.get("category", "general").lower()
        due = info.get("due_date", "").lower()
        if title in q_lower or cat in q_lower or (due and due in q_lower):
            matched_items.append(
                f"{title} (due: {info.get('due_date')}, {cat}, {info.get('priority')})"
            )
        else:
            omitted_count += 1

    if matched_items:
        sections.append(
            f"Relevant Task Slice ({len(matched_items)} matched, {omitted_count} omitted): "
            + ", ".join(matched_items)
        )
    else:
        sections.append(
            f"Task List Summary: {len(all_tasks)} total task(s) stored on disk "
            "(use get_tasks tool if full list is needed)."
        )

    final_context = "\n\n".join(sections)
    print(
        f"[context.py] Built turn context ({len(final_context)} chars, "
        f"memories={len(relevant_memories)}, matched_tasks={len(matched_items)}, "
        f"omitted_tasks={omitted_count})"
    )
    return final_context
