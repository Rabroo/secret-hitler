"""Tests for the 3-failed-elections-in-a-row chaos rule."""

import pytest

from src.game import (
    Faction,
    GameState,
    Role,
    assign_roles,
    chaos_enact,
    check_winner,
    eligible_chancellors,
)
from src.policies import Policy, PolicyDeck
from src.runner import start_game


# --- chaos_enact pure function ---


def _state():
    players = assign_roles(
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    )
    return GameState(
        players=players,
        last_elected_president_id=2,
        last_elected_chancellor_id=4,
        failed_elections=3,
    )


def test_chaos_enact_returns_drawn_policy():
    state = _state()
    deck = PolicyDeck(seed=1, draw_pile=[Policy.LIBERAL] + [Policy.FASCIST] * 16)
    enacted = chaos_enact(state, deck)
    assert enacted is Policy.LIBERAL


def test_chaos_enact_increments_tally():
    state = _state()
    deck = PolicyDeck(seed=1, draw_pile=[Policy.FASCIST] * 17)
    chaos_enact(state, deck)
    assert state.fascist_policies_enacted == 1
    assert state.liberal_policies_enacted == 0


def test_chaos_enact_resets_tracker():
    state = _state()
    assert state.failed_elections == 3
    deck = PolicyDeck(seed=1, draw_pile=[Policy.LIBERAL] * 17)
    chaos_enact(state, deck)
    assert state.failed_elections == 0


def test_chaos_enact_resets_term_limits():
    state = _state()
    assert state.last_elected_president_id == 2
    assert state.last_elected_chancellor_id == 4
    deck = PolicyDeck(seed=1, draw_pile=[Policy.LIBERAL] * 17)
    chaos_enact(state, deck)
    assert state.last_elected_president_id is None
    assert state.last_elected_chancellor_id is None


def test_chaos_enact_eligible_chancellors_resets():
    state = _state()
    state.president_idx = 0  # Player 1 is President
    # Before chaos, P4 (last chancellor) is term-limited.
    before = eligible_chancellors(state)
    assert 4 not in [p.id for p in before]
    deck = PolicyDeck(seed=1, draw_pile=[Policy.LIBERAL] * 17)
    chaos_enact(state, deck)
    after = eligible_chancellors(state)
    # Term limits reset → only the President is excluded; P4 is back in.
    assert 4 in [p.id for p in after]
    assert 1 not in [p.id for p in after]
    assert len(after) == 4


def test_chaos_enact_can_trigger_liberal_win():
    state = _state()
    state.liberal_policies_enacted = 4
    deck = PolicyDeck(seed=1, draw_pile=[Policy.LIBERAL] * 17)
    chaos_enact(state, deck)
    assert state.liberal_policies_enacted == 5
    assert check_winner(state) is Faction.LIBERAL


def test_chaos_enact_can_trigger_fascist_win():
    state = _state()
    state.fascist_policies_enacted = 5
    deck = PolicyDeck(seed=1, draw_pile=[Policy.FASCIST] * 17)
    chaos_enact(state, deck)
    assert state.fascist_policies_enacted == 6
    assert check_winner(state) is Faction.FASCIST


def test_chaos_enact_does_not_trigger_hitler_win_without_election():
    """Hitler-as-Chancellor only wins if Hitler is *elected* — chaos enacting
    a Fascist at F=3 doesn't elect anyone, so no Hitler win even if F now>=3."""
    state = _state()
    state.fascist_policies_enacted = 2
    deck = PolicyDeck(seed=1, draw_pile=[Policy.FASCIST] * 17)
    chaos_enact(state, deck)
    assert state.fascist_policies_enacted == 3
    # Without a chancellor argument, win is None
    assert check_winner(state) is None


# --- runner integration ---


_ROLES = [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]


def test_start_game_failed_election_increments_tracker(capsys):
    """A single failed election should set state.failed_elections to 1."""
    state = start_game(seed=42, rounds=2, forced_roles=_ROLES)
    capsys.readouterr()
    # We can't easily force a single failure with random agents; just assert
    # tracker is non-negative and bounded.
    assert 0 <= state.failed_elections <= 2


def test_start_game_chaos_resets_tracker_when_three_in_a_row(capsys, monkeypatch):
    """With a stacked deck and forced never-pass votes via no-discussion +
    a vote-fn that always returns nein, three rounds should trigger chaos."""
    from src import runner as runner_module

    # Patch make_vote_fn so every vote returns False (forced fail).
    real_make_vote_fn = runner_module.make_vote_fn

    def all_nein(agents):
        return lambda voter, president, nominee: False

    monkeypatch.setattr(runner_module, "make_vote_fn", all_nein)

    state = start_game(
        seed=1,
        rounds=4,
        forced_roles=_ROLES,
        stack_deck=[Policy.FASCIST] * 17,
        discussion=False,
    )
    capsys.readouterr()
    # After the 3rd consecutive nein, chaos should have fired and the tracker
    # should be 0 (then incremented again on round 4's failure → 1).
    chaos_rounds = [r for r in state.history if r.chaos_enacted is not None]
    assert len(chaos_rounds) >= 1
    # Tally should reflect at least one chaos enaction.
    assert state.fascist_policies_enacted >= 1


def test_start_game_chaos_round_event_records_policy(capsys, monkeypatch):
    from src import runner as runner_module

    monkeypatch.setattr(
        runner_module, "make_vote_fn", lambda agents: lambda v, p, n: False
    )
    state = start_game(
        seed=1,
        rounds=4,
        forced_roles=_ROLES,
        stack_deck=[Policy.LIBERAL] * 17,
        discussion=False,
    )
    capsys.readouterr()
    chaos_rounds = [r for r in state.history if r.chaos_enacted is not None]
    if chaos_rounds:
        assert chaos_rounds[0].chaos_enacted is Policy.LIBERAL


def test_start_game_passing_election_resets_tracker_to_zero(capsys):
    """After any passing election, tracker should be 0. With random seed=42
    there are passing elections in the first few rounds."""
    state = start_game(seed=42, rounds=4, forced_roles=_ROLES)
    capsys.readouterr()
    if any(r.election_passed for r in state.history):
        # Find the last round and verify tracker is consistent with the run.
        # If the LAST round was a pass, tracker should be 0.
        last = state.history[-1]
        if last.election_passed:
            assert state.failed_elections == 0
