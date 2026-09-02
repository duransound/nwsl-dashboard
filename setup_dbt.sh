#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup_dbt.sh -- put dbt in its own virtualenv, once.
#
#   cd ~/Downloads/nwsl_xg_starter
#   bash setup_dbt.sh
#
# WHY A SEPARATE VENV
#
# Nothing in this project does `import dbt` -- nwsl_warehouse.py shells out to
# the `dbt` COMMAND. A command you invoke is not a dependency you import, so
# dbt has no business sharing a dependency resolver with pandas, marimo and
# everything else in the project venv. It gets its own, and the loader finds
# it at .venv-dbt/bin/dbt without any PATH changes.
#
# WHY THE FIRST TWO ATTEMPTS FAILED (2026-09-02)
#
# Not a dependency conflict, though it looked like one. The real error:
#
#   dbt-core-experimental-parser ... RuntimeError: failed to download
#   https://github.com/.../dbt_core_experimental_parser-2.0.0rc1-...arm64.whl:
#   [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate
#
# dbt-core depends on dbt-core-experimental-parser, whose current release
# (2.0.0rc1) is published to PyPI as a source-only stub that downloads the
# real platform wheel from GitHub during metadata generation. That download
# uses stdlib urllib, and a python.org macOS build ships with no CA bundle
# wired into OpenSSL -- so it cannot verify github.com.
#
# This is why the ASA API calls have always worked while this failed:
# `requests` bundles its own certificates (certifi); stdlib ssl does not.
#
# Two fixes, tried in order below:
#   1. point stdlib ssl at certifi's CA bundle via SSL_CERT_FILE, so the
#      download can verify GitHub and the normal install path works
#   2. if that still fails, pin the parser to 2.0.0a4 -- the last release that
#      publishes a real macosx_11_0_arm64 wheel to PyPI, so nothing is
#      downloaded at build time at all
#
# The permanent system-wide fix, worth doing regardless, is one double-click:
#   /Applications/Python 3.11/Install Certificates.command
# It installs certifi's bundle for that interpreter, and every stdlib HTTPS
# call from it works afterwards.
#
# Full output goes to dbt_setup.log -- no `| tail`, because the reason a build
# failed is the whole point of the log.
# ---------------------------------------------------------------------------

cd "$(dirname "$0")" || exit 1
LOG="dbt_setup.log"
VENV=".venv-dbt"
PARSER_WHEEL_PIN="dbt-core-experimental-parser==2.0.0a4"

{
  echo "======================================================================"
  echo "dbt setup  $(date)"
  echo "======================================================================"

  # The SYSTEM python, not whatever venv is active -- the point is a clean start.
  PY="$(command -v python3.12 || command -v python3.11 || command -v python3)"
  echo "base interpreter: $PY  ($("$PY" --version 2>&1))"

  if [ -d "$VENV" ]; then
    echo "$VENV already exists -- reusing it"
  else
    echo "creating $VENV ..."
    "$PY" -m venv "$VENV" || { echo "!! could not create the venv"; exit 1; }
  fi

  echo
  echo "--- pip, setuptools, wheel --------------------------------------------"
  "$VENV/bin/python" -m pip install --upgrade pip setuptools wheel 2>&1 | tail -3

  echo
  echo "--- certificates ------------------------------------------------------"
  "$VENV/bin/python" -m pip install --upgrade certifi 2>&1 | tail -2
  CERTS="$("$VENV/bin/python" -m certifi 2>/dev/null)"
  if [ -n "$CERTS" ] && [ -f "$CERTS" ]; then
    export SSL_CERT_FILE="$CERTS"
    export REQUESTS_CA_BUNDLE="$CERTS"
    echo "SSL_CERT_FILE -> $CERTS"
    "$VENV/bin/python" - <<'PYCHK' 2>&1
import urllib.request
try:
    urllib.request.urlopen("https://github.com", timeout=20)
    print("verified https://github.com  -- stdlib ssl is working")
except Exception as exc:
    print(f"still cannot verify github.com: {type(exc).__name__}: {exc}")
PYCHK
  else
    echo "!! certifi did not report a bundle path; continuing without it"
  fi

  echo
  echo "--- attempt 1: dbt-duckdb (normal install) ----------------------------"
  "$VENV/bin/python" -m pip install "dbt-duckdb" 2>&1

  if [ ! -x "$VENV/bin/dbt" ]; then
    echo
    echo "--- attempt 2: pin the parser to a version with a real wheel ---------"
    echo "    $PARSER_WHEEL_PIN  (2.0.0rc1 is source-only and downloads at build time)"
    "$VENV/bin/python" -m pip install "$PARSER_WHEEL_PIN" "dbt-duckdb" 2>&1
  fi

  echo
  echo "--- result ------------------------------------------------------------"
  if [ -x "$VENV/bin/dbt" ]; then
    "$VENV/bin/dbt" --version 2>&1
    echo
    echo "dbt is at: $(pwd)/$VENV/bin/dbt"
    echo "nwsl_warehouse.py finds it there automatically. Next:"
    echo "    bash run_warehouse.sh"
  else
    echo "!! $VENV/bin/dbt was not created. The pip output above says why."
    echo
    echo "   If it is still a certificate error, run this once and try again:"
    echo "       /Applications/Python 3.11/Install Certificates.command"
    echo
    echo "   The warehouse works without dbt either way -- it falls back to"
    echo "   the sql/ files. You just don't get the 41 data tests."
  fi

  echo
  echo "======================================================================"
  echo "done  $(date)"
  echo "======================================================================"
} > "$LOG" 2>&1

echo "Finished. Full output is in $(pwd)/$LOG"
tail -22 "$LOG"
