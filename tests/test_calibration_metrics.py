from datetime import datetime, timedelta

import pytest

from src.engine.calibration_metrics import (
    apply_isotonic,
    brier_score,
    dedupe_predictions,
    expected_calibration_error,
    fit_isotonic,
    reliability_table,
    temporal_split,
    wilson_interval,
)


# ── WILSON ────────────────────────────────────────────────────

def test_wilson_empty_is_uninformative():
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_known_value():
    lo, hi = wilson_interval(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3)
    assert hi == pytest.approx(0.7634, abs=1e-3)


def test_wilson_stays_in_unit_range_at_extremes():
    assert wilson_interval(0, 10)[0] == 0.0
    assert wilson_interval(10, 10)[1] == 1.0
    assert 0.6 < wilson_interval(10, 10)[0] < 0.8


def test_wilson_narrows_with_n():
    w10 = wilson_interval(6, 10)
    w1000 = wilson_interval(600, 1000)
    assert (w1000[1] - w1000[0]) < (w10[1] - w10[0]) / 5


# ── SCORING ───────────────────────────────────────────────────

def test_brier_perfect_and_worst():
    assert brier_score([1.0, 0.0], [True, False]) == 0.0
    assert brier_score([1.0, 0.0], [False, True]) == 1.0
    assert brier_score([], []) is None


def test_ece_zero_when_perfectly_calibrated():
    conf = [0.7] * 10
    outcomes = [True] * 7 + [False] * 3
    assert expected_calibration_error(conf, outcomes) == pytest.approx(0.0, abs=1e-9)


def test_ece_overconfident():
    conf = [0.9] * 10
    outcomes = [True] * 5 + [False] * 5
    assert expected_calibration_error(conf, outcomes) == pytest.approx(0.4)


def test_reliability_table_buckets():
    table = reliability_table([0.05, 0.55, 0.58, 0.95], [False, True, False, True])
    assert [r['bucket'] for r in table] == ['0.0-0.1', '0.5-0.6', '0.9-1.0']
    mid = table[1]
    assert mid['n'] == 2 and mid['correct'] == 1 and mid['accuracy'] == 0.5


# ── ISOTONIC ──────────────────────────────────────────────────

def test_isotonic_pools_violators():
    mapping = fit_isotonic([0.1, 0.2, 0.3, 0.4], [True, False, True, True])
    # First two pool to 0.5, then 1.0
    assert mapping == [[0.15, 0.5], [0.35, 1.0]]


def test_isotonic_is_monotone_on_noisy_data():
    conf = [i / 20 for i in range(20)]
    outcomes = [i % 3 == 0 for i in range(20)]
    ys = [y for _, y in fit_isotonic(conf, outcomes)]
    assert ys == sorted(ys)


def test_apply_isotonic_interpolates_and_clamps_ends():
    mapping = [[0.2, 0.1], [0.8, 0.7]]
    assert apply_isotonic(0.5, mapping) == pytest.approx(0.4)
    assert apply_isotonic(0.0, mapping) == 0.1
    assert apply_isotonic(1.0, mapping) == 0.7
    assert apply_isotonic(0.5, []) == 0.5


# ── HYGIENE ───────────────────────────────────────────────────

def _p(ticker, day, hour=0, direction='buy', horizon='1m'):
    return {
        'ticker': ticker,
        'prediction_timestamp': datetime(2026, 1, day, hour),
        'prediction_horizon': horizon,
        'predicted_direction': direction,
    }


def test_dedupe_same_call_same_day():
    preds = [_p('AAPL', 1, 9), _p('AAPL', 1, 15), _p('AAPL', 2), _p('AAPL', 1, 10, 'avoid'),
             _p('AAPL', 1, 11, horizon='1y'), _p('MSFT', 1)]
    unique = dedupe_predictions(preds)
    assert len(unique) == 5
    # Keeps the earliest of the duplicates
    aapl_buy_day1 = [p for p in unique if p['ticker'] == 'AAPL' and p['predicted_direction'] == 'buy'
                     and p['prediction_timestamp'].day == 1 and p['prediction_horizon'] == '1m']
    assert [p['prediction_timestamp'].hour for p in aapl_buy_day1] == [9]


def test_temporal_split_holds_out_newest():
    preds = [_p('X', d) for d in (5, 1, 9, 3, 7, 2, 8, 4, 6, 10)]
    fit, holdout = temporal_split(preds, 0.3)
    assert len(fit) == 7 and len(holdout) == 3
    assert max(p['prediction_timestamp'] for p in fit) < min(p['prediction_timestamp'] for p in holdout)


def test_isotonic_pools_tied_confidences():
    # Same confidence, mixed outcomes → one point at the group's hit rate
    mapping = fit_isotonic([0.7, 0.7, 0.7, 0.7, 0.9, 0.9], [False, True, False, True, True, True])
    assert mapping == [[0.7, 0.5], [0.9, 1.0]]
    assert apply_isotonic(0.7, mapping) == 0.5
