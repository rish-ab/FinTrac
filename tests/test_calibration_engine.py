# =============================================================
# tests/test_calibration_engine.py
#
# Unit tests for the pure (no-DB) parts of the calibration engine.
# Each test builds a synthetic prediction set with a KNOWN bias
# and checks that the right detectors fire — and that unbiased
# or too-small sets stay clean.
# =============================================================

from datetime import datetime, timedelta

import pytest

from src.engine.calibration_engine import (
    MIN_ISOTONIC_SAMPLES,
    MIN_SAMPLE_SIZE,
    _calibrate_scope,
    _compute_accuracy_stats,
    _run_bias_detectors,
    _select_calibration_confidence,
    apply_confidence_correction,
    build_calibration_report,
    format_calibration_for_prompt,
)

T0 = datetime(2026, 1, 1)


def _preds(n_correct, n_wrong, direction='buy', confidence=0.7, ret=2.0, start=0):
    """
    n_correct + n_wrong predictions, correct/wrong interleaved so every
    time window has the same mix. Wrong ones get the opposite return.
    """
    out = []
    total = n_correct + n_wrong
    for i in range(total):
        # Spread corrects evenly through the sequence
        correct = int((i + 1) * n_correct / total) > int(i * n_correct / total)
        out.append({
            'ticker': f'T{start + i}',
            'prediction_timestamp': T0 + timedelta(days=start + i),
            'prediction_horizon': '1m',
            'predicted_direction': direction,
            'confidence': confidence,
            'is_correct': correct,
            'actual_return_pct': ret if correct else -ret,
        })
    return out


def _detected(preds):
    return {b for b, _, _ in _run_bias_detectors(_compute_accuracy_stats(preds))}


# ── STATS ─────────────────────────────────────────────────────

def test_stats_empty():
    assert _compute_accuracy_stats([]) == {'total': 0}


def test_stats_basic_counts():
    preds = _preds(6, 4, 'buy') + _preds(5, 5, 'avoid') + _preds(2, 0, 'hold')
    s = _compute_accuracy_stats(preds)
    assert s['total'] == 22
    assert s['buy_count'] == 10 and s['avoid_count'] == 10 and s['hold_count'] == 2
    assert s['accuracy_pct'] == round(13 / 22 * 100, 1)
    assert s['buy_precision'] == pytest.approx(0.6)
    assert s['avoid_precision'] == pytest.approx(0.5)


# ── DETECTORS ─────────────────────────────────────────────────

def test_below_min_sample_detects_nothing():
    # Wildly biased, but too few samples to trust
    preds = _preds(0, MIN_SAMPLE_SIZE - 1, 'buy', confidence=0.95, ret=20)
    assert _detected(preds) == set()


def test_well_calibrated_balanced_set_is_clean():
    preds = (_preds(7, 3, 'buy', confidence=0.7)
             + _preds(7, 3, 'avoid', confidence=0.7))
    assert _detected(preds) == set()


def test_small_gap_is_not_significant():
    # 10 predictions at 80% confidence, 60% accuracy: the old detector
    # flagged this (20-point gap) but the Wilson interval [0.31, 0.83]
    # still contains 0.8 — not enough evidence.
    preds = _preds(3, 2, 'buy', confidence=0.8) + _preds(3, 2, 'avoid', confidence=0.8)
    assert 'OVERCONFIDENCE' not in _detected(preds)


def test_overconfidence_detected_and_factor_matches_ratio():
    # 90% confidence, 50% accuracy, balanced directions, n=20
    preds = (_preds(5, 5, 'buy', confidence=0.9)
             + _preds(5, 5, 'avoid', confidence=0.9))
    biases = {b: f for b, _, f in _run_bias_detectors(_compute_accuracy_stats(preds))}
    assert 'OVERCONFIDENCE' in biases
    assert biases['OVERCONFIDENCE'] == pytest.approx(50 / 90, abs=1e-3)


def test_always_buy_and_wrong_flags_optimism_and_direction():
    preds = _preds(4, 16, 'buy', confidence=0.6)
    found = _detected(preds)
    assert {'OPTIMISM_BIAS', 'DIRECTION_BIAS'} <= found
    assert 'PESSIMISM_BIAS' not in found


def test_mostly_buy_but_buys_are_right_is_not_optimism():
    # Bullish in a rising market is not a bias
    preds = _preds(16, 4, 'buy', confidence=0.75)
    assert 'OPTIMISM_BIAS' not in _detected(preds)


def test_always_avoid_and_wrong_flags_pessimism():
    preds = _preds(4, 16, 'avoid', confidence=0.6)
    assert 'PESSIMISM_BIAS' in _detected(preds)


def test_volatility_underestimation():
    preds = (_preds(2, 8, 'buy', confidence=0.5, ret=15)
             + _preds(2, 8, 'avoid', confidence=0.5, ret=15))
    assert 'VOLATILITY_UNDERESTIMATION' in _detected(preds)


def test_correction_factors_stay_in_unit_range():
    preds = _preds(0, 50, 'buy', confidence=1.0, ret=40)
    for _, magnitude, factor in _run_bias_detectors(_compute_accuracy_stats(preds)):
        assert 0 < factor <= 1.0
        assert magnitude >= 0


# ── SCOPE CALIBRATION WITH HOLDOUT ────────────────────────────

def test_scope_below_min_sample_returns_nothing():
    assert _calibrate_scope(_preds(0, MIN_SAMPLE_SIZE - 1, confidence=0.95)) == []


def test_scope_well_calibrated_returns_nothing_numeric():
    preds = _preds(14, 6, 'buy', confidence=0.7) + _preds(14, 6, 'avoid', confidence=0.7, start=20)
    profiles = _calibrate_scope(preds)
    assert not [p for p in profiles if p['bias_type'] != 'CONFIDENCE_MAP']


def test_scope_persistent_overconfidence_is_activated():
    preds = (_preds(10, 10, 'buy', confidence=0.9)
             + _preds(10, 10, 'avoid', confidence=0.9, start=20))
    profiles = {p['bias_type']: p for p in _calibrate_scope(preds)}
    assert 'OVERCONFIDENCE' in profiles
    details = profiles['OVERCONFIDENCE']['details']
    assert details['holdout_brier_corrected'] <= details['holdout_brier_raw']
    assert details['holdout_n'] == 12


def test_scope_bias_that_disappears_in_holdout_is_rejected():
    # Oldest 70%: overconfident (90% conf, 30% right).
    # Newest 30%: 90% conf and always right — shrinking would hurt.
    old = _preds(8, 20, 'buy', confidence=0.9) + _preds(0, 0)
    new = _preds(12, 0, 'avoid', confidence=0.9, ret=5, start=28)
    profiles = _calibrate_scope(old + new)
    assert 'OVERCONFIDENCE' not in {p['bias_type'] for p in profiles}


def test_scope_isotonic_map_fixes_mis_scaled_confidence():
    # Ranking is right (0.95 calls beat 0.6 calls) but the numbers are
    # wrong: 0.95 → 60% hit rate, 0.6 → 20%. No single factor maps both
    # (0.95·k = 0.6 gives 0.6·k ≈ 0.38, not 0.2); the isotonic map can.
    hi = _preds(12, 8, 'buy', confidence=0.95)
    lo = _preds(4, 16, 'avoid', confidence=0.6, start=20)
    # Interleave so both levels appear in fit and holdout windows
    preds = [p for pair in zip(hi, lo) for p in pair]
    for i, p in enumerate(preds):
        p['prediction_timestamp'] = T0 + timedelta(days=i)
    assert len(preds) >= MIN_ISOTONIC_SAMPLES
    profiles = {p['bias_type']: p for p in _calibrate_scope(preds)}
    assert 'CONFIDENCE_MAP' in profiles
    mapping = profiles['CONFIDENCE_MAP']['details']['isotonic_map']
    ys = [y for _, y in mapping]
    assert ys == sorted(ys)


# ── CONFIDENCE SOURCE (raw vs corrected) ──────────────────────

def test_prefers_raw_confidence():
    assert _select_calibration_confidence(0.8, 0.5, {'calibration_corrections_active': 2}) == 0.8


def test_legacy_row_without_corrections_uses_stored():
    assert _select_calibration_confidence(None, 0.7, {'calibration_corrections_active': 0}) == 0.7
    assert _select_calibration_confidence(None, 0.7, None) == 0.7


def test_legacy_row_with_corrections_is_skipped():
    # Stored score was already corrected — calibrating on it is circular
    assert _select_calibration_confidence(None, 0.5, {'calibration_corrections_active': 3}) is None


# ── APPLYING CORRECTIONS ──────────────────────────────────────

def _profile(scope, factor, bias='X', details=None):
    return {'scope': scope, 'bias_type': bias, 'correction_factor': factor,
            'magnitude': 0.1, 'sample_size': 20, 'confidence_interval': details or {}}


def test_no_profiles_returns_raw():
    assert apply_confidence_correction(0.8, []) == 0.8


def test_corrections_do_not_compound():
    # Two biases in the same scope: strongest wins, no 0.8*0.7 product
    profiles = [_profile('global', 0.8), _profile('global', 0.7)]
    assert apply_confidence_correction(0.9, profiles) == pytest.approx(0.63)


def test_most_specific_scope_wins():
    profiles = [
        _profile('global', 0.5),
        _profile('class:EQUITY', 0.6),
        _profile('sector:Technology', 0.9),
    ]
    assert apply_confidence_correction(0.8, profiles) == pytest.approx(0.72)
    assert apply_confidence_correction(0.8, profiles[:2]) == pytest.approx(0.48)


def test_isotonic_map_takes_precedence_over_factors():
    profiles = [
        _profile('global', 0.5, 'OVERCONFIDENCE'),
        _profile('global', 0.9, 'CONFIDENCE_MAP',
                 {'isotonic_map': [[0.3, 0.8], [0.9, 0.5]]}),
    ]
    # Map is flat beyond its ends: raw 0.95 → 0.5, not 0.95 * 0.5
    assert apply_confidence_correction(0.95, profiles) == pytest.approx(0.5)


def test_correction_clamped_to_floor():
    assert apply_confidence_correction(0.15, [_profile('global', 0.5)]) == 0.1


def test_prompt_does_not_ask_model_to_apply_factor():
    # The factor is applied in code; telling the LLM too double-corrects
    text = format_calibration_for_prompt([_profile('global', 0.7, 'OVERCONFIDENCE')])
    assert 'correction factor' not in text.lower()
    assert '0.7' not in text


def test_prompt_omits_confidence_map():
    assert format_calibration_for_prompt([_profile('global', 0.9, 'CONFIDENCE_MAP')]) == ''


# ── REPORT ────────────────────────────────────────────────────

def test_report_empty():
    assert build_calibration_report([]) == {'n': 0}


def test_report_contents():
    preds = _preds(6, 4, 'buy', confidence=0.8) + _preds(3, 2, 'hold', confidence=0.6, start=10)
    for p in preds:
        p['shown_confidence'] = p['confidence'] * 0.9
    r = build_calibration_report(preds)
    assert r['n'] == 15
    assert r['by_action']['BUY']['n'] == 10 and r['by_action']['BUY']['correct'] == 6
    assert r['by_action']['AVOID']['n'] == 0
    assert r['by_horizon']['1m']['n'] == 15
    lo, hi = r['accuracy']['ci']
    assert lo < r['accuracy']['rate'] < hi
    assert r['brier_raw'] != r['brier_shown']
