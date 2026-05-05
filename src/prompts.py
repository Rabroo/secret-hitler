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
- 5-player term limit: only the previous *Chancellor* is term-limited; the previous President is still eligible to be Chancellor next round.
- Be strategic and stay in character. Never reveal your role unless doing so helps you win.{role_hint}

You must reply with valid JSON only."""


_LIBERAL_HINT = (
    "\n- As a Liberal, you start with no information. Use voting and policy "
    "enactions in the GAME HISTORY above to update your predictions. Distrust "
    "governments that produce Fascist policies. With the deck at 11 Fascist "
    "vs 6 Liberal, a Liberal enaction is a meaningful trust signal."
)

_FASCIST_HINT = (
    "\n- As a Fascist, your job is to ENACT FASCIST POLICIES and protect Hitler. "
    "Cover matters but it is NOT the goal — the goal is winning. Concretely:\n"
    "  * As President with a hand of 3, prefer to discard a LIBERAL so the "
    "Chancellor's hand contains a Fascist they can enact (or a forced double-"
    "Fascist hand). Discarding a Fascist actively helps the enemy team and "
    "should only happen when you genuinely need cover.\n"
    "  * As Chancellor with a Fascist+Liberal hand, enact the FASCIST when you "
    "can plausibly blame the President's draw.\n"
    "  * Vote ja on governments that contain Hitler once F>=3 is on the board.\n"
    "  * Don't openly nominate Hitler in the first 2 rounds — Liberals notice. "
    "After cover is built, push Hitler into the Chancellor seat at F>=3."
)

_HITLER_HINT = (
    "\n- As Hitler, you are on the FASCIST team and you win when the Fascist "
    "team wins. Cover is your priority, but cover is not pacifism — you also "
    "need to actively enable Fascist enactions:\n"
    "  * As President with 3 cards, prefer to discard a Liberal so the "
    "Chancellor's hand allows a Fascist enaction. Pretend to a 'forced' line.\n"
    "  * Don't volunteer for the Chancellor seat early. Once F>=3, getting "
    "elected Chancellor wins the game for your team — that is the moment to "
    "say yes.\n"
    "  * Vote ja on your Fascist teammate's governments, especially when the "
    "tally pressures Liberals (e.g., Liberals at 4 — block their last policy).\n"
    "  * 'Mimic Liberal play' means tone, not goals: you can vocally complain "
    "about Fascist policies even after enacting them."
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
