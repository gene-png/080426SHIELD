"""Driving a background Run-AI from a test (#645).

Run-AI answers 202 and finishes in a background job. Two ways to drive it:

* `run_ai_and_wait` -- the PRODUCTION runner. Starlette's TestClient runs a
  response's background tasks before `post()` returns, so by the time the run
  is polled the job has finished. Success-path tests use this; it returns the
  run's `result`, which carries every field the synchronous response used to.
* `DeferringRunner` -- holds the job until the test calls `run_all()`, so a
  test can observe RUNNING: a second POST, a poll mid-run, an edit hitting the
  lock. Without it, every guard test would pass without the guard ever seeing
  a run in progress.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient


class DeferringRunner:
    """A Run-AI runner that holds each job until `run_all()`."""

    def __init__(self) -> None:
        self.pending: list[Callable[[], None]] = []

    def __call__(self, job: Callable[[], None]) -> None:
        self.pending.append(job)

    def run_all(self) -> int:
        """Run every held job, in order. Returns how many ran, so a test can
        assert it actually drove one rather than reading an untouched run."""
        jobs, self.pending = self.pending, []
        for job in jobs:
            job()
        return len(jobs)


def defer_runs(app: Any) -> DeferringRunner:
    """Install a deferring runner on `app` and return it."""
    from app.ai.runs import get_ai_run_runner

    runner = DeferringRunner()
    app.dependency_overrides[get_ai_run_runner] = lambda: runner
    return runner


def start_run(
    c: TestClient, url: str, headers: dict, *, serves: str = "offline", **kwargs: Any
) -> dict:
    """POST a Run-AI and return the 202 body."""
    r = c.post(url, headers=headers, json={"serves": serves, **kwargs})
    assert r.status_code == 202, r.text
    return r.json()


def get_run(c: TestClient, run_id: str, headers: dict) -> dict:
    r = c.get(f"/ai-runs/{run_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def run_ai_and_wait(
    c: TestClient, url: str, headers: dict, *, serves: str = "offline", **kwargs: Any
) -> dict:
    """POST a Run-AI through the production runner and return the COMPLETED
    run's `result`. Fails loudly, with the run, if it ended any other way."""
    started = start_run(c, url, headers, serves=serves, **kwargs)
    run = get_run(c, started["run_id"], headers)
    assert run["status"] == "completed", run
    assert run["result"] is not None, run
    return run["result"]


def run_ai_expecting_failure(
    c: TestClient, url: str, headers: dict, *, serves: str = "offline", **kwargs: Any
) -> dict:
    """POST a Run-AI and return the FAILED run. The synchronous route answered
    these with a 502 or a 409; a background job cannot, so its typed reason and
    `charged_likely` are on the run instead."""
    started = start_run(c, url, headers, serves=serves, **kwargs)
    run = get_run(c, started["run_id"], headers)
    assert run["status"] == "failed", run
    return run


def attack_run_ai(c: TestClient, svc_id: str, headers: dict, **kwargs: Any) -> dict:
    """An ATT&CK Run-AI, driven to completion: the run's `result`, plus the
    assessment's coverage as it stands after the run. The synchronous response
    carried `coverage`; the run does not (the workspace re-reads the
    assessment), so the helper reads it the same way the workspace does."""
    result = run_ai_and_wait(c, f"/attack/services/{svc_id}/run-ai", headers, **kwargs)
    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=headers)
    assert latest.status_code == 200, latest.text
    return {**result, "coverage": latest.json()["coverage"]}


def tech_debt_extract(
    c: TestClient, svc_id: str, headers: dict, artifact_id: str, **kwargs: Any
) -> dict:
    """A Tech Debt extraction, driven to completion: the capability list it
    wrote, read the way the workspace reads it. The synchronous route answered
    with that list; the run's result names it."""
    r = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers=headers,
        json={"artifact_id": artifact_id, "serves": "offline", **kwargs},
    )
    assert r.status_code == 202, r.text
    run = get_run(c, r.json()["run_id"], headers)
    assert run["status"] == "completed", run
    latest = c.get(f"/tech-debt/services/{svc_id}/capability-lists/latest", headers=headers)
    assert latest.status_code == 200, latest.text
    body = latest.json()
    assert body["id"] == run["result"]["capability_list_id"], (body["id"], run["result"])
    return body
