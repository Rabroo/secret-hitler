import pytest

from src.game import (
    GameState,
    Role,
    assign_roles,
    eligible_chancellors,
    nominate_chancellor,
)


def test_assign_roles_count_and_composition():
    players = assign_roles(seed=42)
    assert len(players) == 5
    roles = [p.role for p in players]
    assert roles.count(Role.LIBERAL) == 3
    assert roles.count(Role.FASCIST) == 1
    assert roles.count(Role.HITLER) == 1


def test_assign_roles_player_ids_are_1_to_5():
    players = assign_roles(seed=42)
    assert [p.id for p in players] == [1, 2, 3, 4, 5]


def test_assign_roles_seed_is_deterministic():
    a = assign_roles(seed=123)
    b = assign_roles(seed=123)
    assert [p.role for p in a] == [p.role for p in b]


def test_assign_roles_unsupported_player_count_raises():
    with pytest.raises(NotImplementedError):
        assign_roles(num_players=7)


def test_eligible_chancellors_excludes_president():
    players = assign_roles(seed=1)
    state = GameState(players=players, president_idx=0)
    eligible = eligible_chancellors(state)
    assert players[0] not in eligible
    assert len(eligible) == 4


def test_eligible_chancellors_excludes_last_chancellor():
    players = assign_roles(seed=1)
    state = GameState(
        players=players, president_idx=0, last_elected_chancellor_id=3
    )
    eligible_ids = [p.id for p in eligible_chancellors(state)]
    assert 1 not in eligible_ids  # president
    assert 3 not in eligible_ids  # last chancellor
    assert len(eligible_ids) == 3


def test_eligible_chancellors_excludes_dead_players():
    players = assign_roles(seed=1)
    players[2].alive = False  # player id 3 is dead
    state = GameState(players=players, president_idx=0)
    eligible_ids = [p.id for p in eligible_chancellors(state)]
    assert 3 not in eligible_ids


def test_eligible_chancellors_5p_does_not_term_limit_previous_president():
    players = assign_roles(seed=1)
    state = GameState(
        players=players,
        president_idx=0,
        last_elected_president_id=2,  # should still be eligible at 5p
        last_elected_chancellor_id=3,
    )
    eligible_ids = [p.id for p in eligible_chancellors(state)]
    assert 2 in eligible_ids


def test_nominate_chancellor_returns_valid_choice():
    players = assign_roles(seed=1)
    state = GameState(players=players, president_idx=0)
    chosen = nominate_chancellor(state, lambda pres, cands: cands[0])
    assert chosen.id != 1
    assert chosen.alive


def test_nominate_chancellor_rejects_self_nomination():
    players = assign_roles(seed=1)
    state = GameState(players=players, president_idx=0)
    with pytest.raises(ValueError):
        nominate_chancellor(state, lambda pres, cands: pres)


def test_nominate_chancellor_rejects_term_limited_choice():
    players = assign_roles(seed=1)
    state = GameState(
        players=players, president_idx=0, last_elected_chancellor_id=3
    )
    last_chancellor = players[2]
    with pytest.raises(ValueError):
        nominate_chancellor(state, lambda pres, cands: last_chancellor)


def test_nominate_chancellor_rejects_dead_player():
    players = assign_roles(seed=1)
    players[3].alive = False
    state = GameState(players=players, president_idx=0)
    dead_player = players[3]
    with pytest.raises(ValueError):
        nominate_chancellor(state, lambda pres, cands: dead_player)
