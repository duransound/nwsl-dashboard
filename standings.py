"""
Standings -- the actual league table, built from results rather than xG.

WHY THIS TAB IS DIFFERENT FROM EVERY OTHER TAB HERE

The rest of the dashboard is expected-goals work: what a team deserved.
A league table is the opposite claim -- what a team actually got. The two
belong on the same page precisely because they disagree, and the disagreement
is the story (a side sitting fifth on 1.4 xG per game is a different bet from
a side sitting fifth on 0.8). So the table carries real points alongside an
xG-difference column, and the lede names whichever team the two rank most
differently.

WHAT ASA ACTUALLY PUBLISHES, AND WHAT IS DERIVED

/teams/xgoals returns, per team and confirmed against a real 2026 payload:

    count_games, goals_for, goals_against, goal_difference,
    xgoals_for, xgoals_against, xgoal_difference, points, xpoints

`points`, `count_games`, `goals_for`, `goals_against` and `goal_difference`
are REAL RESULTS, not model output. Games played, points, goals for, goals
against and goal difference therefore need no inference at all.

Wins / draws / losses are NOT on that row, and they are NOT recoverable from
it: W + D + L = GP and 3W + D = Pts is two equations in three unknowns. This
module will not guess them. There are two paths:

  * RESULTS PATH -- a per-game endpoint returned usable rows, so W/D/L are
    counted from actual scorelines. `basis` is "games".
  * TOTALS PATH -- no per-game rows came back, so W/D/L render as "not
    published" and every other column is still exact. `basis` is "totals".

One thing IS exactly derivable league-wide even on the totals path: a decided
match puts 3 points into the league, a drawn match puts 2. So

    draws = 3 * (sum of games played / 2) - (sum of points)

which is arithmetic, not an estimate, and is surfaced in the footnote so the
absent W/D/L column at least says something true.

RECONCILIATION

On the results path the counted points are checked against ASA's own `points`
field and any team that disagrees is reported. A silent mismatch would mean
the game list is incomplete (a postponed fixture, a mid-season expansion side)
and the table would be quietly wrong -- see PLAYBOOK §7, "prefer the
measurement".
"""

from __future__ import annotations

# Field-name aliases. ASA has already renamed the same quantity across
# endpoints twice in this project's history (minutes vs. minutes_played,
# count_games vs. games), so every read of a per-game row goes through these
# rather than assuming one spelling. See PLAYBOOK §0.
_HOME_ID_KEYS = ("home_team_id", "home_team", "home_id")
_AWAY_ID_KEYS = ("away_team_id", "away_team", "away_id")
_HOME_GOAL_KEYS = ("home_score", "home_goals", "home_team_goals", "home_goals_scored")
_AWAY_GOAL_KEYS = ("away_score", "away_goals", "away_team_goals", "away_goals_scored")
_DATE_KEYS = ("date_time_utc", "date_time", "game_date", "date")


def _pick(row, keys):
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _team_key(value):
    """Team ids arrive as a bare string on team endpoints and occasionally as a
    single-element list; normalise before using one as a dict key (round 15)."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def normalize_games(rows):
    """Turn whatever a per-game endpoint returned into
    [{game_id, date, home_id, away_id, home_goals, away_goals}], keeping only
    rows that carry BOTH scorelines.

    A fixture that has not been played yet comes back with null scores on
    every shape of this endpoint observed anywhere, so "no score" means "not
    a result" and dropping it is correct rather than lossy. Returns [] for an
    unusable payload, which is the signal the caller falls back on.
    """
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        home = _team_key(_pick(row, _HOME_ID_KEYS))
        away = _team_key(_pick(row, _AWAY_ID_KEYS))
        hg = _pick(row, _HOME_GOAL_KEYS)
        ag = _pick(row, _AWAY_GOAL_KEYS)
        if home is None or away is None:
            continue
        if not isinstance(hg, (int, float)) or not isinstance(ag, (int, float)):
            continue
        out.append({
            "game_id": row.get("game_id", row.get("id")),
            "date": _pick(row, _DATE_KEYS) or "",
            "home_id": home, "away_id": away,
            "home_goals": int(hg), "away_goals": int(ag),
        })
    # Chronological, because Elo is path-dependent and an unordered replay
    # would produce a different (and meaningless) set of ratings.
    out.sort(key=lambda g: (str(g["date"]), str(g["game_id"] or "")))
    return out


def records_from_games(games, abbr_of):
    """{abbr: {"w","d","l","gp","gf","ga","pts"}} counted off real scorelines."""
    rec = {}

    def slot(abbr):
        return rec.setdefault(abbr, {"w": 0, "d": 0, "l": 0, "gp": 0,
                                     "gf": 0, "ga": 0, "pts": 0})

    for g in games:
        home = abbr_of.get(g["home_id"], g["home_id"])
        away = abbr_of.get(g["away_id"], g["away_id"])
        h, a = slot(home), slot(away)
        h["gp"] += 1; a["gp"] += 1
        h["gf"] += g["home_goals"]; h["ga"] += g["away_goals"]
        a["gf"] += g["away_goals"]; a["ga"] += g["home_goals"]
        if g["home_goals"] > g["away_goals"]:
            h["w"] += 1; h["pts"] += 3; a["l"] += 1
        elif g["home_goals"] < g["away_goals"]:
            a["w"] += 1; a["pts"] += 3; h["l"] += 1
        else:
            h["d"] += 1; a["d"] += 1; h["pts"] += 1; a["pts"] += 1
    return rec


def derived_league_draws(team_rows):
    """Exact league-wide draw count from points and games played, or None.

    A decided match adds 3 points to the league total, a draw adds 2, so
    draws = 3 * matches - total points. Returns (draws, matches) or None when
    either input is missing on any team (a partial sum would be wrong, not
    approximate).
    """
    total_points = 0
    total_gp = 0
    for t in team_rows:
        if t.get("points") is None or t.get("games") is None:
            return None
        total_points += t["points"]
        total_gp += t["games"]
    if total_gp % 2 != 0:
        # An odd total means the league table is mid-update (one side of a
        # fixture counted and not the other); the arithmetic below would be
        # off by a fraction of a match, so say nothing instead.
        return None
    matches = total_gp // 2
    draws = 3 * matches - total_points
    if draws < 0 or draws > matches:
        return None
    return draws, matches


def build_table(team_rows, games=None):
    """team_rows: the dicts fetch_team_charts already assembles, extended with
    goals_for / goals_against / goal_difference / xgd / xpoints.
    games: normalize_games() output, or None/[] when no per-game endpoint
    answered.

    Returns (rows, basis, reconciliation) where rows are sorted league-table
    order (points, then goal difference, then goals for) and carry:

        rank, abbr, team, gp, w, d, l, pts, gf, ga, gd, xgd, xpts, ppg

    w/d/l are None on the totals path -- never zero, because zero is a claim
    and None is the truth. reconciliation is a list of human-readable strings
    describing any disagreement found between counted and published points.
    """
    abbr_of = {}
    for t in team_rows:
        if t.get("team_id"):
            abbr_of[t["team_id"]] = t["abbr"]

    games = games or []
    basis = "games" if games else "totals"
    rec = records_from_games(games, abbr_of) if games else {}
    reconciliation = []

    rows = []
    for t in team_rows:
        counted = rec.get(t["abbr"])
        gp = t.get("games")
        pts = t.get("points")
        gf = t.get("goals_for")
        ga = t.get("goals_against")
        w = d = l = None

        if counted:
            w, d, l = counted["w"], counted["d"], counted["l"]
            # Published totals win any disagreement -- they are the league's
            # own record -- but the disagreement is reported, never swallowed.
            if pts is not None and counted["pts"] != pts:
                reconciliation.append(
                    f"{t['abbr']}: {counted['pts']} points counted from "
                    f"{counted['gp']} games, {pts} published")
            if gp is not None and counted["gp"] != gp:
                reconciliation.append(
                    f"{t['abbr']}: {counted['gp']} games in the results feed, "
                    f"{gp} published")
            gp = gp if gp is not None else counted["gp"]
            pts = pts if pts is not None else counted["pts"]
            gf = gf if gf is not None else counted["gf"]
            ga = ga if ga is not None else counted["ga"]

        gd = t.get("goal_difference")
        if gd is None and gf is not None and ga is not None:
            gd = gf - ga

        rows.append({
            "abbr": t["abbr"], "team": t["name"],
            "gp": gp, "w": w, "d": d, "l": l, "pts": pts,
            "gf": gf, "ga": ga, "gd": gd,
            "xgd": t.get("xgd"), "xpts": t.get("xpoints"),
            "ppg": (pts / gp) if (pts is not None and gp) else None,
        })

    # League-table order. A missing points value sorts last rather than as a
    # zero -- same rule the data tables use for absent numbers.
    def key(r):
        return (r["pts"] is None,
                -(r["pts"] or 0), -(r["gd"] or 0), -(r["gf"] or 0), r["team"])

    rows.sort(key=key)
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return rows, basis, reconciliation


def xg_rank_gaps(rows):
    """Where the table and the xG rank each other most differently.

    Returns [{abbr, team, table_rank, xgd_rank, gap, direction}] widest first.
    `direction` is "over" when a team sits higher in the table than its xG
    difference says (results ahead of performance) and "under" for the
    reverse. This is the tab's story point: the table's own most notable
    disagreement with the rest of the dashboard.
    """
    with_xgd = [r for r in rows if r.get("xgd") is not None]
    if len(with_xgd) < 2:
        return []
    by_xgd = sorted(with_xgd, key=lambda r: -r["xgd"])
    xgd_rank = {r["abbr"]: i + 1 for i, r in enumerate(by_xgd)}
    out = []
    for r in with_xgd:
        gap = xgd_rank[r["abbr"]] - r["rank"]
        out.append({
            "abbr": r["abbr"], "team": r["team"], "table_rank": r["rank"],
            "xgd_rank": xgd_rank[r["abbr"]], "gap": abs(gap),
            "direction": "over" if gap > 0 else ("under" if gap < 0 else "level"),
        })
    out.sort(key=lambda d: (-d["gap"], d["table_rank"]))
    return out


# ------------------------------------------------------------------ self-test

if __name__ == "__main__":
    teams = [
        {"team_id": "A", "abbr": "AAA", "name": "Alpha", "points": 7, "games": 3,
         "goals_for": 6, "goals_against": 2, "goal_difference": 4, "xgd": 3.0},
        {"team_id": "B", "abbr": "BBB", "name": "Bravo", "points": 4, "games": 3,
         "goals_for": 4, "goals_against": 4, "goal_difference": 0, "xgd": 4.0},
        {"team_id": "C", "abbr": "CCC", "name": "Charlie", "points": 1, "games": 2,
         "goals_for": 1, "goals_against": 5, "goal_difference": -4, "xgd": -5.0},
    ]
    games_raw = [
        {"game_id": "g1", "date_time_utc": "2026-03-01", "home_team_id": "A",
         "away_team_id": "B", "home_score": 3, "away_score": 1},
        {"game_id": "g2", "date_time_utc": "2026-03-08", "home_team_id": "B",
         "away_team_id": "C", "home_score": 2, "away_score": 0},
        {"game_id": "g3", "date_time_utc": "2026-03-15", "home_team_id": "C",
         "away_team_id": "A", "home_score": 1, "away_score": 1},
        # An unplayed fixture: must be dropped, not counted 0-0.
        {"game_id": "g4", "date_time_utc": "2026-03-22", "home_team_id": "A",
         "away_team_id": "C", "home_score": None, "away_score": None},
    ]
    games = normalize_games(games_raw)
    assert len(games) == 3, "unplayed fixture must not become a 0-0"
    assert [g["game_id"] for g in games] == ["g1", "g2", "g3"], "must sort by date"
    print(f"normalize_games: {len(games)} results, unplayed fixture dropped")

    rows, basis, recon = build_table(teams, games)
    assert basis == "games"
    top = rows[0]
    assert top["abbr"] == "AAA" and (top["w"], top["d"], top["l"]) == (1, 1, 0), top
    # A's third "game" is the unplayed one; published gp=3 vs 2 counted, so the
    # mismatch MUST be reported rather than silently reconciled.
    assert any("AAA" in m for m in recon), recon
    print(f"results path: {rows[0]['team']} {rows[0]['w']}-{rows[0]['d']}-{rows[0]['l']}, "
          f"{len(recon)} reconciliation note(s)")

    rows_t, basis_t, recon_t = build_table(teams, None)
    assert basis_t == "totals" and recon_t == []
    assert all(r["w"] is None and r["d"] is None and r["l"] is None for r in rows_t), \
        "the totals path must report W/D/L as absent, never as zero"
    assert [r["abbr"] for r in rows_t] == ["AAA", "BBB", "CCC"]
    print("totals path: ok (W/D/L absent, not zeroed)")

    # Two clean seasons, checked by hand. Four team-games = two matches.
    # One win + one draw each way: 4 + 1 = 5 points, so 3*2 - 5 = 1 draw.
    one_draw = [{"team_id": "A", "abbr": "AAA", "name": "Alpha", "points": 4, "games": 2},
                {"team_id": "B", "abbr": "BBB", "name": "Bravo", "points": 1, "games": 2}]
    assert derived_league_draws(one_draw) == (1, 2), derived_league_draws(one_draw)
    # Both matches decided: 6 points over 2 matches, so no draws.
    no_draw = [{"team_id": "A", "abbr": "AAA", "name": "Alpha", "points": 6, "games": 2},
               {"team_id": "B", "abbr": "BBB", "name": "Bravo", "points": 0, "games": 2}]
    assert derived_league_draws(no_draw) == (0, 2), derived_league_draws(no_draw)
    # An odd number of team-games means the feed is mid-update: say nothing.
    odd = [dict(one_draw[0]), dict(one_draw[1])]
    odd[0]["games"] = 3
    assert derived_league_draws(odd) is None
    # A missing field is absent, not zero: decline rather than undercount.
    missing = [dict(one_draw[0]), {**one_draw[1], "points": None}]
    assert derived_league_draws(missing) is None
    print("derived league draws: 1/2 and 0/2 exact; odd team-game count declines to answer")

    gaps = xg_rank_gaps(rows)
    assert gaps and gaps[0]["gap"] >= 1
    print(f"widest table-vs-xG gap: {gaps[0]['team']} "
          f"(#{gaps[0]['table_rank']} table, #{gaps[0]['xgd_rank']} xGD)")

    print("\nall assertions passed")
