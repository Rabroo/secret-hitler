"""Force a damning event: Fascist President draws FFL, deliberately
discards the Liberal, hands FF to a Liberal Chancellor who has no choice
but to enact a Fascist policy. Then let the LLMs only REACT — statements
+ predicted_role updates. The mechanical decisions are scripted.

What's forced:
- Roles: P1 Fascist (President), P2 Hitler, P3 Liberal, P4 Liberal, P5 Liberal.
- Deck top: F, F, L.
- P1 nominates P3 as Chancellor.
- All 5 vote ja.
- P1 discards the LIBERAL (deliberate fascist play).
- P3 (Liberal Chan) enacts the FASCIST (forced — hand was [F, F]).

What's observed:
- Each player's discussion statement.
- Each Liberal's predicted_roles update.
  - Does P3 (the innocent scapegoated Liberal Chan) get correctly identified
    as Liberal? Or do they catch the blame?
  - Does P1 (the actual Fascist) get correctly suspected?

Run with --llm for real reactions (~$0.05–0.10 per single run).

    python3 -m scenarios.scripted_fascist_president_FFL --llm

    # Batch 10 runs:
    python3 -m scenarios.scripted_fascist_president_FFL --llm --runs 10 \\
        --output-dir /tmp/sh_FascistPres_FFL
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.agents import build_scripted_agents
from src.batch_runner import _write_aggregate_csvs  # type: ignore
from src.game import Role
from src.policies import Policy
from src.runner import start_game


# Roles arranged so P1 is the Fascist (Round 1 President is always P1).
ROLES = [Role.FASCIST, Role.HITLER, Role.LIBERAL, Role.LIBERAL, Role.LIBERAL]

# Top of deck: F, F, L. Pres draws this; discarding the L forces FF to chan.
STACK = (
    [Policy.FASCIST, Policy.FASCIST, Policy.LIBERAL]
    + [Policy.LIBERAL] * 5
    + [Policy.FASCIST] * 9
)

# P1 (Fascist Pres) nominates P3 (Liberal). P1 discards Liberal so P3 is
# stuck with FF. P3 enacts F (forced; explicit script for clarity).
SCRIPT = {
    1: {"nominate": 3, "vote": True, "discard": Policy.LIBERAL},
    2: {"vote": True},
    3: {"vote": True, "enact": Policy.FASCIST},
    4: {"vote": True},
    5: {"vote": True},
}


def run_once(*, llm: bool, seed: int, save_log: str | None = None) -> None:
    import src.runner as runner_module

    real_build_agents = runner_module._build_agents

    def patched(*args, **kwargs):
        base = real_build_agents(*args, **kwargs)
        return build_scripted_agents(base, SCRIPT)

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/tmp/sh_FascistPres_FFL"),
    )
    parser.add_argument("--base-seed", type=int, default=1)
    args = parser.parse_args()

    if args.runs <= 1:
        run_once(llm=args.llm, seed=args.base_seed)
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_paths: list[Path] = []
    for i in range(1, args.runs + 1):
        log_path = args.output_dir / f"run_{i:03d}.json"
        print(f"\n### Run {i}/{args.runs} ###")
        run_once(llm=args.llm, seed=args.base_seed + i, save_log=str(log_path))
        log_paths.append(log_path)
    _write_aggregate_csvs(log_paths, args.output_dir)
    print(f"\nBatch complete: {args.runs} run(s) in {args.output_dir}/")


if __name__ == "__main__":
    main()
