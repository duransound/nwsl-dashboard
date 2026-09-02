# The warehouse layer

A DuckDB warehouse underneath the dashboard. Nothing that already works was
changed — `build_dashboard.py`, `chart_builders.py`, and the weekly script are
untouched. This is a parallel path you can move charts onto one at a time.

```
pip install duckdb
python nwsl_warehouse.py load --season 2026 --dump-raw raw_snapshots/
python nwsl_warehouse.py tables
python test_warehouse.py
```

That first command needs real internet. The ASA API is unreachable from both
the Claude cloud sandbox and the desktop bridge, so every number below was
verified against `warehouse_fixture.py` — a synthetic season built to
reproduce each live-data quirk this project has actually been bitten by.
`--fixture` loads it, and needs no network at all.

---

## Why this is worth the trouble

Right now a fetch function calls the API, reshapes the response in Python, and
drops the response on the floor. That is fine until a number looks wrong. Then
the only way to find out what the API actually said is to call it again and
hope it says the same thing — and by then the evidence is gone.

Round 15 is the case in point. Three bugs in a row, each one a wrong
assumption about a response shape, each one only discoverable by triggering it
live and reading a traceback. With the raw payload kept on disk, all three
would have been a `SELECT` away:

```sql
SELECT record FROM raw.asa_records
WHERE endpoint = 'players/xgoals' LIMIT 1;
```

That is the actual argument for a warehouse. Not speed, not scale — **the
input is still there tomorrow.**

---

## The three layers

```
ASA API
   │
   ▼
raw.asa_records      append-only, JSON verbatim, never edited
   │
   ▼
stg.*                typed, normalized — every API quirk handled exactly once
   │
   ▼
dw.*                 dimensions, facts, rates, qualification
   │
   ▼
chart_builders.py    unchanged
```

The discipline that makes it work is that each layer is allowed to do one
thing. Staging may not aggregate. Marts may not parse JSON. When a number is
wrong you know which file to open before you open anything: a wrong *value* is
staging, a wrong *total* is marts.

### `raw` — the landing zone

One row per record the API returned, with the JSON kept as JSON:

| load_id | endpoint | season | variant | fetched_at | record |
|---|---|---|---|---|---|

`variant` is the filter that produced the row — `Penalty` for the
`shot_pattern` call, a position for the goals-added calls. Storing it means one
endpoint can answer several questions without a table per question, and the
npxG subtraction becomes a join instead of a second network call.

`raw.loads` records each run. Views read through `raw.current_load`, which only
sees loads that *finished*. That one join is what makes a failed Tuesday safe:
if `/players/xgoals` dies mid-load, the loader raises, `finished_at` is never
stamped, and the dashboard keeps showing last week's correct numbers instead of
half a league.

### `stg` — normalization, once

Every quirk that has ever cost this project a round is handled here and only
here:

```sql
-- /players/xgoals returns team_id as a LIST; /teams/xgoals returns a string
CASE WHEN json_type(record->'$.team_id') = 'ARRAY'
     THEN record->>'$.team_id[0]'
     ELSE record->>'$.team_id' END AS team_id

-- minutes_played on some endpoints, minutes on others
COALESCE(TRY_CAST(record->>'$.minutes_played' AS DOUBLE),
         TRY_CAST(record->>'$.minutes'        AS DOUBLE)) AS minutes

-- games played has appeared under three names
COALESCE(TRY_CAST(record->>'$.count_games'  AS INTEGER),
         TRY_CAST(record->>'$.games'        AS INTEGER),
         TRY_CAST(record->>'$.games_played' AS INTEGER)) AS games
```

Note `TRY_CAST`, not `CAST`. `TRY_CAST` returns `NULL` where `CAST` would
raise. That is the right choice at this boundary: one renamed field should
degrade a column, not abort a season.

The nested `goals-added` shape gets unnested rather than summed:

```sql
FROM (
    SELECT season, record, unnest(json_extract(record, '$.data[*]')) AS action
    FROM   raw.current_records
    WHERE  endpoint = 'teams/goals-added'
)
```

One row per team per action type. The mart sums it *and* pivots it, so the
Goals Added leaderboard and the Playmaking Style scatter come from one table
instead of two fetches.

### `dw` — the layer the charts read

Three prefixes, and they are the vocabulary a club's stack will already use:

| prefix | means | example |
|---|---|---|
| `dim_` | a thing you slice **by** — descriptive | `dim_team`, `dim_player` |
| `fct_` | a thing you **measure**, at a stated grain | `fct_player_season` |
| `mart_` | built for one consumer — rates, flags, rankings | `mart_player_rates` |

**Grain is the word to hold onto.** The grain of a table is what one row means.
`fct_player_season` is one row per player per season. `fct_player_goals_added`
is one row per player per season *per action type*. Join those two carelessly
and every player total gets multiplied by six, and nothing in the chart will
look obviously wrong — it will just be six times too big.

Most warehouse bugs are grain bugs. When a number is off by a suspiciously
round multiple, that is the first place to look. `test_warehouse.py` has a
dedicated check for exactly this.

---

## What the first live load found

The load ran clean — 1,970 records, 240 qualified players — and immediately
surfaced three things about the ASA API that the existing pipeline gets wrong
or leaves on the table.

**1. `team_id` can hold more than one club, and `[0]` is not "current".**
Six players in 2026 changed clubs mid-season and come back with a two-element
array and every metric summed across both. `build_dashboard.py`'s round-15
comment calls `[0]` "the first (only observed) element" — the data says
otherwise.

**The array's order carries no reliable meaning.** It is not chronological —
Yazmeen Ryan reads `["DEN","HOU"]` on a Houston → Denver move — and once the
per-club splits arrived it turned out not to be minutes-ordered either. Across
all six, `[0]` names the club they played *more* for in three cases and *less*
in three:

| player | array | minutes, by club | is `[0]` the main club? |
|---|---|---|---|
| Ally Sentnor | `["KC","LA"]` | KC 1070 · LA 1009 | yes |
| Yazmeen Ryan | `["DEN","HOU"]` | DEN 1977 · HOU 42 | yes |
| Sarah Schupansky | `["NJY","BOS"]` | NJY 639 · BOS 33 | yes |
| Lilly Reale | `["NJY","BOS"]` | BOS 903 · NJY 629 | **no** |
| Brooklyn Courtnall | `["SD","BAY"]` | BAY 849 · SD 37 | **no** |
| Kennedy Fuller | `["LA","BAY"]` | BAY 937 · LA 762 | **no** |

So there is no array-position rule to fall back on — including the
minutes-descending one this document claimed before the splits were loaded.

The fix isn't a better guess. Adding a `team_id` filter makes ASA return the
**per-club split**, and the parts reconcile to the whole exactly:

```
Sentnor, unfiltered   2079 min   64 shots   5.6834 xG
  team_id=KC          1070 min   26 shots   2.8846 xG   (ST)
  team_id=LA          1009 min   38 shots   2.7988 xG   (AM)
```

The loader now issues those calls automatically for whoever needs them — two
per transferred player, twelve on this load — and `dw.mart_primary_team`
picks the club with the most minutes from real data. `dw.dq_multi_team`
carries a `reconciles` column that goes false the moment a split stops adding
up. Note also that the position differs per club: Sentnor is a striker at
Kansas City and an attacking midfielder at Angel City, which the aggregate row
cannot express at all.

One more shape variation while you're here: on the team-filtered rows,
`team_id` comes back as a **plain string**. Same field, third shape.

**2. `general_position` is on the row.** All 245 of them. `fetch_position_gaps()`
makes eight separate filtered calls per run precisely because this was
"never confirmed to be present" — that can now be one call.

**3. Four fields you aren't using.** `xplace` (ASA's shot-placement component
— finishing skill net of *where* the ball went, a sharper story than
goals-minus-xG), `shots_on_target`, `points_added`, and `xpoints_added`. All
staged now, none charted yet.

---

## SQL you will actually need here

**`COALESCE(a, b, c)`** — first non-NULL. The honest version of a `.get()`
chain: it reads as a rule rather than as a defensive accident.

**`NULLIF(x, 0)`** — returns NULL when `x` is 0. This is the divide-by-zero
guard on every per-96 rate:

```sql
xgoals / NULLIF(minutes, 0) * 96 AS xg96
```

A zero-minutes player yields NULL, which plots as absent. Without it you get
infinity, and one infinity takes the axis of the whole scatter with it.

**`GREATEST(x, 0)`** — the floor under npxG. The unfiltered and penalty calls
are independent snapshots; a match finishing between them can leave a penalty
in one and not the other, and a negative npxG would quietly poison every rate
downstream.

**`LEFT JOIN` vs `JOIN`** — the difference is what happens to rows with no
match. `fct_player_season` LEFT JOINs the penalty response because most players
have no penalty row, and *absent means zero, not unknown*. It inner-joins
`dim_player` because a player with no identity is a real problem worth
surfacing.

**`CASE WHEN ... THEN x END` inside `SUM()`** — a pivot. This turns the action
breakdown into columns without a second scan or a self-join:

```sql
SUM(CASE WHEN action_type = 'Dribbling' THEN goals_added_above_avg END) AS ga_dribbling
```

No `ELSE` clause, so non-matching rows contribute NULL, which `SUM` skips.

**CTEs (`WITH x AS (...)`)** — name an intermediate result instead of nesting
subqueries. `mart_qualification` uses one to compute the league median games
before applying it as a fallback. Read a CTE chain top to bottom like a
paragraph.

**`CROSS JOIN` a one-row view** — how the parameters get in. `dw.params` always
returns exactly one row, so cross-joining it attaches the thresholds to every
row without a correlated subquery.

---

## The qualification rule, in SQL

`qualification.py` says: a player qualifies on `minutes_per_game × their own
team's games played`, with the league median as a fallback and a flat number as
an escape hatch. That whole rule is now `dw.mart_qualification`:

```sql
WITH league AS (
    SELECT season, median(games) AS median_games
    FROM dw.fct_team_season WHERE games IS NOT NULL GROUP BY season
)
SELECT ...,
    CASE
        WHEN p.flat_minutes IS NOT NULL THEN p.flat_minutes
        WHEN COALESCE(t.games, l.median_games) IS NULL THEN p.fallback_minutes
        ELSE p.minutes_per_game * COALESCE(t.games, l.median_games)
    END AS minutes_required
FROM dw.fct_team_season t
LEFT JOIN league l ON l.season = t.season
CROSS JOIN dw.params p;
```

Same three-tier fallback as the Python, but now the *rule itself* is queryable.
You can ask which teams got an imputed games figure this week:

```sql
SELECT team_abbr, games, games_used, games_imputed, minutes_required
FROM dw.mart_qualification ORDER BY minutes_required;
```

That question was previously unanswerable without adding a print statement.

---

## Moving a chart over

`nwsl_warehouse.py` ends with bridge functions returning the exact dict shapes
`build_dashboard.py` already produces. Switching one chart is a two-line change
in `build_dashboard.py`:

```python
import nwsl_warehouse
con = nwsl_warehouse.connect()

# was: rows = fetch_player_pool(season, qual, teams, players)
rows = nwsl_warehouse.player_pool_rows(con, season)
```

`chart_builders.py` never learns anything changed. Move one chart, run a week,
compare the output to the previous week's `history/` snapshot, then move the
next. If a chart misbehaves, delete the two lines and it is back on the old
path.

---

## Files

| file | what it is |
|---|---|
| `nwsl_warehouse.py` | loader, CLI, and the bridge back to `chart_builders` |
| `sql/010_raw.sql` | the landing tables and the current-load views |
| `sql/020_staging.sql` | one view per endpoint — every API quirk, handled once |
| `sql/030_marts.sql` | dimensions, facts, rates, qualification |
| `warehouse_fixture.py` | a synthetic season reproducing every known live quirk |
| `test_warehouse.py` | 15 checks, each one a bug this project has already paid for |
| `nwsl_dw.duckdb` | the database — a build artifact, gitignored, always rebuildable |
| `raw_snapshots/` | saved payloads, so the whole thing rebuilds with no network |

---

## dbt: the transform layer, tested

```
pip install dbt-duckdb
python nwsl_warehouse.py load --season 2026     # runs dbt build automatically
python nwsl_warehouse.py dbt test               # tests only
python nwsl_warehouse.py dbt docs generate      # then: dbt docs serve
```

The split is the standard one, and it's the one a club's stack already uses:
**`nwsl_warehouse.py` owns extract and load**, dbt owns everything after raw.
The loader stays boring; the modelling gets version control, tests, lineage
and generated docs.

Current state: **23 models, 41 tests, all passing.** The plain `sql/` files are
still there and still work — if dbt isn't installed, the loader falls back to
them and produces identical schemas and view names. dbt is an upgrade, not a
dependency.

### Why `dbt build` and not `dbt run` + `dbt test`

`dbt build` interleaves them in dependency order: each model runs, then its
tests, and **a failing test blocks everything downstream**. That's the whole
governance argument in one behaviour. Reintroducing the round-15 `team_id` bug
into `stg_player_xgoals` produces:

```
FAIL 446  assert_team_id_arrays_unwrapped
FAIL 446  assert_minutes_are_present
Done. PASS=16  ERROR=2  SKIP=46
```

Forty-six models skipped. The broken data never reaches a mart, let alone a
chart. That is the difference between a test suite and a data contract — and
it's the thing you can point at when someone asks how you'd govern data
quality, because it's a behaviour rather than an intention.

### The two kinds of test

**Generic tests** live in `_marts.yml` and `_sources.yml` and are declarative —
`unique`, `not_null`, `relationships`, `accepted_values`. They're mostly
grain assertions: `unique` on `season || '-' || player_id` is what catches a
join that silently multiplied rows.

**Singular tests** live in `tests/*.sql` and are just queries that must return
zero rows. Each one is a bug this project has already paid for, and each names
the round it came from:

| test | the bug it prevents |
|---|---|
| `assert_team_id_arrays_unwrapped` | round 15 — `team_id` as a list, joins missing silently |
| `assert_minutes_are_present` | round 15 — `minutes_played` vs `minutes` |
| `assert_goals_added_total_matches_actions` | round 15 — the nested `data` array |
| `assert_npxg_is_never_negative` | round 22 — two independent snapshots |
| `assert_penalty_absence_means_zero` | absent ≠ unknown |
| `assert_rates_are_null_not_infinite` | divide-by-zero on per-96 |
| `assert_qualification_uses_each_teams_own_games` | round 22 — per-team, not league-wide |
| `assert_player_splits_reconcile` | 2026-09-02 — transfer splits must sum to the total |
| `assert_no_double_counted_player_team` | the grain bug in the split union |
| `assert_every_player_resolves_to_a_team` | a blank badge that raises nothing |

Writing a new one is a `.sql` file with a query. If it returns rows, it fails.

### Layout

```
dbt/
  dbt_project.yml            models/staging -> schema stg, models/marts -> dw
  profiles.yml               duckdb, path from $NWSL_DW_PATH
  macros/
    generate_schema_name.sql keeps schemas as `stg`/`dw`, not `dw_stg`
  models/
    staging/  _sources.yml + 8 models, one per endpoint
    marts/    _marts.yml   + 14 models
  tests/      10 singular tests
```

The schema-name macro matters more than it looks: dbt's default would put
staging in `dw_stg`, renaming every view the bridge functions query. The
override keeps the names identical to the hand-written version, which is why
`build_dashboard.py` can't tell the difference.

---

## What this sets up next

Stage 1 items 1 and 2 are done: the warehouse exists and the bug history is
enforced by 41 dbt tests plus 20 offline unit tests.

Item 3 is moving the weekly run from local cron to GitHub Actions — so it
runs whether or not the laptop is awake, and so the run log is public and
inspectable by someone evaluating the work. Item 4 is the written data model,
most of which is now this file.

Two open items outside the roadmap, both surfaced by the first live load:

- `build_dashboard.py` still misattributes the six transferred players — it
  uses the same `[0]` unwrap the warehouse now supersedes. Either move the
  player charts onto `nwsl_warehouse.player_pool_rows()` or port the
  primary-team logic across.
- `fetch_position_gaps()` makes eight API calls per run to get positions that
  are already on the rows. One call would do.
