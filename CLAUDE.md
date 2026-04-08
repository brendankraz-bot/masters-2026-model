# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Owner:** Professional Golf Analyst & Sports Bettor
**Last updated:** 2026-04-07
**Project:** Masters 2026 Live Prediction Model — Python + Streamlit

Read `STATE.md` at session start. Task progress lives in `tasks/todo.md`. Lessons/corrections in `tasks/lessons.md`.

---

## Commands

```bash
# Run the app locally
streamlit run app.py

# Install dependencies
pip install -r requirements.txt

# Test a single module
python -m src.data_fetchers.weather
python -m src.data_fetchers.datagolf
python -m src.model.scoring_model
```

---

## Tournament Facts

- **Dates:** R1 Thursday April 9 → R4 Sunday April 12, 2026
- **Field:** 91 players (18 past champions, 22 first-timers, 6 amateurs)
- **Course:** Augusta National, Par 72, 7,565 yards, Augusta GA
- **Weather coords:** lat=33.5021, lon=-82.0232 (use America/New_York timezone)

---

## Data Sources

| Source | Purpose | Auth | Endpoint |
|--------|---------|------|----------|
| Open-Meteo | Weather forecast | None | `https://api.open-meteo.com/v1/forecast` |
| Polymarket | Prediction market odds | None | `https://clob.polymarket.com/markets` |
| Kalshi | Regulated prediction market | None | Public markets |
| ESPN | Live leaderboard scores | None | Scrapeable (see leaderboard.py) |
| Data Golf | Augusta SG data, course fit, field list | Free tier | `datagolf.com/api-access` |
| DraftKings | Sportsbook odds | None / OpticOdds | `sportsbook.draftkings.com/leagues/golf/us-masters` |

**Data wall:** Augusta National does NOT participate in ShotLink. All Augusta SG data is from Data Golf (2021 onward only). No public Augusta SG before 2021 exists.

---

## Critical Augusta Model Insights (Data Golf 2021-2025)

These are counter-intuitive — do not override without strong evidence:

1. **Around-the-Green SG drives MORE scoring variance at Augusta than any typical Tour stop.** Masters champions' worst category is putting; best is ARG.
2. **Putting SG is SUPPRESSED.** Explains less variance than at any other major. Do NOT chase pure putters.
3. **Bomber advantage reversed since 2021.** Pre-2021: +0.2 SG/round for bombers. 2021-2025: -0.1 SG/round. Do not weight driving distance favorably.
4. **Hole 12 is a disqualifier.** No winner in 12 years made double-bogey or worse on 12.
5. **Par 5s (2, 8, 13, 15) are the scoring engine.** 9 of last 10 winners were under-par on par 5s for the week.
6. **Augusta plays 1.5 fewer shots from 100-150 yds and 0.8 more from 200+ vs. Tour avg.** Long iron > wedge proficiency.

---

## Scoring Model Design

### Pre-Tournament Composite Weights

| Component | Weight |
|-----------|--------|
| DG Overall Skill Rating (time-weighted SG) | 62% |
| Recent form (last 8-12 weeks SG + wins) | 23% |
| Augusta course history SG 2021-2025 avg | 10% |
| Shot-level course fit adjustment | 5% |

### Within-Augusta SG Category Weights

| Category | Weight | Notes |
|----------|--------|-------|
| Approach-the-Green | 38% | r≈-0.45 to -0.52 with finish |
| Around-the-Green | 30% | Elevated vs. Tour norms |
| Off-the-Tee | 15% | No distance bonus |
| Putting | 17% | Lower weight than intuition |

### Live Round-by-Round Blending

| Stage | Pre-Tournament | Actual SG |
|-------|---------------|-----------|
| Before R1 | 100% | 0% |
| After R1 | 67% | 33% |
| After R2 | 47% | 53% |
| After R3 | 22% | 78% |
| Mid-R4 (hole 9) | 10% | 90% |

### In-Round Score Projection

```
Projected_Round_Score =
  (actual_strokes_through_N - par_through_N)
  + expected_sg_remaining × regression_factor
  + field_conditions_adjustment
```

Regression to mean: hole 5=85%, hole 9=55%, hole 14=30%, hole 17=12%
Field conditions adj: field_avg_deviation × 0.6

Special flags:
- Hole 12 double-bogey → -15% confidence multiplier on round
- Par-5 under-conversion → -0.5 strokes per missed birdie opportunity

### Tournament Total

```
Total = completed_rounds_actual + SUM(projected_remaining_rounds)
```

---

## Weather Adjustments

- Wind >20mph: +1.5 to +2.5 to all round projections; boost experience/ARG weight by 5%
- Rain/soft: lower projections -0.5 to -1.5; approach players gain edge
- Cold <50°F: slight negative to driving distance effectiveness

---

## Best Bets Engine

- Edge = model_prob − market_implied_prob
- Minimum threshold: 5% edge to surface a bet
- Kelly: `f = (b × p − q) / b` — use half-Kelly
- Default bankroll: $500 (update live from payouts)
- Confidence tiers: High >15%, Medium 8-15%, Low 5-8%
- Markets: Outright, Top 5/10/20, Make Cut, Round Leader, H2H

---

## Matchup Predictor

Input: 2-3 players + round number → uses per-player Augusta hole-by-hole historical scoring distributions → applies weather adj → 1000-iteration Monte Carlo → outputs win probability + projected score to par.

---

## Agent Model Tier Strategy

| Task Type | Model |
|-----------|-------|
| Data fetching, caching, parsing, Monte Carlo, UI rendering, state I/O | `claude-haiku-4-5-20251001` |
| Best bets calculation, code writing/debugging, scoring model | `claude-sonnet-4-6` |
| Complex reasoning, model override decisions, anomaly handling | `claude-opus-4-6` |

---

## Working Style

- **Autonomous bug fixing** — diagnose and fix, no hand-holding
- **Wave-based parallel work** — launch all independent tasks in a wave simultaneously
- **Never mark complete without proving it works**
- **Plan before any task with 3+ steps or architectural decisions**
- **Atomic commits** — after each completed unit: `feat(module): description`
- **Update STATE.md** at session end or after major milestones
- **Log corrections** in `tasks/lessons.md` immediately after any fix

---

## File Layout

```
masters-model/
├── CLAUDE.md, STATE.md
├── app.py                      # Streamlit entry — 5 tabs, 5-min auto-refresh
├── requirements.txt
├── .streamlit/config.toml
├── data/
│   ├── field_2026.csv          # 91 players: name, OWGR, age, Augusta starts, odds, DG rating
│   ├── augusta_sg_2021_2025.csv
│   ├── hole_by_hole_historical.csv
│   └── cache/
├── src/
│   ├── data_fetchers/
│   │   ├── weather.py          # Open-Meteo wrapper
│   │   ├── datagolf.py         # DG API + scraper
│   │   ├── leaderboard.py      # ESPN live scraper (5-min TTL)
│   │   ├── odds.py             # Polymarket + Kalshi + DK
│   │   └── hole_stats.py       # Per-player per-hole historical data
│   ├── model/
│   │   ├── scoring_model.py    # Pre-tournament composite
│   │   ├── live_model.py       # Round-by-round blend + in-round projection
│   │   ├── matchup.py          # Monte Carlo matchup predictor
│   │   └── best_bets.py        # Edge calc + Kelly sizing
│   └── ui/
│       ├── leaderboard_tab.py
│       ├── predictions_tab.py
│       ├── best_bets_tab.py
│       ├── matchup_tab.py
│       └── hole_analysis_tab.py
└── tasks/
    ├── todo.md
    └── lessons.md
```
