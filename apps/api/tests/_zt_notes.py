"""Giving ZT capabilities notes before a run (#1084).

A capability with blank notes is never sent to the model, and an entry naming
one is dropped as `no_notes`. So a test about what a run does with an answer
must give that capability a note first, or it proves something about the
`no_notes` drop instead of the path it is named for.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi.testclient import TestClient

#: Any note will do: the tests that need one are about the answer, not the note.
NOTE = "Recorded for the test: the capability is partly in place."


def note_rows(c: TestClient, h: dict, answers: list[dict], *, skip: Iterable[str] = ()) -> None:
    """PATCH `NOTE` onto every answer, except those whose code is in `skip`."""
    leave = set(skip)
    for a in answers:
        if a["capability_code"] in leave:
            continue
        r = c.patch(f"/zt/answers/{a['id']}", headers=h, json={"notes": NOTE})
        assert r.status_code == 200, r.text


def noted_assessment(c: TestClient, h: dict, svc_id: str):
    """Create the service's assessment and note every capability. Returns the
    POST's response, as `c.post(.../assessments)` did, so a call site reads
    `answers` from it unchanged."""
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    note_rows(c, h, a.json()["answers"])
    return a
