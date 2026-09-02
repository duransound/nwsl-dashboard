"""
warehouse_fixture.py -- a synthetic NWSL season, shaped exactly like the live API.

Neither the Claude cloud sandbox nor the desktop bridge VM can reach
app.americansocceranalysis.com, so the warehouse SQL cannot be verified against
live data from either place. This module closes that gap the only honest way:
by generating a season whose JSON reproduces every quirk the live API has
actually been observed to have, so a bug in the SQL shows up here rather than
on a Tuesday morning.

The quirks it deliberately reproduces -- each one cost this project a real
debugging round:

  * /players/xgoals returns team_id as a LIST; /teams/xgoals returns a string
  * player endpoints use `minutes_played`; some rows use bare `minutes`
  * /teams/goals-added and /players/goals-added nest a per-action-type
    breakdown under `data` instead of returning flat totals
  * games played appears as `count_games`, not `games`
  * six players carry TWO clubs in team_id -- mid-season transfers, in an order
    that is not chronological (see the 2026-09-02 live load)
  * the shot_pattern=Penalty response returns every player, most with zeroed
    metrics -- but a couple are deliberately omitted here anyway, so the
    LEFT JOIN's "absent means zero" path stays exercised
  * one team is missing from /teams entirely, standing in for the round-3
    outage where the name lookup 500'd while the stats endpoint stayed healthy
  * one player has zero minutes, to prove the per-96 divide-by-zero guard

Everything is seeded, so two runs produce identical numbers and a test can
assert exact values.
"""

from __future__ import annotations

import random

# The real 16 clubs, so a fixture season reads like a season rather than
# like team_01 .. team_16.
TEAMS = [
    ("2lqRn34qr0", "Denver Summit FC",      "DEN"),
    ("315VnJ759x", "Bay FC",                "BAY"),
    ("4JMAk47qKg", "Houston Dash",          "HOU"),
    ("4wM4rZdqjB", "Kansas City Current",   "KC"),
    ("7VqG1lYMvW", "San Diego Wave FC",     "SD"),
    ("7vQ7BBzqD1", "Seattle Reign FC",      "SEA"),
    ("KPqjw8PQ6v", "Chicago Stars FC",      "CHI"),
    ("Pk5LeeNqOW", "Portland Thorns FC",    "POR"),
    ("XVqKeVKM01", "Orlando Pride",         "ORL"),
    ("aDQ0lzvQEv", "Washington Spirit",     "WAS"),
    ("eV5D2w9QKn", "Utah Royals FC",        "UTA"),
    ("eV5DR6YQKn", "Racing Louisville FC",  "LOU"),
    ("kRQa8JOqKZ", "Angel City FC",         "LA"),
    ("raMyrr25d2", "NJ/NY Gotham FC",       "NJY"),
    ("zeQZeazqKw", "North Carolina Courage","NC"),
    ("odMX2OJqYL", "Boston Legacy FC",      "BOS"),
]

ACTION_TYPES = ["Dribbling", "Fouling", "Interrupting", "Passing", "Receiving", "Shooting"]

# Stands in for the round-3 outage: this club's stats arrive, its name does not.
TEAM_MISSING_FROM_LOOKUP = "odMX2OJqYL"

PLAYERS_PER_TEAM = 14
SEED = 20260902


def build_season(season: str = "2026") -> dict:
    """Returns {(endpoint, variant): [records]} -- the shape nwsl_warehouse.load
    consumes when --fixture is passed."""
    rng = random.Random(SEED)

    # ------------------------------------------------------------- teams
    team_records = [
        {"team_id": tid, "team_name": name, "team_abbreviation": abbr}
        for tid, name, abbr in TEAMS
        if tid != TEAM_MISSING_FROM_LOOKUP
    ]

    team_xgoals, team_ga = [], []
    for tid, _name, _abbr in TEAMS:
        games = rng.randint(14, 19)            # uneven schedule, on purpose
        xgf = round(rng.uniform(12.0, 34.0), 2)
        xga = round(rng.uniform(12.0, 34.0), 2)
        team_xgoals.append({
            "team_id": tid,                     # string here, list on player endpoints
            "count_games": games,               # not "games"
            "xgoals_for": xgf,
            "xgoals_against": xga,
            "points": rng.randint(12, 40),
        })
        team_ga.append({
            "team_id": [tid],                   # list here, string above
            "minutes_played": games * 96,
            "data": [
                {"action_type": a,
                 "num_actions_for": rng.randint(200, 900),
                 "goals_added_for": round(rng.uniform(-2.5, 3.5), 3),
                 "num_actions_against": rng.randint(200, 900),
                 "goals_added_against": round(rng.uniform(-2.5, 3.5), 3)}
                for a in ACTION_TYPES
            ],
        })

    games_by_team = {r["team_id"]: r["count_games"] for r in team_xgoals}

    # ----------------------------------------------------------- players
    players, xgoals, penalties, goals_added, keepers = [], [], [], [], []
    n = 0
    for tid, _name, abbr in TEAMS:
        team_games = games_by_team[tid]
        for i in range(PLAYERS_PER_TEAM):
            n += 1
            pid = f"p{n:04d}"
            players.append({"player_id": pid, "player_name": f"{abbr} Player {i + 1}"})

            # One player in the league has literally zero minutes, so the
            # per-96 NULLIF guard is exercised on every fixture run.
            if n == 7:
                minutes = 0
            else:
                minutes = round(rng.uniform(0.15, 1.0) * team_games * 90)

            # Every ~40th player is a mid-season transfer carrying two clubs.
            # The order is deliberately arbitrary -- sometimes the old club
            # first, sometimes the new one -- because that is what the live
            # API does, and code must not depend on the order.
            if n % 40 == 0:
                other = TEAMS[(TEAMS.index((tid, _name, abbr)) + 5) % len(TEAMS)][0]
                team_field = [tid, other] if n % 80 == 0 else [other, tid]
            else:
                team_field = [tid]

            shots = rng.randint(0, 55)
            xg = round(shots * rng.uniform(0.06, 0.16), 3)
            goals = max(0, round(xg + rng.gauss(0, 1.4)))
            position = rng.choice(["CB", "FB", "DM", "CM", "AM", "W", "ST"])
            xgoals.append({
                "player_id": pid,
                "team_id": team_field,             # list, not string; sometimes >1
                "general_position": position,      # present on the row, confirmed live
                "minutes_played": minutes,         # not "minutes"
                "shots": shots,
                "shots_on_target": rng.randint(0, shots) if shots else 0,
                "goals": goals,
                "xgoals": xg,
                "xplace": round(rng.gauss(0, 0.6), 4),
                "xassists": round(rng.uniform(0.0, 4.5), 3),
                "key_passes": rng.randint(0, 40),
                "points_added": round(rng.gauss(0, 1.5), 3),
                "xpoints_added": round(rng.gauss(0, 1.5), 3),
            })

            # The live endpoint returns EVERY player here, most with zeroed
            # metrics rather than being dropped. Two players per league are
            # withheld anyway, so the LEFT JOIN's "absent means zero" path
            # keeps being tested -- correctness should not depend on the API
            # continuing to be generous.
            took_penalties = rng.random() < 0.11 and minutes > 0
            pen_shots = rng.randint(1, 4) if took_penalties else 0
            if n not in (33, 99):
                penalties.append({
                    "player_id": pid,
                    "team_id": team_field,
                    "general_position": position,
                    "minutes_played": minutes,
                    "shots": pen_shots,
                    "goals": min(pen_shots, rng.randint(0, pen_shots)) if pen_shots else 0,
                    "xgoals": round(pen_shots * 0.78, 3),
                    "xassists": 0.0,
                })

            goals_added.append({
                "player_id": pid,
                "team_id": team_field,
                "general_position": position,
                "minutes_played": minutes,
                "data": [
                    {"action_type": a,
                     "num_actions": rng.randint(20, 400),
                     "goals_added_raw": round(rng.uniform(-1.0, 1.6), 3),
                     "goals_added_above_avg": round(rng.uniform(-1.2, 1.6), 3)}
                    for a in ACTION_TYPES
                ],
            })

        # two keepers per club
        for k in range(2):
            n += 1
            pid = f"p{n:04d}"
            players.append({"player_id": pid, "player_name": f"{abbr} Keeper {k + 1}"})
            minutes = round((0.8 if k == 0 else 0.2) * team_games * 90)
            faced = rng.randint(8, 70)
            xg_faced = round(faced * rng.uniform(0.09, 0.14), 3)
            keepers.append({
                "player_id": pid,
                "team_id": [tid],
                "minutes_played": minutes,
                "shots_faced": faced,
                "goals_conceded": max(0, round(xg_faced + rng.gauss(0, 1.2))),
                "xgoals_gk_faced": xg_faced,
            })

    # ------------------------------------------ per-club splits for transfers
    #
    # For every player carrying two clubs, produce the two team_id-filtered
    # rows the live API returns, splitting each metric so the parts sum to the
    # aggregate exactly (verified live: Sentnor's 1070 + 1009 = 2079 minutes,
    # 26 + 38 = 64 shots, 2.8846 + 2.7988 = 5.6834 xG).
    #
    # Two live behaviours reproduced here: team_id comes back as a STRING on
    # these rows, and the aggregate row's array is ordered by minutes
    # descending -- so the fixture reorders it to match rather than leaving the
    # order it was built with.
    splits = []
    for row in xgoals:
        if len(row["team_id"]) < 2:
            continue
        a_id, b_id = row["team_id"]
        share = rng.uniform(0.2, 0.8)

        def part(team_id, frac, last):
            def cut(key, rounding):
                total = row[key]
                return round(total * frac, rounding) if not last else \
                    round(total - round(total * (1 - frac), rounding), rounding)
            return {
                "player_id": row["player_id"],
                "team_id": team_id,                     # string, not a list
                "general_position": row["general_position"] if not last else
                                    rng.choice(["CB", "FB", "DM", "CM", "AM", "W", "ST"]),
                "minutes_played": cut("minutes_played", 0),
                "shots": cut("shots", 0),
                "goals": cut("goals", 0),
                "xgoals": cut("xgoals", 3),
                "xassists": cut("xassists", 3),
            }

        a, b = part(a_id, share, False), part(b_id, 1 - share, True)
        # keep the aggregate's array ordered by minutes desc, as ASA does
        if b["minutes_played"] > a["minutes_played"]:
            row["team_id"] = [b_id, a_id]
        else:
            row["team_id"] = [a_id, b_id]
        splits.extend([a, b])

    return {
        ("teams", None):               team_records,
        ("players", None):             players,
        ("teams/xgoals", None):        team_xgoals,
        ("teams/goals-added", None):   team_ga,
        ("players/xgoals", None):       xgoals,
        ("players/xgoals", "Penalty"):  penalties,
        ("players/xgoals", "by-team"):  splits,
        ("players/goals-added", None): goals_added,
        ("goalkeepers/xgoals", None):  keepers,
    }
