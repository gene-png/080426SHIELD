"""A shard's record says what RAN, not what it selected (#689).

The record used to be written at collection from `session.items`, so it named
every test the shard SELECTED. A test that skipped at runtime, or was never
reached after `-x` or a crash, read as run, and the aggregate's partition check
counted it. The plugin now writes from each test's reports: what ran goes to
the record, what skipped goes to a file beside it, and a test with no report is
in neither -- so the aggregate names it as selected but run nowhere.

Written before the change: on the collection-time record,
`test_a_runtime_skip_is_not_recorded_as_run` and
`test_a_test_never_reached_is_in_neither_file` are red.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.pytest_shard as shard
import scripts.shard_partition as partition
import yaml

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit

_API = Path(__file__).resolve().parents[2]

# Every outcome a test can have, one test each. Sorted, these are dealt to one
# shard of one, so the run below sees all of them.
_OUTCOMES = """
    import pytest
    pytestmark = pytest.mark.unit

    def test_a_passes(): pass

    def test_b_skips_in_its_body(): pytest.skip("not here")

    @pytest.mark.skipif(True, reason="never here")
    def test_c_skips_by_mark(): pass

    @pytest.mark.xfail(reason="known", strict=False)
    def test_d_xfails(): assert False

    def test_e_fails(): assert False

    @pytest.mark.xfail(run=False, reason="never run")
    def test_f_xfail_not_run(): pass
"""
_ID = "tests/unit/test_outcomes.py::"


def _project(tmp_path: Path, body: str = _OUTCOMES) -> Path:
    root = tmp_path / "proj"
    (root / "tests" / "unit").mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\nmarkers =\n    unit: fast\n", encoding="utf-8")
    (root / "tests" / "unit" / "test_outcomes.py").write_text(
        textwrap.dedent(body), encoding="utf-8"
    )
    return root


def _run(root: Path, record: Path, *extra: str, spec: str = "1/1") -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in (shard.SHARD_ENV, shard.RECORD_ENV)}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(_API), env.get("PYTHONPATH")]))
    env.pop("PYTEST_ADDOPTS", None)
    env[shard.SHARD_ENV] = spec
    env[shard.RECORD_ENV] = str(record)
    return subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-p", "scripts.pytest_shard",
         "-q", "-m", "unit", *extra, "tests/unit"],  # fmt: skip
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _lines(path: Path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln]


def test_a_runtime_skip_is_not_recorded_as_run(tmp_path: Path) -> None:
    root = _project(tmp_path)
    record = tmp_path / "ran.txt"
    proc = _run(root, record)
    assert proc.returncode == 1, proc.stdout + proc.stderr  # test_e fails, as it should
    assert _lines(record) == [
        f"{_ID}test_a_passes",
        f"{_ID}test_d_xfails",
        f"{_ID}test_e_fails",
    ], proc.stdout
    assert _lines(shard.skipped_path(record)) == [
        f"{_ID}test_b_skips_in_its_body",
        f"{_ID}test_c_skips_by_mark",
        f"{_ID}test_f_xfail_not_run",
    ], proc.stdout
    assert "pytest_shard: 3 ran, 3 skipped at runtime, 0 never reached" in proc.stdout


def test_a_test_never_reached_is_in_neither_file(tmp_path: Path) -> None:
    """`-x` stops at the first failure; the tests after it never ran."""
    root = _project(
        tmp_path,
        """
        import pytest
        pytestmark = pytest.mark.unit
        def test_a(): pass
        def test_b(): assert False
        def test_c(): pass
        """,
    )
    record = tmp_path / "ran.txt"
    proc = _run(root, record, "-x")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert _lines(record) == [f"{_ID}test_a", f"{_ID}test_b"], proc.stdout
    assert _lines(shard.skipped_path(record)) == [], proc.stdout
    assert "pytest_shard: 2 ran, 0 skipped at runtime, 1 never reached" in proc.stdout


def test_a_stale_record_does_not_survive_a_run_that_writes_none(tmp_path: Path) -> None:
    """A record left from an earlier run must not stand in for this one. Here
    collection succeeds and a hard exit ends the session before its write, as a
    crash or a killed runner would."""
    root = _project(
        tmp_path,
        """
        import os, pytest
        pytestmark = pytest.mark.unit
        def test_a(): os._exit(3)
        """,
    )
    record = tmp_path / "ran.txt"
    record.write_text(f"{_ID}test_a\n", encoding="utf-8")
    shard.skipped_path(record).write_text("", encoding="utf-8")
    proc = _run(root, record)
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert not record.exists(), "a record from an earlier run survived a run that wrote none"
    assert not shard.skipped_path(record).exists()


# --- the verifier, given the skipped files -----------------------------------------


def _write(path: Path, ids: list[str]) -> Path:
    path.write_text("".join(f"{i}\n" for i in ids), encoding="utf-8")
    return path


FULL = ["t.py::a", "t.py::b", "t.py::c", "u.py::d"]


def _verify(tmp_path: Path, ran: list[list[str]], skipped: list[list[str]] | None) -> int:
    argv = ["shard_partition", "verify", "--full", str(_write(tmp_path / "full.txt", FULL))]
    argv += ["--of", str(len(ran)), "--ran"]
    argv += [str(_write(tmp_path / f"ran-{i}.txt", r)) for i, r in enumerate(ran, 1)]
    if skipped is not None:
        argv += ["--skipped"]
        argv += [str(_write(tmp_path / f"skip-{i}.txt", s)) for i, s in enumerate(skipped, 1)]
    return partition.main(argv)


def test_a_skipped_test_is_accounted_for_and_named_but_not_counted_as_run(
    tmp_path: Path, capsys
) -> None:
    rc = _verify(tmp_path, [["t.py::a", "u.py::d"], ["t.py::b"]], [[], ["t.py::c"]])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "4 of 4 selected tests are in exactly one of 2 shards: 3 ran, 1 SKIPPED" in out, out
    assert "skipped, did not run: t.py::c" in out, out


def test_without_the_skipped_files_a_skipped_test_is_a_gap(tmp_path: Path, capsys) -> None:
    """What the aggregate would see if its `--skipped` were dropped: red."""
    assert _verify(tmp_path, [["t.py::a", "u.py::d"], ["t.py::b"]], None) == 1
    assert "selected but ran in no shard: t.py::c" in capsys.readouterr().out


def test_a_test_both_run_and_skipped_is_a_duplicate(tmp_path: Path, capsys) -> None:
    rc = _verify(tmp_path, [["t.py::a", "u.py::d"], ["t.py::b", "t.py::c"]], [[], ["t.py::c"]])
    assert rc == 1
    assert "ran in 2 shards: t.py::c" in capsys.readouterr().out


def test_a_skipped_test_outside_the_selection_is_a_finding(tmp_path: Path, capsys) -> None:
    rc = _verify(tmp_path, [["t.py::a", "u.py::d"], ["t.py::b", "t.py::c"]], [["x.py::z"], []])
    assert rc == 1
    assert "ran but not selected: x.py::z" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv_tail",
    [
        ["--skipped"],  # the flag with no files: a glob that matched nothing
        ["--skipped", "MISSING"],
    ],
    ids=["no-files", "a-missing-file"],
)
def test_missing_skipped_files_are_could_not_look(tmp_path: Path, argv_tail: list[str]) -> None:
    argv = ["shard_partition", "verify", "--full", str(_write(tmp_path / "f.txt", FULL)),
            "--of", "1", "--ran", str(_write(tmp_path / "r.txt", FULL))]  # fmt: skip
    argv += [str(tmp_path / "nope.txt") if a == "MISSING" else a for a in argv_tail]
    assert partition.main(argv) == 2


def test_one_skipped_file_per_record_or_could_not_look(tmp_path: Path) -> None:
    assert _verify(tmp_path, [["t.py::a", "u.py::d"], ["t.py::b", "t.py::c"]], [[]]) == 2


# --- the workflow wires both files through ----------------------------------------


def _jobs() -> dict:
    wf = find_workflows_dir(pathlib.Path(__file__).resolve())
    if wf is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    return yaml.safe_load((wf / "ci.yml").read_text(encoding="utf-8"))["jobs"]


def _shard_job(jobs: dict) -> tuple[dict, dict]:
    found = [
        (job, step)
        for job in jobs.values()
        for step in job.get("steps", [])
        if "-p scripts.pytest_shard" in str(step.get("run", ""))
    ]
    assert len(found) == 1, f"expected one shard step, found {len(found)}"
    return found[0]


def test_every_shard_upload_carries_the_record_and_its_skipped_file() -> None:
    job, step = _shard_job(_jobs())
    record = str(step["env"][shard.RECORD_ENV])
    uploads = [
        s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/upload-artifact@")
    ]
    assert uploads, "the shard job uploads nothing"
    # The plugin's own naming, so the workflow and the plugin cannot drift.
    assert shard.skipped_path(Path("r.txt")) == Path("r.txt.skipped")
    for upload in uploads:
        paths = [ln.strip() for ln in str(upload["with"]["path"]).splitlines() if ln.strip()]
        assert paths == [record, f"{record}.skipped"], paths


def test_the_python_aggregate_passes_the_skipped_files() -> None:
    jobs = _jobs()
    agg = [j for j in jobs.values() if j.get("name") == "Python (ruff + black + pytest + bandit)"]
    assert len(agg) == 1
    runs = [str(s.get("run", "")) for s in agg[0]["steps"]]
    verify = [r for r in runs if "scripts.shard_partition verify" in r]
    assert len(verify) == 1, runs
    assert '--ran "$RUNNER_TEMP"/pytest/pytest-shard-*.txt' in verify[0], verify[0]
    assert '--skipped "$RUNNER_TEMP"/pytest/pytest-shard-*.txt.skipped' in verify[0], verify[0]


def test_the_shard_job_has_a_timeout() -> None:
    """#739: with none, GitHub's 6-hour default holds a required check that long
    behind a hung test."""
    job, _ = _shard_job(_jobs())
    minutes = job.get("timeout-minutes")
    assert isinstance(minutes, int), f"no literal timeout-minutes on the shard job: {minutes!r}"
    assert 0 < minutes <= 120, minutes
