"""Compare voting behaviour at F=2 vs F=3.

At F=3, electing Hitler as Chancellor wins the game for Fascists, so Liberals
should be MUCH more cautious about *any* nominee they're not sure about.
This scenario runs two games with identical role layouts and seeds, only
differing in the starting tally, so the operator can read the diff.

Run with `--llm` for real reasoning (~$0.10 total).
"""

from __future__ import annotations

import argparse

from src.game import Role
from src.runner import start_game


ROLES = [Role.LIBERAL, Role.HITLER, Role.LIBERAL, Role.FASCIST, Role.LIBERAL]
DIVIDER = "#" * 60


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    mode = "llm" if args.llm else "random"

    print(f"\n{DIVIDER}")
    print("# GAME A — starting tally L=0, F=2 (safe-ish)")
    print(DIVIDER)
    start_game(
        seed=args.seed,
        rounds=2,
        agents_mode=mode,
        dashboard=True,
        forced_roles=ROLES,
        start_tally=(0, 2),
        token_budget=40_000,
    )

    print(f"\n{DIVIDER}")
    print("# GAME B — starting tally L=0, F=3 (Hitler-as-Chan wins for Fascists)")
    print(DIVIDER)
    start_game(
        seed=args.seed,
        rounds=2,
        agents_mode=mode,
        dashboard=True,
        forced_roles=ROLES,
        start_tally=(0, 3),
        token_budget=40_000,
    )


if __name__ == "__main__":
    main()
