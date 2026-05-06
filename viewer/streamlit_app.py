"""Streamlit viewer for Secret Hitler LLM game logs.

Run with:

    streamlit run viewer/streamlit_app.py -- path/to/game.json

The `--` separates Streamlit's own args from this script's args.

The viewer reads the JSON game log emitted by `python3 -m src.runner start
--save-log path/to/game.json` and shows:

  - Roster (operator view) + game outcome.
  - Per-round tabs with the gov summary, statements, decisions, and a bar
    chart per player of their predicted_roles after that round.
  - Trajectory tab: pick any (viewer, target) pair, see how the prediction
    evolved across rounds.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import streamlit as st


# --- log loading ------------------------------------------------------------


def _parse_args() -> Path:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", help="Path to a game JSON log emitted by --save-log")
    args, _unknown = parser.parse_known_args()
    return Path(args.log)


@st.cache_data
def load_log(path: str) -> dict:
    return json.loads(Path(path).read_text())


# --- formatting helpers -----------------------------------------------------


_ROLE_EMOJI = {"LIBERAL": "🟦", "FASCIST": "🟥", "HITLER": "💀"}


def _role_label(role: str) -> str:
    return f"{_ROLE_EMOJI.get(role, '')} {role}"


def _format_votes(votes: dict[str, bool]) -> str:
    return ", ".join(
        f"P{pid}={'ja' if v else 'nein'}" for pid, v in sorted(votes.items())
    )


# --- panels -----------------------------------------------------------------


def _panel_overview(log: dict) -> None:
    st.subheader("Roster")
    cols = st.columns(5)
    for col, (pid, role) in zip(cols, sorted(log["operator_view"].items())):
        col.metric(f"Player {pid}", _role_label(role))

    md = log["metadata"]
    st.caption(
        f"Mode: **{md['agents_mode']}** · "
        f"Discussion: {md.get('discussion', True)} · "
        f"LLM updates: {md.get('llm_role_updates', True)} · "
        f"Seed: {md['seed']} · "
        f"Rounds requested: {md['rounds_requested']}"
    )

    if log.get("winner"):
        winner = log["winner"]
        emoji = "🟦" if winner == "liberal" else "🟥"
        st.success(f"{emoji} **{winner.upper()} VICTORY** — {log.get('winning_reason', '')}")
    else:
        st.info("No winner declared (game ended on round limit).")


def _bar_chart_predicted_roles(viewer_id: str, predicted: dict[str, float]) -> None:
    """One bar chart for one viewer: their predicted_roles for each other player."""
    import pandas as pd

    df = pd.DataFrame(
        {
            "player": [f"P{pid}" for pid in sorted(predicted.keys())],
            "predicted_role": [predicted[pid] for pid in sorted(predicted.keys())],
        }
    ).set_index("player")
    st.bar_chart(df, height=180)


def _panel_round(log: dict, round_data: dict) -> None:
    rn = round_data["round_num"]
    pres = round_data["president_id"]
    chan = round_data["chancellor_id"]
    passed = round_data["election_passed"]
    op = log["operator_view"]

    st.markdown(
        f"### Round {rn} — President **P{pres}** ({_role_label(op[str(pres)])}) "
        f"+ Chancellor **P{chan}** ({_role_label(op[str(chan)])})"
    )

    outcome = "✅ ELECTED" if passed else "❌ REJECTED"
    st.markdown(
        f"**Election:** {outcome}  ·  Votes: `{_format_votes(round_data['votes'])}`"
    )

    if round_data.get("policy_session"):
        ps = round_data["policy_session"]
        st.markdown(
            f"**Policy session (operator view)** — Drawn: "
            f"`{', '.join(ps['drawn'])}` · "
            f"Pres discarded: `{ps['discarded_by_president']}` · "
            f"Chan hand: `{', '.join(ps['handed_to_chancellor'])}` · "
            f"Enacted: **{ps['enacted']}** · "
            f"Chan discarded: `{ps['discarded_by_chancellor']}`"
        )
        tally = round_data["tally_after"]
        st.markdown(f"**Tally after:** L={tally['liberal']}  ·  F={tally['fascist']}")

    if round_data.get("statements"):
        with st.expander(f"💬 Discussion ({len(round_data['statements'])} statements)"):
            for s in round_data["statements"]:
                pid = s["player_id"]
                role = op[str(pid)]
                st.markdown(f"**P{pid}** ({_role_label(role)}): {s['text']}")
                if s.get("reasoning"):
                    st.caption(f"private reasoning: _{s['reasoning']}_")

    with st.expander("📊 Predicted roles (after this round) — bar chart per viewer"):
        cols = st.columns(5)
        for col, (vid, pred) in zip(cols, sorted(round_data["predicted_roles_after"].items())):
            with col:
                st.markdown(f"**P{vid}** ({op[vid]})")
                _bar_chart_predicted_roles(vid, pred)


def _panel_trajectory(log: dict) -> None:
    """Line chart of one viewer's predicted_role of one target across rounds."""
    import pandas as pd

    op = log["operator_view"]
    pids = sorted(op.keys(), key=int)

    col1, col2 = st.columns(2)
    viewer = col1.selectbox("Viewer", pids, index=0, format_func=lambda x: f"P{x} ({op[x]})")
    target_choices = [pid for pid in pids if pid != viewer]
    target = col2.selectbox(
        "Target", target_choices, index=0, format_func=lambda x: f"P{x} ({op[x]})"
    )

    rows = []
    initial = log.get("initial_predicted_roles", {}).get(viewer, {})
    if target in initial:
        rows.append({"round": 0, "predicted_role": initial[target]})
    for r in log["rounds"]:
        snap = r["predicted_roles_after"].get(viewer, {})
        if target in snap:
            rows.append({"round": r["round_num"], "predicted_role": snap[target]})

    if not rows:
        st.info("No data for this pair.")
        return

    df = pd.DataFrame(rows).set_index("round")
    st.line_chart(df, height=300)
    st.caption(
        f"P{viewer}'s prediction of P{target}'s role over time. "
        "+1 = predicted Liberal · -1 = predicted Fascist team."
    )


# --- main -------------------------------------------------------------------


def main() -> None:
    log_path = _parse_args()
    log = load_log(str(log_path))

    st.set_page_config(
        page_title="Secret Hitler LLM — Game Viewer",
        layout="wide",
    )
    st.title("🟦🟥 Secret Hitler LLM — Game Viewer")
    st.caption(f"Log: `{log_path}`")

    _panel_overview(log)
    st.divider()

    rounds = log["rounds"]
    if not rounds:
        st.warning("No rounds in this log.")
        return

    tab_labels = [f"Round {r['round_num']}" for r in rounds] + ["📈 Trajectory"]
    tabs = st.tabs(tab_labels)
    for tab, r in zip(tabs[:-1], rounds):
        with tab:
            _panel_round(log, r)
    with tabs[-1]:
        _panel_trajectory(log)


if __name__ == "__main__" or True:
    # Streamlit re-imports the module each rerun without __main__, so always
    # call main() at module scope.
    main()
