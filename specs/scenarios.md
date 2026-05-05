# Spec: Scenario Testing (CLI Flags + Scripts)

## Goal
Let an operator pin a specific game situation and observe how agents respond. Three pieces:

1. **CLI flags** that override the default randomness in `python3 -m src.runner start`.
2. A **`scenarios/` directory** with runnable Python scripts for situations that need finer control than the CLI exposes (e.g. forcing specific decisions, comparing two runs side-by-side).
3. The existing `--dashboard` flag stays the way to *observe* results.

## CLI flags

All flags compose with each other and with the existing flags (`--rounds`, `--agents`, `--dashboard`, `--token-budget`, `--seed`).

### `--force-roles`
Pin the role assignment.
- Format: `--force-roles "1=LIBERAL,2=LIBERAL,3=FASCIST,4=LIBERAL,5=HITLER"`
- All 5 player IDs must be present; total must be 3 Liberal + 1 Fascist + 1 Hitler.
- Ignores `--seed` for role assignment (deck shuffling still uses the seed unless `--stack-deck` is also set).
- Errors out cleanly on malformed input.

### `--start-tally`
Pin the starting policy tally. Useful for "what does the game look like at L=2 F=3?".
- Format: `--start-tally "L=2,F=3"`
- Both keys required. Must be non-negative integers within rulebook bounds (L ≤ 5, F ≤ 6).

### `--stack-deck`
Pre-arrange the draw pile. Top of deck is the leftmost item.
- Format: `--stack-deck "F,F,L,L,F,L,F,F,L,F,F,L,F,F,F,L,L"` (case-insensitive; `F`=Fascist, `L`=Liberal).
- Total cards must equal 17 (full deck) so reshuffles still work intuitively.
- Ignores `--seed` for the initial shuffle.

## scenarios/ directory layout

```
scenarios/
├── __init__.py
├── README.md                    # one-line per scenario explaining what it shows
├── force_hitler_chancellor.py   # example: pin a 5p game where Hitler is nominated, watch behaviour
├── enacted_fascist_at_l0_f0.py  # example: gov enacts F as the very first policy
└── effect_on_predicted_roles.py # example: same setup, two runs differing only in chancellor's enaction
```

Each script:
- Builds a `GameState` directly via the engine API (no CLI roundtrip).
- Uses `assign_roles(forced_roles=...)` and `PolicyDeck(draw_pile=...)`.
- Wires up `RandomAgent`s or `LLMAgent`s as needed.
- Calls `start_game` (or its building blocks) and prints a labelled report.

The scripts are *runnable* (`python3 scenarios/<name>.py`), not pytest fixtures — they're for exploration, not regression.

## Engine API hooks needed

To make the above work without monkey-patching:

- `assign_roles(num_players=5, seed=None, forced_roles=None)` — `forced_roles: list[Role]` skips RNG.
- `PolicyDeck(seed=None, *, draw_pile=None)` — `draw_pile` overrides the shuffled default.
- `start_game(..., forced_roles=None, start_tally=None, stack_deck=None)` — pass-through; runner wires the parsed CLI args into these.

These additions are optional parameters; default behaviour is unchanged.

## Out of scope
- Forcing specific LLM decisions (e.g. "make the chancellor enact Liberal regardless of what the LLM says"). Right approach is a `ScriptedAgent` that returns pre-set decisions; we'll add it when the first scenario actually needs it.
- A dedicated comparison/diff renderer for two runs. Roll your own with shell pipes for now (`diff <(scenario_a) <(scenario_b)`).
- A YAML/JSON scenario format. Python scripts are flexible enough at this stage.

## Dependencies
Stdlib only.
