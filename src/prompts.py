"""Centralised LLM prompt templates.

Every string the LLM sees lives here so it's easy to find, tweak, and
A/B-test. The agent module imports these builders and never composes prompts
inline. See `specs/prompts.md` and `specs/game_history_in_prompts.md`.
"""

from __future__ import annotations

from typing import Optional

from src.game import Player, Role, RoundEvent, Statement
from src.personality import Personality
from src.policies import Policy


# --- system prompt ----------------------------------------------------------

_SYSTEM_TEMPLATE = """You are Player {player_id} in a 5-player game of Secret Hitler.
Your role: {role}.{team_block}
Your alignment desire (+1 wants Liberal outcomes .. -1 wants Fascist outcomes): {desire:+.2f}.

Your predicted_roles for the other players (+1 = you predict Liberal, -1 = you predict Fascist team, 0 = no info):
{predicted_role_lines}

Public roster: {roster}.
{private_block}
{history_block}

Rules summary:
- Liberals win by enacting 5 Liberal policies or executing Hitler.
- Fascists win by enacting 6 Fascist policies, or by electing Hitler as Chancellor after 3 Fascist policies are enacted.
- 5-player term limit: only the previous *Chancellor* is term-limited; the previous President is still eligible to be Chancellor next round.
- When citing past rounds, only cite events as they appear in the GAME HISTORY block above. Do not invent, infer, or paraphrase past events.
- Do NOT claim to have been President, Chancellor, or to have drawn cards in any round unless the GAME HISTORY or your PRIVATE KNOWLEDGE says so. Inventing a role you didn't hold is the easiest lie to refute.
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
    "  * Vote ja on governments that contain Hitler once F>=3 is on the board. "
    "Hitler being elected then wins the game for your team.\n"
    "  * IF YOU ARE NOMINATED as Chancellor, vote ja. Vetoing your own seat is "
    "a tell.\n"
    "  * Your `reasoning` field is PRIVATE — only the operator sees it. Be "
    "candid about team strategy in reasoning; hide alignment in votes/statements."
)

_HITLER_HINT = (
    "\n- As Hitler, you are on the FASCIST team and you win when the Fascist "
    "team wins. Cover is your priority, but cover is not pacifism — you also "
    "need to actively enable Fascist enactions:\n"
    "  * As President with 3 cards, prefer to discard a Liberal so the "
    "Chancellor's hand allows a Fascist enaction. Pretend to a 'forced' line.\n"
    "  * Once F>=3, getting elected Chancellor wins the game for your team.\n"
    "  * IF YOU ARE NOMINATED as Chancellor, vote ja. Voting nein on your own "
    "chancellorship is a huge tell that screams 'I'm Hitler.' Even if it's "
    "early and you don't want the seat, vote ja — let it succeed or fail on "
    "the others' votes.\n"
    "  * Vote ja on your Fascist teammate's governments, especially when the "
    "tally pressures Liberals (e.g., Liberals at 4 — block their last policy).\n"
    "  * Your `reasoning` field is PRIVATE — only the operator sees it, never "
    "the other players. Be candid in your reasoning about your team strategy. "
    "Hide alignment in your votes and statements, not in your private reasoning."
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
        if ev.statements:
            lines.append("    Statements:")
            for s in ev.statements:
                lines.append(f'      P{s.player_id}: "{s.text}"')
    last = history[-1]
    lines.append(
        f"Current tally: L={last.liberal_tally} F={last.fascist_tally}."
    )
    return "\n".join(lines)


def _private_block(private_log: Optional[list[str]]) -> str:
    if not private_log:
        return ""
    lines = [
        "",
        "PRIVATE KNOWLEDGE (visible only to you, never to other players):",
    ]
    for entry in private_log:
        lines.append(f"- {entry}")
    return "\n".join(lines)


def system_prompt(
    player: Player,
    personality: Personality,
    all_players: list[Player],
    history: Optional[list[RoundEvent]] = None,
    private_log: Optional[list[str]] = None,
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
        private_block=_private_block(private_log),
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


# --- discussion prompts -----------------------------------------------------


def statement_prompt(
    enacted: Policy,
    drawn_hand: Optional[list[Policy]],
    chancellor_hand: Optional[list[Policy]],
    liberal_tally: int,
    fascist_tally: int,
    president_id: int,
    chancellor_id: int,
    prior_statements: Optional[list[Statement]] = None,
) -> str:
    lines = [
        "The legislative session is complete:",
        f"  Government:  President P{president_id} + Chancellor P{chancellor_id}",
        f"  Enacted:     {enacted.value.upper()}",
        f"  Tally now:   L={liberal_tally} F={fascist_tally}",
    ]

    if prior_statements:
        lines.append("\nStatements made earlier this round:")
        for s in prior_statements:
            lines.append(f'  P{s.player_id}: "{s.text}"')

    if drawn_hand is not None:
        # PRESIDENT — saw 3 cards privately.
        hand_str = ", ".join(p.value.upper() for p in drawn_hand)
        lines.append(
            f"\nYou were the PRESIDENT this round. You privately drew "
            f"[{hand_str}], discarded one card, and passed the other 2 to "
            f"the Chancellor. Nobody else saw your draw."
        )
        lines.append(
            "Make ONE public statement (1-2 sentences). You may claim "
            "your draw honestly or lie about it. Common President lines: "
            'claim what you drew, defend the discard, accuse the Chancellor.'
        )
    elif chancellor_hand is not None:
        # CHANCELLOR — saw 2 cards privately.
        hand_str = ", ".join(p.value.upper() for p in chancellor_hand)
        lines.append(
            f"\nYou were the CHANCELLOR this round. You received "
            f"[{hand_str}] from the President and enacted "
            f"{enacted.value.upper()}. Nobody else saw your hand."
        )
        lines.append(
            "Make ONE public statement (1-2 sentences). You may claim "
            "honestly what you were given or lie about it. Common Chancellor "
            "lines: claim what was passed, blame the President's draw, "
            "explain why you enacted what you did."
        )
    else:
        # BYSTANDER — was not in the government, saw nothing private.
        lines.append(
            "\nYou were NOT in the government this round (you are not "
            f"President P{president_id} and not Chancellor P{chancellor_id}). "
            "You saw NO policy cards this round."
        )
        lines.append(
            "Do NOT claim to have drawn cards, been President, or been "
            "Chancellor — those would be obvious lies that the actual "
            "President / Chancellor and everyone watching would refute "
            "instantly. Stick to public information."
        )
        lines.append(
            "Make ONE public statement (1-2 sentences): accuse, defend, "
            "share a theory, point out a tell, or compare a gov member's "
            "claim to what was enacted. No card claims about yourself."
        )

    lines.append(
        "\nIMPORTANT: this is a ONE-SHOT statement made simultaneously with "
        "everyone else. Nobody will respond, and the President/Chancellor "
        "have already made their own statements at the same time. "
        "DO NOT ask questions like 'please explain' or 'why did you do X' — "
        "no one will answer. State a position, accusation, or claim. "
        "DO NOT address yourself by player ID — you ARE the player making "
        "this statement. Refer to others as 'P2', 'Player 4', etc., never "
        "yourself."
    )
    lines.append(
        '\nReply as JSON: {"reasoning": "<one short sentence>", '
        '"statement": "<your public message>"}'
    )
    return "\n".join(lines)


def update_predicted_roles_prompt(
    current_predicted_roles: dict[int, float],
    statements: list[Statement],
) -> str:
    current_lines = "\n".join(
        f"  P{pid}: {score:+.2f}"
        for pid, score in sorted(current_predicted_roles.items())
    )
    if statements:
        statement_lines = "\n".join(
            f'  P{s.player_id}: "{s.text}"' for s in statements
        )
    else:
        statement_lines = "  (no statements this round)"
    other_ids = sorted(current_predicted_roles.keys())
    id_list = ", ".join(str(pid) for pid in other_ids)
    return (
        "You just observed this round's events and statements. Use everything "
        "in GAME HISTORY (above), your own PRIVATE KNOWLEDGE (above), and the "
        "statements below to revise your predicted_roles for every other "
        "player.\n\n"
        f"Your current predicted_roles:\n{current_lines}\n\n"
        f"Statements this round:\n{statement_lines}\n\n"
        "Guidelines:\n"
        "- A Liberal policy enaction is mild Liberal evidence for both "
        "President and Chancellor: typically nudge their score +0.1 to +0.4 "
        "toward +1. Stronger if you (as President) personally know they had "
        "a clean Liberal hand and chose Liberal.\n"
        "- A Fascist policy enaction is strong Fascist evidence for both: "
        "typically nudge their score -0.2 to -0.6 toward -1. Even stronger "
        "if you (as President) personally know the Chancellor had a Liberal "
        "available and chose Fascist anyway.\n"
        "- Voting patterns matter: a player who voted ja on a F-enacting "
        "government looks more suspicious than one who voted nein.\n"
        "- A statement that contradicts the actual enaction (e.g., claims a "
        "Liberal-leaning hand when a Fascist was enacted) is a tell.\n"
        "- Be willing to commit. If your scores never move, you're learning "
        "nothing from this round.\n\n"
        f"You MUST provide a value for EVERY other living player ({id_list}).\n"
        "Reply as JSON:\n"
        '{"reasoning": "<one short sentence>", '
        '"predicted_roles": {"<id>": <float>, ...}}\n'
        "Each value in [-1.0, +1.0]. +1 = predicted Liberal, -1 = predicted "
        "Fascist team. Do not include yourself."
    )
