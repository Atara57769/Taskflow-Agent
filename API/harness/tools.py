"""Tool JSON schemas, tool dispatcher, and is_error handling for the API harness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.tools_impl import (
    add_task,
    check_public_holidays,
    get_tasks,
    remove_task,
)

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {
        "name": "add_task",
        "description": "Add or update a task in the user's task list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Task title (e.g. 'prepare quarterly report', 'buy groceries').",
                },
                "due_date": {
                    "type": "string",
                    "description": "Due day or date (e.g. 'Monday', 'Thursday', '2026-11-15').",
                },
                "category": {
                    "type": "string",
                    "description": "Task category such as 'work', 'personal', 'health', 'study'.",
                },
                "priority": {
                    "type": "string",
                    "description": "Priority level: 'low', 'medium', or 'high'.",
                },
            },
            "required": ["title", "due_date"],
        },
    },
    {
        "name": "get_tasks",
        "description": "Get scheduled tasks from the task list, optionally filtered by category or query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional category filter (e.g. 'work', 'personal', 'health').",
                },
                "query": {
                    "type": "string",
                    "description": "Optional substring search filter on task title.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "remove_task",
        "description": "Remove or complete a task from the user's task list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Exact title of the task to remove.",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "check_public_holidays",
        "description": "Check official public holidays externally via Nager.Date API (returns compact summary).",
        "input_schema": {
            "type": "object",
            "properties": {
                "country_code": {
                    "type": "string",
                    "description": "ISO country code (e.g. 'US', 'GB', 'IL').",
                },
                "year": {
                    "type": "integer",
                    "description": "Target calendar year (default 2026).",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of compact holiday entries to return (default 3).",
                },
            },
            "required": ["country_code"],
        },
    },
]


def get_tool_schemas() -> list[dict[str, Any]]:
    """Return a copy of the JSON tool schemas for the Messages API."""
    print(f"[tools.py] Providing {len(TOOLS_SCHEMA)} tool JSON schemas")
    return [dict(schema) for schema in TOOLS_SCHEMA]


def dispatch_tool_call(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_use_id: str,
    data_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Execute a tool call and return a Messages API tool_result content block."""
    print(f"[tools.py] Dispatching tool '{tool_name}' with input={tool_input}")
    try:
        if tool_name == "add_task":
            output = add_task(
                title=str(tool_input.get("title", "")),
                due_date=str(tool_input.get("due_date", "unspecified")),
                category=str(tool_input.get("category", "general")),
                priority=str(tool_input.get("priority", "medium")),
                data_dir=data_dir,
            )
        elif tool_name == "get_tasks":
            output = get_tasks(
                category=tool_input.get("category"),
                query=tool_input.get("query"),
                data_dir=data_dir,
            )
        elif tool_name == "remove_task":
            output = remove_task(
                title=str(tool_input.get("title", "")),
                data_dir=data_dir,
            )
        elif tool_name == "check_public_holidays":
            output = check_public_holidays(
                country_code=str(tool_input.get("country_code", "US")),
                year=int(tool_input.get("year", 2026)),
                max_results=int(tool_input.get("max_results", 3)),
                data_dir=data_dir,
            )
        else:
            raise ValueError(f"Unknown tool '{tool_name}'.")

        print(f"[tools.py] Tool '{tool_name}' succeeded ({len(output)} chars)")
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": output,
        }
    except Exception as exc:
        print(f"[tools.py] Tool '{tool_name}' raised error -> returning is_error=True: {exc}")
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": f"Tool error: {exc}",
            "is_error": True,
        }
