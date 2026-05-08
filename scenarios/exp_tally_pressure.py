"""Experiment 3 — Tally pressure: same event, three board states.

Research question:
  Does the same Fascist enaction get interpreted differently depending on
  the current board state?

Design:
  Three variants. In each, the same forced event happens: Liberal Pres P1
  draws FFF (no choice), Liberal Chan P3 receives FF (forced) and enacts F.
  The only thing that differs is the starting tally.

  - Variant 0: start_tally L=0, F=0 (clean board).
  - Variant M: start_tally L=2, F=2 (mid-game pressure).
  - Variant H: start_tally L=0, F=3 (Hitler-Chancellor win threshold —
              one Fascist policy puts Hitler-as-Chan into win range).

Hypothesis:
  Same observable event causes increasingly sharp drops in bystander
  predicted_role of the gov as the F-tally rises. At F=3 the LLM should
  treat the event as critical.

Headline metric:
  Bystander mean predicted_role[P1] and predicted_role[P3] per state.
  Three-point trajectory. Delta (H − 0) is the headline.

Cost (~$1.50 at gpt-5, --runs 10):
    python3 -m scenarios.exp_tally_pressure --llm --runs 10 \\
        --output-dir /tmp/exp3
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.experiment_runner import Variant, run_experiment
from src.game import Role
from src.policies import Policy


ROLES = [Role.LIBERAL, Role.HITLER, Role.LIBERAL, Role.LIBERAL, Role.FASCIST]
STACK = (
    [Policy.FASCIST] * 3                     # Pres draws FFF (forced)
    + [Policy.LIBERAL] * 6
    + [Policy.FASCIST] * 8
)
SCRIPT = {
    1: {"nominate": 3, "vote": True, "discard": Policy.FASCIST},
    2: {"vote": True},
    3: {"vote": True, "enact": Policy.FASCIST},
    4: {"vote": True},
    5: {"vote": True},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("/tmp/exp_tally_pressure")
    )
    parser.add_argument("--base-seed", type=int, default=1)
    args = parser.parse_args()

    common_kwargs = {"forced_roles": ROLES, "stack_deck": STACK}
    variants = [
        Variant(
            name="0_clean",
            scripted=SCRIPT,
            scenario_kwargs={**common_kwargs, "start_tally": (0, 0)},
        ),
        Variant(
            name="M_midgame",
            scripted=SCRIPT,
            scenario_kwargs={**common_kwargs, "start_tally": (2, 2)},
        ),
        Variant(
            name="H_threshold",
            scripted=SCRIPT,
            scenario_kwargs={**common_kwargs, "start_tally": (0, 3)},
        ),
    ]

    run_experiment(
        variants=variants,
        n_runs=args.runs,
        output_dir=args.output_dir,
        base_seed=args.base_seed,
        shared_kwargs=dict(
            agents_mode="llm" if args.llm else "random",
            model="gpt-5",
            token_budget=200_000,
        ),
    )


if __name__ == "__main__":
    main()
