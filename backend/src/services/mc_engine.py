import numpy as np
from scipy.stats import random_table, norm
from .diagnostics import independence_diagnostics

# Conditional Monte Carlo test with fixed row/column margins (Patefield r x c algorithm).
# Pure functions only: no DB / queue access so every stopping rule is unit-testable.
Z99 = float(norm.ppf(0.995))          # 99% two-sided normal quantile for Wilson intervals
EPS_TOL = 1e-12
CONFIDENCE = 0.99
BH_ALPHA = 0.05
MIN_DRAWS = 100
MAX_DRAWS_LIMIT = 10_000_000
BATCH_MIN, BATCH_MAX = 10, 100_000
EPS_MIN, EPS_MAX = 0.0001, 0.1
DEGENERATE_BATCHES = 2                # confirm a single-support table over two independent batches


def active_table(table):
    """Drop zero-margin rows/columns exactly like the CA pipeline; return active table and keep masks."""
    X = np.asarray(table, dtype=np.int64)
    if X.ndim != 2 or min(X.shape) < 2 or max(X.shape) > 12:
        raise ValueError('列联表须2..12行列的矩阵')
    if (X < 0).any() or not np.equal(X, np.floor(X)).all():
        raise ValueError('列联表须非负整数矩阵')
    n = int(X.sum())
    if n <= 0:
        raise ValueError('总计数为零，无法条件抽样')
    keep_r = X.sum(axis=1) > 0
    keep_c = X.sum(axis=0) > 0
    A = X[np.ix_(keep_r, keep_c)]
    if min(A.shape) < 2:
        raise ValueError('剔除零边际后至少需要2个有效行和列')
    return A, keep_r, keep_c, n


def reference_quantities(A):
    """Observed chi-square, expected counts and |adjusted standardized residual| on the active table."""
    X = A.astype(float)
    n = float(X.sum())
    r = X.sum(axis=1) / n
    c = X.sum(axis=0) / n
    expected = n * np.outer(r, c)
    delta = X - expected
    chi = float(np.sum(delta * delta / expected))
    # adjusted standardized residual (Haberman); sqrt(E*(1-r_i)*(1-c_j)) is always > 0 on the active table
    adj = np.abs(delta / np.sqrt(expected * (1 - r[:, None]) * (1 - c[None, :])))
    return chi, expected, adj


def child_seed(base_seed, batch_index):
    """Deterministic, well-spaced independent stream per batch index.

    The stream depends only on (base_seed, batch_index), never on arrival order, so parallel /
    re-dispatched / duplicated batches reproduce exactly the same draws as one sequential run.
    """
    return np.random.SeedSequence(entropy=[int(base_seed), int(batch_index)])


def simulate_batch(A, batch_index, base_seed, size):
    """One fixed-margin batch. Returns (overall_extreme_count, cell_extreme_matrix, distinct_tables)."""
    row_margins = A.sum(axis=1).copy()
    col_margins = A.sum(axis=0).copy()
    obs_chi, expected, obs_adj = reference_quantities(A)
    rng = np.random.default_rng(child_seed(base_seed, batch_index))
    sims = random_table(row_margins, col_margins).rvs(size=int(size), random_state=rng).astype(np.float64)
    delta = sims - expected
    sim_chi = np.sum(delta * delta / expected, axis=(1, 2))
    overall_extreme = int(np.sum(sim_chi >= obs_chi - EPS_TOL))
    r = row_margins.astype(float) / row_margins.sum()
    c = col_margins.astype(float) / col_margins.sum()
    denom = np.sqrt(expected * (1 - r[:, None]) * (1 - c[None, :]))
    sim_adj = np.abs(delta / denom)
    cell_extreme = np.sum(sim_adj >= (obs_adj - EPS_TOL), axis=0).astype(np.int64)
    distinct = len({s.tobytes() for s in sims.astype(np.int64)})
    return overall_extreme, cell_extreme, distinct


def wilson(x, n, z=Z99):
    """Wilson score interval for the raw binomial proportion x/n; returns (p_hat_add1, low, high, half_width)."""
    n = int(n)
    p_hat = (int(x) + 1) / (n + 1)
    if n == 0:
        return p_hat, 0.0, 1.0, 1.0
    k = int(x)
    den = 1 + z * z / n
    center = (k + z * z / 2) / (n * den)
    half = z * np.sqrt(max(0.0, (k / n) * (1 - k / n) + z * z / (4 * n)) / n) / den
    return p_hat, max(0.0, center - half), min(1.0, center + half), float(half)


def benjamini_hochberg(p_values, alpha=BH_ALPHA):
    """Step-up BH FDR control. Returns adjusted p-values and rejection flags on the input order."""
    p = np.asarray(p_values, dtype=float)
    k = len(p)
    order = np.argsort(p, kind='stable')
    ranked = p[order]
    adjusted = np.empty(k)
    prev = 1.0
    for m in range(k - 1, -1, -1):
        prev = min(prev, ranked[m] * k / (m + 1))
        adjusted[order[m]] = min(prev, 1.0)
    cutoff_rank = -1
    for m in range(k):
        if ranked[m] <= alpha * (m + 1) / k:
            cutoff_rank = m
    rejected = np.zeros(k, dtype=bool)
    if cutoff_rank >= 0:
        rejected[order[: cutoff_rank + 1]] = True
    return adjusted, rejected


def worst_half_width(n, z=Z99):
    """Conservative Wilson half-width bound maximised over x in [0,n] (near p=.5)."""
    n = int(n)
    if n == 0:
        return 1.0
    den = 1 + z * z / n
    return float(z * np.sqrt(0.25 + z * z / (4 * n)) / np.sqrt(n) / den)


def precision_reached(n, epsilon):
    return n >= MIN_DRAWS and worst_half_width(n) <= float(epsilon)


def meets_requirements(n, epsilon, min_draws):
    """Stop only when both the hard floor, the user's minimum and the epsilon guarantee hold."""
    return n >= max(MIN_DRAWS, int(min_draws)) and worst_half_width(n) <= float(epsilon)


def stopping_plan(max_draws, epsilon, min_draws=MIN_DRAWS):
    """Smallest draw count satisfying both the user minimum and epsilon, capped by budget."""
    n = max(MIN_DRAWS, int(min_draws))
    while n < max_draws and worst_half_width(n) > float(epsilon):
        n += 1
    return min(max_draws, n)


def build_inference(state, A, epsilon, max_draws, min_draws=MIN_DRAWS):
    """Assemble the reportable result from accumulated counters. Never fabricates significance."""
    n = int(state['draws'])
    overall_x = int(state['overall_extreme'])
    cell_x = np.asarray(state['cell_extreme'], dtype=np.int64)
    obs_chi, expected, obs_adj = reference_quantities(A)
    p_overall, lo, hi, half = wilson(overall_x, n)
    flat_p = np.array([wilson(x, n)[0] for x in cell_x.flatten()])
    adjusted, rejected = benjamini_hochberg(flat_p)
    rows, cols = A.shape
    cells = []
    flat_idx = 0
    for i in range(rows):
        for j in range(cols):
            ph, clo, chi_, chalf = wilson(int(cell_x[i, j]), n)
            cells.append({
                'row_index': i, 'column_index': j,
                'observed': int(A[i, j]), 'expected': float(expected[i, j]),
                'adjusted_residual_abs': float(obs_adj[i, j]),
                'extreme_count': int(cell_x[i, j]),
                'p_value': ph, 'p_ci_low': clo, 'p_ci_high': chi_, 'p_half_width': chalf,
                'bh_adjusted_p': float(adjusted[flat_idx]),
                'verdict': 'reject' if rejected[flat_idx] else 'no_reject',
            })
            flat_idx += 1
    guaranteed = meets_requirements(n, epsilon, min_draws)
    budget_exhausted = n >= max_draws
    if state.get('degenerate'):
        decision = 'succeeded'
        stop_reason = 'single_support_table'
        conclusion = '固定边际下只有一种可能表格：条件分布退化，检验无随机证据，不作显著性结论。'
    elif guaranteed:
        decision = 'succeeded'
        stop_reason = 'precision_met'
        conclusion = '达到约定精度，整体与逐格判断在99%置信区间保障内有效。'
    elif budget_exhausted:
        decision = 'indeterminate'
        stop_reason = 'budget_exhausted'
        conclusion = '抽样预算耗尽仍未达到约定精度：结论未定，仅报告当前估计与实际置信区间。'
    else:
        decision = 'indeterminate'
        stop_reason = 'interrupted'
        conclusion = '检验中断且未达精度：结论未定，恢复后按同种子继续抽样。'
    diag = independence_diagnostics(A.astype(float))
    return {
        'decision': decision,
        'stop_reason': stop_reason,
        'conclusion': conclusion,
        'precision_guaranteed': bool(guaranteed),
        'budget_exhausted': bool(budget_exhausted),
        'confidence_level': CONFIDENCE,
        'bh_fdr': BH_ALPHA,
        'epsilon_target': float(epsilon),
        'effective_draws': n,
        'target_draws': stopping_plan(max_draws, epsilon, min_draws),
        'worst_case_half_width': worst_half_width(n),
        'overall': {
            'observed_chi_square': obs_chi,
            'extreme_count': overall_x,
            'p_value': p_overall, 'p_ci_low': lo, 'p_ci_high': hi, 'p_half_width': half,
            'asymptotic_p_value': diag['p_value'],
            'asymptotic_reliable': diag['asymptotic_reliable'],
            'verdict': 'reject' if p_overall < BH_ALPHA else 'no_reject',
        },
        'cells': cells,
        'expected': expected.tolist(),
        'asymptotic_diagnostics': diag,
    }
