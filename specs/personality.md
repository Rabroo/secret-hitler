# Spec: Player Personality (Desire + Predicted Roles)

## Goal
Give each player a numeric personality the LLM can reason from. Two pieces:
- A **desire** scalar in `[-1, +1]` describing how much the player wants Liberal (positive) vs. Fascist (negative) outcomes.
- A **predicted_roles** map `{other_player_id: float in [-1, +1]}` — *the viewer's belief about the other player's role*, with `+1.0 = "I think they are Liberal"` and `-1.0 = "I think they are on the Fascist team"`. `0.0` = no information.

Initial values are exact and seeded only by role + 5p visibility rules. Public events (votes, enacted policies) move them later — see `specs/predicted_role_updates.md`.

## Inputs / Outputs
**Inputs**
- `players: list[Player]` — the full roster (with assigned roles).

**Output**
- `dict[player_id, Personality]` — one per player.

## Data shape
```python
@dataclass
class Personality:
    desire: float                  # -1.0 (Fascist-aligned) .. +1.0 (Liberal-aligned)
    predicted_roles: dict[int, float]  # other_id -> -1.0 (predicted Fascist) .. +1.0 (predicted Liberal)
```

## Seeding rules

### Desire (fixed at game start)
| Role     | Base desire | Notes                                                         |
| -------- | ----------- | ------------------------------------------------------------- |
| Liberal  | `+1.0`      | Wants Liberal policies; distrusts confirmed Fascist behavior. |
| Fascist  | `-1.0`      | Wants Fascist policies; wants Hitler elected late game.       |
| Hitler   | `-1.0`      | Same alignment as Fascists; needs to stay hidden.             |

No noise — exact values per role. Two Liberals start identical; behavioural variation is the LLM's job.

### Predicted roles (seeded at game start, will update later)

At 5 players the Fascist team has **perfect information by elimination** — they know the role of every other player. Liberals know nothing. The numbers therefore reflect:

| Viewer\Target  | Liberal | Fascist (other) | Hitler |
| -------------- | ------- | --------------- | ------ |
| Liberal viewer | 0.0     | 0.0             | 0.0    |
| Fascist viewer | +1.0    | n/a             | -1.0   |
| Hitler viewer  | +1.0    | -1.0            | n/a    |

- `+1.0` = predicted Liberal.
- `-1.0` = predicted Fascist (or Hitler — engine treats the Fascist team as one bucket for prediction).
- `0.0` = no information.

For Fascist team viewers these values are pinned at *known truth* and never update — they already know. For Liberal viewers they start at `0.0` and move based on observed events.

The viewer's own entry is omitted from the dict.

## Edge cases
- Initial personalities are fully deterministic from role + roster. No RNG.
- Updates are clamped to `[-1.0, +1.0]` (see updates spec).
- Players added/removed mid-game are out of scope; we build personalities once at game start.

## Out of scope
- Update logic for predicted_roles — see `specs/predicted_role_updates.md`.
- 7+ player rules (Hitler doesn't know the Fascists at that count); revisit when we add bigger games.
- LLM-driven (rather than heuristic) updates — also in the updates spec as future work.

## Dependencies
Stdlib only (`dataclasses`).
