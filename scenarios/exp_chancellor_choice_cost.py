"""Experiment 2 — Cost of an unforced Fascist enaction by the Chancellor.

Research question:
  When the Chancellor genuinely has a choice (F+L hand) and picks Fascist,
  how much trust does that cost them?

Design:
  Both variants: Liberal Pres P1, Liberal Chan P3, deck top FFL. P1
  discards a Fascist → passes [F, L] to P3. P3 receives the F+L hand.
  - Variant A (Chan picks L): P3 enacts the LIBERAL.
  - Variant B (Chan picks F): P3 enacts the FASCIST.

The President has private knowledge that the Chancellor had a Liberal
available — the central fact of the discussion in B.

Hypothesis:
  Chancellor's predicted_role falls noticeably more in B than A — most
  sharply from the Pres (who has private knowledge), but also from
  bystanders once the Pres surfaces the fact in discussion.

Headline metric:
  Mean predicted_role[P3] from P1 (Pres, has private knowledge) at end of
  round 1. Delta (B − A) is the answer. Bystander reads also reported.

Cost (~$1 at gpt-5, --runs 10):
    python3 -m scenarios.exp_chancellor_choice_cost --llm --runs 10 \\
        --output-dir /tmp/exp2
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.experiment_runner import Variant, run_experiment
from src.game import Role
from src.policies import Policy


# Same gov + same hand in both variants — only the Chancellor's enact decision differs.
ROLES = [Role.LIBERAL, Role.HITLER, Role.LIBERAL, Role.LIBERAL, Role.FASCIST]
STACK = (
    [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]  # Pres draws FFL
    + [Policy.LIBERAL] * 5
    + [Policy.FASCIST] * 9
)


def _script_with_enact(enact: Policy) -> dict[int, dict]:
    return {
        1: {"nominate": 3, "vote": True, "discard": Policy.FASCIST},
        2: {"vote": True},
        3: {"vote": True, "enact": enact},
        4: {"vote": True},
        5: {"vote": True},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/exp_chancellor_choice_cost"),
    )
    parser.add_argument("--base-seed", type=int, default=1)
    parser.add_argument(
        "--rounds", type=int, default=3,
        help="Total rounds per game. Round 1 is forced; later rounds are free LLM play.",
    )
    args = parser.parse_args()

    variants = [
        Variant(
            name="A_picks_L",
            scripted=_script_with_enact(Policy.LIBERAL),
            scenario_kwargs={"forced_roles": ROLES, "stack_deck": STACK},
            apply_until_round=1,
        ),
        Variant(
            name="B_picks_F",
            scripted=_script_with_enact(Policy.FASCIST),
            scenario_kwargs={"forced_roles": ROLES, "stack_deck": STACK},
            apply_until_round=1,
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
            rounds=args.rounds,
        ),
    )


if __name__ == "__main__":
    main()
