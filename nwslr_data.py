"""
Loader for historical NWSL data from the nwslR project's public GitHub
repo (https://github.com/adror1/nwslR), covering **2013 (the league's
inaugural season) through 2019** -- years ASA's API doesn't reach.

nwslR is normally installed as an R package (`devtools::install_github
("adror1/nwslR")`), and its cleaned data ships as .rda (R's binary data
format). But the package's data-raw/ folder -- the actual source files the
.rda objects are built from -- is plain CSV and Excel, so this module reads
those directly with pandas. No R installation needed.

What's actually in data-raw/ (confirmed by inspecting the repo directly):
  - franchise.csv       team identity across relocations/rebrands, 2013-2019
                         (includes defunct clubs: Boston Breakers, FC Kansas
                         City, Western New York Flash)
  - stadium.csv          venue + average attendance by team/year
  - fieldplayers_overall_season_<year>.xlsx  (2013-2019, one file per year)
                         season box-score stats per outfield player
                         (Player, Nation, Pos, Squad, Age, Born, MP, Starts,
                         Min, Gls, Ast, PK, PKatt, CrdY, CrdR)
  - goalkeepers_season_<year>.xlsx  (2013-2019) -- same idea, goalkeepers
  - player_awards.xlsx   league awards by season
  - adv_team_stats.csv / adv_player_stats.csv -- match-level Opta-style
    stats, 2016-2019 only, ~150 columns, not wrapped here yet (see the
    bottom of this file for a raw-pandas escape hatch if a future round
    wants them)

Team-name gotcha (confirmed by reading every season file): squad names are
NOT consistent year to year -- full names through 2016 ("Portland Thorns
FC"), short city/nickname strings from 2017 on ("Portland"), and Seattle
renamed "Reign" in the 2019 file alone. TEAM_ALIASES below normalizes every
variant actually seen onto the same team_id abbreviations the rest of this
project uses.

License: nwslR is GPL-3 (see the repo's LICENSE.md) -- this module reads
its public source data for local analysis, same use the R package itself
is built for.
"""

import subprocess
from pathlib import Path

import pandas as pd

REPO_URL = "https://github.com/adror1/nwslR.git"
CACHE_DIR = Path(__file__).parent / ".nwslr_cache"

SEASON_YEARS = list(range(2013, 2020))  # 2013-2019 inclusive

TEAM_ALIASES = {
    "boston breakers": "BOS", "boston": "BOS",
    "chicago red stars": "CHI", "chicago": "CHI",
    "fc kansas city": "KC", "kansas city": "KC",
    "portland thorns fc": "POR", "portland": "POR",
    "seattle": "SEA", "reign": "SEA", "reign fc": "SEA",
    "sky blue fc": "NJ", "sky blue": "NJ",
    "washington spirit": "WAS", "washington": "WAS",
    "western new york flash": "WNY",
    "houston dash": "HOU", "houston": "HOU",
    "orlando pride": "ORL", "orlando": "ORL",
    "north carolina courage": "NC", "north carolina": "NC",
    "utah royals fc": "UTA", "utah": "UTA",
}

# For display -- current/most-recognizable full name per team_id.
TEAM_DISPLAY_NAMES = {
    "BOS": "Boston Breakers", "CHI": "Chicago Red Stars", "KC": "Kansas City",
    "POR": "Portland Thorns FC", "SEA": "Seattle Reign FC", "NJ": "Sky Blue FC",
    "WAS": "Washington Spirit", "WNY": "Western New York Flash",
    "HOU": "Houston Dash", "ORL": "Orlando Pride", "NC": "North Carolina Courage",
    "UTA": "Utah Royals FC",
}


def _run_git(args, cwd=None):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr}")
    return result.stdout


def _ensure_repo():
    """One-time setup: blobless, sparse clone of just data-raw/ (the whole
    folder is ~11MB, small enough not to bother trimming further)."""
    if CACHE_DIR.exists():
        return
    CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
    _run_git([
        "clone", "--depth", "1", "--filter=blob:none", "--sparse",
        REPO_URL, str(CACHE_DIR),
    ])
    _run_git(["sparse-checkout", "set", "data-raw"], cwd=CACHE_DIR)


def _team_id(raw_name):
    return TEAM_ALIASES.get(str(raw_name).strip().lower(), str(raw_name).strip())


def _check_year(year):
    if year not in SEASON_YEARS:
        raise ValueError(
            f"nwslR's season files only cover {SEASON_YEARS[0]}-{SEASON_YEARS[-1]}, not {year}"
        )


def load_franchise():
    """team_id, team_name, city, state, season -- one row per team-season,
    2013-2019. The cleanest source for "what was this franchise called/
    where did it play in year X" questions, including defunct clubs."""
    _ensure_repo()
    return pd.read_csv(CACHE_DIR / "data-raw" / "franchise.csv")


def load_stadium():
    """team_id, stadium name/location/capacity, avg_attendance, year."""
    _ensure_repo()
    df = pd.read_csv(CACHE_DIR / "data-raw" / "stadium.csv")
    df.columns = [c.strip() for c in df.columns]
    return df


def load_player_awards():
    _ensure_repo()
    return pd.read_excel(CACHE_DIR / "data-raw" / "player_awards.xlsx")


def load_field_player_season(year):
    """One season's outfield player box scores, plus a normalized
    `team_id` column (see TEAM_ALIASES) and a `season` column."""
    _check_year(year)
    _ensure_repo()
    df = pd.read_excel(CACHE_DIR / "data-raw" / f"fieldplayers_overall_season_{year}.xlsx")
    df["team_id"] = df["Squad"].map(_team_id)
    df["season"] = year
    return df


def load_goalkeeper_season(year):
    _check_year(year)
    _ensure_repo()
    df = pd.read_excel(CACHE_DIR / "data-raw" / f"goalkeepers_season_{year}.xlsx")
    df["team_id"] = df["Squad"].map(_team_id)
    df["season"] = year
    return df


def load_all_field_player_seasons():
    """Every 2013-2019 season concatenated into one DataFrame -- the
    natural input for any multi-season trend chart."""
    return pd.concat([load_field_player_season(y) for y in SEASON_YEARS], ignore_index=True)


def load_all_goalkeeper_seasons():
    return pd.concat([load_goalkeeper_season(y) for y in SEASON_YEARS], ignore_index=True)


# --- Escape hatch for the two big match-level files (2016-2019, ~150 Opta
# columns each) -- not cleaned/wrapped yet, but readable directly if a
# future round wants them:
#
#   import pandas as pd
#   from nwslr_data import _ensure_repo, CACHE_DIR
#   _ensure_repo()
#   adv_team = pd.read_csv(CACHE_DIR / "data-raw" / "adv_team_stats.csv")
#   adv_player = pd.read_csv(CACHE_DIR / "data-raw" / "adv_player_stats.csv")
#
# game_id encodes the date as a suffix (e.g. "portland-thorns-vs-houston-
# dash-2016-09-07") -- there's no separate date column.
