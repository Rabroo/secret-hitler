# Scenarios

Runnable scripts for inspecting how the agents behave in specific situations.

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

Add `--save-log path.json` to any runner invocation (or run a scenario script and pipe through the runner) to emit a JSON game log, then:

```
pip install streamlit pandas        # one-time, optional dep
streamlit run viewer/streamlit_app.py -- path.json
```

The viewer shows: roster + outcome, per-round bar charts of every player's `predicted_roles` after each round, and a trajectory tab for any (viewer, target) pair across rounds.

## Available scenarios

- **`force_hitler_chancellor`** — Hitler is the only valid Chancellor; observe whether Liberals approve.
- **`enacted_fascist_at_l0_f0`** — first round of the game, gov enacts a Fascist policy. Compare predicted_roles before and after.
- **`round_1_fascist_enact`** — top of deck is FFF; pres has no Liberal to discard; observe how predicted_roles shift on a *forced* Fascist enaction (where the deck is to blame, not intent).
- **`voting_under_f3_pressure`** — runs two games with identical setup, only `start-tally` differing (F=2 vs F=3). At F=3 a Hitler election wins for Fascists, so Liberals should vote much more cautiously. Compare the dashboards.
- **`forced_FL_to_chancellor`** — Pres draws FFL → discards F → passes [F, L]. Two layouts: Liberal Chancellor (likely picks L) vs Fascist Chancellor (likely picks F and lies). Watch how the President's predicted_role of the Chancellor shifts in each.
- **`repeat_fascist_enactor`** — first two rounds forced into F enactions, later draws lean Liberal. Multi-round trajectory of predicted_role for the player who ends up in two F-enacting governments.
