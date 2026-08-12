"""
Loader for NWSL data from StatsBomb's free Open Data repository
(https://github.com/statsbomb/open-data).

Why this exists: ASA's API gives aggregated stats (season totals, per-96
rates) but no shot locations -- there's no way to draw a real shot map from
it. StatsBomb's open data is free, event-level (every pass/shot/carry/
pressure, with pitch x/y and a StatsBomb-model xG value per shot), and is
the same data *format* StatsBomb sells to professional clubs. Confirmed by
reading data/competitions.json directly: StatsBomb has published exactly
two NWSL seasons -- **2018 and 2023** -- nothing more recent, and nothing
earlier. This is a static, one-time data source, not something to put on
the weekly-refresh schedule the ASA-based dashboard uses.

There's no REST API -- the data is plain JSON files sitting in a git repo.
This module uses `git sparse-checkout` (partial clone) to pull down ONLY
the specific files a given call needs -- never a full clone. The full repo
holds dozens of other competitions (women's Euros, multiple World Cups,
La Liga, Bundesliga, etc.) and is multiple gigabytes; a naive `git clone`
or a directory-level sparse pattern like "data" will try to download all
of it. Every path added here is a single exact file
(`git sparse-checkout add --no-cone /data/events/<match_id>.json`), which
keeps each fetch to the size of that one file.

Local cache: .statsbomb_cache/ next to this script. Safe to delete any
time -- everything gets re-fetched on demand.

Data spec: https://github.com/statsbomb/open-data/tree/master/doc
"""

import json
import subprocess
from pathlib import Path

REPO_URL = "https://github.com/statsbomb/open-data.git"
CACHE_DIR = Path(__file__).parent / ".statsbomb_cache"

NWSL_COMPETITION_ID = 49
# season_name -> season_id, read from data/competitions.json. StatsBomb has
# ONLY published these two NWSL seasons -- there is no "latest season"
# call here, unlike the ASA API. Re-check competitions.json if a future
# StatsBomb data release might have added more.
NWSL_SEASONS = {"2023": 107, "2018": 3}

PITCH_LENGTH = 120.0  # StatsBomb's fixed pitch coordinate system, x: 0-120
PITCH_WIDTH = 80.0    # y: 0-80, regardless of the real stadium's dimensions


def _run_git(args, cwd=None):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout


def _ensure_repo():
    """One-time setup: a blobless (--filter=blob:none), sparse clone. This
    downloads git's commit/tree metadata (fast, a few MB) but no file
    contents -- content only gets pulled in by _ensure_paths() below, one
    exact path at a time."""
    if CACHE_DIR.exists():
        return
    CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["clone", "--filter=blob:none", "--sparse", REPO_URL, str(CACHE_DIR)])
    _run_git(["sparse-checkout", "set", "--no-cone", "/data/competitions.json"], cwd=CACHE_DIR)


def _ensure_paths(*repo_relative_paths):
    """Make sure each given repo-relative path (e.g. "data/matches/49/107.
    json") has actually been checked out, fetching it if not. Cheap to call
    repeatedly -- already-present paths are skipped."""
    _ensure_repo()
    current = set(_run_git(["sparse-checkout", "list"], cwd=CACHE_DIR).split())
    missing = [p for p in repo_relative_paths if f"/{p}" not in current]
    if missing:
        _run_git(["sparse-checkout", "add", "--no-cone", *[f"/{p}" for p in missing]], cwd=CACHE_DIR)


def get_nwsl_competitions():
    """Raw competitions.json entries for NWSL -- one per season StatsBomb
    has published. Useful as the source of truth for NWSL_SEASONS above,
    in case StatsBomb adds a season later."""
    _ensure_repo()
    comps = json.loads((CACHE_DIR / "data" / "competitions.json").read_text())
    return [c for c in comps if c["competition_name"] == "NWSL"]


def get_matches(season_name):
    """season_name: '2018' or '2023'. Returns the season's full match list
    -- dicts with match_id, match_date, home_team/away_team, home_score/
    away_score, competition_stage (e.g. "Regular Season", "Semi-finals",
    "Final"), etc."""
    if season_name not in NWSL_SEASONS:
        raise ValueError(
            f"StatsBomb only publishes NWSL {sorted(NWSL_SEASONS)} -- not {season_name!r}"
        )
    season_id = NWSL_SEASONS[season_name]
    path = f"data/matches/{NWSL_COMPETITION_ID}/{season_id}.json"
    _ensure_paths(path)
    return json.loads((CACHE_DIR / path).read_text())


def get_events(match_id):
    """Full raw event stream for one match -- every pass, shot, carry,
    pressure, duel, etc., in StatsBomb's event format. This is the
    "professional tool" data model: each event includes a type, team,
    player, timestamp, pitch location, and type-specific detail (e.g. a
    Shot event's nested "shot" dict has statsbomb_xg, outcome, technique,
    body_part, and even a freeze-frame of where every nearby player was
    standing)."""
    path = f"data/events/{match_id}.json"
    _ensure_paths(path)
    return json.loads((CACHE_DIR / path).read_text())


def get_shots(match_id):
    """Convenience wrapper over get_events(): just the Shot-type events,
    flattened to the fields a shot map or shot-quality analysis actually
    needs. `x`/`y` are in StatsBomb's 0-120 by 0-80 pitch coordinates
    (PITCH_LENGTH/PITCH_WIDTH above); `outcome` is one of 'Goal', 'Saved',
    'Off T', 'Blocked', 'Wayward', 'Post', 'Saved to Post', 'Saved Off
    Target'."""
    events = get_events(match_id)
    shots = []
    for e in events:
        if e["type"]["name"] != "Shot":
            continue
        s = e["shot"]
        shots.append({
            "player": e["player"]["name"],
            "team": e["team"]["name"],
            "minute": e["minute"],
            "second": e["second"],
            "x": e["location"][0],
            "y": e["location"][1],
            "xg": s["statsbomb_xg"],
            "outcome": s["outcome"]["name"],
            "body_part": s["body_part"]["name"],
            "technique": s["technique"]["name"],
        })
    return shots


def get_all_shots_for_season(season_name, competition_stage=None):
    """Every shot across every match in a season (all events/*.json for
    that season's matches -- 137 files for 2023, so this takes a bit
    longer the first time; cached after that). Pass competition_stage
    (e.g. "Final", "Regular Season") to narrow it down."""
    matches = get_matches(season_name)
    if competition_stage:
        matches = [m for m in matches if m.get("competition_stage", {}).get("name") == competition_stage]
    all_shots = []
    for m in matches:
        for shot in get_shots(m["match_id"]):
            shot["match_id"] = m["match_id"]
            shot["match_date"] = m["match_date"]
            all_shots.append(shot)
    return all_shots
