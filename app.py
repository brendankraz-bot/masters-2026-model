"""
Masters 2026 Live Prediction Model — Streamlit App
5 tabs: Leaderboard | Power Rankings | Best Bets | Matchup Predictor | Hole Analysis
Auto-refreshes every 5 minutes during live rounds (April 9-12).
"""

import streamlit as st
from datetime import datetime, date

st.set_page_config(
    page_title="Masters 2026 Model",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Masters green theme styling ───────────────────────────────────────────────
st.markdown("""
<style>
  /* Tab styling */
  .stTabs [data-baseweb="tab-list"] { gap: 8px; }
  .stTabs [data-baseweb="tab"] {
    background-color: #1a2e1a;
    color: #c8d8c8;
    border-radius: 4px 4px 0 0;
    padding: 8px 18px;
    font-weight: 500;
  }
  .stTabs [aria-selected="true"] {
    background-color: #006747 !important;
    color: #ffffff !important;
  }
  /* Score colors */
  .score-under  { color: #4ade80; font-weight: 600; }
  .score-even   { color: #e2e8f0; }
  .score-over   { color: #f87171; font-weight: 600; }
  .score-eagle  { color: #22c55e; font-weight: 700; }
  /* Confidence badges */
  .tier-high   { background:#dc2626; color:#fff; padding:2px 8px; border-radius:10px; font-size:12px; }
  .tier-medium { background:#d97706; color:#fff; padding:2px 8px; border-radius:10px; font-size:12px; }
  .tier-low    { background:#4b5563; color:#fff; padding:2px 8px; border-radius:10px; font-size:12px; }
  /* Header banner */
  .masters-header {
    background: linear-gradient(90deg, #006747 0%, #004d34 100%);
    padding: 14px 24px;
    border-radius: 8px;
    margin-bottom: 16px;
  }
  .masters-header h1 { color: #fff; margin: 0; font-size: 1.8rem; }
  .masters-header p  { color: #a7d4bb; margin: 4px 0 0; font-size: 0.9rem; }
  /* Metric cards */
  [data-testid="stMetric"] {
    background: #1e2d1e;
    border: 1px solid #2d4a2d;
    border-radius: 8px;
    padding: 12px 16px;
  }
  /* Dataframe */
  .dataframe { font-size: 13px; }
</style>
""", unsafe_allow_html=True)


# ── Auto-refresh during live rounds ──────────────────────────────────────────
TOURNAMENT_DATES = [date(2026, 4, 9), date(2026, 4, 10), date(2026, 4, 11), date(2026, 4, 12)]
today = date.today()
is_live_day = today in TOURNAMENT_DATES
if is_live_day:
    st.markdown('<meta http-equiv="refresh" content="300">', unsafe_allow_html=True)


# ── Header ────────────────────────────────────────────────────────────────────
last_refresh = datetime.now().strftime("%I:%M:%S %p ET")
tournament_status = "LIVE" if is_live_day else ("PRE-TOURNAMENT" if today < date(2026, 4, 9) else "COMPLETE")
status_color = "#22c55e" if is_live_day else "#f59e0b"

st.markdown(f"""
<div class="masters-header">
  <h1>⛳ Masters 2026 — Live Prediction Model</h1>
  <p>Augusta National · Par 72 · 7,565 yards &nbsp;|&nbsp;
     <span style="color:{status_color};font-weight:600">{tournament_status}</span>
     &nbsp;|&nbsp; Last updated: {last_refresh}
     {"&nbsp;· Auto-refresh every 5 min" if is_live_day else ""}
  </p>
</div>
""", unsafe_allow_html=True)


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_leaderboard, tab_predictions, tab_bets, tab_matchup, tab_holes = st.tabs([
    "📊 Leaderboard",
    "🏆 Power Rankings",
    "💰 Best Bets",
    "⚔️ Matchup Predictor",
    "🕳️ Hole Analysis",
])

with tab_leaderboard:
    from src.ui.leaderboard_tab import render as render_leaderboard
    render_leaderboard()

with tab_predictions:
    from src.ui.predictions_tab import render as render_predictions
    render_predictions()

with tab_bets:
    from src.ui.best_bets_tab import render as render_best_bets
    render_best_bets()

with tab_matchup:
    from src.ui.matchup_tab import render as render_matchup
    render_matchup()

with tab_holes:
    from src.ui.hole_analysis_tab import render as render_hole_analysis
    render_hole_analysis()
