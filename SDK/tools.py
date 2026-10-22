"""MCP tool definitions for the Claude Agent SDK implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool  # replaces: tools.py

from shared.tools_impl import (
    add_task,
    check_public_holidays,
    get_tasks,
    remove_task,
)


def build_tasks_mcp_server(data_dir: Path | str | None = None) -> Any:
    """Create the SDK MCP server exposing the 4 shared task management tools."""

    @tool(  # replaces: tools.py
        "add_task",
        "Add or update a task in the user's task list.",
        {"title": str, "due_date": str, "category": str, "priority": str},
    )
    async def mcp_add_task(args: dict[str, Any]) -> dict[str, Any]:
        try:
            res = add_task(
                title=str(args.get("title", "")),
                due_date=str(args.get("due_date", "unspecified")),
                category=str(args.get("category", "general")),
                priority=str(args.get("priority", "medium")),
                data_dir=data_dir,
            )
            return {"content": [{"type": "text", "text": res}]}  # replaces: tools.py
        except Exception as exc:
            return {"content": [{"type": "text", "text": f"Tool error: {exc}"}], "is_error": True}  # replaces: tools.py

    @tool(  # replaces: tools.py
        "get_tasks",
        "Get scheduled tasks from the task list, optionally filtered by category or query.",
        {"category": str, "query": str},
    )
    async def mcp_get_tasks(args: dict[str, Any]) -> dict[str, Any]:
        try:
            res = get_tasks(
                category=args.get("category"),
                query=args.get("query"),
                data_dir=data_dir,
            )
            return {"content": [{"type": "text", "text": res}]}  # replaces: tools.py
        except Exception as exc:
            return {"content": [{"type": "text", "text": f"Tool error: {exc}"}], "is_error": True}  # replaces: tools.py

    @tool(  # replaces: tools.py
        "remove_task",
        "Remove or complete a task from the user's task list.",
        {"title": str},
    )
    async def mcp_remove_task(args: dict[str, Any]) -> dict[str, Any]:
        try:
            res = remove_task(
                title=str(args.get("title", "")),
                data_dir=data_dir,
            )
            return {"content": [{"type": "text", "text": res}]}  # replaces: tools.py
        except Exception as exc:
            return {"content": [{"type": "text", "text": f"Tool error: {exc}"}], "is_error": True}  # replaces: tools.py

    @tool(  # replaces: tools.py
        "check_public_holidays",
        "Check official public holidays externally via Nager.Date API.",
        {"country_code": str, "year": int, "max_results": int},
    )
    async def mcp_check_public_holidays(args: dict[str, Any]) -> dict[str, Any]:
        try:
            res = check_public_holidays(
                country_code=str(args.get("country_code", "US")),
                year=int(args.get("year", 2026)),
                max_results=int(args.get("max_results", 3)),
                data_dir=data_dir,
            )
            return {"content": [{"type": "text", "text": res}]}  # replaces: tools.py
        except Exception as exc:
            return {"content": [{"type": "text", "text": f"Tool error: {exc}"}], "is_error": True}  # replaces: tools.py

    return create_sdk_mcp_server(  # replaces: tools.py
        name="tasks",
        version="1.0.0",
        tools=[
            mcp_add_task,
            mcp_get_tasks,
            mcp_remove_task,
            mcp_check_public_holidays,
        ],
    )


ALLOWED_TASK_TOOLS: list[str] = [  # replaces: tools.py
    "mcp__tasks__add_task",
    "mcp__tasks__get_tasks",
    "mcp__tasks__remove_task",
    "mcp__tasks__check_public_holidays",
    "Read",
    "Write",
    "Edit",
]
