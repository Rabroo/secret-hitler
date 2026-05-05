"""CLI runner for Secret Hitler LLM.

Boots a 5-player game, prints an operator-view roster, and runs N rounds of
nomination + ja/nein election with the presidency rotating in seat order.

Player decisions go through a `{player_id: PlayerAgent}` map. By default every
agent is a seeded RandomAgent (free, deterministic). Pass `--agents llm` to use
LLM-backed agents (requires OPENAI_API_KEY in .env).
"""

from __future__ import annotations

import argparse

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
    GameState,
    LegislativeSessionResult,
    Player,
    Role,
    advance_presidency,
    assign_roles,
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
        personalities = build_personalities(players, seed=seed)
        return {
            p.id: LLMAgent(
                player=p,
                personality=personalities[p.id],
                all_players=players,
                client=client,
                fallback=RandomAgent(
                    player=p, seed=None if seed is None else seed + p.id
                ),
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
    leg: LegislativeSessionResult | None,
) -> str:
    lines = [
        _DIVIDER,
        f"DASHBOARD — Round {round_num}",
        _DIVIDER,
    ]
    if leg is not None:
        # Operator-only view of the legislative session — players' LLMs do NOT
        # see this block (only their own role's prompt).
        lines.append(
            "  [OPERATOR-ONLY] Drawn: "
            + ", ".join(p.value.upper() for p in leg.drawn)
            + f"  |  Pres discarded: {leg.discarded_by_president.value.upper()}"
            + "  |  Chancellor hand: "
            + ", ".join(p.value.upper() for p in leg.handed_to_chancellor)
            + f"  |  Enacted: {leg.enacted.value.upper()}"
        )
    for p in players:
        agent = agents[p.id]
        tags = []
        if p.id == president.id:
            tags.append("*President*")
        if p.id == nominee.id:
            tags.append("*Chancellor nominee*")
        if not p.alive:
            tags.append("(dead)")
        tag_suffix = ("  " + " ".join(tags)) if tags else ""
        lines.append(f"\nPlayer {p.id} ({p.role.value.upper()}){tag_suffix}")
        if p.id == president.id and agent.last_nominate_reasoning:
            lines.append(f"  Nominate: Player {nominee.id}")
            lines.append(f'    "{agent.last_nominate_reasoning}"')
        if p.alive and agent.last_vote_reasoning:
            lines.append(f'  Vote reasoning: "{agent.last_vote_reasoning}"')
        if leg is not None and p.id == president.id and agent.last_discard_reasoning:
            lines.append(
                f"  Discarded: {leg.discarded_by_president.value.upper()}"
            )
            lines.append(f'    "{agent.last_discard_reasoning}"')
        if leg is not None and p.id == nominee.id and agent.last_enact_reasoning:
            lines.append(f"  Enacted: {leg.enacted.value.upper()}")
            lines.append(f'    "{agent.last_enact_reasoning}"')
        # Predicted roles snapshot. +1 = predicted Liberal, -1 = predicted
        # Fascist team, 0 = no info. Liberals' values move with enacted
        # policies; Fascist team's stay pinned at known truth.
        predicted_str = "  ".join(
            f"{pid}:{score:+.2f}"
            for pid, score in sorted(personalities[p.id].predicted_roles.items())
        )
        lines.append(f"  Predicted roles: {predicted_str}")
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
) -> GameState:
    players = assign_roles(seed=seed, forced_roles=forced_roles)
    print(_render_operator_view(players))

    agents = _build_agents(agents_mode, players, seed, model, token_budget)
    personalities = build_personalities(players)
    choose = make_choose_fn(agents)
    vote = make_vote_fn(agents)
    discard = make_discard_fn(agents)
    enact = make_enact_fn(agents)
    deck = PolicyDeck(seed=seed, draw_pile=stack_deck)

    state = GameState(players=players, president_idx=0)
    if start_tally is not None:
        state.liberal_policies_enacted, state.fascist_policies_enacted = start_tally

    for round_num in range(1, rounds + 1):
        president = state.players[state.president_idx]
        candidates = eligible_chancellors(state)
        chosen = nominate_chancellor(state, choose)
        result = vote_chancellor(state, chosen, vote)

        leg: LegislativeSessionResult | None = None
        if result.passed:
            leg = legislative_session(state, deck, president, chosen, discard, enact)
            update_predicted_roles_after_session(
                state, personalities, leg, president, chosen
            )
            state.last_elected_president_id = president.id
            state.last_elected_chancellor_id = chosen.id

        print(_render_round(round_num, president, candidates, chosen, result, leg, state))

        if dashboard:
            print(
                _render_dashboard(
                    round_num=round_num,
                    players=players,
                    agents=agents,
                    personalities=personalities,
                    president=president,
                    nominee=chosen,
                    leg=leg,
                )
            )

        advance_presidency(state)

    return state


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
        )


if __name__ == "__main__":
    main()
