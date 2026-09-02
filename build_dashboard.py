"""
Builds the full NWSL analytics dashboard (dashboard.html) from LIVE data via
the ASA API: team xGF-vs-xGA, team xG differential, team Goals Added,
player goals-vs-xG, player xG-vs-xA, shot quality, playmaking style, a
player Goals Added leaderboard, goalkeepers, and a team-roster comparison
tab -- all in one tabbed, self-contained HTML file.

Round 10 (2026-08-12) additions: a new Team Goals Added tab (team-level g+
net of value conceded -- see chart_builders.build_team_goals_added_chart,
fetched here in one call to /teams/goals-added since that endpoint returns
every team without needing a team_id filter), and Playmaking Style now
shown per 96 minutes (using the minutes_played field that already rides
along on every /players/goals-added row).

Round 13 (2026-08-12): the player pool feeding Goals vs. xG, xG vs. xA,
Shot Quality, and Playmaking Style is no longer artificially cut down to a
top-N leaderboard before plotting. fetch_player_pool() already pulled every
player above --minutes across all 16 teams (no team_id filter) -- the
scatter charts were just throwing most of that away by slicing to the top
20 by combined xG+xA (and Playmaking Style was further, accidentally,
capped to the Goals Added leaderboard's top 15). Both caps are gone; --top-n
now controls only the Goals Added bar chart, where a ranked leaderboard
still makes sense to cap for readability. See chart_builders.py's
scatter_display_params() for how the scatter charts stay readable at
100-250+ points instead of 20.

Run on your own machine (unrestricted network):
    pip install requests
    python build_dashboard.py --season 2026 --minutes 500 --top-n 20

For a hands-off weekly refresh, see run_weekly_update.sh -- it's a thin
wrapper around this exact command, meant to run from cron (or Task
Scheduler on Windows) on a machine with normal internet access. No Claude
session or tokens are involved in that path at all; this script only talks
to the ASA API directly.

Follows the project's Design Guidelines doc: each chart picks a single
"story point" from whatever data comes back that day (the biggest gap, the
biggest overperformer, the league leader) and phrases the chart title as
that finding, not the metric name. Re-run this later in the season and the
highlighted team/player will change as the data does -- nothing here is
hardcoded to today's standings.

This file is a thin orchestrator: it fetches data with `requests` and hands
it to chart_builders.py, which holds the actual chart-construction logic
shared with demo_dashboard.py. If you're changing what a chart shows or how
a story point is picked, edit chart_builders.py, not this file -- it'll
apply to both the live and demo dashboards at once.

This is also the natural base for turning this into an actual webapp --
see the README's "From dashboard to webapp" section for what changes.
"""

import argparse
import datetime
import sys

import requests

import chart_builders
from chart_builders import (
    build_finishing_creation_shotquality, build_methods_chart, build_mvp_chart,
    build_placement_chart, build_position_gap_chart, build_set_piece_chart, build_story_lede,
    build_team_charts, build_team_compare_chart, build_team_goals_added_chart,
    per96, rows_to_csv, scatter_display_params,
)
from chart_builders import qualification_phrase
from dashboard_template import render_dashboard
from glossary import GLOSSARY_SECTION
import qualification

BASE_URL = "https://app.americansocceranalysis.com/api/v1/nwsl"

# Where this dashboard is published. Used only to build absolute og:url and
# og:image values for the social-preview meta tags -- a relative og:image is
# silently dropped by every link scraper, so it has to be spelled out here.
# Override per-run with --site-url, or pass "" to omit the tags.
SITE_URL = "https://duransound.github.io/nwsl-dashboard/"


# --------------------------------------------------------------------------
# Transfer-aware team attribution (added 2026-09-02)
#
# /players/xgoals returns team_id as a LIST, and for a player who changed
# clubs mid-season that list holds TWO entries with every metric summed across
# both. Round 15's fix unwrapped it with [0] on the stated assumption that one
# element was the only shape ever observed. Six players in 2026 disprove that,
# and the array's order carries no reliable meaning: [0] names the club they
# played MORE for in three of the six cases and LESS in the other three.
# Lilly Reale reads Gotham-first on 629 minutes at Gotham and 903 at Boston.
#
# Adding a team_id filter makes ASA return the per-club split, and the parts
# reconcile to the whole exactly -- verified live for all six players on both
# minutes and xG. So the club is resolved from real minutes instead of from
# array position. Two calls per transferred player, cached for the rest of the
# run, and every single-club player (239 of 245) costs nothing.
# --------------------------------------------------------------------------

_TEAM_SPLIT_CACHE = {}


def resolve_team_id(season, row):
    """The club this player actually featured for most this season."""
    team_id = row.get("team_id")
    if not isinstance(team_id, list):
        return team_id
    if len(team_id) == 1:
        return team_id[0]

    player_id = row.get("player_id")
    if not player_id:
        # A team-level row (e.g. /teams/goals-added): nothing to split.
        return team_id[0]
    if player_id in _TEAM_SPLIT_CACHE:
        return _TEAM_SPLIT_CACHE[player_id]

    best, best_minutes = team_id[0], -1.0
    for candidate in team_id:
        try:
            rows = requests.get(
                f"{BASE_URL}/players/xgoals",
                params={"season_name": season, "player_id": player_id,
                        "team_id": candidate, "minimum_minutes": 0},
                timeout=30).json()
        except Exception as exc:                              # noqa: BLE001
            # Non-fatal: an unresolved player keeps the old [0] behaviour
            # rather than dropping off the dashboard entirely.
            print(f"  !! split lookup failed for {player_id}/{candidate} ({exc}); "
                  f"keeping the first listed club")
            continue
        for split in rows:
            minutes = split.get("minutes_played", split.get("minutes", 0)) or 0
            if minutes > best_minutes:
                best, best_minutes = candidate, minutes

    _TEAM_SPLIT_CACHE[player_id] = best
    return best


def get_teams():
    return {t["team_id"]: t for t in requests.get(f"{BASE_URL}/teams", timeout=30).json()}


def get_players():
    return {p["player_id"]: p["player_name"] for p in requests.get(f"{BASE_URL}/players", timeout=60).json()}


def fetch_team_charts(season, teams):
    rows = requests.get(f"{BASE_URL}/teams/xgoals", params={"season_name": season}, timeout=30).json()
    team_rows = [
        {
            "abbr": teams.get(r["team_id"], {}).get("team_abbreviation", r["team_id"]),
            "name": teams.get(r["team_id"], {}).get("team_name", r["team_id"]),
            "xgf": r["xgoals_for"], "xga": r["xgoals_against"],
            # Carried for the MVP tab's team-success component. Ignored by
            # build_team_charts (it only reads abbr/name/xgf/xga), and .get()
            # rather than [] because this field has never been confirmed on a
            # live /teams/xgoals row -- mvp_tracker.team_strength() falls back to
            # xG differential if it comes back None, so a missing `points`
            # degrades the one component instead of breaking the run.
            "points": r.get("points"),
            # Games played, for the games-scaled minutes rule (see
            # qualification.py). Same defensive treatment as `points` above:
            # tried under three names because ASA's field naming has already
            # bitten this file twice (round 15), and a team missing a value
            # falls back to the league median inside Qualification rather
            # than being dropped.
            "games": r.get("count_games", r.get("games", r.get("games_played"))),
        }
        for r in rows
    ]
    # Returns team_rows as well so main() can build the MVP chart without a
    # second /teams/xgoals call.
    return build_team_charts(team_rows) + (team_rows,)


def fetch_team_goals_added(season, teams):
    """One call gets every team at once (unlike the player-level endpoint,
    /teams/goals-added has no team_id filter requirement to return everyone),
    so this is cheap on the live path -- no per-team looping needed.

    Bug fix (round 15, caught by a real live run): each row is NOT a flat
    {team_id, goals_added_for, goals_added_against} record -- like the
    player-level /players/goals-added endpoint, it nests a per-action-type
    breakdown under `data` (confirmed via a live fetch: each row is
    {team_id, minutes, data: [{action_type, num_actions_for,
    goals_added_for, num_actions_against, goals_added_against}, ...]} across
    the 6-7 action categories). The original code read goals_added_for/
    goals_added_against directly off the row, which KeyErrors on live data
    every time -- this had never actually been exercised against the live
    API before now (round 10 built and verified it only against the demo
    snapshot, which hardcodes already-summed team totals). Fixed by summing
    across each team's `data` list, the same pattern already used for the
    player-level endpoint elsewhere in this file."""
    rows = requests.get(f"{BASE_URL}/teams/goals-added", params={"season_name": season}, timeout=30).json()
    totals = {}
    for r in rows:
        team_id = resolve_team_id(season, r)
        t = totals.setdefault(team_id, {"ga_for": 0.0, "ga_against": 0.0})
        for action in r.get("data", []):
            t["ga_for"] += action.get("goals_added_for", 0.0)
            t["ga_against"] += action.get("goals_added_against", 0.0)
    return build_team_goals_added_chart([
        {
            "abbr": teams.get(team_id, {}).get("team_abbreviation", team_id),
            "name": teams.get(team_id, {}).get("team_name", team_id),
            "ga_for": v["ga_for"], "ga_against": v["ga_against"],
        }
        for team_id, v in totals.items()
    ])


def fetch_penalty_totals(season, minimum_minutes):
    """Per-player penalty shots/goals/xG, so the finishing charts can work in
    NON-PENALTY terms (round 22).

    ASA doesn't publish an npxG field, but /players/xgoals accepts a
    `shot_pattern` filter, so the penalty component is obtainable by asking
    the same endpoint the same question with shot_pattern=Penalty and
    subtracting. Verified live 2026-08-13: the filtered call returns the same
    row shape with the metrics recomputed over penalties only (a fullback who
    has never taken one comes back with shots 0 / xgoals 0 rather than being
    dropped), and the six shot patterns sum exactly to the unfiltered row.

    One call, not one per player. Missing players are treated as zero
    penalties, which is correct: the filtered response is not guaranteed to
    carry every player the unfiltered one does, and "absent from the penalty
    query" means "took no penalties"."""
    rows = requests.get(f"{BASE_URL}/players/xgoals",
                        params={"season_name": season, "minimum_minutes": minimum_minutes,
                                "shot_pattern": "Penalty"}, timeout=30).json()
    out = {}
    for r in rows:
        out[r["player_id"]] = {
            "shots": r.get("shots", 0) or 0,
            "goals": r.get("goals", 0) or 0,
            "xg": r.get("xgoals", 0.0) or 0.0,
            # Round 31: the placement component of the penalties, so the
            # Placement vs. Luck tab can strip them out of both sides of its
            # split the same way every other finishing view does.
            "xplace": r.get("xplace", 0.0) or 0.0,
        }
    return out


def fetch_player_pool(season, qual, teams, players):
    """`qual` is a qualification.Qualification, not a bare minutes number.

    ASA's `minimum_minutes` parameter is a single league-wide value and
    cannot express a per-team rule, so the pattern here (and in every other
    player-level fetch in this file) is: ask the API for the LOWEST per-team
    threshold, so the server can never drop somebody the per-team rule would
    have kept, then apply the real per-team test client-side once each row's
    team is known. At 16-20 games played across the league that means
    fetching at 480 while the actual bars run 480-600.
    """
    floor = qual.api_floor
    rows = requests.get(f"{BASE_URL}/players/xgoals",
                         params={"season_name": season, "minimum_minutes": floor}, timeout=30).json()
    pens = fetch_penalty_totals(season, floor)
    out = []
    for r in rows:
        # Round 15 bug fix: /players/xgoals returns team_id as a LIST (like
        # /players/goals-added and /goalkeepers/xgoals elsewhere in this
        # file, both of which already normalize it) -- a bare
        # teams.get(r["team_id"], ...) TypeErrors with "unhashable type:
        # list" the moment this runs against live data. Same fix as those:
        # unwrap to the first (only observed) element before using it as a
        # dict key.
        team_id = resolve_team_id(season, r)
        # Round 15 bug fix #3: bare `minutes` isn't on this row either --
        # /players/goals-added, /goalkeepers/xgoals, and /teams/goals-added
        # (all confirmed live this same round) return `minutes_played`
        # instead. Trying that first, falling back to `minutes`, means this
        # works whichever name /players/xgoals actually uses -- couldn't get
        # a fresh live read to confirm which (the API's robots.txt check was
        # timing out when this was fixed), so defensive beats a guess here.
        minutes = r.get("minutes_played", r.get("minutes", 0))
        pen = pens.get(r["player_id"], {"shots": 0, "goals": 0, "xg": 0.0, "xplace": 0.0})
        # max(..., 0) guards the one way this subtraction can go wrong: the two
        # calls are independent snapshots, so a match finishing between them
        # could leave a penalty in the filtered total that isn't in the
        # unfiltered one yet. A negative npxG would silently poison the
        # variance math downstream; clamping loses nothing real.
        out.append({
            "id": r["player_id"], "name": players.get(r["player_id"], r["player_id"]),
            "team": teams.get(team_id, {}).get("team_abbreviation", team_id),
            "minutes": minutes, "xg": r["xgoals"], "xa": r["xassists"],
            "goals": r["goals"], "shots": r.get("shots", 0),
            "npxg": max(r["xgoals"] - pen["xg"], 0.0),
            "npgoals": max(r["goals"] - pen["goals"], 0),
            "npshots": max(r.get("shots", 0) - pen["shots"], 0),
            "pen_shots": pen["shots"], "pen_goals": pen["goals"], "pen_xg": pen["xg"],
            # Round 31. ASA never documents this field; see
            # chart_builders.build_placement_chart for what it is taken to mean
            # and the reconciliation that supports the reading.
            "xplace": r.get("xplace"), "pen_xplace": pen.get("xplace", 0.0),
        })
    # The client-side half of the rule -- see the docstring. Done after the
    # row is assembled because `team` isn't known until team_id is unwrapped.
    return qual.filter(out)


def fetch_set_piece_split(season, teams):
    """Team xG split into open play vs. dead balls, for the Open Play vs. Set
    Pieces tab.

    Four extra calls rather than six: ASA's six shot patterns are mutually
    exclusive and exhaustive (verified live -- see chart_builders'
    DEAD_BALL_PATTERNS comment for the arithmetic), so open play is derivable
    as the unfiltered total minus the three dead-ball patterns minus
    penalties. Each pattern-filtered row carries both xgoals_for and
    xgoals_against, so one pass gives both sides of the ball."""
    def pull(pattern=None):
        params = {"season_name": season}
        if pattern:
            params["shot_pattern"] = pattern
        rows = requests.get(f"{BASE_URL}/teams/xgoals", params=params, timeout=30).json()
        return {r["team_id"]: r for r in rows}

    total = pull()
    dead = [pull(p) for p in chart_builders.DEAD_BALL_PATTERNS]
    pens = pull(chart_builders.PENALTY_PATTERN)

    out = []
    for team_id, row in total.items():
        dead_for = sum(d.get(team_id, {}).get("xgoals_for", 0.0) for d in dead)
        dead_against = sum(d.get(team_id, {}).get("xgoals_against", 0.0) for d in dead)
        pen_for = pens.get(team_id, {}).get("xgoals_for", 0.0)
        pen_against = pens.get(team_id, {}).get("xgoals_against", 0.0)
        out.append({
            "abbr": teams.get(team_id, {}).get("team_abbreviation", team_id),
            "name": teams.get(team_id, {}).get("team_name", team_id),
            "op_for": max(row["xgoals_for"] - dead_for - pen_for, 0.0),
            "op_against": max(row["xgoals_against"] - dead_against - pen_against, 0.0),
            "dead_for": dead_for, "dead_against": dead_against,
        })
    return out


# ASA's own position vocabulary. general_position is documented as a FILTER on
# the goals-added endpoints, so positions are obtained by making one call per
# value and tagging rows by which call returned them -- this works whether or not
# the field is also present on the response rows, which it has never been
# confirmed to be.
OUTFIELD_POSITIONS = ["CB", "FB", "DM", "CM", "AM", "W", "ST"]


def fetch_position_gaps(season, qual, teams, players):
    """Position Gaps tab: g+ ABOVE REPLACEMENT for every position.

    Eight requests -- seven outfield positions against /players/goals-added, plus
    goalkeepers against /goalkeepers/goals-added, since keepers have their own
    action types (Claiming, Fielding, Handling, Passing, Shotstopping, Sweeping)
    and don't appear in the outfield endpoint.

    above_replacement=true is what makes the columns comparable: it grades each
    player against replacement level at their own position, so a defender's value
    means the same thing as a striker's. It also returns aggregated g+ rather
    than the per-action breakdown -- position_gaps handles either shape.

    A failure on any single position is caught and logged rather than aborting
    the whole dashboard: a missing column renders as "no data", which the grid
    already displays honestly.
    """
    abbr_of = {tid: t.get("team_abbreviation", tid) for tid, t in teams.items()}
    rows_by_position = {}
    # Same api_floor / client-side-filter split as fetch_player_pool -- see
    # its docstring. Fetch at the lowest per-team bar, then drop anyone below
    # their OWN team's bar once team_abbr is resolved.
    floor = qual.api_floor

    def tag(rows):
        out = []
        for r in rows:
            team_id = resolve_team_id(season, r)
            abbr = abbr_of.get(team_id, team_id)
            # Minutes live under either name depending on endpoint (the
            # round-15 lesson); position_gaps._minutes() reads both, so the
            # row shape is left alone and only the test is done here.
            minutes = r.get("minutes_played", r.get("minutes", 0))
            if not qual.qualifies(abbr, minutes):
                continue
            out.append({**r, "team_abbr": abbr})
        return out

    for position in OUTFIELD_POSITIONS:
        try:
            resp = requests.get(
                f"{BASE_URL}/players/goals-added",
                params={"season_name": season, "minimum_minutes": floor,
                        "general_position": position, "above_replacement": "true"},
                timeout=30)
            resp.raise_for_status()
            rows_by_position[position] = tag(resp.json())
        except Exception as exc:                      # noqa: BLE001
            print(f"  !! {position} fetch failed ({exc}); column will show as no data")
            rows_by_position[position] = []

    try:
        resp = requests.get(
            f"{BASE_URL}/goalkeepers/goals-added",
            params={"season_name": season, "minimum_minutes": floor,
                    "above_replacement": "true"},
            timeout=30)
        resp.raise_for_status()
        rows_by_position["GK"] = tag(resp.json())
    except Exception as exc:                          # noqa: BLE001
        print(f"  !! GK fetch failed ({exc}); column will show as no data")
        rows_by_position["GK"] = []

    counts = ", ".join(f"{p}:{len(rows_by_position.get(p, []))}"
                       for p in ["GK"] + OUTFIELD_POSITIONS)
    print(f"  -> rows per position: {counts}")
    return rows_by_position


def build_goals_added_chart(season, qual, leaderboard_n, teams, players):
    """leaderboard_n caps only the Goals Added bar chart -- a ranked
    leaderboard genuinely reads better at ~20 bars than at 150+. Playmaking
    Style is a scatter, not a ranking, so it's built from the FULL fetched
    pool (every player above minimum_minutes), not just the leaderboard_n
    leaders -- previously it was accidentally coupled to the leaderboard
    cutoff, which meant a player with a great passing/dribbling split but a
    lower total g+ would never show up on that chart at all."""
    rows = requests.get(f"{BASE_URL}/players/goals-added",
                         params={"season_name": season, "minimum_minutes": qual.api_floor}, timeout=30).json()
    qual_phrase = qualification_phrase(qual)
    scored = []
    ga_by_player = {}
    for r in rows:
        by_action = {a["action_type"]: a["goals_added_above_avg"] for a in r["data"]}
        total = sum(by_action.values())
        team_id = resolve_team_id(season, r)
        name = players.get(r["player_id"], r["player_id"])
        abbr = teams.get(team_id, {}).get("team_abbreviation", team_id)
        # Client-side half of the games-scaled rule (see fetch_player_pool).
        if not qual.qualifies(abbr, r.get("minutes_played", r.get("minutes", 0))):
            continue
        scored.append({
            "player_id": r["player_id"],
            "name": name,
            "label": f'{name} ({abbr})',
            "team": abbr,
            "value": total,
        })
        # minutes_played rides along on every /players/goals-added row, so the
        # live path can convert Playmaking Style to per-96 with no extra
        # fetch -- unlike the demo snapshot, which had to backfill 4 players'
        # minutes individually (see chart_builders.py / project doc).
        ga_by_player[r["player_id"]] = {
            "total": total, "by_action": by_action, "minutes": r.get("minutes_played", 0),
        }
    scored.sort(key=lambda d: d["value"], reverse=True)
    top_rows = scored[:leaderboard_n]
    leader = top_rows[0]

    chart_goals_added = {
        "type": "diverging-bar", "tabLabel": "Goals Added",
        "metricLabel": "Goals Added (g+), all action types combined",
        "title": f"{leader['name']} leads the league in total on-ball contribution",
        "blurb": f"ASA's other headline metric — possession-value contribution (dribbling + fouling + interrupting + passing + receiving + shooting) above average for the position, summed across categories. Top {leaderboard_n} among qualifying players ({qual_phrase}; {len(scored)} qualify).",
        "valueLabel": "Goals Added", "xAxisLabel": "Goals Added (g+)",
        "footnote": "“Above average” is relative to other players in the same general position.",
        "data": [{"label": d["label"], "value": d["value"], "highlight": d is leader} for d in top_rows],
    }

    # --- Chart: playmaking style -- Dribbling g+ vs Passing g+ across every
    # player who qualified for the /players/goals-added pull (not just the
    # leaderboard_n leaders above -- see docstring). Story point = the
    # biggest passing-over-dribbling skew league-wide. ---
    playmaking_pool = []
    for d in scored:
        entry = ga_by_player.get(d["player_id"], {})
        ga = entry.get("by_action", {})
        drib = ga.get("Dribbling", 0.0)
        passing = ga.get("Passing", 0.0)
        minutes = entry.get("minutes", 0)
        playmaking_pool.append({
            "player_id": d["player_id"], "name": d["name"], "drib": drib, "passing": passing,
            "minutes": minutes, "drib96": per96(drib, minutes), "passing96": per96(passing, minutes),
            "team": d["team"],
        })
    most_pass_skewed = max(playmaking_pool, key=lambda d: d["passing96"] - d["drib96"])
    pm_radius, pm_show_badges = scatter_display_params(len(playmaking_pool))

    chart_playmaking = {
        "type": "scatter", "tabLabel": "Playmaking Style",
        "metricLabel": "Goals Added: Dribbling vs. Passing, per 96 minutes",
        "title": f"{most_pass_skewed['name']} creates almost entirely through passing, not dribbling"
                 if most_pass_skewed["passing96"] >= most_pass_skewed["drib96"]
                 else f"{most_pass_skewed['name']} creates far more through dribbling than passing",
        "blurb": f"All {len(playmaking_pool)} qualifying players ({qual_phrase}), split into two of the metric's six action categories — value created by beating defenders on the dribble (right) vs. value created by passing (up), shown per 96 minutes so players with different minutes played are compared fairly.",
        "xAxisLabel": "Dribbling g+ per 96 min", "yAxisLabel": "Passing g+ per 96 min",
        "radius": pm_radius, "showBadges": pm_show_badges,
        "data": [
            {"x": round(d["drib96"], 4), "y": round(d["passing96"], 4), "badge": d["team"],
             "tooltip": f'<div class="name">{d["name"]}</div><div class="row">{d["team"]} &middot; {d["minutes"]} min</div><div class="row">Dribbling {d["drib"]:+.2f} g+ ({d["drib96"]:+.3f}/96) &middot; Passing {d["passing"]:+.2f} g+ ({d["passing96"]:+.3f}/96)</div>',
             "highlight": d["player_id"] == most_pass_skewed["player_id"],
             "annotation": f"{d['name'].split()[-1]}: {d['passing96']:+.3f} g+/96 passing vs. {d['drib96']:+.3f} g+/96 dribbling" if d["player_id"] == most_pass_skewed["player_id"] else None}
            for d in playmaking_pool
        ],
    }

    ga_lookup = {pid: v["total"] for pid, v in ga_by_player.items()}
    # `rows` (raw, still nested under "data") rides along for the MVP tab --
    # summing here is lossy and re-fetching would double this endpoint's calls.
    return chart_goals_added, chart_playmaking, ga_lookup, rows


def build_goalkeeper_chart(season, qual, teams, players):
    rows = requests.get(f"{BASE_URL}/goalkeepers/xgoals",
                         params={"season_name": season, "minimum_minutes": qual.api_floor}, timeout=30).json()
    for r in rows:
        r["gk_name"] = players.get(r["player_id"], r["player_id"])
        team_id = resolve_team_id(season, r)
        r["abbr"] = teams.get(team_id, {}).get("team_abbreviation", team_id)
        r["gsae"] = r["xgoals_gk_faced"] - r["goals_conceded"]
        r["minutes"] = r.get("minutes_played", 0)
        r["shots96"] = per96(r["shots_faced"], r["minutes"])

    # Client-side half of the rule, after abbr/minutes are normalised above.
    rows = [r for r in rows if qual.qualifies(r["abbr"], r["minutes"])]

    if not rows:
        return None
    leader = max(rows, key=lambda r: r["gsae"])
    gk_radius, gk_show_badges = scatter_display_params(len(rows))

    return {
        "type": "scatter", "tabLabel": "Goalkeepers",
        "metricLabel": "Shots Faced vs. Goals Saved Above Expected, per 96 minutes",
        "title": f"{leader['gk_name']} is saving more than any other keeper in the league",
        "blurb": f"All {len(rows)} qualifying goalkeepers ({qualification_phrase(qual)}). Shots faced per 96 minutes (right, workload) vs. goals prevented relative to the quality of shots faced (up, axis is xG on target minus goals actually conceded — positive means outperforming expectation).",
        "xAxisLabel": "Shots faced per 96 min", "yAxisLabel": "Goals saved above expected",
        "radius": gk_radius, "showBadges": gk_show_badges,
        "data": [
            {"x": round(r["shots96"], 4), "y": round(r["gsae"], 3), "badge": r["abbr"],
             "tooltip": f'<div class="name">{r["gk_name"]}</div><div class="row">{r["abbr"]} &middot; {r["shots_faced"]} shots faced ({r["shots96"]:.1f}/96)</div><div class="row">Goals saved above expected: {r["gsae"]:+.2f}</div>',
             "highlight": r["player_id"] == leader["player_id"],
             "annotation": f"{leader['gk_name']}: {leader['gsae']:+.1f} on {leader['shots96']:.1f} shots/96" if r["player_id"] == leader["player_id"] else None}
            for r in rows
        ],
    }


def fetch_team_compare_chart(season, minimum_minutes, teams, players, ga_lookup):
    """Pulls a low-minutes-floor player pool so every team gets a full roster,
    not just the top_n leaderboard cutoff used elsewhere on the dashboard."""
    rows = requests.get(f"{BASE_URL}/players/xgoals",
                         params={"season_name": season, "minimum_minutes": max(1, min(minimum_minutes, 90))},
                         timeout=30).json()
    roster_rows = []
    team_names = {}
    for r in rows:
        # Same round-15 fix as fetch_player_pool -- /players/xgoals returns
        # team_id as a list, not a bare string.
        team_id = resolve_team_id(season, r)
        abbr = teams.get(team_id, {}).get("team_abbreviation", team_id)
        team_names[abbr] = teams.get(team_id, {}).get("team_name", abbr)
        minutes = r.get("minutes_played", r.get("minutes", 0))
        roster_rows.append({
            "id": r["player_id"], "name": players.get(r["player_id"], r["player_id"]), "team": abbr,
            "minutes": minutes, "xg": r["xgoals"], "xa": r["xassists"],
            "goals": r["goals"], "shots": r.get("shots", 0),
        })
    return build_team_compare_chart(roster_rows, team_names, ga_lookup, cap=18)


def main():
    parser = argparse.ArgumentParser(description="Build the full NWSL analytics dashboard from live ASA data.")
    parser.add_argument("--season", default="2026")
    parser.add_argument("--minutes-per-game", type=int, default=qualification.DEFAULT_MINUTES_PER_GAME,
                         help="Minutes per game their own team has played that a player must average "
                              "to qualify for any player-level chart. 30 is FBref's per-90-leaderboard "
                              "convention; 45 is starters-only; 20 is more inclusive. Scales with the "
                              "season, so the pool stays the same KIND of player in March and October.")
    parser.add_argument("--minutes", type=int, default=None,
                         help="Escape hatch: a flat league-wide minutes floor, the pre-round-22 "
                              "behaviour. Overrides --minutes-per-game when set.")
    parser.add_argument("--top-n", type=int, default=20,
                         help="How many players appear on the Goals Added leaderboard bar chart. "
                              "Does NOT limit the scatter charts (Goals vs. xG, xG vs. xA, Shot "
                              "Quality, Playmaking Style) -- those always plot every qualifying "
                              "player.")
    parser.add_argument("--out", default="dashboard.html")
    parser.add_argument("--site-url", default=SITE_URL,
                         help="Absolute URL this page is published at, used to build the "
                              "og:url / og:image social-preview tags. Pass an empty string "
                              "to omit them.")
    args = parser.parse_args()

    print("Fetching team/player reference data...")
    teams = get_teams()
    players = get_players()

    print(f"Fetching NWSL {args.season} team xG data...")
    chart_quadrant, chart_diff, team_rows = fetch_team_charts(args.season, teams)

    # Built here because it needs games played, which arrives on the team
    # rows above, and everything player-level below depends on it.
    qual = qualification.from_team_rows(
        team_rows, minutes_per_game=args.minutes_per_game, flat_minutes=args.minutes)
    print(f"Qualification rule: {qual.describe()}")
    if args.minutes is None and not qual.games_by_team:
        print("  !! WARNING: no games-played field on any /teams/xgoals row, so the "
              "games-scaled rule could not be applied and this build fell back to a "
              "flat floor. Check whether ASA renamed count_games.")

    print(f"Fetching NWSL {args.season} team Goals Added data...")
    chart_team_ga = fetch_team_goals_added(args.season, teams)

    print(f"Fetching NWSL {args.season} shot-pattern splits (4 extra calls)...")
    set_piece_rows = fetch_set_piece_split(args.season, teams)
    chart_set_piece = build_set_piece_chart(set_piece_rows)
    if chart_set_piece:
        # Printed as a live sanity check: if dead-ball xG is 0 for every team,
        # the shot_pattern filter silently stopped being honored and the tab is
        # meaningless even though nothing raised.
        total_dead = sum(r["dead_for"] for r in set_piece_rows)
        total_op = sum(r["op_for"] for r in set_piece_rows)
        share = total_dead / (total_dead + total_op) if (total_dead + total_op) else 0
        print(f"  -> league xG is {share:.1%} dead-ball, {1-share:.1%} open play")
        if total_dead <= 0:
            print("     WARNING: zero dead-ball xG league-wide -- check that "
                  "shot_pattern is still a supported filter.")

    print(f"Fetching NWSL {args.season} player xG/xA data (API floor {qual.api_floor} minutes)...")
    player_pool = fetch_player_pool(args.season, qual, teams, players)
    chart_finishing, chart_creation, chart_shot_quality = build_finishing_creation_shotquality(
        player_pool, minimum_minutes=qual)
    print(f"  -> {len(player_pool)} players qualify; Goals vs. xG / xG vs. xA / Shot Quality "
          f"now plot all of them (previously capped at top {args.top_n} by combined xG+xA).")

    print(f"Fetching NWSL {args.season} Goals Added data...")
    chart_goals_added, chart_playmaking, ga_lookup, ga_rows = build_goals_added_chart(
        args.season, qual, args.top_n, teams, players)

    print("Building MVP tracker...")
    chart_mvp = build_mvp_chart(player_pool, ga_rows, team_rows,
                                minimum_minutes=qual, top_n=15)
    if chart_mvp is None:
        print("  -> SKIPPED (mvp_tracker.py not found, or nobody qualified)")
    else:
        # Printed so a live run can be sanity-checked without opening the page:
        # if every score is 0.00, or the qualifying count looks far too low, the
        # underlying fields are wrong even though nothing raised.
        print(f"  -> {chart_mvp['meta']['qualified']} qualifying field players "
              f"(goalkeepers excluded)")
        for label, leader in chart_mvp["meta"]["leaders"].items():
            print(f"     {label:<24} {leader}")

    print(f"Fetching NWSL {args.season} position data (8 calls, above replacement)...")
    rows_by_position = fetch_position_gaps(args.season, qual, teams, players)
    chart_positions = build_position_gap_chart(rows_by_position, team_rows, players)
    if chart_positions is None:
        print("  -> SKIPPED (position_gaps.py not found, or no position had "
              "enough minutes)")
    else:
        cov = chart_positions["meta"]["coverage"]
        worst = chart_positions["meta"]["worst"]
        print(f"  -> {cov['enough']}/{cov['cells']} cells have enough data "
              f"({cov['share']:.0%}); "
              f"{chart_positions['meta']['disagreements']} personnel/results "
              f"mismatches")
        if worst:
            print(f"     widest hole: {worst['team']} at {worst['position']} "
                  f"({worst['value']:+.2f})")

    print(f"Fetching NWSL {args.season} goalkeeper data...")
    chart_goalkeepers = build_goalkeeper_chart(args.season, qual, teams, players)

    print("Fetching full team rosters for Compare Teammates...")
    # Deliberately NOT subject to the qualification rule: this is a squad
    # view, and a fringe player missing from her own team's roster list reads
    # as a bug rather than as a filter. Keeps its own low 90-minute floor.
    chart_team_compare = fetch_team_compare_chart(args.season, 90, teams, players, ga_lookup)

    charts = [chart_quadrant, chart_diff, chart_team_ga]
    if chart_set_piece:
        charts.append(chart_set_piece)
    if chart_positions:
        charts.append(chart_positions)
    if chart_mvp:
        charts.append(chart_mvp)
    if chart_shot_quality:
        charts.append(chart_shot_quality)
    charts.append(chart_playmaking)
    charts += [chart_finishing]
    # Placement vs. Luck sits immediately after Finishing on purpose: it is the
    # follow-up question to the tab before it ("of that margin, how much is
    # placement?"), and the "what is -> what could be" sequencing rule in the
    # Design Guidelines wants the answer next to the claim it qualifies.
    chart_placement = build_placement_chart(player_pool, minimum_minutes=qual)
    if chart_placement:
        charts.append(chart_placement)
        print(f"  Placement vs. Luck: {len(chart_placement['data'])} players plotted")
    charts += [chart_creation, chart_goals_added]
    if chart_goalkeepers:
        charts.append(chart_goalkeepers)
    charts.append(chart_team_compare)

    # Methods goes last on purpose. It is the tab a reader opens to check
    # something they've already seen, not the one they open first, and putting
    # it up front would push the actual findings off the start of the tab bar.
    signal = (chart_finishing.get("meta") or {}).get("signal")
    generated_at = datetime.datetime.now().astimezone().strftime("%d %B %Y, %H:%M %Z")
    downloads = [
        {"label": "Player finishing", "filename": f"nwsl_{args.season}_finishing.csv",
         "csv": rows_to_csv(chart_finishing["table"]["rows"],
                            [(c["key"], c["label"]) for c in chart_finishing["table"]["columns"]])},
    ]
    if chart_set_piece:
        downloads.append({
            "label": "Team open play vs. set pieces",
            "filename": f"nwsl_{args.season}_set_pieces.csv",
            "csv": rows_to_csv(chart_set_piece["table"]["rows"],
                               [(c["key"], c["label"]) for c in chart_set_piece["table"]["columns"]]),
        })
    chart_methods = build_methods_chart(
        season=args.season, generated_at=generated_at, minimum_minutes=qual,
        signal=signal, pens_excluded=(chart_finishing.get("meta") or {}).get("pensExcluded", False),
        downloads=downloads,
    )
    # Glossary first, then the technical sections. Once a chart is shared the
    # median reader is someone who does not already know what g+ is, and the
    # Methods tab is where they land -- opening it with "the population
    # variance of true finishing skill" loses them before the vocabulary that
    # would have helped. build_methods_chart appends extra_sections at the
    # end, which is the wrong place for this one, so it goes in by index.
    chart_methods["sections"].insert(0, GLOSSARY_SECTION)
    charts.append(chart_methods)

    story = build_story_lede(charts)

    html = render_dashboard(
        title=f"NWSL {args.season} Analytics Dashboard",
        subtitle="Team and player xG stats from the American Soccer Analysis API — each tab leads with the finding, not just the metric. Penalties are excluded from every finishing figure, and the Methods tab lists every choice behind these numbers.",
        charts=charts,
        story=story,
        generated_at=generated_at,
        page_url=args.site_url or None,
        # The week's lede, not the static subtitle: this is the text that
        # shows under the link in a social preview, so it should change when
        # the data does.
        social_description=story or None,
    )
    with open(args.out, "w") as f:
        f.write(html)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    sys.exit(main())
