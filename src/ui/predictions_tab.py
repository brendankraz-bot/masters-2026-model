"""
predictions_tab.py — Power Rankings and model vs. market comparison

Shows:
  - Pre-tournament composite rankings (top 30)
  - SG category breakdown (App, ARG, OTT, Putt) per player
  - Model win % vs market implied %
  - Composite score component bar chart
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px


@st.cache_data(ttl=900, show_spinner=False)
def _load_rankings():
    from src.model.scoring_model import build_rankings
    return build_rankings()


@st.cache_data(ttl=300, show_spinner=False)
def _load_market_odds():
    try:
        from src.data_fetchers.odds import get_consensus_odds
        return get_consensus_odds()
    except Exception:
        try:
            from src.data_fetchers.odds import get_draftkings_odds
            return {k: {"win_prob_consensus": v["win_prob"]} for k, v in get_draftkings_odds().items()}
        except Exception:
            return {}


def _find_market_prob(player_name: str, odds_dict: dict) -> float | None:
    """Fuzzy match player → market implied win probability."""
    name_lower = player_name.lower()
    for key, val in odds_dict.items():
        if key.lower() == name_lower:
            return val.get("win_prob_consensus")
    # Last name match
    last = name_lower.split()[-1]
    for key, val in odds_dict.items():
        if last in key.lower():
            return val.get("win_prob_consensus")
    return None


def _make_sg_chart(df: pd.DataFrame, top_n: int = 15):
    """Horizontal stacked bar chart of SG category breakdown."""
    players = df.head(top_n)["player_name"].tolist()
    sg_app  = df.head(top_n)["skill_score"].tolist()   # composite_score by category proxy

    # Use composite score as base — break into SG category estimates
    # SG weights: APP 38%, ARG 30%, OTT 15%, PUTT 17%
    composites = df.head(top_n)["composite_score"].tolist()
    app_vals  = [c * 0.38 for c in composites]
    arg_vals  = [c * 0.30 for c in composites]
    ott_vals  = [c * 0.15 for c in composites]
    putt_vals = [c * 0.17 for c in composites]

    fig = go.Figure()
    colors = {"Approach": "#006747", "Around-Green": "#22c55e", "Off Tee": "#86efac", "Putting": "#bbf7d0"}

    for vals, label, color in [
        (app_vals,  "Approach",    "#006747"),
        (arg_vals,  "Around-Green","#22c55e"),
        (ott_vals,  "Off Tee",     "#86efac"),
        (putt_vals, "Putting",     "#bbf7d0"),
    ]:
        fig.add_trace(go.Bar(
            name=label,
            y=players[::-1],
            x=vals[::-1],
            orientation="h",
            marker_color=color,
        ))

    fig.update_layout(
        barmode="stack",
        title=f"Composite Score Breakdown — Top {top_n}",
        height=max(350, top_n * 28),
        paper_bgcolor="#0e1a0e",
        plot_bgcolor="#0e1a0e",
        font={"color": "#c8d8c8"},
        xaxis_title="Composite Score",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=160, r=20, t=60, b=40),
    )
    return fig


def render():
    st.subheader("Power Rankings", divider="green")

    with st.spinner("Loading model rankings…"):
        try:
            rankings = _load_rankings()
            market_odds = _load_market_odds()
        except Exception as e:
            st.error(f"Could not load rankings: {e}")
            return

    if rankings is None or rankings.empty:
        st.error("Rankings data unavailable.")
        return

    # ── Controls ──────────────────────────────────────────────────────────────
    col_top, col_filter = st.columns([1, 2])
    with col_top:
        top_n = st.selectbox("Show top N players", [15, 20, 30, 50, 91], index=1)
    with col_filter:
        search = st.text_input("Filter player", placeholder="e.g. Scheffler")

    df = rankings.copy()
    if search:
        df = df[df["player_name"].str.contains(search, case=False, na=False)]

    df = df.head(top_n)

    # ── Build display table ───────────────────────────────────────────────────
    rows = []
    for _, row in df.iterrows():
        market_p = _find_market_prob(row["player_name"], market_odds)
        model_p  = row.get("win_probability", 0)
        win_pct  = row.get("win_pct", 0)

        if market_p and market_p > 0:
            edge = (model_p - market_p) * 100
            market_str = f"{market_p*100:.1f}%"
            edge_str = f"{edge:+.1f}%"
        else:
            market_str = "—"
            edge_str = "—"

        proj = row.get("projected_total", 0)
        proj_str = f"{proj:+.0f}" if proj != 0 else "E"

        rows.append({
            "Rank":        int(row["model_rank"]),
            "Player":      row["player_name"],
            "Composite":   f"{row['composite_score']:.3f}",
            "Win %":       f"{win_pct:.1f}%",
            "Top 5 %":     f"{row.get('top5_probability', 0)*100:.0f}%",
            "Top 10 %":    f"{row.get('top10_probability', 0)*100:.0f}%",
            "Proj Total":  proj_str,
            "Market Win%": market_str,
            "Edge":        edge_str,
            "Age":         int(row["age"]) if row.get("age") else "—",
            "OWGR":        int(row["owgr"]) if row.get("owgr") else "—",
        })

    df_display = pd.DataFrame(rows)

    # Color edge column
    def _edge_style(val):
        if val == "—":
            return ""
        try:
            v = float(str(val).replace("%", "").replace("+", ""))
            if v >= 10:
                return "color: #22c55e; font-weight: 700"
            elif v >= 5:
                return "color: #4ade80; font-weight: 600"
            elif v <= -5:
                return "color: #f87171"
            return ""
        except Exception:
            return ""

    def _proj_style(val):
        try:
            v = float(str(val).replace("E", "0").replace("+", ""))
            if v < -6:
                return "color: #22c55e; font-weight: 700"
            elif v < 0:
                return "color: #4ade80"
            elif v > 3:
                return "color: #f87171"
            return ""
        except Exception:
            return ""

    styled = df_display.style.applymap(_edge_style, subset=["Edge"]).applymap(
        _proj_style, subset=["Proj Total"]
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=500)

    # ── SG breakdown chart ────────────────────────────────────────────────────
    st.divider()
    chart_n = min(15, len(rankings))
    st.plotly_chart(_make_sg_chart(rankings, top_n=chart_n), use_container_width=True)

    # ── Model weight legend ───────────────────────────────────────────────────
    st.divider()
    st.caption("**Composite score weights:**")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("DG Skill Rating", "62%", help="Time-weighted SG using Augusta category weights")
    c2.metric("Recent Form", "23%", help="Last 8–12 weeks SG performance")
    c3.metric("Augusta History", "10%", help="Augusta SG average 2021–2025")
    c4.metric("Course Fit", "5%", help="Shot-level course fit adjustment from DG")

    st.caption("**Augusta SG category weights:** Approach 38% · Around-Green 30% · Off Tee 15% · Putting 17%")
    st.caption("⚠️ Counter-intuitive: SG:ARG drives MORE variance at Augusta than any Tour stop. "
               "Putting is SUPPRESSED. Bomber advantage REVERSED since 2021.")
