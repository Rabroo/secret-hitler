"""President draws FFL → discards F → passes [F, L] to the Chancellor.

Two runs with the same stacked deck but different role layouts:
  GAME A: Chancellor is a LIBERAL (likely picks LIBERAL).
  GAME B: Chancellor is a FASCIST (likely picks FASCIST and lies).

What to compare in the dashboards:
  - Did the Chancellor enact the same policy in both games?
  - Did the Chancellor's statement match what they actually did?
  - How did the President's predicted_role of the Chancellor shift after each?
    A forced-Liberal-passed-and-Liberal-enacted should bump trust UP.
    A forced-Liberal-passed-and-Fascist-enacted should bump trust DOWN hard
    (because the President's PRIVATE KNOWLEDGE proves the Chancellor had a
    Liberal available).

Run with `--llm` (~$0.05).
"""

from __future__ import annotations

import argparse

from src.game import Role
from src.policies import Policy
from src.runner import start_game


# Top 3 cards: FFL → Pres discards F → Chancellor gets [F, L].
STACK_FFL = (
    [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]
    + [Policy.LIBERAL] * 5
    + [Policy.FASCIST] * 9
)

# Layout A: P1 Liberal Pres; first eligible Chancellor likely picked is a Liberal.
ROLES_LIBERAL_CHAN = [
    Role.LIBERAL, Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.HITLER,
]

# Layout B: P1 Liberal Pres; layout chosen so the LLM is likely to pick a
# Fascist as Chancellor (P2 is Fascist and adjacent in seat order).
ROLES_FASCIST_CHAN = [
    Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.LIBERAL, Role.HITLER,
]

DIVIDER = "#" * 60


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    mode = "llm" if args.llm else "random"

    print(f"\n{DIVIDER}")
    print("# GAME A — Liberal-only candidates as Chancellor")
    print("# Pres draws FFL → discards F → Chan gets [F, L]")
    print("# Liberal Chancellor should pick LIBERAL.")
    print(DIVIDER)
    start_game(
        seed=args.seed,
        rounds=1,
        agents_mode=mode,
        dashboard=True,
        forced_roles=ROLES_LIBERAL_CHAN,
        stack_deck=STACK_FFL,
        token_budget=20_000,
    )

    print(f"\n{DIVIDER}")
    print("# GAME B — Fascist available as Chancellor")
    print("# Pres draws FFL → discards F → Chan gets [F, L]")
    print("# Fascist Chancellor likely picks FASCIST and lies in discussion.")
    print(DIVIDER)
    start_game(
        seed=args.seed,
        rounds=1,
        agents_mode=mode,
        dashboard=True,
        forced_roles=ROLES_FASCIST_CHAN,
        stack_deck=STACK_FFL,
        token_budget=20_000,
    )


if __name__ == "__main__":
    main()
