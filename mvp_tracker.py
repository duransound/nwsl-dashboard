"""
MVP tracker — composite scoring layer for the NWSL xG dashboard (round 17).

Design intent (see project doc "Design Guidelines - Visual & Data Storytelling"):
the story is NOT "here is a sorted list of a number I invented." It is rank
stability: whoever leads under every reasonable weighting is the finding. A
composite index with hand-picked weights is a Lie Factor risk, so the weights
are exposed as presets and the headline is computed from agreement across them.

Depends only on plain-dict data shapes, matching chart_builders.py's convention
(parameterized on dicts, not on `requests` responses), so this is testable
against mocks with no live API access.

INPUT SHAPES
  players   : [{"id", "name", "team", "minutes", "xg", "xa", "goals", "shots"}]
              -- same shape build_dashboard.fetch_player_pool() already produces.
  ga_rows   : raw rows from /players/goals-added, i.e.
              {"player_id", "team_id", "minutes_played",
               "data": [{"action_type", "goals_added_above_avg", ...}, ...]}
              team_id may be a str or a 1-element list (both handled).
  teams     : [{"abbr", "name", "xgf", "xga", "points"?}]
              `points` comes from /teams/xgoals; optional, see TEAM_FALLBACK note.
"""

from __future__ import annotations

import math
import zlib
from statistics import mean, pstdev

import finishing_signal as _fs


def finishing_component_is_live(records):
    """True when the regressed finishing component is actually doing work.

    When the pool's estimated finishing-skill variance is zero, every
    regressed margin is zero, `_zscores` collapses the component to all-zeros,
    and the MVP order is decided entirely by goals added, creation and team
    strength -- regardless of what the weighting dropdown says. That is the
    correct behaviour, but a reader looking at a slider labelled "55%
    finishing" and seeing the order refuse to move deserves to be told why.
    The chart footnote uses this."""
    return any(r.get("finishing") for r in records)

# Goalkeepers are the only players who record Claiming actions, so their g+ total
# is not commensurable with an outfield total. Detected, not guessed at.
GK_ACTION = "Claiming"

# Weights apply to z-scores, not raw units, so they are directly comparable.
# Each preset must sum to 1.0.
PRESETS = {
    "balanced":     {"ga": 0.40, "finishing": 0.25, "creation": 0.20, "team": 0.15},
    "g_plus_heavy": {"ga": 0.70, "finishing": 0.10, "creation": 0.10, "team": 0.10},
    "goals_heavy":  {"ga": 0.20, "finishing": 0.55, "creation": 0.10, "team": 0.15},
    "team_success": {"ga": 0.30, "finishing": 0.20, "creation": 0.15, "team": 0.35},
}

PRESET_LABELS = {
    "balanced":     "Balanced",
    "g_plus_heavy": "Goals added heavy",
    "goals_heavy":  "Finishing heavy",
    "team_success": "Team success weighted",
}

PRESET_PHRASE = {
    "balanced":     "balanced weighting",
    "g_plus_heavy": "goals-added-heavy weighting",
    "goals_heavy":  "finishing-heavy weighting",
    "team_success": "team-success weighting",
}

DEFAULT_PRESET = "balanced"


# ---------------------------------------------------------------- helpers

def _first(v):
    """/players/* endpoints return team_id as either a str or a 1-element list."""
    return v[0] if isinstance(v, list) and v else v


def _minutes(row):
    """round-15 lesson: prefer minutes_played, fall back to minutes."""
    for key in ("minutes_played", "minutes"):
        if row.get(key) is not None:
            return float(row[key])
    return 0.0


def _zscores(values):
    """Population z-scores. Returns all-zeros for a degenerate spread."""
    if not values:
        return []
    mu = mean(values)
    sigma = pstdev(values)
    if sigma == 0:
        return [0.0] * len(values)
    return [(v - mu) / sigma for v in values]


def per96(value, minutes):
    """Local copy of chart_builders.per96 so this module stands alone."""
    if not minutes:
        return 0.0
    return value * 96.0 / minutes


# ---------------------------------------------------------------- ingest

def sum_goals_added(ga_rows):
    """
    Collapse the nested /players/goals-added response into one record per player.

    Returns {player_id: {"total", "by_action", "minutes", "is_gk"}}.
    Summing data[].goals_added_above_avg across action types is the documented
    way to get a player's total g+; reading a flat field off the row is the bug
    round 15 hit on the team-level version of this endpoint.
    """
    out = {}
    for row in ga_rows:
        pid = _first(row.get("player_id"))
        if pid is None:
            continue
        actions = row.get("data") or []
        by_action = {}
        for a in actions:
            name = a.get("action_type")
            if name is None:
                continue
            by_action[name] = by_action.get(name, 0.0) + float(
                a.get("goals_added_above_avg") or 0.0
            )
        rec = out.setdefault(
            pid, {"total": 0.0, "by_action": {}, "minutes": 0.0, "is_gk": False}
        )
        for name, val in by_action.items():
            rec["by_action"][name] = rec["by_action"].get(name, 0.0) + val
        rec["total"] += sum(by_action.values())
        rec["minutes"] = max(rec["minutes"], _minutes(row))
        rec["is_gk"] = rec["is_gk"] or GK_ACTION in by_action
    return out


def team_strength(teams):
    """
    {abbr: points} for the team-success component.

    Uses raw season points rather than points-per-game: every club has played
    within a match or two of every other, and /teams/xgoals does not reliably
    carry a games-played field. If a future round adds one, divide here -- it is
    the only place team success enters the score.
    """
    out = {}
    for t in teams:
        pts = t.get("points")
        if pts is None:
            # No points field -> fall back to xG differential as a proxy so the
            # component degrades instead of silently zeroing the whole preset.
            pts = float(t.get("xgf") or 0.0) - float(t.get("xga") or 0.0)
        out[t["abbr"]] = float(pts)
    return out


# ---------------------------------------------------------------- scoring

def _qualifier(minutes_floor):
    """minutes_floor is either a qualification.Qualification (live path since
    round 22 -- a per-team, games-scaled floor) or a bare number (the demo
    snapshot and any older caller). Returns a (team, minutes) -> bool test
    either way, so this module never needs to know which it got."""
    qualifies = getattr(minutes_floor, "qualifies", None)
    if callable(qualifies):
        return qualifies
    floor = float(minutes_floor or 0)
    return lambda team, minutes: float(minutes or 0) >= floor


def build_mvp_index(players, ga_rows, teams, minutes_floor=500, tau2=None):
    """
    Assemble one record per qualifying field player with all four raw components
    and their z-scores. Goalkeepers are excluded (see GK_ACTION) -- their g+ is
    Claiming-dominated and not comparable to an outfield total.

    `tau2` is the population variance of true per-shot finishing skill,
    normally passed straight through from the Goals vs. xG tab's own estimate
    (see finishing_signal.py). It matters because of what the finishing
    component USED to be: a raw, all-situations `goals - xg`.

    That was a live contradiction between two adjacent tabs. Goals vs. xG says
    -- with the league's full shot sample behind it -- that finishing over
    expectation this season is indistinguishable from chance, and regresses
    every player's margin accordingly. The MVP index then took the same
    unregressed quantity, z-scored it, and under the "goals-heavy" weighting
    made it 55% of a player's score. One tab was telling readers the number
    was noise while the tab beside it ranked the league's MVP on it.

    Now the component is the REGRESSED, non-penalty margin. When there is real
    finishing signal in the pool it survives and still separates players; when
    there isn't, every regressed value is zero, `_zscores` returns zeros for
    the degenerate spread, and the component drops out of all four weightings
    on its own -- no special-casing, and the MVP order falls back to the three
    components that do carry information. Passing tau2 in rather than
    recomputing it here is deliberate: estimated on the MVP subset it would
    come out slightly different from the finishing tab's, and the whole point
    of this change is that the two tabs agree by construction.
    """
    ga = sum_goals_added(ga_rows)
    strength = team_strength(teams)
    team_full = {t["abbr"]: t.get("name", t["abbr"]) for t in teams}

    qualifies = _qualifier(minutes_floor)

    records = []
    for p in players:
        pid = p.get("id")
        minutes = float(p.get("minutes") or 0.0)
        if not qualifies(p.get("team"), minutes):
            continue
        g = ga.get(pid)
        if g is None:
            continue          # no g+ row -> cannot score; excluded, not zeroed
        if g["is_gk"]:
            continue

        # Non-penalty wherever the caller supplies it (build_dashboard.py does;
        # the demo snapshot does not). A penalty is ~0.75 xG awarded by team
        # designation, so leaving penalties in makes the finishing component
        # partly a ranking of who takes them -- the same reason the finishing
        # chart works in npxG.
        goals = float(p.get("npgoals", p.get("goals")) or 0.0)
        xg = float(p.get("npxg", p.get("xg")) or 0.0)
        shots = float(p.get("npshots", p.get("shots")) or 0.0)
        xa = float(p.get("xa") or 0.0)

        records.append({
            "id": pid,
            "name": p.get("name") or pid,
            "team": p.get("team"),
            "minutes": minutes,
            # Accumulated, not per-96: availability is part of season-award value.
            # Per-96 rates go in the tooltip for context.
            "ga": g["total"],
            # "finishing" is filled in below, once tau2 is known -- it is the
            # regressed margin, not this raw one. Both are kept: the raw value
            # is still what a reader wants to see quoted ("11 goals from 6.9
            # expected"), it just isn't what should drive a ranking.
            "finishing_raw": goals - xg,
            "creation": xa,
            "team_pts": strength.get(p.get("team"), 0.0),
            "team_name": team_full.get(p.get("team"), p.get("team")),
            "goals": goals,
            "xg": xg,
            "shots": shots,
            "by_action": g["by_action"],
        })

    if not records:
        return []

    # Fall back to estimating from this pool only when no caller supplied a
    # figure -- keeps older callers and the demo path working, at the cost of
    # an estimate that may differ slightly from the finishing tab's.
    if tau2 is None:
        tau2 = _fs.estimate_tau2(records)
    for rec in records:
        rec["finishing"], rec["finishing_kept"] = _fs.shrink(
            rec["goals"], rec["xg"], rec["shots"], tau2)

    for field, zkey in (
        ("ga", "z_ga"),
        ("finishing", "z_finishing"),
        ("creation", "z_creation"),
        ("team_pts", "z_team"),
    ):
        for rec, z in zip(records, _zscores([r[field] for r in records])):
            rec[zkey] = z

    for rec in records:
        rec["scores"] = {
            name: (
                w["ga"] * rec["z_ga"]
                + w["finishing"] * rec["z_finishing"]
                + w["creation"] * rec["z_creation"]
                + w["team"] * rec["z_team"]
            )
            for name, w in PRESETS.items()
        }

    # Each player's rank under every weighting, across the WHOLE qualifying pool
    # (not just the charted top 15). This is what lets the per-player blurb say
    # how much a player's standing depends on the weighting choice.
    for preset in PRESETS:
        order = sorted(records, key=lambda r: -r["scores"][preset])
        for i, rec in enumerate(order):
            rec.setdefault("ranks", {})[preset] = i + 1
    return records


def rank_stability(records):
    """
    Who leads under each preset, and how concentrated that leadership is.

    Returns {"leaders": {preset: id}, "leads": {id: count}, "winner": id,
             "unanimous": bool, "names": {id: name}}.
    """
    leaders, leads, names = {}, {}, {}
    for preset in PRESETS:
        top = max(records, key=lambda r: r["scores"][preset])
        leaders[preset] = top["id"]
        leads[top["id"]] = leads.get(top["id"], 0) + 1
        names[top["id"]] = top["name"]

    # Ties on lead-count are common -- a 1/1/1/1 four-way split happened in
    # 5 of 40 simulated seasons. Falling through to dict order there would name
    # an arbitrary player as the headline MVP, so break ties on the balanced
    # score: deterministic, and defensible as the neutral weighting.
    balanced = {r["id"]: r["scores"][DEFAULT_PRESET] for r in records}
    winner = max(leads, key=lambda pid: (leads[pid], balanced.get(pid, 0.0)))

    return {
        "leaders": leaders,
        "leads": leads,
        "winner": winner,
        "unanimous": leads[winner] == len(PRESETS),
        "contested": len(set(leaders.values())),
        "names": names,
    }


def mvp_title(records, stability):
    """
    Insight-led title per Design Guidelines §2 -- the takeaway, not the metric.
    Rank stability is the actual finding, so the title states it.
    """
    n = len(PRESETS)
    winner_name = stability["names"][stability["winner"]]
    k = stability["leads"][stability["winner"]]
    rivals = [
        stability["names"][pid]
        for pid, _ in sorted(stability["leads"].items(), key=lambda kv: -kv[1])
        if pid != stability["winner"]
    ]

    # A unanimous winner is rare (~8% of simulated seasons), so the split cases
    # below are the normal output, not the exception -- each gets real prose
    # rather than falling through to one generic "no consensus" sentence.
    if stability["unanimous"]:
        return f"{winner_name} is the league MVP under every weighting we tried"

    if k == 1:
        # Every preset crowns someone different: no one leads more than once, so
        # naming a single frontrunner would overstate what the data supports.
        return (
            f"The MVP race is genuinely open — all {n} weightings crown a "
            f"different player, led by {winner_name} on the balanced view"
        )

    if len(rivals) == 1:
        rest = "the rest" if n - k == 1 else f"the other {n - k}"
        return f"{winner_name} leads {k} of {n} MVP weightings, {rivals[0]} {rest}"

    return (
        f"{winner_name} leads {k} of {n} MVP weightings, but "
        f"{len(rivals)} other players each top one"
    )


# ---------------------------------------------------------------- series rows

COMPONENT_LABELS = {
    "ga": "goals added", "finishing": "finishing",
    "creation": "creation", "team": "team success",
}


# Whimsy, but on a leash. Every variant below still describes exactly what the
# number says -- the flourish is in the phrasing, never in the claim. Design
# Guidelines' graphical-integrity rule applies to prose too: a chart may not
# exaggerate an effect visually, and a blurb may not exaggerate one verbally.
COMPONENT_FLAIR = {
    "ga": [
        "does a bit of everything, and does it well",
        "turns up all over the pitch",
        "is quietly excellent at basically everything",
    ],
    "finishing": [
        "is greedy in front of goal, in the best possible way",
        "keeps beating the odds in the box",
        "finishes like the chances owe her money",
    ],
    "creation": [
        "lives for the final ball",
        "is a chance-creation machine",
        "would rather set one up than score it",
    ],
    "team": [
        "is riding one of the league's better sides",
        "has a very good team underneath her",
    ],
}

MAGNITUDE_FLAIR = {
    "far": ["which is frankly a little unfair", "and it isn't close",
            "by a distance that raises eyebrows"],
    "well": ["comfortably clear of the pack", "and it shows"],
    "above": ["a nudge above the crowd", "just ahead of the field"],
    "par": ["right about league par", "squarely mid-table on that count"],
    "below": ["a step behind the pack"],
    "far_below": ["the one place the numbers wince"],
}

WEAK_FLAIR = ["The one wobble", "The chink in the armor", "The soft spot"]
QUIET_FLAIR = ["the quiet corner of the case", "the unremarkable bit",
               "where things go politely silent"]
NO_WEAK_FLAIR = [
    "Good luck finding a hole",
    "There's simply nothing to poke at",
    "Every box ticked",
]
FAVOR_FLAIR = ["The {phrase} flatters her most.",
               "She looks best under the {phrase}.",
               "The {phrase} is her friend."]


def _pick(options, *key_parts):
    """Deterministic variety. A stable CRC over the key means a given player
    keeps the same phrasing every rebuild -- important for a weekly cron job,
    where random wording would produce a noisy diff every single run. (Python's
    built-in hash() is salted per process and would NOT be stable here.)"""
    key = "|".join(str(k) for k in key_parts).encode("utf-8")
    return options[zlib.crc32(key) % len(options)]


def _magnitude_band(z):
    if z >= 1.5:
        return "far"
    if z >= 0.75:
        return "well"
    if z >= 0.25:
        return "above"
    if z > -0.25:
        return "par"
    if z > -0.75:
        return "below"
    return "far_below"


def _flair(z, *key_parts):
    return _pick(MAGNITUDE_FLAIR[_magnitude_band(z)], *key_parts)


def _ordinal(n):
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _component_detail(rec, key):
    """The concrete numbers behind one component, in plain language."""
    if key == "ga":
        return (f"{rec['ga']:+.1f} goals added over the season "
                f"({per96(rec['ga'], rec['minutes']):+.2f} per 96 minutes)")
    if key == "finishing":
        # Quote the raw margin -- that's the fact -- but name the regressed
        # figure as the one being scored, so a reader who checks the arithmetic
        # doesn't find a component that looks like it should be bigger.
        return (f"{rec['goals']:.0f} goals from {rec['xg']:.1f} expected, "
                f"a {rec['finishing_raw']:+.1f} raw margin worth "
                f"{rec['finishing']:+.1f} after regressing for shot volume")
    if key == "creation":
        return f"{rec['creation']:.1f} expected assists"
    return f"{rec['team_name']}'s {rec['team_pts']:.0f} points"


def _zparts(rec):
    """Each component as a z-score -- i.e. how far above or below the league
    this player sits on that measure, independent of the weighting."""
    return {"ga": rec["z_ga"], "finishing": rec["z_finishing"],
            "creation": rec["z_creation"], "team": rec["z_team"]}


def _magnitude(z):
    if z >= 1.5:
        return "far above the league average"
    if z >= 0.75:
        return "well above average"
    if z >= 0.25:
        return "above average"
    if z > -0.25:
        return "around average"
    if z > -0.75:
        return "below average"
    return "well below average"


def _weighted_parts(rec, preset):
    w = PRESETS[preset]
    return {
        "ga": w["ga"] * rec["z_ga"],
        "finishing": w["finishing"] * rec["z_finishing"],
        "creation": w["creation"] * rec["z_creation"],
        "team": w["team"] * rec["z_team"],
    }


def player_headline(rec, preset, stability=None, max_swing=None):
    """One insight-stating sentence about this player under this weighting.

    Same convention as the panel-level title (Design Guidelines §2) -- state the
    finding, not the label -- just with more voice. Which finding applies is
    driven entirely by the data: a unanimous leader gets the stability claim,
    otherwise the finding is how much (or how little) this player's standing
    depends on the weighting, which is the question the whole tab is about.
    """
    name = rec["name"]
    ranks = rec["ranks"]
    best, worst = min(ranks.values()), max(ranks.values())
    swing = worst - best

    if stability and stability["winner"] == rec["id"] and stability["unanimous"]:
        return f"{name} is the MVP no matter how you slice the numbers"
    if ranks[preset] == 1:
        return _pick([
            f"{name} runs away with the {PRESET_PHRASE[preset]}",
            f"Weight it this way and {name} takes the crown",
        ], rec["id"], preset)
    if best == worst:
        return f"{name} will not budge from {_ordinal(best)}, however you weigh it"
    if swing >= 5:
        # The superlative is only offered when this player actually holds the
        # widest swing in the pool -- otherwise "biggest" would be a claim the
        # numbers don't support, picked at random by the variant hash.
        options = [
            f"Move the weights and {name} moves {swing} places with them",
            f"{name} is a genuine weathervane — {swing} places, depending on "
            f"what you value",
        ]
        if max_swing is not None and swing == max_swing:
            options.insert(0, f"{name} is this ballot's biggest mood swing — "
                              f"{swing} places, depending on what you value")
        return _pick(options, rec["id"], preset)
    return (f"{name} never strays outside {_ordinal(best)} to "
            f"{_ordinal(worst)}, whichever way you lean")


def player_story(rec, preset):
    """Two or three sentences with some life in them: what this player is
    unusually good at, where the case thins out, and which weighting suits her.

    Strength is judged on z-scores, not weighted contribution -- the
    heaviest-weighted term (goals added) would otherwise "carry" nearly every
    player and all fifteen blurbs would open the same way. Phrasing varies by a
    stable hash of the player id so no two read identically, while staying fixed
    across rebuilds.
    """
    z = _zparts(rec)
    top = max(z, key=lambda k: z[k])
    bottom = min(z, key=lambda k: z[k])
    pid = rec["id"]

    out = [
        f"{rec['name']} {_pick(COMPONENT_FLAIR[top], pid, 'top')}: "
        f"{_component_detail(rec, top)} — {_flair(z[top], pid, 'topmag')}."
    ]

    if bottom != top:
        zb = z[bottom]
        label = COMPONENT_LABELS[bottom]
        detail = _component_detail(rec, bottom)
        if zb < -0.25:
            out.append(f"{_pick(WEAK_FLAIR, pid, 'weak')}: {label} — "
                       f"{detail}, {_flair(zb, pid, 'weakmag')}.")
        elif zb < 0.25:
            out.append(f"{label.capitalize()} is "
                       f"{_pick(QUIET_FLAIR, pid, 'quiet')}: {detail}.")
        else:
            # Everything above average. Calling the lowest of four strong
            # numbers a "weakness" would contradict the magnitude phrase in the
            # same sentence and undersell a genuinely complete profile.
            out.append(f"{_pick(NO_WEAK_FLAIR, pid, 'nohole')} — even "
                       f"{label}, the lowest of the four, lands "
                       f"{_magnitude(zb)} ({detail}).")

    ranks = rec["ranks"]
    if len(set(ranks.values())) > 1:
        best_preset = min(ranks, key=lambda k: ranks[k])
        out.append(_pick(FAVOR_FLAIR, pid, 'favor').format(
            phrase=PRESET_PHRASE[best_preset]))
    return " ".join(out)


def series_for_preset(records, preset, top_n=None, stability=None):
    """Rows in dashboard_template.drawDivergingBar's exact shape:
    {"label", "value", "highlight", "extra"} plus two narration fields,
    "headline" and "story", which drawPresetCompare swaps into the panel's own
    <h2>/blurb when a reader clicks that bar. The template computes the bar
    annotation itself from d.value, so no annotation field is supplied here."""
    ranked = sorted(records, key=lambda r: -r["scores"][preset])
    if top_n:
        ranked = ranked[:top_n]
    lead_id = ranked[0]["id"] if ranked else None
    # Widest rank swing anywhere in the qualifying pool, so a "biggest" claim in
    # a headline can be checked rather than asserted.
    max_swing = max((max(r["ranks"].values()) - min(r["ranks"].values())
                     for r in records), default=0)
    rows = []
    for rec in ranked:
        rows.append({
            "label": rec["name"],
            "value": round(rec["scores"][preset], 2),
            "highlight": rec["id"] == lead_id,
            "extra": (
                f"{rec['team']} &middot; {int(rec['minutes'])} min &middot; "
                f"{rec['ga']:+.2f} g+ &middot; {rec['goals']:.0f}G vs "
                f"{rec['xg']:.1f} xG ({rec['finishing']:+.1f}) &middot; "
                f"{rec['creation']:.1f} xA<br>Driven by "
                f"{_contribution_share(rec, preset)}"
            ),
            "headline": player_headline(rec, preset, stability, max_swing),
            "story": player_story(rec, preset),
        })
    return rows


def _contribution_share(rec, preset):
    """The component this player stands out most on -- same z-score basis as
    player_story, so the tooltip and the blurb never disagree about which part
    of a player's game is carrying them."""
    z = _zparts(rec)
    top = max(z, key=lambda k: z[k])
    if z[top] <= 0:
        return "no component above league average"
    return f"{COMPONENT_LABELS[top]} ({_magnitude(z[top])})"


# ---------------------------------------------------------------- self-test

def _ga_row(pid, minutes, **actions):
    """Build a /players/goals-added row in the confirmed nested shape."""
    return {"player_id": [pid], "team_id": ["x"], "minutes_played": minutes,
            "data": [{"action_type": k, "goals_added_above_avg": v}
                     for k, v in actions.items()]}


def _mock():
    """Small hand-built pool exercising every branch: a unanimous-ish leader, a
    finishing specialist, a creator, a goalkeeper, and a below-floor player."""
    players = [
        {"id": "p1", "name": "Barbra Banda",   "team": "ORL", "minutes": 1580,
         "xg": 11.2, "xa": 4.1, "goals": 17, "shots": 74},
        {"id": "p2", "name": "Temwa Chawinga", "team": "KC",  "minutes": 1610,
         "xg": 13.9, "xa": 3.2, "goals": 16, "shots": 88},
        {"id": "p3", "name": "Debinha",        "team": "KC",  "minutes": 1440,
         "xg": 5.1,  "xa": 9.4, "goals": 6,  "shots": 41},
        {"id": "p4", "name": "Sophia Wilson",  "team": "POR", "minutes": 1290,
         "xg": 9.8,  "xa": 3.0, "goals": 9,  "shots": 80},
        {"id": "gk1", "name": "Katie Lund",    "team": "LOU", "minutes": 1620,
         "xg": 0.0,  "xa": 0.0, "goals": 0,  "shots": 0},
        {"id": "p5", "name": "Bench Player",   "team": "BAY", "minutes": 210,
         "xg": 1.1,  "xa": 0.4, "goals": 2,  "shots": 9},
    ]

    ga_rows = [
        _ga_row("p1", 1580, Shooting=4.1, Receiving=2.2, Dribbling=1.4, Passing=0.6,
           Interrupting=-0.2, Fouling=0.1),
        _ga_row("p2", 1610, Shooting=3.0, Receiving=1.9, Dribbling=2.1, Passing=0.2,
           Interrupting=0.1, Fouling=-0.1),
        _ga_row("p3", 1440, Shooting=0.9, Receiving=1.6, Dribbling=0.8, Passing=3.4,
           Interrupting=0.3, Fouling=0.0),
        _ga_row("p4", 1290, Shooting=1.2, Receiving=1.1, Dribbling=0.5, Passing=0.1,
           Interrupting=0.0, Fouling=0.0),
        _ga_row("gk1", 1620, Claiming=1.8, Passing=0.4, Fouling=0.0),
        _ga_row("p5", 210, Shooting=0.3, Passing=0.1),
    ]
    teams = [
        {"abbr": "ORL", "name": "Orlando Pride",       "xgf": 38.1, "xga": 24.0, "points": 55},
        {"abbr": "KC",  "name": "Kansas City Current", "xgf": 41.2, "xga": 26.4, "points": 51},
        {"abbr": "POR", "name": "Portland Thorns FC",  "xgf": 33.0, "xga": 30.2, "points": 38},
        {"abbr": "LOU", "name": "Racing Louisville FC","xgf": 25.4, "xga": 33.9, "points": 27},
        {"abbr": "BAY", "name": "Bay FC",              "xgf": 24.1, "xga": 35.0, "points": 24},
    ]
    return players, ga_rows, teams


if __name__ == "__main__":
    players, ga_rows, teams = _mock()

    idx = build_mvp_index(players, ga_rows, teams, minutes_floor=500)
    print(f"qualified: {len(idx)}  ->  {[r['name'] for r in idx]}")
    assert all(r["id"] != "gk1" for r in idx), "goalkeeper leaked into the pool"
    assert all(r["id"] != "p5" for r in idx), "below-floor player leaked in"

    st = rank_stability(idx)
    print("leaders by preset:")
    for p, pid in st["leaders"].items():
        print(f"  {PRESET_LABELS[p]:<24} {st['names'][pid]}")
    print(f"unanimous: {st['unanimous']}")

    print("\ntitle:", mvp_title(idx, st))

    rows = series_for_preset(idx, DEFAULT_PRESET, top_n=15)
    print("\nranking (balanced):")
    for row in rows:
        flag = "*" if row["highlight"] else " "
        print(f" {flag} {row['label']:<18} {row['value']:+.2f}")

    hi = [r for r in rows if r["highlight"]]
    assert len(hi) == 1, f"expected exactly one highlight, got {len(hi)}"
    assert hi[0] is rows[0], "the emphasized row must be the top-ranked one"
    # The template computes the bar annotation from d.value, so the series must
    # NOT supply one -- an annotation key here would be silently ignored.
    assert all("annotation" not in r for r in rows), \
        "series rows must not carry an annotation field"
    assert all(set(r) == {"label", "value", "highlight", "extra",
                          "headline", "story"} for r in rows), \
        "series rows must match drawPresetCompare's contract"
    # Every row must be able to narrate itself, or clicking a bar would blank
    # the panel headline.
    assert all(r["headline"] and r["story"] for r in rows), \
        "every row needs a headline and story"
    assert all("weighted weighting" not in r["story"] and
               "weighted weighting" not in r["headline"] for r in rows), \
        "preset names must read as prose, not doubled words"
    assert len({r["story"] for r in rows}) > len(rows) // 2, \
        "stories are too uniform to be worth showing"
    # A story may say "Good luck finding a hole -- even X ... above average";
    # that is correct. What it must never do is assert a weakness exists and then
    # describe that same component as above average in the same sentence.
    all_flair = [f for group in MAGNITUDE_FLAIR.values() for f in group]
    for r in rows:
        used = [f for f in all_flair if f in r["story"]]
        assert len(used) == len(set(used)), \
            f"story repeats a flair phrase: {r['label']}"
    swings = {rr["name"]: max(rr["ranks"].values()) - min(rr["ranks"].values())
              for rr in idx}
    widest = max(swings.values())
    for r in rows:
        if "biggest mood swing" in r["headline"]:
            assert swings[r["label"]] == widest, \
                f"unsupported superlative for {r['label']}"
    for r in rows:
        for opener in WEAK_FLAIR:
            if opener in r["story"]:
                claim = r["story"].split(opener)[1].split(".")[0]
                assert "above" not in claim and "unfair" not in claim, \
                    f"story calls a strength a weakness: {r['label']} -> {claim}"

    print("\nper-preset top 3:")
    for key in PRESETS:
        pr = series_for_preset(idx, key, top_n=15)
        print(f"  {PRESET_LABELS[key]:<24} "
              + ", ".join(f"{r['label']} ({r['value']:+.2f})" for r in pr[:3]))
        assert sum(1 for r in pr if r["highlight"]) == 1

    # Degenerate-spread guard: a pool where every player is identical must not
    # divide by zero, and must still emit exactly one highlight.
    flat_players = [dict(players[0], id=f"f{i}", name=f"Flat {i}") for i in range(4)]
    flat_ga = [_ga_row(f"f{i}", 1580, Shooting=1.0, Passing=1.0) for i in range(4)]
    flat_idx = build_mvp_index(flat_players, flat_ga, teams, minutes_floor=500)
    flat = series_for_preset(flat_idx, DEFAULT_PRESET)
    assert sum(1 for r in flat if r["highlight"]) == 1
    assert all(math.isfinite(r["value"]) for r in flat)
    print("\ndegenerate-spread case: ok (no NaN, one highlight)")

    print("\nall assertions passed")
