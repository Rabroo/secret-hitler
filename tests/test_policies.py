import pytest

from src.policies import Policy, PolicyDeck


def test_deck_initial_composition_is_6_liberal_11_fascist():
    deck = PolicyDeck(seed=1)
    # Draw all 17 to inspect composition
    drawn = deck.draw(17)
    assert len(drawn) == 17
    assert drawn.count(Policy.LIBERAL) == 6
    assert drawn.count(Policy.FASCIST) == 11


def test_deck_remaining_decreases_on_draw():
    deck = PolicyDeck(seed=1)
    assert deck.remaining == 17
    deck.draw(3)
    assert deck.remaining == 14


def test_deck_seeded_order_is_deterministic():
    a = PolicyDeck(seed=42).draw(17)
    b = PolicyDeck(seed=42).draw(17)
    assert a == b


def test_deck_different_seeds_produce_different_orders():
    a = PolicyDeck(seed=1).draw(17)
    b = PolicyDeck(seed=2).draw(17)
    assert a != b


def test_deck_discard_increases_discard_pile():
    deck = PolicyDeck(seed=1)
    drawn = deck.draw(3)
    assert deck.discard_size == 0
    deck.discard(drawn)
    assert deck.discard_size == 3


def test_deck_reshuffles_when_draw_pile_too_small():
    deck = PolicyDeck(seed=1)
    # Draw 16 of 17 (leaves 1 in draw pile)
    deck.draw(16)
    assert deck.remaining == 1
    # Discard 4 to set up reshuffle
    deck.discard([Policy.LIBERAL, Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL])
    assert deck.remaining == 1
    assert deck.discard_size == 4
    # Drawing 3 should trigger reshuffle: 1 + 4 = 5 cards available
    drawn = deck.draw(3)
    assert len(drawn) == 3
    assert deck.discard_size == 0  # discard merged back in
    assert deck.remaining == 2     # 5 reshuffled - 3 drawn


def test_deck_reshuffle_uses_seeded_rng():
    a = PolicyDeck(seed=99)
    b = PolicyDeck(seed=99)
    # Drain both identically
    a.draw(16); a.discard([Policy.LIBERAL, Policy.FASCIST])
    b.draw(16); b.discard([Policy.LIBERAL, Policy.FASCIST])
    assert a.draw(3) == b.draw(3)


def test_deck_draw_more_than_total_after_reshuffle_works():
    deck = PolicyDeck(seed=1)
    drawn = deck.draw(17)
    deck.discard(drawn)
    # Now deck is empty; discard has 17. Drawing 3 should reshuffle.
    again = deck.draw(3)
    assert len(again) == 3


def test_policy_enum_has_two_values():
    # Sanity: shouldn't accidentally add a third policy type
    assert {p for p in Policy} == {Policy.LIBERAL, Policy.FASCIST}
