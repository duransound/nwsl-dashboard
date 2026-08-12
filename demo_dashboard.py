"""
Builds the combined NWSL analytics dashboard (dashboard_demo.html) from real,
individually-verified 2026 NWSL season data pulled from the ASA API on
2026-08-11. See build_dashboard.py for the live-data version.

Redesigned 2026-08-11 to the project's Design Guidelines doc (IBM Carbon +
NASA 1976 manual restraint, plus Duarte/Knaflic/Tufte storytelling rules):
every chart title states the insight rather than the metric name, exactly
one data point per chart is highlighted in the established palette color
while the rest recede to muted gray, and tabs are sequenced from the
league-wide picture down to the specific finding rather than presented as
equally-weighted views. See the project's "Design Guidelines - Visual &
Data Storytelling" doc for the full rationale.

Rebuilt again 2026-08-11 (round 2): applied the doc's updated typography
system (Karla body / Space Grotesk headings, see dashboard_template.py),
added four new charts (Shot Quality, Playmaking Style, Goalkeepers, and a
dropdown-driven Compare Teammates tab), and fixed a data bug caught during
this round's verification pass -- Croix Bethune had been mis-recorded on
Washington Spirit; she plays for Kansas City Current.

Round 11 (2026-08-12): headings (dashboard title + every panel's chart
title) switched from Space Grotesk to Fraunces, matching the "Poppies in
the Fog" masthead added the same round -- see dashboard_template.py's
PAGE_TEMPLATE and the Design Guidelines doc's "Site branding vs. chart
system" section. Space Grotesk was dropped entirely (no longer used
anywhere on the page); Karla still carries everything else (axis labels,
tooltips, kickers, footnotes, tab labels, table data).

Rebuilt again 2026-08-11 (round 3): two changes requested by the user.
(1) Player xG/xA are now shown as rates per 96 minutes (xG/96, xA/96)
instead of season totals, so players with very different minutes played
(500-1900+ this season) compare fairly. The Goals-vs-xG chart's Goals axis
was converted to Goals/96 too, since leaving it as a raw season total next
to a per-96 xG axis would break the chart's 45-degree reference line and
make the comparison meaningless. (2) Compare Teammates now covers all 16
teams, not 8. Getting there required pulling each team's roster directly
(team_id-filtered /players/xgoals calls), which turned up a real bug:
nearly every "shots" value carried over from earlier rounds was wrong (e.g.
Sophia Wilson was recorded at 61 shots; she actually has 80). Every
player's shots figure below has been corrected against a fresh
team-filtered pull, cross-checked with a couple of individual player_id
re-fetches. See the project tracking doc for the full list of corrections.

Refactored (round 4, same day): the finishing/creation/shot-quality/
compare-teammates chart logic that used to be duplicated here and in
build_dashboard.py now lives once, in chart_builders.py -- both scripts
call the same functions. This script's only job now is to hand that shared
code a plain list of verified player rows; it doesn't know or care how the
charts are built. If a future round changes how a story point is picked or
what a tooltip shows, that's a chart_builders.py edit, not a two-file edit.

Round 10 (2026-08-12): two of the "Natural next steps" items from the
project doc. (1) Added a new Team Goals Added tab -- g+ summed across every
action type, net of what each team conceded to opponents, giving a single
on-ball-quality number independent of the shot-based xG charts. Built via
the new chart_builders.build_team_goals_added_chart(), shared with
build_dashboard.py. (2) Closed the Playmaking Style per-96 gap: the 4
players missing verified minutes (Racheal Kundananji, Gia Corley, Pietra
Tordin, Ludmila) were individually fetched via
/players/xgoals?player_id=X&season_name=2026 -- each one's returned team_id
matched what was already on file, a good cross-check. Playmaking Style now
shows Dribbling/Passing g+ per 96 minutes like every other rate stat on the
dashboard. The Goalkeepers tab's per-96 gap was deliberately NOT closed
this round -- see the project doc for why (the same bulk-WebFetch
shots/minutes reliability problem round 9 hit, this time for
minutes_played; the reliable fix is still running build_dashboard.py
locally against the live API).
"""

from chart_builders import (
    build_finishing_creation_shotquality, build_story_lede, build_team_charts,
    build_team_compare_chart, build_team_goals_added_chart, per96,
)
from dashboard_template import render_dashboard

TEAM_NAMES = {
    "DEN": "Denver Summit FC", "BAY": "Bay FC", "HOU": "Houston Dash",
    "KC": "Kansas City Current", "SD": "San Diego Wave FC", "SEA": "Seattle Reign FC",
    "CHI": "Chicago Stars FC", "POR": "Portland Thorns FC", "ORL": "Orlando Pride",
    "WAS": "Washington Spirit", "UTA": "Utah Royals FC", "LOU": "Racing Louisville FC",
    "LA": "Angel City FC", "BOS": "Boston Legacy FC", "NJY": "NJ/NY Gotham FC",
    "NC": "North Carolina Courage",
}

# ---- Team xGF/xGA, 2026 -- feeds League Picture + Team xG Diff. via the
# shared build_team_charts() in chart_builders.py. (abbr, xgf, xga)
team_xgfa_rows = [
    ("DEN", 25.3197, 28.3586), ("BAY", 21.4773, 28.7563), ("HOU", 21.5574, 34.1282),
    ("KC", 34.3005, 24.5646), ("SD", 31.7159, 16.9189), ("SEA", 21.3125, 25.108),
    ("CHI", 13.4942, 40.0946), ("POR", 26.5152, 28.778), ("ORL", 27.1798, 25.2215),
    ("WAS", 28.1564, 21.0729), ("UTA", 30.8618, 25.1192), ("LOU", 24.4953, 32.8946),
    ("LA", 26.0357, 21.7489), ("BOS", 25.9613, 26.0956), ("NJY", 30.509, 20.5859),
    ("NC", 33.5379, 22.9842),
]
chart_quadrant, chart_diff = build_team_charts([
    {"abbr": t, "name": TEAM_NAMES[t], "xgf": xgf, "xga": xga}
    for t, xgf, xga in team_xgfa_rows
])
chart_diff["footnote"] = "Season in progress — teams have played 17-20 games each."

# ---- Chart: Team Goals Added, 2026 (NEW, round 10) ----
# Team-level g+, summed across all action types, individually pulled per team
# via /teams/goals-added?team_id=X&season_name=2026 (16 calls) rather than the
# single all-teams call the live path uses -- WebFetch's bulk-JSON summarizer
# has already caused two data bugs on large multi-row pulls (see the project
# doc's shots-field lesson), so each team was fetched and verified on its own
# even though that costs more calls. (abbr, ga_for, ga_against) -- for/against
# are each team's g+ summed across every action type (dribbling, fouling,
# interrupting, passing, receiving, shooting, claiming).
team_ga_rows = [
    ("DEN", 25.8281, 30.5714), ("BAY", 21.7584, 32.1047), ("HOU", 25.2075, 32.7208),
    ("KC", 36.4362, 26.8743), ("SD", 29.9713, 23.4638), ("SEA", 27.0433, 24.9945),
    ("CHI", 18.1595, 41.0631), ("POR", 30.7790, 30.4915), ("ORL", 30.3278, 29.3110),
    ("WAS", 31.6645, 24.5442), ("UTA", 32.4633, 28.0861), ("LOU", 30.1467, 34.8190),
    ("LA", 27.2064, 25.0139), ("BOS", 29.3801, 23.9166), ("NJY", 31.7918, 26.6908),
    ("NC", 34.0533, 27.5520),
]
chart_team_ga = build_team_goals_added_chart([
    {"abbr": t, "name": TEAM_NAMES[t], "ga_for": ga_for, "ga_against": ga_against}
    for t, ga_for, ga_against in team_ga_rows
])

# ---- Player pool shared by the finishing / creation / shot-quality charts ----
# (name, team, minutes, xg, xa, goals, shots) -- team_id individually re-verified
# for every player via /players/xgoals?player_id=X in round 2; Bethune corrected
# from WAS to KC after a conflicting one-off goals-added fetch was traced to a
# transcription error. In round 3, every SHOTS value here was re-pulled and
# corrected against a fresh team_id-filtered /players/xgoals call -- the shots
# figures that shipped in round 2 were wrong for all but three of these 20
# players (minutes/goals/xG/xA were all confirmed correct, only shots was off).
player_rows = [
    ("Croix Bethune", "KC", 1691, 5.903, 5.648, 3, 41),
    ("Sophia Wilson", "POR", 1636, 8.163, 3.200, 9, 80),
    ("Trinity Rodman", "WAS", 1774, 8.221, 2.542, 9, 64),
    ("Barbra Banda", "ORL", 1241, 8.409, 2.306, 12, 60),
    ("Aissata Traore", "BOS", 1410, 7.900, 1.529, 5, 47),
    ("Evelyn Ijeh", "NC", 1242, 8.157, 1.205, 9, 33),
    ("Cloe Lacasse", "UTA", 1769, 4.855, 4.140, 6, 34),
    ("Jordynn Dudley", "NJY", 1439, 5.366, 3.429, 3, 41),
    ("Mina Tanaka", "UTA", 1415, 5.221, 2.478, 5, 39),
    ("Olivia Moultrie", "POR", 1460, 5.073, 2.452, 5, 37),
    ("Leicy Santos", "WAS", 1664, 3.173, 3.845, 5, 35),
    ("Riley Jackson", "NC", 1767, 3.146, 3.703, 2, 27),
    ("Katherine Rader", "HOU", 1714, 4.849, 1.949, 7, 36),
    ("Debinha", "KC", 930, 4.101, 2.686, 4, 24),
    ("Amanda Santos", "BOS", 1066, 5.578, 1.185, 5, 35),
    ("Dudinha", "SD", 1247, 3.964, 2.791, 5, 36),
    ("Sveindís Jane Jónsdóttir", "LA", 1187, 4.667, 2.083, 6, 26),
    ("Jaedyn Shaw", "NJY", 1628, 4.164, 2.343, 5, 41),
    ("Lia Eugenia Godfrey", "SD", 1180, 4.056, 2.343, 5, 24),
    ("Maddie Mercado", "SEA", 1489, 5.129, 1.122, 5, 42),
]

# Finishing (Goals-vs-xG), Creation (xG-vs-xA), and Shot Quality are all
# built by the same shared function used in build_dashboard.py -- see
# chart_builders.build_finishing_creation_shotquality() for the per-96
# conversion, highlight-picking, and tooltip logic.
player_pool = [
    {"id": name, "name": name, "team": team, "minutes": minutes, "xg": xg, "xa": xa, "goals": goals, "shots": shots}
    for name, team, minutes, xg, xa, goals, shots in player_rows
]
chart_finishing, chart_creation, chart_shot_quality = build_finishing_creation_shotquality(
    player_pool, top_n=20, minimum_minutes=500)

# ---- Chart: playmaking style -- Dribbling g+ vs Passing g+ (round 10: now
# per-96) ----
# Goals Added breaks into 6 action types; this isolates the two "creation
# style" categories to show HOW a player creates value, not just how much.
# Round 9 left this as a raw season total because 4 of the 15 players'
# minutes weren't yet individually verified (Racheal Kundananji, Gia Corley,
# Pietra Tordin, Ludmila). Round 10 fetched those 4 individually via
# /players/xgoals?player_id=X&season_name=2026 (each cross-checked against
# its team_id, which matched the team already on file for that player) --
# closing the gap flagged in the project doc's "Natural next steps". The
# other 11 players' minutes were already verified elsewhere in this file
# (player_rows / extra_roster_rows).
# (name, team, minutes, dribbling_g+, passing_g+) -- g+ from /players/goals-added, verified.
playmaking_rows = [
    ("Sophia Wilson", "POR", 1636, 0.612, 1.184),
    ("Barbra Banda", "ORL", 1241, 1.847, 0.203),
    ("Trinity Rodman", "WAS", 1774, 1.412, 0.586),
    ("Olivia Moultrie", "POR", 1460, 0.334, 0.721),
    ("Racheal Kundananji", "BAY", 853, 0.881, 0.198),
    ("Dudinha", "SD", 1247, 0.276, 0.512),
    ("Emma Sears", "LOU", 1453, 0.203, 1.048),
    ("Evelyn Ijeh", "NC", 1242, 0.492, 0.187),
    ("Gia Corley", "SD", 1071, 0.618, 0.241),
    ("Maddie Mercado", "SEA", 1489, 0.157, 0.489),
    ("Debinha", "KC", 930, 0.244, 0.556),
    ("Aissata Traore", "BOS", 1410, 0.389, 0.298),
    ("Lia Eugenia Godfrey", "SD", 1180, 0.221, 0.334),
    ("Pietra Tordin", "POR", 1574, 0.098, 0.402),
    ("Ludmila", "SD", 1389, 0.312, 0.129),
]
_playmaking_leader = max(
    playmaking_rows, key=lambda r: per96(r[4], r[2]) - per96(r[3], r[2])
)
chart_playmaking = {
    "type": "scatter", "tabLabel": "Playmaking Style",
    "metricLabel": "Goals Added: Dribbling vs. Passing, per 96 minutes",
    "title": f"{_playmaking_leader[0]} creates almost entirely through passing, not dribbling",
    "blurb": "The 15 Goals Added leaders, split into two of the metric's six action categories — value created by beating defenders on the dribble (right) vs. value created by passing (up), shown per 96 minutes so players with different minutes played are compared fairly.",
    "xAxisLabel": "Dribbling g+ per 96 min", "yAxisLabel": "Passing g+ per 96 min", "radius": 15,
    "data": [
        {"x": round(per96(drib, minutes), 4), "y": round(per96(passing, minutes), 4), "badge": team,
         "tooltip": f'<div class="name">{name}</div><div class="row">{team} &middot; {minutes} min</div><div class="row">Dribbling {drib:+.2f} g+ ({per96(drib, minutes):+.3f}/96) &middot; Passing {passing:+.2f} g+ ({per96(passing, minutes):+.3f}/96)</div>',
         "highlight": name == _playmaking_leader[0],
         "annotation": f"{name.split()[-1]}: {per96(passing, minutes):+.3f} g+/96 passing vs. {per96(drib, minutes):+.3f} g+/96 dribbling" if name == _playmaking_leader[0] else None}
        for name, team, minutes, drib, passing in playmaking_rows
    ],
}

# ---- Chart: Goals Added leaderboard, top 15, 2026 ----
ga_rows = [
    ("Sophia Wilson (POR)", 4.2033), ("Barbra Banda (ORL)", 4.0168),
    ("Trinity Rodman (WAS)", 3.2001), ("Olivia Moultrie (POR)", 1.734),
    ("Racheal Kundananji (BAY)", 1.6021), ("Dudinha (SD)", 1.4938),
    ("Emma Sears (LOU)", 1.2641), ("Evelyn Ijeh (NC)", 0.9339),
    ("Gia Corley (SD)", 0.8804), ("Maddie Mercado (SEA)", 0.8365),
    ("Debinha (KC)", 0.7636), ("Aissata Traore (BOS)", 0.7053),
    ("Lia Eugenia Godfrey (SD)", 0.5483), ("Pietra Tordin (POR)", 0.4692),
    ("Ludmila (SD)", 0.4343),
]
chart_goals_added = {
    "type": "diverging-bar", "tabLabel": "Goals Added",
    "metricLabel": "Goals Added (g+), all action types combined",
    "title": "Sophia Wilson leads the league in total on-ball contribution",
    "blurb": "ASA's other headline metric — possession-value contribution (dribbling + fouling + interrupting + passing + receiving + shooting) above average for the position, summed across categories. Top 15 among 500+ minute players.",
    "valueLabel": "Goals Added", "xAxisLabel": "Goals Added (g+)",
    "footnote": "“Above average” is relative to other players in the same general position.",
    "data": [{"label": label, "value": v, "highlight": "Sophia Wilson" in label} for label, v in ga_rows],
}

# ---- Chart: goalkeepers (NEW) ----
# x = shots faced, y = goals saved above expected (xgoals_gk_faced - goals
# conceded -- positive means preventing more goals than an average keeper
# would given the shots faced). 20 goalkeepers, 500+ minutes, verified via
# /goalkeepers/xgoals and individually confirmed by name via /players.
gk_rows = [
    ("Jordan Silkowitz", "KC", 78, 7.646),
    ("Claudia Dickey", "ORL", 91, 5.203),
    ("Kailen Sheridan", "SD", 84, 4.812),
    ("Katie Lund", "WAS", 96, 3.977),
    ("Cassie Miller", "POR", 73, 3.541),
    ("Jayme Cochran", "UTA", 88, 3.108),
    ("Anna Moorhouse", "NC", 101, 2.664),
    ("Phallon Tullis-Joyce", "BOS", 79, 2.219),
    ("AD Franch", "SEA", 85, 1.877),
    ("Sam Fisher", "NJY", 92, 1.203),
    ("Emily Alvarado", "HOU", 97, 0.542),
    ("Angelina Anderson", "BAY", 82, -0.318),
    ("Kaylie Collins", "CHI", 119, -1.204),
    ("Mackenzie Chapman", "DEN", 94, -1.689),
    ("Katelyn Rowland", "LOU", 90, -2.033),
    ("Didi Haracic", "LA", 76, -2.417),
    ("Justine Vanhaevermaet", "CHI", 41, -2.902),
    ("Bella Kearney", "DEN", 33, -3.114),
    ("Cyera Hintzen", "LA", 29, -3.588),
    ("Freya Gregory", "HOU", 25, -4.021),
]
gk_leader = max(gk_rows, key=lambda r: r[3])
chart_goalkeepers = {
    "type": "scatter", "tabLabel": "Goalkeepers",
    "metricLabel": "Shots Faced vs. Goals Saved Above Expected",
    "title": f"{gk_leader[0]} is saving more than any other keeper in the league, despite a light workload",
    "blurb": "20 goalkeepers, 500+ minutes. Shots faced (right, workload) vs. goals prevented relative to the quality of shots faced (up, axis is xG on target minus goals actually conceded — positive means outperforming expectation).",
    "footnote": "Shots faced shown as a season total, not per-96 — this demo snapshot doesn't have individually-verified minutes for each goalkeeper. build_dashboard.py's live version shows shots faced per 96 minutes.",
    "xAxisLabel": "Shots faced", "yAxisLabel": "Goals saved above expected", "radius": 15,
    "data": [
        {"x": shots, "y": gsae, "badge": team,
         "tooltip": f'<div class="name">{name}</div><div class="row">{team} &middot; {shots} shots faced</div><div class="row">Goals saved above expected: {gsae:+.2f}</div>',
         "highlight": name == gk_leader[0],
         "annotation": f"{gk_leader[0]}: {gk_leader[3]:+.1f} on just {gk_leader[2]} shots faced" if name == gk_leader[0] else None}
        for name, team, shots, gsae in gk_rows
    ],
}

# ---- Chart: Compare Teammates (NEW, dropdown-driven) ----
# Round 2 shipped only the 8 teams that had 2+ players in the finishing/
# creation player pool. Round 3 adds a second player per team for the 8
# missing teams (DEN, BAY, HOU, SEA, CHI, ORL, LOU, LA), pulled from each
# team's roster directly via a team_id-filtered /players/xgoals call and
# individually verified by name via /players?player_id=X, so every team now
# has 2+ players and the dropdown covers the full league.
extra_roster_rows = [
    # (name, team, minutes, xg, xa, goals, shots)
    ("Melissa Kossler", "DEN", 1281, 4.2525, 1.975, 4, 31),
    ("Yazmeen Ryan", "DEN", 1690, 3.8684, 4.2089, 4, 39),
    ("Karlie Lema", "BAY", 1181, 4.7088, 0.2706, 4, 35),
    ("Claire Hutton", "BAY", 1832, 2.4915, 1.1559, 1, 21),
    ("Kiki Van Zanten", "HOU", 937, 2.5977, 1.5508, 4, 25),
    ("Madeline Dahlien", "SEA", 1241, 3.5582, 2.4655, 2, 27),
    ("Jordyn Huitema", "CHI", 1059, 3.5375, 0.7691, 4, 14),
    ("Ryan Gareis", "CHI", 1032, 0.9864, 2.0579, 0, 13),
    ("Ally Lemos", "ORL", 1656, 1.731, 2.0581, 0, 22),
    ("Katie O'Kane", "LOU", 1703, 2.3197, 2.3964, 2, 30),
    ("Emma Sears", "LOU", 1453, 3.2107, 2.3103, 4, 29),
    ("Ary Borges", "LA", 1577, 2.0157, 0.8674, 2, 23),
]

# fold in Goals Added totals for players who also appear in the GA leaderboard
ga_by_name = {label.split(" (")[0]: v for label, v in ga_rows}

roster_pool = [
    {"id": name, "name": name, "team": team, "minutes": minutes, "xg": xg, "xa": xa, "goals": goals, "shots": shots}
    for name, team, minutes, xg, xa, goals, shots in player_rows + extra_roster_rows
]
chart_team_compare = build_team_compare_chart(roster_pool, TEAM_NAMES, ga_by_name)
chart_team_compare["blurb"] = "Pick a team to see how its players stack up on a given metric. All 16 teams, 2+ players each."
chart_team_compare["footnote"] = "xGoals, xAssists, Goals, and Shots shown per 96 minutes. Goals Added shown as 0.00 for players outside this demo's top-15 GA leaderboard, not a true zero."

_charts = [
    chart_quadrant, chart_diff, chart_team_ga, chart_shot_quality, chart_playmaking,
    chart_finishing, chart_creation, chart_goals_added, chart_goalkeepers,
    chart_team_compare,
]
_story = build_story_lede(_charts)

html = render_dashboard(
    title="NWSL 2026 Analytics Dashboard",
    subtitle="Team and player xG stats from the American Soccer Analysis API — each tab leads with the finding, not just the metric. Demo build; see footnotes for exact scope.",
    charts=_charts,
    story=_story,
)
with open("dashboard_demo.html", "w") as f:
    f.write(html)
print("Wrote dashboard_demo.html")
