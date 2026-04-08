"""
matchup_tab.py — 2-3 player head-to-head matchup predictor

UI:
  - Multi-select 2–3 players from the field
  - Round selector (1–4)
  - Run Monte Carlo (1000 simulations)
  - Results: win %, projected score, SG breakdown, confidence, weather context
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go


@st.cache_data(ttl=3600, show_spinner=False)
def _get_field_names():
    """Load player names from the field CSV for the multiselect dropdown."""
    from pathlib import Path
    import pandas as pd
    path = Path(__file__).parent.parent.parent / "data" / "field_2026.csv"
    if path.exists():
        df = pd.read_csv(path)
        col = next((c for c in df.columns if "name" in c.lower()), df.columns[0])
        return sorted(df[col].dropna().tolist())
    # Fallback: hardcoded top players
    return [
        "Scottie Scheffler", "Ludvig Aberg", "Collin Morikawa", "Rory McIlroy",
        "Xander Schauffele", "Jon Rahm", "Hideki Matsuyama", "Brooks Koepka",
        "Viktor Hovland", "Cameron Smith", "Jordan Spieth", "Dustin Johnson",
        "Justin Thomas", "Tommy Fleetwood", "Tony Finau",
    ]


def _win_pct_chart(results: dict) -> go.Figure:
    """Donut-style win probability chart."""
    players = list(results.keys())
    pcts    = [results[p]["win_pct"] for p in players]
    colors  = ["#006747", "#22c55e", "#86efac"][:len(players)]

    fig = go.Figure(go.Pie(
        labels=players,
        values=pcts,
        hole=0.55,
        marker=dict(colors=colors, line=dict(color="#0e1a0e", width=2)),
        textinfo="label+percent",
        textfont_size=13,
    ))
    fig.update_layout(
        showlegend=False,
        paper_bgcolor="#0e1a0e",
        font={"color": "#c8d8c8"},
        margin=dict(l=20, r=20, t=20, b=20),
        height=260,
    )
    return fig


def _sg_breakdown_chart(results: dict) -> go.Figure:
    """Grouped bar chart of SG breakdown per player."""
    players   = list(results.keys())
    categories = ["sg_app", "sg_arg", "sg_ott", "sg_putt"]
    labels     = ["Approach", "Around-Green", "Off Tee", "Putting"]
    colors     = ["#006747", "#22c55e", "#86efac", "#bbf7d0"]

    fig = go.Figure()
    for i, (cat, label, color) in enumerate(zip(categories, labels, colors)):
        fig.add_trace(go.Bar(
            name=label,
            x=players,
            y=[results[p].get(cat, 0) for p in players],
            marker_color=color,
        ))

    fig.update_layout(
        barmode="group",
        title="SG Category Breakdown",
        paper_bgcolor="#0e1a0e",
        plot_bgcolor="#0e1a0e",
        font={"color": "#c8d8c8"},
        yaxis_title="SG / Round",
        height=280,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def render():
    st.subheader("Matchup Predictor", divider="green")
    st.caption("Select 2–3 players to run a 1,000-iteration Monte Carlo simulation for a specific round.")

    field_names = _get_field_names()

    # ── Player selection ───────────────────────────────────────────────────────
    col_players, col_round = st.columns([3, 1])

    with col_players:
        default_players = ["Scottie Scheffler", "Ludvig Aberg", "Rory McIlroy"]
        defaults = [p for p in default_players if p in field_names]
        selected_players = st.multiselect(
            "Select 2–3 players",
            options=field_names,
            default=defaults[:2],
            max_selections=3,
            placeholder="Choose players…",
        )

    with col_round:
        round_num = st.selectbox(
            "Round",
            options=[1, 2, 3, 4],
            index=0,
            format_func=lambda r: f"Round {r} · {['Apr 9','Apr 10','Apr 11','Apr 12'][r-1]}",
        )

    if len(selected_players) < 2:
        st.info("Select at least 2 players to run a matchup.")
        return

    # ── Run simulation ─────────────────────────────────────────────────────────
    run_col, _ = st.columns([1, 3])
    with run_col:
        run_btn = st.button("⚔️ Run Matchup", type="primary", use_container_width=True)

    if not run_btn and "matchup_result" not in st.session_state:
        st.info("Press **Run Matchup** to simulate.")
        return

    if run_btn:
        with st.spinner(f"Running 1,000 Monte Carlo simulations…"):
            try:
                from src.model.matchup import run_matchup
                result = run_matchup(
                    player_names=selected_players,
                    round_number=round_num,
                )
                st.session_state["matchup_result"] = result
                st.session_state["matchup_players"] = selected_players
                st.session_state["matchup_round"] = round_num
            except Exception as e:
                st.error(f"Simulation failed: {e}")
                return

    result = st.session_state.get("matchup_result")
    if not result:
        return

    players_res = result["players"]
    winner      = result["winner"]
    confidence  = result["confidence"]
    weather     = result["weather"]
    ties        = result["ties"]

    # ── Weather context ────────────────────────────────────────────────────────
    wind = weather.get("wind_mph", 0)
    condition = weather.get("condition_label", "—")
    scoring_adj = weather.get("scoring_adjustment", 0)
    adj_color = "#f87171" if scoring_adj > 0 else "#4ade80"

    st.markdown(f"""
    <div style="background:#1a2e1a;border:1px solid #2d4a2d;border-radius:8px;
                padding:8px 16px;margin:8px 0;font-size:13px">
      Round {round_num} conditions: <b>{condition}</b> · Wind <b>{wind:.0f} mph</b> ·
      Scoring adj: <b style="color:{adj_color}">{scoring_adj:+.2f}</b> strokes/round
    </div>
    """, unsafe_allow_html=True)

    # ── Results ────────────────────────────────────────────────────────────────
    st.divider()

    # Sort by win %
    sorted_players = sorted(players_res.items(), key=lambda x: x[1]["win_pct"], reverse=True)

    # Charts
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.plotly_chart(_win_pct_chart(players_res), use_container_width=True)
    with col_chart2:
        st.plotly_chart(_sg_breakdown_chart(players_res), use_container_width=True)

    # Player result cards
    st.divider()
    cols = st.columns(len(sorted_players))
    for col, (name, data) in zip(cols, sorted_players):
        is_winner = name == winner
        border_color = "#006747" if is_winner else "#2d4a2d"
        bg_color = "#1a2e1a" if is_winner else "#0f1f0f"
        pick_badge = "← PICK" if is_winner else ""
        proj = data.get("proj_score_display", "—")
        rng  = data.get("proj_score_range", (None, None))
        rng_str = f"({rng[0]:+.1f} to {rng[1]:+.1f})" if rng[0] is not None else ""

        with col:
            st.markdown(f"""
            <div style="background:{bg_color};border:2px solid {border_color};border-radius:10px;
                        padding:16px;text-align:center">
              <div style="font-size:1.0rem;font-weight:700;color:#fff">{name}</div>
              <div style="font-size:2.2rem;font-weight:800;color:#22c55e;margin:8px 0">
                {data['win_pct']:.1f}%
              </div>
              <div style="color:#94a3b8;font-size:0.85rem">win probability</div>
              <div style="margin-top:10px;font-size:1.1rem;color:#c8d8c8">
                Proj: <b>{proj}</b>
              </div>
              <div style="color:#6b7280;font-size:0.78rem">{rng_str}</div>
              <div style="margin-top:8px;font-size:0.78rem;color:#6b7280">
                App {data.get('sg_app',0):+.2f} |
                ARG {data.get('sg_arg',0):+.2f} |
                OTT {data.get('sg_ott',0):+.2f} |
                Putt {data.get('sg_putt',0):+.2f}
              </div>
              {"<div style='margin-top:10px;background:#006747;color:#fff;padding:3px 10px;border-radius:10px;font-size:12px;font-weight:700'>PICK</div>" if is_winner else ""}
            </div>
            """, unsafe_allow_html=True)

    # Confidence + ties
    conf_colors = {"High": "#22c55e", "Medium": "#f59e0b", "Low": "#94a3b8"}
    st.markdown(f"""
    <div style="text-align:center;margin-top:12px;color:#94a3b8;font-size:13px">
      Confidence: <span style="color:{conf_colors.get(confidence,'#94a3b8')};font-weight:700">
        {confidence}</span> &nbsp;|&nbsp;
      Ties: {ties}/{result['iterations']} simulations
    </div>
    """, unsafe_allow_html=True)

    st.caption("Simulation uses player SG composites + per-hole Augusta distributions + weather adjustments.")
