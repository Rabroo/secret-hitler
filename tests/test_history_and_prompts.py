"""Tests for game-history accumulation, history-in-prompt rendering, and
explicit team identity for Hitler / Fascist."""

import pytest

from src.game import (
    GameState,
    Role,
    RoundEvent,
    assign_roles,
)
from src.personality import build_personalities
from src.policies import Policy
from src.prompts import format_history, system_prompt
from src.runner import start_game


# --- RoundEvent + GameState.history -----------------------------------------


def test_round_event_records_expected_fields():
    ev = RoundEvent(
        round_num=1,
        president_id=1,
        chancellor_id=3,
        election_passed=True,
        votes={1: True, 2: False, 3: True, 4: True, 5: False},
        enacted=Policy.LIBERAL,
        liberal_tally=1,
        fascist_tally=0,
    )
    assert ev.round_num == 1
    assert ev.president_id == 1
    assert ev.chancellor_id == 3
    assert ev.election_passed is True
    assert ev.enacted is Policy.LIBERAL


def test_game_state_history_starts_empty():
    players = assign_roles(seed=1)
    state = GameState(players=players)
    assert state.history == []


# --- runner appends history each round --------------------------------------


def test_start_game_appends_one_history_event_per_round(capsys):
    state = start_game(seed=42, rounds=3)
    capsys.readouterr()
    assert len(state.history) == 3
    assert all(isinstance(ev, RoundEvent) for ev in state.history)
    assert [ev.round_num for ev in state.history] == [1, 2, 3]


def test_start_game_history_records_pass_and_fail(capsys):
    state = start_game(seed=42, rounds=12)
    capsys.readouterr()
    # Mix of passing and failing elections at this seed
    passed = [ev for ev in state.history if ev.election_passed]
    failed = [ev for ev in state.history if not ev.election_passed]
    assert passed and failed
    # Failed events have no enacted policy
    for ev in failed:
        assert ev.enacted is None
    for ev in passed:
        assert ev.enacted in (Policy.LIBERAL, Policy.FASCIST)


def test_start_game_history_tally_matches_running_state(capsys):
    state = start_game(seed=42, rounds=8)
    capsys.readouterr()
    # Last event's tally should match final state
    last = state.history[-1]
    assert last.liberal_tally == state.liberal_policies_enacted
    assert last.fascist_tally == state.fascist_policies_enacted


# --- format_history helper --------------------------------------------------


def test_format_history_empty_says_round_1():
    text = format_history([])
    assert "no rounds completed yet" in text.lower()
    assert "round 1" in text.lower()


def test_format_history_includes_current_round_marker_with_history():
    ev = RoundEvent(
        round_num=1,
        president_id=1,
        chancellor_id=3,
        election_passed=True,
        votes={1: True, 2: True, 3: True, 4: True, 5: True},
        enacted=Policy.LIBERAL,
        liberal_tally=1,
        fascist_tally=0,
    )
    text = format_history([ev])
    # After 1 historical round, the current round being played is round 2.
    assert "ROUND 2" in text
    assert "PAST" in text or "past" in text.lower()


def test_format_history_passing_round_shows_gov_and_enaction():
    ev = RoundEvent(
        round_num=1,
        president_id=1,
        chancellor_id=3,
        election_passed=True,
        votes={1: True, 2: True, 3: True, 4: True, 5: True},
        enacted=Policy.LIBERAL,
        liberal_tally=1,
        fascist_tally=0,
    )
    text = format_history([ev])
    assert "Round 1" in text
    assert "P1" in text and "P3" in text
    assert "ELECTED" in text
    assert "LIBERAL" in text.upper()
    assert "L=1" in text and "F=0" in text


def test_format_history_failed_round_shows_rejection_and_voters():
    ev = RoundEvent(
        round_num=2,
        president_id=2,
        chancellor_id=4,
        election_passed=False,
        votes={1: False, 2: True, 3: False, 4: True, 5: False},
        enacted=None,
        liberal_tally=0,
        fascist_tally=0,
    )
    text = format_history([ev])
    assert "REJECTED" in text or "rejected" in text.lower()


# --- system_prompt: history block + team identity ---------------------------


def _liberal_player_and_personality():
    players = assign_roles(
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    )
    pers = build_personalities(players)
    return players[0], pers[1], players  # player_id=1 is Liberal


def _hitler_player_and_personality():
    players = assign_roles(
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    )
    pers = build_personalities(players)
    return players[4], pers[5], players  # player_id=5 is Hitler


def _fascist_player_and_personality():
    players = assign_roles(
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    )
    pers = build_personalities(players)
    return players[2], pers[3], players  # player_id=3 is Fascist


def test_system_prompt_empty_history_marker():
    player, personality, all_players = _liberal_player_and_personality()
    text = system_prompt(player, personality, all_players, history=[])
    assert "GAME HISTORY" in text
    assert "no rounds completed yet" in text.lower()


def test_system_prompt_renders_history_lines():
    player, personality, all_players = _liberal_player_and_personality()
    history = [
        RoundEvent(
            round_num=1,
            president_id=1,
            chancellor_id=3,
            election_passed=True,
            votes={1: True, 2: True, 3: True, 4: True, 5: True},
            enacted=Policy.LIBERAL,
            liberal_tally=1,
            fascist_tally=0,
        )
    ]
    text = system_prompt(player, personality, all_players, history=history)
    assert "Round 1" in text
    assert "ELECTED" in text


def test_system_prompt_hitler_includes_explicit_teammate():
    player, personality, all_players = _hitler_player_and_personality()
    text = system_prompt(player, personality, all_players, history=[])
    # Player 3 is the Fascist in this forced layout
    assert "teammate is Player 3" in text or "Player 3" in text
    assert "win together" in text.lower() or "fascist team" in text.lower()


def test_system_prompt_fascist_includes_explicit_teammate():
    player, personality, all_players = _fascist_player_and_personality()
    text = system_prompt(player, personality, all_players, history=[])
    # Player 5 is Hitler in this forced layout
    assert "teammate is Player 5" in text or "Player 5" in text
    assert "win together" in text.lower() or "fascist team" in text.lower()


def test_system_prompt_liberal_has_no_teammate_line():
    player, personality, all_players = _liberal_player_and_personality()
    text = system_prompt(player, personality, all_players, history=[])
    assert "teammate" not in text.lower()


# --- LLMAgent uses the history reference ------------------------------------


def test_llm_agent_carries_shared_history_reference():
    """If the runner mutates the shared history list, the agent's prompt sees it."""
    import json

    from src.agents import LLMAgent, RandomAgent
    from src.game import RoundEvent

    class FakeClient:
        def __init__(self):
            self.calls = []
            self.is_exhausted = False

        def chat(self, system, user, json_mode=False):
            self.calls.append({"system": system, "user": user})
            return json.dumps({"reasoning": "ok", "choice": 2})

    players = assign_roles(
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    )
    pers = build_personalities(players)
    history: list[RoundEvent] = []
    client = FakeClient()
    agent = LLMAgent(
        player=players[0],
        personality=pers[1],
        all_players=players,
        client=client,
        fallback=RandomAgent(player=players[0], seed=0),
        history=history,
    )
    # Mutate the shared history before the agent decides.
    history.append(
        RoundEvent(
            round_num=1,
            president_id=1,
            chancellor_id=3,
            election_passed=True,
            votes={1: True, 2: True, 3: True, 4: True, 5: True},
            enacted=Policy.LIBERAL,
            liberal_tally=1,
            fascist_tally=0,
        )
    )
    agent.nominate(players[1:])
    assert "Round 1" in client.calls[0]["system"]
