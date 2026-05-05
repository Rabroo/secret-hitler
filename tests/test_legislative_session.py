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
