"""#1334: a catalog technique with no tactic must fail the catalog BUILD, not
a client page. The client ATT&CK dashboard lists blind spots by tactic
(#1180), and a technique with no tactic is refused there loudly, which would
take the whole dashboard down. The generator refuses it first, with its own
typed `CouldNotLook`, naming the technique.

The world is the committed STIX subset with one active technique's
mitre-attack kill-chain phases removed; which technique is chosen from the
bundle, never from the module under test.
"""

from __future__ import annotations

import copy

import pytest

from app.attack import catalog
from tests.unit.test_attack_catalog_matches_stix import _bundle, _ext_id

pytestmark = pytest.mark.unit


def _active_patterns(bundle: dict) -> list[dict]:
    return [
        o
        for o in bundle["objects"]
        if o.get("type") == "attack-pattern"
        and not o.get("revoked")
        and not o.get("x_mitre_deprecated")
    ]


def test_a_technique_with_no_mitre_attack_tactic_fails_the_build() -> None:
    import scripts.generate_attack_catalog as gen

    bundle = copy.deepcopy(_bundle())
    target = _active_patterns(bundle)[0]
    code = _ext_id(target)
    target["kill_chain_phases"] = [
        p for p in target.get("kill_chain_phases", []) if p.get("kill_chain_name") != "mitre-attack"
    ]
    with pytest.raises(gen.CouldNotLook, match=rf"^{code} maps to no mitre-attack tactic$"):
        gen.build(bundle, catalog.SOURCE_VERSION)


def test_the_committed_subset_still_builds() -> None:
    """The positive control: unmodified, the same bundle builds."""
    import scripts.generate_attack_catalog as gen

    tactics, techniques = gen.build(_bundle(), catalog.SOURCE_VERSION)
    assert tactics and techniques
    assert all(t[2] for t in techniques)
