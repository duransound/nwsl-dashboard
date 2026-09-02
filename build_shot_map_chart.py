"""
Round 10: a real shot map built from StatsBomb's free NWSL event data --
the "shot maps (needs a separate shot-location endpoint)" item that's been
sitting in the starter kit's Natural Next Steps since round 1. ASA's API
has no shot-location field at all; StatsBomb's open data does.

Defaults to the 2023 NWSL Championship Final (Seattle Reign 1-2 NJ/NY
Gotham FC) since it's a real, well-known result with a genuinely
interesting shot pattern -- but works for any match_id in the 2018 or
2023 season (StatsBomb hasn't published any other NWSL seasons; see
statsbomb_data.py). Run with --match-id / --season to pick a different
game, or --list-matches to see what's available in a season first.

Usage:
    python3 build_shot_map_chart.py
    python3 build_shot_map_chart.py --list-matches --season 2023
    python3 build_shot_map_chart.py --match-id 3881607 --season 2023

Output: shot_map_demo.html (self-contained, same design system as the
rest of the dashboard -- open directly in a browser).
"""

import argparse

from dashboard_template import render_dashboard
import statsbomb_data as sb

DEFAULT_MATCH_ID = 3915998  # 2023 NWSL Championship Final
DEFAULT_SEASON = "2023"


def outcome_label(outcome):
    return {
        "Goal": "Goal", "Saved": "Saved", "Off T": "Off target",
        "Blocked": "Blocked", "Wayward": "Wayward", "Post": "Hit the post",
        "Saved to Post": "Saved (post)", "Saved Off Target": "Saved",
    }.get(outcome, outcome)


def build_shot_map_chart(match_id, match_label=""):
    shots = sb.get_shots(match_id)
    if not shots:
        raise ValueError(f"No shots found for match_id {match_id} -- check the id is correct.")

    goals = [s for s in shots if s["outcome"] == "Goal"]
    if goals:
        # the story: whichever goal had the LOWEST xG is the most
        # "unlikely" one -- a natural, data-driven headline for any match.
        story = min(goals, key=lambda s: s["xg"])
        title = f"{story['player']}'s goal came from a shot with just a {story['xg']*100:.0f}% chance of scoring"
    else:
        # fallback for a scoreless match: highlight the single highest-xG
        # chance instead (the "should have scored" moment).
        story = max(shots, key=lambda s: s["xg"])
        title = f"{story['player']}'s {story['xg']*100:.0f}% chance was the best look of the match — and it didn't go in"

    data = []
    for s in shots:
        is_story = s is story
        data.append({
            "x": s["x"], "y": s["y"], "xg": s["xg"], "outcome": s["outcome"],
            "highlight": is_story,
            "annotation": f"{story['player']}, {story['minute']}' — {outcome_label(story['outcome'])}, {story['xg']*100:.0f}% xG" if is_story else None,
            "tooltip": (
                f'<div class="name">{s["player"]}</div>'
                f'<div class="row">{s["team"]} &middot; {s["minute"]}\'</div>'
                f'<div class="row">{outcome_label(s["outcome"])} &middot; xG {s["xg"]:.2f} &middot; {s["body_part"]}</div>'
            ),
        })

    chart = {
        "type": "shot-map", "tabLabel": "Shot Map",
        "metricLabel": "Shot Map (StatsBomb event data)",
        "title": title,
        "blurb": (
            f"Every shot from {match_label or ('match ' + str(match_id))}, "
            "normalized to attack the same goal. Dot size is StatsBomb's xG model "
            "for that shot; filled dots are goals."
        ),
        "footnote": (
            "Source: StatsBomb Open Data (github.com/statsbomb/open-data), free NWSL "
            "event data for the 2018 and 2023 seasons only. Not on the weekly-refresh "
            "schedule the ASA-based tabs use -- this is a static, one-time data source."
        ),
        "data": data,
    }
    return chart


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default=DEFAULT_SEASON, choices=["2018", "2023"])
    parser.add_argument("--match-id", type=int, default=None)
    parser.add_argument("--list-matches", action="store_true")
    parser.add_argument("--out", default="shot_map_demo.html")
    args = parser.parse_args()

    if args.list_matches:
        matches = sb.get_matches(args.season)
        for m in sorted(matches, key=lambda m: m["match_date"]):
            stage = m.get("competition_stage", {}).get("name", "")
            print(f"{m['match_id']}  {m['match_date']}  {m['home_team']['home_team_name']} "
                  f"{m['home_score']}-{m['away_score']} {m['away_team']['away_team_name']}  ({stage})")
        return

    match_id = args.match_id or DEFAULT_MATCH_ID
    match_label = ""
    if match_id == DEFAULT_MATCH_ID:
        match_label = "the 2023 NWSL Championship Final (Seattle Reign 1-2 NJ/NY Gotham FC)"
    else:
        matches = {m["match_id"]: m for m in sb.get_matches(args.season)}
        m = matches.get(match_id)
        if m:
            match_label = f"{m['home_team']['home_team_name']} {m['home_score']}-{m['away_score']} {m['away_team']['away_team_name']} ({m['match_date']})"

    chart = build_shot_map_chart(match_id, match_label)
    html = render_dashboard(
        title="NWSL Shot Map",
        subtitle=f"Real shot locations and xG from {match_label or ('match ' + str(match_id))}, via StatsBomb's free open event data.",
        charts=[chart],
        source_credit="StatsBomb Open Data (github.com/statsbomb/open-data)",
    )
    with open(args.out, "w") as f:
        f.write(html)
    print(f"Wrote {args.out}")
    print(f"Story point: {chart['title']}")


if __name__ == "__main__":
    main()
