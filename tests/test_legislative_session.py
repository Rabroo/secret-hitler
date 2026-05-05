import pytest

from src.game import (
    GameState,
    LegislativeSessionResult,
    assign_roles,
    legislative_session,
)
from src.policies import Policy, PolicyDeck


def _state_with_government(seed=1, president_id=1, chancellor_id=2):
    players = assign_roles(seed=seed)
    state = GameState(
        players=players,
        president_idx=president_id - 1,
        last_elected_president_id=president_id,
        last_elected_chancellor_id=chancellor_id,
    )
    return state, players[president_id - 1], players[chancellor_id - 1]


def _discard_first(_player, hand):
    return hand[0]


def _enact_first(_player, hand):
    return hand[0]


def test_legislative_session_draws_three_passes_two_enacts_one():
    state, pres, chan = _state_with_government()
    deck = PolicyDeck(seed=1)
    result = legislative_session(state, deck, pres, chan, _discard_first, _enact_first)
    assert isinstance(result, LegislativeSessionResult)
    assert len(result.drawn) == 3
    assert len(result.handed_to_chancellor) == 2
    # Discarded by pres + chancellor combined are 2 of the 3 originally drawn
    leftover = list(result.drawn)
    leftover.remove(result.discarded_by_president)
    assert leftover == result.handed_to_chancellor or sorted(
        leftover, key=lambda p: p.value
    ) == sorted(result.handed_to_chancellor, key=lambda p: p.value)


def test_legislative_session_increments_correct_tally():
    state, pres, chan = _state_with_government()
    deck = PolicyDeck(seed=1)
    result = legislative_session(state, deck, pres, chan, _discard_first, _enact_first)
    if result.enacted is Policy.LIBERAL:
        assert state.liberal_policies_enacted == 1
        assert state.fascist_policies_enacted == 0
    else:
        assert state.fascist_policies_enacted == 1
        assert state.liberal_policies_enacted == 0


def test_legislative_session_sends_both_discards_to_pile():
    state, pres, chan = _state_with_government()
    deck = PolicyDeck(seed=1)
    legislative_session(state, deck, pres, chan, _discard_first, _enact_first)
    # 2 policies discarded (one by pres, one by chancellor)
    assert deck.discard_size == 2


def test_legislative_session_does_not_advance_presidency():
    state, pres, chan = _state_with_government()
    deck = PolicyDeck(seed=1)
    before_idx = state.president_idx
    legislative_session(state, deck, pres, chan, _discard_first, _enact_first)
    assert state.president_idx == before_idx


def test_legislative_session_chancellor_gets_two_after_discard():
    state, pres, chan = _state_with_government()
    deck = PolicyDeck(seed=1)
    seen_by_chancellor: list[list[Policy]] = []

    def chan_fn(_player, hand):
        seen_by_chancellor.append(list(hand))
        return hand[0]

    legislative_session(state, deck, pres, chan, _discard_first, chan_fn)
    assert len(seen_by_chancellor) == 1
    assert len(seen_by_chancellor[0]) == 2


def test_legislative_session_rejects_pres_discard_not_in_hand():
    state, pres, chan = _state_with_government()
    deck = PolicyDeck(seed=1)
    # Force a hand of 3 Fascists by pre-stacking the deck
    deck._draw_pile = [Policy.FASCIST, Policy.FASCIST, Policy.FASCIST]  # noqa: SLF001
    with pytest.raises(ValueError):
        legislative_session(
            state,
            deck,
            pres,
            chan,
            lambda p, hand: Policy.LIBERAL,  # not in the hand
            _enact_first,
        )


def test_legislative_session_rejects_chancellor_enact_not_in_hand():
    state, pres, chan = _state_with_government()
    deck = PolicyDeck(seed=1)
    deck._draw_pile = [Policy.FASCIST, Policy.FASCIST, Policy.FASCIST]  # noqa: SLF001
    with pytest.raises(ValueError):
        legislative_session(
            state,
            deck,
            pres,
            chan,
            _discard_first,
            lambda p, hand: Policy.LIBERAL,
        )


def test_legislative_session_handles_duplicate_policies_in_hand():
    state, pres, chan = _state_with_government()
    deck = PolicyDeck(seed=1)
    # Three Fascists; discard one, hand 2 to chancellor, enact one.
    deck._draw_pile = [Policy.FASCIST, Policy.FASCIST, Policy.FASCIST]  # noqa: SLF001
    result = legislative_session(state, deck, pres, chan, _discard_first, _enact_first)
    assert result.enacted is Policy.FASCIST
    assert state.fascist_policies_enacted == 1
    assert deck.discard_size == 2


# --- update_predicted_roles_after_session ---


def _force_state(roles):
    """Build a state with a specific role assignment."""
    from src.game import GameState, assign_roles

    players = assign_roles(forced_roles=roles)
    state = GameState(players=players, president_idx=0)
    return state, players


def test_update_predicted_roles_liberal_gov_lifts_predictions_toward_liberal():
    from src.game import LegislativeSessionResult, Role, update_predicted_roles_after_session
    from src.personality import build_personalities

    state, players = _force_state(
        [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    )
    pers = build_personalities(players)
    pres, chan = players[0], players[1]  # both liberal
    leg = LegislativeSessionResult(
        drawn=[Policy.LIBERAL, Policy.LIBERAL, Policy.FASCIST],
        discarded_by_president=Policy.FASCIST,
        handed_to_chancellor=[Policy.LIBERAL, Policy.LIBERAL],
        enacted=Policy.LIBERAL,
        discarded_by_chancellor=Policy.LIBERAL,
    )
    # Liberal viewer 4 (a Liberal not in the gov) starts at 0.0 for both gov members.
    viewer = players[3]
    assert pers[viewer.id].predicted_roles[pres.id] == 0.0
    assert pers[viewer.id].predicted_roles[chan.id] == 0.0

    update_predicted_roles_after_session(state, pers, leg, pres, chan)

    # Liberal enaction -> both gov members nudge toward +1 by 0.2.
    assert pers[viewer.id].predicted_roles[pres.id] == pytest.approx(0.2)
    assert pers[viewer.id].predicted_roles[chan.id] == pytest.approx(0.2)


def test_update_predicted_roles_fascist_gov_drops_predictions_toward_fascist():
    from src.game import LegislativeSessionResult, Role, update_predicted_roles_after_session
    from src.personality import build_personalities

    state, players = _force_state(
        [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    )
    pers = build_personalities(players)
    pres, chan = players[0], players[2]  # liberal pres + fascist chan
    leg = LegislativeSessionResult(
        drawn=[Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL],
        discarded_by_president=Policy.LIBERAL,
        handed_to_chancellor=[Policy.FASCIST, Policy.FASCIST],
        enacted=Policy.FASCIST,
        discarded_by_chancellor=Policy.FASCIST,
    )
    viewer = players[3]
    update_predicted_roles_after_session(state, pers, leg, pres, chan)

    # Fascist enaction -> both gov members drop by 0.3.
    assert pers[viewer.id].predicted_roles[pres.id] == pytest.approx(-0.3)
    assert pers[viewer.id].predicted_roles[chan.id] == pytest.approx(-0.3)


def test_update_predicted_roles_does_not_touch_fascist_team_views():
    from src.game import LegislativeSessionResult, Role, update_predicted_roles_after_session
    from src.personality import build_personalities

    state, players = _force_state(
        [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    )
    pers = build_personalities(players)
    fascist = players[2]
    hitler = players[4]
    pres, chan = players[0], players[1]  # liberal/liberal gov

    # Snapshot fascist team views before.
    before_fascist = dict(pers[fascist.id].predicted_roles)
    before_hitler = dict(pers[hitler.id].predicted_roles)

    leg = LegislativeSessionResult(
        drawn=[Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL],
        discarded_by_president=Policy.FASCIST,
        handed_to_chancellor=[Policy.FASCIST, Policy.LIBERAL],
        enacted=Policy.FASCIST,
        discarded_by_chancellor=Policy.LIBERAL,
    )
    update_predicted_roles_after_session(state, pers, leg, pres, chan)

    assert pers[fascist.id].predicted_roles == before_fascist
    assert pers[hitler.id].predicted_roles == before_hitler


def test_update_predicted_roles_does_not_modify_self_view():
    from src.game import LegislativeSessionResult, Role, update_predicted_roles_after_session
    from src.personality import build_personalities

    state, players = _force_state(
        [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    )
    pers = build_personalities(players)
    pres, chan = players[0], players[1]  # both liberal — both update OTHERS' views, not their own
    leg = LegislativeSessionResult(
        drawn=[Policy.LIBERAL, Policy.LIBERAL, Policy.FASCIST],
        discarded_by_president=Policy.FASCIST,
        handed_to_chancellor=[Policy.LIBERAL, Policy.LIBERAL],
        enacted=Policy.LIBERAL,
        discarded_by_chancellor=Policy.LIBERAL,
    )
    update_predicted_roles_after_session(state, pers, leg, pres, chan)
    # President's view of themselves: not in the dict at all.
    assert pres.id not in pers[pres.id].predicted_roles
    # Chancellor's view of themselves: same.
    assert chan.id not in pers[chan.id].predicted_roles


def test_update_predicted_roles_clamps_to_unit_range():
    from src.game import LegislativeSessionResult, Role, update_predicted_roles_after_session
    from src.personality import build_personalities

    state, players = _force_state(
        [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    )
    pers = build_personalities(players)
    # Pre-set viewer's predictions to extremes.
    viewer = players[3]
    pres, chan = players[0], players[1]
    pers[viewer.id].predicted_roles[pres.id] = 0.95  # near max
    pers[viewer.id].predicted_roles[chan.id] = -0.95  # near min

    # Liberal enaction: pushes both up by 0.2 -> 1.0 (clamped) and -0.75.
    leg = LegislativeSessionResult(
        drawn=[Policy.LIBERAL, Policy.LIBERAL, Policy.FASCIST],
        discarded_by_president=Policy.FASCIST,
        handed_to_chancellor=[Policy.LIBERAL, Policy.LIBERAL],
        enacted=Policy.LIBERAL,
        discarded_by_chancellor=Policy.LIBERAL,
    )
    update_predicted_roles_after_session(state, pers, leg, pres, chan)

    assert pers[viewer.id].predicted_roles[pres.id] == 1.0
    assert pers[viewer.id].predicted_roles[chan.id] == pytest.approx(-0.75)
