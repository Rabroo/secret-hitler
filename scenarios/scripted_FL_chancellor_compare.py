"""Notes scenario: 'If the President gives the Chancellor F+L policy, the
Chancellor selects a Liberal/Fascist policy — how it affects trust of the
President to the Chancellor.'

Forces the same gov + same hand and runs TWO games:
  GAME A — Chancellor enacts LIBERAL (the safe pick).
  GAME B — Chancellor enacts FASCIST (the damning pick).

What's forced (both games):
- Roles: P1 Liberal, P2 Hitler, P3 Liberal, P4 Liberal, P5 Liberal — wait,
  this layout has no Fascist; we use P3 as the Chancellor and pick a layout
  where P3's role varies between games is expensive. Simpler: keep one
  layout, force the choice, and let the operator compare the two CSV bundles.
  Layout: P1 Liberal, P2 Hitler, P3 Fascist, P4 Liberal, P5 Liberal.
- President is P1 (Liberal), nominates P3.
- All 5 vote ja.
- Deck top: F, F, L. P1 discards F → passes [F, L] to P3.
- P3 enacts FASCIST in Game A; LIBERAL in Game B.

What's observed in each game:
- Discussion + predicted_role updates from all five players.

Run with --llm. Outputs two side-by-side dashboards by default.

    python3 -m scenarios.scripted_FL_chancellor_compare --llm

    # Batch each game N times (separate output dirs):
    python3 -m scenarios.scripted_FL_chancellor_compare --llm --runs 10
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.agents import build_scripted_agents
from src.batch_runner import _write_aggregate_csvs  # type: ignore
from src.game import Role
from src.policies import Policy
from src.runner import start_game


ROLES = [Role.LIBERAL, Role.HITLER, Role.FASCIST, Role.LIBERAL, Role.LIBERAL]

# Top of deck: FFL — President draws all three.
STACK = (
    [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]
    + [Policy.LIBERAL] * 5
    + [Policy.FASCIST] * 9
)


def _script_with_enact(enact: Policy) -> dict:
    return {
        1: {"nominate": 3, "vote": True, "discard": Policy.FASCIST},
        2: {"vote": True},
        3: {"vote": True, "enact": enact},
        4: {"vote": True},
        5: {"vote": True},
    }


def run_once(
    *,
    llm: bool,
    seed: int,
    enact: Policy,
    save_log: str | None = None,
) -> None:
    import src.runner as runner_module

    real_build_agents = runner_module._build_agents
    script = _script_with_enact(enact)

    def patched(*args, **kwargs):
        base = real_build_agents(*args, **kwargs)
        return build_scripted_agents(base, script)

    runner_module._build_agents = patched
    try:
        start_game(
            seed=seed,
            rounds=1,
            agents_mode="llm" if llm else "random",
            model="gpt-5",
            token_budget=200_000,
            forced_roles=ROLES,
            stack_deck=STACK,
            dashboard=True,
            save_log=save_log,
        )
    finally:
        runner_module._build_agents = real_build_agents


def _batch_one_variant(
    *,
    name: str,
    enact: Policy,
    runs: int,
    base_seed: int,
    output_root: Path,
    llm: bool,
) -> Path:
    out = output_root / name
    out.mkdir(parents=True, exist_ok=True)
    log_paths: list[Path] = []
    for i in range(1, runs + 1):
        log_path = out / f"run_{i:03d}.json"
        print(f"\n### {name} run {i}/{runs} ###")
        run_once(llm=llm, seed=base_seed + i, enact=enact, save_log=str(log_path))
        log_paths.append(log_path)
    _write_aggregate_csvs(log_paths, out)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/sh_FL_compare"),
    )
    parser.add_argument("--base-seed", type=int, default=1)
    args = parser.parse_args()

    if args.runs <= 1:
        print("\n" + "#" * 60)
        print("# GAME A — Chancellor enacts FASCIST (damning pick)")
        print("#" * 60)
        run_once(llm=args.llm, seed=args.base_seed, enact=Policy.FASCIST)
        print("\n" + "#" * 60)
        print("# GAME B — Chancellor enacts LIBERAL (safe pick)")
        print("#" * 60)
        run_once(llm=args.llm, seed=args.base_seed, enact=Policy.LIBERAL)
        return

    out_a = _batch_one_variant(
        name="A_chan_picks_F",
        enact=Policy.FASCIST,
        runs=args.runs,
        base_seed=args.base_seed,
        output_root=args.output_dir,
        llm=args.llm,
    )
    out_b = _batch_one_variant(
        name="B_chan_picks_L",
        enact=Policy.LIBERAL,
        runs=args.runs,
        base_seed=args.base_seed,
        output_root=args.output_dir,
        llm=args.llm,
    )
    print(f"\nGame A (Fascist enacted): {out_a}/")
    print(f"Game B (Liberal enacted): {out_b}/")
    print(
        "Compare the two predicted_roles.csv files for how the Chancellor's "
        "choice changed everyone's read of them."
    )


if __name__ == "__main__":
    main()
