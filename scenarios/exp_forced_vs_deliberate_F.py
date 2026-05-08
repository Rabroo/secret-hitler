"""Experiment 1 — Forced vs Deliberate Fascist enaction.

Research question:
  Can the LLM tell deck-driven Fascist enactions apart from deliberately
  engineered ones, when the *observable* event is identical?

Design:
  Variant A (forced):     Liberal Pres P1 draws FFF (no choice). Liberal
                          Chan P3 receives FF (forced) and enacts F.
  Variant B (deliberate): Fascist Pres P1 draws FFL and deliberately
                          discards the LIBERAL. Liberal Chan P3 receives
                          FF and enacts F. Bystanders see exactly the same
                          event as A: "P1+P3 government enacted Fascist."

The two variants differ only in:
  - The actual role of P1 (Liberal in A, Fascist in B).
  - Whether the discard was forced (A) or deliberate (B).

Hypothesis:
  If discussion + private knowledge actually surface information, B should
  produce sharper drops in bystanders' predicted_role[P1] than A. If the
  predicted_role distributions overlap, the LLM cannot differentiate intent
  from variance.

Headline metric:
  Mean predicted_role[P1] from bystanders (P2, P4, P5) at end of round 1.
  Delta (B − A) is the answer.

Cost (~$1 at gpt-5, --runs 10):
    python3 -m scenarios.exp_forced_vs_deliberate_F --llm --runs 10 \\
        --output-dir /tmp/exp1
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.experiment_runner import Variant, run_experiment
from src.game import Role
from src.policies import Policy


# Variant A: forced. Liberal Pres P1, Liberal Chan P3.
ROLES_A = [Role.LIBERAL, Role.HITLER, Role.LIBERAL, Role.LIBERAL, Role.FASCIST]
STACK_A = (
    [Policy.FASCIST] * 3                   # Pres draws FFF (no Liberal to choose)
    + [Policy.LIBERAL] * 6
    + [Policy.FASCIST] * 8
)
# Pres can only discard a Fascist (no Liberal in hand). Chan only has FF.
SCRIPT_A = {
    1: {"nominate": 3, "vote": True, "discard": Policy.FASCIST},
    2: {"vote": True},
    3: {"vote": True, "enact": Policy.FASCIST},
    4: {"vote": True},
    5: {"vote": True},
}

# Variant B: deliberate. Fascist Pres P1, Liberal Chan P3.
ROLES_B = [Role.FASCIST, Role.HITLER, Role.LIBERAL, Role.LIBERAL, Role.LIBERAL]
STACK_B = (
    [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]   # FFL — Pres has the choice
    + [Policy.LIBERAL] * 5
    + [Policy.FASCIST] * 9
)
SCRIPT_B = {
    1: {"nominate": 3, "vote": True, "discard": Policy.LIBERAL},   # the damning move
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
        "--output-dir", type=Path, default=Path("/tmp/exp_forced_vs_deliberate")
    )
    parser.add_argument("--base-seed", type=int, default=1)
    parser.add_argument(
        "--rounds", type=int, default=3,
        help="Total rounds per game. Round 1 is forced; later rounds are free LLM play.",
    )
    args = parser.parse_args()

    variants = [
        Variant(
            name="A_forced",
            scripted=SCRIPT_A,
            scenario_kwargs={"forced_roles": ROLES_A, "stack_deck": STACK_A},
            apply_until_round=1,
        ),
        Variant(
            name="B_deliberate",
            scripted=SCRIPT_B,
            scenario_kwargs={"forced_roles": ROLES_B, "stack_deck": STACK_B},
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
