"""Run a fixed scenario N times and emit aggregated CSV data.

For an operator who wants to study how the LLM's decisions and
predicted_roles vary across runs of the same scenario.

Usage:

    from src.batch_runner import run_batch
    run_batch(
        n_runs=10,
        output_dir="/tmp/sh_FL",
        rounds=1,
        forced_roles=[Role.LIBERAL, Role.HITLER, Role.FASCIST,
                      Role.LIBERAL, Role.LIBERAL],
        stack_deck=[Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL] +
                   [Policy.LIBERAL] * 5 + [Policy.FASCIST] * 9,
        agents_mode="llm",
        model="gpt-5",
    )

See `specs/batch_scenario_runner.md` and the example
`scenarios/batch_chancellor_FL.py`.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from src.runner import start_game


# --- public API -------------------------------------------------------------


def run_batch(
    n_runs: int,
    output_dir: str | Path,
    *,
    base_seed: int = 1,
    **start_game_kwargs: Any,
) -> Path:
    """Run start_game `n_runs` times with the same scenario kwargs.

    Each run gets seed = base_seed + i (i=1..n_runs). Saves per-run JSON logs
    to `<output_dir>/run_NNN.json` and three aggregated CSVs:
    `predicted_roles.csv`, `decisions.csv`, `summary.csv`.

    Returns the output directory path.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Override any caller-supplied seed/save_log; the batch owns those.
    start_game_kwargs.pop("seed", None)
    start_game_kwargs.pop("save_log", None)

    log_paths: list[Path] = []
    for i in range(1, n_runs + 1):
        log_path = output_dir / f"run_{i:03d}.json"
        start_game(
            seed=base_seed + i,
            save_log=str(log_path),
            **start_game_kwargs,
        )
        log_paths.append(log_path)

    _write_aggregate_csvs(log_paths, output_dir)
    return output_dir


# --- aggregation ------------------------------------------------------------


def _write_aggregate_csvs(log_paths: list[Path], output_dir: Path) -> None:
    pred_rows: list[dict] = []
    decision_rows: list[dict] = []
    statement_rows: list[dict] = []
    summary_rows: list[dict] = []

    for run_id, log_path in enumerate(log_paths, start=1):
        log = json.loads(log_path.read_text())
        op = log.get("operator_view", {})

        for r in log.get("rounds", []):
            ps = r.get("policy_session") or {}
            common = {
                "run_id": run_id,
                "round_num": r["round_num"],
                "election_passed": r["election_passed"],
                "enacted_policy": ps.get("enacted"),
                "chaos": r.get("chaos_enacted") is not None,
                "executed_player_id": r.get("executed_player_id") or "",
            }
            for viewer_id, predicted in r.get("predicted_roles_after", {}).items():
                for target_id, score in predicted.items():
                    pred_rows.append(
                        {
                            **common,
                            "viewer_id": viewer_id,
                            "viewer_role": op.get(viewer_id, ""),
                            "target_id": target_id,
                            "target_role": op.get(target_id, ""),
                            "predicted_role": score,
                        }
                    )

            update_reasons = r.get("predicted_role_update_reasonings", {}) or {}
            for s in r.get("statements", []) or []:
                pid = s.get("player_id")
                statement_rows.append(
                    {
                        "run_id": run_id,
                        "round_num": r["round_num"],
                        "player_id": pid,
                        "player_role": op.get(str(pid), ""),
                        "text": s.get("text", ""),
                        "reasoning": s.get("reasoning", ""),
                        "predicted_role_update_reasoning": update_reasons.get(
                            str(pid), ""
                        ),
                    }
                )

            for player_id, decisions in r.get("decisions", {}).items():
                for dtype, dval in decisions.items():
                    if not isinstance(dval, dict):
                        continue
                    value = (
                        dval.get("value")
                        if "value" in dval
                        else dval.get("choice")
                        if "choice" in dval
                        else dval.get("policy")
                        if "policy" in dval
                        else dval.get("execute_id")
                    )
                    decision_rows.append(
                        {
                            "run_id": run_id,
                            "round_num": r["round_num"],
                            "player_id": player_id,
                            "player_role": op.get(player_id, ""),
                            "decision_type": dtype,
                            "value": "" if value is None else str(value),
                            "reasoning": dval.get("reasoning", ""),
                        }
                    )

        rounds = log.get("rounds", [])
        if rounds:
            last_tally = rounds[-1].get("tally_after", {})
            final_l = last_tally.get("liberal", 0)
            final_f = last_tally.get("fascist", 0)
        else:
            final_l = 0
            final_f = 0
        summary_rows.append(
            {
                "run_id": run_id,
                "winner": log.get("winner") or "",
                "winning_reason": log.get("winning_reason") or "",
                "rounds_played": len(rounds),
                "final_l_tally": final_l,
                "final_f_tally": final_f,
            }
        )

    _write_csv(
        output_dir / "predicted_roles.csv",
        pred_rows,
        [
            "run_id",
            "round_num",
            "viewer_id",
            "viewer_role",
            "target_id",
            "target_role",
            "predicted_role",
            "election_passed",
            "enacted_policy",
            "chaos",
            "executed_player_id",
        ],
    )
    _write_csv(
        output_dir / "decisions.csv",
        decision_rows,
        [
            "run_id",
            "round_num",
            "player_id",
            "player_role",
            "decision_type",
            "value",
            "reasoning",
        ],
    )
    _write_csv(
        output_dir / "statements.csv",
        statement_rows,
        [
            "run_id",
            "round_num",
            "player_id",
            "player_role",
            "text",
            "reasoning",
            "predicted_role_update_reasoning",
        ],
    )
    _write_csv(
        output_dir / "summary.csv",
        summary_rows,
        [
            "run_id",
            "winner",
            "winning_reason",
            "rounds_played",
            "final_l_tally",
            "final_f_tally",
        ],
    )


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
