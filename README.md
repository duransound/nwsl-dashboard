# NWSL xG Starter Kit

A minimal, working starting point for building xG (Expected Goals) charts from
[American Soccer Analysis](https://www.americansocceranalysis.com/) data — the
same public API that powers ASA's own site and the `itscalledsoccer` R/Python
packages professionals use.

The dashboard (below) follows this project's **Design Guidelines** doc — a
blend of IBM Carbon / NASA's 1976 Graphics Standards Manual (restraint,
one consistent system, color as meaning not decoration) and data-storytelling
rules from Duarte, Knaflic, and Tufte (lead with the insight, emphasize one
point per chart, cut chartjunk). Concretely: every chart title states a
finding rather than a metric name, exactly one bar/bubble per chart is
highlighted in the palette's blue/red while the rest recede to gray, and
tabs are ordered from the league-wide picture down to the specific finding
rather than presented as equally-weighted views.

## Files

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

Tabs are ordered **League Picture → Team xG Diff. → Shot Quality →
Playmaking Style → Goals vs. xG → xG vs. xA → Goals Added → Goalkeepers →
Compare Teammates**: open on the whole league's shape, narrow to team-level,
then player-level creation/finishing findings, the capstone metric, the
goalkeeper picture, and finally the open-ended explorer tab — Duarte's
"what is, then what's the point" structure, with the one interactive/
exploratory tab placed last since it isn't leading with a single finding.

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
2. **The missing piece is live data in the browser itself.** Right now the
   Python script fetches data and bakes it into the HTML at *build* time. A
   real webapp would fetch from the ASA API at *page-load* time instead, via
   `fetch()` in the browser — which means checking whether ASA's API sends
   CORS headers that allow browser-side requests from an arbitrary origin
   (this wasn't testable from this sandbox; check by opening browser dev
   tools' Network tab against a `fetch()` call once you're set up locally).
   If it doesn't allow that, you'd add a thin backend (a few lines of Flask/
   Express) that proxies the ASA API and adds the CORS headers yourself.
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
  roster data that isn't in the ASA API.
- Natural next charts: xG race chart (cumulative xG over a match/season,
  line chart), shot maps (needs shot-location data, a separate ASA endpoint),
  team-level Goals Added (this kit only did player-level), multi-season
  trends for a team or player you're tracking.

## Note on the sandbox that built this

The cloud environment used to put this kit together has locked-down outbound
network access (only an allowlist of package registries), so it couldn't call
`app.americansocceranalysis.com` or `pip install itscalledsoccer` directly.
The preview PNGs were built from a small hand-verified data snapshot instead.
Your own machine won't have that restriction — `nwsl_xg_charts.py` will pull
live data normally.
