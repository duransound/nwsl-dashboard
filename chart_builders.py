"""
Shared chart-construction logic used by BOTH build_dashboard.py (live data,
via `requests`) and demo_dashboard.py (a hand-verified snapshot).

Why this file exists: before this split, both scripts independently
implemented the finishing/creation/shot-quality/team-compare chart logic.
Every time that logic changed -- most recently, converting xG/xA to
per-96-minute rates -- it had to be edited in two places, which costs
double the tokens/time and is exactly how the two files can quietly drift
out of sync. Now there's one implementation; build_dashboard.py and
demo_dashboard.py each just supply data in a plain shape (see the docstring
on each function) and get the same chart dicts back.

Team-level charts (League Picture, Team xG Diff.), Goals Added, Playmaking
Style, and Goalkeepers are NOT unified here -- they're simple enough, and
differ enough in what data is actually available for the demo snapshot
(e.g. only 2 of 6 Goals Added action categories were individually verified
for the demo), that sharing code for them isn't worth the indirection. See
the project tracking doc if that changes.

Round 13 (2026-08-12): build_finishing_creation_shotquality() no longer
slices to a top-N leaderboard -- it plots every row it's handed. On the
live path that turns "top 20 players by combined xG+xA" into "every
player above the minutes floor, full league" for free, since
build_dashboard.py's fetch_player_pool() was already pulling the whole
league and only got artificially cut down afterward. scatter_display_params()
adapts bubble size/badge visibility so a full-league pool (100-250+
points) doesn't turn into an unreadable pile of overlapping team-abbr
labels -- past 40 points, only the highlighted point keeps its always-on
badge and everyone else is identified via hover tooltip.
"""


def per96(value, minutes):
    return (value / minutes * 96) if minutes else 0.0


def scatter_display_params(n):
    """Adaptive bubble radius + whether to always show the team-badge label
    inside each bubble, for scatter charts whose player count varies with
    where the data came from -- the full league on the live path (can be
    100-250+ players above a minutes floor) vs. a smaller hand-picked set on
    the demo snapshot. At high point counts, an always-on 3-letter badge on
    every bubble overlaps into noise long before the collision-avoidance
    logic can space them out cleanly; past that point, badges are shown only
    for the highlighted point and everyone else is identified via the
    existing hover tooltip instead (same "table/tooltip is the detail view"
    convention already used elsewhere in this project)."""
    if n > 80:
        return 6, False
    if n > 40:
        return 9, False
    return 15, True


def build_team_charts(team_rows):
    """team_rows: list of {"abbr": str, "name": str, "xgf": float, "xga": float}
    for every team. Returns (chart_quadrant, chart_diff)."""
    rows = [{**r, "diff": r["xgf"] - r["xga"]} for r in team_rows]

    by_xgf = sorted(rows, key=lambda r: r["xgf"], reverse=True)
    by_xga = sorted(rows, key=lambda r: r["xga"])
    rank_xgf = {r["abbr"]: i for i, r in enumerate(by_xgf)}
    rank_xga = {r["abbr"]: i for i, r in enumerate(by_xga)}
    best_both = min(rows, key=lambda r: rank_xgf[r["abbr"]] + rank_xga[r["abbr"]])

    chart_quadrant = {
        "type": "scatter", "tabLabel": "League Picture",
        "metricLabel": "Team xGF vs. xGA",
        "title": f"{best_both['name']} is the strongest team on both sides of the ball",
        "blurb": "xG For (right) vs. xG Against (up, axis inverted so up-right is always the strong quadrant). Dashed lines mark the league median. Team totals for the season, not a per-96 rate.",
        "xAxisLabel": "xG For (attacking output)", "yAxisLabel": "xG Against (defensive output)",
        "invertY": True, "medianLines": True, "radius": 15,
        "data": [
            {"x": r["xgf"], "y": r["xga"], "badge": r["abbr"],
             "tooltip": f'<div class="name">{r["name"]}</div><div class="row">xGF {r["xgf"]:.1f} &middot; xGA {r["xga"]:.1f}</div>',
             "highlight": r["abbr"] == best_both["abbr"],
             "annotation": f"{r['abbr']}: rank #{rank_xgf[r['abbr']]+1} attack, #{rank_xga[r['abbr']]+1} defense" if r["abbr"] == best_both["abbr"] else None}
            for r in rows
        ],
    }

    extreme = max(rows, key=lambda r: abs(r["diff"]))
    if extreme["diff"] < 0:
        title = f"{extreme['name']} is being outchanced by {abs(extreme['diff']):.0f} expected goals — the widest gap in the league"
    else:
        title = f"{extreme['name']} has the league's biggest xG edge, +{extreme['diff']:.0f} ahead of the chances they've allowed"

    chart_diff = {
        "type": "diverging-bar", "tabLabel": "Team xG Diff.",
        "metricLabel": "Team xG Differential (xGF - xGA)",
        "title": title,
        "blurb": "xG For minus xG Against, all teams, season through today.",
        "valueLabel": "xG differential", "xAxisLabel": "xG differential (xGF - xGA)",
        "data": [{"label": r["abbr"], "value": r["diff"], "highlight": r["abbr"] == extreme["abbr"]} for r in rows],
    }
    return chart_quadrant, chart_diff


def build_finishing_creation_shotquality(player_rows, minimum_minutes=500, top_n=None):
    """player_rows: list of {"id": str, "name": str, "team": str (abbr),
    "minutes": int, "xg": float, "xa": float, "goals": int, "shots": int}.
    top_n is accepted for backward compatibility with older callers, and is
    None (full pool, the current default) unless a caller explicitly passes
    a number. Uses every row passed in -- on the live path that's already
    the full league above minimum_minutes (build_dashboard.py's
    fetch_player_pool has no team_id filter), so these charts plot the whole
    qualifying pool, not an extra top-N cut on top of it, UNLESS a caller
    explicitly opts back into the old top-N-leaderboard behavior. (Earlier
    versions of this function took a top_n and sliced to the top N by
    combined xG+xA before plotting --
    removed because it was silently shrinking an already-fetched full-league
    pool down to 20 points for no real reason. A leaderboard-style top-N cut
    still makes sense for bar charts like Goals Added, just not for a
    scatter that can show everyone.) Converts xG/xA/Goals to per-96-minute
    rates, and returns (chart_finishing, chart_creation, chart_shot_quality).
    chart_shot_quality is None if no row has >=10 shots.
    """
    pool = list(player_rows)
    if top_n:
        pool = sorted(pool, key=lambda r: r["xg"] + r["xa"], reverse=True)[:top_n]
    for r in pool:
        r["xg96"] = per96(r["xg"], r["minutes"])
        r["xa96"] = per96(r["xa"], r["minutes"])
        r["g96"] = per96(r["goals"], r["minutes"])

    n = len(pool)
    radius, show_badges = scatter_display_params(n)
    pool_desc = (f"Top {top_n} players by combined xG+xA, {minimum_minutes}+ minutes played"
                 if top_n else f"All {n} players with {minimum_minutes}+ minutes played this season")

    # Goals is shown per-96 here too (not a raw season count) so it stays on
    # the same footing as the per-96 xG axis -- otherwise the 45-degree
    # reference line (goals == xG) stops meaning anything.
    best_finisher = max(pool, key=lambda r: r["g96"] - r["xg96"])
    chart_finishing = {
        "type": "scatter", "tabLabel": "Goals vs. xG",
        "metricLabel": "Player Goals vs. xGoals, per 96 minutes",
        "title": f"{best_finisher['name']} is outscoring their xG by more than anyone else in the league",
        "blurb": f"{pool_desc}, shown per 96 minutes (roughly a full match) so players with different minutes are compared fairly. Above the dashed line = scoring more than the shots “deserved”; below = underperforming their chances.",
        "xAxisLabel": "xGoals per 96 min", "yAxisLabel": "Goals per 96 min", "refLine": True,
        "radius": radius, "showBadges": show_badges,
        "data": [
            {"x": round(r["xg96"], 4), "y": round(r["g96"], 4), "badge": r["team"],
             "tooltip": f'<div class="name">{r["name"]}</div><div class="row">{r["team"]} &middot; {r["minutes"]} min</div><div class="row">xG/96 {r["xg96"]:.2f} &middot; Goals/96 {r["g96"]:.2f} &middot; Goals {r["goals"]}</div>',
             "highlight": r["id"] == best_finisher["id"],
             "annotation": f"{r['g96']:.2f} goals/96 on {r['xg96']:.2f} xG/96 (+{r['g96']-r['xg96']:.2f})" if r["id"] == best_finisher["id"] else None}
            for r in pool
        ],
    }

    most_balanced = max(pool, key=lambda r: min(r["xg96"], r["xa96"]))
    chart_creation = {
        "type": "scatter", "tabLabel": "xG vs. xA",
        "metricLabel": "Player xGoals vs. xAssists, per 96 minutes",
        "title": f"{most_balanced['name']} is the league's most balanced dual threat",
        "blurb": "Same player pool, shown per 96 minutes — who creates chances for themselves (right) vs. for others (up), independent of how many minutes each player has played.",
        "xAxisLabel": "xGoals per 96 min", "yAxisLabel": "xAssists per 96 min",
        "radius": radius, "showBadges": show_badges,
        "data": [
            {"x": round(r["xg96"], 4), "y": round(r["xa96"], 4), "badge": r["team"],
             "tooltip": f'<div class="name">{r["name"]}</div><div class="row">{r["team"]} &middot; {r["minutes"]} min</div><div class="row">xG/96 {r["xg96"]:.2f} &middot; xA/96 {r["xa96"]:.2f} &middot; Goals {r["goals"]}</div>',
             "highlight": r["id"] == most_balanced["id"],
             "annotation": f"{r['xg96']:.2f} xG/96, {r['xa96']:.2f} xA/96" if r["id"] == most_balanced["id"] else None}
            for r in pool
        ],
    }

    with_shots = [r for r in pool if r.get("shots", 0) >= 10]
    chart_shot_quality = None
    if with_shots:
        for r in with_shots:
            r["shots96"] = per96(r["shots"], r["minutes"])
        sq_radius, sq_show_badges = scatter_display_params(len(with_shots))
        best_quality = max(with_shots, key=lambda r: r["xg"] / r["shots"])
        chart_shot_quality = {
            "type": "scatter", "tabLabel": "Shot Quality",
            "metricLabel": "Shots Taken vs. xG per Shot, per 96 minutes",
            "title": f"{best_quality['name']} gets more out of every shot than anyone else in the league",
            "blurb": f"Same player pool (min. 10 shots, {len(with_shots)} qualify) — shot volume per 96 minutes (right) vs. average shot quality, xG per shot (up), so players with different minutes played are compared fairly. Low-and-right = high volume, low quality; up-and-left = fewer, better shots.",
            "xAxisLabel": "Shots per 96 min", "yAxisLabel": "xG per shot",
            "radius": sq_radius, "showBadges": sq_show_badges,
            "data": [
                {"x": round(r["shots96"], 4), "y": round(r["xg"] / r["shots"], 4), "badge": r["team"],
                 "tooltip": f'<div class="name">{r["name"]}</div><div class="row">{r["team"]} &middot; {r["shots"]} shots ({r["shots96"]:.1f}/96)</div><div class="row">xG {r["xg"]:.2f} &middot; xG/shot {r["xg"]/r["shots"]:.3f}</div>',
                 "highlight": r["id"] == best_quality["id"],
                 "annotation": f"{best_quality['name'].split()[-1]}: {best_quality['xg']/best_quality['shots']:.2f} xG/shot on {best_quality['shots96']:.1f} shots/96" if r["id"] == best_quality["id"] else None}
                for r in with_shots
            ],
        }

    return chart_finishing, chart_creation, chart_shot_quality


def build_team_goals_added_chart(team_rows):
    """team_rows: list of {"abbr": str, "name": str, "ga_for": float, "ga_against": float}.
    ga_for/ga_against are each team's Goals Added (g+) summed across every
    action type (dribbling, fouling, interrupting, passing, receiving,
    shooting, and claiming for keepers): ga_for is value the team's own
    players created, ga_against is value opposing players created against
    them. Net (for - against) is a single on-ball-quality number, separate
    from the shot-based xG picture in the League Picture / Team xG Diff.
    charts. Returns a diverging-bar chart, same shape as build_team_charts()'s
    chart_diff."""
    rows = [{**r, "net": r["ga_for"] - r["ga_against"]} for r in team_rows]
    extreme = max(rows, key=lambda r: abs(r["net"]))
    if extreme["net"] < 0:
        title = (f"{extreme['name']}'s on-ball play is the league's single biggest goals-added "
                  f"liability, {abs(extreme['net']):.1f} g+ worse than a league-average team")
    else:
        title = (f"{extreme['name']} generates more on-ball value than any other team, "
                  f"+{extreme['net']:.1f} g+ above a league-average team")

    return {
        "type": "diverging-bar", "tabLabel": "Team Goals Added",
        "metricLabel": "Team Goals Added (g+), net of value conceded",
        "title": title,
        "blurb": "Goals Added (g+) summed across every action type — value the team's own players created, minus value opposing players created against them. A single on-ball-quality number, independent of the shot-based xG charts.",
        "valueLabel": "Net Goals Added", "xAxisLabel": "Net Goals Added (g+)",
        "footnote": "Positive = the team created more on-ball value than it conceded, relative to a league-average team; negative = the reverse. Season totals, not per-96 — like Team xG Diff., a team doesn't have a \"minutes played\" denominator the way a player does.",
        "data": [
            {"label": r["abbr"], "value": round(r["net"], 2), "highlight": r["abbr"] == extreme["abbr"],
             "extra": f"Created {r['ga_for']:.1f} g+ &middot; Conceded {r['ga_against']:.1f} g+"}
            for r in rows
        ],
    }


def build_team_compare_chart(roster_rows, team_names, ga_lookup=None, cap=18):
    """roster_rows: list of {"id": str, "name": str, "team": str (abbr),
    "minutes": int, "xg": float, "xa": float, "goals": int, "shots": int} --
    a BROADER pool than build_finishing_creation_shotquality's top_n, ideally
    every player on every team. team_names: {abbr: full name}. ga_lookup:
    optional dict of id-or-name -> Goals Added total (defaults to 0 for any
    player not present). cap: max players kept per team (by minutes)."""
    ga_lookup = ga_lookup or {}
    rosters = {}
    for r in roster_rows:
        ga = ga_lookup.get(r["id"], ga_lookup.get(r["name"], 0.0))
        rosters.setdefault(r["team"], []).append({
            "name": r["name"], "minutes": r["minutes"],
            "xg96": round(per96(r["xg"], r["minutes"]), 4),
            "xa96": round(per96(r["xa"], r["minutes"]), 4),
            "goals96": round(per96(r["goals"], r["minutes"]), 4),
            "shots96": round(per96(r.get("shots", 0), r["minutes"]), 4),
            "ga": round(ga, 3),
        })
    for abbr in rosters:
        rosters[abbr] = sorted(rosters[abbr], key=lambda p: p["minutes"], reverse=True)[:cap]

    return {
        "type": "team-compare", "tabLabel": "Compare Teammates",
        "metricLabel": "Team Roster Comparison",
        "title": "Compare any two teammates head-to-head",
        "blurb": "Pick a team to see how its players stack up on a given metric.",
        "footnote": "xGoals, xAssists, Goals, and Shots shown per 96 minutes.",
        "teamNames": team_names,
        "rosters": rosters,
        "stats": [
            {"key": "ga", "label": "Goals Added (g+)"},
            {"key": "xg96", "label": "xGoals per 96"},
            {"key": "xa96", "label": "xAssists per 96"},
            {"key": "goals96", "label": "Goals per 96"},
            {"key": "shots96", "label": "Shots per 96"},
            {"key": "minutes", "label": "Minutes"},
        ],
    }
