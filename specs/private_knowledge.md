# Spec: Per-Player Private Knowledge

## Goal
Carry forward each player's *private* observations across rounds so they can make grounded accusations in discussion (and in any future call that uses the system prompt).

The motivating bug: a Liberal President discards a Fascist and passes `[L, F]` to a Fascist Chancellor. The Chancellor enacts the Fascist. The Liberal President *should* be able to confidently say "you had a Liberal and picked Fascist anyway." But under the current design that fact lives in `last_discard_reasoning` of the President's previous call, which doesn't survive the next system prompt build. The agent forgets.

## Data shape
Add to `LLMAgent` (and the `PlayerAgent` protocol):
```python
private_log: list[str] = field(default_factory=list)
```

Free-text lines, appended by the runner after each decision the player made. One line per private observation.

## Lines the runner appends

**After President's discard:**
```
Round {N}: as President I drew [{a}, {b}, {c}], discarded {x}, passed [{y}, {z}] to Chancellor P{chan_id}.
```

**After Chancellor's enact:**
```
Round {N}: as Chancellor I received [{y}, {z}] from President P{pres_id}, enacted {e} (discarded {d}).
```

That's it for now. Future powers (investigate, peek, special election) will add their own private lines as they're built.

## Prompt integration
`system_prompt(...)` gains an optional `private_log` parameter; when non-empty it renders a `PRIVATE KNOWLEDGE` section between `Public roster` and `GAME HISTORY`:
```
PRIVATE KNOWLEDGE (visible only to you, never to other players):
- Round 3: as President I drew [FASCIST, FASCIST, LIBERAL], discarded FASCIST, passed [FASCIST, LIBERAL] to Chancellor P3.
- Round 5: as Chancellor I received [FASCIST, LIBERAL] from President P2, enacted LIBERAL (discarded FASCIST).
```

If the log is empty, the section is omitted.

## Visibility rules
- Lines added to one agent's `private_log` are *never* shown to any other agent.
- Operator dashboard already exposes the truth via the `POLICY DECK` operator-only block; no new dashboard work needed.
- Random agents do nothing with the log (their nominate/vote/etc. don't read it). The field exists on the protocol so the runner can append uniformly.

## Edge cases
- Failed elections → no private log entries (no draw happened).
- Once the game ends (`state.winner` set), no further entries.
- A `--no-discussion` run still benefits from private knowledge in nominate/vote/discard/enact prompts going forward.

## Out of scope
- Persisting `private_log` across `start_game` invocations.
- LLM access to *other agents'* logs (would defeat the point).
- Compressing the log when it gets long. At 5p with 12 rounds max it stays small.

## Dependencies
Stdlib only.
