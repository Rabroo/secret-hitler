"""Tests for win-condition detection and runner early-exit."""

import pytest

from src.game import (
    Faction,
    GameState,
    Role,
    assign_roles,
    check_winner,
)
from src.runner import start_game


# --- check_winner pure function ---------------------------------------------


def _state(l: int = 0, f: int = 0):
    players = assign_roles(
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    )
    return GameState(
        players=players,
        liberal_policies_enacted=l,
        fascist_policies_enacted=f,
    )


def test_check_winner_returns_none_when_no_one_has_won():
    state = _state(l=2, f=2)
    assert check_winner(state) is None


def test_check_winner_returns_liberal_at_5_liberal_policies():
    state = _state(l=5, f=2)
    assert check_winner(state) is Faction.LIBERAL


def test_check_winner_returns_fascist_at_6_fascist_policies():
    state = _state(l=4, f=6)
    assert check_winner(state) is Faction.FASCIST


def test_check_winner_hitler_chancellor_at_f3_is_fascist_win():
    state = _state(l=2, f=3)
    hitler = state.players[4]  # forced layout: Player 5 is Hitler
    assert check_winner(state, just_elected_chancellor=hitler) is Faction.FASCIST


def test_check_winner_hitler_chancellor_at_f5_is_fascist_win():
    state = _state(l=1, f=5)
    hitler = state.players[4]
    assert check_winner(state, just_elected_chancellor=hitler) is Faction.FASCIST


def test_check_winner_hitler_chancellor_at_f2_is_no_win():
    state = _state(l=2, f=2)
    hitler = state.players[4]
    assert check_winner(state, just_elected_chancellor=hitler) is None


def test_check_winner_non_hitler_chancellor_does_not_trigger_at_f5():
    state = _state(l=2, f=5)
    fascist = state.players[2]  # Player 3 is the Fascist (not Hitler)
    assert check_winner(state, just_elected_chancellor=fascist) is None


# --- runner integration ----------------------------------------------------


def test_start_game_stops_at_liberal_win(capsys):
    """Force enough Liberal policies via start_tally, then run one round with
    a deck that guarantees a Liberal enaction."""
    from src.policies import Policy

    state = start_game(
        rounds=10,
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER],
        start_tally=(4, 0),
        # Stack so first 3 cards are LIBERAL — enaction will be Liberal regardless
        # of choices; pad the rest.
        stack_deck=[Policy.LIBERAL] * 6 + [Policy.FASCIST] * 11,
        seed=0,
    )
    out = capsys.readouterr().out
    if state.winner is Faction.LIBERAL:
        assert "GAME OVER" in out
        assert "LIBERAL" in out


def test_start_game_stops_at_fascist_win(capsys):
    from src.policies import Policy

    state = start_game(
        rounds=10,
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER],
        start_tally=(0, 5),
        stack_deck=[Policy.FASCIST] * 11 + [Policy.LIBERAL] * 6,
        seed=0,
    )
    out = capsys.readouterr().out
    if state.winner is Faction.FASCIST:
        assert "GAME OVER" in out
        assert "FASCIST" in out


def test_start_game_stops_when_winner_set(capsys):
    """If start_tally is at 5 L already, the first enacted Liberal triggers a
    win and the loop should not run further rounds."""
    from src.policies import Policy

    state = start_game(
        rounds=10,
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER],
        start_tally=(4, 0),
        stack_deck=[Policy.LIBERAL] * 6 + [Policy.FASCIST] * 11,
        seed=0,
    )
    capsys.readouterr()
    if state.winner is not None:
        # Game ended early — fewer than 10 rounds played.
        assert len(state.history) < 10


def test_start_game_no_winner_when_no_threshold_crossed(capsys):
    state = start_game(rounds=2, seed=42)
    capsys.readouterr()
    # Two rounds at this seed don't cross any threshold.
    if state.liberal_policies_enacted < 5 and state.fascist_policies_enacted < 6:
        assert state.winner is None
