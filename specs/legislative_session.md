# Spec: Legislative Session (Policy Deck + Pres/Chancellor Pass)

## Goal
After a successful Chancellor election, the elected government enacts one policy:

1. President draws 3 policies off the deck (privately).
2. President discards 1; the other 2 are passed to the Chancellor.
3. Chancellor enacts 1; the other is discarded.
4. The enacted policy is added to the public tally.
5. Discarded policies (both President's and Chancellor's) go to the discard pile.

Only the President and Chancellor see what was drawn / passed — the rest of the table sees only the enacted policy. This privacy is what gives the game its bluffing dimension; the player-facing prompts must respect it.

Adds infrastructure for the win conditions (5 Liberal / 6 Fascist), but does not yet check them — that's the next spec.

## Inputs / Outputs

**Module: PolicyDeck (new)**
- `Policy` enum with `LIBERAL` and `FASCIST`.
- Deck composition: **6 Liberal + 11 Fascist = 17 cards** (rulebook).
- `PolicyDeck.draw(n: int) -> list[Policy]` — pops n from the top.
- `PolicyDeck.discard(policies: list[Policy])` — adds to the discard pile.
- **Reshuffle rule:** if there are fewer than 3 cards in the draw pile when `draw(3)` is called, the discard pile is shuffled back in *before* drawing. (Rulebook: this happens between rounds, but checking at draw-time is functionally equivalent for our flow.)
- Seeded RNG for deterministic tests.

**Function: `legislative_session(state, deck, president, chancellor, discard_fn, enact_fn)`**
- Draws 3 from the deck.
- Calls `discard_fn(president, hand_of_3) -> Policy` to pick the discard.
- Calls `enact_fn(chancellor, hand_of_2) -> Policy` to pick the enaction.
- Mutates `state.liberal_policies_enacted` / `state.fascist_policies_enacted`.
- Sends both discards to `deck.discard(...)`.
- Returns a `LegislativeSessionResult` with the full sequence (drawn, discarded-by-pres, handed-to-chancellor, enacted, discarded-by-chancellor) — for the operator-side dashboard.

Both decision callbacks must return a `Policy` value that is *present in the hand they were given*. If they return something else (or a duplicate of an already-removed copy when the hand has duplicates), the engine raises `ValueError`. (LLMAgent uses an indexed protocol — see `specs/agent_contracts.md` — to avoid the duplicate-policy ambiguity.)

## State changes
Two new fields on `GameState`:
- `liberal_policies_enacted: int = 0`
- `fascist_policies_enacted: int = 0`

Tally is incremented when the legislative session finishes. Win conditions (`>=5 L` Liberal win, `>=6 F` Fascist win, Hitler-elected-after-3-F Fascist win) are **not** checked here — that's a separate phase.

## Privacy / dashboard
- President's hand of 3 → only visible to the President's own LLM prompt and to the operator-side dashboard (operator block, marked OPERATOR-ONLY).
- Chancellor's hand of 2 → same.
- **Round summary line** (already public): now also prints the enacted policy and the running tally, e.g. `Enacted: FASCIST. Tally: L=1 F=2.`
- The **dashboard** picks up reasoning fields `last_discard_reasoning` / `last_enact_reasoning` from each agent. Other players' agents see nothing about hands — their `last_discard_reasoning` will be empty unless they were the President this round.

## Edge cases
- **Discard pile reshuffle** mid-game: if draw pile has 1 or 2 cards when 3 are needed, shuffle in the discard pile, then draw.
- **Election failed** → no legislative session; `last_elected_*` and tally untouched. Presidency advances as before.
- **`discard_fn` returns a Policy not in the hand** → `ValueError`.
- **`enact_fn` returns a Policy not in the hand** → `ValueError`.
- **Determinism**: same `seed` → same deck order, same draws.

## Out of scope (next spec)
- **Win conditions** (5 L Liberal win, 6 F Fascist win, Hitler-elected-after-3-F Fascist win, Liberal-execute-Hitler win). Tally is being built precisely so we can add these next.
- **Presidential powers** (investigate, special election, peek, execute) — triggered at certain Fascist policy counts.
- **Veto power** (Chancellor + President both refuse to enact, after 5 F policies).
- **Election tracker** (3 failed elections → top policy auto-enacts).
- **Policy claim / accusation flow** (player speech alleging what was passed).

## Dependencies
Stdlib only (`enum`, `random`, `dataclasses`). No new packages.
