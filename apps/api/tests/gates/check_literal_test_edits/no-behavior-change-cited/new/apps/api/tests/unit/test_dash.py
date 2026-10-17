import pytest

pytestmark = pytest.mark.unit


def test_percentage():
    result = compute(2, 4)
    assert result.pct == 33.3
    assert "50%" in result.text
