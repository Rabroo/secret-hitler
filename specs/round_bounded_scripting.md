# Round-bounded scripting

## Goal

Currently `ScriptedAgent` applies its scripted decisions on *every* round. That
is fine for one-shot setups (force a round-1 event, observe the immediate
reaction) but it prevents a scripted experiment from running multiple rounds in
which the LLM is allowed to *react and play freely after* the suspicious event.

We want experiments where round 1 is forced (so every run sees the same
mechanical event) but rounds 2+ are free LLM play, so we can study whether
suspicion *persists*, *fades*, or *compounds* across rounds.

## Inputs / Outputs

- New optional field on `ScriptedAgent`:
  - `apply_until_round: int | None = None` — if set, scripted decisions are
    used only when the current round number is `<= apply_until_round`. After
    that, every decision delegates to `fallback`. `None` (default) keeps the
    old behaviour: scripts always apply.
- New optional field on `Variant`:
  - `apply_until_round: int | None = None` — passed through to
    `build_scripted_agents`.
- `build_scripted_agents` gets a new keyword-only `apply_until_round` arg.

## Steps / Logic

- `ScriptedAgent` needs to know what round it is in.
  - When wrapped around an `LLMAgent`, the fallback already holds a reference
    to `state.history` (the runner shares the same list across all agents).
  - We expose this as `ScriptedAgent.history_ref: list = []`.
    `build_scripted_agents` sets it to `getattr(fallback, "history", [])`.
  - `current_round = len(history_ref) + 1` (history holds *completed* rounds).
- A scripted decision applies iff:
  - the relevant decision-type key is present in `scripted`, AND
  - `apply_until_round is None or current_round <= apply_until_round`.
- Otherwise, every decision delegates to `fallback`.
- Reactive calls (`make_statement`, `update_predicted_roles`) keep delegating
  unconditionally — they were never scripted to begin with.

## Edge cases

- `apply_until_round=0` → scripts never apply (even round 1). Equivalent to
  not wrapping the agent, but allowed for symmetry.
- `apply_until_round=1` → only round 1 forced. This is the common case for
  the new exp_*.py experiments.
- Fallback is a `RandomAgent` (used in tests): no `history` attribute. We
  default `history_ref` to an empty list so `current_round == 1` and the
  scripts always apply (matching the old behaviour). Tests that want to
  exercise the gate can pass an explicit `history_ref` list.
- `scripted` is empty for a player: behaviour unchanged — every call falls
  through to the fallback.

## Dependencies

- Touches `src/agents.py` (ScriptedAgent, build_scripted_agents),
  `src/experiment_runner.py` (Variant, run_experiment plumb-through), and the
  three `scenarios/exp_*.py` scripts (default `rounds=3, apply_until_round=1`).
- Tests: `tests/test_scripted_agent.py`,
  `tests/test_experiment_runner.py`.

## Cost note

Each experiment currently costs ~$1–1.50 with `--runs 10` at 1 round each.
Bumping to 3 rounds roughly triples the per-run LLM call count, so plan for
~$3–4.50 per experiment, ~$10 for all three. Keep `apply_until_round=1` so
only the first round is forced — the rest is the data we actually want.
