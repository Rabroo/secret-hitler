# Spec: Election Tracker (3 Failed Elections → Chaos)

## Goal
Implement the rulebook's election tracker so the game can't stall when Liberals refuse to elect any government at F≥3. Per the rulebook:

> Each time an election fails the tracker advances. After three failed elections in a row, the country is thrown into chaos: the policy at the top of the draw pile is enacted (no Presidential power triggers), term limits reset, and the tracker resets to 0. Each successful election also resets the tracker.

## Triggers
- **Failed election** → `state.failed_elections += 1`. If now `>= 3` → chaos.
- **Successful election** → `state.failed_elections = 0`.
- **Chaos triggered** → enact top of deck, reset tracker, reset term limits, *check win conditions*. No presidential power. No discussion. No agent decision involved.

## State changes
Two new things on `GameState`:
- `failed_elections: int = 0` — current tracker count, in `[0, 3)`.

After chaos:
- `state.failed_elections = 0`
- `state.last_elected_president_id = None`
- `state.last_elected_chancellor_id = None`  (term limits reset per rulebook)
- `state.liberal_policies_enacted` or `state.fascist_policies_enacted` incremented per the auto-enacted policy.
- `check_winner(state)` runs after the auto-enact so a chaos enaction can trigger a tally-based win.

## Engine API
New helper in `src/game.py`:
```python
def chaos_enact(state: GameState, deck: PolicyDeck) -> Policy:
    """Auto-enact the top of the deck. Caller checks failed_elections >= 3."""
```
- Draws 1 card from the deck (deck handles reshuffle when low).
- Increments the appropriate tally.
- Resets tracker + term limits.
- Returns the enacted Policy (caller logs / displays it).
- Does NOT trigger presidential powers.
- Does NOT call `check_winner` itself — caller does.

## RoundEvent additions
Add an optional field so the streamlit viewer / dashboard can render chaos:
```python
chaos_enacted: Optional[Policy] = None
failed_elections_after: int = 0
```
Failed-election rounds where chaos *did* fire have `chaos_enacted` set. Failed-election rounds before the third failure leave it `None` and just bump `failed_elections_after`.

## Runner integration
Inside the round loop, *after* `vote_chancellor` returns:

```python
if result.passed:
    state.failed_elections = 0
    # ... existing legislative session + win checks
else:
    state.failed_elections += 1
    if state.failed_elections >= 3:
        chaos_policy = chaos_enact(state, deck)
        # log chaos_policy on the RoundEvent
        # check tally-win after chaos
        winner = check_winner(state)
        if winner is not None:
            state.winner = winner
            state.winning_reason = f"Chaos auto-enacted policy completed the tally."
```

## Dashboard / round line
- Round-line tail: when failed → append `Election tracker: N/3`.
- When chaos fires that round: also append `Chaos! Auto-enacted: <POLICY>. Tally now: L=X F=Y.`

## Prompts
- Add one line to the shared rules summary block:
  > After 3 failed elections in a row the country goes into chaos: the top of the deck auto-enacts, term limits reset, and the tracker resets.
- Show current tracker in the GAME HISTORY footer:
  > `Current tally: L=N F=N. Election tracker: N/3.`

## Edge cases
- 3rd failure when deck has 0 cards → reshuffle from discard (already handled by `PolicyDeck.draw`).
- 3rd failure when discard is also empty → shouldn't happen mid-game; if it did, `draw()` would raise.
- Chaos enaction at `F=5` could push to `F=6` → Fascist tally win. `check_winner` fires after.
- Chaos at `L=4` → `L=5` → Liberal win.
- Chaos enaction does NOT trigger a presidential power (no F=3 peek, no F=4 execution). Powers don't exist yet anyway, but call this out so the future powers wiring respects it.
- After chaos, term limits reset means the next nomination has every alive non-self player eligible (no last-Chancellor exclusion).

## Tests
- Two failed elections leave tracker at 2, no chaos, term limits unchanged.
- Three failed elections trigger chaos: tally increments by exactly 1, tracker → 0, both `last_elected_*` cleared.
- Successful election resets tracker (was 2 → 0 after a pass).
- `chaos_enact` returns the drawn policy.
- Chaos that puts tally at win threshold sets `state.winner`.
- Term-limit reset means `eligible_chancellors` after chaos is `len(alive) - 1` (only excludes self).
- Runner integration: forced 3 nein votes triggers chaos with the right output line.

## Out of scope
- Presidential powers (peek/execute) — separate spec; chaos won't trigger them when they exist.
- Veto.
- Election tracker visualisation in the streamlit viewer (we just persist the field; the viewer can render it later).

## Dependencies
Stdlib only.
