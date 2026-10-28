# =============================================================
# tests/test_checkpoints.py
#
# Checkpoint predictions (1m companions of long-horizon calls) and
# the calibration run's rule of keeping existing profiles when no
# scope has enough data to re-test them.
# =============================================================

from datetime import datetime, timedelta

import pytest

from src.db.v3_models import PredictionRecord
from src.engine import calibration_engine
from src.engine.calibration_engine import MIN_SAMPLE_SIZE, _scope_is_testable
from src.engine.prediction_evaluator import CHECKPOINT_DELTA, make_checkpoint_prediction

T0 = datetime(2026, 4, 6, 12, 0)


def _parent(horizon='5y', **overrides):
    fields = dict(
        id='parent-id', ticker='XOM', prediction_timestamp=T0,
        prediction_horizon=horizon, predicted_direction='buy',
        confidence_score=0.62, raw_confidence=0.7,
        analysis_context={'market_price': 100.0, 'calibration_corrections_active': 0},
        prompt_version='v1.0.0', model_version='mistral:7b',
        sector='Energy', asset_class='EQUITY', evaluation_status='PENDING',
        evaluation_due_at=T0 + timedelta(days=5 * 365),
    )
    fields.update(overrides)
    return PredictionRecord(**fields)


# ── CHECKPOINT CREATION ───────────────────────────────────────

def test_long_horizon_gets_one_month_checkpoint():
    cp = make_checkpoint_prediction(_parent('5y'))
    assert cp.prediction_horizon == '1m'
    assert cp.prediction_timestamp == T0
    assert cp.evaluation_due_at == T0 + CHECKPOINT_DELTA
    assert cp.evaluation_status == 'PENDING'


def test_checkpoint_copies_call_and_links_parent():
    cp = make_checkpoint_prediction(_parent('2y'))
    assert (cp.ticker, cp.predicted_direction, cp.sector, cp.asset_class) == ('XOM', 'buy', 'Energy', 'EQUITY')
    assert cp.raw_confidence == 0.7 and cp.confidence_score == 0.62
    assert cp.analysis_context['checkpoint_of'] == 'parent-id'
    assert cp.analysis_context['checkpoint_parent_horizon'] == '2y'
    # Evaluator needs the entry price; legacy-skip logic needs this flag
    assert cp.analysis_context['market_price'] == 100.0
    assert cp.analysis_context['calibration_corrections_active'] == 0


@pytest.mark.parametrize('horizon', ['1w', '1m', '30d'])
def test_short_horizon_gets_no_checkpoint(horizon):
    assert make_checkpoint_prediction(_parent(horizon)) is None


def test_unparseable_horizon_gets_no_checkpoint():
    assert make_checkpoint_prediction(_parent('forever')) is None


def test_parent_without_id_is_assigned_one():
    parent = _parent('3m', id=None)
    cp = make_checkpoint_prediction(parent)
    assert parent.id
    assert cp.analysis_context['checkpoint_of'] == parent.id


# ── CALIBRATION KEEPS PROFILES WHEN UNTESTABLE ────────────────

def _evaluated(n):
    return [{
        'ticker': f'T{i}', 'sector': 'Energy', 'asset_class': 'EQUITY',
        'predicted_direction': 'buy', 'prediction_horizon': '1m',
        'confidence': 0.7, 'is_correct': i % 2 == 0,
        'actual_return_pct': 2.0 if i % 2 == 0 else -2.0,
        'prediction_timestamp': T0 + timedelta(days=i),
    } for i in range(n)]


def test_scope_testable_needs_sample_and_holdout():
    assert not _scope_is_testable(_evaluated(MIN_SAMPLE_SIZE - 1))
    # 10 predictions → 3 in the 30% holdout, below MIN_HOLDOUT_SIZE
    assert not _scope_is_testable(_evaluated(MIN_SAMPLE_SIZE))
    assert _scope_is_testable(_evaluated(20))


class _FakeSession:
    def __init__(self):
        self.added, self.committed = [], False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add_all(self, rows):
        self.added += rows

    async def commit(self):
        self.committed = True


@pytest.fixture
def fake_db(monkeypatch):
    session = _FakeSession()
    calls = {'deactivated': 0}

    async def fake_deactivate(db):
        calls['deactivated'] += 1
        return 3

    monkeypatch.setattr(calibration_engine, 'AsyncSessionFactory', lambda: session)
    monkeypatch.setattr(calibration_engine, '_deactivate_old_profiles', fake_deactivate)
    return session, calls


def _feed(monkeypatch, predictions):
    async def fake_fetch(db):
        return predictions
    monkeypatch.setattr(calibration_engine, '_fetch_evaluated_predictions', fake_fetch)


@pytest.mark.asyncio
async def test_too_few_predictions_keeps_existing_profiles(monkeypatch, fake_db):
    session, calls = fake_db
    _feed(monkeypatch, _evaluated(2))
    result = await calibration_engine.run_calibration_engine()
    assert result['status'] == 'skipped'
    assert result['reason'] == 'insufficient_evaluated_predictions'
    assert calls['deactivated'] == 0
    assert not session.committed


@pytest.mark.asyncio
async def test_testable_run_replaces_profiles(monkeypatch, fake_db):
    session, calls = fake_db
    _feed(monkeypatch, _evaluated(20))
    result = await calibration_engine.run_calibration_engine()
    assert result['status'] == 'completed'
    assert calls['deactivated'] == 1
    assert session.committed
