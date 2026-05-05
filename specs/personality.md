# Spec: Player Personality (Desires + Opinions)

## Goal
Give each player a numeric personality the LLM can reason from. Two pieces:
- A **desire** scalar in `[-1, +1]` describing how much the player wants Liberal (negative) vs. Fascist (positive) outcomes.
- An **opinion map** `{other_player_id: float in [-1, +1]}` describing trust (positive) vs. suspicion (negative) of every other player.

Both are seeded deterministically from `(role, role_visibility, seed)`. Opinions can be mutated by the game over time as public events happen (votes, enacted policies). Desires stay fixed for the life of the game.

## Inputs / Outputs
**Inputs**
- `players: list[Player]` — the full roster (with assigned roles).
- `seed: int | None` — for deterministic noise.

**Output**
- `dict[player_id, Personality]` — one per player.

## Data shape
```python
@dataclass
class Personality:
    desire: float          # -1.0 (Liberal-aligned) .. +1.0 (Fascist-aligned)
    opinions: dict[int, float]  # other_id -> -1.0 .. +1.0
```

## Seeding rules

### Desire (fixed at game start)
| Role     | Base desire | Notes                                                         |
| -------- | ----------- | ------------------------------------------------------------- |
| Liberal  | `-1.0`      | Wants Liberal policies; distrusts confirmed Fascist behavior. |
| Fascist  | `+1.0`      | Wants Fascist policies; wants Hitler elected late game.       |
| Hitler   | `+1.0`      | Same alignment as Fascists; needs to stay hidden.             |

A small uniform noise `±0.1` is added per player from the seeded RNG so two Liberals don't read identically to the LLM. Result is clamped to `[-1, +1]`.

### Opinions (seeded at game start, will mutate later)
Initial values reflect what each role is *told* at game start per official rules at 5–6 players:

| Viewer\Target | Liberal | Fascist (other) | Hitler |
| ------------- | ------- | --------------- | ------ |
| Liberal       | 0.0     | 0.0             | 0.0    |
| Fascist       | 0.0     | n/a             | +1.0   |
| Hitler        | 0.0     | +1.0            | n/a    |

Liberals start with no information (all neutral). The Fascist team has mutual recognition: Hitler and the Fascist start the game knowing each other (5–6 player rule; differs at 7+). The viewer's opinion of themselves is omitted from the dict.

Same per-pair noise (`±0.05`, seeded) is layered on so opinions aren't perfectly flat.

## Edge cases
- Same `seed` → identical personalities for the same role assignment.
- Clamping: any noise that pushes a value outside `[-1, +1]` is clamped at the boundary.
- Players added/removed mid-game are out of scope (we only build personalities once at game start; `advance_presidency` already handles dead players).

## Out of scope
- Opinion updates from public events (next phase, after legislative session lands).
- 7+ player rules (Hitler doesn't know Fascists at that count).
- LLM-driven personality drift / sentiment analysis of in-game speech.

## Dependencies
Stdlib only (`random`, `dataclasses`).
