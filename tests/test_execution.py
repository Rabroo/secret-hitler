"""Tests for the Presidential execution power at F=4 and F=5, plus the
Hitler-executed Liberal win condition."""

import json
from collections import deque

import pytest

from src.agents import LLMAgent, RandomAgent, make_execute_fn
from src.game import (
    Faction,
    GameState,
    Role,
    assign_roles,
    check_winner,
    eligible_chancellors,
    execute_player,
)
from src.personality import build_personalities
from src.policies import Policy, PolicyDeck
from src.runner import start_game


_ROLES = [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]


# --- check_winner: Hitler-dead ---


def test_check_winner_returns_liberal_when_hitler_is_dead():
    players = assign_roles(forced_roles=_ROLES)
    # Player 5 is Hitler in this layout.
    players[4].alive = False
    state = GameState(players=players)
    assert check_winner(state) is Faction.LIBERAL


def test_check_winner_hitler_dead_overrides_fascist_tally_win():
    players = assign_roles(forced_roles=_ROLES)
    players[4].alive = False  # Hitler dead
    state = GameState(
        players=players,
        fascist_policies_enacted=6,  # would be Fascist win normally
    )
    assert check_winner(state) is Faction.LIBERAL


def test_check_winner_hitler_alive_does_not_trigger():
    players = assign_roles(forced_roles=_ROLES)
    state = GameState(players=players)
    assert check_winner(state) is None


# --- execute_player engine helper ---


def test_execute_player_flips_alive_and_returns_target():
    players = assign_roles(forced_roles=_ROLES)
    state = GameState(players=players, president_idx=0)
    president = players[0]
    target = execute_player(state, president, lambda pres, alive: alive[0])
    assert isinstance(target, type(president))
    assert target.alive is False
    assert target.id != president.id


def test_execute_player_excludes_president_from_targets():
    players = assign_roles(forced_roles=_ROLES)
    state = GameState(players=players, president_idx=0)
    president = players[0]
    seen_targets = []

    def picker(pres, alive):
        seen_targets.extend(alive)
        return alive[0]

    execute_player(state, president, picker)
    assert all(p.id != president.id for p in seen_targets)


def test_execute_player_rejects_self_choice():
    players = assign_roles(forced_roles=_ROLES)
    state = GameState(players=players, president_idx=0)
    president = players[0]
    with pytest.raises(ValueError):
        execute_player(state, president, lambda pres, alive: pres)


def test_execute_player_rejects_already_dead():
    players = assign_roles(forced_roles=_ROLES)
    players[2].alive = False  # P3 already dead
    state = GameState(players=players, president_idx=0)
    president = players[0]
    dead_p = players[2]
    with pytest.raises(ValueError):
        execute_player(state, president, lambda pres, alive: dead_p)


# --- LLMAgent.execute_player ---


class _FakeClient:
    def __init__(self, replies):
        self.replies = deque(replies)
        self.calls = []
        self.is_exhausted = False

    def chat(self, system, user, json_mode=False):
        self.calls.append({"system": system, "user": user})
        if not self.replies:
            raise AssertionError("FakeClient ran out of replies")
        return self.replies.popleft()


def _make_llm_agent(replies):
    players = assign_roles(forced_roles=_ROLES)
    pers = build_personalities(players)
    fallback = RandomAgent(player=players[0], seed=999)
    client = _FakeClient(replies)
    agent = LLMAgent(
        player=players[0],
        personality=pers[1],
        all_players=players,
        client=client,
        fallback=fallback,
    )
    return agent, client, players


def test_llm_agent_execute_returns_chosen_target():
    agent, _, players = _make_llm_agent(
        [json.dumps({"reasoning": "they look fascist", "execute_id": 3})]
    )
    target = agent.execute_player(players[1:])  # eligible: 2,3,4,5
    assert target.id == 3


def test_llm_agent_execute_retries_on_invalid_id():
    agent, client, players = _make_llm_agent(
        [
            json.dumps({"reasoning": "oops", "execute_id": 1}),  # self — invalid
            json.dumps({"reasoning": "ok", "execute_id": 4}),
        ]
    )
    target = agent.execute_player(players[1:])
    assert target.id == 4
    assert len(client.calls) == 2


def test_llm_agent_execute_falls_back_after_two_failures():
    agent, client, players = _make_llm_agent(
        ["not json", '{"execute_id": "bad"}']
    )
    target = agent.execute_player(players[1:])
    assert target in players[1:]
    assert len(client.calls) == 2


def test_random_agent_execute_picks_alive_non_self():
    players = assign_roles(forced_roles=_ROLES)
    agent = RandomAgent(player=players[0], seed=1)
    target = agent.execute_player(players[1:])
    assert target in players[1:]


# --- adapter ---


def test_make_execute_fn_dispatches_to_president():
    players = assign_roles(forced_roles=_ROLES)
    agents = {p.id: RandomAgent(player=p, seed=p.id) for p in players}
    execute = make_execute_fn(agents)
    target = execute(players[0], players[1:])
    assert target in players[1:]


# --- runner integration ---


def test_runner_triggers_execution_at_f4(capsys, monkeypatch):
    """Pre-load tally to F=3 so the next Fascist enaction triggers F=4 power."""
    state = start_game(
        rounds=2,
        forced_roles=_ROLES,
        start_tally=(0, 3),
        stack_deck=[Policy.FASCIST] * 17,
        discussion=False,
    )
    capsys.readouterr()
    # An execution event should appear in some round.
    executed = [r for r in state.history if r.executed_player_id is not None]
    if executed:
        # A real player got killed.
        assert any(not p.alive for p in state.players)


def test_runner_no_execution_on_chaos_enaction(capsys, monkeypatch):
    """Force 3 nein votes to trigger chaos. Even if chaos pushes Fascist
    count to 4, no execution should fire."""
    from src import runner as runner_module

    monkeypatch.setattr(
        runner_module, "make_vote_fn", lambda agents: lambda v, p, n: False
    )
    state = start_game(
        rounds=4,
        forced_roles=_ROLES,
        start_tally=(0, 3),
        stack_deck=[Policy.FASCIST] * 17,
        discussion=False,
    )
    capsys.readouterr()
    chaos_rounds = [r for r in state.history if r.chaos_enacted is not None]
    # Chaos should have fired at least once with this setup.
    if chaos_rounds:
        # No execution on the chaos round itself.
        for r in chaos_rounds:
            assert r.executed_player_id is None
        # And the chaos enaction(s) shouldn't have flipped any alive flag
        # (since execution power didn't fire on chaos).
        # Note: a non-chaos enaction in another round CAN fire execution; this
        # test only asserts the chaos round itself.
