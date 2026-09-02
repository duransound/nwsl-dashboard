# Freeze frames: what a location-only xG model cannot see

A standalone study on **NWSL 2023**, StatsBomb open data. Not part of the
weekly ASA pipeline — StatsBomb's NWSL coverage is 2018 and 2023 only, static,
no live updates.

```
python3 extract.py     # fetches 137 matches, writes shots_2023.csv
python3 model.py       # fits both models, writes shots_2023_modelled.csv
```

## Why

The dashboard's Placement vs. Luck tab splits a player's finishing margin into
shot placement and a residual labelled *everything I could not attribute*.
Some of that residual is not luck at all — it is shot difficulty the model
never saw. ASA's public xG knows where a shot was taken from and how. It does
not know that three defenders were standing in the way.

StatsBomb's open data carries a **freeze frame** on every shot: the position
and role of every visible player at the instant it was struck. 3,490
non-penalty NWSL 2023 shots, all of them with one.

## What the freeze frame is worth, at the shot level

Two logistic models on the same shots, 5-fold cross-validated so both are
scored out of sample:

| model | log loss | AUC |
|---|---:|---:|
| baseline (league conversion rate) | 0.2924 | — |
| **A — location only** (distance, angle, body part, shot type) | 0.2638 | 0.7324 |
| **B — A + defensive context** | 0.2497 | **0.7778** |
| StatsBomb's own xG (reference) | 0.2426 | 0.7884 |

Model A approximates what ASA's published model sees. Adding the freeze frame
closes **about 80% of the gap** between it and StatsBomb's production model.

Standardised coefficients on the defensive block:

```
gk_off_line         +0.457      keeper caught off their line
nearest_defender    +0.259      space around the shooter
defenders_in_cone   -0.341      bodies between ball and goal
gk_lateral_abs      -0.185
under_pressure      -0.096
```

A keeper off their line is the single most valuable thing a shooter can see —
worth more than the number of defenders in front of them.

Raw conversion tells the same story without any model:

| defenders in cone | shots | goals | conversion |
|---:|---:|---:|---:|
| 0 | 1568 | 179 | 11.4% |
| 1 | 1172 | 80 | 6.8% |
| 2 | 468 | 29 | 6.2% |
| 3 | 179 | 11 | 6.1% |
| 4+ | 103 | 0 | 0.0% |

## What it is worth at the player-season level: almost nothing

This is the part worth reporting honestly, because it is the opposite of what
the study was set up to find.

Across the 48 players with 25+ non-penalty shots, the correlation between
"how much defensive context is worth on your shots" and "how much you beat a
location-only model by" is **+0.065** — 0.4% of the variance. Defensive
context does not explain finishing overperformance over a season. Crowding
averages out; every forward takes a mix.

What it does do is move individual verdicts:

| player | shots | goals | margin, location only | margin, with context |
|---|---:|---:|---:|---:|
| Alex Morgan | 59 | 5 | +0.1 | −1.4 |
| Michelle Alozie | 32 | 4 | +1.3 | −0.0 |
| Morgan Weaver | 75 | 7 | +1.0 | −0.0 |
| Cecelia Kizer | 30 | 6 | +2.2 | +0.5 |

Three of those flip sign. They look like neutral-to-good finishers on shot
location alone, and like average-to-below once you credit how clear their
looks were. The swings are small in absolute terms — under two goals across a
season — and with 48 players an r of 0.065 is indistinguishable from zero
rather than proven to be zero.

## Caveats

- StatsBomb NWSL coverage is 2018 and 2023 only. This cannot be compared
  directly to the 2026 placement work: different seasons, different vendors'
  xG models.
- Freeze frames capture *visible* players only — broadcast framing decides who
  is in the frame. Shots where the camera is tight will understate the crowd.
- StatsBomb's own xG runs 9% hot on this sample (299 goals against 328.4 xG),
  which is worth knowing before treating it as ground truth.
- Penalties excluded throughout, per the convention used across this project.

Data: [StatsBomb Open Data](https://github.com/statsbomb/open-data).
