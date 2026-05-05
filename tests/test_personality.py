from src.game import Role, assign_roles
from src.personality import Personality, build_personalities


def _by_role(players, role):
    return [p for p in players if p.role is role]


def test_liberal_desire_is_exactly_plus_one():
    # Sign convention: +1 = Liberal-aligned, -1 = Fascist-aligned. No noise.
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    for p in _by_role(players, Role.LIBERAL):
        assert pers[p.id].desire == 1.0


def test_fascist_and_hitler_desire_is_exactly_minus_one():
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    for p in _by_role(players, Role.FASCIST):
        assert pers[p.id].desire == -1.0
    for p in _by_role(players, Role.HITLER):
        assert pers[p.id].desire == -1.0


def test_personality_self_not_in_opinions():
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    for p in players:
        assert p.id not in pers[p.id].opinions


def test_personality_opinions_cover_other_players():
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    for p in players:
        expected_others = {o.id for o in players if o.id != p.id}
        assert set(pers[p.id].opinions.keys()) == expected_others


def test_opinions_clamped_to_unit_range():
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    for p in players:
        for v in pers[p.id].opinions.values():
            assert -1.0 <= v <= 1.0


def test_liberal_initial_opinions_are_exactly_zero():
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    for p in _by_role(players, Role.LIBERAL):
        for v in pers[p.id].opinions.values():
            assert v == 0.0


def test_fascist_team_has_perfect_information_at_5p():
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    fascists = _by_role(players, Role.FASCIST)
    hitlers = _by_role(players, Role.HITLER)
    assert len(fascists) == 1 and len(hitlers) == 1
    fascist, hitler = fascists[0], hitlers[0]
    # +1.0: known ally (told by rules).
    assert pers[fascist.id].opinions[hitler.id] == 1.0
    assert pers[hitler.id].opinions[fascist.id] == 1.0
    # -1.0: known opponents (deduced by elimination at 5p).
    for liberal in _by_role(players, Role.LIBERAL):
        assert pers[fascist.id].opinions[liberal.id] == -1.0
        assert pers[hitler.id].opinions[liberal.id] == -1.0


def test_personality_is_deterministic_for_same_seed():
    players_a = assign_roles(seed=42)
    pers_a = build_personalities(players_a, seed=42)
    players_b = assign_roles(seed=42)
    pers_b = build_personalities(players_b, seed=42)
    for p in players_a:
        assert pers_a[p.id].desire == pers_b[p.id].desire
        assert pers_a[p.id].opinions == pers_b[p.id].opinions


def test_personality_is_dataclass_with_expected_fields():
    p = Personality(desire=0.5, opinions={2: 0.1, 3: -0.2})
    assert p.desire == 0.5
    assert p.opinions == {2: 0.1, 3: -0.2}
