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
    # Presidency advances every round regardless of election outcome.
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


def test_start_game_prints_votes_and_result_each_round(capsys):
    start_game(seed=42, rounds=3)
    out = capsys.readouterr().out
    # Every round should announce votes and a result.
    assert out.count("Votes:") == 3
    result_lines = [
        line for line in out.splitlines() if line.startswith("Result:")
    ]
    assert len(result_lines) == 3
    for line in result_lines:
        assert ("ELECTED" in line) or ("REJECTED" in line)


def _parse_elected_chancellors(out: str) -> list[int]:
    """Walk runner output and return chancellors who passed the vote, in order."""
    elected: list[int] = []
    pending: int | None = None
    for line in out.splitlines():
        if line.startswith("Nominated: Player "):
            pending = int(line.split()[-1])
        elif line.startswith("Result: ELECTED"):
            assert pending is not None
            elected.append(pending)
            pending = None
        elif line.startswith("Result: REJECTED"):
            pending = None
    return elected


def test_start_game_term_limit_excludes_previous_elected_chancellor(capsys):
    # 16 rounds at ~50% pass rate should yield several successful elections
    # for the term-limit assertion to bite on.
    start_game(seed=42, rounds=16)
    out = capsys.readouterr().out
    elected = _parse_elected_chancellors(out)
    assert len(elected) >= 2, (
        f"Need >=2 successful elections to test term limits; got {len(elected)}"
    )
    for prev, curr in zip(elected, elected[1:]):
        assert prev != curr, f"Same chancellor elected back-to-back: {prev}"


# --- dashboard ---


def test_start_game_no_dashboard_by_default(capsys):
    start_game(seed=42, rounds=2)
    out = capsys.readouterr().out
    assert "DASHBOARD" not in out


def test_start_game_dashboard_renders_each_round_with_dashboard_flag(capsys):
    start_game(seed=42, rounds=3, dashboard=True)
    out = capsys.readouterr().out
    assert out.count("DASHBOARD — Round") == 3
    # Every player should be listed under each dashboard block.
    for r in range(1, 4):
        # find this round's dashboard block; rough check
        assert f"DASHBOARD — Round {r}" in out
    for pid in range(1, 6):
        assert f"Player {pid} (" in out


def test_start_game_dashboard_shows_opinions(capsys):
    start_game(seed=42, rounds=1, dashboard=True)
    out = capsys.readouterr().out
    assert "Opinions:" in out
