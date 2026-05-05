# Spec: LLM Prompts (Centralised)

## Goal
All LLM-facing strings live in **one place**: `src/prompts.py`. The agent module imports prompt builders from there. This is purely an organisation change — same prompts, easier to find and tweak.

Why: the system prompt, nominate prompt, vote prompt, discard prompt, and enact prompt were buried as private methods inside `LLMAgent`. Hard to find, hard to A/B-test, hard to spot-check terminology drift.

## Module shape

`src/prompts.py` exports five pure functions, each returning a string:

```python
def system_prompt(player: Player, personality: Personality, all_players: list[Player]) -> str: ...
def nominate_prompt(eligible: list[Player]) -> str: ...
def vote_prompt(president: Player, nominee: Player) -> str: ...
def discard_prompt(hand: list[Policy]) -> str: ...
def enact_prompt(hand: list[Policy]) -> str: ...
```

Plus a small helper for the retry message:

```python
def retry_prompt(original: str, reason: str) -> str: ...
```

Every prompt template lives at module scope as a multi-line string constant so they're easy to read and edit:

```python
_SYSTEM_TEMPLATE = """You are Player {player_id} in a 5-player game of Secret Hitler.
Your role: {role}.
...
"""
```

## What the prompts say

### System prompt
- Role and player id.
- Desire scalar with sign convention spelled out.
- `predicted_roles` table — labelled "your predictions of other players' roles" (was: "trust").
- Public roster.
- Win conditions summary.
- Strategic guidance: short, role-aware bullet list.
- "You must reply with valid JSON only."

### Decision prompts
Each decision prompt is independent of the others — it states the situation and the required JSON shape. No reliance on the system prompt for the JSON schema (so a future model that ignores the system message still gets it right).

## Out of scope
- Few-shot examples (good follow-up).
- Per-round game-state context (round number, recent enactions, voting history). Currently every decision call re-builds the prompt from scratch with no history; adding history is a separate spec.

## Dependencies
Imports `Player`, `Role`, `Personality`, `Policy` from existing modules. No new packages.
