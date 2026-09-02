# NWSL xG

[![Weekly NWSL refresh](https://github.com/duransound/nwsl-dashboard/actions/workflows/weekly.yml/badge.svg)](https://github.com/duransound/nwsl-dashboard/actions/workflows/weekly.yml)

A weekly-refreshed NWSL analytics dashboard, and the tested pipeline underneath it.

Everything here is built from [American Soccer Analysis](https://www.americansocceranalysis.com/)'s
public API — the same data behind ASA's own site and the `itscalledsoccer`
packages. Raw JSON responses land in DuckDB untouched and append-only, a dbt
project models them into dimensions, facts and marts, **41 data tests** have to
pass, and only then is the static site rebuilt and pushed. Nothing is
hand-edited on the way through, and a load that fails leaves yesterday's
numbers standing rather than half of today's.

## What's live

|  |  |
|---|---|
| **[Dashboard →](https://duransound.github.io/nwsl-dashboard/)** | 15 tabs, running from the league-wide picture down to individual finishing. Rebuilt every Tuesday by GitHub Actions. One self-contained HTML file — no server, no build step, no JavaScript dependencies. |
| **[Tableau Public →](https://public.tableau.com/app/profile/ian.duran/viz/nwsl-xg-difference/Placementvs_Luck)** | Three sheets off the same warehouse extracts: team xG difference, the league xGF/xGA quadrant, and Placement vs. Luck. |
| **[Shiny app →](https://ianduran.shinyapps.io/nwsl-finishing-explorer/)** | The thresholds the dashboard bakes in at build time — the qualification bar, the shot floor — handed to the reader as controls, with the pool re-derived live from the ASA API on every change. Source in [`shiny/`](shiny/). |

## What's underneath

```
ASA API  ──▶  raw.asa_records          append-only JSON, one row per record,
                    │                  every load stamped; nothing overwritten
                    ▼
              stg.*                    typed views: team_id arrays unwrapped,
                    │                  minutes_played / minutes coalesced
                    ▼
              dw.dim_* fct_* mart_*    dbt — 23 models, 41 data tests
                    │
                    ▼
              index.html               15 tabs, published weekly by CI
```

Raw is never rewritten, so any number on the site can be traced back to the
exact API response it came from, and a modelling change can be replayed
against last month's payloads without re-fetching anything.

| Path | What it is |
|---|---|
| [`nwsl_warehouse.py`](nwsl_warehouse.py) | Loader and CLI — `load`, `build`, `tables`, `sql`, `dbt`. Talks to ASA, writes raw, drives the models. |
| [`sql/`](sql/) | `010_raw.sql`, `020_staging.sql`, `030_marts.sql` — the whole warehouse in plain SQL, runnable without dbt. |
| [`dbt/`](dbt/) | The same models under dbt, plus the tests. [`dbt/tests/`](dbt/tests/) holds 11 singular tests, each one named for a bug that actually happened. |
| [`WAREHOUSE.md`](WAREHOUSE.md) | How the warehouse is shaped and why. |
| `build_dashboard.py`, `chart_builders.py`, `dashboard_template.py` | The site: what each chart says, the shared chart library, the page itself. |
| [`tableau/`](tableau/) | The workbook, the three CSV extracts, and the exporter that writes them. |
| [`freeze_frames/`](freeze_frames/) | The StatsBomb shot-context study. |
| [`.github/workflows/weekly.yml`](.github/workflows/weekly.yml) | Tests → warehouse + dbt → rebuild → publish. The four steps that have to pass in order. |

## Findings

- **[Placement vs. Luck](placement-vs-luck-post.md)** — ASA publishes a field
  called `xplace` that is documented nowhere. Read as a placement increment, it
  splits finishing overperformance into the part a player controls and the part
  that is weather. Ashley Sanchez leads the league on finishing margin with a
  placement of −0.15; Katherine Rader's smaller margin is three-quarters
  placement. The post argues the case and then argues against itself with the
  chance band.
- **[Freeze frames](freeze_frames/README.md)** — whether StatsBomb's shot
  freeze frames (where every player stood at the moment of the shot) improve on
  a pre-shot xG model. A negative result, written up as one rather than
  quietly dropped.

## Design

Charts follow this project's Design Guidelines: IBM Carbon and NASA's 1976
Graphics Standards Manual for restraint and a single consistent system,
Duarte / Knaflic / Tufte for the storytelling. In practice — every chart title
states a finding rather than a metric name; exactly one mark per chart carries
the accent colour (amber `#C98A2E`, or red `#e34948` when the story is
negative) while everything else recedes to grey; and the tabs are ordered from
the league-wide picture down to the specific finding rather than presented as
equally-weighted views.

---

**Everything below is the build log** — how this got here, round by round,
including the parts that were wrong first and had to be corrected. It is
chronological, so the early sections describe a smaller project than the one
above.

## Files (the original starter kit)

- **`nwsl_xg_charts.py`** — the real, reusable script. Calls the ASA API
  directly with `requests`, pulls team- and player-level xG, and writes 2 CSVs
  + 3 PNG charts.
- **`demo_snapshot.py`** — reuses the same chart functions against a small,
  hand-verified snapshot of 2025 NWSL data (used to generate the preview PNGs
  sent alongside this kit, since the cloud sandbox that built this couldn't
  reach the live API — see note below).
- **`*_demo.png`** — the preview charts, built from that real snapshot.
- **`build_xg_xa_chart.py`** — builds the interactive xGoals-vs-xAssists
  bubble chart (see below) as a single self-contained HTML file, pulling live
  data from the ASA API.
- **`demo_xg_xa.py` / `xg_xa_chart_demo.html`** — same chart, built from a
  hand-verified snapshot of the top 20 players by combined xG+xA (2026 season,
  500+ minute qualifiers), for the same sandbox-network-access reason as above.
- **`finishing_signal.py`** — the uncertainty and regression-to-the-mean
  math behind the Goals vs. xG tab: how far chance alone can push a player
  from their xG, and how much of an observed gap the shot volume can actually
  support. No network, no ASA specifics — plain numbers in, plain numbers out.
- **`test_finishing_signal.py`** — assertion tests for the above. Run with
  `python3 test_finishing_signal.py` (no pytest, no network). Worth running
  after any change to the stats: a wrong band renders exactly like a right
  one, so the page cannot tell you it's broken.
- **`dashboard_template.py`** — the shared chart library (bar + scatter, tabs,
  tooltips, collision-avoidance) used by every HTML chart. No external
  dependencies (see "why no D3" below).
- **`chart_builders.py`** — the chart-construction logic (picking each
  chart's highlighted story point, converting to per-96 rates, building
  tooltips) for the finishing/creation/shot-quality/team-compare charts,
  shared by both scripts below. See "Keeping this cheap to maintain" for why
  this file exists.
- **`build_dashboard.py`** — combines everything into one tabbed dashboard:
  team xG differential, team xGF-vs-xGA, shot quality, playmaking style,
  player goals-vs-xG, player xG-vs-xA, a Goals Added leaderboard, a
  goalkeeper chart, and a dropdown-driven team roster comparison. Pulls
  live data via `requests` — no LLM involved, safe to automate (see
  "Automating the weekly refresh" below).
- **`demo_dashboard.py` / `dashboard_demo.html`** — the same dashboard, built
  from hand-verified 2026 snapshots (all 16 teams' full xG table, 32 players'
  xG/xA/shots, 15 players' Goals Added by action type, 20 goalkeepers).
- **`run_weekly_update.sh`** / **`run_weekly_update.ps1`** — thin wrappers
  around `build_dashboard.py`, meant to run from cron (macOS/Linux) or Task
  Scheduler (Windows) on your own machine. Also auto-deploys to GitHub
  Pages if you've set that up (see "Automating the weekly refresh" and
  "Hosting on GitHub Pages" below).
- **`.gitignore`** — excludes `.venv/`, `history/`, and other local-only
  files from the GitHub Pages repo, so only the actual site and source code
  get pushed.
- **`statsbomb_data.py`** / **`build_shot_map_chart.py`** / **`shot_map_demo.html`**
  — a real shot map (pitch diagram, shot locations, dot size = xG) built from
  StatsBomb's free open NWSL event data (2018 and 2023 seasons only — that's
  the entirety of StatsBomb's NWSL coverage). Standalone, not a tab on the
  main dashboard yet — see "Round 10" below.
- **`nwslr_data.py`** / **`build_historical_trend_chart.py`** /
  **`historical_trends_demo.html`** — multi-season historical trends
  (2013-2019, the years before ASA's API coverage starts) from the nwslR
  project's public data, read directly with pandas (no R needed). Also
  standalone for now — see "Round 10" below.

## Run it yourself

```bash
pip install requests pandas matplotlib
python nwsl_xg_charts.py --season 2025 --minutes 900
```

This pulls **live, complete** data (all teams, all qualifying players) and
regenerates the three charts + two CSVs fresh. Change `--season` for other
years, `--minutes` to change the player-minutes cutoff, `--top-n` for how many
players to plot.

For the interactive xG-vs-xA chart:

```bash
python build_xg_xa_chart.py --season 2026 --minutes 500
```

Opens as `xg_xa_chart.html` — open it directly in any browser, no server
needed. Re-run any time during the season to refresh with current data.

For the full combined dashboard (all 5 charts, tabbed):

```bash
python build_dashboard.py --season 2026 --minutes 500 --top-n 20
```

## The three starter charts

1. **Team xG differential** — a diverging bar chart (`xG For − xG Against`
   per team). The single fastest way to see who's created/allowed more
   quality chances than their opponents, independent of finishing luck.
2. **Team xG For vs. xG Against** — a scatter/quadrant chart. Teams to the
   right create more high-quality chances; teams higher up (axis inverted)
   concede fewer. Top-right is the "good on both sides" quadrant.
3. **Player Goals vs. xGoals** — a scatter with a 45° reference line, for
   your top-xG players. Above the line = scoring more than the shots
   "deserved" (hot streak or a true finishing skill signal, small samples
   make it hard to tell which); below = underperforming their chances.

## The interactive xG-vs-xA chart

A bubble scatter, x = xGoals, y = xAssists, for every player with 500+
minutes in the given season — the classic "who creates for themselves vs. for
others" view. Hover any bubble for the player's name, team, minutes, xG, xA,
and actual goals. Built in plain SVG + vanilla JS (no CDN dependency), so the
file is fully self-contained and works offline once generated.

**On the markers:** these are round badges with the team abbreviation, not
real logo images. The sandbox that built this couldn't fetch team logos —
Wikimedia Commons' file and API endpoints were both blocked by its network
allowlist, and hot-linking logos felt like the wrong tradeoff for a
trademarked asset anyway. To use real logos on your own machine: save each
team's crest as a small transparent PNG, then fill in the `TEAM_LOGOS` dict
near the top of `build_xg_xa_chart.py` (`"WAS": "logos/washington_spirit.png"`
etc.) — the chart's marker code has a hook to swap in an `<image>` clipped to
a circle wherever a team has an entry. Wikipedia's team infobox crest or each
team's official press-kit page are reasonable sources; save a local copy
rather than hot-linking so the chart stays self-contained.

**Overlap handling:** when players land close enough on xG/xA that their
bubbles would overlap, the chart nudges them apart just enough to stay
readable and draws a thin dashed leader line back to their true data
position — so the layout stays legible without silently lying about anyone's
numbers.

## The combined dashboard

`dashboard.html` (or `dashboard_demo.html`) puts every chart into one page
with tab navigation — a single-page app, not one file per chart. Built the
same way as the other charts: self-contained SVG + vanilla JS, no CDN
dependency (Google Fonts is the one exception — see Typography below — and
it degrades gracefully if it can't load). `dashboard_template.py` holds the
reusable pieces (a generic bar-chart renderer, a generic scatter renderer,
a dropdown-driven roster-comparison renderer, the tab/panel shell) so
adding another chart later is a matter of fetching the data and appending
one more config dict — not writing a new chart from scratch.

Tabs are ordered **League Picture → Team xG Diff. → Team Goals Added →
Shot Quality → Playmaking Style → Goals vs. xG → xG vs. xA → Goals Added →
Goalkeepers → Compare Teammates**: open on the whole league's shape, narrow
to team-level, then player-level creation/finishing findings, the capstone
metric, the goalkeeper picture, and finally the open-ended explorer tab —
Duarte's "what is, then what's the point" structure, with the one
interactive/exploratory tab placed last since it isn't leading with a
single finding.

### Round 13 (2026-08-12): full-league player pool instead of a top-N cut

The user asked whether the dashboard's player-level charts were drawing
from a limited pool and, if so, to broaden it. Turned out the answer was
"yes, but only on the display side" — `build_dashboard.py`'s
`fetch_player_pool()` was already pulling every player above `--minutes`
across all 16 teams (no `team_id` filter), but
`chart_builders.build_finishing_creation_shotquality()` then quietly
sliced that full pool down to the top 20 by combined xG+xA before handing
it to the chart. Playmaking Style had the same problem one level worse —
it was built only from the Goals Added leaderboard's top 15, so a player
with a distinctive dribbling/passing split but a lower overall g+ total
could never appear on it at all.

**What changed:**
- `build_finishing_creation_shotquality()` no longer takes a `top_n` — it
  plots every row it's handed. On the live path, Goals vs. xG, xG vs. xA,
  and Shot Quality now show the full qualifying league (typically 100-250+
  players depending on the minutes floor and time of season) instead of a
  top-20 cut.
- Playmaking Style is now built from every player who qualified for the
  `/players/goals-added` pull, decoupled from the Goals Added bar chart's
  leaderboard cutoff. The Goals Added *bar chart* itself stays capped at
  `--top-n` (default 20) — a ranked leaderboard genuinely reads better at
  ~20 bars than at 150+, so that cap was kept, just no longer leaking into
  the scatter charts.
- `--top-n` now controls only the Goals Added leaderboard length. It used
  to also cap Finishing/Creation/Shot Quality (removed) and, due to a
  pre-existing bug, did *not* actually reach the Goals Added chart either
  (that call was hardcoded to `15` regardless of the flag) — fixed as part
  of this pass.
- New `chart_builders.scatter_display_params(n)`: past 40 points, bubbles
  shrink and the always-on team-abbreviation badge is dropped for every
  point except the highlighted one — otherwise a full-league scatter turns
  into a pile of overlapping 3-letter labels. Everyone else stays
  identifiable via the existing hover tooltip. Verified visually (not just
  "no console errors") with a 140-player mock pool rendered through
  Playwright — screenshots confirmed clean, readable scatter plots at that
  density with the highlighted point still standing out.
- The **demo snapshot** (`demo_dashboard.py` / `dashboard_demo.html` /
  `index.html`) is deliberately unchanged in scope — it still shows its
  original ~20-player hand-verified set, since that's all this sandbox
  could safely verify without a live API connection. The blurb text now
  reads "All 20 players..." instead of "Top 20 players..." (accurate
  either way, just reflects that there's no cut happening), but the
  player count itself doesn't change until a real `build_dashboard.py` run
  against the live API replaces it — see "Still needs the user to do"
  below.

**Still needs the user to do:** get a successful `python build_dashboard.py`
run against the live API (the round-3 ASA outage may or may not still be a
factor — worth just trying it), then treat that output, not the demo
snapshot, as what gets copied to `index.html` and pushed to GitHub Pages.
That's the one step that actually flips the *live, public* dashboard from
the ~20-player demo over to the full league — everything in this round is
already wired up to do that automatically once a live run succeeds.

### Round 11 additions (2026-08-12)

- **Team Goals Added** (new tab) — Goals Added (g+) summed across every
  action type at the team level, net of what the team conceded to
  opponents: a single on-ball-quality number, separate from the shot-based
  xG picture the League Picture/Team xG Diff. tabs already cover. Built via
  `chart_builders.build_team_goals_added_chart()`. The live path
  (`build_dashboard.py`) gets every team in one call to
  `/teams/goals-added` (no `team_id` filter needed); the demo snapshot
  pulled each team individually to stay safe against the bulk-JSON-summary
  reliability issue described below.
- **Playmaking Style is now per-96**, closing a gap flagged in the previous
  round: 4 of 15 players (Racheal Kundananji, Gia Corley, Pietra Tordin,
  Ludmila) were missing individually-verified minutes in the demo snapshot;
  they were fetched this round via
  `/players/xgoals?player_id=X&season_name=2026` (and each one's returned
  `team_id` matched what was already on file — a good cross-check). The
  Goalkeepers tab's per-96 gap in the demo snapshot was deliberately **not**
  closed the same way this round — bulk-pulling `minutes_played` for all 20
  goalkeepers hit the same large-JSON-summary reliability problem described
  in `demo_dashboard.py`'s comments (the shots-value bug further down in
  this README is the same underlying issue, previously on a different
  field). The reliable fix is still running `build_dashboard.py` locally
  against the live API and using its output as the new demo snapshot.
- The three round-1 static matplotlib charts (`nwsl_xg_charts.py`) and the
  standalone `build_xg_xa_chart.py` bubble chart were restyled to match the
  Design Guidelines doc for the first time — insight-led titles computed
  from the data, one highlighted story point per chart, everything else
  muted to gray, and a best-effort Karla/Space Grotesk typeface match
  (falls back to your system's default sans-serif / matplotlib's DejaVu
  Sans if those fonts aren't installed locally — same idea as the HTML
  dashboard's font fallback, just for a static image instead of a browser).
  A couple of real label-overlap bugs were caught and fixed in this pass
  (a bar annotation colliding with its own axis label, and ~20 player names
  piling up unreadably on a dense scatter) — see the code comments in
  `nwsl_xg_charts.py` for the specifics if you're extending it further.

### New charts this round

- **Shot Quality** (`Shots Taken vs. xG per Shot`) — the same top-N player
  pool, but shot volume against average shot quality (xG per shot). Answers
  "who's taking a lot of low-quality shots vs. a few great ones," which
  neither the Goals-vs-xG nor xG-vs-xA tab shows on its own.
- **Playmaking Style** (`Goals Added: Dribbling vs. Passing`) — ASA's Goals
  Added metric splits into six action-type categories (dribbling, fouling,
  interrupting, passing, receiving, shooting); this isolates two of them to
  show *how* a player creates value, not just how much.
- **Goalkeepers** (`Shots Faced vs. Goals Saved Above Expected`) — from the
  `/goalkeepers/xgoals` endpoint (shots faced, goals conceded, xG on target
  faced). Goals saved above expected = xG faced minus goals actually
  conceded; positive means outperforming what an average keeper would allow
  given the same shots.
- **Compare Teammates** — the one non-static tab: pick a team from the
  dropdown, pick a metric (Goals Added, xGoals per 96, xAssists per 96,
  Goals, Shots, Minutes), and the bar chart and highlighted-leader caption
  redraw entirely client-side in JavaScript. See `drawTeamCompare()` in
  `dashboard_template.py` — every other chart type on this dashboard is
  static/precomputed at build time; this one is genuinely interactive. Every
  team has 2+ players (`build_dashboard.py`'s live version pulls a full
  roster per team; the demo adds one verified extra player to whichever
  teams needed it to reach 16/16 coverage).

**Rate stats, not season totals.** The Goals-vs-xG and xG-vs-xA charts (and
the xGoals/xAssists options in Compare Teammates) show **xG/96** and
**xA/96** — each player's total divided by their minutes played, scaled to
a 96-minute match — instead of raw season totals. This is what makes a
player with 500 minutes comparable to one with 1900: a raw-total chart would
always favor whoever's played the most, which isn't the same thing as who's
best. Goals is shown per-96 alongside xG on the Goals-vs-xG chart for the
same reason — the chart's 45° reference line only means something if both
axes are on the same footing. Shot Quality's xG-per-shot metric was already
a rate (per shot, not per minute) so it didn't need this conversion.

**Highlighting one story point per chart.** Each chart config can mark one
data row `"highlight": True` (see `build_dashboard.py`'s `pick_*`-style
helpers — `best_both`, `extreme`, `best_finisher`, `most_balanced`, `leader`
— which find that row from whatever data comes back, so re-running later in
the season highlights a different team/player as the standings change, not
whoever was on top the day this was written). The highlighted mark keeps its
normal palette color and gets a short static text annotation on the chart
itself (not hidden behind a hover); every other mark recedes to muted gray.
This is the direct implementation of the Design Guidelines' "preattentive
attributes for focus" rule — color marks the one point that matters, nothing
else competes for it.

**Typography.** Per the project's Design Guidelines doc, the dashboard uses
two Google Fonts: Karla for body text, axis labels, tooltips, and table-style
content, and Space Grotesk for headings and titles. Both are loaded via a
standard Google Fonts `<link>` in `dashboard_template.py`'s `<head>`, with a
system-sans fallback stack (`var(--font-body)` / `var(--font-head)`) so the
page still looks fine if that request is ever blocked — which is exactly
what happens in the sandbox this kit was built in; the fonts load fine on a
normal internet connection.

**Why no D3 or other charting library:** the first version of the xG-vs-xA
chart loaded D3 from a CDN, which works fine once you open the file in a
normal browser — but broke while *verifying* the chart in the cloud sandbox
that built this kit, because the sandbox's headless browser is behind the
same locked-down network as everything else there. Rewriting it as
dependency-free vanilla JS fixed that, and as a side effect makes the
shipped file more portable for you too: no CDN outage or ad-blocker can ever
break it.

## Round 10: StatsBomb shot map and nwslR historical trends (2026-08-12)

Two more data sources beyond ASA, wired in as real working code rather than
just documented as options — the "shot maps" and "multi-season trends"
items that had been sitting in Natural Next Steps since round 1, closed by
going to sources ASA's API simply doesn't have.

- **StatsBomb Open Data** (`statsbomb_data.py`) — free, GitHub-hosted,
  shot-by-shot event data with pitch coordinates. ASA's API has no
  shot-location field at all, so a real shot map was never going to come
  from ASA data. Coverage is narrow — StatsBomb has published exactly two
  NWSL seasons, **2018 and 2023** — but where it's available, it's the real
  professional data model (the same one StatsBomb sells to clubs), not an
  aggregate. Pulled via a targeted `git sparse-checkout` of individual files
  rather than a full clone (the repo holds many other competitions) or the
  `statsbombpy` PyPI wrapper.
- **`build_shot_map_chart.py`** → `shot_map_demo.html` — a pitch diagram
  (shot locations, dot size = xG, filled = goal) for the 2023 NWSL
  Championship Final by default; `--match-id`/`--season`/`--list-matches`
  picks any other 2018 or 2023 match. The headline is computed dynamically
  (the goal with the lowest xG — currently Esther González's 46th-minute
  winner in the Final, a 7% chance).
- **nwslR** (`nwslr_data.py`) — historical NWSL data covering **2013
  (league inception) through 2019**, read straight from the R package's
  `data-raw/` CSV/Excel source files with pandas — no R installation
  needed. Includes three now-defunct clubs (Boston Breakers, FC Kansas
  City, Western New York Flash) that predate the league's current 16-team
  footprint.
- **`build_historical_trend_chart.py`** → `historical_trends_demo.html` —
  two tabs: league-wide goals scored per season 2013-2019 (peak season
  highlighted, computed live), and a season-picker bar chart of every
  team's goals that year.
- **New shared chart types** in `dashboard_template.py`: `drawLine` (single-
  series line chart, one point per season), `drawSeasonCompare` (the same
  dropdown-driven pattern as `drawTeamCompare`, but the picker selects a
  season instead of a team), and `drawShotMap` (a pitch diagram in
  StatsBomb's 0-120×0-80 coordinate system, shots normalized to always
  attack the same goal regardless of which end they were actually taken
  at). `drawDivergingBar` also gained an opt-in `oneSided` flag — for
  data that's never negative (like season goal totals), it skips the
  diverging ±max axis instead of showing pointless negative-axis
  gridlines, which is exactly the kind of chartjunk the Design Guidelines
  doc warns against.
- **These two charts are standalone HTML files, not new tabs on the main
  dashboard** — a deliberate scope call, since they pull from entirely
  different infrastructure (git sparse-clone vs. the ASA REST API) and
  aren't on the same weekly-refresh cadence (both sources are static).
  Merging them into `dashboard_demo.html`'s tab order is a natural next
  step (see "Where to go next") once there's a decision on where they fit
  in the "what is → what could be" sequencing rule.

## Round 22: penalties out, uncertainty in, and a Methods tab (2026-08-13)

Prompted by asking what an elite sports-data analyst would say the dashboard
was missing. The answer was not "more charts" — it was that every number on
the page was a bare point estimate from one model, with no statement of how
much of it was chance and no way for a reader to check any of it. Three
changes, in order of how much they move the needle.

### 1. Penalties are out of every finishing figure (npxG)

A penalty is roughly 0.75 xG and it goes to whoever the team designates, not
to whoever finishes well. Any finishing or shot-quality ranking that leaves
them in is partly a ranking of who takes penalties.

ASA doesn't publish an npxG field, but `/players/xgoals` and `/teams/xgoals`
accept a `shot_pattern` filter, so the penalty component is obtainable by
asking the same endpoint the same question with `shot_pattern=Penalty` and
subtracting — one extra call, not one per player. Goals vs. xG, Shot Quality
and the xG axis of xG vs. xA are all non-penalty now.

The six patterns (`Regular`, `Fastbreak`, `Corner`, `Free kick`, `Set piece`,
`Penalty`) are mutually exclusive and exhaustive. Verified live on 2026-08-13
for one team: the six filtered calls summed to exactly the unfiltered row
(235 shots / 25.3197 xG = Regular 170/17.4848 + Corner 42/3.4250 +
Fastbreak 10/1.6420 + Set piece 7/0.3195 + Free kick 3/0.1693 +
Penalty 3/2.2793). That identity is what makes open play derivable as
"total minus dead balls minus penalties", which is how the new tab below
gets away with four extra calls instead of six.

### 2. A chance band and a regressed estimate on Goals vs. xG

Finishing over expectation is one of the slowest-stabilising quantities in
the sport. Over a partial season most players' over- or under-performance is
indistinguishable from a league-average finisher having a good or bad run,
and the old chart rendered those two cases identically — then wrote a
headline about whoever's raw margin was largest, which is a machine for
generating findings that regress the following month.

Now:

- **The shaded ribbon** is where a perfectly average finisher lands 95% of
  the time given that many shots at that quality. Inside it, a gap is not
  distinguishable from luck.
- **`± chance` and `z`** in the table give each player's own exact interval,
  rather than one read off the ribbon.
- **`Regressed`** is an empirical-Bayes estimate: the raw margin times the
  share of it the shot volume can support. The population variance of true
  finishing skill is *estimated from the pool* by shot-weighted method of
  moments, so the strength of the regression is measured, not chosen. On the
  demo snapshot it comes out at exactly zero — the spread across those 20
  players is fully explained by the randomness of 802 shots — and the tab
  says so in its headline instead of crowning the luckiest player.
- **The story point is the largest regressed margin**, not the largest raw
  one.

**This tab is now in season totals, not per-96** — a deliberate exception to
the per-96 convention from rounds 6 and 9, made for a specific reason. Goals
minus xG is not a rate; it is an accumulation whose reliability is the point,
and the noise in it depends on shots taken, not on minutes. In count space
the band is exact for every player at once. On a per-96 axis it could only
ever be drawn for one representative player — precisely the "roughly right
for somebody" this round exists to remove. Rate views of the same players
still live on xG vs. xA, Shot Quality and Compare Teammates.

### 3. Open Play vs. Set Pieces, and a Methods & Data tab

**Open Play vs. Set Pieces** splits team xG by how the chance began. League
Picture and Team xG Diff. are all-situations, which conflates two different
things: dead-ball output comes from a handful of rehearsed routines and
swings hard season to season, while open-play xG is the more stable read on
how a side actually plays. The story point is the team whose open-play rank
and dead-ball rank disagree most — a side propped up by set pieces is a
likelier regression candidate than the same record built in open play.

**Methods & Data** is the tab that makes the rest checkable: which xG model
(and a warning that ASA's numbers will not reconcile with Opta- or
FBref-derived ones), which endpoints, every filter and threshold, what each
derived quantity means, the regression strength actually used in this
build, an explicit list of known limitations, a build timestamp, and CSV
exports of the underlying rows. The CSVs are embedded in the page and
offered via a Blob, so they work on a static host with no backend and keep
working offline.

Every page now carries a **"Built <date>"** stamp in the footer.

### Known limitations, stated rather than hidden

The Methods tab lists these on the page, and they are the honest next round:
nothing is adjusted for score state, venue or opponent strength (ASA's
`/teams/xgoals` exposes `home_adjusted` and `even_game_state` flags this
build doesn't use yet); everything is a season aggregate with no rolling form
window or match-by-match series; player scatters put every position on shared
axes without position-relative percentiles; and there is no second xG source
to triangulate against.

## Automating the weekly refresh

`build_dashboard.py` already pulls **live** data — the only reason it wasn't
running on a schedule before now is that someone had to type the command.
`run_weekly_update.sh` (macOS/Linux) and `run_weekly_update.ps1` (Windows)
fix that: they're thin wrappers that call `build_dashboard.py` with your
usual settings, save a dated snapshot to `history/`, and are meant to be
triggered by your operating system's own scheduler — cron or Task
Scheduler — not by Claude.

**Why it has to run on your machine, not in the cloud.** The API calls
happen over the plain `requests` library, which needs a normal outbound
internet connection. The cloud sandbox this kit was *built* in has a
locked-down network that blocks exactly that kind of direct call (confirmed
again while building this feature) — so a Claude-side schedule would have
to fall back to a much slower, less reliable path (fetching one page at a
time through a web-fetching tool, the same approach that produced the shots
value bug described further down in this README). Running the real script
on your own computer sidesteps all of that: it's the exact same code path
you already tested manually, it takes a few seconds, and it costs nothing.

**Setup, macOS/Linux:**
```bash
cd nwsl_xg_starter
python3 -m venv .venv && source .venv/bin/activate && pip install requests
crontab -e
# add this line (every Monday 7am; adjust as you like):
0 7 * * 1 /full/path/to/nwsl_xg_starter/run_weekly_update.sh >> /full/path/to/nwsl_xg_starter/weekly_update.log 2>&1
```

**Setup, Windows:** open Task Scheduler → Create Task → a weekly trigger →
action "Start a program" running `powershell.exe` with arguments
`-ExecutionPolicy Bypass -File "C:\path\to\run_weekly_update.ps1"`. Full
details are in the comment block at the top of that file.

Either script overwrites `dashboard.html` in place, keeps the last 12
weekly snapshots in `history/` so you can see how the picture changed over
time (open any of those the same way you'd open `dashboard.html`, no server
needed), and — once you've done the one-time GitHub Pages setup below —
also pushes the update so your hosted, browser-accessible copy stays
current. Your machine (or whatever server you point this at) needs to be on
and connected at the scheduled time; if it's asleep, that week's refresh
just doesn't happen until the next time you're online and re-run it
manually. If you'd rather not manage cron/Task Scheduler yourself, ask and
a simpler once-a-week reminder can be set up instead — you'd still run the
script yourself, just with a nudge.

## Keeping this project cheap to maintain

Two changes made in the same round as the automation above, aimed
specifically at reducing how much Claude time/tokens any future update to
this kit costs:

1. **`chart_builders.py` is now the single source of truth** for the
   finishing/creation/shot-quality/team-compare charts. Before this, that
   logic was written out separately in `build_dashboard.py` (live) and
   `demo_dashboard.py` (snapshot) — every feature change (like the per-96
   conversion) meant editing both, in sync, by hand. Now both files just
   hand a plain list of player rows to the same functions. A future request
   like "also show minutes played on hover" is one function edit instead of
   two, and the two dashboards can't quietly drift apart from each other.
2. **Prefer running `build_dashboard.py` locally for anything data-related.**
   The single biggest cost driver in this project so far has been pulling
   fresh data *through a Claude session* in a network-locked sandbox — that
   requires many individual web-fetch calls (one per record, to keep
   accuracy up), each one costing tokens, and it's exactly how the shots-
   data bug found this round crept in in the first place (a bulk fetch
   transcribed one field wrong across many rows). Running the real script
   locally does the same fetch in about 3 seconds, for free, with zero
   transcription risk, because it's just Python talking to an API. Save
   Claude sessions for things that actually need judgment — new chart
   ideas, design changes, restyling — not routine data refreshes.

If you want a chart-logic change applied to a future week's data without
opening a Claude session at all, that's exactly what `chart_builders.py`
and the local scripts are for: edit `chart_builders.py` yourself (it's
plain, commented Python, no framework) and re-run `build_dashboard.py`.

## Hosting on GitHub Pages (browser access from anywhere)

`dashboard.html` is already a complete, self-contained static site — no
server, no database, no build step. That means hosting it is just a matter
of putting the file somewhere public. GitHub Pages is free, requires no
credit card, and — once set up — plugs directly into the weekly script
above, so the live URL refreshes itself every week along with the local
file. This is a one-time setup, done on your own machine (not in a Claude
session, since creating accounts and pushing under your identity isn't
something Claude does on your behalf):

**1. Create a free GitHub account**, if you don't already have one, at
github.com — this is the one step nobody else can do for you.

**2. Create a new repository.** On github.com, click "New repository."
Name it something like `nwsl-dashboard`, leave it **Public** (GitHub Pages'
free tier requires a public repo unless you're on a paid GitHub plan — this
is fine here, there's nothing sensitive in this project, just public NWSL
stats), and don't initialize it with a README (this folder already has one).

**3. Connect this folder to that repository.** From a terminal, inside the
`nwsl_xg_starter` folder:
```bash
git init
git add build_dashboard.py chart_builders.py dashboard_template.py demo_dashboard.py \
        build_xg_xa_chart.py nwsl_xg_charts.py demo_snapshot.py demo_xg_xa.py \
        run_weekly_update.sh run_weekly_update.ps1 README.md .gitignore
cp dashboard.html index.html
git add index.html
git commit -m "Initial NWSL dashboard"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/nwsl-dashboard.git
git push -u origin main
```
(Replace `YOUR-USERNAME` with your actual GitHub username. If `git push`
asks for a password, GitHub no longer accepts your account password there —
either use the GitHub CLI (`gh auth login`, then retry) or set up a
[Personal Access Token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
as your password when prompted. Both are one-time steps.)

**4. Turn on GitHub Pages.** On the repository's GitHub page: Settings →
Pages (left sidebar) → under "Build and deployment," set Source to "Deploy
from a branch," Branch to `main` and folder to `/ (root)` → Save.

**5. Wait about a minute**, then visit `https://YOUR-USERNAME.github.io/nwsl-dashboard/`
— that's your dashboard, live, reachable from any browser: your phone,
another computer, anywhere. Bookmark it.

**After that, you're done** — `run_weekly_update.sh`/`.ps1` already detect
this git setup automatically (see the "GitHub Pages auto-deploy" step each
script added this round) and will `git push` the refreshed dashboard every
time they run, so the URL above stays current without you touching it
again. If you'd rather deploy by hand some weeks, `cp dashboard.html
index.html && git add index.html && git commit -m "update" && git push`
does the same thing the script does.

**What's public:** the whole repository is visible to anyone with the link
(that's how the free tier works) — the Python source, the chart logic, and
the dashboard itself. Nothing in this project is sensitive; it's all public
NWSL statistics and open-source-style code, so this is a reasonable
tradeoff for free, zero-maintenance hosting. If that ever changes (e.g. you
want this private), that requires a paid GitHub plan, or a different host
like Netlify/Vercel which offer free private-ish previews with more setup.

## From dashboard to webapp

You mentioned wanting to build this out into an actual webapp eventually —
here's the honest gap between what you have now and that:

1. **This already *is* the client-side half of a webapp.** `dashboard.html`
   is a single-page app: HTML/CSS/JS, no build step, no framework. That part
   doesn't need to be rebuilt, just extended (more chart types, filters,
   routing between views if it grows beyond tabs).
2. **The missing piece is live data in the browser itself, and CORS is the
   real blocker here (round 11 update).** Right now the Python script
   fetches data and bakes it into the HTML at *build* time. A real webapp
   would fetch from the ASA API at *page-load* time instead, via `fetch()`
   in the browser. This round couldn't test that directly — the cloud
   sandbox's own network is blocked from the ASA API entirely, and its
   Chrome-extension bridge to a real browser wasn't connected this session
   — but a web search turned up a filed, closed GitHub issue on ASA's own
   JS wrapper repo asking for exactly this: [itscalledsoccer-js issue #2,
   "CORS policy prevents requests from static websites"](https://github.com/American-Soccer-Analysis/itscalledsoccer-js/issues/2).
   The issue is closed but there's no visible maintainer comment confirming
   a fix, so treat this as "probably still blocked, unconfirmed" rather
   than a hard no. **To find out for certain**, open any page in your
   browser, open dev tools' Console, and run:
   ```js
   fetch("https://app.americansocceranalysis.com/api/v1/nwsl/teams")
     .then(r => r.json()).then(console.log).catch(console.error)
   ```
   A CORS block shows up as a red network error mentioning
   "Access-Control-Allow-Origin" — if you see that, the API can't be called
   directly from browser JS on a different origin, and you'd add a thin
   backend (a few lines of Flask/Express, or a small Cloudflare
   Worker/Vercel serverless function) that proxies the ASA API and adds the
   CORS header yourself. If the `fetch()` succeeds instead, you're clear to
   call the API directly from the browser with no backend at all.
3. **Hosting**: already done — see "Hosting on GitHub Pages" above. The
   same GitHub Pages setup keeps working if this ever grows into a real
   webapp with a thin backend; you'd just add the backend somewhere with
   server support (Pages itself is static-only).
4. **If it grows past a handful of charts**, that's the point to reach for
   a small framework (even something as light as vanilla JS with a router,
   or Vite + a UI library) rather than one more hand-written tab. Not needed
   yet — five tabs of plain SVG is genuinely fine.

## Where to go next

- **API docs:** https://app.americansocceranalysis.com/api/v1/__docs__/
  (also covers `goals_added` — ASA's possession-value metric — and `xpass`)
- **Official wrapper (optional, adds fuzzy name search):**
  `pip install itscalledsoccer` /
  `install.packages("itscalledsoccer")` —
  https://github.com/American-Soccer-Analysis/itscalledsoccer-r
- **R-native NWSL datasets:** the `nwslR` package —
  https://github.com/adror1/nwslR — useful for historical play-by-play and
  roster data that isn't in the ASA API. Already wired in, see "Round 10"
  above.
- **StatsBomb Open Data** — free, shot-by-shot event data (2018 and 2023
  NWSL seasons only) — https://github.com/statsbomb/open-data. Already
  wired in, see "Round 10" above.
- **Team-level Goals Added is done** (round 11, see above) — this kit
  previously only had player-level.
- **Shot maps are done, via StatsBomb, not ASA** (round 10) — worth being
  precise about which data source: ASA's API genuinely has no
  shot-location field at all (confirmed by checking `itscalledsoccer`'s
  full method list, Python and R — no shot-coordinate or play-by-play
  method anywhere in the package), so a shot map was never going to come
  from the ASA-based scripts in this kit. StatsBomb's open data does have
  shot coordinates, which is what `build_shot_map_chart.py` uses — but
  StatsBomb has only published two full NWSL seasons (2018, 2023), so this
  won't extend to arbitrary recent matches the way the ASA-based charts do.
- **An xG-race (cumulative xG during a live match) chart is still not
  buildable from either source** — StatsBomb's event data has shot-level
  detail *within* a match (so this is technically the closer source), but
  wasn't built this round; `drawLine` (round 10) could support it with
  multiple points per match instead of one point per season if a future
  round wants to build it from `statsbomb_data.py`'s per-match events.
  Separately, confirmed (round 11) that ASA's own `/games/xgoals` endpoint
  only has final match xG totals, not a shot-by-shot timeline, so that
  source specifically can't do this at all.
- **Multi-season trends now exist two ways**: nwslR covers 2013-2019 (see
  "Round 10" above, already built into `historical_trends_demo.html`), and
  separately, ASA's own API was confirmed (round 11) to cover **2021
  through the current season** via `/games` and the xgoals/goals-added
  endpoints — unexplored territory for a team or player you're tracking
  year over year within that more recent window.
- A **match-level "results vs. xG" view** using ASA's `/games` +
  `/games/xgoals` together (e.g. which results most over/underperformed
  the underlying numbers, for any season 2021+) is a scoped, ready-to-build
  next chart based on the round-11 API investigation above — not built
  yet, but the endpoints and fields needed are confirmed.
- **Merge the round-10 shot map and historical trends charts into the main
  `dashboard_demo.html`/`index.html`** instead of leaving them as separate
  standalone files (see "Round 10" above for why they were left standalone
  for now) — needs a decision on tab placement.

## Note on the sandbox that built this

The cloud environment used to put this kit together has locked-down outbound
network access (only an allowlist of package registries), so it couldn't call
`app.americansocceranalysis.com` or `pip install itscalledsoccer` directly.
The preview PNGs were built from a small hand-verified data snapshot instead.
Your own machine won't have that restriction — `nwsl_xg_charts.py` will pull
live data normally.


## Weekly automation on GitHub Actions

`.github/workflows/weekly.yml` runs the refresh every Tuesday at 15:00 UTC,
and on demand from the Actions tab. It replaces the local cron job, which
only fired if the laptop happened to be awake.

The order of its steps is the contract:

1. **Unit tests** against the synthetic season — if these fail the problem is
   the code, not the league, and no API call is spent finding that out.
2. **Warehouse load** — pull the live API into `raw`, then `dbt build`: 23
   models and 41 data tests, in dependency order.
3. **Dashboard rebuild** — only reached if every data test passed.
4. **Publish** — `index.html` committed back to the repo for GitHub Pages.

A failing data test stops the job at step 2. The dashboard is not rebuilt,
`index.html` is not touched, and the live site keeps serving last week's
numbers: stale and correct rather than fresh and wrong. Each run also uploads
its raw API payloads and dbt's `run_results.json` as artifacts, kept 90 days —
so any week's numbers can be re-examined later, by anyone, without taking the
maintainer's word for it.

**Turn off the local cron once this is running.** Two publishers pushing
`index.html` to the same branch will collide. In your own Terminal:

    crontab -l                 # note the NWSL lines
    crontab -e                 # delete or comment the run_weekly_update.sh line

`run_weekly_update.sh` still works for manual local runs; it just should not
be scheduled at the same time as the workflow.
