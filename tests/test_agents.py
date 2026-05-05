import json
from collections import deque

from src.agents import (
    LLMAgent,
    RandomAgent,
    make_choose_fn,
    make_discard_fn,
    make_enact_fn,
    make_vote_fn,
)
from src.game import GameState, Player, Role, assign_roles
from src.personality import build_personalities
from src.policies import Policy


# --- FakeLLMClient: scripted JSON replies, no network ---


class FakeLLMClient:
    def __init__(self, replies):
        # Each reply is a string the client will return verbatim. Tests pass
        # JSON strings to mirror real LLM responses with response_format=json.
        self.replies = deque(replies)
        self.calls = []
        self.is_exhausted = False

    def chat(self, system, user, json_mode=False):
        self.calls.append({"system": system, "user": user, "json_mode": json_mode})
        if not self.replies:
            raise AssertionError("FakeLLMClient ran out of scripted replies")
        return self.replies.popleft()


def _nom(reasoning: str, choice: int) -> str:
    return json.dumps({"reasoning": reasoning, "choice": choice})


def _vote(reasoning: str, vote: str) -> str:
    return json.dumps({"reasoning": reasoning, "vote": vote})


def _discard(reasoning: str, idx: int) -> str:
    return json.dumps({"reasoning": reasoning, "discard_index": idx})


def _enact(reasoning: str, idx: int) -> str:
    return json.dumps({"reasoning": reasoning, "enact_index": idx})


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


def test_random_agent_populates_reasoning_placeholder():
    players = assign_roles(seed=1)
    agent = RandomAgent(player=players[0], seed=1)
    agent.nominate(players[1:])
    agent.vote(players[1], players[2])
    agent.discard_policy([Policy.FASCIST, Policy.LIBERAL, Policy.FASCIST])
    agent.enact_policy([Policy.FASCIST, Policy.LIBERAL])
    assert agent.last_nominate_reasoning != ""
    assert agent.last_vote_reasoning != ""
    assert agent.last_discard_reasoning != ""
    assert agent.last_enact_reasoning != ""


def test_random_agent_discard_returns_policy_in_hand():
    players = assign_roles(seed=1)
    agent = RandomAgent(player=players[0], seed=1)
    hand = [Policy.FASCIST, Policy.LIBERAL, Policy.FASCIST]
    chosen = agent.discard_policy(hand)
    assert chosen in hand


def test_random_agent_enact_returns_policy_in_hand():
    players = assign_roles(seed=1)
    agent = RandomAgent(player=players[0], seed=1)
    hand = [Policy.FASCIST, Policy.LIBERAL]
    chosen = agent.enact_policy(hand)
    assert chosen in hand


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


def test_make_discard_fn_dispatches_to_president_agent():
    players = assign_roles(seed=1)
    agents = {p.id: RandomAgent(player=p, seed=p.id) for p in players}
    discard = make_discard_fn(agents)
    hand = [Policy.FASCIST, Policy.LIBERAL, Policy.FASCIST]
    chosen = discard(players[0], hand)
    assert chosen in hand


def test_make_enact_fn_dispatches_to_chancellor_agent():
    players = assign_roles(seed=1)
    agents = {p.id: RandomAgent(player=p, seed=p.id) for p in players}
    enact = make_enact_fn(agents)
    hand = [Policy.FASCIST, Policy.LIBERAL]
    chosen = enact(players[1], hand)
    assert chosen in hand


# --- LLMAgent: JSON prompt + parsing ---


def _make_llm_agent(player, replies, all_players):
    pers = build_personalities(all_players)[player.id]
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
    agent, _ = _make_llm_agent(
        players[0], replies=[_nom("known ally", 3)], all_players=players
    )
    chosen = agent.nominate(players[1:])
    assert chosen.id == 3


def test_llm_agent_nominate_stores_reasoning():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(
        players[0],
        replies=[_nom("Player 3 is my known ally", 3)],
        all_players=players,
    )
    agent.nominate(players[1:])
    assert "known ally" in agent.last_nominate_reasoning


def test_llm_agent_nominate_retries_on_invalid_then_succeeds():
    players = assign_roles(seed=1)
    # First reply has illegal choice (1 is the President), second is valid
    agent, client = _make_llm_agent(
        players[0],
        replies=[_nom("oops", 1), _nom("valid pick", 2)],
        all_players=players,
    )
    chosen = agent.nominate(players[1:])
    assert chosen.id == 2
    assert len(client.calls) == 2


def test_llm_agent_nominate_falls_back_after_two_failures():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0],
        replies=["not even json", '{"choice": "banana"}'],
        all_players=players,
    )
    chosen = agent.nominate(players[1:])
    assert chosen in players[1:]
    assert len(client.calls) == 2
    assert "fallback" in agent.last_nominate_reasoning.lower()


def test_llm_agent_vote_parses_ja():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(
        players[0], replies=[_vote("looks fine", "ja")], all_players=players
    )
    assert agent.vote(players[1], players[2]) is True


def test_llm_agent_vote_parses_nein():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(
        players[0], replies=[_vote("don't trust them", "nein")], all_players=players
    )
    assert agent.vote(players[1], players[2]) is False


def test_llm_agent_vote_case_insensitive():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(
        players[0],
        replies=[json.dumps({"reasoning": "ok", "vote": "  JA  "})],
        all_players=players,
    )
    assert agent.vote(players[1], players[2]) is True


def test_llm_agent_vote_stores_reasoning():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(
        players[0],
        replies=[_vote("president looks suspicious", "nein")],
        all_players=players,
    )
    agent.vote(players[1], players[2])
    assert "suspicious" in agent.last_vote_reasoning


def test_llm_agent_vote_retries_on_invalid_then_succeeds():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0],
        replies=[_vote("hmm", "maybe"), _vote("ok", "nein")],
        all_players=players,
    )
    assert agent.vote(players[1], players[2]) is False
    assert len(client.calls) == 2


def test_llm_agent_vote_falls_back_after_two_failures():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0],
        replies=["not json", '{"vote": null}'],
        all_players=players,
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
    assert len(client.calls) == 0


def test_llm_agent_system_prompt_includes_role_and_personality():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0], replies=[_nom("ok", 2)], all_players=players
    )
    agent.nominate(players[1:])
    system = client.calls[0]["system"]
    assert f"Player {players[0].id}" in system
    assert players[0].role.value.upper() in system or players[0].role.value in system.lower()


def test_llm_agent_calls_with_json_mode():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0], replies=[_nom("ok", 2)], all_players=players
    )
    agent.nominate(players[1:])
    assert client.calls[0]["json_mode"] is True


# --- LLMAgent: policy discard / enact ---


def test_llm_agent_discard_returns_indexed_policy():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(
        players[0],
        replies=[_discard("toss the liberal", 2)],
        all_players=players,
    )
    hand = [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]
    chosen = agent.discard_policy(hand)
    assert chosen is Policy.LIBERAL


def test_llm_agent_discard_stores_reasoning():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(
        players[0],
        replies=[_discard("burying the liberal", 2)],
        all_players=players,
    )
    agent.discard_policy([Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL])
    assert "burying" in agent.last_discard_reasoning


def test_llm_agent_discard_retries_on_out_of_range_index():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0],
        replies=[_discard("oops", 7), _discard("ok", 0)],
        all_players=players,
    )
    chosen = agent.discard_policy([Policy.FASCIST, Policy.LIBERAL, Policy.LIBERAL])
    assert chosen is Policy.FASCIST
    assert len(client.calls) == 2


def test_llm_agent_discard_falls_back_after_two_failures():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0],
        replies=["not json", '{"discard_index": "nope"}'],
        all_players=players,
    )
    hand = [Policy.FASCIST, Policy.LIBERAL, Policy.FASCIST]
    chosen = agent.discard_policy(hand)
    assert chosen in hand
    assert len(client.calls) == 2
    assert "fallback" in agent.last_discard_reasoning.lower()


def test_llm_agent_enact_returns_indexed_policy():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(
        players[0],
        replies=[_enact("enacting the liberal", 1)],
        all_players=players,
    )
    chosen = agent.enact_policy([Policy.FASCIST, Policy.LIBERAL])
    assert chosen is Policy.LIBERAL


def test_llm_agent_enact_stores_reasoning():
    players = assign_roles(seed=1)
    agent, _ = _make_llm_agent(
        players[0],
        replies=[_enact("liberal best", 1)],
        all_players=players,
    )
    agent.enact_policy([Policy.FASCIST, Policy.LIBERAL])
    assert "liberal" in agent.last_enact_reasoning.lower()


def test_llm_agent_enact_retries_on_out_of_range_index():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0],
        replies=[_enact("oops", 7), _enact("ok", 0)],
        all_players=players,
    )
    chosen = agent.enact_policy([Policy.LIBERAL, Policy.FASCIST])
    assert chosen is Policy.LIBERAL
    assert len(client.calls) == 2


def test_llm_agent_enact_falls_back_after_two_failures():
    players = assign_roles(seed=1)
    agent, client = _make_llm_agent(
        players[0],
        replies=["not json", '{"enact_index": null}'],
        all_players=players,
    )
    hand = [Policy.FASCIST, Policy.LIBERAL]
    chosen = agent.enact_policy(hand)
    assert chosen in hand
    assert len(client.calls) == 2
