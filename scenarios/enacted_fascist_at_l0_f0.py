"""Round 1 enacts a Fascist policy. How do Liberals' predicted_roles shift?

Setup:
- Roles forced: P1 Liberal pres, P3 Fascist who'll be picked Chancellor under
  random agents, plus 2 more Liberals and Hitler.
- Deck stacked so the first 3 cards are F,F,L. President discards 1 of 3,
  Chancellor enacts 1 of 2. Random Fascist Chancellor will likely enact Fascist.

We run one round with `--dashboard` so you can read the predicted_roles
deltas in the dashboard block.
"""

from __future__ import annotations

import argparse

from src.game import Role
from src.policies import Policy
from src.runner import start_game


# 17 cards required: 3 we care about up top, then a plausible mix.
STACK = (
    [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]
    + [Policy.LIBERAL] * 5
    + [Policy.FASCIST] * 9
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    print("=== Scenario: Round 1 with FFL on top of deck ===")
    print("Operator dashboard shows the predicted_role deltas.\n")
    start_game(
        seed=args.seed,
        rounds=1,
        agents_mode="llm" if args.llm else "random",
        dashboard=True,
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER],
        stack_deck=STACK,
        token_budget=12_000,
    )


if __name__ == "__main__":
    main()
