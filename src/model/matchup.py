"""
matchup.py — 2-3 player head-to-head matchup predictor

Methodology:
  1. Pull each player's blended composite score from scoring_model / live_model
  2. Fetch weather for the selected round
  3. Apply weather adjustments to expected SG categories
  4. Use hole_stats.py to build per-hole expected score distributions
  5. Run 1000-iteration Monte Carlo simulation
  6. Output: win probability per player + projected score to par

Input: player names (2-3), round number (1-4)
Output: {player: {win_pct, projected_score, advantage_holes, ...}}
"""

import numpy as np
from typing import Optional

from src.model.scoring_model import (
    build_rankings, get_player_model_score, composite_to_round_sg, _safe_float
)
from src.data_fetchers.hole_stats import (
    get_player_round_distribution, HOLE_PARS, PAR5_HOLES, FIELD_HOLE_AVERAGES
)
from src.data_fetchers.weather import get_round_weather, get_weather_player_adjustments

MONTE_CARLO_ITERATIONS = 1000
TOURNAMENT_ROUNDS = {1: "2026-04-09", 2: "2026-04-10", 3: "2026-04-11", 4: "2026-04-12"}
AUGUSTA_PAR = 72


# ---------------------------------------------------------------------------
# Player setup
# ---------------------------------------------------------------------------

def _get_player_sg(player_name: str, rankings_df=None) -> dict:
    """
    Retrieve a player's SG breakdown from the model.
    Returns {sg_app, sg_arg, sg_ott, sg_putt, composite, name}.
    """
    score = get_player_model_score(player_name, rankings_df)
    if score is None:
        # Fallback: unknown player gets average field estimates
        return {
            "name": player_name,
            "composite": 0.30,
            "sg_app": 0.12, "sg_arg": 0.09, "sg_ott": 0.05, "sg_putt": 0.05,
            "found": False,
        }

    composite = _safe_float(score.get("composite_score"), 0.30)
    sg_breakdown = composite_to_round_sg(composite)
    return {
        "name": score["player_name"],
        "composite": composite,
        "sg_app":  sg_breakdown["sg_app"],
        "sg_arg":  sg_breakdown["sg_arg"],
        "sg_ott":  sg_breakdown["sg_ott"],
        "sg_putt": sg_breakdown["sg_putt"],
        "win_pct": _safe_float(score.get("win_pct")),
        "found": True,
    }


def _apply_weather_to_sg(sg: dict, weather_adj: dict) -> dict:
    """
    Apply weather adjustments to a player's SG breakdown.
    weather_adj: output of get_weather_player_adjustments().
    Returns modified sg dict.
    """
    sg = sg.copy()
    # ARG boost in wind (miss management more important)
    sg["sg_arg"] += sg["sg_arg"] * weather_adj.get("arg_weight_boost", 0)
    # Approach boost in rain
    sg["sg_app"] += sg["sg_app"] * weather_adj.get("approach_weight_boost", 0)
    # Putting dampened in rain (slower greens = less putting variance)
    sg["sg_putt"] += sg["sg_putt"] * weather_adj.get("putting_weight_boost", 0)
    # OTT penalty in wind/cold (distance less valuable)
    penalty = weather_adj.get("distance_penalty", 0)
    sg["sg_ott"] = max(sg["sg_ott"] - abs(sg["sg_ott"]) * penalty, sg["sg_ott"] * 0.7)
    return sg


# ---------------------------------------------------------------------------
# Monte Carlo engine
# ---------------------------------------------------------------------------

def _simulate_round(distribution: dict, weather_scoring_adj: float,
                    rng: np.random.Generator) -> float:
    """
    Simulate a single 18-hole round for one player.
    Returns score vs par for the round.
    distribution: output of hole_stats.get_player_round_distribution()
    """
    expected_vs_par = distribution["expected_total_vs_par"]
    std_dev         = distribution["std_dev"]

    # Draw from normal distribution centered on expected with player-specific std dev
    # Add weather scoring adjustment (shared difficulty for the day)
    raw = rng.normal(expected_vs_par, std_dev)

    # Apply field conditions shift — shared across all players in this matchup
    adjusted = raw + weather_scoring_adj

    return round(adjusted, 2)


def run_matchup(
    player_names: list[str],
    round_number: int,
    use_live_blended: bool = False,
    live_rankings_df=None,
    n_iterations: int = MONTE_CARLO_ITERATIONS,
    seed: Optional[int] = None,
) -> dict:
    """
    Run Monte Carlo matchup simulation for 2-3 players in a given round.

    Parameters:
    -----------
    player_names     : list of 2-3 player name strings
    round_number     : 1, 2, 3, or 4
    use_live_blended : if True, use live_model blended scores; else use pre-tournament
    live_rankings_df : live_model DataFrame (required if use_live_blended=True)
    n_iterations     : Monte Carlo iterations (default 1000)
    seed             : random seed for reproducibility (None = random)

    Returns dict:
    {
      "players": {name: {win_pct, proj_score, proj_score_display, sg_breakdown}},
      "round": int,
      "date": str,
      "weather": dict,
      "iterations": int,
      "ties": int,
      "winner": str | None,
      "confidence": str,   # "High" | "Medium" | "Low"
    }
    """
    if not 2 <= len(player_names) <= 3:
        raise ValueError("Matchup requires 2 or 3 players.")
    if round_number not in TOURNAMENT_ROUNDS:
        raise ValueError(f"Round must be 1-4, got {round_number}.")

    # --- Load base rankings ---
    base_rankings = None
    if not use_live_blended or live_rankings_df is None:
        base_rankings = build_rankings()

    # --- Fetch weather for selected round ---
    weather = get_round_weather(round_number)
    wind_mph    = _safe_float(weather.get("wind_mph"))
    precip_in   = _safe_float(weather.get("precip_inches"))
    min_temp_f  = weather.get("min_temp_f")
    scoring_adj = _safe_float(weather.get("scoring_adjustment"))
    weather_adj = get_weather_player_adjustments(wind_mph, precip_in, min_temp_f)

    # --- Build per-player distributions ---
    player_data = {}
    for name in player_names:
        if use_live_blended and live_rankings_df is not None:
            # Use blended composite from live model
            from src.model.live_model import get_player_live_projection
            proj = get_player_live_projection(name, live_rankings_df)
            if proj:
                composite = _safe_float(proj.get("blended_composite"), 0.30)
                sg_breakdown = composite_to_round_sg(composite)
                sg = {
                    "name": proj["player_name"],
                    "composite": composite,
                    "win_pct": _safe_float(proj.get("win_pct_pre")),
                    "found": True,
                    **sg_breakdown,
                }
            else:
                sg = _get_player_sg(name, base_rankings)
        else:
            sg = _get_player_sg(name, base_rankings)

        # Apply weather adjustments to SG categories
        sg = _apply_weather_to_sg(sg, weather_adj)

        # Build hole-by-hole distribution
        dist = get_player_round_distribution(
            name,
            sg_app=sg["sg_app"],
            sg_arg=sg["sg_arg"],
            sg_ott=sg["sg_ott"],
            sg_putt=sg["sg_putt"],
        )
        player_data[name] = {"sg": sg, "dist": dist}

    # --- Monte Carlo ---
    rng = np.random.default_rng(seed)
    wins = {name: 0 for name in player_names}
    simulated_scores = {name: [] for name in player_names}
    ties = 0

    for _ in range(n_iterations):
        round_scores = {
            name: _simulate_round(player_data[name]["dist"], scoring_adj, rng)
            for name in player_names
        }
        min_score = min(round_scores.values())
        leaders = [n for n, s in round_scores.items() if s == min_score]

        if len(leaders) > 1:
            ties += 1
            for leader in leaders:
                wins[leader] += 0.5 / len(leaders)
        else:
            wins[leaders[0]] += 1

        for name, score in round_scores.items():
            simulated_scores[name].append(score)

    # --- Aggregate results ---
    results = {}
    for name in player_names:
        sim_arr = np.array(simulated_scores[name])
        proj_mean = float(np.mean(sim_arr))
        proj_std  = float(np.std(sim_arr))
        win_pct   = wins[name] / n_iterations * 100

        results[name] = {
            "win_pct":             round(win_pct, 1),
            "proj_score_vs_par":   round(proj_mean, 1),
            "proj_score_display":  _vs_par_display(proj_mean),
            "proj_std_dev":        round(proj_std, 1),
            "proj_score_range":    (round(proj_mean - proj_std, 1), round(proj_mean + proj_std, 1)),
            "composite_score":     round(player_data[name]["sg"]["composite"], 3),
            "sg_app":              round(player_data[name]["sg"]["sg_app"], 3),
            "sg_arg":              round(player_data[name]["sg"]["sg_arg"], 3),
            "sg_ott":              round(player_data[name]["sg"]["sg_ott"], 3),
            "sg_putt":             round(player_data[name]["sg"]["sg_putt"], 3),
            "data_found":          player_data[name]["sg"].get("found", False),
        }

    # Determine winner and confidence
    sorted_players = sorted(results.items(), key=lambda x: x[1]["win_pct"], reverse=True)
    winner = sorted_players[0][0] if sorted_players else None
    top_pct = sorted_players[0][1]["win_pct"] if sorted_players else 0
    second_pct = sorted_players[1][1]["win_pct"] if len(sorted_players) > 1 else 0
    edge = top_pct - second_pct

    if edge >= 20:
        confidence = "High"
    elif edge >= 10:
        confidence = "Medium"
    else:
        confidence = "Low"

    return {
        "players":    results,
        "round":      round_number,
        "date":       TOURNAMENT_ROUNDS[round_number],
        "weather":    weather,
        "iterations": n_iterations,
        "ties":       ties,
        "winner":     winner,
        "confidence": confidence,
    }


def _vs_par_display(score_vs_par: float) -> str:
    """Format score vs par for display (E, -4, +2)."""
    if abs(score_vs_par) < 0.05:
        return "E"
    elif score_vs_par < 0:
        return f"{score_vs_par:.1f}"
    else:
        return f"+{score_vs_par:.1f}"


def format_matchup_result(result: dict) -> str:
    """Return a human-readable matchup summary string."""
    lines = []
    rnd = result["round"]
    date = result["date"]
    w = result["weather"]
    lines.append(f"\n{'='*55}")
    lines.append(f"  MATCHUP PREDICTION — Round {rnd} ({date})")
    lines.append(f"  Weather: {w.get('condition_label','N/A')} | "
                 f"Wind: {w.get('wind_mph',0)} mph | "
                 f"Temp: {w.get('min_temp_f','-')}–{w.get('max_temp_f','-')}°F")
    lines.append(f"  Conditions adj: {w.get('scoring_adjustment',0):+.2f} strokes")
    lines.append(f"{'='*55}")

    sorted_players = sorted(result["players"].items(),
                             key=lambda x: x[1]["win_pct"], reverse=True)
    for name, data in sorted_players:
        winner_tag = " ← PICK" if name == result["winner"] else ""
        lines.append(
            f"  {name:<26} {data['win_pct']:>5.1f}%  "
            f"Proj: {data['proj_score_display']:>5}{winner_tag}"
        )
        lines.append(
            f"  {'':26}  SG: App {data['sg_app']:+.2f} | "
            f"ARG {data['sg_arg']:+.2f} | OTT {data['sg_ott']:+.2f} | "
            f"Putt {data['sg_putt']:+.2f}"
        )

    lines.append(f"\n  Confidence: {result['confidence']}  |  "
                 f"Ties: {result['ties']}/{result['iterations']} sims")
    lines.append(f"{'='*55}\n")
    return "\n".join(lines)


if __name__ == "__main__":
    print("Running sample matchup: Scheffler vs McIlroy vs Aberg — Round 1\n")
    result = run_matchup(
        ["Scottie Scheffler", "Rory McIlroy", "Ludvig Aberg"],
        round_number=1,
        seed=42,
    )
    print(format_matchup_result(result))
