"""The deferred-item alarm clock (`apps/api/scripts/fire_scheduled_triggers.py`).

Tested here rather than left to fire blind in CI, because its whole value is that
it is reliable: a mechanism nobody trusts gets muted, and a muted mechanism is the
"tracked but never comes up" state it exists to end.

The decisions are pure functions and are tested as such. The WIRING is tested
through `main()` with `_gh` replaced (#531 round 1): a guard that is correct
as a function and never called from `main` protects nothing, and deleting its
call must turn a test red. The replacement returns what `gh --json` returns
and asserts nothing about the API's behaviour; `gh` itself is not modelled.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest
import scripts.fire_scheduled_triggers as triggers
from scripts.fire_scheduled_triggers import (
    LIST_LIMIT,
    failure_report,
    main,
    not_truncated,
    parse_trigger,
    stale_fired,
)


@pytest.mark.unit
def test_a_well_formed_trigger_parses() -> None:
    body = (
        "Some context about the deferred work.\n\n"
        "Trigger-date: 2026-10-01\n"
        "Trigger-reason: MVP item 8 is the last one; this opens when it merges.\n"
    )
    due, reason = parse_trigger(body)
    assert due == date(2026, 10, 1)
    assert reason.startswith("MVP item 8")


@pytest.mark.unit
def test_a_missing_date_raises_rather_than_being_skipped() -> None:
    """FAIL LOUDLY. A silently ignored alarm clock is worse than none, because
    the label implies one is set — the item then reads as scheduled while nothing
    will ever fire. That is the exact state this script exists to end, arriving
    through the script itself."""
    with pytest.raises(ValueError, match="no `Trigger-date:` line"):
        parse_trigger("Trigger-reason: because\n")


@pytest.mark.unit
def test_a_missing_reason_raises() -> None:
    """A date with no reason produces a comment nobody can act on, which is how a
    reminder becomes noise and then gets muted."""
    with pytest.raises(ValueError, match="no `Trigger-reason:` line"):
        parse_trigger("Trigger-date: 2026-10-01\n")


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad", ["01-10-2026", "2026/10/01", "October 1 2026", "2026-13-01", "soon"]
)
def test_a_malformed_date_raises_with_the_value_in_the_message(bad: str) -> None:
    """Including `soon` and `2026-13-01`: the first is what someone actually
    types when they mean "later", and the second parses as a date shape but is
    not one. Both must be refused, and the message must quote the value so the
    fix is obvious from the CI log alone."""
    with pytest.raises(ValueError, match="not an ISO date"):
        parse_trigger(f"Trigger-date: {bad}\nTrigger-reason: because\n")


@pytest.mark.unit
def test_the_labels_are_case_insensitive_but_the_date_is_not_guessed() -> None:
    """Tolerant about how the marker is typed, strict about what it means.

    Someone writing `trigger-date:` in lower case should not silently get no
    alarm; someone writing an ambiguous date should not get a guessed one.
    """
    due, _ = parse_trigger("trigger-date: 2026-10-01\ntrigger-reason: x\n")
    assert due == date(2026, 10, 1)


# --- #531 / #496: the trigger that went nowhere --------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "line",
    [
        "`Trigger-date: 2026-09-22`",  # #145's exact shape, which failed four weeks
        "**Trigger-date:** 2026-09-22",
        "- Trigger-date: 2026-09-22",
        "> Trigger-date: 2026-09-22",
    ],
)
def test_a_decorated_trigger_line_parses(line: str) -> None:
    due, reason = parse_trigger(f"## Trigger\n\n{line}\n- Trigger-reason: because\n")
    assert due == date(2026, 9, 22)
    assert reason == "because"


@pytest.mark.unit
def test_a_key_mentioned_but_not_on_its_own_line_names_the_cause() -> None:
    """The old message said "has no `Trigger-date:` line" while the line was
    visibly there, which names the check and not the cause (#531)."""
    body = "The Trigger-date is 2026-09-22, see below.\nTrigger-reason: x\n"
    with pytest.raises(ValueError, match="mentions `Trigger-date` but not as a line of its own"):
        parse_trigger(body)


@pytest.mark.unit
def test_an_empty_value_does_not_borrow_the_next_line() -> None:
    """An empty `Trigger-reason:` is a missing reason. It must not quietly take
    whatever line follows it as the reason the comment will quote."""
    body = "Trigger-date: 2026-10-01\nTrigger-reason:\n- a bullet from the next section\n"
    with pytest.raises(ValueError, match="`Trigger-reason:` has no value on its line"):
        parse_trigger(body)


@pytest.mark.unit
@pytest.mark.parametrize("line", ["Trigger-reason: ``", "**Trigger-reason:** **"])
def test_a_value_of_only_decoration_is_empty(line: str) -> None:
    with pytest.raises(ValueError, match="`Trigger-reason:` has no value on its line"):
        parse_trigger(f"Trigger-date: 2026-10-01\n{line}\n")


@pytest.mark.unit
def test_a_full_page_is_refused_as_truncated() -> None:
    """`gh` stops at `--limit` without saying so, so a full page may hide
    triggers that would never fire (#496)."""
    assert not_truncated([{"number": 1}], limit=2) == [{"number": 1}]
    with pytest.raises(RuntimeError, match="may be truncated"):
        not_truncated([{"number": 1}, {"number": 2}], limit=2)


@pytest.mark.unit
def test_a_fired_trigger_left_untouched_is_reported() -> None:
    today = date(2026, 10, 20)
    issues = [
        {"number": 1, "labels": [{"name": "trigger-fired"}], "updatedAt": "2026-10-01T07:00:00Z"},
        {"number": 2, "labels": [{"name": "trigger-fired"}], "updatedAt": "2026-10-15T07:00:00Z"},
        {"number": 3, "labels": [], "updatedAt": "2026-01-01T07:00:00Z"},
    ]
    assert stale_fired(issues, today, days=14) == ["#1: fired and untouched for 19 days"]


@pytest.mark.unit
def test_a_failed_run_comments_on_the_open_tracking_issue(fake_gh) -> None:
    # The log is one a real run wrote, not a string written to agree with the
    # report: a malformed trigger, through main(), into TRIGGER_LOG.
    log_path = fake_gh([_issue(145, body="`Trigger-date` is below\n")])
    with pytest.raises(ValueError):
        main([])
    log = log_path.read_text(encoding="utf-8")
    existing = [
        {"number": 7, "title": "Scheduled triggers: the weekly run failed"},
        {"number": 8, "title": "Something else"},
    ]
    action, args = failure_report(existing, log, "https://run/1")
    assert action == "comment"
    assert args[0] == "7"
    assert "https://run/1" in args[1]
    assert "#145: mentions `Trigger-date` but not as a line of its own" in args[1]


@pytest.mark.unit
def test_a_failed_run_opens_the_tracking_issue_when_none_is_open() -> None:
    action, args = failure_report([], None, "https://run/2")
    assert action == "create"
    assert args[0] == "Scheduled triggers: the weekly run failed"
    # A crash before the log was written is said, not papered over.
    assert "failed before it wrote its log" in args[1] and "https://run/2" in args[1]


@pytest.mark.unit
@pytest.mark.parametrize("argv", [["--nope"], ["--report-failure"], ["--report-failure", "a", "b"]])
def test_an_unknown_or_incomplete_argument_is_could_not_look(argv: list[str], monkeypatch) -> None:
    # REPO set, so the argument check is the only thing that can refuse.
    monkeypatch.setenv("REPO", "owner/repo")
    assert main(argv) == 2


# --- main()-level wiring: each goes red when its call in main() is deleted ------------------


def _issue(number: int, *, body: str = "", fired: bool = False, updated: str | None = None) -> dict:
    return {
        "number": number,
        "title": f"issue {number}",
        "body": body,
        "labels": [{"name": "scheduled-trigger"}] + ([{"name": "trigger-fired"}] if fired else []),
        "updatedAt": updated or f"{date.today().isoformat()}T07:00:00Z",
    }


@pytest.fixture
def fake_gh(monkeypatch, tmp_path: Path):
    """Replace `_gh` with one serving `issue list` from a given list, and point
    TRIGGER_LOG at a temp file. Returns a setter giving back the log's path;
    every call made is kept on `fake_gh.calls`."""
    calls: list[tuple[str, ...]] = []
    log_path = tmp_path / "triggers.log"
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("TRIGGER_LOG", str(log_path))

    def use(issues: list[dict]) -> Path:
        def gh(*args: str) -> str:
            calls.append(args)
            return json.dumps(issues) if args[:2] == ("issue", "list") else ""

        monkeypatch.setattr(triggers, "_gh", gh)
        return log_path

    use.calls = calls
    return use


@pytest.mark.unit
def test_main_refuses_a_full_page_as_could_not_look(fake_gh) -> None:
    """Wiring for #496: exactly LIST_LIMIT issues, each otherwise clean (fired
    and recently touched), so the refusal is the only thing that can fail."""
    log_path = fake_gh([_issue(n, fired=True) for n in range(LIST_LIMIT)])
    assert main([]) == 2
    log = log_path.read_text(encoding="utf-8")
    assert "could not look -- CouldNotLook: `gh issue list` returned 1000 issues" in log
    assert "Raise LIST_LIMIT" in log


@pytest.mark.unit
def test_main_reads_one_short_of_the_limit_as_complete(fake_gh) -> None:
    fake_gh([_issue(n, fired=True) for n in range(LIST_LIMIT - 1)])
    assert main([]) == 0


@pytest.mark.unit
def test_the_limit_asked_of_gh_is_the_limit_refused(fake_gh) -> None:
    """If `--limit` and the refusal drift apart, a full page is read as complete
    (limit asked < refused) or a complete one refused (asked > refused)."""
    fake_gh([])
    assert main([]) == 0
    (listing,) = [c for c in fake_gh.calls if c[:2] == ("issue", "list")]
    assert listing[listing.index("--limit") + 1] == str(LIST_LIMIT)


@pytest.mark.unit
def test_main_fails_on_a_fired_trigger_left_untouched(fake_gh) -> None:
    log_path = fake_gh([_issue(118, fired=True, updated="2020-01-01T07:00:00Z")])
    with pytest.raises(ValueError, match="#118: fired and untouched for"):
        main([])
    assert "ValueError: issues labelled `scheduled-trigger`" in log_path.read_text("utf-8")


@pytest.mark.unit
def test_a_gh_failure_reaches_the_log_and_exits_2(monkeypatch, tmp_path: Path) -> None:
    """Through the REAL `_gh`, with only `subprocess.run` replaced: the error
    `gh` printed must reach TRIGGER_LOG, which is what the tracking issue quotes."""
    log_path = tmp_path / "triggers.log"
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("TRIGGER_LOG", str(log_path))
    monkeypatch.setattr(
        triggers.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 1, "", "HTTP 502: Bad Gateway"),
    )
    assert main([]) == 2
    assert "gh issue list --repo owner/repo" in log_path.read_text("utf-8")
    assert "HTTP 502: Bad Gateway" in log_path.read_text("utf-8")
