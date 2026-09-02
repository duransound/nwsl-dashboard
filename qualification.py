"""Minutes qualification -- who has played enough to appear on a rate chart.

Every player-level chart in this project needs a minutes floor. Without one,
a player who came on for 12 minutes and scored is the best finisher in the
league at 8.0 goals/96, and every scatter is dominated by noise.

Until round 22 that floor was a flat 500 minutes, which was an arbitrary
number: 500 minutes is most of a season's regular starter in March and a
bench player by October. The same constant meant something completely
different depending on when the dashboard was rebuilt, which is exactly the
thing a weekly-refreshing dashboard should not do.

What replaced it is the convention FBref uses for its per-90 leaderboards:
a player qualifies if they have averaged at least N minutes per game their
TEAM has actually played, with N = 30 by default. Three properties follow:

* It scales with the calendar. Six games in, the bar is 180 minutes; at the
  end of a 26-game season it's 780. The pool stays roughly the same *kind*
  of player all year instead of silently growing from "starters only" to
  "anyone who dressed".
* It is per team, not per league. Mid-season the NWSL schedule is uneven --
  postponements, international windows, expansion-team byes -- so a player
  on a team with 16 games played is judged against 16, not against the
  league leader's 19. A flat league-wide number quietly penalizes whoever
  has games in hand.
* 30/game is deliberately permissive, roughly a third of available minutes.
  It keeps rotation players and mid-season signings in the pool while still
  excluding cameos. Raise it toward 45 (half of all available minutes) for
  a starters-only view.

The ASA API's own `minimum_minutes` parameter is a single league-wide
number, so it cannot express a per-team rule. The pattern everywhere in
build_dashboard.py is therefore: send `api_floor` (the *lowest* per-team
threshold, so the API can't drop anyone who should qualify) and then apply
`qualifies()` client-side once each row's team is known.
"""

DEFAULT_MINUTES_PER_GAME = 30

# Multipliers worth knowing, for anyone tuning --minutes-per-game:
#   45  half of all available minutes -- nailed-on starters only
#   30  FBref's per-90 leaderboard convention (this project's default)
#   20  inclusive -- catches rotation players and late signings


def _median(values):
    ordered = sorted(values)
    n = len(ordered)
    if not n:
        return 0
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


class Qualification:
    """A minutes floor that scales with games played.

    games_by_team: {team_abbr: games played so far}. Teams missing from it
    (or the whole dict being empty, which is what happens if the API stops
    returning a games-played field) fall back to the league median, and if
    there is no median either, to `fallback_minutes` -- a degraded but
    still-working dashboard beats a traceback.

    flat_minutes: set this to opt back out into the old fixed-floor
    behavior (build_dashboard.py's --minutes flag). When set, games played
    is ignored entirely.
    """

    def __init__(self, minutes_per_game=DEFAULT_MINUTES_PER_GAME,
                 games_by_team=None, flat_minutes=None, fallback_minutes=500):
        self.minutes_per_game = int(minutes_per_game)
        self.games_by_team = {k: int(v) for k, v in (games_by_team or {}).items()
                              if v}
        self.flat_minutes = None if flat_minutes is None else int(flat_minutes)
        self.fallback_minutes = int(fallback_minutes)
        self._median_games = int(_median(list(self.games_by_team.values())))

    # ------------------------------------------------------------ thresholds

    def games_for(self, team):
        return self.games_by_team.get(team, self._median_games)

    def threshold(self, team=None):
        """Minutes a player on `team` needs to qualify."""
        if self.flat_minutes is not None:
            return self.flat_minutes
        games = self.games_for(team)
        if not games:
            # No games-played data at all -- can't scale, so hold the old
            # fixed floor rather than letting everyone through at 0.
            return self.fallback_minutes
        return max(1, games * self.minutes_per_game)

    @property
    def api_floor(self):
        """The value to send as the API's league-wide `minimum_minutes`.

        The LOWEST per-team threshold, so the server-side filter can never
        drop a player the per-team rule would have kept. Anything above that
        floor but below their own team's threshold gets removed client-side
        by qualifies().
        """
        if self.flat_minutes is not None:
            return max(1, self.flat_minutes)
        thresholds = [self.threshold(t) for t in self.games_by_team] or [self.threshold(None)]
        return max(1, min(thresholds))

    def qualifies(self, team, minutes):
        try:
            return float(minutes or 0) >= self.threshold(team)
        except (TypeError, ValueError):
            return False

    def filter(self, rows, team_key="team", minutes_key="minutes"):
        return [r for r in rows if self.qualifies(r.get(team_key), r.get(minutes_key))]

    # ----------------------------------------------------------------- prose

    @property
    def phrase(self):
        """Drop-in replacement for the old "500+ minutes played" wording.

        Read by chart_builders.qualification_phrase(), which also accepts a
        bare int so demo_dashboard.py and any older caller keep working.
        """
        if self.flat_minutes is not None:
            return f"{self.flat_minutes}+ minutes played"
        lo, hi = self.threshold_range()
        span = f"{lo}" if lo == hi else f"{lo}–{hi}"
        # Deliberately free of parentheses and em dashes: callers wrap this
        # in both, and nesting either one reads badly.
        return (f"{self.minutes_per_game}+ minutes per game their team has played, "
                f"which is {span} minutes so far this season")

    def threshold_range(self):
        if self.flat_minutes is not None:
            return self.flat_minutes, self.flat_minutes
        thresholds = [self.threshold(t) for t in self.games_by_team] or [self.threshold(None)]
        return min(thresholds), max(thresholds)

    def describe(self):
        """One line for the build log."""
        if self.flat_minutes is not None:
            return f"flat floor: {self.flat_minutes} minutes (games played ignored)"
        if not self.games_by_team:
            return (f"NO games-played data from the API -- falling back to a flat "
                    f"{self.fallback_minutes}-minute floor")
        games = sorted(self.games_by_team.values())
        lo, hi = self.threshold_range()
        return (f"{self.minutes_per_game} min per team game played; teams have "
                f"{games[0]}-{games[-1]} games in, so the bar is {lo}-{hi} minutes "
                f"(API floor {self.api_floor})")

    def __repr__(self):
        return f"<Qualification {self.describe()}>"


def from_team_rows(team_rows, minutes_per_game=DEFAULT_MINUTES_PER_GAME,
                   flat_minutes=None):
    """Build a Qualification from build_dashboard's team_rows.

    Each row is expected to carry "abbr" and "games" (games played). Rows
    without a usable games count are skipped, which is what feeds the median
    fallback above -- see get_games_played() for where "games" comes from.
    """
    games_by_team = {}
    for t in team_rows or []:
        games = t.get("games")
        if games:
            games_by_team[t.get("abbr")] = games
    return Qualification(minutes_per_game=minutes_per_game,
                         games_by_team=games_by_team, flat_minutes=flat_minutes)


# --------------------------------------------------------------- self-test

if __name__ == "__main__":
    q = Qualification(30, {"POR": 18, "KC": 20, "BOS": 16})
    assert q.threshold("POR") == 540
    assert q.threshold("KC") == 600
    assert q.threshold("BOS") == 480
    assert q.api_floor == 480, q.api_floor
    # Unknown team -> league median games (18) -> 540
    assert q.threshold("XXX") == 540
    assert q.qualifies("BOS", 480) and not q.qualifies("BOS", 479)
    # A KC player with 500 minutes clears the 480 API floor but NOT their own
    # team's 600 bar -- this is exactly the row the client-side filter exists
    # to remove.
    assert not q.qualifies("KC", 500)
    assert q.filter([{"team": "KC", "minutes": 500}, {"team": "BOS", "minutes": 500}]) == \
        [{"team": "BOS", "minutes": 500}]

    flat = Qualification(30, {"POR": 18}, flat_minutes=500)
    assert flat.threshold("POR") == 500 and flat.api_floor == 500
    assert flat.phrase == "500+ minutes played"

    # No games data anywhere -> old behavior, not a wide-open floor.
    blind = Qualification(30, {})
    assert blind.threshold("POR") == 500 and blind.api_floor == 500

    # Early season: 2 games in, the bar is 60 minutes, not 500.
    early = Qualification(30, {"POR": 2, "KC": 2})
    assert early.threshold("POR") == 60 and early.api_floor == 60

    assert "30+ minutes per game" in q.phrase and "480–600" in q.phrase
    assert "(" not in q.phrase
    print("qualification.py self-test OK")
    print(" ", q.describe())
    print(" ", q.phrase)
