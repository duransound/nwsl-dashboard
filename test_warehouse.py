"""
test_warehouse.py -- does the SQL actually say what the Python used to say?

Run:  python test_warehouse.py

Every test below loads the synthetic season from warehouse_fixture.py into an
in-memory DuckDB, then checks the models against a second, independent
calculation done in plain Python over the same fixture payloads. Two
implementations agreeing is the point -- a test that recomputes the answer the
same way the code does proves nothing.

The named cases are the bugs this project has already paid for. If a future
edit reintroduces one, it fails here instead of on a Tuesday morning.

Stdlib unittest, no pytest, so it runs anywhere the loader does.
"""

from __future__ import annotations

import unittest

import duckdb

import nwsl_warehouse as wh
import warehouse_fixture

SEASON = "2026"


def fresh_db():
    con = duckdb.connect(":memory:")
    wh._apply(con, "010_raw.sql")
    wh.load(con, SEASON, source="fixture", verbose=False)
    return con


class WarehouseTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.con = fresh_db()
        cls.fx = warehouse_fixture.build_season(SEASON)

    def q(self, sql, params=None):
        return self.con.execute(sql, params or []).fetchall()

    def one(self, sql, params=None):
        return self.con.execute(sql, params or []).fetchone()[0]

    # ------------------------------------------------ round 15: team_id shape

    def test_team_id_list_is_unwrapped(self):
        """/players/xgoals returns team_id as a list. Left unwrapped it becomes
        the literal string '["315VnJ759x"]' and every join to dim_team misses."""
        bad = self.one("""SELECT count(*) FROM stg.player_xgoals
                          WHERE team_id LIKE '[%' OR team_id LIKE '%"%'""")
        self.assertEqual(bad, 0)

        orphans = self.one("""SELECT count(*) FROM dw.fct_player_season
                              WHERE team_abbr IS NULL""")
        self.assertEqual(orphans, 0, "every player row should resolve to a team")

    # ------------------------------------------- round 15: minutes field name

    def test_minutes_resolves_under_either_name(self):
        """`minutes_played` on some endpoints, `minutes` on others. If the
        COALESCE breaks, minutes goes NULL and every per-96 rate silently
        becomes NULL rather than raising."""
        nulls = self.one("SELECT count(*) FROM stg.player_xgoals WHERE minutes IS NULL")
        self.assertEqual(nulls, 0)

        expected = {r["player_id"]: r["minutes_played"]
                    for r in self.fx[("players/xgoals", None)]}
        got = dict(self.q("SELECT player_id, minutes FROM stg.player_xgoals WHERE variant IS NULL"))
        self.assertEqual(got, expected)

    # --------------------------------------- round 15: nested goals-added shape

    def test_team_goals_added_is_summed_across_the_nested_breakdown(self):
        """The row is {team_id, minutes, data:[{action_type, goals_added_for...}]}.
        Reading goals_added_for off the row is the bug that KeyError'd on the
        first live run after surviving five rounds of demo-only testing."""
        expected = {}
        for r in self.fx[("teams/goals-added", None)]:
            tid = r["team_id"][0]
            expected[tid] = round(sum(a["goals_added_for"] for a in r["data"]), 6)

        got = {tid: round(v, 6) for tid, v in
               self.q("SELECT team_id, ga_for FROM dw.fct_team_goals_added")}
        self.assertEqual(got, expected)

    def test_player_goals_added_total_matches_action_breakdown(self):
        """mart_goals_added.ga_total must equal the sum of its own action rows.
        A join that duplicated rows would inflate this and nothing else would
        notice -- this is the grain check."""
        mismatches = self.q("""
            SELECT m.player_id, m.ga_total, f.summed
            FROM   dw.mart_goals_added m
            JOIN  (SELECT player_id, sum(goals_added_above_avg) AS summed
                   FROM dw.fct_player_goals_added GROUP BY player_id) f
              ON  f.player_id = m.player_id
            WHERE abs(m.ga_total - f.summed) > 1e-9
        """)
        self.assertEqual(mismatches, [])

    # ----------------------------------------------------------- npxG derivation

    def test_npxg_subtracts_penalties_and_never_goes_negative(self):
        pens = {r["player_id"]: r for r in self.fx[("players/xgoals", "Penalty")]}
        rows = self.q("""SELECT player_id, xgoals, pen_xgoals, npxg
                         FROM dw.fct_player_season""")
        self.assertTrue(rows)
        for pid, xg, pen_xg, npxg in rows:
            expected_pen = pens.get(pid, {}).get("xgoals", 0.0)
            self.assertAlmostEqual(pen_xg, expected_pen, places=6,
                                   msg=f"{pid}: penalty xG mismatch")
            self.assertAlmostEqual(npxg, max(xg - expected_pen, 0.0), places=6,
                                   msg=f"{pid}: npxG mismatch")
            self.assertGreaterEqual(npxg, 0.0)

    def test_players_absent_from_penalty_response_are_zero_not_null(self):
        """The live endpoint returns every player, most with zeroes. But
        correctness must not depend on that staying true, so the fixture also
        withholds a couple. Absent means zero; if the COALESCE were dropped
        their npxG would go NULL and they would vanish from every chart."""
        took_none = self.one("""
            SELECT count(*) FROM dw.fct_player_season f
            WHERE NOT EXISTS (SELECT 1 FROM stg.player_xgoals p
                              WHERE p.variant = 'Penalty' AND p.player_id = f.player_id)
        """)
        nulls = self.one("SELECT count(*) FROM dw.fct_player_season WHERE npxg IS NULL")
        self.assertGreater(took_none, 0, "fixture should withhold some penalty rows")
        self.assertEqual(nulls, 0)

    # ------------------------ 2026-09-02 live load: team_id can hold two clubs

    def test_multi_team_players_are_flagged_not_silently_collapsed(self):
        """Six players on the first live load carry two clubs, in an order that
        is not chronological. Picking element [0] and moving on attributes at
        least one of them to the club they left. The warehouse must surface
        them rather than choose silently."""
        expected = {r["player_id"] for r in self.fx[("players/xgoals", None)]
                    if len(r["team_id"]) > 1}
        self.assertTrue(expected, "fixture should contain mid-season transfers")

        flagged = self.one("SELECT count(*) FROM dw.dq_multi_team")
        self.assertEqual(flagged, len(expected))

        # first and last must actually differ, or the flag proves nothing
        differing = self.one("""SELECT count(*) FROM dw.dq_multi_team
                                WHERE listed_first IS DISTINCT FROM listed_last""")
        self.assertEqual(differing, len(expected))

        # and a single-club player must never be flagged
        self.assertEqual(
            self.one("SELECT count(*) FROM stg.player_xgoals WHERE team_count < 1"), 0)

    def test_per_club_splits_reconcile_to_the_season_total(self):
        """The reconciliation that makes the split trustworthy: the per-club
        rows must add up to the unfiltered row, to the digit. If they ever
        stop, a split call failed or the API changed shape, and attribution
        has quietly gone back to being a guess."""
        rows = self.q("""SELECT player_name, minutes_unsplit, minutes_split, reconciles
                         FROM dw.dq_multi_team""")
        self.assertTrue(rows, "fixture should contain mid-season transfers")
        for name, unsplit, split, ok in rows:
            self.assertIsNotNone(split, f"{name}: no split loaded")
            self.assertAlmostEqual(split, unsplit, places=6, msg=f"{name}: minutes")
            self.assertTrue(ok)

    def test_primary_team_is_the_club_with_the_most_minutes(self):
        """Not array position, which means nothing: across the six real 2026
        transfers, element [0] is the main club three times and the wrong club
        three times. Verified live -- Lilly Reale reads Gotham-first with 629
        minutes at Gotham and 903 at Boston."""
        for name, primary in self.q("""SELECT player_name, primary_team FROM dw.dq_multi_team"""):
            best = self.q("""
                SELECT team_abbr FROM dw.fct_player_team_season f
                JOIN dw.dim_player p ON p.player_id = f.player_id AND p.season = f.season
                WHERE p.player_name = ? ORDER BY minutes DESC LIMIT 1""", [name])
            self.assertEqual(primary, best[0][0], f"{name}")

    def test_no_player_is_counted_twice_in_the_team_grain(self):
        """fct_player_team_season unions split rows with single-club rows.
        If a transferred player leaked in from both branches their minutes
        would double -- the classic grain bug."""
        dupes = self.q("""
            SELECT player_id, team_id, count(*) FROM dw.fct_player_team_season
            GROUP BY 1, 2 HAVING count(*) > 1""")
        self.assertEqual(dupes, [])

        total_players = self.one("SELECT count(DISTINCT player_id) FROM dw.fct_player_team_season")
        self.assertEqual(total_players,
                         self.one("SELECT count(*) FROM dw.fct_player_season"))

    def test_general_position_is_read_off_the_row(self):
        """Confirmed present on all 245 live rows. fetch_position_gaps() makes
        eight filtered calls per run because this was previously unconfirmed."""
        missing = self.one("""SELECT count(*) FROM dw.fct_player_season
                              WHERE general_position IS NULL""")
        self.assertEqual(missing, 0)

    # ------------------------------------------------------------- per-96 rates

    def test_per96_matches_an_independent_python_calculation(self):
        expected = {}
        for r in self.fx[("players/xgoals", None)]:
            m = r["minutes_played"]
            expected[r["player_id"]] = None if not m else r["xgoals"] / m * 96
        for pid, xg96 in self.q("SELECT player_id, xg96 FROM dw.mart_player_rates"):
            want = expected[pid]
            if want is None:
                self.assertIsNone(xg96, f"{pid}: zero minutes must give NULL, not a number")
            else:
                self.assertAlmostEqual(xg96, want, places=9)

    def test_zero_minutes_player_does_not_produce_infinity(self):
        """The NULLIF guard. Without it this row is inf and it takes the axis
        of every rate scatter with it."""
        row = self.q("""SELECT minutes, xg96, shots96 FROM dw.mart_player_rates
                        WHERE minutes = 0""")
        self.assertTrue(row, "fixture should contain a zero-minutes player")
        for minutes, xg96, shots96 in row:
            self.assertIsNone(xg96)
            self.assertIsNone(shots96)

    # ------------------------------------------------- qualification (round 22)

    def test_minutes_bar_scales_with_each_teams_own_games(self):
        """Per team, not per league: a club with games in hand must not be
        judged against the club that has played the most."""
        games = {r["team_id"]: r["count_games"] for r in self.fx[("teams/xgoals", None)]}
        for tid, required, used in self.q("""SELECT team_id, minutes_required, games_used
                                             FROM dw.mart_qualification"""):
            self.assertEqual(used, games[tid])
            self.assertEqual(required, 30 * games[tid])

        distinct = self.one("SELECT count(DISTINCT minutes_required) FROM dw.mart_qualification")
        self.assertGreater(distinct, 1, "an uneven schedule must give teams different bars")

    def test_qualified_flag_agrees_with_an_independent_check(self):
        games = {r["team_id"]: r["count_games"] for r in self.fx[("teams/xgoals", None)]}
        minutes = {r["player_id"]: (r["team_id"][0], r["minutes_played"])
                   for r in self.fx[("players/xgoals", None)]}
        for pid, qualified in self.q("SELECT player_id, qualified FROM dw.mart_player_rates"):
            tid, mins = minutes[pid]
            self.assertEqual(bool(qualified), mins >= 30 * games[tid], f"{pid}")

    def test_flat_minutes_setting_overrides_the_scaled_rule(self):
        con = duckdb.connect(":memory:")
        wh._apply(con, "010_raw.sql")
        wh.load(con, SEASON, source="fixture", flat_minutes=500, verbose=False)
        bars = con.execute("SELECT DISTINCT minutes_required FROM dw.mart_qualification").fetchall()
        self.assertEqual(bars, [(500.0,)])

    # -------------------------------------------------- round 3: /teams outage

    def test_missing_team_name_degrades_to_the_id_instead_of_dropping_the_team(self):
        """/teams has 500'd while /teams/xgoals stayed healthy. Losing the name
        lookup must not lose the club."""
        missing = warehouse_fixture.TEAM_MISSING_FROM_LOOKUP
        row = self.q("""SELECT team_name, team_abbr, name_missing FROM dw.dim_team
                        WHERE team_id = ?""", [missing])
        self.assertEqual(len(row), 1)
        name, abbr, flagged = row[0]
        self.assertTrue(flagged)
        self.assertEqual(name, missing)
        self.assertEqual(abbr, missing)
        self.assertEqual(self.one("SELECT count(*) FROM dw.fct_team_season"), 16)

    # ------------------------------------------------------------ load hygiene

    def test_partial_load_is_invisible_until_it_finishes(self):
        """An unfinished load must not reach any view -- that is what keeps a
        failed Tuesday showing last week's correct numbers instead of half a
        league."""
        before = self.one("SELECT count(*) FROM dw.fct_team_season")
        self.con.execute("""INSERT INTO raw.loads
                            (load_id, season, started_at, source)
                            VALUES (99999999999999, ?, now(), 'api')""", [SEASON])
        self.con.execute("""INSERT INTO raw.asa_records
                            (load_id, endpoint, season, variant, fetched_at, record)
                            VALUES (99999999999999, 'teams/xgoals', ?, NULL, now(),
                                    '{"team_id":"junk","xgoals_for":1,"xgoals_against":1}')""",
                         [SEASON])
        self.assertEqual(self.one("SELECT count(*) FROM dw.fct_team_season"), before)
        self.con.execute("DELETE FROM raw.asa_records WHERE load_id = 99999999999999")
        self.con.execute("DELETE FROM raw.loads WHERE load_id = 99999999999999")

    def test_critical_endpoint_failure_aborts_without_publishing(self):
        con = duckdb.connect(":memory:")
        wh._apply(con, "010_raw.sql")
        wh.load(con, SEASON, source="fixture", verbose=False)
        good = con.execute("SELECT count(*) FROM dw.fct_player_season").fetchone()[0]

        broken = warehouse_fixture.build_season(SEASON)
        del broken[("players/xgoals", None)]          # the critical one
        original = warehouse_fixture.build_season
        warehouse_fixture.build_season = lambda season: broken
        try:
            with self.assertRaises(RuntimeError):
                wh.load(con, SEASON, source="fixture", verbose=False)
        finally:
            warehouse_fixture.build_season = original

        wh.build_models(con)
        self.assertEqual(con.execute("SELECT count(*) FROM dw.fct_player_season").fetchone()[0],
                         good, "a failed load must not change what the dashboard sees")

    # ------------------------------------------- bridge back to chart_builders

    def test_bridge_returns_the_dict_shape_build_dashboard_expects(self):
        players = wh.player_pool_rows(self.con, SEASON)
        self.assertTrue(players)
        for key in ("id", "name", "team", "minutes", "xg", "xa", "goals", "shots",
                    "npxg", "npgoals", "npshots"):
            self.assertIn(key, players[0])
        self.assertTrue(all(p["minutes"] >= p["minutes_required"] for p in players))

        teams = wh.team_rows(self.con, SEASON)
        self.assertEqual(len(teams), 16)
        for key in ("abbr", "name", "xgf", "xga", "points", "games"):
            self.assertIn(key, teams[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
