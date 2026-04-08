"""
best_bets.py — Best Bets engine for Masters 2026

Edge calculation:
    edge = model_probability - market_implied_probability
    Minimum threshold: 5% edge to surface a bet

Kelly sizing (half-Kelly for safety):
    f = (b × p - q) / b      where b = decimal_odds - 1
    bet_size = f × 0.5 × bankroll

Confidence tiers:
    High   : edge > 15%
    Medium : edge 8–15%
    Low    : edge 5–8%

Markets covered:
    Outright winner, Top 5, Top 10, Top 20, Make Cut, Round Leader, Head-to-Head
"""

import math
from typing import Optional

from src.model.scoring_model import build_rankings, _safe_float
from src.data_fetchers.odds import get_consensus_odds, get_draftkings_odds, _american_to_prob, _prob_to_american

DEFAULT_BANKROLL   = 500.0
MIN_EDGE_PCT       = 5.0
EDGE_HIGH          = 15.0
EDGE_MEDIUM        = 8.0
MAX_SINGLE_BET_PCT = 0.15    # never bet more than 15% of bankroll on a single play

MARKET_TYPES = ["outright", "top5", "top10", "top20", "make_cut", "round_leader"]

MARKET_LABELS = {
    "outright":     "Outright Winner",
    "top5":         "Top 5 Finish",
    "top10":        "Top 10 Finish",
    "top20":        "Top 20 Finish",
    "make_cut":     "Make the Cut",
    "round_leader": "Round 1 Leader",
}


# ---------------------------------------------------------------------------
# Probability conversions
# ---------------------------------------------------------------------------

def _decimal_odds(american: str) -> float:
    """Convert American odds string to decimal odds."""
    prob = _american_to_prob(american)
    return round(1 / prob, 3) if prob > 0 else 0.0


def _implied_prob(american: str) -> float:
    """Convert American odds to raw implied probability (includes vig)."""
    return _american_to_prob(american)


def _remove_vig(probs: list[float]) -> list[float]:
    """Normalize a list of implied probabilities to sum to 1.0 (remove vig)."""
    total = sum(probs)
    if total <= 0:
        return probs
    return [p / total for p in probs]


# ---------------------------------------------------------------------------
# Kelly criterion
# ---------------------------------------------------------------------------

def kelly_fraction(model_prob: float, decimal_odds: float) -> float:
    """
    Full Kelly fraction: f = (b×p - q) / b
    b = decimal_odds - 1  (profit per unit wagered)
    p = model probability of winning
    q = 1 - p
    """
    b = decimal_odds - 1.0
    if b <= 0 or model_prob <= 0:
        return 0.0
    p = model_prob
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, f)


def half_kelly_bet(model_prob: float, american_odds: str, bankroll: float) -> float:
    """
    Return half-Kelly bet size in dollars. Capped at MAX_SINGLE_BET_PCT × bankroll.
    """
    dec = _decimal_odds(american_odds)
    if dec <= 1.0:
        return 0.0
    f = kelly_fraction(model_prob, dec)
    half_f = f * 0.5
    max_bet = bankroll * MAX_SINGLE_BET_PCT
    bet = min(half_f * bankroll, max_bet)
    return round(max(0.0, bet), 2)


def expected_value(model_prob: float, american_odds: str, bet_size: float) -> float:
    """Expected value of a bet in dollars."""
    dec = _decimal_odds(american_odds)
    if dec <= 1.0 or bet_size <= 0:
        return 0.0
    win_amount = bet_size * (dec - 1.0)
    ev = model_prob * win_amount - (1.0 - model_prob) * bet_size
    return round(ev, 2)


# ---------------------------------------------------------------------------
# Edge calculation per player per market
# ---------------------------------------------------------------------------

def _compute_edge(model_prob: float, market_prob: float) -> float:
    """Edge in percentage points: model_pct - market_pct."""
    return round((model_prob - market_prob) * 100, 2)


def _confidence_tier(edge_pct: float) -> str:
    if edge_pct >= EDGE_HIGH:
        return "High"
    elif edge_pct >= EDGE_MEDIUM:
        return "Medium"
    else:
        return "Low"


def _edge_emoji(tier: str) -> str:
    return {"High": "🔥", "Medium": "✅", "Low": "⚠️"}.get(tier, "")


# ---------------------------------------------------------------------------
# Market probability derivation from model
# ---------------------------------------------------------------------------

def derive_market_probs(rankings_row: dict, market: str) -> float:
    """
    Return model probability for a player in a given market.
    Uses scoring_model output columns where available.
    """
    if market == "outright":
        return _safe_float(rankings_row.get("win_probability"))
    elif market == "top5":
        return _safe_float(rankings_row.get("top5_probability"))
    elif market == "top10":
        return _safe_float(rankings_row.get("top10_probability"))
    elif market == "top20":
        return _safe_float(rankings_row.get("top20_probability"))
    elif market == "make_cut":
        return _safe_float(rankings_row.get("make_cut_probability"))
    elif market == "round_leader":
        # R1 leader ≈ 3× outright probability (roughly)
        return min(_safe_float(rankings_row.get("win_probability")) * 3.0, 0.50)
    return 0.0


# ---------------------------------------------------------------------------
# Main best bets builder
# ---------------------------------------------------------------------------

def build_best_bets(
    bankroll: float = DEFAULT_BANKROLL,
    min_edge_pct: float = MIN_EDGE_PCT,
    markets: list[str] = None,
    rankings_df=None,
    consensus_odds: dict = None,
    use_live: bool = False,
    live_rankings_df=None,
) -> list[dict]:
    """
    Compute all best bets across players and markets.

    Returns list of bet dicts sorted by edge descending:
    {
        player_name, market, market_label,
        model_prob, market_prob, edge_pct, confidence,
        american_odds, decimal_odds,
        kelly_fraction, bet_size, expected_value,
        bankroll_pct,
    }
    """
    if markets is None:
        markets = MARKET_TYPES

    # Load rankings
    if rankings_df is None:
        rankings_df = build_rankings()

    # Load market odds
    if consensus_odds is None:
        try:
            consensus_odds = get_consensus_odds()
        except Exception:
            consensus_odds = {}

    # Fall back to DK manual if consensus empty
    if not consensus_odds:
        dk = get_draftkings_odds()
        consensus_odds = {
            name: {
                "win_prob_consensus": d["win_prob"],
                "implied_pct_consensus": d["implied_pct"],
                "american_odds_consensus": d["american_odds"],
                "top5_implied_pct":   _safe_float(d["win_prob"]) * 6.0 * 100,
                "top10_implied_pct":  _safe_float(d["win_prob"]) * 11.0 * 100,
                "top20_implied_pct":  _safe_float(d["win_prob"]) * 18.0 * 100,
                "make_cut_implied_pct": 75.0,
            }
            for name, d in dk.items()
        }

    # Use live rankings if available
    source_rankings = live_rankings_df if (use_live and live_rankings_df is not None) else rankings_df

    bets = []
    for _, row in rankings_df.iterrows():
        player = row["player_name"]

        # Find market odds for this player (fuzzy match)
        mkt_data = _find_player_odds(player, consensus_odds)

        for market in markets:
            model_prob = derive_market_probs(row.to_dict(), market)
            if model_prob <= 0:
                continue

            market_prob, american = _get_market_prob_and_odds(market, mkt_data, model_prob)
            if market_prob <= 0 or not american:
                continue

            edge = _compute_edge(model_prob, market_prob)
            if edge < min_edge_pct:
                continue

            dec_odds = _decimal_odds(american)
            kelly_f  = kelly_fraction(model_prob, dec_odds)
            bet_sz   = half_kelly_bet(model_prob, american, bankroll)
            ev       = expected_value(model_prob, american, bet_sz)
            tier     = _confidence_tier(edge)

            bets.append({
                "player_name":   player,
                "market":        market,
                "market_label":  MARKET_LABELS.get(market, market),
                "model_prob":    round(model_prob, 4),
                "model_pct":     round(model_prob * 100, 1),
                "market_prob":   round(market_prob, 4),
                "market_pct":    round(market_prob * 100, 1),
                "edge_pct":      edge,
                "confidence":    tier,
                "american_odds": american,
                "decimal_odds":  dec_odds,
                "kelly_fraction": round(kelly_f, 4),
                "half_kelly":    round(kelly_f * 0.5, 4),
                "bet_size":      bet_sz,
                "expected_value": ev,
                "bankroll_pct":  round(bet_sz / bankroll * 100, 1) if bankroll > 0 else 0,
            })

    # Sort by edge descending, then confidence tier
    tier_order = {"High": 0, "Medium": 1, "Low": 2}
    bets.sort(key=lambda b: (tier_order.get(b["confidence"], 3), -b["edge_pct"]))
    return bets


def _find_player_odds(player_name: str, odds_dict: dict) -> dict:
    """Fuzzy match player name to odds dict. Returns empty dict if no match."""
    name_lower = player_name.lower()
    # Exact match first
    if player_name in odds_dict:
        return odds_dict[player_name]
    # Last-name match
    last = name_lower.split()[-1]
    for key in odds_dict:
        if last in key.lower():
            return odds_dict[key]
    return {}


def _get_market_prob_and_odds(market: str, mkt_data: dict, model_prob: float) -> tuple[float, str]:
    """
    Return (market_implied_probability, american_odds_string) for a market.
    Derives Top5/10/20/Cut from outright when not directly available.
    """
    win_prob  = _safe_float(mkt_data.get("win_prob_consensus"))
    win_odds  = mkt_data.get("american_odds_consensus", "")

    if market == "outright":
        return win_prob, win_odds

    elif market == "top5":
        implied = _safe_float(mkt_data.get("top5_implied_pct")) / 100
        if implied <= 0 and win_prob > 0:
            implied = min(win_prob * 6.5, 0.85)
        # Derive approximate American odds for top5
        odds = _prob_to_american(implied) if implied > 0 else ""
        return implied, odds

    elif market == "top10":
        implied = _safe_float(mkt_data.get("top10_implied_pct")) / 100
        if implied <= 0 and win_prob > 0:
            implied = min(win_prob * 11.0, 0.90)
        odds = _prob_to_american(implied) if implied > 0 else ""
        return implied, odds

    elif market == "top20":
        implied = _safe_float(mkt_data.get("top20_implied_pct")) / 100
        if implied <= 0 and win_prob > 0:
            implied = min(win_prob * 18.0, 0.95)
        odds = _prob_to_american(implied) if implied > 0 else ""
        return implied, odds

    elif market == "make_cut":
        implied = _safe_float(mkt_data.get("make_cut_implied_pct")) / 100
        if implied <= 0:
            implied = 0.75    # default market assumption
        odds = _prob_to_american(implied) if implied > 0 else ""
        return implied, odds

    elif market == "round_leader":
        r1_prob = min(win_prob * 3.2, 0.40) if win_prob > 0 else model_prob * 3.0
        odds = _prob_to_american(r1_prob) if r1_prob > 0 else ""
        return r1_prob, odds

    return 0.0, ""


# ---------------------------------------------------------------------------
# Bankroll management
# ---------------------------------------------------------------------------

def allocate_bankroll(bets: list[dict], bankroll: float) -> list[dict]:
    """
    Re-scale bet sizes so total exposure stays within bankroll.
    Reduces all bets proportionally if total would exceed bankroll × 0.80.
    """
    total_exposure = sum(b["bet_size"] for b in bets)
    max_exposure = bankroll * 0.80

    if total_exposure > max_exposure and total_exposure > 0:
        scale = max_exposure / total_exposure
        for b in bets:
            b["bet_size"]      = round(b["bet_size"] * scale, 2)
            b["expected_value"] = expected_value(
                b["model_prob"], b["american_odds"], b["bet_size"]
            )
            b["bankroll_pct"]  = round(b["bet_size"] / bankroll * 100, 1)

    return bets


def update_bankroll(bankroll: float, settled_bets: list[dict]) -> float:
    """
    Update bankroll after bets are settled.
    settled_bets items need 'bet_size', 'decimal_odds', 'won' (bool).
    """
    for bet in settled_bets:
        if bet.get("won"):
            profit = bet["bet_size"] * (bet["decimal_odds"] - 1.0)
            bankroll += profit
        else:
            bankroll -= bet["bet_size"]
    return round(bankroll, 2)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_best_bets(bets: list[dict], bankroll: float = DEFAULT_BANKROLL,
                     max_display: int = 15) -> str:
    """Return a formatted best bets table string for display."""
    if not bets:
        return "No best bets found with current edge threshold."

    lines = [
        f"\n{'='*72}",
        f"  MASTERS 2026 — BEST BETS  (Bankroll: ${bankroll:.0f})",
        f"  {len(bets)} bets found above {MIN_EDGE_PCT}% edge threshold",
        f"{'='*72}",
        f"  {'Player':<22} {'Market':<17} {'Edge':>5} {'Tier':<8} {'Odds':>7} {'Bet $':>6} {'EV $':>6}",
        f"  {'-'*68}",
    ]

    for bet in bets[:max_display]:
        tier_icon = _edge_emoji(bet["confidence"])
        lines.append(
            f"  {bet['player_name']:<22} "
            f"{bet['market_label']:<17} "
            f"{bet['edge_pct']:>+5.1f}% "
            f"{tier_icon}{bet['confidence']:<7} "
            f"{bet['american_odds']:>7} "
            f"${bet['bet_size']:>5.0f} "
            f"${bet['expected_value']:>+5.1f}"
        )

    total_exposure = sum(b["bet_size"] for b in bets[:max_display])
    total_ev       = sum(b["expected_value"] for b in bets[:max_display])
    lines += [
        f"  {'-'*68}",
        f"  {'TOTAL EXPOSURE':<40} ${total_exposure:>6.0f}",
        f"  {'TOTAL EXPECTED VALUE':<40} ${total_ev:>+6.1f}",
        f"{'='*72}\n",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print("Building Masters 2026 Best Bets...\n")
    rankings = build_rankings()
    bets = build_best_bets(bankroll=500.0, rankings_df=rankings)
    bets = allocate_bankroll(bets, 500.0)
    print(format_best_bets(bets, bankroll=500.0))
    print(f"Total bets with edge ≥ {MIN_EDGE_PCT}%: {len(bets)}")
