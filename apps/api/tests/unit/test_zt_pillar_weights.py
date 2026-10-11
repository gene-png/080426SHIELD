"""Every ZT pillar has a gap-priority weight, and only real pillars do (#838).

The weight multiplies a gap's size into the priority a client's roadmap is
ordered by. It used to be read with `.get(code, 1.0)`, so a pillar the table did
not know weighed a silent 1.0: a new or renamed pillar changed a client's
priorities with every test green. The advisor made this test required.
"""

from __future__ import annotations

import pytest

from app.zt.catalog import pillars
from app.zt.maturity import ZtFrameworkCode

pytestmark = pytest.mark.unit


def test_the_weight_table_is_exactly_the_catalogs_pillars() -> None:
    # test-integrity: the spec is the set of pillars the two catalogs define; the private table is what is checked against it
    from app.zt.scoring import _PILLAR_WEIGHTS

    catalog = {p.code for fw in ZtFrameworkCode for p in pillars(fw)}
    assert set(_PILLAR_WEIGHTS) == catalog, (
        f"pillars without a weight: {sorted(catalog - set(_PILLAR_WEIGHTS))}; "
        f"weights for no pillar: {sorted(set(_PILLAR_WEIGHTS) - catalog)}"
    )
