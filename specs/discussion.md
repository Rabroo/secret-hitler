# Spec: Discussion Round

## Goal
After each successful legislative session, every alive player makes one public statement before the next round. President can claim what they drew; Chancellor can claim what they were given; others can comment, accuse, or deflect. Statements are public, visible to everyone (including future LLM prompts), and may be lies.

The discussion is what makes Secret Hitler a game of social deduction — without it the LLM agents only see numeric tallies.

## When it runs
- Only after a **successful** election + legislative session (i.e., a policy was actually enacted that round).
- Skipped after failed elections.
- Skipped once `state.winner` is set (game over).

## Order
Statements are collected in **seat order** (Player 1, then 2, then 3, ...). Each speaker sees the statements made *earlier in the same round* in their prompt — Player 3 hears P1 and P2 before speaking.

This isn't perfectly faithful to real-time table talk (which is freeform overlap) but it's a clean approximation and lets later speakers react to earlier ones.

## Decision contract

```python
def make_statement(
    self,
    enacted: Policy,
    drawn_hand: Optional[list[Policy]],     # the 3 cards (President only)
    chancellor_hand: Optional[list[Policy]], # the 2 cards (Chancellor only)
    prior_statements_this_round: list[Statement],
) -> Statement: ...
```

- `drawn_hand` is `None` for everyone except the President.
- `chancellor_hand` is `None` for everyone except the Chancellor.
- `prior_statements_this_round` accumulates as we walk the seats.

Returns a `Statement(player_id, text, reasoning)`. The `text` is what's broadcast publicly; `reasoning` is the model's private rationale (operator-only, shown in the dashboard).

## Data shape

```python
@dataclass
class Statement:
    player_id: int
    text: str          # public
    reasoning: str     # operator-only

# RoundEvent gains:
statements: list[Statement] = field(default_factory=list)
```

## LLM prompt
A new `statement_prompt(...)` in `src/prompts.py`. The prompt structure:

System message: same as other decisions (role, predicted_roles, GAME HISTORY, role hint). Importantly, `GAME HISTORY` already contains *past rounds'* statements when the prompt is built for a later round.

User message:
```
The legislative session is complete:
  - Government: President P{pres_id} + Chancellor P{chan_id}
  - Enacted: {LIBERAL|FASCIST}
  - Tally now: L=N F=N

[If President:] You drew (privately): [LIBERAL, FASCIST, LIBERAL]. You discarded [FASCIST].
[If Chancellor:] You received from the President: [LIBERAL, FASCIST]. You enacted [LIBERAL].

Statements made earlier this round:
- P1: "I drew clean — three Liberals."
- P2: "P1's claim is consistent with the enaction."

Make ONE public statement to the table. You may lie or tell the truth.
Reply as JSON: {"reasoning": "<one short sentence>", "statement": "<your public message>"}
```

If no prior statements: omit that block.

## History integration
`format_history()` is extended so each round's history line shows statements beneath the gov/enaction line:
```
- Round 3: Pres P3 + Chan P4 ELECTED 4-1. Enacted FASCIST. Tally L=2 F=1.
    Statements:
      P1: "I drew FFF — they had no Liberal to give me."
      P2: "Fishy. P1 had a chance to discard a Fascist last round and didn't."
      ...
```

## Cost note
Each enacted round adds **N alive LLM calls** (5 at start of game). At ~700 tokens per call (system + user + reasoning + statement), a 10-round game with 6 enactions adds ~30 calls / ~20k tokens. Roughly $0.05–0.10 on `gpt-5-mini`.

The runner's existing `--token-budget` flag still gates this — once the budget is exhausted, statement-making falls back to a `(silent)` placeholder for that player and the rest of the game.

## CLI
A new flag `--no-discussion` to skip the phase if the operator just wants the mechanical game (cheap; useful for runs that compare deck/voting outcomes without speech). Default: discussion **on**.

## Out of scope
- LLM-driven numerical updates to `predicted_roles` after each statement (V2; expensive).
- Multi-turn back-and-forth in a single round.
- Targeted accusations as a separate game-state field (statements are free text only).
- Persisting statements across `start_game` invocations.

## Dependencies
Stdlib only. No new packages.
