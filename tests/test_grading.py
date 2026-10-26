import pytest

from src.engine.prediction_evaluator import HOLD_TOLERANCE_PCT, grade_direction


@pytest.mark.parametrize('direction, ret, expected', [
    ('buy', 2.0, True),
    ('BUY', -0.1, False),
    ('avoid', -2.0, True),
    ('avoid', 1.0, False),
    ('sell', -1.0, True),
    ('hold', 0.0, True),
    ('hold', HOLD_TOLERANCE_PCT, True),
    ('HOLD', HOLD_TOLERANCE_PCT + 0.01, False),   # backtester used to count every HOLD as correct
    ('hold', -(HOLD_TOLERANCE_PCT + 5), False),
])
def test_grade_direction(direction, ret, expected):
    assert grade_direction(direction, ret) is expected


def test_backtester_uses_shared_grading():
    from src.engine import backtester
    assert backtester.grade_direction is grade_direction
