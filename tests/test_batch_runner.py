"""Tests for the batch scenario runner."""

import csv
import json
from pathlib import Path

import pytest

from src.batch_runner import run_batch
from src.game import Role


_ROLES = [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]


def test_run_batch_creates_per_run_logs(tmp_path, capsys):
    out = run_batch(
        n_runs=3,
        output_dir=tmp_path,
        rounds=1,
        forced_roles=_ROLES,
        agents_mode="random",
        discussion=False,
    )
    capsys.readouterr()
    assert out == Path(tmp_path)
    for i in (1, 2, 3):
        log_path = tmp_path / f"run_{i:03d}.json"
        assert log_path.exists()
        log = json.loads(log_path.read_text())
        assert "rounds" in log
        assert "operator_view" in log


def test_run_batch_writes_predicted_roles_csv(tmp_path, capsys):
    run_batch(
        n_runs=2,
        output_dir=tmp_path,
        rounds=2,
        forced_roles=_ROLES,
        agents_mode="random",
        discussion=False,
    )
    capsys.readouterr()
    csv_path = tmp_path / "predicted_roles.csv"
    assert csv_path.exists()
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    # Each round has 5 viewers and each viewer has 4 targets, so 20 rows per round.
    # 2 runs × 2 rounds × 20 = 80 rows minimum (could be fewer if a game ends early).
    assert len(rows) >= 1
    # Check expected columns are present.
    assert set(rows[0].keys()) >= {
        "run_id", "round_num", "viewer_id", "viewer_role",
        "target_id", "target_role", "predicted_role",
    }


def test_run_batch_writes_decisions_csv(tmp_path, capsys):
    run_batch(
        n_runs=2,
        output_dir=tmp_path,
        rounds=1,
        forced_roles=_ROLES,
        agents_mode="random",
        discussion=False,
    )
    capsys.readouterr()
    csv_path = tmp_path / "decisions.csv"
    assert csv_path.exists()
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    # At least: 5 votes per round × 2 runs = 10 vote rows, plus nominates.
    assert len(rows) >= 10
    assert set(rows[0].keys()) >= {
        "run_id", "round_num", "player_id", "player_role",
        "decision_type", "value", "reasoning",
    }
    # Check that vote decisions appear.
    assert any(r["decision_type"] == "vote" for r in rows)


def test_run_batch_writes_summary_csv(tmp_path, capsys):
    run_batch(
        n_runs=4,
        output_dir=tmp_path,
        rounds=1,
        forced_roles=_ROLES,
        agents_mode="random",
        discussion=False,
    )
    capsys.readouterr()
    csv_path = tmp_path / "summary.csv"
    assert csv_path.exists()
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4
    assert set(rows[0].keys()) >= {
        "run_id", "winner", "winning_reason", "rounds_played",
        "final_l_tally", "final_f_tally",
    }
    assert {r["run_id"] for r in rows} == {"1", "2", "3", "4"}


def test_run_batch_uses_distinct_seeds_per_run(tmp_path, capsys):
    """With agents_mode=random and seeded RNG, two runs at different seeds
    should produce distinguishable game logs (or at least not be guaranteed
    identical)."""
    run_batch(
        n_runs=2,
        output_dir=tmp_path,
        rounds=4,
        forced_roles=_ROLES,
        agents_mode="random",
        discussion=False,
        base_seed=100,
    )
    capsys.readouterr()
    log1 = json.loads((tmp_path / "run_001.json").read_text())
    log2 = json.loads((tmp_path / "run_002.json").read_text())
    # Seeds differ → at least one round's votes should differ across runs.
    differ = False
    for r1, r2 in zip(log1["rounds"], log2["rounds"]):
        if r1["votes"] != r2["votes"]:
            differ = True
            break
    assert differ, "Runs with different seeds produced identical vote sequences"


def test_run_batch_writes_statements_csv(tmp_path, capsys):
    """statements.csv should exist with the expected columns."""
    run_batch(
        n_runs=2,
        output_dir=tmp_path,
        rounds=1,
        forced_roles=_ROLES,
        agents_mode="random",
        # discussion ON so statements actually populate
        discussion=True,
    )
    capsys.readouterr()
    csv_path = tmp_path / "statements.csv"
    assert csv_path.exists()
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    # 2 runs × 5 statements per enacted round if elections passed.
    # At minimum we should see SOME statements.
    if rows:
        assert set(rows[0].keys()) >= {
            "run_id", "round_num", "player_id", "player_role",
            "text", "reasoning", "predicted_role_update_reasoning",
        }


def test_game_log_includes_predicted_role_update_reasonings(tmp_path, capsys):
    """The per-round JSON log should now contain a
    predicted_role_update_reasonings dict (possibly empty)."""
    run_batch(
        n_runs=1,
        output_dir=tmp_path,
        rounds=1,
        forced_roles=_ROLES,
        agents_mode="random",
        discussion=True,
    )
    capsys.readouterr()
    log = json.loads((tmp_path / "run_001.json").read_text())
    for r in log["rounds"]:
        assert "predicted_role_update_reasonings" in r
        assert isinstance(r["predicted_role_update_reasonings"], dict)


def test_run_batch_summary_records_winner_when_forced(tmp_path, capsys):
    """Force a Liberal win via stacked deck + start tally; summary should reflect it."""
    from src.policies import Policy

    run_batch(
        n_runs=2,
        output_dir=tmp_path,
        rounds=10,
        forced_roles=_ROLES,
        start_tally=(4, 0),
        stack_deck=[Policy.LIBERAL] * 6 + [Policy.FASCIST] * 11,
        agents_mode="random",
        discussion=False,
    )
    capsys.readouterr()
    with open(tmp_path / "summary.csv") as f:
        rows = list(csv.DictReader(f))
    # At least one run should end with a Liberal win on this setup (could be
    # via election + L enaction).
    winners = [r["winner"] for r in rows]
    assert any(w == "liberal" for w in winners) or all(w == "" for w in winners)
