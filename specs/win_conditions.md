# Spec: Win Conditions

## Goal
Detect a winning condition and end the game. Three triggers:

1. **Liberal policy win** — `state.liberal_policies_enacted >= 5` immediately after a Liberal policy is enacted.
2. **Fascist policy win** — `state.fascist_policies_enacted >= 6` immediately after a Fascist policy is enacted.
3. **Hitler-Chancellor win** — Hitler is elected as Chancellor at the moment the election succeeds, with `state.fascist_policies_enacted >= 3` already on the board. Triggered before any policy is enacted that round.

When any trigger fires, the runner stops the loop and prints a "GAME OVER — \<faction\> VICTORY" banner with the reason. Subsequent rounds (if `--rounds` was set higher) are not played.

## Faction enum (new)
```python
class Faction(Enum):
    LIBERAL = "liberal"
    FASCIST = "fascist"
```
Hitler counts as Fascist faction.

## State changes
Two new fields on `GameState`:
- `winner: Optional[Faction] = None`
- `winning_reason: Optional[str] = None`  (free-text, shown in the banner)

Once `winner` is non-None the game is over; nothing else mutates the tally or history.

## `check_winner(state, just_elected_chancellor=None)` (new)
Pure function returning `Optional[Faction]`. Caller is responsible for assigning to `state.winner` and `state.winning_reason`.

- Tally checks always run.
- Hitler-Chancellor check runs only when `just_elected_chancellor` is provided (i.e., right after a successful election).

## Runner integration
The order within a round becomes:

1. Nominate.
2. Vote.
3. **If election passed:**
   - Check Hitler-Chancellor win (`just_elected_chancellor=chosen`). If triggered, set `state.winner = FASCIST`, skip legislative session.
   - Otherwise: run legislative session, then check tally win.
4. Append `RoundEvent` to history.
5. Print round + dashboard.
6. **If winner set:** print banner, break out of loop.
7. Advance presidency.

The Hitler-Chancellor check happens *before* the legislative session so the banner can correctly say "Hitler elected Chancellor at F=3" (or higher) — without an extra policy being enacted that round.

## Banner format
```
============================================================
GAME OVER — LIBERAL VICTORY
Liberals enacted 5 Liberal policies.
============================================================
```

```
============================================================
GAME OVER — FASCIST VICTORY
Hitler was elected Chancellor with 4 Fascist policies on the board.
============================================================
```

## Edge cases
- Both `L>=5` and `F>=6` simultaneously is impossible (only one policy enacts per round).
- Hitler-Chancellor check at `F<3` is a no-op (election proceeds to legislative session).
- A failed election never triggers any win condition.
- `start_game` returns the state with `winner` set so callers (tests, scenarios) can inspect.

## Out of scope (next phases)
- **Liberal-execute-Hitler win** — needs presidential-execute power, which doesn't exist.
- **Veto** at F=5.
- **Election tracker** auto-enaction at 3 failed elections in a row.

## Dependencies
Stdlib only.
