"""Shared configuration, constants, pricing, and system prompt for SmartTasks."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "claude-opus-4-6")
DEFAULT_EFFORT = os.environ.get("AGENT_EFFORT", "medium")
MAX_TOKENS = 1024

# Pricing per 1,000,000 tokens in USD
MODEL_PRICING_USD_PER_M = {
    "claude-opus-4-6": {
        "input": 15.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
        "output": 75.00,
    },
    "claude-opus-5-5": {
        "input": 15.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
        "output": 75.00,
    },
    "claude-sonnet-4-5": {
        "input": 3.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
        "output": 15.00,
    },
}


def calculate_turn_cost_usd(
    input_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
    output_tokens: int,
    model: str = DEFAULT_MODEL,
) -> float:
    """Compute USD cost for given token counts using official pricing per 1M tokens."""
    rates = MODEL_PRICING_USD_PER_M.get(
        model,
        MODEL_PRICING_USD_PER_M[DEFAULT_MODEL],
    )
    cost = (
        (input_tokens * rates["input"])
        + (cache_read_tokens * rates["cache_read"])
        + (cache_write_tokens * rates["cache_write"])
        + (output_tokens * rates["output"])
    ) / 1_000_000.0
    return round(cost, 6)


SYSTEM_PROMPT = (
    "You are SmartTasks, a personal task and schedule management assistant.\n"
    "Responsibilities:\n"
    "1. Manage the user's task list using add_task, get_tasks, and remove_task.\n"
    "2. Check official public holidays using check_public_holidays (Nager.Date API) to help plan deadlines.\n"
    "3. Strictly enforce all saved scheduling rules and work-life restrictions stored in memory / CLAUDE.md.\n"
    "4. If a user asks to schedule or add a task that violates a saved scheduling restriction (such as scheduling on a blocked day or weekend work), "
    "you MUST refuse to add the forbidden task, warn the user about the conflict, and suggest an allowed day instead.\n"
    "5. Keep responses concise, accurate, and helpful."
)
