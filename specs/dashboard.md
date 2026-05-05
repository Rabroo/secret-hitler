# Spec: Per-Round Dashboard (LLM Reasoning + Opinions)

## Goal
Give the operator a per-round view of *why* each player made the choices they made and *what they currently believe* about the other players. Operator-only (the LLM agents themselves still see only their own role + opinions in their prompts).

This relies on the LLM emitting reasoning alongside its decision. We switch from plain-text replies (`"3"`, `"ja"`) to JSON replies (`{"reasoning": "...", "choice": 3}`, `{"reasoning": "...", "vote": "ja"}`). Each agent stores its last reasoning, and the dashboard reads it.

## Inputs / Outputs
**Inputs**
- `agents: dict[int, PlayerAgent]` — built once at game start.
- `players: list[Player]` — for the operator-side role labels.
- The just-finished round number, plus the President + Nominee + ElectionResult (already produced by the engine).

**Output**
- A formatted text block printed to stdout when `--dashboard` is on.

## CLI
- New flag `--dashboard` on the `start` subcommand.
- Default: **off** (so existing terminal/test behaviour is unchanged).
- Implied by `--agents llm` only if the user opts in — we don't auto-enable it because reasoning increases output token spend.

## Reasoning capture
- LLM prompts now request JSON. OpenAI's JSON mode is enabled (`response_format={"type": "json_object"}`) so the response is guaranteed to parse as JSON.
- For nomination: `{"reasoning": "<short string>", "choice": <player id int>}`
- For voting: `{"reasoning": "<short string>", "vote": "ja" | "nein"}`
- Parse failures (missing key, wrong type, illegal choice) follow the existing retry-once-then-fall-back-to-random behaviour. If we fall back, reasoning is set to `"(LLM parse failure — random fallback)"`.
- `RandomAgent` populates reasoning fields with `"(random)"` so the dashboard renders consistently in both modes.

## Dashboard format
After each round, when enabled:

```
============================================================
DASHBOARD — Round 1
============================================================
Player 1 (FASCIST)  *President*
  Nominate: Player 2
    "I trust 2 (my Hitler ally) most. ..."
  Vote: ja
    "Voting in my own government."
  Opinions: 2:+1.00  3:-1.00  4:-1.00  5:-1.00

Player 2 (HITLER)  *Chancellor nominee*
  Vote: ja
    "Voting in my own government."
  Opinions: 1:+1.00  3:-1.00  4:-1.00  5:-1.00

Player 3 (LIBERAL)
  Vote: ja
    "No info; voting ja to start the game."
  Opinions: 1:0.00  2:0.00  4:0.00  5:0.00
...
```

- Players are listed in seat order.
- Tags: `*President*`, `*Chancellor nominee*` decorate the relevant seats.
- Dead players are still shown but with a `(dead)` tag and no decisions for the round.
- `Nominate:` line only appears for the President.
- `Vote:` line appears for every alive player.
- `Opinions:` is always shown (current snapshot).
- Reasoning text is shown indented and in quotes.

## Out of scope
- **Opinion updates over time.** Opinions are still static (initial values from `specs/personality.md`). Every round currently shows the same opinions. Building event-driven opinion updates is a separate spec.
- LLM-driven free-form discussion or speech between players.
- Saving the dashboard to a file (stdout only for now).

## Dependencies
No new packages. JSON mode is supported by the OpenAI SDK we already use.
