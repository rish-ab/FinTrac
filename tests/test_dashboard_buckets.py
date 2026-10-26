import pytest

from src.api.routes.dashboard import CONFIDENCE_BUCKETS, _confidence_bucket


@pytest.mark.parametrize('conf, expected', [
    (0.0, '0.0-0.5'),
    (0.3, '0.0-0.5'),     # previously fell into 0.9-1.0
    (0.49, '0.0-0.5'),
    (0.5, '0.5-0.6'),
    (0.6, '0.6-0.7'),
    (0.7, '0.7-0.8'),
    (0.79, '0.7-0.8'),
    (0.8, '0.8-0.9'),
    (0.9, '0.9-1.0'),
    (1.0, '0.9-1.0'),
])
def test_confidence_bucket(conf, expected):
    assert _confidence_bucket(conf) == expected
    assert expected in CONFIDENCE_BUCKETS
