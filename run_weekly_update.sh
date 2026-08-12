#!/usr/bin/env bash
# Pulls fresh NWSL stats from the ASA API, regenerates the dashboard, and
# (if this folder is set up as a git repo with a remote -- see the README's
# "Hosting on GitHub Pages" section) pushes the update so the hosted, live
# URL refreshes itself too. Meant to run on YOUR machine (or any server with
# normal internet access, not the cloud sandbox this kit was built in) on a
# weekly schedule via cron. No Claude session or tokens involved -- this is
# a plain Python script talking directly to the API, plus plain git/gh.
#
# One-time setup:
#   cd /path/to/nwsl_xg_starter
#   python3 -m venv .venv && source .venv/bin/activate
#   pip install requests
#
# Then add a weekly cron entry (macOS/Linux), e.g. every Monday at 7am:
#   crontab -e
#   0 7 * * 1 /path/to/nwsl_xg_starter/run_weekly_update.sh >> /path/to/nwsl_xg_starter/weekly_update.log 2>&1
#
# On Windows, use run_weekly_update.ps1 with Task Scheduler instead.
#
# GitHub Pages auto-deploy (optional -- see README for the one-time setup):
# once this folder is `git init`'d with a `origin` remote pointing at your
# GitHub Pages repo and you've pushed once manually, this script detects
# that automatically and pushes index.html on every run after that. If you
# haven't set that up, this script still works fine -- it just regenerates
# dashboard.html locally and skips the deploy step.

set -euo pipefail
cd "$(dirname "$0")"

# Use a virtualenv if one exists (see setup above); otherwise fall back to
# whatever `python3` resolves to on this machine.
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

SEASON="${NWSL_SEASON:-2026}"
MINUTES="${NWSL_MIN_MINUTES:-500}"
# TOP_N now controls only the Goals Added leaderboard bar chart's length --
# the scatter charts (Goals vs. xG, xG vs. xA, Shot Quality, Playmaking
# Style) always plot every player above MINUTES, full league, regardless of
# this value (round 13, see build_dashboard.py's docstring).
TOP_N="${NWSL_TOP_N:-20}"
TIMESTAMP="$(date +%Y-%m-%d)"

echo "[$TIMESTAMP] Refreshing NWSL dashboard (season=$SEASON, minutes=$MINUTES, top_n=$TOP_N)..."
python3 build_dashboard.py --season "$SEASON" --minutes "$MINUTES" --top-n "$TOP_N" --out dashboard.html

# Keep one dated backup per run so you can see how the data changed week to
# week, without cluttering the folder indefinitely (keeps the last 12).
mkdir -p history
cp dashboard.html "history/dashboard_${TIMESTAMP}.html"
ls -1t history/dashboard_*.html 2>/dev/null | tail -n +13 | xargs -r rm --

echo "[$TIMESTAMP] Done. dashboard.html updated; snapshot saved to history/dashboard_${TIMESTAMP}.html"

# ---- GitHub Pages auto-deploy (only runs if you've set this up) ----
if [ -d ".git" ] && git remote get-url origin >/dev/null 2>&1; then
    echo "[$TIMESTAMP] Git remote detected -- deploying to GitHub Pages..."
    cp dashboard.html index.html
    git add index.html
    if git diff --cached --quiet; then
        echo "[$TIMESTAMP] No changes since last deploy -- nothing to push."
    else
        git commit -m "Weekly stats refresh: ${TIMESTAMP}" --quiet
        if git push --quiet; then
            echo "[$TIMESTAMP] Pushed. Live site will update within a minute or two."
        else
            echo "[$TIMESTAMP] WARNING: git push failed -- check your remote/auth (git push manually to see the error)."
        fi
    fi
else
    echo "[$TIMESTAMP] No git remote configured -- skipping deploy. See README 'Hosting on GitHub Pages' for one-time setup."
fi
