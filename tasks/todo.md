# Masters 2026 Model — Task Tracker

## Wave 1 — Foundation
- [x] Research data sources, model design, agent tiers
- [x] Save research to memory files
- [x] Approve project plan
- [x] Create directory structure
- [x] CLAUDE.md
- [ ] STATE.md ← in progress
- [ ] requirements.txt ← in progress
- [ ] .streamlit/config.toml ← in progress
- [ ] tasks/todo.md + tasks/lessons.md ← in progress
- [ ] src/data_fetchers/weather.py ← in progress
- [ ] src/data_fetchers/datagolf.py ← in progress
- [ ] data/field_2026.csv (91 players) ← in progress

## Wave 2 — Data Layer
- [ ] src/data_fetchers/leaderboard.py (ESPN live scraper, 5-min TTL)
- [ ] src/data_fetchers/odds.py (Polymarket CLOB + Kalshi)
- [ ] src/data_fetchers/hole_stats.py (per-player per-hole historical data)
- [ ] data/augusta_sg_2021_2025.csv (historical SG averages by player)
- [ ] data/hole_by_hole_historical.csv (scoring avg per player per hole)
- [ ] src/model/scoring_model.py (pre-tournament composite)

## Wave 3 — Live Model + Features
- [ ] src/model/live_model.py (round-by-round blend, in-round regression, day + total projections)
- [ ] src/model/matchup.py (Monte Carlo, 2-3 players, weather-adjusted)
- [ ] src/model/best_bets.py (edge calc, Kelly sizing, confidence tiers)

## Wave 4 — UI
- [ ] app.py (5-tab Streamlit shell, 5-min auto-refresh)
- [ ] src/ui/leaderboard_tab.py (live scores + projected day/total)
- [ ] src/ui/predictions_tab.py (power rankings pre + live-adjusted)
- [ ] src/ui/best_bets_tab.py (ranked bets, edge %, confidence, Kelly size)
- [ ] src/ui/matchup_tab.py (player selector, round selector, prediction output)
- [ ] src/ui/hole_analysis_tab.py (per-hole historical scoring vs. field avg)

## Wave 5 — Deploy + Test
- [ ] Deploy to Streamlit Cloud
- [ ] Smoke test all features (April 8 evening)
- [ ] Live test with R1 data (April 9 afternoon)
- [ ] Bankroll update logic from payouts
