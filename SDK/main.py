"""CLI entrypoint for running the Claude Agent SDK scenario benchmark."""

from __future__ import annotations

import argparse
import json
import os
import sys
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
    """Execute the multi-session scenario on the Claude Agent SDK from a clean state."""
    # Ensure ANTHROPIC_API_KEY is unset so SDK uses personal Claude Code login
    os.environ.pop("ANTHROPIC_API_KEY", None)

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SmartTasks SDK Agent Scenario")
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
    run_scenario(scenario_path=args.scenario, out_path=args.out)


if __name__ == "__main__":
    main()
