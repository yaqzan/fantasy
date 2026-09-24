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
- **History:** until 2026-09-24 the frontend was a Cloudflare Pages project (`fantasy`, built from
  the repo now called `fantasy-archive`) and the API rode the dashboard-managed `trading-api`
  tunnel as `fantasy-api.yaqzan.dev`. That tunnel may still list a stale `fantasy-api` ingress
  rule in the dashboard; harmless, DNS points at the `fantasy` tunnel.
