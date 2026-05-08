"""Tests for the multi-variant scripted experiment runner."""

import csv
import json
from pathlib import Path

from src.experiment_runner import Variant, run_experiment
from src.game import Role
from src.policies import Policy


_ROLES = [Role.LIBERAL, Role.LIBERAL, Role.FASCIST, Role.LIBERAL, Role.HITLER]


def test_run_experiment_creates_per_variant_directories(tmp_path, capsys):
    variants = [
        Variant(
            name="A",
            scripted={
                1: {"nominate": 3, "vote": True, "discard": Policy.FASCIST},
                2: {"vote": True},
                3: {"vote": True, "enact": Policy.LIBERAL},
                4: {"vote": True},
                5: {"vote": True},
            },
            scenario_kwargs={
                "forced_roles": _ROLES,
                "stack_deck": [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]
                + [Policy.LIBERAL] * 5
                + [Policy.FASCIST] * 9,
            },
        ),
        Variant(
            name="B",
            scripted={
                1: {"nominate": 3, "vote": True, "discard": Policy.FASCIST},
                2: {"vote": True},
                3: {"vote": True, "enact": Policy.FASCIST},
                4: {"vote": True},
                5: {"vote": True},
            },
            scenario_kwargs={
                "forced_roles": _ROLES,
                "stack_deck": [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]
                + [Policy.LIBERAL] * 5
                + [Policy.FASCIST] * 9,
            },
        ),
    ]
    out = run_experiment(
        variants=variants,
        n_runs=2,
        output_dir=tmp_path,
        shared_kwargs={"agents_mode": "random", "discussion": False},
    )
    capsys.readouterr()
    assert out == tmp_path
    for name in ("A", "B"):
        sub = tmp_path / name
        assert sub.is_dir()
        assert (sub / "run_001.json").exists()
        assert (sub / "run_002.json").exists()
        assert (sub / "predicted_roles.csv").exists()
        assert (sub / "decisions.csv").exists()
        assert (sub / "summary.csv").exists()


def test_run_experiment_writes_top_level_summary_json(tmp_path, capsys):
    variants = [
        Variant(
            name="only",
            scripted={
                1: {"nominate": 3, "vote": True, "discard": Policy.FASCIST},
                2: {"vote": True},
                3: {"vote": True, "enact": Policy.LIBERAL},
                4: {"vote": True},
                5: {"vote": True},
            },
            scenario_kwargs={
                "forced_roles": _ROLES,
                "stack_deck": [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]
                + [Policy.LIBERAL] * 5
                + [Policy.FASCIST] * 9,
            },
        )
    ]
    run_experiment(
        variants=variants,
        n_runs=2,
        output_dir=tmp_path,
        shared_kwargs={"agents_mode": "random", "discussion": False},
    )
    capsys.readouterr()
    summary_path = tmp_path / "summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text())
    assert isinstance(summary, list)
    assert len(summary) == 1
    assert summary[0]["variant"] == "only"
    assert summary[0]["n_runs"] == 2
    rows = summary[0]["predicted_roles_last_round"]
    assert all("mean" in r and "stdev" in r for r in rows)


def test_run_experiment_scripts_correctly_apply_to_each_variant(tmp_path, capsys):
    """Variants A and B differ only in the chancellor's enact decision.
    The decisions.csv per variant should reflect that."""
    variants = [
        Variant(
            name="A_picks_L",
            scripted={
                1: {"nominate": 3, "vote": True, "discard": Policy.FASCIST},
                3: {"vote": True, "enact": Policy.LIBERAL},
            },
            scenario_kwargs={
                "forced_roles": _ROLES,
                "stack_deck": [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]
                + [Policy.LIBERAL] * 5
                + [Policy.FASCIST] * 9,
            },
        ),
        Variant(
            name="B_picks_F",
            scripted={
                1: {"nominate": 3, "vote": True, "discard": Policy.FASCIST},
                3: {"vote": True, "enact": Policy.FASCIST},
            },
            scenario_kwargs={
                "forced_roles": _ROLES,
                "stack_deck": [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]
                + [Policy.LIBERAL] * 5
                + [Policy.FASCIST] * 9,
            },
        ),
    ]
    run_experiment(
        variants=variants,
        n_runs=2,
        output_dir=tmp_path,
        shared_kwargs={"agents_mode": "random", "discussion": False},
    )
    capsys.readouterr()

    # Read each variant's decisions.csv and check enact values.
    def _enact_values(name: str) -> list[str]:
        with open(tmp_path / name / "decisions.csv") as f:
            return [
                r["value"]
                for r in csv.DictReader(f)
                if r["decision_type"] == "enact"
            ]

    a_enacts = _enact_values("A_picks_L")
    b_enacts = _enact_values("B_picks_F")
    assert a_enacts and all(v == "LIBERAL" for v in a_enacts)
    assert b_enacts and all(v == "FASCIST" for v in b_enacts)
