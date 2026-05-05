"""Centralised LLM prompt templates.

Every string the LLM sees lives here so it's easy to find, tweak, and
A/B-test. The agent module imports these builders and never composes prompts
inline. See `specs/prompts.md` and `specs/game_history_in_prompts.md`.
"""

from __future__ import annotations

from typing import Optional

from src.game import Player, Role, RoundEvent
from src.personality import Personality
from src.policies import Policy


# --- system prompt ----------------------------------------------------------

_SYSTEM_TEMPLATE = """You are Player {player_id} in a 5-player game of Secret Hitler.
Your role: {role}.{team_block}
Your alignment desire (+1 wants Liberal outcomes .. -1 wants Fascist outcomes): {desire:+.2f}.

Your predicted_roles for the other players (+1 = you predict Liberal, -1 = you predict Fascist team, 0 = no info):
{predicted_role_lines}

Public roster: {roster}.

{history_block}

Rules summary:
- Liberals win by enacting 5 Liberal policies or executing Hitler.
- Fascists win by enacting 6 Fascist policies, or by electing Hitler as Chancellor after 3 Fascist policies are enacted.
- Be strategic and stay in character. Never reveal your role unless doing so helps you win.{role_hint}

You must reply with valid JSON only."""


_LIBERAL_HINT = (
    "\n- As a Liberal, you start with no information. Use voting and policy "
    "enactions in the GAME HISTORY above to update your predictions. Don't "
    "trust governments that produce Fascist policies."
)

_FASCIST_HINT = (
    "\n- As a Fascist, you know who Hitler is (named above). Don't openly "
    "support Hitler — Liberals will spot the pattern. Early-game, act like "
    "a Liberal: vote moderately, claim Liberal policies. Bury your alignment "
    "until you've built cover. Help Hitler get Chancellor *after* 3 Fascist "
    "policies are enacted — that wins the game for your team."
)

_HITLER_HINT = (
    "\n- As Hitler, stay quiet and undercover. Don't seek the Chancellor "
    "seat early — getting elected with 3+ Fascist policies on the board "
    "wins the game for your team, but only after Liberals stop suspecting "
    "you. Mimic Liberal play in early rounds. Quietly support your "
    "Fascist teammate's governments without making the support obvious."
)

_ROLE_HINTS = {
    Role.LIBERAL: _LIBERAL_HINT,
    Role.FASCIST: _FASCIST_HINT,
    Role.HITLER: _HITLER_HINT,
}


def _fascist_teammate_id(
    player: Player, all_players: list[Player]
) -> Optional[int]:
    """At 5p, Hitler's teammate is the Fascist and vice versa."""
    if player.role is Role.LIBERAL:
        return None
    target = Role.FASCIST if player.role is Role.HITLER else Role.HITLER
    for p in all_players:
        if p.role is target:
            return p.id
    return None


def _team_identity_block(
    player: Player, all_players: list[Player]
) -> str:
    teammate_id = _fascist_teammate_id(player, all_players)
    if teammate_id is None:
        return ""
    return (
        f"\nYour Fascist teammate is Player {teammate_id}. You and Player "
        f"{teammate_id} win together — enact 6 Fascist policies, OR get "
        f"Hitler elected Chancellor after 3 Fascist policies are on the "
        f"board. Quietly support each other's governments, but don't "
        f"openly nominate or always vote ja for them — Liberals will spot "
        f"the pattern."
    )


def format_history(history: list[RoundEvent]) -> str:
    """Render the public game-history block for the system prompt."""
    if not history:
        return "GAME HISTORY: (no rounds completed yet — this is round 1)."

    lines = ["GAME HISTORY (public — every player sees this):"]
    for ev in history:
        ja_ids = [pid for pid, v in sorted(ev.votes.items()) if v]
        nein_ids = [pid for pid, v in sorted(ev.votes.items()) if not v]
        gov = f"Pres P{ev.president_id} + Chan P{ev.chancellor_id}"
        outcome = "ELECTED" if ev.election_passed else "REJECTED"
        result = f"{outcome} {len(ja_ids)}-{len(nein_ids)}"
        breakdown = ""
        if nein_ids and ev.election_passed:
            breakdown = f" (P{', P'.join(str(p) for p in nein_ids)} nein)"
        elif ja_ids and not ev.election_passed:
            breakdown = f" (P{', P'.join(str(p) for p in ja_ids)} ja)"
        if ev.election_passed:
            assert ev.enacted is not None
            tail = f". Enacted {ev.enacted.value.upper()}."
        else:
            tail = "."
        tally = f" Tally L={ev.liberal_tally} F={ev.fascist_tally}."
        lines.append(f"- Round {ev.round_num}: {gov} {result}{breakdown}{tail}{tally}")
    last = history[-1]
    lines.append(
        f"Current tally: L={last.liberal_tally} F={last.fascist_tally}."
    )
    return "\n".join(lines)


def system_prompt(
    player: Player,
    personality: Personality,
    all_players: list[Player],
    history: Optional[list[RoundEvent]] = None,
) -> str:
    predicted_role_lines = "\n".join(
        f"  Player {pid}: {score:+.2f}"
        for pid, score in sorted(personality.predicted_roles.items())
    )
    roster = ", ".join(f"Player {p.id}" for p in all_players)
    return _SYSTEM_TEMPLATE.format(
        player_id=player.id,
        role=player.role.value.upper(),
        team_block=_team_identity_block(player, all_players),
        desire=personality.desire,
        predicted_role_lines=predicted_role_lines,
        roster=roster,
        history_block=format_history(history or []),
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
