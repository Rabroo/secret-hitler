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
    make_vote_fn,
)
from src.game import (
    ElectionResult,
    GameState,
    Player,
    advance_presidency,
    assign_roles,
    eligible_chancellors,
    nominate_chancellor,
    vote_chancellor,
)
from src.personality import build_personalities


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


def _render_round(
    round_num: int,
    president: Player,
    candidates: list[Player],
    chosen: Player,
    result: ElectionResult,
) -> str:
    votes_str = ", ".join(
        f"{pid}={'ja' if v else 'nein'}" for pid, v in sorted(result.votes.items())
    )
    outcome = "ELECTED" if result.passed else "REJECTED"
    return "\n".join(
        [
            f"\n--- Round {round_num} ---",
            f"President: Player {president.id}",
            f"Eligible chancellors: {[p.id for p in candidates]}",
            f"Nominated: Player {chosen.id}",
            f"Votes: {votes_str}",
            f"Result: {outcome} ({result.yes_count} ja, {result.no_count} nein)",
        ]
    )


def start_game(
    seed: int | None = None,
    rounds: int = _DEFAULT_ROUNDS,
    agents_mode: str = _DEFAULT_AGENTS,
    model: str = _DEFAULT_MODEL,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
) -> GameState:
    players = assign_roles(seed=seed)
    print(_render_operator_view(players))

    agents = _build_agents(agents_mode, players, seed, model, token_budget)
    choose = make_choose_fn(agents)
    vote = make_vote_fn(agents)

    state = GameState(players=players, president_idx=0)

    for round_num in range(1, rounds + 1):
        president = state.players[state.president_idx]
        candidates = eligible_chancellors(state)
        chosen = nominate_chancellor(state, choose)
        result = vote_chancellor(state, chosen, vote)
        print(_render_round(round_num, president, candidates, chosen, result))

        if result.passed:
            state.last_elected_president_id = president.id
            state.last_elected_chancellor_id = chosen.id
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

    args = parser.parse_args()
    if args.command == "start":
        start_game(
            seed=args.seed,
            rounds=args.rounds,
            agents_mode=args.agents,
            model=args.model,
            token_budget=args.token_budget,
        )


if __name__ == "__main__":
    main()
