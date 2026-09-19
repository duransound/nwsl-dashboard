"""
Matchup Predictor -- Elo ratings from season results, and a three-outcome
probability for any pairing.

WHY ELO AND NOT AN xG-BASED POISSON MODEL

Poisson-from-xG is the obvious move on a dashboard made of xG, and it was the
first thing considered here. It was rejected for one reason: every other tab
already argues from expected goals, so an xG-driven predictor would agree with
them by construction and tell a reader nothing new. Elo is built from results
only. When it disagrees with the xG tabs -- and on this dashboard it regularly
will -- that disagreement is information rather than a rounding artifact.

TWO WAYS THE RATINGS GET BUILT, AND THE PAGE SAYS WHICH ONE RAN

  * RESULTS PATH ("games"). Game-by-game Elo, chronological, from an actual
    scoreline feed. Standard update with a home-field term and a
    margin-of-victory multiplier. This is real Elo.

  * TABLE PATH ("totals"). No per-game feed answered, so there is nothing to
    iterate over. Ratings are then a DOCUMENTED APPROXIMATION -- a
    standardised blend of points per game and goal difference per game mapped
    onto the Elo scale. It is not Elo; it is a rating that behaves like one,
    and the tab says so in its own footnote rather than in a comment only a
    developer reads.

Calling both "Elo" without distinguishing them would be the exact failure the
PLAYBOOK warns about in §7: an inferred rule presented as a measurement.

THE DRAW MODEL

A plain Elo expectation is a single number between 0 and 1 and cannot, on its
own, say how often a match ends level. Splitting it into three outcomes uses
the Davidson (1970) ties model, the standard extension of Bradley-Terry to
draws:

    x  = 10 ** ((Ra + H - Rb) / 400)
    Z  = x + 1 + nu * sqrt(x)
    P(A wins) = x / Z      P(draw) = nu*sqrt(x) / Z      P(B wins) = 1 / Z

nu controls how draw-prone the competition is. It is NOT a guess: for an even
matchup (x = 1) the model gives P(draw) = nu / (2 + nu), so the league's own
draw rate d pins it exactly at

    nu = 2d / (1 - d)

and the league draw rate is available on BOTH paths -- counted from the games
on the results path, and derived exactly from total points and total games on
the table path (see standings.derived_league_draws). So the draw frequency
this tab predicts is calibrated to the season it is describing.
"""

from __future__ import annotations

import math
from statistics import mean, pstdev

# Elo points of home advantage. 60 is the customary football figure and is
# roughly what a 55%-ish home win rate implies; it is a stated constant rather
# than a fitted one because fitting a single parameter on a 16-team, 4-month
# sample would be noise dressed as rigour.
HOME_ADVANTAGE = 60.0

# Update size per game. 20 is the standard club-football K. Over a ~26-game
# NWSL season it lets ratings move meaningfully without letting one result
# dominate.
K_FACTOR = 20.0

START_RATING = 1500.0

# Table-path only: how many Elo points one standard deviation of league
# strength is worth. 80 puts a typical 16-team league inside roughly a
# 300-point spread, which is the range game-by-game Elo produces for the same
# competition -- chosen so the two paths are on a comparable scale, and stated
# because it is the one free parameter on that path.
SPREAD_PER_SD = 80.0

# Table-path weighting. Points are what a season is scored on; goal difference
# is the better predictor of what happens next. Splitting 60/40 toward points
# keeps the ratings recognisably about the table while letting a team that
# wins narrowly and often sit slightly below a team that wins heavily.
PPG_WEIGHT = 0.6
GD_WEIGHT = 0.4

DEFAULT_DRAW_RATE = 0.24


def _mov_multiplier(goal_diff, rating_diff):
    """FiveThirtyEight's margin-of-victory multiplier.

    A 4-0 is more evidence than a 1-0, but not four times as much, so the
    margin enters logarithmically. The second factor damps the bonus when a
    strong favourite wins big, which is what stops Elo inflating for a good
    team that keeps beating bad ones.
    """
    return (math.log(abs(goal_diff) + 1.0)
            * (2.2 / (0.001 * rating_diff + 2.2)))


def elo_from_games(games, abbr_of, k=K_FACTOR, home_advantage=HOME_ADVANTAGE,
                   start=START_RATING):
    """Chronological game-by-game Elo. games: standings.normalize_games output.

    Returns (ratings, history) where ratings is {abbr: float} and history is
    [{game_id, date, home, away, home_goals, away_goals, home_elo_before,
    away_elo_before, home_elo_after, away_elo_after}] -- kept so a reader can
    be shown how a rating got where it is rather than being asked to trust it.
    """
    ratings = {}
    history = []
    for g in games:
        home = abbr_of.get(g["home_id"], g["home_id"])
        away = abbr_of.get(g["away_id"], g["away_id"])
        rh = ratings.setdefault(home, float(start))
        ra = ratings.setdefault(away, float(start))

        expected_home = 1.0 / (1.0 + 10.0 ** (-((rh + home_advantage) - ra) / 400.0))
        if g["home_goals"] > g["away_goals"]:
            actual_home, winner_edge = 1.0, (rh + home_advantage) - ra
        elif g["home_goals"] < g["away_goals"]:
            actual_home, winner_edge = 0.0, ra - (rh + home_advantage)
        else:
            actual_home, winner_edge = 0.5, 0.0

        margin = abs(g["home_goals"] - g["away_goals"])
        mult = _mov_multiplier(margin, winner_edge) if margin else 1.0
        delta = k * mult * (actual_home - expected_home)

        ratings[home] = rh + delta
        ratings[away] = ra - delta
        history.append({
            "game_id": g["game_id"], "date": g["date"],
            "home": home, "away": away,
            "home_goals": g["home_goals"], "away_goals": g["away_goals"],
            "home_elo_before": round(rh, 1), "away_elo_before": round(ra, 1),
            "home_elo_after": round(ratings[home], 1),
            "away_elo_after": round(ratings[away], 1),
        })
    return ratings, history


def elo_from_table(table_rows, spread=SPREAD_PER_SD, start=START_RATING):
    """The documented approximation used when no per-game feed answered.

    table_rows: standings.build_table output. Uses points per game and goal
    difference per game, each standardised across the league, blended, and
    scaled onto the Elo axis. Teams missing either input are left unrated
    rather than parked at the league average -- an unrated team is excluded
    from the picker instead of being given a fictitious 1500.
    """
    usable = [r for r in table_rows
              if r.get("gp") and r.get("pts") is not None and r.get("gd") is not None]
    if len(usable) < 2:
        return {}
    ppg = [r["pts"] / r["gp"] for r in usable]
    gdg = [r["gd"] / r["gp"] for r in usable]
    ppg_mu, ppg_sd = mean(ppg), pstdev(ppg)
    gdg_mu, gdg_sd = mean(gdg), pstdev(gdg)

    ratings = {}
    for r, p, g in zip(usable, ppg, gdg):
        zp = 0.0 if ppg_sd == 0 else (p - ppg_mu) / ppg_sd
        zg = 0.0 if gdg_sd == 0 else (g - gdg_mu) / gdg_sd
        ratings[r["abbr"]] = start + spread * (PPG_WEIGHT * zp + GD_WEIGHT * zg)
    return ratings


def nu_from_draw_rate(draw_rate):
    """Davidson's tie parameter pinned to an observed draw rate.

    P(draw) between evenly matched sides is nu / (2 + nu), so inverting gives
    nu = 2d / (1 - d). Clamped away from the ends, where the inversion blows
    up on a rate of exactly 0 or 1 that a short season can easily produce.
    """
    if draw_rate is None:
        draw_rate = DEFAULT_DRAW_RATE
    d = min(max(float(draw_rate), 0.01), 0.60)
    return 2.0 * d / (1.0 - d)


def probabilities(rating_a, rating_b, nu, home_advantage=HOME_ADVANTAGE,
                  venue="home"):
    """P(A wins), P(draw), P(B wins) for A hosting B (venue="home"),
    visiting B ("away"), or at a neutral site ("neutral")."""
    edge = {"home": home_advantage, "away": -home_advantage,
            "neutral": 0.0}.get(venue, home_advantage)
    x = 10.0 ** ((rating_a + edge - rating_b) / 400.0)
    root = math.sqrt(x)
    z = x + 1.0 + nu * root
    return x / z, (nu * root) / z, 1.0 / z


def draw_rate_from_games(games):
    if not games:
        return None
    drawn = sum(1 for g in games if g["home_goals"] == g["away_goals"])
    return drawn / len(games)


# ------------------------------------------------------------------ self-test

if __name__ == "__main__":
    # A three-outcome model must be a probability distribution, always.
    for ra, rb, nu, venue in [(1500, 1500, 0.63, "neutral"),
                              (1800, 1200, 0.63, "home"),
                              (1200, 1800, 0.10, "away"),
                              (1500, 1500, 0.01, "home")]:
        w, d, l = probabilities(ra, rb, nu, venue=venue)
        assert abs(w + d + l - 1.0) < 1e-12, (ra, rb, nu, venue, w, d, l)
        assert min(w, d, l) > 0
    print("probabilities: sum to 1 and stay positive across the range")

    # Symmetry: equal ratings at a neutral venue must be a coin flip.
    w, d, l = probabilities(1500, 1500, 0.63, venue="neutral")
    assert abs(w - l) < 1e-12 and abs(d - 0.63 / 2.63) < 1e-12, (w, d, l)
    print(f"even neutral matchup: {w:.1%} / {d:.1%} / {l:.1%}")

    # Home advantage must actually favour the host.
    hw, _, _ = probabilities(1500, 1500, 0.63, venue="home")
    aw, _, _ = probabilities(1500, 1500, 0.63, venue="away")
    assert hw > w > aw, (hw, w, aw)
    print(f"home {hw:.1%} vs neutral {w:.1%} vs away {aw:.1%}")

    # nu calibration round-trips: feed a draw rate in, get it back out of an
    # even matchup.
    for target in (0.10, 0.24, 0.33):
        nu = nu_from_draw_rate(target)
        _, dd, _ = probabilities(1500, 1500, nu, venue="neutral")
        assert abs(dd - target) < 1e-9, (target, dd)
    print("nu calibration: round-trips at 10%, 24% and 33% draw rates")

    # Elo from games: the team that wins everything must end up top, and the
    # margin-of-victory damping must make a 4-0 worth more than a 1-0 but less
    # than four times as much.
    abbr_of = {"A": "AAA", "B": "BBB", "C": "CCC"}
    def game(h, a, hg, ag, i):
        return {"game_id": f"g{i}", "date": f"2026-03-{i:02d}", "home_id": h,
                "away_id": a, "home_goals": hg, "away_goals": ag}
    games = [game("A", "B", 2, 0, 1), game("C", "A", 0, 1, 2),
             game("B", "C", 1, 1, 3), game("A", "C", 3, 0, 4)]
    ratings, history = elo_from_games(games, abbr_of)
    assert ratings["AAA"] > ratings["BBB"] > ratings["CCC"], ratings
    assert len(history) == 4 and history[0]["home_elo_before"] == 1500.0
    print("elo_from_games: " + ", ".join(f"{k} {v:.0f}" for k, v in
                                          sorted(ratings.items(), key=lambda kv: -kv[1])))

    narrow, _ = elo_from_games([game("A", "B", 1, 0, 1)], abbr_of)
    wide, _ = elo_from_games([game("A", "B", 4, 0, 1)], abbr_of)
    gain_narrow = narrow["AAA"] - START_RATING
    gain_wide = wide["AAA"] - START_RATING
    assert gain_wide > gain_narrow, (gain_narrow, gain_wide)
    assert gain_wide < 4 * gain_narrow, "margin must be damped, not linear"
    print(f"margin damping: 1-0 worth {gain_narrow:+.1f}, 4-0 worth {gain_wide:+.1f}")

    # Table path: ordering must follow the table, and a team with no games
    # must be left unrated rather than handed 1500.
    table = [
        {"abbr": "AAA", "gp": 10, "pts": 25, "gd": 12},
        {"abbr": "BBB", "gp": 10, "pts": 14, "gd": 0},
        {"abbr": "CCC", "gp": 10, "pts": 5, "gd": -13},
        {"abbr": "DDD", "gp": 0, "pts": None, "gd": None},
    ]
    tr = elo_from_table(table)
    assert "DDD" not in tr, "a team with no games must not be invented a rating"
    assert tr["AAA"] > tr["BBB"] > tr["CCC"], tr
    spread = max(tr.values()) - min(tr.values())
    assert 100 < spread < 400, spread
    print("elo_from_table: " + ", ".join(f"{k} {v:.0f}" for k, v in
                                          sorted(tr.items(), key=lambda kv: -kv[1]))
          + f" (spread {spread:.0f})")

    assert abs(draw_rate_from_games(games) - 0.25) < 1e-12
    assert draw_rate_from_games([]) is None
    print("draw_rate_from_games: 25% on the fixture, None on an empty feed")

    print("\nall assertions passed")
