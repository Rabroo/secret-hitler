from collections import deque

import pytest

from src.agents import (
    LLMAgent,
    RandomAgent,
    make_choose_fn,
    make_vote_fn,
)
from src.game import GameState, Player, Role, assign_roles
from src.personality import build_personalities


# --- FakeLLMClient: scripted replies, no network ---


class FakeLLMClient:
    def __init__(self, replies):
        self.replies = deque(replies)
        self.calls = []
        self.is_exhausted = False

    def chat(self, system, user):
        self.calls.append({"system": system, "user": user})
        if not self.replies:
            raise AssertionError("FakeLLMClient ran out of scripted replies")
        return self.replies.popleft()


# --- RandomAgent ---


def test_random_agent_nominate_picks_from_eligible():
    players = assign_roles(seed=1)
    agent = RandomAgent(player=players[0], seed=1)
    eligible = players[1:]
    chosen = agent.nominate(eligible)
    assert chosen in eligible


def test_random_agent_vote_returns_bool():
    players = assign_roles(seed=1)
    agent = RandomAgent(player=players[0], seed=1)
    result = agent.vote(president=players[1], nominee=players[2])
    assert isinstance(result, bool)


def test_random_agent_is_deterministic_for_same_seed():
    players = assign_roles(seed=1)
    a = RandomAgent(player=players[0], seed=7)
    b = RandomAgent(player=players[0], seed=7)
    eligible = players[1:]
    assert a.nominate(eligible).id == b.nominate(eligible).id
    assert a.vote(players[1], players[2]) == b.vote(players[1], players[2])


# --- adapters: agents -> ChooseFn / VoteFn ---


def test_make_choose_fn_dispatches_to_president_agent():
    players = assign_roles(seed=1)
    agents = {p.id: RandomAgent(player=p, seed=1) for p in players}
    choose = make_choose_fn(agents)
    eligible = players[1:]
    chosen = choose(players[0], eligible)
    assert chosen in eligible


def test_make_vote_fn_dispatches_to_voter_agent():
    players = assign_roles(seed=1)
    agents = {p.id: RandomAgent(player=p, seed=p.id) for p in players}
    vote = make_vote_fn(agents)
    result = vote(players[2], players[0], players[1])
    assert isinstance(result, bool)


# --- LLMAgent: prompt + parsing ---


def _make_llm_agent(player, replies, all_players):
    pers = build_personalities(all_players, seed=1)[player.id]
    fallback = RandomAgent(player=player, seed=999)
    client = FakeLLMClient(replies)
    return LLMAgent(
        player=player,
        personality=pers,
        all_players=all_players,
        client=client,
        fallback=fallback,
    ), client


def test_llm_agent_nominate_returns_choice_in_eligible():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(players[0], replies=["3"], all_players=players)
    chosen = agent.nominate(players[1:])
    assert chosen.id == 3


def test_llm_agent_nominate_extracts_integer_from_messy_reply():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(
        players[0], replies=["I pick Player 4 because..."], all_players=players
    )
    chosen = agent.nominate(players[1:])
    assert chosen.id == 4


def test_llm_agent_nominate_retries_on_invalid_then_succeeds():
    players = assign_roles(seed=1)
    # First reply illegal (1 is not in eligible), second reply valid
    agent, client = _make_llm_agent(
        players[0], replies=["1", "2"], all_players=players
    )
    chosen = agent.nominate(players[1:])
    assert chosen.id == 2
    assert len(client.calls) == 2


def test_llm_agent_nominate_falls_back_after_two_failures():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0],
        replies=["banana", "still nonsense"],
        all_players=players,
    )
    chosen = agent.nominate(players[1:])
    assert chosen in players[1:]  # fell back to random
    assert len(client.calls) == 2


def test_llm_agent_vote_parses_ja():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(players[0], replies=["ja"], all_players=players)
    assert agent.vote(players[1], players[2]) is True


def test_llm_agent_vote_parses_nein():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(players[0], replies=["nein"], all_players=players)
    assert agent.vote(players[1], players[2]) is False


def test_llm_agent_vote_case_insensitive():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(players[0], replies=["  JA  "], all_players=players)
    assert agent.vote(players[1], players[2]) is True


def test_llm_agent_vote_retries_on_invalid_then_succeeds():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0], replies=["maybe", "nein"], all_players=players
    )
    assert agent.vote(players[1], players[2]) is False
    assert len(client.calls) == 2


def test_llm_agent_vote_falls_back_after_two_failures():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0], replies=["???", "still ???"], all_players=players
    )
    result = agent.vote(players[1], players[2])
    assert isinstance(result, bool)
    assert len(client.calls) == 2


def test_llm_agent_skips_api_when_budget_exhausted():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0], replies=[], all_players=players
    )
    client.is_exhausted = True
    chosen = agent.nominate(players[1:])
    assert chosen in players[1:]
    assert len(client.calls) == 0  # never hit the API


def test_llm_agent_system_prompt_includes_role_and_personality():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0], replies=["2"], all_players=players
    )
    agent.nominate(players[1:])
    system = client.calls[0]["system"]
    assert f"Player {players[0].id}" in system
    assert players[0].role.value.upper() in system or players[0].role.value in system.lower()
