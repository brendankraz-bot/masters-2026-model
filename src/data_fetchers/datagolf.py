"""
datagolf.py — Data Golf API client and public page scraper
Primary source for: Augusta SG data, course fit scores, field list, live stats

Data Golf API docs: https://datagolf.com/api-access
Augusta course fit: https://datagolf.com/course-fit-tool?course_num=14
Historical data: https://datagolf.com/raw-data-archive
2026 field: https://datagolf.com/major-fields?major=masters

IMPORTANT: Augusta National does NOT participate in ShotLink.
All Augusta SG data is from Data Golf's proprietary tracking (2021 onward only).
"""

import os
import json
import time
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

BASE_API_URL = "https://feeds.datagolf.com"
BASE_WEB_URL = "https://datagolf.com"

# Load API key from environment (optional — falls back to public scraping)
API_KEY = os.getenv("DATAGOLF_API_KEY", "")

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
CACHE_TTL = {
    "field": 3600 * 6,       # field list: 6 hours
    "live_stats": 300,        # live stats: 5 minutes
    "predictions": 3600,      # predictions: 1 hour
    "rankings": 3600 * 12,    # player rankings: 12 hours
    "course_fit": 3600 * 24,  # course fit: 24 hours (static)
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"dg_{key}.json"


def _is_cache_valid(key: str, ttl_seconds: int) -> bool:
    p = _cache_path(key)
    if not p.exists():
        return False
    age = time.time() - p.stat().st_mtime
    return age < ttl_seconds


def _load_cache(key: str) -> dict | list | None:
    p = _cache_path(key)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def _save_cache(key: str, data: dict | list):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_cache_path(key), "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _api_get(endpoint: str, params: dict = None) -> dict | list | None:
    """Call Data Golf API with key. Returns None if no key configured."""
    if not API_KEY:
        return None
    url = f"{BASE_API_URL}/{endpoint}"
    p = {"key": API_KEY, **(params or {})}
    try:
        resp = requests.get(url, params=p, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[datagolf] API error on {endpoint}: {e}")
        return None


def _web_get(path: str) -> requests.Response | None:
    """Fetch a public Data Golf web page."""
    url = f"{BASE_WEB_URL}/{path}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp
    except Exception as e:
        print(f"[datagolf] Web fetch error on {path}: {e}")
        return None


# ---------------------------------------------------------------------------
# Field list
# ---------------------------------------------------------------------------

def get_masters_field(use_cache: bool = True) -> list[dict]:
    """
    Return the 2026 Masters field list.
    Tries: DG API → DG web page → cached field_2026.csv fallback.
    """
    cache_key = "masters_field_2026"
    if use_cache and _is_cache_valid(cache_key, CACHE_TTL["field"]):
        return _load_cache(cache_key)

    # Try API first
    data = _api_get("field-updates", {"tour": "pga", "file_format": "json"})
    if data:
        _save_cache(cache_key, data)
        return data

    # Fall back to CSV on disk
    field_csv = Path(__file__).parent.parent.parent / "data" / "field_2026.csv"
    if field_csv.exists():
        df = pd.read_csv(field_csv)
        result = df.to_dict("records")
        _save_cache(cache_key, result)
        return result

    print("[datagolf] No field data available. Populate data/field_2026.csv.")
    return []


# ---------------------------------------------------------------------------
# Pre-tournament predictions / rankings
# ---------------------------------------------------------------------------

def get_pre_tournament_predictions(use_cache: bool = True) -> list[dict]:
    """
    Fetch Data Golf pre-tournament win probabilities and skill ratings for the Masters.
    Returns list of dicts: player_name, dg_id, win_prob, top5_prob, top10_prob,
                           top20_prob, make_cut_prob, sg_total, sg_ott, sg_app,
                           sg_arg, sg_putt, driving_dist, driving_acc
    """
    cache_key = "pre_tournament_preds"
    if use_cache and _is_cache_valid(cache_key, CACHE_TTL["predictions"]):
        return _load_cache(cache_key)

    data = _api_get(
        "preds/pre-tournament",
        {"tour": "pga", "odds_format": "percent", "file_format": "json"},
    )
    if data:
        players = data.get("baseline_history_fit", data) if isinstance(data, dict) else data
        _save_cache(cache_key, players)
        return players

    print("[datagolf] Pre-tournament predictions unavailable (no API key or key limit reached).")
    return []


# ---------------------------------------------------------------------------
# Player rankings / skill ratings
# ---------------------------------------------------------------------------

def get_player_rankings(use_cache: bool = True) -> list[dict]:
    """
    Fetch Data Golf world rankings with SG breakdowns.
    Fields: player_name, dg_id, dg_rank, owgr, sg_total, sg_ott, sg_app, sg_arg, sg_putt
    """
    cache_key = "player_rankings"
    if use_cache and _is_cache_valid(cache_key, CACHE_TTL["rankings"]):
        return _load_cache(cache_key)

    data = _api_get("preds/get-dg-rankings", {"file_format": "json"})
    if data:
        players = data.get("rankings", data) if isinstance(data, dict) else data
        _save_cache(cache_key, players)
        return players

    print("[datagolf] Player rankings unavailable.")
    return []


# ---------------------------------------------------------------------------
# Live tournament stats
# ---------------------------------------------------------------------------

def get_live_stats(use_cache: bool = True) -> dict:
    """
    Fetch live in-tournament strokes gained stats from Data Golf.
    Returns dict with player-level live SG data during the Masters.
    Refreshes every 5 minutes (matches leaderboard TTL).
    """
    cache_key = "live_stats"
    if use_cache and _is_cache_valid(cache_key, CACHE_TTL["live_stats"]):
        return _load_cache(cache_key)

    data = _api_get(
        "preds/live-tournament-stats",
        {"stats": "sg_total,sg_ott,sg_app,sg_arg,sg_putt", "round": "event_avg", "display": "value", "file_format": "json"},
    )
    if data:
        _save_cache(cache_key, data)
        return data

    print("[datagolf] Live stats unavailable.")
    return {}


# ---------------------------------------------------------------------------
# Historical Augusta SG data
# ---------------------------------------------------------------------------

def get_augusta_historical_sg(use_cache: bool = True) -> pd.DataFrame:
    """
    Load historical Augusta SG averages (2021-2025) from local CSV.
    Falls back to Data Golf API if CSV not populated.

    Returns DataFrame: player_name, rounds, sg_avg_round, sg_app, sg_arg, sg_ott, sg_putt
    """
    csv_path = Path(__file__).parent.parent.parent / "data" / "augusta_sg_2021_2025.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        df.columns = df.columns.str.lower().str.replace(" ", "_")
        return df

    # Try API for historical event stats
    cache_key = "augusta_historical_sg"
    if use_cache and _is_cache_valid(cache_key, CACHE_TTL["course_fit"]):
        data = _load_cache(cache_key)
        return pd.DataFrame(data) if data else pd.DataFrame()

    data = _api_get(
        "historical-stats/get-stats",
        {
            "tour": "pga",
            "event_name": "masters",
            "year": "2021,2022,2023,2024,2025",
            "stat": "sg_total,sg_app,sg_arg,sg_ott,sg_putt",
            "file_format": "json",
        },
    )
    if data:
        _save_cache(cache_key, data)
        return pd.DataFrame(data) if isinstance(data, list) else pd.DataFrame()

    print("[datagolf] Augusta historical SG unavailable. Populate data/augusta_sg_2021_2025.csv.")
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Course fit (Augusta-specific)
# ---------------------------------------------------------------------------

def get_course_fit_scores(use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch Augusta National course fit scores from Data Golf.
    Course number 14 = Augusta National.

    Returns DataFrame: player_name, fit_score, fit_percentile,
                       driving_dist_fit, accuracy_fit, approach_fit, arg_fit, putting_fit
    """
    cache_key = "augusta_course_fit"
    if use_cache and _is_cache_valid(cache_key, CACHE_TTL["course_fit"]):
        data = _load_cache(cache_key)
        return pd.DataFrame(data) if data else pd.DataFrame()

    # Try API
    data = _api_get(
        "preds/course-fit",
        {"course": "augusta_national", "file_format": "json"},
    )
    if data:
        _save_cache(cache_key, data)
        players = data.get("course_fit", data) if isinstance(data, dict) else data
        return pd.DataFrame(players)

    print("[datagolf] Course fit data unavailable via API. No API key or endpoint changed.")
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Hole-by-hole stats (Augusta)
# ---------------------------------------------------------------------------

def get_hole_stats(use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch per-player, per-hole historical scoring data at Augusta.
    Returns DataFrame: player_name, hole, avg_score, vs_field, rounds_played
    """
    csv_path = Path(__file__).parent.parent.parent / "data" / "hole_by_hole_historical.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        df.columns = df.columns.str.lower().str.replace(" ", "_")
        return df

    # Try API
    cache_key = "augusta_hole_stats"
    if use_cache and _is_cache_valid(cache_key, CACHE_TTL["course_fit"]):
        data = _load_cache(cache_key)
        return pd.DataFrame(data) if data else pd.DataFrame()

    data = _api_get(
        "historical-stats/hole-scores",
        {"tour": "pga", "event_name": "masters", "file_format": "json"},
    )
    if data:
        _save_cache(cache_key, data)
        return pd.DataFrame(data) if isinstance(data, list) else pd.DataFrame()

    print("[datagolf] Hole-by-hole stats unavailable. Populate data/hole_by_hole_historical.csv.")
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Odds from Data Golf (pre-tournament and live)
# ---------------------------------------------------------------------------

def get_dg_odds(use_cache: bool = True) -> list[dict]:
    """
    Fetch aggregated market odds from Data Golf's betting tools endpoint.
    Returns list: player_name, win_odds_pct (avg across books), top5_pct, top10_pct
    """
    cache_key = "dg_odds"
    if use_cache and _is_cache_valid(cache_key, CACHE_TTL["live_stats"]):
        return _load_cache(cache_key)

    data = _api_get(
        "betting-tools/outrights",
        {"tour": "pga", "market": "win", "odds_format": "percent", "file_format": "json"},
    )
    if data:
        odds = data.get("odds", data) if isinstance(data, dict) else data
        _save_cache(cache_key, odds)
        return odds

    return []


# ---------------------------------------------------------------------------
# Utility: normalize player names for cross-source matching
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """Lowercase, strip accents and punctuation for fuzzy matching."""
    import unicodedata
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    return name.lower().strip()


def build_player_lookup(field: list[dict], name_key: str = "player_name") -> dict:
    """Return {normalized_name: player_dict} for fast lookup."""
    return {normalize_name(p[name_key]): p for p in field if name_key in p}


# ---------------------------------------------------------------------------
# Status check
# ---------------------------------------------------------------------------

def status() -> dict:
    """Quick check on what data is available."""
    field_csv = Path(__file__).parent.parent.parent / "data" / "field_2026.csv"
    sg_csv = Path(__file__).parent.parent.parent / "data" / "augusta_sg_2021_2025.csv"
    hole_csv = Path(__file__).parent.parent.parent / "data" / "hole_by_hole_historical.csv"

    return {
        "api_key_configured": bool(API_KEY),
        "field_csv_exists": field_csv.exists(),
        "sg_historical_csv_exists": sg_csv.exists(),
        "hole_stats_csv_exists": hole_csv.exists(),
        "cache_dir_exists": CACHE_DIR.exists(),
    }


if __name__ == "__main__":
    print("Data Golf status:")
    s = status()
    for k, v in s.items():
        icon = "✓" if v else "✗"
        print(f"  {icon} {k}: {v}")
    print()

    field = get_masters_field()
    print(f"Field loaded: {len(field)} players")

    rankings = get_player_rankings()
    print(f"Rankings loaded: {len(rankings)} players")
