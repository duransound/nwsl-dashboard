# Reconciled round 22 — how to apply and push

**Discard the `dashboard_template.py`, `build_dashboard.py` and
`round22.patch` I sent earlier.** They were cut against files that have since
been rewritten, and applying them would revert the Methods tab, the sortable
data tables, npxG and the finishing-uncertainty work.

## What was actually broken

Two sessions wrote `build_dashboard.py` about five seconds apart at 12:44:55
PT. The npxG/Methods version landed last and silently reverted the
minutes-qualification round, so:

- `run_weekly_update.sh` passes `--minutes-per-game`, which the surviving
  `build_dashboard.py` does not accept → the weekly build dies immediately.
- `qualification.py` sits in the folder, imported by nothing.
- `chart_builders.py` lost `qualification_phrase()` the same way.
- `mvp_tracker.py` is the *other* version — it kept its `_qualifier()` helper,
  which is why nothing crashed before the CLI flag did.

Both rounds' project docs report success. Each was true when written.

## How to apply

```bash
cd ~/Downloads/nwsl_xg_starter
python3 apply_round22.py
```

It edits `dashboard_template.py`, `chart_builders.py` and `build_dashboard.py`
in place, on top of whatever is currently there. **Copy `glossary.py` into the
folder first** — `build_dashboard.py` imports it.

It's a script of anchored string replacements rather than a `git apply` patch
on purpose: a unified diff is pinned to line context and breaks the moment
another session touches a nearby line, whereas these survive edits elsewhere
in the file and fail loudly — `AssertionError` naming the exact edit — instead
of applying in the wrong place. It's also idempotent: run it twice and the
second run reports all 42 edits as "already applied" and changes nothing.

If an anchor has genuinely moved, you'll get one named failure rather than a
corrupted file, and nothing is written until every edit in that file succeeds.

Then:

```bash
python3 apply_round22.py          # 42 edits applied
python3 _mock_live_run.py         # end-to-end check, no network needed
./run_weekly_update.sh            # real build + deploy
```

Also drop `social-card.png` (sent earlier) in the repo root next to
`index.html` — that's the exact URL `og:image` points at.

## What the reconciliation does

**Re-unifies the qualification rule** into the current `build_dashboard.py`,
keeping all the npxG work: `--minutes-per-game` (default 30), `--minutes`
demoted to a flat-floor escape hatch defaulting to `None`, `count_games`
carried on team rows, and the api_floor / client-side-filter split applied to
the player pool, goals added, goalkeepers and position gaps. Compare Teammates
keeps its deliberate 90-minute exemption.

**`qualification_phrase()` restored to `chart_builders.py`**, and used for the
two `meta["minimumMinutes"]` fields as well as the blurbs. That second part
matters: those dicts go through `json.dumps()` in `render_dashboard()`, and a
`Qualification` object is not JSON-serializable — it would crash every live
run. Same bug the npxG round hit and fixed; it came back with the revert.

**Social preview tags + viewport + phone-width CSS** re-cut against the
current template. Thirteen tabs wrapped to six stacked rows at 390px; they're
now one scrolling row that pulls the active tab into view.

**The glossary is folded into the Methods tab** rather than being a competing
explainer tab — inserted as the *first* section, so the tab opens with what
the words mean and then gets progressively more technical. `build_methods_chart`
is untouched; the insert happens by index in `build_dashboard.py`.

**My `data_stamp` was dropped** in favour of the existing `generated_at`
"Built &lt;date&gt;" stamp. Two stamps would have been redundant.

## Verified

`_mock_live_run.py` drives `build_dashboard.main()` to completion against a
mock of all eight endpoints, using the exact argv `run_weekly_update.sh`
passes — because the thing that actually broke was a CLI flag, which no
unit-level check would have caught.

Teams are given uneven games played (16–20) so the per-team bars really differ
(480–600). The load-bearing assertion: 16 teams × 4 players at
300/500/700/1500 minutes should yield **exactly 36** qualifiers — 300 clears
nothing, 700 and 1500 clear every bar (32), and a 500-minute player clears only
on a 16-game team, of which there are 4. If the client-side filter were
skipped, the API floor of 480 alone would let 48 through. It returns 36.

Also asserted: no call ever goes out at a hardcoded 500; Compare Teammates
still uses 90; `og:image` is absolute; `og:description` carries the week's
story rather than the static subtitle; the glossary is section 0 and the
technical sections still follow it; no `<Qualification` string leaked into the
JSON; masthead still appears exactly once; Space Grotesk still absent; CSV
exports intact. Rendered at 390×844 and 1280×900 with no horizontal overflow.

## Still open

- **The Position Gaps headline** ("0.01 g+ per 96 below replacement" as "the
  league's widest hole") — still not investigated. The glossary now notes
  these are per-match rates and that 0.05 per 96 is ~1.2 goals over a season,
  which helps, but if the raw number is really 0.01 the claim is stronger than
  the gap supports.
- **The repo still hasn't been checked for a committed API key.**
- **Two sessions writing this folder is the actual root cause.** Nothing here
  prevents it happening again on the next round.
