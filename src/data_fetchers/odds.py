"""
odds.py — Betting odds fetcher for Masters 2026
Sources: Polymarket (public CLOB API), Kalshi (public API), Data Golf odds,
         DraftKings (manual entry fallback)

Polymarket API: https://clob.polymarket.com/markets
Kalshi: https://trading-api.kalshi.com/trade-api/v2/markets
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_TTL = 300  # 5 minutes for live odds

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Polymarket CLOB API
POLYMARKET_BASE = "https://clob.polymarket.com"

# Kalshi API
KALSHI_BASE = "https://trading-api.kalshi.com/trade-api/v2"

# Known Polymarket Masters 2026 condition ID (winner market)
POLYMARKET_MASTERS_SLUG = "masters-winner-2026"


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"odds_{key}.json"


def _cache_valid(key: str, ttl: int = CACHE_TTL) -> bool:
    p = _cache_path(key)
    if not p.exists():
        return False
    return (time.time() - p.stat().st_mtime) < ttl


def _load_cache(key: str):
    p = _cache_path(key)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def _save_cache(key: str, data):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_cache_path(key), "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# Polymarket
# ---------------------------------------------------------------------------

def _fetch_polymarket_markets(query: str = "masters golf 2026") -> list[dict]:
    """Search Polymarket markets for Masters-related events."""
    try:
        resp = requests.get(
            f"{POLYMARKET_BASE}/markets",
            params={"next_cursor": "", "limit": 100},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        all_markets = data.get("data", [])
        # Filter for Masters-related markets
        keywords = ["masters", "augusta", "golf", "pga"]
        filtered = [
            m for m in all_markets
            if any(kw in m.get("question", "").lower() or kw in m.get("description", "").lower()
                   for kw in keywords)
        ]
        return filtered
    except Exception as e:
        print(f"[odds] Polymarket fetch error: {e}")
        return []


def _polymarket_to_player_probs(markets: list[dict]) -> dict[str, float]:
    """
    Extract player win probabilities from Polymarket markets.
    Returns {player_name: probability_0_to_1}
    """
    probs = {}
    for market in markets:
        question = market.get("question", "")
        tokens = market.get("tokens", [])
        if not tokens:
            continue
        # Each token = one outcome; price = probability (0-1)
        for token in tokens:
            outcome = token.get("outcome", "")
            price = token.get("price", 0)
            if outcome and price:
                # outcome is player name in winner markets
                probs[outcome] = float(price)
    return probs


def get_polymarket_odds(use_cache: bool = True) -> dict[str, dict]:
    """
    Fetch Masters winner odds from Polymarket.
    Returns {player_name: {"win_prob": float, "implied_pct": float, "source": "polymarket"}}
    """
    cache_key = "polymarket"
    if use_cache and _cache_valid(cache_key):
        cached = _load_cache(cache_key)
        if cached:
            return cached

    markets = _fetch_polymarket_markets()
    probs = _polymarket_to_player_probs(markets)

    result = {
        name: {
            "win_prob": prob,
            "implied_pct": round(prob * 100, 2),
            "american_odds": _prob_to_american(prob),
            "source": "polymarket",
        }
        for name, prob in probs.items()
        if prob > 0.001  # filter dust
    }

    if result:
        _save_cache(cache_key, result)

    return result


# ---------------------------------------------------------------------------
# Kalshi
# ---------------------------------------------------------------------------

def _fetch_kalshi_golf_markets() -> list[dict]:
    """Fetch Kalshi markets tagged as golf/masters."""
    try:
        resp = requests.get(
            f"{KALSHI_BASE}/markets",
            params={"status": "open", "series_ticker": "MASTERS"},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("markets", [])
        # Try broader search
        resp2 = requests.get(
            f"{KALSHI_BASE}/markets",
            params={"status": "open", "limit": 200},
            headers=HEADERS,
            timeout=10,
        )
        if resp2.status_code == 200:
            all_mkts = resp2.json().get("markets", [])
            return [m for m in all_mkts
                    if "master" in m.get("title", "").lower()
                    or "golf" in m.get("title", "").lower()
                    or "augusta" in m.get("title", "").lower()]
    except Exception as e:
        print(f"[odds] Kalshi fetch error: {e}")
    return []


def get_kalshi_odds(use_cache: bool = True) -> dict[str, dict]:
    """
    Fetch Masters odds from Kalshi.
    Returns {player_name: {"win_prob": float, "implied_pct": float, "source": "kalshi"}}
    """
    cache_key = "kalshi"
    if use_cache and _cache_valid(cache_key):
        cached = _load_cache(cache_key)
        if cached:
            return cached

    markets = _fetch_kalshi_golf_markets()
    result = {}

    for market in markets:
        yes_price = market.get("yes_bid", market.get("yes_ask", 0))
        title = market.get("title", "")
        ticker = market.get("ticker", "")
        # Kalshi prices are cents (0-99)
        prob = yes_price / 100 if yes_price else 0
        if prob > 0:
            result[title] = {
                "win_prob": prob,
                "implied_pct": round(prob * 100, 2),
                "american_odds": _prob_to_american(prob),
                "ticker": ticker,
                "source": "kalshi",
            }

    if result:
        _save_cache(cache_key, result)

    return result


# ---------------------------------------------------------------------------
# DraftKings — manual entry fallback
# ---------------------------------------------------------------------------

# Manually entered odds (American format) — update as needed pre-tournament
# Source: sportsbook.draftkings.com/leagues/golf/us-masters
DRAFTKINGS_MANUAL = {
    "Scottie Scheffler":  {"american": "+490"},
    "Jon Rahm":           {"american": "+910"},
    "Bryson DeChambeau":  {"american": "+1075"},
    "Rory McIlroy":       {"american": "+1175"},
    "Ludvig Aberg":       {"american": "+1700"},
    "Xander Schauffele":  {"american": "+1800"},
    "Collin Morikawa":    {"american": "+2000"},
    "Tommy Fleetwood":    {"american": "+2500"},
    "Hideki Matsuyama":   {"american": "+3500"},
    "Viktor Hovland":     {"american": "+3000"},
    "Patrick Cantlay":    {"american": "+3000"},
    "Jordan Spieth":      {"american": "+5500"},
    "Justin Thomas":      {"american": "+9000"},
    "Tony Finau":         {"american": "+4000"},
    "Sungjae Im":         {"american": "+4500"},
    "Shane Lowry":        {"american": "+4000"},
    "Tyrrell Hatton":     {"american": "+4000"},
    "Russell Henley":     {"american": "+5000"},
    "Wyndham Clark":      {"american": "+5500"},
    "Min Woo Lee":        {"american": "+8000"},
    "Cameron Young":      {"american": "+9000"},
    "Brooks Koepka":      {"american": "+12000"},
    "Cameron Smith":      {"american": "+10000"},
    "Max Homa":           {"american": "+12000"},
    "Joaquin Niemann":    {"american": "+4000"},
}


def get_draftkings_odds() -> dict[str, dict]:
    """Return manually entered DraftKings odds as normalized probability dict."""
    result = {}
    for player, data in DRAFTKINGS_MANUAL.items():
        american = data.get("american", "")
        prob = _american_to_prob(american)
        result[player] = {
            "win_prob": prob,
            "implied_pct": round(prob * 100, 2),
            "american_odds": american,
            "source": "draftkings_manual",
        }
    return result


# ---------------------------------------------------------------------------
# Merged odds (consensus)
# ---------------------------------------------------------------------------

def get_consensus_odds(use_cache: bool = True) -> dict[str, dict]:
    """
    Merge odds from all available sources into a consensus probability.
    Returns {player_name: {
        "win_prob_consensus": float,   # avg across sources
        "implied_pct_consensus": float,
        "american_odds_consensus": str,
        "sources": {source: prob},
        "top5_implied_pct": float,
        "top10_implied_pct": float,
        "make_cut_implied_pct": float,
    }}
    """
    cache_key = "consensus"
    if use_cache and _cache_valid(cache_key, ttl=600):
        cached = _load_cache(cache_key)
        if cached:
            return cached

    dk = get_draftkings_odds()
    poly = get_polymarket_odds(use_cache=use_cache)

    # Build merged dict — start with DK as base (most complete)
    merged = {}
    for player, data in dk.items():
        merged[player] = {
            "sources": {"draftkings": data["win_prob"]},
            "top5_implied_pct": _estimate_top5(data["win_prob"]),
            "top10_implied_pct": _estimate_top10(data["win_prob"]),
            "make_cut_implied_pct": _estimate_make_cut(data["win_prob"]),
        }

    # Add Polymarket
    for player, data in poly.items():
        matched = _fuzzy_match_player(player, list(merged.keys()))
        if matched:
            merged[matched]["sources"]["polymarket"] = data["win_prob"]
        else:
            merged[player] = {
                "sources": {"polymarket": data["win_prob"]},
                "top5_implied_pct": _estimate_top5(data["win_prob"]),
                "top10_implied_pct": _estimate_top10(data["win_prob"]),
                "make_cut_implied_pct": _estimate_make_cut(data["win_prob"]),
            }

    # Calculate consensus
    result = {}
    for player, data in merged.items():
        probs = list(data["sources"].values())
        consensus = sum(probs) / len(probs)
        result[player] = {
            "win_prob_consensus": round(consensus, 4),
            "implied_pct_consensus": round(consensus * 100, 2),
            "american_odds_consensus": _prob_to_american(consensus),
            "sources": data["sources"],
            "top5_implied_pct": round(data["top5_implied_pct"], 1),
            "top10_implied_pct": round(data["top10_implied_pct"], 1),
            "make_cut_implied_pct": round(data["make_cut_implied_pct"], 1),
            "last_updated": datetime.now().isoformat(),
        }

    if result:
        _save_cache(cache_key, result)

    return result


# ---------------------------------------------------------------------------
# Odds conversion utilities
# ---------------------------------------------------------------------------

def _prob_to_american(prob: float) -> str:
    """Convert win probability to American odds string."""
    if prob <= 0 or prob >= 1:
        return "N/A"
    if prob >= 0.5:
        return f"{round(-prob / (1 - prob) * 100)}"
    else:
        return f"+{round((1 - prob) / prob * 100)}"


def _american_to_prob(odds_str: str) -> float:
    """Convert American odds string (+550, -110) to implied probability."""
    try:
        odds = int(odds_str.replace("+", ""))
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)
    except (ValueError, TypeError):
        return 0.0


def _prob_to_decimal(prob: float) -> float:
    """Convert probability to decimal odds."""
    return round(1 / prob, 2) if prob > 0 else 0.0


def _estimate_top5(win_prob: float) -> float:
    """Rough estimate of top-5 probability from win probability."""
    return min(win_prob * 6.5 * 100, 85.0)


def _estimate_top10(win_prob: float) -> float:
    """Rough estimate of top-10 probability from win probability."""
    return min(win_prob * 11 * 100, 90.0)


def _estimate_make_cut(win_prob: float) -> float:
    """Rough estimate of make-cut probability."""
    if win_prob >= 0.05:
        return 90.0
    elif win_prob >= 0.02:
        return 80.0
    elif win_prob >= 0.01:
        return 70.0
    return 55.0


def _fuzzy_match_player(name: str, candidates: list[str], threshold: float = 0.7) -> str | None:
    """Simple fuzzy name match by token overlap."""
    name_tokens = set(name.lower().split())
    best_score = 0.0
    best_match = None
    for candidate in candidates:
        cand_tokens = set(candidate.lower().split())
        overlap = len(name_tokens & cand_tokens)
        score = overlap / max(len(name_tokens), len(cand_tokens))
        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate
    return best_match


if __name__ == "__main__":
    print("Fetching Masters odds...\n")
    dk = get_draftkings_odds()
    print(f"DraftKings: {len(dk)} players loaded")
    print("\nTop 10 favorites:")
    sorted_players = sorted(dk.items(), key=lambda x: x[1]["win_prob"], reverse=True)
    for name, data in sorted_players[:10]:
        print(f"  {name:<28} {data['american_odds']:>7}  ({data['implied_pct']:.1f}%)")
