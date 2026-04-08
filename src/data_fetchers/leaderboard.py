"""
leaderboard.py — ESPN live leaderboard scraper for the Masters Tournament
5-minute TTL cache during live rounds. Falls back to cache on scrape failure.

Based on: github.com/brett-hobbs/espn-pga-scraper
          github.com/jmstjordan/PGALiveLeaderboard
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime

CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "cache" / "leaderboard.json"
CACHE_TTL_SECONDS = 300  # 5 minutes

# ESPN leaderboard endpoints — tries in order
ESPN_ENDPOINTS = [
    "https://site.api.espn.com/apis/site/v2/sports/golf/pga/leaderboard",
    "https://site.web.api.espn.com/apis/site/v2/sports/golf/leaderboard?league=pga",
]

# Fallback: HTML scrape
ESPN_LEADERBOARD_URL = "https://www.espn.com/golf/leaderboard/_/tour/pga"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

TOURNAMENT_ROUNDS = {1: "2026-04-09", 2: "2026-04-10", 3: "2026-04-11", 4: "2026-04-12"}
AUGUSTA_PAR = 72
HOLE_PARS = [4, 5, 4, 3, 4, 3, 4, 5, 4, 4, 4, 3, 5, 4, 5, 3, 4, 4]  # holes 1-18


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_valid() -> bool:
    if not CACHE_FILE.exists():
        return False
    return (time.time() - CACHE_FILE.stat().st_mtime) < CACHE_TTL_SECONDS


def _load_cache() -> dict | None:
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return None


def _save_cache(data: dict):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def _fetch_espn_api() -> dict | None:
    """Try ESPN JSON API endpoints."""
    for url in ESPN_ENDPOINTS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            continue
    return None


def _parse_espn_api(raw: dict) -> list[dict]:
    """
    Parse ESPN API response into normalized player list.
    Returns list of dicts: player_name, position, total_score, round_scores,
                           current_round, thru, today_score, status, is_active
    """
    players = []
    try:
        events = raw.get("events", [])
        if not events:
            return []
        event = events[0]
        competitions = event.get("competitions", [])
        if not competitions:
            return []
        competitors = competitions[0].get("competitors", [])

        for c in competitors:
            athlete = c.get("athlete", {})
            stats = {s.get("name", ""): s.get("displayValue", "") for s in c.get("statistics", [])}

            name = athlete.get("displayName", "")
            position = c.get("status", {}).get("position", {}).get("displayName", "")
            total = c.get("score", {}).get("displayValue", "E")
            status = c.get("status", {}).get("type", {}).get("name", "")

            # Round scores
            linescores = c.get("linescores", [])
            round_scores = []
            for ls in linescores:
                val = ls.get("displayValue", "-")
                round_scores.append(val)

            # Current round / thru
            current_round = len([s for s in round_scores if s not in ("-", "")])
            thru = stats.get("holesPlayed", stats.get("thru", "-"))

            # Today's score
            today = round_scores[-1] if round_scores else "-"

            players.append({
                "player_name": name,
                "position": position,
                "total_score": _parse_score(total),
                "total_display": total,
                "round_scores": round_scores,
                "current_round": current_round,
                "thru": thru,
                "today_score": _parse_score(today),
                "today_display": today,
                "status": status,
                "is_active": status not in ("cut", "wd", "dq"),
            })

    except Exception as e:
        print(f"[leaderboard] Parse error: {e}")

    return players


def _parse_score(val: str) -> int | None:
    """Convert score display (E, -4, +2, 72) to integer vs par."""
    if val in ("E", "EVEN", ""):
        return 0
    try:
        v = int(val.replace("+", ""))
        # If it looks like a raw round score (60-80), convert vs par
        if 60 <= abs(v) <= 85:
            return v - AUGUSTA_PAR
        return v
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_leaderboard(use_cache: bool = True, force_refresh: bool = False) -> dict:
    """
    Fetch the live Masters leaderboard.
    Returns: {
        "players": [...],          # sorted by position
        "current_round": int,
        "last_updated": str,
        "tournament_status": str,  # "pre" | "active" | "complete"
        "source": str,
    }
    """
    if use_cache and not force_refresh and _cache_valid():
        cached = _load_cache()
        if cached:
            return cached

    raw = _fetch_espn_api()
    if raw:
        players = _parse_espn_api(raw)
        if players:
            result = _build_result(players, source="espn_api")
            _save_cache(result)
            return result

    # Fall back to stale cache
    cached = _load_cache()
    if cached:
        cached["stale"] = True
        return cached

    return _empty_leaderboard()


def _build_result(players: list[dict], source: str) -> dict:
    # Sort by total_score (None last)
    players.sort(key=lambda p: (p["total_score"] is None, p["total_score"] or 0))

    # Determine tournament state
    rounds_active = [p["current_round"] for p in players if p["is_active"]]
    current_round = max(rounds_active) if rounds_active else 0
    status = "pre" if current_round == 0 else ("complete" if all(
        p["status"] == "complete" for p in players if p["is_active"]
    ) else "active")

    return {
        "players": players,
        "current_round": current_round,
        "last_updated": datetime.now().isoformat(),
        "tournament_status": status,
        "source": source,
        "stale": False,
    }


def _empty_leaderboard() -> dict:
    return {
        "players": [],
        "current_round": 0,
        "last_updated": datetime.now().isoformat(),
        "tournament_status": "pre",
        "source": "none",
        "stale": True,
    }


# ---------------------------------------------------------------------------
# Helpers used by live_model.py
# ---------------------------------------------------------------------------

def get_player_live(player_name: str, leaderboard: dict | None = None) -> dict | None:
    """Look up a single player's live data by name (fuzzy)."""
    if leaderboard is None:
        leaderboard = get_leaderboard()
    name_lower = player_name.lower()
    for p in leaderboard.get("players", []):
        if name_lower in p["player_name"].lower() or p["player_name"].lower() in name_lower:
            return p
    return None


def get_current_round_field_avg(leaderboard: dict | None = None) -> float | None:
    """
    Return the average today_score across all active players who have completed ≥9 holes.
    Used for field conditions adjustment in live_model.py.
    """
    if leaderboard is None:
        leaderboard = get_leaderboard()
    scores = [
        p["today_score"]
        for p in leaderboard.get("players", [])
        if p["is_active"] and p["today_score"] is not None and p.get("thru") not in ("-", None, "0", 0)
    ]
    if not scores:
        return None
    return sum(scores) / len(scores)


def get_hole_by_hole_live(player_name: str) -> list[int | None]:
    """
    Return list of 18 scores vs par for current round (None = not yet played).
    ESPN API may not expose hole-by-hole; returns empty if unavailable.
    """
    lb = get_leaderboard()
    player = get_player_live(player_name, lb)
    if not player:
        return [None] * 18
    # ESPN linescores are per-round, not per-hole — hole-level not always available
    return [None] * 18


if __name__ == "__main__":
    print("Fetching Masters leaderboard...\n")
    lb = get_leaderboard(use_cache=False)
    print(f"Status: {lb['tournament_status']} | Round: {lb['current_round']} | Source: {lb['source']}")
    print(f"Last updated: {lb['last_updated']}")
    print(f"Players loaded: {len(lb['players'])}\n")
    for p in lb["players"][:10]:
        print(f"  {p['position']:>4}  {p['player_name']:<28}  {p['total_display']:>4}  R{p['current_round']} Thru:{p['thru']}")
