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
    advance_presidency,
    assign_roles,
    eligible_chancellors,
    legislative_session,
    nominate_chancellor,
    vote_chancellor,
)
from src.personality import Personality, build_personalities
from src.policies import PolicyDeck


_DIVIDER = "=" * 60
_DEFAULT_ROUNDS = 8
_DEFAULT_AGENTS = "random"
_DEFAULT_MODEL = "gpt-5-mini"
_DEFAULT_TOKEN_BUDGET = 50_000


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
        # Opinions snapshot — currently static; will move once event-driven
        # opinion updates are built.
        opinions_str = "  ".join(
            f"{pid}:{score:+.2f}"
            for pid, score in sorted(personalities[p.id].opinions.items())
        )
        lines.append(f"  Opinions: {opinions_str}")
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
) -> GameState:
    players = assign_roles(seed=seed)
    print(_render_operator_view(players))

    agents = _build_agents(agents_mode, players, seed, model, token_budget)
    personalities = build_personalities(players)
    choose = make_choose_fn(agents)
    vote = make_vote_fn(agents)
    discard = make_discard_fn(agents)
    enact = make_enact_fn(agents)
    deck = PolicyDeck(seed=seed)

    state = GameState(players=players, president_idx=0)

    for round_num in range(1, rounds + 1):
        president = state.players[state.president_idx]
        candidates = eligible_chancellors(state)
        chosen = nominate_chancellor(state, choose)
        result = vote_chancellor(state, chosen, vote)

        leg: LegislativeSessionResult | None = None
        if result.passed:
            leg = legislative_session(state, deck, president, chosen, discard, enact)
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
        help="Print each player's reasoning and current opinions after each round",
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
        )


if __name__ == "__main__":
    main()
