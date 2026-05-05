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


def test_personality_self_not_in_predicted_roles():
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    for p in players:
        assert p.id not in pers[p.id].predicted_roles


def test_personality_predicted_roles_cover_other_players():
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    for p in players:
        expected_others = {o.id for o in players if o.id != p.id}
        assert set(pers[p.id].predicted_roles.keys()) == expected_others


def test_predicted_roles_clamped_to_unit_range():
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    for p in players:
        for v in pers[p.id].predicted_roles.values():
            assert -1.0 <= v <= 1.0


def test_liberal_initial_predicted_roles_are_exactly_zero():
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    for p in _by_role(players, Role.LIBERAL):
        for v in pers[p.id].predicted_roles.values():
            assert v == 0.0


def test_fascist_team_has_known_truth_in_predicted_roles():
    # New sign convention: +1 = predicted Liberal, -1 = predicted Fascist team.
    # At 5p the Fascist team has full info, so values are pinned at exact truth.
    players = assign_roles(seed=1)
    pers = build_personalities(players, seed=1)
    fascists = _by_role(players, Role.FASCIST)
    hitlers = _by_role(players, Role.HITLER)
    assert len(fascists) == 1 and len(hitlers) == 1
    fascist, hitler = fascists[0], hitlers[0]
    # Each fascist team member predicts the other as Fascist team (-1.0).
    assert pers[fascist.id].predicted_roles[hitler.id] == -1.0
    assert pers[hitler.id].predicted_roles[fascist.id] == -1.0
    # Each fascist team member predicts every Liberal as Liberal (+1.0).
    for liberal in _by_role(players, Role.LIBERAL):
        assert pers[fascist.id].predicted_roles[liberal.id] == 1.0
        assert pers[hitler.id].predicted_roles[liberal.id] == 1.0


def test_personality_is_deterministic_for_same_seed():
    players_a = assign_roles(seed=42)
    pers_a = build_personalities(players_a, seed=42)
    players_b = assign_roles(seed=42)
    pers_b = build_personalities(players_b, seed=42)
    for p in players_a:
        assert pers_a[p.id].desire == pers_b[p.id].desire
        assert pers_a[p.id].predicted_roles == pers_b[p.id].predicted_roles


def test_personality_is_dataclass_with_expected_fields():
    p = Personality(desire=0.5, predicted_roles={2: 0.1, 3: -0.2})
    assert p.desire == 0.5
    assert p.predicted_roles == {2: 0.1, 3: -0.2}
