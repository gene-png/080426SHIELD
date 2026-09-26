"""The e2e spec-listing check (#540): a spec on disk CI's run excludes is a finding.

The owner's design for #540's Playwright half: compare the specs on disk with
the specs the CI project runs. Written with the check; the live-repo test at
the bottom pins the listing step to CI's real run step.
"""

from __future__ import annotations

import json
import pathlib
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py for why a
# bare `from scripts import ...` sorts differently in the container and in CI.
import scripts.check_e2e_spec_listing as gate
import yaml

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit


def _listing(*specs: str) -> str:
    lines = ["Listing tests:"]
    lines += [f"  [chromium] › {s}:10:5 › a test" for s in specs]
    lines.append(f"Total: {len(specs)} tests in {len(specs)} files")
    return "\n".join(lines) + "\n"


def _repo(
    tmp_path: Path, on_disk: list[str], listing: str, declared: dict | None = None
) -> tuple[Path, Path]:
    for rel in on_disk:
        p = tmp_path / "e2e" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("test('x', () => {});\n", encoding="utf-8")
    # #579: the declarations file is a required input; `None` leaves it out.
    if declared is not None:
        d = tmp_path / ".github" / "e2e-non-suite-files.json"
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(json.dumps(declared), encoding="utf-8")
    lst = tmp_path / "list.txt"
    lst.write_text(listing, encoding="utf-8")
    return tmp_path, lst


def _run(root: Path, lst: Path, capsys) -> tuple[int, str]:
    code = gate.main(["gate", "--root", str(root), "--list-file", str(lst)])
    return code, capsys.readouterr().out


def test_every_spec_listed_is_clean(tmp_path, capsys) -> None:
    root, lst = _repo(
        tmp_path, ["smoke/a.spec.ts", "b.spec.ts"], _listing("smoke/a.spec.ts", "b.spec.ts"), {}
    )
    code, out = _run(root, lst, capsys)
    assert code == 0, out
    assert "2 script file(s) under e2e/: 2 in CI's run, 0 declared non-suite" in out, out


def test_a_spec_on_disk_the_run_excludes_is_a_finding_naming_it(tmp_path, capsys) -> None:
    root, lst = _repo(tmp_path, ["smoke/a.spec.ts", "b.spec.ts"], _listing("b.spec.ts"), {})
    code, out = _run(root, lst, capsys)
    assert code == 1, out
    assert "e2e/smoke/a.spec.ts: not in `npx playwright test --list`" in out, out


def test_windows_separators_in_the_listing_are_normalised(tmp_path, capsys) -> None:
    # --list prints `smoke\\a.spec.ts` on Windows; the author's own first
    # negative test grepped for a forward-slash path and removed nothing.
    root, lst = _repo(tmp_path, ["smoke/a.spec.ts"], _listing("smoke" + chr(92) + "a.spec.ts"), {})
    code, out = _run(root, lst, capsys)
    assert code == 0, out


def test_node_modules_specs_are_not_counted(tmp_path, capsys) -> None:
    root, lst = _repo(
        tmp_path, ["a.spec.ts", "node_modules/pkg/x.spec.ts"], _listing("a.spec.ts"), {}
    )
    code, out = _run(root, lst, capsys)
    assert code == 0, out


@pytest.mark.parametrize(
    "listing",
    ["", "Listing tests:\n", "Listing tests:\nTotal: 0 tests in 0 files\n"],
    ids=["empty", "no-total", "no-specs"],
)
def test_a_listing_that_is_not_one_is_could_not_look(tmp_path, capsys, listing: str) -> None:
    root, lst = _repo(tmp_path, ["a.spec.ts"], listing, {})
    code, out = _run(root, lst, capsys)
    assert code == 2, out


def test_a_missing_list_file_is_could_not_look(tmp_path, capsys) -> None:
    root, _ = _repo(tmp_path, ["a.spec.ts"], _listing("a.spec.ts"), {})
    code, out = _run(root, tmp_path / "absent.txt", capsys)
    assert code == 2, out


def test_no_e2e_dir_is_could_not_look(tmp_path, capsys) -> None:
    lst = tmp_path / "list.txt"
    lst.write_text(_listing("a.spec.ts"), encoding="utf-8")
    code, out = _run(tmp_path, lst, capsys)
    assert code == 2, out
    # The BRANCH, not only the code: without this guard rglob on a missing
    # directory falls through to "no script files under", also exit 2.
    assert "does not exist -- wrong root?" in out, out


def test_list_file_is_required_and_unknown_flags_refused(capsys) -> None:
    assert gate.main(["gate", "--root", "."]) == 2
    assert gate.main(["gate", "--lst", "x"]) == 2


def _e2e_jobs() -> dict:
    wf = find_workflows_dir(pathlib.Path(__file__).resolve())
    if wf is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    return yaml.safe_load((wf / "ci.yml").read_text(encoding="utf-8"))["jobs"]


def _runs(job: dict) -> list[tuple[object, str]]:
    return [(s.get("working-directory"), str(s.get("run") or "").strip()) for s in job["steps"]]


def _shard_count(jobs: dict) -> int:
    shards = jobs["e2e-shard"]["strategy"]["matrix"]["shard"]
    assert shards == list(range(1, len(shards) + 1)), shards
    return len(shards)


# The listing is only evidence about CI's run if it lists what the run runs.
# Since the CI-speed PR the suite runs in shards (coordinator's verdict), so the
# evidence is: (a) the #540 check lists the WHOLE suite, with no arguments;
# (b) each shard leg runs exactly its `--shard=k/N` and lists exactly that share;
# (c) the aggregate requires the shard lists to partition the full list.
# (d) and (e) pin that the aggregate cannot pass on nothing, and that every list
# comes from the same tree. This replaces a pin on ONE job running
# `npx playwright test` with no arguments.


def test_a_the_540_listing_lists_the_whole_suite() -> None:
    runs = _runs(_e2e_jobs()["e2e-session"])
    listing = [r for r in runs if "playwright test --list" in r[1]]
    assert len(listing) == 1, listing
    wd, script = listing[0]
    assert wd == "e2e", listing
    assert (
        script.splitlines()[0] == 'npx playwright test --list > "$RUNNER_TEMP/playwright-list.txt"'
    )


def test_b_each_shard_runs_and_lists_exactly_its_share() -> None:
    jobs = _e2e_jobs()
    n = _shard_count(jobs)
    runs = _runs(jobs["e2e-shard"])
    playwright = [r for r in runs if "playwright test" in r[1] and "install" not in r[1]]
    assert playwright == [
        (
            "e2e",
            f'npx playwright test --list --shard=${{{{ matrix.shard }}}}/{n} > "$RUNNER_TEMP/e2e-shard-${{{{ matrix.shard }}}}.txt"',
        ),
        ("e2e", f"npx playwright test --shard=${{{{ matrix.shard }}}}/{n}"),
    ], playwright


def test_c_the_aggregate_requires_the_shard_lists_to_partition_the_full_list() -> None:
    jobs = _e2e_jobs()
    n = _shard_count(jobs)
    agg = jobs["e2e"]
    assert agg["name"] == "E2E (Playwright smoke suite)"
    assert agg.get("if") == "always()"
    assert set(agg["needs"]) == {"e2e-shard", "e2e-session"}
    verify = [r for _, r in _runs(agg) if "scripts.shard_partition verify" in r]
    assert len(verify) == 1, verify
    assert f"--of {n}" in verify[0] and "ids-playwright-list.txt" in verify[0], verify


def test_e_every_list_comes_from_the_same_tree() -> None:
    """The union means something only if every list was taken from one commit:
    no checkout in any E2E job overrides what it checks out."""
    jobs = _e2e_jobs()
    for name in ("e2e-shard", "e2e-session", "e2e"):
        checkouts = [
            s for s in jobs[name]["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")
        ]
        assert len(checkouts) == 1, (name, checkouts)
        assert "with" not in checkouts[0] or not set(checkouts[0]["with"]) & {
            "ref",
            "repository",
        }, (
            name,
            checkouts[0],
        )


def _run_aggregate_block(tmp_path: Path, full: str | None, shards: dict[int, str | None]) -> int:
    """Execute the aggregate's own verification block, against these lists."""
    import os
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash here")
    jobs = _e2e_jobs()
    block = [
        s for s in jobs["e2e"]["steps"] if "scripts.shard_partition verify" in str(s.get("run", ""))
    ]
    assert len(block) == 1
    temp = tmp_path / "runner"
    (temp / "e2e").mkdir(parents=True)
    if full is not None:
        (temp / "e2e" / "playwright-list.txt").write_text(full, encoding="utf-8")
    for k, text in shards.items():
        if text is not None:
            (temp / "e2e" / f"e2e-shard-{k}.txt").write_text(text, encoding="utf-8")
    workspace = find_workflows_dir(pathlib.Path(__file__).resolve()).parent.parent
    env = {**os.environ, "RUNNER_TEMP": str(temp), "GITHUB_WORKSPACE": str(workspace)}
    proc = subprocess.run(  # noqa: S603 - the workflow's own block, fixture inputs
        [bash, "--noprofile", "--norc", "-e", "-c", block[0]["run"]],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.returncode


def _share(*specs: str) -> str:
    return _listing(*specs)


@pytest.mark.parametrize(
    ("label", "full", "shards", "passes"),
    [
        (
            "a true partition",
            _share("a", "b", "c", "d"),
            {1: _share("a"), 2: _share("b"), 3: _share("c"), 4: _share("d")},
            True,
        ),
        (
            "a missing full list",
            None,
            {1: _share("a"), 2: _share("b"), 3: _share("c"), 4: _share("d")},
            False,
        ),
        (
            "an empty full list",
            "Listing tests:\nTotal: 0 tests in 0 files\n",
            {1: _share(), 2: _share(), 3: _share(), 4: _share()},
            False,
        ),
        (
            "a missing shard list",
            _share("a", "b", "c", "d"),
            {1: _share("a"), 2: _share("b"), 3: _share("c", "d"), 4: None},
            False,
        ),
        (
            "a test in two shards",
            _share("a", "b", "c"),
            {1: _share("a"), 2: _share("a", "b"), 3: _share("c"), 4: _share("c")},
            False,
        ),
        (
            "a test in no shard",
            _share("a", "b", "c", "d"),
            {1: _share("a"), 2: _share("b"), 3: _share("c"), 4: _share("a")},
            False,
        ),
    ],
    ids=["partition", "missing-full", "empty-full", "missing-shard", "duplicate", "gap"],
)
def test_d_the_aggregate_cannot_pass_on_nothing(tmp_path, label, full, shards, passes) -> None:
    """(d): a missing or empty list is a FAILURE, never an empty set matching an
    empty set -- the silent-green shape. Run through the aggregate's own block."""
    rc = _run_aggregate_block(tmp_path, full, shards)
    assert (rc == 0) == passes, (label, rc)


def test_a_truncated_listing_with_specs_but_no_total_is_could_not_look(tmp_path, capsys) -> None:
    # A listing cut off before its `Total:` line may be missing specs, so it
    # cannot certify that every spec on disk is in the run. Without this row the
    # `Total:` check turned nothing red when removed (the other could-not-look
    # rows name no spec, and the no-specs branch caught them first).
    truncated = "Listing tests:\n  [chromium] › a.spec.ts:10:5 › a test\n"
    root, lst = _repo(tmp_path, ["a.spec.ts"], truncated, {})
    code, out = _run(root, lst, capsys)
    assert code == 2, out


# --- #579: every script file is in the run or declared ----------------------------------


def test_a_spec_renamed_out_of_the_pattern_is_a_finding(tmp_path, capsys) -> None:
    # `a.specs.ts` is not collected, so it is not in the listing: the old gate
    # scanned only `*.spec.ts` and stayed green over it.
    root, lst = _repo(tmp_path, ["b.spec.ts", "a.specs.ts"], _listing("b.spec.ts"), {})
    code, out = _run(root, lst, capsys)
    assert code == 1, out
    assert "e2e/a.specs.ts: not in `npx playwright test --list` and not declared" in out, out


def test_a_listed_spec_under_another_extension_counts_as_listed(tmp_path, capsys) -> None:
    root, lst = _repo(
        tmp_path, ["a.spec.tsx", "b.test.js"], _listing("a.spec.tsx", "b.test.js"), {}
    )
    code, out = _run(root, lst, capsys)
    assert code == 0, out


def test_declared_non_suite_files_pass_and_are_counted(tmp_path, capsys) -> None:
    declared = {"helpers/": "imported by specs", "globalSetup.ts": "setup"}
    root, lst = _repo(
        tmp_path,
        ["a.spec.ts", "helpers/auth.ts", "globalSetup.ts"],
        _listing("a.spec.ts"),
        declared,
    )
    code, out = _run(root, lst, capsys)
    assert code == 0, out
    assert "3 script file(s) under e2e/: 1 in CI's run, 2 declared non-suite" in out, out


def test_a_declaration_matching_no_file_is_stale(tmp_path, capsys) -> None:
    root, lst = _repo(tmp_path, ["a.spec.ts"], _listing("a.spec.ts"), {"gone.ts": "was a helper"})
    code, out = _run(root, lst, capsys)
    assert code == 1, out
    assert "'gone.ts' matches no file -- stale" in out, out


def test_a_declared_file_the_run_lists_is_a_finding(tmp_path, capsys) -> None:
    root, lst = _repo(tmp_path, ["a.spec.ts"], _listing("a.spec.ts"), {"a.spec.ts": "not a test"})
    code, out = _run(root, lst, capsys)
    assert code == 1, out
    assert "declared a non-suite file ('a.spec.ts') but the run lists it" in out, out


@pytest.mark.parametrize(
    "declared",
    [None, {"helpers/": ""}, ["helpers/"]],
    ids=["missing", "empty-reason", "not-a-mapping"],
)
def test_a_missing_or_malformed_declarations_file_is_could_not_look(
    tmp_path, capsys, declared
) -> None:
    root, lst = _repo(tmp_path, ["a.spec.ts"], _listing("a.spec.ts"), None)
    if declared is not None:
        d = tmp_path / ".github" / "e2e-non-suite-files.json"
        d.parent.mkdir(parents=True, exist_ok=True)
        d.write_text(json.dumps(declared), encoding="utf-8")
    code, out = _run(root, lst, capsys)
    assert code == 2, out
    assert "e2e-non-suite-files.json" in out, out


def test_non_script_files_are_not_compared(tmp_path, capsys) -> None:
    root, lst = _repo(
        tmp_path, ["a.spec.ts", "README.md", "package.json"], _listing("a.spec.ts"), {}
    )
    code, out = _run(root, lst, capsys)
    assert code == 0, out


# --- review of 81871d4 ------------------------------------------------------------------


@pytest.mark.parametrize("name", ["a.spec.ts.disabled", "a.spec.ts.bak", "a.spec.TS"])
def test_a_spec_disabled_by_its_final_suffix_or_case_is_a_finding(tmp_path, capsys, name) -> None:
    # Only the final suffix was read, so these read as "not a script" and passed.
    root, lst = _repo(tmp_path, ["b.spec.ts", name], _listing("b.spec.ts"), {})
    code, out = _run(root, lst, capsys)
    assert code == 1, out
    assert f"e2e/{name}: not in `npx playwright test --list` and not declared" in out, out


def test_a_spec_named_file_under_a_declared_directory_the_run_lists_is_a_finding(
    tmp_path, capsys
) -> None:
    # testDir "." with no testIgnore lists it, so the DIRECTORY declaration and
    # the run disagree about it.
    root, lst = _repo(
        tmp_path,
        ["a.spec.ts", "helpers/auth.ts", "helpers/s9.spec.ts"],
        _listing("a.spec.ts", "helpers/s9.spec.ts"),
        {"helpers/": "imported by specs"},
    )
    code, out = _run(root, lst, capsys)
    assert code == 1, out
    assert "e2e/helpers/s9.spec.ts: declared a non-suite file ('helpers/')" in out, out
