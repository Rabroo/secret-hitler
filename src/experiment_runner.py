"""Run a multi-variant scripted experiment and report per-variant means.

For each variant: create scripted agents, run N games, save per-run JSON
logs + CSVs (via batch_runner._write_aggregate_csvs), then aggregate to a
summary.json with mean predicted_role values per (viewer_role, target_role)
and per (viewer_id, target_id).

See `specs/scripted_experiments.md`. Used by `scenarios/exp_*.py`.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.agents import build_scripted_agents
from src.batch_runner import _write_aggregate_csvs  # type: ignore
from src.runner import start_game


@dataclass
class Variant:
    """One experimental variant.

    Attributes:
        name: Short slug used for the output sub-directory and the summary.
        scripted: dict[player_id, dict[decision_type, value]] — passed to
            build_scripted_agents to override mechanical decisions.
        scenario_kwargs: forwarded to start_game (e.g. forced_roles,
            stack_deck, start_tally, rounds). Merged with shared kwargs at
            run time; per-variant values win on conflicts.
        focus: optional list of (viewer_id, target_id) pairs to highlight in
            the summary table. Defaults to "all bystanders see Pres + Chan".
        apply_until_round: if set, scripted decisions only apply for rounds
            <= this number; later rounds let the LLM play freely.
    """

    name: str
    scripted: dict[int, dict[str, Any]]
    scenario_kwargs: dict[str, Any] = field(default_factory=dict)
    focus: list[tuple[int, int]] | None = None
    apply_until_round: int | None = None


def run_experiment(
    variants: list[Variant],
    n_runs: int,
    output_dir: str | Path,
    *,
    base_seed: int = 1,
    shared_kwargs: dict[str, Any] | None = None,
) -> Path:
    """Run every variant `n_runs` times, save per-variant CSVs + a top-level
    summary.json with mean predicted_roles. Returns output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    shared = dict(shared_kwargs or {})

    summaries: list[dict] = []
    for variant in variants:
        variant_dir = output_dir / variant.name
        variant_dir.mkdir(parents=True, exist_ok=True)
        log_paths: list[Path] = []
        merged_kwargs = {**shared, **variant.scenario_kwargs}
        for i in range(1, n_runs + 1):
            log_path = variant_dir / f"run_{i:03d}.json"
            _run_one(variant, seed=base_seed + i, save_log=str(log_path), **merged_kwargs)
            log_paths.append(log_path)
        _write_aggregate_csvs(log_paths, variant_dir)
        summaries.append(_summarise_variant(variant, log_paths))

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summaries, indent=2))
    _print_summary_table(summaries)
    print(f"\nWrote per-variant CSVs and summary.json to {output_dir}/")
    return output_dir


def _run_one(
    variant: Variant,
    *,
    seed: int,
    save_log: str,
    **start_kwargs: Any,
) -> None:
    import src.runner as runner_module

    real_build_agents = runner_module._build_agents

    def patched(*args, **kwargs):
        base = real_build_agents(*args, **kwargs)
        return build_scripted_agents(
            base,
            variant.scripted,
            apply_until_round=variant.apply_until_round,
        )

    runner_module._build_agents = patched
    try:
        start_kwargs.setdefault("rounds", 1)
        start_kwargs.setdefault("dashboard", False)
        # Override seed/save_log; experiment runner owns those.
        start_kwargs.pop("seed", None)
        start_kwargs.pop("save_log", None)
        start_game(seed=seed, save_log=save_log, **start_kwargs)
    finally:
        runner_module._build_agents = real_build_agents


def _summarise_variant(variant: Variant, log_paths: list[Path]) -> dict:
    """For each (viewer_id, target_id) pair across all runs, compute the
    mean and std of predicted_role at the LAST round of each run."""
    pairs: dict[tuple[int, int], list[float]] = defaultdict(list)
    op_view: dict[str, str] = {}
    for log_path in log_paths:
        log = json.loads(log_path.read_text())
        op_view = log.get("operator_view", {}) or op_view
        rounds = log.get("rounds", [])
        if not rounds:
            continue
        last_round = rounds[-1]
        snap = last_round.get("predicted_roles_after", {})
        for viewer_id_s, predicted in snap.items():
            for target_id_s, score in predicted.items():
                pairs[(int(viewer_id_s), int(target_id_s))].append(float(score))

    rows = []
    for (viewer_id, target_id), values in sorted(pairs.items()):
        rows.append(
            {
                "viewer_id": viewer_id,
                "viewer_role": op_view.get(str(viewer_id), ""),
                "target_id": target_id,
                "target_role": op_view.get(str(target_id), ""),
                "n": len(values),
                "mean": round(statistics.fmean(values), 3) if values else 0.0,
                "stdev": (
                    round(statistics.stdev(values), 3) if len(values) > 1 else 0.0
                ),
            }
        )

    return {
        "variant": variant.name,
        "n_runs": len(log_paths),
        "operator_view": op_view,
        "predicted_roles_last_round": rows,
    }


def _print_summary_table(summaries: list[dict]) -> None:
    """Print a per-variant table. If two or three variants are present,
    also print a delta column for each pair (B − A, C − A)."""
    print("\n" + "=" * 72)
    print("EXPERIMENT SUMMARY — mean predicted_role at end of round")
    print("=" * 72)
    if not summaries:
        print("(no variants)")
        return

    # Index rows by (viewer_id, target_id) for cross-variant alignment.
    keyed: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)
    op_view: dict[str, str] = {}
    for s in summaries:
        op_view.update(s["operator_view"])
        for r in s["predicted_roles_last_round"]:
            keyed[(r["viewer_id"], r["target_id"])][s["variant"]] = r["mean"]

    variant_names = [s["variant"] for s in summaries]
    header = f"{'viewer':>14} {'target':>14}  " + "  ".join(
        f"{n:>10}" for n in variant_names
    )
    if len(variant_names) >= 2:
        header += "  " + "  ".join(
            f"{name}-{variant_names[0]:>}" for name in variant_names[1:]
        )
    print(header)
    print("-" * len(header))

    for (viewer_id, target_id), per_variant in sorted(keyed.items()):
        viewer_label = f"P{viewer_id} {op_view.get(str(viewer_id), '')[:3]}"
        target_label = f"P{target_id} {op_view.get(str(target_id), '')[:3]}"
        means = [per_variant.get(n, 0.0) for n in variant_names]
        line = f"{viewer_label:>14} {target_label:>14}  " + "  ".join(
            f"{m:+10.3f}" for m in means
        )
        if len(variant_names) >= 2:
            base = means[0]
            for m in means[1:]:
                line += f"  {m - base:+10.3f}"
        print(line)
