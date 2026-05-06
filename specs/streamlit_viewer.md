# Spec: Streamlit Game Viewer + JSON Game Log

## Goal
Let the operator visualise predicted_role evolution across rounds. After every round we already have all the data (gov, statements, post-update predicted_roles); we just need to emit it in a stable JSON format and build a small Streamlit app that loads any log file and renders bar charts + a per-pair trajectory line chart.

The CLI stays the source of truth. Streamlit is a pure post-game viewer that reads the emitted JSON. Run a game once → load the log in Streamlit any time after.

## CLI addition

`python3 -m src.runner start ... --save-log game.json` writes a JSON file to the given path at end of game. Default: no log emission (backward compatible).

## JSON log shape

```json
{
  "metadata": {
    "seed": 1,
    "rounds_requested": 4,
    "agents_mode": "llm",
    "model": "gpt-5-mini",
    "discussion": true,
    "llm_role_updates": true
  },
  "operator_view": {
    "1": "LIBERAL",
    "2": "HITLER",
    "3": "LIBERAL",
    "4": "FASCIST",
    "5": "LIBERAL"
  },
  "initial_predicted_roles": {
    "1": {"2": 0.0, "3": 0.0, "4": 0.0, "5": 0.0},
    "2": {"1": 1.0, "3": 1.0, "4": -1.0, "5": 1.0},
    "3": {"1": 0.0, "2": 0.0, "4": 0.0, "5": 0.0},
    "4": {"1": 1.0, "2": -1.0, "3": 1.0, "5": 1.0},
    "5": {"1": 0.0, "2": 0.0, "3": 0.0, "4": 0.0}
  },
  "rounds": [
    {
      "round_num": 1,
      "president_id": 1,
      "chancellor_id": 3,
      "votes": {"1": true, "2": true, "3": true, "4": false, "5": true},
      "election_passed": true,
      "policy_session": {
        "drawn": ["FASCIST", "LIBERAL", "FASCIST"],
        "discarded_by_president": "FASCIST",
        "handed_to_chancellor": ["LIBERAL", "FASCIST"],
        "enacted": "LIBERAL",
        "discarded_by_chancellor": "FASCIST"
      },
      "tally_after": {"liberal": 1, "fascist": 0},
      "statements": [
        {"player_id": 1, "text": "I drew FLF...", "reasoning": "honest"},
        {"player_id": 3, "text": "...", "reasoning": "..."}
      ],
      "decisions": {
        "1": {
          "nominate": {"choice": 3, "reasoning": "..."},
          "vote": {"value": true, "reasoning": "..."},
          "discard": {"policy": "FASCIST", "reasoning": "..."}
        },
        "3": {
          "vote": {"value": true, "reasoning": "..."},
          "enact": {"policy": "LIBERAL", "reasoning": "..."}
        }
      },
      "predicted_roles_after": {
        "1": {"2": 0.0, "3": 0.4, "4": -0.2, "5": 0.0},
        "2": {"1": 1.0, "3": 1.0, "4": -1.0, "5": 1.0},
        "3": {"1": 0.4, "2": -0.1, "4": -0.2, "5": 0.1},
        "4": {"1": 1.0, "2": -1.0, "3": 1.0, "5": 1.0},
        "5": {"1": 0.2, "2": -0.1, "3": 0.2, "4": -0.1}
      }
    }
  ],
  "winner": "liberal",
  "winning_reason": "Liberals enacted 5 Liberal policies."
}
```

The shape is stable enough that the viewer can load any log without knowing which features were enabled (e.g. `statements` is empty list when discussion was off; `policy_session` is null when election failed).

## Streamlit app

`viewer/streamlit_app.py`. Run via:
```
streamlit run viewer/streamlit_app.py -- game.json
```
(Note the `--` separating Streamlit's own args from script args.)

### Layout
- **Title bar:** "Secret Hitler LLM — Game Viewer"
- **Sidebar:** drop-down to switch between rounds, plus a "Show winner banner" toggle.
- **Top:** roster (with role labels — operator view is the whole point) and game outcome.
- **Round tabs:** one tab per played round.
  - Government summary (pres/chan, election result, enacted policy, tally).
  - Statements list.
  - **Bar chart panel:** one bar chart per player showing their predicted_roles (after this round's update) for the other 4 players. Y-axis fixed to `[-1, +1]`. Bar colour: liberal-leaning green, fascist-leaning red, neutral grey.
- **Trajectory tab:** for any (viewer, target) pair the user picks, show a line chart of the viewer's predicted_role of the target across all rounds. Useful for spotting when suspicion locks in.

### Widgets
- `st.bar_chart` for the per-player bar charts (Streamlit native — no matplotlib dep needed).
- `st.line_chart` for trajectories.
- `st.tabs(...)` for round navigation.
- `st.expander` for statements/decisions.

## Dependencies
- `streamlit>=1.30` — added to `requirements.txt` (the dep set is already aspirational; non-viewer users can skip it).
- Stdlib `json` for the log.

## Edge cases
- Empty `rounds` (no round played, e.g. immediate win? doesn't currently happen but handle gracefully).
- Failed elections: `policy_session` and `statements` are `null` / `[]`; the bar chart still renders (predicted_roles snapshot is from the heuristic update which doesn't run on failed elections — values carry over from the last round).
- Random mode: statements are `(silent)`; viewer still works, just less interesting.
- Log file missing keys (older logs from before this commit): viewer should show what it can and skip missing sections.

## Tests
- `tests/test_game_log.py` — emit a log from a tiny random-mode game, assert JSON shape, types, that all rounds appear, and that predicted_roles are present.
- The Streamlit app is not unit-tested; it's UI code. Manual smoke is enough.

## Out of scope (V2)
- Live-updating dashboard during a running game.
- Action-level granularity (snapshots after each individual LLM call, not just per round).
- Comparing two log files side-by-side in the viewer.
- Hiding the operator view from a "player perspective" mode.
