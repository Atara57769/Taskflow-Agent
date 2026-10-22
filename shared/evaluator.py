"""Scenario assertion evaluator and harness Lines of Code (LOC) analyzer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shared.config import PROJECT_ROOT
from shared.storage import (
    get_claude_md_path,
    get_history_path,
    load_memories,
    load_tasks,
)

HARNESS_MODULES = [
    "loop.py",
    "tools.py",
    "history.py",
    "memory.py",
    "context.py",
    "compaction.py",
    "caching.py",
    "tokens.py",
]


def evaluate_scenario_checks(
    turn_records: list[dict[str, Any]],
    data_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Run the 7 pass/fail checks (primarily against saved disk state)."""
    tasks = load_tasks(data_dir)
    memories = load_memories(data_dir)
    claude_md = get_claude_md_path(data_dir)
    claude_md_text = claude_md.read_text(encoding="utf-8").lower() if claude_md.exists() else ""
    memory_blob = (" ".join(m.get("rule", "") for m in memories) + " " + claude_md_text).lower()

    history_path = get_history_path(data_dir)
    sessions_in_history: set[str] = set()
    if history_path.exists():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("session_id"):
                    sessions_in_history.add(rec["session_id"])

    # 1. Disk state: expected tasks present in data/tasks.json
    expected_tasks = {
        "prepare quarterly report",
        "buy groceries",
        "code review",
        "dentist appointment",
        "server deployment",
    }
    missing_tasks = sorted(expected_tasks - set(tasks.keys()))
    check_1_passed = len(missing_tasks) == 0

    # 2. Disk state: removed task ('draft team slides') is absent
    check_2_passed = "draft team slides" not in tasks

    # 3. Disk state: persistent scheduling memory contains Friday and weekend rules
    check_3_passed = ("friday" in memory_blob) and (
        "weekend" in memory_blob or "saturday" in memory_blob
    )

    # 4. Disk state: contradictory tasks ('client budget meeting', 'weekend server migration') blocked
    forbidden_present = [
        item
        for item in ("client budget meeting", "weekend server migration")
        if item in tasks
    ] + [
        title
        for title, info in tasks.items()
        if "friday" in info.get("due_date", "").lower()
        or (
            info.get("category", "").lower() == "work"
            and any(d in info.get("due_date", "").lower() for d in ("saturday", "sunday", "weekend"))
        )
    ]
    check_4_passed = len(forbidden_present) == 0

    # 5. Disk state: multi-session history persisted for session_1 and session_2
    check_5_passed = {"session_1", "session_2"}.issubset(sessions_in_history)

    # 6. Execution state: external tool (check_public_holidays) was called
    all_tools_used = [
        tool_name
        for turn in turn_records
        for tool_name in turn.get("tools_used", [])
    ]
    check_6_passed = any("check_public_holidays" in t for t in all_tools_used)

    # 7. Session 2 memory recall (Turn 5) & contradiction refusal (Turn 6)
    turn_5_resp = next(
        (t.get("response", "").lower() for t in turn_records if t.get("turn_id") == 5),
        "",
    )
    turn_6_resp = next(
        (t.get("response", "").lower() for t in turn_records if t.get("turn_id") == 6),
        "",
    )
    recalled_in_t5 = "friday" in turn_5_resp and (
        "weekend" in turn_5_resp or "saturday" in turn_5_resp
    )
    refused_in_t6 = (
        any(
            w in turn_6_resp
            for w in ("cannot", "can't", "conflict", "friday", "weekend", "refuse", "blocked")
        )
        and "friday" in turn_6_resp
    )
    check_7_passed = recalled_in_t5 and refused_in_t6 and check_4_passed

    return [
        {
            "id": "state_tasks_expected_items_present",
            "type": "disk_state",
            "passed": check_1_passed,
            "details": (
                f"Present tasks: {sorted(tasks.keys())}"
                if check_1_passed
                else f"Missing expected tasks: {missing_tasks}"
            ),
        },
        {
            "id": "state_removed_task_absent",
            "type": "disk_state",
            "passed": check_2_passed,
            "details": "'draft team slides' is absent from data/tasks.json"
            if check_2_passed
            else "'draft team slides' is still present in data/tasks.json",
        },
        {
            "id": "state_memory_persisted_on_disk",
            "type": "disk_state",
            "passed": check_3_passed,
            "details": f"Saved memory rules count={len(memories)}; CLAUDE.md exists={claude_md.exists()}",
        },
        {
            "id": "state_contradiction_tasks_blocked",
            "type": "disk_state",
            "passed": check_4_passed,
            "details": "Forbidden Friday/weekend tasks were blocked from disk state"
            if check_4_passed
            else f"Forbidden tasks found in disk state: {forbidden_present}",
        },
        {
            "id": "state_multi_session_history_persisted",
            "type": "disk_state",
            "passed": check_5_passed,
            "details": f"Sessions found in history.jsonl: {sorted(sessions_in_history)}",
        },
        {
            "id": "execution_external_tool_called",
            "type": "execution_state",
            "passed": check_6_passed,
            "details": f"Tools executed across run: {all_tools_used}",
        },
        {
            "id": "behavior_session2_recall_and_contradiction_refusal",
            "type": "response_and_state",
            "passed": check_7_passed,
            "details": f"Turn 5 recalled memory={recalled_in_t5}, Turn 6 refused conflict={refused_in_t6}",
        },
    ]


def count_code_lines(file_path: Path) -> int:
    """Count non-empty, non-comment lines of code in a Python file."""
    if not file_path.exists():
        return 0
    count = 0
    for line in file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def compute_harness_loc_breakdown(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """Compute LOC for each API harness module and corresponding SDK replacements."""
    api_harness_dir = project_root / "API" / "harness"
    api_by_module: dict[str, int] = {}
    for mod in HARNESS_MODULES:
        api_by_module[mod] = count_code_lines(api_harness_dir / mod)

    api_files = {
        "API/main.py": count_code_lines(project_root / "API" / "main.py"),
        "API/agent.py": count_code_lines(project_root / "API" / "agent.py"),
        **{f"API/harness/{k}": v for k, v in api_by_module.items()},
    }

    sdk_files = {
        "SDK/main.py": count_code_lines(project_root / "SDK" / "main.py"),
        "SDK/agent.py": count_code_lines(project_root / "SDK" / "agent.py"),
        "SDK/tools.py": count_code_lines(project_root / "SDK" / "tools.py"),
    }

    sdk_replaces_counts: dict[str, int] = {mod: 0 for mod in HARNESS_MODULES}
    for sdk_rel in ("SDK/main.py", "SDK/agent.py", "SDK/tools.py"):
        p = project_root / sdk_rel
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            for mod in HARNESS_MODULES:
                if f"# replaces: {mod}" in line:
                    sdk_replaces_counts[mod] += 1

    return {
        "api_harness_by_module": api_by_module,
        "api_harness_total_loc": sum(api_by_module.values()),
        "api_all_files_loc": api_files,
        "api_total_loc": sum(api_files.values()),
        "sdk_replaces_by_module": sdk_replaces_counts,
        "sdk_replaces_total_lines": sum(sdk_replaces_counts.values()),
        "sdk_all_files_loc": sdk_files,
        "sdk_total_loc": sum(sdk_files.values()),
    }


def build_benchmark_report(
    harness_type: str,
    model: str,
    effort: str,
    turn_records: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Assemble the complete JSON results report for API or SDK."""
    total_in = sum(int(t["input_tokens"]) for t in turn_records)
    total_cr = sum(int(t["cache_read_tokens"]) for t in turn_records)
    total_cw = sum(int(t["cache_write_tokens"]) for t in turn_records)
    total_out = sum(int(t["output_tokens"]) for t in turn_records)
    total_calls = sum(int(t["model_calls"]) for t in turn_records)
    total_cost = round(sum(float(t["cost_usd"]) for t in turn_records), 6)
    total_time = round(sum(float(t["duration_seconds"]) for t in turn_records), 4)

    total_prompt_tokens = total_in + total_cr + total_cw
    cache_hit_pct = (
        round((total_cr / total_prompt_tokens) * 100.0, 2)
        if total_prompt_tokens > 0
        else 0.0
    )

    passed_count = sum(1 for c in checks if c["passed"])
    loc_data = compute_harness_loc_breakdown(project_root)

    return {
        "harness": harness_type,
        "model": model,
        "effort": effort,
        "summary": {
            "total_turns": len(turn_records),
            "input_tokens": total_in,
            "cache_read_tokens": total_cr,
            "cache_write_tokens": total_cw,
            "output_tokens": total_out,
            "total_tokens": total_prompt_tokens + total_out,
            "cache_hit_rate_pct": cache_hit_pct,
            "total_model_calls": total_calls,
            "total_cost_usd": total_cost,
            "total_duration_seconds": total_time,
            "checks_passed": passed_count,
            "checks_total": len(checks),
        },
        "turns": turn_records,
        "checks": checks,
        "loc": loc_data,
    }
