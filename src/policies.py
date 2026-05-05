"""Policy deck for Secret Hitler.

17-card deck: 6 Liberal + 11 Fascist (rulebook). Seedable for tests. Reshuffles
the discard pile back in whenever the draw pile drops below the requested
draw size — equivalent to the rulebook's "reshuffle when draw pile has fewer
than 3 cards" check.
"""

from __future__ import annotations

import random
from enum import Enum
from typing import Optional


class Policy(Enum):
    LIBERAL = "liberal"
    FASCIST = "fascist"


_LIBERAL_COUNT = 6
_FASCIST_COUNT = 11


class PolicyDeck:
    def __init__(
        self,
        seed: Optional[int] = None,
        *,
        draw_pile: Optional[list[Policy]] = None,
    ):
        """If `draw_pile` is given, it overrides the default shuffled deck.

        Pass cards in the order they should be drawn (first item = top of
        deck = next draw). Internally we store the reverse of that so `pop()`
        returns the right card.
        """
        self._rng = random.Random(seed)
        if draw_pile is not None:
            self._draw_pile = list(reversed(draw_pile))
        else:
            self._draw_pile = [Policy.LIBERAL] * _LIBERAL_COUNT + [
                Policy.FASCIST
            ] * _FASCIST_COUNT
            self._rng.shuffle(self._draw_pile)
        self._discard_pile: list[Policy] = []

    @property
    def remaining(self) -> int:
        return len(self._draw_pile)

    @property
    def discard_size(self) -> int:
        return len(self._discard_pile)

    def draw(self, n: int) -> list[Policy]:
        if len(self._draw_pile) < n:
            self._reshuffle_from_discard()
        if len(self._draw_pile) < n:
            raise RuntimeError(
                f"Cannot draw {n}: only {len(self._draw_pile)} cards available "
                f"after reshuffle"
            )
        return [self._draw_pile.pop() for _ in range(n)]

    def discard(self, policies: list[Policy]) -> None:
        self._discard_pile.extend(policies)

    def _reshuffle_from_discard(self) -> None:
        self._draw_pile.extend(self._discard_pile)
        self._discard_pile.clear()
        self._rng.shuffle(self._draw_pile)
