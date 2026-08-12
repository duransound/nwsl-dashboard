"""
Generates preview charts from a real, hand-verified snapshot of NWSL 2025
season data (pulled from the ASA API on 2026-08-11). This sandbox's outbound
network is locked down to a package/domain allowlist that the live ASA API
isn't on, so this snapshot substitutes for a live fetch -- nwsl_xg_charts.py
hits the live API and will work normally on a machine without that
restriction (e.g. your own laptop).
"""

import pandas as pd

from nwsl_xg_charts import (
    chart_player_goals_vs_xg,
    chart_team_xg_differential,
    chart_team_xgf_vs_xga,
)

SEASON = "2025"

# Full 14-team table, verbatim from GET /nwsl/teams/xgoals?season_name=2025
team_rows = [
    ("315VnJ759x", "Bay FC", "BAY", 26, 303, 334, 26, 40, -14, 30.7722, 36.4125, -5.6402, 20, 33.018),
    ("4JMAk47qKg", "Houston Dash", "HOU", 26, 239, 373, 25, 39, -14, 24.5169, 35.6948, -11.1779, 30, 26.48),
    ("4wM4rZdqjB", "Kansas City Current", "KC", 27, 380, 257, 49, 14, 35, 47.3884, 18.4715, 28.9169, 65, 55.105),
    ("7VqG1lYMvW", "San Diego Wave FC", "SD", 27, 346, 296, 38, 35, 3, 32.478, 31.9599, 0.5181, 37, 35.476),
    ("7vQ7BBzqD1", "Seattle Reign FC", "SEA", 27, 242, 351, 30, 30, 0, 27.1353, 35.8995, -8.7641, 39, 29.643),
    ("KPqjw8PQ6v", "Chicago Stars FC", "CHI", 26, 277, 388, 32, 50, -18, 30.2733, 44.9084, -14.6351, 20, 25.837),
    ("Pk5LeeNqOW", "Portland Thorns FC", "POR", 28, 400, 349, 36, 29, 7, 42.4962, 38.7693, 3.7269, 43, 40.024),
    ("XVqKeVKM01", "Orlando Pride", "ORL", 29, 371, 351, 30, 28, 2, 39.8608, 31.2588, 8.602, 44, 39.903),
    ("aDQ0lzvQEv", "Washington Spirit", "WAS", 30, 387, 369, 42, 32, 10, 43.998, 38.5319, 5.4661, 49, 37.328),
    ("eV5D2w9QKn", "Utah Royals FC", "UTA", 26, 312, 341, 27, 40, -13, 25.6718, 41.1531, -15.4813, 25, 26.032),
    ("eV5DR6YQKn", "Racing Louisville FC", "LOU", 27, 408, 369, 35, 36, -1, 38.9097, 37.1702, 1.7395, 38, 37.918),
    ("kRQa8JOqKZ", "Angel City FC", "LA", 26, 349, 336, 30, 38, -8, 31.1325, 36.568, -5.4356, 27, 31.02),
    ("raMyrr25d2", "NJ/NY Gotham FC", "NJY", 29, 343, 247, 37, 23, 14, 32.4922, 26.9355, 5.5567, 45, 40.465),
    ("zeQZeazqKw", "North Carolina Courage", "NC", 26, 328, 324, 35, 38, -3, 39.6704, 33.0622, 6.6082, 35, 40.452),
]
team_df = pd.DataFrame(team_rows, columns=[
    "team_id", "team_name", "team_abbreviation", "count_games", "shots_for", "shots_against",
    "goals_for", "goals_against", "goal_difference", "xgoals_for", "xgoals_against",
    "xgoal_difference", "points", "xpoints",
])

# Top players by xG (min. 1800 minutes), verbatim from GET /nwsl/players/xgoals,
# names verified individually against GET /nwsl/players?player_id=<id>
player_rows = [
    ("Temwa Chawinga", "KC", 2023, 59, 14.0367, 15),
    ("Manaka Matsukubo", "NC", 2322, 63, 9.916, 11),
    ("Reilyn Turner", "POR", 2240, 67, 9.1423, 6),
    ("Esther González", "NJY", 2370, 66, 8.5522, 13),
    ("Emma Sears", "LOU", 2664, 64, 8.3278, 10),
    ("Ally Schlegel", "CHI", 2248, 52, 6.9063, 3),
    ("Racheal Kundananji", "BAY", 2117, 76, 6.7979, 4),
    ("Olivia Moultrie", "POR", 2707, 77, 6.3337, 8),
    ("Ludmila", "CHI", 2046, 45, 5.9939, 10),
    ("Bia Zaneratto", "KC", 1893, 46, 5.7152, 7),
    ("Mina Tanaka", "UTA", 2265, 47, 5.7004, 6),
    ("Haley McCutcheon", "ORL", 2797, 39, 5.605, 4),
]
player_df = pd.DataFrame(player_rows, columns=["player_name", "team", "minutes", "shots", "xgoals", "goals"])

chart_team_xg_differential(team_df, SEASON, f"team_xg_differential_{SEASON}_demo.png")
chart_team_xgf_vs_xga(team_df, SEASON, f"team_xgf_vs_xga_{SEASON}_demo.png")
chart_player_goals_vs_xg(player_df, SEASON, f"player_goals_vs_xg_{SEASON}_demo.png", top_n=12)

print("Wrote 3 demo PNGs.")
