"""Multi-round game with two FFF stacks early — same player likely ends up
in a second F-enacting government. How do other players' predicted_roles
of that player evolve over the two enactments?

Setup:
- 5p layout: P1 Liberal, P2 Hitler, P3 Liberal, P4 Fascist, P5 Liberal.
- Top 6 cards: FFF FFF — first two enacted policies are forced Fascist.
- Cards 7-12 are L,L,L,L,L,L — gives the next two governments better odds
  of enacting Liberal so the contrast shows.
- Cards 13-17: F,F,F,F,F to round out the deck.

What to watch:
- Track the Chancellor in round 1 and round 2 — both will have enacted F.
- After round 2, are they pinned at low predicted_role by the Liberals?
- Round 3 onwards plays out with cleaner draws — does the table correctly
  pivot suspicion?

Run with `--llm` for real reasoning (~$0.20).
"""

from __future__ import annotations

import argparse

from src.game import Role
from src.policies import Policy
from src.runner import start_game


STACK = (
    [Policy.FASCIST] * 6
    + [Policy.LIBERAL] * 6
    + [Policy.FASCIST] * 5
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--rounds", type=int, default=4)
    args = parser.parse_args()

    print("=== Scenario: repeat Fascist enactor ===")
    print("First two governments are forced into F enactions; later draws lean Liberal.")
    print(f"Running {args.rounds} rounds with full discussion.\n")
    start_game(
        seed=args.seed,
        rounds=args.rounds,
        agents_mode="llm" if args.llm else "random",
        dashboard=True,
        forced_roles=[
            Role.LIBERAL, Role.HITLER, Role.LIBERAL, Role.FASCIST, Role.LIBERAL,
        ],
        stack_deck=STACK,
        token_budget=80_000,
    )


if __name__ == "__main__":
    main()
