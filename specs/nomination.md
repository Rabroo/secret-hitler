# Spec: Nomination Phase (Secret Hitler LLM)

## Goal
Framework for the Chancellor nomination phase of a 5-player Secret Hitler game. Players are stub-named 1–5. Decision-making is plugged in via a `choose_fn` callback so we can swap in an LLM later without changing the engine.

## Inputs / Outputs
**Inputs**
- `num_players` (fixed at 5 for now)
- Optional `seed` for deterministic role assignment
- A `GameState` carrying players, current president index, and last-elected-government IDs
- A `choose_fn(president, eligible_candidates) -> Player` callback

**Outputs**
- A list of `Player` objects with assigned `Role`s
- The `Player` nominated as Chancellor

## Steps / Logic
1. **Role assignment** — randomly distribute 3 Liberal, 1 Fascist, 1 Hitler across 5 players. Seedable.
2. **Identify President** — the player at `state.president_idx`.
3. **Compute eligible Chancellors**:
   - Must be alive
   - Cannot be the President themselves
   - Cannot be the last elected Chancellor
   - 5-player rule: previous President is *not* term-limited (this differs at 7+ players)
4. **Invoke `choose_fn`** with `(president, eligible_list)`; it returns the nominee.
5. **Validate** the nominee is in the eligible list; raise `ValueError` otherwise.

## Edge cases
- `choose_fn` returns the President or last Chancellor → `ValueError`.
- `choose_fn` returns a dead player → excluded from eligibility, so `ValueError`.
- `num_players` other than 5 → `NotImplementedError` (other sizes are out of scope for this phase).
- Two seeded calls with same seed → identical role assignments (reproducibility).

## Dependencies
- Python 3.11+
- `pytest` for tests
- Stdlib only for game logic (`random`, `dataclasses`, `enum`)

## Out of scope (future phases)
Voting, policy deck, board state, presidential powers, win conditions, LLM integration, 6–10 player rules.
