# Lineup Optimizer (the Pickup Desk): where things are

Read this first; it is a map. The rules and model are in `leagues.md` "Weekly matchup model", "A week under way",
"Mid-week pickup timing", "Pickups", "Stage plan"; the page design is in `frontend.md` "Lineup Optimizer = the Pickup Desk".
The optimizer is NOT a lineup-setting tool: it projects this week's head-to-head and ranks free-agent claims (add + drop + claim day).

## Map

| Piece | Where |
|---|---|
| Week model (schedule, opponent, free agents, remaining games, claim days) | `lineup_optimizer.py` `Week` |
| Rank pickups (one `Move` per candidate: best drop + day) / greedy claims | `rank_moves` / `best_moves` |
| Guillotine stage plan | `plan_stage` (`/api/stage-plan`) |
| `/api/analyze` payload, `/api/pickups` payload | `get_matchup`, `get_pickup_candidates` (routes in `backend/app.py`) |
| Platform's own played lineups + totals (Fantrax) | `fantrax_canon.py` (`load`), used by `Week.team(canon=)` |
| Played games, live pro-rating, tipped games | `week_actuals.py` (`WeekActuals`, `game_left`); slates from `daily_leaders.slate` |
| Per-player games, lineups, category totals and chances | `player_stats.py` (`player_week_games`, `fill_slots`, `team_week_totals`, `category_win_chances`) |
| Claims already used this week | `fantasy_team_helper.claims_left` (Yahoo only) |
| Page | `frontend/src/components/LineupOptimizer.js`; API client `services/api.js` (`analyze`, `pickups`); sibling `WeeklyPickups.js` |
| Terminal | `python lineup_optimizer.py <league> proj [moves] [plan]` |

## Traps

- Previews are real `/api/analyze?add=&drop=&day=` calls; the page never does model maths (only the week-win chance, Poisson-binomial).
- Mid-week, Fantrax leagues use Fantrax's own played lineups (`fantrax_canon.py`, leagues.md "A week under way"); Yahoo leagues still use today's roster and assume the best-fitting players started. `progress.canon` says which; `/api/analyze`'s `canon` block diffs our played totals against Fantrax's.
- Yahoo waiver players: `pull_yahoo.py sync` stores the day they clear in `league_player_flags.waiver_until`; `Week.add_days` never offers a claim before it (a claim lands that day). Stale until the next sync.
- Injuries: `players.injury_status` is Yahoo's status for every player, refreshed by the hourly Yahoo sync. O / INJ = out all week (`get_injured_players`; the owner's hand flags are ignored here). P / Q / D / DTD / GTD = may play his next game only, at `DAY_TO_DAY_CHANCE` (.9 / .5 / .2 / .5; guesses, uncalibrated) via `player_week_games(doubtful=)`. Yahoo gives no return date, so a short absence reads as out all week (ESPN's injuries feed has the timeline in free text: not wired).
- Claim day = the latest day that is nearly as good: `rank_moves` moves a daily-league claim to a later day unless the earlier one beats it by `EARLY_CLAIM_EDGE` (0.01 expected categories). Without it a pickup who sits on a full bench today (only covering an absent starter) read "claim today" when he first starts tomorrow (Tyson, Courtside, 2026-10-28).
- A claim is assumed to take effect at once; a player in a started game can't be dropped that day.
- Claims left: Yahoo leagues from the sync's pickups used; Fantrax leagues ask Fantrax live (`fantrax_canon.claims_remaining`, "Claims Remaining (Week)", current week only, 90 s cache; any other week or no answer = the full allowance). Guillotine showed 1/1 while Fantrax said 0 (2026-10-29).
- A stored next-week choice is overridden on a week's last day while a claim remains; the owner's own week choice is lost on tab unmount.
- To test a mid-week state without waiting for one: build `Week(league, ws, we)`, set `week.actual = WeekActuals(ws, we, today, fake_slate, norm_name)` and `week.remaining, week.day_weights = week.actual.remaining(week.schedule)`, then call `rank_moves`. Compare against a brute-force drops x days search.
- DB rosters and injury flags go stale between syncs (`pull_yahoo.py sync`, `pull_fantrax.py rosters`); sync before judging a ranking.
- Not yet looked at in a browser by the owner as of 2026-10-26; verify with endpoint probes and the build, not a screenshot.
