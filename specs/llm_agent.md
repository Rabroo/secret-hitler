# Spec: LLM-Backed Player Agent

## Goal
Provide an `LLMAgent` that sits behind the existing nomination and vote callbacks (defined in `specs/agent_contracts.md`) and uses an OpenAI chat model to make decisions. Each agent is owned by exactly one player and receives that player's role + personality at construction. The engine never imports `openai` directly — it only sees the typed callbacks.

## Inputs / Outputs

**Construction**
- `LLMAgent(player, personality, all_players, model, client)`
  - `player: Player` — the agent's own seat (knows its role).
  - `personality: Personality` — desire + opinions (from `specs/personality.md`).
  - `all_players: list[Player]` — public roster for prompts.
  - `model: str` — e.g. `gpt-5-mini`.
  - `client: LLMClient` — thin wrapper over the OpenAI SDK; injectable for tests.

**Decision methods (match the existing engine callbacks)**
- `nominate(eligible: list[Player]) -> Player`
- `vote(president: Player, nominee: Player) -> bool`

## Prompt shape
A single chat completion per decision. System message describes the game rules and the player's identity. User message describes the current decision.

**System (shared per agent, cacheable):**
```
You are Player {id} in a 5-player game of Secret Hitler.
Your role: {ROLE} (Liberal / Fascist / Hitler).
Your alignment desire (-1 Liberal .. +1 Fascist): {desire:+.2f}.
Your initial opinions of other players (-1 distrust .. +1 trust):
  Player 2: {opinion:+.2f}
  Player 3: {opinion:+.2f}
  ...
Public roster: Players 1..5.

Rules summary:
- Liberals win by enacting 5 Liberal policies or executing Hitler.
- Fascists win by enacting 6 Fascist policies or electing Hitler chancellor after 3 fascist policies.
- Be strategic and stay in character. Never reveal your role unless it serves your win condition.
```

**User (per decision):**

For nomination:
```
You are the President this round. Pick a Chancellor from the eligible candidates.
Eligible: [2, 3, 5]
Reply with ONLY the player number (e.g. "3"). No explanation.
```

For voting:
```
The President is Player {pres_id}. They nominated Player {nominee_id} as Chancellor.
Vote ja or nein on this government.
Reply with ONLY one word: "ja" or "nein". No explanation.
```

## Response parsing
- Strip whitespace, lowercase.
- Nomination: extract first integer in the reply; require it to be in `eligible`.
- Vote: must be exactly `ja` or `nein` (allow case-insensitive); anything else fails parsing.

## Failure handling
1. **Parse fail or illegal choice:** retry once with the same prompt plus `"Your previous reply was invalid. Reply with only X."` appended.
2. **Second failure:** fall back to a deterministic default and log a warning to stderr:
   - Nomination: pick the first eligible candidate.
   - Vote: nein (safer for Liberals; fascists can adapt later).
3. **API errors / network:** propagate up — these are user-visible problems, not silent failures.

## Determinism / reproducibility
- The LLM itself is non-deterministic. The `--seed` flag remains useful for role assignment and the random fallback path, but LLM decisions cannot be made bit-exact.
- Tests **never call the live API**. They use a fake `LLMClient` that returns scripted strings.

## Cost controls
- Default model: `gpt-5-mini` (override via `--model`).
- Hard token budget per game (default 50,000); when exceeded, the agent falls back to the random brain for the remainder of the game and prints a warning. Prevents an accidental loop from draining the key.
- `temperature` defaults to `0.7` (some variation between players, not chaos).
- All prompts go through `tiktoken`-style estimated token counting *before* the API call; we add the estimate to the running total. (If tiktoken isn't available, we fall back to `len(text) // 4` — rough but conservative.)

## Module layout
```
src/personality.py   # Personality dataclass + build_personalities()
src/llm_client.py    # OpenAI SDK wrapper, reads OPENAI_API_KEY from .env
src/agents.py        # PlayerAgent protocol, RandomAgent, LLMAgent, adapter to ChooseFn / VoteFn
```

## Runner integration
- New CLI flag `--agents {random,llm}`, default `random` (no API calls).
- New CLI flag `--model` (default `gpt-5-mini`), used only when `--agents llm`.
- New CLI flag `--token-budget` (default 50000).
- `start_game` builds a `dict[player_id, PlayerAgent]`, then constructs `choose_fn` / `vote_fn` adapters from it, then runs the existing loop unchanged.

## Out of scope
- Memory / chat history across rounds (each decision is independent for now).
- LLM-authored speech / public messaging between players.
- Tool use, function calling, or structured outputs (string parsing is enough at this scale).
- Opinion updates from observed events — separate spec when the legislative session lands.

## Dependencies
- `openai` (Python SDK)
- `python-dotenv` (load `.env`)
- `pytest` (existing)
