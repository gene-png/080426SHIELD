import sys

import pytest


@pytest.mark.skipif(sys.version_info < (3, 0), reason="needs python 3")
def test_percentage():
    assert compute(2, 4) == 33.3
