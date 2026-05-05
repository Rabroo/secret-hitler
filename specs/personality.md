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
Initial values reflect what each role is *told* at game start per official rules at 5–6 players:

| Viewer\Target | Liberal | Fascist (other) | Hitler |
| ------------- | ------- | --------------- | ------ |
| Liberal       | 0.0     | 0.0             | 0.0    |
| Fascist       | 0.0     | n/a             | +1.0   |
| Hitler        | 0.0     | +1.0            | n/a    |

Liberals start with no information (all opinions exactly `0.0`). The Fascist team has mutual recognition: Hitler and the Fascist start the game knowing each other (5–6 player rule; differs at 7+) and their opinion of each other is exactly `+1.0` — *complete trust*, no fuzz, since the role information is given to them by the rules. The viewer's opinion of themselves is omitted from the dict.

No noise on opinions either. Public events later in the game will move them off these starting values.

## Edge cases
- Initial personalities are fully deterministic from role + roster — no RNG, so no seed dependency at this stage.
- Players added/removed mid-game are out of scope (we only build personalities once at game start; `advance_presidency` already handles dead players).

## Out of scope
- Opinion updates from public events (next phase, after legislative session lands).
- 7+ player rules (Hitler doesn't know Fascists at that count).
- LLM-driven personality drift / sentiment analysis of in-game speech.

## Dependencies
Stdlib only (`random`, `dataclasses`).
