"""Core game engine for Secret Hitler (LLM edition).

Currently scoped to the 5-player nomination phase. Decision-making is
delegated to a `choose_fn` callback so an LLM can be plugged in later
without touching engine logic.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class Role(Enum):
    LIBERAL = "liberal"
    FASCIST = "fascist"
    HITLER = "hitler"


@dataclass
class Player:
    id: int
    role: Role
    alive: bool = True

    def __repr__(self) -> str:
        status = "" if self.alive else " (dead)"
        return f"Player {self.id} [{self.role.value}]{status}"


@dataclass
class GameState:
    players: list[Player]
    president_idx: int = 0
    last_elected_president_id: Optional[int] = None
    last_elected_chancellor_id: Optional[int] = None


ChooseFn = Callable[[Player, list[Player]], Player]


_FIVE_PLAYER_ROLES = [
    Role.LIBERAL,
    Role.LIBERAL,
    Role.LIBERAL,
    Role.FASCIST,
    Role.HITLER,
]


def assign_roles(num_players: int = 5, seed: Optional[int] = None) -> list[Player]:
    """Randomly assign roles to `num_players` players (only 5 supported for now)."""
    if num_players != 5:
        raise NotImplementedError(
            f"Only 5-player games are supported; got {num_players}"
        )
    rng = random.Random(seed)
    roles = list(_FIVE_PLAYER_ROLES)
    rng.shuffle(roles)
    return [Player(id=i + 1, role=roles[i]) for i in range(num_players)]


def eligible_chancellors(state: GameState) -> list[Player]:
    """Return players the current President may nominate as Chancellor.

    5-player rule: only the last elected Chancellor is term-limited;
    the previous President is still eligible.
    """
    president = state.players[state.president_idx]
    return [
        p
        for p in state.players
        if p.alive
        and p.id != president.id
        and p.id != state.last_elected_chancellor_id
    ]


def advance_presidency(state: GameState) -> None:
    """Move the presidency to the next alive player in seat order, wrapping around."""
    n = len(state.players)
    for step in range(1, n + 1):
        next_idx = (state.president_idx + step) % n
        if state.players[next_idx].alive:
            state.president_idx = next_idx
            return
    raise RuntimeError("No alive players remain to take the presidency")


def nominate_chancellor(state: GameState, choose_fn: ChooseFn) -> Player:
    """Run the nomination step and return the nominee.

    `choose_fn` receives `(president, eligible_candidates)` and must return
    one of the candidates. Raises `ValueError` if the choice is ineligible.
    """
    president = state.players[state.president_idx]
    candidates = eligible_chancellors(state)
    chosen = choose_fn(president, candidates)
    if chosen not in candidates:
        raise ValueError(
            f"Player {chosen.id} is not an eligible Chancellor "
            f"(eligible: {[p.id for p in candidates]})"
        )
    return chosen
