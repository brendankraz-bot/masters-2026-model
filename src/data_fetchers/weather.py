"""
weather.py — Open-Meteo weather fetcher for Augusta National
Coordinates: 33.5021° N, -82.0232° W (America/New_York)
No API key required. Free, public endpoint.
"""

import requests
import json
import os
from datetime import datetime, date
from pathlib import Path

AUGUSTA_LAT = 33.5021
AUGUSTA_LON = -82.0232
TIMEZONE = "America/New_York"
CACHE_FILE = Path(__file__).parent.parent.parent / "data" / "cache" / "weather.json"
CACHE_TTL_HOURS = 1  # refresh every hour

TOURNAMENT_ROUNDS = {
    1: "2026-04-09",
    2: "2026-04-10",
    3: "2026-04-11",
    4: "2026-04-12",
}

BASE_URL = "https://api.open-meteo.com/v1/forecast"

PARAMS = {
    "latitude": AUGUSTA_LAT,
    "longitude": AUGUSTA_LON,
    "daily": [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "windspeed_10m_max",
        "windgusts_10m_max",
        "weathercode",
        "precipitation_probability_max",
    ],
    "hourly": [
        "temperature_2m",
        "windspeed_10m",
        "precipitation_probability",
        "weathercode",
    ],
    "timezone": TIMEZONE,
    "forecast_days": 10,
}


def _is_cache_valid() -> bool:
    if not CACHE_FILE.exists():
        return False
    mtime = datetime.fromtimestamp(CACHE_FILE.stat().st_mtime)
    age_hours = (datetime.now() - mtime).total_seconds() / 3600
    return age_hours < CACHE_TTL_HOURS


def _load_cache() -> dict:
    with open(CACHE_FILE) as f:
        return json.load(f)


def _save_cache(data: dict):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f)


def fetch_forecast(use_cache: bool = True) -> dict:
    """Fetch 10-day daily + hourly forecast for Augusta National."""
    if use_cache and _is_cache_valid():
        return _load_cache()

    resp = requests.get(BASE_URL, params=PARAMS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    _save_cache(data)
    return data


def get_round_weather(round_number: int, use_cache: bool = True) -> dict:
    """
    Return weather summary for a given tournament round (1-4).
    Returns dict with: date, max_temp_f, min_temp_f, wind_mph, gusts_mph,
                       precip_inches, precip_probability, condition, condition_code,
                       scoring_adjustment, condition_label
    """
    target_date = TOURNAMENT_ROUNDS.get(round_number)
    if not target_date:
        raise ValueError(f"Invalid round number: {round_number}. Must be 1-4.")

    data = fetch_forecast(use_cache=use_cache)
    daily = data.get("daily", {})
    dates = daily.get("time", [])

    if target_date not in dates:
        return {"error": f"No forecast data available for {target_date}"}

    idx = dates.index(target_date)

    max_temp_c = daily["temperature_2m_max"][idx]
    min_temp_c = daily["temperature_2m_min"][idx]
    wind_kmh = daily["windspeed_10m_max"][idx]
    gusts_kmh = daily.get("windgusts_10m_max", [None] * len(dates))[idx]
    precip_mm = daily["precipitation_sum"][idx]
    precip_prob = daily.get("precipitation_probability_max", [0] * len(dates))[idx]
    code = daily["weathercode"][idx]

    # Convert units
    max_temp_f = round(max_temp_c * 9 / 5 + 32, 1) if max_temp_c is not None else None
    min_temp_f = round(min_temp_c * 9 / 5 + 32, 1) if min_temp_c is not None else None
    wind_mph = round(wind_kmh * 0.621371, 1) if wind_kmh is not None else 0
    gusts_mph = round(gusts_kmh * 0.621371, 1) if gusts_kmh is not None else 0
    precip_inches = round(precip_mm * 0.0393701, 2) if precip_mm is not None else 0

    scoring_adj, condition_label = _scoring_adjustment(wind_mph, precip_inches, min_temp_f)

    return {
        "round": round_number,
        "date": target_date,
        "max_temp_f": max_temp_f,
        "min_temp_f": min_temp_f,
        "wind_mph": wind_mph,
        "gusts_mph": gusts_mph,
        "precip_inches": precip_inches,
        "precip_probability": precip_prob,
        "condition_code": code,
        "condition_label": condition_label,
        "scoring_adjustment": scoring_adj,
    }


def get_all_rounds_weather(use_cache: bool = True) -> dict:
    """Return weather dict keyed by round number (1-4)."""
    return {r: get_round_weather(r, use_cache=use_cache) for r in range(1, 5)}


def _scoring_adjustment(wind_mph: float, precip_inches: float, min_temp_f: float) -> tuple[float, str]:
    """
    Estimate field scoring adjustment (strokes vs. expected) based on conditions.
    Returns (adjustment_strokes, label) where positive = higher scores / harder day.

    Based on Augusta research:
    - Wind >20mph: +1.5 to +2.5 strokes
    - Rain/soft: -0.5 to -1.5 strokes (greens receptive, scoring goes down)
    - Cold <50°F: slight additional difficulty
    """
    adj = 0.0
    labels = []

    # Wind adjustment
    if wind_mph >= 25:
        adj += 2.5
        labels.append(f"Very windy ({wind_mph} mph)")
    elif wind_mph >= 20:
        adj += 1.75
        labels.append(f"Windy ({wind_mph} mph)")
    elif wind_mph >= 15:
        adj += 0.75
        labels.append(f"Breezy ({wind_mph} mph)")
    else:
        labels.append(f"Calm ({wind_mph} mph)")

    # Rain adjustment (soft greens lower scores, but rain causes discomfort)
    if precip_inches >= 0.25:
        adj -= 1.0
        labels.append("Heavy rain (soft greens)")
    elif precip_inches >= 0.1:
        adj -= 0.5
        labels.append("Light rain (soft greens)")

    # Cold adjustment
    if min_temp_f is not None and min_temp_f < 45:
        adj += 0.5
        labels.append(f"Cold ({min_temp_f}°F low)")
    elif min_temp_f is not None and min_temp_f < 50:
        adj += 0.25
        labels.append(f"Cool ({min_temp_f}°F low)")

    label = " | ".join(labels) if labels else "Normal conditions"
    return round(adj, 2), label


def get_weather_player_adjustments(wind_mph: float, precip_inches: float, min_temp_f: float) -> dict:
    """
    Return per-player-type adjustments based on conditions.
    Used by matchup predictor and live model.
    Returns multipliers/addends for model categories.
    """
    adj = {
        "approach_weight_boost": 0.0,
        "arg_weight_boost": 0.0,
        "putting_weight_boost": 0.0,
        "experience_weight_boost": 0.0,
        "distance_penalty": 0.0,
    }

    if wind_mph >= 20:
        adj["arg_weight_boost"] = 0.05       # miss management premium
        adj["experience_weight_boost"] = 0.05  # course knowledge matters more
        adj["distance_penalty"] = 0.03        # power matters less in wind

    if precip_inches >= 0.1:
        adj["approach_weight_boost"] = 0.04   # high-spin approach players gain
        adj["putting_weight_boost"] = -0.02   # slower greens reduce putting variance

    if min_temp_f is not None and min_temp_f < 50:
        adj["distance_penalty"] = max(adj["distance_penalty"], 0.02)

    return adj


if __name__ == "__main__":
    print("Fetching Augusta weather forecast...\n")
    for rnd in range(1, 5):
        w = get_round_weather(rnd)
        print(f"Round {rnd} ({w.get('date')}):")
        print(f"  Temp: {w.get('min_temp_f')}–{w.get('max_temp_f')}°F")
        print(f"  Wind: {w.get('wind_mph')} mph (gusts {w.get('gusts_mph')} mph)")
        print(f"  Rain: {w.get('precip_inches')}\" ({w.get('precip_probability')}% chance)")
        print(f"  Conditions: {w.get('condition_label')}")
        print(f"  Scoring adjustment: {w.get('scoring_adjustment'):+.2f} strokes\n")
