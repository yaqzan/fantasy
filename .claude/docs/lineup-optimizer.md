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
| Platform's own played lineups (canon) | `canon.py` (shape, provider registry, TTL cache, back-off, concurrent day loop) + providers `fantrax_canon.py`, `yahoo_canon.py`; used by `Week.team(canon=)`. A new platform = one module with `PLATFORM`, `fetch_day`, optional `period_totals`, `canon.register(...)` |
| Played games, live pro-rating, tipped games | `week_actuals.py` (`WeekActuals`, `game_left`); slates from `daily_leaders.slate` |
| Per-player games, lineups, category totals and chances | `player_stats.py` (`player_week_games`, `fill_slots`, `team_week_totals`, `category_win_chances`) |
| Claims already used this week | `fantasy_team_helper.claims_left` (Yahoo only) |
| Week plan (ILP: adds, drops, IL moves, claim days; Yahoo daily points leagues) | `claim_planner.py` (`week_plan`, `solve`, `score_judge`), `/api/plan`; card `components/WeekPlan.js` |
| Page | `frontend/src/components/LineupOptimizer.js`; API client `services/api.js` (`analyze`, `pickups`, `getPlan`); sibling `WeeklyPickups.js` |
| Terminal | `python lineup_optimizer.py <league> proj [moves] [plan]` ; `python claim_planner.py <league>` |

## Traps

- Previews are real `/api/analyze?add=&drop=&day=` calls; the page never does model maths (only the week-win chance, Poisson-binomial).
- Mid-week the played part is the platform's own (`canon.py`: Fantrax via `fantrax_canon.py`, Yahoo via `yahoo_canon.py`: one `teams/roster;date=D/players/stats` call per day gives each team's slot that day and Yahoo's points; BN/IL player-days don't count, so a player picked up mid-game, who lands on the bench, no longer brings points he scored for someone else, Hyland 2026-10-30). Only player-days the platform counted AND the player played are listed (a Yahoo starter with no game has every stat `-`: leaving him in zeroed today's projection, because slots read as full). Same `Canon` shape; `Week()` loads canon and ESPN slates side by side (cold ~9 s Yahoo / ~3 s Fantrax, warm ~0.4 s; `daily_leaders.slate` holds one global lock across its fetch, so threading the slate days buys nothing); refreshes of the Yahoo token / Fantrax cookie are locked because days fetch on 4 threads. See leagues.md "A week under way". `progress.canon` says whether it applied; `/api/analyze`'s `canon` block (Fantrax only) diffs our played totals against Fantrax's. Checked 2026-10-30: our Courtside total = Yahoo's scoreboard (1003.45).
- Yahoo waiver players: `pull_yahoo.py sync` stores the day they clear in `league_player_flags.waiver_until`; `Week.add_days` never offers a claim before it (a claim lands that day). Stale until the next sync.
- Injuries: `players.injury_status` is Yahoo's status for every player, refreshed by the hourly Yahoo sync. O / INJ = out all week (`get_injured_players`; the owner's hand flags are ignored here). P / Q / D / DTD / GTD = may play his next game only, at `DAY_TO_DAY_CHANCE` (.9 / .5 / .2 / .5; guesses, uncalibrated) via `player_week_games(doubtful=)`. Yahoo gives no return date, so a short absence reads as out all week (ESPN's injuries feed has the timeline in free text: not wired).
- Do not drop: `league_player_flags.undroppable` (per league) keeps a player out of every drop (`rank_moves`, `best_moves`, `plan_stage`, the manual drop picker). Yahoo's can't-cut sets it in the sync; the owner sets it by hand with the "Do not drop" chips on the page (`PUT /api/undroppable {player_name, undroppable}`). The sync never clears a hand flag. Flags are per league: lock a player in each league he is yours. The chips list IL players too (the week plan honours their flag).
- IL strip (`IlStrip` in `LineupOptimizer.js`, from `/api/analyze` `il`, `injury`, `il_slots`): no sentences, only chips. A healthy player still in IL is amber with a glow and a lock (he freezes the lineup and blocks adds); my O/INJ players on the active roster are red ("-> IL" with a free slot, "IL full" without). `il_slots` is 3 for Yahoo leagues (`IL_SLOTS`, same as `claim_planner.K`), 0 elsewhere. The plan card marks frozen days with a lock icon only.
- Claim day = the latest day that is nearly as good: `rank_moves` moves a daily-league claim to a later day unless the earlier one beats it by `EARLY_CLAIM_EDGE` (0.01 expected categories). Without it a pickup who sits on a full bench today (only covering an absent starter) read "claim today" when he first starts tomorrow (Tyson, Courtside, 2026-10-28).
- A claim is assumed to take effect at once; a player in a started game can't be dropped that day.
- Claims left: Yahoo leagues from the sync's pickups used; Fantrax leagues ask Fantrax live (`fantrax_canon.claims_remaining`, "Claims Remaining (Week)", current week only, 90 s cache; any other week or no answer = the full allowance). Guillotine showed 1/1 while Fantrax said 0 (2026-10-29).
- A stored next-week choice is overridden on a week's last day while a claim remains; the owner's own week choice is lost on tab unmount.
- To test a mid-week state without waiting for one: build `Week(league, ws, we)`, set `week.actual = WeekActuals(ws, we, today, fake_slate, norm_name)` and `week.remaining, week.day_weights = week.actual.remaining(week.schedule)`, then call `rank_moves`. Compare against a brute-force drops x days search.
- DB rosters and injury flags go stale between syncs (`pull_yahoo.py sync`, `pull_fantrax.py rosters`); sync before judging a ranking.
- Not yet looked at in a browser by the owner as of 2026-10-26; verify with endpoint probes and the build, not a screenshot.

## Week plan (claim_planner.py)

Built from the `.horizon/claims-ilp/` prototype (formulation `04-opus-final.md`, owner answers `05-decisions.md`, the
corrections in `driver/NOTES_plan.md`); equal to it on the live Courtside week (same moves, objective diff 0, judge
P(win) equal; 2026-11-02). Supported: Yahoo, daily lineups, points. Elsewhere `/api/plan` is `{supported: false, reason}`.

- **Rules encoded (owner-confirmed):** adds cost the week's claims, drops and IL moves are free. A dropped player is
  unaddable league-wide for 3 days (`waiver_until`); re-adding my own drop is banned. IL takes only OUT players, but a
  healthy player may stay there: that **freezes** the lineup (Yahoo's stored lineup plays) and **blocks adds** (Yahoo
  help SLN6863) until he is activated, and activating needs an open active spot. Only starters score; the bench covers
  absent starters (`_lineup_chance` layers, availability 0.86). A player in a game under way can't be dropped or moved today.
- **Objective = the judge's own day value, Abel-summed:** `sum_r w_r v_(r) = sum_{k=n}^{R} c_k S_k`, `c_k = w_{k-1} - w_k`,
  `w_R := 0`, S_k = best k active players' v. For n = 9, R = 13: c = 0.2213 0.2788 0.1952 0.1002 0.0645 (sum 0.86).
  04's form (0.86 on the starters + dw on the bench) double-counted `w_n S_n` and dropped `w_13 S_13`: up to 216 FPTS/day off.
  v carries no 0.86 (it lives in the weights) or it is counted twice.
- **Positions off by default** (`solve(positions=False)`): the repo judge (`player_week_games`) ignores positions when
  availability < 1, so a position-constrained ILP lost to greedy on the judge. Make the judge position-aware first.
- **Freeze by enumeration:** each healthy IL player's activation day d* in {today..last day, never} (today skipped
  while his game is on) is one MILP; the best objective wins. Activating on d* leaves him droppable, which covers
  "drop him". Frozen days: stored starters at 0.86 each, no cover, no adds, no IL entries.
- **Tie-breaks (FPTS):** 0.1 per day earlier on adds and drops (prefer later), 0.5 per drop, 0.25 per IL move (without
  it the solver moved an OUT player out of IL for a day to drop him later).
- **Assumes an atomic IL swap** (one player out of IL, another in, one submit on Yahoo; by Yahoo rule, unverified):
  the payload warns whenever a day has both.
- **Rolling:** only today's moves (`do_today`) are actionable; the plan is re-solved on each load (60 s result cache).
  OUT = out all week, a healthy IL player stays healthy, the opponent makes no moves, claims land at once.
- **Win chance** = `score_judge`: each day's roster through `Week.team` (one day's `remaining`/`doubtful` at a time),
  then `category_win_chances` vs the opponent; "now" is the same judge on no moves (frozen days included, so it can
  read lower than `/api/analyze`'s chance, which ignores the freeze).
- **Cost:** one Week build + 7 Yahoo `team/.../roster;date=D` GETs (4 threads, cached 30 min in memory, one burst at a
  time) + ~8 MILPs (~0.05 s each). The card fetches only after `/api/analyze` is in, so the Week's canon is warm.
