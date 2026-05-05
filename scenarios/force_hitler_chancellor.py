"""Force a 5p game where the President MUST nominate Hitler.

Setup:
- Roles fixed: Player 1 is Hitler, Players 2-4 are Liberal, Player 5 is Fascist.
- President is Player 1 (Hitler), so they nominate one of [2,3,4,5].
- We run a single round and watch the votes / dashboard.

Random mode is the default. Pass `--llm` to use the real OpenAI client.
"""

from __future__ import annotations

import argparse

from src.game import Role
from src.runner import start_game


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="Use LLMAgent instead of random")
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    print("=== Scenario: Hitler in the President seat (Player 1) ===")
    print("Watching what they nominate and how Liberals vote.\n")
    start_game(
        seed=args.seed,
        rounds=1,
        agents_mode="llm" if args.llm else "random",
        dashboard=True,
        forced_roles=[Role.HITLER, Role.LIBERAL, Role.LIBERAL, Role.LIBERAL, Role.FASCIST],
        token_budget=12_000,
    )


if __name__ == "__main__":
    main()
