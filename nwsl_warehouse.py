"""
nwsl_warehouse.py -- a DuckDB warehouse under the NWSL dashboard.

WHY THIS EXISTS
---------------
build_dashboard.py currently does fetch -> reshape -> chart in one pass, in
Python, and throws the API's response away. That works, and it has shipped a
live site for fifteen rounds. What it cannot do is answer "what did the API
actually say last Tuesday, and is this week's number different because the
league changed or because the feed did?" -- because last Tuesday's response no
longer exists anywhere.

This module adds the layer that answers that, without touching anything that
currently works:

    ASA API  ->  raw.asa_records   (append-only, JSON kept verbatim)
                      |
                 stg.* models      (typed, normalized -- the bug fixes live here)
                      |
                 dw.*  models      (dims, facts, per-96 rates, qualification)
                      |            built and tested by dbt when it is installed,
                      |            from plain sql/ files when it is not
                      |
              chart_builders.py    (unchanged)

build_dashboard.py is not modified. The bridge functions at the bottom of this
file return the exact dict shapes its fetch_* functions already return, so a
chart can be switched over one at a time and switched back if it misbehaves.

INSTALL
-------
    pip install duckdb           # required, in whatever venv you run this from
    bash setup_dbt.sh            # optional -- dbt in its OWN venv, where the
                                 # tests live. Do not install dbt into the
                                 # project venv; see dbt_executable() below.

USAGE
-----
    # Weekly: pull live data and rebuild the models (needs real internet --
    # neither the Claude cloud sandbox nor the desktop bridge VM can reach
    # app.americansocceranalysis.com, so this runs from your own Terminal)
    python nwsl_warehouse.py load --season 2026

    # Same pull, but also save the raw payloads so you can rebuild offline
    python nwsl_warehouse.py load --season 2026 --dump-raw raw_snapshots/

    # Rebuild the models from payloads already on disk -- no network at all
    python nwsl_warehouse.py load --season 2026 --from-dir raw_snapshots/

    # Load a synthetic season, for trying SQL without touching the API
    python nwsl_warehouse.py load --season 2026 --fixture

    # Re-apply the .sql files after editing them (fast, no re-fetch)
    python nwsl_warehouse.py build

    # dbt, pointed at this database. `load` runs `dbt build` automatically
    # when dbt is installed; these are for working on the models themselves.
    python nwsl_warehouse.py dbt test
    python nwsl_warehouse.py dbt build --select mart_player_rates+
    python nwsl_warehouse.py dbt docs generate        # then: dbt docs serve

    # Look around
    python nwsl_warehouse.py tables
    python nwsl_warehouse.py sql "SELECT team_abbr, xgoal_difference
                                  FROM dw.fct_team_season ORDER BY 2 DESC"

The database is a single file (nwsl_dw.duckdb by default). It is a build
artifact -- gitignored, and rebuildable from raw_snapshots/ at any time.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:                                          # pragma: no cover
    sys.exit("This needs DuckDB. Install it with:  pip install duckdb")

BASE_URL = "https://app.americansocceranalysis.com/api/v1/nwsl"
DEFAULT_DB = "nwsl_dw.duckdb"
SQL_DIR = Path(__file__).resolve().parent / "sql"

# Which endpoints make up a load, and what a failure on each one means.
#
# `critical` is the important column. A load that loses /players/xgoals has
# nothing to plot and must NOT be published -- so the run aborts before
# stamping finished_at, raw.current_load keeps pointing at last week's good
# data, and the dashboard shows stale-but-correct numbers instead of a
# half-empty page. A load that loses /teams only loses the name lookup, which
# dw.dim_team already degrades to team ids. That is the round-3 outage,
# handled as a policy instead of a special case.
ENDPOINTS = [
    # (endpoint,               variant,   critical, needs_season, needs_floor)
    ("teams",                  None,      False,    False,        False),
    ("players",                None,      False,    False,        False),
    ("teams/xgoals",           None,      True,     True,         False),
    ("teams/goals-added",      None,      False,    True,         False),
    ("players/xgoals",         None,      True,     True,         True),
    ("players/xgoals",         "Penalty", False,    True,         True),
    ("players/goals-added",    None,      False,    True,         True),
    ("goalkeepers/xgoals",     None,      False,    True,         False),
]

# The `by-team` variant is not in the table above because it cannot be: which
# calls to make is only known after /players/xgoals comes back. See
# _load_team_splits().
SPLIT_VARIANT = "by-team"


# --------------------------------------------------------------------------
# connection + schema
# --------------------------------------------------------------------------

def connect(db_path: str = DEFAULT_DB):
    con = duckdb.connect(db_path)
    _apply(con, "010_raw.sql")
    return con


def _apply(con, filename: str) -> None:
    path = SQL_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"missing SQL file: {path}")
    con.execute(path.read_text())


DBT_DIR = Path(__file__).resolve().parent / "dbt"

# dbt is a COMMAND, not a library this code imports -- nothing here does
# `import dbt`. That matters, because installing it into the project venv puts
# dbt-core's pinned dependency ranges (agate, protobuf, pydantic, jinja2) in
# the same resolver problem as everything else already in there. On this
# project's venv -- pandas 3.0.5, marimo, botasaurus, ScraperFC -- that
# resolution fails outright.
#
# So dbt gets its own environment, and this looks for it in three places:
#   1. $NWSL_DBT, if you want to point at a specific binary
#   2. .venv-dbt/bin/dbt, created by setup_dbt.sh -- the recommended setup
#   3. whatever `dbt` is on PATH
# Finding none of them is not an error: the loader falls back to the plain
# sql/ files and the warehouse still builds, just without the tests.
def dbt_executable() -> str | None:
    override = os.environ.get("NWSL_DBT")
    if override and Path(override).exists():
        return override
    local = Path(__file__).resolve().parent / ".venv-dbt" / "bin" / "dbt"
    if local.exists():
        return str(local)
    if os.name == "nt":                                     # pragma: no cover
        win = Path(__file__).resolve().parent / ".venv-dbt" / "Scripts" / "dbt.exe"
        if win.exists():
            return str(win)
    return shutil.which("dbt")


def dbt_available() -> bool:
    return DBT_DIR.exists() and dbt_executable() is not None


def run_dbt(db_path: str, command: str = "build", *, extra: list | None = None) -> int:
    """Hand the transform layer to dbt.

    The loader keeps owning extract-and-load; dbt owns everything after raw.
    That is the split a club's stack already uses, and it is what buys the
    parts a hand-rolled pipeline does not have: tests that block a bad build,
    a lineage graph, and generated docs.

    `dbt build` runs each model and then its tests IN DEPENDENCY ORDER, so a
    failing test stops everything downstream of it. Reintroduce the round-15
    team_id bug and the run halts at staging with 46 models skipped -- the
    broken data never reaches a chart. That is the difference between a test
    suite and a data contract.
    """
    exe = dbt_executable()
    if exe is None:
        print("dbt not found. Run:  bash setup_dbt.sh")
        return 127
    env = dict(os.environ, NWSL_DW_PATH=str(Path(db_path).resolve()))
    cmd = [exe, command, "--profiles-dir", "."] + (extra or [])
    return subprocess.run(cmd, cwd=DBT_DIR, env=env).returncode


def build_models(con) -> None:
    """Re-create every staging and mart view from the plain .sql files.

    This is the no-dependency path: it always works, and it is what the tests
    and any in-memory database use. The CLI additionally runs dbt over the
    same database when dbt is installed -- same schemas, same view names, so
    nothing downstream can tell which one ran. dbt is an upgrade, not a
    requirement.
    """
    _apply(con, "010_raw.sql")
    _apply(con, "020_staging.sql")
    _apply(con, "030_marts.sql")


def set_params(con, minutes_per_game=None, flat_minutes=None, fallback_minutes=None):
    """Persist the qualification thresholds so the SQL is not hardcoded."""
    con.execute("CREATE SCHEMA IF NOT EXISTS dw")
    con.execute("CREATE TABLE IF NOT EXISTS dw.settings (key VARCHAR PRIMARY KEY, value VARCHAR)")
    for key, value in (("minutes_per_game", minutes_per_game),
                       ("flat_minutes", flat_minutes),
                       ("fallback_minutes", fallback_minutes)):
        con.execute("DELETE FROM dw.settings WHERE key = ?", [key])
        if value is not None:
            con.execute("INSERT INTO dw.settings VALUES (?, ?)", [key, str(value)])


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------

def _get(endpoint: str, params: dict) -> list:
    import requests                       # imported lazily: offline paths don't need it
    resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()
    if not isinstance(rows, list):
        raise ValueError(f"{endpoint} returned {type(rows).__name__}, expected a list")
    return rows


def _snapshot_name(endpoint: str, variant, season: str) -> str:
    slug = endpoint.replace("/", "__")
    return f"{season}__{slug}" + (f"__{variant}" if variant else "") + ".json"


def _load_team_splits(con, load_id: int, season: str, *, payloads=None,
                      dump_raw: str | None = None, verbose: bool = True) -> int:
    """Resolve mid-season transfers by asking the API for each club separately.

    A player who changed clubs comes back from the unfiltered endpoint with
    team_id as a multi-element array and every metric summed across both
    clubs. Confirmed live on 2026-09-02:

        Ally Sentnor  ["4wM4rZdqjB","kRQa8JOqKZ"]  2079 min, 64 shots, 5.6834 xG
          + team_id=4wM4rZdqjB (KC)                1070 min, 26 shots, 2.8846 xG  (ST)
          + team_id=kRQa8JOqKZ (LA)                1009 min, 38 shots, 2.7988 xG  (AM)

    The parts sum to the whole exactly, so the split is real data rather than
    an approximation -- and the position differs per club, which the aggregate
    row cannot express at all.

    Two further facts, both worth knowing:
      * the team-filtered response returns team_id as a STRING, not an array
      * the array's order carries no reliable meaning. Not chronological
        (Yazmeen Ryan reads ["DEN","HOU"] on a Houston -> Denver move) and not
        minutes-ordered either -- across the six 2026 transfers, `[0]` names
        the club they played MORE for in three cases and LESS in three.

    So there is no array-position rule to fall back on. With the splits
    loaded, no guess is needed.

    Cost is two calls per transferred player, not two per club: six players on
    the first 2026 load, so twelve calls.
    """
    multi = con.execute("""
        SELECT record->>'$.player_id', record->'$.team_id'
        FROM   raw.asa_records
        WHERE  load_id = ? AND endpoint = 'players/xgoals' AND variant IS NULL
          AND  json_type(record->'$.team_id') = 'ARRAY'
          AND  json_array_length(record->'$.team_id') > 1
    """, [load_id]).fetchall()

    if not multi:
        if verbose:
            print("   no mid-season transfers this load")
        return 0

    pairs = [(pid, tid) for pid, teams in multi for tid in json.loads(teams)]
    if verbose:
        print(f"   {len(multi)} transferred players -> {len(pairs)} split calls")

    saved = []
    written = 0
    for player_id, team_id in pairs:
        try:
            if payloads is not None:
                rows = [r for r in payloads.get(("players/xgoals", SPLIT_VARIANT), [])
                        if r["player_id"] == player_id and r["team_id"] == team_id]
            else:
                rows = _get("players/xgoals", {"season_name": season, "player_id": player_id,
                                               "team_id": team_id, "minimum_minutes": 0})
            con.executemany(
                """INSERT INTO raw.asa_records
                   (load_id, endpoint, season, variant, fetched_at, record)
                   VALUES (?, 'players/xgoals', ?, ?, ?, ?)""",
                [[load_id, season, SPLIT_VARIANT, dt.datetime.now(), json.dumps(r)] for r in rows])
            saved.extend(rows)
            written += len(rows)
        except Exception as exc:                                   # noqa: BLE001
            # Non-fatal: without a split the player still appears, attributed
            # to whichever club the array listed first, and dw.dq_multi_team
            # keeps flagging them.
            print(f"   FAIL split {player_id}/{team_id}: {type(exc).__name__}: {exc}")

    if dump_raw and saved:
        (Path(dump_raw) / _snapshot_name("players/xgoals", SPLIT_VARIANT, season)
         ).write_text(json.dumps(saved, indent=1))
    if verbose:
        print(f"   ok   players/xgoals [{SPLIT_VARIANT}]{'':<13} {written:>6} rows")
    return written


def _api_floor(team_rows: list, minutes_per_game: int, flat_minutes, fallback: int) -> int:
    """The lowest per-team minutes bar in the league.

    ASA's `minimum_minutes` parameter is a single league-wide number, so it
    cannot express "30 minutes per game your own team has played". Asking for
    the lowest bar in the league guarantees the API never drops somebody the
    real per-team rule would have kept; dw.mart_qualification then applies the
    real test in SQL, once each row's team is known.
    """
    if flat_minutes is not None:
        return int(flat_minutes)
    games = [g for g in (r.get("count_games") or r.get("games") or r.get("games_played")
                         for r in team_rows) if g]
    if not games:
        return int(fallback)
    return int(minutes_per_game * min(games))


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def load(con, season: str, *, source: str = "api", from_dir: str | None = None,
         dump_raw: str | None = None, minutes_per_game: int = 30,
         flat_minutes=None, fallback_minutes: int = 500, verbose: bool = True) -> int:
    """Run one load. Returns the load_id.

    Raises RuntimeError if a critical endpoint failed -- in which case
    finished_at is never stamped, so raw.current_load ignores this load
    entirely and every downstream view keeps reading the last good one.
    """
    started = dt.datetime.now()
    load_id = int(started.timestamp() * 1000)

    con.execute("""INSERT INTO raw.loads
                   (load_id, season, started_at, source, n_records, n_endpoints, n_failed)
                   VALUES (?, ?, ?, ?, 0, 0, 0)""",
                [load_id, season, started, source])

    if dump_raw:
        Path(dump_raw).mkdir(parents=True, exist_ok=True)

    # Pull the team table first: the per-player floor depends on games played.
    if source == "fixture":
        import warehouse_fixture
        payloads = warehouse_fixture.build_season(season)
    elif source == "json-dir":
        payloads = {}
        for endpoint, variant, _c, _s, _f in ENDPOINTS:
            path = Path(from_dir) / _snapshot_name(endpoint, variant, season)
            if path.exists():
                payloads[(endpoint, variant)] = json.loads(path.read_text())
    else:
        payloads = None                        # fetched below, one call at a time

    n_records = n_failed = n_endpoints = 0
    floor = None

    for endpoint, variant, critical, needs_season, needs_floor in ENDPOINTS:
        try:
            if payloads is not None:
                rows = payloads.get((endpoint, variant))
                if rows is None:
                    raise FileNotFoundError(f"no saved payload for {endpoint} {variant or ''}".strip())
            else:
                params = {}
                if needs_season:
                    params["season_name"] = season
                if needs_floor:
                    if floor is None:
                        floor = fallback_minutes      # teams/xgoals failed; be permissive
                    params["minimum_minutes"] = floor
                if variant:
                    params["shot_pattern"] = variant
                rows = _get(endpoint, params)

            if endpoint == "teams/xgoals" and variant is None:
                floor = _api_floor(rows, minutes_per_game, flat_minutes, fallback_minutes)
                if verbose:
                    print(f"   minutes floor sent to the API: {floor}")

            if dump_raw:
                (Path(dump_raw) / _snapshot_name(endpoint, variant, season)
                 ).write_text(json.dumps(rows, indent=1))

            con.executemany(
                """INSERT INTO raw.asa_records
                   (load_id, endpoint, season, variant, fetched_at, record)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [[load_id, endpoint, season, variant, dt.datetime.now(), json.dumps(r)]
                 for r in rows])

            n_records += len(rows)
            n_endpoints += 1
            if verbose:
                label = f"{endpoint}" + (f" [{variant}]" if variant else "")
                print(f"   ok   {label:<32} {len(rows):>6} rows")

        except Exception as exc:                                   # noqa: BLE001
            n_failed += 1
            label = f"{endpoint}" + (f" [{variant}]" if variant else "")
            print(f"   FAIL {label:<32} {type(exc).__name__}: {exc}")
            if critical:
                con.execute("UPDATE raw.loads SET notes = ?, n_failed = ? WHERE load_id = ?",
                            [f"aborted: critical endpoint {label} failed", n_failed, load_id])
                raise RuntimeError(
                    f"{label} is critical and failed -- load {load_id} left unfinished, "
                    f"so the dashboard keeps reading the last good load."
                ) from exc

    n_records += _load_team_splits(con, load_id, season, payloads=payloads,
                                   dump_raw=dump_raw, verbose=verbose)

    con.execute("""UPDATE raw.loads
                   SET finished_at = ?, n_records = ?, n_endpoints = ?, n_failed = ?
                   WHERE load_id = ?""",
                [dt.datetime.now(), n_records, n_endpoints, n_failed, load_id])

    set_params(con, minutes_per_game, flat_minutes, fallback_minutes)
    build_models(con)
    return load_id


# --------------------------------------------------------------------------
# bridge back to chart_builders.py
#
# Each function returns the exact dict shape the matching build_dashboard.py
# fetch_* function returns today, so a chart can be pointed at SQL without
# chart_builders.py knowing anything changed.
# --------------------------------------------------------------------------

def _dicts(con, sql: str, params: list | None = None) -> list[dict]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def team_rows(con, season: str) -> list[dict]:
    """Replaces the list comprehension inside fetch_team_charts()."""
    return _dicts(con, """
        SELECT team_abbr AS abbr, team_name AS name,
               xgoals_for AS xgf, xgoals_against AS xga,
               points, games
        FROM   dw.fct_team_season
        WHERE  season = ?
        ORDER  BY xgoal_difference DESC
    """, [season])


def player_pool_rows(con, season: str, qualified_only: bool = True) -> list[dict]:
    """Replaces fetch_player_pool() -- including the npxG subtraction, the
    minutes-name fallback, the team_id unwrap, and the qualification filter,
    all of which now happen in SQL."""
    return _dicts(con, f"""
        SELECT player_id AS id, player_name AS name, team_abbr AS team,
               general_position AS position, team_count,
               minutes, xgoals AS xg, xassists AS xa, goals, shots,
               npxg, np_goals AS npgoals, np_shots AS npshots,
               minutes_required, qualified
        FROM   dw.mart_player_rates
        WHERE  season = ?
        {"AND qualified" if qualified_only else ""}
        ORDER  BY xgoals DESC
    """, [season])


def goals_added_rows(con, season: str, top_n: int | None = None) -> list[dict]:
    return _dicts(con, f"""
        SELECT player_id AS id, player_name AS name, team_abbr AS team,
               minutes, ga_total, ga96, ga_dribbling, ga_passing, ga_shooting
        FROM   dw.mart_goals_added
        WHERE  season = ?
        ORDER  BY ga_total DESC
        {f"LIMIT {int(top_n)}" if top_n else ""}
    """, [season])


def goalkeeper_rows(con, season: str) -> list[dict]:
    return _dicts(con, """
        SELECT player_id AS id, player_name AS name, team_abbr AS team,
               minutes, shots_faced, goals_conceded, xgoals_faced,
               goals_saved_above_expected, shots_faced96
        FROM   dw.mart_goalkeepers
        WHERE  season = ?
        ORDER  BY goals_saved_above_expected DESC
    """, [season])


def team_goals_added_rows(con, season: str) -> list[dict]:
    return _dicts(con, """
        SELECT team_abbr AS abbr, team_name AS name, ga_for, ga_against, ga_net
        FROM   dw.fct_team_goals_added
        WHERE  season = ?
        ORDER  BY ga_net DESC
    """, [season])


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _cmd_load(args) -> int:
    con = connect(args.db)
    source = "fixture" if args.fixture else ("json-dir" if args.from_dir else "api")
    print(f"-> loading season {args.season} from {source}")
    try:
        load_id = load(con, args.season, source=source, from_dir=args.from_dir,
                       dump_raw=args.dump_raw, minutes_per_game=args.minutes_per_game,
                       flat_minutes=args.minutes, fallback_minutes=args.fallback_minutes)
    except RuntimeError as exc:
        # An aborted load is a handled outcome, not a crash: the point of the
        # design is that this leaves the previous good load in place. Say so in
        # one line rather than dumping a traceback into the weekly log.
        print(f"-> ABORTED: {exc}")
        previous = con.execute("""SELECT load_id, finished_at FROM raw.loads
                                  WHERE season = ? AND finished_at IS NOT NULL
                                  ORDER BY load_id DESC LIMIT 1""", [args.season]).fetchone()
        if previous:
            print(f"-> still serving load {previous[0]} from {previous[1]}")
        else:
            print("-> no previous good load exists yet, so the warehouse is empty")
        return 2
    row = con.execute("""SELECT n_records, n_endpoints, n_failed
                         FROM raw.loads WHERE load_id = ?""", [load_id]).fetchone()
    print(f"-> load {load_id}: {row[0]} records from {row[1]} endpoints "
          f"({row[2]} failed but non-critical)")
    qualified = con.execute("""SELECT count(*) FROM dw.mart_player_rates
                               WHERE season = ? AND qualified""", [args.season]).fetchone()[0]
    print(f"-> {qualified} players qualified at "
          f"{args.minutes_per_game} min/game")

    if not args.no_dbt and dbt_available():
        # DuckDB allows one writing process at a time, so the loader has to
        # let go of the file before dbt can open it.
        con.close()
        print("-> handing the transform layer to dbt")
        if run_dbt(args.db, "build") != 0:
            print("-> dbt build FAILED: a model errored or a data test caught "
                  "something. Raw data is untouched and the previous views are "
                  "still in place -- read the output above before rebuilding.")
            return 3
        con = connect(args.db)
    elif not args.no_dbt:
        print("-> dbt not found; built the views from sql/ instead. "
              "Run `bash setup_dbt.sh` to get the 41 data tests.")

    print(f"-> database: {args.db}")
    return 0


def _cmd_build(args) -> int:
    con = connect(args.db)
    build_models(con)
    print(f"-> rebuilt models in {args.db}")
    return 0


def _cmd_tables(args) -> int:
    con = connect(args.db)
    build_models(con)
    rows = con.execute("""
        SELECT table_schema, table_name, table_type
        FROM   information_schema.tables
        WHERE  table_schema IN ('raw', 'stg', 'dw')
        ORDER  BY table_schema, table_name
    """).fetchall()
    for schema, name, kind in rows:
        n = con.execute(f'SELECT count(*) FROM "{schema}"."{name}"').fetchone()[0]
        print(f"  {schema:<4} {name:<32} {kind:<10} {n:>8} rows")
    return 0


def _cmd_dbt(args) -> int:
    if not dbt_available():
        print("dbt is not installed. pip install dbt-duckdb")
        return 1
    rest = [a for a in args.dbt_args if a != "--"]
    return run_dbt(args.db, rest[0] if rest else "build", extra=rest[1:])


def _cmd_sql(args) -> int:
    con = connect(args.db)
    build_models(con)
    con.sql(args.query).show(max_rows=args.limit)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=DEFAULT_DB)
    sub = p.add_subparsers(dest="cmd", required=True)

    lo = sub.add_parser("load", help="fetch a season and rebuild the models")
    lo.add_argument("--season", default="2026")
    lo.add_argument("--minutes-per-game", type=int, default=30,
                    help="qualification bar per game the team has played (default 30)")
    lo.add_argument("--minutes", type=int, default=None,
                    help="opt back out to a flat minutes floor")
    lo.add_argument("--fallback-minutes", type=int, default=500)
    lo.add_argument("--dump-raw", default=None, metavar="DIR",
                    help="also save each raw payload as JSON, for offline rebuilds")
    lo.add_argument("--from-dir", default=None, metavar="DIR",
                    help="load from saved payloads instead of the network")
    lo.add_argument("--no-dbt", action="store_true",
                    help="skip the dbt build even if dbt is installed")
    lo.add_argument("--fixture", action="store_true",
                    help="load a synthetic season (no network, for practising SQL)")
    lo.set_defaults(func=_cmd_load)

    bu = sub.add_parser("build", help="re-apply the .sql files")
    bu.set_defaults(func=_cmd_build)

    ta = sub.add_parser("tables", help="list every table and view with row counts")
    ta.set_defaults(func=_cmd_tables)

    dt_ = sub.add_parser("dbt", help="run a dbt command against this database")
    dt_.add_argument("dbt_args", nargs=argparse.REMAINDER,
                     help='e.g. test, "docs generate", "build --select mart_player_rates+"')
    dt_.set_defaults(func=_cmd_dbt)

    sq = sub.add_parser("sql", help="run a query")
    sq.add_argument("query")
    sq.add_argument("--limit", type=int, default=40)
    sq.set_defaults(func=_cmd_sql)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
