"""
Position gaps — which position is each team weakest at, measured against
replacement level rather than league average.

Why replacement level: league average answers "is this group good?", which is
not the question. A team can sit below average at center back and still have no
reason to act. Below *replacement* means a freely available player would do
better -- that's a real hole, and it's the question "where could they improve"
actually asks. ASA exposes this via `above_replacement=true` on the goals-added
endpoints.

Why ASA's native 8 positions (GK, CB, FB, DM, CM, AM, W, ST): collapsing to
GK/DEF/MID/ATT would average a team's center backs together with its full backs
and hide the thing worth knowing. It also removes the need to hand-pick which
g+ action type measures each group -- at this granularity, comparing a player to
replacement level AT THEIR OWN POSITION already handles the fact that attackers
post higher raw g+ than defenders.

KEY ASSUMPTION, not yet confirmed against the live API: that g+ above
replacement is computed per position (build_dashboard.py's own Goals Added
footnote says ASA's g+ is "relative to other players in the same general
position", so this is likely but unverified). If it turns out NOT to be
position-relative, raw cells would be biased by position and
`normalize_across_positions()` below converts each cell to a within-position
z-score instead, restoring comparability. Both paths are implemented; the raw
path is the default.
"""

from __future__ import annotations

from statistics import mean, pstdev

# ASA's own vocabulary, defensive-most to attacking-most. Order matters: it's
# the column order of the grid, so the chart reads like a pitch.
POSITIONS = ["GK", "CB", "FB", "DM", "CM", "AM", "W", "ST"]

POSITION_NAMES = {
    "GK": "goalkeeper", "CB": "center back", "FB": "full back",
    "DM": "defensive midfield", "CM": "central midfield",
    "AM": "attacking midfield", "W": "winger", "ST": "striker",
}

# Blocks used only for the personnel-vs-results cross-check below.
DEF_BLOCK = ["GK", "CB", "FB"]
ATT_BLOCK = ["AM", "W", "ST"]

# A cell needs this many combined minutes before it's allowed to say anything.
# Below it the cell is "no data" -- a team that has fielded one full back for
# 200 minutes has not told us their full backs are bad, and rendering that as a
# red square would be inventing a finding.
MIN_CELL_MINUTES = 400

# A player needs this many minutes at a position before being called a regular
# there -- used for the worst-regular figure, so a 90-minute cameo can't be
# reported as a team's problem at that position.
REGULAR_MINUTES = 300

# How far personnel rank and results rank must diverge (out of 16) before it's
# called a disagreement rather than noise.
DISAGREEMENT_GAP = 6


def _first(v):
    return v[0] if isinstance(v, list) and v else v


def _minutes(row):
    for key in ("minutes_played", "minutes"):
        if row.get(key) is not None:
            return float(row[key])
    return 0.0


def _above_replacement(row):
    """Total g+ above replacement off one row.

    With above_replacement=true the goals-added endpoints return an aggregated
    value rather than the per-action `data` list, but the exact field name is
    unconfirmed -- so try the plausible names, then fall back to summing a
    nested `data` list if the flag was ignored and the disaggregated shape came
    back instead. Returns None when nothing usable is present, so a caller can
    tell "zero" apart from "missing".
    """
    for key in ("goals_added_above_replacement", "goals_added_above_avg",
                "goals_added_raw", "goals_added"):
        v = row.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    data = row.get("data")
    if isinstance(data, list) and data:
        total = 0.0
        found = False
        for action in data:
            for key in ("goals_added_above_replacement", "goals_added_above_avg"):
                if isinstance(action.get(key), (int, float)):
                    total += float(action[key])
                    found = True
                    break
        if found:
            return total
    return None


def build_cells(rows_by_position, teams, min_cell_minutes=MIN_CELL_MINUTES):
    """rows_by_position: {position: [raw goals-added rows]} -- one entry per
    ASA position, each the response of a general_position-filtered call.
    teams: [{"abbr", "name", "xgf", "xga", ...}]

    Returns {(abbr, position): cell}, where a cell is
    {"value", "minutes", "players", "enough"}. `value` is the minutes-weighted
    g+ above replacement per 96 minutes -- i.e. the quality of what the team
    actually fielded there, not a total, so a team isn't penalised for depth.
    Cells below the minutes floor are kept but flagged enough=False with
    value=None.
    """
    abbr_of = {}
    for t in teams:
        abbr_of[t["abbr"]] = t["abbr"]

    acc = {}
    for position, rows in rows_by_position.items():
        for row in rows or []:
            abbr = _first(row.get("team_abbr") or row.get("team_id"))
            if abbr is None:
                continue
            ar = _above_replacement(row)
            minutes = _minutes(row)
            if ar is None or minutes <= 0:
                continue
            key = (abbr, position)
            slot = acc.setdefault(key, {"ga": 0.0, "minutes": 0.0,
                                       "players": 0, "each": []})
            slot["ga"] += ar
            slot["minutes"] += minutes
            slot["players"] += 1
            slot["each"].append({"pid": _first(row.get("player_id")),
                                 "minutes": minutes,
                                 "per96": ar / minutes * 96.0})

    cells = {}
    for abbr in abbr_of:
        for position in POSITIONS:
            slot = acc.get((abbr, position))
            if not slot or slot["minutes"] < min_cell_minutes:
                cells[(abbr, position)] = {
                    "value": None, "minutes": slot["minutes"] if slot else 0.0,
                    "players": slot["players"] if slot else 0, "enough": False,
                }
            else:
                # The minutes-weighted mean is the quality of what the team
                # actually fielded -- the right headline number. But it hides a
                # weak regular behind strong teammates at the same position, so
                # the worst individual regular is carried alongside it for the
                # tooltip. Without this, a team with one excellent and one poor
                # center back reads as merely "fine".
                regulars = [e for e in slot["each"]
                            if e["minutes"] >= REGULAR_MINUTES]
                worst = min(regulars, key=lambda e: e["per96"]) if regulars else None
                cells[(abbr, position)] = {
                    "value": slot["ga"] / slot["minutes"] * 96.0,
                    "minutes": slot["minutes"], "players": slot["players"],
                    "enough": True,
                    "spread": (max(e["per96"] for e in slot["each"])
                               - min(e["per96"] for e in slot["each"])),
                    "worst": worst,
                }
    return cells


def normalize_across_positions(cells):
    """Fallback for the unverified assumption at the top of this file.

    Converts each cell to a z-score within its own position column, so columns
    are comparable even if ASA's above-replacement values are NOT already
    position-relative. Returns a new cells dict; callers can swap this in
    without touching anything downstream.
    """
    out = {k: dict(v) for k, v in cells.items()}
    for position in POSITIONS:
        vals = [v["value"] for (a, p), v in cells.items()
                if p == position and v["enough"]]
        if len(vals) < 2:
            continue
        mu, sigma = mean(vals), pstdev(vals)
        for (a, p), v in out.items():
            if p == position and v["enough"]:
                v["value"] = 0.0 if sigma == 0 else (v["value"] - mu) / sigma
    return out


def weakest_for_team(cells, abbr):
    """The team's most-below-replacement position with enough data, or None."""
    scored = [(p, cells[(abbr, p)]) for p in POSITIONS
              if cells.get((abbr, p), {}).get("enough")]
    if not scored:
        return None
    position, cell = min(scored, key=lambda pc: pc[1]["value"])
    return {"position": position, **cell}


def league_worst_cell(cells, teams):
    """The single widest hole anywhere in the league -- the tab's headline."""
    name_of = {t["abbr"]: t["name"] for t in teams}
    scored = [(a, p, c) for (a, p), c in cells.items() if c["enough"]]
    if not scored:
        return None
    abbr, position, cell = min(scored, key=lambda apc: apc[2]["value"])
    return {"abbr": abbr, "name": name_of.get(abbr, abbr),
            "position": position, **cell}


def _block_score(cells, abbr, block):
    """Minutes-weighted per-96 across a group of positions, ignoring thin cells."""
    num = den = 0.0
    for position in block:
        cell = cells.get((abbr, position))
        if cell and cell["enough"]:
            num += cell["value"] * cell["minutes"]
            den += cell["minutes"]
    return (num / den) if den else None


def _rank(values, reverse):
    """1 = best. `values` is {abbr: score}; None scores are unranked."""
    ranked = sorted([kv for kv in values.items() if kv[1] is not None],
                    key=lambda kv: kv[1], reverse=reverse)
    return {abbr: i + 1 for i, (abbr, _) in enumerate(ranked)}


def find_disagreements(cells, teams, gap=DISAGREEMENT_GAP):
    """Where the players look better (or worse) than the team's actual results.

    This is the tab's real story. If a defense's personnel rank near the top of
    the league on g+ above replacement but the team still concedes a lot of xG,
    the players aren't the problem -- the shape in front of them is. The reverse
    (weak personnel, strong results) is a system flattering its parts.

    Returns [{abbr, name, side, personnel_rank, results_rank, gap, verdict}],
    widest gap first.
    """
    name_of = {t["abbr"]: t["name"] for t in teams}
    xgf = {t["abbr"]: t.get("xgf") for t in teams}
    xga = {t["abbr"]: t.get("xga") for t in teams}

    out = []
    for side, block, outcome, outcome_reverse, label in (
        ("defense", DEF_BLOCK, xga, False, "concede"),
        ("attack", ATT_BLOCK, xgf, True, "create"),
    ):
        personnel = {t["abbr"]: _block_score(cells, t["abbr"], block) for t in teams}
        p_rank = _rank(personnel, reverse=True)      # higher g+ = better = rank 1
        o_rank = _rank(outcome, reverse=outcome_reverse)
        for abbr in p_rank:
            if abbr not in o_rank:
                continue
            diff = o_rank[abbr] - p_rank[abbr]
            if abs(diff) < gap:
                continue
            # Single clause, no internal dash: callers embed this after an
            # em-dash of their own, and nesting two reads badly.
            if diff > 0:
                culprit = ("the shape in front of them"
                           if side == "defense" else "the supply behind them")
                verdict = (f"the players grade out better than the results, so "
                           f"{culprit} is the likelier problem")
            else:
                verdict = "the system appears to be covering for the personnel"
            out.append({
                "abbr": abbr, "name": name_of.get(abbr, abbr), "side": side,
                "personnel_rank": p_rank[abbr], "results_rank": o_rank[abbr],
                "gap": abs(diff), "verdict": verdict,
            })
    out.sort(key=lambda d: -d["gap"])
    return out


def coverage(cells):
    """How much of the 16x8 grid actually has enough data -- worth surfacing, so
    a sparse week reads as sparse rather than as a league of solid squares."""
    total = len(cells)
    enough = sum(1 for c in cells.values() if c["enough"])
    return {"cells": total, "enough": enough,
            "share": (enough / total) if total else 0.0}


# ---------------------------------------------------------------- self-test

def _row(pid, abbr, position, minutes, ar):
    """A goals-added row as returned with above_replacement=true (aggregated)."""
    return {"player_id": pid, "team_abbr": [abbr], "general_position": position,
            "minutes_played": minutes, "goals_added_above_replacement": ar}


if __name__ == "__main__":
    import random

    rng = random.Random(4)
    teams = [{"abbr": f"T{i:02d}", "name": f"Team {i:02d}",
              "xgf": rng.uniform(20, 45), "xga": rng.uniform(20, 45)}
             for i in range(16)]

    rows_by_position = {}
    for position in POSITIONS:
        rows = []
        for t in teams:
            # T07's center backs are planted below, so skip generating any here.
            if t["abbr"] == "T07" and position == "CB":
                continue
            for k in range(rng.randint(1, 3)):
                rows.append(_row(f"{t['abbr']}{position}{k}", t["abbr"], position,
                                 rng.uniform(300, 1700), rng.gauss(0.4, 1.2)))
        rows_by_position[position] = rows

    # A known, unambiguous hole: T07's only center back, heavily below
    # replacement over a full starter's workload.
    rows_by_position["CB"].append(_row("holeCB", "T07", "CB", 1600, -14.0))

    # And a DILUTION case: T01 fields one poor and one excellent full back. The
    # cell mean should look unremarkable while worst-regular exposes the problem.
    rows_by_position["FB"] = [r for r in rows_by_position["FB"]
                              if not r["player_id"].startswith("T01FB")]
    rows_by_position["FB"] += [
        _row("T01FBbad", "T01", "FB", 1500, -6.0),
        _row("T01FBgood", "T01", "FB", 1500, 6.6),
    ]

    cells = build_cells(rows_by_position, teams)
    cov = coverage(cells)
    print(f"grid: {cov['enough']}/{cov['cells']} cells have enough data "
          f"({cov['share']:.0%})")
    assert cov["cells"] == 16 * 8

    worst = league_worst_cell(cells, teams)
    print(f"league's widest hole: {worst['name']} at {worst['position']} "
          f"({worst['value']:+.2f} g+/96 vs replacement)")
    assert worst["abbr"] == "T07" and worst["position"] == "CB", worst

    w7 = weakest_for_team(cells, "T07")
    assert w7["position"] == "CB", w7
    print(f"T07's weakest: {w7['position']} ({w7['value']:+.2f})")

    # A thin cell must never be reported as a weakness.
    thin = {"XX": None}
    sparse_teams = teams + [{"abbr": "XX", "name": "Sparse FC",
                             "xgf": 30, "xga": 30}]
    sparse_rows = {p: list(r) for p, r in rows_by_position.items()}
    sparse_rows["DM"].append(_row("thin1", "XX", "DM", 150, -9.0))
    sparse_cells = build_cells(sparse_rows, sparse_teams)
    assert sparse_cells[("XX", "DM")]["enough"] is False
    assert sparse_cells[("XX", "DM")]["value"] is None
    assert weakest_for_team(sparse_cells, "XX") is None, \
        "a team with only thin cells must report no weakness, not a fake one"
    assert league_worst_cell(sparse_cells, sparse_teams)["abbr"] == "T07", \
        "a 150-minute cell must not win the league-worst headline"
    print("thin-sample guard: ok (150-min cell excluded from every finding)")

    # Dilution: the mean reads near-neutral, but the worst regular does not.
    fb = cells[("T01", "FB")]
    print(f"dilution case T01 FB: mean {fb['value']:+.2f}, "
          f"worst regular {fb['worst']['per96']:+.2f}, spread {fb['spread']:.2f}")
    assert abs(fb["value"]) < 0.10, "mean should look unremarkable here"
    assert fb["worst"]["per96"] < -0.3, "worst regular should expose the problem"
    assert fb["worst"]["pid"] == "T01FBbad"
    print("depth-masking guard: ok (weak regular visible behind a strong one)")

    # Missing above-replacement field -> row skipped, not counted as zero.
    broken = {p: [] for p in POSITIONS}
    broken["ST"] = [{"player_id": "b1", "team_abbr": ["T01"],
                     "minutes_played": 900}]
    assert build_cells(broken, teams)[("T01", "ST")]["enough"] is False
    print("missing-field guard: ok (row skipped, not scored as 0)")

    # Disaggregated fallback: if above_replacement was ignored by the API and a
    # nested per-action list came back instead, the row must still score.
    nested = {p: [] for p in POSITIONS}
    nested["CM"] = [{
        "player_id": "n1", "team_abbr": ["T02"], "minutes_played": 1200,
        "data": [{"action_type": "Passing", "goals_added_above_avg": 1.5},
                 {"action_type": "Receiving", "goals_added_above_avg": -0.5}],
    }]
    nc = build_cells(nested, teams)[("T02", "CM")]
    assert nc["enough"] and abs(nc["value"] - (1.0 / 1200 * 96)) < 1e-9, nc
    print("nested-shape fallback: ok")

    dis = find_disagreements(cells, teams)
    print(f"\npersonnel-vs-results disagreements ({len(dis)}):")
    for d in dis[:4]:
        print(f"  {d['name']:<10} {d['side']:<8} personnel #{d['personnel_rank']:<2} "
              f"results #{d['results_rank']:<2} (gap {d['gap']})")

    norm = normalize_across_positions(cells)
    zs = [c["value"] for c in norm.values() if c["enough"]]
    print(f"\nnormalized fallback: {len(zs)} cells, mean {mean(zs):+.2f} "
          f"(should be ~0)")
    assert abs(mean(zs)) < 0.2

    print("\nall assertions passed")
