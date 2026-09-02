# Tableau Public

Three vizzes, built from the warehouse rather than from raw API pulls. That
distinction is the point: the marts already encode non-penalty totals, the
games-scaled qualification bar and the placement split, so Tableau inherits
those definitions instead of re-implementing them in calculated fields where
they would drift from the dashboard.

```
python3 export_extracts.py --db nwsl_dw.duckdb --season 2026
```

Three CSVs, refreshed after any `nwsl_warehouse.py load`. Tableau Public reads
CSV natively — no driver, no extract API. The ones in this folder are already
built from the 2026 payloads, so you can open Tableau and start.

## Before you build: the rules that make these look like one family

From the project's Design Guidelines. Tableau will fight you on all four.

| | |
|---|---|
| Emphasis colour | Amber `#C98A2E` — one mark per viz, everything else `#9aa5b1` |
| Negative | Red `#e34948` |
| Title | states the finding, not the metric. Not "xG Difference by Team" |
| Chartjunk | no borders, no gradients, no default blue-orange diverging ramp |

Tableau's defaults are the opposite of every one of these. Turning them off is
most of the work, and doing it deliberately is the part worth showing.

---

## 1. Team xG Difference — a diverging bar

**Data:** `nwsl_2026_teams.csv`

1. `Team` → Rows. `xG Difference` → Columns.
2. Sort Rows descending by `xG Difference` (click the sort icon on the axis).
3. Colour: drag `xG Difference` → Colour, edit → **Stepped Colour, 2 steps**,
   centred on 0, custom diverging Amber `#C98A2E` / Red `#e34948`.
   Do not keep the default ramp.
4. Add a reference line at 0, thin, grey.
5. Format → Lines → turn **off** row gridlines, column gridlines, zero lines,
   and the axis rulers.
6. Title: `Chicago is being outchanced by 32 expected goals` — the finding.
   Edit it whenever the data moves; that is the convention, not a one-off.

**What this one demonstrates:** you can impose a design system on a tool whose
defaults resist it.

---

## 2. League Picture — a quadrant scatter

**Data:** `nwsl_2026_league_picture.csv`

1. `xG For` → Columns, `xG Against` → Rows, `Team` → Detail. Marks: Circle.
2. Analytics pane → **Average Line** on each axis, constant, thin grey.
   Those two lines are the quadrants; do not draw boxes.
3. **Reverse the `xG Against` axis** (Edit Axis → Reversed). Up should mean
   good. A reader should never have to remember that down is better.
4. `Team` → Label, and only the label — no tooltip decoration needed.
5. Colour: one calculated field —
   `IF [Team] = "SD" THEN "story" ELSE "rest" END` — Amber and grey.

**What this one demonstrates:** quadrant reading, and an axis flipped for the
reader rather than for the data.

---

## 3. Placement vs. Luck — the one that is actually yours

**Data:** `nwsl_2026_placement.csv`

1. `Placement` → Columns, `Margin` → Rows, `Player` → Detail.
2. Calculated field `Reference` = `[Placement]` → drag to Rows as a second
   measure → **Dual Axis** → synchronise → change its mark type to Line.
   That is the y = x diagonal. Format it dashed and grey.
   *(Tableau has no first-class y=x line; this is the standard workaround and
   worth knowing.)*
3. Filter `Shots` ≥ 10 and `|Margin|` ≥ 1.5 — same cuts as the dashboard tab,
   for the same reason: 130 players inside a goal of expectation are a cloud,
   not a finding.
4. Highlight the top margin in Amber; everything else grey.
5. Title: `Ashley Sanchez leads the league in goals above expectation, and
   almost none of it is placement.`

**What this one demonstrates:** a calculated field doing real work, and a viz
that argues something rather than displaying something.

---

## Installing

Tableau Desktop **Public Edition** — the free authoring app, not the trial.

1. https://public.tableau.com → **Download Tableau Desktop Public Edition**
2. Free account (email) to publish. You can author without one.
3. macOS **Ventura or newer**; Apple Silicon is natively supported, no
   Rosetta. Needs about 2 GB free.

You can save workbooks **locally as .twbx** as well as publishing them —
Tableau's docs are explicit that Public Edition does both. But anything you
publish to your profile is public, permanently and immediately, so keep
private data out of a workbook you intend to post.

## Publishing

1. Server → Tableau Public → Save to Tableau Public As…
2. Sign in (free account).
3. On your profile, set each viz's thumbnail and description.
4. Link the profile from your résumé and from the dashboard's footer.

The profile URL is the credential. A screener filters on the word "Tableau";
what convinces the human who opens it is that three vizzes look like one
system and each says something.
