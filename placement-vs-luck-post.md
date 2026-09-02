# The best finisher in the NWSL isn't finishing especially well

Ashley Sanchez has scored 14 non-penalty goals this season from chances worth
9.03. That margin — plus 4.97 goals above expectation — is the largest in the
league. By the standard measure, she is the best finisher in the NWSL.

The standard measure can't tell you whether that's a skill.

Goals minus expected goals is a single number doing two jobs. It counts the
shots a player buried that an average shooter would have missed, and it counts
every keeper who fumbled, every deflection that fell kindly, every post that
went in instead of out. Those are different things. One of them is worth
scouting; the other is worth waiting out.

American Soccer Analysis publishes a field that separates them. As far as I can
tell, almost nobody uses it — including ASA, in any public writing I could
find.

## A field nobody documents

The field is called `xplace`. It appears on every row of the `players/xgoals`
endpoint, and it is not defined anywhere: not in ASA's expected-goals
explainer, not in the xGoals 2.0 methodology post, not in the API docs, not in
the `itscalledsoccer` wrappers.

What the explainer *does* say is that ASA's shot model takes goal-mouth
placement as an input — "the ball's height and distance from the center of the
goal mouth," used to "rate keepers' abilities to make difficult saves, as well
as identify shooters' placement tendencies." So the model knows where the ball
went. What it publishes under `xplace` is a reasonable guess away, but a guess
is not a method, so I checked.

Across every qualifying shooter in the 2026 season so far:

```
goals                    443.00
xgoals                   475.92     goals − xgoals            = −32.92
xgoals + xplace          434.20     goals − (xgoals + xplace) =  +8.80
```

Adding `xplace` to `xgoals` closes 73% of the gap between what the model
expected and what actually happened. That is what a placement term should do to
a pre-shot model, and it is not what an unrelated quantity would do. It
correlates 0.57 with the finishing margin across 227 shooters — clearly
related, clearly not the same number. Its per-shot average is −0.010, so it
behaves like an increment rather than a level.

I'm reading it as the goals-worth of where a player's shots ended up in the
goal mouth, relative to an average placement from those same chances. If ASA
means something else by it, I'd genuinely like to know.

That reading gives you an arithmetic split. A player's finishing margin is
placement plus everything placement doesn't explain:

```
(goals − xG)  =  placement  +  everything else
```

## Same margin, different reasons

Non-penalty, 2026 season to date, minimum ten shots:

| Player | Team | Margin | Placement | Everything else |
|---|---|---:|---:|---:|
| Ashley Sanchez | North Carolina | +4.97 | **−0.15** | +5.12 |
| Janine Sonis | Denver | +4.65 | +1.80 | +2.85 |
| Trinity Byars | San Diego | +3.62 | +0.68 | +2.94 |
| Barbra Banda | Orlando | +3.55 | +0.38 | +3.18 |
| Katherine Rader | Houston | +2.88 | **+2.19** | +0.70 |
| Jordynn Dudley | Gotham | −2.70 | +1.18 | **−3.88** |

Sanchez leads the league on the headline number and places her shots very
slightly *worse* than average. Every one of those 4.97 goals is coming from
somewhere other than her aim.

Katherine Rader's margin is smaller — plus 2.88, fifth in the league — and
three-quarters of it is placement. On the standard leaderboard she looks like a
lesser version of Sanchez. On this one she is doing a different thing entirely,
and doing the part you'd bet on repeating.

Then there's Jordynn Dudley, who is the most interesting name on the list.
She's 2.70 goals *below* expectation, which on any finishing chart makes her a
striker having a bad season. But her placement is +1.18 — better than all but a
handful of players in the league. Everything she can control, she is doing
well. The residual, −3.88, is the worst in the NWSL.

If you believe placement is more repeatable than deflections and keeper errors
— and it should be, since one is a decision and the other two are weather —
then Dudley is the buy-low case of the season and Sanchez is the sell-high one.

## The part where I argue against myself

Sanchez's entire margin sits inside her own chance band.

Given 77 shots at her average shot quality, a perfectly average finisher lands
within ±5.53 goals of expectation 95% of the time by luck alone. Her +4.97 is
inside that. So is most of this table. Finishing is a famously noisy statistic,
and a season is not very many shots.

That doesn't make the split useless — it makes it a different question.
"Is this margin real?" is answered by the chance band, and for most of these
players the answer is *not yet*. "Given a margin, what is it made of?" is
answered by the placement split, and that answer is available now. Rader's
+2.19 of placement is a claim about 41 shots she actually took, not a
projection.

The two questions want to be asked in that order, and I'd be wary of anyone —
including me — who shows you the second without the first.

The other honest caveat: the residual is not a skill measure and I'm not
treating it as one. It's a bucket labelled *everything I could not attribute*.
Some of what's in there is keeper quality, which is real and belongs to the
keeper. Some is shot selection the model hasn't captured. Most of it is noise.

## Where this lives

The split is now a tab on my NWSL dashboard, rebuilt every Tuesday from ASA's
API: **duransound.github.io/nwsl-dashboard** → *Placement vs. Luck*. All 134
qualifying players are in the table under the chart, including the ones inside
the 1.5-goal cut that keeps the plot readable.

The pipeline behind it is public too, and boring on purpose: raw API responses
land in DuckDB untouched, a dbt project models them, and 41 data tests have to
pass before anything reaches the site. One of those tests exists because it
caught me computing the placement split two different ways in two different
places, on the first run, before it ever went out.

Which is the other reason to write this down. The finding is only worth as much
as the plumbing under it, and the plumbing is the part you can check.

---

*Data: [American Soccer Analysis](https://www.americansocceranalysis.com/).
Non-penalty figures throughout — a penalty is roughly 0.75 xG and measures who
takes them, not who finishes well. Season to date, 2026.*
