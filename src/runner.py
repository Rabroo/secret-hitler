"""CLI runner for Secret Hitler LLM.

Currently boots a 5-player game, prints an operator-view roster (visible
only to the human running the simulation — once LLMs are wired in, each
LLM will only see its own role), and runs N nomination rounds with the
presidency rotating in seat order.
"""

from __future__ import annotations

import argparse
import random
from typing import Callable

from src.game import (
    GameState,
    Player,
    advance_presidency,
    assign_roles,
    eligible_chancellors,
    nominate_chancellor,
)


_DIVIDER = "=" * 60
_DEFAULT_ROUNDS = 8


def _random_choose_fn(seed: int | None) -> Callable[[Player, list[Player]], Player]:
    rng = random.Random(seed)
    return lambda _president, candidates: rng.choice(candidates)


def _render_operator_view(players: list[Player]) -> str:
    lines = [
        _DIVIDER,
        "SECRET — OPERATOR VIEW (do not share with players)",
        _DIVIDER,
    ]
    for p in players:
        lines.append(f"  Player {p.id}: {p.role.value.upper()}")
    lines.append(_DIVIDER)
    return "\n".join(lines)


def _render_round(
    round_num: int,
    president: Player,
    candidates: list[Player],
    chosen: Player,
) -> str:
    return "\n".join(
        [
            f"\n--- Round {round_num} ---",
            f"President: Player {president.id}",
            f"Eligible chancellors: {[p.id for p in candidates]}",
            f"Nominated: Player {chosen.id}",
        ]
    )


def start_game(
    seed: int | None = None,
    rounds: int = _DEFAULT_ROUNDS,
) -> GameState:
    """Run a stub game: assign roles, then rotate the presidency for N rounds."""
    players = assign_roles(seed=seed)
    print(_render_operator_view(players))

    state = GameState(players=players, president_idx=0)
    choose = _random_choose_fn(seed=seed)

    for round_num in range(1, rounds + 1):
        president = state.players[state.president_idx]
        candidates = eligible_chancellors(state)
        chosen = nominate_chancellor(state, choose)
        print(_render_round(round_num, president, candidates, chosen))

        # Stand-in for a successful election until voting is implemented.
        state.last_elected_chancellor_id = chosen.id
        state.last_elected_president_id = president.id
        advance_presidency(state)

    return state


def main() -> None:
    parser = argparse.ArgumentParser(prog="secret-hitler-llm")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start a new game")
    start.add_argument("--seed", type=int, default=None)
    start.add_argument("--rounds", type=int, default=_DEFAULT_ROUNDS)

    args = parser.parse_args()
    if args.command == "start":
        start_game(seed=args.seed, rounds=args.rounds)


if __name__ == "__main__":
    main()
