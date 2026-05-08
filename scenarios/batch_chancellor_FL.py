"""Run the F+L→Chancellor scenario N times and emit CSV data.

Setup (identical across runs):
- 5p forced layout: P1 Liberal, P2 Hitler, P3 Fascist, P4 Liberal, P5 Liberal.
- Top 3 cards stacked F,F,L. President P1 (Liberal) discards F → passes [F, L]
  to the Chancellor (whomever the LLM nominates).
- 1 round per run; full discussion + LLM-driven predicted_role updates.

What you get in `--output-dir`:
- `run_001.json` … `run_010.json` — per-run game logs.
- `predicted_roles.csv` — long-form (run_id, round_num, viewer, target, score).
- `decisions.csv` — long-form per-player decisions.
- `summary.csv` — per-run final state.

Cost: ~$0.50–1.00 total at gpt-5 for 10 runs.

Examples:
    # Free dry run (random agents)
    python3 -m scenarios.batch_chancellor_FL --runs 3 --output-dir /tmp/sh_FL_dry

    # Real LLM, 10 runs at gpt-5
    python3 -m scenarios.batch_chancellor_FL --runs 10 --output-dir /tmp/sh_FL --llm
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.batch_runner import run_batch
from src.game import Role
from src.policies import Policy


# 17 cards: top 3 are FFL (President draws this), then padding so reshuffle
# rules behave normally.
STACK = (
    [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]
    + [Policy.LIBERAL] * 5
    + [Policy.FASCIST] * 9
)

ROLES = [Role.LIBERAL, Role.HITLER, Role.FASCIST, Role.LIBERAL, Role.LIBERAL]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/sh_batch_FL"),
        help="Directory for per-run JSONs and aggregated CSVs",
    )
    parser.add_argument("--llm", action="store_true", help="Use gpt-5 (costs cents)")
    parser.add_argument(
        "--rounds", type=int, default=1, help="Rounds per run (default 1 to keep cost low)"
    )
    parser.add_argument("--token-budget", type=int, default=200_000)
    parser.add_argument("--base-seed", type=int, default=1)
    args = parser.parse_args()

    out = run_batch(
        n_runs=args.runs,
        output_dir=args.output_dir,
        base_seed=args.base_seed,
        rounds=args.rounds,
        agents_mode="llm" if args.llm else "random",
        model="gpt-5",
        token_budget=args.token_budget,
        forced_roles=ROLES,
        stack_deck=STACK,
        dashboard=False,
    )
    print(f"\nBatch complete: {args.runs} run(s) in {out}/")
    print("  - run_NNN.json — per-run game logs")
    print("  - predicted_roles.csv — every per-round predicted_role snapshot")
    print("  - decisions.csv — every per-player decision with reasoning")
    print("  - summary.csv — per-run final state + winner")


if __name__ == "__main__":
    main()
