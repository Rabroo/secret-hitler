"""Tests for ScriptedAgent: forces mechanical decisions, delegates reactive ones."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.agents import RandomAgent, ScriptedAgent
from src.game import Role, Statement, assign_roles
from src.policies import Policy


_ROLES = [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]


def _agent(scripted, role_index=0):
    players = assign_roles(forced_roles=_ROLES)
    fallback = RandomAgent(player=players[role_index], seed=999)
    return ScriptedAgent(
        player=players[role_index],
        fallback=fallback,
        scripted=scripted,
    ), players


# --- nominate ---


def test_scripted_nominate_returns_scripted_target():
    agent, players = _agent({"nominate": 3})
    chosen = agent.nominate(players[1:])
    assert chosen.id == 3


def test_scripted_nominate_falls_back_when_unscripted():
    agent, players = _agent({})
    chosen = agent.nominate(players[1:])
    assert chosen in players[1:]


def test_scripted_nominate_raises_when_target_not_eligible():
    agent, players = _agent({"nominate": 1})  # P1 is the agent itself
    with pytest.raises(ValueError):
        agent.nominate(players[1:])


# --- vote ---


def test_scripted_vote_returns_scripted_value():
    agent, players = _agent({"vote": False})
    assert agent.vote(players[1], players[2]) is False


def test_scripted_vote_falls_back():
    agent, players = _agent({})
    result = agent.vote(players[1], players[2])
    assert isinstance(result, bool)


# --- discard ---


def test_scripted_discard_returns_scripted_policy():
    agent, _ = _agent({"discard": Policy.LIBERAL})
    chosen = agent.discard_policy([Policy.LIBERAL, Policy.FASCIST, Policy.LIBERAL])
    assert chosen is Policy.LIBERAL


def test_scripted_discard_raises_when_not_in_hand():
    agent, _ = _agent({"discard": Policy.LIBERAL})
    with pytest.raises(ValueError):
        agent.discard_policy([Policy.FASCIST, Policy.FASCIST, Policy.FASCIST])


# --- enact ---


def test_scripted_enact_returns_scripted_policy():
    agent, _ = _agent({"enact": Policy.FASCIST})
    chosen = agent.enact_policy([Policy.LIBERAL, Policy.FASCIST])
    assert chosen is Policy.FASCIST


def test_scripted_enact_raises_when_not_in_hand():
    agent, _ = _agent({"enact": Policy.LIBERAL})
    with pytest.raises(ValueError):
        agent.enact_policy([Policy.FASCIST, Policy.FASCIST])


# --- execute ---


def test_scripted_execute_returns_scripted_target():
    agent, players = _agent({"execute": 4})
    target = agent.execute_player(players[1:])
    assert target.id == 4


def test_scripted_execute_raises_when_target_not_in_list():
    agent, players = _agent({"execute": 1})  # P1 is self, not in eligible
    with pytest.raises(ValueError):
        agent.execute_player(players[1:])


# --- delegated reactive calls ---


def test_scripted_make_statement_always_delegates():
    """ScriptedAgent never overrides make_statement — even if user puts a
    'statement' key in scripted, it should not be used for forcing speech."""
    agent, _ = _agent({"statement": "this should be ignored"})
    stmt = agent.make_statement(
        enacted=Policy.LIBERAL,
        drawn_hand=None,
        chancellor_hand=None,
    )
    # Falls back to RandomAgent which produces "(silent)" placeholder.
    assert isinstance(stmt, Statement)


def test_scripted_update_predicted_roles_always_delegates():
    agent, _ = _agent({"nominate": 3})
    new_map = agent.update_predicted_roles(statements_this_round=[])
    assert isinstance(new_map, dict)


# --- reasoning labelling ---


def test_scripted_decisions_label_reasoning_as_scripted():
    agent, players = _agent(
        {"nominate": 3, "vote": True, "discard": Policy.LIBERAL, "enact": Policy.FASCIST}
    )
    agent.nominate(players[1:])
    agent.vote(players[1], players[2])
    agent.discard_policy([Policy.LIBERAL, Policy.FASCIST, Policy.LIBERAL])
    agent.enact_policy([Policy.LIBERAL, Policy.FASCIST])
    assert agent.last_nominate_reasoning == "(scripted)"
    assert agent.last_vote_reasoning == "(scripted)"
    assert agent.last_discard_reasoning == "(scripted)"
    assert agent.last_enact_reasoning == "(scripted)"


# --- helper: build_scripted_agents ---


def test_build_scripted_agents_wraps_only_listed_players():
    from src.agents import build_scripted_agents

    players = assign_roles(forced_roles=_ROLES)
    base = {p.id: RandomAgent(player=p, seed=p.id) for p in players}
    wrapped = build_scripted_agents(base, {1: {"nominate": 3}})
    assert isinstance(wrapped[1], ScriptedAgent)
    assert wrapped[2] is base[2]  # untouched
    assert wrapped[3] is base[3]
