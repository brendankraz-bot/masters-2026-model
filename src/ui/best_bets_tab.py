"""
best_bets_tab.py — Best Bets engine UI

Shows:
  - Bankroll tracker with adjustable starting bankroll
  - Ranked bets: player, market, edge %, confidence tier, odds, Kelly bet size, EV
  - Total exposure and total expected value
  - Bet filter by confidence tier and market type
"""

import streamlit as st
import pandas as pd


@st.cache_data(ttl=900, show_spinner=False)
def _load_bets(bankroll: float, markets: list):
    from src.model.best_bets import build_best_bets, allocate_bankroll
    from src.model.scoring_model import build_rankings
    rankings = build_rankings()
    bets = build_best_bets(bankroll=bankroll, markets=markets, rankings_df=rankings)
    bets = allocate_bankroll(bets, bankroll)
    return bets


def _tier_badge(tier: str) -> str:
    colors = {"High": "#dc2626", "Medium": "#d97706", "Low": "#4b5563"}
    icons  = {"High": "🔥", "Medium": "✅", "Low": "⚠️"}
    c = colors.get(tier, "#4b5563")
    i = icons.get(tier, "")
    return f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:10px;font-size:12px">{i} {tier}</span>'


def render():
    st.subheader("Best Bets Engine", divider="green")

    # ── Sidebar controls (inline) ─────────────────────────────────────────────
    col_bank, col_thresh, col_mkts = st.columns([1, 1, 2])

    with col_bank:
        bankroll = st.number_input("Bankroll ($)", min_value=100, max_value=10000,
                                   value=500, step=50,
                                   help="Your total betting bankroll for this tournament")

    with col_thresh:
        min_edge = st.selectbox("Min edge", [5, 8, 10, 15], index=0,
                                format_func=lambda x: f"{x}%")

    with col_mkts:
        all_markets = ["outright", "top5", "top10", "top20", "make_cut", "round_leader"]
        market_labels = {
            "outright": "Outright", "top5": "Top 5", "top10": "Top 10",
            "top20": "Top 20", "make_cut": "Make Cut", "round_leader": "R1 Leader",
        }
        selected_markets = st.multiselect(
            "Markets",
            options=all_markets,
            default=all_markets,
            format_func=lambda x: market_labels.get(x, x),
        )

    if not selected_markets:
        st.warning("Select at least one market.")
        return

    # ── Confidence filter ─────────────────────────────────────────────────────
    tier_filter = st.radio("Show", ["All", "High only", "High + Medium"],
                           horizontal=True, index=0)

    # ── Load bets ─────────────────────────────────────────────────────────────
    with st.spinner("Calculating best bets…"):
        try:
            bets = _load_bets(bankroll, selected_markets)
        except Exception as e:
            st.error(f"Could not compute bets: {e}")
            return

    # Apply filters
    if tier_filter == "High only":
        bets = [b for b in bets if b["confidence"] == "High"]
    elif tier_filter == "High + Medium":
        bets = [b for b in bets if b["confidence"] in ("High", "Medium")]

    bets = [b for b in bets if b["edge_pct"] >= min_edge]

    if not bets:
        st.info(f"No bets found above {min_edge}% edge with current filters.")
        return

    # ── Bankroll summary metrics ───────────────────────────────────────────────
    total_exposure = sum(b["bet_size"] for b in bets)
    total_ev       = sum(b["expected_value"] for b in bets)
    high_count     = sum(1 for b in bets if b["confidence"] == "High")
    med_count      = sum(1 for b in bets if b["confidence"] == "Medium")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Bankroll", f"${bankroll:,.0f}")
    m2.metric("Total Bets", len(bets))
    m3.metric("Total Exposure", f"${total_exposure:,.0f}",
              delta=f"{total_exposure/bankroll*100:.0f}% of bankroll",
              delta_color="off")
    m4.metric("Expected Value", f"${total_ev:+,.1f}",
              delta_color="normal" if total_ev > 0 else "inverse")
    m5.metric("🔥 High Edge", high_count, delta=f"✅ {med_count} Medium", delta_color="off")

    st.divider()

    # ── Bets table ────────────────────────────────────────────────────────────
    rows = []
    for b in bets:
        rows.append({
            "Player":     b["player_name"],
            "Market":     b["market_label"],
            "Edge":       f"{b['edge_pct']:+.1f}%",
            "Confidence": b["confidence"],
            "Model %":    f"{b['model_pct']:.1f}%",
            "Market %":   f"{b['market_pct']:.1f}%",
            "Odds":       b["american_odds"],
            "Bet Size":   f"${b['bet_size']:.0f}",
            "EV":         f"${b['expected_value']:+.1f}",
            "Bnkrl %":    f"{b['bankroll_pct']:.1f}%",
        })

    df = pd.DataFrame(rows)

    def _style_edge(val):
        try:
            v = float(str(val).replace("%", "").replace("+", ""))
            if v >= 15:
                return "color:#22c55e;font-weight:700"
            elif v >= 8:
                return "color:#4ade80;font-weight:600"
            elif v >= 5:
                return "color:#86efac"
            return ""
        except Exception:
            return ""

    def _style_conf(val):
        mapping = {
            "High":   "color:#ef4444;font-weight:700",
            "Medium": "color:#f59e0b;font-weight:600",
            "Low":    "color:#94a3b8",
        }
        return mapping.get(val, "")

    def _style_ev(val):
        try:
            v = float(str(val).replace("$", "").replace("+", ""))
            return "color:#4ade80;font-weight:600" if v > 0 else "color:#f87171"
        except Exception:
            return ""

    styled = (
        df.style
        .map(_style_edge, subset=["Edge"])
        .map(_style_conf, subset=["Confidence"])
        .map(_style_ev, subset=["EV"])
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Footer ────────────────────────────────────────────────────────────────
    st.divider()
    st.caption(
        "**Sizing:** Half-Kelly · 15% max single bet · 80% max total exposure  |  "
        "**Edge threshold:** Model probability − market implied probability  |  "
        "**Confidence:** High >15% · Medium 8–15% · Low 5–8%"
    )
    st.caption("⚠️ Bet responsibly. These are model-based estimates, not guaranteed outcomes.")
