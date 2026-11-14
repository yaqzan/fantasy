"""The platform (Yahoo / Fantrax) is the source of truth for my roster; the DB is a cache of it. Every reader that is
about to judge my team calls `refresh_my_team(lg)` first: one platform call (throttled 60 s per league, silent on
failure, falls back to the DB) writes Yahoo's / Fantrax's roster (and Yahoo's IL slots) into the DB. The hourly
tasks still run: they cover every other team, free agents, waivers, positions and the transaction log, and keep
the DB warm when nobody has the app open."""


def refresh_my_team(lg):
    if lg.platform == 'yahoo':
        import pull_yahoo
        return pull_yahoo.sync_my_team(lg)
    if lg.platform == 'fantrax':
        import pull_fantrax
        return pull_fantrax.sync_my_team(lg)
    return None
