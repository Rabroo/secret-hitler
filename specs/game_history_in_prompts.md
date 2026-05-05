# Spec: Game History in Prompts + Explicit Team Identity

## Goal
Two related fixes to LLM agent reasoning that the operator surfaced:

1. **Agents don't know what happened in past rounds.** Every LLM call is contextless — even at round 5 the model says "no information yet" because past rounds genuinely aren't in its prompt. Solution: maintain a public **game history** and inject it into the system prompt every call.

2. **Hitler isn't playing as Fascist team.** Hitler reads `Player 5: -1.00` in `predicted_roles` and interprets the negative number as "suspect" rather than "known ally." The team relationship needs to be stated in plain English, not encoded only as a number.

## Inputs / Outputs

### `RoundEvent` (new dataclass)
Captures the **public** facts of one round — what every player at the table sees:
```python
@dataclass
class RoundEvent:
    round_num: int
    president_id: int
    chancellor_id: int
    election_passed: bool
    votes: dict[int, bool]            # player_id -> ja/nein
    enacted: Optional[Policy]         # None if election failed
    liberal_tally: int                # tally AFTER this round
    fascist_tally: int
```

### `GameState.history: list[RoundEvent]` (new field)
Appended after every round, regardless of whether the election passed (failed elections still convey information — who voted nein, who supported whom).

### Prompt format
The system prompt now contains a `GAME HISTORY` section between the personality block and the rules summary:

```
GAME HISTORY (public — every player sees this):
- Round 1: Pres P1 + Chan P3 ELECTED 5-0. Enacted LIBERAL. Tally L=1 F=0.
- Round 2: Pres P2 + Chan P1 ELECTED 5-0. Enacted LIBERAL. Tally L=2 F=0.
- Round 3: Pres P3 + Chan P4 ELECTED 5-0. Enacted FASCIST. Tally L=2 F=1.
- Round 4: Pres P4 + Chan P2 ELECTED 4-1 (P5 nein). Enacted LIBERAL. Tally L=3 F=1.
Current tally: L=3 F=1.
```

If `history` is empty (round 1) the section reads `GAME HISTORY: (no rounds completed yet — this is round 1).`

Failed-election rows look like:
```
- Round 6: Pres P3 nominated P4. REJECTED 2-3 (P1 P3 ja; P2 P4 P5 nein).
```

## Team identity in the system prompt

For `LLMAgent` whose role is FASCIST or HITLER, the system prompt gains a top line:
```
Your Fascist teammate is Player 5.
You two win together — enact 6 Fascist policies, OR get Hitler elected Chancellor at F≥3. Quietly support each other's governments. Don't openly nominate or trust them in public — Liberals will spot the pattern.
```

For Liberal viewers, no such line is added (they have no team to identify).

The teammate is computed from `all_players` and the viewer's own role at construction time — at 5p, Hitler's teammate is the Fascist and vice versa.

## Edge cases
- `history` is empty in round 1 — special-case message.
- Failed elections still get a row.
- Dead voters absent from `votes` is fine (they don't vote).
- The `Tally:` line on a failed row shows the *carried-over* tally (no enaction).
- 7+ player rules: at 7+ Hitler doesn't know who the Fascists are. The teammate-identity line should not be added then. Guard with the `num_players == 5` check we already have.

## Out of scope
- Compressing long history at high round counts (we only ever play ~12 rounds before someone wins, fine).
- Including secret/private context (drawn cards, role reveals from powers) — those go in role-specific sections of the user prompt for that decision.
- Making history persist across `start_game` invocations (game restarts always start fresh).

## Dependencies
Stdlib only.
