# Rotation / injury minutes (research, not shipped)

Goal: predict a player's minutes/FPTS from teammates' absences; surface as an "Opportunity" indicator.
Code: `rotation_data.py` (pull + cache under gitignored `.horizon/rotation/`), `rotation_backtest.py` (walk-forward, 2025-26 train, 2026-27 test).

## Data sources (probed 2026-11-02)
- **NBA daily lineups JSON** `stats.nba.com/js/data/leaders/00_daily_lineups_YYYYMMDD.json` (browser UA + `Referer: https://www.nba.com/`): per game, every rostered player with `rosterStatus` Active/Inactive and `position` set only for the 5 starters. Same ids as `game_lines.player_id`. Works back to at least 2025-26, so it is the **pregame** history we lack elsewhere (`players.injury_status` is current-only). Missing day = 403/404 = no games.
- ESPN depth chart (`espn.com/nba/team/depth/_/name/<abbr>`, core API `.../seasons/2027/teams/{id}/depthcharts`): editorial, current only, goes stale (a Celtics PF starter was wrong). Tiebreak at most, not worth ingesting yet.
- ESPN injuries JSON `site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries` (curl with browser UA; WebFetch gets 403): current only, snapshot on a schedule if wanted. NBA injury-report PDFs (`ak-static.cms.nba.com/referee/injury/Injury-Report_YYYY-MM-DD_HH_MMPM.pdf`) are the only archived Probable/Questionable history.
- Skip Rotowire, Basketball-Reference, Cleaning the Glass (ToS forbid scraping).

## Backtest findings
- Baseline = mean of last 10 played games (+ last-season mpg prior). It **sums to 244-276 team minutes** (only counts games played), and **~1.7 Active players per game with baseline >= 5 min play 0** (DNP-CD). Those two are most of the minutes error (MAE 6.6 train / 9.2 test).
- Naively adding "freed minutes" of Inactive rotation players on top of the baseline made it WORSE (baseline already absorbs absences). Don't do that.
- What helps: normalize active players to 240 (alpha 0.75) **and tilt toward tonight's starters** (gamma 0.5): train new-absence MAE 6.61 -> 6.39, test 9.19 -> 8.55. Gain is the same in games with no new absence, so it is team-total + starter structure, **not an injury-specific effect yet**.
- Position-group tilt toward the absent player's group (beta): no gain at any strength. Position-blind is as good with this data.
- 2026-27 has only 94 new-absence team-games; cannot prove an effect there. 2025-26 (2,476 team-games) is the training set.

## Round 2 (2026-11-02)
- **Play probability** (logistic on baseline, starter, DNP rate over last 6 Active games, minutes freed, Active count): AUC 0.87 train / 0.77 test. Starter (+3.3) and recent-DNP rate (-3.4) carry it. Expected minutes = P(play) x baseline, then 240 + starter tilt: test all-active MAE 8.10 -> 7.09 (train flat at 6.2). 2026-27 play rate is 69% vs 84% in 2025-26 (early-season bloated actives), so retrain as the season fills in.
- **The injury effect is real but small.** Played players, residual vs baseline, cluster bootstrap by team-game, per 10 baseline minutes of NEW rotation absence (Inactive now, Active in one of last 3 games): starters +0.58 [+0.52,+0.63] train, +0.42 [+0.28,+0.57] test; bench +0.29 train, ~0 test; same position group +0.24 train, +0.30 test (CI excludes 0 in both). A 30 mpg starter out is worth about +1.7 min to a starter, +0.9 to a bench man, +0.7 more to his position group.
- **Out of sample (fit 2025-26, score 2026-27, played players, baseline >= 8) the injury terms do not beat a plain intercept+starter fix on MAE** (5.03 vs 5.02; RMSE 6.47 vs 6.49). Most of the gain over baseline (5.22) is the intercept (baseline overshoots by ~2 min) and the starter bump. 94 new-absence team-games is too few to separate the injury part.
- **Next-man-up by minutes rank is NOT supported.** Bench rank 1-2 gains +0.30/10 freed min, rank 3-4 +0.67, rank 5+ +0.78 (train; test same direction, smaller). The effect is diffuse, not a single backup.
- Takeaway for the UI: a per-player "Opportunity" number would be small (usually under 2 min) except when a star sits. Worth showing as a sortable delta, but the value is in star-out nights and in the P(play) / starter-status flag (inactive/DNP risk), which move projections more than redistribution does.

## Next
1. Daily snapshot of the lineups JSON (Expected status before tip) so the live feature uses pregame data; the backtest used final status.
2. Usage/rate bump on FPTS per minute (global elasticity), validated separately.
3. Ship: player-table column "Opp" = projected min with tonight's Inactive list minus baseline, plus a DNP-risk marker; sort/filter on it. Feed the Yahoo daily-points optimizer and claim planner.
