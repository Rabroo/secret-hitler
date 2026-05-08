# Scenarios

Each script is invoked like:

```
python3 -m scenarios.<name>            # free random mode
python3 -m scenarios.<name> --llm      # real LLM (costs cents)
```

For most situations the CLI flags on `python3 -m src.runner start` are enough:

- `--force-roles "1=LIBERAL,2=LIBERAL,3=FASCIST,4=LIBERAL,5=HITLER"`
- `--start-tally "L=2,F=1"`
- `--stack-deck "F,F,L,L,F,L,F,F,L,F,F,L,F,F,F,L,L"`

Use a script when you need finer control — e.g. comparing two runs that differ only in one decision.

## Visualising a game

Add `--save-log path.json` to any runner invocation to emit a JSON game log, then:

```
pip install streamlit pandas        # one-time, optional dep
streamlit run viewer/streamlit_app.py -- path.json
```

The viewer shows: roster + outcome, per-round bar charts of every player's `predicted_roles` after each round, and a trajectory tab for any (viewer, target) pair across rounds.

## Available scripts

### Experiments (research-framed, scripted)

These force the *exact* sequence of mechanical events (nominate, vote, discard, enact) and run the same setup multiple times so you can collect quantitative data on how the LLMs *react* (statements + predicted_role updates). Each prints a per-variant summary table at the end with means and deltas, and writes per-variant CSVs to `--output-dir`.

- **`exp_forced_vs_deliberate_F`** — *Can the LLM tell deck-driven F enactions apart from deliberately engineered ones?* Variant A: Liberal Pres FFF (forced) → Liberal Chan FF → F. Variant B: Fascist Pres FFL → discards Liberal → Liberal Chan FF → F. Same observable event in both; only the actual Pres role and the discard's intent differ. Headline: bystanders' mean predicted_role[Pres] in A vs B.
- **`exp_chancellor_choice_cost`** — *What does an unforced Fascist enaction cost the Chancellor?* Same gov + same F+L hand both variants; Chancellor enacts L in A, F in B. Headline: Pres's mean predicted_role[Chan] in A vs B (Pres has private knowledge of F+L pass).
- **`exp_tally_pressure`** — *Does the same event get interpreted differently at different boards?* Identical forced F enaction at start_tally L=0,F=0 / L=2,F=2 / L=0,F=3. Headline: bystanders' mean predicted_role[Pres] across the three boards.

Cost: ~$1–1.50 per experiment at gpt-5 with `--runs 10`. Total ~$3.50 for all three.

### Free-decision demos (LLM chooses, no scripting)

These let the LLM choose the mechanical decisions; useful for showing the system works rather than for measuring specific deltas.

- **`force_hitler_chancellor`** — Hitler is the only valid Chancellor; observe whether Liberals approve.
- **`enacted_fascist_at_l0_f0`** — first round of the game, gov enacts a Fascist policy.
- **`round_1_fascist_enact`** — top of deck is FFF; Pres has no Liberal to discard.
- **`voting_under_f3_pressure`** — same setup at F=2 vs F=3 to compare Liberal voting behaviour.
- **`forced_FL_to_chancellor`** — Pres draws FFL → discards F → passes [F, L]; runs Liberal-Chan and Fascist-Chan layouts.
- **`repeat_fascist_enactor`** — multi-round trajectory for a player who ends up in two F-enacting governments.
