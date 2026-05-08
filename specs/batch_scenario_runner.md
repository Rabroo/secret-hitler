# Spec: Batch Scenario Runner

## Goal
Run a fixed scenario *N* times and emit structured data (CSV + per-run JSON
logs) so the operator can analyse how the LLM's decisions and
`predicted_roles` updates vary across runs of the same setup. Driven by the
operator's research task: "run a scenario 10 times and record what the LLM
decides to do and how it modifies their predicted roles of the other players."

## Inputs / Outputs

**Function signature** (`src/batch_runner.py`):
```python
def run_batch(
    n_runs: int,
    output_dir: str | Path,
    *,
    base_seed: int = 1,
    **start_game_kwargs,
) -> Path:
    """Run start_game n_runs times with the same scenario kwargs. Each run gets
    seed = base_seed + i. Saves per-run JSON logs and aggregated CSVs."""
```

`**start_game_kwargs` mirrors `start_game`: `rounds`, `agents_mode`, `model`,
`token_budget`, `forced_roles`, `start_tally`, `stack_deck`, `discussion`,
`llm_role_updates`, `dashboard`, etc.

**Outputs in `output_dir/`:**
- `run_001.json`, `run_002.json`, … — full game logs identical to what
  `--save-log` produces today.
- `predicted_roles.csv` — long-form table of every per-round
  `predicted_roles` snapshot. Columns:
  `run_id, round_num, viewer_id, viewer_role, target_id, target_role,
   predicted_role, election_passed, enacted_policy, chaos, executed_player_id`.
- `decisions.csv` — long-form table of every decision made by every player.
  Columns:
  `run_id, round_num, player_id, player_role, decision_type, value, reasoning`.
  Decision types: `nominate`, `vote`, `discard`, `enact`, `execute`.
- `summary.csv` — one row per run with `winner, winning_reason, rounds_played,
  final_l_tally, final_f_tally`.

## Why three CSVs
- `predicted_roles.csv` is the analysis target: pivot on `(viewer_role,
  target_role)` to see how Liberals' beliefs about Fascists evolve.
- `decisions.csv` is the data trace: helpful for "did the chancellor pick L
  or F across runs."
- `summary.csv` is the high-level rollup: how often does each side win?

## Reproducibility
- `base_seed=1` by default. Run *i* uses `seed = base_seed + i`.
- This means **two batch invocations with the same `base_seed` and scenario
  kwargs produce identical random-fallback paths** but the LLM stochasticity
  remains (gpt-5 doesn't guarantee identical outputs for identical inputs).
- Pass `base_seed` to vary the seed range across batch invocations.

## CLI
Invocable as:
```bash
python3 -m scenarios.batch_chancellor_FL --runs 10 --output-dir /tmp/sh_FL --llm
```

The provided example scenario `scenarios/batch_chancellor_FL.py` calls
`run_batch` with the FFL→F+L-to-chancellor setup.

## Cost note
At gpt-5, 1 round with full discussion + LLM updates is roughly $0.05–0.10.
A 10-run batch at 1 round each is ~$0.50–1.00. A 10-run batch at 4 rounds
each is ~$2–4. The example script defaults to 1 round to keep cost bounded.

## Out of scope (operator's other notes — separate work)
- Per-player personality scaffolds ("more certain / less certain Liberals"):
  needs new system-prompt parameterisation; separate spec.
- Human-vs-LLM play mode: needs a hidden-information CLI, separate spec.
- Live streamlit dashboard during play: existing post-game viewer is enough
  for now; can extend later if needed.

## Tests
- `run_batch` with `agents_mode="random"`, 3 runs, 1 round → 3 JSON logs + 3
  CSVs exist.
- `predicted_roles.csv` row count = `n_runs × n_rounds × 5 viewers × 4 targets`.
- `decisions.csv` row count = `n_runs × n_rounds × (5 votes + 1 nominate +
  conditionals)` (we just assert a sensible lower bound: at least N rounds × 5
  decisions present).
- `summary.csv` row count = `n_runs`.
- Non-empty winner column when a winning condition is forced.

## Dependencies
Stdlib only (`csv`, `json`, `pathlib`).
