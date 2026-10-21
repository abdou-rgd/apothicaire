"""Statistics of the frozen sets, at the exercise level (FROZEN_SET.md §3, §4, §6.3, §11; T-083). Pure Python, no dependency.

The exercise is the unit of inference: turns of one exercise share the data, the memory and the prompt, and numbers of one turn
share one tool result, so neither is an independent trial. Everything here takes one value per exercise.

  upper_bound_zero(n)            one-sided 95 % upper bound when no exercise of n fails: 1 - 0.05^(1/n)
  clopper_pearson(f, n)          exact two-sided 95 % interval of f failures out of n
  failure_interval(f, n)         the one the protocol prints: the bound when f = 0, Clopper-Pearson otherwise
  pass_hat_k(c, n, k)            unbiased estimate of pass^k for one exercise correct on c of n seeds: C(c, k) / C(n, k)
                                 (Yao et al., tau-bench, 2024); pass^n is the strict rule of §6.3 (all seeds)
  cluster_bootstrap(per, ...)    95 % percentile interval of sum(a) / sum(b), exercises resampled (10 000 resamples, seed 0)
  mcnemar_exact(b, c)            two-sided exact McNemar p on the discordant exercises (b: only C1 passes, c: only C2 passes)
  paired_bootstrap_mean(d, ...)  95 % percentile interval of the mean of per-exercise differences, exercises resampled
  sign_flip_test(d, ...)         two-sided randomisation p of the mean of per-exercise differences (10 000 sign flips, seed 0)
"""
import math, random

ALPHA = 0.05
N_BOOT = 10000

def upper_bound_zero(n, alpha=ALPHA):
    """One-sided (1 - alpha) upper bound on the failure probability when 0 of n independent exercises fail."""
    return 1.0 - alpha ** (1.0 / n) if n else None

def _binom_cdf(k, n, p):
    if k < 0: return 0.0
    if k >= n: return 1.0
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))

def _bisect(f, lo=0.0, hi=1.0, it=200):
    """Root of a decreasing function f on [lo, hi] (f(lo) >= 0 >= f(hi))."""
    for _ in range(it):
        mid = (lo + hi) / 2
        if f(mid) > 0: lo = mid
        else: hi = mid
    return (lo + hi) / 2

def clopper_pearson(f, n, alpha=ALPHA):
    """Exact two-sided (1 - alpha) interval [lo, hi] of a binomial proportion with f events out of n."""
    if not n: return None
    lo = 0.0 if f == 0 else _bisect(lambda p: alpha / 2 - (1 - _binom_cdf(f - 1, n, p)))
    hi = 1.0 if f == n else _bisect(lambda p: _binom_cdf(f, n, p) - alpha / 2)
    return [lo, hi]

def failure_interval(f, n, alpha=ALPHA):
    """{"failed", "n", "rate", "interval", "kind"}: with no failure the one-sided bound of §4 ([0, bound]), else Clopper-Pearson."""
    if not n: return {"failed": f, "n": n, "rate": None, "interval": None, "kind": None}
    if f == 0: return {"failed": 0, "n": n, "rate": 0.0, "interval": [0.0, upper_bound_zero(n, alpha)], "kind": "one-sided upper bound 1 - 0.05^(1/n)"}
    return {"failed": f, "n": n, "rate": f / n, "interval": clopper_pearson(f, n, alpha), "kind": "exact Clopper-Pearson, two-sided"}

def pass_hat_k(c, n, k):
    """pass^k of one exercise: the probability that k seeds drawn without replacement from its n are all correct, C(c,k)/C(n,k)."""
    if k > n or k < 1: return None
    return math.comb(c, k) / math.comb(n, k)

def pass_k_curve(correct_per_exercise, n_seeds):
    """{k: mean pass^k over exercises} for k = 1..n_seeds; `correct_per_exercise`: seeds passed per exercise (one int each).
    pass^1 is the mean pass rate over seeds, pass^n the share of exercises passed on every seed (§6.3)."""
    m = len(correct_per_exercise)
    return {k: (sum(pass_hat_k(c, n_seeds, k) for c in correct_per_exercise) / m if m else None) for k in range(1, n_seeds + 1)}

def cluster_bootstrap(per, n_boot=N_BOOT, seed=0):
    """95 % percentile interval of sum(a) / sum(b) over exercises resampled with replacement; `per` = [(a, b)], one per exercise."""
    if len(per) < 2: return None
    rng, vals = random.Random(seed), []
    for _ in range(n_boot):
        s = [per[rng.randrange(len(per))] for _ in per]
        d = sum(x[1] for x in s)
        if d: vals.append(sum(x[0] for x in s) / d)
    vals.sort()
    return [vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]] if vals else None

def mcnemar_exact(b, c):
    """Two-sided exact McNemar test: the discordant exercises are binomial(b + c, 1/2) under no difference."""
    n = b + c
    if n == 0: return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)

def paired_bootstrap_mean(d, n_boot=N_BOOT, seed=0):
    """95 % percentile interval of the mean of the per-exercise differences `d`, exercises resampled with replacement."""
    if len(d) < 2: return None
    rng, vals = random.Random(seed), []
    for _ in range(n_boot):
        vals.append(sum(d[rng.randrange(len(d))] for _ in d) / len(d))
    vals.sort()
    return [vals[int(0.025 * len(vals))], vals[min(len(vals) - 1, int(0.975 * len(vals)))]]

def sign_flip_test(d, n_perm=N_BOOT, seed=0):
    """Two-sided randomisation test of mean(d) = 0: each exercise's difference keeps its size and gets a random sign."""
    if not d: return 1.0
    obs = abs(sum(d))
    rng = random.Random(seed)
    hits = sum(1 for _ in range(n_perm) if abs(sum(x if rng.random() < 0.5 else -x for x in d)) >= obs - 1e-12)
    return (hits + 1) / (n_perm + 1)
