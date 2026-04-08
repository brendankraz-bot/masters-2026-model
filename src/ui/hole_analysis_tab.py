"""
hole_analysis_tab.py — Per-hole historical scoring analysis at Augusta National

Shows:
  - 18-hole field scoring averages (2021–2025 data)
  - Danger level ratings with color coding
  - Amen Corner (holes 11–13) special callout
  - Par 5 scoring opportunities (holes 2, 8, 13, 15)
  - Hole 12 disqualifier note
  - Interactive bar chart: field avg vs par
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd


@st.cache_data(ttl=86400, show_spinner=False)
def _load_hole_data():
    from src.data_fetchers.hole_stats import (
        HOLE_PARS, HOLE_YARDS, HOLE_NAMES, HOLE_FLAGS, FIELD_HOLE_AVERAGES, PAR5_HOLES
    )
    return HOLE_PARS, HOLE_YARDS, HOLE_NAMES, HOLE_FLAGS, FIELD_HOLE_AVERAGES, PAR5_HOLES


def _danger_badge(level: str) -> str:
    mapping = {
        "very_high": ("🔴 Very High", "#dc2626"),
        "high":      ("🟠 High",      "#ea580c"),
        "medium":    ("🟡 Medium",    "#ca8a04"),
        "low":       ("🟢 Low",       "#16a34a"),
    }
    label, color = mapping.get(level, ("—", "#6b7280"))
    return f'<span style="color:{color};font-weight:600">{label}</span>'


def _vs_par_bar_chart(hole_data: list[dict]) -> go.Figure:
    """Bar chart showing field avg vs par for all 18 holes."""
    holes = [d["hole"] for d in hole_data]
    vs_par = [d["vs_par"] for d in hole_data]
    labels = [d["name_short"] for d in hole_data]
    pars   = [d["par"] for d in hole_data]

    colors = []
    for vp, hole in zip(vs_par, holes):
        if hole in [11, 12]:
            colors.append("#ef4444")    # Amen Corner danger
        elif hole in [2, 8, 13, 15]:
            colors.append("#22c55e")    # Par 5 birdie opp
        elif vp > 0.30:
            colors.append("#f87171")    # tough
        elif vp < 0:
            colors.append("#4ade80")    # scoring opp
        else:
            colors.append("#64748b")    # neutral

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[f"H{h}" for h in holes],
        y=vs_par,
        marker_color=colors,
        text=[f"{vp:+.2f}" for vp in vs_par],
        textposition="outside",
        hovertemplate=(
            "<b>Hole %{customdata[0]}: %{customdata[1]}</b><br>"
            "Par %{customdata[2]} · %{customdata[3]} yds<br>"
            "Field avg vs par: %{y:+.2f}<extra></extra>"
        ),
        customdata=[(d["hole"], d["name_short"], d["par"], d["yards"]) for d in hole_data],
    ))

    # Reference line at 0
    fig.add_hline(y=0, line_dash="dash", line_color="#4b5563", line_width=1)

    # Amen Corner shading (holes 11-13)
    fig.add_vrect(x0="H10", x1="H12", fillcolor="#ef4444", opacity=0.07,
                  annotation_text="Amen Corner", annotation_position="top left",
                  annotation=dict(font_color="#ef4444", font_size=11))

    fig.update_layout(
        title="Field Scoring Average vs Par — Augusta National (2021–2025)",
        yaxis_title="Strokes vs Par",
        paper_bgcolor="#0e1a0e",
        plot_bgcolor="#0e1a0e",
        font={"color": "#c8d8c8"},
        xaxis=dict(tickfont=dict(size=11)),
        height=360,
        margin=dict(l=40, r=20, t=60, b=40),
        yaxis=dict(zeroline=False),
    )
    return fig


def render():
    st.subheader("Hole-by-Hole Analysis", divider="green")

    try:
        HOLE_PARS, HOLE_YARDS, HOLE_NAMES, HOLE_FLAGS, FIELD_HOLE_AVERAGES, PAR5_HOLES = _load_hole_data()
    except Exception as e:
        st.error(f"Could not load hole data: {e}")
        return

    # Build data list
    hole_data = []
    for i in range(18):
        hole_num = i + 1
        flags = HOLE_FLAGS.get(hole_num, {})
        avgs  = FIELD_HOLE_AVERAGES.get(hole_num, {})
        name  = HOLE_NAMES[i]
        # Shorten name for chart label
        name_short = name.split()[0] if name else f"H{hole_num}"

        hole_data.append({
            "hole":          hole_num,
            "name":          name,
            "name_short":    name_short,
            "par":           HOLE_PARS[i],
            "yards":         HOLE_YARDS[i],
            "danger":        flags.get("danger", "low"),
            "amen_corner":   flags.get("amen_corner", False),
            "par5_opp":      flags.get("par5_birdie_opp", False),
            "field_avg":     avgs.get("field_avg", HOLE_PARS[i]),
            "vs_par":        avgs.get("vs_par", 0),
            "birdie_pct":    avgs.get("birdie_pct", 0),
            "bogey_pct":     avgs.get("bogey_pct", 0),
            "double_pct":    avgs.get("double_pct", 0),
        })

    # ── Chart ─────────────────────────────────────────────────────────────────
    st.plotly_chart(_vs_par_bar_chart(hole_data), use_container_width=True)

    # Color legend
    st.markdown("""
    <div style="display:flex;gap:20px;font-size:12px;margin-bottom:12px">
      <span><span style="color:#22c55e">■</span> Par 5 birdie opportunity</span>
      <span><span style="color:#ef4444">■</span> Amen Corner (11-13)</span>
      <span><span style="color:#f87171">■</span> Tough hole</span>
      <span><span style="color:#64748b">■</span> Neutral</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Amen Corner callout ────────────────────────────────────────────────────
    st.divider()
    col_amen, col_par5 = st.columns(2)

    with col_amen:
        st.markdown("### 🔴 Amen Corner (Holes 11–13)")
        st.markdown("""
        The tournament's most consequential stretch:
        - **Hole 11** (White Dogwood): Par 4, 505 yds · Field +0.45/round · High bogey danger
        - **Hole 12** (Golden Bell): Par 3, 155 yds · **DISQUALIFIER** — no winner in 12 years made double-bogey here · Field +0.40/round
        - **Hole 13** (Azalea): Par 5, 510 yds · Field -0.20/round · Major birdie opportunity in the corner
        """)
        st.error("**Hole 12 rule:** Any double-bogey or worse at 12 applies -15% confidence multiplier to our round projection.", icon="⚠️")

    with col_par5:
        st.markdown("### 🟢 Par 5 Scoring Engine (2, 8, 13, 15)")
        st.markdown("""
        **9 of the last 10 Masters winners were under par on par 5s for the week.**

        - **Hole 2** (Pink Dogwood): 575 yds · Field -0.10/round
        - **Hole 8** (Yellow Jasmine): 570 yds · Field -0.05/round
        - **Hole 13** (Azalea): 510 yds · Field -0.20/round *(reachable in 2)*
        - **Hole 15** (Firethorn): 550 yds · Field -0.15/round *(famous pond approach)*
        """)
        st.success("Par-5 miss penalty: +0.5 strokes to projection per missed birdie opportunity.", icon="📊")

    # ── Full hole table ────────────────────────────────────────────────────────
    st.divider()
    st.subheader("All 18 Holes — Detailed Statistics")

    rows = []
    for d in hole_data:
        tags = []
        if d["amen_corner"]:
            tags.append("Amen Corner")
        if d["par5_opp"]:
            tags.append("Par 5 opp")
        if d["hole"] == 12:
            tags.append("⚠️ Disqualifier")

        rows.append({
            "Hole": d["hole"],
            "Name": d["name"],
            "Par": d["par"],
            "Yards": d["yards"],
            "Field Avg": f"{d['field_avg']:.2f}",
            "vs Par": f"{d['vs_par']:+.2f}",
            "Birdie %": f"{d['birdie_pct']}%",
            "Bogey %": f"{d['bogey_pct']}%",
            "Dbl+ %": f"{d['double_pct']}%",
            "Danger": d["danger"].replace("_", " ").title(),
            "Tags": " · ".join(tags) if tags else "—",
        })

    df = pd.DataFrame(rows)

    def _danger_color(val):
        mapping = {
            "Very High": "color:#ef4444;font-weight:700",
            "High":      "color:#f97316;font-weight:600",
            "Medium":    "color:#eab308",
            "Low":       "color:#4ade80",
        }
        return mapping.get(val, "")

    def _vs_par_color(val):
        try:
            v = float(str(val).replace("+", ""))
            if v < -0.05:
                return "color:#4ade80;font-weight:600"
            elif v > 0.30:
                return "color:#f87171;font-weight:600"
            return ""
        except Exception:
            return ""

    styled = (
        df.style
        .applymap(_danger_color, subset=["Danger"])
        .applymap(_vs_par_color, subset=["vs Par"])
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Key insights ──────────────────────────────────────────────────────────
    st.divider()
    st.caption("**Data source:** Data Golf shot-level data 2021–2025 · Augusta National does not participate in ShotLink")
    st.caption(
        "**Model implications:** "
        "SG:ARG weighted 30% (highest Augusta differentiator) · "
        "SG:Putting weighted 17% (suppressed at Augusta) · "
        "No distance bonus on OTT (bomber advantage reversed 2021–2025)"
    )
