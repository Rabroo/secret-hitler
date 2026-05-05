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

## Future decisions (not yet implemented)
These rows will be filled in as future phases land. Each will follow the same "engine pre-filters legal moves, callback returns one of them" shape:

| Phase                     | Callback signature                                           | Input                                  | Output                              |
| ------------------------- | ------------------------------------------------------------ | -------------------------------------- | ----------------------------------- |
| Policy discard (Pres)     | `discard_fn(president, hand: list[Policy]) -> Policy`        | 3 policies                             | 1 policy to discard                 |
| Policy enact (Chancellor) | `enact_fn(chancellor, hand: list[Policy]) -> Policy`         | 2 policies                             | 1 policy to enact                   |
| Investigate (power)       | `investigate_fn(president, targets: list[Player]) -> Player` | living non-self players                | 1 player to inspect                 |
| Special election (power)  | `special_fn(president, targets: list[Player]) -> Player`     | living non-self players                | next president                      |
| Execution (power)         | `execute_fn(president, targets: list[Player]) -> Player`     | living non-self players                | player to kill                      |

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
