import pytest

from src.game import (
    ElectionResult,
    GameState,
    assign_roles,
    vote_chancellor,
)


def _all_yes(_voter, _president, _nominee):
    return True


def _all_no(_voter, _president, _nominee):
    return False


def test_vote_passes_with_unanimous_yes():
    players = assign_roles(seed=1)
    state = GameState(players=players, president_idx=0)
    nominee = players[1]
    result = vote_chancellor(state, nominee, _all_yes)
    assert isinstance(result, ElectionResult)
    assert result.passed is True
    assert set(result.votes.keys()) == {1, 2, 3, 4, 5}
    assert all(v is True for v in result.votes.values())


def test_vote_fails_with_unanimous_no():
    players = assign_roles(seed=1)
    state = GameState(players=players, president_idx=0)
    nominee = players[1]
    result = vote_chancellor(state, nominee, _all_no)
    assert result.passed is False
    assert all(v is False for v in result.votes.values())


def test_vote_passes_with_strict_majority():
    players = assign_roles(seed=1)
    state = GameState(players=players, president_idx=0)
    nominee = players[1]
    yes_ids = {1, 3, 5}  # 3 yes vs 2 no
    result = vote_chancellor(
        state, nominee, lambda v, p, n: v.id in yes_ids
    )
    assert result.passed is True
    assert sum(result.votes.values()) == 3


def test_vote_tie_fails():
    players = assign_roles(seed=1)
    players[0].alive = False  # 4 alive -> ties possible
    state = GameState(players=players, president_idx=1)
    nominee = players[2]
    yes_ids = {2, 4}  # 2 yes vs 2 no
    result = vote_chancellor(
        state, nominee, lambda v, p, n: v.id in yes_ids
    )
    assert result.passed is False
    assert sum(result.votes.values()) == 2
    assert len(result.votes) == 4


def test_vote_skips_dead_players():
    players = assign_roles(seed=1)
    players[2].alive = False  # player 3 dead
    state = GameState(players=players, president_idx=0)
    nominee = players[1]
    result = vote_chancellor(state, nominee, _all_yes)
    assert 3 not in result.votes
    assert len(result.votes) == 4


def test_vote_callback_sees_president_and_nominee():
    players = assign_roles(seed=1)
    state = GameState(players=players, president_idx=0)
    nominee = players[2]  # player id 3
    seen = []

    def vote_fn(voter, president, nom):
        seen.append((voter.id, president.id, nom.id))
        return True

    vote_chancellor(state, nominee, vote_fn)

    assert all(p_id == 1 for _, p_id, _ in seen)
    assert all(n_id == 3 for _, _, n_id in seen)
    assert {v_id for v_id, _, _ in seen} == {1, 2, 3, 4, 5}


def test_vote_does_not_mutate_state():
    players = assign_roles(seed=1)
    state = GameState(players=players, president_idx=0)
    nominee = players[1]
    before = (
        state.president_idx,
        state.last_elected_president_id,
        state.last_elected_chancellor_id,
    )
    vote_chancellor(state, nominee, _all_yes)
    after = (
        state.president_idx,
        state.last_elected_president_id,
        state.last_elected_chancellor_id,
    )
    assert before == after


def test_vote_dead_nominee_raises():
    players = assign_roles(seed=1)
    players[1].alive = False
    state = GameState(players=players, president_idx=0)
    with pytest.raises(ValueError):
        vote_chancellor(state, players[1], _all_yes)
