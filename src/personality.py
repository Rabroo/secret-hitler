"""Per-player personality: desire scalar + per-pair opinion map.

Initial values are exact and seeded only by role + 5p visibility rules — no
random noise. Public events will mutate opinions later (out of scope here).
See specs/personality.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.game import Player, Role


_KNOWN_ALLY = 1.0
_KNOWN_OPPONENT = -1.0


@dataclass
class Personality:
    desire: float
    opinions: dict[int, float] = field(default_factory=dict)


def _base_desire(role: Role) -> float:
    """Sign convention: +1 = wants Liberal outcomes, -1 = wants Fascist outcomes."""
    if role is Role.LIBERAL:
        return 1.0
    return -1.0  # Fascist + Hitler both want fascist outcomes


def _base_opinion(viewer: Player, target: Player) -> float:
    """Initial trust between two players.

    5-player rule: the Fascist team has *perfect information by elimination*.
    The Fascist is told who Hitler is, so the remaining 3 must all be Liberal;
    same for Hitler. So we seed:
      - Fascist team → fellow team member: +1.0 (known ally)
      - Fascist team → any Liberal:        -1.0 (known opponent)
      - Liberal     → anyone:               0.0 (no info)

    NOTE: at 7+ players the Fascists know each other but Hitler does NOT know
    them, and elimination no longer pins down the rest. This logic must be
    revisited then.
    """
    fascist_team = (Role.FASCIST, Role.HITLER)
    viewer_is_fascist_team = viewer.role in fascist_team
    target_is_fascist_team = target.role in fascist_team

    if viewer_is_fascist_team and target_is_fascist_team:
        return _KNOWN_ALLY
    if viewer_is_fascist_team and not target_is_fascist_team:
        return _KNOWN_OPPONENT
    return 0.0


def build_personalities(
    players: list[Player], seed: Optional[int] = None
) -> dict[int, Personality]:
    # `seed` is accepted for API symmetry with the rest of the engine, but no
    # randomness is used here — initial personalities are deterministic from role.
    del seed
    out: dict[int, Personality] = {}
    for viewer in players:
        opinions = {
            target.id: _base_opinion(viewer, target)
            for target in players
            if target.id != viewer.id
        }
        out[viewer.id] = Personality(
            desire=_base_desire(viewer.role), opinions=opinions
        )
    return out
