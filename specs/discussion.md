# Spec: Discussion Round + LLM-Driven Predicted-Role Updates

## Goal
After every enacted policy, run a discussion phase that does two things:

1. **Statements** — every alive player makes one short public statement.
2. **Belief updates** — every Liberal then privately revises their `predicted_roles` map for the other players, using all the public information (history + this round's statements). Fascist team viewers do not update; they already know the truth at 5p.

The LLM-driven belief update **replaces** the heuristic in `update_predicted_roles_after_session`. The heuristic stays in the codebase for `--no-discussion` runs (a deterministic, free fallback) but is bypassed when the discussion phase is on.

## Phases within a round

Old order:
```
nominate -> vote -> [if pass] legislative session -> heuristic role update -> append history
```

New order:
```
nominate -> vote -> [if pass] legislative session
                              -> discussion (parallel statements, then LLM role updates)
                              -> append history
```

If the election failed, no discussion. If `--no-discussion`, fall back to the old heuristic update.

## Statement collection (3-phase: gov sequential, bystanders parallel)

Three phases per discussion round:

1. **President speaks first.** No prior statements visible. They go on record explaining (or lying about) their draw and discard before anyone else has weighed in.
2. **Chancellor speaks second.** Sees the President's statement in their prompt. They can corroborate, contradict, or add detail — knowing the President has already committed to a story.
3. **Bystanders speak in parallel.** Each non-government living player makes their statement seeing Pres + Chan (snapshot before phase 3 starts) but **not** each other's. This avoids "first bystander advantage" where later speakers parrot earlier ones.

This produces a more natural conversation flow: the gov has to defend itself first; bystanders react.

### Decision contract
```python
def make_statement(
    self,
    enacted: Policy,
    drawn_hand: Optional[list[Policy]],     # 3 cards (President only)
    chancellor_hand: Optional[list[Policy]], # 2 cards (Chancellor only)
) -> Statement: ...
```

Returns a `Statement(player_id, text, reasoning)`. `text` is what's broadcast publicly; `reasoning` is the model's private rationale shown only in the operator dashboard.

### Statement prompt
User message:
```
The legislative session is complete:
  Government:  President P{pres_id} + Chancellor P{chan_id}
  Enacted:     {LIBERAL|FASCIST}
  Tally now:   L=N F=N

[If President:] You drew (privately): [LIBERAL, FASCIST, LIBERAL]. You discarded [FASCIST].
[If Chancellor:] You received: [LIBERAL, FASCIST]. You enacted [LIBERAL].

Make ONE public statement to the table (1-2 sentences). You may lie.
Reply as JSON: {"reasoning": "<short>", "statement": "<your public message>"}
```

## LLM-driven predicted-role update (Liberals only)

After all statements are revealed, each **Liberal** is asked to revise their predicted_roles. Fascists/Hitler skip — their values are pinned at known truth at 5p.

### Decision contract
```python
def update_predicted_roles(
    self,
    statements_this_round: list[Statement],
) -> dict[int, float]: ...
```

Returns the *new* full `predicted_roles` map for every other living player, each in `[-1, +1]`. The agent stores this on `self.personality.predicted_roles` (for LLMAgent) and the runner reads it when rendering the dashboard.

### Update prompt
User message:
```
You just observed Round {n} unfold. Use everything in GAME HISTORY (above)
plus the statements made this round to revise your predicted_roles for every
other player.

Current predicted_roles:
  P2: +0.20
  P3: -0.10
  P4: +0.40
  P5: +0.00

Statements this round:
  P1: "I drew clean — three liberals."
  P2: "P1's claim is consistent."
  P3: "Fishy. The deck is heavy fascist."
  P4: "Trust no one yet."
  P5: "P3 is paranoid."

Reply as JSON:
{
  "reasoning": "<one short sentence>",
  "predicted_roles": {"2": +0.30, "3": -0.40, "4": +0.30, "5": -0.10}
}
Each value in [-1, +1]. +1 = predicted Liberal, -1 = predicted Fascist team.
```

Parsing rules:
- Keys must be alive player IDs other than self. Unknown keys ignored.
- Values clamped to `[-1, +1]`.
- Missing keys → preserve previous value (treated as "no change").
- Two-attempt retry on bad JSON, then fall back to previous values.

## CLI flag

`--no-discussion` (default off — discussion is on by default at 5p).

When set:
- Skip statement collection entirely.
- Use the heuristic `update_predicted_roles_after_session` instead.

## Data shape (already added to game.py)

```python
@dataclass
class Statement:
    player_id: int
    text: str
    reasoning: str = ""

# RoundEvent gains:
statements: list[Statement] = field(default_factory=list)
```

## History rendering

`format_history()` appends a `Statements:` block beneath the round line:
```
- Round 3: Pres P3 + Chan P4 ELECTED 4-1. Enacted FASCIST. Tally L=2 F=1.
    Statements:
      P1: "I had no Liberal in my draw — that was forced."
      P2: "Plausible. Pass."
      P3: "P4 didn't fight hard enough."
      P4: "What was I supposed to do with FF?"
      P5: "P1 has been in two F-enacting governments now."
```

## Dashboard

A new section between `POLICY DECK` and `PLAYERS`:
```
DISCUSSION
  P1 (LIBERAL):  "..."
  P2 (FASCIST):  "..."
  P3 (HITLER):   "..."
  P4 (LIBERAL):  "..."
  P5 (LIBERAL):  "..."
```

Per-player blocks in the `PLAYERS` section also gain a `Statement reasoning:` line so the operator can see the *private* rationale behind each public message.

## Cost

Per enacted round, +8 LLM calls at 5 players (5 statements + 3 Liberal updates). At ~700 tokens per call, ~6k extra tokens per round. A 12-round game with 8 enactions → ~50k extra tokens → ~$0.10–0.20 on `gpt-5-mini`. The `--token-budget` flag still hard-gates this — once exhausted, statement and update calls fall back to placeholders / previous values.

## Out of scope
- Multiple turns of back-and-forth in a single round.
- LLM updates on failed-election rounds (we still skip discussion entirely there).
- Targeted accusations as a separate game-state field.
- Persisting statements / belief updates across game restarts.

## Dependencies
Stdlib only.
