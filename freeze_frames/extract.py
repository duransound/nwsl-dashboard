"""Extract every NWSL 2023 shot from StatsBomb open data, with the defensive
context its freeze frame carries.

StatsBomb pitch: 120 x 80, attacking goal at x=120, posts at y=36 and y=44.
"""
import json, math, pathlib, csv, subprocess, sys

# StatsBomb's open-data repo holds dozens of competitions and several
# gigabytes. The pattern that works (established round 10 of this project) is
# a blobless, sparse clone plus EXACT file paths with a leading slash --
# a directory-level cone pattern tries to pull everything and hangs.
REPO = pathlib.Path("statsbomb-open-data")
COMPETITION, SEASON = 49, 107          # NWSL 2023
EVENTS = REPO / "data/events"


def fetch():
    """Clone just the NWSL 2023 match list and its 137 event files (~380 MB).
    Skipped entirely if the files are already present."""
    if not REPO.exists():
        print("cloning statsbomb/open-data (blobless, sparse)...")
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--sparse",
                        "https://github.com/statsbomb/open-data.git", str(REPO)], check=True)
    matches = REPO / f"data/matches/{COMPETITION}/{SEASON}.json"
    if not matches.exists():
        subprocess.run(["git", "sparse-checkout", "set", "--no-cone",
                        f"/data/matches/{COMPETITION}/{SEASON}.json"], cwd=REPO, check=True)
    ids = [m["match_id"] for m in json.loads(matches.read_text())]
    missing = [i for i in ids if not (EVENTS / f"{i}.json").exists()]
    if missing:
        print(f"fetching {len(missing)} event files (a minute or so)...")
        subprocess.run(["git", "sparse-checkout", "add", "--no-cone",
                        f"/data/matches/{COMPETITION}/{SEASON}.json",
                        *[f"/data/events/{i}.json" for i in ids]], cwd=REPO, check=True)
    return ids
POST_A, POST_B = (120.0, 36.0), (120.0, 44.0)
GOAL_C = (120.0, 40.0)


def _sign(p, a, b):
    return (p[0]-b[0])*(a[1]-b[1]) - (a[0]-b[0])*(p[1]-b[1])


def in_cone(p, shot):
    """Is p inside the triangle shot -> both posts? Standard same-sign test."""
    d1, d2, d3 = _sign(p, shot, POST_A), _sign(p, POST_A, POST_B), _sign(p, POST_B, shot)
    neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (neg and pos)


def goal_angle(loc):
    """Angle in degrees subtended by the goal mouth from the shot location."""
    ax, ay = POST_A[0]-loc[0], POST_A[1]-loc[1]
    bx, by = POST_B[0]-loc[0], POST_B[1]-loc[1]
    na, nb = math.hypot(ax, ay), math.hypot(bx, by)
    if na == 0 or nb == 0:
        return 0.0
    cos = max(-1.0, min(1.0, (ax*bx + ay*by)/(na*nb)))
    return math.degrees(math.acos(cos))


fetch()
rows = []
files = sorted(EVENTS.glob("*.json"))
for f in files:
    ev = json.loads(f.read_text())
    for e in ev:
        if e.get("type", {}).get("name") != "Shot":
            continue
        sh = e["shot"]
        ff = sh.get("freeze_frame")
        loc = e.get("location")
        if not ff or not loc:
            continue
        stype = sh.get("type", {}).get("name", "")
        if stype == "Penalty":
            continue

        opp = [a for a in ff if not a["teammate"]]
        gk = next((a for a in opp if a["position"]["name"] == "Goalkeeper"), None)
        outfield = [a for a in opp if a["position"]["name"] != "Goalkeeper"]

        cone = sum(1 for a in outfield if in_cone(a["location"], loc))
        nearest = min((math.dist(loc, a["location"]) for a in outfield), default=None)

        rows.append({
            "match": f.stem,
            "player": e["player"]["name"],
            "team": e["team"]["name"],
            "minute": e.get("minute"),
            "x": round(loc[0], 2), "y": round(loc[1], 2),
            "distance": round(math.dist(loc, GOAL_C), 3),
            "angle": round(goal_angle(loc), 3),
            "body_part": sh.get("body_part", {}).get("name"),
            "shot_type": stype,
            "under_pressure": bool(e.get("under_pressure")),
            "sb_xg": round(sh["statsbomb_xg"], 5),
            "goal": int(sh.get("outcome", {}).get("name") == "Goal"),
            "defenders_in_cone": cone,
            "nearest_defender": round(nearest, 3) if nearest is not None else None,
            "gk_off_line": round(120.0 - gk["location"][0], 3) if gk else None,
            "gk_lateral": round(gk["location"][1] - 40.0, 3) if gk else None,
            "n_in_frame": len(ff),
        })

print(f"matches parsed: {len(files)}   shots with freeze frames (non-penalty): {len(rows)}")
with open("shots_2023.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)
print("wrote shots_2023.csv")
