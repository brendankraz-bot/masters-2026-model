"""
leaderboard_tab.py — Live leaderboard with score projections

Shows:
  - Live scores from ESPN (5-min TTL cache)
  - In-round projected day score
  - Tournament total projection (blended model)
  - Field conditions banner (weather adjustments)
  - Hole 12 / par-5 flags
"""

import streamlit as st
import pandas as pd
from datetime import date


@st.cache_data(ttl=300, show_spinner=False)
def _load_leaderboard():
    from src.data_fetchers.leaderboard import get_leaderboard
    return get_leaderboard()


@st.cache_data(ttl=300, show_spinner=False)
def _load_weather():
    from src.data_fetchers.weather import get_all_rounds_weather, get_round_weather
    return get_all_rounds_weather(), get_round_weather


@st.cache_data(ttl=900, show_spinner=False)
def _load_pre_rankings():
    from src.model.scoring_model import build_rankings
    return build_rankings()


@st.cache_data(ttl=300, show_spinner=False)
def _load_live_rankings():
    from src.model.live_model import build_live_rankings
    from src.data_fetchers.leaderboard import get_leaderboard
    from src.data_fetchers.weather import get_all_rounds_weather
    from src.model.scoring_model import build_rankings
    lb = get_leaderboard()
    rankings = build_rankings()
    weather = get_all_rounds_weather()
    return build_live_rankings(lb, rankings, weather), lb


def _score_color(val, is_html=True):
    """Return colored HTML span for a vs-par value."""
    try:
        v = float(val)
    except (TypeError, ValueError):
        return str(val)
    if v < -1:
        css = "color:#22c55e;font-weight:700"
        label = f"{v:+.0f}"
    elif v < 0:
        css = "color:#4ade80;font-weight:600"
        label = f"{v:+.0f}"
    elif v == 0:
        css = "color:#e2e8f0"
        label = "E"
    elif v <= 1:
        css = "color:#f87171;font-weight:600"
        label = f"+{v:.0f}"
    else:
        css = "color:#ef4444;font-weight:700"
        label = f"+{v:.0f}"
    return f'<span style="{css}">{label}</span>' if is_html else label


def _format_proj(val):
    if val is None:
        return "—"
    try:
        v = float(val)
        return f"{v:+.1f}" if v != 0 else "E"
    except (TypeError, ValueError):
        return "—"


def render():
    st.subheader("Live Leaderboard", divider="green")

    # ── Weather banner ────────────────────────────────────────────────────────
    today = date.today()
    round_map = {date(2026, 4, 9): 1, date(2026, 4, 10): 2,
                 date(2026, 4, 11): 3, date(2026, 4, 12): 4}
    current_round = round_map.get(today, 0)

    try:
        weather_all, get_round_weather_fn = _load_weather()
        if current_round > 0:
            w = weather_all.get(current_round, {})
        else:
            w = weather_all.get(1, {})  # pre-tournament: show R1 forecast

        wind = w.get("wind_mph", 0)
        temp_lo = w.get("min_temp_f", "—")
        temp_hi = w.get("max_temp_f", "—")
        precip  = w.get("precip_inches", 0)
        scoring_adj = w.get("scoring_adjustment", 0)
        condition = w.get("condition_label", "—")
        adj_color = "#f87171" if scoring_adj > 0 else "#4ade80"

        st.markdown(f"""
        <div style="background:#1a2e1a;border:1px solid #2d4a2d;border-radius:8px;
                    padding:10px 20px;margin-bottom:14px;display:flex;gap:32px;align-items:center">
          <span>🌤 <b>{condition}</b></span>
          <span>🌬 Wind: <b>{wind:.0f} mph</b></span>
          <span>🌡 Temp: <b>{temp_lo}–{temp_hi}°F</b></span>
          <span>🌧 Precip: <b>{precip:.2f}"</b></span>
          <span>📈 Scoring adj: <b style="color:{adj_color}">{scoring_adj:+.2f}</b></span>
          {"<span style='background:#dc2626;color:#fff;padding:2px 8px;border-radius:10px;font-size:12px'>TOUGH CONDITIONS</span>" if wind > 20 else ""}
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        pass

    # ── Load data ─────────────────────────────────────────────────────────────
    with st.spinner("Loading leaderboard…"):
        try:
            live_df, lb_raw = _load_live_rankings()
        except Exception as e:
            st.error(f"Could not load live rankings: {e}")
            return

    if live_df is None or live_df.empty:
        st.info("Leaderboard not yet available. Check back when Round 1 begins on April 9.")
        return

    status = lb_raw.get("status", "pre")
    current_round_live = lb_raw.get("current_round", 0)

    # ── Round indicator ───────────────────────────────────────────────────────
    if current_round_live > 0:
        st.caption(f"Round {current_round_live} · {lb_raw.get('player_count', '—')} players")
    else:
        st.caption("Pre-tournament — projections based on model only")

    # ── Main leaderboard table ────────────────────────────────────────────────
    display_cols = []
    rows = []
    for _, row in live_df.iterrows():
        pos = row.get("position", "—")
        name = row.get("player_name", "—")
        today_disp = row.get("today_display", "—")
        thru = row.get("thru", "—")
        total_disp = row.get("total_display", "—")
        today_proj = _format_proj(row.get("today_proj_vs_par"))
        tourn_proj = _format_proj(row.get("tournament_proj_vs_par"))
        blend_w_actual = row.get("w_actual", 0)
        pre_rank = int(row.get("model_rank_pre", 0)) if row.get("model_rank_pre") else "—"

        rows.append({
            "Pos": pos,
            "Player": name,
            "Today": today_disp,
            "Thru": thru,
            "Total": total_disp,
            "Proj Day": today_proj,
            "Proj Total": tourn_proj,
            "Model Wt": f"{blend_w_actual:.0%}",
            "Pre Rank": pre_rank,
        })

    df_display = pd.DataFrame(rows)

    # Style: color the Proj Total column
    def _style_proj(val):
        try:
            v = float(str(val).replace("E", "0").replace("+", ""))
            if v < -8:
                return "color: #22c55e; font-weight: 700"
            elif v < 0:
                return "color: #4ade80; font-weight: 600"
            elif v == 0:
                return "color: #e2e8f0"
            elif v <= 3:
                return "color: #f87171"
            else:
                return "color: #ef4444; font-weight: 700"
        except Exception:
            return ""

    styled = df_display.style.applymap(_style_proj, subset=["Proj Total", "Proj Day"])
    st.dataframe(styled, use_container_width=True, hide_index=True, height=600)

    # ── Model blend note ──────────────────────────────────────────────────────
    if current_round_live > 0:
        completed = current_round_live - 1
        blend_schedule = {0: (1.0, 0.0), 1: (0.67, 0.33), 2: (0.47, 0.53), 3: (0.22, 0.78)}
        w_pre, w_act = blend_schedule.get(completed, (0.1, 0.9))
        st.caption(
            f"Model blend — Pre-tournament: {w_pre:.0%} · Actual SG: {w_act:.0%}  |  "
            f"'Proj Day' = in-round regression projection  |  'Proj Total' = model tournament total"
        )
    else:
        st.caption("Projections are 100% pre-tournament model until Round 1 begins.")

    # ── Refresh button ────────────────────────────────────────────────────────
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()
