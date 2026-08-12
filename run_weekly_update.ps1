# Windows equivalent of run_weekly_update.sh -- pulls fresh NWSL stats,
# regenerates dashboard.html, and (if this folder is set up as a git repo
# with a remote -- see the README's "Hosting on GitHub Pages" section)
# pushes the update so the hosted, live URL refreshes itself too. Run this
# on your own PC (not the cloud sandbox this kit was built in), scheduled
# weekly via Task Scheduler.
#
# One-time setup (PowerShell, from this folder):
#   python -m venv .venv
#   .venv\Scripts\Activate.ps1
#   pip install requests
#
# Task Scheduler setup:
#   1. Open Task Scheduler -> Create Task
#   2. Trigger: Weekly, pick a day/time (e.g. Monday 7:00 AM)
#   3. Action: "Start a program"
#        Program/script:  powershell.exe
#        Add arguments:   -ExecutionPolicy Bypass -File "C:\path\to\nwsl_xg_starter\run_weekly_update.ps1"
#        Start in:        C:\path\to\nwsl_xg_starter
#
# GitHub Pages auto-deploy (optional -- see README for the one-time setup):
# once this folder is `git init`'d with an `origin` remote pointing at your
# GitHub Pages repo and you've pushed once manually (with Git for Windows
# or GitHub Desktop), this script detects that automatically and pushes
# index.html on every run after that.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Test-Path ".venv\Scripts\Activate.ps1") {
    . .venv\Scripts\Activate.ps1
}

$Season = if ($env:NWSL_SEASON) { $env:NWSL_SEASON } else { "2026" }
$Minutes = if ($env:NWSL_MIN_MINUTES) { $env:NWSL_MIN_MINUTES } else { "500" }
$TopN = if ($env:NWSL_TOP_N) { $env:NWSL_TOP_N } else { "20" }
$Timestamp = Get-Date -Format "yyyy-MM-dd"

Write-Host "[$Timestamp] Refreshing NWSL dashboard (season=$Season, minutes=$Minutes, top_n=$TopN)..."
python build_dashboard.py --season $Season --minutes $Minutes --top-n $TopN --out dashboard.html
if ($LASTEXITCODE -ne 0) {
    Write-Host "[$Timestamp] ERROR: build_dashboard.py failed (exit $LASTEXITCODE) -- stopping before touching history/ or git."
    exit 1
}

New-Item -ItemType Directory -Force -Path "history" | Out-Null
Copy-Item "dashboard.html" "history\dashboard_$Timestamp.html" -Force

# keep the last 12 dated snapshots
Get-ChildItem "history\dashboard_*.html" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 12 | Remove-Item

Write-Host "[$Timestamp] Done. dashboard.html updated; snapshot saved to history\dashboard_$Timestamp.html"

# ---- GitHub Pages auto-deploy (only runs if you've set this up) ----
# Note: native commands like git.exe don't throw terminating errors even
# with $ErrorActionPreference = "Stop", so check $LASTEXITCODE explicitly
# rather than try/catch here.
$hasGitRemote = $false
if (Test-Path ".git") {
    git remote get-url origin *> $null
    if ($LASTEXITCODE -eq 0) {
        $hasGitRemote = $true
    }
}

if ($hasGitRemote) {
    Write-Host "[$Timestamp] Git remote detected -- deploying to GitHub Pages..."
    Copy-Item "dashboard.html" "index.html" -Force
    git add index.html
    $staged = git diff --cached --name-only
    if (-not $staged) {
        Write-Host "[$Timestamp] No changes since last deploy -- nothing to push."
    } else {
        git commit -m "Weekly stats refresh: $Timestamp" --quiet
        git push --quiet
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[$Timestamp] Pushed. Live site will update within a minute or two."
        } else {
            Write-Host "[$Timestamp] WARNING: git push failed -- check your remote/auth (git push manually to see the error)."
        }
    }
} else {
    Write-Host "[$Timestamp] No git remote configured -- skipping deploy. See README 'Hosting on GitHub Pages' for one-time setup."
}
