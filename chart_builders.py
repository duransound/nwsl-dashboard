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


import finishing_signal as _fs


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


def qualification_phrase(minimum_minutes):
    """Render a minutes threshold as prose, accepting either shape.

    Round 22 replaced the flat minutes floor with a per-team rule that scales
    with games played (`qualification.Qualification`), but the demo snapshot
    genuinely was built at a flat 500, and older callers still pass a bare
    int. Accepting both keeps `demo_dashboard.py` and `demo_xg_xa.py` working
    untouched.

    Also the guard against a real crash: a Qualification object interpolated
    into a chart blurb would read as "<Qualification ...>", and stored into a
    chart's `meta` it would reach `json.dumps(charts)` in
    `dashboard_template.render_dashboard()` and raise -- it is not
    JSON-serializable. Everything that touches a threshold for display or for
    meta goes through here, so neither can happen.
    """
    phrase = getattr(minimum_minutes, "phrase", None)
    if phrase is not None:
        return phrase
    return f"{minimum_minutes}+ minutes played"


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

    # ---- penalties out (round 22) -------------------------------------
    # A penalty is ~0.75 xG that says nothing about a player's finishing in
    # open play, and it lands on whoever the team designates rather than
    # whoever earned it. Any finishing comparison that leaves penalties in is
    # partly a ranking of who takes them. build_dashboard.py supplies npxg /
    # npgoals / npshots by fetching /players/xgoals a second time with
    # shot_pattern=Penalty and subtracting; the demo snapshot has no such
    # split, so this falls back to all-situations numbers and the footnote
    # says so instead of silently implying penalties were removed.
    pens_excluded = any("npxg" in r for r in pool)
    for r in pool:
        r["fin_xg"] = r.get("npxg", r["xg"]) if pens_excluded else r["xg"]
        r["fin_goals"] = r.get("npgoals", r["goals"]) if pens_excluded else r["goals"]
        r["fin_shots"] = r.get("npshots", r.get("shots", 0)) if pens_excluded else r.get("shots", 0)
        r["xg96"] = per96(r["fin_xg"], r["minutes"])
        r["xa96"] = per96(r["xa"], r["minutes"])
        r["g96"] = per96(r["fin_goals"], r["minutes"])

    # ---- how much of this is chance? (round 22) ------------------------
    # Every point on the finishing chart used to be a bare point estimate,
    # and the tab's headline was whoever's raw G-xG was largest -- i.e. the
    # maximum of a noisy distribution, which is a machine for generating
    # findings that regress next month. Both are fixed here: `signal` carries
    # the pool-level noise model (see finishing_signal.py for the math and
    # why the band errs wide), each player gets an exact z-score and an
    # empirical-Bayes regressed estimate, and the story point is chosen on
    # the REGRESSED value rather than the raw one.
    signal = _fs.pool_summary(
        [{"shots": r["fin_shots"], "xg": r["fin_xg"], "goals": r["fin_goals"],
          "minutes": r["minutes"]} for r in pool]
    )
    tau2 = signal["tau2"]
    for r in pool:
        r["raw_diff"] = r["fin_goals"] - r["fin_xg"]
        r["chance_sd"] = _fs.noise_sd(r["fin_xg"], r["fin_shots"])
        r["z"] = _fs.z_score(r["fin_goals"], r["fin_xg"], r["fin_shots"])
        r["regressed"], r["kept"] = _fs.shrink(
            r["fin_goals"], r["fin_xg"], r["fin_shots"], tau2)

    n = len(pool)
    radius, show_badges = scatter_display_params(n)
    qual_phrase = qualification_phrase(minimum_minutes)
    pool_desc = (f"Top {top_n} players by combined xG+xA, {qual_phrase}"
                 if top_n else f"All {n} qualifying players ({qual_phrase})")
    xg_word = "npxG" if pens_excluded else "xG"

    # Goals is shown per-96 here too (not a raw season count) so it stays on
    # the same footing as the per-96 xG axis -- otherwise the 45-degree
    # reference line (goals == xG) stops meaning anything.
    #
    # The story point is the largest REGRESSED finishing edge, not the largest
    # raw one. When tau2 is zero -- the league's spread in finishing is no
    # wider than chance produces on its own -- every regressed value is
    # exactly zero, so there is no "best finisher" to name and the headline
    # says that outright rather than crowning the luckiest player.
    if tau2 > 0:
        best_finisher = max(pool, key=lambda r: r["regressed"])
        fin_title = (
            f"{best_finisher['name']} is the league's most convincing finisher — "
            f"{best_finisher['regressed']:+.1f} goals of signal left after regressing "
            f"a raw {best_finisher['raw_diff']:+.1f}"
        )
    else:
        best_finisher = max(pool, key=lambda r: abs(r["z"]) if r["z"] is not None else -1)
        # Phrased over the pool rather than "no NWSL player": on the demo
        # snapshot this chart is ~20 hand-verified players, and a claim about
        # the whole league would be an overclaim the data can't carry.
        fin_title = (
            f"None of these {n} players is finishing distinguishably better than their chances — "
            f"the spread is what chance alone produces"
        )

    # Season totals, not per-96 -- a deliberate exception to this project's
    # per-96 convention (rounds 6 and 9), made in round 22 for a specific
    # reason. Goals minus xG is not a rate; it is an accumulation whose
    # RELIABILITY is the point, and the noise in it depends on shots taken and
    # their quality, not on minutes. In count space the chance band is exact
    # for every player at once; on a per-96 axis it could only ever be drawn
    # for one representative player, which is precisely the kind of "roughly
    # right for someone" that this round exists to remove. Rate views of the
    # same players still exist on xG vs. xA, Shot Quality and Compare
    # Teammates, so nothing is lost by making this one tab count-based.
    band = _fs.band_points(0.0, max((r["fin_xg"] for r in pool), default=0.0),
                           signal["median_shot_quality"])
    if tau2 > 0:
        half = signal["half_weight_shots"]
        regression_note = (
            f"Regressed values use an empirical-Bayes weight estimated from this pool: a player keeps "
            f"half their raw {xg_word} gap at about {half:.0f} shots, less below that, more above. "
            f"Nothing here is hand-tuned — the strength comes from how much of the league's spread "
            f"survives after the chance component is subtracted."
        )
    else:
        regression_note = (
            f"The estimated population variance in true finishing skill came out at zero for this pool: "
            f"the spread you see is fully accounted for by the randomness of {signal['total_shots']:,} "
            f"shots. Every regressed value is therefore exactly 0.0, which is the honest estimate, not a "
            f"bug. That is the normal result for a partial season and it is why the band is here."
        )

    chart_finishing = {
        "type": "scatter", "tabLabel": "Goals vs. xG",
        "metricLabel": f"Player Goals vs. {xg_word}, season totals, with the chance band",
        "title": fin_title,
        "blurb": (
            f"{pool_desc}, as season totals rather than per-96 rates — for this one chart, volume is the "
            f"point: how far a player can credibly sit from the line depends on how many shots they have "
            f"taken. The shaded ribbon is where a perfectly average finisher lands 95% of the time by chance "
            f"alone, so inside it, over- or under-performance is not distinguishable from luck. Above the "
            f"line = scoring more than the chances “deserved”; below = fewer. Hover any point for its own "
            f"exact margin; the table below carries the regressed estimate."
        ),
        "xAxisLabel": f"{xg_word} (season total)", "yAxisLabel": "Goals (season total)", "refLine": True,
        "zeroOrigin": True,
        "radius": radius, "showBadges": show_badges,
        "band": {"points": band, "label": "95% chance band"} if band else None,
        # Consumed by build_methods_chart() so the Methods tab quotes the same
        # numbers this chart was actually drawn with, rather than restating the
        # method in prose and hoping the two stay in sync.
        "meta": {"signal": signal, "pensExcluded": pens_excluded, "minimumMinutes": qual_phrase},
        "footnote": (
            f"{'Penalties excluded (npxG): a penalty is ~0.75 xG that measures who takes them, not who finishes well. ' if pens_excluded else 'Penalties are INCLUDED in these numbers — this is the demo snapshot, which has no shot-pattern split. '}"
            f"Season totals here, not per-96 as elsewhere on this dashboard: the band's width comes from shots "
            f"taken, so plotting rates would hide the one thing that determines whether a gap means anything. "
            f"The ribbon is drawn at this pool's median shot quality ({signal['median_shot_quality']:.3f} "
            f"{xg_word}/shot) and is accurate for every player to the extent their own shot quality matches "
            f"that; the exact per-player interval is in the tooltip and the “± chance” column. Chance intervals "
            f"assume every shot is independent with the player's average shot quality, which slightly "
            f"overstates the noise — the band errs wide on purpose. {regression_note}"
        ),
        "table": {
            "caption": (
                f"Every qualifying player, sorted by raw {xg_word} margin. “± chance” is the 95% margin for that "
                f"player's own shot count; “z” is how many chance-standard-deviations they sit from the line "
                f"(|z| under 2 is not distinguishable from average); “regressed” is the estimate after "
                f"accounting for how much of the gap the shot volume can actually support."
            ),
            "columns": [
                {"key": "player", "label": "Player", "align": "left"},
                {"key": "team", "label": "Team", "align": "left"},
                {"key": "shots", "label": "Shots", "num": True},
                {"key": "xg", "label": xg_word, "num": True},
                {"key": "goals", "label": "Goals", "num": True},
                {"key": "diff", "label": f"G−{xg_word}", "num": True},
                {"key": "band", "label": "± chance", "num": True},
                {"key": "z", "label": "z", "num": True},
                {"key": "regressed", "label": "Regressed", "num": True},
            ],
            "rows": [
                {"player": r["name"], "team": r["team"], "shots": r["fin_shots"],
                 "xg": round(r["fin_xg"], 2), "goals": r["fin_goals"],
                 "diff": round(r["raw_diff"], 2),
                 "band": round(_fs.Z95 * r["chance_sd"], 2),
                 "z": (round(r["z"], 2) if r["z"] is not None else None),
                 "regressed": round(r["regressed"], 2)}
                for r in sorted(pool, key=lambda r: r["raw_diff"], reverse=True)
            ],
        },
        "data": [
            {"x": round(r["fin_xg"], 4), "y": r["fin_goals"], "badge": r["team"],
             "tooltip": (
                 f'<div class="name">{r["name"]}</div>'
                 f'<div class="row">{r["team"]} &middot; {r["minutes"]} min &middot; {r["fin_shots"]} shots</div>'
                 f'<div class="row">{xg_word} {r["fin_xg"]:.2f} &middot; Goals {r["fin_goals"]} &middot; '
                 f'margin {r["raw_diff"]:+.2f}</div>'
                 f'<div class="row">chance range &plusmn;{_fs.Z95 * r["chance_sd"]:.2f}'
                 + (f' &middot; z {r["z"]:+.2f}' if r["z"] is not None else "")
                 + f' &middot; regressed {r["regressed"]:+.2f}</div>'
             ),
             "highlight": r["id"] == best_finisher["id"],
             # Literal "±", not the &plusmn; entity: annotations are written to
             # an SVG <text> node via textContent, which does not decode HTML
             # entities and would print the entity source verbatim. Tooltips
             # go through innerHTML and can use entities; these cannot.
             "annotation": (
                 f"{r['regressed']:+.1f} regressed, from {r['raw_diff']:+.1f} raw"
                 if tau2 > 0 else
                 f"{r['raw_diff']:+.1f} raw, but ±{_fs.Z95 * r['chance_sd']:.1f} is chance"
             ) if r["id"] == best_finisher["id"] else None}
            for r in pool
        ],
    }

    most_balanced = max(pool, key=lambda r: min(r["xg96"], r["xa96"]))
    chart_creation = {
        "type": "scatter", "tabLabel": "xG vs. xA",
        "metricLabel": f"Player {xg_word} vs. xAssists, per 96 minutes",
        "title": f"{most_balanced['name']} is the league's most balanced dual threat",
        "blurb": (
            f"Same player pool, shown per 96 minutes — who creates chances for themselves (right) vs. for "
            f"others (up), independent of how many minutes each player has played. This one stays a rate: "
            f"unlike the finishing chart, the question here is threat per unit of playing time, not how much "
            f"evidence there is. {'Penalties are excluded from the ' + xg_word + ' axis — a penalty is not a chance a player created for themselves.' if pens_excluded else ''}"
        ),
        "xAxisLabel": f"{xg_word} per 96 min", "yAxisLabel": "xAssists per 96 min",
        "radius": radius, "showBadges": show_badges,
        "data": [
            {"x": round(r["xg96"], 4), "y": round(r["xa96"], 4), "badge": r["team"],
             "tooltip": f'<div class="name">{r["name"]}</div><div class="row">{r["team"]} &middot; {r["minutes"]} min</div><div class="row">{xg_word}/96 {r["xg96"]:.2f} &middot; xA/96 {r["xa96"]:.2f} &middot; Goals {r["fin_goals"]}</div>',
             "highlight": r["id"] == most_balanced["id"],
             "annotation": f"{r['xg96']:.2f} xG/96, {r['xa96']:.2f} xA/96" if r["id"] == most_balanced["id"] else None}
            for r in pool
        ],
    }

    # Penalties matter even more here than on the finishing chart: at ~0.75 xG
    # apiece they are by far the highest-quality "shot" anyone takes, so a
    # designated penalty taker's average shot quality is inflated by their job
    # title rather than by the chances they create. Hence fin_shots/fin_xg.
    with_shots = [r for r in pool if r["fin_shots"] >= 10]
    chart_shot_quality = None
    if with_shots:
        for r in with_shots:
            r["shots96"] = per96(r["fin_shots"], r["minutes"])
        sq_radius, sq_show_badges = scatter_display_params(len(with_shots))
        best_quality = max(with_shots, key=lambda r: r["fin_xg"] / r["fin_shots"])
        chart_shot_quality = {
            "type": "scatter", "tabLabel": "Shot Quality",
            "metricLabel": f"Shots Taken vs. {xg_word} per Shot, per 96 minutes",
            "title": f"{best_quality['name']} gets more out of every shot than anyone else in the league",
            "blurb": f"Same player pool (min. 10 shots, {len(with_shots)} qualify) — shot volume per 96 minutes (right) vs. average shot quality, {xg_word} per shot (up), so players with different minutes played are compared fairly. Low-and-right = high volume, low quality; up-and-left = fewer, better shots.",
            "xAxisLabel": "Shots per 96 min", "yAxisLabel": f"{xg_word} per shot",
            "radius": sq_radius, "showBadges": sq_show_badges,
            "footnote": (
                "Penalties excluded — at roughly 0.75 xG each they would swamp this axis and rank penalty "
                "takers, not shot selection. Shot quality is a property of the chances a player gets into, "
                "and it stabilises far faster than finishing does, so no chance band is drawn here."
                if pens_excluded else
                "Penalties are INCLUDED here (demo snapshot, no shot-pattern split available) — a designated "
                "penalty taker's average shot quality is inflated by roughly 0.75 xG per penalty."
            ),
            "data": [
                {"x": round(r["shots96"], 4), "y": round(r["fin_xg"] / r["fin_shots"], 4), "badge": r["team"],
                 "tooltip": f'<div class="name">{r["name"]}</div><div class="row">{r["team"]} &middot; {r["fin_shots"]} shots ({r["shots96"]:.1f}/96)</div><div class="row">{xg_word} {r["fin_xg"]:.2f} &middot; {xg_word}/shot {r["fin_xg"]/r["fin_shots"]:.3f}</div>',
                 "highlight": r["id"] == best_quality["id"],
                 "annotation": f"{best_quality['name'].split()[-1]}: {best_quality['fin_xg']/best_quality['fin_shots']:.2f} {xg_word}/shot on {best_quality['shots96']:.1f} shots/96" if r["id"] == best_quality["id"] else None}
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


def build_mvp_chart(player_rows, ga_rows, team_rows, minimum_minutes=500, top_n=15):
    """MVP tracker tab. Returns a "preset-compare" chart dict, or None if the
    mvp_tracker module isn't installed alongside this file or nothing qualifies.

    player_rows: same shape as build_finishing_creation_shotquality's input --
      {"id", "name", "team", "minutes", "xg", "xa", "goals", "shots"}.
    ga_rows:     RAW rows from /players/goals-added, i.e. still carrying the
      nested {"data": [{"action_type", "goals_added_above_avg"}, ...]} list --
      NOT a pre-summed g+ total. mvp_tracker sums them itself, and uses the
      per-action breakdown to detect goalkeepers (only keepers record Claiming)
      and to say which component drove each player's score.
    team_rows:   {"abbr", "name", "xgf", "xga"} plus "points" if available.

    Why a dropdown instead of one ranking: a composite index with author-chosen
    weights is exactly the kind of non-proportional visual the Design
    Guidelines' graphical-integrity rule warns about. Exposing the weights lets
    the reader reassign them, and the headline states rank STABILITY across all
    four weightings rather than asserting one order is the true one. On a
    realistic full-league pool the four weightings agree on a single leader only
    about 8% of the time, so that agreement is a real finding when it happens.

    The import is local and guarded so a missing mvp_tracker.py drops this one
    tab instead of breaking every other chart in this module.
    """
    try:
        import mvp_tracker as mvp
    except ImportError:
        return None

    records = mvp.build_mvp_index(player_rows, ga_rows, team_rows, minimum_minutes)
    if not records:
        return None

    stability = mvp.rank_stability(records)
    by_preset, captions = {}, {}
    for key in mvp.PRESETS:
        rows = mvp.series_for_preset(records, key, top_n=top_n,
                                     stability=stability)
        by_preset[key] = rows
        leader = rows[0]
        captions[key] = (
            f"{mvp.PRESET_LABELS[key]}: {leader['label']} leads on this weighting, "
            f"scoring {leader['value']:.1f}. Showing the top {len(rows)} of "
            f"{len(records)} qualifying field players."
        )

    return {
        "type": "preset-compare", "tabLabel": "MVP Tracker",
        "metricLabel": "Most Valuable Player index",
        "title": mvp.mvp_title(records, stability),
        "blurb": (
            "Four components — total goals added, finishing over expectation "
            "(G−xG), creation (xA), and the player's team points — each turned "
            f"into a z-score across the {len(records)} qualifying field players, "
            "then combined. Switch weightings to see how much the order depends "
            "on that choice; click any bar to make it the emphasized point."
        ),
        "footnote": (
            "Accumulated rather than per-96: availability is part of a season "
            "award, and per-96 rates would reward a player who appeared in a "
            "handful of matches. Goalkeepers are excluded — their goals added is "
            "Claiming-dominated and not comparable to an outfield total. Goals "
            "added already contains passing and receiving value, so it overlaps "
            "xA by design, the same way voters double-count creative play. "
            "Players with no goals-added row are omitted rather than scored as "
            "zero."
        ),
        "valueLabel": "MVP score", "xAxisLabel": "Composite MVP score (weighted z-scores)",
        "pickerLabel": "Weighting",
        "presets": [{"key": k, "label": mvp.PRESET_LABELS[k]} for k in mvp.PRESETS],
        "defaultPreset": mvp.DEFAULT_PRESET,
        "byPreset": by_preset,
        "captions": captions,
        # Diagnostics for the build log, not for rendering. A live run prints
        # these so the tab can be sanity-checked without opening the page --
        # an all-zero score column or an implausibly small qualifying count
        # means a field name is wrong even though nothing raised.
        "meta": {
            "qualified": len(records),
            # Rendered as prose, not stored raw: this dict goes through
            # json.dumps() in render_dashboard(), and a Qualification object
            # is not JSON-serializable -- a guaranteed crash on every live
            # run once the games-scaled rule is passed in here.
            "minimumMinutes": qualification_phrase(minimum_minutes),
            "leaders": {
                mvp.PRESET_LABELS[k]: by_preset[k][0]["label"] for k in mvp.PRESETS
            },
        },
    }


def build_position_gap_chart(rows_by_position, team_rows, player_names=None,
                             min_cell_minutes=None):
    """Position Gaps tab. Returns a "position-grid" chart dict, or None if
    position_gaps.py isn't installed or nothing has enough data.

    rows_by_position: {position: [raw goals-added rows]} -- one entry per ASA
      general_position, each the response of a position-filtered call made with
      above_replacement=true. Rows must carry a team identifier and minutes.
    team_rows: {"abbr", "name", "xgf", "xga"} per team (xgf/xga power the
      personnel-vs-results cross-check).
    player_names: optional {player_id: name} for naming the worst regular.

    Measured against REPLACEMENT level, not league average: a team can sit below
    average at a position and still have no reason to act, whereas below
    replacement means a freely available player would do better. That's the
    question "where could they improve" actually asks.

    Guarded import so a missing position_gaps.py drops this one tab rather than
    breaking every other chart here.
    """
    try:
        import position_gaps as pg
    except ImportError:
        return None

    names = player_names or {}
    floor = min_cell_minutes if min_cell_minutes is not None else pg.MIN_CELL_MINUTES
    cells = pg.build_cells(rows_by_position, team_rows, min_cell_minutes=floor)
    cov = pg.coverage(cells)
    if cov["enough"] == 0:
        return None

    worst = pg.league_worst_cell(cells, team_rows)
    disagreements = pg.find_disagreements(cells, team_rows)
    dis_by_team = {}
    for d in disagreements:
        dis_by_team.setdefault(d["abbr"], []).append(d)

    name_of = {t["abbr"]: t["name"] for t in team_rows}

    # Row order: strongest overall at the top, so the grid has visible structure
    # rather than reading as noise. Teams with no measurable cells sink to the
    # bottom instead of being dropped, so their absence is itself legible.
    def team_mean(abbr):
        vals = [cells[(abbr, p)]["value"] for p in pg.POSITIONS
                if cells.get((abbr, p), {}).get("enough")]
        return sum(vals) / len(vals) if vals else float("-inf")

    ordered = sorted(team_rows, key=lambda t: -team_mean(t["abbr"]))

    out_cells = []
    for t in team_rows:
        abbr = t["abbr"]
        for position in pg.POSITIONS:
            cell = cells[(abbr, position)]
            pos_name = pg.POSITION_NAMES[position]
            entry = {"abbr": abbr, "position": position,
                     "enough": cell["enough"], "value": cell["value"]}

            if not cell["enough"]:
                entry["tooltip"] = (
                    f'<div class="name">{t["name"]} — {pos_name}</div>'
                    f'<div class="row">Not enough minutes to judge '
                    f'({int(cell["minutes"])} min, {cell["players"]} player'
                    f'{"" if cell["players"] == 1 else "s"}; needs {floor})</div>')
                out_cells.append(entry)
                continue

            worst_reg = cell.get("worst")
            worst_txt = ""
            if worst_reg:
                wname = names.get(worst_reg["pid"], worst_reg["pid"])
                worst_txt = (f'<div class="row">Weakest regular: {wname} '
                             f'({worst_reg["per96"]:+.2f})</div>')
            entry["tooltip"] = (
                f'<div class="name">{t["name"]} — {pos_name}</div>'
                f'<div class="row">{cell["value"]:+.2f} g+ per 96 vs replacement</div>'
                f'<div class="row">{int(cell["minutes"])} min across '
                f'{cell["players"]} player{"" if cell["players"] == 1 else "s"}</div>'
                + worst_txt)

            # Per-cell narration, swapped into the panel headline on click --
            # same convention as the MVP tab.
            if cell["value"] < 0:
                entry["headline"] = (
                    f"{t['name']} is below replacement at {pos_name}, "
                    f"{abs(cell['value']):.2f} g+ per 96 short")
            else:
                entry["headline"] = (
                    f"{t['name']}'s {pos_name} is {cell['value']:.2f} g+ per 96 "
                    f"clear of replacement")

            story = []
            if worst_reg and worst_reg["per96"] < cell["value"] - 0.15:
                wname = names.get(worst_reg["pid"], worst_reg["pid"])
                story.append(
                    f"The group average hides a gap: {wname} is at "
                    f"{worst_reg['per96']:+.2f} per 96, well below the "
                    f"{cell['value']:+.2f} the position averages overall.")
            else:
                story.append(
                    f"{int(cell['minutes'])} minutes across {cell['players']} "
                    f"player{'' if cell['players'] == 1 else 's'}, averaging "
                    f"{cell['value']:+.2f} g+ per 96 against replacement level.")
            team_worst = pg.weakest_for_team(cells, abbr)
            if team_worst and team_worst["position"] != position:
                story.append(
                    f"Their weakest position is actually "
                    f"{pg.POSITION_NAMES[team_worst['position']]} "
                    f"({team_worst['value']:+.2f}).")
            entry["story"] = " ".join(story)

            team_dis = dis_by_team.get(abbr)
            if team_dis:
                d = team_dis[0]
                entry["caption"] = (
                    f"{t['name']}'s {d['side']}: personnel rank "
                    f"#{d['personnel_rank']} but results rank "
                    f"#{d['results_rank']} — {d['verdict']}.")
            out_cells.append(entry)

    if worst:
        title = (f"{worst['name']} has the league's widest hole at "
                 f"{pg.POSITION_NAMES[worst['position']]}, "
                 f"{abs(worst['value']):.2f} g+ per 96 below replacement")
        emphasis_key = f"{worst['abbr']}|{worst['position']}"
    else:
        title = "No position has enough minutes to judge yet"
        emphasis_key = None

    default_caption = ""
    if disagreements:
        d = disagreements[0]
        default_caption = (
            f"Biggest mismatch: {d['name']}'s {d['side']} ranks "
            f"#{d['personnel_rank']} on personnel but #{d['results_rank']} on "
            f"results — {d['verdict']}. Click any cell for that team's detail.")

    return {
        "type": "position-grid", "tabLabel": "Position Gaps",
        "metricLabel": "Goals added above replacement, by position",
        "title": title,
        "blurb": (
            "Every team against ASA's eight positions, defensive-most on the "
            "left. Blue is above replacement level, red below; the deeper the "
            "colour, the wider the gap. Replacement level — not league average "
            "— is the bar, because below average can still be good enough, "
            "while below replacement means a freely available player would do "
            "better. Click any cell for that team's detail."),
        "footnote": (
            f"Minutes-weighted g+ per 96 against replacement, so this reflects "
            f"the quality of what each team actually fielded rather than a "
            f"total. A position needs {floor} combined minutes before it is "
            f"judged at all; thinner cells are shown as neutral, not as "
            f"weakness. Because the group average can hide one weak regular "
            f"behind a strong one, each tooltip also names the weakest regular "
            f"({pg.REGULAR_MINUTES}+ minutes) at that position. "
            f"{cov['enough']} of {cov['cells']} cells have enough data."),
        "valueLabel": "g+ per 96 vs replacement",
        "positions": pg.POSITIONS,
        "teams": [{"abbr": t["abbr"], "name": t["name"]} for t in ordered],
        "cells": out_cells,
        "emphasisKey": emphasis_key,
        "defaultCaption": default_caption,
        "meta": {
            "coverage": cov,
            "disagreements": len(disagreements),
            "worst": None if not worst else
                     {"team": worst["name"], "position": worst["position"],
                      "value": round(worst["value"], 3)},
        },
    }


def build_story_lede(charts):
    """Dashboard-level "Big Idea" (Duarte) for the top of the page, stitched
    from two chart insights that are already computed elsewhere rather than
    a fresh pass over raw data: the league-wide team finding (opens on "what
    is", per the Design Guidelines' sequencing rule) and one player-level
    finding (narrows to "what could be"). Every chart's `title` field is
    already a vetted, insight-stating sentence (Design Guidelines §2), so
    reusing it verbatim means this can never assert something a tab doesn't
    actually support, and it can't drift out of sync as data changes week to
    week -- it always reflects whatever each tab is currently highlighting.

    charts: the same list passed to render_dashboard(). Tabs that don't
    exist on a given run (e.g. no goalkeeper clears the minutes floor) are
    skipped gracefully via player_priority's fallback order. Returns None
    if there's no team-level chart to open on (shouldn't happen in practice,
    but keeps this defensive rather than assuming tab order/presence)."""
    by_tab = {c["tabLabel"]: c for c in charts if c}
    team_chart = by_tab.get("League Picture") or (charts[0] if charts else None)
    if not team_chart:
        return None

    player_priority = ["MVP Tracker", "Goals vs. xG", "Playmaking Style", "xG vs. xA", "Shot Quality", "Goalkeepers"]
    player_chart = next((by_tab[t] for t in player_priority if t in by_tab), None)

    sentences = [team_chart["title"].rstrip(".") + "."]
    if player_chart and player_chart is not team_chart:
        sentences.append(player_chart["title"].rstrip(".") + ".")
    return " ".join(sentences)


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


# Which ASA shot patterns roll up into which bucket. ASA's six patterns are
# mutually exclusive and exhaustive -- verified live on 2026-08-13 against
# /nwsl/teams/xgoals?season_name=2026 for team 2lqRn34qr0, where the six
# pattern-filtered calls summed to exactly the unfiltered row (235 shots,
# 25.3197 xG: Regular 170/17.4848, Corner 42/3.4250, Fastbreak 10/1.6420,
# Set piece 7/0.3195, Free kick 3/0.1693, Penalty 3/2.2793). Open play is
# therefore derivable as total minus the dead-ball and penalty buckets,
# which is how build_dashboard.py computes it -- four extra API calls
# instead of six.
DEAD_BALL_PATTERNS = ["Corner", "Free kick", "Set piece"]
PENALTY_PATTERN = "Penalty"


def build_set_piece_chart(team_rows):
    """Open Play vs. Set Pieces tab.

    team_rows: {"abbr", "name", "op_for", "op_against", "dead_for",
    "dead_against"} -- xG for and against, split into open play (Regular +
    Fastbreak) and dead balls (Corner + Free kick + Set piece). Penalties are
    in neither bucket; they are excluded entirely, since a penalty is a
    referee's decision rather than a repeatable feature of how a team plays.

    Why this tab exists: League Picture and Team xG Diff. are all-situations,
    which quietly conflates two different teams. Set-piece xG comes from a
    handful of coached routines and regresses hard; open-play xG is the
    closest thing to a stable read on how a side actually plays. A team can
    sit comfortably in the all-situations table while being a bottom-third
    open-play side, and that gap is a genuine leading indicator -- so the
    story point here is the team whose open-play rank and dead-ball rank
    disagree the most, not whoever is simply best."""
    rows = []
    for r in team_rows:
        rows.append({
            **r,
            "op_diff": r["op_for"] - r["op_against"],
            "dead_diff": r["dead_for"] - r["dead_against"],
        })
    if not rows:
        return None

    by_op = sorted(rows, key=lambda r: r["op_diff"], reverse=True)
    by_dead = sorted(rows, key=lambda r: r["dead_diff"], reverse=True)
    rank_op = {r["abbr"]: i + 1 for i, r in enumerate(by_op)}
    rank_dead = {r["abbr"]: i + 1 for i, r in enumerate(by_dead)}
    for r in rows:
        r["rank_op"] = rank_op[r["abbr"]]
        r["rank_dead"] = rank_dead[r["abbr"]]
        r["rank_gap"] = r["rank_dead"] - r["rank_op"]

    # Largest disagreement in either direction. Ties break toward the team
    # with the larger dead-ball differential, so the highlighted case is the
    # more consequential one rather than an arbitrary alphabetical pick.
    extreme = max(rows, key=lambda r: (abs(r["rank_gap"]), r["dead_diff"]))
    if extreme["rank_gap"] < 0:
        # Better at dead balls than in open play (lower rank number = better).
        title = (
            f"{extreme['name']} is a set-piece team: {_ordinal(extreme['rank_dead'])} in the league "
            f"on dead-ball xG but only {_ordinal(extreme['rank_op'])} in open play"
        )
    elif extreme["rank_gap"] > 0:
        title = (
            f"{extreme['name']} is {_ordinal(extreme['rank_op'])} in open play but "
            f"{_ordinal(extreme['rank_dead'])} on dead balls — the league's biggest set-piece hole"
        )
    else:
        title = f"No NWSL team's set-piece standing differs from its open-play standing"

    return {
        "type": "scatter", "tabLabel": "Open Play vs. Set Pieces",
        "metricLabel": "Team xG differential, split by how the chance began",
        "title": title,
        "blurb": (
            "Open-play xG differential (right) against dead-ball xG differential (up), both for the season. "
            "Open play is Regular plus Fastbreak; dead balls are Corners, Free kicks and other Set pieces. "
            "Penalties are excluded from both. Dashed lines mark the league median, so the top-right "
            "quadrant is strong at both and the bottom-right is a good open-play side that gives its "
            "advantage back at dead balls."
        ),
        "xAxisLabel": "Open-play xG differential", "yAxisLabel": "Dead-ball xG differential",
        "medianLines": True, "radius": 15,
        "footnote": (
            "The two are worth separating because they behave differently: dead-ball output comes from a "
            "small number of rehearsed routines and swings a lot season to season, while open-play xG is "
            "the more stable read on how a side plays. A team whose all-situations position is propped up "
            "by dead balls is a likelier regression candidate than the same record built in open play. "
            "Season totals, not per-96 — a team has no minutes-played denominator."
        ),
        "table": {
            "caption": "Every team, sorted by open-play xG differential.",
            "columns": [
                {"key": "team", "label": "Team", "align": "left"},
                {"key": "op_diff", "label": "Open play ±", "num": True},
                {"key": "op_rank", "label": "Rank", "num": True},
                {"key": "dead_diff", "label": "Dead ball ±", "num": True},
                {"key": "dead_rank", "label": "Rank", "num": True},
                {"key": "dead_share", "label": "Dead-ball share of xG", "num": True},
            ],
            "rows": [
                {"team": r["name"], "op_diff": round(r["op_diff"], 2), "op_rank": r["rank_op"],
                 "dead_diff": round(r["dead_diff"], 2), "dead_rank": r["rank_dead"],
                 "dead_share": (round(100.0 * r["dead_for"] / (r["dead_for"] + r["op_for"]), 1)
                                if (r["dead_for"] + r["op_for"]) else None)}
                for r in by_op
            ],
        },
        "data": [
            {"x": round(r["op_diff"], 3), "y": round(r["dead_diff"], 3), "badge": r["abbr"],
             "tooltip": (
                 f'<div class="name">{r["name"]}</div>'
                 f'<div class="row">Open play {r["op_diff"]:+.1f} ({_ordinal(r["rank_op"])}) &middot; '
                 f'{r["op_for"]:.1f} for, {r["op_against"]:.1f} against</div>'
                 f'<div class="row">Dead ball {r["dead_diff"]:+.1f} ({_ordinal(r["rank_dead"])}) &middot; '
                 f'{r["dead_for"]:.1f} for, {r["dead_against"]:.1f} against</div>'
             ),
             "highlight": r["abbr"] == extreme["abbr"],
             "annotation": (f"{_ordinal(r['rank_op'])} open play, {_ordinal(r['rank_dead'])} dead ball"
                            if r["abbr"] == extreme["abbr"] else None)}
            for r in rows
        ],
    }


def _ordinal(n):
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def build_methods_chart(season, generated_at, minimum_minutes, signal=None,
                        pens_excluded=False, source_note=None, downloads=None,
                        extra_sections=None):
    """Methods & Data tab.

    An analyst's first question about any dashboard is what the numbers
    actually are and where they came from; without an answer, none of the
    charts can be checked and so none of them can be trusted. This tab exists
    to answer it in one place: which xG model, which endpoints, which filters,
    what each derived quantity means, what the known limitations are, when the
    page was built, and a CSV of the underlying rows so a reader can redo the
    work rather than take it on faith.

    `signal` is chart_finishing["meta"]["signal"] -- passing it through means
    the stated regression strength is the one actually used, not a
    description of it. `downloads` is a list of {"label", "filename", "csv"}
    dicts; the CSV text is embedded in the page and offered via a Blob, so
    the export works on a static GitHub Pages host with no backend."""
    sections = [
        {
            "heading": "Where the numbers come from",
            "items": [
                {"term": "Source",
                 "detail": (source_note or
                            "American Soccer Analysis public API (app.americansocceranalysis.com/api/v1/nwsl). "
                            "Team figures from /teams/xgoals and /teams/goals-added; player figures from "
                            "/players/xgoals, /players/goals-added and /goalkeepers/xgoals.")},
                {"term": "xG model",
                 "detail": (
                     "ASA's own expected-goals model. This matters more than it sounds: xG is a model output, "
                     "not an observation, and different providers disagree. The same shot can be 0.09 to one "
                     "model and 0.14 to another, so figures here will not reconcile with Opta-derived or "
                     "FBref numbers and should not be compared across sources without conversion.")},
                {"term": "Season", "detail": f"{season}, all competitions ASA covers, through the build date below."},
                {"term": "Built", "detail": generated_at},
            ],
        },
        {
            "heading": "Filters and thresholds",
            "items": [
                {"term": "Minutes floor",
                 "detail": (f"{qualification_phrase(minimum_minutes)}. Every player-level chart draws from the full league "
                            f"above this line — there is no top-N cut on the scatter charts. Raising the floor "
                            f"trades coverage for stability; lowering it does the reverse.")},
                {"term": "Shot floor",
                 "detail": "Shot Quality additionally requires 10 or more shots, applied to the raw count."},
                {"term": "Penalties",
                 "detail": (
                     "Excluded from every finishing and shot-quality figure (npxG), by fetching the same "
                     "endpoint a second time with shot_pattern=Penalty and subtracting. A penalty is roughly "
                     "0.75 xG and is assigned by team designation, so leaving them in turns a finishing "
                     "ranking into a partial ranking of who takes penalties."
                     if pens_excluded else
                     "NOT excluded in this build — the demo snapshot has no shot-pattern split available, so "
                     "finishing and shot-quality figures here include penalties. The live build excludes them.")},
                {"term": "Per 96 minutes",
                 "detail": ("Player rates are per 96 minutes, roughly one full match including stoppage. Team "
                            "figures are season totals — a team has no minutes-played denominator.")},
            ],
        },
        {
            "heading": "What the derived quantities mean",
            "items": [
                {"term": "Chance band / ± chance",
                 "detail": (
                     "The range within which a perfectly league-average finisher lands 95% of the time, given "
                     "that player's own shots and shot quality. Goals is modelled as the sum of independent "
                     "Bernoulli trials, one per shot; because only the total xG is published rather than each "
                     "shot's value, the variance is computed at the player's mean shot quality, which is the "
                     "maximum for a fixed total. The band is therefore slightly wider than the truth — it "
                     "will call a real finisher unproven before it will invent a finisher who isn't there.")},
                {"term": "z",
                 "detail": ("Goals minus xG divided by that chance standard deviation. |z| below 2 means the "
                            "player's finishing is not distinguishable from average at the 95% level. Most of "
                            "the league is below 2 in most seasons; that is the expected result, not a null "
                            "finding.")},
                {"term": "Regressed",
                 "detail": (
                     "An empirical-Bayes estimate: the raw goals-minus-xG margin multiplied by the share of it "
                     "the shot volume can actually support. The population variance of true finishing skill is "
                     "estimated from this pool by shot-weighted method of moments, so the strength of the "
                     "regression is measured rather than chosen. A player with few shots keeps little of their "
                     "raw number; a high-volume shooter keeps most of it.")},
                {"term": "Open play vs. dead ball",
                 "detail": ("Open play is ASA's Regular and Fastbreak shot patterns; dead ball is Corner, Free "
                            "kick and Set piece. Penalties are in neither. The six patterns are mutually "
                            "exclusive and sum to the unfiltered total, verified against a live team row.")},
                {"term": "Goals Added (g+)",
                 "detail": ("ASA's on-ball value metric, summed across every action type. It already contains "
                            "passing and receiving value, so it overlaps xA by design.")},
            ],
        },
        {
            "heading": "Known limitations — read these before quoting anything",
            "items": [
                {"term": "No context adjustment",
                 "detail": ("Nothing here is adjusted for score state, venue, or opponent strength. A team "
                            "that leads often will look worse than it is on raw rate metrics, because sides "
                            "in front stop attacking. ASA's endpoints expose home_adjusted and even_game_state "
                            "flags that this build does not yet use.")},
                {"term": "Season aggregates only",
                 "detail": ("Every figure is a season-to-date total. There is no rolling form window and no "
                            "match-by-match series, so a team that has changed sharply mid-season reads as "
                            "its average rather than its current form.")},
                {"term": "Positions are not normalised",
                 "detail": ("Player scatters plot every position on shared axes. A fullback and a striker are "
                            "not comparable on xG per 96; use the Position Gaps tab for position-relative "
                            "context, and read cross-position comparisons with care.")},
                {"term": "Single source",
                 "detail": ("All live figures come from one provider's model. Nothing here is triangulated "
                            "against a second xG source.")},
                {"term": "Descriptive, not predictive",
                 "detail": ("These are measurements of what has happened. No figure on this page is a "
                            "forecast, and the regressed finishing estimate is a better guess at present "
                            "skill, not a projection of future goals.")},
            ],
        },
    ]

    if signal:
        half = signal.get("half_weight_shots")
        sections.insert(3, {
            "heading": "Regression strength actually used in this build",
            "items": [
                {"term": "Qualifying shooters", "detail": f"{signal['n_players']} players, {signal['total_shots']:,} shots between them."},
                {"term": "League mean shot quality", "detail": f"{signal['qbar']:.3f} xG per shot."},
                {"term": "Estimated skill variance (τ²)",
                 "detail": (f"{signal['tau2']:.5f} per shot." if signal["tau2"] > 0 else
                            "0 — the spread in finishing across this pool is no wider than independent shots "
                            "would produce on their own, so every regressed estimate is exactly zero. This is "
                            "the usual result for a partial season.")},
                {"term": "Half-weight shot count",
                 "detail": (f"{half:.0f} shots — the volume at which a player keeps half their raw finishing "
                            f"margin after regression." if half else
                            "Not defined, because the estimated skill variance is zero.")},
                {"term": "Estimator bias",
                 "detail": ("The method-of-moments estimate of τ² is biased low when the true signal is weak, "
                            "so this regression is, if anything, slightly too aggressive. It errs toward "
                            "calling a real finisher average rather than the reverse.")},
            ],
        })

    if extra_sections:
        sections.extend(extra_sections)

    return {
        "type": "methods", "tabLabel": "Methods & Data",
        "metricLabel": "Methodology, definitions and limitations",
        "title": "What these numbers are, how they were computed, and where they break",
        "blurb": (
            "Every chart on this page is a model output filtered through choices someone made. This tab lists "
            "those choices so the rest of the dashboard can be checked rather than believed, and offers the "
            "underlying rows as CSV so you can redo any of it."
        ),
        "sections": sections,
        "downloads": downloads or [],
    }


def rows_to_csv(rows, columns):
    """Minimal RFC-4180-ish CSV writer. Rolled by hand rather than pulling in
    `csv` + StringIO because the output is embedded in a JSON blob inside an
    HTML page, and controlling the quoting/newlines directly is less
    surprising than relying on the module's dialect defaults to survive that
    trip. columns: list of (key, header)."""
    def esc(v):
        if v is None:
            return ""
        s = str(v)
        if any(c in s for c in [',', '"', '\n', '\r']):
            return '"' + s.replace('"', '""') + '"'
        return s

    out = [",".join(esc(h) for _, h in columns)]
    for r in rows:
        out.append(",".join(esc(r.get(k)) for k, _ in columns))
    return "\n".join(out)
