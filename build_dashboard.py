"""
Builds the full NWSL analytics dashboard (dashboard.html) from LIVE data via
the ASA API: team xGF-vs-xGA, team xG differential, player goals-vs-xG,
player xG-vs-xA, shot quality, playmaking style, a Goals Added leaderboard,
goalkeepers, and a team-roster comparison tab -- all in one tabbed,
self-contained HTML file.

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

from chart_builders import build_finishing_creation_shotquality, build_team_charts, build_team_compare_chart
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


def build_goals_added_chart(season, minimum_minutes, top_n, teams, players):
    rows = requests.get(f"{BASE_URL}/players/goals-added",
                         params={"season_name": season, "minimum_minutes": minimum_minutes}, timeout=30).json()
    scored = []
    ga_by_player = {}
    for r in rows:
        by_action = {a["action_type"]: a["goals_added_above_avg"] for a in r["data"]}
        total = sum(by_action.values())
        team_id = r["team_id"][0] if isinstance(r["team_id"], list) else r["team_id"]
        name = players.get(r["player_id"], r["player_id"])
        scored.append({
            "player_id": r["player_id"],
            "name": name,
            "label": f'{name} ({teams.get(team_id, {}).get("team_abbreviation", team_id)})',
            "value": total,
        })
        ga_by_player[r["player_id"]] = {"total": total, "by_action": by_action}
    scored.sort(key=lambda d: d["value"], reverse=True)
    top_rows = scored[:top_n]
    leader = top_rows[0]

    chart_goals_added = {
        "type": "diverging-bar", "tabLabel": "Goals Added",
        "metricLabel": "Goals Added (g+), all action types combined",
        "title": f"{leader['name']} leads the league in total on-ball contribution",
        "blurb": "ASA's other headline metric — possession-value contribution (dribbling + fouling + interrupting + passing + receiving + shooting) above average for the position, summed across categories.",
        "valueLabel": "Goals Added", "xAxisLabel": "Goals Added (g+)",
        "footnote": "“Above average” is relative to other players in the same general position.",
        "data": [{"label": d["label"], "value": d["value"], "highlight": d is leader} for d in top_rows],
    }

    # --- Chart: playmaking style -- Dribbling g+ vs Passing g+ for the same
    # top_n leaders. Story point = the biggest passing-over-dribbling skew. ---
    playmaking_pool = []
    for d in top_rows:
        ga = ga_by_player.get(d["player_id"], {}).get("by_action", {})
        drib = ga.get("Dribbling", 0.0)
        passing = ga.get("Passing", 0.0)
        playmaking_pool.append({"player_id": d["player_id"], "name": d["name"], "drib": drib, "passing": passing,
                                 "team": d["label"].split("(")[-1].rstrip(")")})
    most_pass_skewed = max(playmaking_pool, key=lambda d: d["passing"] - d["drib"])

    chart_playmaking = {
        "type": "scatter", "tabLabel": "Playmaking Style",
        "metricLabel": "Goals Added: Dribbling vs. Passing",
        "title": f"{most_pass_skewed['name']} creates almost entirely through passing, not dribbling"
                 if most_pass_skewed["passing"] >= most_pass_skewed["drib"]
                 else f"{most_pass_skewed['name']} creates far more through dribbling than passing",
        "blurb": f"The top {top_n} Goals Added leaders, split into two of the metric's six action categories — value created by beating defenders on the dribble (right) vs. value created by passing (up).",
        "xAxisLabel": "Dribbling g+", "yAxisLabel": "Passing g+", "radius": 15,
        "data": [
            {"x": d["drib"], "y": d["passing"], "badge": d["team"],
             "tooltip": f'<div class="name">{d["name"]}</div><div class="row">{d["team"]}</div><div class="row">Dribbling {d["drib"]:+.2f} g+ &middot; Passing {d["passing"]:+.2f} g+</div>',
             "highlight": d["player_id"] == most_pass_skewed["player_id"],
             "annotation": f"{d['name'].split()[-1]}: {d['passing']:+.2f} g+ passing vs. {d['drib']:+.2f} g+ dribbling" if d["player_id"] == most_pass_skewed["player_id"] else None}
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

    if not rows:
        return None
    leader = max(rows, key=lambda r: r["gsae"])

    return {
        "type": "scatter", "tabLabel": "Goalkeepers",
        "metricLabel": "Shots Faced vs. Goals Saved Above Expected",
        "title": f"{leader['gk_name']} is saving more than any other keeper in the league",
        "blurb": f"Goalkeepers with {minimum_minutes}+ minutes. Shots faced (right, workload) vs. goals prevented relative to the quality of shots faced (up, axis is xG on target minus goals actually conceded — positive means outperforming expectation).",
        "xAxisLabel": "Shots faced", "yAxisLabel": "Goals saved above expected", "radius": 15,
        "data": [
            {"x": r["shots_faced"], "y": round(r["gsae"], 3), "badge": r["abbr"],
             "tooltip": f'<div class="name">{r["gk_name"]}</div><div class="row">{r["abbr"]} &middot; {r["shots_faced"]} shots faced</div><div class="row">Goals saved above expected: {r["gsae"]:+.2f}</div>',
             "highlight": r["player_id"] == leader["player_id"],
             "annotation": f"{leader['gk_name']}: {leader['gsae']:+.1f} on {leader['shots_faced']} shots faced" if r["player_id"] == leader["player_id"] else None}
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
    parser.add_argument("--minutes", type=int, default=500)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--out", default="dashboard.html")
    args = parser.parse_args()

    print("Fetching team/player reference data...")
    teams = get_teams()
    players = get_players()

    print(f"Fetching NWSL {args.season} team xG data...")
    chart_quadrant, chart_diff = fetch_team_charts(args.season, teams)

    print(f"Fetching NWSL {args.season} player xG/xA data (min {args.minutes} minutes)...")
    player_pool = fetch_player_pool(args.season, args.minutes, teams, players)
    chart_finishing, chart_creation, chart_shot_quality = build_finishing_creation_shotquality(
        player_pool, top_n=args.top_n, minimum_minutes=args.minutes)

    print(f"Fetching NWSL {args.season} Goals Added data...")
    chart_goals_added, chart_playmaking, ga_lookup = build_goals_added_chart(
        args.season, args.minutes, 15, teams, players)

    print(f"Fetching NWSL {args.season} goalkeeper data...")
    chart_goalkeepers = build_goalkeeper_chart(args.season, args.minutes, teams, players)

    print("Fetching full team rosters for Compare Teammates...")
    chart_team_compare = fetch_team_compare_chart(args.season, args.minutes, teams, players, ga_lookup)

    charts = [chart_quadrant, chart_diff]
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
