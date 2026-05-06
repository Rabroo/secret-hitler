"""Force a Fascist enaction in round 1 and observe predicted_roles after.

Setup:
- 5p layout: P1 Liberal, P2 Hitler, P3 Liberal, P4 Fascist, P5 Liberal.
- Top of deck stacked F,F,F so the President's first draw is forced.
- Pres P1 has no Liberal to discard; Chancellor receives [F,F]; F enaction
  is unavoidable.

What to watch:
- Did the LLM correctly recognise the forced nature in its statement?
- Did Liberals' predicted_roles still drop on a forced F enaction (they
  shouldn't drop *much*, given the deck is 11F vs 6L)?

Run with `--llm` for real API calls (~$0.05); default is free random mode.
"""

from __future__ import annotations

import argparse

from src.game import Role
from src.policies import Policy
from src.runner import start_game


# 17 cards: top 3 forced FFF, then a plausible mix.
STACK = [Policy.FASCIST] * 3 + [Policy.LIBERAL] * 6 + [Policy.FASCIST] * 8


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    print("=== Scenario: Round-1 forced Fascist enaction ===")
    print("Pres P1 (Liberal) draws FFF; Chan receives FF; F is enacted.")
    print("Watching how predicted_roles shift after a forced F.\n")
    start_game(
        seed=args.seed,
        rounds=1,
        agents_mode="llm" if args.llm else "random",
        dashboard=True,
        forced_roles=[
            Role.LIBERAL, Role.HITLER, Role.LIBERAL, Role.FASCIST, Role.LIBERAL,
        ],
        stack_deck=STACK,
        token_budget=20_000,
    )


if __name__ == "__main__":
    main()
