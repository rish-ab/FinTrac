# =============================================================
# src/engine/calibration_metrics.py
#
# FinTrac V3 — pure statistics for the calibration engine.
# No DB, no I/O: everything here takes plain lists so it can be
# unit-tested with synthetic data.
#
# WHAT'S HERE:
#   wilson_interval      — confidence interval for a hit rate
#   brier_score / ece    — how well confidence matches outcomes
#   reliability_table    — per-bucket accuracy vs confidence
#   fit_isotonic         — monotone raw→calibrated confidence map
#   apply_isotonic       — evaluate that map
#   dedupe_predictions   — drop repeat queries of the same call
#   temporal_split       — fit on older data, validate on newer
#
# WHY WILSON?
# With n=10 and 55% accuracy the normal-approximation interval
# is roughly ±30 points and can leave [0, 1]. Wilson stays in
# range and is reliable at the small n this system works with.
#
# WHY ISOTONIC?
# A single multiplicative factor can only scale confidence down
# uniformly. Isotonic regression learns a monotone mapping per
# confidence level, so it can fix overconfidence at the top and
# underconfidence at the bottom at the same time — while still
# preserving the model's ranking of its own calls.
# =============================================================

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple


# ── INTERVALS ─────────────────────────────────────────────────

def wilson_interval(successes: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson score interval for a binomial proportion. (0, 1) when n == 0."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


# ── SCORING ───────────────────────────────────────────────────

def brier_score(confidences: Sequence[float], outcomes: Sequence[bool]) -> Optional[float]:
    """Mean squared error between confidence and 0/1 outcome. Lower is better."""
    if not confidences:
        return None
    return sum((c - float(o)) ** 2 for c, o in zip(confidences, outcomes)) / len(confidences)


def _bin_index(conf: float, n_bins: int) -> int:
    return min(int(conf * n_bins), n_bins - 1)


def reliability_table(
    confidences: Sequence[float],
    outcomes: Sequence[bool],
    n_bins: int = 10,
) -> List[dict]:
    """
    Per-bucket accuracy vs mean confidence, with Wilson intervals.
    Only non-empty buckets are returned.
    """
    bins: Dict[int, List[Tuple[float, bool]]] = {}
    for c, o in zip(confidences, outcomes):
        bins.setdefault(_bin_index(c, n_bins), []).append((c, bool(o)))

    table = []
    for i in sorted(bins):
        rows = bins[i]
        n = len(rows)
        correct = sum(1 for _, o in rows if o)
        lo, hi = wilson_interval(correct, n)
        table.append({
            'bucket': f"{i / n_bins:.1f}-{(i + 1) / n_bins:.1f}",
            'n': n,
            'correct': correct,
            'mean_confidence': round(sum(c for c, _ in rows) / n, 3),
            'accuracy': round(correct / n, 3),
            'accuracy_ci': [round(lo, 3), round(hi, 3)],
        })
    return table


def expected_calibration_error(
    confidences: Sequence[float],
    outcomes: Sequence[bool],
    n_bins: int = 10,
) -> Optional[float]:
    """Sample-weighted mean |accuracy − confidence| across buckets."""
    total = len(confidences)
    if total == 0:
        return None
    return sum(
        row['n'] / total * abs(row['accuracy'] - row['mean_confidence'])
        for row in reliability_table(confidences, outcomes, n_bins)
    )


# ── ISOTONIC REGRESSION ───────────────────────────────────────

def fit_isotonic(
    confidences: Sequence[float],
    outcomes: Sequence[bool],
) -> List[List[float]]:
    """
    Pool-adjacent-violators fit of P(correct | confidence).

    Returns a step map [[x, y], ...] sorted by x, where x is the
    mean raw confidence of a pooled block and y its observed hit
    rate (non-decreasing). Stored as JSON on the profile.
    """
    # Pool identical confidences first: LLMs reuse round values (0.7,
    # 0.75, ...) and PAV over individual tied points would leave several
    # blocks at the same x with different y.
    tied: Dict[float, List[float]] = {}
    for x, y in zip(confidences, outcomes):
        agg = tied.setdefault(float(x), [0.0, 0.0])
        agg[0] += float(y)
        agg[1] += 1.0

    # Each block: [sum_x, sum_y, weight]
    blocks: List[List[float]] = []
    for x in sorted(tied):
        sy, w = tied[x]
        blocks.append([x * w, sy, w])
        while len(blocks) > 1 and (
            # >= also pools ties, keeping the stored map compact
            blocks[-2][1] / blocks[-2][2] >= blocks[-1][1] / blocks[-1][2]
        ):
            sx, sy, w = blocks.pop()
            blocks[-1][0] += sx
            blocks[-1][1] += sy
            blocks[-1][2] += w
    return [[round(sx / w, 4), round(sy / w, 4)] for sx, sy, w in blocks]


def apply_isotonic(raw: float, mapping: Sequence[Sequence[float]]) -> float:
    """Piecewise-linear interpolation through the isotonic map; flat beyond the ends."""
    if not mapping:
        return raw
    if raw <= mapping[0][0]:
        return mapping[0][1]
    if raw >= mapping[-1][0]:
        return mapping[-1][1]
    for (x0, y0), (x1, y1) in zip(mapping, mapping[1:]):
        if x0 <= raw <= x1:
            if x1 == x0:
                return y1
            return y0 + (y1 - y0) * (raw - x0) / (x1 - x0)
    return raw


# ── DATA HYGIENE ──────────────────────────────────────────────

def dedupe_predictions(predictions: List[dict]) -> List[dict]:
    """
    Keep one prediction per (ticker, day, horizon, direction).

    The same user re-running the same query produces identical,
    perfectly correlated outcomes — counting them separately
    inflates n and makes noise look significant.
    """
    seen = set()
    unique = []
    for p in sorted(predictions, key=lambda p: p['prediction_timestamp']):
        key = (
            p['ticker'],
            p['prediction_timestamp'].date(),
            p.get('prediction_horizon'),
            p['predicted_direction'],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def temporal_split(
    predictions: List[dict],
    holdout_fraction: float = 0.3,
) -> Tuple[List[dict], List[dict]]:
    """Oldest (1 − holdout_fraction) for fitting, newest for validation."""
    ordered = sorted(predictions, key=lambda p: p['prediction_timestamp'])
    cut = int(round(len(ordered) * (1 - holdout_fraction)))
    return ordered[:cut], ordered[cut:]


def holdout_improvement(
    holdout: List[dict],
    correct: Callable[[float], float],
) -> Tuple[Optional[float], Optional[float]]:
    """(raw Brier, corrected Brier) on held-out predictions."""
    raw = [p['confidence'] for p in holdout]
    outcomes = [p['is_correct'] for p in holdout]
    return (
        brier_score(raw, outcomes),
        brier_score([correct(c) for c in raw], outcomes),
    )
