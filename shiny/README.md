# NWSL Finishing Explorer — Shiny

A companion to the static dashboard, doing the one thing a rendered page
cannot: hand the reader the thresholds.

Every number on the static site is baked at build time, so its judgement calls
are fixed — the qualification bar is 30 minutes per game the team has played,
the shot floor is 10, penalties are always out. Those are defensible and they
are still choices. Here they are controls, and the pool re-derives live.

That is the honest case for Shiny over a static page. Building a Shiny app
that shows the same fixed chart would prove nothing.

## Run it

```r
install.packages(c("shiny", "ggplot2", "dplyr", "DT", "httr", "jsonlite"))
shiny::runApp()
```

Opens at `http://127.0.0.1:xxxx`. No R experience needed to check it works.

## Publish it (free)

```r
install.packages("rsconnect")
rsconnect::setAccountInfo(name="...", token="...", secret="...")   # from shinyapps.io
rsconnect::deployApp()
```

shinyapps.io's free tier allows five applications and 25 active hours a month,
which is more than enough for a portfolio piece. The deployed URL is the
credential.

## Data

Live from the ASA API when reachable; falls back to
`data/nwsl_2026_snapshot.csv` and **says which one it used** in the sidebar.
A portfolio app that silently shows stale numbers when an API is down is worse
than one that is honestly offline — the same rule the warehouse follows when a
load fails.

npxG is derived here the way the Python pipeline derives it: `/players/xgoals`
called twice, once unfiltered and once with `shot_pattern=Penalty`, and
subtracted. ASA publishes no non-penalty field.

## Known limitation, on purpose

For a mid-season transfer, ASA returns `team_id` as a two-element list in an
order that carries no meaning. This app takes the first element. The static
pipeline resolves it properly with a per-club call per player, which is a dozen
extra API round-trips — too slow for a reactive app that re-fetches on every
season change. The comment in `fetch_live()` says so rather than leaving it
looking correct.

Six players in 2026 are affected. Named in `dw.dq_multi_team` on the warehouse
side.

## Files

| | |
|---|---|
| `app.R` | the whole app — UI, server, ASA client, fallback |
| `data/nwsl_2026_snapshot.csv` | 245 players, offline fallback |
