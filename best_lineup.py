"""
Best Possible Lineup -- the strongest available XI for a team in a chosen
formation, graded against replacement level.

WHAT THIS IS BUILT FROM, AND WHY IT REUSES THE POSITION GAPS FETCH

The Position Gaps tab already pulls goals added ABOVE REPLACEMENT for every
player at each of ASA's eight positions (one call per position, plus the
goalkeeper endpoint). That is exactly the input an XI-picker needs, and it is
the reason this tab costs zero extra API calls: build_dashboard.py hands the
same rows_by_position dict to both.

Above replacement rather than above average is what makes the slots
comparable. A center back and a striker post very different raw g+; grading
each against replacement level AT THEIR OWN POSITION is what lets "the best
available player here" mean the same thing in both slots.

Ratings are per 96 minutes, the normalisation used on every other rate figure
on this dashboard, so a starter is not simply beaten by whoever played most.

THE FORMATION -> POSITION MAPPING

ASA's vocabulary has seven outfield buckets (CB, FB, DM, CM, AM, W, ST) plus
GK, and a formation's slots do not map one-to-one onto them. Every slot below
declares which buckets can fill it, and the mapping is deliberately narrow --
a slot that accepts everything would always be filled, and always by whoever
happened to have the highest number, which is not a lineup:

    GK      GK                 the goalkeeper endpoint only
    CB      CB
    FB      FB
    WB      FB, W              a wing-back is played by both in a back three
    DM      DM, CM             the holding pair in a 4-2-3-1
    MID     DM, CM, AM         a generic central midfield slot
    AM      AM, CM             the number ten, or a midfielder pushed up
    W       W, AM              a winger, or a ten moved wide
    ST      ST                 strikers only; a winger is not a center forward

WHAT IT REFUSES TO DO

A slot with no qualifying player renders as "No qualifying player" rather
than reaching down to a bucket it does not belong to, or to a player below the
minutes floor. A team that has fielded one full back for 200 minutes has not
told us who their best full back is, and inventing an answer there would be
exactly the kind of fabricated finding the rest of this dashboard is careful
to avoid.

ASSIGNMENT

Most-constrained-first greedy: slots that accept the fewest buckets are filled
before slots that accept more, each taking the highest-rated unassigned
qualifying player. On an 11-slot problem this is stable, explainable, and
produces the same XI every run given the same data -- which matters, because
the page is rebuilt weekly and a lineup that reshuffled for no reason would
read as a bug. A player can be considered at every position they actually
logged minutes at, but is assigned at most once.
"""

from __future__ import annotations

from position_gaps import _above_replacement, _first, _minutes

# Minutes a player must have logged AT A POSITION before being eligible for a
# slot there. Three full matches. Below it the per-96 rate is a rate over
# almost nothing, and a 90-minute cameo would regularly out-rank a season-long
# starter purely on sample noise.
MIN_SLOT_MINUTES = 270


def _slot(sid, label, eligible):
    return {"id": sid, "label": label, "eligible": list(eligible)}


# Each formation is a list of LINES, defensive-most first. The renderer lays
# lines out from the back of the pitch forward and spaces each line's slots
# evenly, so the shape reads as the formation's name without needing a
# hand-placed coordinate for every slot.
FORMATIONS = [
    {
        "key": "4-3-3", "label": "4-3-3",
        "lines": [
            [_slot("gk", "GK", ["GK"])],
            [_slot("lb", "LB", ["FB"]), _slot("lcb", "CB", ["CB"]),
             _slot("rcb", "CB", ["CB"]), _slot("rb", "RB", ["FB"])],
            [_slot("lcm", "CM", ["DM", "CM", "AM"]), _slot("dm", "CM", ["DM", "CM", "AM"]),
             _slot("rcm", "CM", ["DM", "CM", "AM"])],
            [_slot("lw", "LW", ["W", "AM"]), _slot("st", "ST", ["ST"]),
             _slot("rw", "RW", ["W", "AM"])],
        ],
    },
    {
        "key": "4-4-2", "label": "4-4-2",
        "lines": [
            [_slot("gk", "GK", ["GK"])],
            [_slot("lb", "LB", ["FB"]), _slot("lcb", "CB", ["CB"]),
             _slot("rcb", "CB", ["CB"]), _slot("rb", "RB", ["FB"])],
            [_slot("lm", "LM", ["W", "AM"]), _slot("lcm", "CM", ["DM", "CM", "AM"]),
             _slot("rcm", "CM", ["DM", "CM", "AM"]), _slot("rm", "RM", ["W", "AM"])],
            [_slot("lst", "ST", ["ST"]), _slot("rst", "ST", ["ST"])],
        ],
    },
    {
        "key": "4-2-3-1", "label": "4-2-3-1",
        "lines": [
            [_slot("gk", "GK", ["GK"])],
            [_slot("lb", "LB", ["FB"]), _slot("lcb", "CB", ["CB"]),
             _slot("rcb", "CB", ["CB"]), _slot("rb", "RB", ["FB"])],
            [_slot("ldm", "DM", ["DM", "CM"]), _slot("rdm", "DM", ["DM", "CM"])],
            [_slot("lw", "LW", ["W", "AM"]), _slot("am", "AM", ["AM", "CM"]),
             _slot("rw", "RW", ["W", "AM"])],
            [_slot("st", "ST", ["ST"])],
        ],
    },
    {
        "key": "3-5-2", "label": "3-5-2",
        "lines": [
            [_slot("gk", "GK", ["GK"])],
            [_slot("lcb", "CB", ["CB"]), _slot("ccb", "CB", ["CB"]),
             _slot("rcb", "CB", ["CB"])],
            [_slot("lwb", "LWB", ["FB", "W"]), _slot("lcm", "CM", ["DM", "CM", "AM"]),
             _slot("cm", "CM", ["DM", "CM", "AM"]), _slot("rcm", "CM", ["DM", "CM", "AM"]),
             _slot("rwb", "RWB", ["FB", "W"])],
            [_slot("lst", "ST", ["ST"]), _slot("rst", "ST", ["ST"])],
        ],
    },
]

FORMATION_KEYS = [f["key"] for f in FORMATIONS]


def candidates_by_team(rows_by_position, player_names=None,
                       min_minutes=MIN_SLOT_MINUTES):
    """{abbr: [{player_id, name, position, minutes, rating}]}.

    rows_by_position is exactly what build_dashboard.fetch_position_gaps
    returns: {position: [goals-added rows tagged with team_abbr]}. A row with
    no usable above-replacement value is skipped rather than scored as zero --
    the same distinction position_gaps.build_cells makes, and for the same
    reason: missing is not the same claim as average.
    """
    player_names = player_names or {}
    out = {}
    for position, rows in (rows_by_position or {}).items():
        for row in rows or []:
            abbr = _first(row.get("team_abbr") or row.get("team_id"))
            if abbr is None:
                continue
            ar = _above_replacement(row)
            minutes = _minutes(row)
            if ar is None or minutes < min_minutes or minutes <= 0:
                continue
            pid = _first(row.get("player_id"))
            out.setdefault(abbr, []).append({
                "player_id": pid,
                "name": player_names.get(pid, pid),
                "position": position,
                "minutes": int(round(minutes)),
                "rating": ar / minutes * 96.0,
            })
    return out


def pick_lineup(candidates, formation):
    """Fill one formation from one team's candidate list.

    Returns {"slots": {slot_id: pick or None}, "filled": int, "total": int,
    "strength": float or None}. `strength` is the mean rating of the filled
    slots -- a mean rather than a sum so a team with two empty slots is not
    flattered by having fewer negative contributors, and None when nothing
    was fillable.
    """
    slots = [s for line in formation["lines"] for s in line]
    # Most constrained first. The tie-break on the slot's own index keeps the
    # order fixed, so the same data always produces the same XI.
    order = sorted(range(len(slots)), key=lambda i: (len(slots[i]["eligible"]), i))

    used = set()
    picks = {}
    for i in order:
        slot = slots[i]
        pool = [c for c in candidates
                if c["position"] in slot["eligible"] and c["player_id"] not in used]
        if not pool:
            picks[slot["id"]] = None
            continue
        # Highest rating; name breaks a tie so the result never depends on the
        # order rows happened to arrive in.
        best = max(pool, key=lambda c: (c["rating"], str(c["name"])))
        used.add(best["player_id"])
        picks[slot["id"]] = {
            "name": best["name"], "position": best["position"],
            "minutes": best["minutes"], "rating": round(best["rating"], 3),
        }

    filled = [p for p in picks.values() if p]
    return {
        "slots": picks, "filled": len(filled), "total": len(slots),
        "strength": (round(sum(p["rating"] for p in filled) / len(filled), 3)
                     if filled else None),
    }


def build_all(rows_by_position, player_names=None, min_minutes=MIN_SLOT_MINUTES):
    """{abbr: {formation_key: pick_lineup(...)}} for every team that has any
    qualifying player at all."""
    cands = candidates_by_team(rows_by_position, player_names, min_minutes)
    return {abbr: {f["key"]: pick_lineup(rows, f) for f in FORMATIONS}
            for abbr, rows in cands.items()}


def strongest(lineups, require_complete=True):
    """(abbr, formation_key, lineup) for the league's best XI, or None.

    By default only fully filled XIs are eligible -- a team with three empty
    slots can post a high mean and would otherwise win the headline on a
    technicality. With require_complete=False the field is instead every
    lineup tied for the most slots filled, which is the honest fallback when
    nothing in the league is complete: the comparison is still like-for-like,
    it just isn't eleven.
    """
    pool = [(abbr, key, lu)
            for abbr, by_formation in lineups.items()
            for key, lu in by_formation.items()
            if lu["strength"] is not None]
    if not pool:
        return None
    if require_complete:
        pool = [p for p in pool if p[2]["filled"] == p[2]["total"]]
    else:
        most = max(p[2]["filled"] for p in pool)
        pool = [p for p in pool if p[2]["filled"] == most]
    if not pool:
        return None
    # Name breaks a tie so the headline is stable across rebuilds.
    return max(pool, key=lambda p: (p[2]["strength"], p[0], p[1]))


# ------------------------------------------------------------------ self-test

if __name__ == "__main__":
    def row(pid, abbr, minutes, ar):
        return {"player_id": pid, "team_abbr": [abbr], "minutes_played": minutes,
                "goals_added_above_replacement": ar}

    names = {}
    rows_by_position = {}
    # A deep team (DEEP) with three real options in every bucket, and a thin
    # team (THIN) that has nobody at all at striker.
    for position, count in [("GK", 2), ("CB", 3), ("FB", 3), ("DM", 2),
                            ("CM", 3), ("AM", 2), ("W", 3), ("ST", 2)]:
        rows = []
        for i in range(count):
            pid = f"DEEP{position}{i}"
            names[pid] = f"Deep {position}{i}"
            rows.append(row(pid, "DEEP", 900 + i * 10, 1.0 + i))
        if position != "ST":
            for i in range(2):
                pid = f"THIN{position}{i}"
                names[pid] = f"Thin {position}{i}"
                rows.append(row(pid, "THIN", 800, 0.5))
        rows_by_position[position] = rows

    # A cameo: highest rate in the league, far below the minutes floor. It must
    # never take a slot from a season-long starter.
    names["CAMEO"] = "Cameo Striker"
    rows_by_position["ST"].append(row("CAMEO", "THIN", 120, 40.0))
    # A row with no above-replacement value at all: skipped, not scored as 0.
    rows_by_position["CB"].append({"player_id": "BROKEN", "team_abbr": ["THIN"],
                                   "minutes_played": 1500})

    lineups = build_all(rows_by_position, names)

    deep = lineups["DEEP"]["4-3-3"]
    assert deep["filled"] == 11, deep
    assert deep["slots"]["gk"]["position"] == "GK"
    assert deep["slots"]["st"]["position"] == "ST"
    print(f"DEEP 4-3-3: {deep['filled']}/11 filled, mean rating {deep['strength']:+.3f}")

    # Nobody is picked twice.
    picked = [p["name"] for p in deep["slots"].values() if p]
    assert len(picked) == len(set(picked)), picked
    print("no duplicate selections across 11 slots")

    thin = lineups["THIN"]["4-4-2"]
    assert thin["slots"]["lst"] is None and thin["slots"]["rst"] is None, thin["slots"]
    assert all(p["name"] != "Cameo Striker" for p in thin["slots"].values() if p), \
        "a 120-minute cameo must not fill a slot"
    print(f"THIN 4-4-2: both striker slots honestly empty "
          f"({thin['filled']}/11 filled)")

    assert all(p["name"] != "BROKEN" for p in
               lineups["THIN"]["4-3-3"]["slots"].values() if p)
    print("missing-field guard: row with no above-replacement value skipped")

    # 3-5-2 wing-backs may be filled by a winger when no full back is left.
    wb_only = {"FB": [], "W": [row("W1", "WB", 900, 2.0), row("W2", "WB", 900, 1.5)]}
    wb_names = {"W1": "Wide One", "W2": "Wide Two"}
    wb = build_all({**{p: [] for p in rows_by_position}, **wb_only}, wb_names)["WB"]["3-5-2"]
    assert wb["slots"]["lwb"] and wb["slots"]["rwb"], wb["slots"]
    assert wb["slots"]["lwb"]["position"] == "W"
    print("3-5-2 wing-backs: fillable by wingers when no full back qualifies")

    # Determinism: identical input, identical XI, every time.
    again = build_all(rows_by_position, names)
    assert again == lineups, "the same data must produce the same lineup"
    print("determinism: two builds produce an identical XI")

    best = strongest(lineups)
    assert best and best[0] == "DEEP", best
    print(f"league's strongest complete XI: {best[0]} in {best[1]} "
          f"({best[2]['strength']:+.3f} g+/96 mean)")

    print("\nall assertions passed")
