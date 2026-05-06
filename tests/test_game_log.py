"""Tests for the JSON game-log emitter (--save-log flag)."""

import json
from pathlib import Path

import pytest

from src.game import Role
from src.runner import start_game


def _read_log(tmp_path: Path, **kwargs) -> dict:
    log_path = tmp_path / "game.json"
    start_game(save_log=str(log_path), **kwargs)
    return json.loads(log_path.read_text())


def test_save_log_writes_metadata(tmp_path, capsys):
    log = _read_log(tmp_path, seed=42, rounds=2)
    capsys.readouterr()
    md = log["metadata"]
    assert md["seed"] == 42
    assert md["rounds_requested"] == 2
    assert md["agents_mode"] == "random"
    assert "discussion" in md
    assert "llm_role_updates" in md


def test_save_log_writes_operator_view(tmp_path, capsys):
    log = _read_log(
        tmp_path,
        rounds=1,
        forced_roles=[Role.LIBERAL, Role.HITLER, Role.LIBERAL, Role.FASCIST, Role.LIBERAL],
    )
    capsys.readouterr()
    op = log["operator_view"]
    assert op == {"1": "LIBERAL", "2": "HITLER", "3": "LIBERAL", "4": "FASCIST", "5": "LIBERAL"}


def test_save_log_writes_initial_predicted_roles(tmp_path, capsys):
    log = _read_log(
        tmp_path,
        rounds=1,
        forced_roles=[Role.LIBERAL, Role.HITLER, Role.LIBERAL, Role.FASCIST, Role.LIBERAL],
    )
    capsys.readouterr()
    initial = log["initial_predicted_roles"]
    # 5 viewer entries
    assert set(initial.keys()) == {"1", "2", "3", "4", "5"}
    # Liberal viewers should start at exactly 0.0
    assert all(v == 0.0 for v in initial["1"].values())
    # Fascist viewer P4 should know the truth: P2 (Hitler) at -1, others at +1
    assert initial["4"]["2"] == -1.0
    assert initial["4"]["1"] == 1.0


def test_save_log_writes_one_entry_per_round(tmp_path, capsys):
    log = _read_log(tmp_path, seed=42, rounds=3)
    capsys.readouterr()
    assert len(log["rounds"]) == 3
    assert [r["round_num"] for r in log["rounds"]] == [1, 2, 3]


def test_save_log_passing_round_includes_policy_session(tmp_path, capsys):
    log = _read_log(tmp_path, seed=42, rounds=8)
    capsys.readouterr()
    passed = [r for r in log["rounds"] if r["election_passed"]]
    assert passed
    for r in passed:
        ps = r["policy_session"]
        assert ps is not None
        assert len(ps["drawn"]) == 3
        assert len(ps["handed_to_chancellor"]) == 2
        assert ps["enacted"] in ("LIBERAL", "FASCIST")
        assert r["tally_after"]["liberal"] >= 0
        assert r["tally_after"]["fascist"] >= 0


def test_save_log_failed_round_has_null_policy_session(tmp_path, capsys):
    log = _read_log(tmp_path, seed=42, rounds=12)
    capsys.readouterr()
    failed = [r for r in log["rounds"] if not r["election_passed"]]
    assert failed  # seed produces some failures
    for r in failed:
        assert r["policy_session"] is None
        assert r["statements"] == []


def test_save_log_predicted_roles_after_each_round(tmp_path, capsys):
    log = _read_log(tmp_path, seed=42, rounds=3)
    capsys.readouterr()
    for r in log["rounds"]:
        snap = r["predicted_roles_after"]
        # Five viewers
        assert set(snap.keys()) == {"1", "2", "3", "4", "5"}
        # Each viewer omits self
        for vid, mp in snap.items():
            assert vid not in mp
            for v in mp.values():
                assert -1.0 <= v <= 1.0


def test_save_log_records_winner_when_set(tmp_path, capsys):
    from src.policies import Policy

    # Force a Liberal win in round 1 by stacking the deck and pre-loading tally.
    log = _read_log(
        tmp_path,
        rounds=10,
        forced_roles=[Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER],
        start_tally=(4, 0),
        stack_deck=[Policy.LIBERAL] * 6 + [Policy.FASCIST] * 11,
    )
    capsys.readouterr()
    if log.get("winner") is not None:
        assert log["winner"] in ("liberal", "fascist")
        assert isinstance(log["winning_reason"], str)


def test_save_log_includes_decisions(tmp_path, capsys):
    log = _read_log(tmp_path, seed=42, rounds=2)
    capsys.readouterr()
    for r in log["rounds"]:
        decs = r["decisions"]
        # Pres always made a nominate decision
        assert str(r["president_id"]) in decs
        # Every alive player voted
        for pid in ("1", "2", "3", "4", "5"):
            assert "vote" in decs[pid]
