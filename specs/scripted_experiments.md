# Spec: Scripted Experiments (Research-Framed Scenarios)

## Goal
Replace the loose collection of scripted "scenarios" with a small set of
**experiments** that each have a clear hypothesis and a measurable outcome.
The previous scripted scenarios were demos — they showed the mechanism
worked but produced no quantitative answer. Each experiment here yields
specific predicted_role deltas you can defend in a write-up.

Drop:
- `scenarios/scripted_fascist_president_FFL.py`
- `scenarios/scripted_FL_chancellor_compare.py`
- `scenarios/batch_chancellor_FL.py`

Keep (free-decision demos, useful for showing the system works):
- `scenarios/force_hitler_chancellor.py`
- `scenarios/forced_FL_to_chancellor.py`
- `scenarios/round_1_fascist_enact.py`
- `scenarios/voting_under_f3_pressure.py`
- `scenarios/enacted_fascist_at_l0_f0.py`
- `scenarios/repeat_fascist_enactor.py`

Add (research experiments, prefix `exp_`):

## Experiment 1 — `exp_forced_vs_deliberate_F.py`
**Question:** Can the LLM tell deck-driven Fascist enactions apart from
deliberately-engineered ones?

**Two variants, run N times each:**
- **A (forced):** Liberal Pres P1 + Liberal Chan P3. Deck top FFF — Pres
  has no Liberal in their hand. P3 receives FF, enacts F. *No player had a
  choice.*
- **B (deliberate):** Fascist Pres P1 + Liberal Chan P3. Deck top FFL —
  Pres deliberately discards the Liberal. P3 receives FF, enacts F. *From
  the bystanders' perspective the observable event is identical to A.*

**Hypothesis:** If discussion + private knowledge actually surface
information, B should produce sharper drops in `predicted_role` of P1 (the
real Fascist) than A. If A and B produce the same predicted_role
distributions, the LLM cannot recover hidden information from observable
events.

**Measured outcome (per variant, averaged over N runs):**
- Bystanders' (P2, P4, P5) `predicted_role[P1]` and `predicted_role[P3]`
  after the round.

## Experiment 2 — `exp_chancellor_choice_cost.py`
**Question:** What does an unforced Fascist enaction cost the Chancellor?

**Two variants:**
- **A (Chancellor picks Liberal):** Liberal Pres + Liberal Chan with F+L
  hand. Chancellor enacts the LIBERAL.
- **B (Chancellor picks Fascist):** Same gov + same hand. Chancellor enacts
  the FASCIST.

The Pres genuinely has private knowledge that the Chancellor had a Liberal
available, which becomes the central fact of the discussion in B.

**Hypothesis:** Chancellor's `predicted_role` falls noticeably more in B
than in A — especially from the President, who has private knowledge.

**Measured outcome:**
- Pres's `predicted_role[Chan]` after the round.
- Bystanders' `predicted_role[Chan]` after the round.
- The delta `(B − A)` is the headline number for this experiment.

## Experiment 3 — `exp_tally_pressure.py`
**Question:** Does the same Fascist enaction get interpreted differently
depending on board state?

**Three variants** of the same forced event (Liberal Pres draws FFF →
Liberal Chan forced FF → enacts F):
- **State 0:** start tally `L=0, F=0`.
- **State M:** start tally `L=2, F=2`.
- **State H:** start tally `L=0, F=3` (Hitler-Chancellor win threshold).

**Hypothesis:** Same event causes increasingly sharp drops in Liberal
predicted_role of the gov as F-tally increases. At F=3 the LLM should
treat the event as critical.

**Measured outcome:**
- Bystanders' `predicted_role[P1]` and `predicted_role[P3]` per state.
- Three-point trajectory: L=0/F=0 → L=2/F=2 → L=0/F=3.

## Output format (all experiments)
Each script's `--runs N --output-dir DIR --llm` produces sub-directories
per variant (e.g. `A_forced/`, `B_deliberate/`) each containing:
- `run_NNN.json` — full game logs.
- `predicted_roles.csv`, `decisions.csv`, `summary.csv` — per
  `src.batch_runner._write_aggregate_csvs`.

After all variants finish, the script prints a **summary table** with the
key per-variant means + deltas. Example:

```
Experiment 1 — forced vs deliberate F enaction
  Variant A (forced):     bystanders' mean predicted_role[P1] = +0.18
  Variant B (deliberate): bystanders' mean predicted_role[P1] = -0.34
  Delta (B − A): -0.52  (B punishes the Pres harder, as hypothesised)
```

## Cost
Each experiment runs 2–3 variants × N runs × 1 round.
At `gpt-5` ~$0.05/round, `--runs 10`:
- Experiment 1 (2 variants): ~$1
- Experiment 2 (2 variants): ~$1
- Experiment 3 (3 variants): ~$1.50

Full triple: **~$3.50 for 80 LLM rounds of data**. Plenty for a clean
write-up.

## Implementation
- New helper `src/experiment_runner.py` exposing
  `run_experiment(variants, n_runs, output_dir, **shared_kwargs)`. Each
  variant is a `(name, scripted_overrides, scenario_kwargs)` tuple.
- Helper writes per-variant CSVs and a `summary.json` with the headline
  numbers.
- Each `exp_*.py` script just declares its variants and calls
  `run_experiment`.

## Out of scope
- Statistical testing (t-tests, etc.) — the operator can do that in pandas
  on the CSVs.
- Visualisation — the existing streamlit viewer reads single-game logs;
  cross-run plotting is downstream pandas work.

## Dependencies
Stdlib only.
