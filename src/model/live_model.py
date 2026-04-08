"""
live_model.py — Live round-by-round model blending and in-round score projection

Blending schedule (pre-tournament weight / actual SG weight):
  Before R1:        100% / 0%
  After R1:          67% / 33%
  After R2 (cut):    47% / 53%
  After R3:          22% / 78%
  Mid-R4 hole 9:     10% / 90%

In-round regression to mean by hole depth:
  Hole 5: 85%  |  Hole 9: 55%  |  Hole 14: 30%  |  Hole 17: 12%

Special flags:
  - Hole 12 double-bogey or worse → -15% confidence on projected round score
  - Par-5 under-conversion → -0.5 strokes per missed birdie opportunity
  - Field conditions adjustment: field_avg_deviation × 0.6
"""

import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

from src.model.scoring_model import build_rankings, _safe_float, _project_tournament_score
from src.data_fetchers.weather import get_round_weather, get_weather_player_adjustments

AUGUSTA_PAR = 72
HOLE_PARS = [4, 5, 4, 3, 4, 3, 4, 5, 4, 4, 4, 3, 5, 4, 5, 3, 4, 4]
PAR5_HOLES = {2, 8, 13, 15}   # 1-indexed
HOLE_12_IDX = 11               # 0-indexed

# Pre-tournament vs actual SG blending weights per completed round
BLEND_SCHEDULE = {
    0: (1.00, 0.00),   # before R1
    1: (0.67, 0.33),   # after R1
    2: (0.47, 0.53),   # after R2
    3: (0.22, 0.78),   # after R3
    4: (0.10, 0.90),   # R4 in progress / complete
}

# Regression-to-mean factor by hole number (1-indexed) during active round
REGRESSION_BY_HOLE = {
    1: 0.95, 2: 0.92, 3: 0.90, 4: 0.88, 5: 0.85,
    6: 0.80, 7: 0.75, 8: 0.70, 9: 0.55,
    10: 0.50, 11: 0.44, 12: 0.40, 13: 0.36, 14: 0.30,
    15: 0.24, 16: 0.18, 17: 0.12, 18: 0.05,
}

# Expected Augusta field scoring average per round (vs par)
# Used when actual field data unavailable
EXPECTED_FIELD_AVG_VS_PAR = 0.8   # field typically finishes ~+0.8 relative to scratch par


# ---------------------------------------------------------------------------
# Core blend
# ---------------------------------------------------------------------------

def get_blend_weights(completed_rounds: int, holes_complete_in_current: int = 0) -> tuple[float, float]:
    """
    Return (pre_tournament_weight, actual_weight) for the current tournament stage.
    completed_rounds: number of fully finished rounds (0-4).
    holes_complete_in_current: holes played in the active round (0 if between rounds).
    """
    if completed_rounds >= 4:
        return (0.05, 0.95)

    w_pre, w_actual = BLEND_SCHEDULE.get(completed_rounds, (1.0, 0.0))

    # Smooth mid-round transition: linearly interpolate toward next stage
    if holes_complete_in_current > 0 and completed_rounds < 4:
        next_pre, next_actual = BLEND_SCHEDULE.get(completed_rounds + 1, (0.05, 0.95))
        frac = holes_complete_in_current / 18.0
        w_pre    = w_pre    + (next_pre    - w_pre)    * frac
        w_actual = w_actual + (next_actual - w_actual) * frac

    return round(w_pre, 3), round(w_actual, 3)


def blend_player_score(pre_composite: float, actual_sg_rounds: list[float],
                       completed_rounds: int, holes_in_current: int = 0) -> float:
    """
    Blend pre-tournament composite with actual tournament SG performance.
    actual_sg_rounds: list of per-round SG totals (vs field avg) for completed rounds.
    Returns blended composite score (same scale as scoring_model.py output).
    """
    w_pre, w_actual = get_blend_weights(completed_rounds, holes_in_current)

    if not actual_sg_rounds or w_actual == 0:
        return pre_composite

    actual_avg = sum(actual_sg_rounds) / len(actual_sg_rounds)
    return round(w_pre * pre_composite + w_actual * actual_avg, 4)


# ---------------------------------------------------------------------------
# In-round score projection
# ---------------------------------------------------------------------------

def _regression_factor(hole: int) -> float:
    """Return regression-to-mean factor for a given hole (1-indexed)."""
    return REGRESSION_BY_HOLE.get(max(1, min(hole, 18)), 0.05)


def _par_through_hole(hole: int) -> int:
    """Cumulative par through hole N (1-indexed)."""
    return sum(HOLE_PARS[:hole])


def project_round_score(
    actual_strokes_through_n: int,
    hole_n: int,
    player_expected_sg_per_round: float,
    field_avg_vs_expected: float = 0.0,
    hole_scores: Optional[list[Optional[int]]] = None,
) -> dict:
    """
    Project a player's finishing round score (vs par) given current score through hole N.

    Parameters:
    -----------
    actual_strokes_through_n : total strokes played through hole N
    hole_n                   : last completed hole (1-indexed)
    player_expected_sg_per_round : player's expected SG per round from blended model
                                   (positive = better than field)
    field_avg_vs_expected    : how the field is scoring vs. expected today
                               (positive = harder day, negative = easier)
    hole_scores              : optional list of 18 per-hole scores vs par (None = not played)

    Returns dict with: projected_total_vs_par, score_through_n_vs_par,
                       projected_remaining, regression_factor, flags
    """
    if hole_n <= 0:
        # No holes played — return pre-round projection
        return {
            "projected_total_vs_par": round(-player_expected_sg_per_round * 4, 1),
            "score_through_n_vs_par": None,
            "projected_remaining": round(-player_expected_sg_per_round * 4, 1),
            "regression_factor": 1.0,
            "flags": [],
            "confidence": 1.0,
        }

    par_through = _par_through_hole(hole_n)
    score_vs_par = actual_strokes_through_n - par_through

    # Remaining holes expected score
    holes_remaining = 18 - hole_n
    expected_sg_remaining = player_expected_sg_per_round * (holes_remaining / 18.0)

    # Apply regression to mean
    reg = _regression_factor(hole_n)
    # score_vs_par is partly luck — regress back toward expected
    regressed_current = score_vs_par * (1 - reg) + (-player_expected_sg_per_round * hole_n / 18.0) * reg

    # Field conditions adjustment (shared difficulty/ease)
    conditions_adj = field_avg_vs_expected * 0.6 * (holes_remaining / 18.0)

    projected_total = regressed_current + (-expected_sg_remaining) + conditions_adj

    # --- Special flags ---
    flags = []
    confidence = 1.0

    if hole_scores:
        # Hole 12 disqualifier check (0-indexed = index 11)
        h12_score = hole_scores[HOLE_12_IDX]
        if h12_score is not None and h12_score >= 2:   # double-bogey or worse vs par
            flags.append("hole12_disaster")
            confidence *= 0.85

        # Par-5 conversion check (holes 2, 8, 13, 15 → 0-indexed 1, 7, 12, 14)
        par5_indices = {1: 2, 7: 8, 12: 13, 14: 15}   # 0-idx → hole number
        played_par5s = [(hole_scores[idx], hole_num)
                        for idx, hole_num in par5_indices.items()
                        if idx < hole_n and hole_scores[idx] is not None]
        for score_vs_par_h, hole_num in played_par5s:
            if score_vs_par_h >= 0:   # par or worse on a par 5 = missed birdie
                projected_total += 0.5
                flags.append(f"par5_miss_hole{hole_num}")

    return {
        "projected_total_vs_par": round(projected_total, 1),
        "score_through_n_vs_par": score_vs_par,
        "projected_remaining": round(-expected_sg_remaining + conditions_adj, 1),
        "regression_factor": round(reg, 2),
        "confidence": round(confidence, 2),
        "flags": flags,
    }


# ---------------------------------------------------------------------------
# Tournament total projection
# ---------------------------------------------------------------------------

def project_tournament_total(
    player_name: str,
    completed_round_scores: list[int],          # actual strokes per completed round
    current_round_projected_vs_par: Optional[float],  # in-round projection (vs par)
    blended_composite: float,
    weather_by_round: dict,                      # {round_num: weather_dict}
    total_rounds: int = 4,
) -> dict:
    """
    Project a player's final tournament total (vs par).

    completed_round_scores : list of actual round stroke totals (e.g. [70, 72])
    current_round_projected_vs_par : live projection for the round in progress (vs par)
    blended_composite : current blended model score for remaining-round projection
    weather_by_round : from weather.py get_all_rounds_weather()
    """
    completed = len(completed_round_scores)
    actual_vs_par = sum(s - AUGUSTA_PAR for s in completed_round_scores)

    # Determine which rounds still need projecting
    # If current round is in progress, it's already projected → start from completed+2
    # If no round in progress (between rounds or pre-tournament) → start from completed+1
    first_future = completed + 2 if current_round_projected_vs_par is not None else completed + 1

    future_projections = []
    for r in range(first_future, total_rounds + 1):
        w = weather_by_round.get(r, {})
        weather_adj = _safe_float(w.get("scoring_adjustment"))
        base_proj = _project_round_from_composite(blended_composite)
        future_projections.append(base_proj + weather_adj)

    current_proj = current_round_projected_vs_par if current_round_projected_vs_par is not None else 0.0
    total_projected_vs_par = actual_vs_par + current_proj + sum(future_projections)

    return {
        "player_name": player_name,
        "completed_rounds": completed,
        "actual_vs_par": actual_vs_par,
        "current_round_projected": current_round_projected_vs_par,
        "future_rounds_projected": round(sum(future_projections), 1),
        "total_projected_vs_par": round(total_projected_vs_par, 1),
        "blended_composite": blended_composite,
    }


def _project_round_from_composite(composite: float) -> float:
    """Project single-round score vs par from composite. Scheffler(1.1) → -2.5/round."""
    return round(-composite * 2.5, 1)


# ---------------------------------------------------------------------------
# Full live rankings update
# ---------------------------------------------------------------------------

def build_live_rankings(
    leaderboard_data: dict,
    pre_tournament_rankings: pd.DataFrame,
    weather_by_round: dict,
) -> pd.DataFrame:
    """
    Merge live leaderboard data with pre-tournament model to produce blended rankings.
    Returns DataFrame sorted by projected tournament total.

    leaderboard_data : output of leaderboard.get_leaderboard()
    pre_tournament_rankings : output of scoring_model.build_rankings()
    weather_by_round : output of weather.get_all_rounds_weather()
    """
    players_live = {
        p["player_name"].lower(): p
        for p in leaderboard_data.get("players", [])
    }
    current_round = leaderboard_data.get("current_round", 0)

    rows = []
    for _, pre_row in pre_tournament_rankings.iterrows():
        name = pre_row["player_name"]
        pre_composite = _safe_float(pre_row.get("composite_score"))

        # Match to live leaderboard — exact then last-name then first-token
        name_lower = name.lower()
        live = players_live.get(name_lower)
        if live is None:
            last = name_lower.split()[-1]
            first = name_lower.split()[0]
            for key, val in players_live.items():
                if last in key and first[:3] in key:   # last name + first 3 chars of first name
                    live = val
                    break
            if live is None:
                for key, val in players_live.items():
                    if last in key:
                        live = val
                        break

        # Completed rounds actual scores and SG estimates
        # Gate on current_round so we never ingest stale/historical ESPN data
        actual_round_scores = []
        actual_sg_rounds = []
        if live and current_round > 0:
            rd_scores = (live.get("round_scores", []) or [])[:current_round]
            for rd_score_str in rd_scores:
                try:
                    sg_est = -_safe_float(rd_score_str, 0.0)
                    actual_sg_rounds.append(sg_est)
                    actual_round_scores.append(AUGUSTA_PAR + int(_safe_float(rd_score_str, 0)))
                except (ValueError, TypeError):
                    pass

        holes_in_current = 0
        if live and live.get("thru") not in ("-", None, "0", 0):
            try:
                holes_in_current = int(str(live["thru"]).replace("F", "18"))
            except (ValueError, TypeError):
                holes_in_current = 0

        # Blend
        completed = len(actual_sg_rounds)
        blended = blend_player_score(pre_composite, actual_sg_rounds, completed, holes_in_current)

        # Current round in-round projection
        in_round_proj = None
        if live and holes_in_current > 0 and live.get("today_score") is not None:
            proj = project_round_score(
                actual_strokes_through_n=AUGUSTA_PAR + int(live["today_score"] or 0),
                hole_n=holes_in_current,
                player_expected_sg_per_round=blended * 2.5,
                field_avg_vs_expected=0.0,
            )
            in_round_proj = proj["projected_total_vs_par"]

        # Tournament total
        tournament = project_tournament_total(
            player_name=name,
            completed_round_scores=actual_round_scores,
            current_round_projected_vs_par=in_round_proj,
            blended_composite=blended,
            weather_by_round=weather_by_round,
        )

        rows.append({
            "player_name": name,
            "model_rank_pre": int(pre_row.get("model_rank", 0)),
            "pre_composite": pre_composite,
            "blended_composite": blended,
            "completed_rounds": completed,
            "actual_vs_par": tournament["actual_vs_par"],
            "today_proj_vs_par": in_round_proj,
            "tournament_proj_vs_par": tournament["total_projected_vs_par"],
            "win_pct_pre": _safe_float(pre_row.get("win_pct")),
            "is_active": live.get("is_active", True) if live else True,
            "position": live.get("position", "-") if live else "-",
            "today_display": live.get("today_display", "-") if live else "-",
            "total_display": live.get("total_display", "-") if live else "-",
            "thru": live.get("thru", "-") if live else "-",
            "w_pre": get_blend_weights(completed, holes_in_current)[0],
            "w_actual": get_blend_weights(completed, holes_in_current)[1],
        })

    df = pd.DataFrame(rows)
    df = df[df["is_active"]].copy()
    df = df.sort_values("tournament_proj_vs_par", ascending=True).reset_index(drop=True)
    df["live_rank"] = df.index + 1
    return df


# ---------------------------------------------------------------------------
# Convenience accessor
# ---------------------------------------------------------------------------

def get_player_live_projection(player_name: str, live_rankings: pd.DataFrame) -> dict | None:
    """Return a single player's live projection dict."""
    name_lower = player_name.lower()
    match = live_rankings[live_rankings["player_name"].str.lower().str.contains(name_lower, na=False)]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


if __name__ == "__main__":
    from src.data_fetchers.leaderboard import get_leaderboard
    from src.data_fetchers.weather import get_all_rounds_weather

    print("Building live rankings (pre-tournament stage)...\n")
    rankings = build_rankings()
    lb = get_leaderboard()
    weather = get_all_rounds_weather()

    live = build_live_rankings(lb, rankings, weather)
    print(f"{'Live Rank':<10}{'Player':<28}{'Proj Total':>10}  {'Blend':>6}")
    print("-" * 60)
    for _, row in live.head(15).iterrows():
        print(f"{int(row['live_rank']):<10}{row['player_name']:<28}"
              f"{row['tournament_proj_vs_par']:>+10.1f}  "
              f"{row['w_pre']:.0%}/{row['w_actual']:.0%}")
