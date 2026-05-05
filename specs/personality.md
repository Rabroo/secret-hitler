# Spec: Player Personality (Desires + Opinions)

## Goal
Give each player a numeric personality the LLM can reason from. Two pieces:
- A **desire** scalar in `[-1, +1]` describing how much the player wants Liberal (positive) vs. Fascist (negative) outcomes.
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
| Liberal  | `+1.0`      | Wants Liberal policies; distrusts confirmed Fascist behavior. |
| Fascist  | `-1.0`      | Wants Fascist policies; wants Hitler elected late game.       |
| Hitler   | `-1.0`      | Same alignment as Fascists; needs to stay hidden.             |

No noise — desires are exactly `±1.0` based on role. (Two Liberals start identical; behavioural variation is the LLM's job at runtime, not the engine's.)

### Opinions (seeded at game start, will mutate later)

At 5 players the Fascist team has **perfect information by elimination**: the Fascist is told who Hitler is, so the remaining 3 players must all be Liberal (and vice versa for Hitler). Liberals know nothing.

| Viewer\Target | Liberal | Fascist (other) | Hitler |
| ------------- | ------- | --------------- | ------ |
| Liberal       | 0.0     | 0.0             | 0.0    |
| Fascist       | -1.0    | n/a             | +1.0   |
| Hitler        | -1.0    | +1.0            | n/a    |

- `+1.0` = known ally (told by rules).
- `-1.0` = known opponent (deduced by elimination at 5p).
- `0.0`  = no information.

The viewer's opinion of themselves is omitted from the dict. No noise — values are exact. Public events later in the game will move these off their starting values; that update logic is out of scope for this spec.

**Caveat:** the elimination-knowledge inference only holds at 5–6 players. At 7+ Hitler does not know who the Fascists are, so Hitler's by-elimination knowledge collapses. This logic must be revisited when we add bigger games.

## Edge cases
- Initial personalities are fully deterministic from role + roster — no RNG, so no seed dependency at this stage.
- Players added/removed mid-game are out of scope (we only build personalities once at game start; `advance_presidency` already handles dead players).

## Out of scope
- Opinion updates from public events (next phase, after legislative session lands).
- 7+ player rules (Hitler doesn't know Fascists at that count).
- LLM-driven personality drift / sentiment analysis of in-game speech.

## Dependencies
Stdlib only (`random`, `dataclasses`).
