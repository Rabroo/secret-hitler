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

from src.policies import Policy, PolicyDeck


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
    liberal_policies_enacted: int = 0
    fascist_policies_enacted: int = 0


ChooseFn = Callable[[Player, list[Player]], Player]
VoteFn = Callable[[Player, Player, Player], bool]
DiscardFn = Callable[[Player, list[Policy]], Policy]
EnactFn = Callable[[Player, list[Policy]], Policy]


@dataclass
class ElectionResult:
    passed: bool
    votes: dict[int, bool] = field(default_factory=dict)

    @property
    def yes_count(self) -> int:
        return sum(1 for v in self.votes.values() if v)

    @property
    def no_count(self) -> int:
        return len(self.votes) - self.yes_count


@dataclass
class LegislativeSessionResult:
    drawn: list[Policy]
    discarded_by_president: Policy
    handed_to_chancellor: list[Policy]
    enacted: Policy
    discarded_by_chancellor: Policy


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


def vote_chancellor(
    state: GameState,
    nominee: Player,
    vote_fn: VoteFn,
) -> ElectionResult:
    """Run the chancellor election and return the result without mutating state.

    Every alive player votes via `vote_fn(voter, president, nominee)`. A strict
    majority of yes-votes passes; ties and minority-yes fail.
    """
    if not nominee.alive:
        raise ValueError(
            f"Player {nominee.id} is dead and cannot stand for Chancellor"
        )
    president = state.players[state.president_idx]
    votes: dict[int, bool] = {}
    for voter in state.players:
        if not voter.alive:
            continue
        votes[voter.id] = bool(vote_fn(voter, president, nominee))
    yes = sum(1 for v in votes.values() if v)
    no = len(votes) - yes
    return ElectionResult(passed=yes > no, votes=votes)


def _remove_policy(hand: list[Policy], chosen: Policy) -> list[Policy]:
    """Return a copy of `hand` with one occurrence of `chosen` removed.

    Raises ValueError if `chosen` isn't present. Count-based so duplicate
    policies (e.g. [F, F, L]) are handled correctly.
    """
    if chosen not in hand:
        raise ValueError(
            f"Policy {chosen.value} is not in the hand "
            f"({[p.value for p in hand]})"
        )
    remaining = list(hand)
    remaining.remove(chosen)
    return remaining


def legislative_session(
    state: GameState,
    deck: PolicyDeck,
    president: Player,
    chancellor: Player,
    discard_fn: DiscardFn,
    enact_fn: EnactFn,
) -> LegislativeSessionResult:
    """Run a full legislative session and update the public tally.

    1. Draw 3 from `deck`.
    2. Ask the President to pick one to discard via `discard_fn`.
    3. Pass the remaining 2 to the Chancellor; ask which to enact via `enact_fn`.
    4. Increment the corresponding tally on `state`.
    5. Send both discarded policies to the deck's discard pile.

    Win conditions are NOT checked here — caller's responsibility.
    """
    drawn = deck.draw(3)
    president_discard = discard_fn(president, list(drawn))
    chancellor_hand = _remove_policy(drawn, president_discard)

    enacted = enact_fn(chancellor, list(chancellor_hand))
    chancellor_discard_pile = _remove_policy(chancellor_hand, enacted)
    chancellor_discard = chancellor_discard_pile[0]

    if enacted is Policy.LIBERAL:
        state.liberal_policies_enacted += 1
    else:
        state.fascist_policies_enacted += 1

    deck.discard([president_discard, chancellor_discard])

    return LegislativeSessionResult(
        drawn=list(drawn),
        discarded_by_president=president_discard,
        handed_to_chancellor=list(chancellor_hand),
        enacted=enacted,
        discarded_by_chancellor=chancellor_discard,
    )
