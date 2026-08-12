"""
NWSL xG Starter Kit
====================
Pulls team- and player-level Expected Goals (xG) data straight from the
American Soccer Analysis (ASA) public API and produces three "starter" charts:

  1. Team xG differential          (bar chart, diverging)
  2. Team xG For vs xG Against      (scatter, attacking vs. defensive strength)
  3. Player Goals vs xG             (scatter, over/underperformance)

WHY NO WRAPPER LIBRARY?
------------------------
ASA also publishes an official wrapper package, `itscalledsoccer`
(pip install itscalledsoccer / install.packages("itscalledsoccer") in R).
It's worth learning -- it adds fuzzy name matching and some convenience
methods -- see https://github.com/American-Soccer-Analysis/itscalledsoccer-r
and the Python sibling for details. This script instead calls the REST API
directly with `requests` so you can see exactly what's happening under the
hood: every function here is just a GET request to a documented endpoint.
API docs: https://app.americansocceranalysis.com/api/v1/__docs__/

REQUIREMENTS
------------
pip install requests pandas matplotlib

USAGE
-----
python nwsl_xg_charts.py --season 2025 --minutes 900
"""

import argparse
import sys

import matplotlib.pyplot as plt
import pandas as pd
import requests

BASE_URL = "https://app.americansocceranalysis.com/api/v1/nwsl"

# ---- validated chart palette (see Anthropic dataviz skill / references/palette.md) ----
COLOR_BLUE = "#2a78d6"      # positive / series 1
COLOR_RED = "#e34948"       # negative / series 8
COLOR_MUTED = "#898781"     # axis / muted labels
COLOR_GRID = "#e1e0d9"      # hairline gridlines
COLOR_BASELINE = "#c3c2b7"  # zero line / axis line
COLOR_INK = "#0b0b0b"       # primary text
COLOR_SURFACE = "#fcfcfb"   # chart background


def fetch(endpoint: str, **params) -> pd.DataFrame:
    """GET a JSON array from the ASA API and return it as a DataFrame."""
    resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30)
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


def get_team_xgoals(season: str) -> pd.DataFrame:
    teams = fetch("teams")[["team_id", "team_name", "team_abbreviation"]]
    xg = fetch("teams/xgoals", season_name=season)
    return xg.merge(teams, on="team_id")


def get_player_xgoals(season: str, minimum_minutes: int) -> pd.DataFrame:
    xg = fetch("players/xgoals", season_name=season, minimum_minutes=minimum_minutes)
    # /players is a big roster table -- filter to just the players we kept
    players = fetch("players")[["player_id", "player_name"]]
    return xg.merge(players, on="player_id", how="left")


def chart_team_xg_differential(team_df: pd.DataFrame, season: str, outfile: str):
    df = team_df.sort_values("xgoal_difference")
    colors = [COLOR_RED if v < 0 else COLOR_BLUE for v in df["xgoal_difference"]]

    fig, ax = plt.subplots(figsize=(8, 6), facecolor=COLOR_SURFACE)
    ax.set_facecolor(COLOR_SURFACE)
    ax.barh(df["team_abbreviation"], df["xgoal_difference"], color=colors, height=0.62)
    ax.axvline(0, color=COLOR_BASELINE, linewidth=1)
    ax.set_xlabel("xG differential (xGF - xGA)", color=COLOR_MUTED)
    ax.set_title(f"NWSL {season}: Team xG Differential", color=COLOR_INK, fontsize=13, loc="left")
    ax.tick_params(colors=COLOR_MUTED)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(axis="x", color=COLOR_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for label in ax.get_yticklabels():
        label.set_color(COLOR_INK)
    fig.tight_layout()
    fig.savefig(outfile, dpi=200)
    plt.close(fig)


def chart_team_xgf_vs_xga(team_df: pd.DataFrame, season: str, outfile: str):
    fig, ax = plt.subplots(figsize=(7, 7), facecolor=COLOR_SURFACE)
    ax.set_facecolor(COLOR_SURFACE)
    ax.scatter(team_df["xgoals_for"], team_df["xgoals_against"], s=70,
               color=COLOR_BLUE, edgecolor=COLOR_SURFACE, linewidth=1, zorder=3)

    med_x, med_y = team_df["xgoals_for"].median(), team_df["xgoals_against"].median()
    ax.axvline(med_x, color=COLOR_BASELINE, linewidth=1, linestyle="--")
    ax.axhline(med_y, color=COLOR_BASELINE, linewidth=1, linestyle="--")

    for _, row in team_df.iterrows():
        ax.annotate(row["team_abbreviation"], (row["xgoals_for"], row["xgoals_against"]),
                    textcoords="offset points", xytext=(5, 4), fontsize=8, color=COLOR_INK)

    ax.invert_yaxis()  # up = fewer xG conceded = stronger defense
    ax.set_xlabel("xG For (attacking output)", color=COLOR_MUTED)
    ax.set_ylabel("xG Against (defensive output, inverted)", color=COLOR_MUTED)
    ax.set_title(f"NWSL {season}: Attacking vs. Defensive xG Strength", color=COLOR_INK, fontsize=13, loc="left")
    ax.tick_params(colors=COLOR_MUTED)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(color=COLOR_GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(outfile, dpi=200)
    plt.close(fig)


def chart_player_goals_vs_xg(player_df: pd.DataFrame, season: str, outfile: str, top_n: int = 20):
    df = player_df.sort_values("xgoals", ascending=False).head(top_n).copy()
    df["diff"] = df["goals"] - df["xgoals"]
    colors = [COLOR_RED if d > 0 else COLOR_BLUE for d in df["diff"]]

    fig, ax = plt.subplots(figsize=(7.5, 7.5), facecolor=COLOR_SURFACE)
    ax.set_facecolor(COLOR_SURFACE)

    lim = max(df["xgoals"].max(), df["goals"].max()) * 1.15
    ax.plot([0, lim], [0, lim], color=COLOR_BASELINE, linewidth=1, linestyle="--", zorder=1)

    ax.scatter(df["xgoals"], df["goals"], s=70, color=colors,
               edgecolor=COLOR_SURFACE, linewidth=1, zorder=3)
    for _, row in df.iterrows():
        ax.annotate(row["player_name"], (row["xgoals"], row["goals"]),
                    textcoords="offset points", xytext=(5, 4), fontsize=8, color=COLOR_INK)

    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("xGoals", color=COLOR_MUTED)
    ax.set_ylabel("Goals", color=COLOR_MUTED)
    ax.set_title(f"NWSL {season}: Goals vs. xGoals (top {top_n} by xG)", color=COLOR_INK, fontsize=13, loc="left")
    ax.tick_params(colors=COLOR_MUTED)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(color=COLOR_GRID, linewidth=0.8)
    ax.set_axisbelow(True)

    handles = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=COLOR_RED, markersize=8, label="Overperforming xG"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=COLOR_BLUE, markersize=8, label="Underperforming xG"),
    ]
    ax.legend(handles=handles, frameon=False, labelcolor=COLOR_INK, loc="upper left")
    fig.tight_layout()
    fig.savefig(outfile, dpi=200)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Build basic NWSL xG charts from the ASA API.")
    parser.add_argument("--season", default="2025", help="Season year, e.g. 2025")
    parser.add_argument("--minutes", type=int, default=900, help="Minimum minutes played filter for players")
    parser.add_argument("--top-n", type=int, default=20, help="How many top-xG players to plot")
    args = parser.parse_args()

    print(f"Fetching NWSL {args.season} team xG data...")
    team_df = get_team_xgoals(args.season)
    print(f"Fetching NWSL {args.season} player xG data (min {args.minutes} minutes)...")
    player_df = get_player_xgoals(args.season, args.minutes)

    team_df.to_csv(f"team_xgoals_{args.season}.csv", index=False)
    player_df.to_csv(f"player_xgoals_{args.season}.csv", index=False)

    chart_team_xg_differential(team_df, args.season, f"team_xg_differential_{args.season}.png")
    chart_team_xgf_vs_xga(team_df, args.season, f"team_xgf_vs_xga_{args.season}.png")
    chart_player_goals_vs_xg(player_df, args.season, f"player_goals_vs_xg_{args.season}.png", top_n=args.top_n)

    print("Done. Wrote 2 CSVs and 3 PNG charts to the current directory.")


if __name__ == "__main__":
    sys.exit(main())
