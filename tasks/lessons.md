# Lessons Learned / Corrections Log

_Add an entry immediately after any correction, bug fix, or non-obvious decision._

---

## Template
**Date:** YYYY-MM-DD
**Context:** What were you doing?
**Mistake / Finding:** What went wrong or what was discovered?
**Fix / Rule:** What is the rule going forward?

---

## 2026-04-08 (Wave 3)

**Context:** live_model.py pre-tournament round projection
**Mistake:** `range(completed + 2, total_rounds + 1)` skips round 1 when no round is in progress (completed=0). Only projects 3 of 4 rounds, causing wrong projected totals.
**Fix:** Branch on whether current round is active: `first_future = completed + 2 if current_round_projected else completed + 1`.

**Context:** live_model.py reading stale ESPN round score data
**Mistake:** ESPN API returns historical round linescores (from 2025) even when the tournament hasn't started. Ingesting them caused players like Scheffler to show 47%/53% live blend pre-tournament.
**Fix:** Gate round score ingestion on `current_round > 0` from the leaderboard metadata. Only slice `[:current_round]` rounds from ESPN linescores.

**Context:** live_model.py name matching
**Mistake:** Single last-name match had false positives (e.g., matching "Kirk" to wrong player). 
**Fix:** Require both last name AND first 3 chars of first name to match before falling back to last-name-only.

## 2026-04-08

**Context:** scoring_model.py composite score calculation
**Mistake:** Used `float(val or 0)` pattern to handle missing data. pandas NaN is truthy in Python, so `float(NaN or 0)` returns NaN instead of 0, silently propagating NaN through all calculations.
**Fix:** Added `_safe_float(val, default)` helper that uses `f != f` (IEEE NaN identity) to detect and replace NaN. Use `_safe_float()` for all pandas row access in model code.

**Context:** scoring_model.py OWGR proxy scale
**Mistake:** OWGR proxy formula `max(0.0, 3.0 - owgr * 0.05)` returned 2.95 for OWGR 1. Actual Augusta SG composite values for top players are 0.85–1.1 (not 3.0). This made un-SG-tracked players rank above Scheffler.
**Fix:** Recalibrated to `max(0.05, 0.90 - owgr * 0.008)` and `max(0.05, 1.20 - owgr * 0.010)` for form. Always verify proxy ranges against known-player actuals before using.

**Context:** scoring_model.py tournament projection formula
**Mistake:** `_project_tournament_score` was calibrated assuming composite scores up to 3.0, but actual composites max at 1.115. Scheffler projected +0 instead of -10.
**Fix:** Re-anchored: `projected = -18.78 * composite + 10.94` so composite 1.115 → -10, composite 0.05 → +10.

## 2026-04-07

**Context:** Initial model weight design
**Finding:** Conventional wisdom says Augusta rewards putting. Data Golf 2021-2025 shot-level data shows the opposite — putting SG explains LESS variance at Augusta than at any other major. Around-the-Green explains MORE. Masters winners' worst category is consistently putting.
**Rule:** SG:ARG weight = 30%, SG:Putting = 17%. Do not adjust upward for "great putters" without strong Augusta-specific evidence.

**Context:** Bomber/distance weighting
**Finding:** Pre-2021, bombers gained +0.2 SG/round at Augusta. Since 2021, bombers LOSE -0.1 SG/round. The reversal is driven by approach and putting underperformance by long hitters on specific holes (15, 5, 17, 11).
**Rule:** Do not add a distance bonus to player composite scores. Off-the-Tee weight stays at 15% with no distance multiplier.
