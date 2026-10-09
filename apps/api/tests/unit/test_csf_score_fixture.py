"""The csf_score runtime fixture, written from the approved prompt (#806).

CLAUDE.md: author AI fixtures from what the PROMPT says, never from what the
parser expects. Every expected value below is read from the prompt text, #806
comment 5982122270, quoted by section:

- section 3: one row per (tier, Subcategory) pair, "follow the order of codes
  in `subcategories`, and within each Subcategory follow the order of `tiers`";
- section 9: a Subcategory with no entry in `answers` gets 0 on all five and
  exactly the no-answer `what_we_found`; blank notes get 0 on all five, the
  rating sentence and the evidence sentence;
- sections 7, 8 and 10: `what_we_found` reports the rating with one of the
  five required sentences, then ends with one of the two evidence sentences;
- section 12: no other fields, at the top level or in a row.

The sentences are copied out of the prompt by `_sentence`, so a fixture that
drifts from the approved wording goes red here.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.engine import get_job
from app.ai.llm import FixtureProvider, LLMClient
from app.models.csf_profile import CsfDimensionScore
from tests._ai_runs import csf_run_ai

pytestmark = pytest.mark.unit

_PROMPT = get_job("csf_score").prompt

# Section 5's JSON keys, read from the prompt ("Each is returned under the JSON
# key shown"), and section 12's example row.
_DIMENSIONS = re.findall(r"^- [A-Z][A-Za-z ]+: `([a-z]+)`$", _PROMPT, flags=re.MULTILINE)
_EXAMPLE_ROW = json.loads(re.search(r'\{"scores": \[(\{[^\]]*\})\]\}', _PROMPT).group(1))


def _sentence(after: str) -> str:
    """The exact sentence the prompt prescribes on the line after `after`."""
    lines = _PROMPT.splitlines()
    return lines[lines.index(after) + 1]


_NO_ANSWER = _sentence(
    "When a Subcategory has no entry in `answers`, assign 0 to all five dimensions"
    " and use this exact what_we_found:"
)
_EVIDENCE_ATTACHED = _sentence(
    "When `has_evidence` is true, end what_we_found with this exact sentence:"
)
_NO_EVIDENCE = _sentence(
    "When `has_evidence` is false, or the Subcategory has no entry in `answers`,"
    " end what_we_found with this exact sentence:"
)
_RATING = {
    int(n): f"The recorded maturity rating is Tier {n} ({label})."
    for n, label in re.findall(
        r"^- The recorded maturity rating is Tier (\d) \(([^)]+)\)\.$", _PROMPT, flags=re.MULTILINE
    )
}
_NO_RATING = "No maturity rating was recorded."


def _fixture(payload: dict[str, Any]) -> dict[str, Any]:
    from app.ai.fixtures import _fixture_csf_score

    return json.loads(_fixture_csf_score(payload).content)


def test_the_sentences_were_read_from_the_prompt() -> None:
    """The expectations below are only as good as this parse of the prompt."""
    assert _DIMENSIONS == ["governance", "policy", "implementation", "monitoring", "improvement"]
    assert _NO_ANSWER.startswith("No answer was recorded.")
    assert _EVIDENCE_ATTACHED.startswith("Supporting evidence was attached")
    assert _NO_EVIDENCE == "No supporting evidence was attached to the answer."
    assert sorted(_RATING) == [1, 2, 3, 4]
    assert f"- {_NO_RATING}" in _PROMPT


def test_rows_follow_subcategories_then_tiers_in_input_order() -> None:
    """Section 3. The codes and tiers are deliberately NOT sorted, so a fixture
    that sorts, or loops tiers first, gives a different order."""
    payload = {
        "tiers": ["moderate", "high"],
        "subcategories": ["ID.AM-01", "GV.OC-01", "DE.CM-01"],
        "answers": {},
    }
    rows = _fixture(payload)["scores"]
    assert [(r["subcategory_code"], r["tier"]) for r in rows] == [
        ("ID.AM-01", "moderate"),
        ("ID.AM-01", "high"),
        ("GV.OC-01", "moderate"),
        ("GV.OC-01", "high"),
        ("DE.CM-01", "moderate"),
        ("DE.CM-01", "high"),
    ]


def test_the_response_carries_no_field_the_prompt_does_not_ask_for() -> None:
    """Section 12: "No other fields, at the top level or in a row"."""
    payload = {
        "tiers": ["high"],
        "subcategories": ["GV.OC-01", "GV.OC-02"],
        "answers": {"GV.OC-01": {"maturity_tier": 2, "notes": "Owned.", "has_evidence": False}},
    }
    body = _fixture(payload)
    assert list(body) == ["scores"]
    for row in body["scores"]:
        assert set(row) == set(_EXAMPLE_ROW)


def test_a_code_in_answers_but_not_in_subcategories_gets_no_row() -> None:
    """Section 1: "return no row for any code that is not in `subcategories`"."""
    payload = {
        "tiers": ["high"],
        "subcategories": ["GV.OC-01"],
        "answers": {"PR.AA-01": {"maturity_tier": 3, "notes": "MFA.", "has_evidence": True}},
    }
    rows = _fixture(payload)["scores"]
    assert [r["subcategory_code"] for r in rows] == ["GV.OC-01"]


def test_a_subcategory_with_no_answer_gets_zeros_and_the_exact_sentence() -> None:
    """Section 9, verbatim."""
    payload = {"tiers": ["high", "low"], "subcategories": ["GV.OC-01"], "answers": {}}
    for row in _fixture(payload)["scores"]:
        assert [row[d] for d in _DIMENSIONS] == [0, 0, 0, 0, 0]
        assert row["what_we_found"] == _NO_ANSWER


@pytest.mark.parametrize("blank", [None, "", "   \n"])
def test_blank_notes_get_zeros_the_rating_and_the_evidence_sentence(blank) -> None:
    """Section 9: blank notes score 0 everywhere; the rating and the evidence
    status are still reported, the evidence sentence last (section 10)."""
    payload = {
        "tiers": ["high"],
        "subcategories": ["GV.OC-01"],
        "answers": {"GV.OC-01": {"maturity_tier": 3, "notes": blank, "has_evidence": True}},
    }
    (row,) = _fixture(payload)["scores"]
    assert [row[d] for d in _DIMENSIONS] == [0, 0, 0, 0, 0]
    assert _RATING[3] in row["what_we_found"]
    assert row["what_we_found"].endswith(_EVIDENCE_ATTACHED)
    assert row["what_we_found"] != _NO_ANSWER


@pytest.mark.parametrize(
    ("tier", "has_evidence", "rating_sentence", "evidence_sentence"),
    [
        (1, False, _RATING[1], _NO_EVIDENCE),
        (4, True, _RATING[4], _EVIDENCE_ATTACHED),
        (None, False, _NO_RATING, _NO_EVIDENCE),
    ],
)
def test_noted_answers_end_with_the_rating_then_the_evidence_sentence(
    tier, has_evidence, rating_sentence, evidence_sentence
) -> None:
    """Sections 7, 8 and 10: the rating sentence, then the evidence sentence,
    last. Scores are JSON integers 0, 1 or 2 (section 12)."""
    payload = {
        "tiers": ["high", "moderate", "low"],
        "subcategories": ["GV.OC-01", "GV.OC-02"],
        "answers": {
            code: {
                "maturity_tier": tier,
                "notes": "Owned and reviewed.",
                "has_evidence": has_evidence,
            }
            for code in ("GV.OC-01", "GV.OC-02")
        },
    }
    rows = _fixture(payload)["scores"]
    assert len(rows) == 6
    for row in rows:
        assert row["what_we_found"].endswith(f"{rating_sentence} {evidence_sentence}")
        for d in _DIMENSIONS:
            assert type(row[d]) is int and row[d] in (0, 1, 2), (d, row[d])
    # A noted answer moves at least one dimension, so a run over it changes rows.
    assert any(row[d] for row in rows for d in _DIMENSIONS)


# --- through the run ------------------------------------------------------------


@pytest.fixture()
def world(tmp_path) -> Iterator[tuple[TestClient, sessionmaker, FixtureProvider, dict, str]]:
    url = f"sqlite:///{tmp_path / 'shield-csffixture.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.models.client import Client
    from app.models.client_domain import ClientDomain
    from app.routes.csf import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    with sessions() as seed:
        tenant = Client(legal_name="Test Tenant")
        seed.add(tenant)
        seed.flush()
        seed.add(ClientDomain(client_id=tenant.id, domain="example.com"))
        seed.commit()
        cid = str(tenant.id)
    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        bearer = c.post(
            "/auth/register",
            json={
                "email": "admin@example.com",
                "password": "correct horse battery staple!",
                "display_name": "A",
            },
        ).json()["tokens"]["access_token"]
        h = {"Authorization": f"Bearer {bearer}"}
        svc_id = c.post(
            "/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}
        ).json()["id"]
        assert c.post(f"/csf/services/{svc_id}/assessments", headers=h).status_code in (200, 201)
        seeded = c.post(
            f"/csf/services/{svc_id}/profiles/seed",
            headers=h,
            json={"tiers": ["high", "low", "moderate"]},
        )
        assert seeded.status_code in (200, 201), seeded.text
        yield c, sessions, provider, h, svc_id


def test_through_the_run_only_the_noted_subcategory_moves_a_dimension(world) -> None:
    """The s7 premise (#806 A5): on a draft with one noted answer, the fixture
    run applies every row with no drop, moves a dimension on the noted code
    only, and writes the section 9 sentence on every unanswered row."""
    from app.ai.fixtures import _fixture_csf_score

    c, sessions, provider, h, svc_id = world
    latest = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=h).json()
    answer = next(a for a in latest["answers"] if a["subcategory_code"] == "GV.OC-01")
    saved = c.patch(
        f"/csf/answers/{answer['id']}",
        json={"notes": "The CISO owns the mission statement review."},
        headers=h,
    )
    assert saved.status_code == 200, saved.text
    provider.register("csf_score", _fixture_csf_score)

    result = csf_run_ai(c, svc_id, h)

    assert result["dropped"] == [], result["dropped"]
    moved = {ch["subcategory_code"] for ch in result["changed"] if ch["field"] in _DIMENSIONS}
    assert moved == {"GV.OC-01"}
    with sessions() as db:
        rows = db.execute(select(CsfDimensionScore)).scalars().all()
    assert len(rows) == 318
    for r in rows:
        if r.subcategory_code != "GV.OC-01":
            assert r.what_we_found == _NO_ANSWER, r.subcategory_code
