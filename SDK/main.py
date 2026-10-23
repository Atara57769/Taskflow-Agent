"""CLI entrypoint for running the Claude Agent SDK scenario or interactive chat."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from SDK.agent import SDKAgent  # noqa: E402
from shared.config import DEFAULT_DATA_DIR, DEFAULT_EFFORT, DEFAULT_MODEL  # noqa: E402
from shared.evaluator import build_benchmark_report, evaluate_scenario_checks  # noqa: E402
from shared.storage import reset_state  # noqa: E402


def run_scenario(
    scenario_path: Path,
    out_path: Path,
    data_dir: Path = DEFAULT_DATA_DIR,
    client_factory: Any | None = None,
) -> dict[str, Any]:
    """Execute the multi-session scenario on the Claude Agent SDK from a clean state (wiping memories)."""
    # Ensure ANTHROPIC_API_KEY is unset so SDK uses personal Claude Code login
    os.environ.pop("ANTHROPIC_API_KEY", None)

    # Wipes all memories, tasks, and history files clean before running the scenario
    reset_state(data_dir)
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    model = scenario.get("model", DEFAULT_MODEL)
    effort = scenario.get("effort", DEFAULT_EFFORT)

    turn_records: list[dict[str, Any]] = []
    for session_block in scenario.get("sessions", []):
        session_id = session_block["session_id"]
        print(f"\n=== [SDK] Starting fresh agent instance for {session_id} ===")
        # Each session runs on a brand new SDKAgent instance resuming state from disk
        agent = SDKAgent(  # replaces: history.py
            session_id=session_id,
            model=model,
            effort=effort,
            data_dir=data_dir,
            client_factory=client_factory,
        )
        for turn in session_block.get("turns", []):
            turn_id = turn["turn_id"]
            prompt = turn["prompt"]
            print(f"\n--- [SDK] Turn {turn_id} ({session_id}) ---")
            response_text, metrics = agent.run_turn(prompt)  # replaces: loop.py
            turn_records.append(
                {
                    "turn_id": turn_id,
                    "session_id": session_id,
                    "prompt": prompt,
                    "response": response_text,
                    **metrics,
                }
            )

    checks = evaluate_scenario_checks(turn_records=turn_records, data_dir=data_dir)
    report = build_benchmark_report(
        harness_type="SDK",
        model=model,
        effort=effort,
        turn_records=turn_records,
        checks=checks,
        project_root=PROJECT_ROOT,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"\n[SDK] Saved results to {out_path} | "
        f"Checks passed: {report['summary']['checks_passed']}/{report['summary']['checks_total']} | "
        f"Total cost: ${report['summary']['total_cost_usd']:.6f}"
    )
    return report


def run_interactive(
    session_id: str | None = None,
    reset_on_start: bool = False,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> None:
    """Run an interactive chat loop with SDK agent, starting a new session each run by default."""
    os.environ.pop("ANTHROPIC_API_KEY", None)
    if reset_on_start:
        reset_state(data_dir)
        print("[SDK] All memories, tasks, and history have been wiped clean.")

    current_session = session_id or f"session_{int(time.time())}"
    agent = SDKAgent(session_id=current_session, data_dir=data_dir)

    print(f"=== SmartTasks [SDK] Interactive Mode ===")
    print(f"Active Session: {current_session}")
    print("Commands: 'exit'/'quit' to exit, 'new' for new session, 'clear' to wipe memories.\n")

    while True:
        try:
            user_input = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting interactive chat.")
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in {"exit", "quit"}:
            print("Exiting interactive chat.")
            break

        if cmd == "new":
            current_session = f"session_{int(time.time())}"
            agent = SDKAgent(session_id=current_session, data_dir=data_dir)
            print(f"\n--- Switched to brand new session: {current_session} ---\n")
            continue

        if cmd in {"clear", "reset"}:
            reset_state(data_dir)
            current_session = f"session_{int(time.time())}"
            agent = SDKAgent(session_id=current_session, data_dir=data_dir)
            print(f"\n--- Memories wiped clean. Started new session: {current_session} ---\n")
            continue

        reply, metrics = agent.run_turn(user_input)  # replaces: loop.py
        print(f"\nSmartTasks > {reply}")
        print(
            f"  [metrics: calls={metrics['model_calls']}, tools={metrics['tools_used']}, "
            f"cost=${metrics['cost_usd']:.6f}]\n"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SmartTasks SDK Agent")
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Run in interactive chat mode (starts a new session each run)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe all memories and tasks clean before starting",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Optional session ID for interactive mode (defaults to new session each run)",
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        default=PROJECT_ROOT / "scenario.json",
        help="Path to scenario.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "results" / "sdk.json",
        help="Path to output JSON report",
    )
    args = parser.parse_args()

    if args.interactive:
        run_interactive(
            session_id=args.session,
            reset_on_start=args.reset,
        )
    else:
        run_scenario(scenario_path=args.scenario, out_path=args.out)


if __name__ == "__main__":
    main()
