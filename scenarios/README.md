# Scenarios

Runnable scripts for inspecting how the agents behave in specific situations.

Each script is invoked like:

```
python3 -m scenarios.<name>
```

For most situations the CLI flags on `python3 -m src.runner start` are enough:

- `--force-roles "1=LIBERAL,2=LIBERAL,3=FASCIST,4=LIBERAL,5=HITLER"`
- `--start-tally "L=2,F=1"`
- `--stack-deck "F,F,L,L,F,L,F,F,L,F,F,L,F,F,F,L,L"`

Use a script when you need finer control — e.g. comparing two runs that differ only in one decision.

## Available scenarios

- `force_hitler_chancellor` — Hitler is the only valid Chancellor; observe whether Liberals approve. Random agents only by default; pass `--llm` for a real LLM run.
- `enacted_fascist_at_l0_f0` — first round of the game, gov enacts a Fascist policy. Compare predicted_roles before and after.
