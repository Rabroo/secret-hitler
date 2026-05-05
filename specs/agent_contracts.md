# Spec: Player Agent Contracts (LLM Integration Seam)

## Goal
Define the input/output shapes of every per-player decision in the engine. These are the seams where each LLM-backed player plugs in. The engine never calls an LLM directly — it calls a typed callback, and a player's "brain" (LLM, scripted heuristic, random stub) sits behind that callback.

Keeping these contracts narrow and explicit lets us:
- Swap stubs for LLMs without touching engine logic.
- Test the engine deterministically (random stubs, fixed seeds).
- Give each player its own brain when LLMs land (per-player callback or a `PlayerAgent` protocol).

## Decision: Chancellor Nomination
- **Caller:** the President during the nomination phase.
- **Callback:**
  `choose_fn(president: Player, eligible_candidates: list[Player]) -> Player`
- **Input:** the President themselves, plus the list of players the engine has pre-filtered to be eligible (alive, not the President, not term-limited).
- **Output:** exactly one `Player` from `eligible_candidates`.
- **Engine guarantees:** every player in `eligible_candidates` is a legal nomination. Returning anything else raises `ValueError`.

## Decision: Chancellor Vote
- **Caller:** every alive player during the voting phase.
- **Callback:**
  `vote_fn(voter: Player, president: Player, nominee: Player) -> bool`
- **Input:** the voter, plus the proposed government (President + Nominee).
- **Output:** `True` for Ja, `False` for Nein.
- **Engine guarantees:** dead players are not asked to vote; the nominee is alive.

## Decision: Policy Discard (President)
- **Caller:** the President during the legislative session.
- **Callback:** `discard_fn(president: Player, hand: list[Policy]) -> Policy`
- **Input:** the 3 policies just drawn off the deck.
- **Output:** one of the 3 policies, to be discarded. The remaining 2 go to the Chancellor.
- **Engine guarantees:** the hand has exactly 3 cards. The returned policy must be present in the hand (engine checks identity by *count*, so duplicates are handled correctly).
- **LLMAgent variant:** uses an indexed JSON contract — `{"reasoning": "...", "discard_index": 0|1|2}` — so duplicate Fascist policies are unambiguous.

## Decision: Policy Enact (Chancellor)
- **Caller:** the Chancellor, immediately after the President's discard.
- **Callback:** `enact_fn(chancellor: Player, hand: list[Policy]) -> Policy`
- **Input:** the 2 policies the President passed.
- **Output:** the policy to enact. The other is discarded.
- **Engine guarantees:** the hand has exactly 2 cards. The returned policy must be present in the hand.
- **LLMAgent variant:** `{"reasoning": "...", "enact_index": 0|1}`.

## Future decisions (not yet implemented)
| Phase                    | Callback signature                                           | Input                                  | Output                              |
| ------------------------ | ------------------------------------------------------------ | -------------------------------------- | ----------------------------------- |
| Investigate (power)      | `investigate_fn(president, targets: list[Player]) -> Player` | living non-self players                | 1 player to inspect                 |
| Special election (power) | `special_fn(president, targets: list[Player]) -> Player`     | living non-self players                | next president                      |
| Execution (power)        | `execute_fn(president, targets: list[Player]) -> Player`     | living non-self players                | player to kill                      |
| Veto (Chancellor + Pres) | `veto_fn(player, hand) -> bool`                              | 2 policies                             | True to veto, False to enact one    |

## Player personality (planned, not yet wired)
Each player will eventually carry:
- **Desire vector** — preference for Liberal vs. Fascist outcomes, scored `-1.0` (strongly Liberal-aligned) to `+1.0` (strongly Fascist-aligned). Set deterministically from `Role` plus optional noise.
- **Opinion map** — `{other_player_id: float in [-1, 1]}` representing trust/suspicion of every other player. Updated from public events (votes, policy outcomes, claims).

These feed the LLM prompt for each decision callback, so the LLM has a consistent personality across rounds.

## Reference implementations for stubs
- **Random stub:** seeded `random.Random` to keep tests deterministic.
- **Heuristic stub:** simple "always vote yes" / "never trust fascist-suspect" baselines for sanity-checking logic before LLM costs are incurred.

## Out of scope here
The actual LLM glue (prompt templates, OpenAI client, response parsing) lives in a separate spec when we wire the API in. This document only defines the *engine-facing* shape.
