#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_warehouse.sh -- first live run of the DuckDB warehouse layer.
#
#   cd ~/Downloads/nwsl_xg_starter
#   bash run_warehouse.sh
#
# Everything it does is written to warehouse_run.log, so there is nothing to
# copy and paste back. It does not touch build_dashboard.py, dashboard.html,
# index.html, git, or anything the weekly script uses -- the only things it
# creates are nwsl_dw.duckdb and raw_snapshots/, both gitignored.
# ---------------------------------------------------------------------------

cd "$(dirname "$0")" || exit 1
LOG="warehouse_run.log"

{
  echo "======================================================================"
  echo "warehouse run  $(date)"
  echo "======================================================================"

  # -------------------------------------------------- 1. interpreter
  echo
  echo "--- [1/6] python ------------------------------------------------------"
  if [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
    echo "venv active: $(python --version 2>&1)  at  $(command -v python)"
  else
    echo "no .venv found -- falling back to system python3"
    alias python=python3
    shopt -s expand_aliases
  fi

  # -------------------------------------------------- 2. dependency
  echo
  echo "--- [2/6] duckdb + dbt ------------------------------------------------"
  if python -c "import duckdb, sys; sys.stdout.write(duckdb.__version__)" 2>/dev/null; then
    echo "  (duckdb already installed)"
  else
    echo "installing duckdb..."
    python -m pip install --quiet --disable-pip-version-check duckdb 2>&1 | tail -5
    python -c "import duckdb; print('duckdb', duckdb.__version__)" || {
      echo "!! duckdb still not importable -- stopping here"; exit 1; }
  fi
  # dbt lives in its OWN venv (.venv-dbt), created by setup_dbt.sh. It is a
  # command this project shells out to, never a library it imports, so it has
  # no business sharing a resolver with pandas/marimo/botasaurus -- installing
  # it into the project venv is what failed on 2026-09-02.
  if [ -x .venv-dbt/bin/dbt ]; then
    echo "  (dbt in .venv-dbt)  $(.venv-dbt/bin/dbt --version 2>&1 | head -2 | tail -1)"
  elif command -v dbt >/dev/null 2>&1; then
    echo "  (dbt on PATH)  $(dbt --version 2>&1 | head -2 | tail -1)"
  else
    echo "  dbt not set up -- run:  bash setup_dbt.sh"
    echo "  (the warehouse still builds from sql/, just without the 41 tests)"
  fi

  # -------------------------------------------------- 3. offline tests first
  # Runs against the synthetic season. If this fails, the problem is the code,
  # not the API -- worth knowing before a single network call is made.
  echo
  echo "--- [3/6] tests (offline, synthetic season) ---------------------------"
  python test_warehouse.py 2>&1 | tail -25

  # -------------------------------------------------- 4. the live load
  echo
  echo "--- [4/6] live load from the ASA API ----------------------------------"
  python nwsl_warehouse.py load --season 2026 --dump-raw raw_snapshots/
  echo "load exit code: $?"

  # -------------------------------------------------- 5. what got built
  echo
  echo "--- [5/6] tables ------------------------------------------------------"
  python nwsl_warehouse.py tables

  # -------------------------------------------------- 6. does it look right
  echo
  echo "--- [6/6] sanity queries ----------------------------------------------"

  echo
  echo "> league table by xG difference"
  python nwsl_warehouse.py sql "
    SELECT team_abbr, games, round(xgoals_for,1) AS xgf,
           round(xgoals_against,1) AS xga, round(xgoal_difference,1) AS diff, points
    FROM dw.fct_team_season ORDER BY diff DESC" --limit 20

  echo
  echo "> the qualification bar, per team"
  python nwsl_warehouse.py sql "
    SELECT team_abbr, games, games_imputed, minutes_required
    FROM dw.mart_qualification ORDER BY minutes_required" --limit 20

  echo
  echo "> best finishers in non-penalty terms"
  python nwsl_warehouse.py sql "
    SELECT player_name, team_abbr, minutes, round(npxg,2) AS npxg,
           np_goals, round(np_goals_minus_npxg,2) AS signal
    FROM dw.mart_player_rates WHERE qualified
    ORDER BY signal DESC" --limit 15

  echo
  echo "> mid-season transfers, and whether their per-club splits reconcile"
  python nwsl_warehouse.py sql "
    SELECT player_name, team_ids_raw, listed_first, primary_team,
           minutes_unsplit, minutes_split, reconciles
    FROM dw.dq_multi_team ORDER BY minutes_unsplit DESC" --limit 20

  echo
  echo "> data-quality snapshot -- these should all read 0 except qualified/total"
  python nwsl_warehouse.py sql "
    SELECT
      (SELECT count(*) FROM stg.player_xgoals WHERE team_id LIKE '[%')        AS unwrapped_team_ids,
      (SELECT count(*) FROM stg.player_xgoals WHERE minutes IS NULL)          AS null_minutes,
      (SELECT count(*) FROM dw.fct_player_season WHERE team_abbr IS NULL)     AS players_without_team,
      (SELECT count(*) FROM dw.fct_player_season WHERE npxg IS NULL)          AS null_npxg,
      (SELECT count(*) FROM dw.dim_team WHERE name_missing)                   AS teams_missing_names,
      (SELECT count(*) FROM dw.mart_player_rates WHERE qualified)             AS qualified_players,
      (SELECT count(*) FROM dw.mart_player_rates)                             AS players_total"

  echo
  echo "> what /players/xgoals actually calls its fields (the round-15 question)"
  python -c "
import json, pathlib
p = pathlib.Path('raw_snapshots/2026__players__xgoals.json')
if p.exists():
    rows = json.loads(p.read_text())
    print('rows:', len(rows))
    print('keys:', sorted(rows[0].keys()))
    print('sample:', json.dumps(rows[0], indent=1)[:700])
else:
    print('no snapshot written -- the load did not get that far')
"

  echo
  echo "======================================================================"
  echo "done  $(date)"
  echo "======================================================================"
} > "$LOG" 2>&1

echo "Finished. Full output is in $(pwd)/$LOG"
tail -30 "$LOG"
