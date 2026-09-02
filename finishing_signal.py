"""
Uncertainty and regression-to-the-mean for goals-minus-xG.

Why this file exists (round 22, 2026-08-13): the dashboard's headline chart
was Goals vs. xG, and every point on it was a bare point estimate. A player
sitting +2.5 goals above their xG over a partial season is, for most realistic
shot volumes, indistinguishable from a league-average finisher who got lucky
-- finishing over expectation is one of the slowest-stabilizing quantities in
the sport. A chart that can't tell those two cases apart shouldn't render them
identically.

Two things are computed here, and they answer two different questions:

1. `noise_sd(xg, shots)` -- "how far from the line does pure chance get you?"
   Under the null hypothesis that a player finishes exactly like the average
   shooter facing their shots, goals is Poisson-binomial: the sum of `shots`
   independent Bernoulli trials with success probabilities equal to each
   shot's xG. Its variance is sum(p_i * (1 - p_i)). ASA's aggregate endpoint
   gives us only the SUM of the p_i (that's what xG is) and the count, not the
   individual values, so this approximates the variance with
   shots * qbar * (1 - qbar) where qbar = xg / shots.

   That approximation is deliberately the conservative direction. For a fixed
   mean, the Poisson-binomial variance is MAXIMIZED when every p_i is equal,
   so substituting the mean shot quality for the individual shot qualities can
   only ever overstate the noise, never understate it. The band this produces
   is therefore slightly too WIDE -- it will occasionally call a real finisher
   "not distinguishable from chance", but it will not manufacture significance
   that isn't there. Given the chart is being used to stop people
   over-reading noise, erring wide is the right error.

2. `estimate_tau2` / `shrink` -- "given that a lot of this is chance, what's
   the best guess at the player's actual finishing skill?" This is an
   empirical-Bayes / James-Stein regression to the mean, with the shrinkage
   strength ESTIMATED FROM THE POOL rather than picked by hand.

   Model: player i has a true finishing offset theta_i, measured in goals
   above expected PER SHOT, drawn from a population with mean 0 and variance
   tau^2. We observe r_i = (goals_i - xg_i) / shots_i, whose sampling variance
   around theta_i is qbar_i * (1 - qbar_i) / shots_i.

   tau^2 is recovered by method of moments, weighted by shot count (an
   unweighted average would be dominated by the wild r_i^2 values of players
   with a handful of shots):

       sum_i n_i * r_i^2  =  tau^2 * sum_i n_i  +  sum_i qbar_i(1 - qbar_i)

   so tau^2 = (sum_i d_i^2 / n_i - sum_i qbar_i(1 - qbar_i)) / sum_i n_i,
   floored at zero. Flooring at zero is not a fudge -- tau^2 estimating
   negative IS the finding: it means the observed spread in finishing across
   the league is no wider than what independent coin flips would produce on
   their own, i.e. there is no measurable finishing-skill signal in this
   sample at all, and the honest best estimate for every player is zero.
   `describe()` says exactly that when it happens rather than hiding it.

   The per-player weight is then w_i = n_i * tau^2 / (n_i * tau^2 +
   qbar_i(1 - qbar_i)), and the regressed estimate is w_i * d_i. Note w_i
   depends on shot count, which is the whole point: a striker with 90 shots
   keeps far more of their raw number than a winger with 12.

Nothing in this file needs the network, a season, or ASA specifically -- it
takes plain numbers, so it is unit-testable and reusable for any xG source.
"""

import math

# Two-sided 95%. Named rather than inlined because the footnote text, the band
# geometry, and the per-player z-flag all have to agree on the same number.
Z95 = 1.959963985


def mean_shot_quality(xg, shots):
    """xG per shot, clamped into [0, 1]. Clamping matters because the
    aggregate endpoints round, and a 1-shot 0.9999-xG row can otherwise
    produce a negative variance a few decimals later."""
    if not shots or shots <= 0:
        return 0.0
    return min(max(xg / shots, 0.0), 1.0)


def noise_sd(xg, shots):
    """Standard deviation of goals scored, under the null that this player
    finishes exactly like the average shooter taking their shots. See the
    module docstring for why this over-states rather than under-states."""
    if not shots or shots <= 0 or xg <= 0:
        return 0.0
    q = mean_shot_quality(xg, shots)
    return math.sqrt(max(xg * (1.0 - q), 0.0))


def z_score(goals, xg, shots):
    """How many standard deviations a player's finishing sits from the line.
    Returns None when there is no shot volume to speak of, rather than a
    fake 0.0 -- a player with 2 shots has no z-score worth printing."""
    sd = noise_sd(xg, shots)
    if sd <= 0:
        return None
    return (goals - xg) / sd


def estimate_tau2(rows, min_shots=1):
    """Population variance of true per-shot finishing skill, by shot-weighted
    method of moments. `rows` is any iterable of dicts carrying "goals",
    "xg" and "shots". Returns 0.0 when the estimate is negative or the pool
    is too thin -- see the module docstring on why that is a result, not a
    failure."""
    num = 0.0
    den = 0.0
    for r in rows:
        n = r.get("shots") or 0
        if n < min_shots or n <= 0:
            continue
        xg = r.get("xg") or 0.0
        d = (r.get("goals") or 0) - xg
        q = mean_shot_quality(xg, n)
        num += (d * d) / n - q * (1.0 - q)
        den += n
    if den <= 0:
        return 0.0
    return max(num / den, 0.0)


def shrink(goals, xg, shots, tau2):
    """Regress one player's goals-minus-xG toward zero. Returns
    (regressed_value, weight_kept). weight_kept is in [0, 1] and is worth
    surfacing on its own -- "we kept 12% of this number" is a more legible
    statement of confidence than the regressed value alone."""
    n = shots or 0
    if n <= 0 or tau2 <= 0:
        return 0.0, 0.0
    q = mean_shot_quality(xg, n)
    noise_per_shot = q * (1.0 - q)
    signal = n * tau2
    if signal + noise_per_shot <= 0:
        return 0.0, 0.0
    w = signal / (signal + noise_per_shot)
    return w * ((goals or 0) - (xg or 0.0)), w


def half_weight_shots(tau2, qbar):
    """Shots at which the regressed estimate keeps half the raw value, at the
    league's average shot quality. This is the single most legible summary of
    "how much volume before finishing means anything" and belongs in the
    footnote. None when tau2 is zero (no volume is ever enough, because
    there is no signal to find)."""
    if tau2 <= 0:
        return None
    q = min(max(qbar, 0.0), 1.0)
    noise_per_shot = q * (1.0 - q)
    if noise_per_shot <= 0:
        return None
    return noise_per_shot / tau2


def pool_summary(rows, min_shots=1):
    """Everything the charts and the Methods tab need about a player pool, in
    one pass: tau2, the league mean shot quality, the half-weight shot count,
    and the median minutes/shot-quality the uncertainty band is drawn for."""
    usable = [r for r in rows if (r.get("shots") or 0) >= min_shots]
    tau2 = estimate_tau2(usable, min_shots=min_shots)
    total_shots = sum((r.get("shots") or 0) for r in usable)
    total_xg = sum((r.get("xg") or 0.0) for r in usable)
    qbar = mean_shot_quality(total_xg, total_shots)

    def _median(values):
        vals = sorted(v for v in values if v)
        if not vals:
            return 0.0
        mid = len(vals) // 2
        if len(vals) % 2:
            return float(vals[mid])
        return (vals[mid - 1] + vals[mid]) / 2.0

    return {
        "n_players": len(usable),
        "tau2": tau2,
        "qbar": qbar,
        "total_shots": total_shots,
        "half_weight_shots": half_weight_shots(tau2, qbar),
        "median_minutes": _median([r.get("minutes") or 0 for r in usable]),
        "median_shot_quality": _median(
            [mean_shot_quality(r.get("xg") or 0.0, r.get("shots") or 0) for r in usable]
        ),
    }


def band_points(x_min, x_max, shot_quality, minutes=None, steps=48, z=Z95):
    """Points for the shaded "indistinguishable from average" ribbon on the
    Goals vs. xG scatter, as [[x, lo, hi], ...].

    Two modes, and the difference between them is the whole reason the
    finishing chart is drawn in season totals rather than per-96 rates:

    COUNT MODE (minutes=None -- what the dashboard uses). x is a season xG
    total and y is season goals. The randomness in goals depends only on the
    shots taken and how good they were, NOT on how many minutes it took to
    take them, so the half-width is simply

        z * sqrt(x * (1 - q))

    and that curve is exact for every player on the chart, up to each
    player's own shot quality differing slightly from the pool median q.
    There is no representative player and no caveat about whose band this is.

    RATE MODE (minutes given). x is xG per 96. The randomness still lives in
    counts, so it has to be converted back: an x of xg96 implies a season
    total of xg96 * minutes / 96, giving a half-width of

        z * sqrt(xg96 * (1 - q) * 96 / minutes)

    which depends on minutes and is therefore correct for exactly one
    player -- a low-minutes player's true band is wider than the drawn one
    and a high-minutes player's is narrower. Kept because it is the right
    shape if a rate-axis version is ever wanted, but any caller using it owes
    the reader a footnote naming whose minutes the ribbon belongs to.

    Both are square-root curves pinned at the origin: proportionally widest
    on the left where the sample is thinnest, tightening as volume grows."""
    if x_max <= 0:
        return []
    if minutes is not None and minutes <= 0:
        return []
    q = min(max(shot_quality, 0.0), 1.0)
    scale = (1.0 - q) if minutes is None else (1.0 - q) * 96.0 / minutes
    lo_x = max(0.0, x_min)
    out = []
    for i in range(steps + 1):
        x = lo_x + (x_max - lo_x) * (i / steps)
        half = z * math.sqrt(max(x, 0.0) * scale)
        out.append([round(x, 5), round(x - half, 5), round(x + half, 5)])
    return out
