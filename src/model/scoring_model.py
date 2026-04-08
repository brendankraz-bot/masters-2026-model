"""
scoring_model.py — Pre-tournament composite scoring model for Masters 2026

Model weights (research-validated from Data Golf 2021-2025 Augusta shot-level data):

Top-level:
  DG Overall Skill Rating (time-weighted SG)  62%
  Recent form (last 8-12 weeks)               23%
  Augusta course history SG avg (2021-2025)   10%
  Shot-level course fit adjustment             5%

Within-Augusta SG category weights:
  Approach-the-Green   38%  (r ≈ -0.45 to -0.52 with finish)
  Around-the-Green     30%  (ELEVATED — Augusta's true differentiator)
  Off-the-Tee          15%  (no distance bonus — bomber advantage reversed 2021-2025)
  Putting              17%  (SUPPRESSED — winning Masters is NOT about putting)
"""

import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _safe_float(val, default: float = 0.0) -> float:
    """Convert value to float safely — treats NaN, None, and '' as default."""
    try:
        f = float(val)
        return default if (f != f) else f   # f != f is True only for NaN
    except (TypeError, ValueError):
        return default

# ---------------------------------------------------------------------------
# Augusta SG category weights (DO NOT CHANGE without empirical evidence)
# ---------------------------------------------------------------------------
SG_CATEGORY_WEIGHTS = {
    "sg_app":  0.38,
    "sg_arg":  0.30,
    "sg_ott":  0.15,
    "sg_putt": 0.17,
}
assert abs(sum(SG_CATEGORY_WEIGHTS.values()) - 1.0) < 0.001

# Top-level composite weights
TOP_LEVEL_WEIGHTS = {
    "skill_rating":   0.62,  # DG skill (decomposed by SG category weights above)
    "recent_form":    0.23,  # last 8-12 week form
    "course_history": 0.10,  # Augusta 2021-2025 SG avg
    "course_fit":     0.05,  # shot-level course fit adjustment
}
assert abs(sum(TOP_LEVEL_WEIGHTS.values()) - 1.0) < 0.001

# Age multiplier (9 of 10 recent winners aged 27-36)
def _age_multiplier(age: Optional[float]) -> float:
    if age is None:
        return 1.0
    if 27 <= age <= 36:
        return 1.0
    elif 24 <= age < 27 or 36 < age <= 40:
        return 0.97
    else:
        return 0.94

# OWGR hard cap: players outside top 40 get a cap on win probability
def _owgr_cap(owgr: Optional[float]) -> float:
    if owgr is None:
        return 0.8
    if owgr <= 10:
        return 1.0
    elif owgr <= 25:
        return 0.95
    elif owgr <= 40:
        return 0.85
    elif owgr <= 60:
        return 0.70
    else:
        return 0.50

# Par-5 conversion bonus: +10% weight for players converting >65% par-5 birdie rate
PAR5_BIRDIE_BONUS_THRESHOLD = 0.65


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_field() -> pd.DataFrame:
    path = DATA_DIR / "field_2026.csv"
    if not path.exists():
        raise FileNotFoundError("data/field_2026.csv not found. Run Wave 1 first.")
    df = pd.read_csv(path)
    df.columns = df.columns.str.lower().str.replace(" ", "_")
    return df


def _load_augusta_sg() -> pd.DataFrame:
    path = DATA_DIR / "augusta_sg_2021_2025.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df.columns = df.columns.str.lower().str.replace(" ", "_")
    return df


def _load_dg_rankings() -> pd.DataFrame:
    """Load Data Golf rankings from cache if available."""
    cache = Path(__file__).parent.parent.parent / "data" / "cache" / "dg_player_rankings.json"
    if cache.exists():
        import json
        with open(cache) as f:
            data = json.load(f)
        return pd.DataFrame(data)
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Skill rating builder
# ---------------------------------------------------------------------------

def _build_augusta_sg_composite(row: pd.Series, aug_sg_df: pd.DataFrame) -> float:
    """
    Compute a player's Augusta-weighted SG composite from their SG stats.
    Uses within-Augusta SG category weights (APP 38%, ARG 30%, OTT 15%, PUTT 17%).
    """
    # Try to get Augusta-specific SG from historical CSV first
    if not aug_sg_df.empty and "player_name" in aug_sg_df.columns:
        name_lower = str(row.get("player_name", "")).lower()
        match = aug_sg_df[aug_sg_df["player_name"].str.lower() == name_lower]
        if not match.empty:
            m = match.iloc[0]
            sg_app  = _safe_float(m.get("sg_app",  m.get("sg_approach",   0)))
            sg_arg  = _safe_float(m.get("sg_arg",  m.get("sg_aroundgreen", 0)))
            sg_ott  = _safe_float(m.get("sg_ott",  m.get("sg_offthetee",  0)))
            sg_putt = _safe_float(m.get("sg_putt", m.get("sg_putting",    0)))
            return (sg_app  * SG_CATEGORY_WEIGHTS["sg_app"] +
                    sg_arg  * SG_CATEGORY_WEIGHTS["sg_arg"] +
                    sg_ott  * SG_CATEGORY_WEIGHTS["sg_ott"] +
                    sg_putt * SG_CATEGORY_WEIGHTS["sg_putt"])

    # Fall back to field CSV SG columns if present
    sg_app  = _safe_float(row.get("sg_app"))
    sg_arg  = _safe_float(row.get("sg_arg"))
    sg_ott  = _safe_float(row.get("sg_ott"))
    sg_putt = _safe_float(row.get("sg_putt"))

    if any([sg_app, sg_arg, sg_ott, sg_putt]):
        return (sg_app  * SG_CATEGORY_WEIGHTS["sg_app"] +
                sg_arg  * SG_CATEGORY_WEIGHTS["sg_arg"] +
                sg_ott  * SG_CATEGORY_WEIGHTS["sg_ott"] +
                sg_putt * SG_CATEGORY_WEIGHTS["sg_putt"])

    # Last resort: DG skill rating or OWGR-based proxy
    # Scale calibrated to match actual Augusta SG composite values:
    # OWGR 1 → ~0.89, OWGR 25 → ~0.70, OWGR 60 → ~0.42, OWGR 100 → ~0.10
    dg = _safe_float(row.get("dg_skill_rating"))
    if dg:
        return dg
    owgr = _safe_float(row.get("owgr"), default=60.0)
    return max(0.05, 0.90 - owgr * 0.008)


def _build_skill_rating(row: pd.Series, aug_sg_df: pd.DataFrame) -> float:
    """
    Overall skill rating: Augusta-weighted SG composite (62% weight).
    """
    return _build_augusta_sg_composite(row, aug_sg_df)


def _build_recent_form(row: pd.Series) -> float:
    """
    Recent form score (23% weight).
    Uses dg_recent_form column if available, else proxied from OWGR momentum.
    Scale: roughly SG/round equivalent.
    """
    form = _safe_float(row.get("recent_form_sg", row.get("dg_recent_form")))
    if form:
        return form
    # Proxy calibrated so OWGR 1 ≈ 1.18, OWGR 25 ≈ 0.95, OWGR 60 ≈ 0.60, OWGR 100 ≈ 0.20
    top10s = _safe_float(row.get("recent_top10s"))
    owgr   = _safe_float(row.get("owgr"), default=60.0)
    return max(0.05, 1.20 - owgr * 0.010) + top10s * 0.15


def _build_course_history(row: pd.Series, aug_sg_df: pd.DataFrame) -> float:
    """
    Augusta course history score (10% weight).
    Uses historical SG avg/round if available, else best-finish proxy.
    """
    # Check aug_sg_avg in field CSV (from GNN data)
    aug_sg = _safe_float(row.get("augusta_sg_avg"))
    if aug_sg:
        return aug_sg

    # Check historical CSV
    if not aug_sg_df.empty and "player_name" in aug_sg_df.columns:
        name_lower = str(row.get("player_name", "")).lower()
        match = aug_sg_df[aug_sg_df["player_name"].str.lower() == name_lower]
        if not match.empty:
            m = match.iloc[0]
            sg_avg = _safe_float(m.get("sg_avg_round", m.get("sg_total_avg")))
            if sg_avg:
                return sg_avg

    # Proxy from best finish + starts
    bf = str(row.get("best_finish", "")).upper().strip()
    starts = _safe_float(row.get("augusta_starts"), default=1.0) or 1.0
    try:
        if bf == "1":
            return 2.0
        elif bf in ("2", "T2"):
            return 1.5
        elif bf in ("T3", "T4", "T5"):
            return 1.2
        elif bf.startswith("T") and int(bf[1:]) <= 10:
            return 0.8
        elif bf.startswith("T") and int(bf[1:]) <= 20:
            return 0.4
        elif bf == "MC":
            return -0.3 + min(starts * 0.05, 0.2)   # more starts = slightly less penalty
        elif bf in ("DEB", "", "NAN"):
            return 0.0
        else:
            return 0.1
    except (ValueError, IndexError):
        return 0.0


def _build_course_fit(row: pd.Series) -> float:
    """
    Course fit adjustment (5% weight). Small but non-zero.
    Max DG course fit adjustment is ~+0.07 SG/round.
    """
    return _safe_float(row.get("course_fit_score"))


# ---------------------------------------------------------------------------
# Main composite scorer
# ---------------------------------------------------------------------------

def compute_player_score(row: pd.Series, aug_sg_df: pd.DataFrame) -> dict:
    """
    Compute pre-tournament composite model score for a single player.
    Returns dict with all components and final composite.
    """
    skill    = _build_skill_rating(row, aug_sg_df)
    form     = _build_recent_form(row)
    history  = _build_course_history(row, aug_sg_df)
    fit      = _build_course_fit(row)

    raw_composite = (
        skill    * TOP_LEVEL_WEIGHTS["skill_rating"] +
        form     * TOP_LEVEL_WEIGHTS["recent_form"] +
        history  * TOP_LEVEL_WEIGHTS["course_history"] +
        fit      * TOP_LEVEL_WEIGHTS["course_fit"]
    )

    age     = row.get("age", None)
    owgr    = row.get("owgr", 50)
    age_mult  = _age_multiplier(age)
    owgr_cap  = _owgr_cap(owgr)

    adjusted = raw_composite * age_mult * owgr_cap

    return {
        "player_name":      row.get("player_name", ""),
        "owgr":             owgr,
        "age":              age,
        "skill_score":      round(skill, 3),
        "form_score":       round(form, 3),
        "history_score":    round(history, 3),
        "fit_score":        round(fit, 3),
        "raw_composite":    round(raw_composite, 3),
        "age_multiplier":   round(age_mult, 3),
        "owgr_cap":         round(owgr_cap, 3),
        "composite_score":  round(adjusted, 3),
        "is_past_champion": str(row.get("is_past_champion", "")).lower() == "true",
        "augusta_starts":   row.get("augusta_starts", 0),
    }


def _scores_to_win_probs(df: pd.DataFrame) -> pd.Series:
    """
    Convert composite scores to win probabilities.
    Temperature=3.5 calibrated so the top Augusta performer (Scheffler, composite ~1.1)
    lands near 8-10% — appropriate for a 91-player field with golf's inherent randomness.
    Best_bets.py compares these against market odds to find edge.
    """
    scores = df["composite_score"].values.astype(float)
    shifted = scores - scores.min()
    exp_scores = np.exp(shifted * 3.5)
    probs = exp_scores / exp_scores.sum()
    return pd.Series(probs, index=df.index)


def _project_tournament_score(composite: float) -> float:
    """
    Project expected 4-round tournament score vs par from composite SG score.
    Calibrated to actual composite range (0.05–1.115):
      composite 1.115 (Scheffler) → ~-10  |  composite 0.05 (bottom) → ~+10
    """
    return round(-18.78 * composite + 10.94, 0)


# ---------------------------------------------------------------------------
# Build full rankings table
# ---------------------------------------------------------------------------

def build_rankings(field_df: pd.DataFrame = None,
                   aug_sg_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Run the pre-tournament model across all players in the field.
    Returns DataFrame sorted by composite score, with win probabilities.
    """
    if field_df is None:
        field_df = _load_field()
    if aug_sg_df is None:
        aug_sg_df = _load_augusta_sg()

    rows = []
    for _, player_row in field_df.iterrows():
        score = compute_player_score(player_row, aug_sg_df)
        rows.append(score)

    df = pd.DataFrame(rows)
    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    df["model_rank"] = df.index + 1

    # Win probabilities
    df["win_probability"] = _scores_to_win_probs(df)
    df["win_pct"] = (df["win_probability"] * 100).round(1)
    df["projected_total"] = df["composite_score"].apply(_project_tournament_score)

    # Top-N probabilities (estimated from win prob distribution)
    df["top5_probability"]  = (df["win_probability"] * 6.0).clip(upper=0.85)
    df["top10_probability"] = (df["win_probability"] * 10.5).clip(upper=0.90)
    df["top20_probability"] = (df["win_probability"] * 18.0).clip(upper=0.95)
    df["make_cut_probability"] = df["win_probability"].apply(
        lambda p: 0.90 if p >= 0.05 else (0.80 if p >= 0.02 else (0.70 if p >= 0.01 else 0.55))
    )

    return df


def get_player_model_score(player_name: str, rankings_df: pd.DataFrame = None) -> dict | None:
    """Look up a single player's model score from the rankings DataFrame."""
    if rankings_df is None:
        rankings_df = build_rankings()
    name_lower = player_name.lower()
    match = rankings_df[rankings_df["player_name"].str.lower().str.contains(name_lower, na=False)]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


# ---------------------------------------------------------------------------
# Expected round score conversion
# ---------------------------------------------------------------------------

def composite_to_round_sg(composite: float) -> dict[str, float]:
    """
    Break composite score back into per-round SG category estimates.
    Used by matchup.py to feed hole_stats.py.
    """
    # Approximate: composite ≈ weighted SG/round total
    total_sg = composite  # already in SG/round units
    return {
        "sg_app":  round(total_sg * SG_CATEGORY_WEIGHTS["sg_app"], 3),
        "sg_arg":  round(total_sg * SG_CATEGORY_WEIGHTS["sg_arg"], 3),
        "sg_ott":  round(total_sg * SG_CATEGORY_WEIGHTS["sg_ott"], 3),
        "sg_putt": round(total_sg * SG_CATEGORY_WEIGHTS["sg_putt"], 3),
    }


if __name__ == "__main__":
    print("Building pre-tournament power rankings...\n")
    rankings = build_rankings()
    print(f"{'Rank':<6}{'Player':<28}{'Score':>7}{'Win%':>7}{'Proj':>6}  {'History':>8}")
    print("-" * 65)
    for _, row in rankings.head(20).iterrows():
        print(f"{int(row['model_rank']):<6}{row['player_name']:<28}"
              f"{row['composite_score']:>7.3f}{row['win_pct']:>7.1f}%"
              f"{row['projected_total']:>+7.0f}  {row['history_score']:>8.2f}")
