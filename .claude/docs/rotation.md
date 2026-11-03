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

## Next
1. P(plays) for Active players (DNP-CD, rest) so zeros stop dominating MAE; score minutes only for players who play separately.
2. Next-man-up by minutes rank within the rotation, not position group.
3. Per-minute rate bump (usage) as one global elasticity, validated on FPTS/min.
4. Then the UI: "Opportunity" delta (projected min/FPTS with tonight's Inactive list minus baseline) as a sortable, filterable player-table column; feed Yahoo daily-points Optimizer and claim planner.
