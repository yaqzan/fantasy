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
| Per-day minutes factor (teammates out / back, ESPN return dates, tonight's sheet) | `role_minutes.factors` via `Week.minutes_factor(suffix)`; model in rotation.md "Role-aware minutes" |
| Week plan (ILP: adds, drops, IL moves, claim days; Yahoo daily points leagues) | `claim_planner.py` (`week_plan`, `solve`, `score_judge`, `keep_values`), `/api/plan`; card `components/WeekPlan.js` |
| Page | `frontend/src/components/LineupOptimizer.js`; API client `services/api.js` (`analyze`, `pickups`, `getPlan`); sibling `WeeklyPickups.js` |
| Crowded day: who to start (the Start tab; daily category leagues, all-UTIL slots) | `start_day.py` (`status`, `lineups`), `/api/start-day[/status]`; `components/StartDay.js`, tab logic in `App.js` |
| Terminal | `python lineup_optimizer.py <league> proj [moves] [plan]` ; `python claim_planner.py <league>` |

## Traps

- Previews are real `/api/analyze?add=&drop=&day=` calls; the page never does model maths (only the week-win chance, Poisson-binomial).
- Mid-week the played part is the platform's own (`canon.py`: Fantrax via `fantrax_canon.py`, Yahoo via `yahoo_canon.py`: one `teams/roster;date=D/players/stats` call per day gives each team's slot that day and Yahoo's points; BN/IL player-days don't count, so a player picked up mid-game, who lands on the bench, no longer brings points he scored for someone else, Hyland 2026-10-30). Only player-days the platform counted AND the player played are listed (a Yahoo starter with no game has every stat `-`: leaving him in zeroed today's projection, because slots read as full). Same `Canon` shape; `Week()` loads canon and ESPN slates side by side (cold ~9 s Yahoo / ~3 s Fantrax, warm ~0.4 s; `daily_leaders.slate` holds one global lock across its fetch, so threading the slate days buys nothing); refreshes of the Yahoo token / Fantrax cookie are locked because days fetch on 4 threads. See leagues.md "A week under way". `progress.canon` says whether it applied; `/api/analyze`'s `canon` block (Fantrax only) diffs our played totals against Fantrax's. Checked 2026-10-30: our Courtside total = Yahoo's scoreboard (1003.45).
- Yahoo waiver players: `pull_yahoo.py sync` stores the day they clear in `league_player_flags.waiver_until`; `Week.first_claim_day` is the day AFTER it (the FAAB auction processes overnight; owner 2026-11-07, PJ Washington on waivers to Nov 10 was offered Nov 10). `add_days`, the pickup rows' `days` and `claim_planner` all use it. A plain free agent: now. Stale until the next sync.
- Injuries: `players.injury_status` is Yahoo's status for every player, refreshed by the hourly Yahoo sync. O / INJ = out all week (`get_injured_players`; the owner's hand flags are ignored here). P / Q / D / DTD / GTD = may play his next game only, at `DAY_TO_DAY_CHANCE` (.9 / .5 / .2 / .5; guesses, uncalibrated) via `player_week_games(doubtful=)`. A player the NBA lineup sheet confirms as tonight's starter is dropped from that list (`nba_rotation.tonight_doubtful`, server only; Inactive-tonight is NOT fed in: wrong-day trap, rotation.md "Round 3"). Yahoo gives no return date, so a short absence still reads as out all week for the player himself (ESPN's dates, `injury_reports`, only move his teammates' minutes, next trap).
- Minutes factor (2026-11-03): `Week.minutes_factor(suffix)` = `role_minutes.factors` over the WHOLE week's schedule (not `remaining`: `score_judge` narrows that per day), cached per suffix; `Week(role_minutes=False)` switches it off. `player_week_games(minutes_factor=, effective={})` scales what each game adds to his stats (into `effective`, which `Week.team` passes to `team_week_totals` as the stat games, real games as `games_played` for wins), never the game count, wins or `plays`; in daily leagues a day with factors re-sorts that day's lineup by score + (f - 1) x |score|. `claim_planner` puts the same factor in `v[t]` (`PlayerData.mf`, also in the `_split_doubtful` copies and the IL d* copy), so ILP and judge agree (checked: Reed v = FPTS x factor on both of his games). CLI runs read MySQL (`injury_reports`, `depth_charts`, `game_lines`); only "tonight's sheet" needs the poller. No model / no data = {} = every game at his usual minutes. Add budget, add windows and IL logic are untouched (Courtside 2026-11-03: 5 adds either way, 3 of them the same; the judge scores with the factor too, so its FPTS are not comparable across the switch). Evidence it picks better: rotation.md "Streamers".
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
P(win) equal; 2026-11-02). Since then production alone has the pool rule, bounded d* search and doubt split below
(the prototype's `driver/plan.py`/`extract.py` take force options and a league id, so they stay separate). Supported: Yahoo, daily lineups, points. Elsewhere `/api/plan` is `{supported: false, reason}`.

- **Rules encoded (owner-confirmed):** adds cost the week's claims, drops and IL moves are free (but a drop gives up
  his keep value, below). A dropped player is
  unaddable league-wide for 3 days (`waiver_until`); re-adding my own drop is banned. IL takes only OUT players, but a
  healthy player may stay there: that **freezes** the lineup (Yahoo's stored lineup plays) and **blocks adds** (Yahoo
  help SLN6863) until he is activated, and activating needs an open active spot. Only starters score; the bench covers
  absent starters (`_lineup_chance` layers, availability 0.86). A player in a game under way can't be dropped or moved today.
- **Objective = the judge's own day value, Abel-summed:** `sum_r w_r v_(r) = sum_{k=n}^{R} c_k S_k`, `c_k = w_{k-1} - w_k`,
  `w_R := 0`, S_k = best k active players' v. For n = 9, R = 13: c = 0.2213 0.2788 0.1952 0.1002 0.0645 (sum 0.86).
  04's form (0.86 on the starters + dw on the bench) double-counted `w_n S_n` and dropped `w_13 S_13`: up to 216 FPTS/day off.
  v carries no 0.86 (it lives in the weights) or it is counted twice. Plus each player's keep value on o[last day]
  (mine at the week's end); `model_fpts` and the judge exclude it, so "points" and win chance stay this week's.
- **Keep value (2026-11-04, `keep_values`):** before it, a player with no games left looked worthless, so plans sold
  roster quality for one-game streams (Jalen Green, ROS rank 77, dropped on the week's last day: the old objective
  was an exact tie between dropping him and a streamer). keep = max(his FPTS/g - replacement, 0) x the games he is
  expected to play in the next 2 fantasy weeks, weighted `KEEP_WEEK_WEIGHTS` 1 / 0.5 (a 2-week matchup counts its first week only; league schedule; chance per game = `role_minutes`
  Season.p_out: ESPN return date, Yahoo status, streak; a game he misses costs nothing, he sits in IL). Replacement =
  the `claims_per_week`-th best healthy free agent's FPTS/g. Season's last week (no next week) = no keep: pure
  streaming; a week whose NBA schedule is not stored = `AVG_WEEK_GAMES` 3.5 games x ROS_SHARE (noted). No claim
  carry-over (claims reset weekly); the 3-day unaddable rule needs nothing extra (a drop forfeits all of it).
  Payload: `keep` on add/drop transactions, `plan.keep_total` (week-end roster's keep minus today's).
  Evidence (`.horizon/keep-value/`, `driver/sim.py` + `summary.py`): 51 start weeks of 2023-24..2025-26 game logs x 4
  draft slots, no look-ahead (walk-forward priors + `inseason.project`), other teams re-take the top 117 every
  Monday, the planner re-solved every morning, realised FPTS of the top 9 who played. Over 3 weeks keep beats no-keep
  by +135 FPTS in that 10-team world (95% CI +100..+170, of ~4580; it gives up ~15 in the first week); the review's
  independent sim (`.horizon/review-keep/rsim.py`) at Courtside's real 14 teams: **+57 (CI +29..+89), ~1.4%**; plentiful
  free agents +28 (CI -5..+52), streaming unhurt. A bare tie-break (of two zero-value drops, drop the worse player)
  already earns +23..+26 of it; the keep value still beats that (-32 for the tie-break, CI -56..-6). Top-100 drops
  3.98 -> 0.63 per trial, adds unchanged (15). Weights 1/1 vs the shipped 1/0.5: no measurable difference (the first
  sim said 1/1 by +10, CI 1..20; the review's sim +5, not significant); 0.5/0.25 worse, a third week no better,
  replacement = the best free agent worse. A flat `max(fpg - repl, 0) x 7` keeps 90-96% of the gain (3-11 FPTS behind,
  not significant) but cannot see return dates, which no sim can test.
- **Positions off by default** (`solve(positions=False)`): the repo judge (`player_week_games`) ignores positions when
  availability < 1, so a position-constrained ILP lost to greedy on the judge. Make the judge position-aware first.
- **Freeze by search over d*:** each healthy IL player's activation day d* in {today..last day, never} (today skipped
  while his game is on); one MILP per combination, the best objective wins. Activating on d* leaves him droppable,
  which covers "drop him". Frozen days: stored starters at 0.86 each, no cover, no adds, no IL entries.
  Up to 60 combinations (`FULL_ENUM`) every one is tried (exact). More (2-3 healthy players or a 12-14 day week, up
  to 3375 combos, 127 s): every player on one common day D first (the freeze ends at max d*; activating earlier
  scores nothing on a frozen day), then coordinate descent one player at a time. **Hard budget 8 s** (`SOLVE_BUDGET`):
  past it the best plan so far is returned and the payload warns. Checked 2026-11-02 (`.horizon/claims-ilp/out/b3_check.json`):
  40 small instances identical to full enumeration; 20 largest (64-3375 combos) objective gap 0, max 8.1 s (one hit the budget, still exact) vs 100 s.
- **Pool:** per day t and base position, the top C+9 free agents by v[t] PLUS the top C+9 by the rest of the week
  if added on t (sum of v[t..] + keep). The day-only rule cut multi-game streamers who top no single day (13/2000 property
  instances lost up to 8.4 FPTS); with both, all 13 match the objective with every free agent. Pool ~60-90.
- **Doubtful players:** the Q/D factor is about his NEXT game, so it sits on his first game after the day he is
  actually added (the judge's rule). A doubtful free agent is split into one candidate per add window (days whose
  next game is g, factor on g), at most one copy added; a doubtful healthy IL player gets his factor on his first game
  from his d*. Cost +4% solve time. On the 50 property instances where the old window put the ILP below greedy on
  the judge, 30 remain: 12 are doubtful IL players in the no-freeze test world (no d* there; production has it), 15
  are a judge convention the ILP can't copy: `player_week_games` keeps a doubtful player at his full-score rank and
  scales his chance, the ILP sorts by the doubt-scaled v (gap closes with owned doubt := 1); 2 are tie-break size, 1 other.
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
  time) + ~8 MILPs (~0.05 s each; live Courtside 2026-11-02: 1 MILP, 0.07 s, endpoint ~4.5 s cold). Keep values:
  ~0.23 s (the Season role_minutes already built + one `injury_reports` read). The card fetches only after `/api/analyze` is in, so the Week's canon is warm.

## Start tab (start_day.py, 2026-11-04)

Fantrax category leagues (WSOP, Guillotine) set `roster.active` (6) starters of 10, and on a night when almost everyone
plays the question is who. Capability by rule, not id: `supported` = daily lineups + category scoring + all-UTIL slots.
- **Method:** every legal lineup of the players who can still start (healthy, game today, not tipped) goes through
  `Week.team`; the sat players get a window starting tomorrow, so the rest of the week plays as usual. Value = expected
  categories won against this week's opponent, plus the week-win chance (Poisson-binomial). Exact search up to
  `MAX_LINEUPS` 600 (6 of 10 = 210 lineups, 3-5 s cold, cached 60 s); more is reported as `too_many`, not searched.
- **Roles:** MUST = benching him costs >= `MUST_COST` 0.03 categories of the best lineup; the rest compete for the open
  spots ("toss-up" within `TOSSUP_LOSS` 0.04 of the best lineup, else bench), each with what the best lineup containing
  him loses. Q/GTD players keep `DAY_TO_DAY_CHANCE` and show "% to play".
- **Tab:** `/api/start-day/status` (no lineup search, but builds a Week: ~2 s cold, 60-s cache) decides it; the tab shows only when TODAY has more candidates than
  slots, is first in the row and lit with a pulsing dot (phones show three tabs), and the tab row fades at a cut edge.
  Day chips list the week's conflict days (`conflict_days`); `?day=` takes any day left this week. A sat player is left
  out of that one game only (`player_week_games(sit=)`, `Week.team(sit=)`); `windows` would cut his earlier games too.
- **Not modelled:** a tipped player counts as locked in (his slot is taken); the real lineup set on Fantrax isn't read;
  swing numbers carry the model's usual overconfidence (leagues.md "Calibrated"). Seen 2026-11-04: best vs worst six was about 6-7 points of
  week-win chance in WSOP, 3 in Guillotine. A finished game today counts as locked in; a sat Q/GTD player's doubt is dropped
  for that lineup (else it moved onto his next game).

