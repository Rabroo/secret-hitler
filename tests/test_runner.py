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
    # for the term-limit assertion to bite on. Chaos enactions reset term
    # limits, so we check the assertion only between consecutive elections
    # that did NOT have a chaos event between them.
    state = start_game(seed=42, rounds=16)
    capsys.readouterr()
    # Walk history in order, tracking the previous elected chancellor and
    # resetting that pointer whenever chaos fires in between.
    prev_elected: int | None = None
    saw_at_least_one_pair = False
    for ev in state.history:
        if ev.chaos_enacted is not None:
            prev_elected = None
        if ev.election_passed:
            if prev_elected is not None:
                saw_at_least_one_pair = True
                assert ev.chancellor_id != prev_elected, (
                    f"Same chancellor elected back-to-back without chaos: "
                    f"{prev_elected}"
                )
            prev_elected = ev.chancellor_id
    assert saw_at_least_one_pair, "Need >=2 chaos-free consecutive elections"


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


def test_start_game_dashboard_shows_predicted_roles(capsys):
    start_game(seed=42, rounds=1, dashboard=True)
    out = capsys.readouterr().out
    assert "Predicted roles:" in out


# --- legislative session integration ---


def test_start_game_runs_legislative_session_after_passing_election(capsys):
    start_game(seed=42, rounds=8)
    out = capsys.readouterr().out
    # At least one election should pass at this seed and trigger an enactment.
    assert "Enacted:" in out


def test_start_game_prints_running_tally(capsys):
    start_game(seed=42, rounds=8)
    out = capsys.readouterr().out
    # Tally line should show after each enacted round.
    assert "Tally:" in out


def test_start_game_no_enactment_when_election_fails(capsys):
    # Force every vote to fail by overriding the start_game internals: we do it
    # by parsing output — count Enacted lines vs ELECTED rounds; should be equal.
    start_game(seed=42, rounds=12)
    out = capsys.readouterr().out
    elected = sum(1 for line in out.splitlines() if line.startswith("Result: ELECTED"))
    enacted = sum(1 for line in out.splitlines() if line.startswith("Enacted:"))
    assert elected == enacted


def test_start_game_force_roles_pins_assignment(capsys):
    from src.game import Role

    start_game(
        rounds=1,
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER],
    )
    out = capsys.readouterr().out
    assert "Player 1: LIBERAL" in out
    assert "Player 3: FASCIST" in out
    assert "Player 5: HITLER" in out


def test_start_game_start_tally_seeds_the_board(capsys):
    start_game(rounds=1, start_tally=(2, 1))
    out = capsys.readouterr().out
    # If round 1 enacts a Liberal we'd see L=3 F=1; either way, never below 2/1.
    import re

    m = re.search(r"Tally:\s*L=(\d+)\s+F=(\d+)", out)
    if m:
        l, f = int(m.group(1)), int(m.group(2))
        assert l >= 2 and f >= 1


def test_start_game_stack_deck_controls_initial_draw(capsys):
    from src.game import Role
    from src.policies import Policy

    # Stack deck so first 3 cards are F,F,F -> guaranteed F enactment if the
    # first election passes. Pad to 17 cards (rest can be anything).
    stack = [Policy.FASCIST] * 3 + [Policy.LIBERAL] * 6 + [Policy.FASCIST] * 8
    start_game(
        seed=42,
        rounds=1,
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER],
        stack_deck=stack,
    )
    out = capsys.readouterr().out
    if "Result: ELECTED" in out:
        assert "Enacted: FASCIST" in out


def test_start_game_tally_never_decreases(capsys):
    start_game(seed=42, rounds=8)
    out = capsys.readouterr().out
    # Extract tallies in order; both counts should be monotonic non-decreasing.
    import re

    pairs: list[tuple[int, int]] = []
    for line in out.splitlines():
        m = re.search(r"Tally:\s*L=(\d+)\s+F=(\d+)", line)
        if m:
            pairs.append((int(m.group(1)), int(m.group(2))))
    assert len(pairs) >= 1
    for prev, curr in zip(pairs, pairs[1:]):
        assert curr[0] >= prev[0]
        assert curr[1] >= prev[1]
