# Fantasy

NBA fantasy basketball dashboard and lineup optimizer: https://fantasy.yaqzan.dev.
Flask + Peewee/MySQL backend, React (CRA) + Tailwind frontend, one process on port 5001.

**Public repo (github.com/yaqzan/fantasy), plug and play.** Owner state is gitignored: `.env`
(Fantrax login, league id, DB), `league.json` (team + schedule with league mates' names),
`*.cookie` (Fantrax session), `ops/cloudflared-config.yml`. Tracked files carry no credential,
league id or person's name. Pre-2026-09-23 history (it holds a real password) is in private
`yaqzan/fantasy-archive`.

## Commands

- `C:\Development\server.ps1 start|status|logs -Service fantasy` - api + tunnel (`fantasy-api`, `fantasy-tunnel`)
- `npm --prefix frontend run build` - deploy a frontend change (Flask serves `frontend/build`, live on reload)
- `python init_db.py` - create the database + tables (safe to re-run)
- `python pull_api_data.py` / `update_daily_stats.py` - stats ingest
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

Detail: hosting, tunnel, watchdog, cutover history -> `.claude/docs/ops.md`.
Kanban -> vault `Engineering Wiki/Projects/Fantasy/`.
