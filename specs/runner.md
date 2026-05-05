# Spec: Game Runner — Start Command & President Rotation

## Goal
A CLI entry point that boots a game: assigns roles (visible only in an "operator view" log block), then runs N nomination rounds with the presidency rotating in seat order (1 → 2 → 3 → 4 → 5 → 1 → ...). LLM integration is still stubbed; nominations come from a seeded random `choose_fn`.

## Inputs / Outputs
**Inputs**
- `--seed` (optional int): seeds both role assignment and the random nomination stub for full reproducibility.
- `--rounds` (default 8): number of nomination rounds to play.

**Outputs (stdout)**
- An "operator view" block listing each player's secret role (clearly marked as private — once LLMs are wired in, each LLM only sees its own role; this block is for the human running the simulation).
- One block per round showing: president, eligible chancellors, and the nominee.

## Steps / Logic
1. Assign roles via `assign_roles(seed=seed)`.
2. Print the operator-view roster with an explicit "SECRET" marker.
3. Initialize `GameState` with `president_idx = 0` (Player 1 starts).
4. Build a seeded random `choose_fn` so nominations are reproducible.
5. For each of N rounds:
   a. Identify the current president.
   b. Compute eligible chancellors (for logging).
   c. Run `nominate_chancellor`.
   d. Print the round.
   e. Update `state.last_elected_chancellor_id` so term limits churn realistically. *(This is a stand-in for the not-yet-implemented voting step; once voting lands, this update will be conditional on a successful election.)*
   f. Call `advance_presidency` to step to the next alive player (wrap-around).

## New engine function
- `advance_presidency(state)` — moves `president_idx` to the next alive player in seat order, wrapping past the last seat. Raises `RuntimeError` if no alive players exist.

## Edge cases
- Dead players are skipped during rotation.
- Wrap-around: after player 5, presidency returns to player 1.
- Same `--seed` produces identical roster, presidents, and nominations.
- Term-limit churn — the previous chancellor is excluded next round (3 eligible candidates per round in steady state).

## Dependencies
Python stdlib only (`argparse`, `random`). Tests via `pytest` with `capsys`.

## Out of scope
Voting, policy deck, board state, win conditions, LLM calls, multi-game tournament loop.
