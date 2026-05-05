# Spec: Chancellor Election (Voting Phase)

## Goal
After the President nominates a Chancellor, every alive player votes Ja (yes) or Nein (no). A strict majority of yes-votes seats the government; ties and minority-yes results fail. State updates (term limits) apply only on a successful election. Decision-making is plugged in via a `vote_fn` callback so an LLM can be wired in later without touching the engine.

## Inputs / Outputs
**Inputs**
- `state: GameState` — provides the players list and the current President via `state.president_idx`.
- `nominee: Player` — the Chancellor candidate produced by the nomination phase.
- `vote_fn(voter, president, nominee) -> bool` — per-voter decision callback. Voter sees the proposed government (President + Nominee).

**Output**
- `ElectionResult` containing:
  - `passed: bool` — True if `yes > no`.
  - `votes: dict[int, bool]` — voter `player_id` → ja (True) / nein (False).

The function does not mutate `GameState`. The runner is responsible for applying consequences based on the result.

## Steps / Logic
1. Reject a dead nominee with `ValueError` (defensive — nomination should have excluded them).
2. Identify the President from `state.president_idx`.
3. For each alive player (in seat order, deterministically):
   - Call `vote_fn(voter, president, nominee)`; coerce result to `bool`.
   - Record the vote.
4. Tally: `yes = sum(votes.values())`, `no = len(votes) - yes`.
5. Return `ElectionResult(passed=(yes > no), votes=...)`.

## Runner integration (consequences)
- **On pass:** set `state.last_elected_president_id = president.id` and `state.last_elected_chancellor_id = nominee.id` (term limits update).
- **On fail:** leave `last_elected_*` unchanged.
- **Always:** advance the presidency to the next alive player (`advance_presidency`).

## Edge cases
- Dead players don't vote (skipped during iteration).
- Ties (yes == no) fail.
- A 0-alive-voter state returns `passed=False` with `votes={}` (degenerate; not reachable in normal play).
- `vote_fn` raising propagates — we do not silently swallow.
- Same `seed` produces identical vote sequences across runs (deterministic stub).

## Out of scope (future phases)
- **Election tracker** (3 consecutive failed elections → top policy auto-enacts, term limits reset). Tied to the policy deck, which doesn't exist yet.
- **Hitler-elected-after-3-fascist-policies** win condition. Tied to board state.
- LLM-backed vote functions (the callback shape is the seam where they'll plug in).

## Dependencies
- Python 3.11+
- `pytest` for tests
- Stdlib only (`random`, `dataclasses`)
