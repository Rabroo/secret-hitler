"""Tests for the discussion round: parallel statements, LLM-driven Liberal
predicted_role updates, history integration, runner wiring."""

import json
from collections import deque

import pytest

from src.agents import LLMAgent, RandomAgent
from src.game import Role, RoundEvent, Statement, assign_roles
from src.personality import build_personalities
from src.policies import Policy
from src.prompts import (
    format_history,
    statement_prompt,
    update_predicted_roles_prompt,
)
from src.runner import start_game


# --- FakeClient ---


class _FakeClient:
    def __init__(self, replies):
        self.replies = deque(replies)
        self.calls = []
        self.is_exhausted = False

    def chat(self, system, user, json_mode=False):
        self.calls.append({"system": system, "user": user})
        if not self.replies:
            raise AssertionError("FakeClient ran out of replies")
        return self.replies.popleft()


def _build_llm_agent(replies, role_index=0, role=None):
    """Build an LLMAgent. Pass `role_index` 0..4 for the seat OR `role`
    (Role.LIBERAL/Role.FASCIST/Role.HITLER) to make Player 1 that role."""
    if role is Role.FASCIST:
        forced = [Role.FASCIST, Role.LIBERAL, Role.LIBERAL, Role.LIBERAL, Role.HITLER]
    elif role is Role.HITLER:
        forced = [Role.HITLER, Role.LIBERAL, Role.LIBERAL, Role.LIBERAL, Role.FASCIST]
    elif role is Role.LIBERAL:
        forced = [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    else:
        forced = [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
    seat = 0 if role is not None else role_index
    players = assign_roles(forced_roles=forced)
    pers = build_personalities(players)
    fallback = RandomAgent(player=players[seat], seed=999)
    client = _FakeClient(replies)
    agent = LLMAgent(
        player=players[seat],
        personality=pers[players[seat].id],
        all_players=players,
        client=client,
        fallback=fallback,
    )
    return agent, client, players


# --- statement_prompt builder ---


def test_statement_prompt_includes_government_and_enaction():
    text = statement_prompt(
        enacted=Policy.LIBERAL,
        drawn_hand=None,
        chancellor_hand=None,
        liberal_tally=1,
        fascist_tally=0,
        president_id=1,
        chancellor_id=3,
    )
    assert "President" in text and "P1" in text
    assert "Chancellor" in text and "P3" in text
    assert "LIBERAL" in text.upper()
    assert "L=1" in text and "F=0" in text


def test_statement_prompt_president_sees_drawn_hand():
    text = statement_prompt(
        enacted=Policy.LIBERAL,
        drawn_hand=[Policy.LIBERAL, Policy.LIBERAL, Policy.FASCIST],
        chancellor_hand=None,
        liberal_tally=1,
        fascist_tally=0,
        president_id=1,
        chancellor_id=3,
    )
    assert "drew" in text.lower()


def test_lie_check_prompt_describes_outing_rules():
    from src.prompts import lie_check_prompt

    text = lie_check_prompt(
        role=Role.HITLER,
        statement_text="I had F and L and chose F.",
        drawn_hand=None,
        chancellor_hand=[Policy.FASCIST, Policy.LIBERAL],
        enacted=Policy.FASCIST,
    )
    lower = text.lower()
    # Must mention each "never admit" rule
    assert "liberal available" in lower
    assert "deliberately discarded" in lower
    assert "vote nein on your own" in lower or "voting nein on your own" in lower
    # Must require the JSON shape we parse
    assert "admits_outing" in text
    assert "rewritten" in text


def test_llm_agent_fascist_statement_runs_self_check_when_admits():
    """If the LLM's first reply admits a Fascist tell, the self-check rewrites it."""
    bad_admission = json.dumps({
        "reasoning": "honest",
        "statement": "I had a Liberal and a Fascist and chose the Fascist.",
    })
    safe_rewrite = json.dumps({
        "admits_outing": True,
        "rewritten": "I was passed two Fascists, no choice.",
    })
    agent, client, _ = _build_llm_agent([bad_admission, safe_rewrite], role=Role.FASCIST)
    stmt = agent.make_statement(
        enacted=Policy.FASCIST,
        drawn_hand=None,
        chancellor_hand=[Policy.FASCIST, Policy.LIBERAL],
        president_id=2,
        chancellor_id=1,
        liberal_tally=0,
        fascist_tally=1,
    )
    # The rewritten statement is what gets broadcast.
    assert "two Fascists" in stmt.text
    assert len(client.calls) == 2  # initial + self-check


def test_llm_agent_fascist_statement_keeps_safe_text_when_no_admission():
    """If the LLM's statement doesn't admit anything, the self-check copies it through."""
    safe_initial = json.dumps({
        "reasoning": "covered",
        "statement": "I was passed two Fascists, no choice.",
    })
    self_check_clean = json.dumps({
        "admits_outing": False,
        "rewritten": "I was passed two Fascists, no choice.",
    })
    agent, client, _ = _build_llm_agent([safe_initial, self_check_clean], role=Role.HITLER)
    stmt = agent.make_statement(
        enacted=Policy.FASCIST,
        drawn_hand=None,
        chancellor_hand=[Policy.FASCIST, Policy.FASCIST],
        president_id=2,
        chancellor_id=1,
        liberal_tally=0,
        fascist_tally=1,
    )
    assert "two Fascists" in stmt.text


def test_llm_agent_liberal_statement_skips_self_check():
    """Liberals don't run the self-check (they have no role to hide)."""
    initial = json.dumps({"reasoning": "honest", "statement": "I drew LLF."})
    agent, client, _ = _build_llm_agent([initial], role=Role.LIBERAL)
    stmt = agent.make_statement(
        enacted=Policy.LIBERAL,
        drawn_hand=[Policy.LIBERAL, Policy.LIBERAL, Policy.FASCIST],
        chancellor_hand=None,
        president_id=1,
        chancellor_id=3,
        liberal_tally=1,
        fascist_tally=0,
    )
    assert stmt.text == "I drew LLF."
    # Only one call — no self-check pass for Liberals.
    assert len(client.calls) == 1


def test_statement_prompt_renders_prior_statements_block():
    text = statement_prompt(
        enacted=Policy.LIBERAL,
        drawn_hand=None,
        chancellor_hand=None,
        liberal_tally=1,
        fascist_tally=0,
        president_id=1,
        chancellor_id=3,
        prior_statements=[
            Statement(player_id=1, text="I drew FLL.", reasoning=""),
            Statement(player_id=3, text="I received LL.", reasoning=""),
        ],
    )
    assert "I drew FLL" in text
    assert "I received LL" in text


def test_statement_prompt_chancellor_sees_chancellor_hand():
    text = statement_prompt(
        enacted=Policy.FASCIST,
        drawn_hand=None,
        chancellor_hand=[Policy.FASCIST, Policy.FASCIST],
        liberal_tally=0,
        fascist_tally=1,
        president_id=1,
        chancellor_id=3,
    )
    assert "received" in text.lower() or "passed" in text.lower()


def test_statement_prompt_bystander_explicitly_forbidden_from_card_claims():
    """A non-government player must be told not to invent a President/
    Chancellor role or any card draw."""
    text = statement_prompt(
        enacted=Policy.LIBERAL,
        drawn_hand=None,
        chancellor_hand=None,
        liberal_tally=1,
        fascist_tally=0,
        president_id=1,
        chancellor_id=2,
    )
    lower = text.lower()
    assert "not in the government" in lower
    assert "no policy cards" in lower or "saw no" in lower
    # Forbid the specific failure mode from the buggy log.
    assert "do not claim" in lower or "do not" in lower
    assert "president" in lower and "chancellor" in lower


def test_statement_prompt_forbids_asking_questions():
    """One-shot parallel discussion — asking 'please explain' is pointless."""
    for kw in [
        dict(drawn_hand=[Policy.LIBERAL] * 3, chancellor_hand=None),
        dict(drawn_hand=None, chancellor_hand=[Policy.LIBERAL] * 2),
        dict(drawn_hand=None, chancellor_hand=None),
    ]:
        text = statement_prompt(
            enacted=Policy.LIBERAL,
            liberal_tally=1,
            fascist_tally=0,
            president_id=1,
            chancellor_id=2,
            **kw,
        )
        lower = text.lower()
        assert "one-shot" in lower or "simultaneously" in lower
        assert "do not ask" in lower or "no one will answer" in lower


def test_statement_prompt_forbids_self_addressing():
    """Players addressed themselves by ID in a buggy run; explicitly forbid."""
    text = statement_prompt(
        enacted=Policy.LIBERAL,
        drawn_hand=None,
        chancellor_hand=None,
        liberal_tally=1,
        fascist_tally=0,
        president_id=1,
        chancellor_id=2,
    )
    assert "do not address yourself" in text.lower()


def test_update_predicted_roles_prompt_requires_every_other_player():
    pers = build_personalities(
        assign_roles(
            forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
        )
    )[1]
    text = update_predicted_roles_prompt(
        current_predicted_roles=pers.predicted_roles,
        statements=[],
    )
    lower = text.lower()
    assert "every other living player" in lower
    for pid in (2, 3, 4, 5):
        assert str(pid) in text


def test_update_predicted_roles_prompt_includes_guidelines():
    pers = build_personalities(
        assign_roles(
            forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
        )
    )[1]
    text = update_predicted_roles_prompt(
        current_predicted_roles=pers.predicted_roles,
        statements=[],
    )
    lower = text.lower()
    assert "liberal enaction" in lower
    assert "fascist enaction" in lower
    assert "flat scores" in lower or "commit" in lower


# --- LLMAgent.make_statement ---


def test_llm_agent_make_statement_returns_text():
    agent, client, _ = _build_llm_agent(
        [json.dumps({"reasoning": "spin", "statement": "Three liberals — clean."})]
    )
    stmt = agent.make_statement(
        enacted=Policy.LIBERAL,
        drawn_hand=[Policy.LIBERAL, Policy.LIBERAL, Policy.LIBERAL],
        chancellor_hand=None,
        president_id=1,
        chancellor_id=3,
        liberal_tally=1,
        fascist_tally=0,
    )
    assert isinstance(stmt, Statement)
    assert "Three liberals" in stmt.text
    assert stmt.player_id == 1


def test_llm_agent_make_statement_uses_caller_provided_gov_not_history():
    """REGRESSION: the agent used to derive pres/chan/tally from
    self.history[-1], which was the PREVIOUS round (history is appended after
    discussion). That made round 2's bystanders read 'President P1 +
    Chancellor P3' even though round 2's actual gov was different.

    The fix: caller passes the current round's gov + tally explicitly. This
    test asserts the prompt sent to the LLM uses the values we passed in,
    NOT anything derived from history.
    """
    agent, client, _ = _build_llm_agent(
        [json.dumps({"reasoning": "ok", "statement": "..."})]
    )
    # Salt history with a round that has DIFFERENT pres/chan/tally to the
    # current call.
    agent.history.append(
        RoundEvent(
            round_num=1,
            president_id=1,
            chancellor_id=3,
            election_passed=True,
            votes={1: True, 2: True, 3: True, 4: True, 5: True},
            enacted=Policy.LIBERAL,
            liberal_tally=1,
            fascist_tally=0,
            statements=[],
        )
    )
    agent.make_statement(
        enacted=Policy.FASCIST,
        drawn_hand=None,
        chancellor_hand=None,
        president_id=2,    # current round's pres (not history's)
        chancellor_id=4,   # current round's chan (not history's)
        liberal_tally=1,
        fascist_tally=1,
    )
    user = client.calls[0]["user"]
    assert "P2" in user and "P4" in user
    # Must NOT see history's gov spuriously rendered as the current round.
    assert "President P1" not in user
    assert "Chancellor P3" not in user
    assert "L=1 F=1" in user


def test_llm_agent_make_statement_falls_back_after_two_failures():
    agent, client, _ = _build_llm_agent(["not json", '{"statement": null}'])
    stmt = agent.make_statement(
        enacted=Policy.LIBERAL, drawn_hand=None, chancellor_hand=None
    )
    assert isinstance(stmt, Statement)
    assert len(client.calls) == 2


def test_llm_agent_make_statement_skips_when_budget_exhausted():
    agent, client, _ = _build_llm_agent([])
    client.is_exhausted = True
    stmt = agent.make_statement(
        enacted=Policy.LIBERAL, drawn_hand=None, chancellor_hand=None
    )
    assert isinstance(stmt, Statement)
    assert len(client.calls) == 0


def test_llm_agent_make_statement_includes_prior_statements_when_given():
    """Chancellor and bystanders see prior_statements (Pres + maybe Chan)."""
    agent, client, _ = _build_llm_agent(
        [json.dumps({"reasoning": "ok", "statement": "Mine."})]
    )
    prior = [Statement(player_id=1, text="Clean draw, three liberals.", reasoning="")]
    agent.make_statement(
        enacted=Policy.LIBERAL,
        drawn_hand=None,
        chancellor_hand=None,
        prior_statements=prior,
    )
    user = client.calls[0]["user"]
    assert "Clean draw, three liberals" in user


def test_llm_agent_make_statement_omits_prior_block_when_none():
    """First speaker (President) sees no prior statements."""
    agent, client, _ = _build_llm_agent(
        [json.dumps({"reasoning": "ok", "statement": "Mine."})]
    )
    agent.make_statement(
        enacted=Policy.LIBERAL,
        drawn_hand=None,
        chancellor_hand=None,
        prior_statements=None,
    )
    user = client.calls[0]["user"]
    assert "Statements made earlier this round" not in user


# --- RandomAgent placeholder behaviour ---


def test_random_agent_make_statement_returns_placeholder():
    players = assign_roles(seed=1)
    agent = RandomAgent(player=players[0], seed=1)
    stmt = agent.make_statement(
        enacted=Policy.LIBERAL, drawn_hand=None, chancellor_hand=None
    )
    assert isinstance(stmt, Statement)
    assert stmt.text != ""


def test_random_agent_update_predicted_roles_is_noop():
    """RandomAgent has no LLM; LLM-driven update doesn't apply. The runner
    should fall back to the heuristic for random mode anyway."""
    players = assign_roles(seed=1)
    agent = RandomAgent(player=players[0], seed=1)
    new_map = agent.update_predicted_roles(statements_this_round=[])
    # Empty / unchanged map is acceptable.
    assert isinstance(new_map, dict)


# --- update_predicted_roles_prompt builder ---


def test_update_predicted_roles_prompt_contains_current_values():
    pers = build_personalities(
        assign_roles(
            forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]
        )
    )[1]
    statements = [
        Statement(player_id=2, text="Trust me", reasoning=""),
        Statement(player_id=3, text="Don't trust 2", reasoning=""),
    ]
    text = update_predicted_roles_prompt(
        current_predicted_roles=pers.predicted_roles,
        statements=statements,
    )
    assert "Trust me" in text
    assert "Don't trust 2" in text
    assert "predicted_roles" in text


# --- LLMAgent.update_predicted_roles ---


def test_llm_agent_update_predicted_roles_applies_returned_map():
    agent, client, players = _build_llm_agent(
        [
            json.dumps(
                {
                    "reasoning": "P3 sounds suspicious",
                    "predicted_roles": {"2": 0.4, "3": -0.5, "4": 0.3, "5": 0.0},
                }
            )
        ],
        role_index=0,  # Liberal at seat 1
    )
    agent.update_predicted_roles(statements_this_round=[])
    assert agent.personality.predicted_roles[2] == pytest.approx(0.4)
    assert agent.personality.predicted_roles[3] == pytest.approx(-0.5)
    assert agent.personality.predicted_roles[4] == pytest.approx(0.3)


def test_llm_agent_update_predicted_roles_clamps_to_unit_range():
    agent, client, players = _build_llm_agent(
        [
            json.dumps(
                {
                    "reasoning": "extreme",
                    "predicted_roles": {"2": 5.0, "3": -10.0},
                }
            )
        ],
        role_index=0,
    )
    agent.update_predicted_roles(statements_this_round=[])
    assert agent.personality.predicted_roles[2] == 1.0
    assert agent.personality.predicted_roles[3] == -1.0


def test_llm_agent_update_predicted_roles_preserves_missing_keys():
    agent, client, players = _build_llm_agent(
        [json.dumps({"reasoning": "no change for P3", "predicted_roles": {"2": 0.5}})],
        role_index=0,
    )
    before = dict(agent.personality.predicted_roles)
    agent.update_predicted_roles(statements_this_round=[])
    # P2 updated; P3, P4, P5 untouched.
    assert agent.personality.predicted_roles[2] == 0.5
    assert agent.personality.predicted_roles[3] == before[3]
    assert agent.personality.predicted_roles[4] == before[4]


def test_llm_agent_update_predicted_roles_falls_back_on_bad_reply():
    agent, client, players = _build_llm_agent(
        ["not json", '{"predicted_roles": "nope"}'],
        role_index=0,
    )
    before = dict(agent.personality.predicted_roles)
    agent.update_predicted_roles(statements_this_round=[])
    # All values preserved.
    assert agent.personality.predicted_roles == before
    assert len(client.calls) == 2


def test_llm_agent_update_predicted_roles_ignores_self_id():
    agent, client, players = _build_llm_agent(
        [
            json.dumps(
                {
                    "reasoning": "trying to set my own value",
                    "predicted_roles": {"1": 0.9, "2": 0.5},
                }
            )
        ],
        role_index=0,  # Player 1
    )
    agent.update_predicted_roles(statements_this_round=[])
    assert 1 not in agent.personality.predicted_roles
    assert agent.personality.predicted_roles[2] == 0.5


# --- format_history extension for statements ---


def test_format_history_renders_statements_block():
    ev = RoundEvent(
        round_num=1,
        president_id=1,
        chancellor_id=3,
        election_passed=True,
        votes={1: True, 2: True, 3: True, 4: True, 5: True},
        enacted=Policy.LIBERAL,
        liberal_tally=1,
        fascist_tally=0,
        statements=[
            Statement(player_id=1, text="Clean draw.", reasoning=""),
            Statement(player_id=2, text="Confirmed.", reasoning=""),
        ],
    )
    text = format_history([ev])
    assert "Clean draw" in text
    assert "Confirmed" in text


def test_format_history_omits_statements_when_empty():
    ev = RoundEvent(
        round_num=2,
        president_id=2,
        chancellor_id=4,
        election_passed=False,
        votes={1: True, 2: True, 3: False, 4: False, 5: False},
        enacted=None,
        liberal_tally=0,
        fascist_tally=0,
        statements=[],
    )
    text = format_history([ev])
    assert "Statements" not in text


# --- runner integration ---


def test_start_game_skips_discussion_with_no_discussion_flag(capsys):
    state = start_game(seed=42, rounds=2, discussion=False)
    capsys.readouterr()
    for ev in state.history:
        assert ev.statements == []


def test_start_game_no_statements_after_failed_election(capsys):
    state = start_game(seed=42, rounds=12)
    capsys.readouterr()
    for ev in state.history:
        if not ev.election_passed:
            assert ev.statements == []


def test_start_game_random_mode_has_placeholder_statements(capsys):
    """Random mode supplies '(random)' placeholders so the dashboard renders."""
    state = start_game(seed=42, rounds=1)
    capsys.readouterr()
    for ev in state.history:
        if ev.election_passed:
            # Five alive players in a fresh 5p game -> five statements.
            assert len(ev.statements) == 5


def test_start_game_dashboard_has_discussion_section(capsys):
    state = start_game(seed=42, rounds=1, dashboard=True)
    out = capsys.readouterr().out
    if state.history and state.history[0].statements:
        assert "DISCUSSION" in out
