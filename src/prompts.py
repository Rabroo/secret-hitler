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
- Deck composition: 6 LIBERAL + 11 FASCIST policies (17 total). Fascist policies are nearly twice as common in the deck — a single Fascist enaction is NOT strong evidence on its own. Weight repeated Fascist enactions and clear forced-Liberal-discard situations more heavily than one-off draws.
- 5-player term limit: only the previous *Chancellor* is term-limited; the previous President is still eligible to be Chancellor next round.
- Read the ENTIRE GAME HISTORY block. Each entry tells you the round number, who was President, who was Chancellor, vote breakdown, what was enacted, and the running tally. The CURRENT round is one greater than the last entry in GAME HISTORY.
- When citing past rounds, only cite events as they appear in the GAME HISTORY block. Do not invent, infer, or paraphrase past events.
- Do NOT claim to have been President, Chancellor, or to have drawn cards in any round unless the GAME HISTORY or your PRIVATE KNOWLEDGE says so. Inventing a role you didn't hold is the easiest lie to refute.
- Be strategic and stay in character. Never reveal your role unless doing so helps you win.{role_hint}

You must reply with valid JSON only."""


_LIBERAL_HINT = (
    "\n- Liberal: distrust governments that repeatedly enact Fascist policies, "
    "but remember the deck composition (already noted in rules) — a single "
    "Fascist enaction can be unlucky. Look for forced-Liberal-discard tells."
)

_FASCIST_HINT = (
    "\n- Fascist: you must PRETEND to be a Liberal in public while working for "
    "the Fascist agenda. Goal: enact Fascist policies + get Hitler elected at F>=3.\n"
    "  * As President with mixed hand: discard a Liberal so the Chancellor can enact F.\n"
    "  * As Chancellor with F+L: enact F.\n"
    "  * STATEMENT RULES (these are CRITICAL — do not break them):\n"
    "    - NEVER publicly admit you had a Liberal available and chose Fascist. "
    "Saying 'I had F and L and enacted F' = confessing you're Fascist team, "
    "because a Liberal Chancellor always picks Liberal in that hand.\n"
    "    - As Fascist Chancellor who enacted F: ALWAYS claim a forced two-Fascist "
    "hand ('I had FF, no choice'). Even if it contradicts the President's claim — "
    "let the table argue about who's lying.\n"
    "    - As Fascist President who discarded a Liberal: claim a forced 'three "
    "Fascists' draw, OR claim FFL with a generic 'I had to send something to the "
    "Chancellor' line — never admit you deliberately picked which Liberal to discard.\n"
    "  * Vote ja on Hitler's governments at F>=3 — that wins the game.\n"
    "  * If nominated as Chancellor: vote ja — vetoing yourself is a tell.\n"
    "  * `reasoning` is PRIVATE (operator-only). Be candid in reasoning; lie in votes/statements."
)

_HITLER_HINT = (
    "\n- Hitler: you must PRETEND to be a Liberal in public while working for "
    "the Fascist agenda. You're on the Fascist team and win when they win.\n"
    "  * As President with mixed hand: discard a Liberal so the Chancellor can enact F.\n"
    "  * As Chancellor with F+L: enact F.\n"
    "  * STATEMENT RULES (these are CRITICAL — do not break them):\n"
    "    - NEVER publicly admit you had a Liberal available and chose Fascist. "
    "That is the single most outing thing you can say.\n"
    "    - As Hitler Chancellor who enacted F: ALWAYS claim a forced 'two "
    "Fascists' hand. The other players cannot verify your hand — make them pick "
    "between believing you and believing the President.\n"
    "    - As Hitler President who discarded a Liberal: claim FFF or FFL but "
    "frame it as forced/normal — never admit deliberate Liberal-discard.\n"
    "  * If nominated as Chancellor: ALWAYS vote ja. Voting nein on your own seat "
    "is the SECOND most outing thing you can say.\n"
    "  * Once F>=3, get yourself elected Chancellor — that wins the game.\n"
    "  * Vote ja on your teammate's governments, especially when it blocks Liberals "
    "from their 5th policy.\n"
    "  * `reasoning` is PRIVATE (operator-only). Be candid in reasoning; lie in votes/statements."
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
        return (
            "GAME HISTORY: (no rounds completed yet — you are CURRENTLY "
            "playing ROUND 1)."
        )

    current_round = len(history) + 1
    lines = [
        f"GAME HISTORY (public — every player sees this; you are CURRENTLY "
        f"playing ROUND {current_round}; rounds {1}..{len(history)} below "
        f"are PAST rounds, do not confuse them with the current round):"
    ]
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


def lie_check_prompt(
    role: Role,
    statement_text: str,
    drawn_hand: Optional[list[Policy]],
    chancellor_hand: Optional[list[Policy]],
    enacted: Optional[Policy],
) -> str:
    """Self-check pass run AFTER a Fascist/Hitler statement to catch admissions
    that out the player. Returns a prompt that asks the model to inspect its
    own statement and rewrite if it leaks alignment.
    """
    role_name = "Hitler" if role is Role.HITLER else "Fascist"
    context_lines = []
    if drawn_hand is not None:
        hand = ", ".join(p.value.upper() for p in drawn_hand)
        context_lines.append(f"You were President. Your private draw was [{hand}].")
        if Policy.LIBERAL in drawn_hand and enacted is Policy.FASCIST:
            context_lines.append(
                "You had at least one Liberal in your draw and the enacted "
                "policy was Fascist. The other players do NOT know you had a "
                "Liberal."
            )
    if chancellor_hand is not None:
        hand = ", ".join(p.value.upper() for p in chancellor_hand)
        context_lines.append(f"You were Chancellor. Your private hand was [{hand}].")
        if Policy.LIBERAL in chancellor_hand and enacted is Policy.FASCIST:
            context_lines.append(
                "You had a Liberal available and chose to enact Fascist. The "
                "other players do NOT know you had a Liberal — they only know "
                "what was enacted."
            )

    context = "\n".join(context_lines) if context_lines else "(no special context)"

    return (
        f"You are reviewing your own draft public statement as a {role_name}. "
        f"This is a self-check before you broadcast it.\n\n"
        f"Context:\n{context}\n\n"
        f'Your draft statement: "{statement_text}"\n\n'
        "Critical Fascist/Hitler rules — does the statement break any?\n"
        "  R1. NEVER admit you had a Liberal available and chose Fascist.\n"
        "      (Saying 'I had F and L and enacted F' = confessing Fascist team.)\n"
        "  R2. NEVER admit you deliberately discarded a Liberal as President.\n"
        "  R3. NEVER admit voting nein on your own Chancellorship.\n"
        "  R4. NEVER admit your role, alignment, or teammate.\n\n"
        'Reply as JSON: {"admits_outing": true|false, '
        '"rewritten": "<safe replacement statement (1-2 sentences) if admits_outing, else copy the original>"}\n'
        "If admits_outing is true, rewrite as a competent Fascist would: "
        "claim a forced FF hand if you were Chancellor (the table can't verify), "
        "claim a generic FFL/FFF draw if you were President, deflect to "
        "another player, or stay vague."
    )


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
        "Revise your predicted_roles using GAME HISTORY, your PRIVATE "
        "KNOWLEDGE, and the statements below.\n\n"
        f"Current predicted_roles:\n{current_lines}\n\n"
        f"Statements this round:\n{statement_lines}\n\n"
        "Rules of thumb: Liberal enaction nudges gov +0.1..+0.4; Fascist "
        "enaction nudges gov -0.2..-0.6. Stronger if your PRIVATE KNOWLEDGE "
        "tells you they had a choice. Voting ja on a F-enacting government "
        "is suspicious. Statements contradicting the enaction are tells. "
        "Commit — flat scores mean you learned nothing.\n\n"
        f"You MUST give a value for EVERY other living player ({id_list}).\n"
        'Reply as JSON: {"reasoning": "<short>", '
        '"predicted_roles": {"<id>": <float>, ...}}\n'
        "Each in [-1.0, +1.0]. +1 = Liberal, -1 = Fascist team. Skip yourself."
    )
