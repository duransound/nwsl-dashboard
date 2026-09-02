"""
export_extracts.py -- Tableau extracts, straight out of the warehouse.

Tableau reads the mart layer. That is the point: the marts already contain the
definitions (non-penalty totals, the games-scaled qualification bar, the
placement split), so the BI tool inherits them instead of re-implementing them
in calculated fields where they would drift. This is how a BI tool sits on a
warehouse at a club, and it is the reason to have built the warehouse first.

    python3 export_extracts.py              # after any nwsl_warehouse.py load
    python3 export_extracts.py --season 2026 --out tableau/

Writes three CSVs, one per planned viz. Tableau Public reads CSV natively --
no driver, no extract API, no live connection to maintain.
"""
import argparse, pathlib, sys

try:
    import duckdb
except ImportError:
    sys.exit("needs duckdb:  pip install duckdb")

QUERIES = {
    # 1. Team xG difference -- a diverging bar. One row per club.
    "teams": """
        SELECT team_abbr        AS "Team",
               team_name        AS "Club",
               games            AS "Games",
               round(xgoals_for, 2)        AS "xG For",
               round(xgoals_against, 2)    AS "xG Against",
               round(xgoal_difference, 2)  AS "xG Difference",
               points           AS "Points"
        FROM dw.fct_team_season WHERE season = ?
        ORDER BY xgoal_difference DESC
    """,
    # 2. League picture -- xGF vs xGA quadrants. Same grain, kept separate so
    #    each Tableau workbook has exactly the fields its viz needs.
    "league_picture": """
        SELECT team_abbr AS "Team", team_name AS "Club",
               round(xgoals_for, 2)     AS "xG For",
               round(xgoals_against, 2) AS "xG Against",
               games AS "Games", points AS "Points"
        FROM dw.fct_team_season WHERE season = ?
    """,
    # 3. Placement vs. luck -- one row per qualifying player, with the split
    #    already computed. `Margin` = `Placement` + `Residual`, by construction.
    "placement": """
        SELECT player_name  AS "Player",
               team_abbr    AS "Team",
               general_position AS "Position",
               minutes      AS "Minutes",
               np_shots     AS "Shots",
               np_goals     AS "Goals",
               round(npxg, 3)                 AS "npxG",
               round(np_goals - npxg, 3)      AS "Margin",
               round(np_xplace, 3)            AS "Placement",
               round(finishing_residual, 3)   AS "Residual",
               qualified    AS "Qualified"
        FROM dw.mart_player_rates
        WHERE season = ? AND qualified AND np_shots >= 10
        ORDER BY (np_goals - npxg) DESC
    """,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="nwsl_dw.duckdb")
    ap.add_argument("--season", default="2026")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()

    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(a.db, read_only=True)
    for name, sql in QUERIES.items():
        path = out / f"nwsl_{a.season}_{name}.csv"
        con.execute(f"COPY ({sql.replace('?', repr(a.season))}) TO '{path}' (HEADER, DELIMITER ',')")
        n = con.execute(sql, [a.season]).fetchall()
        print(f"  {path.name:<34} {len(n):>4} rows")
    print(f"\nOpen these in Tableau Public. See README.md for the three builds.")


if __name__ == "__main__":
    main()
