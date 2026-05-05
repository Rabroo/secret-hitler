"""Per-player personality: desire scalar + predicted_roles map.

Initial values are exact and seeded only by role + 5p visibility rules.
predicted_roles[X] = +1 means "I predict X is Liberal", -1 means "I predict
X is on the Fascist team", 0 means "no information". Public events update
the values for Liberal viewers — see `specs/predicted_role_updates.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.game import Player, Role


_PREDICTED_LIBERAL = 1.0
_PREDICTED_FASCIST = -1.0
_NO_INFO = 0.0


@dataclass
class Personality:
    desire: float
    predicted_roles: dict[int, float] = field(default_factory=dict)


def _base_desire(role: Role) -> float:
    """Sign convention: +1 = wants Liberal outcomes, -1 = wants Fascist outcomes."""
    if role is Role.LIBERAL:
        return 1.0
    return -1.0  # Fascist + Hitler both want fascist outcomes


def _base_predicted_role(viewer: Player, target: Player) -> float:
    """Initial prediction of `target`'s role from `viewer`'s perspective.

    5-player rule: the Fascist team has *perfect information by elimination*.
    The Fascist is told who Hitler is, so the remaining 3 must all be Liberal;
    same for Hitler. So we seed:
      - Liberal viewer  → anyone:           0.0  (no info)
      - Fascist viewer  → Liberal:         +1.0  (predicted Liberal — they know)
      - Fascist viewer  → Hitler:          -1.0  (predicted Fascist team — they know)
      - Hitler viewer   → Liberal:         +1.0
      - Hitler viewer   → Fascist:         -1.0

    NOTE: at 7+ players this elimination breaks; revisit then.
    """
    if viewer.role is Role.LIBERAL:
        return _NO_INFO
    # Fascist or Hitler viewer — they have full info at 5p
    if target.role is Role.LIBERAL:
        return _PREDICTED_LIBERAL
    return _PREDICTED_FASCIST


def build_personalities(
    players: list[Player], seed: Optional[int] = None
) -> dict[int, Personality]:
    # `seed` is accepted for API symmetry with the rest of the engine; no RNG
    # is used here — initial personalities are deterministic from role.
    del seed
    out: dict[int, Personality] = {}
    for viewer in players:
        predicted = {
            target.id: _base_predicted_role(viewer, target)
            for target in players
            if target.id != viewer.id
        }
        out[viewer.id] = Personality(
            desire=_base_desire(viewer.role), predicted_roles=predicted
        )
    return out
