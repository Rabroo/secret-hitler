# Spec: Predicted Role Updates (Heuristic)

## Goal
When a policy is enacted, public information becomes available: who was the President, who was the Chancellor, what did they enact. Liberals don't know the deck draw — only the result — so the most they can do is update their *guess* about whether each gov member is Liberal or Fascist.

This spec defines a **simple, observable heuristic**. It is intentionally not LLM-driven (see "Out of scope"). The goal at this stage is to make `predicted_roles` *change over a game* so scenario testing surfaces something interesting; richer reasoning comes later.

## Inputs / Outputs
**Inputs**
- `state: GameState` — needed only for the player roster.
- `personalities: dict[int, Personality]` — mutated in place.
- `leg: LegislativeSessionResult` — what was enacted this round.
- `president: Player`, `chancellor: Player` — the round's gov.

**Output**
- None (mutates `personalities`).

## Update rule (5-player baseline)

After each enacted policy:

| Viewer role                          | Update applied to *each* of {president, chancellor}             |
| ------------------------------------ | --------------------------------------------------------------- |
| **Liberal**                          | Enacted Liberal: `+0.2` toward `+1.0`. Enacted Fascist: `-0.3` toward `-1.0`. |
| **Fascist / Hitler**                 | No-op — they already know the truth; values stay pinned.         |
| **Self** (viewer is in the gov)      | No-op — you don't update your prediction of yourself.            |

Always clamped to `[-1.0, +1.0]` after the update.

The asymmetry (`+0.2` vs `-0.3`) reflects the fact that an enacted Fascist policy is a stronger signal in real Secret Hitler — Liberals fall back hard when a Fascist policy goes through, but mildly trust a Liberal-enacting government because the deck composition (11 F vs 6 L) makes Liberal enactions sometimes lucky.

## Heuristic vs LLM-driven (current state)
The heuristic in this spec is **superseded by the LLM-driven update** described in `specs/discussion.md` whenever the discussion phase runs (the default).

- With discussion on (default): each Liberal sees the round's statements and decides a fresh `predicted_roles` map themselves; the heuristic is bypassed.
- With `--no-discussion`: this heuristic still runs as the cheap, deterministic fallback (no API calls, no statements).

The heuristic stays in the codebase for that fallback path and for free random-mode runs.

## Edge cases
- Election failed → no legislative session → no update.
- Viewer is a dead Liberal → still updates (they observe the public game state even if they can't act).
- Hitler / Fascist viewers' predicted_roles never change — they're frozen at the seeded values forever (correct; they already know).

## Trigger point
The runner calls `update_predicted_roles_after_session(...)` immediately after `legislative_session(...)` returns and *before* the dashboard renders the round, so the dashboard reflects the post-update state.

## Out of scope
- LLM-driven updates (next iteration).
- Updates from voting patterns alone (without a policy enaction).
- Updates from presidential power outcomes (investigate, peek) — those don't exist yet.

## Dependencies
Stdlib only.
