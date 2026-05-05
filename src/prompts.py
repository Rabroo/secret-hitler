"""Centralised LLM prompt templates.

Every string the LLM sees lives here so it's easy to find, tweak, and
A/B-test. The agent module imports these builders and never composes prompts
inline. See `specs/prompts.md`.
"""

from __future__ import annotations

from src.game import Player, Role
from src.personality import Personality
from src.policies import Policy


# --- system prompt ----------------------------------------------------------

_SYSTEM_TEMPLATE = """You are Player {player_id} in a 5-player game of Secret Hitler.
Your role: {role}.
Your alignment desire (+1 wants Liberal outcomes .. -1 wants Fascist outcomes): {desire:+.2f}.

Your predicted_roles for the other players (+1 = you predict Liberal, -1 = you predict Fascist, 0 = no info):
{predicted_role_lines}

Public roster: {roster}.

Rules summary:
- Liberals win by enacting 5 Liberal policies or executing Hitler.
- Fascists win by enacting 6 Fascist policies, or by electing Hitler as Chancellor after 3 Fascist policies are enacted.
- Be strategic and stay in character. Never reveal your role unless doing so helps you win.{role_hint}

You must reply with valid JSON only."""


_LIBERAL_HINT = (
    "\n- As a Liberal, you start with no information. Use voting and policy "
    "enactions to update your predictions. Don't trust governments that "
    "produce Fascist policies."
)

_FASCIST_HINT = (
    "\n- As a Fascist, you know who the other Fascist team member is. "
    "Don't openly support them — Liberals will spot the pattern. Early-game, "
    "act like a Liberal: vote moderately, claim Liberal policies. Bury your "
    "alignment until you've built cover."
)

_HITLER_HINT = (
    "\n- As Hitler, stay quiet and undercover. Don't seek the Chancellor "
    "seat early — getting elected with 3+ Fascist policies on the board "
    "wins the game for your team, but only after Liberals stop suspecting "
    "you. Mimic Liberal play in early rounds."
)

_ROLE_HINTS = {
    Role.LIBERAL: _LIBERAL_HINT,
    Role.FASCIST: _FASCIST_HINT,
    Role.HITLER: _HITLER_HINT,
}


def system_prompt(
    player: Player, personality: Personality, all_players: list[Player]
) -> str:
    predicted_role_lines = "\n".join(
        f"  Player {pid}: {score:+.2f}"
        for pid, score in sorted(personality.predicted_roles.items())
    )
    roster = ", ".join(f"Player {p.id}" for p in all_players)
    return _SYSTEM_TEMPLATE.format(
        player_id=player.id,
        role=player.role.value.upper(),
        desire=personality.desire,
        predicted_role_lines=predicted_role_lines,
        roster=roster,
        role_hint=_ROLE_HINTS[player.role],
    )


# --- decision prompts -------------------------------------------------------


def nominate_prompt(eligible: list[Player]) -> str:
    ids = [p.id for p in eligible]
    return (
        "You are the President this round. Pick a Chancellor from the "
        "eligible candidates.\n"
        f"Eligible: {ids}\n"
        'Reply as JSON: {"reasoning": "<one short sentence>", '
        '"choice": <player id>}'
    )


def vote_prompt(president: Player, nominee: Player) -> str:
    return (
        f"The President is Player {president.id}. They nominated Player "
        f"{nominee.id} as Chancellor. Vote on this government.\n"
        'Reply as JSON: {"reasoning": "<one short sentence>", '
        '"vote": "ja" | "nein"}'
    )


def discard_prompt(hand: list[Policy]) -> str:
    indexed = ", ".join(f"[{i}] {p.value.upper()}" for i, p in enumerate(hand))
    return (
        "You are the President. You drew 3 policies privately — only you "
        "and the Chancellor (after your discard) will see them.\n"
        f"Hand: {indexed}\n"
        "Pick ONE index to discard. The other 2 go to the Chancellor.\n"
        'Reply as JSON: {"reasoning": "<one short sentence>", '
        '"discard_index": 0 | 1 | 2}'
    )


def enact_prompt(hand: list[Policy]) -> str:
    indexed = ", ".join(f"[{i}] {p.value.upper()}" for i, p in enumerate(hand))
    return (
        "You are the Chancellor. The President passed you 2 policies — "
        "only you have seen these.\n"
        f"Hand: {indexed}\n"
        "Pick ONE index to ENACT. The other is discarded.\n"
        'Reply as JSON: {"reasoning": "<one short sentence>", '
        '"enact_index": 0 | 1}'
    )


def retry_prompt(original_user_prompt: str, reason: str) -> str:
    return f"Your previous reply was invalid: {reason}. {original_user_prompt}"
