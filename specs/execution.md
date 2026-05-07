# Spec: Execution Power (Presidential Power at F=4 and F=5)

## Goal
At 5 players, the rulebook grants the President a power to execute a player when the **4th** and the **5th** Fascist policy is enacted via a normal legislative session. Executed players are removed from the game. If the executed player is Hitler, **Liberals win immediately** — that's the fourth win condition we've been missing.

## Triggers
- Power fires immediately AFTER a successful legislative session in which `state.fascist_policies_enacted` becomes **4** or **5**.
- Power does NOT fire from a chaos enaction (per rulebook: "the President does not get a power for the policy enacted from chaos").
- Power does NOT fire if the round already declared a winner (e.g. Hitler-Chancellor-at-F≥3 win which is checked before the legislative session, or a Fascist tally win at F=6).

## Decision contract
New callback:
```python
ExecuteFn = Callable[[Player, list[Player]], Player]
# (president, alive_non_self_players) -> chosen_target
```

Engine guarantees the eligibility list is alive players excluding the President. Returning anyone outside that list raises `ValueError`.

## Engine helper
`src/game.py` gains:
```python
def execute_player(state: GameState, president: Player, execute_fn: ExecuteFn) -> Player:
    """Run the execution power. Returns the executed player.

    Caller is responsible for the win-condition check (executing Hitler ends
    the game).
    """
```
- Sets `target.alive = False`.
- Returns the target so the runner can log + render.

## Win condition
Add to `check_winner`:
- If any `Role.HITLER` player has `alive == False` → return `Faction.LIBERAL`. This check runs first so it overrides everything else.

`state.winning_reason` becomes `"Liberals executed Hitler."`.

## State / RoundEvent
- `RoundEvent.executed_player_id: Optional[int] = None` — set on rounds where the power fired.
- `Player.alive` already exists; we just flip it.

Subsequent rounds already handle dead players correctly:
- `advance_presidency` skips dead.
- `eligible_chancellors` excludes dead.
- `vote_chancellor` only collects votes from alive players.
- LLMAgents that are dead simply are not called for nominate/vote/discard/enact/statement (the runner already iterates `players` and respects `p.alive`).

## Runner integration
After the existing tally-win check on a successful enaction:

```python
if state.fascist_policies_enacted in (4, 5) and state.winner is None and leg is not None:
    target = execute_player(state, president, execute)
    executed_player_id = target.id
    winner = check_winner(state)
    if winner is Faction.LIBERAL:
        state.winner = winner
        state.winning_reason = "Liberals executed Hitler."
    # No state.winner change if Hitler wasn't executed; game continues.
```

The new RoundEvent fields are populated when appended.

## Dashboard / round-line output
Round line gains an extra line when execution fired:
```
Executed: Player {id} (was {role}).
```
The dashboard `GOVERNMENT` block also gains an `Executed:` line when applicable.

The President's reasoning for the execution surfaces in the per-player block:
```
Player 1 (LIBERAL)  [President]
  Execute -> Player 3: "P3 has been in two F-enacting governments..."
```

## Prompts

### System prompt rules
Add one line to the rules summary:
> Presidential powers (5 players): when the 4th and 5th Fascist policies are enacted via a normal session (not chaos), the President executes a player. If Hitler is executed, Liberals win immediately.

### `execute_prompt(targets)`
```
You must execute a player. The Fascist policy track has reached {N} —
this is a Presidential power. Eligible targets (alive, not yourself):
[{ids}]
If you execute Hitler, Liberals win the game immediately.
Reply as JSON: {"reasoning": "<one short sentence>", "execute_id": <player id>}
```

Same JSON / retry / fallback pattern as the other LLMAgent decisions. RandomAgent picks a random alive non-self target.

## Edge cases
- Power fires only on enacted policies, not on chaos.
- If the President themselves is the only alive eligible target (impossible in 5p before round 4+), engine raises rather than executing self.
- Executing a player removes them from `eligible_chancellors` and `advance_presidency`. The round following an execution starts with `advance_presidency` skipping the dead seat.
- Once Hitler is dead, no further chancellor election can win for Fascists via Hitler-as-Chancellor (Hitler can't be nominated). The other Fascist still pushes for the 6-Fascist tally win.
- Chaos at F=3 (rare, but possible) bumps Fascist count to 4 without granting the F=4 execution. Verified by test.

## Tests
- `execute_player` flips `alive` and returns the target.
- `check_winner` returns `Faction.LIBERAL` when Hitler is dead, regardless of tally.
- LLMAgent.execute_player parses JSON, retries on bad reply, falls back.
- RandomAgent.execute_player picks an alive non-self target.
- Runner: forced layout + stacked deck producing F=4 enaction triggers execution; if Hitler is hit, game ends with Liberal win banner.
- Runner: chaos at F=4 (3 failed elections + draw=F at F=3) does NOT trigger execution.
- Runner: F=5 also triggers execution (a player executed at F=4 may have been killed already; the F=5 power picks from remaining alive non-self).
- Subsequent rounds: dead player excluded from votes, nominations, presidency.

## Out of scope (later)
- Policy peek at F=3 (different power, no kill, just info).
- Veto power activation at F=5.
- Investigation power (only at 9-10 players).
- Special election (only at 7-10 players).

## Dependencies
Stdlib only.
