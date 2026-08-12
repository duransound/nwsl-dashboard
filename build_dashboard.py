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
import sys

import requests

from chart_builders import (
    build_finishing_creation_shotquality, build_team_charts, build_team_compare_chart,
    build_team_goals_added_chart, per96, scatter_display_params,
)
from dashboard_template import render_dashboard

BASE_URL = "https://app.americansocceranalysis.com/api/v1/nwsl"


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
        }
        for r in rows
    ]
    return build_team_charts(team_rows)


def fetch_team_goals_added(season, teams):
    """One call gets every team at once (unlike the player-level endpoint,
    /teams/goals-added has no team_id filter requirement to return everyone),
    so this is cheap on the live path -- no per-team looping needed."""
    rows = requests.get(f"{BASE_URL}/teams/goals-added", params={"season_name": season}, timeout=30).json()
    totals = {}
    for r in rows:
        team_id = r["team_id"][0] if isinstance(r["team_id"], list) else r["team_id"]
        t = totals.setdefault(team_id, {"ga_for": 0.0, "ga_against": 0.0})
        t["ga_for"] += r["goals_added_for"]
        t["ga_against"] += r["goals_added_against"]
    return build_team_goals_added_chart([
        {
            "abbr": teams.get(team_id, {}).get("team_abbreviation", team_id),
            "name": teams.get(team_id, {}).get("team_name", team_id),
            "ga_for": v["ga_for"], "ga_against": v["ga_against"],
        }
        for team_id, v in totals.items()
    ])


def fetch_player_pool(season, minimum_minutes, teams, players):
    rows = requests.get(f"{BASE_URL}/players/xgoals",
                         params={"season_name": season, "minimum_minutes": minimum_minutes}, timeout=30).json()
    return [
        {
            "id": r["player_id"], "name": players.get(r["player_id"], r["player_id"]),
            "team": teams.get(r["team_id"], {}).get("team_abbreviation", r["team_id"]),
            "minutes": r["minutes"], "xg": r["xgoals"], "xa": r["xassists"],
            "goals": r["goals"], "shots": r.get("shots", 0),
        }
        for r in rows
    ]


def build_goals_added_chart(season, minimum_minutes, leaderboard_n, teams, players):
    """leaderboard_n caps only the Goals Added bar chart -- a ranked
    leaderboard genuinely reads better at ~20 bars than at 150+. Playmaking
    Style is a scatter, not a ranking, so it's built from the FULL fetched
    pool (every player above minimum_minutes), not just the leaderboard_n
    leaders -- previously it was accidentally coupled to the leaderboard
    cutoff, which meant a player with a great passing/dribbling split but a
    lower total g+ would never show up on that chart at all."""
    rows = requests.get(f"{BASE_URL}/players/goals-added",
                         params={"season_name": season, "minimum_minutes": minimum_minutes}, timeout=30).json()
    scored = []
    ga_by_player = {}
    for r in rows:
        by_action = {a["action_type"]: a["goals_added_above_avg"] for a in r["data"]}
        total = sum(by_action.values())
        team_id = r["team_id"][0] if isinstance(r["team_id"], list) else r["team_id"]
        name = players.get(r["player_id"], r["player_id"])
        abbr = teams.get(team_id, {}).get("team_abbreviation", team_id)
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
        "blurb": f"ASA's other headline metric — possession-value contribution (dribbling + fouling + interrupting + passing + receiving + shooting) above average for the position, summed across categories. Top {leaderboard_n} among {minimum_minutes}+ minute players ({len(scored)} qualify).",
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
        "blurb": f"All {len(playmaking_pool)} players with {minimum_minutes}+ minutes played, split into two of the metric's six action categories — value created by beating defenders on the dribble (right) vs. value created by passing (up), shown per 96 minutes so players with different minutes played are compared fairly.",
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
    return chart_goals_added, chart_playmaking, ga_lookup


def build_goalkeeper_chart(season, minimum_minutes, teams, players):
    rows = requests.get(f"{BASE_URL}/goalkeepers/xgoals",
                         params={"season_name": season, "minimum_minutes": minimum_minutes}, timeout=30).json()
    for r in rows:
        r["gk_name"] = players.get(r["player_id"], r["player_id"])
        team_id = r["team_id"][0] if isinstance(r["team_id"], list) else r["team_id"]
        r["abbr"] = teams.get(team_id, {}).get("team_abbreviation", team_id)
        r["gsae"] = r["xgoals_gk_faced"] - r["goals_conceded"]
        r["minutes"] = r.get("minutes_played", 0)
        r["shots96"] = per96(r["shots_faced"], r["minutes"])

    if not rows:
        return None
    leader = max(rows, key=lambda r: r["gsae"])
    gk_radius, gk_show_badges = scatter_display_params(len(rows))

    return {
        "type": "scatter", "tabLabel": "Goalkeepers",
        "metricLabel": "Shots Faced vs. Goals Saved Above Expected, per 96 minutes",
        "title": f"{leader['gk_name']} is saving more than any other keeper in the league",
        "blurb": f"All {len(rows)} goalkeepers with {minimum_minutes}+ minutes. Shots faced per 96 minutes (right, workload) vs. goals prevented relative to the quality of shots faced (up, axis is xG on target minus goals actually conceded — positive means outperforming expectation).",
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
        abbr = teams.get(r["team_id"], {}).get("team_abbreviation", r["team_id"])
        team_names[abbr] = teams.get(r["team_id"], {}).get("team_name", abbr)
        roster_rows.append({
            "id": r["player_id"], "name": players.get(r["player_id"], r["player_id"]), "team": abbr,
            "minutes": r["minutes"], "xg": r["xgoals"], "xa": r["xassists"],
            "goals": r["goals"], "shots": r.get("shots", 0),
        })
    return build_team_compare_chart(roster_rows, team_names, ga_lookup, cap=18)


def main():
    parser = argparse.ArgumentParser(description="Build the full NWSL analytics dashboard from live ASA data.")
    parser.add_argument("--season", default="2026")
    parser.add_argument("--minutes", type=int, default=500,
                         help="Minimum minutes played to qualify for any player-level chart.")
    parser.add_argument("--top-n", type=int, default=20,
                         help="How many players appear on the Goals Added leaderboard bar chart. "
                              "Does NOT limit the scatter charts (Goals vs. xG, xG vs. xA, Shot "
                              "Quality, Playmaking Style) -- those always plot every qualifying "
                              "player above --minutes.")
    parser.add_argument("--out", default="dashboard.html")
    args = parser.parse_args()

    print("Fetching team/player reference data...")
    teams = get_teams()
    players = get_players()

    print(f"Fetching NWSL {args.season} team xG data...")
    chart_quadrant, chart_diff = fetch_team_charts(args.season, teams)

    print(f"Fetching NWSL {args.season} team Goals Added data...")
    chart_team_ga = fetch_team_goals_added(args.season, teams)

    print(f"Fetching NWSL {args.season} player xG/xA data (min {args.minutes} minutes)...")
    player_pool = fetch_player_pool(args.season, args.minutes, teams, players)
    chart_finishing, chart_creation, chart_shot_quality = build_finishing_creation_shotquality(
        player_pool, minimum_minutes=args.minutes)
    print(f"  -> {len(player_pool)} players qualify; Goals vs. xG / xG vs. xA / Shot Quality "
          f"now plot all of them (previously capped at top {args.top_n} by combined xG+xA).")

    print(f"Fetching NWSL {args.season} Goals Added data...")
    chart_goals_added, chart_playmaking, ga_lookup = build_goals_added_chart(
        args.season, args.minutes, args.top_n, teams, players)

    print(f"Fetching NWSL {args.season} goalkeeper data...")
    chart_goalkeepers = build_goalkeeper_chart(args.season, args.minutes, teams, players)

    print("Fetching full team rosters for Compare Teammates...")
    chart_team_compare = fetch_team_compare_chart(args.season, args.minutes, teams, players, ga_lookup)

    charts = [chart_quadrant, chart_diff, chart_team_ga]
    if chart_shot_quality:
        charts.append(chart_shot_quality)
    charts.append(chart_playmaking)
    charts += [chart_finishing, chart_creation, chart_goals_added]
    if chart_goalkeepers:
        charts.append(chart_goalkeepers)
    charts.append(chart_team_compare)

    html = render_dashboard(
        title=f"NWSL {args.season} Analytics Dashboard",
        subtitle="Team and player xG stats from the American Soccer Analysis API — each tab leads with the finding, not just the metric.",
        charts=charts,
    )
    with open(args.out, "w") as f:
        f.write(html)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    sys.exit(main())
