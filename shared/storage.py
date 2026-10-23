"""Persistent state storage helpers for tasks and scheduling memory."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from shared.config import DEFAULT_DATA_DIR, PROJECT_ROOT


def resolve_data_dir(data_dir: Path | str | None = None) -> Path:
    """Resolve and create the target data directory."""
    target = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def get_tasks_path(data_dir: Path | str | None = None) -> Path:
    return resolve_data_dir(data_dir) / "tasks.json"


def get_memory_path(data_dir: Path | str | None = None) -> Path:
    return resolve_data_dir(data_dir) / "memory.json"


def get_history_path(data_dir: Path | str | None = None) -> Path:
    return resolve_data_dir(data_dir) / "history.jsonl"


def get_claude_md_path(data_dir: Path | str | None = None) -> Path:
    resolved = resolve_data_dir(data_dir)
    if resolved == DEFAULT_DATA_DIR:
        return PROJECT_ROOT / "CLAUDE.md"
    return resolved / "CLAUDE.md"


def reset_state(data_dir: Path | str | None = None) -> None:
    """Reset all persisted state files so each run begins from a clean state."""
    resolved = resolve_data_dir(data_dir)
    if resolved.exists():
        for file_path in resolved.iterdir():
            if file_path.is_file():
                try:
                    file_path.unlink()
                except OSError:
                    pass

    root_claude_md = PROJECT_ROOT / "CLAUDE.md"
    if root_claude_md.exists():
        try:
            root_claude_md.unlink()
        except OSError:
            pass


def load_tasks(data_dir: Path | str | None = None) -> dict[str, dict[str, str]]:
    """Load the tasks dictionary keyed by normalized task title."""
    path = get_tasks_path(data_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def save_tasks(
    tasks: dict[str, dict[str, str]],
    data_dir: Path | str | None = None,
) -> None:
    """Persist the tasks dictionary to disk."""
    path = get_tasks_path(data_dir)
    path.write_text(
        json.dumps(tasks, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def load_memories(data_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """Load saved memory entries from memory.json and/or CLAUDE.md."""
    mem_path = get_memory_path(data_dir)
    memories: list[dict[str, Any]] = []
    if mem_path.exists():
        try:
            loaded = json.loads(mem_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                memories = loaded
        except (json.JSONDecodeError, OSError):
            memories = []

    claude_md = get_claude_md_path(data_dir)
    if claude_md.exists():
        text = claude_md.read_text(encoding="utf-8")
        existing_rules = {m.get("rule", "").lower() for m in memories}
        for line in text.splitlines():
            cleaned = line.strip().lstrip("-* ").strip()
            if cleaned and not cleaned.startswith("#") and cleaned.lower() not in existing_rules:
                memories.append(
                    {
                        "category": "scheduling_restriction",
                        "rule": cleaned,
                        "keywords": _extract_keywords(cleaned),
                    }
                )
    return memories


def save_memories(
    memories: list[dict[str, Any]],
    data_dir: Path | str | None = None,
) -> None:
    """Save memory entries to both memory.json and CLAUDE.md."""
    mem_path = get_memory_path(data_dir)
    mem_path.write_text(json.dumps(memories, indent=2), encoding="utf-8")

    lines = [
        "# User Task Management Memory & Scheduling Rules",
        "",
        "## Active Scheduling Restrictions",
    ]
    for item in memories:
        rule = item.get("rule", "").strip()
        if rule:
            lines.append(f"- {rule}")
    content = "\n".join(lines) + "\n"

    claude_md = get_claude_md_path(data_dir)
    claude_md.write_text(content, encoding="utf-8")
    resolved = resolve_data_dir(data_dir)
    if resolved == DEFAULT_DATA_DIR:
        (resolved / "CLAUDE.md").write_text(content, encoding="utf-8")


def check_schedule_conflict(
    title: str,
    due_date: str,
    category: str = "general",
    data_dir: Path | str | None = None,
) -> str | None:
    """Return a conflict explanation if the task violates saved scheduling memory."""
    norm_due = due_date.strip().lower()
    norm_cat = category.strip().lower()
    norm_title = title.strip().lower()
    memories = load_memories(data_dir)
    combined_rules = " ".join(m.get("rule", "").lower() for m in memories)

    if "friday" in combined_rules and "friday" in norm_due:
        return (
            f"Cannot schedule '{title}' on '{due_date}': conflicts with saved rule "
            "prohibiting tasks on Fridays."
        )

    weekend_days = ("saturday", "sunday", "weekend")
    if ("weekend" in combined_rules or "saturday" in combined_rules or "sunday" in combined_rules):
        if any(day in norm_due for day in weekend_days) and norm_cat == "work":
            return (
                f"Cannot schedule work task '{title}' on '{due_date}': conflicts with saved "
                "rule prohibiting work tasks on weekends (Saturday/Sunday)."
            )

    for mem in memories:
        for forbidden in mem.get("forbidden_days", []):
            if forbidden.lower() in norm_due or forbidden.lower() in norm_title:
                return (
                    f"Cannot schedule '{title}' on '{due_date}': conflicts with saved rule "
                    f"({mem.get('rule', forbidden)})."
                )
    return None


def _extract_keywords(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    stopwords = {
        "the", "and", "for", "that", "have", "has", "with", "not", "are", "you",
        "user", "please", "remember", "scheduling", "rule", "rules", "tasks",
    }
    return sorted({w for w in words if len(w) > 2 and w not in stopwords})
