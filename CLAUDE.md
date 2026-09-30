# Fantasy

NBA fantasy basketball dashboard and lineup optimizer: https://fantasy.yaqzan.dev.
Flask + Peewee/MySQL backend, React (CRA) + Tailwind frontend, one process on port 5001.

**Public repo (github.com/yaqzan/fantasy), plug and play.** Owner state is gitignored or in MySQL:
`.env` (Fantrax login, DB), the `leagues` table (rules, schedule, league mates' names),
`*.cookie` (Fantrax session), `ops/cloudflared-config.yml`. Tracked files carry no credential,
league id or person's name. Pre-2026-09-23 history (it holds a real password) is in private
`yaqzan/fantasy-archive`.

## Commands

- `C:\Development\server.ps1 start|status|logs -Service fantasy` - api + tunnel (`fantasy-api`, `fantasy-tunnel`)
- `npm --prefix frontend run build` - deploy a frontend change (Flask serves `frontend/build`, live on reload)
- `python init_db.py` - create/upgrade the database + tables (safe to re-run, additive only)
- `python pull_api_data.py [--season 2025-26 --force]` - schedule, standings, rosters, stats, techs
- `python pull_technical_fouls.py` - play-by-play tech scan alone (~3s per new game)
- `python pull_api_data.py --rosters --season 2026-27` - teams from next season's rosters, stats untouched
- `python pull_history.py` then `python pull_projections.py` - history, then our model + ESPN projections
- `python import_projections.py players|teams <csv> [--source X]` - load another projection source
- `python pull_fantrax.py projections|techs --league <fantrax id>` - Fantrax projections / past techs (saved login)
- `python lineup_optimizer.py [--league <id>] [--pickup]` - this week's matchup in the terminal
- `ops\windows\install-tasks.ps1 -Controller C:\Development\server.ps1` - watchdog task; ELEVATED shell

## Invariants

- **One origin.** API routes live under `/api` (blueprint prefix); every other path is the React
  app (`serve_frontend`). `static_folder=None` so `/static/*` reaches the build. Don't add a
  second host for the frontend (it used to be a Cloudflare Pages project; retired 2026-09-24).
- **Bind 127.0.0.1**, never `0.0.0.0`, and never `FLASK_DEBUG=1` on a reachable host (the
  Werkzeug debugger runs arbitrary code).
- **Own tunnel** `fantasy` (locally managed, `ops/cloudflared-config.yml`). Never route Fantasy
  through the dashboard-managed `trading-api` tunnel again.
- Credentials only from `.env`; never a default league id or password in code.
- **Multi-league.** Rules, teams, rosters, undroppable flags and schedules belong to a league;
  every league-scoped query filters by it. Requests pick it with the `X-League` header. Never
  reintroduce league constants in `fantasy_config.py` (it holds NBA-wide settings only).

Detail: leagues, categories, daily vs weekly lineups -> `.claude/docs/leagues.md`.
Projections (players, rookies, team wins, sources, backtests) -> `.claude/docs/projections.md`.
Hosting, tunnel, watchdog, cutover history -> `.claude/docs/ops.md`.
Draft strategy: what the room pays for, price-tier returns, category pairs, anchor builds -> `.claude/docs/draft-strategy.md`.
Kanban -> vault `Engineering Wiki/Projects/Fantasy/`.
