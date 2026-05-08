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


# --- round-bounded scripting (apply_until_round) ---


def _agent_with_history(scripted, *, apply_until_round, history_ref, role_index=0):
    players = assign_roles(forced_roles=_ROLES)
    fallback = RandomAgent(player=players[role_index], seed=999)
    return ScriptedAgent(
        player=players[role_index],
        fallback=fallback,
        scripted=scripted,
        apply_until_round=apply_until_round,
        history_ref=history_ref,
    ), players


def test_apply_until_round_active_in_round_1():
    """history_ref empty → current_round==1, apply_until_round=1 → scripted wins."""
    history: list = []
    agent, players = _agent_with_history(
        {"nominate": 3}, apply_until_round=1, history_ref=history,
    )
    chosen = agent.nominate(players[1:])
    assert chosen.id == 3
    assert agent.last_nominate_reasoning == "(scripted)"


def test_apply_until_round_falls_through_after_threshold():
    """One completed round in history_ref → current_round==2.
    apply_until_round=1 → scripts ignored, fallback used."""
    history: list = ["fake_round_1_event"]
    agent, players = _agent_with_history(
        {"vote": False},
        apply_until_round=1,
        history_ref=history,
    )
    # vote should NOT be the scripted False — it should come from the fallback
    # RandomAgent (whose reasoning is "(random)").
    agent.vote(players[1], players[2])
    assert agent.last_vote_reasoning == "(random)"


def test_apply_until_round_none_means_always_apply():
    """Default behaviour: scripts apply on every round."""
    history: list = ["r1", "r2", "r3"]  # round 4 now
    agent, players = _agent_with_history(
        {"nominate": 3}, apply_until_round=None, history_ref=history,
    )
    chosen = agent.nominate(players[1:])
    assert chosen.id == 3


def test_apply_until_round_zero_disables_scripts():
    history: list = []
    agent, players = _agent_with_history(
        {"nominate": 3}, apply_until_round=0, history_ref=history,
    )
    chosen = agent.nominate(players[1:])
    # Falls through to RandomAgent — id can be anything in eligible.
    assert chosen in players[1:]
    assert agent.last_nominate_reasoning == "(random)"


def test_build_scripted_agents_passes_apply_until_round():
    from src.agents import build_scripted_agents

    players = assign_roles(forced_roles=_ROLES)
    base = {p.id: RandomAgent(player=p, seed=p.id) for p in players}
    wrapped = build_scripted_agents(
        base, {1: {"nominate": 3}}, apply_until_round=1,
    )
    assert wrapped[1].apply_until_round == 1
