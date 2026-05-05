import pytest

from src.game import GameState, advance_presidency, assign_roles
from src.runner import start_game


# --- advance_presidency ---


def test_advance_presidency_rotates_in_seat_order():
    players = assign_roles(seed=1)
    state = GameState(players=players, president_idx=0)
    seen = []
    for _ in range(7):  # one and a bit cycles
        advance_presidency(state)
        seen.append(state.president_idx)
    assert seen == [1, 2, 3, 4, 0, 1, 2]


def test_advance_presidency_wraps_past_last_seat():
    players = assign_roles(seed=1)
    state = GameState(players=players, president_idx=4)
    advance_presidency(state)
    assert state.president_idx == 0


def test_advance_presidency_skips_dead_players():
    players = assign_roles(seed=1)
    players[1].alive = False  # player id 2 dead
    state = GameState(players=players, president_idx=0)
    advance_presidency(state)
    assert state.president_idx == 2  # jumped over player 2


def test_advance_presidency_raises_when_no_alive_players():
    players = assign_roles(seed=1)
    for p in players:
        p.alive = False
    state = GameState(players=players, president_idx=0)
    with pytest.raises(RuntimeError):
        advance_presidency(state)


# --- start_game CLI runner ---


def test_start_game_prints_operator_view_with_all_roles(capsys):
    start_game(seed=42, rounds=5)
    out = capsys.readouterr().out
    assert "OPERATOR VIEW" in out
    for i in range(1, 6):
        assert f"Player {i}:" in out


def test_start_game_runs_requested_number_of_rounds(capsys):
    start_game(seed=42, rounds=8)
    out = capsys.readouterr().out
    for r in range(1, 9):
        assert f"Round {r}" in out
    assert "Round 9" not in out


def test_start_game_president_rotation_is_in_seat_order(capsys):
    start_game(seed=42, rounds=8)
    out = capsys.readouterr().out
    presidents = [
        int(line.split()[-1])
        for line in out.splitlines()
        if line.startswith("President: Player ")
    ]
    assert presidents == [1, 2, 3, 4, 5, 1, 2, 3]


def test_start_game_seed_is_fully_deterministic(capsys):
    start_game(seed=99, rounds=4)
    a = capsys.readouterr().out
    start_game(seed=99, rounds=4)
    b = capsys.readouterr().out
    assert a == b


def test_start_game_term_limit_excludes_previous_chancellor(capsys):
    start_game(seed=42, rounds=4)
    out = capsys.readouterr().out
    lines = out.splitlines()
    nominees = []
    for line in lines:
        if line.startswith("Nominated: Player "):
            nominees.append(int(line.split()[-1]))
    # After round 1, the previous chancellor must not be the new chancellor
    for prev, curr in zip(nominees, nominees[1:]):
        assert prev != curr
