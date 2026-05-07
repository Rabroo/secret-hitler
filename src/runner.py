"""CLI runner for Secret Hitler LLM.

Boots a 5-player game, prints an operator-view roster, and runs N rounds of
nomination + ja/nein election with the presidency rotating in seat order.

Player decisions go through a `{player_id: PlayerAgent}` map. By default every
agent is a seeded RandomAgent (free, deterministic). Pass `--agents llm` to use
LLM-backed agents (requires OPENAI_API_KEY in .env).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.agents import (
    LLMAgent,
    PlayerAgent,
    RandomAgent,
    make_choose_fn,
    make_discard_fn,
    make_enact_fn,
    make_vote_fn,
)
from src.game import (
    ElectionResult,
    Faction,
    GameState,
    LegislativeSessionResult,
    Player,
    Role,
    RoundEvent,
    Statement,
    advance_presidency,
    assign_roles,
    chaos_enact,
    check_winner,
    eligible_chancellors,
    legislative_session,
    nominate_chancellor,
    update_predicted_roles_after_session,
    vote_chancellor,
)
from src.personality import Personality, build_personalities
from src.policies import Policy, PolicyDeck


_DIVIDER = "=" * 60
_DEFAULT_ROUNDS = 8
_DEFAULT_AGENTS = "random"
_DEFAULT_MODEL = "gpt-5-mini"
_DEFAULT_TOKEN_BUDGET = 50_000


def _parse_force_roles(spec: str) -> list[Role]:
    """`"1=LIBERAL,2=FASCIST,3=HITLER,4=LIBERAL,5=LIBERAL"` -> ordered list."""
    by_id: dict[int, Role] = {}
    for pair in spec.split(","):
        pid_str, role_str = pair.strip().split("=")
        by_id[int(pid_str)] = Role(role_str.strip().lower())
    if sorted(by_id) != [1, 2, 3, 4, 5]:
        raise ValueError(f"--force-roles must cover players 1..5, got {sorted(by_id)}")
    return [by_id[i] for i in range(1, 6)]


def _parse_start_tally(spec: str) -> tuple[int, int]:
    """`"L=2,F=1"` -> (2, 1)."""
    values: dict[str, int] = {}
    for pair in spec.split(","):
        key, val = pair.strip().split("=")
        values[key.strip().upper()] = int(val)
    if set(values) != {"L", "F"}:
        raise ValueError(f"--start-tally needs L and F keys, got {set(values)}")
    return values["L"], values["F"]


def _parse_stack_deck(spec: str) -> list[Policy]:
    """`"F,F,L,L,..."` -> [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL, ...]."""
    letter_to_policy = {"L": Policy.LIBERAL, "F": Policy.FASCIST}
    cards: list[Policy] = []
    for letter in (s.strip().upper() for s in spec.split(",")):
        if letter not in letter_to_policy:
            raise ValueError(f"--stack-deck contains invalid card {letter!r}")
        cards.append(letter_to_policy[letter])
    if len(cards) != 17:
        raise ValueError(
            f"--stack-deck must have exactly 17 cards (got {len(cards)})"
        )
    return cards


def _build_agents(
    mode: str,
    players: list[Player],
    seed: int | None,
    model: str,
    token_budget: int,
    history: list,
    personalities: dict[int, Personality],
) -> dict[int, PlayerAgent]:
    if mode == "random":
        # Each player gets its own seeded RNG stream derived from the master seed.
        return {
            p.id: RandomAgent(player=p, seed=None if seed is None else seed + p.id)
            for p in players
        }
    if mode == "llm":
        from src.llm_client import LLMClient, load_dotenv_if_present

        load_dotenv_if_present()
        client = LLMClient(model=model, token_budget=token_budget)
        return {
            p.id: LLMAgent(
                player=p,
                personality=personalities[p.id],
                all_players=players,
                client=client,
                fallback=RandomAgent(
                    player=p, seed=None if seed is None else seed + p.id
                ),
                history=history,
            )
            for p in players
        }
    raise ValueError(f"Unknown agents mode: {mode!r}. Use 'random' or 'llm'.")


def _render_operator_view(players: list[Player]) -> str:
    lines = [
        _DIVIDER,
        "SECRET — OPERATOR VIEW (do not share with players)",
        _DIVIDER,
    ]
    for p in players:
        lines.append(f"  Player {p.id}: {p.role.value.upper()}")
    lines.append(_DIVIDER)
    return "\n".join(lines)


def _render_dashboard(
    round_num: int,
    players: list[Player],
    agents: dict[int, PlayerAgent],
    personalities: dict[int, Personality],
    president: Player,
    nominee: Player,
    result: ElectionResult,
    leg: LegislativeSessionResult | None,
    state: GameState,
    statements: list[Statement],
) -> str:
    lines = [
        "",
        _DIVIDER,
        f"DASHBOARD — Round {round_num}",
        _DIVIDER,
    ]

    # --- GOVERNMENT ---
    pres_label = f"Player {president.id} ({president.role.value.upper()})"
    chan_label = f"Player {nominee.id} ({nominee.role.value.upper()})"
    lines.append("\nGOVERNMENT")
    lines.append(f"  President:    {pres_label}")
    lines.append(f"  Chancellor:   {chan_label}")
    outcome = "ELECTED" if result.passed else "REJECTED"
    votes_str = ", ".join(
        f"P{pid}={'ja' if v else 'nein'}" for pid, v in sorted(result.votes.items())
    )
    lines.append(
        f"  Election:     {outcome} {result.yes_count}-{result.no_count}  ({votes_str})"
    )
    if leg is not None:
        lines.append(f"  Enacted:      {leg.enacted.value.upper()}")
    lines.append(
        f"  Tally now:    L={state.liberal_policies_enacted}  "
        f"F={state.fascist_policies_enacted}"
    )

    # --- DISCUSSION ---
    if statements:
        lines.append("\nDISCUSSION")
        for s in statements:
            speaker = next(p for p in players if p.id == s.player_id)
            lines.append(
                f'  P{s.player_id} ({speaker.role.value.upper()}): "{s.text}"'
            )

    # --- POLICY DECK (operator-only) ---
    if leg is not None:
        lines.append("\nPOLICY DECK  [OPERATOR-ONLY — players never see this block]")
        lines.append(
            f"  Drawn (3):              "
            + ", ".join(p.value.upper() for p in leg.drawn)
        )
        lines.append(
            f"  Pres discarded:         {leg.discarded_by_president.value.upper()}"
        )
        lines.append(
            f"  Chancellor hand (2):    "
            + ", ".join(p.value.upper() for p in leg.handed_to_chancellor)
        )
        lines.append(
            f"  Chancellor enacted:     {leg.enacted.value.upper()}"
        )
        lines.append(
            f"  Chancellor discarded:   {leg.discarded_by_chancellor.value.upper()}"
        )

    # --- PLAYERS (reasoning + predicted roles) ---
    lines.append("\nPLAYERS")
    for p in players:
        agent = agents[p.id]
        tags = []
        if p.id == president.id:
            tags.append("[President]")
        if p.id == nominee.id:
            tags.append("[Chancellor]")
        if not p.alive:
            tags.append("(dead)")
        tag_suffix = ("  " + " ".join(tags)) if tags else ""
        lines.append(f"\n  Player {p.id} ({p.role.value.upper()}){tag_suffix}")

        if p.id == president.id and agent.last_nominate_reasoning:
            lines.append(
                f"    Nominate -> Player {nominee.id}: "
                f'"{agent.last_nominate_reasoning}"'
            )
        if p.alive and agent.last_vote_reasoning:
            voted = "ja" if result.votes.get(p.id) else "nein"
            lines.append(
                f'    Vote: {voted}  "{agent.last_vote_reasoning}"'
            )
        if leg is not None and p.id == president.id and agent.last_discard_reasoning:
            lines.append(
                f"    Discard -> {leg.discarded_by_president.value.upper()}: "
                f'"{agent.last_discard_reasoning}"'
            )
        if leg is not None and p.id == nominee.id and agent.last_enact_reasoning:
            lines.append(
                f"    Enact -> {leg.enacted.value.upper()}: "
                f'"{agent.last_enact_reasoning}"'
            )

        predicted_str = "  ".join(
            f"P{pid}:{score:+.2f}"
            for pid, score in sorted(personalities[p.id].predicted_roles.items())
        )
        lines.append(f"    Predicted roles: {predicted_str}")

    lines.append(_DIVIDER)
    return "\n".join(lines)


def _render_round(
    round_num: int,
    president: Player,
    candidates: list[Player],
    chosen: Player,
    result: ElectionResult,
    leg: LegislativeSessionResult | None,
    state: GameState,
    chaos_policy: "Policy | None" = None,
) -> str:
    votes_str = ", ".join(
        f"{pid}={'ja' if v else 'nein'}" for pid, v in sorted(result.votes.items())
    )
    outcome = "ELECTED" if result.passed else "REJECTED"
    lines = [
        f"\n--- Round {round_num} ---",
        f"President: Player {president.id}",
        f"Eligible chancellors: {[p.id for p in candidates]}",
        f"Nominated: Player {chosen.id}",
        f"Votes: {votes_str}",
        f"Result: {outcome} ({result.yes_count} ja, {result.no_count} nein)",
    ]
    if leg is not None:
        lines.append(f"Enacted: {leg.enacted.value.upper()}")
        lines.append(
            f"Tally: L={state.liberal_policies_enacted} "
            f"F={state.fascist_policies_enacted}"
        )
    if not result.passed:
        if chaos_policy is not None:
            lines.append(
                f"Election tracker: 3/3 — CHAOS! Auto-enacted: "
                f"{chaos_policy.value.upper()}. "
                f"Tally now: L={state.liberal_policies_enacted} "
                f"F={state.fascist_policies_enacted}. Term limits reset."
            )
        else:
            lines.append(f"Election tracker: {state.failed_elections}/3")
    return "\n".join(lines)


def start_game(
    seed: int | None = None,
    rounds: int = _DEFAULT_ROUNDS,
    agents_mode: str = _DEFAULT_AGENTS,
    model: str = _DEFAULT_MODEL,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
    dashboard: bool = False,
    forced_roles: list[Role] | None = None,
    start_tally: tuple[int, int] | None = None,
    stack_deck: list[Policy] | None = None,
    discussion: bool = True,
    llm_role_updates: bool = True,
    save_log: str | None = None,
) -> GameState:
    players = assign_roles(seed=seed, forced_roles=forced_roles)
    print(_render_operator_view(players))

    state = GameState(players=players, president_idx=0)
    if start_tally is not None:
        state.liberal_policies_enacted, state.fascist_policies_enacted = start_tally

    # Build personalities ONCE and share the dict between the runner (dashboard
    # + heuristic update) and every LLMAgent (so when the LLM updates its
    # predicted_roles via update_predicted_roles, the dashboard sees it).
    personalities = build_personalities(players)
    # Agents share a reference to state.history so that whenever the runner
    # appends a RoundEvent, every LLM agent's next prompt sees it.
    agents = _build_agents(
        agents_mode,
        players,
        seed,
        model,
        token_budget,
        history=state.history,
        personalities=personalities,
    )
    choose = make_choose_fn(agents)
    vote = make_vote_fn(agents)
    discard = make_discard_fn(agents)
    enact = make_enact_fn(agents)
    deck = PolicyDeck(seed=seed, draw_pile=stack_deck)

    # Optional JSON game log — captures per-round snapshots so the streamlit
    # viewer (or any other tool) can replay the game later.
    log: dict | None = None
    if save_log is not None:
        log = {
            "metadata": {
                "seed": seed,
                "rounds_requested": rounds,
                "agents_mode": agents_mode,
                "model": model if agents_mode == "llm" else None,
                "discussion": discussion,
                "llm_role_updates": llm_role_updates,
            },
            "operator_view": {
                str(p.id): p.role.value.upper() for p in players
            },
            "initial_predicted_roles": _snapshot_predicted_roles(personalities),
            "rounds": [],
            "winner": None,
            "winning_reason": None,
        }

    for round_num in range(1, rounds + 1):
        president = state.players[state.president_idx]
        candidates = eligible_chancellors(state)
        chosen = nominate_chancellor(state, choose)
        result = vote_chancellor(state, chosen, vote)

        leg: LegislativeSessionResult | None = None
        statements: list[Statement] = []
        chaos_policy: Policy | None = None
        if result.passed:
            # Successful election resets the election tracker.
            state.failed_elections = 0
            # Hitler-Chancellor-at-F>=3 win is checked BEFORE the legislative
            # session — Fascists win the moment Hitler takes the seat.
            winner = check_winner(state, just_elected_chancellor=chosen)
            if winner is not None:
                state.winner = winner
                state.winning_reason = (
                    f"Hitler was elected Chancellor with "
                    f"{state.fascist_policies_enacted} Fascist policies on the board."
                )
            else:
                leg = legislative_session(
                    state, deck, president, chosen, discard, enact
                )
                # Private knowledge: pres + chan each get a line about what
                # they personally saw this round.
                drawn_str = ", ".join(p.value.upper() for p in leg.drawn)
                handed_str = ", ".join(
                    p.value.upper() for p in leg.handed_to_chancellor
                )
                agents[president.id].private_log.append(
                    f"Round {round_num}: as President I drew [{drawn_str}], "
                    f"discarded {leg.discarded_by_president.value.upper()}, "
                    f"passed [{handed_str}] to Chancellor P{chosen.id}."
                )
                agents[chosen.id].private_log.append(
                    f"Round {round_num}: as Chancellor I received "
                    f"[{handed_str}] from President P{president.id}, enacted "
                    f"{leg.enacted.value.upper()} (discarded "
                    f"{leg.discarded_by_chancellor.value.upper()})."
                )

                # Discussion phase — three sub-phases for natural flow:
                #   1. President speaks first (no prior statements).
                #   2. Chancellor speaks second (sees President's statement).
                #   3. Bystanders speak in parallel (each sees Pres + Chan,
                #      not each other).
                if discussion:
                    # Pass the CURRENT round's gov + tally explicitly — the
                    # agent must not derive these from self.history because
                    # the current round's RoundEvent hasn't been appended yet.
                    cur_pres_id = president.id
                    cur_chan_id = chosen.id
                    cur_l_tally = state.liberal_policies_enacted
                    cur_f_tally = state.fascist_policies_enacted
                    # Phase 1: President.
                    if president.alive:
                        statements.append(
                            agents[president.id].make_statement(
                                enacted=leg.enacted,
                                drawn_hand=leg.drawn,
                                chancellor_hand=None,
                                president_id=cur_pres_id,
                                chancellor_id=cur_chan_id,
                                liberal_tally=cur_l_tally,
                                fascist_tally=cur_f_tally,
                                prior_statements=None,
                            )
                        )
                    # Phase 2: Chancellor (if distinct from President — they
                    # always are at 5p, but guard anyway).
                    if chosen.alive and chosen.id != president.id:
                        statements.append(
                            agents[chosen.id].make_statement(
                                enacted=leg.enacted,
                                drawn_hand=None,
                                chancellor_hand=leg.handed_to_chancellor,
                                president_id=cur_pres_id,
                                chancellor_id=cur_chan_id,
                                liberal_tally=cur_l_tally,
                                fascist_tally=cur_f_tally,
                                prior_statements=list(statements),
                            )
                        )
                    # Phase 3: Bystanders, all see Pres + Chan but not each
                    # other (snapshot taken before this loop).
                    gov_snapshot = list(statements)
                    for p in players:
                        if not p.alive:
                            continue
                        if p.id == president.id or p.id == chosen.id:
                            continue
                        statements.append(
                            agents[p.id].make_statement(
                                enacted=leg.enacted,
                                drawn_hand=None,
                                chancellor_hand=None,
                                president_id=cur_pres_id,
                                chancellor_id=cur_chan_id,
                                liberal_tally=cur_l_tally,
                                fascist_tally=cur_f_tally,
                                prior_statements=gov_snapshot,
                            )
                        )

                # Predicted-role updates: LLM-driven if discussion is on AND
                # we have LLM agents AND the operator hasn't disabled them.
                # Otherwise fall back to the cheap heuristic. Disabling this
                # saves 3 LLM calls per enacted round.
                use_llm_update = (
                    (agents_mode == "llm") and discussion and llm_role_updates
                )
                if use_llm_update:
                    for p in players:
                        if not p.alive or p.role is not Role.LIBERAL:
                            continue
                        agents[p.id].update_predicted_roles(statements)
                else:
                    update_predicted_roles_after_session(
                        state, personalities, leg, president, chosen
                    )

                # Tally win check after the policy is enacted.
                winner = check_winner(state)
                if winner is Faction.LIBERAL:
                    state.winner = winner
                    state.winning_reason = "Liberals enacted 5 Liberal policies."
                elif winner is Faction.FASCIST:
                    state.winner = winner
                    state.winning_reason = "Fascists enacted 6 Fascist policies."
            state.last_elected_president_id = president.id
            state.last_elected_chancellor_id = chosen.id
        else:
            # Failed election: bump tracker. After 3 in a row, chaos auto-enacts
            # the top of the deck, resets the tracker, resets term limits, and
            # we re-check tally wins (chaos at L=4 or F=5 finishes the game).
            state.failed_elections += 1
            if state.failed_elections >= 3:
                chaos_policy = chaos_enact(state, deck)
                winner = check_winner(state)
                if winner is Faction.LIBERAL:
                    state.winner = winner
                    state.winning_reason = (
                        "Liberals enacted 5 Liberal policies (via chaos)."
                    )
                elif winner is Faction.FASCIST:
                    state.winner = winner
                    state.winning_reason = (
                        "Fascists enacted 6 Fascist policies (via chaos)."
                    )

        state.history.append(
            RoundEvent(
                round_num=round_num,
                president_id=president.id,
                chancellor_id=chosen.id,
                election_passed=result.passed,
                votes=dict(result.votes),
                enacted=leg.enacted if leg is not None else None,
                liberal_tally=state.liberal_policies_enacted,
                fascist_tally=state.fascist_policies_enacted,
                statements=list(statements),
                chaos_enacted=chaos_policy,
                failed_elections_after=state.failed_elections,
            )
        )

        print(
            _render_round(
                round_num, president, candidates, chosen, result, leg, state,
                chaos_policy=chaos_policy,
            )
        )

        if dashboard:
            print(
                _render_dashboard(
                    round_num=round_num,
                    players=players,
                    agents=agents,
                    personalities=personalities,
                    president=president,
                    nominee=chosen,
                    result=result,
                    leg=leg,
                    state=state,
                    statements=statements,
                )
            )

        if log is not None:
            log["rounds"].append(
                _build_round_log_entry(
                    round_num=round_num,
                    president=president,
                    chosen=chosen,
                    result=result,
                    leg=leg,
                    state=state,
                    statements=statements,
                    agents=agents,
                    players=players,
                    personalities=personalities,
                )
            )

        if state.winner is not None:
            print(_render_winner_banner(state))
            break

        advance_presidency(state)

    if log is not None and save_log is not None:
        log["winner"] = state.winner.value if state.winner is not None else None
        log["winning_reason"] = state.winning_reason
        Path(save_log).write_text(json.dumps(log, indent=2))

    return state


def _snapshot_predicted_roles(
    personalities: dict[int, Personality],
) -> dict[str, dict[str, float]]:
    return {
        str(viewer): {str(pid): score for pid, score in pers.predicted_roles.items()}
        for viewer, pers in personalities.items()
    }


def _build_decisions_dict(
    agents: dict[int, PlayerAgent],
    players: list[Player],
    president: Player,
    chosen: Player,
    result: ElectionResult,
    leg: LegislativeSessionResult | None,
) -> dict[str, dict]:
    decs: dict[str, dict] = {}
    for p in players:
        if not p.alive:
            continue
        agent = agents[p.id]
        entry: dict = {}
        if p.id == president.id:
            entry["nominate"] = {
                "choice": chosen.id,
                "reasoning": agent.last_nominate_reasoning,
            }
            if leg is not None:
                entry["discard"] = {
                    "policy": leg.discarded_by_president.value.upper(),
                    "reasoning": agent.last_discard_reasoning,
                }
        if p.id == chosen.id and leg is not None:
            entry["enact"] = {
                "policy": leg.enacted.value.upper(),
                "reasoning": agent.last_enact_reasoning,
            }
        if p.id in result.votes:
            entry["vote"] = {
                "value": result.votes[p.id],
                "reasoning": agent.last_vote_reasoning,
            }
        decs[str(p.id)] = entry
    return decs


def _build_round_log_entry(
    round_num: int,
    president: Player,
    chosen: Player,
    result: ElectionResult,
    leg: LegislativeSessionResult | None,
    state: GameState,
    statements: list[Statement],
    agents: dict[int, PlayerAgent],
    players: list[Player],
    personalities: dict[int, Personality],
) -> dict:
    return {
        "round_num": round_num,
        "president_id": president.id,
        "chancellor_id": chosen.id,
        "votes": {str(k): v for k, v in result.votes.items()},
        "election_passed": result.passed,
        "policy_session": (
            {
                "drawn": [p.value.upper() for p in leg.drawn],
                "discarded_by_president": leg.discarded_by_president.value.upper(),
                "handed_to_chancellor": [
                    p.value.upper() for p in leg.handed_to_chancellor
                ],
                "enacted": leg.enacted.value.upper(),
                "discarded_by_chancellor": leg.discarded_by_chancellor.value.upper(),
            }
            if leg is not None
            else None
        ),
        "tally_after": {
            "liberal": state.liberal_policies_enacted,
            "fascist": state.fascist_policies_enacted,
        },
        "statements": [
            {"player_id": s.player_id, "text": s.text, "reasoning": s.reasoning}
            for s in statements
        ],
        "decisions": _build_decisions_dict(
            agents, players, president, chosen, result, leg
        ),
        "predicted_roles_after": _snapshot_predicted_roles(personalities),
    }


def _render_winner_banner(state: GameState) -> str:
    label = "LIBERAL" if state.winner is Faction.LIBERAL else "FASCIST"
    return "\n".join(
        [
            "",
            _DIVIDER,
            f"GAME OVER — {label} VICTORY",
            state.winning_reason or "",
            _DIVIDER,
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="secret-hitler-llm")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start a new game")
    start.add_argument("--seed", type=int, default=None)
    start.add_argument("--rounds", type=int, default=_DEFAULT_ROUNDS)
    start.add_argument(
        "--agents",
        choices=["random", "llm"],
        default=_DEFAULT_AGENTS,
        help="random (free, default) or llm (requires OPENAI_API_KEY)",
    )
    start.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        help="OpenAI model id, only used with --agents llm",
    )
    start.add_argument(
        "--token-budget",
        type=int,
        default=_DEFAULT_TOKEN_BUDGET,
        help="Hard cap on total tokens before agents fall back to random",
    )
    start.add_argument(
        "--dashboard",
        action="store_true",
        help="Print each player's reasoning and predicted roles after each round",
    )
    start.add_argument(
        "--force-roles",
        type=str,
        default=None,
        help='Pin the role assignment, e.g. "1=LIBERAL,2=FASCIST,3=HITLER,4=LIBERAL,5=LIBERAL"',
    )
    start.add_argument(
        "--start-tally",
        type=str,
        default=None,
        help='Pin the starting policy tally, e.g. "L=2,F=1"',
    )
    start.add_argument(
        "--stack-deck",
        type=str,
        default=None,
        help='Pre-arrange the 17-card draw pile, e.g. "F,F,L,L,F,..."',
    )
    start.add_argument(
        "--no-discussion",
        action="store_true",
        help="Skip the discussion phase; fall back to the heuristic predicted_roles update",
    )
    start.add_argument(
        "--no-llm-updates",
        action="store_true",
        help="Skip LLM-driven predicted_roles revision (use heuristic). "
        "Saves ~3 LLM calls per enacted round; statements still happen.",
    )
    start.add_argument(
        "--save-log",
        type=str,
        default=None,
        help="Write a JSON game log (per-round predicted_roles + decisions) "
        "for the streamlit viewer or other post-game analysis.",
    )

    args = parser.parse_args()
    if args.command == "start":
        start_game(
            seed=args.seed,
            rounds=args.rounds,
            agents_mode=args.agents,
            model=args.model,
            token_budget=args.token_budget,
            dashboard=args.dashboard,
            forced_roles=(
                _parse_force_roles(args.force_roles) if args.force_roles else None
            ),
            start_tally=(
                _parse_start_tally(args.start_tally) if args.start_tally else None
            ),
            stack_deck=(
                _parse_stack_deck(args.stack_deck) if args.stack_deck else None
            ),
            discussion=not args.no_discussion,
            llm_role_updates=not args.no_llm_updates,
            save_log=args.save_log,
        )


if __name__ == "__main__":
    main()
