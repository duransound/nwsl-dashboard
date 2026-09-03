# Data Project Playbook

How to stand up the next one without relearning this one.

Everything below came from building the NWSL dashboard over roughly three
dozen rounds. The parts that read like rules are rules because breaking them
cost a debugging session, and each one names the session it cost. Nothing
here is soccer-specific. Where a rule has an exception, the exception is
stated — a playbook you have to argue with is worse than no playbook.

**The one-sentence version:** land the source untouched, normalise it once,
model it with tests that are named after real bugs, publish from the models,
and let exactly one thing do the publishing.

---

## 0. Before writing any code, survey the source

Half the expensive mistakes happen here, before there is anything to debug.

**Confirm coverage first — league, seasons, and access tier.** A tracking-data
vendor was recommended three times for this project before anyone checked
which leagues it covers. It was the Australian A-League. Ten seconds of
checking would have saved three rounds of planning.

**Pull one real response and save it to disk.** Not into a variable — into a
file you can read. Then answer, from the file rather than from the docs:

- What is the grain? One row per what?
- Which fields change type between endpoints? (Here: `team_id` is a string
  on team endpoints and a *list* on player endpoints.)
- Which fields have aliases? (`minutes` vs `minutes_played`;
  `count_games` vs `games` vs `games_played`.)
- What is nested that looks flat? (Goals-added hides a per-action breakdown
  under `data`.)
- What does the API do when there is nothing to return — `[]`, `null`, or a
  full list of zeroed rows?

**Write down what you cannot verify.** Undocumented fields are hypotheses.
See §7, "prefer the measurement."

---

## 1. Decide whether it needs a warehouse

It usually doesn't, at first. A fetch-compute-render script is the correct
starting point and this project ran on one for twenty-plus rounds.

Graduate when any of these becomes true:

- The data refreshes on a schedule and someone will care whether last week's
  numbers were right
- There is a second season, a second source, or a second consumer
- You have debugged the same upstream quirk twice
- You want to change how something is computed *without* re-fetching

Until then, a script is not technical debt. It's the right size.

---

## 2. The four layers

```
source  ──▶  raw.*        append-only, one row per record, exactly as sent
              │           every load stamped; nothing ever overwritten
              ▼
            stg.*         typed views — the only place upstream weirdness
              │           is normalised, and it is normalised once
              ▼
            dim_/fct_/mart_   declared grain, tested
              │
              ▼
            the surface   built from marts, published by CI
```

**Raw is append-only and never edited.** If a mart is wrong, the fix is a new
query over the same rows — not a re-fetch, not a mutation. This is what makes
an offline rebuild possible, and an offline rebuild is a *test*: replaying
last month's saved payloads through new SQL found two loader bugs here that
the live path had been hiding for weeks.

**Stamp every load, and make unfinished loads invisible.** Two tables —
`raw.loads` (one row per run) and the records themselves — plus a view that
selects only loads with a `finished_at`. A crashed load leaves rows behind
but no downstream view can see them, so a failed refresh serves last week's
numbers rather than half of this week's. **Stale and correct beats fresh and
wrong**, and that rule should hold at every level of the stack.

**Store the filter that produced a row.** If one endpoint is called several
ways — unfiltered, then with a filter — the filter is part of the row's
identity. Keep a `variant` column. Don't infer later which call a row
came from.

**Normalise in staging, once.** A prior round had six separate `[0]` index
expressions on the same list-typed field scattered across the codebase. Five
of them agreed with each other. The sixth was the bug.

**Prefix marts by grain and test the grain.** `dim_` for lookups, `fct_` for
events or observations, `mart_` for the shaped thing a consumer reads. Put a
uniqueness test on every grain key. A model whose grain you can't state in
one sentence isn't finished.

**Derive nothing twice.** If a quantity is computed in both the warehouse and
the page builder, they will drift. Compute it once, or write a test asserting
the two agree. One such test caught a miscomputation on its first run.

---

## 3. Build a fake source before you trust any test

The single highest-leverage thing in this repo is a file that generates a
synthetic season shaped exactly like the live API — including every quirk the
live API has actually been observed to have:

- the field that is a list here and a string there
- the two names for the same field
- the nested breakdown that looks flat
- the entity that appears in the stats endpoint but is missing from the
  lookup endpoint, standing in for a real partial outage
- the row with a zero denominator, so the divide-by-zero guard stays exercised
- the "absent means zero" case, deliberately left absent

Seed it, so two runs produce identical numbers and tests can assert exact
values.

This buys three things at once: tests that run with no network, a place where
every past bug stays caught forever, and the ability to develop when the
source is unreachable. **Every quirk in the fixture should be traceable to a
real incident.** A fixture full of imagined edge cases is fiction; a fixture
full of remembered ones is a regression suite.

---

## 4. Tests

Two kinds, and they do different jobs.

**Schema tests** — uniqueness on grain keys, not-null on anything joined on,
accepted values on anything with a fixed domain. Cheap, mechanical, and they
catch structural drift.

**Singular tests — name each one for the bug it caught.** Not
`test_players_valid`. Instead:

```
assert_player_splits_reconcile
assert_team_id_arrays_unwrapped
assert_qualification_uses_each_teams_own_games
assert_npxg_is_never_negative
assert_rates_are_null_not_infinite
assert_penalty_absence_means_zero
assert_placement_components_sum
```

The name is the institutional memory. It tells the next person what went
wrong once, and it makes a red test self-explaining at 7am.

**Run the offline tests before spending a single network call.** If the
fixture-based suite fails, the problem is the code, not the source.

---

## 5. The surface

**Default to one self-contained static file.** SVG charts, vanilla JS, no
build step, no dependencies, generated by a script. That's what survives
months of no maintenance and hosts free.

**The title is the deliverable.** "xG vs. xA" is a variable list. "San Diego
is the only club strong at both ends" is a claim someone can disagree with.
Compute every title, blurb and caption in the same pass that draws the chart,
so prose and pixels can never contradict each other.

**Check that your axes are independent.** If `y` is defined as something
minus `x`, then plotting `y` against `x` produces a tidy slope that is pure
arithmetic, and readers will read it as a finding. This shipped in draft
here. Ask before every scatter: *could I compute one axis from the other?*
If yes, plot two measured quantities and let the derived one be distance
from a reference line.

**Answer "is this real?" before "what is it made of?"** Decomposition is only
meaningful once the quantity clears noise. Show the uncertainty band first.

**Add a second surface only for what the first cannot do.**

- *Tableau* — for readers who want to pivot it themselves. Feed it flat CSV
  extracts from the marts, not a live database connection. For a y=x
  reference line: duplicate the x measure as a calculated field, put it on a
  synchronized dual axis, set that marks card to Line, and move the
  identifier from **Detail to Path**. On Detail, every row becomes its own
  one-point line and nothing renders.
- *Shiny or any reactive app* — only if the thresholds become controls.
  Rebuilding the same fixed chart reactively proves nothing. The honest case
  is that every qualification bar on a static page is a judgement call
  someone else already made; the app hands them to the reader.
- Any surface that can fall back to bundled data **must say which source it
  used**. An app that silently shows stale numbers is worse than one that is
  honestly offline.

---

## 6. Automation

**The step order is the contract:**

```
1. offline tests       does the code work at all, against the fixture
2. load + model build  hit the source, then run the data tests
3. rebuild the output  only reached if step 2 passed
4. publish             only reached if step 3 produced a file
```

A failing data test stops the job, the output is not rebuilt, and the live
site keeps serving last week's numbers.

**Exactly one thing publishes.** The moment CI owns the schedule, any local
publish script must be made opt-in behind an explicit flag. Two publishers
means a manual run lands on top of a commit CI already made, and the push is
rejected non-fast-forward. That happened here.

**Pin every dependency.** A run in March should behave like a run in
September. The whole point of the tests is that a behaviour change is
visible, and an unpinned dependency makes "what changed?" unanswerable.

**Serialise runs, don't cancel them.** A concurrency group with
`cancel-in-progress: false` — a half-finished refresh is worse than a late one.

**Keep the evidence.** Upload the raw payloads and the test run results as
build artifacts with a retention window. That is what makes "the tests
passed" checkable by someone who is not you, and it is what lets a bad run
be re-examined without committing megabytes of JSON.

---

## 7. Habits that prevent whole categories of bug

**Prefer the measurement over the inferred rule.** An undocumented field
behaved a certain way in two externally verified cases, and that behaviour
was written into five files as a rule. When all six available cases were
finally tested: three matched, three didn't. If a claim about upstream
behaviour is load-bearing, measure it across every case you have — and if
you can't, encode the uncertainty instead of the guess.

**Any scripted edit must assert it landed.** A string-replacement patch here
printed "wording fixed" when its pattern had matched nothing. A step that
reports success without checking will eventually lie, and you'll debug
downstream of a change that never happened.

**Never read a log through `tail` or `head`.** The real error is usually
several lines above the summary, and `head` on a running script can SIGPIPE
it to death mid-write — after which the next screenshot shows a stale file
and you debug the wrong thing. Both happened here, in the same week. Read
the whole log, or grep for the error.

**The README is part of the deliverable.** A front page describing a version
from three rounds ago is actively misleading: it names retired colors, lists
superseded files, and omits the live URL. When a project gains a surface,
linking it from the top of the README is part of shipping it.

**Numbers in prose need the same checking as numbers in charts.** A post here
claimed 65 data tests. The build says 41. Specific figures are exactly what
a skeptical reader verifies first.

---

## 8. Working agreements

Process rules for how Claude and I work on this together.

- **No git commands through the automation bridge.** Running even `git status`
  in a working tree while a terminal is open elsewhere created an `index.lock`
  collision that took a round to unpick. Claude writes commit scripts; I run
  them. Read-only inspection uses `GIT_OPTIONAL_LOCKS=0 git --no-optional-locks`.
- **Credentials never pass through Claude.** Tokens, secrets and passwords get
  pasted by me, into a console, in a directory outside the repo. Note that
  `.Rhistory` and shell history files are where a pasted credential goes to
  live forever — they belong in `.gitignore` from day one.
- **Publishing is a separate yes.** Pushing to a remote, deploying an app, or
  publishing a workbook is asked before it is done, every time — not inferred
  from an earlier approval.
- **One visible action at a time when driving a GUI.** Reporting internal
  state (XML, file diffs) during a click-by-click walkthrough is noise; the
  instruction should be the thing to click.
- **Verify from the rendered artifact, not the source.** Several real bugs
  existed only in the shipped HTML.

---

## 9. Pre-ship checklist

- [ ] Every mart has a stated grain and a uniqueness test on it
- [ ] Offline fixture tests pass with no network
- [ ] The rendered output was read as a stranger would read it
- [ ] No chart plots a derived quantity against its own component
- [ ] Every specific number in prose was recomputed from the data
- [ ] Every threshold is stated somewhere the reader can find
- [ ] A failed refresh leaves the last good version standing
- [ ] Exactly one thing publishes
- [ ] The README links every live surface

---

## 10. What to copy into the next project

| From here | Portability |
|---|---|
| `sql/010_raw.sql` | Near-verbatim. Rename the records table; the loads/current-load pattern is domain-free. |
| `warehouse_fixture.py` | The *pattern*, not the file. Rewrite the quirks for the new source. |
| `test_warehouse.py` | Structure and naming convention; assertions are domain-specific. |
| `.github/workflows/weekly.yml` | Near-verbatim. Change the load command and the schedule. |
| `dashboard_template.py` | Near-verbatim — it is a generic chart library with no sport in it. |
| `finishing_signal.py` | The math generalises to any small-sample rate statistic. Rename it. |
| `nwsl_warehouse.py` | The CLI shape (`load` / `build` / `tables` / `sql` / `dbt`) transfers; the endpoint list does not. |
| `chart_builders.py` | Domain-specific. Read it for the pattern, don't copy it. |

Start the next project as a script. Graduate it when it earns the warehouse.
