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

Round 10 (2026-08-12): restyled to the project's Design Guidelines doc,
matching the interactive dashboard's approach -- these three charts had
been the only ones left in their original round-1 style. Changes: (1)
titles now state the finding, not the metric name, computed dynamically
from whatever data comes back; (2) exactly one story point per chart is
highlighted in the palette's blue/red, everything else recedes to muted
gray (previously every bar/point was colored, which is the "belt and
suspenders" pattern the guidelines call out); (3) attempts to set
Karla/Fraunces (matching the dashboard's typography -- updated round 18,
was Karla/Space Grotesk through round 17, see the Design Guidelines doc's
round-12 typography unification), falling back to matplotlib's default
sans-serif if those fonts aren't installed locally -- this sandbox can't
download font files (same network allowlist issue as the ASA API itself),
so charts built here will show the fallback; running this on a machine
with the fonts installed (e.g. after `pip install` of a
font-bundling package, or just having them in the OS font directory) will
pick them up automatically, no code change needed.
"""

import argparse
import sys

import matplotlib.pyplot as plt
import pandas as pd
import requests
from matplotlib import font_manager as fm

BASE_URL = "https://app.americansocceranalysis.com/api/v1/nwsl"

# ---- validated chart palette (see Anthropic dataviz skill / references/palette.md) ----
# Round 20: positive/series-1 unified with the brand's Amber (was blue
# #2a78d6), matching dashboard_template.py and build_xg_xa_chart.py --
# renamed COLOR_BLUE -> COLOR_ACCENT since the name would otherwise lie.
COLOR_ACCENT = "#C98A2E"    # positive / series 1 (brand Amber)
COLOR_RED = "#e34948"       # negative / series 8
COLOR_MUTED = "#898781"     # axis / muted labels
COLOR_MUTED_FILL = "#c3c2b7"  # muted / de-emphasized marks (bars, points)
COLOR_GRID = "#e1e0d9"      # hairline gridlines
COLOR_BASELINE = "#c3c2b7"  # zero line / axis line
COLOR_INK = "#0b0b0b"       # primary text
COLOR_SURFACE = "#fcfcfb"   # chart background

# Best-effort Karla/Fraunces, matching the dashboard's typography system.
# Resolved ONCE here (rather than left as a family list handed to every text
# call) so a machine without these fonts installed falls back to DejaVu Sans
# cleanly instead of matplotlib re-attempting and re-warning ("findfont: Font
# family 'Karla' not found") on every single label. This sandbox can't
# download font files (same network allowlist issue as the ASA API itself);
# running this on a machine with the fonts actually installed (e.g. via a
# font-bundling pip package, or just present in the OS font directory) will
# pick them up automatically, no code change needed.
_installed = {f.name for f in fm.fontManager.ttflist}
FONT_BODY = "Karla" if "Karla" in _installed else "DejaVu Sans"
FONT_HEAD = "Fraunces" if "Fraunces" in _installed else "DejaVu Sans"
plt.rcParams["font.family"] = FONT_BODY


def _style_axes(ax):
    ax.set_facecolor(COLOR_SURFACE)
    ax.tick_params(colors=COLOR_MUTED)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_axisbelow(True)


def _title(ax, text):
    ax.set_title(text, color=COLOR_INK, fontsize=13, loc="left", fontweight="bold",
                 fontfamily=FONT_HEAD, wrap=True)


def _credit(fig):
    """Bottom-right source credit, same wording/placement convention as the
    interactive dashboard's page-footer (dashboard_template.py) -- these
    matplotlib PNGs are a separate rendering path with no shared HTML
    template to inherit that footer from, so it's added explicitly here."""
    fig.text(0.99, 0.01, "Data: American Soccer Analysis (americansocceranalysis.com)",
              ha="right", va="bottom", fontsize=7.5, color=COLOR_MUTED, fontfamily=FONT_BODY)


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
    df = team_df.sort_values("xgoal_difference").reset_index(drop=True)
    extreme = df.loc[df["xgoal_difference"].abs().idxmax()]
    if extreme["xgoal_difference"] < 0:
        title = (f"{extreme['team_name']} is being outchanced by "
                  f"{abs(extreme['xgoal_difference']):.0f} expected goals — the widest gap in the league")
    else:
        title = (f"{extreme['team_name']} has the league's biggest xG edge, "
                  f"+{extreme['xgoal_difference']:.0f} ahead of the chances it's allowed")

    def bar_color(row):
        if row["team_abbreviation"] != extreme["team_abbreviation"]:
            return COLOR_MUTED_FILL
        return COLOR_RED if row["xgoal_difference"] < 0 else COLOR_ACCENT

    colors = [bar_color(row) for _, row in df.iterrows()]

    fig, ax = plt.subplots(figsize=(8, 6.4), facecolor=COLOR_SURFACE)
    _style_axes(ax)
    ax.barh(df["team_abbreviation"], df["xgoal_difference"], color=colors, height=0.62)
    ax.axvline(0, color=COLOR_BASELINE, linewidth=1)
    ax.set_xlabel("xG differential (xGF - xGA)", color=COLOR_MUTED, fontfamily=FONT_BODY)
    _title(ax, title)
    ax.grid(axis="x", color=COLOR_GRID, linewidth=0.8)
    for label in ax.get_yticklabels():
        label.set_color(COLOR_INK)
        if label.get_text() == extreme["team_abbreviation"]:
            label.set_fontweight("bold")

    # Label the highlighted bar INSIDE it (white text near the tip), not
    # outside -- the highlighted bar is always the longest one (it's picked
    # by largest absolute value), so there's always room, and it can never
    # collide with the y-axis team-abbreviation labels the way an outside
    # label can when the bar's tip lands right next to the axis edge (a real
    # overlap caught in this round's headless QA pass on the CHI bar, which
    # sits at -26.6, very close to the left edge of the plot).
    span = df["xgoal_difference"].abs().max()
    inward = span * 0.025
    if extreme["xgoal_difference"] < 0:
        x, ha = extreme["xgoal_difference"] + inward, "left"
    else:
        x, ha = extreme["xgoal_difference"] - inward, "right"
    # Round 20: label color now follows the same sign check as bar_color()
    # above -- white reads fine on red, but white on the new Amber accent
    # fails WCAG contrast (roughly 2.9:1, well under the 4.5:1 minimum for
    # normal-size text), so the positive case switches to dark ink instead.
    label_color = "white" if extreme["xgoal_difference"] < 0 else COLOR_INK
    ax.text(x, extreme["team_abbreviation"], f"{extreme['xgoal_difference']:+.1f} xG",
            ha=ha, va="center", fontsize=10, fontweight="bold", color=label_color, fontfamily=FONT_BODY)

    fig.tight_layout()
    _credit(fig)
    fig.savefig(outfile, dpi=200)
    plt.close(fig)


def chart_team_xgf_vs_xga(team_df: pd.DataFrame, season: str, outfile: str):
    df = team_df.copy()
    med_x, med_y = df["xgoals_for"].median(), df["xgoals_against"].median()
    # story point: best combined rank on attack (high xGF) and defense (low xGA),
    # same "best on both sides of the ball" logic as the interactive dashboard.
    rank_xgf = df["xgoals_for"].rank(ascending=False)
    rank_xga = df["xgoals_against"].rank(ascending=True)
    combined = rank_xgf + rank_xga
    best_idx = combined.idxmin()
    best = df.loc[best_idx]
    title = f"{best['team_name']} is the strongest team on both sides of the ball"

    colors = [COLOR_ACCENT if i == best_idx else COLOR_MUTED_FILL for i in df.index]

    fig, ax = plt.subplots(figsize=(7, 7), facecolor=COLOR_SURFACE)
    _style_axes(ax)
    ax.scatter(df["xgoals_for"], df["xgoals_against"], s=70,
               color=colors, edgecolor=COLOR_SURFACE, linewidth=1, zorder=3)

    ax.axvline(med_x, color=COLOR_BASELINE, linewidth=1, linestyle="--")
    ax.axhline(med_y, color=COLOR_BASELINE, linewidth=1, linestyle="--")

    for idx, row in df.iterrows():
        is_best = idx == best_idx
        ax.annotate(row["team_abbreviation"], (row["xgoals_for"], row["xgoals_against"]),
                    textcoords="offset points", xytext=(5, 4),
                    fontsize=8.5 if is_best else 8,
                    fontweight="bold" if is_best else "normal",
                    color=COLOR_INK if is_best else COLOR_MUTED, fontfamily=FONT_BODY)

    ax.invert_yaxis()  # up = fewer xG conceded = stronger defense
    ax.set_xlabel("xG For (attacking output)", color=COLOR_MUTED, fontfamily=FONT_BODY)
    ax.set_ylabel("xG Against (defensive output, inverted)", color=COLOR_MUTED, fontfamily=FONT_BODY)
    _title(ax, title)
    ax.grid(color=COLOR_GRID, linewidth=0.8)
    fig.tight_layout()
    _credit(fig)
    fig.savefig(outfile, dpi=200)
    plt.close(fig)


def chart_player_goals_vs_xg(player_df: pd.DataFrame, season: str, outfile: str, top_n: int = 20):
    df = player_df.sort_values("xgoals", ascending=False).head(top_n).copy()
    df["diff"] = df["goals"] - df["xgoals"]
    extreme_idx = df["diff"].abs().idxmax()
    extreme = df.loc[extreme_idx]
    if extreme["diff"] > 0:
        title = f"{extreme['player_name']} is outscoring their xG by more than anyone else in this group"
    else:
        title = f"{extreme['player_name']} is underperforming their xG by more than anyone else in this group"

    colors = []
    for idx, row in df.iterrows():
        if idx != extreme_idx:
            colors.append(COLOR_MUTED_FILL)
        else:
            colors.append(COLOR_RED if row["diff"] > 0 else COLOR_ACCENT)

    fig, ax = plt.subplots(figsize=(7.5, 7.5), facecolor=COLOR_SURFACE)
    _style_axes(ax)

    lim = max(df["xgoals"].max(), df["goals"].max()) * 1.15
    ax.plot([0, lim], [0, lim], color=COLOR_BASELINE, linewidth=1, linestyle="--", zorder=1)

    ax.scatter(df["xgoals"], df["goals"], s=70, color=colors,
               edgecolor=COLOR_SURFACE, linewidth=1, zorder=3)
    # Only the highlighted point gets a name label. With ~20 players this
    # densely clustered (see this round's headless QA screenshot), labeling
    # every point produces an unreadable pile of overlapping names that no
    # static image can un-overlap the way the interactive dashboard's
    # collision-avoidance JS does -- per the design guidelines' "declutter
    # before you decorate," a label only earns its place if it's legible.
    # The full player list is still in the CSV this script also writes.
    ax.annotate(extreme["player_name"], (extreme["xgoals"], extreme["goals"]),
                textcoords="offset points", xytext=(6, 5),
                fontsize=9.5, fontweight="bold", color=COLOR_INK, fontfamily=FONT_BODY)
    ax.annotate(f"{extreme['diff']:+.1f} vs. xG", (extreme["xgoals"], extreme["goals"]),
                textcoords="offset points", xytext=(6, -14),
                fontsize=9.5, fontweight="bold", color=COLOR_INK, fontfamily=FONT_BODY)

    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("xGoals", color=COLOR_MUTED, fontfamily=FONT_BODY)
    ax.set_ylabel("Goals", color=COLOR_MUTED, fontfamily=FONT_BODY)
    _title(ax, title)
    ax.grid(color=COLOR_GRID, linewidth=0.8)
    fig.tight_layout()
    _credit(fig)
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
