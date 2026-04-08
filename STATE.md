# STATE.md — Session Handoff Document

_Update this file at the end of every session or after major milestones._

---

## Current Status

**Date:** 2026-04-08
**Phase:** Wave 4 — UI (next task)
**Tournament:** R1 Thursday April 9, 2026 — TOMORROW

---

## Completed Waves

### Wave 1 — Foundation ✅
- [x] Full directory structure created
- [x] CLAUDE.md (complete project context)
- [x] STATE.md, tasks/todo.md, tasks/lessons.md
- [x] requirements.txt (streamlit, requests, pandas, numpy, bs4, plotly, scipy, lxml)
- [x] .streamlit/config.toml (Masters green theme #006747, dark background)
- [x] src/__init__.py, src/data_fetchers/__init__.py, src/model/__init__.py, src/ui/__init__.py
- [x] src/data_fetchers/weather.py — Open-Meteo API, Augusta coords, scoring adjustments per round
- [x] src/data_fetchers/datagolf.py — DG API client, TTL cache, graceful CSV fallback
- [x] data/field_2026.csv — 88 players with name, country, OWGR, age, Augusta starts, best finish, odds, augusta_sg_avg

### Wave 2 — Data Layer ✅
- [x] src/data_fetchers/leaderboard.py — ESPN API scraper, 5-min TTL cache, pre/active/complete status
- [x] src/data_fetchers/odds.py — Polymarket CLOB API, Kalshi API, DraftKings manual table (25 players), consensus merge, Kelly utils
- [x] src/data_fetchers/hole_stats.py — All 18 hole metadata (par, yards, name, danger, amen corner flags), field avg scoring per hole, per-player round distribution builder
- [x] data/augusta_sg_2021_2025.csv — 52 players with SG category averages (sg_app, sg_arg, sg_ott, sg_putt, sg_avg_round)
- [x] src/model/scoring_model.py — Pre-tournament composite (skill 62% / form 23% / history 10% / fit 5%), augusta SG category weights (APP 38% / ARG 30% / OTT 15% / PUTT 17%), win probs, projected tournament total

**scoring_model output (verified):**
```
1  Scottie Scheffler   11.3%  proj -10
2  Ludvig Aberg         8.7%  proj  -9
3  Collin Morikawa      4.5%  proj  -5
4  Rory McIlroy         3.4%  proj  -4
5  Xander Schauffele    3.3%  proj  -3
6  Jon Rahm             3.1%  proj  -3
7  Hideki Matsuyama     2.7%  proj  -2
```

### Wave 3 — Live Model + Features ✅
- [x] src/model/live_model.py — round-by-round blend (R0:100/0 → R3:22/78 → R4:10/90), in-round regression by hole (hole 5=85% → hole 17=12%), day-score + tournament-total projection, hole 12 disqualifier flag, par-5 conversion tracking, weather adjustment
- [x] src/model/matchup.py — 2-3 player input, round selector, Monte Carlo 1000 iterations, weather-adjusted SG, per-hole distributions, win probability output + projected score + confidence tier
- [x] src/model/best_bets.py — edge calc (model_prob - market_implied_prob), 5% minimum threshold, half-Kelly sizing, $500 default bankroll, confidence tiers (High >15% / Medium 8-15% / Low 5-8%), all market types covered, bankroll allocation cap (80% max exposure)

**best_bets output (verified pre-tournament):**
```
Ludvig Aberg    Top 10   +28.9% 🔥 High   $69 bet  EV +$32.8
Ludvig Aberg    Top 5    +16.2% 🔥 High   $58 bet  EV +$26.2
Cameron Smith   Make Cut +15.0% 🔥 High   $69 bet  EV +$19.0
Jordan Spieth   Make Cut +10.0% ✅ Med    $69 bet  EV  +$9.9
Ludvig Aberg    R1 Lead   +8.3% ✅ Med    $23 bet  EV +$11.0
Total exposure: $400 / EV: +$108
```

**matchup output (verified — Scheffler vs McIlroy vs Aberg, R1):**
```
Scottie Scheffler  36.7%  Proj +1.6 ← PICK  (Low confidence — tight field)
Ludvig Aberg       34.9%  Proj +1.6
Rory McIlroy       28.2%  Proj +2.1
```

---

## Wave 4 — UI ✅

All 6 files complete and syntax-verified:

- [x] **W4.1** `app.py` — 5-tab shell, Masters green theme, auto-refresh meta tag on live days
- [x] **W4.2** `src/ui/leaderboard_tab.py` — live scores, weather banner, projected day/total, model blend display
- [x] **W4.3** `src/ui/predictions_tab.py` — power rankings, SG breakdown chart, model vs market edge
- [x] **W4.4** `src/ui/best_bets_tab.py` — ranked bets, adjustable bankroll/edge threshold, confidence tiers, EV
- [x] **W4.5** `src/ui/matchup_tab.py` — player multiselect, Monte Carlo results, win% donut + SG bar charts
- [x] **W4.6** `src/ui/hole_analysis_tab.py` — 18-hole bar chart, Amen Corner callout, par-5 engine callout, full table

Git repo initialized: 29 files committed (`feat: Masters 2026 live prediction model — full stack`).

## Next: Wave 5 — Deploy (DO THIS NOW — R1 is TOMORROW)

1. **Create GitHub repo:**
   ```bash
   # Option A: Install gh and use CLI
   brew install gh && gh auth login
   gh repo create masters-2026-model --public --push --source .
   
   # Option B: Manual — create repo at github.com, then:
   git remote add origin https://github.com/YOUR_USERNAME/masters-2026-model.git
   git push -u origin main
   ```

2. **Deploy to Streamlit Cloud:**
   - Go to share.streamlit.io → "New app"
   - Connect GitHub repo `masters-2026-model`
   - Main file: `app.py`
   - Python: 3.11
   - No secrets needed (all APIs are public / CSV fallback)
   - Click Deploy

3. **Optional — DG API key:**
   - If you have a Data Golf API key, add in Streamlit Cloud → Settings → Secrets:
     ```toml
     DATAGOLF_API_KEY = "your_key_here"
     ```

4. **Smoke test** the public URL before R1 tee-off (~8am ET April 9)

---

## Key Architectural Decisions (Do Not Override)

| Decision | Rationale |
|----------|-----------|
| SG:ARG weight = 30% | DG 2021-2025: ARG explains MORE variance at Augusta than any Tour stop |
| SG:Putting weight = 17% | Putting SUPPRESSED at Augusta — do not chase putters |
| No distance bonus on OTT | Bomber advantage reversed 2021-2025 (-0.1 SG/round) |
| Half-Kelly sizing | Safer bankroll management for $500 accounts |
| Softmax temperature = 3.5 | Calibrated so Scheffler ~11% win prob in 91-player field |
| Projection formula: -18.78×composite + 10.94 | Anchored: composite 1.115 → -10, composite 0.05 → +10 |
| Gate ESPN linescores on current_round > 0 | ESPN returns 2025 historical scores pre-tournament — must filter |

## Known Gaps / Blockers

1. **Data Golf API key not configured** — all DG endpoints fall back to CSV/public scraping. If you obtain a key, set `DATAGOLF_API_KEY` env var.
2. **DraftKings odds are manual** — `odds.py` has 25 players hardcoded. Update `DRAFTKINGS_MANUAL` dict in `odds.py` before launch if odds shift.
3. **hole_by_hole_historical.csv not populated** — `hole_stats.py` uses field averages as fallback. Will work correctly but per-player hole-level data would sharpen matchup predictions.
4. **field_2026.csv has ~88 players** — 3 amateurs and a few late additions may be missing. Add to CSV if needed.

## How to Run

```bash
cd "Masters 2026"
pip install -r requirements.txt
streamlit run app.py          # local dev
python -m src.data_fetchers.weather      # test weather API
python -m src.data_fetchers.leaderboard  # test ESPN scraper
python -m src.model.scoring_model        # test rankings
python -m src.model.matchup              # test Scheffler/McIlroy/Aberg R1
python -m src.model.best_bets            # test best bets engine
```
