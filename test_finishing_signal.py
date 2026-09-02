"""
Tests for finishing_signal.py. Run with `python3 test_finishing_signal.py`
(no pytest needed, no network needed).

These exist because the uncertainty and regression math is the one part of
this kit that cannot be checked by looking at the rendered page. A chart that
is drawing the wrong band looks exactly like a chart that is drawing the right
one -- the only way to know is to feed the estimator data whose true answer is
known in advance and check that it comes back.

The recovery test is the important one: it simulates leagues with a KNOWN
amount of real finishing skill, runs the estimator on them, and asserts it
recovers roughly that amount -- and, critically, that it recovers ~zero when
there is no skill to find. An estimator that reports signal in pure noise
would put a confident, wrong number on every player's row.
"""

import math
import random

import finishing_signal as fs


def simulate_pool(true_tau, n_players=250, seed=None):
    """A league where every player's finishing skill is drawn from a known
    distribution, and their goals are then actually simulated shot by shot."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n_players):
        shots = max(3, int(rng.lognormvariate(2.9, 0.8)))
        q = min(max(rng.gauss(0.11, 0.03), 0.02), 0.35)
        theta = rng.gauss(0.0, true_tau)
        goals = sum(1 for _ in range(shots)
                    if rng.random() < min(max(q + theta, 0.001), 0.99))
        rows.append({"shots": shots, "xg": shots * q, "goals": goals,
                     "minutes": int(shots * rng.uniform(28, 60))})
    return rows


def approx(a, b, tol):
    return abs(a - b) <= tol


def test_noise_sd_matches_binomial():
    # 100 shots at 0.10 xG each: sd = sqrt(n p (1-p)) = sqrt(100*0.1*0.9) = 3.
    assert approx(fs.noise_sd(10.0, 100), 3.0, 1e-9), fs.noise_sd(10.0, 100)
    # No shots, no uncertainty -- and no division by zero.
    assert fs.noise_sd(0.0, 0) == 0.0
    assert fs.z_score(0, 0.0, 0) is None


def test_z_score():
    assert approx(fs.z_score(15, 10.0, 100), 5.0 / 3.0, 1e-9)
    assert approx(fs.z_score(5, 10.0, 100), -5.0 / 3.0, 1e-9)


def test_shot_quality_clamped():
    # Rounding in the source can produce xg > shots; that must not become a
    # negative variance under the sqrt.
    assert fs.mean_shot_quality(1.4, 1) == 1.0
    assert fs.noise_sd(1.4, 1) == 0.0


def test_tau2_is_zero_when_there_is_no_skill():
    """The single most important property: a league of identical finishers
    must not produce a signal. Averaged over several simulated seasons the
    estimate should sit at essentially zero."""
    ests = [fs.estimate_tau2(simulate_pool(0.0, seed=s)) for s in range(15)]
    mean_tau = sum(math.sqrt(e) for e in ests) / len(ests)
    assert mean_tau < 0.012, f"found signal in pure noise: tau={mean_tau:.4f}"


def test_tau2_recovers_real_skill():
    """And the converse: when the skill really is there, it must be found,
    not regressed away."""
    ests = [fs.estimate_tau2(simulate_pool(0.05, seed=100 + s)) for s in range(10)]
    mean_tau = sum(math.sqrt(e) for e in ests) / len(ests)
    assert approx(mean_tau, 0.05, 0.015), f"recovered tau={mean_tau:.4f}, expected ~0.05"


def test_shrinkage_increases_with_volume():
    """A player with more shots must keep more of their raw margin. This is
    the whole reason the regression is shot-weighted rather than a flat
    multiplier."""
    tau2 = 0.002
    weights = []
    for shots in (10, 40, 90, 200):
        _, w = fs.shrink(goals=shots * 0.11 + 3, xg=shots * 0.11, shots=shots, tau2=tau2)
        weights.append(w)
    assert weights == sorted(weights), weights
    assert 0.0 < weights[0] < 0.3, weights[0]
    assert weights[-1] > 0.6, weights[-1]


def test_zero_tau2_regresses_everything_to_zero():
    value, weight = fs.shrink(goals=9, xg=4.0, shots=50, tau2=0.0)
    assert value == 0.0 and weight == 0.0
    assert fs.half_weight_shots(0.0, 0.11) is None


def test_shrunk_value_never_exceeds_raw():
    """Regression must move estimates toward zero, never past it and never
    away from it -- a sign flip or an inflated value would be a hard bug."""
    tau2 = fs.estimate_tau2(simulate_pool(0.04, seed=7))
    for row in simulate_pool(0.04, seed=8):
        raw = row["goals"] - row["xg"]
        val, w = fs.shrink(row["goals"], row["xg"], row["shots"], tau2)
        assert 0.0 <= w <= 1.0, w
        assert abs(val) <= abs(raw) + 1e-9, (val, raw)
        assert val * raw >= -1e-12, (val, raw)  # same sign, or zero


def test_band_count_mode_is_exact():
    """In count mode the band must equal each player's own 95% interval --
    that is the entire justification for plotting the finishing chart in
    season totals instead of per-96 rates."""
    q = 0.11
    pts = fs.band_points(0.0, 20.0, q)
    for x, lo, hi in pts:
        expected = fs.Z95 * math.sqrt(x * (1 - q))
        assert approx(hi - x, expected, 1e-4), (x, hi - x, expected)
        assert approx(x - lo, expected, 1e-4)


def test_band_widens_with_x_and_is_pinned_at_origin():
    pts = fs.band_points(0.0, 20.0, 0.11)
    widths = [hi - lo for _, lo, hi in pts]
    assert widths == sorted(widths)
    assert approx(widths[0], 0.0, 1e-9)


def test_band_rate_mode_shrinks_with_minutes():
    """Rate mode is kept for completeness; more minutes must mean a tighter
    per-96 band, since the same rate is then backed by more evidence."""
    narrow = fs.band_points(0.0, 1.0, 0.11, minutes=2400)
    wide = fs.band_points(0.0, 1.0, 0.11, minutes=600)
    assert (narrow[-1][2] - narrow[-1][1]) < (wide[-1][2] - wide[-1][1])


def test_band_degenerate_inputs():
    assert fs.band_points(0.0, 0.0, 0.11) == []
    assert fs.band_points(0.0, 10.0, 0.11, minutes=0) == []


def test_pool_summary_shape():
    s = fs.pool_summary(simulate_pool(0.03, seed=3))
    for key in ("n_players", "tau2", "qbar", "total_shots",
                "half_weight_shots", "median_minutes", "median_shot_quality"):
        assert key in s, key
    assert s["n_players"] == 250
    assert 0.0 < s["qbar"] < 0.4
    assert fs.pool_summary([])["tau2"] == 0.0


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  pass  {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
