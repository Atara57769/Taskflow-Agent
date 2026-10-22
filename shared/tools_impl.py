"""Domain implementation of the four task management agent tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from shared.storage import (
    check_schedule_conflict,
    load_tasks,
    save_tasks,
)

NAGER_HOLIDAYS_BASE_URL = "https://date.nager.at/api/v3/PublicHolidays"


def add_task(
    title: str,
    due_date: str = "unspecified",
    category: str = "general",
    priority: str = "medium",
    data_dir: Path | str | None = None,
) -> str:
    """Add or update a task in the user's task list.

    Raises ValueError if the title is empty or violates a saved scheduling restriction.
    """
    cleaned_title = title.strip().lower()
    if not cleaned_title:
        raise ValueError("Task title cannot be empty.")

    cleaned_due = (due_date or "unspecified").strip()
    cleaned_category = (category or "general").strip().lower()
    cleaned_priority = (priority or "medium").strip().lower()

    conflict = check_schedule_conflict(
        title=cleaned_title,
        due_date=cleaned_due,
        category=cleaned_category,
        data_dir=data_dir,
    )
    if conflict:
        raise ValueError(conflict)

    tasks = load_tasks(data_dir)
    tasks[cleaned_title] = {
        "title": cleaned_title,
        "due_date": cleaned_due,
        "category": cleaned_category,
        "priority": cleaned_priority,
    }
    save_tasks(tasks, data_dir)
    return (
        f"ok: added '{cleaned_title}' (due={cleaned_due}, "
        f"cat={cleaned_category}, prio={cleaned_priority}); total={len(tasks)}"
    )


def get_tasks(
    category: str | None = None,
    query: str | None = None,
    data_dir: Path | str | None = None,
) -> str:
    """Retrieve scheduled tasks in a compact token-optimized format."""
    tasks = load_tasks(data_dir)
    if not tasks:
        return "tasks: empty (0 items)"

    items = list(tasks.values())
    if category:
        cat_lower = category.strip().lower()
        items = [t for t in items if t.get("category", "").lower() == cat_lower]
    if query:
        q_lower = query.strip().lower()
        items = [t for t in items if q_lower in t.get("title", "").lower()]

    if not items:
        filter_desc = category or query or "all"
        return f"tasks ({filter_desc}): 0 matching items"

    compact_parts = [
        f"{item['title']} (due: {item['due_date']}, {item['category']}, {item['priority']})"
        for item in sorted(items, key=lambda x: x["title"])
    ]
    return f"tasks ({len(compact_parts)} items): " + ", ".join(compact_parts)


def remove_task(
    title: str,
    data_dir: Path | str | None = None,
) -> str:
    """Remove or complete a task from the user's task list.

    Raises ValueError if the task is not found.
    """
    cleaned_title = title.strip().lower()
    if not cleaned_title:
        raise ValueError("Task title cannot be empty.")

    tasks = load_tasks(data_dir)
    if cleaned_title not in tasks:
        raise ValueError(f"Task '{cleaned_title}' not found in task list.")

    del tasks[cleaned_title]
    save_tasks(tasks, data_dir)
    return f"ok: removed '{cleaned_title}'; remaining={len(tasks)}"


def check_public_holidays(
    country_code: str = "US",
    year: int = 2026,
    max_results: int = 3,
    data_dir: Path | str | None = None,
) -> str:
    """Fetch public holidays via Nager.Date API and return a compact token-optimized summary."""
    cleaned_country = country_code.strip().upper()
    if not cleaned_country:
        raise ValueError("Country code cannot be empty.")

    limit = max(1, min(int(max_results or 3), 5))
    raw_holidays = _fetch_nager_holidays(cleaned_country, int(year or 2026))
    if not raw_holidays:
        return f"holidays({cleaned_country}, {year}): 0 found"

    compact_lines: list[str] = []
    for item in raw_holidays[:limit]:
        date_str = item.get("date", "unknown-date")
        name_str = item.get("name", "Holiday")
        local_name = item.get("localName", name_str)
        compact_lines.append(f"- {date_str}: {name_str} ({local_name})")

    return (
        f"holidays({cleaned_country}, {year}, top {len(compact_lines)}):\n"
        + "\n".join(compact_lines)
    )


def _fetch_nager_holidays(country_code: str, year: int) -> list[dict[str, Any]]:
    """Fetch official public holidays from live Nager.Date API."""
    with httpx.Client(timeout=10.0) as http_client:
        resp = http_client.get(f"{NAGER_HOLIDAYS_BASE_URL}/{year}/{country_code}")
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, list):
            return payload
        return []
