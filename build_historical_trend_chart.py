"""
Round 10: a real multi-season historical chart built from nwslR's
2013-2019 season data -- the "multi-season trends per team or player" item
from the starter kit's Natural Next Steps, for the years ASA's API doesn't
cover (the league's first seven seasons, including three now-defunct
clubs: Boston Breakers, FC Kansas City, Western New York Flash).

Two tabs:
  - "League Scoring" -- total goals scored league-wide, one point per
    season 2013-2019, with the peak season called out.
  - "Team Scoring by Season" -- pick a season, see every team's goal
    total that year (the explorer tab, so it comes second).

Usage:
    python3 build_historical_trend_chart.py

Output: historical_trends_demo.html (self-contained, same design system
as the rest of the dashboard).
"""

from dashboard_template import render_dashboard
import nwslr_data as nr


def build_league_scoring_chart(df):
    by_season = df.groupby("season")["Gls"].sum().to_dict()
    seasons = sorted(by_season)
    peak_season = max(seasons, key=lambda s: by_season[s])
    trough_season = min(seasons, key=lambda s: by_season[s])

    data = []
    for s in seasons:
        total = int(by_season[s])
        is_peak = s == peak_season
        data.append({
            "x": s, "y": total, "xLabel": str(s),
            "highlight": is_peak,
            "annotation": f"{total} goals — the league's highest-scoring season" if is_peak else None,
            "tooltip": f'<div class="name">{s}</div><div class="row">{total} league-wide goals</div>',
        })

    return {
        "type": "line", "tabLabel": "League Scoring",
        "metricLabel": "League-wide Goals Scored, 2013-2019",
        "title": f"{peak_season} was the NWSL's highest-scoring season of its first seven years, with {int(by_season[peak_season])} goals",
        "blurb": (
            f"Total goals scored across the whole league, every season since the NWSL's 2013 "
            f"inaugural year through 2019 -- the years American Soccer Analysis's API doesn't reach. "
            f"{trough_season} was the low point, at {int(by_season[trough_season])}."
        ),
        "xAxisLabel": "Season", "yAxisLabel": "League-wide goals",
        "footnote": "Source: nwslR (github.com/adror1/nwslR), season-level field-player box scores. Raw season totals, not adjusted for the number of teams or games played that year.",
        "data": data,
    }


def build_team_season_chart(df):
    by_season = {}
    for season, g in df.groupby("season"):
        team_totals = g.groupby("team_id")["Gls"].sum()
        by_season[str(season)] = [
            {"label": team_id, "value": int(total)}
            for team_id, total in team_totals.items()
        ]
    seasons = sorted(by_season, key=int)

    return {
        "type": "season-compare", "tabLabel": "Team Scoring by Season",
        "metricLabel": "Team Goals by Season",
        "title": "Explore team scoring in any season back to the NWSL's 2013 launch",
        "blurb": "Pick a season to see every team's total goals that year, including three clubs that no longer exist (Boston Breakers, FC Kansas City, Western New York Flash).",
        "valueLabel": "Goals",
        "seasons": seasons,
        "bySeason": by_season,
    }


def main():
    df = nr.load_all_field_player_seasons()

    league_chart = build_league_scoring_chart(df)
    team_chart = build_team_season_chart(df)

    html = render_dashboard(
        title="NWSL Historical Trends (2013-2019)",
        subtitle="League and team scoring for the NWSL's first seven seasons, via the nwslR project's historical data -- years American Soccer Analysis's API doesn't cover.",
        charts=[league_chart, team_chart],
    )
    with open("historical_trends_demo.html", "w") as f:
        f.write(html)
    print("Wrote historical_trends_demo.html")
    print(f"Story point: {league_chart['title']}")


if __name__ == "__main__":
    main()
