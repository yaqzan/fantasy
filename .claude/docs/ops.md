# Ops

- **Port** 5001, `127.0.0.1` only. server.ps1 runs `fantasy-api` through a generated
  `.server\runtime\fantasy_api_server.py` (binds 127.0.0.1) and `fantasy-tunnel` via
  `cloudflared tunnel --config ops\cloudflared-config.yml run fantasy`. Alias `fantasy` = both.
- **Tunnel** `fantasy` (created 2026-09-24), config `ops/cloudflared-config.yml` (gitignored; UUID
  there). Hostnames: `fantasy.yaqzan.dev` (the app) and `fantasy-api.yaqzan.dev` (legacy alias,
  same app; root-level API paths from before 2026-09-24 no longer exist, only `/api/*`).
  Route DNS with `--config <that file>` and the tunnel UUID (the name argument is ignored when
  `~/.cloudflared/config.yml` names a tunnel).
- **Watchdog** task "Fantasy Watchdog", every 5 min, `ops/windows/watchdog.ps1` via the bundled
  `hidden_run.vbs`. With `-Controller` it calls `server.ps1 start -Service fantasy-api|fantasy-tunnel`;
  without, it starts `python backend\app.py` / cloudflared itself. Logs in `ops/windows/logs/`.
- **No cron jobs for data.** The API process runs a poller thread (`daily_leaders.start_poller`,
  started in `backend/app.py`; sleeps until the next thing is due, see leagues.md "Daily Leaders"):
  ESPN every 5 min while games are on; **ESPN fold**: when ESPN calls a regular-season game final, its
  lines go into `game_lines` and those players' season / last-5 / last-10 totals are recomputed at
  once (`game_log.py`; same `apply_game_stats` as the NBA pull. 2026-04-10 sandbox: 321 folded
  players equal the official totals, times blocked excepted, which is approximate between pulls).
  A fold never builds on a gap: it skips a night if `game_lines` lacks an earlier game night, and a
  player whose stored GP doesn't match his stored games. And the **nightly stats refresh** (`nightly_stats.py`): once a
  night's regular-season games are all final it runs `pull_api_data.py --after-games <date>
  --games <n>` in its own process, which exits 75 until stats.nba.com's game log has all n games
  (it lags the buzzer), then does the full pull: the official log replaces every ESPN row (stat
  corrections included) and drops ESPN rows the NBA doesn't count. Retried every 30 min, given up after 12 h (then
  run it by hand); a restarted server skips a night already pulled (newest `api_updated_at` after
  last tip + 3 h). Log: `stats_refresh.log` (gitignored). Preseason nights never run. Edge: a
  night ESPN counts but the NBA's regular-season log doesn't (the NBA Cup final) retries 12 h.
- **History:** until 2026-09-24 the frontend was a Cloudflare Pages project (`fantasy`, built from
  the repo now called `fantasy-archive`) and the API rode the dashboard-managed `trading-api`
  tunnel as `fantasy-api.yaqzan.dev`. That tunnel may still list a stale `fantasy-api` ingress
  rule in the dashboard; harmless, DNS points at the `fantasy` tunnel.
